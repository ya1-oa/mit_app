"""
Box Count Calculator views.
"""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from docsAppR.models import Client, Room

from .calculator import (
    CATEGORY_CHOICES,
    CATEGORY_GROUPS,
    ItemCategory,
    Room as CalcRoom,
    Item,
    calculate_job,
    calculate_room,
    items_from_dicts,
)
from .models import BoxCalcSession, BoxCalcRoom, BoxCalcItem
from .room_defaults import get_defaults_for_room

logger = logging.getLogger(__name__)


@login_required
def calculator_home(request):
    """Landing page — client selector."""
    clients = Client.objects.order_by('pOwner').values('id', 'pOwner', 'pAddress', 'claimNumber', 'encircle_claim_id')
    return render(request, 'box_calculator/calculator.html', {
        'clients': list(clients),
        'category_choices': CATEGORY_CHOICES,
        'category_groups': {
            group: [(c.value, c.label) for c in cats]
            for group, cats in CATEGORY_GROUPS.items()
        },
    })


# ---------------------------------------------------------------------------
# API — all return JSON
# ---------------------------------------------------------------------------

@login_required
def api_client_rooms(request, client_id):
    """Return rooms for a client, with any saved session data and Encircle dimensions."""
    client = get_object_or_404(Client, id=client_id)
    rooms = list(Room.objects.filter(client=client).order_by('sequence', 'room_name'))

    # Load latest session if exists (table may not exist yet if migrations haven't run)
    session = None
    saved_rooms: dict[str, list] = {}
    try:
        session = BoxCalcSession.objects.filter(client=client).first()
        if session:
            for bcr in session.rooms.prefetch_related('items').all():
                saved_rooms[bcr.room_name] = [
                    {
                        'category': i.category,
                        'quantity': i.quantity,
                        'compartments': i.compartments,
                        'note': i.note,
                        'ai_suggested': i.ai_suggested,
                    }
                    for i in bcr.items.all()
                ]
    except Exception:
        pass  # tables don't exist yet — degrade gracefully

    # Fetch Encircle floor plan dimensions if available
    encircle_dims: dict[str, dict] = {}
    if client.encircle_claim_id:
        try:
            from docsAppR.encircle_client import EncircleAPIClient, EncircleDataProcessor
            api_ec = EncircleAPIClient()
            raw_fp = api_ec.get_claim_floor_plan(client.encircle_claim_id)
            floor_plan = EncircleDataProcessor.process_floor_plan_data(raw_fp)
            for floor_rooms in floor_plan.values():
                for rname, dims in floor_rooms.items():
                    encircle_dims[rname.lower().strip()] = dims
        except Exception as e:
            logger.warning(f"Could not fetch Encircle floor plan for client {client_id}: {e}")

    room_data = []
    for room in rooms:
        items = saved_rooms.get(room.room_name, get_defaults_for_room(room.room_name))
        dims = encircle_dims.get(room.room_name.lower().strip(), {})
        bb = dims.get('bounding_box', {})
        room_data.append({
            'id': str(room.id),
            'name': room.room_name,
            'items': items,
            'width': bb.get('width'),
            'length': bb.get('height'),
            'area': dims.get('area'),
            'ceiling_height': dims.get('ceiling_height'),
        })

    return JsonResponse({
        'client_name': client.pOwner,
        'encircle_claim_id': client.encircle_claim_id or '',
        'rooms': room_data,
        'saved_rooms': saved_rooms,
        'session_id': session.id if session else None,
    })


