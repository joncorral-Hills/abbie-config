#!/usr/bin/env python3
"""Inspect the Lab Results and Lab Markers DBs directly."""
import json, urllib.request, os

notion_key = None
env_path = os.path.expanduser("~/.hermes/.env")
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line.startswith("NOTION_API_KEY="):
            notion_key = line.split("=", 1)[1]
            break

if not notion_key:
    print(json.dumps({"error": "NOTION_API_KEY not found"}))
    exit(1)

headers = {"Authorization": f"Bearer {notion_key}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}

# Try each candidate ID as a database
candidates = [
    "36d63d55-66c5-8125-8c68-ee03bf91096c",
    "36d63d55-66c5-8185-b156-000b9a4a54e8",
    "36d63d55-66c5-8131-bc27-000b9deba4f7",
    "38163d55-66c5-810a-b1e3-000b6571c42a",
    "38163d55-66c5-8197-a990-000bf14dd52b",
    "37e63d55-66c5-81cc-9873-000b7d4ad159",
]
for cid in candidates:
    try:
        req = urllib.request.Request(f"https://api.notion.com/v1/databases/{cid}", headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            schema = json.loads(resp.read().decode())
            title = schema.get("title", [{}])[0].get("plain_text", "") if schema.get("title") else ""
            print(f"\n=== DB: '{title}' ===")
            print(f"ID: {cid}")
            for pname, pdef in schema.get("properties", {}).items():
                print(f"  {pname} ({pdef.get('type','?')})")
    except Exception as e:
        pass

# Check ALLIE page children for child databases
print("\n\n=== ALLIE page children ===")
allie_id = "36d63d55-66c5-8163-8bc9-c438cb43ce3b"
try:
    req = urllib.request.Request(f"https://api.notion.com/v1/blocks/{allie_id}/children?page_size=50", headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        blocks = json.loads(resp.read().decode())
        for block in blocks.get("results", []):
            btype = block.get("type", "?")
            bid = block.get("id", "?")
            if btype == "child_database":
                title = block.get("child_database", {}).get("title", "?")
                print(f"  child_database: '{title}' | ID: {bid}")
except Exception as e:
    print(f"  Error: {e}")

# Also search for any page with "Lab" in title
print("\n\n=== Search for Lab pages ===")
search_req = urllib.request.Request(
    "https://api.notion.com/v1/search",
    data=json.dumps({"query": "Lab", "page_size": 30}).encode(),
    headers=headers, method="POST"
)
try:
    with urllib.request.urlopen(search_req, timeout=15) as resp:
        sres = json.loads(resp.read().decode())
        for r in sres.get("results", []):
            obj = r.get("object", "?")
            rid = r.get("id", "?")
            parent = r.get("parent", {})
            ptype = parent.get("type", "?")
            # Get title
            props = r.get("properties", {})
            title = ""
            if "title" in props:
                titles = props["title"].get("title", [])
                if titles:
                    title = titles[0].get("plain_text", "")
            elif "Name" in props:
                titles = props["Name"].get("title", [])
                if titles:
                    title = titles[0].get("plain_text", "")
            if title:
                print(f"  [{obj}] '{title}' | ID: {rid} | Parent: {ptype}")
            else:
                print(f"  [{obj}] ID: {rid} | Parent: {ptype}")
except Exception as e:
    print(f"  Error: {e}")