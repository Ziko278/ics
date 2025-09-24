# from django import forms
# from .models import StudentFundingModel
# from django.core.exceptions import ValidationError
# from django.utils.translation import gettext_lazy as _
#
#
# class StudentFundingForm(forms.ModelForm):
#     """
#     A form for creating and updating StudentFundingModel instances.
#     It includes validation for payment methods and amounts.
#     """
#     class Meta:
#         model = StudentFundingModel
#         # We only include fields that a user should directly interact with.
#         # Fields like 'session', 'term', and 'created_by' are best handled
#         # automatically in the view or the model's save method.
#         fields = [
#             'student', 'amount', 'method', 'mode', 'status',
#             'proof_of_payment', 'teller_number', 'reference'
#         ]
#         widgets = {
#             'student': forms.Select(attrs={'class': 'form-control select2'}), # Suggesting select2 for better UX
#             'amount': forms.NumberInput(attrs={'placeholder': 'Enter amount paid'}),
#             'teller_number': forms.TextInput(attrs={'placeholder': 'Enter bank teller number'}),
#             'reference': forms.TextInput(attrs={'placeholder': 'Enter payment reference or ID'}),
#         }
#         labels = {
#             'proof_of_payment': _('Upload Proof of Payment'),
#         }
#
#     def __init__(self, *args, **kwargs):
#         """
#         Applies the 'form-control' class to all form fields for styling.
#         """
#         super().__init__(*args, **kwargs)
#         for field_name, field in self.fields.items():
#             # Ensure all fields have the base 'form-control' class
#             if 'class' not in field.widget.attrs:
#                 field.widget.attrs['class'] = 'form-control'
#
#     def clean_amount(self):
#         """
#         Validates that the funding amount is a positive number.
#         """
#         amount = self.cleaned_data.get('amount')
#         if amount is not None and amount <= 0:
#             raise ValidationError(_("The funding amount must be greater than zero."), code='invalid_amount')
#         return amount
#
#     def clean(self):
#         """
#         Provides cross-field validation based on the selected payment method.
#         """
#         cleaned_data = super().clean()
#         method = cleaned_data.get('method')
#         teller_number = cleaned_data.get('teller_number')
#         reference = cleaned_data.get('reference')
#         proof_of_payment = cleaned_data.get('proof_of_payment')
#
#         # Require a teller number for bank teller payments
#         if method == StudentFundingModel.PaymentMethod.BANK_TELLER and not teller_number:
#             self.add_error('teller_number', _("A teller number is required for bank teller payments."))
#
#         # Require a reference for bank transfers
#         if method == StudentFundingModel.PaymentMethod.BANK_TRANSFER and not reference:
#             self.add_error('reference', _("A transaction reference is required for bank transfers."))
#
#         # Require proof of payment for all non-cash offline methods
#         if method != StudentFundingModel.PaymentMethod.CASH and not proof_of_payment:
#              self.add_error('proof_of_payment', _("Proof of payment must be uploaded for this payment method."))
#
#         return cleaned_data
