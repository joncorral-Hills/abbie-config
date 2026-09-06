---
name: digital-storefront-automation
description: >
  Tactical automation layer for the Corral digital product business on Etsy.
  Owns all Notion databases, Etsy API integration, product file management,
  order/revenue sync, mockup generation, and listing health monitoring.
  Feeds data to the digital-storefront-planner skill for strategic analysis.
requires:
  bins: [python3, curl]
  env:
    - NOTION_API_KEY
    - ETSY_API_KEY
    - ETSY_SHARED_SECRET
    - ETSY_SHOP_ID
    - NOTION_DB_SHOP_CONFIG
    - NOTION_DB_PRODUCT_IDEAS
    - NOTION_DB_PRODUCTS
    - NOTION_DB_LISTINGS
    - NOTION_DB_ORDERS
    - NOTION_DB_SEO_KEYWORDS
    - NOTION_DB_SNAPSHOTS
    - GOOGLE_CHAT_WEBHOOK_BUSINESS
---

# Digital Storefront Automation

> **Layer**: Tactical (data collection & sync)
> **Owner**: Allie (Hermes Agent)
> **Platform**: Etsy (API v3)
> **Data Store**: Notion (7 databases)
> **Alerts**: Google Chat (webhook cards)

---

## Overview

This skill provides six core capabilities for managing a digital product
business on Etsy:

| # | Capability | Description |
|---|-----------|-------------|
| 1 | **Etsy API Client** | Full OAuth 2.0 PKCE auth, rate-limited API calls, token management |
| 2 | **Product File Manager** | Directory structure, ZIP packaging, SHA-256 versioning |
| 3 | **Mockup Generator** | PIL-based compositing with 3 templates (default, device, lifestyle) |
| 4 | **Listing CRUD** | Create/read/update/delete listings, image & file uploads |
| 5 | **Order & Revenue Sync** | Delta sync, full fee engine, daily/monthly aggregation |
| 6 | **Listing Health Monitor** | Views, favorites, conversion rate analysis, health scoring |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ALLIE (Hermes Agent)                        │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Cron Jobs   │  │  CLI Entry   │  │  Planner Skill (Future)  │  │
│  │  B1/B2/B3    │  │  Points      │  │  Strategy & Decisions    │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
│         │                 │                        │                │
│  ┌──────▼─────────────────▼────────────────────────▼─────────────┐  │
│  │                  Skill Scripts Layer                           │  │
│  │                                                               │  │
│  │  ┌─────────────────┐ ┌──────────────────┐ ┌───────────────┐  │  │
│  │  │  etsy_client.py  │ │ product_manager  │ │ revenue_sync  │  │  │
│  │  │  ─ EtsyAuth      │ │ ─ ProductManager │ │ ─ RevenueSync │  │  │
│  │  │  ─ EtsyClient    │ │ ─ ZIP/Hash/Mock  │ │ ─ Fee Engine  │  │  │
│  │  │  ─ NotionSync     │ │                  │ │ ─ Milestones  │  │  │
│  │  └────────┬──────────┘ └────────┬─────────┘ └───────┬───────┘  │  │
│  └───────────┼─────────────────────┼───────────────────┼─────────┘  │
│              │                     │                   │            │
└──────────────┼─────────────────────┼───────────────────┼────────────┘
               │                     │                   │
    ┌──────────▼──────────┐  ┌───────▼────────┐  ┌──────▼──────────┐
    │    Etsy API v3      │  │  ~/digital-    │  │  Google Chat    │
    │  openapi.etsy.com   │  │  products/     │  │  Webhook        │
    └──────────┬──────────┘  │  (filesystem)  │  └─────────────────┘
               │             └────────────────┘
    ┌──────────▼──────────┐
    │   Notion API v1     │
    │   7 Databases       │
    │  ┌───────────────┐  │
    │  │ Shop Config   │  │
    │  │ Product Ideas │  │
    │  │ Products      │  │
    │  │ Listings      │  │
    │  │ Orders        │  │
    │  │ SEO Keywords  │  │
    │  │ Biz Snapshots │  │
    │  └───────────────┘  │
    └─────────────────────┘
