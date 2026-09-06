#!/usr/bin/env python3
"""Subscription Sentinel — Detect price hikes, new charges, and cancellations.

Analyzes Plaid recurring transaction streams against an approved subscription
list and historical baselines. Sends Telegram alerts for anomalies and a
daily summary report.

Environment Variables:
    TELEGRAM_BOT_TOKEN  — Bot token for sending alerts
    TELEGRAM_CHAT_ID    — Chat ID to send alerts to
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger("subscription_sentinel")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SKILL_DIR = Path(__file__).resolve().parent.parent          # plaid-budget-sentinel/
RESOURCES_DIR = SKILL_DIR / "resources"
BASELINES_PATH = RESOURCES_DIR / "subscription_baselines.json"

# Two possible locations for the approved-subscriptions catalogue
_APPROVED_CANDIDATES = [
    SKILL_DIR.parent / "financial-automation" / "resources" / "approved_subscriptions.json",
    Path.home() / ".hermes" / "skills" / "financial-automation" / "resources" / "approved_subscriptions.json",
]

PRICE_HIKE_DELTA_MIN = 1.00   # Minimum absolute increase ($)
PRICE_HIKE_PCT_MIN = 0.05     # Minimum percentage increase (5%)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Category emoji map for richer alerts
_EMOJI = {
    "entertainment": "📺",
    "music": "🎵",
    "software": "💻",
    "cloud": "☁️",
    "fitness": "🏋️",
    "food": "🍔",
    "news": "📰",
    "gaming": "🎮",
    "education": "📚",
    "insurance": "🛡️",
    "utilities": "⚡",
    "default": "•",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class PriceHike:
    """A subscription whose recurring amount has increased."""

    merchant: str
    was_amount: float
    now_amount: float
    delta: float
    pct_change: float
    frequency: str
    category: str = ""


@dataclass
class NewSubscription:
    """A recurring charge not found in the approved list or baselines."""

    merchant: str
    amount: float
    frequency: str
    first_seen: str
    category: str = ""


@dataclass
class CancelledSubscription:
    """A subscription present in baselines but absent from current streams."""

    merchant: str
    was_amount: float
    last_seen: str


@dataclass
class SentinelReport:
    """Aggregated results of a subscription scan."""

    price_hikes: list[PriceHike] = field(default_factory=list)
    new_subscriptions: list[NewSubscription] = field(default_factory=list)
    cancelled: list[CancelledSubscription] = field(default_factory=list)
    total_monthly_recurring: float = 0.0
    monthly_change_vs_baseline: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_name(name: str) -> str:
    """Lower-case, strip whitespace for fuzzy matching."""
    return name.strip().lower()


def _freq_label(frequency: str | None) -> str:
    """Human-readable frequency label."""
    mapping = {
        "WEEKLY": "wk",
        "BIWEEKLY": "2wk",
        "SEMI_MONTHLY": "2x/mo",
        "MONTHLY": "mo",
        "ANNUALLY": "yr",
    }
    return mapping.get((frequency or "").upper(), frequency or "unknown")


def _monthly_equivalent(amount: float, frequency: str | None) -> float:
    """Convert an amount to its monthly equivalent based on frequency."""
    freq = (frequency or "").upper()
    multipliers = {
        "WEEKLY": 52 / 12,
        "BIWEEKLY": 26 / 12,
        "SEMI_MONTHLY": 2.0,
        "MONTHLY": 1.0,
        "ANNUALLY": 1 / 12,
    }
    return abs(amount) * multipliers.get(freq, 1.0)


def _emoji_for(category: str) -> str:
    """Pick an emoji for the subscription category."""
    key = _normalise_name(category) if category else "default"
    for tag, emoji in _EMOJI.items():
        if tag in key:
            return emoji
    return _EMOJI["default"]


# ---------------------------------------------------------------------------
# SubscriptionSentinel
# ---------------------------------------------------------------------------

class SubscriptionSentinel:
    """Monitors Plaid recurring streams for price changes and new charges."""

    def __init__(self) -> None:
        self.approved_names: set[str] = set()
        self.approved_lookup: dict[str, dict[str, Any]] = {}
        self.baselines: dict[str, dict[str, Any]] = {}

        self.telegram_token: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id: str = os.environ.get("TELEGRAM_CHAT_ID", "")

        self._load_approved_subscriptions()
        self._load_baselines()

    # -- loaders -----------------------------------------------------------

    def _load_approved_subscriptions(self) -> None:
        """Load the approved subscription catalogue from disk."""
        path: Path | None = None
        for candidate in _APPROVED_CANDIDATES:
            if candidate.exists():
                path = candidate
                break

        if path is None:
            logger.warning("No approved_subscriptions.json found — all streams treated as unknown")
            return

        logger.info("Loading approved subscriptions from %s", path)
        data = json.loads(path.read_text())

        # Flatten all sections into a single lookup
        for section in ("usb_autopay", "flex_autopay", "paused_or_uncertain", "annual"):
            for entry in data.get(section, []):
                key = _normalise_name(entry.get("name", ""))
                if key:
                    self.approved_names.add(key)
                    self.approved_lookup[key] = entry

    def _load_baselines(self) -> None:
        """Load historical baselines from disk."""
        if BASELINES_PATH.exists():
            logger.info("Loading baselines from %s", BASELINES_PATH)
            self.baselines = json.loads(BASELINES_PATH.read_text())
        else:
            logger.info("No baselines file found — starting fresh")
            self.baselines = {}

    # -- core analysis -----------------------------------------------------

    def analyze_streams(
        self,
        outflow_streams: list[dict[str, Any]],
        inflow_streams: list[dict[str, Any]] | None = None,
    ) -> SentinelReport:
        """Run full analysis on recurring transaction streams.

        Args:
            outflow_streams: Plaid outflow recurring streams (expenses).
            inflow_streams:  Plaid inflow recurring streams (income); used
                             only for completeness, not alerted on.

        Returns:
            A SentinelReport with detected anomalies and totals.
        """
        report = SentinelReport()

        report.price_hikes = self.detect_price_hikes(outflow_streams)
        report.new_subscriptions = self.detect_new_subscriptions(outflow_streams)
        report.cancelled = self.detect_cancelled(outflow_streams)

        # Compute total monthly recurring cost
        for stream in outflow_streams:
            if stream.get("status", "").upper() == "MATURE":
                amt = stream.get("last_amount", {}).get("amount", 0.0)
                freq = stream.get("frequency", "MONTHLY")
                report.total_monthly_recurring += _monthly_equivalent(amt, freq)

        report.total_monthly_recurring = round(report.total_monthly_recurring, 2)

        # Compare against baseline total
        baseline_total = self.baselines.get("_meta", {}).get("total_monthly", 0.0)
        report.monthly_change_vs_baseline = round(
            report.total_monthly_recurring - baseline_total, 2
        )

        return report

    def detect_price_hikes(self, streams: list[dict[str, Any]]) -> list[PriceHike]:
        """Identify MATURE streams where the latest amount exceeds the average.

        Thresholds: delta > $1.00 AND percentage change > 5%.
        """
        hikes: list[PriceHike] = []

        for stream in streams:
            if stream.get("status", "").upper() != "MATURE":
                continue

            merchant = stream.get("merchant_name") or stream.get("description", "Unknown")
            last_amt = abs(stream.get("last_amount", {}).get("amount", 0.0))
            avg_amt = abs(stream.get("average_amount", {}).get("amount", 0.0))

            if avg_amt == 0:
                continue

            delta = round(last_amt - avg_amt, 2)
            pct = delta / avg_amt

            if delta > PRICE_HIKE_DELTA_MIN and pct > PRICE_HIKE_PCT_MIN:
                hikes.append(PriceHike(
                    merchant=merchant,
                    was_amount=round(avg_amt, 2),
                    now_amount=round(last_amt, 2),
                    delta=delta,
                    pct_change=round(pct * 100, 1),
                    frequency=stream.get("frequency", "MONTHLY"),
                    category=stream.get("personal_finance_category", {}).get("primary", ""),
                ))

        return hikes

    def detect_new_subscriptions(
        self, streams: list[dict[str, Any]]
    ) -> list[NewSubscription]:
        """Find streams that are NOT in the approved list or baselines."""
        new_subs: list[NewSubscription] = []

        for stream in streams:
            merchant = stream.get("merchant_name") or stream.get("description", "Unknown")
            key = _normalise_name(merchant)

            if key in self.approved_names:
                continue
            if key in {_normalise_name(k) for k in self.baselines if k != "_meta"}:
                continue

            last_amt = abs(stream.get("last_amount", {}).get("amount", 0.0))
            first_date = stream.get("first_date", str(date.today()))

            new_subs.append(NewSubscription(
                merchant=merchant,
                amount=round(last_amt, 2),
                frequency=stream.get("frequency", "MONTHLY"),
                first_seen=first_date,
                category=stream.get("personal_finance_category", {}).get("primary", ""),
            ))

        return new_subs

    def detect_cancelled(
        self, streams: list[dict[str, Any]]
    ) -> list[CancelledSubscription]:
        """Identify subscriptions in baselines but missing from current streams."""
        current_keys: set[str] = set()
        for stream in streams:
            merchant = stream.get("merchant_name") or stream.get("description", "Unknown")
            current_keys.add(_normalise_name(merchant))

        cancelled: list[CancelledSubscription] = []
        for key, info in self.baselines.items():
            if key == "_meta":
                continue
            if _normalise_name(key) not in current_keys:
                cancelled.append(CancelledSubscription(
                    merchant=info.get("merchant", key),
                    was_amount=round(abs(info.get("amount", 0.0)), 2),
                    last_seen=info.get("last_date", "unknown"),
                ))

        return cancelled

    def update_baselines(self, streams: list[dict[str, Any]]) -> None:
        """Persist current stream data as the new baseline reference."""
        new_baselines: dict[str, Any] = {}

        total_monthly = 0.0
        for stream in streams:
            merchant = stream.get("merchant_name") or stream.get("description", "Unknown")
            key = _normalise_name(merchant)
            last_amt = abs(stream.get("last_amount", {}).get("amount", 0.0))
            freq = stream.get("frequency", "MONTHLY")

            new_baselines[key] = {
                "merchant": merchant,
                "amount": round(last_amt, 2),
                "frequency": freq,
                "status": stream.get("status", ""),
                "last_date": stream.get("last_date", str(date.today())),
                "category": stream.get("personal_finance_category", {}).get("primary", ""),
            }

            if stream.get("status", "").upper() == "MATURE":
                total_monthly += _monthly_equivalent(last_amt, freq)

        new_baselines["_meta"] = {
            "total_monthly": round(total_monthly, 2),
            "updated_at": datetime.now().isoformat(),
            "stream_count": len(streams),
        }

        RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
        BASELINES_PATH.write_text(json.dumps(new_baselines, indent=2))
        logger.info("Baselines updated → %s (%d streams)", BASELINES_PATH, len(streams))
        self.baselines = new_baselines

    # -- Telegram ----------------------------------------------------------

    def send_telegram(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message via Telegram Bot API.

        Args:
            message:    The message body (supports HTML by default).
            parse_mode: Telegram parse mode — 'HTML' or 'MarkdownV2'.

        Returns:
            True if the message was sent successfully, False otherwise.
        """
        if not self.telegram_token or not self.telegram_chat_id:
            logger.error("Telegram credentials not configured — skipping alert")
            return False

        url = TELEGRAM_API.format(token=self.telegram_token)
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": parse_mode,
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            logger.info("Telegram alert sent (%d chars)", len(message))
            return True
        except requests.RequestException as exc:
            logger.error("Telegram send failed: %s", exc)
            return False

    # -- alert formatters --------------------------------------------------

    def _format_price_hike_alert(self, report: SentinelReport) -> str:
        """Build HTML message for price hike detections."""
        lines = ["🚨 <b>Subscription Price Hike Detected</b>\n"]

        for h in report.price_hikes:
            emoji = _emoji_for(h.category)
            lines.append(
                f"{emoji} {h.merchant}: ${h.was_amount:.2f} → ${h.now_amount:.2f} "
                f"(+${h.delta:.2f}, +{h.pct_change}%)"
            )

        lines.append("")
        lines.append("💡 Review and decide if you want to keep these.")
        sign = "+" if report.monthly_change_vs_baseline >= 0 else ""
        lines.append(
            f"📊 Total monthly subscriptions: ${report.total_monthly_recurring:.2f} "
            f"({sign}${report.monthly_change_vs_baseline:.2f} vs last scan)"
        )
        return "\n".join(lines)

    def _format_new_sub_alert(self, report: SentinelReport) -> str:
        """Build HTML message for newly detected subscriptions."""
        lines = ["🆕 <b>New Recurring Charge Detected</b>\n"]

        for ns in report.new_subscriptions:
            freq = _freq_label(ns.frequency)
            lines.append(
                f"• {ns.merchant} — ${ns.amount:.2f}/{freq} "
                f"(first seen: {ns.first_seen})"
            )

        lines.append("")
        lines.append("⚠️ Not on your approved list.")
        return "\n".join(lines)

    def _format_cancelled_alert(self, report: SentinelReport) -> str:
        """Build HTML message for cancelled subscriptions."""
        lines = ["🗑️ <b>Subscription Cancelled / Missing</b>\n"]

        for c in report.cancelled:
            lines.append(
                f"• {c.merchant} — was ${c.was_amount:.2f} "
                f"(last seen: {c.last_seen})"
            )

        lines.append("")
        lines.append("ℹ️ These were in your baselines but no longer appear.")
        return "\n".join(lines)

    def _format_daily_summary(self, report: SentinelReport) -> str:
        """Build the always-sent daily summary message."""
        stream_count = self.baselines.get("_meta", {}).get("stream_count", 0)
        sign = "+" if report.monthly_change_vs_baseline >= 0 else ""

        lines = [
            "📋 <b>Subscription Sentinel — Daily Report</b>\n",
            f"Active subscriptions: {stream_count}",
            f"Total monthly cost: ${report.total_monthly_recurring:.2f}",
            f"Change vs last scan: {sign}${report.monthly_change_vs_baseline:.2f}",
            "",
        ]

        if report.price_hikes:
            lines.append(f"⚠️ {len(report.price_hikes)} price hike(s) detected")
        else:
            lines.append("✅ No price hikes detected")

        if report.new_subscriptions:
            lines.append(f"⚠️ {len(report.new_subscriptions)} new unknown charge(s)")
        else:
            lines.append("✅ No new unknown charges")

        if report.cancelled:
            lines.append(f"ℹ️ {len(report.cancelled)} subscription(s) no longer seen")

        return "\n".join(lines)

    # -- orchestration -----------------------------------------------------

    def send_alerts(self, report: SentinelReport) -> None:
        """Send all relevant Telegram alerts for a scan report."""
        if report.price_hikes:
            self.send_telegram(self._format_price_hike_alert(report))

        if report.new_subscriptions:
            self.send_telegram(self._format_new_sub_alert(report))

        if report.cancelled:
            self.send_telegram(self._format_cancelled_alert(report))

        # Always send the daily summary
        self.send_telegram(self._format_daily_summary(report))

    def print_report(self, report: SentinelReport) -> None:
        """Print a human-readable report to stdout."""
        print("=" * 60)
        print("  SUBSCRIPTION SENTINEL REPORT")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)

        print(f"\n  Total monthly cost:  ${report.total_monthly_recurring:.2f}")
        sign = "+" if report.monthly_change_vs_baseline >= 0 else ""
        print(f"  Change vs baseline:  {sign}${report.monthly_change_vs_baseline:.2f}")

        if report.price_hikes:
            print(f"\n  --- Price Hikes ({len(report.price_hikes)}) ---")
            for h in report.price_hikes:
                print(
                    f"    {h.merchant}: ${h.was_amount:.2f} → ${h.now_amount:.2f} "
                    f"(+${h.delta:.2f}, +{h.pct_change}%)"
                )

        if report.new_subscriptions:
            print(f"\n  --- New Subscriptions ({len(report.new_subscriptions)}) ---")
            for ns in report.new_subscriptions:
                freq = _freq_label(ns.frequency)
                print(f"    {ns.merchant}: ${ns.amount:.2f}/{freq} (since {ns.first_seen})")

        if report.cancelled:
            print(f"\n  --- Cancelled ({len(report.cancelled)}) ---")
            for c in report.cancelled:
                print(f"    {c.merchant}: was ${c.was_amount:.2f} (last: {c.last_seen})")

        if not (report.price_hikes or report.new_subscriptions or report.cancelled):
            print("\n  ✅ All clear — no anomalies detected.")

        print("\n" + "=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_scan() -> None:
    """Full scan: fetch recurring streams from Plaid, analyse, alert, update."""
    # Import sibling PlaidClient
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    try:
        from plaid_client import PlaidClient  # type: ignore[import-untyped]
    except ImportError as exc:
        logger.error("Cannot import PlaidClient: %s", exc)
        sys.exit(1)

    client = PlaidClient()
    sentinel = SubscriptionSentinel()

    # Fetch all access tokens and aggregate recurring streams
    all_outflows: list[dict[str, Any]] = []
    all_inflows: list[dict[str, Any]] = []

    tokens = client.get_access_tokens()
    if not tokens:
        logger.error("No Plaid access tokens available")
        sys.exit(1)

    for token in tokens:
        try:
            recurring = client.get_recurring_transactions(token)
            all_outflows.extend(recurring.get("outflow_streams", []))
            all_inflows.extend(recurring.get("inflow_streams", []))
        except Exception as exc:
            logger.warning("Failed to fetch recurring for token: %s", exc)

    logger.info(
        "Fetched %d outflow / %d inflow streams",
        len(all_outflows),
        len(all_inflows),
    )

    report = sentinel.analyze_streams(all_outflows, all_inflows)
    sentinel.print_report(report)
    sentinel.send_alerts(report)
    sentinel.update_baselines(all_outflows)


def _cmd_report() -> None:
    """Print summary from current baselines without scanning or alerting."""
    sentinel = SubscriptionSentinel()

    if not sentinel.baselines or (len(sentinel.baselines) <= 1 and "_meta" in sentinel.baselines):
        print("No baseline data available. Run 'scan' first.")
        return

    # Synthesise a lightweight report from baselines
    total = sentinel.baselines.get("_meta", {}).get("total_monthly", 0.0)
    count = sentinel.baselines.get("_meta", {}).get("stream_count", 0)
    updated = sentinel.baselines.get("_meta", {}).get("updated_at", "never")

    print("=" * 60)
    print("  SUBSCRIPTION BASELINES SUMMARY")
    print("=" * 60)
    print(f"\n  Last scan:           {updated}")
    print(f"  Active streams:      {count}")
    print(f"  Total monthly cost:  ${total:.2f}\n")

    for key, info in sorted(sentinel.baselines.items()):
        if key == "_meta":
            continue
        merchant = info.get("merchant", key)
        amt = info.get("amount", 0.0)
        freq = _freq_label(info.get("frequency"))
        status = info.get("status", "")
        print(f"    {merchant:<30} ${amt:>8.2f}/{freq:<4}  [{status}]")

    print("\n" + "=" * 60)


def _cmd_baselines() -> None:
    """Dump raw baselines JSON to stdout."""
    if BASELINES_PATH.exists():
        print(BASELINES_PATH.read_text())
    else:
        print(json.dumps({}, indent=2))
        logger.info("No baselines file at %s", BASELINES_PATH)


def main() -> None:
    """Entry point for CLI usage."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Subscription Sentinel — Detect subscription anomalies from Plaid streams",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("scan", help="Full scan: fetch, analyse, alert, update baselines")
    sub.add_parser("report", help="Print summary from current baselines")
    sub.add_parser("baselines", help="Dump raw baselines JSON")

    args = parser.parse_args()

    commands = {
        "scan": _cmd_scan,
        "report": _cmd_report,
        "baselines": _cmd_baselines,
    }

    handler = commands.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler()


if __name__ == "__main__":
    main()
