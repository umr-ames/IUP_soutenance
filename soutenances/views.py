from datetime import date as date_cls, datetime, time, timedelta
from itertools import combinations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.decorators import role_required
from professors.models import ProfessorAvailability, ProfessorProfile
from students.models import StudentProfile

from .forms import (
    DeadlineForm,
    JuryForm,
    JuryGenerationForm,
    JuryAddMemberForm,
    JuryMembersForSlotForm,
    JurySmartMembersForm,
    JuryStudentAssignForm,
    PFERequestDecisionForm,
    PFERequestForm,
    PlanningGenerationForm,
    TargetedJuryGenerationForm,
)

from .models import (
    Deadline,
    DefenseSchedule,
    Evaluation,
    Jury,
    JuryMember,
    JuryStudent,
    PFERequest,
    Result,
    FiliereExpert,
    mention_for_average,
)

from .pdf import simple_pdf_response


DEFENSE_DURATION_MINUTES = 20
MAX_SIMULTANEOUS_JURIES = 8

# Date limite des soutenances : aucune soutenance possible après cette date.
DEFENSE_DEADLINE = date_cls(2026, 7, 10)


@login_required
@role_required(["student"])
def submit_pfe_request(request):
    student = get_object_or_404(
        StudentProfile.objects.select_related("encadrant", "user"),
        user=request.user,
    )

    deadline = Deadline.objects.filter(
        is_active=True
    ).order_by("-deadline_date").first()

    if deadline and deadline.is_closed():
        messages.error(request, "La date limite de dépôt des demandes est dépassée.")
        return redirect("student_dashboard")

    existing_request = PFERequest.objects.filter(student=student).first()

    if existing_request and existing_request.status in [
        PFERequest.STATUS_PENDING_PROFESSOR,
        PFERequest.STATUS_PENDING_ADMIN,
        PFERequest.STATUS_ACCEPTED,
    ]:
        messages.warning(request, "Vous avez déjà une demande en cours ou acceptée.")
        return redirect("student_dashboard")

    if request.method == "POST":
        form = PFERequestForm(
            request.POST,
            request.FILES,
            instance=existing_request,
        )

        if form.is_valid():
            pfe_request = form.save(commit=False)
            pfe_request.student = student
            pfe_request.status = PFERequest.STATUS_PENDING_PROFESSOR

            pfe_request.professor_comment = None
            pfe_request.admin_comment = None
            pfe_request.professor_reviewed_at = None
            pfe_request.admin_reviewed_at = None
            pfe_request.reviewed_by_professor = None
            pfe_request.reviewed_by_admin = None
            pfe_request.reviewed_by = None
            pfe_request.reviewed_at = None

            pfe_request.save()

            messages.success(
                request,
                "Votre demande a été envoyée à votre encadrant."
            )
            return redirect("student_dashboard")
    else:
        form = PFERequestForm(instance=existing_request)

    return render(request, "soutenances/submit_pfe_request.html", {
        "form": form,
        "student": student,
        "deadline": deadline,
        "existing_request": existing_request,
    })


@login_required
@role_required(["admin"])
def admin_pfe_requests(request):
    requests = PFERequest.objects.select_related(
        "student",
        "student__user",
        "student__encadrant",
    ).order_by("-submitted_at")

    # Étudiants ayant soutenu = résultat publié par le chef de département.
    defended_student_ids = set(
        Result.objects.filter(is_published=True).values_list(
            "jury_student__student_id", flat=True
        )
    )

    for demande in requests:
        demande.has_defended = demande.student_id in defended_student_ids

    return render(request, "soutenances/admin_pfe_requests.html", {
        "requests": requests,
    })


@login_required
@role_required(["admin"])
def admin_pfe_request_detail(request, pk):
    pfe_request = get_object_or_404(
        PFERequest.objects.select_related(
            "student",
            "student__user",
            "student__encadrant",
            "reviewed_by",
            "reviewed_by_admin",
            "reviewed_by_professor",
        ),
        pk=pk,
    )

    decision_form = PFERequestDecisionForm()

    REUPLOAD_FIELDS = {
        "authorization": "authorization_document",
        "attestation": "attestation_stage",
        "rapport": "rapport_stage",
    }

    if request.method == "POST" and request.POST.get("action") == "request_reupload":
        doc = (request.POST.get("reupload_document") or "").strip()
        comment = (request.POST.get("reupload_comment") or "").strip()
        if doc not in REUPLOAD_FIELDS:
            messages.error(request, "Choisissez le document à faire redéposer.")
        else:
            pfe_request.reupload_document = doc
            pfe_request.reupload_comment = comment
            # On vide la pièce concernée pour obliger l'étudiant à la redéposer.
            setattr(pfe_request, REUPLOAD_FIELDS[doc], None)
            pfe_request.save(update_fields=[
                "reupload_document", "reupload_comment", REUPLOAD_FIELDS[doc],
            ])
            messages.success(
                request,
                "Demande de redépôt envoyée à l'étudiant (visible aussi par l'encadrant)."
            )
        return redirect("admin_pfe_request_detail", pk=pfe_request.pk)

    if request.method == "POST":
        decision_form = PFERequestDecisionForm(request.POST)

        if decision_form.is_valid():
            action = request.POST.get("action")
            comment = decision_form.cleaned_data.get("comment")

            if action == "accept":
                if pfe_request.status != PFERequest.STATUS_PENDING_ADMIN:
                    messages.error(
                        request,
                        "Cette demande doit d'abord être validée par l'encadrant."
                    )
                    return redirect("admin_pfe_request_detail", pk=pfe_request.pk)

                pfe_request.admin_accept(request.user)
                messages.success(request, "La demande a été acceptée avec succès.")
                return redirect("admin_pfe_requests")

            if action == "refuse":
                if pfe_request.status != PFERequest.STATUS_PENDING_ADMIN:
                    messages.error(
                        request,
                        "Cette demande doit d'abord être validée par l'encadrant."
                    )
                    return redirect("admin_pfe_request_detail", pk=pfe_request.pk)

                pfe_request.admin_refuse(request.user, comment)
                messages.success(request, "La demande a été refusée.")
                return redirect("admin_pfe_requests")

            messages.error(request, "Action invalide.")

    return render(request, "soutenances/admin_pfe_request_detail.html", {
        "pfe_request": pfe_request,
        "decision_form": decision_form,
    })


@login_required
@role_required(["admin"])
def admin_deadline(request):
    deadline = Deadline.objects.filter(
        is_active=True
    ).order_by("-deadline_date").first()

    if request.method == "POST":
        form = DeadlineForm(request.POST, instance=deadline)

        if form.is_valid():
            saved = form.save()

            if saved.is_active:
                Deadline.objects.exclude(pk=saved.pk).update(is_active=False)

            messages.success(request, "Date limite mise à jour.")
            return redirect("admin_deadline")
    else:
        form = DeadlineForm(instance=deadline)

    deadlines = Deadline.objects.order_by("-deadline_date")

    return render(request, "soutenances/admin_deadline.html", {
        "form": form,
        "deadlines": deadlines,
    })


@login_required
@role_required(["admin"])
def admin_expert_groups(request):
    """Gestion des groupes d'experts par filière (un expert = professeur de
    référence de la filière, distinct de l'encadrant lors des jurys)."""
    filieres = [c for c in StudentProfile.FILIERE_CHOICES if c[0]]
    professors = list(ProfessorProfile.objects.order_by("full_name"))

    if request.method == "POST":
        for filiere_value, _label in filieres:
            posted_ids = set(request.POST.getlist(f"expert_{filiere_value}"))
            posted_ids = {int(pid) for pid in posted_ids if pid.isdigit()}

            FiliereExpert.objects.filter(filiere=filiere_value).exclude(
                professor_id__in=posted_ids
            ).delete()

            existing = set(
                FiliereExpert.objects.filter(filiere=filiere_value).values_list(
                    "professor_id", flat=True
                )
            )
            for pid in posted_ids - existing:
                FiliereExpert.objects.create(filiere=filiere_value, professor_id=pid)

        messages.success(request, "Groupes d'experts mis à jour.")
        return redirect("admin_expert_groups")

    experts_by_filiere = {value: set() for value, _ in filieres}
    for entry in FiliereExpert.objects.all():
        if entry.filiere in experts_by_filiere:
            experts_by_filiere[entry.filiere].add(entry.professor_id)

    groups = []
    for value, label in filieres:
        selected_ids = experts_by_filiere.get(value, set())
        groups.append({
            "value": value,
            "label": label,
            "count": len(selected_ids),
            "professors": [
                {"id": p.id, "full_name": p.full_name, "checked": p.id in selected_ids}
                for p in professors
            ],
        })

    return render(request, "soutenances/admin_expert_groups.html", {
        "groups": groups,
    })


