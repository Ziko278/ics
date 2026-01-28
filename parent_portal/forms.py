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
    wallet_type = forms.ChoiceField(
        label="Wallet Type",
        required=True,
        choices=[
            ('canteen', 'Canteen Wallet'),
            ('fee', 'Fee Wallet'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
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
        fields = ['amount', 'method', 'teller_number', 'target_invoice', 'wallet_type']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Amount Paid'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'wallet_type': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        student: StudentModel = kwargs.pop('student', None)
        upload_type: str = kwargs.pop('upload_type', None)
        self.upload_type = upload_type

        super().__init__(*args, **kwargs)

        # Add wallet_type to fields Meta
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

        if upload_type == 'wallet':
            self.fields.pop('target_invoice', None)
            # Keep wallet_type field for selection

        elif upload_type == 'fee':
            # For fee payment, remove wallet_type (fee wallet is implied)
            self.fields.pop('wallet_type', None)
            self.fields['target_invoice'].queryset = unpaid_invoices
            self.fields['target_invoice'].required = True
            self.fields['target_invoice'].empty_label = None
            self.fields['target_invoice'].label = "Select Fee"
            self.fields['target_invoice'].label_from_instance = lambda \
                    obj: f"{obj.invoice_number} ({obj.session}/{obj.term.name}) - Bal: ₦{obj.balance:,.2f}"

        else:
            # Default behavior - keep both fields
            self.fields['target_invoice'].queryset = unpaid_invoices
            self.fields['target_invoice'].label_from_instance = lambda \
                    obj: f"{obj.invoice_number} ({obj.session}/{obj.term.name}) - Bal: ₦{obj.balance:,.2f}"

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")
        teller_number = cleaned_data.get("teller_number")
        proof = self.files.get('proof_of_payment')
        target_invoice = cleaned_data.get("target_invoice")
        wallet_type = cleaned_data.get("wallet_type")

        if not proof:
            self.add_error('proof_of_payment', "Proof of payment is required.")

        if self.upload_type == 'fee':
            # For fee uploads, force wallet_type to 'fee'
            cleaned_data['wallet_type'] = 'fee'

            if not target_invoice:
                self.add_error('target_invoice', 'You must select an invoice for a fee payment.')

            if 'target_invoice' in self.fields and not self.fields['target_invoice'].queryset.exists():
                self.add_error(None, "This student has no outstanding invoices available for payment.")

        if self.upload_type == 'wallet':
            if not wallet_type:
                self.add_error('wallet_type', 'You must select a wallet type.')
            cleaned_data['target_invoice'] = None

        return cleaned_data