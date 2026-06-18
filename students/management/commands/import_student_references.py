import csv
import os

from django.core.management.base import BaseCommand, CommandError

from professors.models import ProfessorProfile
from soutenances.models import PFERequest
from students.models import StudentProfile, StudentReference


COLUMN_ALIASES = {
    "matricule": "matricule",
    "full_name": "full_name",
    "nom complet": "full_name",
    "filiere": "filiere",
    "filière": "filiere",
    "encadrant_name": "encadrant_name",
    "encadrant": "encadrant_name",
}

HEADER_KEYWORDS = {"matricule", "nom complet", "filiere", "filière", "encadrant"}


class Command(BaseCommand):
    help = (
        "Importe la liste officielle des etudiants (matricule, full_name, filiere, "
        "encadrant_name) depuis un fichier CSV ou XLSX vers StudentReference. "
        "Pour les fichiers XLSX, la ligne d'en-tete est detectee automatiquement "
        "(des lignes de titre peuvent precede l'en-tete). "
        "Colonnes acceptees (insensibles a la casse) : "
        "matricule/Matricule, full_name/'Nom complet', filiere/Filiere/Filière, "
        "encadrant_name/Encadrant."
    )

    def add_arguments(self, parser):
        parser.add_argument("file_path", type=str)

    def handle(self, *args, **options):
        file_path = options["file_path"]
        extension = os.path.splitext(file_path)[1].lower()

        if extension == ".xlsx":
            rows = self.read_xlsx_rows(file_path)
        elif extension == ".csv":
            rows = self.read_csv_rows(file_path)
        else:
            raise CommandError(
                f"Format non supporte : '{extension}'. Utilisez un fichier .csv ou .xlsx."
            )

        # Snapshot de l'ancienne base avant toute modification, pour le
        # rapport de synchronisation (references absentes du nouveau fichier,
        # encadrants qui disparaissent de la liste officielle).
        old_matricules = set(
            StudentReference.objects.values_list("matricule", flat=True)
        )
        old_encadrant_names = set(
            name for name in StudentReference.objects.values_list(
                "encadrant_name", flat=True
            ).distinct() if name
        )

        total_rows = 0
        created = 0
        updated = 0
        ignored = 0
        errors = []
        seen_matricules = {}
        duplicate_matricules = []
        empty_name = []
        empty_filiere = []
        empty_encadrant = []
        new_encadrant_names = set()
        new_matricules = set()

        for line_number, raw_row in rows:
            total_rows += 1

            if not any((value or "").strip() for value in raw_row.values()):
                ignored += 1
                continue

            matricule = (raw_row.get("matricule") or "").strip()

            if not matricule:
                ignored += 1
                continue

            full_name = (raw_row.get("full_name") or "").strip()
            filiere = (raw_row.get("filiere") or "").strip()
            encadrant_name = (raw_row.get("encadrant_name") or "").strip()

            if matricule in seen_matricules:
                duplicate_matricules.append(matricule)
            seen_matricules[matricule] = line_number

            if not full_name:
                empty_name.append(matricule)

            if not filiere:
                empty_filiere.append(matricule)

            if not encadrant_name:
                empty_encadrant.append(matricule)
            else:
                new_encadrant_names.add(encadrant_name)

            new_matricules.add(matricule)

            try:
                _, was_created = StudentReference.objects.update_or_create(
                    matricule=matricule,
                    defaults={
                        "full_name": full_name,
                        "filiere": filiere,
                        "encadrant_name": encadrant_name,
                    },
                )
            except Exception as exc:
                errors.append(f"Ligne {line_number} (matricule={matricule}) : {exc}")
                continue

            if was_created:
                created += 1
            else:
                updated += 1

        # Professeurs : creer les ProfessorProfile manquants pour les
        # nouveaux encadrants, sans jamais supprimer de profil existant.
        existing_professor_names = {
            name.strip().lower()
            for name in ProfessorProfile.objects.values_list("full_name", flat=True)
        }

        professors_created = []
        professors_existing = 0

        for encadrant_name in sorted(new_encadrant_names):
            if encadrant_name.strip().lower() in existing_professor_names:
                professors_existing += 1
                continue

            ProfessorProfile.objects.create(full_name=encadrant_name)
            professors_created.append(encadrant_name)
            existing_professor_names.add(encadrant_name.strip().lower())

        # Synchronisation prudente : references presentes avant l'import mais
        # absentes du nouveau fichier. On ne supprime jamais automatiquement,
        # on signale seulement, en distinguant celles liees a un compte reel.
        missing_matricules = sorted(old_matricules - new_matricules)
        missing_linked = []
        missing_unlinked = []

        for matricule in missing_matricules:
            is_linked = (
                StudentProfile.objects.filter(matricule=matricule).exists()
                or PFERequest.objects.filter(student__matricule=matricule).exists()
            )

            if is_linked:
                missing_linked.append(matricule)
            else:
                missing_unlinked.append(matricule)

        missing_encadrants = sorted(old_encadrant_names - new_encadrant_names)

        total_in_db = StudentReference.objects.count()
        distinct_encadrants_in_db = StudentReference.objects.exclude(
            encadrant_name=""
        ).values_list("encadrant_name", flat=True).distinct().count()

        # ---- Rapport ----
        self.stdout.write(self.style.SUCCESS("Import terminé."))
        self.stdout.write(f"Lignes lues dans le fichier : {total_rows}")
        self.stdout.write(f"StudentReference créés : {created}")
        self.stdout.write(f"StudentReference mis à jour : {updated}")
        self.stdout.write(f"Lignes ignorées (vides ou sans matricule) : {ignored}")
        self.stdout.write(f"Erreurs : {len(errors)}")
        self.stdout.write(f"Matricules dupliqués dans le fichier : {len(duplicate_matricules)}")
        if duplicate_matricules:
            self.stdout.write("  -> " + ", ".join(duplicate_matricules))
        self.stdout.write(f"Matricules avec nom vide : {len(empty_name)}")
        if empty_name:
            self.stdout.write("  -> " + ", ".join(empty_name))
        self.stdout.write(f"Matricules avec filière vide : {len(empty_filiere)}")
        if empty_filiere:
            self.stdout.write("  -> " + ", ".join(empty_filiere))
        self.stdout.write(f"Matricules avec encadrant vide : {len(empty_encadrant)}")
        if empty_encadrant:
            self.stdout.write("  -> " + ", ".join(empty_encadrant))

        self.stdout.write("")
        self.stdout.write(f"Total StudentReference en base après import : {total_in_db}")
        self.stdout.write(f"Encadrants distincts en base : {distinct_encadrants_in_db}")
        self.stdout.write(f"ProfessorProfile créés : {len(professors_created)}")
        if professors_created:
            self.stdout.write("  -> " + ", ".join(professors_created))
        self.stdout.write(f"ProfessorProfile déjà existants (réutilisés) : {professors_existing}")

        self.stdout.write("")
        self.stdout.write(
            f"Références présentes avant l'import mais absentes du nouveau fichier : "
            f"{len(missing_matricules)}"
        )
        self.stdout.write(
            f"  -> liées à un compte/demande (NON supprimées, signalées) : {len(missing_linked)}"
        )
        if missing_linked:
            self.stdout.write("     " + ", ".join(missing_linked))
        self.stdout.write(
            f"  -> non liées, supprimables en sécurité si besoin (NON supprimées automatiquement) : "
            f"{len(missing_unlinked)}"
        )
        if missing_unlinked:
            self.stdout.write("     " + ", ".join(missing_unlinked))

        self.stdout.write(
            f"Anciens encadrants absents de la nouvelle liste : {len(missing_encadrants)}"
        )
        if missing_encadrants:
            self.stdout.write("  -> " + ", ".join(missing_encadrants))

        for error in errors:
            self.stdout.write(self.style.ERROR(error))

    def normalize_header(self, value):
        return (value or "").strip().lower()

    def read_csv_rows(self, csv_path):
        try:
            file = open(csv_path, encoding="utf-8-sig")
        except OSError as exc:
            raise CommandError(f"Impossible d'ouvrir le fichier : {exc}")

        with file:
            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise CommandError("Le fichier CSV est vide ou sans en-tête.")

            normalized_fieldnames = {
                name: COLUMN_ALIASES.get(self.normalize_header(name))
                for name in reader.fieldnames
            }

            rows = []
            for line_number, raw_row in enumerate(reader, start=2):
                row = {}
                for original_name, value in raw_row.items():
                    target_field = normalized_fieldnames.get(original_name)
                    if target_field:
                        row[target_field] = (value or "").strip()
                rows.append((line_number, row))

            return rows

    def read_xlsx_rows(self, xlsx_path):
        try:
            import openpyxl
        except ImportError as exc:
            raise CommandError(
                "La bibliotheque 'openpyxl' est requise pour lire les fichiers .xlsx. "
                f"Erreur : {exc}"
            )

        try:
            workbook = openpyxl.load_workbook(xlsx_path, data_only=True)
        except Exception as exc:
            raise CommandError(f"Impossible d'ouvrir le fichier Excel : {exc}")

        worksheet = workbook.active

        header_row_index = None
        header_map = {}

        for row_index, row in enumerate(
            worksheet.iter_rows(min_row=1, max_row=20, values_only=True), start=1
        ):
            normalized_cells = [self.normalize_header(cell) for cell in row]
            matches = sum(1 for cell in normalized_cells if cell in HEADER_KEYWORDS)

            if matches >= 3:
                header_row_index = row_index
                for column_index, cell in enumerate(row):
                    target_field = COLUMN_ALIASES.get(self.normalize_header(cell))
                    if target_field:
                        header_map[column_index] = target_field
                break

        if header_row_index is None:
            raise CommandError(
                "Impossible de detecter la ligne d'en-tete (Matricule, Nom complet, "
                "Filiere, Encadrant) dans les 20 premieres lignes du fichier."
            )

        rows = []

        for row_index, row in enumerate(
            worksheet.iter_rows(min_row=header_row_index + 1, values_only=True),
            start=header_row_index + 1,
        ):
            parsed = {}
            for column_index, value in enumerate(row):
                target_field = header_map.get(column_index)
                if target_field:
                    parsed[target_field] = str(value).strip() if value is not None else ""
            rows.append((row_index, parsed))

        return rows
