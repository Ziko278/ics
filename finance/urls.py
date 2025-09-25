from django.urls import path
from finance.views import (
    FinanceSettingDetailView, FinanceSettingCreateView, FinanceSettingUpdateView,
    SupplierAccountsListView, SupplierAccountDetailView, SupplierPaymentRevertView, AllSupplierPaymentsListView,
    SupplierPaymentReceiptView, PurchaseAdvanceAccountsListView, PurchaseAdvancePaymentDetailView,
    FeeListView, FeeCreateView, FeeUpdateView, FeeDeleteView, FeeGroupListView, FeeGroupCreateView, FeeGroupUpdateView,
    FeeGroupDeleteView, FeeMasterListView, FeeMasterCreateView, FeeMasterUpdateView, FeeMasterDeleteView,
    InvoiceListView, InvoiceGenerationView, InvoiceJobStatusView, invoice_job_status_api, InvoiceDetailView,
    ExpenseCategoryListView, ExpenseCategoryCreateView, ExpenseCategoryUpdateView, ExpenseCategoryDeleteView,
    ExpenseListView, ExpenseCreateView, ExpenseUpdateView, ExpenseDetailView, IncomeCategoryListView,
    IncomeCategoryCreateView, FeeMasterDetailView, IncomeCategoryUpdateView, IncomeCategoryDeleteView, IncomeListView,
    IncomeCreateView, IncomeUpdateView, IncomeDetailView, StudentFeeSearchView, get_students_by_class_ajax,
    get_students_by_reg_no_ajax, StudentFinancialDashboardView, BulkFeePaymentView, FeePaymentRevertView,
    FeePaymentReceiptView, StaffBankDetailListView, StaffBankDetailUpdateView, StaffBankDetailCreateView,
    SalaryStructureListView, StaffBankDetailDeleteView, SalaryStructureCreateView, SalaryStructureDetailView,
    SalaryStructureUpdateView, SalaryStructureDeleteView, SalaryAdvanceListView, SalaryAdvanceCreateView,
    SalaryAdvanceDetailView, SalaryAdvanceActionView, process_payroll_view, payroll_dashboard_view,
    export_payroll_to_excel,
)

