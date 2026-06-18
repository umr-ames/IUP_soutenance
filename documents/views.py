from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required

from accounts.decorators import role_required
from .models import DocumentTemplate


@login_required
@role_required(['admin'])
def admin_document_templates(request):
    templates = DocumentTemplate.objects.all().order_by('-uploaded_at')

    return render(request, 'documents/admin_document_templates.html', {
        'templates': templates
    })