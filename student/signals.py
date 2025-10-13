from django.conf import settings
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import EmailMultiAlternatives
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib.auth.models import User
import secrets

from admin_site.models import SchoolInfoModel
from .models import StudentModel, StudentWalletModel, ParentModel, ParentProfileModel


def get_day_ordinal_suffix(day_num):
    if 10 <= day_num % 100 <= 20:
        return 'th'
    else:
        return {1: 'st', 2: 'nd', 3: 'rd'}.get(day_num % 10, 'th')


def make_random_password(length=8, allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'):
    """Generates a random, easy-to-read password."""
    return ''.join(secrets.choice(allowed_chars) for i in range(length))


@receiver(post_save, sender=StudentModel)
def create_student_account(sender, instance, created, **kwargs):
    """
    Creates a wallet for a new student.
    (Your existing signal for students remains unchanged)
    """
    if created:
        student = instance
        StudentWalletModel.objects.create(student=student)
        # Your activity log code can be re-enabled here if needed.


# ==============================================================================
# ===== NEW SIGNAL TO CREATE PARENT USER ACCOUNTS =====
# ==============================================================================
@receiver(post_save, sender=ParentModel)
def create_parent_user_account(sender, instance, created, **kwargs):
    """
    Automatically creates a User account when a new ParentModel is created.
    """
    if created:
        parent = instance

        # 1. CORRECTED: Set the username to be the parent's unique ID.
        username = parent.parent_id

        # Check if a user with this username already exists to prevent errors.
        if User.objects.filter(username=username).exists():
            print(f"User with username {username} already exists. Skipping user creation for parent {parent.id}.")
            return

        # 2. Generate a random password
        password = make_random_password()

        # 3. Create the User object
        # This securely hashes the password.
        user = User.objects.create_user(
            username=username,
            password=password,
            email=parent.email,
            first_name=parent.first_name,
            last_name=parent.last_name
        )

        # 4. Create the ParentProfile to link the User and Parent
        # We store the initial password here for administrative reference.
        ParentProfileModel.objects.create(
            user=user,
            parent=parent,
            default_password=password
        )

        # 5. CORRECTED: Only attempt to send an email if an email address exists.
        if parent.email:
            try:
                school_info = SchoolInfoModel.objects.first()
                mail_subject = f"Your Parent Portal Account for {school_info.name} has been created"

                # Replace 'https://yourdomain.com' with your actual site domain.
                login_url = 'https://yourdomain.com' + reverse('login')

                context = {
                    'parent': parent,
                    'username': username,
                    'password': password,
                    'school_info': school_info,
                    'login_url': login_url
                }

                html_content = render_to_string('emails/parent_welcome_email.html', context)

                email_message = EmailMultiAlternatives(
                    subject=mail_subject,
                    body=f"Hello {parent.first_name},\n\nYour account has been created. Please log in at {login_url} with the username: {username} and password: {password}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[parent.email]
                )
                email_message.attach_alternative(html_content, "text/html")
                email_message.send()

            except Exception as e:
                # It's good practice to log any errors during email sending
                # so it doesn't crash the parent creation process.
                print(f"Error sending welcome email to {parent.email}: {e}")

