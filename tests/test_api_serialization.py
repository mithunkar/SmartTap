from __future__ import annotations

from datetime import date, datetime

import pandas as pd

from smarttap_api import chart_model_from_vega, dataframe_payload, serialize_visualization_result, to_jsonable


def test_dataframe_payload_serializes_columns_and_records():
    df = pd.DataFrame(
        [
            {"datetime": pd.Timestamp("2024-01-01"), "value": 1.25, "label": "A"},
            {"datetime": pd.Timestamp("2024-01-02"), "value": None, "label": "B"},
        ]
    )

    payload = dataframe_payload(df)

    assert payload is not None
    assert payload.columns == ["datetime", "value", "label"]
    assert payload.records[0]["datetime"] == "2024-01-01T00:00:00"
    assert payload.records[1]["value"] is None


def test_to_jsonable_handles_nested_datetime_and_path_values(tmp_path):
    payload = to_jsonable(
        {
            "generated_at": datetime(2024, 1, 2, 3, 4, 5),
            "window_start": date(2024, 1, 1),
            "file": tmp_path / "example.json",
            "items": [pd.Timestamp("2024-01-03")],
        }
    )

    assert payload["generated_at"] == "2024-01-02T03:04:05"
    assert payload["window_start"] == "2024-01-01"
    assert payload["file"].endswith("example.json")
    assert payload["items"] == ["2024-01-03T00:00:00"]


def test_serialize_visualization_result_encodes_primary_and_secondary_views():
    result = serialize_visualization_result(
        {
            "success": True,
            "needs_clarification": False,
            "needs_confirmation": False,
            "error": None,
            "spec": {"task": "visualize_timeseries"},
            "summary": {"row_count": 1},
            "explanation": "One row returned.",
            "data_preview": pd.DataFrame([{"datetime": "2024-01-01", "OBM": 42.0}]),
            "data": pd.DataFrame([{"datetime": "2024-01-01", "OBM": 42.0}]),
            "chart_bytes": b"png-bytes",
            "vega_spec": {
                "mark": "line",
                "data": {"values": [{"datetime": "2024-01-01", "OBM": 42.0}]},
                "encoding": {
                    "x": {"field": "datetime", "type": "temporal"},
                    "y": {"field": "OBM", "type": "quantitative", "title": "Average Temperature (deg F)"},
                },
            },
            "secondary_views": [
                {
                    "caption": "Companion",
                    "chart_bytes": b"secondary-bytes",
                    "data_preview": pd.DataFrame([{"label": "A", "value": 1}]),
                    "vega_spec": {
                        "mark": "bar",
                        "data": {"values": [{"label": "A", "value": 1}]},
                        "encoding": {
                            "x": {"field": "label", "type": "nominal"},
                            "y": {"field": "value", "type": "quantitative"},
                        },
                    },
                    "files": {"png": "outputs/secondary.png"},
                }
            ],
            "files": {"png": "outputs/primary.png"},
            "validation_report": {"status": "ok"},
            "clarification_prompt": None,
            "confirmation_prompt": None,
            "clarification_fields": [],
        }
    )

    assert result.chart_image_url is not None
    assert result.chart_image_url.startswith("data:image/png;base64,")
    assert result.chart_model is not None
    assert result.chart_model.kind == "line"
    assert result.chart_model.x_key == "datetime"
    assert result.secondary_views[0].chart_image_url is not None
    assert result.secondary_views[0].chart_model is not None
    assert result.secondary_views[0].chart_model.kind == "bar"
    assert result.secondary_views[0].data_preview is not None
    assert result.secondary_views[0].data_preview.records[0]["label"] == "A"


