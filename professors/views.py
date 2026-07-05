import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import role_required
from core.models import Notification, notify, notify_admins
from soutenances.models import (
    DefenseSchedule, Evaluation, Jury, JuryMember, JuryStudent, PFERequest,
    Result, mention_for_average,
)
from students.models import StudentProfile, StudentReference

from .forms import (
    EvaluationForm,
    ProfessorRequestDecisionForm,
)
from .models import ProfessorAvailability, ProfessorProfile
from . import slots


SESSION_START_DATE = datetime.date(2026, 6, 1)
SESSION_END_DATE = datetime.date(2026, 7, 10)
GRID_START_HOUR = 9
GRID_END_HOUR = 19


def get_professor_profile(request):
    try:
        return request.user.professor_profile
    except Exception:
        return None


def monday_of(value):
    return value - datetime.timedelta(days=value.weekday())


def clamp_week_start(week_start):
    earliest = monday_of(min(timezone.localdate(), SESSION_START_DATE))
    latest = monday_of(SESSION_END_DATE)

    if week_start < earliest:
        return earliest

    if week_start > latest:
        return latest

    return week_start


def parse_week_start(raw_value):
    if raw_value:
        try:
            return clamp_week_start(
                datetime.date.fromisoformat(raw_value)
            )
        except ValueError:
            pass

    return clamp_week_start(monday_of(timezone.localdate()))


