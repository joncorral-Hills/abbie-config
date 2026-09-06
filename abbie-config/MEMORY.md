# Memory

## Technical Stack
- **Personal Assistant Platform**: Hermes Agent v0.18.2 (running on Ubuntu VM, verified 2026-07-06)
- **Agent Name**: Allie (previously Abbie on OpenClaw)
- **Main Model**: deepseek/deepseek-v4-flash via OpenRouter
- **Fallback Model**: anthropic/claude-sonnet-4-6
- **Auxiliary Models**: gemini-3.5-flash via local endpoint (localhost:8081) — handles compression, vision, web_extract, session_search, approval
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
- Max turns per session: 90
- Gateway timeout: 30 min
- Approvals: smart mode (auto-approve safe ops, buttons for destructive)
- Cron approval mode: deny (no auto-execute)
- Delegation: max 3 parallel subagents, max spawn depth 1
- Context compression: enabled (40% threshold, 15% target, 400 msg hard limit)
- Memory: 2,200 chars (memory store) + 1,375 chars (user profile)
- Security: Tirith policy engine enabled
- Fallback providers chain: OpenRouter → Anthropic

## Architecture Decisions

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

### Notion Databases (Allie's Control Plane)
- **ALLIE page** (`36d63d55-66c5-8163-8bc9-c438cb43ce3b`): MEMORY, SKILLS, DAILY LOGS, 📋 Project Board (`39563d55-66c5-81c3-827b-e124fc4bba17`)
- **INVENT page** (`52b3ad05-9b6a-431a-b994-de8b79cb16ea`): Ideas DB (16 properties)
- **FINANCE page** (`31e8275a-14ea-41b1-98c6-d3ec92de2bf9`): Accounts, Categories, Budgets, Transactions, Statements, Bills & Budget, Financial Roadmap
- **Health & Fitness page** (`36d63d55-66c5-8125-8c68-ee03bf91096c`): Workouts, PRs, Medications, Lab Results, Lab Markers
- **ANTIGRAVITY page** (`37963d55-66c5-8152-9240-c6c2a34391ed`): Bridge between Antigravity (Mac) and Allie (VM)
  - Inbound Relay DB (`37963d55-66c5-813f-ba47-fc8e8f5acb67`): Antigravity → Allie messages
  - Outbound Relay DB (`37963d55-66c5-8127-a0f1-f32b446d828b`): Allie → Antigravity messages
  - Knowledge Index DB (`37963d55-66c5-8135-9d38-f46005672025`): Shared resource catalog
  - Bridge script: `scripts/notion_bridge.py` (config: `scripts/.notion_config.json`, gitignored)

### Household Financial Profile
- **Jon**: $2,860 biweekly (every other Friday), 26 paychecks/yr = ~$74,360/yr
- **Wife**: $1,800 semi-monthly (1st & 15th), 24 paychecks/yr = $43,200/yr
- **Combined monthly base**: $9,320
- **Banks**: Chase (Sapphire Reserve, Freedom Flex, Freedom Unlimited, checking), US Bank (checking/savings), Capital One (Venture X upgrade in progress), Amazon Prime Card, Crypto.com Ruby
- **Total fixed obligations**: $5,720.86/mo (USB Autopay $4,655 + Flex Autopay $903 + Other $163)
- **Monthly margin at targets**: ~$1,149 (corrected from $2,096 on 2026-06-09 after discovering $1,462/mo in untracked bills)
- **Bar mitzvah**: $6,141 balance, deferred to July 2026
- **ER payment plan**: $150/mo from savings, ~16 months remaining
- **Northwestern Mutual**: Whole life/IBC, $1M/30yr, $95.46/mo
- **Investments**: Schwab ($10/mo), Jack Custodial IRA ($3/mo), Jaime 401k (Alight), Jon 401k (TBD)

### Active Crons (verified 2026-07-06 from Allie's live report)
1. Monthly Financial Update — 1st @ 9am
2. hevy-daily-sync — Daily @ 10am
3. hevy-body-metrics-sync — Sundays @ 8am
4. weekly-training-intelligence — Sundays @ 7pm
5. drive-health-reader — Daily @ 8am & 6pm
6. weekly-cost-review — Mondays @ 10am
7. weekly-fitness-overview — Mondays @ 9am

