#!/usr/bin/env python3
"""Health Webhook Receiver — FastAPI app for Health Auto Export data.

Receives JSON payloads from the Health Auto Export iOS app and stores them
in a local SQLite database for Allie to query. Supports both HTTP server mode
and CLI query mode for terminal-based access.

Usage:
    python3 health_webhook.py                    # Start server on port 8082
    python3 health_webhook.py --port 8083        # Custom port
    python3 health_webhook.py --init-db          # Initialize database only
    python3 health_webhook.py --query latest     # Show latest readings
    python3 health_webhook.py --query sleep      # Show recent sleep data
    python3 health_webhook.py --query trends     # Show 30-day trends
    python3 health_webhook.py --query summary    # Human-readable summary
    python3 health_webhook.py --query recovery   # Recovery score inputs

Environment Variables:
    HEALTH_WEBHOOK_TOKEN  — Bearer token for incoming webhook auth (required)
    HEALTH_DB_PATH        — Override SQLite database path (optional)
"""

import os
import sys
import json
import sqlite3
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Optional dependency imports
# ---------------------------------------------------------------------------

try:
    from fastapi import FastAPI, Request, HTTPException, Depends, Query
    from fastapi.responses import JSONResponse
except ImportError:
    FastAPI = None  # type: ignore[assignment, misc]

try:
    import uvicorn
except ImportError:
    uvicorn = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
DEFAULT_DB_PATH = SCRIPT_DIR / "health_data.db"
DEFAULT_PORT = 8082

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("health_webhook")

# ---------------------------------------------------------------------------
# Metric name normalization
# ---------------------------------------------------------------------------

METRIC_MAP = {
    # Cardiovascular
    "Heart Rate": "heart_rate",
    "heart_rate": "heart_rate",
    "Heart Rate Variability": "heart_rate_variability",
    "heart_rate_variability": "heart_rate_variability",
    "HRV": "heart_rate_variability",
    "Resting Heart Rate": "resting_heart_rate",
    "resting_heart_rate": "resting_heart_rate",
    "Resting Heart Rate (BPM)": "resting_heart_rate",
    "Blood Pressure Systolic": "blood_pressure_systolic",
    "Blood Pressure Diastolic": "blood_pressure_diastolic",

    # Activity
    "Step Count": "step_count",
    "step_count": "step_count",
    "Steps": "step_count",
    "Active Energy Burned": "active_energy",
    "active_energy": "active_energy",
    "Active Energy": "active_energy",
    "Basal Energy Burned": "basal_energy",
    "Exercise Minutes": "exercise_minutes",
    "Apple Exercise Time": "exercise_minutes",
    "Stand Hours": "stand_hours",
    "Apple Stand Hour": "stand_hours",
    "Flights Climbed": "flights_climbed",
    "Distance Walking Running": "distance_walking_running",
    "Walking + Running Distance": "distance_walking_running",

    # Body composition
    "Body Mass": "weight",
    "Weight": "weight",
    "Body Fat Percentage": "body_fat_pct",
    "Body Mass Index": "bmi",
    "Lean Body Mass": "lean_body_mass",
    "Waist Circumference": "waist_circumference",

    # Sleep
    "Sleep Analysis": "sleep_analysis",
    "sleep_analysis": "sleep_analysis",
    "Sleep": "sleep_analysis",
    "Sleep In Bed": "sleep_in_bed",
    "Sleep Asleep": "sleep_asleep",
    "Sleep Deep": "sleep_deep",
    "Sleep REM": "sleep_rem",
    "Sleep Core": "sleep_core",
    "Sleep Awake": "sleep_awake",

    # Respiratory
    "Respiratory Rate": "respiratory_rate",
    "Blood Oxygen Saturation": "blood_oxygen",
    "Oxygen Saturation": "blood_oxygen",
    "SpO2": "blood_oxygen",

    # Fitness
    "VO2 Max": "vo2_max",
    "vo2_max": "vo2_max",
    "Walking Heart Rate Average": "walking_heart_rate_avg",

    # Nutrition
    "Dietary Energy": "dietary_energy",
    "Dietary Protein": "dietary_protein",
    "Dietary Carbohydrates": "dietary_carbs",
    "Dietary Fat Total": "dietary_fat",
    "Dietary Fiber": "dietary_fiber",
    "Dietary Water": "dietary_water",
    "Caffeine": "caffeine",

    # Other
    "Mindful Minutes": "mindful_minutes",
    "Headphone Audio Levels": "headphone_audio",
    "Environmental Sound Levels": "environmental_sound",
}

