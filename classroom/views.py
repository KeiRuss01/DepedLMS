from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.models import ParentStudentLink, Student, User

from .forms import (
    AnnouncementForm,
    ClassCalendarEventForm,
    ClassPostForm,
    ClassroomForm,
    CommentForm,
    InviteStudentForm,
    JoinClassForm,
    StudentLinkRequestForm,
)
from .models import Announcement, CalendarEvent, Classroom, ClassEnrollment

from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import date, timedelta
import calendar as month_calendar
import json

from supervisor.models import SchoolAnnouncement
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import (
    ClassPost,
    Comment,
    Module,
    ModuleAnswerSection,
    SectionQuestion,
    ModuleSubmission,
    SubmissionExtraPage,
    SectionResponse,
    SectionAnswer,
    SubmissionAttachment,
)
from .module_validators import validate_answer_file

from .module_forms import (
    ModuleCreateForm,
    ModuleScoreForm,
    AnswerSectionForm,
    SectionQuestionFormSet,
    SectionResponseForm,
    SectionGradeForm,
    SubmissionGradeForm,
)
from .module_pdf_processor import build_student_pdf
from .submission_pdf import build_final_submission_pdf
from .notification_services import (
    notify_attendance_record,
    notify_calendar_event,
    notify_class_announcement,
    notify_join_request,
    notify_module_published,
    notify_submission,
    notify_submission_feedback,
    notify_term_grade_released,
)
from .gradebook import (
    build_released_student_summary,
    build_summary,
    build_term_record,
    next_item_position,
    sync_module_grade_item,
    sync_module_grade_score,
)
from .gradebook_forms import GradeItemForm, GradebookSettingsForm
from .models import (
    AttendanceDay,
    AttendanceRecord,
    GradeItem,
    GradeScore,
    GradebookSettings,
)
from .attendance_summary import (
    build_parent_attendance,
    parse_month,
)
from .stream_posts import (
    sync_announcement_post,
    sync_module_post,
)


@login_required(login_url="accounts:login")
def dashboard_view(request):
    user = request.user

    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)

        if teacher is None:
            messages.error(request, "Your Teacher profile was not found.")
            return redirect("accounts:login")

        active_classrooms = Classroom.objects.filter(
            teacher=teacher,
            is_archived=False,
        )
        classrooms = active_classrooms[:3]

        join_requests = ClassEnrollment.objects.filter(
            classroom__teacher=teacher,
            status=ClassEnrollment.Status.PENDING_TEACHER,
        ).select_related(
            "classroom",
            "student",
            "student__user",
        )[:5]

        today = timezone.localdate()
        today_modules = Module.objects.filter(
            classroom__teacher=teacher,
            classroom__is_archived=False,
            status=Module.Status.PUBLISHED,
            due_at__date=today,
        ).select_related("classroom").order_by("due_at")[:5]

        attendance_pending_classrooms = []
        if today.weekday() < 5:
            recorded_class_ids = AttendanceDay.objects.filter(
                classroom__teacher=teacher,
                date=today,
            ).values_list("classroom_id", flat=True)
            attendance_pending_classrooms = active_classrooms.exclude(
                class_id__in=recorded_class_ids,
            )[:5]

        submissions_to_review = ModuleSubmission.objects.filter(
            module__classroom__teacher=teacher,
            module__classroom__is_archived=False,
            status=ModuleSubmission.Status.SUBMITTED,
        ).select_related(
            "module",
            "module__classroom",
            "student",
            "student__user",
        ).order_by("submitted_at", "updated_at")[:5]

        return render(
            request,
            "classroom/teacher_dashboard.html",
            {
                "classrooms": classrooms,
                "join_requests": join_requests,
                "today_modules": today_modules,
                "attendance_pending_classrooms": attendance_pending_classrooms,
                "submissions_to_review": submissions_to_review,
                "today": today,
            },
        )

    if user.role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)

        if student is None:
            messages.error(request, "Your Student profile was not found.")
            return redirect("accounts:login")

        approved_enrollments = ClassEnrollment.objects.filter(
            student=student,
            status=ClassEnrollment.Status.APPROVED,
            classroom__is_archived=False,
        ).select_related(
            "classroom",
            "classroom__teacher",
        )
        enrollments = approved_enrollments[:3]
        enrolled_class_ids = approved_enrollments.values_list(
            "classroom_id",
            flat=True,
        )

        invitations = ClassEnrollment.objects.filter(
            student=student,
            status=ClassEnrollment.Status.PENDING_STUDENT,
        ).select_related(
            "classroom",
            "classroom__teacher",
        )

        parent_requests = ParentStudentLink.objects.filter(
            student=student,
            status=ParentStudentLink.Status.PENDING,
        ).select_related(
            "parent",
            "parent__user",
        )

        now = timezone.now()
        finished_module_ids = ModuleSubmission.objects.filter(
            student=student,
            status__in=[
                ModuleSubmission.Status.SUBMITTED,
                ModuleSubmission.Status.GRADED,
            ],
        ).values_list("module_id", flat=True)
        available_modules = Module.objects.filter(
            classroom_id__in=enrolled_class_ids,
            classroom__is_archived=False,
            status=Module.Status.PUBLISHED,
        ).exclude(
            module_id__in=finished_module_ids,
        ).select_related("classroom")
        due_soon = available_modules.filter(
            due_at__isnull=False,
            due_at__gte=now,
        ).order_by("due_at")[:5]
        continue_module = due_soon.first()
        if continue_module is None:
            continue_module = available_modules.order_by(
                "-published_at",
                "-created_at",
            ).first()

        latest_announcements = Announcement.objects.filter(
            classroom_id__in=enrolled_class_ids,
            classroom__is_archived=False,
        ).select_related(
            "classroom",
            "posted_by",
        ).order_by("-created_at")[:3]

        return render(
            request,
            "classroom/student_dashboard.html",
            {
                "enrollments": enrollments,
                "invitations": invitations,
                "parent_requests": parent_requests,
                "continue_module": continue_module,
                "due_soon": due_soon,
                "latest_announcements": latest_announcements,
            },
        )

    if user.role == User.Role.PARENT:
        parent = getattr(user, "parent_profile", None)

        if parent is None:
            messages.error(request, "Your Parent profile was not found.")
            return redirect("accounts:login")

        linked_students = ParentStudentLink.objects.filter(
            parent=parent,
            status=ParentStudentLink.Status.APPROVED,
        ).select_related(
            "student",
            "student__user",
            "student__school",
        )

        selected_learner_id = request.GET.get("learner")

        selected_link = linked_students.filter(
            student_id=selected_learner_id,
        ).first()

        if selected_link is None:
            selected_link = linked_students.first()

        linked_student = (
            selected_link.student
            if selected_link
            else None
        )

        weekly_tasks = []
        attention_tasks = []
        attendance_alerts = []
        latest_update = None
        latest_update_kind = ""

        if linked_student:
            tasks = _build_student_module_tasks(linked_student)

            weekly_tasks = [
                task
                for task in tasks
                if task["is_due_soon"]
            ][:3]

            attention_tasks = [
                task
                for task in tasks
                if task["is_overdue"]
                or task["status"] == "returned"
            ][:3]

            attendance_alerts = AttendanceRecord.objects.filter(
                student=linked_student,
                attendance_day__date__gte=(
                    timezone.localdate() - timedelta(days=30)
                ),
                status__in=[
                    AttendanceRecord.Status.ABSENT,
                    AttendanceRecord.Status.LATE,
                ],
            ).select_related(
                "attendance_day",
                "attendance_day__classroom",
            ).order_by(
                "-attendance_day__date"
            )[:3]

            classroom_ids = ClassEnrollment.objects.filter(
                student=linked_student,
                status=ClassEnrollment.Status.APPROVED,
                classroom__is_archived=False,
            ).values_list(
                "classroom_id",
                flat=True,
            )

            class_update = Announcement.objects.filter(
                classroom_id__in=classroom_ids,
            ).select_related(
                "classroom",
            ).order_by(
                "-created_at"
            ).first()

            school_update = SchoolAnnouncement.objects.filter(
                school=linked_student.school,
            ).order_by(
                "-created_at"
            ).first()

            available_updates = [
                update
                for update in [class_update, school_update]
                if update is not None
            ]

            if available_updates:
                latest_update = max(
                    available_updates,
                    key=lambda update: update.created_at,
                )

                latest_update_kind = (
                    "School"
                    if isinstance(latest_update, SchoolAnnouncement)
                    else "Class"
                )

        return render(
            request,
            "classroom/parent_dashboard.html",
            {
                "linked_students": linked_students,
                "linked_student": linked_student,
                "weekly_tasks": weekly_tasks,
                "attention_tasks": attention_tasks,
                "attendance_alerts": attendance_alerts,
                "latest_update": latest_update,
                "latest_update_kind": latest_update_kind,
            },
        )

    if user.role == User.Role.SUPERVISOR:
        return redirect("supervisor:dashboard")

    if user.role == User.Role.PRINCIPAL:
        return redirect("supervisor:principal_dashboard")

    messages.error(request, "Your account does not have a valid role.")
    return redirect("accounts:login")


@login_required(login_url="accounts:login")
def classes_view(request):
    user = request.user

    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)

        if teacher is None:
            messages.error(request, "Your Teacher profile was not found.")
            return redirect("classroom:dashboard")

        active_classes = Classroom.objects.filter(
            teacher=teacher,
            is_archived=False,
        )
        archived_classes = Classroom.objects.filter(
            teacher=teacher,
            is_archived=True,
        )
        join_requests = ClassEnrollment.objects.filter(
            classroom__teacher=teacher,
            status=ClassEnrollment.Status.PENDING_TEACHER,
        ).select_related(
            "classroom",
            "student",
            "student__user",
        )

        return render(
            request,
            "classroom/classes.html",
            {
                "active_classes": active_classes,
                "archived_classes": archived_classes,
                "join_requests": join_requests,
            },
        )

    if user.role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)

        if student is None:
            messages.error(request, "Your Student profile was not found.")
            return redirect("classroom:dashboard")

        enrollments = ClassEnrollment.objects.filter(
            student=student,
            status=ClassEnrollment.Status.APPROVED,
            classroom__is_archived=False,
        ).select_related(
            "classroom",
            "classroom__teacher",
        )
        invitations = ClassEnrollment.objects.filter(
            student=student,
            status=ClassEnrollment.Status.PENDING_STUDENT,
        ).select_related(
            "classroom",
            "classroom__teacher",
        )

        pending_requests = ClassEnrollment.objects.filter(
            student=student,
            status=ClassEnrollment.Status.PENDING_TEACHER,
        ).select_related(
            "classroom",
            "classroom__teacher",
        )

        return render(
            request,
            "classroom/classes.html",
            {
                "enrollments": enrollments,
                "invitations": invitations,
                "pending_requests": pending_requests,
            },
        )

    if user.role == User.Role.PARENT:
        parent = getattr(user, "parent_profile", None)
        linked_students = ParentStudentLink.objects.none()

        if parent:
            linked_students = ParentStudentLink.objects.filter(
                parent=parent,
                status=ParentStudentLink.Status.APPROVED,
            ).select_related(
                "student",
                "student__user",
            )

        selected_link = None
        selected_student_id = request.GET.get("student")

        if selected_student_id:
            selected_link = linked_students.filter(
                student_id=selected_student_id,
            ).first()

        if selected_link is None:
            selected_link = linked_students.first()

        linked_student = selected_link.student if selected_link else None
        enrollments = ClassEnrollment.objects.none()

        if linked_student:
            enrollments = ClassEnrollment.objects.filter(
                student=linked_student,
                status=ClassEnrollment.Status.APPROVED,
                classroom__is_archived=False,
            ).select_related(
                "classroom",
                "classroom__teacher",
            )

        return render(
            request,
            "classroom/classes.html",
            {
                "linked_student": linked_student,
                "linked_students": linked_students,
                "enrollments": enrollments,
            },
        )

    if user.role == User.Role.SUPERVISOR:
        return redirect("supervisor:dashboard")

    if user.role == User.Role.PRINCIPAL:
        return redirect("supervisor:principal_dashboard")

    return redirect("accounts:login")


@login_required(login_url="accounts:login")
def create_class_view(request):
    if request.user.role != User.Role.TEACHER:
        messages.error(request, "Only Teachers can create classes.")
        return redirect("classroom:dashboard")

    teacher = getattr(request.user, "teacher_profile", None)

    if teacher is None:
        messages.error(request, "Your Teacher profile was not found.")
        return redirect("classroom:dashboard")

    form = ClassroomForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        classroom = form.save(commit=False)

        # The logged-in Teacher automatically owns the class.
        classroom.teacher = teacher
        classroom.save()

        messages.success(
            request,
            f"{classroom.class_name} was created successfully.",
        )

        return redirect(
            "classroom:class_detail",
            classroom_id=classroom.class_id,
        )

    return render(
        request,
        "classroom/create_class.html",
        {
            "form": form,
        },
    )


