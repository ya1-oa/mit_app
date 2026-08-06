from django.urls import path
from . import views

app_name = 'mit_audit'

urlpatterns = [
    # Dashboard
    path('',                              views.dashboard,         name='dashboard'),
    # Audit detail
    path('<int:audit_id>/',               views.audit_detail,      name='audit_detail'),
    # Start a new audit
    path('trigger/',                      views.trigger_audit,     name='trigger_audit'),
    # Approve / update dimensions
    path('<int:audit_id>/approve/',       views.approve_dimensions, name='approve_dimensions'),
    # Live status (AJAX polling)
    path('<int:audit_id>/status/',        views.status_api,        name='status_api'),
    # Download PDF by token (unauthenticated)
    path('report/<str:token>/',           views.download_report,   name='download_report'),
    # Settings / config
    path('config/',                       views.config_view,       name='config'),
    # Upload template workbook
    path('config/upload-template/',       views.upload_template,   name='upload_template'),
    # Test-run page
    path('test-run/',                               views.test_run_view,         name='test_run'),
    path('test-run/<int:audit_id>/results/',        views.test_run_results,      name='test_run_results'),
    path('test-run/<int:audit_id>/archive/',        views.archive_test_run,      name='archive_test_run'),
    # Reference photo library
    path('reference-photos/',                       views.reference_photos,      name='reference_photos'),
    path('reference-photos/<int:photo_id>/tag/',    views.tag_reference_photo,   name='tag_reference_photo'),
    path('reference-photos/<int:photo_id>/delete/', views.delete_reference_photo, name='delete_reference_photo'),
]
