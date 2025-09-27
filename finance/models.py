import logging
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
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




# ===================================================================
# Fee Structure Setup Models (The "Price List")
# ===================================================================

class FeeModel(models.Model):
    """Defines a single type of fee (e.g., Tuition, PTA Levy, Bus Fee)."""

    class FeeOccurrence(models.TextChoices):
        TERMLY = 'termly', 'Termly'
        ANNUALLY = 'annually', 'Annually'
        ONE_TIME = 'one_time', 'One Time'

    name = models.CharField(max_length=250, unique=True)
    code = models.CharField(max_length=100, unique=True, help_text="A unique code for this fee, e.g., TUI-001.")
    description = models.TextField(blank=True, null=True)
    occurrence = models.CharField(max_length=50, choices=FeeOccurrence.choices)
    payment_term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True,
                                     help_text="For 'One Time' fees, specify which term it must be paid in.")
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


# --- NEW SUPPORTING MODEL ---
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


# ===================================================================
# Invoicing and Payment Models (The "Bills" and "Payments")
# ===================================================================

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
    def total_amount(self):
        return self.items.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    @property
    def amount_paid(self):
        return self.payments.filter(status='confirmed').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    @property
    def balance(self):
        return self.total_amount - self.amount_paid


class InvoiceItemModel(models.Model):
    """A single line item on an invoice, representing a specific fee."""
    invoice = models.ForeignKey(InvoiceModel, on_delete=models.CASCADE, related_name='items')
    fee_master = models.ForeignKey(FeeMasterModel, on_delete=models.PROTECT)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    @property
    def balance(self):
        return self.amount - self.amount_paid

    def __str__(self):
        return self.description


class FeePaymentModel(models.Model):
    """Records a single payment made by a student, applied against an invoice."""

    class PaymentMode(models.TextChoices):
        CASH = 'cash', 'Cash'
        BANK_TRANSFER = 'bank_transfer', 'Bank Transfer'
        # ... other choices ...

    class PaymentStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        FAILED = 'failed', 'Failed'

    invoice = models.ForeignKey(InvoiceModel, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=20, choices=PaymentMode.choices)
    date = models.DateField(default=timezone.now)
    reference = models.CharField(max_length=100, blank=True, default='')
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


class ExpenseModel(models.Model):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"
    PAYMENT_METHOD_CHOICES = [
        (CASH, "Cash"),
        (CARD, "Card"),
        (TRANSFER, "Bank Transfer"),
    ]

    category = models.ForeignKey(
        ExpenseCategoryModel, on_delete=models.PROTECT, related_name="expenses"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    expense_date = models.DateField(default=timezone.now, db_index=True)

    payment_method = models.CharField(
        max_length=50, choices=PAYMENT_METHOD_CHOICES, default=CASH
    )
    reference = models.CharField(max_length=100, blank=True, null=True)
    receipt = models.FileField(
        upload_to="finance/expenses/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"])],
    )
    notes = models.TextField(blank=True, null=True)

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
        ]
        verbose_name = _("Expense")
        verbose_name_plural = _("Expenses")

    def save(self, *args, **kwargs):
        # set defaults only if not provided
        if not self.session:
            self.session = get_current_session()
        if not self.term:
            self.term = get_current_term()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.__str__()} ({self.amount})"


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
        return f"{self.staff.staff_profile.user.get_full_name()} - {self.bank_name}"


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
        DISBURSED = 'disbursed', 'Disbursed (Owing)'  # Now indicates an active debt
        COMPLETED = 'completed', 'Completed (Paid Off)'  # New status for paid debts
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


# NEW: Model to record every single repayment transaction
class SalaryAdvanceRepayment(models.Model):
    """Logs each individual repayment made by a staff member."""
    staff = models.ForeignKey(StaffModel, on_delete=models.CASCADE, related_name='salary_repayments')
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
        return f"Repayment of {self.amount_paid} for {self.staff}"


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
        return self.tax_amount + self.pension_amount + self.other_deductions

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