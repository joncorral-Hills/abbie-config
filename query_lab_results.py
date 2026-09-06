#!/usr/bin/env python3
"""Query Notion Lab Results DB for recent lab entries."""
import json
import urllib.request
import os

# Load Notion API key
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

# Lab Results DB ID: 36d63d55-66c5-8125-8c68-ee03bf91096c
db_id = "36d63d55-66c5-8125-8c68-ee03bf91096c"

# First, search to find the actual database/data_source ID
search_payload = {
    "query": "Lab Results",
    "filter": {"value": "data_source", "property": "object"},
    "page_size": 10
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

# Look for Lab Results data source
data_source_id = None
for result in search_result.get("results", []):
    props = result.get("properties", {})
    title = ""
    if "title" in props:
        title_objs = props["title"].get("title", [])
        if title_objs:
            title = title_objs[0].get("plain_text", "")
    if "Lab Results" in title or "Lab Result" in title:
        data_source_id = result.get("data_source_id") or result.get("id")
        print(f"FOUND: {title} -> id={data_source_id}", file=open("/dev/stderr", "w"))
        break

# Also try using the raw ID from runbook
if not data_source_id:
    print(f"Trying direct DB ID: {db_id}", file=open("/dev/stderr", "w"))
    data_source_id = db_id

# Now query the data source for recent entries
query_payload = {
    "sorts": [{"property": "Date", "direction": "descending"}],
    "page_size": 20
}

# Try the data source query endpoint
req2 = urllib.request.Request(
    f"https://api.notion.com/v1/data_sources/{data_source_id}/query",
    data=json.dumps(query_payload).encode(),
    headers=headers, method="POST"
)
try:
    with urllib.request.urlopen(req2, timeout=15) as resp2:
        data = json.loads(resp2.read().decode())
except Exception as e:
    print(json.dumps({"error": f"Data source query failed: {str(e)}"}))
    print(json.dumps({"search_result_summary": {"total": search_result.get("total"), "results_count": len(search_result.get("results", []))}}))
    # Fallback: try database endpoint with older API version
    print("Trying fallback with 2022-06-28 API version...", file=open("/dev/stderr", "w"))
    headers2 = {**headers, "Notion-Version": "2022-06-28"}
    req3 = urllib.request.Request(
        f"https://api.notion.com/v1/databases/{db_id}/query",
        data=json.dumps(query_payload).encode(),
        headers=headers2, method="POST"
    )
    try:
        with urllib.request.urlopen(req3, timeout=15) as resp3:
            data = json.loads(resp3.read().decode())
    except Exception as e2:
        print(json.dumps({"error": f"Fallback also failed: {str(e2)}"}))
        exit(1)

print(json.dumps(data, default=str))