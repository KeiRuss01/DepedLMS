from .models import ClassPost


def sync_announcement_post(announcement):
    post, _ = ClassPost.objects.update_or_create(
        announcement=announcement,
        defaults={
            "classroom": announcement.classroom,
            "teacher": announcement.classroom.teacher,
            "post_type": ClassPost.PostType.ANNOUNCEMENT,
            "title": announcement.title,
            "content": announcement.content,
            "is_published": True,
        },
    )

    return post


def sync_module_post(module):
    post, _ = ClassPost.objects.update_or_create(
        module=module,
        defaults={
            "classroom": module.classroom,
            "teacher": module.classroom.teacher,
            "post_type": ClassPost.PostType.MODULE,
            "title": module.title,
            "content": module.instructions,
            "due_date": module.due_at,
            "score": module.max_score or None,
            "grade_component": ClassPost.GradeComponent.WRITTEN_WORK,
            "term": module.term,
            "is_published": (
                module.status == module.Status.PUBLISHED
            ),
            "allow_late_submission": module.allow_late,
        },
    )

    return post