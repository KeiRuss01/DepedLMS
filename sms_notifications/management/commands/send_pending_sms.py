from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from sms_notifications.models import SMSNotification
from sms_notifications.services import (
    PermanentSMSFailure,
    TemporarySMSFailure,
    send_sms,
)


class Command(BaseCommand):
    help = "Send pending SMS notifications in a rate-limited batch."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=settings.SMS_BATCH_SIZE)

    def handle(self, *args, **options):
        if not settings.SMS_ENABLED:
            self.stdout.write(self.style.WARNING("SMS sending is disabled."))
            return

        if not settings.SMS_API_KEY.strip():
            raise CommandError("Add SMS_API_KEY to the .env file.")

        limit = max(1, min(options["limit"], settings.SMS_BATCH_SIZE))
        messages = SMSNotification.objects.filter(
            status__in=[
                SMSNotification.Status.PENDING,
                SMSNotification.Status.FAILED,
            ],
            retry_count__lt=settings.SMS_MAX_RETRIES,
        ).order_by("created_at")[:limit]

        sent_count = 0
        failed_count = 0

        for sms in messages:
            try:
                send_sms(sms)
            except TemporarySMSFailure:
                sms.status = SMSNotification.Status.FAILED
                sms.retry_count += 1
                sms.save(update_fields=["status", "retry_count"])
                failed_count += 1
            except PermanentSMSFailure:
                sms.status = SMSNotification.Status.FAILED
                sms.retry_count = settings.SMS_MAX_RETRIES
                sms.save(update_fields=["status", "retry_count"])
                failed_count += 1
            else:
                sms.status = SMSNotification.Status.SENT
                sms.sent_at = timezone.now()
                sms.save(update_fields=["status", "sent_at"])
                sent_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"SMS sent: {sent_count}; failed: {failed_count}."
            )
        )
