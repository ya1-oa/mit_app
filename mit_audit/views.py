"""
mit_audit/views.py

Views:
  dashboard          — list of all MIT audits with status cards
  audit_detail       — single audit: dimensions, equipment, photo observations
  trigger_audit      — start a new audit for a claim (AJAX POST)
  approve_dimensions — approve / correct dimension rows (AJAX POST)
  status_api         — JSON status for task polling
  download_report    — serve a PDF by download_token (no auth required)
  config_view        — edit MITDay3Config (admin-level)

Note: there is no longer a global template upload.  Each client's 82-MIT
workbook is found automatically via ClaimFile(file_type='82-MIT') DB record,
with a filesystem fallback to the client's Templates folder.
"""
import json
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    from mit_audit.models import (
        MITDay3Audit, MITDay3Config, MITRequiredEquipment, MITReferencePhoto,
    )
    from docsAppR.models import Client

    # ── Audits history ───────────────────────────────────────────────────────
    audits = (
        MITDay3Audit.objects
        .select_related('client', 'triggered_by')
        .prefetch_related('reports', 'required_equipment')
        .filter(archived=False)
        .order_by('-created_at')[:50]
    )
    config = MITDay3Config.get()

    # ── Run-tab: claim list (deduplicated) ───────────────────────────────────
    _all_clients = (
        Client.objects
        .filter(archived=False, encircle_claim_id__isnull=False)
        .exclude(encircle_claim_id='')
        .order_by('-created_at')
    )
    _seen = {}
    for c in _all_clients:
        key = (c.pOwner or '').strip().lower()
        if key not in _seen:
            _seen[key] = c
    clients = sorted(_seen.values(), key=lambda c: (c.pOwner or '').lower())

    # ── Run-tab: default equipment ───────────────────────────────────────────
    # Reference job: 12404 FERRIS, Cleveland OH — ASSURANT / WTR
    # Source: WINTERS/SHARONE standard quantities confirmed by PM
    # ── Drying Chamber Stabilization (stab photo required) ──────────────
    # Default: 1 DH + 1 AFD + 1 double-zipper set per DC — PM can override
    # ── Per-Room Standard Mitigation (from Total Equipment tab) ──────────
    default_equipment = [
        # Stabilization items — require a "connected + running" photo per DC
        {'category': 'dehumidifier',  'display_name': 'Dehumidifier (DHM/LGR)',       'required_quantity': 3,  'requires_stabilization': True},
        {'category': 'air_cleaner',   'display_name': 'AFD / NAFAN / HEPA Scrubber',  'required_quantity': 3,  'requires_stabilization': True},
        {'category': 'zipper_wall',   'display_name': 'Zipper Wall + Poles (BARRZ)',        'required_quantity': 10, 'requires_stabilization': True},
        {'category': 'double_zipper', 'display_name': 'Double Zipper Wall + Poles (BARRZ)', 'required_quantity': 0,  'requires_stabilization': True},
        {'category': 'tension_poles', 'display_name': 'Tension Poles (BARRP)',               'required_quantity': 10, 'requires_stabilization': False},
        # Standard mitigation equipment — qty from Total Equipment tab
        {'category': 'blower',        'display_name': 'Air Mover / Blower (DRY)',     'required_quantity': 36, 'requires_stabilization': False},
        {'category': 'hydroxyl',      'display_name': 'Hydroxyl Generator (DODHY)',   'required_quantity': 3,  'requires_stabilization': False},
        {'category': 'ceiling_cavity','display_name': 'Ceiling Cavity Drying (CCDU)', 'required_quantity': 3,  'requires_stabilization': False},
        {'category': 'wall_cavity',   'display_name': 'Wall Cavity Drying (WCDU)',    'required_quantity': 4,  'requires_stabilization': False},
        {'category': 'floor_drying',  'display_name': 'Wood Floor Dry Mat (WFI)',     'required_quantity': 4,  'requires_stabilization': False},
        {'category': 'drying_blanket','display_name': 'Drying Blanket / Mat (HTBL)',  'required_quantity': 2,  'requires_stabilization': False},
        {'category': 'bound_water',   'display_name': 'Bound Water Cavity (BWCDU)',   'required_quantity': 2,  'requires_stabilization': False},
        {'category': 'heat_air_mover','display_name': 'Heat Air Mover (HTAM)',        'required_quantity': 0,  'requires_stabilization': False},
        {'category': 'antimicrobial', 'display_name': 'Anti-Microbial (GRM)',         'required_quantity': 0,  'requires_stabilization': False},
    ]

    # ── Library-tab: reference photo counts per category ─────────────────────
    from django.db.models import Count
    ref_counts = dict(
        MITReferencePhoto.objects
        .filter(is_active=True, approved=True)
        .values('category')
        .annotate(n=Count('id'))
        .values_list('category', 'n')
    )
    ref_total = sum(ref_counts.values())

    return render(request, 'mit_audit/hub.html', {
        'audits':           audits,
        'config':           config,
        'clients':          clients,
        'default_equipment': default_equipment,
        'ref_counts':       ref_counts,
        'ref_total':        ref_total,
        'active_tab':       request.GET.get('tab', 'run'),
    })


