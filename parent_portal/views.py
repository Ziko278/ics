# parent_portal/views.py
from django.core.files.storage import default_storage
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic import TemplateView, ListView, DetailView, FormView
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone

from admin_site.models import SchoolSettingModel
# Import models from other apps (adjust paths as needed)
from student.models import StudentModel, ParentProfileModel
from finance.models import InvoiceModel, InvoiceItemModel, StudentFundingModel, SchoolBankDetail, FeePaymentModel
from inventory.models import InventoryAssignmentModel, InventoryCollectionModel, SaleModel, SaleItemModel
from cafeteria.models import MealCollectionModel

from .forms import FeeUploadForm


# --- Helper Mixin ---
class ParentPortalMixin(LoginRequiredMixin):
    """
    Ensures user is logged in, has a parent profile, and manages ward selection.
    Includes auto-select logic for single ward.
    Provides parent_obj and selected_ward context.
    """
    login_url = reverse_lazy('login')

    def dispatch(self, request, *args, **kwargs):
        # 1. Login check is handled by LoginRequiredMixin

        # 2. Check for parent profile
        if not hasattr(request.user, 'parent_profile'):
            messages.error(request, "Access denied. Only parents can access this portal.")
            logout(request)
            return redirect(self.login_url)

        # 3. Get Parent object
        self.parent_obj = request.user.parent_profile.parent

        # 4. Initialize selected ward from session
        self.selected_ward_id = request.session.get('selected_ward_id')
        self.selected_ward = None

        # --- AUTO-SELECT LOGIC ---
        # Only auto-select if NO ward is currently selected
        if not self.selected_ward_id:
            wards = self.parent_obj.wards.filter(status='active')
            if wards.count() == 1:
                # Auto-select the only ward
                ward = wards.first()
                request.session['selected_ward_id'] = ward.id
                self.selected_ward_id = ward.id
                self.selected_ward = ward

                # Only redirect to dashboard if we're NOT already on SelectWardView or SetWardView
                view_class_name = self.__class__.__name__
                if view_class_name not in ('SelectWardView', 'SetWardView'):
                    messages.info(request, f"Automatically selected {ward.first_name}'s dashboard.")
                    return redirect(reverse('parent_dashboard'))
        # --- END AUTO-SELECT ---

        # 5. Validate selected ward if one is set
        if self.selected_ward_id and not self.selected_ward:
            try:
                self.selected_ward = self.parent_obj.wards.get(pk=self.selected_ward_id, status='active')
            except StudentModel.DoesNotExist:
                # Ward not found or inactive
                if 'selected_ward_id' in request.session:
                    del request.session['selected_ward_id']
                self.selected_ward_id = None
                self.selected_ward = None

                view_class_name = self.__class__.__name__
                allowed_views = ('SelectWardView', 'SetWardView', 'ParentLoginView', 'ParentLogoutView')
                if view_class_name not in allowed_views:
                    messages.warning(request, "Selected student not found or inactive. Please select again.")
                    return redirect(reverse('parent_select_ward'))

        # 6. Redirect if no ward is selected (and view requires it)
        view_class_name = self.__class__.__name__
        allowed_views = ('SelectWardView', 'SetWardView', 'ParentLoginView', 'ParentLogoutView')
        if not self.selected_ward and view_class_name not in allowed_views:
            return redirect(reverse('parent_select_ward'))

        # All checks passed
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['selected_ward'] = self.selected_ward
        context['parent_wards'] = self.parent_obj.wards.filter(status='active').order_by('first_name')
        try:
            from admin_site.models import SchoolInfoModel
            context['school_info'] = SchoolInfoModel.objects.first()
        except (ImportError, Exception):
            context['school_info'] = None
        return context


class ParentLogoutView(View):
    def get(self, request, *args, **kwargs):
        logout(request)
        messages.info(request, "You have been logged out.")
        return redirect(reverse('login'))


class SelectWardView(ParentPortalMixin, TemplateView):
    template_name = 'parent_portal/select_ward.html'

    def dispatch(self, request, *args, **kwargs):
        # Quick guard before allowing the mixin to run
        if not hasattr(request.user, 'parent_profile'):
            messages.error(request, "Access denied.")
            logout(request)
            return redirect(reverse_lazy('login'))

        # IMPORTANT: call super() so ParentPortalMixin.dispatch runs (MRO)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not context['parent_wards'].exists():
            messages.warning(self.request, "No active students are linked to your account.")
        return context


