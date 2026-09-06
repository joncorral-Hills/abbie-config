# Memory

## Technical Stack
- **Personal Assistant Platform**: Hermes Agent v0.20.0 Herald (running on Abacus AI SuperComputer, migrated 2026-07-30, upgraded 2026-08-06)
- **SuperComputer**: IP 208.122.8.11, port 22 (SSH, blocked at infra level), port 9119 (Hermes Gateway), port 8787 (Bridge API), $10/mo
  - **Cloudflare Tunnel**: systemd quick tunnel → `https://accessing-participate-hon-terminal.trycloudflare.com` (URL changes on restart, check `sudo journalctl -u cloudflared`)
  - **Bridge API Key**: `X-Bridge-Key: UCn0ayC8rB8VS0s3JhdZ7YsNBfzga5jxNF2PhX4qBeM`
  - **SSH**: Key authorized for `ubuntu` user, sshd on port 22, but Abacus infra blocks inbound port 22. Use tunnel+bridge instead.
  - **Hevy Webhook**: POST /webhook/hevy on bridge server, subscribed at hevy.com/settings?developer
- **Agent Name**: Allie (previously Abbie on OpenClaw)
- **Main Model**: deepseek/deepseek-v4-flash via OpenRouter
- **Fallback Model**: anthropic/claude-sonnet-4-6
- **Auxiliary Models**: gemini-3.5-flash via local endpoint (localhost:8081) — handles compression, vision, web_extract, session_search, approval
- **Local LLM**: Gemma 4 E4B IT Q4_K_M via llama.cpp (localhost:8082) — sensitive crons (finance, tax). ~5-6 tok/s generation. Draft model: Gemma 4 E2B at `/home/ubuntu/.local/models/gemma-4-E2B-it-Q4_K_M.gguf` (3.1 GB), ready for speculative decoding test.
  - **MCP SDK**: v1.29.0 (v2.0 breaks claude-agent-sdk dependency — stateless migration blocked until upstream fix)
  - **Approvals allowlist**: `python3 *`, `Check *` auto-approved. Circuit breaker active.
  - **Cron structured outputs**: 6 crons write JSON to `~/.hermes/cron_outputs/` for reliable inter-skill data flow (added 2026-08-08)
- **TTS**: Edge TTS (Aria voice), fallbacks: ElevenLabs, OpenAI, xAI, Mistral
- **Process Manager**: supervisord
- **Terminal**: Docker container (nikolaik/python3.11-nodejs20) with persistent shell
- **Primary Goals**:
  - Optimize token usage efficiency.
  - Establish a robust and clean memory structure.
  - Enhance overall utility, skills, and connections.

## Connected Platforms
- **Telegram**: DM with Jon (@JonCorr, ID 7605388765)
- **Hermes Gateway**: API server, supervisord-managed
- **Google Chat**: Alerts via webhook
- **Terminal**: Local backend, persistent shell, Docker

## Skills Library
- **33 categories, ~280+ skills** under `~/.hermes/skills/`
- Key categories: productivity, software-development, devops, autonomous-ai-agents, research, creative, mcp, github, bioinformatics (300+), cad-skill, media, smart-home, mlops, data-science, red-teaming, gaming
- Custom skills: financial-automation, financial-planner, health-automation, health-planner, digital-storefront-automation, digital-storefront-planner, invention-processor, project-board, billing-dispute-ai, patent-prior-art-scout, openscad, jupyter-live-kernel, native-mcp, job-search, resume-tailoring
- **MCP**: Native MCP client for stdio/HTTP servers

## Hermes Config Highlights
- Max turns per session: 60 ← was 90
- Gateway timeout: 30 min
- Approvals: smart mode (auto-approve safe ops, buttons for destructive)
- Cron approval mode: deny (no auto-execute)
- Delegation: max 3 parallel subagents, max spawn depth 1
- Context compression: enabled (35% threshold, 15% target, 200 msg hard limit) ← was 40%/400
- Memory: 2,200 chars (memory store) + 1,375 chars (user profile)
- Security: Tirith policy engine enabled
- Fallback providers chain: OpenRouter → Anthropic

## Notion Databases (Allie's Control Plane)

| DB | ID |
|:---|:---|
| **ALLIE page** | `36d63d55-66c5-8163-8bc9-c438cb43ce3b` |
| 📋 Project Board | `39563d55-66c5-81c3-827b-e124fc4bba17` |
| **INVENT page** | `52b3ad05-9b6a-431a-b994-de8b79cb16ea` |
| **FINANCE page** | `31e8275a-14ea-41b1-98c6-d3ec92de2bf9` |
| **Health & Fitness** | `36d63d55-66c5-8125-8c68-ee03bf91096c` |
| **ANTIGRAVITY page** | `37963d55-66c5-8152-9240-c6c2a34391ed` |
| ↳ Inbound Relay | `37963d55-66c5-813f-ba47-fc8e8f5acb67` |
| ↳ Outbound Relay | `37963d55-66c5-8127-a0f1-f32b446d828b` |
| ↳ Knowledge Index | `37963d55-66c5-8135-9d38-f46005672025` |
| **BUSINESS** child DBs | Shop `39d63d55-66c5-813e-8c5f-ea2515926d27`, Ideas `39d63d55-66c5-81c4-8307-eb50ddaaf96d`, Products `39d63d55-66c5-81bf-b824-e62a7c44ce31`, Listings `39d63d55-66c5-81cd-97b9-c55e5e345757`, Orders `39d63d55-66c5-8102-90ff-d99238dcee7d`, SEO `39d63d55-66c5-815f-a797-e85017d20447`, Snapshots `39d63d55-66c5-8195-8f56-cf7101ec8601` |

