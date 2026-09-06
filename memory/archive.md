# Memory Archive — Completed ADRs

> Archived from MEMORY.md on 2026-08-29 to reduce context footprint.
> These decisions are finalized and no longer need to be in active memory.

---

### 2026-06-08: Migration from OpenClaw to Hermes
- **Decision**: Full migration from OpenClaw to Hermes Agent (now v0.15.2)
- **Impact**: New skill format, new config structure, new platform integrations
- **Previous**: OpenClaw with Abacus RouteLLM, `openclaw.json` config
- **Current**: Hermes with OpenRouter primary, local Gemini auxiliary at localhost:8081
- **Notion integration**: Unchanged — same NOTION_API_KEY, pages must be explicitly shared

### 2026-05-27: Invention Idea Processor
- **Decision**: Build `#invent` trigger skill for IP/market analysis
- **Notion DB**: INVENT page (`52b3ad05-9b6a-431a-b994-de8b79cb16ea`) with Ideas DB (16 properties)
- **Skill Location**: `~/.hermes/skills/` (migrated from `.agents/skills/invention-processor/`)
- **Triggers**: `#invent` tag, "invention idea" phrase, and secondary patterns
- **Pipeline**: Detect → Capture (Notion) → IP Screen (web search) → Market Analysis → Cross-Reference → Improvement Suggestions → Report

### 2026-05-26: Financial Automation System
- **Decision**: Build Notion-based personal finance automation
- **Notion DB**: FINANCE page (`31e8275a-14ea-41b1-98c6-d3ec92de2bf9`) with 7 child DBs (Accounts, Categories, Budgets, Transactions, Statements, Bills & Budget, Financial Roadmap)
- **PDF Processing**: pdfplumber + LLM categorization for Chase (credit + checking) and US Bank statements
- **Cron**: Monthly Financial Update on 1st of month @ 9am (deepseek-v4-flash)
- **Merchant Cache**: Self-learning JSON mapping, pre-seeded with 60+ known merchants

### 2026-06-09: Financial Planner Upgrade
- **Decision**: Upgrade Allie from budget tracker to personal accountant/financial planner
- **New Skill**: `financial-planner` with 5 modules (Net Worth, Cash Flow, Debt Payoff, Credit Card Rewards, Financial Health Score)
- **Data Corrections**: Discovered $1,462/mo in untracked bills, 5 incorrect amounts, 6 credit cards (skill only knew 1)
- **Scripts**: debt_calculator.py, cash_flow_forecast.py, rewards_optimizer.py — all tested and working
- **Deployment**: Commit 4d1000a pushed to abbie-config, task sent to Allie via bridge
- **Pending**: Jon needs to provide interest rates, debt balances, 401(k) details

### 2026-07-14: Digital Storefront System
- **Decision**: Build two-layer digital business operating system for Etsy digital product sales
- **New Skills**: `digital-storefront-automation` + `digital-storefront-planner`
- **Platform**: Etsy API v3 (OAuth 2.0 PKCE)
- **Notion DB**: BUSINESS page (under ALLIE) with 7 child DBs
- **Total**: 10,246 lines across 17 files
- **Deployment**: Commit eaf5e8f pushed, skills installed on VM 2026-07-14
- **Pending**: Etsy developer account + API keys, then deploy crons B1-B8

### 2026-06-10: Health & Fitness System
- **Decision**: Build two-layer health operating system mirroring the financial architecture
- **New Skills**: `health-automation` + `health-planner`
- **Data Sources**: Hevy API, Apple Health via webhook, Notion DBs, Telegram
- **Scripts**: hevy_sync.py (1094 lines), health_webhook.py (824 lines), lab_interpreter.py (1376 lines)
- **10 Cron Jobs**: H1–H10
- **Deployment**: Commit 50aa6f4 pushed to abbie-config

### 2026-07-20: Robinhood MCP Integration
- **Decision**: Connected Robinhood Agentic Trading MCP to both Antigravity (Mac) and Allie (Hermes VM)
- **MCP URL**: `https://agent.robinhood.com/mcp/trading`
- **Agentic Account**: 959217308 (nickname "Agentic", cash account, individual)
- **Walled Off**: Main brokerage (••••4705) and Roth IRA (••••2482)
- **Allie Role**: Primary trader; **Antigravity Role**: Suggestion mode only
- **First Trade**: 0.141 shares GOOGL @ $354.74

### 2026-07-27: World Monitor Integration (PARKED)
- **Status**: ⏸️ PARKED — waiting for World Monitor Pro subscription
- **Files Built**: `.agents/skills/world-intelligence/` (ready to deploy)
- **Blocker**: `WORLDMONITOR_API_KEY` env var needed on VM

### 2026-07-28: Local LLM Upgrade (Qwen2.5-7B → Qwen3-4B)
- **Results**: Gen speed 0.75 → 3.8 tok/s (5x), model size 4.5 → 2.4 GB (-47%)
- **Deployment**: Commit 49f3cb6, Allie executed via Telegram

### 2026-07-30: Abacus AI SuperComputer Migration + HTTP Bridge
- **Decision**: Allie moved to Abacus AI SuperComputer; direct HTTP bridge replacing Notion relay
- **Bridge Server**: `bridge/server/main.py` — FastAPI on port 8787
- **Notion Relay**: Kept as permanent fallback

### 2026-07-31: Local LLM Upgrade (Qwen3-4B → Gemma 4 E4B)
- **Model**: Gemma 4 E4B IT Q4_K_M (4.0 GB, ~4.5B active params)
- **Draft Model**: Gemma 4 E2B (2.9 GB) staged for speculative decoding
- **n8n Evaluated and Rejected**: 500 MB-1 GB idle RAM too expensive

