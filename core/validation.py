from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, cast

import pandas as pd

from .contracts import QuerySpec
from .data_fetcher import supported_agrimet_locations
from .evidence_router import detect_source_datasets, route_evidence_pattern
from llm.keyword_matcher import match_crop_keywords
from .variable_registry import AGRIMET_VARIABLES, OPENET_VARIABLES

SUPPORTED_TASKS = {"visualize_timeseries", "statistical_summary", "summarize_crops"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CDL_CODES_PATH = DATA_DIR / "CDL_Crop_Codes_Oregon.csv"


def _load_crop_name_candidates() -> List[str]:
    try:
        df = pd.read_csv(CDL_CODES_PATH)
    except Exception:
        return []

    names: List[str] = []
    for value in df.get("Crop_Name", pd.Series(dtype=str)).dropna().astype(str):
        cleaned = value.strip()
        if cleaned:
            names.append(cleaned)
    return names


CROP_NAME_CANDIDATES = _load_crop_name_candidates()


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


def _normalize_free_text(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", (value or "").lower())
    return " ".join(cleaned.split())


def _canonicalize_crop_name(name: str) -> str:
    cleaned = " ".join(str(name or "").strip().split())
    if not cleaned:
        return ""
    lower = cleaned.lower()
    if lower.endswith("ies") and len(cleaned) > 3:
        cleaned = cleaned[:-3] + "y"
    if lower.endswith("s") and not lower.endswith("ss") and len(cleaned) > 3:
        cleaned = cleaned[:-1]
    return cleaned.title()


def _crop_name_variants(name: str) -> set[str]:
    canonical = _canonicalize_crop_name(name).lower()
    if not canonical:
        return set()
    variants = {canonical}
    if canonical.endswith("y"):
        variants.add(canonical[:-1] + "ies")
    else:
        variants.add(canonical + "s")
    return variants


def _normalize_crop_phrase(phrase: str) -> str:
    cleaned = _canonicalize_crop_name(phrase)
    lowered = cleaned.lower()
    trailing_terms = (" farm", " farms", " field", " fields", " orchard", " orchards", " vineyard", " vineyards")
    for term in trailing_terms:
        if lowered.endswith(term):
            cleaned = cleaned[: -len(term)].strip()
            lowered = cleaned.lower()
    return _canonicalize_crop_name(cleaned)


def _normalize_keyword_crop_match(crop_name: str, user_query: str) -> str:
    query_text = f" {_normalize_free_text(user_query)} "
    parts = [part.strip() for part in str(crop_name).replace("-", " ").split("/") if part.strip()]
    for part in parts:
        for variant in _crop_name_variants(part):
            if f" {variant} " in query_text:
                return _canonicalize_crop_name(part)
    return _canonicalize_crop_name(parts[-1] if parts else crop_name)


def _infer_crop_filter(spec: Dict[str, Any], user_query: str) -> str:
    if spec.get("crop_filter"):
        return str(spec["crop_filter"]).strip()

    lowered_query = f" {_normalize_free_text(user_query)} "
    if not lowered_query.strip():
        return ""

    phrase_patterns = [
        r"\bfor\s+([a-z][a-z\s\-]+?)\s+in\b",
        r"\bfor\s+([a-z][a-z\s\-]+?)\s+(?:near|around)\b",
        r"\b([a-z][a-z\s\-]+?)\s+(?:farm|farms|field|fields|orchard|orchards|vineyard|vineyards)\b",
    ]
    for pattern in phrase_patterns:
        match = re.search(pattern, lowered_query)
        if match:
            candidate = _normalize_crop_phrase(match.group(1))
            if candidate and candidate.lower() not in {"the", "all", "selected", "plant water need", "irrigation demand", "water applied"}:
                return candidate

    keyword_match = match_crop_keywords(user_query)
    if keyword_match:
        return _normalize_keyword_crop_match(keyword_match[1], user_query)

    best_match = ""
    best_length = 0
    for crop_name in CROP_NAME_CANDIDATES:
        canonical = _canonicalize_crop_name(crop_name)
        for variant in _crop_name_variants(crop_name):
            if f" {variant} " in lowered_query and len(variant) > best_length:
                best_match = canonical
                best_length = len(variant)

    if best_match:
        return best_match

    farm_pattern = re.search(r"\b([a-z][a-z\s\-]+?)\s+(?:farm|farms|field|fields|orchard|orchards|vineyard|vineyards)\b", lowered_query)
    if farm_pattern:
        guess = _canonicalize_crop_name(farm_pattern.group(1))
        if guess and guess not in {"irrigated", "non irrigated", "water", "crop"}:
            return guess

    return ""


def _query_mentions_location(user_query: str, location: str) -> bool:
    normalized_query = f" {_normalize_free_text(user_query)} "
    normalized_location = _normalize_free_text(location)
    if not normalized_location:
        return False

    candidates = {normalized_location}
    if normalized_location.endswith(" county"):
        candidates.add(normalized_location[: -len(" county")].strip())

    return any(f" {candidate} " in normalized_query for candidate in candidates if candidate)


def _query_mentions_time_range(user_query: str) -> bool:
    lowered = (user_query or "").lower()
    if re.search(r"\b(19\d{2}|20\d{2})\b", lowered):
        return True
    time_tokens = [
        "last year",
        "this year",
        "yesterday",
        "today",
        "this month",
        "last month",
        "from",
        "between",
        "through",
        "during",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ]
    return any(token in lowered for token in time_tokens)


def _infer_dataset(spec: Dict[str, Any], user_query: str, variables: List[str]) -> str:
    if spec.get("dataset"):
        return str(spec["dataset"]).lower()
    sources = detect_source_datasets(variables)
    if len(sources) == 1:
        return sources[0]
    if len(sources) > 1:
        return sources[0]
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
    if task == "summarize_crops":
        return {}
    if not years:
        return {}
    fallback_year = years[-1]
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
    if "reference evapotranspiration" in lowered or "atmospheric water demand" in lowered:
        inferred.append("PEN_ET")
    if "rain" in lowered or "precip" in lowered:
        inferred.append("PC")
    if "24-hour precipitation" in lowered:
        inferred.append("24_HR_PCP")
    if "eta" in lowered or "evapotranspiration" in lowered:
        inferred.append("ETa")
    if "water demand" in lowered and "reference" in lowered:
        inferred.append("PEN_ET")
    if "applied water" in lowered:
        inferred.append("AW")
    if "irrigation demand" in lowered or "irrigation requirement" in lowered:
        inferred.append("NIWR")
    if "usable rain" in lowered or "root zone" in lowered:
        inferred.append("P_rz")
    if "irrigation efficiency" in lowered:
        inferred.append("IRR_EFF")
    if "irrigation system" in lowered:
        inferred.append("ITYPE")
    if "irrigated field" in lowered or "irrigation presence" in lowered:
        inferred.append("IRR_STATUS")
    if "irrigated share" in lowered or "percent irrigated" in lowered:
        inferred.append("per_IRRIGATED")
    if "humidity" in lowered:
        inferred.append("AVG_HUM")
    if "wind pattern" in lowered or "wind speed" in lowered:
        inferred.append("AV_WSPD")
    if "crop coefficient" in lowered or "growth characteristic" in lowered:
        inferred.append("Kc")
    if "crop" in lowered and any(token in lowered for token in ["which", "what", "most", "common", "largest"]):
        inferred.append("CROP")

    deduped: List[str] = []
    seen = set()
    for value in inferred:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _needs_location(spec: QuerySpec, task: str) -> bool:
    if task == "summarize_crops":
        return True
    if spec.get("dataset") == "openet" and (spec.get("openet_geo") == "field" or spec.get("openet_id") or spec.get("huc8_code")):
        return False
    return True


def collect_clarification_fields(spec: QuerySpec) -> List[str]:
    task = spec.get("task", "")
    missing: List[str] = []

    if task in {"visualize_timeseries", "statistical_summary"} and not spec.get("variables"):
        missing.append("variable")
    if _needs_location(spec, task) and not spec.get("location"):
        missing.append("location")
    if task == "visualize_timeseries" and (not spec.get("start_date") or not spec.get("end_date")):
        missing.append("time_range")
    if task == "summarize_crops" and not spec.get("location"):
        missing.append("location")
    if (
        spec.get("dataset") == "agrimet"
        and spec.get("location")
        and not spec.get("station_id")
        and os.getenv("AGRIMET_USE_API") != "1"
    ):
        normalized = str(spec.get("location", "")).strip().lower()
        if normalized not in supported_agrimet_locations():
            missing.append("station")

    seen = set()
    ordered: List[str] = []
    for field in missing:
        if field not in seen:
            ordered.append(field)
            seen.add(field)
    return ordered


def _normalize_spec_shape(spec: Dict[str, Any]) -> QuerySpec:
    fixed: QuerySpec = cast(QuerySpec, dict(spec))

    if fixed.get("dataset"):
        fixed["dataset"] = str(fixed["dataset"]).lower().strip()  # type: ignore[assignment]
    if fixed.get("location"):
        fixed["location"] = str(fixed["location"]).strip()
    if fixed.get("location_type"):
        fixed["location_type"] = str(fixed["location_type"]).lower().strip()  # type: ignore[assignment]
    if fixed.get("station_id"):
        fixed["station_id"] = str(fixed["station_id"]).strip()
    if fixed.get("chart_type"):
        fixed["chart_type"] = str(fixed["chart_type"]).lower().strip()
    if fixed.get("interval"):
        fixed["interval"] = str(fixed["interval"]).lower().strip()
    if fixed.get("aggregation"):
        fixed["aggregation"] = str(fixed["aggregation"]).lower().strip()
    if fixed.get("crop_filter"):
        fixed["crop_filter"] = _canonicalize_crop_name(str(fixed["crop_filter"]))
    if fixed.get("openet_geo"):
        fixed["openet_geo"] = str(fixed["openet_geo"]).lower().strip()
    if fixed.get("openet_id"):
        fixed["openet_id"] = str(fixed["openet_id"]).strip()
    if fixed.get("huc8_code"):
        fixed["huc8_code"] = str(fixed["huc8_code"]).strip()

    variables = fixed.get("variables") or []
    fixed["variables"] = [str(value).strip() for value in variables if str(value).strip()]

    statistics = fixed.get("statistics") or []
    fixed["statistics"] = [str(value).lower().strip() for value in statistics if str(value).strip()]

    clarification_needed = fixed.get("clarification_needed") or []
    fixed["clarification_needed"] = [str(value).strip() for value in clarification_needed if str(value).strip()]

    confirmed_fields = fixed.get("confirmed_fields") or []
    fixed["confirmed_fields"] = [str(value).strip() for value in confirmed_fields if str(value).strip()]

    notes = fixed.get("notes") or []
    fixed["notes"] = [str(value).strip() for value in notes if str(value).strip()]

    if fixed.get("year") is not None and str(fixed["year"]).strip():
        fixed["year"] = int(fixed["year"])  # type: ignore[arg-type]

    return fixed


def validate_and_fix_spec(spec: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    fixed = _normalize_spec_shape(dict(spec or {}))
    confirmed_fields = set(fixed.get("confirmed_fields") or [])
    if (
        fixed.get("location")
        and "location" not in confirmed_fields
        and not _query_mentions_location(user_query, str(fixed["location"]))
    ):
        fixed.pop("location", None)
        fixed.pop("station_id", None)
        notes = list(fixed.get("notes") or [])
        notes.append("Dropped parser-supplied location because it was not mentioned in the user query.")
        fixed["notes"] = notes
    if (
        (fixed.get("start_date") or fixed.get("end_date"))
        and "time_range" not in confirmed_fields
        and not _query_mentions_time_range(user_query)
    ):
        fixed.pop("start_date", None)
        fixed.pop("end_date", None)
        notes = list(fixed.get("notes") or [])
        notes.append("Dropped parser-supplied time range because it was not mentioned in the user query.")
        fixed["notes"] = notes

    task = _infer_task(fixed, user_query)
    if task not in SUPPORTED_TASKS:
        return {
            "task": "error",
            "error_message": f"Unsupported task: {task}. Supported tasks: visualize_timeseries, statistical_summary, summarize_crops.",
        }
    fixed["task"] = task

    if task == "summarize_crops":
        if not fixed.get("location"):
            fixed["clarification_needed"] = ["location"]
            return fixed
        fixed["location_type"] = _infer_location_type(fixed)
        years = _extract_years(str(fixed.get("year", "")) + " " + (user_query or ""))
        fixed["year"] = int(fixed.get("year") or (years[-1] if years else 2024))
        fixed["dataset"] = "openet"
        fixed["clarification_needed"] = collect_clarification_fields(fixed)
        return route_evidence_pattern(fixed, user_query)

    fixed["variables"] = _infer_variables(fixed, user_query, task)
    if fixed["variables"]:
        fixed["dataset"] = _infer_dataset(fixed, user_query, fixed["variables"])
        fixed["location_type"] = _infer_location_type(fixed)
        fixed["chart_type"] = fixed.get("chart_type") or "line"
        fixed["interval"] = fixed.get("interval") or ("monthly" if fixed["dataset"] == "openet" else "daily")
        if fixed["dataset"] == "openet":
            fixed["openet_geo"] = fixed.get("openet_geo") or ("location" if fixed.get("location") else "huc8")
    else:
        fixed["chart_type"] = fixed.get("chart_type") or "line"

    if task == "visualize_timeseries":
        fixed.update(_infer_dates(fixed, user_query, task))

    if task == "statistical_summary":
        fixed["statistics"] = fixed.get("statistics") or ["mean"]

    inferred_crop = _infer_crop_filter(fixed, user_query)
    if inferred_crop:
        fixed["crop_filter"] = inferred_crop

    fixed["clarification_needed"] = collect_clarification_fields(fixed)
    routed = route_evidence_pattern(fixed, user_query)

    if not routed.get("source_datasets") and fixed.get("dataset") in {"openet", "agrimet"}:
        routed["source_datasets"] = [str(fixed["dataset"])]

    if not routed.get("dataset") and len(routed.get("source_datasets") or []) == 1:
        routed["dataset"] = cast(Any, routed["source_datasets"][0])

    if len(routed.get("source_datasets") or []) > 1 and not routed.get("notes"):
        routed["notes"] = []
    if len(routed.get("source_datasets") or []) > 1:
        notes = list(routed.get("notes") or [])
        notes.append("Detected variables from multiple datasets; routing as a coordinated evidence package.")
        routed["notes"] = notes

    return routed
