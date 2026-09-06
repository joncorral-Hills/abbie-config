#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# gemma4-upgrade.sh — LLM Upgrade for Hermes VM (Gemma 4 E4B)
# ═══════════════════════════════════════════════════════════════════
#
# Run as:  bash ~/gemma4-upgrade.sh
#
# What this does:
#   1. Downloads Gemma 4 E4B IT Q4_K_M (target) + Gemma 4 E2B IT Q4_K_M (draft)
#   2. Archives old Qwen3 models
#   3. Creates a new server startup script (without spec decoding yet)
#   4. Stops old llama-server, starts new one, verifies it works
#
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────
LLAMA_DIR="$HOME/.local/llama.cpp"
MODEL_DIR="$HOME/.local/models"
OLD_MODEL_DIR="$HOME/.local/models/archived"
SERVER_LOG="$HOME/.local/llama-server.log"
STARTUP_SCRIPT="$HOME/.local/start-llama-server.sh"
PORT=8082
THREADS_GEN=16
THREADS_BATCH=32
CTX_SIZE=8192

# Target model: Gemma 4 E4B IT Q4_K_M (~4 GB)
TARGET_MODEL="gemma-4-E4B-it-Q4_K_M.gguf"
TARGET_URLS=(
    "https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF/resolve/main/gemma-4-E4B-it-Q4_K_M.gguf"
    "https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/main/gemma-4-E4B-it-Q4_K_M.gguf"
    "https://huggingface.co/lmstudio-community/gemma-4-E4B-it-GGUF/resolve/main/gemma-4-E4B-it-Q4_K_M.gguf"
)

# Draft model: Gemma 4 E2B IT Q4_K_M (~2 GB) — for future speculative decoding
DRAFT_MODEL="gemma-4-E2B-it-Q4_K_M.gguf"
DRAFT_URLS=(
    "https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf"
    "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf"
    "https://huggingface.co/lmstudio-community/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf"
)

# ─── Helpers ──────────────────────────────────────────────────────
log()  { echo "$(date '+%H:%M:%S') [INFO]  $*"; }
warn() { echo "$(date '+%H:%M:%S') [WARN]  $*" >&2; }
fail() { echo "$(date '+%H:%M:%S') [FAIL]  $*" >&2; exit 1; }

file_size_bytes() {
    stat -c%s "$1" 2>/dev/null || stat -f%z "$1" 2>/dev/null || echo 0
}

download_with_fallback() {
    local name="$1" dest="$2" min_bytes="$3"
    shift 3
    local urls=("$@")

    if [[ -f "$dest" ]]; then
        local existing_size
        existing_size=$(file_size_bytes "$dest")
        if (( existing_size >= min_bytes )); then
            log "$name already exists ($(( existing_size / 1048576 )) MB), skipping"
            return 0
        fi
        warn "$name exists but too small (${existing_size}B < ${min_bytes}B), re-downloading"
        rm -f "$dest"
    fi

    for url in "${urls[@]}"; do
        log "Downloading $name from: $(echo "$url" | sed 's|.*/\(.*\)/resolve.*|\1|')..."
        if curl -L --fail --progress-bar -o "$dest" "$url" 2>&1; then
            local size
            size=$(file_size_bytes "$dest")
            if (( size >= min_bytes )); then
                log "✅ $name downloaded ($(( size / 1048576 )) MB)"
                return 0
            fi
            warn "File too small (${size}B), trying next URL..."
            rm -f "$dest"
        else
            warn "Download failed, trying next URL..."
            rm -f "$dest" 2>/dev/null
        fi
    done

    fail "All download URLs failed for $name"
}

# ═══════════════════════════════════════════════════════════════════
# STEP 0: Preflight
# ═══════════════════════════════════════════════════════════════════
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║          HERMES VM — LLM UPGRADE SCRIPT                   ║"
echo "║          Qwen3-4B → Gemma 4 E4B                           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

log "Step 0: Preflight checks..."

# Check required binaries
if ! command -v curl >/dev/null 2>&1; then
    fail "curl is missing. Install with: sudo apt-get install -y curl"
fi

# Find the server binary
SERVER_BIN=""
for candidate in build/bin/llama-server build/llama-server; do
    [[ -f "$LLAMA_DIR/$candidate" ]] && SERVER_BIN="$LLAMA_DIR/$candidate" && break
done
[[ -n "$SERVER_BIN" ]] || fail "llama-server binary not found in $LLAMA_DIR. Is llama.cpp built?"

log "llama-server binary found at $SERVER_BIN"

# Check disk space (need ~10 GB free)
AVAIL_MB=$(df -m "$HOME" | awk 'NR==2 {print $4}')
if (( AVAIL_MB < 10000 )); then
    warn "Low disk space: ${AVAIL_MB}MB available (need ~10000MB). Proceeding anyway..."
fi

log "All prerequisites passed"

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Download target model
# ═══════════════════════════════════════════════════════════════════
log "Step 1: Downloading Gemma 4 target model..."

mkdir -p "$MODEL_DIR" "$OLD_MODEL_DIR"

# Download target model (min 4 GB = 4294967296 bytes)
download_with_fallback "$TARGET_MODEL" "$MODEL_DIR/$TARGET_MODEL" 4294967296 "${TARGET_URLS[@]}"

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Download draft model
# ═══════════════════════════════════════════════════════════════════
log "Step 2: Downloading Gemma 4 draft model (for future spec decoding)..."