@login_required
@role_required(["admin"])
def admin_professor_availability(request):
    today = timezone.localdate()

    # On ne considère que les disponibilités à venir (les créneaux passés ne
    # sont ni comptés ni affichés).
    availabilities = ProfessorAvailability.objects.select_related(
        "professor"
    ).filter(
        date__gte=today,
    ).order_by(
        "date",
        "start_time"
    )

    professor_id = request.GET.get("professor")
    filtered_professor = None

    if professor_id:
        availabilities = availabilities.filter(professor_id=professor_id)
        filtered_professor = ProfessorProfile.objects.filter(id=professor_id).first()

    # Regroupement par professeur : une seule ligne par professeur, avec ses
    # créneaux regroupés par date pour la section détails.
    professors_by_id = {}

    for availability in availabilities:
        professor = availability.professor

        entry = professors_by_id.get(professor.id)

        if entry is None:
            entry = {
                "professor": professor,
                "slots_count": 0,
                "days": {},
                "next_date": None,
            }
            professors_by_id[professor.id] = entry

        entry["slots_count"] += 1
        entry["days"].setdefault(availability.date, []).append(availability)

        if availability.date >= today and (
            entry["next_date"] is None or availability.date < entry["next_date"]
        ):
            entry["next_date"] = availability.date

    professor_rows = []

    for entry in professors_by_id.values():
        sorted_dates = sorted(entry["days"].keys())

        professor_rows.append({
            "professor": entry["professor"],
            "slots_count": entry["slots_count"],
            "days_count": len(sorted_dates),
            "next_date": entry["next_date"],
            "days": [
                {"date": date, "slots": entry["days"][date]}
                for date in sorted_dates
            ],
        })

    professor_rows.sort(key=lambda row: row["professor"].full_name.lower())

    # ── Programme des professeurs : soutenances déjà planifiées, affichées en
    #    face des disponibilités (jury, salle, horaires, nb d'étudiants). ──
    prof_ids = [row["professor"].id for row in professor_rows]
    # Un prof filtré sans aucune disponibilité peut quand même avoir des jurys :
    # on inclut son id pour afficher son programme.
    if filtered_professor and filtered_professor.id not in prof_ids:
        prof_ids.append(filtered_professor.id)
    memberships = JuryMember.objects.filter(
        professor_id__in=prof_ids,
        jury__defense_date__gte=today,
    ).select_related("jury")

    jury_ids = {m.jury_id for m in memberships}
    sched_by_jury = {}
    for schedule in DefenseSchedule.objects.filter(
        jury_student__jury_id__in=jury_ids
    ).select_related("jury_student"):
        sched_by_jury.setdefault(
            schedule.jury_student.jury_id, []
        ).append(schedule)

    prog_by_prof = {}
    for membership in memberships:
        day_schedules = sched_by_jury.get(membership.jury_id, [])
        starts = [s.start_time for s in day_schedules]
        ends = [s.end_time for s in day_schedules]
        prog_by_prof.setdefault(membership.professor_id, {}).setdefault(
            membership.jury.defense_date, []
        ).append({
            "jury": membership.jury,
            "students_count": len(day_schedules),
            "start": min(starts) if starts else None,
            "end": max(ends) if ends else None,
        })

    for row in professor_rows:
        prof_prog = prog_by_prof.get(row["professor"].id, {})
        total_students = 0
        juries_count = 0
        # Union des dates : jours où il est disponible + jours où il a un jury
        # (même sans disponibilité déclarée ce jour-là).
        avail_by_date = {day["date"]: day["slots"] for day in row["days"]}
        all_dates = sorted(set(avail_by_date) | set(prof_prog))
        merged_days = []
        day_conflicts = 0
        for d in all_dates:
            programme = prof_prog.get(d, [])
            # Détection de CHEVAUCHEMENT : deux jurys du même jour dont les
            # horaires se recoupent = le prof est doublement réservé (anomalie).
            ordered = sorted(
                [e for e in programme if e.get("start") and e.get("end")],
                key=lambda e: e["start"],
            )
            for e in ordered:
                e["conflict"] = False
            for i in range(1, len(ordered)):
                if ordered[i]["start"] < ordered[i - 1]["end"]:
                    ordered[i]["conflict"] = True
                    ordered[i - 1]["conflict"] = True
                    day_conflicts += 1
            merged_days.append({
                "date": d,
                "slots": avail_by_date.get(d, []),
                "programme": programme,
            })
            juries_count += len(programme)
            total_students += sum(e["students_count"] for e in programme)
        row["days"] = merged_days
        row["conflicts"] = day_conflicts
        row["scheduled_juries"] = juries_count
        row["scheduled_students"] = total_students

    # Prof filtré sans AUCUNE disponibilité mais avec des jurys : créer sa ligne.
    if filtered_professor and not any(
        r["professor"].id == filtered_professor.id for r in professor_rows
    ):
        prof_prog = prog_by_prof.get(filtered_professor.id, {})
        if prof_prog:
            all_dates = sorted(prof_prog.keys())
            juries_count = sum(len(prof_prog[d]) for d in all_dates)
            total_students = sum(
                e["students_count"] for d in all_dates for e in prof_prog[d]
            )
            professor_rows.append({
                "professor": filtered_professor,
                "slots_count": 0,
                "days_count": 0,
                "next_date": None,
                "days": [
                    {"date": d, "slots": [], "programme": prof_prog[d]}
                    for d in all_dates
                ],
                "scheduled_juries": juries_count,
                "scheduled_students": total_students,
            })

    # Professeurs sans AUCUNE disponibilité future (à relancer).
    with_future = set(
        ProfessorAvailability.objects.filter(date__gte=today)
        .values_list("professor_id", flat=True)
    )
    profs_sans_dispo = ProfessorProfile.objects.exclude(
        id__in=with_future
    ).order_by("full_name")

    return render(request, "professors/admin_professor_availability.html", {
        "professor_rows": professor_rows,
        "filtered_professor": filtered_professor,
        "all_professors": ProfessorProfile.objects.order_by("full_name"),
        "profs_sans_dispo": profs_sans_dispo,
        "profs_sans_dispo_count": profs_sans_dispo.count(),
    })