@login_required
@role_required(["admin"])
def admin_jury_list(request):
    juries = Jury.objects.prefetch_related(
        "members__professor",
        "students__student",
        "students__student__encadrant",
        "students__president",
        "students__schedule",
    ).order_by("-defense_date", "name")

    pending_students_count = StudentProfile.objects.filter(
        pfe_request__status=PFERequest.STATUS_ACCEPTED,
        jury_assignment__isnull=True,
    ).count()

    future_availabilities_count = ProfessorAvailability.objects.filter(
        date__gte=timezone.localdate()
    ).count()

    published_juries_count = juries.filter(is_validated=True).count()
    draft_juries_count = juries.filter(is_validated=False).count()
    assigned_students_count = JuryStudent.objects.count()

    return render(request, "soutenances/admin_jury_list.html", {
        "juries": juries,
        "generation_form": JuryGenerationForm(),
        "pending_students_count": pending_students_count,
        "future_availabilities_count": future_availabilities_count,
        "duration_minutes": DEFENSE_DURATION_MINUTES,
        "total_juries_count": juries.count(),
        "published_juries_count": published_juries_count,
        "draft_juries_count": draft_juries_count,
        "assigned_students_count": assigned_students_count,
    })


@login_required
@role_required(["admin"])
def admin_generate_juries(request):
    if request.method != "POST":
        return redirect("admin_jury_list")

    form = JuryGenerationForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Génération impossible. Veuillez réessayer.")
        return redirect("admin_jury_list")

    result = generate_smart_juries()

    # Render the detailed generation report directly
    return render(request, "soutenances/admin_generation_report.html", {
        "result": result,
    })


@login_required
@role_required(["admin"])
def admin_generate_juries_targeted(request):
    """Génération ciblée : date + nombre de jurys + étudiants + professeurs
    choisis par l'admin (override des disponibilités déclarées)."""
    if request.method == "POST":
        form = TargetedJuryGenerationForm(request.POST)
        if form.is_valid():
            result = generate_targeted_juries(
                form.cleaned_data["defense_date"],
                list(form.cleaned_data["students"]),
                list(form.cleaned_data["professors"]),
                form.cleaned_data["num_juries"],
            )
            if result.get("error"):
                messages.error(request, result["error"])
                return render(request, "soutenances/admin_generate_targeted.html", {"form": form})

            messages.success(
                request,
                f"{result['created']} jury(s) créé(s), "
                f"{result['assigned']} étudiant(s) programmé(s) le "
                f"{form.cleaned_data['defense_date'].strftime('%d/%m/%Y')}."
            )
            if result["skipped"]:
                detail = "; ".join(
                    f"{s.full_name} ({why})" for s, why in result["skipped"][:8]
                )
                messages.warning(
                    request,
                    f"{len(result['skipped'])} étudiant(s) non programmé(s) : {detail}"
                )
            return redirect("admin_jury_list")
    else:
        form = TargetedJuryGenerationForm()

    return render(request, "soutenances/admin_generate_targeted.html", {"form": form})


@transaction.atomic
def generate_targeted_juries(defense_date, students, professors, num_juries):
    """Génère les jurys ciblés en respectant :
    - la date limite des soutenances (DEFENSE_DEADLINE) ;
    - les disponibilités déclarées des membres (obligatoire) ;
    - la priorité aux jurys mono-filière avec un expert de la filière
      (différent de l'encadrant) ; à défaut, au moins un expert ≠ encadrant.
    Chaque jury : 3 professeurs distincts (encadrants inclus), créneaux de 20 min,
    président ≠ encadrant.
    """
    from collections import defaultdict

    result = {
        "created": 0, "assigned": 0, "scheduled": 0,
        "skipped": [], "juries": [], "error": None,
    }

    if defense_date > DEFENSE_DEADLINE:
        result["error"] = (
            f"Aucune soutenance n'est possible après le "
            f"{DEFENSE_DEADLINE.strftime('%d/%m/%Y')}."
        )
        return result

    prof_by_id = {p.id: p for p in professors}
    prof_ids = set(prof_by_id)

    # Experts par filière, restreints aux professeurs sélectionnés.
    experts_by_filiere = defaultdict(set)
    for entry in FiliereExpert.objects.filter(professor_id__in=prof_ids):
        experts_by_filiere[entry.filiere].add(entry.professor_id)
    all_expert_ids = set().union(*experts_by_filiere.values()) if experts_by_filiere else set()

    # 1. Étudiants exploitables (acceptés + encadrant sélectionné).
    ready = []
    for student in students:
        if student.encadrant_id not in prof_ids:
            result["skipped"].append((student, "encadrant non sélectionné"))
        else:
            ready.append(student)

    if not ready:
        return result

    # 2. Regroupement par encadrant (en conservant la filière).
    by_enc = defaultdict(list)
    for student in ready:
        by_enc[student.encadrant_id].append(student)

    enc_filiere = {}
    for eid, group in by_enc.items():
        enc_filiere[eid] = group[0].filiere or ""

    # 3. Répartition des encadrants dans num_juries bandes, priorité mono-filière
    #    et au plus 2 encadrants par jury (1 place réservée à l'expert).
    n = max(1, num_juries)
    buckets = [
        {"filiere": None, "enc_ids": [], "students": []} for _ in range(n)
    ]
    enc_sorted = sorted(by_enc.keys(), key=lambda e: (enc_filiere[e], -len(by_enc[e])))

    for eid in enc_sorted:
        fil = enc_filiere[eid]
        target = None
        # a) bande de même filière avec une place d'encadrant libre
        same = [b for b in buckets if b["filiere"] == fil and len(b["enc_ids"]) < 2]
        if same:
            target = min(same, key=lambda b: len(b["students"]))
        else:
            # b) bande vide
            empty = [b for b in buckets if not b["enc_ids"]]
            if empty:
                target = empty[0]
                target["filiere"] = fil
            else:
                # c) repli : bande avec place d'encadrant libre (filières mêlées)
                room = [b for b in buckets if len(b["enc_ids"]) < 2]
                if room:
                    target = min(room, key=lambda b: len(b["students"]))
        if target is None:
            for student in by_enc[eid]:
                result["skipped"].append((student, "pas assez de jurys disponibles"))
            continue
        target["enc_ids"].append(eid)
        target["students"].extend(by_enc[eid])

    # Les encadrants ne servent que dans leur propre jury : on les exclut des
    # pools d'experts / remplissage pour ne pas les rendre indisponibles ailleurs.
    all_enc_ids = set(by_enc.keys())
    used_prof_ids = set()  # professeurs déjà engagés (jurys parallèles disjoints)

    # Heures de début candidates : grille de 20 min couvrant les plages de
    # disponibilité déclarées ce jour-là (ex. 15:00–19:00). On ne suppose plus
    # un démarrage à 09:00.
    day_avails = list(
        ProfessorAvailability.objects.filter(
            professor_id__in=prof_ids, date=defense_date
        )
    )
    candidate_starts = []
    if day_avails:
        cursor_t = datetime.combine(defense_date, min(a.start_time for a in day_avails))
        end_t = datetime.combine(defense_date, max(a.end_time for a in day_avails))
        while cursor_t <= end_t:
            candidate_starts.append(cursor_t.time())
            cursor_t += timedelta(minutes=DEFENSE_DURATION_MINUTES)

    def earliest_start_for(encadrant_objs, n_students):
        """Renvoie (heure_début, encadrants_disponibles) : d'abord un créneau où
        TOUS les encadrants sont disponibles pour tout le bloc, sinon le créneau
        qui en rend le plus disponibles."""
        block = DEFENSE_DURATION_MINUTES * n_students
        for start in candidate_starts:
            if all(
                is_professor_available(p, defense_date, start, block)
                for p in encadrant_objs
            ):
                return start, list(encadrant_objs)
        best = None
        for start in candidate_starts:
            avail = [
                p for p in encadrant_objs
                if is_professor_available(p, defense_date, start, block)
            ]
            if avail and (best is None or len(avail) > len(best[1])):
                best = (start, avail)
        return best if best else (None, [])

    for bucket in buckets:
        if not bucket["students"]:
            continue

        enc_ids = list(dict.fromkeys(bucket["enc_ids"]))
        enc_objs = [prof_by_id[e] for e in enc_ids]

        # 3a. Choix du créneau de début selon la disponibilité des encadrants.
        start_time, avail_enc = earliest_start_for(enc_objs, len(bucket["students"]))
        if start_time is None:
            for student in bucket["students"]:
                result["skipped"].append(
                    (student, "aucune disponibilité commune des encadrants ce jour")
                )
            continue

        kept_enc = [p.id for p in avail_enc]
        for eid in enc_ids:
            if eid not in kept_enc:
                p = prof_by_id[eid]
                for student in [s for s in bucket["students"] if s.encadrant_id == eid]:
                    result["skipped"].append(
                        (student, f"encadrant indisponible ({p.full_name})")
                    )

        bucket_students = [s for s in bucket["students"] if s.encadrant_id in kept_enc]
        if not bucket_students:
            continue

        n_students = len(bucket_students)
        block_minutes = DEFENSE_DURATION_MINUTES * n_students
        bucket_filieres = {s.filiere or "" for s in bucket_students}

        members = [prof_by_id[e] for e in kept_enc]
        members_ids = {p.id for p in members}

        def can_use(pid):
            if pid in members_ids or pid in used_prof_ids or pid in all_enc_ids:
                return False
            return is_professor_available(
                prof_by_id[pid], defense_date, start_time, block_minutes
            )

        # 3b. Ajouter un expert de la filière (≠ encadrants), disponible.
        has_expert = False
        for fil in bucket_filieres:
            if len(members) >= 3:
                break
            candidates = [
                pid for pid in experts_by_filiere.get(fil, set())
                if pid not in kept_enc and can_use(pid)
            ]
            if candidates:
                pid = candidates[0]
                members.append(prof_by_id[pid])
                members_ids.add(pid)
                has_expert = True

        # 3c. Compléter à 3 avec des professeurs disponibles. On privilégie les
        #     non-experts pour réserver les experts à leur propre filière.
        non_experts = [pid for pid in prof_ids if pid not in all_expert_ids]
        expert_fillers = [pid for pid in prof_ids if pid in all_expert_ids]
        for pid in non_experts + expert_fillers:
            if len(members) >= 3:
                break
            if can_use(pid):
                members.append(prof_by_id[pid])
                members_ids.add(pid)

        if len(members) < 3:
            for student in bucket_students:
                result["skipped"].append(
                    (student, "pas assez de professeurs disponibles pour compléter le jury")
                )
            continue

        # 4. Création du jury et planification (save() vérifie dispo + conflits).
        idx = result["created"] + 1
        jury = Jury.objects.create(
            name=f"Jury {defense_date.strftime('%d/%m')} #{idx}",
            defense_date=defense_date,
            is_validated=False,
        )
        for professor in members:
            JuryMember.objects.create(jury=jury, professor=professor)
        used_prof_ids.update(members_ids)
        result["created"] += 1

        cursor = datetime.combine(defense_date, start_time)
        scheduled_here = 0
        for student in sorted(bucket_students, key=lambda s: s.full_name.lower()):
            # Président : un expert de la filière de préférence, sinon tout
            # membre ≠ encadrant de l'étudiant.
            student_experts = experts_by_filiere.get(student.filiere or "", set())
            president = next(
                (m for m in members
                 if m.id != student.encadrant_id and m.id in student_experts),
                None,
            ) or next(
                (m for m in members if m.id != student.encadrant_id), None
            )
            js = JuryStudent.objects.create(
                student=student, jury=jury, president=president
            )
            try:
                DefenseSchedule.objects.create(
                    jury_student=js,
                    start_time=cursor.time(),
                    end_time=(cursor + timedelta(minutes=DEFENSE_DURATION_MINUTES)).time(),
                    duration_minutes=DEFENSE_DURATION_MINUTES,
                )
            except ValidationError as exc:
                js.delete()
                result["skipped"].append((student, "; ".join(exc.messages)))
                continue
            result["assigned"] += 1
            scheduled_here += 1
            cursor += timedelta(minutes=DEFENSE_DURATION_MINUTES)

        result["scheduled"] += scheduled_here
        result["juries"].append({
            "name": jury.name,
            "members": [p.full_name for p in members],
            "count": scheduled_here,
            "has_expert": has_expert,
            "mono_filiere": len(bucket_filieres) == 1,
        })

    return result


