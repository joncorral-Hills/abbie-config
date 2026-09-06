#!/usr/bin/env python3
"""
Push stock analysis skills to Allie via Notion.
Creates sub-pages under the ALLIE parent page with skill content,
then sends a relay notification.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
ALLIE_PAGE_ID = "36d63d55-66c5-8163-8bc9-c438cb43ce3b"
INBOUND_RELAY_DB = "37963d55-66c5-813f-ba47-fc8e8f5acb67"
NOTION_API = "https://api.notion.com/v1"

SKILLS_BASE = Path("/Users/JonCorral/Documents/Abbie/.agents/skills")

SKILLS = [
    {
        "name": "stock-fundamentals",
        "files": [
            "SKILL.md",
            "scripts/fundamental_screen.py",
            "references/metric_definitions.md",
        ]
    },
    {
        "name": "stock-technicals",
        "files": [
            "SKILL.md",
            "scripts/technical_scan.py",
            "references/indicator_guide.md",
        ]
    },
    {
        "name": "stock-sentiment",
        "files": [
            "SKILL.md",
            "scripts/sentiment_scan.py",
            "references/sentiment_signals.md",
        ]
    },
    {
        "name": "stock-market-macro",
        "files": [
            "SKILL.md",
            "scripts/macro_dashboard.py",
            "references/sector_etf_map.md",
            "references/economic_indicators.md",
        ]
    },
    {
        "name": "stock-weekly-briefing",
        "files": [
            "SKILL.md",
            "scripts/weekly_pipeline.py",
            "references/risk_rules.md",
            "references/report_template.md",
        ]
    },
]

ENV_VARS_NOTE = """Required Environment Variables:
- ALPHA_VANTAGE_API_KEY=6IMKV6GJ8UN4PPQU
- FMP_API_KEY=Mm9b2M98TEmt21hCZsvZKueQMKZqneo5
- FINNHUB_API_KEY=d1k2jihr01ql1h3a965gd1k2jihr01ql1h3a9660
- FRED_API_KEY=180b0cbfb3895d253d02e46d9678d0f1

Critical API Notes (Already Debugged):
- FMP: Must use /stable/ endpoints (NOT /api/v3/). Free tier returns 403 on /api/v3/.
- Alpha Vantage: Must use TIME_SERIES_DAILY (NOT TIME_SERIES_DAILY_ADJUSTED — premium). Do NOT use outputsize=full (also premium). Default compact gives 100 trading days.
- Alpha Vantage fields: Use '4. close' and '5. volume' (NOT '5. adjusted close' / '6. volume').
- FMP field names on /stable/: priceToEarningsGrowthRatioTTM, debtToEquityRatioTTM, dividendPayoutRatioTTM, priceToEarningsRatioTTM, freeCashFlowYieldTTM.
- Alpha Vantage rate limit: 25 requests/day on free tier.
- All scripts use stdlib only (no pip installs needed).
- weekly_pipeline.py SKILLS_DIR variable must be updated to point to Allie's skills directory on the VM."""


def notion_request(method, endpoint, data=None):
    """Make a Notion API request."""
    url = f"{NOTION_API}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"HTTP {e.code} on {endpoint}: {error_body}", file=sys.stderr)
        raise
    except Exception as e:
        print(f"Error on {endpoint}: {e}", file=sys.stderr)
        raise


def chunk_text(text, size=2000):
    """Split text into chunks of at most `size` characters."""
    return [text[i:i + size] for i in range(0, len(text), size)]


def make_code_block(content, language="markdown"):
    """Create a Notion code block, splitting into 2000-char rich_text segments."""
    chunks = chunk_text(content)
    rich_text = [{"type": "text", "text": {"content": c}} for c in chunks]
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": rich_text,
            "language": language,
        }
    }


def make_heading(text, level=3):
    """Create a Notion heading block."""
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {
            "rich_text": [{"type": "text", "text": {"content": text}}]
        }
    }


def detect_language(filepath):
    """Detect the code language from the file extension."""
    ext = Path(filepath).suffix.lower()
    lang_map = {
        ".py": "python",
        ".md": "markdown",
        ".sh": "bash",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
    }
    return lang_map.get(ext, "plain text")


