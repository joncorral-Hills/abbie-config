---
name: system-health
description: >
  System health monitoring and ops intelligence for Allie's bot fleet. Runs
  heartbeat checks on all endpoints and local LLMs, audits cron execution
  against a master registry, validates API tokens, monitors storage and memory,
  performs watchdog functions with Telegram-gated remediation, analyzes token
  usage for optimization opportunities, and generates a weekly Ops Score (0-100).
  Feeds ops_score_latest.json for Life Score consumption.
requires:
  bins: [python3]
  env: [NOTION_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]
---

# System Health (system-health)

## Overview

The `system-health` skill is the operational backbone of Allie's bot fleet. It continuously monitors infrastructure, validates integrations, audits cron reliability, tracks token efficiency, and produces a composite Ops Score. It runs on the `ops-bot` profile — the 9th specialist in Allie's fleet.

### Architecture

```ascii
                    ┌──────────────────────┐
                    │      ops-bot         │
                    │  (System Health)     │
                    │  gemini-local /      │
                    │  fallback deepseek   │
                    └──────────┬───────────┘
                               │
    ┌──────┬──────┬──────┬─────┴─────┬──────┐
    │      │      │      │           │      │
    ▼      ▼      ▼      ▼           ▼      ▼
  SH1    SH2    SH3    SH4        SH5    SH6
  Heart  Cron   Token  Memory     Watch  Weekly
  beat   Audit  & API  & Store    dog    Ops
  Mon.         Audit   Audit            Report
```

### Dependency Chain

```
bridge/server/main.py (endpoints)  ← SH1, SH4, SH5 read
~/.hermes/config.yaml              ← SH2 reads cron definitions
~/.hermes/cron_outputs/*.json      ← SH2 validates timestamps
~/.hermes/bridge_cron_reports.jsonl ← SH2 reads execution history
📋 Project Board DB                ← SH5 reads for stale items
📡 System Health DB (NEW)          ← SH1–SH6 write snapshots & incidents
ops_score_latest.json              ← SH6 writes for Life Score
```

### Parent Notion Pages

- **ALLIE page**: `36d63d55-66c5-8163-8bc9-c438cb43ce3b` (parent for 📡 System Health DB)

---

## Setup (One-Time)

### 1. Create Notion Database: `📡 System Health`

Create this inline database under the **ALLIE** page (`36d63d55-66c5-8163-8bc9-c438cb43ce3b`).

| Property | Type | Details |
| :--- | :--- | :--- |
| `Date` | Title | Format: YYYY-MM-DD |
| `Ops Score` | Number | 0–100, number format |
| `Uptime %` | Number | Percent format |
| `Crons OK` | Number | Count of successful crons |
| `Crons Failed` | Number | Count of failed/missed crons |
| `APIs Healthy` | Number | Count of valid API keys |
| `APIs Degraded` | Number | Count of failing API keys |
| `Disk Free GB` | Number | Number format, 2 decimals |
| `RAM Used %` | Number | Percent format |
| `Tokens Used` | Number | Total tokens consumed this period |
| `Incidents` | Rich Text | Summary of period's incidents |
| `Remediations` | Rich Text | Actions taken (manual or suggested) |
| `Recommendations` | Rich Text | Suggested improvements |
| `WoW Change` | Number | Signed ops score delta |
| `Trend` | Select | Options: `Healthy` (green), `Degraded` (yellow), `Critical` (red) |

**Views**:
- **Timeline** (Default Table): Sorted by Date descending
- **Incidents Only** (Table): Filtered where `Incidents` is not empty

### 2. Install Dependencies

```bash
pip install pyyaml
```
(Most other dependencies — `json`, `urllib`, `os`, `datetime` — are stdlib.)

### 3. Register Crons

Add the following 6 crons to `~/.hermes/config.yaml` under the `ops-bot` profile:

| Cron ID | Name | Schedule | Model |
| :--- | :--- | :--- | :--- |
| `SH1` | Heartbeat Monitor | `0 */2 * * *` (every 2h) | gemini-local |
| `SH2` | Cron Auditor | `30 5 * * *` (daily 5:30 AM CT) | gemini-local |
| `SH3` | Token & API Audit | `0 5 * * *` (daily 5:00 AM CT) | gemini-local |
| `SH4` | Memory & Storage Audit | `0 5 * * 0` (Sun 5:00 AM CT) | gemini-local |
| `SH5` | Watchdog & Self-Heal | `0 1,5,9,13,17,21 * * *` (every 4h offset) | gemini-local |
| `SH6` | Weekly Ops Report | `0 18 * * 0` (Sun 6:00 PM CT) | gemini-local |

### 4. Create Structured Output Directory

Ensure `~/.hermes/cron_outputs/` exists (should already be present from other skills).

---

## Modules

### Module A: Heartbeat Monitor

**Purpose**: Continuously verify that all critical services are reachable and responsive. Alert only on state transitions to avoid notification fatigue.

**Data Sources**:
- Bridge API endpoints (port 8787 via Cloudflare tunnel)
- Local LLM endpoints (localhost:8081, localhost:8082)
- Notion API
- Telegram Bot API
- n8n gateway (192.168.1.143:5678)

**Algorithm**:

