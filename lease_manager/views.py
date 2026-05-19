"""
Lease Manager app views.
"""
import json
import logging
import os

from datetime import timedelta, date

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from docsAppR.models import (
    Client, Landlord, Lease, LeaseDocument, LeaseActivity,
)

# generate_document_from_html is shared with dashboard — import from docsAppR
from docsAppR.views import generate_document_from_html  # noqa: F401 (re-exported)

logger = logging.getLogger(__name__)


def lease_manager(request):
    """
    Main Lease Manager Dashboard
    Displays leases (not individual documents), activity feed, and pipeline status
    """
    from docsAppR.models import PipelineStageAssignment, LeaseStageCompletion

    # Get filter parameters
    status_filter = request.GET.get('status', '')
    client_filter = request.GET.get('client', '')
    date_filter = request.GET.get('date_range', '30')  # Default 30 days

    # Calculate date range
    try:
        days = int(date_filter)
    except ValueError:
        days = 30
    date_threshold = timezone.now() - timedelta(days=days)

    today = date.today()

    # Get all leases
    leases_query = Lease.objects.select_related(
        'client', 'created_by', 'last_modified_by'
    ).prefetch_related('documents', 'stage_completions', 'stage_completions__assigned_user', 'stage_completions__completed_by')

    if status_filter:
        leases_query = leases_query.filter(status=status_filter)
    if client_filter:
        leases_query = leases_query.filter(client__id=client_filter)

    all_leases = leases_query.order_by('-created_at')[:100]

    # Get recent activity
    recent_activity = LeaseActivity.objects.select_related(
        'lease', 'lease__client', 'performed_by'
    ).filter(
        created_at__gte=date_threshold
    ).order_by('-created_at')[:50]

    # Pipeline statistics - current counts
    pipeline_stats = Lease.objects.values('status').annotate(
        count=Count('id')
    ).order_by('status')

    status_counts = {item['status']: item['count'] for item in pipeline_stats}

    STATUS_ORDER = [
        'draft', 'generated', 'review', 'sent_for_signature',
        'signed', 'invoice_created', 'package_sent',
        'payment_pending', 'payment_received', 'completed'
    ]

    cumulative_counts = {}
    total_non_cancelled = Lease.objects.exclude(status='cancelled').count()

    for i, status in enumerate(STATUS_ORDER):
        statuses_at_or_past = STATUS_ORDER[i:]
        cumulative_counts[status] = Lease.objects.filter(
            status__in=statuses_at_or_past
        ).exclude(status='cancelled').count()

    stage_assignments = PipelineStageAssignment.objects.select_related('assigned_user').order_by('order')

    pipeline_steps = []
    for i, status_tuple in enumerate(Lease.LEASE_STATUS_CHOICES):
        status_value, status_label = status_tuple
        if status_value == 'cancelled':
            continue

        assignment = stage_assignments.filter(stage=status_value).first()
        assignee_email = assignment.assigned_user.email if assignment and assignment.assigned_user else 'Unassigned'
        assignee_initials = ''.join([part[0].upper() for part in assignee_email.split('@')[0].split('.')[:2]]) if assignment and assignment.assigned_user else '?'

        pipeline_steps.append({
            'value': status_value,
            'label': status_label,
            'order': i,
            'assignee_email': assignee_email,
            'assignee_initials': assignee_initials,
            'current_count': status_counts.get(status_value, 0),
            'cumulative_count': cumulative_counts.get(status_value, 0),
        })

    total_active = Lease.objects.filter(
        lease_start_date__lte=today,
        lease_end_date__gte=today
    ).exclude(
        status__in=['completed', 'cancelled']
    ).count()

    total_completed = Lease.objects.filter(status='completed').count()

    total_expired = Lease.objects.filter(
        lease_end_date__lt=today
    ).exclude(
        status__in=['completed', 'cancelled']
    ).count()

    clients_with_leases = Client.objects.filter(
        leases__isnull=False
    ).distinct().prefetch_related(
        'leases', 'leases__documents'
    ).annotate(
        lease_count=Count('leases', distinct=True),
        active_lease_count=Count(
            'leases',
            filter=Q(leases__lease_start_date__lte=today) & Q(leases__lease_end_date__gte=today) & ~Q(leases__status__in=['completed', 'cancelled']),
            distinct=True
        )
    ).order_by('-leases__created_at')

    all_clients = Client.objects.all().order_by('pOwner')
    status_choices = Lease.LEASE_STATUS_CHOICES

    total_monthly_rent = Lease.objects.filter(
        lease_start_date__lte=today,
        lease_end_date__gte=today
    ).exclude(
        status__in=['completed', 'cancelled']
    ).aggregate(
        total=Sum('monthly_rent')
    )['total'] or 0

    context = {
        'leases': all_leases,
        'recent_activity': recent_activity,
        'status_counts': status_counts,
        'cumulative_counts': cumulative_counts,
        'pipeline_steps': pipeline_steps,
        'stage_assignments': stage_assignments,
        'total_active': total_active,
        'total_completed': total_completed,
        'total_expired': total_expired,
        'total_non_cancelled': total_non_cancelled,
        'clients_with_leases': clients_with_leases,
        'all_clients': all_clients,
        'status_choices': status_choices,
        'current_status_filter': status_filter,
        'current_client_filter': client_filter,
        'current_date_filter': date_filter,
        'total_monthly_rent': total_monthly_rent,
        'today': today,
    }

    return render(request, 'account/lease_manager.html', context)


