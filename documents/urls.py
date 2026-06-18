from django.urls import path
from . import views

urlpatterns = [
    path(
        'admin/templates/',
        views.admin_document_templates,
        name='admin_document_templates'
    ),
]