**Not deployed**: 7 financial-planner crons (#8–#14) from SKILL.md were never created on the VM

### 2026-06-09: Financial Planner Upgrade
- **Decision**: Upgrade Allie from budget tracker to personal accountant/financial planner
- **New Skill**: `financial-planner` with 5 modules (Net Worth, Cash Flow, Debt Payoff, Credit Card Rewards, Financial Health Score)
- **Data Corrections**: Discovered $1,462/mo in untracked bills, 5 incorrect amounts, 6 credit cards (skill only knew 1)
- **Scripts**: debt_calculator.py, cash_flow_forecast.py, rewards_optimizer.py — all tested and working
- **Deployment**: Commit 4d1000a pushed to abbie-config, task sent to Allie via bridge
- **Pending**: Jon needs to provide interest rates, debt balances, 401(k) details

### 2026-07-14: Digital Storefront System
- **Decision**: Build two-layer digital business operating system for Etsy digital product sales
- **New Skills**: `digital-storefront-automation` (tactical: Etsy API, product files, orders, revenue) + `digital-storefront-planner` (strategic: niche research, SEO, pricing, business health, autonomous growth loop)
- **Platform**: Etsy API v3 (OAuth 2.0 PKCE)
- **Notion DB**: BUSINESS page (TBD — created during setup) with 7 child DBs (Shop Config, Product Ideas, Products, Listings, Orders, SEO Keywords, Business Snapshots)
- **Automation Scripts**: etsy_client.py (1041 lines, full API client), product_manager.py (1041 lines, file lifecycle), revenue_sync.py (743 lines, order/fee sync)
- **Planner Scripts**: niche_researcher.py (1197 lines, trend/demand/competition scoring), seo_optimizer.py (1316 lines, keyword research + listing audit), pricing_engine.py (838 lines, competitive analysis), product_creator.py (1562 lines, generates printable PDFs, SVGs, spreadsheets, social templates, wall art, resumes, checklists)
- **8 Cron Jobs**: B1 Daily Sales Sync (11PM), B2 Listing Health (Mon/Thu 9AM), B3 Product Upload Monitor (8AM), B4 Weekly Niche Scout (Sun 10AM), B5 SEO Audit (Wed 9AM), B6 Monthly Business Review (1st 10AM), B7 Competitor Watch (1st/15th 8AM), B8 Growth Loop Trigger (Sat 11AM)
- **Autonomous Growth Loop**: SCAN → VALIDATE → IDEATE → CREATE → OPTIMIZE → LIST → MONITOR → ITERATE (approval gates at CREATE and LIST via Telegram)
- **Total**: 10,246 lines across 17 files
- **Pending**: Etsy developer account + API keys, Etsy shop setup, Notion BUSINESS page creation, pip install dependencies, cron deployment on VM

### 2026-06-10: Health & Fitness System
- **Decision**: Build two-layer health operating system mirroring the financial architecture
- **New Skills**: `health-automation` (tactical data collection) + `health-planner` (strategic intelligence)
- **Data Sources**: Hevy API (workouts, body metrics, PRs), Apple Health via Health Auto Export ($24.99 lifetime → webhook), Notion DBs (medications, labs), Telegram (supplements, injuries)
- **Hevy API**: REST API with `api-key` header auth. Endpoints: workouts, workouts/events (delta sync), body_measurements, exercise_templates, exercise_history, routines
- **Apple Health Bridge**: Health Auto Export iOS app → POST JSON to `https://VM/api/health` → FastAPI receiver (`health_webhook.py`) → SQLite (`health_data.db`)
- **Scripts**: hevy_sync.py (1094 lines, workout+body metrics+PR sync), health_webhook.py (824 lines, FastAPI receiver), lab_interpreter.py (1376 lines, PDF parser+trends)
- **New Notion DBs**: Body Metrics, Injuries, Family Health Calendar, Health Snapshots
- **Enhanced Notion DBs**: Medications (9 new supplement fields), Lab Markers (optimal ranges + categories)
- **10 Cron Jobs**: H1 Hevy Sync (daily 10PM), H2 Body Metrics (Sat 8AM), H3 Weekly Summary (Sun 7PM), H4 Supplement Reorder (Wed 9AM), H5 Recovery Score (daily 7AM), H6 Training Intel (Sun 7:15PM), H7 Health Score (1st 8:30PM), H8 Biomarker Trends (on new labs), H9 Family Cal (Mon 8AM), H10 Supplement Schedule (daily 7AM/9PM)
- **Resources**: 45+ lab reference ranges, 15 supplement timing profiles, 41 exercise form library entries, health score weights
- **Deployment**: Commit 50aa6f4 pushed to abbie-config
- **Pending**: Jon needs to set up Health Auto Export on iPhone, confirm VM HTTPS endpoint accessibility, provide Hevy API key to Allie's env

## Long-Term User Preferences
- Jon approves **auto-escalation** — Allie can switch models without asking when task complexity warrants it
- Prefers explicit approval gates for side-effect actions (not model switching)
- Heartbeats currently disabled at user request
- Weekly synthesis and financial crons should run on mid-tier model
- Antigravity (this agent) runs on-demand via Gemini/Claude, independent billing from Allie

