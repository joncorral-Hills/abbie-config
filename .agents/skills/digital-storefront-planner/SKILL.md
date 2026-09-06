---
name: digital-storefront-planner
description: >
  Strategic planning layer for the Corral digital storefront. Handles niche
  research and validation, product ideation and concept generation, SEO keyword
  optimization, competitive pricing strategy, business health scoring, and the
  autonomous growth loop. Reads from the automation layer's Notion databases
  (Products, Orders, Listings, Analytics) but only writes to Product Ideas and
  SEO Keywords which it co-owns.
requires:
  bins: [python3]
  env: [NOTION_API_KEY]
---

# Digital Storefront Planner

## Overview

The strategic intelligence layer that drives the Corral digital storefront. While the
automation layer (digital-storefront-automation) handles the operational plumbing —
Etsy API sync, order fulfillment, listing management — this skill is the BRAIN that
decides *what* to sell, *how* to optimize it, and *when* to act.

### Six Core Capabilities

1. **Niche Research Engine** — Discovers profitable digital product niches through
   trend scanning, demand scoring, competition analysis, and profitability estimation
2. **Product Ideation Pipeline** — Generates product concepts by analyzing competitor
   gaps, customer pain points, and market opportunities
3. **SEO & Keyword Optimizer** — Researches keywords, audits listing quality, and
   generates optimized titles/tags/descriptions
4. **Pricing Strategy** — Analyzes competitor pricing, recommends optimal price points,
   and suggests A/B tests
5. **Business Intelligence & Health Score** — Computes a composite health score from
   6 weighted metrics and generates monthly business reviews
6. **Autonomous Growth Loop** — Orchestrates the full pipeline from niche discovery
   to listing publication with human-in-the-loop approval gates

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    DIGITAL STOREFRONT PLANNER                          │
│                      (Strategic Layer)                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────────────┐      │
│  │  Web Search   │   │ Etsy Search  │   │  Notion (read-only)    │      │
│  │  (Trends)     │   │ (Competitors)│   │  Products, Orders,     │      │
│  └──────┬───────┘   └──────┬───────┘   │  Listings, Analytics   │      │
│         │                  │           └──────────┬─────────────┘      │
│         ▼                  ▼                      ▼                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │              NICHE RESEARCH ENGINE (Module A)                   │   │
│  │  trend scan → demand score → competition → profitability        │   │
│  └───────────────────────┬─────────────────────────────────────────┘   │
│                          ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │           PRODUCT IDEATION PIPELINE (Module B)                  │   │
│  │  competitor gaps → concept gen → feasibility scoring            │   │
│  └───────────────────────┬─────────────────────────────────────────┘   │
│                          ▼                                             │
│  ┌───────────────┐ ┌────────────────┐ ┌─────────────────────┐         │
│  │ SEO Optimizer │ │ Pricing Engine │ │  Product Creator    │         │
│  │  (Module C)   │ │  (Module D)    │ │  (Module B cont.)  │         │
│  └───────┬───────┘ └───────┬────────┘ └────────┬────────────┘         │
│          │                 │                   │                       │
│          ▼                 ▼                   ▼                       │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │         BUSINESS INTELLIGENCE (Module E)                        │   │
│  │  6 metrics → composite health score → monthly review            │   │
│  └───────────────────────┬─────────────────────────────────────────┘   │
│                          ▼                                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │          AUTONOMOUS GROWTH LOOP (Module F)                      │   │
│  │  niche scan → ideate → create → optimize → price →             │   │
│  │  [APPROVE] → publish → monitor                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                          │                                             │
│                          ▼                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────────┐         │
│  │  Notion       │ │ Google Chat  │ │     Telegram           │         │
│  │  (write:      │ │ (alerts)     │ │  (approval gates)      │         │
│  │  Ideas, SEO)  │ │              │ │                        │         │
│  └──────────────┘ └──────────────┘ └────────────────────────┘         │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Setup

### Prerequisites

1. **Verify automation layer is deployed** — The `digital-storefront-automation` skill
   must be installed and its Notion databases (Products, Orders, Listings, Analytics)
   must exist before deploying this planner.

2. **Install Python dependencies**:
   ```bash
   pip install requests beautifulsoup4 fpdf2 Pillow openpyxl svgwrite weasyprint jinja2
   ```

3. **Deploy cron jobs B4–B8** — Register the 5 planner crons with Hermes:
   ```bash
   hermes cron add B4-weekly-niche-scout
   hermes cron add B5-seo-audit
   hermes cron add B6-monthly-business-review
   hermes cron add B7-competitor-watch
   hermes cron add B8-growth-loop-trigger
   ```

4. **Run initial niche scan** to populate the Product Ideas database:
   ```bash
   python3 scripts/niche_researcher.py --scan
   ```

