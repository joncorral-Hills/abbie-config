---
name: work-ops
description: >
  Professional life management — career goals, salary and benefits tracking, project notes
  from monday.com, idea capture, and copy generation from tickets. Use when the user mentions
  work goals, salary, raise, benefits, 401k, projects, monday.com, work ideas, 'create copy
  from this ticket', 'what are my work goals', 'track my salary', 'work projects', 'Hill's',
  or any professional career management topic.
requires:
  env: [NOTION_API_KEY]
---

# Work Ops Skill

Manages Jon's professional life at Hill's Pet Nutrition (Colgate-Palmolive). Tracks career goals,
compensation, projects, and generates marketing copy from monday.com tickets.

## 1. Career Goal Tracking

Track short and long-term professional development goals.

### Notion: Goals
| Property | Type | Description |
|----------|------|-------------|
| Goal | Title | e.g. "AWS Solutions Architect certification" |
| Category | Select | `Career Advancement`, `Skill Development`, `Certification`, `Leadership`, `Financial`, `Networking` |
| Priority | Select | `P1 - Critical`, `P2 - High`, `P3 - Medium`, `P4 - Nice to Have` |
| Status | Select | `Not Started`, `In Progress`, `Blocked`, `Completed`, `Deferred` |
| Target Date | Date | When this should be achieved |
| Progress | Number | 0-100% completion |
| Key Results | Text | Measurable outcomes that define "done" |
| Blockers | Text | What's preventing progress |
| Notes | Text | Strategy, resources, context |
| Date Created | Date | When goal was set |
| Date Completed | Date | When goal was achieved |

## 2. Compensation Tracking

Track salary history, benefits, and total compensation.

### Notion: Compensation
| Property | Type | Description |
|----------|------|-------------|
| Period | Title | e.g. "2026 H2", "2025 Annual" |
| Base Salary | Number | Annual base salary |
| Bonus Target | Number | Target bonus percentage |
| Bonus Actual | Number | Actual bonus received |
| 401k Match | Text | Match formula (e.g. "100% of first 6%") |
| 401k Contribution | Text | Current contribution rate |
| Vesting Schedule | Text | Stock/RSU vesting details if applicable |
| Benefits Value | Number | Estimated annual benefits value (health, dental, vision, life, disability) |
| Total Comp | Formula | Base + Bonus Actual + Benefits Value |
| Review Date | Date | Next performance review |
| Merit Increase | Number | Last merit increase percentage |
| Notes | Text | Review feedback, negotiation notes |

### Jon's Current Compensation Context
- **Employer**: Hill's Pet Nutrition (Colgate-Palmolive subsidiary)
- **Location**: Kansas City metro
- **Domain**: Data Engineering / AI-ML / Cloud Architecture
- **Pay Schedule**: Biweekly, $2,860 gross per period
- **Annual Base**: ~$74,360 (estimated from biweekly)
- **401k**: TBD — needs to be recorded
- **Review Cycle**: Annual (date TBD)

> **NOTE**: Salary and compensation data is PII. When this skill is invoked, ensure the
> model is appropriate for sensitive data. If running on gemini-local, limit responses to
> Notion DB operations and avoid sending raw salary figures through the model.

## 3. Project Tracking

Track active work projects and their status.

### Notion: Projects
| Property | Type | Description |
|----------|------|-------------|
| Project Name | Title | Human-readable project name |
| Status | Select | `Planning`, `In Progress`, `On Hold`, `Completed`, `Cancelled` |
| Priority | Select | `P1`, `P2`, `P3`, `P4` |
| Description | Text | What the project accomplishes |
| Monday.com Link | URL | Link to monday.com board/item |
| Monday.com ID | Text | monday.com item ID for API access |
| Start Date | Date | Project kickoff |
| Target Date | Date | Expected completion |
| Stakeholders | Text | Key people involved |
| My Role | Text | Jon's specific responsibilities |
| Key Deliverables | Text | What Jon is expected to produce |
| Notes | Text | Meeting notes, decisions, blockers |
| Last Updated | Date | When this entry was last touched |

## 4. Work Ideas

Capture professional ideas — process improvements, tool suggestions, architecture proposals.

### Notion: Work Ideas
| Property | Type | Description |
|----------|------|-------------|
| Idea | Title | Short description |
| Category | Select | `Process Improvement`, `Architecture`, `Tool/Platform`, `Automation`, `Team/Culture`, `Product`, `Other` |
| Status | Select | `Captured`, `Evaluating`, `Proposed`, `Approved`, `Implemented`, `Rejected` |
| Impact | Select | `High`, `Medium`, `Low` |
| Effort | Select | `Small`, `Medium`, `Large`, `XL` |
| Description | Text | Full idea description and rationale |
| Proposed To | Text | Who this was shared with |
| Outcome | Text | What happened when proposed |
| Date Captured | Date | When the idea was first recorded |

## 5. Monday.com Integration

### API Setup
```
Base URL: https://api.monday.com/v2
Auth: Authorization: $MONDAY_API_KEY
Method: POST (GraphQL)
```

### Query Assigned Items
```graphql
query {
  boards(ids: [BOARD_ID]) {
    items_page(limit: 25, query_params: {
      rules: [{column_id: "person", compare_value: [JON_USER_ID]}]
    }) {
      items {
        id
        name
        column_values {
          id
          text
          value
        }
      }
    }
  }
}
```

### Copy Generation from Tickets
When Jon says "create copy from this ticket" or "write copy for [ticket name]":

1. Fetch the monday.com item by ID or name search
2. Extract: title, description, status, column values
3. Generate appropriate copy based on the item type:
   - **Marketing brief** → Draft copy following Hill's brand voice
   - **Technical spec** → Summarize into stakeholder-friendly language
   - **Bug report** → Draft customer-facing explanation
   - **Feature request** → Draft announcement/changelog entry

> **IMPORTANT**: Follow Hill's Pet Nutrition copywriting guidelines if available from
> the work-context-handoff bridge. Alfred (GravityClaw) maintains Hill's brand voice rules.

## 6. Alfred Bridge Context

The `work-context-handoff` skill pushes Jon's work context from Alfred (GravityClaw, his
work agent) to Allie's Notion workspace. This includes:
- Current meetings and schedule
- Active projects and priorities
- Copywriting rules and brand guidelines
- Team dynamics and org context

When processing work-related queries, check the Alfred handoff page for fresh context.

## 7. Notion DB Setup

On first activation:
1. Create "Work Life" page under Allie's workspace
2. Create 4 child databases: Goals, Compensation, Projects, Work Ideas
3. Seed Compensation with current known data
4. Store page ID and DB IDs in `resources/notion_ids.json`

## 8. Cross-Bot Communication
- `message_agent(target="finance-bot")` or `finance-bot chat -q "..."` for:
  - Salary/tax impact analysis ("If I get a 5% raise, what's the net monthly impact?")
  - Benefits valuation against market rates
  - 401k contribution optimization

## 9. Routing

| Request Pattern | Action |
|----------------|--------|
| "What are my work goals?" | Query Goals DB |
| "Track my salary" | Query/update Compensation DB |
| "What projects am I working on?" | Query Projects DB |
| "Create copy from [ticket]" | Fetch monday.com item → generate copy |
| "Add a work idea" | Create Work Ideas entry |
| "When's my next review?" | Check Compensation DB review date |
| "What did Alfred say about work?" | Check work-context-handoff Notion page |
| "How much PTO do I have?" | Check benefits tracking (if configured) |
