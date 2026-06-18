from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from professors.models import ProfessorAvailability, ProfessorProfile
from soutenances.models import PFERequest
from students.models import StudentProfile, StudentReference


DEMO_PASSWORD = "Demo@2026"

DEMO_PROFESSORS = [
    {"username": "prof1.demo", "email": "prof1.demo@iup.local", "full_name": "Professeur Démo Un", "phone": "90000101"},
    {"username": "prof2.demo", "email": "prof2.demo@iup.local", "full_name": "Professeur Démo Deux", "phone": "90000102"},
    {"username": "prof3.demo", "email": "prof3.demo@iup.local", "full_name": "Professeur Démo Trois", "phone": "90000103"},
]

DEMO_STUDENTS = [
    {
        "username": "etudiant1.demo",
        "email": "etudiant1.demo@iup.local",
        "matricule": "DEMO0001",
        "full_name": "Étudiant Démo Un",
        "filiere": StudentProfile.FILIERE_DS,
        "phone": "90000201",
    },
    {
        "username": "etudiant2.demo",
        "email": "etudiant2.demo@iup.local",
        "matricule": "DEMO0002",
        "full_name": "Étudiant Démo Deux",
        "filiere": StudentProfile.FILIERE_FINTECH,
        "phone": "90000202",
    },
    {
        "username": "etudiant3.demo",
        "email": "etudiant3.demo@iup.local",
        "matricule": "DEMO0003",
        "full_name": "Étudiant Démo Trois",
        "filiere": StudentProfile.FILIERE_MAN,
        "phone": "90000203",
    },
]


class Command(BaseCommand):
    help = (
        "Crée (ou met à jour, de façon idempotente) un jeu de données de démo "
        "pour tester le workflow complet : admin, 3 professeurs, 3 étudiants, "
        "demandes PFE acceptées, disponibilités futures. "
        "Ne génère PAS de jury et ne publie PAS de résultat."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        admin_user = self.create_or_update_user(
            username="admin.demo",
            email="admin.demo@iup.local",
            phone="90000001",
            role=CustomUser.ROLE_ADMIN,
        )
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.save(update_fields=["is_staff", "is_superuser"])

        professor_profiles = []
        for data in DEMO_PROFESSORS:
            user = self.create_or_update_user(
                username=data["username"],
                email=data["email"],
                phone=data["phone"],
                role=CustomUser.ROLE_PROFESSOR,
            )

            profile, _ = ProfessorProfile.objects.get_or_create(
                user=user,
                defaults={"full_name": data["full_name"], "phone": data["phone"]},
            )
            profile.full_name = data["full_name"]
            profile.phone = data["phone"]
            profile.save()
            professor_profiles.append(profile)

        encadrant = professor_profiles[0]

        student_profiles = []
        for data in DEMO_STUDENTS:
            StudentReference.objects.update_or_create(
                matricule=data["matricule"],
                defaults={
                    "full_name": data["full_name"],
                    "filiere": data["filiere"],
                    "encadrant_name": encadrant.full_name,
                },
            )

            user = self.create_or_update_user(
                username=data["username"],
                email=data["email"],
                phone=data["phone"],
                role=CustomUser.ROLE_STUDENT,
            )

            profile, _ = StudentProfile.objects.get_or_create(
                user=user,
                defaults={
                    "matricule": data["matricule"],
                    "full_name": data["full_name"],
                    "filiere": data["filiere"],
                    "encadrant": encadrant,
                },
            )
            profile.matricule = data["matricule"]
            profile.full_name = data["full_name"]
            profile.filiere = data["filiere"]
            profile.encadrant = encadrant
            profile.save()
            student_profiles.append(profile)

            pfe_request, _ = PFERequest.objects.get_or_create(student=profile)
            pfe_request.status = PFERequest.STATUS_ACCEPTED
            pfe_request.save()

        tomorrow = timezone.localdate() + timedelta(days=1)
        day_after = timezone.localdate() + timedelta(days=2)

        for professor in professor_profiles:
            for defense_date in (tomorrow, day_after):
                ProfessorAvailability.objects.get_or_create(
                    professor=professor,
                    date=defense_date,
                    start_time=time(9, 0),
                    end_time=time(12, 0),
                )
                ProfessorAvailability.objects.get_or_create(
                    professor=professor,
                    date=defense_date,
                    start_time=time(16, 0),
                    end_time=time(19, 0),
                )

        self.print_summary(admin_user, professor_profiles, student_profiles)

    def create_or_update_user(self, username, email, phone, role):
        user = CustomUser.objects.filter(username=username).first()

        if not user:
            user = CustomUser(username=username)

        user.email = email
        user.phone_number = phone
        user.role = role
        user.set_password(DEMO_PASSWORD)
        user.is_active = True
        user.save()

        return user

    def print_summary(self, admin_user, professor_profiles, student_profiles):
        self.stdout.write(self.style.SUCCESS("\nDonnées de démo prêtes.\n"))

        self.stdout.write("Identifiants (mot de passe commun : Demo@2026) :")
        self.stdout.write(f"  Admin       : {admin_user.email} / username={admin_user.username}")

        for professor in professor_profiles:
            self.stdout.write(
                f"  Professeur  : {professor.user.email} / username={professor.user.username} "
                f"({professor.full_name})"
            )

        for student in student_profiles:
            self.stdout.write(
                f"  Étudiant    : {student.user.email} / username={student.user.username} "
                f"({student.full_name}, matricule={student.matricule})"
            )

        self.stdout.write("\nÉtapes manuelles de test, dans l'ordre :")
        steps = [
            "Se connecter en admin (admin.demo@iup.local / Demo@2026).",
            "Aller dans Jurys > Générer automatiquement.",
            "Ouvrir le jury créé et cliquer sur Publier.",
            "Se déconnecter, se connecter avec le professeur président désigné pour ce jury "
            "(voir le détail du jury côté admin pour savoir lequel).",
            "Dans Mes jurys, cliquer sur Démarrer la soutenance pour l'étudiant concerné.",
            "Chaque professeur du jury se connecte et saisit son évaluation, puis l'envoie.",
            "Se connecter en admin, aller dans Résultats, publier le résultat de l'étudiant.",
            "Se connecter avec l'étudiant concerné (etudiant1.demo@iup.local / Demo@2026) "
            "et vérifier l'affichage du jury, du planning et du résultat publié.",
        ]
        for index, step in enumerate(steps, start=1):
            self.stdout.write(f"  {index}. {step}")

        self.stdout.write(
            "\nCette commande est relançable sans créer de doublons (get_or_create / update_or_create)."
        )
