from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import Principal, School, Teacher


def home(request):
    # The normal website keeps its complete public landing page.
    request.session.pop("app_shell", None)
    request.session.pop("classroom_splash_seen", None)
    return render(request, "home.html")


def app_entry(request):
    """Entry point reserved for the mobile and desktop application shells."""
    if request.user.is_authenticated:
        return redirect("accounts:home")

    request.session["app_shell"] = True
    return render(
        request,
        "app_splash.html",
        {"login_url": "/accounts/login/?app=1"},
    )


def download(request):
    return render(request, "download.html")


def school(request):
    schools = School.objects.order_by("school_name")
    return render(request, "school.html", {"schools": schools})


def school_detail(request, school_id):
    school = get_object_or_404(School, pk=school_id)
    principals = Principal.objects.filter(school=school).select_related("user")
    teachers = Teacher.objects.filter(school=school).select_related("user").order_by(
        "lastname", "firstname"
    )
    return render(
        request,
        "school_detail.html",
        {
            "school": school,
            "principals": principals,
            "teachers": teachers,
        },
    )


def about(request):
    return render(request, "about.html")


def contact(request):
    if request.method == "POST":
        # Connect this form to your email service or a Contact model.
        messages.success(request, "Thank you. Your message has been received.")
    return render(request, "contact.html")
