from decimal import Decimal
from django.db import models, transaction
from django.db.models import Sum, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.contrib.auth.models import User
import uuid

from admin_site.models import SessionModel, SchoolSettingModel, TermModel
from human_resource.models import StaffModel
from student.models import StudentModel


# ================== INVENTORY MODELS ==================

class CategoryModel(models.Model):
    """Product/Item categories (e.g., 'Electronics', 'Stationery', 'Food')"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


class ItemModel(models.Model):
    """Core item/product model for both shop and store"""

    class Location(models.TextChoices):
        SHOP = 'shop', 'Shop Only'
        STORE = 'store', 'Store Only'
        BOTH = 'both', 'Both Shop & Store'

    class Unit(models.TextChoices):
        PIECE = 'piece', 'Piece'
        PACK = 'pack', 'Pack'
        BOX = 'box', 'Box'
        KG = 'kg', 'Kilogram'
        CARTON = 'carton', 'Carton'

    category = models.ForeignKey(CategoryModel, on_delete=models.PROTECT, related_name='items')
    name = models.CharField(max_length=255)
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    unit = models.CharField(max_length=20, choices=Unit.choices, default=Unit.PIECE)
    location = models.CharField(max_length=10, choices=Location.choices, default=Location.BOTH)
    current_selling_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name="Selling Price"
    )

    shop_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    store_quantity = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    reorder_level = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('10.00'))

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
        constraints = [
            models.UniqueConstraint(fields=['name', 'unit'], name='unique_item_name_unit')
        ]

    def __str__(self):
        return f"{self.name} ({self.get_unit_display()})"

    def get_absolute_url(self):
        return reverse('inventory_item_detail', kwargs={'pk': self.pk})

    @property
    def total_quantity(self):
        return self.shop_quantity + self.store_quantity

    @property
    def is_low_stock(self):
        return self.total_quantity <= self.reorder_level

    def get_stock_ins(self):
        """Returns the 10 most recent stock-in records for this item."""
        return self.stock_ins.order_by('-stock_in__date_received', '-stock_in__created_at')[:10]

    def get_stock_outs(self):
        """Returns the 10 most recent stock-out records for this item."""
        return self.stock_outs.order_by('-date_removed', '-created_at')[:10]

    def get_stock_transfers(self):
        """Returns the 10 most recent stock transfer records for this item."""
        return self.transfers.order_by('-transfer__transfer_date', '-transfer__created_at')[:10]

    @property
    def last_cost_price(self):
        """
        Gets the unit cost from the most recent StockIn record for this item.
        """
        # --- THIS IS THE CORRECTED LINE ---
        # It now correctly looks through the 'stock_in' relationship to find the 'date_received'.
        last_stock_in_item = self.stock_ins.order_by('-stock_in__date_received').first()

        if last_stock_in_item:
            return last_stock_in_item.unit_cost
        return Decimal('0.00')


class SupplierModel(models.Model):
    """Stores information about vendors and suppliers of inventory items."""
    name = models.CharField(max_length=200, unique=True)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    phone_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    # Auditing fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_total_supplied_amount(self):
        """Calculates the total value of all received purchase orders from this supplier."""
        # THE FIX: Calculate the sum by multiplying the quantity and unit cost from the related items.
        total = self.purchaseordermodel_set.filter().aggregate(
            total_sum=Sum(F('items__quantity') * F('items__unit_cost'))
        )['total_sum']
        return total or Decimal('0.00')

    def get_total_paid_amount(self):
        """Calculates the total amount paid to this supplier."""
        # THIS IS THE CORRECTED LINE: Using the 'payments' related_name
        total = self.payments.aggregate(
            total_sum=Sum('amount')
        )['total_sum']
        return total or Decimal('0.00')

    @property
    def balance_owed(self):
        """Calculates the outstanding balance owed to the supplier."""
        return abs(self.get_total_supplied_amount() - self.get_total_paid_amount())


class PurchaseOrderModel(models.Model):
    """Represents a purchase order header sent to a supplier."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        PARTIALLY_RECEIVED = 'partially_received', 'Partially Received'
        RECEIVED = 'received', 'Received'
        CANCELLED = 'cancelled', 'Cancelled'

    supplier = models.ForeignKey(SupplierModel, on_delete=models.PROTECT)
    order_number = models.CharField(max_length=50, unique=True, blank=True)
    order_date = models.DateField(default=timezone.now)
    expected_date = models.DateField(blank=True, null=True)
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(blank=True, null=True)

    # Auditing
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-order_date', '-created_at']
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"

    def __str__(self):
        return f"PO#{self.order_number} - {self.supplier.name}"

    def get_absolute_url(self):
        return reverse('inventory_po_detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"PO-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None:
                    self.session = setting.session
                if self.term is None:
                    self.term = setting.term
        super().save(*args, **kwargs)

    @property
    def total_amount(self):
        """Calculates the total amount of the purchase order from its line items."""
        total = self.items.aggregate(total=Sum(F('quantity') * F('unit_cost')))['total']
        return total or Decimal('0.00')

    @property
    def has_stock_received(self):
        """
        Checks if any StockIn records are linked to this purchase order.
        This is used to determine if the PO can still be edited.
        """
        return self.stockinmodel_set.exists()

    @property
    def amount_paid(self):
        """Calculates the total amount paid against this specific purchase order."""
        total = self.supplierpaymentmodel_set.filter(status='completed').aggregate(
            total_sum=Sum('amount')
        )['total_sum']
        return total or Decimal('0.00')

    @property
    def balance(self):
        """Calculates the outstanding balance for this purchase order."""
        return self.total_amount - self.amount_paid


class PurchaseOrderItemModel(models.Model):
    """Represents a single line item within a Purchase Order."""
    purchase_order = models.ForeignKey(PurchaseOrderModel, on_delete=models.CASCADE, related_name='items')

    # Can be linked to an existing item or be a custom, one-off item
    item = models.ForeignKey(ItemModel, on_delete=models.SET_NULL, blank=True, null=True)
    item_description = models.CharField(
        max_length=255,
        help_text="Auto-filled if an inventory item is selected, or enter a custom description."
    )

    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.00'))])
    is_stocked_in = models.BooleanField(default=False)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"{self.item_description} ({self.quantity})"

    @property
    def line_total(self):
        return self.quantity * self.unit_cost

    def save(self, *args, **kwargs):
        """
        Simple save method that only handles its own fields.
        """
        if self.item and not self.item_description:
            self.item_description = self.item.name
        super().save(*args, **kwargs)


class StockInModel(models.Model):
    """Represents a single stock-in batch/event. This is the parent document."""

    class Source(models.TextChoices):
        PURCHASE = 'purchase', 'Purchase'
        RETURN = 'return', 'Return'
        ADJUSTMENT = 'adjustment', 'Adjustment'
        TRANSFER = 'transfer', 'Transfer'
        DONATION = 'donation', 'Donation'

    receipt_number = models.CharField(max_length=50, unique=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.PURCHASE)

    # These fields are optional and primarily for 'purchase' source
    supplier = models.ForeignKey(SupplierModel, on_delete=models.SET_NULL, null=True, blank=True)
    purchase_order = models.ForeignKey(PurchaseOrderModel, on_delete=models.SET_NULL, null=True, blank=True)

    date_received = models.DateField(default=timezone.now)
    location = models.CharField(max_length=10, choices=ItemModel.Location.choices, default=ItemModel.Location.STORE)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-date_received']
        verbose_name = "Stock In Batch"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = f"STK-IN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None:
                    self.session = setting.session
                if self.term is None:
                    self.term = setting.term

        super().save(*args, **kwargs)

    def __str__(self):
        return self.receipt_number

    @property
    def total_cost(self):
        """
        Calculates the total cost of all items in this stock-in batch.
        """
        total = self.items.annotate(
            line_total=F('quantity_received') * F('unit_cost')
        ).aggregate(
            total=Coalesce(Sum('line_total'), Decimal('0.00'), output_field=DecimalField())
        )['total']
        return total


class StockInItemModel(models.Model):
    """Represents a single line item within a StockInModel batch."""
    stock_in = models.ForeignKey(StockInModel, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name='stock_ins')
    purchase_order_item = models.ForeignKey(PurchaseOrderItemModel, on_delete=models.SET_NULL, null=True, blank=True)

    quantity_received = models.DecimalField(max_digits=10, decimal_places=2)
    # For future FIFO/LIFO: tracks how much of THIS specific batch is left.
    quantity_remaining = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)

    # Batch and Expiry tracking
    batch_number = models.CharField(max_length=100, blank=True, null=True)
    expiry_date = models.DateField(blank=True, null=True)

    @property
    def line_total(self):
        return self.quantity_received * self.unit_cost

    def save(self, *args, **kwargs):
        """
        FIXED VERSION: This method now uses update() to avoid triggering
        additional save() calls that could cause recursion.
        """
        is_new = self.pk is None
        if is_new:
            self.quantity_remaining = self.quantity_received

        super().save(*args, **kwargs)

        if is_new:
            # Use atomic transaction for the inventory update
            with transaction.atomic():
                # Use update() instead of save() to avoid triggering signals/recursion
                if self.stock_in.location == 'shop':
                    ItemModel.objects.filter(pk=self.item.pk).update(
                        shop_quantity=F('shop_quantity') + self.quantity_received
                    )
                else:
                    ItemModel.objects.filter(pk=self.item.pk).update(
                        store_quantity=F('store_quantity') + self.quantity_received
                    )

    def delete(self, *args, **kwargs):
        """
        When a StockInItem is deleted, we need to reverse the inventory change.
        Using update() here as well to avoid recursion.
        """
        with transaction.atomic():
            # Reverse the inventory change
            if self.stock_in.location == 'shop':
                ItemModel.objects.filter(pk=self.item.pk).update(
                    shop_quantity=F('shop_quantity') - self.quantity_received
                )
            else:
                ItemModel.objects.filter(pk=self.item.pk).update(
                    store_quantity=F('store_quantity') - self.quantity_received
                )

        super().delete(*args, **kwargs)


