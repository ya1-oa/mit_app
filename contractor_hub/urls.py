from django.urls import path
from . import views

app_name = 'contractor_hub'

urlpatterns = [
    # Dashboard — list all estimates
    path('', views.dashboard, name='dashboard'),

    # Estimate CRUD
    path('new/', views.estimate_create, name='estimate_create'),
    path('<uuid:pk>/', views.estimate_detail, name='estimate_detail'),
    path('<uuid:pk>/edit/', views.estimate_edit, name='estimate_edit'),

    # Document generation
    path('<uuid:pk>/pdf/', views.estimate_pdf, name='estimate_pdf'),
    path('<uuid:pk>/excel/', views.estimate_excel, name='estimate_excel'),

    # Sections
    path('<uuid:pk>/section/<int:section_pk>/', views.section_detail, name='section_detail'),
    path('<uuid:pk>/section/<int:section_pk>/import-cps/', views.section_import_cps, name='section_import_cps'),
    path('<uuid:pk>/section/<int:section_pk>/invoice/', views.section_invoice_pdf, name='section_invoice_pdf'),

    # Quick sub invoice generator (3-input: client + sub + work type)
    path('quick-invoice/', views.quick_sub_invoice, name='quick_sub_invoice'),
    path('clients/<int:pk>/box-counts/', views.box_count_report, name='box_count_report'),

    # Contractor registry
    path('contractors/', views.contractor_list, name='contractor_list'),
    path('contractors/new/', views.contractor_create, name='contractor_create'),
    path('contractors/<int:pk>/edit/', views.contractor_edit, name='contractor_edit'),

    # Price list import / history
    path('prices/import/', views.price_list_import, name='price_list_import'),
    path('prices/history/', views.price_list_history, name='price_list_history'),

    # JSON API — live totals and line item management
    path('api/stats/', views.api_stats, name='api_stats'),
    path('api/estimate/<uuid:pk>/totals/', views.api_estimate_totals, name='api_estimate_totals'),
    path('api/lineitem/add/', views.api_lineitem_add, name='api_lineitem_add'),
    path('api/lineitem/<int:pk>/update/', views.api_lineitem_update, name='api_lineitem_update'),
    path('api/lineitem/<int:pk>/delete/', views.api_lineitem_delete, name='api_lineitem_delete'),
]
