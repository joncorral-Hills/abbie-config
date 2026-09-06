#!/bin/bash
# llama-on-demand.sh — Start llama-server on demand, auto-stop after idle timeout
#
# This script manages the Gemma 4 E4B llama-server lifecycle:
#   - Starts the server only when needed (before a cron that requires it)
#   - Waits for the server to become healthy
#   - Touches a "last used" timestamp file
#   - A companion idle monitor stops it after IDLE_TIMEOUT minutes of no use
#
# Usage:
#   bash llama-on-demand.sh start     # Start server, wait for healthy
#   bash llama-on-demand.sh stop      # Stop server immediately
#   bash llama-on-demand.sh touch     # Update last-used timestamp (call after each use)
#   bash llama-on-demand.sh status    # Check if running and healthy
#   bash llama-on-demand.sh idle-check # Stop if idle > timeout (called by cron)
#
# Integration with Hermes crons:
#   Crons that need llama-local should include in their message:
#   "First run: bash ~/abbie-config/scripts/llama-on-demand.sh start"
#   And after completion: "Run: bash ~/abbie-config/scripts/llama-on-demand.sh touch"

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
LLAMA_BIN="$HOME/.local/bin/llama-server"
MODEL_PATH="$HOME/.local/models/gemma-4-E4B-it-Q4_K_M.gguf"
PORT=8082
HOST="127.0.0.1"
CTX_SIZE=8192
THREADS=16
BATCH_THREADS=32
HEALTH_URL="http://localhost:${PORT}/health"
PID_FILE="$HOME/.local/llama-server.pid"
LOG_FILE="$HOME/.local/llama-server.log"
TIMESTAMP_FILE="$HOME/.local/llama-server.last_used"
IDLE_TIMEOUT_MINUTES=30  # Stop server after 30 min of no use
MAX_WAIT_SECONDS=120     # Max time to wait for server startup

# ── Functions ────────────────────────────────────────────────────────

is_running() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    # Also check by port
    if pgrep -f "llama-server.*$PORT" >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

is_healthy() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$HEALTH_URL" 2>/dev/null || echo "000")
    [[ "$code" == "200" ]]
}

do_start() {
    if is_running; then
        if is_healthy; then
            echo "[llama-on-demand] Already running and healthy"
            touch "$TIMESTAMP_FILE"
            return 0
        else
            echo "[llama-on-demand] Process exists but unhealthy, restarting..."
            do_stop
        fi
    fi

    echo "[llama-on-demand] Starting llama-server (Gemma 4 E4B, ${CTX_SIZE} ctx)..."

    nohup "$LLAMA_BIN" \
        --model "$MODEL_PATH" \
        --port "$PORT" \
        --host "$HOST" \
        --ctx-size "$CTX_SIZE" \
        --threads "$THREADS" \
        --threads-batch "$BATCH_THREADS" \
        --mlock \
        > "$LOG_FILE" 2>&1 &

    local pid=$!
    echo "$pid" > "$PID_FILE"
    echo "[llama-on-demand] Started with PID $pid, waiting for health..."

    # Wait for server to become healthy
    local elapsed=0
    while [[ $elapsed -lt $MAX_WAIT_SECONDS ]]; do
        if is_healthy; then
            echo "[llama-on-demand] ✅ Healthy after ${elapsed}s"
            touch "$TIMESTAMP_FILE"
            return 0
        fi
        # Check if process died
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "[llama-on-demand] ❌ Process died during startup. Check $LOG_FILE"
            return 1
        fi
        sleep 5
        elapsed=$((elapsed + 5))
    done

    echo "[llama-on-demand] ❌ Timeout after ${MAX_WAIT_SECONDS}s — server did not become healthy"
    return 1
}

do_stop() {
    if [[ -f "$PID_FILE" ]]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "[llama-on-demand] Stopping PID $pid..."
            kill "$pid"
            # Wait for graceful shutdown
            local wait=0
            while kill -0 "$pid" 2>/dev/null && [[ $wait -lt 10 ]]; do
                sleep 1
                wait=$((wait + 1))
            done
            if kill -0 "$pid" 2>/dev/null; then
                echo "[llama-on-demand] Force killing..."
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$PID_FILE"
    fi

    # Also kill any orphan llama-server processes on our port
    pkill -f "llama-server.*$PORT" 2>/dev/null || true
    echo "[llama-on-demand] ✅ Stopped"
}

do_touch() {
    touch "$TIMESTAMP_FILE"
    echo "[llama-on-demand] Timestamp updated"
}

do_status() {
    if is_running; then
        if is_healthy; then
            local last_used="never"
            if [[ -f "$TIMESTAMP_FILE" ]]; then
                last_used=$(stat -c %Y "$TIMESTAMP_FILE" 2>/dev/null || stat -f %m "$TIMESTAMP_FILE" 2>/dev/null)
                local now
                now=$(date +%s)
                local idle_min=$(( (now - last_used) / 60 ))
                last_used="${idle_min} min ago"
            fi
            echo "[llama-on-demand] ✅ Running and healthy (last used: $last_used)"
        else
            echo "[llama-on-demand] ⚠️ Running but NOT healthy"
        fi
    else
        echo "[llama-on-demand] ⏹️ Not running (${MODEL_PATH##*/} = ~4 GB RAM saved)"
    fi
}

do_idle_check() {
    if ! is_running; then
        return 0
    fi

    if [[ ! -f "$TIMESTAMP_FILE" ]]; then
        echo "[llama-on-demand] No timestamp file — stopping (never used since start)"
        do_stop
        return 0
    fi

    local last_used now idle_min
    last_used=$(stat -c %Y "$TIMESTAMP_FILE" 2>/dev/null || stat -f %m "$TIMESTAMP_FILE" 2>/dev/null)
    now=$(date +%s)
    idle_min=$(( (now - last_used) / 60 ))

    if [[ $idle_min -ge $IDLE_TIMEOUT_MINUTES ]]; then
        echo "[llama-on-demand] Idle for ${idle_min} min (threshold: ${IDLE_TIMEOUT_MINUTES} min) — stopping"
        do_stop
    else
        local remaining=$((IDLE_TIMEOUT_MINUTES - idle_min))
        echo "[llama-on-demand] Active — idle ${idle_min} min, will stop in ${remaining} min"
    fi
}

# ── Main ─────────────────────────────────────────────────────────────
case "${1:-status}" in
    start)      do_start ;;
    stop)       do_stop ;;
    touch)      do_touch ;;
    status)     do_status ;;
    idle-check) do_idle_check ;;
    *)
        echo "Usage: $0 {start|stop|touch|status|idle-check}"
        exit 1
        ;;
esac
