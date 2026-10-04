def notification_data(request):
    if not request.user.is_authenticated:
        return {
            "unread_notification_count": 0,
            "recent_notifications": [],
        }

    notifications = request.user.notifications.all()

    return {
        "unread_notification_count": notifications.filter(
            is_read=False
        ).count(),
        "recent_notifications": notifications[:5],
    }