"""
Claims Manager app views.
Imports all claim-related views from docsAppR.
"""
from docsAppR.claims_views import (
    claim_list,
    claim_detail,
    create_claim_step1,
    create_claim_step2,
    create_claim_step3,
    create_claim_combined,
    cancel_claim_creation,
    load_rooms_from_claim,
    save_rooms,
    update_claim,
    claim_task_status,
    send_room_list_from_claim,
    push_to_encircle,
    push_rooms_to_encircle,
    preview_rooms_entries,
    push_rooms_page,
    migrate_encircle_rooms,
    duplicate_encircle_claim,
    get_pushed_rooms,
    delete_pushed_rooms,
    get_folder_structure,
    download_claim_file,
    download_claim_folder,
    download_selected_files,
    upload_claim_file,
    delete_claim_file,
    move_claim_file,
    regenerate_templates,
    data_check_audit,
    encircle_photo_folders,
    encircle_claim_rooms_with_photos,
    upload_label_photos_to_room,
    room_manager_load,
    room_manager_rename,
    room_manager_add,
    room_manager_delete_room,
    room_manager_extract_700s,
    bulk_rename_db_rooms,
    get_claims_for_room_generator,
    get_rooms_for_generator,
    encircle_claims_simple,
    # Encircle inbound sync
    trigger_encircle_sync,
    encircle_sync_status_api,
    # Claim Files page
    claim_files_page,
    send_files_link_email,
    # Excel Hub
    excel_hub,
    excel_hub_api,
    excel_hub_download_zip,
    excel_hub_download_all_zip,
    excel_hub_send_email,
    excel_hub_settings,
    # Public templates download page (no login — signed token)
    claim_templates_public,
    claim_templates_download,
    # Internal templates page (login required)
    claim_templates_page,
)

from docsAppR.views import (
    send_room_list_email,
    import_client_with_rooms_formula_support,
)
