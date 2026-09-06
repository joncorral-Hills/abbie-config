---
name: health-automation
description: >
  Tactical health data collection and sync layer. Integrates Hevy workout API
  for automated workout/body metrics sync, Apple Health via webhook for sleep/HR/HRV,
  lab result PDF parsing and interpretation, and supplement stack management.
  Feeds data to the health-planner skill for strategic analysis.
requires:
  bins: [python3, curl]
  env: [NOTION_API_KEY, HEVY_API_KEY, HEALTH_WEBHOOK_TOKEN]
---

# Health Automation Skill

## Overview

This skill is the **tactical data collection layer** that sits below the `health-planner`
skill (which handles strategic analysis, goal setting, and composite health scoring).
Together they form a complete personal health and fitness system.

1. **Hevy Workout Sync**: Automated workout data ingestion from Hevy API → Notion
2. **Body Metrics Tracking**: Body composition measurements with unit conversion and rolling averages
3. **Apple Health Webhook Bridge**: Sleep, HR, HRV, steps, VO2 Max from iOS via Health Auto Export
4. **Lab Results Interpreter**: PDF parsing, optimal range flagging, trend analysis, and plain-English summaries
5. **Supplement Stack Manager**: Timing optimization, interaction checking, and reorder alerts
6. **PR Detection**: Automated personal record tracking with estimated 1RM calculations

