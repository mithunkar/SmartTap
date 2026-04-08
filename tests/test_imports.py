import importlib
import sys


def test_cli_import_does_not_require_ollama():
    sys.modules.pop("smarttap", None)
    sys.modules.pop("llm.interpretation", None)
    module = importlib.import_module("smarttap")
    assert hasattr(module, "main")


def test_ui_import_is_safe():
    sys.modules.pop("smarttap_ui", None)
    module = importlib.import_module("smarttap_ui")
    assert hasattr(module, "main")


def test_ui_detects_new_query_prompt():
    sys.modules.pop("smarttap_ui", None)
    module = importlib.import_module("smarttap_ui")
    assert module._looks_like_new_query("show me precipitation in 2024") is True
    assert module._looks_like_new_query("Corvallis") is False


def test_ui_display_spec_filters_internal_and_empty_fields():
    sys.modules.pop("smarttap_ui", None)
    module = importlib.import_module("smarttap_ui")
    display = module._display_spec(
        {
            "task": "visualize_timeseries",
            "location": "Corvallis",
            "clarification_needed": ["time_range"],
            "notes": ["internal note"],
            "station_id": "",
        }
    )
    assert display["task"] == "visualize_timeseries"
    assert display["location"] == "Corvallis"
    assert display["clarification_needed"] == ["time_range"]
    assert "notes" not in display
    assert "station_id" not in display
