from django.urls import path
from . import views

urlpatterns = [
    path('', views.emails, name='emails'),

    # Tracking pixel — no login, called by remote email clients
    path('track/<uuid:tracking_pixel_id>/', views.track_email_open, name='track_email_open'),

    path('schedule/create/', views.create_schedule, name='create_schedule'),

    # JSON APIs — documents + claim contacts
    path('api/documents/', views.document_list_api, name='document_list_api'),
    path('api/claim/<int:claim_pk>/contacts/', views.api_claim_contacts, name='api_claim_contacts'),

    # Campaign APIs
    path('api/campaign/preview/', views.api_campaign_preview, name='api_campaign_preview'),
    path('api/campaign/confirm/', views.api_campaign_confirm, name='api_campaign_confirm'),
    path('api/campaign/<uuid:campaign_id>/cancel/', views.api_campaign_cancel, name='api_campaign_cancel'),
]
