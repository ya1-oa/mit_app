from django.urls import path
from . import views

urlpatterns = [
    # Dashboard
    path('', views.encircle_claims_dashboard, name='encircle_dashboard'),
    path('portfolio/', views.portfolio_summary, name='portfolio_summary'),

    # Dimensions
    path('dimensions/<int:claim_id>/', views.fetch_dimensions_API, name='fetch_dimensions_API'),

    # Claims API
    path('api/claims/', views.fetch_all_claims_api, name='fetch_all_claims_api'),
    path('api/claims/export/', views.export_claims_to_excel, name='export_all_claims'),
    path('api/claims/export/<int:claim_id>/', views.export_claims_to_excel, name='export_single_claim'),
    path('api/claims/<int:claim_id>/', views.fetch_claim_details_api, name='fetch_claim_details_api'),
    path('api/claims/<int:claim_id>/structures/<int:structure_id>/rooms/', views.fetch_claim_rooms_api, name='fetch_claim_rooms_api'),

    # Sync
    path('sync/', views.sync_encircle_onedrive, name='sync_cached'),
    path('sync/refresh/', views.sync_encircle_onedrive_refresh, name='sync_refresh'),
    path('sync/export/encircle/', views.export_encircle_csv, name='export_encircle_csv'),
    path('sync/export/onedrive/', views.export_onedrive_csv, name='export_onedrive_csv'),

    # Webhooks
    path('webhooks/', views.encircle_webhook, name='encircle_webhook'),
    path('webhooks/test/', views.encircle_webhook_test, name='encircle_webhook_test'),

    # Room automation
    path('api/automate/', views.generate_room_entries_from_configs, name='encircle_automate'),
]
