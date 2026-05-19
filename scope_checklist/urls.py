from django.urls import path
from . import views

urlpatterns = [
    path('', views.scope_checklist, name='scope_checklist'),
    path('rooms/<int:claim_id>/', views.scope_checklist_get_rooms, name='scope_checklist_get_rooms'),
    path('save/', views.scope_checklist_save, name='scope_checklist_save'),
    path('generate-pdf/', views.scope_checklist_generate_pdf, name='scope_checklist_generate_pdf'),
    path('send-email/', views.scope_checklist_send_email, name='scope_checklist_send_email'),
]
