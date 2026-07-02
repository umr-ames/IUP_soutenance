from datetime import datetime, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from professors.models import ProfessorAvailability, ProfessorProfile
from students.models import StudentProfile


# Seuil de validation : moyenne >= 10 (mention Passable ou supérieure).
PASS_THRESHOLD = Decimal("10")


def mention_for_average(average):
    """Barème officiel des mentions de soutenance.

    < 10            : Insuffisant (non validée)
    10 <= m < 12    : Passable
    12 <= m < 14    : Assez bien
    14 <= m < 16    : Bien
    16 <= m < 18    : Très bien
    m >= 18         : Très bien avec les félicitations du jury
    """
    if average is None:
        return None

    average = Decimal(average)

    if average >= Decimal("18"):
        return "Très bien avec les félicitations du jury"
    if average >= Decimal("16"):
        return "Très bien"
    if average >= Decimal("14"):
        return "Bien"
    if average >= Decimal("12"):
        return "Assez bien"
    if average >= Decimal("10"):
        return "Passable"
    return "Insuffisant"


class FiliereExpert(models.Model):
    """Groupe de professeurs experts par filière. L'admin le gère ; la
    génération de jury privilégie la présence d'un expert (≠ encadrant) de la
    filière de l'étudiant."""
    filiere = models.CharField(
        max_length=20,
        choices=StudentProfile.FILIERE_CHOICES,
    )
    professor = models.ForeignKey(
        ProfessorProfile,
        on_delete=models.CASCADE,
        related_name="expert_filieres",
    )

    class Meta:
        unique_together = ("filiere", "professor")
        verbose_name = "Expert de filière"
        verbose_name_plural = "Experts de filière"

    def __str__(self):
        return f"{self.get_filiere_display()} — {self.professor.full_name}"


class Deadline(models.Model):
    title = models.CharField(max_length=255, default="Date limite des demandes")
    deadline_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    def is_closed(self):
        return timezone.now() > self.deadline_date

    def __str__(self):
        return f"{self.title} - {self.deadline_date}"


def rapport_upload_path(instance, filename):
    return f"rapports/{instance.student.matricule}/{filename}"


def fiche_upload_path(instance, filename):
    return f"fiches_demandes/{instance.student.matricule}/{filename}"


def evaluation_upload_path(instance, filename):
    return f"fiches_evaluation/{instance.student.matricule}/{filename}"


def authorization_upload_path(instance, filename):
    return f"autorisations/{instance.student.matricule}/{filename}"


def rapport_stage_upload_path(instance, filename):
    return f"rapports_stage/{instance.student.matricule}/{filename}"


def attestation_stage_upload_path(instance, filename):
    return f"attestations_stage/{instance.student.matricule}/{filename}"


