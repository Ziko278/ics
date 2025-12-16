from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
import logging

from .models import (
    InvoiceGenerationJob, InvoiceModel, InvoiceItemModel,
    DiscountModel, DiscountApplicationModel, StudentDiscountModel
)
from student.models import StudentModel
from finance.models import FeeMasterModel

logger = logging.getLogger(__name__)


@shared_task
def generate_invoices_task(job_id):
    """
    This is the Celery background task that performs the heavy lifting
    of generating invoices for a large number of students.
    Now includes automatic discount generation based on student's previous discounts.
    Updated to handle fee occurrence types: TERMLY, ANNUALLY, ONE_TIME
    """
    VERSION_CHECK = "VERSION_2024_12_16_FEE_OCCURRENCE_V1"
    logger.info(f"Starting invoice generation task - {VERSION_CHECK}")

    job = None
    students_processed = 0

    try:
        # 1. Get the job record from the database
        job = InvoiceGenerationJob.objects.get(pk=job_id)
        job.status = InvoiceGenerationJob.Status.IN_PROGRESS
        job.save()

        # 2. Find all students in the classes selected for this job
        students_to_invoice = StudentModel.objects.filter(
            student_class__in=job.classes_to_invoice.all(),
            status='active'
        ).select_related('student_class').prefetch_related('utilities')

        job.total_students = students_to_invoice.count()
        job.save(update_fields=['total_students'])

        # 3. Find all fee structures that apply to the selected classes
        applicable_fees = FeeMasterModel.objects.filter(
            student_classes__in=job.classes_to_invoice.all()
        ).select_related('fee', 'group').prefetch_related(
            'student_classes', 'termly_amounts'
        ).distinct()

        # 4. Loop through each student and generate their invoice(s)
        for i, student in enumerate(students_to_invoice):
            students_processed = i + 1

            # Filter the fees that apply to this specific student's class AND utilities
            student_utility_ids = set(student.utilities.values_list('id', flat=True))

            applicable_fees_for_student = [
                f for f in applicable_fees
                if student.student_class in f.student_classes.all()
                   and (f.fee.required_utility_id is None or f.fee.required_utility_id in student_utility_ids)
            ]

            # Create ONE invoice per student per term/session
            with transaction.atomic():
                # Get or create the invoice for this student/session/term
                invoice, created = InvoiceModel.objects.get_or_create(
                    student=student,
                    session=job.session,
                    term=job.term,
                    defaults={
                        'due_date': timezone.now().date(),
                        'status': 'unpaid',
                    }
                )

                # Add all applicable fees as line items
                for fee_master in applicable_fees_for_student:
                    # Get the amount for the correct term
                    termly_amount = None
                    for ta in fee_master.termly_amounts.all():
                        if ta.term_id == job.term_id:
                            termly_amount = ta
                            break

                    amount = termly_amount.amount if termly_amount else Decimal('0.00')

                    # Skip fees with zero amount
                    if amount <= 0:
                        continue

                    # ==================== FEE OCCURRENCE LOGIC ====================
                    fee_occurrence = fee_master.fee.occurrence

                    # Handle ONE_TIME fees
                    if fee_occurrence == 'one_time':
                        # Check if this is the designated payment term
                        if fee_master.fee.payment_term_id != job.term_id:
                            logger.debug(f"Skipping ONE_TIME fee {fee_master.fee.name} - not the payment term")
                            continue

                        # Check if this fee has EVER been created for this student before
                        one_time_exists = InvoiceItemModel.objects.filter(
                            invoice__student=student,
                            fee_master=fee_master
                        ).exists()

                        if one_time_exists:
                            logger.debug(
                                f"Skipping ONE_TIME fee {fee_master.fee.name} - already exists for student {student.id}")
                            continue

                    # Handle ANNUALLY fees
                    elif fee_occurrence == 'annually':
                        # Check if this is the designated payment term
                        if fee_master.fee.payment_term_id != job.term_id:
                            logger.debug(f"Skipping ANNUALLY fee {fee_master.fee.name} - not the payment term")
                            continue

                        # Check if this fee has been created in the CURRENT SESSION
                        annually_exists = InvoiceItemModel.objects.filter(
                            invoice__student=student,
                            invoice__session=job.session,
                            fee_master=fee_master
                        ).exists()

                        if annually_exists:
                            logger.debug(
                                f"Skipping ANNUALLY fee {fee_master.fee.name} - already exists for student {student.id} in session {job.session}")
                            continue

                    # TERMLY fees - always process (no special logic needed)
                    # =============================================================

                    # Check if this fee item already exists on the invoice
                    existing_item = InvoiceItemModel.objects.filter(
                        invoice=invoice,
                        fee_master=fee_master
                    ).first()

                    if not existing_item:
                        # Add the fee as a line item
                        InvoiceItemModel.objects.create(
                            invoice=invoice,
                            fee_master=fee_master,
                            description=f"{fee_master.fee.name} - {fee_master.group.name}",
                            amount=amount
                        )
                        logger.info(
                            f"Created {fee_occurrence} fee item: {fee_master.fee.name} for student {student.id}")

                # ==================== AUTO DISCOUNT GENERATION ====================
                try:
                    _apply_student_discounts(student, invoice, job)
                except Exception as e:
                    logger.error(f"Error applying discounts for student {student.id}: {str(e)}")
                    # Continue processing other students even if discount fails
                # =================================================================

            # 5. Update the progress after each student is processed
            job.processed_students = students_processed
            job.save(update_fields=['processed_students'])

        # 6. Mark the job as successful
        job.status = InvoiceGenerationJob.Status.SUCCESS
        job.error_message = ""

    except Exception as e:
        # 7. If any error occurs, mark the job as failed and record the error
        if job:
            job.status = InvoiceGenerationJob.Status.FAILURE
            job.error_message = f"[{VERSION_CHECK}] Error after {students_processed} students: {str(e)}"
            logger.exception(f"Invoice generation failed for job {job_id}")

    finally:
        # 8. Always set the completion time
        if job:
            job.completed_at = timezone.now()
            job.save()