@login_required(login_url="accounts:login")
def class_detail_view(request, classroom_id):
    if request.user.role != User.Role.TEACHER:
        messages.error(request, "Only Teachers can manage this page.")
        return redirect("classroom:dashboard")

    teacher = getattr(request.user, "teacher_profile", None)

    if teacher is None:
        messages.error(request, "Your Teacher profile was not found.")
        return redirect("classroom:dashboard")

    # A Teacher can only manage a class they created.
    classroom = get_object_or_404(
        Classroom,
        class_id=classroom_id,
        teacher=teacher,
    )

    approved_students = classroom.enrollments.filter(
        status=ClassEnrollment.Status.APPROVED,
    ).select_related(
        "student",
        "student__user",
    )

    join_requests = classroom.enrollments.filter(
        status=ClassEnrollment.Status.PENDING_TEACHER,
    ).select_related(
        "student",
        "student__user",
    )

    pending_invitations = classroom.enrollments.filter(
        status=ClassEnrollment.Status.PENDING_STUDENT,
    ).select_related(
        "student",
        "student__user",
    )

    invite_form = InviteStudentForm()

    return render(
        request,
        "classroom/class_detail.html",
        {
            "classroom": classroom,
            "approved_students": approved_students,
            "join_requests": join_requests,
            "pending_invitations": pending_invitations,
            "invite_form": invite_form,
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def invite_student_view(request, classroom_id):
    if request.user.role != User.Role.TEACHER:
        messages.error(request, "Only Teachers can invite Students.")
        return redirect("classroom:dashboard")

    teacher = getattr(request.user, "teacher_profile", None)

    if teacher is None:
        messages.error(request, "Your Teacher profile was not found.")
        return redirect("classroom:dashboard")

    classroom = get_object_or_404(
        Classroom,
        class_id=classroom_id,
        teacher=teacher,
    )

    form = InviteStudentForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Please enter a valid email address.")
        return redirect(
            "classroom:class_detail",
            classroom_id=classroom.class_id,
        )

    email = form.cleaned_data["email"]

    student_user = User.objects.filter(
        email__iexact=email,
        role=User.Role.STUDENT,
        status=User.Status.ACTIVE,
    ).first()

    if student_user is None:
        messages.error(
            request,
            "No active Student account uses that email.",
        )
        return redirect(
            "classroom:class_detail",
            classroom_id=classroom.class_id,
        )

    student = getattr(student_user, "student_profile", None)

    if student is None:
        messages.error(
            request,
            "The account does not have a Student profile.",
        )
        return redirect(
            "classroom:class_detail",
            classroom_id=classroom.class_id,
        )

    # Prevent a Teacher from inviting Students from another school.
    if student.school_id != teacher.school_id:
        messages.error(
            request,
            "This Student belongs to another school.",
        )
        return redirect(
            "classroom:class_detail",
            classroom_id=classroom.class_id,
        )

    enrollment = ClassEnrollment.objects.filter(
        classroom=classroom,
        student=student,
    ).first()

    if enrollment is None:
        ClassEnrollment.objects.create(
            classroom=classroom,
            student=student,
            status=ClassEnrollment.Status.PENDING_STUDENT,
        )

        messages.success(
            request,
            "The invitation was sent to the Student dashboard.",
        )

    elif enrollment.status == ClassEnrollment.Status.APPROVED:
        messages.info(
            request,
            "This Student is already enrolled.",
        )

    elif enrollment.status == ClassEnrollment.Status.PENDING_STUDENT:
        messages.info(
            request,
            "This Student already has a pending invitation.",
        )

    elif enrollment.status == ClassEnrollment.Status.PENDING_TEACHER:
        messages.info(
            request,
            "This Student already requested to join. "
            "Approve the request below.",
        )

    else:
        # Allow the Teacher to invite the Student again after rejection.
        enrollment.status = ClassEnrollment.Status.PENDING_STUDENT
        enrollment.enrolled_at = None
        enrollment.save(
            update_fields=["status", "enrolled_at"]
        )

        messages.success(
            request,
            "A new invitation was sent to the Student dashboard.",
        )

    return redirect(
        "classroom:class_detail",
        classroom_id=classroom.class_id,
    )


@login_required(login_url="accounts:login")
def join_class_view(request):
    if request.user.role != User.Role.STUDENT:
        messages.error(request, "Only Students can join classes.")
        return redirect("classroom:dashboard")

    student = getattr(request.user, "student_profile", None)

    if student is None:
        messages.error(request, "Your Student profile was not found.")
        return redirect("classroom:dashboard")

    form = JoinClassForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["class_code"]

        classroom = Classroom.objects.filter(
            class_code__iexact=code,
            is_archived=False,
        ).select_related(
            "teacher",
            "teacher__school",
        ).first()

        if classroom is None:
            form.add_error(
                "class_code",
                "No active class uses this code.",
            )

        elif classroom.teacher.school_id != student.school_id:
            form.add_error(
                "class_code",
                "This class belongs to another school.",
            )

        else:
            enrollment = ClassEnrollment.objects.filter(
                classroom=classroom,
                student=student,
            ).first()

            if enrollment is None:
                enrollment = ClassEnrollment.objects.create(
                    classroom=classroom,
                    student=student,
                    status=ClassEnrollment.Status.PENDING_TEACHER,
                )

                notify_join_request(enrollment)

                messages.success(
                    request,
                    "Your request was sent to the Teacher for approval.",
                )

                return redirect("classroom:dashboard")

            if enrollment.status == ClassEnrollment.Status.APPROVED:
                messages.info(
                    request,
                    "You are already enrolled in this class.",
                )

                return redirect("classroom:dashboard")

            if enrollment.status == ClassEnrollment.Status.PENDING_TEACHER:
                messages.info(
                    request,
                    "Your request is still waiting for Teacher approval.",
                )

                return redirect("classroom:dashboard")

            if enrollment.status == ClassEnrollment.Status.PENDING_STUDENT:
                # Entering the code means the Student accepts the invitation.
                enrollment.status = ClassEnrollment.Status.APPROVED
                enrollment.enrolled_at = timezone.now()
                enrollment.save(
                    update_fields=["status", "enrolled_at"]
                )

                messages.success(
                    request,
                    f"You joined {classroom.class_name}.",
                )

                return redirect("classroom:dashboard")

            # Allow another request after a previous rejection.
            enrollment.status = ClassEnrollment.Status.PENDING_TEACHER
            enrollment.enrolled_at = None
            enrollment.save(
                update_fields=["status", "enrolled_at"]
            )

            notify_join_request(enrollment)

            messages.success(
                request,
                "A new join request was sent to the Teacher.",
            )

            return redirect("classroom:dashboard")

    return render(
        request,
        "classroom/join_class.html",
        {
            "form": form,
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def respond_to_invitation_view(request, enrollment_id, action):
    if request.user.role != User.Role.STUDENT:
        messages.error(request, "Only Students can answer invitations.")
        return redirect("classroom:dashboard")

    student = getattr(request.user, "student_profile", None)

    enrollment = get_object_or_404(
        ClassEnrollment,
        enrollment_id=enrollment_id,
        student=student,
        status=ClassEnrollment.Status.PENDING_STUDENT,
    )

    if action == "accept":
        enrollment.status = ClassEnrollment.Status.APPROVED
        enrollment.enrolled_at = timezone.now()
        enrollment.save(
            update_fields=["status", "enrolled_at"]
        )

        messages.success(
            request,
            f"You joined {enrollment.classroom.class_name}.",
        )

    elif action == "decline":
        enrollment.status = ClassEnrollment.Status.REJECTED
        enrollment.enrolled_at = None
        enrollment.save(
            update_fields=["status", "enrolled_at"]
        )

        messages.info(request, "The invitation was declined.")

    else:
        messages.error(request, "Invalid response.")

    return redirect("classroom:dashboard")


@login_required(login_url="accounts:login")
@require_POST
def respond_to_join_request_view(request, enrollment_id, action):
    if request.user.role != User.Role.TEACHER:
        messages.error(request, "Only Teachers can answer join requests.")
        return redirect("classroom:dashboard")

    teacher = getattr(request.user, "teacher_profile", None)

    # The Teacher can only answer requests from their own class.
    enrollment = get_object_or_404(
        ClassEnrollment,
        enrollment_id=enrollment_id,
        classroom__teacher=teacher,
        status=ClassEnrollment.Status.PENDING_TEACHER,
    )

    if action == "approve":
        enrollment.status = ClassEnrollment.Status.APPROVED
        enrollment.enrolled_at = timezone.now()
        enrollment.save(
            update_fields=["status", "enrolled_at"]
        )

        messages.success(
            request,
            f"{enrollment.student} was enrolled successfully.",
        )

    elif action == "reject":
        enrollment.status = ClassEnrollment.Status.REJECTED
        enrollment.enrolled_at = None
        enrollment.save(
            update_fields=["status", "enrolled_at"]
        )

        messages.info(request, "The join request was rejected.")

    else:
        messages.error(request, "Invalid response.")

    return redirect(
        "classroom:class_detail",
        classroom_id=enrollment.classroom_id,
    )

@login_required(login_url="accounts:login")
def class_page_view(request, classroom_id):
    active_tab = request.GET.get("tab", "stream")

    allowed_tabs = [
        "stream",
        "modules",
        "activities",
        "people",
        "grades",
    ]

    if active_tab not in allowed_tabs:
        active_tab = "stream"

    if active_tab == "grades":
        return redirect("classroom:gradebook", classroom_id=classroom_id)

    is_teacher = False
    is_student = False
    student = None

    if request.user.role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)

        if teacher is None:
            messages.error(request, "Your Teacher profile was not found.")
            return redirect("classroom:dashboard")

        classroom = get_object_or_404(
            Classroom,
            class_id=classroom_id,
            teacher=teacher,
            is_archived=False,
        )

        is_teacher = True

    elif request.user.role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)

        if student is None:
            messages.error(request, "Your Student profile was not found.")
            return redirect("classroom:dashboard")

        enrollment = get_object_or_404(
            ClassEnrollment.objects.select_related(
                "classroom",
                "classroom__teacher",
            ),
            classroom_id=classroom_id,
            student=student,
            status=ClassEnrollment.Status.APPROVED,
            classroom__is_archived=False,
        )

        classroom = enrollment.classroom
        is_student = True

    else:
        messages.error(
            request,
            "Only Teachers and enrolled Students can open a class.",
        )
        return redirect("classroom:dashboard")

    enrolled_students = classroom.enrollments.filter(
        status=ClassEnrollment.Status.APPROVED,
    ).select_related(
        "student",
        "student__user",
    )

    module_rows = []
    stream_items = []
    upcoming_modules = []
    selected_term = request.GET.get("term", "")
    search = request.GET.get("q", "").strip()[:150]

    if active_tab == "modules":
        modules = classroom.modules.all()

        if not is_teacher:
            modules = modules.filter(status=Module.Status.PUBLISHED)

        if selected_term in ["1", "2", "3"]:
            modules = modules.filter(term=selected_term)

        if search:
            modules = modules.filter(title__icontains=search)

        submissions = {}

        if student:
            submissions = {
                submission.module_id: submission
                for submission in ModuleSubmission.objects.filter(
                    student=student,
                    module__classroom=classroom,
                )
            }

        module_rows = [
            {
                "module": module,
                "submission": submissions.get(module.pk),
            }
            for module in modules
        ]

    if active_tab == "stream":
        announcements = classroom.announcements.select_related(
            "posted_by",
            "class_post",
        ).prefetch_related(
            "class_post__comments__user",
        )
        published_modules = classroom.modules.filter(
            status=Module.Status.PUBLISHED,
        ).select_related(
            "class_post",
        ).prefetch_related(
            "class_post__comments__user",
        )
        general_posts = classroom.class_posts.filter(
            post_type=ClassPost.PostType.GENERAL,
            is_published=True,
        ).select_related(
            "teacher",
            "teacher__user",
        ).prefetch_related(
            "comments__user",
        )
        stream_items = [
            {
                "kind": "announcement",
                "created_at": announcement.created_at,
                "announcement": announcement,
                "post": getattr(announcement, "class_post", None),
            }
            for announcement in announcements
        ]
        stream_items.extend(
            {
                "kind": "module",
                "created_at": module.published_at or module.created_at,
                "module": module,
                "post": getattr(module, "class_post", None),
            }
            for module in published_modules
        )
        stream_items.extend(
            {
                "kind": "post",
                "created_at": post.created_at,
                "post": post,
            }
            for post in general_posts
        )
        stream_items.sort(key=lambda item: item["created_at"], reverse=True)
        upcoming_modules = published_modules.filter(
            due_at__isnull=False,
            due_at__gte=timezone.now(),
        ).order_by("due_at")[:5]

    return render(
        request,
        "classroom/class_page.html",
        {
            "classroom": classroom,
            "active_tab": active_tab,
            "is_teacher": is_teacher,
            "is_student": is_student,
            "enrolled_students": enrolled_students,
            "rows": module_rows,
            "selected_term": selected_term,
            "search": search,
            "stream_items": stream_items,
            "upcoming_modules": upcoming_modules,
            "announcement_form": AnnouncementForm(),
            "class_post_form": ClassPostForm(),
            "comment_form": CommentForm(),
        },
    )

def _can_comment_on_post(user, post):
    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)

        return (
            teacher is not None
            and post.classroom.teacher_id == teacher.pk
        )

    if user.role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)

        if student is None:
            return False

        return ClassEnrollment.objects.filter(
            classroom=post.classroom,
            student=student,
            status=ClassEnrollment.Status.APPROVED,
        ).exists()

    return False

def _teacher_classroom_or_404(request, classroom_id):
    if request.user.role != User.Role.TEACHER:
        raise PermissionDenied("Only the Teacher can manage class announcements.")
    teacher = getattr(request.user, "teacher_profile", None)
    return get_object_or_404(
        Classroom,
        class_id=classroom_id,
        teacher=teacher,
        is_archived=False,
    )