## Module A: Niche Research Engine

The niche research engine discovers and scores digital product niches through a
5-step analytical pipeline.

### Pipeline

1. **Trend Scanning** — Scrapes trending searches, social media trends, and seasonal
   patterns to identify emerging product opportunities
2. **Demand Scoring** — Estimates monthly search volume and buyer intent for each
   niche using search autocomplete analysis and listing count proxies
3. **Competition Analysis** — Counts competing listings, analyzes top sellers' review
   counts, pricing strategies, and listing quality
4. **Profitability Estimation** — Calculates expected margins based on average pricing,
   production cost (time × hourly rate), and listing fees
5. **Niche Scoring** — Computes a weighted composite score (0–100) using configurable
   weights from `resources/niche_scoring_weights.json`

### Scoring Weights

| Factor           | Weight | Description                                      |
|------------------|--------|--------------------------------------------------|
| Demand           | 0.30   | Search volume and buyer interest signals         |
| Low Competition  | 0.25   | Inverse of market saturation                     |
| Profit Margin    | 0.25   | Expected revenue minus costs per unit            |
| Trend Momentum   | 0.20   | 90-day growth trajectory                         |

### Score Interpretation

| Score Range | Label          | Action                                      |
|-------------|----------------|---------------------------------------------|
| 75–100      | High Potential  | Prioritize immediately — begin product dev  |
| 60–74       | Validated       | Strong candidate — queue for next cycle     |
| 40–59       | Marginal        | Monitor trends — revisit in 30 days         |
| 25–39       | Weak            | Low priority — only if unique angle exists  |
| 0–24        | Reject          | Do not pursue                               |

### Script

```bash
python3 scripts/niche_researcher.py --scan          # Full trend scan
python3 scripts/niche_researcher.py --score "planners"  # Score specific niche
python3 scripts/niche_researcher.py --report         # Generate research report
python3 scripts/niche_researcher.py --test           # Run self-test
```

## Module B: Product Ideation Pipeline

Generates actionable product concepts by analyzing market gaps and matching them
to our production capabilities.

### Pipeline

1. **Competitor Analysis** — Studies top-selling products in target niches to identify
   what's working (high reviews, consistent sales)
2. **Gap Identification** — Finds underserved segments: missing styles, formats,
   themes, or quality levels
3. **Concept Generation** — Creates detailed product concepts with name, description,
   features, target audience, and estimated price
4. **Feasibility Scoring** — Rates each concept on creation complexity, tool
   availability, estimated time, and profit potential

### Supported Product Types

| Product Type           | Tool      | Format | Complexity | Typical Price |
|------------------------|-----------|--------|------------|---------------|
| Printable Planner      | fpdf2     | PDF    | Medium     | $3.99–$12.99  |
| SVG Cut File           | svgwrite  | SVG    | Low        | $1.99–$5.99   |
| Spreadsheet Template   | openpyxl  | XLSX   | Medium     | $5.99–$19.99  |
| Social Media Template  | Pillow    | PNG    | Medium     | $4.99–$14.99  |
| Printable Wall Art     | Pillow    | PNG    | Low        | $2.99–$9.99   |
| Resume Template        | WeasyPrint| PDF    | High       | $7.99–$19.99  |
| Checklist / Worksheet  | fpdf2     | PDF    | Low        | $1.99–$5.99   |
| Digital Sticker Pack   | Pillow    | PNG    | Medium     | $2.99–$7.99   |

### Script

```bash
python3 scripts/product_creator.py --create '{"name": "Weekly Meal Planner", ...}'
python3 scripts/product_creator.py --mockup /path/to/product.pdf
python3 scripts/product_creator.py --list-types
python3 scripts/product_creator.py --test
```

## Module C: SEO & Keyword Optimizer

Researches keywords and audits listing quality to maximize Etsy search visibility.

### Keyword Research Pipeline

1. **Seed Expansion** — Takes a seed keyword and expands via autocomplete suggestions,
   related searches, and category analysis
2. **Keyword Scoring** — Scores each keyword on relevance, estimated volume, and
   competition level
3. **Tag Selection** — Picks the optimal 13 tags from the scored keyword pool using
   a diversity-aware selection algorithm
4. **Title Optimization** — Generates SEO-optimized titles that front-load primary
   keywords while remaining natural and readable

### Listing Audit Scoring (0–100)

| Factor        | Max Points | Key Criteria                              |
|---------------|------------|-------------------------------------------|
| Title         | 25         | Keyword position, length, readability     |
| Tags          | 20         | All 13 used, multi-word, diverse          |
| Description   | 20         | 300+ words, structured, keyword-rich      |
| Images        | 20         | 8+ images, mockups, detail shots          |
| Attributes    | 15         | Category, occasion, style filled          |

### Script

