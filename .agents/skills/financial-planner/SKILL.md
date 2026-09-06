---
name: financial-planner
description: >
  Strategic financial planning layer for the Corral household. Extends the
  financial-automation skill (which handles budgeting, transactions, and statement
  parsing) with five planning modules: Net Worth & Balance Sheet tracking, Cash Flow
  Calendar & Forecasting, Debt Payoff Strategy, Credit Card Rewards Optimization,
  and a composite Financial Health Score. Adds 7 cron jobs and 2 new Notion databases.
requires:
  bins: [python3]
  env: [NOTION_API_KEY]
---

# Financial Planner Skill

## Overview

This skill is the **strategic planning layer** that sits on top of the `financial-automation` skill (which handles tactical budgeting, transaction categorization, and statement parsing). Together they form a complete personal finance system.

**Dependency**: This skill requires `financial-automation` to be active. It reads from the Accounts, Budgets, and Transactions databases created by that skill.

### Architecture

```
financial-automation (tactical)          financial-planner (strategic)
├── 🏦 Accounts DB ──────────────────▶  Module A: Net Worth Snapshots
├── 📊 Budgets DB ───────────────────▶  Module E: Financial Health Score
├── 🧾 Transactions DB ─────────────▶  Module D: Rewards Optimization
├── 📄 Statements DB                    Module B: Cash Flow Calendar
├── merchant_categories.json            Module C: Debt Payoff Strategy
└── budget_targets.json ─────────────▶  (income data shared)
```

### Notion Integration

- **FINANCE page**: `31e8275a-14ea-41b1-98c6-d3ec92de2bf9`
- **Bills & Budget DB**: `5225799b-f83b-4d75-86ba-d23094cb2835`
- Databases from `financial-automation`: Accounts, Budgets, Transactions, Statements
- **New databases** (created by this skill): Net Worth Snapshots, Debts

---

## Setup (One-Time)

### Step 1: Create New Notion Databases

Create 2 new databases under the FINANCE page (`31e8275a-14ea-41b1-98c6-d3ec92de2bf9`).

#### 📈 Net Worth Snapshots

| Property | Type | Details |
|----------|------|---------|
| Snapshot Date | Title | Format: `YYYY-MM` |
| Total Assets | Number (dollar) | Sum of all account balances + investment values |
| Total Liabilities | Number (dollar) | Sum of all debt balances |
| Net Worth | Formula | `prop("Total Assets") - prop("Total Liabilities")` |
| MoM Change | Number (dollar) | This month's NW minus last month's NW |
| MoM Percent | Formula | `prop("MoM Change") / (prop("Net Worth") - prop("MoM Change")) * 100` |
| Assets Breakdown | Rich Text | JSON string: `{"checking": X, "savings": X, "investments": X, "property": X}` |
| Liabilities Breakdown | Rich Text | JSON string: `{"mortgage": X, "auto": X, "student": X, "medical": X, "other": X}` |
| Financial Health Score | Number | 0-100 composite score from Module E |
| Notes | Rich Text | Narrative: major events, windfalls, setbacks |

#### 💳 Debts

| Property | Type | Details |
|----------|------|---------|
| Debt Name | Title | e.g., "Mortgage", "Honda Car Note" |
| Type | Select | Options: `Mortgage`, `Auto Loan`, `Student Loan`, `Personal Loan`, `Medical`, `Credit Card`, `Other` |
| Lender | Rich Text | Servicer name |
| Current Balance | Number (dollar) | Updated monthly |
| Interest Rate | Number (percent) | APR |
| Monthly Payment | Number (dollar) | Minimum required |
| Extra Payment | Number (dollar) | Additional principal payment this month (default 0) |
| Payment Day | Number | Day of month autopay drafts |
| Autopay Source | Select | Options: `US Bank Checking`, `US Bank Savings`, `Chase Checking` |
| Original Amount | Number (dollar) | Starting balance |
| Start Date | Date | Loan origination |
| Payoff Date | Formula | Calculated from balance, rate, and payment |
| Total Interest Remaining | Number (dollar) | Calculated via amortization |
| Priority | Select | Options: `Highest` (avalanche target), `Active`, `Minimum Only`, `0% - No Rush` |
| Status | Select | Options: `Active`, `Paid Off`, `Deferred` |

### Step 2: Seed Debts Database

