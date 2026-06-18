from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = (
        'username',
        'phone_number',
        'email',
        'role',
        'is_staff',
        'is_superuser',
        'is_active',
    )

    list_filter = (
        'role',
        'is_staff',
        'is_superuser',
        'is_active',
    )

    search_fields = (
        'username',
        'phone_number',
        'email',
        'first_name',
        'last_name',
    )

    fieldsets = UserAdmin.fieldsets + (
        ('Role utilisateur', {
            'fields': ('role', 'phone_number')
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role utilisateur', {
            'fields': ('role', 'phone_number')
        }),
    )
