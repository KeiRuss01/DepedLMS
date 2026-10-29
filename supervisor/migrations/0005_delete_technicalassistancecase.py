from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("supervisor", "0004_technicalassistancecase"),
    ]

    operations = [
        migrations.DeleteModel(
            name="TechnicalAssistanceCase",
        ),
    ]