```

---

## Setup

### Step 1: Create Notion BUSINESS Page

Create a top-level page named **BUSINESS** in the Allie workspace. All 7
databases will live as children of this page.

### Step 2: Create Notion Databases

Use the schemas defined in `resources/notion_schema.json` to create these
databases inside the BUSINESS page:

1. **⚙️ Shop Config** — Key-value store for shop settings
2. **💡 Product Ideas** — Idea backlog and triage
3. **📦 Products** — Master product catalog
4. **🏪 Listings** — Etsy listing mirror
5. **🧾 Orders** — Order/receipt records with fee breakdown
6. **🔍 SEO Keywords** — Keyword research and tracking
7. **📊 Business Snapshots** — Daily/weekly/monthly metrics

After creating each database, copy its Database ID and set the corresponding
environment variable (see `requires.env` above).

### Step 3: Create Etsy Developer App

1. Go to https://www.etsy.com/developers/your-apps
2. Create a new app with name "Allie Storefront Manager"
3. Note the **API Key** (keystring) and **Shared Secret**
4. Set redirect URI to `http://localhost:8080/callback`

### Step 4: Run OAuth Flow

```bash
python3 scripts/etsy_client.py --test
```

On first run, this will:
- Generate PKCE challenge
- Print authorization URL
- Start a local callback server on port 8080
- Exchange the code for access + refresh tokens
- Store tokens at `~/.hermes/secrets/etsy_tokens.json`

### Step 5: Verify Token Storage

```bash
cat ~/.hermes/secrets/etsy_tokens.json | python3 -m json.tool
```

Confirm `access_token`, `refresh_token`, and `expires_at` are present.

### Step 6: Install Python Dependencies

```bash
pip install requests Pillow
```

### Step 7: Deploy Cron Jobs

Add the following to Allie's cron schedule (see Cron Automations section below).

---

## Module A: Etsy API Client

**File**: `scripts/etsy_client.py`

### Authentication (EtsyAuth)

| Feature | Details |
|---------|---------|
| Flow | OAuth 2.0 Authorization Code with PKCE (S256) |
| Token Storage | `~/.hermes/secrets/etsy_tokens.json` |
| Auto-Refresh | On 401 response, refreshes token and retries once |
| PKCE Method | SHA-256 code challenge, base64url-encoded |

### API Client (EtsyClient)

| Feature | Details |
|---------|---------|
| Rate Limiter | Token bucket, 10 requests/second |
| Retry Logic | 3 attempts, exponential backoff (1s, 2s, 4s) |
| Error Handling | Raises typed exceptions for 4xx/5xx |

### Endpoints

| Method | Etsy API Endpoint |
|--------|-------------------|
| `get_shop(shop_id)` | `GET /application/shops/{shop_id}` |
| `list_listings(shop_id)` | `GET /application/shops/{shop_id}/listings` |
| `get_listing(listing_id)` | `GET /application/listings/{listing_id}` |
| `create_listing(shop_id, data)` | `POST /application/shops/{shop_id}/listings` |
| `update_listing(shop_id, listing_id, data)` | `PUT /application/shops/{shop_id}/listings/{listing_id}` |
| `delete_listing(listing_id)` | `DELETE /application/listings/{listing_id}` |
| `upload_listing_image(...)` | `POST /application/shops/{shop_id}/listings/{listing_id}/images` |
| `upload_listing_file(...)` | `POST /application/shops/{shop_id}/listings/{listing_id}/files` |
| `get_transactions(shop_id)` | `GET /application/shops/{shop_id}/transactions` |
| `get_receipts(shop_id)` | `GET /application/shops/{shop_id}/receipts` |
| `get_listing_images(listing_id)` | `GET /application/listings/{listing_id}/images` |
| `get_listing_files(listing_id)` | `GET /application/listings/{listing_id}/files` |

### Notion Sync (NotionSync)

| Method | Description |
|--------|-------------|
| `query_database(db_id, filter)` | Paginated query with filter object |
| `create_page(db_id, properties)` | Create new page in database |
| `update_page(page_id, properties)` | Update existing page properties |
| `upsert_by_unique(db_id, prop, val, properties)` | Query by unique field, create or update |
| `sync_listing(listing_data)` | Map Etsy listing fields → Notion Listings DB |
| `sync_order(order_data)` | Map Etsy receipt fields → Notion Orders DB |

---

## Module B: Product File Manager

**File**: `scripts/product_manager.py`

### Directory Structure

