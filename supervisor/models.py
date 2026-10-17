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

class SupervisionVisit(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    visit_id = models.AutoField(primary_key=True)

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="supervision_visits",
    )

    supervisor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="supervision_visits",
    )

    visit_date = models.DateField()

    title = models.CharField(
        max_length=150,
        help_text="Example: Classroom monitoring visit",
    )

    findings = models.TextField(
        help_text="Record the observations or issues found.",
    )

    recommendations = models.TextField(
        help_text="Record the recommended actions.",
    )

    action_owner = models.CharField(
        max_length=150,
        blank=True,
        help_text="Example: School Principal or Grade 10 Teacher",
    )

    follow_up_date = models.DateField(
        blank=True,
        null=True,
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "supervision_visit"
        ordering = ["-visit_date", "-created_at"]

    def __str__(self):
        return f"{self.school.school_name} - {self.title}"

