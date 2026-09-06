---
name: drive-health-reader
cron_id: drive-health-reader
model: Gemini 3 Flash
schedule: Daily @ 8am & 6pm
---
## Trigger
Daily at 8am and 6pm. Triggers when new lab result PDFs are uploaded or new Notion entries are made in the Lab Results DB.

## Data Sources
- Lab Results DB (Notion ID: 36d63d55-66c5-8125-8c68-ee03bf91096c/Lab Results)
- Lab Markers DB (Notion ID: 36d63d55-66c5-8125-8c68-ee03bf91096c/Lab Markers)
- `resources/lab_reference_ranges.json`
- `pdfplumber` for parsing PDFs in the drive.

## Algorithm
1. Parse lab values: If source is PDF, use `pdfplumber` to extract marker/value pairs via regex. If Notion, query Lab Results DB.
2. Load reference ranges from `resources/lab_reference_ranges.json`.
3. Compare values against reference (normal and optimal ranges). Assign status: 🟢 (optimal), ⚠️ (normal), 🔴 (out of range).
4. Query prior Lab Results for the same marker to calculate trend direction (↑, →, ↓) and percentage change.
5. Generate priority actions for out-of-range markers.

## Output Format
🧪 Lab Results Summary — [Date]

| Marker | Value | Range | Optimal | Prior | Trend | Status |
|--------|-------|-------|---------|-------|-------|--------|
| [Marker Name] | [Value] [Unit] | [Normal Range] | [Optimal Range] | [Prior Value] | [Trend] | [Status Emoji] |

🎯 Top action: [Priority Action based on worst marker]
📈 Improving: [Marker] [Trend]
⚠️ Watch: [Marker] [Trend]
🆕 First reading: [Marker] at [Value]

## Error Handling
- If PDF format is unrecognized, fallback to manual entry request via Telegram.
- If no reference range found, log "❓ No reference" in status.
- If no new PDFs or entries, exit silently without generating a report.
