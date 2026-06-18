from django import forms

from .models import DocumentTemplate


class DocumentTemplateForm(forms.ModelForm):
    class Meta:
        model = DocumentTemplate
        fields = ["title", "template_type", "description", "file", "is_active"]
        labels = {
            "title": "Titre",
            "template_type": "Type",
            "description": "Description",
            "file": "Fichier",
            "is_active": "Template actif",
        }
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "template_type": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
            }),
            "file": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": ".pdf,.doc,.docx",
            }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
