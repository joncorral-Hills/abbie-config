#!/usr/bin/env python3
"""
Hevy Daily Sync — Full backfill + incremental sync.
Reads runbook steps, processes Hevy API data, upserts to Notion.
Supports silent mode (no output = nothing new).
"""
import json, urllib.request, urllib.parse, os, sys, datetime

# ── Config ──────────────────────────────────────────────────────────────
env_path = os.path.expanduser("~/.hermes/.env")
env = {}
with open(env_path) as f:
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v

HEVY_KEY = env.get("HEVY_API_KEY", "")
NOTION_KEY = env.get("NOTION_API_KEY", "")
WORKOUTS_DB = "36d63d55-66c5-81ac-9ff4-d10a6509b452"
BODY_METRICS_DB = "3b163d55-66c5-8149-9aaa-c95a9994c93a"
HEVY_BASE = "https://api.hevyapp.com"
HEVY_HEADERS = {"api-key": HEVY_KEY, "Content-Type": "application/json", "Accept": "application/json"}
NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_KEY}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}
KG_TO_LBS = 2.20462
CM_TO_IN = 2.54

def hevy_get(endpoint, params=None):
    url = f"{HEVY_BASE}{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEVY_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def notion_post(endpoint, data):
    url = f"https://api.notion.com/v1{endpoint}"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=NOTION_HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def notion_patch(endpoint, data):
    url = f"https://api.notion.com/v1{endpoint}"
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=NOTION_HEADERS, method="PATCH")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

# ── Step 1: Get existing workout dates from Notion ─────────────────────
existing_dates = set()
cursor = None
while True:
    body = {"page_size": 100}
    if cursor:
        body["start_cursor"] = cursor
    resp = notion_post(f"/databases/{WORKOUTS_DB}/query", body)
    for r in resp.get("results", []):
        date_prop = r.get("properties", {}).get("Date", {})
        if date_prop.get("date") and date_prop["date"].get("start"):
            existing_dates.add(date_prop["date"]["start"])
    if resp.get("has_more"):
        cursor = resp.get("next_cursor")
    else:
        break

# ── Step 2: Fetch all Hevy workouts ────────────────────────────────────
all_workouts = []
page = 1
page_count = 1
while page <= page_count:
    data = hevy_get("/v1/workouts", {"page": page, "pageSize": 10})
    page_count = data.get("page_count", 1)
    all_workouts.extend(data.get("workouts", []))
    page += 1

# ── Step 3: Identify new workouts ──────────────────────────────────────
new_workouts = []
for w in all_workouts:
    w_date = w.get("start_time", "")[:10]
    if w_date not in existing_dates:
        new_workouts.append(w)

# Also check by workout ID in case dates overlap
# Get all existing Hevy workout IDs from Notes
existing_hevy_ids = set()
cursor = None
while True:
    body = {"page_size": 100}
    if cursor:
        body["start_cursor"] = cursor
    resp = notion_post(f"/databases/{WORKOUTS_DB}/query", body)
    for r in resp.get("results", []):
        notes = r.get("properties", {}).get("Notes", {})
        if notes.get("rich_text"):
            for rt in notes["rich_text"]:
                txt = rt.get("text", {}).get("content", "")
                if "Workout ID:" in txt:
                    wid = txt.split("Workout ID:")[1].split("\n")[0].strip()
                    existing_hevy_ids.add(wid)
    if resp.get("has_more"):
        cursor = resp.get("next_cursor")
    else:
        break

# Filter by ID too
new_workouts = [w for w in new_workouts if w.get("id") not in existing_hevy_ids]

# If nothing new, exit silently
if not new_workouts:
    print("[SILENT]", flush=True)
    sys.exit(0)

# ── Step 4: Upsert new workouts with PR detection ──────────────────────
prs_detected = []
created_count = 0

