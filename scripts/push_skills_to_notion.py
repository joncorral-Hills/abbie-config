#!/usr/bin/env python3
"""
Push new skill files to Allie via Notion pages.

Creates a "📦 New Skills Transfer" page under the ANTIGRAVITY namespace,
then creates child pages for each skill file with the full content as
paragraph blocks. Finally, sends a relay message to Allie.

Usage:
    python3 scripts/push_skills_to_notion.py
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

SKILLS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), ".agents", "skills")

# Skills to transfer
SKILLS = [
    "world-intelligence",
    "stock-weekly-briefing",
    "stock-market-macro",
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
    """Split text content into Notion paragraph blocks (max ~2000 chars each).
    
    Splits on line boundaries to avoid breaking mid-line.
    """
    blocks = []
    lines = content.split("\n")
    current_chunk = ""

    for line in lines:
        # If adding this line would exceed the limit, flush current chunk
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

    # Flush remaining
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

    # Notion API limits to 100 blocks per create request
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

    # Append remaining blocks in batches of 100
    for i in range(0, len(remaining_blocks), 100):
        batch = remaining_blocks[i:i+100]
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
        properties["Context"] = {"rich_text": [{"text": {"content": context[:2000]}}]}

    return notion_request("POST", "pages", api_key, {
        "parent": {"database_id": db_id},
        "properties": properties,
    })


def main():
    config = load_config()
    api_key = config["api_key"]
    parent_page_id = config["page_id"]  # ANTIGRAVITY page
    inbound_db = config["databases"]["inbound_relay"]

    print("📦 Pushing new skills to Notion for Allie...\n")

    # Step 1: Create transfer container page
    transfer_page = create_page_with_content(
        api_key, parent_page_id,
        f"📦 New Skills Transfer — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "This page contains 3 skill definitions (1 new + 2 enhanced) for the World Monitor integration.\n\n"
        "Each child page contains a skill file. The page title indicates the "
        "destination file path on the VM.\n\n"
        "Instructions:\n"
        "1. Read each child page\n"
        "2. Create/overwrite the file at the path indicated in the title\n"
        "3. Write the page content as the file content\n"
        "4. For world-intelligence: follow the full Setup (One-Time) section\n"
        "5. For stock-weekly-briefing and stock-market-macro: files are drop-in replacements\n"
    )

    if not transfer_page:
        print("❌ Failed to create transfer page. Aborting.")
        sys.exit(1)

    print(f"✅ Transfer page created: {transfer_page}\n")

    # Step 2: Create child pages for each skill file
    file_count = 0
    for skill_name in SKILLS:
        skill_dir = os.path.join(SKILLS_DIR, skill_name)
        if not os.path.exists(skill_dir):
            print(f"  ⚠️  Skill directory not found: {skill_dir}")
            continue

        # Walk all files in the skill directory
        for root, dirs, files in os.walk(skill_dir):
            for filename in sorted(files):
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, os.path.join(SKILLS_DIR, ".."))
                # Destination path on VM
                vm_path = f".agents/{rel_path}"

                with open(filepath, "r") as f:
                    try:
                        content = f.read()
                    except UnicodeDecodeError:
                        print(f"  ⚠️  Skipping binary file: {filepath}")
                        continue

                print(f"  📄 {vm_path} ({len(content)} chars)...", end=" ")
                page_id = create_page_with_content(
                    api_key, transfer_page,
                    vm_path,
                    content
                )
                if page_id:
                    print("✅")
                    file_count += 1
                else:
                    print("❌")

    print(f"\n📊 Pushed {file_count} files across {len(SKILLS)} skills.\n")

    # Step 3: Send relay message to Allie
    relay_msg = (
        f"World Monitor integration transfer ready — {file_count} files for 3 skills (1 new + 2 enhanced). "
        "Check the '📦 New Skills Transfer' page under ANTIGRAVITY. "
        "Each child page title is the destination file path. "
        "Install world-intelligence (new) and update stock-weekly-briefing + stock-market-macro (enhanced)."
    )

    context = (
        "BUILD ORDER: world-intelligence → stock-weekly-briefing → stock-market-macro.\n\n"
        "🔑 NEEDS CREDENTIALS: world-intelligence requires WORLDMONITOR_API_KEY env var.\n"
        "Jon needs to subscribe to World Monitor Pro ($39.99/mo) or API Starter and provide the API key.\n\n"
        "AFTER Jon provides the API key:\n"
        "1. Install world-intelligence (new skill — follow full Setup section):\n"
        "   - Add worldmonitor MCP server to ~/.hermes/config.yaml\n"
        "   - pip install worldmonitor-sdk\n"
        "   - Create Notion DB: 🌍 World Intelligence (schema in SKILL.md)\n"
        "   - Register crons WI1-WI4\n"
        "2. Replace stock-weekly-briefing/SKILL.md (enhanced with geopolitical correlation layer)\n"
        "3. Replace stock-market-macro/SKILL.md (enhanced with WM data sources + commodity correlation)\n"
        "4. Both enhanced skills now reference WORLDMONITOR_API_KEY in their env requirements"
    )

    result = send_relay_message(api_key, inbound_db, relay_msg, context)
    if result:
        print("✅ Relay message sent to Allie.")
    else:
        print("❌ Failed to send relay message.")

    print("\n🎉 Done! Allie should pick up the transfer on her next relay check.")


if __name__ == "__main__":
    main()
