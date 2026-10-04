from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import PasswordChangeForm
from django.db import transaction

from .models import (
    Parent,
    Principal,
    School,
    Student,
    Teacher,
    User,
    UserPreference,
)


class AccountLoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, request=None, *args, allowed_roles=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.allowed_roles = set(allowed_roles or [])
        self.user_cache = None

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(
                self.request,
                username=email,
                password=password,
            )
            if self.user_cache is None:
                raise forms.ValidationError("Incorrect email or password.")
            if not self.user_cache.is_active:
                raise forms.ValidationError("This account is not active.")

            if self.allowed_roles and self.user_cache.role not in self.allowed_roles:
                raise forms.ValidationError(
                    "Administrative accounts must use the Administration Portal."
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache


class AccountSignupForm(forms.Form):
    PUBLIC_ROLES = (
        (User.Role.STUDENT, "Student"),
        (User.Role.PARENT, "Parent"),
    )

    firstname = forms.CharField(max_length=100)
    middlename = forms.CharField(max_length=100, required=False)
    lastname = forms.CharField(max_length=100)
    suffix = forms.CharField(max_length=20, required=False)
    email = forms.EmailField(max_length=100)
    phone_number = forms.CharField(max_length=11, required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=PUBLIC_ROLES)
    school = forms.ModelChoiceField(queryset=School.objects.none(), required=False)

    employee_id = forms.CharField(max_length=50, required=False)
    specialization = forms.CharField(max_length=100, required=False)
    designation = forms.CharField(max_length=150, required=False)

    lrn = forms.CharField(max_length=20, required=False)
    gender = forms.ChoiceField(choices=Student.Gender.choices, required=False)
    birth_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    address = forms.CharField(required=False, widget=forms.Textarea)

    relationship = forms.ChoiceField(
        choices=Parent.Relationship.choices,
        required=False,
    )
    agree_terms = forms.BooleanField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["school"].queryset = School.objects.order_by("school_name")
        for field_name, field in self.fields.items():
            if field_name in {"role", "agree_terms"}:
                continue
            css_class = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["class"] = css_class

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get("phone_number", "").strip()
        if phone_number and not phone_number.isdigit():
            raise forms.ValidationError("Enter numbers only for the phone number.")
        return phone_number

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        role = cleaned_data.get("role")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "The passwords do not match.")
        if password1 and len(password1) < 8:
            self.add_error("password1", "Use at least 8 characters.")

        if role in {User.Role.STUDENT, User.Role.TEACHER, User.Role.PRINCIPAL}:
            if not cleaned_data.get("school"):
                self.add_error("school", "Select your school.")

        if role in {User.Role.TEACHER, User.Role.PRINCIPAL}:
            employee_id = cleaned_data.get("employee_id", "").strip()
            if not employee_id:
                self.add_error("employee_id", "Enter your DepEd employee ID.")
            elif role == User.Role.TEACHER and Teacher.objects.filter(
                employee_id=employee_id
            ).exists():
                self.add_error("employee_id", "This employee ID is already registered.")
            elif role == User.Role.PRINCIPAL and Principal.objects.filter(
                employee_id=employee_id
            ).exists():
                self.add_error("employee_id", "This employee ID is already registered.")

        if role == User.Role.STUDENT:
            for field_name, message in (
                ("lrn", "Enter your Learner Reference Number."),
                ("gender", "Select your gender."),
                ("birth_date", "Enter your birth date."),
            ):
                if not cleaned_data.get(field_name):
                    self.add_error(field_name, message)
            lrn = cleaned_data.get("lrn", "").strip()
            if lrn and Student.objects.filter(lrn=lrn).exists():
                self.add_error("lrn", "This LRN is already registered.")

        if role == User.Role.PARENT and not cleaned_data.get("relationship"):
            self.add_error("relationship", "Select your relationship to the learner.")

        return cleaned_data

    @transaction.atomic
    def save(self):
        data = self.cleaned_data
        user = User.objects.create_user(
            email=data["email"],
            password=data["password1"],
            role=data["role"],
            phone_number=data.get("phone_number") or None,
            status=User.Status.ACTIVE,
        )

        common_name = {
            "firstname": data["firstname"],
            "middlename": data.get("middlename") or None,
            "lastname": data["lastname"],
        }

        if data["role"] == User.Role.STUDENT:
            Student.objects.create(
                user=user,
                school=data["school"],
                lrn=data["lrn"],
                suffix=data.get("suffix") or None,
                gender=data["gender"],
                birth_date=data["birth_date"],
                address=data.get("address") or None,
                **common_name,
            )
        elif data["role"] == User.Role.TEACHER:
            Teacher.objects.create(
                user=user,
                school=data["school"],
                employee_id=data["employee_id"],
                suffix=data.get("suffix") or None,
                specialization=data.get("specialization") or None,
                **common_name,
            )
        elif data["role"] == User.Role.PRINCIPAL:
            Principal.objects.create(
                user=user,
                school=data["school"],
                employee_id=data["employee_id"],
                suffix=data.get("suffix") or None,
                designation=data.get("designation") or "School Principal",
                **common_name,
            )
        else:
            Parent.objects.create(
                user=user,
                relationship=data["relationship"],
                **common_name,
            )

        return user