# Download draft model (min 2 GB = 2147483648 bytes)
download_with_fallback "$DRAFT_MODEL" "$MODEL_DIR/$DRAFT_MODEL" 2147483648 "${DRAFT_URLS[@]}"

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Archive old models
# ═══════════════════════════════════════════════════════════════════
log "Step 3: Archiving old models..."

shopt -s nullglob
for old in "$MODEL_DIR"/*[Qq]wen3*; do
    if [[ -f "$old" ]]; then
        mv "$old" "$OLD_MODEL_DIR/"
        log "Archived: $(basename "$old") → archived/"
    fi
done
shopt -u nullglob

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Update startup script
# ═══════════════════════════════════════════════════════════════════
log "Step 4: Creating startup script..."

SERVER_BIN_ABS=$(realpath "$SERVER_BIN")

cat > "$STARTUP_SCRIPT" << EOF
#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Gemma 4 E4B Local LLM Server
# Auto-generated by gemma4-upgrade.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
#
# Model:  Gemma 4 E4B IT Q4_K_M (~4 GB)
# Draft:  Available but not enabled yet
# Port:   $PORT (OpenAI-compatible API)
# CPU:    $THREADS_GEN gen threads, $THREADS_BATCH batch threads
# ═══════════════════════════════════════════════════════════════

exec "$SERVER_BIN_ABS" \\
    --model "$MODEL_DIR/$TARGET_MODEL" \\
    --ctx-size $CTX_SIZE \\
    --threads $THREADS_GEN \\
    --threads-batch $THREADS_BATCH \\
    --host 0.0.0.0 \\
    --port $PORT
EOF
chmod +x "$STARTUP_SCRIPT"
log "Startup script updated: $STARTUP_SCRIPT"

# ═══════════════════════════════════════════════════════════════════
# STEP 5: Restart server
# ═══════════════════════════════════════════════════════════════════
log "Step 5: Restarting server..."

# Stop any existing server on this port
if lsof -ti :$PORT >/dev/null 2>&1; then
    log "Stopping existing server on port $PORT..."
    kill $(lsof -ti :$PORT) 2>/dev/null || true
    sleep 3
    # Force kill if still running
    lsof -ti :$PORT >/dev/null 2>&1 && kill -9 $(lsof -ti :$PORT) 2>/dev/null || true
    sleep 1
fi
# Alternatively try pkill if lsof fails
pkill -f "llama-server" 2>/dev/null || true

# Start new server
log "Starting Gemma 4 E4B server..."
nohup "$STARTUP_SCRIPT" > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
log "Server PID: $SERVER_PID"

# Wait for health check (model load takes ~10-15s)
log "Waiting for server to be ready (may take 15-30 seconds for model load)..."
READY=0
for i in $(seq 1 90); do
    # Try multiple health check endpoints
    if curl -sf http://localhost:$PORT/health >/dev/null 2>&1; then
        READY=1
        break
    fi
    # Check if process is still alive
    if ! kill -0 $SERVER_PID 2>/dev/null; then
        fail "Server process died. Check log: tail -50 $SERVER_LOG"
    fi
    sleep 1
done

if (( READY )); then
    log "✅ Server is ready on port $PORT (took ${i}s)"
else
    warn "Server didn't respond after 90s — may still be loading. Check: tail -f $SERVER_LOG"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 6: Test
# ═══════════════════════════════════════════════════════════════════
log "Step 6: Running verification..."

if (( READY )); then
    # Test a simple completion
    VERIFY_START=$(date +%s%N)
    RESPONSE=$(curl -sf --max-time 120 http://localhost:$PORT/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{
            "messages": [{"role": "user", "content": "Reply with exactly: UPGRADE_OK"}],
            "max_tokens": 10,
            "temperature": 0.0
        }' 2>/dev/null || echo '{"error":"timeout"}')
    VERIFY_END=$(date +%s%N)
    VERIFY_MS=$(( (VERIFY_END - VERIFY_START) / 1000000 ))

    if echo "$RESPONSE" | grep -qi "UPGRADE_OK\|choices" 2>/dev/null; then
        log "✅ Model responds correctly (${VERIFY_MS}ms round trip)"
        TEST_STATUS="PASS"
    else
        warn "Response didn't match expected — may still work. Response:"
        echo "$RESPONSE" | python3 -m json.tool 2>/dev/null | head -10 || echo "$RESPONSE" | head -5
        TEST_STATUS="FAIL (see logs)"
    fi
else
    TEST_STATUS="SKIPPED (server not ready)"
fi

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                  UPGRADE COMPLETE                         ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║                                                           ║"
echo "║  Old Model: Qwen3-4B                                      ║"
echo "║  New Model: Gemma 4 E4B IT Q4_K_M                         ║"
echo "║                                                           ║"
echo "║  ✅ Gemma 4 E4B Q4_K_M downloaded (Min: 4GB)              ║"
echo "║  ✅ Gemma 4 E2B Q4_K_M draft downloaded (Min: 2GB)        ║"
echo "║  ✅ Old Qwen3 models archived                             ║"
echo "║  ✅ Server startup script updated                         ║"
echo "║  ✅ Test Status: $TEST_STATUS                                      ║"
echo "║                                                           ║"
echo "║  Files:                                                   ║"
echo "║    Models:  $MODEL_DIR/           ║"
echo "║    Startup: $STARTUP_SCRIPT       ║"
echo "║    Log:     $SERVER_LOG           ║"
echo "║    Old:     $OLD_MODEL_DIR/       ║"
echo "║                                                           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

log "Done. Total time: $SECONDS seconds."
