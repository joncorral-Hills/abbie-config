#!/usr/bin/env python3
"""Debug date filtering and get all recent Hevy data."""
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

# Server time
server_now = datetime.now(timezone.utc)
print(f"Server UTC time: {server_now}")
print(f"Today (server): {server_now.strftime('%Y-%m-%d')}")

# Try 30 days back to catch all recent data
thirty_days_ago = (server_now - timedelta(days=30)).strftime("%Y-%m-%d")
print(f"30 days ago: {thirty_days_ago}")

db_id = "36d63d55-66c5-81ac-9ff4-d10a6509b452"

# Try filter with 30-day window
payload = {
    "sorts": [{"property": "Date", "direction": "descending"}],
    "filter": {"property": "Date", "date": {"on_or_after": thirty_days_ago}},
    "page_size": 20
}
data = json.dumps(payload).encode()
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{db_id}/query",
    data=data, headers=headers, method="POST"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read().decode())

print(f"\nWorkouts last 30 days: {len(result.get('results', []))}")

# Try getting ALL workouts unfiltered with a page_size limit to understand data
# Check what the actual Date values look like in raw form
req2 = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{db_id}/query",
    data=json.dumps({"sorts": [{"property": "Date", "direction": "descending"}], "page_size": 10}).encode(),
    headers=headers, method="POST"
)
with urllib.request.urlopen(req2, timeout=15) as resp:
    raw = json.loads(resp.read().decode())

print("\n=== RAW DATE VALUES ===")
for r in raw.get("results", [10]):
    p = r.get("properties", {}).get("Date", {})
    print(f"  Raw Date field: {json.dumps(p, indent=2)}")
    break  # Just show one

print("\n=== ALL WORKOUTS IN LAST 30 DAYS ===")
for r in result.get("results", []):
    p = r.get("properties", {})
    name = "".join(t.get("plain_text", "") for t in p.get("Name", {}).get("title", []))
    date_val = ""
    d = p.get("Date", {}).get("date")
    if d: date_val = d.get("start", "")
    focus = [s.get("name","") for s in p.get("Focus", {}).get("multi_select", [])]
    volume = p.get("Volume (lbs)", {}).get("number", 0)
    exercises = p.get("Exercises", {}).get("number", 0)
    sets = p.get("Sets", {}).get("number", 0)
    duration = p.get("Duration (min)", {}).get("number", 0)
    print(f"  {name} | {date_val} | Focus: {focus} | Vol: {volume}lbs | Ex: {exercises} | Sets: {sets} | Dur: {duration}min")

print("\n=== NOTES FROM RECENT WORKOUTS ===")
for r in result.get("results", []):
    p = r.get("properties", {})
    name = "".join(t.get("plain_text", "") for t in p.get("Name", {}).get("title", []))
    date_val = ""
    d = p.get("Date", {}).get("date")
    if d: date_val = d.get("start", "")
    notes = "".join(t.get("plain_text", "") for t in p.get("Notes", {}).get("rich_text", []))
    print(f"\n--- {name} | {date_val} ---")
    print(f"  Notes: {notes[:500]}")