@login_required(login_url="accounts:login")
@require_POST
def class_post_create_view(request, classroom_id):
    classroom = _teacher_classroom_or_404(request, classroom_id)
    form = ClassPostForm(request.POST)

    if form.is_valid():
        post = form.save(commit=False)
        post.classroom = classroom
        post.teacher = classroom.teacher
        post.post_type = ClassPost.PostType.GENERAL
        post.is_published = True
        post.save()

        messages.success(request, "Class post published.")
    else:
        messages.error(request, "Complete the post title and message.")

    return redirect(
        f"{reverse('classroom:class_page', args=[classroom.pk])}?tab=stream"
    )


@login_required(login_url="accounts:login")
@require_POST
def class_post_edit_view(request, post_id):
    post = get_object_or_404(
        ClassPost.objects.select_related("classroom"),
        pk=post_id,
        post_type=ClassPost.PostType.GENERAL,
    )
    classroom = _teacher_classroom_or_404(request, post.classroom_id)
    form = ClassPostForm(request.POST, instance=post)

    if form.is_valid():
        form.save()
        messages.success(request, "Class post updated.")
    else:
        messages.error(request, "The class post could not be updated.")

    return redirect(
        f"{reverse('classroom:class_page', args=[classroom.pk])}?tab=stream#post-{post.pk}"
    )


@login_required(login_url="accounts:login")
@require_POST
def class_post_delete_view(request, post_id):
    post = get_object_or_404(
        ClassPost.objects.select_related("classroom"),
        pk=post_id,
        post_type=ClassPost.PostType.GENERAL,
    )
    classroom = _teacher_classroom_or_404(request, post.classroom_id)
    post.delete()

    messages.success(request, "Class post deleted.")

    return redirect(
        f"{reverse('classroom:class_page', args=[classroom.pk])}?tab=stream"
    )

@login_required(login_url="accounts:login")
@require_POST
def comment_create_view(request, post_id):
    post = get_object_or_404(
        ClassPost.objects.select_related(
            "classroom",
            "classroom__teacher",
        ),
        pk=post_id,
        is_published=True,
    )

    if not _can_comment_on_post(request.user, post):
        raise PermissionDenied(
            "You cannot comment on this class post."
        )

    form = CommentForm(request.POST)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.user = request.user

        if (
            request.user.role != User.Role.TEACHER
            and comment.priority == Comment.Priority.IMPORTANT
        ):
            comment.priority = Comment.Priority.NORMAL

        comment.save()

        messages.success(request, "Comment posted.")
    else:
        error_message = "The comment could not be posted."

        if form.errors.get("content"):
            error_message = form.errors["content"][0]

        messages.error(request, error_message)

    class_url = reverse(
        "classroom:class_page",
        args=[post.classroom_id],
    )

    return redirect(
        f"{class_url}?tab=stream#post-{post.pk}"
    )

@login_required(login_url="accounts:login")
@require_POST
def comment_delete_view(request, comment_id):
    comment = get_object_or_404(
        Comment.objects.select_related(
            "post",
            "post__classroom",
            "post__classroom__teacher",
        ),
        pk=comment_id,
    )

    post = comment.post

    teacher = getattr(
        request.user,
        "teacher_profile",
        None,
    )

    is_comment_owner = (
        comment.user_id == request.user.pk
    )

    is_class_teacher = (
        teacher is not None
        and post.classroom.teacher_id == teacher.pk
    )

    if not is_comment_owner and not is_class_teacher:
        raise PermissionDenied(
            "You cannot delete this comment."
        )

    comment.delete()
    messages.success(request, "Comment deleted.")

    class_url = reverse(
        "classroom:class_page",
        args=[post.classroom_id],
    )

    return redirect(
        f"{class_url}?tab=stream#post-{post.pk}"
    )

@login_required(login_url="accounts:login")
@require_POST
def announcement_create_view(request, classroom_id):
    classroom = _teacher_classroom_or_404(request, classroom_id)
    form = AnnouncementForm(request.POST)
    if form.is_valid():
        announcement = form.save(commit=False)
        announcement.classroom = classroom
        announcement.posted_by = request.user
        announcement.save()
        sync_announcement_post(announcement)
        notify_class_announcement(announcement)
        messages.success(request, "Announcement posted to the Class Stream.")
    else:
        messages.error(request, "Complete the announcement title and message.")
    return redirect(
        f"{reverse('classroom:class_page', args=[classroom.pk])}?tab=stream"
    )


@login_required(login_url="accounts:login")
@require_POST
def announcement_edit_view(request, announcement_id):
    announcement = get_object_or_404(
        Announcement.objects.select_related("classroom"),
        pk=announcement_id,
    )
    classroom = _teacher_classroom_or_404(request, announcement.classroom_id)
    form = AnnouncementForm(request.POST, instance=announcement)
    if form.is_valid():
        announcement = form.save()
        sync_announcement_post(announcement)

        messages.success(request, "Announcement updated.")
    else:
        messages.error(request, "The announcement could not be updated.")
    return redirect(
        f"{reverse('classroom:class_page', args=[classroom.pk])}?tab=stream"
    )


@login_required(login_url="accounts:login")
@require_POST
def announcement_delete_view(request, announcement_id):
    announcement = get_object_or_404(
        Announcement.objects.select_related("classroom"),
        pk=announcement_id,
    )
    classroom = _teacher_classroom_or_404(request, announcement.classroom_id)
    announcement.delete()
    messages.success(request, "Announcement deleted.")
    return redirect(
        f"{reverse('classroom:class_page', args=[classroom.pk])}?tab=stream"
    )


@login_required(login_url="accounts:login")
def parent_children_view(request):
    if request.user.role != User.Role.PARENT:
        messages.error(request, "Only Parents can manage learner connections.")
        return redirect("classroom:dashboard")

    parent = getattr(request.user, "parent_profile", None)

    if parent is None:
        messages.error(request, "Your Parent profile was not found.")
        return redirect("classroom:dashboard")

    form = StudentLinkRequestForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        student = Student.objects.filter(
            lrn__iexact=form.cleaned_data["lrn"],
            user__status=User.Status.ACTIVE,
        ).first()

        if student is None:
            form.add_error(
                "lrn",
                "No active Student account uses this LRN.",
            )
        else:
            link = ParentStudentLink.objects.filter(
                parent=parent,
                student=student,
            ).first()

            if link is None:
                ParentStudentLink.objects.create(
                    parent=parent,
                    student=student,
                    relationship=form.cleaned_data["relationship"],
                )
                messages.success(
                    request,
                    "The request was sent to the Student for approval.",
                )
                return redirect("classroom:parent_children")

            if link.status == ParentStudentLink.Status.APPROVED:
                messages.info(request, "This learner is already connected.")
            elif link.status == ParentStudentLink.Status.PENDING:
                messages.info(request, "This request is still waiting for approval.")
            else:
                link.relationship = form.cleaned_data["relationship"]
                link.status = ParentStudentLink.Status.PENDING
                link.responded_at = None
                link.save(
                    update_fields=["relationship", "status", "responded_at"]
                )
                messages.success(
                    request,
                    "A new request was sent to the Student for approval.",
                )
                return redirect("classroom:parent_children")

    approved_links = ParentStudentLink.objects.filter(
        parent=parent,
        status=ParentStudentLink.Status.APPROVED,
    ).select_related("student", "student__user", "student__school")

    pending_links = ParentStudentLink.objects.filter(
        parent=parent,
        status=ParentStudentLink.Status.PENDING,
    ).select_related("student", "student__user", "student__school")

    return render(
        request,
        "classroom/parent_children.html",
        {
            "form": form,
            "approved_links": approved_links,
            "pending_links": pending_links,
        },
    )