### 2026-08-16: Firecrawl "Website Not Supported" Fix
- **Root Cause**: Abacus AI VPS `/etc/environment` overriding API keys with broken proxy
- **Fix**: Upgraded firecrawl-py, set correct env vars in Hermes systemd service
- **Lesson**: Always check `/etc/environment` on Abacus AI VPS images

### 2026-08-24: Bot Mode Activation
- **Decision**: Split monolithic Allie into 9 specialist bot profiles
- **Config**: `agent.bot_mode_protocol: true`
- **Scripts**: `scripts/bot-mode-activate.sh`, `scripts/bot-mode-cron-migrate.sh`
- **Commits**: c4aeb54, 1a41c30, e4206c3, 00c2ec5

### 2026-08-24: Repo Transfer
- **Decision**: Transferred `abbie-config` from `joncorral-Hills` to `jcorral10`
- **Remote URL**: `https://github.com/jcorral10/abbie-config.git`

### 2026-08-25: ops-bot (System Health Monitor)
- **New Skill**: `system-health` with 6 modules (SH1-SH6)
- **Ops Score**: Composite 0–100 metric
- **Deployed**: All files pushed, Notion DB created, 6 crons registered

### 2026-08-25: Memory Audit — 85% → 19% (→ ~80% post-cron-fixes)
- **Fix**: Removed 8 entries, offloaded to soul files
- **Result**: 3 entries (418 chars, 19%) — grew back to ~80% after cron error fixes

### 2026-08-25: finance-bot Model Change (llama-local → deepseek-v4-flash)
- **Problem**: Hermes system prompt ~18K tokens overflows llama-local 16K context
- **Fix**: Changed finance-bot primary to deepseek-v4-flash; llama-local for explicit PII only

### 2026-08-25: gemini-local Fix (gemini-web2api → curl-based proxy)
- **Fix**: curl-based proxy at `~/.local/bin/gemini-local-proxy.py`
- **Architecture**: gemini-local (8081) + llama-local (8082) + deepseek-v4-flash (OpenRouter)

### 2026-08-26: CleverCorral.com — HA Cloudflare Tunnel (COMPLETE ✅)
- **Domain**: clevercorral.com on Cloudflare, DNS Full, SSL Active
- **Route**: `ha.clevercorral.com` → HA instance
- **Root Cause of 400 errors**: HA 2026.8 migrated `http` to `.storage/http`
- **Trusted Proxies** (in `.storage/http`): `127.0.0.1/32`, `172.30.32.0/23`, `192.168.1.0/24`
- **API verified**: 364 entities accessible

### 2026-09-01: Bot Mode Collapsed — Single Profile Restoration
- **Decision**: Reversed the Aug 24 bot-mode split. Collapsed 9 profiles back to single default profile.
- **Root Cause**: 8 days of cascading failures traced to per-profile isolation: stale-exec deadlocks across separate SQLite DBs, provider drift lockouts, circular monitoring (ops-bot couldn't monitor itself), Claude credit drain ($50), silent cron failures.
- **New Architecture**: Single profile, 17 tagged crons (down from 23), `bot_mode_protocol: false`
- **Model Policy**: gemini-local default; deepseek for finance, personal health, and complex synthesis
- **Cron Changes**: Removed TX1 tax cron. Combined fitness + training into one report. Combined SH1–SH5 into single daily health check.
- **System Jobs**: Stale-exec sweeper + heartbeat moved to system crontab (immune to Hermes failures, zero tokens)
- **SOUL**: Unified soul retains coordinator domain-routing pattern without inter-agent delegation
- **Scripts**: `cron-consolidate.sh` (deployment), `bot-mode-activate.sh` + `bot-mode-cron-migrate.sh` archived to `scripts/archive/`
- **Lesson**: Hermes profiles are designed for conversational isolation, not cron isolation. Crons are stateless one-shots that benefit from a single reliable execution path, not 9 fragile ones.

### 2026-09-02: v2 Bot Fleet — Orchestrator + 8 Specialists
- **Decision**: Re-introduce specialist bot profiles with a fundamentally different architecture than v1.
- **Key Change**: Specialists have ZERO crons. All scheduling stays on the orchestrator (default profile). Specialists are activated on-demand via `message_agent()` for interactive queries and complex cron delegation.
- **Specialists**: finance-bot (deepseek), health-bot (deepseek), market-bot (gemini-local), home-bot (gemini-local+n8n), plant-bot (gemini-local), work-bot (gemini-local), osint-bot (gemini-local), invent-bot (gemini-local)
- **New Domains**: Plant & Garden (lawn/fertilizer/watering), OSINT/Security (people search, digital footprint), Work (goals, salary, monday.com)
- **Orchestrator Pruned**: Only 6 skills (project-board, life-score, calendar, work-context-handoff, allie-skill-builder, system-health). Domain skills live with specialists.
- **Cross-Bot Communication**: `bot_mode_protocol: true` enables peer-to-peer message_agent() — Finance↔Market, Invent→OSINT, Invent→Home, Home↔Plant
- **Memory Model**: Total persistent memory expanded from 2,200 to 19,800 chars (9 × 2,200). Orchestrator context window 3-4x smaller (6 skills vs 22).
- **New Skills Needed**: plant-garden, home-hub, work-ops, osint-recon
- **Lesson**: The v1 failure was coupling scheduling to profile isolation. v2 separates the execution plane (orchestrator owns the clock) from the delegation plane (specialists own the expertise).
