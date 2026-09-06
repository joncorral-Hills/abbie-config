#!/usr/bin/env python3
"""Pricing Engine for the Digital Storefront Planner.

Analyzes competitor pricing, recommends optimal price points, tracks
price changes, and suggests A/B tests for Etsy digital products.
"""

import os
import sys
import json
import re
import time
import random
import logging
import argparse
import statistics
import math
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

ETSY_BASE = "https://www.etsy.com"
SCRIPT_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = SCRIPT_DIR.parent / "resources"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("pricing_engine")


# ---------------------------------------------------------------------------
# PricingEngine
# ---------------------------------------------------------------------------


class PricingEngine:
    """End-to-end competitive pricing toolkit for Etsy digital products."""

    def __init__(self, notion_api_key: Optional[str] = None):
        self.notion_api_key = notion_api_key or os.environ.get("NOTION_API_KEY", "")
        self.notion_base = "https://api.notion.com/v1"
        self.session = requests.Session()
        self.session.headers.update({"Accept": "text/html,application/json"})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_notion_headers(self) -> dict:
        """Return Notion API auth + version headers."""
        return {
            "Authorization": f"Bearer {self.notion_api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def _safe_float(self, value: Any) -> float:
        """Coerce *value* to a float, returning 0.0 on any failure.

        Handles None, empty strings, numeric strings with whitespace,
        ints, and already-float values.
        """
        if value is None:
            return 0.0
        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if not cleaned:
                return 0.0
            try:
                return float(cleaned)
            except ValueError:
                return 0.0
        return 0.0

    def _parse_sales_estimate(self, text: str) -> int:
        """Extract a sales count from human-readable strings.

        Supports formats like:
          '1,234 sales'  → 1234
          '5.2k sales'   → 5200
          'No sales yet' → 0
        """
        if not text or not isinstance(text, str):
            return 0
        cleaned = text.strip().lower().replace(",", "")
        # Handle k/K suffix — e.g. '5.2k'
        k_match = re.search(r"([\d.]+)\s*k", cleaned)
        if k_match:
            try:
                return int(float(k_match.group(1)) * 1000)
            except ValueError:
                return 0
        # Plain integer embedded in text — e.g. '1234 sales'
        num_match = re.search(r"(\d+)", cleaned)
        if num_match:
            try:
                return int(num_match.group(1))
            except ValueError:
                return 0
        return 0

    # ------------------------------------------------------------------
    # Market Sampling
    # ------------------------------------------------------------------

    def sample_market(self, niche: str, n: int = 20) -> list[dict]:
        """Scrape the top *n* Etsy listings for *niche*.

        Returns a list of dicts with keys:
            title, price, reviews, sales_estimate, rating, shop_name
        """
        listings: list[dict] = []
        search_url = f"{ETSY_BASE}/search"
        page = 1

        while len(listings) < n:
            params = {"q": niche, "ref": "search_bar", "page": page}
            headers = {"User-Agent": random.choice(USER_AGENTS)}

            for attempt in range(1, 4):  # 3 retries
                try:
                    resp = self.session.get(
                        search_url, params=params, headers=headers, timeout=15
                    )
                    resp.raise_for_status()
                    break
                except requests.RequestException as exc:
                    logger.warning(
                        "Attempt %d for page %d failed: %s", attempt, page, exc
                    )
                    if attempt == 3:
                        logger.error("All retries exhausted for page %d", page)
                        return listings
                    time.sleep(2 * attempt)

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.v2-listing-card")
            if not cards:
                # Fallback selector for updated Etsy markup
                cards = soup.select("div[data-listing-card]")
            if not cards:
                logger.info("No more listing cards found on page %d", page)
                break

            for card in cards:
                if len(listings) >= n:
                    break

                # --- title ---
                title_el = card.select_one("h3") or card.select_one(
                    ".v2-listing-card__title"
                )
                title = title_el.get_text(strip=True) if title_el else "Unknown"

                # --- price ---
                price_el = card.select_one("span.currency-value") or card.select_one(
                    ".lc-price span"
                )
                price = self._safe_float(
                    price_el.get_text(strip=True) if price_el else "0"
                )

                # --- reviews ---
                review_el = card.select_one(
                    "span.text-body-smaller"
                ) or card.select_one(".lc-review-count")
                reviews_text = review_el.get_text(strip=True) if review_el else "0"
                reviews_match = re.search(r"([\d,]+)", reviews_text.replace(",", ""))
                reviews = int(reviews_match.group(1)) if reviews_match else 0

                # --- sales estimate ---
                sales_el = card.select_one(".v2-listing-card__shop-info span")
                sales_text = sales_el.get_text(strip=True) if sales_el else ""
                sales_estimate = self._parse_sales_estimate(sales_text)

                # --- rating ---
                rating_el = card.select_one("input[name='rating']") or card.select_one(
                    "span.v2-listing-card__rating"
                )
                if rating_el:
                    raw_rating = rating_el.get("value") or rating_el.get_text(
                        strip=True
                    )
                    rating = self._safe_float(raw_rating)
                else:
                    rating = 0.0

                # --- shop name ---
                shop_el = card.select_one(
                    "p.v2-listing-card__shop"
                ) or card.select_one(".lc-shop-name")
                shop_name = shop_el.get_text(strip=True) if shop_el else "Unknown Shop"

                listings.append(
                    {
                        "title": title,
                        "price": price,
                        "reviews": reviews,
                        "sales_estimate": sales_estimate,
                        "rating": rating,
                        "shop_name": shop_name,
                    }
                )

            page += 1
            delay = random.uniform(1, 3)
            logger.debug("Sleeping %.1fs before next page", delay)
            time.sleep(delay)

        logger.info("Sampled %d listings for niche '%s'", len(listings), niche)
        return listings

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def compute_statistics(self, prices: list[float]) -> dict:
        """Compute descriptive statistics over a list of prices.

        Filters out zeros and requires ≥ 3 remaining prices.
        """
        filtered = [p for p in prices if p > 0]
        if len(filtered) < 3:
            logger.warning(
                "Fewer than 3 non-zero prices (%d). Cannot compute stats.",
                len(filtered),
            )
            return {}

        sorted_prices = sorted(filtered)
        n = len(sorted_prices)

        def _percentile(data: list[float], pct: float) -> float:
            """Simple nearest-rank percentile."""
            idx = max(0, min(int(math.ceil(pct / 100.0 * len(data))) - 1, len(data) - 1))
            return data[idx]

        return {
            "min": sorted_prices[0],
            "max": sorted_prices[-1],
            "mean": round(statistics.mean(sorted_prices), 2),
            "median": statistics.median(sorted_prices),
            "std_dev": round(statistics.stdev(sorted_prices), 2),
            "p10": _percentile(sorted_prices, 10),
            "p25": _percentile(sorted_prices, 25),
            "p75": _percentile(sorted_prices, 75),
            "p90": _percentile(sorted_prices, 90),
            "count": n,
        }

    # ------------------------------------------------------------------
    # Price Recommendation
    # ------------------------------------------------------------------

    def recommend_price(
        self, product: dict, stats: dict, sales_count: int
    ) -> dict:
        """Return a tiered pricing recommendation.

        Tiers:
          - penetration  (sales < 10)
          - value         (10 ≤ sales ≤ 100, or >100 with rating < 4.5)
          - premium       (sales > 100 AND rating ≥ 4.5)
        """
        median = stats.get("median", 0)

        if sales_count < 10:
            tier = "penetration"
            price = round(median * 0.8, 2)
            rationale = (
                "Penetration pricing to build initial reviews and sales velocity"
            )
        elif sales_count <= 100:
            tier = "value"
            price = round(median, 2)
            rationale = "Value pricing aligned with market median"
        elif sales_count > 100 and product.get("rating", 0) >= 4.5:
            tier = "premium"
            price = round(median * 1.3, 2)
            rationale = (
                "Premium pricing leveraging strong reviews and sales history"
            )
        else:
            # >100 sales but rating < 4.5
            tier = "value"
            price = round(median, 2)
            rationale = "Value pricing aligned with market median"

        return {
            "tier": tier,
            "recommended_price": price,
            "rationale": rationale,
            "min_viable": stats.get("p10", 0),
            "max_viable": stats.get("p90", 0),
            "median_market": median,
        }

    # ------------------------------------------------------------------
    # Price Change Tracking (Notion-backed)
    # ------------------------------------------------------------------

    def track_price_change(
        self,
        listing_id: str,
        old_price: float,
        new_price: float,
        reason: str = "",
    ) -> dict:
        """Record a price change event in the Notion Price History database.

        Returns a summary dict with the change metadata.
        """
        change_pct = (
            round(((new_price - old_price) / old_price) * 100, 1)
            if old_price > 0
            else 0.0
        )
        timestamp = datetime.utcnow().isoformat() + "Z"
        db_id = os.environ.get("NOTION_PRICE_HISTORY_DB", "")

        if db_id and self.notion_api_key:
            payload = {
                "parent": {"database_id": db_id},
                "properties": {
                    "Listing ID": {"title": [{"text": {"content": listing_id}}]},
                    "Old Price": {"number": old_price},
                    "New Price": {"number": new_price},
                    "Change %": {"number": change_pct},
                    "Reason": {"rich_text": [{"text": {"content": reason}}]},
                    "Timestamp": {"date": {"start": timestamp}},
                },
            }
            try:
                resp = requests.post(
                    f"{self.notion_base}/pages",
                    headers=self._get_notion_headers(),
                    json=payload,
                    timeout=15,
                )
                resp.raise_for_status()
                change_id = resp.json().get("id", "")
                logger.info("Recorded price change %s in Notion", change_id)
            except requests.RequestException as exc:
                logger.error("Failed to write price change to Notion: %s", exc)
                change_id = ""
        else:
            logger.warning(
                "Notion credentials or NOTION_PRICE_HISTORY_DB not set — "
                "price change recorded locally only."
            )
            change_id = f"local-{int(time.time())}"

        return {
            "change_id": change_id,
            "timestamp": timestamp,
            "listing_id": listing_id,
            "old_price": old_price,
            "new_price": new_price,
            "change_pct": change_pct,
            "reason": reason,
        }

    # ------------------------------------------------------------------
    # Price Impact Evaluation
    # ------------------------------------------------------------------

    def evaluate_price_impact(self, listing_id: str, days: int = 14) -> dict:
        """Compare sales metrics before vs after the most recent price change.

        Queries the Notion Orders DB for two windows of *days* length.
        """
        orders_db = os.environ.get("NOTION_ORDERS_DB", "")
        now = datetime.utcnow()
        after_start = now - timedelta(days=days)
        before_end = after_start
        before_start = before_end - timedelta(days=days)

        views_before = 0
        views_after = 0
        sales_before = 0
        sales_after = 0

        if orders_db and self.notion_api_key:
            for label, start_dt, end_dt in [
                ("before", before_start, before_end),
                ("after", after_start, now),
            ]:
                payload = {
                    "filter": {
                        "and": [
                            {
                                "property": "Listing ID",
                                "rich_text": {"equals": listing_id},
                            },
                            {
                                "property": "Date",
                                "date": {"on_or_after": start_dt.isoformat() + "Z"},
                            },
                            {
                                "property": "Date",
                                "date": {"on_or_before": end_dt.isoformat() + "Z"},
                            },
                        ]
                    }
                }
                try:
                    resp = requests.post(
                        f"{self.notion_base}/databases/{orders_db}/query",
                        headers=self._get_notion_headers(),
                        json=payload,
                        timeout=15,
                    )
                    resp.raise_for_status()
                    results = resp.json().get("results", [])
                    period_sales = len(results)
                    period_views = sum(
                        r.get("properties", {})
                        .get("Views", {})
                        .get("number", 0)
                        or 0
                        for r in results
                    )
                    if label == "before":
                        sales_before = period_sales
                        views_before = period_views
                    else:
                        sales_after = period_sales
                        views_after = period_views
                except requests.RequestException as exc:
                    logger.error(
                        "Error querying Notion orders (%s window): %s", label, exc
                    )
        else:
            logger.warning(
                "Notion credentials or NOTION_ORDERS_DB not set — "
                "returning zeroed impact data."
            )

        conversion_before = (
            round(sales_before / views_before * 100, 2) if views_before > 0 else 0.0
        )
        conversion_after = (
            round(sales_after / views_after * 100, 2) if views_after > 0 else 0.0
        )

        revenue_before = sales_before  # proxy: count-based
        revenue_after = sales_after
        revenue_change_pct = (
            round(((revenue_after - revenue_before) / revenue_before) * 100, 1)
            if revenue_before > 0
            else 0.0
        )

        if revenue_change_pct > 0:
            recommendation = (
                "Revenue improved after the price change. "
                "Consider keeping the new price point."
            )
        elif revenue_change_pct < 0:
            recommendation = (
                "Revenue declined after the price change. "
                "Consider reverting or testing an intermediate price."
            )
        else:
            recommendation = (
                "No measurable revenue change. "
                "Extend the observation window or test a more significant adjustment."
            )

        return {
            "listing_id": listing_id,
            "period_days": days,
            "views_before": views_before,
            "views_after": views_after,
            "sales_before": sales_before,
            "sales_after": sales_after,
            "conversion_before": conversion_before,
            "conversion_after": conversion_after,
            "revenue_change_pct": revenue_change_pct,
            "recommendation": recommendation,
        }

    # ------------------------------------------------------------------
    # A/B Test Suggestion
    # ------------------------------------------------------------------

    def suggest_ab_test(self, listing_id: str, current_price: float) -> dict:
        """Generate an A/B pricing test plan for a listing."""
        variant_a = round(current_price * 0.85, 2)
        variant_b = round(current_price * 1.15, 2)
        return {
            "listing_id": listing_id,
            "current_price": current_price,
            "variant_a": variant_a,
            "variant_b": variant_b,
            "test_duration_days": 14,
            "success_metric": "revenue_per_view",
            "notes": (
                f"Test ${variant_a:.2f} vs ${variant_b:.2f} over 14 days. "
                "Track revenue per view as primary metric."
            ),
        }

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def generate_pricing_report(self, niche: str, sample_size: int = 20) -> str:
        """Sample the market and produce a Markdown pricing report."""
        listings = self.sample_market(niche, n=sample_size)
        prices = [l["price"] for l in listings]
        stats = self.compute_statistics(prices)

        today = datetime.utcnow().strftime("%Y-%m-%d")

        if not stats:
            return (
                f"# Pricing Report — {niche}\n\n"
                f"_Generated {today}_\n\n"
                "**Insufficient data** — fewer than 3 non-zero prices found.\n"
            )

        # Build recommendation examples for each tier
        pen = self.recommend_price({}, stats, sales_count=0)
        val = self.recommend_price({}, stats, sales_count=50)
        prem = self.recommend_price({"rating": 4.8}, stats, sales_count=200)

        report = f"""# Pricing Report — {niche}

_Generated {today}_

---

## Market Overview

| Metric        | Value           |
|---------------|-----------------|
| Niche         | {niche}         |
| Sample Size   | {stats['count']} listings |
| Date          | {today}         |

---

## Price Distribution

| Statistic   | Value    |
|-------------|----------|
| Min         | ${stats['min']:.2f}  |
| Max         | ${stats['max']:.2f}  |
| Median      | ${stats['median']:.2f} |
| Mean        | ${stats['mean']:.2f}  |
| Std Dev     | ${stats['std_dev']:.2f} |

---

## Percentile Analysis

| Percentile | Price    |
|------------|----------|
| P10        | ${stats['p10']:.2f}  |
| P25        | ${stats['p25']:.2f}  |
| P75        | ${stats['p75']:.2f}  |
| P90        | ${stats['p90']:.2f}  |

---

## Pricing Recommendations

### 🟢 Penetration Tier (< 10 sales)
- **Recommended Price:** ${pen['recommended_price']:.2f}
- **Rationale:** {pen['rationale']}

### 🟡 Value Tier (10–100 sales)
- **Recommended Price:** ${val['recommended_price']:.2f}
- **Rationale:** {val['rationale']}

### 🔵 Premium Tier (> 100 sales, ≥ 4.5★)
- **Recommended Price:** ${prem['recommended_price']:.2f}
- **Rationale:** {prem['rationale']}

---

## Next Steps

1. **Identify your tier** based on current sales volume and rating.
2. **Set your price** within the recommended range (${stats['p10']:.2f} – ${stats['p90']:.2f}).
3. **Track changes** with `--track` to log every price update.
4. **Run A/B tests** with `--ab-test` to validate assumptions.
5. **Re-evaluate** after 14 days using `--recommend` with updated data.
"""
        return report


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def run_tests() -> bool:
    """Execute built-in self-tests. Return True if all pass."""
    engine = PricingEngine()
    passed = 0
    failed = 0

    def _assert(label: str, condition: bool, detail: str = ""):
        nonlocal passed, failed
        if condition:
            passed += 1
            logger.info("✓ %s", label)
        else:
            failed += 1
            logger.error("✗ %s — %s", label, detail)

    # -- test_statistics --
    prices = [5.99, 7.99, 9.99, 12.99, 14.99]
    st = engine.compute_statistics(prices)
    _assert("stats_median", st["median"] == 9.99, f"got {st.get('median')}")
    _assert("stats_min", st["min"] == 5.99, f"got {st.get('min')}")
    _assert("stats_max", st["max"] == 14.99, f"got {st.get('max')}")
    _assert("stats_count", st["count"] == 5, f"got {st.get('count')}")

    # -- test_penetration_pricing --
    rec = engine.recommend_price({}, st, sales_count=0)
    expected_pen = round(9.99 * 0.8, 2)
    _assert(
        "penetration_tier",
        rec["tier"] == "penetration",
        f"got {rec['tier']}",
    )
    _assert(
        "penetration_price",
        rec["recommended_price"] == expected_pen,
        f"got {rec['recommended_price']} expected {expected_pen}",
    )

    # -- test_value_pricing --
    rec = engine.recommend_price({}, st, sales_count=50)
    _assert("value_tier", rec["tier"] == "value", f"got {rec['tier']}")
    _assert(
        "value_price",
        rec["recommended_price"] == round(9.99, 2),
        f"got {rec['recommended_price']}",
    )

    # -- test_premium_pricing --
    rec = engine.recommend_price({"rating": 4.8}, st, sales_count=200)
    expected_prem = round(9.99 * 1.3, 2)
    _assert("premium_tier", rec["tier"] == "premium", f"got {rec['tier']}")
    _assert(
        "premium_price",
        rec["recommended_price"] == expected_prem,
        f"got {rec['recommended_price']} expected {expected_prem}",
    )

    # -- test_ab_test_variants --
    ab = engine.suggest_ab_test("test-123", 9.99)
    _assert(
        "ab_variant_a",
        ab["variant_a"] == round(9.99 * 0.85, 2),
        f"got {ab['variant_a']}",
    )
    _assert(
        "ab_variant_b",
        ab["variant_b"] == round(9.99 * 1.15, 2),
        f"got {ab['variant_b']}",
    )

    # -- test_safe_float --
    _assert("safe_float_none", engine._safe_float(None) == 0.0)
    _assert("safe_float_empty", engine._safe_float("") == 0.0)
    _assert("safe_float_abc", engine._safe_float("abc") == 0.0)
    _assert("safe_float_str", engine._safe_float("5.99") == 5.99)
    _assert("safe_float_int", engine._safe_float(10) == 10.0)

    # -- test_parse_sales --
    _assert(
        "parse_sales_comma",
        engine._parse_sales_estimate("1,234 sales") == 1234,
        f"got {engine._parse_sales_estimate('1,234 sales')}",
    )
    _assert(
        "parse_sales_k",
        engine._parse_sales_estimate("5.2k sales") == 5200,
        f"got {engine._parse_sales_estimate('5.2k sales')}",
    )
    _assert(
        "parse_sales_none",
        engine._parse_sales_estimate("No sales") == 0,
        f"got {engine._parse_sales_estimate('No sales')}",
    )

    total = passed + failed
    logger.info("Tests complete: %d/%d passed", passed, total)
    return failed == 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Competitive pricing engine for Etsy digital products."
    )
    parser.add_argument(
        "--analyze",
        metavar="NICHE",
        help="Scrape and display raw market data for NICHE.",
    )
    parser.add_argument(
        "--recommend",
        metavar="PRODUCT_ID",
        help="Generate a pricing recommendation for PRODUCT_ID.",
    )
    parser.add_argument(
        "--track",
        metavar="LISTING_ID",
        help="Record a price change for LISTING_ID (requires --old-price & --new-price).",
    )
    parser.add_argument("--old-price", type=float, help="Previous price (for --track).")
    parser.add_argument("--new-price", type=float, help="New price (for --track).")
    parser.add_argument("--reason", default="", help="Reason for price change.")
    parser.add_argument(
        "--ab-test",
        metavar="LISTING_ID",
        help="Suggest an A/B pricing test for LISTING_ID.",
    )
    parser.add_argument(
        "--current-price",
        type=float,
        help="Current price of the listing (for --ab-test).",
    )
    parser.add_argument(
        "--report",
        metavar="NICHE",
        help="Generate a full pricing report for NICHE.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="Number of listings to sample (default: 20).",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable debug logging."
    )
    parser.add_argument(
        "--test", action="store_true", help="Run built-in self-tests."
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # --- Test mode ---
    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)

    engine = PricingEngine()

    # --- Analyze ---
    if args.analyze:
        listings = engine.sample_market(args.analyze, n=args.sample_size)
        prices = [l["price"] for l in listings]
        stats = engine.compute_statistics(prices)
        print(json.dumps({"listings": listings, "statistics": stats}, indent=2))
        return

    # --- Report ---
    if args.report:
        report = engine.generate_pricing_report(args.report, sample_size=args.sample_size)
        print(report)
        return

    # --- Recommend ---
    if args.recommend:
        # Fetch product from Notion or use placeholder
        product = {"id": args.recommend, "rating": 4.5}
        sample = engine.sample_market("digital download", n=args.sample_size)
        prices = [l["price"] for l in sample]
        stats = engine.compute_statistics(prices)
        if not stats:
            print("Error: insufficient market data for recommendation.")
            sys.exit(1)
        rec = engine.recommend_price(product, stats, sales_count=0)
        print(json.dumps(rec, indent=2))
        return

    # --- Track ---
    if args.track:
        if args.old_price is None or args.new_price is None:
            print("Error: --track requires --old-price and --new-price.")
            sys.exit(1)
        result = engine.track_price_change(
            args.track, args.old_price, args.new_price, reason=args.reason
        )
        print(json.dumps(result, indent=2))
        return

    # --- A/B Test ---
    if args.ab_test:
        if args.current_price is None:
            print("Error: --ab-test requires --current-price.")
            sys.exit(1)
        plan = engine.suggest_ab_test(args.ab_test, args.current_price)
        print(json.dumps(plan, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