class ProfileUpdateForm(forms.ModelForm):
    phone_number = forms.CharField(
        max_length=13,
        required=True,
        label="Mobile number",
        help_text="Enter an active Philippine mobile number.",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "09XXXXXXXXX",
                "inputmode": "numeric",
            }
        ),
    )

    profile_picture = forms.ImageField(
        required=False,
        label="Profile picture",
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": ".jpg,.jpeg,.png,.webp",
            }
        ),
    )

    class Meta:
        model = User
        fields = [
            "profile_picture",
            "phone_number",
        ]

    def clean_phone_number(self):
        phone_number = self.cleaned_data["phone_number"].strip()

        # Remove commonly entered separators.
        phone_number = (
            phone_number
            .replace(" ", "")
            .replace("-", "")
        )

        # Convert +639XXXXXXXXX into 09XXXXXXXXX.
        if phone_number.startswith("+63"):
            phone_number = "0" + phone_number[3:]

        if not phone_number.isdigit():
            raise forms.ValidationError(
                "The mobile number must contain numbers only."
            )

        if len(phone_number) != 11 or not phone_number.startswith("09"):
            raise forms.ValidationError(
                "Enter a valid number using the format 09XXXXXXXXX."
            )

        return phone_number

    def clean_profile_picture(self):
        picture = self.cleaned_data.get("profile_picture")

        if not picture:
            return picture

        maximum_size = 2 * 1024 * 1024

        if picture.size > maximum_size:
            raise forms.ValidationError(
                "The profile picture must not exceed 2 MB."
            )

        return picture

class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference

        fields = [
            "theme",
            "text_size",
            "sound_enabled",
            "vibration_enabled",
            "new_submission_alerts",
            "pending_join_request_alerts",
            "deadline_reminder_alerts",
            "default_term",
            "default_grading_component",
        ]

        labels = {
            "theme": "Theme",
            "text_size": "Text size",
            "sound_enabled": "Sound",
            "vibration_enabled": "Vibration",
            "new_submission_alerts": "New student submissions",
            "pending_join_request_alerts": "Pending join requests",
            "deadline_reminder_alerts": "Submission deadline reminders",
            "default_term": "Default term",
            "default_grading_component": "Default grading component",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user

        select_fields = [
            "theme",
            "text_size",
            "default_term",
            "default_grading_component",
        ]

        for field_name in select_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update(
                    {"class": "form-select"}
                )

        checkbox_fields = [
            "sound_enabled",
            "vibration_enabled",
            "new_submission_alerts",
            "pending_join_request_alerts",
            "deadline_reminder_alerts",
        ]

        for field_name in checkbox_fields:
            if field_name in self.fields:
                self.fields[field_name].widget.attrs.update(
                    {
                        "class": "form-check-input settings-switch",
                        "role": "switch",
                    }
                )

        # Student accounts do not need Teacher-only settings.
        if user and user.role != User.Role.TEACHER:
            teacher_only_fields = [
                "new_submission_alerts",
                "pending_join_request_alerts",
                "deadline_reminder_alerts",
                "default_term",
                "default_grading_component",
            ]

            for field_name in teacher_only_fields:
                self.fields.pop(field_name, None)

class AccountPasswordChangeForm(PasswordChangeForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)

        for field in self.fields.values():
            field.widget.attrs.update(
                {
                    "class": "form-control",
                    "autocomplete": "new-password",
                }
            )

        self.fields["old_password"].widget.attrs[
            "autocomplete"
        ] = "current-password"
