from django.urls import path

from . import views

app_name = "supervisor"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("principal/dashboard/", views.principal_dashboard_view, name="principal_dashboard"),
    path("school-profile/", views.principal_school_profile_view, name="principal_school_profile"),
    path("teachers/", views.teacher_list_view, name="teachers"),
    path("teachers/create/", views.teacher_create_view, name="teacher_create"),
    path("principals/", views.principal_list_view, name="principals"),
    path("principals/create/", views.principal_create_view, name="principal_create"),
    path("schools/", views.school_list_view, name="schools"),
    path("schools/create/", views.school_create_view, name="school_create"),
    path("schools/<int:school_id>/edit/", views.school_edit_view, name="school_edit"),
]
