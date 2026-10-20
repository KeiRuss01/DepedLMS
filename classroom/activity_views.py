from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User

from .forms import ActivityForm, ActivityReviewForm, ActivitySubmissionForm
from .gradebook import sync_activity_grade_item, sync_activity_grade_score
from .notification_services import (
    notify_activity_feedback,
    notify_activity_published,
    notify_activity_submission,
)
from .models import (
    ActivitySubmission,
    ClassEnrollment,
    Classroom,
    ClassPost,
    GradeScore,
)


def _teacher_classroom(request, classroom_id):
    if request.user.role != User.Role.TEACHER:
        raise PermissionDenied("Only a Teacher can manage class activities.")

    teacher = getattr(request.user, "teacher_profile", None)
    return get_object_or_404(
        Classroom,
        class_id=classroom_id,
        teacher=teacher,
        is_archived=False,
    )


def _activity_access(request, activity_id):
    activity = get_object_or_404(
        ClassPost.objects.select_related(
            "classroom",
            "classroom__teacher",
            "classroom__teacher__user",
        ).prefetch_related("comments__user"),
        pk=activity_id,
        post_type=ClassPost.PostType.ACTIVITY,
    )

    if request.user.role == User.Role.TEACHER:
        teacher = getattr(request.user, "teacher_profile", None)
        if teacher and activity.classroom.teacher_id == teacher.pk:
            return activity, True, None

    if request.user.role == User.Role.STUDENT and activity.is_published:
        student = getattr(request.user, "student_profile", None)
        if student and ClassEnrollment.objects.filter(
            classroom=activity.classroom,
            student=student,
            status=ClassEnrollment.Status.APPROVED,
        ).exists():
            return activity, False, student

    raise PermissionDenied("You cannot open this activity.")


@login_required(login_url="accounts:login")
def activity_create_view(request, classroom_id):
    classroom = _teacher_classroom(request, classroom_id)
    form = ActivityForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        activity = form.save(commit=False)
        activity.classroom = classroom
        activity.teacher = classroom.teacher
        activity.post_type = ClassPost.PostType.ACTIVITY
        activity.is_published = request.POST.get("action") == "publish"
        activity.allow_text_submission = True
        activity.allow_pdf_submission = True
        activity.allow_link_submission = True
        activity.save()

        if activity.is_published:
            sync_activity_grade_item(activity)
            notify_activity_published(activity)
            messages.success(request, "Activity published to the class.")
        else:
            messages.success(request, "Activity saved as a draft.")

        return redirect("classroom:activity_detail", activity_id=activity.pk)

    return render(
        request,
        "classroom/activities/form.html",
        {"classroom": classroom, "form": form, "activity": None},
    )


@login_required(login_url="accounts:login")
def activity_edit_view(request, activity_id):
    activity, is_teacher, _ = _activity_access(request, activity_id)
    if not is_teacher:
        raise PermissionDenied("Only the Teacher can edit this activity.")

    was_published = activity.is_published
    form = ActivityForm(
        request.POST or None,
        request.FILES or None,
        instance=activity,
    )

    if request.method == "POST" and form.is_valid():
        activity = form.save(commit=False)
        activity.is_published = request.POST.get("action") == "publish"
        activity.allow_text_submission = True
        activity.allow_pdf_submission = True
        activity.allow_link_submission = True
        activity.save()

        if activity.is_published:
            sync_activity_grade_item(activity)
            if not was_published:
                notify_activity_published(activity)
            messages.success(request, "Activity updated and published.")
        else:
            messages.success(request, "Activity changes saved as a draft.")

        return redirect("classroom:activity_detail", activity_id=activity.pk)

    return render(
        request,
        "classroom/activities/form.html",
        {"classroom": activity.classroom, "form": form, "activity": activity},
    )


