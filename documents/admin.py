from django.contrib import admin
from .models import DocumentTemplate


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'template_type', 'is_active', 'uploaded_at')
    list_filter = ('template_type', 'is_active')
    search_fields = ('title',)
