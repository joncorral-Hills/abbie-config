#!/usr/bin/env python3
"""SEO Optimizer for the Digital Storefront Planner.

Researches keywords, audits listing quality, and generates optimized
titles/tags/descriptions for Etsy listings.
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
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("seo_optimizer")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ETSY_SUGGEST_URL = "https://www.etsy.com/search/suggest"
NOTION_API_URL = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"

DIGITAL_MODIFIERS = [
    "printable", "template", "digital download", "instant download",
    "PDF", "editable", "planner", "worksheet", "tracker", "checklist",
]

STYLE_DESCRIPTORS = [
    "minimalist", "boho", "modern", "vintage", "aesthetic", "cute",
    "elegant", "rustic", "floral", "watercolor", "retro", "simple",
    "colorful", "pastel", "gothic", "cottagecore", "preppy", "kawaii",
]

PRODUCT_TYPE_WORDS = [
    "planner", "tracker", "template", "printable", "worksheet",
    "calendar", "journal", "sticker", "checklist", "guide", "bundle",
    "kit", "card", "invitation", "resume", "poster", "wall art",
    "bookmark", "label", "tag", "sign", "banner", "insert", "log",
]

COMMON_SEARCH_TERMS = {
    "planner": 95, "budget": 80, "printable": 85, "template": 82,
    "tracker": 75, "digital": 70, "download": 60, "calendar": 78,
    "journal": 72, "wedding": 90, "baby": 88, "birthday": 86,
    "christmas": 92, "minimalist": 65, "aesthetic": 68, "boho": 62,
    "editable": 58, "PDF": 55, "worksheet": 50, "checklist": 48,
    "sticker": 74, "invitation": 76, "resume": 64, "wall art": 60,
    "finance": 52, "meal": 46, "fitness": 54, "habit": 44,
    "gratitude": 40, "self care": 42, "goal": 45, "monthly": 56,
    "weekly": 58, "daily": 60, "yearly": 50, "holiday": 70,
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ListingAudit:
    """Result of an SEO audit for a single listing."""
    listing_id: str
    title_score: int
    tag_score: int
    description_score: int
    image_score: int
    attribute_score: int
    total_score: int
    recommendations: list[str]
    audited_at: str  # ISO-8601 timestamp


# ---------------------------------------------------------------------------
# SEOOptimizer
# ---------------------------------------------------------------------------

class SEOOptimizer:
    """Keyword research, listing audit, and title/tag/description optimizer."""

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def __init__(
        self,
        notion_api_key: Optional[str] = None,
        rules_path: Optional[str] = None,
    ) -> None:
        self.notion_api_key = notion_api_key or os.getenv("NOTION_API_KEY", "")
        default_rules = Path(__file__).parent / "seo_best_practices.json"
        self.rules = self._load_rules(rules_path or str(default_rules))
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        })
        logger.info("SEOOptimizer initialized (rules keys: %s)", list(self.rules.keys()))

    # ------------------------------------------------------------------
    # Configuration helpers
    # ------------------------------------------------------------------

    def _load_rules(self, path: str) -> dict:
        """Load SEO best-practices JSON.  Return sensible defaults on failure."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                logger.info("Loaded SEO rules from %s", path)
                return data
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning("Could not load rules from %s: %s — using defaults", path, exc)
            return {
                "max_title_length": 140,
                "max_tag_length": 20,
                "ideal_tag_count": 13,
                "min_description_words": 300,
                "ideal_image_count": 8,
                "title_weights": {"primary_keyword_position": 8, "length": 5,
                                  "product_type": 4, "style_descriptor": 4,
                                  "no_repeats": 4},
                "tag_weights": {"count": 6, "multi_word_ratio": 5,
                                "breadth": 5, "uniqueness": 4},
                "description_weights": {"word_count": 5, "sections": 5,
                                        "keyword_placement": 4,
                                        "specs": 3, "bullets": 3},
                "image_weights": {"count": 6, "alt_text": 5,
                                  "variety": 3, "whats_included": 3,
                                  "naming": 3},
                "attribute_weights": {"category": 5, "filled_count": 5,
                                      "occasion": 3, "style": 2},
            }

    def _get_notion_headers(self) -> dict:
        """Return authorization headers for the Notion API."""
        return {
            "Authorization": f"Bearer {self.notion_api_key}",
            "Notion-Version": NOTION_API_VERSION,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Keyword research
    # ------------------------------------------------------------------

    def research_keywords(
        self,
        seed: str,
        category: Optional[str] = None,
    ) -> list[dict]:
        """Expand a seed keyword into a scored, sorted keyword list.

        Returns a list of dicts with keys:
            keyword, relevance_score, estimated_volume,
            competition_level, composite
        """
        raw_keywords: list[str] = []

        # 1. Autocomplete expansion
        autocomplete_results = self.expand_via_autocomplete(seed)
        raw_keywords.extend(autocomplete_results)

        # 2. Programmatic variations with digital modifiers
        seed_lower = seed.lower().strip()
        for modifier in DIGITAL_MODIFIERS:
            raw_keywords.append(f"{seed_lower} {modifier}")
            raw_keywords.append(f"{modifier} {seed_lower}")

        # 3. Category-specific variations
        if category:
            cat_lower = category.lower().strip()
            raw_keywords.append(f"{cat_lower} {seed_lower}")
            raw_keywords.append(f"{seed_lower} {cat_lower}")
            for modifier in DIGITAL_MODIFIERS[:5]:
                raw_keywords.append(f"{cat_lower} {seed_lower} {modifier}")

        # 4. Style variations
        for style in STYLE_DESCRIPTORS[:6]:
            raw_keywords.append(f"{style} {seed_lower}")

        # 5. Deduplicate (case-insensitive, preserving first occurrence)
        seen: set[str] = set()
        unique: list[str] = []
        for kw in raw_keywords:
            normalised = kw.lower().strip()
            if normalised and normalised not in seen:
                seen.add(normalised)
                unique.append(normalised)

        # 6. Score and sort
        scored = [self.score_keyword(kw) for kw in unique]
        scored.sort(key=lambda d: d["composite"], reverse=True)

        logger.info(
            "Researched %d keywords for seed '%s' (category=%s)",
            len(scored), seed, category,
        )
        return scored

    def expand_via_autocomplete(self, seed: str) -> list[str]:
        """Hit Etsy's autocomplete endpoint; fall back to programmatic expansion."""
        suggestions: list[str] = []
        try:
            resp = self._session.get(
                ETSY_SUGGEST_URL,
                params={"q": seed},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            # Etsy returns various shapes — handle the common ones
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        suggestions.append(item)
                    elif isinstance(item, dict) and "query" in item:
                        suggestions.append(item["query"])
            elif isinstance(data, dict):
                for key in ("queries", "suggestions", "results"):
                    if key in data and isinstance(data[key], list):
                        for entry in data[key]:
                            if isinstance(entry, str):
                                suggestions.append(entry)
                            elif isinstance(entry, dict):
                                suggestions.append(
                                    entry.get("query", entry.get("value", ""))
                                )
            logger.info("Autocomplete returned %d suggestions for '%s'", len(suggestions), seed)
        except Exception as exc:
            logger.warning("Autocomplete failed for '%s': %s — using fallback", seed, exc)

        # Fallback / supplement: programmatic variations
        if len(suggestions) < 5:
            seed_lower = seed.lower().strip()
            fallbacks = [
                f"{seed_lower} printable",
                f"{seed_lower} template",
                f"{seed_lower} digital download",
                f"best {seed_lower}",
                f"{seed_lower} pdf",
                f"{seed_lower} editable",
                f"cute {seed_lower}",
                f"{seed_lower} instant download",
            ]
            for fb in fallbacks:
                if fb not in suggestions:
                    suggestions.append(fb)

        return suggestions

    def score_keyword(self, keyword: str) -> dict:
        """Score a keyword on relevance, volume, and competition.

        Returns dict with: keyword, relevance_score, estimated_volume,
        competition_level, composite.
        """
        words = keyword.lower().split()
        word_count = len(words)

        # --- Relevance (0-100) ---
        # Longer phrases are more specific / relevant
        if word_count >= 4:
            relevance = 90
        elif word_count == 3:
            relevance = 75
        elif word_count == 2:
            relevance = 55
        else:
            relevance = 30

        # Bonus for containing a digital-product modifier
        if any(mod in keyword.lower() for mod in DIGITAL_MODIFIERS):
            relevance = min(100, relevance + 10)

        # --- Estimated volume (0-100) ---
        volume_scores = []
        for w in words:
            if w in COMMON_SEARCH_TERMS:
                volume_scores.append(COMMON_SEARCH_TERMS[w])
        if volume_scores:
            volume = int(statistics.mean(volume_scores))
        else:
            # Unknown words get a baseline
            volume = max(10, 40 - word_count * 5)

        # --- Competition (0-100, higher = more competitive) ---
        # Short / generic keywords → high competition
        if word_count == 1:
            competition = 90
        elif word_count == 2:
            competition = 70
        elif word_count == 3:
            competition = 50
        else:
            competition = max(20, 60 - word_count * 8)

        # --- Composite ---
        composite = round(
            0.4 * relevance + 0.3 * volume + 0.3 * (100 - competition), 1
        )

        return {
            "keyword": keyword,
            "relevance_score": relevance,
            "estimated_volume": volume,
            "competition_level": competition,
            "composite": composite,
        }

    # ------------------------------------------------------------------
    # Tag selection
    # ------------------------------------------------------------------

    def select_tags(self, keywords: list[dict], n: int = 13) -> list[str]:
        """Greedily select *n* diverse, multi-word tags from scored keywords.

        Prefers multi-word phrases.  Ensures no two selected tags share
        more than 50 % of their words.  Each tag is truncated to 20 chars.
        """
        # Sort: multi-word first, then by composite desc
        sorted_kws = sorted(
            keywords,
            key=lambda d: (len(d["keyword"].split()) > 1, d["composite"]),
            reverse=True,
        )

        selected: list[str] = []
        selected_word_sets: list[set[str]] = []

        for entry in sorted_kws:
            if len(selected) >= n:
                break

            tag = entry["keyword"].strip()[:20].strip()
            if not tag:
                continue

            tag_words = set(tag.lower().split())

            # Diversity check: reject if >50 % word overlap with any existing tag
            too_similar = False
            for existing_words in selected_word_sets:
                if not existing_words or not tag_words:
                    continue
                overlap = len(tag_words & existing_words)
                smaller = min(len(tag_words), len(existing_words))
                if smaller > 0 and overlap / smaller > 0.5:
                    too_similar = True
                    break

            if too_similar:
                continue

            selected.append(tag)
            selected_word_sets.append(tag_words)

        logger.info("Selected %d tags (requested %d)", len(selected), n)
        return selected

    # ------------------------------------------------------------------
    # Title optimisation
    # ------------------------------------------------------------------

    def optimize_title(self, product_name: str, keywords: list[dict]) -> str:
        """Build an SEO-optimised Etsy title (≤ 140 chars).

        Structure:  <top keyword> <product_name> | <secondary keywords …>
        """
        max_len = self.rules.get("max_title_length", 140)

        # Pick top keyword that isn't already the product name
        top_kw = ""
        secondary: list[str] = []
        for entry in keywords:
            kw = entry["keyword"]
            if not top_kw and kw.lower() != product_name.lower():
                top_kw = kw.title()
            else:
                secondary.append(kw.title())

        # Start the title
        if top_kw.lower() in product_name.lower():
            title = product_name.strip()
        else:
            title = f"{top_kw} {product_name}".strip()

        # Append secondary keywords separated by ' | '
        for kw in secondary:
            candidate = f"{title} | {kw}"
            if len(candidate) <= max_len:
                title = candidate
            else:
                # Try to fit a partial keyword (whole words only)
                remaining = max_len - len(title) - 3  # ' | '
                if remaining >= 4:
                    truncated_words = []
                    for word in kw.split():
                        if len(" ".join(truncated_words + [word])) <= remaining:
                            truncated_words.append(word)
                        else:
                            break
                    if truncated_words:
                        title = f"{title} | {' '.join(truncated_words)}"
                break  # stop once we can't fit more

        return title[:max_len].strip()

    # ------------------------------------------------------------------
    # Scoring helpers (private)
    # ------------------------------------------------------------------

    def _score_title(self, title: str) -> tuple[int, list[str]]:
        """Score a listing title out of 25.  Return (score, recommendations)."""
        score = 0
        recs: list[str] = []
        title_lower = title.lower()
        words = title_lower.split()

        # Primary keyword in first 3 words (+8)
        first_three = " ".join(words[:3]) if words else ""
        has_primary_keyword = any(
            pt in first_three for pt in PRODUCT_TYPE_WORDS
        ) or any(mod in first_three for mod in DIGITAL_MODIFIERS)
        if has_primary_keyword:
            score += 8
        else:
            recs.append("Place your primary keyword within the first 3 words of the title.")

        # Length ≥ 120 chars (+5)
        if len(title) >= 120:
            score += 5
        else:
            recs.append(
                f"Title is {len(title)} chars — aim for ≥120 to maximise keyword reach."
            )

        # Contains a product-type word (+4)
        if any(pt in title_lower for pt in PRODUCT_TYPE_WORDS):
            score += 4
        else:
            recs.append(
                "Include a product-type word (e.g. planner, template, tracker) in the title."
            )

        # Has a style descriptor (+4)
        if any(sd in title_lower for sd in STYLE_DESCRIPTORS):
            score += 4
        else:
            recs.append(
                "Add a style descriptor (e.g. minimalist, boho, modern) to attract niche buyers."
            )

        # No repeated keywords more than twice (+4)
        word_counts: dict[str, int] = {}
        for w in words:
            word_counts[w] = word_counts.get(w, 0) + 1
        has_repeats = any(c > 2 for c in word_counts.values())
        if not has_repeats:
            score += 4
        else:
            repeated = [w for w, c in word_counts.items() if c > 2]
            recs.append(
                f"Avoid repeating keywords more than twice. Over-used: {', '.join(repeated)}"
            )

        return score, recs

    def _score_tags(self, tags: list[str]) -> tuple[int, list[str]]:
        """Score listing tags out of 20.  Return (score, recommendations)."""
        score = 0
        recs: list[str] = []

        # Count == 13 (+6)
        if len(tags) == 13:
            score += 6
        else:
            recs.append(f"Use all 13 tag slots (currently {len(tags)}).")

        # > 50 % multi-word (+5)
        multi_word_count = sum(1 for t in tags if len(t.split()) > 1)
        if tags and multi_word_count / len(tags) > 0.5:
            score += 5
        else:
            recs.append(
                "Over half your tags should be multi-word phrases for better specificity."
            )

        # Has both broad and specific tags (+5)
        word_lengths = [len(t.split()) for t in tags]
        has_broad = any(wl == 1 for wl in word_lengths)
        has_specific = any(wl >= 3 for wl in word_lengths)
        if has_broad and has_specific:
            score += 5
        else:
            if not has_broad:
                recs.append("Add at least one broad, single-word tag for discoverability.")
            if not has_specific:
                recs.append("Add at least one specific 3+ word tag for long-tail searches.")

        # No single-word overlap with title (+4)
        # (Caller can pass title words via a side-channel; here we just check
        # for tags that are single words duplicated across other tags)
        tag_single_words = [t.lower() for t in tags if len(t.split()) == 1]
        unique_single = len(set(tag_single_words))
        if unique_single == len(tag_single_words):
            score += 4
        else:
            recs.append("Remove duplicate single-word tags — each tag should be unique.")

        return score, recs

    def _score_description(self, description: str) -> tuple[int, list[str]]:
        """Score a listing description out of 20.  Return (score, recommendations)."""
        score = 0
        recs: list[str] = []
        words = description.split()
        word_count = len(words)

        # Word count ≥ 300 (+5)
        if word_count >= 300:
            score += 5
        else:
            recs.append(
                f"Description is {word_count} words — aim for ≥300 for SEO strength."
            )

        # Has sections / headers (+5)
        has_sections = bool(
            re.search(r"(#{1,3}\s|★|►|▸|■|•\s*[A-Z].*:|\n[A-Z ]{4,}\n)", description)
        )
        if has_sections:
            score += 5
        else:
            recs.append(
                "Break your description into clearly labelled sections (e.g. WHAT'S INCLUDED, HOW TO USE)."
            )

        # Keywords in first 160 chars (+4)
        first_160 = description[:160].lower()
        keyword_in_opening = any(
            kw in first_160 for kw in PRODUCT_TYPE_WORDS + DIGITAL_MODIFIERS
        )
        if keyword_in_opening:
            score += 4
        else:
            recs.append(
                "Put your primary keywords in the first 160 characters — this is the search snippet."
            )

        # Has specs / dimensions (+3)
        has_specs = bool(
            re.search(
                r"(\d+\s*(x|×|by)\s*\d+|"
                r"\d+\s*(inches|cm|mm|px|pixels|dpi|ppi|MB|KB|pages?|sheets?))",
                description,
                re.IGNORECASE,
            )
        )
        if has_specs:
            score += 3
        else:
            recs.append(
                "Add specific dimensions, file sizes, or page counts to the description."
            )

        # Has bullet points or lists (+3)
        has_bullets = bool(
            re.search(r"(^[\-•★►▸✓✔]\s|^\d+[\.\)]\s)", description, re.MULTILINE)
        )
        if has_bullets:
            score += 3
        else:
            recs.append("Use bullet points or numbered lists for easy scanning.")

        return score, recs

    def _score_images(self, images: list[dict]) -> tuple[int, list[str]]:
        """Score listing images out of 20.  Return (score, recommendations).

        Each image dict may have keys: url, alt_text, filename, type.
        """
        score = 0
        recs: list[str] = []

        # Count ≥ 8 (+6)
        if len(images) >= 8:
            score += 6
        else:
            recs.append(f"Upload at least 8 images (currently {len(images)}).")

        # Has alt text or contextual filenames (+5)
        has_context = any(
            img.get("alt_text") or (
                img.get("filename", "") and
                not re.match(r"^(IMG|DSC|image|photo)[\-_]?\d*", img.get("filename", ""), re.I)
            )
            for img in images
        )
        if has_context:
            score += 5
        else:
            recs.append(
                "Name image files descriptively (e.g. 'budget-planner-printable-preview.jpg')."
            )

        # Variety of types (+3)
        types = {img.get("type", "unknown").lower() for img in images}
        if len(types) >= 3:
            score += 3
        elif len(types) >= 2:
            score += 1
            recs.append(
                "Add more image types (mockup, flat lay, close-up, lifestyle, what's-included)."
            )
        else:
            recs.append(
                "Use a variety of image types: mockup, flat lay, close-up, lifestyle."
            )

        # Has a 'what's-included' type (+3)
        whats_included_terms = {"whats_included", "whats-included", "included", "contents"}
        has_included = any(
            img.get("type", "").lower().replace(" ", "_") in whats_included_terms
            or "included" in img.get("filename", "").lower()
            or "included" in img.get("alt_text", "").lower()
            for img in images
        )
        if has_included:
            score += 3
        else:
            recs.append("Add a 'What's Included' image showing all files the buyer receives.")

        # Consistent naming (+3)
        filenames = [img.get("filename", "") for img in images if img.get("filename")]
        if filenames:
            # Check if filenames share a common prefix (≥ 50 % do)
            prefixes = [fn.split("-")[0].split("_")[0].lower() for fn in filenames]
            most_common_prefix = max(set(prefixes), key=prefixes.count) if prefixes else ""
            consistency = prefixes.count(most_common_prefix) / len(prefixes) if prefixes else 0
            if consistency >= 0.5:
                score += 3
            else:
                recs.append("Use a consistent naming scheme for listing images.")
        else:
            recs.append("Ensure image filenames are available for SEO analysis.")

        return score, recs

    def _score_attributes(self, attributes: dict) -> tuple[int, list[str]]:
        """Score listing attributes out of 15.  Return (score, recommendations)."""
        score = 0
        recs: list[str] = []

        # Has category (+5)
        if attributes.get("category"):
            score += 5
        else:
            recs.append("Set a category for the listing to improve search placement.")

        # > 3 attributes filled (+5)
        filled = sum(1 for v in attributes.values() if v)
        if filled > 3:
            score += 5
        else:
            recs.append(
                f"Fill in more attributes ({filled} filled — aim for > 3)."
            )

        # Has occasion (+3)
        if attributes.get("occasion"):
            score += 3
        else:
            recs.append("Specify an occasion (e.g. Birthday, Christmas, Back-to-School).")

        # Has style (+2)
        if attributes.get("style"):
            score += 2
        else:
            recs.append("Add a style attribute (e.g. Minimalist, Boho, Modern).")

        return score, recs

    # ------------------------------------------------------------------
    # Listing audit
    # ------------------------------------------------------------------

    def audit_listing(self, listing: dict) -> ListingAudit:
        """Run a full SEO audit on a single listing dict.

        Expected keys in *listing*:
            listing_id, title, tags (list[str]),
            description (str), images (list[dict]),
            attributes (dict).
        """
        listing_id = listing.get("listing_id", listing.get("id", "unknown"))
        title = listing.get("title", "")
        tags = listing.get("tags", [])
        description = listing.get("description", "")
        images = listing.get("images", [])
        attributes = listing.get("attributes", {})

        title_score, title_recs = self._score_title(title)
        tag_score, tag_recs = self._score_tags(tags)
        desc_score, desc_recs = self._score_description(description)
        img_score, img_recs = self._score_images(images)
        attr_score, attr_recs = self._score_attributes(attributes)

        total = title_score + tag_score + desc_score + img_score + attr_score
        all_recs = title_recs + tag_recs + desc_recs + img_recs + attr_recs

        audit = ListingAudit(
            listing_id=str(listing_id),
            title_score=title_score,
            tag_score=tag_score,
            description_score=desc_score,
            image_score=img_score,
            attribute_score=attr_score,
            total_score=total,
            recommendations=all_recs,
            audited_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info(
            "Audited listing %s — total %d/100 (%d recs)",
            listing_id, total, len(all_recs),
        )
        return audit

    def audit_all_listings(self) -> list[ListingAudit]:
        """Query Notion Listings DB and audit every active listing.

        Returns audits sorted by total_score ascending (worst first).
        """
        db_id = os.getenv("NOTION_LISTINGS_DB", "")
        if not db_id:
            logger.error("NOTION_LISTINGS_DB env var not set")
            return []

        # Query Notion for active listings
        url = f"{NOTION_API_URL}/databases/{db_id}/query"
        payload: dict[str, Any] = {
            "filter": {
                "property": "Status",
                "select": {"equals": "Active"},
            },
            "page_size": 100,
        }

        all_pages: list[dict] = []
        has_more = True
        start_cursor: Optional[str] = None

        while has_more:
            if start_cursor:
                payload["start_cursor"] = start_cursor

            try:
                resp = requests.post(
                    url, headers=self._get_notion_headers(), json=payload, timeout=15
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.error("Notion query failed: %s", exc)
                break

            all_pages.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")

        logger.info("Fetched %d active listings from Notion", len(all_pages))

        audits: list[ListingAudit] = []
        for page in all_pages:
            listing = self._notion_page_to_listing(page)
            audits.append(self.audit_listing(listing))

        # Sort worst-first
        audits.sort(key=lambda a: a.total_score)
        return audits

    def _notion_page_to_listing(self, page: dict) -> dict:
        """Convert a Notion page object into a flat listing dict for auditing."""
        props = page.get("properties", {})

        def _rich_text(prop_name: str) -> str:
            prop = props.get(prop_name, {})
            texts = prop.get("rich_text", prop.get("title", []))
            return "".join(t.get("plain_text", "") for t in texts)

        def _multi_select(prop_name: str) -> list[str]:
            prop = props.get(prop_name, {})
            return [opt.get("name", "") for opt in prop.get("multi_select", [])]

        def _select(prop_name: str) -> str:
            prop = props.get(prop_name, {})
            sel = prop.get("select")
            return sel.get("name", "") if sel else ""

        listing_id = _rich_text("Listing ID") or page.get("id", "unknown")
        title = _rich_text("Title") or _rich_text("Name")
        tags = _multi_select("Tags")
        description = _rich_text("Description")

        # Images — stored as a list of file URLs in a files property
        images_raw = props.get("Images", {}).get("files", [])
        images = []
        for img in images_raw:
            images.append({
                "url": img.get("file", {}).get("url", img.get("external", {}).get("url", "")),
                "filename": img.get("name", ""),
                "alt_text": "",
                "type": "unknown",
            })

        attributes = {
            "category": _select("Category"),
            "occasion": _select("Occasion"),
            "style": _select("Style"),
            "color": _select("Color"),
            "material": _select("Material"),
        }

        return {
            "listing_id": listing_id,
            "title": title,
            "tags": tags,
            "description": description,
            "images": images,
            "attributes": attributes,
        }

    # ------------------------------------------------------------------
    # Recommendation generation
    # ------------------------------------------------------------------

    def generate_recommendations(self, listing: dict, audit: ListingAudit) -> dict:
        """Generate actionable improvement recommendations for a listing."""
        listing_id = listing.get("listing_id", listing.get("id", "unknown"))

        # Determine priority based on score thresholds
        if audit.total_score < 40:
            priority = "high"
        elif audit.total_score < 65:
            priority = "medium"
        else:
            priority = "low"

        # Research keywords for this listing
        product_name = listing.get("title", "digital product")
        seed = product_name.split("|")[0].strip() if "|" in product_name else product_name
        # Take first 3 meaningful words as seed
        seed_words = [w for w in seed.lower().split() if len(w) > 2][:3]
        keyword_seed = " ".join(seed_words) if seed_words else "digital printable"

        keywords = self.research_keywords(keyword_seed)

        # Generate optimised title
        optimized_title = self.optimize_title(product_name, keywords)

        # Generate suggested tags
        suggested_tags = self.select_tags(keywords, n=13)

        # Build description improvements
        description_improvements: list[str] = []
        for rec in audit.recommendations:
            rec_lower = rec.lower()
            if any(
                term in rec_lower
                for term in ["description", "section", "bullet", "keyword", "spec", "dimension"]
            ):
                description_improvements.append(rec)

        if not description_improvements:
            description_improvements.append(
                "Consider adding a WHAT'S INCLUDED section listing all files."
            )
            description_improvements.append(
                "Add a HOW TO USE section with step-by-step instructions."
            )

        # Build image suggestions
        image_suggestions: list[str] = []
        for rec in audit.recommendations:
            rec_lower = rec.lower()
            if any(
                term in rec_lower
                for term in ["image", "photo", "mockup", "upload", "naming", "included"]
            ):
                image_suggestions.append(rec)

        if not image_suggestions:
            image_suggestions.append("Add a lifestyle mockup showing the product in context.")
            image_suggestions.append("Include a close-up detail shot of the design.")

        result = {
            "listing_id": str(listing_id),
            "priority": priority,
            "current_score": audit.total_score,
            "optimized_title": optimized_title,
            "suggested_tags": suggested_tags,
            "description_improvements": description_improvements,
            "image_suggestions": image_suggestions,
        }

        logger.info(
            "Generated recommendations for listing %s (priority=%s, score=%d)",
            listing_id, priority, audit.total_score,
        )
        return result

    # ------------------------------------------------------------------
    # Notion persistence
    # ------------------------------------------------------------------

    def save_keywords_to_notion(self, keywords: list[dict]) -> list[str]:
        """Create pages in the SEO Keywords Notion database.

        Each keyword dict should have: keyword, relevance_score,
        estimated_volume, competition_level, composite.

        Returns a list of created page IDs.
        """
        db_id = os.getenv("NOTION_SEO_KEYWORDS_DB", "")
        if not db_id:
            logger.error("NOTION_SEO_KEYWORDS_DB env var not set")
            return []

        page_ids: list[str] = []
        url = f"{NOTION_API_URL}/pages"
        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for kw in keywords:
            payload = {
                "parent": {"database_id": db_id},
                "properties": {
                    "Keyword": {
                        "title": [{"text": {"content": kw["keyword"]}}],
                    },
                    "Composite Score": {"number": kw.get("composite", 0)},
                    "Relevance": {"number": kw.get("relevance_score", 0)},
                    "Volume": {"number": kw.get("estimated_volume", 0)},
                    "Competition": {"number": kw.get("competition_level", 0)},
                    "Category": {
                        "select": {"name": kw.get("category", "General")},
                    },
                    "Researched Date": {"date": {"start": today_iso}},
                },
            }

            try:
                resp = requests.post(
                    url, headers=self._get_notion_headers(), json=payload, timeout=10
                )
                resp.raise_for_status()
                page_id = resp.json().get("id", "")
                page_ids.append(page_id)
                logger.debug("Created keyword page: %s → %s", kw["keyword"], page_id)
            except Exception as exc:
                logger.error("Failed to save keyword '%s': %s", kw["keyword"], exc)

            # Respect Notion rate limits
            time.sleep(0.35)

        logger.info("Saved %d/%d keywords to Notion", len(page_ids), len(keywords))
        return page_ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def run_tests() -> None:
    """Run built-in self-tests and print results."""
    optimizer = SEOOptimizer()
    passed = 0
    failed = 0
    total = 0

    def assert_test(name: str, condition: bool, detail: str = "") -> None:
        nonlocal passed, failed, total
        total += 1
        if condition:
            passed += 1
            print(f"  ✅ {name}")
        else:
            failed += 1
            print(f"  ❌ {name}{' — ' + detail if detail else ''}")

    # ------------------------------------------------------------------
    print("\n── test_title_scoring ──")
    # ------------------------------------------------------------------
    good_title = (
        "Budget Planner Printable | Monthly Finance Tracker PDF | "
        "Minimalist Expense Log Digital Download | Money Management Template"
    )
    good_score, good_recs = optimizer._score_title(good_title)
    assert_test(
        "Good title scores ≥ 18",
        good_score >= 18,
        f"got {good_score}, recs={good_recs}",
    )

    bad_title = "planner"
    bad_score, bad_recs = optimizer._score_title(bad_title)
    assert_test(
        "Bad title scores ≤ 8",
        bad_score <= 8,
        f"got {bad_score}, recs={bad_recs}",
    )

    # ------------------------------------------------------------------
    print("\n── test_tag_scoring ──")
    # ------------------------------------------------------------------
    full_tags = [
        "budget planner", "finance tracker", "monthly printable",
        "expense log pdf", "money management", "digital download",
        "minimalist planner", "editable template", "instant download",
        "household budget", "savings tracker", "debt payoff", "planner",
    ]
    full_score, full_recs = optimizer._score_tags(full_tags)
    assert_test(
        "Full 13 multi-word tags score ≥ 15",
        full_score >= 15,
        f"got {full_score}, recs={full_recs}",
    )

    weak_tags = ["budget", "planner", "money", "pdf", "cute"]
    weak_score, weak_recs = optimizer._score_tags(weak_tags)
    assert_test(
        "5 single-word tags score ≤ 8",
        weak_score <= 8,
        f"got {weak_score}, recs={weak_recs}",
    )

    # ------------------------------------------------------------------
    print("\n── test_keyword_expansion ──")
    # ------------------------------------------------------------------
    dupes = [
        {"keyword": "budget planner", "composite": 80},
        {"keyword": "budget planner", "composite": 80},
        {"keyword": "finance tracker", "composite": 70},
        {"keyword": "finance tracker", "composite": 70},
        {"keyword": "budget planner", "composite": 80},
    ]
    researched = optimizer.research_keywords("budget planner")
    kw_set = {kw["keyword"] for kw in researched}
    assert_test(
        "Deduplication produces unique keywords",
        len(kw_set) == len(researched),
        f"total={len(researched)}, unique={len(kw_set)}",
    )

    # ------------------------------------------------------------------
    print("\n── test_tag_selection ──")
    # ------------------------------------------------------------------
    many_keywords = optimizer.research_keywords("wedding invitation")
    selected = optimizer.select_tags(many_keywords, n=13)

    assert_test(
        "Returns ≤ 13 tags",
        len(selected) <= 13,
        f"got {len(selected)}",
    )

    # Diversity: no two tags share > 50 % words
    diversity_ok = True
    for i, tag_a in enumerate(selected):
        words_a = set(tag_a.lower().split())
        for j, tag_b in enumerate(selected):
            if i >= j:
                continue
            words_b = set(tag_b.lower().split())
            overlap = len(words_a & words_b)
            smaller = min(len(words_a), len(words_b))
            if smaller > 0 and overlap / smaller > 0.5:
                diversity_ok = False
                logger.warning(
                    "Diversity violation: '%s' ↔ '%s' (overlap=%d/%d)",
                    tag_a, tag_b, overlap, smaller,
                )
    assert_test(
        "No two tags share > 50 % words",
        diversity_ok,
    )

    # ------------------------------------------------------------------
    print(f"\n{'─' * 40}")
    print(f"Results: {passed}/{total} passed, {failed} failed")
    if failed:
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI interface for the SEO Optimizer."""
    parser = argparse.ArgumentParser(
        description="SEO analysis and optimisation engine for Etsy listings.",
    )
    parser.add_argument(
        "--research", metavar="SEED",
        help="Research keywords starting from a seed phrase.",
    )
    parser.add_argument(
        "--category", metavar="CAT",
        help="Narrow keyword research to a category.",
    )
    parser.add_argument(
        "--audit", metavar="LISTING_ID",
        help="Audit a single listing by ID (fetched from Notion).",
    )
    parser.add_argument(
        "--audit-all", action="store_true",
        help="Audit all active listings in Notion.",
    )
    parser.add_argument(
        "--optimize", metavar="LISTING_ID",
        help="Generate optimised title/tags/description for a listing.",
    )
    parser.add_argument(
        "--top", type=int, default=20,
        help="Number of top keywords to display (default: 20).",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Enable verbose / debug logging.",
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run built-in self-tests.",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.test:
        run_tests()
        return

    optimizer = SEOOptimizer()

    # ── Research ─────────────────────────────────────────────────────
    if args.research:
        keywords = optimizer.research_keywords(args.research, category=args.category)
        top_n = keywords[: args.top]
        print(f"\n🔍 Top {len(top_n)} keywords for '{args.research}':\n")
        print(f"{'#':<4} {'Keyword':<35} {'Rel':>4} {'Vol':>4} {'Comp':>4} {'Score':>6}")
        print("─" * 62)
        for i, kw in enumerate(top_n, 1):
            print(
                f"{i:<4} {kw['keyword']:<35} "
                f"{kw['relevance_score']:>4} "
                f"{kw['estimated_volume']:>4} "
                f"{kw['competition_level']:>4} "
                f"{kw['composite']:>6.1f}"
            )

        # Suggest tags from these keywords
        suggested_tags = optimizer.select_tags(keywords, n=13)
        print(f"\n🏷️  Suggested tags ({len(suggested_tags)}):")
        for tag in suggested_tags:
            print(f"  • {tag}")

        # Suggest title
        title = optimizer.optimize_title(args.research, keywords)
        print(f"\n📝 Suggested title ({len(title)} chars):")
        print(f"  {title}")
        return

    # ── Audit single listing ─────────────────────────────────────────
    if args.audit:
        db_id = os.getenv("NOTION_LISTINGS_DB", "")
        if not db_id:
            print("❌ NOTION_LISTINGS_DB environment variable not set.")
            sys.exit(1)

        # Fetch listing from Notion
        url = f"{NOTION_API_URL}/databases/{db_id}/query"
        payload = {
            "filter": {
                "property": "Listing ID",
                "rich_text": {"equals": args.audit},
            },
            "page_size": 1,
        }
        try:
            resp = requests.post(
                url, headers=optimizer._get_notion_headers(), json=payload, timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:
            print(f"❌ Failed to fetch listing: {exc}")
            sys.exit(1)

        if not results:
            print(f"❌ No listing found with ID '{args.audit}'.")
            sys.exit(1)

        listing = optimizer._notion_page_to_listing(results[0])
        audit = optimizer.audit_listing(listing)

        print(f"\n📊 Audit for listing {audit.listing_id}:")
        print(f"   Title:       {audit.title_score}/25")
        print(f"   Tags:        {audit.tag_score}/20")
        print(f"   Description: {audit.description_score}/20")
        print(f"   Images:      {audit.image_score}/20")
        print(f"   Attributes:  {audit.attribute_score}/15")
        print(f"   ────────────────────")
        print(f"   TOTAL:       {audit.total_score}/100")
        if audit.recommendations:
            print(f"\n💡 Recommendations ({len(audit.recommendations)}):")
            for rec in audit.recommendations:
                print(f"   • {rec}")
        return

    # ── Audit all listings ───────────────────────────────────────────
    if args.audit_all:
        audits = optimizer.audit_all_listings()
        if not audits:
            print("⚠️  No active listings found (or Notion query failed).")
            return
        print(f"\n📊 Audited {len(audits)} listings (sorted worst → best):\n")
        print(f"{'Listing ID':<20} {'Title':>6} {'Tags':>5} {'Desc':>5} {'Img':>5} {'Attr':>5} {'Total':>6}")
        print("─" * 58)
        for a in audits:
            print(
                f"{a.listing_id:<20} "
                f"{a.title_score:>5}/25 "
                f"{a.tag_score:>4}/20 "
                f"{a.description_score:>4}/20 "
                f"{a.image_score:>4}/20 "
                f"{a.attribute_score:>4}/15 "
                f"{a.total_score:>5}/100"
            )
        return

    # ── Optimize single listing ──────────────────────────────────────
    if args.optimize:
        db_id = os.getenv("NOTION_LISTINGS_DB", "")
        if not db_id:
            print("❌ NOTION_LISTINGS_DB environment variable not set.")
            sys.exit(1)

        url = f"{NOTION_API_URL}/databases/{db_id}/query"
        payload = {
            "filter": {
                "property": "Listing ID",
                "rich_text": {"equals": args.optimize},
            },
            "page_size": 1,
        }
        try:
            resp = requests.post(
                url, headers=optimizer._get_notion_headers(), json=payload, timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
        except Exception as exc:
            print(f"❌ Failed to fetch listing: {exc}")
            sys.exit(1)

        if not results:
            print(f"❌ No listing found with ID '{args.optimize}'.")
            sys.exit(1)

        listing = optimizer._notion_page_to_listing(results[0])
        audit = optimizer.audit_listing(listing)
        recs = optimizer.generate_recommendations(listing, audit)

        print(f"\n🚀 Optimisation for listing {recs['listing_id']}:")
        print(f"   Priority: {recs['priority'].upper()}")
        print(f"   Current score: {recs['current_score']}/100\n")
        print(f"📝 Optimised title ({len(recs['optimized_title'])} chars):")
        print(f"   {recs['optimized_title']}\n")
        print(f"🏷️  Suggested tags ({len(recs['suggested_tags'])}):")
        for tag in recs["suggested_tags"]:
            print(f"   • {tag}")
        if recs["description_improvements"]:
            print(f"\n📄 Description improvements:")
            for imp in recs["description_improvements"]:
                print(f"   • {imp}")
        if recs["image_suggestions"]:
            print(f"\n🖼️  Image suggestions:")
            for sug in recs["image_suggestions"]:
                print(f"   • {sug}")
        return

    # ── No action specified ──────────────────────────────────────────
    parser.print_help()


if __name__ == "__main__":
    main()
