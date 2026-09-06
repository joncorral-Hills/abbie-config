#!/usr/bin/env python3
"""Check TRAVEL page and Trips database in Notion."""
import json, urllib.request

with open("/home/ubuntu/.hermes/.env") as f:
    env = {}
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v

TOKEN = env.get("NOTION_API_KEY", "")
if not TOKEN:
    print("NO_API_KEY")
    exit(1)

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

# Search for TRAVEL
data = json.dumps({"query": "TRAVEL", "page_size": 10}).encode()
req = urllib.request.Request("https://api.notion.com/v1/search", data=data, headers=headers, method="POST")
with urllib.request.urlopen(req, timeout=15) as resp:
    search_results = json.loads(resp.read().decode())

print("=== SEARCH RESULTS ===")
for r in search_results.get("results", []):
    obj = r.get("object", "?")
    pid = r.get("id", "?")
    title = ""
    props = r.get("properties", {})
    if obj == "page":
        t = props.get("title", props.get("Name", {}))
        if isinstance(t, dict):
            parts = t.get("title", [])
            if parts and isinstance(parts[0], dict):
                title = parts[0].get("plain_text", "")
    elif obj == "database":
        t = r.get("title", [])
        if t and isinstance(t[0], dict):
            title = t[0].get("plain_text", "")
    elif obj == "data_source":
        t = r.get("title", [])
        if t and isinstance(t[0], dict):
            title = t[0].get("plain_text", "")
    print(f"  {obj.upper()}: id={pid} title=\"{title}\"")

# Also search for Trips, Japan, trip, etc.
for q in ["Trips", "Trip", "travel", "✈️"]:
    data = json.dumps({"query": q, "page_size": 5}).encode()
    req = urllib.request.Request("https://api.notion.com/v1/search", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res = json.loads(resp.read().decode())
        for r in res.get("results", []):
            obj = r.get("object", "?")
            pid = r.get("id", "?")
            title = ""
            props = r.get("properties", {})
            if obj == "page":
                t = props.get("title", props.get("Name", {}))
                if isinstance(t, dict):
                    parts = t.get("title", [])
                    if parts and isinstance(parts[0], dict):
                        title = parts[0].get("plain_text", "")
            elif obj == "database":
                t = r.get("title", [])
                if t and isinstance(t[0], dict):
                    title = t[0].get("plain_text", "")
            elif obj == "data_source":
                t = r.get("title", [])
                if t and isinstance(t[0], dict):
                    title = t[0].get("plain_text", "")
            if "trip" in title.lower() or "travel" in title.lower() or "✈️" in title or "japan" in title.lower() or "flight" in title.lower() or "hotel" in title.lower():
                print(f"  [{q}] {obj.upper()}: id={pid} title=\"{title}\"")
    except:
        pass

print("\nDone.")