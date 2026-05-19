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
    """Return rooms for a client, with any saved session data."""
    client = get_object_or_404(Client, id=client_id)
    rooms = Room.objects.filter(client=client).order_by('sequence', 'room_name')

    # Load latest session if exists
    session = BoxCalcSession.objects.filter(client=client).first()
    saved_rooms: dict[str, list] = {}
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

    room_data = []
    for room in rooms:
        items = saved_rooms.get(room.room_name, get_defaults_for_room(room.room_name))
        room_data.append({
            'id': str(room.id),
            'name': room.room_name,
            'items': items,
        })

    return JsonResponse({
        'client_name': client.pOwner,
        'encircle_claim_id': client.encircle_claim_id or '',
        'rooms': room_data,
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
