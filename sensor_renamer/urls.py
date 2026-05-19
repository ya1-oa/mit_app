from django.urls import path
from . import views

urlpatterns = [
    path('', views.sensor_image_renamer, name='sensor_image_renamer'),
    path('guide/', views.guide_sensor_renamer, name='guide_sensor_renamer'),
    path('upload/', views.sensor_upload, name='sensor_upload'),
    path('status/', views.sensor_task_status, name='sensor_task_status'),
    path('download/<str:session_id>/', views.sensor_download_zip, name='sensor_download_zip'),
    path('download/<str:session_id>/<str:subfolder>/', views.sensor_download_subfolder, name='sensor_download_subfolder'),
    path('browse/<str:session_id>/', views.sensor_browse_session, name='sensor_browse_session'),
    path('correct/<str:session_id>/', views.sensor_correct, name='sensor_correct'),
]