urlpatterns = [
    # Finance Settings URLs (Singleton Pattern)
    path('settings/', FinanceSettingDetailView.as_view(), name='finance_setting_detail'),
    path('settings/create/', FinanceSettingCreateView.as_view(), name='finance_setting_create'),
    path('settings/update/', FinanceSettingUpdateView.as_view(), name='finance_setting_update'),

    # The main "Accounts Payable" page, listing POs that need payment. This is the main entry point.
    path('finance/accounts-payable/', SupplierAccountsListView.as_view(), name='finance_accounts_payable_list'),

    # The detail page for a single PO, where payments are made and managed.
    path('finance/accounts-payable/<int:po_pk>/', SupplierAccountDetailView.as_view(),
         name='finance_po_payment_detail'),

    # The action URL to revert a specific payment record in case of error.
    path('finance/supplier-payments/<int:pk>/revert/', SupplierPaymentRevertView.as_view(),
         name='finance_supplier_payment_revert'),

    # The secondary page for viewing a historical log of all individual payment transactions.
    path('finance/supplier-payments/all/', AllSupplierPaymentsListView.as_view(), name='finance_all_payments_list'),
    path('finance/supplier-payments/<int:pk>/receipt/', SupplierPaymentReceiptView.as_view(),
         name='finance_supplier_payment_receipt'),

    path('finance/purchase-advances/', PurchaseAdvanceAccountsListView.as_view(), name='finance_advance_accounts_list'),
    path('finance/purchase-advances/<int:advance_pk>/payments/', PurchaseAdvancePaymentDetailView.as_view(), name='finance_advance_payment_detail'),

    # --- Fee Structure Setup ---
    path('finance/fees/', FeeListView.as_view(), name='finance_fee_list'),
    path('finance/fees/create/', FeeCreateView.as_view(), name='finance_fee_create'),
    path('finance/fees/<int:pk>/update/', FeeUpdateView.as_view(), name='finance_fee_update'),
    path('finance/fees/<int:pk>/delete/', FeeDeleteView.as_view(), name='finance_fee_delete'),

    path('finance/fee-groups/', FeeGroupListView.as_view(), name='finance_fee_group_list'),
    path('finance/fee-groups/create/', FeeGroupCreateView.as_view(), name='finance_fee_group_create'),
    path('finance/fee-groups/<int:pk>/update/', FeeGroupUpdateView.as_view(), name='finance_fee_group_update'),
    path('finance/fee-groups/<int:pk>/delete/', FeeGroupDeleteView.as_view(), name='finance_fee_group_delete'),

    path('finance/fee-structures/', FeeMasterListView.as_view(), name='finance_fee_master_list'),
    path('finance/fee-structures/create/', FeeMasterCreateView.as_view(), name='finance_fee_master_create'),
    # This single URL handles both viewing the details and updating the termly prices
    path('finance/fee-structures/<int:pk>/', FeeMasterDetailView.as_view(), name='finance_fee_master_detail'),
    path('finance/fee-structures/<int:pk>/update/', FeeMasterUpdateView.as_view(), name='finance_fee_master_update'),
    path('finance/fee-structures/<int:pk>/delete/', FeeMasterDeleteView.as_view(), name='finance_fee_master_delete'),

    # --- Invoicing & Payment ---
    path('finance/invoices/', InvoiceListView.as_view(), name='finance_invoice_list'),
    path('finance/invoices/generate/', InvoiceGenerationView.as_view(), name='finance_invoice_generate'),
    path('finance/invoices/job/<uuid:pk>/', InvoiceJobStatusView.as_view(), name='finance_invoice_job_status'),
    path('finance/invoices/job/<uuid:pk>/api/', invoice_job_status_api, name='finance_invoice_job_status_api'),
    path('finance/invoices/<int:pk>/', InvoiceDetailView.as_view(), name='finance_invoice_detail'),

    path('finance/student-payments/search/', StudentFeeSearchView.as_view(), name='finance_student_payment_search'),
    path('finance/student-payments/ajax/get-by-class/', get_students_by_class_ajax, name='finance_ajax_get_students_by_class'),
    path('finance/student-payments/ajax/get-by-reg-no/', get_students_by_reg_no_ajax, name='finance_ajax_get_students_by_reg_no'),

    path('finance/student/<int:pk>/dashboard/', StudentFinancialDashboardView.as_view(), name='finance_student_dashboard'),

    # The page for making a bulk payment for a student
    path('finance/student/<int:pk>/bulk-payment/', BulkFeePaymentView.as_view(), name='finance_bulk_payment_create'),

    # Action URLs for individual payments
    path('finance/student-payments/<int:pk>/revert/', FeePaymentRevertView.as_view(), name='finance_fee_payment_revert'),
    path('finance/student-payments/<int:pk>/receipt/', FeePaymentReceiptView.as_view(), name='finance_fee_payment_receipt'),


    path("expense-categories/", ExpenseCategoryListView.as_view(), name="expense_category_index"),
    path("expense-categories/create/", ExpenseCategoryCreateView.as_view(), name="expense_category_create"),
    path("expense-categories/<int:pk>/edit/", ExpenseCategoryUpdateView.as_view(), name="expense_category_update"),
    path("expense-categories/<int:pk>/delete/", ExpenseCategoryDeleteView.as_view(), name="expense_category_delete"),

    # Expense URLs
    path("expenses/", ExpenseListView.as_view(), name="expense_index"),
    path("expenses/create/", ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/edit/", ExpenseUpdateView.as_view(), name="expense_update"),
    path("expenses/<int:pk>/", ExpenseDetailView.as_view(), name="expense_detail"),

    # Income Category URLs
    path("income-categories/", IncomeCategoryListView.as_view(), name="income_category_index"),
    path("income-categories/create/", IncomeCategoryCreateView.as_view(), name="income_category_create"),
    path("income-categories/<int:pk>/edit/", IncomeCategoryUpdateView.as_view(), name="income_category_update"),
    path("income-categories/<int:pk>/delete/", IncomeCategoryDeleteView.as_view(), name="income_category_delete"),

    # Income URLs
    path("incomes/", IncomeListView.as_view(), name="income_index"),
    path("incomes/create/", IncomeCreateView.as_view(), name="income_create"),
    path("incomes/<int:pk>/edit/", IncomeUpdateView.as_view(), name="income_update"),
    path("incomes/<int:pk>/", IncomeDetailView.as_view(), name="income_detail"),

    path('finance/staff-bank/', StaffBankDetailListView.as_view(), name='finance_staff_bank_detail_list'),
    path('finance/staff-bank/create/', StaffBankDetailCreateView.as_view(), name='finance_staff_bank_detail_create'),
    path('finance/staff-bank/<int:pk>/update/', StaffBankDetailUpdateView.as_view(),
         name='finance_staff_bank_detail_update'),
    path('finance/staff-bank/<int:pk>/delete/', StaffBankDetailDeleteView.as_view(),
         name='finance_staff_bank_detail_delete'),

    # --- Salary Structure URLs (Multi-page Interface) ---
    path('finance/salary-structures/', SalaryStructureListView.as_view(), name='finance_salary_structure_list'),
    path('finance/salary-structures/create/', SalaryStructureCreateView.as_view(),
         name='finance_salary_structure_create'),
    path('finance/salary-structures/<int:pk>/', SalaryStructureDetailView.as_view(),
         name='finance_salary_structure_detail'),
    path('finance/salary-structures/<int:pk>/update/', SalaryStructureUpdateView.as_view(),
         name='finance_salary_structure_update'),
    path('finance/salary-structures/<int:pk>/delete/', SalaryStructureDeleteView.as_view(),
         name='finance_salary_structure_delete'),

    # --- Salary Advance URLs (Multi-page Interface) ---
    path('finance/salary-advances/', SalaryAdvanceListView.as_view(), name='finance_salary_advance_list'),
    path('finance/salary-advances/create/', SalaryAdvanceCreateView.as_view(), name='finance_salary_advance_create'),
    path('finance/salary-advances/<int:pk>/', SalaryAdvanceDetailView.as_view(), name='finance_salary_advance_detail'),
    path('finance/salary-advances/<int:pk>/action/', SalaryAdvanceActionView.as_view(),
         name='finance_salary_advance_action'),

    # --- Salary Record (Paysheet) URLs ---
    path('finance/payroll/process/', process_payroll_view, name='finance_process_payroll'),
    path('finance/payroll/dashboard/', payroll_dashboard_view, name='finance_payroll_dashboard'),
    path('finance/payroll/export/<int:year>/<int:month>/', export_payroll_to_excel, name='finance_export_payroll'),

]