"""
Commande idempotente : crée le jeu de données DEMOENC pour la démonstration devant l'encadrant.

Usage :
    python manage.py create_supervisor_demo_data

Ce que cette commande fait :
  - 6 professeurs DEMOENC (A à F)
  - 12 étudiants DEMOENC avec StudentReference
  - 12 PFERequest au statut ACCEPTED (prêtes pour la génération des jurys)
  - Disponibilités aujourd'hui : 16h30-17h30 / 17h30-18h30 / 18h00-19h00

Ce que cette commande ne fait PAS :
  - Ne génère pas de jury
  - Ne publie rien
  - Ne touche pas aux données officielles réelles
"""

from datetime import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from professors.models import ProfessorAvailability, ProfessorProfile
from soutenances.models import PFERequest
from students.models import StudentProfile, StudentReference


PREFIX   = "DEMOENC"
PASSWORD = "Demo@2026"

DEMO_PROFESSORS = [
    {"letter": "A", "username": "demoenc.prof.a", "email": "demoenc.prof.a@iup.local"},
    {"letter": "B", "username": "demoenc.prof.b", "email": "demoenc.prof.b@iup.local"},
    {"letter": "C", "username": "demoenc.prof.c", "email": "demoenc.prof.c@iup.local"},
    {"letter": "D", "username": "demoenc.prof.d", "email": "demoenc.prof.d@iup.local"},
    {"letter": "E", "username": "demoenc.prof.e", "email": "demoenc.prof.e@iup.local"},
    {"letter": "F", "username": "demoenc.prof.f", "email": "demoenc.prof.f@iup.local"},
]

# Répartition : lettre encadrant -> nombre d'étudiants
STUDENTS_PER_ADVISOR = [
    ("A", 4),
    ("B", 3),
    ("C", 2),
    ("D", 1),
    ("E", 1),
    ("F", 1),
]

# Disponibilités aujourd'hui
# (start, end, [lettres professeurs])
AVAILABILITIES = [
    (time(16, 30), time(17, 30), list("ABCDEF")),  # Créneau 1 — 16h30 tous les profs
    (time(17, 30), time(18, 30), list("ACDE")),    # Créneau 2 — 17h30
    (time(18,  0), time(19,  0), list("BCEF")),    # Créneau 3 — 18h00
]


