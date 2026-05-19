from django.urls import path
from . import views

urlpatterns = [
    path('', views.reading_browser, name='reading_browser'),
    path('upload/', views.upload_readings, name='upload_readings'),
    path('sorted/', views.get_sorted_readings, name='get_sorted_readings'),
    path('export/', views.export_readings, name='export_readings'),
    path('delete/<int:image_id>/', views.delete_reading, name='delete_reading'),
    path('rename/<int:image_id>/', views.rename_reading, name='rename_reading'),
]
