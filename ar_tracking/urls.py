from django.urls import path

from . import views

app_name = 'ar_tracking'

urlpatterns = [
    path('', views.ar_board, name='board'),
    path('templates/api/', views.ar_template_api, name='template_api'),
    path('<uuid:estimate_id>/', views.ar_detail, name='detail'),
    path('<uuid:estimate_id>/note/', views.ar_add_note, name='add_note'),
    path('<uuid:estimate_id>/mark-status/', views.ar_mark_status, name='mark_status'),
    path('<uuid:estimate_id>/schedule-followup/', views.ar_schedule_followup, name='schedule_followup'),
]
