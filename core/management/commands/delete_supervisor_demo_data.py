"""
Supprime proprement toutes les données DEMOENC.
Idempotente : peut être relancée sans erreur même si les données ont déjà été supprimées.

Usage :
    python manage.py delete_supervisor_demo_data
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


PREFIX = "DEMOENC"

PROFESSOR_USERNAMES = [f"demoenc.prof.{l.lower()}" for l in "ABCDEF"]
STUDENT_USERNAMES   = [f"demoenc.student{i:02d}" for i in range(1, 13)]


class Command(BaseCommand):
    help = "Supprime toutes les données DEMOENC (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        total = {k: 0 for k in [
            "ref", "eval", "result", "schedule", "jury_student",
            "jury_member", "jury", "pfe", "student_profile",
            "student_user", "avail", "prof_profile", "prof_user",
        ]}

        # ── 1. Étudiants DEMOENC ────────────────────────────────────────────
        student_users    = CustomUser.objects.filter(username__in=STUDENT_USERNAMES)
        student_profiles = StudentProfile.objects.filter(user__in=student_users)

        # Jurys liés à ces étudiants
        jury_ids = JuryStudent.objects.filter(
            student__in=student_profiles
        ).values_list("jury_id", flat=True).distinct()

        # DefenseSchedule
        n, _ = DefenseSchedule.objects.filter(
            jury_student__student__in=student_profiles
        ).delete()
        total["schedule"] += n

        # Evaluations
        n, _ = Evaluation.objects.filter(
            jury_student__student__in=student_profiles
        ).delete()
        total["eval"] += n

        # Results
        n, _ = Result.objects.filter(
            jury_student__student__in=student_profiles
        ).delete()
        total["result"] += n

        # JuryStudent
        n, _ = JuryStudent.objects.filter(
            student__in=student_profiles
        ).delete()
        total["jury_student"] += n

        # JuryMember (pour les jurys DEMOENC devenus vides)
        n, _ = JuryMember.objects.filter(jury_id__in=jury_ids).delete()
        total["jury_member"] += n

        # Jury
        n, _ = Jury.objects.filter(id__in=jury_ids).delete()
        total["jury"] += n

        # PFERequest
        n, _ = PFERequest.objects.filter(student__in=student_profiles).delete()
        total["pfe"] += n

        # StudentProfile
        n, _ = student_profiles.delete()
        total["student_profile"] += n

        # StudentReference DEMOENC
        n, _ = StudentReference.objects.filter(matricule__startswith=PREFIX).delete()
        total["ref"] += n

        # Comptes étudiants
        n, _ = student_users.delete()
        total["student_user"] += n

        # ── 2. Professeurs DEMOENC ───────────────────────────────────────────
        prof_users    = CustomUser.objects.filter(username__in=PROFESSOR_USERNAMES)
        prof_profiles = ProfessorProfile.objects.filter(user__in=prof_users)

        # Disponibilités
        n, _ = ProfessorAvailability.objects.filter(
            professor__in=prof_profiles
        ).delete()
        total["avail"] += n

        # Profils
        n, _ = prof_profiles.delete()
        total["prof_profile"] += n

        # Comptes professeurs
        n, _ = prof_users.delete()
        total["prof_user"] += n

        # ── 3. Rapport ───────────────────────────────────────────────────────
        grand_total = sum(total.values())

        if grand_total == 0:
            self.stdout.write(self.style.WARNING(
                "Aucune donnée DEMOENC trouvée (déjà supprimée ou jamais créée)."
            ))
            return

        self.stdout.write(self.style.SUCCESS("Données DEMOENC supprimées :"))
        self.stdout.write(f"  Professeurs (comptes)      : {total['prof_user']}")
        self.stdout.write(f"  Professeurs (profils)      : {total['prof_profile']}")
        self.stdout.write(f"  Disponibilités             : {total['avail']}")
        self.stdout.write(f"  Étudiants (comptes)        : {total['student_user']}")
        self.stdout.write(f"  Étudiants (profils)        : {total['student_profile']}")
        self.stdout.write(f"  StudentReference           : {total['ref']}")
        self.stdout.write(f"  PFERequest                 : {total['pfe']}")
        self.stdout.write(f"  JuryStudent                : {total['jury_student']}")
        self.stdout.write(f"  DefenseSchedule            : {total['schedule']}")
        self.stdout.write(f"  Évaluation                 : {total['eval']}")
        self.stdout.write(f"  Result                     : {total['result']}")
        self.stdout.write(f"  JuryMember                 : {total['jury_member']}")
        self.stdout.write(f"  Jury                       : {total['jury']}")
        self.stdout.write(f"  ---------------------------------")
        self.stdout.write(f"  Total suppressions         : {grand_total}")