```python
def heartbeat_monitor():
    """SH1: Every 2 hours. Check all critical service endpoints."""
    
    # Load previous state from ~/.hermes/cron_outputs/heartbeat_state.json
    prev_state = load_json("~/.hermes/cron_outputs/heartbeat_state.json", default={})
    
    services = {
        "bridge": {
            "url": "http://localhost:8787/health",
            "method": "GET",
            "timeout": 10,
            "critical": True
        },
        "gemini-local": {
            "url": "http://localhost:8081/health",
            "method": "GET",
            "timeout": 5,
            "critical": True
        },
        "llama-local": {
            "url": "http://localhost:8082/health",
            "method": "GET",
            "timeout": 5,
            "critical": True
        },
        "notion": {
            "url": "https://api.notion.com/v1/users/me",
            "method": "GET",
            "headers": {"Authorization": "Bearer $NOTION_API_KEY", "Notion-Version": "2022-06-28"},
            "timeout": 10,
            "critical": True
        },
        "telegram": {
            "url": "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getMe",
            "method": "GET",
            "timeout": 10,
            "critical": True
        },
        "n8n": {
            "url": "http://192.168.1.143:5678/healthz",
            "method": "GET",
            "timeout": 5,
            "critical": False  # External to VM, may be unreachable
        }
    }
    
    current_state = {}
    incidents = []
    
    for name, config in services.items():
        try:
            response = http_get_or_post(config["url"], timeout=config["timeout"])
            current_state[name] = "healthy"
        except (ConnectionError, Timeout, HTTPError) as e:
            current_state[name] = "down"
            # Check for state transition
            if prev_state.get(name) != "down":
                incidents.append({
                    "service": name,
                    "transition": f"healthy → down",
                    "error": str(e),
                    "critical": config["critical"],
                    "timestamp": now_iso()
                })
        
        # Check for recovery
        if prev_state.get(name) == "down" and current_state[name] == "healthy":
            incidents.append({
                "service": name,
                "transition": "down → healthy",
                "timestamp": now_iso()
            })
    
    # Save current state
    save_json("~/.hermes/cron_outputs/heartbeat_state.json", current_state)
    
    # Alert on state transitions only (not every check)
    if incidents:
        critical_incidents = [i for i in incidents if i.get("critical")]
        if critical_incidents:
            send_telegram_alert(
                "🚨 *System Health Alert*\n\n" +
                format_incidents(critical_incidents)
            )
        else:
            send_telegram_alert(
                "⚠️ *System Health Notice*\n\n" +
                format_incidents(incidents)
            )
    
    # Write to System Health DB if any state changes
    if incidents:
        write_incident_to_notion(incidents)
    
    return {
        "services": current_state,
        "incidents": len(incidents),
        "all_healthy": all(v == "healthy" for v in current_state.values())
    }
```

**Output**: `~/.hermes/cron_outputs/heartbeat_state.json` — persisted state for transition detection.

---

### Module B: Cron Auditor

**Purpose**: Cross-reference active cron definitions against the master registry, detect missed executions, errors, orphans, and ghosts. Produces a cron health scorecard.

**Data Sources**:
- Bridge API: `GET /status/crons` (active cron definitions from config.yaml)
- Bridge API: `GET /status/cron-reports` (execution history with status, tokens, duration)
- Master Registry: `resources/cron_registry.json`
- Cron Output Files: `~/.hermes/cron_outputs/*.json` (timestamp validation)

**Algorithm**:

```python
def cron_auditor():
    """SH2: Daily @ 5:30 AM CT. Audit all crons against master registry."""
    
    registry = load_json("resources/cron_registry.json")
    expected_crons = registry["crons"]
    
    # 1. Pull active cron definitions from config
    active_crons = bridge_get("/status/crons")["crons"]
    active_ids = {c.get("id") or c.get("name") for c in active_crons}
    
    # 2. Pull recent cron reports (last 48h)
    reports = bridge_get("/status/cron-reports", params={"limit": 100})["reports"]
    
    # 3. Cross-reference
    scorecard = {
        "total_expected": len([c for c in expected_crons if c["deployed"]]),
        "total_active": len(active_ids),
        "missed_last_24h": 0,
        "errored_last_24h": 0,
        "orphaned": [],  # In config but not in any skill
        "ghost": [],     # In skills but not deployed in config
        "not_deployed": [],  # Defined in skills, intentionally not deployed
        "details": []
    }
    
    for cron in expected_crons:
        cron_id = cron["id"]
        
        if not cron["deployed"]:
            scorecard["not_deployed"].append({
                "id": cron_id,
                "name": cron["name"],
                "skill": cron["skill"],
                "reason": cron.get("not_deployed_reason", "Unknown")
            })
            continue
        
        # Check if cron exists in active config
        if cron_id not in active_ids:
            scorecard["ghost"].append(cron_id)
        
        # Check output file freshness (if cron writes one)
        if cron.get("output_file"):
            file_age = get_file_age_hours(cron["output_file"])
            expected_interval = parse_interval_hours(cron["schedule"])
            if file_age and file_age > expected_interval * 2:
                scorecard["missed_last_24h"] += 1
                scorecard["details"].append({
                    "cron_id": cron_id,
                    "issue": "stale_output",
                    "file": cron["output_file"],
                    "age_hours": file_age,
                    "expected_interval_hours": expected_interval
                })
        
        # Check recent reports for errors
        cron_reports = [r for r in reports if r.get("cron_id") == cron_id]
        error_reports = [r for r in cron_reports if r.get("status") == "error"]
        if error_reports:
            scorecard["errored_last_24h"] += len(error_reports)
            scorecard["details"].append({
                "cron_id": cron_id,
                "issue": "execution_error",
                "error_count": len(error_reports),
                "latest_error": error_reports[0].get("output_summary", "No details")
            })
    
    # 4. Detect orphaned crons (in config but not in any skill's registry)
    registered_ids = {c["id"] for c in expected_crons}
    for active_id in active_ids:
        if active_id not in registered_ids:
            scorecard["orphaned"].append(active_id)
    
    # 5. Token usage aggregation across cron reports
    token_usage = {}
    for report in reports:
        cron_id = report.get("cron_id", "unknown")
        tokens = report.get("tokens_used", 0) or 0
        if cron_id not in token_usage:
            token_usage[cron_id] = {"total_tokens": 0, "executions": 0}
        token_usage[cron_id]["total_tokens"] += tokens
        token_usage[cron_id]["executions"] += 1
    
    # Sort by total consumption descending
    top_consumers = sorted(
        token_usage.items(),
        key=lambda x: x[1]["total_tokens"],
        reverse=True
    )[:10]
    
    scorecard["token_usage"] = {
        "total_tokens_24h": sum(v["total_tokens"] for v in token_usage.values()),
        "top_consumers": [
            {"cron_id": k, **v, "avg_per_run": v["total_tokens"] // max(v["executions"], 1)}
            for k, v in top_consumers
        ]
    }
    
    # 6. Alert if issues found
    issues = scorecard["missed_last_24h"] + scorecard["errored_last_24h"] + len(scorecard["ghost"])
    if issues > 0:
        send_telegram_alert(
            "⚠️ *Cron Health Alert*\n\n"
            f"Missed: {scorecard['missed_last_24h']}\n"
            f"Errored: {scorecard['errored_last_24h']}\n"
            f"Ghost (not deployed): {len(scorecard['ghost'])}\n"
            f"Orphaned (no skill): {len(scorecard['orphaned'])}\n\n"
            f"Details:\n{format_cron_details(scorecard['details'])}"
        )
    
    return scorecard
```

