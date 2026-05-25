# docsAppR/onedrive_views.py
# Views for OneDrive-integrated claim creation workflow

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.db import transaction
from django.core.paginator import Paginator
from django.utils import timezone
import json
import logging

from .models import Client, Room, WorkType, RoomWorkTypeValue, ChecklistItem
# OneDrive models removed: OneDriveFolder, OneDriveFile, SyncLog
from .forms import OneDriveClientForm, RoomSelectionForm, BulkWorkTypeForm
# UPDATED: Use server-side tasks instead of OneDrive tasks
from .tasks import create_server_folder_structure_task, copy_templates_to_server_task, push_claim_to_encircle_task, push_encircle_subclaim_task, push_rooms_to_encircle_task, migrate_encircle_rooms_task, generate_and_email_labels_task

# Configure logging
logger = logging.getLogger(__name__)


# ==================== Claim List View ====================

@login_required
def claim_list(request):
    """
    Claims list — sourced from local Django Client records.
    Encircle data is available on the detail page; the list page stays fast
    and reliable by querying the local DB only.
    """
    from django.db.models import Q

    search  = request.GET.get('search', '').strip()
    sort_by = request.GET.get('sort', '-updated_at')

    clients = Client.objects.all()

    # ── Search ─────────────────────────────────────────────────────
    if search:
        clients = clients.filter(
            Q(pOwner__icontains=search) |
            Q(pAddress__icontains=search) |
            Q(claimNumber__icontains=search) |
            Q(insuranceCo_Name__icontains=search) |
            Q(causeOfLoss__icontains=search)
        )

    # ── Sort ───────────────────────────────────────────────────────
    sort_map = {
        'name':       'pOwner',
        '-name':      '-pOwner',
        'date':       'dateOfLoss',
        '-date':      '-dateOfLoss',
        'updated_at': 'updated_at',
        'created_at': 'created_at',
        '-created_at': '-created_at',
    }
    clients = clients.order_by(sort_map.get(sort_by, '-updated_at'))

    # ── Paginate ───────────────────────────────────────────────────
    paginator = Paginator(clients, 30)
    page_obj  = paginator.get_page(request.GET.get('page'))

    return render(request, 'docsAppR/claim_list.html', {
        'page_obj':    page_obj,
        'search':      search,
        'sort_by':     sort_by,
        'total_count': paginator.count,
    })


# ==================== Claim Detail View ====================

@login_required
def claim_detail(request, claim_id):
    """View details of a specific claim - Server-based file management"""

    client = get_object_or_404(Client, id=claim_id)
    rooms = Room.objects.filter(client=client).prefetch_related('work_type_values__work_type').order_by('sequence')

    # Get server-based claim files instead of OneDrive files
    from .models import ClaimFile
    claim_files = ClaimFile.objects.filter(client=client, is_active=True).order_by('-modified_at')

    # Get folder path information
    server_folder_path = client.get_server_folder_path()

    # Ensure checklist items exist for this client
    from .signals import create_checklist_items_for_client
    create_checklist_items_for_client(client)
    client.update_completion_stats()

    # Get checklist items grouped by category
    checklist_items = ChecklistItem.objects.filter(client=client).order_by('document_category', 'document_type')

    # Group checklist items by category
    checklist_by_category = {}
    for item in checklist_items:
        category = item.document_category
        if category not in checklist_by_category:
            checklist_by_category[category] = {
                'items': [],
                'total': 0,
                'completed': 0
            }
        checklist_by_category[category]['items'].append(item)
        checklist_by_category[category]['total'] += 1
        if item.is_completed:
            checklist_by_category[category]['completed'] += 1

    # Calculate percentages for each category
    for category in checklist_by_category:
        total = checklist_by_category[category]['total']
        completed = checklist_by_category[category]['completed']
        checklist_by_category[category]['percent'] = round((completed / total) * 100) if total > 0 else 0

    context = {
        'client': client,
        'rooms': rooms,
        'claim_files': claim_files,
        'server_folder_path': server_folder_path,
        'folder_created_at': client.folder_created_at,
        'last_file_modified': client.last_file_modified,
        'last_modified_by': client.last_modified_by,
        'checklist_by_category': checklist_by_category,
        'checklist_items': checklist_items,
    }

    return render(request, 'docsAppR/claim_detail.html', context)


# ==================== Step 1: Client Information ====================

@login_required
def create_claim_step1(request):
    """Step 1: Enter client information"""

    # Check if there's a client in session (editing)
    client_id = request.session.get('creating_claim_id')
    client = None

    if client_id:
        try:
            client = Client.objects.get(id=client_id)
        except Client.DoesNotExist:
            request.session.pop('creating_claim_id', None)

    if request.method == 'POST':
        form = OneDriveClientForm(request.POST, instance=client)

        if form.is_valid():
            client = form.save(commit=False)
            # OneDrive sync status removed
            client.save()

            # Store client ID in session
            request.session['creating_claim_id'] = client.id

            messages.success(request, 'Client information saved.')
            return redirect('create_claim_step2')
    else:
        form = OneDriveClientForm(instance=client)

    context = {
        'form': form,
        'client': client,
        'step': 1,
    }

    return render(request, 'docsAppR/create_claim_step1_full.html', context)


# ==================== Step 2: Rooms Configuration ====================

@login_required
def create_claim_step2(request):
    """Step 2: Configure rooms and work types"""

    # Get client from session
    client_id = request.session.get('creating_claim_id')

    if not client_id:
        messages.error(request, 'Please complete Step 1 first.')
        return redirect('create_claim_step1')

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        request.session.pop('creating_claim_id', None)
        messages.error(request, 'Client not found. Please start over.')
        return redirect('create_claim_step1')

    # Get all work types for the template
    work_types = WorkType.objects.filter(is_active=True).order_by('display_order')

    # Forms
    selection_form = RoomSelectionForm(exclude_client_id=client.id)
    bulk_form = BulkWorkTypeForm()

    # Work types for the template selection panel (100–700 only)
    basic_work_types = [(wt.work_type_id, wt.name) for wt in work_types
                        if 100 <= wt.work_type_id <= 700]

    context = {
        'client': client,
        'work_types': work_types,
        'selection_form': selection_form,
        'bulk_form': bulk_form,
        'step': 2,
        'work_types_for_template': basic_work_types,
    }

    return render(request, 'docsAppR/create_claim_step2.html', context)


@login_required
@require_POST
def load_rooms_from_claim(request):
    """AJAX endpoint to load rooms from another claim"""

    source_claim_id = request.POST.get('source_claim_id')

    if not source_claim_id:
        return JsonResponse({'success': False, 'error': 'No source claim selected'})

    try:
        source_client = Client.objects.get(id=source_claim_id)
        # Only load base rooms (is_encircle_entry=False); skip generated numbered entries
        source_rooms = (
            Room.objects
            .filter(client=source_client, is_encircle_entry=False)
            .prefetch_related('work_type_values__work_type')
        )

        rooms_data = []
        for room in source_rooms:
            work_types = {}
            for wt_value in room.work_type_values.all():
                work_types[wt_value.work_type.work_type_id] = wt_value.value_type

            rooms_data.append({
                'sequence': room.sequence,
                'name': room.room_name,
                'work_types': work_types
            })

        return JsonResponse({
            'success': True,
            'rooms': rooms_data,
            'message': f'Loaded {len(rooms_data)} rooms from {source_client.pOwner}'
        })

    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Source claim not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def save_rooms(request):
    """
    AJAX endpoint to save rooms and proceed to step 3.
    Rooms tagged claim_type='mit' are saved to a separate "{pOwner} MIT" sub-claim.
    Rooms tagged claim_type='rht' are saved to a separate "{pOwner} RHT" sub-claim.
    Normal rooms go to the primary client claim.
    """
    client_id = request.session.get('creating_claim_id')

    if not client_id:
        return JsonResponse({'success': False, 'error': 'No active claim creation session'})

    try:
        client = Client.objects.get(id=client_id)
        rooms_data = json.loads(request.POST.get('rooms_data', '[]'))

        # Template + work-type selections (now submitted from Step 2)
        selected_templates  = json.loads(request.POST.get('selected_templates', '[]'))
        selected_work_types = json.loads(request.POST.get('selected_work_types', '[]'))

        # ── Separate sub-template types from primary templates ─────────────────
        # 8000s/9000s/siding go to sub-claims; primary gets the rest.
        _SUB_TEMPLATES = {'readings_8000', 'readings_9000', 'siding_10000'}
        primary_templates = [t for t in selected_templates if t not in _SUB_TEMPLATES]
        # Work types: 700 (HMR) gets its own sub-claim handled in Step 3;
        # exclude it from the primary entry generation here.
        _wt_ints = [int(w) for w in selected_work_types if str(w).strip().isdigit()]
        primary_work_types = [w for w in selected_work_types
                              if str(w).strip().isdigit() and int(w) != 700]

        # Fallback: if user didn't pick any primary template, default to basic
        if not primary_templates:
            primary_templates = ['basic']

        if not rooms_data and 'siding_10000' not in selected_templates:
            return JsonResponse({'success': False, 'error': 'No rooms provided'})

        # Split rooms by claim type
        normal_rooms = [r for r in rooms_data if r.get('claim_type', 'normal') == 'normal']
        mit_rooms    = [r for r in rooms_data if r.get('claim_type') == 'mit']
        rht_rooms    = [r for r in rooms_data if r.get('claim_type') == 'rht']

        # Store template choices in session so Step 3 can reference them if needed
        request.session['primary_templates']   = primary_templates
        request.session['primary_work_types']  = primary_work_types
        request.session['selected_templates']  = selected_templates
        request.session.modified = True

        all_work_types = WorkType.objects.filter(is_active=True)

        def _create_rooms_for_client(
            target_client,
            room_list,
            selected_templates=None,
            selected_work_types=None,
            skip_preamble=False,
        ):
            """
            Create Room records for a client.

            Phase 1 — base rooms (is_encircle_entry=False):
              Plain room names + RoomWorkTypeValue LOS configs.  Used for
              editing and for copying rooms between claims.

            Phase 2 — Encircle entries (is_encircle_entry=True):
              Fully-formatted numbered strings generated by build_room_entries().
              These match exactly what gets pushed to Encircle and are used for
              CPS/PPR filtering and for direct Encircle push without re-computing.

            For template-only room series (siding_10000, 8000s, 9000s) that
            contain no base rooms, only Phase 2 records are created.
            """
            from .tasks import build_room_entries as _build

            Room.objects.filter(client=target_client).delete()

            # ── Phase 1: base rooms ───────────────────────────────────────────
            room_names = []
            configs = {}
            for rd in room_list:
                name = rd.get('name', '').strip()
                if not name:
                    continue
                room_names.append(name)
                room = Room.objects.create(
                    client=target_client,
                    room_name=name,
                    sequence=rd['sequence'],
                    is_encircle_entry=False,
                )
                wt_data = rd.get('work_types', {})
                master_value = wt_data.get('100', 'NA')
                for wt in all_work_types:
                    wt_id_str = str(wt.work_type_id)
                    value = wt_data.get(wt_id_str, master_value if wt.work_type_id != 100 else 'NA')
                    RoomWorkTypeValue.objects.create(room=room, work_type=wt, value_type=value)
                wt_ints = {int(k): v for k, v in wt_data.items() if str(k).strip().isdigit()}
                configs[name] = wt_ints

            # ── Phase 2: numbered Encircle entries ────────────────────────────
            if not selected_templates:
                selected_templates = ['basic'] if room_names else []
            if selected_work_types:
                selected_work_types = [int(wt) for wt in selected_work_types
                                       if str(wt).strip().isdigit()]

            all_entries = _build(
                room_names,
                configs,
                selected_templates,
                selected_work_types or None,
                skip_preamble,
            )
            for seq, entry in enumerate(all_entries):
                Room.objects.create(
                    client=target_client,
                    room_name=entry,
                    sequence=seq,
                    is_encircle_entry=True,
                )

        def _clone_client(base_client, name_suffix):
            """Create a copy of base_client with pOwner suffixed."""
            return Client.objects.create(
                pOwner=f"{base_client.pOwner} {name_suffix}",
                pAddress=base_client.pAddress,
                pCityStateZip=base_client.pCityStateZip,
                cEmail=base_client.cEmail,
                cPhone=base_client.cPhone,
                claimNumber=base_client.claimNumber,
                policyNumber=base_client.policyNumber,
                causeOfLoss=base_client.causeOfLoss,
                dateOfLoss=base_client.dateOfLoss,
                insuranceCo_Name=base_client.insuranceCo_Name,
                deskAdjusterDA=base_client.deskAdjusterDA,
                DAPhone=base_client.DAPhone,
                DAEmail=base_client.DAEmail,
                fieldAdjusterName=base_client.fieldAdjusterName,
                phoneFieldAdj=base_client.phoneFieldAdj,
                fieldAdjEmail=base_client.fieldAdjEmail,
            )

        sub_claims_created = []

        mit_client_obj = None
        rht_client_obj = None

        with transaction.atomic():
            # Save normal rooms to the primary claim with selected templates
            _create_rooms_for_client(
                client, normal_rooms,
                selected_templates=primary_templates,
                selected_work_types=primary_work_types or None,
            )

            # MIT sub-claim — always uses 8000s MC Day Readings
            if mit_rooms or 'readings_8000' in selected_templates:
                mit_client_obj = _clone_client(client, 'MIT')
                _create_rooms_for_client(
                    mit_client_obj,
                    mit_rooms or normal_rooms,   # fall back to primary rooms if none tagged
                    selected_templates=['readings_8000'],
                )
                sub_claims_created.append(f"{mit_client_obj.pOwner} ({len(mit_rooms or normal_rooms)} rooms)")
            else:
                request.session.pop('mit_claim_id', None)

            # RHT sub-claim — always uses 9000s Dry Chamber Readings
            if rht_rooms or 'readings_9000' in selected_templates:
                rht_client_obj = _clone_client(client, 'RHT')
                _create_rooms_for_client(
                    rht_client_obj,
                    rht_rooms or normal_rooms,
                    selected_templates=['readings_9000'],
                )
                sub_claims_created.append(f"{rht_client_obj.pOwner} ({len(rht_rooms or normal_rooms)} rooms)")
            else:
                request.session.pop('rht_claim_id', None)

        # Store sub-claim IDs in session AFTER the transaction commits so the
        # DB rows are guaranteed to exist when Step 3 looks them up.
        # Also force session.modified so Django persists the change.
        if mit_client_obj:
            request.session['mit_claim_id'] = str(mit_client_obj.id)
        if rht_client_obj:
            request.session['rht_claim_id'] = str(rht_client_obj.id)
        request.session.modified = True

        msg = f'Saved {len(normal_rooms)} room(s) to primary claim.'
        if sub_claims_created:
            msg += ' Sub-claims created: ' + ', '.join(sub_claims_created) + '.'

        return JsonResponse({
            'success': True,
            'message': msg,
            'sub_claims': sub_claims_created,
        })

    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Client not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ==================== Step 3: Review & Create ====================

