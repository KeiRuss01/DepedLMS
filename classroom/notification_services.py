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
from .models import (
    ActivitySubmission,
    AttendanceRecord,
    ClassEnrollment,
    GradeReportSubmission,
    ModuleSubmission,
)


def notify_final_grade_report_submitted(report):
    """Notify the assigned Principal about a finalized class report."""
    notice_key = (
        report.submitted_at.strftime("%Y%m%d%H%M%S%f")
        if report.submitted_at
        else str(report.pk)
    )
    target_url = (
        reverse(
            "supervisor:principal_grade_report_detail",
            args=[report.pk],
        )
        + f"?notice={notice_key}"
    )
    principals = User.objects.filter(
        role=User.Role.PRINCIPAL,
        principal_profile__school=report.classroom.teacher.school,
        status=User.Status.ACTIVE,
    ).distinct()

    created_count = 0
    for user in principals:
        created_count += _create_notification(
            user=user,
            notification_type=Notification.Type.GENERAL,
            title="Final class report waiting for review",
            message=(
                f"{report.classroom.teacher.firstname} "
                f"{report.classroom.teacher.lastname} finalized "
                f"{report.classroom.subject} for "
                f"{report.classroom.grade_level} – "
                f"{report.classroom.section}."
            ),
            target_url=target_url,
        )
    return created_count


def notify_final_grade_report_reviewed(report):
    """Notify the Teacher and update the Supervisor's aggregate progress."""
    notice_key = (
        report.reviewed_at.strftime("%Y%m%d%H%M%S%f")
        if report.reviewed_at
        else str(report.pk)
    )
    teacher_target = (
        reverse("classroom:gradebook", args=[report.classroom_id])
        + f"?view=summary&notice={notice_key}"
    )

    approved = report.status == GradeReportSubmission.Status.APPROVED
    created_count = int(_create_notification(
        user=report.classroom.teacher.user,
        notification_type=Notification.Type.GENERAL,
        title=(
            "Final class report verified"
            if approved
            else "Final class report returned"
        ),
        message=(
            f"The Principal verified your final {report.classroom.subject} report."
            if approved
            else (
                f"The Principal returned your final {report.classroom.subject} "
                f"report. Comment: {report.principal_comment}"
            )
        ),
        target_url=teacher_target,
    ))

    if approved:
        district_target = (
            reverse("supervisor:district_performance_report")
            + f"?notice={notice_key}"
        )
        for user in User.objects.filter(
            role=User.Role.SUPERVISOR,
            status=User.Status.ACTIVE,
        ):
            created_count += _create_notification(
                user=user,
                notification_type=Notification.Type.GENERAL,
                title="School report progress updated",
                message=(
                    f"{report.classroom.teacher.school.school_name} "
                    "verified another final class report."
                ),
                target_url=district_target,
            )
    return created_count


