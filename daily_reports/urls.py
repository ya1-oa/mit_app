from django.urls import path
from . import views

app_name = 'daily_reports'

urlpatterns = [
    path('',             views.dashboard,    name='daily_reports_dashboard'),
    path('config/',      views.config_view,  name='daily_reports_config'),
    path('tasks/',       views.tasks_view,   name='daily_reports_tasks'),
    path('tasks/<int:task_id>/update/',  views.update_task,  name='daily_reports_update_task'),
    path('tasks/<int:task_id>/delete/',  views.delete_task,  name='daily_reports_delete_task'),
    path('flag/',        views.flag_item,    name='daily_reports_flag'),
    path('resolve/<int:item_id>/', views.resolve_item, name='daily_reports_resolve'),
    path('send-now/',    views.send_now,     name='daily_reports_send_now'),
    path('preview/',      views.preview_report, name='daily_reports_preview'),
    path('save-pinned/',  views.save_pinned,    name='daily_reports_save_pinned'),
    path('priority-tasks/create/', views.create_priority_task, name='daily_create_priority_task'),
    path('priority-tasks/<int:task_id>/update/', views.update_priority_task, name='daily_update_priority_task'),
    path('priority-tasks/<int:task_id>/delete/', views.delete_priority_task, name='daily_delete_priority_task'),
]
