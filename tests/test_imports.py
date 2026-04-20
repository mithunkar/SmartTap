import importlib
import sys
from pathlib import Path


def test_cli_import_does_not_require_ollama():
    sys.modules.pop("smarttap", None)
    sys.modules.pop("llm.interpretation", None)
    module = importlib.import_module("smarttap")
    assert hasattr(module, "main")


def test_ui_import_is_safe():
    sys.modules.pop("smarttap_ui", None)
    module = importlib.import_module("smarttap_ui")
    assert hasattr(module, "main")


def test_ui_open_confirmation_editor_preserves_confirmation_context():
    sys.modules.pop("smarttap_ui", None)
    module = importlib.import_module("smarttap_ui")
    state = {
        "confirmation_spec": {
            "location": "Corvallis",
            "display_location": "Corvallis",
            "crop_filter": "Mint",
            "variables": ["OBM"],
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
        },
        "original_query": "show me temperature in Corvallis for 2024",
        "confirmation_editor_open": False,
        "confirmation_edit_field": None,
        "confirmation_edit_text": "",
        "confirmation_edit_start_date": None,
        "confirmation_edit_end_date": None,
        "confirmation_edit_metric": None,
    }

    module._open_confirmation_editor(state)

    assert state["confirmation_spec"]["location"] == "Corvallis"
    assert state["original_query"] == "show me temperature in Corvallis for 2024"
    assert state["confirmation_editor_open"] is True
    assert state["confirmation_edit_field"] == "crop"
    assert state["confirmation_edit_text"] == "Mint"


def test_ui_cancel_confirmation_editor_keeps_confirmation_state():
    sys.modules.pop("smarttap_ui", None)
    module = importlib.import_module("smarttap_ui")
    state = {
        "confirmation_spec": {"location": "Corvallis"},
        "original_query": "show me temperature in Corvallis for 2024",
        "confirmation_editor_open": True,
        "confirmation_edit_field": "location",
        "confirmation_edit_text": "Salem",
        "confirmation_edit_start_date": None,
        "confirmation_edit_end_date": None,
        "confirmation_edit_metric": "OBM",
    }

    module._close_confirmation_editor(state)

    assert state["confirmation_spec"] == {"location": "Corvallis"}
    assert state["original_query"] == "show me temperature in Corvallis for 2024"
    assert state["confirmation_editor_open"] is False
    assert state["confirmation_edit_field"] is None
    assert state["confirmation_edit_text"] == "Salem"


def test_ui_confirmation_editor_does_not_route_chat_as_followup():
    sys.modules.pop("smarttap_ui", None)
    module = importlib.import_module("smarttap_ui")
    action = module._next_query_action(
        "make the crop winter wheat",
        followup_mode=None,
        pending_spec=None,
        original_query="show me temperature in Corvallis for 2024",
    )

    assert action == "new_query"


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


def test_interpretation_prompt_no_longer_mentions_compare_locations():
    prompt = (Path(__file__).resolve().parent.parent / "prompts" / "interpretation.txt").read_text()
    assert "compare_locations" not in prompt
