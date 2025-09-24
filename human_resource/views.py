import logging
import random
import string

from django.db import transaction, IntegrityError
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.models import User, Group, Permission
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
)
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from .models import StaffModel, StaffProfileModel, HRSettingModel
from .forms import StaffForm, GroupForm, HRSettingForm

logger = logging.getLogger(__name__)


# -------------------------
# Mixins & Helpers
# -------------------------
class FlashFormErrorsMixin:
    """
    Flashes form errors using the messages framework on form_invalid, then redirects.
    """

    def form_invalid(self, form):
        try:
            for field, errors in form.errors.items():
                label = form.fields.get(field).label if form.fields.get(field) else field
                for error in errors:
                    messages.error(self.request, f"{label}: {error}")
        except Exception:
            logger.exception("Error while processing form_invalid messages.")
            messages.error(self.request, "An unexpected error occurred with the form.")
        return redirect(self.get_success_url())


def _send_credentials_email(staff, username, password):
    """
    Renders and sends a credentials email to a staff member.
    Returns True if successful, False otherwise.
    """
    if not staff.email:
        logger.warning(f"Attempted to send credentials to staff ID {staff.id} with no email.")
        return False
    try:
        context = {
            'staff_name': f"{staff.first_name} {staff.last_name}",
            'username': username,
            'password': password,
            'login_url': settings.LOGIN_URL,  # Assumes LOGIN_URL is set in settings.py
        }
        # We will need to create this template later
        html_content = render_to_string('human_resource/email/credentials.html', context)

        send_mail(
            subject="Your Staff Portal Account Credentials",
            message=f"Hello {context['staff_name']},\n\nYour account has been created. Username: {username}, Password: {password}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[staff.email],
            fail_silently=False,
            html_message=html_content
        )
        return True
    except Exception:
        logger.exception(f"Failed to send credentials email to {staff.email}")
        return False


# -------------------------
# Staff Views
# -------------------------
class StaffListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = StaffModel
    permission_required = 'human_resource.view_staffmodel'
    template_name = 'human_resource/staff/index.html'
    context_object_name = "staff_list"

    def get_queryset(self):
        return StaffModel.objects.all().order_by('first_name')


class StaffCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = StaffModel
    permission_required = 'human_resource.add_staffmodel'
    form_class = StaffForm
    template_name = 'human_resource/staff/create.html'
    success_message = 'Staff Successfully Registered'

    def get_success_url(self):
        return reverse('staff_detail', kwargs={'pk': self.object.pk})

    def form_valid(self, form):
        """
        Create the Staff instance, then create the associated User and StaffProfile.
        """
        try:
            with transaction.atomic():
                # First, save the StaffModel instance to get an ID
                staff_instance = form.save()

                # Now, create the User account
                username = staff_instance.staff_id
                password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))

                user, created = User.objects.get_or_create(
                    email=staff_instance.email,
                    defaults={'username': username, 'first_name': staff_instance.first_name,
                              'last_name': staff_instance.last_name}
                )
                if created:
                    user.set_password(password)
                    user.save()

                # Link User to Staff via StaffProfileModel
                StaffProfileModel.objects.create(
                    user=user,
                    staff=staff_instance,
                    default_password=password  # Save password temporarily if email fails
                )

                # Add user to selected group
                if staff_instance.group:
                    staff_instance.group.user_set.add(user)

                # Attempt to send email
                if _send_credentials_email(staff_instance, username, password):
                    messages.success(self.request,
                                     f"Staff '{staff_instance}' created and credentials sent to {staff_instance.email}.")
                else:
                    messages.warning(self.request,
                                     f"Staff '{staff_instance}' created, but failed to send credentials email.")

                # Use self.object for the redirect in get_success_url
                self.object = staff_instance
                return super().form_valid(form)

        except IntegrityError:
            messages.error(self.request, "A user with this email or username (staff ID) may already exist.")
            return self.form_invalid(form)
        except Exception as e:
            logger.exception("Error during staff and user creation.")
            messages.error(self.request, f"An unexpected error occurred: {e}")
            return self.form_invalid(form)


class StaffDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = StaffModel
    permission_required = 'human_resource.view_staffmodel'
    template_name = 'human_resource/staff/detail.html'
    context_object_name = "staff"


class StaffUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = StaffModel
    permission_required = 'human_resource.change_staffmodel'
    form_class = StaffForm
    template_name = 'human_resource/staff/edit.html'
    success_message = 'Staff Information Successfully Updated'
    context_object_name = "staff"

    def get_success_url(self):
        return reverse('staff_detail', kwargs={'pk': self.object.pk})


class StaffDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = StaffModel
    permission_required = 'human_resource.delete_staffmodel'
    template_name = 'human_resource/staff/delete.html'
    context_object_name = "staff"

    # We will create a custom success message, so the default one is not needed.

    def get_success_url(self):
        return reverse('staff_index')

    def post(self, request, *args, **kwargs):
        """
        Overrides the post method to ensure the staff member's User account is
        also deleted and the entire operation is atomic.
        """
        # Get the object before deleting it to use its name in the message
        self.object = self.get_object()
        staff_name = str(self.object)

        try:
            # Use a transaction to ensure that either both the staff and user are
            # deleted, or neither is, preventing orphaned user accounts.
            with transaction.atomic():
                # The default delete() method on the object will trigger the
                # CASCADE delete for StaffProfileModel and then the User model.
                # We are simply calling the default logic from the parent class
                # inside our safe transaction block.
                response = super().post(request, *args, **kwargs)

            messages.success(request,
                             f"Staff '{staff_name}' and their associated user account have been permanently deleted.")
            return response

        except Exception as e:
            # If anything goes wrong, log the error and inform the user.
            logger.error(f"Error deleting staff '{staff_name}' and their user account: {e}", exc_info=True)
            messages.error(request, "An unexpected error occurred. The staff member could not be deleted.")
            return redirect(self.get_success_url())


# -------------------------
# Staff Account Actions
# -------------------------
@login_required
@permission_required("human_resource.change_staffmodel", raise_exception=True)
def generate_staff_login(request, pk):
    """
    Creates a user account for an existing staff member if they don't have one.
    """
    staff = get_object_or_404(StaffModel, pk=pk)
    try:
        # Check if a profile and user already exist
        if hasattr(staff, 'staff_profile') and getattr(staff.staff_profile, 'user', None):
            messages.warning(request, f"'{staff}' already has an active user account.")
            return redirect('staff_detail', pk=pk)

        if not staff.email:
            messages.error(request, "Cannot create an account for a staff member with no email address.")
            return redirect('staff_detail', pk=pk)

        with transaction.atomic():
            username = staff.staff_id
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))

            # Create the user, handling potential username clashes
            try:
                user = User.objects.create_user(username=username, email=staff.email, password=password)
            except IntegrityError:
                username = f"{username}_{random.randint(100, 999)}"
                user = User.objects.create_user(username=username, email=staff.email, password=password)

            # Link user to staff via profile
            StaffProfileModel.objects.create(user=user, staff=staff, default_password=password)

            if _send_credentials_email(staff, username, password):
                messages.success(request, f"Login account created for '{staff}' and credentials have been emailed.")
            else:
                messages.warning(request,
                                 f"Login account created for '{staff}', but the credentials email could not be sent.")

    except Exception as e:
        logger.exception(f"Error generating login for staff ID {pk}")
        messages.error(request, f"An unexpected error occurred: {e}")

    return redirect('staff_detail', pk=pk)


@login_required
@permission_required("human_resource.change_staffmodel", raise_exception=True)
def update_staff_login(request, pk):
    staff = get_object_or_404(StaffModel, pk=pk)
    try:
        profile = staff.staff_profile
        user = profile.user

        password = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        user.set_password(password)
        user.save()

        profile.default_password = password
        profile.save()

        if _send_credentials_email(staff, user.username, password):
            messages.success(request, f"Password for '{staff}' has been reset and emailed.")
        else:
            messages.warning(request, f"Password for '{staff}' was reset, but the email could not be sent.")

    except StaffProfileModel.DoesNotExist:
        messages.error(request, f"'{staff}' does not have a user account to update.")
    except Exception as e:
        logger.exception(f"Error updating login for staff ID {pk}")
        messages.error(request, f"An unexpected error occurred: {e}")

    return redirect('staff_detail', pk=pk)


@login_required
@permission_required("human_resource.change_staffmodel", raise_exception=True)
def disable_staff(request, pk):
    staff = get_object_or_404(StaffModel, pk=pk)
    staff.status = 'inactive'
    staff.save()
    try:
        user = staff.staff_profile.user
        user.is_active = False
        user.save()
        messages.success(request, f"'{staff}' and their user account have been disabled.")
    except StaffProfileModel.DoesNotExist:
        messages.success(request, f"'{staff}' has been disabled (no user account found).")
    return redirect('staff_detail', pk=pk)


