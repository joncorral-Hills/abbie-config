# Local LLM (Qwen2.5-7B) — Setup & Diagnosis Summary

Generated: 2026-07-28
For: External agent review — diagnose and recommend a path forward.

---

## 1. Current Architecture

Two local servers managed by a shared watchdog (`~/.hermes/scripts/llm-watchdog.py`):

| Service | Port | Model | Type | Cost |
|---------|------|-------|------|------|
| Gemini Proxy | 8081 | gemini-3.5-flash + 5 variants | Web-to-API proxy (Google Gemini) | Free (public web auth) |
| Local LLM | 8082 | Qwen2.5-7B-Instruct Q4_K_M (4.5 GB GGUF) | Fully local llama.cpp server | Free (CPU only) |

Both servers are registered as Hermes providers:

- `gemini-local` → http://localhost:8081/v1 — auxiliary tasks (vision, compression, web extraction)
- `llama-local` → http://localhost:8082/v1 — sensitive cron jobs (finance, health, tax, home, travel)
- Fallback → `openrouter/deepseek/deepseek-v4-flash`

---

## 2. VM Specs (Current Host)

| Resource | Value |
|----------|-------|
| **CPU** | Intel Xeon 6975P-C, 16 cores / 32 threads |
| **L3 Cache** | 480 MiB |
| **RAM** | 495 GiB total (139 GiB used, 356 GiB available) |
| **Swap** | 122 GiB (118 MiB used) |
| **Disk** | 1,007 GiB overlay (315 GiB used, 641 GiB free) |
| **GPU** | **None** — CPU-only inference |
| **llama.cpp version** | 1 (0ed235e), built with GCC 12.2.0, x86_64 |

Conclusion: Plenty of RAM and disk. No GPU. All inference is CPU-bound via llama.cpp with 32 threads.

---

## 3. Qwen2.5-7B Performance Characteristics

Measured on this hardware:

| Metric | Value |
|--------|-------|
| Model size | 4.5 GB (Q4_K_M quantization) |
| Context window | 8192 tokens (limited by server args; model supports 32768) |
| Vocabulary | 152,064 tokens (native Qwen2.5 — standard, not "extended") |
| **Prompt processing** | ~7.8 tok/s |
| **Generation speed** | **~0.75 tok/s** |
| Model load time | ~24-30 seconds |
| CPU threads | 32 (all available) |

### Time-to-complete estimates (0.75 tok/s generation)

| Output length | Wall time |
|---------------|-----------|
| 10 tokens (trivial reply) | ~13 sec |
| 100 tokens (short summary) | ~2.2 min |
| 200 tokens (briefing) | ~4.5 min |
| 500 tokens (report) | ~11 min |
| 1000 tokens (long analysis) | ~22 min |

This is slow but survivable for unattended background cron jobs — provided the cron timeout is generous (Hermes default is 1800s/30min).

---

## 4. Cron Jobs Routed to `llama-local` (9 total)

| Job | Schedule | Status | Notes |
|-----|----------|--------|-------|
| Monthly Financial Update | 9am 1st | OK | — |
| weekly-training-intelligence | 7pm Sun | OK | — |
| **weekly-fitness-overview** | 9am Mon | **Delivery Error** | python-telegram-bot not installed |
| **HM1 - Weekly Home Maint Check** | 8am Mon | **Delivery Error** | python-telegram-bot not installed |
| HM2 - Seasonal Home Maint Prep | 9am quarter-start | OK | — |
| LS1 - Monthly Life Score Report | 9pm 3rd | OK | — |
| TX1 - Quarterly Tax Deadline | 9am quarter-start | OK | — |
| TX2 - Monthly Tax Deduction Scan | 10am 5th | OK | — |
| TX3 - Quarterly Tax Dashboard | 8pm quarter-start | OK | — |
| CAL2 - Weekly Conflict Scan | 7pm Sun | OK | — |

### Important finding: the reported "failures" are NOT Qwen failures

Both errored jobs (`weekly-fitness-overview`, `HM1`) have `last_status: ok` — meaning the model ran successfully and produced output. The error is only in **delivery**:

```
delivery error: python-telegram-bot not installed. Run: pip install python-telegram-bot
```

This is a known infrastructure issue — `python-telegram-bot` was never installed on this host.

---

## 5. Server Health & Uptime

The watchdog log shows **continuous uptime with zero failures** in the observed window (many hours):

```
[2026-07-28 13:55:54] Gemini proxy OK
[2026-07-28 13:55:54] Llama server OK
[2026-07-28 13:56:54] ...OK (repeating every 60s)
```

- No "UNRESPONSIVE" events
- No restarts
- No crash loops
- Old watchdog log (from .hermes/home/ directory) also shows no failures

---

## 6. Known Issues & Bottlenecks

