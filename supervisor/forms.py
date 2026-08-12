from django import forms
from django.contrib.auth import authenticate

from accounts.models import School, User


class SupervisorLoginForm(forms.Form):
    """Plain email/password login form. Authentication itself is delegated
    to Django's `authenticate()` so password hashing/checking stays inside
    Django's auth machinery -- this form just adds the "must be a
    supervisor account" rule on top of it."""

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

        if user.role != User.Role.SUPERVISOR:
            raise forms.ValidationError(
                "This portal is for the District Supervisor account only."
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
