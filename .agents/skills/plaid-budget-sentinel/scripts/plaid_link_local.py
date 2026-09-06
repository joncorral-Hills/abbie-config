#!/usr/bin/env python3
"""
Plaid Link — Local Mac Setup
Runs a tiny local server on your Mac so you can connect bank accounts
via Plaid Link directly in your browser. No external dependencies needed.

Usage:
    python3 plaid_link_local.py

Then open http://localhost:9876 in your browser.
"""

import http.server
import json
import os
import ssl
import sys
import urllib.request
import urllib.parse
from datetime import datetime

# ── Configuration ──────────────────────────────────────────────────────────────
PLAID_CLIENT_ID = os.environ.get("PLAID_CLIENT_ID", "6a58fb3a4b80c1000d2e020d")
PLAID_SECRET = os.environ.get("PLAID_SECRET", "19327fb420aa9a50a11539f8f37780")
PLAID_ENV = os.environ.get("PLAID_ENV", "production")
PORT = int(os.environ.get("PLAID_LINK_PORT", "9876"))

PLAID_BASE_URL = {
    "sandbox": "https://sandbox.plaid.com",
    "production": "https://production.plaid.com",
}.get(PLAID_ENV, "https://production.plaid.com")

# Store connected institutions
connected = {}


def plaid_api(endpoint: str, payload: dict) -> dict:
    """Call a Plaid API endpoint."""
    payload["client_id"] = PLAID_CLIENT_ID
    payload["secret"] = PLAID_SECRET
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{PLAID_BASE_URL}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"Plaid API error on {endpoint}: {e.code} — {body}", file=sys.stderr)
        raise


def create_link_token() -> str:
    """Create a Plaid Link token."""
    resp = plaid_api("/link/token/create", {
        "user": {"client_user_id": "jon-corral"},
        "client_name": "Allie Budget Sentinel",
        "products": ["transactions"],
        "country_codes": ["US"],
        "language": "en",
    })
    return resp["link_token"]


