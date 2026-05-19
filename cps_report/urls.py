from django.urls import path
from . import views

urlpatterns = [
    path('', views.cps_home, name='cps_report_home'),
    path('session/<int:session_id>/', views.session_view, name='cps_report_session'),
    path('session/<int:session_id>/progress/', views.session_progress, name='cps_report_progress'),
    path('session/<int:session_id>/export/', views.export_excel, name='cps_report_export'),
    path('session/<int:session_id>/export-pdf/', views.export_pdf, name='cps_report_export_pdf'),
    path('session/<int:session_id>/share-link/', views.get_share_link, name='cps_share_link'),
    path('session/<int:session_id>/clear-signatures/', views.api_clear_signatures, name='cps_clear_signatures'),
    path('session/<int:session_id>/room/<int:room_id>/clear-signature/', views.api_clear_room_signature, name='cps_clear_room_signature'),

    # Public client signature page (no login required)
    path('sign/<uuid:token>/', views.sign_session, name='cps_sign_session'),
    path('sign/<uuid:token>/sign-room/', views.api_sign_room, name='cps_api_sign_room'),

    # API
    path('api/clients/', views.api_search_clients, name='cps_api_clients'),
    path('api/start/', views.api_start_session, name='cps_api_start'),
    path('api/process-room/', views.api_process_room, name='cps_api_process_room'),
    path('api/save-room/', views.api_save_room_items, name='cps_api_save_room'),
    path('api/session/<int:session_id>/status/', views.api_session_status, name='cps_api_status'),
    path('api/room/<int:room_id>/items/', views.api_room_items, name='cps_api_room_items'),

    # Import a previously exported Schedule of Loss Excel file
    path('api/import-excel/', views.api_import_excel, name='cps_api_import_excel'),

    # Diagnostic — shows raw Encircle media breakdown per room for a claim
    path('api/debug/media/<str:claim_id>/', views.api_debug_claim_media, name='cps_api_debug_media'),
]
