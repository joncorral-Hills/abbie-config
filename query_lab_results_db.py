#!/usr/bin/env python3
"""Check Lab Results DB for entries - sorted by date to find latest."""
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

# Lab Results DB ID
db_id = "36d63d55-66c5-81eb-93d8-e13f83f0d152"

# Query all results sorted by date descending
payload = {
    "sorts": [{"property": "Date", "direction": "descending"}],
    "page_size": 100
}
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{db_id}/query",
    data=json.dumps(payload).encode(),
    headers=headers, method="POST"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode())

results = data.get("results", [])
print(f"Total results: {len(results)}")
print(f"Has more: {data.get('has_more', False)}")

# Pretty print each lab visit
for r in results:
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
    panel = ""
    if "Panel" in props:
        pl = props["Panel"].get("select")
        if pl:
            panel = pl.get("name", "")
    
    # Marker values
    markers = {}
    for m in ["TSH", "Total Cholesterol", "LDL", "HDL", "Triglycerides", "Glucose", "Flags"]:
        if m in props:
            pdef = props[m]
            ptype = pdef.get("type", "")
            if ptype == "number":
                val = pdef.get("number")
                if val is not None:
                    markers[m] = val
            elif ptype == "rich_text":
                rt = pdef.get("rich_text", [])
                if rt:
                    markers[m] = rt[0].get("plain_text", "")
            elif ptype == "select":
                sl = pdef.get("select")
                if sl:
                    markers[m] = sl.get("name", "")
    
    print(f"\n--- {name} ---")
    print(f"  Date: {date_val}  |  Source: {source}  |  Panel: {panel}")
    for k, v in markers.items():
        print(f"  {k}: {v}")
    
    notes = props.get("Notes", {}).get("rich_text", [])
    if notes:
        print(f"  Notes: {notes[0].get('plain_text', '')[:80]}")