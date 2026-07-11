from django.conf import settings
from django.db import models


class Notification(models.Model):
    """Notification in-app destinée à un utilisateur (étudiant, professeur ou
    chef de département)."""

    CATEGORY_JURY = "jury"
    CATEGORY_RESULT = "result"
    CATEGORY_DOCUMENT = "document"
    CATEGORY_REQUEST = "request"
    CATEGORY_INFO = "info"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    url = models.CharField(max_length=300, blank=True, default="")
    category = models.CharField(max_length=30, blank=True, default=CATEGORY_INFO)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return f"{self.recipient_id} - {self.title}"


def notify(recipient, title, message="", url="", category=Notification.CATEGORY_INFO):
    """Crée une notification pour un utilisateur. Sans effet si recipient est
    None (robustesse : certains objets peuvent ne pas avoir de compte lié)."""
    if recipient is None:
        return None
    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message or "",
        url=url or "",
        category=category or Notification.CATEGORY_INFO,
    )


def notify_admins(title, message="", url="", category=Notification.CATEGORY_INFO):
    """Notifie tous les chefs de département (rôle admin)."""
    from accounts.models import CustomUser

    created = []
    for user in CustomUser.objects.filter(role="admin"):
        created.append(notify(user, title, message, url, category))
    return created


class SurveyConfig(models.Model):
    """Interrupteur d'ouverture du sondage de satisfaction (une seule ligne)."""
    student_open = models.BooleanField(default=True)
    professor_open = models.BooleanField(default=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SurveyResponse(models.Model):
    """Réponse (anonyme) au sondage de satisfaction. Le lien à l'utilisateur ne
    sert qu'à empêcher les doublons et à calculer le taux de participation ;
    l'admin ne voit que des résultats agrégés + commentaires anonymes.

    5 questions notées de 1 (Très insatisfait) à 5 (Très satisfait) + un
    commentaire libre. Les libellés dépendent du rôle (voir core.views)."""

    ROLE_STUDENT = "student"
    ROLE_PROFESSOR = "professor"
    ROLE_CHOICES = [(ROLE_STUDENT, "Étudiant"), (ROLE_PROFESSOR, "Professeur")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="survey_response",
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    q1 = models.PositiveSmallIntegerField()
    q2 = models.PositiveSmallIntegerField()
    q3 = models.PositiveSmallIntegerField()
    q4 = models.PositiveSmallIntegerField()
    q5 = models.PositiveSmallIntegerField()
    comment = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sondage {self.role} #{self.pk}"
