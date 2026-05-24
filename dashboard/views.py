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
            'name': 'Excel Hub',
            'description': 'Download and email Xactimate Excel reports per claim',
            'url': '/claims/excel-hub/',
            'icon': 'fas fa-file-excel',
            'color': '#16a34a',
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
    ]
    return render(request, 'account/home.html', {'apps': apps})
