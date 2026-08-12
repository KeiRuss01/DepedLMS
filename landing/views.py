from django.contrib import messages
from django.shortcuts import render

from accounts.models import School


def home(request):
    return render(request, "home.html")


def download(request):
    return render(request, "download.html")


def school(request):
    schools = School.objects.order_by("school_name")
    return render(request, "school.html", {"schools": schools})


def about(request):
    return render(request, "about.html")


def contact(request):
    if request.method == "POST":
        # Connect this form to your email service or a Contact model.
        messages.success(request, "Thank you. Your message has been received.")
    return render(request, "contact.html")
