from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db.models import Q
import calendar
from django.utils import timezone

from accounts.models import Principal, School, Student, Teacher, User
from classroom.models import (
    AcademicTerm,
    CalendarEvent,
    Classroom,
    ClassEnrollment,
)
from classroom.notification_services import (
    notify_calendar_event,
    notify_school_announcement,
)
from .models import SchoolAnnouncement

from .forms import (
    AcademicTermForm,
    AdministrationLoginForm,
    DistrictCalendarEventForm,
    PrincipalAccountForm,
    SchoolCalendarEventForm,
    SchoolProfileForm,
    SchoolAnnouncementForm,
    TeacherAccountForm,
)


def _is_supervisor(user):
    return user.is_authenticated and user.role == User.Role.SUPERVISOR

def _is_principal(user):
    return user.is_authenticated and user.role == User.Role.PRINCIPAL


def _administration_redirect(user):
    if user.role == User.Role.SUPERVISOR:
        return redirect("supervisor:dashboard")
    if user.role == User.Role.PRINCIPAL:
        return redirect("supervisor:principal_dashboard")
    return redirect("accounts:login")



def login_view(request):
    if _is_supervisor(request.user) or _is_principal(request.user):
        return _administration_redirect(request.user)

    form = AdministrationLoginForm(request=request, data=request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        auth_login(request, user)
        messages.success(request, f"Welcome back, {user.full_name}.")
        return _administration_redirect(user)

    return render(request, "supervisor/login.html", {"form": form})


@login_required(login_url="supervisor:login")
def dashboard_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    context = {
        "school_count": School.objects.count(),
        "principal_count": Principal.objects.count(),
        "teacher_count": Teacher.objects.count(),
        "student_count": Student.objects.count(),
        "class_count": Classroom.objects.count(),
    }
    return render(request, "supervisor/dashboard.html", context)



@login_required(login_url="supervisor:login")
def principal_dashboard_view(request):
    if not _is_principal(request.user):
        messages.error(request, "You don't have access to the Principal portal.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:login")

    school = principal.school
    context = {
        "school": school,
        "teacher_count": Teacher.objects.filter(school=school).count(),
        "student_count": Student.objects.filter(school=school).count(),
        "class_count": Classroom.objects.filter(teacher__school=school).count(),
        "enrollment_count": ClassEnrollment.objects.filter(
            classroom__teacher__school=school,
            status=ClassEnrollment.Status.APPROVED,
        ).count(),
        "announcement_form": SchoolAnnouncementForm(),
        "school_announcements": SchoolAnnouncement.objects.filter(
            school=school,
        )[:5],
    }
    return render(request, "supervisor/principal_dashboard.html", context)


@login_required(login_url="supervisor:login")
@require_POST
def school_announcement_create_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can post school announcements.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    form = SchoolAnnouncementForm(request.POST)
    if form.is_valid():
        announcement = form.save(commit=False)
        announcement.school = principal.school
        announcement.posted_by = request.user
        announcement.save()
        notify_school_announcement(announcement)
        messages.success(request, "School announcement posted and users notified.")
    else:
        messages.error(request, "Complete the school announcement form.")

    return redirect("supervisor:principal_dashboard")

@login_required(login_url="supervisor:login")
def principal_school_profile_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can update their assigned school profile.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    form = SchoolProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=principal.school,
    )
    if request.method == "POST" and form.is_valid():
        school = form.save()
        messages.success(request, f"{school.school_name} profile was updated.")
        return redirect("supervisor:principal_school_profile")

    return render(
        request,
        "supervisor/principal_school_profile.html",
        {"form": form, "school": principal.school},
    )


@login_required(login_url="supervisor:login")
def teacher_list_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can manage Teacher accounts.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    teachers = Teacher.objects.filter(school=principal.school).select_related(
        "user",
        "school",
    ).prefetch_related("created_classes").order_by("lastname", "firstname")
    return render(
        request,
        "supervisor/teachers.html",
        {"teachers": teachers, "school": principal.school},
    )


@login_required(login_url="supervisor:login")
def teacher_create_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can add Teacher accounts.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    form = TeacherAccountForm(
        request.POST or None,
        school=principal.school,
    )
    if request.method == "POST" and form.is_valid():
        teacher = form.save()
        messages.success(
            request,
            f"Teacher account for {teacher.firstname} {teacher.lastname} was created.",
        )
        return redirect("supervisor:teachers")

    return render(
        request,
        "supervisor/teacher_form.html",
        {"form": form, "school": principal.school},
    )


@login_required(login_url="supervisor:login")
def principal_list_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "Only the District Supervisor can manage Principal accounts.")
        return _administration_redirect(request.user)

    principals = Principal.objects.select_related("user", "school").order_by(
        "lastname",
        "firstname",
    )
    return render(
        request,
        "supervisor/principals.html",
        {"principals": principals},
    )


