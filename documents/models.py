from django.db import models


class DocumentTemplate(models.Model):
    TYPE_STUDENT_REQUEST = 'student_request'
    TYPE_EVALUATION = 'evaluation'
    TYPE_OTHER = 'other'

    TYPE_CHOICES = [
        (TYPE_STUDENT_REQUEST, "Modèle de demande étudiant"),
        (TYPE_EVALUATION, "Fiche d'évaluation"),
        (TYPE_OTHER, 'Autre'),
    ]

    title = models.CharField(max_length=255)
    template_type = models.CharField(
        max_length=30,
        choices=TYPE_CHOICES,
        default=TYPE_STUDENT_REQUEST,
    )
    file = models.FileField(upload_to='templates_documents/')
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
