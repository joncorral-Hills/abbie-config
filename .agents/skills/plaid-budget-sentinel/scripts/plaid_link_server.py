#!/usr/bin/env python3
"""
Plaid Link Server — One-Time Bank Connection Flow
==================================================

A lightweight Flask server that serves a Plaid Link UI so Jon can connect
bank accounts.  After all desired institutions are linked, the server
prints the env-var configuration block and shuts itself down.

Usage
-----
    export PLAID_CLIENT_ID="..."
    export PLAID_SECRET="..."
    export PLAID_ENV="sandbox"          # or "development" / "production"
    python plaid_link_server.py

The server binds to 0.0.0.0:8443 by default.  Override with PLAID_LINK_PORT.

⚠  This is a ONE-TIME setup utility.  Do not leave it running in production.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Graceful dependency checks
# ---------------------------------------------------------------------------

try:
    from flask import Flask, jsonify, request
except ImportError:
    print(
        "\n❌  Flask is not installed.\n"
        "   Install it with:  pip install flask\n"
    )
    sys.exit(1)

try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
    from plaid.model.products import Products
    from plaid.model.accounts_get_request import AccountsGetRequest
except ImportError:
    print(
        "\n❌  plaid-python is not installed.\n"
        "   Install it with:  pip install plaid-python\n"
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("plaid-link-server")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PLAID_CLIENT_ID: str = os.environ.get("PLAID_CLIENT_ID", "")
PLAID_SECRET: str = os.environ.get("PLAID_SECRET", "")
PLAID_ENV: str = os.environ.get("PLAID_ENV", "sandbox")
PLAID_LINK_PORT: int = int(os.environ.get("PLAID_LINK_PORT", "8443"))

TOKEN_PATH: Path = Path.home() / ".hermes" / "plaid_tokens.json"

ENV_MAP: Dict[str, plaid.Environment] = {
    "sandbox": plaid.Environment.Sandbox,
    "development": plaid.Environment.Development,
    "production": plaid.Environment.Production,
}

# ---------------------------------------------------------------------------
# Plaid client bootstrap
# ---------------------------------------------------------------------------


def _build_plaid_client() -> plaid_api.PlaidApi:
    """Construct and return an authenticated Plaid API client."""
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        log.error("PLAID_CLIENT_ID and PLAID_SECRET env vars are required.")
        sys.exit(1)

    env = ENV_MAP.get(PLAID_ENV.lower())
    if env is None:
        log.error("PLAID_ENV must be one of: sandbox, development, production")
        sys.exit(1)

    configuration = plaid.Configuration(
        host=env,
        api_key={
            "clientId": PLAID_CLIENT_ID,
            "secret": PLAID_SECRET,
        },
    )
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


client: plaid_api.PlaidApi = _build_plaid_client()

# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------


def _load_tokens() -> Dict[str, Any]:
    """Load the token file or return a fresh skeleton."""
    if TOKEN_PATH.exists():
        try:
            return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Could not read %s: %s — starting fresh.", TOKEN_PATH, exc)

    return {
        "_meta": {
            "description": "Plaid access tokens. KEEP SECRET.",
            "created": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
        "institutions": {},
    }


def _save_tokens(data: Dict[str, Any]) -> None:
    """Persist token data to disk with restrictive permissions."""
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # chmod 600 — owner read/write only
    TOKEN_PATH.chmod(0o600)
    log.info("Tokens saved to %s", TOKEN_PATH)


tokens: Dict[str, Any] = _load_tokens()

# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

INDEX_HTML: str = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plaid Link — Budget Sentinel</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #1a1a2e;
    color: #e0e0e0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2rem 1rem;
  }
  h1 {
    font-size: 1.75rem;
    color: #4ade80;
    margin-bottom: 0.25rem;
  }
  .subtitle {
    color: #888;
    font-size: 0.85rem;
    margin-bottom: 2rem;
  }
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
    width: 100%;
    max-width: 720px;
    margin-bottom: 2rem;
  }
  .card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(74,222,128,0.15);
    border-radius: 12px;
    padding: 1.25rem;
    transition: border-color 0.2s;
  }
  .card:hover { border-color: rgba(74,222,128,0.4); }
  .card h3 {
    color: #4ade80;
    font-size: 1rem;
    margin-bottom: 0.5rem;
  }
  .card .acct {
    font-size: 0.82rem;
    color: #aaa;
    padding: 0.15rem 0;
  }
  .card .acct .mask {
    color: #4ade80;
    font-family: 'SF Mono', 'Fira Code', monospace;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    border: none;
    border-radius: 8px;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.2s, transform 0.1s;
  }
  .btn:active { transform: scale(0.97); }
  .btn-primary {
    background: #4ade80;
    color: #1a1a2e;
  }
  .btn-primary:hover { background: #22c55e; }
  .btn-done {
    background: rgba(74,222,128,0.12);
    color: #4ade80;
    border: 1px solid rgba(74,222,128,0.3);
    margin-left: 0.75rem;
  }
  .btn-done:hover { background: rgba(74,222,128,0.22); }
  .actions { margin-top: 1rem; }
  .status {
    margin-top: 1.5rem;
    font-size: 0.85rem;
    color: #888;
    min-height: 1.2em;
  }
  .status.error { color: #f87171; }
  .status.success { color: #4ade80; }
  .empty {
    color: #555;
    font-size: 0.85rem;
    grid-column: 1 / -1;
    text-align: center;
    padding: 2rem;
  }
  @media (max-width: 480px) {
    body { padding: 1rem 0.5rem; }
    h1 { font-size: 1.4rem; }
  }
</style>
</head>
<body>
  <h1>🏦 Budget Sentinel</h1>
  <p class="subtitle">Connect your bank accounts via Plaid</p>

  <div class="card-grid" id="connections"></div>

  <div class="actions">
    <button class="btn btn-primary" id="connectBtn" onclick="connectBank()">
      ＋ Connect Bank
    </button>
    <button class="btn btn-done" id="doneBtn" onclick="finishSetup()">
      Done — Generate Config
    </button>
  </div>

  <p class="status" id="status"></p>

  <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
  <script>
    const statusEl  = document.getElementById('status');
    const gridEl    = document.getElementById('connections');

    function setStatus(msg, cls) {
      statusEl.textContent = msg;
      statusEl.className = 'status ' + (cls || '');
    }

    async function loadConnections() {
      try {
        const res  = await fetch('/api/connections');
        const data = await res.json();
        const insts = data.institutions || {};
        const keys  = Object.keys(insts);

        if (keys.length === 0) {
          gridEl.innerHTML = '<p class="empty">No accounts connected yet.</p>';
          return;
        }

        gridEl.innerHTML = keys.map(k => {
          const inst = insts[k];
          const accounts = (inst.accounts || []).map(a =>
            `<div class="acct">${a.name} &middot; <span class="mask">••${a.mask}</span> &middot; ${a.subtype || a.type}</div>`
          ).join('');
          return `<div class="card"><h3>${inst.institution_name}</h3>${accounts}</div>`;
        }).join('');
      } catch (e) {
        console.error(e);
      }
    }

    async function connectBank() {
      setStatus('Creating link token…');
      try {
        const res  = await fetch('/api/create_link_token', { method: 'POST' });
        const data = await res.json();
        if (!data.link_token) {
          setStatus('Error: ' + (data.error || 'no link token'), 'error');
          return;
        }

        setStatus('Opening Plaid Link…');
        const handler = Plaid.create({
          token: data.link_token,
          onSuccess: async (public_token, metadata) => {
            setStatus('Exchanging token…');
            const exRes = await fetch('/api/exchange_token', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                public_token: public_token,
                institution: {
                  institution_id: metadata.institution.institution_id,
                  name: metadata.institution.name,
                },
              }),
            });
            const exData = await exRes.json();
            if (exData.ok) {
              setStatus('✓ Connected ' + metadata.institution.name, 'success');
              loadConnections();
            } else {
              setStatus('Exchange error: ' + (exData.error || 'unknown'), 'error');
            }
          },
          onExit: (err) => {
            if (err) {
              setStatus('Link exited with error: ' + err.display_message, 'error');
            } else {
              setStatus('');
            }
          },
        });
        handler.open();
      } catch (e) {
        setStatus('Error: ' + e.message, 'error');
      }
    }

    async function finishSetup() {
      setStatus('Generating config…');
      try {
        const res = await fetch('/api/done', { method: 'POST' });
        const data = await res.json();
        setStatus('✓ Config printed to terminal. Server shutting down.', 'success');
        document.getElementById('connectBtn').disabled = true;
        document.getElementById('doneBtn').disabled = true;
      } catch (e) {
        setStatus('Error: ' + e.message, 'error');
      }
    }

    // Initial load
    loadConnections();
  </script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# Flask App
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


@app.route("/")
def index() -> str:
    """Serve the Plaid Link UI."""
    return INDEX_HTML


@app.route("/api/create_link_token", methods=["POST"])
def create_link_token() -> tuple:
    """Create a Plaid Link token for the front-end."""
    try:
        request_body = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id="jon-corral"),
            client_name="Budget Sentinel",
            products=[Products("transactions")],
            country_codes=[CountryCode("US")],
            language="en",
        )
        response = client.link_token_create(request_body)
        log.info("Link token created successfully.")
        return jsonify({"link_token": response.link_token}), 200
    except plaid.ApiException as exc:
        body = json.loads(exc.body)
        log.error("Plaid API error creating link token: %s", body)
        return jsonify({"error": body.get("error_message", str(exc))}), 400
    except Exception as exc:
        log.exception("Unexpected error creating link token")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/exchange_token", methods=["POST"])
def exchange_token() -> tuple:
    """Exchange a public token for a persistent access token and store it."""
    payload: Dict[str, Any] = request.get_json(force=True)
    public_token: Optional[str] = payload.get("public_token")
    institution_info: Optional[Dict[str, str]] = payload.get("institution")

    if not public_token or not institution_info:
        return jsonify({"ok": False, "error": "Missing public_token or institution"}), 400

    institution_id: str = institution_info.get("institution_id", "unknown")
    institution_name: str = institution_info.get("name", "Unknown")

    try:
        # Exchange public token → access token
        exchange_req = ItemPublicTokenExchangeRequest(public_token=public_token)
        exchange_resp = client.item_public_token_exchange(exchange_req)
        access_token: str = exchange_resp.access_token

        # Fetch account details
        accounts_req = AccountsGetRequest(access_token=access_token)
        accounts_resp = client.accounts_get(accounts_req)

        account_list: List[Dict[str, Any]] = []
        for acct in accounts_resp.accounts:
            account_list.append({
                "id": acct.account_id,
                "name": acct.name,
                "mask": acct.mask,
                "type": str(acct.type),
                "subtype": str(acct.subtype) if acct.subtype else None,
            })

        # Derive a slug key for storage
        slug: str = institution_name.lower().replace(" ", "_").replace("'", "")

        tokens["institutions"][slug] = {
            "access_token": access_token,
            "institution_id": institution_id,
            "institution_name": institution_name,
            "accounts": account_list,
            "connected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        _save_tokens(tokens)

        log.info(
            "✓ Connected %s (%d accounts)",
            institution_name,
            len(account_list),
        )
        return jsonify({"ok": True, "institution": institution_name, "accounts": len(account_list)}), 200

    except plaid.ApiException as exc:
        body = json.loads(exc.body)
        log.error("Plaid API error during exchange: %s", body)
        return jsonify({"ok": False, "error": body.get("error_message", str(exc))}), 400
    except Exception as exc:
        log.exception("Unexpected error during token exchange")
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/connections", methods=["GET"])
def get_connections() -> tuple:
    """Return the currently connected institutions and their accounts."""
    return jsonify({"institutions": tokens.get("institutions", {})}), 200


@app.route("/api/done", methods=["POST"])
def done() -> tuple:
    """Print environment variable configuration and shut down the server."""
    institutions = tokens.get("institutions", {})

    print("\n" + "=" * 64)
    print("  ✅  Plaid Link Setup Complete")
    print("=" * 64)
    print(f"\n  Tokens saved to: {TOKEN_PATH}")
    print(f"  Institutions connected: {len(institutions)}")
    for slug, inst in institutions.items():
        acct_count = len(inst.get("accounts", []))
        print(f"    • {inst['institution_name']} — {acct_count} account(s)")
    print("\n  Required environment variables for Budget Sentinel:")
    print(f"    PLAID_CLIENT_ID={PLAID_CLIENT_ID}")
    print(f"    PLAID_SECRET=<redacted>")
    print(f"    PLAID_ENV={PLAID_ENV}")
    print(f"    PLAID_TOKENS_PATH={TOKEN_PATH}")
    print("\n" + "=" * 64 + "\n")

    # Schedule server shutdown in a background thread
    def _shutdown() -> None:
        log.info("Shutting down Plaid Link server…")
        os.kill(os.getpid(), signal.SIGINT)

    threading.Timer(1.0, _shutdown).start()

    return jsonify({"ok": True, "message": "Config printed. Server shutting down."}), 200


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Start the one-time Plaid Link server."""
    print()
    print("┌─────────────────────────────────────────────────────┐")
    print("│  ⚠  ONE-TIME USE — Plaid Link Setup Server         │")
    print("│                                                     │")
    print("│  This server is meant for initial bank account      │")
    print("│  linking only.  Shut it down after connecting all   │")
    print("│  desired accounts by clicking 'Done' in the UI.     │")
    print("│                                                     │")
    print(f"│  Plaid env:  {PLAID_ENV:<40s}│")
    print(f"│  Token file: {str(TOKEN_PATH):<40s}│")
    print(f"│  Port:       {PLAID_LINK_PORT:<40d}│")
    print("└─────────────────────────────────────────────────────┘")
    print()

    app.run(
        host="0.0.0.0",
        port=PLAID_LINK_PORT,
        debug=False,
    )


if __name__ == "__main__":
    main()