@login_required(login_url="supervisor:login")
def principal_create_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "Only the District Supervisor can add Principal accounts.")
        return _administration_redirect(request.user)

    form = PrincipalAccountForm(request.POST or None)
    has_available_schools = School.objects.filter(principals__isnull=True).exists()
    if request.method == "POST" and form.is_valid():
        principal = form.save()
        messages.success(
            request,
            f"Principal account for {principal.firstname} {principal.lastname} was created.",
        )
        return redirect("supervisor:principals")

    return render(
        request,
        "supervisor/principal_form.html",
        {
            "form": form,
            "has_schools": has_available_schools,
        },
    )



@login_required(login_url="supervisor:login")
def school_list_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    schools = School.objects.select_related().prefetch_related("principals").order_by(
        "school_name"
    )
    return render(request, "supervisor/schools.html", {"schools": schools})


@login_required(login_url="supervisor:login")
def school_detail_view(request, school_id):
    if not (_is_supervisor(request.user) or _is_principal(request.user)):
        messages.error(request, "You don't have access to this school.")
        return _administration_redirect(request.user)

    school = get_object_or_404(School, pk=school_id)

    # A Principal can only open the school assigned to their profile.
    if _is_principal(request.user):
        principal_profile = getattr(request.user, "principal_profile", None)
        if principal_profile is None or principal_profile.school_id != school.school_id:
            messages.error(request, "You can only view your assigned school.")
            return redirect("supervisor:principal_dashboard")

    principals = Principal.objects.filter(school=school).select_related("user")
    teachers = Teacher.objects.filter(school=school).select_related("user").prefetch_related(
        "created_classes"
    ).order_by("lastname", "firstname")
    students = Student.objects.filter(school=school).select_related("user").order_by(
        "lastname", "firstname"
    )
    classes = Classroom.objects.filter(teacher__school=school).select_related(
        "teacher", "teacher__user"
    ).order_by("teacher__lastname", "subject", "section")

    context = {
        "school": school,
        "principals": principals,
        "teachers": teachers,
        "students": students,
        "classes": classes,
        "principal_count": principals.count(),
        "teacher_count": teachers.count(),
        "student_count": students.count(),
        "class_count": classes.count(),
    }
    return render(request, "supervisor/school_detail.html", context)


@login_required(login_url="supervisor:login")
def student_list_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can view this Student list.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    students = Student.objects.filter(school=principal.school).select_related(
        "user", "school"
    ).order_by("lastname", "firstname")
    return render(
        request,
        "supervisor/students.html",
        {"students": students, "school": principal.school},
    )