def _save_week_availability(request, professor):
    """Enregistre (remplace) les créneaux d'une semaine pour un professeur.
    Deux créneaux par jour : Matin et Après-midi (couvrant tout le créneau)."""
    week_start = parse_week_start(request.POST.get("week_start"))
    week_dates = [week_start + datetime.timedelta(days=i) for i in range(7)]

    ProfessorAvailability.objects.filter(
        professor=professor, date__in=week_dates
    ).delete()

    created_count = 0
    for day in week_dates:
        for slot in (slots.MORNING, slots.AFTERNOON):
            if request.POST.get(f"slot_{day.isoformat()}_{slot}"):
                start_time, end_time = slots.slot_bounds(day, slot)
                ProfessorAvailability.objects.create(
                    professor=professor,
                    date=day,
                    start_time=start_time,
                    end_time=end_time,
                )
                created_count += 1

    return week_start, created_count


def _availability_context(professor, week_param):
    """Construit le contexte de la grille hebdomadaire (Matin / Après-midi)."""
    week_start = parse_week_start(week_param)
    week_dates = [week_start + datetime.timedelta(days=i) for i in range(7)]

    existing = ProfessorAvailability.objects.filter(
        professor=professor,
        date__range=(week_dates[0], week_dates[-1]),
    )

    checked = set()  # (date, slot)
    for availability in existing:
        for slot in slots.slots_touched(
            availability.date, availability.start_time, availability.end_time
        ):
            checked.add((availability.date, slot))

    today = timezone.localdate()
    day_rows = []
    for day in week_dates:
        disabled = day < today or day > SESSION_END_DATE
        morning = slots.morning_slot(day)
        afternoon = slots.afternoon_slot(day)
        day_rows.append({
            "date": day,
            "disabled": disabled,
            "morning_checked": (day, slots.MORNING) in checked,
            "afternoon_checked": (day, slots.AFTERNOON) in checked,
            "morning_label": f"{morning[0].strftime('%Hh%M')}–{morning[1].strftime('%Hh%M')}",
            "afternoon_label": f"{afternoon[0].strftime('%Hh%M')}–{afternoon[1].strftime('%Hh%M')}",
        })

    earliest_week = clamp_week_start(monday_of(min(today, SESSION_START_DATE)))
    latest_week = clamp_week_start(monday_of(SESSION_END_DATE))

    return {
        "week_start": week_start,
        "week_end": week_dates[-1],
        "week_days": week_dates,
        "day_rows": day_rows,
        "can_go_prev": week_start > earliest_week,
        "can_go_next": week_start < latest_week,
        "prev_week": (week_start - datetime.timedelta(days=7)).isoformat(),
        "next_week": (week_start + datetime.timedelta(days=7)).isoformat(),
        "session_end_date": SESSION_END_DATE,
        "availabilities": ProfessorAvailability.objects.filter(
            professor=professor,
            date__gte=today,
        ).order_by("date", "start_time"),
    }


@login_required
@role_required(["professor"])
def professor_availability(request):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    if request.method == "POST":
        week_start, created_count = _save_week_availability(request, professor)
        messages.success(
            request,
            f"Disponibilités enregistrées pour la semaine du {week_start.strftime('%d/%m/%Y')} "
            f"({created_count} créneau(x))."
        )
        return redirect(f"{request.path}?week={week_start.isoformat()}")

    context = _availability_context(professor, request.GET.get("week"))
    context["is_admin"] = False
    return render(request, "professors/professor_availability.html", context)


@login_required
@role_required(["admin"])
def admin_professor_availability_edit(request):
    """L'administration peut renseigner les disponibilités à la place d'un
    professeur (qui peut aussi les remplir lui-même)."""
    professors = ProfessorProfile.objects.order_by("full_name")
    prof_id = request.POST.get("professor") or request.GET.get("professor")
    professor = ProfessorProfile.objects.filter(id=prof_id).first() if prof_id else None

    if request.method == "POST":
        if not professor:
            messages.error(request, "Sélectionnez d'abord un professeur.")
            return redirect("admin_professor_availability_edit")
        week_start, created_count = _save_week_availability(request, professor)
        messages.success(
            request,
            f"Disponibilités de {professor.full_name} enregistrées pour la semaine du "
            f"{week_start.strftime('%d/%m/%Y')} ({created_count} créneau(x))."
        )
        return redirect(
            f"{reverse('admin_professor_availability_edit')}"
            f"?professor={professor.id}&week={week_start.isoformat()}"
        )

    context = {
        "is_admin": True,
        "professors": professors,
        "selected_professor": professor,
    }
    if professor:
        context.update(_availability_context(professor, request.GET.get("week")))
    return render(request, "professors/professor_availability.html", context)


