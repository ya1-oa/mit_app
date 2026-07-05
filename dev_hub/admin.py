from django.contrib import admin
from .models import AppModule, DevTask, TestCoverage, ProgressReport, WeeklyReport


class DevTaskInline(admin.TabularInline):
    model   = DevTask
    extra   = 0
    fields  = ['title', 'task_type', 'status', 'notify_on_complete',
                'queue_for_weekly_report', 'order']
    ordering = ['order', 'created_at']


@admin.register(AppModule)
class AppModuleAdmin(admin.ModelAdmin):
    list_display  = ['name', 'status', 'completion_pct_display', 'order', 'updated_at']
    list_filter   = ['status']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    inlines       = [DevTaskInline]

    @admin.display(description='Done %')
    def completion_pct_display(self, obj):
        return f'{obj.completion_pct}%'


@admin.register(DevTask)
class DevTaskAdmin(admin.ModelAdmin):
    list_display  = ['title', 'module', 'task_type', 'status', 'notify_on_complete',
                     'queue_for_weekly_report', 'completed_at']
    list_filter   = ['status', 'task_type', 'module', 'notify_on_complete',
                     'queue_for_weekly_report']
    search_fields = ['title', 'description']
    ordering      = ['module', 'order']
    readonly_fields = ['id', 'completed_at', 'created_at', 'updated_at']


@admin.register(TestCoverage)
class TestCoverageAdmin(admin.ModelAdmin):
    list_display = ['module', 'unit_tested', 'human_tested', 'coverage_pct', 'updated_at']
    list_filter  = ['unit_tested', 'human_tested']


@admin.register(ProgressReport)
class ProgressReportAdmin(admin.ModelAdmin):
    list_display   = ['sent_at', 'report_type', 'sent_by', 'email_opened', 'has_response']
    list_filter    = ['report_type']
    readonly_fields = ['id', 'sent_at', 'modules_snapshot', 'email_log']
    filter_horizontal = ['modules']

    @admin.display(boolean=True, description='Opened')
    def email_opened(self, obj):
        return obj.email_log.is_opened if obj.email_log else False

    @admin.display(boolean=True, description='Response')
    def has_response(self, obj):
        return bool(obj.response_notes)


@admin.register(WeeklyReport)
class WeeklyReportAdmin(admin.ModelAdmin):
    list_display    = ['title', 'week_of', 'overall_status', 'created_by', 'updated_at']
    list_filter     = ['overall_status', 'week_of']
    search_fields   = ['title']
    readonly_fields = ['id', 'created_at', 'updated_at']
    date_hierarchy  = 'week_of'
