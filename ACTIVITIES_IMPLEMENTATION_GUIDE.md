# Classroom Activities Implementation Guide

## What was added

The Activity feature is online-only for now. A Teacher can create and publish an
Activity, attach one PDF resource, and review Student work. Every Activity
automatically allows Students to write directly, upload one PDF, or submit a
link. Published Activities also appear in the Stream, Tasks page, and Calendar.

## In-app PDF viewer

Activity resources and Student-submitted PDFs open inside the Classroom
application. The normal header and mobile navigation remain visible, and the
viewer provides previous page, next page, zoom out, and zoom in controls.

```text
classroom/templates/classroom/activities/pdf_viewer.html
classroom/static/classroom/js/activity_pdf_viewer.js
classroom/static/classroom/css/activity_pdf_viewer.css
```

The viewer uses the local PDF.js package already included in the project. The
PDF endpoints remain protected by the same Teacher and Student access checks.

## Main database code

`classroom/models.py` now contains:

- Activity settings on `ClassPost` (`activity_type`, default submission
  methods, and `is_closed`).
- `ActivitySubmission` for one Student submission per Activity.
- An optional `activity` connection on `GradeItem`, allowing graded Activities
  to appear in the existing gradebook.

The important relationship is:

```python
class ActivitySubmission(models.Model):
    activity = models.ForeignKey(
        ClassPost,
        on_delete=models.CASCADE,
        related_name="activity_submissions",
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="activity_submissions",
    )
    method = models.CharField(max_length=10, choices=Method.choices)
    text_response = models.TextField(blank=True)
    pdf_file = models.FileField(blank=True, null=True)
    link_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices)
    score = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    feedback = models.TextField(blank=True)
```

The generated migration is:

```text
classroom/migrations/0016_classpost_activity_type_and_more.py
```

## Forms and PDF rules

`classroom/forms.py` contains:

```python
ActivityForm
ActivitySubmissionForm
ActivityReviewForm
```

Both Teacher resources and Student file submissions use `validate_pdf_upload()`.
It accepts only `.pdf` files with a maximum size of 20 MB.

## URLs

These routes were added to `classroom/urls.py`:

```python
path("classes/<int:classroom_id>/activities/create/", activity_views.activity_create_view, name="activity_create")
path("activities/<int:activity_id>/", activity_views.activity_detail_view, name="activity_detail")
path("activities/<int:activity_id>/edit/", activity_views.activity_edit_view, name="activity_edit")
path("activities/<int:activity_id>/status/", activity_views.activity_status_view, name="activity_status")
path("activities/<int:activity_id>/resource/", activity_views.activity_resource_view, name="activity_resource")
path("activity-submissions/<int:submission_id>/review/", activity_views.activity_review_view, name="activity_review")
path("activity-submissions/<int:submission_id>/pdf/", activity_views.activity_submission_pdf_view, name="activity_submission_pdf")
```

The full Activity controller code is in `classroom/activity_views.py`. It was
kept separate so the already-large `classroom/views.py` remains easier to study.

## Interface files

```text
classroom/templates/classroom/activities/form.html
classroom/templates/classroom/activities/detail.html
classroom/templates/classroom/activities/review.html
classroom/static/classroom/css/activities.css
```

`classroom/templates/classroom/class_page.html` was also updated to show the
Activity list and published Activity Stream cards.

## Existing features connected to Activities

- `classroom/gradebook.py`: creates the Activity gradebook item and Student score.
- `classroom/views.py`: shows Activities in the class page, Tasks, and Calendar.
- `classroom/templates/classroom/_task_card.html`: displays Modules and Activities.
- `classroom/templates/classroom/tasks.html`: uses common task fields.
- `classroom/templates/classroom/parent_dashboard.html`: shows linked learner Activity deadlines.
- Existing Stream comments work on the Activity detail page.

## Workflow

1. Teacher opens a class and selects **Activities**.
2. Teacher selects **Create Activity**.
3. Teacher enters the instructions, optional PDF, Term, component, score, and
   deadline. All three Student answer methods are enabled automatically.
4. **Save draft** keeps it private. **Publish** makes it visible to Students and
   adds it to the Stream, Tasks, Calendar, and gradebook.
5. Student opens the Activity and chooses Write, Upload PDF, or Link.
6. **Save draft** remains private from the Teacher. **Turn in** locks the answer.
7. Teacher opens the Activity, selects a submitted Student, enters a score and
   feedback, then either returns it for revision or marks it graded.
8. A graded score is copied into the existing electronic gradebook.

## Commands

The migration has already been generated and applied. On another computer,
after pulling this code, run:

```powershell
python manage.py migrate
python manage.py check
python manage.py runserver
```

The final local validation returned:

```text
System check identified no issues (0 silenced).
```
