---
name: tax-planner
description: >
  Strategic tax planning layer for the Corral household. Monitors spending for deductible expenses, calculates quarterly estimated tax obligations, compares itemized vs standard deductions, and tracks effective tax rates with optimization recommendations. Reads from financial-automation and financial-planner databases. Currently W-2 focused — Etsy/self-employment module will be added when the storefront launches.
requires:
  bins: [python3]
  env: [NOTION_API_KEY]
---

# Tax Planner

## Overview
The `tax-planner` skill provides automated, continuous tax strategy monitoring for the Corral household. By directly integrating with existing financial skills, it detects deductible spending, monitors estimated tax safe harbors, and actively compares the benefits of standard vs. itemized deductions. 

### Architecture Diagram
```ascii
                            +--------------------------+
                            |     tax-planner (Skill)  |
                            |                          |
                            |  - Deduction Maximizer   |
                            |  - Estimated Tax Calc    |
                            |  - Effective Tax Dash    |
                            +-----------+--------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
        [ READS DATA ]                                [ WRITES DATA ]
                 |                                             |
+----------------v-----------------+               +-----------v-----------+
| financial-automation (Skill)     |               | Notion Database       |
| - Transactions DB                |               | 🧾 Tax Deductions      |
| - Budgets DB                     |               +-----------------------+
+----------------------------------+
                 |
+----------------v-----------------+
| plaid-budget-sentinel (Skill)    |
| - personal_finance_category      |
|   (primary + detailed via Plaid) |
+----------------------------------+
                 |
+----------------v-----------------+
| financial-planner (Skill)        |
| - Debts DB (Mortgage Interest)   |
| - cash_flow_calendar.json        |
| - investment_accounts.json       |
+----------------------------------+
```

## Setup (One-Time)

### 1. Notion Database Creation
Create the following database under the **FINANCE** page (`31e8275a-14ea-41b1-98c6-d3ec92de2bf9`).

**Database: 🧾 Tax Deductions**
| Property | Type | Details |
| :--- | :--- | :--- |
| Expense | Title | Description of the deduction |
| Date | Date | Transaction or occurrence date |
| Amount | Number | Formatted as US Dollar |
| Category | Select | `Mortgage Interest`, `Property Tax`, `State/Local Tax`, `Medical (above 7.5% AGI)`, `Charitable`, `Home Office`, `Education`, `Student Loan Interest`, `HSA/FSA`, `401k`, `IRA` |
| Source | Select | `Auto-detected`, `Manual`, `Statement` |
| Confidence | Select | `High`, `Medium`, `Review Needed` |
| Tax Year | Select | e.g., `2026`, `2025` |
| Status | Select | `Captured`, `Verified`, `Excluded` |
| Linked Transaction | Relation | Related to the Transactions DB (financial-automation) |
| Notes | Rich Text | Additional context or rationale |

## Modules

### Module A: Deduction Maximizer
**Purpose**: Continuously scan transaction data to find potential tax deductions and compare total itemized deductions against the standard deduction.
**Data Sources**: Transactions DB (financial-automation), Debts DB (financial-planner), `deduction_categories.json`, `tax_brackets.json`.
**Output Format**: Write to 🧾 Tax Deductions database, log alerts.

