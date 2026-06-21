from django.urls import path

from . import views


urlpatterns = [
    path(
        "admin/availabilities/",
        views.admin_professor_availability,
        name="admin_professor_availability"
    ),

    path(
        "admin/availabilities/edit/",
        views.admin_professor_availability_edit,
        name="admin_professor_availability_edit"
    ),

    path(
        "availability/",
        views.professor_availability,
        name="professor_availability"
    ),

    path(
        "students/",
        views.professor_supervised_students,
        name="professor_supervised_students"
    ),

    path(
        "requests/",
        views.professor_requests,
        name="professor_requests"
    ),

    path(
        "requests/<int:pk>/",
        views.professor_request_detail,
        name="professor_request_detail"
    ),

    path(
        "juries/",
        views.professor_my_juries,
        name="professor_my_juries"
    ),

    path(
        "evaluations/",
        views.professor_evaluations,
        name="professor_evaluations"
    ),

    path(
        "evaluations/<int:jury_student_id>/",
        views.professor_evaluation_detail,
        name="professor_evaluation_detail"
    ),

    path(
        "juries/<int:jury_student_id>/start/",
        views.professor_start_presentation,
        name="professor_start_presentation"
    ),

    path(
        "juries/<int:jury_student_id>/soutenable/",
        views.professor_set_pfe_soutenable,
        name="professor_set_pfe_soutenable"
    ),

    path(
        "submitted-notes/",
        views.professor_submitted_notes,
        name="professor_submitted_notes"
    ),
]