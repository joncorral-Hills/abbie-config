#!/usr/bin/env bash
# specialist-setup.sh — Create v2 bot fleet: 8 specialist profiles + upgraded orchestrator
#
# Prerequisites:
#   - cron-consolidate.sh has already run (16 crons on default, old profiles deleted)
#   - bot-souls/*.md files are current in the repo
#
# What this does:
#   1. Re-enables bot_mode_protocol for peer communication
#   2. Creates 8 specialist profiles (zero crons each)
#   3. Installs specialist SOULs
#   4. Pins models per specialist
#   5. Configures skill access per specialist
#   6. Upgrades orchestrator SOUL
#   7. Prunes orchestrator skills to non-specialist set
#
# Rollback: hermes profile delete <name> --yes for each specialist
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$SCRIPT_DIR/.."
CONFIG_FILE="$HERMES_HOME/config.yaml"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Model aliases — Hermes uses model.default + model.provider, not combined strings
# For deepseek: model.default=deepseek/deepseek-v4-flash, model.provider=openrouter
# For gemini-local: model.default=gemini-local (local proxy, no provider)
DEEPSEEK_MODEL="deepseek/deepseek-v4-flash"
DEEPSEEK_PROVIDER="openrouter"
GEMINI="gemini-local"

echo "══════════════════════════════════════════════"
echo "  🤖 Allie v2 — Specialist Bot Fleet Setup"
echo "  $(date)"
echo "══════════════════════════════════════════════"
echo ""

# ─── Pre-flight ───────────────────────────────────
echo "▶ Pre-flight checks..."

if ! command -v hermes &>/dev/null; then
    echo "❌ hermes not found in PATH"
    exit 1
fi

# Verify crons are on default
CRON_COUNT=$(hermes cron list 2>/dev/null | grep -c '\[' || echo "0")
echo "  Crons on default: $CRON_COUNT"
if [ "$CRON_COUNT" -lt 10 ]; then
    echo "  ⚠️  Expected 16 crons on default. Run cron-consolidate.sh first if needed."
fi

echo "  ✅ Pre-flight passed"
echo ""

# ─── Phase 1: Enable bot_mode_protocol ────────────
echo "▶ Phase 1: Enabling bot_mode_protocol..."

if grep -q "bot_mode_protocol:" "$CONFIG_FILE" 2>/dev/null; then
    sed -i 's/bot_mode_protocol:.*/bot_mode_protocol: true/' "$CONFIG_FILE"
    echo "  ✅ bot_mode_protocol set to true"
else
    # Add it under agent section
    echo "  ℹ️  bot_mode_protocol not found — adding to config"
    echo "" >> "$CONFIG_FILE"
    echo "  bot_mode_protocol: true" >> "$CONFIG_FILE"
    echo "  ✅ bot_mode_protocol added and set to true"
fi

echo ""

# ─── Phase 2: Create specialist profiles ──────────
echo "▶ Phase 2: Creating specialist profiles..."

# Define specialists: name|model|provider|skills (pipe-delimited)
# provider is empty for gemini-local (local proxy)
declare -a SPECIALISTS=(
    "finance-bot|${DEEPSEEK_MODEL}|${DEEPSEEK_PROVIDER}|financial-automation,financial-planner,plaid-budget-sentinel,tax-planner"
    "health-bot|${DEEPSEEK_MODEL}|${DEEPSEEK_PROVIDER}|health-automation,health-planner"
    "market-bot|${GEMINI}||stock-fundamentals,stock-technicals,stock-sentiment,stock-market-macro,stock-weekly-briefing"
    "home-bot|${GEMINI}||home-maintenance,home-hub"
    "plant-bot|${GEMINI}||plant-garden"
    "work-bot|${GEMINI}||work-context-handoff,work-ops"
    "osint-bot|${GEMINI}||osint-recon"
    "invent-bot|${GEMINI}||invention-processor"
    "job-bot|${DEEPSEEK_MODEL}|${DEEPSEEK_PROVIDER}|job-search-ops"
    "travel-bot|${GEMINI}||travel-planner"
)

