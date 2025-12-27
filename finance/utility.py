from decimal import Decimal
from django.db.models import Sum


class SalaryCalculator:
    """
    Service class to handle all salary calculations based on SalarySetting configuration.
    """

    def __init__(self, salary_structure, month, year):
        self.salary_structure = salary_structure
        self.salary_setting = salary_structure.salary_setting
        self.month = month
        self.year = year
        self.staff = salary_structure.staff

    def calculate_basic_components(self):
        """
        Calculate all basic salary components breakdown
        Returns: dict with component codes as keys
        """
        breakdown = {}
        monthly_salary = self.salary_structure.monthly_salary

        for key, component in self.salary_setting.basic_components.items():
            code = component.get('code', key.upper())
            name = component.get('name', key.title())
            percentage = Decimal(str(component.get('percentage', 0)))

            amount = (monthly_salary * percentage) / Decimal('100')

            breakdown[code] = {
                'name': name,
                'percentage': float(percentage),
                'amount': amount
            }

        return breakdown

    def calculate_allowances(self):
        """
        Calculate all allowances based on configuration
        Returns: dict with allowance names as keys
        """
        breakdown = {}
        basic_components = self.calculate_basic_components()

        for allowance in self.salary_setting.allowances:
            if not allowance.get('is_active', False):
                continue

            name = allowance.get('name', 'Unknown')
            calc_type = allowance.get('calculation_type', 'fixed')
            annual_only = allowance.get('annual_only', False)

            amount = Decimal('0.00')

            if calc_type == 'percentage':
                based_on = allowance.get('based_on', 'TOTAL')
                percentage = Decimal(str(allowance.get('percentage', 0)))

                if based_on == 'TOTAL':
                    base_amount = self.salary_structure.monthly_salary
                else:
                    # Calculate combined components (e.g., "B+H")
                    base_amount = self._calculate_combined_base(based_on, basic_components)

                amount = (base_amount * percentage) / Decimal('100')

                # If annual only, multiply by 12
                if annual_only:
                    amount = amount * 12

            elif calc_type == 'fixed':
                amount = Decimal(str(allowance.get('fixed_amount', 0)))

            breakdown[name] = {
                'calculation_type': calc_type,
                'amount': amount,
                'annual_only': annual_only
            }

        return breakdown

    def calculate_statutory_deductions(self):
        """
        Calculate statutory deductions (Pension, NHF, etc.)
        Returns: dict with deduction names as keys
        """
        breakdown = {}
        basic_components = self.calculate_basic_components()

        for deduction in self.salary_setting.statutory_deductions:
            if not deduction.get('is_active', True):
                continue

            name = deduction.get('name', 'Unknown')
            percentage = Decimal(str(deduction.get('percentage', 0)))
            based_on = deduction.get('based_on', 'B')  # Default to Basic

            # Calculate base amount from specified components
            base_amount = self._calculate_combined_base(based_on, basic_components)

            amount = (base_amount * percentage) / Decimal('100')

            breakdown[name] = {
                'percentage': float(percentage),
                'based_on': based_on,
                'amount': amount
            }

        return breakdown

    def calculate_other_deductions(self, custom_deductions=None):
        """
        Calculate other deductions (Loans, Advances, etc.)
        custom_deductions: dict with deduction names and amounts
        Returns: dict with deduction names as keys
        """
        breakdown = {}

        # Get auto-linked deductions (loans, advances)
        for deduction_config in self.salary_setting.other_deductions_config:
            name = deduction_config.get('name', 'Unknown')
            linked_to = deduction_config.get('linked_to', None)

            amount = Decimal('0.00')

            # Auto-calculate linked deductions
            if linked_to == 'staff_loan':
                amount = self._calculate_loan_deduction()
            elif linked_to == 'salary_advance':
                amount = self._calculate_advance_deduction()

            # Override with custom amount if provided
            if custom_deductions and name in custom_deductions:
                amount = Decimal(str(custom_deductions[name]))

            # Only add if amount > 0 or display rule is "always_show"
            display_rule = deduction_config.get('display_rule', 'show_if_filled')
            if amount > 0 or display_rule == 'always_show':
                breakdown[name] = {
                    'amount': amount,
                    'linked_to': linked_to
                }

        # Add any additional custom deductions not in config
        if custom_deductions:
            for name, amount in custom_deductions.items():
                if name not in breakdown:
                    breakdown[name] = {
                        'amount': Decimal(str(amount)),
                        'linked_to': None
                    }

        return breakdown

    def calculate_tax(self, annual_gross_income):
        """
        Calculate PAYE tax based on progressive tax brackets
        Returns: dict with tax breakdown
        """
        # Calculate total reliefs
        total_reliefs = self._calculate_reliefs(annual_gross_income)

        # Calculate taxable income
        taxable_income = max(annual_gross_income - total_reliefs, Decimal('0.00'))

        # Calculate tax using brackets
        annual_tax = Decimal('0.00')
        remaining_income = taxable_income
        tax_breakdown = []

        for bracket in self.salary_setting.tax_brackets:
            limit = bracket.get('limit', None)
            rate = Decimal(str(bracket.get('rate', 0)))

            if limit is None:
                # Final bracket - tax all remaining
                taxable_at_rate = remaining_income
            else:
                limit_decimal = Decimal(str(limit))
                taxable_at_rate = min(remaining_income, limit_decimal)

            if taxable_at_rate <= 0:
                break

            tax_at_rate = (taxable_at_rate * rate) / Decimal('100')
            annual_tax += tax_at_rate

            tax_breakdown.append({
                'limit': float(limit) if limit else None,
                'rate': float(rate),
                'taxable_amount': taxable_at_rate,
                'tax_amount': tax_at_rate
            })

            remaining_income -= taxable_at_rate

            if remaining_income <= 0:
                break

        monthly_tax = annual_tax / 12

        return {
            'annual_gross_income': annual_gross_income,
            'total_reliefs': total_reliefs,
            'taxable_income': taxable_income,
            'annual_tax': annual_tax,
            'monthly_tax': monthly_tax,
            'tax_breakdown': tax_breakdown
        }

    def calculate_complete_salary(self, bonus=Decimal('0.00'), custom_deductions=None,
                                  additional_income=None, other_taxes=Decimal('0.00')):
        """
        Calculate complete salary record with all components
        Returns: dict with all salary information
        """
        # Basic components
        basic_components = self.calculate_basic_components()

        # Allowances
        allowances = self.calculate_allowances()

        # Calculate monthly and annual totals
        monthly_salary = self.salary_structure.monthly_salary
        annual_salary = monthly_salary * 12

        # Total allowances
        total_monthly_allowances = sum(
            a['amount'] for a in allowances.values()
            if not a.get('annual_only', False)
        )
        total_annual_allowances = sum(
            a['amount'] for a in allowances.values()
            if a.get('annual_only', False)
        )

        # Additional income items
        additional_income_dict = additional_income or {}
        total_additional_income = sum(
            Decimal(str(v)) for v in additional_income_dict.values()
        )

        # Total income (Section A)
        total_income = (
                monthly_salary +
                total_monthly_allowances +
                total_additional_income +
                bonus
        )

        # Gross salary for tax calculation
        gross_for_tax = monthly_salary + total_monthly_allowances
        annual_gross = (gross_for_tax * 12) + total_annual_allowances

        # Tax calculation
        tax_info = self.calculate_tax(annual_gross)

        # Statutory deductions (Section B)
        statutory_deductions = self.calculate_statutory_deductions()
        total_statutory = sum(s['amount'] for s in statutory_deductions.values())

        # Other deductions (Section C)
        other_deductions = self.calculate_other_deductions(custom_deductions)
        total_other_deductions = sum(o['amount'] for o in other_deductions.values())

        # Taxation (Section D)
        total_taxation = tax_info['monthly_tax'] + other_taxes

        # Net salary (Take Home)
        net_salary = (
                total_income -
                total_statutory -
                total_other_deductions -
                total_taxation
        )

        # Effective tax rate
        effective_tax_rate = Decimal('0.00')
        if monthly_salary > 0:
            effective_tax_rate = (tax_info['monthly_tax'] / monthly_salary) * 100

        return {
            'monthly_salary': monthly_salary,
            'annual_salary': annual_salary,
            'basic_components_breakdown': basic_components,
            'allowances_breakdown': allowances,
            'additional_income': additional_income_dict,
            'bonus': bonus,
            'total_income': total_income,
            'gross_salary': gross_for_tax,
            'statutory_deductions': statutory_deductions,
            'total_statutory_deductions': total_statutory,
            'other_deductions': other_deductions,
            'total_other_deductions': total_other_deductions,
            'annual_gross_income': tax_info['annual_gross_income'],
            'total_reliefs': tax_info['total_reliefs'],
            'taxable_income': tax_info['taxable_income'],
            'annual_tax': tax_info['annual_tax'],
            'monthly_tax': tax_info['monthly_tax'],
            'other_taxes': other_taxes,
            'total_taxation': total_taxation,
            'effective_tax_rate': effective_tax_rate,
            'net_salary': net_salary
        }

    def _calculate_combined_base(self, component_codes, basic_components):
        """
        Calculate combined base amount from component codes
        e.g., "B+H+T" returns sum of Basic + Housing + Transport
        """
        if isinstance(component_codes, list):
            codes = component_codes
        else:
            codes = [code.strip() for code in str(component_codes).split('+')]

        total = Decimal('0.00')
        for code in codes:
            if code in basic_components:
                total += basic_components[code]['amount']

        return total

    def _calculate_reliefs(self, annual_gross_income):
        """Calculate total tax reliefs and exemptions"""

        total_reliefs = Decimal('0.00')

        for relief in self.salary_setting.reliefs_exemptions:
            if not relief.get('is_active', True):
                continue

            formula_type = relief.get('formula_type', 'fixed')

            if formula_type == 'percentage_plus_fixed':
                percentage = Decimal(str(relief.get('percentage', 0)))
                fixed_amount = Decimal(str(relief.get('fixed_amount', 0)))
                based_on = relief.get('based_on', 'gross_income')

                if based_on == 'gross_income':
                    base = annual_gross_income
                else:
                    base = annual_gross_income  # Default

                relief_amount = (base * percentage / 100) + fixed_amount

            elif formula_type == 'percentage':
                percentage = Decimal(str(relief.get('percentage', 0)))
                based_on = relief.get('based_on', 'gross_income')

                # For percentage of specific components (like Pension from B+H+T)
                if '+' in str(based_on):
                    basic_components = self.calculate_basic_components()
                    base = self._calculate_combined_base(based_on, basic_components) * 12
                else:
                    base = annual_gross_income

                relief_amount = base * percentage / 100

            elif formula_type == 'fixed':
                relief_amount = Decimal(str(relief.get('fixed_amount', 0)))

            else:
                relief_amount = Decimal('0.00')

            total_reliefs += relief_amount

        # ADD THIS SECTION - Add statutory deductions to reliefs
        statutory_deductions = self.calculate_statutory_deductions()
        annual_statutory = sum(s['amount'] for s in statutory_deductions.values()) * 12
        total_reliefs += annual_statutory

        return total_reliefs

    def _calculate_loan_deduction(self):
        """Calculate total loan deduction for this month"""
        from .models import StaffLoan  # Import here to avoid circular import

        # Get all disbursed loans with outstanding balance
        loans = StaffLoan.objects.filter(
            staff=self.staff,
            status=StaffLoan.Status.DISBURSED
        )

        total_deduction = Decimal('0.00')
        for loan in loans:
            if loan.balance > 0:
                # You can implement a repayment plan logic here
                # For now, we'll just track the balance
                total_deduction += loan.balance

        return total_deduction

    def _calculate_advance_deduction(self):
        """Calculate total salary advance deduction for this month"""
        from .models import SalaryAdvance  # Import here to avoid circular import

        # Get advances for this specific month
        advances = SalaryAdvance.objects.filter(
            staff=self.staff,
            status=SalaryAdvance.Status.DISBURSED,
            request_date__year=self.year,
            request_date__month=self.month
        )

        total_advance = advances.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

        return total_advance


