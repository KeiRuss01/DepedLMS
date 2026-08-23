from django.urls import path

from . import views


urlpatterns = [
    path("", views.home, name="home"),
    path("download/", views.download, name="download"),
    path("school/", views.school, name="school"),
    path("school/<int:school_id>/", views.school_detail, name="school_detail"),
    path("about/", views.about, name="about"),
    path("contact/", views.contact, name="contact"),
]
