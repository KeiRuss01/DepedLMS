from django.db.models import F

from accounts.models import ParentStudentLink, User

from .models import ClassEnrollment, ParentTeacherConversation


def valid_conversations_for_user(user):
    """Return conversations backed by a current link and class enrollment."""
    conversations = ParentTeacherConversation.objects.select_related(
        "classroom",
        "classroom__teacher",
        "classroom__teacher__user",
        "student",
        "student__user",
        "parent",
        "parent__user",
    ).filter(
        student__class_enrollments__classroom=F("classroom"),
        student__class_enrollments__status=ClassEnrollment.Status.APPROVED,
        student__parent_links__parent=F("parent"),
        student__parent_links__status=ParentStudentLink.Status.APPROVED,
        classroom__is_archived=False,
    )

    if user.role == User.Role.PARENT:
        return conversations.filter(parent__user=user).distinct()
    if user.role == User.Role.TEACHER:
        return conversations.filter(classroom__teacher__user=user).distinct()
    return conversations.none()
