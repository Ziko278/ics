from decimal import Decimal

from celery import shared_task
from django.utils import timezone
from django.db import transaction

# Adjust these imports to match your project structure
from .models import InvoiceGenerationJob, InvoiceModel, InvoiceItemModel
from student.models import StudentModel
from finance.models import FeeMasterModel


@shared_task
def generate_invoices_task(job_id):
    """
    This is the Celery background task that performs the heavy lifting
    of generating invoices for a large number of students.
    """
    job = None  # Define job here to ensure it's available in the finally block
    try:
        # 1. Get the job record from the database
        job = InvoiceGenerationJob.objects.get(pk=job_id)
        job.status = InvoiceGenerationJob.Status.IN_PROGRESS
        job.save()

        # 2. Find all students in the classes selected for this job
        students_to_invoice = StudentModel.objects.filter(
            student_class__in=job.classes_to_invoice.all(),
            status='active'  # Only invoice active students
        ).select_related('student_class')  # Optimize for student.student_class access

        job.total_students = students_to_invoice.count()
        job.save(update_fields=['total_students'])

        # 3. Find all fee structures that apply to the selected classes
        # We also prefetch the related termly amounts
        applicable_fees = FeeMasterModel.objects.filter(
            student_classes__in=job.classes_to_invoice.all()
        ).select_related('fee', 'group').prefetch_related(
            'student_classes', 'termly_amounts'  # Prefetch for efficiency
        ).distinct()

        # 4. Loop through each student and generate their invoice(s)
        for i, student in enumerate(students_to_invoice):

            # --- START OF FIX ---
            # We must loop through the fees for this student FIRST.

            # Filter the fees that apply to this specific student's class
            applicable_fees_for_student = [
                f for f in applicable_fees if student.student_class in f.student_classes.all()
            ]

            # Now, loop through this student's fees and create one invoice PER fee
            for fee_master in applicable_fees_for_student:
                with transaction.atomic():

                    # Get the amount for the correct term
                    termly_amount = None
                    for ta in fee_master.termly_amounts.all():  # Use the prefetched data
                        if ta.term_id == job.term_id:
                            termly_amount = ta
                            break

                    amount = termly_amount.amount if termly_amount else Decimal('0.00')

                    # Skip creating an invoice if the fee is zero for this term
                    if amount <= 0:
                        continue

                    # Use get_or_create to prevent creating duplicate invoices
                    # 'fee_master' is now defined *before* we use it.
                    invoice, created = InvoiceModel.objects.get_or_create(
                        student=student,
                        session=job.session,
                        term=job.term,
                        fee=fee_master.__str__(),  # This is now SAFE
                        defaults={
                            'due_date': timezone.now().date(),
                            # You should also set the invoice total here
                            # 'total_amount': amount
                        }
                    )

                    # If an invoice was newly created, add its single line item
                    if created:
                        InvoiceItemModel.objects.create(
                            invoice=invoice,
                            fee_master=fee_master,
                            description=f"{fee_master.fee.name} - {fee_master.group.name}",
                            amount=amount
                        )

                        # --- Optional: Update Invoice Total ---
                        # If your InvoiceModel has a 'total_amount' field, set it.
                        # setattr(invoice, 'total_amount', amount)
                        # invoice.save()

            # --- END OF FIX ---

            # 5. Update the progress after each *student* is processed
            job.processed_students = i + 1
            job.save(update_fields=['processed_students'])

        # 6. Mark the job as successful
        job.status = InvoiceGenerationJob.Status.SUCCESS

    except Exception as e:
        # 7. If any error occurs, mark the job as failed and record the error
        if job:
            job.status = InvoiceGenerationJob.Status.FAILURE
            job.error_message = f"Error processing student {i + 1}: {str(e)}"

    finally:
        # 8. Always set the completion time
        if job:
            job.completed_at = timezone.now()
            job.save()
