#!/usr/bin/env python3
"""Hevy → Notion Sync — syncs workout data from Hevy API to Notion databases.

Supports delta sync (only changed workouts), full backfill, body measurements,
exercise template caching, and dry-run mode.

Usage:
    python3 hevy_sync.py                    # Delta sync (workouts changed since last sync)
    python3 hevy_sync.py --full-sync         # Full backfill of all workouts
    python3 hevy_sync.py --body-metrics      # Sync body measurements only
    python3 hevy_sync.py --cache-exercises   # Cache exercise templates
    python3 hevy_sync.py --test-connection   # Test API connectivity
    python3 hevy_sync.py --dry-run           # Print what would be synced without writing

Environment Variables:
    HEVY_API_KEY    — Hevy API key (required)
    NOTION_API_KEY  — Notion integration token (required)
"""

import os
import sys
import json
import math
import time
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
except ImportError:
    print("requests not found — installing...")
    os.system(f"{sys.executable} -m pip install requests")
    import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_URL = "https://api.hevyapp.com"
NOTION_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
SCRIPT_DIR = Path(__file__).parent
RESOURCES_DIR = SCRIPT_DIR.parent / "resources"
SYNC_STATE_PATH = RESOURCES_DIR / "hevy_sync_state.json"
EXERCISE_TEMPLATES_PATH = RESOURCES_DIR / "exercise_templates.json"
RATE_LIMIT_DELAY = 0.5  # seconds between Hevy API calls
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds, doubles each retry
TEMPLATE_STALE_DAYS = 7

# Config — DB IDs populated during Notion setup
CONFIG = {
    "health_page_id": "36d63d55-66c5-8125-8c68-ee03bf91096c",
    "workouts_db_id": None,   # Set during Notion DB creation
    "prs_db_id": None,        # Set during Notion DB creation
    "body_metrics_db_id": None,  # Set during Notion DB creation
}

