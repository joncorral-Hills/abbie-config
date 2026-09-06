#!/usr/bin/env python3
"""
Push the bridge server to Allie via Notion pages.

Creates a "🌉 Bridge Server Deploy" page under the ANTIGRAVITY namespace,
then creates child pages for each file with the full content as
paragraph blocks. Finally, sends a relay message to Allie.

Usage:
    python3 scripts/push_bridge_to_notion.py
"""

import json
import os
import sys
from datetime import datetime, timezone

# Re-use the push infrastructure from push_skills_to_notion.py
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, ".notion_config.json")
REPO_ROOT = os.path.dirname(SCRIPT_DIR)

# Files to transfer with their VM destination paths
FILES = [
    {
        "local": os.path.join(REPO_ROOT, "bridge", "server", "main.py"),
        "vm_path": "bridge/server/main.py",
    },
    {
        "local": os.path.join(REPO_ROOT, "bridge", "server", "requirements.txt"),
        "vm_path": "bridge/server/requirements.txt",
    },
    {
        "local": os.path.join(REPO_ROOT, "bridge", "server", "start.sh"),
        "vm_path": "bridge/server/start.sh",
    },
]

# Import shared functions from the existing push script
sys.path.insert(0, SCRIPT_DIR)
from push_skills_to_notion import (
    load_config,
    notion_request,
    create_page_with_content,
    send_relay_message,
)


def main():
    config = load_config()
    api_key = config["api_key"]
    parent_page_id = config["page_id"]  # ANTIGRAVITY page
    inbound_db = config["databases"]["inbound_relay"]

    print("🌉 Pushing bridge server to Notion for Allie...\n")

    # Step 1: Create transfer container page
    transfer_page = create_page_with_content(
        api_key, parent_page_id,
        f"🌉 Bridge Server Deploy — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "FastAPI bridge server for direct Antigravity↔Allie HTTP communication.\n\n"
        "Each child page contains a file. The page title indicates the "
        "destination path on the VM (relative to home dir).\n\n"
        "Instructions:\n"
        "1. Read each child page\n"
        "2. Create the file at ~/bridge/server/<filename>\n"
        "3. Write the page content as the file content\n"
        "4. Install deps: pip install fastapi uvicorn pyyaml\n"
        "5. Set env var: export BRIDGE_API_KEY='UCn0ayC8rB8VS0s3JhdZ7YsNBfzga5jxNF2PhX4qBeM'\n"
        "6. chmod +x ~/bridge/server/start.sh\n"
        "7. Start: cd ~/bridge/server && ./start.sh\n"
        "8. Add to supervisord for auto-restart\n"
    )

    if not transfer_page:
        print("❌ Failed to create transfer page. Aborting.")
        sys.exit(1)

    print(f"✅ Transfer page created: {transfer_page}\n")

    # Step 2: Push each file
    file_count = 0
    for entry in FILES:
        local_path = entry["local"]
        vm_path = entry["vm_path"]

        if not os.path.exists(local_path):
            print(f"  ⚠️  File not found: {local_path}")
            continue

        with open(local_path, "r") as f:
            content = f.read()

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

    print(f"\n📊 Pushed {file_count} files.\n")

    # Step 3: Send relay message
    relay_msg = (
        f"Bridge server deploy ready — {file_count} files. "
        "Check '🌉 Bridge Server Deploy' page under ANTIGRAVITY. "
        "Each child page title is the destination file path."
    )

    context = (
        "DEPLOY STEPS:\n"
        "1. Create ~/bridge/server/ directory\n"
        "2. Write each file from the Notion pages to the correct path\n"
        "3. pip install fastapi uvicorn pyyaml\n"
        "4. Add to .bashrc or supervisord: export BRIDGE_API_KEY='UCn0ayC8rB8VS0s3JhdZ7YsNBfzga5jxNF2PhX4qBeM'\n"
        "5. chmod +x ~/bridge/server/start.sh\n"
        "6. Start the server: cd ~/bridge/server && ./start.sh &\n"
        "7. Verify: curl http://localhost:8787/health\n"
        "8. Add to supervisord for persistence:\n"
        "   [program:bridge-server]\n"
        "   command=/home/ubuntu/bridge/server/start.sh\n"
        "   directory=/home/ubuntu/bridge/server\n"
        "   environment=BRIDGE_API_KEY='UCn0ayC8rB8VS0s3JhdZ7YsNBfzga5jxNF2PhX4qBeM'\n"
        "   autostart=true\n"
        "   autorestart=true\n"
        "   stdout_logfile=/var/log/bridge-server.log\n"
        "   stderr_logfile=/var/log/bridge-server.err\n\n"
        "PORT: 8787 — needs to be open externally. Check if the Abacus SuperComputer "
        "firewall allows inbound on 8787, or use the same mechanism that opens 9119.\n\n"
        "VERIFY FROM EXTERNAL: curl http://208.122.8.11:8787/health"
    )

    result = send_relay_message(api_key, inbound_db, relay_msg, context)
    if result:
        print("✅ Relay message sent to Allie.")
    else:
        print("❌ Failed to send relay message.")

    print("\n🎉 Done! Tell Allie to check her inbound relay.")


if __name__ == "__main__":
    main()
