import calendar
import logging
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.apps import apps
from django.db import OperationalError
from django.db.models import Sum
from django.utils import timezone

from inventory.models import SupplierModel, PurchaseOrderModel, PurchaseAdvanceModel
from student.models import StudentModel, StudentWalletModel
from human_resource.models import StaffModel
from admin_site.models import SessionModel, TermModel, SchoolSettingModel, ClassesModel, ClassSectionModel
from django.utils.translation import gettext_lazy as _

# Configure a logger for this module
logger = logging.getLogger(__name__)


def generate_payment_reference():
    """Generate a unique payment reference"""
    return f"PAY-{timezone.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"


# If you don't have num2words library, add this to your model or utils.py

def amount_to_words(amount):
    """
    Convert amount to words (simple English implementation)
    For production, use: pip install num2words
    """
    ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
    teens = ['Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen', 'Seventeen', 'Eighteen',
             'Nineteen']

    def convert_below_thousand(num):
        if num == 0:
            return ''
        elif num < 10:
            return ones[num]
        elif num < 20:
            return teens[num - 10]
        elif num < 100:
            return tens[num // 10] + (' ' + ones[num % 10] if num % 10 != 0 else '')
        else:
            return ones[num // 100] + ' Hundred' + (
                ' and ' + convert_below_thousand(num % 100) if num % 100 != 0 else '')

    if amount == 0:
        return 'Zero'

    # Split into integer and decimal parts
    amount_str = str(amount)
    if '.' in amount_str:
        integer_part, decimal_part = amount_str.split('.')
        integer_part = int(integer_part)
        decimal_part = int(decimal_part)
    else:
        integer_part = int(amount)
        decimal_part = 0

    result = ''

    # Billions
    if integer_part >= 1000000000:
        result += convert_below_thousand(integer_part // 1000000000) + ' Billion '
        integer_part %= 1000000000

    # Millions
    if integer_part >= 1000000:
        result += convert_below_thousand(integer_part // 1000000) + ' Million '
        integer_part %= 1000000

    # Thousands
    if integer_part >= 1000:
        result += convert_below_thousand(integer_part // 1000) + ' Thousand '
        integer_part %= 1000

    # Hundreds
    if integer_part > 0:
        result += convert_below_thousand(integer_part)

    # Add decimal part if exists
    if decimal_part > 0:
        result += f' and {decimal_part}/100'

    return result.strip()


# Then update the model method:
def get_total_in_words(self):
    """Convert amount to words for voucher"""
    try:
        from num2words import num2words
        amount_str = num2words(float(self.amount), lang='en')
    except ImportError:
        # Fallback to custom function
        amount_str = amount_to_words(float(self.amount))

    currency_name = "Naira" if self.currency == self.Currency.NAIRA else "Dollars"
    return f"{amount_str.title()} {currency_name} Only"


class StudentFundingModel(models.Model):
    # ✔️ REFACTOR: Enforced data integrity using TextChoices.
    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        POS = 'pos', 'POS'
        BANK_TELLER = 'bank teller', 'Bank Teller'
        BANK_TRANSFER = 'bank transfer', 'Bank Transfer'

    class PaymentMode(models.TextChoices):
        OFFLINE = 'offline', 'Offline'
        ONLINE = 'online', 'Online'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        FAILED = 'failed', 'Failed'

    student = models.ForeignKey(StudentModel, on_delete=models.CASCADE, related_name='funding_list')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    proof_of_payment = models.FileField(blank=True, null=True, upload_to='images/funding')
    method = models.CharField(max_length=100, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    mode = models.CharField(max_length=100, choices=PaymentMode.choices, blank=True, default=PaymentMode.OFFLINE)
    status = models.CharField(max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(StaffModel, on_delete=models.SET_NULL, null=True, blank=True,
                                   help_text="Staff member who recorded this funding transaction.")
    # ✔️ REFACTOR: Linked to SessionModel and the new TermModel for consistency.
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    teller_number = models.CharField(max_length=50, null=True, blank=True)
    decline_reason = models.CharField(max_length=250, null=True, blank=True)
    reference = models.CharField(max_length=250, null=True, blank=True, help_text="Unique reference for this transaction.")

    class Meta:
        verbose_name = "Student Funding Record"
        verbose_name_plural = "Student Funding Records"
        ordering = ['-created_at']

    def __str__(self):
        return f"Funding for {self.student} - {self.amount}"

    def save(self, *args, **kwargs):
        # ✔️ ROBUSTNESS: Improved logic to safely auto-populate session and term.
        if self.session is None or self.term is None:
            try:
                setting = SchoolSettingModel.objects.first()
                if setting:
                    if self.session is None: self.session = setting.session
                    if self.term is None: self.term = setting.term
                else:
                    logger.warning("No SchoolSettingModel found. Cannot auto-set session/term for funding.")
            except (OperationalError, Exception) as e:
                logger.error(f"Error fetching SchoolSettingModel for funding record: {e}", exc_info=True)

        is_new = self.pk is None
        super().save(*args, **kwargs)


class StaffFundingModel(models.Model):
    # ✔️ REFACTOR: Enforced data integrity using TextChoices.
    class PaymentMethod(models.TextChoices):
        CASH = 'cash', 'Cash'
        POS = 'pos', 'POS'
        BANK_TELLER = 'bank teller', 'Bank Teller'
        BANK_TRANSFER = 'bank transfer', 'Bank Transfer'

    class PaymentMode(models.TextChoices):
        OFFLINE = 'offline', 'Offline'
        ONLINE = 'online', 'Online'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        FAILED = 'failed', 'Failed'

    staff = models.ForeignKey(StaffModel, on_delete=models.CASCADE, related_name='staff_funding_list')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    proof_of_payment = models.FileField(blank=True, null=True, upload_to='images/funding')
    method = models.CharField(max_length=100, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    mode = models.CharField(max_length=100, choices=PaymentMode.choices, blank=True, default=PaymentMode.OFFLINE)
    status = models.CharField(max_length=30, choices=PaymentStatus.choices, default=PaymentStatus.CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(StaffModel, on_delete=models.SET_NULL, null=True, blank=True,
                                   help_text="Staff member who recorded this funding transaction.")
    # ✔️ REFACTOR: Linked to SessionModel and the new TermModel for consistency.
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    teller_number = models.CharField(max_length=50, null=True, blank=True)
    decline_reason = models.CharField(max_length=250, null=True, blank=True)
    reference = models.CharField(max_length=250, null=True, blank=True, help_text="Unique reference for this transaction.")

    class Meta:
        verbose_name = "Student Funding Record"
        verbose_name_plural = "Student Funding Records"
        ordering = ['-created_at']

    def __str__(self):
        return f"Funding for {self.staff} - {self.amount}"

    def save(self, *args, **kwargs):
        # ✔️ ROBUSTNESS: Improved logic to safely auto-populate session and term.
        if self.session is None or self.term is None:
            try:
                setting = SchoolSettingModel.objects.first()
                if setting:
                    if self.session is None: self.session = setting.session
                    if self.term is None: self.term = setting.term
                else:
                    logger.warning("No SchoolSettingModel found. Cannot auto-set session/term for funding.")
            except (OperationalError, Exception) as e:
                logger.error(f"Error fetching SchoolSettingModel for funding record: {e}", exc_info=True)

        is_new = self.pk is None
        super().save(*args, **kwargs)


# ===================================================================
# Fee Structure Setup Models (The "Price List")
# ===================================================================
class FeeModel(models.Model):
    """Defines a single type of fee (e.g., Tuition, PTA Levy, Bus Fee)."""

    class FeeOccurrence(models.TextChoices):
        TERMLY = 'quaterly', 'Quaterly'
        ANNUALLY = 'annually', 'Annually'
        ONE_TIME = 'one_time', 'One Time'

    name = models.CharField(max_length=250, unique=True)
    code = models.CharField(max_length=100, unique=True, help_text="A unique code for this fee, e.g., TUI-001.")
    description = models.TextField(blank=True, null=True)
    occurrence = models.CharField(max_length=50, choices=FeeOccurrence.choices)
    payment_term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True,
                                     help_text="For 'One Time' fees, specify which term it must be paid in.")
    required_utility = models.ForeignKey(
        'student.UtilityModel',
        on_delete=models.SET_NULL, null=True, blank=True,
        help_text="If set, this fee is only applied to students subscribed to this utility (e.g., Bus Fee for Transport Utility)."
    )

    parent_bound = models.BooleanField(
        default=False,
        help_text="Check if this fee should be charged once per Parent/Family, rather than per student."
    )
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_fees')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Fee Type"

    def __str__(self):
        return self.name.upper()


class FeeGroupModel(models.Model):
    """Groups fees together for assignment (e.g., 'New Student Fees', 'JSS1 Fees')."""
    name = models.CharField(max_length=250, unique=True)
    description = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_fee_groups')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Fee Group"

    def __str__(self):
        return self.name.upper()


class FeeMasterModel(models.Model):
    """
    The heart of the fee structure. Links a Fee to a Group and assigns it
    to classes. The actual price is now determined by the TermlyFeeAmountModel.
    """
    group = models.ForeignKey(FeeGroupModel, on_delete=models.CASCADE, related_name='fee_structures')
    fee = models.ForeignKey(FeeModel, on_delete=models.PROTECT, related_name='structures')
    student_classes = models.ManyToManyField(ClassesModel,
                                             help_text="Select all classes this fee structure applies to.")
    class_sections = models.ManyToManyField(ClassSectionModel, blank=True,
                                            help_text="Optional: narrow down to specific sections (e.g., JSS1 A).")

    # Auditing
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['fee', 'group'], name='unique_fee_master_combo')]
        verbose_name = "Fee Structure"
        verbose_name_plural = "Fee Structures"

    def __str__(self):
        return f"{self.fee.name} ({self.group.name})"


class TermlyFeeAmountModel(models.Model):
    """
    Sets the specific price for a fee structure for a given term.
    This allows for different prices per term.
    """
    fee_structure = models.ForeignKey(FeeMasterModel, on_delete=models.CASCADE, related_name='termly_amounts')
    term = models.ForeignKey(TermModel, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        unique_together = ['fee_structure', 'term']  # Prevent setting two prices for the same term
        ordering = ['term__order']

    def __str__(self):
        return f"{self.fee_structure} - {self.term.name}: {self.amount}"


class InvoiceModel(models.Model):
    """The parent document for a student's bill in a specific term."""

    class Status(models.TextChoices):
        UNPAID = 'unpaid', 'Unpaid'
        PARTIALLY_PAID = 'partially_paid', 'Partially Paid'
        PAID = 'paid', 'Paid'

    student = models.ForeignKey(StudentModel, on_delete=models.PROTECT, related_name='invoices')
    session = models.ForeignKey(SessionModel, on_delete=models.PROTECT)
    term = models.ForeignKey(TermModel, on_delete=models.PROTECT)

    invoice_number = models.CharField(max_length=50, unique=True, blank=True)
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNPAID)

    class Meta:
        ordering = ['-issue_date']
        unique_together = ['student', 'session',
                           'term']  # Prevent duplicate invoices for the same student in the same term
        verbose_name = "Student Invoice"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = f"INV-{self.issue_date.year}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number

    @property
    def amount_paid(self):
        """Total amount paid including direct payments and family-bound fees paid by siblings"""
        # Check if this invoice has actual payment records
        payment_total = self.payments.filter(status='confirmed').aggregate(total=Sum('amount'))['total'] or Decimal(
            '0.00')

        if payment_total > 0:
            # This invoice has actual payments - use payment records to avoid double counting
            return payment_total
        else:
            # No payments, but check if items are marked as paid (e.g., family-bound fees paid by siblings)
            item_paid_total = self.items.aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')
            return item_paid_total

    @property
    def total_amount(self):
        """Total invoice amount before discounts"""
        return self.items.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    @property
    def total_discount(self):
        """Total discount applied across all invoice items"""
        total = Decimal('0.00')
        for item in self.items.all():
            item_discounts = item.discounts_applied.aggregate(total=Sum('amount_discounted'))['total'] or Decimal(
                '0.00')
            total += item_discounts
        return total

    @property
    def amount_after_discount(self):
        """Invoice amount after applying discounts"""
        return self.total_amount - self.total_discount

    @property
    def balance(self):
        """Balance after discounts and payments"""
        return self.amount_after_discount - self.amount_paid


class InvoiceItemModel(models.Model):
    """A single line item on an invoice, representing a specific fee."""
    invoice = models.ForeignKey(InvoiceModel, on_delete=models.CASCADE, related_name='items')
    fee_master = models.ForeignKey(FeeMasterModel, on_delete=models.PROTECT)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_by_sibling = models.ForeignKey(StudentModel, on_delete=models.SET_NULL, null=True, blank=True,
                                        related_name='family_fees_covered',
                                        help_text="If this is a parent-bound fee paid by a sibling")

    @property
    def total_discount(self):
        """Total discount on this item"""
        return self.discounts_applied.aggregate(
            total=Sum('amount_discounted')
        )['total'] or Decimal('0.00')

    @property
    def amount_after_discount(self):
        """Amount after applying discount"""
        return self.amount - self.total_discount

    @property
    def balance(self):
        """Update to use discounted amount"""
        return self.amount_after_discount - self.amount_paid

    def __str__(self):
        return self.description


class FeePaymentModel(models.Model):
    """Records a single payment made by a student, applied against an invoice."""

    class PaymentMode(models.TextChoices):
        CASH = 'cash', 'Cash'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        BANK_TELLER = 'bank_teller', 'Bank Teller'
        DOLLAR_PAY = 'dollar_pay', 'Dollar Pay'
        OTHERS = 'others', 'OTHERS'

    class Currency(models.TextChoices):
        NAIRA = 'naira', 'Naira (NGN)'
        DOLLAR = 'dollar', 'Dollar (USD)'

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        FAILED = 'failed', 'Failed'

    invoice = models.ForeignKey(InvoiceModel, on_delete=models.PROTECT, related_name='payments')
    bank_account = models.ForeignKey('SchoolBankDetail', on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PaymentMode.choices)
    currency = models.CharField(max_length=20, choices=Currency.choices, default='naira')
    date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True, default='')
    description = models.TextField(blank=True, null=True, default='')
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    notes = models.TextField(blank=True, null=True)
    confirmed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        verbose_name = "Fee Payment"

    def __str__(self):
        return f"Payment of {self.amount} for {self.invoice.invoice_number}"


# ===================================================================
# Asynchronous Job Model (For Scalable Invoice Generation)
# ===================================================================

class InvoiceGenerationJob(models.Model):
    """Tracks the status of an asynchronous invoice generation task."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        IN_PROGRESS = 'in_progress', 'In Progress'
        SUCCESS = 'success', 'Success'
        FAILURE = 'failure', 'Failure'

    job_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(SessionModel, on_delete=models.CASCADE)
    term = models.ForeignKey(TermModel, on_delete=models.CASCADE)
    classes_to_invoice = models.ManyToManyField(ClassesModel)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_students = models.PositiveIntegerField(default=0)
    processed_students = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"Invoice Job for {self.session} {self.term.name}"


def get_current_session():
    setting = SchoolSettingModel.objects.first()
    return setting.session if setting and getattr(setting, "session", None) else None


def get_current_term():
    setting = SchoolSettingModel.objects.first()
    return setting.term if setting and getattr(setting, "term", None) else None




class IncomeCategoryModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = _("Income Category")
        verbose_name_plural = _("Income Categories")
        ordering = ("name",)
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return self.name


class IncomeModel(models.Model):
    category = models.ForeignKey(
        IncomeCategoryModel, on_delete=models.PROTECT, related_name="incomes"
    )
    description = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    income_date = models.DateField(default=timezone.now, db_index=True)

    source = models.CharField(max_length=100, blank=True, null=True)
    reference = models.CharField(max_length=100, blank=True, null=True)
    receipt = models.FileField(
        upload_to="finance/income/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
    )
    notes = models.TextField(blank=True, null=True)

    session = models.ForeignKey(
        SessionModel, on_delete=models.SET_NULL, null=True, blank=True, related_name="incomes"
    )
    term = models.ForeignKey(
        TermModel, on_delete=models.SET_NULL, null=True, blank=True, related_name="incomes"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_incomes"
    )

    class Meta:
        ordering = ("-income_date", "-created_at")
        indexes = [
            models.Index(fields=["income_date"]),
            models.Index(fields=["category"]),
            models.Index(fields=["session"]),
            models.Index(fields=["term"]),
        ]
        verbose_name = _("Income")
        verbose_name_plural = _("Incomes")

    def save(self, *args, **kwargs):
        if not self.session:
            self.session = get_current_session()
        if not self.term:
            self.term = get_current_term()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.description} ({self.amount})"


class ExpenseCategoryModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = _("Expense Category")
        verbose_name_plural = _("Expense Categories")
        ordering = ("name",)
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["name"]),
        ]

    def __str__(self):
        return self.name


class ExpenseModel(models.Model):
    # Payment Method Choices (Updated)
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"
    DOLLAR_PAY = "dollar_pay"
    OTHERS = "others"

    PAYMENT_METHOD_CHOICES = [
        (CASH, "Cash"),
        (CARD, "Card"),
        (TRANSFER, "Bank Transfer"),
        (DOLLAR_PAY, "Dollar Pay"),
        (OTHERS, "Others"),
    ]

    # Currency Choices
    class Currency(models.TextChoices):
        NAIRA = 'naira', 'Naira (NGN)'
        DOLLAR = 'dollar', 'Dollar (USD)'

    # Core Fields
    category = models.ForeignKey(
        ExpenseCategoryModel, on_delete=models.PROTECT, related_name="expenses"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    expense_date = models.DateField(default=timezone.now, db_index=True)

    # Payment Details
    payment_method = models.CharField(
        max_length=50, choices=PAYMENT_METHOD_CHOICES, default=CASH
    )
    currency = models.CharField(
        max_length=20, choices=Currency.choices, default=Currency.NAIRA
    )
    bank_account = models.ForeignKey(
        'SchoolBankDetail', on_delete=models.PROTECT, null=True, blank=True,
        related_name="expenses"
    )

    # Basic Info
    name = models.CharField(max_length=100, blank=True, null=True)
    reference = models.CharField(max_length=100, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    receipt = models.FileField(
        upload_to="finance/expenses/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
    )
    notes = models.TextField(blank=True, null=True)

    # Voucher Specific Fields
    voucher_number = models.CharField(max_length=50, blank=True, db_index=True)
    vote_and_subhead = models.CharField(max_length=200, blank=True, null=True)
    line_items = models.JSONField(default=list, blank=True)
    # Format: [{"date": "2024-01-15", "particular": "Item description", "amount": "5000.00"}, ...]

    # Staff Fields
    prepared_by = models.ForeignKey(
        'human_resource.StaffModel', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prepared_expenses'
    )
    authorised_by = models.ForeignKey(
        'human_resource.StaffModel', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='authorised_expenses'
    )
    collected_by = models.ForeignKey(
        'human_resource.StaffModel', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='collected_expenses'
    )

    # Cheque Details (Optional - for manual completion)
    cheque_number = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=200, blank=True, null=True)
    cheque_by = models.CharField(max_length=100, blank=True, null=True)
    cheque_prepared_date = models.DateField(blank=True, null=True)
    cheque_signed_date = models.DateField(blank=True, null=True)

    # System Fields
    session = models.ForeignKey(
        SessionModel, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )
    term = models.ForeignKey(
        TermModel, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_expenses"
    )

    class Meta:
        ordering = ("-expense_date", "-created_at")
        indexes = [
            models.Index(fields=["expense_date"]),
            models.Index(fields=["category"]),
            models.Index(fields=["session"]),
            models.Index(fields=["term"]),
            models.Index(fields=["voucher_number"]),
        ]
        verbose_name = _("Expense")
        verbose_name_plural = _("Expenses")

    def save(self, *args, **kwargs):
        # Set defaults only if not provided
        if not self.session:
            self.session = get_current_session()
        if not self.term:
            self.term = get_current_term()

        # Auto-generate voucher number from reference if blank
        if not self.voucher_number:
            if self.reference:
                self.voucher_number = self.reference
            else:
                # Generate unique voucher number
                self.voucher_number = self.generate_voucher_number()

        # Note: Don't recalculate amount here - it's already set by the form
        # The form handles line_items calculation before calling save()

        super().save(*args, **kwargs)

    def generate_voucher_number(self):
        """Generate unique voucher number with format EXP-YYYY-NNNN"""
        from django.db.models import Max
        import re

        current_year = timezone.now().year
        prefix = f"EXP-{current_year}-"

        # Get the last voucher number for this year
        last_expense = ExpenseModel.objects.filter(
            voucher_number__startswith=prefix
        ).aggregate(Max('voucher_number'))

        last_voucher = last_expense.get('voucher_number__max')

        if last_voucher:
            # Extract number from voucher like "EXP-2024-0042"
            match = re.search(r'-(\d+)$', last_voucher)
            if match:
                last_num = int(match.group(1))
                new_num = last_num + 1
            else:
                new_num = 1
        else:
            new_num = 1

        return f"{prefix}{str(new_num).zfill(4)}"

    def get_total_in_words(self):
        """Convert amount to words for voucher"""
        from num2words import num2words
        try:
            amount_str = num2words(float(self.amount), lang='en')
            currency_name = "Naira" if self.currency == self.Currency.NAIRA else "Dollars"
            return f"{amount_str.title()} {currency_name} Only"
        except:
            return f"{self.amount} Only"

    def __str__(self):
        return f"{self.category.__str__()} ({self.amount})"


class FinanceSettingModel(models.Model):
    """ A central place for finance-related settings. """
    allow_partial_payments = models.BooleanField(default=True)
    send_payment_receipt_email = models.BooleanField(default=True,
                                                     help_text="Automatically email a receipt to the parent upon payment confirmation.")

    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "General Finance Settings"


class StaffBankDetail(models.Model):
    """Stores the bank details for a single staff member."""
    staff = models.OneToOneField(StaffModel, related_name='bank_details', on_delete=models.CASCADE)
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20, unique=True)
    account_name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Bank Detail"

    def __str__(self):
        return f"{self.staff.__str__()} - {self.bank_name}"


class SchoolBankDetail(models.Model):
    """Stores the bank details for the school."""
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20, unique=True)
    account_name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Staff Bank Detail"

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"


class SalaryStructure(models.Model):
    """Defines the salary components for a single staff member."""
    staff = models.OneToOneField(StaffModel, related_name='salary_structure', on_delete=models.CASCADE)
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2)
    housing_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    transport_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    medical_allowance = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    other_allowances = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'),
                                   help_text="Percentage (e.g., 7.5)")
    pension_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'),
                                       help_text="Percentage (e.g., 8)")
    effective_from = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Salary Structure"

    @property
    def gross_salary(self):
        return (
                    self.basic_salary + self.housing_allowance + self.transport_allowance + self.medical_allowance + self.other_allowances)

    @property
    def tax_amount(self):
        return self.gross_salary * (self.tax_rate / 100)

    @property
    def pension_amount(self):
        return self.basic_salary * (self.pension_rate / 100)

    @property
    def total_deductions(self):
        return self.tax_amount + self.pension_amount

    @property
    def net_salary(self):
        return self.gross_salary - self.total_deductions

    def __str__(self):
        return f"Salary for {self.staff.staff_profile.user.get_full_name()}"


class SalaryAdvance(models.Model):
    """Tracks salary advance requests for staff."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        DISBURSED = 'disbursed', 'Disbursed'  # Now indicates an active debt
        COMPLETED = 'completed', 'Completed'  # New status for paid debts
        REJECTED = 'rejected', 'Rejected'

    staff = models.ForeignKey(StaffModel, on_delete=models.CASCADE, related_name='salary_advances')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    request_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # NEW: Field to track repayments against this specific advance
    repaid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approved_salary_advances')
    approved_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def balance(self):
        """Calculates the outstanding balance for this advance."""
        return self.amount - self.repaid_amount

    def save(self, *args, **kwargs):
        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None: self.session = setting.session
                if self.term is None: self.term = setting.term
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Salary Advance for {self.staff}"


# finance/models.py

class StaffLoan(models.Model):
    """Tracks loan requests for staff, with manual repayment."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        DISBURSED = 'disbursed', 'Disbursed'  # An active debt
        COMPLETED = 'completed', 'Completed'  # Debt fully paid
        REJECTED = 'rejected', 'Rejected'

    staff = models.ForeignKey(StaffModel, on_delete=models.CASCADE, related_name='staff_loans')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    repayment_plan = models.TextField(blank=True, null=True, help_text="e.g., How the staff intends to repay.")
    request_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    repaid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Auditing fields
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='approved_staff_loans')
    approved_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def balance(self):
        """Calculates the outstanding balance for this loan."""
        return self.amount - self.repaid_amount

    def save(self, *args, **kwargs):
        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None: self.session = setting.session
                if self.term is None: self.term = setting.term
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Loan of {self.amount} for {self.staff}"


class StaffLoanRepayment(models.Model):
    """Logs each individual repayment made by a staff member against their loans."""
    staff = models.ForeignKey(StaffModel, on_delete=models.CASCADE, related_name='loan_repayments')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)

    # Auditing
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None: self.session = setting.session
                if self.term is None: self.term = setting.term
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Loan Repayment of {self.amount_paid} for {self.staff}"


class SalaryRecord(models.Model):
    """A historical snapshot of a staff member's payslip for a specific month."""
    staff = models.ForeignKey(StaffModel, on_delete=models.PROTECT, related_name='payslips')
    month = models.PositiveIntegerField()
    year = models.PositiveIntegerField()

    # NEW: Added Session and Term fields for auditing
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)

    # Snapshot fields from SalaryStructure
    basic_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    housing_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    transport_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    medical_allowance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_allowances = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pension_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Month-specific adjustments
    bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    other_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                           help_text="e.g., salary advance repayment")
    salary_advance_deduction = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.CharField(max_length=255, blank=True, null=True)

    # Payment Tracking
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)
    paid_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = ('staff', 'month', 'year')
        ordering = ['-year', '-month']

    def save(self, *args, **kwargs):
        # Auto-populate session and term if not set
        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None: self.session = setting.session
                if self.term is None: self.term = setting.term
        super().save(*args, **kwargs)

    @property
    def gross_salary(self):
        return (
                    self.basic_salary + self.housing_allowance + self.transport_allowance + self.medical_allowance + self.other_allowances + self.bonus)

    @property
    def total_deductions(self):
        return self.tax_amount + self.pension_amount + self.salary_advance_deduction + self.other_deductions

    @property
    def net_salary(self):
        return self.gross_salary - self.total_deductions

    @property
    def balance_due(self):
        return self.net_salary - self.amount_paid

    @property
    def payment_status(self):
        if self.balance_due <= 0 and self.net_salary > 0:
            return "Paid"
        if self.amount_paid > 0:
            return "Partially Paid"
        return "Pending"

    @property
    def month_name(self):
        """Returns the full name of the month."""
        if self.month:
            return calendar.month_name[self.month]
        return ""

    def __str__(self):
        return f"Payslip for {self.staff.staff_profile.user.get_full_name()} - {self.month}/{self.year}"


class SupplierPaymentModel(models.Model):
    """Records payments made to suppliers for purchase orders."""

    class PaymentMethod(models.TextChoices):
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        CASH = 'cash', 'Cash'
        CHEQUE = 'cheque', 'Cheque'

    class PaymentStatus(models.TextChoices):
        COMPLETED = 'completed', 'Completed'
        REVERTED = 'reverted', 'Reverted'

    # What and Who
    supplier = models.ForeignKey(SupplierModel, on_delete=models.PROTECT, related_name='payments')
    purchase_orders = models.ManyToManyField(PurchaseOrderModel, blank=True)

    # Payment Details
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=50, choices=PaymentMethod.choices, default=PaymentMethod.BANK_TRANSFER)
    reference = models.CharField(max_length=100, blank=True, null=True, help_text="e.g., Cheque number, transaction ID")
    receipt_number = models.CharField(max_length=50, unique=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    # Status and Auditing
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.COMPLETED)
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['-payment_date', '-created_at']
        verbose_name = "Supplier Payment"
        verbose_name_plural = "Supplier Payments"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = f"PMT-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

        if self.session is None or self.term is None:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if self.session is None: self.session = setting.session
                if self.term is None: self.term = setting.term

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Payment of {self.amount} to {self.supplier.name}"


