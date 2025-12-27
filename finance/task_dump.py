#
# # ============================================================================
# # PAYROLL DASHBOARD
# # ============================================================================
#
# @login_required
# @permission_required('finance.view_salaryrecord', raise_exception=True)
# def payroll_dashboard_view(request):
#     """Main payroll dashboard with statistics"""
#     today = datetime.now()
#     current_year = int(request.GET.get('year', today.year))
#     current_month = int(request.GET.get('month', today.month))
#
#     # Get salary records for current period
#     records = SalaryRecord.objects.filter(
#         year=current_year,
#         month=current_month
#     ).select_related('staff__staff_profile__user')
#
#     # Calculate statistics
#     total_staff = records.count()
#     paid_records = records.filter(payment_status=SalaryRecord.PaymentStatus.PAID)
#     unpaid_records = records.exclude(payment_status=SalaryRecord.PaymentStatus.PAID)
#
#     total_paid = paid_records.count()
#     total_unpaid = unpaid_records.count()
#
#     total_expected = sum(r.net_salary for r in records)
#     total_paid_amount = sum(r.amount_paid for r in paid_records)
#
#     # Staff with active structures but no record for this month
#     staff_with_structures = StaffModel.objects.filter(
#         salary_structures__is_active=True
#     ).distinct()
#
#     staff_ids_with_records = set(records.values_list('staff_id', flat=True))
#     staff_not_processed = staff_with_structures.exclude(id__in=staff_ids_with_records)
#
#     # Get month name
#     import calendar
#     month_name = calendar.month_name[current_month]
#
#     context = {
#         'current_year': current_year,
#         'current_month': current_month,
#         'month_name': month_name,
#         'total_staff': total_staff,
#         'total_paid': total_paid,
#         'total_unpaid': total_unpaid,
#         'total_expected': total_expected,
#         'total_paid_amount': total_paid_amount,
#         'paid_records': paid_records,
#         'unpaid_records': unpaid_records,
#         'staff_not_processed': staff_not_processed,
#         'years': range(2020, today.year + 2),
#         'months': [(i, calendar.month_name[i]) for i in range(1, 13)],
#         'page_title': f'Payroll Dashboard - {month_name} {current_year}'
#     }
#     return render(request, 'finance/payroll/dashboard.html', context)
#
#
# # ============================================================================
# # BULK PROCESS PAYROLL
# # ============================================================================
#
# @login_required
# @permission_required('finance.add_salaryrecord', raise_exception=True)
# def process_payroll_bulk_view(request):
#     """Bulk create salary records for staff"""
#     today = datetime.now()
#     year = int(request.GET.get('year', today.year))
#     month = int(request.GET.get('month', today.month))
#
#     # Get staff with active structures but no record for this month
#     # FIXED: Changed select_related to prefetch_related for reverse FK
#     staff_with_structures = StaffModel.objects.filter(
#         salary_structures__is_active=True
#     ).prefetch_related('salary_structures__salary_setting').distinct()
#
#     existing_records = SalaryRecord.objects.filter(
#         year=year, month=month
#     ).values_list('staff_id', flat=True)
#
#     staff_to_process = staff_with_structures.exclude(id__in=existing_records)
#
#     if request.method == 'POST':
#         selected_ids = request.POST.getlist('selected_staff')
#         mark_as_paid = request.POST.get('mark_as_paid') == 'on'
#
#         if not selected_ids:
#             messages.warning(request, 'No staff selected.')
#             return redirect(request.path + f'?year={year}&month={month}')
#
#         created_count = 0
#         for staff_id in selected_ids:
#             try:
#                 staff = StaffModel.objects.get(id=staff_id)
#                 structure = staff.salary_structures.filter(is_active=True).first()
#
#                 if not structure:
#                     continue
#
#                 # Create salary record using the helper function
#                 record = create_salary_record(
#                     salary_structure=structure,
#                     month=month,
#                     year=year,
#                     created_by=request.user
#                 )
#
#                 # Mark as paid if requested
#                 if mark_as_paid:
#                     record.payment_status = SalaryRecord.PaymentStatus.PAID
#                     record.paid_date = date.today()
#                     record.paid_by = request.user
#
#                 created_count += 1
#                 record.amount_paid = record.net_salary
#                 record.save()
#
#             except Exception as e:
#                 messages.error(request, f'Error processing {staff}: {str(e)}')
#
#         messages.success(request, f'Successfully processed {created_count} salary records.')
#         return redirect(reverse('finance_payroll_dashboard') + f'?year={year}&month={month}')
#
#     import calendar
#     context = {
#         'staff_to_process': staff_to_process,
#         'year': year,
#         'month': month,
#         'month_name': calendar.month_name[month],
#         'years': range(2020, today.year + 2),
#         'months': [(i, calendar.month_name[i]) for i in range(1, 13)],
#         'page_title': 'Bulk Process Payroll'
#     }
#     return render(request, 'finance/payroll/bulk_process.html', context)
#
#
# def create_salary_record(salary_structure, month, year, created_by=None, bonus=0, custom_deductions=None,
#                          other_taxes=0):
#     """
#     Helper function to create a salary record from a salary structure.
#     This uses the same calculation logic as the salary structure detail view.
#     """
#     from decimal import Decimal
#
#     # Use the same calculation function from salary structure detail
#     calculation = calculate_salary_breakdown(salary_structure)
#
#     # Get the current session and term
#     setting = SchoolSettingModel.objects.first()
#     session = setting.session if setting else None
#     term = setting.term if setting else None
#
#     # Add bonus if provided
#     bonus_amount = Decimal(str(bonus)) if bonus else Decimal('0.00')
#
#     # Calculate custom deductions total
#     custom_deductions = custom_deductions or {}
#     total_custom_deductions = sum(Decimal(str(v)) for v in custom_deductions.values())
#
#     # Add other taxes
#     other_taxes_amount = Decimal(str(other_taxes)) if other_taxes else Decimal('0.00')
#
#     # Calculate final totals
#     total_income = Decimal(str(calculation['gross_income_monthly'])) + bonus_amount
#     total_taxation = Decimal(str(calculation['monthly_tax'])) + other_taxes_amount
#     total_other_deductions = Decimal(str(calculation.get('total_statutory_deductions', 0))) + total_custom_deductions
#     net_salary = total_income - total_taxation - total_other_deductions
#
#     # Create the salary record
#     record = SalaryRecord.objects.create(
#         staff=salary_structure.staff,
#         salary_structure=salary_structure,
#         salary_setting=salary_structure.salary_setting,
#         month=month,
#         year=year,
#         session=session,
#         term=term,
#
#         # Core salary snapshot
#         monthly_salary=salary_structure.monthly_salary,
#         annual_salary=salary_structure.annual_salary,
#
#         # Basic components breakdown
#         basic_components_breakdown=calculation['basic_components'],
#
#         # Allowances breakdown
#         allowances_breakdown={
#             'leave_allowance': {
#                 'monthly': float(calculation['leave_allowance_monthly']),
#                 'annual': float(calculation['leave_allowance_annual']),
#                 'percentage': float(calculation['leave_allowance_percentage'])
#             },
#             'other_allowances': calculation['allowances']
#         },
#
#         # Bonus
#         bonus=bonus_amount,
#
#         # Calculated totals
#         total_income=total_income,
#         gross_salary=Decimal(str(calculation['gross_income_monthly'])),
#
#         # Statutory deductions
#         statutory_deductions={
#             'details': calculation.get('statutory_deductions', []),
#             'total': float(calculation.get('total_statutory_deductions', 0))
#         },
#         total_statutory_deductions=Decimal(str(calculation.get('total_statutory_deductions', 0))),
#
#         # Other deductions
#         other_deductions=custom_deductions,
#         total_other_deductions=total_other_deductions,
#
#         # Tax calculation
#         annual_gross_income=Decimal(str(calculation['gross_income_annual'])),
#         total_reliefs=Decimal(str(calculation['total_reliefs'])),
#         taxable_income=Decimal(str(calculation['taxable_income'])),
#         annual_tax=Decimal(str(calculation['annual_tax'])),
#         monthly_tax=Decimal(str(calculation['monthly_tax'])),
#         other_taxes=other_taxes_amount,
#         total_taxation=total_taxation,
#         effective_tax_rate=Decimal(str(calculation['effective_tax_rate'])),
#
#         # Net salary
#         net_salary=net_salary,
#
#         # Payment status
#         payment_status=SalaryRecord.PaymentStatus.NOT_PROCESSED,
#
#         # Creator
#         created_by=created_by
#     )
#
#     return record
#
#
# # ============================================================================
# # PAYROLL GRID VIEW (Excel-like editing)
# # ============================================================================
#
# @login_required
# @permission_required('finance.view_salaryrecord', raise_exception=True)
# def process_payroll_grid_view(request):
#     """Excel-like grid for editing multiple salary records"""
#     from decimal import Decimal
#     from datetime import datetime, date
#     import calendar
#     import json
#
#     today = datetime.now()
#     year = int(request.GET.get('year', today.year))
#     month = int(request.GET.get('month', today.month))
#
#     records = SalaryRecord.objects.filter(
#         year=year, month=month
#     ).select_related(
#         'staff__staff_profile__user',
#         'salary_setting',
#         'salary_structure'
#     ).order_by('staff__staff_id')
#
#     if request.method == 'POST':
#         # Helper function to convert Decimals in nested structures
#         def convert_decimals(obj):
#             if isinstance(obj, Decimal):
#                 return str(obj)
#             elif isinstance(obj, dict):
#                 return {k: convert_decimals(v) for k, v in obj.items()}
#             elif isinstance(obj, list):
#                 return [convert_decimals(item) for item in obj]
#             return obj
#
#         # Process bulk updates
#         for record in records:
#             # Get form values
#             bonus = request.POST.get(f'bonus_{record.id}', '0')
#             other_taxes = request.POST.get(f'other_taxes_{record.id}', '0')
#             amount_paid = request.POST.get(f'amount_paid_{record.id}', '0')
#             notes = request.POST.get(f'notes_{record.id}', '')
#
#             # Update record with Decimal values
#             record.bonus = Decimal(bonus) if bonus else Decimal('0')
#             record.other_taxes = Decimal(other_taxes) if other_taxes else Decimal('0')
#             record.amount_paid = Decimal(amount_paid) if amount_paid else Decimal('0')
#             record.notes = notes.strip()
#
#             # Handle custom deductions
#             custom_deductions = {}
#             if record.salary_setting.other_deductions_config:
#                 for ded_config in record.salary_setting.other_deductions_config:
#
#                     if not ded_config.get('linked_to'):  # Only handle manual deductions
#                         ded_name = ded_config['name']
#                         ded_key = f"ded_{ded_name.lower().replace(' ', '')}_{record.id}"
#
#                         ded_value = request.POST.get(ded_key, '0')
#                         custom_deductions[ded_name] = Decimal(ded_value) if ded_value else Decimal('0')
#
#             # Handle additional income items
#             additional_income = {}
#             if record.salary_setting.income_items:
#                 for income_config in record.salary_setting.income_items:
#                     income_name = income_config['name']
#                     income_key = f"inc_{income_name.lower().replace(' ', '_')}_{record.id}"
#                     income_value = request.POST.get(income_key, '0')
#                     additional_income[income_name] = Decimal(income_value) if income_value else Decimal('0')
#
#             # Recalculate salary using SalaryCalculator
#             calculator = SalaryCalculator(record.salary_structure, month, year)
#             salary_data = calculator.calculate_complete_salary(
#                 bonus=record.bonus,
#                 custom_deductions=custom_deductions,
#                 other_taxes=record.other_taxes,
#                 additional_income=additional_income
#             )
#
#             # Update calculated fields with proper type conversion
#             record.other_deductions = convert_decimals(salary_data.get('other_deductions', {}))
#             record.total_other_deductions = Decimal(salary_data.get('total_other_deductions', '0'))
#             record.total_taxation = Decimal(salary_data.get('total_taxation', '0'))
#             record.net_salary = Decimal(salary_data.get('net_salary', '0'))
#
#             # Update tax-related fields
#             record.annual_gross_income = Decimal(salary_data.get('annual_gross_income', '0'))
#             record.total_reliefs = Decimal(salary_data.get('total_reliefs', '0'))
#             record.taxable_income = Decimal(salary_data.get('taxable_income', '0'))
#             record.annual_tax = Decimal(salary_data.get('annual_tax', '0'))
#             record.monthly_tax = Decimal(salary_data.get('monthly_tax', '0'))
#             record.effective_tax_rate = Decimal(salary_data.get('effective_tax_rate', '0'))
#
#             # Update income fields
#             record.total_income = Decimal(salary_data.get('total_income', '0'))
#             record.gross_salary = Decimal(salary_data.get('gross_salary', '0'))
#
#             # Update statutory deductions
#             record.statutory_deductions = convert_decimals(salary_data.get('statutory_deductions', {}))
#             record.total_statutory_deductions = Decimal(salary_data.get('total_statutory_deductions', '0'))
#
#             # Update additional income
#             record.additional_income = convert_decimals(additional_income)
#
#             # Save the record (this will trigger the save method that updates payment status)
#             record.save()
#
#         # Handle mark as paid
#         paid_ids = request.POST.getlist('mark_as_paid')
#         if paid_ids:
#             SalaryRecord.objects.filter(id__in=paid_ids).update(
#                 payment_status=SalaryRecord.PaymentStatus.PAID,
#                 paid_date=date.today(),
#                 paid_by=request.user
#             )
#
#             # For records marked as paid with zero amount, set amount to net salary
#             for record_id in paid_ids:
#                 record = SalaryRecord.objects.get(id=record_id)
#                 if record.amount_paid == 0:
#                     record.amount_paid = record.net_salary
#                     record.save()
#
#         messages.success(request, f'Payroll for {calendar.month_name[month]} {year} updated successfully!')
#         return redirect(request.path + f'?year={year}&month={month}')
#
#     # Prepare context for GET request
#     context = {
#         'records': records,
#         'year': year,
#         'month': month,
#         'month_name': calendar.month_name[month],
#         'years': range(2020, today.year + 2),
#         'months': [(i, calendar.month_name[i]) for i in range(1, 13)],
#         'page_title': f'Payroll Grid - {calendar.month_name[month]} {year}'
#     }
#     return render(request, 'finance/payroll/grid_view.html', context)
#
# # ============================================================================
# # INDIVIDUAL SALARY RECORD
# # ============================================================================
#
# @login_required
# @permission_required('finance.view_salaryrecord', raise_exception=True)
# def salary_record_detail_view(request, pk):
#     """View and edit individual salary record"""
#     record = get_object_or_404(
#         SalaryRecord.objects.select_related(
#             'staff__staff_profile__user', 'salary_structure', 'salary_setting'
#         ),
#         pk=pk
#     )
#
#     if request.method == 'POST':
#         action = request.POST.get('action')
#
#         if action == 'mark_paid' and request.user.has_perm('finance.change_salaryrecord'):
#             record.amount_paid = record.net_salary
#             record.payment_status = SalaryRecord.PaymentStatus.PAID
#             record.paid_date = date.today()
#             record.paid_by = request.user
#             record.save()
#             messages.success(request, 'Salary marked as paid.')
#
#         return redirect('finance_salary_record_detail', pk=pk)
#
#     context = {
#         'record': record,
#         'page_title': f'Salary Record: {record.staff} - {record.month_name} {record.year}'
#     }
#     return render(request, 'finance/payroll/record_detail.html', context)
#
#
# # ============================================================================
# # EXPORT FUNCTIONS
# # ============================================================================
#
# @login_required
# @permission_required('finance.view_salaryrecord')
# def export_payroll_excel_view(request, year, month):
#     """Export payroll to Excel"""
#     records = SalaryRecord.objects.filter(
#         year=year, month=month
#     ).select_related('staff__staff_profile__user').order_by('staff__staff_id')
#
#     # Create workbook
#     wb = openpyxl.Workbook()
#     ws = wb.active
#     import calendar
#     ws.title = f'{calendar.month_name[month]} {year}'
#
#     # Headers
#     headers = [
#         'Staff ID', 'Staff Name', 'Monthly Salary', 'Bonus',
#         'Total Income', 'Statutory Deductions', 'Other Deductions',
#         'PAYE', 'Other Taxes', 'Net Salary', 'Amount Paid', 'Status'
#     ]
#
#     for col, header in enumerate(headers, 1):
#         cell = ws.cell(row=1, column=col, value=header)
#         cell.font = Font(bold=True)
#         cell.fill = PatternFill(start_color='CCCCCC', end_color='CCCCCC', fill_type='solid')
#
#     # Data rows
#     for row_num, record in enumerate(records, 2):
#         ws.cell(row=row_num, column=1, value=record.staff.staff_id)
#         ws.cell(row=row_num, column=2, value=str(record.staff))
#         ws.cell(row=row_num, column=3, value=float(record.monthly_salary))
#         ws.cell(row=row_num, column=4, value=float(record.bonus))
#         ws.cell(row=row_num, column=5, value=float(record.total_income))
#         ws.cell(row=row_num, column=6, value=float(record.total_statutory_deductions))
#         ws.cell(row=row_num, column=7, value=float(record.total_other_deductions))
#         ws.cell(row=row_num, column=8, value=float(record.monthly_tax))
#         ws.cell(row=row_num, column=9, value=float(record.other_taxes))
#         ws.cell(row=row_num, column=10, value=float(record.net_salary))
#         ws.cell(row=row_num, column=11, value=float(record.amount_paid))
#         ws.cell(row=row_num, column=12, value=record.payment_status)
#
#     # Create response
#     response = HttpResponse(
#         content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
#     )
#     response['Content-Disposition'] = f'attachment; filename="payroll_{year}_{month}.xlsx"'
#     wb.save(response)
#
#     return response
#
#
# # ============================================================================
# # STAFF PORTAL
# # ============================================================================
#
# @login_required
# def staff_salary_portal_view(request):
#     """Staff view their own salary records"""
#     # Get staff record
#     try:
#         staff = request.user.staff_profile.staff
#     except:
#         messages.error(request, 'No staff record found for your account.')
#         return redirect('home')
#
#     # Get salary records
#     records = SalaryRecord.objects.filter(staff=staff).order_by('-year', '-month')
#
#     # Get current structure
#     current_structure = staff.salary_structures.filter(is_active=True).first()
#
#     context = {
#         'staff': staff,
#         'records': records,
#         'current_structure': current_structure,
#         'page_title': 'My Salary'
#     }
#     return render(request, 'finance/staff_portal/my_salary.html', context)