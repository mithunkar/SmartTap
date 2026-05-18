from __future__ import annotations

import pandas as pd

from scripts.fetch_agrimet_data import derive_daily_precip, validate_station_frame


def test_derive_daily_precip_marks_non_water_year_resets_as_anomalies():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2019-03-09", "2019-03-10", "2019-03-11"]),
            "cum_precip_in": [20.20, 20.19, 20.25],
        }
    )

    daily, anomaly_count = derive_daily_precip(frame)

    assert anomaly_count == 1
    assert pd.isna(daily.iloc[1])
    assert daily.iloc[2] == 0.06


def test_derive_daily_precip_treats_water_year_boundary_as_reset():
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-09-30", "2024-10-01", "2024-10-02"]),
            "cum_precip_in": [4.0, 0.2, 0.35],
        }
    )

    daily, anomaly_count = derive_daily_precip(frame)

    assert anomaly_count == 0
    assert daily.iloc[1] == 0.2
    assert daily.iloc[2] == 0.15


def test_validate_station_frame_rejects_missing_wind_sensor_coverage():
    dates = pd.date_range("2024-01-01", periods=366, freq="D")
    frame = pd.DataFrame(
        {
            "date": dates,
            "max_temp_f": [70.0] * len(dates),
            "min_temp_f": [40.0] * len(dates),
            "cum_precip_in": [0.0] * len(dates),
            "solar_langley": [12.0] * len(dates),
            "wind_speed_mph": [pd.NA] * len(dates),
        }
    )

    is_valid, reason = validate_station_frame(frame, 2024)

    assert is_valid is False
    assert reason == "missing wind sensor coverage"
