from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import School, User

from .forms import SchoolProfileForm, SupervisorLoginForm


def _is_supervisor(user):
    return user.is_authenticated and user.role == User.Role.SUPERVISOR


def login_view(request):
    # Already logged in as the supervisor? Skip straight to the dashboard.
    if _is_supervisor(request.user):
        return redirect("supervisor:dashboard")

    form = SupervisorLoginForm(request=request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        auth_login(request, user)
        messages.success(request, f"Welcome back, {user.full_name}.")
        return redirect("supervisor:dashboard")

    return render(request, "supervisor/login.html", {"form": form})


@login_required(login_url="supervisor:login")
def dashboard_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    return render(request, "supervisor/dashboard.html")


@login_required(login_url="supervisor:login")
def school_list_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    schools = School.objects.order_by("school_name")
    return render(request, "supervisor/schools.html", {"schools": schools})


@login_required(login_url="supervisor:login")
def school_create_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    form = SchoolProfileForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        school = form.save(commit=False)
        school.created_by = request.user
        school.save()
        messages.success(request, f"{school.school_name} was added successfully.")
        return redirect("supervisor:schools")

    return render(
        request,
        "supervisor/school_form.html",
        {"form": form, "page_title": "Add School", "submit_label": "Create School"},
    )


@login_required(login_url="supervisor:login")
def school_edit_view(request, school_id):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    school = get_object_or_404(School, pk=school_id)
    form = SchoolProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=school,
    )
    if request.method == "POST" and form.is_valid():
        school = form.save()
        messages.success(request, f"{school.school_name} was updated successfully.")
        return redirect("supervisor:schools")

    return render(
        request,
        "supervisor/school_form.html",
        {"form": form, "school": school, "page_title": "Edit School", "submit_label": "Save Changes"},
    )


@login_required(login_url="supervisor:login")
def logout_view(request):
    auth_logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("supervisor:login")
