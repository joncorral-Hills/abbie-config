#!/usr/bin/env python3
"""30-day forward checking balance projection.

Models biweekly and semi-monthly pay schedules precisely, handles
recurring bills, and flags dates where balance drops below threshold.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from typing import Any


def _parse_date(d: str) -> date:
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(d, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {d}")


def _biweekly_dates(anchor: str, start: date, end: date) -> list[date]:
    anchor_date = _parse_date(anchor)
    dates = []
    d = anchor_date
    while d <= end:
        if d >= start:
            dates.append(d)
        d += timedelta(days=14)
    d = anchor_date - timedelta(days=14)
    while d >= start:
        dates.append(d)
        d -= timedelta(days=14)
    return sorted(set(dates))


def _semimonthly_dates(days: list[int], start: date, end: date) -> list[date]:
    dates = []
    d = start
    while d <= end:
        if d.day in days:
            dates.append(d)
        d += timedelta(days=1)
    return dates


def _monthly_dates(day: int, start: date, end: date) -> list[date]:
    import calendar as cal
    dates = []
    d = start
    while d <= end:
        target_day = min(day, cal.monthrange(d.year, d.month)[1])
        candidate = d.replace(day=target_day)
        if start <= candidate <= end and candidate not in dates:
            dates.append(candidate)
        if d.month == 12:
            d = d.replace(year=d.year + 1, month=1, day=1)
        else:
            d = d.replace(month=d.month + 1, day=1)
    return sorted(set(dates))


def _resolve_schedule_dates(entry: dict[str, Any], start: date, end: date) -> list[date]:
    schedule = entry.get("schedule", {})
    stype = schedule.get("type", "one_time")

    if stype == "biweekly":
        anchor = schedule.get("anchor")
        if not anchor:
            return []
        return _biweekly_dates(anchor, start, end)

    elif stype == "semi_monthly":
        days = schedule.get("days", [1, 15])
        return _semimonthly_dates(days, start, end)

    elif stype == "monthly":
        day = schedule.get("day", 1)
        return _monthly_dates(day, start, end)

    elif stype == "one_time":
        d = _parse_date(schedule.get("date", entry.get("date", "")))
        if start <= d <= end:
            return [d]
        return []

    elif stype == "weekly":
        dow = schedule.get("day_of_week", 0)
        dates = []
        d = start
        while d <= end:
            if d.weekday() == dow:
                dates.append(d)
            d += timedelta(days=1)
        return dates

    return []


def build_forecast(calendar_entries: list[dict[str, Any]], starting_balance: float, forecast_days: int = 30, threshold: float = 500.0, start_date: date | None = None) -> dict[str, Any]:
    today = start_date or date.today()
    end = today + timedelta(days=forecast_days)

    daily_events: dict[date, list[dict[str, Any]]] = {}
    for entry in calendar_entries:
        dates = _resolve_schedule_dates(entry, today, end)
        amount = float(entry.get("amount", 0))
        for d in dates:
            if d not in daily_events:
                daily_events[d] = []
            daily_events[d].append({
                "name": entry.get("name", "Unknown"),
                "amount": amount,
                "type": entry.get("type", "expense"),
                "category": entry.get("category", "")
            })

    projection: list[dict[str, Any]] = []
    balance = starting_balance
    min_balance = balance
    min_balance_date = today
    alerts: list[dict[str, Any]] = []
    below_threshold = False

    income_dates = []
    for entry in calendar_entries:
        if entry.get("type") == "income":
            income_dates.extend(_resolve_schedule_dates(entry, today, end))
    income_dates = sorted(set(income_dates))

    for day_offset in range(forecast_days + 1):
        current = today + timedelta(days=day_offset)
        events = daily_events.get(current, [])
        day_total = 0.0

        for ev in events:
            if ev["type"] == "income":
                day_total += ev["amount"]
            else:
                day_total -= ev["amount"]

        balance += day_total

        day_record: dict[str, Any] = {
            "date": current.isoformat(),
            "day_of_week": current.strftime("%A"),
            "balance": round(balance, 2),
            "net_change": round(day_total, 2)
        }
        if events:
            day_record["events"] = events

        projection.append(day_record)

        if balance < min_balance:
            min_balance = balance
            min_balance_date = current

        if balance < threshold and not below_threshold:
            below_threshold = True
            next_income = next((d for d in income_dates if d > current), None)
            alert = {
                "type": "BALANCE_BELOW_THRESHOLD",
                "date": current.isoformat(),
                "balance": round(balance, 2),
                "threshold": threshold,
                "message": f"ALERT: Balance projected to hit ${balance:,.2f} on {current.isoformat()}"
            }
            if next_income:
                alert["next_income_date"] = next_income.isoformat()
                alert["message"] += f" before next income on {next_income.isoformat()}"
            alerts.append(alert)
        elif balance >= threshold:
            below_threshold = False

    dates_below = [p["date"] for p in projection if p["balance"] < threshold]

    return {
        "generated": date.today().isoformat(),
        "starting_balance": starting_balance,
        "forecast_days": forecast_days,
        "threshold": threshold,
        "ending_balance": round(balance, 2),
        "min_balance": round(min_balance, 2),
        "min_balance_date": min_balance_date.isoformat(),
        "days_below_threshold": len(dates_below),
        "dates_below_threshold": dates_below,
        "alerts": alerts,
        "projection": projection
    }


def load_calendar(path: str) -> list[dict[str, Any]]:
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if "entries" in data:
        return data["entries"]
    if "calendar" in data:
        return data["calendar"]
    raise ValueError(f"Cannot parse calendar from {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cash flow forecast — 30-day forward balance projection")
    parser.add_argument("--calendar", required=True, help="Path to cash flow calendar JSON")
    parser.add_argument("--balance", type=float, required=True, help="Current checking balance")
    parser.add_argument("--days", type=int, default=30, help="Number of days to forecast")
    parser.add_argument("--threshold", type=float, default=500.0, help="Low balance warning threshold")
    parser.add_argument("--start-date", type=str, default=None, help="Override start date (YYYY-MM-DD)")
    args = parser.parse_args()

    entries = load_calendar(args.calendar)
    start = _parse_date(args.start_date) if args.start_date else None
    result = build_forecast(entries, args.balance, args.days, args.threshold, start)
    json.dump(result, sys.stdout, indent=2)
    print()
