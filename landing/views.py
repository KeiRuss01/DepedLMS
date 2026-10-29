from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

import json
from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import DeviceRegistry

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


def service_worker(request):
    response = render(
        request,
        "pwa/service-worker.js",
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def offline(request):
    return render(request, "pwa/offline.html")


def download(request):
    return render(request, "download.html")

def offline_module_editor(request):
    return render(request, "pwa/offline_module_editor.html")

def school(request):
    schools = School.objects.order_by("school_name")
    return render(request, "school.html", {"schools": schools})

def offline_modules(request):
    return render(request, "pwa/offline_modules.html")

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

def offline_attendance(request):
    return render(
        request,
        "pwa/offline_attendance.html",
    )

def offline_grades(request):
    return render(
        request,
        "pwa/offline_grades.html",
    )

@login_required(login_url="accounts:login")
@require_POST
def register_device(request):
    try:
        payload = json.loads(request.body or b"{}")

        device_id = UUID(
            str(payload.get("device_id", "")).strip()
        )

        device_name = str(
            payload.get("device_name", "")
        ).strip()[:150]

        device_type = str(
            payload.get("device_type", "")
        ).strip().lower()

        browser = str(
            payload.get("browser", "")
        ).strip()[:100]

    except (
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ):
        return JsonResponse(
            {"error": "The device information is invalid."},
            status=400,
        )

    if device_type not in DeviceRegistry.DeviceType.values:
        return JsonResponse(
            {"error": "The device type is invalid."},
            status=400,
        )

    existing_device = DeviceRegistry.objects.filter(
        device_id=device_id
    ).first()

    if (
        existing_device
        and existing_device.user_id != request.user.pk
    ):
        return JsonResponse(
            {
                "error": (
                    "This device identity belongs to another account. "
                    "Clear the application's site data before changing users."
                )
            },
            status=409,
        )

    device, created = DeviceRegistry.objects.update_or_create(
        device_id=device_id,
        defaults={
            "user": request.user,
            "device_name": device_name or "Unnamed device",
            "device_type": device_type,
            "browser": browser,
            "last_sync_at": timezone.now(),
            "is_active": True,
        },
    )

    return JsonResponse(
        {
            "registered": True,
            "created": created,
            "device": {
                "device_id": str(device.device_id),
                "device_name": device.device_name,
                "device_type": device.device_type,
                "browser": device.browser,
                "last_sync_at": (
                    device.last_sync_at.isoformat()
                    if device.last_sync_at
                    else None
                ),
                "is_active": device.is_active,
            },
            "account": {
                "user_id": request.user.pk,
                "full_name": request.user.full_name,
                "role": request.user.role,
                "role_label": request.user.get_role_display(),
            },
        },
        status=201 if created else 200,
    )
