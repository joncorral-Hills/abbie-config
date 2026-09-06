#!/usr/bin/env python3
"""Amortization and payoff scenario engine.

Supports avalanche (highest rate first), snowball (lowest balance first),
and minimum-only strategies with optional extra payments.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, timedelta
from typing import Any


def calculate_minimum_payment(principal: float, annual_rate: float, term_months: int) -> float:
    if annual_rate == 0:
        return principal / max(term_months, 1)
    r = annual_rate / 12
    return principal * (r * (1 + r) ** term_months) / ((1 + r) ** term_months - 1)


def calculate_amortization(principal: float, annual_rate: float, monthly_payment: float) -> list[dict[str, Any]]:
    schedule: list[dict[str, Any]] = []
    balance = principal
    r = annual_rate / 12
    month = 0

    while balance > 0.005 and month < 600:
        month += 1
        interest = balance * r
        principal_paid = min(monthly_payment - interest, balance)
        if principal_paid <= 0:
            schedule.append({
                "month": month,
                "payment": round(interest, 2),
                "principal": 0.0,
                "interest": round(interest, 2),
                "balance": round(balance, 2),
                "error": "Payment does not cover interest"
            })
            break
        balance -= principal_paid
        if balance < 0:
            balance = 0
        actual_payment = principal_paid + interest
        schedule.append({
            "month": month,
            "payment": round(actual_payment, 2),
            "principal": round(principal_paid, 2),
            "interest": round(interest, 2),
            "balance": round(balance, 2)
        })

    return schedule


def _payoff_single(balance: float, annual_rate: float, monthly_payment: float) -> dict[str, Any]:
    if balance <= 0:
        return {"months": 0, "total_interest": 0.0, "total_paid": 0.0}

    r = annual_rate / 12
    total_interest = 0.0
    total_paid = 0.0
    months = 0
    remaining = balance

    while remaining > 0.005 and months < 600:
        months += 1
        interest = remaining * r
        if monthly_payment <= interest:
            return {"months": -1, "total_interest": -1, "total_paid": -1, "error": "Payment does not cover interest"}
        principal_paid = min(monthly_payment - interest, remaining)
        remaining -= principal_paid
        if remaining < 0:
            remaining = 0
        actual = principal_paid + interest
        total_interest += interest
        total_paid += actual

    return {
        "months": months,
        "total_interest": round(total_interest, 2),
        "total_paid": round(total_paid, 2)
    }


def _run_strategy(debts: list[dict[str, Any]], extra_payment: float, order_key: str, reverse: bool) -> dict[str, Any]:
    active = []
    for d in debts:
        active.append({
            "name": d["name"],
            "balance": float(d["balance"]),
            "rate": float(d["rate"]),
            "min_payment": float(d["min_payment"]),
            "original_balance": float(d["balance"]),
            "total_interest": 0.0,
            "total_paid": 0.0,
            "payoff_month": 0
        })

    if order_key == "rate":
        active.sort(key=lambda x: x["rate"], reverse=reverse)
    else:
        active.sort(key=lambda x: x["balance"], reverse=reverse)

    month = 0
    results: list[dict[str, Any]] = []
    freed_payments = 0.0

    while any(d["balance"] > 0.005 for d in active) and month < 600:
        month += 1
        pool = extra_payment + freed_payments

        for d in active:
            if d["balance"] <= 0.005:
                continue
            r = d["rate"] / 12
            interest = d["balance"] * r
            d["total_interest"] += interest
            payment = d["min_payment"]
            principal = payment - interest
            d["balance"] -= principal
            d["total_paid"] += payment
            if d["balance"] < 0:
                d["balance"] = 0

        for d in active:
            if d["balance"] <= 0.005 or pool <= 0:
                continue
            extra_applied = min(pool, d["balance"])
            d["balance"] -= extra_applied
            d["total_paid"] += extra_applied
            pool -= extra_applied
            if d["balance"] < 0:
                d["balance"] = 0

        for d in active:
            if d["balance"] <= 0.005 and d["payoff_month"] == 0:
                d["payoff_month"] = month
                freed_payments += d["min_payment"]

    start = date.today().replace(day=1)
    for d in active:
        payoff_month = d["payoff_month"] if d["payoff_month"] > 0 else month
        payoff_date = _add_months(start, payoff_month)
        results.append({
            "name": d["name"],
            "original_balance": round(d["original_balance"], 2),
            "rate": d["rate"],
            "payoff_month": payoff_month,
            "payoff_date": payoff_date.isoformat(),
            "total_interest": round(d["total_interest"], 2),
            "total_paid": round(d["total_paid"], 2),
            "interest_saved_vs_minimum": 0.0
        })

    total_months = max(r["payoff_month"] for r in results) if results else 0
    total_interest = round(sum(r["total_interest"] for r in results), 2)
    total_paid = round(sum(r["total_paid"] for r in results), 2)

    return {
        "debts": results,
        "total_months": total_months,
        "total_interest": total_interest,
        "total_paid": total_paid,
        "last_payoff_date": _add_months(start, total_months).isoformat()
    }


def _add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    import calendar as cal
    day = min(d.day, cal.monthrange(year, month)[1])
    return date(year, month, day)


def run_minimum(debts: list[dict[str, Any]]) -> dict[str, Any]:
    return _run_strategy(debts, 0.0, "balance", False)


def run_avalanche(debts: list[dict[str, Any]], extra_payment: float) -> dict[str, Any]:
    return _run_strategy(debts, extra_payment, "rate", True)


def run_snowball(debts: list[dict[str, Any]], extra_payment: float) -> dict[str, Any]:
    return _run_strategy(debts, extra_payment, "balance", False)


def compare_strategies(debts: list[dict[str, Any]], extra_payment: float) -> dict[str, Any]:
    minimum = run_minimum(debts)
    avalanche = run_avalanche(debts, extra_payment)
    snowball = run_snowball(debts, extra_payment)

    for strat in [avalanche, snowball]:
        for debt in strat["debts"]:
            min_match = next((m for m in minimum["debts"] if m["name"] == debt["name"]), None)
            if min_match:
                debt["interest_saved_vs_minimum"] = round(min_match["total_interest"] - debt["total_interest"], 2)

    return {
        "extra_payment": extra_payment,
        "minimum": {
            "strategy": "minimum",
            "total_months": minimum["total_months"],
            "total_interest": minimum["total_interest"],
            "total_paid": minimum["total_paid"],
            "last_payoff_date": minimum["last_payoff_date"]
        },
        "avalanche": {
            "strategy": "avalanche",
            "total_months": avalanche["total_months"],
            "total_interest": avalanche["total_interest"],
            "total_paid": avalanche["total_paid"],
            "last_payoff_date": avalanche["last_payoff_date"],
            "interest_saved": round(minimum["total_interest"] - avalanche["total_interest"], 2),
            "months_saved": minimum["total_months"] - avalanche["total_months"],
            "debts": avalanche["debts"]
        },
        "snowball": {
            "strategy": "snowball",
            "total_months": snowball["total_months"],
            "total_interest": snowball["total_interest"],
            "total_paid": snowball["total_paid"],
            "last_payoff_date": snowball["last_payoff_date"],
            "interest_saved": round(minimum["total_interest"] - snowball["total_interest"], 2),
            "months_saved": minimum["total_months"] - snowball["total_months"],
            "debts": snowball["debts"]
        }
    }


def generate_report(debts: list[dict[str, Any]], strategy: str = "avalanche", extra_payment: float = 0.0, target_debt: str | None = None) -> dict[str, Any]:
    if target_debt:
        filtered = [d for d in debts if d["name"].lower() == target_debt.lower()]
        if not filtered:
            return {"error": f"Debt '{target_debt}' not found", "available": [d["name"] for d in debts]}
        debt = filtered[0]
        schedule = calculate_amortization(float(debt["balance"]), float(debt["rate"]), float(debt["min_payment"]) + extra_payment)
        payoff = _payoff_single(float(debt["balance"]), float(debt["rate"]), float(debt["min_payment"]) + extra_payment)
        baseline = _payoff_single(float(debt["balance"]), float(debt["rate"]), float(debt["min_payment"]))
        start = date.today().replace(day=1)
        return {
            "debt": debt["name"],
            "balance": float(debt["balance"]),
            "rate": debt["rate"],
            "min_payment": float(debt["min_payment"]),
            "extra_payment": extra_payment,
            "effective_payment": float(debt["min_payment"]) + extra_payment,
            "payoff_months": payoff["months"],
            "payoff_date": _add_months(start, payoff["months"]).isoformat() if payoff["months"] > 0 else "N/A",
            "total_interest": payoff["total_interest"],
            "total_paid": payoff["total_paid"],
            "baseline_months": baseline["months"],
            "baseline_interest": baseline["total_interest"],
            "interest_saved": round(baseline["total_interest"] - payoff["total_interest"], 2) if payoff["total_interest"] >= 0 else 0,
            "months_saved": baseline["months"] - payoff["months"] if payoff["months"] >= 0 else 0,
            "amortization_schedule": schedule[:12]
        }

    comparison = compare_strategies(debts, extra_payment)

    if strategy == "avalanche":
        primary = comparison["avalanche"]
    elif strategy == "snowball":
        primary = comparison["snowball"]
    else:
        primary = comparison["minimum"]

    total_min_payments = sum(float(d["min_payment"]) for d in debts)
    total_balances = sum(float(d["balance"]) for d in debts)

    return {
        "generated": date.today().isoformat(),
        "strategy": strategy,
        "extra_payment": extra_payment,
        "total_monthly_minimums": round(total_min_payments, 2),
        "total_monthly_with_extra": round(total_min_payments + extra_payment, 2),
        "total_debt_balance": round(total_balances, 2),
        "primary_result": primary,
        "comparison": {
            "minimum_only": comparison["minimum"],
            "avalanche": {
                "total_months": comparison["avalanche"]["total_months"],
                "total_interest": comparison["avalanche"]["total_interest"],
                "interest_saved": comparison["avalanche"]["interest_saved"],
                "months_saved": comparison["avalanche"]["months_saved"]
            },
            "snowball": {
                "total_months": comparison["snowball"]["total_months"],
                "total_interest": comparison["snowball"]["total_interest"],
                "interest_saved": comparison["snowball"]["interest_saved"],
                "months_saved": comparison["snowball"]["months_saved"]
            }
        }
    }


def load_inventory(path: str) -> list[dict[str, Any]]:
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if "debts" in data:
        return data["debts"]
    raise ValueError(f"Cannot parse debt inventory from {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debt payoff calculator and scenario engine")
    parser.add_argument("--inventory", required=True, help="Path to debt inventory JSON")
    parser.add_argument("--extra-payment", type=float, default=0.0, help="Extra monthly payment to apply")
    parser.add_argument("--strategy", choices=["avalanche", "snowball", "minimum"], default="avalanche")
    parser.add_argument("--target-debt", type=str, default=None, help="Analyze a single debt by name")
    args = parser.parse_args()

    debts = load_inventory(args.inventory)
    report = generate_report(debts, args.strategy, args.extra_payment, args.target_debt)
    json.dump(report, sys.stdout, indent=2)
    print()
