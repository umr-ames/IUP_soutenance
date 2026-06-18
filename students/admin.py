from django.contrib import admin

from .models import StudentProfile


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('matricule', 'full_name', 'filiere', 'encadrant', 'phone_number')
    list_filter = ('filiere', 'encadrant')
    search_fields = ('matricule', 'full_name', 'user__phone_number')

    def phone_number(self, obj):
        return obj.user.phone_number or "-"
