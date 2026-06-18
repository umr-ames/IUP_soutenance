from django.db import models
from django.conf import settings
from professors.models import ProfessorProfile


class StudentProfile(models.Model):
    FILIERE_FINTECH = 'FINTECH'
    FILIERE_DS = 'DS'
    FILIERE_MAN = 'MAN'
    FILIERE_LGTR = 'LGTR'
    FILIERE_RXTL = 'RXTL'
    FILIERE_MAEF = 'MAEF'

    FILIERE_CHOICES = [
        ('', 'Non renseignée'),
        (FILIERE_FINTECH, 'FINTECH'),
        (FILIERE_DS, 'DS'),
        (FILIERE_MAN, 'MAN'),
        (FILIERE_LGTR, 'LGTR'),
        (FILIERE_RXTL, 'RXTL'),
        (FILIERE_MAEF, 'MAEF'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='student_profile'
    )

    matricule = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=255)
    filiere = models.CharField(
        max_length=20,
        choices=FILIERE_CHOICES,
        blank=True,
        default=''
    )

    encadrant = models.ForeignKey(
        ProfessorProfile,
        on_delete=models.PROTECT,
        related_name='students'
    )

    entreprise = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        return f"{self.matricule} - {self.full_name}"


class StudentReference(models.Model):
    """Liste officielle pré-importée (CSV) utilisée pour auto-compléter l'inscription."""

    matricule = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=255)
    filiere = models.CharField(max_length=20, blank=True, default='')
    encadrant_name = models.CharField(max_length=255, blank=True, default='')

    def __str__(self):
        return f"{self.matricule} - {self.full_name}"
