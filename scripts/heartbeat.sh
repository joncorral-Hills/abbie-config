#!/bin/bash
# heartbeat.sh — SH1 Heartbeat Monitor (no LLM needed)
# Pings all critical services, detects state transitions, alerts via Telegram.
# Replaces the gemini-local LLM-based heartbeat with a pure bash script.
#
# Usage: Called by Hermes cron SH1 every 4h, or manually: bash heartbeat.sh
# Output: ~/.hermes/cron_outputs/heartbeat_state.json

set -euo pipefail

STATE_FILE="$HOME/.hermes/cron_outputs/heartbeat_state.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Ensure output directory exists
mkdir -p "$(dirname "$STATE_FILE")"

# Load previous state (or empty object if first run)
if [[ -f "$STATE_FILE" ]]; then
    PREV_STATE=$(cat "$STATE_FILE")
else
    PREV_STATE='{}'
fi

get_prev() {
    echo "$PREV_STATE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('$1',{}).get('status','unknown'))" 2>/dev/null || echo "unknown"
}

# ── Service Checks ──────────────────────────────────────────────────
declare -A RESULTS
INCIDENTS=""
INCIDENT_COUNT=0

check_service() {
    local name="$1"
    local url="$2"
    local timeout="${3:-5}"
    local critical="${4:-true}"
    local extra_headers="${5:-}"

    local http_code
    if [[ -n "$extra_headers" ]]; then
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$timeout" -H "$extra_headers" "$url" 2>/dev/null || echo "000")
    else
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$timeout" "$url" 2>/dev/null || echo "000")
    fi

    local status="healthy"
    if [[ "$http_code" == "000" || "$http_code" -ge 500 ]]; then
        status="down"
    fi

    RESULTS[$name]="$status"
    local prev_status
    prev_status=$(get_prev "$name")

    # Detect transitions
    if [[ "$prev_status" != "down" && "$status" == "down" ]]; then
        INCIDENT_COUNT=$((INCIDENT_COUNT + 1))
        if [[ "$critical" == "true" ]]; then
            INCIDENTS+="🚨 *$name*: healthy → down (HTTP $http_code)\n"
        else
            INCIDENTS+="⚠️ *$name*: healthy → down (HTTP $http_code)\n"
        fi
    elif [[ "$prev_status" == "down" && "$status" == "healthy" ]]; then
        INCIDENT_COUNT=$((INCIDENT_COUNT + 1))
        INCIDENTS+="✅ *$name*: recovered (down → healthy)\n"
    fi
}

# Check all services
check_service "bridge"       "http://localhost:8787/health"           10  true
check_service "gemini-local" "http://localhost:8081/health"            5  true
check_service "llama-local"  "http://localhost:8082/health"            5  true
check_service "notion"       "https://api.notion.com/v1/users/me"    10  true  "Authorization: Bearer ${NOTION_API_KEY:-missing}"
check_service "telegram"     "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN:-missing}/getMe" 10 true
check_service "n8n"          "http://192.168.1.143:5678/healthz"      5  false

# ── Build New State JSON ────────────────────────────────────────────
NEW_STATE='{'
FIRST=true
for name in "${!RESULTS[@]}"; do
    if [[ "$FIRST" == "true" ]]; then
        FIRST=false
    else
        NEW_STATE+=','
    fi
    NEW_STATE+="\"$name\":{\"status\":\"${RESULTS[$name]}\",\"checked_at\":\"$TIMESTAMP\"}"
done
NEW_STATE+='}'

# Pretty-print and save
echo "$NEW_STATE" | python3 -m json.tool > "$STATE_FILE"

# ── Count healthy/down ──────────────────────────────────────────────
TOTAL=${#RESULTS[@]}
HEALTHY=0
for name in "${!RESULTS[@]}"; do
    [[ "${RESULTS[$name]}" == "healthy" ]] && HEALTHY=$((HEALTHY + 1))
done
DOWN=$((TOTAL - HEALTHY))

# ── Alert on State Transitions ─────────────────────────────────────
if [[ $INCIDENT_COUNT -gt 0 && -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
    MESSAGE="🏥 *Heartbeat Report* ($TIMESTAMP)\n\n"
    MESSAGE+="$INCIDENTS\n"
    MESSAGE+="Services: $HEALTHY/$TOTAL healthy"

    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d chat_id="${TELEGRAM_CHAT_ID}" \
        -d parse_mode="Markdown" \
        -d text="$(echo -e "$MESSAGE")" > /dev/null 2>&1
fi

# ── Summary to stdout (for cron log capture) ────────────────────────
echo "[$TIMESTAMP] Heartbeat: $HEALTHY/$TOTAL healthy, $INCIDENT_COUNT state transitions"
for name in "${!RESULTS[@]}"; do
    echo "  $name: ${RESULTS[$name]}"
done
