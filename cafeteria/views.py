from datetime import date

from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView
from django.shortcuts import redirect, get_object_or_404

from admin_site.models import SessionModel, TermModel, SchoolSettingModel
from cafeteria.models import MealModel, CafeteriaSettingModel, MealCollectionModel
from cafeteria.forms import MealForm, CafeteriaSettingForm
from finance.models import InvoiceModel
from human_resource.models import StaffModel
from student.models import StudentModel


# ===================================================================
# Mixins
# ===================================================================
class FlashFormErrorsMixin:
    """
    Handles form errors by adding them to Django's messages framework and redirecting.
    """

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            label = form.fields.get(field).label if form.fields.get(field) else field.replace('_', ' ').title()
            for error in errors:
                messages.error(self.request, f"{label}: {error}")
        return redirect(self.get_success_url())


# ===================================================================
# Meal Type Views (Single Page Interface)
# ===================================================================
class MealListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = MealModel
    permission_required = 'cafeteria.view_mealmodel'
    template_name = 'cafeteria/meal/index.html'
    context_object_name = 'meals'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = MealForm()
        return context


class MealCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = MealModel
    permission_required = 'cafeteria.add_mealmodel'
    form_class = MealForm

    def get_success_url(self):
        return reverse('cafeteria_meal_list')

    def form_valid(self, form):
        messages.success(self.request, f"Meal Type '{form.cleaned_data['name']}' created successfully.")
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class MealUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = MealModel
    permission_required = 'cafeteria.change_mealmodel'
    form_class = MealForm

    def get_success_url(self):
        return reverse('cafeteria_meal_list')

    def form_valid(self, form):
        messages.success(self.request, f"Meal Type '{form.cleaned_data['name']}' updated successfully.")
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class MealDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = MealModel
    permission_required = 'cafeteria.delete_mealmodel'
    template_name = 'cafeteria/meal/delete.html'
    success_url = reverse_lazy('cafeteria_meal_list')

    def form_valid(self, form):
        messages.success(self.request, f"Meal Type '{self.object.name}' was deleted successfully.")
        return super().form_valid(form)


class CafeteriaSettingDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """
    Displays the current cafeteria settings. If no settings exist,
    it redirects the user to the create page.
    """
    model = CafeteriaSettingModel
    permission_required = 'cafeteria.view_cafeteriasettingmodel'
    template_name = 'cafeteria/settings/detail.html'
    context_object_name = 'setting'

    def get_object(self, queryset=None):
        # The object is the first (and only) row, or None if it doesn't exist.
        return CafeteriaSettingModel.objects.first()

    def dispatch(self, request, *args, **kwargs):
        # If no settings object exists, redirect to the create view.
        if not self.get_object():
            return redirect(reverse('cafeteria_settings_create'))
        return super().dispatch(request, *args, **kwargs)


class CafeteriaSettingCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    Handles the initial creation of the cafeteria settings.
    This view will only be accessible if no settings object exists.
    """
    model = CafeteriaSettingModel
    permission_required = 'cafeteria.add_cafeteriasettingmodel'
    form_class = CafeteriaSettingForm
    template_name = 'cafeteria/settings/form.html'
    success_url = reverse_lazy('cafeteria_settings_detail')

    def dispatch(self, request, *args, **kwargs):
        # If a settings object already exists, redirect to the edit view.
        if CafeteriaSettingModel.objects.exists():
            return redirect(reverse('cafeteria_settings_update'))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Cafeteria settings created successfully.")
        return super().form_valid(form)


class CafeteriaSettingUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """
    Handles updating the existing cafeteria settings object.
    """
    model = CafeteriaSettingModel
    permission_required = 'cafeteria.change_cafeteriasettingmodel'
    form_class = CafeteriaSettingForm
    template_name = 'cafeteria/settings/form.html'
    success_url = reverse_lazy('cafeteria_settings_detail')

    def get_object(self, queryset=None):
        # This view will always edit the first (and only) settings object.
        return CafeteriaSettingModel.objects.first()

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        messages.success(self.request, "Cafeteria settings updated successfully.")
        return super().form_valid(form)


class MealCollectionLiveView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    The main, interactive page for recording meal collections in real-time.
    """
    permission_required = 'cafeteria.add_mealcollectionmodel'
    template_name = 'cafeteria/collection/live.html'