class PurchaseAdvancePaymentModel(models.Model):
    """Track payments made to staff for purchase advances"""

    advance = models.ForeignKey(PurchaseAdvanceModel, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=50, default='cash',
                                      choices=[('cash', 'Cash'), ('bank_transfer', 'Bank Transfer'),
                                               ('cheque', 'Cheque')])
    reference = models.CharField(max_length=100, blank=True, null=True)
    voucher_number = models.CharField(max_length=50, unique=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.voucher_number:
            self.voucher_number = f"PAY-{timezone.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

        # Update advance disbursed amount
        total_paid = self.advance.payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        self.advance.disbursed_amount = total_paid
        if total_paid >= self.advance.approved_amount:
            self.advance.status = 'disbursed'
        self.advance.save()

    def __str__(self):
        return f"Payment to {self.advance.staff} - ₦{self.amount}"


class AdvanceSettlementModel(models.Model):
    """Records settlement of purchase advances"""

    advance = models.ForeignKey(PurchaseAdvanceModel, on_delete=models.CASCADE, related_name='settlements')
    settlement_type = models.CharField(max_length=20, choices=[
        ('refund', 'Refund to Staff'),
        ('payment', 'Payment by Staff')
    ])
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    settlement_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=50, default='cash')
    reference = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.settlement_type.title()} - {self.advance.staff} - ₦{self.amount}"


