from django.urls import path
from . import views
from . import claims_views

urlpatterns = [
    # Claims Management (Server-based)
    path('claims/', claims_views.claim_list, name='claim_list'),
    path('claims/<int:claim_id>/', claims_views.claim_detail, name='claim_detail'),
    path('claims/create/', claims_views.create_claim_combined, name='create_claim_combined'),
    path('claims/create/step1/', claims_views.create_claim_step1, name='create_claim_step1'),
    path('claims/create/step2/', claims_views.create_claim_step2, name='create_claim_step2'),
    path('claims/create/step3/', claims_views.create_claim_step3, name='create_claim_step3'),
    path('claims/create/cancel/', claims_views.cancel_claim_creation, name='cancel_claim_creation'),
    path('claims/ajax/load-rooms/', claims_views.load_rooms_from_claim, name='load_rooms_from_claim'),
    path('claims/ajax/save-rooms/', claims_views.save_rooms, name='save_rooms'),
    # REMOVED: OneDrive sync URLs no longer needed with server-side storage
    # path('claims/<int:claim_id>/sync/from-onedrive/', ...) - REMOVED
    # path('claims/<int:claim_id>/sync/to-onedrive/', ...) - REMOVED
    path('claims/<int:claim_id>/update/', claims_views.update_claim, name='update_claim'),

    # Room Generator API endpoints
    path('api/claims/for-room-generator/', claims_views.get_claims_for_room_generator, name='get_claims_for_room_generator'),
    path('api/claims/rooms/', claims_views.get_rooms_for_generator, name='get_rooms_for_generator'),

    # Folder Browser API endpoints
    path('claims/<int:claim_id>/folder-structure/', claims_views.get_folder_structure, name='get_folder_structure'),
    path('claims/<int:claim_id>/download/', claims_views.download_claim_file, name='download_claim_file'),
    path('claims/<int:claim_id>/download-folder/', claims_views.download_claim_folder, name='download_claim_folder'),
    path('claims/<int:claim_id>/upload/', claims_views.upload_claim_file, name='upload_claim_file'),
    path('claims/<int:claim_id>/regenerate-templates/', claims_views.regenerate_templates, name='regenerate_templates'),
    path('claims/<int:claim_id>/delete-file/', claims_views.delete_claim_file, name='delete_claim_file'),
    path('claims/<int:claim_id>/move-file/', claims_views.move_claim_file, name='move_claim_file'),
    path('claims/data-check/', claims_views.data_check_audit, name='data_check_audit'),

    # Original views
    path('', views.dashboard, name="dashboard"),
    path('checklist/', views.checklist, name="checklist"),
    path('api/client-details/<int:client_id>/', views.api_client_details, name='api_client_details'),
    path('update_checklist/', views.update_checklist, name='update_checklist'),
    path('create/', views.create, name="create"),
    #path('update_checklist_item/<int:item_id>/', views.update_checklist_item, name='update_checklist_item'),
    path('generate_invoice_pdf/<int:client_id>/', views.generate_invoice_pdf, name="generate_invoice_pdf"),
    path('statistics/', views.statistics, name="statistics"),
    path('logout/', views.logout_view, name='logout'),
    path('emails/', views.emails, name='emails'),
    path('emails/track/<uuid:tracking_pixel_id>/', views.track_email_open, name='track_email_open'),
    path('emails/schedule/create/', views.create_schedule, name='create_schedule'),
    path('api/documents/', views.document_list_api, name='document_list_api'),
    path('labels/', views.labels, name='labels'),
    path('wall-labels/', views.wall_labels, name='wall_labels'),
    path('clients/', views.client_list, name='client_list'),
    path('generate_pdf/', views.generate_document_from_html, name='generate_pdf'),
    path('encircle/', views.encircle_claims_dashboard, name='encircle_dashboard'),
    path('fetch_dimensions_API/<int:claim_id>/', views.fetch_dimensions_API, name='fetch_dimensions_API'),
    path('api/encircle/claims/', views.fetch_all_claims_api, name='fetch_all_claims_api'),
    path('api/encircle/claims/<int:claim_id>/', views.fetch_claim_details_api, name='fetch_claim_details_api'),
    path('api/encircle/claims/<int:claim_id>/rooms/', views.fetch_claim_rooms_api, name='fetch_claim_rooms_api'),
    path('api/encircle/claims/export/', views.export_claims_to_excel, name='export_all_claims'),
    path('api/encircle/claims/export/<int:claim_id>/', views.export_claims_to_excel, name='export_single_claim'),
    path('download-media/', views.download_media_view, name='download_media'),
    path('save-landlord/', views.save_landlord, name='save_landlord'),
    path('generate-data-report/', views.generate_data_report, name='generate_data_report'),
    path('api/automate/', views.generate_room_entries_from_configs, name='automate'),
    path('api/get-all-clients/', views.get_all_clients, name='get_all_clients'),
    path('api/send-room-list-email/', views.send_room_list_email, name='send_room_list_email'),
    path('readings/', views.reading_browser, name='reading_browser'),
    path('readings/upload/', views.upload_readings, name='upload_readings'),
    path('readings/sorted/', views.get_sorted_readings, name='get_sorted_readings'),
    path('readings/export/', views.export_readings, name='export_readings'),
    path('readings/delete/<int:image_id>/', views.delete_reading, name='delete_reading'),
    path('readings/rename/<int:image_id>/', views.rename_reading, name='rename_reading'),
    path('api/import-client-with-rooms/', views.import_client_with_rooms_formula_support, name='import_client_with_rooms'),
    path('api/claim-images/structured-shared', views.list_claim_images_shared),
    path('sync/', views.sync_encircle_onedrive, name='sync_cached'),
    path('sync/refresh/', views.sync_encircle_onedrive_refresh, name='sync_refresh'),
    path('sync/export/encircle/', views.export_encircle_csv, name='export_encircle_csv'),
    path('sync/export/onedrive/', views.export_onedrive_csv, name='export_onedrive_csv'),
    path('generate-all-documents/', views.generate_all_documents, name='generate_all_documents'),

    # Lease Manager Dashboard
    path('lease-manager/', views.lease_manager, name='lease_manager'),
    path('lease-manager/create-draft/', views.create_draft_lease, name='create_draft_lease'),
    path('lease-manager/update-status/', views.update_lease_status, name='update_lease_status'),
    path('lease-manager/leases/<int:client_id>/', views.get_leases_by_client, name='get_leases_by_client'),
    path('lease-manager/download/<uuid:document_id>/', views.download_lease_document, name='download_lease_document'),
    path('lease-manager/view/<uuid:document_id>/', views.view_lease_document, name='view_lease_document'),
    path('lease-manager/add-note/', views.add_lease_note, name='add_lease_note'),
    path('lease-manager/activity-feed/', views.lease_activity_feed, name='lease_activity_feed'),

    # Encircle Webhooks
    path('webhooks/encircle/', views.encircle_webhook, name='encircle_webhook'),
    path('webhooks/encircle/test/', views.encircle_webhook_test, name='encircle_webhook_test'),

    # Scope Checklist
    path('scope-checklist/', views.scope_checklist, name='scope_checklist'),
    path('api/scope-checklist/rooms/<int:claim_id>/', views.scope_checklist_get_rooms, name='scope_checklist_get_rooms'),
    path('api/scope-checklist/save/', views.scope_checklist_save, name='scope_checklist_save'),
    path('api/scope-checklist/generate-pdf/', views.scope_checklist_generate_pdf, name='scope_checklist_generate_pdf'),
    path('api/scope-checklist/send-email/', views.scope_checklist_send_email, name='scope_checklist_send_email'),
]