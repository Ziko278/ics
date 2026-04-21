// salary_setting_form.js

document.addEventListener('DOMContentLoaded', function() {
    // Containers
    const basicComponentsContainer = document.getElementById('basicComponentsContainer');
    const allowancesContainer = document.getElementById('allowancesContainer');
    const reliefsContainer = document.getElementById('reliefsContainer');
    const taxBracketsContainer = document.getElementById('taxBracketsContainer');
    const statutoryDeductionsContainer = document.getElementById('statutoryDeductionsContainer');
    const otherDeductionsContainer = document.getElementById('otherDeductionsContainer');
    const incomeItemsContainer = document.getElementById('incomeItemsContainer');
    const additionalFieldsContainer = document.getElementById('additionalFieldsContainer');

    // Hidden inputs
    const hiddenBasicComponents = document.getElementById('id_basic_components_json');
    const hiddenAllowances = document.getElementById('id_allowances_json');
    const hiddenReliefs = document.getElementById('id_reliefs_exemptions_json');
    const hiddenTaxBrackets = document.getElementById('id_tax_brackets_json');
    const hiddenIncomeItems = document.getElementById('id_income_items_json');
    const hiddenStatutoryDeductions = document.getElementById('id_statutory_deductions_json');
    const hiddenOtherDeductions = document.getElementById('id_other_deductions_config_json');
    const hiddenAdditionalFields = document.getElementById('id_additional_fields_json');

    // Buttons
    const addBasicComponentBtn = document.getElementById('addBasicComponentBtn');
    const addAllowanceBtn = document.getElementById('addAllowanceBtn');
    const addReliefBtn = document.getElementById('addReliefBtn');
    const addTaxBracketBtn = document.getElementById('addTaxBracketBtn');
    const addStatutoryDeductionBtn = document.getElementById('addStatutoryDeductionBtn');
    const addOtherDeductionBtn = document.getElementById('addOtherDeductionBtn');
    const addIncomeItemBtn = document.getElementById('addIncomeItemBtn');
    const addAdditionalFieldBtn = document.getElementById('addAdditionalFieldBtn');

    // Error modal
    const errorModalEl = document.getElementById('errorModal');
    const errorModal = errorModalEl ? new bootstrap.Modal(errorModalEl) : null;
    const errorModalMessage = document.getElementById('errorModalMessage');

    // Form
    const salarySettingForm = document.getElementById('salarySettingForm');

    let componentCounter = 0;

    // ========================================
    // UTILITY: Show error
    // ========================================
    function showError(message) {
        if (errorModal && errorModalMessage) {
            errorModalMessage.textContent = message;
            errorModal.show();
        } else {
            alert(message);
        }
    }

    // ========================================
    // UTILITY: Get current additional field codes/names
    // ========================================
    function getAdditionalFields() {
        const fields = [];
        additionalFieldsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.add-field-name')?.value || '').trim();
            const code = (item.querySelector('.add-field-code')?.value || '').trim();
            if (name && code) fields.push({ name, code });
        });
        return fields;
    }

    // ========================================
    // UTILITY: Get current basic component codes
    // ========================================
    function getBasicComponentCodes() {
        const codes = [];
        basicComponentsContainer.querySelectorAll('.component-item').forEach(item => {
            const code = (item.querySelector('.comp-code')?.value || '').trim().toUpperCase();
            if (code) codes.push(code);
        });
        return codes;
    }

    // ========================================
    // UTILITY: Build a <select> for additional fields
    // ========================================
    function buildAdditionalFieldSelect(selectedValue, cssClass) {
        const fields = getAdditionalFields();
        let options = fields.map(f =>
            `<option value="${escapeHtml(f.code)}" ${f.code === selectedValue ? 'selected' : ''}>${escapeHtml(f.name)} (${escapeHtml(f.code)})</option>`
        ).join('');
        if (!options) options = '<option value="">-- No additional fields defined --</option>';
        return `<select class="form-control ${cssClass}">${options}</select>`;
    }

    // ========================================
    // UTILITY: Switch based-on field between text and select
    // ========================================
    function applyBasedOnType(item, type, currentValue, inputClass, labelText) {
        const container = item.querySelector(`.${inputClass}-wrapper`);
        if (!container) return;

        if (type === 'additional_field') {
            const fields = getAdditionalFields();
            let options = fields.map(f =>
                `<option value="${escapeHtml(f.code)}" ${f.code === currentValue ? 'selected' : ''}>${escapeHtml(f.name)} (${escapeHtml(f.code)})</option>`
            ).join('');
            if (!options) options = '<option value="">-- No additional fields defined --</option>';
            container.innerHTML = `
                <div class="form-floating mb-2">
                    <select class="form-control ${inputClass}">${options}</select>
                    <label>${escapeHtml(labelText)}</label>
                </div>`;
        } else {
            // Salary component text input
            container.innerHTML = `
                <div class="form-floating mb-2">
                    <input type="text" class="form-control ${inputClass}" placeholder="Based On" value="${escapeHtml(currentValue || '')}">
                    <label>${escapeHtml(labelText)}</label>
                </div>`;
        }
    }

    // ========================================
    // UTILITY: Refresh all based-on selects when additional fields change
    // ========================================
    function refreshAllAdditionalFieldSelects() {
        const fields = getAdditionalFields();

        // For each section, find items where based-on-type = additional_field and rebuild the select
        [
            { container: allowancesContainer, typeClass: 'allow-based-on-type', inputClass: 'allow-based-on', wrapperClass: 'allow-based-on-wrapper', label: 'Based On (field)' },
            { container: reliefsContainer, typeClass: 'relief-based-on-type', inputClass: 'relief-based-on', wrapperClass: 'relief-based-on-wrapper', label: 'Based On (field)' },
            { container: statutoryDeductionsContainer, typeClass: 'stat-based-on-type', inputClass: 'stat-based-on', wrapperClass: 'stat-based-on-wrapper', label: 'Based On (field)' },
        ].forEach(({ container, typeClass, inputClass, wrapperClass, label }) => {
            container.querySelectorAll('.component-item').forEach(item => {
                const typeSelect = item.querySelector(`.${typeClass}`);
                if (!typeSelect || typeSelect.value !== 'additional_field') return;

                const currentSelect = item.querySelector(`.${inputClass}`);
                const currentValue = currentSelect ? currentSelect.value : '';
                const wrapper = item.querySelector(`.${wrapperClass}`);
                if (!wrapper) return;

                let options = fields.map(f =>
                    `<option value="${escapeHtml(f.code)}" ${f.code === currentValue ? 'selected' : ''}>${escapeHtml(f.name)} (${escapeHtml(f.code)})</option>`
                ).join('');
                if (!options) options = '<option value="">-- No additional fields defined --</option>';

                const floatingDiv = wrapper.querySelector('.form-floating');
                if (floatingDiv) {
                    const selectEl = floatingDiv.querySelector('select');
                    if (selectEl) selectEl.innerHTML = options;
                    else floatingDiv.innerHTML = `<select class="form-control ${inputClass}">${options}</select><label>${escapeHtml(label)}</label>`;
                }
            });
        });
    }

    // ========================================
    // BASIC SALARY COMPONENTS TOOLTIP TEXT
    // ========================================
    const BASIC_COMPONENT_HELP = `
        <strong>Basic Salary Components</strong><br>
        Split the monthly salary into named components. Each component gets a <strong>Code</strong> (e.g. <code>B</code>, <code>H</code>, <code>T</code>) and a <strong>Percentage</strong>. All percentages must total 100%.<br><br>
        <strong>Component codes</strong> are used throughout the form to reference these components (e.g. in allowances, statutory deductions, and tax reliefs).<br><br>
        <strong>Rules:</strong><br>
        • Code must be <strong>unique</strong> and <strong>max 3 characters</strong><br>
        • Codes are case-insensitive (<code>B</code> = <code>b</code>)
    `;

    const BASED_ON_HELP = `
        <strong>Based On — Syntax Guide</strong><br>
        Controls what amount the percentage is calculated against:<br><br>
        <code>TOTAL</code> — Total monthly salary (all basic components)<br>
        <code>GROSS_INCOME</code> — Full gross income (including allowances)<br>
        <code>B</code> — A single component by its code (e.g. Basic salary)<br>
        <code>B+H+T</code> — Sum of multiple components by code<br>
        <em>additional field code</em> — e.g. <code>rent</code> (select "Additional Field" as Base Type)<br><br>
        <strong>Note:</strong> Component codes must exactly match those defined in the Basic Salary Components section.
    `;

    // ========================================
    // BASIC COMPONENTS
    // ========================================
    function addBasicComponent(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row align-items-start">
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control comp-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Name *</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control comp-code" placeholder="Code" maxlength="3" value="${escapeHtml(data?.code || '')}" style="text-transform:uppercase;">
                        <label>Code * <small class="text-muted">(max 3)</small></label>
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
                    <small class="text-muted d-block mb-1 mt-2">Example (₦500k): <strong class="comp-amount">₦0.00</strong></small>
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
        // Force code to uppercase and max 3 chars
        const codeInput = item.querySelector('.comp-code');
        if (codeInput) {
            codeInput.addEventListener('input', function() {
                this.value = this.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 3);
                updateBasicComponentsJSON();
                refreshAllAdditionalFieldSelects(); // codes changed, update tooltip mentions
            });
        }

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
            const code = (item.querySelector('.comp-code')?.value || '').trim().toUpperCase();
            const percentage = parseFloat(item.querySelector('.comp-percentage')?.value) || 0;

            if (name && code) {
                const key = name.toLowerCase().replace(/\s+/g, '_');
                components[key] = { code, percentage, name };
                totalPercentage += percentage;

                const amount = (500000 * percentage) / 100;
                const amountEl = item.querySelector('.comp-amount');
                if (amountEl) {
                    amountEl.textContent = `₦${amount.toLocaleString('en-NG', {minimumFractionDigits: 2})}`;
                }
            } else {
                const amountEl = item.querySelector('.comp-amount');
                if (amountEl) amountEl.textContent = `₦0.00`;
            }
        });

        const totalSpan = document.getElementById('totalPercentage');
        if (totalSpan) {
            totalSpan.textContent = totalPercentage.toFixed(2);
            totalSpan.className = Math.abs(totalPercentage - 100) < 0.01 ? 'percentage-valid' : 'percentage-invalid';
        }

        hiddenBasicComponents.value = JSON.stringify(components, null, 2);
        updateContainerState(basicComponentsContainer);
    }

    // ========================================
    // BASED-ON FIELD BUILDER (shared for allowances, reliefs, statutory)
    // ========================================
    /**
     * Renders the based-on input/select into the wrapper element.
     * @param {HTMLElement} wrapper - the .xxx-based-on-wrapper div
     * @param {string} type - 'component' | 'additional_field'
     * @param {string} currentValue - the current based_on value
     * @param {string} inputClass - CSS class to put on the input/select (e.g. 'allow-based-on')
     * @param {string} labelText - text for the floating label
     * @param {Function} onChangeCallback - called on input/change
     */
    function renderBasedOnField(wrapper, type, currentValue, inputClass, labelText, onChangeCallback) {
        let inner = '';
        if (type === 'additional_field') {
            const fields = getAdditionalFields();
            let options = fields.map(f =>
                `<option value="${escapeHtml(f.code)}" ${f.code === currentValue ? 'selected' : ''}>${escapeHtml(f.name)} (${escapeHtml(f.code)})</option>`
            ).join('');
            if (!options) options = '<option value="">-- No additional fields defined --</option>';
            inner = `
                <div class="form-floating mb-2">
                    <select class="form-control ${inputClass}">${options}</select>
                    <label>${escapeHtml(labelText)}</label>
                </div>`;
        } else {
            inner = `
                <div class="form-floating mb-2">
                    <input type="text" class="form-control ${inputClass}" placeholder="Based On" value="${escapeHtml(currentValue || '')}">
                    <label>${escapeHtml(labelText)}</label>
                </div>`;
        }
        wrapper.innerHTML = inner;
        const el = wrapper.querySelector(`.${inputClass}`);
        if (el && onChangeCallback) {
            el.addEventListener('input', onChangeCallback);
            el.addEventListener('change', onChangeCallback);
        }
    }

    // ========================================
    // ALLOWANCES
    // ========================================
    function addAllowance(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        const calcType = data?.calculation_type || 'percentage';
        const basedOnType = data?.based_on_type || 'component';
        const basedOnValue = data?.based_on || 'TOTAL';

        item.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control allow-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Allowance Name *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <select class="form-control allow-calc-type">
                            <option value="percentage" ${calcType === 'percentage' ? 'selected' : ''}>Percentage</option>
                            <option value="fixed" ${calcType === 'fixed' ? 'selected' : ''}>Fixed Amount</option>
                            <option value="combined" ${calcType === 'combined' ? 'selected' : ''}>Combined (Fixed + %)</option>
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
                <div class="col-md-2 text-end">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove allowance">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>

            <div class="calc-details">
                <div class="row">
                    <div class="col-md-3 percentage-group" style="display: ${calcType === 'fixed' ? 'none' : 'block'};">
                        <div class="form-floating mb-2">
                            <input type="number" class="form-control allow-percentage" step="0.01" min="0"
                                   placeholder="%" value="${data?.percentage ?? ''}">
                            <label>Percentage %</label>
                        </div>
                    </div>
                    <div class="col-md-3 percentage-group" style="display: ${calcType === 'fixed' ? 'none' : 'block'};">
                        <div class="form-floating mb-2">
                            <select class="form-control allow-based-on-type">
                                <option value="component" ${basedOnType === 'component' ? 'selected' : ''}>Salary Component
                                    <button type="button" class="btn btn-sm btn-outline-secondary ms-1 based-on-help-btn"
                                        data-bs-toggle="popover" data-bs-html="true" data-bs-trigger="click"
                                        data-bs-content="${escapeHtml(BASED_ON_HELP)}" title="Based On Help"
                                        style="padding:1px 5px;font-size:0.75rem;">?</button>
                                </option>
                                <option value="additional_field" ${basedOnType === 'additional_field' ? 'selected' : ''}>Additional Field</option>
                            </select>
                            <label>Base Type</label>
                        </div>
                    </div>
                    <div class="col-md-3 percentage-group allow-based-on-wrapper" style="display: ${calcType === 'fixed' ? 'none' : 'block'};">
                        <!-- rendered by renderBasedOnField() -->
                    </div>
                    <div class="col-md-3 fixed-group" style="display: ${calcType === 'percentage' ? 'none' : 'block'};">
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

        // Render the based-on field
        const wrapper = item.querySelector('.allow-based-on-wrapper');
        renderBasedOnField(wrapper, basedOnType, basedOnValue, 'allow-based-on', 'Based On', updateAllowancesJSON);

        attachAllowanceEvents(item);
        updateAllowancesJSON();
    }

    function attachAllowanceEvents(item) {
        const calcType = item.querySelector('.allow-calc-type');
        const percentageGroups = item.querySelectorAll('.percentage-group');
        const fixedGroups = item.querySelectorAll('.fixed-group');
        const basedOnTypeSelect = item.querySelector('.allow-based-on-type');

        calcType.addEventListener('change', function() {
            const isFixed = this.value === 'fixed';
            const isPercentage = this.value === 'percentage';
            percentageGroups.forEach(el => el.style.display = isFixed ? 'none' : 'block');
            fixedGroups.forEach(el => el.style.display = isPercentage ? 'none' : 'block');
            updateAllowancesJSON();
        });

        basedOnTypeSelect.addEventListener('change', function() {
            const wrapper = item.querySelector('.allow-based-on-wrapper');
            const currentInput = item.querySelector('.allow-based-on');
            const currentValue = currentInput ? currentInput.value : '';
            renderBasedOnField(wrapper, this.value, currentValue, 'allow-based-on', 'Based On', updateAllowancesJSON);
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

            const calcType = item.querySelector('.allow-calc-type')?.value || 'percentage';
            const allowance = {
                name,
                is_active: !!item.querySelector('.allow-active')?.checked,
                calculation_type: calcType,
                annual_only: !!item.querySelector('.allow-annual')?.checked
            };

            if (calcType !== 'fixed') {
                const percentage = parseFloat(item.querySelector('.allow-percentage')?.value);
                const basedOn = (item.querySelector('.allow-based-on')?.value || '').trim();
                const basedOnType = item.querySelector('.allow-based-on-type')?.value || 'component';
                if (!isNaN(percentage)) allowance.percentage = percentage;
                if (basedOn) allowance.based_on = basedOn;
                allowance.based_on_type = basedOnType;
            }

            if (calcType !== 'percentage') {
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

        const calcType = data?.calculation_type || (data?.formula_type === 'percentage_plus_fixed' ? 'combined' : data?.formula_type || 'combined');
        const basedOnType = data?.based_on_type || 'component';
        const basedOnValue = data?.based_on || 'GROSS_INCOME';
        const isFixed = calcType === 'fixed';

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
                        <select class="form-control relief-calc-type">
                            <option value="combined" ${calcType === 'combined' ? 'selected' : ''}>Percentage + Fixed</option>
                            <option value="percentage" ${calcType === 'percentage' ? 'selected' : ''}>Percentage Only</option>
                            <option value="fixed" ${isFixed ? 'selected' : ''}>Fixed Only</option>
                        </select>
                        <label>Calculation Type</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-check mt-3">
                        <input type="checkbox" class="form-check-input relief-active" ${data?.is_active !== false ? 'checked' : ''}>
                        <label class="form-check-label">Active</label>
                    </div>
                </div>
                <div class="col-md-2 text-end">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove relief">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>

            <div class="calc-details">
                <div class="row">
                    <div class="col-md-3 percentage-group" style="display: ${isFixed ? 'none' : 'block'};">
                        <div class="form-floating mb-2">
                            <input type="number" class="form-control relief-percentage" step="0.01" min="0"
                                   value="${data?.percentage ?? ''}">
                            <label>Percentage %</label>
                        </div>
                    </div>
                    <div class="col-md-3 percentage-group" style="display: ${isFixed ? 'none' : 'block'};">
                        <div class="form-floating mb-2">
                            <select class="form-control relief-based-on-type">
                                <option value="component" ${basedOnType === 'component' ? 'selected' : ''}>Salary Component</option>
                                <option value="additional_field" ${basedOnType === 'additional_field' ? 'selected' : ''}>Additional Field</option>
                            </select>
                            <label>Base Type</label>
                        </div>
                    </div>
                    <div class="col-md-3 percentage-group relief-based-on-wrapper" style="display: ${isFixed ? 'none' : 'block'};">
                        <!-- rendered by renderBasedOnField() -->
                    </div>
                    <div class="col-md-3 fixed-group" style="display: ${calcType === 'percentage' ? 'none' : 'block'};">
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

        const wrapper = item.querySelector('.relief-based-on-wrapper');
        renderBasedOnField(wrapper, basedOnType, basedOnValue, 'relief-based-on', 'Based On', updateReliefsJSON);

        attachReliefEvents(item);
        updateReliefsJSON();
    }

    function attachReliefEvents(item) {
        const calcType = item.querySelector('.relief-calc-type');
        const percentageGroups = item.querySelectorAll('.percentage-group');
        const fixedGroups = item.querySelectorAll('.fixed-group');
        const basedOnTypeSelect = item.querySelector('.relief-based-on-type');

        calcType.addEventListener('change', function() {
            const isFixed = this.value === 'fixed';
            const isPercentage = this.value === 'percentage';
            percentageGroups.forEach(el => el.style.display = isFixed ? 'none' : 'block');
            fixedGroups.forEach(el => el.style.display = isPercentage ? 'none' : 'block');
            updateReliefsJSON();
        });

        basedOnTypeSelect.addEventListener('change', function() {
            const wrapper = item.querySelector('.relief-based-on-wrapper');
            const currentInput = item.querySelector('.relief-based-on');
            const currentValue = currentInput ? currentInput.value : '';
            renderBasedOnField(wrapper, this.value, currentValue, 'relief-based-on', 'Based On', updateReliefsJSON);
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

            const calcType = item.querySelector('.relief-calc-type')?.value || 'combined';
            const relief = {
                name,
                is_active: !!item.querySelector('.relief-active')?.checked,
                calculation_type: calcType
            };

            if (calcType !== 'fixed') {
                const percentage = parseFloat(item.querySelector('.relief-percentage')?.value);
                const basedOn = (item.querySelector('.relief-based-on')?.value || '').trim();
                const basedOnType = item.querySelector('.relief-based-on-type')?.value || 'component';
                if (!isNaN(percentage)) relief.percentage = percentage;
                if (basedOn) relief.based_on = basedOn;
                relief.based_on_type = basedOnType;
            }

            if (calcType !== 'percentage') {
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

        // FIX #4: Separate the label and hint to avoid overflow/overlap
        item.innerHTML = `
            <div class="row align-items-end">
                <div class="col-md-5">
                    <label class="form-label fw-semibold mb-1">
                        Income Limit (₦)
                        <small class="text-muted fw-normal ms-1">— leave empty for "remaining"</small>
                    </label>
                    <input type="number" class="form-control bracket-limit" step="1" min="0"
                           placeholder="e.g. 300000" value="${data?.limit !== null && data?.limit !== undefined ? data.limit : ''}">
                </div>
                <div class="col-md-5">
                    <div class="form-floating mb-0">
                        <input type="number" class="form-control bracket-rate" step="0.01" min="0" max="100"
                               placeholder="Rate" value="${data?.rate ?? ''}">
                        <label>Tax Rate % *</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <button type="button" class="btn btn-danger btn-sm remove-btn" aria-label="Remove bracket">
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
                brackets.push({
                    limit: limitInput === '' ? null : parseFloat(limitInput),
                    rate
                });
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

        const calcType = data?.calculation_type || 'percentage';
        const basedOnType = data?.based_on_type || 'component';
        const basedOnValue = data?.based_on || 'B';
        const isFixed = calcType === 'fixed';

        item.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control stat-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Deduction Name *</label>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="form-floating mb-2">
                        <select class="form-control stat-calc-type">
                            <option value="percentage" ${calcType === 'percentage' ? 'selected' : ''}>Percentage</option>
                            <option value="fixed" ${calcType === 'fixed' ? 'selected' : ''}>Fixed Amount</option>
                            <option value="combined" ${calcType === 'combined' ? 'selected' : ''}>Combined (Fixed + %)</option>
                        </select>
                        <label>Calculation Type</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <div class="form-check mt-3">
                        <input type="checkbox" class="form-check-input stat-active" ${data?.is_active !== false ? 'checked' : ''}>
                        <label class="form-check-label">Active</label>
                    </div>
                </div>
                <div class="col-md-4 text-end">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove statutory deduction">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>

            <div class="calc-details">
                <div class="row">
                    <div class="col-md-3 percentage-group" style="display: ${isFixed ? 'none' : 'block'};">
                        <div class="form-floating mb-2">
                            <input type="number" class="form-control stat-percentage" step="0.01" min="0"
                                   value="${data?.percentage ?? ''}">
                            <label>Percentage %</label>
                        </div>
                    </div>
                    <div class="col-md-3 percentage-group" style="display: ${isFixed ? 'none' : 'block'};">
                        <div class="form-floating mb-2">
                            <select class="form-control stat-based-on-type">
                                <option value="component" ${basedOnType === 'component' ? 'selected' : ''}>Salary Component</option>
                                <option value="additional_field" ${basedOnType === 'additional_field' ? 'selected' : ''}>Additional Field</option>
                            </select>
                            <label>Base Type</label>
                        </div>
                    </div>
                    <div class="col-md-3 percentage-group stat-based-on-wrapper" style="display: ${isFixed ? 'none' : 'block'};">
                        <!-- rendered by renderBasedOnField() -->
                    </div>
                    <div class="col-md-3 fixed-group" style="display: ${calcType === 'percentage' ? 'none' : 'block'};">
                        <div class="form-floating mb-2">
                            <input type="number" class="form-control stat-fixed-amount" step="0.01" min="0"
                                   value="${data?.fixed_amount ?? ''}">
                            <label>Fixed Amount (₦)</label>
                        </div>
                    </div>
                </div>
            </div>
        `;

        statutoryDeductionsContainer.appendChild(item);

        const wrapper = item.querySelector('.stat-based-on-wrapper');
        renderBasedOnField(wrapper, basedOnType, basedOnValue, 'stat-based-on', 'Based On', updateStatutoryDeductionsJSON);

        attachStatutoryDeductionEvents(item);
        updateStatutoryDeductionsJSON();
    }

    function attachStatutoryDeductionEvents(item) {
        const calcType = item.querySelector('.stat-calc-type');
        const percentageGroups = item.querySelectorAll('.percentage-group');
        const fixedGroups = item.querySelectorAll('.fixed-group');
        const basedOnTypeSelect = item.querySelector('.stat-based-on-type');

        calcType.addEventListener('change', function() {
            const isFixed = this.value === 'fixed';
            const isPercentage = this.value === 'percentage';
            percentageGroups.forEach(el => el.style.display = isFixed ? 'none' : 'block');
            fixedGroups.forEach(el => el.style.display = isPercentage ? 'none' : 'block');
            updateStatutoryDeductionsJSON();
        });

        basedOnTypeSelect.addEventListener('change', function() {
            const wrapper = item.querySelector('.stat-based-on-wrapper');
            const currentInput = item.querySelector('.stat-based-on');
            const currentValue = currentInput ? currentInput.value : '';
            renderBasedOnField(wrapper, this.value, currentValue, 'stat-based-on', 'Based On', updateStatutoryDeductionsJSON);
            updateStatutoryDeductionsJSON();
        });

        const inputs = item.querySelectorAll('input, select');
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
            if (!name) return;

            const calcType = item.querySelector('.stat-calc-type')?.value || 'percentage';
            const deduction = {
                name,
                is_active: !!item.querySelector('.stat-active')?.checked,
                calculation_type: calcType
            };

            if (calcType !== 'fixed') {
                const percentage = parseFloat(item.querySelector('.stat-percentage')?.value);
                const basedOn = (item.querySelector('.stat-based-on')?.value || '').trim();
                const basedOnType = item.querySelector('.stat-based-on-type')?.value || 'component';
                if (!isNaN(percentage)) deduction.percentage = percentage;
                if (basedOn) deduction.based_on = basedOn;
                deduction.based_on_type = basedOnType;
            }

            if (calcType !== 'percentage') {
                const fixedAmount = parseFloat(item.querySelector('.stat-fixed-amount')?.value);
                if (!isNaN(fixedAmount)) deduction.fixed_amount = fixedAmount;
            }

            deductions.push(deduction);
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
                name,
                display_rule: item.querySelector('.other-display-rule')?.value || 'show_if_filled',
                order: parseInt(item.querySelector('.other-order')?.value) || 1
            };

            if (linkedTo) deduction.linked_to = linkedTo;
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
                name,
                display_rule: item.querySelector('.income-display-rule')?.value || 'show_if_filled',
                order: parseInt(item.querySelector('.income-order')?.value) || 1
            });
        });

        hiddenIncomeItems.value = JSON.stringify(items, null, 2);
        updateContainerState(incomeItemsContainer);
    }

    // ========================================
    // ADDITIONAL FIELDS
    // ========================================
    function addAdditionalField(data = null) {
        componentCounter++;
        const item = document.createElement('div');
        item.className = 'component-item border rounded p-3 mb-3';
        item.dataset.id = componentCounter;

        item.innerHTML = `
            <div class="row">
                <div class="col-md-5">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control add-field-name" placeholder="Name" value="${escapeHtml(data?.name || '')}">
                        <label>Field Name * (e.g., Rent)</label>
                    </div>
                </div>
                <div class="col-md-5">
                    <div class="form-floating mb-2">
                        <input type="text" class="form-control add-field-code" placeholder="Code" value="${escapeHtml(data?.code || '')}">
                        <label>Field Code * (e.g., rent)</label>
                    </div>
                </div>
                <div class="col-md-2">
                    <button type="button" class="btn btn-danger btn-sm remove-btn mt-2" aria-label="Remove field">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </div>
        `;

        additionalFieldsContainer.appendChild(item);
        attachAdditionalFieldEvents(item);
        updateAdditionalFieldsJSON();
    }

    function attachAdditionalFieldEvents(item) {
        const inputs = item.querySelectorAll('input');
        inputs.forEach(input => {
            input.addEventListener('input', function() {
                updateAdditionalFieldsJSON();
                refreshAllAdditionalFieldSelects();
            });
            input.addEventListener('change', function() {
                updateAdditionalFieldsJSON();
                refreshAllAdditionalFieldSelects();
            });
        });

        const removeBtn = item.querySelector('.remove-btn');
        if (removeBtn) {
            removeBtn.addEventListener('click', function() {
                item.remove();
                updateAdditionalFieldsJSON();
                refreshAllAdditionalFieldSelects();
            });
        }
    }

    function updateAdditionalFieldsJSON() {
        const fields = [];

        additionalFieldsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.add-field-name')?.value || '').trim();
            const code = (item.querySelector('.add-field-code')?.value || '').trim();
            if (name && code) fields.push({ name, code });
        });

        hiddenAdditionalFields.value = JSON.stringify(fields, null, 2);
        updateContainerState(additionalFieldsContainer);
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
        basicComponentsContainer.innerHTML = '';
        allowancesContainer.innerHTML = '';
        reliefsContainer.innerHTML = '';
        taxBracketsContainer.innerHTML = '';
        statutoryDeductionsContainer.innerHTML = '';
        otherDeductionsContainer.innerHTML = '';
        incomeItemsContainer.innerHTML = '';
        additionalFieldsContainer.innerHTML = '';

        const isEditMode = hiddenBasicComponents.value && hiddenBasicComponents.value !== '{}';

        // Load additional fields FIRST so they are available when other sections render
        try {
            const addFields = JSON.parse(hiddenAdditionalFields.value || '[]');
            if (Array.isArray(addFields) && addFields.length > 0) {
                addFields.forEach(f => addAdditionalField(f));
            }
        } catch (e) {
            console.warn('Failed to parse additional fields JSON', e);
        }

        // Load basic components
        try {
            const basicComponents = JSON.parse(hiddenBasicComponents.value || '{}');
            if (Object.keys(basicComponents).length > 0) {
                Object.values(basicComponents).forEach(comp => {
                    addBasicComponent({ name: comp.name, code: comp.code, percentage: comp.percentage });
                });
            } else if (!isEditMode) {
                addBasicComponent();
            }
        } catch (e) {
            console.warn('Failed to parse basic components JSON', e);
            if (!isEditMode) addBasicComponent();
        }

        // Load allowances
        try {
            const allowances = JSON.parse(hiddenAllowances.value || '[]');
            if (Array.isArray(allowances) && allowances.length > 0) allowances.forEach(a => addAllowance(a));
        } catch (e) { console.warn('Failed to parse allowances JSON', e); }

        // Load reliefs
        try {
            const reliefs = JSON.parse(hiddenReliefs.value || '[]');
            if (Array.isArray(reliefs) && reliefs.length > 0) reliefs.forEach(r => addRelief(r));
        } catch (e) { console.warn('Failed to parse reliefs JSON', e); }

        // Load tax brackets
        try {
            const brackets = JSON.parse(hiddenTaxBrackets.value || '[]');
            if (Array.isArray(brackets) && brackets.length > 0) brackets.forEach(b => addTaxBracket(b));
        } catch (e) { console.warn('Failed to parse tax brackets JSON', e); }

        // Load statutory deductions
        try {
            const statutory = JSON.parse(hiddenStatutoryDeductions.value || '[]');
            if (Array.isArray(statutory) && statutory.length > 0) statutory.forEach(s => addStatutoryDeduction(s));
        } catch (e) { console.warn('Failed to parse statutory deductions JSON', e); }

        // Load other deductions
        try {
            const others = JSON.parse(hiddenOtherDeductions.value || '[]');
            if (Array.isArray(others) && others.length > 0) others.forEach(o => addOtherDeduction(o));
        } catch (e) { console.warn('Failed to parse other deductions JSON', e); }

        // Load income items
        try {
            const incomeItems = JSON.parse(hiddenIncomeItems.value || '[]');
            if (Array.isArray(incomeItems) && incomeItems.length > 0) incomeItems.forEach(i => addIncomeItem(i));
        } catch (e) { console.warn('Failed to parse income items JSON', e); }
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

    function isFormLocked() {
        if (salarySettingForm?.dataset?.locked === 'true') return true;
        const isLockedInput = document.querySelector('input[name="is_locked"], #id_is_locked');
        if (isLockedInput) {
            const val = (isLockedInput.value || '').toLowerCase();
            if (val === 'true' || val === '1' || val === 'on') return true;
        }
        if (window.SALARY_SETTING_LOCKED === true) return true;
        return false;
    }

    function disableEditing() {
        [addBasicComponentBtn, addAllowanceBtn, addReliefBtn, addTaxBracketBtn, addStatutoryDeductionBtn, addOtherDeductionBtn, addIncomeItemBtn, addAdditionalFieldBtn].forEach(btn => {
            if (btn) btn.setAttribute('disabled', 'disabled');
        });

        document.querySelectorAll('#salarySettingForm input, #salarySettingForm select, #salarySettingForm textarea, #salarySettingForm button').forEach(el => {
            if (el.type === 'submit' || (el.type === 'button' && !el.classList.contains('btn-danger'))) return;
            el.setAttribute('disabled', 'disabled');
        });

        document.querySelectorAll('.remove-btn').forEach(rb => rb.style.display = 'none');
    }

    // ========================================
    // VALIDATION: Basic component codes unique + max 3 chars
    // ========================================
    function validateBasicComponentCodes() {
        const codes = [];
        let error = null;

        basicComponentsContainer.querySelectorAll('.component-item').forEach(item => {
            const code = (item.querySelector('.comp-code')?.value || '').trim().toUpperCase();
            const name = (item.querySelector('.comp-name')?.value || '').trim();
            if (!code && name) {
                error = `Component "${name}" is missing a code.`;
                return;
            }
            if (code.length > 3) {
                error = `Component code "${code}" exceeds 3 characters.`;
                return;
            }
            if (codes.includes(code)) {
                error = `Duplicate component code "${code}". Each code must be unique.`;
                return;
            }
            if (code) codes.push(code);
        });

        return error;
    }

    // ========================================
    // VALIDATION: based_on references valid codes
    // ========================================
    const VALID_KEYWORDS = ['TOTAL', 'GROSS_INCOME'];

    function validateBasedOnValue(value, basedOnType, fieldName) {
        if (!value || basedOnType === 'additional_field') return null;

        const upperVal = value.trim().toUpperCase();

        // Keywords are always valid
        if (VALID_KEYWORDS.includes(upperVal)) return null;

        // Otherwise treat as component code expression (e.g. B+H+T)
        const codes = upperVal.split('+').map(c => c.trim()).filter(Boolean);
        const existingCodes = getBasicComponentCodes();

        for (const code of codes) {
            if (!existingCodes.includes(code)) {
                return `"${fieldName}": Based On code "${code}" does not match any defined basic component. Valid codes: ${existingCodes.join(', ') || 'none defined'}. Use TOTAL or GROSS_INCOME for keywords.`;
            }
        }
        return null;
    }

    function validateAllBasedOnFields() {
        const errors = [];

        // Allowances
        allowancesContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.allow-name')?.value || '').trim();
            const basedOnType = item.querySelector('.allow-based-on-type')?.value || 'component';
            const basedOn = (item.querySelector('.allow-based-on')?.value || '').trim();
            const calcType = item.querySelector('.allow-calc-type')?.value;
            if (calcType !== 'fixed' && basedOn) {
                const err = validateBasedOnValue(basedOn, basedOnType, `Allowance "${name}"`);
                if (err) errors.push(err);
            }
        });

        // Reliefs
        reliefsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.relief-name')?.value || '').trim();
            const basedOnType = item.querySelector('.relief-based-on-type')?.value || 'component';
            const basedOn = (item.querySelector('.relief-based-on')?.value || '').trim();
            const calcType = item.querySelector('.relief-calc-type')?.value;
            if (calcType !== 'fixed' && basedOn) {
                const err = validateBasedOnValue(basedOn, basedOnType, `Relief "${name}"`);
                if (err) errors.push(err);
            }
        });

        // Statutory deductions
        statutoryDeductionsContainer.querySelectorAll('.component-item').forEach(item => {
            const name = (item.querySelector('.stat-name')?.value || '').trim();
            const basedOnType = item.querySelector('.stat-based-on-type')?.value || 'component';
            const basedOn = (item.querySelector('.stat-based-on')?.value || '').trim();
            const calcType = item.querySelector('.stat-calc-type')?.value;
            if (calcType !== 'fixed' && basedOn) {
                const err = validateBasedOnValue(basedOn, basedOnType, `Statutory Deduction "${name}"`);
                if (err) errors.push(err);
            }
        });

        return errors;
    }

    // ========================================
    // HELP POPOVERS: inject ? buttons into section headers
    // ========================================
    function initHelpPopovers() {
        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(btn => {
            const section = btn.closest('.card');
            if (!section) return;

            const header = section.querySelector('.card-header');
            if (!header) return;

            // Destroy any existing tooltip the template inline script may have created
            const existingTooltip = bootstrap.Tooltip.getInstance(btn);
            if (existingTooltip) existingTooltip.dispose();

            const content = header.classList.contains('bg-success')
                ? BASIC_COMPONENT_HELP
                : BASED_ON_HELP;

            btn.removeAttribute('data-bs-toggle');
            btn.removeAttribute('data-bs-original-title');
            btn.removeAttribute('title');
            btn.classList.add('salary-help-btn');

            const pop = new bootstrap.Popover(btn, {
                html: true,
                content: content,
                title: 'Help',
                placement: 'left',
                trigger: 'manual',
                sanitize: false
            });

            btn._salaryPopoverVisible = false;

            btn.addEventListener('click', function(e) {
                e.stopPropagation();
                // Close all other open popovers
                document.querySelectorAll('.salary-help-btn').forEach(other => {
                    if (other !== btn && other._salaryPopoverVisible) {
                        bootstrap.Popover.getInstance(other)?.hide();
                        other._salaryPopoverVisible = false;
                    }
                });
                // Toggle this one
                if (btn._salaryPopoverVisible) {
                    pop.hide();
                    btn._salaryPopoverVisible = false;
                } else {
                    pop.show();
                    btn._salaryPopoverVisible = true;
                }
            });
        });

        // Capture phase: fires before any child stopPropagation
        document.addEventListener('click', function(e) {
            if (e.target.closest('.salary-help-btn')) return;
            if (e.target.closest('.popover')) return;
            document.querySelectorAll('.salary-help-btn').forEach(btn => {
                if (btn._salaryPopoverVisible) {
                    bootstrap.Popover.getInstance(btn)?.hide();
                    btn._salaryPopoverVisible = false;
                }
            });
        }, true);
    }


    // ========================================
    // BUTTON HANDLERS
    // ========================================
    if (addBasicComponentBtn) addBasicComponentBtn.addEventListener('click', () => addBasicComponent());
    if (addAllowanceBtn) addAllowanceBtn.addEventListener('click', () => addAllowance());
    if (addReliefBtn) addReliefBtn.addEventListener('click', () => addRelief());
    if (addTaxBracketBtn) addTaxBracketBtn.addEventListener('click', () => addTaxBracket());
    if (addStatutoryDeductionBtn) addStatutoryDeductionBtn.addEventListener('click', () => addStatutoryDeduction());
    if (addOtherDeductionBtn) addOtherDeductionBtn.addEventListener('click', () => addOtherDeduction());
    if (addIncomeItemBtn) addIncomeItemBtn.addEventListener('click', () => addIncomeItem());
    if (addAdditionalFieldBtn) addAdditionalFieldBtn.addEventListener('click', () => addAdditionalField());

    // ========================================
    // FORM SUBMIT VALIDATION
    // ========================================
    if (salarySettingForm) {
        salarySettingForm.addEventListener('submit', function(event) {
            // Serialize all sections
            updateBasicComponentsJSON();
            updateAllowancesJSON();
            updateReliefsJSON();
            updateTaxBracketsJSON();
            updateStatutoryDeductionsJSON();
            updateOtherDeductionsJSON();
            updateIncomeItemsJSON();
            updateAdditionalFieldsJSON();

            // 1. Validate basic components total 100%
            const total = parseFloat(document.getElementById('totalPercentage')?.textContent || '0');
            if (isNaN(total) || Math.abs(total - 100) > 0.01) {
                event.preventDefault();
                event.stopPropagation();
                showError(`Basic salary components must total 100%. Current total: ${isNaN(total) ? 0 : total.toFixed(2)}%`);
                return false;
            }

            // 2. Validate component codes are unique and max 3 chars
            const codeError = validateBasicComponentCodes();
            if (codeError) {
                event.preventDefault();
                event.stopPropagation();
                showError(codeError);
                return false;
            }

            // 3. Validate all based_on references are valid
            const basedOnErrors = validateAllBasedOnFields();
            if (basedOnErrors.length > 0) {
                event.preventDefault();
                event.stopPropagation();
                showError(basedOnErrors[0]); // Show first error
                return false;
            }

            return true;
        });
    }

    // ========================================
    // INIT
    // ========================================
    loadExistingData();
    initHelpPopovers();

    if (isFormLocked()) {
        disableEditing();
    }

    // Re-sync on hidden field change (dev tools edge case)
    [hiddenBasicComponents, hiddenAllowances, hiddenReliefs, hiddenTaxBrackets, hiddenIncomeItems, hiddenStatutoryDeductions, hiddenOtherDeductions, hiddenAdditionalFields].forEach(h => {
        if (h) {
            h.addEventListener('change', () => {
                updateBasicComponentsJSON();
                updateAllowancesJSON();
                updateReliefsJSON();
                updateAdditionalFieldsJSON();
            });
        }
    });
});