class DiscountModel(models.Model):
    """The blueprint for a discount (Identity and Scope)."""

    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage (%)'
        FIXED = 'fixed', 'Fixed Amount ($)'

    class DiscountOccurrence(models.TextChoices):
        TERMLY = 'quaterly', 'Quaterly'
        ANNUALLY = 'annually', 'Annually'
        ONE_TIME = 'one_time', 'One Time (Single Term)'

    title = models.CharField(max_length=250, unique=True, help_text="e.g., Staff Discount, Early Bird Discount")

    # The current, intended type. This is used to default the DiscountApplicationModel.
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices,
                                     help_text="The intended type for this discount blueprint.")

    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True,
                                 help_text="Default value (amount/percentage) for initial application setup.")

    occurrence = models.CharField(max_length=50, choices=DiscountOccurrence.choices)

    applicable_fees = models.ManyToManyField('FeeModel', help_text="Fees this discount can be applied against.",
                                             blank=True)
    applicable_classes = models.ManyToManyField(ClassesModel, help_text="Classes this discount can apply to.",
                                                blank=True, related_name='applicable_classes')

    # Deletion Protection: If any application record exists, this blueprint cannot be deleted.
    is_protected = models.BooleanField(default=False, editable=False)

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']
        verbose_name = "Discount Blueprint"

    def __str__(self):
        return self.title.upper()


