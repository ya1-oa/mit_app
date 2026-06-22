from django.urls import path
from . import views

app_name = 'dev_hub'

urlpatterns = [
    # Dashboard
    path('',                                    views.dashboard,       name='dashboard'),

    # Weekly progress report (editable HTML + PDF).
    # MUST precede the <slug:slug> catch-all below, or "weekly-reports" would be
    # resolved as a module slug.
    path('weekly-reports/',                       views.weekly_report_list,   name='weekly_report_list'),
    path('weekly-reports/new/',                   views.weekly_report_create, name='weekly_report_create'),
    path('weekly-reports/<uuid:report_id>/',       views.weekly_report_detail, name='weekly_report_detail'),
    path('weekly-reports/<uuid:report_id>/edit/',  views.weekly_report_edit,   name='weekly_report_edit'),
    path('weekly-reports/<uuid:report_id>/pdf/',   views.weekly_report_pdf,    name='weekly_report_pdf'),

    # Module detail
    path('<slug:slug>/',                         views.module_detail,   name='module_detail'),

    # Task AJAX endpoints
    path('api/task/<uuid:task_id>/toggle/',      views.task_toggle,     name='task_toggle'),
    path('api/task/<uuid:task_id>/queue/',        views.task_queue_toggle, name='task_queue_toggle'),
    path('api/module/<int:module_id>/task/add/', views.task_add,        name='task_add'),

    # Notifications & reporting
    path('task/<uuid:task_id>/notify-client/',   views.notify_client,   name='notify_client'),
    path('report/adhoc/',                        views.report_adhoc,    name='report_adhoc'),
    path('report/<uuid:report_id>/response/',    views.report_response, name='report_response'),

    # Coverage
    path('module/<int:module_id>/coverage/',     views.coverage_update, name='coverage_update'),

    # AI Resources & cost tracking
    path('ai-resources/',                        views.ai_resources,    name='ai_resources'),
    path('api/ai-usage/data/',                   views.ai_usage_data,   name='ai_usage_data'),
]