# ---------------------------------------------------------------------------
# Audit detail
# ---------------------------------------------------------------------------

@login_required
def audit_detail(request, audit_id):
    from mit_audit.models import MITDay3Audit

    audit = get_object_or_404(
        MITDay3Audit.objects
        .select_related('client', 'triggered_by')
        .prefetch_related(
            'room_dimensions',
            'required_equipment__photo_observation',
            'reports',
        ),
        pk=audit_id,
    )
    return render(request, 'mit_audit/audit_detail.html', {'audit': audit})


# ---------------------------------------------------------------------------
# Start a new audit (AJAX POST)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def trigger_audit(request):
    """
    Body JSON: { "client_id": 123 }
    Creates a MITDay3Audit and starts the Celery pipeline.
    """
    from mit_audit.models import MITDay3Audit
    from mit_audit.tasks import start_audit_pipeline
    from docsAppR.models import Client

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    client_id = data.get('client_id')
    if not client_id:
        return JsonResponse({'error': 'client_id required'}, status=400)

    client = get_object_or_404(Client, id=client_id, archived=False)

    audit = MITDay3Audit.objects.create(
        client            = client,
        encircle_claim_id = client.encircle_claim_id or '',
        triggered_by      = request.user,
    )
    start_audit_pipeline(audit.pk)
    return JsonResponse({'ok': True, 'audit_id': audit.pk})


# ---------------------------------------------------------------------------
# Approve / update dimension rows (AJAX POST)
# ---------------------------------------------------------------------------

@login_required
@require_POST
def approve_dimensions(request, audit_id):
    """
    Body JSON:
      { "action": "approve_all" }
      OR
      { "action": "update", "rows": [{ "id": 1, "length": 12, "width": 10, "height": 8, "approved": true }] }
    """
    from mit_audit.models import MITDay3Audit, MITRoomDimension
    from mit_audit.tasks import approve_and_continue

    audit = get_object_or_404(MITDay3Audit, pk=audit_id)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    action = data.get('action', 'approve_all')

    if action == 'approve_all':
        MITRoomDimension.objects.filter(audit=audit).update(approved=True)
        approve_and_continue.delay(audit_id)
        return JsonResponse({'ok': True, 'action': 'approve_all'})

    if action == 'update':
        rows = data.get('rows', [])
        for row in rows:
            dim = get_object_or_404(MITRoomDimension, id=row['id'], audit=audit)
            if 'length' in row:
                dim.length = row['length']
            if 'width' in row:
                dim.width = row['width']
            if 'height' in row:
                dim.height = row['height']
            if 'approved' in row:
                dim.approved = bool(row['approved'])
            dim.save()

        # If all are now approved, fire the next step
        if not audit.room_dimensions.filter(approved=False).exists():
            approve_and_continue.delay(audit_id)
            return JsonResponse({'ok': True, 'pipeline_started': True})
        return JsonResponse({'ok': True, 'pipeline_started': False})

    return JsonResponse({'error': f'Unknown action: {action}'}, status=400)


# ---------------------------------------------------------------------------
# Status polling (AJAX GET)
# ---------------------------------------------------------------------------

