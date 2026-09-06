---
name: invention-processor
description: >
  Detects, captures, and analyzes invention ideas via #invent tag or explicit 
  mention. Performs IP novelty screening and market viability analysis, 
  cross-references against existing ideas in the Notion INVENT database, and 
  provides structured improvement suggestions.
requires:
  bins: [python3, pip]
  env: [NOTION_API_KEY]
---

# Invention Idea Processor

## Overview

This skill enables Abbie to function as Jon's invention idea processor:
1. **Trigger Detection**: Recognizes `#invent` tags or explicit invention language
2. **Idea Capture**: Creates structured entries in the Notion INVENT database
3. **IP Novelty Screen**: Web search + LLM analysis for prior art and conflicts
4. **Market Viability**: Competitive landscape, market sizing, monetization paths
5. **Cross-Reference**: Compares against all existing ideas, suggests improvements

---

## Trigger Detection

### Primary Triggers (always activate)
- Message contains `#invent` tag (case-insensitive)
- Message contains "invention idea" or "I have an invention" (case-insensitive)

### Secondary Triggers (activate if context supports it)
- "idea for a product"
- "idea for an app"
- "what if we built"
- "what if there was a"
- "patent idea"
- "new product concept"

### Detection Regex
```
Primary:  (?i)#invent|invention\s+idea|i\s+have\s+an\s+invention
Secondary: (?i)idea\s+for\s+a\s+(product|app|device|service|tool)|what\s+if\s+we\s+built|what\s+if\s+there\s+was|patent\s+idea|new\s+product\s+concept
```

### On Detection
1. Extract the core idea from the message (strip conversational fluff, greetings, etc.)
2. Acknowledge: `💡 Invention idea detected. Capturing and analyzing...`
3. Proceed to the Processing Pipeline

---

## Notion Database

