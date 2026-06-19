"""Contexte global injecté dans tous les templates.

Centralise l'identité institutionnelle pour qu'elle soit modifiable à un
seul endroit (et surchargeable via variables d'environnement en production).
"""

import os


def institution(request):
    return {
        "INSTITUTION_NAME": os.environ.get(
            "INSTITUTION_NAME",
            "Institut Supérieur de Génie Industriel (ISGI)",
        ),
        "INSTITUTION_DEPARTMENT": os.environ.get(
            "INSTITUTION_DEPARTMENT",
            "Département de l'IUP",
        ),
        "ACADEMIC_YEAR": os.environ.get(
            "ACADEMIC_YEAR",
            "Année universitaire 2025 / 2026",
        ),
    }


def soutenance_deadline(request):
    """Date limite active des demandes de soutenance, disponible partout
    (page de connexion incluse) pour l'afficher de façon remarquable."""
    # Import local : évite tout import circulaire au chargement des apps.
    from django.utils import timezone
    from soutenances.models import Deadline

    deadline = (
        Deadline.objects.filter(is_active=True)
        .order_by("-deadline_date")
        .first()
    )

    closed = deadline.is_closed() if deadline else False
    days_left = None
    if deadline and not closed:
        days_left = (deadline.deadline_date - timezone.now()).days

    return {
        "SOUTENANCE_DEADLINE": deadline,
        "SOUTENANCE_DEADLINE_CLOSED": closed,
        "SOUTENANCE_DEADLINE_DAYS_LEFT": days_left,
    }