@transaction.atomic
def generate_smart_juries():
    """
    Génère les jurys en parcourant les créneaux chronologiquement.
    À chaque créneau, sélectionne les encadrants disponibles avec le plus d'étudiants prêts.
    La capacité du créneau (20 min/étudiant) détermine combien d'étudiants on peut affecter.
    """
    from collections import defaultdict

    # 1. Collect all ready students (accepted PFE, no jury, advisor known)
    all_ready = list(
        StudentProfile.objects.filter(
            pfe_request__status=PFERequest.STATUS_ACCEPTED,
            jury_assignment__isnull=True,
            encadrant__isnull=False,
        ).select_related("encadrant", "user")
    )

    professors = list(ProfessorProfile.objects.order_by("full_name"))

    result = {
        "created": 0,
        "assigned": 0,
        "scheduled": 0,
        "errors": [],
        "report": {
            "total_ready": len(all_ready),
            "by_encadrant_before": {},
            "juries": [],
        },
    }

    if not all_ready:
        return result

    if len(professors) < 3:
        for student in all_ready:
            result["errors"].append({
                "student": student,
                "reason": "not_enough_professors",
                "message": "Nombre insuffisant de professeurs pour former un jury.",
            })
        return result

    # 2. Group students by encadrant (mutable for tracking remaining students)
    students_by_encadrant = defaultdict(list)
    for student in all_ready:
        students_by_encadrant[student.encadrant_id].append(student)
    for key in students_by_encadrant:
        students_by_encadrant[key].sort(key=lambda s: s.full_name.lower())

    # Fill report: student counts per advisor before generation
    for enc_id, students in students_by_encadrant.items():
        if students:
            enc_name = students[0].encadrant.full_name
            result["report"]["by_encadrant_before"][enc_name] = len(students)

    # 3. Get all future slot starts in chronological order
    candidate_slots = build_all_future_slot_starts()

    if not candidate_slots:
        for enc_id, students in students_by_encadrant.items():
            for student in students:
                result["errors"].append({
                    "student": student,
                    "reason": "no_slots",
                    "message": "Aucune disponibilité future déclarée par les professeurs.",
                })
        return result

    jury_index = 1

    # 4. Walk through slots chronologically
    for defense_date, block_start in candidate_slots:
        # Stop early if no students remain
        if not any(students_by_encadrant.values()):
            break

        # Skip if global simultaneous-jury capacity is reached at this slot
        if jury_slot_capacity_reached(defense_date, block_start):
            continue

        # Find professors free at this slot (available + no conflict)
        available_profs = [
            p for p in professors
            if is_professor_available(p, defense_date, block_start, DEFENSE_DURATION_MINUTES)
            and not professor_has_conflict(p, defense_date, block_start, DEFENSE_DURATION_MINUTES)
        ]

        if len(available_profs) < 3:
            continue

        # 5. Split: advisors with remaining students vs others
        remaining_enc_ids = {
            enc_id for enc_id, stds in students_by_encadrant.items() if stds
        }
        profs_with_students = [p for p in available_profs if p.id in remaining_enc_ids]
        profs_without_students = [p for p in available_profs if p.id not in remaining_enc_ids]

        # At least one advisor with students must be available
        if not profs_with_students:
            continue

        # Prioritize advisors with the most remaining students
        profs_with_students.sort(
            key=lambda p: (-len(students_by_encadrant.get(p.id, [])), p.full_name.lower())
        )

        # Form jury of 3: fill first with advisors-with-students, then with others
        if len(profs_with_students) >= 3:
            jury_members = profs_with_students[:3]
        else:
            jury_members = list(profs_with_students)
            jury_members.extend(profs_without_students[:3 - len(jury_members)])

        if len(jury_members) < 3:
            continue

        # 6. Build consecutive 30-min slots to determine real capacity
        available_slots = build_consecutive_available_slots(
            members=jury_members,
            defense_date=defense_date,
            block_start=block_start,
            max_slots=20,
        )

        if not available_slots:
            continue

        capacity = len(available_slots)

        # 7. Collect and rank students from jury-member advisors
        students_pool = []
        for prof in jury_members:
            students_pool.extend(students_by_encadrant.get(prof.id, []))

        # Advisor with most remaining students first, then student name
        students_pool.sort(
            key=lambda s: (
                -len(students_by_encadrant.get(s.encadrant_id, [])),
                s.full_name.lower(),
            )
        )

        selected_students = students_pool[:capacity]
        selected_slots = available_slots[:len(selected_students)]

        if not selected_students:
            continue

        plan = {
            "members": jury_members,
            "students": selected_students,
            "defense_date": defense_date,
            "start_times": selected_slots,
        }

        try:
            jury = create_grouped_jury_from_plan(plan, jury_index)
        except ValidationError as exc:
            for student in selected_students:
                result["errors"].append({
                    "student": student,
                    "reason": "validation_error",
                    "message": "; ".join(exc.messages),
                })
            continue

        result["created"] += 1
        result["assigned"] += len(selected_students)
        result["scheduled"] += len(selected_students)
        jury_index += 1

        # Build report entry for this jury
        report_entry = {
            "jury_name": jury.name,
            "members": [p.full_name for p in jury_members],
            "defense_date": defense_date,
            "slot_start": block_start,
            "capacity": capacity,
            "students_scheduled": [],
        }
        for student, slot_start in zip(selected_students, selected_slots):
            slot_end = (
                datetime.combine(defense_date, slot_start)
                + timedelta(minutes=DEFENSE_DURATION_MINUTES)
            ).time()
            report_entry["students_scheduled"].append({
                "name": student.full_name,
                "encadrant": student.encadrant.full_name if student.encadrant else "—",
                "start_time": slot_start,
                "end_time": slot_end,
            })
        result["report"]["juries"].append(report_entry)

        # 8. Remove assigned students from the pool
        for student in selected_students:
            pool = students_by_encadrant.get(student.encadrant_id, [])
            if student in pool:
                pool.remove(student)

    # 9. Report remaining unassigned students with reason
    for enc_id, students in students_by_encadrant.items():
        for student in students:
            result["errors"].append({
                "student": student,
                "reason": "no_slot_found",
                "message": "Aucun créneau commun trouvé pour l'encadrant de cet étudiant.",
            })

    return result


@transaction.atomic
def generate_juries_for_date(defense_date=None):
    return generate_smart_juries()


def build_all_future_slot_starts():
    today = timezone.localdate()
    now_time = timezone.localtime().time()

    starts = set()

    availabilities = ProfessorAvailability.objects.filter(
        date__gte=today,
    ).order_by(
        "date",
        "start_time",
        "end_time",
    )

    for availability in availabilities:
        for defense_date, start_time in build_slots_from_availability(availability):
            if defense_date > today or start_time > now_time:
                starts.add((defense_date, start_time))

    return sorted(
        starts,
        key=lambda item: (item[0], item[1])
    )


