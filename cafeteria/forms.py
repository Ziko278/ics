from django import forms
from django.core.exceptions import ValidationError
from cafeteria.models import MealModel, CafeteriaSettingModel
from finance.models import FeeModel


class MealForm(forms.ModelForm):
    """
    Form for creating and updating meal types.
    """

    class Meta:
        model = MealModel
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_name(self):
        """
        Custom validation to ensure the meal name is unique (case-insensitive).
        """
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError("Meal name cannot be empty.")

        qs = MealModel.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("A meal type with this name already exists.")

        return name


class CafeteriaSettingForm(forms.ModelForm):
    """
    A form for creating and updating the singleton CafeteriaSettingModel.
    """
    class Meta:
        model = CafeteriaSettingModel
        fields = ['max_meals_per_day', 'cafeteria_fee', 'is_active']
        widgets = {
            'max_meals_per_day': forms.NumberInput(attrs={'class': 'form-control'}),
            'cafeteria_fee': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input form-switch'}),
        }
        help_texts = {
            'is_active': 'Globally enable or disable the cafeteria meal collection system.'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate the dropdown with all available fee types from the finance app
        self.fields['cafeteria_fee'].queryset = FeeModel.objects.all().order_by('name')
        self.fields['cafeteria_fee'].help_text = "Select the fee that students must pay to be eligible for meals."
        self.fields['cafeteria_fee'].required = False

