#!/usr/bin/env python3
"""Check all Lab Results DBs and query Lab Markers for reference ranges."""
import json, urllib.request, os

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

# 1. Check Jon's other Lab Results DB
print("=== Jon Northwestern Lab Results DB ===")
jon_db_id = "7811b04c-6d00-413c-a70e-17fb5b72a36c"
try:
    req = urllib.request.Request(f"https://api.notion.com/v1/databases/{jon_db_id}", headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        schema = json.loads(resp.read().decode())
        title = schema.get("title", [{}])[0].get("plain_text", "") if schema.get("title") else "(empty)"
        print(f"DB: '{title}'")
        for pname, pdef in schema.get("properties", {}).items():
            print(f"  {pname} ({pdef.get('type','?')})")
except Exception as e:
    print(f"Error: {e}")

# 2. Jaime/Joey Lab Tests DB
print("\n=== Jaime/Joey Lab Tests DB ===")
jaime_db_id = "d068a6f6-4dbf-43e9-9ea2-fccf80f14656"
try:
    req = urllib.request.Request(f"https://api.notion.com/v1/databases/{jaime_db_id}", headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        schema = json.loads(resp.read().decode())
        title = schema.get("title", [{}])[0].get("plain_text", "") if schema.get("title") else "(empty)"
        print(f"DB: '{title}'")
        for pname, pdef in schema.get("properties", {}).items():
            print(f"  {pname} ({pdef.get('type','?')})")
except Exception as e:
    print(f"Error: {e}")

# 3. Lab Markers DB - get reference ranges
print("\n=== Lab Markers DB ===")
markers_db_id = "36d63d55-66c5-81ce-931f-fad8cdd29699"
try:
    req = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{markers_db_id}/query",
        data=json.dumps({"page_size": 30}).encode(),
        headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        mdata = json.loads(resp.read().decode())
    for r in mdata.get("results", []):
        props = r.get("properties", {})
        name = ""
        if "Name" in props:
            titles = props["Name"].get("title", [])
            if titles:
                name = titles[0].get("plain_text", "")
        ref_low = props.get("Reference Low", {}).get("number")
        ref_high = props.get("Reference High", {}).get("number")
        unit = props.get("Unit", {})
        unit_val = ""
        if unit.get("type") == "rich_text":
            rt = unit.get("rich_text", [])
            if rt:
                unit_val = rt[0].get("plain_text", "")
        status = ""
        sl = props.get("Status", {}).get("select")
        if sl:
            status = sl.get("name", "")
        print(f"  {name}: {ref_low} - {ref_high} {unit_val}  [{status}]")
except Exception as e:
    print(f"Error: {e}")