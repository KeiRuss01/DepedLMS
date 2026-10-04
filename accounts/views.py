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

    student_enrollments = []

    if user.role == User.Role.STUDENT and profile:
        from classroom.models import ClassEnrollment

        student_enrollments = (
            profile.class_enrollments
            .filter(status=ClassEnrollment.Status.APPROVED)
            .select_related("classroom")
            .order_by(
                "classroom__grade_level",
                "classroom__section",
            )
        )

    context = {
        "profile": profile,
        "profile_form": form,
        "student_enrollments": student_enrollments,
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

    if request.user.role == User.Role.TEACHER:
        mandatory_sms_items = [
            "School-wide announcements",
        ]
    else:
        mandatory_sms_items = [
            "Newly uploaded modules",
            "Approaching module deadlines",
            "Class and school announcements",
        ]

    phone_number = request.user.phone_number or ""

    if len(phone_number) >= 6:
        masked_phone = (
            f"{phone_number[:4]} ••• ••{phone_number[-2:]}"
        )
    else:
        masked_phone = "No mobile number registered"

    # Keep the masked value ASCII-safe when the source file is moved
    # between Windows editors with different encodings.
    if len(phone_number) >= 6:
        masked_phone = (
            f"{phone_number[:4]} *** **{phone_number[-2:]}"
        )

    context = {
        "preference_form": preference_form,
        "password_form": password_form,
        "preference": preference,
        "mandatory_sms_items": mandatory_sms_items,
        "masked_phone": masked_phone,
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

    return render(
        request,
        "accounts/notifications.html",
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
