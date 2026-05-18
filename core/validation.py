from __future__ import annotations

import sqlite3
import re
from typing import Any, Dict, List, cast

import pandas as pd

from llm.keyword_matcher import match_crop_keywords

from .contracts import QuerySpec
from .crop_utils import (
    best_crop_keyword_match,
    canonicalize_crop_name,
    crop_name_variants,
    normalize_crop_phrase,
    normalize_free_text,
)
from .evidence_router import (
    detect_source_datasets,
    is_crop_filtered_trend_request,
    route_evidence_pattern,
)
from .location_resolver import display_location_name, resolve_agrimet_location, supported_agrimet_locations
from .paths import CDL_CODES_CSV, FIELD_POINTS_GPKG
from .variable_registry import (
    AGRIMET_VARIABLES,
    OPENET_VARIABLES,
    default_aggregation_for_variables,
    infer_variables_from_text,
    normalize_variable,
)

SUPPORTED_TASKS = {"visualize_timeseries", "statistical_summary", "summarize_crops"}
ANNUAL_OPENET_VARIABLES = {
    "AREA",
    "ACRES_FTR_GEOM",
    "CROP",
    "IRR_STATUS",
    "per_IRRIGATED",
    "IRR_EFF",
    "ITYPE",
}
CDL_CODES_PATH = CDL_CODES_CSV


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


def _load_openet_location_candidates() -> tuple[List[str], List[str]]:
    if not FIELD_POINTS_GPKG.exists():
        return [], []

    conn = sqlite3.connect(FIELD_POINTS_GPKG)
    try:
        counties_df = pd.read_sql_query(
            "SELECT DISTINCT County FROM field_points WHERE County IS NOT NULL AND County != '' ORDER BY County",
            conn,
        )
        cities_df = pd.read_sql_query(
            """
            SELECT DISTINCT city_name FROM (
                SELECT Nearest_City_1 AS city_name FROM field_points
                UNION
                SELECT Nearest_City_2 AS city_name FROM field_points
            )
            WHERE city_name IS NOT NULL AND city_name != ''
            ORDER BY city_name
            """,
            conn,
        )
    finally:
        conn.close()

    counties = [str(value).strip() for value in counties_df["County"].dropna().tolist() if str(value).strip()]
    cities = [str(value).split(",")[0].strip() for value in cities_df["city_name"].dropna().tolist() if str(value).strip()]
    return counties, cities


OPENET_COUNTIES, OPENET_CITIES = _load_openet_location_candidates()


def validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    spec = payload.get("spec", {})
    records = (payload.get("data") or {}).get("records") or []
    requested_variables = [str(value) for value in spec.get("variables") or []]
    report = {
        "ok": True,
        "errors": [],
        "warnings": [],
        "summary": {},
        "location": spec.get("display_location") or spec.get("location"),
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

    tracked_cols = [column for column in requested_variables if column in df.columns]
    if not tracked_cols:
        tracked_cols = [
            column
            for column in df.columns
            if column != "datetime" and pd.api.types.is_numeric_dtype(df[column])
        ]

    usable_mask = pd.Series(True, index=df.index)
    if tracked_cols:
        usable_mask = df[tracked_cols].notna().any(axis=1)

    nonnull_count = {column: int(df[column].notna().sum()) for column in tracked_cols}
    all_null_variables = [column for column in tracked_cols if nonnull_count.get(column, 0) == 0]

    report["summary"]["row_count"] = len(df)
    report["summary"]["usable_row_count"] = int(usable_mask.sum())
    report["summary"]["nonnull_count"] = nonnull_count
    report["summary"]["all_null_variables"] = all_null_variables
    report["summary"]["missing_fraction"] = (
        df[tracked_cols].isna().mean().to_dict() if tracked_cols else {}
    )
    report["nonnull_count"] = nonnull_count
    report["all_null_variables"] = all_null_variables
    report["usable_row_count"] = int(usable_mask.sum())

    if tracked_cols and int(usable_mask.sum()) == 0:
        report["errors"].append("No usable values were returned for the requested variables.")

    report["ok"] = not report["errors"]
    return report


def _extract_years(text: str) -> List[int]:
    return [int(year) for year in re.findall(r"\b(19\d{2}|20\d{2})\b", text or "")]


def _infer_task(spec: Dict[str, Any], user_query: str) -> str:
    if spec.get("task"):
        task = str(spec["task"]).strip()
        if task == "compare_locations":
            return "visualize_timeseries"
        return task

    lowered = (user_query or "").lower()
    if any(token in lowered for token in ["what crops", "which crops", "most commonly grown", "most grown crops"]):
        return "summarize_crops"
    if any(token in lowered for token in ["average", "mean", "median", "sum", "total", "minimum", "maximum"]) and not _query_mentions_time_range(user_query):
        return "statistical_summary"
    return "visualize_timeseries"


def _infer_location_type(spec: Dict[str, Any]) -> str:
    location_type = (spec.get("location_type") or "").lower().strip()
    if location_type:
        return location_type
    location = str(spec.get("display_location") or spec.get("location") or "").lower()
    return "county" if location.endswith(" county") else "city"


def _query_mentions_location(user_query: str, location: str) -> bool:
    normalized_query = f" {normalize_free_text(user_query)} "
    normalized_location = normalize_free_text(location)
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


def _infer_dates(spec: Dict[str, Any], user_query: str, task: str) -> Dict[str, str]:
    if spec.get("start_date") and spec.get("end_date"):
        return {"start_date": str(spec["start_date"]), "end_date": str(spec["end_date"])}
    if task == "summarize_crops":
        return {}

    years = _extract_years(
        " ".join(str(spec.get(key, "")) for key in ["year", "start_date", "end_date"]) + " " + (user_query or "")
    )
    if not years:
        lowered = (user_query or "").lower()
        if task == "visualize_timeseries" and any(
            token in lowered for token in ["compare", "versus", " vs ", "how many", "by crop", "by irrigation", "break down by"]
        ):
            return {"start_date": "2024-01-01", "end_date": "2024-12-31"}
        return {}

    start_year = years[0]
    end_year = years[-1]
    return {
        "start_date": str(spec.get("start_date") or f"{start_year}-01-01"),
        "end_date": str(spec.get("end_date") or f"{end_year}-12-31"),
    }


def _infer_location(user_query: str) -> str:
    county_match = re.search(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+County)\b", user_query or "")
    if county_match:
        return county_match.group(1).strip()

    query = user_query or ""
    preposition_match = re.search(
        r"\b(?:in|near|around)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b",
        query,
    )
    if preposition_match:
        candidate = preposition_match.group(1).strip()
        normalized = normalize_free_text(candidate)
        supported_locations = {normalize_free_text(value) for value in supported_agrimet_locations()}
        openet_cities = {normalize_free_text(value) for value in OPENET_CITIES}
        if normalized in supported_locations or normalized in openet_cities or candidate in {"Medford", "La Grande", "Madras", "Salem"}:
            return candidate

    return ""


def _normalize_explicit_variables(spec: Dict[str, Any]) -> List[str]:
    variables = []
    for value in spec.get("variables") or []:
        normalized = normalize_variable(str(value))
        if normalized:
            variables.append(normalized)
    return variables


def _prefer_precip_variable(user_query: str, location_type: str) -> str:
    lowered = (user_query or "").lower()
    if any(token in lowered for token in ["usable rain", "usable rainfall", "effective rainfall"]):
        return "Prz"
    if "accumul" in lowered:
        return "24_HR_PCP" if location_type != "county" else "PPT"
    if location_type == "county" or any(token in lowered for token in ["field", "fields", "crop", "orchard", "vineyard"]):
        return "PPT"
    return "PC"


def _infer_variables(spec: Dict[str, Any], user_query: str, task: str) -> List[str]:
    explicit = _normalize_explicit_variables(spec)
    if explicit or task == "summarize_crops":
        return explicit

    lowered = (user_query or "").lower()
    location_type = _infer_location_type(spec)
    inferred = infer_variables_from_text(user_query)

    if not inferred and any(token in lowered for token in ["rain", "rainfall", "precip"]):
        inferred.append(_prefer_precip_variable(user_query, location_type))

    if any(value in inferred for value in {"PC", "24_HR_PCP", "PPT"}) and any(token in lowered for token in ["rain", "precip"]):
        preferred = _prefer_precip_variable(user_query, location_type)
        inferred = [preferred] + [value for value in inferred if value not in {"PC", "24_HR_PCP", "PPT"}]

    if "how many" in lowered and "IRR_STATUS" not in inferred and any(token in lowered for token in ["irrigated", "irrigation presence"]):
        inferred.append("IRR_STATUS")

    if "by crop" in lowered and "CROP" not in inferred:
        inferred.append("CROP")
    if any(token in lowered for token in ["irrigation system", "irrigation systems", "irrigation method", "irrigation methods"]) and "ITYPE" not in inferred:
        inferred.append("ITYPE")
    if any(token in lowered for token in ["irrigated vs", "non irrigated", "non-irrigated"]) and "IRR_STATUS" not in inferred:
        inferred.append("IRR_STATUS")

    preferred_pairs = [
        ("per_IRRIGATED", "IRR_STATUS"),
        ("AVG_HUM", "TU"),
        ("AVG_TMP", "OBM"),
        ("AV_WSPD", "WS"),
        ("24_HR_PCP", "PC"),
    ]
    values = list(inferred)
    for preferred, fallback in preferred_pairs:
        if preferred in values and fallback in values:
            values = [value for value in values if value != fallback]

    deduped: List[str] = []
    seen = set()
    for value in values:
        if value not in seen:
            deduped.append(value)
            seen.add(value)
    return deduped


def _infer_dataset(spec: Dict[str, Any], user_query: str, variables: List[str]) -> str:
    if spec.get("dataset"):
        return str(spec["dataset"]).lower().strip()
    sources = detect_source_datasets(variables)
    if len(sources) == 1:
        return sources[0]
    if len(sources) > 1:
        return sources[0]

    lowered = (user_query or "").lower()
    location_type = _infer_location_type(spec)
    if location_type == "county":
        return "openet"
    if any(variable in OPENET_VARIABLES for variable in variables):
        return "openet"
    if any(variable in AGRIMET_VARIABLES for variable in variables):
        return "agrimet"
    if any(token in lowered for token in ["eta", "evapotranspiration", "applied water", "irrigation", "crop", "fields"]):
        return "openet"
    return "agrimet"


def _default_interval(dataset: str, variables: List[str]) -> str:
    if dataset == "openet" and any(variable in ANNUAL_OPENET_VARIABLES for variable in variables):
        return "yearly"
    return "monthly" if dataset == "openet" else "daily"


def _infer_crop_filter(spec: Dict[str, Any], user_query: str) -> str:
    if spec.get("crop_filter"):
        return canonicalize_crop_name(str(spec["crop_filter"]))

    lowered_query = f" {normalize_free_text(user_query)} "
    if not lowered_query.strip():
        return ""

    direct_match = best_crop_keyword_match(user_query, CROP_NAME_CANDIDATES)
    if direct_match:
        return direct_match

    def _literal_keyword_match() -> str:
        keyword_match = match_crop_keywords(user_query)
        if not keyword_match:
            return ""
        candidate = canonicalize_crop_name(keyword_match[1])
        variants = crop_name_variants(candidate) | {normalize_free_text(candidate)}
        if any(variant and f" {variant} " in lowered_query for variant in variants):
            return candidate
        return ""

    keyword_literal = _literal_keyword_match()
    if keyword_literal:
        return keyword_literal

    phrase_patterns = [
        r"\bfor\s+([a-z][a-z\s\-]+?)\s+(?:farm|farms|field|fields|orchard|orchards|vineyard|vineyards|crop|crops)\b",
        r"\bby\s+([a-z][a-z\s\-]+?)\s+(?:farm|farms|field|fields|orchard|orchards|vineyard|vineyards|crop|crops)\b",
        r"\b(?:affecting|impacting)\s+([a-z][a-z\s\-]+?)\s+(?:farm|farms|field|fields|orchard|orchards|vineyard|vineyards|crop|crops)\b",
        r"\bfor\s+([a-z][a-z\s\-]+?)\s+(?:near|around|in)\b",
        r"\bespecially\s+([a-z][a-z\s\-]+)\b",
    ]
    for pattern in phrase_patterns:
        match = re.search(pattern, lowered_query)
        if match:
            candidate = normalize_crop_phrase(match.group(1))
            if candidate and candidate.lower() not in {"the", "all", "selected", "water", "crop"}:
                return candidate

    farm_pattern = re.search(r"\b([a-z][a-z\s\-]+?)\s+(?:farm|farms|field|fields|orchard|orchards|vineyard|vineyards)\b", lowered_query)
    if farm_pattern:
        guess = canonicalize_crop_name(farm_pattern.group(1))
        if guess and guess not in {"Irrigated", "Non Irrigated", "Water", "Crop"}:
            return guess

    return ""


def _needs_location(spec: QuerySpec, task: str) -> bool:
    if task == "summarize_crops":
        return True
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

    if spec.get("dataset") == "agrimet" and spec.get("location"):
        resolution = resolve_agrimet_location(
            str(spec.get("display_location") or spec.get("location")),
            local_only=False,
            start_date=str(spec.get("start_date") or "") or None,
            end_date=str(spec.get("end_date") or "") or None,
        )
        if not resolution:
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
    if fixed.get("display_location"):
        fixed["display_location"] = str(fixed["display_location"]).strip()
    if fixed.get("location_type"):
        fixed["location_type"] = str(fixed["location_type"]).lower().strip()  # type: ignore[assignment]
    if fixed.get("station_id"):
        fixed["station_id"] = str(fixed["station_id"]).strip()
    if fixed.get("station_title"):
        fixed["station_title"] = str(fixed["station_title"]).strip()
    if fixed.get("chart_type"):
        fixed["chart_type"] = str(fixed["chart_type"]).lower().strip()
    if fixed.get("interval"):
        fixed["interval"] = str(fixed["interval"]).lower().strip()
    if fixed.get("aggregation"):
        fixed["aggregation"] = str(fixed["aggregation"]).lower().strip()
    if fixed.get("crop_filter"):
        fixed["crop_filter"] = canonicalize_crop_name(str(fixed["crop_filter"]))
    if fixed.get("openet_geo"):
        fixed["openet_geo"] = str(fixed["openet_geo"]).lower().strip()
    if fixed.get("openet_id"):
        fixed["openet_id"] = str(fixed["openet_id"]).strip()
    if fixed.get("huc8_code"):
        fixed["huc8_code"] = str(fixed["huc8_code"]).strip()
    if fixed.get("confirmation_status"):
        fixed["confirmation_status"] = str(fixed["confirmation_status"]).lower().strip()  # type: ignore[assignment]

    fixed["variables"] = _normalize_explicit_variables(fixed)

    statistics = fixed.get("statistics") or []
    fixed["statistics"] = [str(value).lower().strip() for value in statistics if str(value).strip()]

    clarification_needed = fixed.get("clarification_needed") or []
    fixed["clarification_needed"] = [str(value).strip() for value in clarification_needed if str(value).strip()]

    confirmed_fields = fixed.get("confirmed_fields") or []
    fixed["confirmed_fields"] = [str(value).strip() for value in confirmed_fields if str(value).strip()]

    notes = fixed.get("notes") or []
    fixed["notes"] = [str(value).strip() for value in notes if str(value).strip()]

    if fixed.get("year") is not None and str(fixed["year"]).strip():
        year_text = str(fixed["year"]).strip()
        years = _extract_years(year_text)
        if years:
            fixed["year"] = years[-1]
        else:
            fixed["year"] = int(year_text)  # type: ignore[arg-type]

    return fixed


def _apply_location_resolution(fixed: QuerySpec) -> QuerySpec:
    if not fixed.get("location"):
        return fixed

    location_type = _infer_location_type(fixed)
    fixed["location_type"] = location_type  # type: ignore[assignment]
    fixed["display_location"] = fixed.get("display_location") or display_location_name(str(fixed["location"]), location_type)

    if fixed.get("dataset") != "agrimet":
        fixed["display_location"] = display_location_name(str(fixed["display_location"]), location_type)
        return fixed

    resolution = resolve_agrimet_location(
        str(fixed["display_location"]),
        local_only=False,
        start_date=str(fixed.get("start_date") or "") or None,
        end_date=str(fixed.get("end_date") or "") or None,
    )
    if not resolution:
        return fixed

    fixed["display_location"] = resolution.get("display_location") or fixed["display_location"]
    if resolution.get("canonical_location"):
        fixed["location"] = resolution["canonical_location"]
    if resolution.get("station_id"):
        fixed["station_id"] = resolution["station_id"]
    if resolution.get("station_title"):
        fixed["station_title"] = resolution["station_title"]
    if resolution.get("station_resolution_mode"):
        fixed["station_resolution_mode"] = resolution["station_resolution_mode"]  # type: ignore[assignment]
    fixed["supported_local"] = bool(resolution.get("supported_local", True))  # type: ignore[assignment]

    notes = list(fixed.get("notes") or [])
    if resolution.get("station_title") and resolution.get("station_resolution_mode") not in {None, "", "exact"}:
        notes.append(
            f"Resolved {fixed['display_location']} to {resolution['station_title']} ({resolution.get('station_id', '')}) via {resolution['station_resolution_mode']}."
        )
    if fixed.get("dataset") == "agrimet":
        notes.append("Runtime AgriMet queries use the AgriMet API only.")
    if notes:
        fixed["notes"] = notes
    return fixed


def _normalize_grouping_variables_for_crop_trends(fixed: QuerySpec, user_query: str) -> QuerySpec:
    variables = list(fixed.get("variables") or [])
    if not variables or not is_crop_filtered_trend_request(fixed, user_query):
        return fixed

    non_group_variables = [value for value in variables if value not in {"CROP", "IRR_STATUS", "ITYPE"}]
    if not non_group_variables:
        return fixed

    fixed["variables"] = non_group_variables
    fixed.pop("group_by", None)
    fixed.pop("split_by", None)
    fixed.pop("compare_by", None)
    fixed["secondary_variables"] = []
    return fixed


def validate_and_fix_spec(spec: Dict[str, Any], user_query: str) -> Dict[str, Any]:
    fixed = _normalize_spec_shape(dict(spec or {}))
    confirmed_fields = set(fixed.get("confirmed_fields") or [])

    if (
        fixed.get("location")
        and "location" not in confirmed_fields
        and not _query_mentions_location(user_query, str(fixed.get("display_location") or fixed["location"]))
    ):
        fixed.pop("location", None)
        fixed.pop("display_location", None)
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

    if not fixed.get("location"):
        inferred_location = _infer_location(user_query)
        if inferred_location:
            fixed["location"] = inferred_location
            fixed["display_location"] = inferred_location

    if task == "summarize_crops":
        if not fixed.get("location"):
            fixed["clarification_needed"] = ["location"]
            return fixed

        years = _extract_years(str(fixed.get("year", "")) + " " + (user_query or ""))
        fixed["location_type"] = _infer_location_type(fixed)
        fixed["display_location"] = fixed.get("display_location") or display_location_name(str(fixed["location"]), fixed["location_type"])
        fixed["year"] = int(fixed.get("year") or (years[-1] if years else 2024))
        fixed["dataset"] = "openet"
        fixed["variables"] = fixed.get("variables") or ["CROP"]
        inferred_crop = _infer_crop_filter(fixed, user_query)
        if inferred_crop:
            fixed["crop_filter"] = inferred_crop
        fixed["confirmation_status"] = cast(Any, fixed.get("confirmation_status") or "pending")
        fixed["clarification_needed"] = collect_clarification_fields(fixed)
        return route_evidence_pattern(fixed, user_query)

    fixed["variables"] = _infer_variables(fixed, user_query, task)
    if fixed["variables"]:
        fixed["dataset"] = _infer_dataset(fixed, user_query, fixed["variables"])
        fixed["location_type"] = _infer_location_type(fixed)
        fixed = _apply_location_resolution(fixed)
        fixed["chart_type"] = fixed.get("chart_type") or "line"
        fixed["interval"] = fixed.get("interval") or _default_interval(str(fixed["dataset"]), fixed["variables"])
        if fixed["dataset"] == "openet":
            fixed["openet_geo"] = "location"
    else:
        fixed["chart_type"] = fixed.get("chart_type") or "line"

    if task == "visualize_timeseries":
        fixed.update(_infer_dates(fixed, user_query, task))

    if task == "statistical_summary":
        fixed["statistics"] = fixed.get("statistics") or ["mean"]

    if any(token in (user_query or "").lower() for token in ["how many", "number of", "count"]) and "IRR_STATUS" in (fixed.get("variables") or []):
        fixed["aggregation"] = fixed.get("aggregation") or "sum"

    if fixed.get("variables") and not fixed.get("aggregation"):
        fixed["aggregation"] = default_aggregation_for_variables(fixed.get("variables") or [])

    inferred_crop = _infer_crop_filter(fixed, user_query)
    if inferred_crop:
        fixed["crop_filter"] = inferred_crop

    fixed = _normalize_grouping_variables_for_crop_trends(fixed, user_query)

    fixed["display_location"] = fixed.get("display_location") or (
        display_location_name(str(fixed["location"]), fixed.get("location_type")) if fixed.get("location") else ""
    )
    fixed["confirmation_status"] = cast(Any, fixed.get("confirmation_status") or "pending")
    fixed["clarification_needed"] = collect_clarification_fields(fixed)
    routed = route_evidence_pattern(fixed, user_query)

    if not routed.get("source_datasets") and routed.get("dataset") in {"openet", "agrimet"}:
        routed["source_datasets"] = [str(routed["dataset"])]

    if not routed.get("dataset") and len(routed.get("source_datasets") or []) == 1:
        routed["dataset"] = cast(Any, routed["source_datasets"][0])

    if len(routed.get("source_datasets") or []) > 1:
        notes = list(routed.get("notes") or [])
        notes.append("Detected variables from multiple datasets; routing as a coordinated evidence package.")
        routed["notes"] = notes

    return routed
