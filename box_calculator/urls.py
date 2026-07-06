from django.urls import path
from . import views

urlpatterns = [
    # Manual category-based calculator
    path('', views.calculator_home, name='calculator_home'),
    path('report/<int:session_id>/', views.report_view, name='box_calc_report'),

    # Manual calculator API
    path('api/rooms/<int:client_id>/', views.api_client_rooms, name='api_client_rooms'),
    path('api/calculate/', views.api_calculate, name='box_calc_calculate'),
    path('api/defaults/', views.api_defaults, name='box_calc_defaults'),
    path('api/ai-analyze/', views.api_ai_analyze, name='box_calc_ai_analyze'),
    path('api/save/', views.api_save_session, name='api_save_session'),
    path('api/analyze-pdf/', views.api_pdf_to_cps_session, name='api_analyze_pdf'),
    path('api/auto-from-encircle/', views.api_auto_from_encircle, name='api_auto_from_encircle'),

    # CPS — AI image-based box count estimation (300-series rooms)
    path('cps/', views.cps_home, name='cps_home'),
    path('cps/session/<int:client_id>/', views.cps_session, name='cps_session'),
    path('cps/upload/', views.cps_upload_room, name='cps_upload_room'),
    path('cps/status/<str:task_id>/', views.cps_task_status, name='cps_task_status'),
    path('cps/report/<int:session_id>/', views.cps_report, name='cps_report'),
    path('cps/export/<int:session_id>/', views.cps_export_excel, name='cps_export_excel'),
    path('cps/pdf/<int:session_id>/', views.cps_export_pdf, name='cps_export_pdf'),
    path('cps/room/<int:room_id>/update/', views.cps_update_room, name='cps_update_room'),
    path('cps/room/<int:room_id>/delete/', views.cps_delete_room, name='cps_delete_room'),
]
