"""
mit_audit/tasks.py

Celery task chain for the MIT Day 3 equipment audit pipeline.

Chain order (each step depends on the previous):
  1. extract_floor_plan_dimensions  — Encircle API → MITRoomDimension rows
  2. (manual approval gate in UI if any rows need_review)
  3. populate_mit_workbook          — write approved dims → workbook, LO recalc
  4. calculate_required_equipment   — read Total Equipment tab → MITRequiredEquipment
  5. review_encircle_photos         — Claude AI → MITPhotoObservation rows
  6. generate_mit_reports           — WeasyPrint two PDFs → MITReport rows
  7. send_mit_notification          — completion email

Tasks 1–2 and 3–7 are wired as Celery chains; the gap at step 2 (approval gate)
is bridged by the 'approve_all_dimensions' shortcut view for auto-approve when
all confidence scores are >= 0.75, or by a manual dashboard action.

Each task calls audit.set_status() before and after its work so the UI
can poll /mit/api/audit/<id>/status/ for live progress.
"""
import logging

from celery import chain, shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _log(audit, msg: str) -> None:
    """Append a live progress message to the audit log (visible in hub via status_api)."""
    from mit_audit.models import MITAuditLog
    MITAuditLog.objects.create(audit=audit, message=msg)
    logger.info('[MIT][%d] %s', audit.pk, msg)