def _create_notification(
    user,
    notification_type,
    title,
    message,
    target_url,
):
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

    principal_user_ids = list(
        User.objects.filter(
            principal_profile__school=school,
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
        principal_user_ids
        + teacher_user_ids
        + student_user_ids
        + parent_user_ids
    )
    return User.objects.filter(user_id__in=audience_ids)


def _student_audience(student):
    """The Student account and approved connected Parent accounts."""
    user_ids = {student.user_id}
    user_ids.update(
        ParentStudentLink.objects.filter(
            student=student,
            status=ParentStudentLink.Status.APPROVED,
            parent__user__status=User.Status.ACTIVE,
        ).values_list("parent__user_id", flat=True)
    )
    return User.objects.filter(
        user_id__in=user_ids,
        status=User.Status.ACTIVE,
    )


def _preference_enabled(user, field_name):
    preference, created = UserPreference.objects.get_or_create(user=user)
    return getattr(preference, field_name, True)


def notify_class_archive_status(classroom, archived):
    """Tell enrolled learners and connected parents about archive changes."""
    status = "archived" if archived else "restored"
    changed_key = timezone.now().strftime("%Y%m%d%H%M%S%f")
    target_url = (
        reverse("classroom:classes")
        + f"?class_status={status}&class={classroom.pk}&changed={changed_key}"
    )

    created_count = 0
    for user in _class_audience(classroom):
        created_count += _create_notification(
            user=user,
            notification_type=Notification.Type.GENERAL,
            title=f"Class {status}",
            message=(
                f"{classroom.class_name} ({classroom.subject}) was {status} "
                "by the Teacher."
            ),
            target_url=target_url,
        )
    return created_count


def notify_student_removed(enrollment):
    """Tell a learner when their Teacher removes them from a class."""
    changed_key = timezone.now().strftime("%Y%m%d%H%M%S%f")
    target_url = reverse("classroom:classes") + f"?removed={changed_key}"
    return _create_notification(
        user=enrollment.student.user,
        notification_type=Notification.Type.GENERAL,
        title="Removed from class",
        message=(
            f"Your Teacher removed you from {enrollment.classroom.class_name} "
            f"({enrollment.classroom.subject})."
        ),
        target_url=target_url,
    )


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


def _deadline_details(due_at, reminder):
    local_due = timezone.localtime(due_at)
    labels = {
        "24h": "is due within 24 hours",
        "12h": "is due within 12 hours",
        "6h": "is due within 6 hours",
        "1h": "is due within 1 hour",
    }
    return local_due, labels[reminder]


def notify_module_deadline(module, reminder):
    if not module.due_at:
        return 0

    local_due, reminder_label = _deadline_details(module.due_at, reminder)
    due_key = module.due_at.strftime("%Y%m%d%H%M")

    created_count = 0
    enrollments = ClassEnrollment.objects.filter(
        classroom=module.classroom,
        status=ClassEnrollment.Status.APPROVED,
    ).select_related("student", "student__user")

    for enrollment in enrollments:
        student = enrollment.student
        already_submitted = ModuleSubmission.objects.filter(
            module=module,
            student=student,
            status__in=[
                ModuleSubmission.Status.SUBMITTED,
                ModuleSubmission.Status.GRADED,
            ],
        ).exists()
        if already_submitted:
            continue

        target_url = (
            reverse("classroom:module_work", args=[module.pk])
            + f"?deadline={due_key}&reminder={reminder}"
            + f"&learner={student.pk}"
        )

        for user in _student_audience(student):
            if not _preference_enabled(user, "deadline_reminder_alerts"):
                continue
            created_count += _create_notification(
                user=user,
                notification_type=Notification.Type.DEADLINE,
                title=f"Module deadline: {reminder_label}",
                message=(
                    f"{module.title} for {module.classroom.subject} is due "
                    f"on {local_due.strftime('%B %d, %Y at %I:%M %p')}."
                ),
                target_url=target_url,
            )
    return created_count


def notify_upcoming_module_deadline(module):
    """Compatibility helper retained for older calls."""
    return notify_module_deadline(module, "24h")


def notify_activity_published(activity):
    target_url = reverse("classroom:activity_detail", args=[activity.pk])
    created_count = 0

    for user in _class_audience(activity.classroom):
        created_count += _create_notification(
            user=user,
            notification_type=Notification.Type.ACTIVITY,
            title="New activity published",
            message=(
                f"{activity.classroom.subject}: {activity.title} "
                "is now available."
            ),
            target_url=target_url,
        )
    return created_count


def notify_activity_deadline(activity, reminder):
    if not activity.due_date:
        return 0

    local_due, reminder_label = _deadline_details(activity.due_date, reminder)
    created_count = 0
    enrollments = ClassEnrollment.objects.filter(
        classroom=activity.classroom,
        status=ClassEnrollment.Status.APPROVED,
    ).select_related("student", "student__user")

    for enrollment in enrollments:
        student = enrollment.student
        already_submitted = ActivitySubmission.objects.filter(
            activity=activity,
            student=student,
            status__in=[
                ActivitySubmission.Status.SUBMITTED,
                ActivitySubmission.Status.GRADED,
            ],
        ).exists()
        if already_submitted:
            continue

        target_url = (
            reverse("classroom:activity_detail", args=[activity.pk])
            + f"?reminder={reminder}&learner={student.pk}"
        )
        for user in _student_audience(student):
            if not _preference_enabled(user, "deadline_reminder_alerts"):
                continue
            created_count += _create_notification(
                user=user,
                notification_type=Notification.Type.DEADLINE,
                title=f"Activity deadline: {reminder_label}",
                message=(
                    f"{activity.title} for {activity.classroom.subject} is due "
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
    for user in _school_audience(announcement.school).exclude(
        pk=announcement.posted_by_id
    ):
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

def notify_activity_submission(submission):
    """Notify the Teacher when a Student submits an Activity."""

    teacher_user = submission.activity.classroom.teacher.user

    if not _preference_enabled(
        teacher_user,
        "new_submission_alerts",
    ):
        return 0

    target_url = reverse(
        "classroom:activity_review",
        args=[submission.pk],
    )

    created = _create_notification(
        user=teacher_user,
        notification_type=Notification.Type.SUBMISSION,
        title="New activity submission",
        message=(
            f"{submission.student} submitted "
            f"{submission.activity.title}."
        ),
        target_url=target_url,
    )

    return int(created)

def notify_activity_feedback(submission):
    """Notify the Student and approved Parent accounts about Activity feedback."""

    if not submission.feedback:
        return 0

    activity = submission.activity

    student_target = reverse(
        "classroom:activity_detail",
        args=[activity.pk],
    )

    parent_target = (
        reverse("classroom:tasks")
        + f"?learner={submission.student_id}"
        + "&status=returned"
    )

    created_count = _create_notification(
        user=submission.student.user,
        notification_type=Notification.Type.FEEDBACK,
        title="Activity feedback available",
        message=(
            f"Your Teacher added feedback to "
            f"{activity.title}."
        ),
        target_url=student_target,
    )

    for link in _approved_parent_links(submission.student):
        created_count += _create_notification(
            user=link.parent.user,
            notification_type=Notification.Type.FEEDBACK,
            title="Activity feedback available",
            message=(
                f"Feedback for {submission.student.firstname}'s "
                f"{activity.title} is now available."
            ),
            target_url=parent_target,
        )

    return created_count

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

def _approved_parent_links(student):
    return ParentStudentLink.objects.filter(
        student=student,
        status=ParentStudentLink.Status.APPROVED,
        parent__user__status=User.Status.ACTIVE,
    ).select_related(
        "parent",
        "parent__user",
    )


def notify_term_grade_released(classroom, term):
    """
    Notify approved Parents when a Teacher releases
    one class term grade.
    """

    enrollments = ClassEnrollment.objects.filter(
        classroom=classroom,
        status=ClassEnrollment.Status.APPROVED,
    ).select_related(
        "student",
    )

    created_count = 0

    for enrollment in enrollments:
        student = enrollment.student

        parent_target_url = (
            reverse("classroom:parent_progress")
            + f"?learner={student.pk}&tab=grades"
        )

        student_target_url = (
            reverse("classroom:class_page", args=[classroom.pk])
            + "?tab=grades"
        )

        recipients = [(student.user, student_target_url)]
        recipients.extend(
            (link.parent.user, parent_target_url)
            for link in _approved_parent_links(student)
        )

        for user, target_url in recipients:
            created_count += _create_notification(
                user=user,
                notification_type=(
                    Notification.Type.GRADE_RELEASED
                ),
                title=f"Term {term} grade released",
                message=(
                    f"{classroom.subject}: "
                    f"{student.firstname}'s Term {term} "
                    "grade is now available."
                ),
                target_url=target_url,
            )

    return created_count


def notify_attendance_record(record):
    """
    Notify approved Parents only for an absence or tardiness.
    """

    if record.status not in {
        AttendanceRecord.Status.ABSENT,
        AttendanceRecord.Status.LATE,
    }:
        return 0

    student = record.student
    classroom = record.attendance_day.classroom
    attendance_date = record.attendance_day.date

    status_label = (
        "absent"
        if record.status == AttendanceRecord.Status.ABSENT
        else "tardy"
    )

    target_url = (
        reverse("classroom:parent_progress")
        + f"?learner={student.pk}"
        + "&tab=attendance"
        + f"&classroom={classroom.pk}"
        + f"&month={attendance_date:%Y-%m}"
    )

    created_count = 0

    for link in _approved_parent_links(student):
        created_count += _create_notification(
            user=link.parent.user,
            notification_type=Notification.Type.ATTENDANCE,
            title=f"{status_label.title()} attendance recorded",
            message=(
                f"{student.firstname} was marked "
                f"{status_label} in {classroom.subject} "
                f"on {attendance_date:%B %d, %Y}."
            ),
            target_url=target_url,
        )

    return created_count


def notify_submission_feedback(submission):
    """
    Notify the Student and approved Parents after the
    Teacher saves feedback.
    """

    if not submission.feedback:
        return 0

    parent_target = (
        reverse("classroom:tasks")
        + f"?learner={submission.student_id}"
        + "&status=returned"
    )

    student_target = reverse(
        "classroom:module_work",
        args=[submission.module_id],
    )

    created_count = _create_notification(
        user=submission.student.user,
        notification_type=Notification.Type.FEEDBACK,
        title="Teacher feedback available",
        message=(
            f"Your Teacher added feedback to "
            f"{submission.module.title}."
        ),
        target_url=student_target,
    )

    for link in _approved_parent_links(submission.student):
        created_count += _create_notification(
            user=link.parent.user,
            notification_type=Notification.Type.FEEDBACK,
            title="Teacher feedback available",
            message=(
                f"Feedback for {submission.student.firstname}'s "
                f"{submission.module.title} is now available."
            ),
            target_url=parent_target,
        )

    return created_count
