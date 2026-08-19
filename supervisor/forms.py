from django import forms
from django.contrib.auth import authenticate
from django.db import transaction

from accounts.models import Principal, School, Teacher, User


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
        self.fields["school"].queryset = School.objects.order_by("school_name")

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
