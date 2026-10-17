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
        "Queue Module and Activity reminders for deadlines that are "
        "near, tomorrow, or today."
    )

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()
        near_limit = now + timedelta(days=3)

        modules = Module.objects.filter(
            status=Module.Status.PUBLISHED,
            due_at__gt=now,
            due_at__lte=near_limit,
        ).select_related("classroom")

        activities = ClassPost.objects.filter(
            post_type=ClassPost.PostType.ACTIVITY,
            is_published=True,
            is_closed=False,
            due_date__gt=now,
            due_date__lte=near_limit,
        ).select_related("classroom")

        notification_count = 0

        for module in modules:
            days_left = (
                timezone.localtime(module.due_at).date() - today
            ).days
            reminder = self._reminder_name(days_left)
            if reminder:
                notification_count += notify_module_deadline(module, reminder)

        for activity in activities:
            days_left = (
                timezone.localtime(activity.due_date).date() - today
            ).days
            reminder = self._reminder_name(days_left)
            if reminder:
                notification_count += notify_activity_deadline(activity, reminder)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {notification_count} deadline notification(s)."
            )
        )

    @staticmethod
    def _reminder_name(days_left):
        if days_left == 0:
            return "today"
        if days_left == 1:
            return "tomorrow"
        if 2 <= days_left <= 3:
            return "near"
        return None
