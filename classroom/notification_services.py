"""Small notification helpers shared by classroom and administration views."""

from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    Notification,
    ParentStudentLink,
    School,
    User,
    UserPreference,
)

from .models import ClassEnrollment


def _create_notification(user, notification_type, title, message, target_url):
    """Create one notification per user and event URL."""
    notification, created = Notification.objects.get_or_create(
        recipient=user,
        notification_type=notification_type,
        target_url=target_url,
        defaults={
            "title": title,
            "message": message,
        },
    )
    return created


def _class_audience(classroom):
    """Active approved Students and their approved connected Parents."""
    student_ids = list(
        ClassEnrollment.objects.filter(
            classroom=classroom,
            status=ClassEnrollment.Status.APPROVED,
        ).values_list("student_id", flat=True)
    )

    student_user_ids = list(
        User.objects.filter(
            student_profile__student_id__in=student_ids,
            status=User.Status.ACTIVE,
        ).values_list("user_id", flat=True)
    )

    parent_user_ids = list(
        ParentStudentLink.objects.filter(
            student_id__in=student_ids,
            status=ParentStudentLink.Status.APPROVED,
            parent__user__status=User.Status.ACTIVE,
        ).values_list("parent__user_id", flat=True)
    )

    audience_ids = set(student_user_ids + parent_user_ids)
    return User.objects.filter(user_id__in=audience_ids)


def _school_audience(school):
    """Active Teachers, Students and connected Parents in one school."""
    teacher_user_ids = list(
        User.objects.filter(
            teacher_profile__school=school,
            status=User.Status.ACTIVE,
        ).values_list("user_id", flat=True)
    )

    student_ids = list(
        User.objects.filter(
            student_profile__school=school,
            status=User.Status.ACTIVE,
        ).values_list("student_profile__student_id", flat=True)
    )

    student_user_ids = list(
        User.objects.filter(
            student_profile__student_id__in=student_ids,
        ).values_list("user_id", flat=True)
    )

    parent_user_ids = list(
        ParentStudentLink.objects.filter(
            student_id__in=student_ids,
            status=ParentStudentLink.Status.APPROVED,
            parent__user__status=User.Status.ACTIVE,
        ).values_list("parent__user_id", flat=True)
    )

    audience_ids = set(
        teacher_user_ids + student_user_ids + parent_user_ids
    )
    return User.objects.filter(user_id__in=audience_ids)


def _preference_enabled(user, field_name):
    preference, created = UserPreference.objects.get_or_create(user=user)
    return getattr(preference, field_name, True)


def notify_module_published(module):
    target_url = reverse("classroom:module_work", args=[module.pk])

    due_text = ""
    if module.due_at:
        local_due = timezone.localtime(module.due_at)
        due_text = (
            " It is due on "
            f"{local_due.strftime('%B %d, %Y at %I:%M %p')}."
        )

    created_count = 0
    for user in _class_audience(module.classroom):
        created_count += _create_notification(
            user=user,
            notification_type=Notification.Type.MODULE,
            title="New module published",
            message=(
                f"{module.classroom.subject}: {module.title} "
                f"is now available.{due_text}"
            ),
            target_url=target_url,
        )
    return created_count


def notify_upcoming_module_deadline(module):
    if not module.due_at:
        return 0

    local_due = timezone.localtime(module.due_at)
    due_key = module.due_at.strftime("%Y%m%d%H%M")
    target_url = (
        reverse("classroom:module_work", args=[module.pk])
        + f"?deadline={due_key}"
    )

    created_count = 0
    for user in _class_audience(module.classroom):
        created_count += _create_notification(
            user=user,
            notification_type=Notification.Type.DEADLINE,
            title="Module deadline approaching",
            message=(
                f"{module.title} for {module.classroom.subject} is due "
                f"on {local_due.strftime('%B %d, %Y at %I:%M %p')}."
            ),
            target_url=target_url,
        )
    return created_count


