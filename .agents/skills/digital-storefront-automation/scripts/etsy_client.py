#!/usr/bin/env python3
"""
etsy_client.py — Complete Etsy API v3 + Notion sync client for digital storefront automation.

Provides:
  - EtsyAuth: OAuth 2.0 PKCE flow with token persistence and auto-refresh.
  - EtsyClient: Rate-limited, retrying HTTP client for all Etsy v3 endpoints.
  - NotionSync: CRUD + upsert operations against 7 Notion databases.
  - CLI: --test, --refresh-token, --shop-info entrypoints.

Environment variables:
  ETSY_API_KEY, ETSY_SHARED_SECRET, ETSY_SHOP_ID,
  NOTION_API_KEY, NOTION_DB_SHOP_CONFIG, NOTION_DB_PRODUCT_IDEAS,
  NOTION_DB_PRODUCTS, NOTION_DB_LISTINGS, NOTION_DB_ORDERS,
  NOTION_DB_SEO_KEYWORDS, NOTION_DB_SNAPSHOTS
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ETSY_API_BASE = "https://openapi.etsy.com/v3"
ETSY_OAUTH_CONNECT = "https://www.etsy.com/oauth/connect"
ETSY_TOKEN_URL = "https://api.etsy.com/v3/public/oauth/token"
NOTION_API_BASE = "https://api.notion.com/v1"
TOKEN_PATH = Path.home() / ".hermes" / "secrets" / "etsy_tokens.json"
NOTION_VERSION = "2022-06-28"

LOG = logging.getLogger("etsy_client")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _env(name: str, required: bool = True) -> Optional[str]:
    """Read an environment variable, raising if required and missing."""
    val = os.environ.get(name)
    if required and not val:
        raise EnvironmentError(f"Missing required environment variable: {name}")
    return val


def _now_ts() -> int:
    """Current UTC epoch seconds."""
    return int(datetime.now(timezone.utc).timestamp())


# ===================================================================
# EtsyAuth — OAuth 2.0 Authorization Code + PKCE (S256)
# ===================================================================
class EtsyAuth:
    """Manages Etsy OAuth 2.0 PKCE authentication lifecycle.

    Flow:
      1. Generate code_verifier / code_challenge (S256).
      2. Build authorization URL → user opens in browser.
      3. Exchange authorization code for access + refresh tokens.
      4. Persist tokens to ~/.hermes/secrets/etsy_tokens.json.
      5. Auto-refresh when tokens expire or a 401 is encountered.
    """

    SCOPES = [
        "transactions_r",
        "transactions_w",
        "listings_r",
        "listings_w",
        "listings_d",
        "shops_r",
        "shops_w",
        "profile_r",
        "email_r",
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        shared_secret: Optional[str] = None,
        redirect_uri: str = "http://localhost:3370/callback",
    ) -> None:
        self.api_key = api_key or _env("ETSY_API_KEY")
        self.shared_secret = shared_secret or _env("ETSY_SHARED_SECRET")
        self.redirect_uri = redirect_uri
        self._tokens: Dict[str, Any] = {}
        self._code_verifier: Optional[str] = None
        self._load_tokens()

    # ---- PKCE helpers ----

    def _generate_verifier(self, length: int = 64) -> str:
        """Generate a cryptographically random code_verifier (43-128 chars)."""
        self._code_verifier = secrets.token_urlsafe(length)[:128]
        return self._code_verifier

    @staticmethod
    def _compute_challenge(verifier: str) -> str:
        """Compute S256 code_challenge from a code_verifier."""
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    # ---- Authorization URL ----

    def build_auth_url(self, state: Optional[str] = None) -> tuple[str, str]:
        """Return (authorization_url, code_verifier) for the PKCE flow.

        The caller should open the URL in a browser, then capture the
        ``code`` query-param from the redirect.
        """
        verifier = self._generate_verifier()
        challenge = self._compute_challenge(verifier)
        state = state or secrets.token_urlsafe(16)
        params = {
            "response_type": "code",
            "client_id": self.api_key,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.SCOPES),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        url = f"{ETSY_OAUTH_CONNECT}?{urlencode(params)}"
        LOG.info("Auth URL built — open in browser to authorize.")
        return url, verifier

    # ---- Token exchange ----

    def exchange_code(self, code: str, verifier: Optional[str] = None) -> Dict[str, Any]:
        """Exchange an authorization code for access + refresh tokens."""
        verifier = verifier or self._code_verifier
        if not verifier:
            raise ValueError("No code_verifier available. Call build_auth_url first.")
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.api_key,
            "redirect_uri": self.redirect_uri,
            "code": code,
            "code_verifier": verifier,
        }
        resp = requests.post(ETSY_TOKEN_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._store_tokens(data)
        LOG.info("Token exchange successful — tokens persisted.")
        return data

    # ---- Token refresh ----

    def refresh_token(self) -> Dict[str, Any]:
        """Use the stored refresh_token to obtain a new access_token."""
        rt = self._tokens.get("refresh_token")
        if not rt:
            raise RuntimeError("No refresh_token stored. Re-authorize via build_auth_url.")
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.api_key,
            "refresh_token": rt,
        }
        resp = requests.post(ETSY_TOKEN_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        self._store_tokens(data)
        LOG.info("Token refresh successful.")
        return data

    # ---- Token access ----

    @property
    def access_token(self) -> str:
        """Return a valid access_token, refreshing if expired."""
        if not self._tokens.get("access_token"):
            raise RuntimeError("No access_token. Authorize first.")
        expires_at = self._tokens.get("expires_at", 0)
        if _now_ts() >= expires_at - 60:
            LOG.info("Access token expired or near expiry — refreshing.")
            self.refresh_token()
        return self._tokens["access_token"]

    # ---- Persistence ----

    def _load_tokens(self) -> None:
        """Load tokens from disk if the file exists."""
        if TOKEN_PATH.exists():
            try:
                self._tokens = json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
                LOG.debug("Loaded tokens from %s", TOKEN_PATH)
            except (json.JSONDecodeError, OSError) as exc:
                LOG.warning("Failed to load tokens: %s", exc)
                self._tokens = {}

    def _store_tokens(self, data: Dict[str, Any]) -> None:
        """Persist token response to disk, computing expires_at."""
        data["expires_at"] = _now_ts() + int(data.get("expires_in", 3600))
        data["refreshed_at"] = datetime.now(timezone.utc).isoformat()
        self._tokens = data
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        TOKEN_PATH.chmod(0o600)
        LOG.debug("Tokens written to %s", TOKEN_PATH)

    @property
    def is_authenticated(self) -> bool:
        """True if we hold a non-expired access_token."""
        if not self._tokens.get("access_token"):
            return False
        return _now_ts() < self._tokens.get("expires_at", 0) - 60


# ===================================================================
# EtsyClient — rate-limited, retrying Etsy v3 API wrapper
# ===================================================================
class EtsyClient:
    """HTTP client for Etsy API v3 with token-bucket rate limiting,
    exponential-backoff retries, and automatic 401 token refresh.
    """

    # Rate limiter: 10 requests per second (token bucket)
    _RATE_LIMIT = 10
    _RATE_WINDOW = 1.0  # seconds

    # Retry policy
    _MAX_RETRIES = 3
    _BACKOFF_BASE = 1.0  # seconds
    _BACKOFF_FACTOR = 2.0

    def __init__(self, auth: EtsyAuth) -> None:
        self.auth = auth
        self._request_timestamps: List[float] = []
        self.session = requests.Session()

    # ---- Rate limiter ----

    def _wait_for_rate_limit(self) -> None:
        """Block until a request slot is available under the token-bucket."""
        now = time.monotonic()
        # Purge timestamps older than the rate window
        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < self._RATE_WINDOW
        ]
        if len(self._request_timestamps) >= self._RATE_LIMIT:
            oldest = self._request_timestamps[0]
            sleep_for = self._RATE_WINDOW - (now - oldest)
            if sleep_for > 0:
                LOG.debug("Rate limit reached — sleeping %.3fs", sleep_for)
                time.sleep(sleep_for)
        self._request_timestamps.append(time.monotonic())

    # ---- Core request ----

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.auth.access_token}",
            "x-api-key": self.auth.api_key,
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        """Execute a request with rate limiting, retries, and 401 auto-refresh."""
        url = f"{ETSY_API_BASE}{path}" if path.startswith("/") else path
        last_exc: Optional[Exception] = None

        for attempt in range(self._MAX_RETRIES + 1):
            self._wait_for_rate_limit()
            try:
                headers = self._headers()
                # Remove Content-Type for multipart uploads
                if files:
                    headers.pop("Content-Type", None)

                resp = self.session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    data=data,
                    files=files,
                    timeout=timeout,
                )

                # Auto-refresh on 401
                if resp.status_code == 401 and attempt < self._MAX_RETRIES:
                    LOG.warning("401 received — attempting token refresh (attempt %d).", attempt + 1)
                    self.auth.refresh_token()
                    continue

                # Rate-limited by Etsy (429)
                if resp.status_code == 429:
                    retry_after = float(resp.headers.get("Retry-After", self._BACKOFF_BASE))
                    LOG.warning("429 rate-limited — sleeping %.1fs", retry_after)
                    time.sleep(retry_after)
                    continue

                resp.raise_for_status()

                # Some endpoints return 204 No Content
                if resp.status_code == 204:
                    return {"status": "ok", "code": 204}

                return resp.json()

            except requests.exceptions.RequestException as exc:
                last_exc = exc
                if attempt < self._MAX_RETRIES:
                    backoff = self._BACKOFF_BASE * (self._BACKOFF_FACTOR ** attempt)
                    LOG.warning(
                        "Request failed (attempt %d/%d): %s — retrying in %.1fs",
                        attempt + 1,
                        self._MAX_RETRIES,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                else:
                    LOG.error("Request failed after %d retries: %s", self._MAX_RETRIES + 1, exc)

        raise last_exc  # type: ignore[misc]

    # ---- Shop endpoints ----

    def get_shop(self, shop_id: Optional[int] = None) -> Dict[str, Any]:
        """GET /application/shops/{shop_id}"""
        sid = shop_id or int(_env("ETSY_SHOP_ID"))
        return self._request("GET", f"/application/shops/{sid}")

    # ---- Listing endpoints ----

    def list_listings(
        self,
        shop_id: Optional[int] = None,
        state: str = "active",
        limit: int = 25,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """GET /application/shops/{shop_id}/listings"""
        sid = shop_id or int(_env("ETSY_SHOP_ID"))
        params = {"state": state, "limit": limit, "offset": offset}
        return self._request("GET", f"/application/shops/{sid}/listings", params=params)

    def get_listing(self, listing_id: int) -> Dict[str, Any]:
        """GET /application/listings/{listing_id}"""
        return self._request("GET", f"/application/listings/{listing_id}")

    def create_listing(self, shop_id: Optional[int] = None, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /application/shops/{shop_id}/listings

        Required fields in *data*: title, description, price, quantity,
        taxonomy_id, who_made, when_made, is_supply.
        """
        sid = shop_id or int(_env("ETSY_SHOP_ID"))
        if not data:
            raise ValueError("Listing data payload is required.")
        return self._request("POST", f"/application/shops/{sid}/listings", json_body=data)

    def update_listing(
        self,
        shop_id: Optional[int] = None,
        listing_id: Optional[int] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """PATCH /application/shops/{shop_id}/listings/{listing_id}"""
        sid = shop_id or int(_env("ETSY_SHOP_ID"))
        if listing_id is None:
            raise ValueError("listing_id is required.")
        if not data:
            raise ValueError("Update data payload is required.")
        return self._request("PATCH", f"/application/shops/{sid}/listings/{listing_id}", json_body=data)

    def delete_listing(self, listing_id: int) -> Dict[str, Any]:
        """DELETE /application/listings/{listing_id}"""
        return self._request("DELETE", f"/application/listings/{listing_id}")

    # ---- Listing images ----

    def upload_listing_image(
        self,
        shop_id: Optional[int] = None,
        listing_id: Optional[int] = None,
        image_path: Optional[str] = None,
        rank: int = 1,
    ) -> Dict[str, Any]:
        """POST /application/shops/{shop_id}/listings/{listing_id}/images

        Uploads a local image file to an Etsy listing.
        """
        sid = shop_id or int(_env("ETSY_SHOP_ID"))
        if listing_id is None:
            raise ValueError("listing_id is required.")
        if not image_path or not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        img_path = Path(image_path)
        with open(img_path, "rb") as fh:
            files = {"image": (img_path.name, fh, "image/jpeg")}
            form_data = {"rank": str(rank)}
            return self._request(
                "POST",
                f"/application/shops/{sid}/listings/{listing_id}/images",
                data=form_data,
                files=files,
            )

    def get_listing_images(self, listing_id: int) -> Dict[str, Any]:
        """GET /application/listings/{listing_id}/images"""
        return self._request("GET", f"/application/listings/{listing_id}/images")

    # ---- Listing digital files ----

    def upload_listing_file(
        self,
        shop_id: Optional[int] = None,
        listing_id: Optional[int] = None,
        file_path: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /application/shops/{shop_id}/listings/{listing_id}/files

        Uploads a digital file attachment to a listing.
        """
        sid = shop_id or int(_env("ETSY_SHOP_ID"))
        if listing_id is None:
            raise ValueError("listing_id is required.")
        if not file_path or not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        fp = Path(file_path)
        display_name = name or fp.stem
        with open(fp, "rb") as fh:
            files = {"file": (fp.name, fh, "application/octet-stream")}
            form_data = {"name": display_name}
            return self._request(
                "POST",
                f"/application/shops/{sid}/listings/{listing_id}/files",
                data=form_data,
                files=files,
            )

    def get_listing_files(self, listing_id: int) -> Dict[str, Any]:
        """GET /application/listings/{listing_id}/files"""
        return self._request("GET", f"/application/listings/{listing_id}/files")

    # ---- Transactions ----

    def get_transactions(
        self,
        shop_id: Optional[int] = None,
        limit: int = 25,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """GET /application/shops/{shop_id}/transactions"""
        sid = shop_id or int(_env("ETSY_SHOP_ID"))
        params = {"limit": limit, "offset": offset}
        return self._request("GET", f"/application/shops/{sid}/transactions", params=params)

    # ---- Receipts / Orders ----

    def get_receipts(
        self,
        shop_id: Optional[int] = None,
        was_paid: bool = True,
        limit: int = 25,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """GET /application/shops/{shop_id}/receipts"""
        sid = shop_id or int(_env("ETSY_SHOP_ID"))
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if was_paid:
            params["was_paid"] = "true"
        return self._request("GET", f"/application/shops/{sid}/receipts", params=params)


# ===================================================================
# NotionSync — CRUD operations for 7 Notion databases
# ===================================================================
class NotionSync:
    """Syncs storefront data to Notion databases.

    Database IDs are loaded from environment variables:
      NOTION_DB_SHOP_CONFIG, NOTION_DB_PRODUCT_IDEAS, NOTION_DB_PRODUCTS,
      NOTION_DB_LISTINGS, NOTION_DB_ORDERS, NOTION_DB_SEO_KEYWORDS,
      NOTION_DB_SNAPSHOTS
    """

    DB_ENV_MAP = {
        "shop_config": "NOTION_DB_SHOP_CONFIG",
        "product_ideas": "NOTION_DB_PRODUCT_IDEAS",
        "products": "NOTION_DB_PRODUCTS",
        "listings": "NOTION_DB_LISTINGS",
        "orders": "NOTION_DB_ORDERS",
        "seo_keywords": "NOTION_DB_SEO_KEYWORDS",
        "snapshots": "NOTION_DB_SNAPSHOTS",
    }

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or _env("NOTION_API_KEY")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            }
        )
        self._db_ids: Dict[str, str] = {}
        for label, env_name in self.DB_ENV_MAP.items():
            val = os.environ.get(env_name)
            if val:
                self._db_ids[label] = val

    def get_db_id(self, label: str) -> str:
        """Resolve a friendly label to a Notion database ID."""
        db_id = self._db_ids.get(label)
        if not db_id:
            env_name = self.DB_ENV_MAP.get(label, label)
            raise EnvironmentError(
                f"Notion DB ID for '{label}' not configured. Set {env_name}."
            )
        return db_id

    # ---- Generic CRUD ----

    def query_database(
        self,
        db_id: str,
        filter_obj: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 100,
        start_cursor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /databases/{db_id}/query — query a Notion database."""
        body: Dict[str, Any] = {"page_size": page_size}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts
        if start_cursor:
            body["start_cursor"] = start_cursor
        resp = self.session.post(
            f"{NOTION_API_BASE}/databases/{db_id}/query",
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def create_page(
        self,
        db_id: str,
        properties: Dict[str, Any],
        children: Optional[List[Dict[str, Any]]] = None,
        icon: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /pages — create a new page (row) in a Notion database."""
        body: Dict[str, Any] = {
            "parent": {"database_id": db_id},
            "properties": properties,
        }
        if children:
            body["children"] = children
        if icon:
            body["icon"] = icon
        resp = self.session.post(
            f"{NOTION_API_BASE}/pages",
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def update_page(
        self,
        page_id: str,
        properties: Dict[str, Any],
        archived: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """PATCH /pages/{page_id} — update properties on an existing page."""
        body: Dict[str, Any] = {"properties": properties}
        if archived is not None:
            body["archived"] = archived
        resp = self.session.patch(
            f"{NOTION_API_BASE}/pages/{page_id}",
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def upsert_by_unique(
        self,
        db_id: str,
        unique_prop: str,
        unique_val: Any,
        properties: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Query for a page where unique_prop == unique_val; update it if found, else create.

        Supports rich_text, number, and title property types for the filter.
        """
        # Build a filter that checks the unique property
        if isinstance(unique_val, (int, float)):
            filter_obj = {
                "property": unique_prop,
                "number": {"equals": unique_val},
            }
        else:
            filter_obj = {
                "property": unique_prop,
                "rich_text": {"equals": str(unique_val)},
            }

        result = self.query_database(db_id, filter_obj=filter_obj, page_size=1)
        existing = result.get("results", [])

        if existing:
            page_id = existing[0]["id"]
            LOG.debug("Upsert: updating existing page %s", page_id)
            return self.update_page(page_id, properties)
        else:
            LOG.debug("Upsert: creating new page in %s", db_id)
            return self.create_page(db_id, properties)

    # ---- Notion property builders ----

    @staticmethod
    def _title(text: str) -> Dict[str, Any]:
        return {"title": [{"type": "text", "text": {"content": str(text)[:2000]}}]}

    @staticmethod
    def _rich_text(text: str) -> Dict[str, Any]:
        return {"rich_text": [{"type": "text", "text": {"content": str(text)[:2000]}}]}

    @staticmethod
    def _number(val: Any) -> Dict[str, Any]:
        try:
            return {"number": float(val)}
        except (TypeError, ValueError):
            return {"number": 0}

    @staticmethod
    def _select(name: str) -> Dict[str, Any]:
        return {"select": {"name": str(name)}}

    @staticmethod
    def _multi_select(names: List[str]) -> Dict[str, Any]:
        return {"multi_select": [{"name": n} for n in names]}

    @staticmethod
    def _url(url: str) -> Dict[str, Any]:
        return {"url": str(url) if url else None}

    @staticmethod
    def _date(iso_str: str) -> Dict[str, Any]:
        return {"date": {"start": iso_str}}

    @staticmethod
    def _checkbox(val: bool) -> Dict[str, Any]:
        return {"checkbox": bool(val)}

    # ---- Listing sync ----

    def sync_listing(self, listing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a single Etsy listing into the Listings Notion database.

        Maps Etsy listing fields → Notion properties.
        """
        db_id = self.get_db_id("listings")
        listing_id = listing_data.get("listing_id", 0)

        # Extract pricing — Etsy returns price as {"amount": cents, "divisor": 100, ...}
        price_obj = listing_data.get("price", {})
        if isinstance(price_obj, dict):
            price = price_obj.get("amount", 0) / max(price_obj.get("divisor", 100), 1)
        else:
            price = float(price_obj) if price_obj else 0.0

        # Build tags list
        tags = listing_data.get("tags", [])
        if isinstance(tags, list):
            tags_str = ", ".join(tags[:13])
        else:
            tags_str = str(tags)

        # Listing URL
        url = listing_data.get("url", f"https://www.etsy.com/listing/{listing_id}")

        # Timestamps
        created_ts = listing_data.get("created_timestamp")
        updated_ts = listing_data.get("updated_timestamp")
        created_iso = (
            datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()
            if created_ts
            else datetime.now(timezone.utc).isoformat()
        )
        updated_iso = (
            datetime.fromtimestamp(updated_ts, tz=timezone.utc).isoformat()
            if updated_ts
            else datetime.now(timezone.utc).isoformat()
        )

        properties: Dict[str, Any] = {
            "Title": self._title(listing_data.get("title", "Untitled")),
            "Listing ID": self._number(listing_id),
            "State": self._select(listing_data.get("state", "draft")),
            "Description": self._rich_text(listing_data.get("description", "")[:2000]),
            "Price": self._number(price),
            "Currency": self._rich_text(listing_data.get("currency_code", "USD")),
            "Quantity": self._number(listing_data.get("quantity", 0)),
            "Tags": self._rich_text(tags_str),
            "Views": self._number(listing_data.get("views", 0)),
            "Favorites": self._number(listing_data.get("num_favorers", 0)),
            "URL": self._url(url),
            "Taxonomy ID": self._number(listing_data.get("taxonomy_id", 0)),
            "Who Made": self._rich_text(listing_data.get("who_made", "")),
            "When Made": self._rich_text(listing_data.get("when_made", "")),
            "Is Supply": self._checkbox(listing_data.get("is_supply", False)),
            "Is Digital": self._checkbox(listing_data.get("is_digital", False)),
            "Is Personalizable": self._checkbox(listing_data.get("is_personalizable", False)),
            "Created": self._date(created_iso),
            "Updated": self._date(updated_iso),
            "Last Synced": self._date(datetime.now(timezone.utc).isoformat()),
        }

        return self.upsert_by_unique(db_id, "Listing ID", listing_id, properties)

    # ---- Order / receipt sync ----

    def sync_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert a single Etsy receipt/order into the Orders Notion database.

        Maps receipt fields → Notion properties with fee breakdown.
        """
        db_id = self.get_db_id("orders")
        receipt_id = order_data.get("receipt_id", 0)

        # Price helper for Etsy money objects
        def _money(field: str) -> float:
            obj = order_data.get(field, {})
            if isinstance(obj, dict):
                return obj.get("amount", 0) / max(obj.get("divisor", 100), 1)
            try:
                return float(obj)
            except (TypeError, ValueError):
                return 0.0

        # Buyer name
        buyer_name = order_data.get("name", "")
        buyer_email = order_data.get("buyer_email", "")

        # Timestamps
        created_ts = order_data.get("create_timestamp")
        created_iso = (
            datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()
            if created_ts
            else datetime.now(timezone.utc).isoformat()
        )
        updated_ts = order_data.get("update_timestamp")
        updated_iso = (
            datetime.fromtimestamp(updated_ts, tz=timezone.utc).isoformat()
            if updated_ts
            else datetime.now(timezone.utc).isoformat()
        )

        # Transaction items — join listing titles
        transactions = order_data.get("transactions", [])
        item_titles = [t.get("title", "") for t in transactions if isinstance(t, dict)]
        items_str = "; ".join(item_titles) if item_titles else "N/A"

        # Quantity sum
        total_qty = sum(
            t.get("quantity", 0) for t in transactions if isinstance(t, dict)
        )

        properties: Dict[str, Any] = {
            "Receipt ID": self._title(str(receipt_id)),
            "Receipt ID Num": self._number(receipt_id),
            "Buyer": self._rich_text(buyer_name),
            "Buyer Email": self._rich_text(buyer_email),
            "Items": self._rich_text(items_str[:2000]),
            "Quantity": self._number(total_qty),
            "Subtotal": self._number(_money("subtotal")),
            "Grand Total": self._number(_money("grandtotal")),
            "Shipping Cost": self._number(_money("total_shipping_cost")),
            "Tax": self._number(_money("total_tax_cost")),
            "Discount": self._number(_money("discount_amt")),
            "Gift Wrap Cost": self._number(_money("gift_wrap_price")),
            "Payment Method": self._rich_text(order_data.get("payment_method", "")),
            "Was Paid": self._checkbox(order_data.get("was_paid", False)),
            "Was Shipped": self._checkbox(order_data.get("was_shipped", False)),
            "Was Delivered": self._checkbox(order_data.get("was_delivered", False)),
            "Status": self._select(
                "Paid" if order_data.get("was_paid") else "Unpaid"
            ),
            "Order Date": self._date(created_iso),
            "Updated": self._date(updated_iso),
            "Last Synced": self._date(datetime.now(timezone.utc).isoformat()),
        }

        return self.upsert_by_unique(db_id, "Receipt ID Num", receipt_id, properties)

    # ---- Bulk sync helpers ----

    def sync_all_listings(self, listings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sync a batch of Etsy listings to Notion."""
        results = []
        for listing in listings:
            try:
                result = self.sync_listing(listing)
                results.append({"listing_id": listing.get("listing_id"), "status": "ok"})
                LOG.info("Synced listing %s", listing.get("listing_id"))
            except Exception as exc:
                results.append({"listing_id": listing.get("listing_id"), "status": "error", "error": str(exc)})
                LOG.error("Failed to sync listing %s: %s", listing.get("listing_id"), exc)
        return results

    def sync_all_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Sync a batch of Etsy receipts/orders to Notion."""
        results = []
        for order in orders:
            try:
                result = self.sync_order(order)
                results.append({"receipt_id": order.get("receipt_id"), "status": "ok"})
                LOG.info("Synced order %s", order.get("receipt_id"))
            except Exception as exc:
                results.append({"receipt_id": order.get("receipt_id"), "status": "error", "error": str(exc)})
                LOG.error("Failed to sync order %s: %s", order.get("receipt_id"), exc)
        return results

    # ---- Shop config helpers ----

    def get_config(self, key: str) -> Optional[str]:
        """Read a key-value pair from the Shop Config database."""
        db_id = self.get_db_id("shop_config")
        filter_obj = {"property": "Key", "title": {"equals": key}}
        result = self.query_database(db_id, filter_obj=filter_obj, page_size=1)
        pages = result.get("results", [])
        if not pages:
            return None
        props = pages[0].get("properties", {})
        value_prop = props.get("Value", {})
        rich_texts = value_prop.get("rich_text", [])
        if rich_texts:
            return rich_texts[0].get("text", {}).get("content", "")
        return None

    def set_config(self, key: str, value: str) -> Dict[str, Any]:
        """Write a key-value pair to the Shop Config database (upsert)."""
        db_id = self.get_db_id("shop_config")
        properties = {
            "Key": self._title(key),
            "Value": self._rich_text(value),
            "Updated": self._date(datetime.now(timezone.utc).isoformat()),
        }
        return self.upsert_by_unique(db_id, "Key", key, properties)

    # ---- Snapshot ----

    def create_snapshot(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Write a business snapshot row with key metrics."""
        db_id = self.get_db_id("snapshots")
        now_iso = datetime.now(timezone.utc).isoformat()
        properties: Dict[str, Any] = {
            "Date": self._title(now_iso[:10]),
            "Timestamp": self._date(now_iso),
            "Total Listings": self._number(metrics.get("total_listings", 0)),
            "Active Listings": self._number(metrics.get("active_listings", 0)),
            "Total Orders": self._number(metrics.get("total_orders", 0)),
            "Revenue": self._number(metrics.get("revenue", 0)),
            "Views": self._number(metrics.get("views", 0)),
            "Favorites": self._number(metrics.get("favorites", 0)),
            "Conversion Rate": self._number(metrics.get("conversion_rate", 0)),
            "Notes": self._rich_text(metrics.get("notes", "")),
        }
        return self.create_page(db_id, properties)


# ===================================================================
# CLI entrypoint
# ===================================================================
def _run_test(etsy: EtsyClient, notion: NotionSync) -> None:
    """Connectivity smoke test: verify auth, fetch shop, query one Notion DB."""
    print("=" * 60)
    print("  Etsy + Notion connectivity test")
    print("=" * 60)

    # 1. Auth check
    print("\n[1/3] Checking Etsy authentication...")
    if etsy.auth.is_authenticated:
        print("  ✅ Authenticated (token present and not expired)")
    else:
        print("  ⚠️  Token missing or expired — attempting refresh...")
        try:
            etsy.auth.refresh_token()
            print("  ✅ Token refreshed successfully")
        except Exception as exc:
            print(f"  ❌ Token refresh failed: {exc}")
            print("     Run with --refresh-token or re-authorize.")

    # 2. Fetch shop info
    print("\n[2/3] Fetching shop info from Etsy...")
    try:
        shop = etsy.get_shop()
        shop_name = shop.get("shop_name", "Unknown")
        shop_id = shop.get("shop_id", "?")
        num_listings = shop.get("listing_active_count", "?")
        print(f"  ✅ Shop: {shop_name} (ID: {shop_id})")
        print(f"     Active listings: {num_listings}")
    except Exception as exc:
        print(f"  ❌ Failed to fetch shop: {exc}")

    # 3. Query first available Notion DB
    print("\n[3/3] Testing Notion API connectivity...")
    tested = False
    for label in notion.DB_ENV_MAP:
        try:
            db_id = notion.get_db_id(label)
        except EnvironmentError:
            continue
        try:
            result = notion.query_database(db_id, page_size=1)
            count = len(result.get("results", []))
            print(f"  ✅ Queried '{label}' database — got {count} result(s)")
            tested = True
            break
        except Exception as exc:
            print(f"  ❌ Failed to query '{label}': {exc}")
            tested = True
            break

    if not tested:
        print("  ⚠️  No Notion DB IDs configured — skipping Notion test.")

    print("\n" + "=" * 60)
    print("  Test complete.")
    print("=" * 60)


def _show_shop_info(etsy: EtsyClient) -> None:
    """Pretty-print shop info as JSON."""
    shop = etsy.get_shop()
    print(json.dumps(shop, indent=2, default=str))


def _force_refresh(auth: EtsyAuth) -> None:
    """Force refresh the OAuth token and print result."""
    data = auth.refresh_token()
    print("Token refreshed successfully.")
    print(f"  Expires at: {datetime.fromtimestamp(data.get('expires_at', 0), tz=timezone.utc).isoformat()}")


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Etsy API v3 + Notion sync client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python etsy_client.py --test            # Run connectivity tests
  python etsy_client.py --refresh-token   # Force refresh OAuth token
  python etsy_client.py --shop-info       # Print shop info JSON
        """,
    )
    parser.add_argument("--test", action="store_true", help="Run connectivity smoke tests")
    parser.add_argument("--refresh-token", action="store_true", help="Force refresh OAuth token")
    parser.add_argument("--shop-info", action="store_true", help="Print shop info as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not any([args.test, args.refresh_token, args.shop_info]):
        parser.print_help()
        sys.exit(0)

    try:
        auth = EtsyAuth()
    except EnvironmentError as exc:
        print(f"❌ Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.refresh_token:
        try:
            _force_refresh(auth)
        except Exception as exc:
            print(f"❌ Token refresh failed: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    etsy = EtsyClient(auth)

    if args.shop_info:
        try:
            _show_shop_info(etsy)
        except Exception as exc:
            print(f"❌ Failed to fetch shop info: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    if args.test:
        try:
            notion = NotionSync()
        except EnvironmentError:
            notion = NotionSync.__new__(NotionSync)
            notion.api_key = ""
            notion.session = requests.Session()
            notion._db_ids = {}
            LOG.warning("NOTION_API_KEY not set — Notion tests will be skipped.")
        _run_test(etsy, notion)


if __name__ == "__main__":
    main()
