from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from django.db import transaction
import logging

from .models import InvoiceGenerationJob, InvoiceModel, InvoiceItemModel
from student.models import StudentModel
from finance.models import FeeMasterModel

logger = logging.getLogger(__name__)


@shared_task
def generate_invoices_task(job_id):
    """
    This is the Celery background task that performs the heavy lifting
    of generating invoices for a large number of students.
    """
    VERSION_CHECK = "VERSION_2024_11_02_FIX_V2"
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
        ).select_related('student_class')

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

            # Filter the fees that apply to this specific student's class
            # Filter the fees that apply to this specific student's class AND utilities
            student_utilities = set(student.utilities.all())  # Get student's utilities as a set

            applicable_fees_for_student = [
                f for f in applicable_fees
                if student.student_class in f.student_classes.all()
                   and (f.fee.required_utility is None or f.fee.required_utility in student_utilities)
            ]

            # Create ONE invoice per student per term/session
            # Then add multiple items to it
            with transaction.atomic():
                # Get or create the invoice for this student/session/term
                invoice, created = InvoiceModel.objects.get_or_create(
                    student=student,
                    session=job.session,
                    term=job.term,
                    defaults={
                        'due_date': timezone.now().date(),
                        'status': 'unpaid',  # Set appropriate default status
                    }
                )

                # Now add all applicable fees as line items
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