# Unit normalization
UNIT_MAP = {
    "count/min": "bpm",
    "count": "count",
    "ms": "ms",
    "kcal": "kcal",
    "Cal": "kcal",
    "hr": "hours",
    "min": "minutes",
    "lb": "lbs",
    "kg": "kg",
    "%": "%",
    "mi": "miles",
    "km": "km",
    "count/s": "count/s",
    "mL/kg·min": "mL/kg·min",
    "breaths/min": "breaths/min",
    "dBASPL": "dB",
}

# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------


def get_db_path() -> Path:
    """Get the database file path from env or default."""
    return Path(os.environ.get("HEALTH_DB_PATH", str(DEFAULT_DB_PATH)))


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a SQLite connection with row_factory = sqlite3.Row."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Optional[Path] = None) -> None:
    """Create tables and indexes if they don't exist."""
    conn = get_db_connection(db_path)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS health_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL,
                source TEXT,
                sample_date TEXT NOT NULL,
                received_at TEXT DEFAULT (datetime('now')),
                UNIQUE(metric_name, sample_date, source)
            );

            CREATE INDEX IF NOT EXISTS idx_metric_date
                ON health_samples(metric_name, sample_date);

            CREATE INDEX IF NOT EXISTS idx_sample_date
                ON health_samples(sample_date DESC);

            CREATE INDEX IF NOT EXISTS idx_received_at
                ON health_samples(received_at DESC);
        """)
        conn.commit()
        log.info("Database initialized at %s", get_db_path())
    finally:
        conn.close()


def normalize_metric_name(raw_name: str) -> str:
    """Normalize a Health Auto Export metric name to an internal key."""
    if raw_name in METRIC_MAP:
        return METRIC_MAP[raw_name]
    # Fallback: lowercase, replace spaces with underscores
    return raw_name.lower().replace(" ", "_").replace("-", "_")


def normalize_unit(raw_unit: str) -> str:
    """Normalize a unit string."""
    return UNIT_MAP.get(raw_unit, raw_unit)


def insert_health_samples(conn: sqlite3.Connection, metric_name: str,
                           unit: str, data_points: list[dict]) -> int:
    """Insert health data points with INSERT OR REPLACE for dedup.

    Returns:
        Number of rows inserted/updated.
    """
    normalized_metric = normalize_metric_name(metric_name)
    normalized_unit = normalize_unit(unit)
    count = 0

    for dp in data_points:
        value = dp.get("value") or dp.get("qty")
        date_str = dp.get("date", "")
        source = dp.get("source", "Apple Health")

        if value is None:
            continue

        try:
            value = float(value)
        except (ValueError, TypeError):
            log.warning("Skipping non-numeric value for %s: %s", normalized_metric, value)
            continue

        # Normalize date — keep ISO format
        if isinstance(date_str, str) and date_str:
            # Truncate to second precision for dedup consistency
            sample_date = date_str[:19]
        else:
            sample_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

        conn.execute(
            """INSERT OR REPLACE INTO health_samples
               (metric_name, value, unit, source, sample_date)
               VALUES (?, ?, ?, ?, ?)""",
            (normalized_metric, value, normalized_unit, source, sample_date),
        )
        count += 1

    conn.commit()
    return count

# ---------------------------------------------------------------------------
# Query functions
# ---------------------------------------------------------------------------


def query_latest(conn: sqlite3.Connection) -> list[dict]:
    """Return the most recent reading for each metric."""
    rows = conn.execute("""
        SELECT metric_name, value, unit, source, sample_date, received_at
        FROM health_samples
        WHERE id IN (
            SELECT id FROM health_samples h1
            WHERE sample_date = (
                SELECT MAX(sample_date) FROM health_samples h2
                WHERE h2.metric_name = h1.metric_name
            )
        )
        ORDER BY metric_name
    """).fetchall()
    return [dict(r) for r in rows]


def query_sleep(conn: sqlite3.Connection, date: Optional[str] = None) -> list[dict]:
    """Return sleep data for a specific date (or most recent)."""
    sleep_metrics = ("sleep_analysis", "sleep_in_bed", "sleep_asleep",
                     "sleep_deep", "sleep_rem", "sleep_core", "sleep_awake")
    placeholders = ",".join("?" for _ in sleep_metrics)

    if date:
        rows = conn.execute(
            f"""SELECT metric_name, value, unit, source, sample_date
                FROM health_samples
                WHERE metric_name IN ({placeholders})
                  AND sample_date LIKE ?
                ORDER BY sample_date DESC""",
            (*sleep_metrics, f"{date}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""SELECT metric_name, value, unit, source, sample_date
                FROM health_samples
                WHERE metric_name IN ({placeholders})
                ORDER BY sample_date DESC
                LIMIT 20""",
            sleep_metrics,
        ).fetchall()

    return [dict(r) for r in rows]


