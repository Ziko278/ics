import logging
import random
import string

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import StaffModel, StaffProfileModel

logger = logging.getLogger(__name__)


def _send_credentials_email_signal(staff, username, password):
    """
    Helper function to render and send a credentials email from within the signal.
    """
    if not staff.email:
        logger.warning(f"Signal: Staff ID {staff.id} has no email, cannot send credentials.")
        return False
    try:
        context = {
            'staff_name': f"{staff.first_name} {staff.last_name}",
            'username': username,
            'password': password,
            'login_url': settings.LOGIN_URL,
        }
        html_content = render_to_string('human_resource/email/credentials.html', context)

        send_mail(
            subject="Your Staff Portal Account Credentials",
            message=f"Hello {context['staff_name']},\n\nYour account has been created. Username: {username}, Password: {password}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[staff.email],
            fail_silently=False,
            html_message=html_content
        )
        logger.info(f"Signal: Credentials successfully emailed to {staff.email}")
        return True
    except Exception:
        logger.exception(f"Signal: Failed to send credentials email to {staff.email}")
        return False


# @receiver(post_save, sender=StaffModel)
# def create_staff_user_account(sender, instance, created, **kwargs):
#     """
#     Signal to automatically create a User account when a new StaffModel instance is created.
#     """
#     if created:
#         staff = instance
#         logger.info(f"Signal triggered: Creating user account for new staff '{staff}'.")
#
#         # Prevent signal from running if a user profile already exists (e.g., from data migration)
#         if hasattr(staff, 'staff_profile') and staff.staff_profile is not None:
#             logger.info(f"Signal: Staff '{staff}' already has a profile. Skipping user creation.")
#             return
#
#         try:
#             # 1. Generate Credentials
#             username = staff.staff_id
#             password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
#
#             # 2. Create Django User
#             user = User.objects.create_user(
#                 username=username,
#                 email=staff.email,
#                 password=password,
#                 first_name=staff.first_name,
#                 last_name=staff.last_name
#             )
#
#             # 3. Create Staff Profile and save password as a fallback
#             StaffProfileModel.objects.create(
#                 user=user,
#                 staff=staff,
#                 default_password=password
#             )
#
#             # 4. Add user to their assigned group
#             if staff.group:
#                 staff.group.user_set.add(user)
#
#             logger.info(f"Signal: Successfully created User '{username}' for Staff '{staff}'.")
#
#             # 5. Attempt to send email
#             _send_credentials_email_signal(staff, username, password)
#
#         except Exception:
#             # Log any exception during the process
#             logger.exception(f"Signal: An unexpected error occurred while creating user for Staff ID {staff.id}.")
