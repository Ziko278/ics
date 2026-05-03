# finance/emails.py

import logging
from decimal import Decimal

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _get_school_info():
    """Safely fetch school info for email context."""
    try:
        from admin_site.models import SchoolInfoModel
        return SchoolInfoModel.objects.first()
    except Exception:
        return None


def _get_from_email(school_info=None):
    """
    Build a friendly from email using the school name.
    e.g. 'International Community School <icsportalengine5@gmail.com>'
    """
    if school_info and school_info.name:
        raw = settings.DEFAULT_FROM_EMAIL
        # Extract just the email address part
        if '<' in raw:
            address = raw.split('<')[1].rstrip('>')
        else:
            address = raw
        return f"{school_info.name} <{address}>"
    return settings.DEFAULT_FROM_EMAIL


def _get_logo_url(school_info, request=None):
    """Safely get an absolute logo URL."""
    if not school_info or not school_info.logo:
        return None
    try:
        if request:
            return request.build_absolute_uri(school_info.logo.url)
        return school_info.logo.url
    except Exception:
        return None


# ==============================================================================
# FEE PAYMENT CONFIRMATION EMAIL
# ==============================================================================

def send_fee_payment_confirmation_email(payment, request=None):
    """
    Send a payment confirmation email after a FeePaymentModel is confirmed.
    Works for both online and offline payments.
    """
    try:
        invoice  = payment.invoice
        student  = invoice.student
        school   = _get_school_info()

        # Resolve recipient email
        recipient = None
        try:
            if student.parent and student.parent.user:
                recipient = student.parent.user.email
        except Exception:
            pass

        if not recipient:
            logger.warning(
                f"No recipient email for fee payment {payment.pk}. Skipping."
            )
            return False

        # Build item breakdown if available
        item_breakdown = []
        if payment.item_breakdown:
            for item_id, amount_paid in payment.item_breakdown.items():
                try:
                    from .models import InvoiceItemModel
                    item = invoice.items.get(pk=item_id)
                    item_breakdown.append({
                        'description': item.description,
                        'amount_paid': Decimal(str(amount_paid)),
                    })
                except Exception:
                    continue

        context = {
            'student_name':     f"{student.first_name} {student.last_name}",
            'invoice_number':   invoice.invoice_number,
            'session':          str(invoice.session),
            'term':             str(invoice.term),
            'amount':           payment.amount,
            'payment_mode':     payment.get_payment_mode_display(),
            'reference':        payment.reference or '—',
            'payment_date':     payment.created_at,
            'invoice_balance':  invoice.balance,
            'invoice_status':   invoice.get_status_display(),
            'item_breakdown':   item_breakdown,
            'school':           school,
            'logo_url':         _get_logo_url(school, request),
        }

        html_content = render_to_string(
            'finance/email/fee_payment_confirmation.html',
            context
        )
        recipients = [recipient]
        if school and school.email and school.email != recipient:
            recipients.append(school.email)

        send_mail(
            subject=f"Fee Payment Confirmed — {invoice.invoice_number}",
            message=(
                f"Dear Parent,\n\n"
                f"A payment of ₦{payment.amount:,.2f} for {student.first_name} "
                f"{student.last_name} has been confirmed.\n\n"
                f"Invoice: {invoice.invoice_number}\n"
                f"Reference: {payment.reference or '—'}\n\n"
                f"Thank you."
            ),
            from_email=_get_from_email(school),
            recipient_list=recipients,
            fail_silently=False,
            html_message=html_content,
        )

        logger.info(
            f"Fee payment confirmation email sent to {recipient} "
            f"for payment {payment.pk}."
        )
        return True

    except Exception:
        logger.exception(
            f"Failed to send fee payment confirmation email for payment {payment.pk}."
        )
        return False


# ==============================================================================
# STUDENT WALLET FUNDING CONFIRMATION EMAIL
# ==============================================================================