```bash
python3 scripts/seo_optimizer.py --research "planner printable"
python3 scripts/seo_optimizer.py --audit <listing_id>
python3 scripts/seo_optimizer.py --audit-all
python3 scripts/seo_optimizer.py --optimize <listing_id>
python3 scripts/seo_optimizer.py --test
```

## Module D: Pricing Strategy

Analyzes competitor pricing and recommends optimal price points based on market
position, sales volume, and customer ratings.

### Competitive Analysis

Samples 20 competing products in the same niche to build a price distribution:
- Median price, mean price, price range (P10–P90)
- Price-to-review correlation
- Premium indicator signals (high price + high reviews)

### Pricing Tiers

| Tier         | Trigger Condition            | Formula          | Rationale                     |
|--------------|------------------------------|------------------|-------------------------------|
| Penetration  | < 10 sales                   | 0.8 × median     | Undercut to build reviews     |
| Value        | 10–100 sales                 | 1.0 × median     | Match market expectations     |
| Premium      | 100+ sales, 4.5+ rating      | 1.3 × median     | Leverage social proof         |

### Price Tracking

Logs every price change with timestamp, reason, and old/new values to enable
impact analysis after 14-day observation windows.

### A/B Testing

Suggests price variants for split testing: typically ±15% from current price.
Tracks conversion rate changes across the test period.

### Script

```bash
python3 scripts/pricing_engine.py --analyze "planner printable"
python3 scripts/pricing_engine.py --recommend <product_id>
python3 scripts/pricing_engine.py --test
```

## Module E: Business Intelligence & Health Score

Computes a composite business health score from 6 weighted metrics and generates
monthly business reviews.

### Health Score Metrics

| Metric             | Weight | Target     | Unit            |
|--------------------|--------|------------|-----------------|
| Revenue Growth     | 0.25   | 15% MoM    | percent_mom     |
| Conversion Rate    | 0.20   | 3.0%       | percent         |
| Avg Order Value    | 0.15   | $10.00     | usd             |
| Review Rating      | 0.15   | 4.8 stars  | stars           |
| Listing Quality    | 0.15   | 80/100     | score_0_100     |
| Product Diversity  | 0.10   | 5 categories| categories     |

### Score Interpretation

| Score | Label      | Description                                          |
|-------|------------|------------------------------------------------------|
| 80–100| Thriving   | Performing excellently — focus on scaling             |
| 60–79 | Growing    | Solid foundation — target weakest metrics             |
| 40–59 | Developing | Early stage — focus on fundamentals                   |
| 0–39  | Critical   | Urgent attention — core fundamentals need work        |

### Monthly Report Format

The monthly business review includes:
- Executive summary with health score and trend
- Metric-by-metric breakdown with sparkline trends
- Top performing products (by revenue and conversion)
- Underperforming products (candidates for optimization or sunset)
- Competitive position analysis
- Prioritized recommendations
- Next month's goals and targets

## Module F: Autonomous Growth Loop

Orchestrates the complete pipeline from niche discovery to listing publication,
with human-in-the-loop approval gates at critical decision points.

### 8-Step Pipeline

```
  ┌──────────────┐
  │ 1. NICHE     │ Scan trending niches, score & rank
  │    SCAN      │
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 2. PRODUCT   │ Generate concepts for top niches
  │    IDEATION  │
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 3. FEASIBIL- │ Score complexity, time, profit potential
  │    ITY CHECK │
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 4. CREATE    │ ← APPROVAL GATE (Telegram)
  │    PRODUCT   │   Generate files, mockups, metadata
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 5. OPTIMIZE  │ SEO title, tags, description
  │    LISTING   │
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 6. SET       │ Market-based price recommendation
  │    PRICE     │
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 7. PUBLISH   │ ← APPROVAL GATE (Telegram)
  │    LISTING   │   Create draft on Etsy
  └──────┬───────┘
         ▼
  ┌──────────────┐
  │ 8. MONITOR   │ Track performance for 30 days
  │    PERFORM.  │
  └──────────────┘
```

### Approval Gates

- **CREATE** (Step 4): Jon must approve product creation via Telegram before
  generation begins. Includes niche score, product type, and estimated price.
- **LIST** (Step 7): Jon must review the complete listing (title, tags, price,
  mockup) via Telegram before it goes live on Etsy.
- **PRICE CHANGE**: Auto-approved if change is ≤20%. Larger changes require
  Telegram approval.
- **SUNSET**: Removing a product always requires explicit approval.

### Loop Settings

- Maximum 2 new products per growth cycle
- Minimum niche score of 60 to proceed
- Minimum 90 days active before considering sunset
- Minimum SEO score of 70 before publishing
- 7-day cooldown between cycles

## Cron Automations

