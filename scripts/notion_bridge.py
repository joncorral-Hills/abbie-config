#!/usr/bin/env python3
"""
Antigravity ↔ Allie Notion Bridge

Relay messages between Antigravity (local Mac) and Allie (Hermes VM)
via shared Notion databases.

Usage:
    python3 notion_bridge.py send "Your message here" [--category task] [--context "extra context"]
    python3 notion_bridge.py read                     # Read unprocessed messages from Allie
    python3 notion_bridge.py status                   # Check both relay queues
    python3 notion_bridge.py ack PAGE_ID              # Mark an outbound message as Delivered
    python3 notion_bridge.py knowledge list           # List Knowledge Index entries
    python3 notion_bridge.py knowledge add "Title" --content "Details"
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, ".notion_config.json")
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"


def load_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"Error: Config not found at {CONFIG_PATH}")
        print("Create .notion_config.json with api_key and database IDs.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    # Prefer env var over config file for the API key (reduces leak surface)
    env_key = os.environ.get("NOTION_API_KEY")
    if env_key:
        config["api_key"] = env_key
    return config


def notion_request(method, endpoint, api_key, body=None):
    """Make an authenticated request to the Notion API via curl."""
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

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Invalid response: {result.stdout[:500]}")
        sys.exit(1)

    if "status" in data and data["status"] >= 400:
        print(f"Notion API error {data['status']}: {data.get('message', data)}")
        sys.exit(1)

    return data


def query_database(api_key, db_id, filter_obj=None, sorts=None):
    """Query a Notion database with optional filters and sorting."""
    body = {}
    if filter_obj:
        body["filter"] = filter_obj
    if sorts:
        body["sorts"] = sorts
    return notion_request("POST", f"databases/{db_id}/query", api_key, body)


def create_page(api_key, db_id, properties):
    """Create a new page (row) in a Notion database."""
    body = {
        "parent": {"database_id": db_id},
        "properties": properties,
    }
    return notion_request("POST", "pages", api_key, body)


def update_page(api_key, page_id, properties):
    """Update properties on an existing Notion page."""
    return notion_request("PATCH", f"pages/{page_id}", api_key, {"properties": properties})


# ── Commands ──────────────────────────────────────────────────────────────

def cmd_send(args, config):
    """Send a message to Allie via the Inbound Relay."""
    api_key = config["api_key"]
    db_id = config["databases"]["inbound_relay"]

    properties = {
        "Message": {"title": [{"text": {"content": args.message}}]},
        "Source": {"select": {"name": "Antigravity"}},
        "Status": {"select": {"name": "New"}},
        "Timestamp": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
    }

    if args.category:
        properties["Category"] = {"multi_select": [{"name": args.category}]}
    if args.context:
        properties["Context"] = {"rich_text": [{"text": {"content": args.context}}]}

    result = create_page(api_key, db_id, properties)
    page_id = result["id"]
    print(f"✅ Sent to Allie → \"{args.message}\"")
    print(f"   Page ID: {page_id}")
    print(f"   Category: {args.category or 'none'}")
    print(f"   Status: New (waiting for Allie to process)")


def cmd_read(args, config):
    """Read undelivered messages from Allie via the Outbound Relay."""
    api_key = config["api_key"]
    db_id = config["databases"]["outbound_relay"]

    # Fetch messages with Status = Pending
    filter_obj = {
        "property": "Status",
        "select": {"equals": "Pending"},
    }
    sorts = [{"property": "Timestamp", "direction": "ascending"}]
    result = query_database(api_key, db_id, filter_obj, sorts)

    messages = result.get("results", [])
    if not messages:
        print("📭 No new messages from Allie.")
        return

    print(f"📬 {len(messages)} message(s) from Allie:\n")
    for msg in messages:
        props = msg["properties"]
        page_id = msg["id"]

        title = _get_title(props.get("Message", {}))
        msg_type = _get_select(props.get("Type", {}))
        content = _get_rich_text(props.get("Content", {}))
        timestamp = _get_date(props.get("Timestamp", {}))

        print(f"  {'─' * 60}")
        print(f"  ID:        {page_id}")
        print(f"  Type:      {msg_type}")
        print(f"  Time:      {timestamp}")
        print(f"  Subject:   {title}")
        if content:
            print(f"  Content:   {content[:500]}")
        print()

    if args.auto_ack:
        for msg in messages:
            update_page(api_key, msg["id"], {
                "Status": {"select": {"name": "Delivered"}}
            })
        print(f"✅ Marked {len(messages)} message(s) as Delivered.")


def cmd_status(args, config):
    """Show queue status for both relays."""
    api_key = config["api_key"]

    # Inbound: messages we sent that Allie hasn't processed
    inbound_pending = query_database(api_key, config["databases"]["inbound_relay"], {
        "property": "Status",
        "select": {"equals": "New"},
    })
    inbound_count = len(inbound_pending.get("results", []))

    # Outbound: messages from Allie we haven't read
    outbound_pending = query_database(api_key, config["databases"]["outbound_relay"], {
        "property": "Status",
        "select": {"equals": "Pending"},
    })
    outbound_count = len(outbound_pending.get("results", []))

    print("📊 Bridge Status")
    print(f"   → Inbound (Antigravity → Allie):  {inbound_count} awaiting processing")
    print(f"   ← Outbound (Allie → Antigravity): {outbound_count} unread")

    if outbound_count > 0:
        print(f"\n   Run `python3 notion_bridge.py read` to see Allie's messages.")


def cmd_ack(args, config):
    """Mark a specific outbound message as Delivered."""
    api_key = config["api_key"]
    update_page(api_key, args.page_id, {
        "Status": {"select": {"name": "Delivered"}}
    })
    print(f"✅ Marked {args.page_id} as Delivered.")


def cmd_knowledge(args, config):
    """List or add entries to the Knowledge Index."""
    api_key = config["api_key"]
    db_id = config["databases"]["knowledge_index"]

    if args.knowledge_action == "list":
        result = query_database(api_key, db_id)
        entries = result.get("results", [])
        if not entries:
            print("📚 Knowledge Index is empty.")
            return
        print(f"📚 Knowledge Index ({len(entries)} entries):\n")
        for entry in entries:
            props = entry["properties"]
            title = _get_title(props.get("Name", props.get("Title", {})))
            print(f"  • {title}")

    elif args.knowledge_action == "add":
        properties = {
            "Title": {"title": [{"text": {"content": args.title}}]},
            "Type": {"select": {"name": "Skill"}},
            "Last Updated": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        }
        if args.content:
            properties["Description"] = {"rich_text": [{"text": {"content": args.content[:2000]}}]}
        create_page(api_key, db_id, properties)
        print(f"✅ Added to Knowledge Index: \"{args.title}\"")


# ── Property helpers ──────────────────────────────────────────────────────

def _get_title(prop):
    try:
        return prop["title"][0]["plain_text"]
    except (KeyError, IndexError):
        return "(untitled)"

def _get_select(prop):
    try:
        return prop["select"]["name"]
    except (KeyError, TypeError):
        return "(none)"

def _get_rich_text(prop):
    try:
        return "".join(t["plain_text"] for t in prop["rich_text"])
    except (KeyError, TypeError):
        return ""

def _get_date(prop):
    try:
        return prop["date"]["start"]
    except (KeyError, TypeError):
        return "(no date)"


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Antigravity ↔ Allie Notion Bridge",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # send
    p_send = subparsers.add_parser("send", help="Send a message to Allie")
    p_send.add_argument("message", help="Message text")
    p_send.add_argument("--category", choices=["Task", "Query", "Knowledge", "Idea", "Alert"], default=None)
    p_send.add_argument("--context", help="Additional context", default=None)

    # read
    p_read = subparsers.add_parser("read", help="Read messages from Allie")
    p_read.add_argument("--auto-ack", action="store_true", help="Auto-mark as Delivered after reading")

    # status
    subparsers.add_parser("status", help="Check relay queue status")

    # ack
    p_ack = subparsers.add_parser("ack", help="Mark an outbound message as Delivered")
    p_ack.add_argument("page_id", help="Notion page ID to acknowledge")

    # knowledge
    p_know = subparsers.add_parser("knowledge", help="Manage Knowledge Index")
    k_sub = p_know.add_subparsers(dest="knowledge_action", required=True)
    k_sub.add_parser("list", help="List all entries")
    k_add = k_sub.add_parser("add", help="Add an entry")
    k_add.add_argument("title", help="Entry title")
    k_add.add_argument("--content", help="Entry content/description", default=None)

    args = parser.parse_args()
    config = load_config()

    commands = {
        "send": cmd_send,
        "read": cmd_read,
        "status": cmd_status,
        "ack": cmd_ack,
        "knowledge": cmd_knowledge,
    }
    commands[args.command](args, config)


if __name__ == "__main__":
    main()
