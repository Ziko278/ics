import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import openpyxl
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Q, Sum, Avg, F, DecimalField, Value, Count
from django.db.models.functions import TruncMonth, Coalesce, Concat
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.utils import timezone
from django.utils.timezone import now
from django.views import View
from django.views.generic import TemplateView, CreateView, UpdateView, ListView, DetailView, DeleteView, FormView
from openpyxl.styles import Font

from admin_site.models import SessionModel, TermModel, SchoolSettingModel, ClassesModel, ActivityLogModel
from admin_site.views import FlashFormErrorsMixin
from human_resource.models import StaffModel, StaffProfileModel, StaffWalletModel
from inventory.models import PurchaseOrderModel, PurchaseAdvanceModel
from student.models import StudentModel, StudentWalletModel
from student.signals import get_day_ordinal_suffix
from .models import FinanceSettingModel, SupplierPaymentModel, PurchaseAdvancePaymentModel, FeeModel, FeeGroupModel, \
    FeeMasterModel, InvoiceGenerationJob, InvoiceModel, FeePaymentModel, ExpenseCategoryModel, ExpenseModel, \
    IncomeCategoryModel, IncomeModel, TermlyFeeAmountModel, StaffBankDetail, SalaryRecord, SalaryAdvance, \
    SalaryStructure, StudentFundingModel, InvoiceItemModel, AdvanceSettlementModel, \
    SchoolBankDetail, StaffLoan, StaffLoanRepayment, StaffFundingModel
from .forms import FinanceSettingForm, SupplierPaymentForm, PurchaseAdvancePaymentForm, FeeForm, FeeGroupForm, \
    InvoiceGenerationForm, FeePaymentForm, ExpenseCategoryForm, ExpenseForm, IncomeCategoryForm, \
    IncomeForm, TermlyFeeAmountFormSet, FeeMasterCreateForm, BulkPaymentForm, StaffBankDetailForm, PaysheetRowForm, \
    SalaryAdvanceForm, SalaryStructureForm, StudentFundingForm, SchoolBankDetailForm, \
    StaffLoanForm, StaffLoanRepaymentForm, StaffFundingForm
from finance.tasks import generate_invoices_task
from pytz import timezone as pytz_timezone

# ===================================================================
# Finance Settings Views (Singleton Pattern)
# ===================================================================


class FinanceSettingDetailView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    """
    Displays the current finance settings. If no settings exist,
    it redirects the user to the create page.
    """
    permission_required = 'finance.view_financesettingmodel'
    template_name = 'finance/setting/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['finance_setting'] = FinanceSettingModel.objects.first()
        return context

    def dispatch(self, request, *args, **kwargs):
        # If no settings object exists, redirect to the create view
        if not FinanceSettingModel.objects.exists():
            return redirect(reverse('finance_setting_create'))
        return super().dispatch(request, *args, **kwargs)


class FinanceSettingCreateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    """
    Handles the initial creation of the finance settings.
    This view will only be accessible if no settings object exists.
    """
    model = FinanceSettingModel
    permission_required = 'finance.change_financesettingmodel'
    form_class = FinanceSettingForm
    template_name = 'finance/setting/create.html'
    success_message = 'Finance Settings Created Successfully'
    success_url = reverse_lazy('finance_setting_detail')

    def dispatch(self, request, *args, **kwargs):
        # If a settings object already exists, redirect to the edit view
        if FinanceSettingModel.objects.exists():
            return redirect(reverse('finance_setting_update'))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        # Set the 'updated_by' field to the current user upon creation
        form.instance.updated_by = self.request.user
        return super().form_valid(form)


class FinanceSettingUpdateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    """
    Handles updating the existing finance settings object.
    """
    model = FinanceSettingModel
    permission_required = 'finance.change_financesettingmodel'
    form_class = FinanceSettingForm
    template_name = 'finance/setting/create.html'
    success_message = 'Finance Settings Updated Successfully'
    success_url = reverse_lazy('finance_setting_detail')

    def get_object(self, queryset=None):
        # This view will always edit the first (and only) settings object
        return FinanceSettingModel.objects.first()

    def form_valid(self, form):
        # Update the 'updated_by' field to the current user upon update
        form.instance.updated_by = self.request.user
        return super().form_valid(form)


class SupplierAccountsListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    PRIMARY VIEW ("Accounts Payable"): Lists all submitted Purchase Orders
    that require payment, showing their financial status.
    """
    model = PurchaseOrderModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/supplier_payment/accounts_payable_list.html'
    context_object_name = 'purchase_orders'
    paginate_by = 20

    def get_queryset(self):
        # We start with submitted POs and prefetch supplier data for efficiency
        queryset = super().get_queryset().filter(
            status__in=['submitted', 'partially_received', 'received']
        ).select_related('supplier', 'session', 'term')

        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        query = self.request.GET.get('q')

        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        if query:
            queryset = queryset.filter(
                Q(supplier__name__icontains=query) | Q(order_number__icontains=query)
            ).distinct()

        return queryset.order_by('-order_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = SessionModel.objects.all().order_by('-start_year')
        context['terms'] = TermModel.objects.all().order_by('order')
        context['search_query'] = self.request.GET.get('q', '')
        # ... (add selected session/term logic here for the template filters) ...
        return context


class SupplierAccountDetailView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    DETAIL VIEW: Manages payments for a single Purchase Order.
    This view displays the PO's financial details, lists existing payments,
    and includes an inline form to add new payments.
    """
    model = SupplierPaymentModel
    form_class = SupplierPaymentForm
    permission_required = 'finance.add_expensemodel'
    template_name = 'finance/supplier_payment/po_payment_detail.html'

    def get_form_kwargs(self):
        """
        This method is overridden to pass the purchase_order instance
        to the form, so it knows the maximum payable amount.
        """
        kwargs = super().get_form_kwargs()
        self.purchase_order = get_object_or_404(PurchaseOrderModel, pk=self.kwargs['po_pk'])
        kwargs['purchase_order'] = self.purchase_order
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.purchase_order = get_object_or_404(PurchaseOrderModel, pk=self.kwargs['po_pk'])
        context['po'] = self.purchase_order
        # Get all payments related to this PO, including reverted ones for history
        context['payments'] = self.purchase_order.supplierpaymentmodel_set.all().order_by('-payment_date')
        return context

    def form_valid(self, form):
        self.purchase_order = get_object_or_404(PurchaseOrderModel, pk=self.kwargs['po_pk'])
        payment = form.save(commit=False)
        payment.supplier = self.purchase_order.supplier
        payment.created_by = self.request.user
        payment.save()
        # M2M fields must be saved after the initial save
        payment.purchase_orders.add(self.purchase_order)
        messages.success(self.request, "Payment recorded successfully against the Purchase Order.")
        return redirect('finance_po_payment_detail', po_pk=self.purchase_order.pk)


