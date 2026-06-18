from django.core.management.base import BaseCommand
from django.db import transaction

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
    Note,
    PFERequest,
    Result,
)
from students.models import StudentProfile


class Command(BaseCommand):
    help = "Safely remove development/demo data while preserving superuser admins."

    def add_arguments(self, parser):
        parser.add_argument(
            "--documents",
            action="store_true",
            help="Also delete uploaded document template records.",
        )
        parser.add_argument(
            "--deadlines",
            action="store_true",
            help="Also delete request deadline records.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        counts = {}

        for model in (
            Result,
            Evaluation,
            Note,
            DefenseSchedule,
            JuryStudent,
            JuryMember,
            Jury,
            PFERequest,
            ProfessorAvailability,
        ):
            counts[model.__name__] = model.objects.count()
            model.objects.all().delete()

        counts["StudentProfile"] = StudentProfile.objects.count()
        StudentProfile.objects.all().delete()

        counts["ProfessorProfile"] = ProfessorProfile.objects.count()
        ProfessorProfile.objects.all().delete()

        if options["documents"]:
            counts["DocumentTemplate"] = DocumentTemplate.objects.count()
            DocumentTemplate.objects.all().delete()

        if options["deadlines"]:
            counts["Deadline"] = Deadline.objects.count()
            Deadline.objects.all().delete()

        users = CustomUser.objects.filter(
            is_superuser=False,
            role__in=[CustomUser.ROLE_STUDENT, CustomUser.ROLE_PROFESSOR],
        )
        counts["CustomUser(student/professor)"] = users.count()
        users.delete()

        self.stdout.write(self.style.SUCCESS("Development data reset complete."))
        for name, count in counts.items():
            self.stdout.write(f"{name}: {count} removed")
        self.stdout.write("Superuser/admin accounts were preserved.")
