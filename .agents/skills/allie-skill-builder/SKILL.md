---
name: allie-skill-builder
description: >
  End-to-end pipeline for designing, building, and deploying new skills to Allie's
  Hermes VM via the Notion bridge. Handles skill architecture design, SKILL.md 
  authoring, resource file creation, Notion transfer via push script, and generates
  Telegram activation prompts for Jon. Use whenever Jon asks to add new capabilities,
  features, or automations to Allie.
requires:
  bins: [python3]
  env: [NOTION_API_KEY]
---

# Allie Skill Builder

## Overview

This skill defines the complete pipeline for creating new skills for Allie (Hermes VM assistant) from Antigravity (local Mac). It covers the full lifecycle:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ALLIE SKILL BUILDER PIPELINE                         │
│                                                                         │
│  Phase 1: RESEARCH          Phase 2: DESIGN          Phase 3: BUILD     │
│  ┌──────────────────┐      ┌──────────────────┐      ┌──────────────┐  │
│  │ Load SOUL.md     │      │ Gap analysis     │      │ Create       │  │
│  │ Load MEMORY.md   │─────▶│ Feature proposal │─────▶│ SKILL.md     │  │
│  │ Audit skills     │      │ Impl plan + gate │      │ Resource JSON│  │
│  │ Check project bd │      │ User approval    │      │ Validate all │  │
│  └──────────────────┘      └──────────────────┘      └──────────────┘  │
│                                                              │          │
│  Phase 4: TRANSFER          Phase 5: ACTIVATE                │          │
│  ┌──────────────────┐      ┌──────────────────┐             │          │
│  │ push_skills_to_  │      │ Generate Telegram│             │          │
│  │ notion.py        │◀─────│ prompts for Jon  │◀────────────┘          │
│  │ Relay message    │      │ Confirm receipt  │                         │
│  │ Verify delivery  │      │ Monitor setup    │                         │
│  └──────────────────┘      └──────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Principle

**Allie cannot read Antigravity's local filesystem.** All file transfers go through Notion. The `push_skills_to_notion.py` script handles this by creating Notion pages with file content as child blocks, then sending a relay message.

---

## Phase 1: Research Current State

Before designing new skills, always audit what Allie already has.

### Step 1.1: Load Cognitive Files

Read these files from the workspace root:

| File | Purpose |
|------|---------|
| `SOUL.md` | Allie's identity, tone, communication style |
| `MEMORY.md` | Technical stack, architecture decisions, API keys available |
| `USER.md` | Jon's preferences, coding style |

### Step 1.2: Inventory Existing Skills

```bash
# List all current skills
ls -la .agents/skills/

# Count lines per SKILL.md to gauge complexity
find .agents/skills -name "SKILL.md" -exec wc -l {} \;

# List all resource files
find .agents/skills -name "*.json" | sort
```

### Step 1.3: Check Active Projects

Query the Project Board for in-progress or blocked items that might affect new skill design:
- Page ID: `39563d55-66c5-81c3-827b-e124fc4bba17`
- Look for blocked items that new skills might unblock
- Look for related projects to avoid duplication

### Step 1.4: Identify Deployed Crons

Check MEMORY.md and each SKILL.md for all registered and pending cron jobs. New crons must not conflict with existing schedules.

---

## Phase 2: Design Skills

### Step 2.1: Gap Analysis

Map Allie's current capabilities into a coverage matrix:

```markdown
| Domain | Tactical Layer | Strategic Layer | Maturity |
|--------|---------------|-----------------|----------|
| [domain] | [what exists] | [what exists] | High/Med/Low/None |
```

Identify gaps where new skills would add value.

### Step 2.2: Feature Proposal

Create an artifact (`new_features.md` or similar) presenting proposed features organized by impact tier:

- **Tier 1**: High-impact, natural extensions of existing skills
- **Tier 2**: High-value new domains
- **Tier 3**: Force multipliers and quality-of-life

Each proposal should include:
- What it connects to (existing skills/data)
- Tactical layer capabilities
- Strategic layer capabilities (if applicable)
- Notion DB requirements
- Cron jobs
- Dependencies/blockers

### Step 2.3: Implementation Plan

After Jon selects features, create `implementation_plan.md` with:

1. Full Notion DB schemas (Property, Type, Details columns)
2. Module definitions with Python pseudocode
3. Cron schedules with message formats
4. Resource file specifications
5. Integration maps (READ/WRITE ownership)
6. Data collection checklist (what Jon needs to provide)
7. Verification plan

