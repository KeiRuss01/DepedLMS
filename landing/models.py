from django.conf import settings
from django.db import models


class DeviceRegistry(models.Model):

    class DeviceType(models.TextChoices):
        MOBILE = "mobile", "Mobile"
        TABLET = "tablet", "Tablet"
        DESKTOP = "desktop", "Desktop"

    device_id = models.UUIDField(
        primary_key=True,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="registered_devices",
        db_column="user_id",
    )

    device_name = models.CharField(
        max_length=150,
    )

    device_type = models.CharField(
        max_length=20,
        choices=DeviceType.choices,
        default=DeviceType.DESKTOP,
    )

    browser = models.CharField(
        max_length=100,
        blank=True,
    )

    last_sync_at = models.DateTimeField(
        blank=True,
        null=True,
    )

    registered_at = models.DateTimeField(
        auto_now_add=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    class Meta:
        db_table = "device_registry"
        ordering = ["-last_sync_at", "-registered_at"]

    def __str__(self):
        return f"{self.device_name} — {self.user}"