def merge_consecutive_hours(hours):
    """Turn [9, 10, 11, 14] into [(9, 12), (14, 15)] (end exclusive)."""
    if not hours:
        return []

    sorted_hours = sorted(hours)
    ranges = []
    range_start = sorted_hours[0]
    previous = sorted_hours[0]

    for hour in sorted_hours[1:]:
        if hour == previous + 1:
            previous = hour
            continue

        ranges.append((range_start, previous + 1))
        range_start = hour
        previous = hour

    ranges.append((range_start, previous + 1))
    return ranges


@login_required
@role_required(["professor"])
def professor_supervised_students(request):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    # Source officielle : StudentReference (inclut les étudiants sans compte)
    refs = StudentReference.objects.filter(
        encadrant_name=professor.full_name
    ).order_by("full_name")

    # Index des profils existants par matricule pour jointure rapide
    profile_map = {
        sp.matricule: sp
        for sp in StudentProfile.objects.filter(
            matricule__in=refs.values_list("matricule", flat=True)
        ).select_related("user").prefetch_related("pfe_request")
    }

    rows = []
    for ref in refs:
        profile = profile_map.get(ref.matricule)
        pfe_request = None
        if profile:
            try:
                pfe_request = profile.pfe_request
            except Exception:
                pass
        rows.append({
            "ref":        ref,
            "profile":    profile,
            "has_account": profile is not None,
            "pfe_request": pfe_request,
        })

    # Étudiants avec compte qui ne seraient pas dans StudentReference
    # (cas d'encadrant via FK directe sans référence officielle)
    ref_matricules = {r.matricule for r in refs}
    extra_profiles = professor.students.select_related("user").prefetch_related(
        "pfe_request"
    ).exclude(matricule__in=ref_matricules)
    for profile in extra_profiles.order_by("full_name"):
        pfe_request = None
        try:
            pfe_request = profile.pfe_request
        except Exception:
            pass
        rows.append({
            "ref": None,
            "profile": profile,
            "has_account": True,
            "pfe_request": pfe_request,
        })

    rows.sort(key=lambda r: (not r["has_account"], (r["ref"] or r["profile"]).full_name))

    return render(request, "professors/professor_supervised_students.html", {
        "professor": professor,
        "rows": rows,
    })


@login_required
@role_required(["professor"])
def professor_requests(request):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    requests = PFERequest.objects.filter(
        student__encadrant=professor
    ).select_related(
        "student",
        "student__encadrant",
    ).order_by(
        "-submitted_at"
    )

    return render(request, "professors/professor_requests.html", {
        "professor": professor,
        "requests": requests,
    })


