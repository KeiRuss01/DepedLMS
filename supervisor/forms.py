import re
import unicodedata
from datetime import datetime, time

from django import forms
from django.contrib.auth import authenticate
from django.db import transaction
from django.utils import timezone

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

class DistrictAnnouncementForm(forms.ModelForm):
    all_schools = forms.BooleanField(
        required=False,
        initial=True,
        label="Send to all schools",
    )
    target_schools = forms.ModelMultipleChoiceField(
        queryset=School.objects.all().order_by("school_name"),
        required=False,
        label="Selected schools",
        widget=forms.SelectMultiple(attrs={"class": "form-select"}),
    )

    class Meta:
        model = SchoolAnnouncement
        fields = ("title", "content", "priority")
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "District announcement title",
                }
            ),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Write the district announcement...",
                }
            ),
            "priority": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("all_schools") and not cleaned_data.get(
            "target_schools"
        ):
            self.add_error(
                "target_schools",
                "Select at least one school or choose all schools.",
            )
        return cleaned_data


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


def _account_token(value):
    """Return a lowercase ASCII token safe for generated email addresses."""
    normalized = unicodedata.normalize("NFKD", (value or "").strip())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", ascii_value.lower())


def _given_name_initials(value):
    normalized = unicodedata.normalize("NFKD", (value or "").strip())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    name_parts = re.findall(r"[A-Za-z0-9]+", ascii_value)
    return "".join(part[0].lower() for part in name_parts if part)


def _available_generated_email(firstname, middlename, lastname):
    last_token = _account_token(lastname)
    first_initials = _given_name_initials(firstname)
    middle_initials = _given_name_initials(middlename)

    local_parts = [last_token, first_initials]
    if middle_initials:
        local_parts.append(middle_initials[0])
    base_local = ".".join(part for part in local_parts if part)

    candidate = f"{base_local}@gmail.com"
    suffix_number = 2
    while User.objects.filter(email__iexact=candidate).exists():
        candidate = f"{base_local}{suffix_number}@gmail.com"
        suffix_number += 1
    return candidate


def _generated_temporary_password(lastname):
    name_parts = re.findall(r"[A-Za-z0-9]+", unicodedata.normalize(
        "NFKD", (lastname or "").strip()
    ).encode("ascii", "ignore").decode("ascii"))
    password_name = "".join(part.capitalize() for part in name_parts)
    return f"{password_name}{timezone.localdate().year}"


class GeneratedStaffAccountForm(forms.Form):
    email = forms.EmailField(
        max_length=100,
        required=False,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control generated-account-email",
                "placeholder": "Generated after entering the name",
                "readonly": True,
            }
        ),
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
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control generated-account-password",
                "placeholder": "Generated after entering the last name",
                "readonly": True,
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()
        firstname = cleaned_data.get("firstname")
        lastname = cleaned_data.get("lastname")
        if firstname and lastname:
            cleaned_data["email"] = _available_generated_email(
                firstname,
                cleaned_data.get("middlename"),
                lastname,
            )
            cleaned_data["password1"] = _generated_temporary_password(lastname)
        return cleaned_data


class PrincipalAccountForm(GeneratedStaffAccountForm):
    school = forms.ModelChoiceField(
        queryset=School.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # A school can only have one assigned Principal account.
        self.fields["school"].queryset = School.objects.filter(
            principals__isnull=True,
        ).order_by("school_name")

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


class TeacherAccountForm(GeneratedStaffAccountForm):
    def __init__(self, *args, school, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school

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
        all_day = cleaned_data.get("all_day")

        if all_day and start_at:
            current_timezone = timezone.get_current_timezone()
            start_date = (
                timezone.localtime(start_at).date()
                if timezone.is_aware(start_at)
                else start_at.date()
            )
            end_date = start_date
            if end_at:
                end_date = (
                    timezone.localtime(end_at).date()
                    if timezone.is_aware(end_at)
                    else end_at.date()
                )

            start_at = timezone.make_aware(
                datetime.combine(start_date, time.min),
                current_timezone,
            )
            end_at = timezone.make_aware(
                datetime.combine(end_date, time.max),
                current_timezone,
            )
            cleaned_data["start_at"] = start_at
            cleaned_data["end_at"] = end_at

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
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d",
        ]
        self.fields["end_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d",
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
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d",
        ]
        self.fields["end_at"].input_formats = [
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d",
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
