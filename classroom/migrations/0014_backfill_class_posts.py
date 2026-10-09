from django.db import migrations


def create_existing_class_posts(apps, schema_editor):
    Announcement = apps.get_model(
        "classroom",
        "Announcement",
    )

    Module = apps.get_model(
        "classroom",
        "Module",
    )

    ClassPost = apps.get_model(
        "classroom",
        "ClassPost",
    )

    for announcement in Announcement.objects.select_related(
        "classroom"
    ):
        post, created = ClassPost.objects.update_or_create(
            announcement_id=announcement.pk,
            defaults={
                "classroom_id": announcement.classroom_id,
                "teacher_id": announcement.classroom.teacher_id,
                "post_type": "announcement",
                "title": announcement.title,
                "content": announcement.content,
                "is_published": True,
            },
        )

        if created:
            ClassPost.objects.filter(pk=post.pk).update(
                created_at=announcement.created_at
            )

    published_modules = Module.objects.filter(
        status="published"
    ).select_related("classroom")

    for module in published_modules:
        post, created = ClassPost.objects.update_or_create(
            module_id=module.pk,
            defaults={
                "classroom_id": module.classroom_id,
                "teacher_id": module.classroom.teacher_id,
                "post_type": "module",
                "title": module.title,
                "content": module.instructions,
                "due_date": module.due_at,
                "score": module.max_score or None,
                "grade_component": "written_work",
                "term": module.term,
                "is_published": True,
                "allow_late_submission": module.allow_late,
            },
        )

        if created:
            original_date = (
                module.published_at or module.created_at
            )

            ClassPost.objects.filter(pk=post.pk).update(
                created_at=original_date
            )


def remove_created_class_posts(apps, schema_editor):
    ClassPost = apps.get_model(
        "classroom",
        "ClassPost",
    )

    ClassPost.objects.filter(
        post_type__in=["announcement", "module"],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("classroom", "0013_classpost_comment"),
    ]

    operations = [
        migrations.RunPython(
            create_existing_class_posts,
            remove_created_class_posts,
        ),
    ]