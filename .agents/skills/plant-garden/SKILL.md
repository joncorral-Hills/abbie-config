---
name: plant-garden
description: >
  Lawn care, indoor/outdoor plant tracking, fertilizer scheduling, product usage history,
  and seasonal garden guidance for Kansas City metro (USDA Zone 6a). Use when the user
  mentions lawn, grass, mowing, fertilizer, plants, watering, weeds, aeration, overseeding,
  garden, pest control on plants, 'when should I fertilize', 'what plants do I have',
  'lawn schedule', or any yard/garden topic.
requires:
  env: [NOTION_API_KEY]
---

# Plant & Garden Skill

Manages the Corral household's lawn care, indoor/outdoor plants, fertilizer scheduling, and
seasonal garden calendar. All guidance is calibrated for **Kansas City metro, USDA Zone 6a**.

## 1. Plant Inventory

Track all indoor and outdoor plants.

### Notion: Plants
| Property | Type | Description |
|----------|------|-------------|
| Plant Name | Title | Common name (e.g. "Snake Plant", "Tomatoes", "Front Yard Fescue") |
| Type | Select | `Indoor`, `Outdoor`, `Lawn`, `Vegetable`, `Herb`, `Tree`, `Shrub` |
| Location | Text | Where it lives (e.g. "Living Room", "Back Garden Bed", "Front Yard") |
| Sun Needs | Select | `Full Sun`, `Partial Sun`, `Shade`, `Indirect Light` |
| Water Schedule | Select | `Daily`, `Every 2-3 Days`, `Weekly`, `Bi-Weekly`, `As Needed` |
| Last Watered | Date | When last watered (manual tracking for indoor) |
| Last Fertilized | Date | Most recent fertilizer application |
| Fertilizer Used | Text | Product name and application rate |
| Health Status | Select | `Thriving`, `Good`, `Fair`, `Struggling`, `Dormant`, `Dead` |
| Notes | Text | Care tips, problems observed, seasonal behavior |
| Photo | Files | Current photo for health tracking |
| Date Added | Date | When the plant was acquired |

## 2. Product Tracking

Track fertilizers, pesticides, soil amendments, seeds, and other garden products.

### Notion: Garden Products
| Property | Type | Description |
|----------|------|-------------|
| Product Name | Title | e.g. "Scotts Turf Builder", "Milorganite", "Neem Oil" |
| Type | Select | `Fertilizer`, `Pre-Emergent`, `Post-Emergent`, `Pesticide`, `Fungicide`, `Soil Amendment`, `Seed`, `Mulch`, `Other` |
| Brand | Text | Manufacturer |
| NPK Ratio | Text | e.g. "32-0-4", "6-4-0" (for fertilizers) |
| Application Rate | Text | e.g. "3.5 lbs per 1,000 sq ft" |
| Coverage | Text | e.g. "5,000 sq ft per bag" |
| Last Applied | Date | Most recent application date |
| Next Application | Date | Scheduled next use |
| Quantity Remaining | Text | e.g. "1.5 bags", "half bottle" |
| Purchase Location | Text | Where bought |
| Price | Number | Cost per unit |
| Notes | Text | Application tips, results observed |

## 3. Lawn Zones

Track different lawn areas with their specific characteristics.

### Notion: Lawn Zones
| Property | Type | Description |
|----------|------|-------------|
| Zone Name | Title | e.g. "Front Yard", "Back Yard", "Side Strip" |
| Area (sq ft) | Number | Approximate square footage |
| Grass Type | Select | `Tall Fescue`, `Kentucky Bluegrass`, `Bermuda`, `Zoysia`, `Mixed`, `Other` |
| Sun Exposure | Select | `Full Sun`, `Partial Sun`, `Mostly Shade` |
| Irrigation | Select | `Sprinkler System`, `Manual`, `None` |
| Last Mowed | Date | Most recent mowing |
| Mowing Height | Text | e.g. "3.5 inches" |
| Last Aerated | Date | Core aeration date |
| Last Overseeded | Date | Overseeding date |
| Last Soil Test | Date | When soil was last tested |
| Soil pH | Number | From most recent test |
| Notes | Text | Problem areas, drainage issues, etc. |

