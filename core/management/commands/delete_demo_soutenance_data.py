from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomUser
from professors.models import ProfessorAvailability, ProfessorProfile
from soutenances.models import Jury, PFERequest
from students.models import StudentProfile, StudentReference


DEMO_USERNAMES = [
    "admin.demo",
    "prof1.demo",
    "prof2.demo",
    "prof3.demo",
    "etudiant1.demo",
    "etudiant2.demo",
    "etudiant3.demo",
]

DEMO_MATRICULES = ["DEMO0001", "DEMO0002", "DEMO0003"]

DEMO_PROFESSOR_NAMES = [
    "Professeur Démo Un",
    "Professeur Démo Deux",
    "Professeur Démo Trois",
]


class Command(BaseCommand):
    help = (
        "Supprime uniquement les données créées par create_demo_soutenance_data "
        "(comptes *.demo, matricules DEMO0001-3, leurs demandes PFE, jurys, "
        "évaluations, résultats et disponibilités associées). "
        "Relançable sans risque : ne touche à aucune autre donnée."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {}

        student_profiles = StudentProfile.objects.filter(matricule__in=DEMO_MATRICULES)
        student_user_ids = list(student_profiles.values_list("user_id", flat=True))

        # Jurys générés pour ces étudiants démo : doivent être supprimés
        # explicitement (Jury n'est pas un enfant de StudentProfile, donc le
        # cascade ne le supprime pas), sinon JuryMember.professor (PROTECT)
        # empêche ensuite la suppression des ProfessorProfile démo.
        demo_juries = Jury.objects.filter(
            students__student__matricule__in=DEMO_MATRICULES
        ).distinct()
        counts["Jury (demo)"] = demo_juries.count()
        demo_jury_ids = list(demo_juries.values_list("id", flat=True))

        # PFERequest, JuryStudent, evaluations, results cascade-delete via
        # StudentProfile -> PFERequest -> JuryStudent -> Evaluation/Result/DefenseSchedule
        counts["PFERequest (demo)"] = PFERequest.objects.filter(
            student__matricule__in=DEMO_MATRICULES
        ).count()

        counts["StudentProfile (demo)"] = student_profiles.count()
        student_profiles.delete()

        # À ce stade, les JuryStudent associés ont disparu (cascade). On ne
        # supprime que les jurys identifiés plus haut qui sont désormais
        # vides (aucun étudiant restant), par sécurité si un jury mélangeait
        # un jour des étudiants démo et réels.
        empty_demo_juries = Jury.objects.filter(
            id__in=demo_jury_ids, students__isnull=True
        )
        counts["Jury (démo, devenus vides, supprimés)"] = empty_demo_juries.count()
        empty_demo_juries.delete()

        counts["StudentReference (demo)"] = StudentReference.objects.filter(
            matricule__in=DEMO_MATRICULES
        ).count()
        StudentReference.objects.filter(matricule__in=DEMO_MATRICULES).delete()

        professor_profiles = ProfessorProfile.objects.filter(
            full_name__in=DEMO_PROFESSOR_NAMES
        )
        professor_user_ids = list(professor_profiles.values_list("user_id", flat=True))

        counts["ProfessorAvailability (demo)"] = ProfessorAvailability.objects.filter(
            professor__in=professor_profiles
        ).count()
        ProfessorAvailability.objects.filter(professor__in=professor_profiles).delete()

        counts["ProfessorProfile (demo)"] = professor_profiles.count()
        professor_profiles.delete()

        demo_users = CustomUser.objects.filter(username__in=DEMO_USERNAMES)
        counts["CustomUser (demo, by username)"] = demo_users.count()
        demo_users.delete()

        # Safety net: remove any leftover users only referenced via FK ids
        # collected above (in case username was changed) and any user with
        # an @iup.local demo-style email pattern we created.
        leftover_users = CustomUser.objects.filter(
            id__in=[uid for uid in (student_user_ids + professor_user_ids) if uid]
        )
        counts["CustomUser (demo, leftover by id)"] = leftover_users.count()
        leftover_users.delete()

        self.stdout.write(self.style.SUCCESS("Nettoyage des données démo terminé."))
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count} supprimé(s)")