for spec in "${SPECIALISTS[@]}"; do
    IFS='|' read -r name model provider skills <<< "$spec"

    echo "  📋 $name (model: $model, provider: ${provider:-local})"

    # Create profile if it doesn't exist
    if hermes profile list 2>/dev/null | grep -q "$name"; then
        echo "     ℹ️  Already exists — skipping creation"
    else
        hermes profile create "$name" 2>/dev/null && \
            echo "     ✅ Profile created" || \
            echo "     ❌ Failed to create profile"
    fi

    # Create profile directory if it doesn't exist
    PROFILE_DIR="$HERMES_HOME/profiles/$name"
    mkdir -p "$PROFILE_DIR"

    # Install SOUL
    SOUL_SRC="$REPO_DIR/bot-souls/${name}.md"
    if [ -f "$SOUL_SRC" ]; then
        cp "$SOUL_SRC" "$PROFILE_DIR/SOUL.md"
        echo "     ✅ SOUL installed"
    else
        echo "     ⚠️  SOUL not found at $SOUL_SRC"
    fi

    # Pin model (use model.default + model.provider for Hermes format)
    hermes -p "$name" config set model.default "$model" 2>/dev/null && \
        echo "     ✅ Model set: $model" || \
        echo "     ⚠️  Could not set model via CLI"

    if [ -n "$provider" ]; then
        hermes -p "$name" config set model.provider "$provider" 2>/dev/null && \
            echo "     ✅ Provider set: $provider" || \
            echo "     ⚠️  Could not set provider via CLI"
    fi

    # Configure allowed skills (if any specified)
    if [ -n "$skills" ]; then
        # Write skills config to profile config.yaml
        PROFILE_CONFIG="$PROFILE_DIR/config.yaml"
        if [ ! -f "$PROFILE_CONFIG" ]; then
            echo "# Profile config for $name" > "$PROFILE_CONFIG"
        fi

        # Check if allowed_skills already exists
        if grep -q "allowed_skills:" "$PROFILE_CONFIG" 2>/dev/null; then
            echo "     ℹ️  allowed_skills already configured"
        else
            echo "" >> "$PROFILE_CONFIG"
            echo "allowed_skills:" >> "$PROFILE_CONFIG"
            IFS=',' read -ra SKILL_ARRAY <<< "$skills"
            for skill in "${SKILL_ARRAY[@]}"; do
                echo "  - $skill" >> "$PROFILE_CONFIG"
            done
            echo "     ✅ Skills configured: $skills"
        fi
    else
        echo "     ℹ️  No existing skills — new skill needs to be built"
    fi

    # Verify zero crons
    BOT_CRONS=$(hermes -p "$name" cron list 2>/dev/null | grep -c '\[' || echo "0")
    if [ "$BOT_CRONS" -gt 0 ]; then
        echo "     ⚠️  WARNING: $name has $BOT_CRONS crons — these should be removed!"
    else
        echo "     ✅ Zero crons (correct)"
    fi

    echo ""
done

# ─── Phase 3: Upgrade orchestrator SOUL ───────────
echo "▶ Phase 3: Upgrading orchestrator SOUL..."

ORCH_SOUL="$REPO_DIR/bot-souls/orchestrator-soul.md"
if [ -f "$ORCH_SOUL" ]; then
    # Back up current
    cp "$HERMES_HOME/SOUL.md" "$HERMES_HOME/SOUL.md.pre-v2.bak" 2>/dev/null || true
    cp "$ORCH_SOUL" "$HERMES_HOME/SOUL.md"
    echo "  ✅ Orchestrator SOUL upgraded (backup: SOUL.md.pre-v2.bak)"
else
    echo "  ⚠️  Orchestrator SOUL not found at $ORCH_SOUL"
fi

echo ""

# ─── Phase 4: Prune orchestrator skills ───────────
echo "▶ Phase 4: Configuring orchestrator skill access..."

# The orchestrator should only have non-specialist skills
# Specialist skills are accessible via delegation to specialists
ORCH_SKILLS="project-board,life-score,calendar-automation,work-context-handoff,allie-skill-builder,system-health"

if grep -q "allowed_skills:" "$CONFIG_FILE" 2>/dev/null; then
    echo "  ℹ️  allowed_skills already set in global config — updating"
    # Remove existing allowed_skills block and rewrite
    sed -i '/^allowed_skills:/,/^[^ ]/{ /^allowed_skills:/d; /^  - /d; }' "$CONFIG_FILE"
fi

echo "" >> "$CONFIG_FILE"
echo "allowed_skills:" >> "$CONFIG_FILE"
IFS=',' read -ra ORCH_ARRAY <<< "$ORCH_SKILLS"
for skill in "${ORCH_ARRAY[@]}"; do
    echo "  - $skill" >> "$CONFIG_FILE"
done
echo "  ✅ Orchestrator pruned to: $ORCH_SKILLS"

echo ""

# ─── Summary ─────────────────────────────────────
echo "══════════════════════════════════════════════"
echo "  ✅ v2 Bot Fleet Setup Complete!"
echo "══════════════════════════════════════════════"
echo ""
echo "Profiles:"
hermes profile list 2>/dev/null || echo "  (run 'hermes profile list' to verify)"
echo ""
echo "Cron check (should all be on default):"
hermes cron list 2>/dev/null | head -5
echo "  ..."
echo ""
echo "Verification commands:"
echo "  hermes profile list                      → 9 profiles (default + 8 specialists)"
echo "  hermes cron list | grep -c ']'           → 16 crons on default"
echo "  hermes -p finance-bot cron list          → 0 crons"
echo "  grep bot_mode_protocol ~/.hermes/config.yaml → true"
echo ""
echo "Test delegation:"
echo "  hermes chat -q 'What is my budget this month?'"
echo "  → Should delegate to finance-bot via message_agent()"
echo ""
echo "Next steps:"
echo "  1. Test interactive DMs for each domain via Telegram"
echo "  2. Wait for next cron cycle to verify orchestrator fires correctly"
echo "  3. Build new skills: plant-garden, home-hub, work-ops, osint-recon"
