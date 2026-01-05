import base64
import io
from typing import Dict, Any, List, Tuple

import pandas as pd
import matplotlib.pyplot as plt


VAR_LABELS = {
    "OBM": "Air Temp (°C)",
    "PC": "Precipitation (mm)",
    "TU": "Humidity (%)",
    "ET": "Evapotranspiration (mm)",
}

def _json_safe_records(df: pd.DataFrame) -> list[dict]:
    """Convert datetime-like objects into JSON-safe strings."""
    out = df.to_dict(orient="records")
    for r in out:
        if "datetime" in r:
            r["datetime"] = pd.to_datetime(r["datetime"]).isoformat()
    return out

def _label(v: str) -> str:
    return VAR_LABELS.get(v, v)

def payload_to_df(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], pd.DataFrame, List[str]]:
    if "spec" not in payload or "data" not in payload:
        raise ValueError("Expected payload with keys: spec, data")

    spec = payload["spec"]
    records = payload["data"].get("records") or []
    if not records:
        raise ValueError("No records in payload.data.records")

    df = pd.DataFrame.from_records(records)

    if "datetime" not in df.columns:
        if "DATETIME" in df.columns:
            df = df.rename(columns={"DATETIME": "datetime"})
        else:
            raise ValueError("Records must include 'datetime' (or 'DATETIME')")

    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()

    requested = spec.get("variables") or [c for c in df.columns]
    requested = [v for v in requested if v in df.columns]
    if not requested:
        requested = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    df = df[requested]
    return spec, df, requested

def _range(s: pd.Series) -> float:
    s = s.dropna()
    if s.empty:
        return 0.0
    return float(s.max() - s.min())

def choose_view(df: pd.DataFrame, variables: List[str], chart_type: str) -> Dict[str, Any]:
    chart_type = (chart_type or "line").lower()
    vars_ = variables[:]

    if len(vars_) <= 1:
        return {"mode": "single", "vars": vars_}

    ranges = {v: _range(df[v]) for v in vars_}
    nonzero = [r for r in ranges.values() if r > 0]
    if not nonzero:
        return {"mode": "single", "vars": [vars_[0]]}

    rmax = max(nonzero)
    rmin = min(nonzero)

    if len(vars_) == 2:
        ratio = rmax / (rmin + 1e-9)
        if ratio >= 5.0:
            left = max(vars_, key=lambda v: ranges[v])
            right = min(vars_, key=lambda v: ranges[v])
            return {"mode": "dual_axis", "left": left, "right": right}
        return {"mode": "single", "vars": vars_}

    return {"mode": "facet", "vars": vars_}


