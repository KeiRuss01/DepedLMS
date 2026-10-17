from django.conf import settings
from django.db import models

from accounts.models import School


class SchoolAnnouncement(models.Model):
    class Priority(models.TextChoices):
        NORMAL = "normal", "Normal"
        IMPORTANT = "important", "Important"
        URGENT = "urgent", "Urgent"

    announcement_id = models.AutoField(primary_key=True)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="school_announcements",
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="school_announcements_posted",
    )
    title = models.CharField(max_length=150)
    content = models.TextField()
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "school_announcement"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.school} - {self.title}"

class SchoolReportSubmission(models.Model):

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted to District"
        RETURNED = "returned", "Returned for Correction"
        ACKNOWLEDGED = "acknowledged", "Acknowledged by District"

    report_id = models.AutoField(
        primary_key=True,
    )

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="final_report_submissions",
    )

    school_year = models.CharField(
        max_length=20,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUBMITTED,
    )

    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_school_reports",
    )

    submitted_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_school_reports",
        blank=True,
        null=True,
    )

    reviewed_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    district_comment = models.TextField(
        blank=True,
    )

    snapshot = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        db_table = "school_report_submission"
        ordering = ["-submitted_at"]

        constraints = [
            models.UniqueConstraint(
                fields=["school", "school_year"],
                name="unique_school_report_per_school_year",
            )
        ]

    def __str__(self):
        return (
            f"{self.school.school_name} - "
            f"{self.school_year} - "
            f"{self.get_status_display()}"
        )

