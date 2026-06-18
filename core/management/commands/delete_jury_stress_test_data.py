"""
Supprime proprement toutes les données TESTSTRESS.
Idempotente : peut être relancée sans erreur même si les données ont déjà été supprimées.

Usage :
    python manage.py delete_jury_stress_test_data
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomUser
from professors.models import ProfessorAvailability, ProfessorProfile
from students.models import StudentProfile, StudentReference
from soutenances.models import (
    DefenseSchedule,
    Evaluation,
    Jury,
    JuryMember,
    JuryStudent,
    PFERequest,
    Result,
)


PREFIX = "TESTSTRESS"

PROFESSOR_USERNAMES = [f"teststress.prof.{l}" for l in "abcdefgh"]
STUDENT_USERNAMES   = [f"teststress.student{i:02d}" for i in range(1, 20)]


class Command(BaseCommand):
    help = "Supprime toutes les données TESTSTRESS (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        total = {k: 0 for k in ["ref", "eval", "result", "schedule", "jury_student",
                                  "jury_member", "jury", "pfe", "student_profile",
                                  "student_user", "avail", "prof_profile", "prof_user"]}

        # ── 1. Étudiants TESTSTRESS ─────────────────────────────────────────
        student_users = CustomUser.objects.filter(username__in=STUDENT_USERNAMES)
        student_profiles = StudentProfile.objects.filter(user__in=student_users)

        # Jurys ayant des JuryStudent liés à ces étudiants
        jury_ids_from_students = JuryStudent.objects.filter(
            student__in=student_profiles
        ).values_list("jury_id", flat=True).distinct()

        # DefenseSchedule → JuryStudent → étudiants
        ds_count, _ = DefenseSchedule.objects.filter(
            jury_student__student__in=student_profiles
        ).delete()
        total["schedule"] += ds_count

        # Evaluations liées aux étudiants TESTSTRESS
        ev_count, _ = Evaluation.objects.filter(
            jury_student__student__in=student_profiles
        ).delete()
        total["eval"] += ev_count

        # Results liés aux étudiants TESTSTRESS
        re_count, _ = Result.objects.filter(
            jury_student__student__in=student_profiles
        ).delete()
        total["result"] += re_count

        # JuryStudent
        js_count, _ = JuryStudent.objects.filter(
            student__in=student_profiles
        ).delete()
        total["jury_student"] += js_count

        # JuryMember et Jury eux-mêmes (seulement ceux vides après suppression des étudiants)
        jm_count, _ = JuryMember.objects.filter(
            jury_id__in=jury_ids_from_students
        ).delete()
        total["jury_member"] += jm_count

        j_count, _ = Jury.objects.filter(
            id__in=jury_ids_from_students
        ).delete()
        total["jury"] += j_count

        # PFERequest
        pfe_count, _ = PFERequest.objects.filter(
            student__in=student_profiles
        ).delete()
        total["pfe"] += pfe_count

        # StudentProfile
        sp_count, _ = student_profiles.delete()
        total["student_profile"] += sp_count

        # StudentReference TESTSTRESS
        ref_count, _ = StudentReference.objects.filter(
            matricule__startswith=PREFIX
        ).delete()
        total["ref"] += ref_count

        # Comptes utilisateurs étudiants
        su_count, _ = student_users.delete()
        total["student_user"] += su_count

        # ── 2. Professeurs TESTSTRESS ────────────────────────────────────────
        prof_users    = CustomUser.objects.filter(username__in=PROFESSOR_USERNAMES)
        prof_profiles = ProfessorProfile.objects.filter(user__in=prof_users)

        # Disponibilités
        av_count, _ = ProfessorAvailability.objects.filter(
            professor__in=prof_profiles
        ).delete()
        total["avail"] += av_count

        # JuryMember où le professeur est TESTSTRESS (jurys générés après création)
        extra_jm, _ = JuryMember.objects.filter(professor__in=prof_profiles).delete()
        total["jury_member"] += extra_jm

        # Jurys désormais sans aucun étudiant ni membre TESTSTRESS → supprimer s'ils
        # ont "TESTSTRESS" dans le nom (sécurité : ne pas toucher aux jurys réels)
        orphan_ids = list(
            Jury.objects.filter(name__icontains="TESTSTRESS")
                        .exclude(id__in=jury_ids_from_students)
                        .values_list("id", flat=True)
        )
        if orphan_ids:
            oj_count, _ = Jury.objects.filter(id__in=orphan_ids).delete()
            total["jury"] += oj_count

        # Profils
        pp_count, _ = prof_profiles.delete()
        total["prof_profile"] += pp_count

        # Comptes utilisateurs professeurs
        pu_count, _ = prof_users.delete()
        total["prof_user"] += pu_count

        # ── Rapport ──────────────────────────────────────────────────────────
        grand_total = sum(total.values())

        if grand_total == 0:
            self.stdout.write(self.style.WARNING(
                "Aucune donnée TESTSTRESS trouvée (déjà supprimée ou jamais créée)."
            ))
            return

        self.stdout.write(self.style.SUCCESS("Donnees TESTSTRESS supprimees :"))
        self.stdout.write(f"  Professeurs (comptes)      : {total['prof_user']}")
        self.stdout.write(f"  Professeurs (profils)      : {total['prof_profile']}")
        self.stdout.write(f"  Disponibilités             : {total['avail']}")
        self.stdout.write(f"  Étudiants (comptes)        : {total['student_user']}")
        self.stdout.write(f"  Étudiants (profils)        : {total['student_profile']}")
        self.stdout.write(f"  StudentReference           : {total['ref']}")
        self.stdout.write(f"  PFERequest                 : {total['pfe']}")
        self.stdout.write(f"  JuryStudent                : {total['jury_student']}")
        self.stdout.write(f"  DefenseSchedule            : {total['schedule']}")
        self.stdout.write(f"  Evaluation                 : {total['eval']}")
        self.stdout.write(f"  Result                     : {total['result']}")
        self.stdout.write(f"  JuryMember                 : {total['jury_member']}")
        self.stdout.write(f"  Jury                       : {total['jury']}")
        self.stdout.write(f"  ---------------------------------")
        self.stdout.write(f"  Total suppressions         : {grand_total}")
