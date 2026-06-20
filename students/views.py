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
        messages.error(request, "Votre profil étudiant n'est pas encore configuré.")
        return redirect("student_dashboard")

    existing_request = PFERequest.objects.filter(student=student).first()

    REFUSED_STATUSES = (
        PFERequest.STATUS_REFUSED_PROFESSOR,
        PFERequest.STATUS_REFUSED_ADMIN,
    )

    def dossier_complete(req):
        return bool(req.rapport_stage) and bool(req.authorization_document) and bool(req.attestation_stage)

    is_refused = bool(existing_request) and existing_request.status in REFUSED_STATUSES

    # Dossier déjà déposé mais incomplet (ex. rapport manquant) : l'étudiant
    # peut le compléter sans changer le statut de sa demande.
    completing = (
        bool(existing_request)
        and not is_refused
        and not dossier_complete(existing_request)
    )

    # Bloquer uniquement si la demande est complète et non refusée.
    if existing_request and not is_refused and not completing:
        messages.info(request, "Vous avez déjà envoyé une demande de soutenance.")
        return redirect("student_dashboard")

    deadline = get_active_deadline()
    # La date limite bloque une nouvelle demande ou un renvoi, mais jamais la
    # complétion d'un dossier déjà déposé (l'étudiant doit pouvoir le régulariser).
    if deadline and deadline.is_closed() and not completing:
        messages.error(
            request,
            "La date limite est dépassée. Vous ne pouvez plus envoyer une demande."
        )
        return redirect("student_dashboard")

    if request.method == "POST":
        if completing:
            form = PFERequestForm(request.POST, request.FILES, instance=existing_request)
            if form.is_valid():
                form.save()
                # Si un redépôt était demandé et que la pièce est de nouveau
                # présente, on efface la demande de redépôt.
                reupload_field = {
                    "authorization": "authorization_document",
                    "attestation": "attestation_stage",
                    "rapport": "rapport_stage",
                }.get(existing_request.reupload_document)
                if reupload_field and getattr(existing_request, reupload_field):
                    existing_request.reupload_document = ""
                    existing_request.reupload_comment = None
                    existing_request.save(
                        update_fields=["reupload_document", "reupload_comment"]
                    )
                messages.success(
                    request,
                    "Votre dossier a été complété avec succès. La pièce manquante a été ajoutée."
                )
                return redirect("student_dashboard")
        else:
            form = PFERequestForm(request.POST, request.FILES)
            if form.is_valid():
                if is_refused:
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
                    if updated.authorization_document:
                        existing_request.authorization_document = updated.authorization_document
                    if updated.attestation_stage:
                        existing_request.attestation_stage = updated.attestation_stage
                    if updated.rapport_stage:
                        existing_request.rapport_stage = updated.rapport_stage
                    existing_request.save()
                    messages.success(
                        request,
                        "Votre demande a été renvoyée avec succès. Elle repart en validation encadrant."
                    )
                else:
                    pfe_request = form.save(commit=False)
                    pfe_request.student = student
                    pfe_request.save()
                    messages.success(
                        request,
                        "Votre demande de soutenance a été envoyée avec succès."
                    )
                return redirect("student_dashboard")
    else:
        form = PFERequestForm(instance=existing_request) if completing else PFERequestForm()

    document_templates = DocumentTemplate.objects.filter(
        is_active=True,
        template_type=DocumentTemplate.TYPE_STUDENT_REQUEST,
    ).order_by("-uploaded_at")
    official_template = document_templates.first()

    return render(request, "students/submit_pfe_request.html", {
        "form": form,
        "deadline": deadline,
        "completing": completing,
        "document_templates": document_templates,
        "official_template": official_template,
    })


@login_required
@role_required(["student"])
def edit_entreprise(request):
    student = getattr(request.user, "student_profile", None)
    if not student:
        messages.error(request, "Votre profil étudiant n'est pas encore configuré.")
        return redirect("student_dashboard")

    if request.method == "POST":
        entreprise = (request.POST.get("entreprise") or "").strip()
        if not entreprise:
            messages.error(request, "Le nom de l'entreprise ne peut pas être vide.")
        else:
            student.entreprise = entreprise
            student.save(update_fields=["entreprise"])
            messages.success(
                request,
                "Le nom de votre entreprise de stage a été mis à jour."
            )
            return redirect("student_dashboard")

    return render(request, "students/edit_entreprise.html", {"student": student})


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
