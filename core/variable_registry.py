from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List


@dataclass(frozen=True)
class VariableMetadata:
    code: str
    dataset: str
    label: str
    units: str = ""
    default_aggregation: str = "mean"
    aliases: tuple[str, ...] = ()

    @property
    def chart_label(self) -> str:
        return self.label if not self.units else f"{self.label} ({self.units})"


def _clean(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
    return " ".join(cleaned.split())


def _metadata(
    code: str,
    dataset: str,
    label: str,
    *,
    units: str = "",
    default_aggregation: str = "mean",
    aliases: Iterable[str] = (),
) -> VariableMetadata:
    return VariableMetadata(
        code=code,
        dataset=dataset,
        label=label,
        units=units,
        default_aggregation=default_aggregation,
        aliases=tuple(_clean(value) for value in aliases if _clean(value)),
    )


VARIABLE_REGISTRY: Dict[str, VariableMetadata] = {
    "OBM": _metadata(
        "OBM",
        "agrimet",
        "Average Temperature",
        units="deg F",
        aliases=("temperature", "average temperature", "avg temp", "temp"),
    ),
    "MX": _metadata("MX", "agrimet", "Maximum Temperature", units="deg F", aliases=("max temperature", "high temp")),
    "MN": _metadata("MN", "agrimet", "Minimum Temperature", units="deg F", aliases=("min temperature", "low temp")),
    "PC": _metadata(
        "PC",
        "agrimet",
        "Precipitation",
        units="mm",
        aliases=("precipitation", "rain", "rainfall", "daily precipitation"),
    ),
    "SR": _metadata("SR", "agrimet", "Solar Radiation", units="Langleys", aliases=("solar radiation", "sun")),
    "WS": _metadata("WS", "agrimet", "Wind Speed", units="mph", aliases=("wind speed",)),
    "TU": _metadata("TU", "agrimet", "Humidity", units="percent", aliases=("humidity", "relative humidity")),
    "ET": _metadata("ET", "agrimet", "Evapotranspiration", units="mm", aliases=("evapotranspiration",)),
    "PEN_ET": _metadata(
        "PEN_ET",
        "agrimet",
        "Reference Evapotranspiration",
        units="mm",
        aliases=("reference evapotranspiration", "atmospheric water demand", "water demand"),
    ),
    "24_HR_PCP": _metadata(
        "24_HR_PCP",
        "agrimet",
        "24-Hour Precipitation",
        units="mm",
        default_aggregation="raw",
        aliases=("24 hour precipitation", "24-hour precipitation", "rainfall accumulate", "rainfall accumulated", "rainfall accumulation"),
    ),
    "AVG_TMP": _metadata(
        "AVG_TMP",
        "agrimet",
        "Average Temperature",
        units="deg F",
        default_aggregation="raw",
        aliases=("air temperature", "average air temperature", "temperature evolution"),
    ),
    "AVG_HUM": _metadata(
        "AVG_HUM",
        "agrimet",
        "Average Humidity",
        units="percent",
        default_aggregation="raw",
        aliases=("humidity levels", "average humidity"),
    ),
    "AV_WSPD": _metadata(
        "AV_WSPD",
        "agrimet",
        "Average Wind Speed",
        units="mph",
        default_aggregation="raw",
        aliases=("wind patterns", "wind speed patterns", "average wind speed"),
    ),
    "Kc": _metadata(
        "Kc",
        "agrimet",
        "Crop Coefficient",
        default_aggregation="raw",
        aliases=("crop coefficient", "growth characteristic", "growth characteristics", "crop growth characteristics"),
    ),
    "ETa": _metadata(
        "ETa",
        "openet",
        "Crop Water Use",
        units="in",
        aliases=("eta", "evapotranspiration", "crop water use", "plant water use"),
    ),
    "ETDa": _metadata(
        "ETDa",
        "openet",
        "Potential Crop Water Demand",
        aliases=("etda", "potential water need", "potential water needs", "potential crop water demand"),
    ),
    "PPT": _metadata(
        "PPT",
        "openet",
        "Precipitation",
        units="in",
        aliases=("field precipitation", "field rainfall", "rainfall patterns", "precipitation"),
    ),
    "Prz": _metadata(
        "Prz",
        "openet",
        "Usable Rainfall",
        units="in",
        aliases=("usable rainfall", "usable rain", "effective rainfall"),
    ),
    "AW": _metadata(
        "AW",
        "openet",
        "Applied Water",
        units="acre-ft",
        default_aggregation="sum",
        aliases=(
            "applied water",
            "water applied",
            "water was applied",
            "irrigation water applied",
            "irrigation water was applied",
        ),
    ),
    "NIWR": _metadata(
        "NIWR",
        "openet",
        "Net Irrigation Water Requirement",
        aliases=("niwr", "irrigation demand", "net irrigation water requirement"),
    ),
    "IRR_CU_VOLUMEadj": _metadata(
        "IRR_CU_VOLUMEadj",
        "openet",
        "Adjusted Irrigation Consumptive Use",
        default_aggregation="sum",
        aliases=(
            "irrigation water consumed",
            "irrigation water was consumed",
            "water was consumed",
            "consumptive use",
            "irrigation consumed",
        ),
    ),
    "WS_C": _metadata("WS_C", "openet", "Water Stress Coefficient", aliases=("water stress", "stress coefficient")),
    "P_rz": _metadata("P_rz", "openet", "Root Zone Precipitation", units="in", aliases=("root zone precipitation", "root zone rain")),
    "AREA": _metadata("AREA", "openet", "Farmland Area", units="acres", default_aggregation="sum", aliases=("area", "farmland area")),
    "ACRES_FTR_GEOM": _metadata(
        "ACRES_FTR_GEOM",
        "openet",
        "Farmland Area",
        units="acres",
        default_aggregation="sum",
        aliases=("farmland planted", "farmland area", "acreage", "farm area", "largest farm areas"),
    ),
    "CROP": _metadata(
        "CROP",
        "openet",
        "Crop Category",
        aliases=(
            "crop category",
            "crop categories",
            "crop type",
            "crop types",
            "which crops",
            "what crops",
            "grown crops",
            "most commonly grown",
            "most grown",
        ),
    ),
    "IRR_STATUS": _metadata(
        "IRR_STATUS",
        "openet",
        "Irrigated Fields",
        default_aggregation="sum",
        aliases=("irrigated field", "irrigated fields", "irrigation presence"),
    ),
    "per_IRRIGATED": _metadata(
        "per_IRRIGATED",
        "openet",
        "Irrigated Share",
        units="percent",
        aliases=("share of irrigated", "irrigated share", "percent irrigated"),
    ),
    "IRR_EFF": _metadata("IRR_EFF", "openet", "Irrigation Efficiency", aliases=("irrigation efficiency",)),
    "ITYPE": _metadata(
        "ITYPE",
        "openet",
        "Irrigation System",
        aliases=("irrigation system", "irrigation systems", "irrigation method", "irrigation methods"),
    ),
}


OPENET_VARIABLES = frozenset(code for code, metadata in VARIABLE_REGISTRY.items() if metadata.dataset == "openet")
AGRIMET_VARIABLES = frozenset(code for code, metadata in VARIABLE_REGISTRY.items() if metadata.dataset == "agrimet")

_ALIAS_TO_CODE: Dict[str, str] = {}
for code, metadata in VARIABLE_REGISTRY.items():
    for alias in {code.lower(), _clean(code), *metadata.aliases}:
        if alias and alias not in _ALIAS_TO_CODE:
            _ALIAS_TO_CODE[alias] = code


def get_variable_metadata(variable: str) -> VariableMetadata | None:
    return VARIABLE_REGISTRY.get(normalize_variable(variable))


def variable_dataset(variable: str) -> str:
    metadata = get_variable_metadata(variable)
    return metadata.dataset if metadata else ""


def variable_label(variable: str) -> str:
    metadata = get_variable_metadata(variable)
    return metadata.chart_label if metadata else str(variable)


def variable_units(variable: str) -> str:
    metadata = get_variable_metadata(variable)
    return metadata.units if metadata else ""


def chart_label(variable: str) -> str:
    metadata = get_variable_metadata(variable)
    return metadata.chart_label if metadata else str(variable)


def variable_default_aggregation(variable: str) -> str:
    metadata = get_variable_metadata(variable)
    return metadata.default_aggregation if metadata else "mean"


def default_aggregation_for_variables(variables: Iterable[str]) -> str:
    aggregations = [variable_default_aggregation(variable) for variable in variables if str(variable).strip()]
    if not aggregations:
        return "mean"

    first = aggregations[0]
    if all(value == first for value in aggregations):
        return first
    return "mean"


def normalize_variable(variable: str) -> str:
    cleaned = _clean(variable)
    if not cleaned:
        return str(variable or "").strip()
    return _ALIAS_TO_CODE.get(cleaned, str(variable).strip())


def normalize_openet_variable(variable: str) -> str:
    normalized = normalize_variable(variable)
    return normalized if normalized in OPENET_VARIABLES else str(variable).strip()


def infer_variables_from_text(text: str) -> List[str]:
    query = f" {_clean(text)} "
    matches: List[tuple[int, str]] = []
    for code, metadata in VARIABLE_REGISTRY.items():
        best_score = 0
        for alias in metadata.aliases:
            if alias and f" {alias} " in query:
                best_score = max(best_score, len(alias))
        if best_score:
            matches.append((best_score, code))

    matches.sort(key=lambda item: (-item[0], item[1]))
    ordered: List[str] = []
    seen = set()
    for _, code in matches:
        if code not in seen:
            ordered.append(code)
            seen.add(code)
    return ordered


def variables_for_dataset(dataset: str) -> List[VariableMetadata]:
    normalized = str(dataset or "").lower().strip()
    return [metadata for metadata in VARIABLE_REGISTRY.values() if metadata.dataset == normalized]
