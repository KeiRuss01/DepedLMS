from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import AccountLoginForm, AccountSignupForm
from .models import User


def login_view(request):
    classroom_roles = {
        User.Role.TEACHER,
        User.Role.STUDENT,
        User.Role.PARENT,
    }
    if request.user.is_authenticated:
        return _role_redirect(request.user)

    form = AccountLoginForm(
        request=request,
        data=request.POST or None,
        allowed_roles=classroom_roles,
    )
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        return _role_redirect(user)

    return render(request, "accounts/login.html", {"form": form})


def signup_view(request):
    if request.user.is_authenticated:
        return _role_redirect(request.user)

    form = AccountSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your account was created successfully.")
        return _role_redirect(user)

    return render(request, "accounts/signup.html", {"form": form})


@login_required(login_url="accounts:login")
def account_home(request):
    return _role_redirect(request.user)


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("accounts:login")


def _role_redirect(user):
    if user.role == User.Role.SUPERVISOR:
        return redirect("supervisor:dashboard")

    if user.role == User.Role.PRINCIPAL:
        return redirect("supervisor:principal_dashboard")

    if user.role in {
        User.Role.TEACHER,
        User.Role.STUDENT,
        User.Role.PARENT,
    }:
        return redirect("classroom:dashboard")

    return redirect("accounts:login")
