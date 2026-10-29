import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_alter_notification_notification_type"),
        ("supervisor", "0003_schoolreportsubmission_delete_supervisionvisit_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="TechnicalAssistanceCase",
            fields=[
                ("assistance_id", models.AutoField(primary_key=True, serialize=False)),
                ("concern", models.CharField(max_length=200)),
                ("details", models.TextField(blank=True)),
                ("assistance_provided", models.TextField(blank=True)),
                ("priority", models.CharField(choices=[("normal", "Normal"), ("important", "Important"), ("urgent", "Urgent")], default="normal", max_length=20)),
                ("status", models.CharField(choices=[("open", "Open"), ("ongoing", "Ongoing"), ("resolved", "Resolved")], default="open", max_length=20)),
                ("follow_up_date", models.DateField(blank=True, null=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="technical_assistance_cases_created", to=settings.AUTH_USER_MODEL)),
                ("school", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="technical_assistance_cases", to="accounts.school")),
            ],
            options={"db_table": "technical_assistance_case", "ordering": ["-created_at"]},
        ),
    ]
