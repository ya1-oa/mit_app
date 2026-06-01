from django.urls import path
from . import views

app_name = 'dev_hub'

urlpatterns = [
    # Dashboard
    path('',                                    views.dashboard,       name='dashboard'),

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
]
