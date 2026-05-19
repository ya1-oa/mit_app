from django.urls import path
from . import views

urlpatterns = [
    path('', views.equipment_checker, name='equipment_checker'),
    path('upload/', views.equipment_upload, name='equipment_upload'),
    path('status/', views.equipment_task_status, name='equipment_task_status'),
    path('export-csv/', views.equipment_export_csv, name='equipment_export_csv'),
    path('guide/', views.guide_equipment_checker, name='guide_equipment_checker'),
]
