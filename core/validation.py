from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List

import pandas as pd


SUPPORTED_TASKS = {"visualize_timeseries", "statistical_summary", "summarize_crops"}
OPENET_VARIABLES = {
    "ETa",
    "PPT",
    "P_rz",
    "AW",
    "WS_C",
    "AREA",
    "ACRES_FTR_GEOM",
    "CROP",
    "IRR_STATUS",
    "per_IRRIGATED",
    "IRR_EFF",
    "ITYPE",
}


def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
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
    invalid = int(df["datetime"].isna().sum())
    if invalid:
        report["warnings"].append(f"{invalid} rows have invalid datetime values.")

    numeric_cols = [column for column in df.columns if column != "datetime"]
    report["summary"]["row_count"] = len(df)
    report["summary"]["missing_fraction"] = (
        df[numeric_cols].isna().mean().to_dict() if numeric_cols else {}
    )
    report["ok"] = not report["errors"]
    return report


def _infer_task(spec: Dict[str, Any], user_query: str) -> str:
    if spec.get("task"):
        return spec["task"]
    lowered = (user_query or "").lower()
    if "what crops" in lowered or "which crops" in lowered:
        return "summarize_crops"
    if any(token in lowered for token in ["average", "mean", "median", "sum", "total", "minimum", "maximum"]):
        return "statistical_summary"
    return "visualize_timeseries"


def _infer_location_type(spec: Dict[str, Any]) -> str:
    location_type = (spec.get("location_type") or "").lower().strip()
    if location_type:
        return location_type
    location = (spec.get("location") or "").lower()
    return "county" if location.endswith(" county") else "city"


def _infer_dataset(spec: Dict[str, Any], user_query: str, variables: List[str]) -> str:
    if spec.get("dataset"):
        return str(spec["dataset"]).lower()
    lowered = (user_query or "").lower()
    if any(variable in OPENET_VARIABLES for variable in variables):
        return "openet"
    if any(token in lowered for token in ["eta", "evapotranspiration", "applied water", "irrigation", "crop", "fields"]):
        return "openet"
    return "agrimet"


def _extract_years(text: str) -> List[int]:
    return [int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")]


def _infer_dates(spec: Dict[str, Any], user_query: str, task: str) -> Dict[str, str]:
    if spec.get("start_date") and spec.get("end_date"):
        return {"start_date": spec["start_date"], "end_date": spec["end_date"]}

    years = _extract_years(" ".join(str(spec.get(key, "")) for key in ["year", "start_date", "end_date"]) + " " + (user_query or ""))
    fallback_year = years[-1] if years else max(date.today().year - 1, 2024)
    if task == "summarize_crops":
        return {}
    return {
        "start_date": spec.get("start_date") or f"{fallback_year}-01-01",
        "end_date": spec.get("end_date") or f"{fallback_year}-12-31",
    }


def _infer_variables(spec: Dict[str, Any], user_query: str, task: str) -> List[str]:
    variables = [value for value in (spec.get("variables") or []) if isinstance(value, str)]
    if variables or task == "summarize_crops":
        return variables

    lowered = (user_query or "").lower()
    inferred: List[str] = []

    if "solar" in lowered or "radiation" in lowered:
        inferred.append("SR")
    if "wind" in lowered:
        inferred.append("WS")
    if "humidity" in lowered:
        inferred.append("TU")
    if "max temp" in lowered or "maximum temp" in lowered:
        inferred.append("MX")
    if "min temp" in lowered or "minimum temp" in lowered:
        inferred.append("MN")
    if "temperature" in lowered or "temp" in lowered:
        inferred.append("OBM")
    if "rain" in lowered or "precip" in lowered:
        inferred.append("PC")
    if "eta" in lowered or "evapotranspiration" in lowered:
        inferred.append("ETa")
    if "applied water" in lowered:
        inferred.append("AW")
    if "usable rain" in lowered or "root zone" in lowered:
        inferred.append("P_rz")
    if "irrigation efficiency" in lowered:
        inferred.append("IRR_EFF")
    if "irrigation system" in lowered:
        inferred.append("ITYPE")
    if "irrigated share" in lowered or "percent irrigated" in lowered:
        inferred.append("per_IRRIGATED")

    deduped: List[str] = []
    seen = set()
    for value in inferred:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def validate_and_fix_spec(spec: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    fixed = dict(spec or {})
    task = _infer_task(fixed, user_query)
    if task not in SUPPORTED_TASKS:
        return {
            "task": "error",
            "error_message": f"Unsupported task: {task}. Supported tasks: visualize_timeseries, statistical_summary, summarize_crops.",
        }
    fixed["task"] = task

    if task == "summarize_crops":
        if not fixed.get("location"):
            return {"task": "error", "error_message": "Crop summary requires a city or county location."}
        fixed["location_type"] = _infer_location_type(fixed)
        years = _extract_years(str(fixed.get("year", "")) + " " + (user_query or ""))
        fixed["year"] = int(fixed.get("year") or (years[-1] if years else 2024))
        fixed["dataset"] = "openet"
        return fixed

    fixed["variables"] = _infer_variables(fixed, user_query, task)
    if not fixed["variables"]:
        return {"task": "error", "error_message": "Could not infer a variable from the query."}

    fixed["dataset"] = _infer_dataset(fixed, user_query, fixed["variables"])
    fixed["location_type"] = _infer_location_type(fixed)
    fixed["chart_type"] = fixed.get("chart_type") or "line"
    fixed["interval"] = fixed.get("interval") or ("monthly" if fixed["dataset"] == "openet" else "daily")
    fixed.update(_infer_dates(fixed, user_query, task))

    if not fixed.get("location") and fixed["dataset"] == "agrimet":
        fixed["location"] = "corvallis"

    if fixed["dataset"] == "openet":
        fixed["openet_geo"] = fixed.get("openet_geo") or ("location" if fixed.get("location") else "huc8")

    if task == "statistical_summary":
        fixed["statistics"] = fixed.get("statistics") or ["mean"]

    return fixed
