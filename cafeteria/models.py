# cafeteria/models.py
from decimal import Decimal
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User

from admin_site.models import SessionModel, TermModel, SchoolSettingModel
from human_resource.models import StaffModel
from student.models import StudentModel
from finance.models import FeeModel


class MealModel(models.Model):
    """Types of meals available (Breakfast, Lunch, Dinner, Snack)"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class CafeteriaSettingModel(models.Model):
    """A singleton model for global cafeteria settings."""
    max_meals_per_day = models.PositiveIntegerField(default=3,
                                                    help_text="The maximum number of meals a student can collect in a single day.")

    # This links the cafeteria service to a specific fee in your finance system.
    cafeteria_fee = models.ForeignKey(
        FeeModel,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        help_text="Select the fee that grants students access to the cafeteria."
    )
    is_active = models.BooleanField(default=True,
                                    help_text="Enable or disable the entire cafeteria meal collection system.")

    # Auditing
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Cafeteria Setting"
        verbose_name_plural = "Cafeteria Settings"

    def __str__(self):
        return "Global Cafeteria Settings"

    def save(self, *args, **kwargs):
        # Enforce the singleton pattern
        self.pk = 1
        super().save(*args, **kwargs)


class MealCollectionModel(models.Model):
    """A record of a single student collecting a specific meal on a specific day."""
    student = models.ForeignKey(StudentModel, on_delete=models.CASCADE, related_name='meal_collections')
    meal = models.ForeignKey(MealModel, on_delete=models.PROTECT) # PROTECT to prevent deleting meals with history

    collection_date = models.DateField(default=timezone.now)
    collection_time = models.TimeField(auto_now_add=True)

    session = models.ForeignKey(SessionModel, on_delete=models.SET_NULL, null=True, blank=True)
    term = models.ForeignKey(TermModel, on_delete=models.SET_NULL, null=True, blank=True)

    # Corrected to link to StaffModel for consistency
    served_by = models.ForeignKey(StaffModel, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ('student', 'meal', 'collection_date') # Prevents duplicate entries
        ordering = ['-collection_date', '-collection_time']
        verbose_name = "Meal Collection Record"

    def save(self, *args, **kwargs):
        # Auto-populate session and term if not provided
        if not self.session or not self.term:
            setting = SchoolSettingModel.objects.first()
            if setting:
                if not self.session: self.session = setting.session
                if not self.term: self.term = setting.term
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} - {self.meal.name} on {self.collection_date}"
