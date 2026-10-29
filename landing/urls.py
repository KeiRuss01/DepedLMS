from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("service-worker.js", views.service_worker, name="service_worker"),
    path("offline/", views.offline, name="offline"),
    path("app/", views.app_entry, name="app_entry"),
    path("download/", views.download, name="download"),
    path("school/", views.school, name="school"),
    path("school/<int:school_id>/", views.school_detail, name="school_detail"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
    path(
        "offline/modules/",
        views.offline_modules,
        name="offline_modules",
    ),
    path(
        "offline/modules/editor/",
        views.offline_module_editor,
        name="offline_module_editor",
    ),
    path(
        "pwa/devices/register/",
        views.register_device,
        name="register_device",
    ),
    path(
        "offline/attendance/",
        views.offline_attendance,
        name="offline_attendance",
    ),
    path(
        "offline/grades/",
        views.offline_grades,
        name="offline_grades",
    ),
]
