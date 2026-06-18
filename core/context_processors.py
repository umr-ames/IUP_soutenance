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
