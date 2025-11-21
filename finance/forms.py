import re
from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Sum, Q
from django.forms import inlineformset_factory, CheckboxSelectMultiple

from admin_site.models import TermModel, ClassesModel, SessionModel, SchoolSettingModel, ClassSectionModel
from finance.models import FinanceSettingModel, SupplierPaymentModel, PurchaseAdvancePaymentModel, FeeModel, \
    FeeGroupModel, FeeMasterModel, InvoiceGenerationJob, FeePaymentModel, ExpenseCategoryModel, ExpenseModel, \
    IncomeCategoryModel, IncomeModel, TermlyFeeAmountModel, StaffBankDetail, SalaryStructure, SalaryAdvance, \
    SalaryRecord, StudentFundingModel, SchoolBankDetail, StaffLoanRepayment, StaffLoan, StaffFundingModel, \
    DiscountModel, DiscountApplicationModel, StudentDiscountModel, InvoiceModel
from human_resource.models import StaffModel
from inventory.models import PurchaseOrderModel
from student.models import StudentModel

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
        fields = ['name', 'code', 'occurrence', 'payment_term', 'description', 'required_utility',
            'parent_bound']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'code': forms.TextInput(attrs={'class': 'form-control'}),
            'occurrence': forms.Select(attrs={'class': 'form-select'}),
            'payment_term': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'required_utility': forms.Select(attrs={'class': 'form-select'}),
            'parent_bound': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
        fields = ['payment_mode', 'currency', 'date', 'reference', 'description', 'notes', 'bank_account']
        # --- END OF FIX ---

        widgets = {
            # We REMOVED the 'amount' widget
            'bank_account': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'payment_mode': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'currency': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm'}),
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
    currency = forms.ChoiceField(
        choices=FeePaymentModel.Currency.choices,
        widget=forms.Select(attrs={'class': 'form-select', 'value':'naira'})
    )
    date = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    reference = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    description = forms.CharField(
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
    # Expose receipt as a FileField so we can validate size
    receipt = forms.FileField(required=False, validators=[validate_file_size])

    # Line items as a hidden JSON field (will be populated via JavaScript)
    line_items_json = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = ExpenseModel
        fields = [
            "category", "amount", "expense_date",
            "payment_method", "currency", "bank_account", "reference", "name",
            "description", "receipt", "notes",
            "vote_and_subhead",
            "prepared_by", "authorised_by", "collected_by",
            "cheque_number", "bank_name", "cheque_by", "cheque_prepared_date", "cheque_signed_date",
            "session", "term",
        ]
        # Note: line_items excluded - handled via line_items_json hidden field
        widgets = {
            "category": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "0.01",
                "min": "0.01",
                "id": "id_amount"
            }),
            "expense_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "payment_method": forms.Select(attrs={"class": "form-control"}),
            "currency": forms.Select(attrs={"class": "form-control"}),
            "bank_account": forms.Select(attrs={"class": "form-control"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "vote_and_subhead": forms.TextInput(attrs={"class": "form-control"}),
            "session": forms.Select(attrs={"class": "form-control"}),
            "term": forms.Select(attrs={"class": "form-control"}),

            # Staff fields with Select2
            "prepared_by": forms.Select(attrs={"class": "form-control select2-staff"}),
            "authorised_by": forms.Select(attrs={"class": "form-control select2-staff"}),
            "collected_by": forms.Select(attrs={"class": "form-control select2-staff"}),

            # Cheque fields
            "cheque_number": forms.TextInput(attrs={"class": "form-control"}),
            "bank_name": forms.TextInput(attrs={"class": "form-control"}),
            "cheque_by": forms.TextInput(attrs={"class": "form-control"}),
            "cheque_prepared_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "cheque_signed_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only categories that are active
        self.fields["category"].queryset = ExpenseCategoryModel.objects.filter(
            is_active=True
        ).order_by("name")

        # Staff queryset - only active staff
        active_staff = StaffModel.objects.filter(status='active').order_by('first_name', 'last_name')
        self.fields["prepared_by"].queryset = active_staff
        self.fields["authorised_by"].queryset = active_staff
        self.fields["collected_by"].queryset = active_staff

        # Make staff fields not required
        self.fields["prepared_by"].required = False
        self.fields["authorised_by"].required = False
        self.fields["collected_by"].required = False

        # Set defaults from SchoolSettingModel when available
        setting = get_current_setting()
        if setting:
            if not self.initial.get("session") and hasattr(setting, "session"):
                self.initial["session"] = setting.session
            if not self.initial.get("term") and hasattr(setting, "term"):
                self.initial["term"] = setting.term

        # Populate line_items_json from instance if editing
        if self.instance and self.instance.pk and self.instance.line_items:
            import json
            self.fields['line_items_json'].initial = json.dumps(self.instance.line_items)

    def clean_amount(self):
        amount = self.cleaned_data.get("amount")
        line_items_json = self.cleaned_data.get("line_items_json")

        # If line items exist, amount should be calculated from them
        if line_items_json:
            try:
                import json
                line_items = json.loads(line_items_json)
                if line_items and len(line_items) > 0:
                    # Amount will be calculated in save(), so we allow any value here
                    return amount
            except:
                pass

        # Standard validation if no line items
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
            # Simple character check
            if not re.match(r'^[\w\s\-\/&,]+$', pm):
                raise ValidationError("Payment method contains invalid characters.")
        return pm

    def clean_line_items_json(self):
        """Validate and parse line items JSON"""
        line_items_json = self.cleaned_data.get("line_items_json")
        if not line_items_json:
            return []

        try:
            import json
            # Check if it's already a list/dict or needs parsing
            if isinstance(line_items_json, str):
                line_items = json.loads(line_items_json)
            else:
                line_items = line_items_json

            # Validate structure
            if not isinstance(line_items, list):
                raise ValidationError("Invalid line items format.")

            for item in line_items:
                if not isinstance(item, dict):
                    raise ValidationError("Invalid line item structure.")
                if 'particular' not in item or 'amount' not in item:
                    raise ValidationError("Each line item must have 'particular' and 'amount'.")

                # Validate amount
                try:
                    Decimal(item['amount'])
                except:
                    raise ValidationError(f"Invalid amount in line item: {item.get('particular', '')}")

            return line_items
        except json.JSONDecodeError:
            raise ValidationError("Invalid JSON format for line items.")
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Error processing line items: {str(e)}")

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Get the cleaned line items (already validated and parsed in clean_line_items_json)
        parsed_items = self.cleaned_data.get('line_items_json', [])

        instance.line_items = parsed_items

        # Recalculate amount from line items if they exist
        if parsed_items and len(parsed_items) > 0:
            from decimal import Decimal
            total = sum(Decimal(item.get('amount', 0)) for item in parsed_items)
            instance.amount = total

        if commit:
            instance.save()
        return instance

    
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


class DiscountForm(forms.ModelForm):
    """Form for DiscountModel blueprint using the modal interface."""

    # Explicitly define M2M fields using CheckboxSelectMultiple widget
    applicable_fees = forms.ModelMultipleChoiceField(
        queryset=FeeModel.objects.all().order_by('name'),
        widget=CheckboxSelectMultiple,
        required=False,
        label="Applicable Fee Types"
    )
    applicable_classes = forms.ModelMultipleChoiceField(
        queryset=ClassesModel.objects.all().order_by('name'),
        widget=CheckboxSelectMultiple,
        required=False,
        label="Applicable Classes"
    )

    class Meta:
        model = DiscountModel
        fields = [
            'title', 'discount_type', 'amount', 'occurrence',
            'applicable_fees', 'applicable_classes'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'discount_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'occurrence': forms.Select(attrs={'class': 'form-select'}),
            # Note: applicable_fees and applicable_classes are handled above.
        }


class DiscountApplicationForm(forms.ModelForm):
    """Form for DiscountApplicationModel, locking the rate and type for a term."""

    class Meta:
        model = DiscountApplicationModel
        fields = [
            'discount', 'session', 'term',
            'discount_type', 'discount_amount'
        ]
        widgets = {
            # Add unique IDs for JavaScript targeting
            'discount': forms.Select(attrs={'class': 'form-select', 'id': 'id_app_discount'}),
            'session': forms.Select(attrs={'class': 'form-select'}),
            'term': forms.Select(attrs={'class': 'form-select'}),
            'discount_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_app_discount_type'}),
            'discount_amount': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'id': 'id_app_discount_amount'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. Set default session and term from SchoolSettingModel
        try:
            # Assumes SchoolSettingModel is a singleton (has only one record)
            settings = SchoolSettingModel.objects.get()
            if settings.session:
                self.fields['session'].initial = settings.session.pk
            if settings.term:
                self.fields['term'].initial = settings.term.pk
        except SchoolSettingModel.DoesNotExist:
            pass  # No settings found, so no defaults
        except SchoolSettingModel.MultipleObjectsReturned:
            pass  # Should not happen

        # 2. Set 'discount_type' to disabled (it will be autofilled by JS)
        # The model's save() method handles setting the type, so disabling
        # it here is purely for the UI.
        self.fields['discount_type'].readonly = True
        self.fields['discount_amount'].readonly = True

        # Order the FK fields
        self.fields['discount'].queryset = DiscountModel.objects.all().order_by('title')
        self.fields['session'].queryset = SessionModel.objects.all().order_by('-id')
        self.fields['term'].queryset = TermModel.objects.all().order_by('order')

        # Set optional status for session/term
        self.fields['session'].required = False
        self.fields['term'].required = False

        # If editing an existing object, lock the discount dropdown
        if self.instance.pk:
            self.fields['discount'].disabled = True


class StudentDiscountAssignForm(forms.Form):
    discount_application = forms.ModelChoiceField(
        queryset=DiscountApplicationModel.objects.none(),
        label="Select Discount",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        student = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)

        # Show available discount applications
        school_setting = SchoolSettingModel.objects.first()

        queryset = DiscountApplicationModel.objects.filter(
            Q(session=school_setting.session, term=school_setting.term) |
            Q(session__isnull=True, term__isnull=True)
        ).select_related('discount')

        # Filter to show only discounts applicable to student's class (if student provided)
        if student and student.student_class:
            # Show discounts that either have no class restriction OR include student's class
            queryset = queryset.filter(
                Q(discount__applicable_classes__isnull=True) |
                Q(discount__applicable_classes=student.student_class)
            ).distinct()

        self.fields['discount_application'].queryset = queryset

        self.fields['discount_application'].label_from_instance = lambda obj: \
            f"{obj.discount.title} - {obj.discount_amount}{'%' if obj.discount_type == 'percentage' else ' (Fixed)'}"