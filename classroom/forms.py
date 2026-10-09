from django import forms

from accounts.models import ParentStudentLink

from .models import (
    Announcement,
    CalendarEvent,
    ClassPost,
    Classroom,
    Comment,
)


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
