#!/usr/bin/env python3
"""Find Workouts and PRs database IDs from the Health & Fitness parent page."""
import json, urllib.request

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

# Get children blocks of the Health & Fitness page
page_id = "36d63d55-66c5-8125-8c68-ee03bf91096c"
block_children = []
next_cursor = None

while True:
    url = f"https://api.notion.com/v1/blocks/{page_id}/children?page_size=50"
    if next_cursor:
        url += f"&start_cursor={next_cursor}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode())
    block_children.extend(result.get("results", []))
    if result.get("has_more") and result.get("next_cursor"):
        next_cursor = result["next_cursor"]
    else:
        break

print(f"=== CHILD BLOCKS ({len(block_children)}) ===")
for b in block_children:
    btype = b.get("type", "?")
    # Child database blocks have type "child_database"
    if btype == "child_database":
        child_db = b.get("child_database", {})
        title = child_db.get("title", "?")
        # The ID of the database itself is in the block
        db_id = b.get("id", "").replace("-", "")
        print(f"  DB: '{title}' — ID: {b.get('id')} (plain: {db_id})")
    else:
        # Could be a heading, paragraph, etc.
        text = ""
        items = b.get(btype, {})
        if "rich_text" in items:
            text = "".join(t.get("plain_text", "") for t in items.get("rich_text", []))[:50]
        print(f"  Block type={btype}: '{text}'")