from django.urls import path
from finance.views import *

urlpatterns = [
    # Finance Settings URLs (Singleton Pattern)
    path('settings/', FinanceSettingDetailView.as_view(), name='finance_setting_detail'),
    path('settings/create/', FinanceSettingCreateView.as_view(), name='finance_setting_create'),
    path('settings/update/', FinanceSettingUpdateView.as_view(), name='finance_setting_update'),

    # The main "Accounts Payable" page, listing POs that need payment. This is the main entry point.
    path('accounts-payable/', SupplierAccountsListView.as_view(), name='finance_accounts_payable_list'),

    # The detail page for a single PO, where payments are made and managed.
    path('accounts-payable/<int:po_pk>/', SupplierAccountDetailView.as_view(),
         name='finance_po_payment_detail'),

    # The action URL to revert a specific payment record in case of error.
    path('supplier-payments/<int:pk>/revert/', SupplierPaymentRevertView.as_view(),
         name='finance_supplier_payment_revert'),

    # The secondary page for viewing a historical log of all individual payment transactions.
    path('supplier-payments/all/', AllSupplierPaymentsListView.as_view(), name='finance_all_payments_list'),
    path('supplier-payments/<int:pk>/receipt/', SupplierPaymentReceiptView.as_view(),
         name='finance_supplier_payment_receipt'),

    path('purchase-advances/', PurchaseAdvanceAccountsListView.as_view(), name='finance_advance_accounts_list'),
    path('purchase-advances/<int:advance_pk>/payments/', PurchaseAdvancePaymentDetailView.as_view(), name='finance_advance_payment_detail'),

    # --- Fee Structure Setup ---
    path('fees/', FeeListView.as_view(), name='finance_fee_list'),
    path('fees/create/', FeeCreateView.as_view(), name='finance_fee_create'),
    path('fees/<int:pk>/update/', FeeUpdateView.as_view(), name='finance_fee_update'),
    path('fees/<int:pk>/delete/', FeeDeleteView.as_view(), name='finance_fee_delete'),

    path('fee-groups/', FeeGroupListView.as_view(), name='finance_fee_group_list'),
    path('fee-groups/create/', FeeGroupCreateView.as_view(), name='finance_fee_group_create'),
    path('fee-groups/<int:pk>/update/', FeeGroupUpdateView.as_view(), name='finance_fee_group_update'),
    path('fee-groups/<int:pk>/delete/', FeeGroupDeleteView.as_view(), name='finance_fee_group_delete'),

    path('discounts/', DiscountListView.as_view(), name='finance_discount_list'),
    path('discounts/create/', DiscountCreateView.as_view(), name='finance_discount_create'),
    path('discounts/<int:pk>/update/', DiscountUpdateView.as_view(), name='finance_discount_update'),
    path('discounts/<int:pk>/delete/', DiscountDeleteView.as_view(), name='finance_discount_setup_delete'),

    path('discount-rates/create/', DiscountApplicationCreateView.as_view(), name='finance_discount_application_create'),
    path('discount-rates/<int:application_pk>/update/', DiscountApplicationUpdateView.as_view(), name='finance_discount_application_update'),
    path('discount-rates/<int:application_pk>/delete/', DiscountApplicationDeleteView.as_view(), name='finance_discount_application_delete'),
    path('discount-rates/', DiscountApplicationListView.as_view(), name='finance_discount_application_list'),

    path('discounts/select-student/', DiscountSelectStudentView.as_view(), name='finance_discount_select_student'),
    path('discount/student/<int:student_pk>/assign/', StudentDiscountAssignView.as_view(), name='finance_discount_assign'),
    path('discounts/index/', StudentDiscountIndexView.as_view(), name='finance_discount_index'),
    path('discounts/delete/<int:pk>/', StudentDiscountDeleteView.as_view(), name='finance_discount_delete'),

    path('discount/api/get-discounts/', GetDiscountsAjaxView.as_view(), name='finance_discount_get_ajax'),

    path('fee-structures/', FeeMasterListView.as_view(), name='finance_fee_master_list'),
    path('fee-structures/create/', FeeMasterCreateView.as_view(), name='finance_fee_master_create'),
    # This single URL handles both viewing the details and updating the termly prices
    path('fee-structures/<int:pk>/', FeeMasterDetailView.as_view(), name='finance_fee_master_detail'),
    path('fee-structures/<int:pk>/update/', FeeMasterUpdateView.as_view(), name='finance_fee_master_update'),
    path('fee-structures/<int:pk>/delete/', FeeMasterDeleteView.as_view(), name='finance_fee_master_delete'),

    # --- Invoicing & Payment ---
    path('invoices/', InvoiceListView.as_view(), name='finance_invoice_list'),
    path('invoices/generate/', InvoiceGenerationView.as_view(), name='finance_invoice_generate'),
    path('invoices/job/<uuid:pk>/', InvoiceJobStatusView.as_view(), name='finance_invoice_job_status'),
    path('invoices/job/<uuid:pk>/api/', invoice_job_status_api, name='finance_invoice_job_status_api'),
    path('invoices/<int:pk>/', InvoiceDetailView.as_view(), name='finance_invoice_detail'),

    path('invoices/<int:pk>/delete/', InvoiceDeleteView.as_view(), name='finance_invoice_delete'),
    path('invoices/items/<int:pk>/delete/', InvoiceItemDeleteView.as_view(), name='finance_invoice_item_delete'),

    path('student-payments/search/', StudentFeeSearchView.as_view(), name='finance_student_payment_search'),
    path('student-payments/ajax/get-by-class/', get_students_by_class_ajax, name='finance_ajax_get_students_by_class'),
    path('student-payments/ajax/get-by-reg-no/', get_students_by_reg_no_ajax, name='finance_ajax_get_students_by_reg_no'),
    path('payments/', FeePaymentListView.as_view(), name='finance_payment_index'),
    path('payments/pending/', FeePendingPaymentListView.as_view(), name='finance_pending_payment_index'),

    path('student/<int:pk>/dashboard/', StudentFinancialDashboardView.as_view(), name='finance_student_dashboard'),
    path('invoice/<int:pk>/receipt/', InvoiceReceiptView.as_view(), name='finance_invoice_receipt'),

    # The page for making a bulk payment for a student
    path('finance/student/<int:pk>/bulk-payment/', BulkFeePaymentView.as_view(), name='finance_bulk_payment_create'),

    # Action URLs for individual payments
    path('finance/student-payments/<int:pk>/revert/', FeePaymentRevertView.as_view(), name='finance_fee_payment_revert'),
    path('finance/student-payments/<int:pk>/receipt/', FeePaymentReceiptView.as_view(), name='finance_fee_payment_receipt'),
    path('fee-payments/<int:payment_id>/confirm/', confirm_fee_payment_view, name='confirm_fee_payment'),

    path('get-invoice-items/<int:invoice_id>/', get_invoice_items_json, name='get_invoice_items_json'),
    path('payment/review/<int:payment_id>/', payment_review_view, name='review_fee_payment'),

    path("expense-categories/", ExpenseCategoryListView.as_view(), name="expense_category_index"),
    path("expense-categories/create/", ExpenseCategoryCreateView.as_view(), name="expense_category_create"),
    path("expense-categories/<int:pk>/edit/", ExpenseCategoryUpdateView.as_view(), name="expense_category_update"),
    path("expense-categories/<int:pk>/delete/", ExpenseCategoryDeleteView.as_view(), name="expense_category_delete"),

    # Expense URLs
    path("expenses/", ExpenseListView.as_view(), name="expense_index"),
    path("expenses/create/", ExpenseCreateView.as_view(), name="expense_create"),
    path("expenses/<int:pk>/edit/", ExpenseUpdateView.as_view(), name="expense_update"),
    path("expenses/<int:pk>/", ExpenseDetailView.as_view(), name="expense_detail"),
    path('expense/<int:pk>/print-voucher/', ExpensePrintVoucherView.as_view(), name='expense_print_voucher'),


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

    path('finance/school-bank/', SchoolBankDetailListView.as_view(), name='finance_school_bank_detail_list'),
    path('finance/school-bank/create/', SchoolBankDetailCreateView.as_view(), name='finance_school_bank_detail_create'),
    path('finance/school-bank/<int:pk>/update/', SchoolBankDetailUpdateView.as_view(), name='finance_school_bank_detail_update'),
    path('finance/school-bank/<int:pk>/delete/', SchoolBankDetailDeleteView.as_view(), name='finance_school_bank_detail_delete'),

    # --- Salary Advance URLs (Multi-page Interface) ---
    path('finance/salary-advances/', SalaryAdvanceListView.as_view(), name='finance_salary_advance_list'),
    path('finance/salary-advances/create/', SalaryAdvanceCreateView.as_view(), name='finance_salary_advance_create'),
    path('finance/salary-advances/<int:pk>/', SalaryAdvanceDetailView.as_view(), name='finance_salary_advance_detail'),
    path('finance/salary-advances/<int:pk>/action/', SalaryAdvanceActionView.as_view(),
         name='finance_salary_advance_action'),


    # --- Staff Loan URLs ---
    path('finance/staff-loans/', StaffLoanListView.as_view(), name='finance_staff_loan_list'),
    path('finance/staff-loans/create/', StaffLoanCreateView.as_view(), name='finance_staff_loan_create'),
    path('finance/staff-loans/<int:pk>/', StaffLoanDetailView.as_view(), name='finance_staff_loan_detail'),
    path('finance/staff-loans/<int:pk>/action/', StaffLoanActionView.as_view(), name='finance_staff_loan_action'),
    path('staff-loans/debtors/', StaffLoanDebtorsListView.as_view(), name='finance_staff_loan_debtors'),
    path('staff-loans/staff/<int:staff_pk>/', StaffLoanDebtDetailView.as_view(), name='finance_staff_loan_debt_detail'),
    path('staff-loans/staff/<int:staff_pk>/repay/', record_staff_loan_repayment, name='finance_record_loan_repayment'),



    path('deposit/select-student', DepositPaymentSelectStudentView.as_view(), name='deposit_select_student'),
    path('deposit/get-class-student', deposit_get_class_students, name='deposit_get_class_students'),
    path('deposit/get-student-by-reg-number', deposit_get_class_students_by_reg_number,
         name='deposit_get_class_students_by_reg_number'),
    path('deposit/payment/index', deposit_payment_list_view, name='deposit_index'),
    path('deposit/<int:pk>/detail', deposit_detail_view, name='deposit_detail'),
    path('deposit/<int:student_pk>/create', deposit_create_view, name='deposit_create'),
    path('deposit/<int:pk>/revert/', deposit_revert_view, name='deposit_revert'),

    path('deposit/payment/pending/index', pending_deposit_payment_list_view, name='pending_deposit_index'),
    path('deposit/<int:payment_id>/confirm/', confirm_payment_view, name='confirm_payment'),
    path('deposit/<int:payment_id>/cancel/', decline_payment_view, name='decline_payment'),


    path('staff-deposit/select-staff', DepositPaymentSelectStaffView.as_view(), name='deposit_select_staff'),
    path('staff-deposit/payment/index', staff_deposit_payment_list_view, name='staff_deposit_index'),
    path('staff-deposit/<int:pk>/detail', staff_deposit_detail_view, name='staff_deposit_detail'),
    path('staff-deposit/<int:staff_pk>/create', staff_deposit_create_view, name='staff_deposit_create'),

    path('staff-deposit/payment/pending/index', staff_pending_deposit_payment_list_view, name='staff_pending_deposit_index'),
    path('staff-deposit/<int:payment_id>/confirm/', staff_confirm_payment_view, name='staff_confirm_payment'),
    path('staff-deposit/<int:payment_id>/cancel/', staff_decline_payment_view, name='staff_decline_payment'),
    path('staff-deposit/<int:pk>/revert/', staff_deposit_revert_view, name='staff_deposit_revert'),

    path('my-funding/upload/', StaffUploadDepositView.as_view(), name='staff_upload_deposit'),

    # 2. STAFF: Page for staff to see their own deposit history
    path('my-funding/history/', StaffDepositHistoryView.as_view(), name='staff_deposit_history'),

    path('fee/dashboard/', fee_dashboard, name='fee_dashboard'),
    path('dashboard/', finance_dashboard, name='finance_dashboard'),

    path('reports/income-expense/', income_expense_report, name='income_expense_report'),

    path('payment-cleanup/', payment_cleanup_view, name='payment_cleanup_view'),
    path('payment-cleanup/process-class/', process_payment_cleanup_for_class, name='payment_cleanup_process_class'),

    # ============================================================================
    # GENERAL OTHER PAYMENT URLS (All students)
    # ============================================================================
    path('other-payments/', OtherPaymentListView.as_view(), name='finance_other_payment_list'),

    # ============================================================================
    # STUDENT-SPECIFIC OTHER PAYMENT URLS
    # ============================================================================
    path('student/<int:student_pk>/other-payments/', StudentOtherPaymentIndexView.as_view(), name='finance_student_other_payment_index'),
    path('student/<int:student_pk>/other-payments/create/', StudentOtherPaymentCreateView.as_view(), name='finance_student_other_payment_create'),
    path('other-payments/<int:pk>/update/', StudentOtherPaymentUpdateView.as_view(), name='finance_other_payment_update'),
    path('other-payments/<int:pk>/delete/', StudentOtherPaymentDeleteView.as_view(), name='finance_other_payment_delete'),

    # ============================================================================
    # PAYMENT CLEARANCE URLS
    # ============================================================================
    path('other-payments/<int:other_payment_pk>/pay/', OtherPaymentClearanceCreateView.as_view(), name='finance_other_payment_pay'),
    path('other-payment-clearance/<int:pk>/revert/', OtherPaymentClearanceRevertView.as_view(), name='finance_other_payment_clearance_revert'),

    path('finance/salary-settings/', salary_setting_list_view, name='finance_salary_setting_list'),
    path('finance/salary-settings/create/', salary_setting_create_view, name='finance_salary_setting_create'),
    path('finance/salary-settings/<int:pk>/', salary_setting_detail_view, name='finance_salary_setting_detail'),
    path('finance/salary-settings/<int:pk>/update/', salary_setting_update_view,
         name='finance_salary_setting_update'),

    # Salary Structure URLs
    path('finance/salary-structures/', salary_structure_list_view, name='finance_salary_structure_list'),
    path('finance/salary-structures/create/', salary_structure_create_view,
         name='finance_salary_structure_create'),
    path('finance/salary-structures/<int:pk>/', salary_structure_detail_view,
         name='finance_salary_structure_detail'),
    path('finance/salary-structures/<int:pk>/update/', salary_structure_update_view,
         name='finance_salary_structure_update'),

    path('payroll/dashboard/', payroll_dashboard_view, name='finance_payroll_dashboard'),

    path('payroll/', payroll_view, name='finance_payroll'),
    path('payroll/process/<int:structure_id>/', process_payroll_view, name='finance_process_payroll'),
    path('payroll/record/<int:pk>/', salary_record_detail_view, name='finance_salary_record_detail'),
    path('payroll/record/<int:pk>/pdf/', download_payslip_pdf, name='finance_download_payslip_pdf'),
    path('payroll/mark-paid/<int:pk>/', mark_as_paid_view, name='finance_mark_as_paid'),
    path('payroll/bulk/', bulk_payroll_view, name='finance_bulk_payroll'),
    path('payroll/bulk/save/', bulk_payroll_save, name='finance_bulk_payroll_save'),
    path('payroll/auto-save-row/', auto_save_payroll_row, name='finance_auto_save_payroll_row'),

    path('payroll/annual/', annual_payroll_list_view, name='finance_annual_payroll_list'),
    path('payroll/annual/<int:structure_id>/detail', annual_payroll_detail_view, name='finance_annual_payroll_detail'),
    path('payroll/annual/<int:structure_id>/pdf/', download_annual_payslip_pdf,
         name='finance_annual_payslip_pdf'),

    path('payroll/reports/', salary_management_report_view, name='finance_salary_management_report'),
    path('payroll/reports/pdf/', download_salary_report_pdf, name='finance_salary_report_pdf'),
    path('payroll/bank-payment-export/', bank_payment_export_view, name='finance_bank_payment_export'),
    path('payroll/bank-payment-export/download/', download_bank_payment_excel, name='finance_bank_payment_download'),

    path('bonus/', BonusListView.as_view(), name='finance_bonus_list'),
    path('bonus/create/', BonusCreateView.as_view(), name='finance_bonus_create'),
    path('bonus/<int:pk>/', BonusDetailView.as_view(), name='finance_bonus_detail'),
    path('bonus/<int:pk>/edit/', BonusUpdateView.as_view(), name='finance_bonus_update'),
    path('bonus/<int:pk>/delete/', BonusDeleteView.as_view(), name='finance_bonus_delete'),
    path('bonus/<int:pk>/mark-paid/', mark_bonus_as_paid_view, name='finance_bonus_mark_as_paid'),
    path('bonus/report/', bonus_report_view, name='finance_bonus_report'),
    path('bonus/report/pdf/', bonus_report_pdf_view, name='finance_bonus_report_pdf'),
    path('bonus/staff-search/', staff_search_view, name='finance_bonus_staff_search'),

    # Staff Payroll URLs
    path('staff/my-payroll/monthly/', staff_monthly_payroll_view, name='staff_monthly_payroll'),
    path('staff/my-payroll/annual/', staff_annual_payroll_view, name='staff_annual_payroll'),

    # Staff Bonus URLs
    path('staff/my-bonuses/', staff_bonus_list_view, name='staff_bonus_list'),
    path('staff/my-bonuses/<int:pk>/', staff_bonus_detail_view, name='staff_bonus_detail'),
]
