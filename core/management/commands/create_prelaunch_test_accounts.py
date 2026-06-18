from datetime import time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from professors.models import ProfessorAvailability, ProfessorProfile
from soutenances.models import (
    DefenseSchedule,
    Evaluation,
    Jury,
    JuryMember,
    JuryStudent,
    PFERequest,
    Result,
)
from students.models import StudentProfile, StudentReference


PREFIX = "PRETEST"
PASSWORD = "Test@2026"
ADMIN_USERNAME = "pretest.admin"
ADMIN_EMAIL = "pretest.admin@iup.local"
ADMIN_PHONE = "91000000"

PROFESSORS = [
    ("A", "pretest.prof.a", "pretest.prof.a@iup.local", "91000001", "PRETEST Professeur A"),
    ("B", "pretest.prof.b", "pretest.prof.b@iup.local", "91000002", "PRETEST Professeur B"),
    ("C", "pretest.prof.c", "pretest.prof.c@iup.local", "91000003", "PRETEST Professeur C"),
    ("D", "pretest.prof.d", "pretest.prof.d@iup.local", "91000004", "PRETEST Professeur D"),
    ("E", "pretest.prof.e", "pretest.prof.e@iup.local", "91000005", "PRETEST Professeur E"),
]

STUDENTS = [
    ("001", "PRETEST Étudiant 01 - demande à envoyer", "DS", "A", "Nouakchott Digital"),
    ("002", "PRETEST Étudiant 02 - attente encadrant", "FINTECH", "A", "Banque Test"),
    ("003", "PRETEST Étudiant 03 - attente département", "LGTR", "B", "Logistique Test"),
    ("004", "PRETEST Étudiant 04 - accepté sans jury", "RXTL", "C", "Télécom Test"),
    ("005", "PRETEST Étudiant 05 - jury publié", "MAEF", "A", "Finance Test"),
    ("006", "PRETEST Étudiant 06 - soutenance démarrée", "MAN", "B", "Management Test"),
    ("007", "PRETEST Étudiant 07 - résultat à publier", "DS", "C", "Data Test"),
    ("008", "PRETEST Étudiant 08 - résultat publié", "FINTECH", "D", "Fintech Test"),
    ("009", "PRETEST Étudiant 09 - refus encadrant", "LGTR", "E", "Archive Test"),
    ("010", "PRETEST Étudiant 10 - refus département", "RXTL", "A", "Contrôle Test"),
]


