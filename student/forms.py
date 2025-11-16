import re
from django import forms
from django.core.exceptions import ValidationError
from django.forms import CheckboxSelectMultiple

from admin_site.models import ClassesModel, ClassSectionModel, ClassSectionInfoModel
from .models import StudentModel, ParentModel, StudentSettingModel, UtilityModel


class UtilityForm(forms.ModelForm):
    """
    Form for creating and updating school utilities.
    """

    class Meta:
        model = UtilityModel
        fields = ['name', 'code', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Boarding, Transport'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., BRD, TRN'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                                 'placeholder': 'Optional: A brief description of the utility'}),
        }

    def clean_name(self):
        """
        Custom validation to ensure the utility name is unique (case-insensitive).
        """
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError("Utility name cannot be empty.")

        # Check for other utilities with the same name, ignoring case.
        qs = UtilityModel.objects.filter(name__iexact=name)

        # If we are in "update" mode, exclude the current instance from the check.
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("A utility with this name already exists.")

        return name

    def clean_code(self):
        """
        Custom validation to ensure the utility code is unique (case-insensitive).
        """
        code = self.cleaned_data.get('code')
        if not code:
            raise ValidationError("Utility code cannot be empty.")

        # Check for other utilities with the same code, ignoring case.
        qs = UtilityModel.objects.filter(code__iexact=code)

        # If we are in "update" mode, exclude the current instance from the check.
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("A utility with this code already exists.")

        return code


class StudentSettingForm(forms.ModelForm):
    """
    Form for managing the singleton Student & Parent settings.
    """

    class Meta:
        model = StudentSettingModel
        fields = [
            'auto_generate_student_id', 'student_prefix',
            'auto_generate_parent_id', 'parent_prefix'
        ]
        widgets = {
            'auto_generate_student_id': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'student_prefix': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '10'}),
            'auto_generate_parent_id': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'parent_prefix': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '10'}),
        }

    def clean_student_prefix(self):
        prefix = self.cleaned_data.get('student_prefix')
        if prefix:
            prefix = prefix.upper().strip()
            if not re.match(r'^[A-Z0-9]+$', prefix):
                raise ValidationError("Student prefix must contain only letters and numbers.")
            if len(prefix) < 2:
                raise ValidationError("Student prefix must be at least 2 characters long.")
        return prefix

    def clean_parent_prefix(self):
        prefix = self.cleaned_data.get('parent_prefix')
        if prefix:
            prefix = prefix.upper().strip()
            if not re.match(r'^[A-Z0-9]+$', prefix):
                raise ValidationError("Parent prefix must contain only letters and numbers.")
            if len(prefix) < 2:
                raise ValidationError("Parent prefix must be at least 2 characters long.")
        return prefix


class ParentForm(forms.ModelForm):
    """
    Form for creating and updating Parent records with robust validation.
    """

    class Meta:
        model = ParentModel
        fields = [
            'first_name', 'last_name', 'email', 'mobile', 'occupation', 'residential_address'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'mobile': forms.TextInput(attrs={'class': 'form-control'}),
            'occupation': forms.TextInput(attrs={'class': 'form-control'}),
            'residential_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name')
        if not first_name:
            raise ValidationError("First name is required.")
        return first_name.strip().title()

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name')
        if not last_name:
            raise ValidationError("Last name is required.")
        return last_name.strip().title()

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            return

        email = email.lower().strip()
        qs = ParentModel.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("A parent with this email already exists.")
        return email

    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if not mobile:
            return

        mobile = re.sub(r'[^\d+]', '', mobile)
        if not re.match(r'^(\+234|0)[789]\d{9}$', mobile):
            raise ValidationError("Please enter a valid Nigerian mobile number.")

        qs = ParentModel.objects.filter(mobile=mobile)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("This mobile number is already registered to another parent.")
        return mobile


