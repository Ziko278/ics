import io
import logging
import random
import string

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.storage import FileSystemStorage
from django.db import transaction, IntegrityError
from django.db.models import Count
from django.db.transaction import non_atomic_requests
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.models import User, Group, Permission
from django.utils.decorators import method_decorator
from django.views.generic import (
    ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
)
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from xlsxwriter import Workbook

from .models import StaffModel, StaffProfileModel, HRSettingModel
from .forms import StaffForm, GroupForm, HRSettingForm, StaffUploadForm, StaffProfileUpdateForm
from human_resource.tasks import process_staff_upload

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


@method_decorator(non_atomic_requests, name='dispatch')
class StaffCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = StaffModel
    permission_required = 'human_resource.add_staffmodel'
    form_class = StaffForm
    template_name = 'human_resource/staff/create.html'

    def get_success_url(self):
        # self.object is set in form_valid before redirecting
        return reverse('staff_detail', kwargs={'pk': self.object.pk})

    def _send_credentials_and_set_messages(self, staff, username, password):
        """
        Handles sending email and setting the appropriate success/warning message.
        This method is only called after the database transaction is successful.
        """
        # Only attempt to send an email if one was provided.
        if staff.email:
            if _send_credentials_email(staff, username, password):
                messages.success(self.request,
                                 f"Staff '{staff}' created and credentials sent to {staff.email}.")
            else:
                messages.warning(self.request,
                                 f"Staff '{staff}' created, but failed to send credentials via email.")
        else:
            # If no email, just show a success message without mentioning credentials.
            messages.success(self.request, f"Staff '{staff}' created successfully (no email provided for credentials).")

    def form_valid(self, form):
        """
        Creates Staff, User, and Profile in a transaction.
        Sends email after successful commit.
        """
        try:
            # Use atomic block for database operations only
            with transaction.atomic():
                # Prepare the staff instance
                staff_instance = form.save(commit=False)

                # Generate staff_id if needed
                if not staff_instance.staff_id:
                    staff_instance.staff_id = staff_instance.generate_unique_staff_id()

                username = staff_instance.staff_id

                # Check if username already exists
                if User.objects.filter(username=username).exists():
                    raise ValueError(f"Username {username} already exists")

                # Check if email already exists
                if staff_instance.email and User.objects.filter(email=staff_instance.email).exists():
                    raise ValueError(f"Email {staff_instance.email} already exists")

                # Generate password
                password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

                # Create user
                user_fields = {
                    'username': username,
                    'password': password,
                    'first_name': staff_instance.first_name,
                    'last_name': staff_instance.staff_id,
                }
                if staff_instance.email:
                    user_fields['email'] = staff_instance.email

                user = User.objects.create_user(**user_fields)

                # Save staff with skip flag
                staff_instance.save(skip_user_sync=True)

                # Create profile
                StaffProfileModel.objects.create(
                    user=user,
                    staff=staff_instance,
                    default_password=password
                )

                # Add to group
                if staff_instance.group:
                    staff_instance.group.user_set.add(user)

                # Set for redirect
                self.object = staff_instance

            # Transaction committed successfully - now send email
            self._send_credentials_and_set_messages(staff_instance, username, password)
            return HttpResponseRedirect(self.get_success_url())

        except ValueError as e:
            # Custom validation errors
            messages.error(self.request, str(e))
            return self.form_invalid(form)

        except IntegrityError as e:
            # Database constraint violations
            logger.exception("IntegrityError during staff creation")
            if 'username' in str(e).lower():
                messages.error(self.request, f"Staff ID already exists in the system.")
            elif 'email' in str(e).lower():
                messages.error(self.request, "Email address already exists in the system.")
            else:
                messages.error(self.request, "A database error occurred. Please check for duplicates.")
            return self.form_invalid(form)

        except Exception as e:
            # Catch-all for other errors
            logger.exception("Unexpected error during staff creation")
            messages.error(self.request, f"An unexpected error occurred: {str(e)}")
            return self.form_invalid(form)


class StaffDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = StaffModel
    permission_required = 'human_resource.view_staffmodel'
    template_name = 'human_resource/staff/detail.html'
    context_object_name = "staff"


class StaffUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = StaffModel
    permission_required = 'human_resource.add_staffmodel'
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
@permission_required("human_resource.add_staffmodel", raise_exception=True)
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
            password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

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
@permission_required("human_resource.add_staffmodel", raise_exception=True)
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
@permission_required("human_resource.add_staffmodel", raise_exception=True)
def disable_staff(request, pk):
    staff = get_object_or_404(StaffModel, pk=pk)
    staff.status = 'inactive'
    staff.save(skip_user_sync=True)  # Add this flag

    try:
        user = staff.staff_profile.user
        user.is_active = False
        user.save()
        messages.success(request, f"'{staff}' and their user account have been disabled.")
    except StaffProfileModel.DoesNotExist:
        messages.success(request, f"'{staff}' has been disabled (no user account found).")

    return redirect('staff_detail', pk=pk)


@login_required
@permission_required("human_resource.add_staffmodel", raise_exception=True)
def enable_staff(request, pk):
    staff = get_object_or_404(StaffModel, pk=pk)
    staff.status = 'active'
    staff.save(skip_user_sync=True)  # Add this flag

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
    permission_required = 'auth.add_group'
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
    permission_required = 'auth.add_group'
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
    permission_required = 'auth.add_group'
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
@permission_required("auth.add_group", raise_exception=True)
def group_permission_view(request, pk):
    group = get_object_or_404(Group, pk=pk)
    if request.method == 'POST':
        permissions = request.POST.getlist('permissions[]')
        permission_list = []
        for permission_code in permissions:
            permission = Permission.objects.filter(codename=permission_code).first()
            if permission:
                permission_list.append(permission.id)
        try:
            group.permissions.set(permission_list)
            messages.success(request, 'Group Permission Successfully Updated')
        except Exception:
            logger.exception("Failed updating group permissions for group id=%s", pk)
            messages.error(request, "Failed to update group permissions. Contact admin.")
        return redirect(reverse('group_index'))

    context = {
        'group': group,
        'permission_codenames': group.permissions.all().values_list('codename', flat=True),
        'permission_list': Permission.objects.all(),
    }
    return render(request, 'human_resource/group/permission.html', context)


