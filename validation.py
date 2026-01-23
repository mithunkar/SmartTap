# validation.py
from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd

def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Return a validation report (warnings/errors) for payload.data.records."""
    spec = payload.get("spec", {})
    records = (payload.get("data") or {}).get("records") or []
    report = {
        "ok": True,
        "errors": [],
        "warnings": [],
        "summary": {},
        "location": spec.get("location"),
        "variables": spec.get("variables"),
        "start_date": spec.get("start_date"),
        "end_date": spec.get("end_date"),
    }

    if not records:
        report["ok"] = False
        report["errors"].append("No records returned.")
        return report

    df = pd.DataFrame(records)
    if "datetime" not in df.columns:
        report["ok"] = False
        report["errors"].append("Missing 'datetime' column in records.")
        return report

    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    bad_dt = df["datetime"].isna().sum()
    if bad_dt:
        report["warnings"].append(f"{bad_dt} rows have invalid datetime.")

    # missingness + ranges
    numeric_cols = [c for c in df.columns if c != "datetime"]
    miss = df[numeric_cols].isna().mean().to_dict() if numeric_cols else {}
    report["summary"]["missing_fraction"] = miss
    report["summary"]["row_count"] = len(df)

    # simple plausibility checks (edit ranges as needed)
    ranges = {
        "MX": (-40, 130),
        "MN": (-60, 120),
        "OBM": (-50, 125),
        "PC": (0, 500),   # mm/day
        "SR": (0, 2000),  # langleys/day (loose)
        "WS": (0, 150),   # mph (loose)
        "ET": (0, 25),    # mm/day (loose)
    }
    for col in numeric_cols:
        if col in ranges:
            lo, hi = ranges[col]
            bad = df[(df[col] < lo) | (df[col] > hi)][col].count()
            if bad:
                report["warnings"].append(f"{col}: {bad} values outside [{lo},{hi}]")

    report["ok"] = (len(report["errors"]) == 0)
    return report

def validate_and_fix_spec(spec: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    """
    Validate + repair the LLM output spec.
    Ensures dataset/location/variables/start_date/end_date are not None.
    Tries to infer variables from the user query if missing.
    """
    fixed = dict(spec or {})

    # Required defaults
    if not fixed.get("task"):
        fixed["task"] = "visualize_timeseries"

    if not fixed.get("dataset"):
        fixed["dataset"] = "agrimet"

    if not fixed.get("location"):
        fixed["location"] = "corvallis"

    if not fixed.get("chart_type"):
        fixed["chart_type"] = "line"

    if not fixed.get("interval"):
        fixed["interval"] = "daily"

    # Infer variables if missing/None/empty
    vars_ = fixed.get("variables")
    if not isinstance(vars_, list) or len(vars_) == 0:
        q = (user_query or "").lower()

        inferred: List[str] = []

        # Temperature intents
        if "max" in q and "temp" in q:
            inferred.append("MX")
        if ("min" in q and "temp" in q) or ("low" in q and "temp" in q):
            inferred.append("MN")
        if "average" in q or "avg" in q or "mean" in q:
            if "temp" in q:
                inferred.append("OBM")
        # If user just says "temperature"
        if "temp" in q or "temperature" in q:
            if not inferred:
                inferred.append("OBM")

        # Other variables
        if "rain" in q or "rainfall" in q or "precip" in q:
            inferred.append("PC")
        if "solar" in q or "sun" in q or "radiation" in q:
            inferred.append("SR")
        if "wind" in q:
            inferred.append("WS")
        if "humidity" in q:
            inferred.append("TU")
        if "et" in q or "evapotranspiration" in q:
            inferred.append("ET")
            fixed["dataset"] = "openet"  # follow your rule

        # If still empty → throw error instead of silently failing
        if not inferred:
            return {
                "task": "error",
                "error_message": "Could not infer variables from query. Try: 'max temperature', 'rainfall', 'solar radiation', etc."
            }

        # Deduplicate while preserving order
        seen = set()
        inferred = [v for v in inferred if not (v in seen or seen.add(v))]
        fixed["variables"] = inferred

    # If dates missing, fail early (better than plotting wrong range)
    if not fixed.get("start_date") or not fixed.get("end_date"):
        return {
            "task": "error",
            "error_message": "Missing date range. Please specify a month/year or start and end dates (e.g., 'July 2017' or '2017-07-01 to 2017-07-31')."
        }

    return fixed
