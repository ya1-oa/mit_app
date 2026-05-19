from django.urls import path
from . import views

urlpatterns = [
    # Home — app grid landing page (shown after login)
    path('', views.home, name='home'),

    # Dashboard — statistics & claims overview
    path('dashboard/', views.dashboard, name='dashboard'),

    # Auth
    path('logout/', views.logout_view, name='logout'),

    # Legacy / misc
    path('checklist/', views.checklist, name='checklist'),
    path('update_checklist/', views.update_checklist, name='update_checklist'),
    path('create/', views.create, name='create'),
    path('statistics/', views.statistics, name='statistics'),
    path('clients/', views.client_list, name='client_list'),
    path('generate_invoice_pdf/<int:client_id>/', views.generate_invoice_pdf, name='generate_invoice_pdf'),
    path('generate-all-documents/', views.generate_all_documents, name='generate_all_documents'),
    path('generate-data-report/', views.generate_data_report, name='generate_data_report'),

    # API helpers
    path('api/client-details/<int:client_id>/', views.api_client_details, name='api_client_details'),
    path('api/get-all-clients/', views.get_all_clients, name='get_all_clients'),
    path('api/send-room-list-email/', views.send_room_list_email, name='send_room_list_email'),
    path('api/import-client-with-rooms/', views.import_client_with_rooms_formula_support, name='import_client_with_rooms'),
    path('api/automate/', views.generate_room_entries_from_configs, name='automate'),
]