def _apply_student_discounts(student, invoice, job):
    """
    Automatically apply discounts to a student's invoice based on their previous discount history.
    Handles TERMLY and ANNUALLY occurrences, with smart class progression detection.
    """

    # Get student's previous discount records, grouped by occurrence
    previous_discounts = StudentDiscountModel.objects.filter(
        student=student
    ).select_related(
        'discount_application__discount',
        'discount_application__session',
        'discount_application__term',
        'invoice_item__invoice'
    ).order_by('-created_at')

    # Separate by occurrence type to avoid conflicts
    termly_discounts = previous_discounts.filter(
        discount_application__discount__occurrence=DiscountModel.DiscountOccurrence.TERMLY
    )

    annually_discounts = previous_discounts.filter(
        discount_application__discount__occurrence=DiscountModel.DiscountOccurrence.ANNUALLY
    )

    # Track which discount blueprints we've already processed to avoid duplicates
    processed_discount_ids = set()

    # Process TERMLY discounts
    for prev_discount in termly_discounts:
        discount_blueprint = prev_discount.discount_application.discount

        # Skip if already processed this blueprint
        if discount_blueprint.id in processed_discount_ids:
            continue

        # Check if discount already exists for current term
        if StudentDiscountModel.objects.filter(
                student=student,
                discount_application__discount=discount_blueprint,
                invoice_item__invoice__term=job.term,
                invoice_item__invoice__session=job.session
        ).exists():
            processed_discount_ids.add(discount_blueprint.id)
            continue

        # Try to apply this discount or find alternative
        if _process_discount_for_student(
                student, invoice, job, discount_blueprint, processed_discount_ids
        ):
            processed_discount_ids.add(discount_blueprint.id)

    # Process ANNUALLY discounts
    for prev_discount in annually_discounts:
        discount_blueprint = prev_discount.discount_application.discount

        # Skip if already processed this blueprint
        if discount_blueprint.id in processed_discount_ids:
            continue

        # Check if discount already exists for current session (any term)
        if StudentDiscountModel.objects.filter(
                student=student,
                discount_application__discount=discount_blueprint,
                invoice_item__invoice__session=job.session
        ).exists():
            processed_discount_ids.add(discount_blueprint.id)
            continue

        # Try to apply this discount or find alternative
        if _process_discount_for_student(
                student, invoice, job, discount_blueprint, processed_discount_ids
        ):
            processed_discount_ids.add(discount_blueprint.id)