- **Database ID**: `ff59713b-9715-470d-98f8-f957e56f3850`
- **Parent Page**: INVENT (shared with Abbie's integration)

### Schema Discovery

Before first use, run the schema discovery step:
```bash
python3 .agents/skills/invention-processor/scripts/notion_invent.py schema
```

This reads the live database schema and outputs the property map. The script 
adapts to whatever properties exist. If key properties are missing, it will 
note what to add manually in Notion.

### Recommended Properties

If adding properties to the INVENT database, these are ideal:

| Property | Type | Purpose |
|----------|------|---------|
| Name | Title | Idea name/title |
| Description | Rich Text | One-paragraph summary |
| Category | Select | See `resources/idea_categories.json` |
| Status | Select | New → Analyzed → Refined → Parked → Pursuing |
| IP Score | Number | 1-10 novelty assessment |
| Market Score | Number | 1-10 viability assessment |
| Related Ideas | Relation | Links to similar ideas in same DB |
| Date Added | Date | When the idea was captured |
| Tags | Multi-select | Free-form tags for filtering |

If these properties don't exist, the skill stores all analysis in the page body.

---

## Processing Pipeline

### Step 1: DETECT & CAPTURE
- **Model**: Kimi K2.6 (default)
- **Action**:
  1. Parse the idea from the user's message
  2. Generate a concise title (5-10 words max)
  3. Generate a one-paragraph description
  4. Create a Notion page in the INVENT database:
     - Set title property to the generated name
     - Set Description (if property exists) to the paragraph summary
     - Set Status = "New" (if property exists)
     - Set Category (if property exists) using `resources/idea_categories.json`
     - Set Date Added = today (if property exists)
  5. Store the raw user input as the first block in the page body
  6. Respond: `💡 Captured: "[Idea Title]" — running IP and market analysis...`

### Step 2: IP NOVELTY SCREEN
- **Model**: Sonnet 4.6 (mid-tier — requires reasoning + web search)
- **Action**:
  1. Generate 3-5 targeted search queries using templates from `resources/ip_search_queries.json`
  2. Search the web for:
     - Existing patents (Google Patents, patent databases)
     - Existing products or services that solve the same problem
     - Academic research or prior art
  3. Analyze findings with LLM:
     - **Novelty Score** (1-10): How original is this idea?
       - 1-3: Heavily patented / many existing products
       - 4-6: Some prior art exists but differentiation possible
       - 7-10: Highly novel, minimal prior art found
     - **Key Differentiators**: What makes this idea unique vs. existing solutions?
     - **Potential Conflicts**: Specific patents or products that overlap
     - **Freedom to Operate Notes**: High-level assessment (NOT legal advice)
  4. Update the Notion page:
     - Set IP Score property (if exists)
     - Append IP analysis section to page body using `resources/analysis_template.md`

### Step 3: MARKET VIABILITY
- **Model**: Sonnet 4.6 (mid-tier)
- **Action**:
  1. Search the web for:
     - Market size and growth trends for the problem domain
     - Direct and indirect competitors
     - Target audience demographics
     - Industry trends and timing
  2. Analyze findings with LLM:
     - **Market Score** (1-10): How viable is this commercially?
       - 1-3: Niche market, heavy competition, unclear demand
       - 4-6: Moderate market with some competition
       - 7-10: Large/growing market, clear demand, gap exists
     - **Target Audience**: Who would buy/use this?
     - **Competitors**: Top 3-5 existing solutions
     - **Monetization Paths**: How could this make money?
     - **Timing Assessment**: Is the market ready for this?
  3. Update the Notion page:
     - Set Market Score property (if exists)
     - Append market analysis section to page body

### Step 4: CROSS-REFERENCE
- **Model**: Kimi K2.6 (default — comparing text, not deep reasoning)
- **Action**:
  1. Fetch all existing ideas from the INVENT database:
     ```bash
     python3 .agents/skills/invention-processor/scripts/notion_invent.py list
     ```
  2. For each existing idea, compare semantic similarity to the new idea
  3. Identify:
     - **Overlapping ideas**: Ideas solving a similar problem
     - **Synergies**: Ideas that could combine to create something stronger
     - **Contradictions**: Ideas that conflict or compete with each other
     - **Technology Reuse**: Shared components or infrastructure
  4. If the INVENT database has a "Related Ideas" relation property, link them
  5. Append cross-reference section to page body

### Step 5: IMPROVEMENT SUGGESTIONS
- **Model**: Sonnet 4.6 (mid-tier — creative synthesis)
- **Action**:
  1. Based on all analysis from Steps 2-4, generate actionable improvements:
     - **Technical improvements**: Better approaches, materials, architectures
     - **Market positioning**: Niche-down, pivot angle, unique selling proposition
     - **Combination plays**: Merge with existing ideas from the database
     - **Risk mitigation**: How to navigate IP conflicts found
     - **MVP definition**: Smallest viable version to test the idea
  2. Append improvement section to page body
  3. Set Status = "Analyzed" (if property exists)

### Step 6: REPORT
- **Model**: Kimi K2.6 (default)
- **Action**:
  1. Compose a concise summary message with:
     - Idea title
     - IP Score and one-line summary
     - Market Score and one-line summary
     - Top 2-3 improvement suggestions
     - Link to the Notion page
  2. Send via Google Chat (if webhook configured)
  3. Reply to the user with the summary

---

## Error Handling

- **Notion API failure**: Log error, store analysis locally in 
  `memory/invention_backlog.json`, retry on next heartbeat
- **Web search failure**: Skip that section, note "Web search unavailable" in 
  the report, still complete LLM-only analysis
- **Database schema mismatch**: Fall back to page-body-only mode (no property 
  writes), log warning for Jon to review
- **Rate limiting**: If Notion returns 429, exponential backoff (1s, 2s, 4s, max 30s)

---

## Manual Commands

Jon can also trigger analysis manually:

- `Analyze idea: [description]` — Same as #invent but without the tag
- `Review all ideas` — Re-run cross-reference on entire INVENT database
- `Refresh idea: [name]` — Re-run IP + Market analysis on an existing idea
- `List ideas` — Show all ideas with scores from INVENT database

---

## Important Disclaimers

Every analysis report MUST include this footer:

> ⚠️ **Disclaimer**: This analysis is AI-generated and does not constitute legal 
> or financial advice. IP novelty scores are based on publicly searchable 
> information and may miss unpublished patents or trade secrets. Consult a 
> patent attorney for formal freedom-to-operate assessments.

---

## Files in This Skill

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — instructions and architecture |
| `scripts/notion_invent.py` | Notion API operations (CRUD, schema discovery) |
| `resources/analysis_template.md` | Structured report template for page body |
| `resources/ip_search_queries.json` | Patent and product search query templates |
| `resources/idea_categories.json` | Idea taxonomy for auto-categorization |