class SupplierPaymentRevertView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Handles reverting a 'Completed' payment to 'Reverted' status."""
    permission_required = 'finance.add_expensemodel'

    def post(self, request, *args, **kwargs):
        payment = get_object_or_404(SupplierPaymentModel, pk=self.kwargs['pk'])
        # Find the PO this payment is linked to, to redirect back correctly
        po_pk = payment.purchase_orders.first().pk if payment.purchase_orders.exists() else None

        if payment.status == 'completed':
            payment.status = 'reverted'
            payment.save()
            messages.warning(request, f"Payment {payment.receipt_number} has been successfully reverted.")
        else:
            messages.error(request, "Only 'Completed' payments can be reverted.")

        if po_pk:
            return redirect('finance_po_payment_detail', po_pk=po_pk)
        return redirect('finance_all_payments_list')  # Fallback redirect


class AllSupplierPaymentsListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    SECONDARY VIEW: Provides a comprehensive, filterable log of all
    individual supplier payment transactions for auditing purposes.
    """
    model = SupplierPaymentModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/supplier_payment/all_payments_list.html'
    context_object_name = 'payments'
    paginate_by = 25

    def get_queryset(self):
        queryset = super().get_queryset().select_related('supplier', 'session', 'term')

        # Get filter parameters from the request
        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        query = self.request.GET.get('q')

        # Apply filters if provided
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        if query:
            queryset = queryset.filter(
                Q(supplier__name__icontains=query) |
                Q(purchase_orders__order_number__icontains=query) |
                Q(receipt_number__icontains=query) |
                Q(reference__icontains=query)
            ).distinct()  # Use distinct to avoid duplicates from M2M join

        return queryset.order_by('-payment_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school_setting = SchoolSettingModel.objects.first()

        # Add filter options and selections to the context
        context['sessions'] = SessionModel.objects.all().order_by('-start_year')
        context['terms'] = TermModel.objects.all().order_by('order')
        context['search_query'] = self.request.GET.get('q', '')

        selected_session_id = self.request.GET.get('session')
        if selected_session_id:
            context['selected_session'] = get_object_or_404(SessionModel, pk=selected_session_id)
        elif school_setting:
            context['selected_session'] = school_setting.session

        selected_term_id = self.request.GET.get('term')
        if selected_term_id:
            context['selected_term'] = get_object_or_404(TermModel, pk=selected_term_id)
        elif school_setting:
            context['selected_term'] = school_setting.term

        return context


class SupplierPaymentReceiptView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """
    Displays a printable receipt for a single supplier payment.
    """
    model = SupplierPaymentModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/supplier_payment/receipt.html'
    context_object_name = 'payment'


class PurchaseAdvanceAccountsListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lists approved advances that need payments"""
    model = PurchaseAdvanceModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/purchase_advance/accounts_list.html'
    context_object_name = 'purchase_advances'
    paginate_by = 20

    def get_queryset(self):
        from inventory.models import PurchaseAdvanceModel
        queryset = PurchaseAdvanceModel.objects.filter(
            status__in=['approved', 'disbursed']
        ).select_related('staff', 'session', 'term')

        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        query = self.request.GET.get('q')

        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        if query:
            queryset = queryset.filter(
                Q(staff__first_name__icontains=query) | Q(staff__last_name__icontains=query) |
                Q(advance_number__icontains=query)
            ).distinct()

        return queryset.order_by('-request_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sessions'] = SessionModel.objects.all().order_by('-start_year')
        context['terms'] = TermModel.objects.all().order_by('order')
        context['search_query'] = self.request.GET.get('q', '')
        return context


class PurchaseAdvancePaymentDetailView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Manages payments for a single Purchase Advance"""
    model = PurchaseAdvancePaymentModel
    form_class = PurchaseAdvancePaymentForm
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/purchase_advance/payment_detail.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        from inventory.models import PurchaseAdvanceModel
        self.advance = get_object_or_404(PurchaseAdvanceModel, pk=self.kwargs['advance_pk'])
        kwargs['advance'] = self.advance
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from inventory.models import PurchaseAdvanceModel
        self.advance = get_object_or_404(PurchaseAdvanceModel, pk=self.kwargs['advance_pk'])
        context['advance'] = self.advance
        context['payments'] = self.advance.payments.all().order_by('-payment_date')
        return context

    def form_valid(self, form):
        from inventory.models import PurchaseAdvanceModel
        self.advance = get_object_or_404(PurchaseAdvanceModel, pk=self.kwargs['advance_pk'])
        payment = form.save(commit=False)
        payment.advance = self.advance
        payment.created_by = self.request.user
        payment.save()
        messages.success(self.request, "Payment recorded successfully against the Purchase Advance.")
        return redirect('finance_advance_payment_detail', advance_pk=self.advance.pk)


# ===================================================================
# Fee Type Views (Modal Interface)
# ===================================================================
class FeeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = FeeModel
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/fee/index.html'
    context_object_name = 'fees'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = FeeForm()
        return context


class FeeCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = FeeModel
    permission_required = 'finance.add_feemodel'
    form_class = FeeForm

    def get_success_url(self):
        return reverse('finance_fee_list')

    def form_valid(self, form):
        messages.success(self.request, "Fee Type created successfully.")
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class FeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = FeeModel
    permission_required = 'finance.add_feemodel'
    form_class = FeeForm

    def get_success_url(self):
        return reverse('finance_fee_list')

    def form_valid(self, form):
        messages.success(self.request, "Fee Type updated successfully.")
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class FeeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = FeeModel
    permission_required = 'finance.add_feemodel'
    template_name = 'finance/fee/delete.html'
    success_url = reverse_lazy('finance_fee_list')

    def form_valid(self, form):
        messages.success(self.request, f"Fee Type '{self.object.name}' deleted successfully.")
        return super().form_valid(form)


# ===================================================================
# Fee Group Views (Modal Interface)
# ===================================================================
class FeeGroupListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = FeeGroupModel
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/fee_group/index.html'
    context_object_name = 'fee_groups'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = FeeGroupForm()
        return context


class FeeGroupCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = FeeGroupModel
    permission_required = 'finance.add_feemodel'
    form_class = FeeGroupForm

    def get_success_url(self):
        return reverse('finance_fee_group_list')

    def form_valid(self, form):
        messages.success(self.request, "Fee Group created successfully.")
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class FeeGroupUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = FeeGroupModel
    permission_required = 'finance.add_feemodel'
    form_class = FeeGroupForm

    def get_success_url(self):
        return reverse('finance_fee_group_list')

    def form_valid(self, form):
        messages.success(self.request, "Fee Group updated successfully.")
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class FeeGroupDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = FeeGroupModel
    permission_required = 'finance.add_feemodel'
    template_name = 'finance/fee_group/delete.html'
    success_url = reverse_lazy('finance_fee_group_list')
    context_object_name = 'fee_group'

    def form_valid(self, form):
        messages.success(self.request, f"Fee Group '{self.object.name}' deleted successfully.")
        return super().form_valid(form)


# ===================================================================
# Fee Master (Structure)
# ===================================================================
class FeeMasterListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Displays a list of all created fee structures."""
    model = FeeMasterModel
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/fee_master/index.html'
    context_object_name = 'fee_structures'
    paginate_by = 15


class FeeMasterCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Handles the creation of the main FeeMasterModel header (Step 1)."""
    model = FeeMasterModel
    permission_required = 'finance.add_feemodel'
    form_class = FeeMasterCreateForm
    template_name = 'finance/fee_master/create.html'

    def form_valid(self, form):
        messages.success(self.request, "Fee structure created. Now, set the price for each term.")
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        # Redirect to the detail page to set the termly prices
        return reverse('finance_fee_master_detail', kwargs={'pk': self.object.pk})


# Updated view
class FeeMasterDetailView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/fee_master/detail.html'

    def get(self, request, *args, **kwargs):
        fee_structure = get_object_or_404(FeeMasterModel, pk=self.kwargs.get('pk'))

        # Determine which terms to show
        if fee_structure.fee.occurrence == FeeModel.FeeOccurrence.TERMLY:
            terms = TermModel.objects.all().order_by('order')
        else:
            if fee_structure.fee.payment_term:
                terms = [fee_structure.fee.payment_term]
            else:
                terms = []

        # Get existing amounts
        term_amounts = {}
        for amount in fee_structure.termly_amounts.filter(term__in=terms):
            term_amounts[amount.term.id] = amount.amount

        # Prepare display data
        display_terms = []
        for term in terms:
            display_terms.append({
                'term': term,
                'amount': term_amounts.get(term.id, Decimal('0.00'))
            })

        context = {
            'fee_structure': fee_structure,
            'display_terms': display_terms,
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        fee_structure = get_object_or_404(FeeMasterModel, pk=self.kwargs.get('pk'))

        # Determine which terms to process
        if fee_structure.fee.occurrence == FeeModel.FeeOccurrence.TERMLY:
            terms = TermModel.objects.all().order_by('order')
        else:
            if fee_structure.fee.payment_term:
                terms = [fee_structure.fee.payment_term]
            else:
                terms = []

        # Save amounts
        for term in terms:
            field_name = f'term_{term.id}_amount'
            if field_name in request.POST:
                amount = Decimal(request.POST[field_name] or '0')
                TermlyFeeAmountModel.objects.update_or_create(
                    fee_structure=fee_structure,
                    term=term,
                    defaults={'amount': amount}
                )

        messages.success(request, "Fee amounts saved successfully!")
        return redirect('finance_fee_master_detail', pk=fee_structure.pk)


class FeeMasterUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """
    Handles updating the core details of a FeeMasterModel, such as the
    group, fee, and class assignments.
    """
    model = FeeMasterModel
    permission_required = 'finance.add_feemodel'
    form_class = FeeMasterCreateForm  # We can reuse the create form for updating
    template_name = 'finance/fee_master/update.html'
    context_object_name = 'fee_structure'

    def form_valid(self, form):
        messages.success(self.request, "Fee structure details updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        # Redirect back to the detail page after updating
        return reverse('finance_fee_master_detail', kwargs={'pk': self.object.pk})


class FeeMasterDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Handles the deletion of a FeeMasterModel."""
    model = FeeMasterModel
    permission_required = 'finance.add_feemodel'
    template_name = 'finance/fee_master/delete.html'
    success_url = reverse_lazy('finance_fee_master_list')

    def form_valid(self, form):
        messages.success(self.request, f"Fee structure '{self.object}' deleted successfully.")
        return super().form_valid(form)


# ===================================================================
# Invoice Generation Views (Asynchronous Workflow)
# ===================================================================
class InvoiceGenerationView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    form_class = InvoiceGenerationForm
    template_name = 'finance/invoice/generate.html'
    permission_required = 'finance.add_feemodel'

    def form_valid(self, form):
        job = form.save(commit=False)
        job.created_by = self.request.user
        job.save()
        form.save_m2m()  # Important for ManyToManyField ('classes_to_invoice')

        generate_invoices_task.delay(str(job.job_id))
        messages.info(self.request,
                      "Invoice generation has been started in the background. You will be redirected to the status page.")
        return redirect('finance_invoice_job_status', pk=job.job_id)


class InvoiceJobStatusView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = InvoiceGenerationJob
    template_name = 'finance/invoice/status.html'
    context_object_name = 'job'
    permission_required = 'finance.view_feemodel'


def invoice_job_status_api(request, pk):
    job = get_object_or_404(InvoiceGenerationJob, pk=pk)
    return JsonResponse({
        'status': job.get_status_display(),
        'total_students': job.total_students,
        'processed_students': job.processed_students,
        'error_message': job.error_message,
        'is_complete': job.status in ['success', 'failure']
    })


# ===================================================================
# Invoice and Payment Management Views
# ===================================================================

class InvoiceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = InvoiceModel
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/invoice/index.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        """
        This method builds the list of invoices based on the filters
        and search query from the URL.
        """
        # Start with the base queryset and pre-fetch related models for performance
        queryset = super().get_queryset().select_related(
            'student', 'student__student_class', 'student__class_section', 'session', 'term'
        )

        # Get filter values from the request's GET parameters
        search_query = self.request.GET.get('q', '').strip()
        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        status = self.request.GET.get('status', '')

        # Apply session filter
        if session_id:
            queryset = queryset.filter(session_id=session_id)

        # Apply term filter
        if term_id:
            queryset = queryset.filter(term_id=term_id)

        # Apply status filter
        if status:
            queryset = queryset.filter(status=status)

        # Apply search query
        if search_query:
            # Annotate the student's full name to make it searchable
            queryset = queryset.annotate(
                student_full_name=Concat(
                    'student__first_name', Value(' '), 'student__last_name'
                )
            ).filter(
                Q(student_full_name__icontains=search_query) |
                Q(student__registration_number__icontains=search_query) |
                Q(invoice_number__icontains=search_query)
            )

        return queryset.order_by('-issue_date')

    def get_context_data(self, **kwargs):
        """
        This method adds the necessary data for the filter dropdowns and
        to remember the user's current selections.
        """
        context = super().get_context_data(**kwargs)
        school_setting = SchoolSettingModel.objects.first()

        # Data for the filter dropdowns
        context['sessions'] = SessionModel.objects.all().order_by('-start_year')
        context['terms'] = TermModel.objects.all().order_by('order')
        context['status_choices'] = InvoiceModel.Status.choices

        # Get the currently selected filter values to keep them selected in the form
        selected_session_id = self.request.GET.get('session')
        selected_term_id = self.request.GET.get('term')

        # Pass the selected objects or defaults to the template
        if selected_session_id:
            context['selected_session'] = SessionModel.objects.get(pk=selected_session_id)
        elif school_setting:
            context['selected_session'] = school_setting.session

        if selected_term_id:
            context['selected_term'] = TermModel.objects.get(pk=selected_term_id)
        elif school_setting:
            context['selected_term'] = school_setting.term

        context['selected_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('q', '')

        return context


class InvoiceDetailView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = FeePaymentModel
    form_class = FeePaymentForm
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/invoice/detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.invoice = get_object_or_404(InvoiceModel, pk=self.kwargs['pk'])
        context['invoice'] = self.invoice
        context['payments'] = self.invoice.payments.all().order_by('-date')
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['invoice'] = get_object_or_404(InvoiceModel, pk=self.kwargs['pk'])
        return kwargs

    def form_valid(self, form):
        invoice = get_object_or_404(InvoiceModel, pk=self.kwargs['pk'])
        payment = form.save(commit=False)
        payment.invoice = invoice
        payment.status = FeePaymentModel.PaymentStatus.CONFIRMED  # Or based on your workflow
        payment.confirmed_by = self.request.user
        payment.save()

        # Update invoice status
        if invoice.balance <= 0:
            invoice.status = InvoiceModel.Status.PAID
        else:
            invoice.status = InvoiceModel.Status.PARTIALLY_PAID
        invoice.save()

        messages.success(self.request, "Payment recorded successfully.")
        return redirect('finance_invoice_detail', pk=invoice.pk)


class StudentFeeSearchView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'finance.add_feemodel'
    template_name = 'finance/payment/select_student.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get classes with sections as JSON-serializable data
        class_list = []
        for cls in ClassesModel.objects.prefetch_related('section').all().order_by('name'):
            class_list.append({
                'id': cls.id,
                'name': cls.name,
                'sections': [{'id': s.id, 'name': s.name} for s in cls.section.all()]
            })

        context['class_list'] = ClassesModel.objects.prefetch_related('section').all().order_by('name')
        context['class_list_json'] = json.dumps(class_list)

        # Pre-load students with related names
        all_students = StudentModel.objects.filter(status='active').select_related('student_class', 'class_section')

        # Create custom student data with class/section names
        student_data = []
        for student in all_students:
            student_data.append({
                'pk': student.id,
                'fields': {
                    'first_name': student.first_name,
                    'last_name': student.last_name,
                    'registration_number': student.registration_number,
                    'gender': student.gender,
                    'image': student.image.url if student.image else '',
                    'student_class_id': student.student_class.id if student.student_class else '',
                    'student_class_name': student.student_class.name if student.student_class else '',
                    'class_section_id': student.class_section.id if student.class_section else '',
                    'class_section_name': student.class_section.name if student.class_section else '',
                }
            })

        context['student_list_json'] = json.dumps(student_data)
        return context


def get_students_by_class_ajax(request):
    """AJAX endpoint to fetch students for a given class and section."""
    class_pk = request.GET.get('class_pk')
    section_pk = request.GET.get('section_pk')
    students = StudentModel.objects.filter(student_class_id=class_pk, class_section_id=section_pk, status='active')
    return render(request, 'finance/payment/partials/student_search_results.html', {'students': students})


def get_students_by_reg_no_ajax(request):
    """AJAX endpoint to fetch students by registration number."""
    reg_no = request.GET.get('reg_no', '').strip()
    students = StudentModel.objects.filter(registration_number__icontains=reg_no, status='active')
    return render(request, 'finance/payment/partials/student_search_results.html', {'students': students})


class StudentFinancialDashboardView(LoginRequiredMixin, PermissionRequiredMixin, TemplateView):
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/payment/student_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = get_object_or_404(StudentModel, pk=self.kwargs['pk'])
        context['student'] = student

        school_setting = SchoolSettingModel.objects.first()

        # --- NEW LOGIC: Load a specific invoice or the current one ---
        invoice_id = self.request.GET.get('invoice_id')
        if invoice_id:
            # Load a specific invoice from the history
            current_invoice = get_object_or_404(student.invoices, pk=invoice_id)
        else:
            # Default to the invoice for the current term
            current_invoice = student.invoices.filter(
                session=school_setting.session, term=school_setting.term
            ).first()

        context['current_invoice'] = current_invoice
        context['invoice_history'] = student.invoices.order_by('-session__start_year', '-term__order')
        context['all_payments'] = FeePaymentModel.objects.filter(invoice__student=student).order_by('-date')

        # Pass the form for payment details, bound to the current invoice
        if current_invoice:
            context['payment_form'] = FeePaymentForm()
        else:
            context['payment_form'] = FeePaymentForm()

        return context

    def post(self, request, *args, **kwargs):
        student = get_object_or_404(StudentModel, pk=self.kwargs.get('pk'))
        invoice_id = request.POST.get('invoice_id')
        invoice = get_object_or_404(InvoiceModel, pk=invoice_id)

        # 1. Instantiate the form that holds the payment details (mode, date, bank)
        # We pass the `invoice` so its clean methods (like max amount) work
        payment_form = FeePaymentForm(request.POST)

        # 2. Loop through item payments to calculate total and prep data
        total_paid_in_transaction = Decimal('0.00')
        item_payment_data = {}  # Stores {item_instance: amount_to_pay}

        for key, value in request.POST.items():
            if key.startswith('item_') and value:
                try:
                    item_id = int(key.split('_')[1])
                    amount_for_item = Decimal(value)

                    if amount_for_item > 0:
                        item = get_object_or_404(InvoiceItemModel, pk=item_id, invoice=invoice)

                        # Don't allow overpayment on a single item
                        payable_amount = min(amount_for_item, item.balance)

                        # Store this for the atomic transaction
                        item_payment_data[item] = payable_amount
                        total_paid_in_transaction += payable_amount

                except (ValueError, TypeError, InvoiceItemModel.DoesNotExist):
                    # Malicious or bad data, just skip it
                    continue

        # 3. Check if any payment was made AND if the payment details are valid
        if total_paid_in_transaction <= 0:
            messages.warning(request, "No payment amount was entered.")
            return redirect('finance_student_dashboard', pk=student.pk)

        if payment_form.is_valid():
            # --- This is the fix ---
            # We have valid payment details from the form
            # and a valid total from our item loop.
            try:
                with transaction.atomic():
                    # First, apply the payments to the individual items
                    for item, amount in item_payment_data.items():
                        item.amount_paid += amount
                        item.save(update_fields=['amount_paid'])

                        # Now, create the single FeePaymentModel using the *cleaned form data*
                    FeePaymentModel.objects.create(
                        invoice=invoice,
                        amount=total_paid_in_transaction,

                        # Use cleaned_data, not request.POST
                        payment_mode=payment_form.cleaned_data['payment_mode'],
                        date=payment_form.cleaned_data['date'],  # This is now a clean date object
                        bank_account=payment_form.cleaned_data['bank_account'],
                        # This is now a SchoolBankDetail instance
                        reference=payment_form.cleaned_data['reference'],
                        notes=payment_form.cleaned_data['notes'],

                        status=FeePaymentModel.PaymentStatus.CONFIRMED,
                        confirmed_by=request.user
                    )

                    # Finally, update the parent invoice's status
                    invoice.refresh_from_db()  # Get fresh balance calculations
                    if invoice.balance <= Decimal('0.01'):
                        invoice.status = InvoiceModel.Status.PAID
                    else:
                        invoice.status = InvoiceModel.Status.PARTIALLY_PAID
                    invoice.save(update_fields=['status'])

                    messages.success(request,
                                     f"Payment of SAR {total_paid_in_transaction:,.2f} was applied successfully.")

            except Exception as e:
                # This will catch any unexpected errors during the transaction
                messages.error(request, f"An error occurred while saving the payment: {e}")

        else:
            # The payment details (e.g., no date, no bank) were invalid.
            messages.error(request, "Payment failed: The payment details (mode, date, or bank) were invalid.")
            # Add the specific form errors
            for field, errors in payment_form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.title()}: {error}")

        return redirect('finance_student_dashboard', pk=student.pk)


class InvoiceReceiptView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = InvoiceModel
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/payment/invoice_receipt.html'
    context_object_name = 'invoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # You can add school settings to the context if needed for the header
        # context['school_setting'] = SchoolSettingModel.objects.first()
        return context


class FeePaymentListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = FeePaymentModel
    permission_required = 'finance.view_feemodel'  # Assumes default permission
    template_name = 'finance/payment/payment_index.html'
    context_object_name = 'payment_list'
    paginate_by = 25

    def get_queryset(self):
        # Start with a base queryset, pre-fetching related data for efficiency
        queryset = FeePaymentModel.objects.select_related(
            'invoice__student',
            'invoice__session',
            'invoice__term'
        ).order_by('-date', '-created_at')

        # Get filter parameters from the URL
        session_id = self.request.GET.get('session', '')
        term_id = self.request.GET.get('term', '')
        search_query = self.request.GET.get('search', '').strip()

        # Apply filters if they exist
        if session_id:
            queryset = queryset.filter(invoice__session_id=session_id)

        if term_id:
            queryset = queryset.filter(invoice__term_id=term_id)

        # Apply search query if it exists
        if search_query:
            # Annotate the student's full name to make it searchable
            queryset = queryset.annotate(
                student_full_name=Concat(
                    'invoice__student__first_name', Value(' '), 'invoice__student__last_name'
                )
            ).filter(
                Q(student_full_name__icontains=search_query) |
                Q(invoice__student__registration_number__icontains=search_query) |
                Q(invoice__invoice_number__icontains=search_query)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Pass data for the filter dropdowns
        context['session_list'] = SessionModel.objects.all().order_by('-start_year')
        context['term_list'] = TermModel.objects.all().order_by('order')

        # Pass current filter values back to the template to maintain state
        context['current_session_id'] = self.request.GET.get('session', '')
        context['current_term_id'] = self.request.GET.get('term', '')
        context['search_query'] = self.request.GET.get('search', '')

        return context


class BulkFeePaymentView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """
    Handles a single "bulk" payment that is intelligently allocated
    across multiple outstanding invoices for a student, oldest first.
    """
    form_class = BulkPaymentForm
    permission_required = 'finance.add_feemodel'
    template_name = 'finance/payment/bulk_payment_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        self.student = get_object_or_404(StudentModel, pk=self.kwargs['pk'])
        context['student'] = self.student
        context['outstanding_invoices'] = self.student.invoices.exclude(status=InvoiceModel.Status.PAID).order_by(
            'issue_date')
        return context

    def form_valid(self, form):
        student = get_object_or_404(StudentModel, pk=self.kwargs['pk'])
        total_amount_paid = form.cleaned_data['amount']
        amount_to_allocate = total_amount_paid

        # Get all unpaid or partially paid invoices, oldest first, to pay them off in order.
        outstanding_invoices = student.invoices.exclude(status=InvoiceModel.Status.PAID).order_by('issue_date')

        with transaction.atomic():
            for invoice in outstanding_invoices:
                if amount_to_allocate <= 0:
                    break

                payment_for_this_invoice = min(invoice.balance, amount_to_allocate)

                if payment_for_this_invoice > 0:
                    FeePaymentModel.objects.create(
                        invoice=invoice,
                        amount=payment_for_this_invoice,
                        payment_mode=form.cleaned_data['payment_mode'],
                        date=form.cleaned_data['date'],
                        reference=form.cleaned_data.get('reference') or f"bulk-pmt-{invoice.invoice_number}",
                        status=FeePaymentModel.PaymentStatus.CONFIRMED,
                        confirmed_by=self.request.user
                    )

                    # Refresh invoice from DB before checking balance again
                    invoice.refresh_from_db()
                    if invoice.balance <= Decimal('0.01'):
                        invoice.status = InvoiceModel.Status.PAID
                    else:
                        invoice.status = InvoiceModel.Status.PARTIALLY_PAID
                    invoice.save()

                    amount_to_allocate -= payment_for_this_invoice

        messages.success(self.request,
                         f"Bulk payment of ₦{total_amount_paid} allocated successfully across outstanding invoices.")
        return redirect('finance_student_dashboard', pk=student.pk)


class FeePaymentRevertView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Handles reverting a confirmed student fee payment to safely correct errors."""
    permission_required = 'finance.add_feemodel'

    def post(self, request, *args, **kwargs):
        payment = get_object_or_404(FeePaymentModel, pk=self.kwargs['pk'])
        invoice = payment.invoice

        with transaction.atomic():
            payment.status = FeePaymentModel.PaymentStatus.REVERTED  # Or use a more complex logic
            payment.save()

            # After reverting, re-evaluate and update the invoice status.
            invoice.refresh_from_db()
            if invoice.amount_paid <= 0:
                invoice.status = InvoiceModel.Status.UNPAID
            else:
                invoice.status = InvoiceModel.Status.PARTIALLY_PAID
            invoice.save()

        messages.warning(request, f"Payment {payment.reference} has been reverted.")
        return redirect('finance_student_dashboard', pk=invoice.student.pk)


class FeePaymentReceiptView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Displays a printable receipt for a single student fee payment."""
    model = FeePaymentModel
    permission_required = 'finance.view_feemodel'
    template_name = 'finance/payment/receipt.html'
    context_object_name = 'payment'


# -------------------------
# Expense Category Views
# -------------------------
class ExpenseCategoryCreateView(
    LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView
):
    model = ExpenseCategoryModel
    permission_required = 'finance.add_expensemodel'
    form_class = ExpenseCategoryForm
    template_name = 'finance/expense_category/index.html'
    success_message = 'Expense Category Successfully Created'

    def get_success_url(self):
        return reverse('expense_category_index')

    def dispatch(self, request, *args, **kwargs):
        # original UX: POST-only create endpoint; GET redirects back to index
        if request.method == 'GET':
            return redirect(reverse('expense_category_index'))
        return super().dispatch(request, *args, **kwargs)


class ExpenseCategoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ExpenseCategoryModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/expense_category/index.html'
    context_object_name = "category_list"

    def get_queryset(self):
        return ExpenseCategoryModel.objects.all().order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = ExpenseCategoryForm()
        return context


class ExpenseCategoryUpdateView(
    LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView
):
    model = ExpenseCategoryModel
    permission_required = 'finance.add_expensemodel'
    form_class = ExpenseCategoryForm
    template_name = 'finance/expense_category/index.html'
    success_message = 'Expense Category Successfully Updated'

    def get_success_url(self):
        return reverse('expense_category_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(reverse('expense_category_index'))
        return super().dispatch(request, *args, **kwargs)


class ExpenseCategoryDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ExpenseCategoryModel
    permission_required = 'finance.add_expensemodel'
    template_name = 'finance/expense_category/delete.html'
    context_object_name = "category"
    success_message = 'Expense Category Successfully Deleted'

    def get_success_url(self):
        return reverse('expense_category_index')


# -------------------------
# Expense Views
# -------------------------
class ExpenseListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ExpenseModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/expense/index.html'
    context_object_name = "expense_list"
    paginate_by = 20

    def get_queryset(self):
        # only select related fields that exist on your model
        queryset = ExpenseModel.objects.select_related(
            'category', 'session', 'term', 'created_by'
        ).order_by('-expense_date')

        # Filter by category, session, term
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category_id=category)

        session = self.request.GET.get('session')
        if session:
            queryset = queryset.filter(session_id=session)

        term = self.request.GET.get('term')
        if term:
            queryset = queryset.filter(term_id=term)

        # Search over description and reference
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(reference__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = ExpenseCategoryModel.objects.all().order_by('name')
        # removed departments - not in your model
        context['total_amount'] = self.get_queryset().aggregate(Sum('amount'))['amount__sum'] or 0
        return context


class ExpenseCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ExpenseModel
    permission_required = 'finance.add_expensemodel'
    form_class = ExpenseForm
    template_name = 'finance/expense/create.html'
    success_message = 'Expense Successfully Created'

    def get_success_url(self):
        return reverse('expense_detail', kwargs={'pk': self.object.pk})


class ExpenseUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = ExpenseModel
    permission_required = 'finance.add_expensemodel'
    form_class = ExpenseForm
    template_name = 'finance/expense/edit.html'
    success_message = 'Expense Successfully Updated'

    def get_success_url(self):
        return reverse('expense_detail', kwargs={'pk': self.object.pk})


class ExpenseDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ExpenseModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/expense/detail.html'
    context_object_name = "expense"


# -------------------------
# Income Category Views
# -------------------------
class IncomeCategoryCreateView(
    LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView
):
    model = IncomeCategoryModel
    permission_required = 'finance.add_expensemodel'
    form_class = IncomeCategoryForm
    template_name = 'finance/income_category/index.html'
    success_message = 'Income Category Successfully Created'

    def get_success_url(self):
        return reverse('income_category_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(reverse('income_category_index'))
        return super().dispatch(request, *args, **kwargs)


class IncomeCategoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = IncomeCategoryModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/income_category/index.html'
    context_object_name = "category_list"

    def get_queryset(self):
        return IncomeCategoryModel.objects.all().order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = IncomeCategoryForm()
        return context


class IncomeCategoryUpdateView(
    LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView
):
    model = IncomeCategoryModel
    permission_required = 'finance.add_expensemodel'
    form_class = IncomeCategoryForm
    template_name = 'finance/income_category/index.html'
    success_message = 'Income Category Successfully Updated'

    def get_success_url(self):
        return reverse('income_category_index')

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(reverse('income_category_index'))
        return super().dispatch(request, *args, **kwargs)


class IncomeCategoryDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = IncomeCategoryModel
    permission_required = 'finance.add_expensemodel'
    template_name = 'finance/income_category/delete.html'
    context_object_name = "category"
    success_message = 'Income Category Successfully Deleted'

    def get_success_url(self):
        return reverse('income_category_index')


# -------------------------
# Income Views
# -------------------------
class IncomeListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = IncomeModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/income/index.html'
    context_object_name = "income_list"
    paginate_by = 20

    def get_queryset(self):
        queryset = IncomeModel.objects.select_related(
            'category', 'session', 'term', 'created_by'
        ).order_by('-income_date')

        # Filter by category, session, term
        category = self.request.GET.get('category')
        if category:
            queryset = queryset.filter(category_id=category)

        session = self.request.GET.get('session')
        if session:
            queryset = queryset.filter(session_id=session)

        term = self.request.GET.get('term')
        if term:
            queryset = queryset.filter(term_id=term)

        # Search over description, reference, source
        search = self.request.GET.get('search')
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search) |
                Q(reference__icontains=search) |
                Q(source__icontains=search)
            )

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categories'] = IncomeCategoryModel.objects.all().order_by('name')
        # removed departments
        context['total_amount'] = self.get_queryset().aggregate(Sum('amount'))['amount__sum'] or 0
        return context


class IncomeCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = IncomeModel
    permission_required = 'finance.add_expensemodel'
    form_class = IncomeForm
    template_name = 'finance/income/create.html'
    success_message = 'Income Successfully Created'

    def get_success_url(self):
        return reverse('income_detail', kwargs={'pk': self.object.pk})


class IncomeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = IncomeModel
    permission_required = 'finance.add_expensemodel'
    form_class = IncomeForm
    template_name = 'finance/income/edit.html'
    success_message = 'Income Successfully Updated'

    def get_success_url(self):
        return reverse('income_detail', kwargs={'pk': self.object.pk})


class IncomeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = IncomeModel
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/income/detail.html'
    context_object_name = "income"


# ===================================================================
# Staff Bank Detail Views (Modal Interface)
# ===================================================================
class StaffBankDetailListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = StaffBankDetail
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/staff_bank/index.html'
    context_object_name = "bank_detail_list"

    def get_queryset(self):
        return StaffBankDetail.objects.select_related('staff__staff_profile__user').order_by(
            'staff__staff_profile__user__first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = StaffBankDetailForm()
        return context


class StaffBankDetailCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = StaffBankDetail
    permission_required = 'finance.add_salaryrecord'
    form_class = StaffBankDetailForm

    def get_success_url(self):
        return reverse('finance_staff_bank_detail_list')

    def form_valid(self, form):
        messages.success(self.request, "Bank Detail Created Successfully.")
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class StaffBankDetailUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = StaffBankDetail
    permission_required = 'finance.add_salaryrecord'
    form_class = StaffBankDetailForm
    success_url = reverse_lazy('finance_staff_bank_detail_list')

    def form_valid(self, form):
        messages.success(self.request, "Bank Detail Updated Successfully.")
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class StaffBankDetailDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = StaffBankDetail
    permission_required = 'finance.add_salaryrecord'
    template_name = 'finance/staff_bank/delete.html'
    context_object_name = "bank_detail"
    success_url = reverse_lazy('finance_staff_bank_detail_list')

    def form_valid(self, form):
        messages.success(self.request, "Bank Detail Deleted Successfully.")
        return super().form_valid(form)


# ===================================================================
# School Bank Detail Views (Modal Interface)
# ===================================================================
class SchoolBankDetailListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = SchoolBankDetail
    permission_required = 'finance.view_expensemodel'
    template_name = 'finance/school_bank/index.html'
    context_object_name = "school_bank_detail_list"

    def get_queryset(self):
        return SchoolBankDetail.objects.order_by('bank_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Assuming you will create a SchoolBankDetailForm
        context['form'] = SchoolBankDetailForm()
        return context


class SchoolBankDetailCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = SchoolBankDetail
    permission_required = 'finance.add_expensemodel'
    form_class = SchoolBankDetailForm

    def get_success_url(self):
        return reverse('finance_school_bank_detail_list')

    def form_valid(self, form):
        messages.success(self.request, "School Bank Detail Created Successfully.")
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class SchoolBankDetailUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = SchoolBankDetail
    permission_required = 'finance.add_expensemodel'
    form_class = SchoolBankDetailForm
    success_url = reverse_lazy('finance_school_bank_detail_list')

    def form_valid(self, form):
        messages.success(self.request, "School Bank Detail Updated Successfully.")
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class SchoolBankDetailDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = SchoolBankDetail
    permission_required = 'finance.add_expensemodel'
    template_name = 'finance/school_bank/delete.html'
    context_object_name = "school_bank_detail"
    success_url = reverse_lazy('finance_school_bank_detail_list')

    def form_valid(self, form):
        messages.success(self.request, "School Bank Detail Deleted Successfully.")
        return super().form_valid(form)


# ===================================================================
# Salary Structure Views (Multi-page Interface)
# ===================================================================
class SalaryStructureListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = SalaryStructure
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/salary_structure/index.html'
    context_object_name = "salary_structure_list"

    def get_queryset(self):
        return SalaryStructure.objects.select_related('staff__staff_profile__user').order_by(
            'staff__staff_profile__user__first_name')


class SalaryStructureCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = SalaryStructure
    permission_required = 'finance.add_salaryrecord'
    form_class = SalaryStructureForm
    template_name = 'finance/salary_structure/create.html'

    def get_success_url(self):
        messages.success(self.request, "Salary Structure Created Successfully.")
        return reverse('finance_salary_structure_detail', kwargs={'pk': self.object.pk})


class SalaryStructureUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = SalaryStructure
    permission_required = 'finance.add_salaryrecord'
    form_class = SalaryStructureForm
    template_name = 'finance/salary_structure/edit.html'

    def get_success_url(self):
        messages.success(self.request, "Salary Structure Updated Successfully.")
        return reverse('finance_salary_structure_detail', kwargs={'pk': self.object.pk})


class SalaryStructureDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SalaryStructure
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/salary_structure/detail.html'
    context_object_name = "salary_structure"


class SalaryStructureDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = SalaryStructure
    permission_required = 'finance.add_salaryrecord'
    template_name = 'finance/salary_structure/delete.html'
    success_url = reverse_lazy('finance_salary_structure_list')

    def form_valid(self, form):
        messages.success(self.request, "Salary Structure Deleted Successfully.")
        return super().form_valid(form)


# ===================================================================
# Salary Advance Views (NEW - Multi-page Interface)
# ===================================================================
class SalaryAdvanceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = SalaryAdvance
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/salary_advance/index.html'
    context_object_name = 'advances'
    paginate_by = 15

    def get_queryset(self):
        # Add search and filter logic here
        return super().get_queryset().select_related('staff__staff_profile__user').order_by('-request_date')


class SalaryAdvanceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = SalaryAdvance
    permission_required = 'finance.add_salaryrecord'
    form_class = SalaryAdvanceForm
    template_name = 'finance/salary_advance/create.html'

    def get_success_url(self):
        messages.success(self.request, "Salary advance request submitted successfully.")
        return reverse('finance_salary_advance_detail', kwargs={'pk': self.object.pk})


class SalaryAdvanceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SalaryAdvance
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/salary_advance/detail.html'
    context_object_name = 'advance'


class SalaryAdvanceActionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """A single view to handle all status changes for a salary advance."""
    permission_required = 'finance.add_salaryrecord'

    def post(self, request, *args, **kwargs):
        advance = get_object_or_404(SalaryAdvance, pk=self.kwargs.get('pk'))
        action = request.POST.get('action')

        if action == 'approve' and advance.status == 'pending':
            advance.status = SalaryAdvance.Status.APPROVED
            advance.approved_by = request.user
            advance.approved_date = date.today()
            advance.save()
            messages.success(request, "Salary advance has been approved.")
        elif action == 'reject' and advance.status == 'pending':
            advance.status = SalaryAdvance.Status.REJECTED
            advance.save()
            messages.warning(request, "Salary advance has been rejected.")
        elif action == 'disburse' and advance.status == 'approved':
            advance.status = SalaryAdvance.Status.DISBURSED
            # In a real system, you might link this to an Expense record
            advance.save()
            messages.info(request, "Salary advance marked as disbursed.")
        else:
            messages.error(request, "Invalid action or status.")

        return redirect('finance_salary_advance_detail', pk=advance.pk)


# ===================================================================
# Staff Loan Views
# ===================================================================
class StaffLoanListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = StaffLoan
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/staff_loan/index.html'
    context_object_name = 'loans'
    paginate_by = 15

    def get_queryset(self):
        return super().get_queryset().select_related('staff__staff_profile__user').order_by('-request_date')


class StaffLoanCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = StaffLoan
    permission_required = 'finance.add_salaryrecord'
    form_class = StaffLoanForm
    template_name = 'finance/staff_loan/create.html'

    def get_success_url(self):
        messages.success(self.request, "Staff loan request submitted successfully.")
        return reverse('finance_staff_loan_detail', kwargs={'pk': self.object.pk})


class StaffLoanDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = StaffLoan
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/staff_loan/detail.html'
    context_object_name = 'loan'


class StaffLoanActionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'finance.add_salaryrecord'

    def post(self, request, *args, **kwargs):
        loan = get_object_or_404(StaffLoan, pk=self.kwargs.get('pk'))
        action = request.POST.get('action')

        if action == 'approve' and loan.status == 'pending':
            loan.status = StaffLoan.Status.APPROVED
            loan.approved_by = request.user
            loan.approved_date = date.today()
            loan.save()
            messages.success(request, "Staff loan has been approved.")
        elif action == 'reject' and loan.status == 'pending':
            loan.status = StaffLoan.Status.REJECTED
            loan.save()
            messages.warning(request, "Staff loan has been rejected.")
        elif action == 'disburse' and loan.status == 'approved':
            loan.status = StaffLoan.Status.DISBURSED
            loan.save()
            messages.info(request, "Staff loan marked as disbursed.")
        else:
            messages.error(request, "Invalid action or status.")
        return redirect('finance_staff_loan_detail', pk=loan.pk)


class StaffLoanDebtorsListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = StaffModel
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/staff_loan/debtors_list.html'
    context_object_name = 'debtors'

    def get_queryset(self):
        return StaffModel.objects.annotate(
            total_loan=Coalesce(Sum('staff_loans__amount', filter=Q(staff_loans__status__in=['disbursed', 'completed'])), Value(0), output_field=DecimalField()),
            total_repaid=Coalesce(Sum('staff_loans__repaid_amount', filter=Q(staff_loans__status__in=['disbursed', 'completed'])), Value(0), output_field=DecimalField())
        ).annotate(
            total_due=F('total_loan') - F('total_repaid')
        ).filter(total_due__gt=0).order_by('staff_profile__user__last_name')


class StaffLoanDebtDetailView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """Shows a breakdown of a staff's debt, repayment history, and a repayment form."""
    permission_required = 'finance.view_salaryrecord'
    template_name = 'finance/staff_loan/staff_debt_detail.html'

    def get(self, request, *args, **kwargs):
        staff = get_object_or_404(StaffModel, pk=self.kwargs.get('staff_pk'))

        # Get all loans that are currently owing
        outstanding_loans = StaffLoan.objects.filter(
            staff=staff,
            status=StaffLoan.Status.DISBURSED
        ).order_by('request_date')

        # Calculate total amount due from outstanding loans
        total_due = sum(loan.balance for loan in outstanding_loans)

        # NEW: Get the history of all past repayment transactions
        repayment_history = StaffLoanRepayment.objects.filter(
            staff=staff
        ).select_related('created_by').order_by('-payment_date', '-created_at')

        # The form for making a new payment
        form = StaffLoanRepaymentForm()

        context = {
            'staff': staff,
            'outstanding_loans': outstanding_loans,
            'total_due': total_due,
            'repayment_history': repayment_history,  # Add history to the context
            'form': form
        }
        return render(request, self.template_name, context)


@login_required
@permission_required("finance.add_salaryrecord", raise_exception=True)
@transaction.atomic
def record_staff_loan_repayment(request, staff_pk):
    if request.method != 'POST':
        return redirect('finance_staff_loan_debtors')

    staff = get_object_or_404(StaffModel, pk=staff_pk)
    form = StaffLoanRepaymentForm(request.POST)

    if form.is_valid():
        amount_paid = form.cleaned_data['amount_paid']
        payment_to_apply = amount_paid

        repayment = form.save(commit=False)
        repayment.staff = staff
        repayment.created_by = request.user
        repayment.save()

        outstanding_loans = StaffLoan.objects.filter(staff=staff, status=StaffLoan.Status.DISBURSED).order_by('request_date')
        for loan in outstanding_loans:
            if payment_to_apply <= 0: break
            payment_for_this_loan = min(payment_to_apply, loan.balance)
            loan.repaid_amount += payment_for_this_loan
            payment_to_apply -= payment_for_this_loan
            if loan.balance <= 0:
                loan.status = StaffLoan.Status.COMPLETED
            loan.save()
        messages.success(request, f"Repayment of {amount_paid} recorded for {staff}.")
    else:
        messages.error(request, "Invalid data submitted. Please check the form.")
    return redirect('finance_staff_loan_debt_detail', staff_pk=staff.pk)


@login_required
@permission_required("finance.add_salaryrecord", raise_exception=True)
def process_payroll_view(request):
    # This GET request logic is correct and does not need changes.
    current_year = datetime.now().year
    current_month = datetime.now().month
    try:
        year = int(request.GET.get('year', current_year))
        month = int(request.GET.get('month', current_month))
    except (ValueError, TypeError):
        year = current_year
        month = current_month

    staff_with_structures = StaffModel.objects.filter(salary_structure__is_active=True).select_related(
        'salary_structure')
    for staff in staff_with_structures:
        structure = staff.salary_structure
        total_advance_for_month = \
        SalaryAdvance.objects.filter(staff=staff, status=SalaryAdvance.Status.DISBURSED, request_date__year=year,
                                     request_date__month=month).aggregate(total=Sum('amount'))['total'] or Decimal(
            '0.00')
        record, created = SalaryRecord.objects.get_or_create(staff=staff, year=year, month=month,
                                                             defaults={'basic_salary': structure.basic_salary,
                                                                       'housing_allowance': structure.housing_allowance,
                                                                       'transport_allowance': structure.transport_allowance,
                                                                       'medical_allowance': structure.medical_allowance,
                                                                       'other_allowances': structure.other_allowances,
                                                                       'tax_amount': structure.tax_amount,
                                                                       'pension_amount': structure.pension_amount,
                                                                       'salary_advance_deduction': total_advance_for_month})
        if not created and record.salary_advance_deduction != total_advance_for_month:
            record.salary_advance_deduction = total_advance_for_month
            record.save(update_fields=['salary_advance_deduction'])

    queryset = SalaryRecord.objects.filter(year=year, month=month, staff__in=staff_with_structures).select_related(
        'staff__staff_profile__user')
    PaysheetFormSet = modelformset_factory(SalaryRecord, form=PaysheetRowForm, extra=0)

    # ==============================================================================
    # ===== THIS IS THE NEW, CORRECTED LOGIC FOR SAVING THE FORM =====
    # ==============================================================================
    if request.method == 'POST':
        formset = PaysheetFormSet(request.POST, queryset=queryset)
        if formset.is_valid():

            # We will now manually iterate through every form in the formset
            # and save it explicitly. This bypasses the issue where Django
            # thinks the pre-filled amount hasn't changed.
            for form in formset.forms:
                # Get the instance attached to the form
                instance = form.instance
                # Get the validated data from the submitted form
                cleaned_data = form.cleaned_data

                # Manually update the instance with all the data from the form fields
                instance.bonus = cleaned_data.get('bonus', instance.bonus)
                instance.other_deductions = cleaned_data.get('other_deductions', instance.other_deductions)
                instance.amount_paid = cleaned_data.get('amount_paid', instance.amount_paid)
                instance.notes = cleaned_data.get('notes', instance.notes)

                # Save each instance with its updated data.
                instance.save()

            # 'Mark as Paid' logic can now run on the correctly saved data.
            paid_ids = request.POST.getlist('mark_as_paid')
            if paid_ids:
                paid_records = SalaryRecord.objects.filter(id__in=paid_ids)
                for record in paid_records:
                    if not record.is_paid:
                        record.is_paid = True
                        if record.amount_paid == 0:
                            record.amount_paid = record.net_salary
                        record.paid_date = date.today()
                        record.paid_by = request.user
                        record.save()

            messages.success(request, 'Paysheet saved successfully!')
            return redirect(reverse('finance_process_payroll') + f'?year={year}&month={month}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # The GET request logic and context calculation are correct.
        formset = PaysheetFormSet(queryset=queryset)

    totals = queryset.aggregate(total_bonus=Sum('bonus'), total_advance=Sum('salary_advance_deduction'),
                                total_other_deductions=Sum('other_deductions'))
    total_net_salary = 0
    total_amount_paid = 0
    # We refresh the queryset to get the newly saved values for the totals
    # This is important after a POST request, but doesn't hurt on a GET
    for record in queryset.all():
        total_net_salary += record.net_salary
        if record.amount_paid > 0:
            total_amount_paid += record.amount_paid
        else:
            total_amount_paid += record.net_salary

    context = {
        'formset': formset, 'year': year, 'month': month,
        'years': range(2020, datetime.now().year + 2),
        'months': [(i, datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        'totals': totals, 'total_net_salary': total_net_salary, 'total_amount_paid': total_amount_paid,
    }
    return render(request, 'finance/salary_record/process_payroll.html', context)


@login_required
@permission_required('finance.view_salaryrecord')
def export_payroll_to_excel(request, year, month):
    """
    Generates an Excel file with a detailed breakdown of the payroll for a given month and year.
    """
    # 1. Fetch the relevant salary records
    queryset = SalaryRecord.objects.filter(year=year, month=month).select_related('staff')

    # 2. Create an in-memory Excel workbook
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    month_name = datetime(2000, month, 1).strftime('%B')
    worksheet.title = f'Payroll_{year}_{month_name}'

    # 3. Define the detailed header row
    headers = [
        'Staff ID', 'Full Name', 'Basic Salary', 'Housing', 'Transport', 'Medical',
        'Other Allowances', 'Bonus', 'Gross Salary', 'Tax (PAYE)', 'Pension',
        'Other Deductions', 'Total Deductions', 'Net Salary', 'Amount Paid', 'Status', 'Notes'
    ]
    for col_num, header_title in enumerate(headers, 1):
        cell = worksheet.cell(row=1, column=col_num, value=header_title)
        cell.font = Font(bold=True)

    # 4. Write data rows for each salary record
    for row_num, record in enumerate(queryset, 2):
        worksheet.cell(row=row_num, column=1, value=record.staff.staff_id)
        worksheet.cell(row=row_num, column=2, value=record.staff.__str__())
        worksheet.cell(row=row_num, column=3, value=record.basic_salary)
        worksheet.cell(row=row_num, column=4, value=record.housing_allowance)
        worksheet.cell(row=row_num, column=5, value=record.transport_allowance)
        worksheet.cell(row=row_num, column=6, value=record.medical_allowance)
        worksheet.cell(row=row_num, column=7, value=record.other_allowances)
        worksheet.cell(row=row_num, column=8, value=record.bonus)
        worksheet.cell(row=row_num, column=9, value=record.gross_salary)
        worksheet.cell(row=row_num, column=10, value=record.tax_amount)
        worksheet.cell(row=row_num, column=11, value=record.pension_amount)
        worksheet.cell(row=row_num, column=12, value=record.other_deductions)
        worksheet.cell(row=row_num, column=13, value=record.total_deductions)
        worksheet.cell(row=row_num, column=14, value=record.net_salary)
        worksheet.cell(row=row_num, column=15, value=record.amount_paid)
        worksheet.cell(row=row_num, column=16, value=record.payment_status)
        worksheet.cell(row=row_num, column=17, value=record.notes)

    # 5. Create the HttpResponse object with the correct headers
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="payroll_{year}_{month_name}.xlsx"'

    # Save the workbook to the response
    workbook.save(response)

    return response


@login_required
@permission_required('finance.view_salaryrecord')
def payroll_dashboard_view(request):
    """
    Provides data for a dashboard with payroll statistics and visualizations.
    Calculates net salary at the database level to fix the FieldError.
    """
    # Define the net salary calculation using F() objects for database-level arithmetic
    net_salary_expression = (
            F('basic_salary') + F('housing_allowance') + F('transport_allowance') +
            F('medical_allowance') + F('other_allowances') + F('bonus') -
            (F('tax_amount') + F('pension_amount') + F('other_deductions'))
    )

    # Get the current period
    today = datetime.now()
    current_year = today.year
    current_month = today.month

    # Get last month's period for comparison
    last_month_date = today.replace(day=1) - timedelta(days=1)
    last_month = last_month_date.month
    last_year = last_month_date.year

    # --- 1. KPI Cards Data ---
    current_month_payroll = SalaryRecord.objects.filter(year=current_year, month=current_month)
    last_month_payroll = SalaryRecord.objects.filter(year=last_year, month=last_month)

    total_payroll_current = current_month_payroll.aggregate(total=Sum(net_salary_expression))['total'] or 0
    total_payroll_last = last_month_payroll.aggregate(total=Sum(net_salary_expression))['total'] or 0

    staff_paid_count = current_month_payroll.count()
    average_net_salary = current_month_payroll.aggregate(avg=Avg(net_salary_expression))['avg'] or 0

    # Calculate percentage change
    if total_payroll_last > 0:
        percent_change = ((total_payroll_current - total_payroll_last) / total_payroll_last) * 100
    else:
        percent_change = 100 if total_payroll_current > 0 else 0

    # --- 2. Charts Data ---
    # Chart 2: Salary Trend (Line Chart - Last 12 Months)
    twelve_months_ago = today - timedelta(days=365)
    salary_trend = SalaryRecord.objects.filter(paid_date__gte=twelve_months_ago) \
        .annotate(month_year=TruncMonth('paid_date')) \
        .values('month_year') \
        .annotate(total_net=Sum(net_salary_expression)) \
        .order_by('month_year')

    salary_trend_data = [
        {'month': item['month_year'].strftime('%b %Y'), 'total': float(item['total_net'])}
        for item in salary_trend if item['month_year'] and item['total_net']
    ]

    context = {
        # KPI Cards
        'total_payroll_current': total_payroll_current,
        'staff_paid_count': staff_paid_count,
        'average_net_salary': average_net_salary,
        'percent_change': percent_change,

        # Chart Data (passed as JSON)
        'salary_trend_data': json.dumps(salary_trend_data),
    }

    return render(request, 'finance/salary_record/dashboard.html', context)


class DepositPaymentSelectStudentView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, TemplateView):
    template_name = 'finance/funding/select_student.html'
    permission_required = 'finance.add_studentfundingmodel'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['class_list'] = ClassesModel.objects.all().order_by('name')
        student_list = StudentModel.objects.all()
        context['student_list'] = serializers.serialize("json", student_list)
        return context


class DepositPaymentSelectStaffView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, TemplateView):
    template_name = 'finance/funding/select_staff.html'
    permission_required = 'finance.add_studentfundingmodel'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_list = StaffModel.objects.all()
        context['staff_list'] = serializers.serialize("json", staff_list)
        return context


@login_required
def deposit_get_class_students(request):
    class_pk = request.GET.get('class_pk')
    section_pk = request.GET.get('section_pk')

    student_list = StudentModel.objects.filter(student_class=class_pk, class_section=section_pk)
    result = ''
    for student in student_list:
        full_name = "{} {}".format(student.first_name.title(), student.last_name.title())
        result += """<li class='list-group-item select_student d-flex justify-content-between align-items-center' student_id='{}'>
        {} </li>""".format(student.id, full_name)
    if result == '':
        result += """<li class='list-group-item  d-flex justify-content-between align-items-center bg-danger text-white'>
        No Student in Selected Class</li>"""
    return HttpResponse(result)


@login_required
def deposit_get_class_students_by_reg_number(request):
    reg_no = request.GET.get('reg_no')

    student_list = StudentModel.objects.filter(registration_number__contains=reg_no)
    result = ''
    for student in student_list:
        full_name = "{} {}".format(student.first_name.title(), student.last_name.title())
        result += """<li class='list-group-item select_student d-flex justify-content-between align-items-center' student_id={}>
        {} </li>""".format(student.id, full_name)
    if result == '':
        result += """<li class='list-group-item d-flex justify-content-between align-items-center bg-danger text-white'>
        No Student in with inputed Registration Number</li>"""
    return HttpResponse(result)


@login_required
@permission_required("finance.view_studentfundingmodel", raise_exception=True)
def deposit_payment_list_view(request):
    session_id = request.GET.get('session', None)
    school_setting = SchoolSettingModel.objects.first()
    if not session_id:
        session = school_setting.session
    else:
        session = SessionModel.objects.get(id=session_id)
    session_list = SessionModel.objects.all()
    term = request.GET.get('term', None)
    if not term:
        term = school_setting.term
    fee_payment_list = StudentFundingModel.objects.filter(session=session, term=term).exclude(status='pending').order_by('-id')
    context = {
        'fee_payment_list': fee_payment_list,
        'session': session,
        'term': term,
        'session_list': session_list
    }
    return render(request, 'finance/funding/index.html', context)


@login_required
@permission_required("finance.view_studentfundingmodel", raise_exception=True)
def staff_deposit_payment_list_view(request):
    session_id = request.GET.get('session', None)
    school_setting = SchoolSettingModel.objects.first()
    if not session_id:
        session = school_setting.session
    else:
        session = SessionModel.objects.get(id=session_id)
    session_list = SessionModel.objects.all()
    term = request.GET.get('term', None)
    if not term:
        term = school_setting.term
    fee_payment_list = StaffFundingModel.objects.filter(session=session, term=term).exclude(status='pending').order_by('-id')
    context = {
        'fee_payment_list': fee_payment_list,
        'session': session,
        'term': term,
        'session_list': session_list
    }
    return render(request, 'finance/funding/staff_index.html', context)


@login_required
@permission_required("finance.view_studentfundingmodel", raise_exception=True)
def pending_deposit_payment_list_view(request):
    session_id = request.GET.get('session', None)
    session = SessionModel.objects.get(id=session_id)
    term_id = request.GET.get('session', None)
    term = TermModel.objects.get(id=session_id)
    session_list = SessionModel.objects.all()
    term_list = TermModel.objects.all().order_by('order')
    fee_payment_list = StudentFundingModel.objects.filter(session=session, term=term, status='pending').order_by('-id')
    context = {
        'fee_payment_list': fee_payment_list,
        'session': session,
        'term': term,
        'session_list': session_list,
        'term_list': term_list,
    }
    return render(request, 'finance/funding/pending.html', context)


@login_required
@permission_required("finance.add_studentfundingmodel", raise_exception=True)
def deposit_create_view(request, student_pk):
    student = StudentModel.objects.get(pk=student_pk)
    setting = SchoolSettingModel.objects.first()

    if request.method == 'POST':
        form = StudentFundingForm(request.POST, request.FILES)  # Pass request.FILES for file uploads
        if form.is_valid():
            deposit = form.save(commit=False)  # Don't save yet, we need to set the student
            deposit.student = student  # Associate the funding with the student

            try:
                profile = StaffProfileModel.objects.get(user=request.user)
                deposit.created_by = profile.staff
            except Exception:
                pass
            # Set session and term based on school setting if not provided by form
            if not deposit.session:
                deposit.session = setting.session
            if not deposit.term:
                deposit.term = setting.term

            amount = deposit.amount  # Get amount directly from the saved instance
            messages.success(request, f'Deposit of ₦{amount} successful!')

            # Update student wallet
            student_wallet, created = StudentWalletModel.objects.get_or_create(student=student)  # Get or create wallet

            student_wallet.balance += amount

            if student_wallet.debt > 0:
                if student_wallet.balance > student_wallet.debt:
                    student_wallet.balance -= student_wallet.debt
                    student_wallet.debt = 0
                else:
                    student_wallet.debt -= student_wallet.balance
                    student_wallet.balance = 0

            student_wallet.save()

            deposit.balance = student_wallet.balance - student_wallet.debt
            deposit.save()  # Now save the deposit

            target_timezone = pytz_timezone('Africa/Lagos')

            localized_created_at = timezone.localtime(deposit.created_at, timezone=target_timezone)

            formatted_time = localized_created_at.strftime(
                f"%B {localized_created_at.day}{get_day_ordinal_suffix(localized_created_at.day)} %Y %I:%M%p"
            )

            log = f"""
                       <div class='text-white bg-success' style='padding:5px;'>
                       <p class=''>Student Wallet Funding: <a href={reverse('deposit_detail', kwargs={'pk': deposit.id})}><b>₦{amount}</b></a> deposit to wallet of
                       <a href={reverse('student_detail', kwargs={'pk': deposit.student.id})}><b>{deposit.student.__str__().title()}</b></a>
                        by <a href={reverse('staff_detail', kwargs={'pk': deposit.created_by.id})}><b>{deposit.created_by.__str__().title()}</b></a>
                       <br><span style='float:right'>{formatted_time}</span>
                       </p>

                       </div>
                       """

            activity = ActivityLogModel.objects.create(log=log)
            activity.save()

            return redirect('deposit_detail',
                        pk=deposit.pk)  # Redirect to prevent form resubmission on refresh
        else:
            # If form is not valid, messages.error can show form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = StudentFundingForm()  # Instantiate an empty form for GET request

    context = {
        'student': student,
        'form': form,
        'payment_list': StudentFundingModel.objects.filter(student=student, term=setting.term,
                                                           session=setting.session).order_by('-created_at'),
        'setting': setting
    }
    return render(request, 'finance/funding/create.html', context)


@login_required
@permission_required("finance.view_studentfundingmodel", raise_exception=True)
def deposit_detail_view(request, pk):
    deposit = get_object_or_404(StudentFundingModel, pk=pk)

    # Compute total profit here
    return render(request, 'finance/funding/detail.html', {
        'funding': deposit,
    })


@login_required
@permission_required("finance.add_studentfundingmodel", raise_exception=True)
def staff_deposit_create_view(request, staff_pk):
    staff = StaffModel.objects.get(pk=staff_pk)
    setting = SchoolSettingModel.objects.first()

    if request.method == 'POST':
        form = StaffFundingForm(request.POST, request.FILES)  # Pass request.FILES for file uploads
        if form.is_valid():
            deposit = form.save(commit=False)  # Don't save yet, we need to set the staff
            deposit.staff = staff  # Associate the funding with the staff

            try:
                profile = StaffProfileModel.objects.get(user=request.user)
                deposit.created_by = profile.staff
            except Exception:
                pass
            # Set session and term based on school setting if not provided by form
            if not deposit.session:
                deposit.session = setting.session
            if not deposit.term:
                deposit.term = setting.term

            amount = deposit.amount  # Get amount directly from the saved instance
            messages.success(request, f'Deposit of ₦{amount} successful!')

            # Update staff wallet
            staff_wallet, created = StaffWalletModel.objects.get_or_create(staff=staff)  # Get or create wallet

            staff_wallet.balance += amount

            staff_wallet.save()

            deposit.balance = staff_wallet.balance
            deposit.save()  # Now save the deposit

            target_timezone = pytz_timezone('Africa/Lagos')

            localized_created_at = timezone.localtime(deposit.created_at, timezone=target_timezone)

            formatted_time = localized_created_at.strftime(
                f"%B {localized_created_at.day}{get_day_ordinal_suffix(localized_created_at.day)} %Y %I:%M%p"
            )

            log = f"""
                       <div class='text-white bg-success' style='padding:5px;'>
                       <p class=''>Staff Wallet Funding: <a href={reverse('staff_deposit_detail', kwargs={'pk': deposit.id})}><b>₦{amount}</b></a> deposit to wallet of
                       <a href={reverse('staff_detail', kwargs={'pk': deposit.staff.id})}><b>{deposit.staff.__str__().title()}</b></a>
                        by <a href={reverse('staff_detail', kwargs={'pk': deposit.created_by.id})}><b>{deposit.created_by.__str__().title()}</b></a>
                       <br><span style='float:right'>{formatted_time}</span>
                       </p>

                       </div>
                       """

            activity = ActivityLogModel.objects.create(log=log)
            activity.save()

            return redirect('staff_deposit_detail',
                        pk=deposit.pk)  # Redirect to prevent form resubmission on refresh
        else:
            # If form is not valid, messages.error can show form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field.replace('_', ' ').title()}: {error}")
    else:
        form = StaffFundingForm()  # Instantiate an empty form for GET request

    staff_wallet, created = StaffWalletModel.objects.get_or_create(staff=staff)  # Get or create wallet

    context = {
        'staff': staff,
        'form': form,
        'payment_list': StaffFundingModel.objects.filter(staff=staff, term=setting.term,
                                                           session=setting.session).order_by('-created_at'),
        'setting': setting
    }
    return render(request, 'finance/funding/staff_create.html', context)


@login_required
@permission_required("finance.view_studentfundingmodel", raise_exception=True)
def staff_deposit_detail_view(request, pk):
    deposit = get_object_or_404(StaffFundingModel, pk=pk)

    # Compute total profit here
    return render(request, 'finance/funding/staff_detail.html', {
        'funding': deposit,
    })


@login_required
@permission_required("finance.change_studentfundingmodel", raise_exception=True)
@transaction.atomic
def confirm_payment_view(request, payment_id):
    payment = get_object_or_404(StudentFundingModel, pk=payment_id)
    student = payment.student # Get the student associated with this payment

    if request.method == 'POST':
        # Check if the payment is already confirmed or declined
        if payment.status != 'pending':
            messages.warning(request, f"Payment is already {payment.status.capitalize()}. Cannot confirm.")
            # Redirect to a list of payments or the payment detail page
            return redirect(reverse('pending_deposit_index')) # Replace with your actual URL name

        # Get or create student wallet
        student_wallet, created = StudentWalletModel.objects.get_or_create(student=student)

        # Apply the payment amount to the wallet balance
        # Keeping calculations as float as per original deposit_create_view
        student_wallet.balance += payment.amount

        # Apply debt reduction logic
        if student_wallet.debt > 0:
            if student_wallet.balance > student_wallet.debt:
                student_wallet.balance -= student_wallet.debt
                student_wallet.debt = 0.0 # Use 0.0 for float consistency
            else:
                student_wallet.debt -= student_wallet.balance
                student_wallet.balance = 0.0 # Use 0.0 for float consistency

        student_wallet.save() # Save the updated wallet

        # Update the payment status and its internal balance field
        payment.status = 'confirmed'
        # Replicate the balance update from the original view
        payment.balance = student_wallet.balance - student_wallet.debt
        payment.save() # Save the updated payment record

        # Log wallet confirmation
        from pytz import timezone as pytz_timezone
        localized_created_at = timezone.localtime(now(), timezone=pytz_timezone('Africa/Lagos'))
        formatted_time = localized_created_at.strftime(
            f"%B {localized_created_at.day}{get_day_ordinal_suffix(localized_created_at.day)} %Y %I:%M%p"
        )

        student_url = reverse('student_detail', kwargs={'pk': student.pk})
        payment_url = reverse('deposit_detail', kwargs={'pk': payment.pk})
        staff = StaffProfileModel.objects.get(user=request.user).staff
        staff_url = reverse('staff_detail', kwargs={'pk': staff.pk}) if staff else '#'

        log = f"""
        <div class='text-white bg-success p-2' style='border-radius:5px;'>
          <p>
            Payment of <a href="{payment_url}"><b>₦{payment.amount:.2f}</b></a> for
            <a href="{student_url}"><b>{student.__str__().title()}</b></a> was
            <b>confirmed</b> by
            <a href="{staff_url}"><b>{staff.__str__().title()}</b></a>.
            <br>
            <b>Status:</b> Confirmed &nbsp; | &nbsp;
            <b>Wallet Balance:</b> ₦{student_wallet.balance:.2f}
            <span class='float-end'>{now().strftime('%Y-%m-%d %H:%M:%S')}</span>
          </p>
        </div>
        """

        ActivityLogModel.objects.create(
            log=log,
        )

        messages.success(request, f"Payment of ₦{payment.amount} for {student.first_name} {student.last_name} confirmed successfully.")
        return redirect(reverse('deposit_index')) # Replace with your actual URL name

    else:
        # For GET requests to this URL, you might want to display a confirmation prompt
        # or just redirect with a message. Assuming redirect for simplicity.
        messages.info(request, "Please use a POST request to confirm this payment.")
        return redirect(reverse('pending_deposit_index'))  # Replace with your actual URL name


# --- Decline Payment View ---
@login_required
@permission_required("finance.change_studentfundingmodel", raise_exception=True)
@transaction.atomic
def decline_payment_view(request, payment_id):
    payment = get_object_or_404(StudentFundingModel, pk=payment_id)
    student = payment.student # Get the student associated with this payment

    if request.method == 'POST':
        # Check if the payment is already confirmed or declined
        if payment.status != 'pending':
            messages.warning(request, f"Payment is already {payment.status.capitalize()}. Cannot decline.")
            # Redirect to a list of payments or the payment detail page
            return redirect(reverse('pending_deposit_index')) # Replace with your actual URL name

        # Update the payment status to 'declined'
        payment.status = 'declined'
        payment.save()

        # Log wallet deposit decline
        from pytz import timezone as pytz_timezone
        localized_created_at = timezone.localtime(now(), timezone=pytz_timezone('Africa/Lagos'))
        formatted_time = localized_created_at.strftime(
            f"%B {localized_created_at.day}{get_day_ordinal_suffix(localized_created_at.day)} %Y %I:%M%p"
        )

        student_url = reverse('student_detail', kwargs={'pk': student.pk})
        payment_url = reverse('deposit_detail', kwargs={'pk': payment.pk})
        staff = StaffProfileModel.objects.get(user=request.user).staff
        staff_url = reverse('staff_detail', kwargs={'pk': staff.pk}) if staff else '#'

        log = f"""
        <div class='text-white bg-danger p-2' style='border-radius:5px;'>
          <p>
            Payment of <a href="{payment_url}"><b>₦{payment.amount:.2f}</b></a> for
            <a href="{student_url}"><b>{student.__str__().title()}</b></a> was
            <b>declined</b> by
            <a href="{staff_url}"><b>{staff.__str__().title()}</b></a>.
            <br>
            <b>Status:</b> Declined
            <span class='float-end'>{now().strftime('%Y-%m-%d %H:%M:%S')}</span>
          </p>
        </div>
        """

        ActivityLogModel.objects.create(
            log=log,
        )

        messages.success(request, f"Payment of ₦{payment.amount} for {student.first_name} {student.last_name} has been declined.")
        return redirect(reverse('deposit_index'))  # Replace with your actual URL name
    else:
        # For GET requests to this URL, you might want to display a confirmation prompt
        # or just redirect with a message. Assuming redirect for simplicity.
        messages.info(request, "Method Not Supported.")
        return redirect(reverse('pending_deposit_index'))  # Replace with your actual URL name


@login_required
def fee_dashboard(request):
    # Get current session and term or allow filtering
    current_setting = SchoolSettingModel.objects.first()
    selected_session_id = request.GET.get('session',
                                          current_setting.session.id if current_setting and current_setting.session else None)
    selected_term_id = request.GET.get('term',
                                       current_setting.term.id if current_setting and current_setting.term else None)

    if selected_session_id:
        selected_session = SessionModel.objects.get(id=selected_session_id)
    else:
        selected_session = None

    if selected_term_id:
        selected_term = TermModel.objects.get(id=selected_term_id)
    else:
        selected_term = None

    # Base queryset for invoices
    invoice_filter = Q()
    if selected_session:
        invoice_filter &= Q(session=selected_session)
    if selected_term:
        invoice_filter &= Q(term=selected_term)

    invoices = InvoiceModel.objects.filter(invoice_filter)

    # === KEY METRICS ===
    total_expected = invoices.aggregate(
        total=Sum('items__amount')
    )['total'] or Decimal('0.00')

    total_paid = FeePaymentModel.objects.filter(
        invoice__in=invoices,
        status='confirmed'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    total_pending = total_expected - total_paid

    # Student funding (additional payments)
    funding_filter = Q(status='confirmed')
    if selected_session:
        funding_filter &= Q(session=selected_session)
    if selected_term:
        funding_filter &= Q(term=selected_term)

    total_funding = StudentFundingModel.objects.filter(funding_filter).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')

    # Collection rate
    collection_rate = (total_paid / total_expected * 100) if total_expected > 0 else 0

    # === DISTRIBUTION ANALYSIS ===

    # Fee distribution by type
    fee_distribution = InvoiceItemModel.objects.filter(
        invoice__in=invoices
    ).values(
        'fee_master__fee__name'
    ).annotate(
        expected=Sum('amount'),
        paid=Sum('amount_paid'),
        pending=F('expected') - F('paid')
    ).order_by('-expected')

    # Distribution by class
    class_distribution = invoices.values(
        'student__student_class__name'
    ).annotate(
        expected=Sum('items__amount'),
        paid_amount=Sum('payments__amount', filter=Q(payments__status='confirmed')),
        student_count=Count('student', distinct=True)
    ).order_by('-expected')

    # === PAYMENT TRENDS (Last 30 days) ===
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=30)

    daily_payments = []
    current_date = start_date
    while current_date <= end_date:
        day_payments = FeePaymentModel.objects.filter(
            date=current_date,
            status='confirmed',
            invoice__in=invoices
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        daily_payments.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'amount': float(day_payments)
        })
        current_date += timedelta(days=1)

    # === DEFAULTERS & ALERTS ===

    # Students with high outstanding balances
    defaulters = []
    for invoice in invoices.filter(status__in=['unpaid', 'partially_paid']):
        balance = invoice.balance
        if balance > 0:
            defaulters.append({
                'student': invoice.student,
                'class': invoice.student.student_class.name if invoice.student.student_class else 'N/A',
                'balance': balance,
                'invoice': invoice
            })

    # Sort defaulters by balance (highest first)
    defaulters = sorted(defaulters, key=lambda x: x['balance'], reverse=True)[:20]

    # === MONTHLY TRENDS (Last 12 months) ===
    monthly_trends = []
    for i in range(12):
        month_date = end_date.replace(day=1) - timedelta(days=30 * i)
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            month_end = month_date.replace(year=month_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)

        month_payments = FeePaymentModel.objects.filter(
            date__range=[month_start, month_end],
            status='confirmed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        month_funding = StudentFundingModel.objects.filter(
            created_at__date__range=[month_start, month_end],
            status='confirmed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        monthly_trends.append({
            'month': month_date.strftime('%b %Y'),
            'fee_payments': float(month_payments),
            'funding': float(month_funding),
            'total_income': float(month_payments + month_funding)
        })

    monthly_trends.reverse()  # Latest first

    # === PAYMENT METHOD ANALYSIS ===
    payment_methods = FeePaymentModel.objects.filter(
        invoice__in=invoices,
        status='confirmed'
    ).values('payment_mode').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')

    funding_methods = StudentFundingModel.objects.filter(
        funding_filter
    ).values('method').annotate(
        total=Sum('amount'),
        count=Count('id')
    ).order_by('-total')

    # === RECENT ACTIVITY ===
    recent_payments = FeePaymentModel.objects.filter(
        invoice__in=invoices,
        status='confirmed'
    ).select_related(
        'invoice__student', 'invoice__student__student_class'
    ).order_by('-date', '-created_at')[:10]

    recent_funding = StudentFundingModel.objects.filter(
        funding_filter
    ).select_related(
        'student', 'student__student_class'
    ).order_by('-created_at')[:10]

    context = {
        # Filters
        'sessions': SessionModel.objects.all(),
        'terms': TermModel.objects.all(),
        'selected_session': selected_session,
        'selected_term': selected_term,

        # Key metrics
        'total_expected': total_expected,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'total_funding': total_funding,
        'collection_rate': round(collection_rate, 1),
        'total_students': invoices.values('student').distinct().count(),
        'total_invoices': invoices.count(),
        'pending_invoices': invoices.exclude(status='paid').count(),

        # Distributions
        'fee_distribution': fee_distribution,
        'class_distribution': class_distribution,
        'defaulters': defaulters,
        'payment_methods': payment_methods,
        'funding_methods': funding_methods,

        # Recent activity
        'recent_payments': recent_payments,
        'recent_funding': recent_funding,

        # Chart data (JSON)
        'daily_payments_data': json.dumps(daily_payments),
        'monthly_trends_data': json.dumps(monthly_trends),
        'fee_distribution_chart': json.dumps([
            {'name': item['fee_master__fee__name'], 'value': float(item['expected'])}
            for item in fee_distribution
        ]),
        'class_distribution_chart': json.dumps([
            {'name': item['student__student_class__name'] or 'No Class', 'value': float(item['expected'] or 0)}
            for item in class_distribution
        ]),
    }

    return render(request, 'finance/fee_dashboard.html', context)


@login_required
def finance_dashboard(request):
    # Get current session and term or allow filtering
    current_setting = SchoolSettingModel.objects.first()
    selected_session_id = request.GET.get('session',
                                          current_setting.session.id if current_setting and current_setting.session else None)
    selected_term_id = request.GET.get('term',
                                       current_setting.term.id if current_setting and current_setting.term else None)

    if selected_session_id:
        selected_session = SessionModel.objects.get(id=selected_session_id)
    else:
        selected_session = None

    if selected_term_id:
        selected_term = TermModel.objects.get(id=selected_term_id)
    else:
        selected_term = None

    # Base filters
    session_filter = Q()
    term_filter = Q()
    if selected_session:
        session_filter = Q(session=selected_session)
    if selected_term:
        term_filter = Q(term=selected_term)

    combined_filter = session_filter & term_filter

    # === INCOME CALCULATIONS ===

    # 1. Fee payments
    fee_payments = FeePaymentModel.objects.filter(
        status='confirmed'
    )
    if selected_session:
        fee_payments = fee_payments.filter(invoice__session=selected_session)
    if selected_term:
        fee_payments = fee_payments.filter(invoice__term=selected_term)

    total_fee_income = fee_payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 2. Student funding
    total_funding_income = StudentFundingModel.objects.filter(
        combined_filter,
        status='confirmed'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 3. Other income
    total_other_income = IncomeModel.objects.filter(
        combined_filter
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 4. Salary advance repayments
    total_loan_repayments = StaffLoanRepayment.objects.filter(
        combined_filter
    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

    # 5. Purchase advance settlements (payments by staff)
    total_advance_settlements_income = AdvanceSettlementModel.objects.filter(
        settlement_type='payment',
        advance__session=selected_session if selected_session else None,
        advance__term=selected_term if selected_term else None
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    total_income = (total_fee_income + total_funding_income + total_other_income +
                    total_loan_repayments + total_advance_settlements_income)

    # === EXPENSE CALCULATIONS ===

    # 1. General expenses
    total_expenses = ExpenseModel.objects.filter(
        combined_filter
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 2. Salary payments
    total_salary_payments = SalaryRecord.objects.filter(
        combined_filter
    ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

    # 3. Supplier payments
    total_supplier_payments = SupplierPaymentModel.objects.filter(
        combined_filter,
        status='completed'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 4. Purchase advance payments
    total_purchase_advance_payments = PurchaseAdvancePaymentModel.objects.filter(
        advance__session=selected_session if selected_session else None,
        advance__term=selected_term if selected_term else None
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 5. Salary advance disbursements (when status changed to disbursed)
    # Note: This tracks new advances given out, not repayments
    salary_advances_given = SalaryAdvance.objects.filter(
        combined_filter,
        status='disbursed'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    # 6. Advance settlements (refunds to staff)
    total_advance_settlements_expense = AdvanceSettlementModel.objects.filter(
        settlement_type='refund'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    total_expenses_paid = (total_expenses + total_salary_payments + total_supplier_payments +
                           total_purchase_advance_payments + salary_advances_given +
                           total_advance_settlements_expense)

    # === OUTSTANDING RECEIVABLES (What we're owed) ===

    # 1. Unpaid fee balances
    invoice_filter = Q()
    if selected_session:
        invoice_filter &= Q(session=selected_session)
    if selected_term:
        invoice_filter &= Q(term=selected_term)

    invoices = InvoiceModel.objects.filter(invoice_filter)
    total_fee_receivables = sum(invoice.balance for invoice in invoices if invoice.balance > 0)

    # 2. Outstanding salary advances
    outstanding_salary_advances = SalaryAdvance.objects.filter(
        status='disbursed'
    ).aggregate(
        total=Sum(F('amount') - F('repaid_amount'))
    )['total'] or Decimal('0.00')

    # 3. Outstanding purchase advances
    outstanding_purchase_advances = Decimal('0.00')
    try:
        purchase_advances = PurchaseAdvanceModel.objects.filter(
            status='disbursed'
        )
        for advance in purchase_advances:
            outstanding_purchase_advances += (advance.approved_amount - advance.disbursed_amount)
    except:
        pass  # Handle if PurchaseAdvanceModel doesn't have these fields

    total_receivables = total_fee_receivables + outstanding_salary_advances + outstanding_purchase_advances

    # === OUTSTANDING OBLIGATIONS (What we owe) ===

    # 1. Unpaid staff salaries
    # Calculate unpaid salaries manually since net_salary is a property
    unpaid_salaries = Decimal('0.00')
    salary_records = SalaryRecord.objects.filter(combined_filter)

    for record in salary_records:
        if record.net_salary > record.amount_paid:
            unpaid_salaries += (record.net_salary - record.amount_paid)

    total_obligations = unpaid_salaries

    # === NET POSITION ===
    net_cash_position = total_income - total_expenses_paid
    net_overall_position = (total_income + total_receivables) - (total_expenses_paid + total_obligations)

    # === MONTHLY TRENDS (Last 12 months) ===
    monthly_trends = []
    for i in range(12):
        month_date = timezone.now().date().replace(day=1) - timedelta(days=30 * i)
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            month_end = month_date.replace(year=month_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)

        # Monthly income
        month_fee_income = FeePaymentModel.objects.filter(
            date__range=[month_start, month_end],
            status='confirmed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        month_other_income = IncomeModel.objects.filter(
            income_date__range=[month_start, month_end]
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        month_funding = StudentFundingModel.objects.filter(
            created_at__date__range=[month_start, month_end],
            status='confirmed'
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        # Monthly expenses
        month_expenses = ExpenseModel.objects.filter(
            expense_date__range=[month_start, month_end]
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        month_salary_payments = SalaryRecord.objects.filter(
            paid_date__range=[month_start, month_end]
        ).aggregate(total=Sum('amount_paid'))['total'] or Decimal('0.00')

        total_month_income = month_fee_income + month_other_income + month_funding
        total_month_expenses = month_expenses + month_salary_payments

        monthly_trends.append({
            'month': month_date.strftime('%b %Y'),
            'income': float(total_month_income),
            'expenses': float(total_month_expenses),
            'net': float(total_month_income - total_month_expenses)
        })

    monthly_trends.reverse()

    # === INCOME BREAKDOWN ===
    income_breakdown = [
        {'name': 'Fee Payments', 'value': float(total_fee_income)},
        {'name': 'Student Funding', 'value': float(total_funding_income)},
        {'name': 'Other Income', 'value': float(total_other_income)},
        {'name': 'Salary Repayments', 'value': float(total_loan_repayments)},
        {'name': 'Advance Settlements', 'value': float(total_advance_settlements_income)},
    ]

    # === EXPENSE BREAKDOWN ===
    expense_breakdown = [
        {'name': 'General Expenses', 'value': float(total_expenses)},
        {'name': 'Staff Salaries', 'value': float(total_salary_payments)},
        {'name': 'Supplier Payments', 'value': float(total_supplier_payments)},
        {'name': 'Purchase Advances', 'value': float(total_purchase_advance_payments)},
        {'name': 'Salary Advances', 'value': float(salary_advances_given)},
        {'name': 'Staff Refunds', 'value': float(total_advance_settlements_expense)},
    ]

    # === RECENT TRANSACTIONS ===
    recent_income = []

    # Recent fee payments
    recent_fee_payments = fee_payments.select_related(
        'invoice__student'
    ).order_by('-date')[:5]

    for payment in recent_fee_payments:
        recent_income.append({
            'type': 'Fee Payment',
            'description': f'{payment.invoice.student} - {payment.payment_mode}',
            'amount': payment.amount,
            'date': payment.date
        })

    # Recent other income
    recent_other_income = IncomeModel.objects.filter(
        combined_filter
    ).order_by('-income_date')[:3]

    for income in recent_other_income:
        recent_income.append({
            'type': 'Other Income',
            'description': income.description or income.category.name,
            'amount': income.amount,
            'date': income.income_date
        })

    # Sort by date
    recent_income.sort(key=lambda x: x['date'], reverse=True)
    recent_income = recent_income[:10]

    # Recent expenses
    recent_expenses = ExpenseModel.objects.filter(
        combined_filter
    ).select_related('category').order_by('-expense_date')[:10]

    context = {
        # Filters
        'sessions': SessionModel.objects.all(),
        'terms': TermModel.objects.all(),
        'selected_session': selected_session,
        'selected_term': selected_term,

        # Key financial metrics
        'total_income': total_income,
        'total_expenses_paid': total_expenses_paid,
        'net_cash_position': net_cash_position,
        'total_receivables': total_receivables,
        'total_obligations': total_obligations,
        'net_overall_position': net_overall_position,

        # Income breakdown
        'total_fee_income': total_fee_income,
        'total_funding_income': total_funding_income,
        'total_other_income': total_other_income,
        'total_loan_repayments': total_loan_repayments,

        # Expense breakdown
        'total_expenses': total_expenses,
        'total_salary_payments': total_salary_payments,
        'total_supplier_payments': total_supplier_payments,
        'salary_advances_given': salary_advances_given,

        # Receivables breakdown
        'total_fee_receivables': total_fee_receivables,
        'outstanding_salary_advances': outstanding_salary_advances,
        'outstanding_purchase_advances': outstanding_purchase_advances,

        # Obligations
        'unpaid_salaries': unpaid_salaries,

        # Recent activity
        'recent_income': recent_income,
        'recent_expenses': recent_expenses,

        # Chart data
        'monthly_trends_data': json.dumps(monthly_trends),
        'income_breakdown_data': json.dumps(income_breakdown),
        'expense_breakdown_data': json.dumps(expense_breakdown),
    }

    return render(request, 'finance/finance_dashboard.html', context)


@login_required
def my_salary_profile_view(request):
    """
    Displays the salary profile for the currently logged-in staff member.
    Includes salary structure, bank details, and a filterable payslip history.
    """
    try:
        user_staff_profile = request.user.staff_profile
        staff = StaffModel.objects.get(staff_profile=user_staff_profile)
    except ObjectDoesNotExist:  # Catches both DoesNotExist exceptions
        messages.error(request, "You do not have a staff profile and cannot access this page.")
        return render(request, 'finance/staff_profile/no_profile.html')

    # Get the staff's salary structure
    try:
        salary_structure = staff.salary_structure
    except ObjectDoesNotExist:
        salary_structure = None

    try:
        bank_detail = staff.bank_details
    except ObjectDoesNotExist:  # This will correctly catch the error if no details exist
        bank_detail = None
    # =======================================

    # Handle filtering for the payslip history
    payslips = SalaryRecord.objects.filter(staff=staff)
    available_years = payslips.values_list('year', flat=True).distinct().order_by('-year')

    selected_year = request.GET.get('year', '')
    selected_month = request.GET.get('month', '')

    if selected_year:
        payslips = payslips.filter(year=selected_year)
    if selected_month:
        payslips = payslips.filter(month=selected_month)

    payslips = payslips.order_by('-year', '-month')

    context = {
        'staff': staff,
        'salary_structure': salary_structure,
        'bank_detail': bank_detail,
        'payslips': payslips,
        'available_years': available_years,
        'available_months': [(i, datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        'selected_year': selected_year,
        'selected_month': selected_month
    }
    return render(request, 'finance/staff_profile/salary_profile.html', context)

