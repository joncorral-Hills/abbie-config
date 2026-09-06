#!/usr/bin/env python3
"""
PDF Statement Parser for Chase and US Bank statements.

Usage:
    python parse_statement.py <pdf_path> <bank_type>

Bank types:
    chase_credit    - Chase Flex / Chase credit card statements
    chase_sapphire  - Chase Sapphire Reserve credit card statements
    chase_checking  - Chase checking account statements
    usbank          - US Bank checking/savings statements

Output:
    JSON array of transactions to stdout.
    Each transaction: {date, description, amount, type, raw_text, fingerprint}
"""

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import pdfplumber
except ImportError:
    print("Error: pdfplumber not installed. Run: pip install pdfplumber", file=sys.stderr)
    sys.exit(1)


def clean_amount(amount_str: str) -> Optional[float]:
    """Parse a dollar amount string into a float."""
    if not amount_str or amount_str.strip() in ("", "-", "--", "N/A"):
        return None
    cleaned = re.sub(r"[,$\s]", "", amount_str.strip())
    # Handle parentheses as negative: (123.45) -> -123.45
    paren_match = re.match(r"^\((.+)\)$", cleaned)
    if paren_match:
        cleaned = "-" + paren_match.group(1)
    try:
        return float(cleaned)
    except ValueError:
        return None


def normalize_description(desc: str) -> str:
    """Clean up merchant descriptions for consistent matching."""
    if not desc:
        return ""
    # Remove extra whitespace
    desc = " ".join(desc.split())
    # Remove trailing reference numbers (common in bank statements)
    desc = re.sub(r"\s+#?\d{4,}$", "", desc)
    # Remove dates embedded in descriptions
    desc = re.sub(r"\s+\d{2}/\d{2}\s*$", "", desc)
    return desc.strip()


def classify_transaction_type(description: str, amount: float) -> str:
    """Classify transaction type based on description and amount."""
    desc_upper = description.upper()

    # Transfers
    transfer_keywords = ["TRANSFER", "XFER", "TFR", "ZELLE", "VENMO CASHOUT"]
    if any(kw in desc_upper for kw in transfer_keywords):
        return "transfer"

    # Payments / credits
    if amount > 0:
        if any(kw in desc_upper for kw in ["PAYMENT", "CREDIT", "REFUND", "RETURN", "REVERSAL"]):
            return "credit"
        if any(kw in desc_upper for kw in ["DEPOSIT", "PAYROLL", "DIRECT DEP", "ACH CREDIT"]):
            return "income"
        return "credit"

    # Recurring / autopay
    if any(kw in desc_upper for kw in ["AUTOPAY", "AUTO PAY", "RECURRING", "SUBSCRIPTION"]):
        return "recurring"

    # ATM
    if "ATM" in desc_upper:
        return "atm"

    # Check
    if re.match(r"^CHECK\s+#?\d+", desc_upper):
        return "check"

    return "purchase"


def make_fingerprint(date: str, amount: float, description: str) -> str:
    """Create a unique fingerprint for duplicate detection."""
    raw = f"{date}|{amount:.2f}|{description.upper().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def deduplicate(transactions: list[dict]) -> list[dict]:
    """Remove duplicate transactions based on fingerprint."""
    seen = set()
    unique = []
    for tx in transactions:
        fp = tx.get("fingerprint", make_fingerprint(
            tx["date"], tx.get("amount", 0), tx["description"]
        ))
        if fp not in seen:
            seen.add(fp)
            unique.append(tx)
    dupes_removed = len(transactions) - len(unique)
    if dupes_removed > 0:
        import sys
        print(f"Removed {dupes_removed} duplicate transactions", file=sys.stderr)
    return unique


def parse_chase_credit(pdf_path: str) -> list[dict]:
    """
    Parse Chase credit card (Flex) PDF statement.

    Chase credit card statements have transactions listed in sections
    (Purchases, Payments, etc.) with columns:
    Date, Description, Amount (or Date, Post Date, Description, Amount)
    """
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text += text + "\n"

        # Parse transaction lines
        # Chase credit card format: MM/DD  description  amount
        # or: MM/DD  MM/DD  description  amount
        lines = full_text.split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Match: date [post_date] description amount
            # Pattern: MM/DD [MM/DD] ... -?$X,XXX.XX
            match = re.match(
                r"^(\d{2}/\d{2})\s+"           # Transaction date
                r"(?:(\d{2}/\d{2})\s+)?"        # Optional post date
                r"(.+?)\s+"                      # Description (non-greedy)
                r"(-?\$?[\d,]+\.\d{2})$",        # Amount
                line,
            )

            if match:
                date_str = match.group(1)
                description = normalize_description(match.group(3))
                amount = clean_amount(match.group(4))

                if amount is None:
                    continue

                # Chase credit: negative = charge, positive = payment/credit
                # Normalize: purchases should be positive spending amounts
                spending_amount = abs(amount)
                tx_type = classify_transaction_type(description, amount)

                final_amount = spending_amount if amount < 0 else -spending_amount
                transactions.append({
                    "date": date_str,
                    "description": description,
                    "amount": final_amount,
                    "type": tx_type,
                    "raw_text": line,
                    "fingerprint": make_fingerprint(date_str, final_amount, description),
                })

    return deduplicate(transactions)


