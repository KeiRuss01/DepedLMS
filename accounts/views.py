from django.contrib import messages
from django.contrib.auth import (
    login,
    logout,
    update_session_auth_hash,
)
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
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


@never_cache
@ensure_csrf_cookie
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

        if form.cleaned_data.get("remember_me"):
            # Keep the user logged in for 30 days.
            request.session.set_expiry(60 * 60 * 24 * 30)
        else:
            # Session expires when the browser closes.
            request.session.set_expiry(0)

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

    # Keep the fields explicit even when the learner has not joined an
    # approved class yet; empty boxes are confusing on mobile.
    student_grade_level = "Not assigned"
    student_section = "Not assigned"
    student_class_warning = False
    context = {
        "profile": profile,
        "profile_form": form,
        "student_grade_level": student_grade_level,
        "student_section": student_section,
        "student_class_warning": student_class_warning,
    }

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

        # A student can have several subject classrooms, but the profile
        # should show only the current school year's grade and section.
        current_school_year = (
            approved_enrollments
            .values_list("classroom__school_year", flat=True)
            .distinct()
            .order_by("-classroom__school_year")
            .first()
        )

        current_enrollments = approved_enrollments.filter(
            classroom__school_year=current_school_year,
        ) if current_school_year else approved_enrollments.none()

        grade_levels = list(
            current_enrollments
            .values_list("classroom__grade_level", flat=True)
            .distinct()
            .order_by("classroom__grade_level")
        )

        sections = list(
            current_enrollments
            .values_list("classroom__section", flat=True)
            .distinct()
            .order_by("classroom__section")
        )

        student_grade_level = (
            grade_levels[0]
            if grade_levels
            else "Not assigned"
        )

        student_section = (
            sections[0]
            if sections
            else "Not assigned"
        )

        student_class_warning = (
            len(grade_levels) > 1
            or len(sections) > 1
        )

        # The values above are calculated after the initial context is built.
        # Copy them back into the context before rendering the profile page.
        context.update(
            {
                "student_grade_level": student_grade_level,
                "student_section": student_section,
                "student_class_warning": student_class_warning,
            }
        )

    return render(
        request,
        "accounts/profile.html",
        context,
    )


@login_required(login_url="accounts:login")
@require_POST
def send_email_verification(request):
    user = request.user

    if user.email_verified:
        messages.info(request, "Your email address is already verified.")
        return redirect("accounts:profile")

    token = signing.dumps(
        {"user_id": user.pk, "email": user.email},
        salt="accounts.email-verification",
    )
    verify_path = reverse(
        "accounts:verify_email",
        kwargs={"token": token},
    )
    verify_url = f"{settings.SITE_URL.rstrip('/')}{verify_path}"

    try:
        send_mail(
            "Verify your North 1 District LMS email",
            (
                f"Hello {user.full_name},\n\n"
                "Please verify your email address by opening this link:\n"
                f"{verify_url}\n\n"
                "This link expires in 24 hours."
            ),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
    except Exception:
        messages.error(
            request,
            "The verification email could not be sent. Please try again later.",
        )
    else:
        messages.success(
            request,
            "A verification link was sent to your email address.",
        )

    return redirect("accounts:profile")


def verify_email(request, token):
    try:
        payload = signing.loads(
            token,
            salt="accounts.email-verification",
            max_age=settings.EMAIL_VERIFICATION_TIMEOUT,
        )
        user = User.objects.get(
            pk=payload["user_id"],
            email__iexact=payload["email"],
        )
    except (BadSignature, SignatureExpired, KeyError, User.DoesNotExist):
        messages.error(
            request,
            "That verification link is invalid or has expired.",
        )
        return redirect("accounts:login")

    if not user.email_verified:
        user.email_verified = True
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified", "email_verified_at"])

    messages.success(request, "Your email address has been verified.")
    if request.user.is_authenticated and request.user.pk == user.pk:
        return redirect("accounts:profile")
    return redirect("accounts:login")

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
    notifications = request.user.notifications.all()
    latest_notification = (
        notifications.filter(is_read=False).first()
        or notifications.first()
    )

    response_data = {
        "unread_count": notifications.filter(
            is_read=False
        ).count(),
        "latest_id": None,
        "latest_title": "",
        "latest_message": "",
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