@login_required(login_url="accounts:login")
def activity_detail_view(request, activity_id):
    activity, is_teacher, student = _activity_access(request, activity_id)
    submission = None
    submission_form = None
    submissions = None

    if is_teacher:
        submissions = activity.activity_submissions.select_related(
            "student",
            "student__user",
        ).exclude(status=ActivitySubmission.Status.DRAFT)
    else:
        submission = ActivitySubmission.objects.filter(
            activity=activity,
            student=student,
        ).first()

        locked = submission and submission.status in [
            ActivitySubmission.Status.SUBMITTED,
            ActivitySubmission.Status.GRADED,
        ]
        is_late = activity.due_date and timezone.now() > activity.due_date
        can_submit = not activity.is_closed and (
            not is_late or activity.allow_late_submission
        )

        if request.method == "POST":
            if locked:
                messages.info(request, "This submission is already locked.")
                return redirect("classroom:activity_detail", activity_id=activity.pk)
            if not can_submit:
                messages.error(request, "This activity no longer accepts submissions.")
                return redirect("classroom:activity_detail", activity_id=activity.pk)

            submission_form = ActivitySubmissionForm(
                request.POST,
                request.FILES,
                instance=submission,
                activity=activity,
            )

            if submission_form.is_valid():
                submission = submission_form.save(commit=False)
                submission.activity = activity
                submission.student = student

                if submission.method == ActivitySubmission.Method.TEXT:
                    submission.pdf_file = None
                    submission.link_url = ""
                elif submission.method == ActivitySubmission.Method.PDF:
                    submission.text_response = ""
                    submission.link_url = ""
                else:
                    submission.text_response = ""
                    submission.pdf_file = None

                if request.POST.get("action") == "submit":
                    submission.status = ActivitySubmission.Status.SUBMITTED
                    submission.submitted_at = timezone.now()
                    messages.success(request, "Your activity was submitted.")
                else:
                    submission.status = ActivitySubmission.Status.DRAFT
                    messages.success(request, "Draft saved.")

                submission.save()

                if submission.status == ActivitySubmission.Status.SUBMITTED:
                    notify_activity_submission(submission)

                return redirect(
                    "classroom:activity_detail",
                    activity_id=activity.pk,
                )
        else:
            submission_form = ActivitySubmissionForm(
                instance=submission,
                activity=activity,
            )

    submitted_statuses = [
        ActivitySubmission.Status.SUBMITTED,
        ActivitySubmission.Status.GRADED,
    ]
    return render(
        request,
        "classroom/activities/detail.html",
        {
            "classroom": activity.classroom,
            "activity": activity,
            "is_teacher": is_teacher,
            "is_student": not is_teacher,
            "submission": submission,
            "submission_form": submission_form,
            "submissions": submissions,
            "submitted_count": submissions.filter(status__in=submitted_statuses).count()
            if submissions is not None
            else 0,
            "enrolled_count": activity.classroom.enrollments.filter(
                status=ClassEnrollment.Status.APPROVED
            ).count(),
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def activity_status_view(request, activity_id):
    activity, is_teacher, _ = _activity_access(request, activity_id)
    if not is_teacher:
        raise PermissionDenied("Only the Teacher can change this activity.")

    action = request.POST.get("action")
    if action == "delete":
        classroom_id = activity.classroom_id
        activity.delete()
        messages.success(request, "Activity deleted.")
        return redirect(f"/classroom/classes/{classroom_id}/classroom/?tab=activities")
    if action in ["publish", "unpublish"]:
        was_published = activity.is_published
        activity.is_published = action == "publish"
        activity.save(update_fields=["is_published", "updated_at"])
        if activity.is_published:
            sync_activity_grade_item(activity)
            if not was_published:
                notify_activity_published(activity)
    elif action in ["close", "reopen"]:
        activity.is_closed = action == "close"
        activity.save(update_fields=["is_closed", "updated_at"])
    else:
        messages.error(request, "Invalid activity action.")
        return redirect("classroom:activity_detail", activity_id=activity.pk)

    messages.success(request, "Activity status updated.")
    return redirect("classroom:activity_detail", activity_id=activity.pk)


@login_required(login_url="accounts:login")
def activity_review_view(request, submission_id):
    submission = get_object_or_404(
        ActivitySubmission.objects.select_related(
            "activity",
            "activity__classroom",
            "student",
            "student__user",
        ),
        pk=submission_id,
    )
    if submission.status == ActivitySubmission.Status.DRAFT:
        raise PermissionDenied("A Student draft cannot be reviewed.")
    activity, is_teacher, _ = _activity_access(request, submission.activity_id)
    if not is_teacher:
        raise PermissionDenied("Only the Teacher can review this submission.")

    form = ActivityReviewForm(
        request.POST or None,
        instance=submission,
        activity=activity,
    )
    if request.method == "POST" and form.is_valid():
        submission = form.save(commit=False)
        if submission.status == ActivitySubmission.Status.GRADED:
            submission.graded_at = timezone.now()
            submission.save()
            sync_activity_grade_score(submission)
        else:
            submission.graded_at = None
            submission.save()
            GradeScore.objects.filter(
                item__activity=activity,
                student=submission.student,
            ).delete()
        notify_activity_feedback(submission)

        messages.success(request, "Review saved.")

        return redirect(
            "classroom:activity_review",
            submission_id=submission.pk,
        )

    return render(
        request,
        "classroom/activities/review.html",
        {"activity": activity, "submission": submission, "form": form},
    )


def _inline_pdf(file_field, filename):
    if not file_field:
        raise Http404("PDF not found.")
    try:
        response = FileResponse(file_field.open("rb"), content_type="application/pdf")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("PDF not found.")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


@login_required(login_url="accounts:login")
def activity_resource_view(request, activity_id):
    activity, _, _ = _activity_access(request, activity_id)
    return _inline_pdf(activity.file, f"activity-{activity.pk}.pdf")


@login_required(login_url="accounts:login")
def activity_resource_reader_view(request, activity_id):
    activity, _, _ = _activity_access(request, activity_id)
    if not activity.file:
        raise Http404("PDF not found.")
    return render(
        request,
        "classroom/activities/pdf_viewer.html",
        {
            "document_title": activity.title,
            "document_label": "Activity resource",
            "pdf_url": reverse("classroom:activity_resource", args=[activity.pk]),
            "back_url": reverse("classroom:activity_detail", args=[activity.pk]),
        },
    )


@login_required(login_url="accounts:login")
def activity_submission_pdf_view(request, submission_id):
    submission = get_object_or_404(
        ActivitySubmission.objects.select_related("activity", "student"),
        pk=submission_id,
    )
    _, is_teacher, student = _activity_access(request, submission.activity_id)
    if not is_teacher and submission.student_id != student.pk:
        raise PermissionDenied("You cannot open this submission.")
    return _inline_pdf(submission.pdf_file, f"submission-{submission.pk}.pdf")


@login_required(login_url="accounts:login")
def activity_submission_pdf_reader_view(request, submission_id):
    submission = get_object_or_404(
        ActivitySubmission.objects.select_related(
            "activity",
            "activity__classroom",
            "student",
            "student__user",
        ),
        pk=submission_id,
    )
    _, is_teacher, student = _activity_access(request, submission.activity_id)
    if not is_teacher and submission.student_id != student.pk:
        raise PermissionDenied("You cannot open this submission.")
    if not submission.pdf_file:
        raise Http404("PDF not found.")

    if is_teacher:
        back_url = reverse("classroom:activity_review", args=[submission.pk])
    else:
        back_url = reverse("classroom:activity_detail", args=[submission.activity_id])

    return render(
        request,
        "classroom/activities/pdf_viewer.html",
        {
            "document_title": f"{submission.student.user.full_name} - {submission.activity.title}",
            "document_label": "Submitted PDF",
            "pdf_url": reverse("classroom:activity_submission_pdf", args=[submission.pk]),
            "back_url": back_url,
        },
    )
