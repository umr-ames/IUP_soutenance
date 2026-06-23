from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import render, redirect

from .forms import PhoneLoginForm, StudentRegisterForm, ProfessorRegisterForm
from .models import CustomUser
from students.models import StudentProfile


@login_required
def change_password_view(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password') or ''
        new_password1 = request.POST.get('new_password1') or ''
        new_password2 = request.POST.get('new_password2') or ''

        if not request.user.check_password(old_password):
            messages.error(request, "Mot de passe actuel incorrect.")
        elif new_password1 != new_password2:
            messages.error(request, "Les deux nouveaux mots de passe ne correspondent pas.")
        else:
            try:
                validate_password(new_password1, request.user)
            except DjangoValidationError as error:
                messages.error(request, " ".join(error.messages))
            else:
                request.user.set_password(new_password1)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Votre mot de passe a été modifié avec succès.")
                return redirect('dashboard')

    return render(request, 'accounts/change_password.html')


def phone_login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = PhoneLoginForm(request, request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('dashboard')
    else:
        form = PhoneLoginForm()

    return render(request, 'accounts/login.html', {
        'form': form
    })


def logout_view(request):
    logout(request)
    return redirect('login')


def student_register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = StudentRegisterForm(request.POST)

        if form.is_valid():
            matricule = form.cleaned_data['matricule']
            full_name = form.cleaned_data['full_name']
            email = form.cleaned_data['email']
            phone_number = form.cleaned_data['phone_number']
            filiere = form.cleaned_data['filiere']
            encadrant = form.cleaned_data['encadrant']
            entreprise = form.cleaned_data['entreprise']
            password = form.cleaned_data['password1']

            username = matricule.lower()

            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                phone_number=phone_number,
                password=password,
                role=CustomUser.ROLE_STUDENT
            )

            StudentProfile.objects.create(
                user=user,
                matricule=matricule,
                full_name=full_name,
                filiere=filiere,
                encadrant=encadrant,
                entreprise=entreprise,
            )

            login(request, user, backend='accounts.backends.PhoneOrUsernameBackend')

            messages.success(
                request,
                "Votre compte étudiant a été créé avec succès."
            )
            return redirect('dashboard')
    else:
        form = StudentRegisterForm()

    return render(request, 'accounts/student_register.html', {
        'form': form
    })


def professor_register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = ProfessorRegisterForm(request.POST)

        if form.is_valid():
            professor = form.cleaned_data['professor']
            email = form.cleaned_data['email']
            phone_number = form.cleaned_data['phone_number']
            password = form.cleaned_data['password1']

            username = f"prof_{professor.id}"

            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                phone_number=phone_number,
                password=password,
                role=CustomUser.ROLE_PROFESSOR
            )

            professor.user = user
            professor.phone = phone_number
            professor.save()

            login(request, user, backend='accounts.backends.PhoneOrUsernameBackend')

            messages.success(
                request,
                "Votre compte professeur a été créé avec succès."
            )
            return redirect('dashboard')
    else:
        form = ProfessorRegisterForm()

    return render(request, 'accounts/professor_register.html', {
        'form': form
    })
