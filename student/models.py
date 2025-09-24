import logging
import uuid
from django.db import models, transaction
from django.contrib.auth.models import User
from admin_site.models import ClassesModel, ClassSectionModel
from human_resource.models import StaffModel

logger = logging.getLogger(__name__)


class StudentSettingModel(models.Model):
    """
    A singleton model to control settings for the Student app.
    """
    auto_generate_student_id = models.BooleanField(default=True)
    student_prefix = models.CharField(max_length=10, blank=True, null=True, default='STU')
    auto_generate_parent_id = models.BooleanField(default=True)
    parent_prefix = models.CharField(max_length=10, blank=True, null=True, default='PAR')

    def __str__(self):
        return "Student & Parent Settings"


class StudentIDGeneratorModel(models.Model):
    """
    A dedicated counter for safely generating sequential Student IDs.
    """
    last_id = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ParentIDGeneratorModel(models.Model):
    """
    A dedicated counter for safely generating sequential Parent IDs.
    """
    last_id = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)


class ParentModel(models.Model):
    """
    Represents a parent or guardian, with their own contact info and user account.
    """

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    parent_id = models.CharField(max_length=100, unique=True, blank=True)
    email = models.EmailField(max_length=100, unique=True, blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, null=True)

    # Optional fields from your example
    occupation = models.CharField(max_length=100, null=True, blank=True)
    residential_address = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def number_of_wards(self):
        return self.students.count()

    def save(self, *args, **kwargs):
        if not self.parent_id:
            self.parent_id = self.generate_unique_parent_id()
        super().save(*args, **kwargs)

    @transaction.atomic
    def generate_unique_parent_id(self):
        setting, _ = StudentSettingModel.objects.get_or_create(id=1)
        if not setting.auto_generate_parent_id:
            return f"PAR-{uuid.uuid4().hex[:6].upper()}"

        counter, _ = ParentIDGeneratorModel.objects.select_for_update().get_or_create(id=1)
        for _ in range(10):
            counter.last_id += 1
            new_id_str = str(counter.last_id).zfill(4)
            prefix = setting.parent_prefix or 'PAR'
            full_id = f"{prefix}-{new_id_str}"
            if not ParentModel.objects.filter(parent_id=full_id).exists():
                counter.save()
                return full_id
        return f"PAR-ERR-{uuid.uuid4().hex[:6].upper()}"


class ParentProfileModel(models.Model):
    """
    Links a ParentModel to a Django User account for portal access.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='parent_profile')
    parent = models.OneToOneField(ParentModel, on_delete=models.CASCADE, related_name='parent_profile')
    default_password = models.CharField(max_length=100)

    def __str__(self):
        return self.user.username


class StudentModel(models.Model):
    """
    Represents a student, now linked to a parent.
    """

    class Gender(models.TextChoices):
        MALE = 'MALE', 'MALE'
        FEMALE = 'FEMALE', 'FEMALE'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'ACTIVE'
        GRADUATED = 'graduated', 'GRADUATED'
        SUSPENDED = 'suspended', 'SUSPENDED'
        INACTIVE = 'inactive', 'INACTIVE'

    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    registration_number = models.CharField(max_length=50, blank=True, unique=True)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    image = models.FileField(blank=True, null=True, upload_to='images/student_images')

    # Crucial link to the parent
    parent = models.ForeignKey(ParentModel, on_delete=models.PROTECT, related_name='wards')

    student_class = models.ForeignKey(ClassesModel, null=True, on_delete=models.SET_NULL)
    class_section = models.ForeignKey(ClassSectionModel, null=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.ACTIVE)

    created_by = models.ForeignKey(StaffModel, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        if not self.registration_number:
            self.registration_number = self.generate_unique_student_id()
        super().save(*args, **kwargs)

    @transaction.atomic
    def generate_unique_student_id(self):
        setting, _ = StudentSettingModel.objects.get_or_create(id=1)
        if not setting.auto_generate_student_id:
            return f"STU-{uuid.uuid4().hex[:6].upper()}"

        counter, _ = StudentIDGeneratorModel.objects.select_for_update().get_or_create(id=1)
        for _ in range(10):
            counter.last_id += 1
            new_id_str = str(counter.last_id).zfill(4)
            prefix = setting.student_prefix or 'STU'
            full_id = f"{prefix}-{new_id_str}"
            if not StudentModel.objects.filter(registration_number=full_id).exists():
                counter.save()
                return full_id
        return f"STU-ERR-{uuid.uuid4().hex[:6].upper()}"

    def is_fingerprint_enrolled(self):
        return self.fingerprints.all().count() > 0


class StudentWalletModel(models.Model):
    student = models.OneToOneField(StudentModel, on_delete=models.CASCADE, related_name='student_wallet')
    # Use DecimalField for financial accuracy
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    debt = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.student}'s Wallet"


class FingerprintModel(models.Model):
    """
    Enhanced fingerprint model with quality metrics and matching capabilities
    """
    FINGER_CHOICES = [
        ('LEFT_THUMB', 'Left Thumb'),
        ('LEFT_INDEX', 'Left Index'),
        ('LEFT_MIDDLE', 'Left Middle'),
        ('LEFT_RING', 'Left Ring'),
        ('LEFT_LITTLE', 'Left Little'),
        ('RIGHT_THUMB', 'Right Thumb'),
        ('RIGHT_INDEX', 'Right Index'),
        ('RIGHT_MIDDLE', 'Right Middle'),
        ('RIGHT_RING', 'Right Ring'),
        ('RIGHT_LITTLE', 'Right Little'),
    ]

    student = models.ForeignKey(StudentModel, on_delete=models.CASCADE, related_name='fingerprints')
    finger_name = models.CharField(max_length=20, choices=FINGER_CHOICES)

    # Store the fingerprint template (binary data as base64)
    fingerprint_template = models.TextField(help_text="Base64 encoded fingerprint template")

    # Quality metrics
    quality_score = models.FloatField(null=True, blank=True, help_text="Fingerprint quality (0.0-1.0)")
    capture_device = models.CharField(max_length=100, default="U.are.U 4500", blank=True)

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    usage_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['student', 'finger_name']
        indexes = [
            models.Index(fields=['student', 'is_active']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.student} - {self.get_finger_name_display()}"

    def mark_used(self):
        """Mark this fingerprint as recently used"""
        from django.utils import timezone
        self.last_used = timezone.now()
        self.usage_count += 1
        self.save(update_fields=['last_used', 'usage_count'])

