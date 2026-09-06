---
name: travel-planner
description: >
  Structured travel guide generation system. Builds multi-day itineraries
  from destination specs, preferences, budget, and constraints. Researches
  flights, hotels, activities, dining, and logistics — outputs formatted
  travel guides.
requires:
  bins: [python3]
  env: []
---

# Travel Planner

## Overview

Generate complete, structured travel guides from a set of inputs. Research
destination details, build day-by-day itineraries, and compile logistics
into a single reference document.

## Input Gathering

### Required
- Destination(s)
- Travel dates
- Number of travelers + ages (affects activities, hotels, dining)
- Budget tier (backpacker / mid-range / luxury / mix)

### Important Context
- Travel style: relaxed vs packed, guided vs self-directed
- Interests: history, nature, food, adventure, art, shopping, local culture
- Mobility constraints (stroller, accessibility)
- Dietary restrictions
- Language concerns
- Hotel preferences (chain vs boutique, amenities)
- Flight preferences (direct, airline, class)

## Guide Structure

### 1. Trip Overview
```
Destination: [City/Region, Country]
Dates: [Start] — [End] ([X] days)
Travelers: [Count], ages [ages]
Budget: [Tier] (~$X per day, excluding flights)
Currency: [Local] / [Exchange rate]
Language: [Primary] + [English coverage]
Weather: [Expected conditions during visit]
```

### 2. Logistics Summary
| Item | Details | Cost |
|------|---------|------|
| **Flights** | Airlines, times, layovers | $X |
| **Arrival transfer** | Airport → hotel | $X |
| **Accommodation** | Hotel name, address, room type | $X/night |
| **Departure transfer** | Hotel → airport | $X |
| **Local transport** | Rail pass, subway, rental car | $X |
| **Travel insurance** | Provider, coverage | $X |
| **Phone/internet** | eSIM, local SIM, roaming | $X |
| **TOTAL ESTIMATED** | | ~$X |

### 3. Daily Itinerary
For each day:

```
## Day X — [Theme/Focus]
**Weather:** [Forecast]
**Dress:** [Recommendation]

| Time | Activity | Location | Notes | Cost |
|------|----------|----------|-------|------|
| 08:00 | Breakfast | [Restaurant] | [Reservation? Cuisine?] | $X |
| 10:00 | [Activity] | [Venue/Area] | [Tickets? Duration? Tips?] | $X |
| 12:30 | Lunch | [Restaurant] | [Note] | $X |
| 14:00 | [Activity] | [Venue/Area] | [Note] | $X |
| 17:00 | [Activity] | [Venue/Area] | [Note] | $X |
| 19:30 | Dinner | [Restaurant] | [Reservation required] | $X |
| Evening | [Optional] | [Venue/Area] | [Note] | $X |
```

**Day-specific tips:**
- [Practical note about logistics, bookings, etc.]
- [Backup plan if weather/p closure]

### 4. Restaurant Shortlist
| Name | Cuisine | Price | Why | Priority |
|------|---------|-------|-----|----------|
| [Name] | [Type] | $$$ | [One-line reason] | Must-try / Backup |

### 5. Activity Shortlist
| Name | Type | Duration | Cost | Book Ahead? | Priority |
|------|------|----------|------|-------------|----------|
| [Name] | [Type] | [Hours] | $X | Yes/No | Must-do / Flexible |

### 6. Practical Information
- **Emergency numbers:** [Local 911 equivalent]
- **Embassy/consulate:** [Address, phone]
- **Pharmacy:** [Nearest to hotel, 24hr?]
- **Grocery/supermarket:** [For snacks, water, supplies]
- **Laundry:** [Hotel or nearby]
- **Tipping customs:** [% expectation by service]
- **Cultural notes:** [Dress codes, etiquette, scams to avoid]
- **Power:** [Plug type, voltage]
- **Apps to download:** [Transit, maps, translation, food booking]

### 7. Packing List
- **Documents:** Passport, visas, confirmations, insurance
- **Clothing:** [Weather-appropriate layers, formal if needed]
- **Tech:** Adapters, chargers, power bank, eSIM
- **Health:** Meds, first aid, sunscreen
- **Misc:** [Destination-specific items]

## Research Process

1. **Flights**: Check Google Flights, Skyscanner, airline sites for best routes/times
2. **Hotels**: Check Booking.com, Airbnb, hotel sites — read recent reviews
3. **Activities**: Check official tourism sites, TripAdvisor, Atlas Obscura, local blogs
4. **Dining**: Check Michelin, local food blogs, Google Maps reviews
5. **Transport**: Check local transit apps, rail passes, airport transfer options
6. **Entry requirements**: Check official consulate/embassy site for visas, vaccinations
7. **Currency**: Check current exchange rate, cash vs card acceptance
8. **Weather**: Check historical averages for travel dates

## Booking Checklist
- [ ] Flights booked
- [ ] Hotel booked + confirmation saved
- [ ] Travel insurance purchased
- [ ] Passport valid 6+ months past return
- [ ] Visa applied for (if needed)
- [ ] Key activity tickets purchased
- [ ] Restaurant reservations made
- [ ] Phone/internet sorted (eSIM/downloaded)
- [ ] Airport transfer booked
- [ ] Notify bank of travel
- [ ] Confirm checkout time with hotel

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — guide structure, research, checklist |
| `templates/guide_template.md` | Blank travel guide template |
| `resources/booking_checklist.json` | Per-trip-type booking checklist |
