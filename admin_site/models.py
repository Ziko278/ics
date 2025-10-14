import logging
from django.db import models
from django.apps import apps
from django.db import OperationalError
from human_resource.models import StaffModel

# Configure a logger for this module
logger = logging.getLogger(__name__)


class TermModel(models.Model):
    name = models.CharField(max_length=20, unique=True)
    order = models.PositiveIntegerField(unique=True, help_text="Order for sorting terms (e.g., 1 for 1st Term).")

    class Meta:
        ordering = ['order']
        verbose_name = "Term"
        verbose_name_plural = "Terms"

    def __str__(self):
        return self.name


class SessionModel(models.Model):
    start_year = models.PositiveIntegerField()
    end_year = models.PositiveIntegerField()
    SEPERATOR = (('-', '-'), ('/', '/'))
    seperator = models.CharField(max_length=1, choices=SEPERATOR, default='-')

    def __str__(self):
        return f"{self.start_year}{self.seperator}{self.end_year}"


class SchoolInfoModel(models.Model):
    name = models.CharField(max_length=250)
    short_name = models.CharField(max_length=50)
    logo = models.FileField(upload_to='images/logo', blank=True, null=True)
    mobile = models.CharField(max_length=20)
    email = models.EmailField()
    address = models.CharField(max_length=255)

    def __str__(self):
        return self.short_name.upper()


class SchoolSettingModel(models.Model):
    allow_student_debt = models.BooleanField(default=True)
    auto_low_balance_notification = models.BooleanField(default=True)
    # ✔️ BUG PREVENTION: Using DecimalField for all financial values.
    max_student_debt = models.DecimalField(max_digits=10, decimal_places=2)
    low_balance = models.DecimalField(max_digits=10, decimal_places=2)
    allow_refund = models.BooleanField(default=False)
    auto_generate_student_id = models.BooleanField(default=True)
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)
    account_name = models.CharField(max_length=200, null=True, blank=True)
    account_number = models.CharField(max_length=20, null=True, blank=True)
    bank = models.CharField(max_length=100, null=True, blank=True)


class ClassSectionModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['name'], name='unique_class_name_type_combo')]

    def __str__(self):
        return self.name.upper()


class ClassesModel(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, default='', blank=True)
    section = models.ManyToManyField(ClassSectionModel, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['name'], name='unique_name_class_type_combo')]

    def __str__(self):
        return self.name.upper()

    def number_of_students(self):
        # This method is preserved exactly as you wrote it.
        StudentModel = apps.get_model('student', 'StudentModel')
        return StudentModel.objects.filter(student_class=self).count()


class ClassSectionInfoModel(models.Model):
    student_class = models.ForeignKey(ClassesModel, on_delete=models.CASCADE)
    section = models.ForeignKey(ClassSectionModel, on_delete=models.CASCADE)
    form_teacher = models.ForeignKey(
        StaffModel, on_delete=models.SET_NULL, null=True, blank=True,
        limit_choices_to={'group__name': 'Teachers'},
        related_name='form_teacher_rosters'
    )
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['student_class', 'section'], name='unique_student_class_section_combo')]

    def __str__(self):
        return f"{self.student_class.name.upper()} {self.section.name.upper()}"

    def number_of_students(self):
        # This method is preserved exactly as you wrote it.
        StudentModel = apps.get_model('student', 'StudentModel')
        return StudentModel.objects.filter(student_class=self.student_class, class_section=self.section).count()


class ActivityLogModel(models.Model):
    category = models.CharField(max_length=50, blank=True, null=True)
    sub_category = models.CharField(max_length=50, blank=True, null=True)
    log = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True, help_text="Session of activity.")
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True, help_text="Session of activity.")

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.category or 'N/A'} - {self.log[:50]}..."

    def save(self, *args, **kwargs):
        # ✔️ ROBUSTNESS: Refined exception handling for auto-populating fields.
        if self.session is None or self.term is None:
            try:
                # Use explicit app label to prevent lookup errors.
                Setting = apps.get_model('admin_site', 'SchoolSettingModel')
                setting = Setting.objects.first()
                if setting:
                    if self.session is None: self.session = setting.session
                    if self.term is None: self.term = setting.term
                else:
                    logger.warning("No SchoolSettingModel found. Cannot auto-set session/term for ActivityLog.")
            except LookupError:
                logger.error("FATAL: 'admin_site.SchoolSettingModel' is not registered. Check INSTALLED_APPS.")
            except OperationalError as e:
                logger.error(f"Database error fetching SchoolSettingModel: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Unexpected error in ActivityLog save: {e}", exc_info=True)
        super().save(*args, **kwargs)

