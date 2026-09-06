#!/usr/bin/env python3
"""
Hevy API client for Jon Corral.
Minimal wrapper around the Hevy public API.
https://api.hevyapp.com/docs/

Requires Hevy Pro subscription and API key from:
https://hevy.com/settings?developer
"""
import urllib.request, urllib.parse, json, os

BASE = "https://api.hevyapp.com"

class HevyClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get(self, endpoint, params=None):
        url = f"{BASE}{endpoint}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())

    # ── User ─────────────────────────────────────────────────────────
    def get_user(self):
        return self._get("/v1/user/info")

    # ── Workouts ─────────────────────────────────────────────────────
    def get_workouts(self, page=1, page_size=10):
        return self._get("/v1/workouts", {"page": page, "pageSize": page_size})

    def get_workout(self, workout_id):
        return self._get(f"/v1/workouts/{workout_id}")

    def get_workout_count(self):
        return self._get("/v1/workouts/count")

    def get_workout_events(self, since=None):
        params = {}
        if since:
            params["since"] = since
        return self._get("/v1/workouts/events", params)

    # ── Routines ─────────────────────────────────────────────────────
    def get_routines(self, page=1, page_size=10):
        return self._get("/v1/routines", {"page": page, "pageSize": page_size})

    def get_routine(self, routine_id):
        return self._get(f"/v1/routines/{routine_id}")

    # ── Exercise Templates ───────────────────────────────────────────
    def get_exercise_templates(self, page=1, page_size=10):
        return self._get("/v1/exercise_templates", {"page": page, "pageSize": page_size})

    def get_exercise_template(self, template_id):
        return self._get(f"/v1/exercise_templates/{template_id}")

    # ── Exercise History ─────────────────────────────────────────────
    def get_exercise_history(self, template_id, page=1, page_size=10):
        return self._get(f"/v1/exercise_history/{template_id}", {"page": page, "pageSize": page_size})

    # ── Body Measurements ────────────────────────────────────────────
    def get_body_measurements(self, page=1, page_size=10):
        return self._get("/v1/body_measurements", {"page": page, "pageSize": page_size})

    def get_body_measurement(self, date):
        return self._get(f"/v1/body_measurements/{date}")


def load_api_key():
    """Read HEVY_API_KEY from /home/ubuntu/.hermes/.env"""
    env_path = "/home/ubuntu/.hermes/.env"
    if os.path.exists(env_path):
        with open(env_path) as f:
            env = dict(line.strip().split("=", 1) for line in f if "=" in line and not line.startswith("#"))
        return env.get("HEVY_API_KEY", "")
    return ""


if __name__ == "__main__":
    key = load_api_key()
    if not key:
        print("ERROR: HEVY_API_KEY not found in /home/ubuntu/.hermes/.env")
        print("Get your API key at: https://hevy.com/settings?developer")
        print("Requires Hevy Pro subscription.")
        exit(1)

    client = HevyClient(key)
    print("=== Hevy User Info ===")
    user = client.get_user()
    print(json.dumps(user, indent=2, default=str))

    print("\n=== Workout Count ===")
    count = client.get_workout_count()
    print(json.dumps(count, indent=2, default=str))

    print("\n=== Latest Workouts ===")
    workouts = client.get_workouts(page=1, page_size=5)
    for w in workouts.get("workouts", []):
        print(f"  {w.get('id')} | {w.get('title','Untitled')} | {w.get('start_time','')[:10]}")
