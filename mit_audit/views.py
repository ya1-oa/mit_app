"""
mit_audit/views.py

Views:
  dashboard         — list of all MIT audits with status cards
  audit_detail      — single audit: dimensions, equipment, photo observations
  trigger_audit     — start a new audit for a claim (AJAX POST)
  approve_dimensions — approve / correct dimension rows (AJAX POST)
  status_api        — JSON status for task polling
  download_report   — serve a PDF by download_token (no auth required)
  config_view       — edit MITDay3Config (admin-level)
  upload_template   — upload the MIT Day 3 .xlsx template
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
    from mit_audit.models import MITDay3Audit, MITDay3Config

    audits = (
        MITDay3Audit.objects
        .select_related('client', 'triggered_by')
        .prefetch_related('reports', 'required_equipment')
        .order_by('-created_at')[:50]
    )
    config = MITDay3Config.get()

    return render(request, 'mit_audit/dashboard.html', {
        'audits':             audits,
        'config':             config,
        'template_exists':    bool(config.template_path),
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

    audit = get_object_or_404(MITDay3Audit, pk=audit_id)
    dims_total    = audit.room_dimensions.count()
    dims_review   = audit.room_dimensions.filter(needs_review=True, approved=False).count()
    equip_total   = audit.required_equipment.count()
    obs_total     = sum(
        1 for e in audit.required_equipment.all()
        if hasattr(e, 'photo_observation')
    )
    reports_done  = audit.reports.count()

    return JsonResponse({
        'status':       audit.status,
        'status_label': audit.get_status_display(),
        'error':        audit.error_message,
        'dims_total':   dims_total,
        'dims_review':  dims_review,
        'equip_total':  equip_total,
        'obs_total':    obs_total,
        'reports_done': reports_done,
        'complete':     audit.status == 'complete',
        'workbook_ready': bool(audit.workbook_path),
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
    from mit_audit.workbook_service import get_template_path

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

    template_path = get_template_path()
    return render(request, 'mit_audit/config.html', {
        'config':         config,
        'template_exists': bool(template_path),
        'template_path':   str(template_path) if template_path else '—',
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
