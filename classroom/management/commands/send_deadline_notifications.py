from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from classroom.models import Module
from classroom.notification_services import (
    notify_upcoming_module_deadline,
)


class Command(BaseCommand):
    help = "Notify learners about published Modules approaching their deadline."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Upcoming deadline window in hours. Default: 24.",
        )

    def handle(self, *args, **options):
        hours = max(options["hours"], 1)
        now = timezone.now()
        deadline_limit = now + timedelta(hours=hours)

        modules = Module.objects.filter(
            status=Module.Status.PUBLISHED,
            due_at__gt=now,
            due_at__lte=deadline_limit,
        ).select_related("classroom")

        notification_count = 0
        for module in modules:
            notification_count += notify_upcoming_module_deadline(module)

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {notification_count} deadline notification(s)."
            )
        )
