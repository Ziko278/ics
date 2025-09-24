import json
from datetime import date, datetime, timedelta
from decimal import Decimal

import openpyxl
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core import serializers
from django.db import transaction
from django.db.models import Q, Sum, Avg, F
from django.db.models.functions import TruncMonth
from django.forms import modelformset_factory
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views import View
from django.views.generic import TemplateView, CreateView, UpdateView, ListView, DetailView, DeleteView, FormView
from openpyxl.styles import Font

from admin_site.models import SessionModel, TermModel, SchoolSettingModel, ClassesModel
from admin_site.views import FlashFormErrorsMixin
from human_resource.models import StaffModel
from inventory.models import PurchaseOrderModel, PurchaseAdvanceModel
from student.models import StudentModel
from .models import FinanceSettingModel, SupplierPaymentModel, PurchaseAdvancePaymentModel, FeeModel, FeeGroupModel, \
    FeeMasterModel, InvoiceGenerationJob, InvoiceModel, FeePaymentModel, ExpenseCategoryModel, ExpenseModel, \
    IncomeCategoryModel, IncomeModel, TermlyFeeAmountModel, StaffBankDetail, SalaryRecord, SalaryAdvance, \
    SalaryStructure
from .forms import FinanceSettingForm, SupplierPaymentForm, PurchaseAdvancePaymentForm, FeeForm, FeeGroupForm, \
    InvoiceGenerationForm, FeePaymentForm, ExpenseCategoryForm, ExpenseForm, IncomeCategoryForm, \
    IncomeForm, TermlyFeeAmountFormSet, FeeMasterCreateForm, BulkPaymentForm, StaffBankDetailForm, PaysheetRowForm, \
    SalaryAdvanceForm, SalaryStructureForm
from finance.tasks import generate_invoices_task

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
    permission_required = 'finance.add_financesettingmodel'
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
    permission_required = 'finance.view_supplierpaymentmodel'
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
    permission_required = 'finance.add_supplierpaymentmodel'
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
    permission_required = 'finance.change_supplierpaymentmodel'

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


# In finance/views.py

class AllSupplierPaymentsListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    SECONDARY VIEW: Provides a comprehensive, filterable log of all
    individual supplier payment transactions for auditing purposes.
    """
    model = SupplierPaymentModel
    permission_required = 'finance.view_supplierpaymentmodel'
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
    permission_required = 'finance.view_supplierpaymentmodel'
    template_name = 'finance/supplier_payment/receipt.html'
    context_object_name = 'payment'


class PurchaseAdvanceAccountsListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lists approved advances that need payments"""
    model = PurchaseAdvanceModel
    permission_required = 'finance.view_purchaseadvancepaymentmodel'
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
    permission_required = 'finance.add_purchaseadvancepaymentmodel'
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
    success_url = reverse_lazy('finance_fee_list')

    def form_valid(self, form):
        messages.success(self.request, "Fee Type created successfully.")
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class FeeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = FeeModel
    permission_required = 'finance.change_feemodel'
    form_class = FeeForm
    success_url = reverse_lazy('finance_fee_list')

    def form_valid(self, form):
        messages.success(self.request, "Fee Type updated successfully.")
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class FeeDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = FeeModel
    permission_required = 'finance.delete_feemodel'
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
    permission_required = 'finance.view_feegroupmodel'
    template_name = 'finance/fee_group/index.html'
    context_object_name = 'fee_groups'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = FeeGroupForm()
        return context


class FeeGroupCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = FeeGroupModel
    permission_required = 'finance.add_feegroupmodel'
    form_class = FeeGroupForm
    success_url = reverse_lazy('finance_fee_group_list')

    def form_valid(self, form):
        messages.success(self.request, "Fee Group created successfully.")
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class FeeGroupUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = FeeGroupModel
    permission_required = 'finance.change_feegroupmodel'
    form_class = FeeGroupForm
    success_url = reverse_lazy('finance_fee_group_list')

    def form_valid(self, form):
        messages.success(self.request, "Fee Group updated successfully.")
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class FeeGroupDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = FeeGroupModel
    permission_required = 'finance.delete_feegroupmodel'
    template_name = 'finance/fee_group/delete.html'
    success_url = reverse_lazy('finance_fee_group_list')

    def form_valid(self, form):
        messages.success(self.request, f"Fee Group '{self.object.name}' deleted successfully.")
        return super().form_valid(form)



# ===================================================================
# Fee Master (Structure) Views (Corrected)
# ===================================================================

class FeeMasterListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Displays a list of all created fee structures."""
    model = FeeMasterModel
    permission_required = 'finance.view_feemastermodel'
    template_name = 'finance/fee_master/index.html'
    context_object_name = 'fee_structures'
    paginate_by = 15


class FeeMasterCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Handles the creation of the main FeeMasterModel header (Step 1)."""
    model = FeeMasterModel
    permission_required = 'finance.add_feemastermodel'
    form_class = FeeMasterCreateForm
    template_name = 'finance/fee_master/create.html'

    def form_valid(self, form):
        messages.success(self.request, "Fee structure created. Now, set the price for each term.")
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        # Redirect to the detail page to set the termly prices
        return reverse('finance_fee_master_detail', kwargs={'pk': self.object.pk})


class FeeMasterDetailView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    The main view for managing a fee structure. It displays details and handles
    the formset for setting/updating termly prices.
    """
    permission_required = 'finance.change_feemastermodel'
    template_name = 'finance/fee_master/detail.html'

    def get(self, request, *args, **kwargs):
        fee_structure = get_object_or_404(FeeMasterModel, pk=self.kwargs.get('pk'))
        all_terms = TermModel.objects.all().order_by('order')

        initial_data = []
        for term in all_terms:
            amount_instance = fee_structure.termly_amounts.filter(term=term).first()
            initial_data.append({
                'term': term,
                'amount': amount_instance.amount if amount_instance else Decimal('0.00')
            })

        formset = TermlyFeeAmountFormSet(initial=initial_data)
        context = {'fee_structure': fee_structure, 'formset': formset}
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        fee_structure = get_object_or_404(FeeMasterModel, pk=self.kwargs.get('pk'))
        formset = TermlyFeeAmountFormSet(request.POST)

        if formset.is_valid():
            for form in formset:
                term = form.cleaned_data.get('term')
                amount = form.cleaned_data.get('amount')
                if term and amount is not None:
                    TermlyFeeAmountModel.objects.update_or_create(
                        fee_structure=fee_structure, term=term, defaults={'amount': amount}
                    )
            messages.success(request, "Termly fee amounts saved successfully.")
            return redirect('finance_fee_master_detail', pk=fee_structure.pk)

        context = {'fee_structure': fee_structure, 'formset': formset}
        return render(request, self.template_name, context)


class FeeMasterUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    """
    Handles updating the core details of a FeeMasterModel, such as the
    group, fee, and class assignments.
    """
    model = FeeMasterModel
    permission_required = 'finance.change_feemastermodel'
    form_class = FeeMasterCreateForm  # We can reuse the create form for updating
    template_name = 'finance/fee_master/update.html'

    def form_valid(self, form):
        messages.success(self.request, "Fee structure details updated successfully.")
        return super().form_valid(form)

    def get_success_url(self):
        # Redirect back to the detail page after updating
        return reverse('finance_fee_master_detail', kwargs={'pk': self.object.pk})


class FeeMasterDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Handles the deletion of a FeeMasterModel."""
    model = FeeMasterModel
    permission_required = 'finance.delete_feemastermodel'
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
    permission_required = 'finance.add_invoicemodel'

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
    permission_required = 'finance.view_invoicegenerationjob'


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
    permission_required = 'finance.view_invoicemodel'
    template_name = 'finance/invoice/index.html'
    context_object_name = 'invoices'
    paginate_by = 20
    # Add search and filter logic here for student name, invoice #, status, etc.


class InvoiceDetailView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = FeePaymentModel
    form_class = FeePaymentForm
    permission_required = 'finance.add_feepaymentmodel'
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
    """
    The main search page for finding a student to manage their fees.
    """
    permission_required = 'finance.add_feepaymentmodel'
    template_name = 'finance/payment/select_student.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['class_list'] = ClassesModel.objects.prefetch_related('section').all().order_by('name')
        # Pre-load all students for the client-side name search
        all_students = StudentModel.objects.select_related('student_class', 'class_section').filter(is_active=True)
        context['student_list_json'] = serializers.serialize("json", all_students)
        return context


def get_students_by_class_ajax(request):
    """AJAX endpoint to fetch students for a given class and section."""
    class_pk = request.GET.get('class_pk')
    section_pk = request.GET.get('section_pk')
    students = StudentModel.objects.filter(student_class_id=class_pk, class_section_id=section_pk, is_active=True)
    return render(request, 'finance/payment/partials/student_search_results.html', {'students': students})


