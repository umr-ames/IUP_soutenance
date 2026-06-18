import csv
import io
import re
import tempfile
import unicodedata

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.management import call_command
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import redirect, render

from accounts.decorators import role_required
from accounts.models import CustomUser
from documents.models import DocumentTemplate
from professors.models import ProfessorProfile
from students.models import StudentProfile
from soutenances.models import (
    Deadline,
    DefenseSchedule,
    Evaluation,
    Jury,
    JuryStudent,
    PFERequest,
    Result,
)
from .forms import ImportPeopleForm, ImportStudentReferencesForm


DEFAULT_IMPORT_PASSWORD = "iup2026"


def dashboard_redirect(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if request.user.role == "admin":
        return redirect("admin_dashboard")

    if request.user.role == "professor":
        return redirect("professor_dashboard")

    if request.user.role == "student":
        return redirect("student_dashboard")

    return redirect("login")


@login_required
@role_required(["admin"])
def admin_dashboard(request):
    stats = {
        "students": StudentProfile.objects.count(),
        "professors": ProfessorProfile.objects.count(),
        "total_requests": PFERequest.objects.count(),
        "pending_professor_requests": PFERequest.objects.filter(
            status=PFERequest.STATUS_PENDING_PROFESSOR
        ).count(),
        "pending_admin_requests": PFERequest.objects.filter(
            status=PFERequest.STATUS_PENDING_ADMIN
        ).count(),
        "accepted_requests": PFERequest.objects.filter(
            status=PFERequest.STATUS_ACCEPTED
        ).count(),
        "refused_requests": PFERequest.objects.filter(
            status__in=[
                PFERequest.STATUS_REFUSED_BY_PROFESSOR,
                PFERequest.STATUS_REFUSED_BY_ADMIN,
            ]
        ).count(),
        "juries": Jury.objects.count(),
        "published_juries": Jury.objects.filter(is_validated=True).count(),
        "draft_juries": Jury.objects.filter(is_validated=False).count(),
        "planned_defenses": DefenseSchedule.objects.count(),
        "published_results": Result.objects.filter(is_published=True).count(),
        "unpublished_results": Result.objects.filter(
            average__isnull=False,
            is_published=False
        ).count(),
        "note_gap_alerts": Result.objects.filter(has_note_gap_alert=True).count(),
        "score_16_plus": Result.objects.filter(average__gte=16).count(),
        "score_14_1599": Result.objects.filter(average__gte=14, average__lt=16).count(),
        "score_12_1399": Result.objects.filter(average__gte=12, average__lt=14).count(),
        "score_10_1199": Result.objects.filter(average__gte=10, average__lt=12).count(),
        "score_below_10": Result.objects.filter(average__lt=10).count(),
    }

    recent_requests = PFERequest.objects.select_related(
        "student",
        "student__encadrant",
    ).order_by("-submitted_at")[:6]

    upcoming_schedules = DefenseSchedule.objects.select_related(
        "jury_student__student",
        "jury_student__jury",
    ).order_by("jury_student__jury__defense_date", "start_time")[:6]

    gap_alerts = Result.objects.filter(
        has_note_gap_alert=True
    ).select_related("jury_student__student", "jury_student__jury")[:5]

    draft_juries = Jury.objects.filter(
        is_validated=False
    ).order_by("-created_at")[:5]

    results_to_publish = Result.objects.filter(
        average__isnull=False,
        is_published=False,
    ).select_related("jury_student__student", "jury_student__jury")[:5]

    return render(request, "core/admin_dashboard.html", {
        "stats": stats,
        "recent_requests": recent_requests,
        "upcoming_schedules": upcoming_schedules,
        "gap_alerts": gap_alerts,
        "draft_juries": draft_juries,
        "results_to_publish": results_to_publish,
    })


@login_required
@role_required(["professor"])
def professor_dashboard(request):
    professor = getattr(request.user, "professor_profile", None)
    if not professor:
        messages.warning(request, "Votre profil professeur n'est pas encore configuré.")
        return render(request, "core/professor_dashboard.html", {
            "professor": None,
        })

    supervised_students = StudentProfile.objects.filter(
        encadrant=professor
    ).select_related("pfe_request")

    jury_students = JuryStudent.objects.filter(
        jury__members__professor=professor
    ).select_related(
        "student",
        "student__encadrant",
        "jury",
    ).distinct()

    pending_requests_count = PFERequest.objects.filter(
        student__encadrant=professor,
        status=PFERequest.STATUS_PENDING_PROFESSOR,
    ).count()
    submitted_notes = professor.given_evaluations.filter(is_submitted=True).count()
    pending_evaluations = 0
    for assignment in jury_students:
        evaluation = assignment.evaluations.filter(professor=professor).first()
        if evaluation is None or not evaluation.is_submitted:
            pending_evaluations += 1

    availability_blocks = professor.availabilities.order_by("date", "start_time")[:5]
    availability_count = professor.availabilities.count()

    to_start_count = JuryStudent.objects.filter(
        president=professor,
        presentation_started=False,
        jury__is_validated=True,
    ).count()

    return render(request, "core/professor_dashboard.html", {
        "professor": professor,
        "supervised_students_count": supervised_students.count(),
        "pending_requests_count": pending_requests_count,
        "juries_count": Jury.objects.filter(members__professor=professor).distinct().count(),
        "pending_evaluations": pending_evaluations,
        "submitted_notes": submitted_notes,
        "availability_blocks": availability_blocks,
        "availability_count": availability_count,
        "to_start_count": to_start_count,
        "supervised_students": supervised_students[:6],
    })


@login_required
@role_required(["student"])
def student_dashboard(request):
    student = getattr(request.user, "student_profile", None)
    pfe_request = None
    jury_assignment = None
    schedule = None
    result = None

    if student:
        pfe_request = getattr(student, "pfe_request", None)
        jury_assignment = getattr(student, "jury_assignment", None)
        if jury_assignment and not jury_assignment.jury.is_validated:
            jury_assignment = None
        if jury_assignment:
            schedule = getattr(jury_assignment, "schedule", None)
            candidate_result = getattr(jury_assignment, "result", None)
            if candidate_result and candidate_result.is_published:
                result = candidate_result

    deadline = Deadline.objects.filter(
        is_active=True
    ).order_by("-deadline_date").first()

    document_templates = DocumentTemplate.objects.filter(
        is_active=True,
        template_type=DocumentTemplate.TYPE_STUDENT_REQUEST,
    ).order_by("-uploaded_at")
    official_template = document_templates.first()
    deadline_closed = deadline.is_closed() if deadline else False

    return render(request, "core/student_dashboard.html", {
        "student": student,
        "pfe_request": pfe_request,
        "deadline": deadline,
        "deadline_closed": deadline_closed,
        "document_templates": document_templates,
        "official_template": official_template,
        "jury_assignment": jury_assignment,
        "schedule": schedule,
        "result": result,
    })


@login_required
@role_required(["admin"])
def admin_student_list(request):
    students = StudentProfile.objects.select_related(
        "user",
        "encadrant",
    ).annotate(
        has_request=Count("pfe_request")
    ).order_by("filiere", "full_name")

    return render(request, "core/admin_students.html", {
        "students": students,
    })


@login_required
@role_required(["admin"])
def admin_professor_list(request):
    professors = ProfessorProfile.objects.select_related("user").annotate(
        supervised_count=Count("students", distinct=True),
        jury_count=Count("jury_memberships__jury", distinct=True),
        availability_count=Count("availabilities", distinct=True),
    ).order_by("full_name")

    return render(request, "core/admin_professors.html", {
        "professors": professors,
    })


@login_required
@role_required(["admin"])
def admin_import_people(request):
    if request.method == "POST":
        form = ImportPeopleForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                rows = read_import_rows(form.cleaned_data["data_file"])
                result = import_people_rows(rows)
            except Exception as exc:
                messages.error(request, f"Import impossible : {exc}")
            else:
                messages.success(
                    request,
                    "Import terminé : "
                    f"{result['created_students']} étudiants créés, "
                    f"{result['updated_students']} mis à jour, "
                    f"{result['created_professors']} professeurs créés."
                )
                if result["errors"]:
                    messages.warning(
                        request,
                        f"{len(result['errors'])} ligne(s) ignorée(s)."
                    )
                return render(request, "core/admin_import.html", {
                    "form": ImportPeopleForm(),
                    "result": result,
                })
    else:
        form = ImportPeopleForm()

    return render(request, "core/admin_import.html", {
        "form": form,
    })


@login_required
@role_required(["admin"])
def admin_import_student_references(request):
    if request.method == "POST":
        form = ImportStudentReferencesForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data["data_file"]
            extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
            temporary_path = None

            try:
                with tempfile.NamedTemporaryFile(
                    suffix=f".{extension}",
                    delete=False,
                ) as temporary_file:
                    for chunk in uploaded_file.chunks():
                        temporary_file.write(chunk)
                    temporary_path = temporary_file.name

                output = io.StringIO()
                call_command(
                    "import_student_references",
                    temporary_path,
                    stdout=output,
                )
            except Exception as exc:
                messages.error(request, f"Import impossible : {exc}")
            else:
                messages.success(
                    request,
                    "Liste officielle importée avec succès. "
                    "Les professeurs manquants ont été créés automatiquement."
                )
                return render(request, "core/admin_import_references.html", {
                    "form": ImportStudentReferencesForm(),
                    "report": output.getvalue(),
                })
            finally:
                if temporary_path:
                    try:
                        import os
                        os.unlink(temporary_path)
                    except Exception:
                        pass
    else:
        form = ImportStudentReferencesForm()

    return render(request, "core/admin_import_references.html", {
        "form": form,
    })


def read_import_rows(uploaded_file):
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()
    if extension == "csv":
        return read_csv_rows(uploaded_file)
    if extension == "xlsx":
        return read_xlsx_rows(uploaded_file)
    raise ValueError("Format non pris en charge.")


def read_csv_rows(uploaded_file):
    raw = uploaded_file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")

    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.reader(io.StringIO(text), dialect)
    return normalize_table_rows(list(reader))


def read_xlsx_rows(uploaded_file):
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError(
            "Le support Excel necessite openpyxl. Installez requirements.txt."
        ) from exc

    workbook = load_workbook(uploaded_file, read_only=True, data_only=True)
    sheet = workbook.active
    return normalize_table_rows(list(sheet.iter_rows(values_only=True)))


def normalize_table_rows(raw_rows):
    rows = [list(row) for row in raw_rows if any(cell for cell in row)]
    if not rows:
        return []

    headers = [_header_key(cell) for cell in rows[0]]
    normalized_rows = []
    for index, row in enumerate(rows[1:], start=2):
        data = {}
        for position, value in enumerate(row):
            if position < len(headers) and headers[position]:
                data[headers[position]] = (str(value).strip() if value is not None else "")
        data["_line"] = index
        normalized_rows.append(data)
    return normalized_rows


def _header_key(value):
    aliases = {
        "matricule": "matricule",
        "nomcomplet": "full_name",
        "nometprenom": "full_name",
        "fullname": "full_name",
        "etudiant": "full_name",
        "filiere": "filiere",
        "encadrant": "encadrant",
        "superviseur": "encadrant",
    }
    key = _ascii_slug(value).replace("_", "")
    return aliases.get(key, key)


def _ascii_slug(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value


def normalize_filiere(value):
    raw = str(value or "").strip().upper()
    compact = re.sub(r"[^A-Z0-9]+", "", raw)
    mapping = {
        "FINTECH": "FINTECH",
        "FIN": "FINTECH",
        "DS": "DS",
        "DATASCIENCE": "DS",
        "MAN": "MAN",
        "MANAGEMENT": "MAN",
        "LGTR": "LGTR",
        "RXTL": "RXTL",
        "MAEF": "MAEF",
    }
    return mapping.get(compact)


@transaction.atomic
def import_people_rows(rows):
    result = {
        "created_students": 0,
        "updated_students": 0,
        "created_professors": 0,
        "errors": [],
    }

    for row in rows:
        matricule = row.get("matricule", "").strip()
        full_name = row.get("full_name", "").strip()
        filiere = normalize_filiere(row.get("filiere", ""))
        encadrant_name = row.get("encadrant", "").strip()

        if not all([matricule, full_name, filiere, encadrant_name]):
            result["errors"].append({
                "line": row.get("_line"),
                "message": "matricule, nom complet, filiere ou encadrant manquant",
            })
            continue

        professor, professor_created = get_or_create_professor(encadrant_name)
        if professor_created:
            result["created_professors"] += 1

        user, _ = get_or_create_user(
            username_base=matricule,
            role=CustomUser.ROLE_STUDENT,
            full_name=full_name,
        )

        student, created = StudentProfile.objects.get_or_create(
            matricule=matricule,
            defaults={
                "user": user,
                "full_name": full_name,
                "filiere": filiere,
                "encadrant": professor,
            }
        )

        if created:
            result["created_students"] += 1
        else:
            student.user = student.user or user
            student.full_name = full_name
            student.filiere = filiere
            student.encadrant = professor
            student.save()
            result["updated_students"] += 1

    return result


def get_or_create_professor(full_name):
    professor = ProfessorProfile.objects.filter(full_name__iexact=full_name).first()
    if professor:
        return professor, False

    return ProfessorProfile.objects.create(full_name=full_name), True


def get_or_create_user(username_base, role, full_name):
    username = unique_username(username_base)
    user = CustomUser.objects.filter(username=username_base).first()
    if user:
        user.role = role
        user.save(update_fields=["role"])
        return user, False

    user = CustomUser(username=username, role=role, is_active=True)
    parts = full_name.split(" ", 1)
    user.first_name = parts[0]
    user.last_name = parts[1] if len(parts) > 1 else ""
    user.set_password(DEFAULT_IMPORT_PASSWORD)
    user.save()
    return user, True


def unique_username(username_base):
    base = _ascii_slug(username_base) or "user"
    base = base[:145]
    candidate = base
    suffix = 1
    while CustomUser.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base}_{suffix}"[:150]
    return candidate
