from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    path('',                           views.task_board,    name='board'),
    path('create/',                    views.task_create,   name='create'),
    path('<uuid:task_id>/edit/',       views.task_edit,     name='edit'),
    path('<uuid:task_id>/complete/',   views.task_complete, name='complete'),
    path('<uuid:task_id>/status/',     views.task_status,   name='status'),
    path('<uuid:task_id>/delete/',     views.task_delete,   name='delete'),
    path('api/',                       views.api_tasks,     name='api'),
]
