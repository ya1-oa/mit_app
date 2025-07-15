from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name="dashboard"),
    path('checklist/', views.checklist, name="checklist"),
    path('update_checklist/', views.update_checklist, name='update_checklist'),
    path('create/', views.create, name="create"),
    path('update_checklist_item/<int:item_id>/', views.update_checklist_item, name='update_checklist_item'),
    path('generate_invoice_pdf/<int:client_id>/', views.generate_invoice_pdf, name="generate_invoice_pdf"),
    path('statistics/', views.statistics, name="statistics"),
    path('logout/', views.logout_view, name='logout'),
    path('emails/', views.emails, name='emails'),
    path('labels/', views.labels, name='labels'),
    path('generate_documents/', views.client_list, name='client_list'),
    path('generate_pdf/', views.generate_document_from_html, name='generate_pdf'),
    path('encircle/', views.encircle_claims_dashboard, name='encircle_dashboard'),
    path('fetch_dimensions_API/<int:claim_id>/', views.fetch_dimensions_API, name='fetch_dimensions_API'),
    path('api/encircle/claims/', views.fetch_all_claims_api, name='fetch_all_claims_api'),
    path('api/encircle/claims/<int:claim_id>/', views.fetch_claim_details_api, name='fetch_claim_details_api'),
    path('api/encircle/claims/<int:claim_id>/rooms/', views.fetch_claim_rooms_api, name='fetch_claim_rooms_api'),
    path('api/encircle/claims/export/', views.export_claims_to_excel, name='export_all_claims'),
    path('api/encircle/claims/export/<int:claim_id>/', views.export_claims_to_excel, name='export_single_claim'),
    path('download-media/', views.download_media_view, name='download_media'),
    path('save-landlord/', views.save_landlord, name='save_landlord'),
    #path('download-status/', views.download_status_view, name='download_status')
]