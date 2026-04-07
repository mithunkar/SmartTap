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
