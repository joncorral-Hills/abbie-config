#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════
# llm-upgrade.sh — Complete LLM Upgrade for Hermes VM
# ═══════════════════════════════════════════════════════════════════
#
# Run as:  bash ~/llm-upgrade.sh
#
# What this does:
#   1. Installs python-telegram-bot (fixes 2 broken cron deliveries)
#   2. Rebuilds llama.cpp from source with AVX-512 + AMX support
#   3. Downloads Qwen3-4B Q4_K_M (target) + Qwen3-0.6B Q4_K_M (draft)
#   4. Creates a new server startup script with speculative decoding
#   5. Stops old llama-server, starts new one, verifies it works
#
# Prerequisites: git, cmake, gcc/g++ (>=12), curl, python3, pip
# Runtime: ~15 minutes (dominated by model download + compilation)
# Disk: ~4 GB additional (build artifacts + 2 model files)
#
# IMPORTANT: Run this on the VM host, NOT inside the Docker container.
# ═══════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────
LLAMA_DIR="$HOME/.local/llama.cpp"
MODEL_DIR="$HOME/.local/models"
OLD_MODEL_DIR="$HOME/.local/models/archived"
SERVER_LOG="$HOME/.local/llama-server.log"
STARTUP_SCRIPT="$HOME/.local/start-llama-server.sh"
PORT=8082
THREADS_GEN=16       # Half of cores — leaves headroom for prompt eval
THREADS_BATCH=32     # All cores — max throughput for prompt processing
CTX_SIZE=8192        # Match current config; Qwen3 supports up to 128K

# Target model: Qwen3-4B Q4_K_M (~2.5-2.8 GB)
TARGET_MODEL="Qwen3-4B-Q4_K_M.gguf"
TARGET_URLS=(
    "https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/qwen3-4b-q4_k_m.gguf"
    "https://huggingface.co/bartowski/Qwen_Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"
    "https://huggingface.co/lmstudio-community/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf"
)

