"""
Tests for the agrimet_station_loader integration.

Covers every change made across the 4 files:
  - core/agrimet_station_loader.py      (new file)
  - core/location_resolver.py           (rewrote to use loader)
  - core/data_fetcher.py                (rewrote _agrimet_file_prefix + get_data_files_for_range)
  - smarttap_service.py                 (import fix for supported_agrimet_locations)

Run from the SmartTap-main/ root:
    pytest tests/test_station_loader_integration.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Make sure the project root is on sys.path so imports work
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ===========================================================================
# 1. agrimet_station_loader — the new file itself
# ===========================================================================

class TestAgrimetStationLoader:
    """Tests for core/agrimet_station_loader.py"""

    def setup_method(self):
        # Reset the module-level cache before every test
        import core.agrimet_station_loader as loader
        loader._DF = None

    def test_load_returns_dataframe(self):
        from core.agrimet_station_loader import load_agrimet_station_metadata
        df = load_agrimet_station_metadata()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_load_has_required_columns(self):
        from core.agrimet_station_loader import load_agrimet_station_metadata
        df = load_agrimet_station_metadata()
        for col in ["station_id", "title", "state", "nearest_city", "county", "latitude", "longitude"]:
            assert col in df.columns, f"Missing column: {col}"

    def test_only_oregon_stations_loaded(self):
        """Loader filters to OR stations (state == 'or') by default."""
        from core.agrimet_station_loader import load_agrimet_station_metadata
        df = load_agrimet_station_metadata()
        non_or = df[~df["state"].isin(["or", ""])]
        assert len(non_or) == 0, f"Non-OR stations found: {non_or['station_id'].tolist()}"

    def test_station_ids_are_lowercase(self):
        from core.agrimet_station_loader import load_agrimet_station_metadata
        df = load_agrimet_station_metadata()
        assert all(df["station_id"] == df["station_id"].str.lower())

    def test_no_duplicate_station_ids(self):
        from core.agrimet_station_loader import load_agrimet_station_metadata
        df = load_agrimet_station_metadata()
        assert df["station_id"].duplicated().sum() == 0

    def test_cache_returns_same_object(self):
        """Second call returns the cached DataFrame, not a new one."""
        from core.agrimet_station_loader import load_agrimet_station_metadata
        df1 = load_agrimet_station_metadata()
        df2 = load_agrimet_station_metadata()
        assert df1 is df2

    # --- find_station_record ---

    def test_find_station_record_by_station_id(self):
        from core.agrimet_station_loader import find_station_record
        record = find_station_record("crvo")
        assert record is not None
        assert record["station_id"] == "crvo"

    def test_find_station_record_by_city_name(self):
        """crvo has Corvallis as Nearest_City_2 in the CSV."""
        from core.agrimet_station_loader import find_station_record
        record = find_station_record("corvallis")
        assert record is not None
        assert record["station_id"] == "crvo"

    def test_find_station_record_by_county(self):
        from core.agrimet_station_loader import find_station_record
        record = find_station_record("benton")
        assert record is not None
        assert record["county"] == "benton"

    def test_find_station_record_county_with_suffix(self):
        """'Benton County' should strip the suffix and still match."""
        from core.agrimet_station_loader import find_station_record
        record = find_station_record("Benton County")
        assert record is not None
        assert record["county"] == "benton"

    def test_find_station_record_case_insensitive(self):
        from core.agrimet_station_loader import find_station_record
        assert find_station_record("CRVO") is not None
        assert find_station_record("Crvo") is not None
        assert find_station_record("crvo") is not None

    def test_find_station_record_unknown_returns_none(self):
        from core.agrimet_station_loader import find_station_record
        assert find_station_record("atlantis") is None

    def test_find_station_record_empty_returns_none(self):
        from core.agrimet_station_loader import find_station_record
        assert find_station_record("") is None

    # --- resolve_location_to_station_id ---

    def test_resolve_location_to_station_id_known(self):
        from core.agrimet_station_loader import resolve_location_to_station_id
        assert resolve_location_to_station_id("corvallis") == "crvo"

    def test_resolve_location_to_station_id_unknown(self):
        from core.agrimet_station_loader import resolve_location_to_station_id
        assert resolve_location_to_station_id("atlantis") is None

    # --- find_stations_for_county ---

    def test_find_stations_for_county_benton(self):
        from core.agrimet_station_loader import find_stations_for_county
        stations = find_stations_for_county("benton")
        assert isinstance(stations, list)
        assert "crvo" in stations

    def test_find_stations_for_county_with_suffix(self):
        from core.agrimet_station_loader import find_stations_for_county
        stations = find_stations_for_county("Benton County")
        assert "crvo" in stations

    def test_find_stations_for_county_unknown(self):
        from core.agrimet_station_loader import find_stations_for_county
        assert find_stations_for_county("nonexistent") == []

    def test_find_stations_for_county_empty(self):
        from core.agrimet_station_loader import find_stations_for_county
        assert find_stations_for_county("") == []

    # --- find_local_file_prefixes ---

    def test_find_local_file_prefixes_corvallis(self):
        """For crvo (Corvallis station), should return 'corvallis' as first prefix."""
        from core.agrimet_station_loader import find_local_file_prefixes
        prefixes = find_local_file_prefixes("corvallis")
        assert isinstance(prefixes, list)
        assert len(prefixes) > 0
        assert prefixes[0] == "corvallis"

    def test_find_local_file_prefixes_includes_station_id(self):
        """Station ID should always appear in the prefix list as a fallback."""
        from core.agrimet_station_loader import find_local_file_prefixes
        prefixes = find_local_file_prefixes("corvallis")
        assert "crvo" in prefixes

    def test_find_local_file_prefixes_unknown_returns_empty(self):
        from core.agrimet_station_loader import find_local_file_prefixes
        assert find_local_file_prefixes("atlantis") == []

    # --- supported_agrimet_locations ---

    def test_supported_agrimet_locations_returns_list(self):
        from core.agrimet_station_loader import supported_agrimet_locations
        locs = supported_agrimet_locations()
        assert isinstance(locs, list)
        assert len(locs) > 5

    def test_supported_agrimet_locations_contains_known(self):
        from core.agrimet_station_loader import supported_agrimet_locations
        locs = supported_agrimet_locations()
        assert "corvallis" in locs
        assert "benton" in locs
        assert "crvo" in locs

    def test_supported_agrimet_locations_sorted(self):
        from core.agrimet_station_loader import supported_agrimet_locations
        locs = supported_agrimet_locations()
        assert locs == sorted(locs)

    # --- is_supported_agrimet_location ---

    def test_is_supported_known_city(self):
        from core.agrimet_station_loader import is_supported_agrimet_location
        assert is_supported_agrimet_location("corvallis") is True

    def test_is_supported_known_station_id(self):
        from core.agrimet_station_loader import is_supported_agrimet_location
        assert is_supported_agrimet_location("crvo") is True

    def test_is_supported_known_county(self):
        from core.agrimet_station_loader import is_supported_agrimet_location
        assert is_supported_agrimet_location("benton") is True

    def test_is_supported_unknown(self):
        from core.agrimet_station_loader import is_supported_agrimet_location
        assert is_supported_agrimet_location("atlantis") is False

    def test_is_supported_empty(self):
        from core.agrimet_station_loader import is_supported_agrimet_location
        assert is_supported_agrimet_location("") is False


# ===========================================================================
# 2. location_resolver — rewrote to use loader
# ===========================================================================

class TestLocationResolver:
    """Tests for core/location_resolver.py after the rewrite."""

    def setup_method(self):
        import core.agrimet_station_loader as loader
        loader._DF = None

    def test_supported_agrimet_locations_uses_loader(self):
        """supported_agrimet_locations() must now return more than the old 5."""
        from core.location_resolver import supported_agrimet_locations
        locs = supported_agrimet_locations()
        assert len(locs) > 5, "Still using old hardcoded 5-city list!"
        assert "corvallis" in locs
        assert "benton" in locs

    def test_resolve_by_city_name(self):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("corvallis")
        assert result is not None
        assert result["station_id"] == "crvo"
        assert result["match_type"] == "station_metadata"

    def test_resolve_by_station_id(self):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("crvo")
        assert result is not None
        assert result["station_id"] == "crvo"

    def test_resolve_by_county(self):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("benton")
        assert result is not None
        assert result["county_name"] == "benton"

    def test_resolve_county_with_suffix(self):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("Benton County")
        assert result is not None
        assert result["county_name"] == "benton"

    def test_resolve_unknown_returns_none(self):
        from core.location_resolver import resolve_agrimet_location
        assert resolve_agrimet_location("atlantis") is None

    def test_resolve_returns_display_location(self):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("corvallis")
        assert result is not None
        assert result["display_location"] == "Corvallis"

    def test_resolve_returns_station_title(self):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("corvallis")
        assert result is not None
        assert "corvallis" in result.get("station_title", "").lower()

    def test_resolve_local_only_known_station(self):
        """local_only=True should still return a result for a known station."""
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("corvallis", local_only=True)
        assert result is not None

    def test_resolve_local_only_unknown_returns_none(self):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("atlantis", local_only=True)
        assert result is None

    def test_no_more_agrimet_api_import(self):
        """location_resolver must NOT import LOCATION_ALIASES from agrimet_api."""
        import core.location_resolver as lr
        assert not hasattr(lr, "LOCAL_AGRIMET_ALIASES"), \
            "OLD LOCAL_AGRIMET_ALIASES dict still present — rewrite not applied"
        assert not hasattr(lr, "AGRIMET_FRIENDLY_NAMES"), \
            "OLD AGRIMET_FRIENDLY_NAMES dict still present — rewrite not applied"

    def test_normalize_location_text(self):
        from core.location_resolver import normalize_location_text
        assert normalize_location_text("  Hood_River  ") == "hood river"
        assert normalize_location_text("CORVALLIS") == "corvallis"
        assert normalize_location_text("") == ""

    def test_strip_county_suffix(self):
        from core.location_resolver import strip_county_suffix
        assert strip_county_suffix("Benton County") == "benton"
        assert strip_county_suffix("benton") == "benton"

    def test_display_location_name_city(self):
        from core.location_resolver import display_location_name
        assert display_location_name("corvallis") == "Corvallis"

    def test_display_location_name_county(self):
        from core.location_resolver import display_location_name
        assert display_location_name("benton county") == "Benton County"
        assert display_location_name("benton", location_type="county") == "Benton County"


# ===========================================================================
# 3. data_fetcher — _agrimet_file_prefix and get_data_files_for_range
# ===========================================================================

class TestDataFetcherPrefixResolution:
    """
    Tests for the rewritten _agrimet_file_prefix and get_data_files_for_range
    in core/data_fetcher.py.

    We mock the filesystem so tests don't depend on real CSV files being present.
    """

    def setup_method(self):
        import core.agrimet_station_loader as loader
        loader._DF = None

    def test_no_more_agrimet_friendly_names_dict(self):
        """The old hardcoded 5-city dict must be gone from data_fetcher."""
        import core.data_fetcher as df_module
        assert not hasattr(df_module, "AGRIMET_FRIENDLY_NAMES"), \
            "OLD AGRIMET_FRIENDLY_NAMES dict still present in data_fetcher — rewrite not applied"

    def test_agrimet_file_prefix_corvallis(self):
        """For 'corvallis', prefix should be 'corvallis' (city name, not station code)."""
        from core.data_fetcher import _agrimet_file_prefix, AGRIMET_DIR
        # Mock the glob to pretend corvallis_weather_*.csv exists on disk
        with patch.object(Path, "glob", return_value=[AGRIMET_DIR / "corvallis_weather_2024.csv"]):
            prefix = _agrimet_file_prefix("corvallis")
        assert prefix == "corvallis"

    def test_agrimet_file_prefix_falls_back_to_station_id(self):
        """If no files match city name, falls back to station ID prefix."""
        from core.data_fetcher import _agrimet_file_prefix, AGRIMET_DIR
        # First glob (city name) returns nothing, second glob (station id) returns a file
        call_count = 0
        def fake_glob(pattern):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return []  # city prefix not found
            return [AGRIMET_DIR / "crvo_weather_2024.csv"]  # station id found
        with patch.object(Path, "glob", side_effect=fake_glob):
            prefix = _agrimet_file_prefix("corvallis")
        assert prefix == "crvo"

    def test_agrimet_file_prefix_unknown_raises(self):
        """Unknown location with no matching files should raise ValueError."""
        from core.data_fetcher import _agrimet_file_prefix
        with patch.object(Path, "glob", return_value=[]):
            with pytest.raises(ValueError, match="Unknown AgriMet location"):
                _agrimet_file_prefix("atlantis")

    def test_get_data_files_for_range_finds_files(self):
        """get_data_files_for_range should find corvallis_weather_YYYY.csv files."""
        from core.data_fetcher import get_data_files_for_range, AGRIMET_DIR
        fake_files = [
            AGRIMET_DIR / "corvallis_weather_2023.csv",
            AGRIMET_DIR / "corvallis_weather_2024.csv",
        ]
        with patch.object(Path, "exists", return_value=True):
            with patch.object(Path, "glob", return_value=fake_files):
                files = get_data_files_for_range("corvallis", "2023-01-01", "2024-12-31")
        assert len(files) > 0

    def test_get_data_files_for_range_returns_empty_if_no_files(self):
        """Returns empty list when no files exist, does not raise."""
        from core.data_fetcher import get_data_files_for_range
        with patch.object(Path, "exists", return_value=False):
            with patch.object(Path, "glob", return_value=[]):
                files = get_data_files_for_range("corvallis", "2024-01-01", "2024-12-31")
        assert files == []

    def test_get_data_files_tries_multiple_prefixes(self):
        """If city-name prefix has no files, should try station-ID prefix next."""
        from core.data_fetcher import get_data_files_for_range, AGRIMET_DIR
        crvo_file = AGRIMET_DIR / "crvo_weather_2024.csv"

        def fake_exists(self):
            return "crvo" in str(self)

        with patch.object(Path, "exists", fake_exists):
            files = get_data_files_for_range("corvallis", "2024-01-01", "2024-12-31")
        assert any("crvo" in str(f) for f in files)

    def test_normalize_agrimet_spec_fills_station_id(self):
        """_normalize_agrimet_spec should enrich spec with station_id from the loader."""
        from core.data_fetcher import _normalize_agrimet_spec
        spec = {"location": "corvallis", "variables": ["OBM"]}
        result = _normalize_agrimet_spec(spec)
        assert result.get("station_id") == "crvo"

    def test_normalize_agrimet_spec_fills_display_location(self):
        from core.data_fetcher import _normalize_agrimet_spec
        spec = {"location": "corvallis"}
        result = _normalize_agrimet_spec(spec)
        assert result.get("display_location") == "Corvallis"


# ===========================================================================
# 4. smarttap_service — import fix for supported_agrimet_locations
# ===========================================================================

class TestSmartTapServiceImport:
    """
    Verifies that smarttap_service imports supported_agrimet_locations
    from location_resolver, not from data_fetcher.
    """

    def test_supported_agrimet_locations_not_from_data_fetcher(self):
        """data_fetcher must NOT export supported_agrimet_locations."""
        import core.data_fetcher as df_module
        assert not hasattr(df_module, "supported_agrimet_locations"), (
            "supported_agrimet_locations is still exported from data_fetcher. "
            "Remove it and import from location_resolver in smarttap_service.py instead."
        )

    def test_supported_agrimet_locations_available_in_resolver(self):
        """location_resolver must export supported_agrimet_locations."""
        from core.location_resolver import supported_agrimet_locations
        locs = supported_agrimet_locations()
        assert isinstance(locs, list)
        assert len(locs) > 5

    def test_smarttap_service_can_call_supported_locations(self):
        """
        The function used in _build_clarification_prompt must be callable
        and return more than the old 5-city hardcoded list.
        """
        # Import the function the same way smarttap_service.py now does
        from core.location_resolver import supported_agrimet_locations
        result = supported_agrimet_locations()
        assert len(result) > 5, (
            f"Only {len(result)} locations returned — "
            "still using old hardcoded list instead of loader"
        )


# ===========================================================================
# 5. Regression — old hardcoded locations still work
# ===========================================================================

class TestRegressionOldLocations:
    """
    The 5 locations that worked before must still work after the changes.
    """

    def setup_method(self):
        import core.agrimet_station_loader as loader
        loader._DF = None

    @pytest.mark.parametrize("location,expected_id", [
        ("corvallis", "crvo"),
        ("ontario",   "onto"),
        ("pendleton", "ptro"),
    ])
    def test_old_locations_still_resolve(self, location, expected_id):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location(location)
        assert result is not None, f"'{location}' no longer resolves"
        assert result["station_id"] == expected_id, (
            f"'{location}' resolved to {result['station_id']}, expected {expected_id}"
        )

    @pytest.mark.parametrize("location", [
        "corvallis", "ontario", "pendleton",
    ])
    def test_old_locations_in_supported_list(self, location):
        from core.location_resolver import supported_agrimet_locations
        assert location in supported_agrimet_locations()

    @pytest.mark.parametrize("location", [
        "corvallis", "ontario", "pendleton",
    ])
    def test_old_locations_have_file_prefixes(self, location):
        from core.agrimet_station_loader import find_local_file_prefixes
        prefixes = find_local_file_prefixes(location)
        assert len(prefixes) > 0, f"No file prefixes for '{location}'"


# ===========================================================================
# 6. New locations — things that couldn't work before but should now
# ===========================================================================

class TestNewLocationsNowWork:
    """
    Locations that were OUTSIDE the old 5-city hardcoded list but are in
    the full metadata CSV — these should now resolve correctly.
    """

    def setup_method(self):
        import core.agrimet_station_loader as loader
        loader._DF = None

    @pytest.mark.parametrize("location,expected_station", [
        ("bend",      "abpo"),   # first bend station in CSV
        ("hood river","hoxo"),
        ("benton",    "crvo"),   # county lookup
        ("klamath",   "agko"),   # county lookup
        ("hoxo",      "hoxo"),   # direct station ID
    ])
    def test_new_location_resolves(self, location, expected_station):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location(location)
        assert result is not None, f"'{location}' did not resolve — should work now"

    def test_county_lookup_returns_station(self):
        from core.location_resolver import resolve_agrimet_location
        result = resolve_agrimet_location("deschutes")
        assert result is not None
        assert result["county_name"] == "deschutes"

    def test_many_more_locations_available(self):
        from core.location_resolver import supported_agrimet_locations
        from core.agrimet_station_loader import load_agrimet_station_metadata
        df = load_agrimet_station_metadata()
        locs = supported_agrimet_locations()
        # Should have at least as many entries as there are stations
        assert len(locs) >= len(df), (
            f"supported_agrimet_locations returns {len(locs)} entries "
            f"but metadata has {len(df)} stations"
        )
