from core.visualizer import choose_view, payload_to_df, vega_spec


PAYLOAD = {
    "spec": {
        "task": "visualize_timeseries",
        "dataset": "agrimet",
        "location": "corvallis",
        "variables": ["OBM", "PC"],
        "chart_type": "line",
        "start_date": "2020-01-01",
        "end_date": "2020-01-03",
    },
    "data": {
        "records": [
            {"datetime": "2020-01-01", "OBM": 50.0, "PC": 0.0},
            {"datetime": "2020-01-02", "OBM": 51.0, "PC": 4.0},
            {"datetime": "2020-01-03", "OBM": 48.0, "PC": 1.0},
        ]
    },
}


def test_payload_to_df():
    spec, df, variables = payload_to_df(PAYLOAD)
    assert spec["dataset"] == "agrimet"
    assert list(df.columns) == ["OBM", "PC"]
    assert variables == ["OBM", "PC"]


def test_choose_view_for_two_similar_ranges():
    _, df, variables = payload_to_df(PAYLOAD)
    view = choose_view(df, variables, "line")
    assert view["mode"] == "single"


def test_vega_spec_has_schema():
    spec = vega_spec(PAYLOAD)
    assert spec["$schema"].startswith("https://vega.github.io/")