### A. Speed — the core problem (~0.75 tok/s)

7B parameter model on CPU with 32 threads is simply slow. The Q4_K_M quantization helps but output projection is still the bottleneck (no GPU acceleration). This makes interactive use impractical and causes long delays in cron job completion — users experience "it's thinking forever."

### B. Delivery infrastructure gap

`python-telegram-bot` is not installed, causing delivery errors for any cron job with `deliver: telegram` or even `deliver: origin` (Hermes uses python-telegram-bot for all Telegram delivery regardless of the deliver field).

Fix: `pip install python-telegram-bot`

### C. Multi-cron queue contention

When multiple `llama-local` cron jobs trigger simultaneously (e.g., Sunday evening has 3 jobs: training-intelligence, conflict-scan, and possibly overlapping maintenance jobs), requests queue at the single llama-server process. Each job must wait for the previous one to finish generating. With 0.75 tok/s and jobs producing 200-500 token outputs, back-to-back jobs can create a 15-30 minute processing backlog.

### D. No GPU — limited upside

Without a GPU, the only way to speed up local inference is:
- Switch to a smaller model (3B or 1.5B) → faster but lower quality
- Switch to a CPU-optimized model architecture (e.g., Phi-3-mini-4k)
- Use fewer quantization bits (Q3_K_M or Q2_K) → faster but more quality loss
- Increase threads aggressively (already at 32)

### E. Limited context window (8192 vs 32768 capacity)

The server is launched with `-c 8192` despite the model supporting 32768. This limits how much context sensitive jobs can include. Possibly intentional for speed.

---

## 7. Questions for the Diagnostic Agent

1. **Is 0.75 tok/s acceptable for background cron jobs?** The current jobs produce brief outputs (100-300 tokens). At 0.75 tok/s, each takes 2-7 minutes. Is this tolerable?

2. **Do we want to keep a local model at all?** The Gemini proxy (gemini-web2api) is free, faster, and has been equally reliable. The only reason to keep the local model is privacy for financial/health/tax data. The real privacy question: is sending financial summaries to Google's free Gemini endpoint (which is NOT a standard API — it's a web scraper proxy) actually more private than using OpenRouter/DeepSeek?

3. **Should we swap to a smaller local model?** A 3B model like Phi-3-mini or Qwen2.5-3B would run ~2-3x faster on CPU with acceptable quality for structured task outputs.

4. **Should we reinstall the watchdog + servers?** The watchdog has file path quirks (logs to both ~/.hermes/logs/ and ~/.hermes/home/.hermes/logs/ due to PATH.home() override). Should consolidate.

5. **Is there a missing failure mode not captured in logs?** Jon reports the model gets "overwhelmed with existing crons." The watchdog shows no failures, but perhaps some cron jobs timeout silently, or responses are truncated/empty, and the error isn't logged because the model technically returned _something_.

---

## 8. Recommendations to Evaluate

### Option A: Fix delivery, keep Qwen
- Install `python-telegram-bot` — fixes the two "failed" jobs instantly
- Accept 0.75 tok/s for background crons
- Increase context window: change `-c 8192` to `-c 16384` in watchdog
- Add concurrency detection: stagger cron schedules to avoid queue pileup

### Option B: Swap Qwen for a smaller CPU model
- Replace with Qwen2.5-3B Q4_K_M (~2 GB) or Phi-3-mini-4k Q4_K_M (~2.3 GB)
- Expected speed: ~2-3 tok/s generation (3-4x faster)
- Accept some quality degradation for structured template outputs
- Still fully local, fully private

### Option C: Route sensitive jobs through Gemini proxy
- Data already leaves the machine for non-sensitive tasks via gemini-web2api
- Financial/health data goes to Google's free web frontend (same privacy level)
- Eliminates the local model entirely — simpler architecture, zero maintenance
- gemini-web2api is faster but fragile (Google can break the proxy at any time)

### Option D: Hybrid — Gemini proxy for fast track, local as fallback
- Move all cron jobs to gemini-local by default
- Keep Qwen as emergency fallback if Gemini proxy breaks
- Only 1-2 jobs on local at most

---

## Files Referenced

- Watchdog: `/home/ubuntu/.hermes/scripts/llm-watchdog.py`
- Startup: `/home/ubuntu/.hermes/scripts/llm-start.sh`
- Gemini proxy: `/home/ubuntu/gemini-web2api/gemini_web2api.py`
- Model: `/home/ubuntu/qwen2.5-7b-q4_k_m.gguf` (4.5 GB)
- Hermes config: `/home/ubuntu/.hermes/config.yaml`
- Cron jobs: `/home/ubuntu/.hermes/cron/jobs.json`
- Watchdog log: `/home/ubuntu/.hermes/logs/llm-watchdog.log`