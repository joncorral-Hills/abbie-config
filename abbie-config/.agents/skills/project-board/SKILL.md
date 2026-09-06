---
name: project-board
description: >
  Kanban-style project management board in Notion. Tracks all of Allie's active,
  queued, blocked, and completed projects across all skill domains. Jon can
  directly edit the board to add projects, reprioritize, or change instructions
  via the "Jon's Notes" field. Allie reads the board at session start and
  updates it as work progresses.
requires:
  bins: [python3]
  env: [NOTION_API_KEY]
---

# Project Board Skill

## Overview

This skill gives Allie a visual, interactive project management system via a
Notion Kanban board. It serves two purposes:

1. **For Jon**: A real-time dashboard of what Allie is working on, what's stuck,
   and what's done. Jon can add new projects, reprioritize, or leave instructions
   directly in Notion — no need to go through Telegram or the bridge.

2. **For Allie**: A persistent work queue that survives session boundaries.
   Allie reads the board to decide what to work on next and updates it as
   progress is made.

**Parent page**: ALLIE (`36d63d55-66c5-8163-8bc9-c438cb43ce3b`)
**Database name**: 📋 Project Board

---

## Setup (One-Time)

### Step 1: Create the Database

Create an **inline database** under the ALLIE page using the schema in
`resources/notion_schema.json`. The database should be named **📋 Project Board**.

Create all properties exactly as specified in the schema. Pay attention to select
option colors — they make the board scannable.

### Step 2: Create Views

Create 3 views on the database:

1. **Board** (Board view, default)
   - Group by: `Status`
   - Sort by: `Priority` ascending (High first)
   - Column order: 📋 Backlog → 🔄 In Progress → ⏸️ On Hold → 👀 Needs Review → ✅ Done
   - Show properties on cards: Priority, Skill, Owner, Due Date

2. **Active** (Table view)
   - Filter: Status = "🔄 In Progress" OR "👀 Needs Review"
   - Sort by: Priority ascending

3. **By Skill** (Table view)
   - Group by: Skill
   - Sort by: Status ascending

### Step 3: Seed Initial Projects

Use the `seed_data` in `resources/notion_schema.json` to create the initial
project cards. These represent known open work items from the July 2026
integration review.

### Step 4: Record the Database ID

After creating the database, record its ID in your memory. You'll use it for
all future queries and updates.

---

## Properties Reference

| Property | Type | Purpose |
|----------|------|---------|
| **Project** | Title | Project name — short, scannable |
| **Status** | Select | Kanban column (see statuses below) |
| **Priority** | Select | 🔴 High / 🟡 Medium / 🟢 Low |
| **Skill** | Select | Domain: Financial, Health, Invention, Infrastructure, Research, Other |
| **Owner** | Select | Allie (autonomous), Jon (needs his action), Both (collaborative) |
| **Description** | Rich Text | What needs to be done |
| **Jon's Notes** | Rich Text | Jon's instructions or feedback — **read-only for Allie** |
| **Allie's Notes** | Rich Text | Allie's working notes — **write-only for Allie** |
| **Blocked By** | Rich Text | What's preventing progress |
| **Outcome** | Rich Text | Filled when Done — summary of what was accomplished |
| **Due Date** | Date | Optional target date |
| **Last Touched** | Date | Last time Allie updated this project |
| **Created** | Created Time | Auto-populated by Notion |

---

## Status Definitions

| Status | Meaning | When to use |
|--------|---------|-------------|
| 📋 **Backlog** | Identified but not started | New projects, future work |
| 🔄 **In Progress** | Actively being worked on | Allie is currently executing |
| ⏸️ **On Hold** | Paused — blocked by external dependency | Waiting on Jon, API key, data, etc. |
| 👀 **Needs Review** | Work done, needs Jon's input | Allie finished but needs approval/feedback |
| ✅ **Done** | Completed | Fill Outcome field with summary |

---

## Allie's Operating Protocol

### On Session Start

1. Query the Project Board for all projects where Status ≠ ✅ Done
2. Check for any changes in **Jon's Notes** since last session (compare to
   Allie's Notes or Last Touched date)
