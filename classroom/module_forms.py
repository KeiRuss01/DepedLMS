from django import forms
from django.forms import inlineformset_factory

from .models import (
    Module,
    ModuleAnswerSection,
    ModuleSubmission,
    SectionQuestion,
    SectionResponse,
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


class AnswerSectionForm(forms.ModelForm):
    class Meta:
        model = ModuleAnswerSection
        fields = [
            "title", "instructions", "answer_method", "page_start",
            "page_end", "required", "max_score", "max_files",
        ]
        widgets = {"instructions": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)
        self.fields["title"].help_text = (
            "Use the heading in the module, such as What I Know or Assessment."
        )
        self.fields["max_score"].help_text = (
            "For essays and uploaded work, the Teacher checks the response and "
            "enters a score up to this total."
        )

    def clean(self):
        data = super().clean()
        start = data.get("page_start")
        end = data.get("page_end")
        if start and end and end < start:
            self.add_error("page_end", "The ending page cannot be before the starting page.")
        if data.get("answer_method") == ModuleAnswerSection.AnswerMethod.NONE:
            data["max_score"] = 0
        return data


class SectionQuestionForm(forms.ModelForm):
    class Meta:
        model = SectionQuestion
        fields = [
            "prompt", "question_type", "choices_text", "correct_answer",
            "points", "required",
        ]
        widgets = {
            "prompt": forms.Textarea(
                attrs={"rows": 2, "class": "auto-grow"}
            ),
            "choices_text": forms.Textarea(
                attrs={"rows": 1, "class": "auto-grow"}
            ),
            "correct_answer": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)


SectionQuestionFormSet = inlineformset_factory(
    ModuleAnswerSection,
    SectionQuestion,
    form=SectionQuestionForm,
    extra=3,
    can_delete=True,
)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super(MultipleFileField, self).clean(upload, initial) for upload in files if upload]


class SectionResponseForm(forms.Form):
    def __init__(self, section, *args, response=None, complete=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        self.response = response
        self.complete = complete

        if section.answer_method == ModuleAnswerSection.AnswerMethod.STRUCTURED:
            saved = {}
            if response:
                saved = dict(response.answers.values_list("question_id", "answer_text"))
            for question in section.questions.all():
                name = f"question_{question.pk}"
                required = complete and question.required
                if question.question_type == SectionQuestion.QuestionType.MULTIPLE_CHOICE:
                    choices = [("", "Choose an answer")]
                    choices += [(choice, choice) for choice in question.choices]
                    field = forms.ChoiceField(choices=choices, required=required)
                elif question.question_type == SectionQuestion.QuestionType.TRUE_FALSE:
                    field = forms.ChoiceField(
                        choices=[("", "Choose an answer"), ("True", "True"), ("False", "False")],
                        required=required,
                    )
                elif question.question_type == SectionQuestion.QuestionType.LONG:
                    field = forms.CharField(
                        widget=forms.Textarea(attrs={"rows": 6}),
                        required=required,
                        max_length=20000,
                    )
                else:
                    field = forms.CharField(required=required, max_length=5000)
                field.label = f"{question.position}. {question.prompt} ({question.points:g} points)"
                field.initial = saved.get(question.pk, "")
                self.fields[name] = field
        elif section.answer_method == ModuleAnswerSection.AnswerMethod.WRITTEN:
            self.fields["written_answer"] = forms.CharField(
                label=f"Written answer (maximum {section.max_score} points)",
                widget=forms.Textarea(attrs={"rows": 16}),
                max_length=50000,
                required=complete and section.required,
                initial=response.written_answer if response else "",
            )
        elif section.answer_method == ModuleAnswerSection.AnswerMethod.FILE:
            self.fields["answer_files"] = MultipleFileField(
                label=f"Upload files (maximum {section.max_files})",
                required=False,
                validators=[validate_answer_file],
                widget=MultipleFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"}),
            )
        apply_bootstrap(self)

    def clean(self):
        data = super().clean()
        if self.section.answer_method == ModuleAnswerSection.AnswerMethod.FILE:
            new_files = data.get("answer_files", [])
            old_count = self.response.attachments.count() if self.response else 0
            if len(new_files) + old_count > self.section.max_files:
                self.add_error("answer_files", f"You may upload up to {self.section.max_files} files.")
            if self.complete and self.section.required and not new_files and not old_count:
                self.add_error("answer_files", "Upload at least one file to complete this section.")
        return data


class SectionGradeForm(forms.ModelForm):
    class Meta:
        model = SectionResponse
        fields = ["score", "feedback"]
        widgets = {"feedback": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, section, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.section = section
        self.fields["score"].required = True
        self.fields["score"].label = f"Final score (out of {section.max_score})"
        self.fields["score"].widget.attrs.update({"min": 0, "max": section.max_score})
        apply_bootstrap(self)

    def clean_score(self):
        score = self.cleaned_data["score"]
        if score > self.section.max_score:
            raise forms.ValidationError(f"The maximum score is {self.section.max_score}.")
        return score


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
