from django.urls import path
from . import views

urlpatterns = [
    path('', views.cps_home, name='cps_report_home'),
    path('session/<int:session_id>/', views.session_view, name='cps_report_session'),
    path('session/<int:session_id>/progress/', views.session_progress, name='cps_report_progress'),
    path('session/<int:session_id>/export/', views.export_excel, name='cps_report_export'),
    path('session/<int:session_id>/export-pdf/', views.export_pdf, name='cps_report_export_pdf'),
    path('session/<int:session_id>/export-photo-pdf/', views.export_photo_pdf, name='cps_report_export_photo_pdf'),
    path('session/<int:session_id>/regenerate-photo-pdf/', views.regenerate_photo_pdf, name='cps_regenerate_photo_pdf'),
    path('session/<int:session_id>/photo-pdf-status/', views.photo_pdf_status_api, name='cps_photo_pdf_status'),
    path('session/<int:session_id>/summary/', views.session_summary, name='cps_report_summary'),
    path('session/<int:session_id>/pricing-audit/', views.pricing_audit_view, name='cps_pricing_audit'),
    path('session/<int:session_id>/summary/pdf/', views.export_summary_pdf, name='cps_report_summary_pdf'),
    path('session/<int:session_id>/summary/excel/', views.export_summary_excel, name='cps_report_summary_excel'),
    path('session/<int:session_id>/share-link/', views.get_share_link, name='cps_share_link'),
    path('session/<int:session_id>/room/<int:room_id>/share-link/', views.get_room_share_link, name='cps_room_share_link'),
    path('session/<int:session_id>/cancel/', views.api_cancel_session, name='cps_cancel_session'),
    path('session/<int:session_id>/rerun/', views.api_rerun_session, name='cps_rerun_session'),
    path('session/<int:session_id>/clear-signatures/', views.api_clear_signatures, name='cps_clear_signatures'),
    path('session/<int:session_id>/room/<int:room_id>/clear-signature/', views.api_clear_room_signature, name='cps_clear_room_signature'),

    # Public client signature page (no login required)
    path('sign/<uuid:token>/', views.sign_session, name='cps_sign_session'),
    path('sign/<uuid:token>/sign-room/', views.api_sign_room, name='cps_api_sign_room'),
    # Per-room signature links — client sees only that one room
    path('sign/room/<uuid:token>/', views.sign_room_direct, name='cps_sign_room_direct'),
    path('sign/room/<uuid:token>/sign-room/', views.api_sign_room_direct, name='cps_api_sign_room_direct'),

    # API
    path('api/clients/', views.api_search_clients, name='cps_api_clients'),
    path('api/rooms/', views.api_fetch_rooms, name='cps_api_fetch_rooms'),
    path('api/start/', views.api_start_session, name='cps_api_start'),
    path('api/process-room/', views.api_process_room, name='cps_api_process_room'),
    path('api/save-room/', views.api_save_room_items, name='cps_api_save_room'),
    path('api/session/<int:session_id>/status/', views.api_session_status, name='cps_api_status'),
    path('api/session/<int:session_id>/logs/', views.api_session_logs, name='cps_api_logs'),
    path('api/room/<int:room_id>/items/', views.api_room_items, name='cps_api_room_items'),
    path('api/reassign-photo/', views.api_reassign_photo, name='cps_api_reassign_photo'),

    # Import a previously exported Schedule of Loss Excel file
    path('api/import-excel/', views.api_import_excel, name='cps_api_import_excel'),

    # Diagnostic — shows raw Encircle media breakdown per room for a claim
    path('api/debug/media/<str:claim_id>/', views.api_debug_claim_media, name='cps_api_debug_media'),
]
