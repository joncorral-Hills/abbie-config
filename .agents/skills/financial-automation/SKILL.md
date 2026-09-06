---
name: financial-automation
description: >
  Personal finance automation system. Creates and maintains a Notion-based budget 
  tracker with PDF statement parsing, automatic transaction categorization, and 
  weekly/monthly reporting via Google Chat. Manages budgets, tracks spending vs. 
  targets, and enforces financial discipline through alerts and audits.
requires:
  bins: [python3, pip]
  env: [NOTION_API_KEY]
---

# Financial Automation Skill

## Overview

This skill enables Abbie to function as Jon's personal finance automation layer:
1. **Notion Budget System**: 4 linked databases under the existing FINANCE page
2. **PDF Statement Processing**: Parse Chase and US Bank statements into categorized transactions
3. **Automated Alerts**: 7 cron jobs for spending reports, tripwires, and audits
4. **Merchant Intelligence**: Self-learning category mapping that improves over time

---

## Setup (One-Time)

### Step 1: Notion Database Creation

Create 4 databases under Jon's existing **FINANCE** page in Notion. Use the schema 
definitions in `resources/notion_schema.json`. Creation order matters due to relations:

1. **🏦 Accounts** (no dependencies)
2. **📊 Budgets** (no dependencies)
3. **📄 Statements** (no dependencies)
4. **🧾 Transactions** (relates to Budgets, Statements)

After creating all 4, go back and add:
- `Transactions` relation on Budgets (→ Transactions DB)
- `Spent` rollup on Budgets (sum of Amount from Transactions)
- `Transactions` relation on Statements (→ Transactions DB)
- `Transactions Imported` rollup on Statements (count from Transactions)
- `Total Amount` rollup on Statements (sum of Amount from Transactions)

### Step 2: Seed Budget Targets

Create rows in the Budgets database for June 2026 with these targets:

| Category | June Budget |
|----------|------------|
| Dining / Takeout | $500 |
| Groceries | $550 |
| Household / Target / Walmart | $300 |
| Kids Extras / Activities | $200 |
| Shopping / Personal | $200 |
| Entertainment / Random | $0 |
| Gas | $250 |

### Step 3: Seed Accounts

| Account | Type | Initial Balance |
|---------|------|----------------|
| Chase Checking | Checking | $3,100 |
| Emergency Savings | Savings | $8,250 |
| Chase Flex | Credit | $0 (paid in full monthly) |
| US Bank Checking | Checking | TBD (ask Jon) |

### Step 4: Install Python Dependencies

```bash
pip install pdfplumber
```

### Step 5: Deploy Cron Jobs

See the "Cron Automations" section below for all 7 jobs.

---

## PDF Statement Processing

### Workflow

1. **Trigger**: Daily cron (10 PM CT) checks Statements DB for `Status = Uploaded`
2. **Download**: Fetch PDF file from the Notion page via API
3. **Parse**: Run `scripts/parse_statement.py` with the PDF path and bank type
4. **Categorize**: Map each merchant to a budget category using `resources/merchant_categories.json`
   - Known merchants: instant lookup (no LLM cost)
   - Unknown merchants: classify with LLM, then cache the result
5. **Import**: Create Transaction rows in Notion, linked to Budget category and Statement
6. **Report**: Update Statement status to "Parsed" and send summary via Google Chat

### Bank-Specific Parsing

#### Chase (Credit Card — Chase Flex)
- Format: Date, Post Date, Description, Category, Type, Amount
- Amounts: Negative = purchase, Positive = payment/credit
- Key fields: Description (for merchant matching), Amount, Date

#### Chase (Checking)
- Format: Details, Posting Date, Description, Amount, Type, Balance, Check or Slip #
- Types: DEBIT, CHECK, DSLIP (deposit slip), ACH_CREDIT, ACH_DEBIT
- Note: Deposits are positive, debits are negative

#### US Bank (Checking/Savings)
- Format: Date, Description, Credit, Debit, Balance
- Separate credit/debit columns instead of signed amounts
- Description field contains payee and reference numbers

