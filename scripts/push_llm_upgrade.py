#!/usr/bin/env python3
"""
Push LLM upgrade package to Allie via Notion relay.

Creates a transfer page under ANTIGRAVITY with the upgrade script,
then sends a minimal relay message with exact execution instructions.

Usage:
    python3 scripts/push_llm_upgrade.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, ".notion_config.json")
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

# Files to transfer
FILES_TO_PUSH = [
    os.path.join(SCRIPT_DIR, "llm-upgrade.sh"),
]


def load_config():
    with open(CONFIG_PATH) as f:
        config = json.load(f)
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
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Invalid response: {result.stdout[:500]}")
        sys.exit(1)

    if "status" in data and data["status"] >= 400:
        print(f"Notion API error {data['status']}: {data.get('message', data)}")
        return None

    return data


def text_to_blocks(content, max_len=1900):
    """Split text content into Notion paragraph blocks."""
    blocks = []
    lines = content.split("\n")
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_len and current_chunk:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": current_chunk}
                    }]
                }
            })
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"

    if current_chunk.strip():
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": current_chunk}
                }]
            }
        })

    return blocks


def create_page_with_content(api_key, parent_id, title, content, is_database=False):
    """Create a Notion page under a parent with text content as child blocks."""
    blocks = text_to_blocks(content)
    initial_blocks = blocks[:100]
    remaining_blocks = blocks[100:]

    parent_key = "database_id" if is_database else "page_id"
    body = {
        "parent": {parent_key: parent_id},
        "properties": {
            "title": {"title": [{"text": {"content": title}}]}
        },
        "children": initial_blocks
    }

    result = notion_request("POST", "pages", api_key, body)
    if not result:
        print(f"  ❌ Failed to create page: {title}")
        return None

    page_id = result["id"]

    for i in range(0, len(remaining_blocks), 100):
        batch = remaining_blocks[i:i + 100]
        append_body = {"children": batch}
        notion_request("PATCH", f"blocks/{page_id}/children", api_key, append_body)

    return page_id


def send_relay_message(api_key, db_id, message, context=None):
    """Send a message via the Inbound Relay."""
    properties = {
        "Message": {"title": [{"text": {"content": message}}]},
        "Source": {"select": {"name": "Antigravity"}},
        "Status": {"select": {"name": "New"}},
        "Timestamp": {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        "Category": {"multi_select": [{"name": "Task"}]},
    }
    if context:
        properties["Context"] = {
            "rich_text": [{"text": {"content": context[:2000]}}]
        }

    return notion_request("POST", "pages", api_key, {
        "parent": {"database_id": db_id},
        "properties": properties,
    })


def main():
    config = load_config()
    api_key = config["api_key"]
    parent_page_id = config["page_id"]
    inbound_db = config["databases"]["inbound_relay"]

    print("🔧 Pushing LLM upgrade package to Notion for Allie...\n")

    # Create transfer page
    transfer_page = create_page_with_content(
        api_key, parent_page_id,
        f"🔧 LLM Upgrade Package — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        (
            "This package upgrades the local LLM from Qwen2.5-7B to Qwen3-4B with speculative decoding.\n\n"
            "Expected improvement: 0.75 tok/s → 8-15 tok/s (10-20x faster).\n\n"
            "Contains:\n"
            "1. llm-upgrade.sh — Self-contained bash script. Run it, everything else is automatic.\n"
            "2. Cron routing changes — Listed in the relay message context.\n\n"
            "The script handles: pip install, llama.cpp rebuild with AVX-512/AMX, model download, "
            "server restart, and verification. Zero LLM reasoning required — just execute.\n"
        )
    )

    if not transfer_page:
        print("❌ Failed to create transfer page. Aborting.")
        sys.exit(1)

    print(f"✅ Transfer page created: {transfer_page}\n")

    # Push the upgrade script
    file_count = 0
    for filepath in FILES_TO_PUSH:
        if not os.path.exists(filepath):
            print(f"  ⚠️  File not found: {filepath}")
            continue

        filename = os.path.basename(filepath)
        with open(filepath, "r") as f:
            content = f.read()

        print(f"  📄 {filename} ({len(content)} chars)...", end=" ")
        page_id = create_page_with_content(
            api_key, transfer_page,
            f"~/llm-upgrade.sh",
            content
        )
        if page_id:
            print("✅")
            file_count += 1
        else:
            print("❌")

    print(f"\n📊 Pushed {file_count} file(s).\n")

    # ─── Relay Message ────────────────────────────────────────────
    relay_msg = (
        "LLM upgrade package ready. "
        "Upgrades local LLM from Qwen2.5-7B (0.75 tok/s) to Qwen3-4B with speculative decoding (8-15 tok/s). "
        "Execute the 3 steps in Context — all mechanical, no reasoning needed."
    )

    context = """STEP 1 — RUN UPGRADE SCRIPT:
Save llm-upgrade.sh from the transfer page to ~/llm-upgrade.sh, then:
  chmod +x ~/llm-upgrade.sh && bash ~/llm-upgrade.sh
This handles: pip install python-telegram-bot, llama.cpp rebuild (AVX-512+AMX), Qwen3-4B + 0.6B download, server restart with speculative decoding on port 8082. Runtime: ~15 min.

STEP 2 — UPDATE WATCHDOG:
In ~/.hermes/scripts/llm-watchdog.py, replace the old llama-server command for port 8082 with:
  ~/.local/start-llama-server.sh
Or replace the model path and arguments inline to match the generated startup script.

STEP 3 — CRON ROUTING CHANGES:
Move these crons FROM llama-local TO gemini-local (not privacy-sensitive):
  - weekly-training-intelligence
  - weekly-fitness-overview
  - HM1 (Weekly Home Maint Check)
  - HM2 (Seasonal Home Maint Prep)
  - LS1 (Monthly Life Score Report)

KEEP on llama-local (privacy-sensitive):
  - Monthly Financial Update
  - All TX* crons (tax-planner)
  - Any health crons with PII (lab results, medications, biomarkers)

STAGGER Monday AM crons (now on gemini-local, fast):
  - 7:00 AM: HM1
  - 7:15 AM: weekly-fitness-overview
  - 7:30 AM: weekly-cost-review

VERIFY after all steps:
  curl http://localhost:8082/health
  curl http://localhost:8082/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Say OK"}],"max_tokens":5}'"""

    result = send_relay_message(api_key, inbound_db, relay_msg, context)
    if result:
        print("✅ Relay message sent to Allie.")
    else:
        print("❌ Failed to send relay message.")

    print("\n🎉 Done! Allie will pick this up on her next relay check.")


if __name__ == "__main__":
    main()