def query_trends(conn: sqlite3.Connection, metric: str = "heart_rate",
                 days: int = 30) -> list[dict]:
    """Return time series for a metric over the last N days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    normalized = normalize_metric_name(metric)

    rows = conn.execute(
        """SELECT metric_name, value, unit, sample_date
           FROM health_samples
           WHERE metric_name = ?
             AND sample_date >= ?
           ORDER BY sample_date ASC""",
        (normalized, cutoff),
    ).fetchall()

    results = [dict(r) for r in rows]

    if results:
        values = [r["value"] for r in results]
        summary = {
            "metric": normalized,
            "days": days,
            "count": len(values),
            "min": round(min(values), 1),
            "max": round(max(values), 1),
            "avg": round(sum(values) / len(values), 1),
            "latest": values[-1],
        }
        return [{"summary": summary, "data": results}]

    return results


def query_summary(conn: sqlite3.Connection) -> dict:
    """Return a human-readable summary of all latest metrics."""
    latest = query_latest(conn)
    if not latest:
        return {"message": "No health data recorded yet."}

    categories: dict[str, list[dict]] = {
        "❤️ Cardiovascular": [],
        "🏃 Activity": [],
        "😴 Sleep": [],
        "⚖️ Body": [],
        "🫁 Respiratory": [],
        "🍽️ Nutrition": [],
        "📊 Other": [],
    }

    category_map = {
        "heart_rate": "❤️ Cardiovascular",
        "heart_rate_variability": "❤️ Cardiovascular",
        "resting_heart_rate": "❤️ Cardiovascular",
        "blood_pressure_systolic": "❤️ Cardiovascular",
        "blood_pressure_diastolic": "❤️ Cardiovascular",
        "walking_heart_rate_avg": "❤️ Cardiovascular",
        "step_count": "🏃 Activity",
        "active_energy": "🏃 Activity",
        "exercise_minutes": "🏃 Activity",
        "stand_hours": "🏃 Activity",
        "flights_climbed": "🏃 Activity",
        "distance_walking_running": "🏃 Activity",
        "vo2_max": "🏃 Activity",
        "sleep_analysis": "😴 Sleep",
        "sleep_in_bed": "😴 Sleep",
        "sleep_asleep": "😴 Sleep",
        "sleep_deep": "😴 Sleep",
        "sleep_rem": "😴 Sleep",
        "sleep_core": "😴 Sleep",
        "sleep_awake": "😴 Sleep",
        "weight": "⚖️ Body",
        "body_fat_pct": "⚖️ Body",
        "bmi": "⚖️ Body",
        "lean_body_mass": "⚖️ Body",
        "waist_circumference": "⚖️ Body",
        "respiratory_rate": "🫁 Respiratory",
        "blood_oxygen": "🫁 Respiratory",
        "dietary_energy": "🍽️ Nutrition",
        "dietary_protein": "🍽️ Nutrition",
        "dietary_carbs": "🍽️ Nutrition",
        "dietary_fat": "🍽️ Nutrition",
        "dietary_fiber": "🍽️ Nutrition",
        "dietary_water": "🍽️ Nutrition",
        "caffeine": "🍽️ Nutrition",
    }

    for reading in latest:
        cat = category_map.get(reading["metric_name"], "📊 Other")
        categories[cat].append(reading)

    # Build text summary
    lines = ["📋 Health Data Summary", "=" * 40, ""]
    for cat_name, readings in categories.items():
        if not readings:
            continue
        lines.append(f"\n{cat_name}")
        lines.append("-" * 30)
        for r in readings:
            name = r["metric_name"].replace("_", " ").title()
            lines.append(f"  {name}: {r['value']} {r['unit']}  ({r['sample_date'][:10]})")

    total = sum(len(v) for v in categories.values())
    lines.append(f"\n{'=' * 40}")
    lines.append(f"Total metrics tracked: {total}")

    return {
        "text": "\n".join(lines),
        "categories": {k: v for k, v in categories.items() if v},
        "total_metrics": total,
    }


def query_recovery_inputs(conn: sqlite3.Connection) -> dict:
    """Return the specific data points needed for Recovery Score calculation.

    The Recovery Score formula uses:
    - Last night's sleep duration (hours)
    - Latest HRV (ms)
    - Latest Resting Heart Rate (bpm)
    """
    result: dict = {
        "sleep_hours": None,
        "hrv_ms": None,
        "resting_hr_bpm": None,
        "data_freshness": {},
    }

    # Sleep — last night's total
    sleep_row = conn.execute(
        """SELECT value, unit, sample_date FROM health_samples
           WHERE metric_name IN ('sleep_asleep', 'sleep_analysis', 'sleep_in_bed')
           ORDER BY sample_date DESC LIMIT 1"""
    ).fetchone()
    if sleep_row:
        val = sleep_row["value"]
        unit = sleep_row["unit"]
        # Convert to hours if in minutes
        if unit in ("minutes", "min"):
            val = round(val / 60, 2)
        result["sleep_hours"] = val
        result["data_freshness"]["sleep"] = sleep_row["sample_date"]

    # HRV
    hrv_row = conn.execute(
        """SELECT value, unit, sample_date FROM health_samples
           WHERE metric_name = 'heart_rate_variability'
           ORDER BY sample_date DESC LIMIT 1"""
    ).fetchone()
    if hrv_row:
        result["hrv_ms"] = hrv_row["value"]
        result["data_freshness"]["hrv"] = hrv_row["sample_date"]

    # Resting HR
    rhr_row = conn.execute(
        """SELECT value, unit, sample_date FROM health_samples
           WHERE metric_name = 'resting_heart_rate'
           ORDER BY sample_date DESC LIMIT 1"""
    ).fetchone()
    if rhr_row:
        result["resting_hr_bpm"] = rhr_row["value"]
        result["data_freshness"]["resting_hr"] = rhr_row["sample_date"]

    # Check data staleness
    now = datetime.now(timezone.utc)
    for key, date_str in result["data_freshness"].items():
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            age_hours = (now - dt).total_seconds() / 3600
            result["data_freshness"][key] = {
                "date": date_str,
                "age_hours": round(age_hours, 1),
                "stale": age_hours > 24,
            }
        except (ValueError, TypeError):
            pass

    return result

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

if FastAPI is not None:
    app = FastAPI(
        title="Health Webhook Receiver",
        description="Receives Apple Health data from Health Auto Export and stores it in SQLite.",
        version="1.0.0",
    )

    def get_token() -> str:
        """Get the expected bearer token from environment."""
        token = os.environ.get("HEALTH_WEBHOOK_TOKEN")
        if not token:
            log.warning("HEALTH_WEBHOOK_TOKEN not set — webhook auth disabled")
        return token or ""

    def verify_auth(request: Request) -> None:
        """Validate Authorization header against expected token."""
        expected = get_token()
        if not expected:
            return  # Auth disabled if no token configured

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")

        token = auth_header[7:]  # Strip "Bearer "
        if token != expected:
            raise HTTPException(status_code=401, detail="Invalid token")

    @app.on_event("startup")
    async def startup():
        """Initialize the database on server startup."""
        init_db()
        log.info("Health webhook server started")

    @app.post("/api/health")
    async def receive_health_data(request: Request):
        """Receive Health Auto Export JSON payload.

        Expected format — either a single metric object or an array:
        ```json
        {"name": "Heart Rate", "unit": "count/min",
         "data": [{"value": 72, "date": "2026-06-10T08:00:00Z", "source": "Apple Watch"}]}
        ```
        """
        verify_auth(request)

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        conn = get_db_connection()
        total_inserted = 0

        try:
            # Handle both single metric and array of metrics
            metrics = body if isinstance(body, list) else [body]

            for metric in metrics:
                name = metric.get("name", "")
                unit = metric.get("unit", "")
                data_points = metric.get("data", [])

                if not name:
                    log.warning("Skipping metric with no name")
                    continue

                if not data_points:
                    log.warning("Skipping metric %s with no data points", name)
                    continue

                count = insert_health_samples(conn, name, unit, data_points)
                total_inserted += count
                log.info("Inserted %d samples for %s", count, name)

        finally:
            conn.close()

        return {
            "status": "ok",
            "samples_stored": total_inserted,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    @app.get("/api/health/latest")
    async def get_latest():
        """Return the most recent reading for each metric."""
        conn = get_db_connection()
        try:
            results = query_latest(conn)
            return {"metrics": results, "count": len(results)}
        finally:
            conn.close()

    @app.get("/api/health/sleep")
    async def get_sleep(date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")):
        """Return sleep data for a specific date or the most recent."""
        conn = get_db_connection()
        try:
            results = query_sleep(conn, date)
            return {"sleep_data": results, "count": len(results)}
        finally:
            conn.close()

    @app.get("/api/health/trends")
    async def get_trends(
        metric: str = Query("heart_rate", description="Metric name"),
        days: int = Query(30, description="Number of days", ge=1, le=365),
    ):
        """Return time series for a metric over the last N days."""
        conn = get_db_connection()
        try:
            results = query_trends(conn, metric, days)
            return {"trends": results}
        finally:
            conn.close()

    @app.get("/api/health/summary")
    async def get_summary():
        """Return a human-readable summary of all latest metrics."""
        conn = get_db_connection()
        try:
            return query_summary(conn)
        finally:
            conn.close()

    @app.get("/api/health/recovery-inputs")
    async def get_recovery_inputs():
        """Return the specific data points needed for the Recovery Score calculation."""
        conn = get_db_connection()
        try:
            return query_recovery_inputs(conn)
        finally:
            conn.close()

    @app.get("/api/health/metrics")
    async def list_metrics():
        """Return a list of all tracked metric names with sample counts."""
        conn = get_db_connection()
        try:
            rows = conn.execute(
                """SELECT metric_name, COUNT(*) as sample_count,
                          MIN(sample_date) as first_sample,
                          MAX(sample_date) as last_sample
                   FROM health_samples
                   GROUP BY metric_name
                   ORDER BY metric_name"""
            ).fetchall()
            return {"metrics": [dict(r) for r in rows]}
        finally:
            conn.close()

else:
    app = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# CLI query mode
# ---------------------------------------------------------------------------


def cli_query(query_type: str) -> None:
    """Execute a query and print results to stdout.

    Args:
        query_type: One of 'latest', 'sleep', 'trends', 'summary', 'recovery'.
    """
    db_path = get_db_path()
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        print("   Run: python3 health_webhook.py --init-db")
        sys.exit(1)

    conn = get_db_connection(db_path)

    try:
        if query_type == "latest":
            results = query_latest(conn)
            if not results:
                print("No health data recorded yet.")
                return
            print(f"\n{'Metric':<30} {'Value':>10} {'Unit':<10} {'Date':<20}")
            print("-" * 75)
            for r in results:
                name = r["metric_name"].replace("_", " ").title()
                print(f"{name:<30} {r['value']:>10.1f} {r['unit']:<10} {r['sample_date'][:16]}")

        elif query_type == "sleep":
            results = query_sleep(conn)
            if not results:
                print("No sleep data recorded yet.")
                return
            print(f"\n{'Metric':<25} {'Value':>10} {'Unit':<10} {'Date':<20}")
            print("-" * 70)
            for r in results:
                name = r["metric_name"].replace("_", " ").title()
                print(f"{name:<25} {r['value']:>10.1f} {r['unit']:<10} {r['sample_date'][:16]}")

        elif query_type == "trends":
            results = query_trends(conn, "heart_rate", 30)
            if not results or not results[0].get("summary"):
                print("Not enough data for trends yet.")
                return
            summary = results[0]["summary"]
            print(f"\n📊 {summary['metric'].replace('_', ' ').title()} — Last {summary['days']} Days")
            print(f"   Count: {summary['count']} readings")
            print(f"   Min:   {summary['min']}")
            print(f"   Max:   {summary['max']}")
            print(f"   Avg:   {summary['avg']}")
            print(f"   Latest: {summary['latest']}")

        elif query_type == "summary":
            result = query_summary(conn)
            print(result.get("text", result.get("message", "No data.")))

        elif query_type == "recovery":
            result = query_recovery_inputs(conn)
            print("\n🔄 Recovery Score Inputs")
            print("=" * 40)
            sleep = result.get("sleep_hours")
            hrv = result.get("hrv_ms")
            rhr = result.get("resting_hr_bpm")
            print(f"  Sleep:         {sleep:.1f} hours" if sleep else "  Sleep:         ⚠️  No data")
            print(f"  HRV:           {hrv:.0f} ms" if hrv else "  HRV:           ⚠️  No data")
            print(f"  Resting HR:    {rhr:.0f} bpm" if rhr else "  Resting HR:    ⚠️  No data")

            freshness = result.get("data_freshness", {})
            if freshness:
                print("\n  Data Freshness:")
                for key, info in freshness.items():
                    if isinstance(info, dict):
                        stale = " ⚠️ STALE" if info.get("stale") else " ✅"
                        print(f"    {key}: {info.get('age_hours', '?')}h ago{stale}")

        else:
            print(f"Unknown query type: {query_type}")
            print("Valid options: latest, sleep, trends, summary, recovery")
            sys.exit(1)

    finally:
        conn.close()

# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and dispatch."""
    parser = argparse.ArgumentParser(
        description="Health Webhook Receiver — receives and queries Apple Health data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Query examples:
  python3 health_webhook.py --query latest      # Most recent reading per metric
  python3 health_webhook.py --query sleep        # Recent sleep data
  python3 health_webhook.py --query trends       # 30-day heart rate trends
  python3 health_webhook.py --query summary      # Full human-readable summary
  python3 health_webhook.py --query recovery     # Recovery score inputs

Server examples:
  python3 health_webhook.py                      # Start on default port 8082
  python3 health_webhook.py --port 8083          # Custom port
        """,
    )

    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"Port to run the webhook server on (default: {DEFAULT_PORT})")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Host to bind the server to (default: 0.0.0.0)")
    parser.add_argument("--init-db", action="store_true",
                        help="Initialize the SQLite database and exit")
    parser.add_argument("--query", type=str, metavar="TYPE",
                        choices=["latest", "sleep", "trends", "summary", "recovery"],
                        help="Query mode: latest, sleep, trends, summary, recovery")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Init DB mode
    if args.init_db:
        init_db()
        print(f"✅ Database initialized at {get_db_path()}")
        return

    # Query mode
    if args.query:
        cli_query(args.query)
        return

    # Server mode
    if FastAPI is None or uvicorn is None:
        missing = []
        if FastAPI is None:
            missing.append("fastapi")
        if uvicorn is None:
            missing.append("uvicorn")
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print(f"   Install with: pip install {' '.join(missing)}")
        sys.exit(1)

    # Ensure DB exists before starting server
    init_db()

    log.info("Starting Health Webhook server on %s:%d", args.host, args.port)
    log.info("Database: %s", get_db_path())

    token = os.environ.get("HEALTH_WEBHOOK_TOKEN")
    if token:
        log.info("Auth: Bearer token configured (%d chars)", len(token))
    else:
        log.warning("Auth: HEALTH_WEBHOOK_TOKEN not set — webhook auth disabled!")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
