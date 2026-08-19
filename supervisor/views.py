from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Principal, School, Teacher, User

from .forms import (
    AdministrationLoginForm,
    PrincipalAccountForm,
    SchoolProfileForm,
    TeacherAccountForm,
)


def _is_supervisor(user):
    return user.is_authenticated and user.role == User.Role.SUPERVISOR

def _is_principal(user):
    return user.is_authenticated and user.role == User.Role.PRINCIPAL


def _administration_redirect(user):
    if user.role == User.Role.SUPERVISOR:
        return redirect("supervisor:dashboard")
    if user.role == User.Role.PRINCIPAL:
        return redirect("supervisor:principal_dashboard")
    return redirect("accounts:login")



def login_view(request):
    if _is_supervisor(request.user) or _is_principal(request.user):
        return _administration_redirect(request.user)

    form = AdministrationLoginForm(request=request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        auth_login(request, user)
        messages.success(request, f"Welcome back, {user.full_name}.")
        return _administration_redirect(user)

    return render(request, "supervisor/login.html", {"form": form})


@login_required(login_url="supervisor:login")
def dashboard_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    return render(request, "supervisor/dashboard.html")



@login_required(login_url="supervisor:login")
def principal_dashboard_view(request):
    if not _is_principal(request.user):
        messages.error(request, "You don't have access to the Principal portal.")
        return _administration_redirect(request.user)

    return render(request, "supervisor/principal_dashboard.html")

@login_required(login_url="supervisor:login")
def principal_school_profile_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can update their assigned school profile.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    form = SchoolProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=principal.school,
    )
    if request.method == "POST" and form.is_valid():
        school = form.save()
        messages.success(request, f"{school.school_name} profile was updated.")
        return redirect("supervisor:principal_school_profile")

    return render(
        request,
        "supervisor/principal_school_profile.html",
        {"form": form, "school": principal.school},
    )


@login_required(login_url="supervisor:login")
def teacher_list_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can manage Teacher accounts.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    teachers = Teacher.objects.filter(school=principal.school).select_related(
        "user",
        "school",
    ).order_by("lastname", "firstname")
    return render(
        request,
        "supervisor/teachers.html",
        {"teachers": teachers, "school": principal.school},
    )


@login_required(login_url="supervisor:login")
def teacher_create_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can add Teacher accounts.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    form = TeacherAccountForm(
        request.POST or None,
        school=principal.school,
    )
    if request.method == "POST" and form.is_valid():
        teacher = form.save()
        messages.success(
            request,
            f"Teacher account for {teacher.firstname} {teacher.lastname} was created.",
        )
        return redirect("supervisor:teachers")

    return render(
        request,
        "supervisor/teacher_form.html",
        {"form": form, "school": principal.school},
    )


@login_required(login_url="supervisor:login")
def principal_list_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "Only the District Supervisor can manage Principal accounts.")
        return _administration_redirect(request.user)

    principals = Principal.objects.select_related("user", "school").order_by(
        "lastname",
        "firstname",
    )
    return render(
        request,
        "supervisor/principals.html",
        {"principals": principals},
    )


@login_required(login_url="supervisor:login")
def principal_create_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "Only the District Supervisor can add Principal accounts.")
        return _administration_redirect(request.user)

    form = PrincipalAccountForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        principal = form.save()
        messages.success(
            request,
            f"Principal account for {principal.firstname} {principal.lastname} was created.",
        )
        return redirect("supervisor:principals")

    return render(
        request,
        "supervisor/principal_form.html",
        {
            "form": form,
            "has_schools": School.objects.exists(),
        },
    )



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
