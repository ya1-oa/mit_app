from django.contrib import admin
from .models import DailyReportConfig, HighPriorityItem, OperationalTask, DailyReportLog


@admin.register(DailyReportConfig)
class DailyReportConfigAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'send_hour', 'escalation_days', 'updated_at']


@admin.register(HighPriorityItem)
class HighPriorityItemAdmin(admin.ModelAdmin):
    list_display  = ['client', 'item_type', 'is_resolved', 'added_by', 'added_at']
    list_filter   = ['item_type', 'is_resolved']
    raw_id_fields = ['client', 'ppr_session', 'lease']


@admin.register(OperationalTask)
class OperationalTaskAdmin(admin.ModelAdmin):
    list_display  = ['title', 'app', 'status', 'priority', 'percent_complete', 'due_date']
    list_filter   = ['app', 'status', 'priority']
    list_editable = ['status', 'percent_complete']


@admin.register(DailyReportLog)
class DailyReportLogAdmin(admin.ModelAdmin):
    list_display = ['report_type', 'sent_at', 'total_items', 'urgent_items', 'email_success']
    list_filter  = ['report_type', 'email_success']
