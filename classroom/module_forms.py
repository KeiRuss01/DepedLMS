from django import forms
from django.forms import inlineformset_factory

from .models import (
    Module,
    ModuleSubmission,
)
from .module_validators import validate_pdf, validate_answer_file


def apply_bootstrap(form):
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            css_class = "form-check-input"
        elif isinstance(field.widget, forms.Select):
            css_class = "form-select"
        else:
            css_class = "form-control"
        existing_class = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing_class} {css_class}".strip()


class ModuleCreateForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = [
            "title", "instructions", "pdf", "term", "week",
            "due_at", "allow_late", "hidden_pages",
        ]
        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 3}),
            "pdf": forms.FileInput(attrs={"accept": "application/pdf,.pdf"}),
            "due_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }
        help_texts = {
            "hidden_pages": (
                "Optional Teacher-only pages, such as an answer key. "
                "Example: 18, 20-22"
            ),
            "due_at": "This one deadline applies to the complete module.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)

    def clean_pdf(self):
        upload = self.cleaned_data["pdf"]
        validate_pdf(upload)
        return upload


class ModuleEditForm(ModuleCreateForm):
    """Edit Module details while keeping the current PDF optional."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pdf"].required = False
        self.fields["pdf"].help_text = (
            "Leave this blank to keep the current PDF. Upload a PDF only "
            "when you want to replace it."
        )

    def clean_pdf(self):
        upload = self.cleaned_data.get("pdf")
        if upload is False:
            raise forms.ValidationError(
                "A module must keep a PDF. Upload a replacement instead."
            )
        if upload and hasattr(upload, "content_type"):
            validate_pdf(upload)
        return upload


class ModuleScoreForm(forms.ModelForm):
    """Lets the Teacher set the score after inspecting the uploaded PDF."""

    class Meta:
        model = Module
        fields = ["max_score"]
        labels = {"max_score": "Maximum score"}
        help_texts = {
            "max_score": (
                "Review the Module first, then enter the total number of points "
                "for the complete worksheet."
            ),
        }
        widgets = {
            "max_score": forms.NumberInput(attrs={"min": 1, "max": 10000}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)

    def clean_max_score(self):
        max_score = self.cleaned_data["max_score"]
        if max_score < 1:
            raise forms.ValidationError("Enter at least 1 point.")

        highest_existing_score = (
            self.instance.submissions.exclude(score__isnull=True)
            .order_by("-score")
            .values_list("score", flat=True)
            .first()
        )
        if highest_existing_score is not None and max_score < highest_existing_score:
            raise forms.ValidationError(
                f"This cannot be lower than the existing score of "
                f"{highest_existing_score:g}."
            )
        return max_score


class SubmissionGradeForm(forms.ModelForm):
    """Grades one complete PDF Module submission."""

    class Meta:
        model = ModuleSubmission
        fields = ["score", "feedback"]
        widgets = {"feedback": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, module, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = module
        self.fields["score"].required = True
        self.fields["score"].label = f"Module score (out of {module.total_points})"
        self.fields["score"].widget.attrs.update({
            "min": 0,
            "max": module.total_points,
            "step": "0.01",
        })
        apply_bootstrap(self)

    def clean_score(self):
        score = self.cleaned_data["score"]
        if score > self.module.total_points:
            raise forms.ValidationError(
                f"The maximum Module score is {self.module.total_points}."
            )
        return score