class DiscountApplicationModel(models.Model):
    """
    Locks the rate and type for a specific Session and Term.
    Session and Term are optional, defaulting to the SchoolSettingModel's active term.
    """

    DiscountType = DiscountModel.DiscountType

    discount = models.ForeignKey('DiscountModel', on_delete=models.PROTECT, related_name='applications')

    # UPDATED: Session and Term are now optional (null=True, blank=True)
    session = models.ForeignKey(SessionModel, on_delete=models.PROTECT, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.PROTECT, null=True, blank=True)

    discount_type = models.CharField(max_length=20, choices=DiscountType.choices,
                                     help_text="The type of discount (Percentage or Fixed) locked for this term.")

    discount_amount = models.DecimalField(max_digits=10, decimal_places=2,
                                          help_text="The exact amount or percentage locked for this term.")

    is_protected = models.BooleanField(default=False, editable=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # NOTE: The unique_together constraint must be dropped or modified because
        # allowing nulls means multiple records can have (discount, null, null).
        # We will enforce the uniqueness of (discount, session, term) with a clean method.
        # We will keep unique_together for non-null values for database integrity.
        unique_together = ['discount', 'session', 'term']
        ordering = ['-session__id', 'term__order']
        verbose_name = "Discount Application"

    def __str__(self):
        session_name = self.session.__str__() if self.session else 'Global'
        term_name = self.term.name if self.term else 'Current'
        return f"{self.discount.title} ({session_name} - {term_name})"

    # Custom logic to handle defaulting and unique constraint for nulls
    def clean(self):
        # Enforce that if one is set, both must be set (cannot have session=X, term=None)
        if (self.session and not self.term) or (not self.session and self.term):
            raise ValidationError("Session and Term must either both be set, or both be left blank.")

        # Enforce uniqueness for the 'Global' application (when both are null)
        if self.session is None and self.term is None:
            if DiscountApplicationModel.objects.filter(
                    discount=self.discount, session__isnull=True, term__isnull=True
            ).exclude(pk=self.pk).exists():
                raise ValidationError("A Global (Current Session/Term) application already exists for this discount.")

    def save(self, *args, **kwargs):
        # 1. New Record Logic: Inherit Type and Protect Blueprint
        if not self.pk:
            # Inherit the current type from the blueprint on creation
            self.discount_type = self.discount.discount_type

            # Protect the blueprint
            if not self.discount.is_protected:
                self.discount.is_protected = True
                self.discount.save(update_fields=['is_protected'])

        # 2. Defaulting Logic: Pull active session/term from SchoolSettingModel if not set
        if self.session is None and self.term is None:
            try:
                # Assuming SchoolSettingModel is a singleton (has only one record)
                settings = SchoolSettingModel.objects.first()
                if settings.session and settings.term:
                    self.session = settings.session
                    self.term = settings.term
            except SchoolSettingModel.DoesNotExist:
                # If no settings exist, it saves with nulls, handled by the unique constraint check
                pass
            except SchoolSettingModel.MultipleObjectsReturned:
                # Should not happen if it's a singleton, but good practice to catch
                pass

        # 3. Existing Record Logic: Lock Type for historical safety
        # ... (The logic to prevent changing self.discount_type remains the same) ...
        if self.pk:
            original = DiscountApplicationModel.objects.get(pk=self.pk)
            if original.discount_type != self.discount_type:
                self.discount_type = original.discount_type  # Revert the change

        super().save(*args, **kwargs)


class StudentDiscountModel(models.Model):
    """The transactional record of a discount being applied to a student's invoice."""

    student = models.ForeignKey(StudentModel, on_delete=models.PROTECT, related_name='discounts_received')

    # Links to the locked rate and type (DiscountApplicationModel)
    discount_application = models.ForeignKey(DiscountApplicationModel, on_delete=models.PROTECT,
                                             related_name='student_discounts')

    # Links to the final billing document
    invoice_item = models.ForeignKey('InvoiceItemModel', on_delete=models.PROTECT, null=True,
                                     related_name='discounts_applied')
    # The final calculated monetary amount discounted on this specific invoice.
    amount_discounted = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # A student can only receive a specific discount application once per invoice
        unique_together = ['student', 'discount_application', 'invoice_item']
        verbose_name = "Student Discount Record"

    def __str__(self):
        return f"{self.student.first_name} received ₦{self.amount_discounted} discount on {self.invoice_item.description}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Ensure the application model is protected once a student record exists
        if not self.discount_application.is_protected:
            self.discount_application.is_protected = True
            self.discount_application.save(update_fields=['is_protected'])

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        # If this was the last student record for the application, unprotect it
        if not self.discount_application.student_discounts.exists():
            self.discount_application.is_protected = False
            self.discount_application.save(update_fields=['is_protected'])