class Command(BaseCommand):
    help = (
        "Crée (idempotent) le jeu de données DEMOENC pour la démonstration. "
        "Les demandes sont directement au statut accepted. "
        "Ne génère pas de jury — faire la génération manuellement depuis l'interface admin."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        today = timezone.localdate()
        now   = timezone.now()

        self.stdout.write(self.style.MIGRATE_HEADING(
            "\n=== create_supervisor_demo_data ==="
        ))

        # ── 1. Professeurs ──────────────────────────────────────────────────
        prof_profiles = {}
        created_profs = 0

        for data in DEMO_PROFESSORS:
            full_name = f"DEMOENC Prof {data['letter']}"

            user, user_created = CustomUser.objects.get_or_create(
                username=data["username"],
                defaults={
                    "email":     data["email"],
                    "role":      CustomUser.ROLE_PROFESSOR,
                    "is_active": True,
                },
            )
            user.set_password(PASSWORD)
            user.email     = data["email"]
            user.role      = CustomUser.ROLE_PROFESSOR
            user.is_active = True
            user.save()
            if user_created:
                created_profs += 1

            profile, _ = ProfessorProfile.objects.get_or_create(
                user=user,
                defaults={"full_name": full_name},
            )
            profile.full_name = full_name
            profile.save()
            prof_profiles[data["letter"]] = profile

        self.stdout.write(
            f"  Professeurs    : {len(prof_profiles)} synchronisés ({created_profs} nouveaux)"
        )

        # ── 2. Étudiants + PFERequest accepted ─────────────────────────────
        created_students = 0
        accepted_requests = 0
        student_num = 0

        for letter, count in STUDENTS_PER_ADVISOR:
            advisor = prof_profiles[letter]

            for _ in range(count):
                student_num += 1
                num_str   = f"{student_num:02d}"
                username  = f"demoenc.student{num_str}"
                email     = f"demoenc.student{num_str}@iup.local"
                matricule = f"DEMOENC{num_str.zfill(3)}"
                full_name = f"DEMOENC Etudiant {num_str} (Enc {letter})"

                # StudentReference
                StudentReference.objects.update_or_create(
                    matricule=matricule,
                    defaults={
                        "full_name":      full_name,
                        "filiere":        "FINTECH",
                        "encadrant_name": advisor.full_name,
                    },
                )

                # Compte utilisateur
                user, user_created = CustomUser.objects.get_or_create(
                    username=username,
                    defaults={
                        "email":     email,
                        "role":      CustomUser.ROLE_STUDENT,
                        "is_active": True,
                    },
                )
                user.set_password(PASSWORD)
                user.email     = email
                user.role      = CustomUser.ROLE_STUDENT
                user.is_active = True
                user.save()
                if user_created:
                    created_students += 1

                # Profil étudiant
                profile, _ = StudentProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "matricule": matricule,
                        "full_name": full_name,
                        "filiere":   "FINTECH",
                        "encadrant": advisor,
                    },
                )
                profile.matricule = matricule
                profile.full_name = full_name
                profile.filiere   = "FINTECH"
                profile.encadrant = advisor
                profile.save()

                # PFERequest — créer ou mettre à jour au statut accepted
                req, req_created = PFERequest.objects.get_or_create(
                    student=profile,
                    defaults={"status": PFERequest.STATUS_ACCEPTED},
                )
                if not req_created and req.status != PFERequest.STATUS_ACCEPTED:
                    req.status = PFERequest.STATUS_ACCEPTED

                # Simuler la validation encadrant + admin
                req.professor_reviewed_at = req.professor_reviewed_at or now
                req.admin_reviewed_at     = req.admin_reviewed_at     or now
                req.reviewed_at           = req.reviewed_at           or now
                req.save()
                accepted_requests += 1

        self.stdout.write(
            f"  Étudiants      : {student_num} synchronisés ({created_students} nouveaux)"
        )
        self.stdout.write(
            f"  PFERequest     : {accepted_requests} au statut 'accepted'"
        )

        # ── 3. Disponibilités aujourd'hui ───────────────────────────────────
        avail_created = 0
        avail_total   = 0

        for start, end, letters in AVAILABILITIES:
            for letter in letters:
                _, created = ProfessorAvailability.objects.get_or_create(
                    professor=prof_profiles[letter],
                    date=today,
                    start_time=start,
                    end_time=end,
                )
                if created:
                    avail_created += 1
                avail_total += 1

        self.stdout.write(
            f"  Disponibilités : {avail_total} configurées ({avail_created} nouvelles)"
        )

        # ── 4. Vérifications de non-contamination ───────────────────────────
        real_profs    = ProfessorProfile.objects.exclude(
            full_name__startswith="DEMOENC"
        ).exclude(
            full_name__startswith="TESTSTRESS"
        ).count()
        real_refs     = StudentReference.objects.exclude(
            matricule__startswith="DEMOENC"
        ).exclude(
            matricule__startswith="TESTSTRESS"
        ).count()
        stress_users  = CustomUser.objects.filter(
            username__startswith="teststress."
        ).count()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Données DEMOENC prêtes ==="))
        self.stdout.write("-" * 60)
        self.stdout.write("COMPTES PROFESSEURS  (mot de passe : Demo@2026)")
        for data in DEMO_PROFESSORS:
            self.stdout.write(f"  {data['email']}")

        self.stdout.write("")
        self.stdout.write("COMPTES ETUDIANTS  (mot de passe : Demo@2026)")
        for i in range(1, student_num + 1):
            self.stdout.write(f"  demoenc.student{i:02d}@iup.local")

        self.stdout.write("")
        self.stdout.write("DISPONIBILITES AUJOURD'HUI")
        self.stdout.write(f"  {today}  16h30-17h30  -> Prof A B C D E F  (tous)")
        self.stdout.write(f"  {today}  17h30-18h30  -> Prof A C D E")
        self.stdout.write(f"  {today}  18h00-19h00  -> Prof B C E F")

        self.stdout.write("")
        self.stdout.write("RÉPARTITION ÉTUDIANTS / ENCADRANT")
        for letter, count in STUDENTS_PER_ADVISOR:
            self.stdout.write(f"  Prof {letter} : {count} étudiant(s)")

        self.stdout.write("")
        self.stdout.write("INTÉGRITÉ DES DONNÉES OFFICIELLES")
        self.stdout.write(f"  ProfessorProfile officiels (hors DEMO/STRESS) : {real_profs}")
        self.stdout.write(f"  StudentReference officielles (hors DEMO/STRESS) : {real_refs}")
        if stress_users > 0:
            self.stdout.write(
                self.style.WARNING(f"  ATTENTION : {stress_users} compte(s) TESTSTRESS encore présents !")
            )
        else:
            self.stdout.write(self.style.SUCCESS("  0 compte TESTSTRESS restant — OK"))

        self.stdout.write("")
        self.stdout.write("ÉTAPES POUR LA DÉMONSTRATION")
        self.stdout.write("  1. Admin -> Générer automatiquement les jurys")
        self.stdout.write("  2. Admin -> Vérifier/ajuster les jurys générés")
        self.stdout.write("  3. Admin -> Publier les jurys")
        self.stdout.write("  4. Connexion compte professeur président -> attendre l'alerte 16h30")
        self.stdout.write("  5. Cliquer 'Démarrer la soutenance'")
        self.stdout.write("  6. Chaque professeur du jury -> saisir les notes")
        self.stdout.write("  7. Admin -> Résultats -> Publier")
        self.stdout.write("-" * 60)
        self.stdout.write("")
        self.stdout.write("Pour nettoyer : python manage.py delete_supervisor_demo_data")
        self.stdout.write("")
