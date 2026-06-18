from django.urls import path
from . import views

urlpatterns = [
    path('login/', views.phone_login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.student_register_view, name='student_register'),
    path('prof/', views.professor_register_view, name='professor_register'),
]