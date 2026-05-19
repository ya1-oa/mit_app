"""
sensor_renamer/views.py
=======================
Django views for the Sensor Image Renamer page.
Handles file upload → Celery task dispatch → status polling → ZIP download.
"""
import io
import json
import uuid
import zipfile
import logging
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from sensor_renamer.tasks import (
    process_sensor_images_task,
    ALL_SUBFOLDERS, SUB_NA, SUPPORTED_EXTS,
    build_filenames, result_has_na, safe_dest,
)

logger = logging.getLogger(__name__)


@login_required
def sensor_image_renamer(request):
    """Main page for the sensor image renamer tool."""
    return render(request, 'docsAppR/sensor_image_renamer.html', {
        'subfolders': ALL_SUBFOLDERS,
        'sub_na': SUB_NA,
    })


@login_required
def guide_sensor_renamer(request):
    """Printable user guide for the sensor image renamer."""
    return render(request, 'docsAppR/guide_sensor_renamer.html')


@login_required
@csrf_exempt
@require_POST
def sensor_upload(request):
    """
    Accept uploaded sensor images, save to a temp session folder,
    then fire the Celery processing task.
    """
    files = request.FILES.getlist('images')
    if not files:
        return JsonResponse({'error': 'No files uploaded'}, status=400)

    session_id = str(uuid.uuid4())
    input_dir = Path(settings.MEDIA_ROOT) / 'sensor_sessions' / session_id / 'input'
    input_dir.mkdir(parents=True, exist_ok=True)

    saved_paths = []
    skipped = []
    for f in files:
        if Path(f.name).suffix.lower() not in SUPPORTED_EXTS:
            skipped.append(f.name)
            continue
        dest = input_dir / f.name
        if dest.exists():
            stem, sfx = Path(f.name).stem, Path(f.name).suffix
            dest = input_dir / f"{stem}_{uuid.uuid4().hex[:6]}{sfx}"
        with open(dest, 'wb') as out:
            for chunk in f.chunks():
                out.write(chunk)
        saved_paths.append(str(dest))

    if not saved_paths:
        return JsonResponse({'error': 'No supported image files received'}, status=400)

    model = request.POST.get('model', 'claude-sonnet-4-6')
    try:
        workers = max(1, min(16, int(request.POST.get('workers', 4))))
    except (ValueError, TypeError):
        workers = 4

    task = process_sensor_images_task.delay(session_id, saved_paths, model, workers)

    logger.info(f"[sensor_upload] session={session_id} files={len(saved_paths)} task={task.id}")

    return JsonResponse({
        'task_id': task.id,
        'session_id': session_id,
        'count': len(saved_paths),
        'skipped': skipped,
    })


@login_required
def sensor_task_status(request):
    """Poll Celery task status. Returns JSON with state + progress/results."""
    from celery.result import AsyncResult

    task_id = request.GET.get('task_id')
    if not task_id:
        return JsonResponse({'error': 'task_id required'}, status=400)

    r = AsyncResult(task_id)

    if r.state == 'PENDING':
        return JsonResponse({'state': 'PENDING', 'done': 0, 'total': 0, 'percent': 0})

    if r.state == 'PROGRESS':
        meta = r.info or {}
        return JsonResponse({
            'state': 'PROGRESS',
            'done': meta.get('done', 0),
            'total': meta.get('total', 0),
            'percent': meta.get('percent', 0),
            'current_file': meta.get('current_file', ''),
        })

    if r.state == 'SUCCESS':
        return JsonResponse({'state': 'SUCCESS', 'result': r.result})

    return JsonResponse({'state': 'FAILURE', 'error': str(r.result)})


@login_required
def sensor_download_zip(request, session_id):
    """Stream the processed output folder as a ZIP download."""
    output_dir = Path(settings.MEDIA_ROOT) / 'sensor_sessions' / session_id / 'output'
    if not output_dir.exists():
        return HttpResponse('Session not found or already cleaned up.', status=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(output_dir.rglob('*')):
            if f.is_file():
                zf.write(f, f.relative_to(output_dir))
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type='application/zip')
    short_id = session_id[:8]
    response['Content-Disposition'] = f'attachment; filename="sensor_readings_{short_id}.zip"'
    return response


