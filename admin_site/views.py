import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.contrib import messages
from django.contrib.auth import logout, authenticate, login
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import View, TemplateView, ListView, DetailView, CreateView, UpdateView, DeleteView
from django.db.models import Sum, F
from django.db import OperationalError
from django.utils.timezone import now

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
            today = now().date()
            # context['total_products'] = ProductModel.objects.count()
            # context['low_stock'] = ProductModel.objects.filter(quantity__lte=F('reorder_level')).count()
            # context['total_sales_today'] = SaleModel.objects.filter(sale_date__date=today).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
            # context['total_profit_today'] = SaleItemModel.objects.filter(sale__sale_date__date=today).aggregate(Sum('profit'))['profit__sum'] or 0
            # context['total_staff'] = StaffModel.objects.count()
            # context['total_returns'] = ReturnModel.objects.count()
            # context['total_suppliers'] = SupplierModel.objects.count()
            context['active_students'] = StudentModel.objects.filter(status='active').count()
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
    permission_required = 'admin_site.view_schoolinfomodel'
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
    permission_required = 'admin_site.add_schoolinfomodel'
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
    permission_required = 'admin_site.view_schoolsettingmodel'
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
    permission_required = 'admin_site.add_schoolsettingmodel'
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
    permission_required = 'admin_site.view_classsectionmodel'
    template_name = 'admin_site/class_section/index.html'
    context_object_name = "class_section_list"
    queryset = ClassSectionModel.objects.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = ClassSectionForm()
        return context


class ClassSectionCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, SuccessMessageMixin, CreateView):
    model = ClassSectionModel
    permission_required = 'admin_site.add_classsectionmodel'
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
    permission_required = 'admin_site.change_classsectionmodel'
    form_class = ClassSectionForm
    success_message = 'Class Section Updated Successfully'
    success_url = reverse_lazy('class_section_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(reverse('class_section_index'))
        return super().dispatch(request, *args, **kwargs)


class ClassSectionDeleteView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ClassSectionModel
    permission_required = 'admin_site.delete_classsectionmodel'
    template_name = 'admin_site/class_section/delete.html'
    success_message = 'Class Section Deleted Successfully'
    success_url = reverse_lazy('class_section_index')


class ClassListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ClassesModel
    permission_required = 'admin_site.view_classesmodel'
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
    permission_required = 'admin_site.view_classesmodel'
    template_name = 'admin_site/class/detail.html'
    context_object_name = "class"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = ClassForm()
        context['class_section_list'] = ClassSectionModel.objects.all()
        return context


class ClassUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, SuccessMessageMixin, UpdateView):
    model = ClassesModel
    permission_required = 'admin_site.change_classesmodel'
    form_class = ClassForm
    success_message = 'Class Updated Successfully'

    def get_success_url(self):
        return reverse('class_detail', kwargs={'pk': self.object.pk})


class ClassDeleteView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ClassesModel
    permission_required = 'admin_site.delete_classesmodel'
    template_name = 'admin_site/class/delete.html'
    success_message = 'Class Deleted Successfully'
    success_url = reverse_lazy('class_index')
    context_object_name = "class"


class ClassSectionInfoDetailView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'admin_site.view_classsectioninfomodel'
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
    permission_required = 'admin_site.change_classsectioninfomodel'
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
                return redirect(reverse('admin_dashboard'))

            # 2. Check for Staff Profile
            # hasattr is an efficient way to check for a related object without a try/except block
            if hasattr(user, 'staff_profile'):
                messages.success(request, f'Welcome back, {user.staff_profile.staff}!')
                return redirect(reverse('admin_dashboard'))

            # 3. Check for Parent Profile
            elif hasattr(user, 'parent_profile'):
                messages.success(request, f'Welcome back, {user.parent_profile.parent}!')
                # TODO: Create a 'parent_dashboard' URL and view
                # For now, we redirect to a placeholder or the main admin dashboard
                return redirect(reverse('admin_dashboard'))

            # 4. If user has no associated profile, deny access and log out
            else:
                messages.error(request, 'Your account is not associated with any role. Access Denied.')
                logout(request) # CRITICAL FIX: Log the user out
                return redirect(reverse('login')) # Use your actual login URL name

        else:
            messages.error(request, 'Invalid username or password.')
            return redirect(reverse('login')) # Use your actual login URL name

    return render(request, 'admin_site/sign_in.html')


def logout_view(request):
    logout(request)
    messages.info(request, "You have been successfully signed out.")
    return redirect('admin_login')