@login_required(login_url="supervisor:login")
def class_list_view(request):
    if not _is_principal(request.user):
        messages.error(request, "Only a Principal can view this Class list.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None:
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    classes = Classroom.objects.filter(
        teacher__school=principal.school,
    ).select_related("teacher", "teacher__user").prefetch_related("enrollments")
    return render(
        request,
        "supervisor/classes.html",
        {"classes": classes, "school": principal.school},
    )


@login_required(login_url="supervisor:login")
def school_create_view(request):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    form = SchoolProfileForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        school = form.save(commit=False)
        school.created_by = request.user
        school.save()
        messages.success(request, f"{school.school_name} was added successfully.")
        return redirect("supervisor:schools")

    return render(
        request,
        "supervisor/school_form.html",
        {"form": form, "page_title": "Add School", "submit_label": "Create School"},
    )


@login_required(login_url="supervisor:login")
def school_edit_view(request, school_id):
    if not _is_supervisor(request.user):
        messages.error(request, "You don't have access to the supervisor portal.")
        return redirect("supervisor:login")

    school = get_object_or_404(School, pk=school_id)
    form = SchoolProfileForm(
        request.POST or None,
        request.FILES or None,
        instance=school,
    )
    if request.method == "POST" and form.is_valid():
        school = form.save()
        messages.success(request, f"{school.school_name} was updated successfully.")
        return redirect("supervisor:schools")

    return render(
        request,
        "supervisor/school_form.html",
        {"form": form, "school": school, "page_title": "Edit School", "submit_label": "Save Changes"},
    )


@login_required(login_url="supervisor:login")
def logout_view(request):
    auth_logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("supervisor:login")


# =========================================================
# MONTH CALENDAR HELPER
# =========================================================

def _local_date(date_time):
    if timezone.is_aware(date_time):
        return timezone.localtime(date_time).date()

    return date_time.date()


def _build_calendar_month(request, events):
    today = timezone.localdate()

    try:
        selected_year = int(
            request.GET.get("year", today.year)
        )
        selected_month = int(
            request.GET.get("month", today.month)
        )

        if selected_month < 1 or selected_month > 12:
            raise ValueError

    except (TypeError, ValueError):
        selected_year = today.year
        selected_month = today.month

    month_calendar = calendar.Calendar(
        firstweekday=6
    )

    month_dates = month_calendar.monthdatescalendar(
        selected_year,
        selected_month,
    )

    event_list = list(events)
    calendar_weeks = []

    for week in month_dates:
        calendar_week = []

        for day in week:
            day_events = []

            for event in event_list:
                start_date = _local_date(event.start_at)

                if event.end_at:
                    end_date = _local_date(event.end_at)
                else:
                    end_date = start_date

                if start_date <= day <= end_date:
                    day_events.append(event)

            calendar_week.append({
                "date": day,
                "is_current_month": (
                    day.month == selected_month
                ),
                "is_today": day == today,
                "is_weekend": day.weekday() >= 5,
                "events": day_events,
            })

        calendar_weeks.append(calendar_week)

    if selected_month == 1:
        previous_year = selected_year - 1
        previous_month = 12
    else:
        previous_year = selected_year
        previous_month = selected_month - 1

    if selected_month == 12:
        next_year = selected_year + 1
        next_month = 1
    else:
        next_year = selected_year
        next_month = selected_month + 1

    return {
        "calendar_weeks": calendar_weeks,
        "calendar_month_name": calendar.month_name[
            selected_month
        ],
        "calendar_year": selected_year,
        "previous_year": previous_year,
        "previous_month": previous_month,
        "next_year": next_year,
        "next_month": next_month,
    }

# =========================================================
# DISTRICT CALENDAR
# District Supervisor only
# =========================================================

@login_required(login_url="supervisor:login")
def district_calendar_view(request):
    if not _is_supervisor(request.user):
        messages.error(
            request,
            "Only the District Supervisor can manage the district calendar.",
        )
        return _administration_redirect(request.user)

    supervisor = getattr(
        request.user,
        "supervisor_profile",
        None,
    )

    if supervisor is None:
        messages.error(
            request,
            "Your Supervisor profile was not found.",
        )
        return redirect("supervisor:dashboard")

    editing_event = None
    edit_event_id = request.POST.get("event_id") or request.GET.get("edit_event")
    if edit_event_id:
        editing_event = get_object_or_404(
            CalendarEvent.objects.exclude(status=CalendarEvent.Status.CANCELLED),
            pk=edit_event_id,
            level=CalendarEvent.Level.DISTRICT,
        )

    event_form = DistrictCalendarEventForm(
        request.POST or None,
        request.FILES or None,
        supervisor=supervisor,
        instance=editing_event,
    )
    term_form = AcademicTermForm()

    if request.method == "POST":
        form_type = request.POST.get("form_type")

        # Add an official district event.
        if form_type == "event":
            if event_form.is_valid():
                is_new = event_form.instance.pk is None
                event = event_form.save(commit=False)
                event.level = CalendarEvent.Level.DISTRICT
                if is_new:
                    event.created_by = request.user
                event.school = None
                event.classroom = None
                event.save()

                event_form.save_m2m()

                # An all-schools event does not need selected schools.
                if event.applies_to_all_schools:
                    event.target_schools.clear()

                if event.status == CalendarEvent.Status.PUBLISHED:
                    notify_calendar_event(
                        event,
                        "created" if is_new else "updated",
                    )

                messages.success(
                    request,
                    "The official calendar event was saved.",
                )
                return redirect(
                    "supervisor:district_calendar"
                )

        # Configure one of the three academic terms.
        elif form_type == "term":
            term_form = AcademicTermForm(request.POST)

            if term_form.is_valid():
                term = term_form.save(commit=False)
                term.created_by = request.user
                term.save()

                messages.success(
                    request,
                    f"{term.get_term_display()} was saved.",
                )
                return redirect(
                    "supervisor:district_calendar"
                )

    district_events = (
        CalendarEvent.objects
        .filter(level=CalendarEvent.Level.DISTRICT)
        .prefetch_related("target_schools")
        .select_related("created_by")
        .order_by("start_at")
    )

    academic_terms = AcademicTerm.objects.order_by(
        "school_year",
        "term",
    )

    calendar_context = _build_calendar_month(
        request,
        district_events.filter(status=CalendarEvent.Status.PUBLISHED),
    )

    context = {
        "supervisor": supervisor,
        "event_form": event_form,
        "term_form": term_form,
        "district_events": district_events,
        "academic_terms": academic_terms,
        "editing_event": editing_event,
        **calendar_context,
    }

    return render(
        request,
        "supervisor/district_calendar.html",
        context,
    )

# =========================================================
# SCHOOL CALENDAR
# Principal only
# =========================================================

@login_required(login_url="supervisor:login")
def principal_calendar_view(request):
    if not _is_principal(request.user):
        messages.error(
            request,
            "Only a Principal can manage the school calendar.",
        )
        return _administration_redirect(request.user)

    principal = getattr(
        request.user,
        "principal_profile",
        None,
    )

    if principal is None:
        messages.error(
            request,
            "Your Principal profile is not connected to a school.",
        )
        return redirect(
            "supervisor:principal_dashboard"
        )

    school = principal.school

    editing_event = None
    edit_event_id = request.POST.get("event_id") or request.GET.get("edit_event")
    if edit_event_id:
        editing_event = get_object_or_404(
            CalendarEvent.objects.exclude(status=CalendarEvent.Status.CANCELLED),
            pk=edit_event_id,
            level=CalendarEvent.Level.SCHOOL,
            school=school,
        )

    event_form = SchoolCalendarEventForm(
        request.POST or None,
        request.FILES or None,
        instance=editing_event,
    )

    if request.method == "POST" and event_form.is_valid():
        is_new = event_form.instance.pk is None
        event = event_form.save(commit=False)

        event.level = CalendarEvent.Level.SCHOOL
        event.school = school
        event.classroom = None
        if is_new:
            event.created_by = request.user
        event.applies_to_all_schools = False

        event.save()

        if event.status == CalendarEvent.Status.PUBLISHED:
            notify_calendar_event(
                event,
                "created" if is_new else "updated",
            )

        messages.success(
            request,
            "The school calendar event was saved.",
        )

        return redirect(
            "supervisor:principal_calendar"
        )

    # Official Supervisor events that apply to this school.
    district_events = (
        CalendarEvent.objects
        .filter(
            level=CalendarEvent.Level.DISTRICT,
            status=CalendarEvent.Status.PUBLISHED,
        )
        .filter(
            Q(applies_to_all_schools=True)
            | Q(target_schools=school)
        )
        .distinct()
        .select_related("created_by")
        .order_by("start_at")
    )

    # Events created by the Principal for their own school.
    school_events = (
        CalendarEvent.objects
        .filter(
            level=CalendarEvent.Level.SCHOOL,
            school=school,
        )
        .select_related("created_by")
        .order_by("start_at")
    )

    academic_terms = AcademicTerm.objects.order_by(
        "school_year",
        "term",
    )

    combined_events = (
        list(district_events)
        + list(school_events.filter(status=CalendarEvent.Status.PUBLISHED))
    )

    calendar_context = _build_calendar_month(
        request,
        combined_events,
    )

    context = {
        "principal": principal,
        "school": school,
        "event_form": event_form,
        "district_events": district_events,
        "school_events": school_events,
        "academic_terms": academic_terms,
        "editing_event": editing_event,
        **calendar_context,
    }

    return render(
        request,
        "supervisor/principal_calendar.html",
        context,
    )

# =========================================================
# CANCEL DISTRICT EVENT
# =========================================================

@login_required(login_url="supervisor:login")
@require_POST
def district_calendar_event_cancel_view(
    request,
    event_id,
):
    if not _is_supervisor(request.user):
        messages.error(
            request,
            "Only the District Supervisor can cancel district events.",
        )
        return _administration_redirect(request.user)

    event = get_object_or_404(
        CalendarEvent,
        pk=event_id,
        level=CalendarEvent.Level.DISTRICT,
    )

    event.status = CalendarEvent.Status.CANCELLED
    event.save(update_fields=["status", "updated_at"])
    notify_calendar_event(event, "cancelled")

    messages.success(
        request,
        "The district calendar event was cancelled.",
    )

    return redirect(
        "supervisor:district_calendar"
    )


# =========================================================
# CANCEL SCHOOL EVENT
# =========================================================

@login_required(login_url="supervisor:login")
@require_POST
def principal_calendar_event_cancel_view(
    request,
    event_id,
):
    if not _is_principal(request.user):
        messages.error(
            request,
            "Only a Principal can cancel school events.",
        )
        return _administration_redirect(request.user)

    principal = getattr(
        request.user,
        "principal_profile",
        None,
    )

    if principal is None:
        messages.error(
            request,
            "Your Principal profile was not found.",
        )
        return redirect(
            "supervisor:principal_dashboard"
        )

    event = get_object_or_404(
        CalendarEvent,
        pk=event_id,
        level=CalendarEvent.Level.SCHOOL,
        school=principal.school,
    )

    event.status = CalendarEvent.Status.CANCELLED
    event.save(update_fields=["status", "updated_at"])
    notify_calendar_event(event, "cancelled")

    messages.success(
        request,
        "The school calendar event was cancelled.",
    )

    return redirect(
        "supervisor:principal_calendar"
    )
