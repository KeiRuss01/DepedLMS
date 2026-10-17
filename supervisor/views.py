from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db.models import Q
import calendar
from django.utils import timezone

from accounts.models import Principal, School, Student, Teacher, User
from classroom.models import (
    AcademicTerm,
    ActivitySubmission,
    AttendanceDay,
    CalendarEvent,
    ClassEnrollment,
    Classroom,
    ClassPost,
    GradebookSettings,
    GradeReportSubmission,
    Module,
    ModuleSubmission,
)
from classroom.notification_services import (
    notify_calendar_event,
    notify_school_announcement,
)
from .models import (
    SchoolAnnouncement,
    SchoolReportSubmission,
)

from .forms import (
    AcademicTermForm,
    AdministrationLoginForm,
    DistrictAnnouncementForm,
    DistrictCalendarEventForm,
    PrincipalAccountForm,
    SchoolCalendarEventForm,
    SchoolProfileForm,
    SchoolAnnouncementForm,
    TeacherAccountForm,
)

from .report_services import build_consolidated_learners


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

def _build_school_monitoring(
    schools=None,
    school_year="",
    selected_term="",
):
    """
    Build a read-only monitoring summary for each school.
    """

    if schools is None:
        schools = School.objects.order_by("school_name")

    today = timezone.localdate()
    now = timezone.now()
    monitoring = []

    for school in schools:
        classrooms = Classroom.objects.filter(
            teacher__school=school,
            is_archived=False,
        )

        if school_year:
            classrooms = classrooms.filter(
                school_year=school_year,
            )

        modules = Module.objects.filter(
            classroom__in=classrooms,
            status=Module.Status.PUBLISHED,
        )

        activities = ClassPost.objects.filter(
            classroom__in=classrooms,
            post_type=ClassPost.PostType.ACTIVITY,
            is_published=True,
        )

        module_submissions = ModuleSubmission.objects.filter(
            module__in=modules,
        )

        activity_submissions = ActivitySubmission.objects.filter(
            activity__in=activities,
        )

        pending_review = (
            module_submissions.filter(
                status=ModuleSubmission.Status.SUBMITTED,
            ).count()
            + activity_submissions.filter(
                status=ActivitySubmission.Status.SUBMITTED,
            ).count()
        )

        completed_work = (
            module_submissions.filter(
                status=ModuleSubmission.Status.GRADED,
            ).count()
            + activity_submissions.filter(
                status=ActivitySubmission.Status.GRADED,
            ).count()
        )

        returned_work = (
            module_submissions.filter(
                status=ModuleSubmission.Status.RETURNED,
            ).count()
            + activity_submissions.filter(
                status=ActivitySubmission.Status.RETURNED,
            ).count()
        )

        overdue_work = (
            module_submissions.filter(
                module__due_at__lt=now,
                status__in=[
                    ModuleSubmission.Status.DRAFT,
                    ModuleSubmission.Status.RETURNED,
                ],
            ).count()
            + activity_submissions.filter(
                activity__due_date__lt=now,
                status__in=[
                    ActivitySubmission.Status.DRAFT,
                    ActivitySubmission.Status.RETURNED,
                ],
            ).count()
        )

        attendance_pending = 0

        if today.weekday() < 5:
            attendance_pending = classrooms.exclude(
                attendance_days__date=today,
            ).count()

        gradebook_filter = {}

        if selected_term in {"1", "2", "3"}:
            gradebook_filter[
                f"term_{selected_term}_released"
            ] = True
        else:
            gradebook_filter = {
                "term_1_released": True,
            }

        released_gradebooks = GradebookSettings.objects.filter(
            classroom__in=classrooms,
            **gradebook_filter,
        ).count()

        monitoring.append({
            "school": school,
            "teacher_count": Teacher.objects.filter(
                school=school,
                user__status=User.Status.ACTIVE,
            ).count(),
            "student_count": Student.objects.filter(
                school=school,
                user__status=User.Status.ACTIVE,
            ).count(),
            "class_count": classrooms.count(),
            "module_count": modules.count(),
            "activity_count": activities.count(),
            "pending_review": pending_review,
            "completed_work": completed_work,
            "returned_work": returned_work,
            "overdue_work": overdue_work,
            "attendance_pending": attendance_pending,
            "released_gradebooks": released_gradebooks,
        })

    return monitoring

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
        "school_monitoring": _build_school_monitoring(),
        "district_announcement_form": DistrictAnnouncementForm(),
    }
    return render(request, "supervisor/dashboard.html", context)

