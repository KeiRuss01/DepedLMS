from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ParentStudentLink, Student, User

from .forms import (
    AnnouncementForm,
    ClassroomForm,
    InviteStudentForm,
    JoinClassForm,
    StudentLinkRequestForm,
)
from .models import Announcement, Classroom, ClassEnrollment

from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import date
import calendar as month_calendar

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.views.decorators.http import require_http_methods

from .models import (
    Module,
    ModuleAnswerSection,
    SectionQuestion,
    ModuleSubmission,
    SectionResponse,
    SectionAnswer,
    SubmissionAttachment,
)

from .module_forms import (
    ModuleCreateForm,
    AnswerSectionForm,
    SectionQuestionFormSet,
    SectionResponseForm,
    SectionGradeForm,
)
from .module_pdf_processor import build_student_pdf
from .gradebook import (
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
        linked_students = ParentStudentLink.objects.none()

        if parent:
            linked_students = ParentStudentLink.objects.filter(
                parent=parent,
                status=ParentStudentLink.Status.APPROVED,
            ).select_related(
                "student",
                "student__user",
                "student__school",
            )

        first_link = linked_students.first()
        linked_student = first_link.student if first_link else None

        return render(
            request,
            "classroom/parent_dashboard.html",
            {
                "linked_student": linked_student,
                "linked_students": linked_students,
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
                ClassEnrollment.objects.create(
                    classroom=classroom,
                    student=student,
                    status=ClassEnrollment.Status.PENDING_TEACHER,
                )

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
        announcements = classroom.announcements.select_related("posted_by")
        published_modules = classroom.modules.filter(
            status=Module.Status.PUBLISHED,
        )
        stream_items = [
            {
                "kind": "announcement",
                "created_at": announcement.created_at,
                "announcement": announcement,
            }
            for announcement in announcements
        ]
        stream_items.extend(
            {
                "kind": "module",
                "created_at": module.published_at or module.created_at,
                "module": module,
            }
            for module in published_modules
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
        },
    )


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
def announcement_create_view(request, classroom_id):
    classroom = _teacher_classroom_or_404(request, classroom_id)
    form = AnnouncementForm(request.POST)
    if form.is_valid():
        announcement = form.save(commit=False)
        announcement.classroom = classroom
        announcement.posted_by = request.user
        announcement.save()
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
        form.save()
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
                "Draft created. Add only the answer sections that exist in this module.",
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

    if request.method == "POST":
        if request.POST.get("action") != "publish":
            raise PermissionDenied("Invalid action.")
        module.status = Module.Status.PUBLISHED
        module.published_at = timezone.now()
        module.save(update_fields=["status", "published_at"])
        messages.success(request, "Module published to enrolled Students.")
        return redirect("classroom:module_manage", module_id=module.pk)

    sections = module.answer_sections.prefetch_related("questions")
    return render(
        request,
        "classroom/modules/live_manage.html",
        {
            "classroom": classroom,
            "module": module,
            "sections": sections,
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
        else:
            missing = []
            for section in module.answer_sections.filter(required=True):
                response = submission.section_responses.filter(section=section, is_complete=True).first()
                if not response:
                    missing.append(section.title)
            if missing:
                messages.error(request, "Complete these required sections first: " + ", ".join(missing))
            else:
                submission.status = ModuleSubmission.Status.SUBMITTED
                submission.submitted_at = timezone.now()
                submission.save(update_fields=["status", "submitted_at", "updated_at"])
                graded_required = submission.section_responses.filter(
                    section__required=True,
                    section__include_in_grade=True,
                )
                if graded_required.exists() and not graded_required.filter(score__isnull=True).exists():
                    submission.update_total_score()
                    sync_module_grade_score(submission)
                    submission.status = ModuleSubmission.Status.GRADED
                    submission.graded_at = timezone.now()
                    submission.save(update_fields=["status", "graded_at", "updated_at"])
                messages.success(request, "Complete module submitted to your Teacher.")
                return redirect("classroom:module_work", module_id=module.pk)

    responses = {}
    if submission:
        responses = {row.section_id: row for row in submission.section_responses.all()}
    section_rows = [
        {"section": section, "response": responses.get(section.pk)}
        for section in module.answer_sections.all()
    ]
    can_edit = not is_teacher and not locked and not deadline_closed

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
        },
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
            setattr(settings, field_name, not current_value)
            settings.save(update_fields=[field_name])
            message = "released to Students" if not current_value else "hidden from Students"
            messages.success(request, f"Term {term} Quarterly Grades are now {message}.")
            return redirect(f"{request.path}?term={term}")

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
                    AttendanceRecord.objects.update_or_create(
                        attendance_day=attendance_day,
                        student=student,
                        defaults={
                            "status": status,
                            "remarks": request.POST.get(
                                f"remarks_{student.pk}", ""
                            ).strip()[:200],
                        },
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

def _private_file_response(field, filename, content_type):
    if not field:
        raise Http404("File not found.")

    try:
        file = field.open("rb")
    except OSError:
        raise Http404("File not found.")

    response = FileResponse(
        file,
        as_attachment=True,
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
