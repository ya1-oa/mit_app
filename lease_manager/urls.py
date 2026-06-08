from django.urls import path
from . import views
from . import signature_views as sv

app_name = 'lease_manager'

urlpatterns = [
    # ── Dashboard (list view) ────────────────────────────────────────────────
    path('', views.lease_manager, name='lease_manager'),

    # ── Lease CRUD / pipeline ────────────────────────────────────────────────
    path('create-draft/',             views.create_draft_lease,   name='create_draft_lease'),
    path('update-status/',            views.update_lease_status,  name='update_lease_status'),
    path('leases/<int:client_id>/',   views.get_leases_by_client, name='get_leases_by_client'),
    path('add-note/',                 views.add_lease_note,       name='add_lease_note'),
    path('activity-feed/',            views.lease_activity_feed,  name='lease_activity_feed'),
    path('save-landlord/',            views.save_landlord,        name='save_landlord'),
    path('generate-pdf/',             views.generate_document_from_html, name='generate_pdf'),

    # ── Document download / view ─────────────────────────────────────────────
    path('download/<uuid:document_id>/', views.download_lease_document, name='download_lease_document'),
    path('view/<uuid:document_id>/',     views.view_lease_document,     name='view_lease_document'),

    # ── ALE check + demand letter ────────────────────────────────────────────
    path('api/client/<int:client_id>/ale-check/',
         views.api_ale_check, name='api_ale_check'),
    path('lease/<uuid:lease_id>/demand-letter/',
         views.demand_letter_compose, name='demand_letter_compose'),

    # ── ALE import / prefill ─────────────────────────────────────────────────
    path('api/lease/<uuid:lease_id>/ale-import/',
         views.api_ale_import, name='api_ale_import'),
    path('api/client/<int:client_id>/ale-prefill/',
         views.api_ale_prefill, name='api_ale_prefill'),
    path('api/lease/<uuid:lease_id>/contacts/',
         views.api_lease_contacts, name='api_lease_contacts'),

    # ── Send document package (email) ────────────────────────────────────────
    path('lease/<uuid:lease_id>/send-package/',
         views.lease_send_package, name='lease_send_package'),

    # ── Workflow task tracking ───────────────────────────────────────────────
    path('task/<uuid:task_id>/update/',
         views.update_lease_task, name='update_lease_task'),

    # ════════════════════════════════════════════════════════════════════════
    # NEW: One-click generate + detail + e-signature system
    # ════════════════════════════════════════════════════════════════════════

    # One-click generate from a client/claim page
    path('client/<int:client_id>/quick-generate/',
         sv.quick_generate_lease, name='quick_generate_lease'),

    # Lease detail hub (internal, login required)
    path('lease/<uuid:lease_id>/',
         sv.lease_detail, name='lease_detail'),

    # Send for signature (POST JSON)
    path('lease/<uuid:lease_id>/send-for-signature/',
         sv.send_for_signature, name='send_for_signature'),

    # ── Public signing pages (no login required) ─────────────────────────────
    path('sign/<uuid:token>/',
         sv.sign_page, name='sign_page'),
    path('sign/<uuid:token>/submit/',
         sv.sign_submit, name='sign_submit'),
    path('sign/<uuid:token>/complete/',
         sv.sign_complete, name='sign_complete'),
    path('sign/<uuid:token>/decline/',
         sv.sign_decline, name='sign_decline'),
    path('sign/<uuid:token>/declined/',
         sv.sign_declined_page, name='sign_declined_page'),
]