def vega_spec(payload: Dict[str, Any]) -> Dict[str, Any]:
 spec, df, vars_ = payload_to_df(payload)
 chart_type = (spec.get("chart_type") or "line").lower()
 view = choose_view(df, vars_, chart_type)

 title = spec.get("title") or f"{spec.get('location','').title()} • {spec.get('dataset','').upper()}"
 mark = "bar" if chart_type == "bar" else "line"

 # long format (used for single + facet)
 use_vars = view.get("vars", vars_)
 long_df = df.reset_index().melt(
     id_vars=["datetime"],
     value_vars=use_vars,
     var_name="variable",
     value_name="value"
 )

 if view["mode"] == "single":
     return {
         "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
         "title": title,
         "data": {"values": _json_safe_records(long_df)},
         "mark": {"type": mark},
         "encoding": {
             "x": {"field": "datetime", "type": "temporal", "title": "Date/Time"},
             "y": {"field": "value", "type": "quantitative", "title": "Value"},
             "color": {"field": "variable", "type": "nominal", "title": "Variable"},
             "tooltip": [
                 {"field": "datetime", "type": "temporal"},
                 {"field": "variable", "type": "nominal"},
                 {"field": "value", "type": "quantitative"},
             ],
         },
     }

 if view["mode"] == "dual_axis":
     left = view["left"]
     right = view["right"]

     left_data = df[[left]].reset_index().rename(columns={left: "value"})
     left_data["variable"] = left

     right_data = df[[right]].reset_index().rename(columns={right: "value"})
     right_data["variable"] = right

     return {
         "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
         "title": title,
         "resolve": {"scale": {"y": "independent"}},
         "layer": [
             {
                 "data": {"values": _json_safe_records(left_data)},
                 "mark": {"type": mark},
                 "encoding": {
                     "x": {"field": "datetime", "type": "temporal", "title": "Date/Time"},
                     "y": {"field": "value", "type": "quantitative", "title": _label(left)},
                     "tooltip": [
                         {"field": "datetime", "type": "temporal"},
                         {"field": "variable", "type": "nominal"},
                         {"field": "value", "type": "quantitative"},
                     ],
                 },
             },
             {
                 "data": {"values": _json_safe_records(right_data)},
                 "mark": {"type": mark},
                 "encoding": {
                     "x": {"field": "datetime", "type": "temporal"},
                     "y": {
                         "field": "value",
                         "type": "quantitative",
                         "title": _label(right),
                         "axis": {"orient": "right"},
                     },
                     "tooltip": [
                         {"field": "datetime", "type": "temporal"},
                         {"field": "variable", "type": "nominal"},
                         {"field": "value", "type": "quantitative"},
                     ],
                 },
             },
         ],
     }

 # facet
 return {
     "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
     "title": title,
     "data": {"values": _json_safe_records(long_df)},
     "facet": {"field": "variable", "type": "nominal"},
     "spec": {
         "mark": {"type": mark},
         "encoding": {
             "x": {"field": "datetime", "type": "temporal", "title": "Date/Time"},
             "y": {"field": "value", "type": "quantitative", "title": "Value"},
             "tooltip": [
                 {"field": "datetime", "type": "temporal"},
                 {"field": "variable", "type": "nominal"},
                 {"field": "value", "type": "quantitative"},
             ],
         },
     },
     "columns": 1,
 }

def png_bytes(payload: Dict[str, Any]) -> bytes:
    spec, df, vars_ = payload_to_df(payload)
    chart_type = (spec.get("chart_type") or "line").lower()
    view = choose_view(df, vars_, chart_type)

    title = spec.get("title") or f"{spec.get('location','').title()} • {spec.get('dataset','').upper()}"

    fig = plt.figure(figsize=(10, 4.8))
    fig.suptitle(title)

    if view["mode"] == "single":
        ax = fig.add_subplot(111)
        if chart_type == "bar":
            v = view["vars"][0]
            ax.bar(df.index, df[v])
            ax.set_ylabel(_label(v))
        else:
            for v in view["vars"]:
                ax.plot(df.index, df[v], label=v)
            ax.legend(loc="upper left")
            ax.set_ylabel("Value")
        ax.set_xlabel("Date/Time")

    elif view["mode"] == "dual_axis":
        left = view["left"]
        right = view["right"]
        ax1 = fig.add_subplot(111)
        ax2 = ax1.twinx()

        if chart_type == "bar":
            ax1.bar(df.index, df[left])
            ax2.plot(df.index, df[right])
        else:
            ax1.plot(df.index, df[left], label=left)
            ax2.plot(df.index, df[right], label=right)

        ax1.set_ylabel(_label(left))
        ax2.set_ylabel(_label(right))
        ax1.set_xlabel("Date/Time")

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    else:
        n = len(view["vars"])
        for i, v in enumerate(view["vars"], start=1):
            ax = fig.add_subplot(n, 1, i)
            if chart_type == "bar":
                ax.bar(df.index, df[v])
            else:
                ax.plot(df.index, df[v])
            ax.set_ylabel(_label(v))
            if i == n:
                ax.set_xlabel("Date/Time")

    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0.02, 1, 0.92])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    return buf.getvalue()

def png_base64(payload: Dict[str, Any]) -> str:
    return base64.b64encode(png_bytes(payload)).decode("utf-8")