Load all debts from `resources/debt_inventory.json`. For items with TBD rates/balances, create the row with `null` values and set status to indicate data needed.

### Step 3: Collect Missing Data from Jon

Before the system is fully operational, Jon must provide:

1. **Debt details** (for each: current balance, interest rate, remaining term):
   - Mortgage
   - Honda car note
   - Tesla car note
   - Student loan
   - Jaime's loan
2. **Jon's last paycheck date** (to calculate biweekly schedule forward)
3. **401k details** (both Jon and Jaime): provider, contribution rate, employer match
4. **Schwab account type** and balance
5. **Northwestern Mutual current cash value**
6. **Credit limits** for all 6 cards

Store responses in the respective resource JSON files.

---

## Module A: Net Worth & Balance Sheet

### Purpose
Track household net worth monthly, identify trends, and celebrate milestones.

### Data Collection (1st of each month)

**Assets** — pull from these sources:
1. **Checking accounts**: Accounts DB (Chase Checking, US Bank Checking)
2. **Savings accounts**: Accounts DB (Emergency Savings, US Bank Savings)
3. **Investment accounts**:
   - **Robinhood Agentic**: Read from `stock-weekly-briefing/resources/portfolio_snapshot.json` (auto-updated weekly by stock-weekly-briefing pipeline via Robinhood MCP)
   - Jack's Custodial IRA (Schwab) — query Jon or integrate when API access available
   - Schwab account
   - Jaime's 401k (Alight)
   - Jon's 401k
   - Northwestern Mutual cash value
   - CRO stake (Crypto.com)
4. **Property**: Home value (use Zillow Zestimate or county assessment — update quarterly, not monthly)
5. **Vehicles**: KBB or NADA values (update quarterly)

**Liabilities** — pull from Debts DB:
1. Mortgage remaining balance
2. Honda remaining balance
3. Tesla remaining balance
4. Student loan remaining balance
5. Jaime's loan remaining balance
6. ER payment remaining balance
7. Credit card statement balances (should be $0 if paid in full)

### Net Worth Calculation

```
Net Worth = Total Assets - Total Liabilities

Assets = Σ(checking_balances) + Σ(savings_balances) + Σ(investment_values) + home_value + vehicle_values
Liabilities = Σ(debt_balances) + Σ(credit_card_balances)
```

### Monthly Snapshot Procedure

1. Create a new row in Net Worth Snapshots DB with `YYYY-MM` title
2. Sum all asset values → Total Assets
3. Sum all liability values → Total Liabilities
4. Calculate Net Worth
5. Query previous month's snapshot for MoM Change
6. Calculate Financial Health Score (Module E) and record
7. Write narrative Notes for any significant events

### Milestone Alerts

Send Google Chat celebration messages when:

| Milestone | Message |
|-----------|---------|
| Net worth increases 3 consecutive months | 🎉 Net worth has grown for 3 straight months! Momentum is real. |
| Net worth crosses a $10K boundary | 🏆 Net worth just crossed $XX0,000! |
| A debt is fully paid off | 🎊 [Debt Name] is PAID OFF! That frees up $[amount]/mo. |
| Emergency fund hits 1-month expenses | 🛡️ Emergency fund covers 1 full month of expenses! |
| Emergency fund hits 3-month expenses | 🛡️🛡️🛡️ Emergency fund covers 3 months! Financial stability achieved. |
| Savings rate exceeds 15% | 💰 Savings rate hit [X]%! Above the 15% threshold. |

---

## Module B: Cash Flow Calendar & Forecasting

### Purpose
Predict account balances 14 days ahead. Identify low-balance risk windows. Optimize bonus paycheck months.

### Data Source
`resources/cash_flow_calendar.json` contains all recurring inflows and outflows mapped to calendar dates.

### 14-Day Lookahead Algorithm

Every day, compute the projected balance for each of the next 14 days:

```python
projected_balance = current_checking_balance

for day in range(1, 15):
    target_date = today + timedelta(days=day)
    
    # Add inflows scheduled for target_date
    for inflow in get_inflows(target_date):
        projected_balance += inflow.amount
    
    # Subtract outflows scheduled for target_date
    for outflow in get_outflows(target_date):
        projected_balance -= abs(outflow.amount)
    
    # Check thresholds
    if projected_balance < LOW_BALANCE_THRESHOLD:
        trigger_alert(target_date, projected_balance)
```

