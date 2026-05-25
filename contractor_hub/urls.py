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

    # Contractor registry
    path('contractors/', views.contractor_list, name='contractor_list'),
    path('contractors/new/', views.contractor_create, name='contractor_create'),
    path('contractors/<int:pk>/edit/', views.contractor_edit, name='contractor_edit'),

    # JSON API — live totals and line item management
    path('api/estimate/<uuid:pk>/totals/', views.api_estimate_totals, name='api_estimate_totals'),
    path('api/lineitem/add/', views.api_lineitem_add, name='api_lineitem_add'),
    path('api/lineitem/<int:pk>/update/', views.api_lineitem_update, name='api_lineitem_update'),
    path('api/lineitem/<int:pk>/delete/', views.api_lineitem_delete, name='api_lineitem_delete'),
]
