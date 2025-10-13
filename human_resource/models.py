import logging
import uuid

from django.conf import settings
from django.db import models, transaction
from django.contrib.auth.models import User, Group
from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)


class HRSettingModel(models.Model):
    """
    A singleton model to control settings for the Human Resources app.
    """
    auto_generate_staff_id = models.BooleanField(default=True)
    staff_prefix = models.CharField(max_length=10, blank=True, null=True, default='STF')

    def __str__(self):
        return "HR Settings"


class StaffIDGeneratorModel(models.Model):
    """
    A dedicated model to safely generate sequential staff IDs, preventing race conditions.
    This model should only ever have one row with id=1.
    """
    last_id = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class StaffModel(models.Model):
    """
    Represents a staff member in the school.
    """

    class Gender(models.TextChoices):
        MALE = 'MALE', 'MALE'
        FEMALE = 'FEMALE', 'FEMALE'

    # Renamed for consistency with Django conventions
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)

    staff_id = models.CharField(max_length=100, unique=True, blank=True)
    image = models.FileField(upload_to='images/staff_images', blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True, default='')
    email = models.EmailField(max_length=100, blank=True, null=True, default='')
    gender = models.CharField(max_length=10, choices=Gender.choices)
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=30, choices=[('active', 'ACTIVE'), ('inactive', 'INACTIVE')], default='active')

    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        # Extract the skip flag
        skip_user_sync = kwargs.pop('skip_user_sync', False)

        # Check if this is a new record
        is_new = self.pk is None

        # Generate staff_id if needed
        if not self.staff_id:
            self.staff_id = self.generate_unique_staff_id()

        # Save to database
        super().save(*args, **kwargs)

        # Don't sync users for new records or when explicitly skipped
        if skip_user_sync or is_new:
            return

        # Only sync for existing staff updates
        try:
            profile = self.staff_profile
            user = profile.user

            user.email = self.email
            user.first_name = self.first_name
            user.last_name = self.last_name
            user.save()

            if self.group:
                user.groups.clear()
                self.group.user_set.add(user)

        except ObjectDoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Error syncing user for staff {self}: {e}", exc_info=True)

    @transaction.atomic
    def generate_unique_staff_id(self):
        """
        Generates a unique, sequential staff ID using a dedicated counter model
        to prevent race conditions.
        """
        setting, _ = HRSettingModel.objects.get_or_create(id=1)

        # Fallback for manual ID generation
        if not setting.auto_generate_staff_id:
            timestamp = uuid.uuid4().hex[:6].upper()
            return f"STF-{timestamp}"

        # Get or create the counter record and lock it for this transaction
        counter, _ = StaffIDGeneratorModel.objects.select_for_update().get_or_create(id=1)

        for _ in range(10):  # Try up to 10 times to find a unique ID
            counter.last_id += 1
            new_id_num = counter.last_id
            new_id_str = str(new_id_num).zfill(4)  # Formats 1 as "0001", 123 as "0123"

            prefix = setting.staff_prefix or 'STF'
            full_id = f"{prefix}-{new_id_str}"

            if not StaffModel.objects.filter(staff_id=full_id).exists():
                counter.save()
                return full_id

        # Ultimate fallback if 10 attempts fail, ensuring no crash
        return f"STF-ERR-{uuid.uuid4().hex[:6].upper()}"


class StaffProfileModel(models.Model):
    """
    Links a StaffModel to a Django User account.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    staff = models.OneToOneField(StaffModel, on_delete=models.CASCADE, related_name='staff_profile')
    default_password = models.CharField(max_length=100)  # To store the initial password

    def __str__(self):
        return self.user.username

    def delete(self, *args, **kwargs):
        """
        Override delete to ensure User is deleted when Profile is deleted.
        """
        user = self.user
        super().delete(*args, **kwargs)
        user.delete()


class StaffUploadTask(models.Model):
    """Tracks the status and result of a Celery staff upload task."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSING = 'PROCESSING', 'Processing'
        SUCCESS = 'SUCCESS', 'Success'
        FAILURE = 'FAILURE', 'Failure'

    task_id = models.CharField(max_length=255, unique=True, help_text="Celery task ID")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    result = models.TextField(blank=True, null=True, help_text="Result or error message from the task.")

    # Auditing fields
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Upload Task {self.task_id} - {self.status}"

