import re
from django import forms
from django.core.exceptions import ValidationError
from .models import (
    SchoolInfoModel, SchoolSettingModel, SessionModel, ClassSectionModel,
    ClassesModel, ClassSectionInfoModel
)


class SchoolInfoForm(forms.ModelForm):
    """Form for the SchoolInfoModel."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields:
            if field != 'separate_school_section':
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'autocomplete': 'off'
                })

    class Meta:
        model = SchoolInfoModel
        fields = '__all__'


class SchoolSettingForm(forms.ModelForm):
    """
    Form for SchoolSettingModel with validation for financial logic.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields:
            if field not in ['auto_low_balance_notification', 'allow_student_debt']:
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'autocomplete': 'off'
                })

    class Meta:
        model = SchoolSettingModel
        fields = '__all__'

    def clean_max_student_debt(self):
        """Ensures the maximum student debt is not a negative number."""
        max_debt = self.cleaned_data.get('max_student_debt')
        if max_debt < 0:
            raise ValidationError("Maximum student debt cannot be a negative amount.")
        return max_debt

    def clean_low_balance(self):
        """Ensures the low balance threshold is not a negative number."""
        low_balance = self.cleaned_data.get('low_balance')
        if low_balance < 0:
            raise ValidationError("Low balance threshold cannot be a negative amount.")
        return low_balance


class SessionForm(forms.ModelForm):
    """
    Form for SessionModel with validation for date ranges.
    """

    class Meta:
        model = SessionModel
        fields = '__all__'

    def clean(self):
        """Ensures the end year is not earlier than the start year."""
        cleaned_data = super().clean()
        start_year = cleaned_data.get('start_year')
        end_year = cleaned_data.get('end_year')

        if start_year and end_year and end_year < start_year:
            raise ValidationError("Validation Error: The end year cannot be earlier than the start year.")
        return cleaned_data


class ClassSectionForm(forms.ModelForm):
    """Form for the ClassSectionModel with uniqueness validation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields:
            if field not in ['auto_low_balance_notification', 'allow_student_debt']:
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'autocomplete': 'off'
                })

    class Meta:
        model = ClassSectionModel
        fields = ['name']

    def clean_name(self):
        """Validates the section name for length, characters, and uniqueness."""
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError("Section name is required.")

        if not re.match(r'^[a-zA-Z0-9\s\-]+$', name):
            raise ValidationError("Section name can only contain letters, numbers, spaces, and hyphens.")

        # ✔️ UNIQUENESS CHECK: Inspired by your example form.
        qs = ClassSectionModel.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"A class section named '{name}' already exists.")
        return name


class ClassForm(forms.ModelForm):
    """Form for the ClassesModel with uniqueness validation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in self.fields:
            if field not in ['section']:
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'autocomplete': 'off'
                })

    class Meta:
        model = ClassesModel
        fields = ['name', 'code', 'section']
        widgets = {
            'section': forms.CheckboxSelectMultiple,
        }

    def clean_name(self):
        """Validates the class name for length, characters, and uniqueness."""
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError("Class name is required.")

        name = ' '.join(name.strip().split())
        if len(name) < 2:
            raise ValidationError("Class name must be at least 2 characters long.")

        if not re.match(r'^[a-zA-Z0-9\s\-]+$', name):
            raise ValidationError("Class name can only contain letters, numbers, spaces, and hyphens.")

        # ✔️ UNIQUENESS CHECK: Inspired by your example form.
        qs = ClassesModel.objects.filter(name__iexact=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"A class named '{name}' already exists.")
        return name


class ClassSectionInfoForm(forms.ModelForm):
    """
    Form for ClassSectionInfoModel with relational validation.
    """

    class Meta:
        model = ClassSectionInfoModel
        fields = ['student_class', 'section', 'form_teacher']

    def clean(self):
        """
        Ensures that the selected section is actually associated with the
        selected class in the ClassesModel.
        """
        cleaned_data = super().clean()
        student_class = cleaned_data.get('student_class')
        section = cleaned_data.get('section')

        if student_class and section:
            if not student_class.section.filter(pk=section.pk).exists():
                self.add_error(
                    'section',
                    f"'{section}' is not a valid section for the class '{student_class}'. Please check the class settings."
                )
        return cleaned_data

