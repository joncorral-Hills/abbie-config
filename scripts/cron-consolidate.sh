#!/usr/bin/env bash
# cron-consolidate.sh — Collapse bot fleet to single-profile architecture
#
# What this does:
#   1. Backs up all existing state (profiles, crons, config)
#   2. Deletes all crons across all profiles
#   3. Creates 17 consolidated crons on the default profile
#   4. Installs system crontab for sweeper + heartbeat
#   5. Installs unified SOUL.md
#   6. Disables bot_mode_protocol
#   7. Deletes specialist profiles
#
# Execution: Allie pulls from git and runs this on the VM
# Rollback: Restore from ~/.hermes/consolidation-backup-<timestamp>/
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR/.."
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$HERMES_HOME/consolidation-backup-${TIMESTAMP}"

# Model aliases
DEEPSEEK="openrouter/deepseek/deepseek-v4-flash"
GEMINI="gemini-local"

echo "══════════════════════════════════════════════"
echo "  🔧 Bot Fleet Consolidation"
echo "  $(date)"
echo "══════════════════════════════════════════════"
echo ""

# ─── Pre-flight ───────────────────────────────────
echo "▶ Pre-flight checks..."

if ! command -v hermes &>/dev/null; then
    echo "❌ hermes not found in PATH"
    exit 1
fi

echo "  Hermes version: $(hermes --version 2>/dev/null || echo 'unknown')"
echo "  ✅ All checks passed"
echo ""

# ─── Phase 0: Backup ─────────────────────────────
echo "▶ Phase 0: Backing up current state..."
mkdir -p "$BACKUP_DIR"

# Back up config
cp "$HERMES_HOME/config.yaml" "$BACKUP_DIR/config.yaml.bak" 2>/dev/null || true

# Back up SOUL
cp "$HERMES_HOME/SOUL.md" "$BACKUP_DIR/SOUL.md.bak" 2>/dev/null || true

# Back up all profile dirs
if [ -d "$HERMES_HOME/profiles" ]; then
    cp -r "$HERMES_HOME/profiles" "$BACKUP_DIR/profiles-backup"
    echo "  ✅ Profiles backed up"
fi

# Snapshot all crons across all profiles
echo "  Saving cron snapshots..."
hermes cron list > "$BACKUP_DIR/crons-default.txt" 2>&1 || true
for prof in finance-bot health-bot home-bot storefront-bot market-bot invent-bot job-bot ops-bot; do
    hermes -p "$prof" cron list > "$BACKUP_DIR/crons-${prof}.txt" 2>&1 || true
done
echo "  ✅ All state backed up to $BACKUP_DIR"
echo ""

# ─── Phase 1: Delete all existing crons ──────────
echo "▶ Phase 1: Clearing all crons across all profiles..."

