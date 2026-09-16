from django import forms

from .models import GradeItem, GradebookSettings


class GradeItemForm(forms.ModelForm):
    class Meta:
        model = GradeItem
        fields = ["title", "component", "highest_possible_score"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "component": forms.Select(attrs={"class": "form-select"}),
            "highest_possible_score": forms.NumberInput(
                attrs={"class": "form-control", "min": "1", "step": "0.01"}
            ),
        }

    def clean_highest_possible_score(self):
        value = self.cleaned_data["highest_possible_score"]
        if value <= 0:
            raise forms.ValidationError("The highest possible score must be greater than zero.")
        return value


class GradebookSettingsForm(forms.ModelForm):
    class Meta:
        model = GradebookSettings
        fields = [
            "written_work_weight",
            "performance_task_weight",
            "assessment_weight",
        ]
        widgets = {
            "written_work_weight": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
            "performance_task_weight": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
            "assessment_weight": forms.NumberInput(
                attrs={"class": "form-control", "min": 0, "max": 100}
            ),
        }

    def clean(self):
        data = super().clean()
        total = sum(
            data.get(field, 0) or 0
            for field in self.Meta.fields
        )
        if total != 100:
            raise forms.ValidationError("The three component weights must total 100%.")
        return data
