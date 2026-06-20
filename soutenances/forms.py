from django import forms

from professors.models import ProfessorProfile
from students.models import StudentProfile

from .models import (
    Deadline,
    Jury,
    PFERequest,
)


class PFERequestForm(forms.ModelForm):
    # Taille maximale d'un scan (Mo)
    MAX_UPLOAD_MB = 15

    class Meta:
        model = PFERequest
        fields = [
            "authorization_document",
            "attestation_stage",
            "rapport_stage",
        ]

        widgets = {
            "authorization_document": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": ".pdf",
            }),
            "attestation_stage": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": ".pdf",
            }),
            "rapport_stage": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": ".pdf,.doc,.docx",
                "required": True,
            }),
        }

        labels = {
            "authorization_document": "Autorisation de soutenance (PDF)",
            "attestation_stage": "Attestation de stage (PDF)",
            "rapport_stage": "Rapport de stage",
        }

        help_texts = {
            "authorization_document": "À scanner en PDF, clair et lisible.",
            "attestation_stage": "À scanner en PDF, clair et lisible.",
            "rapport_stage": "Format PDF, DOC ou DOCX. Taille maximale : 15 Mo.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pièces obligatoires du dossier de soutenance
        self.fields["authorization_document"].required = True
        self.fields["attestation_stage"].required = True
        self.fields["rapport_stage"].required = True
        self.fields["rapport_stage"].error_messages["required"] = (
            "Le rapport de stage est obligatoire pour envoyer la demande de soutenance."
        )

    def _validate_pdf_scan(self, file, label):
        if not file:
            return file

        extension = getattr(file, "name", "").split(".")[-1].lower()
        if extension != "pdf":
            raise forms.ValidationError(
                f"{label} doit être un fichier PDF scanné, clair et lisible."
            )

        size = getattr(file, "size", 0) or 0
        if size > self.MAX_UPLOAD_MB * 1024 * 1024:
            raise forms.ValidationError(
                f"{label} dépasse {self.MAX_UPLOAD_MB} Mo. Réduisez la taille du scan."
            )

        return file

    def clean_authorization_document(self):
        return self._validate_pdf_scan(
            self.cleaned_data.get("authorization_document"),
            "L'autorisation de soutenance",
        )

    def clean_attestation_stage(self):
        return self._validate_pdf_scan(
            self.cleaned_data.get("attestation_stage"),
            "L'attestation de stage",
        )

    def clean_rapport_stage(self):
        file = self.cleaned_data.get("rapport_stage")

        if file:
            allowed_extensions = ["pdf", "doc", "docx"]
            extension = file.name.split(".")[-1].lower()

            if extension not in allowed_extensions:
                raise forms.ValidationError(
                    "Le rapport doit être au format PDF, DOC ou DOCX."
                )

            size = getattr(file, "size", 0) or 0
            if size > self.MAX_UPLOAD_MB * 1024 * 1024:
                raise forms.ValidationError(
                    f"Le rapport dépasse {self.MAX_UPLOAD_MB} Mo. Réduisez la taille du fichier."
                )

        return file


class PFERequestDecisionForm(forms.Form):
    comment = forms.CharField(
        label="Commentaire",
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 4,
            "placeholder": "Ajouter un commentaire si nécessaire..."
        })
    )


class DeadlineForm(forms.ModelForm):
    class Meta:
        model = Deadline
        fields = [
            "title",
            "deadline_date",
            "is_active",
        ]

        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ex: Date limite de dépôt des demandes",
            }),
            "deadline_date": forms.DateTimeInput(attrs={
                "class": "form-control",
                "type": "datetime-local",
            }),
            "is_active": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

        labels = {
            "title": "Titre",
            "deadline_date": "Date limite",
            "is_active": "Activer cette date limite",
        }


class JuryForm(forms.ModelForm):
    members = forms.ModelMultipleChoiceField(
        label="Membres du jury",
        queryset=ProfessorProfile.objects.all().order_by("full_name"),
        widget=forms.SelectMultiple(attrs={
            "class": "form-select",
            "size": 8,
        }),
        help_text="Sélectionnez exactement 3 professeurs."
    )

    class Meta:
        model = Jury
        fields = [
            "name",
            "defense_date",
            "is_validated",
            "members",
        ]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ex: Jury 1"
            }),
            "defense_date": forms.DateInput(attrs={
                "class": "form-control",
                "type": "date",
            }),
            "is_validated": forms.CheckboxInput(attrs={
                "class": "form-check-input",
            }),
        }

        labels = {
            "name": "Nom du jury",
            "defense_date": "Date de soutenance",
            "is_validated": "Jury validé",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.pk:
            self.fields["members"].initial = ProfessorProfile.objects.filter(
                jury_memberships__jury=self.instance
            )

    def clean_members(self):
        members = self.cleaned_data.get("members")

        if not members:
            raise forms.ValidationError("Vous devez sélectionner 3 professeurs.")

        if members.count() != 3:
            raise forms.ValidationError("Un jury doit contenir exactement 3 professeurs.")

        return members


class JuryGenerationForm(forms.Form):
    """
    Génération intelligente sans choix manuel de date.

    Le département de l'IUP clique seulement sur le bouton de génération.
    Le système cherche automatiquement les meilleurs créneaux à partir des
    disponibilités futures des professeurs.

    La date et l'heure sont donc déterminées automatiquement par l'algorithme :
    - disponibilité de l'encadrant,
    - disponibilité de deux autres professeurs,
    - absence de conflit,
    - charge la plus faible.
    """

    auto_generation = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.HiddenInput(attrs={
            "value": "1",
        })
    )


