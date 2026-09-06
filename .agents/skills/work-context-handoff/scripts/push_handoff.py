#!/usr/bin/env python3
"""
Push a structured handoff document to Notion.

Creates a page under ALLIE and sends a bridge relay notification.

Usage:
    python3 push_handoff.py <handoff.json>

The JSON file must follow this schema:
{
  "title": "Page title",
  "sections": [
    {
      "heading": "Section Title",
      "level": 2,
      "blocks": [
        {"type": "text", "content": "..."},
        {"type": "bullet", "content": "..."},
        {"type": "table", "headers": ["A", "B"], "rows": [["a", "b"]]},
        {"type": "heading", "level": 3, "content": "..."},
        {"type": "divider"}
      ]
    }
  ]
}
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"
ALLIE_PAGE_ID = "36d63d55-66c5-8163-8bc9-c438cb43ce3b"
INBOUND_RELAY_DB = "37963d55-66c5-813f-ba47-fc8e8f5acb67"

# Load API key from config — search known locations
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_SEARCH_PATHS = [
    os.path.join(os.path.expanduser("~"), "Documents", "Abbie", "scripts", ".notion_config.json"),
    os.path.join(SCRIPT_DIR, "..", "..", "..", "..", "scripts", ".notion_config.json"),
    os.path.join(SCRIPT_DIR, "..", "..", "..", "scripts", ".notion_config.json"),
]


def load_api_key():
    """Load API key from env or config file."""
    env_key = os.environ.get("NOTION_API_KEY")
    if env_key:
        return env_key
    for path in CONFIG_SEARCH_PATHS:
        norm = os.path.normpath(path)
        if os.path.exists(norm):
            with open(norm) as f:
                return json.load(f)["api_key"]
    print("Error: No NOTION_API_KEY env var and config not found.")
    for p in CONFIG_SEARCH_PATHS:
        print(f"  Checked: {os.path.normpath(p)}")
    sys.exit(1)


def notion_request(api_key, method, endpoint, body=None):
    """Make an authenticated Notion API request."""
    url = f"{BASE_URL}/{endpoint}"
    cmd = [
        "curl", "-s", "-X", method, url,
        "-H", f"Authorization: Bearer {api_key}",
        "-H", f"Notion-Version: {NOTION_VERSION}",
        "-H", "Content-Type: application/json",
    ]
    if body:
        cmd += ["-d", json.dumps(body)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"curl error: {result.stderr}")
        sys.exit(1)
    data = json.loads(result.stdout)
    status = data.get("status", 200)
    if status >= 400:
        msg = data.get("message", str(data))
        print(f"Notion API error {status}: {msg}")
        sys.exit(1)
    return data


# ── Block builders ────────────────────────────────────────────────────────

def _rich_text(content):
    """Build rich_text array, chunking at 2000 chars."""
    chunks = []
    while content:
        chunks.append({"type": "text", "text": {"content": content[:2000]}})
        content = content[2000:]
    return chunks


def make_heading(level, content):
    t = f"heading_{level}"
    return {"object": "block", "type": t, t: {"rich_text": _rich_text(content)}}


def make_text(content):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(content)},
    }


def make_bullet(content):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(content)},
    }


def make_divider():
    return {"object": "block", "type": "divider", "divider": {}}


def make_table(headers, rows):
    width = len(headers)
    children = [
        {"type": "table_row", "table_row": {
            "cells": [[{"type": "text", "text": {"content": h}}] for h in headers]
        }}
    ]
    for row in rows:
        # Pad row to width if needed
        padded = list(row) + [""] * (width - len(row))
        children.append({
            "type": "table_row",
            "table_row": {
                "cells": [[{"type": "text", "text": {"content": str(c)}}] for c in padded[:width]]
            }
        })
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": width,
            "has_column_header": True,
            "has_row_header": False,
            "children": children,
        }
    }


def make_callout(content, emoji="📋"):
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich_text(content),
            "icon": {"emoji": emoji},
        }
    }


def block_from_spec(spec):
    """Convert a block spec dict to a Notion block."""
    btype = spec["type"]
    if btype == "text":
        return make_text(spec["content"])
    elif btype == "bullet":
        return make_bullet(spec["content"])
    elif btype == "heading":
        return make_heading(spec.get("level", 3), spec["content"])
    elif btype == "table":
        return make_table(spec["headers"], spec["rows"])
    elif btype == "divider":
        return make_divider()
    elif btype == "callout":
        return make_callout(spec["content"], spec.get("emoji", "📋"))
    else:
        return make_text(f"[Unknown block type: {btype}]")


# ── Main ──────────────────────────────────────────────────────────────────

def build_blocks(data):
    """Build all Notion blocks from the handoff JSON."""
    blocks = []

    # Optional callout at the top
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    blocks.append(make_callout(
        f"Compiled by Antigravity on {now} from Alfred's (GravityClaw) working "
        "memory, Obsidian vault, and session logs. This gives Allie situational "
        "awareness of Jon's professional life."
    ))
    blocks.append(make_divider())

    for section in data.get("sections", []):
        level = section.get("level", 2)
        blocks.append(make_heading(level, section["heading"]))
        for b in section.get("blocks", []):
            blocks.append(block_from_spec(b))
        blocks.append(make_divider())

    return blocks


def create_page(api_key, title, blocks):
    """Create the handoff page under ALLIE, batching blocks if needed."""
    first_batch = blocks[:100]
    remaining = blocks[100:]

    body = {
        "parent": {"page_id": ALLIE_PAGE_ID},
        "icon": {"emoji": "🤝"},
        "properties": {
            "title": [{"text": {"content": title}}]
        },
        "children": first_batch,
    }

    print(f"Creating handoff page under ALLIE...")
    result = notion_request(api_key, "POST", "pages", body)
    page_id = result["id"]
    page_url = result.get("url", f"https://notion.so/{page_id.replace('-', '')}")
    print(f"  Page created: {page_id}")
    print(f"  URL: {page_url}")

    # Append remaining blocks in batches of 100
    while remaining:
        batch = remaining[:100]
        remaining = remaining[100:]
        print(f"  Appending {len(batch)} additional blocks...")
        notion_request(api_key, "PATCH", f"blocks/{page_id}/children", {"children": batch})

    return page_id, page_url


def send_notification(api_key, page_id, page_url, title):
    """Send a bridge relay notification to Allie."""
    summary = (
        f"A work context handoff document has been created as a Notion page "
        f"under ALLIE. It covers Jon's meetings, active projects, copywriting "
        f"rules, content brainstorms, and key context from Alfred's system. "
        f"Page ID: {page_id}"
    )

    properties = {
        "Message": {"title": [{"text": {"content": f"📋 {title}"}}]},
        "Source": {"select": {"name": "Antigravity"}},
        "Status": {"select": {"name": "New"}},
        "Timestamp": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        "Category": {"multi_select": [{"name": "Knowledge"}]},
        "Context": {"rich_text": [{"text": {"content": summary[:2000]}}]},
    }

    body = {
        "parent": {"database_id": INBOUND_RELAY_DB},
        "properties": properties,
    }

    print("Sending bridge notification to Allie...")
    result = notion_request(api_key, "POST", "pages", body)
    print(f"  Bridge message sent (ID: {result['id']})")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 push_handoff.py <handoff.json>")
        sys.exit(1)

    json_path = sys.argv[1]
    if not os.path.exists(json_path):
        print(f"Error: File not found: {json_path}")
        sys.exit(1)

    with open(json_path) as f:
        data = json.load(f)

    api_key = load_api_key()
    title = data.get("title", "Alfred to Allie Handoff: Work Context")
    blocks = build_blocks(data)

    print(f"Total blocks: {len(blocks)}")
    page_id, page_url = create_page(api_key, title, blocks)
    send_notification(api_key, page_id, page_url, title)

    print(f"\nHandoff complete.")
    print(f"  Page: {page_url}")

    # Write result for the calling agent to read
    result_path = json_path.replace(".json", "_result.json")
    with open(result_path, "w") as f:
        json.dump({"page_id": page_id, "page_url": page_url}, f, indent=2)
    print(f"  Result saved: {result_path}")


if __name__ == "__main__":
    main()
