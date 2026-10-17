from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create deadline reminders and send one rate-limited SMS batch."

    def handle(self, *args, **options):
        call_command("send_deadline_notifications")
        call_command("send_pending_sms")