class StudentForm(forms.ModelForm):
    utilities = forms.ModelMultipleChoiceField(
        queryset=StudentModel.utilities.field.related_model.objects.all(),
        widget=CheckboxSelectMultiple,
        required=False,  # Allow students to have no utilities
        label="Subscribed Utilities"
    )

    class Meta:
        model = StudentModel
        fields = [
            'first_name', 'last_name', 'gender', 'image',
            'parent', 'student_class', 'class_section', 'utilities', 'status'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-control select2'}),
            'student_class': forms.Select(attrs={'class': 'form-control'}),
            'class_section': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        # Pull out the user (if passed)
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        # --- Parent dropdown setup ---
        self.fields['parent'].queryset = ParentModel.objects.all().order_by('first_name', 'last_name')
        self.fields['parent'].empty_label = "Select a Parent/Guardian"

        # --- Default class querysets ---
        all_classes = ClassesModel.objects.all().order_by('name')
        all_sections = ClassSectionModel.objects.all().order_by('name')

        # --- Determine filtering rules ---
        if (user and user.has_perm('student.add_studentmodel')) or user.is_superuser:
            # Full access: show all classes and sections
            self.fields['student_class'].queryset = all_classes
            self.fields['class_section'].queryset = all_sections
        else:
            try:
                staff = user.staff_profile.staff

                # Classes where this teacher is form teacher
                assigned_infos = ClassSectionInfoModel.objects.filter(form_teacher=staff)
                assigned_class_ids = assigned_infos.values_list('student_class_id', flat=True)
                assigned_section_ids = assigned_infos.values_list('section_id', flat=True)

                # Limit visible classes and sections
                self.fields['student_class'].queryset = all_classes.filter(id__in=assigned_class_ids)
                self.fields['class_section'].queryset = all_sections.filter(id__in=assigned_section_ids)

            except Exception:
                self.fields['student_class'].queryset = ClassesModel.objects.none()
                self.fields['class_section'].queryset = ClassSectionModel.objects.none()

        # --- Always include currently assigned class/section during edit ---
        if self.instance and self.instance.pk:
            current_class = self.instance.student_class
            current_section = self.instance.class_section
            if current_class:
                self.fields['student_class'].queryset = (
                        self.fields['student_class'].queryset | ClassesModel.objects.filter(pk=current_class.pk)
                ).distinct()
            if current_section:
                self.fields['class_section'].queryset = (
                        self.fields['class_section'].queryset | ClassSectionModel.objects.filter(pk=current_section.pk)
                ).distinct()

            # Lock parent field during edit
            self.fields['parent'].disabled = True
            self.fields['parent'].initial = self.instance.parent

        # --- Empty labels ---
        self.fields['student_class'].empty_label = "Select a Class"
        self.fields['class_section'].empty_label = "Select a Class Section"


class ParentStudentUploadForm(forms.Form):
    """Form for uploading parent and student Excel files together."""

    parent_file = forms.FileField(
        label='Parent Excel File',
        help_text='Upload the Excel file containing parent information',
        widget=forms.FileInput(attrs={
            'accept': '.xlsx,.xls',
            'class': 'form-control'
        })
    )

    student_file = forms.FileField(
        label='Student Excel File',
        help_text='Upload the Excel file containing student information',
        widget=forms.FileInput(attrs={
            'accept': '.xlsx,.xls',
            'class': 'form-control'
        })
    )

    def clean_parent_file(self):
        file = self.cleaned_data.get('parent_file')
        if file:
            if not file.name.endswith(('.xlsx', '.xls')):
                raise forms.ValidationError('Only Excel files (.xlsx, .xls) are allowed.')
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('File size must not exceed 10MB.')
        return file

    def clean_student_file(self):
        file = self.cleaned_data.get('student_file')
        if file:
            if not file.name.endswith(('.xlsx', '.xls')):
                raise forms.ValidationError('Only Excel files (.xlsx, .xls) are allowed.')
            if file.size > 10 * 1024 * 1024:
                raise forms.ValidationError('File size must not exceed 10MB.')
        return file