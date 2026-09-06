#!/usr/bin/env python3
"""Query Lab Results DB - get full raw data for all entries."""
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

db_id = "36d63d55-66c5-81eb-93d8-e13f83f0d152"

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

for r in results:
    props = r.get("properties", {})
    name = ""
    if "Name" in props:
        titles = props["Name"].get("title", [])
        if titles:
            name = titles[0].get("plain_text", "")
    print(f"\n=== {name} (id: {r['id']}) ===")
    for pname, pdef in props.items():
        ptype = pdef.get("type", "?")
        val = "..."
        if ptype == "title":
            val = pdef.get("title", [{}])[0].get("plain_text", "") if pdef.get("title") else ""
        elif ptype == "number":
            val = pdef.get("number")
        elif ptype == "rich_text":
            rt = pdef.get("rich_text", [])
            val = rt[0].get("plain_text", "") if rt else ""
        elif ptype == "select":
            sl = pdef.get("select")
            val = sl.get("name", "") if sl else ""
        elif ptype == "multi_select":
            val = [s.get("name") for s in pdef.get("multi_select", [])]
        elif ptype == "date":
            d = pdef.get("date")
            val = d.get("start", "") if d else ""
        elif ptype == "checkbox":
            val = pdef.get("checkbox", False)
        elif ptype == "url":
            val = pdef.get("url", "")
        elif ptype == "formula":
            f = pdef.get("formula")
            val = f.get(f.get("type", ""), "") if f else ""
        elif ptype == "relation":
            rel = pdef.get("relation", [])
            val = [r.get("id", "") for r in rel]
        elif ptype == "rollup":
            rup = pdef.get("rollup", {})
            val = rup.get(rup.get("type", ""), "") if rup else ""
        else:
            val = f"({ptype})"
        print(f"  {pname} [{ptype}]: {val}")