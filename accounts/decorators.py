from functools import wraps

from django.shortcuts import redirect
from django.contrib import messages


def role_required(allowed_roles):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')

            if request.user.role not in allowed_roles:
                messages.error(
                    request,
                    "Vous n'avez pas l'autorisation d'accéder à cette page."
                )
                return redirect('dashboard')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
