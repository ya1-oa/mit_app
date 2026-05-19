from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    CustomUser, Client, Document, DocumentCategory, Landlord,
    WorkType, Room, RoomWorkTypeValue,
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