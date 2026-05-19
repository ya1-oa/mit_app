from django.urls import path
from . import views

urlpatterns = [
    path('', views.emails, name='emails'),
    path('track/<uuid:tracking_pixel_id>/', views.track_email_open, name='track_email_open'),
    path('schedule/create/', views.create_schedule, name='create_schedule'),
    path('api/documents/', views.document_list_api, name='document_list_api'),
]