**Algorithm (Python Pseudocode)**:
```python
def deduction_maximizer(transactions, debts, income_data, brackets, categories):
    deductions_found = []
    total_medical = 0
    total_salt = 0
    
    # 1. Scan transactions for deductible categories
    for tx in transactions:
        # Layer 1: Use Plaid's AI categorization if available
        category, confidence = match_deduction_plaid(tx.get('personal_finance_category', {}))
        # Layer 2: Fall back to merchant pattern matching
        if not category:
            category, confidence = match_deduction(tx['merchant'], categories)
        if category:
            deductions_found.append({
                "Expense": tx['description'],
                "Date": tx['date'],
                "Amount": tx['amount'],
                "Category": category,
                "Source": "Auto-detected",
                "Confidence": confidence,
                "Linked_Tx": tx['id']
            })
            
            if category == "Medical (above 7.5% AGI)":
                total_medical += tx['amount']
            elif category in ["State/Local Tax", "Property Tax"]:
                total_salt += tx['amount']

    # 2. Add Mortgage Interest from Debts DB
    mortgage_interest = get_ytd_mortgage_interest(debts)
    if mortgage_interest > 0:
        deductions_found.append({
            "Expense": "YTD Mortgage Interest",
            "Category": "Mortgage Interest",
            "Amount": mortgage_interest,
            "Source": "Statement",
            "Confidence": "High"
        })
        
    # 3. Apply limitations
    salt_deduction = min(total_salt, brackets['salt_cap'])
    agi = calculate_agi(income_data)
    medical_floor = agi * brackets['medical_floor_pct']
    medical_deduction = max(0, total_medical - medical_floor)
    
    total_itemized = sum(d['Amount'] for d in deductions_found if d['Category'] not in ["Medical (above 7.5% AGI)", "State/Local Tax", "Property Tax"]) + salt_deduction + medical_deduction + mortgage_interest
    
    # 4. Compare vs Standard
    std_deduction = brackets['standard_deduction']['MFJ']
    recommendation = "Itemize" if total_itemized > std_deduction else "Standard"
    
    write_to_notion(deductions_found)
    return {"total_itemized": total_itemized, "standard": std_deduction, "recommendation": recommendation}

def match_deduction(merchant, categories):
    for cat_name, details in categories.items():
        for pattern in details['merchant_patterns']:
            if pattern.lower() in merchant.lower():
                return cat_name, details['confidence_level']
    return None, None


# Plaid Personal Finance Category → Tax Deduction mapping
PLAID_TO_TAX_MAP = {
    "MEDICAL": {
        "MEDICAL_DENTAL_CARE": ("Medical (above 7.5% AGI)", "High"),
        "MEDICAL_EYE_CARE": ("Medical (above 7.5% AGI)", "High"),
        "MEDICAL_HOSPITALS_AND_CLINICS": ("Medical (above 7.5% AGI)", "High"),
        "MEDICAL_PHARMACIES_AND_SUPPLEMENTS": ("Medical (above 7.5% AGI)", "Medium"),
    },
    "GOVERNMENT_AND_NON_PROFIT": {
        "GOVERNMENT_AND_NON_PROFIT_DONATIONS": ("Charitable", "High"),
        "GOVERNMENT_AND_NON_PROFIT_TAX_PAYMENT": ("State/Local Tax", "High"),
    },
    "EDUCATION": {"_default": ("Education", "Medium")},
}

def match_deduction_plaid(pfc):
    """Match transaction to tax deduction using Plaid's personal_finance_category."""
    if not pfc:
        return None, None
    primary = pfc.get("primary", "")
    detailed = pfc.get("detailed", "")
    mapping = PLAID_TO_TAX_MAP.get(primary, {})
    if detailed in mapping:
        return mapping[detailed]
    if "_default" in mapping:
        return mapping["_default"]
    return None, None
```

### Module B: Quarterly Estimated Tax Calculator
**Purpose**: Monitor non-wage income (investments, interest) and ensure safe harbor rules are met to avoid underpayment penalties.
**Data Sources**: `prior_year_tax.json`, `investment_accounts.json`, `tax_brackets.json`.
**Output Format**: Quarterly alert with safe harbor analysis.

**Algorithm (Python Pseudocode)**:
```python
def calc_quarterly_estimates(current_income, withholding, prior_tax, brackets):
    # Safe harbor logic: 100% of prior year, or 110% if prior AGI > $150k
    safe_harbor_pct = 1.1 if prior_tax['prior_year_agi'] > 150000 else 1.0
    safe_harbor_amount = prior_tax['federal_tax'] * safe_harbor_pct
    
    # Current year projection
    projected_total_tax = calculate_current_tax(current_income, brackets)
    projected_90_pct = projected_total_tax * 0.9
    
    target_withholding = min(safe_harbor_amount, projected_90_pct)
    
    q_target = target_withholding / 4
    current_q = get_current_quarter()
    
    ytd_target = q_target * current_q
    ytd_withholding = withholding['federal']
    
    if ytd_withholding < ytd_target:
        shortfall = ytd_target - ytd_withholding
        return f"Warning: Estimated payment of ${shortfall:,.2f} recommended to meet safe harbor."
    
    return "Safe harbor met through W-2 withholding."
```

### Module C: Effective Tax Rate Dashboard
**Purpose**: Compare actual vs. optimized effective tax rates considering Federal, State (Kansas), and FICA. Provide recommendations.
**Data Sources**: `cash_flow_calendar.json`, `tax_brackets.json`.
**Output Format**: Formatted report detailing tax burden and strategies.

