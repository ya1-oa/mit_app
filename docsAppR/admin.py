from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    CustomUser, Client, Document, DocumentCategory, Landlord,
    WorkType, Room, RoomWorkTypeValue,
    SentEmail, EmailOpenEvent, GeneratedFile, UploadedAttachment, EmailCampaign,
    EncircleSyncLog,
)

# Register your models here.
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_staff']

admin.site.register(CustomUser, CustomUserAdmin)


# ==================== OneDrive Integration Models ====================

@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ['work_type_id', 'name', 'applies_to_all_rooms', 'display_order', 'is_active']
    list_filter = ['is_active', 'applies_to_all_rooms']
    search_fields = ['name']
    ordering = ['display_order', 'work_type_id']


class RoomWorkTypeValueInline(admin.TabularInline):
    model = RoomWorkTypeValue
    extra = 0
    fields = ['work_type', 'value_type']


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['room_name', 'client', 'sequence']
    list_filter = []
    search_fields = ['room_name', 'client__pOwner', 'client__claimNumber']
    ordering = ['client', 'sequence']
    inlines = [RoomWorkTypeValueInline]


# ==================== Original Models ====================

admin.site.register(Client)
admin.site.register(Document)
admin.site.register(DocumentCategory)
admin.site.register(Landlord)


# ==================== Email Models ====================

class EmailOpenEventInline(admin.TabularInline):
    model = EmailOpenEvent
    extra = 0
    readonly_fields = ['opened_at', 'ip_address', 'user_agent']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SentEmail)
class SentEmailAdmin(admin.ModelAdmin):
    list_display  = ['subject', 'sent_by', 'claim', 'sent_at', 'opened_badge', 'opened_at', 'open_count']
    list_filter   = ['is_opened', 'sent_at', 'notify_on_open']
    search_fields = ['subject', 'sent_by__email', 'claim__pOwner']
    readonly_fields = [
        'tracking_pixel_id', 'sent_at', 'is_opened', 'opened_at',
        'recipients', 'cc', 'bcc',
    ]
    ordering  = ['-sent_at']
    inlines   = [EmailOpenEventInline]

    @admin.display(boolean=True, description='Opened')
    def opened_badge(self, obj):
        return obj.is_opened

    @admin.display(description='Open count')
    def open_count(self, obj):
        return obj.emailopenevent_set.count()


@admin.register(GeneratedFile)
class GeneratedFileAdmin(admin.ModelAdmin):
    list_display  = ['name', 'category', 'client', 'created_by', 'created_at']
    list_filter   = ['category', 'created_at']
    search_fields = ['name', 'client__pOwner']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']


@admin.register(UploadedAttachment)
class UploadedAttachmentAdmin(admin.ModelAdmin):
    list_display  = ['original_name', 'mime_type', 'size_display', 'uploaded_by', 'uploaded_at']
    list_filter   = ['uploaded_at']
    search_fields = ['original_name', 'uploaded_by__email']
    readonly_fields = ['id', 'uploaded_at']

    @admin.display(description='Size')
    def size_display(self, obj):
        if obj.size < 1024:
            return f'{obj.size} B'
        elif obj.size < 1024 * 1024:
            return f'{obj.size / 1024:.1f} KB'
        return f'{obj.size / (1024 * 1024):.1f} MB'


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display  = ['name', 'status', 'total_sends', 'sends_completed',
                     'interval_display', 'start_at', 'created_by', 'created_at']
    list_filter   = ['status', 'interval_unit']
    search_fields = ['name', 'subject', 'created_by__email']
    readonly_fields = ['id', 'created_at', 'updated_at', 'beat_task_ids', 'sends_completed']
    ordering = ['-created_at']

    @admin.display(description='Interval')
    def interval_display(self, obj):
        return f'every {obj.interval_value} {obj.interval_unit}'

@admin.register(EncircleSyncLog)
class EncircleSyncLogAdmin(admin.ModelAdmin):
    list_display = [
        'started_at', 'status', 'triggered_by',
        'claims_processed', 'claims_created', 'claims_updated',
        'error_count', 'duration_display',
    ]
    list_filter  = ['status', 'triggered_by']
    readonly_fields = [
        'started_at', 'completed_at', 'status', 'triggered_by',
        'claims_processed', 'claims_created', 'claims_updated',
        'error_count', 'error_details',
    ]
    ordering = ['-started_at']

    @admin.display(description='Duration')
    def duration_display(self, obj):
        secs = obj.duration_seconds
        if secs is None:
            return '—'
        if secs < 60:
            return f'{secs}s'
        return f'{secs // 60}m {secs % 60}s'