@login_required(login_url="accounts:login")
def student_parent_requests_view(request):
    if request.user.role != User.Role.STUDENT:
        messages.error(request, "Only Students can review Parent requests.")
        return redirect("classroom:dashboard")

    student = getattr(request.user, "student_profile", None)

    if student is None:
        messages.error(request, "Your Student profile was not found.")
        return redirect("classroom:dashboard")

    pending_links = ParentStudentLink.objects.filter(
        student=student,
        status=ParentStudentLink.Status.PENDING,
    ).select_related("parent", "parent__user")

    approved_links = ParentStudentLink.objects.filter(
        student=student,
        status=ParentStudentLink.Status.APPROVED,
    ).select_related("parent", "parent__user")

    return render(
        request,
        "classroom/student_parent_requests.html",
        {
            "pending_links": pending_links,
            "approved_links": approved_links,
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def respond_parent_link_view(request, link_id, action):
    if request.user.role != User.Role.STUDENT:
        messages.error(request, "Only Students can answer Parent requests.")
        return redirect("classroom:dashboard")

    student = getattr(request.user, "student_profile", None)
    link = get_object_or_404(
        ParentStudentLink,
        link_id=link_id,
        student=student,
        status=ParentStudentLink.Status.PENDING,
    )

    if action == "accept":
        link.status = ParentStudentLink.Status.APPROVED
        link.responded_at = timezone.now()
        link.save(update_fields=["status", "responded_at"])
        messages.success(request, f"{link.parent} is now connected to your account.")
    elif action == "reject":
        link.status = ParentStudentLink.Status.REJECTED
        link.responded_at = timezone.now()
        link.save(update_fields=["status", "responded_at"])
        messages.info(request, "The Parent connection request was rejected.")
    else:
        messages.error(request, "Invalid response.")

    return redirect("classroom:student_parent_requests")

def _module_class_access(request, classroom_id):
    if request.user.status != User.Status.ACTIVE:
        raise PermissionDenied("Your account is not active.")

    classroom = get_object_or_404(
        Classroom.objects.select_related("teacher"),
        pk=classroom_id,
        is_archived=False,
    )

    if request.user.role == User.Role.TEACHER:
        teacher = getattr(
            request.user,
            "teacher_profile",
            None,
        )

        if teacher is None or classroom.teacher_id != teacher.pk:
            raise PermissionDenied(
                "You do not own this class."
            )

        return classroom, True, None

    if request.user.role == User.Role.STUDENT:
        student = getattr(
            request.user,
            "student_profile",
            None,
        )

        if student is None:
            raise PermissionDenied("Student profile not found.")

        get_object_or_404(
            ClassEnrollment,
            classroom=classroom,
            student=student,
            status=ClassEnrollment.Status.APPROVED,
        )

        return classroom, False, student

    raise PermissionDenied(
        "Only the class Teacher and enrolled Students can access modules."
    )


def _get_module_access(request, module_id):
    module = get_object_or_404(
        Module.objects.select_related("classroom"),
        pk=module_id,
    )

    classroom, is_teacher, student = _module_class_access(
        request,
        module.classroom_id,
    )

    if not is_teacher and module.status != Module.Status.PUBLISHED:
        raise Http404("Module not found.")

    return module, classroom, is_teacher, student

@login_required(login_url="accounts:login")
def module_list_view(request, classroom_id):
    classroom, is_teacher, student = _module_class_access(
        request,
        classroom_id,
    )

    modules = classroom.modules.all()

    if not is_teacher:
        modules = modules.filter(
            status=Module.Status.PUBLISHED,
        )

    selected_term = request.GET.get("term", "")

    if selected_term in ["1", "2", "3"]:
        modules = modules.filter(term=selected_term)

    search = request.GET.get("q", "").strip()[:150]

    if search:
        modules = modules.filter(title__icontains=search)

    submissions = {}

    if student:
        submissions = {
            submission.module_id: submission
            for submission in ModuleSubmission.objects.filter(
                student=student,
                module__classroom=classroom,
            )
        }

    rows = [
        {
            "module": module,
            "submission": submissions.get(module.pk),
        }
        for module in modules
    ]

    return render(
        request,
        "classroom/modules/live_list.html",
        {
            "classroom": classroom,
            "is_teacher": is_teacher,
            "rows": rows,
            "selected_term": selected_term,
            "search": search,
        },
    )

@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def module_create_view(request, classroom_id):
    classroom, is_teacher, student = _module_class_access(
        request,
        classroom_id,
    )

    if not is_teacher:
        raise PermissionDenied("Only the Teacher can create modules.")

    form = ModuleCreateForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
    )

    if request.method == "POST" and form.is_valid():
        module = form.save(commit=False)
        module.classroom = classroom
        module.status = Module.Status.DRAFT
        module.save()
        sync_module_grade_item(module)
        try:
            build_student_pdf(module)
        except ValidationError as error:
            module.delete()
            form.add_error("hidden_pages", error)
        else:
            messages.success(
                request,
                "Draft created. Students will answer directly on the Module PDF.",
            )
            return redirect("classroom:module_manage", module_id=module.pk)

    return render(
        request,
        "classroom/modules/live_create.html",
        {
            "classroom": classroom,
            "form": form,
            "is_teacher": True,
        },
    )

@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def module_manage_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(
        request,
        module_id,
    )

    if not is_teacher:
        raise PermissionDenied("Only the Teacher can manage modules.")

    score_form = ModuleScoreForm(instance=module)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save_score":
            score_form = ModuleScoreForm(request.POST, instance=module)
            if score_form.is_valid():
                module = score_form.save()
                sync_module_grade_item(module)

                if module.status == Module.Status.PUBLISHED:
                    sync_module_post(module)
                    
                messages.success(request, "Maximum Module score saved.")
                return redirect("classroom:module_manage", module_id=module.pk)
        elif action == "publish":
            if module.total_points < 1:
                messages.error(
                    request,
                    "Review the PDF and set the maximum score before publishing.",
                )
            else:
                was_already_published = (
                    module.status == Module.Status.PUBLISHED
                )
                module.status = Module.Status.PUBLISHED
                module.published_at = timezone.now()
                module.save(update_fields=["status", "published_at"])
                sync_module_grade_item(module)
                sync_module_post(module)

                if not was_already_published:
                    notify_module_published(module)

                messages.success(request, "Module published to enrolled Students.")
                return redirect("classroom:module_manage", module_id=module.pk)
        else:
            raise PermissionDenied("Invalid action.")

    sections = module.answer_sections.prefetch_related("questions")
    return render(
        request,
        "classroom/modules/live_manage.html",
        {
            "classroom": classroom,
            "module": module,
            "sections": sections,
            "score_form": score_form,
            "is_teacher": True,
        },
    )


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def module_section_create_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(request, module_id)
    if not is_teacher:
        raise PermissionDenied("Only the Teacher can add answer sections.")
    section = ModuleAnswerSection(module=module, position=module.answer_sections.count() + 1)
    form = AnswerSectionForm(request.POST or None, instance=section)
    if request.method == "POST" and form.is_valid():
        section = form.save()
        sync_module_grade_item(module)
        messages.success(request, "Answer section added.")
        return redirect("classroom:module_section_edit", section_id=section.pk)
    return render(request, "classroom/modules/live_section_form.html", {
        "classroom": classroom, "module": module, "form": form,
        "section": None, "is_teacher": True,
    })


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def module_section_edit_view(request, section_id):
    section = get_object_or_404(ModuleAnswerSection.objects.select_related("module"), pk=section_id)
    module, classroom, is_teacher, student = _get_module_access(request, section.module_id)
    if not is_teacher:
        raise PermissionDenied("Only the Teacher can edit answer sections.")
    form = AnswerSectionForm(request.POST or None, instance=section)
    formset = SectionQuestionFormSet(request.POST or None, instance=section, prefix="questions")
    forms_valid = form.is_valid() and formset.is_valid() if request.method == "POST" else False
    if forms_valid and form.cleaned_data["answer_method"] == ModuleAnswerSection.AnswerMethod.STRUCTURED:
        question_points = sum(
            row.get("points", 0)
            for row in formset.cleaned_data
            if row and not row.get("DELETE")
        )
        if question_points > form.cleaned_data["max_score"]:
            form.add_error(
                "max_score",
                f"Question points total {question_points}, so the section total cannot be lower.",
            )
            forms_valid = False
    if request.method == "POST" and forms_valid:
        with transaction.atomic():
            form.save()
            formset.save()
            for position, question in enumerate(section.questions.order_by("position", "pk"), start=1):
                if question.position != position:
                    question.position = position
                    question.save(update_fields=["position"])
            sync_module_grade_item(module)
        messages.success(request, "Answer section saved.")
        return redirect("classroom:module_manage", module_id=module.pk)
    return render(request, "classroom/modules/live_section_form.html", {
        "classroom": classroom, "module": module, "section": section,
        "form": form, "formset": formset, "is_teacher": True,
    })


@login_required(login_url="accounts:login")
@require_POST
def module_section_delete_view(request, section_id):
    section = get_object_or_404(ModuleAnswerSection.objects.select_related("module"), pk=section_id)
    module, classroom, is_teacher, student = _get_module_access(request, section.module_id)
    if not is_teacher:
        raise PermissionDenied("Only the Teacher can delete answer sections.")
    section.delete()
    sync_module_grade_item(module)
    messages.success(request, "Answer section removed.")
    return redirect("classroom:module_manage", module_id=module.pk)

@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def module_work_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(
        request,
        module_id,
    )

    submission = None
    if student:
        submission, created = ModuleSubmission.objects.get_or_create(module=module, student=student)
    locked = bool(submission and submission.status != ModuleSubmission.Status.DRAFT)
    deadline_closed = bool(module.due_at and timezone.now() > module.due_at and not module.allow_late)

    if request.method == "POST":
        if is_teacher:
            raise PermissionDenied("The Teacher preview cannot submit student answers.")
        if locked:
            messages.error(request, "This module has already been submitted.")
        elif deadline_closed:
            messages.error(request, "The deadline has passed and late submissions are closed.")
        elif module.answer_sections.exists() and not (
            submission.annotation_data or submission.extra_pages.exists()
        ):
            # Backward compatibility for Modules prepared with the older
            # answer-section workflow. Newly created Modules use the PDF path.
            missing = []
            for section in module.answer_sections.filter(required=True):
                response = submission.section_responses.filter(
                    section=section,
                    is_complete=True,
                ).first()
                if not response:
                    missing.append(section.title)
            if missing:
                messages.error(
                    request,
                    "Complete these required sections first: " + ", ".join(missing),
                )
            else:
                submission.status = ModuleSubmission.Status.SUBMITTED
                submission.submitted_at = timezone.now()
                submission.save(update_fields=["status", "submitted_at", "updated_at"])
                graded_required = submission.section_responses.filter(
                    section__required=True,
                    section__include_in_grade=True,
                )
                if graded_required.exists() and not graded_required.filter(
                    score__isnull=True,
                ).exists():
                    submission.update_total_score()
                    sync_module_grade_score(submission)
                    submission.status = ModuleSubmission.Status.GRADED
                    submission.graded_at = timezone.now()
                    submission.save(update_fields=["status", "graded_at", "updated_at"])
                notify_submission(submission)
                messages.success(request, "Complete module submitted to your Teacher.")
                return redirect("classroom:module_work", module_id=module.pk)
        elif not (
            submission.annotation_data or submission.extra_pages.exists()
        ):
            messages.error(
                request,
                "Add an answer, drawing, or uploaded output before submitting.",
            )
        else:
            try:
                build_final_submission_pdf(submission)
            except ValidationError as error:
                messages.error(request, "; ".join(error.messages))
            else:
                submission.status = ModuleSubmission.Status.SUBMITTED
                submission.submitted_at = timezone.now()
                submission.save(update_fields=["status", "submitted_at", "updated_at"])
                notify_submission(submission)
                messages.success(request, "Complete answered Module submitted to your Teacher.")
                return redirect("classroom:module_work", module_id=module.pk)

    responses = {}
    if submission:
        responses = {row.section_id: row for row in submission.section_responses.all()}
    section_rows = [
        {"section": section, "response": responses.get(section.pk)}
        for section in module.answer_sections.all()
    ]
    can_edit = not is_teacher and not locked and not deadline_closed
    if submission and locked and submission.answered_pdf:
        pdf_url = reverse("classroom:submission_pdf", args=[submission.pk])
    else:
        pdf_url = reverse("classroom:module_pdf", args=[module.pk])

    return render(
        request,
        "classroom/modules/live_work.html",
        {
            "classroom": classroom,
            "module": module,
            "submission": submission,
            "section_rows": section_rows,
            "is_teacher": is_teacher,
            "can_edit": can_edit,
            "deadline_closed": deadline_closed,
            "pdf_url": pdf_url,
        },
    )


MOBILE_ANNOTATION_TOOLS = {
    "type",
    "draw",
    "check",
    "circle",
    "highlight",
}


def _mobile_draft_error(module, submission):
    if submission.status != ModuleSubmission.Status.DRAFT:
        return "This Module has already been submitted.", 409

    if module.due_at and timezone.now() > module.due_at and not module.allow_late:
        return "The Module deadline has passed.", 403

    return None


def _clean_mobile_annotations(value):
    """Validate and reduce mobile annotation JSON to supported fields."""
    if not isinstance(value, list):
        raise ValidationError("Annotations must be provided as a list.")
    if len(value) > 3000:
        raise ValidationError("This Module contains too many annotations.")
    if len(json.dumps(value)) > 2_000_000:
        raise ValidationError("The annotation draft is too large.")

    cleaned_annotations = []
    for raw_annotation in value:
        if not isinstance(raw_annotation, dict):
            raise ValidationError("An annotation has an invalid format.")

        tool = raw_annotation.get("tool")
        if tool not in MOBILE_ANNOTATION_TOOLS:
            raise ValidationError("An annotation contains an unsupported tool.")

        try:
            page_number = int(raw_annotation.get("page"))
        except (TypeError, ValueError):
            raise ValidationError("An annotation contains an invalid page.")
        if not 1 <= page_number <= 500:
            raise ValidationError("An annotation contains an invalid page.")

        annotation_id = str(raw_annotation.get("id", ""))[:64]
        if not annotation_id:
            raise ValidationError("Every annotation must have an ID.")

        cleaned = {
            "id": annotation_id,
            "page": page_number,
            "tool": tool,
        }

        for field_name in ["x", "y", "width", "height", "size", "opacity"]:
            if field_name not in raw_annotation:
                continue
            raw_value = raw_annotation[field_name]
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                raise ValidationError(f"Invalid annotation value: {field_name}.")
            cleaned[field_name] = float(raw_value)

        if "text" in raw_annotation:
            text = raw_annotation["text"]
            if not isinstance(text, str):
                raise ValidationError("Annotation text is invalid.")
            cleaned["text"] = text[:5000]

        if "color" in raw_annotation:
            color = raw_annotation["color"]
            if not isinstance(color, str) or len(color) > 20:
                raise ValidationError("Annotation color is invalid.")
            cleaned["color"] = color

        if "points" in raw_annotation:
            raw_points = raw_annotation["points"]
            if not isinstance(raw_points, list) or len(raw_points) > 5000:
                raise ValidationError("Annotation drawing points are invalid.")
            cleaned_points = []
            for raw_point in raw_points:
                if not isinstance(raw_point, dict):
                    raise ValidationError("A drawing point is invalid.")
                x = raw_point.get("x")
                y = raw_point.get("y")
                if (
                    isinstance(x, bool)
                    or isinstance(y, bool)
                    or not isinstance(x, (int, float))
                    or not isinstance(y, (int, float))
                ):
                    raise ValidationError("A drawing point is invalid.")
                cleaned_points.append({"x": float(x), "y": float(y)})
            cleaned["points"] = cleaned_points

        cleaned_annotations.append(cleaned)

    return cleaned_annotations


def _serialize_extra_page(extra_page):
    file_url = ""
    if extra_page.uploaded_file:
        file_url = reverse("classroom:module_extra_page_file", args=[extra_page.pk])

    return {
        "id": extra_page.pk,
        "page_type": extra_page.page_type,
        "page_type_label": extra_page.get_page_type_display(),
        "title": extra_page.title,
        "related_pdf_page": extra_page.related_pdf_page,
        "position": extra_page.position,
        "essay_text": extra_page.essay_text,
        "drawing_data": extra_page.drawing_data,
        "original_name": extra_page.original_name,
        "caption": extra_page.caption,
        "file_url": file_url,
        "update_url": reverse("classroom:module_extra_page_update", args=[extra_page.pk]),
        "delete_url": reverse("classroom:module_extra_page_delete", args=[extra_page.pk]),
    }


def _get_student_extra_page_access(request, extra_page_id):
    extra_page = get_object_or_404(
        SubmissionExtraPage.objects.select_related(
            "submission__module",
            "submission__student",
        ),
        pk=extra_page_id,
    )
    module, classroom, is_teacher, student = _get_module_access(
        request,
        extra_page.submission.module_id,
    )
    if is_teacher:
        raise PermissionDenied("The Teacher cannot modify Student draft pages.")
    if extra_page.submission.student_id != student.pk:
        raise PermissionDenied("You cannot access another Student's draft.")
    return extra_page, extra_page.submission, module, classroom, student


@login_required(login_url="accounts:login")
@require_GET
def module_mobile_draft_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(request, module_id)
    if is_teacher:
        raise PermissionDenied("The Teacher preview does not have a Student draft.")

    submission, _ = ModuleSubmission.objects.get_or_create(
        module=module,
        student=student,
    )
    return JsonResponse({
        "submission_id": submission.pk,
        "status": submission.status,
        "editable": _mobile_draft_error(module, submission) is None,
        "current_page": submission.current_page,
        "annotations": submission.annotation_data,
        "extra_pages": [
            _serialize_extra_page(extra_page)
            for extra_page in submission.extra_pages.all()
        ],
        "draft_saved_at": (
            submission.draft_saved_at.isoformat()
            if submission.draft_saved_at else None
        ),
    })


@login_required(login_url="accounts:login")
@require_POST
def module_mobile_annotations_save_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(request, module_id)
    if is_teacher:
        raise PermissionDenied("The Teacher preview cannot save Student answers.")

    submission, _ = ModuleSubmission.objects.get_or_create(
        module=module,
        student=student,
    )
    draft_error = _mobile_draft_error(module, submission)
    if draft_error:
        message, status_code = draft_error
        return JsonResponse({"error": message}, status=status_code)

    try:
        data = json.loads(request.body or b"{}")
        annotations = _clean_mobile_annotations(data.get("annotations", []))
        current_page = int(data.get("current_page", 1))
        if not 1 <= current_page <= 500:
            raise ValidationError("The current PDF page is invalid.")
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as error:
        message = (
            "; ".join(error.messages)
            if isinstance(error, ValidationError)
            else "The annotation draft is invalid."
        )
        return JsonResponse({"error": message}, status=400)

    submission.annotation_data = annotations
    submission.current_page = current_page
    submission.draft_saved_at = timezone.now()
    submission.save(update_fields=[
        "annotation_data",
        "current_page",
        "draft_saved_at",
        "updated_at",
    ])
    return JsonResponse({
        "saved": True,
        "annotation_count": len(annotations),
        "current_page": current_page,
        "saved_at": submission.draft_saved_at.isoformat(),
    })


@login_required(login_url="accounts:login")
@require_POST
def module_extra_page_create_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(request, module_id)
    if is_teacher:
        raise PermissionDenied("The Teacher cannot add Student answer pages.")

    submission, _ = ModuleSubmission.objects.get_or_create(
        module=module,
        student=student,
    )
    draft_error = _mobile_draft_error(module, submission)
    if draft_error:
        message, status_code = draft_error
        return JsonResponse({"error": message}, status=status_code)

    page_type = request.POST.get("page_type", "").strip()
    valid_page_types = {
        SubmissionExtraPage.PageType.ESSAY,
        SubmissionExtraPage.PageType.DRAWING,
        SubmissionExtraPage.PageType.UPLOAD,
    }
    if page_type not in valid_page_types:
        return JsonResponse({"error": "Select a valid answer-page type."}, status=400)

    default_titles = {
        SubmissionExtraPage.PageType.ESSAY: "Written Answer",
        SubmissionExtraPage.PageType.DRAWING: "Blank Drawing Page",
        SubmissionExtraPage.PageType.UPLOAD: "Uploaded Output",
    }
    title = request.POST.get("title", "").strip()[:150] or default_titles[page_type]
    caption = request.POST.get("caption", "").strip()[:500]
    related_pdf_page = request.POST.get("related_pdf_page", "").strip()
    if related_pdf_page:
        try:
            related_pdf_page = int(related_pdf_page)
            if related_pdf_page < 1:
                raise ValueError
        except ValueError:
            return JsonResponse({"error": "The related Module page is invalid."}, status=400)
    else:
        related_pdf_page = None

    uploaded_file = request.FILES.get("file")
    if page_type == SubmissionExtraPage.PageType.UPLOAD:
        if uploaded_file is None:
            return JsonResponse({"error": "Choose an image or PDF to upload."}, status=400)
        try:
            validate_answer_file(uploaded_file)
        except ValidationError as error:
            return JsonResponse({"error": "; ".join(error.messages)}, status=400)
    elif uploaded_file is not None:
        return JsonResponse(
            {"error": "Files can only be added to an Uploaded Output page."},
            status=400,
        )

    with transaction.atomic():
        highest_position = submission.extra_pages.aggregate(
            highest=Max("position")
        )["highest"] or 0
        extra_page = SubmissionExtraPage(
            submission=submission,
            page_type=page_type,
            title=title,
            related_pdf_page=related_pdf_page,
            position=highest_position + 1,
            caption=caption,
        )
        if uploaded_file:
            extra_page.uploaded_file = uploaded_file
            extra_page.original_name = Path(uploaded_file.name).name[:255]
        extra_page.full_clean()
        extra_page.save()

    return JsonResponse(
        {"created": True, "page": _serialize_extra_page(extra_page)},
        status=201,
    )


@login_required(login_url="accounts:login")
@require_POST
def module_extra_page_update_view(request, extra_page_id):
    extra_page, submission, module, classroom, student = _get_student_extra_page_access(
        request,
        extra_page_id,
    )
    draft_error = _mobile_draft_error(module, submission)
    if draft_error:
        message, status_code = draft_error
        return JsonResponse({"error": message}, status=status_code)

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "The answer-page data is invalid."}, status=400)

    if "title" in data:
        title = str(data["title"]).strip()[:150]
        if not title:
            return JsonResponse({"error": "The page title is required."}, status=400)
        extra_page.title = title

    if "caption" in data:
        extra_page.caption = str(data["caption"]).strip()[:500]

    if "related_pdf_page" in data:
        related_pdf_page = data["related_pdf_page"]
        if related_pdf_page in ["", None]:
            extra_page.related_pdf_page = None
        else:
            try:
                related_pdf_page = int(related_pdf_page)
                if related_pdf_page < 1:
                    raise ValueError
            except (TypeError, ValueError):
                return JsonResponse({"error": "The related Module page is invalid."}, status=400)
            extra_page.related_pdf_page = related_pdf_page

    if extra_page.page_type == SubmissionExtraPage.PageType.ESSAY and "essay_text" in data:
        essay_text = data["essay_text"]
        if not isinstance(essay_text, str):
            return JsonResponse({"error": "The written answer is invalid."}, status=400)
        extra_page.essay_text = essay_text[:50000]

    if extra_page.page_type == SubmissionExtraPage.PageType.DRAWING and "drawing_data" in data:
        drawing_data = data["drawing_data"]
        if not isinstance(drawing_data, list):
            return JsonResponse({"error": "The drawing data is invalid."}, status=400)
        if len(json.dumps(drawing_data)) > 2_000_000:
            return JsonResponse({"error": "The drawing is too large."}, status=400)
        extra_page.drawing_data = drawing_data

    extra_page.full_clean()
    extra_page.save()
    submission.draft_saved_at = timezone.now()
    submission.save(update_fields=["draft_saved_at", "updated_at"])
    return JsonResponse({
        "saved": True,
        "page": _serialize_extra_page(extra_page),
        "saved_at": submission.draft_saved_at.isoformat(),
    })


