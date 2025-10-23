import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import logout, authenticate, login, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.generic import View, TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.db.models import Sum, F, Count
from django.db import OperationalError
from django.utils.timezone import now

from inventory.models import ItemModel, SaleItemModel, SaleModel, SupplierModel
from .models import (
    ActivityLogModel, SchoolInfoModel, SchoolSettingModel, ClassSectionModel,
    ClassesModel, ClassSectionInfoModel
)
from .forms import (
    SchoolInfoForm, SchoolSettingForm, ClassSectionForm, ClassForm, ClassSectionInfoForm, SessionForm
)

# Preserving imports from your other apps as requested
from human_resource.models import StaffModel
from student.models import StudentModel

logger = logging.getLogger(__name__)


class FlashFormErrorsMixin:
    """
    Flashes form errors to the messages framework and redirects on invalid form submission.
    """
    def form_invalid(self, form):
        redirect_url = self.get_success_url()
        try:
            for field, errors in form.errors.items():
                field_name = form.fields.get(field).label if form.fields.get(field) else field.replace('_', ' ').title()
                for error in errors:
                    messages.error(self.request, f"{field_name}: {error}")
        except Exception as e:
            logger.exception(f"Error processing form_invalid in {self.__class__.__name__}: {e}")
            messages.error(self.request, "There was an error processing the form. Please check the inputs and try again.")
        return redirect(redirect_url)


class AdminDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'admin_site/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            today = timezone.now().date()

            # --- Academic & General Info ---
            context['academic_info'] = SchoolSettingModel.objects.select_related('session', 'term').first()
            context['active_students'] = StudentModel.objects.filter(status='active').count()
            context['total_staff'] = StaffModel.objects.count()

            # --- Inventory & Sales Info ---
            context['total_products'] = ItemModel.objects.count()

            # Use the efficient low-stock query we created
            low_stock_query = ItemModel.objects.annotate(
                total_quantity=F('shop_quantity') + F('store_quantity')
            ).filter(total_quantity__lte=F('reorder_level'))
            context['low_stock'] = low_stock_query.count()

            # Calculate today's sales and profit
            sales_items_today = SaleItemModel.objects.filter(sale__created_at__date=today)
            total_sales_data = sales_items_today.aggregate(
                total_revenue=Sum(F('quantity') * F('unit_price'))
            )
            total_discounts_today = SaleModel.objects.filter(created_at__date=today).aggregate(
                total_discount=Sum('discount')
            )['total_discount'] or 0

            context['total_sales_today'] = (total_sales_data['total_revenue'] or 0) - total_discounts_today

            profit_data = sales_items_today.aggregate(
                total_profit=Sum((F('unit_price') - F('unit_cost')) * F('quantity'))
            )
            context['total_profit_today'] = profit_data['total_profit'] or 0

            context['total_suppliers'] = SupplierModel.objects.filter(is_active=True).count()

            # --- Data for Student Distribution Pie Chart ---
            context['student_class_list'] = StudentModel.objects.filter(
                status='active'
            ).values(
                'student_class__name'  # Group by the class name
            ).annotate(
                number_of_students=Count('id')  # Count students in each group
            ).order_by('student_class__name')

        except OperationalError as e:
            logger.error(f"DATABASE ERROR in AdminDashboardView: {e}")
            messages.error(self.request, "A database error occurred. Some dashboard data may be unavailable.")
        except Exception as e:
            logger.error(f"UNEXPECTED ERROR in AdminDashboardView: {e}", exc_info=True)
            messages.warning(self.request, "An unexpected error occurred while loading dashboard data.")

        return context


class ActivityLogView(LoginRequiredMixin, ListView):
    model = ActivityLogModel
    permission_required = 'admin_site.view_activitylogmodel'
    template_name = 'admin_site/activity_log.html'
    context_object_name = "activity_log_list"
    queryset = ActivityLogModel.objects.order_by('-created_at')


# --- Singleton Views for SchoolInfo (Dedicated Pages) ---
class SchoolInfoDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SchoolInfoModel
    permission_required = 'admin_site.change_schoolinfomodel'
    template_name = 'admin_site/school_info/detail.html'
    context_object_name = "school_info"

    def dispatch(self, request, *args, **kwargs):
        if not SchoolInfoModel.objects.exists():
            messages.info(request, "Please create the school information first.")
            return redirect(reverse('school_info_create'))
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return SchoolInfoModel.objects.first()


class SchoolInfoCreateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = SchoolInfoModel
    permission_required = 'admin_site.change_schoolinfomodel'
    form_class = SchoolInfoForm
    template_name = 'admin_site/school_info/create.html'
    success_message = 'School Information Created Successfully'

    def get_success_url(self):

        return reverse('school_info_detail')

    def dispatch(self, request, *args, **kwargs):
        if SchoolInfoModel.objects.exists():
            info = SchoolInfoModel.objects.first()
            return redirect(reverse('school_info_edit', kwargs={'pk': info.pk}))
        return super().dispatch(request, *args, **kwargs)


class SchoolInfoUpdateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    model = SchoolInfoModel
    permission_required = 'admin_site.change_schoolinfomodel'
    form_class = SchoolInfoForm
    template_name = 'admin_site/school_info/create.html'
    success_message = 'School Information Updated Successfully'

    def get_success_url(self):
        return reverse('school_info_detail')


# --- Singleton Views for SchoolSetting (Dedicated Pages) ---
class SchoolSettingDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SchoolSettingModel
    permission_required = 'admin_site.change_schoolsettingmodel'
    template_name = 'admin_site/school_setting/detail.html'
    context_object_name = "school_setting"

    def dispatch(self, request, *args, **kwargs):
        if not SchoolSettingModel.objects.exists():
            messages.info(request, "Please create the school settings first.")
            return redirect(reverse('school_setting_create'))
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return SchoolSettingModel.objects.first()


class SchoolSettingCreateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = SchoolSettingModel
    permission_required = 'admin_site.change_schoolsettingmodel'
    form_class = SchoolSettingForm
    template_name = 'admin_site/school_setting/create.html'
    success_message = 'Settings Created Successfully'

    def get_success_url(self):
        return reverse('school_setting_detail', kwargs={'pk': self.object.pk})

    def dispatch(self, request, *args, **kwargs):
        if SchoolSettingModel.objects.exists():
            setting = SchoolSettingModel.objects.first()
            return redirect(reverse('school_setting_edit', kwargs={'pk': setting.pk}))
        return super().dispatch(request, *args, **kwargs)


class SchoolSettingUpdateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    model = SchoolSettingModel
    permission_required = 'admin_site.change_schoolsettingmodel'
    form_class = SchoolSettingForm
    template_name = 'admin_site/school_setting/create.html'
    success_message = 'Settings Updated Successfully'

    def get_success_url(self):
        return reverse('school_setting_detail')


# --- CRUD Views for ClassSection (Single Page Pattern) ---
class ClassSectionListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ClassSectionModel
    permission_required = 'admin_site.add_classesmodel'
    template_name = 'admin_site/class_section/index.html'
    context_object_name = "class_section_list"
    queryset = ClassSectionModel.objects.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = ClassSectionForm()
        return context


class ClassSectionCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, SuccessMessageMixin, CreateView):
    model = ClassSectionModel
    permission_required = 'admin_site.add_classesmodel'
    form_class = ClassSectionForm
    success_message = 'Class Section Added Successfully'

    def get_success_url(self):
        return reverse('class_section_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(reverse('class_section_index'))
        return super().dispatch(request, *args, **kwargs)


class ClassSectionUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, SuccessMessageMixin, UpdateView):
    model = ClassSectionModel
    permission_required = 'admin_site.add_classesmodel'
    form_class = ClassSectionForm
    success_message = 'Class Section Updated Successfully'
    success_url = reverse_lazy('class_section_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(reverse('class_section_index'))
        return super().dispatch(request, *args, **kwargs)


class ClassSectionDeleteView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ClassSectionModel
    permission_required = 'admin_site.add_classesmodel'
    template_name = 'admin_site/class_section/delete.html'
    success_message = 'Class Section Deleted Successfully'
    success_url = reverse_lazy('class_section_index')


class ClassListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ClassesModel
    permission_required = 'admin_site.add_classesmodel'
    template_name = 'admin_site/class/index.html'
    context_object_name = "class_list"
    queryset = ClassesModel.objects.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = ClassForm()
        context['class_section_list'] = ClassSectionModel.objects.all()
        return context


class ClassCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, SuccessMessageMixin, CreateView):
    model = ClassesModel
    permission_required = 'admin_site.add_classesmodel'
    form_class = ClassForm
    success_message = 'Class Added Successfully'
    success_url = reverse_lazy('class_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(reverse('class_index'))
        return super().dispatch(request, *args, **kwargs)


class ClassDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ClassesModel
    permission_required = 'admin_site.add_classesmodel'
    template_name = 'admin_site/class/detail.html'
    context_object_name = "class"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = ClassForm()
        context['class_section_list'] = ClassSectionModel.objects.all()
        return context


class ClassUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, SuccessMessageMixin, UpdateView):
    model = ClassesModel
    permission_required = 'admin_site.add_classesmodel'
    form_class = ClassForm
    success_message = 'Class Updated Successfully'

    def get_success_url(self):
        return reverse('class_detail', kwargs={'pk': self.object.pk})


class ClassDeleteView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ClassesModel
    permission_required = 'admin_site.add_classesmodel'
    template_name = 'admin_site/class/delete.html'
    success_message = 'Class Deleted Successfully'
    success_url = reverse_lazy('class_index')
    context_object_name = "class"