**Output**: Cron health scorecard (logged, not persisted to JSON unless issues found).

---

### Module C: Token & API Key Audit

**Purpose**: Validate all API keys with minimal read-only probes. Detect expired or expiring tokens. Check for environment variable conflicts. Analyze token consumption patterns and suggest optimizations.

**Data Sources**:
- Environment variables on the VM
- `/etc/environment` (for conflict detection)
- API endpoints (read-only probes)
- Cron reports (token usage data)

**Algorithm**:

```python
def token_api_audit():
    """SH3: Daily @ 5:00 AM CT. Validate all API keys and analyze usage."""
    
    api_probes = [
        {
            "name": "Notion",
            "env_var": "NOTION_API_KEY",
            "probe_url": "https://api.notion.com/v1/users/me",
            "probe_headers": {"Notion-Version": "2022-06-28"},
            "auth_type": "bearer",
            "expected_status": 200,
            "critical": True
        },
        {
            "name": "Hevy",
            "env_var": "HEVY_API_KEY",
            "probe_url": "https://api.hevyapp.com/v1/workouts?page=1&pageSize=1",
            "auth_type": "api-key",
            "expected_status": 200,
            "critical": True
        },
        {
            "name": "Plaid",
            "env_var": "PLAID_CLIENT_ID",
            "secondary_env": "PLAID_SECRET",
            "probe_url": "https://production.plaid.com/institutions/get",
            "probe_body": {"count": 1, "offset": 0, "country_codes": ["US"]},
            "auth_type": "plaid",
            "expected_status": 200,
            "critical": True
        },
        {
            "name": "Telegram",
            "env_var": "TELEGRAM_BOT_TOKEN",
            "probe_url_template": "https://api.telegram.org/bot{token}/getMe",
            "auth_type": "url_token",
            "expected_status": 200,
            "critical": True
        },
        {
            "name": "Finnhub",
            "env_var": "FINNHUB_API_KEY",
            "probe_url": "https://finnhub.io/api/v1/quote?symbol=AAPL",
            "auth_type": "query_token",
            "expected_status": 200,
            "critical": False
        },
        {
            "name": "Alpha Vantage",
            "env_var": "ALPHA_VANTAGE_API_KEY",
            "probe_url": "https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=AAPL",
            "auth_type": "query_apikey",
            "expected_status": 200,
            "critical": False
        },
        {
            "name": "FRED",
            "env_var": "FRED_API_KEY",
            "probe_url": "https://api.stlouisfed.org/fred/series?series_id=GDP&file_type=json",
            "auth_type": "query_apikey",
            "expected_status": 200,
            "critical": False
        },
        {
            "name": "FMP",
            "env_var": "FMP_API_KEY",
            "probe_url": "https://financialmodelingprep.com/stable/profile?symbol=AAPL",
            "auth_type": "query_apikey",
            "expected_status": 200,
            "critical": False
        },
        {
            "name": "Firecrawl",
            "env_var": "FIRECRAWL_API_KEY",
            "probe_url": "https://api.firecrawl.dev/v1/crawl/status",
            "auth_type": "bearer",
            "expected_status": [200, 404],  # 404 OK (no active crawl)
            "critical": False
        },
        {
            "name": "World Monitor",
            "env_var": "WORLDMONITOR_API_KEY",
            "probe_url": "https://worldmonitor.app/api/health",
            "auth_type": "bearer",
            "expected_status": 200,
            "critical": False,
            "optional": True  # May not be subscribed yet
        },
        {
            "name": "Etsy",
            "env_var": "ETSY_API_KEY",
            "probe_note": "OAuth 2.0 PKCE — check token file freshness",
            "token_file": "~/.hermes/secrets/etsy_tokens.json",
            "critical": False,
            "optional": True  # Pending Etsy developer account
        },
        {
            "name": "Google Calendar",
            "env_var": "GOOGLE_CALENDAR_REFRESH_TOKEN",
            "probe_note": "OAuth2 — check refresh token validity via token endpoint",
            "critical": False,
            "optional": True
        }
    ]
    
    results = {"healthy": [], "degraded": [], "missing": [], "optional_missing": []}
    
    for probe in api_probes:
        env_value = os.environ.get(probe["env_var"])
        
        if not env_value:
            if probe.get("optional"):
                results["optional_missing"].append(probe["name"])
            else:
                results["missing"].append(probe["name"])
            continue
        
        try:
            status = execute_probe(probe, env_value)
            if status in (probe["expected_status"] if isinstance(probe["expected_status"], list) 
                         else [probe["expected_status"]]):
                results["healthy"].append(probe["name"])
            else:
                results["degraded"].append({
                    "name": probe["name"],
                    "status": status,
                    "expected": probe["expected_status"]
                })
        except Exception as e:
            results["degraded"].append({
                "name": probe["name"],
                "error": str(e)
            })
    
    # Check for /etc/environment conflicts (Abacus AI hijacking protection)
    env_conflicts = check_etc_environment_conflicts([
        "FIRECRAWL_API_KEY", "FIRECRAWL_API_URL", "FIRECRAWL_BASE_URL",
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY"
    ])
    
    # Check token file freshness for OAuth-based services
    oauth_warnings = check_oauth_token_freshness([
        {"name": "Etsy", "path": "~/.hermes/secrets/etsy_tokens.json", "max_age_days": 30},
        {"name": "Plaid", "path": "~/.hermes/plaid_cursors.json", "check": "exists"}
    ])
    
    # --- Token Usage Analysis ---
    # Aggregate token data from cron reports
    reports = bridge_get("/status/cron-reports", params={"limit": 200})["reports"]
    
    usage_by_bot = {}
    usage_by_skill = {}
    usage_by_cron = {}
    
    registry = load_json("resources/cron_registry.json")
    cron_to_bot = {c["id"]: c["bot"] for c in registry["crons"]}
    cron_to_skill = {c["id"]: c["skill"] for c in registry["crons"]}
    
    for report in reports:
        tokens = report.get("tokens_used", 0) or 0
        cron_id = report.get("cron_id", "unknown")
        bot = cron_to_bot.get(cron_id, "unknown")
        skill = cron_to_skill.get(cron_id, "unknown")
        
        usage_by_bot.setdefault(bot, 0)
        usage_by_bot[bot] += tokens
        usage_by_skill.setdefault(skill, 0)
        usage_by_skill[skill] += tokens
        usage_by_cron.setdefault(cron_id, {"tokens": 0, "runs": 0})
        usage_by_cron[cron_id]["tokens"] += tokens
        usage_by_cron[cron_id]["runs"] += 1
    
    # Identify optimization opportunities
    optimizations = []
    for cron_id, data in usage_by_cron.items():
        avg = data["tokens"] // max(data["runs"], 1)
        cron_meta = next((c for c in registry["crons"] if c["id"] == cron_id), {})
        
        # Flag crons averaging >5000 tokens per run on cloud models
        if avg > 5000 and cron_meta.get("model") in ["deepseek-v4-flash", "claude-sonnet-4-6"]:
            optimizations.append({
                "cron_id": cron_id,
                "avg_tokens": avg,
                "current_model": cron_meta.get("model"),
                "suggestion": "Consider moving to gemini-local or llama-local if task complexity allows"
            })
        
        # Flag crons running more frequently than needed
        if data["runs"] > 7 and avg < 500:
            optimizations.append({
                "cron_id": cron_id,
                "avg_tokens": avg,
                "runs": data["runs"],
                "suggestion": "Low token usage per run — consider reducing frequency or batching"
            })
    
    token_analysis = {
        "total_tokens_period": sum(usage_by_bot.values()),
        "by_bot": dict(sorted(usage_by_bot.items(), key=lambda x: x[1], reverse=True)),
        "by_skill": dict(sorted(usage_by_skill.items(), key=lambda x: x[1], reverse=True)),
        "top_5_crons": sorted(
            [{"id": k, **v, "avg": v["tokens"] // max(v["runs"], 1)} 
             for k, v in usage_by_cron.items()],
            key=lambda x: x["tokens"], reverse=True
        )[:5],
        "optimizations": optimizations
    }
    
    # Alert on degraded APIs
    if results["degraded"] or results["missing"]:
        send_telegram_alert(
            "🔑 *API Key Health Report*\n\n"
            f"✅ Healthy: {len(results['healthy'])}\n"
            f"❌ Degraded: {len(results['degraded'])}\n"
            f"⛔ Missing: {len(results['missing'])}\n"
            f"ℹ️ Optional (not configured): {len(results['optional_missing'])}\n\n"
            + format_degraded_details(results["degraded"])
            + format_env_conflicts(env_conflicts)
        )
    
    if optimizations:
        send_telegram_alert(
            "💡 *Token Optimization Suggestions*\n\n"
            + format_optimizations(optimizations)
        )
    
    return {"api_results": results, "token_analysis": token_analysis}
```

