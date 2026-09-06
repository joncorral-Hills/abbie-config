#!/usr/bin/env python3
"""Plaid API client for Allie's personal finance automation.

Wraps the plaid-python SDK and integrates with the existing Notion-based
financial-automation skill. Provides transaction sync, balance checks,
recurring stream detection, merchant categorization, and Notion write-back.

Environment Variables:
    PLAID_CLIENT_ID      — Plaid application client ID
    PLAID_SECRET         — Plaid secret (production)
    PLAID_ENV            — Plaid environment (default: 'production')
    PLAID_ACCESS_TOKENS  — JSON string mapping institution labels to access tokens
    NOTION_API_KEY       — Notion integration token
    TRANSACTIONS_DB_ID   — Notion Transactions database ID
    ACCOUNTS_DB_ID       — Notion Accounts database ID
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Graceful import of plaid-python
# ---------------------------------------------------------------------------
try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.transactions_sync_request import TransactionsSyncRequest
    from plaid.model.transactions_recurring_get_request import TransactionsRecurringGetRequest
    from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest
    from plaid.model.products import Products

    PLAID_AVAILABLE = True
except ImportError:
    PLAID_AVAILABLE = False

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("plaid_client")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)-8s %(name)s — %(message)s")
    )
    logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HERMES_DIR = Path.home() / ".hermes"
CURSOR_FILE = HERMES_DIR / "plaid_cursors.json"
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Account-name mapping tokens (institution → subtype/name → friendly label)
ACCOUNT_MAP: list[dict[str, Any]] = [
    {"institution": "chase", "match_field": "name", "contains": "Flex", "label": "Chase Flex"},
    {"institution": "chase", "match_field": "name", "contains": "Sapphire", "label": "Chase Sapphire Reserve"},
    {"institution": "chase", "match_field": "name", "contains": "Freedom Unlimited", "label": "Chase Freedom Unlimited"},
    {"institution": "chase", "match_field": "subtype", "contains": "checking", "label": "Chase Checking"},
    {"institution": "usbank", "match_field": "subtype", "contains": "checking", "label": "US Bank Checking"},
    {"institution": "usbank", "match_field": "subtype", "contains": "savings", "label": "US Bank Savings"},
    {"institution": "capital", "match_field": None, "contains": None, "label": "Capital One Venture X"},
    {"institution": "amazon", "match_field": None, "contains": None, "label": "Amazon Prime Card"},
]


# ═══════════════════════════════════════════════════════════════════════════
# PlaidClient
# ═══════════════════════════════════════════════════════════════════════════
class PlaidClient:
    """Thin wrapper around the plaid-python SDK.

    Reads credentials from environment variables and exposes high-level
    helpers for link tokens, transaction sync, recurring streams, and
    account balances.
    """

    def __init__(self) -> None:
        if not PLAID_AVAILABLE:
            raise ImportError(
                "plaid-python is not installed. "
                "Install it with: pip install plaid-python"
            )

        self.client_id: str = os.environ.get("PLAID_CLIENT_ID", "")
        self.secret: str = os.environ.get("PLAID_SECRET", "")
        self.env_name: str = os.environ.get("PLAID_ENV", "production").lower()

        if not self.client_id or not self.secret:
            raise EnvironmentError(
                "PLAID_CLIENT_ID and PLAID_SECRET must be set in the environment."
            )

        env_map = {
            "sandbox": plaid.Environment.Sandbox,
            "development": plaid.Environment.Development,
            "production": plaid.Environment.Production,
        }
        host = env_map.get(self.env_name)
        if host is None:
            raise ValueError(
                f"Unknown PLAID_ENV '{self.env_name}'. "
                "Expected 'sandbox', 'development', or 'production'."
            )

        configuration = plaid.Configuration(
            host=host,
            api_key={
                "clientId": self.client_id,
                "secret": self.secret,
            },
        )
        api_client = plaid.ApiClient(configuration)
        self.client: plaid_api.PlaidApi = plaid_api.PlaidApi(api_client)
        logger.info("PlaidClient initialised (env=%s)", self.env_name)

    # ------------------------------------------------------------------
    # Link & Token Exchange
    # ------------------------------------------------------------------
    def create_link_token(self, user_id: str = "jon") -> dict[str, Any]:
        """Create a Plaid Link token for connecting a new institution.

        Args:
            user_id: Client-side user identifier.

        Returns:
            Dict with ``link_token`` and ``expiration``.
        """
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
            client_name="Allie Finance",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = self.client.link_token_create(request)
        result = {
            "link_token": response.link_token,
            "expiration": str(response.expiration),
        }
        logger.info("Link token created for user=%s", user_id)
        return result

    def exchange_public_token(self, public_token: str) -> dict[str, str]:
        """Exchange a public token from Link for a persistent access token.

        Args:
            public_token: The public token returned by Plaid Link.

        Returns:
            Dict with ``access_token`` and ``item_id``.
        """
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = self.client.item_public_token_exchange(request)
        result = {
            "access_token": response.access_token,
            "item_id": response.item_id,
        }
        logger.info("Public token exchanged → item_id=%s", response.item_id)
        return result

    # ------------------------------------------------------------------
    # Access Tokens
    # ------------------------------------------------------------------
    @staticmethod
    def get_access_tokens() -> dict[str, str]:
        """Load institution → access-token map from ``PLAID_ACCESS_TOKENS``.

        Returns:
            Dict mapping institution labels to access tokens.

        Raises:
            EnvironmentError: If the env var is missing or invalid JSON.
        """
        raw = os.environ.get("PLAID_ACCESS_TOKENS", "")
        if not raw:
            raise EnvironmentError(
                "PLAID_ACCESS_TOKENS is not set. "
                "Expected JSON: {\"chase\": \"access-production-xxx\", ...}"
            )
        try:
            tokens: dict[str, str] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EnvironmentError(
                f"PLAID_ACCESS_TOKENS is not valid JSON: {exc}"
            ) from exc
        return tokens

    # ------------------------------------------------------------------
    # Transaction Sync (cursor-based)
    # ------------------------------------------------------------------
    def sync_transactions(
        self,
        access_token: str,
        cursor: Optional[str] = None,
    ) -> dict[str, Any]:
        """Incrementally sync transactions using ``/transactions/sync``.

        Loops until ``has_more`` is False, accumulating added, modified,
        and removed transactions across pages.

        Args:
            access_token: Institution access token.
            cursor: Optional sync cursor from a previous call.

        Returns:
            Dict with keys ``added``, ``modified``, ``removed``, and
            ``next_cursor``.
        """
        added: list[dict[str, Any]] = []
        modified: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        has_more = True
        next_cursor = cursor or ""

        while has_more:
            request_kwargs: dict[str, Any] = {"access_token": access_token}
            if next_cursor:
                request_kwargs["cursor"] = next_cursor

            request = TransactionsSyncRequest(**request_kwargs)
            response = self.client.transactions_sync(request)

            added.extend(
                [self._txn_to_dict(t) for t in (response.added or [])]
            )
            modified.extend(
                [self._txn_to_dict(t) for t in (response.modified or [])]
            )
            removed.extend(
                [
                    {"transaction_id": t.transaction_id}
                    for t in (response.removed or [])
                ]
            )

            has_more = response.has_more
            next_cursor = response.next_cursor
            logger.debug(
                "sync page: +%d modified=%d removed=%d has_more=%s",
                len(response.added or []),
                len(response.modified or []),
                len(response.removed or []),
                has_more,
            )

        logger.info(
            "Transaction sync complete: %d added, %d modified, %d removed",
            len(added),
            len(modified),
            len(removed),
        )
        return {
            "added": added,
            "modified": modified,
            "removed": removed,
            "next_cursor": next_cursor,
        }

    # ------------------------------------------------------------------
    # Recurring Transactions
    # ------------------------------------------------------------------
    def get_recurring_transactions(
        self, access_token: str
    ) -> dict[str, Any]:
        """Fetch recurring transaction streams.

        Args:
            access_token: Institution access token.

        Returns:
            Dict with ``inflow_streams`` and ``outflow_streams``.
        """
        request = TransactionsRecurringGetRequest(
            access_token=access_token,
            account_ids=[],
        )
        response = self.client.transactions_recurring_get(request)

        inflows = [
            self._stream_to_dict(s) for s in (response.inflow_streams or [])
        ]
        outflows = [
            self._stream_to_dict(s) for s in (response.outflow_streams or [])
        ]
        logger.info(
            "Recurring streams: %d inflow, %d outflow",
            len(inflows),
            len(outflows),
        )
        return {"inflow_streams": inflows, "outflow_streams": outflows}

    # ------------------------------------------------------------------
    # Account Balances
    # ------------------------------------------------------------------
    def get_balances(self, access_token: str) -> list[dict[str, Any]]:
        """Retrieve current account balances.

        Args:
            access_token: Institution access token.

        Returns:
            List of account dicts with balance information.
        """
        request = AccountsBalanceGetRequest(access_token=access_token)
        response = self.client.accounts_balance_get(request)

        accounts = []
        for acct in response.accounts:
            accounts.append(
                {
                    "account_id": acct.account_id,
                    "name": acct.name,
                    "official_name": acct.official_name,
                    "type": str(acct.type),
                    "subtype": str(acct.subtype) if acct.subtype else None,
                    "balances": {
                        "available": acct.balances.available,
                        "current": acct.balances.current,
                        "limit": acct.balances.limit,
                        "iso_currency_code": acct.balances.iso_currency_code,
                    },
                }
            )
        logger.info("Fetched balances for %d accounts", len(accounts))
        return accounts

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _txn_to_dict(txn: Any) -> dict[str, Any]:
        """Convert a Plaid transaction model to a plain dict."""
        personal_finance = getattr(txn, "personal_finance_category", None)
        return {
            "transaction_id": txn.transaction_id,
            "account_id": txn.account_id,
            "amount": txn.amount,
            "date": str(txn.date) if txn.date else None,
            "authorized_date": str(txn.authorized_date) if txn.authorized_date else None,
            "name": txn.name,
            "merchant_name": getattr(txn, "merchant_name", None),
            "category": txn.category if hasattr(txn, "category") else None,
            "personal_finance_category": {
                "primary": personal_finance.primary if personal_finance else None,
                "detailed": personal_finance.detailed if personal_finance else None,
            },
            "pending": txn.pending,
            "payment_channel": str(txn.payment_channel) if hasattr(txn, "payment_channel") else None,
            "iso_currency_code": txn.iso_currency_code,
        }

    @staticmethod
    def _stream_to_dict(stream: Any) -> dict[str, Any]:
        """Convert a Plaid recurring stream model to a plain dict."""
        return {
            "stream_id": getattr(stream, "stream_id", None),
            "account_id": getattr(stream, "account_id", None),
            "description": getattr(stream, "description", None),
            "merchant_name": getattr(stream, "merchant_name", None),
            "average_amount": {
                "amount": getattr(getattr(stream, "average_amount", None), "amount", None),
                "iso_currency_code": getattr(
                    getattr(stream, "average_amount", None), "iso_currency_code", None
                ),
            },
            "last_amount": {
                "amount": getattr(getattr(stream, "last_amount", None), "amount", None),
                "iso_currency_code": getattr(
                    getattr(stream, "last_amount", None), "iso_currency_code", None
                ),
            },
            "frequency": str(getattr(stream, "frequency", "")),
            "status": str(getattr(stream, "status", "")),
            "category": getattr(stream, "category", None),
            "is_active": getattr(stream, "is_active", None),
            "last_date": str(getattr(stream, "last_date", "")) or None,
            "transaction_ids": getattr(stream, "transaction_ids", []),
        }


# ═══════════════════════════════════════════════════════════════════════════
# CategoryMapper
# ═══════════════════════════════════════════════════════════════════════════
class CategoryMapper:
    """Maps Plaid transaction categories to Allie's budget categories.

    Loads two configuration files:
      1. ``plaid_category_map.json``  — primary & detailed Plaid-to-Allie mapping
      2. ``merchant_categories.json`` — merchant-level overrides (from
         financial-automation skill)

    Resolution order:
      1. Exact merchant match (normalised uppercase, numbers stripped)
      2. Detailed category override
      3. Primary category mapping
      4. Fallback → ``'Uncategorized'``
    """

    def __init__(self) -> None:
        self.plaid_map: dict[str, Any] = self._load_plaid_map()
        self.merchant_map: dict[str, Any] = self._load_merchant_map()

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------
    @staticmethod
    def _load_plaid_map() -> dict[str, Any]:
        """Load ``plaid_category_map.json`` from ``../resources/``."""
        resources_dir = Path(__file__).resolve().parent.parent / "resources"
        path = resources_dir / "plaid_category_map.json"
        if path.is_file():
            with open(path, "r", encoding="utf-8") as fh:
                data: dict[str, Any] = json.load(fh)
                logger.debug("Loaded plaid_category_map from %s", path)
                return data
        logger.warning("plaid_category_map.json not found at %s", path)
        return {"primary": {}, "detailed_overrides": {}}

    @staticmethod
    def _load_merchant_map() -> dict[str, Any]:
        """Load ``merchant_categories.json`` from financial-automation resources.

        Search order:
          1. ``~/.hermes/skills/financial-automation/resources/merchant_categories.json``
          2. ``../../financial-automation/resources/merchant_categories.json``
             (relative to this script's parent skill directory)
        """
        candidates = [
            HERMES_DIR / "skills" / "financial-automation" / "resources" / "merchant_categories.json",
            Path(__file__).resolve().parent.parent.parent
            / "financial-automation"
            / "resources"
            / "merchant_categories.json",
        ]
        for path in candidates:
            if path.is_file():
                with open(path, "r", encoding="utf-8") as fh:
                    data: dict[str, Any] = json.load(fh)
                    merchants = data.get("merchants", data)
                    logger.debug("Loaded merchant_categories from %s", path)
                    return merchants
        logger.warning(
            "merchant_categories.json not found in any candidate path."
        )
        return {}

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_merchant(name: str | None) -> str:
        """Normalise merchant name: uppercase, strip trailing digits."""
        if not name:
            return ""
        import re
        cleaned = re.sub(r"\d+", "", name).strip()
        return cleaned.upper()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def map_category(
        self,
        plaid_category_primary: str | None,
        plaid_category_detailed: str | None,
        merchant_name: str | None,
    ) -> str:
        """Resolve a transaction to an Allie budget category.

        Args:
            plaid_category_primary: Plaid primary category (e.g., ``FOOD_AND_DRINK``).
            plaid_category_detailed: Plaid detailed category (e.g., ``FOOD_AND_DRINK_GROCERIES``).
            merchant_name: Raw merchant name from Plaid.

        Returns:
            Allie budget category string.
        """
        # 1. Merchant-level override
        if merchant_name:
            normalised = self._normalise_merchant(merchant_name)
            for key, info in self.merchant_map.items():
                if self._normalise_merchant(key) == normalised:
                    category = info.get("category") if isinstance(info, dict) else info
                    if category:
                        logger.debug(
                            "Category via merchant match: %s → %s",
                            merchant_name,
                            category,
                        )
                        return category

        # 2. Detailed category override
        if plaid_category_detailed:
            detailed_overrides: dict[str, str] = self.plaid_map.get(
                "detailed_overrides", {}
            )
            if plaid_category_detailed in detailed_overrides:
                cat = detailed_overrides[plaid_category_detailed]
                logger.debug(
                    "Category via detailed override: %s → %s",
                    plaid_category_detailed,
                    cat,
                )
                return cat

        # 3. Primary category mapping
        if plaid_category_primary:
            primary_map: dict[str, str] = self.plaid_map.get("primary", {})
            if plaid_category_primary in primary_map:
                cat = primary_map[plaid_category_primary]
                logger.debug(
                    "Category via primary map: %s → %s",
                    plaid_category_primary,
                    cat,
                )
                return cat

        # 4. Fallback
        logger.debug(
            "No category match for merchant=%s primary=%s detailed=%s → Uncategorized",
            merchant_name,
            plaid_category_primary,
            plaid_category_detailed,
        )
        return "Uncategorized"

    def is_recurring(
        self,
        merchant_name: str | None,
        plaid_category: str | None,
    ) -> bool:
        """Determine whether a transaction is recurring.

        Checks the merchant_categories recurring flag first, then falls
        back to Plaid category heuristics (subscriptions, rent, etc.).

        Args:
            merchant_name: Raw merchant name from Plaid.
            plaid_category: Plaid detailed or primary category string.

        Returns:
            True if the transaction appears to be recurring.
        """
        # Check merchant override
        if merchant_name:
            normalised = self._normalise_merchant(merchant_name)
            for key, info in self.merchant_map.items():
                if self._normalise_merchant(key) == normalised:
                    if isinstance(info, dict) and "recurring" in info:
                        return bool(info["recurring"])

        # Heuristic: Plaid category keywords
        if plaid_category:
            recurring_keywords = [
                "SUBSCRIPTION",
                "RENT",
                "INSURANCE",
                "LOAN",
                "MORTGAGE",
                "UTILITIES",
                "INTERNET",
                "PHONE",
                "MEMBERSHIP",
            ]
            upper = plaid_category.upper()
            return any(kw in upper for kw in recurring_keywords)

        return False


# ═══════════════════════════════════════════════════════════════════════════
# Account Name Resolution
# ═══════════════════════════════════════════════════════════════════════════
def resolve_account_name(
    institution_label: str,
    account: dict[str, Any],
) -> str:
    """Map a Plaid account to the friendly name used in Notion.

    Uses the institution label (from ``PLAID_ACCESS_TOKENS`` keys) and
    the account's ``name``, ``official_name``, and ``subtype`` fields to
    find a match in ``ACCOUNT_MAP``.

    Args:
        institution_label: Key from PLAID_ACCESS_TOKENS (e.g., 'chase').
        account: Account dict from Plaid (must have 'name', 'subtype').

    Returns:
        Friendly account name string.
    """
    inst_lower = institution_label.lower()
    acct_name = (account.get("name") or "").lower()
    acct_official = (account.get("official_name") or "").lower()
    acct_subtype = (account.get("subtype") or "").lower()
    combined_name = f"{acct_name} {acct_official}"

    for rule in ACCOUNT_MAP:
        rule_inst = rule["institution"].lower()
        if rule_inst not in inst_lower:
            continue

        # Rules with no match field match on institution alone
        if rule["match_field"] is None:
            return rule["label"]

        field_value = acct_name if rule["match_field"] == "name" else acct_subtype
        search_term = rule["contains"].lower()

        if search_term in field_value or search_term in combined_name:
            return rule["label"]

    # Fallback: use official_name or name from Plaid
    return account.get("official_name") or account.get("name") or "Unknown Account"


# ═══════════════════════════════════════════════════════════════════════════
# Cursor Persistence
# ═══════════════════════════════════════════════════════════════════════════
class CursorStore:
    """Persist sync cursors to disk keyed by SHA-256 of access token.

    File location: ``~/.hermes/plaid_cursors.json``
    Format: ``{"<sha256>": "cursor_string", ...}``
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path: Path = path or CURSOR_FILE
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        """Load cursor data from disk."""
        if self.path.is_file():
            with open(self.path, "r", encoding="utf-8") as fh:
                data: dict[str, str] = json.load(fh)
                return data
        return {}

    def _save(self) -> None:
        """Persist cursor data to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2)

    @staticmethod
    def _hash_token(access_token: str) -> str:
        """SHA-256 hash of the access token."""
        return hashlib.sha256(access_token.encode("utf-8")).hexdigest()

    def get(self, access_token: str) -> str | None:
        """Retrieve the stored cursor for an access token.

        Args:
            access_token: Plaid access token.

        Returns:
            Cursor string, or None if no cursor is stored.
        """
        return self._data.get(self._hash_token(access_token))

    def set(self, access_token: str, cursor: str) -> None:
        """Store a cursor for an access token.

        Args:
            access_token: Plaid access token.
            cursor: Sync cursor to store.
        """
        self._data[self._hash_token(access_token)] = cursor
        self._save()
        logger.debug("Cursor saved for token hash %s…", self._hash_token(access_token)[:12])


# ═══════════════════════════════════════════════════════════════════════════
# NotionTransactionWriter
# ═══════════════════════════════════════════════════════════════════════════
class NotionTransactionWriter:
    """Writes Plaid transactions to Allie's Notion Transactions database.

    Creates pages with: Description (title), Amount (number), Date (date),
    Account (select), Source='Plaid Sync' (select), Recurring (checkbox),
    Notes (rich_text — includes plaid_transaction_id for dedup).
    """

    def __init__(
        self,
        notion_api_key: str | None = None,
        transactions_db_id: str | None = None,
        accounts_db_id: str | None = None,
    ) -> None:
        if requests is None:
            raise ImportError("requests library is required for Notion API calls.")

        self.api_key: str = notion_api_key or os.environ.get("NOTION_API_KEY", "")
        self.transactions_db_id: str = transactions_db_id or os.environ.get("TRANSACTIONS_DB_ID", "")
        self.accounts_db_id: str = accounts_db_id or os.environ.get("ACCOUNTS_DB_ID", "")

        if not self.api_key:
            raise EnvironmentError("NOTION_API_KEY is required.")
        if not self.transactions_db_id:
            raise EnvironmentError("TRANSACTIONS_DB_ID is required.")

        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_VERSION,
        }

    # ------------------------------------------------------------------
    # Write Transaction
    # ------------------------------------------------------------------
    def write_transaction(self, txn_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new page in the Notion Transactions database.

        Args:
            txn_data: Dict with keys: description, amount, date, account,
                      recurring, notes, plaid_transaction_id.

        Returns:
            Notion API response dict.

        Raises:
            requests.HTTPError: On Notion API failure.
        """
        plaid_id = txn_data.get("plaid_transaction_id", "")
        notes_text = txn_data.get("notes", "")
        if plaid_id:
            notes_text = f"[plaid:{plaid_id}] {notes_text}".strip()

        # Plaid amounts: positive = money out, negative = money in
        amount = txn_data.get("amount", 0)

        properties: dict[str, Any] = {
            "Description": {
                "title": [{"text": {"content": txn_data.get("description", "Unknown")}}]
            },
            "Amount": {"number": amount},
            "Date": {"date": {"start": txn_data.get("date", str(date.today()))}},
            "Account": {"select": {"name": txn_data.get("account", "Unknown Account")}},
            "Source": {"select": {"name": "Plaid Sync"}},
            "Recurring": {"checkbox": bool(txn_data.get("recurring", False))},
            "Notes": {
                "rich_text": [{"text": {"content": notes_text[:2000]}}]
            },
        }

        payload = {
            "parent": {"database_id": self.transactions_db_id},
            "properties": properties,
        }

        resp = requests.post(
            f"{NOTION_API_BASE}/pages",
            headers=self._headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        logger.info(
            "Wrote transaction to Notion: %s ($%.2f)",
            txn_data.get("description", "?"),
            amount,
        )
        return result

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------
    def transaction_exists(self, plaid_transaction_id: str) -> bool:
        """Check if a transaction with this Plaid ID already exists in Notion.

        Queries the Notes property for ``[plaid:<id>]``.

        Args:
            plaid_transaction_id: The Plaid transaction ID to search for.

        Returns:
            True if a matching page exists.
        """
        search_tag = f"[plaid:{plaid_transaction_id}]"
        filter_payload = {
            "filter": {
                "property": "Notes",
                "rich_text": {"contains": search_tag},
            }
        }

        resp = requests.post(
            f"{NOTION_API_BASE}/databases/{self.transactions_db_id}/query",
            headers=self._headers,
            json=filter_payload,
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        exists = len(results) > 0
        if exists:
            logger.debug("Transaction %s already exists in Notion.", plaid_transaction_id)
        return exists

    # ------------------------------------------------------------------
    # Account Balances
    # ------------------------------------------------------------------
    def update_account_balance(
        self,
        account_name: str,
        balance: float | None,
        last_updated: str | None = None,
    ) -> dict[str, Any] | None:
        """Update an account's balance in the Notion Accounts database.

        Finds the account page by name, then updates the Balance and
        Last Updated properties via PATCH.

        Args:
            account_name: Friendly account name (e.g., 'Chase Checking').
            balance: Current balance in dollars.
            last_updated: ISO date string; defaults to today.

        Returns:
            Notion API response dict, or None if account not found or
            Accounts DB is not configured.
        """
        if not self.accounts_db_id:
            logger.warning("ACCOUNTS_DB_ID not set — skipping balance update.")
            return None

        # Find the account page
        filter_payload = {
            "filter": {
                "property": "Name",
                "title": {"equals": account_name},
            }
        }
        resp = requests.post(
            f"{NOTION_API_BASE}/databases/{self.accounts_db_id}/query",
            headers=self._headers,
            json=filter_payload,
            timeout=30,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if not results:
            logger.warning("Account '%s' not found in Notion Accounts DB.", account_name)
            return None

        page_id = results[0]["id"]
        update_date = last_updated or str(date.today())

        update_payload: dict[str, Any] = {
            "properties": {
                "Balance": {"number": balance},
                "Last Updated": {"date": {"start": update_date}},
            }
        }

        resp = requests.patch(
            f"{NOTION_API_BASE}/pages/{page_id}",
            headers=self._headers,
            json=update_payload,
            timeout=30,
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        logger.info(
            "Updated balance for %s: $%.2f (as of %s)",
            account_name,
            balance or 0,
            update_date,
        )
        return result


# ═══════════════════════════════════════════════════════════════════════════
# CLI Commands
# ═══════════════════════════════════════════════════════════════════════════
def _cmd_sync(args: argparse.Namespace) -> None:
    """Sync transactions from all institutions and write to Notion."""
    client = PlaidClient()
    cursor_store = CursorStore()
    mapper = CategoryMapper()
    writer = NotionTransactionWriter()

    tokens = client.get_access_tokens()
    total_added = 0
    total_skipped = 0
    total_errors = 0

    for institution, access_token in tokens.items():
        logger.info("═══ Syncing %s ═══", institution.upper())

        # Load saved cursor
        cursor = cursor_store.get(access_token)
        if cursor:
            logger.info("Resuming from saved cursor for %s", institution)

        # Sync transactions
        try:
            result = client.sync_transactions(access_token, cursor=cursor)
        except Exception as exc:
            logger.error("Failed to sync %s: %s", institution, exc)
            total_errors += 1
            continue

        # Persist new cursor
        cursor_store.set(access_token, result["next_cursor"])

        # Process added transactions
        for txn in result["added"]:
            plaid_id = txn["transaction_id"]

            # Deduplication check
            if writer.transaction_exists(plaid_id):
                total_skipped += 1
                continue

            # Categorise
            pfc = txn.get("personal_finance_category", {})
            category = mapper.map_category(
                pfc.get("primary"),
                pfc.get("detailed"),
                txn.get("merchant_name"),
            )
            recurring = mapper.is_recurring(
                txn.get("merchant_name"),
                pfc.get("detailed") or pfc.get("primary"),
            )

            # Resolve account name
            account_name = resolve_account_name(institution, {
                "name": txn.get("name", ""),
                "official_name": txn.get("merchant_name", ""),
                "subtype": "",  # Not available from txn; best-effort
            })
            # If resolution fell through, use institution default
            if account_name == "Unknown Account":
                account_name = resolve_account_name(institution, {
                    "name": institution,
                    "subtype": "checking",
                })

            # Build Notion payload
            description = txn.get("merchant_name") or txn.get("name") or "Unknown"
            txn_data = {
                "description": description,
                "amount": txn.get("amount", 0),
                "date": txn.get("date", str(date.today())),
                "account": account_name,
                "recurring": recurring,
                "notes": f"Category: {category}",
                "plaid_transaction_id": plaid_id,
            }

            try:
                writer.write_transaction(txn_data)
                total_added += 1
            except Exception as exc:
                logger.error("Failed to write txn %s: %s", plaid_id, exc)
                total_errors += 1

        # Log modified / removed for awareness
        if result["modified"]:
            logger.info(
                "%d modified transactions (not auto-updated in Notion)",
                len(result["modified"]),
            )
        if result["removed"]:
            logger.info(
                "%d removed transactions (not auto-deleted from Notion)",
                len(result["removed"]),
            )

    # Summary
    print("\n" + "═" * 50)
    print("  SYNC SUMMARY")
    print("═" * 50)
    print(f"  Added to Notion : {total_added}")
    print(f"  Skipped (dupes) : {total_skipped}")
    print(f"  Errors          : {total_errors}")
    print("═" * 50)


def _cmd_balances(args: argparse.Namespace) -> None:
    """Fetch and display account balances."""
    client = PlaidClient()
    tokens = client.get_access_tokens()
    update_notion = getattr(args, "update_notion", False)

    writer: NotionTransactionWriter | None = None
    if update_notion:
        writer = NotionTransactionWriter()

    print("\n" + "═" * 60)
    print("  ACCOUNT BALANCES")
    print("═" * 60)

    for institution, access_token in tokens.items():
        print(f"\n  ── {institution.upper()} ──")
        try:
            accounts = client.get_balances(access_token)
        except Exception as exc:
            logger.error("Failed to fetch balances for %s: %s", institution, exc)
            continue

        for acct in accounts:
            friendly_name = resolve_account_name(institution, acct)
            bal = acct.get("balances", {})
            current = bal.get("current")
            available = bal.get("available")
            limit = bal.get("limit")

            parts = [f"  {friendly_name}"]
            if current is not None:
                parts.append(f"Current: ${current:,.2f}")
            if available is not None:
                parts.append(f"Available: ${available:,.2f}")
            if limit is not None:
                parts.append(f"Limit: ${limit:,.2f}")
            print("  |  ".join(parts))

            # Optionally update Notion
            if writer and current is not None:
                try:
                    writer.update_account_balance(
                        friendly_name,
                        current,
                        last_updated=str(date.today()),
                    )
                except Exception as exc:
                    logger.error(
                        "Failed to update Notion balance for %s: %s",
                        friendly_name,
                        exc,
                    )

    print("\n" + "═" * 60)


def _cmd_recurring(args: argparse.Namespace) -> None:
    """Fetch and display recurring transaction streams."""
    client = PlaidClient()
    tokens = client.get_access_tokens()

    print("\n" + "═" * 60)
    print("  RECURRING TRANSACTIONS")
    print("═" * 60)

    for institution, access_token in tokens.items():
        print(f"\n  ── {institution.upper()} ──")
        try:
            result = client.get_recurring_transactions(access_token)
        except Exception as exc:
            logger.error("Failed to fetch recurring for %s: %s", institution, exc)
            continue

        if result["outflow_streams"]:
            print("\n  OUTFLOWS:")
            for stream in result["outflow_streams"]:
                desc = stream.get("description") or stream.get("merchant_name") or "?"
                avg = stream.get("average_amount", {}).get("amount")
                freq = stream.get("frequency", "?")
                status = stream.get("status", "?")
                avg_str = f"${avg:,.2f}" if avg is not None else "N/A"
                print(f"    • {desc:<35} {avg_str:>10}  ({freq}, {status})")

        if result["inflow_streams"]:
            print("\n  INFLOWS:")
            for stream in result["inflow_streams"]:
                desc = stream.get("description") or stream.get("merchant_name") or "?"
                avg = stream.get("average_amount", {}).get("amount")
                freq = stream.get("frequency", "?")
                avg_str = f"${avg:,.2f}" if avg is not None else "N/A"
                print(f"    • {desc:<35} {avg_str:>10}  ({freq})")

        if not result["outflow_streams"] and not result["inflow_streams"]:
            print("    (no recurring streams detected)")

    print("\n" + "═" * 60)


def _cmd_link_token(args: argparse.Namespace) -> None:
    """Generate and print a Plaid Link token."""
    client = PlaidClient()
    user_id = getattr(args, "user_id", "jon")
    result = client.create_link_token(user_id=user_id)
    print("\n" + "═" * 60)
    print("  LINK TOKEN")
    print("═" * 60)
    print(f"  Token     : {result['link_token']}")
    print(f"  Expires   : {result['expiration']}")
    print("═" * 60)


# ═══════════════════════════════════════════════════════════════════════════
# Main Entry Point
# ═══════════════════════════════════════════════════════════════════════════
def main() -> None:
    """CLI entry point for the Plaid client."""
    parser = argparse.ArgumentParser(
        description="Allie's Plaid API client — transaction sync & account management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python plaid_client.py sync\n"
            "  python plaid_client.py balances --update-notion\n"
            "  python plaid_client.py recurring\n"
            "  python plaid_client.py link-token\n"
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # sync
    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync all institutions, write transactions to Notion",
    )
    sync_parser.set_defaults(func=_cmd_sync)

    # balances
    bal_parser = subparsers.add_parser(
        "balances",
        help="Fetch and display account balances",
    )
    bal_parser.add_argument(
        "--update-notion",
        action="store_true",
        dest="update_notion",
        help="Also update balances in the Notion Accounts DB",
    )
    bal_parser.set_defaults(func=_cmd_balances)

    # recurring
    rec_parser = subparsers.add_parser(
        "recurring",
        help="Fetch and display recurring transaction streams",
    )
    rec_parser.set_defaults(func=_cmd_recurring)

    # link-token
    link_parser = subparsers.add_parser(
        "link-token",
        help="Generate a Plaid Link token",
    )
    link_parser.add_argument(
        "--user-id",
        default="jon",
        help="Client user ID (default: jon)",
    )
    link_parser.set_defaults(func=_cmd_link_token)

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
