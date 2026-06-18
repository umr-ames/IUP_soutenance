"""
Commande idempotente : crée le jeu de données TESTSTRESS pour la démonstration.

Usage :
    python manage.py create_jury_stress_test_data

Ce que cette commande fait :
  - 8 professeurs TESTSTRESS (A à H)
  - 19 étudiants TESTSTRESS avec StudentReference
  - 19 PFERequest au statut pending_professor (à valider manuellement)
  - Disponibilités croisées sur 5 créneaux (demain / après-demain / j+3)

Ce que cette commande ne fait PAS :
  - Ne génère pas de jury
  - Ne valide pas les demandes
  - Ne publie pas de résultats
  - Ne touche pas aux données réelles
"""

from datetime import time, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from professors.models import ProfessorAvailability, ProfessorProfile
from soutenances.models import PFERequest
from students.models import StudentProfile, StudentReference


PREFIX = "TESTSTRESS"
STRESS_PASSWORD = "Test@2026"

# 8 professors A..H
STRESS_PROFESSORS = [
    {"letter": "A", "username": "teststress.prof.a", "email": "teststress.prof.a@iup.local"},
    {"letter": "B", "username": "teststress.prof.b", "email": "teststress.prof.b@iup.local"},
    {"letter": "C", "username": "teststress.prof.c", "email": "teststress.prof.c@iup.local"},
    {"letter": "D", "username": "teststress.prof.d", "email": "teststress.prof.d@iup.local"},
    {"letter": "E", "username": "teststress.prof.e", "email": "teststress.prof.e@iup.local"},
    {"letter": "F", "username": "teststress.prof.f", "email": "teststress.prof.f@iup.local"},
    {"letter": "G", "username": "teststress.prof.g", "email": "teststress.prof.g@iup.local"},
    {"letter": "H", "username": "teststress.prof.h", "email": "teststress.prof.h@iup.local"},
]

# Répartition étudiants par encadrant (lettre → nombre)
STUDENTS_PER_ADVISOR = [
    ("A", 5),
    ("B", 4),
    ("C", 3),
    ("D", 2),
    ("E", 2),
    ("F", 1),
    ("G", 1),
    ("H", 1),
]

# Disponibilités par créneau :
# Chaque entrée = (offset_jours, start, end, [lettres profs])
# Créneau 1 : demain 09-11h  → A B C D E F  (2 jurys simultanés possibles)
# Créneau 2 : demain 14-16h  → A D G
# Créneau 3 : après-demain 09-12h → B E H
# Créneau 4 : après-demain 14-17h → A C D
# Créneau 5 : j+3 09-11h → B F G
AVAILABILITIES = [
    (1, time(9, 0),  time(11, 0), list("ABCDEF")),
    (1, time(14, 0), time(16, 0), list("ADG")),
    (2, time(9, 0),  time(12, 0), list("BEH")),
    (2, time(14, 0), time(17, 0), list("ACD")),
    (3, time(9, 0),  time(11, 0), list("BFG")),
]