class PFERequest(models.Model):
    STATUS_PENDING_PROFESSOR = "pending_professor"
    STATUS_REFUSED_PROFESSOR = "refused_by_professor"
    STATUS_PENDING_ADMIN = "pending_admin"
    STATUS_REFUSED_ADMIN = "refused_by_admin"
    STATUS_ACCEPTED = "accepted"

    STATUS_PENDING = STATUS_PENDING_PROFESSOR
    STATUS_REFUSED = STATUS_REFUSED_ADMIN

    STATUS_REFUSED_BY_PROFESSOR = STATUS_REFUSED_PROFESSOR
    STATUS_REFUSED_BY_ADMIN = STATUS_REFUSED_ADMIN

    STATUS_PENDING_BY_PROFESSOR = STATUS_PENDING_PROFESSOR
    STATUS_PENDING_BY_ADMIN = STATUS_PENDING_ADMIN

    STATUS_CHOICES = [
        (STATUS_PENDING_PROFESSOR, "En attente de validation encadrant"),
        (STATUS_REFUSED_PROFESSOR, "Refusée par l’encadrant"),
        (STATUS_PENDING_ADMIN, "En attente du département de l'IUP"),
        (STATUS_REFUSED_ADMIN, "Refusée par le département de l'IUP"),
        (STATUS_ACCEPTED, "Acceptée"),
    ]

    student = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="pfe_request"
    )

    authorization_document = models.FileField(
        upload_to=authorization_upload_path,
        blank=True,
        null=True
    )

    rapport_stage = models.FileField(
        upload_to=rapport_stage_upload_path,
        blank=True,
        null=True
    )

    attestation_stage = models.FileField(
        upload_to=attestation_stage_upload_path,
        blank=True,
        null=True
    )

    rapport_pfe = models.FileField(
        upload_to=rapport_upload_path,
        blank=True,
        null=True
    )

    fiche_demande = models.FileField(
        upload_to=fiche_upload_path,
        blank=True,
        null=True
    )

    fiche_evaluation = models.FileField(
        upload_to=evaluation_upload_path,
        blank=True,
        null=True
    )

    status = models.CharField(
        max_length=30,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING_PROFESSOR
    )

    submitted_at = models.DateTimeField(auto_now_add=True)

    professor_comment = models.TextField(blank=True, null=True)
    admin_comment = models.TextField(blank=True, null=True)

    # Demande de redépôt d'une pièce par le département (vue par l'étudiant
    # et son encadrant).
    REUPLOAD_CHOICES = [
        ("authorization", "Autorisation de soutenance"),
        ("attestation", "Attestation de stage"),
        ("rapport", "Rapport de stage"),
    ]
    reupload_document = models.CharField(
        max_length=20, blank=True, default="", choices=REUPLOAD_CHOICES
    )
    reupload_comment = models.TextField(blank=True, null=True)

    professor_reviewed_at = models.DateTimeField(blank=True, null=True)
    admin_reviewed_at = models.DateTimeField(blank=True, null=True)

    reviewed_by_professor = models.ForeignKey(
        ProfessorProfile,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_pfe_requests"
    )

    reviewed_by_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="admin_reviewed_pfe_requests"
    )

    reviewed_at = models.DateTimeField(blank=True, null=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_pfe_requests"
    )

    def professor_accept(self, professor):
        self.status = self.STATUS_PENDING_ADMIN
        self.reviewed_by_professor = professor
        self.professor_reviewed_at = timezone.now()
        self.save()

    def professor_refuse(self, professor, comment=None):
        self.status = self.STATUS_REFUSED_PROFESSOR
        self.reviewed_by_professor = professor
        self.professor_reviewed_at = timezone.now()
        self.professor_comment = comment
        self.save()

    def admin_accept(self, admin_user):
        self.status = self.STATUS_ACCEPTED
        self.reviewed_by_admin = admin_user
        self.admin_reviewed_at = timezone.now()
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()

    def admin_refuse(self, admin_user, comment=None):
        self.status = self.STATUS_REFUSED_ADMIN
        self.reviewed_by_admin = admin_user
        self.admin_reviewed_at = timezone.now()
        self.admin_comment = comment
        self.reviewed_by = admin_user
        self.reviewed_at = timezone.now()
        self.save()

    def accept(self, admin_user):
        self.admin_accept(admin_user)

    def refuse(self, admin_user, comment=None):
        self.admin_refuse(admin_user, comment)

    def __str__(self):
        return f"Demande PFE - {self.student.full_name} - {self.get_status_display()}"


class Jury(models.Model):
    SALLE_CHOICES = [
        ("", "Non définie"),
        ("Amphi", "Amphi"),
        ("Salle 1", "Salle 1"),
        ("Salle 2", "Salle 2"),
        ("Salle 3", "Salle 3"),
        ("Salle 7", "Salle 7"),
        ("Salle 8", "Salle 8"),
        ("Salle 10", "Salle 10"),
    ]

    name = models.CharField(max_length=255)
    defense_date = models.DateField()
    salle = models.CharField(
        max_length=20, choices=SALLE_CHOICES, blank=True, default="",
        verbose_name="Salle",
    )
    is_validated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def members_count(self):
        return self.members.count()

    def students_count(self):
        return self.students.count()

    def clean(self):
        if self.pk and self.members.count() > 3:
            raise ValidationError("Un jury ne peut pas avoir plus de 3 professeurs.")

    def __str__(self):
        return f"{self.name} - {self.defense_date}"