class SetWardView(ParentPortalMixin, View):
    def get(self, request, ward_id, *args, **kwargs):
        try:
            # Ensure the parent owns this ward
            ward = self.parent_obj.wards.get(pk=ward_id, status='active')
            request.session['selected_ward_id'] = ward.id
            messages.info(request, f"Now viewing dashboard for {ward.first_name}.")
            return redirect(reverse('parent_dashboard'))
        except StudentModel.DoesNotExist:
            messages.error(request, "Invalid student selection.")
            return redirect(reverse('select_ward'))


class DashboardView(ParentPortalMixin, TemplateView):
    template_name = 'parent_portal/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ward = self.selected_ward

        # Fee Summary
        context['pending_invoices'] = InvoiceModel.objects.filter(
            student=ward, status__in=['unpaid', 'partially_paid']
        ).order_by('issue_date')
        context['total_due'] = sum(inv.balance for inv in context['pending_invoices'])

        # Recent Shop Spending
        context['recent_sales'] = SaleModel.objects.filter(
            customer=ward
        ).order_by('-sale_date')[:5]

        # Recent Cafeteria Visits
        context['recent_meals'] = MealCollectionModel.objects.filter(
            student=ward
        ).order_by('-collection_date', '-collection_time')[:5]

        return context


# --- Fee Management ---

class FeeInvoiceListView(ParentPortalMixin, ListView):
    model = InvoiceModel
    template_name = 'parent_portal/fee_list.html'
    context_object_name = 'invoices'

    def get_queryset(self):
        return InvoiceModel.objects.filter(
            student=self.selected_ward
        ).order_by('-session__start_year', '-term__order')


class AccountDetailView(ParentPortalMixin, TemplateView):
    model = InvoiceModel
    template_name = 'parent_portal/account_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['funding_account'] = SchoolSettingModel.objects.first()
        context['school_account_list'] = SchoolBankDetail.objects.all()
        return context


class FeeInvoiceDetailView(ParentPortalMixin, DetailView):
    model = InvoiceModel
    template_name = 'parent_portal/fee_invoice_detail.html' # New template needed
    context_object_name = 'invoice'

    def get_queryset(self):
        # Ensure parent can only see invoices for their selected ward
        return InvoiceModel.objects.filter(student=self.selected_ward)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['invoice_items'] = self.object.items.all()
        return context


class FeeUploadView(ParentPortalMixin, FormView):
    form_class = FeeUploadForm
    template_name = 'parent_portal/fee_upload.html'
    # Redirect to history to see the upload status
    success_url = reverse_lazy('parent_fee_history')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['student'] = self.selected_ward
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bank_details'] = SchoolBankDetail.objects.filter(is_active=True)
        return context

    def form_valid(self, form):
        cleaned_data = form.cleaned_data
        target_invoice: InvoiceModel = cleaned_data.get('target_invoice')
        proof_file = self.request.FILES.get('proof_of_payment') # Get the file object

        parent_user = self.request.user # Get the logged-in parent user

        if target_invoice:
            # --- Create FeePaymentModel ---
            try:
                # Security check
                if target_invoice.student != self.selected_ward:
                    messages.error(self.request, "Selected invoice does not belong to the current student.")
                    return self.form_invalid(form)

                # Handle proof storage manually (Example: save to media/parent_proofs/)
                # You MUST adapt the path and potentially filename logic
                proof_file_name = None
                if proof_file:
                    # Basic filename example (consider adding timestamp/UUID for uniqueness)
                    file_name = f"parent_proofs/{self.selected_ward.registration_number}_{target_invoice.invoice_number}_{proof_file.name}"
                    proof_file_name = default_storage.save(file_name, proof_file)
                    # proof_file_url = default_storage.url(proof_file_name) # Get URL if needed

                FeePaymentModel.objects.create(
                    invoice=target_invoice,
                    # No 'parent' field, use notes
                    amount=cleaned_data['amount'],
                    payment_mode=cleaned_data['method'], # Ensure values match choices
                    date=timezone.now().date(),
                    reference=cleaned_data.get('teller_number', ''),
                    status=FeePaymentModel.PaymentStatus.PENDING,
                    # No 'proof_of_payment' field, use notes
                    notes=f"Parent Upload via Portal.\nUser: {parent_user.username}.\nProof File: {proof_file_name or 'Not Saved'}.\nStudent: {self.selected_ward}.",
                    # bank_account, confirmed_by are null initially
                )
                messages.success(self.request, "Payment proof for invoice submitted. Pending review.")

            except Exception as e:
                messages.error(self.request, f"Error saving invoice payment proof: {e}")
                # Consider deleting the saved file if creation fails halfway
                if proof_file_name and default_storage.exists(proof_file_name):
                    default_storage.delete(proof_file_name)
                return self.form_invalid(form)

        else:
            # --- Create StudentFundingModel (Wallet) ---
            try:
                # StudentFundingModel might still have proof_of_payment field
                funding = StudentFundingModel(
                    student=self.selected_ward,
                    amount=cleaned_data['amount'],
                    method=cleaned_data['method'],
                    teller_number=cleaned_data.get('teller_number', ''),
                    proof_of_payment=proof_file, # Assign file directly if model has the field
                    status='pending',
                    mode='online',
                    # Add parent info to notes if model lacks parent field
                    # notes=f"Uploaded by parent: {parent_user.username}"
                )
                # Set session/term automatically
                try:
                    from admin_site.models import SchoolSettingModel
                    setting = SchoolSettingModel.objects.first()
                    if setting:
                        funding.session = setting.session
                        funding.term = setting.term
                except (ImportError, Exception): pass

                funding.save()
                messages.success(self.request, "Wallet funding proof submitted. Pending review.")

            except Exception as e:
                 messages.error(self.request, f"Error saving wallet funding proof: {e}")
                 return self.form_invalid(form)

        return redirect(self.success_url) # Use redirect with success_url

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            # Handle non-field errors (like __all__)
            field_label = "__all__" if field == "__all__" else form.fields.get(field).label if form.fields.get(field) else field.replace('_', ' ').title()
            for error in errors:
                messages.error(self.request, f"{field_label}: {error}")
        return self.render_to_response(self.get_context_data(form=form))


