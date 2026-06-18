from django.urls import path
from . import views

urlpatterns = [
    path(
        'demande-soutenance/',
        views.submit_pfe_request,
        name='submit_pfe_request'
    ),
    path(
        'api/lookup-matricule/',
        views.lookup_student_reference,
        name='lookup_student_reference'
    ),
]