from django.conf import settings
from django.db import models


class SMSNotification(models.Model):
    """Table 3.8 SMS_notifications from the capstone data dictionary."""

    class Type(models.TextChoices):
        DISTRICT_ANNOUNCEMENT = "district_announcement", "District announcement"
        SCHOOL_ANNOUNCEMENT = "school_announcement", "School announcement"
        CLASS_ANNOUNCEMENT = "class_announcement", "Class announcement"
        NEW_MODULE = "new_module", "New module"
        NEW_ACTIVITY = "new_activity", "New activity"
        MODULE_DEADLINE_NEAR = "module_deadline_near", "Module deadline near"
        MODULE_DEADLINE_TOMORROW = (
            "module_deadline_tomorrow",
            "Module deadline tomorrow",
        )
        MODULE_DEADLINE_TODAY = "module_deadline_today", "Module deadline today"
        ACTIVITY_DEADLINE_NEAR = (
            "activity_deadline_near",
            "Activity deadline near",
        )
        ACTIVITY_DEADLINE_TOMORROW = (
            "activity_deadline_tomorrow",
            "Activity deadline tomorrow",
        )
        ACTIVITY_DEADLINE_TODAY = (
            "activity_deadline_today",
            "Activity deadline today",
        )
        GRADE_AVAILABLE = "grade_available", "Grade available"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    sms_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sms_notifications",
        db_column="user_id",
    )
    # A CharField is required because phone numbers may start with 0 or +63.
    phone_number = models.CharField(max_length=13)
    message_text = models.TextField()
    sms_type = models.CharField(max_length=40, choices=Type.choices)
    reference_id = models.PositiveBigIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    retry_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "sms_notifications"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "sms_type", "reference_id"],
                name="unique_sms_user_type_reference",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="sms_queue_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.phone_number} - {self.get_sms_type_display()}"