@login_required(login_url="supervisor:login")
def district_performance_report_view(request):
    if not _is_supervisor(request.user):
        messages.error(
            request,
            "Only the District Supervisor can open District Reports.",
        )
        return _administration_redirect(request.user)

    schools = School.objects.order_by(
        "school_name",
    )

    school_years = (
        Classroom.objects.filter(
            is_archived=False,
        )
        .values_list("school_year", flat=True)
        .distinct()
        .order_by("-school_year")
    )

    selected_year = request.GET.get(
        "school_year",
        "",
    )

    if not selected_year:
        selected_year = school_years.first() or ""

    selected_school = request.GET.get(
        "school",
        "",
    )

    selected_status = request.GET.get(
        "status",
        "",
    )

    if selected_status not in {
        "",
        "missing",
        SchoolReportSubmission.Status.SUBMITTED,
        SchoolReportSubmission.Status.RETURNED,
        SchoolReportSubmission.Status.ACKNOWLEDGED,
    }:
        selected_status = ""

    submissions = (
        SchoolReportSubmission.objects.filter(
            school_year=selected_year,
        )
        .select_related(
            "school",
            "submitted_by",
            "reviewed_by",
        )
    )

    submission_map = {
        submission.school_id: submission
        for submission in submissions
    }

    report_rows = []

    for school in schools:
        submission = submission_map.get(
            school.pk,
        )

        row_status = (
            submission.status
            if submission
            else "missing"
        )

        if (
            selected_school
            and str(school.pk) != selected_school
        ):
            continue

        if (
            selected_status
            and row_status != selected_status
        ):
            continue

        report_rows.append({
            "school": school,
            "submission": submission,
            "status": row_status,
        })

    school_count = schools.count()

    submitted_count = submissions.filter(
        status=SchoolReportSubmission.Status.SUBMITTED,
    ).count()

    returned_count = submissions.filter(
        status=SchoolReportSubmission.Status.RETURNED,
    ).count()

    acknowledged_count = submissions.filter(
        status=SchoolReportSubmission.Status.ACKNOWLEDGED,
    ).count()

    missing_count = school_count - submissions.count()

    return render(
        request,
        "supervisor/district_performance_report.html",
        {
            "schools": schools,
            "school_years": school_years,
            "report_rows": report_rows,
            "selected_year": selected_year,
            "selected_school": selected_school,
            "selected_status": selected_status,
            "school_count": school_count,
            "submitted_count": submitted_count,
            "returned_count": returned_count,
            "acknowledged_count": acknowledged_count,
            "missing_count": missing_count,
        },
    )

@login_required(login_url="supervisor:login")
def district_school_report_detail_view(
    request,
    report_id,
):
    if not _is_supervisor(request.user):
        messages.error(
            request,
            "Only the District Supervisor can review school reports.",
        )
        return _administration_redirect(request.user)

    report = get_object_or_404(
        SchoolReportSubmission.objects.select_related(
            "school",
            "submitted_by",
            "reviewed_by",
        ),
        pk=report_id,
    )

    snapshot = report.snapshot or {}

    return render(
        request,
        "supervisor/district_school_report_detail.html",
        {
            "report": report,
            "snapshot": snapshot,
            "class_reports": snapshot.get(
                "class_reports",
                [],
            ),
            "learner_reports": snapshot.get(
                "learner_reports",
                [],
            ),
        },
    )

