from django.urls import path

from . import views
from .views_stats import admin_statistiques


urlpatterns = [
    path("", views.dashboard_redirect, name="dashboard"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-dashboard/students/", views.admin_student_list, name="admin_student_list"),
    path("admin-dashboard/students/verifier-liste-officielle/", views.admin_check_official_list, name="admin_check_official_list"),
    path("admin-dashboard/students/liste-complete/", views.admin_students_overview, name="admin_students_overview"),
    path("admin-dashboard/students/liste-complete/export.xlsx", views.admin_students_overview_export, name="admin_students_overview_export"),
    path("admin-dashboard/students/<int:pk>/reset-password/", views.admin_reset_student_password, name="admin_reset_student_password"),
    path("admin-dashboard/professors/", views.admin_professor_list, name="admin_professor_list"),
    path("admin-dashboard/professors/recap/", views.admin_professors_recap, name="admin_professors_recap"),
    path("admin-dashboard/professors/details/", views.admin_professors_details, name="admin_professors_details"),
    path("admin-dashboard/professors/<int:pk>/fiche/", views.admin_professor_fiche, name="admin_professor_fiche"),
    path("professor-dashboard/ma-fiche/", views.professor_my_recap, name="professor_my_recap"),
    path("admin-dashboard/professors/<int:pk>/rename/", views.admin_rename_professor, name="admin_rename_professor"),
    path("admin-dashboard/professors/<int:pk>/toggle-priority/", views.admin_toggle_priority_professor, name="admin_toggle_priority_professor"),
    path("admin-dashboard/encadrant-etudiants/", views.admin_professor_students, name="admin_professor_students"),
    path("admin-dashboard/professors/<int:pk>/reset-password/", views.admin_reset_professor_password, name="admin_reset_professor_password"),
    path("admin-dashboard/import/", views.admin_import_people, name="admin_import_people"),
    path("admin-dashboard/import-references/", views.admin_import_student_references, name="admin_import_student_references"),
    path("sondage/", views.survey_form, name="survey_form"),
    path("admin-dashboard/sondage/", views.admin_survey_results, name="admin_survey_results"),
    path("admin-dashboard/sondage/etat/", views.admin_survey_toggle, name="admin_survey_toggle"),
    path("admin-dashboard/statistiques/", admin_statistiques, name="admin_statistiques"),
    path("admin-dashboard/statistiques/restants/", views.admin_stat_restants, name="admin_stat_restants"),
    path("admin-dashboard/statistiques/non-inscrits/", views.admin_stat_non_inscrits, name="admin_stat_non_inscrits"),
    path("admin-dashboard/statistiques/non-notes/", views.admin_stat_non_notes, name="admin_stat_non_notes"),
    path("admin-dashboard/statistiques/sans-demande/", views.admin_stat_sans_demande, name="admin_stat_sans_demande"),
    path("admin-dashboard/statistiques/rapport/", views.admin_stats_report, name="admin_stats_report"),
    path("admin-dashboard/statistiques/resultats/explorer/", views.admin_results_explorer, name="admin_results_explorer"),
    path("admin-dashboard/professors/jurys-details/", views.admin_professors_jury_details, name="admin_professors_jury_details"),
    path("professor-dashboard/", views.professor_dashboard, name="professor_dashboard"),
    path("student-dashboard/", views.student_dashboard, name="student_dashboard"),
    path("notifications/feed/", views.notifications_feed, name="notifications_feed"),
    path("notifications/<int:pk>/open/", views.notification_open, name="notification_open"),
    path("notifications/mark-all-read/", views.notifications_mark_all_read, name="notifications_mark_all_read"),
]