@login_required
def status_api(request, audit_id):
    from mit_audit.models import MITDay3Audit

    from mit_audit.models import MITAuditLog

    audit = get_object_or_404(MITDay3Audit, pk=audit_id)
    dims_total    = audit.room_dimensions.count()
    dims_review   = audit.room_dimensions.filter(needs_review=True, approved=False).count()
    equip_total   = audit.required_equipment.count()
    obs_total     = audit.required_equipment.filter(
        photo_observation__isnull=False
    ).count()
    reports_done  = audit.reports.count()

    # Live log lines — all entries newest first, then reversed for display
    logs = list(
        MITAuditLog.objects.filter(audit=audit)
        .order_by('created_at')
        .values_list('message', flat=True)
    )

    return JsonResponse({
        'status':         audit.status,
        'status_label':   audit.get_status_display(),
        'error':          audit.error_message,
        'dims_total':     dims_total,
        'dims_review':    dims_review,
        'equip_total':    equip_total,
        'obs_total':      obs_total,
        'reports_done':   reports_done,
        'complete':       audit.status == 'complete',
        'workbook_ready': bool(audit.workbook_path),
        'logs':           logs,
    })


# ---------------------------------------------------------------------------
# Download a report PDF (unauthenticated — token required)
# ---------------------------------------------------------------------------

def download_report(request, token):
    from mit_audit.models import MITReport

    report = get_object_or_404(MITReport, download_token=token)
    path   = Path(report.file_path)
    if not path.exists():
        raise Http404('Report PDF not found on disk.')

    filename = f'MIT_Audit_{report.audit_id}_{report.report_type}.pdf'
    return FileResponse(
        open(path, 'rb'),
        as_attachment=True,
        filename=filename,
        content_type='application/pdf',
    )


# ---------------------------------------------------------------------------
# Config view
# ---------------------------------------------------------------------------

@login_required
def config_view(request):
    from mit_audit.models import MITDay3Config

    config = MITDay3Config.get()

    if request.method == 'POST':
        p = request.POST
        config.job_info_sheet        = p.get('job_info_sheet', config.job_info_sheet)
        config.total_equipment_sheet = p.get('total_equipment_sheet', config.total_equipment_sheet)
        raw_dim_map = p.get('dimension_cell_map', '')
        raw_eq_map  = p.get('equipment_cell_map', '')
        try:
            if raw_dim_map.strip():
                config.dimension_cell_map = json.loads(raw_dim_map)
        except json.JSONDecodeError:
            pass
        try:
            if raw_eq_map.strip():
                config.equipment_cell_map = json.loads(raw_eq_map)
        except json.JSONDecodeError:
            pass
        config.save()
        return redirect('mit_audit:config')

    return render(request, 'mit_audit/config.html', {
        'config': config,
    })


# ---------------------------------------------------------------------------
# Upload MIT Day 3 template
# ---------------------------------------------------------------------------

@login_required
@require_POST
def upload_template(request):
    """Accept a .xlsx template upload and save to MEDIA_ROOT/mit_templates/."""
    from mit_audit.models import MITDay3Config

    f = request.FILES.get('template')
    if not f:
        return JsonResponse({'error': 'No file uploaded'}, status=400)
    if not f.name.endswith('.xlsx'):
        return JsonResponse({'error': 'Only .xlsx files accepted'}, status=400)

    dest_dir = Path(settings.MEDIA_ROOT) / 'mit_templates'
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / 'MIT_Day3.xlsx'
    with open(dest, 'wb') as out:
        for chunk in f.chunks():
            out.write(chunk)

    config = MITDay3Config.get()
    config.template_path = 'mit_templates/MIT_Day3.xlsx'
    config.save(update_fields=['template_path', 'updated_at'])

    logger.info('[MIT] Template uploaded → %s', dest)
    return JsonResponse({'ok': True, 'path': str(dest)})


# ---------------------------------------------------------------------------
# Test-run page  — run reports against any claim without a workbook
# ---------------------------------------------------------------------------