def notify_class_announcement(announcement):
    target_url = (
        reverse(
            "classroom:class_page",
            args=[announcement.classroom_id],
        )
        + f"?tab=stream&announcement={announcement.pk}"
    )

    created_count = 0
    for user in _class_audience(announcement.classroom):
        created_count += _create_notification(
            user=user,
            notification_type=Notification.Type.CLASS_ANNOUNCEMENT,
            title=announcement.title,
            message=(
                f"{announcement.classroom.subject}: "
                f"{announcement.content}"
            ),
            target_url=target_url,
        )
    return created_count


def notify_school_announcement(announcement):
    target_url = reverse("classroom:dashboard") + (
        f"?school_announcement={announcement.pk}"
    )

    created_count = 0
    for user in _school_audience(announcement.school):
        created_count += _create_notification(
            user=user,
            notification_type=Notification.Type.SCHOOL_ANNOUNCEMENT,
            title=announcement.title,
            message=(
                f"{announcement.school.school_name}: "
                f"{announcement.content}"
            ),
            target_url=target_url,
        )
    return created_count


def notify_submission(submission):
    teacher_user = submission.module.classroom.teacher.user

    if not _preference_enabled(teacher_user, "new_submission_alerts"):
        return 0

    target_url = reverse(
        "classroom:module_review",
        args=[submission.pk],
    )

    created = _create_notification(
        user=teacher_user,
        notification_type=Notification.Type.SUBMISSION,
        title="New module submission",
        message=(
            f"{submission.student} submitted "
            f"{submission.module.title}."
        ),
        target_url=target_url,
    )
    return int(created)


def notify_join_request(enrollment):
    teacher_user = enrollment.classroom.teacher.user

    if not _preference_enabled(
        teacher_user,
        "pending_join_request_alerts",
    ):
        return 0

    target_url = reverse(
        "classroom:class_detail",
        args=[enrollment.classroom_id],
    )

    created = _create_notification(
        user=teacher_user,
        notification_type=Notification.Type.JOIN_REQUEST,
        title="New class join request",
        message=(
            f"{enrollment.student} requested to join "
            f"{enrollment.classroom.class_name}."
        ),
        target_url=target_url,
    )
    return int(created)


def notify_calendar_event(event, action="created"):
    """Notify Classroom Portal users affected by a calendar change."""
    action_labels = {
        "created": "New calendar event",
        "updated": "Calendar event updated",
        "cancelled": "Calendar event cancelled",
    }
    action_words = {
        "created": "was added",
        "updated": "was updated",
        "cancelled": "was cancelled",
    }

    recipient_ids = set()

    if event.level == "classroom" and event.classroom_id:
        recipient_ids.update(
            _class_audience(event.classroom).values_list("pk", flat=True)
        )
    elif event.level == "school" and event.school_id:
        recipient_ids.update(
            _school_audience(event.school).values_list("pk", flat=True)
        )
    elif event.level == "district":
        schools = (
            School.objects.all()
            if event.applies_to_all_schools
            else event.target_schools.all()
        )
        for school in schools:
            recipient_ids.update(
                _school_audience(school).values_list("pk", flat=True)
            )

    recipient_ids.discard(event.created_by_id)

    event_date = timezone.localtime(event.start_at).strftime("%B %d, %Y")
    notice_key = event.updated_at.strftime("%Y%m%d%H%M%S%f")
    target_url = (
        reverse("classroom:calendar")
        + f"?event={event.pk}&notice={notice_key}&action={action}"
    )

    created_count = 0
    for user in User.objects.filter(pk__in=recipient_ids):
        created_count += _create_notification(
            user=user,
            notification_type=Notification.Type.GENERAL,
            title=action_labels.get(action, "Calendar update"),
            message=(
                f"{event.title} {action_words.get(action, 'changed')} "
                f"for {event_date}."
            ),
            target_url=target_url,
        )

    return created_count