for w in new_workouts:
    w_id = w.get("id")
    title = w.get("title", "Workout")
    start_time = w.get("start_time", "")
    end_time = w.get("end_time", "")
    w_date = start_time[:10] if start_time else ""
    
    # Duration
    duration_min = 0
    if start_time and end_time:
        try:
            st = datetime.datetime.fromisoformat(start_time.replace("Z", "+00:00") if start_time.endswith("Z") else start_time)
            et = datetime.datetime.fromisoformat(end_time.replace("Z", "+00:00") if end_time.endswith("Z") else end_time)
            duration_min = int((et - st).total_seconds() / 60)
        except:
            pass
    
    # Calculate volume, sets, exercises, and detect PRs
    total_volume_lbs = 0
    total_sets = 0
    exercise_count = 0
    exercise_details = []
    
    for ex in w.get("exercises", []):
        exercise_count += 1
        ex_title = ex.get("title", "Unknown")
        ex_sets = []
        best_1rm = 0
        best_set = None
        
        for s in ex.get("sets", []):
            total_sets += 1
            wt = s.get("weight_kg")
            reps = s.get("reps")
            stype = s.get("type", "normal")
            
            if wt and reps:
                vol_lbs = wt * KG_TO_LBS * reps
                total_volume_lbs += vol_lbs
                ex_sets.append({
                    "weight_lbs": round(wt * KG_TO_LBS, 1),
                    "reps": reps,
                    "type": stype
                })
                # PR detection (Epley formula on normal/failure sets)
                if stype in ("normal", "failure"):
                    epley_1rm = wt * KG_TO_LBS * (1 + reps / 30)
                    if epley_1rm > best_1rm:
                        best_1rm = epley_1rm
                        best_set = {"weight_lbs": round(wt * KG_TO_LBS, 1), "reps": reps}
            elif wt:
                ex_sets.append({"weight_lbs": round(wt * KG_TO_LBS, 1), "reps": reps, "type": stype})
            else:
                ex_sets.append({
                    "weight_lbs": None, "reps": reps, "type": stype,
                    "distance_m": s.get("distance_meters"),
                    "duration_s": s.get("duration_seconds")
                })
        
        if best_set and best_1rm > 0:
            prs_detected.append({
                "exercise": ex_title, "weight_lbs": best_set["weight_lbs"],
                "reps": best_set["reps"], "estimated_1rm": round(best_1rm, 1),
                "workout_date": w_date, "workout_id": w_id
            })
        
        exercise_details.append({"name": ex_title, "sets": ex_sets})
    
    # Determine focus tags
    focus_tags = []
    cardio = ["treadmill", "run", "walk", "bike", "elliptical", "rower"]
    push = ["chest press", "shoulder press", "triceps", "chest fly", "dip"]
    pull = ["row", "pulldown", "bicep curl", "lat", "seated row"]
    legs = ["leg extension", "leg curl", "squat", "lunge", "leg press", "calf"]
    core = ["crunch", "plank", "leg raise", "ab", "sit-up"]
    
    for ex in exercise_details:
        en = ex["name"].lower()
        if any(k in en for k in cardio): focus_tags.append("🫀 Cardio")
        if any(k in en for k in push): focus_tags.append("💪 Push")
        if any(k in en for k in pull): focus_tags.append("🔙 Pull")
        if any(k in en for k in legs): focus_tags.append("🦵 Legs")
        if any(k in en for k in core): focus_tags.append("🧘 Core")
    focus_tags = list(dict.fromkeys(focus_tags))
    if not focus_tags:
        focus_tags.append("🤝 Full Body")
    
    # Build Notion page
    properties = {
        "Name": {"title": [{"text": {"content": title[:2000]}}]},
        "Date": {"date": {"start": w_date}},
        "Duration (min)": {"number": duration_min},
        "Exercises": {"number": exercise_count},
        "Sets": {"number": total_sets},
        "Volume (lbs)": {"number": round(total_volume_lbs, 1)},
        "Focus": {"multi_select": [{"name": f} for f in focus_tags]},
    }
    
    notes_parts = [f"Workout ID: {w_id}"]
    for ex in exercise_details:
        sets_str = " | ".join([
            f"{s['weight_lbs']} lbs × {s['reps']} reps" if s.get('weight_lbs') and s.get('reps') else
            f"{s.get('distance_m', '?')}m in {s.get('duration_s', '?')}s" if s.get('distance_m') else
            f"bw × {s.get('reps', '?')} reps" if s.get('reps') else
            f"{s.get('weight_lbs', '?')} lbs"
            for s in ex["sets"]
        ])
        notes_parts.append(f"  {ex['name']}: {sets_str}")
    
    payload = {
        "parent": {"database_id": WORKOUTS_DB},
        "properties": properties,
        "children": [
            {"object": "block", "type": "paragraph", "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": "\n".join(notes_parts)[:1980]}}]
            }}
        ]
    }
    
    try:
        notion_post("/pages", payload)
        created_count += 1
    except Exception as e:
        print(f"  ❌ Failed to create {w_date} - {title}: {e}", flush=True)