def exchange_public_token(public_token: str) -> str:
    """Exchange a public token for an access token."""
    resp = plaid_api("/item/public_token/exchange", {
        "public_token": public_token,
    })
    return resp["access_token"]


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Plaid Budget Sentinel — Connect Banks</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f0f23;
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 40px 20px;
        }
        h1 {
            font-size: 28px;
            color: #4ade80;
            margin-bottom: 8px;
        }
        .subtitle {
            color: #888;
            margin-bottom: 32px;
            font-size: 14px;
        }
        .btn {
            background: #4ade80;
            color: #0f0f23;
            border: none;
            padding: 16px 32px;
            border-radius: 12px;
            font-size: 18px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 32px;
        }
        .btn:hover { background: #22c55e; transform: scale(1.02); }
        .btn:disabled { background: #333; color: #666; cursor: not-allowed; transform: none; }
        .connections {
            width: 100%;
            max-width: 500px;
        }
        .card {
            background: #1a1a3e;
            border: 1px solid #2a2a5e;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 12px;
            animation: fadeIn 0.3s ease;
        }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .card h3 { color: #4ade80; margin-bottom: 8px; font-size: 18px; }
        .card .accounts { color: #aaa; font-size: 14px; }
        .card .accounts span { display: block; padding: 2px 0; }
        .done-btn {
            background: #2563eb;
            color: white;
            border: none;
            padding: 16px 32px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            margin-top: 20px;
            display: none;
            transition: all 0.2s;
        }
        .done-btn:hover { background: #1d4ed8; }
        .status {
            margin-top: 12px;
            padding: 12px 20px;
            border-radius: 8px;
            font-size: 14px;
            display: none;
        }
        .status.success { display: block; background: #064e3b; color: #4ade80; border: 1px solid #065f46; }
        .status.error { display: block; background: #450a0a; color: #f87171; border: 1px solid #7f1d1d; }
        .env-output {
            background: #111;
            border: 1px solid #333;
            border-radius: 8px;
            padding: 16px;
            font-family: monospace;
            font-size: 13px;
            white-space: pre-wrap;
            word-break: break-all;
            margin-top: 20px;
            display: none;
            width: 100%;
            max-width: 500px;
            color: #4ade80;
        }
        .instructions {
            background: #1a1a3e;
            border: 1px solid #2a2a5e;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
            max-width: 500px;
            font-size: 14px;
            color: #aaa;
            line-height: 1.6;
        }
        .instructions strong { color: #e0e0e0; }
    </style>
</head>
<body>
    <h1>🏦 Plaid Budget Sentinel</h1>
    <p class="subtitle">Connect your bank accounts for Allie</p>

    <div class="instructions">
        <strong>How this works:</strong><br>
        Click "Connect Bank" below. A Plaid popup will open where you log into
        your bank (Chase, US Bank, etc.) directly. Your credentials are never
        sent to this page — Plaid handles authentication securely.<br><br>
        Connect each bank one at a time. When done, click "Generate Config."
    </div>

    <button class="btn" id="connectBtn" onclick="connectBank()">Connect Bank</button>

    <div class="connections" id="connections"></div>
    <div id="status" class="status"></div>
    <button class="done-btn" id="doneBtn" onclick="generateConfig()">✅ Done — Generate Config</button>
    <div class="env-output" id="envOutput"></div>

    <script>
        let connectionCount = 0;

        async function connectBank() {
            const btn = document.getElementById('connectBtn');
            btn.disabled = true;
            btn.textContent = 'Loading...';

            try {
                const resp = await fetch('/api/create_link_token', { method: 'POST' });
                const data = await resp.json();

                if (data.error) {
                    showStatus('Error: ' + data.error, 'error');
                    btn.disabled = false;
                    btn.textContent = 'Connect Bank';
                    return;
                }

                const handler = Plaid.create({
                    token: data.link_token,
                    onSuccess: async (public_token, metadata) => {
                        showStatus('Exchanging token for ' + metadata.institution.name + '...', 'success');
                        const exchResp = await fetch('/api/exchange_token', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                public_token: public_token,
                                institution_name: metadata.institution.name,
                                institution_id: metadata.institution.institution_id,
                                accounts: metadata.accounts,
                            }),
                        });
                        const exchData = await exchResp.json();
                        if (exchData.status === 'success') {
                            connectionCount++;
                            addConnectionCard(exchData);
                            showStatus('✅ ' + exchData.institution + ' connected!', 'success');
                            document.getElementById('doneBtn').style.display = 'block';
                        } else {
                            showStatus('Error: ' + (exchData.error || 'Unknown'), 'error');
                        }
                        btn.disabled = false;
                        btn.textContent = 'Connect Another Bank';
                    },
                    onExit: (err) => {
                        btn.disabled = false;
                        btn.textContent = connectionCount > 0 ? 'Connect Another Bank' : 'Connect Bank';
                        if (err) showStatus('Link exited: ' + err.display_message, 'error');
                    },
                });
                handler.open();
            } catch (e) {
                showStatus('Error: ' + e.message, 'error');
                btn.disabled = false;
                btn.textContent = 'Connect Bank';
            }
        }

        function addConnectionCard(data) {
            const div = document.getElementById('connections');
            const accounts = data.accounts.map(a =>
                `<span>• ${a.name} (...${a.mask}) — ${a.subtype || a.type}</span>`
            ).join('');
            div.innerHTML += `
                <div class="card">
                    <h3>🏦 ${data.institution}</h3>
                    <div class="accounts">${accounts}</div>
                </div>`;
        }

        function showStatus(msg, type) {
            const el = document.getElementById('status');
            el.textContent = msg;
            el.className = 'status ' + type;
        }

        async function generateConfig() {
            const resp = await fetch('/api/done', { method: 'POST' });
            const data = await resp.json();
            const el = document.getElementById('envOutput');
            el.style.display = 'block';
            el.textContent = '# Add this to Allie\\'s environment:\\n\\nexport PLAID_ACCESS_TOKENS=\\'' + JSON.stringify(data.tokens) + '\\'\\n\\n# Send this entire block to Allie via Telegram.';

            showStatus('✅ Config generated! Copy the block below and send it to Allie.', 'success');
            document.getElementById('doneBtn').style.display = 'none';
        }
    </script>
</body>
</html>
"""


class PlaidLinkHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the local Plaid Link server."""

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass

    def _respond(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def _respond_html(self, html: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_GET(self):
        if self.path == "/" or self.path == "":
            self._respond_html(HTML_PAGE)
        elif self.path == "/api/connections":
            self._respond(200, {"institutions": connected})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/create_link_token":
            try:
                token = create_link_token()
                self._respond(200, {"link_token": token})
            except Exception as e:
                self._respond(500, {"error": str(e)})

        elif self.path == "/api/exchange_token":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            try:
                access_token = exchange_public_token(body["public_token"])
                inst_name = body.get("institution_name", "Unknown")
                inst_key = inst_name.lower().replace(" ", "_")
                accounts = body.get("accounts", [])

                connected[inst_key] = {
                    "access_token": access_token,
                    "institution_name": inst_name,
                    "institution_id": body.get("institution_id", ""),
                    "accounts": [
                        {
                            "id": a.get("id", ""),
                            "name": a.get("name", ""),
                            "mask": a.get("mask", ""),
                            "type": a.get("type", ""),
                            "subtype": a.get("subtype", ""),
                        }
                        for a in accounts
                    ],
                    "connected_at": datetime.now().isoformat(),
                }

                print(f"  ✅ Connected: {inst_name} ({len(accounts)} accounts)")
                self._respond(200, {
                    "status": "success",
                    "institution": inst_name,
                    "accounts": connected[inst_key]["accounts"],
                })
            except Exception as e:
                self._respond(500, {"error": str(e)})

        elif self.path == "/api/done":
            tokens = {k: v["access_token"] for k, v in connected.items()}
            tokens_json = json.dumps(tokens)

            print("\n" + "=" * 60)
            print("🎉 ALL BANKS CONNECTED!")
            print("=" * 60)
            print(f"\nConnected {len(connected)} institution(s):")
            for key, info in connected.items():
                acct_names = ", ".join(a["name"] for a in info["accounts"])
                print(f"  🏦 {info['institution_name']}: {acct_names}")
            print(f"\n📋 Send this to Allie via Telegram:\n")
            print(f"export PLAID_ACCESS_TOKENS='{tokens_json}'")
            print("\n" + "=" * 60)

            self._respond(200, {"status": "done", "tokens": tokens})
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main():
    print()
    print("🏦 Plaid Budget Sentinel — Bank Connection")
    print("=" * 50)
    print(f"  Environment: {PLAID_ENV}")
    print(f"  Client ID:   {PLAID_CLIENT_ID[:8]}...")
    print(f"  Server:      http://localhost:{PORT}")
    print("=" * 50)
    print()
    print("👉 Open this URL in your browser:")
    print(f"   http://localhost:{PORT}")
    print()
    print("Connect each bank, then click 'Done — Generate Config'.")
    print("Press Ctrl+C to stop the server.\n")

    server = http.server.HTTPServer(("127.0.0.1", PORT), PlaidLinkHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nServer stopped.")
        if connected:
            tokens = {k: v["access_token"] for k, v in connected.items()}
            print(f"\n📋 PLAID_ACCESS_TOKENS='{json.dumps(tokens)}'")
        server.server_close()


if __name__ == "__main__":
    main()
