from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse

from admin_site.models import SchoolInfoModel, ActivityLogModel
from student.models import *
from django.contrib.auth.models import User
from student.models import StudentModel, StudentWalletModel
import secrets
from django.utils import timezone
from pytz import timezone as pytz_timezone


def get_day_ordinal_suffix(day_num):
    if 10 <= day_num % 100 <= 20:
        return 'th'
    else:
        return {1: 'st', 2: 'nd', 3: 'rd'}.get(day_num % 10, 'th')


def make_random_password(length=10, allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'):
    return ''.join(secrets.choice(allowed_chars) for i in range(length))


@receiver(post_save, sender=StudentModel)
def create_student_account(sender, instance, created, **kwargs):
    if created:
        student = instance
        wallet = StudentWalletModel.objects.create(student=student)
        wallet.save()

        # target_timezone = pytz_timezone('Africa/Lagos')
        #
        # localized_created_at = timezone.localtime(student.created_at, timezone=target_timezone)
        #
        # formatted_time = localized_created_at.strftime(
        #     f"%B {localized_created_at.day}{get_day_ordinal_suffix(localized_created_at.day)} %Y %I:%M%p"
        # )
        #
        # log = f"""
        #    <div class='text-white bg-primary' style='padding:5px;'>
        #    <p class=''>New Student registration:
        #    <a href={reverse('student_detail', kwargs={'pk': student.id})}><b>{student.__str__().title()}</b></a>
        #    Registered by <a href={reverse('staff_detail', kwargs={'pk': student.created_by.id})}><b>{student.created_by.__str__().title()}</b></a>
        #    <br><span style='float:right'>{formatted_time}</span>
        #    </p>
        #
        #    </div>
        #    """
        #
        # activity = ActivityLogModel.objects.create(log=log)
        # activity.save()

