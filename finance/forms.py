import re
from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Sum
from django.forms import inlineformset_factory

from admin_site.models import TermModel, ClassesModel, SessionModel, SchoolSettingModel, ClassSectionModel
from finance.models import FinanceSettingModel, SupplierPaymentModel, PurchaseAdvancePaymentModel, FeeModel, \
    FeeGroupModel, FeeMasterModel, InvoiceGenerationJob, FeePaymentModel, ExpenseCategoryModel, ExpenseModel, \
    IncomeCategoryModel, IncomeModel, TermlyFeeAmountModel, StaffBankDetail, SalaryStructure, SalaryAdvance, \
    SalaryRecord, StudentFundingModel, SchoolBankDetail, StaffLoanRepayment, StaffLoan, StaffFundingModel
from human_resource.models import StaffModel
from inventory.models import PurchaseOrderModel


# Helpers
MAX_AMOUNT = Decimal('999999999.99')
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5 MB - adjust as needed


def validate_file_size(f):
    if not f:
        return
    if getattr(f, 'size', 0) > MAX_UPLOAD_SIZE:
        raise ValidationError(f"File too large. Max size is {MAX_UPLOAD_SIZE // (1024*1024)}MB.")


def get_current_setting():
    return SchoolSettingModel.objects.first()


def normalize_whitespace(s: str) -> str:
    return ' '.join(s.strip().split())


class FinanceSettingForm(forms.ModelForm):
    """
    A form for creating and updating the singleton FinanceSettingModel.
    """
    class Meta:
        model = FinanceSettingModel
        # We only want the user to edit these specific fields.
        # The auditing fields will be handled automatically in the view.
        fields = ['allow_partial_payments', 'send_payment_receipt_email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # This loop applies modern Bootstrap styling to the form fields.
        # It makes checkboxes look like proper toggles/checks.
        for field_name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'form-check-input'
            else:
                field.widget.attrs['class'] = 'form-control'


class SupplierPaymentForm(forms.ModelForm):
    """Form for adding a new payment to a specific Purchase Order."""
    class Meta:
        model = SupplierPaymentModel
        # We don't need 'supplier' or 'purchase_orders' in the form,
        # as they will be set automatically in the view.
        fields = ['amount', 'payment_date', 'payment_method', 'reference', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control form-control-sm'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'reference': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        # We expect 'purchase_order' to be passed from the view.
        self.purchase_order = kwargs.pop('purchase_order', None)
        super().__init__(*args, **kwargs)

        if self.purchase_order:
            balance = self.purchase_order.balance
            # Set HTML5 max attribute for instant browser validation.
            self.fields['amount'].widget.attrs['max'] = balance
            self.fields['amount'].widget.attrs['placeholder'] = f"Max: {balance:,.2f}"
            self.fields['amount'].help_text = f"The current balance due is ₦{balance:,.2f}."

    def clean_amount(self):
        """
        Server-side validation to ensure the payment amount does not
        exceed the outstanding balance of the purchase order.
        """
        amount = self.cleaned_data.get('amount')
        if self.purchase_order and amount:
            # Using a small tolerance for floating point comparisons
            if amount > self.purchase_order.balance + Decimal('0.01'):
                raise ValidationError(
                    f"Payment cannot exceed the outstanding balance of ₦{self.purchase_order.balance:,.2f}."
                )
        return amount


class PurchaseAdvancePaymentForm(forms.ModelForm):
    class Meta:
        model = PurchaseAdvancePaymentModel
        fields = ['amount', 'payment_date', 'payment_method', 'reference', 'notes']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Payment reference...'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes...'}),
        }

    def __init__(self, *args, **kwargs):
        self.advance = kwargs.pop('advance', None)
        super().__init__(*args, **kwargs)

        if self.advance:
            max_payable = self.advance.approved_amount - self.advance.disbursed_amount
            self.fields['amount'].widget.attrs['max'] = float(max_payable)
            self.fields['amount'].help_text = f"Maximum payable: ₦{max_payable:,.2f}"

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if self.advance:
            max_payable = self.advance.approved_amount - self.advance.disbursed_amount
            if amount > max_payable:
                raise forms.ValidationError(f"Amount cannot exceed ₦{max_payable:,.2f}")
        return amount


