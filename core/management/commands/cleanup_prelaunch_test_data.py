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
        "Nettoyage avant ouverture reelle : supprime les comptes etudiants de "
        "test (iup23439, iup23000/2222/1111/1010) et leurs PFERequest/JuryStudent/"
        "DefenseSchedule/Evaluation/Result associes (cascade), supprime les jurys "
        "devenus vides, supprime les comptes utilisateurs professeurs de test "
        "(prof_5/6/8/10/11) et leurs disponibilites, et detache (user=None) les "
        "ProfessorProfile reels correspondants pour permettre une vraie inscription. "
        "Ne touche jamais a StudentReference, aux ProfessorProfile eux-memes, ni "
        "au compte admin reel. Relancable sans risque."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {}

        # 1) Comptes etudiants de test : la suppression de StudentProfile cascade
        # sur PFERequest, JuryStudent, DefenseSchedule, Evaluation, Result.
        student_profiles = StudentProfile.objects.filter(
            user__username__in=TEST_STUDENT_USERNAMES
        )
        counts["StudentProfile (test) supprimes"] = student_profiles.count()
        affected_jury_ids = list(
            Jury.objects.filter(students__student__in=student_profiles)
            .values_list("id", flat=True)
            .distinct()
        )
        student_profiles.delete()

        test_student_users = CustomUser.objects.filter(
            username__in=TEST_STUDENT_USERNAMES
        )
        counts["CustomUser etudiants (test) supprimes"] = test_student_users.count()
        test_student_users.delete()

        # 2) Jurys devenus vides (plus aucun etudiant affecte) -> supprimer.
        empty_juries = Jury.objects.filter(id__in=affected_jury_ids, students__isnull=True)
        counts["Jury devenus vides supprimes"] = empty_juries.count()
        empty_juries.delete()

        # 3) Comptes utilisateurs professeurs de test : detacher le ProfessorProfile
        # reel (user=None) puis supprimer le compte utilisateur et ses disponibilites.
        test_professor_users = CustomUser.objects.filter(
            username__in=TEST_PROFESSOR_USERNAMES
        )
        professor_profiles = ProfessorProfile.objects.filter(
            user__in=test_professor_users
        )

        counts["ProfessorAvailability (test) supprimees"] = (
            ProfessorAvailability.objects.filter(professor__in=professor_profiles).count()
        )
        ProfessorAvailability.objects.filter(professor__in=professor_profiles).delete()

        counts["ProfessorProfile detaches (user remis a None)"] = professor_profiles.count()
        for profile in professor_profiles:
            profile.user = None
            profile.save(update_fields=["user"])

        counts["CustomUser professeurs (test) supprimes"] = test_professor_users.count()
        test_professor_users.delete()

        self.stdout.write(self.style.SUCCESS("Nettoyage pre-ouverture termine."))
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count}")
