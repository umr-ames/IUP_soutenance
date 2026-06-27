import re

from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from .models import CustomUser
from students.models import StudentProfile, StudentReference, normalize_matricule
from professors.models import ProfessorProfile


def find_student_reference(matricule):
    """Retourne la fiche officielle correspondant au matricule, en tolérant les
    espaces, caractères invisibles et la casse (cf. normalize_matricule)."""
    if not matricule:
        return None

    target = normalize_matricule(matricule)
    if not target:
        return None

    # Correspondance directe (cas nominal, données déjà propres)
    reference = StudentReference.objects.filter(matricule__iexact=matricule).first()
    if reference:
        return reference

    # Repli tolérant : compare les matricules normalisés (données historiques
    # contenant un espace insécable / caractère invisible).
    for candidate in StudentReference.objects.all():
        if normalize_matricule(candidate.matricule) == target:
            return candidate

    return None


PHONE_NUMBER_PATTERN = re.compile(r"^[234][0-9]{7}$")
PHONE_NUMBER_ERROR = (
    "Le numéro de téléphone doit contenir exactement 8 chiffres "
    "et commencer par 2, 3 ou 4."
)


def clean_mauritanian_phone_number(value):
    phone_number = re.sub(r"\s+", "", value or "")

    if not PHONE_NUMBER_PATTERN.fullmatch(phone_number):
        raise forms.ValidationError(PHONE_NUMBER_ERROR)

    return phone_number


def clean_email_value(value):
    return (value or "").strip().lower()


class PhoneLoginForm(forms.Form):
    phone_number = forms.CharField(
        label="Email ou numéro de téléphone",
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Email ou téléphone'
        })
    )

    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Mot de passe'
        })
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        phone_number = cleaned_data.get('phone_number')
        password = cleaned_data.get('password')

        if phone_number and password:
            self.user = authenticate(
                self.request,
                username=phone_number,
                password=password
            )

            if self.user is None:
                raise forms.ValidationError(
                    "Numéro de téléphone ou mot de passe incorrect."
                )

        return cleaned_data

    def get_user(self):
        return self.user


class StudentRegisterForm(forms.Form):
    matricule = forms.CharField(
        label="Matricule",
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: IUP23441'
        })
    )

    full_name = forms.CharField(
        label="Nom complet",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Renseigne automatiquement depuis le matricule',
            'readonly': 'readonly'
        })
    )

    email = forms.EmailField(
        label="Email",
        error_messages={
            'required': "Veuillez saisir votre email.",
            'invalid': "Adresse email invalide. Exemple : nom@exemple.com.",
        },
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: etudiant@exemple.com',
            'autocomplete': 'email'
        })
    )

    phone_number = forms.CharField(
        label="Numéro de téléphone",
        max_length=8,
        error_messages={
            'required': "Veuillez saisir votre numéro de téléphone.",
            'max_length': PHONE_NUMBER_ERROR,
        },
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 22000000',
            'inputmode': 'numeric',
            'maxlength': '8',
            'pattern': '[234][0-9]{7}',
            'title': PHONE_NUMBER_ERROR
        })
    )

    filiere = forms.ChoiceField(
        label="Filière",
        choices=StudentProfile.FILIERE_CHOICES,
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select'
        })
    )

    encadrant = forms.ModelChoiceField(
        label="Encadrant",
        queryset=ProfessorProfile.objects.all().order_by('full_name'),
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-select searchable-select'
        })
    )

    entreprise = forms.CharField(
        label="Entreprise de stage",
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: Mauritel, Banque Populaire, Ministère...'
        })
    )

    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control'
        })
    )

    password2 = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control'
        })
    )

    def clean_matricule(self):
        matricule = normalize_matricule(self.cleaned_data.get('matricule'))

        if StudentProfile.objects.filter(matricule__iexact=matricule).exists():
            raise forms.ValidationError("Ce matricule existe déjà.")

        reference = find_student_reference(matricule)
        if reference is None:
            raise forms.ValidationError(
                "Ce matricule n'est pas dans la liste officielle."
            )

        # On enregistre le matricule officiel normalisé (cohérence aval).
        return normalize_matricule(reference.matricule)

    def clean_phone_number(self):
        phone_number = clean_mauritanian_phone_number(
            self.cleaned_data.get('phone_number')
        )

        if CustomUser.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError("Ce numéro de téléphone est déjà utilisé.")

        return phone_number

    def clean_email(self):
        email = clean_email_value(self.cleaned_data.get('email'))

        if email and CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Cet email est déjà utilisé.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        matricule = cleaned_data.get('matricule')
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")

        if password1:
            try:
                validate_password(password1)
            except DjangoValidationError as error:
                self.add_error('password1', error)

        if matricule:
            reference = find_student_reference(matricule)

            if reference:
                cleaned_data['full_name'] = reference.full_name
                cleaned_data['filiere'] = reference.filiere

                encadrant = ProfessorProfile.objects.filter(
                    full_name__iexact=reference.encadrant_name
                ).first()

                if not encadrant:
                    raise forms.ValidationError(
                        "L'encadrant officiel de ce matricule n'existe pas encore. "
                        "Importez d'abord la liste officielle."
                    )

                cleaned_data['encadrant'] = encadrant

        return cleaned_data


class ProfessorRegisterForm(forms.Form):
    professor = forms.ModelChoiceField(
        label="Votre nom",
        queryset=ProfessorProfile.objects.filter(user__isnull=True).order_by('full_name'),
        widget=forms.Select(attrs={
            'class': 'form-select searchable-select'
        })
    )

    email = forms.EmailField(
        label="Email",
        error_messages={
            'required': "Veuillez saisir votre email.",
            'invalid': "Adresse email invalide. Exemple : nom@exemple.com.",
        },
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: professeur@exemple.com',
            'autocomplete': 'email'
        })
    )

    phone_number = forms.CharField(
        label="Numéro de téléphone",
        max_length=8,
        error_messages={
            'required': "Veuillez saisir votre numéro de téléphone.",
            'max_length': PHONE_NUMBER_ERROR,
        },
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 22000000',
            'inputmode': 'numeric',
            'maxlength': '8',
            'pattern': '[234][0-9]{7}',
            'title': PHONE_NUMBER_ERROR
        })
    )

    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control'
        })
    )

    password2 = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control'
        })
    )

    def clean_phone_number(self):
        phone_number = clean_mauritanian_phone_number(
            self.cleaned_data.get('phone_number')
        )

        if CustomUser.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError("Ce numéro de téléphone est déjà utilisé.")

        return phone_number

    def clean_email(self):
        email = clean_email_value(self.cleaned_data.get('email'))

        if email and CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Cet email est déjà utilisé.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")

        if password1:
            try:
                validate_password(password1)
            except DjangoValidationError as error:
                self.add_error('password1', error)

        return cleaned_data