class JuryMember(models.Model):
    jury = models.ForeignKey(
        Jury,
        on_delete=models.CASCADE,
        related_name="members"
    )

    professor = models.ForeignKey(
        ProfessorProfile,
        on_delete=models.PROTECT,
        related_name="jury_memberships"
    )

    class Meta:
        unique_together = ("jury", "professor")

    def clean(self):
        if self.jury_id:
            count = self.jury.members.exclude(pk=self.pk).count()

            if count >= 3:
                raise ValidationError(
                    "Un jury ne peut pas contenir plus de 3 professeurs."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.jury.name} - {self.professor.full_name}"


class JuryStudent(models.Model):
    # ── Décision PFE soutenable ─────────────────────────────────────────────
    PFE_SOUTENABLE_PENDING = "pending"
    PFE_SOUTENABLE_OUI     = "soutenable"
    PFE_SOUTENABLE_NON     = "non_soutenable"

    PFE_SOUTENABLE_CHOICES = [
        (PFE_SOUTENABLE_PENDING, "Décision non prise"),
        (PFE_SOUTENABLE_OUI,     "PFE soutenable"),
        (PFE_SOUTENABLE_NON,     "PFE non soutenable"),
    ]

    jury = models.ForeignKey(
        Jury,
        on_delete=models.CASCADE,
        related_name="students"
    )

    student = models.OneToOneField(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name="jury_assignment"
    )

    president = models.ForeignKey(
        ProfessorProfile,
        on_delete=models.PROTECT,
        related_name="presided_soutenances",
        blank=True,
        null=True,
        verbose_name="Président de soutenance"
    )

    assigned_at = models.DateTimeField(auto_now_add=True)

    # Vrai lorsque l'encadrant n'a déclaré aucune disponibilité : le jury est
    # alors formé sans lui, avec obligatoirement un expert de la filière.
    encadrant_absent = models.BooleanField(default=False)

    presentation_started = models.BooleanField(default=False)
    presentation_started_at = models.DateTimeField(blank=True, null=True)
    presentation_started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="started_presentations"
    )

    pfe_soutenable_status = models.CharField(
        max_length=20,
        choices=PFE_SOUTENABLE_CHOICES,
        default=PFE_SOUTENABLE_PENDING,
        verbose_name="Décision soutenable",
    )
    pfe_soutenable_decided_at = models.DateTimeField(blank=True, null=True)
    pfe_soutenable_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="pfe_soutenable_decisions",
        verbose_name="Décidé par",
    )

    class Meta:
        unique_together = ("jury", "student")

    def clean(self):
        if not self.jury_id or not self.student_id:
            return

        jury_professors = ProfessorProfile.objects.filter(
            jury_memberships__jury=self.jury
        )

        jury_professor_ids = set(
            jury_professors.values_list("id", flat=True)
        )

        if self.student.encadrant not in jury_professors:
            # Exception : si l'encadrant n'a AUCUNE disponibilité future déclarée,
            # le jury peut être formé sans lui, à condition de contenir un expert
            # de la filière de l'étudiant.
            from django.utils import timezone
            encadrant = self.student.encadrant
            has_avail = ProfessorAvailability.objects.filter(
                professor=encadrant, date__gte=timezone.localdate()
            ).exists()
            if has_avail:
                raise ValidationError(
                    "L'encadrant de l'étudiant doit obligatoirement être membre de son jury."
                )
            expert_present = FiliereExpert.objects.filter(
                filiere=self.student.filiere,
                professor_id__in=jury_professor_ids,
            ).exists()
            if not expert_present:
                raise ValidationError(
                    "Encadrant sans disponibilité : le jury doit contenir un "
                    "expert de la filière de l'étudiant."
                )

        if self.president_id:
            if self.president_id not in jury_professor_ids:
                raise ValidationError(
                    "Le président de soutenance doit être membre du jury."
                )

            if self.student.encadrant_id == self.president_id:
                raise ValidationError(
                    "L'encadrant de l'étudiant ne peut pas être président de sa soutenance."
                )

        if not hasattr(self.student, "pfe_request"):
            raise ValidationError(
                "L'étudiant doit avoir une demande de soutenance."
            )

        if self.student.pfe_request.status != PFERequest.STATUS_ACCEPTED:
            raise ValidationError(
                "L'étudiant doit avoir une demande acceptée par le département de l'IUP."
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def start_presentation(self, started_by):
        if self.presentation_started:
            return

        now = timezone.now()

        # Transition d'état pure : démarrer la soutenance ne doit jamais être
        # bloqué par la validation de composition du jury (full_clean via
        # save()). On écrit donc directement les champs concernés, comme le
        # fait déjà la décision « soutenable ».
        type(self).objects.filter(pk=self.pk).update(
            presentation_started=True,
            presentation_started_at=now,
            presentation_started_by=started_by,
        )

        self.presentation_started = True
        self.presentation_started_at = now
        self.presentation_started_by = started_by

    @property
    def presentation_duration_minutes(self):
        schedule = getattr(self, "schedule", None)
        if schedule and schedule.duration_minutes:
            return schedule.duration_minutes
        return 20

    @property
    def presentation_end_at(self):
        """Heure de fin réelle = heure de lancement effective + durée (20 min).
        Permet d'afficher l'horaire réel, même si la soutenance a commencé en
        retard par rapport au créneau prévu."""
        if not self.presentation_started_at:
            return None
        return self.presentation_started_at + timedelta(
            minutes=self.presentation_duration_minutes
        )

    def __str__(self):
        if self.president:
            return (
                f"{self.student.full_name} - {self.jury.name} - "
                f"Président: {self.president.full_name}"
            )

        return f"{self.student.full_name} - {self.jury.name}"


class DefenseSchedule(models.Model):
    jury_student = models.OneToOneField(
        JuryStudent,
        on_delete=models.CASCADE,
        related_name="schedule"
    )

    start_time = models.TimeField()
    end_time = models.TimeField(blank=True, null=True)
    duration_minutes = models.PositiveIntegerField(default=20)

    def clean(self):
        jury = self.jury_student.jury
        date = jury.defense_date

        start_datetime = datetime.combine(date, self.start_time)

        if self.end_time:
            end_datetime = datetime.combine(date, self.end_time)
        else:
            end_datetime = start_datetime + timedelta(minutes=self.duration_minutes)

        if end_datetime <= start_datetime:
            raise ValidationError("L'heure de fin doit être après l'heure de début.")

        current_professors = ProfessorProfile.objects.filter(
            jury_memberships__jury=jury
        )

        conflicting_schedules = DefenseSchedule.objects.exclude(pk=self.pk).filter(
            jury_student__jury__defense_date=date,
            start_time__lt=end_datetime.time(),
            end_time__gt=start_datetime.time(),
            jury_student__jury__members__professor__in=current_professors
        ).distinct()

        if conflicting_schedules.exists():
            raise ValidationError(
                "Conflit d'horaire : un professeur de ce jury est déjà occupé."
            )

        unavailable = []

        for professor in current_professors:
            is_available = ProfessorAvailability.objects.filter(
                professor=professor,
                date=date,
                start_time__lte=self.start_time,
                end_time__gte=end_datetime.time(),
            ).exists()

            if not is_available:
                unavailable.append(professor.full_name)

        if unavailable:
            raise ValidationError(
                "Disponibilité manquante pour : " + ", ".join(unavailable)
            )

    def save(self, *args, **kwargs):
        if not self.end_time:
            jury = self.jury_student.jury
            start_datetime = datetime.combine(jury.defense_date, self.start_time)
            self.end_time = (
                start_datetime + timedelta(minutes=self.duration_minutes)
            ).time()

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.jury_student.student.full_name} - "
            f"{self.start_time} à {self.end_time}"
        )


