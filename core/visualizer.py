import base64
import io
from typing import Dict, Any, List, Tuple

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib


VAR_LABELS = {
    "OBM": "Avg Temp (°F)",
    "MX": "Max Temp (°F)",
    "MN": "Min Temp (°F)",
    "PC": "Precipitation (mm)",
    "SR": "Solar Radiation (Langleys)",
    "WS": "Wind Speed (mph)",
    "TU": "Humidity (%)",
    "ET": "Evapotranspiration (mm)",
    "ETa": "Evapotranspiration (mm)",
    "PPT": "Precipitation (mm)",
    "AW": "Available Water (mm)",
    "WS_C": "Water Stress Coefficient",
    "P_rz": "Root Zone Precip (mm)",
}


def create_crop_bar_chart(crop_summary: pd.DataFrame, location: str, year: int, 
                          top_n: int = 15) -> Tuple[bytes, Dict[str, Any]]:
    """
    Create a horizontal bar chart for crop distribution
    
    Args:
        crop_summary: DataFrame with columns ['Crop', 'Group', 'Field Count']
        location: Location name
        year: Year of data
        top_n: Number of top crops to show
        
    Returns:
        Tuple of (PNG bytes, Vega-Lite spec dict)
    """
    # Take top N crops
    top_crops = crop_summary.head(top_n).copy()
    top_crops = top_crops.sort_values('Field Count', ascending=True)  # For horizontal bars
    
    # Create Vega-Lite spec
    vega = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": f"Top {top_n} Crops in {location} ({year})",
        "width": 600,
        "height": 400,
        "data": {"values": top_crops.to_dict('records')},
        "mark": "bar",
        "encoding": {
            "y": {
                "field": "Crop",
                "type": "nominal",
                "sort": "-x",
                "title": None
            },
            "x": {
                "field": "Field Count",
                "type": "quantitative",
                "title": "Number of Fields"
            },
            "color": {
                "field": "Group",
                "type": "nominal",
                "title": "Crop Group",
                "scale": {"scheme": "category20"}
            },
            "tooltip": [
                {"field": "Crop", "type": "nominal"},
                {"field": "Group", "type": "nominal", "title": "Group"},
                {"field": "Field Count", "type": "quantitative", "title": "Fields"}
            ]
        }
    }
    
    # Create matplotlib PNG
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Create color map by group
    groups = top_crops['Group'].unique()
    colors = plt.cm.tab20(range(len(groups)))
    group_colors = dict(zip(groups, colors))
    bar_colors = [group_colors[g] for g in top_crops['Group']]
    
    y_pos = range(len(top_crops))
    ax.barh(y_pos, top_crops['Field Count'], color=bar_colors)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(top_crops['Crop'])
    ax.set_xlabel('Number of Fields', fontsize=12)
    ax.set_title(f'Top {top_n} Crops in {location} ({year})', fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    # Add legend for groups
    handles = [plt.Rectangle((0,0),1,1, color=group_colors[g]) for g in groups]
    ax.legend(handles, groups, title='Crop Group', bbox_to_anchor=(1.05, 1), loc='upper left')
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    
    return buf.read(), vega


def create_crop_pie_chart(crop_summary: pd.DataFrame, location: str, year: int,
                         top_n: int = 10) -> Tuple[bytes, Dict[str, Any]]:
    """
    Create a pie chart showing crop distribution by group
    
    Args:
        crop_summary: DataFrame with columns ['Crop', 'Group', 'Field Count']
        location: Location name
        year: Year of data
        top_n: Number of groups to show (rest grouped as "Other")
        
    Returns:
        Tuple of (PNG bytes, Vega-Lite spec dict)
    """
    # Group by crop group
    group_summary = crop_summary.groupby('Group')['Field Count'].sum().reset_index()
    group_summary = group_summary.sort_values('Field Count', ascending=False)
    
    # Take top N, group rest as "Other"
    if len(group_summary) > top_n:
        top_groups = group_summary.head(top_n)
        other_count = group_summary.iloc[top_n:]['Field Count'].sum()
        other_row = pd.DataFrame([{'Group': 'Other', 'Field Count': other_count}])
        group_summary = pd.concat([top_groups, other_row], ignore_index=True)
    
    # Create Vega-Lite spec
    vega = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": f"Crop Distribution by Group - {location} ({year})",
        "width": 400,
        "height": 400,
        "data": {"values": group_summary.to_dict('records')},
        "mark": {"type": "arc", "innerRadius": 50},
        "encoding": {
            "theta": {"field": "Field Count", "type": "quantitative"},
            "color": {
                "field": "Group",
                "type": "nominal",
                "scale": {"scheme": "category20"},
                "legend": {"title": "Crop Group"}
            },
            "tooltip": [
                {"field": "Group", "type": "nominal"},
                {"field": "Field Count", "type": "quantitative", "title": "Fields"}
            ]
        }
    }
    
    # Create matplotlib PNG
    fig, ax = plt.subplots(figsize=(10, 8))
    
    colors = plt.cm.tab20(range(len(group_summary)))
    wedges, texts, autotexts = ax.pie(
        group_summary['Field Count'],
        labels=group_summary['Group'],
        autopct='%1.1f%%',
        colors=colors,
        startangle=90
    )
    
    # Improve text readability
    for text in texts:
        text.set_fontsize(10)
    for autotext in autotexts:
        autotext.set_color('white')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(9)
    
    ax.set_title(f'Crop Distribution by Group - {location} ({year})', 
                 fontsize=14, fontweight='bold', pad=20)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    
    return buf.read(), vega


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
        return {"mode": "single", "vars": vars_, "reason": "Only one variable requested → single-axis."}

    ranges = {v: _range(df[v]) for v in vars_}
    nonzero = [r for r in ranges.values() if r > 0]
    if not nonzero:
        return {
            "mode": "single",
            "vars": [vars_[0]],
            "reason": "All variable ranges are 0 (flat series) → using first variable on single-axis."
        }


    rmax = max(nonzero)
    rmin = min(nonzero)

    if len(vars_) == 2:
        ratio = rmax / (rmin + 1e-9)
        if ratio >= 5.0:
            left = max(vars_, key=lambda v: ranges[v])
            right = min(vars_, key=lambda v: ranges[v])
            return {"mode": "dual_axis", "left": left, "right": right,"reason": f"Two variables with scale ratio {ratio:.2f} ≥ 5 → dual-axis (left={left}, right={right})."}
        return {"mode": "single", "vars": vars_,"reason": f"Two variables with similar scales (ratio {ratio:.2f} < 5) → single-axis."}

    return {"mode": "facet", "vars": vars_,"reason": "3+ variables requested → faceted small multiples."}