**Output**: API health report + token usage analysis. No persistent JSON — alerts only.

---

### Module D: Memory & Storage Audit

**Purpose**: Monitor disk space, RAM usage, log file sizes, Notion database row counts, and Hermes memory capacity. Suggest archival and compaction strategies.

**Data Sources**:
- Bridge API: `GET /status/system` (disk, RAM)
- Bridge API: `GET /files/list` (file inventory)
- Notion API: Database queries for row counts
- `~/.hermes/cron_outputs/` (stale file detection)
- SQLite: `health_data.db` size check

**Algorithm**:

```python
def memory_storage_audit():
    """SH4: Weekly Sun @ 5:00 AM CT. Full storage and memory audit."""
    
    thresholds = load_json("resources/alert_thresholds.json")
    alerts = []
    recommendations = []
    
    # 1. System resources
    system = bridge_get("/status/system")
    
    if system["disk_free_gb"] < thresholds["disk_free_gb_min"]:
        alerts.append(f"🔴 Disk space critical: {system['disk_free_gb']} GB free (min: {thresholds['disk_free_gb_min']} GB)")
    
    if system["memory_used_pct"] > thresholds["ram_used_pct_max"]:
        alerts.append(f"🔴 RAM usage high: {system['memory_used_pct']}% (max: {thresholds['ram_used_pct_max']}%)")
    
    # 2. JSONL log file sizes
    log_files = [
        "bridge_inbox.jsonl",
        "bridge_outbox.jsonl",
        "bridge_cron_reports.jsonl",
        "hevy_webhook_events.jsonl"
    ]
    
    for log_file in log_files:
        try:
            file_info = bridge_get("/files/list", params={"path": "."})
            # Find the file in the listing and check size
            for entry in file_info["entries"]:
                if entry["name"] == log_file:
                    size_mb = entry["size"] / (1024 * 1024)
                    if size_mb > thresholds["log_file_max_mb"]:
                        alerts.append(f"⚠️ Log file oversized: {log_file} ({size_mb:.1f} MB)")
                        recommendations.append(
                            f"Rotate {log_file}: `mv {log_file} {log_file}.bak && touch {log_file}`"
                        )
        except Exception:
            pass
    
    # 3. Cron output staleness check
    cron_outputs = bridge_get("/files/list", params={"path": "cron_outputs"})
    stale_files = []
    
    expected_outputs = {
        "weekly_cost_review_latest.json": 7 * 24,     # Weekly
        "monthly_financial_latest.json": 35 * 24,      # Monthly
        "training_intel_latest.json": 7 * 24,           # Weekly
        "health_score_latest.json": 35 * 24,            # Monthly
        "ls1_latest.json": 35 * 24,                     # Monthly
        "tx2_deductions_latest.json": 35 * 24           # Monthly
    }
    
    # Compare file modification times against expected intervals
    # Flag files older than 2x their expected interval
    
    # 4. Notion database row counts
    notion_dbs_to_check = [
        {"name": "Transactions", "id": "TRANSACTIONS_DB_ID", "warn_rows": 500},
        {"name": "Workouts", "id": "WORKOUTS_DB_ID", "warn_rows": 200},
        {"name": "Lab Results", "id": "LAB_RESULTS_DB_ID", "warn_rows": 200},
        {"name": "Orders", "id": "ORDERS_DB_ID", "warn_rows": 200},
        {"name": "SEO Keywords", "id": "SEO_KEYWORDS_DB_ID", "warn_rows": 200},
        {"name": "Project Board", "id": "39563d55-66c5-81c3-827b-e124fc4bba17", "warn_rows": 100},
        {"name": "System Health", "id": "SYSTEM_HEALTH_DB_ID", "warn_rows": 200}
    ]
    
    for db in notion_dbs_to_check:
        row_count = notion_query_count(db["id"])
        if row_count > db["warn_rows"]:
            recommendations.append(
                f"📦 {db['name']} has {row_count} rows (warn: {db['warn_rows']}). "
                f"Consider archiving entries older than 6 months."
            )
    
    # 5. SQLite health_data.db size check
    try:
        db_size = get_file_size("health_data.db")
        if db_size > 50 * 1024 * 1024:  # > 50 MB
            recommendations.append(
                f"SQLite health_data.db is {db_size // (1024*1024)} MB. Run VACUUM to defragment."
            )
    except Exception:
        pass
    
    # 6. Hermes memory store usage
    # Memory limit: 2,200 chars (memory store) + 1,375 chars (user profile)
    # Check current usage against limits
    
    # 7. MEMORY.md health check (context budget guard)
    memory_md_size = get_file_size("~/abbie-config/MEMORY.md")
    memory_md_kb = memory_md_size / 1024
    if memory_md_kb > 10:
        alerts.append(f"⚠️ MEMORY.md is {memory_md_kb:.1f} KB (target: < 5 KB). Archive completed ADRs to memory/archive.md")
    elif memory_md_kb > 5:
        recommendations.append(f"📝 MEMORY.md is {memory_md_kb:.1f} KB — approaching 5 KB target. Review for stale entries.")
    
    # Count ADR entries older than 30 days
    adr_count = count_adrs_older_than_days("~/abbie-config/MEMORY.md", days=30)
    if adr_count > 0:
        recommendations.append(f"📦 {adr_count} ADR entries older than 30 days in MEMORY.md — archive to memory/archive.md")
    
    # 8. Daily log archival check
    old_daily_logs = count_files_older_than("~/abbie-config/memory/", pattern="20*.md", days=14)
    if old_daily_logs > 0:
        recommendations.append(
            f"📋 {old_daily_logs} daily logs older than 14 days — "
            f"run: bash ~/abbie-config/scripts/rotate_logs.sh"
        )
    
    # 9. Llama-server on-demand status
    llama_status = run_command("bash ~/abbie-config/scripts/llama-on-demand.sh status")
    # Include in audit report for visibility
    
    audit_result = {
        "disk_free_gb": system["disk_free_gb"],
        "ram_used_pct": system["memory_used_pct"],
        "memory_md_kb": round(memory_md_kb, 1),
        "llama_status": llama_status,
        "alerts": alerts,
        "recommendations": recommendations,
        "stale_outputs": stale_files,
        "timestamp": now_iso()
    }
    
    if alerts:
        send_telegram_alert(
            "💾 *Storage & Memory Alert*\n\n"
            + "\n".join(alerts)
            + ("\n\n💡 *Recommendations:*\n" + "\n".join(recommendations) if recommendations else "")
        )
    elif recommendations:
        # Non-urgent — include in weekly report only
        pass
    
    return audit_result
```

