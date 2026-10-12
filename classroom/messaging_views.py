from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import ParentStudentLink, User

from .message_queries import valid_conversations_for_user
from .models import (
    ClassEnrollment,
    Classroom,
    ParentTeacherConversation,
    ParentTeacherMessage,
)


def _require_messaging_role(user):
    if user.role not in [User.Role.PARENT, User.Role.TEACHER]:
        raise PermissionDenied("Messaging is only available to Parents and Teachers.")


def _conversation_rows(user):
    conversations = valid_conversations_for_user(user).annotate(
        unread_count=Count(
            "messages",
            filter=Q(messages__read_at__isnull=True)
            & ~Q(messages__sender=user),
        )
    ).prefetch_related(
        Prefetch(
            "messages",
            queryset=ParentTeacherMessage.objects.select_related("sender").order_by("-created_at"),
            to_attr="latest_messages",
        )
    )
    return [
        {
            "conversation": conversation,
            "last_message": conversation.latest_messages[0]
            if conversation.latest_messages
            else None,
            "unread_count": conversation.unread_count,
        }
        for conversation in conversations
    ]


def _eligible_contacts(user):
    contacts = []
    existing = {
        (item.classroom_id, item.student_id, item.parent_id): item
        for item in valid_conversations_for_user(user)
    }

    if user.role == User.Role.PARENT:
        parent = user.parent_profile
        links = ParentStudentLink.objects.filter(
            parent=parent,
            status=ParentStudentLink.Status.APPROVED,
        ).select_related("student", "student__user")

        for link in links:
            enrollments = ClassEnrollment.objects.filter(
                student=link.student,
                status=ClassEnrollment.Status.APPROVED,
                classroom__is_archived=False,
            ).select_related("classroom", "classroom__teacher", "classroom__teacher__user")
            for enrollment in enrollments:
                contacts.append({
                    "classroom": enrollment.classroom,
                    "student": link.student,
                    "parent": parent,
                    "conversation": existing.get(
                        (enrollment.classroom_id, link.student_id, parent.pk)
                    ),
                })

    else:
        teacher = user.teacher_profile
        enrollments = ClassEnrollment.objects.filter(
            classroom__teacher=teacher,
            classroom__is_archived=False,
            status=ClassEnrollment.Status.APPROVED,
        ).select_related("classroom", "student", "student__user")

        for enrollment in enrollments:
            links = ParentStudentLink.objects.filter(
                student=enrollment.student,
                status=ParentStudentLink.Status.APPROVED,
            ).select_related("parent", "parent__user")
            for link in links:
                contacts.append({
                    "classroom": enrollment.classroom,
                    "student": enrollment.student,
                    "parent": link.parent,
                    "conversation": existing.get(
                        (enrollment.classroom_id, enrollment.student_id, link.parent_id)
                    ),
                })

    return contacts


def _get_conversation(user, conversation_id):
    _require_messaging_role(user)
    return get_object_or_404(
        valid_conversations_for_user(user),
        pk=conversation_id,
    )


def _mark_opened(conversation, user):
    conversation.messages.filter(
        read_at__isnull=True,
    ).exclude(sender=user).update(read_at=timezone.now())


@login_required(login_url="accounts:login")
def message_inbox_view(request):
    _require_messaging_role(request.user)
    return render(
        request,
        "classroom/messages/inbox.html",
        {
            "conversation_rows": _conversation_rows(request.user),
            "eligible_contacts": _eligible_contacts(request.user),
        },
    )


@login_required(login_url="accounts:login")
def message_conversation_view(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    _mark_opened(conversation, request.user)
    return render(
        request,
        "classroom/messages/conversation.html",
        {
            "conversation": conversation,
            "conversation_messages": conversation.messages.select_related("sender"),
        },
    )


@login_required(login_url="accounts:login")
def message_panel_conversation_view(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    _mark_opened(conversation, request.user)
    return render(
        request,
        "classroom/messages/_panel_chat.html",
        {
            "conversation": conversation,
            "conversation_messages": conversation.messages.select_related("sender"),
        },
    )


@login_required(login_url="accounts:login")
@require_POST
def message_conversation_start_view(request):
    _require_messaging_role(request.user)
    classroom = get_object_or_404(
        Classroom.objects.select_related("teacher", "teacher__user"),
        pk=request.POST.get("classroom_id"),
        is_archived=False,
    )
    student_id = request.POST.get("student_id")

    enrollment = get_object_or_404(
        ClassEnrollment,
        classroom=classroom,
        student_id=student_id,
        status=ClassEnrollment.Status.APPROVED,
    )

    if request.user.role == User.Role.PARENT:
        parent = request.user.parent_profile
        get_object_or_404(
            ParentStudentLink,
            parent=parent,
            student_id=student_id,
            status=ParentStudentLink.Status.APPROVED,
        )
    else:
        if classroom.teacher_id != request.user.teacher_profile.pk:
            raise PermissionDenied("You cannot start this conversation.")
        link = get_object_or_404(
            ParentStudentLink,
            parent_id=request.POST.get("parent_id"),
            student_id=student_id,
            status=ParentStudentLink.Status.APPROVED,
        )
        parent = link.parent

    conversation, _ = ParentTeacherConversation.objects.get_or_create(
        classroom=classroom,
        student=enrollment.student,
        parent=parent,
    )
    return redirect("classroom:message_conversation", conversation_id=conversation.pk)


@login_required(login_url="accounts:login")
@require_POST
def message_send_view(request, conversation_id):
    conversation = _get_conversation(request.user, conversation_id)
    content = request.POST.get("content", "").strip()

    if not content:
        error = "Write a message before sending."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": error}, status=400)
        messages.error(request, error)
    elif len(content) > 2000:
        error = "Messages cannot exceed 2,000 characters."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": False, "error": error}, status=400)
        messages.error(request, error)
    else:
        ParentTeacherMessage.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content,
        )
        conversation.updated_at = timezone.now()
        conversation.save(update_fields=["updated_at"])
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({
                "ok": True,
                "panel_url": reverse(
                    "classroom:message_panel_conversation",
                    args=[conversation.pk],
                ),
            })

    return redirect("classroom:message_conversation", conversation_id=conversation.pk)
