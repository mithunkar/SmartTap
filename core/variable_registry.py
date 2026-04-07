from __future__ import annotations

from typing import Dict


AGRIMET_VARIABLE_LABELS: Dict[str, str] = {
    "OBM": "Avg Temp (°F)",
    "MX": "Max Temp (°F)",
    "MN": "Min Temp (°F)",
    "PC": "Precipitation (mm)",
    "SR": "Solar Radiation (Langleys)",
    "WS": "Wind Speed (mph)",
    "TU": "Humidity (%)",
    "ET": "Evapotranspiration (mm)",
    "PEN_ET": "Reference Evapotranspiration",
    "24_HR_PCP": "24-Hour Precipitation",
    "AVG_TMP": "Avg Temp (°F)",
    "AVG_HUM": "Humidity (%)",
    "AV_WSPD": "Wind Speed (mph)",
    "Kc": "Crop Coefficient",
}


OPENET_VARIABLE_LABELS: Dict[str, str] = {
    "ETa": "Evapotranspiration (in)",
    "PPT": "Precipitation (in)",
    "AW": "Applied Water (acre-ft)",
    "WS_C": "Water Stress Coefficient",
    "P_rz": "Root Zone Precip (in)",
    "AREA": "Farmland Area (acres)",
    "ACRES_FTR_GEOM": "Farmland Area (acres)",
    "CROP": "Crop Field Count",
    "IRR_STATUS": "Irrigated Fields",
    "per_IRRIGATED": "Irrigated Share (%)",
    "IRR_EFF": "Irrigation Efficiency",
    "ITYPE": "Irrigation System Mode",
}


VARIABLE_LABELS: Dict[str, str] = {**AGRIMET_VARIABLE_LABELS, **OPENET_VARIABLE_LABELS}


OPENET_VARIABLE_ALIASES: Dict[str, str] = {
    "eta": "ETa",
    "et": "ETa",
    "ppt": "PPT",
    "precip": "PPT",
    "precipitation": "PPT",
    "aw": "AW",
    "ws": "WS_C",
    "wsc": "WS_C",
    "area": "AREA",
    "acres": "AREA",
    "acreage": "AREA",
    "farmland": "AREA",
    "crop": "CROP",
    "crops": "CROP",
    "irrigated": "IRR_STATUS",
    "irrigation_status": "IRR_STATUS",
    "percent_irrigated": "per_IRRIGATED",
    "irrigated_share": "per_IRRIGATED",
    "irrigation_share": "per_IRRIGATED",
    "irrigation_efficiency": "IRR_EFF",
    "irrigation_system": "ITYPE",
}


OPENET_VARIABLES = frozenset(OPENET_VARIABLE_LABELS.keys())
AGRIMET_VARIABLES = frozenset(AGRIMET_VARIABLE_LABELS.keys())


def variable_label(variable: str) -> str:
    return VARIABLE_LABELS.get(variable, variable)


def normalize_openet_variable(variable: str) -> str:
    cleaned = (variable or "").strip()
    return OPENET_VARIABLE_ALIASES.get(cleaned.lower(), cleaned)

