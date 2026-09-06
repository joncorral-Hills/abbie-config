---
name: osint-recon
description: >
  OSINT and digital security operations — people search, email/phone reverse lookup,
  business registry search, family digital footprint monitoring, data broker scanning,
  breach detection, and removal request generation. Use when the user mentions 'find someone',
  'look up', 'who is', 'reverse lookup', 'data brokers', 'digital footprint', 'remove my data',
  'privacy', 'breach check', 'background check', 'find email', 'find phone number',
  'business lookup', or any people/business research topic.
requires:
  env: [NOTION_API_KEY]
---

# OSINT Recon Skill

Provides open-source intelligence and digital security operations for the Corral household.
Finds people, businesses, and contact information. Monitors the family's digital footprint
and helps remove personal data from data broker databases.

## 1. People Search

### Methods (Public Sources Only)
All searches use publicly available data. No paid OSINT services without Jon's approval.

#### Name Search
1. Web search: `"First Last" site:linkedin.com` → professional profile
2. Web search: `"First Last" [city] [state]` → local records
3. Public records: County property records, voter rolls (state-specific)
4. Social media: LinkedIn, Facebook, Twitter/X, Instagram (public profiles only)
5. Professional: Company websites, conference speakers, published papers

#### Email Discovery
1. Pattern testing: `first.last@domain.com`, `flast@domain.com`, `firstl@domain.com`
2. Web search: `"@domain.com" "First Last"` → published email addresses
3. Hunter.io pattern: If domain is known, check common corporate patterns
4. WHOIS: Domain registration records (for business owners)
5. GitHub/GitLab: Developer email from commit history (public repos)

#### Phone Reverse Lookup
1. Web search: `"(XXX) XXX-XXXX"` → published listings
2. Carrier lookup: Identify carrier (landline vs mobile)
3. Business directories: Yellow Pages, BBB, Google Business

#### Business Lookup
1. State Secretary of State: Business entity search (name, registered agent, status)
2. BBB: Rating, complaints, accreditation
3. Google Business: Location, hours, reviews
4. LinkedIn: Company page, employees, size
5. WHOIS: Domain registration details

### Output Format
For every search, return a structured summary:
```
## Search Results: [Query]
**Type**: Person / Business / Email / Phone
**Sources Checked**: [list]
**Confidence**: High / Medium / Low

### Findings
- [Finding 1 with source]
- [Finding 2 with source]

### Cross-References
- [Any connections between findings]

### Logged to Notion: ✅ Search ID: [ID]
```

## 2. Digital Footprint Monitoring

Track where family members' personal data appears online.

### Notion: Digital Footprint
| Property | Type | Description |
|----------|------|-------------|
| Family Member | Title | Name of the person being monitored |
| Site/Service | Text | Where data was found (e.g. "Spokeo", "WhitePages") |
| Data Type | Multi-Select | `Name`, `Address`, `Phone`, `Email`, `Age`, `Relatives`, `Property Records`, `Social Media`, `Photos` |
| Data Exposed | Text | Specific data visible |
| Risk Level | Select | `Critical`, `High`, `Medium`, `Low` |
| Removal Status | Select | `Not Started`, `Submitted`, `Pending`, `Confirmed Removed`, `Re-appeared`, `Cannot Remove` |
| Removal Method | Select | `Online Form`, `Email Request`, `Phone Call`, `Legal/DMCA`, `N/A` |
| Opt-Out URL | URL | Direct link to the removal/opt-out page |
| Date Discovered | Date | When this exposure was found |
| Date Submitted | Date | When removal was requested |
| Date Confirmed | Date | When removal was verified |
| Last Checked | Date | Most recent verification |
| Notes | Text | Special instructions, confirmation numbers |

### Family Members to Monitor
- Jon Corral
- Jaime Corral
- Children (names stored in Notion only, never in skill files)

## 3. Data Broker Database

Known data brokers and their removal processes.

### Notion: Data Brokers
| Property | Type | Description |
|----------|------|-------------|
| Broker Name | Title | e.g. "Spokeo", "BeenVerified" |
| Website | URL | Main site |
| Opt-Out URL | URL | Direct removal page |
| Removal Method | Select | `Online Form`, `Email`, `Phone`, `Mail`, `Account Required` |
| Difficulty | Select | `Easy`, `Medium`, `Hard`, `Very Hard` |
| Verification | Select | `None`, `Email`, `Phone`, `ID Required` |
| Re-list Period | Text | How often they re-add data (e.g. "30-60 days", "Never") |
| Auto-Remove Available | Checkbox | Whether automated removal is possible |
| Status | Select | `Active`, `Submitted`, `Confirmed`, `Blocked` |
| Last Submitted | Date | Most recent removal request |
| Next Check | Date | When to verify removal |
| Notes | Text | Process quirks, workarounds |

