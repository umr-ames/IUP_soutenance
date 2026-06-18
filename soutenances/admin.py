from django.contrib import admin

from .models import (
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


class JuryMemberInline(admin.TabularInline):
    model = JuryMember
    extra = 3
    max_num = 3


class JuryStudentInline(admin.TabularInline):
    model = JuryStudent
    extra = 1


@admin.register(Deadline)
class DeadlineAdmin(admin.ModelAdmin):
    list_display = ('title', 'deadline_date', 'is_active')
    list_filter = ('is_active',)


@admin.register(PFERequest)
class PFERequestAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'status',
        'submitted_at',
        'professor_reviewed_at',
        'admin_reviewed_at',
    )
    list_filter = ('status', 'submitted_at')
    search_fields = ('student__full_name', 'student__matricule')
    readonly_fields = ('submitted_at', 'professor_reviewed_at', 'admin_reviewed_at')


@admin.register(Jury)
class JuryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'defense_date',
        'members_count',
        'students_count',
        'is_validated',
    )
    list_filter = ('defense_date', 'is_validated')
    search_fields = ('name',)
    inlines = [JuryMemberInline, JuryStudentInline]


@admin.register(JuryMember)
class JuryMemberAdmin(admin.ModelAdmin):
    list_display = ('jury', 'professor')
    list_filter = ('jury', 'professor')
    search_fields = ('jury__name', 'professor__full_name')


@admin.register(JuryStudent)
class JuryStudentAdmin(admin.ModelAdmin):
    list_display = ('student', 'jury', 'assigned_at', 'presentation_started')
    list_filter = ('jury', 'student__filiere')
    search_fields = (
        'student__full_name',
        'student__matricule',
        'jury__name',
    )


@admin.register(DefenseSchedule)
class DefenseScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'jury_student',
        'start_time',
        'end_time',
        'duration_minutes',
    )
    list_filter = (
        'jury_student__jury',
        'jury_student__jury__defense_date',
    )


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = (
        'jury_student',
        'professor',
        'value',
        'is_submitted',
        'submitted_at',
    )
    list_filter = ('is_submitted', 'professor')
    search_fields = (
        'jury_student__student__full_name',
        'professor__full_name',
    )


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = (
        'jury_student',
        'professor',
        'rapport_note',
        'presentation_note',
        'questions_note',
        'final_note',
        'is_submitted',
        'is_locked',
    )
    list_filter = ('is_submitted', 'is_locked', 'professor')
    search_fields = (
        'jury_student__student__full_name',
        'professor__full_name',
    )


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = (
        'jury_student',
        'average',
        'note_gap_value',
        'has_note_gap_alert',
        'is_published',
        'published_at',
    )
    list_filter = ('is_published', 'has_note_gap_alert')
    search_fields = (
        'jury_student__student__full_name',
        'jury_student__student__matricule',
    )