**Dependency**: Requires `HEVY_API_KEY` (generate at https://hevy.com/settings?developer)

### Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                           DATA SOURCES                                     │
├────────────┬──────────────┬──────────────┬──────────────┬──────────────────┤
│  Hevy API  │ Apple Health │  Lab PDFs    │  Manual      │  Supplement      │
│  (workouts,│ (via Health  │  (pdfplumber)│  Entries     │  Inventory       │
│  body meas)│  Auto Export)│              │  (Notion)    │  (Notion)        │
└─────┬──────┴──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────────┘
      │             │              │              │              │
      ▼             ▼              ▼              ▼              ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                     health-automation (THIS SKILL)                         │
│                                                                            │
│  hevy_sync.py ─── health_webhook.py ─── lab_interpreter.py                │
│       │                  │                     │                           │
│       ▼                  ▼                     ▼                           │
│  ┌──────────────────────────────────────────────────────┐                  │
│  │              Notion Databases (6 DBs)                │                  │
│  │  Workouts │ PRs │ Body Metrics │ Medications │       │                  │
│  │  Lab Results │ Lab Markers                           │                  │
│  └──────────────────────────────────────────────────────┘                  │
└────────────────────────────────────┬───────────────────────────────────────┘
                                     │ READS ▼
                          ┌──────────┴───────────┐
                          │   health-planner      │
                          │   (strategic layer)   │
                          │   Goals, Scoring,     │
                          │   Periodization,      │
                          │   Trend Analysis      │
                          └──────────────────────┘
```

### Notion Integration

- **Health & Fitness page**: `36d63d55-66c5-8125-8c68-ee03bf91096c`
- **Existing DBs**: Workouts, PRs, Medications, Lab Results, Lab Markers
- **New DBs to create**: Body Metrics
- **Enhanced DBs**: Medications (add supplement fields), Lab Markers (add optimal ranges)

---

## Setup (One-Time)

### Step 1: Verify API Access

```bash
# Verify Hevy API key is valid
curl -s -H "api-key: $HEVY_API_KEY" https://api.hevyapp.com/v1/workouts/count
# Expected: {"workout_count": <number>}
```

### Step 2: Create New Notion Databases

Create **Body Metrics** database under the Health & Fitness page. See schema in
"Notion DB Schemas" section below.

### Step 3: Enhance Existing Databases

Add new properties to **Medications** and **Lab Markers** databases.
See "Medications DB enhancements" and "Lab Markers DB enhancements" sections.

### Step 4: Install Python Dependencies

```bash
pip install pdfplumber fastapi uvicorn httpx
```

### Step 5: Cache Exercise Templates

Run initial exercise template cache:
```bash
python3 scripts/hevy_sync.py --cache-templates
```

### Step 6: Run Initial Backfill

```bash
python3 scripts/hevy_sync.py --backfill
python3 scripts/hevy_sync.py --body-metrics --backfill
```

### Step 7: Deploy Cron Jobs

See the "Cron Jobs" section below for all 4 jobs owned by this skill.

---

## Hevy API Integration

### Authentication

All Hevy API requests use the `api-key` header (NOT `Authorization: Bearer`):

```bash
curl -H "api-key: $HEVY_API_KEY" https://api.hevyapp.com/v1/workouts/count
```

### Endpoint Reference

| Endpoint | Method | Auth | Description | Rate Notes |
|----------|--------|------|-------------|------------|
| `/v1/workouts` | GET | `api-key` header | Paginated workout list (max 10/page) | Paginate with `page` param (1-indexed) |
| `/v1/workouts/events?since=TIMESTAMP` | GET | `api-key` header | Delta sync — changed workouts since ISO 8601 timestamp | Use for ongoing sync |
| `/v1/workouts/{workoutId}` | GET | `api-key` header | Single workout details | |
| `/v1/workouts/count` | GET | `api-key` header | Total workout count | |
| `/v1/body_measurements` | GET | `api-key` header | Paginated body measurements (max 10/page) | Paginate with `page` param |
| `/v1/body_measurements/{date}` | GET | `api-key` header | Single measurement by YYYY-MM-DD | |
| `/v1/exercise_templates` | GET | `api-key` header | Exercise catalog with muscle groups (max 100/page) | Cache locally — rarely changes |
| `/v1/exercise_history/{exerciseTemplateId}` | GET | `api-key` header | Per-exercise history (optional `start_date`/`end_date` filtering) | For PR detection |
| `/v1/routines` | GET | `api-key` header | Routine templates | On-demand |

### Units

- All weights from Hevy are in **kg** → convert to **lbs** for Notion (× 2.20462)
- All measurements from Hevy are in **cm** → convert to **inches** for Notion (÷ 2.54)

### Workout Response Schema

```json
{
  "id": "workout-uuid",
  "title": "Push Day",
  "description": "Chest and triceps focus",
  "start_time": "2026-06-09T14:30:00Z",
  "end_time": "2026-06-09T15:45:00Z",
  "exercises": [
    {
      "index": 0,
      "title": "Bench Press (Barbell)",
      "notes": "Felt strong today",
      "exercise_template_id": "template-uuid",
      "supersets_id": null,
      "sets": [
        {
          "index": 0,
          "type": "warmup",
          "weight_kg": 60,
          "reps": 10,
          "distance_meters": null,
          "duration_seconds": null,
          "rpe": null,
          "custom_metric": null
        },
        {
          "index": 1,
          "type": "normal",
          "weight_kg": 100,
          "reps": 5,
          "distance_meters": null,
          "duration_seconds": null,
          "rpe": 8.5,
          "custom_metric": null
        }
      ]
    }
  ]
}
```

### Body Measurement Fields

`GET /v1/body_measurements` returns objects with:
`date`, `weight_kg`, `fat_percent`, `lean_mass_kg`, `neck_cm`, `shoulder_cm`,
`chest_cm`, `left_bicep_cm`, `right_bicep_cm`, `left_forearm_cm`, `right_forearm_cm`,
`abdomen`, `waist`, `hips`, `left_thigh`, `right_thigh`, `left_calf`, `right_calf`

### Exercise Template Fields

`GET /v1/exercise_templates` returns objects with:
`id`, `title`, `type`, `primary_muscle_group`, `secondary_muscle_groups`, `is_custom`

---

## Sync Procedures

### Initial Backfill

Run once to populate all historical data:

```python
def run_backfill():
    """Full backfill of all Hevy workout and body measurement data."""
    
    # 1. Fetch total count
    count = hevy_get("/v1/workouts/count")["workout_count"]
    
    # 2. Cache exercise templates
    cache_exercise_templates()
    
    # 3. Paginate through all workouts
    total_pages = math.ceil(count / 10)
    for page in range(1, total_pages + 1):
        workouts = hevy_get(f"/v1/workouts?page={page}")["workouts"]
        
        for workout in workouts:
            # 4. Calculate total volume per workout
            total_volume_kg = sum(
                (s["weight_kg"] or 0) * (s["reps"] or 0)
                for ex in workout["exercises"]
                for s in ex["sets"]
                if s["type"] in ("normal", "failure", "dropset")
            )
            total_volume_lbs = total_volume_kg * 2.20462
            
            # 5. Extract muscle groups from exercise templates
            muscle_groups = set()
            for ex in workout["exercises"]:
                template = get_cached_template(ex["exercise_template_id"])
                if template:
                    muscle_groups.add(template["primary_muscle_group"])
                    muscle_groups.update(template.get("secondary_muscle_groups", []))
            
            # 6. Create Notion row in Workouts DB
            create_notion_workout(workout, total_volume_lbs, muscle_groups)
            
            # 7. Detect PRs using estimated 1RM
            detect_prs(workout)
    
    # 8. Fetch all body measurements
    sync_body_measurements(backfill=True)
    
    # 9. Save sync state
    save_sync_state({
        "last_workout_sync": datetime.utcnow().isoformat() + "Z",
        "total_workouts_synced": count
    })
```

### PR Detection Algorithm

```python
def detect_prs(workout):
    """Check each exercise for new personal records using estimated 1RM."""
    workout_date = workout["start_time"]
    
    for exercise in workout["exercises"]:
        # Only check "normal" and "failure" sets (skip warmup/dropset)
        working_sets = [
            s for s in exercise["sets"]
            if s["type"] in ("normal", "failure") and s["weight_kg"] and s["reps"]
        ]
        
        if not working_sets:
            continue
        
        # Find the best set by estimated 1RM
        best_set = max(working_sets, key=lambda s: estimated_1rm(s["weight_kg"], s["reps"]))
        new_1rm_kg = estimated_1rm(best_set["weight_kg"], best_set["reps"])
        new_1rm_lbs = new_1rm_kg * 2.20462
        
        # Query PRs DB for current record
        current_pr = query_pr(exercise["title"])
        
        if current_pr is None or new_1rm_lbs > current_pr["estimated_1rm_lbs"]:
            previous_best = current_pr["estimated_1rm_lbs"] if current_pr else 0
            improvement_pct = ((new_1rm_lbs - previous_best) / previous_best * 100
                              if previous_best > 0 else 0)
            
            upsert_pr({
                "exercise": exercise["title"],
                "weight_lbs": best_set["weight_kg"] * 2.20462,
                "reps": best_set["reps"],
                "estimated_1rm_lbs": new_1rm_lbs,
                "date_set": workout_date,
                "previous_best_lbs": previous_best,
                "improvement_pct": improvement_pct
            })
            
            return True  # PR detected — flag workout
    
    return False

def estimated_1rm(weight_kg, reps):
    """Epley formula for estimated one-rep max."""
    if reps == 1:
        return weight_kg
    return weight_kg * (1 + reps / 30)
```

### Ongoing Sync (Daily Cron — H1)

```python
def run_delta_sync():
    """Delta sync: only fetch workouts changed since last sync."""
    state = load_sync_state()
    since = state["last_workout_sync"]
    
    if since is None:
        # No prior sync — run backfill instead
        return run_backfill()
    
    # 1. Fetch changed workouts
    events = hevy_get(f"/v1/workouts/events?since={since}")
    
    # 2. Process updated workouts
    for event in events.get("events", []):
        if event["type"] == "updated":
            workout = hevy_get(f"/v1/workouts/{event['workout']['id']}")
            upsert_notion_workout(workout)
            
            # Check for new PRs
            if detect_prs(workout):
                send_pr_celebration(workout)
        
        elif event["type"] == "deleted":
            archive_notion_workout(event["workout"]["id"])
    
    # 3. Update sync state
    save_sync_state({
        "last_workout_sync": datetime.utcnow().isoformat() + "Z",
        "total_workouts_synced": state["total_workouts_synced"] + len(events.get("events", []))
    })
```

### Body Metrics Sync (Weekly — H2)

```python
def sync_body_measurements(backfill=False):
    """Sync body measurements from Hevy to Body Metrics DB."""
    state = load_sync_state()
    
    if backfill:
        # Paginate through all measurements
        page = 1
        while True:
            data = hevy_get(f"/v1/body_measurements?page={page}")
            measurements = data.get("body_measurements", [])
            if not measurements:
                break
            for m in measurements:
                upsert_body_metric(m)
            page += 1
    else:
        # Fetch latest page and compare against last synced date
        data = hevy_get("/v1/body_measurements?page=1")
        measurements = data.get("body_measurements", [])
        last_synced = state.get("last_body_measurement_sync")
        
        new_measurements = [
            m for m in measurements
            if last_synced is None or m["date"] > last_synced
        ]
        
        for m in new_measurements:
            upsert_body_metric(m)
    
    # Calculate 7-day rolling weight average
    update_rolling_averages()
    
    save_sync_state({
        "last_body_measurement_sync": datetime.utcnow().strftime("%Y-%m-%d")
    })

def upsert_body_metric(measurement):
    """Convert units and upsert to Body Metrics DB."""
    m = measurement
    
    def avg_pair(left, right):
        vals = [v for v in [left, right] if v is not None]
        return sum(vals) / len(vals) if vals else None
    
    def cm_to_in(cm):
        return round(cm / 2.54, 1) if cm is not None else None
    
    def kg_to_lbs(kg):
        return round(kg * 2.20462, 1) if kg is not None else None
    
    row = {
        "Date": m["date"],
        "Weight (lbs)": kg_to_lbs(m.get("weight_kg")),
        "Body Fat %": m.get("fat_percent"),
        "Lean Mass (lbs)": kg_to_lbs(m.get("lean_mass_kg")),
        "Chest (in)": cm_to_in(m.get("chest_cm")),
        "Waist (in)": cm_to_in(m.get("waist")),
        "Shoulders (in)": cm_to_in(m.get("shoulder_cm")),
        "Bicep Avg (in)": cm_to_in(avg_pair(m.get("left_bicep_cm"), m.get("right_bicep_cm"))),
        "Abdomen (in)": cm_to_in(m.get("abdomen")),
        "Hips (in)": cm_to_in(m.get("hips")),
        "Thigh Avg (in)": cm_to_in(avg_pair(m.get("left_thigh"), m.get("right_thigh"))),
        "Calf Avg (in)": cm_to_in(avg_pair(m.get("left_calf"), m.get("right_calf")))
    }
    
    notion_upsert("Body Metrics", key="Date", row=row)
```

---

## Notion DB Schemas

### Workouts DB (existing — ensure these properties exist)

| Property | Type | Source |
|----------|------|--------|
| Title | Title | `workout.title` |
| Date | Date | `workout.start_time` |
| Duration (min) | Number | `(end_time - start_time)` in minutes |
| Muscle Groups | Multi-select | Derived from exercise templates |
| Total Volume (lbs) | Number | `Σ(weight × reps)` converted to lbs |
| Exercise Count | Number | `len(exercises)` |
| Set Count | Number | `Σ(len(sets))` across exercises |
| Exercises Detail | Rich Text | JSON of exercises + sets |
| Hevy ID | Rich Text | `workout.id` (for dedup) |
| PR Set | Checkbox | `True` if any PR was detected |

### Body Metrics DB (NEW — create under Health & Fitness page)

| Property | Type | Source |
|----------|------|--------|
| Date | Title | YYYY-MM-DD |
| Weight (lbs) | Number | `weight_kg × 2.20462` |
| Body Fat % | Number | `fat_percent` |
| Lean Mass (lbs) | Number | `lean_mass_kg × 2.20462` |
| Chest (in) | Number | `chest_cm / 2.54` |
| Waist (in) | Number | `waist / 2.54` |
| Shoulders (in) | Number | `shoulder_cm / 2.54` |
| Bicep Avg (in) | Number | `avg(left_bicep_cm, right_bicep_cm) / 2.54` |
| Abdomen (in) | Number | `abdomen / 2.54` |
| Hips (in) | Number | `hips / 2.54` |
| Thigh Avg (in) | Number | `avg(left_thigh, right_thigh) / 2.54` |
| Calf Avg (in) | Number | `avg(left_calf, right_calf) / 2.54` |
| Weight 7d Avg (lbs) | Number | Rolling 7-day average |

### PRs DB (existing — ensure these properties)

| Property | Type | Source |
|----------|------|--------|
| Exercise | Title | `exercise.title` |
| Weight (lbs) | Number | Best set weight |
| Reps | Number | Reps at best weight |
| Estimated 1RM (lbs) | Number | `weight × (1 + reps/30)` |
| Date Set | Date | Workout date |
| Previous Best (lbs) | Number | Prior 1RM before this PR |
| Improvement % | Number | `(new - old) / old × 100` |

### Medications DB Enhancements (ADD these properties to existing DB)

| New Property | Type | Purpose |
|-------------|------|--------|
| Type | Select | Options: `Medication`, `Supplement` |
| Timing | Select | `Morning` / `With Meal` / `Evening` / `Bedtime` |
| Take With | Multi-select | `Fat` / `Water` / `Empty Stomach` |
| Cycle | Rich Text | e.g., `8 weeks on / 4 weeks off` |
| Current Phase | Select | `Active` / `Off-Cycle` / `Paused` |
| Reorder Threshold (days) | Number | Days supply remaining before alert |
| Daily Dose Count | Number | How many per day |
| Supply Remaining | Number | Pills/servings remaining |
| Interactions | Rich Text | Known interactions with other supplements/medications |

### Lab Markers DB Enhancements (ADD these to existing DB)

| New Property | Type | Purpose |
|-------------|------|--------|
| Optimal Low | Number | Optimal range lower bound (functional medicine target) |
| Optimal High | Number | Optimal range upper bound (functional medicine target) |
| Priority | Select | `Critical` / `Important` / `Routine` |
| Category | Select | `Lipid Panel` / `Metabolic` / `Hormone` / `Vitamin` / `Thyroid` / `CBC` / `Liver` / `Inflammation` / `Electrolyte` / `Other` |

---

## Apple Health Webhook Bridge

### Architecture

A FastAPI application (`scripts/health_webhook.py`) runs on a VM and receives
health data from the **Health Auto Export** iOS app.

```
┌──────────────┐    POST /api/health     ┌──────────────────┐
│ Health Auto   │ ────────────────────▶  │ health_webhook.py │
│ Export (iOS)  │   Bearer <token>        │ (FastAPI on VM)   │
└──────────────┘                         └────────┬─────────┘
                                                   │
                                                   ▼
                                          ┌────────────────┐
                                          │  SQLite DB      │
                                          │  health_data.db │
                                          └────────────────┘
```

### Webhook Receiver

```python
# scripts/health_webhook.py — Core receiver logic

from fastapi import FastAPI, Header, HTTPException
import sqlite3
from datetime import datetime

app = FastAPI()
AUTH_TOKEN = os.environ["HEALTH_WEBHOOK_TOKEN"]

SUPPORTED_METRICS = [
    "Sleep Analysis",
    "Heart Rate",
    "Heart Rate Variability",
    "Resting Heart Rate",
    "Steps",
    "VO2 Max",
    "Active Energy"
]

@app.post("/api/health")
async def receive_health_data(data: dict, authorization: str = Header(...)):
    # Authenticate
    if authorization != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # Store each metric sample
    conn = sqlite3.connect("health_data.db")
    for metric in data.get("metrics", []):
        if metric["name"] not in SUPPORTED_METRICS:
            continue
        for sample in metric.get("data", []):
            conn.execute("""
                INSERT OR REPLACE INTO health_samples
                (metric_name, value, unit, source, sample_date, received_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                metric["name"],
                sample["value"],
                metric.get("unit", ""),
                sample.get("source", "Apple Health"),
                sample["date"],
                datetime.utcnow().isoformat()
            ))
    conn.commit()
    conn.close()
    return {"status": "ok", "samples_stored": len(data.get("metrics", []))}
```

### SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS health_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    source TEXT,
    sample_date TEXT NOT NULL,
    received_at TEXT NOT NULL,
    UNIQUE(metric_name, sample_date, source)
);

CREATE INDEX idx_metric_date ON health_samples(metric_name, sample_date);
```

### Health Auto Export Setup Guide (for Jon)

1. Install **Health Auto Export** from the App Store
2. Purchase Premium ($24.99 lifetime unlock)
3. Create a **REST API** automation:
   - URL: `https://<vm-endpoint>/api/health`
   - Method: `POST`
   - Header: `Authorization: Bearer <token>`
4. Select metrics:
   - Sleep Analysis
   - Heart Rate
   - Heart Rate Variability (SDNN)
   - Resting Heart Rate
   - Steps
   - VO2 Max
   - Active Energy
5. Set cadence: **every 15 minutes**
6. Enable background refresh: iOS Settings → Health Auto Export → Background App Refresh: ON
7. Verify data flow by checking `health_data.db` after 30 minutes

---

## Lab Results Interpreter

### Trigger Conditions

Activated when:
- A new Lab Results entry is created in the Notion DB
- Jon uploads a lab PDF to the Lab Results page
- Jon asks "interpret my labs" or similar

### Processing Pipeline

```python
def interpret_lab_results(source):
    """Full lab interpretation pipeline."""
    
    # 1. Parse lab values
    if source.endswith(".pdf"):
        raw_values = parse_lab_pdf(source)  # uses pdfplumber
    else:
        raw_values = query_notion_lab_results(source)  # from Notion entry
    
    # 2. Load reference ranges
    ranges = load_json("resources/lab_reference_ranges.json")
    
    # 3. Match each value against ranges
    results = []
    for marker_name, value in raw_values.items():
        ref = find_reference(ranges, marker_name)
        if ref is None:
            results.append({"marker": marker_name, "value": value, "status": "❓ No reference"})
            continue
        
        # 4. Compare against optimal and normal ranges
        status = classify_value(value, ref)
        
        # 5. Query prior Lab Results for trend
        prior = query_prior_lab_value(marker_name)
        trend = compute_trend(value, prior)
        
        results.append({
            "marker": marker_name,
            "value": value,
            "unit": ref["unit"],
            "normal_range": f"{ref['normal_low']}-{ref['normal_high']}",
            "optimal_range": f"{ref['optimal_low']}-{ref['optimal_high']}",
            "prior_value": prior,
            "trend": trend,
            "status": status
        })
    
    # 6. Generate plain-English summary
    report = generate_lab_report(results)
    
    # 7. Send via Google Chat and/or Telegram
    send_report(report)
    
    return results

def classify_value(value, ref):
    """Flag: 🟢 optimal, ⚠️ normal but outside optimal, 🔴 out of range."""
    if ref["optimal_low"] <= value <= ref["optimal_high"]:
        return "🟢"
    elif ref["normal_low"] <= value <= ref["normal_high"]:
        return "⚠️"
    else:
        return "🔴"

def compute_trend(current, prior):
    """Calculate trend: ↑ rising, → stable, ↓ falling, with % change."""
    if prior is None:
        return {"direction": "—", "pct_change": None, "label": "First reading"}
    
    pct = ((current - prior) / prior) * 100
    
    if abs(pct) < 5:
        return {"direction": "→", "pct_change": round(pct, 1), "label": "stable"}
    elif pct > 0:
        return {"direction": "↑", "pct_change": round(pct, 1), "label": f"rising {abs(round(pct))}%"}
    else:
        return {"direction": "↓", "pct_change": round(pct, 1), "label": f"falling {abs(round(pct))}%"}
```

### Lab PDF Parsing (using pdfplumber)

```python
import pdfplumber
import re

def parse_lab_pdf(pdf_path):
    """Extract lab marker/value pairs from a lab results PDF."""
    values = {}
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text is None:
                continue
            
            # Common lab report patterns:
            # "Marker Name    Value    Unit    Reference Range"
            # "Vitamin D, 25-OH    28    ng/mL    20-100"
            lines = text.split("\n")
            for line in lines:
                # Match patterns like "Marker Name  28.5  ng/mL  20-100"
                match = re.match(
                    r'^(.+?)\s+(\d+\.?\d*)\s+(\S+)\s+[\d.]+-[\d.]+',
                    line.strip()
                )
                if match:
                    marker = match.group(1).strip()
                    value = float(match.group(2))
                    values[marker] = value
    
    return values
```

### Report Format

```
🧪 Lab Results Summary — [Date]

| Marker | Value | Range | Optimal | Prior | Trend | Status |
|--------|-------|-------|---------|-------|-------|--------|
| Vitamin D | 28 ng/mL | 20-100 | 40-60 | 45 | ↓ 38% | ⚠️ |
| Total Cholesterol | 195 mg/dL | <200 | <180 | 210 | ↓ 7% | 🟢 |
| Fasting Glucose | 88 mg/dL | 65-99 | 72-86 | 82 | ↑ 7% | ⚠️ |
| Total Testosterone | 650 ng/dL | 264-916 | 500-900 | 580 | ↑ 12% | 🟢 |
| hs-CRP | 0.8 mg/L | 0-3 | 0-1 | 1.2 | ↓ 33% | 🟢 |
| Ferritin | 42 ng/mL | 30-400 | 50-150 | — | — | ⚠️ |

🎯 Top action: Vitamin D dropped below optimal (40-60). Supplement 5000 IU D3 daily with fatty meal.
📈 Improving: Total Cholesterol down 7%, hs-CRP down 33% — keep it up!
⚠️ Watch: Fasting glucose edging above optimal range. Monitor carb intake.
🆕 First reading: Ferritin at 42 — below optimal. Consider iron-rich foods or supplementation.
```

---

## Supplement Stack Manager

### Daily Schedule Generation

When queried about supplement schedule:

```python
def generate_supplement_schedule():
    """Build optimal daily supplement schedule from active supplements."""
    
    # 1. Query Medications DB filtered by Type=Supplement, Current Phase=Active
    active_supplements = query_notion(
        db="Medications",
        filter={"and": [
            {"property": "Type", "select": {"equals": "Supplement"}},
            {"property": "Current Phase", "select": {"equals": "Active"}}
        ]}
    )
    
    # 2. Load timing rules
    timing_rules = load_json("resources/supplement_timing.json")
    
    # 3. Cross-reference each supplement against timing rules
    schedule = {
        "Morning (empty stomach)": [],
        "Morning (with breakfast)": [],
        "With Lunch": [],
        "Evening (with dinner)": [],
        "Bedtime": [],
        "Any Time": []
    }
    
    for supp in active_supplements:
        rule = find_timing_rule(timing_rules, supp["name"])
        if rule:
            timing_key = map_timing_to_schedule_key(rule["timing"])
            schedule[timing_key].append({
                "name": supp["name"],
                "dose": rule["typical_dose"],
                "take_with": rule["take_with"],
                "notes": rule.get("notes", "")
            })
    
    # 4. Check for conflicts
    conflicts = check_interactions(active_supplements, timing_rules)
    
    # 5. Present as daily schedule
    return format_schedule(schedule, conflicts)

def check_interactions(supplements, timing_rules):
    """Check for timing conflicts and dangerous interactions."""
    conflicts = []
    
    for i, supp_a in enumerate(supplements):
        rule_a = find_timing_rule(timing_rules, supp_a["name"])
        if not rule_a:
            continue
        
        for supp_b in supplements[i+1:]:
            rule_b = find_timing_rule(timing_rules, supp_b["name"])
            if not rule_b:
                continue
            
            # Check if any interaction exists between these two
            for interaction in rule_a.get("interactions", []):
                if matches_supplement(interaction["with"], supp_b["name"]):
                    if interaction["type"] == "separation":
                        # Ensure they're scheduled at different times
                        if get_timing_slot(rule_a) == get_timing_slot(rule_b):
                            conflicts.append({
                                "type": "separation_needed",
                                "supplements": [supp_a["name"], supp_b["name"]],
                                "min_hours": interaction.get("min_separation_hours", 2),
                                "reason": interaction["note"]
                            })
                    elif interaction["type"] == "caution":
                        conflicts.append({
                            "type": "caution",
                            "supplements": [supp_a["name"], supp_b["name"]],
                            "reason": interaction["note"]
                        })
    
    return conflicts
```

### Schedule Report Format

```
💊 Daily Supplement Schedule

🌅 Morning (empty stomach) — 6:30 AM
  • Probiotics — 1 capsule, 30 min before food

🍳 Morning (with breakfast) — 7:30 AM
  • Vitamin D3 — 5000 IU (take with fat)
  • Vitamin K2 MK-7 — 100mcg (take with fat)
  • Omega-3 Fish Oil — 2g EPA+DHA (take with fat)
  • Vitamin B Complex — 1 capsule
  • Vitamin C — 500mg
  • L-Theanine — 200mg (with coffee)

🍽️ With Lunch — 12:30 PM
  • Berberine — 500mg

🌙 Evening (with dinner) — 6:30 PM
  • Zinc — 30mg (take with food)
  • Berberine — 500mg

😴 Bedtime — 9:30 PM
  • Magnesium Glycinate — 400mg
  • Ashwagandha — 600mg KSM-66

⏰ Any Time
  • Creatine — 5g (with water)
  • Collagen Peptides — 15g (in coffee or water, with vitamin C)

⚠️ Conflicts Detected:
  • Separate Zinc and Iron by 2+ hours (compete for DMT1 transporter)
  • Separate Magnesium and Calcium by 2+ hours (absorption competition)

🔄 Cycling Notes:
  • Ashwagandha: Week 6 of 8 — off-cycle starts in 2 weeks
```

### Reorder Alert Logic

```python
def check_reorder_alerts():
    """Check supply levels for all active supplements."""
    active = query_notion(
        db="Medications",
        filter={"and": [
            {"property": "Type", "select": {"equals": "Supplement"}},
            {"property": "Current Phase", "select": {"equals": "Active"}}
        ]}
    )
    
    alerts = []
    for supplement in active:
        supply = supplement.get("Supply Remaining", 0)
        daily_dose = supplement.get("Daily Dose Count", 1)
        threshold = supplement.get("Reorder Threshold (days)", 14)
        
        if daily_dose <= 0:
            continue
        
        days_remaining = supply / daily_dose
        
        if days_remaining <= threshold:
            alerts.append({
                "name": supplement["Title"],
                "days_remaining": round(days_remaining),
                "supply_remaining": supply,
                "daily_dose": daily_dose
            })
    
    for alert in alerts:
        send_alert(
            f"⏰ {alert['name']} has ~{alert['days_remaining']} days left "
            f"({alert['supply_remaining']} remaining at {alert['daily_dose']}/day). "
            f"Reorder soon!"
        )
    
    return alerts
```

---

## Weekly Training Summary

Run **Sunday 7:00 PM CT** (Cron H3). Pull Hevy workouts from past 7 days.

### Report Generation

```python
def generate_weekly_training_summary():
    """Generate comprehensive weekly training report from Hevy data."""
    
    # Fetch this week's workouts from Notion
    week_start = get_monday_of_current_week()
    week_end = week_start + timedelta(days=6)
    
    workouts = query_notion(
        db="Workouts",
        filter={"and": [
            {"property": "Date", "date": {"on_or_after": week_start.isoformat()}},
            {"property": "Date", "date": {"on_or_before": week_end.isoformat()}}
        ]}
    )
    
    # Calculate stats
    session_count = len(workouts)
    total_volume = sum(w["Total Volume (lbs)"] for w in workouts)
    total_duration_min = sum(w["Duration (min)"] for w in workouts)
    
    # Get last week's volume for comparison
    last_week_volume = get_last_week_volume()
    volume_change_pct = ((total_volume - last_week_volume) / last_week_volume * 100
                         if last_week_volume > 0 else 0)
    
    # Muscle group frequency
    muscle_freq = Counter()
    muscle_volume = defaultdict(float)
    for w in workouts:
        for group in w["Muscle Groups"]:
            muscle_freq[group] += 1
        # Parse exercise detail for per-group volume
        parse_volume_by_group(w, muscle_volume)
    
    # Detect PRs from this week
    prs = query_notion(
        db="PRs",
        filter={"property": "Date Set", "date": {
            "on_or_after": week_start.isoformat(),
            "on_or_before": week_end.isoformat()
        }}
    )
    
    # Check for gaps (muscle groups not hit enough)
    target_frequency = {"Legs": 2, "Back": 2, "Chest": 2, "Shoulders": 1, "Arms": 1}
    gaps = {group: target - muscle_freq.get(group, 0)
            for group, target in target_frequency.items()
            if muscle_freq.get(group, 0) < target}
    
    return format_weekly_report(
        session_count, total_volume, total_duration_min,
        volume_change_pct, muscle_freq, muscle_volume, prs, gaps
    )
```

### Report Format

```
📊 Weekly Training Summary — Week of [Mon date] to [Sun date]

Sessions: X/Y target (XX% consistency)
Total Volume: XX,XXX lbs (↑/↓ X% vs last week)
Duration: X hrs XX min total

🏆 PRs This Week:
- Bench Press: 235×5 (est. 1RM: 274 lbs) — NEW PR! ↑ 3.2%
- Squat: 315×3 (est. 1RM: 347 lbs) — NEW PR! ↑ 5.1%

💪 Muscle Groups Hit:
- Chest: 2× | Back: 2× | Legs: 1× | Shoulders: 1× | Arms: 2×

⚠️ Gaps:
- Legs only hit 1× this week (target: 2×)

📈 Volume by Group (lbs):
- Chest: 12,500 | Back: 10,200 | Legs: 8,800 | Shoulders: 4,500 | Arms: 3,200
```

---

## Cron Jobs

This skill owns 4 cron jobs.

### H1. Hevy Workout Sync

- **Schedule**: Daily 10:00 PM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Run `hevy_sync.py` for delta sync using
  `/v1/workouts/events?since=TIMESTAMP`. For each updated workout, upsert Notion
  row. For each deleted workout, archive Notion row. On PR detection, send
  celebration message via Google Chat:
  ```
  🏆 NEW PR! Bench Press — 235 lbs × 5 reps
  Est. 1RM: 274 lbs (↑ 3.2% from 265 lbs)
  Keep pushing! 💪
  ```

### H2. Body Metrics Sync

- **Schedule**: Saturday 8:00 AM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Run `hevy_sync.py --body-metrics`. Fetch latest body measurements
  from Hevy. Convert units (kg→lbs, cm→inches). Calculate 7-day rolling weight
  average. Upsert to Body Metrics DB. If weight changed >2 lbs from last week,
  note in sync log.

### H3. Weekly Training Summary

- **Schedule**: Sunday 7:00 PM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Generate weekly training summary from Hevy data in Workouts DB.
  Calculate volume, muscle group frequency, PR count, and identify training gaps.
  Send formatted report via Google Chat.

### H4. Supplement Reorder Alert

- **Schedule**: Wednesday 9:00 AM CT
- **Model**: Gemini 2.5 Flash
- **Action**: Query Medications DB for all active supplements. Calculate
  `days_remaining = Supply Remaining / Daily Dose Count`. If
  `days_remaining ≤ Reorder Threshold (days)`, send alert via Google Chat.

---

## Integration with health-planner

This skill **collects and stores** data. The `health-planner` skill (strategic
layer) **reads from** these databases for composite analysis:

| Database | Owner | health-planner Access |
|----------|-------|----------------------|
| Workouts | **health-automation** | READ — training volume, consistency, periodization |
| PRs | **health-automation** | READ — strength progression tracking |
| Body Metrics | **health-automation** | READ — body composition trends |
| Medications | **health-automation** | READ/WRITE — supplement protocol adherence |
| Lab Results | **health-automation** | READ — biomarker trends |
| Lab Markers | **health-automation** | READ — reference ranges |

### Shared Data

- **Workout data**: health-automation syncs from Hevy; health-planner analyzes for periodization and overtraining signals.
- **Body metrics**: health-automation stores raw measurements; health-planner computes body composition trends and goal progress.
- **Lab results**: health-automation parses and flags; health-planner incorporates into composite health score.
- **Apple Health data**: health-automation receives via webhook; health-planner uses sleep/HRV for recovery scoring.

---

## Files in This Skill

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — instructions and architecture |
| `scripts/hevy_sync.py` | Hevy API → Notion sync engine (workouts + body metrics) |
| `scripts/health_webhook.py` | FastAPI receiver for Health Auto Export (Apple Health data) |
| `scripts/lab_interpreter.py` | Lab PDF parser + trend analyzer + report generator |
| `resources/hevy_sync_state.json` | Sync timestamps, counters, and dedup state |
| `resources/exercise_templates.json` | Cached Hevy exercise catalog (populated on first sync) |
| `resources/supplement_timing.json` | Supplement timing rules, dosing, and interaction constraints |
| `resources/lab_reference_ranges.json` | Optimal + normal lab reference ranges (male adult) |
