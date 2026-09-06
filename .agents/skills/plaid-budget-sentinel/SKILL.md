---
name: plaid-budget-sentinel
description: >
  Real-time bank transaction sync via Plaid API. Auto-fetches transactions,
  dynamically categorizes spending using Plaid AI + merchant intelligence,
  and alerts on subscription price hikes via Telegram. Replaces manual PDF
  statement processing with zero-touch automation.
requires:
  bins: [python3]
  env: [PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ACCESS_TOKENS, NOTION_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]
---

# Plaid Budget Sentinel

## Overview

This skill replaces the manual PDF statement processing flow in `financial-automation`
with a real-time, zero-touch bank connection via the Plaid API. It provides three
core capabilities:

1. **Transaction Sync** — Auto-fetches transactions from all linked bank accounts
   every 6 hours, categorizes them with a dual-layer system (Plaid AI + merchant
   intelligence), and writes them directly to the Notion Transactions DB.
2. **Subscription Sentinel** — Monitors recurring transaction streams for price
   hikes, detects unknown new subscriptions, and identifies cancellations. Alerts
   via Telegram in real-time.
3. **Balance Tracking** — Pulls real-time account balances daily and updates the
   Notion Accounts DB, feeding accurate data into cash flow forecasting.

**Dependency**: Requires `financial-automation` to be active. This skill writes to
the Transactions and Accounts databases created by that skill.

---

## Architecture

```
Plaid API
  ├── /transactions/sync ──────→ plaid_client.py ──→ Notion Transactions DB
  │                                                    ↓
  │                              (feeds all financial-automation crons:
  │                               weekly scorecard, dining tripwire,
  │                               subscription audit, rewards optimizer)
  │
  ├── /transactions/recurring/get → subscription_sentinel.py ──→ Telegram
  │                                   ↓
  │                                 Price hike alerts
  │                                 New subscription alerts
  │                                 Daily summary
  │
  └── /accounts/balance/get ───→ plaid_client.py ──→ Notion Accounts DB
                                                       ↓
                                                     (feeds financial-planner:
                                                      cash flow forecast,
                                                      net worth snapshot,
                                                      emergency fund tracker)
```

### Data Flow

```
Jon's Banks (Chase, US Bank, Capital One)
       ↓ (OAuth via Plaid Link — one-time setup)
Plaid API (aggregates all accounts)
       ↓ (cursor-based sync every 6 hours)
plaid_client.py
  ├── CategoryMapper (Plaid PFC v2 + merchant_categories.json)
  └── NotionTransactionWriter
       ↓
Notion Transactions DB (shared with financial-automation)
       ↓
All existing crons read from this DB unchanged
```

---

## Setup (One-Time)

### Step 1: Plaid Developer Account