# ── Step 5: Body Measurements ──────────────────────────────────────────
body_measurements = hevy_get("/v1/body_measurements", {"page": 1, "pageSize": 10})
new_measurements = 0
for m in body_measurements.get("body_measurements", []):
    m_date = m.get("date", "")
    weight_kg = m.get("weight_kg")
    
    # Check if this date already exists in Body Metrics
    check = notion_post(f"/databases/{BODY_METRICS_DB}/query", {
        "filter": {"property": "Date", "date": {"equals": m_date}},
        "page_size": 1
    })
    
    if check.get("results"):
        continue  # Already exists
    
    # Build properties
    props = {
        "Name": {"title": [{"text": {"content": m_date}}]},
        "Date": {"date": {"start": m_date}},
    }
    
    if weight_kg is not None:
        props["Weight (kg)"] = {"number": round(weight_kg, 2)}
        props["Weight (lbs)"] = {"number": round(weight_kg * KG_TO_LBS, 1)}
    
    # Convert cm to inches for body measurements
    for cm_field, in_field in [
        ("neck_cm", "Neck (in)"), ("shoulder_cm", "Shoulders (in)"),
        ("chest_cm", "Chest (in)"), ("left_bicep_cm", "Left Bicep (in)"),
        ("right_bicep_cm", "Right Bicep (in)"),
        ("left_forearm_cm", "Left Forearm (in)"),
        ("right_forearm_cm", "Right Forearm (in)"),
        ("waist", "Waist (in)"), ("hips", "Hips (in)"),
        ("left_thigh", "Left Thigh (in)"),
        ("right_thigh", "Right Thigh (in)"),
        ("left_calf", "Left Calf (in)"),
        ("right_calf", "Right Calf (in)"),
    ]:
        val = m.get(cm_field)
        if val is not None:
            props[in_field] = {"number": round(val / CM_TO_IN, 1)}
    
    try:
        notion_post("/pages", {"parent": {"database_id": BODY_METRICS_DB}, "properties": props})
        new_measurements += 1
    except Exception as e:
        print(f"  ❌ Failed to create body measurement {m_date}: {e}", flush=True)

# ── Step 6: Save sync state ────────────────────────────────────────────
state_dir = os.path.expanduser("~/.hermes/state")
os.makedirs(state_dir, exist_ok=True)
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
sync_state = {
    "last_workout_sync": now,
    "workouts_synced": created_count,
    "measurements_synced": new_measurements,
    "prs_found": len(prs_detected),
    "sync_type": "incremental"
}
with open(f"{state_dir}/hevy_sync_state.json", "w") as f:
    json.dump(sync_state, f, indent=2)

# ── Output ─────────────────────────────────────────────────────────────
if prs_detected:
    # Deduplicate PRs by exercise name, keep the best
    best_prs = {}
    for pr in prs_detected:
        ex = pr["exercise"]
        if ex not in best_prs or pr["estimated_1rm"] > best_prs[ex]["estimated_1rm"]:
            best_prs[ex] = pr
    
    print("🎉 New PRs Detected!")
    for ex, pr in best_prs.items():
        print(f"{pr['exercise']}: {pr['weight_lbs']} lbs × {pr['reps']} reps (Estimated 1RM: {pr['estimated_1rm']} lbs)")

print(f"\n📊 Sync Summary: {created_count} workouts, {new_measurements} measurements, {len(prs_detected)} PR candidates")