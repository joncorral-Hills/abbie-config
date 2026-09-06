#!/usr/bin/env python3
"""
revenue_sync.py — Etsy Digital Storefront Revenue Sync Engine

Delta and full sync of Etsy orders into Notion, with fee calculation,
daily/monthly aggregation, milestone detection, and Google Chat alerts.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

# ---------------------------------------------------------------------------
# Sibling import — etsy_client lives in the same scripts/ directory
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etsy_client import EtsyClient  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SYNC_STATE_DIR = os.path.expanduser("~/.hermes/state/storefront/")
SYNC_STATE_FILE = os.path.join(SYNC_STATE_DIR, "revenue_sync_state.json")
MILESTONES_FILE = os.path.join(SYNC_STATE_DIR, "milestones.json")
FEE_SCHEDULE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "resources",
    "etsy_fee_schedule.json",
)

GOOGLE_CHAT_WEBHOOK = os.environ.get("GOOGLE_CHAT_WEBHOOK_BUSINESS", "")

# Default fee schedule (overridden by resources/etsy_fee_schedule.json)
DEFAULT_FEE_SCHEDULE = {
    "listing_flat": 0.20,
    "transaction_pct": 0.065,
    "processing_domestic_pct": 0.03,
    "processing_domestic_flat": 0.25,
    "processing_international_pct": 0.04,
    "processing_international_flat": 0.25,
    "offsite_ads_pct": 0.15,
    "regulatory_pct": 0.0025,
}

# Milestone thresholds
ORDER_MILESTONES = [1, 10, 25, 50, 100, 250, 500, 1000]
REVENUE_MILESTONES = [100, 500, 1000, 5000, 10000, 50000]


def _load_fee_schedule() -> dict:
    """Load fee schedule from JSON resource or fall back to defaults."""
    resolved = os.path.normpath(FEE_SCHEDULE_PATH)
    if os.path.isfile(resolved):
        try:
            with open(resolved, "r") as fh:
                data = json.load(fh)
            merged = {**DEFAULT_FEE_SCHEDULE, **data}
            return merged
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULT_FEE_SCHEDULE)


FEE_SCHEDULE = _load_fee_schedule()


# ═══════════════════════════════════════════════════════════════════════════
# RevenueSync
# ═══════════════════════════════════════════════════════════════════════════
class RevenueSync:
    """End-to-end Etsy → Notion revenue synchronisation."""

    def __init__(self, etsy_client: "EtsyClient", notion_sync):
        """
        Parameters
        ----------
        etsy_client : EtsyClient
            Authenticated Etsy API wrapper (from sibling module).
        notion_sync : object
            Notion helper exposing ``upsert_order(data)`` and
            ``upsert_snapshot(period, period_type, data)`` methods.
        """
        self.etsy = etsy_client
        self.notion = notion_sync
        self.state = self._load_sync_state()
        self.milestones = self._load_milestones()

    # ------------------------------------------------------------------
    # Core sync
    # ------------------------------------------------------------------
    def sync_orders(self, since: Optional[str] = None) -> dict:
        """Delta-sync orders from Etsy since *since* (ISO-8601) or last
        checkpoint.  Returns ``{new_orders, total_revenue, fees}``."""
        if since is None:
            since = self.state.get("last_sync_timestamp")

        receipts = self.etsy.get_receipts(min_created=since)

        new_orders = 0
        total_revenue = 0.0
        total_fees: dict = {}
        last_receipt_id = self.state.get("last_receipt_id", 0)

        for receipt in receipts:
            receipt_id = receipt.get("receipt_id", 0)
            if receipt_id <= last_receipt_id:
                continue

            gross = float(receipt.get("grandtotal", {}).get("amount", 0)) / max(
                int(receipt.get("grandtotal", {}).get("divisor", 100)), 1
            )
            is_offsite = receipt.get("is_from_offsite_ads", False)
            shipping_addr = receipt.get("shipping_address", {}) or {}
            buyer_country = (shipping_addr.get("country_iso", "") or "").upper()
            is_international = buyer_country not in ("US", "")

            fees = self.calculate_fees(
                gross,
                is_offsite_ad=is_offsite,
                is_international=is_international,
            )

            order_data = {
                "receipt_id": receipt_id,
                "date": receipt.get("create_timestamp"),
                "buyer": receipt.get("buyer_email", ""),
                "gross": gross,
                "fees": fees,
                "net": fees["net"],
                "items": [
                    {
                        "title": t.get("title", ""),
                        "quantity": t.get("quantity", 1),
                        "price": float(t.get("price", {}).get("amount", 0))
                        / max(int(t.get("price", {}).get("divisor", 100)), 1),
                    }
                    for t in receipt.get("transactions", [])
                ],
                "is_offsite_ad": is_offsite,
                "is_international": is_international,
            }

            self.notion.upsert_order(order_data)

            new_orders += 1
            total_revenue += gross
            for key, val in fees.items():
                if isinstance(val, (int, float)):
                    total_fees[key] = total_fees.get(key, 0.0) + val

            if receipt_id > last_receipt_id:
                last_receipt_id = receipt_id

        # Update persisted state
        self.state["last_sync_timestamp"] = datetime.now(timezone.utc).isoformat()
        self.state["last_receipt_id"] = last_receipt_id
        self.state["total_orders_synced"] = (
            self.state.get("total_orders_synced", 0) + new_orders
        )
        self.state["total_revenue_synced"] = round(
            self.state.get("total_revenue_synced", 0.0) + total_revenue, 2
        )
        self._save_sync_state(self.state)

        # Milestone check
        milestones_hit = self.detect_milestones(
            {
                "total_orders": self.state["total_orders_synced"],
                "total_revenue": self.state["total_revenue_synced"],
            }
        )
        for ms in milestones_hit:
            self.send_milestone_alert(ms)

        return {
            "new_orders": new_orders,
            "total_revenue": round(total_revenue, 2),
            "fees": {k: round(v, 2) for k, v in total_fees.items()},
        }

    # ------------------------------------------------------------------
    # Fee engine
    # ------------------------------------------------------------------
    def calculate_fees(
        self,
        gross: float,
        is_offsite_ad: bool = False,
        is_international: bool = False,
    ) -> dict:
        """Full Etsy fee breakdown for a single order.

        Returns dict with individual fee lines, total_fees, and net.
        """
        listing_fee = FEE_SCHEDULE["listing_flat"]
        transaction_fee = round(gross * FEE_SCHEDULE["transaction_pct"], 2)

        if is_international:
            processing_fee = round(
                gross * FEE_SCHEDULE["processing_international_pct"]
                + FEE_SCHEDULE["processing_international_flat"],
                2,
            )
        else:
            processing_fee = round(
                gross * FEE_SCHEDULE["processing_domestic_pct"]
                + FEE_SCHEDULE["processing_domestic_flat"],
                2,
            )

        offsite_ads_fee = (
            round(gross * FEE_SCHEDULE["offsite_ads_pct"], 2) if is_offsite_ad else 0.0
        )
        regulatory_fee = round(gross * FEE_SCHEDULE["regulatory_pct"], 2)

        total_fees = round(
            listing_fee
            + transaction_fee
            + processing_fee
            + offsite_ads_fee
            + regulatory_fee,
            2,
        )
        net = round(gross - total_fees, 2)

        return {
            "listing_fee": listing_fee,
            "transaction_fee": transaction_fee,
            "processing_fee": processing_fee,
            "offsite_ads_fee": offsite_ads_fee,
            "regulatory_fee": regulatory_fee,
            "total_fees": total_fees,
            "net": net,
        }

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------
    def aggregate_daily(self, date: str) -> dict:
        """Sum all orders for *date* (YYYY-MM-DD).

        Returns ``{orders, gross, fees, net, top_product}``.
        """
        target = datetime.strptime(date, "%Y-%m-%d").date()
        day_start = datetime(
            target.year, target.month, target.day, tzinfo=timezone.utc
        )
        day_end = day_start + timedelta(days=1)

        receipts = self.etsy.get_receipts(
            min_created=day_start.isoformat(),
            max_created=day_end.isoformat(),
        )

        orders = 0
        gross = 0.0
        fees_total = 0.0
        net_total = 0.0
        product_counts: dict[str, int] = {}

        for receipt in receipts:
            order_gross = float(receipt.get("grandtotal", {}).get("amount", 0)) / max(
                int(receipt.get("grandtotal", {}).get("divisor", 100)), 1
            )
            shipping_addr = receipt.get("shipping_address", {}) or {}
            buyer_country = (shipping_addr.get("country_iso", "") or "").upper()
            is_international = buyer_country not in ("US", "")
            is_offsite = receipt.get("is_from_offsite_ads", False)

            fees = self.calculate_fees(
                order_gross,
                is_offsite_ad=is_offsite,
                is_international=is_international,
            )
            orders += 1
            gross += order_gross
            fees_total += fees["total_fees"]
            net_total += fees["net"]

            for txn in receipt.get("transactions", []):
                title = txn.get("title", "Unknown")
                qty = txn.get("quantity", 1)
                product_counts[title] = product_counts.get(title, 0) + qty

        top_product = (
            max(product_counts, key=product_counts.get) if product_counts else None
        )

        return {
            "orders": orders,
            "gross": round(gross, 2),
            "fees": round(fees_total, 2),
            "net": round(net_total, 2),
            "top_product": top_product,
        }

    def aggregate_monthly(self, year: int, month: int) -> dict:
        """Sum all orders for *year*-*month*.

        Returns ``{orders, gross, fees, net, top_product, avg_order_value}``.
        """
        month_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        receipts = self.etsy.get_receipts(
            min_created=month_start.isoformat(),
            max_created=month_end.isoformat(),
        )

        orders = 0
        gross = 0.0
        fees_total = 0.0
        net_total = 0.0
        product_counts: dict[str, int] = {}

        for receipt in receipts:
            order_gross = float(receipt.get("grandtotal", {}).get("amount", 0)) / max(
                int(receipt.get("grandtotal", {}).get("divisor", 100)), 1
            )
            shipping_addr = receipt.get("shipping_address", {}) or {}
            buyer_country = (shipping_addr.get("country_iso", "") or "").upper()
            is_international = buyer_country not in ("US", "")
            is_offsite = receipt.get("is_from_offsite_ads", False)

            fees = self.calculate_fees(
                order_gross,
                is_offsite_ad=is_offsite,
                is_international=is_international,
            )
            orders += 1
            gross += order_gross
            fees_total += fees["total_fees"]
            net_total += fees["net"]

            for txn in receipt.get("transactions", []):
                title = txn.get("title", "Unknown")
                qty = txn.get("quantity", 1)
                product_counts[title] = product_counts.get(title, 0) + qty

        top_product = (
            max(product_counts, key=product_counts.get) if product_counts else None
        )
        avg_order_value = round(gross / orders, 2) if orders else 0.0

        return {
            "orders": orders,
            "gross": round(gross, 2),
            "fees": round(fees_total, 2),
            "net": round(net_total, 2),
            "top_product": top_product,
            "avg_order_value": avg_order_value,
        }

    # ------------------------------------------------------------------
    # Notion snapshot
    # ------------------------------------------------------------------
    def update_snapshot(self, period: str, period_type: str, data: dict) -> str:
        """Upsert a business snapshot into Notion.

        Parameters
        ----------
        period : str
            Human label, e.g. ``"2026-07-14"`` or ``"2026-07"``.
        period_type : str
            ``"daily"`` or ``"monthly"``.
        data : dict
            Aggregation dict produced by ``aggregate_daily`` / ``aggregate_monthly``.

        Returns
        -------
        str
            Notion page ID of the upserted snapshot.
        """
        snapshot = {
            "period": period,
            "period_type": period_type,
            "orders": data.get("orders", 0),
            "gross_revenue": data.get("gross", 0.0),
            "total_fees": data.get("fees", 0.0),
            "net_revenue": data.get("net", 0.0),
            "top_product": data.get("top_product"),
            "avg_order_value": data.get("avg_order_value"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        page_id = self.notion.upsert_snapshot(period, period_type, snapshot)
        return page_id

    # ------------------------------------------------------------------
    # Milestones
    # ------------------------------------------------------------------
    def detect_milestones(self, current_totals: dict) -> list[str]:
        """Return list of newly-hit milestone strings."""
        hit: list[str] = []
        total_orders = current_totals.get("total_orders", 0)
        total_revenue = current_totals.get("total_revenue", 0.0)

        # First sale
        if total_orders >= 1 and "first_sale" not in self.milestones:
            hit.append("first_sale")
            self.milestones.add("first_sale")

        # Order milestones
        for threshold in ORDER_MILESTONES:
            key = f"orders_{threshold}"
            if total_orders >= threshold and key not in self.milestones:
                hit.append(key)
                self.milestones.add(key)

        # Revenue milestones
        for threshold in REVENUE_MILESTONES:
            key = f"revenue_{threshold}"
            if total_revenue >= threshold and key not in self.milestones:
                hit.append(key)
                self.milestones.add(key)

        if hit:
            self._save_milestones(self.milestones)

        return hit

    def send_milestone_alert(self, milestone: str) -> None:
        """Send a Google Chat card celebrating *milestone*."""
        if not GOOGLE_CHAT_WEBHOOK:
            print(f"[milestone] {milestone} (no webhook configured)")
            return

        label = milestone.replace("_", " ").title()
        if milestone == "first_sale":
            emoji = "🎉"
            description = "Your very first Etsy sale just landed!"
        elif milestone.startswith("orders_"):
            count = milestone.split("_", 1)[1]
            emoji = "📦"
            description = f"You've reached {count} total orders!"
        elif milestone.startswith("revenue_"):
            amount = milestone.split("_", 1)[1]
            emoji = "💰"
            description = f"You've crossed ${amount} in total revenue!"
        else:
            emoji = "🏆"
            description = f"Milestone achieved: {label}"

        card_payload = {
            "cardsV2": [
                {
                    "cardId": f"milestone-{milestone}",
                    "card": {
                        "header": {
                            "title": f"{emoji} Storefront Milestone",
                            "subtitle": label,
                        },
                        "sections": [
                            {
                                "widgets": [
                                    {
                                        "decoratedText": {
                                            "topLabel": "Milestone",
                                            "text": description,
                                        }
                                    },
                                    {
                                        "decoratedText": {
                                            "topLabel": "Achieved",
                                            "text": datetime.now(
                                                timezone.utc
                                            ).strftime("%Y-%m-%d %H:%M UTC"),
                                        }
                                    },
                                ]
                            }
                        ],
                    },
                }
            ]
        }

        try:
            resp = requests.post(
                GOOGLE_CHAT_WEBHOOK,
                json=card_payload,
                timeout=10,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[milestone-alert] Failed to send {milestone}: {exc}")

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------
    def _load_sync_state(self) -> dict:
        """Load sync state from disk or return defaults."""
        if os.path.isfile(SYNC_STATE_FILE):
            try:
                with open(SYNC_STATE_FILE, "r") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "last_sync_timestamp": None,
            "last_receipt_id": 0,
            "total_orders_synced": 0,
            "total_revenue_synced": 0.0,
        }

    def _save_sync_state(self, state: dict) -> None:
        """Persist sync state to disk."""
        Path(SYNC_STATE_DIR).mkdir(parents=True, exist_ok=True)
        tmp = SYNC_STATE_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(state, fh, indent=2)
        os.replace(tmp, SYNC_STATE_FILE)

    def _load_milestones(self) -> set:
        """Load achieved milestones from disk."""
        if os.path.isfile(MILESTONES_FILE):
            try:
                with open(MILESTONES_FILE, "r") as fh:
                    data = json.load(fh)
                return set(data) if isinstance(data, list) else set()
            except (json.JSONDecodeError, OSError):
                pass
        return set()

    def _save_milestones(self, milestones: set) -> None:
        """Persist milestones to disk."""
        Path(SYNC_STATE_DIR).mkdir(parents=True, exist_ok=True)
        tmp = MILESTONES_FILE + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(sorted(milestones), fh, indent=2)
        os.replace(tmp, MILESTONES_FILE)


# ═══════════════════════════════════════════════════════════════════════════
# Self-tests
# ═══════════════════════════════════════════════════════════════════════════
def _run_tests() -> None:
    """Lightweight self-tests for fee calculation and state I/O."""

    class _MockEtsy:
        def get_receipts(self, **kw):
            return []

    class _MockNotion:
        def upsert_order(self, data):
            pass

        def upsert_snapshot(self, period, period_type, data):
            return "mock-page-id"

    rs = RevenueSync(_MockEtsy(), _MockNotion())

    # --- Fee calculation (domestic, no offsite ads) ----------------------
    fees = rs.calculate_fees(25.0, is_offsite_ad=False, is_international=False)
    assert fees["listing_fee"] == 0.20, f"listing_fee: {fees['listing_fee']}"
    assert fees["transaction_fee"] == round(25.0 * 0.065, 2), (
        f"transaction_fee: {fees['transaction_fee']}"
    )
    expected_processing = round(25.0 * 0.03 + 0.25, 2)
    assert fees["processing_fee"] == expected_processing, (
        f"processing_fee: {fees['processing_fee']}"
    )
    assert fees["offsite_ads_fee"] == 0.0, (
        f"offsite_ads_fee: {fees['offsite_ads_fee']}"
    )
    expected_regulatory = round(25.0 * 0.0025, 2)
    assert fees["regulatory_fee"] == expected_regulatory, (
        f"regulatory_fee: {fees['regulatory_fee']}"
    )
    expected_total = round(
        0.20 + round(25.0 * 0.065, 2) + expected_processing + expected_regulatory, 2
    )
    assert fees["total_fees"] == expected_total, (
        f"total_fees: {fees['total_fees']} != {expected_total}"
    )
    assert fees["net"] == round(25.0 - expected_total, 2), f"net: {fees['net']}"
    print("✓ Fee calculation (domestic, no ads) passed")

    # --- Fee calculation (international + offsite ads) -------------------
    fees_intl = rs.calculate_fees(50.0, is_offsite_ad=True, is_international=True)
    assert fees_intl["processing_fee"] == round(50.0 * 0.04 + 0.25, 2)
    assert fees_intl["offsite_ads_fee"] == round(50.0 * 0.15, 2)
    print("✓ Fee calculation (international + offsite ads) passed")

    # --- State file I/O --------------------------------------------------
    import tempfile, shutil

    test_dir = tempfile.mkdtemp(prefix="revenue_sync_test_")
    original_state = SYNC_STATE_FILE
    original_miles = MILESTONES_FILE
    original_dir = SYNC_STATE_DIR

    # Monkey-patch paths for test isolation
    import revenue_sync as _mod

    _mod.SYNC_STATE_DIR = test_dir  # type: ignore[attr-defined]
    _mod.SYNC_STATE_FILE = os.path.join(test_dir, "test_state.json")
    _mod.MILESTONES_FILE = os.path.join(test_dir, "test_milestones.json")

    try:
        rs2 = RevenueSync(_MockEtsy(), _MockNotion())
        assert rs2.state["total_orders_synced"] == 0
        assert rs2.milestones == set()

        rs2.state["total_orders_synced"] = 42
        rs2.state["total_revenue_synced"] = 1234.56
        rs2._save_sync_state(rs2.state)

        rs3 = RevenueSync(_MockEtsy(), _MockNotion())
        assert rs3.state["total_orders_synced"] == 42
        assert rs3.state["total_revenue_synced"] == 1234.56
        print("✓ State file round-trip passed")

        # Milestones round-trip
        rs3.milestones = {"first_sale", "orders_10"}
        rs3._save_milestones(rs3.milestones)

        rs4 = RevenueSync(_MockEtsy(), _MockNotion())
        assert rs4.milestones == {"first_sale", "orders_10"}
        print("✓ Milestones file round-trip passed")
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        _mod.SYNC_STATE_DIR = original_dir
        _mod.SYNC_STATE_FILE = original_state
        _mod.MILESTONES_FILE = original_miles

    # --- Milestone detection ---------------------------------------------
    rs5 = RevenueSync(_MockEtsy(), _MockNotion())
    rs5.milestones = set()  # reset
    hits = rs5.detect_milestones({"total_orders": 1, "total_revenue": 25.0})
    assert "first_sale" in hits
    assert "orders_1" in hits
    assert "orders_10" not in hits
    print("✓ Milestone detection passed")

    # Idempotency: same totals should not re-fire
    hits2 = rs5.detect_milestones({"total_orders": 1, "total_revenue": 25.0})
    assert len(hits2) == 0
    print("✓ Milestone idempotency passed")

    print("\nAll self-tests passed ✅")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Etsy Revenue Sync Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Delta sync new orders since last run",
    )
    parser.add_argument(
        "--full-sync",
        action="store_true",
        help="Full sync all orders (ignores last checkpoint)",
    )
    parser.add_argument(
        "--aggregate",
        action="store_true",
        help="Run aggregation (requires --date or --month)",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Date for daily aggregation (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="Month for monthly aggregation (YYYY-MM)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run self-tests",
    )
    args = parser.parse_args()

    if args.test:
        _run_tests()
        return

    if not (args.sync or args.full_sync or args.aggregate):
        parser.print_help()
        sys.exit(1)

    # Build real clients (env-driven)
    etsy = EtsyClient()

    # Lazy import — notion_sync lives alongside this script
    from notion_sync import NotionSync  # noqa: E402

    notion = NotionSync()

    engine = RevenueSync(etsy, notion)

    if args.sync:
        result = engine.sync_orders()
        print(json.dumps(result, indent=2))

    elif args.full_sync:
        result = engine.sync_orders(since="2020-01-01T00:00:00Z")
        print(json.dumps(result, indent=2))

    elif args.aggregate:
        if args.date:
            data = engine.aggregate_daily(args.date)
            page_id = engine.update_snapshot(args.date, "daily", data)
            print(json.dumps({**data, "snapshot_page_id": page_id}, indent=2))
        elif args.month:
            parts = args.month.split("-")
            if len(parts) != 2:
                print("Error: --month must be YYYY-MM format", file=sys.stderr)
                sys.exit(1)
            year, month = int(parts[0]), int(parts[1])
            data = engine.aggregate_monthly(year, month)
            page_id = engine.update_snapshot(args.month, "monthly", data)
            print(json.dumps({**data, "snapshot_page_id": page_id}, indent=2))
        else:
            print(
                "Error: --aggregate requires --date or --month",
                file=sys.stderr,
            )
            sys.exit(1)


if __name__ == "__main__":
    main()
