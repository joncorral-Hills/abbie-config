#!/usr/bin/env python3
"""Query the ✈️ Trips database for upcoming trips."""
import json, urllib.request
from datetime import date

with open("/home/ubuntu/.hermes/.env") as f:
    env = {}
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v

TOKEN = env.get("NOTION_API_KEY", "")
if not TOKEN:
    print("NO_API_KEY")
    exit(1)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

TRIPS_DB = "3a863d55-66c5-811f-9985-f48cd60bd278"

# First get the schema
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{TRIPS_DB}",
    headers=headers
)
with urllib.request.urlopen(req, timeout=15) as resp:
    schema = json.loads(resp.read().decode())

print("=== SCHEMA ===")
for name, prop in schema.get("properties", {}).items():
    print(f"  {name}: type={prop.get('type')}")

# Query all trips
data = json.dumps({
    "page_size": 50,
    "sorts": [{"property": "Start Date", "direction": "ascending"}]
}).encode()

req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{TRIPS_DB}/query",
    data=data, headers=headers, method="POST"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    trips = json.loads(resp.read().decode())

today = date.today()
print(f"\n=== ALL TRIPS (sorted by date) Today: {today} ===")
upcoming = []
for t in trips.get("results", []):
    props = t.get("properties", {})
    
    # Title
    title_obj = props.get("Trip Name", props.get("Name", props.get("Title", {})))
    title = ""
    if isinstance(title_obj, dict):
        parts = title_obj.get("title", [])
        if parts and isinstance(parts[0], dict):
            title = parts[0].get("plain_text", "")
    
    # Status
    status_obj = props.get("Status", {})
    status = ""
    if isinstance(status_obj, dict) and status_obj.get("select"):
        status = status_obj["select"].get("name", "")
    
    # Destination
    dest_obj = props.get("Destination", {})
    dest = ""
    if isinstance(dest_obj, dict):
        parts = dest_obj.get("rich_text", [])
        if parts and isinstance(parts[0], dict):
            dest = parts[0].get("plain_text", "")
    
    # Dates
    start_date = ""
    end_date = ""
    date_obj = props.get("Start Date", props.get("Date", {}))
    if isinstance(date_obj, dict) and date_obj.get("date"):
        start_date = date_obj["date"].get("start", "")
        end_date = date_obj["date"].get("end", "")
    
    # Budget
    budget_obj = props.get("Budget", {})
    budget = ""
    if isinstance(budget_obj, dict) and budget_obj.get("number") is not None:
        budget = budget_obj["number"]
    
    # Notes
    notes_obj = props.get("Notes", {})
    notes = ""
    if isinstance(notes_obj, dict):
        parts = notes_obj.get("rich_text", [])
        if parts and isinstance(parts[0], dict):
            notes = parts[0].get("plain_text", "")
    
    print(f"\n  Trip: \"{title}\"")
    print(f"    Status: {status}")
    print(f"    Destination: {dest}")
    print(f"    Dates: {start_date} → {end_date}")
    print(f"    Budget: {budget}")
    print(f"    Notes: {notes}")
    
    if status in ["Planning", "Booked", "Active"]:
        upcoming.append({"title": title, "dest": dest, "start": start_date, "end": end_date, "notes": notes})

print(f"\n=== UPCOMING ({len(upcoming)}) ===")
for u in upcoming:
    print(f"  {u['title']}: {u['start']} → {u['end']} ({u['dest']})")
    print(f"    Notes: {u['notes']}")

# Also check the other "Trips" database
TRIPS_DB2 = "c70cedf2-25f6-4613-9b48-733c31d2cc6e"
try:
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{TRIPS_DB2}",
        headers=headers
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        schema2 = json.loads(resp.read().decode())
    print(f"\n=== SECOND TRIPS DB SCHEMA ===")
    for name, prop in schema2.get("properties", {}).items():
        print(f"  {name}: type={prop.get('type')}")
    
    # Query it
    data = json.dumps({"page_size": 20}).encode()
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{TRIPS_DB2}/query",
        data=data, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        trips2 = json.loads(resp.read().decode())
    print(f"\n=== TRIPS (second DB) ===")
    for t in trips2.get("results", []):
        props = t.get("properties", {})
        title_obj = props.get("Name", props.get("Title", props.get("Trip Name", {})))
        title = ""
        if isinstance(title_obj, dict):
            parts = title_obj.get("title", [])
            if parts and isinstance(parts[0], dict):
                title = parts[0].get("plain_text", "")
        print(f"  \"{title}\"")
except Exception as e:
    print(f"\nSecond DB error: {e}")

print("\nDone.")