**Gate**: Request user approval before proceeding to build.

---

## Phase 3: Build Skills

### Step 3.1: Skill File Conventions

Every Allie skill follows this exact structure:

#### YAML Frontmatter
```yaml
---
name: skill-name
description: >
  Multi-line description. First sentence should be a complete summary.
  Additional sentences add context about what the skill connects to
  and what it enables.
requires:
  bins: [python3]
  pip: [optional-packages]
  env: [NOTION_API_KEY, OTHER_KEYS]
---
```

#### Required Sections (in order)

| Section | Purpose | Required? |
|---------|---------|-----------|
| Overview | Architecture diagram (ASCII), dependency chain, Notion page IDs | Yes |
| Setup (One-Time) | Step-by-step DB creation, seeding, dependency install, cron registration | Yes |
| Modules (A, B, C...) | Each with Purpose, Data Sources, Algorithm (Python pseudocode), Output format | Yes |
| Cron Automations | Numbered with prefix code, Schedule, Model, Action, Message format | Yes |
| Resource Files | Table of all files in the skill with purposes | Yes |
| Integration | READ/WRITE ownership map for all Notion databases | Yes |
| Data Collection Checklist | Items Jon must provide before full activation | If applicable |

#### Conventions

- **Notion DB schemas**: Full property tables with Property, Type, Details columns
- **Property types**: Title, Rich Text, Number (dollar/percent), Select (list Options), Multi-select, Date, Formula, Relation, Rollup, Checkbox
- **Cron naming**: Use skill-prefix codes (e.g., `HM1`, `HM2` for home-maintenance; `TX1`, `TX2` for tax-planner)
- **Model references**: `Gemini 3 Flash` for simple crons, `Kimi K2.6` for complex parsing, `DeepSeek V4 Flash` for primary agent
- **Alert channels**: Primary is Telegram. Google Chat webhook for formatted reports/cards
- **Python pseudocode**: Working algorithm code in fenced blocks — not just descriptions
- **Resource JSON**: Valid JSON with realistic seed data. No comments except `"_comment"` fields
- **Known Notion page IDs**:
  - FINANCE: `31e8275a-14ea-41b1-98c6-d3ec92de2bf9`
  - Health & Fitness: `36d63d55-66c5-8125-8c68-ee03bf91096c`
  - ALLIE: contains Project Board (`39563d55-66c5-81c3-827b-e124fc4bba17`)
  - ANTIGRAVITY: `37963d5566c581529240c6c2a34391ed`

### Step 3.2: File Locations

All skills go in: `/Users/JonCorral/Documents/Abbie/.agents/skills/<skill-name>/`

Standard layout:
```
.agents/skills/<skill-name>/
├── SKILL.md                          # Main instruction file
└── resources/                        # Data files (optional)
    ├── <config>.json
    └── <seed_data>.json
```

### Step 3.3: Parallelization Strategy

For multiple skills, use subagents to build in parallel:

1. Define a `skill_builder` subagent with write tools and the system prompt from this skill's conventions
2. Spawn one subagent per skill with a detailed prompt containing:
   - All Notion DB schemas
   - All module specifications with pseudocode requirements
   - All cron definitions
   - Resource file specifications
   - Household context data (income, filing status, etc.) if relevant
3. Track progress in a `task.md` artifact

### Step 3.4: Validation

After all files are created:

```bash
# Verify frontmatter exists
for skill in <skill-names>; do
  head -1 ".agents/skills/$skill/SKILL.md" | grep -q "^---" && echo "$skill: ✅" || echo "$skill: ❌"
done

# Validate all JSON
find .agents/skills/<skill-names> -name "*.json" | while read f; do
  python3 -c "import json; json.load(open('$f')); print('✅', '$f')" 2>&1
done

# File inventory
find .agents/skills/<skill-names> -type f | sort
```

---

## Phase 4: Transfer to Allie

Two transfer channels are available. Use the HTTP bridge (primary) when it's reachable; fall back to Notion if it's not.

### Option A: HTTP Bridge (Primary — Sub-Second)

Push skill files directly to Allie's VM via the bridge API.

**Step 4A.1: Push files**
```bash
# Push an entire skill directory
python3 scripts/bridge.py push <skill-name>

# Or push individual files
python3 scripts/bridge.py push-file .agents/skills/<skill>/SKILL.md skills/<skill>/SKILL.md
```

