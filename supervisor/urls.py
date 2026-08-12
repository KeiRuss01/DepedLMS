from django.urls import path

from . import views

app_name = "supervisor"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("schools/", views.school_list_view, name="schools"),
    path("schools/create/", views.school_create_view, name="school_create"),
    path("schools/<int:school_id>/edit/", views.school_edit_view, name="school_edit"),
]
