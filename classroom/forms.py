from django import forms

from pathlib import Path

from accounts.models import ParentStudentLink

from .models import (
    Announcement,
    CalendarEvent,
    ClassPost,
    Classroom,
    Comment,
    ActivitySubmission,
)


def validate_pdf_upload(uploaded_file):
    if not uploaded_file:
        return uploaded_file

    if Path(uploaded_file.name).suffix.lower() != ".pdf":
        raise forms.ValidationError("Only PDF files are allowed.")

    if uploaded_file.size > 20 * 1024 * 1024:
        raise forms.ValidationError("The PDF must not exceed 20 MB.")

    return uploaded_file


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "content", "priority"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Announcement title",
            }),
            "content": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Write the announcement for your class...",
            }),
            "priority": forms.Select(attrs={"class": "form-select"}),
        }


class ClassPostForm(forms.ModelForm):
    class Meta:
        model = ClassPost
        fields = ["title", "content"]
        widgets = {
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "maxlength": 200,
                "placeholder": "Post title",
            }),
            "content": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "maxlength": 3000,
                "placeholder": "Share an update with your class...",
            }),
        }

    def clean_content(self):
        content = self.cleaned_data["content"].strip()

        if not content:
            raise forms.ValidationError("Write something before posting.")

        return content


class ActivityForm(forms.ModelForm):
    class Meta:
        model = ClassPost
        fields = [
            "activity_type",
            "title",
            "content",
            "file",
            "term",
            "grade_component",
            "score",
            "due_date",
            "allow_late_submission",
        ]
        widgets = {
            "activity_type": forms.Select(attrs={"class": "form-select"}),
            "title": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Activity title",
            }),
            "content": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 6,
                "placeholder": "Write the Activity instructions...",
            }),
            "file": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "application/pdf,.pdf",
            }),
            "term": forms.Select(attrs={"class": "form-select"}),
            "grade_component": forms.Select(attrs={"class": "form-select"}),
            "score": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "1",
                "step": "0.01",
            }),
            "due_date": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={"class": "form-control", "type": "datetime-local"},
            ),
            "allow_late_submission": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["file"].required = False
        self.fields["due_date"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["grade_component"].choices = [
            choice
            for choice in ClassPost.GradeComponent.choices
            if choice[0] != ClassPost.GradeComponent.NOT_GRADED
        ]

    def clean_file(self):
        return validate_pdf_upload(self.cleaned_data.get("file"))

class ActivitySubmissionForm(forms.ModelForm):
    method = forms.ChoiceField(
        choices=[],
        widget=forms.RadioSelect,
    )

    class Meta:
        model = ActivitySubmission
        fields = ["method", "text_response", "pdf_file", "link_url", "note"]
        widgets = {
            "text_response": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 9,
                "placeholder": "Write your answer here...",
            }),
            "pdf_file": forms.ClearableFileInput(attrs={
                "class": "form-control",
                "accept": "application/pdf,.pdf",
            }),
            "link_url": forms.URLInput(attrs={
                "class": "form-control",
                "placeholder": "https://example.com/your-work",
            }),
            "note": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Optional note for your Teacher",
            }),
        }

    def __init__(self, *args, activity, **kwargs):
        super().__init__(*args, **kwargs)
        self.activity = activity
        choices = [
            (ActivitySubmission.Method.TEXT, "Write"),
            (ActivitySubmission.Method.PDF, "Upload PDF"),
            (ActivitySubmission.Method.LINK, "Link"),
        ]
        self.fields["method"].choices = choices
        if not self.initial.get("method") and choices:
            self.initial["method"] = choices[0][0]
        self.fields["text_response"].required = False
        self.fields["pdf_file"].required = False
        self.fields["link_url"].required = False

    def clean_pdf_file(self):
        return validate_pdf_upload(self.cleaned_data.get("pdf_file"))

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")
        if method == ActivitySubmission.Method.TEXT and not cleaned_data.get("text_response", "").strip():
            self.add_error("text_response", "Write your answer before saving.")
        elif method == ActivitySubmission.Method.PDF and not (
            cleaned_data.get("pdf_file") or self.instance.pdf_file
        ):
            self.add_error("pdf_file", "Choose a PDF file.")
        elif method == ActivitySubmission.Method.LINK and not cleaned_data.get("link_url"):
            self.add_error("link_url", "Enter the link to your work.")
        return cleaned_data