# ---------------------------------------------------------------------------
# Step 1: Extract floor-plan dimensions from Encircle
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def extract_floor_plan_dimensions(self, audit_id: int):
    """
    Call Encircle API to fetch floor plan dimensions for the claim,
    create MITRoomDimension rows, and auto-approve high-confidence ones.
    """
    from mit_audit.models import MITDay3Audit, MITRoomDimension

    audit = MITDay3Audit.objects.select_related('client').get(pk=audit_id)
    audit.set_status('extracting_dims')

    encircle_id = audit.encircle_claim_id or audit.client.encircle_claim_id or ''
    if not encircle_id:
        audit.set_status('error', 'No Encircle claim ID — cannot fetch floor plan.')
        return {'ok': False, 'error': 'No Encircle claim ID'}

    try:
        from docsAppR.encircle_client import EncircleAPIClient
        api = EncircleAPIClient()
        raw = api.get_claim_floor_plan(encircle_id)
    except Exception as exc:
        logger.error('[MIT] extract_floor_plan_dimensions: Encircle API error: %s', exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            audit.set_status('error', f'Encircle API error: {exc}')
            return {'ok': False, 'error': str(exc)}

    rooms_extracted = _parse_encircle_floor_plan(raw)
    if not rooms_extracted:
        # No dimensions found — move straight to manual entry state
        audit.set_status('dims_review', 'No floor plan dimensions found in Encircle. Enter manually.')
        return {'ok': True, 'rooms': 0, 'needs_review': 0}

    MITRoomDimension.objects.filter(audit=audit).delete()  # clear any prior run

    needs_review_count = 0
    for room in rooms_extracted:
        conf  = room.get('confidence', 1.0)
        needs = conf < 0.75
        dim   = MITRoomDimension.objects.create(
            audit               = audit,
            room_name           = room['name'],
            length              = room.get('length'),
            width               = room.get('width'),
            height              = room.get('height'),
            source_floorplan_id = str(encircle_id),
            confidence_score    = conf,
            needs_review        = needs,
            approved            = not needs,  # auto-approve high-confidence
        )
        if needs:
            needs_review_count += 1

    logger.info('[MIT] Extracted %d rooms for audit #%d (%d flagged)',
                len(rooms_extracted), audit_id, needs_review_count)

    if needs_review_count:
        audit.set_status('dims_review')
        return {'ok': True, 'rooms': len(rooms_extracted), 'needs_review': needs_review_count}

    # All auto-approved — advance immediately
    audit.set_status('populating_wb')
    # Fire the next step without waiting (separate task so the chain can continue)
    populate_mit_workbook.delay(audit_id)
    return {'ok': True, 'rooms': len(rooms_extracted), 'needs_review': 0}


def _parse_encircle_floor_plan(raw) -> list[dict]:
    """
    Parse the floor plan API response into a list of room dicts.
    Encircle's /floor_plan_dimensions endpoint returns a structure like:
      { 'list': [ { 'floors': [ { 'features': [ ... ] } ] } ] }
    Each feature may have area, perimeter, or explicit dimension fields.
    """
    if not raw:
        return []

    rooms = []
    floor_list = raw.get('list', []) if isinstance(raw, dict) else []
    for floor_group in floor_list:
        for floor in floor_group.get('floors', []):
            for feature in floor.get('features', []):
                name = (
                    feature.get('label') or
                    feature.get('name') or
                    feature.get('room_type') or
                    'Unknown Room'
                )
                # Encircle may provide explicit L/W/H or just area
                length = _safe_float(feature.get('length') or feature.get('width_ft'))
                width  = _safe_float(feature.get('width')  or feature.get('length_ft'))
                height = _safe_float(feature.get('height') or feature.get('ceiling_height') or 8.0)
                area   = _safe_float(feature.get('area')   or feature.get('square_feet'))

                # If we only have area, estimate L and W assuming square
                if area and not (length and width):
                    import math
                    side = math.sqrt(area)
                    length = length or round(side, 2)
                    width  = width  or round(side, 2)

                confidence = 1.0 if (length and width) else 0.6
                rooms.append({
                    'name':       str(name).strip(),
                    'length':     length,
                    'width':      width,
                    'height':     height or 8.0,
                    'confidence': confidence,
                })

    return rooms


def _safe_float(val) -> float | None:
    try:
        return float(val) if val is not None else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Step 2 (optional gate): auto-approve all flagged dimensions
# Called by the dashboard 'Approve All' button or when user saves corrections.
# ---------------------------------------------------------------------------

@shared_task(bind=True)
def approve_and_continue(self, audit_id: int):
    """
    Called after the user approves all dimension rows in the review gate.
    Advances status and fires the workbook population step.
    """
    from mit_audit.models import MITDay3Audit, MITRoomDimension
    audit = MITDay3Audit.objects.get(pk=audit_id)
    MITRoomDimension.objects.filter(audit=audit, needs_review=True).update(approved=True)
    audit.set_status('populating_wb')
    populate_mit_workbook.delay(audit_id)
    return {'ok': True}


# ---------------------------------------------------------------------------
# Step 3: Populate the workbook and trigger LibreOffice recalc
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=1)
def populate_mit_workbook(self, audit_id: int):
    """
    1. Copy the MIT Day 3 template for this job (if not already done).
    2. Write approved room dimensions into the Job Information sheet.
    3. Trigger LibreOffice UNO (or subprocess fallback) recalculation.
    """
    from mit_audit.models import MITDay3Audit
    from mit_audit import workbook_service as ws

    audit = MITDay3Audit.objects.select_related('client').get(pk=audit_id)
    audit.set_status('populating_wb')

    # Locate and copy the client's existing 82-MIT workbook
    if not audit.workbook_path:
        try:
            path = ws.find_and_copy_client_workbook(audit)
            audit.workbook_path = path
            audit.save(update_fields=['workbook_path', 'updated_at'])
        except FileNotFoundError as exc:
            audit.set_status('error', str(exc))
            return {'ok': False, 'error': str(exc)}

    # Write dimensions
    dims = audit.room_dimensions.filter(approved=True)
    try:
        written = ws.write_dimensions(audit.workbook_path, dims)
    except Exception as exc:
        logger.error('[MIT] write_dimensions failed for audit #%d: %s', audit_id, exc)
        audit.set_status('error', f'Workbook write error: {exc}')
        return {'ok': False, 'error': str(exc)}

    logger.info('[MIT] Wrote %d rooms to workbook for audit #%d', len(written), audit_id)

    # Recalculate: try UNO first, then subprocess
    recalced = ws.recalculate_via_uno(audit.workbook_path)
    if not recalced:
        recalced = ws.recalculate_via_subprocess(audit.workbook_path)
    if not recalced:
        logger.warning(
            '[MIT] No recalc method succeeded for audit #%d; '
            'will read cached values from data_only open', audit_id
        )

    audit.set_status('calculating')
    calculate_required_equipment.delay(audit_id)
    return {'ok': True, 'rooms_written': len(written), 'recalculated': recalced}


# ---------------------------------------------------------------------------
# Step 4: Read Total Equipment tab → MITRequiredEquipment
# ---------------------------------------------------------------------------

