"""
equipment_checker/views.py
==========================
Django views for the Equipment Documentation Checker page.
Handles file upload → Celery task dispatch → status polling → CSV export.
"""
import io
import csv
import json
import uuid
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from equipment_checker.tasks import process_equipment_check_task, SUPPORTED_EXTS

logger = logging.getLogger(__name__)


@login_required
def equipment_checker(request):
    """Main page for the equipment documentation checker."""
    return render(request, 'docsAppR/equipment_checker.html')


@login_required
def guide_equipment_checker(request):
    """Printable user guide for the equipment checker."""
    return render(request, 'docsAppR/guide_equipment_checker.html')


@login_required
@csrf_exempt
@require_POST
def equipment_upload(request):
    """
    Accept uploaded job site photos and/or a room-photo PDF report + line items,
    save to a temp session folder, then fire the Celery verification task.
    At least one of: images OR a PDF report must be provided.
    """
    image_files = request.FILES.getlist('images')
    job_pdf_file = request.FILES.get('job_pdf')
    raw_items_text = request.POST.get('line_items', '').strip()

    if not image_files and not job_pdf_file:
        return JsonResponse(
            {'error': 'Please upload a PDF report or individual photos (or both)'},
            status=400
        )
    if not raw_items_text:
        return JsonResponse({'error': 'No line items provided'}, status=400)

    raw_items = [line for line in raw_items_text.splitlines() if line.strip()]
    if not raw_items:
        return JsonResponse({'error': 'No valid line items found'}, status=400)

    session_id = str(uuid.uuid4())
    input_dir = Path(settings.MEDIA_ROOT) / 'equipment_sessions' / session_id / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)

    job_pdf_path = ''
    if job_pdf_file:
        if Path(job_pdf_file.name).suffix.lower() != '.pdf':
            return JsonResponse({'error': 'Job report must be a PDF file'}, status=400)
        pdf_dest = input_dir / 'job_report.pdf'
        with open(pdf_dest, 'wb') as out:
            for chunk in job_pdf_file.chunks():
                out.write(chunk)
        job_pdf_path = str(pdf_dest)

    saved_paths = []
    skipped = []
    for f in image_files:
        if Path(f.name).suffix.lower() not in SUPPORTED_EXTS:
            skipped.append(f.name)
            continue
        dest = input_dir / f.name
        if dest.exists():
            stem, sfx = Path(f.name).stem, Path(f.name).suffix
            dest = input_dir / f'{stem}_{uuid.uuid4().hex[:6]}{sfx}'
        with open(dest, 'wb') as out:
            for chunk in f.chunks():
                out.write(chunk)
        saved_paths.append(str(dest))

    model = request.POST.get('model', 'claude-sonnet-4-6')
    task = process_equipment_check_task.delay(
        session_id, saved_paths, raw_items, model, job_pdf_path
    )

    logger.info(
        f"[equipment_upload] session={session_id} pdf={bool(job_pdf_path)} "
        f"images={len(saved_paths)} items={len(raw_items)} task={task.id}"
    )

    return JsonResponse({
        'task_id': task.id,
        'session_id': session_id,
        'has_pdf': bool(job_pdf_path),
        'image_count': len(saved_paths),
        'item_count': len(raw_items),
        'skipped': skipped,
    })


@login_required
def equipment_task_status(request):
    """Poll Celery task status. Returns JSON with state + step/results."""
    from celery.result import AsyncResult

    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'task_id required'}, status=400)

    r = AsyncResult(task_id)

    if r.state == 'PENDING':
        return JsonResponse({'state': 'PENDING', 'step': 'Waiting in queue…', 'percent': 0})

    if r.state == 'PROGRESS':
        meta = r.info or {}
        return JsonResponse({
            'state': 'PROGRESS',
            'step': meta.get('step', ''),
            'percent': meta.get('percent', 0),
        })

    if r.state == 'SUCCESS':
        return JsonResponse({'state': 'SUCCESS', 'result': r.result})

    return JsonResponse({'state': 'FAILURE', 'error': str(r.result)})


@login_required
@csrf_exempt
@require_POST
def equipment_export_csv(request):
    """Accept results JSON from the client, return a CSV download."""
    try:
        data = json.loads(request.body)
        results = data.get('results', [])
    except Exception:
        return HttpResponse('Invalid JSON', status=400)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Room', 'Description', 'Status', 'Verification Note'])
    for row in results:
        writer.writerow([
            row.get('room', ''),
            row.get('description', ''),
            row.get('status', ''),
            row.get('note', ''),
        ])

    response = HttpResponse(buf.getvalue(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="equipment_check.csv"'
    return response