class Command(BaseCommand):
    help = (
        "Crée (idempotent) le jeu de données TESTSTRESS pour la démonstration "
        "de la génération de jurys. Ne valide pas les demandes, ne génère pas de jury."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()

        # ── 1. Professeurs ──────────────────────────────────────────────────
        prof_profiles = {}
        created_profs = 0

        for data in STRESS_PROFESSORS:
            full_name = f"TESTSTRESS Prof {data['letter']}"
            user, user_created = CustomUser.objects.get_or_create(
                username=data["username"],
                defaults={
                    "email": data["email"],
                    "role": CustomUser.ROLE_PROFESSOR,
                    "is_active": True,
                },
            )
            if user_created:
                user.set_password(STRESS_PASSWORD)
                user.save()
                created_profs += 1
            else:
                # Toujours synchroniser le mot de passe (idempotent)
                user.set_password(STRESS_PASSWORD)
                user.email = data["email"]
                user.role = CustomUser.ROLE_PROFESSOR
                user.is_active = True
                user.save()

            profile, _ = ProfessorProfile.objects.get_or_create(
                user=user,
                defaults={"full_name": full_name},
            )
            profile.full_name = full_name
            profile.save()
            prof_profiles[data["letter"]] = profile

        self.stdout.write(f"  Professeurs : {len(prof_profiles)} synchronisés ({created_profs} nouveaux)")

        # ── 2. Étudiants ────────────────────────────────────────────────────
        created_students = 0
        student_num = 0
        all_student_profiles = []

        for letter, count in STUDENTS_PER_ADVISOR:
            advisor = prof_profiles[letter]

            for _ in range(count):
                student_num += 1
                num_str = f"{student_num:02d}"
                username   = f"teststress.student{num_str}"
                email      = f"teststress.student{num_str}@iup.local"
                matricule  = f"TESTSTRESS{num_str.zfill(3)}"
                full_name  = f"TESTSTRESS Étudiant {num_str} (Enc {letter})"

                # StudentReference pour l'auto-fill à l'inscription
                StudentReference.objects.update_or_create(
                    matricule=matricule,
                    defaults={
                        "full_name": full_name,
                        "filiere": "FINTECH",
                        "encadrant_name": advisor.full_name,
                    },
                )

                user, user_created = CustomUser.objects.get_or_create(
                    username=username,
                    defaults={
                        "email": email,
                        "role": CustomUser.ROLE_STUDENT,
                        "is_active": True,
                    },
                )
                if user_created:
                    user.set_password(STRESS_PASSWORD)
                    user.save()
                    created_students += 1
                else:
                    user.set_password(STRESS_PASSWORD)
                    user.email = email
                    user.role = CustomUser.ROLE_STUDENT
                    user.is_active = True
                    user.save()

                profile, _ = StudentProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "matricule": matricule,
                        "full_name": full_name,
                        "filiere": "FINTECH",
                        "encadrant": advisor,
                    },
                )
                profile.matricule = matricule
                profile.full_name = full_name
                profile.filiere = "FINTECH"
                profile.encadrant = advisor
                profile.save()
                all_student_profiles.append(profile)

                # PFERequest en statut pending_professor (à valider manuellement)
                PFERequest.objects.get_or_create(
                    student=profile,
                    defaults={"status": PFERequest.STATUS_PENDING_PROFESSOR},
                )

        self.stdout.write(f"  Étudiants   : {student_num} synchronisés ({created_students} nouveaux)")

        # ── 3. Disponibilités ───────────────────────────────────────────────
        avail_created = 0
        for day_offset, start, end, letters in AVAILABILITIES:
            defense_date = today + timedelta(days=day_offset)
            for letter in letters:
                _, created = ProfessorAvailability.objects.get_or_create(
                    professor=prof_profiles[letter],
                    date=defense_date,
                    start_time=start,
                    end_time=end,
                )
                if created:
                    avail_created += 1

        self.stdout.write(f"  Disponibilités : {avail_created} nouvelles créées")

        # ── 4. Résumé ───────────────────────────────────────────────────────
        tomorrow     = today + timedelta(days=1)
        day_after    = today + timedelta(days=2)
        day_plus_3   = today + timedelta(days=3)

        self.stdout.write(self.style.SUCCESS("\nDonnées TESTSTRESS prêtes.\n"))
        self.stdout.write("-" * 60)
        self.stdout.write("COMPTES PROFESSEURS")
        for data in STRESS_PROFESSORS:
            self.stdout.write(f"  {data['email']}  /  {STRESS_PASSWORD}")

        self.stdout.write("")
        self.stdout.write("COMPTES ÉTUDIANTS  (mot de passe : Test@2026)")
        for i in range(1, student_num + 1):
            self.stdout.write(f"  teststress.student{i:02d}@iup.local")

        self.stdout.write("")
        self.stdout.write("DISPONIBILITÉS")
        self.stdout.write(f"  Créneau 1 -- {tomorrow}  09h-11h  -- A B C D E F  (2 jurys simultanés possibles)")
        self.stdout.write(f"  Créneau 2 -- {tomorrow}  14h-16h  -- A D G")
        self.stdout.write(f"  Créneau 3 -- {day_after}  09h-12h  -- B E H")
        self.stdout.write(f"  Créneau 4 -- {day_after}  14h-17h  -- A C D")
        self.stdout.write(f"  Créneau 5 -- {day_plus_3}  09h-11h  -- B F G")

        self.stdout.write("")
        self.stdout.write("ÉTAPES MANUELLES À EFFECTUER")
        self.stdout.write("  1. Connexion professeur -> valider chaque demande (pending_professor)")
        self.stdout.write("  2. Connexion admin -> accepter les demandes (pending_admin)")
        self.stdout.write("  3. Admin -> Générer automatiquement les jurys")
        self.stdout.write("  4. Admin -> Publier les jurys")
        self.stdout.write("  5. Connexion professeur-président -> démarrer la soutenance")
        self.stdout.write("  6. Professeurs -> saisir les notes")
        self.stdout.write("  7. Admin -> publier les résultats")
        self.stdout.write("-" * 60)
        self.stdout.write("")
        self.stdout.write("Pour nettoyer : python manage.py delete_jury_stress_test_data")
