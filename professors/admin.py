from django.contrib import admin
from .models import ProfessorProfile, ProfessorAvailability


@admin.register(ProfessorProfile)
class ProfessorProfileAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'user', 'phone')
    search_fields = ('full_name', 'user__username', 'user__email', 'phone')


@admin.register(ProfessorAvailability)
class ProfessorAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('professor', 'date', 'start_time', 'end_time')
    list_filter = ('date', 'professor')
    search_fields = ('professor__full_name',)