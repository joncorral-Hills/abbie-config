#!/usr/bin/env python3
"""
Hevy Body Metrics Sync — fetches body measurements from Hevy API and
upserts them into the Notion Body Metrics database.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, date

NOTION_API_KEY = os.environ.get("NOTION_API_KEY")
HEVY_API_KEY = os.environ.get("HEVY_API_KEY")
NOTION_VERSION = "2022-06-28"

# Database IDs
BODY_METRICS_DB_ID = "3b163d55-66c5-8149-9aaa-c95a9994c93a"
SYNC_STATE_PATH = os.path.expanduser("~/.hermes/skills/resources/hevy_sync_state.json")
ALT_SYNC_STATE_PATH = os.path.expanduser("~/.hermes/state/hevy_sync_state.json")


def load_sync_state():
    for path in [SYNC_STATE_PATH, ALT_SYNC_STATE_PATH]:
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    return {"last_body_sync": None}


def save_sync_state(state):
    os.makedirs(os.path.dirname(SYNC_STATE_PATH), exist_ok=True)
    with open(SYNC_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def hevy_request(path):
    url = f"https://api.hevyapp.com/v1{path}"
    req = urllib.request.Request(url, headers={"api-key": HEVY_API_KEY})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def notion_request(method, endpoint, data=None):
    url = f"https://api.notion.com/v1/{endpoint}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url, data=body,
        headers={
            "Authorization": f"Bearer {NOTION_API_KEY}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"Notion API error {e.code}: {error_body}")
        raise


def get_existing_dates():
    existing_dates = set()
    has_more = True
    cursor = None
    while has_more:
        payload = {
            "sorts": [{"property": "Date", "direction": "descending"}],
            "page_size": 100
        }
        if cursor:
            payload["start_cursor"] = cursor
        result = notion_request("POST", f"databases/{BODY_METRICS_DB_ID}/query", payload)
        for page in result.get("results", []):
            props = page.get("properties", {})
            date_prop = props.get("Date", {}).get("date", {})
            if date_prop and date_prop.get("start"):
                existing_dates.add(date_prop["start"])
        has_more = result.get("has_more", False)
        cursor = result.get("next_cursor")
    return existing_dates


def cm_to_in(cm):
    if cm is None:
        return None
    return round(cm / 2.54, 1)


def kg_to_lbs(kg):
    if kg is None:
        return None
    return round(kg * 2.20462, 1)


def upsert_measurement(measurement, existing_dates):
    m_date = measurement["date"]
    m = measurement

    properties = {
        "Name": {
            "title": [{"text": {"content": f"Body Metrics - {m_date}"}}]
        },
        "Date": {
            "date": {"start": m_date}
        },
        "Weight (kg)": {
            "number": m.get("weight_kg")
        },
        "Weight (lbs)": {
            "number": kg_to_lbs(m.get("weight_kg"))
        }
    }

    if m.get("fat_percent") is not None:
        properties["Body Fat %"] = {"number": m["fat_percent"]}

    meas_map = {
        "Neck (in)": cm_to_in(m.get("neck_cm")),
        "Shoulders (in)": cm_to_in(m.get("shoulder_cm")),
        "Chest (in)": cm_to_in(m.get("chest_cm")),
        "Left Bicep (in)": cm_to_in(m.get("left_bicep_cm")),
        "Right Bicep (in)": cm_to_in(m.get("right_bicep_cm")),
        "Left Forearm (in)": cm_to_in(m.get("left_forearm_cm")),
        "Right Forearm (in)": cm_to_in(m.get("right_forearm_cm")),
        "Waist (in)": cm_to_in(m.get("waist")),
        "Hips (in)": cm_to_in(m.get("hips")),
        "Left Thigh (in)": cm_to_in(m.get("left_thigh")),
        "Right Thigh (in)": cm_to_in(m.get("right_thigh")),
        "Left Calf (in)": cm_to_in(m.get("left_calf")),
        "Right Calf (in)": cm_to_in(m.get("right_calf")),
    }
    for name, value in meas_map.items():
        if value is not None:
            properties[name] = {"number": value}

    if m_date in existing_dates:
        search_result = notion_request(
            "POST",
            f"databases/{BODY_METRICS_DB_ID}/query",
            {
                "filter": {"property": "Date", "date": {"equals": m_date}},
                "page_size": 1
            }
        )
        pages = search_result.get("results", [])
        if pages:
            page_id = pages[0]["id"]
            notion_request("PATCH", f"pages/{page_id}", {"properties": properties})
            print(f"  Updated {m_date}: {m.get('weight_kg', '?')} kg")
            return {"action": "updated", "date": m_date}

    parent = {"database_id": BODY_METRICS_DB_ID, "type": "database_id"}
    payload = {"parent": parent, "properties": properties}
    try:
        notion_request("POST", "pages", payload)
        print(f"  Created {m_date}: {m.get('weight_kg', '?')} kg")
        return {"action": "created", "date": m_date}
    except Exception as e:
        print(f"  Failed for {m_date}: {e}")
        return {"action": "error", "date": m_date, "error": str(e)}


def get_body_measurements_page(page=1):
    return hevy_request(f"/body_measurements?page={page}")


def main():
    print("Hevy Body Metrics Sync")
    print("=" * 40)
    print()

    if not HEVY_API_KEY:
        print("ERROR: HEVY_API_KEY not found in environment")
        return
    if not NOTION_API_KEY:
        print("ERROR: NOTION_API_KEY not found in environment")
        return

    state = load_sync_state()
    last_body_sync = state.get("last_body_sync")
    print(f"Last body sync: {last_body_sync or 'Never'}")
    print()

    print("Checking existing Notion Body Metrics...")
    existing_dates = get_existing_dates()
    print(f"  Found {len(existing_dates)} existing measurement dates")
    print()

    print("Fetching body measurements from Hevy...")
    all_measurements = []
    page = 1
    while True:
        data = get_body_measurements_page(page)
        measurements = data.get("body_measurements", [])
        if not measurements:
            break
        all_measurements.extend(measurements)
        page += 1
    print(f"  Total measurements from Hevy: {len(all_measurements)}")
    print()

    # Measurements come sorted desc by date; stop at last synced date
    new_measurements = []
    for m in all_measurements:
        m_date = m.get("date", "")
        if last_body_sync and m_date <= last_body_sync:
            break
        if m_date not in existing_dates:
            new_measurements.append(m)

    print(f"New measurements to sync: {len(new_measurements)}")
    print()

    if not new_measurements:
        if all_measurements:
            most_recent = all_measurements[0]["date"]
            state["last_body_sync"] = most_recent
            save_sync_state(state)
            print(f"No new measurements. Updated last_body_sync to {most_recent}")
        else:
            print("No measurements found. Nothing to sync.")
        return

    new_measurements.sort(key=lambda m: m["date"])

    results = {"created": 0, "updated": 0, "errors": 0}
    for m in new_measurements:
        result = upsert_measurement(m, existing_dates)
        if result["action"] == "created":
            results["created"] += 1
            existing_dates.add(m["date"])
        elif result["action"] == "updated":
            results["updated"] += 1
        else:
            results["errors"] += 1

    most_recent = new_measurements[-1]["date"] if new_measurements else None
    if most_recent:
        state["last_body_sync"] = most_recent
        save_sync_state(state)

    print()
    print("=" * 40)
    print(f"Sync complete!")
    print(f"  Created: {results['created']}")
    print(f"  Updated: {results['updated']}")
    print(f"  Errors:  {results['errors']}")
    print(f"  Last body sync: {most_recent}")


if __name__ == "__main__":
    main()