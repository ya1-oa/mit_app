"""
Dashboard app views.
Imports view functions from docsAppR and exposes the home page (app grid).
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

# Re-export existing views from docsAppR
from docsAppR.views import (
    dashboard,
    checklist,
    update_checklist,
    api_client_details,
    create,
    generate_invoice_pdf,
    statistics,
    logout_view,
    client_list,
    generate_all_documents,
    generate_document_from_html,
    generate_data_report,
    get_all_clients,
    send_room_list_email,
    import_client_with_rooms_formula_support,
)
from encircle.views import generate_room_entries_from_configs


@login_required
def activity_page(request):
    """
    Global system activity log — all actions across every app, newest first.
    Supports filtering by action type and user, and pagination.
    """
    from docsAppR.models import SystemActivity, LeaseActivity, SentEmail

    action_filter = request.GET.get('action', '')
    user_filter   = request.GET.get('user', '')
    page          = max(1, int(request.GET.get('page', 1)))
    per_page      = 50

    qs = SystemActivity.objects.select_related('performed_by', 'related_client', 'related_lease')
    if action_filter:
        qs = qs.filter(action_type=action_filter)
    if user_filter:
        qs = qs.filter(performed_by__email__icontains=user_filter)

    total   = qs.count()
    offset  = (page - 1) * per_page
    activities = qs[offset: offset + per_page]
    has_more   = offset + per_page < total

    # Stats cards
    from django.db.models import Count
    from django.utils import timezone
    from datetime import timedelta
    since_24h  = timezone.now() - timedelta(hours=24)
    since_7d   = timezone.now() - timedelta(days=7)

    stats = {
        'total':    total,
        'today':    SystemActivity.objects.filter(created_at__gte=since_24h).count(),
        'week':     SystemActivity.objects.filter(created_at__gte=since_7d).count(),
        'emails':   SystemActivity.objects.filter(action_type__in=['email_sent', 'package_sent']).count(),
        'leases':   SystemActivity.objects.filter(action_type__in=['lease_created', 'lease_status_changed']).count(),
        'letters':  SystemActivity.objects.filter(action_type='demand_letter').count(),
    }

    from docsAppR.models import SystemActivity as SA
    action_choices = SA.ACTION_CHOICES

    context = {
        'activities':     activities,
        'stats':          stats,
        'action_choices': action_choices,
        'action_filter':  action_filter,
        'user_filter':    user_filter,
        'page':           page,
        'per_page':       per_page,
        'total':          total,
        'has_more':       has_more,
        'has_prev':       page > 1,
        'next_page':      page + 1,
        'prev_page':      page - 1,
    }
    return render(request, 'account/activity.html', context)


@login_required
def home(request):
    """
    Landing page shown after login.
    Displays a grid of all available apps.
    """
    apps = [
        {
            'name': 'Claims Manager',
            'description': 'Create, track and manage all insurance claims',
            'url': '/claims/',
            'icon': 'fas fa-folder-open',
            'color': '#3b82f6',
        },
        {
            'name': 'Scope Checklist',
            'description': 'Room-by-room scope of work checklists',
            'url': '/scope-checklist/',
            'icon': 'fas fa-clipboard-list',
            'color': '#10b981',
        },
        {
            'name': 'Lease Manager',
            'description': 'Manage leases, documents and ALE tracking',
            'url': '/lease-manager/',
            'icon': 'fas fa-file-contract',
            'color': '#8b5cf6',
        },
        {
            'name': 'Email Manager',
            'description': 'Send and schedule client emails',
            'url': '/emails/',
            'icon': 'fas fa-envelope',
            'color': '#f59e0b',
        },
        {
            'name': 'Box Labels',
            'description': 'Generate and print box labels for rooms',
            'url': '/labels/',
            'icon': 'fas fa-tags',
            'color': '#ef4444',
        },
        {
            'name': 'Wall Labels',
            'description': 'Generate directional wall labels',
            'url': '/labels/wall/',
            'icon': 'fas fa-compass',
            'color': '#ec4899',
        },
        {
            'name': 'Reading Browser',
            'description': 'Browse and manage moisture reading images',
            'url': '/readings/',
            'icon': 'fas fa-camera',
            'color': '#06b6d4',
        },
        {
            'name': 'Sensor Renamer',
            'description': 'AI-powered sensor image renaming tool',
            'url': '/sensor-renamer/',
            'icon': 'fas fa-microscope',
            'color': '#84cc16',
        },
        {
            'name': 'Equipment Checker',
            'description': 'Verify equipment documentation with AI',
            'url': '/equipment-checker/',
            'icon': 'fas fa-clipboard-check',
            'color': '#f97316',
        },
        {
            'name': 'Claim Images',
            'description': 'Download and organize claim photo sets',
            'url': '/claim-images/',
            'icon': 'fas fa-images',
            'color': '#64748b',
        },
        {
            'name': 'Encircle Dashboard',
            'description': 'View and sync Encircle claims data',
            'url': '/encircle/',
            'icon': 'fas fa-circle-nodes',
            'color': '#0ea5e9',
        },
        {
            'name': 'Push Rooms',
            'description': 'Push rooms to Encircle and copy photos',
            'url': '/claims/push-rooms/',
            'icon': 'fas fa-upload',
            'color': '#7c3aed',
        },
        {
            'name': 'Box Calculator',
            'description': 'Estimate box counts for pack-out jobs',
            'url': '/box-calculator/',
            'icon': 'fas fa-boxes',
            'color': '#d97706',
        },
        {
            'name': 'CPS Schedule of Loss',
            'description': 'AI-powered contents pricing from Encircle room photos',
            'url': '/cps-report/',
            'icon': 'fas fa-file-invoice-dollar',
            'color': '#059669',
        },
        {
            'name': 'Accounts Receivable',
            'description': 'Track contractor invoices and follow-up reminders',
            'url': '/ar-tracking/',
            'icon': 'fas fa-hand-holding-dollar',
            'color': '#0891b2',
        },
    ]
    return render(request, 'account/home.html', {'apps': apps})
