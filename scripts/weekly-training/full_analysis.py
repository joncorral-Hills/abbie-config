#!/usr/bin/env python3
"""Query 4 weeks of workout data and PRs database."""
import json, urllib.request
from datetime import datetime, timezone, timedelta

with open("/home/ubuntu/.hermes/.env") as f:
    for line in f:
        if line.startswith("NOTION_API_KEY="):
            notion_key = line.strip().split("=", 1)[1]
            break

headers = {
    "Authorization": f"Bearer {notion_key}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

server_now = datetime.now(timezone.utc)
# "This week" = last 7 days (Aug 17-23 for Sunday cron)
this_week_start = (server_now - timedelta(days=7)).strftime("%Y-%m-%d")  # Aug 17
four_weeks_ago = (server_now - timedelta(days=28)).strftime("%Y-%m-%d")  # Jul 27

# Get all workouts in last 4 weeks
db_id_workouts = "36d63d55-66c5-81ac-9ff4-d10a6509b452"
all_results = []
next_cursor = None
while True:
    payload = {
        "sorts": [{"property": "Date", "direction": "descending"}],
        "filter": {"property": "Date", "date": {"on_or_after": four_weeks_ago}},
        "page_size": 100
    }
    if next_cursor:
        payload["start_cursor"] = next_cursor
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{db_id_workouts}/query",
        data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
    all_results.extend(result.get("results", []))
    if result.get("has_more") and result.get("next_cursor"):
        next_cursor = result["next_cursor"]
    else:
        break

print(f"=== WORKOUTS IN LAST 28 DAYS ({four_weeks_ago} to now) === ")
print(f"Total workouts: {len(all_results)}")

# Organize by week
this_week = []  # Aug 17-23
prev_week_1 = []  # Aug 10-16
prev_week_2 = []  # Aug 3-9
prev_week_3 = []  # Jul 27 - Aug 2

for r in all_results:
    p = r.get("properties", {})
    name = "".join(t.get("plain_text", "") for t in p.get("Name", {}).get("title", []))
    d = p.get("Date", {}).get("date")
    date_str = d.get("start", "") if d else ""
    volume = p.get("Volume (lbs)", {}).get("number", 0) or 0
    focus = [s.get("name","") for s in p.get("Focus", {}).get("multi_select", [])]
    exercises = p.get("Exercises", {}).get("number", 0) or 0
    sets = p.get("Sets", {}).get("number", 0) or 0
    duration = p.get("Duration (min)", {}).get("number", 0) or 0

    entry = {"name": name, "date": date_str, "volume": volume, "focus": focus, 
             "exercises": exercises, "sets": sets, "duration": duration, "page_id": r.get("id")}
    
    # Week classification
    if date_str >= "2026-08-17":
        this_week.append(entry)
    elif date_str >= "2026-08-10":
        prev_week_1.append(entry)
    elif date_str >= "2026-08-03":
        prev_week_2.append(entry)
    else:
        prev_week_3.append(entry)

print(f"\nThis Week (Aug 17-23): {len(this_week)} workouts")
for w in this_week:
    print(f"  {w['name']} | {w['date']} | Vol: {w['volume']}lbs | Focus: {w['focus']}")

print(f"\nWeek -1 (Aug 10-16): {len(prev_week_1)} workouts")
for w in prev_week_1:
    print(f"  {w['name']} | {w['date']} | Vol: {w['volume']}lbs | Focus: {w['focus']}")

print(f"\nWeek -2 (Aug 3-9): {len(prev_week_2)} workouts")
for w in prev_week_2:
    print(f"  {w['name']} | {w['date']} | Vol: {w['volume']}lbs | Focus: {w['focus']}")

print(f"\nWeek -3 (Jul 27-Aug 2): {len(prev_week_3)} workouts")
for w in prev_week_3:
    print(f"  {w['name']} | {w['date']} | Vol: {w['volume']}lbs | Focus: {w['focus']}")

# Volume by week
vol_this_week = sum(w['volume'] for w in this_week)
vol_w1 = sum(w['volume'] for w in prev_week_1)
vol_w2 = sum(w['volume'] for w in prev_week_2)
vol_w3 = sum(w['volume'] for w in prev_week_3)
vol_4wk_avg = (vol_w1 + vol_w2 + vol_w3) / 3 if (vol_w1 + vol_w2 + vol_w3) > 0 else 0

print(f"\n=== VOLUME SUMMARY ===")
print(f"This Week: {vol_this_week} lbs")
print(f"Week -1 (Aug 10-16): {vol_w1} lbs")
print(f"Week -2 (Aug 3-9): {vol_w2} lbs")
print(f"Week -3 (Jul 27-Aug 2): {vol_w3} lbs")
print(f"4-Week Rolling Avg (excl this week): {vol_4wk_avg:.0f} lbs")
if vol_4wk_avg > 0 and vol_this_week > 0:
    pct_change = ((vol_this_week - vol_4wk_avg) / vol_4wk_avg) * 100
    print(f"Change from avg: {pct_change:+.1f}%")

# Focus / muscle group analysis across weeks
all_focus_this_week = {}
for w in this_week:
    for f in w['focus']:
        all_focus_this_week[f] = all_focus_this_week.get(f, 0) + 1

print(f"\n=== MUSCLE GROUPS THIS WEEK ===")
total_sessions = len(this_week)
for muscle, count in sorted(all_focus_this_week.items()):
    print(f"  {muscle}: {count}x (target: 2x/week)")

# Query PRs database
print(f"\n\n=== PRs DATABASE ===")
pr_db_id = "36d63d55-66c5-81e0-9b88-e0461ecfe40d"

# Get schema
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{pr_db_id}",
    headers=headers, method="GET"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    pr_schema = json.loads(resp.read().decode())

print("PR Schema:")
props = pr_schema.get('properties', {})
for name, prop in props.items():
    print(f"  {name}: type={prop.get('type', '?')}")

# Query recent PRs
payload = {
    "sorts": [{"property": "Date", "direction": "descending"}],
    "page_size": 20
}
data = json.dumps(payload).encode()
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{pr_db_id}/query",
    data=data, headers=headers, method="POST"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    pr_result = json.loads(resp.read().decode())

print(f"\nRecent PRs ({len(pr_result.get('results', []))} total):")
for r in pr_result.get("results", []):
    p = r.get("properties", {})
    name = "".join(t.get("plain_text", "") for t in p.get("Name", {}).get("title", []))
    
    date_val = ""
    if "Date" in p:
        d = p["Date"].get("date")
        if d: date_val = d.get("start", "")
    
    details = []
    for pname, pval in p.items():
        if pname in ("Name", "Date"):
            continue
        ptype = pval.get("type", "?")
        if ptype == "rich_text":
            val = "".join(t.get("plain_text", "") for t in pval.get("rich_text", []))
            if val: details.append(f"{pname}={val[:100]}")
        elif ptype == "select":
            s = pval.get("select")
            if s: details.append(f"{pname}={s.get('name','')}")
        elif ptype == "multi_select":
            vals = [s.get("name","") for s in pval.get("multi_select", [])]
            if vals: details.append(f"{pname}={','.join(vals)}")
        elif ptype == "number":
            n = pval.get("number")
            if n is not None: details.append(f"{pname}={n}")
        elif ptype == "date":
            pass
        elif ptype == "formula":
            ftype = pval.get("formula", {}).get("type", "")
            val = pval.get("formula", {}).get(ftype, "")
            if val is not None: details.append(f"{pname}={val}")
    
    extra = "; ".join(details) if details else ""
    print(f"  {name} | {date_val} | {extra[:200]}")

# Also get the Notes content from the recent workouts to extract exercise details
print(f"\n\n=== EXERCISE DETAILS FROM WORKOUT NOTES ===")
for r in all_results:
    p = r.get("properties", {})
    name = "".join(t.get("plain_text", "") for t in p.get("Name", {}).get("title", []))
    d = p.get("Date", {}).get("date")
    date_str = d.get("start", "") if d else ""
    notes = "".join(t.get("plain_text", "") for t in p.get("Notes", {}).get("rich_text", []))
    
    # Notes contain Hevy IDs and exercise names like "Treadmill, Chest Press (Machine)"
    # Parse out exercises
    if notes:
        # Look for exercise names after the Hevy ID
        parts = notes.split("|")
        exercises_str = parts[-1].strip() if len(parts) > 1 else ""
        print(f"  {name} ({date_str}): {exercises_str[:300]}")