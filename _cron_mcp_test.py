#!/usr/bin/env python3
"""Get Robinhood portfolio state via MCP tools using the Hermes MCP client."""
import json, subprocess, sys

# Try using Hermes MCP client to call tools
result = subprocess.run(
    ["hermes", "mcp", "tools"],
    capture_output=True, text=True, timeout=30
)
print("=== MCP TOOLS LIST ===")
print(result.stdout[:2000])
print("=== STDERR ===", result.stderr[:500] if result.stderr else "(none)")

# Try calling the tool
result2 = subprocess.run(
    ["hermes", "mcp", "call", "get_portfolio", '{"account_number":"959217308"}'],
    capture_output=True, text=True, timeout=30
)
print("=== GET_PORTFOLIO ===")
print(result2.stdout[:3000])
print("=== STDERR ===", result2.stderr[:500] if result2.stderr else "(none)")

# Also try get_equity_positions
result3 = subprocess.run(
    ["hermes", "mcp", "call", "get_equity_positions", '{"account_number":"959217308"}'],
    capture_output=True, text=True, timeout=30
)
print("=== GET_POSITIONS ===")
print(result3.stdout[:3000])
print("=== STDERR ===", result3.stderr[:500] if result3.stderr else "(none)")