**Low-Balance Thresholds**:
- 🔴 Critical: Below $500 in checking → immediate alert
- 🟡 Warning: Below $1,500 in checking → advisory alert
- 🟢 Healthy: Above $2,500 in checking

### Jon's Biweekly Pay Schedule

Jon is paid biweekly on Fridays. To calculate the schedule:

1. Get Jon's last paycheck date (TBD — ask Jon)
2. Generate all future Fridays at 14-day intervals
3. Identify **bonus paycheck months**: months containing 3 paychecks instead of 2

```python
def find_bonus_months(last_paydate, year=2026):
    """Identify months with 3 paychecks."""
    paydates = []
    current = last_paydate
    while current.year <= year:
        paydates.append(current)
        current += timedelta(days=14)
    
    from collections import Counter
    months = Counter(d.month for d in paydates if d.year == year)
    return [month for month, count in months.items() if count == 3]
```

**Bonus paycheck strategy**: The 3rd paycheck in a bonus month ($2,860) should be allocated:
1. 50% → Emergency fund
2. 30% → Highest-priority debt extra payment
3. 20% → Sinking funds or investments

### Jaime's Semi-Monthly Schedule

Jaime is paid on the 1st and 15th. If those fall on a weekend:
- Saturday → paid Friday (the day before)
- Sunday → paid Monday (the day after)

### Dense Payment Windows

The calendar has natural "crunch" periods where multiple large drafts cluster:

| Window | Drafts | Approximate Total |
|--------|--------|-------------------|
| 1st–3rd | Mortgage $2,161 + AT&T $280 + JoCo WW $111 + YouTube TV $73 + Google Fiber $70 | ~$2,695 |
| 16th–20th | Honda $670 + Jaime Loan $312 + Tesla $435 + NW Mutual $95 + WaterOne $150 + Progressive $441 | ~$2,103 |

Ensure checking balance exceeds $2,700 before the 1st and $2,200 before the 16th.

### Cash Flow Report Format

```
📅 14-Day Cash Flow Forecast (as of [date])
Starting Balance: $X,XXX (US Bank Checking)

[date] 💰 Jaime paycheck +$1,800        → $X,XXX
[date] 🔴 Mortgage -$2,161              → $X,XXX  ⚠️ LOW
[date] 🔴 AT&T -$280                    → $X,XXX
[date] 💰 Jon paycheck +$2,860          → $X,XXX
...

Lowest projected balance: $X,XXX on [date] [🟢🟡🔴]
Action needed: [none / transfer $X from savings / defer discretionary]
```

---

## Module C: Debt Payoff Strategy

### Purpose
Minimize total interest paid, accelerate debt freedom, and provide clear payoff timelines.

### Debt Inventory
All debts are tracked in `resources/debt_inventory.json` and mirrored to the Debts Notion DB.

### Amortization Calculations

For each debt with a known rate and balance, calculate:

```python
def monthly_payment(principal, annual_rate, months):
    """Standard amortization formula."""
    r = annual_rate / 12
    if r == 0:
        return principal / months
    return principal * (r * (1 + r)**months) / ((1 + r)**months - 1)

def remaining_interest(balance, annual_rate, monthly_payment):
    """Total interest remaining on the loan."""
    r = annual_rate / 12
    if r == 0:
        return 0
    total_paid = 0
    while balance > 0:
        interest = balance * r
        principal = monthly_payment - interest
        balance -= principal
        total_paid += interest
    return total_paid

def months_to_payoff(balance, annual_rate, monthly_payment):
    """Months until the debt reaches $0."""
    r = annual_rate / 12
    if r == 0:
        return math.ceil(balance / monthly_payment)
    return math.ceil(-math.log(1 - (balance * r / monthly_payment)) / math.log(1 + r))

def extra_payment_savings(balance, annual_rate, min_payment, extra):
    """Interest saved by adding extra monthly principal."""
    interest_without = remaining_interest(balance, annual_rate, min_payment)
    interest_with = remaining_interest(balance, annual_rate, min_payment + extra)
    months_without = months_to_payoff(balance, annual_rate, min_payment)
    months_with = months_to_payoff(balance, annual_rate, min_payment + extra)
    return {
        "interest_saved": interest_without - interest_with,
        "months_saved": months_without - months_with
    }
```

### Strategy Selection