### Priority Data Brokers (Seed List)
| Broker | Opt-Out Method | Difficulty |
|--------|---------------|------------|
| Spokeo | spokeo.com/optout | Easy — email verification |
| BeenVerified | beenverified.com/faq/opt-out | Medium — account required |
| WhitePages | whitepages.com/suppression-requests | Easy — phone verification |
| Radaris | radaris.com/control/privacy | Medium — account required |
| Intelius | intelius.com/opt-out | Medium — email + identity |
| PeopleFinder | peoplefinder.com/optout | Easy — online form |
| TruePeopleSearch | truepeoplesearch.com/removal | Easy — online form |
| FastPeopleSearch | fastpeoplesearch.com/removal | Easy — online form |
| ThatsThem | thatsthem.com/optout | Easy — online form |
| Nuwber | nuwber.com/removal | Medium — email required |
| US Search | ussearch.com/opt-out | Medium |
| Pipl | No free opt-out | Hard — commercial only |
| Clearbit | Varies | Medium |
| ZoomInfo | zoominfo.com/about-zoominfo/privacy-center | Medium — form + verification |

## 4. Breach Monitoring

### HaveIBeenPwned Check
```bash
# Check if an email has been in known breaches
curl -s -H "hibp-api-key: $HIBP_API_KEY" \
  "https://haveibeenpwned.com/api/v3/breachedaccount/EMAIL_ADDRESS"
```

If no API key, use the web interface at haveibeenpwned.com and report results.

### Breach Alert Workflow
1. Check family email addresses against known breach databases
2. If breach found: log to Notion, alert Jon via Telegram with:
   - Service breached
   - Data types exposed
   - Date of breach
   - Recommended actions (change password, enable 2FA, monitor accounts)

## 5. Search Logging

### Notion: Searches
| Property | Type | Description |
|----------|------|-------------|
| Query | Title | What was searched for |
| Type | Select | `Person`, `Business`, `Email`, `Phone`, `Domain`, `Breach Check` |
| Requested By | Select | `Jon`, `invent-bot`, `home-bot`, `other` |
| Results Summary | Text | Brief findings |
| Sources Used | Multi-Select | `Web Search`, `LinkedIn`, `Public Records`, `WHOIS`, `Social Media`, `Breach DB` |
| Confidence | Select | `High`, `Medium`, `Low`, `No Results` |
| Date | Date | When search was conducted |
| Linked Footprint | Relation | Link to Digital Footprint entries if personal data found |

## 6. Security Rules

> **CRITICAL**: All operations follow strict privacy and ethical guidelines.

1. **All searches are logged** to the Searches Notion DB — no untracked lookups
2. **Family data is PII** — never send raw personal details to external APIs without Jon's approval
3. **No paid OSINT services** without explicit approval (no Pipl, no Palantir, no Lexis)
4. **Public sources only** — web search, public records, WHOIS, social media, breach databases
5. **Removal requests only for family** — never submit opt-outs on behalf of non-family
6. **Report findings clearly**: what data is exposed, where, severity, how to remove
7. **Never store passwords** — only note which services may be compromised

## 7. Cross-Bot Communication
- Respond to **Invent Bot** requests: `"Find potential licensees for [product] in [industry]"`
  - Search for companies in the target industry
  - Find decision-maker contacts (VP of Product, Licensing Director, etc.)
  - Return structured list: company, contact, email, role, source
- Available to **any bot** that needs contact/business research

## 8. Notion DB Setup

On first activation:
1. Create "OSINT" page under Allie's workspace
2. Create 3 child databases: Digital Footprint, Data Brokers, Searches
3. Seed Data Brokers with the priority list above
4. Store page ID and DB IDs in `resources/notion_ids.json`

## 9. Routing

| Request Pattern | Action |
|----------------|--------|
| "Find [person name]" | People search across public sources |
| "Look up [email/phone]" | Reverse lookup |
| "Find [company]" | Business lookup |
| "Check my digital footprint" | Scan data brokers for family data |
| "Remove my data from [broker]" | Generate opt-out request |
| "Check for breaches" | Run email through breach databases |
| "Who owns [domain]?" | WHOIS lookup |
| "Find licensees for [product]" | Industry + contact search (invent-bot) |
| "Add a data broker" | Create Data Brokers entry |
| "Status of removal requests" | Query Digital Footprint DB filtered by Removal Status |