@login_required(login_url="accounts:login")
@require_POST
def module_extra_page_delete_view(request, extra_page_id):
    extra_page, submission, module, classroom, student = _get_student_extra_page_access(
        request,
        extra_page_id,
    )
    draft_error = _mobile_draft_error(module, submission)
    if draft_error:
        message, status_code = draft_error
        return JsonResponse({"error": message}, status=status_code)

    if extra_page.uploaded_file:
        extra_page.uploaded_file.delete(save=False)
    extra_page.delete()

    for position, remaining_page in enumerate(submission.extra_pages.all(), start=1):
        if remaining_page.position != position:
            remaining_page.position = position
            remaining_page.save(update_fields=["position", "updated_at"])

    submission.draft_saved_at = timezone.now()
    submission.save(update_fields=["draft_saved_at", "updated_at"])
    return JsonResponse({
        "deleted": True,
        "extra_page_id": extra_page_id,
        "saved_at": submission.draft_saved_at.isoformat(),
    })


@login_required(login_url="accounts:login")
def module_extra_page_file_view(request, extra_page_id):
    extra_page = get_object_or_404(
        SubmissionExtraPage.objects.select_related(
            "submission__module",
            "submission__student",
        ),
        pk=extra_page_id,
    )
    submission = extra_page.submission
    module, classroom, is_teacher, student = _get_module_access(
        request,
        submission.module_id,
    )
    if is_teacher:
        if submission.status == ModuleSubmission.Status.DRAFT:
            raise PermissionDenied("Student drafts are private.")
    elif submission.student_id != student.pk:
        raise PermissionDenied("You cannot open another Student's output.")

    if not extra_page.uploaded_file:
        raise Http404("Uploaded output not found.")

    extension = Path(extra_page.uploaded_file.name).suffix.lower()
    content_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    return _private_file_response(
        extra_page.uploaded_file,
        extra_page.original_name or "student-output",
        content_types.get(extension, "application/octet-stream"),
    )


def _normalized_answer(value):
    return " ".join((value or "").strip().casefold().split())


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def module_section_work_view(request, section_id):
    section = get_object_or_404(
        ModuleAnswerSection.objects.select_related("module").prefetch_related("questions"),
        pk=section_id,
    )
    module, classroom, is_teacher, student = _get_module_access(request, section.module_id)
    if is_teacher:
        response = None
        submission = None
    else:
        submission, created = ModuleSubmission.objects.get_or_create(module=module, student=student)
        response = submission.section_responses.filter(section=section).first()
    complete = request.POST.get("action") == "complete"
    form = SectionResponseForm(
        section,
        request.POST or None,
        request.FILES or None,
        response=response,
        complete=complete,
    )
    locked = bool(submission and submission.status != ModuleSubmission.Status.DRAFT)
    deadline_closed = bool(module.due_at and timezone.now() > module.due_at and not module.allow_late)
    if request.method == "POST":
        if is_teacher:
            raise PermissionDenied("Teacher preview cannot save Student work.")
        if locked or deadline_closed:
            raise PermissionDenied("This module can no longer be changed.")
        if request.POST.get("action") not in ["draft", "complete"]:
            form.add_error(None, "Choose Save draft or Mark section complete.")
        elif form.is_valid():
            response, created = SectionResponse.objects.get_or_create(
                submission=submission, section=section
            )
            response.written_answer = form.cleaned_data.get("written_answer", response.written_answer)
            response.is_complete = complete
            response.auto_score = 0
            if section.answer_method == ModuleAnswerSection.AnswerMethod.STRUCTURED:
                response.score = None
                all_automatic = True
                for question in section.questions.all():
                    value = form.cleaned_data.get(f"question_{question.pk}", "")
                    is_correct = None
                    awarded = 0
                    if question.correct_answer.strip():
                        is_correct = _normalized_answer(value) == _normalized_answer(question.correct_answer)
                        awarded = question.points if is_correct else 0
                    else:
                        all_automatic = False
                    SectionAnswer.objects.update_or_create(
                        response=response,
                        question=question,
                        defaults={
                            "answer_text": value,
                            "is_correct": is_correct,
                            "awarded_points": awarded,
                        },
                    )
                    response.auto_score += awarded
                if complete and all_automatic:
                    response.score = min(response.auto_score, section.max_score)
            response.save()
            for upload in form.cleaned_data.get("answer_files", []):
                SubmissionAttachment.objects.create(
                    response=response, file=upload, original_name=upload.name
                )
            messages.success(request, "Section completed." if complete else "Section draft saved.")
            return redirect("classroom:module_work", module_id=module.pk)
    return render(request, "classroom/modules/live_section_work.html", {
        "classroom": classroom, "module": module, "section": section,
        "submission": submission, "response": response, "form": form,
        "is_teacher": is_teacher, "can_edit": not is_teacher and not locked and not deadline_closed,
    })

@login_required(login_url="accounts:login")
def module_submissions_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(
        request,
        module_id,
    )

    if not is_teacher:
        raise PermissionDenied("Only the Teacher can review submissions.")

    submissions = module.submissions.filter(
        status__in=[
            ModuleSubmission.Status.SUBMITTED,
            ModuleSubmission.Status.GRADED,
        ],
    ).select_related(
        "student",
        "student__user",
    ).order_by("-submitted_at")

    return render(
        request,
        "classroom/modules/live_submissions.html",
        {
            "classroom": classroom,
            "module": module,
            "submissions": submissions,
            "is_teacher": True,
        },
    )


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def module_review_view(request, submission_id):
    submission = get_object_or_404(
        ModuleSubmission.objects.select_related(
            "module",
            "student",
            "student__user",
        ),
        pk=submission_id,
        status__in=[
            ModuleSubmission.Status.SUBMITTED,
            ModuleSubmission.Status.GRADED,
        ],
    )

    module, classroom, is_teacher, student = _get_module_access(
        request,
        submission.module_id,
    )

    if not is_teacher:
        raise PermissionDenied("Only the Teacher can grade submissions.")

    if submission.answered_pdf:
        grade_form = SubmissionGradeForm(
            module,
            request.POST or None,
            instance=submission,
        )
        if request.method == "POST" and grade_form.is_valid():
            graded = grade_form.save(commit=False)
            graded.status = ModuleSubmission.Status.GRADED
            graded.graded_at = timezone.now()
            graded.save(update_fields=[
                "score",
                "feedback",
                "status",
                "graded_at",
                "updated_at",
            ])

            sync_module_grade_score(graded)

            notify_submission_feedback(
                graded
            )

            messages.success(
                request,
                "Module score and feedback saved.",
            )
            return redirect("classroom:module_review", submission_id=submission.pk)

        return render(
            request,
            "classroom/modules/live_review.html",
            {
                "classroom": classroom,
                "module": module,
                "submission": submission,
                "submission_grade_form": grade_form,
                "direct_pdf_submission": True,
                "pdf_url": reverse(
                    "classroom:submission_pdf",
                    args=[submission.pk],
                ),
                "can_edit": False,
                "deadline_closed": False,
                "is_teacher": True,
            },
        )

    responses = submission.section_responses.select_related("section").prefetch_related(
        "answers__question", "attachments"
    )
    forms = []
    posted_response = request.POST.get("response_id")
    for response in responses:
        bound = request.POST if request.method == "POST" and posted_response == str(response.pk) else None
        grade_form = SectionGradeForm(response.section, bound, instance=response, prefix=f"grade-{response.pk}")
        forms.append({"response": response, "form": grade_form})
        if bound is not None and grade_form.is_valid():
            graded = grade_form.save(commit=False)
            graded.graded_at = timezone.now()
            graded.save()
            submission.update_total_score()
            sync_module_grade_score(submission)
            required_responses = submission.section_responses.filter(
                section__required=True, section__include_in_grade=True
            )
            if required_responses.exists() and not required_responses.filter(score__isnull=True).exists():
                submission.status = ModuleSubmission.Status.GRADED
                submission.graded_at = timezone.now()
                submission.save(update_fields=["status", "graded_at", "updated_at"])
            messages.success(request, f"Score saved for {response.section.title}.")
            return redirect("classroom:module_review", submission_id=submission.pk)

    return render(
        request,
        "classroom/modules/live_review.html",
        {
            "classroom": classroom,
            "module": module,
            "submission": submission,
            "response_forms": forms,
            "is_teacher": True,
        },
    )