class StudentSearchForMealAjaxView(LoginRequiredMixin, View):
    """
    AJAX endpoint to search for a student and check their meal eligibility.
    """

    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        if not query:
            return JsonResponse({'error': 'No search query provided.'}, status=400)

        student = StudentModel.objects.filter(
            Q(registration_number__iexact=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query)
        ).select_related('student_class', 'class_section').filter(status='active').first()

        if not student:
            return JsonResponse({'error': f"Student '{query}' not found."}, status=404)

        setting = CafeteriaSettingModel.objects.first()
        is_eligible = True
        eligibility_message = "Eligible for Meal"

        # Check 1: Has the student paid the required cafeteria fee (if one is set)?
        if setting and setting.cafeteria_fee:
            fee_paid = InvoiceModel.objects.filter(
                student=student,
                items__fee_master__fee=setting.cafeteria_fee,
                status=InvoiceModel.Status.PAID
            ).exists()
            if not fee_paid:
                is_eligible = False
                eligibility_message = f"Required Fee Not Paid: '{setting.cafeteria_fee.name}'"

        # Check 2: Have they exceeded the daily meal limit?
        meals_today = MealCollectionModel.objects.filter(student=student, collection_date=date.today()).count()
        if setting and meals_today >= setting.max_meals_per_day:
            is_eligible = False
            eligibility_message = f"Daily Limit Reached ({meals_today} of {setting.max_meals_per_day} meals)"

        # Get meals already collected today to prevent showing buttons for them
        collected_meal_ids = MealCollectionModel.objects.filter(
            student=student, collection_date=date.today()
        ).values_list('meal_id', flat=True)

        return JsonResponse({
            'student': {
                'id': student.pk,
                'name': f"{student.first_name} {student.last_name}",
                'class': f"{student.student_class.name} {student.class_section.name}",
                'image_url': student.image.url if student.image else None,
            },
            'is_eligible': is_eligible,
            'eligibility_message': eligibility_message,
            'meals_today_count': meals_today,
            'available_meals': list(
                MealModel.objects.filter(is_active=True).exclude(id__in=collected_meal_ids).values('id', 'name'))
        })


class RecordMealAjaxView(LoginRequiredMixin, View):
    """AJAX endpoint to quickly record a meal collection."""

    def post(self, request, *args, **kwargs):
        student_id = request.POST.get('student_id')
        meal_id = request.POST.get('meal_id')

        try:
            student = StudentModel.objects.get(pk=student_id)
            meal = MealModel.objects.get(pk=meal_id)

            try:
                staff_member = StaffModel.objects.get(admin=request.user)
            except StaffModel.DoesNotExist:
                return JsonResponse(
                    {'status': 'error', 'message': 'Your user account is not linked to a staff profile.'}, status=403)

            # Final server-side check for daily limit
            setting = CafeteriaSettingModel.objects.first()
            if setting:
                meals_today = MealCollectionModel.objects.filter(student=student, collection_date=date.today()).count()
                if meals_today >= setting.max_meals_per_day:
                    return JsonResponse({'status': 'error', 'message': 'Daily meal limit has been reached.'},
                                        status=403)

            MealCollectionModel.objects.create(student=student, meal=meal, served_by=staff_member)
            return JsonResponse({'status': 'success', 'message': f"{meal.name} recorded for {student.first_name}."})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class MealCollectionHistoryView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    A historical log of all meal collections with full search and filtering.
    """
    model = MealCollectionModel
    permission_required = 'cafeteria.view_mealcollectionmodel'
    template_name = 'cafeteria/collection/history.html'
    context_object_name = 'collections'
    paginate_by = 30

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'student', 'meal', 'served_by__staff_profile__user', 'session', 'term'
        )

        # Get filter parameters from the request
        query = self.request.GET.get('q')
        meal_id = self.request.GET.get('meal')
        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        # Apply filters
        if query:
            queryset = queryset.filter(
                Q(student__first_name__icontains=query) |
                Q(student__last_name__icontains=query) |
                Q(student__registration_number__icontains=query)
            )
        if meal_id:
            queryset = queryset.filter(meal_id=meal_id)
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        if start_date:
            queryset = queryset.filter(collection_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(collection_date__lte=end_date)

        return queryset.order_by('-collection_date', '-collection_time')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass filter values back to the template to re-populate the form
        context['search_query'] = self.request.GET.get('q', '')
        context['selected_meal'] = self.request.GET.get('meal', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')

        # Pass filter options and current selections to the template
        context['meals'] = MealModel.objects.filter(is_active=True)
        context['sessions'] = SessionModel.objects.all().order_by('-start_year')
        context['terms'] = TermModel.objects.all().order_by('order')

        school_setting = SchoolSettingModel.objects.first()
        selected_session_id = self.request.GET.get('session')
        if selected_session_id:
            context['selected_session'] = get_object_or_404(SessionModel, pk=selected_session_id)

        selected_term_id = self.request.GET.get('term')
        if selected_term_id:
            context['selected_term'] = get_object_or_404(TermModel, pk=selected_term_id)

        return context

