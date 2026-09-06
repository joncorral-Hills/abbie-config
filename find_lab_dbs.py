#!/usr/bin/env python3
"""Find the Lab Results and Lab Markers databases."""
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

# Check the parent of known Lab pages
lab_pages = [
    ("Jon Northwestern Lab Results", "0de28424-8519-4873-8dc3-3c6419246aca"),
    ("Jaime October Labcorp", "c4d7790b-a9f6-4a14-95e3-da9ebe3a90e3"),
    ("Joey Lab Tests", "f056d2a5-371a-4bca-894d-e16fa83dd885"),
]

print("=== Checking parents of lab pages ===")
for name, pid in lab_pages:
    try:
        req = urllib.request.Request(f"https://api.notion.com/v1/pages/{pid}", headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            page = json.loads(resp.read().decode())
            parent = page.get("parent", {})
            print(f"'{name}' parent: type={parent.get('type','?')} id={parent.get('database_id','?')}")
    except Exception as e:
        print(f"'{name}' error: {e}")

# Check unnamed databases that might be Lab Results
print("\n=== Checking unnamed databases for lab content ===")
unnamed_dbs = [
    "38163d55-66c5-8178-af96-ee43f6617cd4",
    "38163d55-66c5-8159-9ee2-f6b07fa1d25a",
    "36d63d55-66c5-81ce-931f-fad8cdd29699",
    "36d63d55-66c5-81eb-93d8-e13f83f0d152",
]
for did in unnamed_dbs:
    try:
        req = urllib.request.Request(f"https://api.notion.com/v1/databases/{did}", headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            schema = json.loads(resp.read().decode())
            title = schema.get("title", [{}])[0].get("plain_text", "") if schema.get("title") else "(empty)"
            print(f"\nDB: '{title}' | ID: {did}")
            # Query for first 3 results to see content
            qreq = urllib.request.Request(
                f"https://api.notion.com/v1/databases/{did}/query",
                data=json.dumps({"page_size": 3}).encode(),
                headers=headers, method="POST"
            )
            with urllib.request.urlopen(qreq, timeout=10) as qresp:
                qres = json.loads(qresp.read().decode())
                for r in qres.get("results", []):
                    props = r.get("properties", {})
                    # Get name/title
                    name = ""
                    for key in ["Name", "Title", "Lab Results"]:
                        if key in props:
                            titles = props[key].get("title", [])
                            if titles:
                                name = titles[0].get("plain_text", "")
                    print(f"  Sample: '{name}'  Props: {list(props.keys())}")
    except Exception as e:
        print(f"  DB {did[:15]}... error: {e}")