# -------------------------
# HR Setting Views (Singleton)
# -------------------------
class HRSettingDetailView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'human_resource.change_hrsettingmodel'
    template_name = 'human_resource/setting/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hr_setting'] = HRSettingModel.objects.first()
        return context


class HRSettingCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = HRSettingModel
    permission_required = 'human_resource.change_hrsettingmodel'
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


@login_required
@permission_required("human_resource.add_staffmodel", raise_exception=True)
def staff_upload_view(request):
    """
    Handles the file upload form and initiates the background task for processing.
    """
    if request.method == 'POST':
        form = StaffUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['excel_file']

            # Use FileSystemStorage to save the file securely.
            # This prevents filename conflicts and saves it in your MEDIA_ROOT.
            fs = FileSystemStorage()
            filename = fs.save(uploaded_file.name, uploaded_file)
            file_path = fs.path(filename)

            # Dispatch the background task with the path to the saved file.
            process_staff_upload.delay(file_path)

            # Provide immediate feedback to the user.
            messages.success(request, (
                'File uploaded successfully! The staff data is being processed in the background. '
                'You can safely navigate away from this page.'
            ))
            return redirect('staff_upload')
    else:
        form = StaffUploadForm()

    return render(request, 'human_resource/staff/upload.html', {'form': form})


@login_required
@permission_required("human_resource.view_staffmodel", raise_exception=True)
def hr_dashboard_view(request):
    """
    Displays a dashboard with key statistics about the staff.
    """
    total_staff = StaffModel.objects.count()
    active_staff = StaffModel.objects.filter(status='active').count()
    male_staff = StaffModel.objects.filter(gender='MALE').count()
    female_staff = StaffModel.objects.filter(gender='FEMALE').count()

    # Get a count of staff in each group/department
    staff_by_group = StaffModel.objects.values('group__name').annotate(
        staff_count=Count('id')
    ).order_by('-staff_count')

    context = {
        'total_staff': total_staff,
        'active_staff': active_staff,
        'male_staff': male_staff,
        'female_staff': female_staff,
        'staff_by_group': staff_by_group,
    }
    return render(request, 'human_resource/dashboard.html', context)


@login_required
def staff_profile_view(request):
    """
    Allows a logged-in staff member to view and update their own profile.
    """
    # Get the StaffModel instance linked to the currently logged-in user
    staff = get_object_or_404(StaffModel, staff_profile__user=request.user)

    if request.method == 'POST':
        form = StaffProfileUpdateForm(request.POST, request.FILES, instance=staff)
        if form.is_valid():
            form.save()  # The model's save() method will sync with the User model
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('staff_profile')
    else:
        form = StaffProfileUpdateForm(instance=staff)

    context = {
        'form': form,
        'staff': staff
    }
    return render(request, 'human_resource/staff/profile.html', context)


# human_resource/views.py

@login_required
@permission_required("human_resource.view_staffmodel", raise_exception=True)
def export_all_staff_view(request):
    """
    Exports a list of all staff with their login credentials (excluding current password) to an Excel file.
    """
    staff_list = StaffModel.objects.select_related(
        'staff_profile__user'
    ).prefetch_related('staff_profile__user__groups').order_by('last_name', 'first_name')

    if not staff_list.exists():
        messages.warning(request, "No staff members found to export.")
        return redirect(request.META.get('HTTP_REFERER', 'some_default_url_name'))

    output = io.BytesIO()
    workbook = Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet("Staff List")

    # ADDED 'Default Password' to the headers
    headers = ['Staff ID', 'Full Name', 'Username', 'Default Password', 'Role(s)', 'Email', 'Mobile']
    header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3'})
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header, header_format)

    # Write data rows
    for row_num, staff in enumerate(staff_list, 1):
        # Initialize variables with default values from the StaffModel
        full_name = f"{staff.first_name} {staff.last_name}"
        username = 'N/A'
        default_password = 'N/A' # Initialize password field
        roles = 'N/A'
        email = staff.email or 'N/A'

        # Try to get more accurate data from the linked User and Profile
        try:
            profile = staff.staff_profile
            user = profile.user

            full_name = user.get_full_name()
            username = user.username
            email = user.email
            roles = ', '.join([group.name for group in user.groups.all()])

            # FETCH THE SAVED DEFAULT PASSWORD
            default_password = profile.default_password

        except ObjectDoesNotExist:
            # This block runs if a staff member exists but has no user account linked yet.
            # The initial default values will be used.
            pass

        worksheet.write(row_num, 0, staff.staff_id)
        worksheet.write(row_num, 1, full_name)
        worksheet.write(row_num, 2, username)
        # WRITE THE PASSWORD TO THE NEW COLUMN
        worksheet.write(row_num, 3, default_password)
        worksheet.write(row_num, 4, roles)
        worksheet.write(row_num, 5, email)
        worksheet.write(row_num, 6, staff.mobile or 'N/A')

    # Auto-fit columns for better readability
    worksheet.autofit()

    workbook.close()
    output.seek(0)

    filename = "All-Staff-Credentials.xlsx"
    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response['Content-Disposition'] = f"attachment; filename={filename}"
    return response

