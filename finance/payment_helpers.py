import json
import re
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
import uuid
from human_resource.models import StaffWalletModel
from student.models import StudentWalletModel
from .models import (
    FeePaymentModel,
    StudentFundingModel,
    StaffFundingModel,
    InvoiceModel,
    InvoiceItemModel
)
from .emails import (
    send_fee_payment_confirmation_email,
    send_student_funding_confirmation_email,
    send_staff_funding_confirmation_email,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# SHARED INTERNAL UTILITIES
# ==============================================================================

def _get_unpaid_items(invoice):
    """
    Fetch invoice items with a remaining balance, accounting for discounts
    and sibling payments via the .balance property.
    """
    candidates = invoice.items.select_related(
        'fee_master__fee', 'paid_by_sibling'
    ).prefetch_related('discounts_applied').filter(
        amount_paid__lt=F('amount')
    ).order_by('id')
    return [item for item in candidates if item.balance > Decimal('0.01')]


def _apply_sibling_logic(item, invoice):
    """
    If the fee is parent-bound and this item is now fully paid,
    propagate the payment to the same fee item on all sibling invoices.
    """
    if item.fee_master.fee.parent_bound and item.amount_paid >= item.amount_after_discount:
        student = invoice.student
        if student.parent:
            for sibling in student.parent.wards.exclude(pk=student.pk):
                try:
                    sibling_invoice = InvoiceModel.objects.get(
                        student=sibling,
                        session=invoice.session,
                        term=invoice.term,
                    )
                    sibling_item = InvoiceItemModel.objects.get(
                        invoice=sibling_invoice,
                        fee_master=item.fee_master,
                    )
                    sibling_item.paid_by_sibling = student
                    sibling_item.amount_paid = sibling_item.amount_after_discount
                    sibling_item.save(update_fields=['paid_by_sibling', 'amount_paid'])
                except (InvoiceModel.DoesNotExist, InvoiceItemModel.DoesNotExist):
                    continue


def _parse_parent_allocations(notes: str) -> dict:
    """
    Extract the item allocation JSON that was embedded in payment notes
    at submission time (both teller upload and online payment store it
    in the same format).

    Returns a dict of {item_id_str: {'description': ..., 'amount': ...}}
    or an empty dict if none found.
    """
    if not notes:
        return {}
    try:
        match = re.search(
            r'Item Allocations:\s*(\{.*?\})',
            notes,
            re.DOTALL
        )
        if match:
            return json.loads(match.group(1))
    except (json.JSONDecodeError, AttributeError):
        pass
    return {}


# ==============================================================================
# CORE CONFIRMATION HELPERS
# ==============================================================================

@transaction.atomic
def do_confirm_fee_payment(payment: FeePaymentModel, override_allocation: bool = False) -> None:
    """
    Confirm a pending FeePaymentModel and allocate the amount across
    invoice items. Replicates the full logic of confirm_fee_payment_view.

    Raises ValueError if the payment is not in PENDING status.
    Must be called inside a transaction (wraps itself atomically as well
    for safety when called from the webhook).
    """
    if payment.status != FeePaymentModel.PaymentStatus.PENDING:
        raise ValueError(
            f"Payment {payment.pk} is not pending (status={payment.status}). Cannot confirm."
        )

    item_breakdown = {}
    invoice = payment.invoice
    amount_to_allocate = payment.amount

    parent_allocations = _parse_parent_allocations(payment.notes)

    if parent_allocations and not override_allocation:
        # --- Honour the parent's itemized selections ---
        for item_id_str, allocation_data in parent_allocations.items():
            try:
                item_id = int(item_id_str)
                allocated_amount = Decimal(str(allocation_data['amount']))
                item = InvoiceItemModel.objects.prefetch_related(
                    'discounts_applied'
                ).get(pk=item_id, invoice=invoice)

                payable = min(item.balance, allocated_amount)
                item.amount_paid += payable
                item.save(update_fields=['amount_paid'])
                amount_to_allocate -= payable
                item_breakdown[str(item.pk)] = str(payable)
                _apply_sibling_logic(item, invoice)

            except (ValueError, InvoiceItemModel.DoesNotExist):
                continue

        # Distribute any leftover (e.g. parent over-specified or rounding)
        if amount_to_allocate > Decimal('0.01'):
            for item in _get_unpaid_items(invoice):
                if amount_to_allocate <= Decimal('0'):
                    break
                payable = min(item.balance, amount_to_allocate)
                item.amount_paid += payable
                item.save(update_fields=['amount_paid'])
                amount_to_allocate -= payable
                current = Decimal(item_breakdown.get(str(item.pk), '0'))
                item_breakdown[str(item.pk)] = str(current + payable)

    else:
        # --- Auto-distribute across unpaid items in order ---
        for item in _get_unpaid_items(invoice):
            if amount_to_allocate <= Decimal('0'):
                break
            payable = min(item.balance, amount_to_allocate)
            item.amount_paid += payable
            item.save(update_fields=['amount_paid'])
            amount_to_allocate -= payable
            item_breakdown[str(item.pk)] = str(payable)
            _apply_sibling_logic(item, invoice)

    # Update payment record
    payment.status = FeePaymentModel.PaymentStatus.CONFIRMED
    payment.item_breakdown = item_breakdown
    payment.save(update_fields=['status', 'item_breakdown', 'confirmed_by'])

    # Update invoice status
    invoice.refresh_from_db()
    if invoice.balance <= Decimal('0.01'):
        invoice.status = InvoiceModel.Status.PAID
    else:
        invoice.status = InvoiceModel.Status.PARTIALLY_PAID
    invoice.save(update_fields=['status'])

    send_fee_payment_confirmation_email(payment)

    logger.info(
        f"FeePayment {payment.pk} confirmed. "
        f"Invoice {invoice.invoice_number} status → {invoice.status}."
    )


@transaction.atomic
def do_confirm_student_funding(payment: StudentFundingModel) -> None:
    """
    Confirm a pending StudentFundingModel and credit the appropriate wallet.
    Replicates the full logic of confirm_payment_view.

    Raises ValueError if the payment is not in PENDING status.
    """
    if payment.status != StudentFundingModel.PaymentStatus.PENDING:
        raise ValueError(
            f"StudentFunding {payment.pk} is not pending (status={payment.status}). Cannot confirm."
        )

    student = payment.student
    student_wallet, _ = StudentWalletModel.objects.get_or_create(student=student)
    wallet_type = payment.wallet_type

    if wallet_type == StudentFundingModel.WalletType.CANTEEN:
        student_wallet.balance += payment.amount
        # Offset any existing debt
        if student_wallet.debt > 0:
            if student_wallet.balance >= student_wallet.debt:
                student_wallet.balance -= student_wallet.debt
                student_wallet.debt = Decimal('0.00')
            else:
                student_wallet.debt -= student_wallet.balance
                student_wallet.balance = Decimal('0.00')
    else:
        # Fee wallet
        student_wallet.fee_balance += payment.amount

    student_wallet.save()

    payment.status = StudentFundingModel.PaymentStatus.CONFIRMED
    payment.save(update_fields=['status'])

    send_student_funding_confirmation_email(payment)

    logger.info(
        f"StudentFunding {payment.pk} confirmed for student {student}. "
        f"Wallet type: {wallet_type}."
    )


@transaction.atomic
def do_confirm_staff_funding(payment: StaffFundingModel) -> None:
    """
    Confirm a pending StaffFundingModel and credit the staff wallet.
    Replicates the full logic of staff_confirm_payment_view.

    Raises ValueError if the payment is not in PENDING status.
    """
    if payment.status != StaffFundingModel.PaymentStatus.PENDING:
        raise ValueError(
            f"StaffFunding {payment.pk} is not pending (status={payment.status}). Cannot confirm."
        )

    staff = payment.staff
    staff_wallet, _ = StaffWalletModel.objects.get_or_create(staff=staff)
    staff_wallet.balance += payment.amount
    staff_wallet.save()

    payment.status = StaffFundingModel.PaymentStatus.CONFIRMED
    payment.save(update_fields=['status'])

    send_staff_funding_confirmation_email(payment)

    logger.info(
        f"StaffFunding {payment.pk} confirmed for staff {staff}."
    )


def generate_payment_reference(prefix: str = 'PAY') -> str:
    """
    Generate a unique payment reference.
    Format: PAY-<uppercase uuid4 first 16 chars>
    e.g. PAY-3F6A1B2C4D5E6F7A
    """
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"

