from django.contrib import admin

from .models import AREmailTemplate, CommunicationActivity


@admin.register(CommunicationActivity)
class CommunicationActivityAdmin(admin.ModelAdmin):
    list_display = ['estimate', 'activity_type', 'tenant', 'created_by', 'created_at']
    list_filter = ['activity_type', 'tenant']
    search_fields = ['estimate__estimate_number', 'notes']
    readonly_fields = ['created_at']
    ordering = ['-created_at']


@admin.register(AREmailTemplate)
class AREmailTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'tenant', 'is_default', 'created_at']
    list_filter = ['category', 'tenant', 'is_default']
    search_fields = ['name', 'subject_template']
    readonly_fields = ['created_at']
    ordering = ['category', 'name']