@login_required
def create_claim_step3(request):
    """Step 3: Review and create OneDrive structure"""

    # Get client from session
    client_id = request.session.get('creating_claim_id')

    if not client_id:
        messages.error(request, 'Please complete Step 1 first.')
        return redirect('create_claim_step1')

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        request.session.pop('creating_claim_id', None)
        messages.error(request, 'Client not found. Please start over.')
        return redirect('create_claim_step1')

    rooms = Room.objects.filter(client=client).prefetch_related('work_type_values__work_type').order_by('sequence')
    encircle_rooms = Room.objects.filter(client=client, is_encircle_entry=True).order_by('sequence')

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            client.save()

            # Trigger server-side background tasks
            folder_task = create_server_folder_structure_task.delay(client.id)
            templates_task = copy_templates_to_server_task.delay(client.id)

            # ── Encircle template routing ──────────────────────────────────────────
            # Templates and work types were selected in Step 2 and stored in
            # the session.  The Encircle entries are already generated and stored
            # as Room records (is_encircle_entry=True), so the push task will use
            # them directly without re-computing.
            primary_templates   = request.session.get('primary_templates', ['basic'])
            primary_work_types  = request.session.get('primary_work_types', [])

            encircle_task = push_claim_to_encircle_task.delay(
                str(client.id), primary_templates, primary_work_types
            )

            # ── Standard 8000s / 9000s room lists ─────────────────────────────────
            # These are the default rooms created when the user picks the 8000s/9000s
            # quick-add group in Step 2.  If the user checks readings_8000/9000 in
            # Step 3 but never explicitly added those rooms in Step 2 (common case),
            # we create the sub-claim here with the canonical room list so the
            # Encircle claim always gets created when the box is checked.
            _MIT_DEFAULT_ROOMS = [
                '8100 DEHUMIDIFIER (LGR)',
                '8200 AIR MOVER',
                '8300 AIR SCRUBBER / HEPA',
                '8400 DESICCANT DEHUMIDIFIER',
                '8500 MOISTURE BARRIER',
                '8600 INJECTION DRYING SYSTEM',
            ]
            _RHT_DEFAULT_ROOMS = [
                '9100 RH/T MONITORING - LEVEL 1',
                '9200 RH/T MONITORING - LEVEL 2',
                '9300 RH/T MONITORING - LEVEL 3',
                '9400 FINAL RH/T MONITORING',
                '9500 MOISTURE READINGS LOG',
            ]

            def _subclaim_name(suffix):
                """
                Format: 'First SUFFIX Last'  e.g. 'John MC Doe', 'Jane HMR Smith'.
                Splits on the final space so multi-word first names are preserved.
                """
                owner = (client.pOwner or '').strip()
                parts = owner.rsplit(' ', 1)
                if len(parts) == 2:
                    return f"{parts[0]} {suffix} {parts[1]}"
                return f"{owner} {suffix}"

            def _find_sub_claim(suffix, session_id):
                """
                Look up an existing sub-claim Client.
                Priority: 1) session ID  2) DB name match.
                Returns None if no DB record exists.
                """
                if session_id:
                    sub = Client.objects.filter(id=session_id).first()
                    if sub:
                        return sub
                return (
                    Client.objects
                    .filter(pOwner=_subclaim_name(suffix))
                    .order_by('-id').first()
                )

            # ── MC sub-claim → Encircle (8000s readings) ──────────────────────────
            # Always creates a separate Client DB record named "{pOwner} MC",
            # the same pattern used for HMR.  If a record was already created in
            # Step 2 (stored in session) we reuse it; otherwise we create one now
            # so the MC claim appears alongside the primary in the dashboard.
            encircle_mit_task = None
            mit_session_id = request.session.pop('mit_claim_id', None)
            if 'readings_8000' in encircle_templates:
                mit_sub = _find_sub_claim('MC', mit_session_id)
                if not mit_sub:
                    try:
                        mit_sub = Client.objects.create(
                            pOwner=_subclaim_name('MC'),
                            pAddress=client.pAddress,
                            pCityStateZip=client.pCityStateZip,
                            cEmail=client.cEmail,
                            cPhone=client.cPhone,
                            claimNumber=client.claimNumber,
                            policyNumber=client.policyNumber,
                            causeOfLoss=client.causeOfLoss,
                            dateOfLoss=client.dateOfLoss,
                            insuranceCo_Name=client.insuranceCo_Name,
                            deskAdjusterDA=client.deskAdjusterDA,
                            DAPhone=client.DAPhone,
                            DAEmail=client.DAEmail,
                            fieldAdjusterName=client.fieldAdjusterName,
                            phoneFieldAdj=client.phoneFieldAdj,
                            fieldAdjEmail=client.fieldAdjEmail,
                        )
                        # Copy primary rooms so _build_8000s() stamps each
                        # actual room name into the DAY1–DAY4 MC readings rows.
                        primary_rooms_qs = (
                            Room.objects
                            .filter(client=client)
                            .prefetch_related('work_type_values__work_type')
                            .order_by('sequence')
                        )
                        for room in primary_rooms_qs:
                            new_room = Room.objects.create(
                                client=mit_sub,
                                room_name=room.room_name,
                                sequence=room.sequence,
                            )
                            for wtv in room.work_type_values.all():
                                RoomWorkTypeValue.objects.create(
                                    room=new_room,
                                    work_type=wtv.work_type,
                                    value_type=wtv.value_type,
                                )
                    except Exception:
                        mit_sub = None
                if mit_sub:
                    create_server_folder_structure_task.delay(mit_sub.id)
                    copy_templates_to_server_task.delay(mit_sub.id)
                    encircle_mit_task = push_claim_to_encircle_task.delay(
                        str(mit_sub.id), ['readings_8000']
                    )

            # ── RHT sub-claim → Encircle (9000s readings) ─────────────────────────
            # Same pattern: always a separate Client DB record named "{pOwner} RHT".
            encircle_rht_task = None
            rht_session_id = request.session.pop('rht_claim_id', None)
            if 'readings_9000' in encircle_templates:
                rht_sub = _find_sub_claim('RHT', rht_session_id)
                if not rht_sub:
                    try:
                        rht_sub = Client.objects.create(
                            pOwner=_subclaim_name('RHT'),
                            pAddress=client.pAddress,
                            pCityStateZip=client.pCityStateZip,
                            cEmail=client.cEmail,
                            cPhone=client.cPhone,
                            claimNumber=client.claimNumber,
                            policyNumber=client.policyNumber,
                            causeOfLoss=client.causeOfLoss,
                            dateOfLoss=client.dateOfLoss,
                            insuranceCo_Name=client.insuranceCo_Name,
                            deskAdjusterDA=client.deskAdjusterDA,
                            DAPhone=client.DAPhone,
                            DAEmail=client.DAEmail,
                            fieldAdjusterName=client.fieldAdjusterName,
                            phoneFieldAdj=client.phoneFieldAdj,
                            fieldAdjEmail=client.fieldAdjEmail,
                        )
                        for seq, room_name in enumerate(_RHT_DEFAULT_ROOMS, 1):
                            Room.objects.create(
                                client=rht_sub,
                                room_name=room_name,
                                sequence=seq,
                            )
                    except Exception:
                        rht_sub = None
                if rht_sub:
                    create_server_folder_structure_task.delay(rht_sub.id)
                    copy_templates_to_server_task.delay(rht_sub.id)
                    encircle_rht_task = push_claim_to_encircle_task.delay(
                        str(rht_sub.id), ['readings_9000']
                    )

            # ── HMR sub-claim → Encircle (700s only) ──────────────────────────────
            # When the user selects work type 700 (HMR = Hazardous Materials) from
            # the base list, create a separate Encircle claim named "{pOwner} HMR"
            # containing the same rooms as the primary claim but pushed with only
            # the 700-series entries.  A new Client record is created so this claim
            # is visible and manageable alongside the primary, MIT, and RHT claims.
            selected_wt_ints = [int(wt) for wt in selected_work_types if str(wt).strip().isdigit()]
            encircle_hmr_task = None
            if 700 in selected_wt_ints:
                try:
                    hmr_client = Client.objects.create(
                        pOwner=_subclaim_name('HMR'),
                        pAddress=client.pAddress,
                        pCityStateZip=client.pCityStateZip,
                        cEmail=client.cEmail,
                        cPhone=client.cPhone,
                        claimNumber=client.claimNumber,
                        policyNumber=client.policyNumber,
                        causeOfLoss=client.causeOfLoss,
                        dateOfLoss=client.dateOfLoss,
                        insuranceCo_Name=client.insuranceCo_Name,
                        deskAdjusterDA=client.deskAdjusterDA,
                        DAPhone=client.DAPhone,
                        DAEmail=client.DAEmail,
                        fieldAdjusterName=client.fieldAdjusterName,
                        phoneFieldAdj=client.phoneFieldAdj,
                        fieldAdjEmail=client.fieldAdjEmail,
                    )
                    # Copy all primary rooms (with work-type values) to the HMR sub-claim
                    primary_rooms_qs = (
                        Room.objects
                        .filter(client=client)
                        .prefetch_related('work_type_values__work_type')
                        .order_by('sequence')
                    )
                    for room in primary_rooms_qs:
                        new_room = Room.objects.create(
                            client=hmr_client,
                            room_name=room.room_name,
                            sequence=room.sequence,
                        )
                        for wtv in room.work_type_values.all():
                            RoomWorkTypeValue.objects.create(
                                room=new_room,
                                work_type=wtv.work_type,
                                value_type=wtv.value_type,
                            )
                    create_server_folder_structure_task.delay(hmr_client.id)
                    copy_templates_to_server_task.delay(hmr_client.id)
                    # Push with basic template but ONLY work type 700 so only the
                    # 700-series room entries appear in this Encircle claim
                    encircle_hmr_task = push_claim_to_encircle_task.delay(
                        str(hmr_client.id), ['basic'], [700], skip_preamble=True
                    )
                except Exception:
                    pass

            # ── SDG sub-claim → Encircle (Siding 10-17) ───────────────────────────
            # Separate Client record named "{pOwner} SDG" — same pattern as MIT/RHT.
            encircle_sdg_task = None
            sdg_session_id = request.session.pop('sdg_claim_id', None)
            if 'siding_10000' in encircle_templates:
                sdg_sub = _find_sub_claim('SDG', sdg_session_id)
                if not sdg_sub:
                    try:
                        sdg_sub = Client.objects.create(
                            pOwner=_subclaim_name('SDG'),
                            pAddress=client.pAddress,
                            pCityStateZip=client.pCityStateZip,
                            cEmail=client.cEmail,
                            cPhone=client.cPhone,
                            claimNumber=client.claimNumber,
                            policyNumber=client.policyNumber,
                            causeOfLoss=client.causeOfLoss,
                            dateOfLoss=client.dateOfLoss,
                            insuranceCo_Name=client.insuranceCo_Name,
                            deskAdjusterDA=client.deskAdjusterDA,
                            DAPhone=client.DAPhone,
                            DAEmail=client.DAEmail,
                            fieldAdjusterName=client.fieldAdjusterName,
                            phoneFieldAdj=client.phoneFieldAdj,
                            fieldAdjEmail=client.fieldAdjEmail,
                        )
                    except Exception:
                        sdg_sub = None
                if sdg_sub:
                    create_server_folder_structure_task.delay(sdg_sub.id)
                    copy_templates_to_server_task.delay(sdg_sub.id)
                    encircle_sdg_task = push_claim_to_encircle_task.delay(
                        str(sdg_sub.id), ['siding_10000']
                    )

            # Auto-generate and email labels for all rooms
            labels_task = generate_and_email_labels_task.delay(str(client.id))

            # Auto-send room list email to default recipients (synchronous)
            email_ok, email_err = _auto_send_room_list(client)

            # Clear session
            request.session.pop('creating_claim_id', None)

            from django.urls import reverse
            detail_url = reverse('claim_detail', kwargs={'claim_id': client.id})

            task_ids = {
                'folder': folder_task.id,
                'templates': templates_task.id,
                'encircle': encircle_task.id,
                'labels': labels_task.id,
            }
            # Include sub-claim Encircle task IDs when present so the
            # frontend can poll and display their status separately.
            if encircle_mit_task:
                task_ids['encircle_mit'] = encircle_mit_task.id
            if encircle_rht_task:
                task_ids['encircle_rht'] = encircle_rht_task.id
            if encircle_hmr_task:
                task_ids['encircle_hmr'] = encircle_hmr_task.id
            if encircle_sdg_task:
                task_ids['encircle_sdg'] = encircle_sdg_task.id

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'redirect_url': detail_url,
                    'claim_id': str(client.id),
                    'task_ids': task_ids,
                    'sync_status': {
                        'db': True,
                        'email': email_ok,
                        'email_error': email_err,
                    },
                })

            messages.success(request, f'Claim created for {client.pOwner}!')
            return redirect('claim_detail', claim_id=client.id)

        except Exception as e:
            if is_ajax:
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
            messages.error(request, f'Error creating claim: {str(e)}')

    context = {
        'client': client,
        'rooms': rooms,
        'encircle_rooms': encircle_rooms,
        'step': 3,
    }

    return render(request, 'docsAppR/create_claim_step3.html', context)


# ==================== Combined Single-Page Claim Creation ====================