def _gradebook_access(request, classroom_id):
    if request.user.role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        classroom = get_object_or_404(
            Classroom,
            class_id=classroom_id,
            teacher=teacher,
            is_archived=False,
        )
        return classroom, True, None

    if request.user.role == User.Role.STUDENT:
        student = getattr(request.user, "student_profile", None)
        enrollment = get_object_or_404(
            ClassEnrollment.objects.select_related("classroom"),
            classroom_id=classroom_id,
            student=student,
            status=ClassEnrollment.Status.APPROVED,
            classroom__is_archived=False,
        )
        return enrollment.classroom, False, student

    raise PermissionDenied("Only the Teacher and enrolled Students can open the gradebook.")


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def gradebook_view(request, classroom_id):
    classroom, is_teacher, current_student = _gradebook_access(request, classroom_id)
    term = request.GET.get("term", "1")
    if term not in {"1", "2", "3"}:
        term = "1"
    display = request.GET.get("view", "record")
    if display not in {"record", "summary"}:
        display = "record"
    if not is_teacher:
        display = "record"

    enrolled = list(
        Student.objects.filter(
            class_enrollments__classroom=classroom,
            class_enrollments__status=ClassEnrollment.Status.APPROVED,
        ).distinct().order_by("gender", "lastname", "firstname")
    )
    visible_students = enrolled if is_teacher else [current_student]

    settings, _ = GradebookSettings.objects.get_or_create(classroom=classroom)
    # This also backfills gradebook columns for Modules made before the
    # gradebook feature was introduced.
    for module in classroom.modules.all().order_by("created_at", "pk"):
        sync_module_grade_item(module)
        for submission in module.submissions.filter(score__isnull=False):
            sync_module_grade_score(submission)
    item_form = GradeItemForm()
    settings_form = GradebookSettingsForm(instance=settings)

    if request.method == "POST":
        if not is_teacher:
            raise PermissionDenied("Only the Teacher can change grades.")
        action = request.POST.get("action")

        if action == "add_item":
            item_form = GradeItemForm(request.POST)
            if item_form.is_valid():
                item = item_form.save(commit=False)
                item.classroom = classroom
                item.term = term
                item.position = next_item_position(classroom, term, item.component)
                item.save()
                messages.success(request, f"{item.title} was added to the next empty slot.")
                return redirect(f"{request.path}?term={term}")

        elif action == "save_weights":
            settings_form = GradebookSettingsForm(request.POST, instance=settings)
            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, "Grade component weights saved.")
                return redirect(f"{request.path}?term={term}")

        elif action == "toggle_release":
            field_name = f"term_{term}_released"
            current_value = getattr(settings, field_name)

            new_value = not current_value

            setattr(
                settings,
                field_name,
                new_value,
            )

            settings.save(
                update_fields=[field_name],
            )

            if new_value:
                notify_term_grade_released(
                    classroom,
                    term,
                )

            message = (
                "released to Students and Parents"
                if new_value
                else "hidden from Students and Parents"
            )

            messages.success(
                request,
                f"Term {term} grades are now {message}.",
            )

            return redirect(
                f"{request.path}?term={term}"
            )

        elif action == "save_scores":
            errors = []
            new_item_ids = set()
            with transaction.atomic():
                component_labels = {
                    GradeItem.Component.WRITTEN_WORK: "Written Work",
                    GradeItem.Component.PERFORMANCE_TASK: "Performance Task",
                    GradeItem.Component.ASSESSMENT: "Quarterly Assessment",
                }

                # Empty cells are direct-entry slots. Supplying an HPS or a
                # learner score turns that exact slot into a manual item.
                for key in request.POST:
                    if not key.startswith("new_hps_"):
                        continue
                    remainder = key[len("new_hps_"):]
                    component, separator, position_text = remainder.rpartition("_")
                    if not separator or component not in component_labels:
                        continue
                    try:
                        position = int(position_text)
                    except ValueError:
                        continue
                    hps_raw = request.POST.get(key, "").strip()
                    score_values = {
                        student.pk: request.POST.get(
                            f"new_score_{component}_{position}_{student.pk}", ""
                        ).strip()
                        for student in enrolled
                    }
                    if not hps_raw and not any(score_values.values()):
                        continue
                    try:
                        hps = Decimal(hps_raw)
                    except InvalidOperation:
                        errors.append(
                            f"Enter the highest possible score for {component_labels[component]} {position}."
                        )
                        continue
                    if hps <= 0:
                        errors.append(
                            f"The highest possible score for {component_labels[component]} {position} must be greater than zero."
                        )
                        continue
                    item, created = GradeItem.objects.get_or_create(
                        classroom=classroom,
                        term=term,
                        component=component,
                        position=position,
                        defaults={
                            "title": f"{component_labels[component]} {position}",
                            "highest_possible_score": hps,
                        },
                    )
                    if not created:
                        continue
                    new_item_ids.add(item.pk)
                    for student in enrolled:
                        raw_value = score_values[student.pk]
                        if not raw_value:
                            continue
                        try:
                            score = Decimal(raw_value)
                        except InvalidOperation:
                            errors.append(f"Invalid score for {student.firstname}.")
                            continue
                        if score < 0 or score > hps:
                            errors.append(
                                f"{item.title}: {student.firstname}'s score must be 0 to {hps}."
                            )
                            continue
                        GradeScore.objects.create(item=item, student=student, score=score)

                items = GradeItem.objects.filter(classroom=classroom, term=term)
                for item in items:
                    if item.pk in new_item_ids:
                        continue
                    for student in enrolled:
                        field = f"score_{item.pk}_{student.pk}"
                        raw_value = request.POST.get(field, "").strip()
                        if raw_value == "":
                            GradeScore.objects.filter(item=item, student=student).delete()
                            continue
                        try:
                            score = Decimal(raw_value)
                        except InvalidOperation:
                            errors.append(f"Invalid score for {student.firstname} in {item.title}.")
                            continue
                        if score < 0 or score > item.highest_possible_score:
                            errors.append(
                                f"{item.title}: {student.firstname}'s score must be 0 to {item.highest_possible_score}."
                            )
                            continue
                        GradeScore.objects.update_or_create(
                            item=item,
                            student=student,
                            defaults={"score": score},
                        )
                if errors:
                    transaction.set_rollback(True)
            if errors:
                for error in errors[:5]:
                    messages.error(request, error)
            else:
                messages.success(request, "Scores saved and grades recalculated.")
                return redirect(f"{request.path}?term={term}")

    record = build_term_record(classroom, term, visible_students)
    quarterly_grade_released = getattr(settings, f"term_{term}_released")
    student_score_groups = []
    if not is_teacher:
        score_lookup = {
            score.item_id: score.score
            for score in GradeScore.objects.filter(
                student=current_student,
                item__classroom=classroom,
                item__term=term,
            )
        }
        for component, label in (
            (GradeItem.Component.WRITTEN_WORK, "Written Works"),
            (GradeItem.Component.PERFORMANCE_TASK, "Performance Tasks"),
            (GradeItem.Component.ASSESSMENT, "Quarterly Assessment"),
        ):
            component_items = record["grouped"][component]
            student_score_groups.append({
                "label": label,
                "items": [
                    {"item": item, "score": score_lookup.get(item.pk)}
                    for item in component_items
                ],
            })
    summary_rows = build_summary(classroom, visible_students) if display == "summary" else []
    return render(request, "classroom/gradebook.html", {
        "classroom": classroom,
        "is_teacher": is_teacher,
        "is_student": not is_teacher,
        "term": term,
        "display": display,
        "record": record,
        "rows": record["rows"],
        "summary_rows": summary_rows,
        "summary_male_rows": [row for row in summary_rows if row["student"].gender == Student.Gender.MALE],
        "summary_female_rows": [row for row in summary_rows if row["student"].gender == Student.Gender.FEMALE],
        "item_form": item_form,
        "settings_form": settings_form,
        "quarterly_grade_released": quarterly_grade_released,
        "student_score_groups": student_score_groups,
        "student_term_row": record["rows"][0] if record["rows"] else None,
        "male_rows": [row for row in record["rows"] if row["student"].gender == Student.Gender.MALE],
        "female_rows": [row for row in record["rows"] if row["student"].gender == Student.Gender.FEMALE],
    })


@login_required(login_url="accounts:login")
@require_POST
def grade_item_delete_view(request, item_id):
    item = get_object_or_404(GradeItem.objects.select_related("classroom", "module"), pk=item_id)
    classroom, is_teacher, current_student = _gradebook_access(request, item.classroom_id)
    if not is_teacher:
        raise PermissionDenied("Only the Teacher can remove grade items.")
    if item.module_id:
        messages.error(request, "A Module column is removed by deleting its Module, not from the gradebook.")
    else:
        title = item.title
        term = item.term
        item.delete()
        messages.success(request, f"{title} was removed.")
        return redirect(
            f"{reverse('classroom:gradebook', args=[classroom.pk])}?term={term}"
        )
    return redirect("classroom:gradebook", classroom_id=classroom.pk)


@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def attendance_view(request, classroom_id):
    if request.user.role != User.Role.TEACHER:
        raise PermissionDenied("Only the Teacher can manage class attendance.")

    teacher = getattr(request.user, "teacher_profile", None)
    classroom = get_object_or_404(
        Classroom.objects.select_related("teacher", "teacher__school"),
        class_id=classroom_id,
        teacher=teacher,
        is_archived=False,
    )
    students = list(
        Student.objects.filter(
            class_enrollments__classroom=classroom,
            class_enrollments__status=ClassEnrollment.Status.APPROVED,
        ).distinct().order_by("gender", "lastname", "firstname")
    )

    view_mode = request.GET.get("view", "daily")
    if view_mode not in {"daily", "monthly"}:
        view_mode = "daily"

    raw_date = request.GET.get("date", timezone.localdate().isoformat())
    try:
        selected_date = date.fromisoformat(raw_date)
    except ValueError:
        selected_date = timezone.localdate()

    raw_month = request.GET.get("month", selected_date.strftime("%Y-%m"))
    try:
        month_year, month_number = (int(part) for part in raw_month.split("-", 1))
        selected_month = date(month_year, month_number, 1)
    except (ValueError, TypeError):
        selected_month = selected_date.replace(day=1)

    if request.method == "POST":
        action = request.POST.get("action")
        if action != "save_attendance":
            raise PermissionDenied("Invalid attendance action.")

        try:
            entry_date = date.fromisoformat(request.POST.get("date", ""))
        except ValueError:
            messages.error(request, "Select a valid attendance date.")
            return redirect("classroom:attendance", classroom_id=classroom.pk)

        day_type = request.POST.get("day_type", AttendanceDay.DayType.CLASS_DAY)
        if day_type not in AttendanceDay.DayType.values:
            day_type = AttendanceDay.DayType.CLASS_DAY

        with transaction.atomic():
            attendance_day, _ = AttendanceDay.objects.update_or_create(
                classroom=classroom,
                date=entry_date,
                defaults={
                    "day_type": day_type,
                    "note": request.POST.get("note", "").strip()[:150],
                    "recorded_by": teacher,
                },
            )

            if day_type != AttendanceDay.DayType.CLASS_DAY:
                attendance_day.records.all().delete()
            else:
                valid_statuses = set(AttendanceRecord.Status.values)
                for student in students:
                    status = request.POST.get(
                        f"status_{student.pk}", AttendanceRecord.Status.PRESENT
                    )
                    if status not in valid_statuses:
                        status = AttendanceRecord.Status.PRESENT
                    attendance_record, created = (
                        AttendanceRecord.objects.update_or_create(
                            attendance_day=attendance_day,
                            student=student,
                            defaults={
                                "status": status,
                                "remarks": request.POST.get(
                                    f"remarks_{student.pk}",
                                    "",
                                ).strip()[:200],
                            },
                        )
                    )

                    notify_attendance_record(
                        attendance_record
                    )

        if day_type == AttendanceDay.DayType.CLASS_DAY:
            messages.success(request, f"Attendance saved for {entry_date:%B %d, %Y}.")
        else:
            messages.success(
                request,
                f"{entry_date:%B %d, %Y} was marked as {attendance_day.get_day_type_display()}.",
            )
        return redirect(
            f"{reverse('classroom:attendance', args=[classroom.pk])}?view=daily&date={entry_date.isoformat()}"
        )

    attendance_day = AttendanceDay.objects.filter(
        classroom=classroom,
        date=selected_date,
    ).prefetch_related("records").first()
    record_lookup = {
        record.student_id: record
        for record in attendance_day.records.all()
    } if attendance_day else {}
    daily_rows = [
        {"student": student, "record": record_lookup.get(student.pk)}
        for student in students
    ]

    first_weekday, days_in_month = month_calendar.monthrange(
        selected_month.year, selected_month.month
    )
    del first_weekday
    report_dates = [
        date(selected_month.year, selected_month.month, day_number)
        for day_number in range(1, days_in_month + 1)
        if date(selected_month.year, selected_month.month, day_number).weekday() < 5
    ]
    month_days = {
        day.date: day
        for day in AttendanceDay.objects.filter(
            classroom=classroom,
            date__year=selected_month.year,
            date__month=selected_month.month,
        ).prefetch_related("records")
    }
    month_record_lookup = {}
    for day in month_days.values():
        for record in day.records.all():
            month_record_lookup[(day.date, record.student_id)] = record

    monthly_columns = [
        {"date": report_date, "number": report_date.day, "weekday": report_date.strftime("%a")[:1]}
        for report_date in report_dates
    ]
    monthly_rows = []
    for student in students:
        cells = []
        absent_total = 0
        late_total = 0
        remarks = []
        for report_date in report_dates:
            day = month_days.get(report_date)
            record = month_record_lookup.get((report_date, student.pk))
            code = ""
            title = "Not recorded"
            css_class = "unrecorded"
            if day and day.day_type == AttendanceDay.DayType.HOLIDAY:
                code, title, css_class = "H", day.note or "Holiday", "holiday"
            elif day and day.day_type == AttendanceDay.DayType.NO_CLASS:
                code, title, css_class = "NC", day.note or "No class", "no-class"
            elif record:
                code_map = {
                    AttendanceRecord.Status.PRESENT: "✓",
                    AttendanceRecord.Status.ABSENT: "A",
                    AttendanceRecord.Status.LATE: "L",
                    AttendanceRecord.Status.EXCUSED: "E",
                }
                code = code_map[record.status]
                title = record.get_status_display()
                css_class = record.status
                if record.status == AttendanceRecord.Status.ABSENT:
                    absent_total += 1
                if record.status == AttendanceRecord.Status.LATE:
                    late_total += 1
                if record.remarks:
                    remarks.append(f"{report_date.day}: {record.remarks}")
            cells.append({
                "date": report_date,
                "code": code,
                "title": title,
                "css_class": css_class,
            })
        monthly_rows.append({
            "student": student,
            "cells": cells,
            "absent_total": absent_total,
            "late_total": late_total,
            "remarks": "; ".join(remarks),
        })

    return render(request, "classroom/attendance.html", {
        "classroom": classroom,
        "is_teacher": True,
        "view_mode": view_mode,
        "selected_date": selected_date,
        "selected_month": selected_month,
        "attendance_day": attendance_day,
        "daily_rows": daily_rows,
        "status_choices": AttendanceRecord.Status.choices,
        "day_type_choices": AttendanceDay.DayType.choices,
        "monthly_columns": monthly_columns,
        "monthly_rows": monthly_rows,
    })