```
~/digital-products/
├── minimalist-wall-art-set/
│   ├── metadata.json
│   ├── source/              # Original editable files (PSD, AI, etc.)
│   ├── deliverables/        # Customer-facing files (PDF, PNG, SVG)
│   ├── mockups/             # Generated mockup images
│   │   ├── default_mockup.png
│   │   ├── device_mockup.png
│   │   └── lifestyle_mockup.png
│   └── minimalist-wall-art-set.zip
├── budget-planner-2026/
│   ├── metadata.json
│   ├── source/
│   ├── deliverables/
│   ├── mockups/
│   └── budget-planner-2026.zip
└── ...
```

### Mockup Templates

| Template | Dimensions | Description |
|----------|-----------|-------------|
| `default` | 2000×2000 | White background, product centered, drop shadow |
| `device` | 2000×1500 | Tablet/iPad frame overlay, product on screen |
| `lifestyle` | 2400×1600 | Desk scene background, product at slight angle |

### metadata.json Schema

```json
{
  "slug": "minimalist-wall-art-set",
  "display_name": "Minimalist Wall Art Set",
  "category": "Printable Art",
  "status": "draft",
  "created_at": "2026-07-14T10:00:00Z",
  "updated_at": "2026-07-14T10:00:00Z",
  "price": null,
  "tags": [],
  "description": "",
  "file_hash": null,
  "package_path": null,
  "package_date": null,
  "etsy_listing_id": null,
  "notion_page_id": null,
  "mockup_paths": {},
  "deliverable_count": 0,
  "version": 1
}
```

### Status Flow

```
draft → needs_mockup → ready → listed → paused → archived
                                  ↑         │
                                  └─────────┘
```

---

## Module C: Listing Manager

Listing management is handled by the `EtsyClient` class combined with
`NotionSync`. The workflow for listing a product:

### Field Mapping (Product → Etsy Listing)

| Product Field | Etsy API Field | Notes |
|---------------|----------------|-------|
| `display_name` | `title` | Max 140 characters |
| `description` | `description` | Supports basic HTML |
| `price` | `price` | In cents (multiply by 100) |
| `tags` | `tags` | Array, max 13 tags |
| `category` | `taxonomy_id` | Map via `etsy_taxonomy.json` |
| — | `who_made` | Always `"i_did"` |
| — | `is_digital` | Always `true` |
| — | `when_made` | Always `"2020_2026"` |
| — | `is_supply` | Always `false` |

### Image Pipeline

1. Generate mockups via `product_manager.py --mockup`
2. Upload primary mockup as rank 1 image
3. Upload additional mockups as rank 2, 3, ...
4. Upload deliverable preview images if available

### Listing Status Flow

```
draft → active → inactive → expired → removed
         ↑  ↓
         sold_out
```

---

## Module D: Order & Revenue Sync

**File**: `scripts/revenue_sync.py`

### Delta Sync

Orders are synced incrementally using a watermark timestamp stored in
`~/.hermes/state/storefront/revenue_sync_state.json`.

```json
{
  "last_sync_timestamp": "2026-07-14T10:00:00Z",
  "last_receipt_id": 1234567890,
  "total_orders_synced": 0,
  "total_revenue_synced": 0.0
}
```

### Fee Engine

Every order is processed through the full Etsy fee engine:

| Fee | Rate | Applies To |
|-----|------|-----------|
| Listing Fee | $0.20 flat | Per listing |
| Transaction Fee | 6.5% | Total sale price |
| Processing (domestic) | 3% + $0.25 | Total sale price |
| Processing (international) | 4% + $0.25 | Total sale price |
| Offsite Ads | 15% | Order total (if from ad) |
| Regulatory | 0.25% | Total sale price |

**Example**: $12.99 sale (domestic, no offsite ad)

| Fee | Amount |
|-----|--------|
| Listing | $0.20 |
| Transaction (6.5%) | $0.84 |
| Processing (3% + $0.25) | $0.64 |
| Regulatory (0.25%) | $0.03 |
| **Total Fees** | **$1.71** |
| **Net Revenue** | **$11.28** |

### Daily Aggregation

Aggregates all orders for a given date into a Business Snapshot:
- Total orders
- Gross revenue
- Total fees
- Net revenue
- Top selling product

### Milestone Detection