class StockOutModel(models.Model):
    """Stock removed (non-sale transactions like damage, staff collection, etc.)"""

    class Reason(models.TextChoices):
        STAFF_COLLECTION = 'staff_collection', 'Staff Collection'
        DAMAGE = 'damage', 'Damage'
        EXPIRED = 'expired', 'Expired'
        ADJUSTMENT = 'adjustment', 'Stock Adjustment'
        WASTAGE = 'wastage', 'Wastage'
        CAFETERIA = 'cafeteria', 'Cafeteria'
        BOARDING = 'boarding house store', 'Boarding House Store'

    class LocationChoices(models.TextChoices):
        STORE = 'store', 'Store'
        SHOP = 'shop', 'Shop'

    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name='stock_outs')
    quantity_removed = models.DecimalField(max_digits=10, decimal_places=2,
                                           validators=[MinValueValidator(Decimal('0.01'))])
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    reason = models.CharField(max_length=20, choices=Reason.choices)
    location = models.CharField(max_length=10, choices=LocationChoices.choices)
    staff_recipient = models.ForeignKey(StaffModel, on_delete=models.SET_NULL, null=True, blank=True)
    date_removed = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='stk_out_cb')
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-date_removed']
        verbose_name = "Stock Out Record"

    def __str__(self):
        return f"Stock Out: {self.item.name} - {self.quantity_removed}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if is_new:
            # The view is now responsible for validation before calling save.
            # This method now safely assumes it has a valid item and quantity.
            if self.unit_cost is None or self.unit_cost == Decimal('0.00'):
                self.unit_cost = self.item.last_cost_price

            self.total_cost = self.quantity_removed * self.unit_cost

        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None:
                    self.session = setting.session
                if self.term is None:
                    self.term = setting.term

        super().save(*args, **kwargs)


