#!/usr/bin/env python3
"""Query Brave Search API for flight prices."""
import json, urllib.request

# Read API key from .env
with open("/home/ubuntu/.hermes/.env") as f:
    env = {}
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v

# Also try directly from environment or known patterns
BRAVE_KEY = env.get("BRAVE_SEARCH_API_KEY", "")
if not BRAVE_KEY:
    # Try from config.yaml
    with open("/home/ubuntu/.hermes/config.yaml") as f:
        for line in f:
            if "api_key" in line and "brave" in line.lower():
                parts = line.split(":", 1)
                if len(parts) > 1:
                    BRAVE_KEY = parts[1].strip().strip('"').strip("'")
                    break

if not BRAVE_KEY:
    print("NO_BRAVE_KEY")
    exit(1)

queries = [
    "flights MCI to NRT Tokyo June 2027 round trip price cheap",
    "flights MCI to HND Tokyo June 2027 round trip price cheap",
    "Kansas City to Tokyo flights June 2027 round trip",
]

for q in queries:
    url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(q)}&count=5"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "X-Subscription-Token": BRAVE_KEY
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        print(f"\n=== Query: {q} ===")
        for r in data.get("web", {}).get("results", []):
            title = r.get("title", "")
            desc = r.get("description", "")[:200]
            url2 = r.get("url", "")
            print(f"  [{title}]({url2})")
            print(f"  {desc}")
    except Exception as e:
        print(f"\n=== Query: {q} - ERROR: {e} ===")

print("\nDone.")