| Threshold | Milestone Label |
|-----------|----------------|
| 1 order | 🎉 First Sale! |
| 10 orders | 📦 10 Orders |
| 25 orders | 📦 25 Orders |
| 50 orders | 📦 50 Orders |
| 100 orders | 💯 100 Orders |
| 250 orders | 🚀 250 Orders |
| 500 orders | 🌟 500 Orders |
| 1000 orders | 👑 1,000 Orders |
| $100 revenue | 💵 $100 Revenue |
| $500 revenue | 💰 $500 Revenue |
| $1,000 revenue | 🤑 $1K Revenue |
| $5,000 revenue | 💎 $5K Revenue |
| $10,000 revenue | 🏆 $10K Revenue |
| $50,000 revenue | 🚀 $50K Revenue |

Milestones trigger a Google Chat card alert via the `GOOGLE_CHAT_WEBHOOK_BUSINESS`
webhook.

---

## Notion Database Schemas

Full schemas are defined in `resources/notion_schema.json`. Summary below:

### ⚙️ Shop Config (7 properties)

| Property | Type | Description |
|----------|------|-------------|
| Key | Title | Configuration key name |
| Value | Rich Text | Configuration value |
| Category | Select | API / Shop / Billing / Notifications / Sync |
| Sensitive | Checkbox | If true, value stored as pointer |
| Last Updated | Date | Last modification date |
| Updated By | Select | Allie / Jon / System |
| Notes | Rich Text | Additional context |

### 💡 Product Ideas (10 properties)

| Property | Type | Description |
|----------|------|-------------|
| Idea | Title | Short product idea name |
| Description | Rich Text | Detailed concept description |
| Category | Select | Printable Art / Planner / SVG / Template / ... |
| Priority | Select | 🔴 High / 🟡 Medium / 🟢 Low |
| Status | Select | 💭 Brainstorm / 📋 Researching / ✅ Approved / 🚀 In Production / ❌ Rejected |
| Market Research | Rich Text | Competitor analysis, demand signals |
| Target Price | Number ($) | Estimated selling price |
| Estimated Effort | Select | < 1 hour / 1-4 hours / 4-8 hours / > 8 hours |
| Source | Select | Jon / Allie Research / Trend Alert / Customer Request |
| Created | Created Time | Auto-set |

### 📦 Products (10 properties)

| Property | Type | Description |
|----------|------|-------------|
| Name | Title | Product display name |
| Slug | Rich Text | URL-safe identifier |
| Category | Select | Printable Art / Planner / SVG / ... |
| Status | Select | 🛠️ Draft / 📸 Needs Mockup / ✅ Ready / 🚀 Listed / ⏸️ Paused / 🗄️ Archived |
| File Path | Rich Text | Absolute path on filesystem |
| File Hash | Rich Text | SHA-256 of deliverable ZIP |
| Etsy Listing ID | Number | Linked Etsy listing ID |
| Price | Number ($) | Selling price |
| Tags | Multi-Select | Product tags |
| Last Modified | Last Edited Time | Auto-set |

### 🏪 Listings (13 properties)

| Property | Type | Description |
|----------|------|-------------|
| Title | Title | Etsy listing title (max 140 chars) |
| Listing ID | Number | Etsy listing_id |
| Product | Relation → Products | Link to product catalog |
| Status | Select | draft / active / inactive / sold_out / expired / removed |
| Price | Number ($) | Listed price |
| Views | Number | Total views |
| Favorites | Number | Total favorites |
| Sales | Number | Units sold |
| Conversion Rate | Number (%) | Sales / Views |
| Tags | Rich Text | Comma-separated (max 13) |
| Taxonomy ID | Number | Etsy category ID |
| Last Synced | Date | Last sync timestamp |
| Health Score | Select | 🟢 Good / 🟡 Needs Attention / 🔴 Poor |

### 🧾 Orders (11 properties)

| Property | Type | Description |
|----------|------|-------------|
| Order ID | Title | Etsy receipt_id as string |
| Receipt ID | Number | Etsy receipt_id (numeric) |
| Listing | Relation → Listings | Link to listing |
| Buyer | Rich Text | Buyer display name |
| Gross Revenue | Number ($) | Total paid by buyer |
| Etsy Fees | Number ($) | Total fees |
| Net Revenue | Number ($) | Gross - Fees |
| Offsite Ad | Checkbox | From offsite ad? |
| Order Date | Date | Order timestamp |
| Status | Select | Paid / Completed / Refunded / Cancelled |
| Country | Rich Text | Buyer's country |