class FeeForm(forms.ModelForm):
    """Form for FeeModel using the modal interface."""

    class Meta:
        model = FeeModel
        fields = ['name', 'code', 'occurrence', 'payment_term', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'occurrence': forms.Select(attrs={'class': 'form-select'}),
            'payment_term': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment_term'].queryset = TermModel.objects.all().order_by('order')
        self.fields['payment_term'].required = False


class FeeGroupForm(forms.ModelForm):
    """Form for FeeGroupModel using the modal interface."""

    class Meta:
        model = FeeGroupModel
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class FeeMasterCreateForm(forms.ModelForm):
    """
    Form for creating the FeeMasterModel header. This defines the 'what' and 'who'.
    """
    student_classes = forms.ModelMultipleChoiceField(
        queryset=ClassesModel.objects.all().order_by('name'),
        widget=forms.CheckboxSelectMultiple,
        required=True
    )
    class_sections = forms.ModelMultipleChoiceField(
        queryset=ClassSectionModel.objects.all().order_by('name'),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = FeeMasterModel
        fields = ['group', 'fee', 'student_classes', 'class_sections']
        widgets = {
            'group': forms.Select(attrs={'class': 'form-select'}),
            'fee': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].queryset = FeeGroupModel.objects.all().order_by('name')
        self.fields['fee'].queryset = FeeModel.objects.all().order_by('name')


# This FormSet is the key to managing multiple termly amounts on the detail page.
# Alternative approach - Custom FormSet (if the above doesn't work)
class TermlyFeeAmountFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        self.relevant_terms = kwargs.pop('relevant_terms', None)
        super().__init__(*args, **kwargs)

    def get_queryset(self):
        if not hasattr(self, '_queryset'):
            qs = super().get_queryset()
            if self.relevant_terms:
                qs = qs.filter(term__in=self.relevant_terms)
            self._queryset = qs
        return self._queryset


# Updated FormSet factory
TermlyFeeAmountFormSet = inlineformset_factory(
    FeeMasterModel,
    TermlyFeeAmountModel,
    fields=('term', 'amount'),
    extra=0,
    can_delete=False,
    formset=TermlyFeeAmountFormSet,  # Use custom formset class
    widgets={
        'amount': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.01'}),
        'term': forms.HiddenInput(),
    }
)


class InvoiceGenerationForm(forms.ModelForm):
    """Form for the 'Generate Invoices' page to start the background task."""

    class Meta:
        model = InvoiceGenerationJob
        fields = ['session', 'term', 'classes_to_invoice']
        widgets = {
            'session': forms.Select(attrs={'class': 'form-select'}),
            'term': forms.Select(attrs={'class': 'form-select'}),
            'classes_to_invoice': forms.CheckboxSelectMultiple,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['session'].queryset = SessionModel.objects.all().order_by('-start_year')
        self.fields['term'].queryset = TermModel.objects.all().order_by('order')
        self.fields['classes_to_invoice'].queryset = ClassesModel.objects.all().order_by('name')


class FeePaymentForm(forms.ModelForm):
    """
    Form for validating the PAYMENT DETAILS of a transaction.
    The amount is calculated by the view, not this form.
    """

    class Meta:
        model = FeePaymentModel

        # --- THIS IS THE FIX ---
        # We REMOVED 'amount' from this list.
        fields = ['payment_mode', 'date', 'reference', 'notes', 'bank_account']
        # --- END OF FIX ---

        widgets = {
            # We REMOVED the 'amount' widget
            'bank_account': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'payment_mode': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'notes': forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 2}),
        }


class BulkPaymentForm(forms.Form):
    """A simple form for accepting a single bulk payment amount."""
    amount = forms.DecimalField(
        label="Total Amount to Pay",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    payment_mode = forms.ChoiceField(
        choices=FeePaymentModel.PaymentMode.choices,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )


# -------------------- EXPENSE CATEGORY FORM --------------------

class ExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = ExpenseCategoryModel
        # include only model fields you are likely to edit by admin/user
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Category name"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            raise ValidationError("Category name is required.")
        name = normalize_whitespace(name)
        if len(name) < 2:
            raise ValidationError("Category name must be at least 2 characters long.")
        # allow unicode letters/numbers, spaces, hyphen and ampersand
        for ch in name:
            if not (ch.isalnum() or ch in " -&"):
                raise ValidationError("Category name contains invalid characters.")
        qs = ExpenseCategoryModel.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Category '{name}' already exists.")
        return name


# -------------------- EXPENSE FORM --------------------

class ExpenseForm(forms.ModelForm):
    # expose receipt as a FileField so we can validate size
    receipt = forms.FileField(required=False, validators=[validate_file_size])

    class Meta:
        model = ExpenseModel
        fields = [
            "category", "amount", "expense_date",
            "payment_method", "reference", "receipt", "notes",
            "session", "term",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "expense_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "payment_method": forms.TextInput(attrs={"class": "form-control", "placeholder": "cash, card, transfer"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "session": forms.Select(attrs={"class": "form-control"}),
            "term": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # only categories that are active
        self.fields["category"].queryset = ExpenseCategoryModel.objects.filter(is_active=True).order_by("name")

        # set defaults from SchoolSettingModel when available
        setting = get_current_setting()
        if setting:
            if not self.initial.get("session") and hasattr(setting, "session"):
                self.initial["session"] = setting.session
            if not self.initial.get("term") and hasattr(setting, "term"):
                self.initial["term"] = setting.term

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            raise ValidationError("Amount is required.")
        try:
            amount = Decimal(amount)
        except Exception:
            raise ValidationError("Invalid amount.")
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0.")
        if amount > MAX_AMOUNT:
            raise ValidationError("Amount is too large.")
        return amount

    def clean_expense_date(self):
        expense_date = self.cleaned_data.get("expense_date")
        if not expense_date:
            raise ValidationError("Expense date is required.")
        if expense_date > date.today():
            raise ValidationError("Expense date cannot be in the future.")
        if (date.today() - expense_date).days > 365:
            raise ValidationError("Expense date cannot be more than 1 year ago.")
        return expense_date

    def clean_payment_method(self):
        pm = self.cleaned_data.get("payment_method")
        if pm:
            pm = pm.strip()
            if len(pm) > 50:
                raise ValidationError("Payment method is too long.")
            # simple character check
            if not re.match(r'^[\w\s\-\/&,]+$', pm):
                raise ValidationError("Payment method contains invalid characters.")
        return pm


# -------------------- INCOME CATEGORY FORM --------------------

class IncomeCategoryForm(forms.ModelForm):
    class Meta:
        model = IncomeCategoryModel
        fields = ["name", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Category name"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name")
        if not name:
            raise ValidationError("Category name is required.")
        name = normalize_whitespace(name)
        if len(name) < 2:
            raise ValidationError("Category name must be at least 2 characters long.")
        for ch in name:
            if not (ch.isalnum() or ch in " -&"):
                raise ValidationError("Category name contains invalid characters.")
        qs = IncomeCategoryModel.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"Category '{name}' already exists.")
        return name


# -------------------- INCOME FORM --------------------

class IncomeForm(forms.ModelForm):
    receipt = forms.FileField(required=False, validators=[validate_file_size])

    class Meta:
        model = IncomeModel
        fields = [
            "category", "description", "amount", "income_date",
            "source", "reference", "receipt", "notes",
            "session", "term",
        ]
        widgets = {
            "category": forms.Select(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "income_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "source": forms.TextInput(attrs={"class": "form-control"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "session": forms.Select(attrs={"class": "form-control"}),
            "term": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = IncomeCategoryModel.objects.filter(is_active=True).order_by("name")
        setting = get_current_setting()
        if setting:
            if not self.initial.get("session") and hasattr(setting, "session"):
                self.initial["session"] = setting.session
            if not self.initial.get("term") and hasattr(setting, "term"):
                self.initial["term"] = setting.term

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        if amount is None:
            raise ValidationError("Amount is required.")
        try:
            amount = Decimal(amount)
        except Exception:
            raise ValidationError("Invalid amount.")
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0.")
        if amount > MAX_AMOUNT:
            raise ValidationError("Amount is too large.")
        return amount

    def clean_income_date(self):
        income_date = self.cleaned_data.get("income_date")
        if not income_date:
            raise ValidationError("Income date is required.")
        if income_date > date.today():
            raise ValidationError("Income date cannot be in the future.")
        if (date.today() - income_date).days > 365:
            raise ValidationError("Income date cannot be more than 1 year ago.")
        return income_date


# ===================================================================
# Staff Bank Detail Form
# ===================================================================
class StaffBankDetailForm(forms.ModelForm):
    """Form for creating and updating staff bank details."""

    class Meta:
        model = StaffBankDetail
        fields = ['staff', 'bank_name', 'account_number', 'account_name', 'is_active']
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'account_name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only allow selecting active staff who don't already have bank details
        if not self.instance.pk:
            self.fields['staff'].queryset = StaffModel.objects.filter(bank_details__isnull=True)
        else:
            self.fields['staff'].queryset = StaffModel.objects.filter(pk=self.instance.staff.pk)
            self.fields['staff'].disabled = True

    def clean_account_number(self):
        account_number = self.cleaned_data.get('account_number')
        if not account_number:
            raise ValidationError("Account number is required.")
        account_number = re.sub(r'[^\d]', '', account_number)
        if not (10 <= len(account_number) <= 20):
            raise ValidationError("Account number must be between 10 and 20 digits.")
        return account_number


# ===================================================================
# School Bank Detail Form
# ===================================================================
class SchoolBankDetailForm(forms.ModelForm):
    """Form for creating and updating staff bank details."""

    class Meta:
        model = SchoolBankDetail
        fields = ['bank_name', 'account_number', 'account_name', 'is_active']
        widgets = {
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'account_name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_account_number(self):
        account_number = self.cleaned_data.get('account_number')
        if not account_number:
            raise ValidationError("Account number is required.")
        account_number = re.sub(r'[^\d]', '', account_number)
        if not (10 <= len(account_number) <= 20):
            raise ValidationError("Account number must be between 10 and 20 digits.")
        return account_number


# ===================================================================
# Salary Structure Form
# ===================================================================
class SalaryStructureForm(forms.ModelForm):
    """Form for defining a staff member's salary structure."""

    class Meta:
        model = SalaryStructure
        fields = [
            'staff', 'basic_salary', 'housing_allowance', 'transport_allowance',
            'medical_allowance', 'other_allowances', 'tax_rate', 'pension_rate',
            'effective_from', 'is_active'
        ]
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'basic_salary': forms.NumberInput(attrs={'class': 'form-control'}),
            'housing_allowance': forms.NumberInput(attrs={'class': 'form-control'}),
            'transport_allowance': forms.NumberInput(attrs={'class': 'form-control'}),
            'medical_allowance': forms.NumberInput(attrs={'class': 'form-control'}),
            'other_allowances': forms.NumberInput(attrs={'class': 'form-control'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 7.5'}),
            'pension_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 8.0'}),
            'effective_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only allow selecting active staff who don't already have a salary structure
        if not self.instance.pk:
            self.fields['staff'].queryset = StaffModel.objects.filter(salary_structure__isnull=True)
        else:
            self.fields['staff'].queryset = StaffModel.objects.filter(pk=self.instance.staff.pk)
            self.fields['staff'].disabled = True


# ===================================================================
# Salary Advance Form (New)
# ===================================================================
# finance/forms.py

class SalaryAdvanceForm(forms.ModelForm):
    """Form for staff to request a salary advance with validation."""

    class Meta:
        model = SalaryAdvance
        fields = ['staff', 'amount', 'reason', 'request_date']
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'request_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # It's good practice to prefetch related user data for the dropdown
        self.fields['staff'].queryset = StaffModel.objects.select_related(
            'staff_profile__user'
        ).order_by('staff_profile__user__first_name', 'staff_profile__user__last_name')

    def clean(self):
        """
        Adds validation for salary structure existence and monthly advance limits.
        """
        cleaned_data = super().clean()
        staff = cleaned_data.get('staff')
        amount = cleaned_data.get('amount')
        request_date = cleaned_data.get('request_date')

        # First, ensure the required fields for validation are present.
        if not all([staff, amount, request_date]):
            # If basic field validation (e.g., required=True) failed, stop here.
            return cleaned_data

        # Basic check that was in your clean_amount()
        if amount <= 0:
            self.add_error('amount', "Advance amount must be a positive number.")
            # No need to proceed if the amount is invalid
            return cleaned_data

        # === Main Validation Logic ===

        # 1. Staff must have an active salary structure.
        try:
            structure = staff.salary_structure
            if not structure.is_active:
                raise ValidationError(
                    "This staff member does not have an active salary structure and cannot request an advance.")
        except StaffModel.salary_structure.RelatedObjectDoesNotExist:
            raise ValidationError("This staff member's salary profile is not set up. Cannot request an advance.")

        # 2. Requested amount cannot exceed the monthly limit.
        net_salary = structure.net_salary

        # Sum all non-rejected/completed advances for the same month.
        advances_this_month = SalaryAdvance.objects.filter(
            staff=staff,
            request_date__year=request_date.year,
            request_date__month=request_date.month,
            status__in=[SalaryAdvance.Status.PENDING, SalaryAdvance.Status.APPROVED, SalaryAdvance.Status.DISBURSED]
        )

        # If editing an existing advance, exclude it from the calculation.
        if self.instance and self.instance.pk:
            advances_this_month = advances_this_month.exclude(pk=self.instance.pk)

        total_already_taken = advances_this_month.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        max_allowed = net_salary - total_already_taken

        if amount > max_allowed:
            # This raises a non-field error that will appear at the top of the form.
            raise ValidationError(
                f"Amount exceeds the limit for {request_date.strftime('%B')}. "
                f"Net Salary: ₦{net_salary:,.2f}, "
                f"Already Taken: ₦{total_already_taken:,.2f}. "
                f"You can request up to ₦{max_allowed:,.2f}."
            )

        return cleaned_data


# finance/forms.py

class StaffLoanForm(forms.ModelForm):
    """Form for staff to request a loan."""
    class Meta:
        model = StaffLoan
        fields = ['staff', 'amount', 'reason', 'repayment_plan', 'request_date']
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'repayment_plan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'request_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['staff'].queryset = StaffModel.objects.select_related(
            'staff_profile__user'
        ).order_by('staff_profile__user__first_name')

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if not amount or amount <= 0:
            raise ValidationError("Loan amount must be a positive number.")
        return amount


class StaffLoanRepaymentForm(forms.ModelForm):
    """Form to record a repayment for a staff loan."""
    class Meta:
        model = StaffLoanRepayment
        fields = ['amount_paid', 'payment_date']
        widgets = {
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Enter amount paid'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


# ===================================================================
# Paysheet Row Form (For interactive paysheet)
# ===================================================================
class PaysheetRowForm(forms.ModelForm):
    """
    Represents a single editable row in the interactive paysheet.
    """

    class Meta:
        model = SalaryRecord
        fields = ['bonus', 'other_deductions', 'salary_advance_deduction', 'notes', 'amount_paid']
        widgets = {
            'salary_advance_deduction': forms.NumberInput(attrs={'class': 'form-control form-control-sm editable-field'}),
            'bonus': forms.NumberInput(attrs={'class': 'form-control form-control-sm editable-field'}),
            'other_deductions': forms.NumberInput(attrs={'class': 'form-control form-control-sm editable-field'}),
            'notes': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'amount_paid': forms.NumberInput(attrs={'class': 'form-control form-control-sm editable-field'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # THIS IS THE CRITICAL LOGIC THAT SETS THE DEFAULT 'Amount Paid'
        # It checks if the database value is 0, and if so,
        # it pre-fills the form field with the net_salary.
        if self.instance and self.instance.pk:
            if self.instance.amount_paid == Decimal('0.00'):
                self.initial['amount_paid'] = self.instance.net_salary


class StudentFundingForm(forms.ModelForm):
    """Form for creating a new funding record."""
    class Meta:
        model = StudentFundingModel
        # Be explicit about the fields a user can fill
        fields = [
             'amount', 'method', 'mode',
             'proof_of_payment', 'teller_number', 'reference'
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'mode': forms.Select(attrs={'class': 'form-select'}),
            'proof_of_payment': forms.FileInput(attrs={'class': 'form-control'}),
            'teller_number': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # You can hide the student field if it's set by the URL


class StaffFundingForm(forms.ModelForm):
    """Form for creating a new funding record."""
    class Meta:
        model = StaffFundingModel
        # Be explicit about the fields a user can fill
        fields = [
             'amount', 'method', 'mode',
             'proof_of_payment', 'teller_number', 'reference'
        ]
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'mode': forms.Select(attrs={'class': 'form-select'}),
            'proof_of_payment': forms.FileInput(attrs={'class': 'form-control'}),
            'teller_number': forms.TextInput(attrs={'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # You can hide the student field if it's set by the URL