**Default: Hybrid approach** (Avalanche with quick-win exceptions)

Decision tree:

```
1. Is ER Payment ($150/mo, 0%, ~$2,400 remaining)?
   → Minimum payments only. 0% interest = free money. Never pay extra.

2. Any debt with balance < $2,000 AND rate > 0%?
   → Pay it off first (snowball win). Redirect freed payment to next target.

3. Otherwise: Avalanche order
   → Sort remaining debts by interest rate descending
   → All extra money goes to highest-rate debt
   → When it's paid off, roll that payment into the next highest
```

### Debt Payoff Waterfall

When a debt is paid off, the freed monthly payment cascades:

```
Debt A ($X/mo) paid off
  → $X/mo redirected to Debt B (now paying min + $X)
  → Debt B pays off faster
  → Debt B's payment + $X → Debt C
  → Continue until debt-free (excluding mortgage)
```

### Bi-Weekly Mortgage Integration

If the mortgage lender supports bi-weekly payments:

- Current: 12 payments/year × $2,160.57 = $25,926.84/year
- Bi-weekly: 26 payments/year × $1,080.29 = $28,087.54/year
- **Extra principal per year**: $2,160.70 (equivalent to one extra monthly payment)
- **Estimated years saved**: 4–7 years on a 30-year mortgage (depends on rate)

If the lender doesn't support true bi-weekly, simulate it:
- Make normal monthly payments
- Make one additional principal-only payment each year (use bonus paycheck month)

### Debt Dashboard (Monthly Report)

```
💳 Debt Payoff Dashboard — [Month Year]

| Debt | Balance | Rate | Payment | Payoff Date | Priority |
|------|---------|------|---------|-------------|----------|
| Mortgage | $XXX,XXX | X.X% | $2,161 | YYYY-MM | Hold |
| Honda | $XX,XXX | X.X% | $670 | YYYY-MM | Avalanche #1 |
| Tesla | $XX,XXX | X.X% | $435 | YYYY-MM | Active |
| Student | $XX,XXX | X.X% | $217 | YYYY-MM | Active |
| Jaime Loan | $XX,XXX | X.X% | $312 | YYYY-MM | Active |
| ER Payment | $2,400 | 0.0% | $150 | 2027-10 | Min Only |

Total Debt: $XXX,XXX
Total Monthly Payments: $3,945
Debt-to-Income Ratio: XX.X%
Interest paid this month: $X,XXX
Extra payment this month: $XXX → [target debt]

🎯 Next milestone: [Debt Name] payoff in [X] months
💡 If you add $200/mo extra: saves $X,XXX interest, [X] months earlier
```

---

## Module D: Credit Card Rewards Optimization

### Purpose
Maximize rewards earnings, never miss a quarterly activation, catch wrong-card usage, and validate annual fee ROI.

### Data Source
`resources/chase_rewards.json` — Complete card portfolio and optimal selection rules.
`resources/credit_cards.json` — Card details, limits, and status.

### Chase Trifecta Strategy

All UR points flow into the Sapphire Reserve where they're worth **1.5¢/point** via the Chase Travel portal or transferable 1:1 to airline/hotel partners.

**Effective earn rates (including 1.5¢ multiplier)**:
- Freedom Flex quarterly category: **7.5%** (5x × 1.5¢)
- Sapphire Reserve dining/travel: **4.5%** (3x × 1.5¢)
- Freedom Flex/Unlimited dining: **4.5%** (3x × 1.5¢)
- Freedom Unlimited everything else: **2.25%** (1.5x × 1.5¢)
- Chase Travel portal: **15%** (10x × 1.5¢)

### Optimal Card Decision Tree

For every purchase:

```
Is it Spotify?
  → Crypto.com Ruby (100% rebate in CRO)

Is it Amazon.com or Whole Foods?
  → Amazon Prime Card (5%)
  → EXCEPTION: During Freedom Flex quarterly Amazon period, use Flex (7.5% effective UR)

Is it dining or a restaurant?
  → Chase Sapphire Reserve (4.5% effective)

Is it travel? (flights, hotels, car rentals, transit)
  → Chase Sapphire Reserve via Chase Travel portal (15% effective)
  → If must book direct: Sapphire Reserve (4.5% effective)

Is it a drugstore/pharmacy?
  → Chase Freedom Flex (4.5% effective)

Is it in the current Freedom Flex 5% quarterly category?
  → Chase Freedom Flex (7.5% effective, $1,500/quarter cap)

Is it streaming?
  → Chase Sapphire Reserve (4.5% effective, 3x streaming)

Is it online grocery delivery?
  → Chase Sapphire Reserve (4.5% effective, 3x online grocery)

Everything else?
  → Chase Freedom Unlimited (2.25% effective)
  → If CFU unavailable: Capital One Venture X (2%)
```

