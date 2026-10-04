from django.urls import path

from . import views


app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("home/", views.account_home, name="home"),
    path("logout/", views.logout_view, name="logout"),
    path(
        "profile/",
        views.profile_view,
        name="profile",
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