**Output**: Audit report. Alerts only if thresholds exceeded; recommendations deferred to weekly report.

---

### Module E: Watchdog & Self-Heal

**Purpose**: Monitor critical processes, detect stale project board items, and surface remediation options via Telegram approval buttons. **No auto-remediation** — all fixes require Jon's explicit approval.

**Data Sources**:
- `supervisord` (process status)
- Local LLM health endpoints
- Cloudflare tunnel journal
- Project Board Notion DB
- Alert thresholds config

**Algorithm**:

```python
def watchdog():
    """SH5: Every 4h (offset from SH1). Process monitoring and remediation suggestions."""
    
    thresholds = load_json("resources/alert_thresholds.json")
    issues = []
    suggested_actions = []
    
    # 1. Check supervisord processes
    expected_processes = ["hermes-gateway", "bridge-server", "bridge-tunnel"]
    
    for proc in expected_processes:
        status = run_command(f"supervisorctl status {proc}")
        if "RUNNING" not in status:
            issues.append({
                "type": "process_down",
                "process": proc,
                "status": status.strip(),
                "critical": True
            })
            suggested_actions.append({
                "description": f"Restart {proc}",
                "command": f"supervisorctl restart {proc}",
                "risk": "low",
                "requires_approval": True
            })
    
    # 2. Check local LLM responsiveness (deeper than heartbeat)
    for port, name in [(8081, "gemini-local"), (8082, "llama-local")]:
        try:
            start = time.time()
            response = http_get(f"http://localhost:{port}/health", timeout=10)
            latency = time.time() - start
            
            if latency > 5:  # > 5s response = degraded
                issues.append({
                    "type": "llm_slow",
                    "service": name,
                    "latency_s": round(latency, 2),
                    "critical": False
                })
        except Exception as e:
            issues.append({
                "type": "llm_down",
                "service": name,
                "error": str(e),
                "critical": True
            })
            suggested_actions.append({
                "description": f"Restart {name} llama-server",
                "command": f"supervisorctl restart llama-{name}",
                "risk": "medium",
                "requires_approval": True
            })
    
    # 3. Check Cloudflare tunnel URL stability
    try:
        tunnel_log = run_command("sudo journalctl -u cloudflared -n 5 --no-pager")
        # Extract current tunnel URL and compare to stored URL in MEMORY
        current_url = extract_tunnel_url(tunnel_log)
        stored_url = load_stored_tunnel_url()
        
        if current_url and stored_url and current_url != stored_url:
            issues.append({
                "type": "tunnel_url_changed",
                "old_url": stored_url,
                "new_url": current_url,
                "critical": True
            })
            suggested_actions.append({
                "description": "Update bridge config with new tunnel URL",
                "details": f"New URL: {current_url}",
                "risk": "low",
                "requires_approval": True
            })
    except Exception:
        pass
    
    # 4. Project Board hygiene
    project_board_id = "39563d55-66c5-81c3-827b-e124fc4bba17"
    
    # Check for stale "On Hold" items
    on_hold_items = notion_query(project_board_id, filter={
        "property": "Status",
        "select": {"equals": "⏸️ On Hold"}
    })
    
    stale_on_hold = [
        item for item in on_hold_items
        if days_since(item["Last Touched"]) > thresholds["project_board_stale_on_hold_days"]
    ]
    
    # Check for stale "Needs Review" items
    needs_review_items = notion_query(project_board_id, filter={
        "property": "Status",
        "select": {"equals": "👀 Needs Review"}
    })
    
    stale_review = [
        item for item in needs_review_items
        if days_since(item["Last Touched"]) > thresholds["project_board_stale_needs_review_days"]
    ]
    
    if stale_on_hold or stale_review:
        issues.append({
            "type": "board_hygiene",
            "stale_on_hold": len(stale_on_hold),
            "stale_needs_review": len(stale_review),
            "items": [
                {"title": item["Project"], "status": "On Hold", 
                 "days_stale": days_since(item["Last Touched"])}
                for item in stale_on_hold
            ] + [
                {"title": item["Project"], "status": "Needs Review",
                 "days_stale": days_since(item["Last Touched"])}
                for item in stale_review
            ]
        })
    
    # 5. Check for oversized log files needing rotation
    log_files_to_check = [
        "bridge_inbox.jsonl", "bridge_outbox.jsonl",
        "bridge_cron_reports.jsonl", "hevy_webhook_events.jsonl"
    ]
    
    for log_file in log_files_to_check:
        size_mb = get_file_size_mb(log_file)
        if size_mb and size_mb > thresholds["log_file_max_mb"]:
            suggested_actions.append({
                "description": f"Rotate {log_file} ({size_mb:.1f} MB)",
                "command": f"mv ~/.hermes/{log_file} ~/.hermes/{log_file}.bak && touch ~/.hermes/{log_file}",
                "risk": "low",
                "requires_approval": True
            })
    
    # 6. Alert with approval buttons
    if issues:
        alert_msg = "🐕 *Watchdog Report*\n\n"
        alert_msg += f"Issues found: {len(issues)}\n\n"
        
        for issue in issues:
            emoji = "🔴" if issue.get("critical") else "⚠️"
            alert_msg += f"{emoji} {issue['type']}: {format_issue(issue)}\n"
        
        if suggested_actions:
            alert_msg += "\n*Suggested Remediations:*\n"
            for i, action in enumerate(suggested_actions, 1):
                alert_msg += f"{i}. {action['description']} (Risk: {action['risk']})\n"
            alert_msg += "\nReply with the number to approve, or 'skip' to dismiss."
        
        send_telegram_alert(alert_msg)
        
        # Log incident to System Health DB
        write_incident_to_notion(issues, suggested_actions)
    
    return {
        "issues": len(issues),
        "suggested_actions": len(suggested_actions),
        "all_clear": len(issues) == 0
    }
```