### Quarterly Activation Reminders

Freedom Flex 5% categories MUST be activated each quarter. The activation window opens ~2 weeks before the quarter starts.

| Quarter | Months | 2026 Categories | Activation Reminder Date |
|---------|--------|-----------------|-------------------------|
| Q1 | Jan–Mar | Gas stations, EV charging | December 15 |
| Q2 | Apr–Jun | Amazon.com, Select streaming | March 15 |
| Q3 | Jul–Sep | TBD — check chase.com/freedom | June 15 |
| Q4 | Oct–Dec | TBD — check chase.com/freedom | September 15 |

When a new quarter's categories are announced, update `chase_rewards.json`.

### Wrong-Card Alerts

When processing transactions (from the Transactions DB in financial-automation), check each credit card transaction against the optimal card rules:

```python
def check_wrong_card(transaction):
    """Returns alert if a suboptimal card was used."""
    category = transaction.category
    card_used = transaction.account
    optimal = get_optimal_card(category)
    
    if card_used != optimal.card_name:
        lost_value = (optimal.effective_rate - get_rate(card_used, category)) * transaction.amount
        if lost_value > 0.50:  # Only alert if >$0.50 was left on the table
            return {
                "transaction": transaction.description,
                "amount": transaction.amount,
                "card_used": card_used,
                "should_have_used": optimal.card_name,
                "value_lost": lost_value
            }
    return None
```

Include wrong-card summary in the weekly spending scorecard.

### Sapphire Reserve Annual Fee ROI

Track annually to validate the $550 fee:

```
Sapphire Reserve ROI Calculation:

Credits & Perks:
+ $300 travel credit (auto-applied)          = $300
+ DashPass membership value (~$120/yr)       = $120
+ Lyft Pink value (~$100/yr)                 = $100
+ Global Entry credit ($100/4yr amortized)   = $25

Points Value (at 1.5¢/point):
+ Dining: $500/mo × 12 × 3pts × $0.015      = $324
+ Travel: $200/mo × 12 × 3pts × $0.015      = $108
+ Streaming: $100/mo × 12 × 3pts × $0.015   = $54
+ Other via CSR: estimate                     = $XX

Total Value:                                  = $1,031+
Annual Fee:                                   - $550
─────────────────────────────────────────────
Net Benefit:                                  = $481+

Verdict: KEEP ✅ (break-even at ~$X,XXX dining spend/yr)
```

Recalculate at Jon's cardmember anniversary. Alert if ROI drops below $100 net.

### Capital One Venture X ROI

```
Venture X ROI:
+ $300 travel credit                          = $300
+ 10,000 anniversary miles ($100 value)       = $100
+ Priority Pass / Capital One Lounges         = $150 (estimated)
                                               ─────
Total Credits:                                = $550
Annual Fee:                                   - $395
Net before earn:                              = $155 (positive before any spending)

Verdict: KEEP ✅ (profitable even with zero spending due to credits > fee)
```

---

## Module E: Financial Health Score

### Purpose
Single composite score (0–100) that quantifies overall household financial health. Makes progress tangible and identifies the highest-impact area to focus on.

### Data Source
`resources/financial_health_weights.json` — Metric definitions, weights, and thresholds.

### Scoring Formula

```
Financial Health Score = Σ (metric_score × weight)

Where:
  budget_adherence  × 0.20  (from financial-automation Budgets DB)
+ emergency_fund    × 0.20  (from Accounts DB savings balance)
+ debt_to_income    × 0.15  (from debt_inventory.json + budget_targets.json)
+ savings_rate      × 0.15  (from investment_accounts.json contributions)
+ net_worth_trend   × 0.15  (from Net Worth Snapshots DB, 3-month rolling)
+ credit_util       × 0.10  (from credit_cards.json / Accounts DB)
+ rewards_efficiency× 0.05  (from transaction wrong-card analysis)
```

### Metric Calculations