@shared_task(bind=True)
def calculate_required_equipment(self, audit_id: int):
    """
    Open the recalculated workbook with data_only=True, scan the Total Equipment
    tab, and create MITRequiredEquipment rows for every item with qty > 0.
    """
    from mit_audit.models import MITDay3Audit, MITRequiredEquipment
    from mit_audit import workbook_service as ws

    audit = MITDay3Audit.objects.get(pk=audit_id)
    if not audit.workbook_path:
        audit.set_status('error', 'No workbook path — population step did not complete.')
        return {'ok': False}

    try:
        items = ws.read_total_equipment(audit.workbook_path)
    except Exception as exc:
        logger.error('[MIT] read_total_equipment failed for audit #%d: %s', audit_id, exc)
        audit.set_status('error', f'Equipment read error: {exc}')
        return {'ok': False, 'error': str(exc)}

    if not items:
        audit.set_status('error', 'No equipment with qty > 0 found in Total Equipment tab. '
                         'Check that the workbook recalculated correctly.')
        return {'ok': False, 'error': 'No equipment found'}

    # Clear any previous run's data
    MITRequiredEquipment.objects.filter(audit=audit).delete()

    for it in items:
        MITRequiredEquipment.objects.create(
            audit                        = audit,
            display_name                 = it['display_name'],
            equipment_type               = it['equipment_type'],
            category                     = it['category'],
            required_quantity            = it['required_quantity'],
            source_sheet                 = it['source_sheet'],
            workbook_row                 = it.get('workbook_row'),
            workbook_cell                = it.get('workbook_cell', ''),
            requires_stabilization_photo = it.get('requires_stabilization_photo', False),
        )

    logger.info('[MIT] Created %d required equipment rows for audit #%d', len(items), audit_id)
    audit.set_status('reviewing_photos')
    review_encircle_photos.delay(audit_id)
    return {'ok': True, 'items': len(items)}


# ---------------------------------------------------------------------------
# Step 5: AI photo review
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=1, soft_time_limit=600, time_limit=660)
def review_encircle_photos(self, audit_id: int):
    """
    Fetch Encircle photos for the claim and send them to Claude for review.
    Creates one MITPhotoObservation per MITRequiredEquipment row.
    """
    from mit_audit.models import MITDay3Audit, MITRequiredEquipment, MITPhotoObservation
    from mit_audit import photo_service as ps

    api_key = getattr(settings, 'ANTHROPIC_API_KEY', '')
    if not api_key:
        logger.error('[MIT] ANTHROPIC_API_KEY not set — skipping photo review')

    audit = MITDay3Audit.objects.select_related('client').get(pk=audit_id)
    audit.set_status('reviewing_photos')

    encircle_id = audit.encircle_claim_id or audit.client.encircle_claim_id or ''

    # Fetch photos
    _log(audit, f'Fetching photos from Encircle claim {encircle_id}…')
    photos = ps.fetch_encircle_photos(encircle_id) if encircle_id else []

    if photos:
        by_type: dict[str, int] = {}
        for p in photos:
            by_type[p.get('room_type', 'other')] = by_type.get(p.get('room_type', 'other'), 0) + 1
        breakdown = '  '.join(f'{k}: {v}' for k, v in by_type.items())
        _log(audit, f'Found {len(photos)} photos — {breakdown}')
    else:
        _log(audit, 'No photos found in Encircle — AI will flag all as missing')

    required_items = list(
        MITRequiredEquipment.objects.filter(audit=audit)
        .values('id', 'equipment_type', 'display_name', 'category',
                'required_quantity', 'requires_stabilization_photo')
    )

    if not required_items:
        audit.set_status('error', 'No required equipment — run calculation step first.')
        return {'ok': False}

    _log(audit, f'Starting AI review — {len(required_items)} equipment types…')

    # Run AI review (handles empty photos gracefully)
    try:
        if api_key:
            observations = ps.review_photos_with_ai(
                required_items, photos, api_key, task_self=self,
                log_fn=lambda msg: _log(audit, msg),
            )
        else:
            # No API key — create manual-review placeholders
            observations = [{
                **item,
                'visible_quantity':    0,
                'missing_quantity':    item['required_quantity'],
                'status':              'manual',
                'supporting_photo_ids': [],
                'ai_confidence':       'low',
                'ai_notes':            'AI review skipped — ANTHROPIC_API_KEY not configured.',
                'stabilization_check': {'required': item.get('requires_stabilization_photo'),
                                         'found': None, 'notes': ''},
                'recommended_action':  'Configure API key and re-run photo review.',
            } for item in required_items]
    except Exception as exc:
        logger.error('[MIT] review_photos_with_ai failed for audit #%d: %s', audit_id, exc)
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            audit.set_status('error', f'Photo review error: {exc}')
            return {'ok': False, 'error': str(exc)}

    # Persist observations
    MITPhotoObservation.objects.filter(required_item__audit=audit).delete()

    id_map = {it['equipment_type']: it['id'] for it in required_items}
    # Also map by display_name in case equipment_type didn't match
    name_map = {it['display_name'].lower(): it['id'] for it in required_items}

    for obs in observations:
        req_id = (
            id_map.get(obs.get('equipment_type')) or
            name_map.get((obs.get('display_name') or '').lower())
        )
        if not req_id:
            logger.warning('[MIT] Could not match observation to required item: %s', obs)
            continue
        stab_check = obs.get('stabilization_check') or {}
        MITPhotoObservation.objects.update_or_create(
            required_item_id = req_id,
            defaults={
                'visible_quantity':         int(obs.get('visible_quantity', 0)),
                'ai_confidence':            obs.get('ai_confidence', 'low'),
                'ai_notes':                 obs.get('ai_notes', ''),
                'supporting_photo_ids':     obs.get('supporting_photo_ids', []),
                'stabilization_photo_found': stab_check.get('found'),
                'recommended_action':       obs.get('recommended_action', ''),
                'ai_model':                 AI_MODEL,
            },
        )

    logger.info('[MIT] Saved %d photo observations for audit #%d', len(observations), audit_id)
    _log(audit, f'AI review done — {len(observations)} items reviewed. Generating missing-equipment reports…')
    audit.set_status('generating_reports')
    generate_mit_reports.delay(audit_id)
    return {'ok': True, 'photos_reviewed': len(photos), 'observations': len(observations)}


