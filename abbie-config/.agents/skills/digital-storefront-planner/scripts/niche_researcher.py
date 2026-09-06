#!/usr/bin/env python3
"""Niche Research Engine for the Digital Storefront Planner.

Discovers and scores digital product niches by analyzing trends, demand,
competition, and profitability. Produces ranked niche recommendations
for product ideation.
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
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SEEDS = [
    "planner",
    "wall art",
    "wedding",
    "budget tracker",
    "resume template",
    "social media template",
    "checklist",
    "SVG cut file",
    "digital sticker",
    "spreadsheet template",
]

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

ETSY_BASE = "https://www.etsy.com"

SCRIPT_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = SCRIPT_DIR.parent / "resources"

logger = logging.getLogger("niche_researcher")

# ---------------------------------------------------------------------------
# Default scoring weights & tier tables
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS: dict[str, float] = {
    "demand": 0.30,
    "competition": 0.25,
    "profitability": 0.25,
    "momentum": 0.20,
}

DEMAND_TIERS: list[dict] = [
    {"min": 50000, "score": 95, "label": "Explosive"},
    {"min": 20000, "score": 80, "label": "High"},
    {"min": 5000, "score": 60, "label": "Moderate"},
    {"min": 1000, "score": 40, "label": "Low"},
    {"min": 0, "score": 20, "label": "Very Low"},
]

COMPETITION_TIERS: list[dict] = [
    {"max": 500, "score": 90, "label": "Low Competition"},
    {"max": 2000, "score": 70, "label": "Moderate Competition"},
    {"max": 10000, "score": 50, "label": "Competitive"},
    {"max": 50000, "score": 30, "label": "Highly Competitive"},
    {"max": float("inf"), "score": 15, "label": "Saturated"},
]

PROFITABILITY_TIERS: list[dict] = [
    {"min": 15.0, "score": 95, "label": "High Margin"},
    {"min": 8.0, "score": 75, "label": "Good Margin"},
    {"min": 3.0, "score": 55, "label": "Moderate Margin"},
    {"min": 1.0, "score": 35, "label": "Thin Margin"},
    {"min": 0.0, "score": 15, "label": "Unprofitable"},
]

OVERALL_THRESHOLDS: list[tuple[int, str]] = [
    (80, "🔥 Hot Niche"),
    (65, "✅ Promising"),
    (50, "⚠️ Moderate"),
    (0, "❌ Weak"),
]

# =========================================================================
# EtsySearchAnalyzer
# =========================================================================


class EtsySearchAnalyzer:
    """Scrapes and parses Etsy search results for niche analysis."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
            }
        )

    # ----- helpers --------------------------------------------------------

    def _make_request(self, url: str) -> Optional[BeautifulSoup]:
        """GET *url* with random UA, polite delay, and retry logic.

        Returns parsed ``BeautifulSoup`` or ``None`` on total failure.
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                delay = random.uniform(1.0, 3.0)
                time.sleep(delay)
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                resp = self.session.get(url, headers=headers, timeout=15)
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1) + random.uniform(0, 1)
                    logger.warning(
                        "Rate-limited (429). Backing off %.1fs (attempt %d/%d)",
                        wait,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "html.parser")
            except requests.RequestException as exc:
                backoff = 2 ** (attempt + 1) + random.uniform(0, 1)
                logger.warning(
                    "Request failed (%s). Retrying in %.1fs (attempt %d/%d)",
                    exc,
                    backoff,
                    attempt + 1,
                    max_retries,
                )
                time.sleep(backoff)
        logger.error("All %d retries exhausted for %s", max_retries, url)
        return None

    def _parse_price(self, price_str: str) -> float:
        """Extract a numeric price from a display string.

        Handles ``$5.99``, ``USD 10.00``, ``$1,234.56``, and range formats
        like ``$5.99 - $12.99`` (returns the first value).
        """
        if not price_str:
            return 0.0
        try:
            cleaned = price_str.strip()
            # Remove currency symbols and labels
            cleaned = re.sub(r"(?i)(USD|CA\$|£|€|\$)", "", cleaned)
            # If range, take the first number
            if "-" in cleaned or "–" in cleaned:
                cleaned = re.split(r"[-–]", cleaned)[0]
            # Strip commas, whitespace
            cleaned = cleaned.replace(",", "").strip()
            # Grab the first float-like substring
            match = re.search(r"(\d+\.?\d*)", cleaned)
            if match:
                return float(match.group(1))
            return 0.0
        except (ValueError, IndexError):
            return 0.0

    # ----- public ---------------------------------------------------------

    def count_listings(self, query: str) -> int:
        """Return the approximate number of Etsy listings matching *query*."""
        url = f"{ETSY_BASE}/search?q={requests.utils.quote(query)}"
        soup = self._make_request(url)
        if not soup:
            return 0

        # Etsy shows result counts in several possible elements
        count_patterns = [
            r"([\d,]+)\s+results?",
            r"Showing\s+[\d,]+\s+of\s+([\d,]+)",
            r"([\d,]+)\s+items?",
        ]
        # Try the page text for a result-count string
        page_text = soup.get_text(" ", strip=True)
        for pattern in count_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return int(match.group(1).replace(",", ""))

        # Fallback: count listing cards on page and extrapolate
        cards = soup.select(
            "div.v2-listing-card, li.wt-list-unstyled, div[data-listing-id]"
        )
        if cards:
            return len(cards) * 100  # rough heuristic: page ≈ 1% of total
        return 0

    def get_top_listings(self, query: str, n: int = 10) -> list[dict]:
        """Scrape the first *n* listing cards for *query*.

        Each dict has keys: ``title``, ``price``, ``reviews``, ``shop_name``.
        """
        url = f"{ETSY_BASE}/search?q={requests.utils.quote(query)}&ref=search_bar"
        soup = self._make_request(url)
        if not soup:
            return []

        results: list[dict] = []

        # Try primary selectors
        cards = soup.select("div.v2-listing-card")
        if not cards:
            cards = soup.select("div[data-listing-id]")
        if not cards:
            cards = soup.select("li.wt-list-unstyled")

        for card in cards[:n]:
            listing: dict[str, Any] = {
                "title": "",
                "price": 0.0,
                "reviews": 0,
                "shop_name": "",
            }

            # Title
            title_el = card.select_one(
                "h3, .v2-listing-card__title, [data-listing-card-title]"
            )
            if title_el:
                listing["title"] = title_el.get_text(strip=True)

            # Price
            price_el = card.select_one(
                ".currency-value, span.currency-value, .lc-price, "
                "span[data-currency-value], .wt-text-title-01"
            )
            if price_el:
                listing["price"] = self._parse_price(price_el.get_text(strip=True))

            # Reviews
            review_el = card.select_one(
                ".wt-text-caption, span[aria-label*='star'], "
                "[data-reviews-count], .wt-text-gray"
            )
            if review_el:
                review_text = review_el.get_text(strip=True)
                rev_match = re.search(r"([\d,]+)", review_text)
                if rev_match:
                    listing["reviews"] = int(rev_match.group(1).replace(",", ""))

            # Shop name
            shop_el = card.select_one(
                ".v2-listing-card__shop, .wt-text-caption, "
                "p.wt-text-caption, [data-shop-name]"
            )
            if shop_el:
                listing["shop_name"] = shop_el.get_text(strip=True)

            results.append(listing)

        return results

    def extract_pricing(self, listings: list[dict]) -> dict:
        """Compute pricing statistics from a list of listing dicts."""
        prices = [l["price"] for l in listings if l.get("price", 0) > 0]
        if not prices:
            return {
                "min": 0.0,
                "max": 0.0,
                "median": 0.0,
                "mean": 0.0,
                "p10": 0.0,
                "p90": 0.0,
            }

        prices_sorted = sorted(prices)
        n = len(prices_sorted)

        def percentile(data: list[float], pct: float) -> float:
            k = (pct / 100) * (len(data) - 1)
            f = int(k)
            c = f + 1
            if c >= len(data):
                return data[-1]
            return data[f] + (k - f) * (data[c] - data[f])

        return {
            "min": round(prices_sorted[0], 2),
            "max": round(prices_sorted[-1], 2),
            "median": round(statistics.median(prices), 2),
            "mean": round(statistics.mean(prices), 2),
            "p10": round(percentile(prices_sorted, 10), 2),
            "p90": round(percentile(prices_sorted, 90), 2),
        }

    def extract_reviews(self, listings: list[dict]) -> dict:
        """Compute review statistics from a list of listing dicts."""
        reviews = [l.get("reviews", 0) for l in listings]
        if not reviews:
            return {"total_reviews": 0, "avg_reviews": 0.0, "max_reviews": 0}
        return {
            "total_reviews": sum(reviews),
            "avg_reviews": round(statistics.mean(reviews), 1),
            "max_reviews": max(reviews),
        }


# =========================================================================
# NicheResearcher
# =========================================================================


class NicheResearcher:
    """Discovers, scores, and ranks digital product niches."""

    def __init__(
        self,
        notion_api_key: Optional[str] = None,
        weights_path: Optional[str] = None,
    ) -> None:
        self.notion_api_key = notion_api_key or os.environ.get("NOTION_API_KEY", "")
        self.weights = self._load_weights(weights_path)
        self.analyzer = EtsySearchAnalyzer()

    # ----- internal -------------------------------------------------------

    def _load_weights(self, path: Optional[str]) -> dict[str, float]:
        """Load scoring weights from a JSON file, falling back to defaults."""
        if path and Path(path).is_file():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                logger.info("Loaded custom weights from %s", path)
                # Ensure all required keys present
                for key in DEFAULT_WEIGHTS:
                    if key not in data:
                        data[key] = DEFAULT_WEIGHTS[key]
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load weights from %s: %s", path, exc)
        return dict(DEFAULT_WEIGHTS)

    def _get_notion_headers(self) -> dict[str, str]:
        """Return standard Notion API headers."""
        return {
            "Authorization": f"Bearer {self.notion_api_key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

    def _score_from_tiers(
        self,
        value: float,
        tiers: list[dict],
        key: str,
    ) -> tuple[int, str]:
        """Walk *tiers* from top to bottom and return (score, label) for the
        first tier whose threshold is met.

        *key* is the dict key to compare against (``"min"`` or ``"max"``).
        """
        for tier in tiers:
            threshold = tier[key]
            if key == "min" and value >= threshold:
                return tier["score"], tier["label"]
            if key == "max" and value <= threshold:
                return tier["score"], tier["label"]
        # Fallback: return last tier
        last = tiers[-1]
        return last["score"], last["label"]

    # ----- discovery ------------------------------------------------------

    def scan_trending_niches(
        self,
        seed_categories: Optional[list[str]] = None,
    ) -> list[dict]:
        """Expand *seed_categories* via Etsy autocomplete suggestions.

        Returns a de-duplicated list of ``{niche, source, discovered_at}``.
        """
        seeds = seed_categories or DEFAULT_SEEDS
        discovered: dict[str, dict] = {}
        now_iso = datetime.now(timezone.utc).isoformat()

        for seed in seeds:
            # Add the seed itself
            norm = seed.strip().lower()
            if norm and norm not in discovered:
                discovered[norm] = {
                    "niche": norm,
                    "source": "seed",
                    "discovered_at": now_iso,
                }

            # Hit Etsy's autocomplete endpoint
            suggest_url = (
                f"{ETSY_BASE}/search/suggest?q={requests.utils.quote(seed)}"
            )
            try:
                delay = random.uniform(1.0, 2.5)
                time.sleep(delay)
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                resp = self.analyzer.session.get(
                    suggest_url, headers=headers, timeout=10
                )
                if resp.status_code == 200:
                    # Response may be JSON or HTML depending on endpoint
                    try:
                        data = resp.json()
                        suggestions: list[str] = []
                        if isinstance(data, list):
                            suggestions = [
                                s if isinstance(s, str) else s.get("query", "")
                                for s in data
                            ]
                        elif isinstance(data, dict):
                            suggestions = data.get("results", data.get("suggestions", []))
                        for sug in suggestions:
                            s_norm = sug.strip().lower()
                            if s_norm and s_norm not in discovered:
                                discovered[s_norm] = {
                                    "niche": s_norm,
                                    "source": f"autocomplete:{seed}",
                                    "discovered_at": now_iso,
                                }
                    except (json.JSONDecodeError, ValueError):
                        # Try parsing as HTML
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for link in soup.select("a"):
                            text = link.get_text(strip=True).lower()
                            if text and len(text) > 2 and text not in discovered:
                                discovered[text] = {
                                    "niche": text,
                                    "source": f"autocomplete:{seed}",
                                    "discovered_at": now_iso,
                                }
            except requests.RequestException as exc:
                logger.warning("Autocomplete request failed for '%s': %s", seed, exc)
                continue

        result = list(discovered.values())
        logger.info("Discovered %d unique niches from %d seeds", len(result), len(seeds))
        return result

    # ----- scoring --------------------------------------------------------

    def score_demand(self, niche: str) -> dict:
        """Score demand for *niche* based on Etsy listing count."""
        listing_count = self.analyzer.count_listings(niche)
        est_monthly_searches = int(listing_count * 2.5)
        score, label = self._score_from_tiers(listing_count, DEMAND_TIERS, "min")
        return {
            "score": score,
            "label": label,
            "listing_count": listing_count,
            "est_monthly_searches": est_monthly_searches,
        }

    def analyze_competition(self, niche: str) -> dict:
        """Score competition intensity for *niche*.

        Lower listing count → higher score (less competition is better).
        """
        listings = self.analyzer.get_top_listings(niche, n=12)
        pricing = self.analyzer.extract_pricing(listings)
        reviews = self.analyzer.extract_reviews(listings)
        listing_count = self.analyzer.count_listings(niche)

        # Inverted scoring: fewer listings = less competition = higher score
        score, label = self._score_from_tiers(listing_count, COMPETITION_TIERS, "max")

        return {
            "score": score,
            "label": label,
            "listing_count": listing_count,
            "top_listings_sampled": len(listings),
            "pricing": pricing,
            "reviews": reviews,
        }

    def estimate_profitability(
        self,
        niche: str,
        avg_price: Optional[float] = None,
    ) -> dict:
        """Estimate per-sale profit margin for *niche*.

        If *avg_price* is not provided, sample via the analyzer.
        Deducts Etsy transaction fee (6.5%) and listing fee ($0.20).
        """
        if avg_price is None:
            listings = self.analyzer.get_top_listings(niche, n=8)
            pricing = self.analyzer.extract_pricing(listings)
            avg_price = pricing.get("mean", 0.0)

        if avg_price <= 0:
            return {
                "score": 15,
                "label": "Unprofitable",
                "avg_price": 0.0,
                "etsy_fee": 0.0,
                "listing_fee": 0.20,
                "margin": 0.0,
                "margin_pct": 0.0,
            }

        etsy_fee = round(avg_price * 0.065, 2)
        listing_fee = 0.20
        margin = round(avg_price - etsy_fee - listing_fee, 2)
        margin_pct = round((margin / avg_price) * 100, 1) if avg_price > 0 else 0.0

        score, label = self._score_from_tiers(margin, PROFITABILITY_TIERS, "min")

        return {
            "score": score,
            "label": label,
            "avg_price": round(avg_price, 2),
            "etsy_fee": etsy_fee,
            "listing_fee": listing_fee,
            "margin": margin,
            "margin_pct": margin_pct,
        }

    def compute_trend_momentum(self, niche: str) -> dict:
        """Estimate trend momentum by analysing listing freshness signals.

        Looks for recency cues in listing titles/review counts to infer
        whether a niche is growing, stable, or declining. Defaults to
        ``'stable'`` (score 55) when insufficient data is available.
        """
        listings = self.analyzer.get_top_listings(niche, n=10)

        if len(listings) < 3:
            return {
                "score": 55,
                "label": "Stable",
                "growth_pct": 0.0,
                "trend_direction": "stable",
            }

        # Heuristic: if top listings have high review counts, the niche is
        # established. If reviews are low, it's likely newer / growing.
        reviews = [l.get("reviews", 0) for l in listings]
        avg_rev = statistics.mean(reviews) if reviews else 0
        max_rev = max(reviews) if reviews else 0

        # Count year references in titles as freshness signals
        current_year = datetime.now().year
        freshness_hits = 0
        for listing in listings:
            title = listing.get("title", "")
            if str(current_year) in title or str(current_year + 1) in title:
                freshness_hits += 1
            if any(kw in title.lower() for kw in ["new", "updated", "latest", "trending"]):
                freshness_hits += 1

        # Scoring logic
        if freshness_hits >= 5 and avg_rev < 500:
            score, label, growth, direction = 85, "Rising Fast", 25.0, "up"
        elif freshness_hits >= 3 and avg_rev < 1000:
            score, label, growth, direction = 70, "Growing", 12.0, "up"
        elif avg_rev > 5000 and freshness_hits <= 1:
            score, label, growth, direction = 35, "Mature / Declining", -5.0, "down"
        elif avg_rev > 2000 and freshness_hits <= 1:
            score, label, growth, direction = 45, "Plateau", 0.0, "flat"
        else:
            score, label, growth, direction = 55, "Stable", 2.0, "stable"

        return {
            "score": score,
            "label": label,
            "growth_pct": growth,
            "trend_direction": direction,
        }

    def compute_niche_score(self, niche: str) -> dict:
        """Run all four scoring dimensions and produce a composite score."""
        demand = self.score_demand(niche)
        competition = self.analyze_competition(niche)
        profitability = self.estimate_profitability(
            niche, avg_price=competition["pricing"].get("mean")
        )
        momentum = self.compute_trend_momentum(niche)

        weighted_total = round(
            demand["score"] * self.weights["demand"]
            + competition["score"] * self.weights["competition"]
            + profitability["score"] * self.weights["profitability"]
            + momentum["score"] * self.weights["momentum"],
            1,
        )

        overall_label = "❌ Weak"
        for threshold, label in OVERALL_THRESHOLDS:
            if weighted_total >= threshold:
                overall_label = label
                break

        return {
            "niche": niche,
            "total_score": weighted_total,
            "overall_label": overall_label,
            "demand": demand,
            "competition": competition,
            "profitability": profitability,
            "momentum": momentum,
            "weights_used": dict(self.weights),
            "scored_at": datetime.now(timezone.utc).isoformat(),
        }

    def rank_niches(self, niches: list[str]) -> list[dict]:
        """Score every niche and return them sorted by total_score descending."""
        scored: list[dict] = []
        for idx, niche in enumerate(niches, 1):
            logger.info("Scoring niche %d/%d: %s", idx, len(niches), niche)
            result = self.compute_niche_score(niche)
            scored.append(result)
        scored.sort(key=lambda x: x["total_score"], reverse=True)
        return scored

    # ----- Notion integration ---------------------------------------------

    def save_to_notion(self, niches: list[dict]) -> list[str]:
        """Create Notion pages in the Product Ideas DB for each scored niche.

        Reads the database ID from the ``NOTION_PRODUCT_IDEAS_DB`` env var.
        Returns a list of created page IDs.
        """
        db_id = os.environ.get("NOTION_PRODUCT_IDEAS_DB", "")
        if not db_id:
            logger.error("NOTION_PRODUCT_IDEAS_DB env var not set. Skipping Notion save.")
            return []
        if not self.notion_api_key:
            logger.error("NOTION_API_KEY not available. Skipping Notion save.")
            return []

        headers = self._get_notion_headers()
        page_ids: list[str] = []

        for niche_data in niches:
            niche_name = niche_data.get("niche", "Unknown")
            payload = {
                "parent": {"database_id": db_id},
                "properties": {
                    "Name": {
                        "title": [{"text": {"content": niche_name}}],
                    },
                    "Niche Score": {
                        "number": niche_data.get("total_score", 0),
                    },
                    "Demand Score": {
                        "number": niche_data.get("demand", {}).get("score", 0),
                    },
                    "Competition Score": {
                        "number": niche_data.get("competition", {}).get("score", 0),
                    },
                    "Profitability Score": {
                        "number": niche_data.get("profitability", {}).get("score", 0),
                    },
                    "Momentum Score": {
                        "number": niche_data.get("momentum", {}).get("score", 0),
                    },
                    "Label": {
                        "select": {
                            "name": niche_data.get("overall_label", "Unknown"),
                        },
                    },
                    "Source": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": niche_data.get("demand", {}).get(
                                        "label", "scan"
                                    ),
                                }
                            }
                        ],
                    },
                    "Status": {
                        "select": {"name": "New"},
                    },
                    "Scan Date": {
                        "date": {
                            "start": niche_data.get(
                                "scored_at",
                                datetime.now(timezone.utc).isoformat(),
                            ),
                        },
                    },
                },
            }

            try:
                resp = requests.post(
                    "https://api.notion.com/v1/pages",
                    headers=headers,
                    json=payload,
                    timeout=15,
                )
                if resp.status_code in (200, 201):
                    page_id = resp.json().get("id", "")
                    page_ids.append(page_id)
                    logger.info("Created Notion page for '%s': %s", niche_name, page_id)
                else:
                    logger.error(
                        "Notion API error for '%s': %d %s",
                        niche_name,
                        resp.status_code,
                        resp.text[:200],
                    )
            except requests.RequestException as exc:
                logger.error("Notion request failed for '%s': %s", niche_name, exc)

        logger.info("Saved %d/%d niches to Notion", len(page_ids), len(niches))
        return page_ids

    # ----- reporting ------------------------------------------------------

    def generate_research_report(self, niches: list[dict]) -> str:
        """Build a Markdown research report from scored niche data."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines: list[str] = []

        lines.append("# 🔍 Niche Research Report")
        lines.append(f"\n**Generated:** {now}")
        lines.append(f"**Niches Analyzed:** {len(niches)}")
        lines.append("")

        # Summary table
        lines.append("## Summary")
        lines.append("")
        lines.append(
            "| Rank | Niche | Score | Label | Demand | Competition | Profit | Momentum |"
        )
        lines.append(
            "|------|-------|-------|-------|--------|-------------|--------|----------|"
        )
        for rank, n in enumerate(niches, 1):
            lines.append(
                f"| {rank} | {n['niche']} | {n['total_score']} | {n['overall_label']} "
                f"| {n['demand']['score']} | {n['competition']['score']} "
                f"| {n['profitability']['score']} | {n['momentum']['score']} |"
            )
        lines.append("")

        # Detailed sections
        lines.append("## Detailed Analysis")
        lines.append("")

        for rank, n in enumerate(niches, 1):
            lines.append(f"### {rank}. {n['niche'].title()}")
            lines.append("")
            lines.append(f"**Overall:** {n['total_score']}/100 — {n['overall_label']}")
            lines.append("")

            # Demand
            d = n["demand"]
            lines.append(f"- **Demand ({d['score']}/100 — {d['label']}):** "
                         f"~{d['listing_count']:,} listings, "
                         f"~{d['est_monthly_searches']:,} est. monthly searches")

            # Competition
            c = n["competition"]
            pricing = c.get("pricing", {})
            reviews = c.get("reviews", {})
            lines.append(
                f"- **Competition ({c['score']}/100 — {c['label']}):** "
                f"Median price ${pricing.get('median', 0):.2f}, "
                f"avg reviews {reviews.get('avg_reviews', 0):.0f}"
            )

            # Profitability
            p = n["profitability"]
            lines.append(
                f"- **Profitability ({p['score']}/100 — {p['label']}):** "
                f"Avg price ${p['avg_price']:.2f}, "
                f"margin ${p['margin']:.2f} ({p['margin_pct']:.1f}%)"
            )

            # Momentum
            m = n["momentum"]
            lines.append(
                f"- **Momentum ({m['score']}/100 — {m['label']}):** "
                f"{m['growth_pct']:+.1f}% growth, direction: {m['trend_direction']}"
            )
            lines.append("")

        # Methodology
        lines.append("---")
        lines.append("")
        lines.append("## Methodology")
        lines.append("")
        lines.append(
            "Scores are computed across four dimensions — **Demand**, "
            "**Competition** (inverted), **Profitability**, and **Momentum** — "
            "each rated 0-100 and combined via configurable weights:"
        )
        lines.append("")
        for dim, weight in self.weights.items():
            lines.append(f"- {dim.title()}: {weight * 100:.0f}%")
        lines.append("")
        lines.append(
            "Data is sourced from Etsy search results, listing metadata, "
            "and autocomplete suggestions. Listings are sampled from the "
            "first page of results; counts are parsed from search result "
            "headers. Trend momentum uses title freshness signals and "
            "review distribution heuristics."
        )
        lines.append("")

        return "\n".join(lines)


