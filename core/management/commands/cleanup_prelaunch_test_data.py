from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomUser
from professors.models import ProfessorAvailability, ProfessorProfile
from soutenances.models import Jury
from students.models import StudentProfile


TEST_STUDENT_USERNAMES = ["iup23439", "iup23000", "iup2222", "iup1111", "iup1010"]
TEST_PROFESSOR_USERNAMES = ["prof_5", "prof_6", "prof_8", "prof_10", "prof_11"]


class Command(BaseCommand):
    help = (
        "Nettoyage avant ouverture réelle : supprime les comptes étudiants de "
        "test (iup23439, iup23000/2222/1111/1010) et leurs PFERequest/JuryStudent/"
        "DefenseSchedule/Evaluation/Result associés (cascade), supprime les jurys "
        "devenus vides, supprime les comptes utilisateurs professeurs de test "
        "(prof_5/6/8/10/11) et leurs disponibilités, et détache (user=None) les "
        "ProfessorProfile réels correspondants pour permettre une vraie inscription. "
        "Ne touche jamais à StudentReference, aux ProfessorProfile eux-mêmes, ni "
        "au compte admin réel. Relançable sans risque."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {}

        # 1) Comptes étudiants de test : la suppression de StudentProfile cascade
        # sur PFERequest, JuryStudent, DefenseSchedule, Evaluation, Result.
        student_profiles = StudentProfile.objects.filter(
            user__username__in=TEST_STUDENT_USERNAMES
        )
        counts["StudentProfile (test) supprimés"] = student_profiles.count()
        affected_jury_ids = list(
            Jury.objects.filter(students__student__in=student_profiles)
            .values_list("id", flat=True)
            .distinct()
        )
        student_profiles.delete()

        test_student_users = CustomUser.objects.filter(
            username__in=TEST_STUDENT_USERNAMES
        )
        counts["CustomUser étudiants (test) supprimés"] = test_student_users.count()
        test_student_users.delete()

        # 2) Jurys devenus vides (plus aucun étudiant affecté) -> supprimer.
        empty_juries = Jury.objects.filter(id__in=affected_jury_ids, students__isnull=True)
        counts["Jurys devenus vides supprimés"] = empty_juries.count()
        empty_juries.delete()

        # 3) Comptes utilisateurs professeurs de test : détacher le ProfessorProfile
        # réel (user=None) puis supprimer le compte utilisateur et ses disponibilités.
        test_professor_users = CustomUser.objects.filter(
            username__in=TEST_PROFESSOR_USERNAMES
        )
        professor_profiles = ProfessorProfile.objects.filter(
            user__in=test_professor_users
        )

        counts["ProfessorAvailability (test) supprimées"] = (
            ProfessorAvailability.objects.filter(professor__in=professor_profiles).count()
        )
        ProfessorAvailability.objects.filter(professor__in=professor_profiles).delete()

        counts["ProfessorProfile détachés (user remis à None)"] = professor_profiles.count()
        for profile in professor_profiles:
            profile.user = None
            profile.save(update_fields=["user"])

        counts["CustomUser professeurs (test) supprimés"] = test_professor_users.count()
        test_professor_users.delete()

        self.stdout.write(self.style.SUCCESS("Nettoyage pré-ouverture terminé."))
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count}")
