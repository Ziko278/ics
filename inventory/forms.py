from django import forms
from django.core.exceptions import ValidationError
from django.forms import modelformset_factory

from admin_site.models import SessionModel, TermModel
from human_resource.models import StaffModel
from student.models import StudentModel
from .models import CategoryModel, SupplierModel, ItemModel, PurchaseOrderItemModel, PurchaseOrderModel, \
    StockInItemModel, StockInModel, StockOutModel, StockTransferModel, PurchaseAdvanceModel, PurchaseAdvanceItemModel, \
    SaleModel


class CategoryForm(forms.ModelForm):
    """
    Form for creating and updating inventory categories.
    """

    class Meta:
        model = CategoryModel
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Textbooks, Uniforms'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                                 'placeholder': 'Optional: A brief description of the category'}),
        }

    def clean_name(self):
        """
        Custom validation to ensure the category name is unique (case-insensitive).
        """
        name = self.cleaned_data.get('name')
        if not name:
            raise ValidationError("Category name cannot be empty.")

        # Check for other categories with the same name, ignoring case.
        qs = CategoryModel.objects.filter(name__iexact=name)

        # If we are in "update" mode, exclude the current instance from the check.
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise ValidationError("An inventory category with this name already exists.")

        return name


class SupplierForm(forms.ModelForm):
    """Form for creating and updating suppliers."""

    class Meta:
        model = SupplierModel
        fields = ['name', 'contact_person', 'phone_number', 'email', 'address', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Zenith Books Ltd'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., John Doe'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., 08012345678'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'e.g., contact@zenithbooks.com'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_name(self):
        name = self.cleaned_data.get('name').strip()
        if self.instance.pk:
            if SupplierModel.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
                raise ValidationError("A supplier with this name already exists.")
        elif SupplierModel.objects.filter(name__iexact=name).exists():
            raise ValidationError("A supplier with this name already exists.")
        return name

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        if phone_number:
            if self.instance.pk:
                if SupplierModel.objects.filter(phone_number=phone_number).exclude(pk=self.instance.pk).exists():
                    raise ValidationError("This phone number is already registered to another supplier.")
            elif SupplierModel.objects.filter(phone_number=phone_number).exists():
                raise ValidationError("This phone number is already registered to another supplier.")
        return phone_number

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            if self.instance.pk:
                if SupplierModel.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
                    raise ValidationError("This email address is already registered to another supplier.")
            elif SupplierModel.objects.filter(email__iexact=email).exists():
                raise ValidationError("This email address is already registered to another supplier.")
        return email


class ItemCreateForm(forms.ModelForm):
    """Form for creating a new inventory item, allowing initial stock entry."""

    class Meta:
        model = ItemModel
        fields = [
            'name', 'category', 'barcode', 'unit', 'location',
            'current_selling_price', 'reorder_level',
            'shop_quantity', 'store_quantity', 'is_active'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Primary School Uniform'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Scan or enter barcode'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'current_selling_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'shop_quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'store_quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = CategoryModel.objects.all().order_by('name')
        self.fields['shop_quantity'].help_text = 'Set the initial quantity available in the shop.'
        self.fields['store_quantity'].help_text = 'Set the initial quantity available in the main store.'


class ItemUpdateForm(forms.ModelForm):
    """Form for updating an existing inventory item. Stock quantities are not editable."""

    class Meta:
        model = ItemModel
        # Exclude the quantity fields from the update form
        exclude = ['shop_quantity', 'store_quantity', 'created_by']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'barcode': forms.TextInput(attrs={'class': 'form-control'}),
            'unit': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'current_selling_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'reorder_level': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = CategoryModel.objects.all().order_by('name')


class PurchaseOrderCreateForm(forms.ModelForm):
    """Form for creating the initial Purchase Order header."""

    class Meta:
        model = PurchaseOrderModel
        fields = ['supplier', 'order_date', 'expected_date', 'session', 'term', 'notes']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'order_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'expected_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'session': forms.Select(attrs={'class': 'form-select'}),
            'term': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional notes...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = SupplierModel.objects.filter(is_active=True)
        self.fields['session'].queryset = SessionModel.objects.all().order_by('-start_year')
        self.fields['term'].queryset = TermModel.objects.all().order_by('order')

        # Make session and term not required in the form, as the model's save()
        # method will auto-populate them from school settings if they are left blank.
        self.fields['session'].required = False
        self.fields['term'].required = False


class PurchaseOrderItemForm(forms.ModelForm):
    """Form for adding/editing individual line items on the PO detail page."""

    class Meta:
        model = PurchaseOrderItemModel
        fields = ['item', 'item_description', 'quantity', 'unit_cost']
        widgets = {
            'item': forms.HiddenInput(),
            'item_description': forms.TextInput(
                attrs={'class': 'form-control form-control-sm', 'autocomplete': 'off', 'placeholder': 'Item Description'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Qty'}),
            'unit_cost': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Unit Cost'}),
        }


class ManualStockInForm(forms.ModelForm):
    """Form for creating a manual Stock In batch (for non-PO entries)."""

    class Meta:
        model = StockInModel
        fields = ['source', 'supplier', 'date_received', 'location', 'notes']
        widgets = {
            'source': forms.Select(attrs={'class': 'form-select'}),
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'date_received': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = SupplierModel.objects.filter(is_active=True)
        self.fields['supplier'].required = False


class StockInFromPOForm(forms.ModelForm):
    """
    A single form within the formset for receiving items from a PO.
    The user will only input the 'quantity_received'.
    """

    class Meta:
        model = StockInItemModel
        fields = ['quantity_received']
        widgets = {
            'quantity_received': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'min': 0}),
        }


# It creates a "FormSet" to handle multiple StockInFromPOForm instances at once.
StockInFromPOFormSet = modelformset_factory(
    StockInItemModel,
    form=StockInFromPOForm,
    extra=0  # Don't show any empty extra forms by default
)


class StockInSelectionForm(forms.Form):
    """
    A form to select which items from a Purchase Order to stock in.
    """
    items_to_receive = forms.ModelMultipleChoiceField(
        queryset=PurchaseOrderItemModel.objects.none(),  # Populated in the view
        widget=forms.CheckboxSelectMultiple(),
        label="",  # The label is handled by the table structure in the template
        required=False  # Make it optional so form doesn't fail if nothing selected
    )

    def __init__(self, *args, **kwargs):
        purchase_order = kwargs.pop('purchase_order', None)
        super().__init__(*args, **kwargs)

        if purchase_order:
            # Get pending items and ensure they're properly selected
            pending_items = purchase_order.items.filter(
                item__isnull=False
            ).exclude(is_stocked_in=True)

            self.fields['items_to_receive'].queryset = pending_items

            # Debug: Print what we're getting
            print(f"Pending items count: {pending_items.count()}")
            for item in pending_items:
                print(f"Item: {item.item.name if item.item else item.item_description} - Qty: {item.quantity}")


class StockOutForm(forms.ModelForm):
    """Form for creating a new stock-out transaction from the item detail page."""
    quantity_removed = forms.DecimalField(widget=forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01'}))
    specific_batch_id = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = StockOutModel
        fields = ['reason', 'location', 'staff_recipient', 'quantity_removed', 'notes']
        widgets = {
            'reason': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'staff_recipient': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class StockTransferCreateForm(forms.ModelForm):
    """Form for creating the Stock Transfer batch header."""
    class Meta:
        model = StockTransferModel
        fields = ['direction', 'transfer_date', 'notes']
        widgets = {
            'direction': forms.Select(attrs={'class': 'form-select'}),
            'transfer_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }


class PurchaseAdvanceCreateForm(forms.ModelForm):
    """Form for creating the initial Purchase Advance request."""

    class Meta:
        model = PurchaseAdvanceModel
        fields = ['staff', 'purpose']
        widgets = {
            'staff': forms.Select(attrs={'class': 'form-select'}),
            'purpose': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Purpose of advance request...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['staff'].queryset = StaffModel.objects.filter(status='active')


class PurchaseAdvanceItemForm(forms.ModelForm):
    """Form for adding/editing individual line items on the advance detail page."""

    class Meta:
        model = PurchaseAdvanceItemModel
        fields = ['item', 'item_description', 'quantity', 'estimated_unit_cost']
        widgets = {
            'item': forms.HiddenInput(),
            'item_description': forms.TextInput(
                attrs={'class': 'form-control form-control-sm', 'placeholder': 'Item Description'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Qty'}),
            'estimated_unit_cost': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Est. Cost'}),
        }


class SaleForm(forms.ModelForm):
    """
    Form for the sale header in the Point of Sale (POS) interface.
    Handles customer selection (student or staff), payment method, and overall discount.
    """

    class Meta:
        model = SaleModel
        fields = ['customer', 'staff_customer', 'payment_method', 'discount']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'staff_customer': forms.Select(attrs={'class': 'form-select'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'discount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Populate student dropdown
        self.fields['customer'].queryset = StudentModel.objects.filter(is_active=True).select_related(
            'student_profile__user')
        self.fields['customer'].required = False
        self.fields['customer'].empty_label = "-- Select Student --"
        self.fields['customer'].label = "Student Customer"

        # Populate staff dropdown
        self.fields['staff_customer'].queryset = StaffModel.objects.filter(status='active')
        self.fields['staff_customer'].required = False
        self.fields['staff_customer'].empty_label = "-- Select Staff --"
        self.fields['staff_customer'].label = "Staff Customer"

        # Help text
        self.fields['customer'].help_text = "Leave both empty for walk-in customers"

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        staff_customer = cleaned_data.get('staff_customer')
        payment_method = cleaned_data.get('payment_method')

        # Validation: Can't select both student and staff
        if customer and staff_customer:
            raise forms.ValidationError("Cannot select both a student and a staff member. Please choose only one.")

        # Validation: Student wallet requires a student
        if payment_method == 'student_wallet' and not customer:
            raise forms.ValidationError("Student Wallet payment requires a student to be selected.")

        # Validation: Staff wallet requires a staff member
        if payment_method == 'staff_wallet' and not staff_customer:
            raise forms.ValidationError("Staff Wallet payment requires a staff member to be selected.")

        return cleaned_data