### Handling Edge Cases
- **Transfers between accounts**: Tag as "Transfer" category, do not count against budget
- **Recurring charges**: Auto-flag based on merchant_categories.json `recurring: true`
- **Refunds/credits**: Negative amounts reduce category spending
- **ATM withdrawals**: Tag as "Cash" — Jon should manually categorize later

---

## Cron Automations

### 1. Weekly Spending Scorecard
- **Schedule**: Sunday 8:00 PM CT
- **Model**: Gemini 3 Flash
- **Action**: Query Transactions DB for current week. Group by category. Compare to 
  weekly pro-rated budget (monthly target / 4.33). Send Google Chat message with 
  traffic-light status per category.
- **Message format**:
  ```
  📊 Week of [date range]
  Dining:     $XXX / $115  [🟢🟡🔴]
  Groceries:  $XXX / $127  [🟢🟡🔴]
  Household:  $XXX / $69   [🟢🟡🔴]
  ...
  Monthly pace: $X,XXX / $2,000 target
  ```

### 2. Dining Tripwire Alert
- **Schedule**: Daily 9:00 PM CT
- **Model**: Gemini 3 Flash
- **Action**: Sum dining category transactions for current calendar week (Mon–Sun). 
  If > $125, send immediate alert.
- **Message**: "⚠️ Dining hit $[amount] this week. $[remaining] left for the month. Cook tonight."

### 3. Monthly Subscription Audit
- **Schedule**: 1st of month, 10:00 AM CT
- **Model**: Kimi K2.6
- **Action**: Query Transactions DB for recurring charges. Compare against the 
  approved list in `resources/approved_subscriptions.json`. Flag new charges. 
  Remind about paused subscriptions.

### 4. Bill-Pay Verification
- **Schedule**: 2nd of month, 9:00 AM CT
- **Model**: Gemini 3 Flash
- **Action**: Check for expected drafts: mortgage ($2,145), ER payment ($150), 
  Chase Flex statement balance ($0 target). Report pass/fail.

### 5. Emergency Fund Tracker
- **Schedule**: 15th and last day of month, 8:00 PM CT
- **Model**: Gemini 3 Flash
- **Action**: Read Emergency Savings balance from Accounts DB. Compare to roadmap:
  - June: hold ~$6,900+
  - July: $8,900+ (post-bar mitzvah)
  - August: $11,000+
  - September: $12,000+
  Report balance, target, and weeks-of-runway.

### 6. Bar Mitzvah Tracker (Temporary)
- **Schedule**: Daily 8:00 AM CT, May 27 → June 6 only
- **Model**: Gemini 3 Flash
- **Action**: Query for bar mitzvah related transactions. Running tally vs. $6,141 cap.
- **Auto-delete**: Remove this cron after June 6.

### 7. Statement Processor
- **Schedule**: Daily 10:00 PM CT
- **Model**: Kimi K2.6
- **Action**: See "PDF Statement Processing" section above.

---

## Merchant Category Learning

The `resources/merchant_categories.json` file is a growing knowledge base. Rules:

1. **Exact match first**: Look up the merchant name exactly
2. **Fuzzy match second**: Normalize (uppercase, strip numbers/symbols) and retry
3. **LLM fallback**: If no match, ask the LLM to classify based on merchant name
4. **Cache the result**: Add the new mapping to the JSON file
5. **Periodic review**: Every month, output new mappings for Jon to confirm

Never delete a cached mapping. If Jon corrects a category, update it in place.

---

## Monthly Maintenance

At the start of each month:
1. Create new Budget rows for the new month (copy targets from previous month)
2. Update Account balances from latest statements
3. Archive previous month's Budget rows (set a "Month" property)
4. Review and confirm new merchant mappings

---

## Files in This Skill

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — instructions and architecture |
| `scripts/parse_statement.py` | PDF parsing script for Chase and US Bank |
| `resources/notion_schema.json` | Notion database property definitions |
| `resources/merchant_categories.json` | Merchant → category mapping cache |
| `resources/approved_subscriptions.json` | Approved recurring charges list |
| `resources/budget_targets.json` | Monthly budget targets by category |