def get_students_by_reg_no_ajax(request):
    """AJAX endpoint to fetch students by registration number."""
    reg_no = request.GET.get('reg_no', '').strip()
    students = StudentModel.objects.filter(registration_number__icontains=reg_no, is_active=True)
    return render(request, 'finance/payment/partials/student_search_results.html', {'students': students})


class StudentFinancialDashboardView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    Displays a financial dashboard for a student AND handles the creation
    of new fee payments against their CURRENT invoice.
    """
    model = FeePaymentModel
    form_class = FeePaymentForm
    permission_required = 'finance.add_feepaymentmodel'
    template_name = 'finance/payment/student_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student = get_object_or_404(StudentModel, pk=self.kwargs['pk'])
        context['student'] = student

        school_setting = SchoolSettingModel.objects.first()
        current_session = school_setting.session if school_setting else None
        current_term = school_setting.term if school_setting else None

        current_invoice = student.invoices.filter(session=current_session, term=current_term).first()
        context['current_invoice'] = current_invoice

        if 'form' not in context and current_invoice:
            context['form'] = FeePaymentForm(invoice=current_invoice)

        context['invoice_history'] = student.invoices.exclude(
            pk=current_invoice.pk if current_invoice else None
        ).order_by('-session__start_year', '-term__order')

        context['all_payments'] = FeePaymentModel.objects.filter(invoice__student=student).order_by('-date')

        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        student = get_object_or_404(StudentModel, pk=self.kwargs['pk'])
        school_setting = SchoolSettingModel.objects.first()
        if school_setting:
            current_invoice = student.invoices.filter(session=school_setting.session, term=school_setting.term).first()
            kwargs['invoice'] = current_invoice
        return kwargs

    def form_valid(self, form):
        invoice = self.get_form_kwargs().get('invoice')
        if not invoice:
            messages.error(self.request, "Cannot record payment: No current invoice found for this student.")
            return redirect(self.get_success_url())

        payment = form.save(commit=False)
        payment.invoice = invoice
        payment.status = FeePaymentModel.PaymentStatus.CONFIRMED
        payment.confirmed_by = self.request.user
        payment.save()

        # After saving the payment, update the invoice's status based on the new balance.
        if invoice.balance <= Decimal('0.01'):
            invoice.status = InvoiceModel.Status.PAID
        else:
            invoice.status = InvoiceModel.Status.PARTIALLY_PAID
        invoice.save()

        messages.success(self.request, f"Payment of ₦{payment.amount} recorded successfully.")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('finance_student_dashboard', kwargs={'pk': self.kwargs['pk']})


class BulkFeePaymentView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """
    Handles a single "bulk" payment that is intelligently allocated
    across multiple outstanding invoices for a student, oldest first.
    """
    form_class = BulkPaymentForm
    permission_required = 'finance.add_feepaymentmodel'
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
    permission_required = 'finance.change_feepaymentmodel'

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
    permission_required = 'finance.view_feepaymentmodel'
    template_name = 'finance/payment/receipt.html'
    context_object_name = 'payment'


# -------------------------
# Expense Category Views
# -------------------------
class ExpenseCategoryCreateView(
    LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView
):
    model = ExpenseCategoryModel
    permission_required = 'finance.add_expensecategory'   # keep existing codename (see note below)
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
    permission_required = 'finance.view_expensecategory'
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
    permission_required = 'finance.change_expensecategory'
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
    permission_required = 'finance.delete_expensecategory'
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
    permission_required = 'finance.view_expense'
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


class ExpenseCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    model = ExpenseModel
    permission_required = 'finance.add_expense'
    form_class = ExpenseForm
    template_name = 'finance/expense/create.html'
    success_message = 'Expense Successfully Created'

    def get_success_url(self):
        return reverse('expense_detail', kwargs={'pk': self.object.pk})


class ExpenseUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = ExpenseModel
    permission_required = 'finance.change_expense'
    form_class = ExpenseForm
    template_name = 'finance/expense/edit.html'
    success_message = 'Expense Successfully Updated'

    def get_success_url(self):
        return reverse('expense_detail', kwargs={'pk': self.object.pk})


class ExpenseDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ExpenseModel
    permission_required = 'finance.view_expense'
    template_name = 'finance/expense/detail.html'
    context_object_name = "expense"


# -------------------------
# Income Category Views
# -------------------------
class IncomeCategoryCreateView(
    LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView
):
    model = IncomeCategoryModel
    permission_required = 'finance.add_incomecategory'
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
    permission_required = 'finance.view_incomecategory'
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
    permission_required = 'finance.change_incomecategory'
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
    permission_required = 'finance.delete_incomecategory'
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
    permission_required = 'finance.view_income'
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
    permission_required = 'finance.add_income'
    form_class = IncomeForm
    template_name = 'finance/income/create.html'
    success_message = 'Income Successfully Created'

    def get_success_url(self):
        return reverse('income_detail', kwargs={'pk': self.object.pk})


class IncomeUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = IncomeModel
    permission_required = 'finance.change_income'
    form_class = IncomeForm
    template_name = 'finance/income/edit.html'
    success_message = 'Income Successfully Updated'

    def get_success_url(self):
        return reverse('income_detail', kwargs={'pk': self.object.pk})


class IncomeDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = IncomeModel
    permission_required = 'finance.view_income'
    template_name = 'finance/income/detail.html'
    context_object_name = "income"


# ===================================================================
# Staff Bank Detail Views (Modal Interface)
# ===================================================================
class StaffBankDetailListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = StaffBankDetail
    permission_required = 'finance.view_staffbankdetail'
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
    permission_required = 'finance.add_staffbankdetail'
    form_class = StaffBankDetailForm
    success_url = reverse_lazy('finance_staff_bank_detail_list')

    def form_valid(self, form):
        messages.success(self.request, "Bank Detail Created Successfully.")
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET': return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class StaffBankDetailUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    model = StaffBankDetail
    permission_required = 'finance.change_staffbankdetail'
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
    permission_required = 'finance.delete_staffbankdetail'
    template_name = 'finance/staff_bank/delete.html'
    context_object_name = "bank_detail"
    success_url = reverse_lazy('finance_staff_bank_detail_list')

    def form_valid(self, form):
        messages.success(self.request, "Bank Detail Deleted Successfully.")
        return super().form_valid(form)


# ===================================================================
# Salary Structure Views (Multi-page Interface)
# ===================================================================
class SalaryStructureListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = SalaryStructure
    permission_required = 'finance.view_salarystructure'
    template_name = 'finance/salary_structure/index.html'
    context_object_name = "salary_structure_list"

    def get_queryset(self):
        return SalaryStructure.objects.select_related('staff__staff_profile__user').order_by(
            'staff__staff_profile__user__first_name')


class SalaryStructureCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = SalaryStructure
    permission_required = 'finance.add_salarystructure'
    form_class = SalaryStructureForm
    template_name = 'finance/salary_structure/create.html'

    def get_success_url(self):
        messages.success(self.request, "Salary Structure Created Successfully.")
        return reverse('finance_salary_structure_detail', kwargs={'pk': self.object.pk})


class SalaryStructureUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = SalaryStructure
    permission_required = 'finance.change_salarystructure'
    form_class = SalaryStructureForm
    template_name = 'finance/salary_structure/update.html'

    def get_success_url(self):
        messages.success(self.request, "Salary Structure Updated Successfully.")
        return reverse('finance_salary_structure_detail', kwargs={'pk': self.object.pk})


class SalaryStructureDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SalaryStructure
    permission_required = 'finance.view_salarystructure'
    template_name = 'finance/salary_structure/detail.html'
    context_object_name = "salary_structure"


class SalaryStructureDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = SalaryStructure
    permission_required = 'finance.delete_salarystructure'
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
    permission_required = 'finance.view_salaryadvance'
    template_name = 'finance/salary_advance/index.html'
    context_object_name = 'advances'
    paginate_by = 15

    def get_queryset(self):
        # Add search and filter logic here
        return super().get_queryset().select_related('staff__staff_profile__user').order_by('-request_date')


class SalaryAdvanceCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = SalaryAdvance
    permission_required = 'finance.add_salaryadvance'
    form_class = SalaryAdvanceForm
    template_name = 'finance/salary_advance/create.html'

    def get_success_url(self):
        messages.success(self.request, "Salary advance request submitted successfully.")
        return reverse('finance_salary_advance_detail', kwargs={'pk': self.object.pk})


class SalaryAdvanceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SalaryAdvance
    permission_required = 'finance.view_salaryadvance'
    template_name = 'finance/salary_advance/detail.html'
    context_object_name = 'advance'


class SalaryAdvanceActionView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """A single view to handle all status changes for a salary advance."""
    permission_required = 'finance.change_salaryadvance'

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


@login_required
@permission_required('finance.add_salaryrecord')
def process_payroll_view(request):
    """
    An interactive view to manage the payroll for a specific month and year.
    Lists all staff with active salary structures and allows for inline editing.
    """
    # 1. Determine the period to process from GET parameters or use current month/year
    current_year = datetime.now().year
    current_month = datetime.now().month

    try:
        year = int(request.GET.get('year', current_year))
        month = int(request.GET.get('month', current_month))
    except (ValueError, TypeError):
        year = current_year
        month = current_month

    # 2. Get all staff who should be on the paysheet (i.e., have an active structure)
    staff_with_structures = StaffModel.objects.filter(salary_structure__is_active=True).select_related(
        'salary_structure')

    # 3. For each staff member, ensure a SalaryRecord exists for the period.
    # This automatically creates missing records, replacing the need for bulk generation.
    for staff in staff_with_structures:
        structure = staff.salary_structure
        record, created = SalaryRecord.objects.get_or_create(
            staff=staff,
            year=year,
            month=month,
            # 'defaults' are only used if a new record is being created
            defaults={
                'basic_salary': structure.basic_salary,
                'housing_allowance': structure.housing_allowance,
                'transport_allowance': structure.transport_allowance,
                'medical_allowance': structure.medical_allowance,
                'other_allowances': structure.other_allowances,
                'tax_amount': structure.tax_amount,
                'pension_amount': structure.pension_amount,
            }
        )

    # 4. Create a Formset. This is a collection of forms for our editable table.
    queryset = SalaryRecord.objects.filter(year=year, month=month, staff__in=staff_with_structures).select_related(
        'staff')
    PaysheetFormSet = modelformset_factory(SalaryRecord, form=PaysheetRowForm, extra=0)

    if request.method == 'POST':
        formset = PaysheetFormSet(request.POST, queryset=queryset)
        if formset.is_valid():
            # Save all the inline changes (bonus, deductions, notes, etc.)
            formset.save()

            # Handle the bulk "Mark as Paid" action
            paid_ids = request.POST.getlist('mark_as_paid')
            if paid_ids:
                paid_records = SalaryRecord.objects.filter(id__in=paid_ids)
                for record in paid_records:
                    if not record.is_paid:  # Only update if not already paid
                        record.is_paid = True
                        # If amount_paid is still 0, assume full payment on bulk mark
                        if record.amount_paid == 0:
                            record.amount_paid = record.net_salary
                        record.paid_date = date.today()
                        record.paid_by = request.user
                        record.save()

            messages.success(request, 'Paysheet saved successfully!')
            # Redirect back to the same page with the same filters
            return redirect(reverse('process_payroll') + f'?year={year}&month={month}')
        else:
            messages.error(request, 'Please correct the errors below. Invalid data was submitted.')

    else:
        # For a GET request, just display the formset with the current data
        formset = PaysheetFormSet(queryset=queryset)

    context = {
        'formset': formset,
        'year': year,
        'month': month,
        'years': range(2020, datetime.now().year + 2),
        'months': [(i, datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
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

    # Chart 1: Payroll Cost by Department (Bar Chart)
    dept_payroll = SalaryRecord.objects.filter(year=current_year, month=current_month) \
        .values('staff__department__name') \
        .annotate(total_cost=Sum(net_salary_expression)) \
        .order_by('-total_cost')

    dept_payroll_data = [
        {'name': item['staff__department__name'] or 'Unassigned', 'value': float(item['total_cost'])}
        for item in dept_payroll if item['total_cost']
    ]

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

    # Chart 3: Average Salary by Position (Bar Chart)
    position_payroll = SalaryRecord.objects.filter(year=current_year, month=current_month) \
        .values('staff__position__name') \
        .annotate(avg_salary=Avg(net_salary_expression)) \
        .order_by('-avg_salary')

    position_payroll_data = [
        {'name': item['staff__position__name'] or 'Unassigned', 'value': float(item['avg_salary'])}
        for item in position_payroll if item['avg_salary']
    ]

    context = {
        # KPI Cards
        'total_payroll_current': total_payroll_current,
        'staff_paid_count': staff_paid_count,
        'average_net_salary': average_net_salary,
        'percent_change': percent_change,

        # Chart Data (passed as JSON)
        'dept_payroll_data': json.dumps(dept_payroll_data),
        'salary_trend_data': json.dumps(salary_trend_data),
        'position_payroll_data': json.dumps(position_payroll_data),
    }

    return render(request, 'finance/salary_record/dashboard.html', context)




