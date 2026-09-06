---
name: billing-dispute-ai
description: >
  Evidence-backed institutional bill dispute system. Gathers bill details,
  identifies relevant regulations, compiles evidence, and generates formal
  dispute letters for medical bills, utility overcharges, erroneous fees,
  and subscription disputes.
requires:
  bins: [python3]
---

# Billing Dispute AI

## Overview

Turn a messy bill into a bulletproof dispute. This skill handles the
full pipeline:
1. **Parse** the bill for errors, overcharges, and potential violations
2. **Research** relevant laws, regulations, and company policies
3. **Gather** evidence (receipts, prior bills, competitor rates, regulations)
4. **Generate** a formal dispute letter with cited evidence
5. **Track** outcomes and follow-ups

## Supported Dispute Types

| Type | Key Laws/Regs | What to Look For |
|------|---------------|------------------|
| **Medical bills** | No Surprises Act, Fair Debt Collection Practices Act | Upcoding, out-of-network charges without consent, duplicate billing |
| **Credit cards** | Fair Credit Billing Act (FCBA) | Unauthorized charges, billing errors, disputed amounts > $50 |
| **Utilities** | State PUC regulations | Rate errors, estimated vs actual usage, erroneous fees |
| **Subscriptions** | FTC Click-to-Cancel rule, state auto-renewal laws | Difficult cancellation, post-cancellation charges, undisclosed auto-renewal |
| **Telecom/cell** | FCC rules, Truth-in-Billing | Cramming, slamming, undisclosed fees |
| **HOA/landlord** | State landlord-tenant law, lease terms | Unlawful fees, security deposit withholding, repair charges |

## Dispute Pipeline

### Step 1: Intake
Collect from user:
- Bill type and provider name
- Bill amount and date
- What specifically is disputed (line items)
- Any prior communication with provider
- Relevant account numbers or confirmation IDs

### Step 2: Error Detection
Scan for common errors:
- Duplicate charges
- Services not received
- Incorrect rates (check against published rates)
- Math errors (subtotal + tax + fees)
- Upcoding (medical: service billed at higher level than provided)
- Out-of-network charges without proper notice
- Missing insurance adjustments
- Proration errors

### Step 3: Legal/Regulatory Research
Search for:
- Applicable federal law (FCBA, No Surprises Act, FTC rules)
- State-specific regulations (auto-renewal, utility, medical billing)
- Company-specific policies (published on provider website)
- Complaint patterns (search: "[provider] billing dispute fraud")

### Step 4: Evidence Compilation
Build evidence packet:
- The bill itself (annotated with disputed items highlighted)
- Prior bills for comparison (if rate changed)
- Relevant law/regulation excerpts
- Screenshots of published policies/rates
- Any prior correspondence
- Timeline of events

### Step 5: Letter Generation
Generate a formal dispute letter with:
1. **Header**: Your info, provider info, date, account #
2. **Subject line**: Clear dispute summary
3. **Opening**: State the dispute calmly and factually
4. **Facts**: Chronological account with dates and amounts
5. **Legal basis**: Cite specific laws/regulations that support your position
6. **Evidence**: Reference attached documents by number
7. **Demand**: Specific resolution (refund amount, credit, correction)
8. **Deadline**: Reasonable timeframe (typically 30 days)
9. **Closing**: Professional but firm
10. **Enclosures**: List of attached evidence

### Step 6: Delivery & Tracking
- Send via certified mail + email for maximum evidence
- Log delivery confirmation
- Calendar follow-up date (30 days)
- If no response → escalate (state AG, CFPB, FCC, BBB)

## Letter Templates

### Medical Bill Dispute — No Surprises Act
```
Dear [Billing Department],

I am writing to dispute charges on my account [ACCT#] dated [DATE] in the amount of $[AMOUNT].

Specifically, I dispute the following charges:
- [Line item]: $[amount] — [reason: e.g., "billed as out-of-network despite receiving care at an in-network facility"]

Under the No Surprises Act (42 U.S.C. § 300gg-111), patients who receive emergency services or scheduled services at in-network facilities cannot be billed at out-of-network rates for ancillary services without advance notice and consent.

[Provide timeline of care, any notice received or not received, and why the charge violates the Act.]

I am requesting:
1. Re-billing at the in-network rate
2. An updated explanation of benefits
3. A refund of $[amount overcharged] within 30 days

Attached: [List enclosures]

Sincerely,
[Name]
```

### Credit Card Billing Error — FCBA
```
Dear [Card Issuer],

I am writing to dispute a billing error under the Fair Credit Billing Act (15 U.S.C. § 1666). My account number is [ACCT#].

Transaction details:
- Date: [DATE]
- Amount: $[AMOUNT]
- Merchant: [NAME]
- Description: [What was supposed to be purchased]

Reason for dispute: [e.g., "Item not received," "Unauthorized charge," "Charged incorrect amount"]

Under the FCBA, I am not required to pay the disputed amount while you investigate, and you must acknowledge this dispute within 30 days and resolve it within 90 days.

I request:
1. Investigation of this charge
2. Temporary credit of $[amount] pending resolution
3. Written confirmation of dispute receipt

Attached: [receipt, correspondence, tracking info, etc.]

Sincerely,
[Name]
```

## Escalation Paths

| Stage | Action | Timeline |
|-------|--------|----------|
| 1 | Formal dispute letter to provider | Day 0 |
| 2 | Follow-up #1 if no response | Day 15 |
| 3 | Follow-up #2 + regulator complaint | Day 30 |
| 4 | Regulator/AG complaint | Day 45 |
| 5 | Small claims court (if <$10K) | Day 60+ |

### Regulators by Type
| Dispute Type | Primary Regulator | URL |
|--------------|-------------------|-----|
| Credit card | CFPB | consumerfinance.gov/complaint |
| Medical | State AG + CMS | cms.gov/nosurprises |
| Telecom | FCC | consumercomplaints.fcc.gov |
| Utilities | State PUC | varies by state |
| General | State AG + BBB | bbb.org |
| Debt collection | CFPB + State AG | consumerfinance.gov |

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — pipeline, templates, escalation |
| `resources/dispute_templates/` | Letter templates by dispute type |
| `resources/regulator_lookup.json` | Regulator URLs and contacts by state/type |
| `scripts/evidence_compiler.py` | Compile evidence into a single PDF packet |
