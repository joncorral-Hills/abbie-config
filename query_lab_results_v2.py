#!/usr/bin/env python3
"""Dump Notion search results and inspect the Lab Results DB."""
import json
import urllib.request
import os

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

headers = {
    "Authorization": f"Bearer {notion_key}",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json"
}

# Search for Lab Results
search_payload = {
    "query": "Lab",
    "filter": {"value": "data_source", "property": "object"},
    "page_size": 20
}
req = urllib.request.Request(
    "https://api.notion.com/v1/search",
    data=json.dumps(search_payload).encode(),
    headers=headers, method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        search_result = json.loads(resp.read().decode())
except Exception as e:
    print(json.dumps({"error": f"Search failed: {str(e)}"}))
    exit(1)

print("SEARCH RESULTS (data sources matching 'Lab'):")
for r in search_result.get("results", []):
    props = r.get("properties", {})
    title = ""
    if "title" in props:
        title_objs = props["title"].get("title", [])
        if title_objs:
            title = title_objs[0].get("plain_text", "")
    did = r.get("data_source_id") or r.get("id")
    print(f"  Title: '{title}' | ID: {did} | Object: {r.get('object')}")

# Also search pages
search_payload2 = {
    "query": "Lab Results",
    "page_size": 20
}
req2 = urllib.request.Request(
    "https://api.notion.com/v1/search",
    data=json.dumps(search_payload2).encode(),
    headers=headers, method="POST"
)
try:
    with urllib.request.urlopen(req2, timeout=15) as resp2:
        search_result2 = json.loads(resp2.read().decode())
except Exception as e:
    print(json.dumps({"error": f"Search 2 failed: {str(e)}"}))
    exit(1)

print("\nALL RESULTS matching 'Lab Results':")
for r in search_result2.get("results", []):
    obj_type = r.get("object")
    props = r.get("properties", {})
    title = ""
    if "title" in props:
        title_objs = props["title"].get("title", [])
        if title_objs:
            title = title_objs[0].get("plain_text", "")
    rid = r.get("id", "")
    print(f"  Type: {obj_type} | Title: '{title}' | ID: {rid}")

# Also check the workspace-specific quirks for known DB IDs
print("\n\nTrying workspace-specific DB IDs...")
# The runbook says: 36d63d55-66c5-8125-8c68-ee03bf91096c/Lab Results and /Lab Markers
# Let me try the raw parent ID
print(f"\nSearching with parent DB ID: 36d63d55-66c5-8125-8c68-ee03bf91096c")
search_payload3 = {
    "query": "36d63d55",
    "page_size": 20
}
req3 = urllib.request.Request(
    "https://api.notion.com/v1/search",
    data=json.dumps(search_payload3).encode(),
    headers=headers, method="POST"
)
try:
    with urllib.request.urlopen(req3, timeout=15) as resp3:
        search_result3 = json.loads(resp3.read().decode())
except Exception as e:
    print(json.dumps({"error": f"Search 3 failed: {str(e)}"}))
    exit(1)

for r in search_result3.get("results", []):
    obj_type = r.get("object")
    props = r.get("properties", {})
    title = ""
    if "title" in props:
        title_objs = props["title"].get("title", [])
        if title_objs:
            title = title_objs[0].get("plain_text", "")
    rid = r.get("id", "")
    parent = r.get("parent", {})
    print(f"  Type: {obj_type} | Title: '{title}' | ID: {rid} | Parent: {parent.get('type','?')}")