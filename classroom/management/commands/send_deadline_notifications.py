from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from classroom.models import ClassPost, Module
from classroom.notification_services import (
    notify_activity_deadline,
    notify_module_deadline,
)


class Command(BaseCommand):
    help = (
        "Queue Module and Activity reminders 24, 12, 6, and 1 hour "
        "before their deadlines."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        reminder_limit = now + timedelta(hours=24)

        modules = Module.objects.filter(
            status=Module.Status.PUBLISHED,
            due_at__gt=now,
            due_at__lte=reminder_limit,
        ).select_related("classroom")

        activities = ClassPost.objects.filter(
            post_type=ClassPost.PostType.ACTIVITY,
            is_published=True,
            is_closed=False,
            due_date__gt=now,
            due_date__lte=reminder_limit,
        ).select_related("classroom")

        notification_count = 0

        for module in modules:
            reminder = self._reminder_name(module.due_at - now)
            if reminder:
                notification_count += notify_module_deadline(module, reminder)

        for activity in activities:
            reminder = self._reminder_name(activity.due_date - now)
            if reminder:
                notification_count += notify_activity_deadline(activity, reminder)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {notification_count} deadline notification(s)."
            )
        )

    @staticmethod
    def _reminder_name(time_left):
        seconds_left = time_left.total_seconds()
        if seconds_left <= 0:
            return None
        if seconds_left <= 60 * 60:
            return "1h"
        if seconds_left <= 6 * 60 * 60:
            return "6h"
        if seconds_left <= 12 * 60 * 60:
            return "12h"
        if seconds_left <= 24 * 60 * 60:
            return "24h"
        return None