| Job ID | Name                  | Schedule          | Model              | Description                                           |
|--------|-----------------------|-------------------|--------------------|---------------------------------------------------------|
| B4     | Weekly Niche Scout    | Sun 10:00 AM CT   | sonnet-4.6         | Full niche scan with trend analysis and scoring         |
| B5     | SEO Audit             | Wed 9:00 AM CT    | deepseek-v4-flash  | Audit all active listings, flag scores < 70             |
| B6     | Monthly Business Review| 1st of month 10AM | sonnet-4.6         | Compute health score, generate monthly report           |
| B7     | Competitor Watch      | 1st & 15th 8:00 AM| deepseek-v4-flash  | Monitor competitor pricing and new product launches     |
| B8     | Growth Loop Trigger   | Sat 11:00 AM CT   | sonnet-4.6         | Execute autonomous growth loop pipeline                 |

### B4: Weekly Niche Scout
```
Schedule: 0 10 * * 0 (Sunday 10:00 AM)
Model: sonnet-4.6
Pipeline:
  1. Scan Google Trends, Etsy trending, social media for emerging niches
  2. Score each niche using the 4-factor weighted model
  3. Compare against existing Product Ideas database to avoid duplicates
  4. Save top-scoring niches to Notion Product Ideas DB
  5. Alert via Google Chat with summary of top 5 opportunities
```

### B5: SEO Audit
```
Schedule: 0 9 * * 3 (Wednesday 9:00 AM)
Model: deepseek-v4-flash
Pipeline:
  1. Pull all active listings from Notion Listings DB
  2. Audit each listing against SEO best practices (5 factors, 100 points)
  3. Generate specific recommendations for listings scoring < 70
  4. Save audit results and recommendations to Notion SEO Keywords DB
  5. Alert via Google Chat with audit summary and action items
```

### B6: Monthly Business Review
```
Schedule: 0 10 1 * * (1st of month 10:00 AM)
Model: sonnet-4.6
Pipeline:
  1. Pull 30-day metrics from Notion Analytics and Orders DBs
  2. Compute composite health score from 6 weighted metrics
  3. Compare against previous month and identify trends
  4. Rank products by revenue and conversion rate
  5. Generate comprehensive monthly report
  6. Post executive summary to Google Chat
  7. Save full report to Notion
```

### B7: Competitor Watch
```
Schedule: 0 8 1,15 * * (1st and 15th at 8:00 AM)
Model: deepseek-v4-flash
Pipeline:
  1. Search Etsy for top sellers in our active niches
  2. Track new product launches from tracked competitors
  3. Monitor pricing changes and promotional patterns
  4. Identify emerging product formats or styles
  5. Alert via Google Chat with competitive intelligence summary
```

### B8: Growth Loop Trigger
```
Schedule: 0 11 * * 6 (Saturday 11:00 AM)
Model: sonnet-4.6
Pipeline:
  1. Check if cooldown period has elapsed since last cycle
  2. Check if under max active products limit
  3. Pull top-scoring niches from Product Ideas DB
  4. Execute growth loop pipeline (steps 1-8)
  5. Handle approval gates via Telegram
  6. Report results via Google Chat
```

## Integration

| System                 | Direction | Purpose                                      |
|------------------------|-----------|----------------------------------------------|
| Notion Product Ideas   | Read/Write| Store and retrieve niche research results    |
| Notion SEO Keywords    | Read/Write| Store keyword research and audit results     |
| Notion Products DB     | Read      | Current product catalog and metadata         |
| Notion Orders DB       | Read      | Sales data for health scoring                |
| Notion Listings DB     | Read      | Active listings for SEO auditing             |
| Notion Analytics DB    | Read      | Traffic and conversion metrics               |
| Google Chat            | Write     | Alerts, reports, and notifications           |
| Telegram               | Read/Write| Approval gates for growth loop               |
| Etsy (via web search)  | Read      | Competitor analysis and trend discovery      |
| Google Trends (proxy)  | Read      | Trend momentum signals                       |

## Files

| File                                    | Purpose                                    |
|-----------------------------------------|--------------------------------------------|
| `SKILL.md`                              | This skill definition                      |
| `scripts/niche_researcher.py`           | Niche discovery and scoring engine         |
| `scripts/seo_optimizer.py`              | SEO keyword research and listing auditor   |
| `scripts/pricing_engine.py`             | Competitive pricing analysis and strategy  |
| `scripts/product_creator.py`            | Digital product generation factory         |
| `resources/niche_scoring_weights.json`  | Niche scoring weights and thresholds       |
| `resources/product_type_capabilities.json`| Product type definitions and metadata    |
| `resources/business_health_weights.json`| Health score metrics and benchmarks        |
| `resources/seo_best_practices.json`     | Etsy SEO rules and scoring criteria        |
| `resources/growth_loop_config.json`     | Growth loop pipeline and approval gates    |