@login_required
def create_claim_combined(request):
    """Combined single-page claim creation with rooms"""

    if request.method == 'POST':
        form = OneDriveClientForm(request.POST)

        if form.is_valid():
            client = form.save(commit=False)
            client.save()

            # Handle rooms data
            rooms_data_json = request.POST.get('rooms_data')
            if rooms_data_json:
                try:
                    rooms_data = json.loads(rooms_data_json)

                    # Create rooms
                    for room_data in rooms_data:
                        room = Room.objects.create(
                            client=client,
                            room_name=room_data['name'],
                            sequence=room_data['sequence']
                        )

                        # Get all active work types
                        all_work_types = WorkType.objects.filter(is_active=True)

                        # Get work type values from room_data (may be empty or partial)
                        work_types_data = room_data.get('work_types', {})

                        # Get WT100 value (master work type) - default to 'NA' if not provided
                        master_value = work_types_data.get('100', 'NA')

                        # Create work type values for all active work types
                        for work_type in all_work_types:
                            wt_id_str = str(work_type.work_type_id)

                            # If this is WT100, use provided value or default to 'NA'
                            if work_type.work_type_id == 100:
                                value = work_types_data.get(wt_id_str, 'NA')
                            else:
                                # All other work types follow WT100's value unless explicitly overridden
                                value = work_types_data.get(wt_id_str, master_value)

                            RoomWorkTypeValue.objects.create(
                                room=room,
                                work_type=work_type,
                                value_type=value
                            )
                except Exception as e:
                    messages.error(request, f'Error processing rooms: {str(e)}')

            # UPDATED: Trigger server-side structure creation (replaces OneDrive)
            create_server_folder_structure_task.delay(client.id)
            copy_templates_to_server_task.delay(client.id)

            # Push claim + rooms to Encircle in the background (basic always included)
            push_claim_to_encircle_task.delay(str(client.id), ['basic'])

            # Auto-generate and email labels for all rooms
            generate_and_email_labels_task.delay(str(client.id))

            messages.success(request, f'Claim created! Server folder structure is being created for {client.pOwner}.')
            return redirect('dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = OneDriveClientForm()

    work_types = WorkType.objects.filter(is_active=True).order_by('display_order')

    context = {
        'form': form,
        'work_types': work_types,
        'client': None,
    }

    return render(request, 'account/claim_form.html', context)


# ==================== Cancel Claim Creation ====================

@login_required
def cancel_claim_creation(request):
    """Cancel claim creation and clean up session"""

    if 'creating_claim_id' in request.session:
        request.session.pop('creating_claim_id')
        messages.info(request, 'Claim creation cancelled.')

    return redirect('claim_list')


def _auto_send_room_list(client, recipients=None):
    """
    Synchronously send a room list email for `client`.
    Called automatically after claim creation. Non-fatal if it fails.
    """
    from django.core.mail import EmailMessage
    from django.conf import settings
    from .views import generate_room_list_email_html, generate_room_list_pdf

    if recipients is None:
        recipients = ['galaxielsaga@gmail.com']  # testing: change when ready for full distribution

    try:
        rooms = []
        configs = {}
        for room in client.rooms.all().order_by('sequence'):
            rooms.append(room.room_name)
            room_config = {}
            for rtv in room.work_type_values.select_related('work_type'):
                room_config[str(rtv.work_type.work_type_id)] = rtv.value_type
            configs[room.room_name] = room_config

        if not rooms:
            return True, None  # nothing to send, not an error

        room_data = {'rooms': rooms, 'configs': configs}
        html_content = generate_room_list_email_html(client.pOwner, client.pAddress or '', room_data)
        pdf_buffer = generate_room_list_pdf(client.pOwner, client.pAddress or '', room_data)

        email = EmailMessage(
            subject=f'[ROOM LIST] {client.pOwner} — Worktype Documentation',
            body=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        email.content_subtype = 'html'
        pdf_filename = f"{client.pOwner.replace(' ', '_')}_Room_List.pdf"
        email.attach(pdf_filename, pdf_buffer.getvalue(), 'application/pdf')
        email.send()
        logger.info(f'Auto-sent room list for {client.pOwner} to {recipients}')
    except Exception as exc:
        logger.warning(f'_auto_send_room_list failed for {client.pOwner}: {exc}', exc_info=True)
        return False, str(exc)
    return True, None


@login_required
def claim_task_status(request):
    """
    Poll status of background Celery tasks by ID.
    GET params: folder=<id>&templates=<id>&labels=<id>&encircle=<id>
    Returns JSON with state (PENDING/STARTED/SUCCESS/FAILURE) per key.
    """
    from celery.result import AsyncResult
    keys = ['folder', 'templates', 'labels', 'encircle']
    statuses = {}
    for key in keys:
        task_id = request.GET.get(key)
        if task_id:
            r = AsyncResult(task_id)
            entry = {
                'state': r.state,
                'error': str(r.result) if r.state == 'FAILURE' else None,
            }
            if r.state == 'SUCCESS' and isinstance(r.result, dict):
                entry['result'] = r.result
            statuses[key] = entry
    return JsonResponse({'statuses': statuses})


# ==================== Encircle Push ====================

@login_required
@require_POST
def send_room_list_from_claim(request):
    """
    Send room list email for a claim that is in the process of being created (step 3).
    Reads the claim from session's 'creating_claim_id', builds room_data from its rooms
    and work-type values, then emails a PDF attachment to the requested recipients.
    """
    import json as _json
    from django.core.mail import EmailMessage
    from django.conf import settings
    from .views import generate_room_list_email_html, generate_room_list_pdf

    try:
        body = _json.loads(request.body)
    except _json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    recipients = body.get('recipients', [])
    if not recipients:
        return JsonResponse({'error': 'No recipients provided'}, status=400)

    claim_id = request.session.get('creating_claim_id')
    if not claim_id:
        return JsonResponse({'error': 'No claim in progress'}, status=400)

    client = get_object_or_404(Client, id=claim_id)

    # Build room_data
    rooms = []
    configs = {}
    for room in client.rooms.all().order_by('sequence'):
        rooms.append(room.room_name)
        room_config = {}
        for rtv in room.work_type_values.select_related('work_type'):
            # Use work_type_id (100, 200, ...) as key — matches generate_room_list_pdf expectations
            room_config[str(rtv.work_type.work_type_id)] = rtv.value_type
        configs[room.room_name] = room_config

    if not rooms:
        return JsonResponse({'error': 'No rooms found for this claim'}, status=400)

    room_data = {'rooms': rooms, 'configs': configs}

    try:
        html_content = generate_room_list_email_html(client.pOwner, client.pAddress, room_data)
        pdf_buffer = generate_room_list_pdf(client.pOwner, client.pAddress, room_data)

        email = EmailMessage(
            subject=f'[ROOM LIST] {client.pOwner} — Worktype Documentation',
            body=html_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        email.content_subtype = 'html'
        pdf_filename = f"{client.pOwner.replace(' ', '_')}_Room_List.pdf"
        email.attach(pdf_filename, pdf_buffer.getvalue(), 'application/pdf')
        email.send()

        return JsonResponse({
            'success': True,
            'recipients_count': len(recipients),
            'message': f'Room list sent to {len(recipients)} recipient(s)',
        })
    except Exception as exc:
        logger.error(f'send_room_list_from_claim error: {exc}', exc_info=True)
        return JsonResponse({'error': str(exc)}, status=500)


@login_required
@require_POST
def push_to_encircle(request, claim_id):
    """
    Manually (re-)push a claim and its rooms to Encircle.
    Called via the 'Sync to Encircle' button on claim_detail.html.
    Returns JSON so the front-end can display the result without a page reload.
    """
    client = get_object_or_404(Client, id=claim_id)

    try:
        task = push_claim_to_encircle_task.delay(str(client.id))
        return JsonResponse({
            'success': True,
            'message': f'Encircle sync queued for {client.pOwner}. '
                       f'The claim and all rooms will appear in Encircle shortly.',
            'task_id': task.id,
            'existing_encircle_id': client.encircle_claim_id or None,
        })
    except Exception as exc:
        logger.error(f"push_to_encircle view error for claim {claim_id}: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def push_rooms_to_encircle(request, claim_id):
    """
    Push rooms from a local Client to a SPECIFIC existing Encircle claim.
    Use this to correct a claim that was previously synced with wrong rooms.

    POST body (JSON):
        encircle_claim_id  – target Encircle claim id (required)
        selected_templates – list of template keys, e.g. ["basic", "readings"]
                             Defaults to ["basic", "readings"] if omitted.
    """
    import json
    client = get_object_or_404(Client, id=claim_id)

    try:
        body = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON body'}, status=400)

    encircle_claim_id = (body.get('encircle_claim_id') or '').strip()
    if not encircle_claim_id:
        return JsonResponse({'success': False, 'error': 'encircle_claim_id is required'}, status=400)

    selected_templates = body.get('selected_templates') or ['basic', 'readings']

    try:
        task = push_rooms_to_encircle_task.delay(
            str(client.id),
            encircle_claim_id,
            selected_templates,
        )
        return JsonResponse({
            'success': True,
            'message': (
                f'Room push queued for {client.pOwner} → Encircle claim {encircle_claim_id}. '
                f'Templates: {selected_templates}.'
            ),
            'task_id': task.id,
        })
    except Exception as exc:
        logger.error(f"push_rooms_to_encircle view error for claim {claim_id}: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ==================== Update Claim API ====================

@login_required
@require_POST
def update_claim(request, claim_id):
    """Update claim and trigger OneDrive sync"""
    import traceback
    import logging
    logger = logging.getLogger(__name__)

    try:
        client = get_object_or_404(Client, id=claim_id)
        logger.info(f"Updating claim {claim_id} for client {client.pOwner}")

        # Update client fields from POST data
        for field, value in request.POST.items():
            if field != 'csrfmiddlewaretoken' and field != 'client_id' and hasattr(client, field):
                # Skip checkbox fields that start with 'item_' (checklist items)
                if not field.startswith('item_'):
                    # Handle date fields properly
                    field_obj = client._meta.get_field(field)
                    if field_obj.get_internal_type() in ['DateField', 'DateTimeField']:
                        if value == '' or value is None:
                            setattr(client, field, None)
                        else:
                            try:
                                from django.utils.dateparse import parse_date, parse_datetime
                                if field_obj.get_internal_type() == 'DateField':
                                    parsed = parse_date(value)
                                else:
                                    parsed = parse_datetime(value)
                                setattr(client, field, parsed)
                            except Exception as date_err:
                                logger.warning(f"Could not parse date for field {field}: {value} - {date_err}")
                                setattr(client, field, None)
                    elif field_obj.get_internal_type() == 'BooleanField':
                        setattr(client, field, value.lower() in ('true', '1', 'yes', 'on'))
                    else:
                        field_type = field_obj.get_internal_type()
                        if value == '' or value is None:
                            # CharField/TextField are null=False - use empty string
                            if field_type in ('CharField', 'TextField'):
                                setattr(client, field, '')
                            else:
                                setattr(client, field, None)
                        else:
                            setattr(client, field, value)

        client.save()
        logger.info(f"Client {claim_id} saved successfully")
        # Note: client.save() fires regenerate_excel_files_on_update signal automatically

        # Handle checklist items update
        for item in client.checklist_items.all():
            field_name = f'item_{item.id}'
            item.is_completed = field_name in request.POST
            item.save()

        # Update completion stats
        client.update_completion_stats()

        return JsonResponse({
            'success': True,
            'message': 'Claim saved. Regenerating Excel files…',
            'regenerating_files': True,
            'completion_percent': client.completion_percent,
            'category_completion': client.category_completion or {}
        })

    except Exception as e:
        logger.error(f"Error updating claim {claim_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)


# ==================== Room Generator API Endpoints ====================

def get_claims_for_room_generator(request):
    """
    API endpoint to get all claims for the room list generator dropdown
    Returns claims with basic info needed for selection
    """
    try:
        clients = Client.objects.all().order_by('-created_at')[:200]  # Get 200 most recent claims
        claims_data = []

        for client in clients:
            claims_data.append({
                'id': client.id,
                'pOwner': client.pOwner or 'Unknown',
                'pAddress': client.pAddress or '',
                'claimNumber': client.claimNumber or '',
                'insuranceCo_Name': client.insuranceCo_Name or ''
            })

        return JsonResponse({'success': True, 'claims': claims_data})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_rooms_for_generator(request):
    """
    API endpoint to get rooms for a specific claim (for room list generator)
    Returns rooms formatted for the room list generator's baseRooms array
    """
    claim_id = request.GET.get('claim_id')

    if not claim_id:
        return JsonResponse({'success': False, 'error': 'No claim_id provided'}, status=400)

    try:
        client = Client.objects.get(id=claim_id)
        rooms = Room.objects.filter(client=client).order_by('sequence')

        rooms_data = []
        for room in rooms:
            # Get work type values for this room
            work_type_values = {}
            for wt_value in room.work_type_values.all():
                work_type_values[wt_value.work_type.work_type_id] = wt_value.value_type

            rooms_data.append({
                'sequence': room.sequence,
                'name': room.room_name,
                'work_types': work_type_values
            })

        return JsonResponse({
            'success': True,
            'rooms': rooms_data,
            'claim_info': {
                'pOwner': client.pOwner,
                'pAddress': client.pAddress,
                'claimNumber': client.claimNumber,
                'insuranceCo_Name': client.insuranceCo_Name
            }
        })

    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Claim not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ==================== Folder Browser API Endpoints ====================

@login_required
def get_folder_structure(request, claim_id):
    """
    API endpoint to get the folder structure for a claim
    Returns the folder tree with files
    Automatically creates folder structure if it doesn't exist
    """
    import os
    from pathlib import Path

    try:
        client = get_object_or_404(Client, id=claim_id)
        folder_path = client.get_server_folder_path()

        # Ensure folder structure exists - create if missing
        if not os.path.exists(folder_path):
            logger.info(f"Folder structure missing for claim {claim_id}, creating...")
            try:
                from .claim_folder_utils import create_claim_folder_structure
                result = create_claim_folder_structure(client)
                logger.info(f"Created folder structure: {result['claim_folder']}")
                # Update client with the server folder path
                client.save()

                # Trigger template generation
                from .tasks import copy_templates_to_server_task
                copy_templates_to_server_task.delay(client.id)
                logger.info(f"Triggered template generation for claim {claim_id}")

            except Exception as e:
                logger.error(f"Failed to create folder structure: {str(e)}")
                return JsonResponse({
                    'success': False,
                    'error': f'Failed to create folder structure: {str(e)}'
                }, status=500)

        # Check if Templates folder has Excel files
        templates_folder = None
        for item in os.listdir(folder_path):
            if item.startswith('Templates '):
                templates_folder = os.path.join(folder_path, item)
                break

        # If templates folder exists but has no Excel files, trigger template generation
        templates_generating = False
        if templates_folder and os.path.exists(templates_folder):
            excel_files = [f for f in os.listdir(templates_folder) if f.endswith(('.xlsx', '.xlsm'))]
            if not excel_files:
                logger.info(f"No Excel templates found for claim {claim_id}, triggering generation...")
                from .tasks import copy_templates_to_server_task
                copy_templates_to_server_task.delay(client.id)
                templates_generating = True

        def build_tree(path, base_path):
            """Recursively build folder tree structure"""
            tree = {
                'name': os.path.basename(path) or os.path.basename(base_path),
                'path': os.path.relpath(path, base_path),
                'type': 'folder',
                'children': []
            }

            try:
                items = sorted(os.listdir(path))

                # Separate folders and files
                folders = []
                files = []

                for item in items:
                    item_path = os.path.join(path, item)

                    # Skip hidden files and metadata
                    if item.startswith('.') or item == 'claim_metadata.json':
                        continue

                    if os.path.isdir(item_path):
                        folders.append(item)
                    else:
                        files.append(item)

                # Add folders first
                for folder in folders:
                    folder_path_full = os.path.join(path, folder)
                    tree['children'].append(build_tree(folder_path_full, base_path))

                # Add files
                for file in files:
                    file_path_full = os.path.join(path, file)
                    rel_path = os.path.relpath(file_path_full, base_path)

                    # Get file size and extension
                    file_size = os.path.getsize(file_path_full)
                    file_ext = os.path.splitext(file)[1].lower()
                    import datetime
                    mtime = os.path.getmtime(file_path_full)
                    last_modified = datetime.datetime.fromtimestamp(mtime).strftime('%m/%d/%Y %I:%M %p')

                    # Determine icon based on file type
                    icon = 'fa-file'
                    if file_ext in ['.xlsx', '.xlsm', '.xls']:
                        icon = 'fa-file-excel text-success'
                    elif file_ext in ['.pdf']:
                        icon = 'fa-file-pdf text-danger'
                    elif file_ext in ['.doc', '.docx']:
                        icon = 'fa-file-word text-primary'
                    elif file_ext in ['.txt']:
                        icon = 'fa-file-alt text-muted'
                    elif file_ext in ['.json']:
                        icon = 'fa-file-code text-info'
                    elif file_ext in ['.jpg', '.jpeg', '.png', '.gif']:
                        icon = 'fa-file-image text-warning'

                    tree['children'].append({
                        'name': file,
                        'path': rel_path,
                        'type': 'file',
                        'size': file_size,
                        'extension': file_ext,
                        'icon': icon,
                        'last_modified': last_modified
                    })

            except PermissionError:
                tree['error'] = 'Permission denied'

            return tree

        structure = build_tree(folder_path, folder_path)

        return JsonResponse({
            'success': True,
            'structure': structure,
            'base_path': folder_path,
            'templates_generating': templates_generating
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def download_claim_file(request, claim_id):
    """
    Download a file from the claim folder
    """
    import os
    from django.http import FileResponse, Http404
    import mimetypes

    try:
        client = get_object_or_404(Client, id=claim_id)
        folder_path = client.get_server_folder_path()

        # Get the relative path from query params
        file_path = request.GET.get('path', '')

        if not file_path:
            return JsonResponse({'success': False, 'error': 'No file path provided'}, status=400)

        # Build full path and normalize it
        full_path = os.path.normpath(os.path.join(folder_path, file_path))

        # Security check: ensure the file is within the claim folder
        if not full_path.startswith(folder_path):
            return JsonResponse({'success': False, 'error': 'Invalid file path'}, status=403)

        # Check if file exists
        if not os.path.exists(full_path) or not os.path.isfile(full_path):
            raise Http404('File not found')

        # Get the mime type
        mime_type, _ = mimetypes.guess_type(full_path)
        if not mime_type:
            mime_type = 'application/octet-stream'

        # Open and return the file
        response = FileResponse(open(full_path, 'rb'), content_type=mime_type)
        response['Content-Disposition'] = f'attachment; filename="{os.path.basename(full_path)}"'

        return response

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def download_claim_folder(request, claim_id):
    """
    Download an entire folder from the claim structure as a ZIP file.
    If the folder (especially Templates) has no files, ensures templates
    are generated synchronously before creating the ZIP.
    """
    import os
    import zipfile
    import io
    from django.http import HttpResponse, Http404
    from pathlib import Path

    try:
        client = get_object_or_404(Client, id=claim_id)
        folder_path = client.get_server_folder_path()

        # Ensure the claim folder structure exists
        if not os.path.exists(folder_path):
            from .claim_folder_utils import create_claim_folder_structure
            create_claim_folder_structure(client)
            folder_path = client.get_server_folder_path()

        # Normalize the base folder path for consistent comparison
        folder_path = os.path.normpath(folder_path)

        # Get the relative path from query params
        relative_folder = request.GET.get('path', '')

        # Build full path and normalize it
        if relative_folder:
            full_folder_path = os.path.normpath(os.path.join(folder_path, relative_folder))
        else:
            full_folder_path = folder_path

        # Security check: ensure the folder is within the claim folder
        if not full_folder_path.startswith(folder_path):
            return JsonResponse({'success': False, 'error': 'Invalid folder path'}, status=403)

        # Check if folder exists
        if not os.path.exists(full_folder_path) or not os.path.isdir(full_folder_path):
            raise Http404('Folder not found')

        # If downloading a Templates folder (or root which includes it),
        # ensure templates have been generated
        is_templates_folder = os.path.basename(full_folder_path).startswith('Templates ')
        is_root_folder = (full_folder_path == folder_path)

        if is_templates_folder or is_root_folder:
            # Find the Templates subfolder
            templates_folder = None
            if is_templates_folder:
                templates_folder = full_folder_path
            else:
                # Root folder - find the Templates subfolder within it
                for item in os.listdir(full_folder_path):
                    if item.startswith('Templates '):
                        templates_folder = os.path.join(full_folder_path, item)
                        break

            # If Templates folder exists but has no Excel files, generate them synchronously
            if templates_folder and os.path.exists(templates_folder):
                excel_files = [f for f in os.listdir(templates_folder)
                               if f.endswith(('.xlsx', '.xlsm')) and not f.startswith('~$')]
                if not excel_files:
                    logger.info(f"Templates folder empty for claim {claim_id}, generating synchronously...")
                    try:
                        from .claim_folder_utils import copy_templates_to_claim_folder, populate_excel_templates
                        copied = copy_templates_to_claim_folder(client)
                        logger.info(f"Copied {len(copied)} templates synchronously")
                        if copied:
                            result = populate_excel_templates(client, templates_folder)
                            logger.info(f"Populated templates: {result}")
                    except Exception as gen_err:
                        logger.error(f"Error generating templates synchronously: {gen_err}")

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        file_count = 0
        zip_root = full_folder_path

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(zip_root):
                for file in files:
                    if file.endswith('.json') or file.startswith('~$'):
                        continue
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, zip_root)
                    zip_file.write(file_path, arcname)
                    file_count += 1

        logger.info(f"Created ZIP with {file_count} files for claim {claim_id}")

        # Prepare the response
        zip_buffer.seek(0)

        # Generate a clean filename for the ZIP
        if relative_folder and relative_folder != '.':
            folder_name = os.path.basename(full_folder_path)
        else:
            folder_name = client.pOwner or f'Claim_{claim_id}'

        # Clean filename for download
        import re
        safe_name = re.sub(r'[<>:"/\\|?*]', '_', folder_name)
        zip_filename = f'{safe_name}.zip'

        response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="{zip_filename}"'

        return response

    except Exception as e:
        logger.error(f"Error downloading folder for claim {claim_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def download_selected_files(request, claim_id):
    """
    Download a user-selected subset of folders/files as a ZIP.
    Accepts form POST field 'paths_json' (JSON-encoded list of relative paths)
    or a JSON body with {"paths": [...]}.
    """
    import os
    import zipfile
    import io
    import json as json_mod
    import re
    from django.http import HttpResponse

    try:
        paths_json = request.POST.get('paths_json', '')
        if paths_json:
            selected_paths = json_mod.loads(paths_json)
        else:
            data = json_mod.loads(request.body)
            selected_paths = data.get('paths', [])
    except Exception:
        return JsonResponse({'error': 'Invalid data'}, status=400)

    if not selected_paths:
        return JsonResponse({'error': 'No paths selected'}, status=400)

    client = get_object_or_404(Client, id=claim_id)
    base_folder = os.path.normpath(client.get_server_folder_path())

    zip_buffer = io.BytesIO()
    added = set()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for rel_path in selected_paths:
            full_path = os.path.normpath(os.path.join(base_folder, rel_path))
            # Security: must stay within claim folder
            if not full_path.startswith(base_folder):
                continue
            if os.path.isdir(full_path):
                for root, dirs, files in os.walk(full_path):
                    for fname in files:
                        if fname.startswith('~$') or fname.endswith('.json'):
                            continue
                        fpath = os.path.join(root, fname)
                        arcname = os.path.relpath(fpath, base_folder)
                        if arcname not in added:
                            zf.write(fpath, arcname)
                            added.add(arcname)
            elif os.path.isfile(full_path):
                fname = os.path.basename(full_path)
                if not fname.startswith('~$') and not fname.endswith('.json'):
                    arcname = os.path.relpath(full_path, base_folder)
                    if arcname not in added:
                        zf.write(full_path, arcname)
                        added.add(arcname)

    zip_buffer.seek(0)
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', client.pOwner or f'Claim_{claim_id}')
    response = HttpResponse(zip_buffer.getvalue(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{safe_name}_selected.zip"'
    return response


@login_required
@require_POST
def regenerate_templates(request, claim_id):
    """
    Regenerate all Excel templates from the latest client/claim data.
    Clears Column C in jobinfo(2) for each file, then repopulates with current data.
    """
    import os
    import json as json_mod

    try:
        client = get_object_or_404(Client, id=claim_id)
        folder_path = client.get_server_folder_path()

        # Read optional method override from JSON body
        populate_method = None
        try:
            body = json_mod.loads(request.body or '{}')
            populate_method = body.get('method') or None  # 'auto'|'uno'|'xml'|None
            if populate_method not in (None, 'auto', 'uno', 'xml'):
                populate_method = None  # ignore unknown values
        except Exception:
            pass

        # Ensure folder structure exists
        if not os.path.exists(folder_path):
            from .claim_folder_utils import create_claim_folder_structure
            create_claim_folder_structure(client)
            folder_path = client.get_server_folder_path()

        from .claim_folder_utils import (
            get_templates_folder,
            copy_templates_to_claim_folder,
            populate_excel_templates,
            save_rooms_to_json,
            save_client_info_to_json,
        )

        templates_folder = get_templates_folder(client)

        # Check if templates folder has Excel files; if not, copy base templates first
        if os.path.exists(templates_folder):
            import glob
            existing = glob.glob(os.path.join(templates_folder, '*.xlsx')) + \
                       glob.glob(os.path.join(templates_folder, '*.xlsm'))
            existing = [f for f in existing if not os.path.basename(f).startswith('~$')]
        else:
            existing = []

        if not existing:
            copied = copy_templates_to_claim_folder(client)
            logger.info(f"Copied {len(copied)} base templates for regeneration")

        # Populate all templates with the latest client data
        result = populate_excel_templates(client, templates_folder, method=populate_method)

        # Also update the JSON data files
        try:
            save_rooms_to_json(client)
            save_client_info_to_json(client)
        except Exception as json_err:
            logger.warning(f"Error saving JSON data: {json_err}")

        if result.get('success'):
            method_label = result.get('method') or populate_method or 'auto'

            # Best-effort: email the files-page link to notification list
            try:
                import json as _jmod
                from django.conf import settings as _cfg
                from django.core.mail import send_mail as _send_mail
                _settings_path = _os.path.join(_cfg.MEDIA_ROOT, 'config', 'excel_hub_settings.json')
                _recipients = []
                if _os.path.exists(_settings_path):
                    with open(_settings_path) as _fh:
                        _recipients = [e.strip() for e in _jmod.load(_fh).get('emails', []) if e.strip()]
                if _recipients:
                    _files_url = request.build_absolute_uri(f'/claims/{claim_id}/files/')
                    _send_mail(
                        subject=f"Files Ready — {client.pOwner or f'Claim {claim_id}'}",
                        message=(
                            f"Excel templates for the following claim have been generated:\n\n"
                            f"  Insured : {client.pOwner or '—'}\n"
                            f"  Address : {client.pAddress or '—'}\n"
                            f"  Claim # : {client.claimNumber or '—'}\n\n"
                            f"View & download:\n{_files_url}\n\nSent from Claimet App"
                        ),
                        from_email=_cfg.DEFAULT_FROM_EMAIL,
                        recipient_list=_recipients,
                        fail_silently=True,
                    )
            except Exception as _email_err:
                logger.warning(f"Auto-email after regenerate failed: {_email_err}")

            return JsonResponse({
                'success': True,
                'message': f'Regenerated {result.get("total_processed", 0)} templates with latest claim data. [{method_label}]',
                'populated_files': result.get('populated_files', []),
                'errors': result.get('errors', []),
                'method_used': result.get('method'),
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Failed to regenerate templates'),
            }, status=500)

    except Exception as e:
        logger.error(f"Error regenerating templates for claim {claim_id}: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def data_check_audit(request, claim_id=None):
    """
    Create a new test claim with unique incremental values in every field,
    run the template generation process, then read back all templates and
    return a side-by-side comparison of input vs. output for auditing.

    The test claim is named TEST_AUDIT_NNN and persists for manual inspection.
    """
    import os
    import glob as glob_mod
    from django.db.models.signals import post_save
    from .claim_folder_utils import (
        populate_excel_templates, get_templates_folder,
        create_claim_folder_structure, copy_templates_to_claim_folder,
    )
    from .tasks import _read_jobinfo_cells
    from .models import Room, WorkType, RoomWorkTypeValue
    from .signals import (
        create_client_folder_and_templates,
        regenerate_excel_files_on_update,
        create_client_checklist,
    )

    try:
        # --- Step 1: Incremental test name ---
        existing = Client.objects.filter(pOwner__startswith='TEST_AUDIT_').count()
        test_name = f"TEST_AUDIT_{existing + 1:03d}"

        # --- Step 2: Fill every field with unique identifiable value ---
        test_values = {}
        counter = [1]

        def tv(field_name):
            val = f"TST{counter[0]:03d}_{field_name}"
            test_values[field_name] = val
            counter[0] += 1
            return val

        # Get all actual model field names from Client
        model_field_names = {f.name for f in Client._meta.get_fields() if hasattr(f, 'column')}

        # CharField fields to fill with unique test strings
        text_fields = [
            'pAddress', 'pCityStateZip', 'cPhone', 'cEmail',
            'coOwner2', 'cPhone2', 'cAddress2', 'cCityStateZip2', 'cEmail2',
            'causeOfLoss', 'rebuildType1', 'rebuildType2', 'rebuildType3', 'yearBuilt',
            'breathingIssue', 'hazardMaterialRemediation',
            'insuranceCo_Name', 'claimNumber', 'policyNumber', 'emailInsCo',
            'deskAdjusterDA', 'DAPhone', 'DAPhExt', 'DAEmail',
            'fieldAdjusterName', 'phoneFieldAdj', 'fieldAdjEmail',
            'adjContents', 'adjCpsPhone', 'adjCpsEmail',
            'emsAdj', 'emsAdjPhone', 'emsTmpEmail',
            'attLossDraftDept', 'insAddressOvernightMail', 'insCityStateZip',
            'insuranceCoPhone', 'insWebsite', 'insMailingAddress', 'insMailCityStateZip',
            'newCustomerID', 'roomID',
            'mortgageCo', 'mortgageAccountCo',
            'mortgageContactPerson', 'mortgagePhoneContact', 'mortgagePhoneExtContact',
            'mortgageAttnLossDraftDept', 'mortgageOverNightMail', 'mortgageCityStZipOVN',
            'mortgageEmail', 'mortgageWebsite', 'mortgageCoFax',
            'mortgageMailingAddress',
            'mortgageInitialOfferPhase1ContractAmount', 'drawRequest',
            'coName', 'coWebsite', 'coEmailstatus', 'coAddress', 'coCityState',
            'coAddress2', 'coCityState2', 'coCityState3',
            'coLogo1', 'coLogo2', 'coLogo3', 'coRepPH', 'coREPEmail', 'coPhone2',
            'TinW9', 'fedExAccount',
            'insuranceCustomerServiceRep', 'phoneExt',
            'timeOfClaimReport',
            'ale_lessee_name', 'ale_lessee_home_address', 'ale_lessee_city_state_zip',
            'ale_lessee_email', 'ale_lessee_phone',
            'ale_rental_bedrooms', 'ale_rental_months',
            'ale_lessor_name', 'ale_lessor_leased_address', 'ale_lessor_phone',
            'ale_lessor_email', 'ale_lessor_mailing_address', 'ale_lessor_mailing_city_zip',
            'ale_lessor_contact_person', 'ale_lessor_city_zip',
            'ale_re_mailing_address', 'ale_re_city_zip', 'ale_re_contact_person',
            'ale_re_email', 'ale_re_phone',
            'ale_re_owner_broker_name', 'ale_re_owner_broker_phone', 'ale_re_owner_broker_email',
        ]

        # Create client with only fields that exist on the model
        client = Client(pOwner=test_name)
        for field in text_fields:
            val = tv(field)
            if field in model_field_names:
                setattr(client, field, val)

        # BooleanField fields — set True, record test value as 'Y' (what build_field_mapping outputs)
        for bf in ['tarpExtTMPOk', 'IntTMPOk', 'DRYPLACUTOUTMOLDSPRAYOK']:
            if bf in model_field_names:
                setattr(client, bf, True)
            test_values[bf] = 'Y'

        # DecimalField — set a numeric test value
        if 'ale_rental_amount_per_month' in model_field_names:
            from decimal import Decimal
            client.ale_rental_amount_per_month = Decimal('12345.67')
        test_values['ale_rental_amount_per_month'] = '12345.67'

        # Boolean fields
        for bf, bv in [('demo', True), ('mitigation', True), ('CPSCLNCONCGN', True),
                       ('replacement', True), ('otherStructures', True)]:
            if bf in model_field_names:
                setattr(client, bf, bv)
            test_values[bf] = 'Y'
        if 'lossOfUseALE' in model_field_names:
            client.lossOfUseALE = 'Y'
        test_values['lossOfUseALE'] = 'Y'
        test_values['pOwner'] = test_name

        # Disconnect ALL post_save signals to prevent Celery tasks from
        # racing with our sync populate below (the Celery worker may use
        # cached old code with openpyxl, corrupting every file it touches)
        post_save.disconnect(create_client_folder_and_templates, sender=Client)
        post_save.disconnect(regenerate_excel_files_on_update, sender=Client)
        post_save.disconnect(create_client_checklist, sender=Client)
        try:
            client.save()

            # Add test rooms (also disconnect Room signal to prevent label emails)
            from .signals import generate_labels_on_room_creation
            post_save.disconnect(generate_labels_on_room_creation, sender=Room)
            try:
                work_types = list(WorkType.objects.all())
                for idx in range(1, 6):
                    room_name = f"TST_ROOM_{idx:03d}"
                    test_values[f'room_{idx}'] = room_name
                    room = Room.objects.create(client=client, room_name=room_name, sequence=idx)
                    for wt in work_types:
                        RoomWorkTypeValue.objects.create(room=room, work_type=wt, value_type='LOS')
            finally:
                post_save.connect(generate_labels_on_room_creation, sender=Room)
        finally:
            post_save.connect(create_client_folder_and_templates, sender=Client)
            post_save.connect(regenerate_excel_files_on_update, sender=Client)
            post_save.connect(create_client_checklist, sender=Client)

        # --- Step 3: Run synchronously (no Celery interference) ---
        templates_folder = get_templates_folder(client)
        if not templates_folder or not os.path.exists(templates_folder):
            create_claim_folder_structure(client)
            templates_folder = get_templates_folder(client)

        copy_templates_to_claim_folder(client)
        populate_excel_templates(client, templates_folder)

        # --- Step 4: Read back every template and compare ---
        audit_results = []
        excel_files = glob_mod.glob(os.path.join(templates_folder, '*.xlsx'))
        excel_files += glob_mod.glob(os.path.join(templates_folder, '*.xlsm'))
        excel_files = [f for f in excel_files if not os.path.basename(f).startswith('~$')]

        for fpath in sorted(excel_files):
            fname = os.path.basename(fpath)
            file_data = {'filename': fname, 'cells': []}
            try:
                cells = _read_jobinfo_cells(fpath)
                for cell in cells:
                    label = cell.get('label', '')
                    value = cell.get('value', '')
                    if label or value:
                        matched_field = None
                        for tf, tval in test_values.items():
                            if value == tval:
                                matched_field = tf
                                break
                        file_data['cells'].append({
                            'row': cell.get('row', 0),
                            'label': label,
                            'value': value,
                            'matched_field': matched_field,
                            'match': matched_field is not None,
                        })
            except Exception as e:
                file_data['error'] = str(e)
            audit_results.append(file_data)

        return JsonResponse({
            'success': True,
            'claim_id': client.id,
            'test_name': test_name,
            'test_values': test_values,
            'files': audit_results,
            'total_test_fields': len(test_values),
        })

    except Exception as e:
        logger.error(f"Data check audit error: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def upload_claim_file(request, claim_id):
    """
    Upload a file to a specific folder in the claim structure
    """
    import os
    import hashlib
    import mimetypes
    from django.core.files.storage import default_storage

    try:
        client = get_object_or_404(Client, id=claim_id)
        folder_path = client.get_server_folder_path()

        # Get the uploaded file
        uploaded_file = request.FILES.get('file')
        if not uploaded_file:
            return JsonResponse({'success': False, 'error': 'No file provided'}, status=400)

        # Get the target folder path from request
        target_folder = request.POST.get('folder_path', '')

        # Build full target folder path
        folder_path = os.path.normpath(folder_path)
        if target_folder:
            full_folder_path = os.path.normpath(os.path.join(folder_path, target_folder))
        else:
            full_folder_path = folder_path

        # Security check: ensure target is within claim folder
        if not full_folder_path.startswith(folder_path):
            return JsonResponse({'success': False, 'error': 'Invalid folder path'}, status=403)

        # Create folder if it doesn't exist
        os.makedirs(full_folder_path, exist_ok=True)

        # Build full file path
        file_name = uploaded_file.name
        full_file_path = os.path.join(full_folder_path, file_name)

        # Check if file already exists
        file_exists = os.path.exists(full_file_path)
        overwrite = request.POST.get('overwrite', 'false').lower() == 'true'

        if file_exists and not overwrite:
            return JsonResponse({
                'success': False,
                'error': 'File already exists',
                'file_exists': True,
                'filename': file_name
            }, status=409)

        # Save the file
        with open(full_file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

        # Calculate file hash
        with open(full_file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        # Get file size and mime type
        file_size = os.path.getsize(full_file_path)
        mime_type, _ = mimetypes.guess_type(full_file_path)

        # Create or update ClaimFile record
        from .models import ClaimFile
        rel_path = os.path.relpath(full_file_path, folder_path)

        # Determine file type based on filename
        file_type = 'OTHER'
        if file_name.startswith('01-INFO'):
            file_type = '01-INFO'
        elif file_name.startswith('01-ROOMS'):
            file_type = '01-ROOMS'
        elif file_name.startswith('02-INS-CO'):
            file_type = '02-INS-CO'
        elif file_name.startswith('30-MASTER'):
            file_type = '30-MASTER'
        elif 'CONTRACT' in file_name.upper():
            file_type = '50-CONTRACT'
        elif 'SCOPE' in file_name.upper():
            file_type = '60-SCOPE'
        elif 'MIT' in file_name.upper():
            file_type = '82-MIT'
        elif 'CPS' in file_name.upper():
            file_type = '92-CPS'
        elif 'INVOICE' in file_name.upper():
            file_type = '94-INVOICE'

        claim_file, created = ClaimFile.objects.update_or_create(
            client=client,
            file_path=rel_path,
            defaults={
                'file_type': file_type,
                'file_name': file_name,
                'file_size': file_size,
                'file_hash': file_hash,
                'mime_type': mime_type or 'application/octet-stream',
                'description': f'Uploaded by {request.user.username}',
                'is_active': True,
                'modified_by': request.user,
            }
        )
        # Set created_by only for new records
        if created:
            claim_file.created_by = request.user
            claim_file.save(update_fields=['created_by'])

        # Update client's last modified timestamp
        client.last_file_modified = timezone.now()
        client.last_modified_by = request.user
        client.save(update_fields=['last_file_modified', 'last_modified_by'])

        return JsonResponse({
            'success': True,
            'message': 'File uploaded successfully',
            'filename': file_name,
            'file_size': file_size,
            'file_path': rel_path,
            'created': created
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def delete_claim_file(request, claim_id):
    """
    Delete a file from the claim folder.
    Expects JSON body: { "path": "<relative path>" }
    """
    import os, json

    try:
        client = get_object_or_404(Client, id=claim_id)
        base_path = os.path.normpath(client.get_server_folder_path())

        data = json.loads(request.body)
        rel_path = data.get('path', '')
        if not rel_path:
            return JsonResponse({'success': False, 'error': 'No path provided'}, status=400)

        full_path = os.path.normpath(os.path.join(base_path, rel_path))

        # Security: must stay inside claim folder
        if not full_path.startswith(base_path):
            return JsonResponse({'success': False, 'error': 'Invalid path'}, status=403)

        if not os.path.isfile(full_path):
            return JsonResponse({'success': False, 'error': 'File not found'}, status=404)

        os.remove(full_path)

        # Remove DB record if exists
        from .models import ClaimFile
        ClaimFile.objects.filter(client=client, file_path=rel_path).delete()

        return JsonResponse({'success': True, 'message': 'File deleted'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def move_claim_file(request, claim_id):
    """
    Move a file to a different folder within the claim.
    Expects JSON body: { "source_path": "<rel path>", "dest_folder": "<rel folder path>" }
    dest_folder = "" means root of claim folder.
    """
    import os, json, shutil

    try:
        client = get_object_or_404(Client, id=claim_id)
        base_path = os.path.normpath(client.get_server_folder_path())

        data = json.loads(request.body)
        source_rel = data.get('source_path', '')
        dest_folder_rel = data.get('dest_folder', '')

        if not source_rel:
            return JsonResponse({'success': False, 'error': 'No source path provided'}, status=400)

        source_full = os.path.normpath(os.path.join(base_path, source_rel))
        dest_folder_full = os.path.normpath(os.path.join(base_path, dest_folder_rel)) if dest_folder_rel else base_path

        # Security checks
        if not source_full.startswith(base_path):
            return JsonResponse({'success': False, 'error': 'Invalid source path'}, status=403)
        if not dest_folder_full.startswith(base_path):
            return JsonResponse({'success': False, 'error': 'Invalid destination path'}, status=403)

        if not os.path.isfile(source_full):
            return JsonResponse({'success': False, 'error': 'Source file not found'}, status=404)

        if not os.path.isdir(dest_folder_full):
            return JsonResponse({'success': False, 'error': 'Destination folder not found'}, status=404)

        file_name = os.path.basename(source_full)
        dest_full = os.path.join(dest_folder_full, file_name)

        if os.path.exists(dest_full):
            return JsonResponse({'success': False, 'error': 'A file with that name already exists in the destination folder'}, status=409)

        shutil.move(source_full, dest_full)

        # Update DB record
        new_rel = os.path.relpath(dest_full, base_path)
        from .models import ClaimFile
        ClaimFile.objects.filter(client=client, file_path=source_rel).update(file_path=new_rel)

        return JsonResponse({'success': True, 'message': 'File moved', 'new_path': new_rel})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ──────────────────────────────────────────────────────────────────────────────
# Push-Rooms Tool  (correction / manual room push UI)
# ──────────────────────────────────────────────────────────────────────────────

@login_required
def push_rooms_page(request):
    """
    Renders the room-push correction tool page.
    Passes all local clients for the left-panel selector.
    """
    clients = (
        Client.objects
        .only('id', 'pOwner', 'pAddress', 'claimNumber', 'encircle_claim_id')
        .order_by('pOwner')
    )
    return render(request, 'account/push_rooms_tool.html', {'clients': clients})


@login_required
def preview_rooms_entries(request, claim_id):
    """
    GET  /claims/<claim_id>/preview-rooms/?templates=basic,readings
    Returns the exact list of room entry strings that would be pushed,
    without making any Encircle API call.
    """
    from .tasks import build_room_entries
    from .models import Room

    client = get_object_or_404(Client, id=claim_id)
    templates_param = request.GET.get('templates', 'basic,readings')
    selected_templates = [t.strip() for t in templates_param.split(',') if t.strip()]

    rooms_qs = (
        Room.objects
        .filter(client=client)
        .prefetch_related('work_type_values__work_type')
        .order_by('sequence')
    )
    room_names = []
    configs = {}
    for room in rooms_qs:
        room_names.append(room.room_name)
        configs[room.room_name] = {
            wtv.work_type.work_type_id: wtv.value_type
            for wtv in room.work_type_values.all()
        }

    entries = build_room_entries(room_names, configs, selected_templates)
    return JsonResponse({
        'client_name': client.pOwner,
        'room_count': len(room_names),
        'entry_count': len(entries),
        'entries': entries,
    })


@login_required
def encircle_claims_simple(request):
    """
    GET  /api/encircle/claims/simple/?q=<search>
    Returns a lightweight list of Encircle claims: [{id, name, address}]
    filtered by the optional ?q= query.
    Used to populate the Encircle claim selector on the push-rooms tool.
    """
    from .encircle_client import EncircleAPIClient
    from .views import EncircleDataProcessor
    q = (request.GET.get('q') or '').strip().lower()
    try:
        api = EncircleAPIClient()
        processor = EncircleDataProcessor()
        raw = api.get_all_claims()
        processed = processor.process_claims_list(raw)
        claims = [
            {
                'id': c['id'],
                'name': c.get('policyholder_name') or '',
                'address': c.get('full_address') or '',
            }
            for c in processed
        ]
        if q:
            claims = [
                c for c in claims
                if q in c['name'].lower() or q in c['address'].lower()
            ]
        claims.sort(key=lambda c: c['name'].lower())
        return JsonResponse({'claims': claims})
    except Exception as exc:
        logger.error(f"encircle_claims_simple error: {exc}", exc_info=True)
        return JsonResponse({'error': str(exc)}, status=500)


@login_required
@require_POST
def migrate_encircle_rooms(request):
    """
    POST  /claims/migrate-encircle-rooms/
    Body (JSON):  { "encircle_claim_id": "abc123" }

    Queues migrate_encircle_rooms_task which:
      1. Identifies old-format rooms (name doesn't start with a digit).
      2. Moves their photos to the best-matching new-format room.
      3. Deletes all old-format rooms.
    """
    import json
    try:
        body = json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON body'}, status=400)

    encircle_claim_id = (body.get('encircle_claim_id') or '').strip()
    if not encircle_claim_id:
        return JsonResponse({'success': False, 'error': 'encircle_claim_id is required'}, status=400)

    try:
        task = migrate_encircle_rooms_task.delay(encircle_claim_id)
        return JsonResponse({
            'success': True,
            'message': (
                f'Migration queued for Encircle claim {encircle_claim_id}. '
                'Old rooms will have their photos moved to matching new rooms, '
                'then be deleted.'
            ),
            'task_id': task.id,
        })
    except Exception as exc:
        logger.error(f"migrate_encircle_rooms view error: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def duplicate_encircle_claim(request):
    """
    POST  /claims/duplicate-encircle-claim/
    Body (JSON):
        {
            "encircle_claim_id": "abc123",
            "suffix": "(TEST COPY)"   ← optional, defaults to "(TEST COPY)"
        }

    Synchronously creates a new Encircle claim with the same metadata and a
    copy of all room entries, returning the new_claim_id immediately so the
    user can proceed to migration without manual lookup.

    The source claim is NEVER written to — only GET calls are made against it.
    """
    import json as _json
    from .encircle_client import EncircleAPIClient

    try:
        body = _json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON body'}, status=400)

    encircle_claim_id = (body.get('encircle_claim_id') or '').strip()
    if not encircle_claim_id:
        return JsonResponse({'success': False, 'error': 'encircle_claim_id is required'}, status=400)

    suffix = (body.get('suffix') or '(TEST COPY)').strip()

    try:
        api = EncircleAPIClient()

        # ── 1. Fetch source claim (READ ONLY — source is never modified) ──────
        src = api.get_claim_details(encircle_claim_id)

        # ── 2. Build new claim payload ────────────────────────────────────────
        base_name = (src.get('policyholder_name') or '').strip()
        new_name  = f"{base_name} {suffix}".strip()

        # Normalize date_of_loss: Encircle GET returns "2024-03-15T00:00:00Z",
        # but create_claim requires "YYYY-MM-DD" only.
        date_raw = src.get('date_of_loss') or ''
        date_normalized = date_raw[:10] if date_raw else ''

        new_payload = {
            'policyholder_name':      new_name,
            'full_address':           src.get('full_address') or '',
            'type_of_loss':           src.get('type_of_loss') or 'Other',
            'date_of_loss':           date_normalized,
            'adjuster_name':          src.get('adjuster_name') or '',
            'insurance_company_name': src.get('insurance_company_name') or '',
            'policy_number':          src.get('policy_number') or '',
            # At least one identifier is required by the API — copy from source
            'contractor_identifier':  str(src['contractor_identifier']) if src.get('contractor_identifier') else '',
            'assignment_identifier':  str(src['assignment_identifier']) if src.get('assignment_identifier') else '',
            'insurer_identifier':     str(src['insurer_identifier']) if src.get('insurer_identifier') else '',
        }
        # Strip empty strings so we don't send blank optional fields
        new_payload = {k: v for k, v in new_payload.items() if v}

        new_claim = api.create_claim(new_payload)
        new_claim_id = str(new_claim.get('id') or '')
        if not new_claim_id:
            raise ValueError(f"Encircle did not return an id for the new claim: {new_claim}")

        logger.info(f"duplicate_encircle_claim: created new claim {new_claim_id} ('{new_name}')")

        # ── 3. Copy rooms from source into new claim ──────────────────────────
        rooms_copied = 0
        rooms_failed = []
        try:
            # READ-ONLY fetch for source — intentionally NOT using
            # get_or_create_default_structure so we never write to the source claim.
            src_structures_resp = api.get_claim_structures(encircle_claim_id)
            src_structures = (
                src_structures_resp.get('list', src_structures_resp)
                if isinstance(src_structures_resp, dict)
                else src_structures_resp
            )
            if not src_structures:
                raise ValueError(
                    f"Source claim {encircle_claim_id} has no structures — cannot copy rooms. "
                    "The source claim was NOT modified."
                )
            src_structure    = src_structures[0]
            src_structure_id = str(src_structure.get('id') or '')

            src_rooms_resp = api.get_claim_rooms(encircle_claim_id, src_structure_id)
            src_rooms = (
                src_rooms_resp.get('list', [])
                if isinstance(src_rooms_resp, dict)
                else []
            )

            dst_structure    = api.get_or_create_default_structure(new_claim_id)
            dst_structure_id = str(dst_structure.get('id') or '')

            for room in src_rooms:
                room_name = (room.get('name') or '').strip()
                if not room_name:
                    continue
                try:
                    api.create_room(new_claim_id, dst_structure_id, {'name': room_name})
                    rooms_copied += 1
                except Exception as room_exc:
                    logger.warning(
                        f"duplicate_encircle_claim: failed to copy room '{room_name}': {room_exc}"
                    )
                    rooms_failed.append(room_name)
        except Exception as rooms_exc:
            logger.warning(f"duplicate_encircle_claim: room copy error — {rooms_exc}", exc_info=True)

        logger.info(
            f"duplicate_encircle_claim done: source={encircle_claim_id} → "
            f"new={new_claim_id}, rooms_copied={rooms_copied}"
        )

        return JsonResponse({
            'success': True,
            'new_claim_id': new_claim_id,
            'new_claim_name': new_name,
            'rooms_copied': rooms_copied,
            'rooms_failed': rooms_failed,
            'message': (
                f'Claim duplicated successfully. '
                f'New claim "{new_name}" (ID: {new_claim_id}) created with {rooms_copied} room(s) copied.'
            ),
        })

    except Exception as exc:
        logger.error(f"duplicate_encircle_claim view error: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def get_pushed_rooms(request):
    """
    GET  /claims/pushed-rooms/?encircle_claim_id=...

    Returns all rooms our system has pushed to the given Encircle claim,
    looked up from the EncirclePushedRoom tracking table.
    Does NOT call the Encircle API — instant, no network cost.
    """
    from .models import EncirclePushedRoom

    encircle_claim_id = (request.GET.get('encircle_claim_id') or '').strip()
    if not encircle_claim_id:
        return JsonResponse({'success': False, 'error': 'encircle_claim_id is required'}, status=400)

    try:
        records = EncirclePushedRoom.objects.filter(
            encircle_claim_id=encircle_claim_id
        ).values('room_id', 'room_name', 'structure_id', 'pushed_at')

        rooms = [
            {
                'id':           r['room_id'],
                'name':         r['room_name'],
                'structure_id': r['structure_id'],
                'pushed_at':    r['pushed_at'].strftime('%Y-%m-%d %H:%M') if r['pushed_at'] else '',
            }
            for r in records
        ]
        return JsonResponse({
            'success': True,
            'count':   len(rooms),
            'rooms':   rooms,
        })
    except Exception as exc:
        logger.error(f"get_pushed_rooms error: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def delete_pushed_rooms(request):
    """
    POST  /claims/delete-pushed-rooms/
    Body (JSON):
        {
            "encircle_claim_id": "abc123",
            "room_ids": ["encircle_room_id1", ...]   ← Encircle room IDs to delete
        }

    Deletes the specified rooms from Encircle and removes them from the
    EncirclePushedRoom tracking table.  structure_id is resolved from the
    tracking table — no need to pass it from the frontend.
    """
    import json as _json
    from .encircle_client import EncircleAPIClient
    from .models import EncirclePushedRoom

    try:
        body = _json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON body'}, status=400)

    encircle_claim_id = (body.get('encircle_claim_id') or '').strip()
    room_ids          = body.get('room_ids') or []

    if not encircle_claim_id:
        return JsonResponse({'success': False, 'error': 'encircle_claim_id is required'}, status=400)
    if not room_ids:
        return JsonResponse({'success': False, 'error': 'No room_ids provided'}, status=400)

    try:
        api     = EncircleAPIClient()
        deleted = []
        failed  = []

        for room_id in room_ids:
            room_id = str(room_id)
            # Look up structure_id from tracking table
            record = EncirclePushedRoom.objects.filter(
                encircle_claim_id=encircle_claim_id, room_id=room_id
            ).first()
            structure_id = record.structure_id if record else ''
            if not structure_id:
                logger.warning(f"delete_pushed_rooms: no structure_id for room {room_id}, skipping")
                failed.append({'id': room_id, 'error': 'structure_id not found in tracking table'})
                continue
            try:
                api.delete_room(encircle_claim_id, structure_id, room_id)
                deleted.append(room_id)
                EncirclePushedRoom.objects.filter(
                    encircle_claim_id=encircle_claim_id, room_id=room_id
                ).delete()
                logger.info(f"delete_pushed_rooms: deleted room {room_id} from claim {encircle_claim_id}")
            except Exception as exc:
                logger.warning(f"delete_pushed_rooms: failed to delete room {room_id}: {exc}")
                failed.append({'id': room_id, 'error': str(exc)})

        return JsonResponse({
            'success':       True,
            'deleted_count': len(deleted),
            'failed_count':  len(failed),
            'failed':        failed,
            'message': (
                f'Deleted {len(deleted)} room(s) from claim {encircle_claim_id}.'
                + (f' {len(failed)} failed.' if failed else '')
            ),
        })

    except Exception as exc:
        logger.error(f"delete_pushed_rooms error: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ──────────────────────────────────────────────────────────────────────────────
# Room Manager Tool
# ──────────────────────────────────────────────────────────────────────────────

@login_required
def room_manager_load(request):
    """GET /claims/room-manager-load/?encircle_claim_id=<id>
    Returns all rooms in Encircle's natural order (not sorted)."""
    claim_id = (request.GET.get('encircle_claim_id') or '').strip()
    if not claim_id:
        return JsonResponse({'success': False, 'error': 'encircle_claim_id required'}, status=400)
    try:
        structures = (_encircle_get(f"property_claims/{claim_id}/structures").get('list') or [])
        all_rooms = []
        default_sid = ''
        for structure in structures:
            sid = str(structure.get('id') or '')
            if not sid:
                continue
            if not default_sid:
                default_sid = sid
            after = None
            while True:
                params = {'limit': 100}
                if after:
                    params['after'] = after
                try:
                    resp = _encircle_get(f"property_claims/{claim_id}/structures/{sid}/rooms", params=params)
                except Exception as exc:
                    logger.warning(f"room_manager_load structure {sid}: {exc}")
                    break
                for r in (resp.get('list') or []):
                    rid = str(r.get('id') or '')
                    if rid:
                        all_rooms.append({'id': rid, 'name': (r.get('name') or '').strip(), 'structure_id': sid})
                after = (resp.get('cursor') or {}).get('after')
                if not after:
                    break
        return JsonResponse({'success': True, 'rooms': all_rooms, 'default_structure_id': default_sid})
    except Exception as exc:
        logger.error(f"room_manager_load: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


def _get_room_photos_for_move(claim_id, structure_id, room_id, room_name):
    """Return media items for a specific room, trying room-level then claim-level fallback."""
    from .encircle_client import EncircleAPIClient
    api = EncircleAPIClient()
    room_id_str = str(room_id)
    try:
        photos = api.get_room_media(claim_id, structure_id, room_id)
        if photos:
            return photos
    except Exception:
        pass
    # Fallback: filter claim-level media by source.primary_id
    all_media = _fetch_all_media_for_claim(claim_id)
    return [m for m in all_media
            if str((m.get('source') or {}).get('primary_id', '')) == room_id_str]


@login_required
@require_POST
def room_manager_rename(request):
    """
    POST /claims/room-manager-rename/
    Body: {claim_id, structure_id, room_id, old_name, new_name}

    Strategy (no photo moving, no room deletion):
      1. Try PATCH /rooms/{room_id} {"name": new_name} — in-place rename, photos stay.
      2. If Encircle doesn't support PATCH on rooms, fall back to:
           a. Create new room with new_name (empty — photos stay in old room).
           b. Archive old room by PATCHing its name to "OLD: {old_name}" so it
              sorts to the end and is clearly labelled for manual cleanup.
              If that PATCH also fails, old room is simply left untouched.
    No photos are ever moved. No rooms are ever deleted.
    """
    import json as _json
    try:
        body = _json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    claim_id     = (body.get('claim_id')     or '').strip()
    structure_id = (body.get('structure_id') or '').strip()
    room_id      = (body.get('room_id')      or '').strip()
    old_name     = (body.get('old_name')     or '').strip()
    new_name     = (body.get('new_name')     or '').strip()

    if not all([claim_id, structure_id, room_id, new_name]):
        return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
    if old_name and old_name == new_name:
        return JsonResponse({'success': True, 'room_id': room_id, 'method': 'no_change',
                             'message': 'Name unchanged.'})

    try:
        from .encircle_client import EncircleAPIClient
        api = EncircleAPIClient()

        # ── Strategy 1: direct PATCH rename (best — photos stay, one room) ──
        try:
            result = api._make_patch_request(
                f"property_claims/{claim_id}/structures/{structure_id}/rooms/{room_id}",
                {"name": new_name},
            )
            patched_id = str(result.get('id') or room_id)
            return JsonResponse({
                'success': True,
                'room_id': patched_id,
                'method': 'patch',
                'message': f'Renamed in-place to "{new_name}". Photos untouched.',
            })
        except Exception as patch_exc:
            logger.info(f"room_manager_rename: PATCH not supported ({patch_exc}), falling back to create+archive")

        # ── Strategy 2: create new room + archive old room (no deletion) ────
        new_room    = api.create_room(claim_id, structure_id, {'name': new_name})
        new_room_id = str(new_room.get('id') or '')
        if not new_room_id:
            raise Exception(f"create_room returned no id: {new_room}")

        # Archive old room: rename it so it sorts after regular numbered rooms.
        # Use "OLD: " prefix so it's obviously an archived room.
        archive_name = f"OLD: {old_name}" if old_name else f"OLD: {room_id}"
        archived = False
        try:
            api._make_patch_request(
                f"property_claims/{claim_id}/structures/{structure_id}/rooms/{room_id}",
                {"name": archive_name},
            )
            archived = True
        except Exception as arch_exc:
            logger.info(f"room_manager_rename: could not archive old room ({arch_exc}); left untouched")

        return JsonResponse({
            'success':      True,
            'room_id':      new_room_id,
            'old_room_id':  room_id,
            'method':       'create_and_archive',
            'archived':     archived,
            'message': (
                f'Created new room "{new_name}". '
                + (f'Old room archived as "{archive_name}".'
                   if archived
                   else 'Old room left as-is (photos remain there).')
            ),
        })

    except Exception as exc:
        logger.error(f"room_manager_rename: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def room_manager_add(request):
    """POST /claims/room-manager-add/
    Body: {claim_id, structure_id, name}"""
    import json as _json
    try:
        body = _json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    claim_id    = (body.get('claim_id')    or '').strip()
    structure_id= (body.get('structure_id')or '').strip()
    name        = (body.get('name')        or '').strip()
    if not all([claim_id, structure_id, name]):
        return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
    try:
        from .encircle_client import EncircleAPIClient
        api = EncircleAPIClient()
        new_room = api.create_room(claim_id, structure_id, {'name': name})
        return JsonResponse({'success': True, 'room_id': str(new_room.get('id') or ''), 'name': name})
    except Exception as exc:
        logger.error(f"room_manager_add: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def room_manager_delete_room(request):
    """POST /claims/room-manager-delete/
    Body: {claim_id, structure_id, room_id}"""
    import json as _json
    try:
        body = _json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    claim_id    = (body.get('claim_id')    or '').strip()
    structure_id= (body.get('structure_id')or '').strip()
    room_id     = (body.get('room_id')     or '').strip()
    if not all([claim_id, structure_id, room_id]):
        return JsonResponse({'success': False, 'error': 'Missing required fields'}, status=400)
    try:
        from .encircle_client import EncircleAPIClient
        api = EncircleAPIClient()
        api.delete_room(claim_id, structure_id, room_id)
        return JsonResponse({'success': True})
    except Exception as exc:
        logger.error(f"room_manager_delete_room: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def bulk_rename_db_rooms(request):
    """
    POST /claims/bulk-rename-db-rooms/
    Body JSON: { "client_id": 123, "room_names": ["LIVING ROOM DN", ...] }

    Renames existing DB rooms by position order to match room_names.
    If room_names has more entries than existing rooms, the extra names are
    created as new Room rows (no work-type values — same as adding a room in Step 2).
    Never deletes rooms.
    """
    import json as _json
    try:
        body = _json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    client_id  = body.get('client_id')
    room_names = [n.strip() for n in (body.get('room_names') or []) if str(n).strip()]

    if not client_id:
        return JsonResponse({'success': False, 'error': 'client_id required'}, status=400)
    if not room_names:
        return JsonResponse({'success': False, 'error': 'room_names must be a non-empty list'}, status=400)

    try:
        client = Client.objects.get(id=client_id)
        rooms  = list(Room.objects.filter(client=client).order_by('sequence', 'id'))

        renamed = 0
        added   = 0
        results = []

        # Rename existing rooms by position
        for i, room in enumerate(rooms):
            if i >= len(room_names):
                break
            new_name = room_names[i]
            old_name = room.room_name
            if new_name != old_name:
                room.room_name = new_name
                room.save(update_fields=['room_name'])
                renamed += 1
                results.append({'action': 'renamed', 'old': old_name, 'new': new_name})
            else:
                results.append({'action': 'unchanged', 'old': old_name, 'new': new_name})

        # Add rooms for any names beyond the existing count
        if len(room_names) > len(rooms):
            next_seq = (rooms[-1].sequence + 1) if rooms else 1
            for name in room_names[len(rooms):]:
                Room.objects.create(client=client, room_name=name, sequence=next_seq)
                results.append({'action': 'added', 'old': '', 'new': name})
                next_seq += 1
                added += 1

        return JsonResponse({
            'success': True,
            'renamed': renamed,
            'added':   added,
            'total':   len(results),
            'results': results,
        })
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Claim not found'}, status=404)
    except Exception as exc:
        logger.error(f"bulk_rename_db_rooms: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def room_manager_extract_700s(request):
    """POST /claims/room-manager-extract-700s/
    Body: {source_claim_id, new_claim_name}
    Detects 700-series rooms, creates a new HMR claim, copies rooms+photos, deletes from source."""
    import json as _json
    import requests as _req
    import re as _re
    try:
        body = _json.loads(request.body or '{}')
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    source_claim_id = (body.get('source_claim_id') or '').strip()
    new_claim_name  = (body.get('new_claim_name')  or '').strip()
    if not source_claim_id or not new_claim_name:
        return JsonResponse({'success': False, 'error': 'source_claim_id and new_claim_name required'}, status=400)

    try:
        from .encircle_client import EncircleAPIClient
        api = EncircleAPIClient()
        auth_hdr = {"Authorization": _ENCIRCLE_HEADERS["Authorization"]}

        source_claim = _encircle_get(f"property_claims/{source_claim_id}")
        structures   = (_encircle_get(f"property_claims/{source_claim_id}/structures").get('list') or [])

        _700_re = _re.compile(r'^7\d{2}', _re.IGNORECASE)
        rooms_to_move = []
        for structure in structures:
            sid = str(structure.get('id') or '')
            if not sid:
                continue
            rooms_resp = _encircle_get(f"property_claims/{source_claim_id}/structures/{sid}/rooms")
            for r in (rooms_resp.get('list') or []):
                name = (r.get('name') or '').strip()
                if _700_re.match(name) or 'HMR' in name.upper():
                    rooms_to_move.append({'id': str(r.get('id')), 'name': name, 'structure_id': sid})

        if not rooms_to_move:
            return JsonResponse({'success': False, 'error': 'No 700-series or HMR rooms found.'}, status=400)

        ids = api.get_account_ids()
        new_claim = api.create_claim({
            'policyholder_name':      new_claim_name,
            'type_of_loss':           source_claim.get('type_of_loss') or 'Other',
            'full_address':           source_claim.get('full_address') or '',
            'organization_id':        ids.get('organization_id'),
            'brand_id':               ids.get('brand_id'),
            'contractor_identifier':  ids.get('contractor_identifier'),
        })
        new_claim_id = str(new_claim.get('id') or '')
        if not new_claim_id:
            raise Exception(f"create_claim returned no id: {new_claim}")

        new_structure    = api.get_or_create_default_structure(new_claim_id)
        new_structure_id = str(new_structure.get('id') or '')

        rooms_done = photos_copied = 0
        errors = []

        for room in rooms_to_move:
            new_room    = api.create_room(new_claim_id, new_structure_id, {'name': room['name']})
            new_room_id = str(new_room.get('id') or '')
            if not new_room_id:
                errors.append(f"Could not create room: {room['name']}")
                continue

            # Copy photos to the new claim using the proven 3-step upload flow.
            photos = _get_room_photos_for_move(source_claim_id, room['structure_id'], room['id'], room['name'])
            room_photo_errors = 0
            for photo in photos:
                dl_url       = photo.get('download_uri') or photo.get('url') or ''
                filename     = photo.get('filename') or 'photo.jpg'
                content_type = photo.get('content_type') or 'image/jpeg'
                if not dl_url:
                    continue
                try:
                    dl = _req.get(dl_url, timeout=60)
                    dl.raise_for_status()
                    r_up = _req.post(f"{_ENCIRCLE_BASE_URL}/upload", headers=auth_hdr,
                                     files={"file": (filename, dl.content, content_type)}, timeout=120)
                    if not r_up.ok:
                        errors.append(f"Upload failed {filename}: {r_up.status_code}")
                        room_photo_errors += 1
                        continue
                    upload_id = r_up.json().get("upload_id") or r_up.json().get("id")
                    r_att = _req.post(f"{_ENCIRCLE_BASE_URL}/property_claims/{new_claim_id}/media",
                                      headers={**auth_hdr, "Content-Type": "application/json"},
                                      json={"upload_id": upload_id, "filename": filename, "content_type": content_type},
                                      timeout=30)
                    if r_att.ok:
                        att = r_att.json()
                        if isinstance(att, list):
                            att = att[0] if att else {}
                        mid = str(att.get("id") or (att.get("source") or {}).get("primary_id") or "")
                        if mid:
                            api.reassign_media(new_claim_id, mid, new_room_id)
                        photos_copied += 1
                    else:
                        errors.append(f"Attach failed {filename}: {r_att.status_code}")
                        room_photo_errors += 1
                except Exception as exc:
                    errors.append(f"{filename}: {str(exc)[:80]}")
                    room_photo_errors += 1

            rooms_done += 1
            if room_photo_errors:
                errors.append(
                    f"Room '{room['name']}': {room_photo_errors} photo(s) failed to copy."
                )

        # NOTE: source rooms are intentionally NOT deleted here.
        # The frontend shows a "Delete source rooms" button so the user can verify
        # photos arrived before removing originals.
        extracted_rooms = [
            {'id': r['id'], 'name': r['name'], 'structure_id': r['structure_id']}
            for r in rooms_to_move
        ]

        return JsonResponse({
            'success':          True,
            'new_claim_id':     new_claim_id,
            'rooms_extracted':  rooms_done,
            'photos_copied':    photos_copied,
            'errors':           errors,
            'extracted_rooms':  extracted_rooms,   # returned so UI can offer delete
            'source_claim_id':  source_claim_id,
            'message': (
                f'Copied {rooms_done} room(s) and {photos_copied} photo(s) to new claim '
                f'"{new_claim_name}" (id={new_claim_id}). '
                f'Source rooms are still in the original claim — verify photos, then delete.'
                + (f' {len(errors)} warning(s).' if errors else '')
            ),
        })
    except Exception as exc:
        logger.error(f"room_manager_extract_700s: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ──────────────────────────────────────────────────────────────────────────────
# Photo Copy Tool  (copy photos from one Encircle claim into another claim's room)
# ──────────────────────────────────────────────────────────────────────────────
# Three endpoints:
#   GET  /claims/encircle-photo-folders/        — fetch ALL media; group by room label
#   GET  /claims/encircle-claim-rooms/          — list all rooms on a destination claim
#   POST /claims/upload-label-photos-to-room/   — download photos by label, re-upload to dest room

_ENCIRCLE_API_KEY  = "367382d2-0b2d-4b01-9d06-8f18fd492f5e"
_ENCIRCLE_BASE_URL = "https://api.encircleapp.com/v1"
_ENCIRCLE_HEADERS  = {"Authorization": f"Bearer {_ENCIRCLE_API_KEY}"}


def _encircle_get(path, params=None):
    """Direct GET to Encircle v1 API.  Returns parsed JSON dict or raises."""
    import requests as _req
    url  = f"{_ENCIRCLE_BASE_URL}/{path.lstrip('/')}"
    resp = _req.get(url, headers=_ENCIRCLE_HEADERS, params=params, timeout=30)
    if not resp.ok:
        raise Exception(f"Encircle {resp.status_code}: {resp.text[:300]}")
    return resp.json()




def _fetch_all_media_for_claim(claim_id):
    """
    Paginate through GET /property_claims/{id}/media and return every item as a list.
    Each item has at minimum: id, filename, content_type, download_uri, labels (list).
    """
    all_items = []
    after_cursor = None
    while True:
        params = {'limit': 100}
        if after_cursor:
            params['after'] = after_cursor
        page = _encircle_get(f"property_claims/{claim_id}/media", params=params)
        items = page.get('list') or []
        all_items.extend(items)
        cursor = page.get('cursor') or {}
        after_cursor = cursor.get('after')
        if not after_cursor or not items:
            break
    return all_items


def _fetch_all_claim_media(api, claim_id):
    """Fetch every media item for claim_id using the working claim-level endpoint."""
    all_media = []
    after_cursor = None
    while True:
        params = {'limit': 100}
        if after_cursor:
            params['after'] = after_cursor
        resp = api._make_request(f"property_claims/{claim_id}/media", params=params)
        if not resp or 'list' not in resp:
            break
        all_media.extend(resp['list'])
        after_cursor = (resp.get('cursor') or {}).get('after')
        if not after_cursor:
            break
    return all_media


@login_required
def encircle_photo_folders(request):
    """
    GET /claims/encircle-photo-folders/?encircle_claim_id=<id>

    Fetches ALL media for the claim via GET /property_claims/{id}/media.
    Groups items by the last non-empty element of each item's `labels` list
    (that is how Encircle's own mobile app and EncircleMediaDownloader
    associate photos to rooms).

    Returns every folder with its photo count AND the full list of photos so
    the UI can display filenames, making it obvious what will be copied.

    Response:
        {
          "success": true,
          "total_media": N,
          "folders": [
            {
              "label": "LIVING ROOM",
              "count": 5,
              "photos": [
                {"id": "...", "filename": "...", "content_type": "image/jpeg", "download_uri": "..."},
                ...
              ]
            },
            ...
          ]
        }
    """
    claim_id = (request.GET.get('encircle_claim_id') or '').strip()
    if not claim_id:
        return JsonResponse({'success': False, 'error': 'encircle_claim_id required'}, status=400)

    try:
        all_items = _fetch_all_media_for_claim(claim_id)

        # Build folders: group by last non-empty label on each item.
        # Include full photo info so the UI can display filenames.
        folder_map = {}   # label -> list of photo dicts
        for item in all_items:
            labels  = [l.strip() for l in (item.get('labels') or []) if l.strip()]
            label   = labels[-1] if labels else 'Unlabeled'
            photo   = {
                'id':           str(item.get('id') or ''),
                'filename':     item.get('filename') or 'photo.jpg',
                'content_type': item.get('content_type') or 'image/jpeg',
                'download_uri': item.get('download_uri') or item.get('url') or '',
            }
            folder_map.setdefault(label, []).append(photo)

        folders = sorted(
            [{'label': k, 'count': len(v), 'photos': v} for k, v in folder_map.items()],
            key=lambda x: x['label'].lower(),
        )
        return JsonResponse({'success': True, 'total_media': len(all_items), 'folders': folders})

    except Exception as exc:
        logger.error(f"encircle_photo_folders error: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
def encircle_claim_rooms_with_photos(request):
    """
    GET /claims/encircle-claim-rooms/?encircle_claim_id=<id>

    Returns every room on the claim across all its structures.
    Uses direct Encircle API calls (no EncircleAPIClient wrapper).

    Response:
        {"success": true, "rooms": [{"id": "...", "name": "...", "structure_id": "..."}, ...]}
    """
    claim_id = (request.GET.get('encircle_claim_id') or '').strip()
    if not claim_id:
        return JsonResponse({'success': False, 'error': 'encircle_claim_id required'}, status=400)

    try:
        # 1. Get all structures for the claim
        structures_resp = _encircle_get(f"property_claims/{claim_id}/structures")
        structures = structures_resp.get('list') or []

        all_rooms = []
        for structure in structures:
            sid = str(structure.get('id') or '')
            if not sid:
                continue
            # 2. Paginate through all rooms in this structure
            after = None
            while True:
                params = {'limit': 100}
                if after:
                    params['after'] = after
                try:
                    rooms_resp = _encircle_get(
                        f"property_claims/{claim_id}/structures/{sid}/rooms",
                        params=params,
                    )
                except Exception as exc:
                    logger.warning(f"encircle_claim_rooms: structure {sid}: {exc}")
                    break
                for r in (rooms_resp.get('list') or []):
                    rid = str(r.get('id') or '')
                    if rid:
                        all_rooms.append({
                            'id':           rid,
                            'name':         (r.get('name') or '').strip(),
                            'structure_id': sid,
                        })
                after = (rooms_resp.get('cursor') or {}).get('after')
                if not after:
                    break

        all_rooms.sort(key=lambda r: r['name'].lower())
        return JsonResponse({'success': True, 'rooms': all_rooms})

    except Exception as exc:
        logger.error(f"encircle_claim_rooms error: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


@login_required
@require_POST
def upload_label_photos_to_room(request):
    """
    POST /claims/upload-label-photos-to-room/

    Downloads every photo in the given source label folder from source_claim,
    then re-uploads each to dest_claim/dest_room.  Works across different claims.

    Body JSON:
        {
          "source_claim_id": "...",
          "source_label":    "LIVING ROOM",   // the folder label to copy
          "dest_claim_id":   "...",
          "dest_room_id":    "..."
        }

    Response:
        {"success": true, "copied": 5, "failed": 0, "errors": [], "message": "..."}
    """
    import json as _json
    import base64 as _b64
    import requests as _req
    from .encircle_client import EncircleAPIClient

    try:
        body = _json.loads(request.body or '{}')
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Invalid JSON body'}, status=400)

    source_claim_id = (body.get('source_claim_id') or '').strip()
    source_label    = (body.get('source_label')    or '').strip()
    dest_claim_id   = (body.get('dest_claim_id')   or '').strip()
    dest_room_id    = (body.get('dest_room_id')    or '').strip()

    missing = [k for k, v in [
        ('source_claim_id', source_claim_id),
        ('source_label',    source_label),
        ('dest_claim_id',   dest_claim_id),
        ('dest_room_id',    dest_room_id),
    ] if not v]
    if missing:
        return JsonResponse({'success': False, 'error': f'Missing: {", ".join(missing)}'}, status=400)

    try:
        api = EncircleAPIClient()

        # Fetch ALL media for the source claim (claim-level endpoint, proven to work)
        all_items = _fetch_all_media_for_claim(source_claim_id)

        # Keep only items whose labels list contains source_label (case-insensitive)
        label_lower = source_label.lower()
        to_copy = [
            item for item in all_items
            if any(l.strip().lower() == label_lower for l in (item.get('labels') or []))
        ]

        if not to_copy:
            return JsonResponse({
                'success': True, 'copied': 0, 'failed': 0, 'errors': [],
                'message': (
                    f'No photos found for folder "{source_label}" '
                    f'(claim has {len(all_items)} total photos across all folders).'
                ),
            })

        copied = 0
        errors = []
        for item in to_copy:
            dl_url       = item.get('download_uri') or item.get('url') or ''
            filename     = item.get('filename') or 'photo.jpg'
            content_type = item.get('content_type') or 'image/jpeg'

            if not dl_url:
                errors.append({'filename': filename, 'error': 'No download_uri in API response'})
                continue
            try:
                # Step 1 — download the photo bytes from Encircle CDN
                dl = _req.get(dl_url, timeout=60)
                dl.raise_for_status()

                # Correct Encircle upload flow (per /v1/upload API docs):
                #   Step 2a — POST /v1/upload  →  binary multipart, returns {"upload_id": "..."}
                #   Step 2b — POST /v1/property_claims/{id}/media  →  JSON with upload_id + source
                auth_hdr = {"Authorization": _ENCIRCLE_HEADERS["Authorization"]}

                # 2a — upload the file bytes to the dedicated upload endpoint
                r_upload = _req.post(
                    f"{_ENCIRCLE_BASE_URL}/upload",
                    headers=auth_hdr,
                    files={"file": (filename, dl.content, content_type)},
                    timeout=120,
                )
                if not r_upload.ok:
                    try:
                        err = r_upload.json()
                    except Exception:
                        err = r_upload.text[:400]
                    raise Exception(f"Encircle /upload {r_upload.status_code}: {err}")

                upload_id = r_upload.json().get("upload_id") or r_upload.json().get("id")
                if not upload_id:
                    raise Exception(f"No upload_id in /upload response: {r_upload.json()}")

                # 2b — attach upload to the destination claim (no source here)
                r_attach = _req.post(
                    f"{_ENCIRCLE_BASE_URL}/property_claims/{dest_claim_id}/media",
                    headers={**auth_hdr, "Content-Type": "application/json"},
                    json={
                        "upload_id":    upload_id,
                        "filename":     filename,
                        "content_type": content_type,
                    },
                    timeout=30,
                )
                if not r_attach.ok:
                    try:
                        err = r_attach.json()
                    except Exception:
                        err = r_attach.text[:400]
                    raise Exception(f"Encircle /media attach {r_attach.status_code}: {err}")

                # 2c — assign to destination room via PATCH
                # The attach response has no top-level 'id'; the media ID is source.primary_id
                attach_data = r_attach.json()
                if isinstance(attach_data, list):
                    attach_data = attach_data[0] if attach_data else {}

                media_id = str(
                    attach_data.get("id") or
                    (attach_data.get("source") or {}).get("primary_id") or ""
                )

                if media_id:
                    api.reassign_media(dest_claim_id, media_id, dest_room_id)
                else:
                    logger.warning(f"No media_id in attach response: {attach_data}")

                copied += 1
            except Exception as exc:
                errors.append({'filename': filename, 'error': str(exc)})
                logger.warning(f"upload_label_photos_to_room: {filename}: {exc}")

        return JsonResponse({
            'success':  True,
            'copied':   copied,
            'failed':   len(errors),
            'errors':   errors,
            'message':  f'Uploaded {copied} photo(s) to destination room.'
                        + (f' {len(errors)} failed.' if errors else ''),
        })

    except Exception as exc:
        logger.error(f"upload_label_photos_to_room error: {exc}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ══════════════════════════════════════════════════════════════════════════════
# CLAIM FILES PAGE — per-claim file browser + shareable link emailer
# ══════════════════════════════════════════════════════════════════════════════

@login_required
def claim_files_page(request, claim_id):
    """Standalone, shareable file browser for a single claim."""
    client = get_object_or_404(Client, id=claim_id)
    return render(request, 'docsAppR/claim_files.html', {'client': client})


@login_required
@require_POST
def send_files_link_email(request, claim_id):
    """Send an email with the link to this claim's files page."""
    import os, json as _jmod
    from django.conf import settings as _cfg
    from django.core.mail import send_mail

    client = get_object_or_404(Client, id=claim_id)

    # Resolve recipients from settings file
    settings_path = os.path.join(_cfg.MEDIA_ROOT, 'config', 'excel_hub_settings.json')
    recipients = []
    try:
        if os.path.exists(settings_path):
            with open(settings_path) as fh:
                recipients = [e.strip() for e in _jmod.load(fh).get('emails', []) if e.strip()]
    except Exception:
        pass

    if not recipients:
        return JsonResponse({
            'success': False,
            'error': 'No notification emails configured. Add them via the Email Settings button on the Excel Hub page.',
        }, status=400)

    files_url = request.build_absolute_uri(f'/claims/{claim_id}/files/')
    claim_label = client.pOwner or f'Claim {claim_id}'
    subject = f"Claim Files Ready — {claim_label}"
    body = (
        f"Files for the following claim are ready to view:\n\n"
        f"  Insured : {client.pOwner or '—'}\n"
        f"  Address : {client.pAddress or '—'}\n"
        f"  Claim # : {client.claimNumber or '—'}\n\n"
        f"View & download files:\n{files_url}\n\n"
        f"Sent from Claimet App"
    )

    try:
        send_mail(subject, body, _cfg.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
        return JsonResponse({'success': True, 'recipients': recipients})
    except Exception as e:
        logger.error(f"send_files_link_email error: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# ══════════════════════════════════════════════════════════════════════════════
# EXCEL HUB — standalone page for browsing / emailing / downloading Excel files
# ══════════════════════════════════════════════════════════════════════════════

import os as _os
import io as _io
import zipfile as _zipfile
import json as _json_mod
import datetime as _dt
import re as _re

from django.conf import settings as _settings
from django.core.mail import EmailMessage as _EmailMessage

_EXCEL_HUB_SETTINGS_PATH = _os.path.join(_settings.MEDIA_ROOT, 'config', 'excel_hub_settings.json')
_EXCEL_EXTS = {'.xlsx', '.xlsm', '.xls'}


def _eh_get_emails():
    """Return list of configured notification emails."""
    try:
        if _os.path.exists(_EXCEL_HUB_SETTINGS_PATH):
            with open(_EXCEL_HUB_SETTINGS_PATH) as f:
                return [e.strip() for e in _json_mod.load(f).get('emails', []) if e.strip()]
    except Exception:
        pass
    return []


def _eh_save_emails(emails):
    _os.makedirs(_os.path.dirname(_EXCEL_HUB_SETTINGS_PATH), exist_ok=True)
    with open(_EXCEL_HUB_SETTINGS_PATH, 'w') as f:
        _json_mod.dump({'emails': emails}, f)


def _eh_fmt_size(n):
    if n < 1024:
        return f"{n} B"
    if n < 1048576:
        return f"{n/1024:.1f} KB"
    return f"{n/1048576:.1f} MB"


def _eh_claim_excel_files(client):
    """Return list of folder-groups with Excel files for one claim."""
    folder_path = client.get_server_folder_path()
    if not folder_path or not _os.path.exists(folder_path):
        return []

    by_folder = {}
    for root, dirs, files in _os.walk(folder_path):
        dirs.sort()
        for fname in sorted(files):
            ext = _os.path.splitext(fname)[1].lower()
            if ext not in _EXCEL_EXTS or fname.startswith('~$'):
                continue
            full = _os.path.join(root, fname)
            rel = _os.path.relpath(full, folder_path).replace('\\', '/')
            folder_rel = _os.path.relpath(root, folder_path)
            folder_name = '(root)' if folder_rel == '.' else folder_rel.replace('\\', '/')
            try:
                mtime = _dt.datetime.fromtimestamp(_os.path.getmtime(full)).strftime('%m/%d/%Y')
                size = _os.path.getsize(full)
            except OSError:
                mtime, size = '', 0
            by_folder.setdefault(folder_name, []).append({
                'name': fname,
                'path': rel,
                'folder': folder_name,
                'size': size,
                'size_str': _eh_fmt_size(size),
                'modified': mtime,
            })

    # Sort folders: Templates first, then alphabetical
    result = []
    for k in sorted(by_folder.keys(), key=lambda x: (not x.startswith('Templates'), x)):
        result.append({'folder_name': k, 'files': by_folder[k]})
    return result


def _eh_send_email_for_client(client, recipients, xlsx_bytes=None, xlsx_name=None):
    """
    Send an email with all Excel files for a client (or a single xlsx_bytes file).
    Returns (files_sent, error_str).
    """
    folder_path = client.get_server_folder_path()
    attachments = []  # list of (filename, bytes)

    if xlsx_bytes and xlsx_name:
        attachments.append((xlsx_name, xlsx_bytes))
    else:
        if folder_path and _os.path.exists(folder_path):
            for root, dirs, files in _os.walk(folder_path):
                for fname in sorted(files):
                    ext = _os.path.splitext(fname)[1].lower()
                    if ext not in _EXCEL_EXTS or fname.startswith('~$'):
                        continue
                    try:
                        with open(_os.path.join(root, fname), 'rb') as fh:
                            attachments.append((fname, fh.read()))
                    except OSError:
                        pass

    if not attachments:
        return 0, 'No Excel files found'

    subject = (
        f"Excel Files — {client.pOwner or 'Claim'}"
        + (f" | {client.claimNumber}" if client.claimNumber else '')
    )
    body = (
        f"Excel file(s) for claim:\n\n"
        f"  Insured : {client.pOwner or '—'}\n"
        f"  Address : {client.pAddress or '—'}\n"
        f"  Claim # : {client.claimNumber or '—'}\n\n"
        f"{len(attachments)} file(s) attached.\n\nSent by Claimet App"
    )
    try:
        msg = _EmailMessage(
            subject=subject, body=body,
            from_email=_settings.DEFAULT_FROM_EMAIL, to=recipients,
        )
        for fname, data in attachments:
            msg.attach(fname, data, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        msg.send()
        return len(attachments), None
    except Exception as e:
        return 0, str(e)


# ── Views ─────────────────────────────────────────────────────────────────────

@login_required
def excel_hub(request):
    """Render the standalone Excel Hub page."""
    return render(request, 'docsAppR/excel_hub.html', {
        'notification_emails': _eh_get_emails(),
    })


@login_required
def excel_hub_api(request):
    """JSON: all claims with their Excel files, grouped by folder."""
    clients = Client.objects.all().order_by('pOwner')
    result = []
    for client in clients:
        groups = _eh_claim_excel_files(client)
        if not groups:
            continue
        total = sum(len(g['files']) for g in groups)
        result.append({
            'id': client.id,
            'name': client.pOwner or f'Claim {client.id}',
            'address': client.pAddress or '',
            'claim_number': client.claimNumber or '',
            'folder_groups': groups,
            'total_files': total,
        })
    return JsonResponse({'claims': result, 'total': len(result)})


@login_required
def excel_hub_download_zip(request, claim_id):
    """Download all Excel files for one claim as a ZIP."""
    client = get_object_or_404(Client, id=claim_id)
    folder_path = client.get_server_folder_path()

    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, 'w', _zipfile.ZIP_DEFLATED) as zf:
        if folder_path and _os.path.exists(folder_path):
            for root, dirs, files in _os.walk(folder_path):
                for fname in files:
                    ext = _os.path.splitext(fname)[1].lower()
                    if ext not in _EXCEL_EXTS or fname.startswith('~$'):
                        continue
                    full = _os.path.join(root, fname)
                    arcname = _os.path.relpath(full, folder_path).replace('\\', '/')
                    zf.write(full, arcname)

    buf.seek(0)
    from django.http import HttpResponse
    safe = _re.sub(r'[<>:"/\\|?*]', '_', client.pOwner or f'Claim_{claim_id}')
    resp = HttpResponse(buf.getvalue(), content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="{safe}_Excel.zip"'
    return resp


@login_required
def excel_hub_download_all_zip(request):
    """Download all Excel files across every claim as a single ZIP."""
    from django.http import HttpResponse
    clients = Client.objects.all().order_by('pOwner')

    buf = _io.BytesIO()
    with _zipfile.ZipFile(buf, 'w', _zipfile.ZIP_DEFLATED) as zf:
        for client in clients:
            folder_path = client.get_server_folder_path()
            if not folder_path or not _os.path.exists(folder_path):
                continue
            safe = _re.sub(r'[<>:"/\\|?*]', '_', client.pOwner or f'Claim_{client.id}')
            for root, dirs, files in _os.walk(folder_path):
                for fname in files:
                    ext = _os.path.splitext(fname)[1].lower()
                    if ext not in _EXCEL_EXTS or fname.startswith('~$'):
                        continue
                    full = _os.path.join(root, fname)
                    rel = _os.path.relpath(full, folder_path).replace('\\', '/')
                    zf.write(full, f"{safe}/{rel}")

    buf.seek(0)
    date_str = _dt.date.today().strftime('%Y%m%d')
    resp = HttpResponse(buf.getvalue(), content_type='application/zip')
    resp['Content-Disposition'] = f'attachment; filename="AllClaims_Excel_{date_str}.zip"'
    return resp


@login_required
@require_POST
def excel_hub_send_email(request, claim_id):
    """POST: send email with all Excel files for one claim."""
    client = get_object_or_404(Client, id=claim_id)
    try:
        data = _json_mod.loads(request.body or '{}')
        recipients = [e.strip() for e in data.get('recipients', []) if e.strip()]
    except Exception:
        recipients = []

    if not recipients:
        recipients = _eh_get_emails()

    if not recipients:
        return JsonResponse({'success': False, 'error': 'No recipients configured. Add emails in Settings first.'}, status=400)

    sent, err = _eh_send_email_for_client(client, recipients)
    if err:
        return JsonResponse({'success': False, 'error': err}, status=500)
    return JsonResponse({'success': True, 'files_sent': sent, 'recipients': recipients})


@login_required
def excel_hub_settings(request):
    """GET: return notification email list. POST: update it."""
    if request.method == 'POST':
        try:
            data = _json_mod.loads(request.body or '{}')
            emails = [e.strip() for e in data.get('emails', []) if e.strip()]
            _eh_save_emails(emails)
            return JsonResponse({'success': True, 'emails': emails})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'emails': _eh_get_emails()})
