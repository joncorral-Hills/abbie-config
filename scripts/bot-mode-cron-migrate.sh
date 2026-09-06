#!/usr/bin/env bash
# bot-mode-cron-migrate.sh — Phase 2: Migrate crons to specialist bot profiles
# Execution: Allie runs this on the VM after Phase 1 profiles are confirmed
# Strategy: Create new crons under bot profiles FIRST, then delete old ones
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
BACKUP_DIR="$HERMES_HOME/cron-migration-backup"
mkdir -p "$BACKUP_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "══════════════════════════════════════════════"
echo "  🔄 Bot Mode — Phase 2: Cron Migration"
echo "══════════════════════════════════════════════"
echo ""

# ─── n8n External Workflows (Mac Mini) ───────────
echo "▶ n8n Workflows on Mac Mini (192.168.1.143:5678)"
echo "  These run OUTSIDE Hermes — do NOT duplicate them as bot crons:"
echo ""
echo "  📋 Workflow 1: Morning Briefing (7 AM daily)"
echo "     → Thermostat temps, weather, calendar → Telegram"
echo "     ⚠️  Overlaps with: CAL2 calendar cron (calendar portion)"
echo "     ⚠️  Overlaps with: drive-health-reader (morning system check)"
echo ""
echo "  📋 Workflow 2: Smart Notion Relay (every 30s)"
echo "     → Intercepts deterministic relay tasks (ha_state, ha_trigger, shell)"
echo "     → Only passes complex/reasoning tasks to Allie"
echo ""
echo "  📋 Workflow 3: HA Event Reactor (webhook-driven)"
echo "     → Temperature alerts, presence changes, device offline → Telegram"
echo ""
echo "  ℹ️  CAL2 calendar cron will be created with REDUCED scope"
echo "     (Allie handles scheduling conflicts + smart briefing;"
echo "      n8n handles the raw calendar/weather/thermostat data push)"
echo ""

# ─── Step 1: Backup current crons ────────────────
echo "▶ Step 1: Backing up current cron list..."
hermes cron list > "$BACKUP_DIR/crons_before_${TIMESTAMP}.txt" 2>&1 || true
echo "  ✅ Backup saved to $BACKUP_DIR/crons_before_${TIMESTAMP}.txt"
echo ""
echo "  Current crons:"
hermes cron list 2>/dev/null || echo "  (could not list crons)"
echo ""

# ─── Step 2: Verify all profiles exist ───────────
echo "▶ Step 2: Verifying bot profiles exist..."
REQUIRED_PROFILES=(finance-bot health-bot home-bot storefront-bot market-bot)
MISSING=0
for prof in "${REQUIRED_PROFILES[@]}"; do
    if hermes profile list 2>/dev/null | grep -q "$prof"; then
        echo "  ✅ $prof"
    else
        echo "  ❌ $prof — MISSING"
        MISSING=1
    fi
done
if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "❌ Some profiles are missing. Run scripts/bot-mode-activate.sh first."
    exit 1
fi
echo ""

# ─── Step 3: Create new crons under bot profiles ─
echo "▶ Step 3: Creating crons under bot profiles..."
echo "  (Old crons remain active until Step 4)"
echo ""

# Helper function: create a cron on a profile, skip if similar already exists
create_bot_cron() {
    local profile="$1"
    local name="$2"
    local schedule="$3"
    local model="$4"
    local prompt="$5"

    echo "  📋 [$profile] $name"
    echo "     Schedule: $schedule | Model: $model"

    # Check if a cron with this name already exists on the profile
    if hermes -p "$profile" cron list 2>/dev/null | grep -qi "$name"; then
        echo "     ⚠️  Already exists — skipping"
        return 0
    fi

    hermes -p "$profile" cron create "$name" \
        --schedule "$schedule" \
        --model "$model" \
        --prompt "$prompt" 2>/dev/null && echo "     ✅ Created" || echo "     ❌ Failed"
}

# ── Finance Bot crons ──
echo "  ── finance-bot ──"

create_bot_cron "finance-bot" \
    "[bot:finance-bot] Monthly Financial Update" \
    "0 9 1 * *" \
    "llama-local" \
    "Run the monthly financial update. Parse any new bank statements, categorize transactions, update budget tracking in Notion, and generate the monthly financial summary. Report findings via Telegram."

create_bot_cron "finance-bot" \
    "[bot:finance-bot] Weekly Cost Review" \
    "30 7 * * 1" \
    "gemini-local" \
    "Run the weekly cost review. Summarize this week's spending by category, flag any unusual transactions or budget overages, and report via Telegram."

create_bot_cron "finance-bot" \
    "[bot:finance-bot] TX1 Monthly Tax Review" \
    "0 10 1 * *" \
    "llama-local" \
    "Run the monthly tax review. Check for new deductible expenses, update quarterly estimated tax calculations, and compare itemized vs standard deduction. Report via Telegram."

create_bot_cron "finance-bot" \
    "[bot:finance-bot] TX2 Quarterly Tax Estimate" \
    "0 10 15 3,6,9,12 *" \
    "llama-local" \
    "Calculate the quarterly estimated tax obligation. Review YTD income, withholdings, and deductions. Determine if additional estimated payment is needed. Report via Telegram."

create_bot_cron "finance-bot" \
    "[bot:finance-bot] TX3 Annual Tax Prep" \
    "0 10 15 1 *" \
    "llama-local" \
    "Run annual tax prep review. Compile all deductions, income sources, and tax documents needed for filing. Generate a tax prep summary. Report via Telegram."

echo ""

# ── Health Bot crons ──
echo "  ── health-bot ──"