@login_required
def sensor_browse_session(request, session_id):
    """
    Return a JSON list of all output files for a session, grouped by sub-folder.
    Used by the UI to render the file browser panel.
    """
    output_dir = Path(settings.MEDIA_ROOT) / 'sensor_sessions' / session_id / 'output'
    if not output_dir.exists():
        return JsonResponse({'error': 'Session not found'}, status=404)

    folders = {}
    for sub in ALL_SUBFOLDERS:
        sub_dir = output_dir / sub
        if sub_dir.exists():
            files = []
            for f in sorted(sub_dir.iterdir()):
                if f.is_file():
                    rel = f.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
                    files.append({
                        'name': f.name,
                        'url': f'{settings.MEDIA_URL}{rel}',
                        'size_kb': round(f.stat().st_size / 1024, 1),
                    })
            if files:
                folders[sub] = files

    total = sum(len(v) for v in folders.values())
    return JsonResponse({'folders': folders, 'total': total})


@login_required
def sensor_download_subfolder(request, session_id, subfolder):
    """Download a single sub-folder as a ZIP."""
    if subfolder not in ALL_SUBFOLDERS:
        return HttpResponse('Invalid subfolder', status=400)

    sub_dir = Path(settings.MEDIA_ROOT) / 'sensor_sessions' / session_id / 'output' / subfolder
    if not sub_dir.exists():
        return HttpResponse('Folder not found', status=404)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(sub_dir.iterdir()):
            if f.is_file():
                zf.write(f, f.name)
    buf.seek(0)

    response = HttpResponse(buf.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{subfolder}_{session_id[:8]}.zip"'
    return response


@login_required
@csrf_exempt
@require_POST
def sensor_correct(request, session_id):
    """
    Apply a manual correction to a file in NA_Review/.
    Moves the file to the appropriate sorted sub-folder(s).

    POST body (JSON):
        {"filename": "RH65.3_TNa_GPP310.5.jpg", "device_type": "RH_T_GPP",
         "RH": 65.3, "T": 22.1, "GPP": 310.5}
    or for MC:
        {"filename": "MCNa.jpg", "device_type": "MC", "MC": 19.5}
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    filename = data.get('filename', '').strip()
    dtype = data.get('device_type', '')
    if not filename or dtype not in ('MC', 'RH_T_GPP'):
        return JsonResponse({'error': 'filename and device_type required'}, status=400)

    na_dir = Path(settings.MEDIA_ROOT) / 'sensor_sessions' / session_id / 'output' / SUB_NA
    src = na_dir / filename
    if not src.exists():
        return JsonResponse({'error': f'{filename} not found in NA_Review'}, status=404)

    try:
        if dtype == 'MC':
            corrected = {'device_type': 'MC', 'MC': round(float(data['MC']), 1),
                         'RH': None, 'T': None, 'GPP': None}
        else:
            corrected = {
                'device_type': 'RH_T_GPP', 'MC': None,
                'RH':  round(float(data['RH']),  1),
                'T':   round(float(data['T']),   1),
                'GPP': round(float(data['GPP']), 1),
            }
    except (KeyError, ValueError, TypeError) as e:
        return JsonResponse({'error': f'Invalid value: {e}'}, status=400)

    if result_has_na(corrected):
        return JsonResponse({'error': 'Corrected result still has NA values'}, status=400)

    output_root = Path(settings.MEDIA_ROOT) / 'sensor_sessions' / session_id / 'output'
    ext = src.suffix.lower()
    file_map = build_filenames(corrected, ext)
    moved = []

    for sub, fname in file_map.items():
        sub_dir = output_root / sub
        sub_dir.mkdir(parents=True, exist_ok=True)
        dest = safe_dest(sub_dir, fname)
        try:
            import shutil
            shutil.copy2(src, dest)
            moved.append(f'{sub}/{dest.name}')
        except Exception as exc:
            return JsonResponse({'error': f'Copy error: {exc}'}, status=500)

    try:
        src.unlink()
    except Exception as exc:
        logger.warning(f"Could not remove {src} from NA_Review: {exc}")

    return JsonResponse({'success': True, 'moved_to': moved})
