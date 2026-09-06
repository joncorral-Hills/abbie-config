import urllib.request, json, os

NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
INVENT_DB_ID = "ff59713b-9715-470d-98f8-f957e56f3850"

headers = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

payload = {
    "parent": {"database_id": INVENT_DB_ID},
    "properties": {
        "Name": {
            "title": [{"text": {"content": "Modular Travel Tube — Swappable Spouts (Squirt/Roll/Dab)"}}]
        },
        "Category": {"multi_select": [{"name": "Invention"}]},
        "Status": {"select": {"name": "Idea"}},
        "Priority": {"select": {"name": "Low"}},
        "Label": {"multi_select": [{"name": "Product"}]}
    },
    "children": [
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [{"text": {"content": "Refillable travel tubes/containers with modular/swappable spouts for squirt, roll-on, and dab applications. Fill with soap, face wash, contact solution, etc. and attach the necessary dispensing head."}}]
        }},
        {"object": "block", "type": "heading_2", "heading_2": {
            "rich_text": [{"text": {"content": "Assessment"}}]
        }},
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [{"text": {"content": "Verdict: Viable niche. Market has modular water bottles (TMB) and interchangeable bottle caps (patent US20140291360A1), but no dedicated toiletry tube system with squirt/roll/dab heads. Best angle: soft squeeze tube body for travel, not rigid water bottle."}}]
        }},
        {"object": "block", "type": "heading_2", "heading_2": {
            "rich_text": [{"text": {"content": "Known Prior Art"}}]
        }},
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [{"text": {"content": "Patent US20140291360A1 — Universal bottle dispensing cap (interchangeable outlets)"}}]
        }},
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [{"text": {"content": "TMB (The Modular Bottle) — modularbottle.com — glass water bottle, 3-4 interchangeable lids, $30-50"}}]
        }},
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [{"text": {"content": "Amazon/Etsy: refillable squeeze bottles, roll-on bottles, dab containers — all sold as separate products, no unified system"}}]
        }},
        {"object": "block", "type": "heading_2", "heading_2": {
            "rich_text": [{"text": {"content": "Suggested Direction"}}]
        }},
        {"object": "block", "type": "paragraph", "paragraph": {
            "rich_text": [{"text": {"content": "Narrow to soft travel-tube form factor (TSA-friendly). Design patent on spout attachment mechanism + form. License to travel accessory or toiletry brands."}}]
        }}
    ]
}

req = urllib.request.Request(
    "https://api.notion.com/v1/pages",
    data=json.dumps(payload).encode(),
    headers=headers,
    method="POST"
)

resp = urllib.request.urlopen(req)
result = json.loads(resp.read())
page_id = result.get("id", "unknown")
url = result.get("url", "no url")
print(f"Saved to INVENT. Page: {url}")