def build_consecutive_available_slots(members, defense_date, block_start, max_slots):
    if jury_slot_capacity_reached(defense_date, block_start):
        return []

    slots = []
    cursor = datetime.combine(defense_date, block_start)

    for index in range(max_slots):
        current_time = (
            cursor + timedelta(minutes=index * DEFENSE_DURATION_MINUTES)
        ).time()

        all_members_available = True

        for professor in members:
            if not is_professor_available(
                professor,
                defense_date,
                current_time,
                DEFENSE_DURATION_MINUTES,
            ):
                all_members_available = False
                break

            if professor_has_conflict(
                professor,
                defense_date,
                current_time,
                DEFENSE_DURATION_MINUTES,
            ):
                all_members_available = False
                break

        if not all_members_available:
            break

        slots.append(current_time)

    return slots


def create_grouped_jury_from_plan(plan, jury_index):
    jury = Jury.objects.create(
        name=build_grouped_jury_name(
            students=plan["students"],
            jury_index=jury_index,
        ),
        defense_date=plan["defense_date"],
        is_validated=False,
    )

    try:
        for professor in plan["members"]:
            JuryMember.objects.create(
                jury=jury,
                professor=professor,
            )

        for student, start_time in zip(plan["students"], plan["start_times"]):
            president = choose_president_for_student(
                student=student,
                members=plan["members"],
                defense_date=plan["defense_date"],
            )

            assignment = JuryStudent.objects.create(
                jury=jury,
                student=student,
                president=president,
            )

            DefenseSchedule.objects.create(
                jury_student=assignment,
                start_time=start_time,
                duration_minutes=DEFENSE_DURATION_MINUTES,
            )

    except ValidationError:
        jury.delete()
        raise

    return jury


def build_grouped_jury_name(students, jury_index):
    first_student = students[0]

    if len(students) == 1:
        return f"Jury intelligent {jury_index} - {first_student.matricule}"

    return (
        f"Jury intelligent {jury_index} - "
        f"{len(students)} étudiants - "
        f"{first_student.matricule}"
    )


def choose_president_for_student(student, members, defense_date):
    candidates = [
        professor for professor in members
        if professor.id != student.encadrant_id
    ]

    candidates.sort(
        key=lambda professor: (
            professor_load_on_date(professor, defense_date),
            professor_total_scheduled_load(professor),
            supervised_students_count(professor),
            professor.full_name.lower(),
        )
    )

    return candidates[0] if candidates else None


def calculate_next_defense_slot_for_jury(jury, members):
    """
    Retourne le prochain start_time disponible de 20 min pour ce jury.
    Utilise end_time du dernier créneau existant, ou cherche le premier créneau libre.
    Retourne None si aucun créneau valide n'est trouvé.
    """
    last_schedule = DefenseSchedule.objects.filter(
        jury_student__jury=jury,
    ).order_by("-start_time").first()

    if last_schedule:
        next_start = last_schedule.end_time
    else:
        # No students yet: find earliest slot where all members are available
        avails = ProfessorAvailability.objects.filter(
            professor__in=members,
            date=jury.defense_date,
        ).order_by("start_time")

        next_start = None
        for avail in avails:
            candidate = avail.start_time
            if all(
                is_professor_available(m, jury.defense_date, candidate, DEFENSE_DURATION_MINUTES)
                for m in members
            ):
                next_start = candidate
                break

        if next_start is None:
            return None

    # Verify availability and no conflict for all members at next_start
    for member in members:
        if not is_professor_available(member, jury.defense_date, next_start, DEFENSE_DURATION_MINUTES):
            return None
        if professor_has_conflict(member, jury.defense_date, next_start, DEFENSE_DURATION_MINUTES):
            return None

    return next_start


@login_required
@role_required(["admin"])
def admin_jury_create(request):
    if request.method == "POST":
        form = JuryForm(request.POST)

        if form.is_valid():
            jury = save_jury_with_members(form)
            messages.success(request, "Le jury a été créé avec succès.")
            return redirect("admin_jury_detail", pk=jury.pk)
    else:
        form = JuryForm()

    eligible_students = StudentProfile.objects.filter(
        pfe_request__status=PFERequest.STATUS_ACCEPTED,
        jury_assignment__isnull=True,
    ).select_related("encadrant").order_by("encadrant__full_name", "full_name")

    return render(request, "soutenances/admin_jury_form.html", {
        "form": form,
        "title": "Créer un jury",
        "eligible_students": eligible_students,
    })


@login_required
@role_required(["admin"])
def admin_jury_quick_create(request):
    """Flux guidé et réellement contraint par les disponibilités :
    étudiant -> encadrant -> créneau réel -> membres réellement disponibles
    à ce créneau -> création atomique de Jury + JuryMember + JuryStudent +
    DefenseSchedule. Le filtrage n'est pas qu'une suggestion JS : le
    queryset du formulaire de membres est restreint côté serveur, et tout
    est revérifié juste avant la création."""

    eligible_students = StudentProfile.objects.filter(
        pfe_request__status=PFERequest.STATUS_ACCEPTED,
        jury_assignment__isnull=True,
    ).select_related("encadrant").order_by("encadrant__full_name", "full_name")

    context = {"eligible_students": eligible_students}

    student_id = request.POST.get("student_id") or request.GET.get("student_id")
    student = None

    if student_id:
        student = get_object_or_404(
            StudentProfile.objects.select_related("encadrant"),
            pk=student_id,
        )
        context["student"] = student

        if not student.encadrant_id:
            messages.error(request, "Cet étudiant n'a pas d'encadrant défini.")
            return render(request, "soutenances/admin_jury_quick_create.html", context)

    slot_key = request.POST.get("slot") or request.GET.get("slot")
    selected_date = None
    selected_time = None

    if student:
        slots = get_common_available_slots([student.encadrant])

        context["slots"] = [
            {
                "key": f"{defense_date.isoformat()}|{start_time.strftime('%H:%M')}",
                "date": defense_date,
                "start_time": start_time,
            }
            for defense_date, start_time in slots
        ]

        if not slots:
            context["no_slots"] = True

    if slot_key and student:
        try:
            date_raw, time_raw = slot_key.split("|")
            selected_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
            selected_time = datetime.strptime(time_raw, "%H:%M").time()
        except ValueError:
            selected_date = None
            selected_time = None

    members_form = None
    other_available = None

    if student and selected_date and selected_time:
        # Revérification serveur : le créneau doit toujours être valide pour
        # l'encadrant au moment où on l'utilise, pas seulement quand la liste
        # a été affichée.
        encadrant_still_ok = (
            is_professor_available(student.encadrant, selected_date, selected_time)
            and not professor_has_conflict(student.encadrant, selected_date, selected_time)
        )

        if not encadrant_still_ok:
            messages.error(
                request,
                "Ce créneau n'est plus disponible pour l'encadrant. Choisissez-en un autre."
            )
            selected_date = None
            selected_time = None
        else:
            available_professors = get_available_professors_at_slot(selected_date, selected_time)
            other_available = ProfessorProfile.objects.filter(
                id__in=[p.id for p in available_professors]
            ).exclude(id=student.encadrant_id).order_by("full_name")

            context["selected_date"] = selected_date
            context["selected_time"] = selected_time
            context["slot_key"] = slot_key
            context["available_count"] = other_available.count()

            if other_available.count() < 2:
                context["not_enough_members"] = True
            else:
                if request.method == "POST" and request.POST.get("step") == "3":
                    members_form = JuryMembersForSlotForm(
                        request.POST, available_queryset=other_available
                    )
                else:
                    members_form = JuryMembersForSlotForm(available_queryset=other_available)

            context["members_form"] = members_form

    if (
        request.method == "POST"
        and request.POST.get("step") == "3"
        and members_form is not None
        and student
        and selected_date
        and selected_time
    ):
        if members_form.is_valid():
            try:
                with transaction.atomic():
                    if not (
                        is_professor_available(student.encadrant, selected_date, selected_time)
                        and not professor_has_conflict(student.encadrant, selected_date, selected_time)
                    ):
                        raise ValidationError(
                            "Le créneau n'est plus disponible pour l'encadrant."
                        )

                    chosen_others = list(members_form.cleaned_data["members"])

                    for professor in chosen_others:
                        if not (
                            is_professor_available(professor, selected_date, selected_time)
                            and not professor_has_conflict(professor, selected_date, selected_time)
                        ):
                            raise ValidationError(
                                f"{professor.full_name} n'est plus disponible à ce créneau."
                            )

                    jury = Jury.objects.create(
                        name=f"Jury {student.full_name} - {selected_date.strftime('%d/%m/%Y')}",
                        defense_date=selected_date,
                        is_validated=False,
                    )

                    members = [student.encadrant] + chosen_others

                    for professor in members:
                        JuryMember.objects.create(jury=jury, professor=professor)

                    president = choose_president_for_student(
                        student=student,
                        members=members,
                        defense_date=selected_date,
                    )

                    jury_student = JuryStudent.objects.create(
                        jury=jury,
                        student=student,
                        president=president,
                    )

                    DefenseSchedule.objects.create(
                        jury_student=jury_student,
                        start_time=selected_time,
                        duration_minutes=DEFENSE_DURATION_MINUTES,
                    )
            except ValidationError as exc:
                messages.error(
                    request,
                    "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
                )
            else:
                messages.success(
                    request,
                    f"Jury créé pour {student.full_name}, le "
                    f"{selected_date.strftime('%d/%m/%Y')} à {selected_time.strftime('%H:%M')}."
                )
                return redirect("admin_jury_detail", pk=jury.pk)

    return render(request, "soutenances/admin_jury_quick_create.html", context)


