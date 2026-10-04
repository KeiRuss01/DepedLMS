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

