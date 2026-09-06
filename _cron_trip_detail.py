#!/usr/bin/env python3
"""Query the second Trips DB for trip details."""
import json, urllib.request

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

TRIPS_DB2 = "c70cedf2-25f6-4613-9b48-733c31d2cc6e"

data = json.dumps({"page_size": 20}).encode()
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{TRIPS_DB2}/query",
    data=data, headers=headers, method="POST"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    trips2 = json.loads(resp.read().decode())

print("=== TRIPS (second DB - detailed) ===")
for t in trips2.get("results", []):
    props = t.get("properties", {})
    
    # Name
    name_obj = props.get("Name", {})
    name = ""
    if isinstance(name_obj, dict) and name_obj.get("title"):
        name = "".join(p.get("plain_text", "") for p in name_obj["title"])
    
    # Status
    status_obj = props.get("Status", {})
    status = ""
    if isinstance(status_obj, dict) and status_obj.get("select"):
        status = status_obj["select"].get("name", "")
    
    # Date/Dates
    date_str = ""
    for key in ["Date", "Dates"]:
        d = props.get(key, {})
        if isinstance(d, dict) and d.get("date"):
            dval = d["date"]
            start = dval.get("start", "")
            end = dval.get("end", "")
            date_str = f"{start}" + (f" → {end}" if end else "")
            break
    
    print(f"\n  \"{name}\"")
    print(f"    Status: {status}")
    print(f"    Dates: {date_str}")

print("\nDone.")