@login_required
@role_required(["professor"])
def professor_request_detail(request, pk):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    pfe_request = get_object_or_404(
        PFERequest.objects.select_related(
            "student",
            "student__encadrant",
        ),
        pk=pk,
        student__encadrant=professor,
    )

    if request.method == "POST":
        action = request.POST.get("action")

        comment = (
            request.POST.get("professor_comment")
            or request.POST.get("comment")
            or ""
        )

        form = ProfessorRequestDecisionForm({
            "action": action,
            "professor_comment": comment,
        })

        if form.is_valid():
            if pfe_request.status != PFERequest.STATUS_PENDING_PROFESSOR:
                messages.error(request, "Cette demande a déjà été traitée.")
                return redirect("professor_request_detail", pk=pfe_request.pk)

            if action == "accept":
                pfe_request.professor_accept(professor)

                student_user = getattr(pfe_request.student, "user", None)
                notify(
                    student_user,
                    "Demande validée par votre encadrant",
                    "Votre encadrant a validé votre demande. Elle est transmise au département de l'IUP.",
                    "/student-dashboard/",
                    category=Notification.CATEGORY_REQUEST,
                )
                notify_admins(
                    "Demande à valider",
                    f"{pfe_request.student.full_name} ({pfe_request.student.matricule}) — demande validée par l'encadrant, en attente du département.",
                    "/soutenances/admin/demandes/",
                    category=Notification.CATEGORY_REQUEST,
                )

                messages.success(
                    request,
                    "La demande a été validée et envoyée au département de l'IUP."
                )

                return redirect("professor_requests")

            if action == "refuse":
                pfe_request.professor_refuse(professor, comment)

                student_user = getattr(pfe_request.student, "user", None)
                notify(
                    student_user,
                    "Demande refusée par votre encadrant",
                    "Votre encadrant a refusé votre demande. Consultez son commentaire et redéposez si nécessaire.",
                    "/student-dashboard/",
                    category=Notification.CATEGORY_REQUEST,
                )

                messages.success(request, "La demande a été refusée.")

                return redirect("professor_requests")
        else:
            messages.error(request, form.errors)

    return render(request, "professors/professor_request_detail.html", {
        "pfe_request": pfe_request,
    })


@login_required
@role_required(["professor"])
def professor_start_presentation(request, jury_student_id):
    professor = get_professor_profile(request)

    jury_student = get_object_or_404(
        JuryStudent.objects.select_related("president", "jury"),
        pk=jury_student_id,
    )

    if not professor or jury_student.president_id != professor.id:
        messages.error(request, "Seul le président de soutenance peut démarrer cette soutenance.")
        return redirect("professor_my_juries")

    if request.method == "POST":
        jury_student.start_presentation(request.user)
        messages.success(
            request,
            "La soutenance a été démarrée. Les évaluations sont maintenant ouvertes."
        )

    return redirect("professor_my_juries")


@login_required
@role_required(["professor"])
def professor_set_pfe_soutenable(request, jury_student_id):
    """Seul le président peut décider si le PFE est soutenable ou non."""
    professor = get_professor_profile(request)

    jury_student = get_object_or_404(
        JuryStudent.objects.select_related("student", "jury"),
        pk=jury_student_id,
    )

    if not professor or jury_student.president_id != professor.id:
        messages.error(request, "Seul le président de soutenance peut prendre cette décision.")
        return redirect("professor_my_juries")

    if not jury_student.presentation_started:
        messages.error(request, "La soutenance doit être démarrée avant de prendre cette décision.")
        return redirect("professor_my_juries")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "soutenable":
            JuryStudent.objects.filter(pk=jury_student.pk).update(
                pfe_soutenable_status=JuryStudent.PFE_SOUTENABLE_OUI,
                pfe_soutenable_decided_at=timezone.now(),
                pfe_soutenable_decided_by=request.user,
            )
            messages.success(request, f"PFE de {jury_student.student.full_name} déclaré soutenable.")
        elif action == "non_soutenable":
            JuryStudent.objects.filter(pk=jury_student.pk).update(
                pfe_soutenable_status=JuryStudent.PFE_SOUTENABLE_NON,
                pfe_soutenable_decided_at=timezone.now(),
                pfe_soutenable_decided_by=request.user,
            )
            messages.success(
                request,
                f"PFE de {jury_student.student.full_name} déclaré non soutenable. "
                "Les évaluations sont bloquées."
            )
        else:
            messages.error(request, "Action invalide.")

    return redirect("professor_my_juries")


@login_required
@role_required(["professor"])
def professor_my_juries(request):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    juries = Jury.objects.filter(
        members__professor=professor,
        is_validated=True,
    ).prefetch_related(
        "members__professor",
        "students__student",
        "students__student__encadrant",
    ).distinct().order_by(
        "-defense_date",
        "name",
    )

    now = timezone.localtime()

    return render(request, "professors/professor_my_juries.html", {
        "professor": professor,
        "juries": juries,
        "now_date": now.date(),
        "now_time": now.time(),
    })