AI_MODEL = 'claude-sonnet-4-6'


# ---------------------------------------------------------------------------
# Step 6: Generate PDF reports
# ---------------------------------------------------------------------------

@shared_task(bind=True)
def generate_mit_reports(self, audit_id: int):
    """
    Run WeasyPrint for both report types and save MITReport rows.
    """
    from mit_audit.models import MITDay3Audit, MITReport
    from mit_audit import report_builder as rb

    audit = MITDay3Audit.objects.get(pk=audit_id)
    audit.set_status('generating_reports')

    # For test-run audits the required_* reports were already generated synchronously
    # in test_run_view before the Celery task fired, so we only build the missing-*
    # reports here (they depend on AI observations). For full-pipeline audits we
    # build all four.
    if audit.is_test_run:
        report_jobs = [
            ('missing_equipment', rb.build_missing_equipment_report),
            ('missing_stab',      rb.build_missing_stab_report),
        ]
    else:
        report_jobs = [
            ('required_equipment', rb.build_required_equipment_report),
            ('required_stab',      rb.build_required_stab_report),
            ('missing_equipment',  rb.build_missing_equipment_report),
            ('missing_stab',       rb.build_missing_stab_report),
        ]

    errors = []
    for report_type, builder_fn in report_jobs:
        try:
            pdf_path = builder_fn(audit)
            from pathlib import Path
            size = Path(pdf_path).stat().st_size
            MITReport.objects.update_or_create(
                audit=audit, report_type=report_type,
                defaults={'file_path': pdf_path, 'file_size_bytes': size},
            )
            logger.info('[MIT] %s report saved: %s', report_type, pdf_path)
            _log(audit, f'📄 Report ready: {report_type.replace("_", " ").title()}')
        except Exception as exc:
            logger.error('[MIT] %s report failed for audit #%d: %s', report_type, audit_id, exc)
            errors.append(f'{report_type}: {exc}')
            _log(audit, f'⚠ Report failed: {report_type} — {exc}')

    if errors:
        audit.set_status('error', '; '.join(errors))
        return {'ok': False, 'errors': errors}

    audit.status       = 'complete'
    audit.completed_at = timezone.now()
    audit.save(update_fields=['status', 'completed_at', 'updated_at'])
    _log(audit, '✅ All reports ready.')

    send_mit_notification.delay(audit_id)
    return {'ok': True}


# ---------------------------------------------------------------------------
# Step 7: Send email notification
# ---------------------------------------------------------------------------

@shared_task(bind=True)
def send_mit_notification(self, audit_id: int):
    from mit_audit.models import MITDay3Audit
    from mit_audit.email_utils import send_mit_completion_email

    audit = MITDay3Audit.objects.select_related('client').prefetch_related('reports').get(pk=audit_id)
    sent  = send_mit_completion_email(audit)
    return {'ok': sent}


# ---------------------------------------------------------------------------
# Entry point: kick off the pipeline for a given audit
# ---------------------------------------------------------------------------

def start_audit_pipeline(audit_id: int):
    """
    Public entry point — called by views or the Encircle webhook handler.
    Fires Step 1; subsequent steps chain automatically.
    """
    extract_floor_plan_dimensions.delay(audit_id)
    logger.info('[MIT] Pipeline started for audit #%d', audit_id)
