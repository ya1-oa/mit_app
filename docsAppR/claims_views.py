# docsAppR/onedrive_views.py
# Views for OneDrive-integrated claim creation workflow

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.db import transaction
from django.db.models import Count, Q, Case, When, IntegerField, F
from django.core.paginator import Paginator
from django.utils import timezone
import json
import logging

from .models import Client, Room, WorkType, RoomWorkTypeValue, ChecklistItem
# OneDrive models removed: OneDriveFolder, OneDriveFile, SyncLog
from .forms import OneDriveClientForm, RoomSelectionForm, BulkWorkTypeForm
# UPDATED: Use server-side tasks instead of OneDrive tasks
from .tasks import create_server_folder_structure_task, copy_templates_to_server_task, push_claim_to_encircle_task, generate_and_email_labels_task

# Configure logging
logger = logging.getLogger(__name__)


# ==================== Claim List View ====================

@login_required
def claim_list(request):
    """List all claims with filtering, sorting, and pagination"""

    # Get query parameters
    search = request.GET.get('search', '')
    sort_by = request.GET.get('sort', '-created_at')  # Default: newest first
    filter_completion = request.GET.get('completion', '')  # Filter by completion status

    # Valid sort options
    valid_sorts = {
        '-created_at': '-created_at',
        'created_at': 'created_at',
        '-completion_percent': '-completion_percent',
        'completion_percent': 'completion_percent',
        'pOwner': 'pOwner',
        '-pOwner': '-pOwner',
        '-updated_at': '-updated_at',
    }
    sort_field = valid_sorts.get(sort_by, '-created_at')

    # Base queryset with checklist completion annotations
    claims = Client.objects.annotate(
        total_checklist_items=Count('checklist_items'),
        completed_checklist_items=Count('checklist_items', filter=Q(checklist_items__is_completed=True)),
        # Category-specific counts
        mit_total=Count('checklist_items', filter=Q(checklist_items__document_category='MIT')),
        mit_completed=Count('checklist_items', filter=Q(checklist_items__document_category='MIT', checklist_items__is_completed=True)),
        cps_total=Count('checklist_items', filter=Q(checklist_items__document_category='CPS')),
        cps_completed=Count('checklist_items', filter=Q(checklist_items__document_category='CPS', checklist_items__is_completed=True)),
        ppr_total=Count('checklist_items', filter=Q(checklist_items__document_category='PPR')),
        ppr_completed=Count('checklist_items', filter=Q(checklist_items__document_category='PPR', checklist_items__is_completed=True)),
    )

    # Apply search filter
    if search:
        claims = claims.filter(
            Q(pOwner__icontains=search) |
            Q(claimNumber__icontains=search) |
            Q(pAddress__icontains=search)
        )

    # Apply completion filter
    if filter_completion == 'complete':
        # Show only claims with 100% completion
        claims = claims.filter(completion_percent=100)
    elif filter_completion == 'incomplete':
        # Show only claims with < 100% completion
        claims = claims.filter(completion_percent__lt=100)
    elif filter_completion == 'not_started':
        # Show claims with 0% completion
        claims = claims.filter(completion_percent=0)
    elif filter_completion == 'in_progress':
        # Show claims with 1-99% completion
        claims = claims.filter(completion_percent__gt=0, completion_percent__lt=100)

    # Apply sorting
    claims = claims.order_by(sort_field)

    # Pagination
    paginator = Paginator(claims, 20)  # 20 claims per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search': search,
        'sort_by': sort_by,
        'filter_completion': filter_completion,
    }

    return render(request, 'docsAppR/claim_list.html', context)


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

    context = {
        'client': client,
        'work_types': work_types,
        'selection_form': selection_form,
        'bulk_form': bulk_form,
        'step': 2,
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
        source_rooms = Room.objects.filter(client=source_client).prefetch_related('work_type_values__work_type')

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
    """AJAX endpoint to save rooms data and proceed to step 3"""

    client_id = request.session.get('creating_claim_id')

    if not client_id:
        return JsonResponse({'success': False, 'error': 'No active claim creation session'})

    try:
        client = Client.objects.get(id=client_id)
        rooms_data = json.loads(request.POST.get('rooms_data', '[]'))

        if not rooms_data:
            return JsonResponse({'success': False, 'error': 'No rooms provided'})

        # Use transaction to ensure atomicity
        with transaction.atomic():
            # Delete existing rooms for this client
            Room.objects.filter(client=client).delete()

            # Create new rooms
            for room_data in rooms_data:
                room = Room.objects.create(
                    client=client,
                    room_name=room_data['name'],
                    sequence=room_data['sequence']
                    # REMOVED: sync_status field (OneDrive-specific, not in Room model)
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

        return JsonResponse({'success': True, 'message': f'Saved {len(rooms_data)} rooms'})

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

    if request.method == 'POST':
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        try:
            client.save()

            # Trigger server-side background tasks
            folder_task = create_server_folder_structure_task.delay(client.id)
            templates_task = copy_templates_to_server_task.delay(client.id)

            # Push claim + rooms to Encircle with selected templates
            encircle_templates = request.POST.getlist('encircle_templates')
            encircle_task = push_claim_to_encircle_task.delay(str(client.id), encircle_templates)

            # Auto-generate and email labels for all rooms
            labels_task = generate_and_email_labels_task.delay(str(client.id))

            # Auto-send room list email to default recipients (synchronous)
            email_ok, email_err = _auto_send_room_list(client)

            # Clear session
            request.session.pop('creating_claim_id', None)

            from django.urls import reverse
            detail_url = reverse('claim_detail', kwargs={'claim_id': client.id})

            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'redirect_url': detail_url,
                    'claim_id': str(client.id),
                    'task_ids': {
                        'folder': folder_task.id,
                        'templates': templates_task.id,
                        'encircle': encircle_task.id,
                        'labels': labels_task.id,
                    },
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
        'step': 3,
    }

    return render(request, 'docsAppR/create_claim_step3.html', context)


# ==================== Sync Actions ====================
# REMOVED: OneDrive sync functions no longer needed with server-side storage
# sync_from_onedrive() - REMOVED
# sync_to_onedrive() - REMOVED


# ==================== Combined Single-Page Claim Creation ====================

@login_required
def create_claim_combined(request):
    """Combined single-page claim creation with rooms"""

    if request.method == 'POST':
        form = OneDriveClientForm(request.POST)

        if form.is_valid():
            # Save client
            client = form.save(commit=False)
            # OneDrive sync status removed
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
                            # REMOVED: sync_status field (OneDrive-specific, not in Room model)
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
        recipients = ['wsbjoe9@gmail.com', 'galaxielsaga@gmail.com']

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
            statuses[key] = {
                'state': r.state,
                'error': str(r.result) if r.state == 'FAILURE' else None,
            }
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

        # For root downloads: only include the Templates folder (Excel + PDFs)
        # For specific subfolder downloads: include everything in that folder
        if is_root_folder:
            # Find the Templates subfolder and zip only that
            templates_dir = None
            for item in os.listdir(full_folder_path):
                if item.startswith('Templates '):
                    templates_dir = os.path.join(full_folder_path, item)
                    break
            zip_root = templates_dir if templates_dir and os.path.exists(templates_dir) else full_folder_path
        else:
            zip_root = full_folder_path

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for root, dirs, files in os.walk(zip_root):
                for file in files:
                    if file.endswith('.json') or file.startswith('~$'):
                        continue
                    # For root downloads, only include Excel and PDF files
                    if is_root_folder:
                        ext = os.path.splitext(file)[1].lower()
                        if ext not in ('.xlsx', '.xlsm', '.pdf'):
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
