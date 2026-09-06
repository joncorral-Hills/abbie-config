---
name: home-hub
description: >
  Central hub for home operations — Home Assistant device control, 3D printer queue,
  network device inventory, product/paint registry, local service contacts, and home
  maintenance scheduling. Use when the user mentions smart home devices, HA, printer,
  network devices, paints, local contractors, home repairs, or 'turn on/off', 'print this',
  'what's on the network', 'what color did we paint', 'find a plumber'.
requires:
  env: [HA_TOKEN, HA_URL]
---

# Home Hub Skill

Central operations skill for the Corral household's physical infrastructure. Manages five domains:
Home Assistant devices, 3D printer queue, network inventory, product/paint registry, and local services.

## 1. Home Assistant Integration

### Connection
- **URL**: `https://ha.clevercorral.com` (env: `HA_URL`)
- **Token**: Long-lived access token (env: `HA_TOKEN`)
- **Entities**: 364 total
- **n8n Mac Mini**: `192.168.1.143:5678` — 3 existing workflows (Morning Briefing, Smart Notion Relay, HA Event Reactor)

### Device Control
Use the HA REST API for device operations:

```bash
# Get entity state
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states/light.living_room"

# Turn on/off
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "light.living_room"}' \
  "$HA_URL/api/services/light/turn_on"

# Set thermostat
curl -s -X POST -H "Authorization: Bearer $HA_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "climate.thermostat", "temperature": 72}' \
  "$HA_URL/api/services/climate/set_temperature"
```

### Common Entity Patterns
- Lights: `light.<room>` — turn_on, turn_off, toggle
- Switches: `switch.<device>` — turn_on, turn_off
- Climate: `climate.<zone>` — set_temperature, set_hvac_mode
- Media: `media_player.<device>` — play, pause, volume_set
- Locks: `lock.<door>` — lock, unlock
- Covers: `cover.<blind>` — open, close, set_position
- Cameras: `camera.<location>` — snapshot

### n8n Webhook Triggers
For complex automations, trigger n8n workflows on the Mac Mini:
```bash
curl -s -X POST "http://192.168.1.143:5678/webhook/<webhook-id>" \
  -H "Content-Type: application/json" \
  -d '{"action": "<action>", "params": {}}'
```

## 2. 3D Printer Queue

### Printer
- **Model**: Bambu Lab (local network)
- **File Format**: STL → sliced to GCODE
- **Cross-Bot**: Receives print jobs from invent-bot via CLI delegation

### Workflow
1. Receive STL file path (from invent-bot or Jon)
2. Log to Notion Printer Queue DB with status "Queued"
3. Notify Jon via Telegram: file name, estimated material, dimensions
4. Jon confirms → update status to "Printing"
5. On completion → update status to "Complete", log material used

### Notion: Printer Queue
| Property | Type | Description |
|----------|------|-------------|
| File Name | Title | STL file name |
| Source | Select | `invent-bot`, `Jon`, `other` |
| Status | Select | `Queued`, `Approved`, `Printing`, `Complete`, `Failed` |
| Material | Select | `PLA`, `PETG`, `TPU`, `ABS` |
| Estimated Time | Text | e.g. "2h 15m" |
| Dimensions | Text | e.g. "120mm × 80mm × 45mm" |
| Notes | Text | Special instructions |
| Date Queued | Date | When the job was submitted |
| Date Completed | Date | When the print finished |

## 3. Network Inventory

Track all devices on the home network.

### Notion: Network Devices
| Property | Type | Description |
|----------|------|-------------|
| Device Name | Title | Human-readable name |
| IP Address | Text | Static or DHCP-assigned IP |
| MAC Address | Text | Hardware address |
| Type | Select | `Router`, `Switch`, `AP`, `Server`, `IoT`, `Computer`, `Phone`, `Printer`, `Camera`, `NAS` |
| URL | URL | Admin/access URL if applicable |
| Location | Select | `Office`, `Living Room`, `Garage`, `Server Closet`, etc. |
| Status | Select | `Online`, `Offline`, `Retired` |
| Notes | Text | Login hints, firmware version, etc. |
| Last Updated | Date | When this entry was last verified |

### Key Network Devices (seed data)
| Device | IP | URL | Type |
|--------|-----|-----|------|
| Abacus VM (Allie) | 208.122.8.11 | — | Server |
| Mac Mini (n8n) | 192.168.1.143 | :5678 | Server |
| Home Assistant | — | ha.clevercorral.com | IoT |
| Bridge API | 208.122.8.11 | :8787 | Server |

## 4. Product & Paint Registry

Track paints, materials, and home products for future reference.

### Notion: Products & Paints
| Property | Type | Description |
|----------|------|-------------|
| Product Name | Title | e.g. "Living Room Accent Wall" or "Deck Stain" |
| Type | Select | `Paint`, `Stain`, `Caulk`, `Adhesive`, `Hardware`, `Material`, `Other` |
| Brand | Text | e.g. "Sherwin-Williams", "Behr" |
| Color/Code | Text | Color name and/or code, e.g. "Agreeable Gray SW 7029" |
| Finish | Select | `Flat`, `Eggshell`, `Satin`, `Semi-Gloss`, `Gloss`, `N/A` |
| Location Used | Text | Where in the house this was applied |
| Purchase Date | Date | When purchased |
| Quantity | Text | e.g. "1 gallon", "2 cans" |
| Store | Text | Where purchased |
| Notes | Text | Application tips, coats needed, etc. |

## 5. Local Services Directory

Track contractors, service providers, and vendor contacts.

### Notion: Local Services
| Property | Type | Description |
|----------|------|-------------|
| Company | Title | Business name |
| Category | Select | `Plumber`, `Electrician`, `HVAC`, `Roofer`, `Painter`, `Landscaper`, `Pest Control`, `Appliance Repair`, `General Handyman`, `Locksmith`, `Cleaning`, `Tree Service`, `Other` |
| Contact Name | Text | Primary contact person |
| Phone | Phone | Primary phone number |
| Email | Email | Contact email |
| Website | URL | Business website |
| Rating | Select | `⭐`, `⭐⭐`, `⭐⭐⭐`, `⭐⭐⭐⭐`, `⭐⭐⭐⭐⭐` |
| Last Used | Date | Most recent service date |
| Estimate | Text | Last quoted price |
| Notes | Text | Quality notes, availability, specialties |
| Recommended By | Text | Who referred them |

## 6. Notion DB Setup

All tables live under a single **Home Hub** page in Notion. On first activation:

1. Create "Home Hub" page under Allie's workspace
2. Create 5 child databases: Printer Queue, Network Devices, Products & Paints, Local Services, Home Maintenance
3. Seed Network Devices with known entries (Abacus VM, Mac Mini, HA)
4. Store the page ID and all DB IDs in this skill's `resources/notion_ids.json`

## 7. Routing

| Request Pattern | Action |
|----------------|--------|
| "Turn on/off [device]" | HA REST API → services endpoint |
| "What's the temperature?" | HA REST API → sensor states |
| "Print this STL" | Log to Printer Queue, notify Jon |
| "What's on the network?" | Query Network Devices DB |
| "What color did we paint the [room]?" | Query Products & Paints DB |
| "Find me a [plumber/electrician]" | Query Local Services DB |
| "Add [contractor] to my contacts" | Create Local Services entry |
| "Check system health" | HA health + network device ping sweep |
