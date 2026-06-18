from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_ADMIN = 'admin'
    ROLE_PROFESSOR = 'professor'
    ROLE_STUDENT = 'student'

    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Administrateur'),
        (ROLE_PROFESSOR, 'Professeur'),
        (ROLE_STUDENT, 'Étudiant'),
    ]

    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_STUDENT
    )

    phone_number = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True
    )

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.ROLE_ADMIN
        super().save(*args, **kwargs)

    def is_admin_role(self):
        return self.role == self.ROLE_ADMIN

    def is_professor_role(self):
        return self.role == self.ROLE_PROFESSOR

    def is_student_role(self):
        return self.role == self.ROLE_STUDENT

    @property
    def display_name(self):
        if self.role == self.ROLE_PROFESSOR:
            try:
                return self.professor_profile.full_name
            except Exception:
                return self.username

        if self.role == self.ROLE_STUDENT:
            try:
                return self.student_profile.full_name
            except Exception:
                return self.username

        full_name = self.get_full_name()
        if full_name:
            return full_name

        return self.username

    def __str__(self):
        return self.display_name