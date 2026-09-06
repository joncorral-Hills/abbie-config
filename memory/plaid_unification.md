# Plaid → Financial-Automation Unification
- Date: 2026-08-04
- Plaid now writes to the financial-automation Transactions DB (36c63d55-66c5-8107-b787-fc7c20d5be04)
- Separate Plaid Transactions DB (39f6...) is no longer the primary sync target
- 500+ historical transactions re-synced with Source="Plaid Sync"
- Balances update to the Plaid Accounts DB (39f6...) — separate from financial-automation Accounts DB
- ACCOUNT_MAP labels updated to match financial-automation account names
- Fixes applied: _load_merchant_map search path, write_transaction schema, _normalise_merchant ref
- Issue: Account relation not set on existing transactions (merchant→account mapping needs work)