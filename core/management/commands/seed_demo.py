from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from documents.models import DocumentTemplate
from professors.models import ProfessorAvailability, ProfessorProfile
from soutenances.models import (
    Deadline,
    DefenseSchedule,
    Evaluation,
    Jury,
    JuryMember,
    JuryStudent,
    PFERequest,
    Result,
)
from students.models import StudentProfile


DEMO_PASSWORD = "demo12345"
PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
    b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] "
    b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj\n"
    b"4 0 obj << /Length 0 >> stream\n"
    b"endstream endobj\n"
    b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
    b"trailer << /Root 1 0 R >>\n%%EOF\n"
)


class Command(BaseCommand):
    help = "Create demonstrable PFE soutenance data without deleting existing data."

    @transaction.atomic
    def handle(self, *args, **options):
        admin = self.ensure_user(
            username="admin",
            role=CustomUser.ROLE_ADMIN,
            full_name="Administrateur IUP",
            phone_number="99000000",
            is_staff=True,
            is_superuser=True,
        )

        professors = self.seed_professors()
        students = self.seed_students(professors)
        self.seed_documents()
        self.seed_deadline()
        self.seed_requests(students, admin)
        juries = self.seed_juries(professors)
        assignments = self.seed_assignments(students, juries)
        self.seed_availability(professors)
        self.seed_planning(assignments)
        self.seed_evaluations(assignments)

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write(
            "Password demo12345. Logins: admin phone 99000000, "
            "professors 22000001..22000005, students 22100001.."
        )

    def ensure_user(
        self,
        username,
        role,
        full_name,
        phone_number=None,
        is_staff=False,
        is_superuser=False,
    ):
        user, created = CustomUser.objects.get_or_create(
            username=username,
            defaults={
                "role": role,
                "phone_number": phone_number,
                "is_staff": is_staff,
                "is_superuser": is_superuser,
                "is_active": True,
            },
        )
        parts = full_name.split(" ", 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ""
        user.role = role
        user.is_active = True
        if phone_number and not CustomUser.objects.exclude(pk=user.pk).filter(
            phone_number=phone_number
        ).exists():
            user.phone_number = phone_number
        if is_staff:
            user.is_staff = True
        if is_superuser:
            user.is_superuser = True
        if created:
            user.set_password(DEMO_PASSWORD)
        user.save()
        return user

    def seed_professors(self):
        names = [
            "Aminata Ba",
            "Moussa Diop",
            "Salem Ahmed",
            "Fatimata Sow",
            "Mohamed Vall",
        ]
        professors = []
        for index, name in enumerate(names, start=1):
            phone = f"2200000{index}"
            user = self.ensure_user(
                username=f"prof{index}",
                role=CustomUser.ROLE_PROFESSOR,
                full_name=name,
                phone_number=phone,
            )
            professor, _ = ProfessorProfile.objects.get_or_create(
                full_name=name,
                defaults={"user": user, "phone": phone},
            )
            professor.user = user
            professor.phone = phone
            professor.save()
            professors.append(professor)
        return professors

    def seed_students(self, professors):
        data = [
            ("IUP26001", "Khadija Mohamed", "DS", professors[0]),
            ("IUP26002", "Abdoulaye Sarr", "FINTECH", professors[1]),
            ("IUP26003", "Mariem Ahmed", "LGTR", professors[2]),
            ("IUP26004", "Cheikh Ndiaye", "RXTL", professors[3]),
            ("IUP26005", "Rama Kane", "MAEF", professors[4]),
            ("IUP26006", "Ibrahima Diallo", "MAN", professors[0]),
        ]
        students = []
        for index, (matricule, full_name, filiere, encadrant) in enumerate(data, start=1):
            user = self.ensure_user(
                username=matricule.lower(),
                role=CustomUser.ROLE_STUDENT,
                full_name=full_name,
                phone_number=f"2210000{index}",
            )
            student, _ = StudentProfile.objects.get_or_create(
                matricule=matricule,
                defaults={
                    "user": user,
                    "full_name": full_name,
                    "filiere": filiere,
                    "encadrant": encadrant,
                },
            )
            student.user = user
            student.full_name = full_name
            student.filiere = filiere
            student.encadrant = encadrant
            student.save()
            students.append(student)
        return students

    def seed_documents(self):
        downloads = Path.home() / "Downloads"
        documents = [
            (
                "Autorisation de soutenance unifiee",
                DocumentTemplate.TYPE_STUDENT_REQUEST,
                "Formulaire d'autorisation a remplir avant depot.",
                downloads / "Autorisation soutenance_unifiee.pdf",
                downloads / "Autorisation soutenance_unifiee.pdf",
            ),
            (
                "Fiche d'evaluation de soutenance",
                DocumentTemplate.TYPE_EVALUATION,
                "Document officiel base sur 3 criteres.",
                downloads / "fiche_evaluation_soutenance.pdf",
                downloads / "fiche_evaluation_soutenance.docx",
            ),
        ]
        for title, template_type, description, *candidates in documents:
            if DocumentTemplate.objects.filter(title=title).exists():
                continue
            document = DocumentTemplate(
                title=title,
                template_type=template_type,
                description=description,
                is_active=True,
            )
            source = next((path for path in candidates if path.exists()), None)
            if source:
                with source.open("rb") as handle:
                    document.file.save(source.name, File(handle), save=True)
            else:
                document.file.save(
                    f"{title.lower().replace(' ', '-')}.pdf",
                    ContentFile(PDF_BYTES),
                    save=True,
                )

    def seed_deadline(self):
        if not Deadline.objects.filter(is_active=True).exists():
            Deadline.objects.create(
                title="Date limite des demandes",
                deadline_date=timezone.now() + timedelta(days=30),
                is_active=True,
            )

    def seed_requests(self, students, admin):
        for student in students[:5]:
            request, created = PFERequest.objects.get_or_create(
                student=student,
                defaults={
                    "status": PFERequest.STATUS_ACCEPTED,
                    "reviewed_by_professor": student.encadrant,
                    "professor_reviewed_at": timezone.now(),
                    "reviewed_by_admin": admin,
                    "admin_reviewed_at": timezone.now(),
                    "reviewed_by": admin,
                    "reviewed_at": timezone.now(),
                },
            )
            if created or not request.rapport_stage:
                request.rapport_stage.save(
                    f"rapport_{student.matricule}.pdf",
                    ContentFile(PDF_BYTES),
                    save=False,
                )
            if created or not request.authorization_document:
                request.authorization_document.save(
                    f"autorisation_{student.matricule}.pdf",
                    ContentFile(PDF_BYTES),
                    save=False,
                )
            request.status = PFERequest.STATUS_ACCEPTED
            request.reviewed_by_professor = student.encadrant
            request.professor_reviewed_at = request.professor_reviewed_at or timezone.now()
            request.reviewed_by_admin = admin
            request.admin_reviewed_at = request.admin_reviewed_at or timezone.now()
            request.reviewed_by = admin
            request.reviewed_at = request.reviewed_at or request.admin_reviewed_at
            request.save()

    def seed_juries(self, professors):
        defense_date = date.today() + timedelta(days=10)
        configs = [
            ("Jury A - Data et Fintech", [professors[0], professors[1], professors[2]]),
            ("Jury B - Reseaux et Gestion", [professors[2], professors[3], professors[4]]),
        ]
        juries = []
        for name, members in configs:
            jury, _ = Jury.objects.get_or_create(
                name=name,
                defaults={"defense_date": defense_date},
            )
            jury.defense_date = defense_date
            jury.save(update_fields=["defense_date"])
            for professor in members:
                JuryMember.objects.get_or_create(jury=jury, professor=professor)
            juries.append(jury)
        return juries

    def seed_assignments(self, students, juries):
        mapping = [
            (students[0], juries[0]),
            (students[1], juries[0]),
            (students[2], juries[0]),
            (students[3], juries[1]),
            (students[4], juries[1]),
        ]
        assignments = []
        for student, jury in mapping:
            assignment, _ = JuryStudent.objects.get_or_create(
                student=student,
                defaults={"jury": jury},
            )
            assignments.append(assignment)
        return assignments

    def seed_availability(self, professors):
        defense_date = date.today() + timedelta(days=10)
        for professor in professors:
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

    def seed_planning(self, assignments):
        slots = [time(9, 0), time(9, 15), time(9, 30), time(9, 45), time(10, 0)]
        for assignment, slot in zip(assignments, slots):
            DefenseSchedule.objects.get_or_create(
                jury_student=assignment,
                defaults={"start_time": slot},
            )

    def seed_evaluations(self, assignments):
        if not assignments:
            return
        assignment = assignments[0]
        values = [
            (Decimal("16.00"), Decimal("16.00"), Decimal("16.00")),
            (Decimal("12.50"), Decimal("12.50"), Decimal("12.50")),
            (Decimal("15.00"), Decimal("15.00"), Decimal("15.00")),
        ]
        for member, notes in zip(assignment.jury.members.select_related("professor"), values):
            evaluation, created = Evaluation.objects.get_or_create(
                jury_student=assignment,
                professor=member.professor,
                defaults={
                    "rapport_note": notes[0],
                    "presentation_note": notes[1],
                    "questions_note": notes[2],
                },
            )
            if created:
                evaluation.submit()
        result, _ = Result.objects.get_or_create(jury_student=assignment)
        if result.average is None:
            result.calculate_average()
