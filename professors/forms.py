from django import forms
from django.core.exceptions import ValidationError

from soutenances.models import Evaluation
from .models import ProfessorAvailability


class BootstrapFormMixin:
    def _bootstrap_fields(self):
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class ProfessorRequestDecisionForm(forms.Form):
    ACTION_CHOICES = (
        ("accept", "Valider"),
        ("refuse", "Refuser"),
    )

    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.HiddenInput
    )

    professor_comment = forms.CharField(
        label="Commentaire encadrant",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Motif de refus ou observation"
        })
    )

    def clean(self):
        cleaned = super().clean()

        if cleaned.get("action") == "refuse" and not cleaned.get("professor_comment"):
            raise ValidationError("Le commentaire est obligatoire pour refuser.")

        return cleaned


class ProfessorAvailabilityForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = ProfessorAvailability
        fields = [
            "date",
            "start_time",
            "end_time",
        ]

        labels = {
            "date": "Date",
            "start_time": "Début",
            "end_time": "Fin",
        }

        widgets = {
            "date": forms.DateInput(attrs={
                "type": "date",
            }),
            "start_time": forms.TimeInput(attrs={
                "type": "time",
            }),
            "end_time": forms.TimeInput(attrs={
                "type": "time",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap_fields()


class EvaluationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Evaluation
        fields = [
            "rapport_note",
            "presentation_note",
            "questions_note",
        ]

        labels = {
            "rapport_note": "Rapport /20 (coef. 0.30)",
            "presentation_note": "Présentation personnelle /20 (coef. 0.30)",
            "questions_note": "Réponses aux questions /20 (coef. 0.40)",
        }

        widgets = {
            "rapport_note": forms.NumberInput(attrs={
                "step": "0.25",
                "min": "0",
                "max": "20",
                "placeholder": "Ex: 15.50",
            }),
            "presentation_note": forms.NumberInput(attrs={
                "step": "0.25",
                "min": "0",
                "max": "20",
                "placeholder": "Ex: 16.00",
            }),
            "questions_note": forms.NumberInput(attrs={
                "step": "0.25",
                "min": "0",
                "max": "20",
                "placeholder": "Ex: 14.75",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrap_fields()

    def clean(self):
        cleaned = super().clean()

        rapport_note = cleaned.get("rapport_note")
        presentation_note = cleaned.get("presentation_note")
        questions_note = cleaned.get("questions_note")

        notes = [
            rapport_note,
            presentation_note,
            questions_note,
        ]

        if any(note is None for note in notes):
            raise ValidationError("Toutes les notes sont obligatoires.")

        for note in notes:
            if note < 0 or note > 20:
                raise ValidationError("Chaque note doit être entre 0 et 20.")

        return cleaned


class EvaluationSubmissionForm(EvaluationForm):
    pass