@login_required
def test_run_view(request):
    """
    GET  — show the test-run form (client picker + equipment quantities).
    POST — create a MITDay3Audit + MITRequiredEquipment from the form,
           skip to the photo-review step, return {ok, audit_id}.
    """
    from mit_audit.models import MITDay3Audit, MITRequiredEquipment
    from docsAppR.models import Client

    # GET → redirect to unified hub (Run tab)
    if request.method == 'GET':
        return redirect('mit_audit:dashboard')

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        client_id = data.get('client_id')
        equipment = data.get('equipment', [])   # [{category, display_name, required_quantity, requires_stabilization}]

        if not client_id:
            return JsonResponse({'error': 'client_id required'}, status=400)

        client = get_object_or_404(Client, pk=client_id, archived=False)
        if not client.encircle_claim_id:
            return JsonResponse({'error': 'This client has no Encircle claim ID.'}, status=400)

        audit = MITDay3Audit.objects.create(
            client            = client,
            encircle_claim_id = client.encircle_claim_id,
            triggered_by      = request.user,
            is_test_run       = True,
        )

        created_count = 0
        for item in equipment:
            qty = int(item.get('required_quantity') or 0)
            if qty <= 0:
                continue
            MITRequiredEquipment.objects.create(
                audit                        = audit,
                display_name                 = item.get('display_name', '').strip() or item.get('category', 'other'),
                equipment_type               = item.get('category', 'other'),
                category                     = item.get('category', 'other'),
                required_quantity            = qty,
                source_sheet                 = 'test_run',
                workbook_row                 = None,
                workbook_cell                = '',
                requires_stabilization_photo = bool(item.get('requires_stabilization')),
            )
            created_count += 1

        if created_count == 0:
            audit.delete()
            return JsonResponse({'error': 'Enter at least one equipment type with qty > 0.'}, status=400)

        # ── Generate required-equipment reports immediately (no AI needed) ──
        # These just list what equipment is expected; the missing-* reports
        # (which compare expected vs observed) are generated by the Celery task
        # after AI photo review completes.
        from mit_audit.models import MITAuditLog, MITReport
        from mit_audit import report_builder as rb

        early_reports = []
        MITAuditLog.objects.create(
            audit=audit,
            message=f'Audit created — {created_count} equipment type(s) on this job.',
        )
        for report_type, builder_fn in [
            ('required_equipment', rb.build_required_equipment_report),
            ('required_stab',      rb.build_required_stab_report),
        ]:
            try:
                pdf_path = builder_fn(audit)
                size = Path(pdf_path).stat().st_size
                rpt, _ = MITReport.objects.update_or_create(
                    audit=audit, report_type=report_type,
                    defaults={'file_path': pdf_path, 'file_size_bytes': size},
                )
                early_reports.append({'type': report_type, 'url': rpt.get_download_url()})
                MITAuditLog.objects.create(
                    audit=audit,
                    message=f'📄 Report ready: {report_type.replace("_", " ").title()}',
                )
            except Exception as exc:
                logger.warning('[MIT] Early %s report failed for audit #%d: %s',
                               report_type, audit.pk, exc)

        MITAuditLog.objects.create(
            audit=audit,
            message='Handing off to Celery worker for AI photo review…',
        )

        # Skip workbook — go straight to photo review
        from mit_audit.tasks import review_encircle_photos
        review_encircle_photos.delay(audit.pk)

        return JsonResponse({'ok': True, 'audit_id': audit.pk, 'reports': early_reports})
    # GET is handled by the dashboard hub — should not reach here.


@login_required
def test_run_results(request, audit_id):
    """
    AJAX: return AI observations for a completed audit so the test-run page
    can render them without a page reload.
    """
    from mit_audit.models import MITDay3Audit, MITPhotoObservation

    audit = get_object_or_404(MITDay3Audit, pk=audit_id)
    rows = []
    for eq in audit.required_equipment.prefetch_related('photo_observation').all():
        obs = getattr(eq, 'photo_observation', None)
        rows.append({
            'display_name':       eq.display_name,
            'category':           eq.category,
            'required_quantity':  eq.required_quantity,
            'visible_quantity':   obs.visible_quantity if obs else None,
            'ai_confidence':      obs.ai_confidence if obs else None,
            'ai_notes':           obs.ai_notes if obs else '',
            'recommended_action': obs.recommended_action if obs else '',
            'status':             obs.status if obs else 'missing',
            'stab_required':      eq.requires_stabilization_photo,
            'stab_found':         obs.stabilization_photo_found if obs else None,
        })

    reports = []
    for r in audit.reports.all():
        reports.append({
            'type':  r.report_type,
            'label': r.get_report_type_display(),
            'url':   r.get_download_url(),
        })

    return JsonResponse({
        'ok':      True,
        'status':  audit.status,
        'error':   audit.error_message,
        'rows':    rows,
        'reports': reports,
    })


