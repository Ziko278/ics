import re
from django import forms
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from .models import StaffModel, HRSettingModel, DepartmentModel, PositionModel


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = DepartmentModel
        fields = ['name', 'code', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Department Name'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'DEPT', 'maxlength': '20'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError("Department name is required.")

        # Remove extra spaces and validate
        name = ' '.join(name.strip().split())
        if len(name) < 2:
            raise ValidationError("Department name must be at least 2 characters long.")

        # Check for special characters (allow only letters, numbers, spaces, hyphens)
        if not re.match(r'^[a-zA-Z0-9\s\-&]+$', name):
            raise ValidationError("Department name contains invalid characters.")

        # Check uniqueness (case-insensitive)
        existing = DepartmentModel.objects.filter(name__iexact=name)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise ValidationError(f"Department '{name}' already exists.")

        return name

    def clean_code(self):
        code = self.cleaned_data.get('code')
        if code:
            code = code.upper().strip()

            # Validate format
            if not re.match(r'^[A-Z0-9]+$', code):
                raise ValidationError("Department code must contain only letters and numbers.")

            if len(code) < 2 or len(code) > 20:
                raise ValidationError("Department code must be between 2 and 20 characters.")

            # Check uniqueness
            existing = DepartmentModel.objects.filter(code=code)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)

            if existing.exists():
                raise ValidationError(f"Department code '{code}' already exists.")

        return code


class PositionForm(forms.ModelForm):
    """  """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'form-control',
                'autocomplete': 'off'
            })

    class Meta:
        model = PositionModel
        fields = '__all__'
        widgets = {

        }



class StaffForm(forms.ModelForm):
    """
    Form for creating and updating Staff records with robust validation.
    """

    class Meta:
        model = StaffModel
        fields = [
            'first_name', 'last_name', 'department', 'email', 'mobile',
            'gender', 'group', 'status', 'image'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.Select(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'mobile': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'group': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate the group dropdown with available permission groups
        self.fields['group'].queryset = Group.objects.all()
        self.fields['group'].empty_label = "Select Permission Group"

    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name')
        if not first_name:
            raise ValidationError("First name is required.")

        first_name = first_name.strip().title()
        if len(first_name) < 2:
            raise ValidationError("First name must be at least 2 characters long.")
        if not re.match(r'^[a-zA-Z\s\-\']+$', first_name):
            raise ValidationError("First name contains invalid characters.")
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name')
        if not last_name:
            raise ValidationError("Last name is required.")

        last_name = last_name.strip().title()
        if len(last_name) < 2:
            raise ValidationError("Last name must be at least 2 characters long.")
        if not re.match(r'^[a-zA-Z\s\-\']+$', last_name):
            raise ValidationError("Last name contains invalid characters.")
        return last_name

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            return

        email = email.lower().strip()
        qs = StaffModel.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("A staff member with this email already exists.")
        return email

    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if not mobile:
            return

        # Standardize by removing spaces and keeping '+' if present
        mobile = re.sub(r'[^\d+]', '', mobile)

        # Validate for a typical Nigerian phone number format
        if not re.match(r'^(\+234|0)[789]\d{9}$', mobile):
            raise ValidationError("Please enter a valid Nigerian mobile number (e.g., 08012345678).")

        qs = StaffModel.objects.filter(mobile=mobile)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("This mobile number is already registered to another staff member.")
        return mobile

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image:
            # Check file size (2MB limit)
            if image.size > 2 * 1024 * 1024:
                raise ValidationError("Image file size cannot exceed 2MB.")
            # Check file type
            allowed_types = ['image/jpeg', 'image/png', 'image/gif']
            if image.content_type not in allowed_types:
                raise ValidationError("Please upload a valid image file (JPEG, PNG).")
        return image


class GroupForm(forms.ModelForm):
    """
    Form for creating and updating user permission groups.
    """

    class Meta:
        model = Group
        fields = ['name', 'permissions']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'permissions': forms.SelectMultiple(attrs={'class': 'form-control', 'size': '10'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError("Group name is required.")

        qs = Group.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("A permission group with this name already exists.")
        return name


class HRSettingForm(forms.ModelForm):
    """
    Form for managing HR settings, like Staff ID generation.
    """

    class Meta:
        model = HRSettingModel
        fields = ['auto_generate_staff_id', 'staff_prefix']
        widgets = {
            'auto_generate_staff_id': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'staff_prefix': forms.TextInput(attrs={'class': 'form-control', 'maxlength': '10'}),
        }

    def clean_staff_prefix(self):
        staff_prefix = self.cleaned_data.get('staff_prefix')
        if staff_prefix:
            staff_prefix = staff_prefix.upper().strip()
            if not re.match(r'^[A-Z0-9]+$', staff_prefix):
                raise ValidationError("Staff prefix must contain only letters and numbers.")
            if len(staff_prefix) < 2:
                raise ValidationError("Staff prefix must be at least 2 characters long.")
        return staff_prefix


class StaffUploadForm(forms.Form):
    """
    A simple form to handle the upload of the staff Excel file.
    """
    excel_file = forms.FileField(
        label="Staff Data File",
        help_text="Upload an .xlsx file with columns: first_name, last_name, gender, email, mobile, group_name.",
        widget=forms.widgets.FileInput(attrs={'class': 'form-control'})
    )

    def clean_excel_file(self):
        """
        Validates that the uploaded file is an Excel file.
        """
        file = self.cleaned_data.get('excel_file')
        if file:
            if not file.name.endswith('.xlsx'):
                raise forms.ValidationError("Invalid file type. Only .xlsx files are accepted.")
        return file


class StaffProfileUpdateForm(forms.ModelForm):
    """
    Form for staff members to update their own profile information.
    The 'group' (position) is excluded as requested.
    """
    class Meta:
        model = StaffModel
        fields = ['first_name', 'last_name', 'mobile', 'email', 'image']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'mobile': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }
