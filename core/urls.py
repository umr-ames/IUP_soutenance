from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard_redirect, name="dashboard"),
    path("admin-dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin-dashboard/students/", views.admin_student_list, name="admin_student_list"),
    path("admin-dashboard/professors/", views.admin_professor_list, name="admin_professor_list"),
    path("admin-dashboard/import/", views.admin_import_people, name="admin_import_people"),
    path("admin-dashboard/import-references/", views.admin_import_student_references, name="admin_import_student_references"),
    path("professor-dashboard/", views.professor_dashboard, name="professor_dashboard"),
    path("student-dashboard/", views.student_dashboard, name="student_dashboard"),
]