class JuryStudentAssignForm(forms.Form):
    student = forms.ModelChoiceField(
        label="Étudiant",
        queryset=StudentProfile.objects.none(),
        widget=forms.Select(attrs={
            "class": "form-select",
        })
    )

    def __init__(self, *args, **kwargs):
        self.jury = kwargs.pop("jury", None)
        super().__init__(*args, **kwargs)

        queryset = StudentProfile.objects.filter(
            pfe_request__status=PFERequest.STATUS_ACCEPTED,
            jury_assignment__isnull=True,
        ).select_related(
            "encadrant",
            "user",
        ).order_by(
            "filiere",
            "full_name"
        )

        if self.jury:
            jury_professors = ProfessorProfile.objects.filter(
                jury_memberships__jury=self.jury
            )

            queryset = queryset.filter(
                encadrant__in=jury_professors
            )

        self.fields["student"].queryset = queryset


class JuryMembersForSlotForm(forms.Form):
    """Choix des 2 professeurs supplémentaires (en plus de l'encadrant) pour
    un jury créé via le flux guidé. Le queryset est restreint côté serveur
    aux seuls professeurs réellement disponibles au créneau choisi : un
    professeur indisponible ne peut donc pas être sélectionné, même en
    contournant le JavaScript (Django rejette toute valeur hors queryset)."""

    members = forms.ModelMultipleChoiceField(
        label="2 professeurs supplémentaires disponibles à ce créneau",
        queryset=ProfessorProfile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, available_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)

        if available_queryset is not None:
            self.fields["members"].queryset = available_queryset

    def clean_members(self):
        members = self.cleaned_data.get("members")

        if not members or members.count() != 2:
            raise forms.ValidationError(
                "Vous devez choisir exactement 2 professeurs supplémentaires, "
                "parmi ceux disponibles à ce créneau."
            )

        return members


class JurySmartMembersForm(forms.Form):
    """Choix des 3 membres lors de la modification intelligente d'un jury
    déjà généré. Le queryset n'autorise que : les professeurs réellement
    disponibles au créneau choisi, plus les encadrants déjà obligatoires
    (étudiants déjà affectés à ce jury). Tout autre id envoyé en POST est
    rejeté par Django, indépendamment du JavaScript."""

    members = forms.ModelMultipleChoiceField(
        label="Membres du jury pour ce créneau",
        queryset=ProfessorProfile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, selectable_queryset=None, mandatory_ids=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.mandatory_ids = set(mandatory_ids or [])

        if selectable_queryset is not None:
            self.fields["members"].queryset = selectable_queryset

    def clean_members(self):
        members = self.cleaned_data.get("members")
        member_ids = {member.id for member in members} if members else set()

        missing_mandatory = self.mandatory_ids - member_ids

        if missing_mandatory:
            raise forms.ValidationError(
                "Les encadrants des étudiants déjà affectés à ce jury doivent "
                "rester membres du jury."
            )

        if len(member_ids) != 3:
            raise forms.ValidationError(
                "Un jury doit contenir exactement 3 professeurs."
            )

        return members


class JuryAddMemberForm(forms.Form):
    """Ajout d'un membre dans la page Modifier jury. Le queryset est
    restreint côté serveur aux professeurs réellement disponibles au
    créneau du jury (et pas déjà membres) : un professeur indisponible ne
    peut pas être ajouté, même via un POST forcé."""

    professor = forms.ModelChoiceField(
        label="Professeur à ajouter",
        queryset=ProfessorProfile.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, selectable_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)

        if selectable_queryset is not None:
            self.fields["professor"].queryset = selectable_queryset


class PlanningGenerationForm(forms.Form):
    """
    Planning manuel par date.

    Ce formulaire reste utile pour le département de l'IUP s'il veut régénérer
    manuellement le planning d'une date précise.

    La génération intelligente des jurys, elle, n'a plus besoin de date.
    """

    defense_date = forms.DateField(
        label="Date de soutenance",
        widget=forms.DateInput(attrs={
            "class": "form-control",
            "type": "date",
        })
    )

    overwrite_existing = forms.BooleanField(
        label="Supprimer l'ancien planning de cette date et régénérer",
        required=False,
        widget=forms.CheckboxInput(attrs={
            "class": "form-check-input",
        })
    )
