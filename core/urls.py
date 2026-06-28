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
    path("admin-dashboard/encadrant-etudiants/", views.admin_professor_students, name="admin_professor_students"),
    path("admin-dashboard/professors/<int:pk>/reset-password/", views.admin_reset_professor_password, name="admin_reset_professor_password"),
    path("admin-dashboard/import/", views.admin_import_people, name="admin_import_people"),
    path("admin-dashboard/import-references/", views.admin_import_student_references, name="admin_import_student_references"),
    path("admin-dashboard/statistiques/", admin_statistiques, name="admin_statistiques"),
    path("professor-dashboard/", views.professor_dashboard, name="professor_dashboard"),
    path("student-dashboard/", views.student_dashboard, name="student_dashboard"),
]
