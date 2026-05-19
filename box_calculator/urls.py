from django.urls import path
from . import views

urlpatterns = [
    path('', views.calculator_home, name='box_calculator'),
    path('report/<int:session_id>/', views.report_view, name='box_calc_report'),

    # API endpoints
    path('api/rooms/<int:client_id>/', views.api_client_rooms, name='box_calc_rooms'),
    path('api/calculate/', views.api_calculate, name='box_calc_calculate'),
    path('api/defaults/', views.api_defaults, name='box_calc_defaults'),
    path('api/ai-analyze/', views.api_ai_analyze, name='box_calc_ai_analyze'),
    path('api/save/', views.api_save_session, name='box_calc_save'),
]
