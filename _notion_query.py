#!/usr/bin/env python3
import json, os, sys, subprocess

API_KEY = os.environ.get("NOTION_API_KEY")
BASE = "https://api.notion.com/v1"
HEADERS = [
    "-H", f"Authorization: Bearer {API_KEY}",
    "-H", "Notion-Version: 2025-09-03",
    "-H", "Content-Type: application/json"
]

def notion_get(path):
    r = subprocess.run(["curl", "-s", f"{BASE}/{path}"] + HEADERS,
                       capture_output=True, text=True)
    return json.loads(r.stdout)

def notion_post(path, body=None):
    args = ["curl", "-s", "-X", "POST", f"{BASE}/{path}"] + HEADERS
    if body:
        args += ["-d", json.dumps(body)]
    r = subprocess.run(args, capture_output=True, text=True)
    return json.loads(r.stdout)

# Query the Ideas database by ID
db_id = sys.argv[1] if len(sys.argv) > 1 else "ff59713b-9715-470d-98f8-f957e56f3850"

# Get database info
info = notion_get(f"data_sources/{db_id}")
print("=== DATABASE INFO ===")
print(f"ID: {info.get('id','?')}")
title = ''.join(t.get('plain_text','') for t in info.get('title',[]) if isinstance(t,dict))
print(f"Title: {title}")
props = info.get('properties',{})
print(f"Properties ({len(props)}):")
for k,v in props.items():
    print(f"  - {k} ({v['type']})")

# Query all rows
print("\n=== ALL ITEMS ===")
results = []
cursor = None
while True:
    body = {"page_size": 100}
    if cursor:
        body["start_cursor"] = cursor
    data = notion_post(f"data_sources/{db_id}/query", body)
    results.extend(data.get("results", []))
    if not data.get("has_more"):
        break
    cursor = data.get("next_cursor")

print(f"Total items: {len(results)}")
for r in results:
    p = r.get("properties", {})
    # Try to get the title property
    name = ""
    title_props = [v for k,v in p.items() if v.get("type") == "title"]
    if title_props:
        title_parts = title_props[0].get("title", [])
        name = ''.join(t.get("plain_text","") for t in title_parts)
    
    # Get other interesting fields
    print(f"\n--- {r['id'][:8]}... ---")
    print(f"  Name: {name or '(no title)'}")
    for k,v in p.items():
        t = v["type"]
        val = "..."
        if t == "title":
            continue  # already shown
        elif t == "rich_text":
            val = ''.join(txt.get("plain_text","") for txt in v.get("rich_text",[]))
        elif t == "select" and v.get("select"):
            val = v["select"]["name"]
        elif t == "multi_select":
            val = ", ".join(o["name"] for o in v.get("multi_select",[]))
        elif t == "date" and v.get("date"):
            val = v["date"].get("start","")
        elif t == "checkbox":
            val = v.get("checkbox", False)
        elif t == "number":
            val = v.get("number", "")
        elif t == "url":
            val = v.get("url", "")
        elif t == "email":
            val = v.get("email", "")
        elif t == "status":
            st = v.get("status")
            val = st["name"] if st else ""
        elif t == "phone_number":
            val = v.get("phone_number", "")
        elif t == "formula":
            f = v.get("formula",{})
            val = f.get(f.get("type",""),"")
        else:
            val = f"({t})"
        if val:
            print(f"  {k}: {val[:200]}")
print("\nDone.")