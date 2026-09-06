#!/usr/bin/env python3
"""
Notion INVENT Database Integration
===================================
Provides CRUD operations against Jon's INVENT database in Notion.
Uses the Notion API directly via HTTP requests.

Usage:
  python3 notion_invent.py schema                          # Discover database schema
  python3 notion_invent.py list                             # List all ideas
  python3 notion_invent.py create "Title" "Description"     # Create new idea
  python3 notion_invent.py update <page_id> <markdown_file> # Append analysis to page
  python3 notion_invent.py get <page_id>                    # Get idea details
  python3 notion_invent.py search "query"                   # Search ideas by title

Environment:
  NOTION_API_KEY — Notion integration token (required)
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE_ID = "ff59713b9715470d98f8f957e56f3850"
NOTION_VERSION = "2022-06-28"
BASE_URL = "https://api.notion.com/v1"

# Property names the skill expects (adapts if missing)
EXPECTED_PROPERTIES = {
    "title": "Name",           # Title property — required by Notion
    "description": "Description",
    "category": "Category",
    "status": "Status",
    "ip_score": "IP Score",
    "market_score": "Market Score",
    "related_ideas": "Related Ideas",
    "date_added": "Date Added",
    "tags": "Tags",
}

# Status options
STATUS_OPTIONS = ["New", "Analyzed", "Refined", "Parked", "Pursuing"]


# ---------------------------------------------------------------------------
# HTTP Helpers
# ---------------------------------------------------------------------------

def _get_api_key():
    """Retrieve Notion API key from environment or config file."""
    key = os.environ.get("NOTION_API_KEY")
    if key:
        return key
    # Fallback: read from config file (Abbie stores it here too)
    config_path = os.path.expanduser("~/.config/notion/api_key")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            return f.read().strip()
    print("ERROR: NOTION_API_KEY not found in environment or ~/.config/notion/api_key")
    sys.exit(1)


def _headers():
    return {
        "Authorization": f"Bearer {_get_api_key()}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _request(method, path, body=None, retries=3):
    """Make an HTTP request to the Notion API with retry + backoff."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            if e.code == 429:
                # Rate limited — backoff
                wait = min(2 ** attempt, 30)
                print(f"  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                continue
            elif e.code == 409 and attempt < retries - 1:
                # Conflict — retry
                time.sleep(1)
                continue
            else:
                print(f"ERROR: Notion API {method} {path} → {e.code}")
                print(f"  {error_body[:500]}")
                sys.exit(1)
        except urllib.error.URLError as e:
            print(f"ERROR: Network error — {e.reason}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            sys.exit(1)
    
    print("ERROR: Max retries exceeded")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Schema Discovery
# ---------------------------------------------------------------------------

def get_schema():
    """Retrieve and display the INVENT database schema."""
    result = _request("GET", f"/databases/{DATABASE_ID}")
    
    title = "".join(t.get("plain_text", "") for t in result.get("title", []))
    properties = result.get("properties", {})
    
    print(f"Database: {title}")
    print(f"ID: {result.get('id', 'unknown')}")
    print(f"URL: {result.get('url', 'unknown')}")
    print(f"\nProperties ({len(properties)}):")
    print("-" * 60)
    
    schema_map = {}
    for name, prop in sorted(properties.items()):
        prop_type = prop.get("type", "unknown")
        prop_id = prop.get("id", "")
        extra = ""
        
        if prop_type == "select":
            options = [o["name"] for o in prop.get("select", {}).get("options", [])]
            extra = f" → [{', '.join(options)}]"
        elif prop_type == "multi_select":
            options = [o["name"] for o in prop.get("multi_select", {}).get("options", [])]
            extra = f" → [{', '.join(options)}]"
        elif prop_type == "relation":
            rel_db = prop.get("relation", {}).get("database_id", "?")
            extra = f" → relates to {rel_db}"
        elif prop_type == "rollup":
            extra = f" → rollup"
        elif prop_type == "formula":
            expr = prop.get("formula", {}).get("expression", "")
            extra = f" → {expr[:50]}"
        
        print(f"  {name:30s} {prop_type:15s} (id: {prop_id}){extra}")
        schema_map[name] = {"type": prop_type, "id": prop_id}
    
    # Check which expected properties exist
    print(f"\n{'='*60}")
    print("Expected Property Check:")
    for key, expected_name in EXPECTED_PROPERTIES.items():
        found = expected_name in properties
        status = "✅" if found else "❌ MISSING"
        print(f"  {key:20s} → {expected_name:20s} {status}")
    
    return schema_map


# ---------------------------------------------------------------------------
# List Ideas
# ---------------------------------------------------------------------------

def list_ideas(include_body=False):
    """Fetch all ideas from the INVENT database."""
    all_pages = []
    start_cursor = None
    
    while True:
        body = {"page_size": 100}
        if start_cursor:
            body["start_cursor"] = start_cursor
        
        result = _request("POST", f"/databases/{DATABASE_ID}/query", body)
        all_pages.extend(result.get("results", []))
        
        if not result.get("has_more"):
            break
        start_cursor = result.get("next_cursor")
    
    ideas = []
    for page in all_pages:
        idea = _parse_page(page)
        ideas.append(idea)
    
    return ideas


def _parse_page(page):
    """Extract structured data from a Notion page object."""
    props = page.get("properties", {})
    idea = {
        "id": page.get("id", ""),
        "url": page.get("url", ""),
        "created_time": page.get("created_time", ""),
        "last_edited_time": page.get("last_edited_time", ""),
    }
    
    for key, expected_name in EXPECTED_PROPERTIES.items():
        if expected_name not in props:
            idea[key] = None
            continue
        
        prop = props[expected_name]
        prop_type = prop.get("type", "")
        
        if prop_type == "title":
            idea[key] = "".join(t.get("plain_text", "") for t in prop.get("title", []))
        elif prop_type == "rich_text":
            idea[key] = "".join(t.get("plain_text", "") for t in prop.get("rich_text", []))
        elif prop_type == "select":
            sel = prop.get("select")
            idea[key] = sel.get("name") if sel else None
        elif prop_type == "multi_select":
            idea[key] = [o.get("name") for o in prop.get("multi_select", [])]
        elif prop_type == "number":
            idea[key] = prop.get("number")
        elif prop_type == "date":
            d = prop.get("date")
            idea[key] = d.get("start") if d else None
        elif prop_type == "relation":
            idea[key] = [r.get("id") for r in prop.get("relation", [])]
        elif prop_type == "checkbox":
            idea[key] = prop.get("checkbox", False)
        else:
            idea[key] = f"[{prop_type}]"
    
    return idea


def print_ideas(ideas):
    """Pretty-print a list of ideas."""
    if not ideas:
        print("No ideas found in the INVENT database.")
        return
    
    print(f"Found {len(ideas)} idea(s):\n")
    for i, idea in enumerate(ideas, 1):
        title = idea.get("title") or "(untitled)"
        status = idea.get("status") or "-"
        ip = idea.get("ip_score")
        market = idea.get("market_score")
        category = idea.get("category") or "-"
        
        ip_str = f"{ip}/10" if ip is not None else "-"
        market_str = f"{market}/10" if market is not None else "-"
        
        print(f"  {i:3d}. {title}")
        print(f"       Status: {status}  |  IP: {ip_str}  |  Market: {market_str}  |  Category: {category}")
        if idea.get("description"):
            desc = idea["description"][:120]
            print(f"       {desc}{'...' if len(idea.get('description', '')) > 120 else ''}")
        print(f"       URL: {idea.get('url', '-')}")
        print()


# ---------------------------------------------------------------------------
# Create Idea
# ---------------------------------------------------------------------------

def create_idea(title, description, category=None, tags=None):
    """Create a new idea page in the INVENT database."""
    # First, discover schema to know which properties exist
    db = _request("GET", f"/databases/{DATABASE_ID}")
    existing_props = set(db.get("properties", {}).keys())
    
    # Build properties payload
    properties = {}
    
    # Title is always the title property — find it
    title_prop_name = None
    for name, prop in db.get("properties", {}).items():
        if prop.get("type") == "title":
            title_prop_name = name
            break
    
    if not title_prop_name:
        print("ERROR: No title property found in database")
        sys.exit(1)
    
    properties[title_prop_name] = {
        "title": [{"text": {"content": title}}]
    }
    
    # Optional properties — only set if they exist in the schema
    if EXPECTED_PROPERTIES["description"] in existing_props:
        properties[EXPECTED_PROPERTIES["description"]] = {
            "rich_text": [{"text": {"content": description[:2000]}}]
        }
    
    if EXPECTED_PROPERTIES["status"] in existing_props:
        properties[EXPECTED_PROPERTIES["status"]] = {
            "select": {"name": "New"}
        }
    
    if category and EXPECTED_PROPERTIES["category"] in existing_props:
        properties[EXPECTED_PROPERTIES["category"]] = {
            "select": {"name": category}
        }
    
    if EXPECTED_PROPERTIES["date_added"] in existing_props:
        properties[EXPECTED_PROPERTIES["date_added"]] = {
            "date": {"start": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
        }
    
    if tags and EXPECTED_PROPERTIES["tags"] in existing_props:
        properties[EXPECTED_PROPERTIES["tags"]] = {
            "multi_select": [{"name": t} for t in tags]
        }
    
    # Build page body with the raw description
    children = [
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Original Idea"}}]
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": description}}]
            }
        },
        {
            "object": "block",
            "type": "divider",
            "divider": {}
        }
    ]
    
    body = {
        "parent": {"database_id": DATABASE_ID},
        "properties": properties,
        "children": children,
    }
    
    result = _request("POST", "/pages", body)
    page_id = result.get("id", "")
    page_url = result.get("url", "")
    
    print(f"✅ Created idea: \"{title}\"")
    print(f"   Page ID: {page_id}")
    print(f"   URL: {page_url}")
    
    return {"id": page_id, "url": page_url}


# ---------------------------------------------------------------------------
# Update Idea (Append Analysis)
# ---------------------------------------------------------------------------

def update_idea_body(page_id, markdown_content):
    """Append analysis content as blocks to an existing idea page."""
    blocks = _markdown_to_blocks(markdown_content)
    
    # Notion API limits children to 100 blocks per request
    for i in range(0, len(blocks), 100):
        batch = blocks[i:i+100]
        _request("PATCH", f"/blocks/{page_id}/children", {"children": batch})
    
    print(f"✅ Appended {len(blocks)} blocks to page {page_id}")


def update_idea_properties(page_id, **kwargs):
    """Update specific properties on an idea page.
    
    Accepted kwargs: ip_score, market_score, status, category, tags, related_ideas
    """
    # Discover schema first
    db = _request("GET", f"/databases/{DATABASE_ID}")
    existing_props = set(db.get("properties", {}).keys())
    
    properties = {}
    
    if "ip_score" in kwargs and EXPECTED_PROPERTIES["ip_score"] in existing_props:
        properties[EXPECTED_PROPERTIES["ip_score"]] = {"number": kwargs["ip_score"]}
    
    if "market_score" in kwargs and EXPECTED_PROPERTIES["market_score"] in existing_props:
        properties[EXPECTED_PROPERTIES["market_score"]] = {"number": kwargs["market_score"]}
    
    if "status" in kwargs and EXPECTED_PROPERTIES["status"] in existing_props:
        properties[EXPECTED_PROPERTIES["status"]] = {"select": {"name": kwargs["status"]}}
    
    if "category" in kwargs and EXPECTED_PROPERTIES["category"] in existing_props:
        properties[EXPECTED_PROPERTIES["category"]] = {"select": {"name": kwargs["category"]}}
    
    if "tags" in kwargs and EXPECTED_PROPERTIES["tags"] in existing_props:
        properties[EXPECTED_PROPERTIES["tags"]] = {
            "multi_select": [{"name": t} for t in kwargs["tags"]]
        }
    
    if "related_ideas" in kwargs and EXPECTED_PROPERTIES["related_ideas"] in existing_props:
        properties[EXPECTED_PROPERTIES["related_ideas"]] = {
            "relation": [{"id": rid} for rid in kwargs["related_ideas"]]
        }
    
    if not properties:
        print("⚠️  No matching properties found to update")
        return
    
    _request("PATCH", f"/pages/{page_id}", {"properties": properties})
    print(f"✅ Updated properties on page {page_id}")


# ---------------------------------------------------------------------------
# Get Idea Details
# ---------------------------------------------------------------------------

def get_idea(page_id):
    """Get full details for a specific idea page."""
    page = _request("GET", f"/pages/{page_id}")
    idea = _parse_page(page)
    
    # Also fetch page body blocks
    blocks = []
    start_cursor = None
    while True:
        path = f"/blocks/{page_id}/children?page_size=100"
        if start_cursor:
            path += f"&start_cursor={start_cursor}"
        result = _request("GET", path)
        blocks.extend(result.get("results", []))
        if not result.get("has_more"):
            break
        start_cursor = result.get("next_cursor")
    
    idea["body_blocks"] = len(blocks)
    idea["body_text"] = _blocks_to_text(blocks)
    
    return idea


def _blocks_to_text(blocks):
    """Extract plain text from Notion blocks."""
    lines = []
    for block in blocks:
        btype = block.get("type", "")
        content = block.get(btype, {})
        
        if "rich_text" in content:
            text = "".join(t.get("plain_text", "") for t in content["rich_text"])
            if btype.startswith("heading"):
                level = btype[-1] if btype[-1].isdigit() else "2"
                lines.append(f"{'#' * int(level)} {text}")
            else:
                lines.append(text)
        elif btype == "divider":
            lines.append("---")
        elif btype == "bulleted_list_item":
            text = "".join(t.get("plain_text", "") for t in content.get("rich_text", []))
            lines.append(f"- {text}")
        elif btype == "numbered_list_item":
            text = "".join(t.get("plain_text", "") for t in content.get("rich_text", []))
            lines.append(f"1. {text}")
    
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Search Ideas
# ---------------------------------------------------------------------------

def search_ideas(query):
    """Search ideas by title (client-side filter since Notion text search is limited)."""
    ideas = list_ideas()
    query_lower = query.lower()
    matches = [
        idea for idea in ideas
        if query_lower in (idea.get("title") or "").lower()
        or query_lower in (idea.get("description") or "").lower()
    ]
    return matches


# ---------------------------------------------------------------------------
# Markdown → Notion Blocks Converter
# ---------------------------------------------------------------------------

def _markdown_to_blocks(md_text):
    """Convert simple markdown to Notion block objects.
    
    Supports: headings (##, ###), paragraphs, bulleted lists, dividers, bold/italic.
    """
    blocks = []
    lines = md_text.strip().split("\n")
    
    for line in lines:
        stripped = line.strip()
        
        if not stripped:
            continue
        
        if stripped == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif stripped.startswith("### "):
            blocks.append(_heading_block(3, stripped[4:]))
        elif stripped.startswith("## "):
            blocks.append(_heading_block(2, stripped[3:]))
        elif stripped.startswith("# "):
            blocks.append(_heading_block(1, stripped[2:]))
        elif stripped.startswith("- ") or stripped.startswith("* "):
            blocks.append(_bullet_block(stripped[2:]))
        elif stripped.startswith("> "):
            blocks.append(_callout_block(stripped[2:]))
        else:
            blocks.append(_paragraph_block(stripped))
    
    return blocks


def _rich_text(content):
    """Create a rich_text array with basic formatting support."""
    # Handle bold (**text**) and italic (*text*)
    segments = []
    remaining = content
    
    while remaining:
        # Find bold markers
        bold_start = remaining.find("**")
        if bold_start != -1:
            bold_end = remaining.find("**", bold_start + 2)
            if bold_end != -1:
                # Text before bold
                if bold_start > 0:
                    segments.append({
                        "type": "text",
                        "text": {"content": remaining[:bold_start]},
                    })
                # Bold text
                segments.append({
                    "type": "text",
                    "text": {"content": remaining[bold_start+2:bold_end]},
                    "annotations": {"bold": True},
                })
                remaining = remaining[bold_end+2:]
                continue
        
        # No more formatting — add rest as plain text
        # Notion limits rich_text content to 2000 chars per segment
        while remaining:
            chunk = remaining[:2000]
            segments.append({
                "type": "text",
                "text": {"content": chunk},
            })
            remaining = remaining[2000:]
        break
    
    return segments if segments else [{"type": "text", "text": {"content": content[:2000]}}]


def _heading_block(level, text):
    key = f"heading_{level}"
    return {
        "object": "block",
        "type": key,
        key: {"rich_text": _rich_text(text)},
    }


def _paragraph_block(text):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(text)},
    }


