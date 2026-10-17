from django.contrib import admin

from .models import SMSNotification


@admin.register(SMSNotification)
class SMSNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "sms_id",
        "user",
        "phone_number",
        "sms_type",
        "status",
        "retry_count",
        "sent_at",
        "created_at",
    )
    list_filter = ("status", "sms_type", "created_at")
    search_fields = ("user__email", "phone_number", "message_text")
    readonly_fields = (
        "user",
        "phone_number",
        "message_text",
        "sms_type",
        "reference_id",
        "status",
        "sent_at",
        "created_at",
        "retry_count",
    )