@login_required
@role_required(["admin"])
def admin_jury_update(request, pk):
    """
    Page Modifier jury — simplifiée.
    Le créneau réel est auto-détecté depuis les DefenseSchedule existants.
    Plus de sélection manuelle de créneau.
    """
    jury = get_object_or_404(
        Jury.objects.prefetch_related("members__professor"),
        pk=pk,
    )

    jury_students = list(
        jury.students.select_related("student__encadrant", "schedule")
    )

    # ── 1. Détection automatique du créneau réel (premier slot planifié) ──
    # On prend le DefenseSchedule avec le plus petit start_time du jury.
    first_schedule = (
        DefenseSchedule.objects.filter(jury_student__jury=jury)
        .order_by("start_time")
        .first()
    )
    real_slot_date  = jury.defense_date if first_schedule else None
    real_slot_start = first_schedule.start_time if first_schedule else None
    real_slot_end   = first_schedule.end_time   if first_schedule else None
    has_real_slot   = real_slot_date is not None and real_slot_start is not None

    # ── 2. Membres actuels avec logique can_remove ─────────────────────────
    current_members = list(
        jury.members.select_related("professor").order_by("professor__full_name")
    )
    member_rows = []

    for member in current_members:
        professor = member.professor
        supervised_here = [
            js.student for js in jury_students
            if js.student.encadrant_id == professor.id
        ]

        is_available = None
        if has_real_slot:
            is_available = (
                is_professor_available(professor, real_slot_date, real_slot_start)
                and not professor_has_conflict(professor, real_slot_date, real_slot_start)
            )

        # Bloquer le retrait si ce professeur est l'encadrant d'étudiants dans ce jury
        # (chaque étudiant n'a qu'un seul encadrant → retrait toujours bloqué si encadrant actif)
        can_remove = len(supervised_here) == 0
        cannot_remove_reason = (
            "Impossible de retirer ce professeur : il est le seul encadrant "
            f"des étudiants affectés ({', '.join(s.full_name for s in supervised_here)}). "
            "Utilisez « Supprimer le jury » si nécessaire."
            if not can_remove else None
        )

        member_rows.append({
            "member": member,
            "professor": professor,
            "supervised_here": supervised_here,
            "is_available": is_available,
            "can_remove": can_remove,
            "cannot_remove_reason": cannot_remove_reason,
        })

    # ── 3. Formulaire d'ajout filtré sur le créneau réel ──────────────────
    add_member_form = None
    addable_count = 0

    if has_real_slot and len(current_members) < 3:
        available_at_slot = get_available_professors_at_slot(real_slot_date, real_slot_start)
        current_member_ids = {m.professor_id for m in current_members}
        addable_qs = ProfessorProfile.objects.filter(
            id__in=[p.id for p in available_at_slot if p.id not in current_member_ids]
        ).order_by("full_name")
        addable_count = addable_qs.count()

        if request.method == "POST" and request.POST.get("action") == "add_member":
            add_member_form = JuryAddMemberForm(request.POST, selectable_queryset=addable_qs)
        else:
            add_member_form = JuryAddMemberForm(selectable_queryset=addable_qs)

    # ── 3bis. Candidats au remplacement d'un membre (ex. encadrant indisponible) ──
    # Professeurs disponibles au créneau réel et pas déjà membres du jury.
    replacement_candidates = []
    if has_real_slot:
        available_at_slot = get_available_professors_at_slot(real_slot_date, real_slot_start)
        current_member_ids = {m.professor_id for m in current_members}
        replacement_candidates = [
            p for p in available_at_slot if p.id not in current_member_ids
        ]

    context = {
        "jury": jury,
        "jury_students": jury_students,
        "member_rows": member_rows,
        "current_members_count": len(current_members),
        "real_slot_date": real_slot_date,
        "real_slot_start": real_slot_start,
        "real_slot_end": real_slot_end,
        "has_real_slot": has_real_slot,
        "add_member_form": add_member_form,
        "addable_count": addable_count,
        "replacement_candidates": replacement_candidates,
    }

    # ── 4. POST : retirer un membre ────────────────────────────────────────
    if request.method == "POST" and request.POST.get("action") == "remove_member":
        try:
            professor_id = int(request.POST.get("professor_id", ""))
        except ValueError:
            professor_id = None

        member_to_remove = (
            jury.members.filter(professor_id=professor_id).first()
            if professor_id is not None else None
        )

        if not member_to_remove:
            messages.error(request, "Ce professeur n'est pas membre de ce jury.")
        else:
            supervised = [
                js for js in jury_students
                if js.student.encadrant_id == professor_id
            ]
            if supervised:
                names = ", ".join(js.student.full_name for js in supervised)
                messages.error(
                    request,
                    f"Impossible de retirer ce professeur : il est le seul encadrant "
                    f"des étudiants affectés à ce jury ({names}). "
                    "Utilisez « Supprimer le jury » si le jury entier doit être dissous."
                )
            else:
                prof_name = member_to_remove.professor.full_name

                # Vérifier si ce professeur est président d'une soutenance dans ce jury
                presided = [js for js in jury_students if js.president_id == professor_id]
                if presided:
                    # Chercher un remplaçant parmi les membres restants
                    # (doit être membre du jury et différent de l'encadrant de chaque étudiant)
                    remaining = [
                        m.professor for m in current_members
                        if m.professor_id != professor_id
                    ]
                    replacements = {}  # jury_student.pk -> nouveau président
                    blocked = False

                    for js in presided:
                        new_pres = next(
                            (p for p in remaining if p.id != js.student.encadrant_id),
                            None,
                        )
                        if new_pres is None:
                            blocked = True
                            messages.error(
                                request,
                                f"Impossible de retirer {prof_name} : il est président de la "
                                f"soutenance de {js.student.full_name} et aucun autre membre "
                                "valide ne peut le remplacer comme président."
                            )
                            break
                        replacements[js.pk] = new_pres

                    if not blocked:
                        # Appliquer les remplacements via update() pour éviter full_clean
                        # (le membre n'est pas encore retiré, la cohérence est préservée)
                        for js in presided:
                            JuryStudent.objects.filter(pk=js.pk).update(
                                president=replacements[js.pk]
                            )
                        member_to_remove.delete()
                        new_pres_name = next(iter(replacements.values())).full_name
                        presided_names = ", ".join(js.student.full_name for js in presided)
                        messages.success(
                            request,
                            f"{prof_name} retiré. Président remplacé par {new_pres_name} "
                            f"pour : {presided_names}."
                        )
                else:
                    member_to_remove.delete()
                    messages.success(request, f"{prof_name} retiré du jury.")

        return redirect("admin_jury_update", pk=jury.pk)

    # ── 5. POST : ajouter un membre (avec vérification backend) ───────────
    if (
        request.method == "POST"
        and request.POST.get("action") == "add_member"
        and add_member_form is not None
    ):
        if add_member_form.is_valid():
            professor = add_member_form.cleaned_data["professor"]

            # Vérification backend : disponible ET sans conflit au créneau réel
            still_ok = has_real_slot and (
                is_professor_available(professor, real_slot_date, real_slot_start)
                and not professor_has_conflict(professor, real_slot_date, real_slot_start)
            )

            if not still_ok:
                messages.error(
                    request,
                    f"{professor.full_name} n'est pas disponible au créneau réel de ce jury "
                    f"({real_slot_date} à {real_slot_start})."
                )
            elif jury.members.count() >= 3:
                messages.error(request, "Ce jury contient déjà 3 professeurs.")
            else:
                try:
                    JuryMember.objects.create(jury=jury, professor=professor)
                    messages.success(request, f"{professor.full_name} ajouté au jury.")
                except ValidationError as exc:
                    messages.error(request, "; ".join(exc.messages))
        else:
            messages.error(request, "Sélection de professeur invalide ou indisponible.")

        return redirect("admin_jury_update", pk=jury.pk)

    # ── 6. POST : remplacer un membre (ex. encadrant devenu indisponible) ─────
    if request.method == "POST" and request.POST.get("action") == "replace_member":
        try:
            old_id = int(request.POST.get("old_professor_id", ""))
            new_id = int(request.POST.get("new_professor_id", ""))
        except (ValueError, TypeError):
            messages.error(request, "Sélection invalide.")
            return redirect("admin_jury_update", pk=jury.pk)

        old_member = jury.members.filter(professor_id=old_id).first()
        new_prof = ProfessorProfile.objects.filter(id=new_id).first()

        if not old_member:
            messages.error(request, "Le membre à remplacer n'appartient pas à ce jury.")
        elif not new_prof:
            messages.error(request, "Choisissez un professeur remplaçant.")
        elif jury.members.filter(professor_id=new_id).exists():
            messages.error(request, f"{new_prof.full_name} est déjà membre de ce jury.")
        elif has_real_slot and not (
            is_professor_available(new_prof, real_slot_date, real_slot_start)
            and not professor_has_conflict(new_prof, real_slot_date, real_slot_start)
        ):
            messages.error(
                request,
                f"{new_prof.full_name} n'est pas disponible au créneau de ce jury "
                f"({real_slot_date} à {real_slot_start})."
            )
        else:
            old_name = old_member.professor.full_name
            with transaction.atomic():
                # Reprendre la présidence des soutenances présidées par l'ancien membre
                JuryStudent.objects.filter(
                    jury=jury, president_id=old_id
                ).update(president=new_prof)
                # Retirer l'ancien AVANT d'ajouter le nouveau (max 3 membres)
                old_member.delete()
                JuryMember.objects.create(jury=jury, professor=new_prof)
            messages.success(
                request,
                f"{old_name} a été remplacé par {new_prof.full_name} dans ce jury."
            )
        return redirect("admin_jury_update", pk=jury.pk)

    # ── 7. POST : désigner le président d'une soutenance (≠ encadrant) ────────
    if request.method == "POST" and request.POST.get("action") == "set_president":
        try:
            js_id = int(request.POST.get("jury_student_id", ""))
            pres_id = int(request.POST.get("president_id", ""))
        except (ValueError, TypeError):
            messages.error(request, "Sélection invalide.")
            return redirect("admin_jury_update", pk=jury.pk)

        js = JuryStudent.objects.select_related("student").filter(
            pk=js_id, jury=jury
        ).first()

        if not js:
            messages.error(request, "Étudiant introuvable dans ce jury.")
        elif not jury.members.filter(professor_id=pres_id).exists():
            messages.error(request, "Le président doit être membre du jury.")
        elif js.student.encadrant_id == pres_id:
            messages.error(
                request,
                "L'encadrant de l'étudiant ne peut pas être président de sa soutenance."
            )
        else:
            JuryStudent.objects.filter(pk=js.pk).update(president_id=pres_id)
            messages.success(
                request, f"Président défini pour {js.student.full_name}."
            )
        return redirect("admin_jury_update", pk=jury.pk)

    return render(request, "soutenances/admin_jury_update.html", context)


