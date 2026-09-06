---
name: work-context-handoff
description: >
  Scans Alfred's (GravityClaw) working memory, Obsidian vault, and session logs
  to compile a structured handoff document about Jon's professional life at
  Hill's Pet Nutrition, then pushes it to Allie's Notion workspace. Use when
  the user says 'handoff to Allie,' 'sync Alfred notes to Allie,' 'update Allie
  on my work,' 'work context handoff,' 'transfer work notes,' 'give Allie my
  work context,' or wants Allie to understand Jon's meetings, projects, and
  assignments from Alfred's perspective.
---

# Work Context Handoff Skill

Compile Alfred's knowledge of Jon's work life into a structured Notion page
under ALLIE, then notify Allie via the bridge relay.

## Source Locations

Scan these locations in order. Skip any that don't exist.

### Alfred's Working Memory
1. `/Users/JonCorral/Documents/GravityClaw/MEMORY.md` — meetings, projects, user profile, copywriting rules
2. `/Users/JonCorral/Documents/GravityClaw/memory/SOUL.md` — identity
3. `/Users/JonCorral/Documents/GravityClaw/memory/USER.md` — preferences

### Alfred Session Logs
4. `/Users/JonCorral/Documents/Alfred-Agent/memory/*.md` — work logs (read all)
5. `/Users/JonCorral/Documents/Abbie/memory/*.md` — Antigravity logs (read last 7 days)

### Obsidian Vault (Google Drive)

Base path: `/Users/JonCorral/Library/CloudStorage/GoogleDrive-jon_corral@hillspet.com/My Drive/Obsidian Vault/`

6. `YYYY-MM-DD.md` (root) — today's daily note (today's focus, tasks)
7. `Dashboard.md` — active project list with stacks and statuses
8. `MOC.md` — Map of Content (full project index, NotebookLM notebooks, prompt library)
9. `Work/PROJECTS ⭐/` — all project files (read each `.md`)
10. `meetings/` — all meeting notes (read each `.md`)
11. `inbox/` — recent brainstorms and captured ideas (read each `.md`)
12. `Reference/daily/` — recent daily logs (read last 14 days)

## Output Structure

Build a Notion page with these sections:

| # | Section | Source |
|---|---------|--------|
| 1 | Jon's Work Profile | GravityClaw MEMORY.md |
| 2 | Recurring Meeting Schedule + Proactive Patterns | GravityClaw MEMORY.md |
| 3 | Active Work Projects | Dashboard.md + `Work/PROJECTS ⭐/` files |
| 4 | Recent Content Work & Brainstorms | `inbox/` files |
| 5 | Copywriting Rules & Preferences | GravityClaw MEMORY.md |
| 6 | Key Integrations | ALFRED_HANDOFF.md or GravityClaw codebase |
| 7 | Knowledge Base & Content Resources | MOC.md (NotebookLM notebooks) |
| 8 | Key Context for Allie | GravityClaw MEMORY.md + USER.md |
| 9 | Today's Focus | Today's daily note |
| 10 | Open / Active Threads | Dashboard.md open questions + recent inbox |

## Execution

Run `scripts/push_handoff.py` with the compiled content. The script:

1. Creates a Notion page under ALLIE (`36d63d55-66c5-8163-8bc9-c438cb43ce3b`)
2. Writes all sections as structured Notion blocks (headings, tables, bullets)
3. Sends a bridge relay notification via the Inbound Relay DB

### Script Usage

```bash
python3 <skill_dir>/scripts/push_handoff.py <handoff_json_path>
```

The script expects a JSON file with this schema:

```json
{
  "title": "Alfred → Allie Handoff: Jon's Work Life Context",
  "sections": [
    {
      "heading": "Section Title",
      "level": 2,
      "blocks": [
        {"type": "text", "content": "Paragraph text"},
        {"type": "bullet", "content": "Bullet point"},
        {"type": "table", "headers": ["Col1", "Col2"], "rows": [["a", "b"]]},
        {"type": "heading", "level": 3, "content": "Sub-heading"},
        {"type": "divider"}
      ]
    }
  ]
}
```

### Notion Configuration

Read from `/Users/JonCorral/Documents/Abbie/scripts/.notion_config.json`:

| Key | Value | Purpose |
|-----|-------|---------|
| `api_key` | From config file | Notion API authentication |
| `databases.inbound_relay` | `37963d55-66c5-813f-ba47-fc8e8f5acb67` | Bridge relay notification |

Parent page: ALLIE `36d63d55-66c5-8163-8bc9-c438cb43ce3b`

### Block Limits

- Notion API: max 100 children per request — batch if needed
- Rich text: max 2000 chars per text element — chunk longer content
- Tables: include `has_column_header: true`

## Workflow

1. **Scan** all source locations, collect raw content
2. **Synthesize** into the 10-section structure — deduplicate, merge related items
3. **Write** the handoff JSON to a temp file
4. **Run** `scripts/push_handoff.py` to create the Notion page
5. **Report** the page URL and bridge notification status to the user
6. **Optionally** provide a prompt the user can paste into Allie's Telegram to help her interpret the handoff

## Allie Interpretation Prompt Template

When the user asks for a prompt to give Allie, use this template (customize the page ID):

```
Read the new Notion page under ALLIE titled "Alfred → Allie Handoff: Jon's
Work Life Context" (page ID: <PAGE_ID>). This was compiled by Antigravity
from Alfred's working memory.

How to interpret it:
- Sections 1–2 (profile + meetings) — my weekly work rhythm. Context only.
- Section 3 (active projects) — work projects, not personal. You don't own them.
- Section 4 (brainstorms) — content ideas from Hill's. Context only.
- Section 5 (copywriting rules) — Alfred's domain unless I ask for Hill's copy help.
- Sections 6–7 (integrations + knowledge) — Alfred's toolchain. Reference only.
- Section 8 (key context) — communication style applies to you too.
- Section 9 (today's focus) — awareness only.

Store the key facts in your memory. Don't create projects or tasks from it.
The goal is that when I mention work stuff in passing, you have enough context
to understand without me explaining from scratch.
```
