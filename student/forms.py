import re
from django import forms
from django.core.exceptions import ValidationError
from admin_site.models import ClassesModel, ClassSectionModel
from .models import StudentModel, ParentModel, StudentSettingModel


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
    """
    Form for registering a new student and assigning them to a parent and class.
    """

    class Meta:
        model = StudentModel
        fields = [
            'first_name', 'last_name', 'gender', 'image',
            'parent', 'student_class', 'class_section', 'status'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'parent': forms.Select(attrs={'class': 'form-control select2'}),  # select2 class for better UI
            'student_class': forms.Select(attrs={'class': 'form-control'}),
            'class_section': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set up querysets and empty labels for dropdowns
        self.fields['parent'].queryset = ParentModel.objects.all().order_by('first_name', 'last_name')
        self.fields['parent'].empty_label = "Select a Parent/Guardian"

        self.fields['student_class'].queryset = ClassesModel.objects.all().order_by('name')
        self.fields['student_class'].empty_label = "Select a Class"

        self.fields['class_section'].queryset = ClassSectionModel.objects.all().order_by('name')
        self.fields['class_section'].empty_label = "Select a Class Section"

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

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            if image.size > 2 * 1024 * 1024:
                raise ValidationError("Image file size cannot exceed 2MB.")
            allowed_types = ['image/jpeg', 'image/png']
            if image.content_type not in allowed_types:
                raise ValidationError("Please upload a valid image file (JPEG, PNG).")
        return image


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