def vega_spec(payload: Dict[str, Any]) -> Dict[str, Any]:
    spec, df, vars_ = payload_to_df(payload)
    chart_type = (spec.get("chart_type") or "line").lower()
    view = choose_view(df, vars_, chart_type)

    # Generate title based on dataset type and query mode
    if spec.get("title"):
        title = spec["title"]
    elif spec.get("dataset") == "openet":
        # Location-based OpenET queries (new system)
        if spec.get("openet_geo") == "location" and spec.get("location"):
            location = spec["location"]
            location_type = spec.get("location_type", "area")
            
            # Add location type label
            type_label = f"{location_type.title()}" if location_type in ["city", "county"] else ""
            
            # Add variables to title
            if len(vars_) == 1:
                var_label = f"{vars_[0]}"
            elif len(vars_) <= 3:
                var_label = ", ".join(vars_)
            else:
                var_label = f"{len(vars_)} variables"
            
            # Include crop filter if present
            crop_filter = spec.get("crop_filter")
            if crop_filter:
                title = f"{var_label} for {crop_filter.title()} Fields near {location} ({type_label})"
            else:
                title = f"{var_label} near {location} ({type_label})"
        
        # Legacy HUC-based queries
        else:
            huc8 = spec.get("huc8_code", "")
            location_name = "Klamath Falls" if huc8 == "18010204" else f"HUC8 {huc8}"
            title = f"{location_name} • OpenET"
    else:
        # AgriMet or other datasets
        location = spec.get("location", "").title()
        dataset = spec.get("dataset", "").upper()
        if len(vars_) == 1:
            title = f"{vars_[0]} in {location} ({dataset})"
        elif len(vars_) <= 3:
            var_label = ", ".join(vars_)
            title = f"{var_label} in {location} ({dataset})"
        else:
            title = f"{location} • {dataset}"
    
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

    # Generate title based on dataset type and query mode (same logic as vega_spec)
    if spec.get("title"):
        title = spec["title"]
    elif spec.get("dataset") == "openet":
        # Location-based OpenET queries (new system)
        if spec.get("openet_geo") == "location" and spec.get("location"):
            location = spec["location"]
            location_type = spec.get("location_type", "area")
            
            # Add location type label
            type_label = f"{location_type.title()}" if location_type in ["city", "county"] else ""
            
            # Add variables to title
            if len(vars_) == 1:
                var_label = f"{vars_[0]}"
            elif len(vars_) <= 3:
                var_label = ", ".join(vars_)
            else:
                var_label = f"{len(vars_)} variables"
            
            # Include crop filter if present
            crop_filter = spec.get("crop_filter")
            if crop_filter:
                title = f"{var_label} for {crop_filter.title()} Fields near {location} ({type_label})"
            else:
                title = f"{var_label} near {location} ({type_label})"
        
        # Legacy HUC-based queries
        else:
            huc8 = spec.get("huc8_code", "")
            location_name = "Klamath Falls" if huc8 == "18010204" else f"HUC8 {huc8}"
            title = f"{location_name} • OpenET"
    else:
        # AgriMet or other datasets
        location = spec.get("location", "").title()
        dataset = spec.get("dataset", "").upper()
        if len(vars_) == 1:
            title = f"{vars_[0]} in {location} ({dataset})"
        elif len(vars_) <= 3:
            var_label = ", ".join(vars_)
            title = f"{var_label} in {location} ({dataset})"
        else:
            title = f"{location} • {dataset}"

    fig = plt.figure(figsize=(10, 4.8))
    fig.suptitle(title)

    if view["mode"] == "single":
        ax = fig.add_subplot(111)
        if not view.get("vars"):
            raise ValueError(f"No variables to plot. Spec variables={spec.get('variables')} df_cols={list(df.columns)}")
        v = view["vars"][0]

        v = view["vars"][0]

        if chart_type == "bar":
            ax.bar(df.index, df[v])
            ax.set_ylabel(_label(v))

        elif chart_type == "scatter":
            ax.scatter(df.index, df[v])
            ax.set_ylabel(_label(v))

        elif chart_type == "area":
            ax.fill_between(df.index, df[v])
            ax.set_ylabel(_label(v))

        elif chart_type == "histogram":
            ax.hist(df[v].dropna(), bins=30)
            ax.set_xlabel(_label(v))
            ax.set_ylabel("Frequency")

        elif chart_type == "box":
            ax.boxplot(df[v].dropna(), vert=True)
            ax.set_ylabel(_label(v))
    
        else:
            for v in view["vars"]:
                ax.plot(df.index, df[v], label=_label(v))

            if len(view["vars"]) == 1:
                ax.set_ylabel(_label(view["vars"][0]))
                # optional: hide legend when only one variable
                # ax.legend().remove()
            else:
                ax.set_ylabel("Value")
                ax.legend(loc="upper left")

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
        
    # Keep x-axis within requested range to avoid tick drift into next month
    if spec.get("start_date") and spec.get("end_date"):
        start = pd.to_datetime(spec["start_date"])
        end = pd.to_datetime(spec["end_date"])
        if view["mode"] == "dual_axis":
            ax1.set_xlim(start, end)
        else:
            ax.set_xlim(start, end)


    fig.tight_layout(rect=[0, 0.02, 1, 0.92])

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    return buf.getvalue()

def png_base64(payload: Dict[str, Any]) -> str:
    return base64.b64encode(png_bytes(payload)).decode("utf-8")
