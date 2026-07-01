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