class Command(BaseCommand):
    help = (
        "Crée des comptes et données PRETEST pour vérifier le parcours complet "
        "avant ouverture aux vrais étudiants, professeurs et administrateurs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Supprime toutes les données PRETEST créées par cette commande.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["delete"]:
            self.delete_pretest_data()
            return

        admin = self.ensure_user(
            username=ADMIN_USERNAME,
            email=ADMIN_EMAIL,
            phone=ADMIN_PHONE,
            role=CustomUser.ROLE_ADMIN,
            is_staff=True,
            is_superuser=True,
        )

        professors = self.create_professors()
        students = self.create_students(professors)
        self.create_requests(admin, professors, students)
        self.create_availabilities(professors)
        juries = self.create_juries(professors)
        assignments = self.create_assignments(admin, juries, students)
        self.create_evaluations_and_results(assignments)

        self.print_summary()

    def ensure_user(self, username, email, phone, role, is_staff=False, is_superuser=False):
        user, _ = CustomUser.objects.get_or_create(username=username)
        user.email = email
        user.phone_number = phone
        user.role = role
        user.is_active = True
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.set_password(PASSWORD)
        user.save()
        return user

    def create_professors(self):
        professors = {}
        for letter, username, email, phone, full_name in PROFESSORS:
            user = self.ensure_user(
                username=username,
                email=email,
                phone=phone,
                role=CustomUser.ROLE_PROFESSOR,
            )
            profile, _ = ProfessorProfile.objects.get_or_create(
                full_name=full_name,
                defaults={"user": user, "phone": phone},
            )
            profile.user = user
            profile.phone = phone
            profile.save()
            professors[letter] = profile
        return professors

    def create_students(self, professors):
        students = {}
        for index, (suffix, full_name, filiere, professor_letter, entreprise) in enumerate(STUDENTS, start=1):
            matricule = f"{PREFIX}{suffix}"
            username = f"pretest.student{suffix}"
            email = f"{username}@iup.local"
            phone = f"910001{index:02d}"
            encadrant = professors[professor_letter]

            StudentReference.objects.update_or_create(
                matricule=matricule,
                defaults={
                    "full_name": full_name,
                    "filiere": filiere,
                    "encadrant_name": encadrant.full_name,
                },
            )

            user = self.ensure_user(
                username=username,
                email=email,
                phone=phone,
                role=CustomUser.ROLE_STUDENT,
            )
            profile, _ = StudentProfile.objects.get_or_create(
                matricule=matricule,
                defaults={
                    "user": user,
                    "full_name": full_name,
                    "filiere": filiere,
                    "encadrant": encadrant,
                    "entreprise": entreprise,
                },
            )
            profile.user = user
            profile.full_name = full_name
            profile.filiere = filiere
            profile.encadrant = encadrant
            profile.entreprise = entreprise
            profile.save()
            students[suffix] = profile
        return students

    def create_requests(self, admin, professors, students):
        now = timezone.now()
        statuses = {
            "002": PFERequest.STATUS_PENDING_PROFESSOR,
            "003": PFERequest.STATUS_PENDING_ADMIN,
            "004": PFERequest.STATUS_ACCEPTED,
            "005": PFERequest.STATUS_ACCEPTED,
            "006": PFERequest.STATUS_ACCEPTED,
            "007": PFERequest.STATUS_ACCEPTED,
            "008": PFERequest.STATUS_ACCEPTED,
            "009": PFERequest.STATUS_REFUSED_PROFESSOR,
            "010": PFERequest.STATUS_REFUSED_ADMIN,
        }

        for suffix, status in statuses.items():
            student = students[suffix]
            request, _ = PFERequest.objects.get_or_create(student=student)
            request.status = status
            request.professor_comment = None
            request.admin_comment = None
            request.reviewed_by_professor = None
            request.reviewed_by_admin = None
            request.reviewed_by = None
            request.professor_reviewed_at = None
            request.admin_reviewed_at = None
            request.reviewed_at = None

            if status in {
                PFERequest.STATUS_PENDING_ADMIN,
                PFERequest.STATUS_ACCEPTED,
                PFERequest.STATUS_REFUSED_ADMIN,
            }:
                request.reviewed_by_professor = student.encadrant
                request.professor_reviewed_at = now

            if status == PFERequest.STATUS_ACCEPTED:
                request.reviewed_by_admin = admin
                request.reviewed_by = admin
                request.admin_reviewed_at = now
                request.reviewed_at = now

            if status == PFERequest.STATUS_REFUSED_PROFESSOR:
                request.reviewed_by_professor = student.encadrant
                request.professor_reviewed_at = now
                request.professor_comment = "Dossier de test refusé par l'encadrant."

            if status == PFERequest.STATUS_REFUSED_ADMIN:
                request.reviewed_by_admin = admin
                request.reviewed_by = admin
                request.admin_reviewed_at = now
                request.reviewed_at = now
                request.admin_comment = "Dossier de test refusé par le département."

            request.save()

    def create_availabilities(self, professors):
        defense_date = timezone.localdate() + timedelta(days=7)
        for professor in professors.values():
            ProfessorAvailability.objects.get_or_create(
                professor=professor,
                date=defense_date,
                start_time=time(9, 0),
                end_time=time(12, 0),
            )
            ProfessorAvailability.objects.get_or_create(
                professor=professor,
                date=defense_date,
                start_time=time(14, 0),
                end_time=time(17, 0),
            )

    def create_juries(self, professors):
        defense_date = timezone.localdate() + timedelta(days=7)
        configs = {
            "PRETEST Jury A": [professors["A"], professors["B"], professors["C"]],
            "PRETEST Jury B": [professors["B"], professors["D"], professors["E"]],
            "PRETEST Jury C": [professors["C"], professors["A"], professors["D"]],
        }
        juries = {}
        for name, members in configs.items():
            jury, _ = Jury.objects.get_or_create(
                name=name,
                defaults={"defense_date": defense_date, "is_validated": True},
            )
            jury.defense_date = defense_date
            jury.is_validated = True
            jury.save()
            for member in members:
                JuryMember.objects.get_or_create(jury=jury, professor=member)
            juries[name] = jury
        return juries

    def create_assignments(self, admin, juries, students):
        mapping = {
            "005": (juries["PRETEST Jury A"], "B", time(9, 0)),
            "006": (juries["PRETEST Jury B"], "D", time(9, 30)),
            "007": (juries["PRETEST Jury C"], "A", time(10, 0)),
            "008": (juries["PRETEST Jury C"], "A", time(10, 30)),
        }

        assignments = {}
        for suffix, (jury, president_letter, start_time) in mapping.items():
            student = students[suffix]
            president = next(
                member.professor
                for member in jury.members.select_related("professor")
                if member.professor.full_name.endswith(f" {president_letter}")
            )
            assignment, _ = JuryStudent.objects.get_or_create(
                student=student,
                defaults={"jury": jury, "president": president},
            )
            assignment.jury = jury
            assignment.president = president

            if suffix in {"006", "007", "008"}:
                assignment.presentation_started = True
                assignment.presentation_started_at = timezone.now()
                assignment.presentation_started_by = admin
                assignment.pfe_soutenable_status = JuryStudent.PFE_SOUTENABLE_OUI
                assignment.pfe_soutenable_decided_at = timezone.now()
                assignment.pfe_soutenable_decided_by = admin

            assignment.save()

            DefenseSchedule.objects.update_or_create(
                jury_student=assignment,
                defaults={
                    "start_time": start_time,
                    "duration_minutes": 30,
                },
            )
            assignments[suffix] = assignment
        return assignments

    def create_evaluations_and_results(self, assignments):
        for suffix in ("007", "008"):
            assignment = assignments[suffix]
            notes = [
                (Decimal("15.00"), Decimal("16.00"), Decimal("15.50")),
                (Decimal("13.00"), Decimal("14.00"), Decimal("13.50")),
                (Decimal("17.00"), Decimal("16.50"), Decimal("17.00")),
            ]
            for member, values in zip(assignment.jury.members.select_related("professor"), notes):
                evaluation, _ = Evaluation.objects.get_or_create(
                    jury_student=assignment,
                    professor=member.professor,
                    defaults={
                        "rapport_note": values[0],
                        "presentation_note": values[1],
                        "questions_note": values[2],
                    },
                )
                evaluation.rapport_note = values[0]
                evaluation.presentation_note = values[1]
                evaluation.questions_note = values[2]
                was_submitted = evaluation.is_submitted
                evaluation.is_locked = False
                evaluation.save()
                if was_submitted:
                    evaluation.is_locked = True
                    evaluation.save(update_fields=["is_locked"])
                else:
                    evaluation.submit()

            result, _ = Result.objects.get_or_create(jury_student=assignment)
            result.calculate_average()
            if suffix == "008":
                result.publish()
            else:
                result.is_published = False
                result.published_at = None
                result.save(update_fields=["is_published", "published_at"])

    def delete_pretest_data(self):
        pretest_students = StudentProfile.objects.filter(matricule__startswith=PREFIX)
        pretest_users = CustomUser.objects.filter(username__startswith="pretest.")
        pretest_professors = ProfessorProfile.objects.filter(full_name__startswith=PREFIX)
        pretest_juries = Jury.objects.filter(name__startswith=PREFIX)

        counts = {
            "jurys": pretest_juries.count(),
            "étudiants": pretest_students.count(),
            "professeurs": pretest_professors.count(),
            "utilisateurs": pretest_users.count(),
            "références": StudentReference.objects.filter(matricule__startswith=PREFIX).count(),
        }

        pretest_juries.delete()
        pretest_students.delete()
        StudentReference.objects.filter(matricule__startswith=PREFIX).delete()
        ProfessorAvailability.objects.filter(professor__in=pretest_professors).delete()
        pretest_professors.delete()
        pretest_users.delete()

        self.stdout.write(self.style.SUCCESS("Données PRETEST supprimées."))
        for label, count in counts.items():
            self.stdout.write(f"  {label}: {count}")

    def print_summary(self):
        self.stdout.write(self.style.SUCCESS("\nComptes PRETEST créés ou mis à jour.\n"))
        self.stdout.write(f"Mot de passe commun : {PASSWORD}\n")
        self.stdout.write("ADMIN")
        self.stdout.write(f"  {ADMIN_EMAIL} / téléphone {ADMIN_PHONE}")
        self.stdout.write("\nPROFESSEURS")
        for _, _, email, phone, full_name in PROFESSORS:
            self.stdout.write(f"  {email} / téléphone {phone} / {full_name}")
        self.stdout.write("\nÉTUDIANTS")
        for index, (suffix, full_name, *_rest) in enumerate(STUDENTS, start=1):
            email = f"pretest.student{suffix}@iup.local"
            phone = f"910001{index:02d}"
            matricule = f"{PREFIX}{suffix}"
            self.stdout.write(f"  {email} / téléphone {phone} / matricule {matricule} / {full_name}")
        self.stdout.write("\nScénarios couverts :")
        self.stdout.write("  PRETEST001 : étudiant avec référence officielle, sans demande.")
        self.stdout.write("  PRETEST002 : demande en attente de validation encadrant.")
        self.stdout.write("  PRETEST003 : demande en attente de validation département.")
        self.stdout.write("  PRETEST004 : demande acceptée, sans jury.")
        self.stdout.write("  PRETEST005 : jury publié et planning visible.")
        self.stdout.write("  PRETEST006 : soutenance démarrée, évaluations à saisir.")
        self.stdout.write("  PRETEST007 : évaluations envoyées, résultat à publier.")
        self.stdout.write("  PRETEST008 : résultat publié visible côté étudiant.")
        self.stdout.write("  PRETEST009 : demande refusée par l'encadrant.")
        self.stdout.write("  PRETEST010 : demande refusée par le département.")
        self.stdout.write("\nSuppression après test : python manage.py create_prelaunch_test_accounts --delete")