**Output**: Watchdog report via Telegram with approval-gated remediation suggestions.

---

### Module F: Weekly Ops Report

**Purpose**: Aggregate all module data into a comprehensive weekly scorecard with a composite Ops Score (0–100). Deliver via Google Chat rich card and Telegram. Write structured output for Life Score consumption.

**Data Sources**:
- Heartbeat state history (Module A outputs)
- Cron audit results (Module B)
- API health results (Module C)
- Storage audit results (Module D)
- Watchdog incident log (Module E)
- `📡 System Health` DB (historical data for WoW trend)

**Algorithm**:

```python
def weekly_ops_report():
    """SH6: Sun @ 6:00 PM CT. Comprehensive weekly ops scorecard."""
    
    # 1. Compute sub-scores
    
    # Uptime Score (0-100, weight: 0.25)
    # Based on heartbeat_state.json transition log
    # Count total checks vs. successful checks over the week
    heartbeat_history = load_heartbeat_history_7d()
    total_checks = heartbeat_history["total"]
    passed_checks = heartbeat_history["passed"]
    uptime_pct = (passed_checks / max(total_checks, 1)) * 100
    uptime_score = min(100, uptime_pct)
    
    # Cron Reliability Score (0-100, weight: 0.25)
    # Based on cron reports: successful / total expected
    cron_reports_7d = get_cron_reports_7d()
    total_expected = cron_reports_7d["expected"]
    total_succeeded = cron_reports_7d["succeeded"]
    cron_score = (total_succeeded / max(total_expected, 1)) * 100
    
    # API Health Score (0-100, weight: 0.20)
    # Based on latest Module C results
    api_results = get_latest_api_audit()
    total_apis = len(api_results["healthy"]) + len(api_results["degraded"]) + len(api_results["missing"])
    healthy_apis = len(api_results["healthy"])
    api_score = (healthy_apis / max(total_apis, 1)) * 100
    
    # Resource Efficiency Score (0-100, weight: 0.15)
    # Composite of disk, RAM, log sizes
    system = bridge_get("/status/system")
    disk_score = min(100, (system["disk_free_gb"] / 10) * 100)  # 10 GB = 100%
    ram_score = max(0, 100 - system["memory_used_pct"])
    resource_score = (disk_score * 0.5 + ram_score * 0.5)
    
    # Hygiene Score (0-100, weight: 0.15)
    # Based on project board staleness, stale outputs, log rotation needs
    hygiene_deductions = 0
    stale_board_items = count_stale_board_items()
    hygiene_deductions += stale_board_items * 5  # -5 per stale item
    oversized_logs = count_oversized_logs()
    hygiene_deductions += oversized_logs * 10  # -10 per oversized log
    stale_outputs = count_stale_cron_outputs()
    hygiene_deductions += stale_outputs * 5  # -5 per stale output
    hygiene_score = max(0, 100 - hygiene_deductions)
    
    # 2. Composite Ops Score
    ops_score = round(
        uptime_score * 0.25 +
        cron_score * 0.25 +
        api_score * 0.20 +
        resource_score * 0.15 +
        hygiene_score * 0.15
    )
    
    # 3. Week-over-week trend
    prev_snapshot = get_previous_ops_snapshot()
    wow_change = ops_score - (prev_snapshot.get("ops_score", ops_score) if prev_snapshot else ops_score)
    
    if ops_score >= 90:
        trend = "Healthy"
    elif ops_score >= 70:
        trend = "Degraded"
    else:
        trend = "Critical"
    
    # 4. Top incidents this week
    incidents_7d = get_incidents_7d()
    top_incidents = incidents_7d[:3]
    
    # 5. Token usage summary
    token_summary = get_token_usage_summary_7d()
    
    # 6. Recommendations
    recommendations = []
    if cron_score < 90:
        recommendations.append("Review failed crons — check model availability and network connectivity")
    if api_score < 100:
        recommendations.append("Rotate or refresh degraded API keys")
    if resource_score < 80:
        recommendations.append("Free disk space or reduce memory usage — check for large logs")
    if hygiene_score < 80:
        recommendations.append("Address stale project board items and rotate oversized logs")
    if token_summary.get("optimizations"):
        recommendations.append(
            f"Token savings opportunity: {len(token_summary['optimizations'])} crons "
            f"could be optimized (see Module C for details)"
        )
    
    # 7. Write to Notion
    write_to_notion_system_health({
        "Date": today_iso(),
        "Ops Score": ops_score,
        "Uptime %": round(uptime_pct, 1),
        "Crons OK": total_succeeded,
        "Crons Failed": total_expected - total_succeeded,
        "APIs Healthy": healthy_apis,
        "APIs Degraded": len(api_results["degraded"]),
        "Disk Free GB": system["disk_free_gb"],
        "RAM Used %": system["memory_used_pct"],
        "Tokens Used": token_summary.get("total_tokens_period", 0),
        "Incidents": format_incidents_rich_text(top_incidents),
        "Remediations": format_remediations_rich_text(incidents_7d),
        "Recommendations": "\n".join(recommendations),
        "WoW Change": wow_change,
        "Trend": trend
    })
    
    # 8. Write structured output for Life Score
    save_json("~/.hermes/cron_outputs/ops_score_latest.json", {
        "ops_score": ops_score,
        "trend": trend,
        "wow_change": wow_change,
        "sub_scores": {
            "uptime": round(uptime_score, 1),
            "cron_reliability": round(cron_score, 1),
            "api_health": round(api_score, 1),
            "resource_efficiency": round(resource_score, 1),
            "hygiene": round(hygiene_score, 1)
        },
        "token_usage": {
            "total": token_summary.get("total_tokens_period", 0),
            "top_consumer": token_summary.get("top_5_crons", [{}])[0].get("id", "N/A"),
            "optimizations_available": len(token_summary.get("optimizations", []))
        },
        "top_incidents": [i.get("type", "unknown") for i in top_incidents],
        "recommendations": recommendations,
        "generated_at": now_iso()
    })
    
    # 9. Deliver reports
    
    # Google Chat rich card
    send_google_chat_card({
        "header": {
            "title": "📡 Weekly Ops Report",
            "subtitle": f"Ops Score: {ops_score}/100 ({trend})",
            "imageUrl": trend_icon_url(trend)
        },
        "sections": [
            {
                "header": "Sub-Scores",
                "widgets": [
                    key_value("Uptime", f"{uptime_pct:.1f}%"),
                    key_value("Cron Reliability", f"{cron_score:.0f}%"),
                    key_value("API Health", f"{api_score:.0f}%"),
                    key_value("Resources", f"{resource_score:.0f}%"),
                    key_value("Hygiene", f"{hygiene_score:.0f}%")
                ]
            },
            {
                "header": "Token Usage",
                "widgets": [
                    key_value("Total Tokens", f"{token_summary.get('total_tokens_period', 0):,}"),
                    key_value("Top Consumer", token_summary.get("top_5_crons", [{}])[0].get("id", "N/A")),
                    key_value("Optimizations", f"{len(token_summary.get('optimizations', []))} available")
                ]
            },
            {
                "header": f"WoW Change: {'+' if wow_change >= 0 else ''}{wow_change}",
                "widgets": [
                    text_paragraph("\n".join(recommendations) if recommendations else "All clear — no action needed.")
                ]
            }
        ]
    })
    
    # Telegram summary
    send_telegram_alert(
        f"📡 *Weekly Ops Score: {ops_score}/100* ({trend})\n\n"
        f"⏱ Uptime: {uptime_pct:.1f}%\n"
        f"⚙️ Crons: {total_succeeded}/{total_expected} OK\n"
        f"🔑 APIs: {healthy_apis}/{total_apis} healthy\n"
        f"💾 Disk: {system['disk_free_gb']:.1f} GB free\n"
        f"🧠 RAM: {system['memory_used_pct']:.1f}% used\n"
        f"🪙 Tokens: {token_summary.get('total_tokens_period', 0):,}\n"
        f"📈 WoW: {'+' if wow_change >= 0 else ''}{wow_change}\n"
        + (f"\n💡 *Recommendations:*\n" + "\n".join(f"• {r}" for r in recommendations) if recommendations else "")
    )
    
    return {"ops_score": ops_score, "trend": trend}
```

