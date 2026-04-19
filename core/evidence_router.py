from __future__ import annotations

from typing import Any, Dict, List

from .contracts import QuerySpec
from .variable_registry import AGRIMET_VARIABLES, OPENET_VARIABLES


RANKING_TOKENS = ("most", "largest", "top", "common", "dominant", "rank")
COMPARE_TOKENS = (" vs ", "versus", "compared", "compare", "keep up with")
DISTRIBUTION_TOKENS = ("share", "mix", "distribution", "percent", "portion")
CHANGE_TOKENS = ("before and after", "difference between", "differ between", "delta", "change amount")
CHANGE_AMOUNT_TOKENS = ("how much did", "how much has", "increase by", "decrease by")
SEASONAL_TOKENS = ("seasonal", "seasonality", "typical annual", "annual cycle", "month of year", "which months", "monthly pattern")
METRIC_RANKING_GROUP_TOKENS = ("crop", "crops", "county", "counties", "location", "locations", "station", "stations")
METRIC_RANKING_VALUE_TOKENS = ("highest", "lowest", "largest", "smallest", "top", "rank")


def detect_source_datasets(variables: List[str]) -> List[str]:
    sources: List[str] = []
    if any(variable in OPENET_VARIABLES for variable in variables):
        sources.append("openet")
    if any(variable in AGRIMET_VARIABLES for variable in variables):
        sources.append("agrimet")
    return sources


def _split_variable_roles(variables: List[str]) -> tuple[List[str], List[str], str]:
    split_candidates = [value for value in variables if value in {"IRR_STATUS", "ITYPE", "CROP"}]
    secondary = [value for value in variables if value not in split_candidates]
    split_by = split_candidates[0] if split_candidates else ""
    return split_candidates, secondary, split_by


def route_evidence_pattern(spec: QuerySpec, user_query: str) -> QuerySpec:
    routed: QuerySpec = dict(spec)
    variables = list(routed.get("variables") or [])
    lowered = f" {(user_query or '').lower()} "
    sources = detect_source_datasets(variables)
    split_candidates, secondary_variables, split_by = _split_variable_roles(variables)

    routed["source_datasets"] = sources
    routed["secondary_variables"] = secondary_variables
    if split_candidates:
        routed["group_by"] = split_candidates
        routed["split_by"] = split_by

    if routed.get("task") == "statistical_summary":
        routed["evidence_pattern"] = "stat_snapshot"
        routed["chart_package"] = "stat_snapshot"
        return routed

    if len(sources) > 1:
        routed["evidence_pattern"] = "cross_dataset_comparison"
        routed["chart_package"] = ["primary_trend", "dataset_companion"]
        return routed

    if routed.get("task") == "summarize_crops":
        if any(token in lowered for token in DISTRIBUTION_TOKENS):
            routed["evidence_pattern"] = "distribution_categories"
            routed["chart_package"] = ["distribution_bar", "distribution_companion"]
        else:
            routed["evidence_pattern"] = "ranking_categories"
            routed["chart_package"] = ["ranking_bar", "distribution_companion"]
        routed.setdefault("group_by", ["CROP"])
        return routed

    if split_candidates and not secondary_variables and len(variables) == 1:
        routed["evidence_pattern"] = "trend_single"
        routed["chart_package"] = "single_trend"
        return routed

    if (
        any(token in lowered for token in METRIC_RANKING_VALUE_TOKENS)
        and any(token in lowered for token in METRIC_RANKING_GROUP_TOKENS)
        and variables
    ):
        routed["evidence_pattern"] = "ranking_metric"
        routed["chart_package"] = ["ranking_metric_bar", "ranking_metric_companion"]
        return routed

    if split_candidates and secondary_variables:
        routed["evidence_pattern"] = "comparison_grouped"
        routed["chart_package"] = "grouped_comparison"
        routed["compare_by"] = split_by
        return routed

    if any(token in lowered for token in SEASONAL_TOKENS):
        routed["evidence_pattern"] = "seasonality_pattern"
        routed["chart_package"] = ["seasonal_profile", "seasonal_companion"]
        return routed

    if any(token in lowered for token in CHANGE_TOKENS) or any(token in lowered for token in CHANGE_AMOUNT_TOKENS):
        routed["evidence_pattern"] = "change_over_period"
        routed["chart_package"] = ["delta_primary", "delta_companion"]
        return routed

    if any(token in lowered for token in RANKING_TOKENS) and ("crop" in lowered or "field" in lowered):
        routed["evidence_pattern"] = "ranking_categories"
        routed["chart_package"] = "ranking_bar"
        return routed

    if len(variables) > 1 or any(token in lowered for token in COMPARE_TOKENS):
        routed["evidence_pattern"] = "comparison_multivariate"
        routed["chart_package"] = "comparison_series"
        return routed

    routed["evidence_pattern"] = "trend_single"
    routed["chart_package"] = "single_trend"
    return routed
