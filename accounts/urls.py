from django.urls import path
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from . import views
from .forms import AccountPasswordResetForm, AccountSetPasswordForm


app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("home/", views.account_home, name="home"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=AccountPasswordResetForm,
            template_name="accounts/password_reset_form.html",
            email_template_name="accounts/password_reset_email.txt",
            subject_template_name="accounts/password_reset_subject.txt",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            form_class=AccountSetPasswordForm,
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    path(
        "profile/",
        views.profile_view,
        name="profile",
    ),
    path(
        "verify-email/send/",
        views.send_email_verification,
        name="send_email_verification",
    ),
    path(
        "verify-email/<str:token>/",
        views.verify_email,
        name="verify_email",
    ),

    path(
        "settings/",
        views.settings_view,
        name="settings",
    ),

    path(
        "notifications/",
        views.notifications_view,
        name="notifications",
    ),

    path(
        "notifications/status/",
        views.notification_status_view,
        name="notification_status",
    ),

    path(
        "notifications/<int:notification_id>/open/",
        views.open_notification_view,
        name="open_notification",
    ),

    path(
        "notifications/read-all/",
        views.mark_all_notifications_read_view,
        name="mark_all_notifications_read",
    ),
]