@login_required
@role_required(["admin"])
def admin_jury_delete(request, pk):
    """Suppression complète d'un jury — bloquée si évaluations ou résultats existent."""
    jury = get_object_or_404(Jury, pk=pk)

    if request.method != "POST":
        return redirect("admin_jury_update", pk=pk)

    # Protection : ne pas supprimer si des évaluations ou résultats existent
    has_evaluations = Evaluation.objects.filter(jury_student__jury=jury).exists()
    has_results     = Result.objects.filter(jury_student__jury=jury).exists()

    if has_evaluations or has_results:
        messages.error(
            request,
            "Impossible de supprimer ce jury : des évaluations ou résultats existent déjà. "
            "Supprimez-les manuellement si nécessaire."
        )
        return redirect("admin_jury_update", pk=pk)

    jury_name = jury.name
    # CASCADE Django supprime automatiquement : JuryMember, JuryStudent, DefenseSchedule
    jury.delete()
    messages.success(request, f"Le jury « {jury_name} » a été supprimé.")
    return redirect("admin_jury_list")


@transaction.atomic
def save_jury_with_members(form):
    jury = form.save()

    JuryMember.objects.filter(jury=jury).delete()

    for professor in form.cleaned_data["members"]:
        JuryMember.objects.create(
            jury=jury,
            professor=professor,
        )

    return jury


@login_required
@role_required(["admin"])
def admin_jury_detail(request, pk):
    jury = get_object_or_404(
        Jury.objects.prefetch_related(
            "members__professor",
            "students__student",
            "students__student__encadrant",
            "students__president",
            "students__schedule",
        ),
        pk=pk,
    )

    form = JuryStudentAssignForm(jury=jury)

    return render(request, "soutenances/admin_jury_detail.html", {
        "jury": jury,
        "form": form,
    })


@login_required
@role_required(["admin"])
def admin_jury_add_student(request, pk):
    jury = get_object_or_404(
        Jury.objects.prefetch_related("members__professor"),
        pk=pk,
    )

    if request.method == "POST":
        form = JuryStudentAssignForm(request.POST, jury=jury)

        if form.is_valid():
            try:
                student = form.cleaned_data["student"]

                members = [
                    member.professor
                    for member in jury.members.select_related("professor")
                ]

                president = choose_president_for_student(
                    student=student,
                    members=members,
                    defense_date=jury.defense_date,
                )

                # Calculate the next available 30-min slot for this student
                next_start = calculate_next_defense_slot_for_jury(jury, members)

                if next_start is None:
                    messages.error(
                        request,
                        "Impossible d'ajouter cet étudiant : aucun horaire de passage disponible pour ce jury."
                    )
                    return redirect("admin_jury_detail", pk=jury.pk)

                with transaction.atomic():
                    assignment = JuryStudent.objects.create(
                        jury=jury,
                        student=student,
                        president=president,
                    )
                    DefenseSchedule.objects.create(
                        jury_student=assignment,
                        start_time=next_start,
                        duration_minutes=DEFENSE_DURATION_MINUTES,
                    )

            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                messages.success(request, "L'étudiant a été ajouté au jury avec son horaire de passage.")

            return redirect("admin_jury_detail", pk=jury.pk)

        messages.error(request, "Impossible d'ajouter cet étudiant au jury.")

        return render(request, "soutenances/admin_jury_detail.html", {
            "jury": jury,
            "form": form,
        })

    return redirect("admin_jury_detail", pk=jury.pk)


@login_required
@role_required(["admin"])
def admin_jury_remove_student(request, pk, assignment_pk):
    jury = get_object_or_404(Jury, pk=pk)

    assignment = get_object_or_404(
        JuryStudent,
        pk=assignment_pk,
        jury=jury,
    )

    if request.method == "POST":
        assignment.delete()
        messages.success(request, "L'affectation a été supprimée.")

    return redirect("admin_jury_detail", pk=jury.pk)


@login_required
@role_required(["admin"])
def admin_jury_publish(request, pk):
    jury = get_object_or_404(Jury, pk=pk)

    if request.method == "POST":
        jury.is_validated = True
        jury.save(update_fields=["is_validated"])
        messages.success(request, "Le jury a été publié. Étudiants et professeurs peuvent le voir.")
        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
        if next_url:
            return redirect(next_url)
        return redirect("admin_jury_list")

    return redirect("admin_jury_list")


@login_required
@role_required(["admin"])
def admin_planning(request):
    schedules = DefenseSchedule.objects.select_related(
        "jury_student__student",
        "jury_student__student__encadrant",
        "jury_student__president",
        "jury_student__jury",
    ).order_by(
        "jury_student__jury__defense_date",
        "start_time",
        "jury_student__jury__name",
    )

    return render(request, "soutenances/admin_planning.html", {
        "schedules": schedules,
        "generation_form": PlanningGenerationForm(),
        "duration_minutes": DEFENSE_DURATION_MINUTES,
    })


@login_required
@role_required(["admin"])
def admin_generate_planning(request):
    if request.method == "POST":
        form = PlanningGenerationForm(request.POST)

        if form.is_valid():
            result = generate_planning_for_date(
                form.cleaned_data["defense_date"],
                form.cleaned_data["overwrite_existing"],
            )

            if result["created"]:
                messages.success(
                    request,
                    f"{result['created']} horaire(s) généré(s) en créneaux de 20 minutes."
                )

            if result["errors"]:
                messages.warning(
                    request,
                    f"{len(result['errors'])} affectation(s) sans horaire disponible."
                )

            return render(request, "soutenances/admin_planning_generate.html", {
                "form": PlanningGenerationForm(initial={
                    "defense_date": form.cleaned_data["defense_date"],
                }),
                "result": result,
                "duration_minutes": DEFENSE_DURATION_MINUTES,
            })

    else:
        first_jury = Jury.objects.order_by("-defense_date").first()

        initial = {
            "defense_date": first_jury.defense_date
        } if first_jury else {}

        form = PlanningGenerationForm(initial=initial)

    return render(request, "soutenances/admin_planning_generate.html", {
        "form": form,
        "duration_minutes": DEFENSE_DURATION_MINUTES,
    })


@transaction.atomic
def generate_planning_for_date(defense_date, overwrite_existing=False):
    if overwrite_existing:
        DefenseSchedule.objects.filter(
            jury_student__jury__defense_date=defense_date
        ).delete()

    assignments = JuryStudent.objects.filter(
        jury__defense_date=defense_date,
        schedule__isnull=True,
    ).select_related(
        "student",
        "student__encadrant",
        "president",
        "jury",
    ).order_by(
        "student__encadrant__full_name",
        "jury__name",
        "student__full_name",
    )

    slots = build_slots(defense_date)

    result = {
        "created": 0,
        "errors": [],
    }

    for assignment in assignments:
        created = False
        last_error = None

        for slot in slots:
            if jury_slot_capacity_reached(defense_date, slot):
                continue

            schedule = DefenseSchedule(
                jury_student=assignment,
                start_time=slot,
                duration_minutes=DEFENSE_DURATION_MINUTES,
            )

            try:
                schedule.save()
            except ValidationError as exc:
                last_error = exc
                continue
            else:
                result["created"] += 1
                created = True
                break

        if not created:
            result["errors"].append({
                "assignment": assignment,
                "message": (
                    last_error.messages[0]
                    if last_error and hasattr(last_error, "messages")
                    else "Aucun créneau compatible."
                ),
            })

    return result


