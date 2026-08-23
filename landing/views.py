from django.contrib import messages
from django.shortcuts import get_object_or_404, render

from accounts.models import Principal, School, Teacher


def home(request):
    return render(request, "home.html")


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
