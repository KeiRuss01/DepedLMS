from django.db import migrations


def make_module_sections_written_work(apps, schema_editor):
    Section = apps.get_model("classroom", "ModuleAnswerSection")
    Section.objects.exclude(answer_method="none").update(
        include_in_grade=True,
        grading_component="written_work",
    )
    Section.objects.filter(answer_method="none").update(
        include_in_grade=False,
        grading_component="not_graded",
        max_score=0,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("classroom", "0003_module_hidden_pages_module_student_pdf_module_week_and_more"),
    ]

    operations = [
        migrations.RunPython(
            make_module_sections_written_work,
            migrations.RunPython.noop,
        ),
    ]