def push_skill(skill_def):
    """Push a single skill to Notion as a sub-page of ALLIE."""
    skill_name = skill_def["name"]
    skill_dir = SKILLS_BASE / skill_name

    print(f"\n📦 Pushing skill: {skill_name}")

    # Build children blocks
    children = []

    for rel_path in skill_def["files"]:
        file_path = skill_dir / rel_path
        if not file_path.exists():
            print(f"  ⚠️  Missing: {file_path}", file=sys.stderr)
            continue

        content = file_path.read_text(encoding="utf-8")
        lang = detect_language(rel_path)

        children.append(make_heading(rel_path, level=3))
        children.append(make_code_block(content, lang))

        print(f"  ✅ {rel_path} ({len(content)} chars)")

    if not children:
        print(f"  ❌ No files found for {skill_name}, skipping.")
        return None

    # Notion API limits children to 100 blocks per request
    # Our skills are small enough to fit, but chunk if needed
    payload = {
        "parent": {"page_id": ALLIE_PAGE_ID},
        "properties": {
            "title": [{"text": {"content": f"Skill: {skill_name}"}}]
        },
        "children": children[:100],  # Notion limit
    }

    result = notion_request("POST", "pages", payload)
    page_id = result["id"]
    print(f"  📄 Created page: {page_id}")

    # If more than 100 blocks, append the rest
    if len(children) > 100:
        for i in range(100, len(children), 100):
            batch = children[i:i + 100]
            notion_request("PATCH", f"blocks/{page_id}/children", {"children": batch})
            print(f"  📎 Appended {len(batch)} additional blocks")

    return page_id


def send_relay_notification(message):
    """Send a notification to Allie via the Inbound Relay DB."""
    payload = {
        "parent": {"database_id": INBOUND_RELAY_DB},
        "properties": {
            "Message": {
                "title": [{"text": {"content": message}}]
            },
            "Status": {
                "select": {"name": "New"}
            },
            "Source": {
                "select": {"name": "Antigravity"}
            },
            "Category": {
                "multi_select": [{"name": "Skill"}]
            },
        }
    }
    result = notion_request("POST", "pages", payload)
    print(f"📨 Relay notification sent: {result['id']}")
    return result["id"]


def main():
    if not NOTION_API_KEY:
        print("❌ NOTION_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("Stock Analysis Skills → Allie (via Notion)")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 60)

    # 1. Push setup notes as a dedicated page
    setup_children = [
        make_heading("Environment Variables & API Notes", level=2),
        make_code_block(ENV_VARS_NOTE, "bash"),
        make_heading("Directory Structure", level=2),
        make_code_block(
            "stock-fundamentals/\n"
            "├── SKILL.md\n"
            "├── scripts/fundamental_screen.py\n"
            "└── references/metric_definitions.md\n"
            "\n"
            "stock-technicals/\n"
            "├── SKILL.md\n"
            "├── scripts/technical_scan.py\n"
            "└── references/indicator_guide.md\n"
            "\n"
            "stock-sentiment/\n"
            "├── SKILL.md\n"
            "├── scripts/sentiment_scan.py\n"
            "└── references/sentiment_signals.md\n"
            "\n"
            "stock-market-macro/\n"
            "├── SKILL.md\n"
            "├── scripts/macro_dashboard.py\n"
            "├── references/sector_etf_map.md\n"
            "└── references/economic_indicators.md\n"
            "\n"
            "stock-weekly-briefing/\n"
            "├── SKILL.md\n"
            "├── scripts/weekly_pipeline.py\n"
            "├── references/risk_rules.md\n"
            "└── references/report_template.md\n",
            "plain text"
        ),
    ]

    setup_payload = {
        "parent": {"page_id": ALLIE_PAGE_ID},
        "properties": {
            "title": [{"text": {"content": "Stock Skills — Setup & API Notes"}}]
        },
        "children": setup_children,
    }
    setup_result = notion_request("POST", "pages", setup_payload)
    setup_page_id = setup_result["id"]
    print(f"\n📋 Setup page created: {setup_page_id}")

    # 2. Push each skill
    page_ids = {"setup": setup_page_id}
    for skill in SKILLS:
        pid = push_skill(skill)
        if pid:
            page_ids[skill["name"]] = pid

    # 3. Send relay notification
    skill_list = ", ".join(page_ids.keys())
    id_list = ", ".join(f"{k}={v}" for k, v in page_ids.items())
    message = (
        f"Stock analysis skills delivered (5 skills, 16 files). "
        f"Skills: {skill_list}. "
        f"Action required: Install to skills directory, set env vars, update SKILLS_DIR in weekly_pipeline.py. "
        f"See setup page {setup_page_id} for details."
    )
    send_relay_notification(message)

    print("\n" + "=" * 60)
    print("✅ All skills pushed to Notion successfully.")
    print(f"Pages created: {json.dumps(page_ids, indent=2)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