# =========================================================================
# Test suite
# =========================================================================


def run_tests() -> int:
    """Run built-in self-tests. Returns 0 on all-pass, 1 on any failure."""
    results: list[tuple[str, bool, str]] = []

    # ---- test_tier_scoring -----------------------------------------------
    test_name = "test_tier_scoring"
    try:
        researcher = NicheResearcher.__new__(NicheResearcher)
        researcher.weights = dict(DEFAULT_WEIGHTS)

        mock_tiers = [
            {"min": 100, "score": 90, "label": "High"},
            {"min": 50, "score": 60, "label": "Medium"},
            {"min": 0, "score": 20, "label": "Low"},
        ]
        score, label = researcher._score_from_tiers(150, mock_tiers, "min")
        assert score == 90 and label == "High", f"Got {score}, {label}"

        score, label = researcher._score_from_tiers(75, mock_tiers, "min")
        assert score == 60 and label == "Medium", f"Got {score}, {label}"

        score, label = researcher._score_from_tiers(10, mock_tiers, "min")
        assert score == 20 and label == "Low", f"Got {score}, {label}"

        # Test "max" key direction
        max_tiers = [
            {"max": 50, "score": 95, "label": "Easy"},
            {"max": 200, "score": 50, "label": "Hard"},
            {"max": float("inf"), "score": 10, "label": "Impossible"},
        ]
        score, label = researcher._score_from_tiers(30, max_tiers, "max")
        assert score == 95 and label == "Easy", f"Got {score}, {label}"

        score, label = researcher._score_from_tiers(100, max_tiers, "max")
        assert score == 50 and label == "Hard", f"Got {score}, {label}"

        results.append((test_name, True, "All tier assertions passed"))
    except Exception as exc:
        results.append((test_name, False, str(exc)))

    # ---- test_niche_score_computation ------------------------------------
    test_name = "test_niche_score_computation"
    try:
        researcher = NicheResearcher.__new__(NicheResearcher)
        researcher.weights = {
            "demand": 0.30,
            "competition": 0.25,
            "profitability": 0.25,
            "momentum": 0.20,
        }
        researcher.analyzer = EtsySearchAnalyzer.__new__(EtsySearchAnalyzer)

        # Mock the four scoring methods
        demand_result = {"score": 80, "label": "High", "listing_count": 25000, "est_monthly_searches": 62500}
        competition_result = {
            "score": 70,
            "label": "Moderate Competition",
            "listing_count": 1500,
            "top_listings_sampled": 10,
            "pricing": {"min": 3.0, "max": 25.0, "median": 9.99, "mean": 11.50, "p10": 4.0, "p90": 20.0},
            "reviews": {"total_reviews": 5000, "avg_reviews": 500.0, "max_reviews": 2000},
        }
        profitability_result = {
            "score": 75,
            "label": "Good Margin",
            "avg_price": 11.50,
            "etsy_fee": 0.75,
            "listing_fee": 0.20,
            "margin": 10.55,
            "margin_pct": 91.7,
        }
        momentum_result = {"score": 55, "label": "Stable", "growth_pct": 2.0, "trend_direction": "stable"}

        # Manually compute expected weighted total
        expected = round(
            80 * 0.30 + 70 * 0.25 + 75 * 0.25 + 55 * 0.20,
            1,
        )
        # = 24.0 + 17.5 + 18.75 + 11.0 = 71.25

        # Monkey-patch scoring methods
        researcher.score_demand = lambda n: demand_result
        researcher.analyze_competition = lambda n: competition_result
        researcher.estimate_profitability = lambda n, avg_price=None: profitability_result
        researcher.compute_trend_momentum = lambda n: momentum_result

        result = researcher.compute_niche_score("test niche")
        assert abs(result["total_score"] - expected) < 0.01, (
            f"Expected {expected}, got {result['total_score']}"
        )
        assert result["overall_label"] == "✅ Promising", (
            f"Expected '✅ Promising', got '{result['overall_label']}'"
        )

        results.append((test_name, True, f"Weighted score {expected} computed correctly"))
    except Exception as exc:
        results.append((test_name, False, str(exc)))

    # ---- test_price_parsing ----------------------------------------------
    test_name = "test_price_parsing"
    try:
        analyzer = EtsySearchAnalyzer.__new__(EtsySearchAnalyzer)

        cases = [
            ("$5.99", 5.99),
            ("USD 10.00", 10.00),
            ("7.99", 7.99),
            ("$1,234.56", 1234.56),
            ("$5.99 - $12.99", 5.99),
            ("free", 0.0),
            ("", 0.0),
            ("abc", 0.0),
        ]
        for input_str, expected_val in cases:
            result = analyzer._parse_price(input_str)
            assert abs(result - expected_val) < 0.01, (
                f"_parse_price('{input_str}') = {result}, expected {expected_val}"
            )

        results.append((test_name, True, f"All {len(cases)} price parsing cases passed"))
    except Exception as exc:
        results.append((test_name, False, str(exc)))

    # ---- test_report_generation ------------------------------------------
    test_name = "test_report_generation"
    try:
        researcher = NicheResearcher.__new__(NicheResearcher)
        researcher.weights = dict(DEFAULT_WEIGHTS)

        mock_niches = [
            {
                "niche": "budget planner",
                "total_score": 78.5,
                "overall_label": "✅ Promising",
                "demand": {"score": 80, "label": "High", "listing_count": 20000, "est_monthly_searches": 50000},
                "competition": {
                    "score": 70,
                    "label": "Moderate",
                    "pricing": {"median": 9.99},
                    "reviews": {"avg_reviews": 300},
                },
                "profitability": {
                    "score": 75,
                    "label": "Good Margin",
                    "avg_price": 9.99,
                    "margin": 9.14,
                    "margin_pct": 91.5,
                },
                "momentum": {
                    "score": 60,
                    "label": "Growing",
                    "growth_pct": 8.0,
                    "trend_direction": "up",
                },
            },
            {
                "niche": "digital sticker",
                "total_score": 65.0,
                "overall_label": "✅ Promising",
                "demand": {"score": 60, "label": "Moderate", "listing_count": 8000, "est_monthly_searches": 20000},
                "competition": {
                    "score": 50,
                    "label": "Competitive",
                    "pricing": {"median": 4.50},
                    "reviews": {"avg_reviews": 800},
                },
                "profitability": {
                    "score": 55,
                    "label": "Moderate Margin",
                    "avg_price": 4.50,
                    "margin": 4.01,
                    "margin_pct": 89.1,
                },
                "momentum": {
                    "score": 55,
                    "label": "Stable",
                    "growth_pct": 2.0,
                    "trend_direction": "stable",
                },
            },
        ]

        report = researcher.generate_research_report(mock_niches)
        assert len(report) > 100, f"Report too short: {len(report)} chars"
        assert "# 🔍 Niche Research Report" in report, "Missing report header"
        assert "## Summary" in report, "Missing summary section"
        assert "## Detailed Analysis" in report, "Missing detailed analysis"
        assert "## Methodology" in report, "Missing methodology section"
        assert "budget planner" in report.lower(), "Missing niche data"
        assert "digital sticker" in report.lower(), "Missing second niche"

        results.append((test_name, True, "Report generated with all expected sections"))
    except Exception as exc:
        results.append((test_name, False, str(exc)))

    # ---- print results ---------------------------------------------------
    print("\n" + "=" * 60)
    print("  NICHE RESEARCHER — TEST RESULTS")
    print("=" * 60)
    all_passed = True
    for name, passed, detail in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}  {name}")
        if not passed:
            print(f"         → {detail}")
            all_passed = False
    print("=" * 60)
    total = len(results)
    passed_count = sum(1 for _, p, _ in results if p)
    print(f"  {passed_count}/{total} tests passed")
    print("=" * 60 + "\n")
    return 0 if all_passed else 1


