from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("classroom", "0019_submissionextrapage_essay_bold_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="submissionextrapage",
            name="essay_html",
            field=models.TextField(blank=True),
        ),
    ]
