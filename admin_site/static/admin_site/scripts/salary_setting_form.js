// salary_setting_form.js - Save this in your static/js/ directory
// Completed version — loads existing data, wires buttons, validates before submit.

document.addEventListener('DOMContentLoaded', function() {
    // Containers
    const basicComponentsContainer = document.getElementById('basicComponentsContainer');
    const allowancesContainer = document.getElementById('allowancesContainer');
    const reliefsContainer = document.getElementById('reliefsContainer');
    const taxBracketsContainer = document.getElementById('taxBracketsContainer');
    const statutoryDeductionsContainer = document.getElementById('statutoryDeductionsContainer');
    const otherDeductionsContainer = document.getElementById('otherDeductionsContainer');
    const incomeItemsContainer = document.getElementById('incomeItemsContainer');

    // Hidden inputs
    const hiddenBasicComponents = document.getElementById('id_basic_components_json');
    const hiddenAllowances = document.getElementById('id_allowances_json');
    const hiddenReliefs = document.getElementById('id_reliefs_exemptions_json');
    const hiddenTaxBrackets = document.getElementById('id_tax_brackets_json');
    const hiddenIncomeItems = document.getElementById('id_income_items_json');
    const hiddenStatutoryDeductions = document.getElementById('id_statutory_deductions_json');
    const hiddenOtherDeductions = document.getElementById('id_other_deductions_config_json');

    // Buttons
    const addBasicComponentBtn = document.getElementById('addBasicComponentBtn');
    const addAllowanceBtn = document.getElementById('addAllowanceBtn');
    const addReliefBtn = document.getElementById('addReliefBtn');
    const addTaxBracketBtn = document.getElementById('addTaxBracketBtn');
    const addStatutoryDeductionBtn = document.getElementById('addStatutoryDeductionBtn');
    const addOtherDeductionBtn = document.getElementById('addOtherDeductionBtn');
    const addIncomeItemBtn = document.getElementById('addIncomeItemBtn');

    // Error modal
    const errorModalEl = document.getElementById('errorModal');
    const errorModal = errorModalEl ? new bootstrap.Modal(errorModalEl) : null;
    const errorModalMessage = document.getElementById('errorModalMessage');

    // Form
    const salarySettingForm = document.getElementById('salarySettingForm');

    let componentCounter = 0;

    // Utility function to show error
    function showError(message) {
        if (errorModal && errorModalMessage) {
            errorModalMessage.textContent = message;
            errorModal.show();
        } else {
            alert(message);
        }
    }

    // ========================================
    // BASIC COMPONENTS
    // ========================================
    function addBasicComponent(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control comp-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Name *</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control comp-code" placeholder="Code" value="${escapeHtml(data?.code || '')}">
                        <label>Code *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <input type="number" class="form-control comp-percentage" step="0.01" min="0" max="100"
                               placeholder="%" value="${data?.percentage ?? ''}">
                        <label>Percentage % *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <small class="text-muted d-block mb-2">Current: <strong class="comp-amount">₦0.00</strong></small>
                    <small class="text-muted">Example based on ₦500,000 salary</small>
                </div>
                <div class="col-md-1">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove component">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>
        `;

        basicComponentsContainer.appendChild(item);
        attachBasicComponentEvents(item);
        updateBasicComponentsJSON();
    }

    function attachBasicComponentEvents(item) {
        const inputs = item.querySelectorAll('input');
        inputs.forEach(input => {
            input.addEventListener('input', updateBasicComponentsJSON);
            input.addEventListener('change', updateBasicComponentsJSON);
        });

        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                item.remove();
                updateBasicComponentsJSON();
            });
        }
    }

    function updateBasicComponentsJSON() {
        const components = {};
        let totalPercentage = 0;

        basicComponentsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.comp-name')?.value || '').trim();
            const code = (item.querySelector('.comp-code')?.value || '').trim();
            const percentage = parseFloat(item.querySelector('.comp-percentage')?.value) || 0;

            if (name && code) {
                const key = name.toLowerCase().replace(/\s+/g, '_');
                components[key] = {
                    code: code,
                    percentage: percentage,
                    name: name
                };
                totalPercentage += percentage;

                // Update example amount (based on 500,000 sample)
                const amount = (500000 * percentage) / 100;
                const amountEl = item.querySelector('.comp-amount');
                if (amountEl) {
                    amountEl.textContent = `₦${amount.toLocaleString('en-NG', {minimumFractionDigits: 2})}`;
                }
            } else {
                // If missing name or code, show 0.00 example
                const amountEl = item.querySelector('.comp-amount');
                if (amountEl) amountEl.textContent = `₦0.00`;
            }
        });

        // Update total percentage display
        const totalSpan = document.getElementById('totalPercentage');
        totalSpan.textContent = totalPercentage.toFixed(2);

        if (Math.abs(totalPercentage - 100) < 0.01) {
            totalSpan.className = 'percentage-valid';
        } else {
            totalSpan.className = 'percentage-invalid';
        }

        hiddenBasicComponents.value = JSON.stringify(components, null, 2);
        updateContainerState(basicComponentsContainer);
    }

    // ========================================
    // ALLOWANCES
    // ========================================
    function addAllowance(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row">
                <div class="col-md-4">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control allow-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Allowance Name *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <select class="form-control allow-calc-type">
                            <option value="percentage" ${data?.calculation_type === 'percentage' ? 'selected' : ''}>Percentage</option>
                            <option value="fixed" ${data?.calculation_type === 'fixed' ? 'selected' : ''}>Fixed Amount</option>
                        </select>
                        <label>Calculation Type</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-check mt-3">
                        <input type="checkbox" class="form-check-input allow-active" ${data?.is_active !== false ? 'checked' : ''}>
                        <label class="form-check-label">Active</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-check mt-3">
                        <input type="checkbox" class="form-check-input allow-annual" ${data?.annual_only ? 'checked' : ''}>
                        <label class="form-check-label">Annual Only</label>
                    </div>
                </div>
                <div class="col-md-1">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove allowance">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>

            <div class="percentage-fields" style="display: ${data?.calculation_type === 'fixed' ? 'none' : 'block'};">
                <div class="row">
                    <div class="col-md-4">
                        <div class="form-floating mb-2">
                            <input type="number" class="form-control allow-percentage" step="0.01" min="0"
                                   placeholder="%" value="${data?.percentage ?? ''}">
                            <label>Percentage %</label>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="form-floating mb-2">
                            <input type="text" class="form-control allow-based-on" placeholder="Based On"
                                   value="${escapeHtml(data?.based_on || 'TOTAL')}">
                            <label>Based On (e.g., B, B+H, TOTAL)</label>
                        </div>
                    </div>
                </div>
            </div>

            <div class="fixed-fields" style="display: ${data?.calculation_type === 'fixed' ? 'block' : 'none'};">
                <div class="row">
                    <div class="col-md-6">
                        <div class="form-floating mb-2">
                            <input type="number" class="form-control allow-fixed-amount" step="0.01" min="0"
                                   placeholder="Amount" value="${data?.fixed_amount ?? ''}">
                            <label>Fixed Amount (₦)</label>
                        </div>
                    </div>
                </div>
            </div>
        `;

        allowancesContainer.appendChild(item);
        attachAllowanceEvents(item);
        updateAllowancesJSON();
    }

    function attachAllowanceEvents(item) {
        const calcType = item.querySelector('.allow-calc-type');
        const percentageFields = item.querySelector('.percentage-fields');
        const fixedFields = item.querySelector('.fixed-fields');

        calcType.addEventListener('change', function() {
            percentageFields.style.display = this.value === 'percentage' ? 'block' : 'none';
            fixedFields.style.display = this.value === 'fixed' ? 'block' : 'none';
            updateAllowancesJSON();
        });

        const inputs = item.querySelectorAll('input, select');
        inputs.forEach(input => {
            input.addEventListener('input', updateAllowancesJSON);
            input.addEventListener('change', updateAllowancesJSON);
        });

        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                item.remove();
                updateAllowancesJSON();
            });
        }
    }

    function updateAllowancesJSON() {
        const allowances = [];

        allowancesContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.allow-name')?.value || '').trim();
            if (!name) return;

            const allowance = {
                name: name,
                is_active: !!item.querySelector('.allow-active')?.checked,
                calculation_type: item.querySelector('.allow-calc-type')?.value || 'percentage',
                annual_only: !!item.querySelector('.allow-annual')?.checked
            };

            if (allowance.calculation_type === 'percentage') {
                const percentage = parseFloat(item.querySelector('.allow-percentage')?.value);
                const basedOn = (item.querySelector('.allow-based-on')?.value || '').trim();
                if (!isNaN(percentage)) allowance.percentage = percentage;
                if (basedOn) allowance.based_on = basedOn;
            } else {
                const fixedAmount = parseFloat(item.querySelector('.allow-fixed-amount')?.value);
                if (!isNaN(fixedAmount)) allowance.fixed_amount = fixedAmount;
            }

            allowances.push(allowance);
        });

        hiddenAllowances.value = JSON.stringify(allowances, null, 2);
        updateContainerState(allowancesContainer);
    }

    // ========================================
    // TAX RELIEFS
    // ========================================
    function addRelief(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row">
                <div class="col-md-4">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control relief-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Relief Name *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <select class="form-control relief-formula-type">
                            <option value="percentage_plus_fixed" ${data?.formula_type === 'percentage_plus_fixed' ? 'selected' : ''}>Percentage + Fixed</option>
                            <option value="percentage" ${data?.formula_type === 'percentage' ? 'selected' : ''}>Percentage Only</option>
                            <option value="fixed" ${data?.formula_type === 'fixed' ? 'selected' : ''}>Fixed Only</option>
                        </select>
                        <label>Formula Type</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-check mt-3">
                        <input type="checkbox" class="form-check-input relief-active" ${data?.is_active !== false ? 'checked' : ''}>
                        <label class="form-check-label">Active</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove relief">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>

            <div class="relief-percentage-fields" style="display: ${data?.formula_type === 'fixed' ? 'none' : 'block'};">
                <div class="row">
                    <div class="col-md-4">
                        <div class="form-floating mb-2">
                            <input type="number" class="form-control relief-percentage" step="0.01" min="0"
                                   value="${data?.percentage ?? ''}">
                            <label>Percentage %</label>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="form-floating mb-2">
                            <input type="text" class="form-control relief-based-on"
                                   value="${escapeHtml(data?.based_on || 'gross_income')}">
                            <label>Based On</label>
                        </div>
                    </div>
                </div>
            </div>

            <div class="relief-fixed-fields" style="display: ${data?.formula_type === 'percentage' ? 'none' : 'block'};">
                <div class="row">
                    <div class="col-md-6">
                        <div class="form-floating mb-2">
                            <input type="number" class="form-control relief-fixed-amount" step="0.01" min="0"
                                   value="${data?.fixed_amount ?? ''}">
                            <label>Fixed Amount (₦)</label>
                        </div>
                    </div>
                </div>
            </div>
        `;

        reliefsContainer.appendChild(item);
        attachReliefEvents(item);
        updateReliefsJSON();
    }

    function attachReliefEvents(item) {
        const formulaType = item.querySelector('.relief-formula-type');
        const percentageFields = item.querySelector('.relief-percentage-fields');
        const fixedFields = item.querySelector('.relief-fixed-fields');

        formulaType.addEventListener('change', function() {
            percentageFields.style.display = this.value === 'percentage' ? 'block' : this.value === 'percentage_plus_fixed' ? 'block' : 'none';
            fixedFields.style.display = this.value === 'fixed' ? 'block' : this.value === 'percentage_plus_fixed' ? 'block' : 'none';
            updateReliefsJSON();
        });

        const inputs = item.querySelectorAll('input, select');
        inputs.forEach(input => {
            input.addEventListener('input', updateReliefsJSON);
            input.addEventListener('change', updateReliefsJSON);
        });

        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                item.remove();
                updateReliefsJSON();
            });
        }
    }

    function updateReliefsJSON() {
        const reliefs = [];

        reliefsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.relief-name')?.value || '').trim();
            if (!name) return;

            const relief = {
                name: name,
                is_active: !!item.querySelector('.relief-active')?.checked,
                formula_type: item.querySelector('.relief-formula-type')?.value || 'percentage_plus_fixed'
            };

            if (relief.formula_type !== 'fixed') {
                const percentage = parseFloat(item.querySelector('.relief-percentage')?.value);
                const basedOn = (item.querySelector('.relief-based-on')?.value || '').trim();
                if (!isNaN(percentage)) relief.percentage = percentage;
                if (basedOn) relief.based_on = basedOn;
            }

            if (relief.formula_type !== 'percentage') {
                const fixedAmount = parseFloat(item.querySelector('.relief-fixed-amount')?.value);
                if (!isNaN(fixedAmount)) relief.fixed_amount = fixedAmount;
            }

            reliefs.push(relief);
        });

        hiddenReliefs.value = JSON.stringify(reliefs, null, 2);
        updateContainerState(reliefsContainer);
    }

    // ========================================
    // TAX BRACKETS
    // ========================================
    function addTaxBracket(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row">
                <div class="col-md-5">
                    <div class="form-floating mb-2">
                        <input type="number" class="form-control bracket-limit" step="1" min="0"
                               placeholder="Limit" value="${data?.limit !== null && data?.limit !== undefined ? data.limit : ''}">
                        <label>Income Limit (₦) - Leave empty for remaining</label>
                    </div>
                </div>
                <div class="col-md-5">
                    <div class="form-floating mb-2">
                        <input type="number" class="form-control bracket-rate" step="0.01" min="0" max="100"
                               placeholder="Rate" value="${data?.rate ?? ''}">
                        <label>Tax Rate % *</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove bracket">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>
        `;

        taxBracketsContainer.appendChild(item);
        attachTaxBracketEvents(item);
        updateTaxBracketsJSON();
    }

    function attachTaxBracketEvents(item) {
        const inputs = item.querySelectorAll('input');
        inputs.forEach(input => {
            input.addEventListener('input', updateTaxBracketsJSON);
        });

        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                item.remove();
                updateTaxBracketsJSON();
            });
        }
    }

    function updateTaxBracketsJSON() {
        const brackets = [];

        taxBracketsContainer.querySelectorAll('.component-item').forEach(item => {
            const limitInput = (item.querySelector('.bracket-limit')?.value || '').trim();
            const rate = parseFloat(item.querySelector('.bracket-rate')?.value);

            if (!isNaN(rate)) {
                const bracket = {
                    limit: limitInput === '' ? null : parseFloat(limitInput),
                    rate: rate
                };
                brackets.push(bracket);
            }
        });

        hiddenTaxBrackets.value = JSON.stringify(brackets, null, 2);
        updateContainerState(taxBracketsContainer);
    }

    // ========================================
    // STATUTORY DEDUCTIONS
    // ========================================
    function addStatutoryDeduction(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row">
                <div class="col-md-4">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control stat-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Deduction Name *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <input type="number" class="form-control stat-percentage" step="0.01" min="0"
                               value="${data?.percentage ?? ''}">
                        <label>Percentage % *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control stat-based-on"
                               value="${escapeHtml(data?.based_on || 'B')}">
                        <label>Based On (e.g., B+H+T)</label>
                    </div>
                </div>
                <div class="col-md-1">
                    <div class="form-check mt-3">
                        <input type="checkbox" class="form-check-input stat-active" ${data?.is_active !== false ? 'checked' : ''}>
                        <label class="form-check-label">Active</label>
                    </div>
                </div>
                <div class="col-md-1">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove statutory deduction">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>
        `;

        statutoryDeductionsContainer.appendChild(item);
        attachStatutoryDeductionEvents(item);
        updateStatutoryDeductionsJSON();
    }

    function attachStatutoryDeductionEvents(item) {
        const inputs = item.querySelectorAll('input');
        inputs.forEach(input => {
            input.addEventListener('input', updateStatutoryDeductionsJSON);
            input.addEventListener('change', updateStatutoryDeductionsJSON);
        });

        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                item.remove();
                updateStatutoryDeductionsJSON();
            });
        }
    }

    function updateStatutoryDeductionsJSON() {
        const deductions = [];

        statutoryDeductionsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.stat-name')?.value || '').trim();
            const percentage = parseFloat(item.querySelector('.stat-percentage')?.value);
            const basedOn = (item.querySelector('.stat-based-on')?.value || '').trim();

            if (name && !isNaN(percentage)) {
                deductions.push({
                    name: name,
                    is_active: !!item.querySelector('.stat-active')?.checked,
                    percentage: percentage,
                    based_on: basedOn || 'B'
                });
            }
        });

        hiddenStatutoryDeductions.value = JSON.stringify(deductions, null, 2);
        updateContainerState(statutoryDeductionsContainer);
    }

    // ========================================
    // OTHER DEDUCTIONS CONFIG
    // ========================================
    function addOtherDeduction(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row">
                <div class="col-md-4">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control other-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Deduction Name *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <select class="form-control other-display-rule">
                            <option value="show_if_filled" ${data?.display_rule === 'show_if_filled' ? 'selected' : ''}>Show if Filled</option>
                            <option value="always_show" ${data?.display_rule === 'always_show' ? 'selected' : ''}>Always Show</option>
                        </select>
                        <label>Display Rule</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <select class="form-control other-linked-to">
                            <option value="" ${!data?.linked_to ? 'selected' : ''}>None (Manual)</option>
                            <option value="staff_loan" ${data?.linked_to === 'staff_loan' ? 'selected' : ''}>Staff Loan</option>
                            <option value="salary_advance" ${data?.linked_to === 'salary_advance' ? 'selected' : ''}>Salary Advance</option>
                        </select>
                        <label>Auto-Link To</label>
                    </div>
                </div>
                <div class="col-md-1">
                    <div class="form-floating mb-2">
                        <input type="number" class="form-control other-order" min="1" value="${data?.order ?? 1}">
                        <label>Order</label>
                    </div>
                </div>
                <div class="col-md-1">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove other deduction">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>
        `;

        otherDeductionsContainer.appendChild(item);
        attachOtherDeductionEvents(item);
        updateOtherDeductionsJSON();
    }

    function attachOtherDeductionEvents(item) {
        const inputs = item.querySelectorAll('input, select');
        inputs.forEach(input => {
            input.addEventListener('input', updateOtherDeductionsJSON);
            input.addEventListener('change', updateOtherDeductionsJSON);
        });

        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                item.remove();
                updateOtherDeductionsJSON();
            });
        }
    }

    function updateOtherDeductionsJSON() {
        const deductions = [];

        otherDeductionsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.other-name')?.value || '').trim();
            if (!name) return;

            const linkedTo = (item.querySelector('.other-linked-to')?.value || '').trim();
            const deduction = {
                name: name,
                display_rule: item.querySelector('.other-display-rule')?.value || 'show_if_filled',
                order: parseInt(item.querySelector('.other-order')?.value) || 1
            };

            if (linkedTo) {
                deduction.linked_to = linkedTo;
            }

            deductions.push(deduction);
        });

        hiddenOtherDeductions.value = JSON.stringify(deductions, null, 2);
        updateContainerState(otherDeductionsContainer);
    }

    // ========================================
    // INCOME ITEMS
    // ========================================
    function addIncomeItem(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row">
                <div class="col-md-5">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control income-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Income Item Name *</label>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="form-floating mb-2">
                        <select class="form-control income-display-rule">
                            <option value="show_if_filled" ${data?.display_rule === 'show_if_filled' ? 'selected' : ''}>Show if Filled</option>
                            <option value="always_show" ${data?.display_rule === 'always_show' ? 'selected' : ''}>Always Show</option>
                        </select>
                        <label>Display Rule</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-floating mb-2">
                        <input type="number" class="form-control income-order" min="1" value="${data?.order ?? 1}">
                        <label>Order</label>
                    </div>
                </div>
                <div class="col-md-1">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove income item">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>
        `;

        incomeItemsContainer.appendChild(item);
        attachIncomeItemEvents(item);
        updateIncomeItemsJSON();
    }

    function attachIncomeItemEvents(item) {
        const inputs = item.querySelectorAll('input, select');
        inputs.forEach(input => {
            input.addEventListener('input', updateIncomeItemsJSON);
            input.addEventListener('change', updateIncomeItemsJSON);
        });

        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                item.remove();
                updateIncomeItemsJSON();
            });
        }
    }

    function updateIncomeItemsJSON() {
        const items = [];

        incomeItemsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.income-name')?.value || '').trim();
            if (!name) return;

            items.push({
                name: name,
                display_rule: item.querySelector('.income-display-rule')?.value || 'show_if_filled',
                order: parseInt(item.querySelector('.income-order')?.value) || 1
            });
        });

        hiddenIncomeItems.value = JSON.stringify(items, null, 2);
        updateContainerState(incomeItemsContainer);
    }

    // ========================================
    // UTILITY FUNCTIONS
    // ========================================
    function updateContainerState(container) {
        if (container.children.length > 0) {
            container.classList.add('has-items');
        } else {
            container.classList.remove('has-items');
        }
    }

     function loadExistingData() {
    // Clear all containers first
    basicComponentsContainer.innerHTML = '';
    allowancesContainer.innerHTML = '';
    reliefsContainer.innerHTML = '';
    taxBracketsContainer.innerHTML = '';
    statutoryDeductionsContainer.innerHTML = '';
    otherDeductionsContainer.innerHTML = '';
    incomeItemsContainer.innerHTML = '';

    // Check if we're in edit mode by checking if there's data in the hidden fields
    const isEditMode = hiddenBasicComponents.value && hiddenBasicComponents.value !== '{}';

    // Load basic components
    try {
        const basicComponents = JSON.parse(hiddenBasicComponents.value || '{}');
        if (Object.keys(basicComponents).length > 0) {
            // basicComponents is an object keyed by name-key
            Object.values(basicComponents).forEach(comp => {
                addBasicComponent({
                    name: comp.name,
                    code: comp.code,
                    percentage: comp.percentage
                });
            });
        } else if (!isEditMode) {
            // Only add default template if not in edit mode
            addBasicComponent();
        }
    } catch (e) {
        console.warn('Failed to parse basic components JSON', e);
        if (!isEditMode) addBasicComponent();
    }

    // Load allowances
    try {
        const allowances = JSON.parse(hiddenAllowances.value || '[]');
        if (Array.isArray(allowances) && allowances.length > 0) {
            allowances.forEach(a => addAllowance(a));
        } else if (!isEditMode) {
            addAllowance();
        }
    } catch (e) {
        console.warn('Failed to parse allowances JSON', e);
        if (!isEditMode) addAllowance();
    }

    // Load reliefs
    try {
        const reliefs = JSON.parse(hiddenReliefs.value || '[]');
        if (Array.isArray(reliefs) && reliefs.length > 0) {
            reliefs.forEach(r => addRelief(r));
        } else if (!isEditMode) {
            addRelief();
        }
    } catch (e) {
        console.warn('Failed to parse reliefs JSON', e);
        if (!isEditMode) addRelief();
    }

    // Load tax brackets
    try {
        const brackets = JSON.parse(hiddenTaxBrackets.value || '[]');
        if (Array.isArray(brackets) && brackets.length > 0) {
            brackets.forEach(b => addTaxBracket(b));
        } else if (!isEditMode) {
            addTaxBracket();
        }
    } catch (e) {
        console.warn('Failed to parse tax brackets JSON', e);
        if (!isEditMode) addTaxBracket();
    }

    // Load statutory deductions
    try {
        const statutory = JSON.parse(hiddenStatutoryDeductions.value || '[]');
        if (Array.isArray(statutory) && statutory.length > 0) {
            statutory.forEach(s => addStatutoryDeduction(s));
        } else if (!isEditMode) {
            addStatutoryDeduction();
        }
    } catch (e) {
        console.warn('Failed to parse statutory deductions JSON', e);
        if (!isEditMode) addStatutoryDeduction();
    }

    // Load other deductions
    try {
        const others = JSON.parse(hiddenOtherDeductions.value || '[]');
        if (Array.isArray(others) && others.length > 0) {
            others.forEach(o => addOtherDeduction(o));
        } else if (!isEditMode) {
            addOtherDeduction();
        }
    } catch (e) {
        console.warn('Failed to parse other deductions JSON', e);
        if (!isEditMode) addOtherDeduction();
    }

    // Load income items
    try {
        const incomeItems = JSON.parse(hiddenIncomeItems.value || '[]');
        if (Array.isArray(incomeItems) && incomeItems.length > 0) {
            incomeItems.forEach(i => addIncomeItem(i));
        } else if (!isEditMode) {
            addIncomeItem();
        }
    } catch (e) {
        console.warn('Failed to parse income items JSON', e);
        if (!isEditMode) addIncomeItem();
    }
}

    function escapeHtml(unsafe) {
        if (unsafe === undefined || unsafe === null) return '';
        return String(unsafe)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Detect locked state (either via form data-locked attribute, a hidden input, or global var)
    function isFormLocked() {
        // 1. data-locked attribute on the form
        if (salarySettingForm && salarySettingForm.dataset && salarySettingForm.dataset.locked === 'true') {
            return true;
        }

        // 2. hidden input named is_locked (if backend renders it)
        const isLockedInput = document.querySelector('input[name="is_locked"], #id_is_locked');
        if (isLockedInput) {
            const val = (isLockedInput.value || '').toLowerCase();
            if (val === 'true' || val === '1' || val === 'on') return true;
        }

        // 3. a global variable rendered into template could be used (not relied on)
        if (window.SALARY_SETTING_LOCKED === true) return true;

        return false;
    }

    function disableEditing() {
        // Disable add buttons
        [addBasicComponentBtn, addAllowanceBtn, addReliefBtn, addTaxBracketBtn, addStatutoryDeductionBtn, addOtherDeductionBtn, addIncomeItemBtn].forEach(btn => {
            if (btn) btn.setAttribute('disabled', 'disabled');
        });

        // Disable all inputs/selects and hide remove buttons
        document.querySelectorAll('#salarySettingForm input, #salarySettingForm select, #salarySettingForm textarea, #salarySettingForm button').forEach(el => {
            // Keep CSRF, submit and cancel buttons enabled/visible
            if (el.type === 'submit' || el.type === 'button' && el.classList.contains('btn-danger') === false) return;
            // but disable inputs and selects
            if (el.tagName.toLowerCase() === 'input' || el.tagName.toLowerCase() === 'select' || el.tagName.toLowerCase() === 'textarea' || el.tagName.toLowerCase() === 'button') {
                el.setAttribute('disabled', 'disabled');
            }
        });

        // Hide remove buttons specifically
        document.querySelectorAll('.remove-btn').forEach(rb => rb.style.display = 'none');
    }

    // Attach top-level add button handlers (if present)
    if (addBasicComponentBtn) addBasicComponentBtn.addEventListener('click', () => addBasicComponent());
    if (addAllowanceBtn) addAllowanceBtn.addEventListener('click', () => addAllowance());
    if (addReliefBtn) addReliefBtn.addEventListener('click', () => addRelief());
    if (addTaxBracketBtn) addTaxBracketBtn.addEventListener('click', () => addTaxBracket());
    if (addStatutoryDeductionBtn) addStatutoryDeductionBtn.addEventListener('click', () => addStatutoryDeduction());
    if (addOtherDeductionBtn) addOtherDeductionBtn.addEventListener('click', () => addOtherDeduction());
    if (addIncomeItemBtn) addIncomeItemBtn.addEventListener('click', () => addIncomeItem());

    // On form submit: ensure we update hidden fields and validate basic components sum == 100
    if (salarySettingForm) {
        salarySettingForm.addEventListener('submit', function(event) {
            // Ensure latest values are serialized
            updateBasicComponentsJSON();
            updateAllowancesJSON();
            updateReliefsJSON();
            updateTaxBracketsJSON();
            updateStatutoryDeductionsJSON();
            updateOtherDeductionsJSON();
            updateIncomeItemsJSON();

            // Validate basic components add up to 100 (client-side)
            const total = parseFloat(document.getElementById('totalPercentage')?.textContent || '0');
            if (isNaN(total) || Math.abs(total - 100) > 0.01) {
                event.preventDefault();
                event.stopPropagation();
                showError(`Basic salary components must total 100%. Current total: ${isNaN(total) ? 0 : total.toFixed(2)}%`);
                return false;
            }

            // Optionally you can add more client-side validations here

            return true;
        });
    }

    // Initialize: load existing JSON and set disabled state if locked
    loadExistingData();

    // After loading, if form should be locked, disable editing
    if (isFormLocked()) {
        disableEditing();
    }

    // Minor enhancement: recalc totals if user pastes JSON directly into hidden fields from admin dev tools
    // (Not typical, but safe)
    [hiddenBasicComponents, hiddenAllowances, hiddenReliefs, hiddenTaxBrackets, hiddenIncomeItems, hiddenStatutoryDeductions, hiddenOtherDeductions].forEach(h => {
        if (h) {
            h.addEventListener('change', () => {
                // re-render is not attempted here; just update values
                updateBasicComponentsJSON();
                updateAllowancesJSON();
                updateReliefsJSON();
            });
        }
    });
});
