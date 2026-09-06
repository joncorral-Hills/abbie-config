#!/usr/bin/env python3
"""Query Workouts DB for last 7 days of data."""
import json, urllib.request
from datetime import datetime, timedelta

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

# First, inspect DB schema
db_id = "36d63d55-66c5-81ac-9ff4-d10a6509b452"
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{db_id}",
    headers=headers, method="GET"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    db_info = json.loads(resp.read().decode())

print("=== WORKOUTS DB SCHEMA ===")
props = db_info.get('properties', {})
for name, prop in props.items():
    print(f"  {name}: type={prop.get('type', '?')}")

print("\n=== RECENT WORKOUTS (last 20) ===")
payload = {
    "sorts": [{"property": "Date", "direction": "descending"}],
    "page_size": 20
}
data = json.dumps(payload).encode()
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{db_id}/query",
    data=data, headers=headers, method="POST"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    query_result = json.loads(resp.read().decode())

for r in query_result.get("results", []):
    p = r.get("properties", {})
    
    # Name
    name = ""
    if "Name" in p:
        name = "".join(t.get("plain_text", "") for t in p["Name"].get("title", []))
    
    # Date
    date_val = ""
    if "Date" in p:
        d = p["Date"].get("date")
        if d: date_val = d.get("start", "")
    
    # Maybe there's an Exercises or similar field
    # Show all non-empty properties
    details = []
    for pname, pval in p.items():
        if pname in ("Name", "Date"):
            continue
        ptype = pval.get("type", "?")
        if ptype == "rich_text":
            val = "".join(t.get("plain_text", "") for t in pval.get("rich_text", []))
            if val:
                details.append(f"{pname}={val[:80]}")
        elif ptype == "select":
            s = pval.get("select")
            if s: details.append(f"{pname}={s.get('name','')}")
        elif ptype == "multi_select":
            vals = [s.get("name","") for s in pval.get("multi_select", [])]
            if vals: details.append(f"{pname}={','.join(vals)}")
        elif ptype == "number":
            n = pval.get("number")
            if n is not None: details.append(f"{pname}={n}")
        elif ptype == "array":
            items = pval.get("array", [])
            if items:
                item_names = []
                for item in items:
                    for t in item.get("title", []):
                        item_names.append(t.get("plain_text", ""))
                if item_names:
                    details.append(f"{pname}={', '.join(item_names[:5])}")
        elif ptype == "formula":
            pass  # skip formulas
        elif ptype == "relation":
            rels = pval.get("relation", [])
            if rels: details.append(f"{pname}={len(rels)} items")
        elif ptype == "rollup":
            pass
        elif ptype == "checkbox":
            details.append(f"{pname}={pval.get('checkbox')}")
        elif ptype == "status":
            s = pval.get("status")
            if s: details.append(f"{pname}={s.get('name','')}")
    
    extra = "; ".join(details) if details else ""
    print(f"  {name} | {date_val} | {extra[:200]}")

# Now get all workouts in last 7 days for detailed analysis
print("\n\n=== DETAILED WORKOUTS LAST 7 DAYS ===")
seven_days_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

payload = {
    "sorts": [{"property": "Date", "direction": "descending"}],
    "filter": {"property": "Date", "date": {"on_or_after": seven_days_ago}},
    "page_size": 20
}
data = json.dumps(payload).encode()
req = urllib.request.Request(
    f"https://api.notion.com/v1/databases/{db_id}/query",
    data=data, headers=headers, method="POST"
)
with urllib.request.urlopen(req, timeout=15) as resp:
    recent = json.loads(resp.read().decode())

for r in recent.get("results", []):
    p = r.get("properties", {})
    name = "".join(t.get("plain_text", "") for t in p.get("Name", {}).get("title", []))
    date_val = ""
    d = p.get("Date", {}).get("date")
    if d: date_val = d.get("start", "")
    
    print(f"\n### {name} | {date_val}")
    for pname, pval in p.items():
        if pname in ("Name", "Date"):
            continue
        ptype = pval.get("type", "?")
        if ptype == "rich_text":
            val = "".join(t.get("plain_text", "") for t in pval.get("rich_text", []))
            if val: print(f"  {pname}: {val[:200]}")
        elif ptype == "select":
            s = pval.get("select")
            if s: print(f"  {pname}: {s.get('name','')}")
        elif ptype == "multi_select":
            vals = [s.get("name","") for s in pval.get("multi_select", [])]
            if vals: print(f"  {pname}: {', '.join(vals)}")
        elif ptype == "number":
            n = pval.get("number")
            if n is not None: print(f"  {pname}: {n}")
        elif ptype == "array":
            items = pval.get("array", [])
            if items:
                for item in items:
                    item_name = "".join(t.get("plain_text", "") for t in item.get("title", []))
                    item_props = {k: v for k, v in item.items() if k not in ("id", "type", "title", "object")}
                    print(f"  - {item_name} {item_props}")
        elif ptype == "checkbox":
            print(f"  {pname}: {pval.get('checkbox')}")
        elif ptype == "relation":
            rels = pval.get("relation", [])
            if rels: print(f"  {pname}: {len(rels)} links")
        elif ptype == "status":
            s = pval.get("status")
            if s: print(f"  {pname}: {s.get('name','')}")
        elif ptype == "formula":
            ftype = pval.get("formula", {}).get("type", "")
            val = pval.get("formula", {}).get(ftype, "")
            if val is not None and val != "": print(f"  {pname} (formula): {val}")
        elif ptype == "rollup":
            rtype = pval.get("rollup", {}).get("type", "")
            val = pval.get("rollup", {}).get(rtype, "")
            if val is not None and val != "": print(f"  {pname} (rollup): {val}")
        else:
            val = str(pval)[:100]
            if "None" not in val and "{}" not in val:
                print(f"  {pname} ({ptype}): {val}")
    
    # Print the raw JSON for key fields to understand structure
    print(f"  (page_id: {r.get('id', '')})")