class Note(models.Model):
    jury_student = models.ForeignKey(
        JuryStudent,
        on_delete=models.CASCADE,
        related_name="notes"
    )

    professor = models.ForeignKey(
        ProfessorProfile,
        on_delete=models.PROTECT,
        related_name="given_notes"
    )

    value = models.DecimalField(max_digits=5, decimal_places=2)
    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ("jury_student", "professor")

    def clean(self):
        jury_professors = ProfessorProfile.objects.filter(
            jury_memberships__jury=self.jury_student.jury
        )

        if self.professor not in jury_professors:
            raise ValidationError(
                "Ce professeur n'est pas membre du jury de cet étudiant."
            )

        if self.value < 0 or self.value > 20:
            raise ValidationError("La note doit être entre 0 et 20.")

        if self.pk:
            old_note = Note.objects.get(pk=self.pk)

            if old_note.is_submitted:
                raise ValidationError(
                    "La note a déjà été envoyée et ne peut plus être modifiée."
                )

    def submit(self):
        if self.is_submitted:
            raise ValidationError("Cette note est déjà envoyée.")

        self.is_submitted = True
        self.submitted_at = timezone.now()
        self.save()

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.professor.full_name} - "
            f"{self.jury_student.student.full_name} : {self.value}"
        )


class Evaluation(models.Model):
    jury_student = models.ForeignKey(
        JuryStudent,
        on_delete=models.CASCADE,
        related_name="evaluations"
    )

    professor = models.ForeignKey(
        ProfessorProfile,
        on_delete=models.PROTECT,
        related_name="given_evaluations"
    )

    rapport_note = models.DecimalField(max_digits=5, decimal_places=2)
    presentation_note = models.DecimalField(max_digits=5, decimal_places=2)
    questions_note = models.DecimalField(max_digits=5, decimal_places=2)

    final_note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True
    )

    is_submitted = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(blank=True, null=True)

    is_locked = models.BooleanField(default=False)

    unlocked_by_admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="unlocked_evaluations"
    )

    unlocked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ("jury_student", "professor")

    def clean(self):
        jury_professors = ProfessorProfile.objects.filter(
            jury_memberships__jury=self.jury_student.jury
        )

        if self.professor not in jury_professors:
            raise ValidationError(
                "Ce professeur n'est pas membre du jury de cet étudiant."
            )

        for field_name in ("rapport_note", "presentation_note", "questions_note"):
            value = getattr(self, field_name)

            if value is None or value < 0 or value > 20:
                raise ValidationError("Chaque note doit être entre 0 et 20.")

        if self.pk:
            old = Evaluation.objects.get(pk=self.pk)

            changed_notes = any(
                getattr(old, field) != getattr(self, field)
                for field in ("rapport_note", "presentation_note", "questions_note")
            )

            if old.is_locked and self.is_locked and changed_notes:
                raise ValidationError("Cette évaluation est verrouillée.")

    def calculate_final_note(self):
        value = (
            self.rapport_note * Decimal("0.30")
            + self.presentation_note * Decimal("0.30")
            + self.questions_note * Decimal("0.40")
        )

        self.final_note = value.quantize(Decimal("0.01"))
        return self.final_note

    def submit(self):
        if self.is_locked:
            raise ValidationError("Cette évaluation est verrouillée.")

        self.calculate_final_note()
        self.is_submitted = True
        self.is_locked = True
        self.submitted_at = timezone.now()
        self.save()

    def unlock(self, admin_user):
        self.is_locked = False
        self.is_submitted = False
        self.unlocked_by_admin = admin_user
        self.unlocked_at = timezone.now()
        self.save()

    def save(self, *args, **kwargs):
        if all(
            getattr(self, field) is not None
            for field in ("rapport_note", "presentation_note", "questions_note")
        ):
            self.calculate_final_note()

        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.professor.full_name} - "
            f"{self.jury_student.student.full_name} : {self.final_note}"
        )