class ActivityReviewForm(forms.ModelForm):
    class Meta:
        model = ActivitySubmission
        fields = ["score", "feedback", "status"]
        widgets = {
            "score": forms.NumberInput(attrs={
                "class": "form-control",
                "min": "0",
                "step": "0.01",
            }),
            "feedback": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 5,
                "placeholder": "Write feedback for the Student...",
            }),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, activity, **kwargs):
        super().__init__(*args, **kwargs)
        self.activity = activity
        self.fields["status"].choices = [
            (ActivitySubmission.Status.RETURNED, "Return for revision"),
            (ActivitySubmission.Status.GRADED, "Mark as graded"),
        ]
        self.fields["score"].widget.attrs["max"] = activity.score

    def clean_score(self):
        score = self.cleaned_data.get("score")
        if score is not None and self.activity.score is not None and score > self.activity.score:
            raise forms.ValidationError(
                f"The score cannot exceed {self.activity.score}."
            )
        return score

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("status") == ActivitySubmission.Status.GRADED
            and cleaned_data.get("score") is None
        ):
            self.add_error("score", "Enter a score before marking this work as graded.")
        return cleaned_data

class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["content", "priority"]

        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "comment-input",
                    "rows": 2,
                    "maxlength": 1000,
                    "placeholder": "Write a comment...",
                }
            ),
            "priority": forms.Select(
                attrs={
                    "class": "comment-priority",
                }
            ),
        }

    def clean_content(self):
        content = self.cleaned_data["content"].strip()

        if not content:
            raise forms.ValidationError(
                "Write a comment before posting."
            )

        return content

class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom

        fields = [
            "class_name",
            "subject",
            "grade_level",
            "section",
            "school_year",
            "description",
        ]

        widgets = {
            "class_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Science 8 - Section A",
                }
            ),
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Science",
                }
            ),
            "grade_level": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Grade 8",
                }
            ),
            "section": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Section A",
                }
            ),
            "school_year": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: 2026-2027",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Optional class description",
                }
            ),
        }


class InviteStudentForm(forms.Form):
    email = forms.EmailField(
        label="Student email",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "student@example.com",
            }
        ),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class JoinClassForm(forms.Form):
    class_code = forms.CharField(
        label="Class code",
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "class": "form-control text-uppercase",
                "placeholder": "Enter class code",
                "autocomplete": "off",
            }
        ),
    )

    def clean_class_code(self):
        return self.cleaned_data["class_code"].strip().upper()


class StudentLinkRequestForm(forms.Form):
    lrn = forms.CharField(
        label="Learner Reference Number",
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter the student's LRN",
                "autocomplete": "off",
            }
        ),
    )
    relationship = forms.ChoiceField(
        choices=ParentStudentLink.Relationship.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean_lrn(self):
        return self.cleaned_data["lrn"].strip()

# =========================================================
# CLASS CALENDAR EVENT FORM
# Teacher only
# =========================================================

class ClassCalendarEventForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent

        fields = [
            "title",
            "description",
            "event_type",
            "start_at",
            "end_at",
            "all_day",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Performance Task",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional instructions",
                }
            ),
            "event_type": forms.Select(
                attrs={"class": "form-select"}
            ),
            "start_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
            ),
            "end_at": forms.DateTimeInput(
                format="%Y-%m-%dT%H:%M",
                attrs={
                    "class": "form-control",
                    "type": "datetime-local",
                },
            ),
            "all_day": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["start_at"].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]
        self.fields["end_at"].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]

        # These are the only event types Teachers need.
        self.fields["event_type"].choices = [
            (
                CalendarEvent.EventType.ACTIVITY,
                "Class Activity",
            ),
            (
                CalendarEvent.EventType.DEADLINE,
                "Deadline",
            ),
            (
                CalendarEvent.EventType.MEETING,
                "Meeting",
            ),
            (
                CalendarEvent.EventType.OTHER,
                "Other",
            ),
        ]

    def clean(self):
        cleaned_data = super().clean()

        start_at = cleaned_data.get("start_at")
        end_at = cleaned_data.get("end_at")

        if start_at and end_at and end_at < start_at:
            self.add_error(
                "end_at",
                "The end date cannot be earlier than the start date.",
            )

        return cleaned_data