create_bot_cron "health-bot" \
    "[bot:health-bot] Hevy Daily Sync" \
    "0 10 * * *" \
    "gemini-local" \
    "Sync today's workouts from the Hevy API. Check for new workouts via the events endpoint, update the Notion Workouts database with exercises, sets, reps, and weights. Update PRs if any new records were set. Report new workouts via Telegram."

create_bot_cron "health-bot" \
    "[bot:health-bot] Body Metrics Sync" \
    "0 8 * * 0" \
    "gemini-local" \
    "Sync body measurements from Hevy API. Update the Notion Body Metrics database with latest weight, body fat percentage, and measurements. Report via Telegram."

create_bot_cron "health-bot" \
    "[bot:health-bot] Weekly Training Intelligence" \
    "0 19 * * 0" \
    "gemini-local" \
    "Generate the weekly training intelligence report. Analyze this week's workout volume, intensity, progressive overload trends, muscle group balance, and recovery patterns. Compare against previous weeks. Report via Telegram."

create_bot_cron "health-bot" \
    "[bot:health-bot] Drive Health Reader" \
    "0 8,18 * * *" \
    "gemini-local" \
    "Check drive health SMART data. Read and parse drive health metrics, flag any concerning indicators (reallocated sectors, pending sectors, temperature anomalies). Report issues via Telegram."

create_bot_cron "health-bot" \
    "[bot:health-bot] Weekly Fitness Overview" \
    "15 7 * * 1" \
    "gemini-local" \
    "Generate the weekly fitness overview. Summarize workouts completed this week, total volume, consistency score, and notable achievements. Report via Telegram."

echo ""

# ── Home Bot crons ──
echo "  ── home-bot ──"

create_bot_cron "home-bot" \
    "[bot:home-bot] Weekly Home Maintenance" \
    "0 7 * * 1" \
    "gemini-local" \
    "Check the home maintenance schedule. List any tasks due this week, upcoming seasonal maintenance items, and overdue tasks. Report via Telegram."

create_bot_cron "home-bot" \
    "[bot:home-bot] Seasonal Home Prep" \
    "0 9 1 3,6,9,12 *" \
    "gemini-local" \
    "Run the seasonal home maintenance prep review. Based on the current season and Kansas City zone 6a climate, list upcoming seasonal tasks, preventive maintenance items, and any vendor appointments needed. Report via Telegram."

echo ""

# ── Default (coordinator) crons ──
echo "  ── default (coordinator) ──"

# LS1 and CAL2 stay on default but get the [bot:default] namespace
create_bot_cron "default" \
    "[bot:default] Monthly Life Score" \
    "0 21 3 * *" \
    "gemini-local" \
    "Calculate the monthly Life Score. Read the latest Financial Health Score, Composite Health Score, and Growth Score. Compute the weighted composite Life Score (0-100). Compare against previous months and identify the highest-impact area to focus on. Report via Telegram."

create_bot_cron "default" \
    "[bot:default] Calendar Sync" \
    "0 8 * * *" \
    "llama-local" \
    "Run the daily calendar intelligence check. NOTE: n8n on the Mac Mini already sends raw calendar events, weather, and thermostat data to Telegram at 7 AM. Your job is the SMART layer on top: detect scheduling conflicts between work and personal calendars, flag double-bookings, identify prep needed for upcoming appointments, and alert on any calendar changes since yesterday. Do NOT duplicate the raw event list that n8n already sent. Report only actionable insights via Telegram."

echo ""

# ─── Step 4: Verify new crons ────────────────────
echo "▶ Step 4: Verifying new crons..."
echo ""
echo "  finance-bot crons:"
hermes -p finance-bot cron list 2>/dev/null || echo "  (none)"
echo ""
echo "  health-bot crons:"
hermes -p health-bot cron list 2>/dev/null || echo "  (none)"
echo ""
echo "  home-bot crons:"
hermes -p home-bot cron list 2>/dev/null || echo "  (none)"
echo ""
echo "  default crons:"
hermes cron list 2>/dev/null || echo "  (none)"
echo ""

# ─── Step 5: Instructions for old cron cleanup ───
echo "══════════════════════════════════════════════"
echo "  ⚠️  Step 5: Manual Cleanup Required"
echo "══════════════════════════════════════════════"
echo ""
echo "  New crons have been created under bot profiles."
echo "  Old crons on the default profile need manual deletion."
echo ""
echo "  Run 'hermes cron list' to see old crons with their IDs,"
echo "  then delete each old one with:"
echo "    hermes cron delete <id>"
echo ""
echo "  Old crons to delete (by name):"
echo "    - Monthly Financial Update"
echo "    - weekly-cost-review"
echo "    - TX1/TX2/TX3 (tax crons)"
echo "    - hevy-daily-sync"
echo "    - hevy-body-metrics-sync"
echo "    - weekly-training-intelligence"
echo "    - drive-health-reader"
echo "    - weekly-fitness-overview"
echo "    - HM1 - Weekly Home Maint"
echo "    - HM2 - Seasonal Home Maint Prep"
echo "    - LS1 - Monthly Life Score (if re-created as [bot:default])"
echo "    - CAL2 (if re-created as [bot:default])"
echo ""
echo "  KEEP old crons running until you confirm new ones fire correctly."
echo "  The old and new will run in parallel briefly — that's fine."
echo ""

# Save post-migration state
hermes cron list > "$BACKUP_DIR/crons_after_${TIMESTAMP}.txt" 2>&1 || true

echo "══════════════════════════════════════════════"
echo "  ✅ Phase 2 Complete — New crons created!"
echo "══════════════════════════════════════════════"
echo ""
echo "  Backup: $BACKUP_DIR/"
echo "  Next: Verify new crons fire, then delete old duplicates."
