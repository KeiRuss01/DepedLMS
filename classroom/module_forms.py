from django import forms
from django.forms import modelformset_factory

from .models import Module, ModuleItem
from .module_validators import validate_pdf, validate_answer_file


def apply_bootstrap(form):
    for field in form.fields.values():
        if isinstance(field.widget, forms.CheckboxInput):
            css_class = "form-check-input"
        elif isinstance(field.widget, forms.Select):
            css_class = "form-select"
        else:
            css_class = "form-control"

        field.widget.attrs["class"] = css_class


class ModuleCreateForm(forms.ModelForm):
    number_of_items = forms.IntegerField(
        min_value=1,
        max_value=50,
        initial=5,
        help_text="Used only for a numbered answer sheet.",
    )

    default_answer_type = forms.ChoiceField(
        choices=ModuleItem.AnswerType.choices,
        initial=ModuleItem.AnswerType.SHORT,
        help_text="You can change individual items before publishing.",
    )

    class Meta:
        model = Module

        fields = [
            "title",
            "instructions",
            "pdf",
            "term",
            "answer_mode",
            "max_score",
            "due_at",
            "allow_late",
        ]

        widgets = {
            "instructions": forms.Textarea(attrs={"rows": 3}),
            "pdf": forms.FileInput(
                attrs={"accept": "application/pdf,.pdf"}
            ),
            "due_at": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)

    def clean_pdf(self):
        upload = self.cleaned_data["pdf"]
        validate_pdf(upload)
        return upload


class ModuleItemForm(forms.ModelForm):
    class Meta:
        model = ModuleItem
        fields = ["label", "answer_type"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_bootstrap(self)


ModuleItemFormSet = modelformset_factory(
    ModuleItem,
    form=ModuleItemForm,
    extra=0,
    can_delete=False,
    edit_only=True,
    max_num=50,
    validate_max=True,
)


class StudentModuleForm(forms.Form):
    def __init__(
        self,
        module,
        *args,
        submission=None,
        complete=False,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.module = module
        self.submission = submission
        self.complete = complete

        if module.answer_mode == Module.AnswerMode.STRUCTURED:
            saved_answers = {}

            if submission:
                saved_answers = dict(
                    submission.answers.values_list(
                        "item_id",
                        "answer_text",
                    )
                )

            for item in module.items.all():
                field_name = f"item_{item.pk}"

                if item.answer_type == ModuleItem.AnswerType.CHOICE:
                    field = forms.ChoiceField(
                        choices=[
                            ("", "Choose an answer"),
                            ("A", "A"),
                            ("B", "B"),
                            ("C", "C"),
                            ("D", "D"),
                        ],
                        required=complete,
                    )
                else:
                    widget = (
                        forms.Textarea(attrs={"rows": 4})
                        if item.answer_type == ModuleItem.AnswerType.LONG
                        else forms.TextInput()
                    )

                    field = forms.CharField(
                        widget=widget,
                        max_length=10000,
                        required=complete,
                    )

                field.label = item.label
                field.initial = saved_answers.get(item.pk, "")
                self.fields[field_name] = field

        elif module.answer_mode == Module.AnswerMode.WRITTEN:
            self.fields["written_answer"] = forms.CharField(
                label="Your answer",
                widget=forms.Textarea(attrs={"rows": 14}),
                max_length=50000,
                required=complete,
                initial=(
                    submission.written_answer
                    if submission else ""
                ),
            )

        else:
            self.fields["answer_file"] = forms.FileField(
                label="Your answer file",
                required=False,
                validators=[validate_answer_file],
                widget=forms.FileInput(
                    attrs={
                        "accept": ".pdf,.jpg,.jpeg,.png",
                    }
                ),
            )

        apply_bootstrap(self)

    def clean(self):
        cleaned_data = super().clean()

        if (
            self.complete
            and self.module.answer_mode == Module.AnswerMode.FILE
        ):
            existing_file = (
                self.submission
                and self.submission.answer_file
            )

            if not cleaned_data.get("answer_file") and not existing_file:
                self.add_error(
                    "answer_file",
                    "Attach your answer before submitting.",
                )

        return cleaned_data


class ModuleGradeForm(forms.Form):
    score = forms.DecimalField(
        min_value=0,
        max_digits=7,
        decimal_places=2,
    )

    feedback = forms.CharField(
        required=False,
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 5}),
    )

    def __init__(self, module, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.module = module
        self.fields["score"].widget.attrs["max"] = module.max_score
        apply_bootstrap(self)

    def clean_score(self):
        score = self.cleaned_data["score"]

        if score > self.module.max_score:
            raise forms.ValidationError(
                f"The maximum score is {self.module.max_score}."
            )

        return score