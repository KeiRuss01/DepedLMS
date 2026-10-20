from django.contrib import messages
from django.contrib.auth import (
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_GET, require_POST
from django.urls import reverse
from django.utils import timezone

from .forms import (
    AccountLoginForm,
    AccountPasswordChangeForm,
    AccountSignupForm,
    ProfileUpdateForm,
    UserPreferenceForm,
)
from .models import Notification, User, UserPreference
from django.http import JsonResponse


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

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "auth_base_template": _auth_base_template(request),
        },
    )


def signup_view(request):
    if request.user.is_authenticated:
        return _role_redirect(request.user)

    form = AccountSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Your account was created successfully.")
        return _role_redirect(user)

    return render(
        request,
        "accounts/signup.html",
        {
            "form": form,
            "auth_base_template": _auth_base_template(request),
        },
    )


@login_required(login_url="accounts:login")
def account_home(request):
    return _role_redirect(request.user)

@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("accounts:login")

@login_required(login_url="accounts:login")
def profile_view(request):
    user = request.user

    profile = (
        getattr(user, "teacher_profile", None)
        or getattr(user, "student_profile", None)
        or getattr(user, "parent_profile", None)
        or getattr(user, "principal_profile", None)
        or getattr(user, "supervisor_profile", None)
    )

    if request.method == "POST":
        form = ProfileUpdateForm(
            request.POST,
            request.FILES,
            instance=user,
        )

        if form.is_valid():
            form.save()

            messages.success(
                request,
                "Your profile was updated successfully.",
            )

            return redirect("accounts:profile")
    else:
        form = ProfileUpdateForm(instance=user)

    student_grade_level = ""
    student_section = ""
    student_class_warning = False

    if user.role == User.Role.STUDENT and profile:
        from classroom.models import ClassEnrollment

        approved_enrollments = (
            profile.class_enrollments
            .filter(
                status=ClassEnrollment.Status.APPROVED,
                classroom__is_archived=False,
            )
            .select_related("classroom")
        )

        grade_levels = list(
            approved_enrollments
            .values_list(
                "classroom__grade_level",
                flat=True,
            )
            .distinct()
            .order_by("classroom__grade_level")
        )

        sections = list(
            approved_enrollments
            .values_list(
                "classroom__section",
                flat=True,
            )
            .distinct()
            .order_by("classroom__section")
        )

        student_grade_level = (
            ", ".join(grade_levels)
            if grade_levels
            else "Not assigned"
        )

        student_section = (
            ", ".join(sections)
            if sections
            else "Not assigned"
        )

        student_class_warning = (
            len(grade_levels) > 1
            or len(sections) > 1
        )

        context = {
            "profile": profile,
            "profile_form": form,
            "student_grade_level": student_grade_level,
            "student_section": student_section,
            "student_class_warning": student_class_warning,
        }

    return render(
        request,
        "accounts/profile.html",
        context,
    )

@login_required(login_url="accounts:login")
def settings_view(request):
    preference, created = UserPreference.objects.get_or_create(
        user=request.user
    )

    preference_form = UserPreferenceForm(
        instance=preference,
        user=request.user,
    )

    password_form = AccountPasswordChangeForm(
        request.user
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_preferences":
            preference_form = UserPreferenceForm(
                request.POST,
                instance=preference,
                user=request.user,
            )

            if preference_form.is_valid():
                preference_form.save()

                messages.success(
                    request,
                    "Your settings were saved.",
                )

                return redirect("accounts:settings")

        elif action == "change_password":
            password_form = AccountPasswordChangeForm(
                request.user,
                request.POST,
            )

            if password_form.is_valid():
                updated_user = password_form.save()

                # Prevent the user from being logged out.
                update_session_auth_hash(
                    request,
                    updated_user,
                )

                messages.success(
                    request,
                    "Your password was changed successfully.",
                )

                return redirect("accounts:settings")

        else:
            messages.error(
                request,
                "The requested settings action was not recognized.",
            )

    context = {
        "preference_form": preference_form,
        "password_form": password_form,
        "preference": preference,
    }

    return render(
        request,
        "accounts/settings.html",
        context,
    )

@login_required(login_url="accounts:login")
def notifications_view(request):
    notifications = (
        request.user.notifications
        .all()[:50]
    )

    template_name = "accounts/notifications.html"
    if request.user.role in {
        User.Role.SUPERVISOR,
        User.Role.PRINCIPAL,
    }:
        template_name = "supervisor/admin_notifications.html"

    return render(
        request,
        template_name,
        {
            "notifications": notifications,
        },
    )

@login_required(login_url="accounts:login")
@require_POST
def open_notification_view(request, notification_id):
    notification = get_object_or_404(
        Notification,
        notification_id=notification_id,
        recipient=request.user,
    )

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()

        notification.save(
            update_fields=[
                "is_read",
                "read_at",
            ]
        )

    target_url = notification.target_url

    # Only allow internal links.
    if (
        not target_url
        or not target_url.startswith("/")
        or target_url.startswith("//")
    ):
        if request.user.role == User.Role.SUPERVISOR:
            target_url = reverse("supervisor:dashboard")
        elif request.user.role == User.Role.PRINCIPAL:
            target_url = reverse("supervisor:principal_dashboard")
        else:
            target_url = reverse("classroom:dashboard")

    return redirect(target_url)

@login_required(login_url="accounts:login")
@require_POST
def mark_all_notifications_read_view(request):
    request.user.notifications.filter(
        is_read=False
    ).update(
        is_read=True,
        read_at=timezone.now(),
    )

    messages.success(
        request,
        "All notifications were marked as read.",
    )

    return redirect("accounts:notifications")

@login_required(login_url="accounts:login")
@require_GET
def notification_status_view(request):
    preference, created = UserPreference.objects.get_or_create(
        user=request.user
    )

    notifications = request.user.notifications.all()
    latest_notification = notifications.first()

    response_data = {
        "unread_count": notifications.filter(
            is_read=False
        ).count(),
        "latest_id": None,
        "latest_title": "",
        "latest_message": "",
        "sound_enabled": preference.sound_enabled,
        "vibration_enabled": preference.vibration_enabled,
    }

    if latest_notification:
        response_data.update(
            {
                "latest_id": latest_notification.notification_id,
                "latest_title": latest_notification.title,
                "latest_message": latest_notification.message,
            }
        )

    return JsonResponse(response_data)

def _auth_base_template(request):
    """Use the clean shell only when opened by the installed application."""
    if request.GET.get("app") == "1":
        request.session["app_shell"] = True
    elif request.GET.get("web") == "1":
        request.session.pop("app_shell", None)

    if request.session.get("app_shell"):
        return "accounts/app_auth_base.html"
    return "accounts/auth_base.html"


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
