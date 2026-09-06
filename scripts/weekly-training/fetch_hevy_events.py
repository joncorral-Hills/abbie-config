#!/usr/bin/env python3
"""Fetch workout events from Hevy API since Aug 1 using correct UTC epoch."""
import json, urllib.request, time
from datetime import datetime, timezone

with open("/home/ubuntu/.hermes/.env") as f:
    env = {}
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v

hevy_key = env.get("HEVY_API_KEY", "")

# Use UTC epoch seconds
since_epoch = int(datetime(2026, 8, 1, tzinfo=timezone.utc).timestamp())

def fetch_events(since_ts):
    all_events = []
    page = 1
    while True:
        url = f"https://api.hevyapp.com/v1/workouts/events?since={since_ts}&page={page}"
        req = urllib.request.Request(url, headers={"api-key": hevy_key})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            body = e.read().decode() if hasattr(e, 'read') else ''
            print(f"Error on page {page}: {e} | {body[:200]}")
            break
        
        events = data.get("events", [])
        all_events.extend(events)
        pc = data.get("page_count", 1)
        print(f"Page {page}/{pc}: {len(events)} events")
        if page >= pc:
            break
        page += 1
    return all_events

print("=== FETCHING HEVY EVENTS SINCE 2026-08-01 ===")
events = fetch_events(since_epoch)
print(f"\nTotal events: {len(events)}")

# Organize by date
by_date = {}
for e in events:
    w = e.get("workout", {})
    start = w.get("start_time", "")[:10]
    if start:
        by_date.setdefault(start, []).append(e)

print(f"\n=== WORKOUTS BY DATE ===")
for date in sorted(by_date.keys(), reverse=True):
    for e in by_date[date]:
        w = e.get("workout", {})
        title = w.get("title", "")
        wid = w.get("id", "?")
        exercises = w.get("exercises", [])
        print(f"\n  {date}: {title} (ID: {wid[:8]})")
        for ex in exercises:
            ex_title = ex.get("title", "") or ex.get("exercise_template_id", "")
            sets_data = ex.get("sets", [])
            print(f"    {ex_title}: {len(sets_data)} sets")
            for s in sets_data:
                st = s.get("set_type", "")
                wk = s.get("weight_kg")
                r = s.get("reps")
                if wk and r:
                    wl = wk * 2.20462
                    print(f"      {st}: {wk:.0f}kg × {r} = {wl:.0f}lbs ({wl*r:.0f} vol)")

# Get exercise templates for muscle mapping
print("\n\n=== EXERCISE TEMPLATES (first page) ===")
req2 = urllib.request.Request(
    "https://api.hevyapp.com/v1/exercise_templates?page=1&pageSize=5",
    headers={"api-key": hevy_key}
)
with urllib.request.urlopen(req2, timeout=15) as resp:
    templates = json.loads(resp.read().decode())

for t in templates.get("exercise_templates", []):
    print(f"  {t.get('id','')}: {t.get('title','')} — {t.get('primary_muscle_group','')} / {t.get('secondary_muscle_groups',[])}")