# =========================================================
# ROLE-BASED CLASSROOM CALENDAR
# =========================================================

def _calendar_date(value):
    """Return a date using the project's local timezone."""
    if timezone.is_aware(value):
        return timezone.localtime(value).date()
    return value.date()


def _calendar_item_from_event(event):
    start_date = _calendar_date(event.start_at)
    end_date = _calendar_date(event.end_at) if event.end_at else start_date

    return {
        "event_id": event.pk,
        "title": event.title,
        "description": event.description,
        "start_date": start_date,
        "end_date": end_date,
        "event_type": event.event_type,
        "event_type_label": event.get_event_type_display(),
        "level": event.level,
        "level_label": event.get_level_display(),
        "classroom": event.classroom,
        "source": event.source,
        "is_editable": event.level == CalendarEvent.Level.CLASSROOM,
        "is_module_deadline": False,
    }


def _calendar_item_from_module(module):
    due_date = _calendar_date(module.due_at)

    return {
        "event_id": None,
        "title": f"{module.title} Due",
        "description": module.instructions,
        "start_date": due_date,
        "end_date": due_date,
        "event_type": CalendarEvent.EventType.DEADLINE,
        "event_type_label": "Module deadline",
        "level": "module",
        "level_label": "Module deadline",
        "classroom": module.classroom,
        "source": "",
        "is_editable": False,
        "is_module_deadline": True,
    }


def _collect_calendar_items(school, classrooms):
    """Collect official, school, class, and module events."""
    classrooms = list(classrooms)

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
    )

    school_events = CalendarEvent.objects.filter(
        level=CalendarEvent.Level.SCHOOL,
        school=school,
        status=CalendarEvent.Status.PUBLISHED,
    )

    class_events = CalendarEvent.objects.filter(
        level=CalendarEvent.Level.CLASSROOM,
        classroom__in=classrooms,
        status=CalendarEvent.Status.PUBLISHED,
    ).select_related("classroom")

    modules = Module.objects.filter(
        classroom__in=classrooms,
        status=Module.Status.PUBLISHED,
        due_at__isnull=False,
    ).select_related("classroom")

    items = [
        _calendar_item_from_event(event)
        for event in list(district_events)
        + list(school_events)
        + list(class_events)
    ]

    items.extend(
        _calendar_item_from_module(module)
        for module in modules
    )

    return items


def _class_event_conflicts_with_no_class(event, school):
    """Return True when a class event overlaps an official non-class day."""
    official_events = (
        CalendarEvent.objects
        .filter(
            status=CalendarEvent.Status.PUBLISHED,
            event_type__in=[
                CalendarEvent.EventType.HOLIDAY,
                CalendarEvent.EventType.NO_CLASS,
            ],
        )
        .filter(
            Q(
                level=CalendarEvent.Level.DISTRICT,
                applies_to_all_schools=True,
            )
            | Q(
                level=CalendarEvent.Level.DISTRICT,
                target_schools=school,
            )
            | Q(
                level=CalendarEvent.Level.SCHOOL,
                school=school,
            )
        )
        .distinct()
    )

    candidate_start = _calendar_date(event.start_at)
    candidate_end = (
        _calendar_date(event.end_at)
        if event.end_at
        else candidate_start
    )

    for official_event in official_events:
        official_start = _calendar_date(official_event.start_at)
        official_end = (
            _calendar_date(official_event.end_at)
            if official_event.end_at
            else official_start
        )
        if candidate_start <= official_end and candidate_end >= official_start:
            return True

    return False


def _build_classroom_calendar_month(request, items):
    today = timezone.localdate()

    try:
        selected_year = int(request.GET.get("year", today.year))
        selected_month = int(request.GET.get("month", today.month))
        if selected_month not in range(1, 13):
            raise ValueError
    except (TypeError, ValueError):
        selected_year = today.year
        selected_month = today.month

    weeks = []
    month_dates = month_calendar.Calendar(
        firstweekday=6
    ).monthdatescalendar(selected_year, selected_month)

    for week in month_dates:
        cells = []
        for day in week:
            day_items = [
                item
                for item in items
                if item["start_date"] <= day <= item["end_date"]
            ]
            cells.append({
                "date": day,
                "is_current_month": day.month == selected_month,
                "is_today": day == today,
                "is_weekend": day.weekday() >= 5,
                "events": day_items,
            })
        weeks.append(cells)

    if selected_month == 1:
        previous_year, previous_month = selected_year - 1, 12
    else:
        previous_year, previous_month = selected_year, selected_month - 1

    if selected_month == 12:
        next_year, next_month = selected_year + 1, 1
    else:
        next_year, next_month = selected_year, selected_month + 1

    return {
        "calendar_weeks": weeks,
        "calendar_month_name": month_calendar.month_name[selected_month],
        "calendar_year": selected_year,
        "previous_year": previous_year,
        "previous_month": previous_month,
        "next_year": next_year,
        "next_month": next_month,
    }

def _build_student_module_tasks(student, classroom_id=None):
    """
    Build task cards from published Modules and the Student's submissions.
    This does not create another database table.
    """

    approved_classrooms = Classroom.objects.filter(
        enrollments__student=student,
        enrollments__status=ClassEnrollment.Status.APPROVED,
        is_archived=False,
    ).distinct()

    if classroom_id:
        approved_classrooms = approved_classrooms.filter(
            pk=classroom_id,
        )

    modules = (
        Module.objects.filter(
            classroom__in=approved_classrooms,
            status=Module.Status.PUBLISHED,
        )
        .select_related("classroom")
        .order_by("due_at", "-published_at", "-created_at")
    )

    submissions = {
        submission.module_id: submission
        for submission in ModuleSubmission.objects.filter(
            student=student,
            module__in=modules,
        ).select_related("module")
    }

    now = timezone.now()
    due_soon_limit = now + timedelta(days=7)
    tasks = []

    for module in modules:
        submission = submissions.get(module.pk)

        if submission is None:
            status = "to_do"
            status_label = "To Do"
            action_label = "Start"

        elif submission.status == ModuleSubmission.Status.DRAFT:
            status = "in_progress"
            status_label = "In Progress"
            action_label = "Continue"

        elif submission.status == ModuleSubmission.Status.SUBMITTED:
            status = "submitted"
            status_label = "Submitted"
            action_label = "View Submission"

        elif submission.status == ModuleSubmission.Status.RETURNED:
            status = "returned"
            status_label = "Returned"
            action_label = "Revise"

        else:
            status = "completed"
            status_label = "Completed"
            action_label = "View Result"

        is_overdue = bool(
            module.due_at
            and module.due_at < now
            and status in {
                "to_do",
                "in_progress",
                "returned",
            }
        )

        is_due_soon = bool(
            module.due_at
            and now <= module.due_at <= due_soon_limit
            and status not in {
                "submitted",
                "completed",
            }
        )

        tasks.append({
            "module": module,
            "submission": submission,
            "status": status,
            "status_label": status_label,
            "action_label": action_label,
            "is_due_soon": is_due_soon,
            "is_overdue": is_overdue,
            "url": reverse(
                "classroom:module_work",
                args=[module.pk],
            ),
        })

    return tasks

def _build_task_overview(tasks):
    """
    Calculate the weekly deadlines and Student task progress.
    """

    status_counts = {
        "to_do": 0,
        "in_progress": 0,
        "submitted": 0,
        "returned": 0,
        "completed": 0,
    }

    for task in tasks:
        status = task["status"]

        if status in status_counts:
            status_counts[status] += 1

    total_tasks = len(tasks)
    completed_tasks = status_counts["completed"]

    if total_tasks:
        progress_percent = round(
            (completed_tasks / total_tasks) * 100
        )
    else:
        progress_percent = 0

    week_tasks = sorted(
        [
            task
            for task in tasks
            if task["is_due_soon"]
        ],
        key=lambda task: task["module"].due_at,
    )[:5]

    return {
        "status_counts": status_counts,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks,
        "progress_percent": progress_percent,
        "week_tasks": week_tasks,
    }

@login_required(login_url="accounts:login")
def tasks_view(request):
    user = request.user
    selected_status = request.GET.get("status", "all")
    selected_classroom_id = request.GET.get("classroom")

    valid_statuses = {
        "all",
        "to_do",
        "in_progress",
        "submitted",
        "returned",
        "completed",
    }

    if selected_status not in valid_statuses:
        selected_status = "all"

    # =====================================================
    # TEACHER TASKS
    # =====================================================

    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)

        if teacher is None:
            messages.error(
                request,
                "Your Teacher profile was not found.",
            )
            return redirect("classroom:dashboard")

        classrooms = Classroom.objects.filter(
            teacher=teacher,
            is_archived=False,
        )

        modules = Module.objects.filter(
            classroom__teacher=teacher,
            classroom__is_archived=False,
        )

        if selected_classroom_id:
            if classrooms.filter(pk=selected_classroom_id).exists():
                modules = modules.filter(
                    classroom_id=selected_classroom_id,
                )
            else:
                selected_classroom_id = None

        modules = modules.select_related(
            "classroom",
        ).annotate(
            review_count=Count(
                "submissions",
                filter=Q(
                    submissions__status=(
                        ModuleSubmission.Status.SUBMITTED
                    )
                ),
            )
        )

        now = timezone.now()
        due_soon_limit = now + timedelta(days=7)

        review_modules = modules.filter(
            review_count__gt=0,
        ).order_by("-review_count", "due_at")

        draft_modules = modules.filter(
            status=Module.Status.DRAFT,
        ).order_by("-created_at")

        due_modules = modules.filter(
            status=Module.Status.PUBLISHED,
            due_at__gte=now,
            due_at__lte=due_soon_limit,
        ).order_by("due_at")

        teacher_summary = {
            "needs_review": sum(
                module.review_count
                for module in review_modules
            ),
            "due_soon": due_modules.count(),
            "drafts": draft_modules.count(),
            "published": modules.filter(
                status=Module.Status.PUBLISHED,
            ).count(),
        }

        return render(
            request,
            "classroom/tasks.html",
            {
                "role_view": "teacher",
                "classrooms": classrooms,
                "selected_classroom_id": selected_classroom_id,
                "review_modules": review_modules,
                "draft_modules": draft_modules,
                "due_modules": due_modules,
                "task_summary": teacher_summary,
            },
        )

    # =====================================================
    # STUDENT TASKS
    # =====================================================

    if user.role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)

        if student is None:
            messages.error(
                request,
                "Your Student profile was not found.",
            )
            return redirect("classroom:dashboard")

        classrooms = Classroom.objects.filter(
            enrollments__student=student,
            enrollments__status=ClassEnrollment.Status.APPROVED,
            is_archived=False,
        ).distinct()

        if (
            selected_classroom_id
            and not classrooms.filter(
                pk=selected_classroom_id,
            ).exists()
        ):
            selected_classroom_id = None

        tasks = _build_student_module_tasks(
            student,
            selected_classroom_id,
        )

        task_overview = _build_task_overview(tasks)

        task_summary = {
            "to_do": sum(
                task["status"] == "to_do"
                for task in tasks
            ),
            "due_soon": sum(
                task["is_due_soon"]
                for task in tasks
            ),
            "returned": sum(
                task["status"] == "returned"
                for task in tasks
            ),
            "completed": sum(
                task["status"] == "completed"
                for task in tasks
            ),
        }

        if selected_status != "all":
            visible_tasks = [
                task
                for task in tasks
                if task["status"] == selected_status
            ]
        else:
            visible_tasks = tasks

        due_soon_tasks = [
            task
            for task in visible_tasks
            if task["is_due_soon"] or task["is_overdue"]
        ]

        later_tasks = [
            task
            for task in visible_tasks
            if task not in due_soon_tasks
        ]

        return render(
            request,
            "classroom/tasks.html",
            {
                "role_view": "student",
                "read_only": False,
                "classrooms": classrooms,
                "selected_classroom_id": selected_classroom_id,
                "selected_status": selected_status,
                "task_summary": task_summary,
                "due_soon_tasks": due_soon_tasks,
                "later_tasks": later_tasks,
                "task_overview": task_overview,
            },
        )

    # =====================================================
    # PARENT TASK MONITORING
    # =====================================================

    if user.role == User.Role.PARENT:
        parent = getattr(user, "parent_profile", None)

        if parent is None:
            messages.error(
                request,
                "Your Parent profile was not found.",
            )
            return redirect("classroom:dashboard")

        linked_students = ParentStudentLink.objects.filter(
            parent=parent,
            status=ParentStudentLink.Status.APPROVED,
        ).select_related(
            "student",
            "student__user",
        )

        selected_learner_id = request.GET.get("learner")
        selected_link = None

        if selected_learner_id:
            selected_link = linked_students.filter(
                student_id=selected_learner_id,
            ).first()

        if selected_link is None:
            selected_link = linked_students.first()

        selected_student = (
            selected_link.student
            if selected_link
            else None
        )

        tasks = []
        task_overview = _build_task_overview(tasks)

        if selected_student:
            tasks = _build_student_module_tasks(
                selected_student,
                selected_classroom_id,
            )

            task_overview = _build_task_overview(tasks)

        task_summary = {
            "to_do": sum(
                task["status"] == "to_do"
                for task in tasks
            ),
            "due_soon": sum(
                task["is_due_soon"]
                for task in tasks
            ),
            "returned": sum(
                task["status"] == "returned"
                for task in tasks
            ),
            "completed": sum(
                task["status"] == "completed"
                for task in tasks
            ),
        }

        if selected_status != "all":
            visible_tasks = [
                task
                for task in tasks
                if task["status"] == selected_status
            ]
        else:
            visible_tasks = tasks

        due_soon_tasks = [
            task
            for task in visible_tasks
            if task["is_due_soon"] or task["is_overdue"]
        ]

        later_tasks = [
            task
            for task in visible_tasks
            if task not in due_soon_tasks
        ]

        return render(
            request,
            "classroom/tasks.html",
            {
                "role_view": "parent",
                "read_only": True,
                "linked_students": linked_students,
                "selected_student": selected_student,
                "selected_status": selected_status,
                "task_summary": task_summary,
                "due_soon_tasks": due_soon_tasks,
                "later_tasks": later_tasks,
                "task_overview": task_overview,
            },
        )

    return redirect("classroom:dashboard")