# Muscle group mapping for common exercises
MUSCLE_GROUP_MAP = {
    "chest": ["bench press", "chest press", "chest fly", "push up", "dip", "pec"],
    "back": ["row", "pull up", "chin up", "lat pulldown", "deadlift", "pulldown"],
    "shoulders": ["overhead press", "lateral raise", "shoulder press", "face pull", "front raise", "rear delt"],
    "biceps": ["curl", "bicep"],
    "triceps": ["tricep", "pushdown", "skull crusher", "close grip"],
    "legs": ["squat", "leg press", "lunge", "leg curl", "leg extension", "calf raise", "hip thrust"],
    "core": ["plank", "crunch", "ab ", "sit up", "russian twist", "leg raise"],
    "glutes": ["hip thrust", "glute bridge", "kickback"],
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("hevy_sync")

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

CONFIG_PATH = RESOURCES_DIR / "hevy_config.json"


def load_config() -> dict:
    """Load CONFIG from disk, merging with defaults."""
    global CONFIG
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                saved = json.load(f)
            CONFIG.update(saved)
            log.debug("Loaded config from %s", CONFIG_PATH)
        except (json.JSONDecodeError, IOError) as exc:
            log.warning("Could not read config file: %s", exc)
    return CONFIG


def save_config() -> None:
    """Persist CONFIG to disk."""
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(CONFIG, f, indent=2)
    log.debug("Saved config to %s", CONFIG_PATH)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get_hevy_key() -> str:
    key = os.environ.get("HEVY_API_KEY")
    if not key:
        log.error("HEVY_API_KEY environment variable is not set")
        sys.exit(1)
    return key


def _get_notion_key() -> str:
    key = os.environ.get("NOTION_API_KEY")
    if not key:
        log.error("NOTION_API_KEY environment variable is not set")
        sys.exit(1)
    return key


def hevy_get(endpoint: str, params: dict | None = None) -> dict:
    """GET request to the Hevy API with retries and rate-limit delay.

    Args:
        endpoint: API path (e.g. ``/v1/workouts``).
        params: Optional query parameters.

    Returns:
        Parsed JSON response body.
    """
    url = f"{BASE_URL}{endpoint}"
    headers = {"api-key": _get_hevy_key(), "Accept": "application/json"}
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * attempt
                log.warning("Rate-limited (429). Waiting %ds…", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                log.warning("Hevy GET %s failed (attempt %d/%d): %s — retrying in %ds",
                            endpoint, attempt, MAX_RETRIES, exc, wait)
                time.sleep(wait)
            else:
                log.error("Hevy GET %s failed after %d attempts: %s", endpoint, MAX_RETRIES, exc)

    raise last_exc  # type: ignore[misc]


def notion_post(endpoint: str, data: dict) -> dict:
    """POST to the Notion API.

    Args:
        endpoint: API path (e.g. ``/databases``).
        data: JSON body.

    Returns:
        Parsed JSON response.
    """
    url = f"{NOTION_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {_get_notion_key()}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=30)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * attempt
                log.warning("Notion rate-limited (429). Waiting %ds…", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                log.error("Notion POST %s → %d: %s", endpoint, resp.status_code, resp.text[:500])
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                log.warning("Notion POST %s failed (attempt %d/%d): %s — retrying in %ds",
                            endpoint, attempt, MAX_RETRIES, exc, wait)
                time.sleep(wait)
            else:
                log.error("Notion POST %s failed after %d attempts: %s", endpoint, MAX_RETRIES, exc)

    raise last_exc  # type: ignore[misc]


def notion_patch(endpoint: str, data: dict) -> dict:
    """PATCH to the Notion API (for page updates).

    Args:
        endpoint: API path (e.g. ``/pages/<page_id>``).
        data: JSON body.

    Returns:
        Parsed JSON response.
    """
    url = f"{NOTION_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {_get_notion_key()}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }
    last_exc = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.patch(url, headers=headers, json=data, timeout=30)
            if resp.status_code == 429:
                wait = RETRY_BACKOFF * attempt
                log.warning("Notion rate-limited (429). Waiting %ds…", wait)
                time.sleep(wait)
                continue
            if resp.status_code >= 400:
                log.error("Notion PATCH %s → %d: %s", endpoint, resp.status_code, resp.text[:500])
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                log.warning("Notion PATCH %s failed (attempt %d/%d): %s — retrying in %ds",
                            endpoint, attempt, MAX_RETRIES, exc, wait)
                time.sleep(wait)
            else:
                log.error("Notion PATCH %s failed after %d attempts: %s", endpoint, MAX_RETRIES, exc)

    raise last_exc  # type: ignore[misc]


def notion_query_db(database_id: str, filter_obj: dict | None = None,
                    sorts: list | None = None) -> list[dict]:
    """Query a Notion database and return all matching pages (handles pagination).

    Args:
        database_id: Notion database ID.
        filter_obj: Optional Notion filter object.
        sorts: Optional list of sort objects.

    Returns:
        List of page objects.
    """
    pages: list[dict] = []
    body: dict = {}
    if filter_obj:
        body["filter"] = filter_obj
    if sorts:
        body["sorts"] = sorts

    has_more = True
    while has_more:
        result = notion_post(f"/databases/{database_id}/query", body)
        pages.extend(result.get("results", []))
        has_more = result.get("has_more", False)
        if has_more:
            body["start_cursor"] = result["next_cursor"]

    return pages

# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------


def paginate_hevy(endpoint: str, page_size: int = 10):
    """Generator that yields all items from a paginated Hevy endpoint.

    The Hevy API returns ``{ page, page_count, <data_key>: [...] }`` where
    the data key varies by endpoint (``workouts``, ``body_measurements``,
    ``exercise_templates``, etc.).

    Args:
        endpoint: API path.
        page_size: Number of items per page (max varies by endpoint).

    Yields:
        Individual items from across all pages.
    """
    page = 1
    while True:
        data = hevy_get(endpoint, params={"page": page, "pageSize": page_size})
        page_count = data.get("page_count", 1)

        # Find the data key (it's the key that isn't 'page' or 'page_count')
        data_key = None
        for key in data:
            if key not in ("page", "page_count"):
                val = data[key]
                if isinstance(val, list):
                    data_key = key
                    break

        if data_key is None:
            log.warning("No list key found in Hevy response for %s", endpoint)
            return

        items = data[data_key]
        if not items:
            return

        yield from items

        if page >= page_count:
            return
        page += 1

# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------


def kg_to_lbs(kg: float) -> float:
    """Convert kilograms to pounds, rounded to 1 decimal."""
    return round(kg * 2.20462, 1)


def cm_to_inches(cm: float) -> float:
    """Convert centimeters to inches, rounded to 1 decimal."""
    return round(cm / 2.54, 1)

# ---------------------------------------------------------------------------
# 1RM estimation
# ---------------------------------------------------------------------------


def estimate_1rm(weight_kg: float, reps: int) -> float:
    """Estimate one-rep max from weight and reps.

    Uses the Brzycki formula for reps ≤ 10 and the Epley formula for reps > 10.

    Args:
        weight_kg: Weight lifted in kilograms.
        reps: Number of repetitions.

    Returns:
        Estimated 1RM in kg, rounded to 1 decimal.
    """
    if reps <= 0:
        return weight_kg
    if reps == 1:
        return round(weight_kg, 1)
    if reps <= 10:
        # Brzycki formula
        return round(weight_kg / (1.0278 - 0.0278 * reps), 1)
    # Epley formula
    return round(weight_kg * (1 + reps / 30), 1)

# ---------------------------------------------------------------------------
# Sync state management
# ---------------------------------------------------------------------------


def load_sync_state() -> dict:
    """Load the sync state file.

    Returns:
        Dict with keys like ``last_sync_time``, ``prs``, etc.
    """
    if SYNC_STATE_PATH.exists():
        try:
            with open(SYNC_STATE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            log.warning("Could not read sync state: %s — starting fresh", exc)
    return {
        "last_sync_time": None,
        "synced_workout_ids": [],
        "prs": {},  # { exercise_template_id: { "weight_kg": X, "reps": Y, "e1rm": Z, "date": "..." } }
        "last_body_sync": None,
        "total_workouts_synced": 0,
        "total_prs_detected": 0,
    }


def save_sync_state(state: dict) -> None:
    """Persist sync state to disk."""
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    with open(SYNC_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, default=str)
    log.debug("Sync state saved to %s", SYNC_STATE_PATH)

# ---------------------------------------------------------------------------
# Exercise templates
# ---------------------------------------------------------------------------


def load_exercise_templates() -> dict:
    """Load cached exercise templates. Re-fetch from API if stale (>7 days).

    Returns:
        Dict mapping ``exercise_template_id`` → template dict.
    """
    if EXERCISE_TEMPLATES_PATH.exists():
        try:
            with open(EXERCISE_TEMPLATES_PATH, "r") as f:
                cached = json.load(f)
            fetched_at = cached.get("fetched_at")
            if fetched_at:
                fetched_dt = datetime.fromisoformat(fetched_at)
                age = datetime.now(timezone.utc) - fetched_dt
                if age < timedelta(days=TEMPLATE_STALE_DAYS):
                    return cached.get("templates", {})
            log.info("Exercise template cache is stale — refreshing…")
        except (json.JSONDecodeError, IOError) as exc:
            log.warning("Could not read exercise templates: %s", exc)

    return cache_exercise_templates()


def cache_exercise_templates() -> dict:
    """Fetch all exercise templates from the Hevy API and save to disk.

    Returns:
        Dict mapping ``exercise_template_id`` → template dict.
    """
    log.info("Fetching exercise templates from Hevy…")
    templates: dict = {}
    count = 0

    for tmpl in paginate_hevy("/v1/exercise_templates", page_size=100):
        tmpl_id = tmpl.get("id")
        if tmpl_id:
            templates[tmpl_id] = {
                "id": tmpl_id,
                "title": tmpl.get("title", "Unknown"),
                "type": tmpl.get("type", ""),
                "primary_muscle_group": tmpl.get("primary_muscle_group", ""),
                "secondary_muscle_groups": tmpl.get("secondary_muscle_groups", []),
                "is_custom": tmpl.get("is_custom", False),
            }
            count += 1

    cache_data = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "count": count,
        "templates": templates,
    }

    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    with open(EXERCISE_TEMPLATES_PATH, "w") as f:
        json.dump(cache_data, f, indent=2)

    log.info("Cached %d exercise templates → %s", count, EXERCISE_TEMPLATES_PATH)
    return templates

# ---------------------------------------------------------------------------
# Muscle group detection
# ---------------------------------------------------------------------------


def detect_muscle_groups(exercise_name: str, template: dict | None = None) -> list[str]:
    """Detect muscle groups from exercise name and template metadata.

    Args:
        exercise_name: Human-readable exercise name.
        template: Optional exercise template dict from Hevy.

    Returns:
        List of muscle group names.
    """
    groups: set[str] = set()

    # Use template metadata first
    if template:
        primary = template.get("primary_muscle_group", "")
        if primary:
            groups.add(primary)
        for sec in template.get("secondary_muscle_groups", []):
            if sec:
                groups.add(sec)

    # Fallback: keyword matching on exercise name
    if not groups:
        name_lower = exercise_name.lower()
        for group, keywords in MUSCLE_GROUP_MAP.items():
            if any(kw in name_lower for kw in keywords):
                groups.add(group)

    return sorted(groups) if groups else ["other"]

# ---------------------------------------------------------------------------
# PR detection
# ---------------------------------------------------------------------------


def detect_pr(exercise_template_id: str, exercise_name: str,
              weight_kg: float, reps: int, workout_date: str,
              state: dict) -> dict | None:
    """Check if this set beats the cached PR for this exercise.

    A PR is detected when the estimated 1RM exceeds the previous best for this
    exercise template.

    Args:
        exercise_template_id: Hevy exercise template ID.
        exercise_name: Human-readable exercise name.
        weight_kg: Weight lifted in kg.
        reps: Reps performed.
        workout_date: ISO date string.
        state: Current sync state dict (mutated in place if PR detected).

    Returns:
        PR details dict if a new PR was detected, else ``None``.
    """
    if weight_kg <= 0 or reps <= 0:
        return None

    e1rm = estimate_1rm(weight_kg, reps)
    prs = state.setdefault("prs", {})
    current_best = prs.get(exercise_template_id)

    if current_best and e1rm <= current_best.get("e1rm", 0):
        return None  # Not a PR

    pr_info = {
        "exercise_template_id": exercise_template_id,
        "exercise_name": exercise_name,
        "weight_kg": weight_kg,
        "weight_lbs": kg_to_lbs(weight_kg),
        "reps": reps,
        "e1rm": e1rm,
        "e1rm_lbs": kg_to_lbs(e1rm),
        "date": workout_date,
        "previous_e1rm": current_best.get("e1rm") if current_best else None,
    }

    # Update cached PR
    prs[exercise_template_id] = {
        "weight_kg": weight_kg,
        "reps": reps,
        "e1rm": e1rm,
        "date": workout_date,
        "exercise_name": exercise_name,
    }

    return pr_info

# ---------------------------------------------------------------------------
# Notion dedup helper
# ---------------------------------------------------------------------------


def find_notion_page_by_hevy_id(db_id: str, hevy_id: str) -> str | None:
    """Query Notion DB for a page with a matching Hevy ID property.

    Args:
        db_id: Notion database ID.
        hevy_id: Hevy workout or measurement ID.

    Returns:
        Notion page ID if found, else ``None``.
    """
    try:
        pages = notion_query_db(db_id, filter_obj={
            "property": "Hevy ID",
            "rich_text": {"equals": hevy_id},
        })
        if pages:
            return pages[0]["id"]
    except Exception as exc:
        log.debug("Dedup lookup failed for %s: %s", hevy_id, exc)
    return None

# ---------------------------------------------------------------------------
# Workout sync
# ---------------------------------------------------------------------------


def _build_workout_notion_properties(workout: dict, templates: dict) -> tuple[dict, list[dict]]:
    """Extract workout data and build Notion page properties.

    Returns:
        Tuple of (properties dict, list of PR dicts detected).
    """
    workout_id = workout.get("id", "unknown")
    title = workout.get("title", "Untitled Workout")
    start_time = workout.get("start_time", "")
    end_time = workout.get("end_time", "")
    exercises = workout.get("exercises", [])

    # Parse dates
    workout_date = start_time[:10] if start_time else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Calculate duration in minutes
    duration_min = 0
    if start_time and end_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            duration_min = int((end_dt - start_dt).total_seconds() / 60)
        except (ValueError, TypeError):
            pass

    # Aggregate exercise data
    total_volume_kg = 0.0
    total_sets = 0
    total_reps = 0
    exercise_names: list[str] = []
    all_muscle_groups: set[str] = set()
    prs_detected: list[dict] = []

    for ex in exercises:
        tmpl_id = ex.get("exercise_template_id", "")
        tmpl = templates.get(tmpl_id, {})
        ex_name = tmpl.get("title", ex.get("title", "Unknown Exercise"))
        exercise_names.append(ex_name)

        groups = detect_muscle_groups(ex_name, tmpl)
        all_muscle_groups.update(groups)

        for s in ex.get("sets", []):
            set_type = s.get("type", "normal")
            weight = s.get("weight_kg", 0) or 0
            reps = s.get("reps", 0) or 0

            total_sets += 1
            total_reps += reps
            total_volume_kg += weight * reps

            # Only check PRs on working sets (not warmup)
            if set_type in ("normal", "failure") and weight > 0 and reps > 0:
                # PR detection is done in sync_workouts to access state
                prs_detected.append({
                    "tmpl_id": tmpl_id,
                    "ex_name": ex_name,
                    "weight_kg": weight,
                    "reps": reps,
                    "date": workout_date,
                })

    total_volume_lbs = kg_to_lbs(total_volume_kg)

    properties = {
        "Name": {"title": [{"text": {"content": title}}]},
        "Hevy ID": {"rich_text": [{"text": {"content": workout_id}}]},
        "Date": {"date": {"start": workout_date}},
        "Duration (min)": {"number": duration_min},
        "Exercises": {"rich_text": [{"text": {"content": ", ".join(exercise_names[:20])}}]},
        "Total Sets": {"number": total_sets},
        "Total Reps": {"number": total_reps},
        "Volume (lbs)": {"number": total_volume_lbs},
        "Volume (kg)": {"number": round(total_volume_kg, 1)},
        "Muscle Groups": {"multi_select": [{"name": g} for g in sorted(all_muscle_groups)]},
        "Exercise Count": {"number": len(exercises)},
    }

    return properties, prs_detected


def sync_workouts(full: bool = False, dry_run: bool = False) -> None:
    """Sync workouts from Hevy to Notion.

    Args:
        full: If True, backfill all workouts. If False, only sync changes since
              the last sync timestamp.
        dry_run: If True, print what would happen without writing to Notion.
    """
    db_id = CONFIG.get("workouts_db_id")
    if not db_id:
        log.error("workouts_db_id not configured. Run setup first or set it in %s", CONFIG_PATH)
        return

    state = load_sync_state()
    templates = load_exercise_templates()
    synced_ids = set(state.get("synced_workout_ids", []))

    mode = "FULL" if full else "DELTA"
    log.info("Starting %s workout sync (dry_run=%s)…", mode, dry_run)

    workouts_to_sync: list[dict] = []

    if full:
        # Fetch all workouts via pagination
        for workout in paginate_hevy("/v1/workouts", page_size=10):
            workouts_to_sync.append(workout)
    else:
        # Delta: use events endpoint if we have a last sync time
        last_sync = state.get("last_sync_time")
        if last_sync:
            log.info("Fetching workouts changed since %s…", last_sync)
            try:
                for event in paginate_hevy("/v1/workouts/events", page_size=10):
                    # Events contain workout objects
                    workout = event.get("workout") or event
                    workouts_to_sync.append(workout)
            except requests.RequestException:
                log.warning("Events endpoint failed — falling back to full paginated fetch")
                for workout in paginate_hevy("/v1/workouts", page_size=10):
                    workouts_to_sync.append(workout)
        else:
            log.info("No previous sync — fetching all workouts…")
            for workout in paginate_hevy("/v1/workouts", page_size=10):
                workouts_to_sync.append(workout)

    log.info("Found %d workouts to process", len(workouts_to_sync))

    synced_count = 0
    skipped_count = 0
    pr_count = 0
    all_prs: list[dict] = []

    for workout in workouts_to_sync:
        workout_id = workout.get("id", "")
        if not workout_id:
            log.warning("Skipping workout with no ID")
            skipped_count += 1
            continue

        properties, pr_candidates = _build_workout_notion_properties(workout, templates)

        # Detect PRs
        for pc in pr_candidates:
            pr = detect_pr(pc["tmpl_id"], pc["ex_name"], pc["weight_kg"],
                           pc["reps"], pc["date"], state)
            if pr:
                all_prs.append(pr)
                pr_count += 1

        if dry_run:
            title = workout.get("title", "Untitled")
            date = properties.get("Date", {}).get("date", {}).get("start", "?")
            vol = properties.get("Volume (lbs)", {}).get("number", 0)
            log.info("[DRY RUN] Would sync: %s on %s — %d sets, %s lbs volume",
                     title, date, properties.get("Total Sets", {}).get("number", 0), vol)
            synced_count += 1
            continue

        # Check for existing page (dedup)
        existing_page_id = find_notion_page_by_hevy_id(db_id, workout_id)

        if existing_page_id:
            # Update existing page
            try:
                notion_patch(f"/pages/{existing_page_id}", {"properties": properties})
                log.debug("Updated workout %s (page %s)", workout_id, existing_page_id)
            except Exception as exc:
                log.error("Failed to update workout %s: %s", workout_id, exc)
                continue
        else:
            # Create new page
            try:
                notion_post("/pages", {
                    "parent": {"database_id": db_id},
                    "properties": properties,
                })
                log.debug("Created workout %s", workout_id)
            except Exception as exc:
                log.error("Failed to create workout %s: %s", workout_id, exc)
                continue

        synced_ids.add(workout_id)
        synced_count += 1

    # Sync PRs to Notion PR database
    prs_db_id = CONFIG.get("prs_db_id")
    if all_prs and prs_db_id and not dry_run:
        log.info("Syncing %d PRs to Notion…", len(all_prs))
        for pr in all_prs:
            pr_properties = {
                "Name": {"title": [{"text": {"content": f"🏆 {pr['exercise_name']}"}}]},
                "Exercise": {"rich_text": [{"text": {"content": pr["exercise_name"]}}]},
                "Weight (lbs)": {"number": pr["weight_lbs"]},
                "Reps": {"number": pr["reps"]},
                "Estimated 1RM (lbs)": {"number": pr["e1rm_lbs"]},
                "Date": {"date": {"start": pr["date"]}},
            }
            if pr.get("previous_e1rm"):
                improvement = round(pr["e1rm"] - pr["previous_e1rm"], 1)
                pr_properties["Improvement (kg)"] = {"number": improvement}

            try:
                notion_post("/pages", {
                    "parent": {"database_id": prs_db_id},
                    "properties": pr_properties,
                })
            except Exception as exc:
                log.error("Failed to create PR record for %s: %s", pr["exercise_name"], exc)

    # Update state
    state["last_sync_time"] = datetime.now(timezone.utc).isoformat()
    state["synced_workout_ids"] = list(synced_ids)[-500:]  # Keep last 500 IDs
    state["total_workouts_synced"] = state.get("total_workouts_synced", 0) + synced_count
    state["total_prs_detected"] = state.get("total_prs_detected", 0) + pr_count

    if not dry_run:
        save_sync_state(state)

    # Summary
    log.info("=" * 60)
    log.info("Sync complete!")
    log.info("  Mode:           %s%s", mode, " (DRY RUN)" if dry_run else "")
    log.info("  Workouts synced: %d", synced_count)
    log.info("  Workouts skipped: %d", skipped_count)
    log.info("  PRs detected:    %d", pr_count)
    for pr in all_prs:
        prev = f" (prev: {kg_to_lbs(pr['previous_e1rm'])} lbs)" if pr.get("previous_e1rm") else ""
        log.info("    🏆 %s: %s lbs × %d reps → e1RM %s lbs%s",
                 pr["exercise_name"], pr["weight_lbs"], pr["reps"], pr["e1rm_lbs"], prev)
    log.info("=" * 60)

# ---------------------------------------------------------------------------
# Body metrics sync
# ---------------------------------------------------------------------------


def sync_body_metrics(dry_run: bool = False) -> None:
    """Sync body measurements from Hevy to Notion.

    Fetches all body measurements, converts units, computes a 7-day rolling
    weight average, and creates/updates rows in the Body Metrics Notion DB.

    Args:
        dry_run: If True, print what would happen without writing.
    """
    db_id = CONFIG.get("body_metrics_db_id")
    if not db_id:
        log.error("body_metrics_db_id not configured. Run setup first or set it in %s", CONFIG_PATH)
        return

    state = load_sync_state()
    log.info("Starting body metrics sync (dry_run=%s)…", dry_run)

    measurements: list[dict] = []
    for m in paginate_hevy("/v1/body_measurements", page_size=10):
        measurements.append(m)

    log.info("Fetched %d body measurements", len(measurements))

    if not measurements:
        log.info("No body measurements to sync")
        return

    # Sort by date for rolling average calculation
    measurements.sort(key=lambda m: m.get("date", m.get("created_at", "")))

    # Build weight history for rolling average
    weight_history: list[tuple[str, float]] = []
    for m in measurements:
        weight_kg = m.get("weight_kg")
        if weight_kg and weight_kg > 0:
            date_str = m.get("date", m.get("created_at", ""))[:10]
            weight_history.append((date_str, weight_kg))

    synced_count = 0

    for m in measurements:
        m_id = m.get("id", "")
        date_str = m.get("date", m.get("created_at", ""))[:10]
        weight_kg = m.get("weight_kg")
        body_fat_pct = m.get("body_fat_percentage")
        neck_cm = m.get("neck_cm")
        shoulders_cm = m.get("shoulders_cm")
        chest_cm = m.get("chest_cm")
        left_bicep_cm = m.get("left_bicep_cm")
        right_bicep_cm = m.get("right_bicep_cm")
        waist_cm = m.get("waist_cm")
        hips_cm = m.get("hips_cm")
        left_thigh_cm = m.get("left_thigh_cm")
        right_thigh_cm = m.get("right_thigh_cm")
        left_calf_cm = m.get("left_calf_cm")
        right_calf_cm = m.get("right_calf_cm")

        # 7-day rolling weight average
        rolling_avg_lbs = None
        if weight_kg:
            try:
                current_date = datetime.strptime(date_str, "%Y-%m-%d")
                window_start = current_date - timedelta(days=6)
                window_weights = [
                    w for d, w in weight_history
                    if window_start <= datetime.strptime(d, "%Y-%m-%d") <= current_date
                ]
                if window_weights:
                    rolling_avg_kg = sum(window_weights) / len(window_weights)
                    rolling_avg_lbs = kg_to_lbs(rolling_avg_kg)
            except (ValueError, TypeError):
                pass

        properties: dict = {
            "Name": {"title": [{"text": {"content": f"Body Metrics — {date_str}"}}]},
            "Hevy ID": {"rich_text": [{"text": {"content": str(m_id)}}]},
            "Date": {"date": {"start": date_str}},
        }

        if weight_kg:
            properties["Weight (lbs)"] = {"number": kg_to_lbs(weight_kg)}
            properties["Weight (kg)"] = {"number": round(weight_kg, 1)}
        if rolling_avg_lbs:
            properties["7-Day Avg (lbs)"] = {"number": rolling_avg_lbs}
        if body_fat_pct:
            properties["Body Fat %"] = {"number": round(body_fat_pct, 1)}
        if waist_cm:
            properties["Waist (in)"] = {"number": cm_to_inches(waist_cm)}
        if chest_cm:
            properties["Chest (in)"] = {"number": cm_to_inches(chest_cm)}
        if neck_cm:
            properties["Neck (in)"] = {"number": cm_to_inches(neck_cm)}
        if shoulders_cm:
            properties["Shoulders (in)"] = {"number": cm_to_inches(shoulders_cm)}
        if hips_cm:
            properties["Hips (in)"] = {"number": cm_to_inches(hips_cm)}

        # Biceps — average if both provided
        bicep_values = [v for v in [left_bicep_cm, right_bicep_cm] if v]
        if bicep_values:
            avg_bicep = sum(bicep_values) / len(bicep_values)
            properties["Bicep (in)"] = {"number": cm_to_inches(avg_bicep)}

        # Thighs — average if both provided
        thigh_values = [v for v in [left_thigh_cm, right_thigh_cm] if v]
        if thigh_values:
            avg_thigh = sum(thigh_values) / len(thigh_values)
            properties["Thigh (in)"] = {"number": cm_to_inches(avg_thigh)}

        # Calves — average if both provided
        calf_values = [v for v in [left_calf_cm, right_calf_cm] if v]
        if calf_values:
            avg_calf = sum(calf_values) / len(calf_values)
            properties["Calf (in)"] = {"number": cm_to_inches(avg_calf)}

        if dry_run:
            w = properties.get("Weight (lbs)", {}).get("number", "N/A")
            log.info("[DRY RUN] Would sync body metrics for %s — weight: %s lbs", date_str, w)
            synced_count += 1
            continue

        # Dedup
        existing_page_id = find_notion_page_by_hevy_id(db_id, str(m_id))

        if existing_page_id:
            try:
                notion_patch(f"/pages/{existing_page_id}", {"properties": properties})
                log.debug("Updated body metrics %s (page %s)", m_id, existing_page_id)
            except Exception as exc:
                log.error("Failed to update body metrics %s: %s", m_id, exc)
                continue
        else:
            try:
                notion_post("/pages", {
                    "parent": {"database_id": db_id},
                    "properties": properties,
                })
                log.debug("Created body metrics %s", m_id)
            except Exception as exc:
                log.error("Failed to create body metrics %s: %s", m_id, exc)
                continue

        synced_count += 1

    # Update state
    state["last_body_sync"] = datetime.now(timezone.utc).isoformat()
    if not dry_run:
        save_sync_state(state)

    # Summary
    log.info("=" * 60)
    log.info("Body metrics sync complete!")
    log.info("  Measurements synced: %d%s", synced_count, " (DRY RUN)" if dry_run else "")
    log.info("=" * 60)

# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------


def test_connection() -> bool:
    """Test connectivity to both the Hevy and Notion APIs.

    Returns:
        True if both APIs respond successfully.
    """
    success = True

    log.info("Testing Hevy API connection…")
    try:
        data = hevy_get("/v1/workouts", params={"page": 1, "pageSize": 1})
        count = data.get("page_count", "?")
        log.info("  ✅ Hevy API OK — %s page(s) of workouts available", count)
    except Exception as exc:
        log.error("  ❌ Hevy API failed: %s", exc)
        success = False

    log.info("Testing Notion API connection…")
    try:
        url = f"{NOTION_URL}/users/me"
        headers = {
            "Authorization": f"Bearer {_get_notion_key()}",
            "Notion-Version": NOTION_VERSION,
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        user = resp.json()
        name = user.get("name", user.get("id", "unknown"))
        log.info("  ✅ Notion API OK — authenticated as: %s", name)
    except Exception as exc:
        log.error("  ❌ Notion API failed: %s", exc)
        success = False

    # Check config
    log.info("Checking configuration…")
    for key, val in CONFIG.items():
        status = "✅" if val else "⚠️  NOT SET"
        log.info("  %s %s = %s", status, key, val or "(empty)")

    return success

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate action."""
    parser = argparse.ArgumentParser(
        description="Sync Hevy workout data to Notion databases.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 hevy_sync.py                    # Delta sync
  python3 hevy_sync.py --full-sync        # Full backfill
  python3 hevy_sync.py --body-metrics     # Sync body measurements
  python3 hevy_sync.py --cache-exercises  # Refresh exercise template cache
  python3 hevy_sync.py --test-connection  # Test API connectivity
  python3 hevy_sync.py --dry-run          # Preview without writing
        """,
    )

    parser.add_argument("--full-sync", action="store_true",
                        help="Full backfill of all workouts (instead of delta)")
    parser.add_argument("--body-metrics", action="store_true",
                        help="Sync body measurements only")
    parser.add_argument("--cache-exercises", action="store_true",
                        help="Refresh the exercise template cache")
    parser.add_argument("--test-connection", action="store_true",
                        help="Test API connectivity and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be synced without writing to Notion")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load persisted config
    load_config()

    # Dispatch
    if args.test_connection:
        ok = test_connection()
        sys.exit(0 if ok else 1)

    if args.cache_exercises:
        templates = cache_exercise_templates()
        log.info("Done. %d templates cached.", len(templates))
        return

    if args.body_metrics:
        sync_body_metrics(dry_run=args.dry_run)
        return

    # Default: workout sync
    sync_workouts(full=args.full_sync, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
