# parent_portal/forms.py
from django import forms
from finance.models import StudentFundingModel, InvoiceModel  # Adjust import based on your project structure
from student.models import StudentModel


class ParentLoginForm(forms.Form):
    username = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}), required=True)


# parent_portal/forms.py
# (Keep necessary imports: forms, InvoiceModel, StudentFundingModel, StudentModel, Decimal)

class FeeUploadForm(forms.ModelForm):
    target_invoice = forms.ModelChoiceField(
        queryset=InvoiceModel.objects.none(),
        required=False,  # Base is False, override in __init__
        label="Select Fee",
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="-- General Wallet Funding --"
    )
    teller_number = forms.CharField(
        label="Teller Number / Transaction ID",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    proof_of_payment = forms.FileField(
        label="Upload Proof (Image/PDF)",
        required=True,
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = StudentFundingModel
        fields = ['amount', 'method', 'teller_number', 'target_invoice']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Amount Paid'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        student: StudentModel = kwargs.pop('student', None)
        # Get the new 'upload_type' passed from the view
        upload_type: str = kwargs.pop('upload_type', None)
        self.upload_type = upload_type  # Store for use in clean method

        super().__init__(*args, **kwargs)

        self.fields['method'].choices = [
            ('bank teller', 'Bank Teller'),
            ('bank transfer', 'Bank Transfer'),
        ]

        if student:
            unpaid_invoices = InvoiceModel.objects.filter(
                student=student,
                status__in=[InvoiceModel.Status.UNPAID, InvoiceModel.Status.PARTIALLY_PAID]
            ).order_by('-session__start_year', '-term__order')
        else:
            unpaid_invoices = InvoiceModel.objects.none()

        # Logic to modify the target_invoice field based on upload_type
        if upload_type == 'wallet':
            # For wallet funding, remove the invoice field entirely.
            # The view's form_valid will see target_invoice=None and fund the wallet.
            self.fields.pop('target_invoice', None)

        elif upload_type == 'fee':
            # For fee payment, make selecting an invoice mandatory.
            self.fields['target_invoice'].queryset = unpaid_invoices
            self.fields['target_invoice'].required = True
            self.fields['target_invoice'].empty_label = None  # Force a selection
            self.fields['target_invoice'].label = "Select Fee"
            self.fields['target_invoice'].label_from_instance = lambda \
                obj: f"{obj.invoice_number} ({obj.session}/{obj.term.name}) - Bal: ₦{obj.balance:,.2f}"

        else:
            # Default/original behavior (if type is not 'fee' or 'wallet')
            self.fields['target_invoice'].queryset = unpaid_invoices
            self.fields['target_invoice'].label_from_instance = lambda \
                obj: f"{obj.invoice_number} ({obj.session}/{obj.term.name}) - Bal: ₦{obj.balance:,.2f}"

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")
        teller_number = cleaned_data.get("teller_number")
        proof = self.files.get('proof_of_payment')
        target_invoice = cleaned_data.get("target_invoice")

        if not proof:
            self.add_error('proof_of_payment', "Proof of payment is required.")

        # Check for outstanding invoices only if in 'fee' mode
        if self.upload_type == 'fee':
            if not target_invoice:
                # This check is slightly redundant if required=True is set, but is a good safeguard
                self.add_error('target_invoice', 'You must select an invoice for a fee payment.')

            # Check if there were any invoices to select from in the first place
            if 'target_invoice' in self.fields and not self.fields['target_invoice'].queryset.exists():
                self.add_error(None, "This student has no outstanding invoices available for payment.")

        # If in 'wallet' mode, ensure target_invoice is None
        if self.upload_type == 'wallet' and target_invoice:
            # This shouldn't happen if field was popped, but good to be safe
            cleaned_data['target_invoice'] = None

        return cleaned_data
