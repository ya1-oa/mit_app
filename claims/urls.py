from django.urls import path
from . import views

urlpatterns = [
    # List & detail
    path('', views.claim_list, name='claim_list'),
    path('<int:claim_id>/', views.claim_detail, name='claim_detail'),

    # Create wizard
    path('create/', views.create_claim_combined, name='create_claim_combined'),
    path('create/step1/', views.create_claim_step1, name='create_claim_step1'),
    path('create/step2/', views.create_claim_step2, name='create_claim_step2'),
    path('create/step3/', views.create_claim_step3, name='create_claim_step3'),
    path('create/cancel/', views.cancel_claim_creation, name='cancel_claim_creation'),

    # AJAX helpers
    path('ajax/load-rooms/', views.load_rooms_from_claim, name='load_rooms_from_claim'),
    path('ajax/save-rooms/', views.save_rooms, name='save_rooms'),

    # Update
    path('<int:claim_id>/update/', views.update_claim, name='update_claim'),

    # Task status
    path('task-status/', views.claim_task_status, name='claim_task_status'),
    path('send-room-list/', views.send_room_list_from_claim, name='send_room_list_from_claim'),

    # Encircle integration
    path('<int:claim_id>/push-to-encircle/', views.push_to_encircle, name='push_to_encircle'),
    path('<int:claim_id>/push-rooms-to-encircle/', views.push_rooms_to_encircle, name='push_rooms_to_encircle'),
    path('<int:claim_id>/preview-rooms/', views.preview_rooms_entries, name='preview_rooms_entries'),
    path('push-rooms/', views.push_rooms_page, name='push_rooms_page'),
    path('migrate-encircle-rooms/', views.migrate_encircle_rooms, name='migrate_encircle_rooms'),
    path('duplicate-encircle-claim/', views.duplicate_encircle_claim, name='duplicate_encircle_claim'),
    path('pushed-rooms/', views.get_pushed_rooms, name='get_pushed_rooms'),
    path('delete-pushed-rooms/', views.delete_pushed_rooms, name='delete_pushed_rooms'),

    # Folder browser
    path('<int:claim_id>/folder-structure/', views.get_folder_structure, name='get_folder_structure'),
    path('<int:claim_id>/download/', views.download_claim_file, name='download_claim_file'),
    path('<int:claim_id>/download-folder/', views.download_claim_folder, name='download_claim_folder'),
    path('<int:claim_id>/download-selected/', views.download_selected_files, name='download_selected_files'),
    path('<int:claim_id>/upload/', views.upload_claim_file, name='upload_claim_file'),
    path('<int:claim_id>/regenerate-templates/', views.regenerate_templates, name='regenerate_templates'),
    path('<int:claim_id>/delete-file/', views.delete_claim_file, name='delete_claim_file'),
    path('<int:claim_id>/move-file/', views.move_claim_file, name='move_claim_file'),

    # Room manager
    path('room-manager-load/', views.room_manager_load, name='room_manager_load'),
    path('room-manager-rename/', views.room_manager_rename, name='room_manager_rename'),
    path('room-manager-add/', views.room_manager_add, name='room_manager_add'),
    path('room-manager-delete/', views.room_manager_delete_room, name='room_manager_delete_room'),
    path('room-manager-extract-700s/', views.room_manager_extract_700s, name='room_manager_extract_700s'),
    path('bulk-rename-db-rooms/', views.bulk_rename_db_rooms, name='bulk_rename_db_rooms'),

    # Data & audit
    path('data-check/', views.data_check_audit, name='data_check_audit'),
    path('encircle-photo-folders/', views.encircle_photo_folders, name='encircle_photo_folders'),
    path('encircle-claim-rooms/', views.encircle_claim_rooms_with_photos, name='encircle_claim_rooms_with_photos'),
    path('upload-label-photos-to-room/', views.upload_label_photos_to_room, name='upload_label_photos_to_room'),

    # Room generator API
    path('api/for-room-generator/', views.get_claims_for_room_generator, name='get_claims_for_room_generator'),
    path('api/rooms/', views.get_rooms_for_generator, name='get_rooms_for_generator'),
    path('api/encircle/simple/', views.encircle_claims_simple, name='encircle_claims_simple'),

    # Misc
    path('api/send-room-list-email/', views.send_room_list_email, name='claims_send_room_list_email'),
    path('api/import-client-with-rooms/', views.import_client_with_rooms_formula_support, name='claims_import_client_with_rooms'),

    # Claim Files — per-claim file browser page + link emailer
    path('<int:claim_id>/files/', views.claim_files_page, name='claim_files_page'),
    path('<int:claim_id>/send-files-link/', views.send_files_link_email, name='send_files_link_email'),

    # Excel Hub — standalone Excel file browser / emailer
    path('excel-hub/', views.excel_hub, name='excel_hub'),
    path('excel-hub/api/', views.excel_hub_api, name='excel_hub_api'),
    path('excel-hub/download-all/', views.excel_hub_download_all_zip, name='excel_hub_download_all'),
    path('excel-hub/settings/', views.excel_hub_settings, name='excel_hub_settings'),
    path('excel-hub/<int:claim_id>/download/', views.excel_hub_download_zip, name='excel_hub_download_zip'),
    path('excel-hub/<int:claim_id>/send-email/', views.excel_hub_send_email, name='excel_hub_send_email'),

    # Internal templates page — login required, linked from claim detail
    path('<int:claim_id>/templates/', views.claim_templates_page, name='claim_templates_page'),

    # Public templates download — no login, signed token identifies the claim
    path('templates/<str:token>/', views.claim_templates_public, name='claim_templates_public'),
    path('templates/<str:token>/download/<path:file_path>', views.claim_templates_download, name='claim_templates_download'),
]