class StockTransferModel(models.Model):
    """The parent document for a single, multi-item stock transfer event."""

    class Direction(models.TextChoices):
        STORE_TO_SHOP = 'store_to_shop', 'Store to Shop'
        SHOP_TO_STORE = 'shop_to_store', 'Shop to Store'

    receipt_number = models.CharField(max_length=50, unique=True, blank=True)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    transfer_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)

    # Auditing
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transfer_date', '-created_at']
        verbose_name = "Stock Transfer Batch"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = f"STK-TRN-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None:
                    self.session = setting.session
                if self.term is None:
                    self.term = setting.term

        super().save(*args, **kwargs)

    def __str__(self):
        return self.receipt_number


class StockTransferItemModel(models.Model):
    """A single line item within a stock transfer batch."""
    transfer = models.ForeignKey(StockTransferModel, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT, related_name='transfers')
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])

    def __str__(self):
        return f"{self.item.name} ({self.quantity})"


# ================== INVENTORY ASSIGNMENT MODELS ==================
class InventoryAssignmentModel(models.Model):
    """Assign inventory items to classes/students for collection"""

    GENDER_CHOICES = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('both', 'Both')
    ]

    TYPE_CHOICES = [
        ('pri', 'Primary'),
        ('sec', 'Secondary'),
        ('mix', 'General')
    ]

    # What is being assigned
    item = models.ForeignKey(ItemModel, on_delete=models.CASCADE, related_name='assignments')
    quantity_per_student = models.DecimalField(max_digits=10, decimal_places=2,
                                               validators=[MinValueValidator(Decimal('0.01'))])

    # Who gets it
    student_classes = models.ManyToManyField('admin_site.ClassesModel', blank=True)
    gender = models.CharField(max_length=15, choices=GENDER_CHOICES, default='both')

    # When and conditions
    session = models.ForeignKey(SessionModel, on_delete=models.CASCADE, blank=True, null=True)
    term = models.ForeignKey(TermModel, on_delete=models.CASCADE, blank=True, null=True)
    is_mandatory = models.BooleanField(default=False, help_text="Must all eligible students collect?")

    # Fee integration (if item must be paid for)
    is_free = models.BooleanField(default=True, help_text="Is this item free or must fees be paid?")
    # Settings
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='assignment_updates')

    class Meta:
        verbose_name = "Inventory Assignment"
        verbose_name_plural = "Inventory Assignments"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Auto-set session and term if not provided
        if not self.session or not self.term:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if not self.session:
                    self.session = setting.session
                if not self.term:
                    self.term = setting.term
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item.name} - {self.term} {self.session}"