@login_required(login_url="supervisor:login")
@require_POST
@transaction.atomic
def district_school_report_review_view(
    request,
    report_id,
):
    if not _is_supervisor(request.user):
        messages.error(
            request,
            "Only the District Supervisor can review school reports.",
        )
        return _administration_redirect(request.user)

    report = get_object_or_404(
        SchoolReportSubmission,
        pk=report_id,
    )

    if (
        report.status
        != SchoolReportSubmission.Status.SUBMITTED
    ):
        messages.error(
            request,
            "Only submitted school reports can be reviewed.",
        )

        return redirect(
            "supervisor:district_school_report_detail",
            report_id=report.pk,
        )

    action = request.POST.get(
        "action",
        "",
    )

    comment = request.POST.get(
        "district_comment",
        "",
    ).strip()

    if action == "acknowledge":
        report.status = (
            SchoolReportSubmission.Status.ACKNOWLEDGED
        )

        success_message = (
            "The school report was acknowledged."
        )

    elif action == "return":
        if not comment:
            messages.error(
                request,
                "Enter a correction comment before returning the report.",
            )

            return redirect(
                "supervisor:district_school_report_detail",
                report_id=report.pk,
            )

        report.status = (
            SchoolReportSubmission.Status.RETURNED
        )

        success_message = (
            "The school report was returned to the Principal."
        )

    else:
        messages.error(
            request,
            "Invalid report action.",
        )

        return redirect(
            "supervisor:district_school_report_detail",
            report_id=report.pk,
        )

    report.district_comment = comment
    report.reviewed_by = request.user
    report.reviewed_at = timezone.now()

    report.save(
        update_fields=[
            "status",
            "district_comment",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )

    messages.success(
        request,
        success_message,
    )

    return redirect(
        "supervisor:district_school_report_detail",
        report_id=report.pk,
    )

@login_required(login_url="supervisor:login")
@require_POST
@transaction.atomic
def district_announcement_create_view(request):
    if not _is_supervisor(request.user):
        messages.error(
            request,
            "Only the District Supervisor can post district announcements.",
        )
        return _administration_redirect(request.user)

    form = DistrictAnnouncementForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Complete the district announcement form.")
        return redirect("supervisor:dashboard")

    schools = (
        School.objects.all()
        if form.cleaned_data["all_schools"]
        else form.cleaned_data["target_schools"]
    )

    created_count = 0
    for school in schools:
        announcement = SchoolAnnouncement.objects.create(
            school=school,
            posted_by=request.user,
            title=form.cleaned_data["title"],
            content=form.cleaned_data["content"],
            priority=form.cleaned_data["priority"],
        )
        notify_school_announcement(announcement)
        created_count += 1

    messages.success(
        request,
        f"District announcement posted to {created_count} school(s).",
    )
    return redirect("supervisor:dashboard")



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
def principal_grade_reports_view(request):
    if not _is_principal(request.user):
        messages.error(
            request,
            "Only the Principal can open school reports.",
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
        return redirect("supervisor:principal_dashboard")

    school = principal.school

    all_classrooms = Classroom.objects.filter(
        teacher__school=school,
        is_archived=False,
    ).select_related(
        "teacher",
        "final_grade_report",
    )

    school_years = (
        all_classrooms
        .values_list("school_year", flat=True)
        .distinct()
        .order_by("-school_year")
    )

    grade_levels = (
        all_classrooms
        .values_list("grade_level", flat=True)
        .distinct()
        .order_by("grade_level")
    )

    sections = (
        all_classrooms
        .values_list("section", flat=True)
        .distinct()
        .order_by("section")
    )

    selected_year = request.GET.get(
        "school_year",
        "",
    )

    selected_grade = request.GET.get(
        "grade_level",
        "",
    )

    selected_section = request.GET.get(
        "section",
        "",
    )

    selected_status = request.GET.get(
        "status",
        "",
    )

    allowed_statuses = {
        "",
        "missing",
        GradeReportSubmission.Status.SUBMITTED,
        GradeReportSubmission.Status.RETURNED,
        GradeReportSubmission.Status.APPROVED,
    }

    if selected_status not in allowed_statuses:
        selected_status = ""

    classrooms = all_classrooms

    if selected_year:
        classrooms = classrooms.filter(
            school_year=selected_year,
        )

    if selected_grade:
        classrooms = classrooms.filter(
            grade_level=selected_grade,
        )

    if selected_section:
        classrooms = classrooms.filter(
            section=selected_section,
        )

    classrooms = list(
        classrooms.order_by(
            "grade_level",
            "section",
            "subject",
        )
    )

    class_rows = []

    for classroom in classrooms:
        report = getattr(
            classroom,
            "final_grade_report",
            None,
        )

        row_status = (
            report.status
            if report
            else "missing"
        )

        if (
            selected_status
            and row_status != selected_status
        ):
            continue

        class_rows.append({
            "classroom": classroom,
            "report": report,
            "status": row_status,
        })

    classroom_ids = [
        classroom.pk
        for classroom in classrooms
    ]

    report_counts = GradeReportSubmission.objects.filter(
        classroom_id__in=classroom_ids,
    )

    expected_count = len(classroom_ids)

    submitted_count = report_counts.filter(
        status=GradeReportSubmission.Status.SUBMITTED,
    ).count()

    returned_count = report_counts.filter(
        status=GradeReportSubmission.Status.RETURNED,
    ).count()

    approved_count = report_counts.filter(
        status=GradeReportSubmission.Status.APPROVED,
    ).count()

    missing_count = (
        expected_count - report_counts.count()
    )

    approved_reports = (
        GradeReportSubmission.objects.filter(
            classroom_id__in=classroom_ids,
            status=GradeReportSubmission.Status.APPROVED,
        )
        .select_related(
            "classroom",
            "classroom__teacher",
        )
        .order_by(
            "classroom__grade_level",
            "classroom__section",
            "classroom__subject",
        )
    )

    learner_reports = build_consolidated_learners(
        approved_reports
    )

    selected_tab = request.GET.get(
        "tab",
        "submissions",
    )

    if selected_tab not in {
        "submissions",
        "learners",
    }:
        selected_tab = "submissions"

    return render(
        request,
        "supervisor/principal_grade_reports.html",
        {
            "school": school,
            "class_rows": class_rows,
            "learner_reports": learner_reports,
            "school_years": school_years,
            "grade_levels": grade_levels,
            "sections": sections,
            "selected_year": selected_year,
            "selected_grade": selected_grade,
            "selected_section": selected_section,
            "selected_status": selected_status,
            "selected_tab": selected_tab,
            "expected_count": expected_count,
            "submitted_count": submitted_count,
            "returned_count": returned_count,
            "approved_count": approved_count,
            "missing_count": missing_count,
        },
    )

@login_required(login_url="supervisor:login")
def principal_grade_report_detail_view(
    request,
    report_id,
):
    if not _is_principal(request.user):
        messages.error(
            request,
            "Only the Principal can review school reports.",
        )
        return _administration_redirect(request.user)

    principal = getattr(
        request.user,
        "principal_profile",
        None,
    )

    if principal is None:
        return redirect(
            "supervisor:principal_dashboard"
        )

    report = get_object_or_404(
        GradeReportSubmission.objects.select_related(
            "classroom",
            "classroom__teacher",
            "submitted_by",
            "reviewed_by",
        ),
        pk=report_id,
        classroom__teacher__school=principal.school,
    )

    snapshot = report.snapshot or {}

    return render(
        request,
        "supervisor/principal_grade_report_detail.html",
        {
            "school": principal.school,
            "report": report,
            "snapshot": snapshot,
            "learners": snapshot.get(
                "learners",
                [],
            ),
        },
    )

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
    if not (_is_principal(request.user) or _is_supervisor(request.user)):
        messages.error(request, "You don't have access to the Teacher list.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    schools = School.objects.order_by("school_name") if _is_supervisor(request.user) else []
    selected_school_id = request.GET.get("school") if _is_supervisor(request.user) else None
    school = principal.school if principal else None

    if _is_supervisor(request.user) and selected_school_id:
        school = schools.filter(pk=selected_school_id).first()

    if _is_supervisor(request.user):
        teachers = Teacher.objects.filter(school=school) if school else Teacher.objects.none()
    else:
        teachers = Teacher.objects.filter(school=school)

    teachers = teachers.select_related(
        "user",
        "school",
    ).prefetch_related("created_classes").order_by("lastname", "firstname")
    return render(
        request,
        "supervisor/teachers.html",
        {
            "teachers": teachers,
            "school": school,
            "schools": schools,
            "selected_school_id": selected_school_id,
            "is_supervisor_view": _is_supervisor(request.user),
        },
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
@require_POST
@transaction.atomic
def principal_grade_report_review_view(
    request,
    report_id,
):
    if not _is_principal(request.user):
        messages.error(
            request,
            "Only the Principal can review school reports.",
        )
        return _administration_redirect(request.user)

    principal = getattr(
        request.user,
        "principal_profile",
        None,
    )

    if principal is None:
        return redirect(
            "supervisor:principal_dashboard"
        )

    report = get_object_or_404(
        GradeReportSubmission.objects.select_related(
            "classroom",
        ),
        pk=report_id,
        classroom__teacher__school=principal.school,
    )

    if (
        report.status
        != GradeReportSubmission.Status.SUBMITTED
    ):
        messages.error(
            request,
            "Only submitted reports can be reviewed.",
        )
        return redirect(
            "supervisor:principal_grade_report_detail",
            report_id=report.pk,
        )

    action = request.POST.get(
        "action",
        "",
    )

    comment = request.POST.get(
        "principal_comment",
        "",
    ).strip()

    if action == "approve":
        report.status = (
            GradeReportSubmission.Status.APPROVED
        )

        success_message = (
            "The final class report was approved."
        )

    elif action == "return":
        if not comment:
            messages.error(
                request,
                "Enter a correction comment before returning the report.",
            )
            return redirect(
                "supervisor:principal_grade_report_detail",
                report_id=report.pk,
            )

        report.status = (
            GradeReportSubmission.Status.RETURNED
        )

        success_message = (
            "The report was returned to the Teacher for correction."
        )

    else:
        messages.error(
            request,
            "Invalid report action.",
        )
        return redirect(
            "supervisor:principal_grade_report_detail",
            report_id=report.pk,
        )

    report.principal_comment = comment
    report.reviewed_by = request.user
    report.reviewed_at = timezone.now()

    report.save(
        update_fields=[
            "status",
            "principal_comment",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )

    messages.success(
        request,
        success_message,
    )

    return redirect(
        "supervisor:principal_grade_report_detail",
        report_id=report.pk,
    )

@login_required(login_url="supervisor:login")
def student_list_view(request):
    if not (_is_principal(request.user) or _is_supervisor(request.user)):
        messages.error(request, "You don't have access to the Student list.")
        return _administration_redirect(request.user)

    principal = getattr(request.user, "principal_profile", None)
    if principal is None and _is_principal(request.user):
        messages.error(request, "Your Principal profile is not connected to a school.")
        return redirect("supervisor:principal_dashboard")

    schools = School.objects.order_by("school_name") if _is_supervisor(request.user) else []
    selected_school_id = request.GET.get("school") if _is_supervisor(request.user) else None
    school = principal.school if principal else None

    if _is_supervisor(request.user) and selected_school_id:
        school = schools.filter(pk=selected_school_id).first()

    if _is_supervisor(request.user):
        students = Student.objects.filter(school=school) if school else Student.objects.none()
    else:
        students = Student.objects.filter(school=school)

    students = students.select_related(
        "user", "school"
    ).order_by("lastname", "firstname")
    return render(
        request,
        "supervisor/students.html",
        {
            "students": students,
            "school": school,
            "schools": schools,
            "selected_school_id": selected_school_id,
            "is_supervisor_view": _is_supervisor(request.user),
        },
    )


@login_required(login_url="supervisor:login")
def teacher_detail_view(request, teacher_id):
    if not (_is_supervisor(request.user) or _is_principal(request.user)):
        return _administration_redirect(request.user)

    teacher = get_object_or_404(
        Teacher.objects.select_related("user", "school").prefetch_related("created_classes"),
        pk=teacher_id,
    )

    if _is_principal(request.user):
        principal = getattr(request.user, "principal_profile", None)
        if principal is None or principal.school_id != teacher.school_id:
            raise PermissionDenied("You can only view Teachers in your school.")

    return render(
        request,
        "supervisor/teacher_detail.html",
        {"teacher": teacher},
    )


@login_required(login_url="supervisor:login")
def student_detail_view(request, student_id):
    if not (_is_supervisor(request.user) or _is_principal(request.user)):
        return _administration_redirect(request.user)

    student = get_object_or_404(
        Student.objects.select_related("user", "school", "parent", "parent__user"),
        pk=student_id,
    )

    if _is_principal(request.user):
        principal = getattr(request.user, "principal_profile", None)
        if principal is None or principal.school_id != student.school_id:
            raise PermissionDenied("You can only view Students in your school.")

    enrollments = ClassEnrollment.objects.filter(
        student=student,
        status=ClassEnrollment.Status.APPROVED,
    ).select_related(
        "classroom",
        "classroom__teacher",
        "classroom__teacher__user",
    ).order_by("classroom__subject", "classroom__section")

    return render(
        request,
        "supervisor/student_detail.html",
        {
            "student": student,
            "enrollments": enrollments,
        },
    )


@login_required(login_url="supervisor:login")
@require_POST
def account_status_view(request, user_id):
    """Allow the District Supervisor to change managed account status."""

    if not _is_supervisor(request.user):
        messages.error(
            request,
            "Only the District Supervisor can change account status.",
        )
        return _administration_redirect(request.user)

    target = get_object_or_404(User, pk=user_id)

    managed_roles = {
        User.Role.PRINCIPAL,
        User.Role.TEACHER,
        User.Role.STUDENT,
    }

    if (
        target.role not in managed_roles
        or target.pk == request.user.pk
    ):
        messages.error(request, "This account cannot be changed here.")
        return redirect(request.POST.get("next") or "supervisor:dashboard")

    new_status = request.POST.get("status")
    valid_statuses = {
        User.Status.ACTIVE,
        User.Status.INACTIVE,
        User.Status.SUSPENDED,
    }

    if new_status not in valid_statuses:
        messages.error(request, "Select a valid account status.")
        return redirect(request.POST.get("next") or "supervisor:dashboard")

    target.status = new_status
    target.save(update_fields=["status", "updated_at"])

    messages.success(
        request,
        f"{target.email} is now {target.get_status_display()}.",
    )
    return redirect(request.POST.get("next") or "supervisor:dashboard")


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