#### 1. Budget Adherence (20%)

```python
def budget_adherence_score():
    """Compare actual spend vs target for each variable category."""
    categories = query_budgets_db(month=current_month)
    scores = []
    for cat in categories:
        if cat.budget_amount == 0:
            continue
        ratio = abs(cat.spent) / cat.budget_amount
        cat_score = max(0, min(100, (1 - max(0, ratio - 1)) * 100))
        scores.append((cat_score, cat.budget_amount))
    
    # Weighted average by budget size
    total_weight = sum(w for _, w in scores)
    return sum(s * w for s, w in scores) / total_weight if total_weight else 100
```

#### 2. Emergency Fund Progress (20%)

```python
def emergency_fund_score():
    """EF balance as percentage of 3-month essential expenses target."""
    ef_balance = get_account_balance("Emergency Savings")
    target = 21366  # 3 months essential expenses
    return min(100, (ef_balance / target) * 100)
```

#### 3. Debt-to-Income Ratio (15%)

```python
def dti_score():
    """Lower DTI = higher score. 20% DTI = 100, 60% DTI = 0."""
    total_debt_payments = sum(d.monthly_payment for d in get_active_debts())
    gross_monthly = 9320
    dti_percent = (total_debt_payments / gross_monthly) * 100
    return max(0, 100 - ((dti_percent - 20) * 2.5))
```

#### 4. Savings Rate (15%)

```python
def savings_rate_score():
    """Monthly savings as % of take-home. 20% rate = 100."""
    monthly_savings = sum([
        get_ef_contribution(),
        get_401k_contributions(),  # employee portion only
        get_ira_contributions(),
        get_schwab_contribution(),
        get_nwm_cash_value_growth()
    ])
    net_income = 9320  # combined take-home
    savings_pct = (monthly_savings / net_income) * 100
    return min(100, (savings_pct / 20) * 100)
```

#### 5. Net Worth Trajectory (15%)

```python
def net_worth_trajectory_score():
    """3-month rolling average of MoM net worth changes."""
    snapshots = query_nw_snapshots(last_n=4)  # need 4 to get 3 deltas
    if len(snapshots) < 2:
        return 50  # neutral until we have history
    
    changes = [snapshots[i].net_worth - snapshots[i+1].net_worth 
               for i in range(len(snapshots)-1)]
    avg_change = sum(changes) / len(changes)
    
    if avg_change >= 1000: return 100
    if avg_change >= 500: return 85
    if avg_change >= 1: return 70
    if avg_change >= -200: return 50
    if avg_change >= -500: return 25
    return 10
```

#### 6. Credit Utilization (10%)

```python
def credit_utilization_score():
    """Total balances / total limits. 0% = 100, 30% = 0."""
    total_balance = sum(c.current_balance for c in get_credit_cards())
    total_limit = sum(c.credit_limit for c in get_credit_cards())
    if total_limit == 0:
        return 100
    util_pct = (total_balance / total_limit) * 100
    return max(0, 100 - (util_pct * 3.33))
```

#### 7. Rewards Efficiency (5%)

```python
def rewards_efficiency_score():
    """% of transactions on the optimal card."""
    transactions = query_credit_card_transactions(month=current_month)
    optimal_count = sum(1 for t in transactions if is_optimal_card(t))
    total = len(transactions)
    if total == 0:
        return 100
    return (optimal_count / total) * 100
```

### Score Interpretation

| Range | Rating | Emoji | Meaning |
|-------|--------|-------|---------|
| 90–100 | Excellent | 🏆 | All metrics green. Maintain course. |
| 75–89 | Good | ✅ | Minor areas for improvement. |
| 60–74 | Fair | ⚠️ | Several areas need attention. |
| 40–59 | Needs Work | 🔶 | Significant financial stress. |
| 0–39 | Critical | 🚨 | Immediate intervention required. |

### Actionable Recommendations Engine

After computing the score, identify the single highest-impact action:

```python
def get_top_recommendation(metrics):
    """Find the metric with lowest score × highest weight = biggest improvement potential."""
    potential = [(name, (100 - score) * weight) for name, score, weight in metrics]
    worst = max(potential, key=lambda x: x[1])
    
    recommendations = {
        "budget_adherence": "Tighten spending in [worst category]. Cook at home this week.",
        "emergency_fund": f"Transfer ${suggested_amount} to emergency fund this paycheck.",
        "debt_to_income": f"Add ${extra} extra to {highest_rate_debt}. Saves ${interest} in interest.",
        "savings_rate": "Increase 401k contribution by 1%. You won't notice it in take-home.",
        "net_worth_trajectory": "Review last month's unusual expenses. Prevent recurrence.",
        "credit_utilization": "Pay down card balance before statement close date.",
        "rewards_efficiency": f"Switch {category} purchases to {optimal_card}."
    }
    return recommendations[worst[0]]
```

### Monthly Health Report Format

```
🏥 Financial Health Score — [Month Year]

Overall: XX / 100 [emoji] (↑/→/↓ vs last month)

| Metric | Score | Weight | Contribution | Status |
|--------|-------|--------|--------------|--------|
| Budget Adherence | XX | 20% | XX.X | 🟢🟡🔴 |
| Emergency Fund | XX | 20% | XX.X | 🟢🟡🔴 |
| Debt-to-Income | XX | 15% | XX.X | 🟢🟡🔴 |
| Savings Rate | XX | 15% | XX.X | 🟢🟡🔴 |
| Net Worth Trend | XX | 15% | XX.X | 🟢🟡🔴 |
| Credit Utilization | XX | 10% | XX.X | 🟢🟡🔴 |
| Rewards Efficiency | XX | 5% | XX.X | 🟢🟡🔴 |

🎯 Top recommendation: [actionable suggestion]
📈 Best metric: [name] at [score] — keep it up!
📉 Biggest opportunity: [name] at [score] — [specific advice]
```

---

## Cron Automations

This skill adds 7 new cron jobs. These are IN ADDITION to the 7 crons in `financial-automation`.

### 8. Cash Flow 14-Day Forecast
- **Schedule**: Monday and Thursday 7:00 AM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Load `cash_flow_calendar.json`. Get current checking balance from Accounts DB. Project next 14 days of inflows/outflows. Send forecast via Google Chat.
- **Alert threshold**: Projected balance below $1,500 at any point → 🔴 warning with suggested action.

### 9. Monthly Net Worth Snapshot
- **Schedule**: 1st of month, 9:00 AM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Execute Module A snapshot procedure. Create Net Worth Snapshots DB row. Calculate MoM change. Send summary via Google Chat. Check milestone triggers.

### 10. Debt Progress Update
- **Schedule**: 1st of month, 10:00 AM CT (runs after net worth snapshot)
- **Model**: Gemini 2.5 Flash
- **Action**: Update Debts DB balances. Recalculate payoff dates. Compute interest saved from extra payments. Send debt dashboard via Google Chat.

### 11. Freedom Flex Quarterly Activation Reminder
- **Schedule**: 15th of March, June, September, December — 9:00 AM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Check if next quarter's Freedom Flex 5% category is known. Send reminder to activate at chase.com/freedom. Update `chase_rewards.json` with new categories when announced.
- **Message**: "🔔 Freedom Flex Q[X] activation window opens soon! Categories: [X]. Activate NOW at chase.com/freedom — it's free money you'll lose if you forget."

### 12. Weekly Rewards Optimization Check
- **Schedule**: Sunday 8:15 PM CT (runs 15 minutes after the weekly spending scorecard)
- **Model**: Gemini 2.5 Flash
- **Action**: Scan this week's credit card transactions. Compare card used vs optimal card per category. Report any wrong-card usage with value left on the table.
- **Message format**:
  ```
  💳 Rewards Check — Week of [dates]
  
  Optimal card usage: XX% (X of Y transactions)
  
  ⚠️ Wrong card spotted:
  - [Merchant] $XX on [card used] → should be [optimal card] (lost $X.XX)
  
  UR Points earned this week: ~X,XXX (worth ~$XX.XX)
  ```

### 13. Financial Health Score (Monthly)
- **Schedule**: 2nd of month, 8:00 PM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Execute Module E full scoring. Store score in Net Worth Snapshots DB. Send health report via Google Chat.

### 14. Bonus Paycheck Alert
- **Schedule**: Daily check at 8:00 AM CT (only fires in bonus paycheck months)
- **Model**: Gemini 2.5 Flash
- **Action**: Check if the current week contains a 3rd biweekly paycheck for the month. If yes, send allocation recommendation 3 days before payday.
- **Message**: "💰 BONUS PAYCHECK incoming on [Friday date]! This is paycheck #3 this month — $2,860 extra. Recommended split: $1,430 → emergency fund, $858 → [highest debt], $572 → investments."
- **Efficiency**: Only compute in months identified as bonus months. Skip all other months.