class ClassSectionInfoDetailView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'admin_site.add_classesmodel'
    template_name = 'admin_site/class_section_info/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        class_pk = self.kwargs.get('class_pk')
        section_pk = self.kwargs.get('section_pk')
        student_class = get_object_or_404(ClassesModel, pk=class_pk)
        section = get_object_or_404(ClassSectionModel, pk=section_pk)
        info, created = ClassSectionInfoModel.objects.get_or_create(student_class=student_class, section=section)
        if created:
            messages.info(self.request, f"Created a new roster for {student_class} - {section}.")
        context['student_class'] = student_class
        context['class_section'] = section
        context['class_section_info'] = info
        context['form'] = ClassSectionInfoForm(instance=info)
        return context


class ClassSectionInfoUpdateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    model = ClassSectionInfoModel
    permission_required = 'admin_site.add_classesmodel'
    form_class = ClassSectionInfoForm
    success_message = 'Class Roster Information Updated Successfully'

    def get_object(self, queryset=None):
        # The URL passes the direct PK of the ClassSectionInfoModel instance
        pk = self.kwargs.get('pk')
        return get_object_or_404(ClassSectionInfoModel, pk=pk)

    def get_success_url(self):
        return reverse('class_section_info_detail', kwargs={'class_pk': self.object.student_class.pk, 'section_pk': self.object.section.pk})


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            # --- Remember Me Logic ---
            remember_me = request.POST.get('remember_me')
            if remember_me:
                # Set session to expire in 30 days
                request.session.set_expiry(3600 * 24 * 30)
            else:
                # Session expires when browser closes
                request.session.set_expiry(0)

            # --- Role-Based Redirect Logic ---
            login(request, user)

            # 1. Check for Superuser
            if user.is_superuser:
                messages.success(request, f'Welcome back, {user.username.title()}!')
                return redirect(reverse('admin_dashboard')) # Keep admin redirect

            # 2. Check for Staff Profile
            if hasattr(user, 'staff_profile'):
                messages.success(request, f'Welcome back, {user.staff_profile.staff}!')
                return redirect(reverse('admin_dashboard')) # Keep staff redirect

            # 3. Check for Parent Profile
            elif hasattr(user, 'parent_profile'):
                # Clear any previous ward selection from session
                if 'selected_ward_id' in request.session:
                    del request.session['selected_ward_id']
                messages.success(request, f'Welcome back, {user.parent_profile.parent.first_name}!')
                # Redirect to the parent portal ward selection page
                return redirect(reverse('select_ward'))

            # 4. If user has no associated profile, deny access and log out
            else:
                messages.error(request, 'Your account is not associated with any role. Access Denied.')
                logout(request)
                return redirect(reverse('login')) # Use your actual login URL name

        else:
            # Invalid credentials
            messages.error(request, 'Invalid username or password.')
            # Redirect back to login page
            return redirect(reverse('login')) # Use your actual login URL name

    # For GET requests, just show the login form
    return render(request, 'admin_site/sign_in.html')


def logout_view(request):
    logout(request)
    messages.info(request, "You have been successfully signed out.")
    return redirect('login')


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def change_password_view(request):
    """
    View to handle password change for authenticated users.
    Validates current password and updates to new password.
    """

    if request.method == 'POST':
        # Get form data
        current_password = request.POST.get('current_password', '').strip()
        new_password1 = request.POST.get('new_password1', '').strip()
        new_password2 = request.POST.get('new_password2', '').strip()

        # Validation
        errors = []

        # Check if all fields are provided
        if not current_password:
            errors.append("Current password is required.")

        if not new_password1:
            errors.append("New password is required.")

        if not new_password2:
            errors.append("Password confirmation is required.")

        # Check if new passwords match
        if new_password1 and new_password2 and new_password1 != new_password2:
            errors.append("New passwords do not match.")

        # Check password length and complexity
        if new_password1 and len(new_password1) < 8:
            errors.append("New password must be at least 8 characters long.")

        # Check if new password is different from current
        if current_password and new_password1 and current_password == new_password1:
            errors.append("New password must be different from current password.")

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'admin_site/user/change_password.html')

        # Verify current password
        user = authenticate(username=request.user.username, password=current_password)
        if user is None:
            messages.error(request, "Current password is incorrect.")
            logger.warning(
                f"Failed password change attempt for user {request.user.username} - incorrect current password")
            return render(request, 'admin_site/user/change_password.html')

        try:
            # Change password
            user.set_password(new_password1)
            user.save()

            # Keep user logged in after password change
            update_session_auth_hash(request, user)

            messages.success(request, "Your password has been successfully changed!")
            logger.info(f"Password successfully changed for user {request.user.username}")

            # Redirect to dashboard or profile page
            return redirect('admin_dashboard')  # Change this to your desired redirect URL

        except Exception as e:
            logger.exception(f"Error changing password for user {request.user.username}: {str(e)}")
            messages.error(request, "An error occurred while changing your password. Please try again.")
            return render(request, 'admin_site/user/change_password.html')

    # GET request - show the form
    return render(request, 'admin_site/user/change_password.html')