## 4. Seasonal Calendar — Zone 6a Kansas City

### Spring (March – May)
| When | Task | Details |
|------|------|---------|
| Early Mar | Clean up | Remove debris, dead leaves, fallen branches |
| Mid Mar | Pre-emergent #1 | Apply when soil temp reaches 55°F (crabgrass prevention) |
| Late Mar | Soil test | Test pH and nutrient levels if not done in fall |
| Early Apr | Pre-emergent #2 | Split application if using lower rate |
| Mid Apr (after last frost ~Apr 15) | Start mowing | First mow at 3" height, raise to 3.5"+ |
| Late Apr | Spring fertilizer | Light nitrogen application (0.5-0.75 lb N/1000 sq ft) |
| May | Spot treat weeds | Post-emergent for broadleaf weeds |
| May | Plant annuals/vegetables | After last frost date |

### Summer (June – August)
| When | Task | Details |
|------|------|---------|
| Jun | Raise mowing height | 4"+ to shade soil and retain moisture |
| Jun-Aug | Water deeply | 1-1.5" per week, early morning, infrequent deep soaks |
| Jul | Grub prevention | Apply GrubEx or milky spore if grub history |
| Jul-Aug | Minimal fertilizer | Avoid heavy N in heat — iron-only apps OK |
| Aug | Prepare for fall | Order seed, schedule aeration |

### Fall (September – November)
| When | Task | Details |
|------|------|---------|
| Early Sep | **Core aerate** | Best time for Zone 6a cool-season grass |
| Early Sep | **Overseed** | Immediately after aeration, keep moist 2-3 weeks |
| Sep | Fall fertilizer #1 | 1 lb N/1000 sq ft — most important feeding of the year |
| Oct | Fall fertilizer #2 | Repeat application |
| Late Oct | Post-emergent cleanup | Last chance for broadleaf weed control |
| Nov | **Winterizer fertilizer** | Final application before dormancy |
| Nov | Winterize irrigation | Blow out sprinkler lines before first hard freeze (~Nov 15) |
| Nov | Leaf cleanup | Mulch-mow or remove — don't let leaves smother grass |

### Winter (December – February)
| When | Task | Details |
|------|------|---------|
| Dec-Feb | Indoor plant focus | Adjust watering for lower humidity, less frequent |
| Jan | Plan spring garden | Order seeds, plan vegetable beds |
| Feb | Sharpen mower blades | Prep equipment for spring |
| Late Feb | Soil test | If not done in fall |

## 5. Key Zone 6a Facts
- **Last frost**: ~April 15
- **First frost**: ~October 15
- **Growing season**: ~180 days
- **Best grass**: Tall Fescue (heat tolerant), Kentucky Bluegrass (self-spreading)
- **Aeration window**: Sep 1-30 (cool-season grasses)
- **Pre-emergent timing**: When soil temp at 4" depth reaches 55°F (typically mid-March)
- **Winterizer timing**: Before first hard freeze, after last mow

## 6. Cross-Bot Communication
- `message_agent(target="home-bot")` or `home-bot chat -q "..."` for:
  - Sprinkler system control via HA
  - Irrigation schedule changes
  - Outdoor lighting adjustments for garden areas
- Respond to Home Bot queries about yard work timing and context

## 7. Notion DB Setup

On first activation:
1. Create "Plant & Garden" page under Allie's workspace
2. Create 3 child databases: Plants, Garden Products, Lawn Zones
3. Seed seasonal calendar as a linked database view or separate reference
4. Store page ID and DB IDs in `resources/notion_ids.json`

## 8. Routing

| Request Pattern | Action |
|----------------|--------|
| "When should I fertilize?" | Check last application, consult seasonal calendar |
| "What plants do I have?" | Query Plants DB |
| "What fertilizer did I use on the lawn?" | Query Garden Products filtered by lawn use |
| "Time to aerate?" | Check last aeration date + current date vs Zone 6a window |
| "What's my lawn care schedule?" | Generate upcoming tasks from seasonal calendar |
| "My [plant] looks sick" | Check health records, suggest diagnosis |
| "Add [product]" | Create Garden Products entry |
| "Water the lawn" | Delegate to home-bot for sprinkler control |
