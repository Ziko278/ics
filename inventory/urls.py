from django.urls import path

from student.views import identify_student_by_fingerprint
from .views import (
    CategoryListView, CategoryCreateView, CategoryUpdateView, CategoryDeleteView,
    SupplierListView, SupplierCreateView, SupplierDetailView, SupplierUpdateView, SupplierDeleteView,
    ItemListView, ItemDetailView, ItemDeleteView, ItemBarcodeScanAjaxView, ItemCreateView, ItemUpdateView,
    PurchaseOrderListView, PurchaseOrderDetailView, PurchaseOrderCreateView, PurchaseOrderItemCreateView,
    PurchaseOrderItemDeleteView, POItemSearchAjaxView, PurchaseOrderStatusUpdateView, StockInListView,
    ManualStockInCreateView, StockInDetailView, StockInFromPOCreateView, StockOutCreateView, StockOutListView,
    StockTransferListView, StockTransferCreateView, StockTransferDetailView, ItemSearchForTransferAjaxView,
    PurchaseAdvanceListView, PurchaseAdvanceCreateView, PurchaseAdvanceDetailView, PurchaseAdvanceItemCreateView,
    PurchaseAdvanceItemDeleteView, AdvanceItemSearchAjaxView, PurchaseAdvanceStatusUpdateView, place_order_view,
    view_orders, order_detail, process_refund, api_student_search, api_item_search, api_barcode_lookup,
    assignment_list_view, generate_collections_view, collection_job_status_view, collection_job_status_ajax,
    student_collection_search_view, ajax_get_students_by_class, ajax_get_students_by_reg_no,
    student_collection_dashboard_view, process_collection_view, create_direct_collection_view, create_assignment_view,
    delete_assignment_view, edit_assignment_view,
)


