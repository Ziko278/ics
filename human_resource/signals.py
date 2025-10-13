import random
import string
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib.auth.models import User

from admin_site.models import SchoolInfoModel
from .models import StaffModel, StaffProfileModel


def _send_credentials_email(staff, username, password):
    """A helper function to send the welcome email."""
    if not staff.email:
        return False
    try:
        school_info = SchoolInfoModel.objects.first()
        mail_subject = f"Your Staff Account for {school_info.name}"
        # Replace 'https://yourdomain.com' with your actual site domain
        login_url = 'https://yourdomain.com' + reverse('login')

        context = {
            'staff': staff,
            'username': username,
            'password': password,
            'school_info': school_info,
            'login_url': login_url
        }
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
    Automatically creates a User account and profile when a new StaffModel is created.
    """
    if created:
        staff_instance = instance

        # Check if a profile already exists to prevent errors on re-saves
        if hasattr(staff_instance, 'staff_profile'):
            return

        # 1. Generate username (using the staff_id)
        username = staff_instance.staff_id

        # Check for username collision (should be rare with unique staff_id)
        if User.objects.filter(username=username).exists():
            username = f"{username}-{random.randint(100, 999)}"

        # 2. Generate a random password
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

        # 3. Create the User
        user = User.objects.create_user(
            username=username,
            password=password,
            first_name=staff_instance.first_name,
            last_name=staff_instance.last_name,
            email=staff_instance.email or ''
        )

        # 4. Create the StaffProfile to link them
        StaffProfileModel.objects.create(
            user=user,
            staff=staff_instance,
            default_password=password
        )

        # 5. Add the user to the specified group
        if staff_instance.group:
            staff_instance.group.user_set.add(user)

        # 6. Send the welcome email
        #_send_credentials_email(staff_instance, username, password)
