#!/usr/bin/env python3
"""Credit card spending optimization engine.

Determines optimal card per spending category, calculates rewards earned
vs. rewards possible, and provides per-transaction recommendations.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from typing import Any

MERCHANT_CATEGORIES: dict[str, str] = {
    "DOORDASH": "dining", "GRUBHUB": "dining", "UBER EATS": "dining",
    "UBEREATS": "dining", "TACO BELL": "dining", "MCDONALDS": "dining",
    "CHIPOTLE": "dining", "STARBUCKS": "dining", "CHICK-FIL-A": "dining",
    "PANERA": "dining", "SONIC": "dining", "WINGSTOP": "dining",
    "PIZZA HUT": "dining", "DOMINOS": "dining", "EINSTEIN": "dining",
    "BURGER KING": "dining", "WENDYS": "dining", "SUBWAY": "dining",
    "PANDA EXPRESS": "dining", "OLIVE GARDEN": "dining",
    "APPLEBEES": "dining", "IHOP": "dining", "DENNYS": "dining",
    "BUFFALO WILD WINGS": "dining", "FIVE GUYS": "dining",
    "POPEYES": "dining", "ARBYS": "dining", "JACK IN THE BOX": "dining",
    "WHATABURGER": "dining", "CRACKER BARREL": "dining",
    "RED LOBSTER": "dining", "LONGHORN": "dining",
    "OUTBACK": "dining", "TEXAS ROADHOUSE": "dining",
    "CHEESECAKE FACTORY": "dining", "CANES": "dining",
    "RAISING CANES": "dining", "CULVERS": "dining",

    "HY-VEE": "groceries", "HYVEE": "groceries", "ALDI": "groceries",
    "COSTCO": "groceries", "COSTCO WHSE": "groceries",
    "SAMS CLUB": "groceries", "SAM'S CLUB": "groceries",
    "TRADER JOE": "groceries", "WHOLE FOODS": "groceries",
    "KROGER": "groceries", "PRICE CHOPPER": "groceries",
    "PUBLIX": "groceries", "SAFEWAY": "groceries",
    "SPROUTS": "groceries", "FOOD LION": "groceries",

    "TARGET": "groceries", "WALMART": "groceries", "WAL-MART": "groceries",

    "SHELL": "gas", "SHELL OIL": "gas", "QT": "gas",
    "QUIKTRIP": "gas", "BP": "gas", "CASEY": "gas",
    "PHILLIPS 66": "gas", "CHEVRON": "gas", "EXXON": "gas",
    "CONOCO": "gas", "MARATHON": "gas", "VALERO": "gas",
    "SPEEDWAY": "gas", "MURPHY": "gas", "RACETRAC": "gas",

    "WALGREENS": "drugstores", "CVS": "drugstores",
    "RITE AID": "drugstores", "DUANE READE": "drugstores",

    "NETFLIX": "streaming", "SPOTIFY": "streaming",
    "YOUTUBE TV": "streaming", "GOOGLE YOUTUBE": "streaming",
    "HBO MAX": "streaming", "APPLE TV": "streaming",
    "DISNEY PLUS": "streaming", "HULU": "streaming",
    "PARAMOUNT": "streaming", "PEACOCK": "streaming",
    "AMAZON PRIME VIDEO": "streaming",

    "AMAZON": "amazon", "AMAZON.COM": "amazon", "AMZN": "amazon",
    "AMZN MKTP": "amazon", "AMAZON PRIME": "amazon",

    "UNITED AIRLINES": "travel", "DELTA": "travel",
    "AMERICAN AIRLINES": "travel", "SOUTHWEST": "travel",
    "JETBLUE": "travel", "FRONTIER": "travel",
    "MARRIOTT": "travel", "HILTON": "travel", "HYATT": "travel",
    "AIRBNB": "travel", "VRBO": "travel",
    "HERTZ": "travel", "ENTERPRISE": "travel", "AVIS": "travel",
    "UBER": "travel", "LYFT": "travel",
    "EXPEDIA": "travel", "BOOKING.COM": "travel",
    "HOTELS.COM": "travel",

    "HOME DEPOT": "general", "LOWES": "general",
    "MENARDS": "general", "BED BATH": "general",
    "DOLLAR TREE": "general", "DOLLAR GENERAL": "general",
    "BEST BUY": "general", "APPLE STORE": "general",
    "IKEA": "general", "MICHAELS": "general",
}

DEFAULT_CARDS: list[dict[str, Any]] = [
    {
        "name": "Chase Sapphire Reserve",
        "network": "chase",
        "annual_fee": 550,
        "point_value_cents": 1.5,
        "earning_rates": {
            "dining": 3.0,
            "travel": 3.0,
            "streaming": 1.0,
            "groceries": 1.0,
            "gas": 1.0,
            "drugstores": 1.0,
            "amazon": 1.0,
            "general": 1.0
        },
        "credits": [
            {"name": "Travel Credit", "amount": 300},
            {"name": "DoorDash DashPass", "amount": 60}
        ]
    },
    {
        "name": "Chase Freedom Flex",
        "network": "chase",
        "annual_fee": 0,
        "point_value_cents": 1.5,
        "earning_rates": {
            "dining": 3.0,
            "travel": 1.0,
            "streaming": 1.0,
            "groceries": 1.0,
            "gas": 1.0,
            "drugstores": 1.0,
            "amazon": 1.0,
            "general": 1.0
        },
        "quarterly_categories": {}
    },
    {
        "name": "Chase Freedom Unlimited",
        "network": "chase",
        "annual_fee": 0,
        "point_value_cents": 1.5,
        "earning_rates": {
            "dining": 3.0,
            "travel": 1.5,
            "streaming": 1.5,
            "groceries": 1.5,
            "gas": 1.5,
            "drugstores": 1.5,
            "amazon": 1.5,
            "general": 1.5
        }
    },
    {
        "name": "Amazon Prime Visa",
        "network": "other",
        "annual_fee": 0,
        "point_value_cents": 1.0,
        "earning_rates": {
            "dining": 2.0,
            "travel": 1.0,
            "streaming": 1.0,
            "groceries": 1.0,
            "gas": 1.0,
            "drugstores": 1.0,
            "amazon": 5.0,
            "general": 1.0
        }
    },
    {
        "name": "Capital One Venture X",
        "network": "other",
        "annual_fee": 395,
        "point_value_cents": 1.0,
        "earning_rates": {
            "dining": 2.0,
            "travel": 2.0,
            "streaming": 2.0,
            "groceries": 2.0,
            "gas": 2.0,
            "drugstores": 2.0,
            "amazon": 2.0,
            "general": 2.0
        },
        "credits": [
            {"name": "Travel Credit", "amount": 300}
        ]
    }
]

QUARTERLY_BONUS: dict[str, dict[str, list[str]]] = {
    "2026": {
        "Q1": ["groceries", "gas"],
        "Q2": ["streaming", "drugstores"],
        "Q3": ["gas", "dining"],
        "Q4": ["amazon", "general"]
    }
}

QUARTERLY_RATE = 5.0
QUARTERLY_CAP = 1500.0


def classify_merchant(merchant: str, custom_mappings: dict[str, str] | None = None) -> str:
    normalized = merchant.upper().strip()
    if custom_mappings:
        for key, cat in custom_mappings.items():
            if key.upper() in normalized:
                return cat
    for key, cat in MERCHANT_CATEGORIES.items():
        if key in normalized:
            return cat
    return "general"


def _get_effective_rate(card: dict[str, Any], category: str, quarter: str | None, year: str | None) -> float:
    base_rate = card.get("earning_rates", {}).get(category, 1.0)

    if card["name"] == "Chase Freedom Flex" and quarter and year:
        bonus_cats = QUARTERLY_BONUS.get(year, {}).get(quarter, [])
        if category in bonus_cats:
            return max(base_rate, QUARTERLY_RATE)

    return base_rate


def _calc_reward_value(amount: float, rate: float, point_value_cents: float) -> float:
    points = amount * rate
    return round(points * point_value_cents / 100, 2)


def find_optimal_card(category: str, cards: list[dict[str, Any]], quarter: str | None = None, year: str | None = None) -> dict[str, Any]:
    best_card = None
    best_value = 0.0
    best_rate = 0.0

    for card in cards:
        rate = _get_effective_rate(card, category, quarter, year)
        value_per_dollar = rate * card.get("point_value_cents", 1.0) / 100
        if value_per_dollar > best_value:
            best_value = value_per_dollar
            best_card = card
            best_rate = rate

    return {
        "card": best_card["name"] if best_card else "Unknown",
        "rate": best_rate,
        "point_value_cents": best_card.get("point_value_cents", 1.0) if best_card else 1.0,
        "value_per_dollar": round(best_value, 4)
    }


def analyze_transactions(transactions: list[dict[str, Any]], cards: list[dict[str, Any]], quarter: str | None = None, year: str | None = None, custom_mappings: dict[str, str] | None = None) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    category_summary: dict[str, dict[str, float]] = defaultdict(lambda: {
        "total_spent": 0.0, "actual_rewards": 0.0, "optimal_rewards": 0.0, "missed_rewards": 0.0
    })
    total_actual = 0.0
    total_optimal = 0.0

    card_lookup = {c["name"]: c for c in cards}

    for txn in transactions:
        merchant = txn.get("merchant", txn.get("description", ""))
        amount = abs(float(txn.get("amount", 0)))
        card_used = txn.get("card", "")
        txn_date = txn.get("date", "")

        category = txn.get("category") or classify_merchant(merchant, custom_mappings)

        actual_card = card_lookup.get(card_used)
        if actual_card:
            actual_rate = _get_effective_rate(actual_card, category, quarter, year)
            actual_reward = _calc_reward_value(amount, actual_rate, actual_card.get("point_value_cents", 1.0))
        else:
            actual_rate = 0.0
            actual_reward = 0.0

        optimal = find_optimal_card(category, cards, quarter, year)
        optimal_reward = _calc_reward_value(amount, optimal["rate"], optimal["point_value_cents"])
        missed = round(optimal_reward - actual_reward, 2)

        result = {
            "date": txn_date,
            "merchant": merchant,
            "amount": amount,
            "category": category,
            "card_used": card_used,
            "actual_rate": actual_rate,
            "actual_reward": actual_reward,
            "optimal_card": optimal["card"],
            "optimal_rate": optimal["rate"],
            "optimal_reward": optimal_reward,
            "missed_reward": max(missed, 0),
            "was_optimal": card_used == optimal["card"]
        }
        results.append(result)

        cat = category_summary[category]
        cat["total_spent"] += amount
        cat["actual_rewards"] += actual_reward
        cat["optimal_rewards"] += optimal_reward
        cat["missed_rewards"] += max(missed, 0)

        total_actual += actual_reward
        total_optimal += optimal_reward

    cat_output = {}
    for cat_name, vals in category_summary.items():
        optimal_info = find_optimal_card(cat_name, cards, quarter, year)
        cat_output[cat_name] = {
            "total_spent": round(vals["total_spent"], 2),
            "actual_rewards": round(vals["actual_rewards"], 2),
            "optimal_rewards": round(vals["optimal_rewards"], 2),
            "missed_rewards": round(vals["missed_rewards"], 2),
            "best_card": optimal_info["card"],
            "best_rate": optimal_info["rate"]
        }

    total_missed = round(total_optimal - total_actual, 2)
    annual_projection = round(total_actual * 12, 2) if transactions else 0.0

    csr = card_lookup.get("Chase Sapphire Reserve")
    roi: dict[str, Any] = {}
    if csr:
        credits_value = sum(c["amount"] for c in csr.get("credits", []))
        annual_rewards = annual_projection
        net_value = round(annual_rewards + credits_value - csr["annual_fee"], 2)
        roi = {
            "card": "Chase Sapphire Reserve",
            "annual_fee": csr["annual_fee"],
            "annual_credits": credits_value,
            "projected_annual_rewards": annual_rewards,
            "net_annual_value": net_value,
            "breakeven_monthly_spend": round((csr["annual_fee"] - credits_value) / 12 / 0.045, 2) if credits_value < csr["annual_fee"] else 0.0,
            "worth_keeping": net_value > 0
        }

    optimal_count = sum(1 for r in results if r["was_optimal"])

    return {
        "generated": date.today().isoformat(),
        "quarter": quarter,
        "year": year,
        "transaction_count": len(results),
        "optimal_usage_rate": round(optimal_count / max(len(results), 1) * 100, 1),
        "total_spent": round(sum(r["amount"] for r in results), 2),
        "total_actual_rewards": round(total_actual, 2),
        "total_optimal_rewards": round(total_optimal, 2),
        "total_missed_rewards": round(max(total_missed, 0), 2),
        "monthly_rewards": round(total_actual, 2),
        "annual_projection": annual_projection,
        "category_summary": cat_output,
        "category_card_guide": {
            cat: find_optimal_card(cat, cards, quarter, year)
            for cat in ["dining", "groceries", "gas", "travel", "drugstores", "streaming", "amazon", "general"]
        },
        "sapphire_reserve_roi": roi,
        "transactions": results
    }


def load_transactions(path: str) -> list[dict[str, Any]]:
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if "transactions" in data:
        return data["transactions"]
    raise ValueError(f"Cannot parse transactions from {path}")


def load_cards(path: str) -> list[dict[str, Any]]:
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if "cards" in data:
        return data["cards"]
    # Handle chase_rewards.json nested structure — fall back to built-in defaults
    # since the JSON is a reference doc, not a direct card config
    if "chase_trifecta" in data or "optimal_card_selection" in data:
        return DEFAULT_CARDS
    raise ValueError(f"Cannot parse cards from {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Credit card rewards optimization engine")
    parser.add_argument("--transactions", required=True, help="Path to transactions JSON")
    parser.add_argument("--cards", type=str, default=None, help="Path to card config JSON (uses defaults if omitted)")
    parser.add_argument("--quarter", type=str, default=None, help="Current quarter (Q1-Q4) for Freedom Flex rotating categories")
    parser.add_argument("--year", type=str, default=None, help="Year for quarterly category lookup")
    args = parser.parse_args()

    txns = load_transactions(args.transactions)
    cards = load_cards(args.cards) if args.cards else DEFAULT_CARDS
    result = analyze_transactions(txns, cards, args.quarter, args.year)
    json.dump(result, sys.stdout, indent=2)
    print()