delete_all_crons_for_profile() {
    local profile="$1"
    local profile_flag=""
    if [ "$profile" != "default" ]; then
        profile_flag="-p $profile"
    fi

    # Get cron IDs — try JSON first, then fall back to text parsing
    local cron_ids
    cron_ids=$(hermes $profile_flag cron list --json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    crons = data if isinstance(data, list) else data.get('crons', data.get('jobs', []))
    for c in crons:
        cid = c.get('id', c.get('cron_id', ''))
        if cid:
            print(cid)
except:
    pass
" 2>/dev/null || true)

    # Fallback: try plain text parsing with multiple patterns
    if [ -z "$cron_ids" ]; then
        cron_ids=$(hermes $profile_flag cron list 2>/dev/null | grep -oE '^\s*[0-9]+' | tr -d ' ' || true)
    fi

    if [ -z "$cron_ids" ]; then
        echo "    (no crons found or could not parse)"
        return 0
    fi

    for cid in $cron_ids; do
        if [ -n "$cid" ]; then
            hermes $profile_flag cron delete "$cid" --yes 2>/dev/null && \
                echo "    Deleted cron $cid" || \
                echo "    ⚠️  Could not delete cron $cid"
        fi
    done
}

for prof in default finance-bot health-bot home-bot storefront-bot market-bot invent-bot job-bot ops-bot; do
    echo "  Clearing $prof..."
    delete_all_crons_for_profile "$prof"
done
echo "  ✅ All crons cleared"
echo ""

# ─── Phase 2: Create consolidated crons on default ─
echo "▶ Phase 2: Creating 17 consolidated crons on default profile..."
echo ""

create_cron() {
    local name="$1"
    local schedule="$2"
    local model="$3"
    local prompt="$4"

    echo "  📋 $name"
    echo "     Schedule: $schedule | Model: $(basename $model)"

    # Hermes CLI: schedule is positional, not a flag
    hermes cron create "$name" "$schedule" \
        --model "$model" \
        --prompt "$prompt" 2>/dev/null && echo "     ✅ Created" || echo "     ❌ Failed"
}

# ── Finance crons (deepseek — handles financial data) ──
echo "  ── [FIN] Finance ──"

create_cron "[FIN] Plaid Daily Sync" \
    "0 7 * * *" \
    "$DEEPSEEK" \
    "Run Plaid daily sync. Fetch new transactions from all linked bank accounts via the Plaid API. Categorize each transaction using the merchant cache at ~/.hermes/skills/financial-automation/merchant_cache.json. Record new transactions to the Notion Transactions DB (FINANCE page 31e8275a). Flag any subscription price changes or unusual charges. Report a brief summary to Telegram: transaction count, total spending, and any alerts."

create_cron "[FIN] Weekly Cost Review" \
    "30 7 * * 1" \
    "$DEEPSEEK" \
    "Run the weekly cost review. Query the Notion Transactions DB for the past 7 days. Summarize spending by category (groceries, dining, gas, subscriptions, etc.). Compare against monthly budget targets. Flag any categories over 25% of monthly budget already spent. Report via Telegram with a clean table format."

create_cron "[FIN] Monthly Financial Update" \
    "0 9 1 * *" \
    "$DEEPSEEK" \
    "Run the monthly financial update. Parse any new bank statements available. Update budget tracking in the Notion FINANCE page (31e8275a). Calculate: total income, total expenses, savings rate, net worth change, debt paydown progress. Compare against previous month. Generate the monthly financial summary and report via Telegram."

create_cron "[FIN] TX2 Quarterly Tax Estimate" \
    "0 10 15 3,6,9,12 *" \
    "$DEEPSEEK" \
    "Calculate quarterly estimated tax obligation. Review YTD income from all sources, current withholdings, and qualifying deductions. Determine if an additional estimated tax payment is needed for this quarter. Compare itemized vs standard deduction running totals. Report the estimate and any recommended actions via Telegram."

create_cron "[FIN] TX3 Annual Tax Prep" \
    "0 10 15 1 *" \
    "$DEEPSEEK" \
    "Run annual tax prep review. Compile all deductions, income sources, and tax documents needed for filing. List all W-2s, 1099s, and deduction receipts collected vs missing. Generate a tax prep readiness summary with a checklist of outstanding items. Report via Telegram."

echo ""

# ── Health crons (deepseek — personal health data) ──
echo "  ── [HEALTH] Health ──"

create_cron "[HEALTH] Hevy Daily Sync" \
    "0 10 * * *" \
    "$DEEPSEEK" \
    "Sync today's workouts from the Hevy API. Check the events endpoint for new completed workouts. For each new workout: record exercises, sets, reps, and weights to the Notion Workouts database (Health & Fitness page 36d63d55-66c5-8125). Check if any new personal records (PRs) were set and update the PRs database. Report new workouts via Telegram with exercise names, volume, and any PRs."

create_cron "[HEALTH] Body Metrics Sync" \
    "0 8 * * 0" \
    "$DEEPSEEK" \
    "Sync body measurements from the Hevy API. Pull latest weight, body fat percentage, and any measurements. Update the Notion Body Metrics database. Calculate weekly trend (up/down/stable). Report via Telegram with current stats and 4-week trend."

create_cron "[HEALTH] Weekly Fitness & Training Report" \
    "15 7 * * 1" \
    "$DEEPSEEK" \
    "Generate the combined weekly fitness and training intelligence report. Cover: (1) Workouts completed this week — exercises, total volume, consistency score. (2) Progressive overload analysis — weight/rep increases vs last week. (3) Muscle group balance — check for neglected groups. (4) Recovery patterns — rest day spacing, workout duration trends. (5) Notable achievements and PRs. (6) Comparison against previous 4 weeks. Report via Telegram."

echo ""

# ── Home crons (gemini-local — no PII) ──
echo "  ── [HOME] Home ──"

create_cron "[HOME] Travel Price Watch" \
    "0 6 * * *" \
    "$GEMINI" \
    "Monitor flight and hotel prices for any upcoming trips in the travel watchlist. Check for price drops or deals. If a significant price change is detected (>10% drop), alert via Telegram with the current price, previous price, and booking recommendation."

create_cron "[HOME] Weekly Home Maintenance" \
    "0 7 * * 1" \
    "$GEMINI" \
    "Check the home maintenance schedule for the Corral household in Kansas City metro (USDA Zone 6a). List tasks due this week, upcoming seasonal items, and any overdue tasks. Include estimated time and difficulty for each task. Report via Telegram."

create_cron "[HOME] Seasonal Home Prep" \
    "0 9 1 3,6,9,12 *" \
    "$GEMINI" \
    "Run the quarterly seasonal home maintenance prep for Kansas City metro (Zone 6a). Based on the upcoming season, list: HVAC service needs, gutter/roof inspection, lawn/sprinkler prep, winterization or spring startup tasks, and any vendor appointments to schedule. Report via Telegram."

echo ""

# ── Market crons (deepseek — complex analysis) ──
echo "  ── [MKT] Market ──"

create_cron "[MKT] Stock Weekly Briefing" \
    "30 8 * * 2,4" \
    "$DEEPSEEK" \
    "Generate the stock market briefing. Cover: (1) Robinhood agentic account portfolio overview — current positions, P/L, buying power. (2) Position updates — price changes since last briefing. (3) Watchlist movers — notable price or volume changes. (4) Macro context — any major market events, Fed actions, or sector rotation signals. Keep it concise. Report via Telegram."

echo ""

# ── Ops crons (gemini-local — system monitoring, not personal data) ──
echo "  ── [OPS] Ops ──"

create_cron "[OPS] Daily System Health Check" \
    "0 5 * * *" \
    "$GEMINI" \
    "Run the combined daily system health check. Perform ALL of the following:

1. HEARTBEAT: Ping these endpoints and report status:
   - Bridge API: http://localhost:8787/health
   - gemini-local: http://localhost:8081/health
   - llama-local: http://localhost:8082/health
   - Check Telegram API connectivity
   - Check Notion API connectivity

2. CRON AUDIT: List all Hermes crons, check for missed or stuck executions in the last 24 hours. Report any crons that failed to fire or are stuck in 'running' state.

3. API AUDIT: Verify API keys are valid and not near expiration for: Plaid, Hevy, OpenRouter, Notion, Robinhood MCP, Firecrawl.

4. STORAGE: Check disk usage (df -h), RAM usage (free -h), and log file sizes under ~/.hermes/logs/. Flag if disk >80% or any log >100MB.

5. DRIVE HEALTH: Read SMART data for storage drives, flag concerning indicators (reallocated sectors, pending sectors, temperature anomalies).

Report a single summary via Telegram with ✅/⚠️/❌ status per section. Only detail items that need attention."

create_cron "[OPS] Weekly Ops Report" \
    "0 18 * * 0" \
    "$DEEPSEEK" \
    "Generate the weekly ops report. Summarize: (1) System uptime and availability this week. (2) Cron execution success rate — how many fired vs missed vs failed. (3) Token usage and cost estimate across all crons. (4) API health trends — any recurring failures. (5) Storage and memory trends. (6) Compute a weekly Ops Score (0-100) based on: uptime, cron reliability, API health, storage headroom. Report via Telegram."

echo ""

# ── Default crons ──
echo "  ── [DEFAULT] Default ──"

create_cron "[DEFAULT] LS1 Monthly Life Score" \
    "0 21 3 * *" \
    "$DEEPSEEK" \
    "Calculate the monthly Life Score. Read the latest Financial Health Score, Composite Health Score, and Growth Score from their respective JSON outputs in ~/.hermes/cron_outputs/. Compute the weighted composite Life Score (0-100): Financial 35%, Health 35%, Growth 30%. Compare against previous months. Identify the single highest-impact area to focus on next month. Report via Telegram."

create_cron "[DEFAULT] CAL2 Calendar Intelligence" \
    "0 8 * * *" \
    "$GEMINI" \
    "Run the daily calendar intelligence check. NOTE: n8n on the Mac Mini already sends raw calendar events, weather, and thermostat data to Telegram at 7 AM. Your job is the SMART layer on top: detect scheduling conflicts between work and personal calendars, flag double-bookings, identify prep time needed for upcoming meetings, and alert on calendar changes since yesterday. Do NOT duplicate the raw event list. Report only actionable insights via Telegram."

echo ""

# ─── Phase 3: System crontab ─────────────────────
echo "▶ Phase 3: Installing system crontab jobs..."

# Stale-exec sweeper (zero tokens, runs as pure Python)
SWEEPER_PATH="$HERMES_HOME/scripts/stale-exec-sweeper.py"
HEARTBEAT_PATH="$HOME/abbie-config/scripts/heartbeat.sh"
SWEEPER_LOG="$HERMES_HOME/logs/sweeper.log"
HEARTBEAT_LOG="$HERMES_HOME/logs/heartbeat.log"

mkdir -p "$HERMES_HOME/logs"

# Build new crontab entries
CRONTAB_ADDITIONS=$(cat <<'CRONTAB_EOF'
# === Allie System Jobs (added by cron-consolidate.sh) ===
# Stale-exec sweeper — clears stuck Hermes cron executions every 6h (zero tokens)
0 */6 * * * /usr/bin/python3 SWEEPER_PLACEHOLDER >> SWEEPER_LOG_PLACEHOLDER 2>&1
# Lightweight heartbeat — bash script, no LLM, every 4h
0 */4 * * * bash HEARTBEAT_PLACEHOLDER >> HEARTBEAT_LOG_PLACEHOLDER 2>&1
# === End Allie System Jobs ===
CRONTAB_EOF
)

# Substitute actual paths
CRONTAB_ADDITIONS=$(echo "$CRONTAB_ADDITIONS" | \
    sed "s|SWEEPER_PLACEHOLDER|${SWEEPER_PATH}|g" | \
    sed "s|SWEEPER_LOG_PLACEHOLDER|${SWEEPER_LOG}|g" | \
    sed "s|HEARTBEAT_PLACEHOLDER|${HEARTBEAT_PATH}|g" | \
    sed "s|HEARTBEAT_LOG_PLACEHOLDER|${HEARTBEAT_LOG}|g")

# Check if already installed
if crontab -l 2>/dev/null | grep -q "Allie System Jobs"; then
    echo "  ⚠️  System crontab entries already exist — skipping"
else
    # Append to existing crontab
    (crontab -l 2>/dev/null || true; echo "$CRONTAB_ADDITIONS") | crontab -
    echo "  ✅ System crontab installed (sweeper every 6h, heartbeat every 4h)"
fi

echo ""

# ─── Phase 4: Install unified SOUL ──────────────
echo "▶ Phase 4: Installing unified SOUL.md..."

UNIFIED_SOUL="$REPO_DIR/bot-souls/unified-soul.md"
if [ -f "$UNIFIED_SOUL" ]; then
    # Back up current
    if [ -f "$HERMES_HOME/SOUL.md" ]; then
        cp "$HERMES_HOME/SOUL.md" "$BACKUP_DIR/SOUL.md.pre-consolidation.bak"
        echo "  📋 Current SOUL.md backed up"
    fi
    cp "$UNIFIED_SOUL" "$HERMES_HOME/SOUL.md"
    echo "  ✅ Unified SOUL.md installed"
else
    echo "  ⚠️  Unified SOUL not found at $UNIFIED_SOUL — skipping"
fi

echo ""

# ─── Phase 5: Disable bot mode ──────────────────
echo "▶ Phase 5: Disabling bot_mode_protocol..."

CONFIG_FILE="$HERMES_HOME/config.yaml"
if grep -q "bot_mode_protocol" "$CONFIG_FILE" 2>/dev/null; then
    sed -i 's/bot_mode_protocol:.*/bot_mode_protocol: false/' "$CONFIG_FILE"
    echo "  ✅ bot_mode_protocol set to false"
else
    echo "  ℹ️  bot_mode_protocol not found in config — nothing to change"
fi

# Ensure fallback is deepseek only (no Claude)
if grep -q "claude" "$CONFIG_FILE" 2>/dev/null; then
    echo "  ⚠️  Claude found in config — check fallback_providers manually"
else
    echo "  ✅ No Claude references in config"
fi

echo ""

# ─── Phase 6: Delete specialist profiles ─────────
echo "▶ Phase 6: Deleting specialist bot profiles..."

for prof in finance-bot health-bot home-bot storefront-bot market-bot invent-bot job-bot ops-bot; do
    if hermes profile list 2>/dev/null | grep -q "$prof"; then
        hermes profile delete "$prof" --yes 2>/dev/null && \
            echo "  ✅ Deleted $prof" || \
            echo "  ⚠️  Could not delete $prof via CLI"
    else
        echo "  ℹ️  $prof not found — already gone"
    fi
done

echo ""

# ─── Phase 7: Restore skills to default ──────────
echo "▶ Phase 7: Verifying skill access on default profile..."

# After deleting bot profiles, default should see all skills in ~/.hermes/skills/
SKILL_COUNT=$(find "$HERMES_HOME/skills" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l)
echo "  Skills directories with SKILL.md: $SKILL_COUNT"

# If the default profile had skill restrictions, remove them
if [ -f "$HERMES_HOME/config.yaml" ]; then
    if grep -q "allowed_skills:" "$CONFIG_FILE" 2>/dev/null; then
        echo "  ⚠️  'allowed_skills' restriction found in config — commenting out"
        sed -i 's/^  allowed_skills:/  # allowed_skills: (removed by consolidation)/' "$CONFIG_FILE"
    fi
fi

echo "  ✅ Default profile has access to all installed skills"
echo ""

# ─── Summary ─────────────────────────────────────
echo "══════════════════════════════════════════════"
echo "  ✅ Consolidation Complete!"
echo "══════════════════════════════════════════════"
echo ""
echo "State:"
echo "  Profiles:"
hermes profile list 2>/dev/null || echo "  (run 'hermes profile list' to verify)"
echo ""
echo "  Crons:"
hermes cron list 2>/dev/null || echo "  (run 'hermes cron list' to verify)"
echo ""
echo "  System crontab:"
crontab -l 2>/dev/null | grep -A1 "Allie" || echo "  (check 'crontab -l')"
echo ""
echo "Backup: $BACKUP_DIR"
echo ""
echo "Verification:"
echo "  1. hermes profile list            → should show only 'default'"
echo "  2. hermes cron list               → should show 17 crons"
echo "  3. hermes cron list | grep -c ']' → should return 17"
echo "  4. crontab -l | grep sweeper      → should show sweeper entry"
echo "  5. Wait for next cron to fire, verify Telegram delivery"
echo ""
echo "Rollback:"
echo "  cp $BACKUP_DIR/config.yaml.bak $HERMES_HOME/config.yaml"
echo "  cp $BACKUP_DIR/SOUL.md.bak $HERMES_HOME/SOUL.md"
echo "  cp -r $BACKUP_DIR/profiles-backup/* $HERMES_HOME/profiles/"
echo "  # Then re-run bot-mode-activate.sh + bot-mode-cron-migrate.sh"