def send_student_funding_confirmation_email(funding, request=None):
    """
    Send a wallet funding confirmation email after a StudentFundingModel is confirmed.
    Works for both online and offline funding.
    """
    try:
        student = funding.student
        school  = _get_school_info()

        # Resolve recipient
        recipient = None
        try:
            if student.parent and student.parent.user:
                recipient = student.parent.user.email
        except Exception:
            pass

        if not recipient:
            logger.warning(
                f"No recipient email for student funding {funding.pk}. Skipping."
            )
            return False

        # Get updated wallet balance
        wallet_balance = None
        wallet_fee_balance = None
        try:
            from .models import StudentWalletModel
            wallet = StudentWalletModel.objects.get(student=student)
            wallet_balance     = wallet.balance
            wallet_fee_balance = wallet.fee_balance
        except Exception:
            pass

        context = {
            'student_name':     f"{student.first_name} {student.last_name}",
            'wallet_type':      funding.get_wallet_type_display(),
            'amount':           funding.amount,
            'method':           funding.get_method_display(),
            'reference':        funding.reference or funding.teller_number or '—',
            'funding_date':     funding.created_at,
            'session':          str(funding.session) if funding.session else '—',
            'term':             str(funding.term) if funding.term else '—',
            'wallet_balance':   wallet_balance,
            'wallet_fee_balance': wallet_fee_balance,
            'school':           school,
            'logo_url':         _get_logo_url(school, request),
        }

        html_content = render_to_string(
            'finance/email/student_funding_confirmation.html',
            context
        )

        recipients = [recipient]
        if school and school.email and school.email != recipient:
            recipients.append(school.email)

        send_mail(
            subject=f"Wallet Funding Confirmed — {student.first_name} {student.last_name}",
            message=(
                f"Dear Parent,\n\n"
                f"A wallet funding of ₦{funding.amount:,.2f} for "
                f"{student.first_name} {student.last_name} has been confirmed.\n\n"
                f"Wallet: {funding.get_wallet_type_display()}\n"
                f"Reference: {funding.reference or '—'}\n\n"
                f"Thank you."
            ),
            from_email=_get_from_email(school),
            recipient_list=recipients,
            fail_silently=False,
            html_message=html_content,
        )

        logger.info(
            f"Student funding confirmation email sent to {recipient} "
            f"for funding {funding.pk}."
        )
        return True

    except Exception:
        logger.exception(
            f"Failed to send student funding confirmation email for funding {funding.pk}."
        )
        return False


# ==============================================================================
# STAFF WALLET FUNDING CONFIRMATION EMAIL
# ==============================================================================

def send_staff_funding_confirmation_email(funding, request=None):
    """
    Send a wallet funding confirmation email after a StaffFundingModel is confirmed.
    """
    try:
        staff  = funding.staff
        school = _get_school_info()

        # Resolve recipient
        recipient = staff.email or ''
        if not recipient:
            try:
                recipient = staff.staff_profile.user.email or ''
            except Exception:
                pass

        if not recipient:
            logger.warning(
                f"No recipient email for staff funding {funding.pk}. Skipping."
            )
            return False

        # Get updated wallet balance
        wallet_balance = None
        try:
            from .models import StaffWalletModel
            wallet         = StaffWalletModel.objects.get(staff=staff)
            wallet_balance = wallet.balance
        except Exception:
            pass

        context = {
            'staff_name':     f"{staff.first_name} {staff.last_name}",
            'amount':         funding.amount,
            'method':         funding.get_method_display(),
            'reference':      funding.reference or funding.teller_number or '—',
            'funding_date':   funding.created_at,
            'session':        str(funding.session) if funding.session else '—',
            'term':           str(funding.term) if funding.term else '—',
            'wallet_balance': wallet_balance,
            'school':         school,
            'logo_url':       _get_logo_url(school, request),
        }

        html_content = render_to_string(
            'finance/email/staff_funding_confirmation.html',
            context
        )
        recipients = [recipient]
        if school and school.email and school.email != recipient:
            recipients.append(school.email)
        send_mail(
            subject="Wallet Funding Confirmed",
            message=(
                f"Dear {staff.first_name},\n\n"
                f"Your wallet funding of ₦{funding.amount:,.2f} has been confirmed.\n\n"
                f"Reference: {funding.reference or '—'}\n\n"
                f"Thank you."
            ),
            from_email=_get_from_email(school),
            recipient_list=recipients,
            fail_silently=False,
            html_message=html_content,
        )

        logger.info(
            f"Staff funding confirmation email sent to {recipient} "
            f"for funding {funding.pk}."
        )
        return True

    except Exception:
        logger.exception(
            f"Failed to send staff funding confirmation email for funding {funding.pk}."
        )
        return False