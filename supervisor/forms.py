from django import forms
from django.contrib.auth import authenticate
from django.db import transaction

from accounts.models import Principal, School, Teacher, User
from classroom.models import AcademicTerm, CalendarEvent
from .models import SchoolAnnouncement


class SchoolAnnouncementForm(forms.ModelForm):
    class Meta:
        model = SchoolAnnouncement
        fields = ("title", "content", "priority")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Announcement title",
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Write the school announcement...",
                }
            ),
            "priority": forms.Select(attrs={"class": "form-select"}),
        }


class AdministrationLoginForm(forms.Form):
    """Email/password login for District Supervisors and Principals."""

    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "you@deped.gov.ph",
                "autofocus": True,
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Password"}
        )
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if not email or not password:
            return cleaned_data

        user = authenticate(self.request, username=email, password=password)

        if user is None:
            raise forms.ValidationError(
                "Incorrect email or password. Please try again."
            )

        administration_roles = {
            User.Role.SUPERVISOR,
            User.Role.PRINCIPAL,
        }
        if user.role not in administration_roles:
            raise forms.ValidationError(
                "This account belongs to the Classroom Portal."
            )

        if user.status != User.Status.ACTIVE:
            raise forms.ValidationError(
                "This account is not active. Please contact the system administrator."
            )

        self.user_cache = user
        return cleaned_data

    def get_user(self):
        return self.user_cache


class SchoolProfileForm(forms.ModelForm):
    class Meta:
        model = School
        fields = (
            "school_name",
            "logo",
            "school_id_number",
            "region",
            "division",
            "district",
            "address",
        )
        widgets = {
            "school_name": forms.TextInput(attrs={"placeholder": "School name"}),
            "school_id_number": forms.TextInput(attrs={"placeholder": "Optional"}),
            "region": forms.TextInput(attrs={"placeholder": "Optional"}),
            "division": forms.TextInput(attrs={"placeholder": "Optional"}),
            "district": forms.TextInput(attrs={"placeholder": "Optional"}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"

    def clean_school_name(self):
        school_name = self.cleaned_data["school_name"].strip()
        existing = School.objects.filter(school_name__iexact=school_name)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError("A school with this name already exists.")
        return school_name


class PrincipalAccountForm(forms.Form):
    email = forms.EmailField(
        max_length=100,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "principal@school.edu.ph"}),
    )
    firstname = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
    )
    middlename = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
    )
    lastname = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
    )
    suffix = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
    )
    school = forms.ModelChoiceField(
        queryset=School.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    password1 = forms.CharField(
        label="Temporary password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "At least 8 characters"}),
    )
    password2 = forms.CharField(
        label="Confirm temporary password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Repeat password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A school can only have one assigned Principal account.
        self.fields["school"].queryset = School.objects.filter(
            principals__isnull=True,
        ).order_by("school_name")

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and len(password1) < 8:
            self.add_error("password1", "Use at least 8 characters.")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        return cleaned_data

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(
            email=data["email"],
            password=data["password1"],
            role=User.Role.PRINCIPAL,
            status=User.Status.ACTIVE,
        )
        principal = Principal.objects.create(
            user=user,
            school=data["school"],
            employee_id="",
            firstname=data["firstname"].strip(),
            middlename=data.get("middlename", "").strip() or None,
            lastname=data["lastname"].strip(),
            suffix=data.get("suffix", "").strip() or None,
            designation="School Principal",
        )
        return principal


class TeacherAccountForm(forms.Form):
    email = forms.EmailField(
        max_length=100,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "teacher@school.edu.ph"}),
    )
    firstname = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "First name"}),
    )
    middlename = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
    )
    lastname = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Last name"}),
    )
    suffix = forms.CharField(
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
    )
    password1 = forms.CharField(
        label="Temporary password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "At least 8 characters"}),
    )
    password2 = forms.CharField(
        label="Confirm temporary password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Repeat password"}),
    )

    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and len(password1) < 8:
            self.add_error("password1", "Use at least 8 characters.")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        return cleaned_data

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(
            email=data["email"],
            password=data["password1"],
            role=User.Role.TEACHER,
            status=User.Status.ACTIVE,
        )
        teacher = Teacher.objects.create(
            user=user,
            school=self.school,
            employee_id="",
            firstname=data["firstname"].strip(),
            middlename=data.get("middlename", "").strip() or None,
            lastname=data["lastname"].strip(),
            suffix=data.get("suffix", "").strip() or None,
            specialization=None,
        )
        return teacher