urlpatterns = [
    # Inventory Category URLs
    path('categories/', CategoryListView.as_view(), name='inventory_category_list'),
    path('categories/create/', CategoryCreateView.as_view(), name='inventory_category_create'),
    path('categories/<int:pk>/update/', CategoryUpdateView.as_view(), name='inventory_category_update'),
    path('categories/<int:pk>/delete/', CategoryDeleteView.as_view(), name='inventory_category_delete'),

    # Inventory Supplier URLs
    path('suppliers/', SupplierListView.as_view(), name='inventory_supplier_list'),
    path('suppliers/create/', SupplierCreateView.as_view(), name='inventory_supplier_create'),
    path('suppliers/<int:pk>/', SupplierDetailView.as_view(), name='inventory_supplier_detail'),
    path('suppliers/<int:pk>/update/', SupplierUpdateView.as_view(), name='inventory_supplier_update'),
    path('suppliers/<int:pk>/delete/', SupplierDeleteView.as_view(), name='inventory_supplier_delete'),

    path('items/', ItemListView.as_view(), name='inventory_item_list'),
    path('items/create/', ItemCreateView.as_view(), name='inventory_item_create'),
    path('items/<int:pk>/', ItemDetailView.as_view(), name='inventory_item_detail'),
    path('items/<int:pk>/update/', ItemUpdateView.as_view(), name='inventory_item_update'),
    path('items/<int:pk>/delete/', ItemDeleteView.as_view(), name='inventory_item_delete'),

    # --- AJAX URL for Barcode Scanning ---
    path('items/ajax/scan-barcode/', ItemBarcodeScanAjaxView.as_view(), name='inventory_item_ajax_scan'),

    path('inventory/purchase-orders/', PurchaseOrderListView.as_view(), name='inventory_po_list'),
    path('inventory/purchase-orders/create/', PurchaseOrderCreateView.as_view(), name='inventory_po_create'),
    path('inventory/purchase-orders/<int:pk>/', PurchaseOrderDetailView.as_view(), name='inventory_po_detail'),

    # URLs for managing items within a PO
    path('inventory/purchase-orders/<int:po_pk>/add-item/', PurchaseOrderItemCreateView.as_view(),
         name='inventory_po_add_item'),
    path('inventory/purchase-orders/item/<int:pk>/delete/', PurchaseOrderItemDeleteView.as_view(),
         name='inventory_po_delete_item'),

    # AJAX URLs for the PO detail page
    path('inventory/purchase-orders/ajax/search-items/', POItemSearchAjaxView.as_view(),
         name='inventory_po_ajax_search'),
    path('inventory/purchase-orders/<int:pk>/update-status/', PurchaseOrderStatusUpdateView.as_view(),
         name='inventory_po_update_status'),

    path('inventory/stock-in/', StockInListView.as_view(), name='inventory_stock_in_list'),
    path('inventory/stock-in/manual/', ManualStockInCreateView.as_view(), name='inventory_manual_stock_in_create'),
    path('inventory/stock-in/<int:pk>/', StockInDetailView.as_view(), name='inventory_stock_in_detail'),
    path('inventory/stock-in/from-po/<int:po_pk>/', StockInFromPOCreateView.as_view(), name='inventory_stock_in_from_po_create'),

    path('inventory/items/<int:item_pk>/stock-out/', StockOutCreateView.as_view(), name='inventory_item_stock_out'),
    path('inventory/stock-out/', StockOutListView.as_view(), name='inventory_stock_out_list'),

    path('inventory/stock-transfer/', StockTransferListView.as_view(), name='inventory_stock_transfer_list'),
    path('inventory/stock-transfer/create/', StockTransferCreateView.as_view(), name='inventory_stock_transfer_create'),
    path('inventory/stock-transfer/<int:pk>/', StockTransferDetailView.as_view(), name='inventory_stock_transfer_detail'),
    path('inventory/stock-transfer/ajax/search-items/', ItemSearchForTransferAjaxView.as_view(), name='inventory_transfer_ajax_search'),

    # Purchase Advance URLs
    path('inventory/purchase-advances/', PurchaseAdvanceListView.as_view(), name='inventory_advance_list'),
    path('inventory/purchase-advances/create/', PurchaseAdvanceCreateView.as_view(), name='inventory_advance_create'),
    path('inventory/purchase-advances/<int:pk>/', PurchaseAdvanceDetailView.as_view(), name='inventory_advance_detail'),

    # URLs for managing items within an advance
    path('inventory/purchase-advances/<int:advance_pk>/add-item/', PurchaseAdvanceItemCreateView.as_view(),
         name='inventory_advance_add_item'),
    path('inventory/purchase-advances/item/<int:pk>/delete/', PurchaseAdvanceItemDeleteView.as_view(),
         name='inventory_advance_delete_item'),

    # AJAX URLs for the advance detail page
    path('inventory/purchase-advances/ajax/search-items/', AdvanceItemSearchAjaxView.as_view(),
         name='inventory_advance_ajax_search'),
    path('inventory/purchase-advances/<int:pk>/update-status/', PurchaseAdvanceStatusUpdateView.as_view(),
         name='inventory_advance_update_status'),

    path('place-order/', place_order_view, name='place_order'),
    path('orders/', view_orders, name='view_orders'),
    path('orders/<int:pk>/', order_detail, name='order_detail'),
    path('orders/<int:pk>/refund/', process_refund, name='process_refund'),
    path('place-order/', place_order_view, name='place_order'),

    path('api/student-search/', api_student_search, name='api_student_search'),
    path('api/item-search/', api_item_search, name='api_item_search'),
    path('api/barcode-lookup/', api_barcode_lookup, name='api_barcode_lookup'),
    path('api/identify-fingerprint/', identify_student_by_fingerprint, name='identify_student_by_fingerprint'),

    path('assignments/', assignment_list_view, name='assignment_list'),
    path('assignments/create/', create_assignment_view, name='create_assignment'),
    path('assignments/<int:assignment_pk>/edit/', edit_assignment_view, name='edit_assignment'),
    path('assignments/<int:assignment_pk>/delete/', delete_assignment_view, name='delete_assignment'),
    path('assignments/<int:assignment_pk>/generate/', generate_collections_view, name='generate_collections'),

    # Job Monitoring
    path('jobs/<uuid:job_id>/', collection_job_status_view, name='collection_job_status'),
    path('jobs/<uuid:job_id>/ajax/', collection_job_status_ajax, name='collection_job_status_ajax'),

    # Student Search
    path('students/search/', student_collection_search_view, name='student_collection_search'),
    path('students/ajax/by-class/', ajax_get_students_by_class, name='ajax_get_students_by_class'),
    path('students/ajax/by-reg/', ajax_get_students_by_reg_no, name='ajax_get_students_by_reg_no'),

    # Collection Management
    path('students/<int:student_pk>/collections/', student_collection_dashboard_view,
         name='student_collection_dashboard'),
    path('collections/<int:collection_pk>/process/', process_collection_view, name='process_collection'),
    path('student/<int:student_pk>/direct-purchase/', create_direct_collection_view,
         name='create_direct_collection'),

]