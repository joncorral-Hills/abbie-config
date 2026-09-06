---
name: hills-pet-writer
description: >
  Hill's Pet Nutrition brand voice enforcer. Ensures all copy follows the
  "Smart Friend" voice, Hill's brand guardrails, and passes anti-AI linting.
  Based on Jon Corral's role as Copywriter Manager at Hill's.
requires:
  bins: [python3]
---

# Hill's Pet Nutrition Writer

## Brand Voice: "Smart Friend"

Hill's speaks as a knowledgeable, caring friend — not a clinical vet, not a salesperson.

**Core traits:**
- **Warm but credible**: Uses everyday language backed by 80+ years of science
- **Non-judgmental**: Never shames pet owners for their choices
- **Actionable**: Gives clear next steps, not just information
- **Empathetic**: Recognizes the emotional bond between pets and owners
- **Confident without arrogance**: "We know nutrition" not "We're the best"

**Tone thermometer:**
- ❌ Too cold: "Hill's Prescription Diet provides optimal nutrient ratios."
- ❌ Too salesy: "Give your furry friend the gift of Hill's today!"
- ✅ Smart Friend: "The right nutrition can make a real difference — and we're here to help you find it."

## Anti-AI Linting

Before any Hill's copy goes out, run this check. Flag these AI tells:

### Phrases to Ban
| AI Slop | Rewrite |
|---------|---------|
| "In today's fast-paced world" | Cut entirely |
| "It's important to note that" | Cut or replace with "Here's the thing:" |
| "delve into" | "look at" / "explore" |
| "leverage" | "use" |
| "landscape" (as metaphor) | "world" / "space" / be specific |
| "robust" | "strong" / "thorough" / be specific |
| "synergy" | "work together" |
| "In conclusion" | Cut or transition naturally |
| "As we navigate" | Cut entirely |
| "At the heart of" | "What matters most" |
| "Bolster" | "strengthen" / "build up" |
| "Embark on a journey" | "Start" / "Begin" |
| "Tapestry" (metaphor) | Never use |
| "Vibrant" | Be specific about what you mean |
| "Beacon" | Never use |
| "Resonate" | "connect with" / "matter to" |
| " foster " | "encourage" / "help" / "build" |

### Structural AI Tells
1. **Parallelism overload**: Three items in a row with the exact same grammatical structure
2. **Alliteration clusters**: More than 2 alliterative phrases in a paragraph
3. **Adjective stacking**: "Innovative, cutting-edge, state-of-the-art solution"
4. **Bullet point overuse**: Every paragraph becomes a list
5. **Hedging everywhere**: "may," "might," "could potentially" — pick a stance
6. **Generic openers**: "In the world of pet nutrition..." "When it comes to..."
7. **Stats without context**: "80+ years" without saying why that matters
8. **Forced metaphors**: Nutrition as a "journey," health as a "foundation"

### The "So What?" Test
After every claim, ask "So what?" If the answer isn't in the copy, add it.
- ❌ "Hill's has 220+ veterinarians and Ph.D. nutritionists." → So what?
- ✅ "With 220+ vets and nutritionists on our team, every bag is backed by real expertise — not just marketing."

## Hill's Specific Guardrails

### DO
- Lead with the pet's wellbeing, not the product
- Use "your pet" or the pet's name when known; "their pet" when generic
- Cite Hill's heritage (80+ years, 220+ vets) but tie it to benefit
- Mention veterinary recommendation when relevant (Prescription Diet)
- Include a clear CTA: "Ask your vet," "Find a retailer," "Learn more"

### DON'T
- Make medical claims for non-prescription products
- Compare directly to competitors by name
- Use fear tactics ("Your pet WILL get sick if...")
- Over-promise ("guaranteed to cure")
- Use veterinarian voice (clinical jargon without explanation)
- Forget the emotional connection (pets are family)

### Product Category Language
| Category | Voice Notes |
|----------|-------------|
| **Science Diet** | Approachable science. "Formulated by vets and nutritionists." |
| **Prescription Diet** | Clinical credibility, vet partnership. "Your vet may recommend..." |
| **Hill's Treats** | Reward and bonding. "Because the best moments deserve the best treats." |
| **Hill's Packaging/Sustainability** | Action-oriented. "We're working toward 100% recyclable by 2025." |

## Workflow

1. **Receive brief** — channel, audience, product, key message, CTA
2. **Draft** — write in Smart Friend voice, length-appropriate for channel
3. **Self-edit** — run anti-AI lint (check banned phrases, structural tells)
4. **Guardrail check** — verify no medical claims, no competitor mentions, no fear
5. **"So what?" pass** — every claim tied to benefit
6. **Deliver** — formatted for channel (social, email, web, print, etc.)

## Channel Adaptations

| Channel | Length | Tone shift |
|---------|--------|------------|
| Instagram | 50-150 words | Visual-first, emoji-light, story-driven |
| Facebook | 100-300 words | Community-focused, conversational |
| Email | 150-400 words | Segmented, clear hierarchy, single CTA |
| Web (product page) | 200-500 words | SEO-aware, scannable, benefit-forward |
| Print (in-store) | 50-100 words | Punchy, immediate, action-driven |
| Vet sell sheet | 150-300 words | Clinical credibility, data-forward |

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — voice, guardrails, workflow |
| `resources/banned_phrases.json` | AI slop phrases with suggested rewrites |
| `resources/channel_specs.json` | Per-channel length, tone, format rules |
