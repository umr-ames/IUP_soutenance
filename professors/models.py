from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError


class ProfessorProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='professor_profile',
        blank=True,
        null=True
    )

    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30, blank=True, null=True)

    def __str__(self):
        return self.full_name


class ProfessorAvailability(models.Model):
    professor = models.ForeignKey(
        ProfessorProfile,
        on_delete=models.CASCADE,
        related_name='availabilities'
    )

    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ['date', 'start_time']
        unique_together = ('professor', 'date', 'start_time', 'end_time')

    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError("L'heure de fin doit être après l'heure de début.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.professor.full_name} - {self.date} ({self.start_time} - {self.end_time})"