---

## Cron Summary (All 14 Jobs)

| # | Job | Schedule | Skill |
|---|-----|----------|-------|
| 1 | Weekly Spending Scorecard | Sun 8:00 PM | financial-automation |
| 2 | Dining Tripwire Alert | Daily 9:00 PM | financial-automation |
| 3 | Monthly Subscription Audit | 1st 10:00 AM | financial-automation |
| 4 | Bill-Pay Verification | 2nd 9:00 AM | financial-automation |
| 5 | Emergency Fund Tracker | 15th & last day 8:00 PM | financial-automation |
| 6 | ~~Bar Mitzvah Tracker~~ | ~~Daily 8:00 AM~~ | financial-automation (expired) |
| 7 | Statement Processor | Daily 10:00 PM | financial-automation |
| 8 | Cash Flow 14-Day Forecast | Mon/Thu 7:00 AM | **financial-planner** |
| 9 | Monthly Net Worth Snapshot | 1st 9:00 AM | **financial-planner** |
| 10 | Debt Progress Update | 1st 10:00 AM | **financial-planner** |
| 11 | Freedom Flex Activation Reminder | Quarterly (Mar/Jun/Sep/Dec 15th) | **financial-planner** |
| 12 | Weekly Rewards Optimization | Sun 8:15 PM | **financial-planner** |
| 13 | Financial Health Score | 2nd 8:00 PM | **financial-planner** |
| 14 | Bonus Paycheck Alert | Daily 8:00 AM (conditional) | **financial-planner** |

---

## Resource Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — instructions and architecture |
| `resources/cash_flow_calendar.json` | All recurring inflows/outflows mapped to calendar dates |
| `resources/chase_rewards.json` | Chase trifecta + all cards earning rules and optimal selection |
| `resources/credit_cards.json` | Full card portfolio with limits, fees, and features |
| `resources/debt_inventory.json` | All household debts with amortization data |
| `resources/investment_accounts.json` | Retirement and investment accounts with roadmap goals |
| `resources/financial_health_weights.json` | FHS metric definitions, weights, and scoring thresholds |

---

## Integration with financial-automation

This skill **reads from** but never **writes to** the databases owned by `financial-automation`:

| Database | Owner | This Skill's Access |
|----------|-------|---------------------|
| 🏦 Accounts | financial-automation | READ — balances for net worth, EF, cash flow |
| 📊 Budgets | financial-automation | READ — spending vs targets for budget adherence |
| 🧾 Transactions | financial-automation | READ — card usage for rewards check, spending data |
| 📄 Statements | financial-automation | READ — statement processing status |
| 📈 Net Worth Snapshots | **financial-planner** | READ/WRITE — monthly snapshots |
| 💳 Debts | **financial-planner** | READ/WRITE — debt tracking and payoff |

### Shared Data

- **Income data**: Both skills reference `budget_targets.json` from financial-automation for household income figures.
- **Account balances**: Both skills use the Accounts DB. financial-automation updates balances; this skill reads them.
- **Transaction data**: financial-automation categorizes transactions; this skill analyzes them for rewards optimization.

---

## Data Collection Checklist

Before all modules are fully operational, collect from Jon:

- [ ] Jon's most recent paycheck date (to project biweekly schedule)
- [ ] Mortgage: current balance, interest rate, original amount, term, start date
- [ ] Honda: current balance, interest rate, original amount, term
- [ ] Tesla: current balance, interest rate, original amount, term
- [ ] Student Loan: current balance, interest rate, servicer, federal vs private
- [ ] Jaime's Loan: current balance, interest rate, type, lender
- [ ] Jon's 401k: provider, contribution rate, employer match formula
- [ ] Jaime's 401k (Alight): contribution rate, employer match formula
- [ ] Schwab account: type (IRA vs brokerage), current balance
- [ ] Northwestern Mutual: current cash value
- [ ] Credit limits for all 6 cards
- [ ] Home value estimate (Zillow Zestimate or county assessment)
- [ ] Vehicle values (year/model for KBB lookup)
- [ ] Capital One Venture X: upgrade completion status
