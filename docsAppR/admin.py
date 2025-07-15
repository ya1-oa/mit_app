from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Client, Document, DocumentCategory, Landlord

# Register your models here.
class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['email', 'username', 'first_name', 'last_name', 'is_staff']

admin.site.register(CustomUser, CustomUserAdmin)

admin.site.register(Client)

admin.site.register(Document)

admin.site.register(DocumentCategory)

admin.site.register(Landlord)