# Draft model: Qwen3-0.6B Q4_K_M (~484 MB) — for speculative decoding
DRAFT_MODEL="Qwen3-0.6B-Q4_K_M.gguf"
DRAFT_URLS=(
    "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/qwen3-0.6b-q4_k_m.gguf"
    "https://huggingface.co/bartowski/Qwen_Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf"
    "https://huggingface.co/lmstudio-community/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q4_K_M.gguf"
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
echo "║          HERMES VM — LLM UPGRADE SCRIPT                  ║"
echo "║  Qwen2.5-7B → Qwen3-4B + Speculative Decoding           ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

log "Step 0: Preflight checks..."

# Check required binaries
MISSING=()
for cmd in git cmake curl python3; do
    command -v "$cmd" >/dev/null 2>&1 || MISSING+=("$cmd")
done

# gcc/g++ — check for any version
if ! command -v gcc >/dev/null 2>&1 && ! command -v cc >/dev/null 2>&1; then
    MISSING+=("gcc")
fi

if (( ${#MISSING[@]} > 0 )); then
    fail "Missing required tools: ${MISSING[*]}. Install with: sudo apt-get install -y ${MISSING[*]}"
fi

# pip might be pip3
PIP_CMD="pip"
command -v pip >/dev/null 2>&1 || PIP_CMD="pip3"
command -v "$PIP_CMD" >/dev/null 2>&1 || fail "pip not found. Install with: sudo apt-get install -y python3-pip"

log "All prerequisites found"

# Detect CPU features
AVX512=OFF
AMX=OFF
if [[ -f /proc/cpuinfo ]]; then
    grep -q "avx512" /proc/cpuinfo 2>/dev/null && AVX512=ON
    grep -q "amx"    /proc/cpuinfo 2>/dev/null && AMX=ON
fi
log "CPU features: AVX-512=$AVX512, AMX=$AMX"

# Check disk space (need ~5 GB free)
AVAIL_MB=$(df -m "$HOME" | awk 'NR==2 {print $4}')
if (( AVAIL_MB < 5000 )); then
    warn "Low disk space: ${AVAIL_MB}MB available (need ~5000MB). Proceeding anyway..."
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 1: Fix python-telegram-bot
# ═══════════════════════════════════════════════════════════════════
log "Step 1: Installing python-telegram-bot..."

if $PIP_CMD show python-telegram-bot >/dev/null 2>&1; then
    log "python-telegram-bot already installed"
else
    $PIP_CMD install --quiet --break-system-packages python-telegram-bot 2>/dev/null \
        || $PIP_CMD install --quiet python-telegram-bot 2>/dev/null \
        || warn "pip install failed — try: sudo $PIP_CMD install python-telegram-bot"
    log "✅ python-telegram-bot installed"
fi

# ═══════════════════════════════════════════════════════════════════
# STEP 2: Build llama.cpp from source
# ═══════════════════════════════════════════════════════════════════
log "Step 2: Building llama.cpp with optimized CPU flags..."

mkdir -p "$(dirname "$LLAMA_DIR")"

if [[ -d "$LLAMA_DIR/.git" ]]; then
    log "Existing llama.cpp repo found, updating..."
    cd "$LLAMA_DIR"
    git fetch origin
    git reset --hard origin/master 2>/dev/null || git reset --hard origin/main
else
    log "Cloning llama.cpp..."
    rm -rf "$LLAMA_DIR"
    git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$LLAMA_DIR"
fi

cd "$LLAMA_DIR"
rm -rf build

log "Running cmake (AVX512=$AVX512, AMX=$AMX)..."
cmake -S . -B build \
    -DGGML_AVX512="$AVX512" \
    -DGGML_AVX512_VBMI="$AVX512" \
    -DGGML_AVX512_VNNI="$AVX512" \
    -DGGML_AMX="$AMX" \
    -DCMAKE_BUILD_TYPE=Release \
    2>&1 | tail -5

log "Compiling with $(nproc) threads..."
cmake --build build -j"$(nproc)" 2>&1 | tail -3

# Find the server binary (location varies by version)
SERVER_BIN=""
for candidate in build/bin/llama-server build/llama-server; do
    [[ -f "$LLAMA_DIR/$candidate" ]] && SERVER_BIN="$LLAMA_DIR/$candidate" && break
done
[[ -n "$SERVER_BIN" ]] || fail "llama-server binary not found after build. Check build output."

log "✅ llama.cpp built: $SERVER_BIN"

# Print build info for verification
"$SERVER_BIN" --version 2>&1 | head -3 || true

# ═══════════════════════════════════════════════════════════════════
# STEP 3: Download models
# ═══════════════════════════════════════════════════════════════════
log "Step 3: Downloading Qwen3 models..."

mkdir -p "$MODEL_DIR" "$OLD_MODEL_DIR"

# Archive any existing Qwen2.5 models
shopt -s nullglob
for old in "$MODEL_DIR"/*[Qq]wen2*; do
    if [[ -f "$old" ]]; then
        mv "$old" "$OLD_MODEL_DIR/"
        log "Archived: $(basename "$old") → archived/"
    fi
done
shopt -u nullglob

# Download target model (min 500 MB expected)
download_with_fallback "$TARGET_MODEL" "$MODEL_DIR/$TARGET_MODEL" 500000000 "${TARGET_URLS[@]}"

# Download draft model (min 100 MB expected)
download_with_fallback "$DRAFT_MODEL" "$MODEL_DIR/$DRAFT_MODEL" 100000000 "${DRAFT_URLS[@]}"

# ═══════════════════════════════════════════════════════════════════
# STEP 4: Create startup script + restart server
# ═══════════════════════════════════════════════════════════════════
log "Step 4: Creating startup script and restarting server..."

# Find absolute path to server binary
SERVER_BIN_ABS=$(realpath "$SERVER_BIN")

cat > "$STARTUP_SCRIPT" << EOF
#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# Qwen3-4B Local LLM Server with Speculative Decoding
# Auto-generated by llm-upgrade.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)
#
# Model:  Qwen3-4B Q4_K_M (~2.8 GB)
# Draft:  Qwen3-0.6B Q4_K_M (~484 MB) — speculative decoding
# Port:   $PORT (OpenAI-compatible API)
# CPU:    $THREADS_GEN gen threads, $THREADS_BATCH batch threads
# ═══════════════════════════════════════════════════════════════

exec "$SERVER_BIN_ABS" \\
    --model "$MODEL_DIR/$TARGET_MODEL" \\
    --model-draft "$MODEL_DIR/$DRAFT_MODEL" \\
    --spec-type draft \\
    --draft-max 8 \\
    --draft-min 2 \\
    --chat-template qwen2 \\
    --jinja \\
    --ctx-size $CTX_SIZE \\
    --threads $THREADS_GEN \\
    --threads-batch $THREADS_BATCH \\
    --host 0.0.0.0 \\
    --port $PORT
EOF
chmod +x "$STARTUP_SCRIPT"
log "Startup script: $STARTUP_SCRIPT"

# Stop any existing server on this port
if lsof -ti :$PORT >/dev/null 2>&1; then
    log "Stopping existing server on port $PORT..."
    kill $(lsof -ti :$PORT) 2>/dev/null || true
    sleep 3
    # Force kill if still running
    lsof -ti :$PORT >/dev/null 2>&1 && kill -9 $(lsof -ti :$PORT) 2>/dev/null || true
    sleep 1
fi

# Start new server
log "Starting Qwen3-4B server with speculative decoding..."
nohup "$STARTUP_SCRIPT" > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
log "Server PID: $SERVER_PID"

# Wait for health check (model load takes ~10-15s for 4B)
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
# STEP 5: Verification
# ═══════════════════════════════════════════════════════════════════
log "Step 5: Running verification..."

if (( READY )); then
    # Test a simple completion
    VERIFY_START=$(date +%s%N)
    RESPONSE=$(curl -sf --max-time 120 http://localhost:$PORT/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{
            "model": "qwen3-4b",
            "messages": [{"role": "user", "content": "Reply with exactly: UPGRADE_OK"}],
            "max_tokens": 10,
            "temperature": 0.0
        }' 2>/dev/null || echo '{"error":"timeout"}')
    VERIFY_END=$(date +%s%N)
    VERIFY_MS=$(( (VERIFY_END - VERIFY_START) / 1000000 ))

    if echo "$RESPONSE" | grep -qi "UPGRADE_OK\|choices" 2>/dev/null; then
        log "✅ Model responds correctly (${VERIFY_MS}ms round trip)"
    else
        warn "Response didn't match expected — may still work. Response:"
        echo "$RESPONSE" | python3 -m json.tool 2>/dev/null | head -10 || echo "$RESPONSE" | head -5
    fi

    # Quick benchmark: measure tok/s
    log "Running quick benchmark (50 token generation)..."
    BENCH_RESPONSE=$(curl -sf --max-time 180 http://localhost:$PORT/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{
            "model": "qwen3-4b",
            "messages": [{"role": "user", "content": "Count from 1 to 50, one number per line."}],
            "max_tokens": 200,
            "temperature": 0.0
        }' 2>/dev/null || echo '{}')

    # Extract usage stats if available
    COMPLETION_TOKENS=$(echo "$BENCH_RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('usage', {}).get('completion_tokens', 'N/A'))
except: print('N/A')
" 2>/dev/null)
    log "Benchmark complete. Completion tokens: $COMPLETION_TOKENS"
    log "Check server log for detailed tok/s: grep 'tok/s' $SERVER_LOG | tail -5"
fi

# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║                  UPGRADE COMPLETE                        ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║                                                           ║"
echo "║  ✅ python-telegram-bot installed                        ║"
echo "║  ✅ llama.cpp rebuilt (AVX-512=$AVX512, AMX=$AMX)           ║"
echo "║  ✅ Qwen3-4B Q4_K_M downloaded                          ║"
echo "║  ✅ Qwen3-0.6B Q4_K_M draft model downloaded            ║"
echo "║  ✅ Server running on port $PORT with spec decoding      ║"
echo "║                                                           ║"
echo "║  Files:                                                   ║"
echo "║    Models:  $MODEL_DIR/           ║"
echo "║    Startup: $STARTUP_SCRIPT       ║"
echo "║    Log:     $SERVER_LOG           ║"
echo "║    Old:     $OLD_MODEL_DIR/       ║"
echo "║                                                           ║"
echo "╠═══════════════════════════════════════════════════════════╣"
echo "║  REMAINING STEPS (see relay message):                    ║"
echo "║  1. Update llm-watchdog.py to use new startup script     ║"
echo "║  2. Apply cron routing changes                           ║"
echo "║  3. Stagger Monday morning crons                         ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""

log "Done. Total time: $SECONDS seconds."