def create_salary_record(salary_structure, month, year, bonus=Decimal('0.00'),
                         custom_deductions=None, additional_income=None,
                         other_taxes=Decimal('0.00'), created_by=None):
    """
    Helper function to create a complete SalaryRecord
    """
    from .models import SalaryRecord  # Import here to avoid circular import

    calculator = SalaryCalculator(salary_structure, month, year)
    salary_data = calculator.calculate_complete_salary(
        bonus=bonus,
        custom_deductions=custom_deductions,
        additional_income=additional_income,
        other_taxes=other_taxes
    )

    # Create the salary record
    record = SalaryRecord.objects.create(
        staff=salary_structure.staff,
        salary_structure=salary_structure,
        salary_setting=salary_structure.salary_setting,
        month=month,
        year=year,
        monthly_salary=salary_data['monthly_salary'],
        annual_salary=salary_data['annual_salary'],
        basic_components_breakdown=salary_data['basic_components_breakdown'],
        allowances_breakdown=salary_data['allowances_breakdown'],
        additional_income=salary_data['additional_income'],
        bonus=salary_data['bonus'],
        total_income=salary_data['total_income'],
        gross_salary=salary_data['gross_salary'],
        statutory_deductions=salary_data['statutory_deductions'],
        total_statutory_deductions=salary_data['total_statutory_deductions'],
        other_deductions=salary_data['other_deductions'],
        total_other_deductions=salary_data['total_other_deductions'],
        annual_gross_income=salary_data['annual_gross_income'],
        total_reliefs=salary_data['total_reliefs'],
        taxable_income=salary_data['taxable_income'],
        annual_tax=salary_data['annual_tax'],
        monthly_tax=salary_data['monthly_tax'],
        other_taxes=salary_data['other_taxes'],
        total_taxation=salary_data['total_taxation'],
        effective_tax_rate=salary_data['effective_tax_rate'],
        net_salary=salary_data['net_salary'],
        created_by=created_by
    )

    return record