class FeeUploadHistoryView(ParentPortalMixin, ListView):
    # --- ADD THIS LINE BACK ---
    model = StudentFundingModel # Provide a base model for ListView
    # --- END ADDITION ---
    template_name = 'parent_portal/fee_history.html'
    # context_object_name = 'uploads' # We are using custom context names below
    # paginate_by = 10 # Pagination across two lists is complex, handle manually if needed

    def get_context_data(self, **kwargs):
        # This calls ParentPortalMixin.get_context_data and ListView.get_context_data
        context = super().get_context_data(**kwargs)
        parent_user = self.request.user

        # Fetch wallet funding uploads
        wallet_uploads = StudentFundingModel.objects.filter(
            student=self.selected_ward,
            mode='online'
            # Add parent filter if model has it
            # parent=self.parent_obj,
        ).order_by('-created_at')

        # Fetch invoice payment uploads initiated by parent
        invoice_uploads = FeePaymentModel.objects.filter(
            invoice__student=self.selected_ward,
            status=FeePaymentModel.PaymentStatus.PENDING, # Show pending ones
            notes__icontains=f"User: {parent_user.username}" # Identify by note
            # Add parent filter if model has it
            # parent=self.parent_obj
        ).select_related('invoice').order_by('-created_at')

        context['wallet_uploads'] = wallet_uploads
        context['invoice_uploads'] = invoice_uploads

        # Remove the default queryset if ListView added it under 'object_list' or 'studentfundingmodel_list'
        context.pop('object_list', None)
        context.pop('studentfundingmodel_list', None)


        return context
# --- Shop ---

class ShopHistoryView(ParentPortalMixin, ListView):
    model = SaleModel
    template_name = 'parent_portal/shop_history.html'
    context_object_name = 'sales'
    paginate_by = 15

    def get_queryset(self):
        return SaleModel.objects.filter(
            customer=self.selected_ward
        ).order_by('-sale_date')

class ShopHistoryDetailView(ParentPortalMixin, DetailView):
    model = SaleModel
    template_name = 'parent_portal/shop_detail.html'
    context_object_name = 'sale'

    def get_queryset(self):
        # Ensure parent can only see sales for their selected ward
        return SaleModel.objects.filter(customer=self.selected_ward)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sale_items'] = self.object.items.select_related('item').all()
        return context

# --- Inventory ---

class InventoryView(ParentPortalMixin, ListView):
    model = InventoryCollectionModel
    template_name = 'parent_portal/inventory_list.html'
    context_object_name = 'collections'

    def get_queryset(self):
        # Get all collection records for the selected student
        return InventoryCollectionModel.objects.filter(
            student=self.selected_ward
        ).select_related(
            'assignment__item', 'assignment__session', 'assignment__term'
        ).order_by('-assignment__session__start_year', '-assignment__term__order', 'assignment__item__name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Optional: Group by assignment if needed, or process directly in template
        return context

# --- Cafeteria ---


class CafeteriaHistoryView(ParentPortalMixin, ListView):
    model = MealCollectionModel
    template_name = 'parent_portal/cafeteria_history.html'
    context_object_name = 'meals'
    paginate_by = 20

    def get_queryset(self):
        return MealCollectionModel.objects.filter(
            student=self.selected_ward
        ).select_related('meal').order_by('-collection_date', '-collection_time')