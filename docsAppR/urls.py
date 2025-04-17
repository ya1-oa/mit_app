from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name=""),
    path('checklist/', views.checklist, name="checklist"),
    path('create/', views.create, name="create"),
    path('dashboard/', views.dashboard, name="dashboard"),
    path('createpdfs/', views.client_list, name="client_list"),
    path("generate_invoice_pdf/<int:client_id>/", views.generate_invoice_pdf, name="generate_invoice_pdf"),
    path('logout/', views.logout_view, name='logout'),
    path('emails/', views.emails, name='emails'),
    path('labels/', views.labels, name='labels'),
    path('encircle/', views.get_dimensions, name='get_dimensions')
]