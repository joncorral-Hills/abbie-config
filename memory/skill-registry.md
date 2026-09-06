# Skill & Cron Job Registry

## Notion SKILLS Database
- **Database ID**: `36d63d55-66c5-8116-8444-d17011cad076`
- **Parent Page**: ALLIE (`36d63d55-66c5-8163-8bc9-c438cb43ce3b`)
- **Schema**: Name (title), Instructions (rich_text), Trigger (rich_text), Model Tier (select), Use Count (number), Last Used (date)

## Backed-Up Skills (9 total)

| Skill | Notion Page ID | Local Path | Model Tier |
|-------|---------------|------------|------------|
| billing-dispute-ai | `36d63d55-66c5-81fa-9688-d56d6c72f45b` | `.agents/skills/billing-dispute-ai/` | Kimi K2.6 |
| financial-automation | `36d63d55-66c5-8136-8609-eb0ea386550c` | `.agents/skills/financial-automation/` | Kimi K2.6 |
| first-aid-triage | `36d63d55-66c5-810d-9a96-d5ef1cc8ed7d` | `.agents/skills/first-aid-triage/` | Gemini 3 Flash |
| hills-pet-writer | `36d63d55-66c5-81de-bf5d-f198b0f003f1` | `.agents/skills/hills-pet-writer/` | Gemini 3 Flash |
| invention-processor | `36d63d55-66c5-817b-8c2c-eb0f77308922` | `.agents/skills/invention-processor/` | Kimi K2.6 |
| marketing-core | `36d63d55-66c5-8152-b932-dee4299744cb` | `.agents/skills/marketing-core/` | Gemini 3 Flash |
| parametric-3d-printing | `36d63d55-66c5-812b-b0ac-cdedf297c3a2` | `.agents/skills/parametric-3d-printing/` | Gemini 3 Flash |
| patent-prior-art-scout | `36d63d55-66c5-815d-b81f-dde7614e0d63` | `.agents/skills/patent-prior-art-scout/` | Kimi K2.6 |
| travel-planner | `36d63d55-66c5-81b1-9179-e0360466deae` | `.agents/skills/travel-planner/` | Kimi K2.6 |

## Financial Automation Cron Jobs (7 total)

| Job | Schedule | Model | Job ID |
|-----|----------|-------|--------|
| Daily Financial Pulse | Daily 8:00 AM | Gemini 3 Flash | `d10a21296ef2` |
| Statement Import Queue | Every 6 hours | Kimi K2.6 | `18990ce3b9a3` |
| Transaction Categorization | Daily 9:00 AM | Gemini 3 Flash | `3a9b42ecc25f` |
| Weekly Budget Variance | Mondays 8:00 AM | Kimi K2.6 | `9705c439bfba` |
| Monthly Subscription Audit | 1st of month, 8:00 AM | Kimi K2.6 | `c03fe9e99da7` |
| Weekly Financial Health | Sundays 8:00 AM | Gemini 3 Flash | `339230f00715` |
| Monthly Budget Rollover | 1st of month, 9:00 AM | Kimi K2.6 | `24dcd4399a17` |

## Key Notion Database IDs

| Database | ID |
|----------|-----|
| Accounts | `36c63d55-66c5-81ff-a3c9-ef453408dcf6` |
| Categories | `36c63d55-66c5-81f4-9cba-eee6dbdaa9b4` |
| Budgets | `36c63d55-66c5-81a0-ab42-c60697006b2f` |
| Transactions | `36c63d55-66c5-8107-b787-fc7c20d5be04` |
| Statements | `36c63d55-66c5-8176-b0ff-f1f9eb50f321` |
| INVENT | `ff59713b-9715-470d-98f8-f957e56f3850` |
| SKILLS | `36d63d55-66c5-8116-8444-d17011cad076` |
| FINANCE (parent page) | `31e8275a-14ea-41b1-98c6-d3ec92de2bf9` |

## OpenRouter Credit Tracking

| Script | Purpose | Path |
|--------|---------|------|
| `openrouter_credits.py` | Check balance, log usage, alert thresholds | `/home/ubuntu/scripts/openrouter_credits.py` |
| `openrouter_weekly_report.py` | Generate weekly spending report with projections | `/home/ubuntu/scripts/openrouter_weekly_report.py` |

| Cron Job | Schedule | Model | Job ID |
|----------|----------|-------|--------|
| openrouter-credit-check | Daily 9:00 AM | Gemini 3 Flash | `0192a69455c1` |
| openrouter-weekly-report | Sundays 9:00 AM | Gemini 3 Flash | `13d795f27371` |

## Last Updated
2026-05-27