**Step 4A.2: Notify Allie**
```bash
python3 scripts/bridge.py send "New skill pushed: <skill-name>. Files at ~/.hermes/skills/<skill>/. Run setup from the Setup (One-Time) section." --category Task
```

**Step 4A.3: Verify**
```bash
python3 scripts/bridge.py pull skills/<skill-name>/SKILL.md  # Confirm file exists
python3 scripts/bridge.py status                              # Check system health
```

### Option B: Notion Bridge (Fallback)

Use when the HTTP bridge is unreachable (tunnel down, etc.).

1. Edit the `SKILLS` array in `scripts/push_skills_to_notion.py`
2. Run: `python3 scripts/push_skills_to_notion.py`
3. Verify: `python3 scripts/notion_bridge.py status`
4. Provide Jon with a Telegram prompt to tell Allie

---

## Phase 5: Activate on Allie

### Step 5.1: Categorize Skills by Readiness

| Bucket | Meaning | Jon's Action |
|--------|---------|-------------|
| ✅ **No blockers** | Can be set up immediately | Tell Allie to set up |
| ⏳ **Needs data** | Requires Jon to provide specific info | Fill in the data, then tell Allie |
| 🔑 **Needs credentials** | Requires API keys or OAuth setup | Set up the API access first |

### Step 5.2: Activation

**Via HTTP bridge:**
```bash
python3 scripts/bridge.py send "Install <skill-name>: create Notion DBs per schema, seed data, register crons [codes]." --category Task
```

**Via Telegram (if bridge is down):**
```
Check your inbound relay — there's a skills transfer waiting under
"📦 New Skills Transfer" in ANTIGRAVITY. Create all files, then set up
skills with no blockers: [list skills].
```

### Step 5.3: Post-Activation Verification

1. **File check**: `python3 scripts/bridge.py pull skills/<skill>/SKILL.md`
2. **Relay confirm**: `python3 scripts/bridge.py send "Confirm <skill-name> is operational" --category Query`
3. **Cron check**: `python3 scripts/bridge.py status`
4. **Dry run**: Ask Allie to execute one cron manually

---

## Quick Reference: End-to-End Checklist

```markdown
## New Allie Skill Pipeline

### Research
- [ ] Load SOUL.md, MEMORY.md, USER.md
- [ ] Inventory existing skills and crons
- [ ] Check project board for context

### Design
- [ ] Gap analysis → coverage matrix
- [ ] Feature proposal → user selects
- [ ] Implementation plan → user approves

### Build
- [ ] Create SKILL.md files (parallel subagents for multiple)
- [ ] Create resource JSON files
- [ ] Validate YAML frontmatter and JSON
- [ ] Update task tracker

### Transfer (pick one)
- [ ] **Bridge**: `python3 scripts/bridge.py push <skill-name>` + send relay
- [ ] **Notion**: Update SKILLS list → run push script → verify relay

### Activate
- [ ] Categorize by readiness
- [ ] Allie installs and sets up
- [ ] Verify files, Notion DBs, crons, dry run
- [ ] Update MEMORY.md and configs/skill_manifest.yaml
```

---

## Resource Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — pipeline instructions |
| `scripts/bridge.py` | **HTTP bridge client** — primary transfer channel |
| `scripts/.bridge_config.json` | Bridge URL + API key (gitignored) |
| `scripts/push_skills_to_notion.py` | Notion transfer script (fallback) |
| `scripts/notion_bridge.py` | Notion relay messaging (fallback) |

---

## Integration Notes

This is an **Antigravity-side skill** — it runs on Jon's Mac, not on Allie's VM.

### Communication Channels

| Channel | Latency | Use |
|---------|---------|-----|
| **HTTP Bridge** (`scripts/bridge.py`) | Sub-second | Primary — file push, relay, status |
| **Notion Relay** (`scripts/notion_bridge.py`) | Minutes-hours | Fallback when bridge is down |
| **Telegram** | Immediate | Activation prompts, blocker resolution |

### Notion Database IDs
- **Antigravity → Allie**: Inbound Relay DB (`37963d55-66c5-813f-ba47-fc8e8f5acb67`)
- **Allie → Antigravity**: Outbound Relay DB (`37963d55-66c5-8127-a0f1-f32b446d828b`)
- **Shared knowledge**: Knowledge Index DB (`37963d55-66c5-8135-9d38-f46005672025`)
- **File transfer (Notion)**: Pages under ANTIGRAVITY (`37963d5566c581529240c6c2a34391ed`)

