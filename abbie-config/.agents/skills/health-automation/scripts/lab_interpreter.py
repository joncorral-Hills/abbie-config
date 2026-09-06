#!/usr/bin/env python3
"""Lab Results Interpreter — parses lab PDFs and generates trend analysis.

Extracts lab values from PDF reports (or Notion), compares against normal and
optimal reference ranges, computes trends from historical data, and generates
actionable markdown reports.

Usage:
    python3 lab_interpreter.py --pdf /path/to/lab_results.pdf  # Parse PDF and interpret
    python3 lab_interpreter.py --interpret                      # Interpret latest from Notion
    python3 lab_interpreter.py --trends                         # Generate trend report
    python3 lab_interpreter.py --test-sample                    # Run with sample data

Environment Variables:
    NOTION_API_KEY   — Notion integration token (required for Notion queries)
"""

import os
import sys
import re
import json
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print("Installing requests…")
    os.system(f"{sys.executable} -m pip install requests")
    import requests

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
RESOURCES_DIR = SCRIPT_DIR.parent / "resources"
REFERENCE_RANGES_PATH = RESOURCES_DIR / "lab_reference_ranges.json"
NOTION_URL = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("lab_interpreter")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = RESOURCES_DIR / "hevy_config.json"


def load_config() -> dict:
    """Load the health-automation config."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

# ---------------------------------------------------------------------------
# Default reference ranges (used when lab_reference_ranges.json doesn't exist)
# ---------------------------------------------------------------------------

DEFAULT_REFERENCE_RANGES = {
    "glucose_fasting": {
        "display_name": "Glucose, Fasting",
        "unit": "mg/dL",
        "normal_low": 65,
        "normal_high": 99,
        "optimal_low": 72,
        "optimal_high": 86,
        "critical_low": 40,
        "critical_high": 400,
        "notes": "Optimal fasting glucose is below 86 mg/dL for metabolic health.",
    },
    "hemoglobin_a1c": {
        "display_name": "Hemoglobin A1c",
        "unit": "%",
        "normal_low": 4.0,
        "normal_high": 5.6,
        "optimal_low": 4.0,
        "optimal_high": 5.2,
        "critical_low": None,
        "critical_high": 10.0,
        "notes": "Target <5.2% for optimal metabolic health.",
    },
    "cholesterol_total": {
        "display_name": "Cholesterol, Total",
        "unit": "mg/dL",
        "normal_low": 125,
        "normal_high": 200,
        "optimal_low": 150,
        "optimal_high": 190,
        "critical_low": None,
        "critical_high": 300,
        "notes": "Total cholesterol alone is not a strong predictor — look at ratios.",
    },
    "ldl_cholesterol": {
        "display_name": "LDL Cholesterol",
        "unit": "mg/dL",
        "normal_low": 0,
        "normal_high": 130,
        "optimal_low": 0,
        "optimal_high": 100,
        "critical_low": None,
        "critical_high": 190,
        "notes": "Optimal <100; target <70 if cardiovascular risk factors.",
    },
    "hdl_cholesterol": {
        "display_name": "HDL Cholesterol",
        "unit": "mg/dL",
        "normal_low": 40,
        "normal_high": 200,
        "optimal_low": 50,
        "optimal_high": 200,
        "critical_low": 20,
        "critical_high": None,
        "notes": "Higher is better. Target >50 for men, >60 for women.",
    },
    "triglycerides": {
        "display_name": "Triglycerides",
        "unit": "mg/dL",
        "normal_low": 0,
        "normal_high": 150,
        "optimal_low": 0,
        "optimal_high": 80,
        "critical_low": None,
        "critical_high": 500,
        "notes": "Optimal <80. High triglycerides strongly linked to insulin resistance.",
    },
    "creatinine": {
        "display_name": "Creatinine",
        "unit": "mg/dL",
        "normal_low": 0.70,
        "normal_high": 1.33,
        "optimal_low": 0.80,
        "optimal_high": 1.10,
        "critical_low": None,
        "critical_high": 4.0,
        "notes": "Kidney function marker. Can be elevated with high muscle mass.",
    },
    "egfr": {
        "display_name": "eGFR",
        "unit": "mL/min/1.73m²",
        "normal_low": 60,
        "normal_high": 200,
        "optimal_low": 90,
        "optimal_high": 200,
        "critical_low": 15,
        "critical_high": None,
        "notes": "Higher is better. <60 indicates chronic kidney disease.",
    },
    "ast_sgot": {
        "display_name": "AST (SGOT)",
        "unit": "U/L",
        "normal_low": 10,
        "normal_high": 40,
        "optimal_low": 10,
        "optimal_high": 26,
        "critical_low": None,
        "critical_high": 200,
        "notes": "Liver enzyme. Can be elevated after intense exercise.",
    },
    "alt_sgpt": {
        "display_name": "ALT (SGPT)",
        "unit": "U/L",
        "normal_low": 7,
        "normal_high": 56,
        "optimal_low": 7,
        "optimal_high": 26,
        "critical_low": None,
        "critical_high": 200,
        "notes": "Liver enzyme. More specific to liver than AST.",
    },
    "tsh": {
        "display_name": "TSH",
        "unit": "mIU/L",
        "normal_low": 0.45,
        "normal_high": 4.5,
        "optimal_low": 0.5,
        "optimal_high": 2.5,
        "critical_low": 0.01,
        "critical_high": 10.0,
        "notes": "Thyroid-stimulating hormone. Optimal 0.5–2.5.",
    },
    "vitamin_d_25oh": {
        "display_name": "Vitamin D, 25-Hydroxy",
        "unit": "ng/mL",
        "normal_low": 30,
        "normal_high": 100,
        "optimal_low": 50,
        "optimal_high": 80,
        "critical_low": 10,
        "critical_high": 150,
        "notes": "Optimal 50–80 ng/mL. Most people are deficient.",
    },
    "testosterone_total": {
        "display_name": "Testosterone, Total",
        "unit": "ng/dL",
        "normal_low": 264,
        "normal_high": 916,
        "optimal_low": 500,
        "optimal_high": 900,
        "critical_low": 100,
        "critical_high": None,
        "notes": "Optimal >500 for men. Consider free T and SHBG too.",
    },
    "testosterone_free": {
        "display_name": "Testosterone, Free",
        "unit": "pg/mL",
        "normal_low": 5.0,
        "normal_high": 21.0,
        "optimal_low": 10.0,
        "optimal_high": 21.0,
        "critical_low": None,
        "critical_high": None,
        "notes": "Free T is the bioavailable fraction.",
    },
    "iron_serum": {
        "display_name": "Iron, Serum",
        "unit": "µg/dL",
        "normal_low": 38,
        "normal_high": 169,
        "optimal_low": 60,
        "optimal_high": 120,
        "critical_low": 20,
        "critical_high": 300,
        "notes": "Fluctuates daily. Interpret with ferritin and TIBC.",
    },
    "ferritin": {
        "display_name": "Ferritin",
        "unit": "ng/mL",
        "normal_low": 30,
        "normal_high": 400,
        "optimal_low": 50,
        "optimal_high": 150,
        "critical_low": 10,
        "critical_high": 1000,
        "notes": "Iron storage. Also an acute-phase reactant (elevated in inflammation).",
    },
    "vitamin_b12": {
        "display_name": "Vitamin B12",
        "unit": "pg/mL",
        "normal_low": 200,
        "normal_high": 1100,
        "optimal_low": 500,
        "optimal_high": 1000,
        "critical_low": 150,
        "critical_high": None,
        "notes": "Optimal >500. Deficiency causes fatigue and neurological symptoms.",
    },
    "folate": {
        "display_name": "Folate",
        "unit": "ng/mL",
        "normal_low": 3.0,
        "normal_high": 20.0,
        "optimal_low": 10.0,
        "optimal_high": 20.0,
        "critical_low": 2.0,
        "critical_high": None,
        "notes": "Important for DNA synthesis and methylation.",
    },
    "hsCRP": {
        "display_name": "hs-CRP",
        "unit": "mg/L",
        "normal_low": 0,
        "normal_high": 3.0,
        "optimal_low": 0,
        "optimal_high": 1.0,
        "critical_low": None,
        "critical_high": 10.0,
        "notes": "Inflammation marker. <1.0 is optimal for cardiovascular risk.",
    },
    "wbc": {
        "display_name": "White Blood Cell Count",
        "unit": "x10³/µL",
        "normal_low": 3.4,
        "normal_high": 10.8,
        "optimal_low": 4.0,
        "optimal_high": 7.0,
        "critical_low": 2.0,
        "critical_high": 30.0,
        "notes": "Immune function marker.",
    },
    "rbc": {
        "display_name": "Red Blood Cell Count",
        "unit": "x10⁶/µL",
        "normal_low": 4.14,
        "normal_high": 5.80,
        "optimal_low": 4.5,
        "optimal_high": 5.5,
        "critical_low": 3.0,
        "critical_high": 7.0,
        "notes": "Oxygen-carrying capacity.",
    },
    "hemoglobin": {
        "display_name": "Hemoglobin",
        "unit": "g/dL",
        "normal_low": 12.6,
        "normal_high": 17.7,
        "optimal_low": 14.0,
        "optimal_high": 17.0,
        "critical_low": 7.0,
        "critical_high": 20.0,
        "notes": "Oxygen transport protein in red blood cells.",
    },
    "hematocrit": {
        "display_name": "Hematocrit",
        "unit": "%",
        "normal_low": 37.5,
        "normal_high": 51.0,
        "optimal_low": 41.0,
        "optimal_high": 49.0,
        "critical_low": 25.0,
        "critical_high": 60.0,
        "notes": "Percentage of blood volume that is red blood cells.",
    },
    "platelets": {
        "display_name": "Platelets",
        "unit": "x10³/µL",
        "normal_low": 150,
        "normal_high": 379,
        "optimal_low": 175,
        "optimal_high": 300,
        "critical_low": 50,
        "critical_high": 600,
        "notes": "Blood clotting function.",
    },
    "uric_acid": {
        "display_name": "Uric Acid",
        "unit": "mg/dL",
        "normal_low": 2.4,
        "normal_high": 8.2,
        "optimal_low": 3.5,
        "optimal_high": 6.0,
        "critical_low": None,
        "critical_high": 12.0,
        "notes": "Elevated levels associated with gout and metabolic syndrome.",
    },
    "insulin_fasting": {
        "display_name": "Insulin, Fasting",
        "unit": "µIU/mL",
        "normal_low": 2.6,
        "normal_high": 24.9,
        "optimal_low": 2.6,
        "optimal_high": 8.0,
        "critical_low": None,
        "critical_high": 50.0,
        "notes": "Optimal <8 µIU/mL. Elevated fasting insulin = early insulin resistance.",
    },
    "homocysteine": {
        "display_name": "Homocysteine",
        "unit": "µmol/L",
        "normal_low": 0,
        "normal_high": 15.0,
        "optimal_low": 0,
        "optimal_high": 8.0,
        "critical_low": None,
        "critical_high": 50.0,
        "notes": "Cardiovascular risk marker. Optimal <8. Elevated by B12/folate deficiency.",
    },
}

# ---------------------------------------------------------------------------
# Marker name aliases — map PDF text variants to canonical keys
# ---------------------------------------------------------------------------

MARKER_ALIASES = {
    "glucose": "glucose_fasting",
    "glucose, fasting": "glucose_fasting",
    "fasting glucose": "glucose_fasting",
    "glucose fasting": "glucose_fasting",
    "hemoglobin a1c": "hemoglobin_a1c",
    "hba1c": "hemoglobin_a1c",
    "a1c": "hemoglobin_a1c",
    "cholesterol, total": "cholesterol_total",
    "total cholesterol": "cholesterol_total",
    "cholesterol total": "cholesterol_total",
    "ldl": "ldl_cholesterol",
    "ldl cholesterol": "ldl_cholesterol",
    "ldl-c": "ldl_cholesterol",
    "ldl cholesterol calc": "ldl_cholesterol",
    "hdl": "hdl_cholesterol",
    "hdl cholesterol": "hdl_cholesterol",
    "hdl-c": "hdl_cholesterol",
    "triglyceride": "triglycerides",
    "triglycerides": "triglycerides",
    "creatinine": "creatinine",
    "creatinine, serum": "creatinine",
    "egfr": "egfr",
    "egfr non-afr. american": "egfr",
    "gfr": "egfr",
    "glomerular filtration rate": "egfr",
    "ast": "ast_sgot",
    "ast (sgot)": "ast_sgot",
    "sgot": "ast_sgot",
    "aspartate aminotransferase": "ast_sgot",
    "alt": "alt_sgpt",
    "alt (sgpt)": "alt_sgpt",
    "sgpt": "alt_sgpt",
    "alanine aminotransferase": "alt_sgpt",
    "tsh": "tsh",
    "thyroid stimulating hormone": "tsh",
    "vitamin d": "vitamin_d_25oh",
    "vitamin d, 25-hydroxy": "vitamin_d_25oh",
    "25-hydroxy vitamin d": "vitamin_d_25oh",
    "25-oh vitamin d": "vitamin_d_25oh",
    "testosterone": "testosterone_total",
    "testosterone, total": "testosterone_total",
    "total testosterone": "testosterone_total",
    "testosterone, free": "testosterone_free",
    "free testosterone": "testosterone_free",
    "iron": "iron_serum",
    "iron, serum": "iron_serum",
    "serum iron": "iron_serum",
    "ferritin": "ferritin",
    "ferritin, serum": "ferritin",
    "vitamin b12": "vitamin_b12",
    "b12": "vitamin_b12",
    "cobalamin": "vitamin_b12",
    "folate": "folate",
    "folic acid": "folate",
    "hs-crp": "hsCRP",
    "hscrp": "hsCRP",
    "c-reactive protein": "hsCRP",
    "c-reactive protein, cardiac": "hsCRP",
    "crp, high sensitivity": "hsCRP",
    "wbc": "wbc",
    "white blood cell count": "wbc",
    "white blood cells": "wbc",
    "rbc": "rbc",
    "red blood cell count": "rbc",
    "red blood cells": "rbc",
    "hemoglobin": "hemoglobin",
    "hgb": "hemoglobin",
    "hematocrit": "hematocrit",
    "hct": "hematocrit",
    "platelets": "platelets",
    "platelet count": "platelets",
    "plt": "platelets",
    "uric acid": "uric_acid",
    "insulin": "insulin_fasting",
    "insulin, fasting": "insulin_fasting",
    "fasting insulin": "insulin_fasting",
    "homocysteine": "homocysteine",
}

# ---------------------------------------------------------------------------
# Reference range loading
# ---------------------------------------------------------------------------


def load_reference_ranges() -> dict:
    """Load reference ranges from JSON file, falling back to built-in defaults.

    Returns:
        Dict of marker_key → range dict.
    """
    if REFERENCE_RANGES_PATH.exists():
        try:
            with open(REFERENCE_RANGES_PATH, "r") as f:
                data = json.load(f)
            log.info("Loaded reference ranges from %s (%d markers)", REFERENCE_RANGES_PATH, len(data))
            return data
        except (json.JSONDecodeError, IOError) as exc:
            log.warning("Could not read reference ranges: %s — using defaults", exc)

    log.info("Using built-in default reference ranges (%d markers)", len(DEFAULT_REFERENCE_RANGES))
    return DEFAULT_REFERENCE_RANGES


def save_default_reference_ranges() -> None:
    """Write the default reference ranges to disk for user customization."""
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    with open(REFERENCE_RANGES_PATH, "w") as f:
        json.dump(DEFAULT_REFERENCE_RANGES, f, indent=2)
    log.info("Saved default reference ranges to %s", REFERENCE_RANGES_PATH)

# ---------------------------------------------------------------------------
# PDF parsing
# ---------------------------------------------------------------------------


def normalize_marker_name(raw_name: str) -> Optional[str]:
    """Normalize a raw marker name from a PDF to a canonical key.

    Returns:
        Canonical key or None if unrecognized.
    """
    cleaned = raw_name.strip().lower()
    # Remove trailing commas, colons, special chars
    cleaned = re.sub(r'[:\*#]+$', '', cleaned).strip()

    # Direct lookup
    if cleaned in MARKER_ALIASES:
        return MARKER_ALIASES[cleaned]

    # Try without common suffixes
    for suffix in [", serum", " serum", ", plasma", " plasma", " level",
                   " test", " blood", ", blood"]:
        trimmed = cleaned.replace(suffix, "").strip()
        if trimmed in MARKER_ALIASES:
            return MARKER_ALIASES[trimmed]

    # Try snake_case conversion
    snake = re.sub(r'[\s,\-/]+', '_', cleaned).strip('_')
    if snake in DEFAULT_REFERENCE_RANGES:
        return snake

    return None


def parse_lab_pdf(filepath: str) -> list[dict]:
    """Parse lab values from a PDF report using pdfplumber.

    Supports common lab report formats with patterns like:
    - ``Glucose, Fasting  95  mg/dL  65-99``
    - ``CHOLESTEROL, TOTAL    195    mg/dL    125 - 200``

    Args:
        filepath: Path to the PDF file.

    Returns:
        List of dicts with keys: marker_name, canonical_key, value, unit,
        range_low, range_high, raw_line.
    """
    if pdfplumber is None:
        log.error("pdfplumber is required for PDF parsing.")
        print("❌ pdfplumber not installed.")
        print("   Install with: pip install pdfplumber")
        sys.exit(1)

    filepath = os.path.expanduser(filepath)
    if not os.path.exists(filepath):
        log.error("PDF file not found: %s", filepath)
        sys.exit(1)

    log.info("Parsing PDF: %s", filepath)
    results: list[dict] = []

    # Regex patterns for lab value extraction
    # Pattern 1: Marker  Value  Unit  Low-High
    patterns = [
        # "Glucose, Fasting    95    mg/dL    65-99"
        re.compile(
            r'^(.+?)\s{2,}(\d+\.?\d*)\s+([a-zA-Z/%µ·³⁶²¹⁰\s]+?)\s+'
            r'(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)',
            re.IGNORECASE,
        ),
        # "CHOLESTEROL, TOTAL    195 mg/dL    125 - 200"
        re.compile(
            r'^(.+?)\s{2,}(\d+\.?\d*)\s+([a-zA-Z/%µ·³⁶²¹⁰\s]+?)\s+'
            r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',
            re.IGNORECASE,
        ),
        # Tabular: "Marker | Value | Unit | Range" (pipe-separated)
        re.compile(
            r'^(.+?)\s*\|\s*(\d+\.?\d*)\s*\|\s*([a-zA-Z/%µ·³⁶²¹⁰\s]+?)\s*\|\s*'
            r'(\d+\.?\d*)\s*[-–]\s*(\d+\.?\d*)',
            re.IGNORECASE,
        ),
        # "Marker    Value    Range (Low - High)"
        re.compile(
            r'^(.+?)\s{2,}(\d+\.?\d*)\s{2,}(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)',
            re.IGNORECASE,
        ),
    ]

    # Pattern for values with H/L flags: "Glucose  105 H  mg/dL  65-99"
    flag_pattern = re.compile(
        r'^(.+?)\s{2,}(\d+\.?\d*)\s*([HL])\s+([a-zA-Z/%µ·³⁶²¹⁰\s]+?)\s+'
        r'(\d+\.?\d*)\s*[-–—]\s*(\d+\.?\d*)',
        re.IGNORECASE,
    )

    with pdfplumber.open(filepath) as pdf:
        for page_num, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                line = line.strip()
                if not line or len(line) < 5:
                    continue

                # Try flag pattern first
                m = flag_pattern.match(line)
                if m:
                    marker_raw = m.group(1).strip()
                    value = float(m.group(2))
                    # flag = m.group(3)  # H or L
                    unit = m.group(4).strip()
                    range_low = float(m.group(5))
                    range_high = float(m.group(6))

                    canonical = normalize_marker_name(marker_raw)
                    results.append({
                        "marker_name": marker_raw,
                        "canonical_key": canonical,
                        "value": value,
                        "unit": unit,
                        "range_low": range_low,
                        "range_high": range_high,
                        "raw_line": line,
                        "page": page_num,
                    })
                    continue

                # Try standard patterns
                for pattern in patterns:
                    m = pattern.match(line)
                    if m:
                        groups = m.groups()
                        marker_raw = groups[0].strip()

                        if len(groups) == 5:
                            value = float(groups[1])
                            unit = groups[2].strip()
                            range_low = float(groups[3])
                            range_high = float(groups[4])
                        elif len(groups) == 4:
                            # No unit in pattern
                            value = float(groups[1])
                            unit = ""
                            range_low = float(groups[2])
                            range_high = float(groups[3])
                        else:
                            continue

                        canonical = normalize_marker_name(marker_raw)
                        results.append({
                            "marker_name": marker_raw,
                            "canonical_key": canonical,
                            "value": value,
                            "unit": unit,
                            "range_low": range_low,
                            "range_high": range_high,
                            "raw_line": line,
                            "page": page_num,
                        })
                        break  # Use first matching pattern

    log.info("Extracted %d lab values from PDF", len(results))
    recognized = sum(1 for r in results if r["canonical_key"])
    log.info("  Recognized: %d, Unrecognized: %d", recognized, len(results) - recognized)

    return results

# ---------------------------------------------------------------------------
# Value interpretation
# ---------------------------------------------------------------------------


def interpret_value(marker_name: str, value: float,
                    reference_ranges: dict) -> dict:
    """Compare a lab value against normal and optimal reference ranges.

    Args:
        marker_name: Canonical marker key.
        value: Measured value.
        reference_ranges: Dict of marker_key → range dict.

    Returns:
        Dict with: status, emoji, direction, notes, range info.
    """
    ranges = reference_ranges.get(marker_name)
    if not ranges:
        return {
            "status": "unknown",
            "emoji": "❓",
            "direction": "",
            "notes": f"No reference range found for '{marker_name}'.",
            "display_name": marker_name.replace("_", " ").title(),
        }

    display_name = ranges.get("display_name", marker_name.replace("_", " ").title())
    normal_low = ranges.get("normal_low")
    normal_high = ranges.get("normal_high")
    optimal_low = ranges.get("optimal_low")
    optimal_high = ranges.get("optimal_high")
    critical_low = ranges.get("critical_low")
    critical_high = ranges.get("critical_high")
    marker_notes = ranges.get("notes", "")

    result = {
        "display_name": display_name,
        "value": value,
        "unit": ranges.get("unit", ""),
        "normal_range": f"{normal_low}–{normal_high}" if normal_low is not None else "",
        "optimal_range": f"{optimal_low}–{optimal_high}" if optimal_low is not None else "",
        "notes": marker_notes,
    }

    # Check critical
    if critical_low is not None and value < critical_low:
        result["status"] = "critical_low"
        result["emoji"] = "🔴"
        result["direction"] = "⬇️"
        result["notes"] = f"CRITICALLY LOW. {marker_notes}"
        return result

    if critical_high is not None and value > critical_high:
        result["status"] = "critical_high"
        result["emoji"] = "🔴"
        result["direction"] = "⬆️"
        result["notes"] = f"CRITICALLY HIGH. {marker_notes}"
        return result

    # Check normal range
    in_normal = True
    if normal_low is not None and value < normal_low:
        in_normal = False
        result["status"] = "out_of_range_low"
        result["emoji"] = "🔴"
        result["direction"] = "⬇️"
    elif normal_high is not None and value > normal_high:
        in_normal = False
        result["status"] = "out_of_range_high"
        result["emoji"] = "🔴"
        result["direction"] = "⬆️"

    if not in_normal:
        return result

    # Check optimal range
    if optimal_low is not None and optimal_high is not None:
        if optimal_low <= value <= optimal_high:
            result["status"] = "optimal"
            result["emoji"] = "🟢"
            result["direction"] = "✅"
        elif value < optimal_low:
            result["status"] = "borderline_low"
            result["emoji"] = "🟡"
            result["direction"] = "↓"
            result["notes"] = f"In normal range but below optimal ({optimal_low}–{optimal_high}). {marker_notes}"
        else:
            result["status"] = "borderline_high"
            result["emoji"] = "🟡"
            result["direction"] = "↑"
            result["notes"] = f"In normal range but above optimal ({optimal_low}–{optimal_high}). {marker_notes}"
    else:
        result["status"] = "normal"
        result["emoji"] = "🟢"
        result["direction"] = "✅"

    return result

# ---------------------------------------------------------------------------
# Notion integration
# ---------------------------------------------------------------------------


def _notion_headers() -> dict:
    key = os.environ.get("NOTION_API_KEY")
    if not key:
        log.error("NOTION_API_KEY not set")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def query_prior_results(marker_name: str, db_id: Optional[str] = None) -> list[dict]:
    """Query Notion Lab Results DB for historical values of a marker.

    Args:
        marker_name: Canonical marker key.
        db_id: Notion database ID. If None, read from config.

    Returns:
        List of dicts with keys: value, date, notes — sorted by date descending.
    """
    if not db_id:
        config = load_config()
        db_id = config.get("lab_results_db_id")
        if not db_id:
            log.warning("lab_results_db_id not configured — no historical data available")
            return []

    try:
        body = {
            "filter": {
                "property": "Marker",
                "rich_text": {"equals": marker_name},
            },
            "sorts": [{"property": "Date", "direction": "descending"}],
        }
        resp = requests.post(
            f"{NOTION_URL}/databases/{db_id}/query",
            headers=_notion_headers(),
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        results = []
        for page in data.get("results", []):
            props = page.get("properties", {})
            value_prop = props.get("Value", {})
            date_prop = props.get("Date", {})

            value = value_prop.get("number")
            date_info = date_prop.get("date", {})
            date_str = date_info.get("start", "") if date_info else ""

            if value is not None:
                results.append({
                    "value": value,
                    "date": date_str,
                    "page_id": page.get("id"),
                })

        return results

    except requests.RequestException as exc:
        log.warning("Failed to query Notion for %s: %s", marker_name, exc)
        return []

# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------


def calculate_trend(current_value: float,
                    prior_values: list[dict]) -> dict:
    """Compute trend metrics from current and historical values.

    Args:
        current_value: Current lab value.
        prior_values: List of dicts with 'value' and 'date' keys, sorted by
                      date descending.

    Returns:
        Dict with: pct_change, direction, direction_emoji, slope, data_points, interpretation.
    """
    result = {
        "current": current_value,
        "data_points": len(prior_values) + 1,  # including current
        "pct_change": None,
        "direction": "→",
        "direction_emoji": "➡️",
        "slope": None,
        "interpretation": "Insufficient data for trend analysis.",
    }

    if not prior_values:
        return result

    # Percent change from last result
    last_value = prior_values[0]["value"]
    if last_value != 0:
        pct_change = round(((current_value - last_value) / abs(last_value)) * 100, 1)
        result["pct_change"] = pct_change
        result["previous"] = last_value
        result["previous_date"] = prior_values[0].get("date", "")

        if pct_change > 5:
            result["direction"] = "↑"
            result["direction_emoji"] = "⬆️"
        elif pct_change < -5:
            result["direction"] = "↓"
            result["direction_emoji"] = "⬇️"
        else:
            result["direction"] = "→"
            result["direction_emoji"] = "➡️"

    # Slope over last 3+ results
    if len(prior_values) >= 2:
        # Build chronological list (oldest first)
        values = [p["value"] for p in reversed(prior_values)] + [current_value]
        n = len(values)

        # Simple linear regression slope
        x_vals = list(range(n))
        x_mean = sum(x_vals) / n
        y_mean = sum(values) / n

        numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, values))
        denominator = sum((x - x_mean) ** 2 for x in x_vals)

        if denominator != 0:
            slope = round(numerator / denominator, 2)
            result["slope"] = slope

            if slope > 1:
                result["interpretation"] = "📈 Trending upward significantly."
            elif slope > 0.2:
                result["interpretation"] = "↗️ Slight upward trend."
            elif slope < -1:
                result["interpretation"] = "📉 Trending downward significantly."
            elif slope < -0.2:
                result["interpretation"] = "↘️ Slight downward trend."
            else:
                result["interpretation"] = "➡️ Stable — no significant trend."
    elif result["pct_change"] is not None:
        pct = result["pct_change"]
        if abs(pct) < 3:
            result["interpretation"] = "Stable compared to last result."
        elif pct > 0:
            result["interpretation"] = f"Increased {pct}% since last result."
        else:
            result["interpretation"] = f"Decreased {abs(pct)}% since last result."

    return result

# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(results: list[dict], reference_ranges: dict,
                    report_date: Optional[str] = None) -> str:
    """Format the full interpretation report as a markdown string.

    Args:
        results: List of parsed lab value dicts (from parse_lab_pdf or manual input).
        reference_ranges: Loaded reference ranges.
        report_date: Optional date string for the report header.

    Returns:
        Markdown-formatted report string.
    """
    if not report_date:
        report_date = datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"# 🔬 Lab Results Interpretation — {report_date}",
        "",
        f"**Markers analyzed:** {len(results)}",
        "",
    ]

    # Categorize results
    optimal_list: list[dict] = []
    borderline_list: list[dict] = []
    out_of_range_list: list[dict] = []
    unknown_list: list[dict] = []

    for r in results:
        canonical = r.get("canonical_key")
        value = r.get("value")

        if canonical is None or value is None:
            unknown_list.append(r)
            continue

        interp = interpret_value(canonical, value, reference_ranges)
        r["interpretation"] = interp

        status = interp.get("status", "unknown")
        if status in ("optimal", "normal"):
            optimal_list.append(r)
        elif status.startswith("borderline"):
            borderline_list.append(r)
        elif status.startswith("out_of_range") or status.startswith("critical"):
            out_of_range_list.append(r)
        else:
            unknown_list.append(r)

    # Summary counts
    lines.append("## 📊 Summary")
    lines.append("")
    lines.append(f"| Status | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| 🟢 Optimal/Normal | {len(optimal_list)} |")
    lines.append(f"| 🟡 Borderline | {len(borderline_list)} |")
    lines.append(f"| 🔴 Out of Range | {len(out_of_range_list)} |")
    lines.append(f"| ❓ Unrecognized | {len(unknown_list)} |")
    lines.append("")

    # Detailed results table
    lines.append("## 📋 Detailed Results")
    lines.append("")
    lines.append("| Status | Marker | Value | Unit | Normal Range | Optimal Range | Notes |")
    lines.append("|--------|--------|-------|------|-------------|---------------|-------|")

    # Show out-of-range first, then borderline, then optimal
    all_interpreted = out_of_range_list + borderline_list + optimal_list
    for r in all_interpreted:
        interp = r.get("interpretation", {})
        emoji = interp.get("emoji", "❓")
        display = interp.get("display_name", r.get("marker_name", "?"))
        value = r.get("value", "?")
        unit = interp.get("unit", r.get("unit", ""))
        normal = interp.get("normal_range", "")
        optimal = interp.get("optimal_range", "")
        notes = interp.get("notes", "")
        # Escape pipe characters in notes
        notes = notes.replace("|", "\\|")
        lines.append(f"| {emoji} | {display} | {value} | {unit} | {normal} | {optimal} | {notes} |")

    # Unrecognized markers
    if unknown_list:
        lines.append("")
        lines.append("## ❓ Unrecognized Markers")
        lines.append("")
        lines.append("These markers were extracted from the PDF but couldn't be matched to known reference ranges:")
        lines.append("")
        for r in unknown_list:
            name = r.get("marker_name", "?")
            value = r.get("value", "?")
            unit = r.get("unit", "")
            lines.append(f"- **{name}**: {value} {unit}")

    # Action items
    if out_of_range_list or borderline_list:
        lines.append("")
        lines.append("## ⚡ Action Items")
        lines.append("")

        if out_of_range_list:
            lines.append("### 🔴 Requires Attention")
            lines.append("")
            for r in out_of_range_list:
                interp = r.get("interpretation", {})
                display = interp.get("display_name", r.get("marker_name", "?"))
                value = r.get("value", "?")
                unit = interp.get("unit", "")
                notes = interp.get("notes", "")
                direction = interp.get("direction", "")
                lines.append(f"- {direction} **{display}** = {value} {unit} — {notes}")

        if borderline_list:
            lines.append("")
            lines.append("### 🟡 Monitor / Optimize")
            lines.append("")
            for r in borderline_list:
                interp = r.get("interpretation", {})
                display = interp.get("display_name", r.get("marker_name", "?"))
                value = r.get("value", "?")
                unit = interp.get("unit", "")
                notes = interp.get("notes", "")
                lines.append(f"- **{display}** = {value} {unit} — {notes}")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by lab_interpreter.py on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Trend report
# ---------------------------------------------------------------------------


def generate_trend_report(reference_ranges: dict) -> str:
    """Query all markers with 2+ historical results and compute trends.

    Args:
        reference_ranges: Loaded reference ranges.

    Returns:
        Markdown-formatted trend report.
    """
    config = load_config()
    db_id = config.get("lab_results_db_id")

    if not db_id:
        return "❌ lab_results_db_id not configured — cannot generate trend report."

    log.info("Generating trend report…")

    lines = [
        "# 📈 Lab Results Trend Report",
        f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
    ]

    markers_with_trends: list[dict] = []
    concerning: list[dict] = []

    for marker_key, ranges in reference_ranges.items():
        prior = query_prior_results(marker_key, db_id)
        if len(prior) < 2:
            continue

        current_value = prior[0]["value"]
        historical = prior[1:]  # Exclude the most recent (it's "current")

        trend = calculate_trend(current_value, historical)
        trend["marker_key"] = marker_key
        trend["display_name"] = ranges.get("display_name", marker_key.replace("_", " ").title())
        trend["unit"] = ranges.get("unit", "")
        markers_with_trends.append(trend)

        # Check if the trend is concerning
        interp = interpret_value(marker_key, current_value, reference_ranges)
        if interp.get("status", "").startswith(("out_of_range", "critical")):
            concerning.append({**trend, "interpretation": interp})

    if not markers_with_trends:
        lines.append("Not enough historical data for trend analysis. Need at least 2 results per marker.")
        return "\n".join(lines)

    # Trend table
    lines.append(f"**Markers with trend data:** {len(markers_with_trends)}")
    lines.append("")
    lines.append("| Trend | Marker | Current | Previous | Change | Data Points | Interpretation |")
    lines.append("|-------|--------|---------|----------|--------|-------------|----------------|")

    for t in sorted(markers_with_trends, key=lambda x: abs(x.get("pct_change") or 0), reverse=True):
        emoji = t.get("direction_emoji", "➡️")
        name = t.get("display_name", "?")
        current = t.get("current", "?")
        prev = t.get("previous", "?")
        pct = t.get("pct_change")
        pct_str = f"{pct:+.1f}%" if pct is not None else "—"
        dp = t.get("data_points", "?")
        interp = t.get("interpretation", "")
        lines.append(f"| {emoji} | {name} | {current} | {prev} | {pct_str} | {dp} | {interp} |")

    # Concerning trends
    if concerning:
        lines.append("")
        lines.append("## ⚠️ Concerning Patterns")
        lines.append("")
        for c in concerning:
            name = c.get("display_name", "?")
            current = c.get("current", "?")
            unit = c.get("unit", "")
            pct = c.get("pct_change")
            direction = c.get("direction_emoji", "")
            interp_status = c.get("interpretation", {}).get("status", "")
            lines.append(f"- {direction} **{name}**: {current} {unit}"
                         f" ({'+' if pct and pct > 0 else ''}{pct}% change)"
                         f" — Status: {interp_status}")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by lab_interpreter.py on {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Test with sample data
# ---------------------------------------------------------------------------

SAMPLE_DATA = [
    {"marker_name": "Glucose, Fasting", "canonical_key": "glucose_fasting", "value": 95, "unit": "mg/dL", "range_low": 65, "range_high": 99},
    {"marker_name": "Hemoglobin A1c", "canonical_key": "hemoglobin_a1c", "value": 5.3, "unit": "%", "range_low": 4.0, "range_high": 5.6},
    {"marker_name": "Cholesterol, Total", "canonical_key": "cholesterol_total", "value": 215, "unit": "mg/dL", "range_low": 125, "range_high": 200},
    {"marker_name": "LDL Cholesterol", "canonical_key": "ldl_cholesterol", "value": 135, "unit": "mg/dL", "range_low": 0, "range_high": 130},
    {"marker_name": "HDL Cholesterol", "canonical_key": "hdl_cholesterol", "value": 55, "unit": "mg/dL", "range_low": 40, "range_high": 200},
    {"marker_name": "Triglycerides", "canonical_key": "triglycerides", "value": 110, "unit": "mg/dL", "range_low": 0, "range_high": 150},
    {"marker_name": "TSH", "canonical_key": "tsh", "value": 1.8, "unit": "mIU/L", "range_low": 0.45, "range_high": 4.5},
    {"marker_name": "Vitamin D, 25-Hydroxy", "canonical_key": "vitamin_d_25oh", "value": 38, "unit": "ng/mL", "range_low": 30, "range_high": 100},
    {"marker_name": "Testosterone, Total", "canonical_key": "testosterone_total", "value": 485, "unit": "ng/dL", "range_low": 264, "range_high": 916},
    {"marker_name": "hs-CRP", "canonical_key": "hsCRP", "value": 0.8, "unit": "mg/L", "range_low": 0, "range_high": 3.0},
    {"marker_name": "Ferritin", "canonical_key": "ferritin", "value": 95, "unit": "ng/mL", "range_low": 30, "range_high": 400},
    {"marker_name": "Vitamin B12", "canonical_key": "vitamin_b12", "value": 420, "unit": "pg/mL", "range_low": 200, "range_high": 1100},
    {"marker_name": "AST (SGOT)", "canonical_key": "ast_sgot", "value": 22, "unit": "U/L", "range_low": 10, "range_high": 40},
    {"marker_name": "ALT (SGPT)", "canonical_key": "alt_sgpt", "value": 18, "unit": "U/L", "range_low": 7, "range_high": 56},
    {"marker_name": "Hemoglobin", "canonical_key": "hemoglobin", "value": 15.2, "unit": "g/dL", "range_low": 12.6, "range_high": 17.7},
    {"marker_name": "White Blood Cell Count", "canonical_key": "wbc", "value": 5.8, "unit": "x10³/µL", "range_low": 3.4, "range_high": 10.8},
    {"marker_name": "Insulin, Fasting", "canonical_key": "insulin_fasting", "value": 12, "unit": "µIU/mL", "range_low": 2.6, "range_high": 24.9},
]


def test_with_sample() -> None:
    """Run the interpreter with hardcoded sample data to verify logic."""
    log.info("Running with sample data (%d markers)…", len(SAMPLE_DATA))

    reference_ranges = load_reference_ranges()
    report = generate_report(SAMPLE_DATA, reference_ranges, report_date="2026-06-10 (Sample)")

    print(report)
    print()

    # Test individual interpretations
    log.info("Individual interpretation tests:")
    test_cases = [
        ("glucose_fasting", 95, "Should be borderline_high (normal but above optimal 86)"),
        ("cholesterol_total", 215, "Should be out_of_range_high (>200)"),
        ("tsh", 1.8, "Should be optimal"),
        ("vitamin_d_25oh", 38, "Should be borderline_low (normal but below optimal 50)"),
        ("testosterone_total", 485, "Should be borderline_low (normal but below optimal 500)"),
    ]

    for marker, value, expected in test_cases:
        interp = interpret_value(marker, value, reference_ranges)
        status = interp.get("status", "?")
        emoji = interp.get("emoji", "?")
        log.info("  %s %s = %s → %s (%s) — Expected: %s",
                 emoji, marker, value, status, interp.get("direction", ""), expected)

    # Test trend calculation
    log.info("\nTrend calculation tests:")
    prior = [
        {"value": 210, "date": "2026-03-15"},
        {"value": 205, "date": "2025-12-10"},
        {"value": 198, "date": "2025-06-20"},
    ]
    trend = calculate_trend(215, prior)
    log.info("  Cholesterol trend: %s (slope: %s, change: %s%%)",
             trend["interpretation"], trend.get("slope"), trend.get("pct_change"))

    log.info("\n✅ Sample test complete!")

# ---------------------------------------------------------------------------
# Notion-based interpretation
# ---------------------------------------------------------------------------


def interpret_from_notion() -> None:
    """Query the latest Lab Results from Notion and generate interpretation."""
    config = load_config()
    db_id = config.get("lab_results_db_id")

    if not db_id:
        log.error("lab_results_db_id not configured.")
        print("❌ Set lab_results_db_id in resources/hevy_config.json")
        sys.exit(1)

    log.info("Querying latest lab results from Notion…")
    reference_ranges = load_reference_ranges()

    try:
        body = {
            "sorts": [{"property": "Date", "direction": "descending"}],
            "page_size": 50,
        }
        resp = requests.post(
            f"{NOTION_URL}/databases/{db_id}/query",
            headers=_notion_headers(),
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        results: list[dict] = []
        latest_date = None

        for page in data.get("results", []):
            props = page.get("properties", {})
            marker_prop = props.get("Marker", {})
            value_prop = props.get("Value", {})
            unit_prop = props.get("Unit", {})
            date_prop = props.get("Date", {})

            # Extract marker name
            marker_texts = marker_prop.get("rich_text", []) or marker_prop.get("title", [])
            marker_name = marker_texts[0]["text"]["content"] if marker_texts else None

            value = value_prop.get("number")
            unit_texts = unit_prop.get("rich_text", [])
            unit = unit_texts[0]["text"]["content"] if unit_texts else ""
            date_info = date_prop.get("date", {})
            date_str = date_info.get("start", "") if date_info else ""

            if marker_name is None or value is None:
                continue

            # Only include results from the most recent date
            if latest_date is None:
                latest_date = date_str[:10]
            elif date_str[:10] != latest_date:
                break  # We've moved past the latest date

            canonical = normalize_marker_name(marker_name)
            results.append({
                "marker_name": marker_name,
                "canonical_key": canonical,
                "value": value,
                "unit": unit,
            })

        if not results:
            print("No lab results found in Notion.")
            return

        log.info("Found %d markers from %s", len(results), latest_date)
        report = generate_report(results, reference_ranges, report_date=latest_date)
        print(report)

    except requests.RequestException as exc:
        log.error("Failed to query Notion: %s", exc)
        sys.exit(1)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse CLI arguments and dispatch."""
    parser = argparse.ArgumentParser(
        description="Lab Results Interpreter — parses PDFs and generates trend analysis.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 lab_interpreter.py --pdf /path/to/labs.pdf    # Parse and interpret a PDF
  python3 lab_interpreter.py --interpret                 # Interpret latest from Notion
  python3 lab_interpreter.py --trends                    # Generate trend report
  python3 lab_interpreter.py --test-sample               # Run with sample data
  python3 lab_interpreter.py --save-defaults             # Save default reference ranges
        """,
    )

    parser.add_argument("--pdf", type=str, metavar="PATH",
                        help="Path to a lab results PDF to parse and interpret")
    parser.add_argument("--interpret", action="store_true",
                        help="Interpret the latest lab results from Notion")
    parser.add_argument("--trends", action="store_true",
                        help="Generate a trend report for all tracked markers")
    parser.add_argument("--test-sample", action="store_true",
                        help="Run with hardcoded sample data")
    parser.add_argument("--save-defaults", action="store_true",
                        help="Save default reference ranges to JSON for customization")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Dispatch
    if args.save_defaults:
        save_default_reference_ranges()
        print(f"✅ Default reference ranges saved to {REFERENCE_RANGES_PATH}")
        return

    if args.test_sample:
        test_with_sample()
        return

    if args.pdf:
        reference_ranges = load_reference_ranges()
        results = parse_lab_pdf(args.pdf)
        if not results:
            print("❌ No lab values extracted from the PDF.")
            print("   Check the PDF format — the parser expects tabular lab results.")
            sys.exit(1)
        report = generate_report(results, reference_ranges)
        print(report)
        return

    if args.interpret:
        interpret_from_notion()
        return

    if args.trends:
        reference_ranges = load_reference_ranges()
        report = generate_trend_report(reference_ranges)
        print(report)
        return

    # No flags — show help
    parser.print_help()


if __name__ == "__main__":
    main()
