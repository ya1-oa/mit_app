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

    # PPR — AI image-based box count estimation
    path('ppr/', views.ppr_home, name='ppr_home'),
    path('ppr/session/<int:client_id>/', views.ppr_session, name='ppr_session'),
    path('ppr/upload/', views.ppr_upload_room, name='ppr_upload_room'),
    path('ppr/status/<str:task_id>/', views.ppr_task_status, name='ppr_task_status'),
    path('ppr/report/<int:session_id>/', views.ppr_report, name='ppr_report'),
    path('ppr/export/<int:session_id>/', views.ppr_export_excel, name='ppr_export_excel'),
    path('ppr/room/<int:room_id>/update/', views.ppr_update_room, name='ppr_update_room'),
    path('ppr/room/<int:room_id>/delete/', views.ppr_delete_room, name='ppr_delete_room'),
]