def create_draft_lease(request):
    """
    Auto-create a draft lease when user starts inputting information for a client.
    Called via AJAX when user selects a client for lease generation.
    """
    from docsAppR.models import PipelineStageAssignment, LeaseStageCompletion

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        client_id = data.get('client_id')
        client_name = data.get('client_name')

        if not client_id and not client_name:
            return JsonResponse({'error': 'client_id or client_name required'}, status=400)

        if client_id:
            client = Client.objects.get(id=client_id)
        else:
            client = Client.objects.get(pOwner=client_name)

        existing_draft = Lease.objects.filter(
            client=client,
            status='draft'
        ).first()

        if existing_draft:
            return JsonResponse({
                'success': True,
                'lease_id': str(existing_draft.id),
                'message': 'Existing draft found',
                'is_new': False
            })

        lease = Lease.objects.create(
            client=client,
            lessor_name='',
            property_address=client.pAddress or '',
            property_city=client.pCityStateZip.split(',')[0].strip() if client.pCityStateZip else '',
            status='draft',
            created_by=request.user if request.user.is_authenticated else None,
            last_modified_by=request.user if request.user.is_authenticated else None,
        )

        LeaseActivity.objects.create(
            lease=lease,
            activity_type='draft',
            description=f'Draft lease created for {client.pOwner}',
            performed_by=request.user if request.user.is_authenticated else None
        )

        stage_assignments = PipelineStageAssignment.objects.all()
        for assignment in stage_assignments:
            LeaseStageCompletion.objects.create(
                lease=lease,
                stage=assignment.stage,
                assigned_user=assignment.assigned_user,
                is_completed=False
            )

        draft_completion = LeaseStageCompletion.objects.filter(
            lease=lease,
            stage='draft'
        ).first()
        if draft_completion:
            draft_completion.is_completed = True
            draft_completion.completed_by = request.user if request.user.is_authenticated else None
            draft_completion.completed_at = timezone.now()
            draft_completion.save()

        return JsonResponse({
            'success': True,
            'lease_id': str(lease.id),
            'message': 'Draft lease created',
            'is_new': True
        })

    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)
    except Exception as e:
        logger.error(f"Error creating draft lease: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


def update_lease_status(request):
    """API endpoint to update lease status"""
    from docsAppR.models import LeaseStageCompletion

    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        lease_id = data.get('lease_id')
        new_status = data.get('status')

        if not lease_id or not new_status:
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        lease = Lease.objects.get(id=lease_id)
        old_status = lease.status

        lease.status = new_status
        lease.last_modified_by = request.user if request.user.is_authenticated else None

        now = timezone.now()
        status_timestamp_map = {
            'generated': 'generated_at',
            'review': 'reviewed_at',
            'sent_for_signature': 'sent_for_signature_at',
            'signed': 'signed_at',
            'invoice_created': 'invoice_created_at',
            'package_sent': 'package_sent_at',
            'payment_received': 'payment_received_at',
            'completed': 'completed_at',
        }

        if new_status in status_timestamp_map:
            setattr(lease, status_timestamp_map[new_status], now)

        lease.save()

        stage_completion = LeaseStageCompletion.objects.filter(
            lease=lease,
            stage=new_status
        ).first()

        if stage_completion and not stage_completion.is_completed:
            stage_completion.is_completed = True
            stage_completion.completed_by = request.user if request.user.is_authenticated else None
            stage_completion.completed_at = now
            stage_completion.save()

        LeaseActivity.objects.create(
            lease=lease,
            activity_type=new_status,
            description=f'Status changed from "{old_status}" to "{new_status}"',
            old_status=old_status,
            new_status=new_status,
            performed_by=request.user if request.user.is_authenticated else None
        )

        return JsonResponse({
            'success': True,
            'new_status': new_status,
            'status_display': lease.get_status_display()
        })

    except Lease.DoesNotExist:
        return JsonResponse({'error': 'Lease not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_leases_by_client(request, client_id):
    """API endpoint to get leases for a specific client"""
    today = date.today()

    try:
        client = Client.objects.get(id=client_id)
        leases = Lease.objects.filter(client=client).prefetch_related('documents').order_by('-created_at')

        leases_data = []
        for lease in leases:
            docs = [{
                'id': str(doc.id),
                'document_type': doc.document_type,
                'document_type_display': doc.get_document_type_display(),
                'document_name': doc.document_name,
                'file_path': doc.file_path,
            } for doc in lease.documents.all()]

            leases_data.append({
                'id': str(lease.id),
                'lessor_name': lease.lessor_name,
                'property_address': lease.full_property_address,
                'monthly_rent': float(lease.monthly_rent) if lease.monthly_rent else None,
                'lease_start_date': lease.lease_start_date.isoformat() if lease.lease_start_date else None,
                'lease_end_date': lease.lease_end_date.isoformat() if lease.lease_end_date else None,
                'status': lease.status,
                'status_display': lease.get_status_display(),
                'status_color': lease.get_status_color(),
                'is_active': lease.is_active,
                'is_expired': lease.is_expired,
                'is_renewal': lease.is_renewal,
                'created_at': lease.created_at.isoformat(),
                'created_by': lease.created_by.email if lease.created_by else None,
                'documents': docs,
            })

        return JsonResponse({
            'success': True,
            'client': {
                'id': client.id,
                'name': client.pOwner,
                'address': client.pAddress,
            },
            'leases': leases_data
        })

    except Client.DoesNotExist:
        return JsonResponse({'error': 'Client not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def download_lease_document(request, document_id):
    """Download a specific lease document PDF"""
    import mimetypes

    try:
        lease_doc = LeaseDocument.objects.select_related('lease').get(id=document_id)

        if not lease_doc.file_path:
            return HttpResponse("Document file path not set", status=404)

        full_path = os.path.join(settings.MEDIA_ROOT, lease_doc.file_path)

        if not os.path.exists(full_path):
            return HttpResponse(f"Document file not found at {full_path}", status=404)

        LeaseActivity.objects.create(
            lease=lease_doc.lease,
            activity_type='downloaded',
            description=f'Downloaded {lease_doc.document_name}',
            performed_by=request.user if request.user.is_authenticated else None
        )

        with open(full_path, 'rb') as f:
            content = f.read()

        content_type, _ = mimetypes.guess_type(full_path)
        response = HttpResponse(content, content_type=content_type or 'application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{lease_doc.document_name}.pdf"'
        return response

    except LeaseDocument.DoesNotExist:
        return HttpResponse("Document not found", status=404)
    except Exception as e:
        return HttpResponse(f"Error downloading document: {str(e)}", status=500)


def view_lease_document(request, document_id):
    """View a specific lease document PDF in browser"""
    import mimetypes

    try:
        lease_doc = LeaseDocument.objects.select_related('lease').get(id=document_id)

        if not lease_doc.file_path:
            return HttpResponse("Document file path not set", status=404)

        full_path = os.path.join(settings.MEDIA_ROOT, lease_doc.file_path)

        if not os.path.exists(full_path):
            return HttpResponse(f"Document file not found", status=404)

        LeaseActivity.objects.create(
            lease=lease_doc.lease,
            activity_type='viewed',
            description=f'Viewed {lease_doc.document_name}',
            performed_by=request.user if request.user.is_authenticated else None
        )

        with open(full_path, 'rb') as f:
            content = f.read()

        content_type, _ = mimetypes.guess_type(full_path)
        response = HttpResponse(content, content_type=content_type or 'application/pdf')
        response['Content-Disposition'] = f'inline; filename="{lease_doc.document_name}.pdf"'
        return response

    except LeaseDocument.DoesNotExist:
        return HttpResponse("Document not found", status=404)
    except Exception as e:
        return HttpResponse(f"Error viewing document: {str(e)}", status=500)


def add_lease_note(request):
    """Add a note to a lease"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        lease_id = data.get('lease_id')
        note = data.get('note', '').strip()

        if not lease_id or not note:
            return JsonResponse({'error': 'Missing required fields'}, status=400)

        lease = Lease.objects.get(id=lease_id)

        timestamp = timezone.now().strftime('%Y-%m-%d %H:%M')
        user_name = request.user.email if request.user.is_authenticated else 'Anonymous'
        new_note = f"[{timestamp}] {user_name}: {note}"

        if lease.notes:
            lease.notes = f"{lease.notes}\n\n{new_note}"
        else:
            lease.notes = new_note

        lease.save()

        LeaseActivity.objects.create(
            lease=lease,
            activity_type='note_added',
            description=f'Note added: {note[:100]}...' if len(note) > 100 else f'Note added: {note}',
            performed_by=request.user if request.user.is_authenticated else None
        )

        return JsonResponse({'success': True, 'note': new_note})

    except Lease.DoesNotExist:
        return JsonResponse({'error': 'Lease not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def lease_activity_feed(request):
    """API endpoint to get paginated activity feed"""
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 20))
    client_filter = request.GET.get('client', '')

    offset = (page - 1) * per_page

    query = LeaseActivity.objects.select_related('lease', 'lease__client', 'performed_by')

    if client_filter:
        query = query.filter(lease__client__id=client_filter)

    total_count = query.count()
    activities = query.order_by('-created_at')[offset:offset + per_page]

    activity_data = []
    for activity in activities:
        activity_data.append({
            'id': str(activity.id),
            'activity_type': activity.activity_type,
            'activity_type_display': activity.get_activity_type_display(),
            'description': activity.description,
            'client_name': activity.lease.client.pOwner if activity.lease else 'Unknown',
            'client_id': activity.lease.client.id if activity.lease else None,
            'lease_id': str(activity.lease.id) if activity.lease else None,
            'performed_by': activity.performed_by.email if activity.performed_by else 'System',
            'created_at': activity.created_at.isoformat(),
            'time_ago': _get_time_ago(activity.created_at),
        })

    return JsonResponse({
        'success': True,
        'activities': activity_data,
        'total_count': total_count,
        'page': page,
        'per_page': per_page,
        'has_more': offset + per_page < total_count
    })


def _get_time_ago(dt):
    """Helper function to get human-readable time ago string"""
    now = timezone.now()
    diff = now - dt

    if diff.days > 30:
        return dt.strftime('%b %d, %Y')
    elif diff.days > 0:
        return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"
    else:
        return "Just now"


def save_landlord(request):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            landlord_data = {
                # Basic Information
                'full_name': request.POST.get('full_name'),
                'address': request.POST.get('address'),
                'city': request.POST.get('city'),
                'state': request.POST.get('state'),
                'zip_code': request.POST.get('zip_code'),
                'phone': request.POST.get('phone'),
                'email': request.POST.get('email'),

                # Rental Property Information
                'property_address': request.POST.get('property_address'),
                'property_city': request.POST.get('property_city'),
                'property_state': request.POST.get('property_state'),
                'property_zip': request.POST.get('property_zip'),

                # term start and end
                'term_start_date': request.POST.get('term_start_date'),
                'term_end_date': request.POST.get('term_end_date'),

                # Agreement Defaults
                'default_rent_amount': request.POST.get('default_rent_amount', 0),
                'default_security_deposit': request.POST.get('default_security_deposit', 0),
                'default_rent_due_day': request.POST.get('default_rent_due_day', 1),
                'default_late_fee': request.POST.get('default_late_fee', 0),
                'default_late_fee_start_day': request.POST.get('default_late_fee_start_day', 5),
                'default_eviction_day': request.POST.get('default_eviction_day', 10),
                'default_nsf_fee': request.POST.get('default_nsf_fee', 0),
                'default_max_occupants': request.POST.get('default_max_occupants', 10),
                'default_parking_spaces': request.POST.get('default_parking_spaces', 2),
                'default_parking_fee': request.POST.get('default_parking_fee', 0),
                'default_inspection_fee': request.POST.get('default_inspection_fee', 300.00),
                'bedrooms': request.POST.get('bedrooms', 1),
                'rental_months': request.POST.get('rental_months'),

                # Additional Contact Persons
                'contact_person_1': request.POST.get('contact_person_1'),
                'contact_person_2': request.POST.get('contact_person_2'),
                'contact_phone': request.POST.get('contact_phone'),
                'contact_email': request.POST.get('contact_email'),

                # Real Estate Company Information
                'real_estate_company': request.POST.get('real_estate_company'),
                'company_mailing_address': request.POST.get('company_mailing_address'),
                'company_city': request.POST.get('company_city'),
                'company_state': request.POST.get('company_state'),
                'company_zip': request.POST.get('company_zip'),
                'company_contact_person': request.POST.get('company_contact_person'),
                'company_phone': request.POST.get('company_phone'),
                'company_email': request.POST.get('company_email'),
                'broker_name': request.POST.get('broker_name'),
                'broker_phone': request.POST.get('broker_phone'),
                'broker_email': request.POST.get('broker_email'),
            }

            if landlord_data['term_start_date']:
                landlord_data['term_start_date'] = parse_date(landlord_data['term_start_date'])
            if landlord_data['term_end_date']:
                landlord_data['term_end_date'] = parse_date(landlord_data['term_end_date'])

            # Convert empty strings to None for non-required fields
            for field in landlord_data:
                if landlord_data[field] == '':
                    landlord_data[field] = None

            # Validate required fields
            required_fields = [
                'full_name', 'address', 'city', 'state', 'zip_code', 'phone',
                'property_address', 'property_city', 'property_state', 'property_zip'
            ]

            missing_fields = [field for field in required_fields if not landlord_data.get(field)]
            if missing_fields:
                return JsonResponse({
                    'success': False,
                    'error': f'Missing required fields: {", ".join(missing_fields)}'
                })

            # Convert numeric fields
            numeric_fields = [
                'default_rent_amount', 'default_security_deposit', 'default_late_fee',
                'default_nsf_fee', 'default_rent_due_day', 'default_late_fee_start_day',
                'default_eviction_day', 'default_max_occupants', 'default_parking_spaces',
                'default_parking_fee', 'default_inspection_fee'
            ]

            for field in numeric_fields:
                if landlord_data[field] is not None:
                    try:
                        if field in ['default_rent_amount', 'default_security_deposit',
                                     'default_late_fee', 'default_nsf_fee', 'default_inspection_fee']:
                            landlord_data[field] = float(landlord_data[field])
                        else:
                            landlord_data[field] = int(landlord_data[field])
                    except (ValueError, TypeError):
                        return JsonResponse({
                            'success': False,
                            'error': f'Invalid value for {field.replace("_", " ").title()}'
                        })

            landlord, created = Landlord.objects.update_or_create(
                property_address=landlord_data['property_address'],
                defaults=landlord_data
            )

            return JsonResponse({
                'success': True,
                'created': created,
                'landlord_id': landlord.id
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e),
                'type': type(e).__name__
            })

    return JsonResponse({
        'success': False,
        'error': 'Invalid request method or not AJAX'
    })
