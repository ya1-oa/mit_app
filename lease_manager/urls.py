from django.urls import path
from . import views

urlpatterns = [
    # Main dashboard
    path('', views.lease_manager, name='lease_manager'),

    # Lease CRUD / pipeline
    path('create-draft/',             views.create_draft_lease,   name='create_draft_lease'),
    path('update-status/',            views.update_lease_status,  name='update_lease_status'),
    path('leases/<int:client_id>/',   views.get_leases_by_client, name='get_leases_by_client'),
    path('add-note/',                 views.add_lease_note,       name='add_lease_note'),
    path('activity-feed/',            views.lease_activity_feed,  name='lease_activity_feed'),
    path('save-landlord/',            views.save_landlord,        name='save_landlord'),
    path('generate-pdf/',             views.generate_document_from_html, name='generate_pdf'),

    # Document download / view
    path('download/<uuid:document_id>/', views.download_lease_document, name='download_lease_document'),
    path('view/<uuid:document_id>/',     views.view_lease_document,     name='view_lease_document'),

    # ── NEW: ALE import ─────────────────────────────────────────────────────
    # POST: import ALE fields into an existing lease
    path('api/lease/<uuid:lease_id>/ale-import/',
         views.api_ale_import, name='api_ale_import'),

    # GET: preview ALE data for a client (before import)
    path('api/client/<int:client_id>/ale-prefill/',
         views.api_ale_prefill, name='api_ale_prefill'),

    # GET: prioritised contact list for a lease
    path('api/lease/<uuid:lease_id>/contacts/',
         views.api_lease_contacts, name='api_lease_contacts'),

    # ── NEW: Send document package ───────────────────────────────────────────
    # GET renders compose page; POST sends immediately or schedules
    path('lease/<uuid:lease_id>/send-package/',
         views.lease_send_package, name='lease_send_package'),
]