class Result(models.Model):
    jury_student = models.OneToOneField(
        JuryStudent,
        on_delete=models.CASCADE,
        related_name="result"
    )

    average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True
    )

    note_gap_value = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True
    )

    has_note_gap_alert = models.BooleanField(default=False)

    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(blank=True, null=True)

    def calculate_average(self):
        evaluations = self.jury_student.evaluations.filter(is_submitted=True)

        if evaluations.count() != 3:
            raise ValidationError(
                "La moyenne ne peut être calculée qu'après les 3 évaluations."
            )

        notes = [evaluation.final_note for evaluation in evaluations]
        total = sum(notes, Decimal("0"))

        self.average = (total / Decimal("3")).quantize(Decimal("0.01"))
        self.note_gap_value = (max(notes) - min(notes)).quantize(Decimal("0.01"))
        self.has_note_gap_alert = self.note_gap_value >= Decimal("3.00")

        self.save()
        return self.average

    def publish(self):
        if self.average is None:
            self.calculate_average()

        self.is_published = True
        self.published_at = timezone.now()
        self.save()

    @property
    def mention(self):
        return mention_for_average(self.average)

    @property
    def is_validated(self):
        return self.average is not None and self.average >= PASS_THRESHOLD

    def __str__(self):
        return f"Résultat - {self.jury_student.student.full_name} - {self.average}"