@login_required
@role_required(["professor"])
def professor_evaluations(request):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    jury_students = JuryStudent.objects.filter(
        jury__members__professor=professor,
        jury__is_validated=True,
    ).select_related(
        "student",
        "jury",
        "student__encadrant",
    ).distinct().order_by(
        "jury__defense_date",
        "jury__name",
        "student__full_name",
    )

    rows = []

    for jury_student in jury_students:
        evaluation = Evaluation.objects.filter(
            jury_student=jury_student,
            professor=professor,
        ).first()

        rows.append({
            "jury_student": jury_student,
            "evaluation": evaluation,
        })

    return render(request, "professors/professor_evaluations.html", {
        "professor": professor,
        "rows": rows,
    })


def _auto_finalize_result(jury_student):
    """Dès que les 3 membres ont noté : calcule le résultat et le PUBLIE
    automatiquement s'il n'y a pas d'écart (< 3 pts). En cas d'écart (≥ 3),
    le résultat reste NON publié (bloqué pour le département).

    Renvoie True si publié auto, False si bloqué (écart), None si pas encore
    3 notes."""
    if jury_student.evaluations.filter(is_submitted=True).count() != 3:
        return None
    result, _ = Result.objects.get_or_create(jury_student=jury_student)
    if result.is_published:
        return True
    result.calculate_average()  # renseigne average, note_gap_value, has_note_gap_alert
    if result.has_note_gap_alert:
        return False
    result.publish()
    notify(
        getattr(jury_student.student, "user", None),
        "Résultat publié",
        "Votre résultat de soutenance est disponible.",
        "/student-dashboard/",
        category=Notification.CATEGORY_RESULT,
    )
    notify_admins(
        "Résultat publié automatiquement",
        f"{jury_student.student.full_name} — moyenne {result.average} "
        f"(sans écart).",
        "/admin-dashboard/results/",
        category=Notification.CATEGORY_RESULT,
    )
    return True


@login_required
@role_required(["professor"])
def professor_evaluation_detail(request, jury_student_id):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    jury_student = get_object_or_404(
        JuryStudent.objects.select_related(
            "student",
            "jury",
            "student__encadrant",
        ),
        pk=jury_student_id,
        jury__members__professor=professor,
        jury__is_validated=True,
    )

    existing_evaluation = Evaluation.objects.filter(
        jury_student=jury_student,
        professor=professor,
    ).first()

    if existing_evaluation:
        evaluation = existing_evaluation
    else:
        evaluation = Evaluation(
            jury_student=jury_student,
            professor=professor
        )

    if request.method == "POST":
        if existing_evaluation and existing_evaluation.is_locked:
            messages.error(
                request,
                "Cette évaluation est déjà envoyée et verrouillée."
            )

            return redirect(
                "professor_evaluation_detail",
                jury_student_id=jury_student.id
            )

        form = EvaluationForm(
            request.POST,
            instance=evaluation
        )

        if form.is_valid():
            evaluation = form.save(commit=False)
            evaluation.jury_student = jury_student
            evaluation.professor = professor

            action = request.POST.get("action")

            if action == "save":
                evaluation.save()

                messages.success(
                    request,
                    "Évaluation enregistrée comme brouillon."
                )

                return redirect(
                    "professor_evaluation_detail",
                    jury_student_id=jury_student.id
                )

            if action == "submit":
                evaluation.submit()
                published = _auto_finalize_result(jury_student)

                if published is True:
                    messages.success(
                        request,
                        "Évaluation envoyée. Les 3 notes sont là et sans écart : "
                        "le résultat a été publié automatiquement."
                    )
                elif published is False:
                    messages.warning(
                        request,
                        "Évaluation envoyée. Les 3 notes présentent un écart ≥ 3 "
                        "points : le résultat est en attente de validation du "
                        "département."
                    )
                else:
                    messages.success(request, "Évaluation envoyée avec succès.")

                return redirect("professor_evaluations")

            messages.error(request, "Action invalide.")
        else:
            messages.error(request, "Veuillez corriger les erreurs du formulaire.")
    else:
        form = EvaluationForm(instance=evaluation)

    return render(request, "professors/professor_evaluation_detail.html", {
        "professor": professor,
        "jury_student": jury_student,
        "evaluation": existing_evaluation,
        "form": form,
        "is_pfe_soutenable_pending": jury_student.pfe_soutenable_status == JuryStudent.PFE_SOUTENABLE_PENDING,
        "is_pfe_soutenable": jury_student.pfe_soutenable_status == JuryStudent.PFE_SOUTENABLE_OUI,
        "is_pfe_non_soutenable": jury_student.pfe_soutenable_status == JuryStudent.PFE_SOUTENABLE_NON,
        "is_evaluation_locked": bool(existing_evaluation and existing_evaluation.is_locked),
    })


