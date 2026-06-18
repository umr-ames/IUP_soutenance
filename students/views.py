from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render

from accounts.decorators import role_required
from documents.models import DocumentTemplate
from soutenances.forms import PFERequestForm
from soutenances.models import Deadline, PFERequest

from .models import StudentReference


def get_active_deadline():
    return Deadline.objects.filter(is_active=True).order_by("-deadline_date").first()


@login_required
@role_required(["student"])
def submit_pfe_request(request):
    student = getattr(request.user, "student_profile", None)
    if not student:
        messages.error(request, "Votre profil etudiant n'est pas encore configure.")
        return redirect("student_dashboard")

    existing_request = PFERequest.objects.filter(student=student).first()

    REFUSED_STATUSES = (
        PFERequest.STATUS_REFUSED_PROFESSOR,
        PFERequest.STATUS_REFUSED_ADMIN,
    )

    # Bloquer uniquement si une demande non refusée existe déjà
    if existing_request and existing_request.status not in REFUSED_STATUSES:
        messages.info(request, "Vous avez deja envoye une demande de soutenance.")
        return redirect("student_dashboard")

    deadline = get_active_deadline()
    if deadline and deadline.is_closed():
        messages.error(
            request,
            "La date limite est depassee. Vous ne pouvez plus envoyer une demande."
        )
        return redirect("student_dashboard")

    if request.method == "POST":
        form = PFERequestForm(request.POST, request.FILES)
        if form.is_valid():
            if existing_request and existing_request.status in REFUSED_STATUSES:
                # Renvoi après refus : réinitialiser la demande existante
                existing_request.status = PFERequest.STATUS_PENDING_PROFESSOR
                existing_request.professor_comment = None
                existing_request.admin_comment = None
                existing_request.professor_reviewed_at = None
                existing_request.admin_reviewed_at = None
                existing_request.reviewed_by_professor = None
                existing_request.reviewed_by_admin = None
                existing_request.reviewed_at = None
                existing_request.reviewed_by = None
                updated = form.save(commit=False)
                if updated.rapport_stage:
                    existing_request.rapport_stage = updated.rapport_stage
                existing_request.save()
                messages.success(
                    request,
                    "Votre demande a ete renvoyee avec succes. Elle repart en validation encadrant."
                )
            else:
                pfe_request = form.save(commit=False)
                pfe_request.student = student
                pfe_request.save()
                messages.success(
                    request,
                    "Votre demande de soutenance a ete envoyee avec succes."
                )
            return redirect("student_dashboard")
    else:
        form = PFERequestForm()

    document_templates = DocumentTemplate.objects.filter(
        is_active=True,
        template_type=DocumentTemplate.TYPE_STUDENT_REQUEST,
    ).order_by("-uploaded_at")
    official_template = document_templates.first()

    return render(request, "students/submit_pfe_request.html", {
        "form": form,
        "deadline": deadline,
        "document_templates": document_templates,
        "official_template": official_template,
    })


def lookup_student_reference(request):
    matricule = request.GET.get("matricule", "").strip()

    if not matricule:
        return JsonResponse({"found": False})

    reference = StudentReference.objects.filter(matricule__iexact=matricule).first()

    if not reference:
        return JsonResponse({"found": False})

    return JsonResponse({
        "found": True,
        "full_name": reference.full_name,
        "filiere": reference.filiere,
        "encadrant_name": reference.encadrant_name,
    })
