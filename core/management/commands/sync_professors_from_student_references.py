import re

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import CustomUser
from professors.models import ProfessorAvailability, ProfessorProfile
from soutenances.models import Evaluation, JuryMember
from students.models import StudentProfile, StudentReference


def normalize(name):
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


class Command(BaseCommand):
    help = (
        "Synchronise ProfessorProfile avec la liste officielle des encadrants "
        "présente dans StudentReference.encadrant_name. Supprime tout "
        "ProfessorProfile qui n'encadre aucun étudiant dans la liste officielle "
        "actuelle (et son compte utilisateur lié, ses disponibilités). "
        "Ne supprime jamais un professeur lié à un jury ou une évaluation : "
        "ces cas sont signalés et ignorés pour ne pas casser la base. "
        "Relançable sans risque : la deuxième exécution ne supprime rien."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        encadrant_names = [
            name for name in StudentReference.objects.values_list(
                "encadrant_name", flat=True
            )
            if name and name.strip()
        ]

        distinct_official = {}
        for name in encadrant_names:
            distinct_official.setdefault(normalize(name), name)

        all_professors = list(ProfessorProfile.objects.all())
        total_before = len(all_professors)

        to_keep = []
        to_remove = []

        for professor in all_professors:
            if normalize(professor.full_name) in distinct_official:
                to_keep.append(professor)
            else:
                to_remove.append(professor)

        blocked = []
        removable = []

        for professor in to_remove:
            jury_links = JuryMember.objects.filter(professor=professor).count()
            evaluation_links = Evaluation.objects.filter(professor=professor).count()
            supervised = StudentProfile.objects.filter(encadrant=professor).count()

            if jury_links or evaluation_links or supervised:
                blocked.append({
                    "professor": professor,
                    "jury_links": jury_links,
                    "evaluation_links": evaluation_links,
                    "supervised": supervised,
                })
            else:
                removable.append(professor)

        removed_names = []
        removed_user_count = 0

        for professor in removable:
            if professor.user_id:
                user = professor.user
                removed_user_count += 1
                ProfessorAvailability.objects.filter(professor=professor).delete()
                removed_names.append(professor.full_name)
                professor.delete()
                CustomUser.objects.filter(pk=user.pk).delete()
            else:
                ProfessorAvailability.objects.filter(professor=professor).delete()
                removed_names.append(professor.full_name)
                professor.delete()

        total_after = ProfessorProfile.objects.count()
        distinct_official_count = len(distinct_official)

        self.stdout.write(self.style.SUCCESS("Synchronisation terminée."))
        self.stdout.write(f"Encadrants distincts officiels (StudentReference) : {distinct_official_count}")
        self.stdout.write(f"ProfessorProfile avant : {total_before}")
        self.stdout.write(f"ProfessorProfile après : {total_after}")
        self.stdout.write(f"Conservés (encadrent réellement) : {len(to_keep)}")
        self.stdout.write(f"Supprimés : {len(removed_names)}")
        if removed_names:
            self.stdout.write("  -> " + ", ".join(removed_names))
        self.stdout.write(f"Comptes utilisateurs professeurs supprimés : {removed_user_count}")

        if blocked:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(blocked)} professeur(s) hors liste officielle mais NON supprimé(s) "
                    "car lié(s) à des données actives :"
                )
            )
            for entry in blocked:
                self.stdout.write(
                    f"  -> {entry['professor'].full_name} : "
                    f"{entry['jury_links']} jury(s), "
                    f"{entry['evaluation_links']} évaluation(s), "
                    f"{entry['supervised']} étudiant(s) encadré(s)"
                )

        if distinct_official_count != total_after:
            self.stdout.write(
                self.style.WARNING(
                    f"Anomalie : {distinct_official_count} encadrants officiels distincts mais "
                    f"{total_after} ProfessorProfile en base. Vérifiez les professeurs bloqués "
                    "ci-dessus ou un écart de nom (espaces, casse, accents) non normalisé."
                )
            )