def build_smart_jury_name(student, index):
    return f"Jury intelligent {index} - {student.matricule}"


def build_future_slots_for_professor(professor):
    availabilities = ProfessorAvailability.objects.filter(
        professor=professor,
        date__gte=timezone.localdate(),
    ).order_by(
        "date",
        "start_time",
    )

    slots = []
    seen = set()

    for availability in availabilities:
        for defense_date, start_time in build_slots_from_availability(availability):
            key = (defense_date, start_time)

            if key in seen:
                continue

            seen.add(key)
            slots.append(key)

    return slots


def build_slots_from_availability(availability):
    slots = []

    cursor = datetime.combine(
        availability.date,
        availability.start_time,
    )

    limit = datetime.combine(
        availability.date,
        availability.end_time,
    )

    while cursor + timedelta(minutes=DEFENSE_DURATION_MINUTES) <= limit:
        slots.append((
            availability.date,
            cursor.time(),
        ))
        cursor += timedelta(minutes=DEFENSE_DURATION_MINUTES)

    return slots


def build_slots(defense_date):
    windows = [
        (time(9, 0), time(12, 0)),
        (time(16, 0), time(19, 0)),
    ]

    slots = []

    for start, end in windows:
        cursor = datetime.combine(defense_date, start)
        limit = datetime.combine(defense_date, end)

        while cursor + timedelta(minutes=DEFENSE_DURATION_MINUTES) <= limit:
            slots.append(cursor.time())
            cursor += timedelta(minutes=DEFENSE_DURATION_MINUTES)

    return slots


def slot_end_time(defense_date, start_time, duration_minutes=DEFENSE_DURATION_MINUTES):
    start_datetime = datetime.combine(defense_date, start_time)
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    return end_datetime.time()


def is_professor_available(professor, defense_date, start_time, duration_minutes=DEFENSE_DURATION_MINUTES):
    end_time = slot_end_time(defense_date, start_time, duration_minutes)

    return ProfessorAvailability.objects.filter(
        professor=professor,
        date=defense_date,
        start_time__lte=start_time,
        end_time__gte=end_time,
    ).exists()


def professor_has_conflict(professor, defense_date, start_time, duration_minutes=DEFENSE_DURATION_MINUTES):
    end_time = slot_end_time(defense_date, start_time, duration_minutes)

    return DefenseSchedule.objects.filter(
        jury_student__jury__defense_date=defense_date,
        start_time__lt=end_time,
        end_time__gt=start_time,
        jury_student__jury__members__professor=professor,
    ).distinct().exists()


def juries_count_at_slot(defense_date, start_time, duration_minutes=DEFENSE_DURATION_MINUTES):
    end_time = slot_end_time(defense_date, start_time, duration_minutes)

    return DefenseSchedule.objects.filter(
        jury_student__jury__defense_date=defense_date,
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).values_list("jury_student__jury_id", flat=True).distinct().count()


def jury_slot_capacity_reached(defense_date, start_time, duration_minutes=DEFENSE_DURATION_MINUTES):
    return juries_count_at_slot(defense_date, start_time, duration_minutes) >= MAX_SIMULTANEOUS_JURIES


def professor_load_on_date(professor, defense_date):
    return JuryMember.objects.filter(
        professor=professor,
        jury__defense_date=defense_date,
    ).count()


def professor_total_scheduled_load(professor):
    return DefenseSchedule.objects.filter(
        jury_student__jury__members__professor=professor,
    ).distinct().count()


def supervised_students_count(professor):
    try:
        return professor.students.count()
    except Exception:
        return 0


@login_required
@role_required(["admin"])
def admin_results(request):
    assignments = JuryStudent.objects.select_related(
        "student",
        "jury",
        "president",
        "result",
    ).prefetch_related(
        "evaluations__professor",
    ).order_by(
        "jury__defense_date",
        "student__full_name",
    )

    from decimal import Decimal

    items = []

    for assignment in assignments:
        result = getattr(assignment, "result", None)

        submitted_evaluations = [
            evaluation for evaluation in assignment.evaluations.all()
            if evaluation.is_submitted
        ]

        ready = len(submitted_evaluations) == 3

        # Moyenne et écart provisoires calculés inline sans toucher la base
        computed_average = None
        computed_gap = None
        computed_gap_alert = False
        avg_rapport = None
        avg_presentation = None
        avg_questions = None
        if ready:
            notes = [e.final_note for e in submitted_evaluations]
            computed_average = (sum(notes, Decimal("0")) / Decimal("3")).quantize(Decimal("0.01"))
            computed_gap = (max(notes) - min(notes)).quantize(Decimal("0.01"))
            computed_gap_alert = computed_gap >= Decimal("3.00")
            avg_rapport = (sum((e.rapport_note for e in submitted_evaluations), Decimal("0")) / Decimal("3")).quantize(Decimal("0.01"))
            avg_presentation = (sum((e.presentation_note for e in submitted_evaluations), Decimal("0")) / Decimal("3")).quantize(Decimal("0.01"))
            avg_questions = (sum((e.questions_note for e in submitted_evaluations), Decimal("0")) / Decimal("3")).quantize(Decimal("0.01"))

        mention_average = result.average if (result and result.average is not None) else computed_average
        mention = mention_for_average(mention_average) if mention_average is not None else None

        items.append({
            "assignment": assignment,
            "evaluations": submitted_evaluations,
            "result": result,
            "ready": ready,
            "computed_average": computed_average,
            "computed_gap": computed_gap,
            "computed_gap_alert": computed_gap_alert,
            "avg_rapport": avg_rapport,
            "avg_presentation": avg_presentation,
            "avg_questions": avg_questions,
            "mention": mention,
        })

    return render(request, "soutenances/admin_results.html", {
        "items": items,
    })


@login_required
@role_required(["admin"])
def admin_publish_result(request, pk):
    assignment = get_object_or_404(JuryStudent, pk=pk)

    if request.method == "POST":
        result, _ = Result.objects.get_or_create(
            jury_student=assignment,
        )

        try:
            result.publish()
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            messages.success(request, "Résultat publié.")

    return redirect("admin_results")


@login_required
@role_required(["admin"])
def admin_publish_all_results(request):
    if request.method == "POST":
        count = 0

        for assignment in JuryStudent.objects.prefetch_related("evaluations"):
            if assignment.evaluations.filter(is_submitted=True).count() == 3:
                result, _ = Result.objects.get_or_create(
                    jury_student=assignment,
                )
                result.publish()
                count += 1

        messages.success(request, f"{count} résultat(s) publié(s).")

    return redirect("admin_results")


@login_required
@role_required(["admin"])
def admin_unlock_evaluation(request, pk):
    evaluation = get_object_or_404(Evaluation, pk=pk)

    if request.method == "POST":
        evaluation.unlock(request.user)

        result = getattr(evaluation.jury_student, "result", None)

        if result:
            result.is_published = False
            result.published_at = None
            result.average = None
            result.note_gap_value = None
            result.has_note_gap_alert = False
            result.save()

        messages.success(request, "Évaluation déverrouillée.")

    return redirect("admin_results")


@login_required
@role_required(["admin"])
def export_juries_pdf(request):
    lines = []

    juries = Jury.objects.prefetch_related(
        "members__professor",
        "students__student",
        "students__student__encadrant",
        "students__president",
    ).order_by(
        "defense_date",
        "name",
    )

    for jury in juries:
        lines.append("JURY :")
        lines.append(f"Nom du jury : {jury.name}")
        lines.append(f"Date de soutenance : {format_date(jury.defense_date)}")
        lines.append(f"Jury validé : {yes_no(jury.is_validated)}")
        lines.append("Membres :")

        for member in jury.members.all():
            lines.append(f"- {member.professor.full_name}")

        lines.append("Étudiants affectés :")

        if jury.students.exists():
            for assignment in jury.students.all():
                president_name = (
                    assignment.president.full_name
                    if assignment.president
                    else "Non défini"
                )

                lines.append(
                    f"- {assignment.student.matricule} | "
                    f"{assignment.student.full_name} | "
                    f"{assignment.student.filiere or '-'} | "
                    f"Encadrant : {assignment.student.encadrant.full_name} | "
                    f"Président : {president_name}"
                )
        else:
            lines.append("- Aucun étudiant affecté")

        lines.append("-----")

    return simple_pdf_response(
        "Liste des jurys",
        lines,
        "liste-jurys.pdf",
    )


@login_required
@role_required(["admin"])
def export_planning_pdf(request):
    lines = []

    schedules = DefenseSchedule.objects.select_related(
        "jury_student__student",
        "jury_student__president",
        "jury_student__jury",
    ).order_by(
        "jury_student__jury__defense_date",
        "start_time",
    )

    for schedule in schedules:
        president_name = (
            schedule.jury_student.president.full_name
            if schedule.jury_student.president
            else "Non défini"
        )

        lines.append(
            f"{format_date(schedule.jury_student.jury.defense_date)} | "
            f"{format_time(schedule.start_time)} - {format_time(schedule.end_time)} | "
            f"{schedule.jury_student.jury.name} | "
            f"{schedule.jury_student.student.matricule} | "
            f"{schedule.jury_student.student.full_name} | "
            f"Président : {president_name}"
        )

    return simple_pdf_response(
        "Planning des soutenances",
        lines,
        "planning-soutenances.pdf",
    )


