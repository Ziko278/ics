import random
import string
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction  # <-- IMPORT THIS
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib.auth.models import User

from admin_site.models import SchoolInfoModel
from .models import StaffModel, StaffProfileModel


def _send_credentials_email(staff, username, password):
    # ... (This helper function does not need to be changed) ...
    if not staff.email:
        return False
    try:
        school_info = SchoolInfoModel.objects.first()
        mail_subject = f"Your Staff Account for {school_info.name}"
        login_url = 'https://yourdomain.com' + reverse('login')

        context = {'staff': staff, 'username': username, 'password': password, 'school_info': school_info,
                   'login_url': login_url}
        html_content = render_to_string('emails/staff_welcome_email.html', context)

        email_message = EmailMultiAlternatives(
            subject=mail_subject,
            body=f"Hello {staff.first_name},\n\nYour account has been created. Log in at {login_url} with username: {username} and password: {password}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[staff.email]
        )
        email_message.attach_alternative(html_content, "text/html")
        email_message.send()
        return True
    except Exception as e:
        print(f"Error sending staff welcome email to {staff.email}: {e}")
        return False


@receiver(post_save, sender=StaffModel)
def create_staff_user_account(sender, instance, created, **kwargs):
    """
    Schedules the user account creation to run after the database transaction is committed.
    """
    if created:
        # We wrap the logic in a lambda and pass it to on_commit
        transaction.on_commit(lambda: _create_user_and_profile(instance.pk))


def _create_user_and_profile(staff_pk):
    """
    This function contains the actual logic and is called by the on_commit hook.
    We pass the primary key (pk) to avoid issues with stale model instances.
    """
    try:
        staff_instance = StaffModel.objects.get(pk=staff_pk)

        # Check if a profile already exists to prevent race conditions
        if hasattr(staff_instance, 'staff_profile'):
            return

        username = staff_instance.staff_id
        if User.objects.filter(username=username).exists():
            username = f"{username}-{random.randint(100, 999)}"

        password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=staff_instance.first_name,
            last_name=staff_instance.last_name,
            email=staff_instance.email or ''
        )

        StaffProfileModel.objects.create(
            user=user,
            staff=staff_instance,
            default_password=password
        )

        if staff_instance.group:
            staff_instance.group.user_set.add(user)

        # _send_credentials_email(staff_instance, username, password)

    except StaffModel.DoesNotExist:
        # This can happen in rare edge cases, so we handle it gracefully.
        print(f"Could not find Staff with pk={staff_pk} to create user.")
    except Exception as e:
        print(f"An error occurred in _create_user_and_profile for staff pk={staff_pk}: {e}")


