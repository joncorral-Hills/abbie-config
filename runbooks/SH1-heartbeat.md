# SH1 — Heartbeat Monitor (Bash Script)

## Schedule
Every 4 hours: `0 */4 * * *` (reduced from every 2h)

## What to Do
Run the heartbeat bash script — **no LLM inference needed**.

```bash
bash ~/abbie-config/scripts/heartbeat.sh
```

## What It Checks
- Bridge API (localhost:8787)
- gemini-local (localhost:8081)
- llama-local (localhost:8082)
- Notion API
- Telegram Bot API
- n8n (192.168.1.143:5678, non-critical)

## State Tracking
Previous state persisted at `~/.hermes/cron_outputs/heartbeat_state.json`.
Alerts fire only on **state transitions** (healthy→down or down→healthy).

## On Failure
If multiple critical services are down, the script sends a Telegram alert.
No remediation — just notification. Remediation is handled by SH5 Watchdog.
