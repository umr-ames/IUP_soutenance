import mimetypes
from pathlib import Path
from urllib.parse import unquote

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils._os import safe_join

from accounts.models import CustomUser
from professors.models import ProfessorProfile
from soutenances.models import JuryStudent, PFERequest


PFE_DOCUMENT_FIELDS = (
    "authorization_document",
    "rapport_stage",
    "attestation_stage",
    "rapport_pfe",
    "fiche_demande",
    "fiche_evaluation",
)


def _normalize_media_path(path):
    clean_path = unquote(path or "").replace("\\", "/").lstrip("/")

    if not clean_path or clean_path.startswith("../") or "/../" in clean_path:
        raise Http404("Fichier introuvable.")

    return clean_path


def _get_pfe_request_for_file(clean_path):
    query = Q()
    for field_name in PFE_DOCUMENT_FIELDS:
        query |= Q(**{field_name: clean_path})

    return (
        PFERequest.objects
        .select_related("student__user", "student__encadrant")
        .filter(query)
        .first()
    )


def _can_access_pfe_document(user, pfe_request):
    if user.role == CustomUser.ROLE_ADMIN:
        return True

    if user.role == CustomUser.ROLE_STUDENT:
        return pfe_request.student.user_id == user.id

    if user.role == CustomUser.ROLE_PROFESSOR:
        professor = ProfessorProfile.objects.filter(user=user).first()
        if not professor:
            return False

        if pfe_request.student.encadrant_id == professor.id:
            return True

        return JuryStudent.objects.filter(
            student=pfe_request.student,
            jury__members__professor=professor,
        ).exists()

    return False


@login_required
def protected_media(request, path):
    clean_path = _normalize_media_path(path)

    try:
        file_path = Path(safe_join(settings.MEDIA_ROOT, clean_path))
    except ValueError as exc:
        raise Http404("Fichier introuvable.") from exc

    if not file_path.is_file():
        raise Http404("Fichier introuvable.")

    if request.user.role == CustomUser.ROLE_ADMIN:
        return _file_response(file_path)

    if clean_path.startswith("templates_documents/"):
        return _file_response(file_path)

    pfe_request = _get_pfe_request_for_file(clean_path)
    if not pfe_request:
        raise Http404("Fichier introuvable.")

    if not _can_access_pfe_document(request.user, pfe_request):
        raise PermissionDenied("Vous n'avez pas l'autorisation d'accéder à ce fichier.")

    return _file_response(file_path)


def _file_response(file_path):
    content_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        open(file_path, "rb"),
        content_type=content_type or "application/octet-stream",
    )