Jon has already created his account at [dashboard.plaid.com](https://dashboard.plaid.com).

- **Client ID**: stored in `PLAID_CLIENT_ID` env var
- **Production Secret**: stored in `PLAID_SECRET` env var
- **Plan**: Trial (free, up to 10 Items)

### Step 2: Install Dependencies

```bash
pip install plaid-python flask requests
```

### Step 3: Store Environment Variables

Add to `~/.bashrc` or Allie's `.env`:

```bash
export PLAID_CLIENT_ID="<from Plaid Dashboard>"
export PLAID_SECRET="<from Plaid Dashboard>"
export PLAID_ENV="production"
# PLAID_ACCESS_TOKENS gets set after Step 5
```

### Step 4: Run Plaid Link Server

```bash
python scripts/plaid_link_server.py
```

This starts a temporary Flask server on port 8443. Send Jon the URL.

### Step 5: Jon Connects Banks

Jon opens the URL in his browser and clicks "Connect Bank" for each institution:

1. **Chase** (covers: Sapphire Reserve, Freedom Flex, Freedom Unlimited, Checking)
2. **US Bank** (covers: Checking, Savings)
3. **Capital One** (covers: Venture X)
4. **Amazon** (if separate from Chase — covers: Prime Card)

After connecting all banks, Jon clicks "Done — Generate Config." The server outputs
the `PLAID_ACCESS_TOKENS` environment variable to set.

### Step 6: Set Access Tokens

```bash
export PLAID_ACCESS_TOKENS='{"chase":"access-production-xxx","usbank":"access-production-yyy",...}'
```

### Step 7: Shut Down Link Server

The server shuts itself down after the Done step. It's never used again.

### Step 8: Update Notion Transaction Schema

Add `Plaid Sync` as an option to the `Source` select property in the Transactions DB.

### Step 9: Verify Connection

```bash
python scripts/plaid_client.py balances
python scripts/plaid_client.py sync
```

Confirm transactions appear in the Notion Transactions DB.

### Step 10: Deploy Crons

See the "Cron Automations" section below for the 3 new jobs.

---

## Transaction Sync Flow

Triggered by Cron #15 (every 6 hours) or manually via CLI.

1. Load access tokens from `PLAID_ACCESS_TOKENS` env var
2. For each institution:
   a. Load cursor from `~/.hermes/plaid_cursors.json` (or start with no cursor)
   b. Call `/transactions/sync` with cursor — loop until `has_more` is False
   c. For each **added** transaction:
      - Check deduplication: search Notion Notes field for `plaid_txn_id`
      - Map category using dual-layer system (see "Category Mapping" below)
      - Map account name to Notion select option
      - Write to Notion Transactions DB with `Source = "Plaid Sync"`
   d. For each **modified** transaction:
      - Find existing Notion page by plaid_txn_id
      - Update amount, date, or category if changed
   e. For each **removed** transaction:
      - Log the removal (don't delete from Notion — may be useful for audit)
   f. Save updated cursor
3. Log summary: X added, Y modified, Z removed

### Sync Output Example

```
[2026-07-16 18:00:01] Syncing Chase...
  Added: 12 transactions
  Modified: 1 transaction
  Removed: 0 transactions
[2026-07-16 18:00:03] Syncing US Bank...
  Added: 5 transactions
  Modified: 0 transactions
  Removed: 0 transactions
Total: 17 new, 1 modified, 0 removed
```

---

## Subscription Sentinel Flow

Triggered by Cron #16 (daily at 9 AM CT) or manually via CLI.

1. Fetch recurring transaction streams from all institutions via
   `/transactions/recurring/get`
2. **Price Hike Detection**: For each MATURE outflow stream, compare
   `last_amount` against `average_amount`. Flag if:
   - Dollar delta > $1.00 AND
   - Percentage increase > 5%
3. **New Subscription Detection**: Compare stream merchants against
   `approved_subscriptions.json` and `subscription_baselines.json`.
   Flag streams not found in either list.
4. **Cancellation Detection**: Compare `subscription_baselines.json`
   against current streams. If a baseline entry has no matching current
   stream, it may have been cancelled.
5. **Alert**: Send Telegram messages for any findings
6. **Daily Summary**: Always send a summary of active subscriptions and
   total monthly recurring cost
7. **Update Baselines**: Save current stream data for future comparison

---

## Balance Tracking Flow

Triggered by Cron #17 (daily at 7 AM CT) or manually via CLI.

1. Fetch real-time balances from all institutions via `/accounts/balance/get`
2. Map each Plaid account to the Notion Accounts DB entry
3. Update `Current Balance` and `Last Updated` fields
4. This feeds into:
   - Cash Flow 14-Day Forecast (financial-planner Module B)
   - Emergency Fund Tracker (financial-automation Cron #5)
   - Net Worth Snapshot (financial-planner Module A)

---

## Category Mapping

Dual-layer approach for maximum accuracy:

### Layer 1: Merchant Override (Jon-specific)

Check `merchant_categories.json` from `financial-automation`. This file contains
Jon's personal merchant→category mappings built over time:

```
"TARGET" → "Household / Target / Walmart"
"DOORDASH" → "Dining / Takeout"
"COSTCO" → "Groceries"
```

Merchant name is normalized: uppercase, strip trailing numbers and reference codes.

### Layer 2: Plaid PFC v2

If no merchant override exists, use the Plaid Personal Finance Category:

1. Check `detailed_overrides` in `plaid_category_map.json` first
   (e.g., `FOOD_AND_DRINK_GROCERIES` → "Groceries")
2. Fall back to `primary` mapping
   (e.g., `FOOD_AND_DRINK` → "Dining / Takeout")

### Layer 3: Fallback

If neither layer matches: `Uncategorized`.

Unknown merchants should be logged for periodic review and eventual addition
to `merchant_categories.json`.

---

## Cron Automations

This skill adds 3 new cron jobs (#15–#17). These extend the existing 14 crons
from `financial-automation` and `financial-planner`.

### 15. Plaid Transaction Sync

- **Schedule**: Every 6 hours (12:00 AM, 6:00 AM, 12:00 PM, 6:00 PM CT)
- **Model**: Gemini 3 Flash
- **Action**: Run `python scripts/plaid_client.py sync`. Log results.
  No alerts unless errors occur.
- **Hermes cron config**:
  ```
  schedule: "0 0,6,12,18 * * *"
  command: "cd ~/.hermes/skills/plaid-budget-sentinel && python scripts/plaid_client.py sync"
  ```

### 16. Subscription Sentinel

- **Schedule**: Daily 9:00 AM CT
- **Model**: Gemini 3 Flash
- **Action**: Run `python scripts/subscription_sentinel.py scan`.
  Sends Telegram alerts for price hikes, new subs, and cancellations.
  Always sends daily summary.
- **Hermes cron config**:
  ```
  schedule: "0 9 * * *"
  command: "cd ~/.hermes/skills/plaid-budget-sentinel && python scripts/subscription_sentinel.py scan"
  ```

### 17. Balance Snapshot

- **Schedule**: Daily 7:00 AM CT
- **Model**: Gemini 3 Flash
- **Action**: Run `python scripts/plaid_client.py balances --update-notion`.
  Updates Accounts DB with real-time balances.
- **Hermes cron config**:
  ```
  schedule: "0 7 * * *"
  command: "cd ~/.hermes/skills/plaid-budget-sentinel && python scripts/plaid_client.py balances --update-notion"
  ```

---

## What This Replaces

| Old Component | Status | Notes |
|---------------|--------|-------|
| Cron #7 (Statement Processor) | **DISABLED** | Plaid sync replaces PDF parsing |
| Cron #3 (Monthly Subscription Audit) | **DISABLED** | Daily Sentinel replaces monthly audit |
| Manual PDF uploads | **ELIMINATED** | No human action needed |
| Manual balance entry | **ELIMINATED** | API pulls real-time balances |
| `parse_statement.py` | **KEPT (fallback)** | Available for edge cases but not scheduled |

---

## Integration with financial-automation

| Database | Owner | This Skill's Access |
|----------|-------|---------------------|
| 🧾 Transactions | financial-automation | **WRITE** — adds new transactions with Source="Plaid Sync" |
| 🏦 Accounts | financial-automation | **WRITE** — updates balances daily |
| 📊 Budgets | financial-automation | **READ** — category matching for transaction linking |
| 📄 Statements | financial-automation | **NONE** — no longer used for ingestion |

### Shared Resources

- `merchant_categories.json` from financial-automation: read-only for category overrides
- `approved_subscriptions.json` from financial-automation: read-only for subscription validation
- `budget_targets.json` from financial-automation: not used directly

---

## Cron Summary (All 17 Jobs)

| # | Job | Schedule | Skill |
|---|-----|----------|-------|
| 1 | Weekly Spending Scorecard | Sun 8:00 PM | financial-automation |
| 2 | Dining Tripwire Alert | Daily 9:00 PM | financial-automation |
| 3 | ~~Monthly Subscription Audit~~ | ~~1st 10:00 AM~~ | ~~financial-automation~~ **(replaced by #16)** |
| 4 | Bill-Pay Verification | 2nd 9:00 AM | financial-automation |
| 5 | Emergency Fund Tracker | 15th & last day 8:00 PM | financial-automation |
| 6 | ~~Bar Mitzvah Tracker~~ | ~~Daily 8:00 AM~~ | financial-automation (expired) |
| 7 | ~~Statement Processor~~ | ~~Daily 10:00 PM~~ | ~~financial-automation~~ **(replaced by #15)** |
| 8 | Cash Flow 14-Day Forecast | Mon/Thu 7:00 AM | financial-planner |
| 9 | Monthly Net Worth Snapshot | 1st 9:00 AM | financial-planner |
| 10 | Debt Progress Update | 1st 10:00 AM | financial-planner |
| 11 | Freedom Flex Activation Reminder | Quarterly | financial-planner |
| 12 | Weekly Rewards Optimization | Sun 8:15 PM | financial-planner |
| 13 | Financial Health Score | 2nd 8:00 PM | financial-planner |
| 14 | Bonus Paycheck Alert | Daily 8:00 AM (conditional) | financial-planner |
| **15** | **Plaid Transaction Sync** | **Every 6 hours** | **plaid-budget-sentinel** |
| **16** | **Subscription Sentinel** | **Daily 9:00 AM** | **plaid-budget-sentinel** |
| **17** | **Balance Snapshot** | **Daily 7:00 AM** | **plaid-budget-sentinel** |

---

## Files in This Skill

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — instructions and architecture |
| `scripts/plaid_client.py` | Core Plaid API client, category mapper, Notion writer, CLI |
| `scripts/subscription_sentinel.py` | Price hike detection, Telegram alerts, baseline tracking |
| `scripts/plaid_link_server.py` | One-time Flask server for Plaid Link bank connection |
| `resources/plaid_category_map.json` | Plaid PFC v2 → Allie budget category mapping |
| `resources/subscription_baselines.json` | Tracked subscription amounts for delta detection |

---

## Troubleshooting

### "ITEM_LOGIN_REQUIRED" error
The bank connection has gone stale (rare, but happens). Jon needs to re-authenticate:
1. Run `python scripts/plaid_link_server.py`
2. Reconnect the affected bank
3. Update the access token in `PLAID_ACCESS_TOKENS`

### Transactions not appearing in Notion
1. Check `python scripts/plaid_client.py sync` output for errors
2. Verify `TRANSACTIONS_DB_ID` env var matches the correct Notion database
3. Check Notion API key has write access to the database

### Telegram alerts not sending
1. Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` env vars are set
2. Test with: `curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" -d "chat_id=$TELEGRAM_CHAT_ID&text=test"`

### Cursor stuck / duplicate transactions
Delete `~/.hermes/plaid_cursors.json` to force a full re-sync. Deduplication via
plaid_transaction_id in the Notes field prevents actual duplicates in Notion.
