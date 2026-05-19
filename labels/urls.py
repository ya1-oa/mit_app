from django.urls import path
from . import views

urlpatterns = [
    # Box labels
    path('', views.labels, name='labels'),
    path('<str:claim_id>/download-all/', views.generate_combined_labels, name='generate_combined_labels'),
    path('email-to-group/', views.email_labels_to_group, name='email_labels_to_group'),

    # Wall labels
    path('wall/', views.wall_labels, name='wall_labels'),
    path('wall/<str:claim_id>/download-all/', views.generate_wall_labels_download, name='generate_wall_labels_download'),
]
