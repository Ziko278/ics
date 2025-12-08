# parent_portal/views.py
from decimal import Decimal
import logging
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView, ListView, DetailView, FormView
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.utils import timezone

from admin_site.models import SchoolSettingModel
# Import models from other apps (adjust paths as needed)
from student.models import StudentModel, ParentProfileModel
from finance.models import InvoiceModel, InvoiceItemModel, StudentFundingModel, SchoolBankDetail, FeePaymentModel, \
    StudentDiscountModel
from inventory.models import InventoryAssignmentModel, InventoryCollectionModel, SaleModel, SaleItemModel
from cafeteria.models import MealCollectionModel

from .forms import FeeUploadForm

logger = logging.getLogger(__name__)


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
        context['total_discount'] = sum(inv.total_discount for inv in context['pending_invoices'])

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
        context['invoice_discounts'] = StudentDiscountModel.objects.filter(
            invoice_item__invoice=self.object
        ).select_related('discount_application__discount')
        return context


class FeeUploadView(ParentPortalMixin, FormView):
    form_class = FeeUploadForm
    template_name = 'parent_portal/fee_upload.html'
    success_url = reverse_lazy('parent_fee_history')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['student'] = self.selected_ward
        kwargs['upload_type'] = self.request.GET.get('type', 'fee')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        transaction_type = self.request.GET.get('type', 'fee')
        context['transaction_type'] = transaction_type

        if transaction_type == 'wallet':
            try:
                context['funding_account'] = SchoolSettingModel.objects.first()
            except SchoolSettingModel.DoesNotExist:
                context['funding_account'] = None
            context['bank_details'] = None
        else:
            context['bank_details'] = SchoolBankDetail.objects.all()
            context['funding_account'] = None

        return context

    def form_valid(self, form):
        cleaned_data = form.cleaned_data
        target_invoice = cleaned_data.get('target_invoice')
        proof_file = self.request.FILES.get('proof_of_payment')
        parent_user = self.request.user
        payment_type = self.request.POST.get('payment_type', 'quick')  # 'quick' or 'itemized'

        if target_invoice:
            # --- Create FeePaymentModel for invoice payment ---
            try:
                if target_invoice.student != self.selected_ward:
                    messages.error(self.request, "Selected invoice does not belong to the current student.")
                    return self.form_invalid(form)

                # Save proof file
                proof_file_name = None
                if proof_file:
                    file_name = f"parent_proofs/{self.selected_ward.registration_number}_{target_invoice.invoice_number}_{proof_file.name}"
                    proof_file_name = default_storage.save(file_name, proof_file)

                # Get or create a default bank account for parent uploads
                bank_account = SchoolBankDetail.objects.first()
                if not bank_account:
                    messages.error(self.request, "No bank account configured. Please contact administration.")
                    return self.form_invalid(form)

                # Build notes with payment allocation details
                notes_parts = [
                    f"Parent Upload via Portal.",
                    f"User: {parent_user.username}.",
                    f"Proof File: {proof_file_name or 'Not Saved'}.",
                    f"Student: {self.selected_ward}.",
                    f"Payment Type: {payment_type.title()}"
                ]

                # Handle itemized payment
                if payment_type == 'itemized':
                    item_allocations = {}
                    total_allocated = Decimal('0.00')

                    for key, value in self.request.POST.items():
                        if key.startswith('item_') and value:
                            try:
                                item_id = int(key.split('_')[1])
                                amount_for_item = Decimal(value)

                                if amount_for_item > 0:
                                    item = get_object_or_404(InvoiceItemModel, pk=item_id, invoice=target_invoice)

                                    # Don't allow overpayment on a single item
                                    payable_amount = min(amount_for_item, item.balance)

                                    if payable_amount != amount_for_item:
                                        messages.warning(
                                            self.request,
                                            f"Amount for '{item.description}' adjusted from ₦{amount_for_item:,.2f} to ₦{payable_amount:,.2f} (item balance)"
                                        )

                                    item_allocations[item_id] = {
                                        'description': item.description,
                                        'amount': float(payable_amount)
                                    }
                                    total_allocated += payable_amount

                            except (ValueError, TypeError, InvoiceItemModel.DoesNotExist):
                                continue

                    # Validate that allocated amounts match the total payment
                    if total_allocated != cleaned_data['amount']:
                        messages.error(
                            self.request,
                            f"Item allocations (₦{total_allocated:,.2f}) must equal the total amount paid (₦{cleaned_data['amount']:,.2f})"
                        )
                        return self.form_invalid(form)

                    if not item_allocations:
                        messages.error(self.request, "Please select at least one fee item to pay.")
                        return self.form_invalid(form)

                    # Store item allocations as JSON in notes
                    import json
                    notes_parts.append(f"Item Allocations: {json.dumps(item_allocations, indent=2)}")

                notes = "\n".join(notes_parts)

                FeePaymentModel.objects.create(
                    invoice=target_invoice,
                    amount=cleaned_data['amount'],
                    payment_mode=cleaned_data['method'],
                    bank_account=bank_account,
                    date=timezone.now().date(),
                    reference=cleaned_data.get('teller_number', ''),
                    status=FeePaymentModel.PaymentStatus.PENDING,
                    notes=notes,
                )

                if payment_type == 'itemized':
                    messages.success(
                        self.request,
                        f"Payment proof of ₦{cleaned_data['amount']:,.2f} for {len(item_allocations)} fee item(s) submitted. Pending review."
                    )
                else:
                    messages.success(self.request, "Payment proof for invoice submitted. Pending review.")

            except Exception as e:
                messages.error(self.request, f"Error saving invoice payment proof: {e}")
                if proof_file_name and default_storage.exists(proof_file_name):
                    default_storage.delete(proof_file_name)
                return self.form_invalid(form)

        else:
            # --- Create StudentFundingModel (Wallet) ---
            try:
                funding = StudentFundingModel(
                    student=self.selected_ward,
                    amount=cleaned_data['amount'],
                    method=cleaned_data['method'],
                    teller_number=cleaned_data.get('teller_number', ''),
                    proof_of_payment=proof_file,
                    status='pending',
                    mode='online',
                )
                try:
                    setting = SchoolSettingModel.objects.first()
                    if setting:
                        funding.session = setting.session
                        funding.term = setting.term
                except Exception:
                    pass

                funding.save()
                messages.success(self.request, "Wallet funding proof submitted. Pending review.")

            except Exception as e:
                messages.error(self.request, f"Error saving wallet funding proof: {e}")
                return self.form_invalid(form)

        return redirect(self.success_url)

    def form_invalid(self, form):
        for field, errors in form.errors.items():
            field_label = "__all__" if field == "__all__" else form.fields.get(field).label if form.fields.get(
                field) else field.replace('_', ' ').title()
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


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def parent_change_password_view(request):
    """
    View to handle password change for authenticated parents.
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
            return render(request, 'parent_portal/change_password.html')

        # Verify current password
        user = authenticate(username=request.user.username, password=current_password)
        if user is None:
            messages.error(request, "Current password is incorrect.")
            logger.warning(
                f"Failed password change attempt for parent {request.user.username} - incorrect current password")
            return render(request, 'parent_portal/change_password.html')

        try:
            # Change password
            user.set_password(new_password1)
            user.save()

            # Keep user logged in after password change
            update_session_auth_hash(request, user)

            messages.success(request, "Your password has been successfully changed!")
            logger.info(f"Password successfully changed for parent {request.user.username}")

            # Redirect to parent dashboard
            return redirect('parent_dashboard')

        except Exception as e:
            logger.exception(f"Error changing password for parent {request.user.username}: {str(e)}")
            messages.error(request, "An error occurred while changing your password. Please try again.")
            return render(request, 'parent_portal/change_password.html')

    # GET request - show the form
    return render(request, 'parent_portal/change_password.html')