**Output**:
- `~/.hermes/cron_outputs/ops_score_latest.json` — structured output for Life Score
- `📡 System Health` Notion DB entry
- Google Chat rich card
- Telegram summary message

---

## Cron Automations

| Cron ID | Schedule | Model | Action | Message |
| :--- | :--- | :--- | :--- | :--- |
| `SH1` | `0 */4 * * *` (every 4h) | **bash script** | Heartbeat Monitor | Ping all services, alert on state changes (no LLM needed) |
| `SH2` | `30 5 * * *` (daily 5:30 AM CT) | gemini-local | Cron Auditor | Cross-reference crons, detect missed/errored, analyze token usage |
| `SH3` | `0 5 * * *` (daily 5:00 AM CT) | gemini-local | Token & API Audit | Probe all API keys, check env conflicts, usage analysis |
| `SH4` | `0 5 * * 0` (Sun 5:00 AM CT) | gemini-local | Memory & Storage Audit | Disk, RAM, logs, Notion sizes, SQLite, archival suggestions |
| `SH5` | `0 1,5,9,13,17,21 * * *` (every 4h) | gemini-local | Watchdog | Process monitoring, board hygiene, remediation suggestions |
| `SH6` | `0 18 * * 0` (Sun 6:00 PM CT) | gemini-local | Weekly Ops Report | Composite Ops Score, token analysis, Google Chat card + Telegram |

