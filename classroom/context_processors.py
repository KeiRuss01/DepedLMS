from django.db.models import Count, Prefetch, Q

from accounts.models import User

from .message_queries import valid_conversations_for_user
from .models import ParentTeacherMessage


def message_data(request):
    if not request.user.is_authenticated or request.user.role not in [
        User.Role.PARENT,
        User.Role.TEACHER,
    ]:
        return {
            "messaging_enabled": False,
            "unread_message_count": 0,
            "message_conversation_rows": [],
        }

    valid_conversations = valid_conversations_for_user(request.user)
    unread_message_count = ParentTeacherMessage.objects.filter(
        conversation__in=valid_conversations,
        read_at__isnull=True,
    ).exclude(sender=request.user).count()

    conversations = valid_conversations.annotate(
        unread_count=Count(
            "messages",
            filter=Q(messages__read_at__isnull=True)
            & ~Q(messages__sender=request.user),
        )
    ).prefetch_related(
        Prefetch(
            "messages",
            queryset=ParentTeacherMessage.objects.select_related("sender").order_by("-created_at"),
            to_attr="latest_messages",
        )
    )[:8]

    rows = [
        {
            "conversation": conversation,
            "last_message": conversation.latest_messages[0]
            if conversation.latest_messages
            else None,
            "unread_count": conversation.unread_count,
        }
        for conversation in conversations
    ]

    return {
        "messaging_enabled": True,
        "unread_message_count": unread_message_count,
        "message_conversation_rows": rows,
    }
