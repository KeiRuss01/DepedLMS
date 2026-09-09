from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ParentStudentLink, Student, User

from .forms import (
    ClassroomForm,
    InviteStudentForm,
    JoinClassForm,
    StudentLinkRequestForm,
)
from .models import Classroom, ClassEnrollment

from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.views.decorators.http import require_http_methods

from .models import (
    Module,
    ModuleItem,
    ModuleSubmission,
    ModuleAnswer,
)

from .module_forms import (
    ModuleCreateForm,
    ModuleItemFormSet,
    StudentModuleForm,
    ModuleGradeForm,
)


@login_required(login_url="accounts:login")
def dashboard_view(request):
    user = request.user

    if user.role == User.Role.TEACHER:
        teacher = getattr(user, "teacher_profile", None)

        if teacher is None:
            messages.error(request, "Your Teacher profile was not found.")
            return redirect("accounts:login")

        classrooms = Classroom.objects.filter(
            teacher=teacher,
            is_archived=False,
        )[:3]

        join_requests = ClassEnrollment.objects.filter(
            classroom__teacher=teacher,
            status=ClassEnrollment.Status.PENDING_TEACHER,
        ).select_related(
            "classroom",
            "student",
            "student__user",
        )[:5]

        return render(
            request,
            "classroom/teacher_dashboard.html",
            {
                "classrooms": classrooms,
                "join_requests": join_requests,
            },
        )

    if user.role == User.Role.STUDENT:
        student = getattr(user, "student_profile", None)

        if student is None:
            messages.error(request, "Your Student profile was not found.")
            return redirect("accounts:login")

        enrollments = ClassEnrollment.objects.filter(
            student=student,
            status=ClassEnrollment.Status.APPROVED,
            classroom__is_archived=False,
        ).select_related(
            "classroom",
            "classroom__teacher",
        )[:3]

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

        return render(
            request,
            "classroom/student_dashboard.html",
            {
                "enrollments": enrollments,
                "invitations": invitations,
                "parent_requests": parent_requests,
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

    if active_tab == "modules":
        return redirect(
            "classroom:module_list",
            classroom_id=classroom_id,
        )

    if active_tab not in allowed_tabs:
        active_tab = "stream"

    is_teacher = False
    is_student = False

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

    return render(
        request,
        "classroom/class_page.html",
        {
            "classroom": classroom,
            "active_tab": active_tab,
            "is_teacher": is_teacher,
            "is_student": is_student,
            "enrolled_students": enrolled_students,
        },
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
        with transaction.atomic():
            module = form.save(commit=False)
            module.classroom = classroom
            module.status = Module.Status.DRAFT
            module.save()

            if module.answer_mode == Module.AnswerMode.STRUCTURED:
                count = form.cleaned_data["number_of_items"]
                answer_type = form.cleaned_data["default_answer_type"]

                for position in range(1, count + 1):
                    ModuleItem.objects.create(
                        module=module,
                        position=position,
                        label=f"Item {position}",
                        answer_type=answer_type,
                    )

        messages.success(
            request,
            "Draft created. Review the answer fields before publishing.",
        )

        return redirect(
            "classroom:module_manage",
            module_id=module.pk,
        )

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

    formset = None

    if request.method == "POST":
        action = request.POST.get("action")

        if action not in ["save", "publish"]:
            raise PermissionDenied("Invalid action.")

        with transaction.atomic():
            module = get_object_or_404(
                Module.objects.select_for_update(),
                pk=module.pk,
            )

            if module.status != Module.Status.DRAFT:
                messages.error(
                    request,
                    "Published modules cannot be changed in this version.",
                )
                return redirect(
                    "classroom:module_manage",
                    module_id=module.pk,
                )

            valid = True

            if module.answer_mode == Module.AnswerMode.STRUCTURED:
                formset = ModuleItemFormSet(
                    request.POST,
                    queryset=module.items.all(),
                    prefix="items",
                )

                valid = formset.is_valid()

                if not module.items.exists():
                    valid = False
                    messages.error(
                        request,
                        "A numbered answer sheet needs at least one item.",
                    )

                if valid:
                    formset.save()

            if valid:
                if action == "publish":
                    module.status = Module.Status.PUBLISHED
                    module.published_at = timezone.now()
                    module.save(
                        update_fields=["status", "published_at"]
                    )

                    messages.success(
                        request,
                        "Module published to enrolled Students.",
                    )
                else:
                    messages.success(
                        request,
                        "Answer fields saved.",
                    )

                return redirect(
                    "classroom:module_manage",
                    module_id=module.pk,
                )

    elif (
        module.status == Module.Status.DRAFT
        and module.answer_mode == Module.AnswerMode.STRUCTURED
    ):
        formset = ModuleItemFormSet(
            queryset=module.items.all(),
            prefix="items",
        )

    return render(
        request,
        "classroom/modules/live_manage.html",
        {
            "classroom": classroom,
            "module": module,
            "formset": formset,
            "is_teacher": True,
        },
    )

@login_required(login_url="accounts:login")
@require_http_methods(["GET", "POST"])
def module_work_view(request, module_id):
    module, classroom, is_teacher, student = _get_module_access(
        request,
        module_id,
    )

    submission = None

    if student:
        submission = ModuleSubmission.objects.filter(
            module=module,
            student=student,
        ).first()

    locked = bool(
        submission
        and submission.status != ModuleSubmission.Status.DRAFT
    )

    deadline_closed = bool(
        module.due_at
        and timezone.now() > module.due_at
        and not module.allow_late
    )

    action = request.POST.get("action")
    complete = action == "submit"

    form = StudentModuleForm(
        module,
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        submission=submission,
        complete=complete,
    )

    if request.method == "POST":
        if is_teacher:
            raise PermissionDenied(
                "The Teacher preview cannot submit student answers."
            )

        if action not in ["draft", "submit"]:
            form.add_error(None, "Choose Save draft or Submit.")

        elif locked:
            form.add_error(
                None,
                "This work has already been submitted.",
            )

        elif deadline_closed:
            form.add_error(
                None,
                "The deadline has passed and late submissions are closed.",
            )

        elif form.is_valid():
            with transaction.atomic():
                # Lock this enrollment while saving to prevent duplicate
                # submissions from simultaneous requests.
                get_object_or_404(
                    ClassEnrollment.objects.select_for_update(),
                    classroom=classroom,
                    student=student,
                    status=ClassEnrollment.Status.APPROVED,
                )

                saved, created = ModuleSubmission.objects.get_or_create(
                    module=module,
                    student=student,
                )

                saved = ModuleSubmission.objects.select_for_update().get(
                    pk=saved.pk,
                )

                if saved.status != ModuleSubmission.Status.DRAFT:
                    messages.error(
                        request,
                        "This work has already been submitted.",
                    )
                    return redirect(
                        "classroom:module_work",
                        module_id=module.pk,
                    )

                # Recheck the deadline immediately before saving.
                if (
                    module.due_at
                    and timezone.now() > module.due_at
                    and not module.allow_late
                ):
                    messages.error(request, "Submissions are closed.")
                    return redirect(
                        "classroom:module_work",
                        module_id=module.pk,
                    )

                if module.answer_mode == Module.AnswerMode.STRUCTURED:
                    for item in module.items.all():
                        ModuleAnswer.objects.update_or_create(
                            submission=saved,
                            item=item,
                            defaults={
                                "answer_text": form.cleaned_data[
                                    f"item_{item.pk}"
                                ],
                            },
                        )

                elif module.answer_mode == Module.AnswerMode.WRITTEN:
                    saved.written_answer = form.cleaned_data[
                        "written_answer"
                    ]

                else:
                    upload = form.cleaned_data.get("answer_file")

                    if upload:
                        saved.answer_file = upload

                if complete:
                    saved.status = ModuleSubmission.Status.SUBMITTED
                    saved.submitted_at = timezone.now()

                saved.save()

            messages.success(
                request,
                "Module submitted." if complete else "Draft saved.",
            )

            return redirect(
                "classroom:module_work",
                module_id=module.pk,
            )

    can_edit = (
        not is_teacher
        and not locked
        and not deadline_closed
    )

    return render(
        request,
        "classroom/modules/live_work.html",
        {
            "classroom": classroom,
            "module": module,
            "submission": submission,
            "form": form,
            "is_teacher": is_teacher,
            "can_edit": can_edit,
            "deadline_closed": deadline_closed,
        },
    )

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

    form = ModuleGradeForm(
        module,
        request.POST if request.method == "POST" else None,
        initial={
            "score": submission.score,
            "feedback": submission.feedback,
        },
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            submission = get_object_or_404(
                ModuleSubmission.objects.select_for_update(),
                pk=submission.pk,
                status__in=[
                    ModuleSubmission.Status.SUBMITTED,
                    ModuleSubmission.Status.GRADED,
                ],
            )

            submission.score = form.cleaned_data["score"]
            submission.feedback = form.cleaned_data["feedback"]
            submission.status = ModuleSubmission.Status.GRADED
            submission.graded_at = timezone.now()

            submission.save(
                update_fields=[
                    "score",
                    "feedback",
                    "status",
                    "graded_at",
                    "updated_at",
                ]
            )

        messages.success(
            request,
            "Score and feedback are now visible to the Student.",
        )

        return redirect(
            "classroom:module_review",
            submission_id=submission.pk,
        )

    saved_answers = dict(
        submission.answers.values_list(
            "item_id",
            "answer_text",
        )
    )

    answer_rows = [
        {
            "label": item.label,
            "answer": saved_answers.get(item.pk, ""),
        }
        for item in module.items.all()
    ]

    return render(
        request,
        "classroom/modules/live_review.html",
        {
            "classroom": classroom,
            "module": module,
            "submission": submission,
            "answer_rows": answer_rows,
            "form": form,
            "is_teacher": True,
        },
    )

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

    return _private_file_response(
        module.pdf,
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