@login_required
@require_POST
def api_calculate(request):
    """Calculate box counts for a list of rooms + items (no DB write)."""
    try:
        data = json.loads(request.body)
        rooms_data = data.get('rooms', [])
        if not rooms_data:
            return JsonResponse({'error': 'No rooms provided'}, status=400)

        calc_rooms = []
        for rd in rooms_data:
            items = items_from_dicts(rd.get('items', []))
            calc_rooms.append(CalcRoom(name=rd['name'], items=tuple(items)))

        report = calculate_job(calc_rooms)
        return JsonResponse({'success': True, 'report': report.to_dict()})
    except Exception as e:
        logger.error(f"api_calculate error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_defaults(request):
    """Return default items for a room name."""
    try:
        data = json.loads(request.body)
        room_name = data.get('room_name', '')
        if not room_name:
            return JsonResponse({'error': 'room_name required'}, status=400)
        return JsonResponse({'items': get_defaults_for_room(room_name)})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_ai_analyze(request):
    """AI image analysis for a room."""
    from .ai_analyzer import analyze_room_with_ai
    try:
        data = json.loads(request.body)
        room_name = data.get('room_name', '')
        encircle_claim_id = data.get('encircle_claim_id', '')
        image_urls = data.get('image_urls', [])
        if not room_name:
            return JsonResponse({'error': 'room_name required'}, status=400)
        result = analyze_room_with_ai(
            room_name=room_name,
            encircle_claim_id=encircle_claim_id or None,
            image_urls=image_urls or None,
        )
        return JsonResponse(result)
    except Exception as e:
        logger.error(f"api_ai_analyze error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def api_save_session(request):
    """Persist the current calculator state to the database."""
    try:
        data = json.loads(request.body)
        client_id = data.get('client_id')
        rooms_data = data.get('rooms', [])
        notes = data.get('notes', '')

        if not client_id:
            return JsonResponse({'error': 'client_id required'}, status=400)

        client = get_object_or_404(Client, id=client_id)

        # Upsert session — one session per client (latest wins)
        session, _ = BoxCalcSession.objects.get_or_create(client=client)
        session.notes = notes
        session.save()

        # Clear old rooms and rebuild
        session.rooms.all().delete()

        for order, rd in enumerate(rooms_data):
            room_name = rd.get('name', '')
            if not room_name:
                continue

            # Try to link to the Room model
            orm_room = Room.objects.filter(client=client, room_name=room_name).first()
            bcr = BoxCalcRoom.objects.create(
                session=session,
                room=orm_room,
                room_name=room_name,
                order=order,
            )

            for item_order, item_dict in enumerate(rd.get('items', [])):
                cat = item_dict.get('category', '')
                if cat not in [c.value for c in ItemCategory]:
                    continue
                BoxCalcItem.objects.create(
                    room=bcr,
                    category=cat,
                    quantity=max(1, int(item_dict.get('quantity', 1))),
                    compartments=max(0, int(item_dict.get('compartments', 0))),
                    note=str(item_dict.get('note', ''))[:255],
                    ai_suggested=bool(item_dict.get('ai_suggested', False)),
                    order=item_order,
                )

        # Return the full calculated report
        report = session.get_job_report()
        return JsonResponse({
            'success': True,
            'session_id': session.id,
            'report': report.to_dict(),
        })
    except Exception as e:
        logger.error(f"api_save_session error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def report_view(request, session_id):
    """Printable report for a saved session."""
    session = get_object_or_404(BoxCalcSession, id=session_id)
    report = session.get_job_report()
    return render(request, 'box_calculator/report.html', {
        'session': session,
        'report': report,
        'report_dict': report.to_dict(),
    })


# ---------------------------------------------------------------------------
# PPR (Pre-Packout Report) — AI image-based views
# ---------------------------------------------------------------------------

@login_required
def cps_home(request):
    """CPS home — multi-claim generate + bulk export."""
    from .models import BoxCalcCPSSession
    sessions_by_client = {
        s.client_id: s
        for s in BoxCalcCPSSession.unscoped
            .select_related('client')
            .prefetch_related('rooms', 'saved_reports')
    }
    rows = [
        {'client': c, 'session': sessions_by_client.get(c.id)}
        for c in Client.objects.order_by('pOwner')
    ]
    return render(request, 'box_calculator/cps.html', {'rows': rows})


@login_required
def cps_session(request, client_id):
    """Load or create a PPR session for a client; return session JSON."""
    from .models import BoxCalcCPSSession
    client = get_object_or_404(Client, id=client_id)

    # Pull 300-series rooms from Encircle/docsAppR (room_name starts with 3xx).
    # Prefer pre-generated numbered entries (is_encircle_entry=True) so the
    # 301/302/… prefix is present.  Fall back to all rooms for legacy clients.
    numbered_qs = Room.objects.filter(client=client, is_encircle_entry=True).order_by('sequence')
    rooms_qs = numbered_qs if numbered_qs.exists() else Room.objects.filter(client=client).order_by('sequence', 'room_name')
    ppr_rooms_qs = [r for r in rooms_qs if _is_packout_room(r.room_name)]

    session = BoxCalcCPSSession.unscoped.filter(client=client).first()
    session_data = None
    if session:
        session_data = {
            'id': session.id,
            'notes': session.notes,
            'rooms': [r.to_dict() for r in session.rooms.order_by('order', 'room_name')],
        }

    return JsonResponse({
        'client_name': client.pOwner,
        'claim_number': client.claimNumber or '',
        'encircle_claim_id': client.encircle_claim_id or '',
        'available_rooms': [{'id': r.id, 'name': r.room_name} for r in ppr_rooms_qs],
        'session': session_data,
    })


def _is_packout_room(room_name: str) -> bool:
    """True if the room number prefix indicates a 300-series packout room."""
    import re
    m = re.match(r'^(\d+)', room_name.strip())
    if not m:
        return True  # un-numbered rooms always included
    num = int(m.group(1))
    return 300 <= num < 400


@login_required
@require_POST
def cps_upload_room(request):
    """
    Accept image uploads for a single room and dispatch the AI analysis task.

    POST: multipart/form-data
        client_id   — int
        room_name   — str  e.g. "301 Living Room DN"
        images      — file[] (JPEG/PNG/WEBP etc.)
        model       — optional Claude model ID

    Returns: {"task_id": str, "room_name": str, "session_id": int}
    """
    from .models import BoxCalcCPSSession, BoxCalcCPSRoom
    from .tasks import process_cps_room_task
    import uuid, pathlib

    client_id = request.POST.get('client_id')
    room_name = request.POST.get('room_name', '').strip()
    model = request.POST.get('model', 'claude-haiku-4-5-20251001')
    files = request.FILES.getlist('images')

    if not client_id:
        return JsonResponse({'error': 'client_id required'}, status=400)
    if not room_name:
        return JsonResponse({'error': 'room_name required'}, status=400)
    if not files:
        return JsonResponse({'error': 'At least one image required'}, status=400)

    client = get_object_or_404(Client, id=client_id)
    session, _ = BoxCalcCPSSession.unscoped.get_or_create(
        client=client,
        defaults={'tenant': getattr(request, 'tenant', None)},
    )

    # Save uploaded files to temp storage
    upload_dir = pathlib.Path('/tmp') / f'cps_{session.id}_{uuid.uuid4().hex[:8]}'
    upload_dir.mkdir(parents=True, exist_ok=True)

    ALLOWED_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff', '.tif'}
    saved_paths = []
    for f in files[:5]:
        ext = pathlib.Path(f.name).suffix.lower()
        if ext not in ALLOWED_EXTS:
            continue
        dest = upload_dir / f'{uuid.uuid4().hex}{ext}'
        with open(dest, 'wb') as out:
            for chunk in f.chunks():
                out.write(chunk)
        saved_paths.append(str(dest))

    if not saved_paths:
        return JsonResponse({'error': 'No supported image files in upload'}, status=400)

    # Mark room as pending and dispatch task
    ppr_room, _ = BoxCalcCPSRoom.objects.get_or_create(session=session, room_name=room_name)
    ppr_room.status = 'pending'
    ppr_room.save(update_fields=['status'])

    task = process_cps_room_task.delay(
        session_id=session.id,
        room_name=room_name,
        image_paths=saved_paths,
        model=model,
    )

    ppr_room.celery_task_id = task.id
    ppr_room.save(update_fields=['celery_task_id'])

    return JsonResponse({
        'task_id': task.id,
        'room_name': room_name,
        'session_id': session.id,
    })


@login_required
def cps_task_status(request, task_id):
    """Poll status of a PPR room analysis task."""
    from celery.result import AsyncResult
    from .models import BoxCalcCPSRoom

    result = AsyncResult(task_id)
    state = result.state

    room = BoxCalcCPSRoom.objects.filter(celery_task_id=task_id).first()
    room_data = room.to_dict() if room else None

    if state == 'SUCCESS':
        return JsonResponse({'state': 'SUCCESS', 'room': room_data})
    elif state == 'FAILURE':
        return JsonResponse({'state': 'FAILURE', 'error': str(result.result), 'room': room_data})
    elif state == 'PROGRESS':
        return JsonResponse({'state': 'PROGRESS', 'meta': result.info, 'room': room_data})
    else:
        return JsonResponse({'state': state, 'room': room_data})


@login_required
def cps_report(request, session_id):
    """Render the PPR report page for a completed session."""
    from .models import BoxCalcCPSSession
    from .cps_analyzer import CPS_COLUMNS, CPS_COLUMN_LABELS
    session = get_object_or_404(BoxCalcCPSSession.unscoped, id=session_id)
    primary_rooms   = session.rooms.exclude(room_name__startswith='[OVERVIEW]').order_by('order', 'room_name')
    overview_rooms  = session.rooms.filter(room_name__startswith='[OVERVIEW]').order_by('order', 'room_name')
    saved_reports   = session.saved_reports.order_by('-created_at')
    return render(request, 'box_calculator/cps_report.html', {
        'session': session,
        'primary_rooms':  primary_rooms,
        'overview_rooms': overview_rooms,
        'cps_columns': CPS_COLUMNS,
        'cps_column_labels': CPS_COLUMN_LABELS,
        'grand_counts':    session.grand_counts,
        'grand_total':     session.grand_total,
        'overview_counts': session.overview_counts,
        'overview_total':  session.overview_total,
        'saved_reports':   saved_reports,
    })


@login_required
def cps_export_pdf(request, session_id):
    """Generate, save, and stream the CPS box count report as PDF."""
    from .models import BoxCalcCPSSession, BoxCalcCPSReport
    from .pdf_builder import build_cps_pdf
    session = get_object_or_404(BoxCalcCPSSession.unscoped, id=session_id)
    pdf_bytes = build_cps_pdf(session)
    safe_name = session.client.pOwner.replace(' ', '_').replace('/', '-')
    filename = f"CPS_Box_Count_{safe_name}.pdf"
    BoxCalcCPSReport.objects.create(
        session=session,
        format=BoxCalcCPSReport.FORMAT_PDF,
        filename=filename,
        file_data=pdf_bytes,
        file_size=len(pdf_bytes),
        created_by=request.user,
    )
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def cps_export_excel(request, session_id):
    """Generate, save, and stream the PPR Excel report (.xlsx)."""
    from .models import BoxCalcCPSSession, BoxCalcCPSReport
    from .excel_builder import build_cps_excel
    session = get_object_or_404(BoxCalcCPSSession.unscoped, id=session_id)
    xlsx_bytes = build_cps_excel(session)
    safe_name = session.client.pOwner.replace(' ', '_').replace('/', '-')
    filename = f"PPR_Box_Count_{safe_name}.xlsx"
    BoxCalcCPSReport.objects.create(
        session=session,
        format=BoxCalcCPSReport.FORMAT_EXCEL,
        filename=filename,
        file_data=xlsx_bytes,
        file_size=len(xlsx_bytes),
        created_by=request.user,
    )
    response = HttpResponse(
        xlsx_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def cps_saved_report(request, report_id):
    """Serve a previously saved CPS report (PDF or Excel) from the database."""
    from .models import BoxCalcCPSReport
    report = get_object_or_404(BoxCalcCPSReport, id=report_id)
    response = HttpResponse(bytes(report.file_data), content_type=report.mime_type)
    response['Content-Disposition'] = f'attachment; filename="{report.filename}"'
    return response


@login_required
@require_POST
def cps_bulk_export(request):
    """
    Generate a ZIP of PDF or Excel reports for multiple CPS sessions.
    POST JSON: {"session_ids": [1, 2, 3], "format": "pdf"|"excel"}
    Saves each report to BoxCalcCPSReport and streams a ZIP back.
    """
    import io
    import zipfile
    from .models import BoxCalcCPSSession, BoxCalcCPSReport

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    session_ids = body.get('session_ids', [])
    fmt = body.get('format', 'pdf').lower()
    if fmt not in ('pdf', 'excel'):
        return JsonResponse({'error': 'format must be pdf or excel'}, status=400)
    if not session_ids:
        return JsonResponse({'error': 'No sessions selected'}, status=400)

    sessions = list(BoxCalcCPSSession.unscoped.filter(id__in=session_ids).select_related('client'))
    if not sessions:
        return JsonResponse({'error': 'No matching sessions found'}, status=404)

    if fmt == 'pdf':
        from .pdf_builder import build_cps_pdf
    else:
        from .excel_builder import build_cps_excel

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        seen_names: dict[str, int] = {}
        for session in sessions:
            safe_name = session.client.pOwner.replace(' ', '_').replace('/', '-')
            if fmt == 'pdf':
                file_bytes = build_cps_pdf(session)
                base_filename = f"CPS_Box_Count_{safe_name}.pdf"
                report_format = BoxCalcCPSReport.FORMAT_PDF
            else:
                file_bytes = build_cps_excel(session)
                base_filename = f"PPR_Box_Count_{safe_name}.xlsx"
                report_format = BoxCalcCPSReport.FORMAT_EXCEL

            # Deduplicate filenames within the ZIP
            if base_filename in seen_names:
                seen_names[base_filename] += 1
                name, ext = base_filename.rsplit('.', 1)
                zip_entry = f"{name}_{seen_names[base_filename]}.{ext}"
            else:
                seen_names[base_filename] = 0
                zip_entry = base_filename

            zf.writestr(zip_entry, file_bytes)
            BoxCalcCPSReport.objects.create(
                session=session,
                format=report_format,
                filename=base_filename,
                file_data=file_bytes,
                file_size=len(file_bytes),
                created_by=request.user,
            )

    zip_bytes = zip_buf.getvalue()
    response = HttpResponse(zip_bytes, content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="CPS_Reports.zip"'
    return response


@login_required
@require_POST
def cps_update_room(request, room_id):
    """Manually edit a room's PPR counts (override AI estimates)."""
    from .models import BoxCalcCPSRoom
    from .cps_analyzer import CPS_COLUMNS
    ppr_room = get_object_or_404(BoxCalcCPSRoom, id=room_id)
    try:
        data = json.loads(request.body)
        for col in CPS_COLUMNS:
            if col in data:
                setattr(ppr_room, col, max(0, int(data[col])))
        ppr_room.save()
        return JsonResponse({'success': True, 'room': ppr_room.to_dict()})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def cps_delete_room(request, room_id):
    """Remove a room from the PPR session."""
    from .models import BoxCalcCPSRoom
    ppr_room = get_object_or_404(BoxCalcCPSRoom, id=room_id)
    ppr_room.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def api_auto_from_encircle(request):
    """
    Kick off automatic Encircle photo download + CPS analysis for all 300-series rooms.
    POST body: JSON {"client_id": int}
    Returns: {"success": true, "session_id": int, "rooms": [{"room_name": str, "task_id": str}]}
    """
    import re
    from .models import BoxCalcCPSSession, BoxCalcCPSRoom
    from .tasks import process_cps_room_task

    try:
        data = json.loads(request.body)
        client_id = data.get('client_id')
    except (json.JSONDecodeError, KeyError):
        return JsonResponse({'error': 'Invalid JSON body'}, status=400)

    if not client_id:
        return JsonResponse({'error': 'client_id required'}, status=400)

    client = get_object_or_404(Client, id=client_id)

    if not client.encircle_claim_id:
        return JsonResponse({'error': 'This client has no Encircle claim ID'}, status=400)

    # Fetch Encircle structure + all rooms
    try:
        from docsAppR.encircle_client import EncircleAPIClient
        api = EncircleAPIClient()
        structures = api.get_claim_structures(client.encircle_claim_id)
        struct_list = structures.get('list') if isinstance(structures, dict) else None
        if not struct_list:
            return JsonResponse({'error': 'No structures found for this claim in Encircle'}, status=400)
        structure_id = str(struct_list[0]['id'])
        all_rooms = api.get_all_structure_rooms(client.encircle_claim_id, structure_id)
    except Exception as e:
        logger.error("Encircle fetch error for client %s: %s", client_id, e, exc_info=True)
        return JsonResponse({'error': f'Encircle API error: {e}'}, status=500)

    # Collect 300-series (packout) and 100-series (overview) rooms — both deduplicated
    rooms_300, seen_300 = [], set()
    rooms_100, seen_100 = [], set()
    for room in all_rooms:
        label = (room.get('label') or room.get('name') or '').strip()
        m = re.match(r'^(\d+)', label)
        if not m:
            continue
        num = int(m.group(1))
        if 300 <= num < 400 and label not in seen_300:
            seen_300.add(label)
            rooms_300.append({'name': label, 'num': m.group(1)})
        elif 100 <= num < 200 and label not in seen_100:
            seen_100.add(label)
            rooms_100.append({'name': label, 'num': m.group(1)})

    # Primary: 300-series if present, else fall back to 100-series overview shots
    if rooms_300:
        primary_rooms = rooms_300
        supplemental_overview = rooms_100  # cross-check with wide-angle shots
    elif rooms_100:
        primary_rooms = rooms_100          # no 300-series — use overviews as primary
        supplemental_overview = []
    else:
        return JsonResponse({'error': 'No 300-series or 100-series packout rooms found in this claim'}, status=400)

    # Fetch ALL claim media in one call — same approach as ZipMediaDownloader/claim_images app.
    # The room-level /rooms/{id}/media endpoint returns 404 for rooms without directly
    # attached media; claim-level media is the correct source with room labels as metadata.
    try:
        all_claim_media = api.get_all_claim_media(client.encircle_claim_id)
    except Exception as e:
        logger.error("Encircle media fetch error for client %s: %s", client_id, e, exc_info=True)
        return JsonResponse({'error': f'Encircle media API error: {e}'}, status=500)

    # Group download_uris by 3-digit room number prefix (same label-matching logic
    # as ZipMediaDownloader._should_download: check item['labels'] for the room name).
    media_by_room_num: dict[str, list[str]] = {}
    for item in all_claim_media:
        ct = (item.get('content_type') or '').lower().split(';')[0].strip()
        if not ct.startswith('image/'):
            continue
        url = item.get('download_uri')
        if not url:
            continue
        for label in item.get('labels', []):
            m = re.match(r'^(\d+)', (label or '').strip())
            if m:
                media_by_room_num.setdefault(m.group(1), []).append(url)
                break

    logger.info("CPS Encircle media — claim=%s total_images=%d rooms_with_media=%s",
                client.encircle_claim_id, len(all_claim_media),
                {k: len(v) for k, v in media_by_room_num.items()})

    # Filter supplemental overview rooms to only those that have actual photos in Encircle
    supplemental_overview = [r for r in supplemental_overview if media_by_room_num.get(r['num'])]

    # Create/upsert session (unscoped — TenantScopedManager returns empty qs in non-request contexts)
    try:
        session = BoxCalcCPSSession.unscoped.filter(client=client).order_by('-updated_at').first()
        if session is None:
            session = BoxCalcCPSSession.unscoped.create(
                client=client,
                tenant=getattr(request, 'tenant', None),
            )
        BoxCalcCPSSession.unscoped.filter(client=client).exclude(pk=session.pk).delete()
        session.rooms.all().delete()
    except Exception as e:
        logger.error("CPS session DB error for client %s: %s", client_id, e, exc_info=True)
        return JsonResponse({'error': f'Database error: {e}'}, status=500)

    # Create room rows and dispatch process_cps_room_task with photo URLs directly.
    # process_cps_room_task already handles http(s) URLs in _image_to_base64.
    _ROOM_DEFAULTS = lambda order: {
        'order': order,
        'status': 'pending',
        'celery_task_id': '',
        'small': 0, 'medium': 0, 'large': 0, 'box_wrapped': 0,
        'picture_mirror': 0, 'plant_vase': 0, 'tv': 0,
        'wardrobe': 0, 'mattress': 0, 'dish_pack': 0,
        'glass_pack': 0, 'boots_pans': 0,
        'confidence': '', 'ai_notes': '', 'images_count': 0,
    }
    room_tasks = []
    try:
        # Primary rooms (300-series, or 100-series when no 300s)
        for order, room_info in enumerate(primary_rooms):
            photo_urls = media_by_room_num.get(room_info['num'], [])[:5]
            cps_room, _ = BoxCalcCPSRoom.objects.update_or_create(
                session=session,
                room_name=room_info['name'],
                defaults=_ROOM_DEFAULTS(order),
            )
            task = process_cps_room_task.delay(
                session_id=session.id,
                room_name=room_info['name'],
                image_paths=photo_urls,
            )
            cps_room.celery_task_id = task.id
            cps_room.save(update_fields=['celery_task_id'])
            room_tasks.append({'room_name': room_info['name'], 'task_id': task.id})

        # Supplemental overview rooms (100-series when 300-series are primary).
        # Claude uses the wide-angle overview prompt to catch items missed in individual shots.
        for i, room_info in enumerate(supplemental_overview):
            photo_urls = media_by_room_num.get(room_info['num'], [])[:5]
            ov_name = f"[OVERVIEW] {room_info['name']}"
            cps_room, _ = BoxCalcCPSRoom.objects.update_or_create(
                session=session,
                room_name=ov_name,
                defaults=_ROOM_DEFAULTS(len(primary_rooms) + i),
            )
            task = process_cps_room_task.delay(
                session_id=session.id,
                room_name=ov_name,
                image_paths=photo_urls,
                is_overview=True,
            )
            cps_room.celery_task_id = task.id
            cps_room.save(update_fields=['celery_task_id'])
            room_tasks.append({'room_name': ov_name, 'task_id': task.id})

    except Exception as e:
        logger.error("Error dispatching CPS tasks for client %s: %s", client_id, e, exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({
        'success': True,
        'session_id': session.id,
        'rooms': room_tasks,
    })


@login_required
@require_POST
def api_pdf_to_cps_session(request):
    """
    Accept an uploaded box count report PDF, run Claude master-estimator analysis,
    persist results as a BoxCalcCPSSession + BoxCalcCPSRoom records, and return
    the session ID so the caller can redirect to the existing CPS report/edit page.

    POST: multipart/form-data
        file       — PDF (≤20 MB)
        client_id  — int (required)
    """
    from .ai_analyzer import analyze_pdf_report
    from .models import BoxCalcCPSSession, BoxCalcCPSRoom
    from .cps_analyzer import CPS_COLUMNS

    pdf_file  = request.FILES.get('file')
    client_id = request.POST.get('client_id')

    if not pdf_file:
        return JsonResponse({'error': 'No file uploaded'}, status=400)
    if not pdf_file.name.lower().endswith('.pdf'):
        return JsonResponse({'error': 'File must be a PDF'}, status=400)
    if pdf_file.size > 20 * 1024 * 1024:
        return JsonResponse({'error': 'PDF must be under 20 MB'}, status=400)
    if not client_id:
        return JsonResponse({'error': 'client_id required'}, status=400)

    client = get_object_or_404(Client, id=client_id)

    # Build context string for the prompt
    parts = [client.pOwner]
    if client.claimNumber:
        parts.append(f"Claim #{client.claimNumber}")
    if client.pAddress:
        parts.append(client.pAddress)
    client_context = ' — '.join(parts)

    try:
        pdf_bytes = pdf_file.read()
        result = analyze_pdf_report(pdf_bytes, client_context=client_context)
    except Exception as e:
        logger.error(f"api_pdf_to_cps_session analysis error: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

    if not result.get('success'):
        return JsonResponse({'error': result.get('error', 'Analysis failed')}, status=500)

    # Persist to CPS session — one session per client (upsert)
    session, _ = BoxCalcCPSSession.unscoped.get_or_create(
        client=client,
        defaults={'tenant': getattr(request, 'tenant', None)},
    )
    session.notes = result.get('estimator_notes', '')
    session.save(update_fields=['notes', 'updated_at'])

    # Replace all rooms with fresh AI estimates
    session.rooms.all().delete()

    for order, room_data in enumerate(result.get('rooms', [])):
        room_name = room_data.get('name', f'Room {order + 1}')
        kwargs = {col: max(0, int(room_data.get(col, 0) or 0)) for col in CPS_COLUMNS}
        BoxCalcCPSRoom.objects.create(
            session=session,
            room_name=room_name,
            order=order,
            status='complete',
            confidence='high',
            ai_notes=room_data.get('ai_notes', ''),
            images_count=0,
            **kwargs,
        )

    return JsonResponse({'success': True, 'session_id': session.id})
