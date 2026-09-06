---
name: patent-prior-art-scout
description: >
  Novelty assessment and patent prior art research system. Searches patent
  databases, academic literature, and product listings to assess invention
  novelty and freedom-to-operate risks.
requires:
  bins: [python3]
---

# Patent Prior Art Scout

## Overview

Before filing a patent or investing in an invention, know what's already out
there. This skill performs systematic prior art searches across patents,
products, and academic literature to assess:
1. **Novelty**: Is this idea genuinely new?
2. **Non-obviousness**: Would this be obvious to someone skilled in the field?
3. **Freedom to Operate**: Can you practice this invention without infringing?

## Search Sources

| Source | URL | Best For |
|--------|-----|----------|
| **Google Patents** | patents.google.com | Quick broad search, full-text |
| **USPTO Patent Full-Text** | patft.uspto.gov | Official US patents |
| **USPTO Patent Public Search** | ppubs.uspto.gov | Advanced Boolean search |
| **Espacenet** | worldwide.espacenet.com | International patents |
| **WIPO/PCT** | wipo.int/patentscope | PCT applications |
| **Google Scholar** | scholar.google.com | Academic prior art |
| **arXiv** | arxiv.org | Preprints, technical papers |
| **Amazon/Product Hunt** | amazon.com, producthunt.com | Product prior art |
| **Crunchbase** | crunchbase.com | Startup/competitor landscape |

## Search Strategy

### 1. Concept Decomposition
Break the invention into its core concepts. For each concept, generate:
- **Technical terms**: Domain-specific vocabulary
- **Synonyms**: Alternative ways experts describe the same thing
- **Broader categories**: The general class this belongs to
- **Narrower specifics**: Particular implementations

Example: "Smart collar that tracks pet hydration"
- Concepts: wearable sensor, hydration monitoring, pet tracking, NFC/Bluetooth, microfluidics
- Synonyms: moisture detection, fluid intake, animal collar, IoT pet device

### 2. Query Construction
Build targeted queries for each database:

**Google Patents:**
```
(wearable OR collar OR harness) AND (pet OR dog OR cat OR animal) AND (hydration OR moisture OR fluid) AND (sensor OR monitor OR track)
```

**Google Scholar:**
```
"animal hydration monitoring" OR "pet water intake sensor" OR "wearable hydration"
```

**Product search:**
```
smart pet collar hydration monitoring
dog water intake tracker collar
```

### 3. Systematic Search
For each source:
1. Run broad query → collect top 20-50 results
2. Screen titles/abstracts → flag relevant items
3. Read full text of flagged items
4. Extract: publication date, claims/features, similarity level
5. Record in search log

### 4. Relevance Scoring
Grade each prior art reference:

| Score | Meaning | Action |
|-------|---------|--------|
| **A** (Exact match) | Same invention, different expression | High risk — likely unpatentable |
| **B** (Teaching suggestion) | Prior art teaches each element separately | Medium risk — obviousness challenge likely |
| **C** (Partial overlap) | Overlaps some elements but not all | Low-moderate risk — differentiate remaining elements |
| **D** (Distant cousin) | Same problem space, different solution | Low risk — good differentiator exists |
| **E** (Novel) | Nothing similar found | Proceed with confidence |

## Analysis Report

### Novelty Opinion
| Factor | Assessment |
|--------|------------|
| Prior art count | X patents, Y products, Z papers found |
| Closest prior art | [Title + date] |
| Novel elements | [What's genuinely new] |
| Risk level | High / Medium / Low |
| Recommendation | Proceed / Redesign / Abandon |

### Freedom-to-Operate (FTO) Notes
- Patents that could block implementation
- Claim-by-claim overlap analysis
- Design-around suggestions
- Licensing considerations

### Improvement Suggestions
Based on what the prior art landscape reveals:
- Gaps in existing solutions
- Unexpected combinations that strengthen novelty
- Technical improvements from related fields
- Market positioning angles

## Important Disclaimers

> ⚠️ **Disclaimer**: This is a preliminary prior art search using publicly
> available databases. It does not constitute a formal patentability opinion.
> A qualified patent attorney should conduct a professional search before
> filing. Unpublished patent applications, provisional filings, and trade
> secrets may exist that are not discoverable through public search.

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — search strategy, scoring, reporting |
| `resources/search_template.md` | Structured search log template |
| `resources/database_guides.json` | Query syntax and tips per database |
