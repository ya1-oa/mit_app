from django.urls import path
from . import views

urlpatterns = [
    path('', views.lease_manager, name='lease_manager'),
    path('create-draft/', views.create_draft_lease, name='create_draft_lease'),
    path('update-status/', views.update_lease_status, name='update_lease_status'),
    path('leases/<int:client_id>/', views.get_leases_by_client, name='get_leases_by_client'),
    path('download/<uuid:document_id>/', views.download_lease_document, name='download_lease_document'),
    path('view/<uuid:document_id>/', views.view_lease_document, name='view_lease_document'),
    path('add-note/', views.add_lease_note, name='add_lease_note'),
    path('activity-feed/', views.lease_activity_feed, name='lease_activity_feed'),
    path('save-landlord/', views.save_landlord, name='save_landlord'),
    path('generate-pdf/', views.generate_document_from_html, name='generate_pdf'),
]