**Algorithm (Python Pseudocode)**:
```python
def generate_tax_dashboard(income_data, deductions, brackets):
    combined_gross = income_data['jon_gross'] + income_data['jaime_gross']
    
    # Pre-tax deductions (401k, HSA)
    taxable_income = combined_gross - income_data['pre_tax_deductions']
    
    # Calculate Federal Tax
    fed_tax = calc_progressive_tax(taxable_income, brackets['federal_2026']['MFJ'])
    
    # Calculate Kansas Tax
    ks_tax = calc_progressive_tax(taxable_income, brackets['kansas_2026']['MFJ'])
    
    # Calculate FICA (Social Security cap applies to Jon's alone)
    ss_cap = brackets['ss_wage_base']
    jon_fica = min(income_data['jon_gross'], ss_cap) * 0.062 + income_data['jon_gross'] * 0.0145
    jaime_fica = income_data['jaime_gross'] * 0.0765 # Under cap
    total_fica = jon_fica + jaime_fica
    
    total_tax = fed_tax + ks_tax + total_fica
    effective_rate = total_tax / combined_gross
    
    # Optimizations
    optimizations = []
    if income_data['401k_contributions'] < brackets['max_401k'] * 2:
        optimizations.append("Maximize 401(k) to reduce taxable income.")
        
    return {
        "gross_income": combined_gross,
        "effective_rate": effective_rate,
        "fed_tax": fed_tax,
        "ks_tax": ks_tax,
        "fica": total_fica,
        "optimizations": optimizations
    }
```

## Cron Automations

### TX1: Quarterly Tax Deadline Alert
- **Schedule**: 1st of Apr, Jun, Sep, Jan at 9:00 AM CT
- **Model**: Gemini 3 Flash
- **Action**: Runs Module B to check if estimated tax payments are needed for the upcoming quarterly deadline.
- **Message Format**:
  ```
  🧾 **Quarterly Tax Deadline Approaching (Apr 15)**
  - Safe Harbor Target (YTD): $X,XXX
  - Current YTD Withholding: $X,XXX
  - Status: [Safe / Payment Required]
  - Recommended Estimated Payment: $X
  ```

### TX2: Monthly Deduction Scan
- **Schedule**: 5th of every month at 10:00 AM CT
- **Model**: Kimi K2.6
- **Action**: Runs Module A, scans Transactions DB for the previous month, writes to Notion, and summarizes itemized vs standard progress.
- **Message Format**:
  ```
  🔍 **Tax Deduction Scan Complete**
  - New Deductions Found: X
  - Total Potential Itemized: $X,XXX
  - 2026 Standard Deduction: $30,000 (est.)
  - Current Recommendation: [Standard / Itemize]
  - View details in Notion: [Link]
  ```
- **Structured Output**: Write machine-readable JSON for downstream skill consumption.
  - **Path**: `~/.hermes/cron_outputs/tx2_deductions_latest.json`
  - **Schema**:
    ```json
    {
      "month": "YYYY-MM",
      "deductions_found": [
        {"merchant": "name", "amount": 0.00, "category": "Charitable", "match_method": "plaid_ai|merchant_pattern|manual"}
      ],
      "total_deductible": 0.00,
      "ytd_deductible": 0.00,
      "standard_deduction": 30000,
      "itemized_vs_standard": "itemize|standard|too_close",
      "timestamp": "ISO8601"
    }
    ```
  - **Consumers**: `financial-planner` (tax optimization recommendations), `life-score` (financial domain).

### TX3: Quarterly Tax Dashboard
- **Schedule**: 1st of Apr, Jul, Oct, Jan at 8:00 PM CT
- **Model**: DeepSeek V4 Flash
- **Action**: Runs Module C to calculate the effective tax rate and compile optimization recommendations.
- **Message Format**:
  ```
  📊 **Quarterly Tax Optimization Dashboard**
  - Estimated Combined Gross: $234,880
  - Effective Tax Rate: XX.X% (Fed: XX%, KS: X%, FICA: X%)
  - **Recommendations**:
    1. Increase 401k contribution by X%
    2. Consider bunching charitable donations
  ```

## Resource Files
| File | Description |
| :--- | :--- |
| `tax_brackets.json` | 2026 Federal and KS tax brackets, standard deduction, limitations. |
| `deduction_categories.json` | Rules for matching transactions to tax deduction categories. |
| `prior_year_tax.json` | Static data containing the prior year's tax baseline for safe harbor. |

## Integration
- **financial-automation**: READ (Transactions DB for deductions, Budgets DB)
- **plaid-budget-sentinel**: READ (personal_finance_category field on Transactions for AI-assisted deduction classification)
- **financial-planner**: READ (Debts DB for mortgage interest, income sources)
- **tax-planner**: WRITE (🧾 Tax Deductions database)

## Data Collection Checklist
- [ ] Jon: Provide completed `prior_year_tax.json` details from last year's return.
- [ ] Jon: Confirm pre-tax deduction amounts currently hitting paychecks (401k, HSA, health premiums).
- [ ] Jon: Confirm property tax annual amount for Kansas.
