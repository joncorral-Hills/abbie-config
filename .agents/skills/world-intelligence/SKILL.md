---
name: world-intelligence
description: Geopolitical and global intelligence layer powered by World Monitor MCP for situational analysis, risk monitoring, and market correlation.
requires:
  bins: []
  pip: ["worldmonitor-sdk"]
  env: ["WORLDMONITOR_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "NOTION_API_KEY"]
---

# 🌍 World Intelligence

## Overview

The `world-intelligence` skill serves as Allie's geopolitical and global intelligence layer. Powered by the World Monitor MCP (which provides 42+ tools for live intelligence), it continuously monitors chokepoints, cyber threats, conflict events, and country risks. It enriches Allie's existing stock and financial skills by identifying when geopolitical signals correlate with market movements, and proactively monitors the safety of travel destinations.

### Architecture

```text
                                 ┌─────────────────────────┐
                                 │ World Monitor MCP       │
                                 │ (42+ Intel Tools)       │
                                 └────────────┬────────────┘
                                              │
┌──────────────────────┐             ┌────────▼────────┐
│ Notion DB            │◄───WRITE────┤ Allie Agent     ├────READ───► Watchlist (JSON)
│ "World Intelligence" │             │ (Hermes Engine) │◄───WRITE──► Baseline (JSON)
└──────────────────────┘             └────────┬────────┘
                                              │
                                     ┌────────▼────────┐
                                     │ Telegram Alerts │
                                     │ (Primary Alert) │
                                     └─────────────────┘
```

**Dependency Chain:**
- Feeds into: `stock-weekly-briefing`, `travel-planner`, `financial-planner`
- Relies on: `World Monitor MCP`

**Relevant Notion Pages:**
- ALLIE Project Board: `39563d55-66c5-81c3-827b-e124fc4bba17`

---

## Setup (One-Time)

### 1. Configure World Monitor MCP
Add the World Monitor MCP server to `~/.hermes/config.yaml` under the `mcp_servers` section:

```yaml
mcp_servers:
  worldmonitor:
    transport: http
    url: https://worldmonitor.app/mcp
    headers:
      X-WorldMonitor-Key: ${WORLDMONITOR_API_KEY}
```

### 2. Install Dependencies
```bash
pip install worldmonitor-sdk
```

### 3. Create Notion Database
Create a new database under the ALLIE page titled **🌍 World Intelligence**. 

**Schema:**

| Property | Type | Details |
|----------|------|---------|
| Alert | Title | Brief description of the intelligence signal |
| Domain | Select | `Geopolitical`, `Maritime`, `Cyber`, `Energy`, `Climate`, `Health`, `Market`, `Conflict` |
| Severity | Select | `Critical`, `High`, `Medium`, `Low`, `Info` |
| Countries | Multi-select | ISO country names affected |
| Source Tool | Select | The WM MCP tool that produced this signal |
| Signal Date | Date | When the event/signal was detected |
| Impact Score | Number | 0-100 composite impact score |
| Action Taken | Checkbox | Whether Allie has acted on this (e.g., alerted Jon, adjusted briefing) |
| Notes | Rich Text | Detailed intelligence notes, AI analysis |

### 4. Register Cron Automations
Register `WI1`, `WI2`, `WI3`, and `WI4` within the Hermes cron registry as detailed in the automations section below.

---

## Modules

### Module A: Daily Geopolitical Pulse
**Purpose:** Delivers a concise morning Telegram digest of overnight geopolitical movements, risk shifts, and global disruptions.
**Data Sources:** `get_world_brief`, `get_country_risk`, `get_chokepoint_status`, `get_market_data`, `get_conflict_events`
**Output Format:** Telegram message with distinct emoji sections (🌍 Brief, ⚠️ Risk Movers, 🚢 Chokepoints, 📊 Fear/Greed, ⚔️ Conflicts).

**Algorithm:**
```python
def generate_daily_pulse(config, watchlist):
    # 1. Pull the AI Summary for the world
    brief = call_mcp("worldmonitor", "get_world_brief")
    
    # 2. Check risk movers on watchlist
    risk_movers = []
    for country in watchlist:
        risk = call_mcp("worldmonitor", "get_country_risk", {"country_code": country['code']})
        if risk['cii_score'] - (country['baseline_cii'] or risk['cii_score']) > config['alert_thresholds']['cii_delta_trigger']:
            risk_movers.append(f"{country['name']}: {risk['cii_score']} (+{risk['cii_score'] - country['baseline_cii']})")
    
    # 3. Check chokepoint disruption status
    chokepoints = call_mcp("worldmonitor", "get_chokepoint_status")
    disrupted = [cp for cp in chokepoints if cp['status'] == 'Disrupted']
    
    # 4. Pull Fear & Greed Index
    market_data = call_mcp("worldmonitor", "get_market_data", {"metric": "fear_and_greed"})
    f_and_g = market_data['value']
    
    # 5. Check for new conflicts
    conflicts = call_mcp("worldmonitor", "get_conflict_events", {"timeframe": "24h"})
    fatal_conflicts = [c for c in conflicts if c.get('fatalities', 0) > 0]
    
    # 6. Format Telegram Message
    msg = f"🌍 **Daily Pulse**\n{brief['summary']}\n\n"
    msg += f"⚠️ **Risk Movers**: {', '.join(risk_movers) if risk_movers else 'None'}\n"
    msg += f"🚢 **Chokepoints**: {', '.join([c['name'] for c in disrupted]) if disrupted else 'Clear'}\n"
    msg += f"📊 **Fear/Greed**: {f_and_g}\n"
    msg += f"⚔️ **Conflicts**: {len(fatal_conflicts)} new fatal events"
    
    send_telegram(msg)
```

### Module B: Country Risk Monitor
**Purpose:** Actively monitors the specific countries Jon cares about, sending targeted alerts and logging Notion entries if significant risk threshold breaches occur.
**Data Sources:** `get_country_risk`, `get_country_brief`, `get_sanctions_data`
**Output Format:** Telegram alert + Notion entry.

**Algorithm:**
```python
def monitor_country_risks(config, watchlist_path):
    watchlist = load_json(watchlist_path)
    updates_made = False
    
    for country in watchlist['watchlist']:
        risk_data = call_mcp("worldmonitor", "get_country_risk", {"country_code": country['code']})
        current_cii = risk_data['cii_score']
        baseline = country.get('baseline_cii')
        
        # Initialize baseline if None
        if baseline is None:
            country['baseline_cii'] = current_cii
            updates_made = True
            continue
            
        delta = current_cii - baseline
        
        if abs(delta) > config['alert_thresholds']['cii_delta_trigger']:
            # Major shift detected
            brief = call_mcp("worldmonitor", "get_country_brief", {"country_code": country['code']})
            sanctions = call_mcp("worldmonitor", "get_sanctions_data", {"country_code": country['code']})
            
            # Send Alert
            msg = f"🚨 **Risk Alert**: {country['name']} CII shifted by {delta} points.\n"
            msg += f"Current: {current_cii} | Baseline: {baseline}\n\n"
            msg += f"Details: {brief['summary']}"
            send_telegram(msg)
            
            # Write to Notion
            notion_write(
                database_id="<world_intel_db_id>",
                properties={
                    "Alert": f"Major Risk Shift: {country['name']}",
                    "Domain": "Geopolitical",
                    "Severity": "High" if delta > 0 else "Info",
                    "Countries": [country['name']],
                    "Source Tool": "get_country_risk",
                    "Impact Score": min(abs(delta) * 10, 100),
                    "Notes": brief['summary']
                }
            )
            
            # Update baseline
            country['baseline_cii'] = current_cii
            updates_made = True
            
    if updates_made:
        save_json(watchlist_path, watchlist)
```

### Module C: Cyber Threat Digest
**Purpose:** Delivers a weekly summary of cyber threats relevant to cloud, enterprise, and internet infrastructure.
**Data Sources:** `get_cyber_threats`, `get_infrastructure_status`
**Output Format:** Telegram message.

**Algorithm:**
```python
def generate_cyber_digest():
    threats = call_mcp("worldmonitor", "get_cyber_threats", {"timeframe": "7d"})
    infra = call_mcp("worldmonitor", "get_infrastructure_status", {"type": "internet"})
    
    # Filter CISA KEV additions and Active C2
    cisa_additions = [t for t in threats if t.get('cisa_kev_added', False)]
    c2_threats = [t for t in threats if t.get('type') == 'C2_Infrastructure']
    major_outages = [i for i in infra if i['status'] == 'Outage']
    
    msg = "🛡️ **Weekly Cyber Digest**\n\n"
    msg += f"**CISA KEV Additions**: {len(cisa_additions)}\n"
    for add in cisa_additions[:3]:
        msg += f"- {add['cve_id']}: {add['description']}\n"
        
    msg += f"\n**Active C2 Threats**: {len(c2_threats)}\n"
    msg += f"**Major Infra Outages**: {len(major_outages)}\n"
    for out in major_outages:
        msg += f"- {out['region']}: {out['details']}\n"
        
    send_telegram(msg)
```

### Module D: Situation Analysis (On-Demand)
**Purpose:** Evaluates geopolitical scenarios (e.g., "What happens if Iran blocks Hormuz?") dynamically based on real-time multi-signal analysis.
**Data Sources:** `analyze_situation`, `get_country_risk`, `get_chokepoint_status`, `get_market_data`
**Output Format:** Inline Agent Response (Text/Markdown).

**Algorithm:**
```python
def analyze_scenario(query):
    # Pass the user query directly to the WM MCP analyze_situation tool
    analysis = call_mcp("worldmonitor", "analyze_situation", {"query": query})
    
    # Supplement with live related data if entities are detected
    entities = analysis.get('entities_detected', [])
    supplemental = ""
    if 'Iran' in entities:
        risk = call_mcp("worldmonitor", "get_country_risk", {"country_code": "IR"})
        choke = call_mcp("worldmonitor", "get_chokepoint_status", {"name": "Strait of Hormuz"})
        supplemental += f"Live Context: Iran Risk {risk['cii_score']}. Hormuz Status: {choke['status']}\n"
        
    return f"**Scenario Analysis:**\n{analysis['assessment']}\n\n{supplemental}\n*Confidence: {analysis['confidence']}*"
```

### Module E: Market Correlation Engine
**Purpose:** Cross-references global intelligence with market data to identify how geopolitical disruptions impact financial assets (shipping ETFs, oil, defense stocks).
**Data Sources:** `get_market_data`, `get_chokepoint_status`, `get_energy_intelligence`, `get_conflict_events`
**Output Format:** JSON artifact consumed by `stock-weekly-briefing`.

**Algorithm:**
```python
def detect_market_correlations():
    # Gather Intelligence
    energy = call_mcp("worldmonitor", "get_energy_intelligence")
    chokepoints = call_mcp("worldmonitor", "get_chokepoint_status")
    conflicts = call_mcp("worldmonitor", "get_conflict_events", {"timeframe": "7d"})
    
    # Gather Market Response
    oil_price = call_mcp("worldmonitor", "get_market_data", {"ticker": "CL=F"}) # Crude Oil
    defense_etf = call_mcp("worldmonitor", "get_market_data", {"ticker": "ITA"})
    shipping_etf = call_mcp("worldmonitor", "get_market_data", {"ticker": "BOAT"})
    
    correlations = []
    
    disrupted_chokepoints = [c for c in chokepoints if c['status'] == 'Disrupted']
    if disrupted_chokepoints and float(shipping_etf['weekly_change']) > 2.0:
        correlations.append({
            "driver": "Chokepoint Disruption",
            "asset": "Shipping (BOAT)",
            "thesis": "Logistical bottlenecks increasing freight rates."
        })
        
    if energy['supply_risk_index'] > 70 and float(oil_price['weekly_change']) > 3.0:
        correlations.append({
            "driver": "Energy Supply Risk",
            "asset": "Crude Oil (CL=F)",
            "thesis": "High supply risk pricing into commodities."
        })
        
    save_json("artifacts/market_geopolitics_correlation.json", {"correlations": correlations})
```

### Module F: Travel Safety Check
**Purpose:** Called before trip planning to run a pre-flight safety and health check on the destination.
**Data Sources:** `get_country_risk`, `get_health_signals`, `get_climate_data`, `get_natural_disasters`
**Output Format:** Inline JSON summary injected into the travel planner's context.

**Algorithm:**
```python
def check_travel_safety(country_code):
    risk = call_mcp("worldmonitor", "get_country_risk", {"country_code": country_code})
    health = call_mcp("worldmonitor", "get_health_signals", {"country_code": country_code})
    climate = call_mcp("worldmonitor", "get_climate_data", {"country_code": country_code})
    disasters = call_mcp("worldmonitor", "get_natural_disasters", {"country_code": country_code})
    
    active_disasters = [d for d in disasters if d['status'] == 'Active']
    
    safety_summary = {
        "destination": country_code,
        "cii_risk_score": risk['cii_score'],
        "health_alerts": [h['alert'] for h in health['active_alerts']],
        "climate_anomalies": climate['anomalies'],
        "active_disasters": [d['name'] for d in active_disasters],
        "is_safe_to_travel": risk['cii_score'] < 60 and len(active_disasters) == 0
    }
    
    return safety_summary
```

---

## Cron Automations

| Code | Schedule | Model | Action | Target / Message |
|------|----------|-------|--------|------------------|
| `WI1` | Daily @ 6:30 AM CT | Gemini 3 Flash | Module A | Telegram formatting: `🌍 Brief`, `⚠️ Risk Movers`, etc. |
| `WI2` | Every 6h (6A, 12P, 6P, 12A) | Gemini 3 Flash | Module B | Silent unless threshold breached -> Telegram/Notion |
| `WI3` | Mondays @ 8:30 AM CT | Gemini 3 Flash | Module C | Weekly Cyber Threat Telegram digest |
| `WI4` | Sundays @ 5:00 PM CT | DeepSeek V4 Flash | Module E | Outputs JSON artifact for weekly stock briefing |

---

## Resource Files

| File | Purpose |
|------|---------|
| `resources/wm_config.json` | Configurations, thresholds, and module mappings for World Monitor MCP. |
| `resources/watchlist_countries.json` | Baseline intelligence metrics and country codes tracked by the risk monitor. |

---

## Integration

**READ / WRITE Map:**
- **READ**:
  - `stock-weekly-briefing`: Reads outputs from Module E to contextualize financial reports.
  - `travel-planner`: Calls Module F for automated safety context prior to itinerary planning.
  - `financial-planner`: Reads country exposure context from geopolitical snapshots.
- **WRITE**:
  - Notion Database (`🌍 World Intelligence`): Significant alerts logged for historical tracking.
  - `resources/watchlist_countries.json`: Updates baseline CII metrics for tracked countries automatically.
- **EXTERNAL**:
  - World Monitor MCP (`https://worldmonitor.app/mcp`) endpoints
  - Telegram Bot API
  - Notion API
