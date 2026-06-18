from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm

from .models import CustomUser
from students.models import StudentProfile
from professors.models import ProfessorProfile


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
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Votre nom complet'
        })
    )

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: etudiant@exemple.com'
        })
    )

    phone_number = forms.CharField(
        label="Numéro de téléphone",
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 22 00 00 00'
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
        widget=forms.Select(attrs={
            'class': 'form-select searchable-select'
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
        matricule = self.cleaned_data.get('matricule')

        if StudentProfile.objects.filter(matricule=matricule).exists():
            raise forms.ValidationError("Ce matricule existe déjà.")

        return matricule

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')

        if CustomUser.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError("Ce numéro de téléphone est déjà utilisé.")

        return phone_number

    def clean_email(self):
        email = self.cleaned_data.get('email')

        if email and CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Cet email est déjà utilisé.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")

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
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: professeur@exemple.com'
        })
    )

    phone_number = forms.CharField(
        label="Numéro de téléphone",
        max_length=30,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ex: 22 00 00 00'
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
        phone_number = self.cleaned_data.get('phone_number')

        if CustomUser.objects.filter(phone_number=phone_number).exists():
            raise forms.ValidationError("Ce numéro de téléphone est déjà utilisé.")

        return phone_number

    def clean_email(self):
        email = self.cleaned_data.get('email')

        if email and CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Cet email est déjà utilisé.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")

        return cleaned_data