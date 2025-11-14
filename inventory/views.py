import json
import logging
import tempfile
from datetime import date
from decimal import Decimal

from django.template.loader import render_to_string

from .tasks import generate_collections_task
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, F, ExpressionWrapper, Sum, DecimalField, Count, Case, When
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, FormView
from django.shortcuts import redirect, render, get_object_or_404

from admin_site.models import SessionModel, TermModel, SchoolSettingModel, ActivityLogModel, ClassesModel
from human_resource.models import StaffProfileModel, StaffModel, StaffWalletModel
from student.models import StudentModel, StudentWalletModel
from .models import CategoryModel, SupplierModel, ItemModel, PurchaseOrderModel, StockInModel, StockInItemModel, \
    PurchaseOrderItemModel, StockOutModel, StockTransferModel, PurchaseAdvanceModel, PurchaseAdvanceItemModel, \
    SaleItemModel, SaleModel, InventoryAssignmentModel, InventoryCollectionModel, CollectionGenerationJob, \
    DirectSaleModel
from .forms import CategoryForm, SupplierForm, ItemUpdateForm, ItemCreateForm, ManualStockInForm, StockInFromPOFormSet, \
    StockInSelectionForm, StockOutForm, PurchaseOrderCreateForm, PurchaseOrderItemForm, StockTransferCreateForm, \
    PurchaseAdvanceItemForm, PurchaseAdvanceCreateForm
from .services import perform_stock_out, perform_stock_transfer
from pytz import timezone as pytz_timezone
from django.http import HttpResponse

logger = logging.getLogger(__name__)


# ===================================================================
# Mixins
# ===================================================================

class FlashFormErrorsMixin:
    """
    A mixin for CreateView/UpdateView that handles form errors by
    adding them to Django's messages framework and redirecting back.
    """

    def form_invalid(self, form):
        # Add each specific form error as a separate message
        for field, errors in form.errors.items():
            label = form.fields.get(field).label if form.fields.get(field) else field.replace('_', ' ').title()
            for error in errors:
                # Add a distinct message for each error
                messages.error(self.request, f"{label}: {error}")

        # Redirect back to the success_url (which is the list page)
        return redirect(self.get_success_url())


# ===================================================================
# Inventory Category Views (Single Page Interface)
# ===================================================================

class CategoryListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    The main view for displaying the list of categories. It also provides
    the form instance needed for the 'Add New' modal.
    """
    model = CategoryModel
    permission_required = 'inventory.view_itemmodel'
    template_name = 'inventory/category/index.html'
    context_object_name = 'categories'

    # No pagination as requested for this light model.

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Provide an empty form for the 'Add New Category' modal.
        # This will be rendered on the 'index.html' template.
        if 'form' not in context:
            context['form'] = CategoryForm()
        return context


class CategoryCreateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, CreateView):
    """
    Handles the creation of a new category. This view only processes POST
    requests from the modal form on the category list page.
    """
    model = CategoryModel
    permission_required = 'inventory.add_itemmodel'
    form_class = CategoryForm
    template_name = 'inventory/category/index.html'  # Required for error redirect context

    def get_success_url(self):
        return reverse('inventory_category_list')

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.cleaned_data['name']}' created successfully.")
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        # This view should not be accessed via GET. It is a POST endpoint only.
        if request.method == 'GET':
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class CategoryUpdateView(LoginRequiredMixin, PermissionRequiredMixin, FlashFormErrorsMixin, UpdateView):
    """
    Handles updating an existing category. This view only processes POST
    requests from the modal form on the category list page.
    """
    model = CategoryModel
    permission_required = 'inventory.add_itemmodel'
    form_class = CategoryForm
    template_name = 'inventory/category/index.html'  # Required for error redirect context

    def get_success_url(self):
        return reverse('inventory_category_list')

    def form_valid(self, form):
        messages.success(self.request, f"Category '{form.cleaned_data['name']}' updated successfully.")
        return super().form_valid(form)

    def dispatch(self, request, *args, **kwargs):
        # This view should not be accessed via GET. It is a POST endpoint only.
        if request.method == 'GET':
            return redirect(self.success_url)
        return super().dispatch(request, *args, **kwargs)


class CategoryDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """
    Handles the actual deletion of a category object. The confirmation
    is handled by a modal on the list page.
    """
    model = CategoryModel
    permission_required = 'inventory.delete_itemmodel'
    template_name = 'inventory/category/delete.html'  # For the confirmation modal content
    success_url = reverse_lazy('inventory_category_list')
    context_object_name = 'category'

    def form_valid(self, form):
        # Add a success message before deleting the object.
        messages.success(self.request, f"Category '{self.object.name}' was deleted successfully.")
        return super().form_valid(form)


# ===================================================================
# Inventory Supplier Views (Multi-page CRUD)
# ===================================================================

class SupplierListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = SupplierModel
    permission_required = 'inventory.view_itemmodel'
    template_name = 'inventory/supplier/index.html'
    context_object_name = 'suppliers'


class SupplierDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = SupplierModel
    permission_required = 'inventory.view_itemmodel'
    template_name = 'inventory/supplier/detail.html'
    context_object_name = 'supplier'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        supplier = self.get_object()
        # Fetching related purchase orders and payments
        context['purchase_orders'] = supplier.purchaseordermodel_set.all().order_by('-order_date')
        context['payments'] = supplier.payments.all().order_by('-payment_date')
        return context


class SupplierCreateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = SupplierModel
    permission_required = 'inventory.add_itemmodel'
    form_class = SupplierForm
    template_name = 'inventory/supplier/create.html'
    success_message = "Supplier '%(name)s' was created successfully."
    success_url = reverse_lazy('inventory_supplier_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class SupplierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    model = SupplierModel
    permission_required = 'inventory.add_itemmodel'
    form_class = SupplierForm
    template_name = 'inventory/supplier/update.html'
    success_message = "Supplier '%(name)s' was updated successfully."
    success_url = reverse_lazy('inventory_supplier_list')


class SupplierDeleteView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    model = SupplierModel
    permission_required = 'inventory.delete_itemmodel'
    template_name = 'inventory/supplier/delete.html'
    success_message = "Supplier was deleted successfully."
    success_url = reverse_lazy('inventory_supplier_list')


class ItemListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = ItemModel
    permission_required = 'inventory.view_itemmodel'
    template_name = 'inventory/item/index.html'
    context_object_name = 'items'
    paginate_by = 20  # Set pagination to 20 items per page

    def get_queryset(self):
        """
        Override to implement search functionality.
        """
        queryset = super().get_queryset()
        query = self.request.GET.get('q')
        if query:
            # Search by item name or barcode
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(barcode__iexact=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        """
        Add the search query back to the context to display in the template.
        """
        context = super().get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('q', '')
        return context


class ItemDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = ItemModel
    permission_required = 'inventory.view_itemmodel'
    template_name = 'inventory/item/detail.html'
    context_object_name = 'item'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        item = self.get_object()

        # Add the empty StockOutForm to the context for the modal
        context['stock_out_form'] = StockOutForm()

        # Fetching related stock movements for the detail page tabs
        context['stock_ins'] = item.get_stock_ins()
        context['stock_outs'] = item.get_stock_outs()
        context['stock_transfers'] = item.get_stock_transfers()
        return context


class ItemCreateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = ItemModel
    permission_required = 'inventory.add_itemmodel'
    form_class = ItemCreateForm  # Use the form that allows setting initial quantity
    template_name = 'inventory/item/create.html'
    success_message = "Item '%(name)s' was created successfully."
    success_url = reverse_lazy('inventory_item_list')

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)


class ItemUpdateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    model = ItemModel
    permission_required = 'inventory.add_itemmodel'
    form_class = ItemUpdateForm  # Use the form that makes quantity read-only
    template_name = 'inventory/item/update.html'
    success_message = "Item '%(name)s' was updated successfully."
    context_object_name = 'item'

    def get_success_url(self):
        # Redirect back to the detail page of the item that was just updated
        return reverse_lazy('inventory_item_detail', kwargs={'pk': self.object.pk})


class ItemDeleteView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    model = ItemModel
    permission_required = 'inventory.delete_itemmodel'
    template_name = 'inventory/item/delete.html'
    success_message = "Item was deleted successfully."
    context_object_name = 'item'
    success_url = reverse_lazy('inventory_item_list')


# ===================================================================
# AJAX Views for Barcode Scanning
# ===================================================================
class ItemBarcodeScanAjaxView(LoginRequiredMixin, View):
    """
    An AJAX endpoint to find an item by its barcode and return its detail URL.
    """

    def get(self, request, *args, **kwargs):
        barcode = request.GET.get('barcode', None)
        if not barcode:
            return JsonResponse({'status': 'error', 'message': 'No barcode provided.'}, status=400)

        try:
            item = ItemModel.objects.get(barcode=barcode)
            return JsonResponse({
                'status': 'success',
                'url': item.get_absolute_url()
            })
        except ItemModel.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Item with this barcode not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ===================================================================
# Purchase Order Views (Models 5 & 6)
# ===================================================================
class PurchaseOrderListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = PurchaseOrderModel
    permission_required = 'inventory.view_inventorycollectionmodel'
    template_name = 'inventory/purchase_order/index.html'
    context_object_name = 'purchase_orders'
    paginate_by = 20

    def get_queryset(self):
        """
        Overrides the default queryset to include filtering by search query,
        session, and term.
        """
        queryset = super().get_queryset().select_related('supplier', 'session', 'term')

        # Get filter parameters from the request URL
        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        query = self.request.GET.get('q')

        # Apply session and term filters if they are provided
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)

        # Apply the general search query
        if query:
            queryset = queryset.filter(
                Q(order_number__icontains=query) | Q(supplier__name__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        """
        Adds the filter dropdown options and current selections to the context.
        """
        context = super().get_context_data(**kwargs)
        school_setting = SchoolSettingModel.objects.first()

        # Determine the currently selected session for the filter form
        selected_session_id = self.request.GET.get('session')
        if selected_session_id:
            context['selected_session'] = get_object_or_404(SessionModel, pk=selected_session_id)
        elif school_setting:
            context['selected_session'] = school_setting.session

        # Determine the currently selected term for the filter form
        selected_term_id = self.request.GET.get('term')
        if selected_term_id:
            context['selected_term'] = get_object_or_404(TermModel, pk=selected_term_id)
        elif school_setting:
            context['selected_term'] = school_setting.term

        # Provide all sessions and terms for the filter dropdowns
        context['sessions'] = SessionModel.objects.all().order_by('-start_year')
        context['terms'] = TermModel.objects.all().order_by('order')
        context['search_query'] = self.request.GET.get('q', '')

        return context


class PurchaseOrderCreateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = PurchaseOrderModel
    permission_required = 'inventory.add_inventorycollectionmodel'
    form_class = PurchaseOrderCreateForm
    template_name = 'inventory/purchase_order/create.html'
    success_message = "Purchase Order created successfully. You can now add items."

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        # Redirect to the detail page of the newly created PO to add items
        return reverse('inventory_po_detail', kwargs={'pk': self.object.pk})


class PurchaseOrderDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PurchaseOrderModel
    permission_required = 'inventory.view_inventorycollectionmodel'
    template_name = 'inventory/purchase_order/detail.html'
    context_object_name = 'po'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item_form'] = PurchaseOrderItemForm()
        return context


class PurchaseOrderItemCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Handles adding a new item to a PO via POST from the detail page."""
    model = PurchaseOrderItemModel
    form_class = PurchaseOrderItemForm
    permission_required = 'inventory.add_inventorycollectionmodel'

    def form_valid(self, form):
        purchase_order = get_object_or_404(PurchaseOrderModel, pk=self.kwargs['po_pk'])
        form.instance.purchase_order = purchase_order
        form.save()
        messages.success(self.request, f"Item '{form.instance.item_description}' added to PO.")
        return redirect('inventory_po_detail', pk=purchase_order.pk)

    def form_invalid(self, form):
        purchase_order_pk = self.kwargs['po_pk']
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"Error adding item: {error}")
        return redirect('inventory_po_detail', pk=purchase_order_pk)


class PurchaseOrderItemDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    """Handles deleting an item from a PO."""
    model = PurchaseOrderItemModel
    permission_required = 'inventory.add_inventorycollectionmodel'

    def get_success_url(self):
        purchase_order_pk = self.object.purchase_order.pk
        messages.success(self.request, "Item removed from PO successfully.")
        return reverse('inventory_po_detail', kwargs={'pk': purchase_order_pk})


# ===================================================================
# AJAX Views for Purchase Order Detail Page
# ===================================================================

class POItemSearchAjaxView(LoginRequiredMixin, View):
    """
    AJAX endpoint for searching inventory items by name OR barcode.
    This single view now handles both manual search and barcode scan lookups.
    Returns item data as JSON.
    """
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        if len(query) < 2:
            return JsonResponse({'items': []})

        items = ItemModel.objects.filter(
            Q(name__icontains=query) | Q(barcode__iexact=query)
        ).filter(is_active=True)[:10] # Limit results for performance

        results = []
        for item in items:
            results.append({
                'id': item.id,
                'name': item.name,
                'unit': item.get_unit_display(),
                'last_cost': item.last_cost_price
            })
        return JsonResponse({'items': results})


class PurchaseOrderStatusUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    Handles updating the status of a Purchase Order, including submitting
    and reverting back to draft.
    """
    permission_required = 'inventory.add_inventorycollectionmodel'

    def post(self, request, *args, **kwargs):
        po = get_object_or_404(PurchaseOrderModel, pk=self.kwargs.get('pk'))
        new_status = request.POST.get('status')

        # --- Logic for SUBMITTING a Draft ---
        if po.status == 'draft' and new_status == 'submitted':
            if not po.items.exists():
                messages.error(request, "Cannot submit a Purchase Order with no items.")
                return redirect(po.get_absolute_url())

            po.status = 'submitted'
            po.save()
            messages.success(request, f"Purchase Order {po.order_number} has been submitted.")

        # --- NEW: Logic for REVERTING a Submitted PO back to Draft ---
        elif po.status == 'submitted' and new_status == 'draft':
            # Crucial check: only allow revert if no stock has been received yet
            if po.has_stock_received:
                messages.error(request, "Cannot revert PO. Stock has already been received against it.")
                return redirect(po.get_absolute_url())

            po.status = 'draft'
            po.save()
            messages.warning(request,
                             f"Purchase Order {po.order_number} has been reverted to Draft and is now editable.")

        else:
            messages.error(request, "Invalid status update or action not allowed.")

        return redirect(po.get_absolute_url())


# ===================================================================
# Stock In Views (Model 8/39)
# ===================================================================

class StockInListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """Lists all historical Stock In batches."""
    model = StockInModel
    permission_required = 'inventory.view_stockinmodel'
    template_name = 'inventory/stock_in/index.html'
    context_object_name = 'stock_in_batches'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().select_related('supplier', 'purchase_order', 'created_by')
        query = self.request.GET.get('q')
        if query:
            queryset = queryset.filter(
                Q(receipt_number__icontains=query) |
                Q(supplier__name__icontains=query) |
                Q(purchase_order__order_number__icontains=query)
            ).distinct()
        return queryset


class StockInDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Shows the details and items of a single Stock In batch."""
    model = StockInModel
    permission_required = 'inventory.view_stockinmodel'
    template_name = 'inventory/stock_in/detail.html'
    context_object_name = 'batch'


class StockInFromPOCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    """
    Handles stocking in selected items directly from a Purchase Order.
    """
    form_class = StockInSelectionForm
    permission_required = 'inventory.add_stockinmodel'
    template_name = 'inventory/stock_in/from_po.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Get the purchase order early in the dispatch method.
        """
        self.purchase_order = get_object_or_404(PurchaseOrderModel, pk=kwargs.get('po_pk'))
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        """
        Pass the purchase order to the form.
        """
        kwargs = super().get_form_kwargs()
        kwargs['purchase_order'] = self.purchase_order
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['po'] = self.purchase_order

        # Add pending items to context for direct template access
        pending_items = self.purchase_order.items.filter(
            item__isnull=False
        ).exclude(is_stocked_in=True)

        context['pending_items'] = pending_items
        return context

    def get_initial(self):
        """
        Pre-select all pending items by default.
        """
        initial = super().get_initial()

        # Get pending items directly
        pending_items = self.purchase_order.items.filter(
            item__isnull=False
        ).exclude(is_stocked_in=True)

        # Set initial selection to all pending items
        initial['items_to_receive'] = list(pending_items.values_list('pk', flat=True))
        return initial

    def form_valid(self, form):
        selected_items = form.cleaned_data['items_to_receive']

        if not selected_items:
            messages.warning(self.request, "No items were selected to be stocked in.")
            return redirect(self.get_success_url())

        with transaction.atomic():
            stock_in_batch = StockInModel.objects.create(
                purchase_order=self.purchase_order,
                supplier=self.purchase_order.supplier,
                notes=f"Stock received against {self.purchase_order.order_number}",
                created_by=self.request.user
            )

            for po_item in selected_items:
                StockInItemModel.objects.create(
                    stock_in=stock_in_batch,
                    item=po_item.item,
                    purchase_order_item=po_item,
                    quantity_received=po_item.quantity,
                    unit_cost=po_item.unit_cost
                )
                po_item.is_stocked_in = True
                po_item.save()

        messages.success(self.request, f"Successfully stocked in {len(selected_items)} item(s).")
        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('inventory_po_detail', kwargs={'pk': self.kwargs.get('po_pk')})


class ManualStockInCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """
    Handles manual, multi-item stock-ins using a dynamic "cart" interface.
    """
    model = StockInModel
    form_class = ManualStockInForm
    permission_required = 'inventory.add_stockinmodel'
    template_name = 'inventory/stock_in/manual_create.html'

    def form_valid(self, form):
        # The main form for the batch details (supplier, date, etc.)
        stock_in_batch = form.save(commit=False)
        stock_in_batch.created_by = self.request.user

        # Get the "cart" data submitted from the hidden inputs
        item_ids = self.request.POST.getlist('item_id')
        quantities = self.request.POST.getlist('quantity')
        unit_costs = self.request.POST.getlist('unit_cost')

        if not item_ids:
            messages.error(self.request, "Cannot create a stock-in record with no items. Please add items to the list.")
            return self.form_invalid(form)

        with transaction.atomic():
            stock_in_batch.save()  # Save the parent batch first

            for i in range(len(item_ids)):
                try:
                    item = ItemModel.objects.get(pk=item_ids[i])
                    StockInItemModel.objects.create(
                        stock_in=stock_in_batch,
                        item=item,
                        quantity_received=Decimal(quantities[i]),
                        unit_cost=Decimal(unit_costs[i])
                    )
                except (ItemModel.DoesNotExist, ValueError, IndexError):
                    # In a real app, you might want more robust error handling
                    messages.error(self.request, "There was an error processing the item list. Please try again.")
                    return self.form_invalid(form)

        messages.success(self.request, "Stock-in record created successfully.")
        return redirect('inventory_stock_in_detail', pk=stock_in_batch.pk)


class StockOutCreateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    """
    Handles the creation of a StockOut record by correctly calling the
    FIFO service function.
    """
    permission_required = 'inventory.add_stockinmodel'

    def post(self, request, *args, **kwargs):
        item = get_object_or_404(ItemModel, pk=self.kwargs.get('item_pk'))
        form = StockOutForm(request.POST)

        if form.is_valid():
            try:
                # --- THIS IS THE CORRECTED LOGIC ---
                # It now calls the powerful service function to do all the work.
                perform_stock_out(
                    item=item,
                    location=form.cleaned_data['location'],
                    quantity_to_remove=form.cleaned_data['quantity_removed'],
                    reason=form.cleaned_data['reason'],
                    created_by_user=request.user,
                    specific_batch_id=form.cleaned_data.get('specific_batch_id'),
                    staff_recipient=form.cleaned_data.get('staff_recipient'),
                    notes=form.cleaned_data.get('notes')
                )
                messages.success(request, "Stock out recorded successfully.")

            except ValidationError as e:
                # Catch errors from the service (e.g., insufficient stock)
                messages.error(request, e.message)

            return redirect(item.get_absolute_url())

        # If the form itself is invalid (e.g., staff recipient not selected)
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field.title()}: {error}")

        return redirect(item.get_absolute_url())


class StockOutListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Lists all historical Stock Out records with full search and filtering capabilities.
    """
    model = StockOutModel
    permission_required = 'inventory.view_stockinmodel'
    template_name = 'inventory/stock_out/index.html'
    context_object_name = 'stock_out_records'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'item', 'staff_recipient__staff_profile__user', 'created_by__staff_profile__user', 'session', 'term'
        )

        query = self.request.GET.get('q')
        reason = self.request.GET.get('reason')
        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        if query:
            # --- THIS IS THE CORRECTED FILTER ---
            # It now searches by item name OR barcode
            queryset = queryset.filter(
                Q(item__name__icontains=query) |
                Q(item__barcode__iexact=query)
            )
        if reason:
            queryset = queryset.filter(reason=reason)
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        if start_date:
            queryset = queryset.filter(date_removed__gte=start_date)
        if end_date:
            queryset = queryset.filter(date_removed__lte=end_date)

        return queryset.order_by('-date_removed', '-created_at')

    def get_context_data(self, **kwargs):
        """
        Adds all filter options and the user's current selections
        to the template context.
        """
        context = super().get_context_data(**kwargs)

        # Pass all filter values back to the template to re-populate the form
        context['search_query'] = self.request.GET.get('q', '')
        context['selected_reason'] = self.request.GET.get('reason', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')

        # Pass the master list of choices for the filter dropdowns
        context['reason_choices'] = StockOutModel.Reason.choices
        context['sessions'] = SessionModel.objects.all().order_by('-start_year')
        context['terms'] = TermModel.objects.all().order_by('order')

        school_setting = SchoolSettingModel.objects.first()

        # Pass the full object for the selected session and term
        selected_session_id = self.request.GET.get('session')
        if selected_session_id:
            context['selected_session'] = get_object_or_404(SessionModel, pk=selected_session_id)

        selected_term_id = self.request.GET.get('term')
        if selected_term_id:
            context['selected_term'] = get_object_or_404(TermModel, pk=selected_term_id)

        return context


# ===================================================================
# Stock Transfer Views (Model 10/39)
# ===================================================================

class StockTransferListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Lists all historical Stock Transfer batches with full search and filtering.
    """
    model = StockTransferModel
    permission_required = 'inventory.view_stockinmodel'
    template_name = 'inventory/stock_transfer/index.html'
    context_object_name = 'transfer_batches'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().select_related('created_by__staff_profile__user', 'session', 'term')

        # Get all filter parameters from the request
        query = self.request.GET.get('q')
        direction = self.request.GET.get('direction')
        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date')

        # Apply all filters
        if query:
            queryset = queryset.filter(receipt_number__icontains=query)
        if direction:
            queryset = queryset.filter(direction=direction)
        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)
        if start_date:
            queryset = queryset.filter(transfer_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(transfer_date__lte=end_date)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pass filter values back to the template to re-populate the form
        context['search_query'] = self.request.GET.get('q', '')
        context['selected_direction'] = self.request.GET.get('direction', '')
        context['start_date'] = self.request.GET.get('start_date', '')
        context['end_date'] = self.request.GET.get('end_date', '')

        # Pass filter options and current selections to the template
        context['direction_choices'] = StockTransferModel.Direction.choices
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


class StockTransferDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    """Shows the details and items of a single Stock Transfer batch."""
    model = StockTransferModel
    permission_required = 'inventory.view_stockinmodel'
    template_name = 'inventory/stock_transfer/detail.html'
    context_object_name = 'batch'


class StockTransferCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    """Handles the creation of a multi-item stock transfer via a dynamic "cart"."""
    model = StockTransferModel
    form_class = StockTransferCreateForm
    permission_required = 'inventory.add_stockinmodel'
    template_name = 'inventory/stock_transfer/create.html'

    def form_valid(self, form):
        item_ids = self.request.POST.getlist('item_id')
        quantities = self.request.POST.getlist('quantity')

        if not item_ids:
            messages.error(self.request, "Cannot create a transfer with no items. Please add items to the list.")
            return self.form_invalid(form)

        items_data = []
        for i in range(len(item_ids)):
            try:
                item = ItemModel.objects.get(pk=item_ids[i])
                items_data.append({'item': item, 'quantity': Decimal(quantities[i])})
            except (ItemModel.DoesNotExist, ValueError):
                messages.error(self.request, "An error occurred with the item list. Please try again.")
                return self.form_invalid(form)

        try:
            # The service function now correctly finds the staff member from the user
            perform_stock_transfer(
                direction=form.cleaned_data['direction'],
                items_data=items_data,
                created_by_user=self.request.user,
                notes=form.cleaned_data.get('notes')
            )
            messages.success(self.request, "Stock transfer recorded successfully.")
            # We don't have a detail view for the transfer batch itself, so we redirect to the list.
            return redirect('inventory_stock_transfer_list')
        except ValidationError as e:
            messages.error(self.request, e.message)
            return self.form_invalid(form)


class ItemSearchForTransferAjaxView(LoginRequiredMixin, View):
    """
    AJAX endpoint for the transfer page that returns item data including
    both shop and store stock levels for front-end validation.
    """

    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        if len(query) < 2:
            return JsonResponse({'items': []})

        items = ItemModel.objects.filter(
            Q(name__icontains=query) | Q(barcode__iexact=query)
        ).filter(is_active=True)[:10]

        results = [{
            'id': item.id,
            'name': item.name,
            'unit': item.get_unit_display(),
            'shop_qty': item.shop_quantity,
            'store_qty': item.store_quantity
        } for item in items]

        return JsonResponse({'items': results})


class PurchaseAdvanceListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = PurchaseAdvanceModel
    permission_required = 'inventory.view_inventorycollectionmodel'
    template_name = 'inventory/purchase_advance/index.html'
    context_object_name = 'purchase_advances'
    paginate_by = 20

    def get_queryset(self):
        queryset = super().get_queryset().select_related('staff', 'session', 'term')

        session_id = self.request.GET.get('session')
        term_id = self.request.GET.get('term')
        query = self.request.GET.get('q')

        if session_id:
            queryset = queryset.filter(session_id=session_id)
        if term_id:
            queryset = queryset.filter(term_id=term_id)

        if query:
            queryset = queryset.filter(
                Q(advance_number__icontains=query) | Q(staff__first_name__icontains=query) |
                Q(staff__last_name__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school_setting = SchoolSettingModel.objects.first()

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

        context['sessions'] = SessionModel.objects.all().order_by('-start_year')
        context['terms'] = TermModel.objects.all().order_by('order')
        context['search_query'] = self.request.GET.get('q', '')

        return context


class PurchaseAdvanceCreateView(LoginRequiredMixin, PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    model = PurchaseAdvanceModel
    permission_required = 'inventory.add_inventorycollectionmodel'
    form_class = PurchaseAdvanceCreateForm
    template_name = 'inventory/purchase_advance/create.html'
    success_message = "Purchase Advance created successfully. You can now add items."

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('inventory_advance_detail', kwargs={'pk': self.object.pk})


class PurchaseAdvanceDetailView(LoginRequiredMixin, PermissionRequiredMixin, DetailView):
    model = PurchaseAdvanceModel
    permission_required = 'inventory.view_inventorycollectionmodel'
    template_name = 'inventory/purchase_advance/detail.html'
    context_object_name = 'advance'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['item_form'] = PurchaseAdvanceItemForm()
        return context


class PurchaseAdvanceItemCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = PurchaseAdvanceItemModel
    form_class = PurchaseAdvanceItemForm
    permission_required = 'inventory.add_inventorycollectionmodel'

    def form_valid(self, form):
        advance = get_object_or_404(PurchaseAdvanceModel, pk=self.kwargs['advance_pk'])
        form.instance.advance = advance
        form.save()
        # Update advance total
        advance.save()
        messages.success(self.request, f"Item '{form.instance.item_description}' added to advance request.")
        return redirect('inventory_advance_detail', pk=advance.pk)

    def form_invalid(self, form):
        advance_pk = self.kwargs['advance_pk']
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f"Error adding item: {error}")
        return redirect('inventory_advance_detail', pk=advance_pk)


class PurchaseAdvanceItemDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = PurchaseAdvanceItemModel
    permission_required = 'inventory.add_inventorycollectionmodel'

    def get_success_url(self):
        advance_pk = self.object.advance.pk
        messages.success(self.request, "Item removed from advance request successfully.")
        return reverse('inventory_advance_detail', kwargs={'pk': advance_pk})


class PurchaseAdvanceStatusUpdateView(LoginRequiredMixin, PermissionRequiredMixin, View):
    permission_required = 'inventory.add_inventorycollectionmodel'

    def post(self, request, *args, **kwargs):
        advance = get_object_or_404(PurchaseAdvanceModel, pk=self.kwargs.get('pk'))
        new_status = request.POST.get('status')

        if advance.status == 'pending' and new_status == 'approved':
            if not advance.items.exists():
                messages.error(request, "Cannot approve advance request with no items.")
                return redirect(advance.get_absolute_url())

            advance.status = 'approved'
            advance.approved_by = request.user
            advance.approved_date = timezone.now().date()
            advance.approved_amount = advance.total_amount
            advance.save()
            messages.success(request, f"Purchase Advance {advance.advance_number} has been approved.")

        elif advance.status == 'approved' and new_status == 'pending':
            # Check if any payments have been made
            if advance.disbursed_amount > 0:
                messages.error(request, "Cannot revert advance. Payments have already been made.")
                return redirect(advance.get_absolute_url())

            advance.status = 'pending'
            advance.approved_by = None
            advance.approved_date = None
            advance.approved_amount = Decimal('0.00')
            advance.save()
            messages.warning(request, f"Purchase Advance {advance.advance_number} has been reverted to pending.")

        else:
            messages.error(request, "Invalid status update or action not allowed.")

        return redirect(advance.get_absolute_url())


class AdvanceItemSearchAjaxView(LoginRequiredMixin, View):
    """AJAX endpoint for searching inventory items by name OR barcode."""
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '')
        if len(query) < 2:
            return JsonResponse({'items': []})

        items = ItemModel.objects.filter(
            Q(name__icontains=query) | Q(barcode__iexact=query)
        ).filter(is_active=True)[:10]

        results = []
        for item in items:
            recent_stock = item.stock_ins.order_by('-stock_in__date_received').first()
            last_cost = float(recent_stock.unit_cost) if recent_stock else 0

            results.append({
                'id': item.id,
                'name': item.name,
                'unit': item.get_unit_display(),
                'last_cost': last_cost
            })
        return JsonResponse({'items': results})


# Add this NEW view function to your views.py
def api_person_search(request):
    """
    AJAX endpoint for searching both students and staff.
    Returns a combined list with type indicators.
    """
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse([], safe=False)

    results = []

    # Search students
    students = StudentModel.objects.filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(registration_number__icontains=query)
    )[:10]

    for student in students:
        wallet, _ = StudentWalletModel.objects.get_or_create(student=student)
        results.append({
            'type': 'student',
            'id': student.id,
            'name': f"{student.first_name} {student.last_name}",
            'identifier': student.registration_number,  # reg number for students
            'display_class': str(student.current_class) if hasattr(student, 'current_class') else '',
            'wallet_balance': float(wallet.balance),
            'image_url': student.image.url if student.image else None
        })

    # Search staff
    staff_members = StaffModel.objects.filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(staff_id__icontains=query),
        status='active'
    )[:10]

    for staff in staff_members:
        wallet, _ = StaffWalletModel.objects.get_or_create(staff=staff)
        results.append({
            'type': 'staff',
            'id': staff.id,
            'name': f"{staff.first_name} {staff.last_name}",
            'identifier': staff.staff_id,  # staff_id for staff
            'display_class': '',  # Staff don't have classes
            'wallet_balance': float(wallet.balance),
            'image_url': staff.image.url if staff.image else None
        })

    return JsonResponse(results, safe=False)


# REPLACE your existing place_order_view with this updated version
@login_required
@permission_required("inventory.add_salemodel", raise_exception=True)
@transaction.atomic
def place_order_view(request):
    # --- GET Request: Show the order form and suggestions ---
    if request.method == 'GET':
        # Query for the top 10 best-selling items by quantity
        top_items = SaleItemModel.objects.values(
            'item__id',
            'item__name',
            'item__current_selling_price',
            'item__shop_quantity'
        ).annotate(total_sold=Sum('quantity')) \
                        .order_by('-total_sold')[:10]

        context = {
            'settings': SchoolSettingModel.objects.last(),
            'items': ItemModel.objects.filter(is_active=True),
            'top_items': top_items,
        }
        return render(request, 'inventory/sales/place_order.html', context)

    # --- POST Request: Process the sale ---
    student_id = request.POST.get('student_id')
    staff_id = request.POST.get('staff_id')
    payment_method = request.POST.get('payment_method')

    student = None
    staff = None

    # Get the customer (either student or staff)
    if student_id:
        student = get_object_or_404(StudentModel, pk=student_id)
    elif staff_id:
        staff = get_object_or_404(StaffModel, pk=staff_id)

    # Validate payment method selection
    if payment_method == 'student_wallet' and not student:
        messages.error(request, 'A student must be selected to use the Student Wallet payment method.')
        return redirect(reverse('place_order'))

    if payment_method == 'staff_wallet' and not staff:
        messages.error(request, 'A staff member must be selected to use the Staff Wallet payment method.')
        return redirect(reverse('place_order'))

    # Gather line-items from the form
    idx = 0
    items = []
    subtotal = Decimal('0.00')
    while True:
        item_id = request.POST.get(f'items[{idx}][item_id]')
        qty = request.POST.get(f'items[{idx}][quantity]')
        if not item_id or not qty:
            break

        item = get_object_or_404(ItemModel, pk=item_id)
        try:
            quantity = Decimal(str(qty))
        except Exception:
            messages.error(request, f'Invalid quantity for item {item.name}')
            return redirect(reverse('place_order'))

        unit_price = item.current_selling_price
        line_total = unit_price * quantity
        items.append((item, quantity, unit_price))
        subtotal += line_total
        idx += 1

    if not items:
        messages.error(request, 'No items were added to the order.')
        return redirect(reverse('place_order'))

    discount = Decimal(str(request.POST.get('discount', '0.00') or '0.00'))
    total_amount = subtotal - discount

    # Wallet validation based on payment method
    if payment_method == 'student_wallet':
        wallet, _ = StudentWalletModel.objects.get_or_create(student=student)
        available = Decimal(str(wallet.balance or '0.00'))

        if total_amount > available:
            messages.error(request,
                           f'Insufficient funds for {student}. Available: ₦{available}, Needed: ₦{total_amount}')
            return redirect(reverse('place_order'))

    elif payment_method == 'staff_wallet':
        wallet, _ = StaffWalletModel.objects.get_or_create(staff=staff)
        available = Decimal(str(wallet.balance or '0.00'))

        if total_amount > available:
            messages.error(request,
                           f'Insufficient funds for {staff}. Available: ₦{available}, Needed: ₦{total_amount}')
            return redirect(reverse('place_order'))

    # Create Sale header
    sale = SaleModel.objects.create(
        customer=student,
        staff_customer=staff,
        discount=discount,
        payment_method=payment_method
    )

    try:
        created_by = StaffProfileModel.objects.get(user=request.user).staff
        sale.created_by = created_by
        sale.save()
    except Exception:
        pass

    # --- FIFO Stock Consumption and Sale Item Creation ---
    for item, qty, unit_price in items:
        item = ItemModel.objects.select_for_update().get(pk=item.pk)
        remaining = qty
        total_cost = Decimal('0.00')

        batches = StockInItemModel.objects.select_for_update().filter(
            item=item,
            quantity_remaining__gt=Decimal('0.00')
        ).order_by('stock_in__date_received', 'stock_in__created_at')

        for batch in batches:
            if remaining <= Decimal('0.00'):
                break
            available_in_batch = batch.quantity_remaining or Decimal('0.00')
            take = min(remaining, available_in_batch)
            if take <= Decimal('0.00'):
                continue

            batch.quantity_remaining = (available_in_batch - take).quantize(Decimal('0.01'))
            batch.save(update_fields=['quantity_remaining'])
            unit_cost = batch.unit_cost or Decimal('0.00')
            total_cost += (take * unit_cost)
            remaining -= take

        if remaining > Decimal('0.00'):
            raise ValueError(f"Not enough stock to fulfill {qty} of {item.name}. Only {qty - remaining} available.")

        avg_cost = (total_cost / qty).quantize(Decimal('0.01')) if qty > 0 else Decimal('0.00')

        SaleItemModel.objects.create(
            sale=sale,
            item=item,
            quantity=qty,
            unit_price=unit_price,
            unit_cost=avg_cost
        )

        to_take = qty
        shop_avail = item.shop_quantity or Decimal('0.00')
        if shop_avail >= to_take:
            item.shop_quantity = (shop_avail - to_take)
            to_take = Decimal('0.00')
        else:
            item.shop_quantity = Decimal('0.00')
            to_take = (to_take - shop_avail)

        if to_take > Decimal('0.00'):
            store_avail = item.store_quantity or Decimal('0.00')
            item.store_quantity = (store_avail - to_take)

        item.save(update_fields=['shop_quantity', 'store_quantity'])

    # Wallet deduction
    if payment_method == 'student_wallet':
        wallet.refresh_from_db()
        wallet_balance = Decimal(str(wallet.balance or 0))
        wallet.balance = float((wallet_balance - total_amount).quantize(Decimal('0.01')))
        wallet.save(update_fields=['balance'])

    elif payment_method == 'staff_wallet':
        wallet.refresh_from_db()
        wallet_balance = Decimal(str(wallet.balance or 0))
        wallet.balance = float((wallet_balance - total_amount).quantize(Decimal('0.01')))
        wallet.save(update_fields=['balance'])

    messages.success(request, f'Sale #{sale.id} recorded successfully.')
    return redirect(reverse('place_order'))


@login_required
@permission_required("inventory.view_salemodel", raise_exception=True)
def view_orders(request):
    # Get search parameters
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()
    staff_filter = request.GET.get('staff', '').strip()

    # Base queryset: include related customer + created_by for fewer queries
    orders_qs = SaleModel.objects.select_related('customer', 'created_by').all()

    # --- Determine related accessor name for sale items dynamically ---
    # This makes the code robust regardless of related_name used on the FK from SaleItemModel -> SaleModel
    related_accessor = None
    for rel in SaleModel._meta.related_objects:
        # related_model is the model on the other side (SaleItemModel)
        try:
            rel_model = rel.related_model
        except AttributeError:
            continue
        # Heuristic: look for a model that has 'unit_price' and 'quantity' fields
        field_names = {f.name for f in rel_model._meta.get_fields()}
        if {'quantity', 'unit_price'}.issubset(field_names):
            related_accessor = rel.get_accessor_name()
            break

    # Fallback to 'items' if autodetect failed (common pattern)
    if not related_accessor:
        related_accessor = 'items'

    qty_field = f"{related_accessor}__quantity"
    price_field = f"{related_accessor}__unit_price"

    # Annotate totals: line_total is sum(quantity * unit_price) for each sale, total_quantity is sum(quantity)
    # Use ExpressionWrapper to multiply fields
    try:
        line_expr = ExpressionWrapper(F(qty_field) * F(price_field), output_field=DecimalField())
        orders_qs = orders_qs.annotate(
            line_total=Sum(line_expr),
            total_quantity=Sum(qty_field)
        )
    except Exception:
        # If annotation fails (unexpected related name), still continue without totals
        orders_qs = orders_qs.annotate(total_quantity=Sum(qty_field))

    # Apply filters: search (transaction id or customer fields)
    if search_query:
        orders_qs = orders_qs.filter(
            Q(transaction_id__icontains=search_query) |
            Q(customer__first_name__icontains=search_query) |
            Q(customer__last_name__icontains=search_query) |
            Q(customer__registration_number__icontains=search_query)
        )

    if status_filter:
        orders_qs = orders_qs.filter(status=status_filter)

    if staff_filter:
        orders_qs = orders_qs.filter(created_by_id=staff_filter)

    # Date filtering: prefer sale_date if present, else use created_at
    date_field = 'sale_date' if 'sale_date' in {f.name for f in SaleModel._meta.get_fields()} else 'created_at'

    if date_from:
        orders_qs = orders_qs.filter(**{f"{date_field}__date__gte": date_from})
    if date_to:
        orders_qs = orders_qs.filter(**{f"{date_field}__date__lte": date_to})

    # Pagination
    paginator = Paginator(orders_qs.order_by('-id'), 20)  # show latest first
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'status_choices': SaleModel.Status.choices,
        'staff_filter': staff_filter,
        'staff_list': StaffModel.objects.filter(
            status='active',
            salemodel__isnull=False  # Has at least one sale
        ).distinct().order_by('first_name', 'last_name'),
    }

    return render(request, 'inventory/sales/index.html', context)


@login_required
@permission_required("inventory.view_salemodel", raise_exception=True)
def staff_sales_report(request):
    """Display staff sales summary with totals by payment method."""

    # Get date parameters, default to today
    today = date.today()
    date_from = request.GET.get('date_from', '').strip() or str(today)
    date_to = request.GET.get('date_to', '').strip() or str(today)
    staff_filter = request.GET.get('staff', '').strip()
    download_pdf = request.GET.get('download', '') == 'pdf'

    # Validate date range
    try:
        from_date = date.fromisoformat(date_from)
        to_date = date.fromisoformat(date_to)

        if from_date > to_date:
            from_date, to_date = to_date, from_date
            date_from, date_to = date_to, date_from

    except ValueError:
        from_date = to_date = today
        date_from = date_to = str(today)

    # Generate title based on date range
    if date_from == date_to:
        report_title = from_date.strftime("%B %d, %Y")
    else:
        report_title = f"{from_date.strftime('%B %d, %Y')} - {to_date.strftime('%B %d, %Y')}"

    # Base queryset - sales in date range
    sales_qs = SaleModel.objects.filter(
        sale_date__date__gte=from_date,
        sale_date__date__lte=to_date,
        status='completed'
    )

    # Filter by staff if provided
    if staff_filter:
        sales_qs = sales_qs.filter(created_by_id=staff_filter)

    # Group by staff and aggregate
    staff_summary = sales_qs.values(
        'created_by__id',
        'created_by__first_name',
        'created_by__last_name',
        'created_by__staff_id'
    ).annotate(
        total_sales=Count('id'),
        cash_total=Sum(
            Case(
                When(payment_method='cash', then=F('items__quantity') * F('items__unit_price')),
                default=0,
                output_field=DecimalField()
            )
        ) - Sum(
            Case(
                When(payment_method='cash', then=F('discount')),
                default=0,
                output_field=DecimalField()
            )
        ),
        student_wallet_total=Sum(
            Case(
                When(payment_method='student_wallet', then=F('items__quantity') * F('items__unit_price')),
                default=0,
                output_field=DecimalField()
            )
        ) - Sum(
            Case(
                When(payment_method='student_wallet', then=F('discount')),
                default=0,
                output_field=DecimalField()
            )
        ),
        staff_wallet_total=Sum(
            Case(
                When(payment_method='staff_wallet', then=F('items__quantity') * F('items__unit_price')),
                default=0,
                output_field=DecimalField()
            )
        ) - Sum(
            Case(
                When(payment_method='staff_wallet', then=F('discount')),
                default=0,
                output_field=DecimalField()
            )
        ),
        pos_total=Sum(
            Case(
                When(payment_method='pos', then=F('items__quantity') * F('items__unit_price')),
                default=0,
                output_field=DecimalField()
            )
        ) - Sum(
            Case(
                When(payment_method='pos', then=F('discount')),
                default=0,
                output_field=DecimalField()
            )
        ),
    ).order_by('-total_sales')

    # Calculate grand totals
    grand_totals = {
        'total_sales': 0,
        'total_amount': Decimal('0.00'),
        'cash_total': Decimal('0.00'),
        'student_wallet_total': Decimal('0.00'),
        'staff_wallet_total': Decimal('0.00'),
        'pos_total': Decimal('0.00'),
    }

    for staff in staff_summary:
        # Convert None to Decimal('0.00')
        staff['cash_total'] = staff['cash_total'] or Decimal('0.00')
        staff['student_wallet_total'] = staff['student_wallet_total'] or Decimal('0.00')
        staff['staff_wallet_total'] = staff['staff_wallet_total'] or Decimal('0.00')
        staff['pos_total'] = staff['pos_total'] or Decimal('0.00')

        staff['total_amount'] = (
                staff['cash_total'] +
                staff['student_wallet_total'] +
                staff['staff_wallet_total'] +
                staff['pos_total']
        )

        grand_totals['total_sales'] += staff['total_sales']
        grand_totals['total_amount'] += staff['total_amount']
        grand_totals['cash_total'] += staff['cash_total']
        grand_totals['student_wallet_total'] += staff['student_wallet_total']
        grand_totals['staff_wallet_total'] += staff['staff_wallet_total']
        grand_totals['pos_total'] += staff['pos_total']

    context = {
        'staff_summary': staff_summary,
        'grand_totals': grand_totals,
        'report_title': report_title,
        'date_from': date_from,
        'date_to': date_to,
        'staff_filter': staff_filter,
        'staff_list': StaffModel.objects.filter(
            status='active',
            salemodel__isnull=False  # Has at least one sale
        ).distinct().order_by('first_name', 'last_name'),
    }

    # Generate PDF if requested (lazy import)
    # Generate PDF if requested
    if download_pdf:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from io import BytesIO

            # Create PDF buffer
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), topMargin=0.5 * inch, bottomMargin=0.5 * inch)
            elements = []
            styles = getSampleStyleSheet()

            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=10,
                alignment=1  # Center
            )
            elements.append(Paragraph("Staff Sales Report", title_style))

            subtitle_style = ParagraphStyle(
                'CustomSubtitle',
                parent=styles['Normal'],
                fontSize=14,
                textColor=colors.HexColor('#3498db'),
                spaceAfter=20,
                alignment=1
            )
            elements.append(Paragraph(report_title, subtitle_style))
            elements.append(Spacer(1, 0.2 * inch))

            # Prepare table data
            table_data = [
                ['Staff Name', 'Staff ID', 'Sales', 'Total (₦)', 'Cash (₦)',
                 'Student Wallet (₦)', 'Staff Wallet (₦)', 'POS (₦)']
            ]

            for staff in staff_summary:
                table_data.append([
                    f"{staff['created_by__first_name']} {staff['created_by__last_name']}",
                    staff['created_by__staff_id'],
                    str(staff['total_sales']),
                    f"{staff['total_amount']:,.2f}",
                    f"{staff['cash_total']:,.2f}",
                    f"{staff['student_wallet_total']:,.2f}",
                    f"{staff['staff_wallet_total']:,.2f}",
                    f"{staff['pos_total']:,.2f}",
                ])

            # Grand total row
            if staff_summary:
                table_data.append([
                    'GRAND TOTAL',
                    '',
                    str(grand_totals['total_sales']),
                    f"{grand_totals['total_amount']:,.2f}",
                    f"{grand_totals['cash_total']:,.2f}",
                    f"{grand_totals['student_wallet_total']:,.2f}",
                    f"{grand_totals['staff_wallet_total']:,.2f}",
                    f"{grand_totals['pos_total']:,.2f}",
                ])

            # Create table
            table = Table(table_data, repeatRows=1)
            table.setStyle(TableStyle([
                # Header
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),

                # Data rows
                ('BACKGROUND', (0, 1), (-1, -2), colors.beige),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),  # Right align numbers
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -2), 1, colors.grey),
                ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#f8f9fa')]),

                # Grand total row (last row)
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#ecf0f1')),
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.black),
                ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, -1), (-1, -1), 11),
                ('LINEABOVE', (0, -1), (-1, -1), 2, colors.HexColor('#2c3e50')),
                ('TOPPADDING', (0, -1), (-1, -1), 12),
            ]))

            elements.append(table)

            # Build PDF
            doc.build(elements)

            # Return response
            pdf_content = buffer.getvalue()
            buffer.close()

            response = HttpResponse(pdf_content, content_type='application/pdf')
            filename = f"staff_sales_report_{date_from}_{date_to}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        except ImportError:
            from django.contrib import messages
            messages.error(request, 'PDF generation is not available. Please contact administrator.')
            return redirect('staff_sales_report')

    return render(request, 'inventory/sales/staff_report.html', context)


@login_required
@permission_required("inventory.view_salemodel", raise_exception=True)
def order_detail(request, pk):
    sale = get_object_or_404(SaleModel, pk=pk)
    items = sale.items.select_related('item')  # Changed from saleitemmodel_set to items

    # Calculate totals
    total_profit = sum(item.profit for item in items)

    context = {
        'sale': sale,
        'items': items,
        'total_profit': total_profit,
    }

    return render(request, 'inventory/sales/detail.html', context)


# API endpoints for AJAX calls
@login_required
def api_student_search(request):
    """AJAX endpoint for student search"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse([])

    students = StudentModel.objects.filter(
        Q(first_name__icontains=query) |
        Q(last_name__icontains=query) |
        Q(registration_number__icontains=query)
    )[:10]

    data = []
    for student in students:
        wallet, _ = StudentWalletModel.objects.get_or_create(student=student)
        data.append({
            'id': student.id,
            'name': f"{student.first_name} {student.last_name}",
            'reg_number': student.registration_number,
            'student_class': str(student.current_class) if hasattr(student, 'current_class') else '',
            'wallet_balance': float(wallet.balance),
            'wallet_debt': float(wallet.debt),
            'image_url': student.image.url if student.image else None
        })

    return JsonResponse(data, safe=False)


@login_required
def api_item_search(request):
    """AJAX endpoint for item search"""
    query = request.GET.get('q', '')
    if len(query) < 2:
        return JsonResponse([])

    items = ItemModel.objects.filter(
        Q(name__icontains=query) |
        Q(barcode__icontains=query),
        is_active=True
    )[:10]

    data = []
    for item in items:
        data.append({
            'id': item.id,
            'name': item.name,
            'selling_price': float(item.current_selling_price),
            'qty_remaining': float(item.shop_quantity)
        })

    return JsonResponse(data, safe=False)


@login_required
def api_barcode_lookup(request):
    """AJAX endpoint for barcode lookup"""
    barcode = request.POST.get('barcode', '')

    try:
        item = ItemModel.objects.get(barcode=barcode, is_active=True)
        return JsonResponse({
            'success': True,
            'item': {
                'id': item.id,
                'name': item.name,
                'selling_price': float(item.selling_price),
                'qty_remaining': float(item.shop_quantity)
            }
        })
    except ItemModel.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Item not found'})


# Additional view for refund processing
@login_required
@permission_required("inventory.change_salemodel", raise_exception=True)
@transaction.atomic
def process_refund(request, pk):
    """Process a refund for a completed order"""
    if request.method != 'POST':
        return redirect('order_detail', pk=pk)

    sale = get_object_or_404(SaleModel, pk=pk)

    if sale.status != SaleModel.Status.COMPLETED:
        messages.error(request, 'Only completed orders can be refunded.')
        return redirect('order_detail', pk=pk)

    refund_reason = request.POST.get('refund_reason', '').strip()

    try:
        # Restore items to inventory
        for sale_item in sale.items.all():
            item = sale_item.item
            item.shop_quantity += sale_item.quantity
            item.save()

            # Restore stock batches (FIFO in reverse)
            remaining_qty = sale_item.quantity
            batches = StockInItemModel.objects.filter(
                item=item,
            ).order_by('-stock_in__created_at')  # Reverse order for refund

            for batch in batches:
                if remaining_qty <= 0:
                    break

                restore_qty = min(remaining_qty, sale_item.quantity)
                batch.quantity_remaining += restore_qty
                batch.save()

                remaining_qty -= restore_qty

        # Refund to customer wallet if applicable
        if sale.customer and sale.payment_method == SaleModel.PaymentMethod.STUDENT_WALLET:
            wallet, _ = StudentWalletModel.objects.get_or_create(student=sale.customer)
            wallet.balance = float(Decimal(str(wallet.balance)) + sale.total_amount)
            wallet.save()

        # Update sale status
        sale.status = SaleModel.Status.REFUNDED
        sale.save()

        # Log the refund
        staff = StaffProfileModel.objects.get(user=request.user).staff
        log = f"""
        <div class='text-white bg-warning p-2' style='border-radius: 5px;'>
          <p>
            <b>Order Refund:</b> Order
            <a href="{reverse('order_detail', kwargs={'pk': sale.pk})}"><b>#{sale.transaction_id}</b></a>
            was <b>refunded</b> by
            <a href="{reverse('staff_detail', kwargs={'pk': staff.pk})}"><b>{staff.__str__().title()}</b></a>.
            <br>
            <b>Amount:</b> ₦{sale.total_amount:.2f} | <b>Reason:</b> {refund_reason}
            <br>
            <b>Time:</b> {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}
          </p>
        </div>
        """

        ActivityLogModel.objects.create(log=log)
        messages.success(request, f'Order #{sale.transaction_id} has been successfully refunded.')

    except Exception as e:
        messages.error(request, f'Error processing refund: {str(e)}')

    return redirect('order_detail', pk=pk)


# Update your existing api_barcode_lookup to handle both students and items
@login_required
def api_barcode_lookup(request):
    """Enhanced barcode lookup for both students and items"""
    barcode = request.GET.get('barcode', '')

    if not barcode:
        return JsonResponse({'success': False, 'message': 'No barcode provided'})

    # Try to find student first
    try:
        student = StudentModel.objects.get(registration_number=barcode)
        wallet, _ = StudentWalletModel.objects.get_or_create(student=student)
        return JsonResponse({
            'success': True,
            'student': {
                'id': student.id,
                'name': f"{student.first_name} {student.last_name}",
                'reg_number': student.registration_number,
                'student_class': f"{student.student_class} {student.class_section}",
                'wallet_balance': float(wallet.balance),
                'wallet_debt': float(wallet.debt),
                'image_url': student.image.url if student.image else None
            }
        })
    except StudentModel.DoesNotExist:
        pass

    try:
        item = ItemModel.objects.get(barcode=barcode, is_active=True)
        print(item)
        return JsonResponse({
            'success': True,
            'item': {
                'id': item.id,
                'name': item.name,
                'selling_price': float(item.current_selling_price),
                'qty_remaining': float(item.shop_quantity)
            }
        })
    except ItemModel.DoesNotExist:
        pass

    return JsonResponse({'success': False, 'message': 'Barcode not found'})


@login_required
@permission_required("inventory.view_inventorycollectionmodel", raise_exception=True)
def assignment_list_view(request):
    """View all inventory assignments and initiate collection generation"""
    assignments = InventoryAssignmentModel.objects.filter(
        is_active=True
    ).select_related('item', 'session', 'term').prefetch_related('student_classes')

    context = {
        'assignments': assignments,
    }
    return render(request, 'inventory/inventory/assignment_list.html', context)


@login_required
@permission_required("inventory.add_inventorycollectionmodel", raise_exception=True)
def create_assignment_view(request):
    """Create a new inventory assignment"""
    if request.method == 'POST':
        try:
            # Get form data
            item_id = request.POST.get('item')
            quantity_per_student = Decimal(request.POST.get('quantity_per_student'))
            gender = request.POST.get('gender', 'both')
            type_choice = request.POST.get('type', '')
            is_mandatory = request.POST.get('is_mandatory') == 'on'
            is_free = request.POST.get('is_free') == 'on'
            notes = request.POST.get('notes', '')

            # Get selected classes
            selected_classes = request.POST.getlist('student_classes')

            # Get item
            item = get_object_or_404(ItemModel, pk=item_id)

            # Create assignment
            assignment = InventoryAssignmentModel.objects.create(
                item=item,
                quantity_per_student=quantity_per_student,
                gender=gender,
                type=type_choice if type_choice else None,
                is_mandatory=is_mandatory,
                is_free=is_free,
                notes=notes,
                created_by=request.user
            )

            # Add selected classes
            if selected_classes:
                assignment.student_classes.set(selected_classes)

            messages.success(
                request,
                f"Assignment created successfully for '{item.name}'"
            )
            return redirect('assignment_list')

        except Exception as e:
            messages.error(request, f"Error creating assignment: {str(e)}")
            return redirect('create_assignment')

    # GET request - show form
    items = ItemModel.objects.filter(
        is_active=True,
        location__in=['store', 'both']
    ).select_related('category').order_by('name')

    classes = ClassesModel.objects.all().order_by('name')

    context = {
        'items': items,
        'classes': classes,
    }
    return render(request, 'inventory/inventory/create_assignment.html', context)


@login_required
@permission_required("inventory.add_inventorycollectionmodel", raise_exception=True)
def edit_assignment_view(request, assignment_pk):
    """Edit an existing assignment"""
    assignment = get_object_or_404(InventoryAssignmentModel, pk=assignment_pk)

    if request.method == 'POST':
        try:
            assignment.quantity_per_student = Decimal(request.POST.get('quantity_per_student'))
            assignment.gender = request.POST.get('gender', 'both')
            assignment.type = request.POST.get('type', '') or None
            assignment.is_mandatory = request.POST.get('is_mandatory') == 'on'
            assignment.is_free = request.POST.get('is_free') == 'on'
            assignment.notes = request.POST.get('notes', '')
            assignment.updated_by = request.user

            # Update classes
            selected_classes = request.POST.getlist('student_classes')
            if selected_classes:
                assignment.student_classes.set(selected_classes)
            else:
                assignment.student_classes.clear()

            assignment.save()

            messages.success(request, "Assignment updated successfully")
            return redirect('assignment_list')

        except Exception as e:
            messages.error(request, f"Error updating assignment: {str(e)}")

    classes = ClassesModel.objects.all().order_by('name')

    context = {
        'assignment': assignment,
        'classes': classes,
    }
    return render(request, 'inventory/inventory/edit_assignment.html', context)


@login_required
@permission_required("inventory.add_inventorycollectionmodel", raise_exception=True)
def delete_assignment_view(request, assignment_pk):
    """Deactivate an assignment"""
    assignment = get_object_or_404(InventoryAssignmentModel, pk=assignment_pk)

    if request.method == 'POST':
        assignment.is_active = False
        assignment.updated_by = request.user
        assignment.save()

        messages.success(request, f"Assignment for '{assignment.item.name}' deactivated successfully")
        return redirect('assignment_list')

    return redirect('assignment_list')


@login_required
@permission_required("inventory.add_inventorycollectionmodel", raise_exception=True)
def generate_collections_view(request, assignment_pk):
    """Initiate background job to generate collections for an assignment"""
    assignment = get_object_or_404(InventoryAssignmentModel, pk=assignment_pk)

    # Check if item has stock in store
    if assignment.item.store_quantity <= 0:
        messages.error(
            request,
            f"Cannot generate collections. '{assignment.item.name}' has no stock in store."
        )
        return redirect('assignment_list')

    # Create a job record
    job = CollectionGenerationJob.objects.create(
        assignment=assignment,
        created_by=request.user
    )

    # Trigger the Celery task
    generate_collections_task.delay(job.pk)

    messages.success(
        request,
        f"Collection generation started for '{assignment.item.name}'. "
        f"Job ID: {job.job_id}"
    )
    return redirect('collection_job_status', job_id=job.job_id)


# ==================== JOB MONITORING VIEWS ====================

@login_required
@permission_required("inventory.view_inventorycollectionmodel", raise_exception=True)
def collection_job_status_view(request, job_id):
    """Monitor the progress of a collection generation job"""
    job = get_object_or_404(CollectionGenerationJob, job_id=job_id)

    context = {
        'job': job,
    }
    return render(request, 'inventory/inventory/collection_job_status.html', context)


@login_required
@permission_required("inventory.view_inventorycollectionmodel", raise_exception=True)
def collection_job_status_ajax(request, job_id):
    """AJAX endpoint to get real-time job progress"""
    job = get_object_or_404(CollectionGenerationJob, job_id=job_id)

    data = {
        'status': job.status,
        'progress_percentage': job.progress_percentage,
        'total_students': job.total_students,
        'processed_students': job.processed_students,
        'created_collections': job.created_collections,
        'skipped_students': job.skipped_students,
        'error_message': job.error_message,
    }
    return JsonResponse(data)


# ==================== STUDENT SEARCH VIEWS ====================

@login_required
@permission_required("inventory.view_inventorycollectionmodel", raise_exception=True)
def student_collection_search_view(request):
    """Search page to find students and access their collections"""
    # Get all classes for dropdown
    class_list = ClassesModel.objects.all().prefetch_related('section')

    # Serialize class data with sections
    class_list_data = []
    for cls in class_list:
        class_list_data.append({
            'id': cls.id,
            'name': cls.name,
            'sections': [
                {'id': sec.id, 'name': sec.name}
                for sec in cls.section.all()
            ]
        })

    # Get all students for client-side search
    students = StudentModel.objects.filter(
        status='active'
    ).select_related('student_class', 'class_section')

    # Serialize student data
    student_data = []
    for student in students:
        student_data.append({
            'pk': student.pk,
            'fields': {
                'first_name': student.first_name,
                'last_name': student.last_name,
                'registration_number': student.registration_number,
                'gender': student.gender,
                'student_class_name': student.student_class.name if student.student_class else '',
                'class_section_name': student.class_section.name if student.class_section else '',
                'image': student.image.url if student.image else '',
            }
        })

    context = {
        'class_list': class_list,
        'class_list_json': json.dumps(class_list_data),
        'student_list_json': json.dumps(student_data),
    }
    return render(request, 'inventory/inventory/student_collection_search.html', context)


# ==================== AJAX SEARCH ENDPOINTS ====================

@login_required
def ajax_get_students_by_class(request):
    """AJAX: Get students by class and section"""
    class_pk = request.GET.get('class_pk')
    section_pk = request.GET.get('section_pk')

    if not class_pk or not section_pk:
        return JsonResponse({'error': 'Missing parameters'}, status=400)

    students = StudentModel.objects.filter(
        student_class_id=class_pk,
        class_section_id=section_pk,
        status='active'
    ).order_by('first_name', 'last_name')

    html = ''
    for student in students:
        full_name = f"{student.first_name} {student.middle_name or ''} {student.last_name}".strip()
        html += f'''
        <li class="list-group-item list-group-item-action select-student" 
            style="cursor: pointer;" 
            data-student-id="{student.pk}">
            {full_name} ({student.registration_number})
        </li>
        '''

    if not html:
        html = '<li class="list-group-item list-group-item-danger">No students found.</li>'

    return JsonResponse({'html': html})


@login_required
def ajax_get_students_by_reg_no(request):
    """AJAX: Search students by registration number"""
    reg_no = request.GET.get('reg_no', '').strip()

    if len(reg_no) < 2:
        return JsonResponse({'html': ''})

    students = StudentModel.objects.filter(
        registration_number__icontains=reg_no,
        status='active'
    ).order_by('first_name', 'last_name')[:20]

    html = ''
    for student in students:
        full_name = f"{student.first_name} {student.middle_name or ''} {student.last_name}".strip()
        html += f'''
        <li class="list-group-item list-group-item-action select-student" 
            style="cursor: pointer;" 
            data-student-id="{student.pk}">
            {full_name} ({student.registration_number})
        </li>
        '''

    if not html:
        html = '<li class="list-group-item list-group-item-danger">No students found.</li>'

    return JsonResponse({'html': html})


# ==================== COLLECTION MANAGEMENT VIEWS ====================

@login_required
@permission_required("inventory.view_inventorycollectionmodel", raise_exception=True)
def student_collection_dashboard_view(request, student_pk):
    """View a student's inventory collections"""
    student = get_object_or_404(StudentModel, pk=student_pk)

    # Get all collections for this student
    collections = InventoryCollectionModel.objects.filter(
        student=student
    ).select_related(
        'assignment__item',
        'assignment__session',
        'assignment__term',
        'collected_by_staff'
    ).order_by('-created_at')

    # Get available items in store for direct purchase
    available_items = ItemModel.objects.filter(
        location__in=['store', 'both'],
        store_quantity__gt=0,
        is_active=True
    ).select_related('category')

    direct_purchases = DirectSaleModel.objects.filter(
        student=student
    ).select_related('item', 'session', 'term', 'sold_by').order_by('-sale_date')

    context = {
        'student': student,
        'collections': collections,
        'available_items': available_items,
        'direct_purchases': direct_purchases,
    }
    return render(request, 'inventory/inventory/student_collection_dashboard.html', context)


@login_required
@permission_required("inventory.add_inventorycollectionmodel", raise_exception=True)
def process_collection_view(request, collection_pk):
    """Process/update a collection (mark as collected, partial collection, etc.)"""
    collection = get_object_or_404(InventoryCollectionModel, pk=collection_pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'collect':
            quantity_to_collect = Decimal(request.POST.get('quantity_collected', 0))

            # Validate quantity
            if quantity_to_collect <= 0:
                messages.error(request, "Quantity must be greater than zero.")
                return redirect('student_collection_dashboard', student_pk=collection.student.pk)

            if quantity_to_collect > collection.outstanding_quantity:
                messages.error(request, "Quantity exceeds outstanding amount.")
                return redirect('student_collection_dashboard', student_pk=collection.student.pk)

            # Check store stock
            if collection.assignment.item.store_quantity < quantity_to_collect:
                messages.error(
                    request,
                    f"Insufficient stock in store. Available: {collection.assignment.item.store_quantity}"
                )
                return redirect('student_collection_dashboard', student_pk=collection.student.pk)

            # Check payment if required
            if collection.payment_required and not collection.payment_completed:
                messages.error(request, "Payment must be completed before collection.")
                return redirect('student_collection_dashboard', student_pk=collection.student.pk)

            # Process collection
            collection.quantity_collected += quantity_to_collect
            collection.collection_date = timezone.now().date()
            collection.collected_by_staff = request.user.staffmodel if hasattr(request.user, 'staffmodel') else None
            collection.save()

            # Reduce store stock
            item = collection.assignment.item
            item.store_quantity -= quantity_to_collect
            item.save(update_fields=['store_quantity'])

            messages.success(
                request,
                f"Collected {quantity_to_collect} {item.get_unit_display()} of {item.name}"
            )

        elif action == 'mark_paid':
            amount_paid = Decimal(request.POST.get('amount_paid', 0))
            collection.amount_paid = amount_paid
            collection.payment_completed = True
            collection.save(update_fields=['amount_paid', 'payment_completed'])
            messages.success(request, "Payment recorded successfully.")

        return redirect('student_collection_dashboard', student_pk=collection.student.pk)

    return redirect('student_collection_dashboard', student_pk=collection.student.pk)


@login_required
@permission_required("inventory.add_inventorycollectionmodel", raise_exception=True)
def create_direct_collection_view(request, student_pk):
    """Allow student to purchase/collect items not assigned to them - STANDALONE PURCHASE"""
    student = get_object_or_404(StudentModel, pk=student_pk)

    if request.method == 'POST':
        item_pk = request.POST.get('item')
        quantity = Decimal(request.POST.get('quantity', 0))
        amount_paid = Decimal(request.POST.get('amount_paid', 0))
        payment_method = request.POST.get('payment_method', 'Cash')

        item = get_object_or_404(ItemModel, pk=item_pk)

        # Validate stock
        if item.store_quantity < quantity:
            messages.error(request, "Insufficient stock in store.")
            return redirect('student_collection_dashboard', student_pk=student_pk)

        # Create a DirectSale record (NOT an assignment or collection)
        direct_sale = DirectSaleModel.objects.create(
            student=student,
            item=item,
            quantity=quantity,
            unit_price=item.current_selling_price,
            total_amount=item.current_selling_price * quantity,
            amount_paid=amount_paid,
            payment_completed=(amount_paid >= item.current_selling_price * quantity),
            payment_method=payment_method,
            sold_by=request.user.staffmodel if hasattr(request.user, 'staffmodel') else None,
            created_by=request.user
        )

        # Reduce stock
        item.store_quantity -= quantity
        item.save(update_fields=['store_quantity'])

        messages.success(
            request,
            f"Direct purchase processed: {quantity} {item.get_unit_display()} of {item.name} for ₦{amount_paid}"
        )
        return redirect('student_collection_dashboard', student_pk=student_pk)

    return redirect('student_collection_dashboard', student_pk=student_pk)