@login_required
@role_required(["professor"])
def professor_submitted_notes(request):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    evaluations = Evaluation.objects.filter(
        professor=professor,
        is_submitted=True,
    ).select_related(
        "jury_student",
        "jury_student__student",
        "jury_student__jury",
    ).order_by(
        "-submitted_at"
    )

    return render(request, "professors/professor_submitted_notes.html", {
        "professor": professor,
        "evaluations": evaluations,
    })

@login_required
@role_required(["professor"])
def professor_jury_student_dossier(request, jury_student_id):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    jury_student = get_object_or_404(
        JuryStudent.objects.select_related(
            "student",
            "student__encadrant",
            "jury",
            "president",
        ),
        pk=jury_student_id,
        jury__members__professor=professor,
        jury__is_validated=True,
    )

    pfe_request = PFERequest.objects.filter(student=jury_student.student).first()

    return render(request, "professors/professor_jury_student_dossier.html", {
        "jury_student": jury_student,
        "pfe_request": pfe_request,
        "professor": professor,
    })


@login_required
@role_required(["professor"])
def professor_president_results(request):
    professor = get_professor_profile(request)

    if not professor:
        messages.error(request, "Votre profil professeur n'est pas encore configuré.")
        return redirect("professor_dashboard")

    assignments = JuryStudent.objects.filter(
        president=professor,
        jury__is_validated=True,
    ).select_related(
        "student",
        "student__encadrant",
        "jury",
        "result",
    ).prefetch_related(
        "evaluations__professor",
        "jury__members",
    ).order_by(
        "jury__defense_date",
        "student__full_name",
    )

    from soutenances.views import compute_criteria_averages

    rows = []
    for assignment in assignments:
        result = getattr(assignment, "result", None)
        published_result = result if (result and result.is_published) else None

        avgs = compute_criteria_averages(assignment)
        complete = avgs["complete"]
        computed_average = avgs["avg_finale"] if complete else None

        mention_average = published_result.average if published_result else computed_average
        mention = mention_for_average(mention_average) if mention_average is not None else None

        member_notes = []
        if complete:
            member_notes = sorted(
                avgs["submitted"], key=lambda e: e.professor.full_name.lower()
            )

        rows.append({
            "assignment": assignment,
            "published_result": published_result,
            "computed_average": computed_average,
            "avg_rapport": avgs["avg_rapport"] if complete else None,
            "avg_presentation": avgs["avg_presentation"] if complete else None,
            "avg_questions": avgs["avg_questions"] if complete else None,
            "mention": mention if complete or published_result else None,
            "complete": complete,
            "evals_count": avgs["submitted_count"],
            "members_count": avgs["members_count"],
            "member_notes": member_notes,
        })

    return render(request, "professors/professor_president_results.html", {
        "professor": professor,
        "rows": rows,
    })
