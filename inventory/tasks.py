# ============================================
# FILE: inventory/tasks.py
# ============================================
# Celery task for generating inventory collections
# ============================================

from celery import shared_task
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

# Adjust these imports to match your project structure
from .models import (
    CollectionGenerationJob,
    InventoryCollectionModel,
    InventoryAssignmentModel
)
from student.models import StudentModel


@shared_task
def generate_collections_task(job_id):
    """
    Background task to generate inventory collections for eligible students
    based on an InventoryAssignmentModel.

    Args:
        job_id: Primary key of the CollectionGenerationJob

    Process:
        1. Gets the job and assignment
        2. Filters students by: class, gender, type, active status
        3. Validates store stock
        4. Creates pending collections (prevents duplicates)
        5. Updates progress in real-time
        6. Handles errors gracefully
    """
    job = None
    try:
        # 1. Get the job record from the database
        job = CollectionGenerationJob.objects.get(pk=job_id)
        job.status = CollectionGenerationJob.Status.IN_PROGRESS
        job.started_at = timezone.now()
        job.save()

        # 2. Get the assignment
        assignment = job.assignment

        # 3. Build the student queryset based on assignment criteria
        students_query = StudentModel.objects.filter(
            status='active'  # Only active students
        )

        # Filter by classes if specified
        if assignment.student_classes.exists():
            students_query = students_query.filter(
                student_class__in=assignment.student_classes.all()
            )

        # Filter by gender (male/female/both)
        if assignment.gender != 'both':
            students_query = students_query.filter(gender=assignment.gender)

        # Filter by type (primary/secondary/general)
        if assignment.type:
            if assignment.type == 'pri':
                students_query = students_query.filter(student_class__type='primary')
            elif assignment.type == 'sec':
                students_query = students_query.filter(student_class__type='secondary')
            # 'mix' means all types, so no filter needed

        # Get distinct students
        students_to_process = students_query.distinct()
        job.total_students = students_to_process.count()
        job.save(update_fields=['total_students'])

        # 4. Check if item has stock in store
        if assignment.item.store_quantity <= 0:
            raise ValueError(
                f"Item '{assignment.item.name}' has no stock in store. "
                "Cannot create collections."
            )

        # 5. Process each student
        created_count = 0
        skipped_count = 0

        for i, student in enumerate(students_to_process):
            with transaction.atomic():
                # Use get_or_create to prevent duplicate collections
                collection, created = InventoryCollectionModel.objects.get_or_create(
                    assignment=assignment,
                    student=student,
                    defaults={
                        'quantity_assigned': assignment.quantity_per_student,
                        'quantity_collected': Decimal('0.00'),
                        'status': 'pending',
                        'payment_required': not assignment.is_free,
                        'amount_paid': Decimal('0.00'),
                        'payment_completed': False,
                    }
                )

                if created:
                    created_count += 1
                else:
                    skipped_count += 1

            # 6. Update progress after each student
            job.processed_students = i + 1
            job.created_collections = created_count
            job.skipped_students = skipped_count
            job.save(update_fields=[
                'processed_students',
                'created_collections',
                'skipped_students'
            ])

        # 7. Mark job as successful
        job.status = CollectionGenerationJob.Status.SUCCESS

    except Exception as e:
        # 8. Handle errors - mark job as failed and record error
        if job:
            job.status = CollectionGenerationJob.Status.FAILURE
            job.error_message = str(e)

    finally:
        # 9. Always set completion time
        if job:
            job.completed_at = timezone.now()
            job.save()


# ============================================
# OPTIONAL: Additional helper tasks
# ============================================

@shared_task
def send_collection_notifications(assignment_id):
    """
    Optional: Send email/SMS notifications to students
    about available collections
    """
    from django.core.mail import send_mail

    assignment = InventoryAssignmentModel.objects.get(pk=assignment_id)
    collections = InventoryCollectionModel.objects.filter(
        assignment=assignment,
        status='pending'
    ).select_related('student')

    for collection in collections:
        student = collection.student
        if student.email:
            send_mail(
                subject=f'Collection Ready: {assignment.item.name}',
                message=f'''
Dear {student.first_name},

Your {assignment.item.name} is ready for collection.
Quantity: {collection.quantity_assigned} {assignment.item.get_unit_display()}

Please visit the inventory store to collect your items.

Thank you.
                ''',
                from_email='inventory@yourschool.com',
                recipient_list=[student.email],
                fail_silently=True,
            )


@shared_task
def cleanup_old_jobs():
    """
    Optional: Cleanup old completed jobs (run periodically)
    Keep only last 30 days
    """
    from datetime import timedelta

    cutoff_date = timezone.now() - timedelta(days=30)
    old_jobs = CollectionGenerationJob.objects.filter(
        completed_at__lt=cutoff_date,
        status__in=['success', 'failure']
    )

    count = old_jobs.count()
    old_jobs.delete()

    return f"Deleted {count} old jobs"

# ============================================
# CELERY BEAT SCHEDULE (Optional)
# ============================================
# Add to your celery.py for periodic tasks:
#
# from celery.schedules import crontab
#
# app.conf.beat_schedule = {
#     'cleanup-old-jobs': {
#         'task': 'inventory.tasks.cleanup_old_jobs',
#         'schedule': crontab(hour=2, minute=0),  # Run at 2 AM daily
#     },
# }