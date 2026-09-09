# Module management and submissions: layout stage

## Where to open it

Sign in as a Teacher, open one of your classes, and select **Modules**.
Choose **Add Module** to configure a local preview. Add a title, choose a PDF,
and select numbered answers, written response, or answer file. Preview the Student
layout or keep the draft in the current page to see its library card.

Select **Preview submissions** to inspect the Teacher submission-list layout,
then **Preview review layout** for the score and feedback form.

An approved enrolled Student can open the same class's Modules tab and select
**Preview answer workspace**. Its preview controls allow testing a local PDF and
each answer method. These controls are for this layout stage; in the finished
system the Teacher chooses the method and the Student receives the published PDF.

At widths below 992px, switch between **Module** and **Answer sheet** using the
two buttons. Switching panels keeps entered answers in memory.

## Files and responsibilities

- `classroom/templates/classroom/class_page.html`: includes the module layout on
  the existing Modules tab and loads its stylesheet/script.
- `classroom/templates/classroom/modules/index.html`: module library, search,
  term filters, empty state, and role-specific includes.
- `classroom/templates/classroom/modules/teacher_setup.html`: module details,
  PDF selection, answer-method selection, bulk blank fields, and schedule.
- `classroom/templates/classroom/modules/workspace.html`: PDF pane, answer pane,
  mobile switches, draft and submission-review controls.
- `classroom/templates/classroom/modules/submissions.html`: Teacher submission
  list and score/feedback layout.
- `classroom/static/classroom/css/modules.css`: responsive layout and appearance.
- `classroom/static/classroom/js/modules.js`: page-local interactions only.

## What works in this stage

Opening layout screens, selecting a local PDF, creating numbered blank answer
fields, changing an item's response type, entering answers, previewing a draft
card, searching/filtering that preview card, and switching mobile panels.

PDF display currently uses the browser's embedded viewer. On devices that do not
support it, Open PDF is a fallback. A consistent embedded mobile PDF.js viewer
can be introduced in a later stage.

## What is deliberately not connected yet

There are no upload requests, database saves, persistent drafts, publication,
submission, extraction/OCR, automatic grading, or feedback delivery. The page
displays that limitation, and action buttons do not pretend that data was saved.
Refreshing, navigating to another class tab, or closing the page clears its
preview data. Do not use this preview for actual student work.

## Academic year and terms

A class belongs to an academic year. Module setup offers Term 1, Term 2, Term 3.
The Create Class form no longer asks for a quarter. Its `forms.py` field list was
adjusted as well so a hidden required quarter does not break class creation.

`models.py`, `views.py`, URLs, and migrations were not changed. The legacy
`Classroom.quarter` column and its existing default remain until the database
lesson. Do not interpret that default as a new class's academic term.

Later, remove that class column using a migration after reviewing existing data,
and put a term field on each module. Historical four-quarter records should not
be relabelled as three-term records. Grade calculations need their own policy
review; this layout does not change grading rules.

## Next guided stages

1. Agree on module and submission fields and discuss the model relationships.
2. Add models and migrations together, explaining every field.
3. Add forms and views for Teacher publishing and authorized Student access.
4. Replace page-local preview data with database records and protected PDF access.
5. Connect drafts, submissions, file validation, feedback, and role/ownership checks.
6. Remove preview controls and test the complete Teacher/Student workflow.

No database migration is needed for the current layout stage.
