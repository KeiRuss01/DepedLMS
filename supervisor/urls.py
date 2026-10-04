from django.urls import path

from . import views

app_name = "supervisor"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("principal/dashboard/", views.principal_dashboard_view, name="principal_dashboard"),
    path(
        "principal/announcements/create/",
        views.school_announcement_create_view,
        name="school_announcement_create",
    ),
    path("school-profile/", views.principal_school_profile_view, name="principal_school_profile"),
    path("teachers/", views.teacher_list_view, name="teachers"),
    path("teachers/create/", views.teacher_create_view, name="teacher_create"),
    path("students/", views.student_list_view, name="students"),
    path("classes/", views.class_list_view, name="classes"),
    path("principals/", views.principal_list_view, name="principals"),
    path("principals/create/", views.principal_create_view, name="principal_create"),
    path("schools/", views.school_list_view, name="schools"),
    path("schools/create/", views.school_create_view, name="school_create"),
    path("schools/<int:school_id>/", views.school_detail_view, name="school_detail"),
    path("schools/<int:school_id>/edit/", views.school_edit_view, name="school_edit"),
    # District Supervisor calendar
    path(
        "calendar/",
        views.district_calendar_view,
        name="district_calendar",
    ),
    path(
        "calendar/events/<int:event_id>/cancel/",
        views.district_calendar_event_cancel_view,
        name="district_calendar_event_cancel",
    ),

    # Principal school calendar
    path(
        "principal/calendar/",
        views.principal_calendar_view,
        name="principal_calendar",
    ),
    path(
        "principal/calendar/events/<int:event_id>/cancel/",
        views.principal_calendar_event_cancel_view,
        name="principal_calendar_event_cancel",
    ),
]
