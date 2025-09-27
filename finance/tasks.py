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
        )
        job.total_students = students_to_invoice.count()
        job.save(update_fields=['total_students'])

        # 3. Find all fee structures that apply to the selected classes
        applicable_fees = FeeMasterModel.objects.filter(
            student_classes__in=job.classes_to_invoice.all()
        ).select_related('fee', 'group').distinct()

        # 4. Loop through each student and generate their invoice
        for i, student in enumerate(students_to_invoice):
            with transaction.atomic():
                # Use get_or_create to prevent creating duplicate invoices if the job is run twice
                invoice, created = InvoiceModel.objects.get_or_create(
                    student=student,
                    session=job.session,
                    term=job.term,
                    fee=fee_master.__str__(),
                    defaults={'due_date': timezone.now().date()}  # Set a default due date
                )

                # If an invoice was newly created, add all the line items
                if created:
                    for fee_master in applicable_fees:
                        # Final check to ensure this specific fee applies to this student's specific class
                        if student.student_class in fee_master.student_classes.all():

                            # With this:
                            termly_amount = fee_master.termly_amounts.filter(term=job.term).first()
                            amount = termly_amount.amount if termly_amount else Decimal('0.00')
                            InvoiceItemModel.objects.create(
                                invoice=invoice,
                                fee_master=fee_master,
                                description=f"{fee_master.fee.name} - {fee_master.group.name}",
                                amount=amount
                            )

            # 5. Update the progress after each student is processed
            job.processed_students = i + 1
            job.save(update_fields=['processed_students'])

        # 6. Mark the job as successful
        job.status = InvoiceGenerationJob.Status.SUCCESS

    except Exception as e:
        # 7. If any error occurs, mark the job as failed and record the error
        if job:
            job.status = InvoiceGenerationJob.Status.FAILURE
            job.error_message = str(e)

    finally:
        # 8. Always set the completion time
        if job:
            job.completed_at = timezone.now()
            job.save()