# =========================================================
# CALENDAR FORM HELPERS
# =========================================================

class CalendarDateValidationMixin:
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


# =========================================================
# ACADEMIC TERM FORM
# Supervisor only
# =========================================================

class AcademicTermForm(forms.ModelForm):
    class Meta:
        model = AcademicTerm
        fields = [
            "school_year",
            "term",
            "start_date",
            "end_date",
        ]

        widgets = {
            "school_year": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: 2026-2027",
                }
            ),
            "term": forms.Select(
                attrs={"class": "form-select"}
            ),
            "start_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
            "end_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()

        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date and end_date < start_date:
            self.add_error(
                "end_date",
                "The end date cannot be earlier than the start date.",
            )

        return cleaned_data


# =========================================================
# DISTRICT CALENDAR EVENT FORM
# Supervisor only
# =========================================================

class DistrictCalendarEventForm(
    CalendarDateValidationMixin,
    forms.ModelForm,
):
    class Meta:
        model = CalendarEvent

        fields = [
            "title",
            "description",
            "school_year",
            "event_type",
            "start_at",
            "end_at",
            "all_day",
            "applies_to_all_schools",
            "target_schools",
            "source",
            "source_file",
            "status",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: Term 1 Assessment Period",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional event description",
                }
            ),
            "school_year": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: 2026-2027",
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
            "applies_to_all_schools": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "target_schools": forms.CheckboxSelectMultiple(),
            "source": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Example: DepEd Order No. 009, s. 2026"
                    ),
                }
            ),
            "source_file": forms.ClearableFileInput(
                attrs={"class": "form-control"}
            ),
            "status": forms.Select(
                attrs={"class": "form-select"}
            ),
        }

    def __init__(self, *args, supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["start_at"].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]
        self.fields["end_at"].input_formats = [
            "%Y-%m-%dT%H:%M"
        ]

        schools = School.objects.order_by("school_name")

        # Only show schools from the Supervisor's district.
        if supervisor and supervisor.district:
            schools = schools.filter(
                district__iexact=supervisor.district
            )

        self.fields["target_schools"].queryset = schools
        self.fields["target_schools"].required = False

    def clean(self):
        cleaned_data = super().clean()

        applies_to_all = cleaned_data.get(
            "applies_to_all_schools"
        )
        target_schools = cleaned_data.get("target_schools")

        if (
            not applies_to_all
            and target_schools is not None
            and not target_schools.exists()
        ):
            self.add_error(
                "target_schools",
                "Select at least one school or choose all schools.",
            )

        return cleaned_data


# =========================================================
# SCHOOL CALENDAR EVENT FORM
# Principal only
# =========================================================

class SchoolCalendarEventForm(
    CalendarDateValidationMixin,
    forms.ModelForm,
):
    class Meta:
        model = CalendarEvent

        fields = [
            "title",
            "description",
            "school_year",
            "event_type",
            "start_at",
            "end_at",
            "all_day",
            "status",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: School Intramurals",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional event description",
                }
            ),
            "school_year": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Example: 2026-2027",
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
            "status": forms.Select(
                attrs={"class": "form-select"}
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

        # Principals should not create classroom deadlines.
        self.fields["event_type"].choices = [
            (
                CalendarEvent.EventType.ACADEMIC,
                "Academic Schedule",
            ),
            (
                CalendarEvent.EventType.HOLIDAY,
                "Holiday",
            ),
            (
                CalendarEvent.EventType.NO_CLASS,
                "No Classes",
            ),
            (
                CalendarEvent.EventType.GRADING,
                "Grading Schedule",
            ),
            (
                CalendarEvent.EventType.ACTIVITY,
                "School Activity",
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