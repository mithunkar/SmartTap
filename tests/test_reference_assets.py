from __future__ import annotations

from core.agrimet_station_loader import load_agrimet_station_metadata
from core.paths import (
    AGRIMET_STATIONS_METADATA,
    CDL_CODES_CSV,
    CROP_NAME_KEYWORDS_JSON,
    OPENET_DATA_ACCESS_GUIDE_DOCX,
    OPENET_DATA_FIELDS_HTML,
    OPENET_VARIABLE_KEYWORDS_JSON,
)
from llm.interpretation import load_keyword_mappings


def test_reference_assets_exist_in_tracked_reference_dir():
    for path in [
        AGRIMET_STATIONS_METADATA,
        CDL_CODES_CSV,
        OPENET_VARIABLE_KEYWORDS_JSON,
        CROP_NAME_KEYWORDS_JSON,
        OPENET_DATA_FIELDS_HTML,
        OPENET_DATA_ACCESS_GUIDE_DOCX,
    ]:
        assert path.exists(), f"Missing reference asset: {path}"


def test_agrimet_station_metadata_loads_from_reference_dir():
    df = load_agrimet_station_metadata()
    assert not df.empty
    assert AGRIMET_STATIONS_METADATA.exists()


def test_keyword_mappings_load_from_reference_dir():
    variable_keywords, crop_keywords = load_keyword_mappings()
    assert variable_keywords
    assert crop_keywords