@login_required(login_url="accounts:login")
def calendar_view(request):
    user = request.user
    event_form = None
    selected_classroom = None
    selected_learner = None
    editing_event = None
    linked_students = []
    calendar_title = "My Calendar"
    calendar_subtitle = "View your schedules and important dates."
    read_only = True

    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)
        if teacher is None:
            messages.error(request, "Your Teacher profile was not found.")
            return redirect("classroom:dashboard")

        available_classrooms = Classroom.objects.filter(
            teacher=teacher,
            is_archived=False,
        ).order_by("subject", "section")

        edit_event_id = request.POST.get("event_id") or request.GET.get("edit_event")
        if edit_event_id:
            editing_event = get_object_or_404(
                CalendarEvent.objects.exclude(status=CalendarEvent.Status.CANCELLED),
                pk=edit_event_id,
                level=CalendarEvent.Level.CLASSROOM,
                classroom__teacher=teacher,
            )
            selected_classroom = editing_event.classroom
        else:
            selected_id = request.POST.get("classroom_id") or request.GET.get("classroom_id")
            if selected_id:
                selected_classroom = available_classrooms.filter(pk=selected_id).first()
            if selected_classroom is None:
                selected_classroom = available_classrooms.first()

        classrooms = [selected_classroom] if selected_classroom else []
        school = teacher.school
        calendar_title = "Class Calendar"
        calendar_subtitle = "Manage class events and view locked official dates."
        read_only = False
        event_form = ClassCalendarEventForm(
            request.POST or None,
            instance=editing_event,
        )

        if request.method == "POST":
            if selected_classroom is None:
                messages.error(request, "Create or select a class first.")
            elif event_form.is_valid():
                is_new = event_form.instance.pk is None
                event = event_form.save(commit=False)
                event.level = CalendarEvent.Level.CLASSROOM
                event.classroom = selected_classroom
                event.school = None
                event.school_year = selected_classroom.school_year
                if is_new:
                    event.created_by = user
                event.status = CalendarEvent.Status.PUBLISHED
                event.applies_to_all_schools = False

                event_date = timezone.localtime(event.start_at).date()

                if event_date.weekday() >= 5:
                    event_form.add_error(
                        "start_at",
                        "Saturday and Sunday are default no-class days.",
                    )
                elif _class_event_conflicts_with_no_class(event, teacher.school):
                    event_form.add_error(
                        "start_at",
                        "This date is an official holiday or no-class day.",
                    )
                else:
                    event.save()
                    notify_calendar_event(
                        event,
                        "created" if is_new else "updated",
                    )

                    messages.success(
                        request,
                        "The class event was added." if is_new else "The class event was updated.",
                    )
                    return redirect(
                        f"{reverse('classroom:calendar')}?classroom_id={selected_classroom.pk}"
                    )

    elif user.role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)
        if student is None:
            messages.error(request, "Your Student profile was not found.")
            return redirect("classroom:dashboard")

        available_classrooms = Classroom.objects.filter(
            enrollments__student=student,
            enrollments__status=ClassEnrollment.Status.APPROVED,
            is_archived=False,
        ).distinct().order_by("subject", "section")
        classrooms = list(available_classrooms)
        school = student.school
        calendar_title = "My Calendar"
        calendar_subtitle = "View school events, class activities, and module deadlines."

    elif user.role == User.Role.PARENT:
        parent = getattr(user, "parent_profile", None)
        if parent is None:
            messages.error(request, "Your Parent profile was not found.")
            return redirect("classroom:dashboard")

        linked_students = list(
            Student.objects.filter(
                parent_links__parent=parent,
                parent_links__status=ParentStudentLink.Status.APPROVED,
            ).select_related("school").distinct().order_by("lastname", "firstname")
        )

        learner_id = request.GET.get("learner_id")
        if learner_id:
            selected_learner = next(
                (student for student in linked_students if str(student.pk) == learner_id),
                None,
            )
        if selected_learner is None and linked_students:
            selected_learner = linked_students[0]

        if selected_learner:
            available_classrooms = Classroom.objects.filter(
                enrollments__student=selected_learner,
                enrollments__status=ClassEnrollment.Status.APPROVED,
                is_archived=False,
            ).distinct().order_by("subject", "section")
            classrooms = list(available_classrooms)
            school = selected_learner.school
        else:
            available_classrooms = Classroom.objects.none()
            classrooms = []
            school = None

        calendar_title = "Learner Calendar"
        calendar_subtitle = "View the schedule of your connected learner."

    else:
        messages.error(request, "This calendar belongs to the Classroom Portal.")
        return redirect("classroom:dashboard")

    items = _collect_calendar_items(school, classrooms) if school else []

    selected_filter = request.GET.get("filter", "all")
    if selected_filter not in {"all", "school", "classes", "deadlines"}:
        selected_filter = "all"

    if selected_filter == "school":
        items = [item for item in items if item["level"] in {"district", "school"}]
    elif selected_filter == "classes":
        items = [item for item in items if item["level"] == "classroom"]
    elif selected_filter == "deadlines":
        items = [item for item in items if item["event_type"] == "deadline"]

    today = timezone.localdate()
    upcoming_events = sorted(
        [item for item in items if item["end_date"] >= today],
        key=lambda item: (item["start_date"], item["title"]),
    )[:8]

    calendar_context = _build_classroom_calendar_month(request, items)

    return render(request, "classroom/calendar.html", {
        "calendar_title": calendar_title,
        "calendar_subtitle": calendar_subtitle,
        "read_only": read_only,
        "event_form": event_form,
        "available_classrooms": available_classrooms,
        "selected_classroom": selected_classroom,
        "linked_students": linked_students,
        "selected_learner": selected_learner,
        "editing_event": editing_event,
        "selected_filter": selected_filter,
        "calendar_items": items,
        "upcoming_events": upcoming_events,
        **calendar_context,
    })


@login_required(login_url="accounts:login")
@require_POST
def class_calendar_event_cancel_view(request, event_id):
    if request.user.role != User.Role.TEACHER:
        raise PermissionDenied("Only Teachers can cancel class events.")

    teacher = getattr(request.user, "teacher_profile", None)
    if teacher is None:
        raise PermissionDenied("Teacher profile not found.")

    event = get_object_or_404(
        CalendarEvent,
        pk=event_id,
        level=CalendarEvent.Level.CLASSROOM,
        classroom__teacher=teacher,
    )
    classroom_id = event.classroom_id
    event.status = CalendarEvent.Status.CANCELLED
    event.save(update_fields=["status", "updated_at"])
    notify_calendar_event(event, "cancelled")

    messages.success(request, "The class event was cancelled.")
    return redirect(
        f"{reverse('classroom:calendar')}?classroom_id={classroom_id}"
    )


def _private_file_response(
    field,
    filename,
    content_type,
    *,
    as_attachment=True,
):
    if not field:
        raise Http404("File not found.")

    try:
        file = field.open("rb")
    except OSError:
        raise Http404("File not found.")

    response = FileResponse(
        file,
        as_attachment=as_attachment,
        filename=filename,
        content_type=content_type,
    )

    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"

    return response


@login_required(login_url="accounts:login")
def module_pdf_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(
        request,
        module_id,
    )

    pdf_file = module.pdf if is_teacher else (module.student_pdf or module.pdf)
    return _private_file_response(
        pdf_file,
        "module.pdf",
        "application/pdf",
        as_attachment=False,
    )


@login_required(login_url="accounts:login")
def module_attachment_view(request, submission_id):
    submission = get_object_or_404(
        ModuleSubmission,
        pk=submission_id,
    )

    module, classroom, is_teacher, student = _get_module_access(
        request,
        submission.module_id,
    )

    if is_teacher:
        if submission.status == ModuleSubmission.Status.DRAFT:
            raise PermissionDenied(
                "Student drafts are private."
            )

    elif submission.student_id != student.pk:
        raise PermissionDenied(
            "You cannot open another Student's answer."
        )

    extension = Path(submission.answer_file.name).suffix.lower()

    content_types = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }

    return _private_file_response(
        submission.answer_file,
        f"student-answer{extension}",
        content_types.get(
            extension,
            "application/octet-stream",
        ),
    )


@login_required(login_url="accounts:login")
def submission_pdf_view(request, submission_id):
    submission = get_object_or_404(
        ModuleSubmission.objects.select_related("module", "student"),
        pk=submission_id,
    )
    module, classroom, is_teacher, student = _get_module_access(
        request,
        submission.module_id,
    )
    if is_teacher:
        if submission.status == ModuleSubmission.Status.DRAFT:
            raise PermissionDenied("Student drafts are private.")
    elif submission.student_id != student.pk:
        raise PermissionDenied("You cannot open another Student's Module.")
    if not submission.answered_pdf:
        raise Http404("Answered PDF not found.")
    return _private_file_response(
        submission.answered_pdf,
        f"{module.title}-answered.pdf",
        "application/pdf",
        as_attachment=False,
    )


@login_required(login_url="accounts:login")
def section_attachment_view(request, attachment_id):
    attachment = get_object_or_404(
        SubmissionAttachment.objects.select_related(
            "response__submission__module", "response__submission__student"
        ),
        pk=attachment_id,
    )
    submission = attachment.response.submission
    module, classroom, is_teacher, student = _get_module_access(request, submission.module_id)
    if not is_teacher and submission.student_id != student.pk:
        raise PermissionDenied("You cannot open another Student's answer.")
    if is_teacher and submission.status == ModuleSubmission.Status.DRAFT:
        raise PermissionDenied("Student drafts are private.")
    extension = Path(attachment.file.name).suffix.lower()
    content_types = {
        ".pdf": "application/pdf", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".png": "image/png",
    }
    return _private_file_response(
        attachment.file,
        attachment.original_name,
        content_types.get(extension, "application/octet-stream"),
    )

@login_required(login_url="accounts:login")
def parent_progress_view(request):
    if request.user.role != User.Role.PARENT:
        return redirect("classroom:dashboard")

    parent = getattr(
        request.user,
        "parent_profile",
        None,
    )

    if parent is None:
        return redirect("classroom:dashboard")

    linked_students = ParentStudentLink.objects.filter(
        parent=parent,
        status=ParentStudentLink.Status.APPROVED,
    ).select_related(
        "student",
        "student__user",
    )

    selected_link = linked_students.filter(
        student_id=request.GET.get("learner"),
    ).first()

    if selected_link is None:
        selected_link = linked_students.first()

    selected_student = (
        selected_link.student
        if selected_link
        else None
    )

    active_tab = request.GET.get("tab", "grades")

    if active_tab not in {"grades", "attendance"}:
        active_tab = "grades"

    classrooms = Classroom.objects.none()
    selected_classroom = None
    grade_rows = []
    attendance_summary = None

    if selected_student:
        classrooms = Classroom.objects.filter(
            enrollments__student=selected_student,
            enrollments__status=ClassEnrollment.Status.APPROVED,
            is_archived=False,
        ).distinct()

        if active_tab == "grades":
            grade_rows = build_released_student_summary(
                selected_student,
                classrooms,
            )

        else:
            selected_classroom = classrooms.filter(
                pk=request.GET.get("classroom"),
            ).first()

            if selected_classroom is None:
                selected_classroom = classrooms.first()

            if selected_classroom:
                selected_month = parse_month(
                    request.GET.get("month")
                )

                attendance_summary = build_parent_attendance(
                    selected_student,
                    selected_classroom,
                    selected_month,
                )

    return render(
        request,
        "classroom/parent_progress.html",
        {
            "linked_students": linked_students,
            "selected_student": selected_student,
            "classrooms": classrooms,
            "selected_classroom": selected_classroom,
            "grade_rows": grade_rows,
            "attendance_summary": attendance_summary,
            "active_tab": active_tab,
        },
    )