---

## Resource Files

| File | Purpose |
| :--- | :--- |
| `SKILL.md` | Primary instruction manual |
| `resources/cron_registry.json` | Master registry of all expected crons across all skills |
| `resources/notion_schema.json` | Schema for 📡 System Health Notion DB |
| `resources/alert_thresholds.json` | Configurable thresholds for all alert conditions |

---

## Integration

### READ/WRITE Matrix

| Database / Resource | Access | Notes |
| :--- | :--- | :--- |
| 📡 System Health DB | **READ/WRITE** | Sole owner — snapshots, incidents, remediations |
| 📋 Project Board DB (`39563d55-66c5-81c3-827b-e124fc4bba17`) | READ | Stale item detection in Module E |
| Bridge API (all `/status/*` endpoints) | READ | System metrics, cron reports, file listings |
| `~/.hermes/config.yaml` | READ | Active cron definitions |
| `~/.hermes/cron_outputs/` | READ + WRITE (`ops_score_latest.json`, `heartbeat_state.json`) | Timestamp validation + own outputs |
| `~/.hermes/bridge_cron_reports.jsonl` | READ | Cron execution history |
| `supervisord` | READ | Process status checks |
| Telegram Bot API | WRITE | Alerts and approval-gated remediation prompts |
| Google Chat Webhook | WRITE | Weekly Ops Report rich card |

### Self-Healing Policy

**Mode: Alert & Approval**. ops-bot does NOT auto-remediate. All suggested actions are delivered via Telegram with numbered options. Jon replies with the number to approve execution, or "skip" to dismiss.

---

## Data Collection Checklist

- [x] Bridge API key and URL (already in `.bridge_config.json`)
- [x] Notion API key (already in env)
- [x] Telegram Bot Token and Chat ID (already in env)
- [ ] Google Chat Webhook URL for ops reports (can reuse existing or create a new `GOOGLE_CHAT_WEBHOOK_OPS`)
- [ ] System Health Notion DB ID (created during setup)
