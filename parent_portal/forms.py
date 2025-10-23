# parent_portal/forms.py
from django import forms
from finance.models import StudentFundingModel, InvoiceModel  # Adjust import based on your project structure
from student.models import StudentModel


class ParentLoginForm(forms.Form):
    username = forms.CharField(max_length=150, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}), required=True)


# parent_portal/forms.py
# (Keep necessary imports: forms, InvoiceModel, StudentFundingModel, StudentModel, Decimal)

class FeeUploadForm(forms.ModelForm): # Keep inheriting for field convenience
    target_invoice = forms.ModelChoiceField(
        queryset=InvoiceModel.objects.none(),
        required=False,
        label="Link to Specific Invoice (Optional)",
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="-- General Wallet Funding --"
    )
    # Use teller_number field name consistent with StudentFundingModel for less change
    teller_number = forms.CharField(
        label="Teller Number / Transaction ID",
        required=False, # Make optional initially, check in clean method
        widget=forms.TextInput(attrs={'class':'form-control'})
    )
    proof_of_payment = forms.FileField( # Define explicitly as model doesn't have it directly
        label="Upload Proof (Image/PDF)",
        required=True, # Proof is mandatory for parent uploads
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = StudentFundingModel # Still use this for Amount, Method fields
        # Remove proof_of_payment from here if it's not in StudentFundingModel
        fields = ['amount', 'method', 'teller_number', 'target_invoice']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Amount Paid'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            # teller_number defined above
            # target_invoice defined above
        }

    def __init__(self, *args, **kwargs):
        student: StudentModel = kwargs.pop('student', None)
        super().__init__(*args, **kwargs)

        self.fields['method'].choices = [
            # Ensure these values match FeePaymentModel.PaymentMode choices if creating that
            ('bank_teller', 'Bank Teller'),
            ('bank_transfer', 'Bank Transfer'),
        ]
        # self.fields['proof_of_payment'].required = True # Set on explicit field definition

        if student:
            unpaid_invoices = InvoiceModel.objects.filter(
                student=student,
                status__in=[InvoiceModel.Status.UNPAID, InvoiceModel.Status.PARTIALLY_PAID]  # Was PARTIALLLY_PAID

                # Was PARTIALLLY_PAID # Typo corrected
            ).order_by('-session__start_year', '-term__order')
            self.fields['target_invoice'].queryset = unpaid_invoices
            self.fields['target_invoice'].label_from_instance = lambda obj: f"{obj.invoice_number} ({obj.session}/{obj.term.name}) - Bal: ₦{obj.balance:,.2f}"
        else:
             self.fields['target_invoice'].queryset = InvoiceModel.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")
        teller_number = cleaned_data.get("teller_number")
        proof = self.files.get('proof_of_payment') # Access uploaded file

        # Require teller number/ref based on method
        if method in ['bank_teller', 'bank_transfer'] and not teller_number:
            self.add_error('teller_number', "Please provide the Teller Number or Transaction ID.")

        # Ensure proof is uploaded (redundant due to required=True, but safe)
        if not proof:
             self.add_error('proof_of_payment', "Proof of payment is required.")
        # Add file size/type validation if needed here

        return cleaned_data
