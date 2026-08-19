from django import forms

from accounts.models import ParentStudentLink

from .models import Classroom


class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom

        fields = [
            "class_name",
            "subject",
            "grade_level",
            "section",
            "school_year",
            "quarter",
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
            "quarter": forms.Select(
                attrs={"class": "form-select"}
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
