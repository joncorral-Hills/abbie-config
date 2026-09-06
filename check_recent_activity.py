#!/usr/bin/env python3
"""Check alternate Lab Results DB and check for recent activity."""
import json, urllib.request, os
from datetime import datetime, timezone

notion_key = None
with open(os.path.expanduser("~/.hermes/.env")) as f:
    for line in f:
        line = line.strip()
        if line.startswith("NOTION_API_KEY="):
            notion_key = line.split("=", 1)[1]
            break

if not notion_key:
    print(json.dumps({"error": "NOTION_API_KEY not found"}))
    exit(1)

headers = {"Authorization": f"Bearer {notion_key}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

# Check alternate Lab Results DB
alt_db_id = "38163d55-66c5-8159-9ee2-f6b07fa1d25a"
print(f"=== Alternate Lab Results DB ({alt_db_id}) ===")
try:
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{alt_db_id}/query",
        data=json.dumps({"sorts": [{"property": "Date", "direction": "descending"}], "page_size": 10}).encode(),
        headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    print(f"Total: {len(data.get('results', []))}")
    for r in data.get("results", []):
        props = r.get("properties", {})
        name = ""
        if "Name" in props:
            titles = props["Name"].get("title", [])
            if titles:
                name = titles[0].get("plain_text", "")
        date_val = ""
        if "Date" in props:
            d = props["Date"].get("date")
            if d:
                date_val = d.get("start", "")
        source = ""
        if "Source" in props:
            s = props["Source"].get("select")
            if s:
                source = s.get("name", "")
        print(f"  '{name}' | Date: {date_val} | Source: {source}")
        # Show all properties
        for pname, pdef in props.items():
            if pname in ["Name", "Date", "Source"]:
                continue
            ptype = pdef.get("type", "")
            val = None
            if ptype == "number":
                val = pdef.get("number")
            elif ptype == "rich_text":
                rt = pdef.get("rich_text", [])
                if rt:
                    val = rt[0].get("plain_text", "")
            elif ptype == "select":
                sl = pdef.get("select")
                if sl:
                    val = sl.get("name", "")
            if val is not None:
                print(f"    {pname}: {val}")
except Exception as e:
    print(f"Error: {e}")

# Check created_time of latest entry in main Lab Results DB
print("\n=== Check latest entry timing in main Lab Results DB ===")
main_db_id = "36d63d55-66c5-81eb-93d8-e13f83f0d152"
try:
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{main_db_id}/query",
        data=json.dumps({"sorts": [{"timestamp": "created_time", "direction": "descending"}], "page_size": 3}).encode(),
        headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    for r in data.get("results", []):
        props = r.get("properties", {})
        name = ""
        if "Name" in props:
            titles = props["Name"].get("title", [])
            if titles:
                name = titles[0].get("plain_text", "")
        created = r.get("created_time", "?")
        last_edited = r.get("last_edited_time", "?")
        print(f"  '{name}' | Created: {created} | Last edited: {last_edited}")
except Exception as e:
    print(f"Error: {e}")

# Also check today's date from system
now = datetime.now(timezone.utc)
print(f"\nSystem time: {now}")