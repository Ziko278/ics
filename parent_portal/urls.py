# parent_portal/urls.py
from django.urls import path
from . import views
from .views import parent_change_password_view, ParentOtherPaymentListView

urlpatterns = [
    # --- Auth & Ward Selection ---
    path('select-ward/', views.SelectWardView.as_view(), name='parent_select_ward'),
    path('set-ward/<int:ward_id>/', views.SetWardView.as_view(), name='parent_set_ward'),

    # --- Main Portal ---
    path('dashboard/', views.DashboardView.as_view(), name='parent_dashboard'),

    # --- Fees ---
    path('account-details/', views.AccountDetailView.as_view(), name='parent_account_detail'),
    path('fees/', views.FeeInvoiceListView.as_view(), name='parent_fee_list'),
    path('fees/invoice/<int:pk>/', views.FeeInvoiceDetailView.as_view(), name='parent_fee_invoice_detail'), # Added detail view
    path('fees/upload/', views.FeeUploadView.as_view(), name='parent_fee_upload'),
    path('fees/history/', views.FeeUploadHistoryView.as_view(), name='parent_fee_history'),
    path('other-payments/', ParentOtherPaymentListView.as_view(), name='parent_other_payment_list'),

    # --- Shop ---
    path('shop/', views.ShopHistoryView.as_view(), name='parent_shop_history'),
    path('shop/<int:pk>/', views.ShopHistoryDetailView.as_view(), name='parent_shop_detail'),

    # --- Inventory ---
    path('inventory/', views.InventoryView.as_view(), name='parent_inventory_list'),

    # --- Cafeteria ---
    path('cafeteria/', views.CafeteriaHistoryView.as_view(), name='parent_cafeteria_history'),

    path('change-password/', parent_change_password_view, name='parent_change_password'),
]