3. If Jon added new projects or modified existing ones, acknowledge and
   incorporate into the current session plan
4. Prioritize work: 🔴 High → 🟡 Medium → 🟢 Low, with Owner = Allie first

### During Work

1. When starting work on a project:
   - Set Status → 🔄 In Progress
   - Set Last Touched → now
   - Add a note to Allie's Notes: "Started YYYY-MM-DD: [brief plan]"

2. When making progress:
   - Update Allie's Notes with progress
   - Set Last Touched → now

3. When blocked:
   - Set Status → ⏸️ On Hold
   - Fill Blocked By with the specific blocker
   - Set Last Touched → now

4. When work is done and needs Jon's review:
   - Set Status → 👀 Needs Review
   - Update Allie's Notes with what was done
   - Set Last Touched → now

5. When fully complete:
   - Set Status → ✅ Done
   - Fill Outcome with a clear summary of what was accomplished
   - Set Last Touched → now

### On Session End

1. Update Last Touched on any project worked on during the session
2. If a project was started but not finished, leave notes in Allie's Notes
   explaining current state and next steps

### Board Hygiene

- **Weekly**: Review all ⏸️ On Hold projects. If the blocker has been resolved,
  move to 📋 Backlog or 🔄 In Progress.
- **Monthly**: Archive ✅ Done projects older than 30 days (move to a separate
  "Archive" page or add an "Archived" status).
- **Never** delete a project. Even failed or abandoned projects should be marked
  Done with an Outcome explaining why.
- **Never** overwrite Jon's Notes. That field is Jon's voice — read it, act on
  it, but don't modify it. Respond in Allie's Notes.

---

## Jon's Interaction Model

Jon interacts with the board directly in Notion:

1. **Add a project**: Create a new row, fill in Project name, Description, and
   Priority. Set Owner to "Allie" if it's autonomous work.
2. **Reprioritize**: Change the Priority select on any project.
3. **Give instructions**: Write in **Jon's Notes** — Allie reads this field at
   session start and will act on it.
4. **Change approach**: Edit the Description or add to Jon's Notes to redirect
   how Allie handles a project.
5. **Drag cards**: In Board view, drag cards between Status columns to manually
   override status (e.g., move something from On Hold back to Backlog).
6. **Approve work**: When a project is in 👀 Needs Review, Jon can move it to
   ✅ Done or back to 🔄 In Progress with feedback in Jon's Notes.

---

## Creating New Projects Programmatically

When Allie identifies new work (from cron jobs, conversation, or other skills),
she should create a new project card:

```python
# Example: create a new project via Notion API
properties = {
    "Project": {"title": [{"text": {"content": "New project name"}}]},
    "Status": {"select": {"name": "📋 Backlog"}},
    "Priority": {"select": {"name": "🟡 Medium"}},
    "Skill": {"select": {"name": "Financial"}},
    "Owner": {"select": {"name": "Allie"}},
    "Description": {"rich_text": [{"text": {"content": "What needs to be done"}}]},
    "Last Touched": {"date": {"start": "2026-07-06T12:00:00-05:00"}}
}
```

Self-created projects should start in 📋 Backlog with a clear Description.
Allie is free to move her own projects through the board autonomously —
including starting work on self-created projects when capacity allows. Use
good judgment on prioritization: finish In Progress work before starting new
Backlog items, and respect Jon's Priority rankings.

**Jon's override**: If Jon sets a project to ⏸️ On Hold, writes "pause" or
"wait" in Jon's Notes, or changes Priority, Allie must respect that. Jon's
direct edits to the board always take precedence over Allie's autonomous
decisions.

---

## Integration with Other Skills

| Skill | Integration |
|-------|-------------|
| `financial-automation` | Financial cron failures → create On Hold project card |
| `financial-planner` | Missing data items → track as Backlog projects owned by Jon |
| `health-automation` | Deployment blockers → tracked as On Hold |
| `health-planner` | Depends on health-automation completion |
| `invention-processor` | New invention ideas → optionally create a project card for follow-up |

---

## Files in This Skill

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — instructions and operating protocol |
| `resources/notion_schema.json` | Database schema, view definitions, and seed data |