### 🔍 SEO Keywords (7 properties)

| Property | Type | Description |
|----------|------|-------------|
| Keyword | Title | Search keyword/phrase |
| Category | Select | Primary / Secondary / Long Tail / Trending / Competitor |
| Search Volume | Select | 🔥 High / 📈 Medium / 📉 Low |
| Competition | Select | High / Medium / Low |
| Used In Listings | Relation → Listings | Listings using this keyword |
| Performance Notes | Rich Text | Observations |
| Last Reviewed | Date | Last evaluation date |

### 📊 Business Snapshots (11 properties)

| Property | Type | Description |
|----------|------|-------------|
| Period | Title | Date string or range |
| Period Type | Select | Daily / Weekly / Monthly |
| Total Orders | Number | Order count |
| Gross Revenue | Number ($) | Total revenue |
| Total Fees | Number ($) | Total Etsy fees |
| Net Revenue | Number ($) | After fees |
| Total Views | Number | Listing views |
| Total Favorites | Number | Hearts |
| Conversion Rate | Number (%) | Sales / Views |
| Active Listings | Number | Active listing count |
| Top Product | Rich Text | Best seller |

---

## Cron Automations

### B1: Daily Sales Sync

| Field | Value |
|-------|-------|
| Schedule | Daily at 11:00 PM CT |
| Cron | `0 23 * * *` |
| Model | `deepseek-v4-flash` |
| Script | `scripts/revenue_sync.py --sync` |
| Fallback | `scripts/revenue_sync.py --full-sync` |

**What it does:**
1. Delta-syncs new orders from Etsy since last run
2. Calculates fee breakdown for each order
3. Upserts orders into Notion Orders DB
4. Aggregates daily totals into Business Snapshots
5. Checks for milestone achievements
6. Sends milestone alerts to Google Chat if triggered

### B2: Listing Health Check

| Field | Value |
|-------|-------|
| Schedule | Monday & Thursday at 9:00 AM CT |
| Cron | `0 9 * * 1,4` |
| Model | `deepseek-v4-flash` |
| Script | `scripts/etsy_client.py --shop-info` + custom analysis |

**What it does:**
1. Fetches all active listings from Etsy
2. Syncs views, favorites, sales counts to Notion Listings DB
3. Calculates conversion rate for each listing
4. Assigns health scores:
   - 🟢 Good: Conversion > 2% or < 30 days old
   - 🟡 Needs Attention: Conversion 0.5-2% and > 30 days
   - 🔴 Poor: Conversion < 0.5% and > 60 days
5. Alerts on any newly 🔴 Poor listings

### B3: Product Upload Monitor

| Field | Value |
|-------|-------|
| Schedule | Daily at 8:00 AM CT |
| Cron | `0 8 * * *` |
| Model | `deepseek-v4-flash` |
| Script | `scripts/product_manager.py --check-updates` |

**What it does:**
1. Scans `~/digital-products/` for all products
2. Computes current file hashes and compares vs stored
3. Flags products with changed deliverables
4. Updates Notion Products DB with new hash and status
5. Alerts on products that changed but aren't re-listed

---

## Integration Points

| System | Direction | What |
|--------|-----------|------|
| Etsy API v3 | ← Read | Shop data, listings, orders, receipts |
| Etsy API v3 | → Write | Create/update listings, upload images/files |
| Notion API | ← Read | Product metadata, keyword lists, config |
| Notion API | → Write | Sync listings, orders, snapshots, products |
| Google Chat | → Write | Milestone alerts, health warnings |
| Filesystem | ↔ R/W | Product files, ZIPs, mockups, metadata |
| digital-storefront-planner | → Feed | Revenue data, listing health, product status |

---

## Files

| File | Purpose | Lines |
|------|---------|-------|
| `SKILL.md` | This skill definition document | — |
| `scripts/etsy_client.py` | Etsy OAuth + API client + Notion sync | ~700 |
| `scripts/product_manager.py` | Product files, packaging, mockups | ~450 |
| `scripts/revenue_sync.py` | Order sync, fees, aggregation, milestones | ~400 |
| `resources/etsy_taxonomy.json` | Digital product category taxonomy IDs | — |
| `resources/etsy_fee_schedule.json` | Complete Etsy fee structure | — |
| `resources/notion_schema.json` | All 7 Notion database schemas | — |
