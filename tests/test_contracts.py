from __future__ import annotations

import pandas as pd

from core.contracts import (
    build_clarification_result,
    build_confirmation_result,
    build_error_result,
    build_preview,
    build_success_result,
)
from core.crop_utils import canonicalize_crop_name, crop_name_variants, matching_crop_codes
from core.data_fetcher import get_dataset_adapter
from core.agrimet_station_loader import find_local_file_prefixes
from core.location_resolver import resolve_agrimet_location
from core.validation import validate_and_fix_spec
from core.variable_registry import normalize_variable, variable_label


def test_build_preview_keeps_small_frames_intact():
    df = pd.DataFrame({"value": [1, 2, 3]}, index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    preview = build_preview(df, limit=20)
    assert len(preview) == 3
    assert "index" in preview.columns or "datetime" in preview.columns


def test_build_preview_truncates_with_head_and_tail():
    df = pd.DataFrame({"value": list(range(30))}, index=pd.date_range("2024-01-01", periods=30, freq="D"))
    preview = build_preview(df, limit=20)
    assert len(preview) == 20
    assert preview["value"].iloc[0] == 0
    assert preview["value"].iloc[-1] == 29


def test_build_success_result_uses_canonical_shape():
    preview = pd.DataFrame({"value": [1]})
    data = pd.DataFrame({"value": [1, 2]})
    result = build_success_result(
        spec={"task": "visualize_timeseries", "dataset": "agrimet"},
        summary={"row_count": 2},
        explanation="This chart shows one value.",
        data_preview=preview,
        data=data,
        chart_bytes=b"png",
        vega_spec={"mark": "line"},
        files={"png": "outputs/charts/example.png"},
        validation_report={"ok": True},
    )
    assert result["success"] is True
    assert result["needs_confirmation"] is False
    assert result["data"] is data
    assert result["files"]["png"].endswith(".png")


def test_build_error_result_uses_canonical_shape():
    result = build_error_result("boom")
    assert result["success"] is False
    assert result["needs_confirmation"] is False
    assert result["error"] == "boom"


def test_build_clarification_result_uses_canonical_shape():
    result = build_clarification_result(
        spec={"task": "visualize_timeseries", "clarification_needed": ["location"]},
        prompt="Need location",
        fields=["location"],
    )
    assert result["success"] is False
    assert result["needs_clarification"] is True
    assert result["clarification_prompt"] == "Need location"


def test_build_confirmation_result_uses_canonical_shape():
    result = build_confirmation_result(
        spec={"task": "visualize_timeseries", "confirmation_status": "pending"},
        prompt="Confirm this request.",
    )
    assert result["success"] is False
    assert result["needs_confirmation"] is True
    assert result["confirmation_prompt"] == "Confirm this request."


def test_variable_registry_normalizes_aliases_and_labels():
    assert normalize_variable("potential water needs") == "ETDa"
    assert normalize_variable("crop growth characteristics") == "Kc"
    assert variable_label("ACRES_FTR_GEOM") == "Farmland Area (acres)"


def test_crop_name_canonicalization_handles_plural_forms():
    assert canonicalize_crop_name("potatoes") == "Potato"
    assert canonicalize_crop_name("berries") == "Berry"
    assert "potatoes" in crop_name_variants("Potato")


def test_matching_crop_codes_prefers_exact_label_before_broader_family_matches():
    crop_names = {
        21: {"name": "Barley"},
        22: {"name": "Durum Wheat"},
        23: {"name": "Spring Wheat"},
        24: {"name": "Winter Wheat"},
        36: {"name": "Alfalfa"},
        37: {"name": "Other Hay/Non Alfalfa"},
    }

    assert matching_crop_codes("Alfalfa", crop_names) == [36]
    assert matching_crop_codes("Wheat", crop_names) == [22, 23, 24]


def test_resolve_agrimet_location_handles_supported_and_unsupported_places():
    benton = resolve_agrimet_location("Benton County", local_only=True)
    assert benton is not None
    assert benton["canonical_location"] == "corvallis"
    assert benton["supported_local"] is True

    medford = resolve_agrimet_location("Medford", local_only=True)
    assert medford is not None
    assert medford["supported_local"] is False
    assert medford["station_title"].startswith("Medford")
    assert medford["station_resolution_mode"] == "nearest_city"


def test_resolve_agrimet_location_uses_city_centroid_for_la_grande():
    lagrande = resolve_agrimet_location("La Grande", local_only=False)
    assert lagrande is not None
    assert lagrande["station_id"] == "imbo"
    assert lagrande["station_resolution_mode"] == "centroid_nearest_station"


def test_resolve_agrimet_location_uses_city_centroid_for_salem():
    salem = resolve_agrimet_location("Salem", local_only=False)
    assert salem is not None
    assert salem["station_id"] == "subo"
    assert salem["station_resolution_mode"] == "centroid_nearest_station"


def test_find_local_file_prefixes_prioritizes_bundled_dataset_names():
    assert find_local_file_prefixes("corvallis")[0] == "corvallis"
    assert "corvallis" in find_local_file_prefixes("crvo")


def test_validate_and_fix_spec_normalizes_queryspec_shape():
    result = validate_and_fix_spec(
        {
            "dataset": "AGRIMET",
            "location": " Corvallis ",
            "variables": [" OBM ", " "],
            "statistics": [" MEAN "],
            "chart_type": "LINE",
            "confirmation_status": "CONFIRMED",
        },
        "Show temperature in Corvallis for 2024",
    )
    assert result["dataset"] == "agrimet"
    assert result["location"] == "corvallis"
    assert result["display_location"] == "Corvallis"
    assert result["variables"] == ["OBM"]
    assert result["statistics"] == ["mean"]
    assert result["chart_type"] == "line"
    assert result["confirmation_status"] == "confirmed"


def test_get_dataset_adapter_exposes_contract_defaults():
    adapter = get_dataset_adapter("openet")
    assert adapter.contract.name == "openet"
    assert adapter.contract.default_interval == "monthly"


def test_validate_and_fix_spec_drops_unmentioned_parser_location():
    result = validate_and_fix_spec(
        {
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "location": "corvallis",
            "display_location": "Corvallis",
            "variables": ["PC"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
        "show me precipitation in 2024",
    )
    assert "location" not in result
    assert "location" in result["clarification_needed"]


def test_validate_and_fix_spec_drops_unmentioned_parser_time_range():
    result = validate_and_fix_spec(
        {
            "task": "visualize_timeseries",
            "dataset": "agrimet",
            "variables": ["PC"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
        "show me precipitation",
    )
    assert "start_date" not in result
    assert "end_date" not in result
    assert "time_range" in result["clarification_needed"]


def test_validate_and_fix_spec_accepts_supported_agrimet_county():
    result = validate_and_fix_spec(
        {
            "dataset": "agrimet",
            "variables": ["PC"],
            "location": "Benton County",
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
        "show me precipitation in Benton County for 2024",
    )
    assert result["location"] == "corvallis"
    assert result["display_location"] == "Benton County"
    assert result["station_id"] == "crvo"
    assert "station" not in result["clarification_needed"]


def test_validate_and_fix_spec_auto_resolves_nonlocal_agrimet_city():
    result = validate_and_fix_spec({}, "How did air temperature evolve near Medford for peach orchards between 2015 and 2023?")
    assert result["display_location"] == "Medford"
    assert result["location"] == "medford"
    assert result["variables"] == ["AVG_TMP"]
    assert result["crop_filter"] == "Peach"
    assert result["station_id"] == "mdfo"
    assert result["clarification_needed"] == []


def test_validate_and_fix_spec_infers_partner_query_fields():
    result = validate_and_fix_spec(
        {},
        "How has the amount of farmland planted with alfalfa changed in Morrow County between 2014 and 2022?",
    )
    assert result["location"] == "Morrow County"
    assert result["variables"] == ["ACRES_FTR_GEOM"]
    assert result["crop_filter"] == "Alfalfa"
    assert result["start_date"] == "2014-01-01"
    assert result["end_date"] == "2022-12-31"
    assert result["evidence_pattern"] == "trend_single"


def test_validate_and_fix_spec_strips_grouping_variables_from_crop_filtered_trend_prompts():
    result = validate_and_fix_spec(
        {
            "task": "visualize_timeseries",
            "dataset": "openet",
            "location": "Deschutes County",
            "location_type": "county",
            "variables": ["per_IRRIGATED", "CROP"],
            "start_date": "2018-01-01",
            "end_date": "2024-12-31",
        },
        "How did the share of irrigated fields growing potatoes change in Deschutes County from 2018 to 2024?",
    )
    assert result["variables"] == ["per_IRRIGATED"]
    assert result["crop_filter"] == "Potato"
    assert result["evidence_pattern"] == "trend_single"
    assert "compare_by" not in result
    assert "split_by" not in result
    assert "group_by" not in result


def test_validate_and_fix_spec_summarize_crops_keeps_focus_crop():
    result = validate_and_fix_spec(
        {},
        "What crops were most commonly grown in Yamhill County between 2016 and 2023, especially corn?",
    )
    assert result["task"] == "summarize_crops"
    assert result["variables"] == ["CROP"]
    assert result["crop_filter"] == "Corn"
    assert result["display_location"] == "Yamhill County"


def test_validate_and_fix_spec_uses_sum_aggregation_for_irrigated_counts():
    result = validate_and_fix_spec(
        {},
        "How many irrigated barley fields were recorded in Baker County from 2016 to 2020?",
    )
    assert result["variables"] == ["IRR_STATUS"]
    assert result["aggregation"] == "sum"
    assert result["crop_filter"] == "Barley"


def test_validate_and_fix_spec_routes_irrigation_system_ranking_prompt():
    result = validate_and_fix_spec(
        {},
        "What irrigation systems were most often used for wheat fields in Jefferson County between 2015 and 2021?",
    )
    assert result["variables"] == ["ITYPE"]
    assert result["crop_filter"] == "Wheat"
    assert result["evidence_pattern"] == "ranking_metric"
    assert result["compare_by"] == "ITYPE"
    assert "group_by" not in result
    assert "split_by" not in result


def test_validate_and_fix_spec_routes_cross_dataset_pattern():
    result = validate_and_fix_spec(
        {
            "task": "visualize_timeseries",
            "location": "Corvallis",
            "display_location": "Corvallis",
            "variables": ["ETa", "PEN_ET", "PPT"],
            "start_date": "2015-01-01",
            "end_date": "2023-12-31",
        },
        "For hazelnut orchards in Corvallis, how did rainfall, crop water use, and water demand vary from 2015 to 2023?",
    )
    assert result["evidence_pattern"] == "cross_dataset_comparison"
    assert result["source_datasets"] == ["openet", "agrimet"]
