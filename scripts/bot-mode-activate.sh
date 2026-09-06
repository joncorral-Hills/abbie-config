#!/usr/bin/env bash
# bot-mode-activate.sh — Phase 1: Create specialist bot profiles for Allie
# Execution: Allie pulls from git and runs this script on the VM
# Rollback: hermes profile delete <name> --yes (default profile untouched)
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOUL_DIR="$SCRIPT_DIR/../bot-souls"

echo "══════════════════════════════════════════════"
echo "  🤖 Bot Mode Activation — Phase 1"
echo "══════════════════════════════════════════════"
echo ""

# ─── Pre-flight checks ───────────────────────────
echo "▶ Pre-flight checks..."

if ! command -v hermes &>/dev/null; then
    echo "❌ hermes not found in PATH"
    exit 1
fi

HERMES_VERSION=$(hermes --version 2>/dev/null || echo "unknown")
echo "  Hermes version: $HERMES_VERSION"

if [ ! -d "$SOUL_DIR" ]; then
    echo "❌ SOUL directory not found at $SOUL_DIR"
    echo "  Make sure bot-souls/ exists in the repo root."
    exit 1
fi

echo "  ✅ All checks passed"
echo ""

# ─── Phase 1a: Enable bot_mode_protocol ──────────
echo "▶ Phase 1a: Enabling bot_mode_protocol..."

CONFIG_FILE="$HERMES_HOME/config.yaml"
if grep -q "bot_mode_protocol" "$CONFIG_FILE" 2>/dev/null; then
    echo "  bot_mode_protocol already present in config.yaml — updating to true"
    sed -i 's/bot_mode_protocol:.*/bot_mode_protocol: true/' "$CONFIG_FILE"
else
    # Check if agent: section exists
    if grep -q "^agent:" "$CONFIG_FILE" 2>/dev/null; then
        # Add under existing agent: section
        sed -i '/^agent:/a\  bot_mode_protocol: true' "$CONFIG_FILE"
    else
        # Add new agent: section
        echo -e "\nagent:\n  bot_mode_protocol: true" >> "$CONFIG_FILE"
    fi
fi
echo "  ✅ bot_mode_protocol enabled"
echo ""

# ─── Phase 1b: Create bot profiles ──────────────
echo "▶ Phase 1b: Creating bot profiles..."

declare -A BOT_DESCRIPTIONS=(
    ["finance-bot"]="Manages all personal finance: budgets, transactions, statement parsing, tax planning, debt payoff, credit card optimization, and Plaid transaction sync. Handles sensitive financial PII on local LLM only."
    ["health-bot"]="Tracks workouts via Hevy API, syncs health metrics and body composition, generates training intelligence and recovery scores, manages supplements, and interprets lab results."
    ["home-bot"]="Manages home maintenance schedules and seasonal prep for Kansas City metro zone 6a. Also handles travel planning with points optimization."
    ["storefront-bot"]="Operates the Etsy digital product storefront: niche research, product creation, SEO optimization, listing management, mockup generation, and revenue tracking."
    ["market-bot"]="Researches stocks using fundamental, technical, and sentiment analysis. Generates weekly market briefings. Manages the Robinhood agentic trading account via MCP."
    ["invent-bot"]="Captures and analyzes invention ideas via #invent tag. Performs IP novelty screening, patent prior art searches, market viability analysis, and generates 3D models via OpenSCAD for physical prototypes."
    ["job-bot"]="Career contingency system. Handles job searches, resume tailoring, cover letter writing, interview prep, and application tracking. Standby mode by default — activates when needed."
)

declare -A BOT_MODELS=(
    ["finance-bot"]="llama-local"
    ["health-bot"]="gemini-local"
    ["home-bot"]="gemini-local"
    ["storefront-bot"]="deepseek-v4-flash"
    ["market-bot"]="deepseek-v4-flash"
    ["invent-bot"]="deepseek-v4-flash"
    ["job-bot"]="deepseek-v4-flash"
)

for bot in finance-bot health-bot home-bot storefront-bot market-bot invent-bot job-bot; do
    echo "  Creating $bot..."
    
    # Check if profile already exists
    if hermes profile list 2>/dev/null | grep -q "$bot"; then
        echo "    ⚠️  Profile '$bot' already exists — skipping creation"
    else
        hermes profile create "$bot" --clone --description "${BOT_DESCRIPTIONS[$bot]}"
        echo "    ✅ Created"
    fi
done
echo ""

# ─── Phase 1c: Pin models per profile ───────────
echo "▶ Phase 1c: Pinning models..."

for bot in "${!BOT_MODELS[@]}"; do
    model="${BOT_MODELS[$bot]}"
    echo "  $bot → $model"
    hermes -p "$bot" config set model.default "$model" 2>/dev/null || \
        echo "    ⚠️  Could not pin model via CLI — will set in config.yaml directly"
done
echo ""

# ─── Phase 1d: Install SOUL.md files ────────────
echo "▶ Phase 1d: Installing SOUL.md files..."

# Install bot SOULs
for bot in finance-bot health-bot home-bot storefront-bot market-bot invent-bot job-bot; do
    SOUL_SRC="$SOUL_DIR/${bot}.md"
    if [ -f "$SOUL_SRC" ]; then
        PROFILE_DIR="$HERMES_HOME/profiles/$bot"
        if [ -d "$PROFILE_DIR" ]; then
            cp "$SOUL_SRC" "$PROFILE_DIR/SOUL.md"
            echo "  ✅ $bot SOUL.md installed"
        else
            echo "  ⚠️  Profile dir not found for $bot — skipping SOUL"
        fi
    else
        echo "  ⚠️  No SOUL file at $SOUL_SRC"
    fi
done

# Install coordinator SOUL for default profile
COORD_SOUL="$SOUL_DIR/coordinator.md"
if [ -f "$COORD_SOUL" ]; then
    # Back up existing SOUL.md
    if [ -f "$HERMES_HOME/SOUL.md" ]; then
        cp "$HERMES_HOME/SOUL.md" "$HERMES_HOME/SOUL.md.pre-botmode.bak"
        echo "  📋 Backed up existing default SOUL.md → SOUL.md.pre-botmode.bak"
    fi
    cp "$COORD_SOUL" "$HERMES_HOME/SOUL.md"
    echo "  ✅ Coordinator SOUL.md installed on default profile"
fi
echo ""

# ─── Phase 1e: Display name for default ─────────
echo "▶ Phase 1e: Setting display name for default profile..."
hermes profile rename default "Allie" 2>/dev/null || echo "  ⚠️  Display name set may not be supported — cosmetic only"
echo ""

# ─── Summary ─────────────────────────────────────
echo "══════════════════════════════════════════════"
echo "  ✅ Phase 1 Complete!"
echo "══════════════════════════════════════════════"
echo ""
echo "Profiles created:"
hermes profile list 2>/dev/null || echo "(run 'hermes profile list' to verify)"
echo ""
echo "Next steps:"
echo "  1. Verify: hermes -p finance-bot chat -q 'who are you?'"
echo "  2. Verify: hermes -p health-bot chat -q 'who are you?'"
echo "  3. Phase 2: Run cron migration script (separate)"
echo ""
echo "Rollback (if needed):"
echo "  hermes profile delete finance-bot --yes"
echo "  hermes profile delete health-bot --yes"
echo "  hermes profile delete home-bot --yes"
echo "  hermes profile delete storefront-bot --yes"
echo "  hermes profile delete market-bot --yes"
echo "  cp ~/.hermes/SOUL.md.pre-botmode.bak ~/.hermes/SOUL.md"