def test_chart_model_from_vega_handles_horizontal_bar_and_donut():
    bar_model = chart_model_from_vega(
        {
            "title": "Top Crops",
            "data": {"values": [{"Crop": "Mint", "Field Count": 12}, {"Crop": "Wheat", "Field Count": 8}]},
            "mark": "bar",
            "encoding": {
                "y": {"field": "Crop", "type": "nominal"},
                "x": {"field": "Field Count", "type": "quantitative", "title": "Number of Fields"},
                "color": {"field": "Group", "type": "nominal", "legend": {"title": "Crop Group"}},
            },
        }
    )

    donut_model = chart_model_from_vega(
        {
            "title": "Distribution",
            "data": {"values": [{"Group": "Hay", "Field Count": 10}, {"Group": "Grain", "Field Count": 5}]},
            "mark": {"type": "arc", "innerRadius": 50},
            "encoding": {
                "theta": {"field": "Field Count", "type": "quantitative", "title": "Fields"},
                "color": {"field": "Group", "type": "nominal", "legend": {"title": "Crop Group"}},
            },
        }
    )

    assert bar_model is not None
    assert bar_model.kind == "bar"
    assert bar_model.horizontal is True
    assert bar_model.x_key == "Crop"

    assert donut_model is not None
    assert donut_model.kind == "donut"
    assert donut_model.x_key == "Group"
    assert donut_model.series[0].key == "Field Count"


def test_chart_model_from_vega_handles_grouped_and_stacked_bars():
    grouped_model = chart_model_from_vega(
        {
            "title": "Grouped Summary",
            "data": {
                "values": [
                    {"group": "A", "variable": "ETa", "value": 2.0},
                    {"group": "A", "variable": "PPT", "value": 1.0},
                    {"group": "B", "variable": "ETa", "value": 3.0},
                    {"group": "B", "variable": "PPT", "value": 1.5},
                ]
            },
            "mark": "bar",
            "encoding": {
                "x": {"field": "group", "type": "nominal"},
                "y": {"field": "value", "type": "quantitative"},
                "color": {"field": "variable", "type": "nominal", "title": "Variable"},
            },
        }
    )

    stacked_model = chart_model_from_vega(
        {
            "title": "Yearly Breakdown",
            "data": {
                "values": [
                    {"year": "2020", "group": "Drip", "field_count": 5},
                    {"year": "2020", "group": "Pivot", "field_count": 3},
                    {"year": "2021", "group": "Drip", "field_count": 4},
                    {"year": "2021", "group": "Pivot", "field_count": 6},
                ]
            },
            "mark": "bar",
            "encoding": {
                "x": {"field": "year", "type": "nominal"},
                "y": {"field": "field_count", "type": "quantitative", "stack": "zero"},
                "color": {"field": "group", "type": "nominal", "title": "Irrigation System"},
            },
        }
    )

    assert grouped_model is not None
    assert grouped_model.kind == "bar"
    assert grouped_model.stacked is False
    assert grouped_model.series[0].key == "Crop Water Use (in)"
    assert grouped_model.rows[0]["group"] == "A"

    assert stacked_model is not None
    assert stacked_model.kind == "bar"
    assert stacked_model.stacked is True
    assert stacked_model.series[0].key == "Drip"


def test_chart_model_from_vega_handles_faceted_multi_line():
    model = chart_model_from_vega(
        {
            "title": "Grouped Comparison",
            "data": {
                "values": [
                    {"datetime": "2024-01-01", "group": "North", "variable": "ETa", "value": 1.0},
                    {"datetime": "2024-01-01", "group": "South", "variable": "ETa", "value": 2.0},
                    {"datetime": "2024-01-01", "group": "North", "variable": "PPT", "value": 3.0},
                    {"datetime": "2024-01-01", "group": "South", "variable": "PPT", "value": 4.0},
                ]
            },
            "facet": {"field": "variable", "type": "nominal"},
            "spec": {
                "mark": {"type": "line", "point": True},
                "encoding": {
                    "x": {"field": "datetime", "type": "temporal"},
                    "y": {"field": "value", "type": "quantitative"},
                    "color": {"field": "group", "type": "nominal", "title": "County"},
                },
            },
        }
    )

    assert model is not None
    assert model.kind == "line"
    assert model.series[0].key == "Crop Water Use (in) • North"
    assert model.series[1].key == "Crop Water Use (in) • South"