def parse_chase_checking(pdf_path: str) -> list[dict]:
    """
    Parse Chase checking account PDF statement.

    Format: Details | Posting Date | Description | Amount | Type | Balance
    Types: DEBIT, CHECK, DSLIP, ACH_CREDIT, ACH_DEBIT, ATM, FEE
    """
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            # Try table extraction first
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    # Skip header rows
                    if any(
                        h in str(row[0]).upper()
                        for h in ["DATE", "POSTING", "DETAILS", "DESCRIPTION"]
                    ):
                        continue

                    # Try to find date, description, and amount in the row
                    date_str = None
                    description = None
                    amount = None

                    for cell in row:
                        cell_str = str(cell or "").strip()
                        if not cell_str:
                            continue
                        # Date detection
                        if re.match(r"^\d{2}/\d{2}(/\d{2,4})?$", cell_str) and not date_str:
                            date_str = cell_str
                        # Amount detection
                        elif re.match(r"^-?\$?[\d,]+\.\d{2}$", cell_str):
                            amount = clean_amount(cell_str)
                        # Description (longest non-date, non-amount cell)
                        elif len(cell_str) > 3 and not re.match(r"^[\d.$,-]+$", cell_str):
                            if description is None or len(cell_str) > len(description):
                                description = cell_str

                    if date_str and description and amount is not None:
                        transactions.append({
                            "date": date_str,
                            "description": normalize_description(description),
                            "amount": amount,
                            "type": classify_transaction_type(description, amount),
                            "raw_text": " | ".join(str(c or "") for c in row),
                        })

            # Fallback: line-by-line text parsing if no tables found
            if not tables:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    match = re.match(
                        r"^(\d{2}/\d{2}(?:/\d{2,4})?)\s+"
                        r"(.+?)\s+"
                        r"(-?\$?[\d,]+\.\d{2})\s*",
                        line.strip(),
                    )
                    if match:
                        transactions.append({
                            "date": match.group(1),
                            "description": normalize_description(match.group(2)),
                            "amount": clean_amount(match.group(3)),
                            "type": classify_transaction_type(
                                match.group(2), clean_amount(match.group(3)) or 0
                            ),
                            "raw_text": line.strip(),
                        })

    return transactions


def parse_usbank(pdf_path: str) -> list[dict]:
    """
    Parse US Bank checking/savings PDF statement.

    Format: Date | Description | Credit | Debit | Balance
    Credit and Debit are in separate columns.
    """
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    if any(
                        h in str(row[0]).upper()
                        for h in ["DATE", "POSTING", "TRANSACTION"]
                    ):
                        continue

                    date_str = None
                    description = None
                    credit = None
                    debit = None

                    for i, cell in enumerate(row):
                        cell_str = str(cell or "").strip()
                        if not cell_str:
                            continue
                        if re.match(r"^\d{2}/\d{2}(/\d{2,4})?$", cell_str) and not date_str:
                            date_str = cell_str
                        elif re.match(r"^-?\$?[\d,]+\.\d{2}$", cell_str):
                            val = clean_amount(cell_str)
                            if val is not None:
                                # US Bank: typically credit column before debit,
                                # or debit before credit. Try positional.
                                if credit is None and val > 0:
                                    credit = val
                                elif debit is None:
                                    debit = abs(val)
                        elif len(cell_str) > 3 and not re.match(r"^[\d.$,-]+$", cell_str):
                            if description is None or len(cell_str) > len(description):
                                description = cell_str

                    if date_str and description:
                        if credit:
                            amount = credit  # Positive = deposit/credit
                        elif debit:
                            amount = -debit  # Negative = withdrawal/purchase
                        else:
                            continue

                        transactions.append({
                            "date": date_str,
                            "description": normalize_description(description),
                            "amount": amount,
                            "type": classify_transaction_type(description, amount),
                            "raw_text": " | ".join(str(c or "") for c in row),
                        })

            # Fallback text parsing
            if not tables:
                text = page.extract_text() or ""
                for line in text.split("\n"):
                    match = re.match(
                        r"^(\d{2}/\d{2}(?:/\d{2,4})?)\s+"
                        r"(.+?)\s+"
                        r"(-?\$?[\d,]+\.\d{2})\s*",
                        line.strip(),
                    )
                    if match:
                        transactions.append({
                            "date": match.group(1),
                            "description": normalize_description(match.group(2)),
                            "amount": clean_amount(match.group(3)),
                            "type": classify_transaction_type(
                                match.group(2), clean_amount(match.group(3)) or 0
                            ),
                            "raw_text": line.strip(),
                        })

    return transactions


PARSERS = {
    "chase_credit": parse_chase_credit,
    "chase_sapphire": parse_chase_credit,
    "chase_checking": parse_chase_checking,
    "usbank": parse_usbank,
}


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <pdf_path> <bank_type>", file=sys.stderr)
        print(f"Bank types: {', '.join(PARSERS.keys())}", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    bank_type = sys.argv[2].lower()

    if not Path(pdf_path).exists():
        print(f"Error: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    if bank_type not in PARSERS:
        print(f"Error: Unknown bank type: {bank_type}", file=sys.stderr)
        print(f"Valid types: {', '.join(PARSERS.keys())}", file=sys.stderr)
        sys.exit(1)

    parser = PARSERS[bank_type]
    transactions = parser(pdf_path)

    # Summary to stderr
    total_purchases = sum(t["amount"] for t in transactions if t["amount"] < 0)
    total_credits = sum(t["amount"] for t in transactions if t["amount"] > 0)
    print(f"Parsed {len(transactions)} transactions", file=sys.stderr)
    print(f"Total purchases: ${abs(total_purchases):,.2f}", file=sys.stderr)
    print(f"Total credits: ${total_credits:,.2f}", file=sys.stderr)

    # Transactions as JSON to stdout
    print(json.dumps(transactions, indent=2))


if __name__ == "__main__":
    main()