class InventoryCollectionModel(models.Model):
    """Track individual student collections of assigned inventory"""

    STATUS_CHOICES = [
        ('pending', 'Pending Collection'),
        ('collected', 'Collected'),
        ('partially_collected', 'Partially Collected'),
        ('cancelled', 'Cancelled'),
        ('returned', 'Returned')
    ]

    assignment = models.ForeignKey(InventoryAssignmentModel, on_delete=models.CASCADE,
                                   related_name='collections')
    student = models.ForeignKey(StudentModel, on_delete=models.CASCADE, related_name='inventory_collections')

    # Collection details
    quantity_assigned = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    quantity_collected = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Dates
    collection_date = models.DateField(blank=True, null=True)
    due_date = models.DateField(blank=True, null=True)

    # Status and payment
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    payment_required = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2,
                                             default=Decimal('0.00'), blank=True, null=True,
                                             help_text="Amount per student if not free")
    payment_completed = models.BooleanField(default=False)

    # Collection details
    collected_by_staff = models.ForeignKey(StaffModel, on_delete=models.SET_NULL, null=True, blank=True,
                                           help_text="Staff who handed over the items")
    notes = models.TextField(blank=True, null=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('assignment', 'student')
        verbose_name = "Inventory Collection"
        verbose_name_plural = "Inventory Collections"
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        # Set quantity_assigned from assignment if not set
        if not self.quantity_assigned:
            self.quantity_assigned = self.assignment.quantity_per_student

        # Update status based on collection
        if self.quantity_collected >= self.quantity_assigned:
            self.status = 'collected'
        elif self.quantity_collected > 0:
            self.status = 'partially_collected'
        elif self.status not in ['cancelled', 'returned']:
            self.status = 'pending'

        super().save(*args, **kwargs)

    @property
    def outstanding_quantity(self):
        """Quantity still to be collected"""
        return self.quantity_assigned - self.quantity_collected

    def __str__(self):
        return f"{self.student} - {self.assignment.item.name} ({self.status})"


class InventoryReturnModel(models.Model):
    """Handle returns of collected inventory items"""

    RETURN_REASON_CHOICES = [
        ('damaged', 'Damaged'),
        ('wrong_size', 'Wrong Size'),
        ('excess', 'Excess Quantity'),
        ('duplicate', 'Duplicate Collection'),
        ('student_left', 'Student Left School'),
        ('other', 'Other')
    ]

    collection = models.ForeignKey(InventoryCollectionModel, on_delete=models.CASCADE,
                                   related_name='returns')
    quantity_returned = models.DecimalField(max_digits=10, decimal_places=2,
                                            validators=[MinValueValidator(Decimal('0.01'))])
    return_reason = models.CharField(max_length=20, choices=RETURN_REASON_CHOICES)
    return_date = models.DateField(default=timezone.now)

    # Condition and action
    item_condition = models.CharField(max_length=50, default='good')
    action_taken = models.CharField(max_length=100, blank=True, null=True,
                                    help_text="What was done with returned items")

    # Staff and notes
    received_by = models.ForeignKey(StaffModel, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Update collection status and quantities
        self.collection.quantity_collected -= self.quantity_returned
        if self.collection.quantity_collected <= 0:
            self.collection.quantity_collected = Decimal('0.00')
            self.collection.status = 'returned'
        elif self.collection.quantity_collected < self.collection.quantity_assigned:
            self.collection.status = 'partially_collected'
        self.collection.save()

    def __str__(self):
        return f"Return - {self.collection.student} - {self.quantity_returned} {self.collection.assignment.item.name}"


class SaleModel(models.Model):
    """The parent document for a single sales transaction."""

    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        STUDENT_WALLET = 'student_wallet', 'Student Wallet'
        POS = 'pos', 'POS'

    class Status(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        REFUNDED = 'refunded', 'Refunded'

    transaction_id = models.CharField(max_length=50, unique=True, blank=True)
    sale_date = models.DateTimeField(default=timezone.now)
    customer = models.ForeignKey(StudentModel, on_delete=models.SET_NULL, null=True, blank=True)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)

    # Auditing
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    created_by = models.ForeignKey(StaffModel, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sale_date']
        verbose_name = "Sale Transaction"

    def save(self, *args, **kwargs):
        if not self.transaction_id:
            self.transaction_id = f"SALE-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4].upper()}"
        if not self.session or not self.term:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if not self.session: self.session = setting.session
                if not self.term: self.term = setting.term
        super().save(*args, **kwargs)

    def __str__(self):
        return self.transaction_id

    @property
    def subtotal(self):
        """
        Sum of (quantity * unit_price) across related sale items.
        Uses an ExpressionWrapper so we don't rely on a non-existent 'line_total' DB field.
        """
        # Build expression: quantity * unit_price
        line_expr = ExpressionWrapper(
            F('quantity') * F('unit_price'),
            output_field=DecimalField(max_digits=14, decimal_places=2)
        )

        # Aggregate sum at DB level; Coalesce to return 0 if no rows
        agg = self.items.aggregate(
            total=Coalesce(Sum(line_expr), Decimal('0.00'), output_field=DecimalField())
        )

        total = agg.get('total') or Decimal('0.00')
        # Normalize to 2 decimal places
        return total.quantize(Decimal('0.01'))

    @property
    def total_amount(self):
        return self.subtotal - self.discount


class SaleItemModel(models.Model):
    """A single line item within a sale transaction."""
    sale = models.ForeignKey(SaleModel, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemModel, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2,
                                     help_text="The selling price at the time of sale.")

    # Financials (snapshot at the time of sale)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    @property
    def line_total(self):
        return self.quantity * self.unit_price

    @property
    def profit(self):
        return (self.unit_price - self.unit_cost) * self.quantity

    def __str__(self):
        return f"{self.item.name} x {self.quantity}"


# ================== PURCHASE ADVANCE MODELS ==================
class PurchaseAdvanceModel(models.Model):
    """Purchase advance requests by staff"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('disbursed', 'Disbursed'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    staff = models.ForeignKey(StaffModel, on_delete=models.CASCADE)
    advance_number = models.CharField(max_length=50, unique=True, blank=True)
    purpose = models.TextField()

    requested_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    approved_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    disbursed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    request_date = models.DateField(default=timezone.now)
    approved_date = models.DateField(blank=True, null=True)
    disbursed_date = models.DateField(blank=True, null=True)

    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approved_advances')
    disbursed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='disbursed_advances')

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_advances')

    class Meta:
        ordering = ['-request_date', '-created_at']
        verbose_name = "Purchase Advance"
        verbose_name_plural = "Purchase Advances"

    def get_absolute_url(self):
        return reverse('inventory_advance_detail', kwargs={'pk': self.pk})

    def save(self, *args, **kwargs):
        if not self.advance_number:
            self.advance_number = f"ADV-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        # Auto-set session and term
        if not self.session or not self.term:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if not self.session:
                    self.session = setting.session
                if not self.term:
                    self.term = setting.term

        # Calculate requested amount from items
        if self.pk:
            self.requested_amount = sum(item.line_total for item in self.items.all())

        super().save(*args, **kwargs)

    @property
    def total_amount(self):
        """Calculates the total requested amount from line items."""
        total = self.items.aggregate(total=Sum(F('quantity') * F('estimated_unit_cost')))['total']
        return total or Decimal('0.00')

    @property
    def balance_due(self):
        """Balance after shopping - positive means staff owes school"""
        if hasattr(self, 'report'):
            return self.report.actual_total - self.disbursed_amount
        return Decimal('0.00')

    @property
    def balance(self):
        """Calculates the outstanding balance to be disbursed."""
        return self.approved_amount - self.disbursed_amount

    def __str__(self):
        return f"Advance #{self.advance_number} - {self.staff}"


class PurchaseAdvanceItemModel(models.Model):
    """Items in a purchase advance request"""
    advance = models.ForeignKey(PurchaseAdvanceModel, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemModel, on_delete=models.CASCADE, blank=True, null=True,
                             help_text="Select from inventory items or leave blank for custom item")
    item_description = models.CharField(max_length=255,
                                        help_text="Item name - auto-filled if inventory item selected, or enter custom name")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    def save(self, *args, **kwargs):
        # Auto-fill item description if inventory item is selected
        if self.item and not self.item_description:
            self.item_description = self.item.name
        self.line_total = self.quantity * self.estimated_unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item_description} - {self.quantity}"


class PurchaseReportModel(models.Model):
    """Actual purchase report after shopping"""
    advance = models.OneToOneField(PurchaseAdvanceModel, on_delete=models.CASCADE, related_name='report')
    actual_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    balance_due = models.DecimalField(max_digits=12, decimal_places=2,
                                      default=Decimal('0.00'))  # +ve if staff owes, -ve if school owes

    report_date = models.DateField(default=timezone.now)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        self.balance_due = self.actual_total - self.advance.disbursed_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Report for {self.advance.advance_number}"


class PurchaseReportItemModel(models.Model):
    """Actual items purchased"""
    report = models.ForeignKey(PurchaseReportModel, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(ItemModel, on_delete=models.CASCADE, blank=True, null=True,
                             help_text="Select from inventory items if applicable")
    item_description = models.CharField(max_length=255,
                                        help_text="Item name - auto-filled if inventory item selected, or enter custom name")
    quantity_bought = models.DecimalField(max_digits=10, decimal_places=2)
    actual_unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    def save(self, *args, **kwargs):
        # Auto-fill item description if inventory item is selected
        if self.item and not self.item_description:
            self.item_description = self.item.name
        self.line_total = self.quantity_bought * self.actual_unit_cost
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.item_description} - {self.quantity_bought} bought"


class CollectionGenerationJob(models.Model):
    """Track background jobs for generating inventory collections"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUCCESS = 'success', 'Success'
        FAILURE = 'failure', 'Failure'

    # Job identification
    job_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    assignment = models.ForeignKey(
        'InventoryAssignmentModel',
        on_delete=models.CASCADE,
        related_name='generation_jobs'
    )

    # Progress tracking
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING
    )
    total_students = models.IntegerField(default=0)
    processed_students = models.IntegerField(default=0)
    created_collections = models.IntegerField(default=0)
    skipped_students = models.IntegerField(default=0)

    # Error handling
    error_message = models.TextField(blank=True, null=True)

    # Audit
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = "Collection Generation Job"
        verbose_name_plural = "Collection Generation Jobs"
        ordering = ['-created_at']

    def __str__(self):
        return f"Job {self.job_id} - {self.assignment.item.name} ({self.get_status_display()})"

    @property
    def progress_percentage(self):
        """Calculate progress percentage"""
        if self.total_students == 0:
            return 0
        return int((self.processed_students / self.total_students) * 100)

    @property
    def duration(self):
        """Calculate job duration"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


# ================== DIRECT SALES MODEL ==================
class DirectSaleModel(models.Model):
    """
    Track direct sales/purchases to students
    (items not part of any assignment)
    """

    # Who and what
    student = models.ForeignKey(StudentModel, on_delete=models.CASCADE, related_name='direct_purchases')
    item = models.ForeignKey(ItemModel, on_delete=models.CASCADE, related_name='direct_sales')

    # Transaction details
    quantity = models.DecimalField(max_digits=10, decimal_places=2,
                                   validators=[MinValueValidator(Decimal('0.01'))])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))

    # Payment status
    payment_completed = models.BooleanField(default=True)
    payment_method = models.CharField(max_length=50, blank=True, null=True,
                                      help_text="Cash, Transfer, etc.")

    # Session/Term tracking
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL,
                                blank=True, null=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL,
                             blank=True, null=True)

    # Staff and notes
    sold_by = models.ForeignKey(StaffModel, on_delete=models.SET_NULL,
                                null=True, blank=True,
                                help_text="Staff who processed the sale")
    notes = models.TextField(blank=True, null=True)

    # Audit
    sale_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                   null=True, blank=True)

    class Meta:
        verbose_name = "Direct Sale"
        verbose_name_plural = "Direct Sales"
        ordering = ['-sale_date', '-created_at']

    def save(self, *args, **kwargs):
        # Auto-calculate total if not set
        if not self.total_amount:
            self.total_amount = self.quantity * self.unit_price

        # Auto-set session and term if not provided
        if not self.session or not self.term:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if not self.session:
                    self.session = setting.session
                if not self.term:
                    self.term = setting.term

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.item.name} ({self.quantity}) - {self.sale_date}"

    @property
    def balance(self):
        """Outstanding balance"""
        return self.total_amount - self.amount_paid