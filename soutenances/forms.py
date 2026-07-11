from decimal import Decimal

from django import forms

from professors.models import ProfessorProfile
from students.models import StudentProfile, StudentReference

from .models import (
    Deadline,
    Jury,
    PFERequest,
)


class HistoricalDefenseForm(forms.Form):
    """Saisie manuelle d'une soutenance déjà réalisée avant la plateforme.
    Recherche par matricule : fonctionne pour un étudiant déjà inscrit (sans
    demande) comme pour un étudiant de la liste officielle non encore inscrit."""

    matricule = forms.CharField(
        label="Matricule de l'étudiant",
        max_length=50,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex : IUP23491"}),
    )
    defense_date = forms.DateField(
        label="Date de soutenance",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    salle = forms.ChoiceField(
        label="Salle", required=False, choices=Jury.SALLE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    president = forms.ModelChoiceField(
        label="Président du jury",
        queryset=ProfessorProfile.objects.order_by("full_name"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    member = forms.ModelChoiceField(
        label="3ᵉ membre du jury",
        queryset=ProfessorProfile.objects.order_by("full_name"),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    final_note = forms.DecimalField(
        label="Note finale /20",
        min_value=Decimal("0"), max_value=Decimal("20"),
        max_digits=5, decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": 0, "max": 20}),
    )

    def clean(self):
        from students.models import normalize_matricule

        cleaned = super().clean()
        president = cleaned.get("president")
        member = cleaned.get("member")

        raw = cleaned.get("matricule")
        matricule = normalize_matricule(raw) if raw else ""
        cleaned["matricule"] = matricule
        encadrant = None

        if matricule:
            profile = StudentProfile.objects.select_related("encadrant").filter(
                matricule__iexact=matricule
            ).first()
            reference = StudentReference.objects.filter(
                matricule__iexact=matricule
            ).first()

            if profile:
                # Étudiant déjà inscrit : on réutilise son profil et son encadrant.
                cleaned["student_profile"] = profile
                cleaned["reference"] = reference
                encadrant = profile.encadrant
                if hasattr(profile, "jury_assignment"):
                    self.add_error(
                        "matricule",
                        "Cet étudiant a déjà un jury / une soutenance enregistrée.",
                    )
            elif reference:
                # Non inscrit : on créera son profil ; encadrant repris de la liste.
                cleaned["reference"] = reference
                cleaned["student_profile"] = None
                encadrant = ProfessorProfile.objects.filter(
                    full_name__iexact=(reference.encadrant_name or "").strip()
                ).first()
                if not encadrant:
                    self.add_error(
                        "matricule",
                        "L'encadrant officiel de cet étudiant "
                        f"(« {reference.encadrant_name} ») n'existe pas encore comme "
                        "professeur. Importez d'abord la liste officielle.",
                    )
            else:
                self.add_error(
                    "matricule",
                    "Aucun étudiant (inscrit ou liste officielle) ne correspond à ce matricule.",
                )

        cleaned["encadrant"] = encadrant

        if encadrant:
            if president and president.id == encadrant.id:
                self.add_error("president", "Le président ne peut pas être l'encadrant.")
            if member and member.id == encadrant.id:
                self.add_error("member", "Ce membre ne peut pas être l'encadrant.")

        if president and member and president.id == member.id:
            self.add_error("member", "Le membre doit être différent du président.")

        return cleaned


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
        # Mode « régularisation » : dossier déjà déposé, l'étudiant redépose
        # seulement la ou les pièce(s) qu'il souhaite changer. Les autres pièces
        # déjà déposées sont conservées telles quelles.
        self.completing = kwargs.pop("completing", False)
        super().__init__(*args, **kwargs)

        if self.completing:
            # Aucune pièce n'est obligatoire : on ne remplace que ce qu'on dépose.
            for name in ("authorization_document", "attestation_stage", "rapport_stage"):
                self.fields[name].required = False
        else:
            # Première demande : toutes les pièces sont obligatoires.
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
        value = self.cleaned_data.get("authorization_document")
        # Ne valider que les fichiers fraîchement déposés ; une pièce déjà
        # stockée et conservée telle quelle n'est pas re-vérifiée.
        if not self.files.get("authorization_document"):
            return value
        return self._validate_pdf_scan(value, "L'autorisation de soutenance")

    def clean_attestation_stage(self):
        value = self.cleaned_data.get("attestation_stage")
        if not self.files.get("attestation_stage"):
            return value
        return self._validate_pdf_scan(value, "L'attestation de stage")

    def clean_rapport_stage(self):
        file = self.cleaned_data.get("rapport_stage")

        if file and self.files.get("rapport_stage"):
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

    def clean(self):
        cleaned = super().clean()
        # En régularisation, l'étudiant doit déposer au moins une pièce,
        # sinon le formulaire ne fait rien (source de confusion).
        if self.completing:
            has_new_file = any(
                bool(self.files.get(name))
                for name in ("authorization_document", "attestation_stage", "rapport_stage")
            )
            if not has_new_file:
                raise forms.ValidationError(
                    "Sélectionnez au moins un document à déposer. "
                    "Les pièces que vous ne changez pas restent inchangées."
                )
        return cleaned


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

    start_date = forms.DateField(
        label="Date de début des soutenances",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    end_date = forms.DateField(
        label="Date de fin des soutenances",
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Tous les jours de l'intervalle sont utilisés, week-ends compris.",
    )
    max_simultaneous = forms.IntegerField(
        label="Nombre max de jurys en même temps",
        min_value=1,
        max_value=7,
        initial=7,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        help_text="Limité au nombre de salles disponibles (7).",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError(
                "La date de fin doit être postérieure ou égale à la date de début."
            )
        return cleaned


class TargetedJuryGenerationForm(forms.Form):
    """Génération ciblée : l'admin choisit une date, un nombre de jurys, les
    étudiants (parmi les acceptés) et un groupe de professeurs."""

    num_juries = forms.IntegerField(
        label="Nombre de jurys souhaité",
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": 1}),
    )
    students = forms.ModelMultipleChoiceField(
        label="Étudiants à programmer",
        queryset=StudentProfile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    professors = forms.ModelMultipleChoiceField(
        label="Professeurs (groupe de jury)",
        queryset=ProfessorProfile.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["students"].queryset = (
            StudentProfile.objects.filter(
                pfe_request__status=PFERequest.STATUS_ACCEPTED,
                jury_assignment__isnull=True,
                encadrant__isnull=False,
            ).select_related("encadrant").order_by("encadrant__full_name", "full_name")
        )
        self.fields["professors"].queryset = ProfessorProfile.objects.order_by("full_name")

    def clean(self):
        cleaned = super().clean()
        professors = cleaned.get("professors")
        if professors is not None and professors.count() < 3:
            self.add_error("professors", "Sélectionnez au moins 3 professeurs.")
        return cleaned


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
        )

        jury_prof_ids = set()
        if self.jury:
            jury_prof_ids = set(
                ProfessorProfile.objects.filter(
                    jury_memberships__jury=self.jury
                ).values_list("id", flat=True)
            )
            # Tous les étudiants sans jury sont sélectionnables : ceux dont
            # l'encadrant est membre d'abord, puis les autres (ajout forcé par
            # l'admin, avec avertissement « encadrant hors jury »).
            from django.db.models import Case, When, IntegerField
            queryset = queryset.annotate(
                _enc_in_jury=Case(
                    When(encadrant_id__in=jury_prof_ids, then=0),
                    default=1,
                    output_field=IntegerField(),
                )
            ).order_by("_enc_in_jury", "filiere", "full_name")
        else:
            queryset = queryset.order_by("filiere", "full_name")

        field = self.fields["student"]
        field.queryset = queryset

        def _label(obj):
            base = f"{obj.full_name} ({obj.matricule})"
            if jury_prof_ids and obj.encadrant_id not in jury_prof_ids:
                enc = obj.encadrant.full_name if obj.encadrant else "?"
                return f"{base} — ⚠ encadrant hors jury : {enc}"
            return base

        field.label_from_instance = _label


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