def _bullet_block(text):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(text)},
    }


def _callout_block(text):
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich_text(text),
            "icon": {"emoji": "⚠️"},
        },
    }


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    command = sys.argv[1].lower()
    
    if command == "schema":
        get_schema()
    
    elif command == "list":
        ideas = list_ideas()
        print_ideas(ideas)
    
    elif command == "create":
        if len(sys.argv) < 4:
            print("Usage: notion_invent.py create \"Title\" \"Description\" [category]")
            sys.exit(1)
        title = sys.argv[2]
        description = sys.argv[3]
        category = sys.argv[4] if len(sys.argv) > 4 else None
        create_idea(title, description, category)
    
    elif command == "update":
        if len(sys.argv) < 4:
            print("Usage: notion_invent.py update <page_id> <markdown_file>")
            sys.exit(1)
        page_id = sys.argv[2]
        md_file = sys.argv[3]
        with open(md_file, "r") as f:
            content = f.read()
        update_idea_body(page_id, content)
    
    elif command == "get":
        if len(sys.argv) < 3:
            print("Usage: notion_invent.py get <page_id>")
            sys.exit(1)
        page_id = sys.argv[2]
        idea = get_idea(page_id)
        print(json.dumps(idea, indent=2, default=str))
    
    elif command == "search":
        if len(sys.argv) < 3:
            print("Usage: notion_invent.py search \"query\"")
            sys.exit(1)
        query = sys.argv[2]
        matches = search_ideas(query)
        print_ideas(matches)
    
    elif command == "set-props":
        # Usage: set-props <page_id> key=value key=value ...
        if len(sys.argv) < 4:
            print("Usage: notion_invent.py set-props <page_id> key=value ...")
            sys.exit(1)
        page_id = sys.argv[2]
        kwargs = {}
        for arg in sys.argv[3:]:
            k, v = arg.split("=", 1)
            # Auto-convert numeric values
            try:
                v = int(v)
            except ValueError:
                try:
                    v = float(v)
                except ValueError:
                    pass
            kwargs[k] = v
        update_idea_properties(page_id, **kwargs)
    
    else:
        print(f"Unknown command: {command}")
        print("Commands: schema, list, create, update, get, search, set-props")
        sys.exit(1)


if __name__ == "__main__":
    main()