def _process_discount_for_student(student, invoice, job, discount_blueprint, processed_ids):
    """
    Process a single discount for a student. Handles class eligibility checks
    and finds alternative discounts if student's class has changed.

    Returns True if discount was successfully applied, False otherwise.
    """

    # Skip if discount has no applicable fees configured
    if not discount_blueprint.applicable_fees.exists():
        logger.warning(f"Discount {discount_blueprint.id} has no applicable fees configured")
        return False

    # Skip if discount has no applicable classes configured
    if not discount_blueprint.applicable_classes.exists():
        logger.warning(f"Discount {discount_blueprint.id} has no applicable classes configured")
        return False

    # Check if student's current class is eligible
    if student.student_class in discount_blueprint.applicable_classes.all():
        # Student's class is still eligible - apply this discount
        return _apply_discount_to_invoice(student, invoice, job, discount_blueprint)

    else:
        # Student's class is no longer eligible - search for alternative discount
        logger.info(f"Student {student.id} class changed, searching for alternative discount")

        # Get the fees this discount applies to
        applicable_fees = discount_blueprint.applicable_fees.all()

        # Search for alternative discounts that:
        # 1. Apply to the same fees (or overlapping fees)
        # 2. Include student's current class
        # 3. Have the same occurrence type
        # 4. Haven't been processed yet
        alternative_discounts = DiscountModel.objects.filter(
            applicable_fees__in=applicable_fees,
            applicable_classes=student.student_class,
            occurrence=discount_blueprint.occurrence
        ).exclude(
            id__in=processed_ids
        ).distinct()

        # Try to apply the first matching alternative
        for alt_discount in alternative_discounts:
            if _apply_discount_to_invoice(student, invoice, job, alt_discount):
                processed_ids.add(alt_discount.id)
                logger.info(f"Applied alternative discount {alt_discount.id} for student {student.id}")
                return True

        logger.info(f"No alternative discount found for student {student.id}")
        return False


def _apply_discount_to_invoice(student, invoice, job, discount_blueprint):
    """
    Apply a discount blueprint to a student's invoice.
    Creates DiscountApplicationModel lock if needed, then creates StudentDiscountModel records.

    Returns True if successfully applied, False otherwise.
    """

    # Get or create DiscountApplicationModel for this session/term
    discount_application = _get_or_create_discount_application(
        discount_blueprint, job.session, job.term
    )

    if not discount_application:
        logger.error(f"Failed to get/create discount application for {discount_blueprint.id}")
        return False

    # Find applicable invoice items
    applicable_fees = discount_blueprint.applicable_fees.all()
    applicable_items = invoice.items.filter(
        fee_master__fee__in=applicable_fees
    )

    if not applicable_items.exists():
        logger.info(f"No matching invoice items for discount {discount_blueprint.id}")
        return False

    # Apply discount to each applicable item
    discount_applied = False

    for item in applicable_items:
        # Check if discount already applied to this specific item
        if StudentDiscountModel.objects.filter(
                student=student,
                discount_application=discount_application,
                invoice_item=item
        ).exists():
            continue

        # Calculate discount amount
        if discount_application.discount_type == DiscountModel.DiscountType.PERCENTAGE:
            discount_amount = (item.amount * discount_application.discount_amount) / Decimal('100')
        else:  # FIXED
            # For fixed amount, divide equally among applicable items
            discount_amount = discount_application.discount_amount / applicable_items.count()

        # Round to 2 decimal places
        discount_amount = discount_amount.quantize(Decimal('0.01'))

        # Create discount record
        StudentDiscountModel.objects.create(
            student=student,
            discount_application=discount_application,
            invoice_item=item,
            amount_discounted=discount_amount
        )

        discount_applied = True
        logger.info(f"Applied discount {discount_blueprint.id} to item {item.id} for student {student.id}")

    return discount_applied


def _get_or_create_discount_application(discount_blueprint, session, term):
    """
    Get existing DiscountApplicationModel for session/term, or create one if it doesn't exist.
    When creating, uses the blueprint's default amount and discount_type.

    Returns DiscountApplicationModel or None if creation fails.
    """

    try:
        # Try to get existing application
        discount_application = DiscountApplicationModel.objects.filter(
            discount=discount_blueprint,
            session=session,
            term=term
        ).first()

        if discount_application:
            return discount_application

        # Check for global application (null session/term)
        global_application = DiscountApplicationModel.objects.filter(
            discount=discount_blueprint,
            session__isnull=True,
            term__isnull=True
        ).first()

        if global_application:
            return global_application

        # No existing application found - create one automatically
        logger.info(f"Auto-creating DiscountApplication for discount {discount_blueprint.id}")

        discount_application = DiscountApplicationModel.objects.create(
            discount=discount_blueprint,
            session=session,
            term=term,
            discount_type=discount_blueprint.discount_type,
            discount_amount=discount_blueprint.amount or Decimal('0.00')
        )

        logger.info(f"Created DiscountApplication {discount_application.id}")
        return discount_application

    except Exception as e:
        logger.error(f"Error getting/creating discount application: {str(e)}")
        return None