@login_required
@role_required(["admin"])
def export_results_pdf(request):
    lines = []

    results = Result.objects.select_related(
        "jury_student__student",
        "jury_student__president",
        "jury_student__jury",
    ).order_by(
        "jury_student__student__full_name",
    )

    for result in results:
        status = "publié" if result.is_published else "non publié"
        alert = "oui" if result.has_note_gap_alert else "non"

        lines.append(
            f"{result.jury_student.student.matricule} | "
            f"{result.jury_student.student.full_name} | "
            f"{result.jury_student.jury.name} | "
            f"Moyenne : {decimal_text(result.average)} /20 | "
            f"Écart : {decimal_text(result.note_gap_value)} | "
            f"Alerte : {alert} | "
            f"Publication : {status}"
        )

    return simple_pdf_response(
        "Liste des résultats",
        lines,
        "résultats.pdf",
    )


@login_required
@role_required(["admin"])
def export_student_pv_pdf(request, pk):
    assignment = get_object_or_404(
        JuryStudent.objects.select_related(
            "student",
            "student__user",
            "student__encadrant",
            "president",
            "jury",
            "result",
        ).prefetch_related(
            "jury__members__professor",
            "evaluations__professor",
        ),
        pk=pk,
    )

    student = assignment.student
    jury = assignment.jury
    result = getattr(assignment, "result", None)
    schedule = get_assignment_schedule(assignment)
    pfe_request = PFERequest.objects.filter(student=student).first()

    members = [
        member.professor.full_name
        for member in jury.members.all()
    ]

    president_name = (
        assignment.president.full_name
        if assignment.president
        else "Non défini"
    )

    evaluations = list(
        assignment.evaluations.select_related("professor").order_by(
            "professor__full_name"
        )
    )

    lines = []

    lines.append("INFORMATIONS ÉTUDIANT :")
    lines.append(f"Nom complet : {student.full_name}")
    lines.append(f"Matricule : {student.matricule}")
    lines.append(f"Filière : {student.filiere or '-'}")
    lines.append(f"Téléphone : {student.user.phone_number or '-'}")
    lines.append(f"Encadrant : {student.encadrant.full_name}")
    lines.append(f"Président de soutenance : {president_name}")
    lines.append("")

    lines.append("DEMANDE DE SOUTENANCE :")
    if pfe_request:
        lines.append(f"Statut de la demande : {pfe_request.get_status_display()}")
        lines.append(f"Date de dépôt : {format_datetime(pfe_request.submitted_at)}")
        lines.append(f"Validation encadrant : {format_datetime(pfe_request.professor_reviewed_at)}")
        lines.append(f"Validation département de l'IUP : {format_datetime(pfe_request.admin_reviewed_at)}")

        if pfe_request.professor_comment:
            lines.append(f"Commentaire encadrant : {pfe_request.professor_comment}")

        if pfe_request.admin_comment:
            lines.append(f"Commentaire département de l'IUP : {pfe_request.admin_comment}")
    else:
        lines.append("Aucune demande trouvée.")
    lines.append("")

    lines.append("JURY ET PLANNING :")
    lines.append(f"Jury : {jury.name}")
    lines.append(f"Date de soutenance : {format_date(jury.defense_date)}")

    if schedule:
        lines.append(
            f"Horaire : {format_time(schedule.start_time)} - {format_time(schedule.end_time)}"
        )
    else:
        lines.append("Horaire : non planifié")

    lines.append("Membres du jury :")
    for member_name in members:
        lines.append(f"- {member_name}")
    lines.append("")

    lines.append("ÉVALUATIONS :")
    if evaluations:
        for evaluation in evaluations:
            statut = "envoyée" if evaluation.is_submitted else "brouillon"

            lines.append(f"Professeur : {evaluation.professor.full_name}")
            lines.append(f"  Rapport : {decimal_text(evaluation.rapport_note)} /20 | Coef. 0.30")
            lines.append(f"  Présentation : {decimal_text(evaluation.presentation_note)} /20 | Coef. 0.30")
            lines.append(f"  Réponses aux questions : {decimal_text(evaluation.questions_note)} /20 | Coef. 0.40")
            lines.append(f"  Note finale professeur : {decimal_text(evaluation.final_note)} /20")
            lines.append(f"  Statut : {statut}")
    else:
        lines.append("Aucune évaluation enregistrée.")
    lines.append("")

    lines.append("RÉSULTAT FINAL :")
    if result:
        lines.append(f"Moyenne finale : {decimal_text(result.average)} /20")
        lines.append(f"Écart entre notes : {decimal_text(result.note_gap_value)}")
        lines.append(f"Alerte écart >= 3 : {yes_no(result.has_note_gap_alert)}")
        lines.append(f"Résultat publié : {yes_no(result.is_published)}")
        lines.append(f"Date de publication : {format_datetime(result.published_at)}")
    else:
        lines.append("Résultat non calculé.")
    lines.append("")

    lines.append("DÉCISION :")
    if result and result.is_published:
        lines.append("Décision : résultat validé et publié par le département de l'IUP.")
    else:
        lines.append("Décision : en attente de publication par le département de l'IUP.")
    lines.append("")

    lines.append("SIGNATURES :")
    lines.append(f"Président de soutenance ({president_name}) : ______________________________")
    lines.append("Membre du jury : _________________________________")
    lines.append("Membre du jury : _________________________________")
    lines.append("Département de l'IUP : _________________________________")

    return simple_pdf_response(
        f"PV de soutenance - {student.full_name}",
        lines,
        f"pv-{student.matricule}.pdf",
    )


def get_assignment_schedule(assignment):
    try:
        return assignment.schedule
    except Exception:
        return None


def format_date(value):
    if not value:
        return "-"

    return value.strftime("%d/%m/%Y")


def format_time(value):
    if not value:
        return "-"

    return value.strftime("%H:%M")


def format_datetime(value):
    if not value:
        return "-"

    try:
        value = timezone.localtime(value)
    except Exception:
        pass

    return value.strftime("%d/%m/%Y %H:%M")


def decimal_text(value):
    if value is None:
        return "-"

    return str(value).replace(".", ",")


def yes_no(value):
    return "oui" if value else "non"


def get_common_available_slots(encadrants):
    """Real, server-side source of truth: future slots where every given
    encadrant is both declared-available and conflict-free. Used by the
    AJAX hint endpoint and by the enforced quick-create flow."""

    common_slots = None

    for encadrant in encadrants:
        professor_slots = set(build_future_slots_for_professor(encadrant))
        professor_slots = {
            (defense_date, start_time)
            for defense_date, start_time in professor_slots
            if is_professor_available(encadrant, defense_date, start_time)
            and not professor_has_conflict(encadrant, defense_date, start_time)
        }

        if common_slots is None:
            common_slots = professor_slots
        else:
            common_slots &= professor_slots

    return sorted(common_slots or [])


def get_available_professors_at_slot(defense_date, start_time):
    """Real, server-side source of truth: professors actually available
    (declared availability, no conflict) at a given date/time."""

    return [
        professor for professor in ProfessorProfile.objects.order_by("full_name")
        if is_professor_available(professor, defense_date, start_time)
        and not professor_has_conflict(professor, defense_date, start_time)
    ]


@login_required
@role_required(["admin"])
def admin_jury_helper_slots(request):
    """AJAX helper (informational only, used by the free-form manual jury
    creation page): given one or more student ids, return the future slots
    where every selected student's encadrant is available."""

    student_ids = request.GET.getlist("student_id")

    if not student_ids:
        return JsonResponse({"slots": [], "encadrants": []})

    students = StudentProfile.objects.filter(
        id__in=student_ids
    ).select_related("encadrant")

    encadrants = {
        student.encadrant for student in students if student.encadrant_id
    }

    if not encadrants:
        return JsonResponse({"slots": [], "encadrants": []})

    common_slots = get_common_available_slots(encadrants)

    return JsonResponse({
        "slots": [
            {
                "date": defense_date.isoformat(),
                "start_time": start_time.strftime("%H:%M"),
                "label": f"{defense_date.strftime('%d/%m/%Y')} à {start_time.strftime('%H:%M')}",
            }
            for defense_date, start_time in common_slots
        ],
        "encadrants": [
            {"id": encadrant.id, "name": encadrant.full_name}
            for encadrant in encadrants
        ],
    })


@login_required
@role_required(["admin"])
def admin_jury_helper_members(request):
    """AJAX helper (informational only): given a date and a start time,
    return the professors who are actually available at that slot."""

    date_raw = request.GET.get("date")
    start_time_raw = request.GET.get("start_time")

    if not date_raw or not start_time_raw:
        return JsonResponse({"available_professor_ids": [], "all_count": 0})

    try:
        defense_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        start_time = datetime.strptime(start_time_raw, "%H:%M").time()
    except ValueError:
        return JsonResponse({"error": "Date ou heure invalide."}, status=400)

    available_ids = [
        professor.id for professor in get_available_professors_at_slot(defense_date, start_time)
    ]

    return JsonResponse({
        "available_professor_ids": available_ids,
        "all_count": ProfessorProfile.objects.count(),
    })