@login_required
@permission_required("human_resource.change_staffmodel", raise_exception=True)
def enable_staff(request, pk):
    staff = get_object_or_404(StaffModel, pk=pk)
    staff.status = 'active'
    staff.save()
    try:
        user = staff.staff_profile.user
        user.is_active = True
        user.save()
        messages.success(request, f"'{staff}' and their user account have been enabled.")
    except StaffProfileModel.DoesNotExist:
        messages.success(request, f"'{staff}' has been enabled (no user account found).")
    return redirect('staff_detail', pk=pk)


# -------------------------
# Group & Permission Views
# -------------------------
class GroupListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Group
    permission_required = 'auth.view_group'
    template_name = 'human_resource/group/index.html'
    context_object_name = "group_list"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = GroupForm()
        return context


class GroupCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = Group
    permission_required = 'auth.add_group'
    form_class = GroupForm
    success_message = 'Permission Group Created Successfully'

    def get_success_url(self):
        return reverse('group_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)


class GroupUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = Group
    permission_required = 'auth.change_group'
    form_class = GroupForm
    success_message = 'Permission Group Updated Successfully'

    def get_success_url(self):
        return reverse('group_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(self.get_success_url())

        """
        Overrides the dispatch method to add a protection check.
        This prevents critical system groups from being edited.
        """
        # Get the object that is about to be acted upon
        group_to_edit = self.get_object()

        # Define a list of protected group names (case-insensitive check)
        protected_groups = ['teachers']

        if group_to_edit.name.lower() in protected_groups:
            # If the group is protected, show an error message and redirect
            messages.error(
                self.request,
                f"The '{group_to_edit.name}' group is a critical part of the system and cannot be edited."
            )
            return redirect('group_index')

        # If the group is not protected, proceed with the normal view logic

        return super().dispatch(request, *args, **kwargs)


class GroupDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Group
    permission_required = 'auth.delete_group'
    template_name = 'human_resource/group/delete.html'
    context_object_name = "group"
    success_message = 'Group Successfully Deleted'

    def get_success_url(self):
        return reverse('group_index')

    def dispatch(self, request, *args, **kwargs):
        """
        Overrides the dispatch method to add a protection check.
        This prevents critical system groups from being deleted.
        """
        # Get the object that is about to be acted upon
        group_to_delete = self.get_object()

        # Define a list of protected group names (case-insensitive check)
        protected_groups = ['teachers']

        if group_to_delete.name.lower() in protected_groups:
            # If the group is protected, show an error message and redirect
            messages.error(
                self.request,
                f"The '{group_to_delete.name}' group is a critical part of the system and cannot be deleted."
            )
            return redirect('group_index')

        # If the group is not protected, proceed with the normal view logic
        return super().dispatch(request, *args, **kwargs)


@login_required
@permission_required("auth.change_group", raise_exception=True)
def group_permission_view(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        permission_ids = request.POST.getlist('permissions')
        try:
            group.permissions.set(permission_ids)
            messages.success(request, f"Permissions for group '{group.name}' updated successfully.")
        except Exception as e:
            logger.exception(f"Failed to update permissions for group ID {pk}")
            messages.error(request, f"An error occurred: {e}")
        return redirect('group_index')

    context = {
        'group': group,
        'permission_list': Permission.objects.all(),
    }
    return render(request, 'human_resource/group/permission.html', context)


# -------------------------
# HR Setting Views (Singleton)
# -------------------------
class HRSettingDetailView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'human_resource.view_hrsettingmodel'
    template_name = 'human_resource/setting/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hr_setting'] = HRSettingModel.objects.first()
        return context


class HRSettingCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = HRSettingModel
    permission_required = 'human_resource.add_hrsettingmodel'
    form_class = HRSettingForm
    template_name = 'human_resource/setting/create.html'
    success_message = 'HR Settings Created Successfully'

    def get_success_url(self):
        return reverse('hr_setting_detail')

    def dispatch(self, request, *args, **kwargs):
        if HRSettingModel.objects.exists():
            return redirect('hr_setting_edit')
        return super().dispatch(request, *args, **kwargs)


class HRSettingUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = HRSettingModel
    permission_required = 'human_resource.change_hrsettingmodel'
    form_class = HRSettingForm
    template_name = 'human_resource/setting/create.html'
    success_message = 'HR Settings Updated Successfully'

    def get_object(self):
        return HRSettingModel.objects.first()

    def get_success_url(self):
        return reverse('hr_setting_detail')