## Architecture Decisions

> **Full ADR archive**: See [memory/archive.md](file:///Users/JonCorral/Documents/Abbie/memory/archive.md) for all completed ADRs (18 entries, June–August 2026).

### Active Pending Items

| Item | Blocker | Owner |
|:---|:---|:---|
| Financial planner crons #8–#14 | Never deployed on VM | Jon/Allie |
| Etsy storefront crons B1–B8 | Waiting on `ETSY_API_KEY`, `ETSY_SHARED_SECRET`, `ETSY_SHOP_ID` | Jon |
| World Monitor integration | Waiting on subscription (\$39.99/mo) + `WORLDMONITOR_API_KEY` | Jon |
| Apple Health webhook | Jon needs Health Auto Export setup on iPhone | Jon |
| Interest rates, debt balances, 401(k) | Needed for financial planner scripts | Jon |
| Speculative decoding (E2B draft) | Only if RAM headroom allows | Allie |
| VM git remote update | `git remote set-url origin https://github.com/jcorral10/abbie-config.git` | Allie |

### Household Financial Profile
- **Jon**: $2,860 biweekly (every other Friday), 26 paychecks/yr = ~$74,360/yr
- **Wife**: $1,800 semi-monthly (1st & 15th), 24 paychecks/yr = $43,200/yr
- **Combined monthly base**: $9,320
- **Banks**: Chase (Sapphire Reserve, Freedom Flex, Freedom Unlimited, checking), US Bank (checking/savings), Capital One (Venture X upgrade in progress), Amazon Prime Card, Crypto.com Ruby
- **Total fixed obligations**: $5,720.86/mo (USB Autopay $4,655 + Flex Autopay $903 + Other $163)
- **Monthly margin at targets**: ~$1,149
- **ER payment plan**: $150/mo from savings, ~16 months remaining
- **Northwestern Mutual**: Whole life/IBC, $1M/30yr, $95.46/mo
- **Investments**: Schwab ($10/mo), Jack Custodial IRA ($3/mo), Jaime 401k (Alight), Jon 401k (TBD)

### Active Crons Summary (v2 — Sep 2, 2026)
Orchestrator (default) owns all 16 crons + 2 system crontab jobs. Specialists have ZERO crons.
- **[FIN]**: 5 crons (Plaid sync, cost review, monthly update, TX2 quarterly, TX3 annual)
- **[HEALTH]**: 3 crons (Hevy sync, body metrics, weekly fitness & training report)
- **[HOME]**: 3 crons (travel watch, weekly maint, seasonal prep)
- **[MKT]**: 1 cron (stock weekly briefing)
- **[OPS]**: 2 crons (daily system health check, weekly ops report)
- **[DEFAULT]**: 2 crons (LS1 life score, CAL2 calendar intel) + stale sweeper (system crontab)

### Key Architecture Facts (v2.1)
- **Architecture**: Orchestrator + 10 specialists, `bot_mode_protocol: true`
- **Orchestrator**: default profile, all crons, 6 skills (project-board, life-score, calendar, work-context-handoff, allie-skill-builder, system-health)
- **Specialists**: finance-bot, health-bot, market-bot, home-bot, plant-bot, work-bot, osint-bot, invent-bot, job-bot, travel-bot — zero crons, pruned skills, on-demand via CLI wrappers
- **Models**: deepseek (orchestrator, finance, health, job), gemini-local (market, home, plant, work, osint, invent, travel)
- **Cross-bot**: Peers communicate via CLI wrappers — Finance↔Market, Invent→OSINT, Invent→Home, Home↔Plant, Job→Finance/Work
- **Bridge**: FastAPI on port 8787, Cloudflare tunnel, Notion as fallback
- **Robinhood MCP**: Market Bot = primary trader (approval-gated), Antigravity = suggestion mode only
- **HA**: `ha.clevercorral.com` → 364 entities, Home Bot manages via n8n webhooks
- **Repo**: `https://github.com/jcorral10/abbie-config.git`

## Long-Term User Preferences
- Jon approves **auto-escalation** — Allie can switch models without asking when task complexity warrants it
- Prefers explicit approval gates for side-effect actions (not model switching)
- Heartbeats currently disabled at user request
- Weekly synthesis and financial crons should run on mid-tier model
- Antigravity (this agent) runs on-demand via Gemini/Claude, independent billing from Allie