# ---------------------------------------------------------------------------
# Archive a test run
# ---------------------------------------------------------------------------

@login_required
@require_POST
def archive_test_run(request, audit_id):
    """Toggle archived flag on a test-run audit (soft-hide from run history)."""
    from mit_audit.models import MITDay3Audit
    audit = get_object_or_404(MITDay3Audit, pk=audit_id, is_test_run=True)
    audit.archived = not audit.archived
    audit.save(update_fields=['archived'])
    return JsonResponse({'ok': True, 'archived': audit.archived})


# ---------------------------------------------------------------------------
# Reference photo library
# ---------------------------------------------------------------------------

@login_required
def reference_photos(request):
    """
    Grid view of all imported reference photos.
    Staff can tag each photo with an equipment category and approve/reject.
    """
    from mit_audit.models import MITReferencePhoto, MITRequiredEquipment

    filter_cat = request.GET.get('category', '')
    filter_status = request.GET.get('status', 'pending')   # pending | approved | all

    qs = MITReferencePhoto.objects.filter(is_active=True)
    if filter_cat:
        qs = qs.filter(category=filter_cat)
    if filter_status == 'pending':
        qs = qs.filter(approved=False)
    elif filter_status == 'approved':
        qs = qs.filter(approved=True)

    photos = qs.order_by('category', '-created_at')[:200]

    # Count by category for the sidebar
    from django.db.models import Count
    counts = (
        MITReferencePhoto.objects
        .filter(is_active=True, approved=True)
        .values('category')
        .annotate(n=Count('id'))
        .order_by('category')
    )
    approved_by_cat = {c['category']: c['n'] for c in counts}
    total_approved  = sum(approved_by_cat.values())
    pending_count   = MITReferencePhoto.objects.filter(is_active=True, approved=False).count()

    return render(request, 'mit_audit/reference_photos.html', {
        'photos':           photos,
        'category_choices': MITRequiredEquipment.CATEGORY_CHOICES,
        'approved_by_cat':  approved_by_cat,
        'total_approved':   total_approved,
        'pending_count':    pending_count,
        'filter_cat':       filter_cat,
        'filter_status':    filter_status,
    })


@login_required
@require_POST
def tag_reference_photo(request, photo_id):
    """
    AJAX: update category + description on a reference photo, optionally approve.
    Body: { category, display_name, description, approve: bool }
    """
    from mit_audit.models import MITReferencePhoto
    from django.utils import timezone

    try:
        photo = MITReferencePhoto.objects.get(pk=photo_id, is_active=True)
    except MITReferencePhoto.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    data = json.loads(request.body)
    photo.category     = data.get('category', photo.category)
    photo.display_name = data.get('display_name', photo.display_name)
    photo.description  = data.get('description', photo.description)

    if data.get('approve'):
        photo.approved    = True
        photo.approved_by = request.user
        photo.approved_at = timezone.now()
    elif data.get('approve') is False:
        photo.approved    = False
        photo.approved_by = None
        photo.approved_at = None

    photo.save(update_fields=[
        'category', 'display_name', 'description',
        'approved', 'approved_by', 'approved_at',
    ])
    return JsonResponse({'ok': True, 'approved': photo.approved, 'category': photo.category})


@login_required
@require_POST
def delete_reference_photo(request, photo_id):
    """AJAX: soft-delete (is_active=False) a reference photo."""
    from mit_audit.models import MITReferencePhoto

    try:
        photo = MITReferencePhoto.objects.get(pk=photo_id)
    except MITReferencePhoto.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    photo.is_active = False
    photo.approved  = False
    photo.save(update_fields=['is_active', 'approved'])
    return JsonResponse({'ok': True})