# =========================================================================
# CLI
# =========================================================================


def main() -> None:
    """Entry point for the niche research CLI."""
    parser = argparse.ArgumentParser(
        description="Niche Research Engine — discover and score Etsy digital product niches",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --scan                       Discover niches from default seeds\n"
            "  %(prog)s --scan --seeds planner,SVG    Discover niches from custom seeds\n"
            "  %(prog)s --score 'budget tracker'      Score a single niche\n"
            "  %(prog)s --report --top 5              Generate a report for top 5 niches\n"
            "  %(prog)s --test                        Run built-in self-tests\n"
        ),
    )

    parser.add_argument(
        "--scan",
        action="store_true",
        help="Discover trending niches via Etsy autocomplete",
    )
    parser.add_argument(
        "--score",
        type=str,
        metavar="NICHE",
        help="Score a specific niche",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate a full research report (scans + scores + ranks)",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        metavar="SEEDS",
        help="Comma-separated seed categories for scanning",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        metavar="N",
        help="Number of top niches to include in ranking/report (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=str,
        metavar="PATH",
        help="Output file path for the report",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run built-in self-tests and exit",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # --test
    if args.test:
        sys.exit(run_tests())

    # Initialise researcher
    researcher = NicheResearcher()
    seeds = args.seeds.split(",") if args.seeds else None

    # --scan
    if args.scan:
        logger.info("Starting niche scan...")
        discovered = researcher.scan_trending_niches(seed_categories=seeds)
        print(f"\n🔍 Discovered {len(discovered)} niches:\n")
        for item in discovered:
            print(f"  • {item['niche']}  (source: {item['source']})")
        print()

        # Optionally write JSON
        if args.output:
            out_path = Path(args.output)
            out_path.write_text(json.dumps(discovered, indent=2), encoding="utf-8")
            print(f"💾 Saved to {out_path}")
        return

    # --score NICHE
    if args.score:
        logger.info("Scoring niche: %s", args.score)
        result = researcher.compute_niche_score(args.score)
        print(f"\n📊 Niche Score for '{args.score}':\n")
        print(f"  Total:         {result['total_score']}/100 {result['overall_label']}")
        print(f"  Demand:        {result['demand']['score']}/100 ({result['demand']['label']})")
        print(f"  Competition:   {result['competition']['score']}/100 ({result['competition']['label']})")
        print(f"  Profitability: {result['profitability']['score']}/100 ({result['profitability']['label']})")
        print(f"  Momentum:      {result['momentum']['score']}/100 ({result['momentum']['label']})")
        print()

        if args.output:
            out_path = Path(args.output)
            out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(f"💾 Saved to {out_path}")
        return

    # --report
    if args.report:
        logger.info("Generating full research report...")
        discovered = researcher.scan_trending_niches(seed_categories=seeds)
        niche_names = [d["niche"] for d in discovered[: args.top]]

        logger.info("Ranking top %d niches...", len(niche_names))
        ranked = researcher.rank_niches(niche_names)

        report = researcher.generate_research_report(ranked)

        if args.output:
            out_path = Path(args.output)
            out_path.write_text(report, encoding="utf-8")
            print(f"💾 Report saved to {out_path}")
        else:
            print(report)

        # Save to Notion if configured
        if os.environ.get("NOTION_PRODUCT_IDEAS_DB"):
            logger.info("Saving results to Notion...")
            page_ids = researcher.save_to_notion(ranked)
            print(f"📝 Created {len(page_ids)} Notion pages")
        return

    # No action specified
    parser.print_help()


if __name__ == "__main__":
    main()
