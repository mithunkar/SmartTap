import base64
import io
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple

cache_dir = Path(__file__).resolve().parent.parent / ".cache" / "matplotlib"
cache_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(cache_dir))
os.environ.setdefault("XDG_CACHE_HOME", str(cache_dir.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .variable_registry import variable_label


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


def create_grouped_comparison_chart(
    grouped_df: pd.DataFrame,
    *,
    location: str,
    compare_by: str,
    variables: List[str],
    title: str | None = None,
) -> Tuple[bytes, Dict[str, Any]]:
    data = grouped_df.copy()
    data["datetime"] = pd.to_datetime(data["datetime"])
    variables = variables or sorted(data["variable"].astype(str).unique().tolist())
    resolved_title = title or f"{', '.join(variable_label(v) for v in variables)} by {variable_label(compare_by)} in {location}"
    multi_time = data["datetime"].nunique() > 1

    if multi_time:
        if len(variables) > 1:
            vega = {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "title": resolved_title,
                "data": {"values": _json_safe_records(data[["datetime", "group", "variable", "value"]])},
                "facet": {"field": "variable", "type": "nominal", "title": "Variable"},
                "spec": {
                    "mark": {"type": "line", "point": True},
                    "encoding": {
                        "x": {"field": "datetime", "type": "temporal", "title": "Date/Time"},
                        "y": {"field": "value", "type": "quantitative", "title": "Value"},
                        "color": {"field": "group", "type": "nominal", "title": variable_label(compare_by)},
                        "tooltip": [
                            {"field": "datetime", "type": "temporal"},
                            {"field": "variable", "type": "nominal"},
                            {"field": "group", "type": "nominal"},
                            {"field": "value", "type": "quantitative"},
                        ],
                    },
                },
                "columns": 1,
            }
        else:
            vega = {
                "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                "title": resolved_title,
                "data": {"values": _json_safe_records(data[["datetime", "group", "variable", "value"]])},
                "mark": {"type": "line", "point": True},
                "encoding": {
                    "x": {"field": "datetime", "type": "temporal", "title": "Date/Time"},
                    "y": {"field": "value", "type": "quantitative", "title": variable_label(variables[0])},
                    "color": {"field": "group", "type": "nominal", "title": variable_label(compare_by)},
                    "tooltip": [
                        {"field": "datetime", "type": "temporal"},
                        {"field": "group", "type": "nominal"},
                        {"field": "value", "type": "quantitative"},
                    ],
                },
            }
    else:
        vega = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": resolved_title,
            "data": {"values": _json_safe_records(data[["datetime", "group", "variable", "value"]])},
            "mark": "bar",
            "encoding": {
                "x": {"field": "group", "type": "nominal", "title": variable_label(compare_by)},
                "y": {"field": "value", "type": "quantitative", "title": "Value"},
                "color": {"field": "variable", "type": "nominal", "title": "Variable"},
                "tooltip": [
                    {"field": "group", "type": "nominal"},
                    {"field": "variable", "type": "nominal"},
                    {"field": "value", "type": "quantitative"},
                ],
            },
        }

    fig = plt.figure(figsize=(10, 5.5 if len(variables) == 1 else 7.5))
    if multi_time:
        if len(variables) == 1:
            ax = fig.add_subplot(111)
            variable = variables[0]
            for group_name, frame in data.groupby("group"):
                ordered = frame.sort_values("datetime")
                ax.plot(ordered["datetime"], ordered["value"], marker="o", label=str(group_name))
            ax.set_title(resolved_title)
            ax.set_xlabel("Date/Time")
            ax.set_ylabel(variable_label(variable))
            ax.legend(loc="upper left")
            ax.grid(alpha=0.25)
        else:
            axes = fig.subplots(len(variables), 1, squeeze=False)
            for index, variable in enumerate(variables):
                ax = axes[index][0]
                subset = data[data["variable"] == variable]
                for group_name, frame in subset.groupby("group"):
                    ordered = frame.sort_values("datetime")
                    ax.plot(ordered["datetime"], ordered["value"], marker="o", label=str(group_name))
                ax.set_ylabel(variable_label(variable))
                ax.grid(alpha=0.25)
                if index == 0:
                    ax.set_title(resolved_title)
                    ax.legend(loc="upper left")
                if index == len(variables) - 1:
                    ax.set_xlabel("Date/Time")
    else:
        ax = fig.add_subplot(111)
        pivoted = data.pivot_table(index="group", columns="variable", values="value", aggfunc="mean").fillna(0)
        pivoted.plot(kind="bar", ax=ax)
        ax.set_title(resolved_title)
        ax.set_xlabel(variable_label(compare_by))
        ax.set_ylabel("Value")
        ax.grid(axis="y", alpha=0.25)

    fig.autofmt_xdate()
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    return buf.getvalue(), vega


def create_grouped_summary_chart(
    grouped_df: pd.DataFrame,
    *,
    compare_by: str,
    aggregation: str = "mean",
    title: str | None = None,
) -> Tuple[pd.DataFrame, bytes, Dict[str, Any]]:
    metric_name = "sum" if aggregation == "sum" else "mean"
    summary = grouped_df.groupby(["group", "variable"], as_index=False)["value"].agg(metric_name)
    resolved_title = title or f"Grouped summary by {variable_label(compare_by)}"
    vega = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": resolved_title,
        "data": {"values": summary.to_dict("records")},
        "mark": "bar",
        "encoding": {
            "x": {"field": "group", "type": "nominal", "title": variable_label(compare_by)},
            "y": {"field": "value", "type": "quantitative", "title": metric_name.title()},
            "color": {"field": "variable", "type": "nominal", "title": "Variable"},
            "tooltip": [
                {"field": "group", "type": "nominal"},
                {"field": "variable", "type": "nominal"},
                {"field": "value", "type": "quantitative"},
            ],
        },
    }

    fig, ax = plt.subplots(figsize=(9, 4.8))
    pivoted = summary.pivot_table(index="group", columns="variable", values="value", aggfunc="mean").fillna(0)
    pivoted.plot(kind="bar", ax=ax)
    ax.set_title(resolved_title)
    ax.set_xlabel(variable_label(compare_by))
    ax.set_ylabel(metric_name.title())
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    return summary, buf.getvalue(), vega


def create_metric_ranking_chart(
    ranking_df: pd.DataFrame,
    *,
    location: str,
    compare_by: str,
    title: str | None = None,
) -> Tuple[bytes, Dict[str, Any]]:
    data = ranking_df.copy()
    resolved_title = title or f"Most Common {variable_label(compare_by)} in {location}"
    plot_df = data.sort_values("field_count", ascending=True)

    vega = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": resolved_title,
        "data": {"values": plot_df.to_dict("records")},
        "mark": "bar",
        "encoding": {
            "y": {"field": "group", "type": "nominal", "sort": "-x", "title": variable_label(compare_by)},
            "x": {"field": "field_count", "type": "quantitative", "title": "Field-Years"},
            "tooltip": [
                {"field": "group", "type": "nominal", "title": variable_label(compare_by)},
                {"field": "field_count", "type": "quantitative", "title": "Field-Years"},
                {"field": "share", "type": "quantitative", "title": "Share (%)"},
            ],
        },
    }

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.barh(plot_df["group"], plot_df["field_count"], color="#4c78a8")
    ax.set_title(resolved_title)
    ax.set_xlabel("Field-Years")
    ax.set_ylabel(variable_label(compare_by))
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    return buf.getvalue(), vega


def create_metric_yearly_breakdown_chart(
    yearly_df: pd.DataFrame,
    *,
    location: str,
    compare_by: str,
    title: str | None = None,
) -> Tuple[bytes, Dict[str, Any]]:
    data = yearly_df.copy()
    data["datetime"] = pd.to_datetime(data["datetime"])
    data["year"] = data["datetime"].dt.year.astype(str)
    resolved_title = title or f"{variable_label(compare_by)} by Year in {location}"

    vega = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": resolved_title,
        "data": {"values": _json_safe_records(data[["datetime", "year", "group", "field_count"]])},
        "mark": "bar",
        "encoding": {
            "x": {"field": "year", "type": "nominal", "title": "Year"},
            "y": {"field": "field_count", "type": "quantitative", "title": "Field-Years", "stack": "zero"},
            "color": {"field": "group", "type": "nominal", "title": variable_label(compare_by)},
            "tooltip": [
                {"field": "year", "type": "nominal", "title": "Year"},
                {"field": "group", "type": "nominal", "title": variable_label(compare_by)},
                {"field": "field_count", "type": "quantitative", "title": "Field-Years"},
            ],
        },
    }

    pivoted = data.pivot_table(index="year", columns="group", values="field_count", aggfunc="sum").fillna(0)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    pivoted.plot(kind="bar", stacked=True, ax=ax)
    ax.set_title(resolved_title)
    ax.set_xlabel("Year")
    ax.set_ylabel("Field-Years")
    ax.legend(title=variable_label(compare_by), bbox_to_anchor=(1.02, 1), loc="upper left")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160)
    plt.close(fig)
    return buf.getvalue(), vega


def _json_safe_records(df: pd.DataFrame) -> list[dict]:
    """Convert datetime-like objects into JSON-safe strings."""
    out = df.to_dict(orient="records")
    for r in out:
        if "datetime" in r:
            r["datetime"] = pd.to_datetime(r["datetime"]).isoformat()
    return out

def _label(v: str) -> str:
    return variable_label(v)

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
    display_location = spec.get("display_location") or spec.get("location", "")

    # Generate title based on dataset type and query mode
    if spec.get("title"):
        title = spec["title"]
    elif spec.get("dataset") == "openet":
        # Location-based OpenET queries (new system)
        if spec.get("openet_geo") == "location" and spec.get("location"):
            location = display_location or spec["location"]
            location_type = spec.get("location_type", "area")
            
            # Add location type label
            type_label = f"{location_type.title()}" if location_type in ["city", "county"] else ""
            
            # Add variables to title
            if len(vars_) == 1:
                var_label = variable_label(vars_[0])
            elif len(vars_) <= 3:
                var_label = ", ".join(variable_label(value) for value in vars_)
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
        location = str(display_location or spec.get("location", "")).title()
        dataset = spec.get("dataset", "").upper()
        if len(vars_) == 1:
            title = f"{variable_label(vars_[0])} in {location} ({dataset})"
        elif len(vars_) <= 3:
            var_label = ", ".join(variable_label(value) for value in vars_)
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
        y_title = variable_label(use_vars[0]) if len(use_vars) == 1 else "Value"
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "data": {"values": _json_safe_records(long_df)},
            "mark": {"type": mark},
            "encoding": {
                "x": {"field": "datetime", "type": "temporal", "title": "Date/Time"},
                "y": {"field": "value", "type": "quantitative", "title": y_title},
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
    facet_y_title = variable_label(use_vars[0]) if len(use_vars) == 1 else "Value"
    return {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title,
        "data": {"values": _json_safe_records(long_df)},
        "facet": {"field": "variable", "type": "nominal"},
        "spec": {
            "mark": {"type": mark},
            "encoding": {
                "x": {"field": "datetime", "type": "temporal", "title": "Date/Time"},
                "y": {"field": "value", "type": "quantitative", "title": facet_y_title},
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
    display_location = spec.get("display_location") or spec.get("location", "")

    # Generate title based on dataset type and query mode (same logic as vega_spec)
    if spec.get("title"):
        title = spec["title"]
    elif spec.get("dataset") == "openet":
        # Location-based OpenET queries (new system)
        if spec.get("openet_geo") == "location" and spec.get("location"):
            location = display_location or spec["location"]
            location_type = spec.get("location_type", "area")
            
            # Add location type label
            type_label = f"{location_type.title()}" if location_type in ["city", "county"] else ""
            
            # Add variables to title
            if len(vars_) == 1:
                var_label = variable_label(vars_[0])
            elif len(vars_) <= 3:
                var_label = ", ".join(variable_label(value) for value in vars_)
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
        location = str(display_location or spec.get("location", "")).title()
        dataset = spec.get("dataset", "").upper()
        if len(vars_) == 1:
            title = f"{variable_label(vars_[0])} in {location} ({dataset})"
        elif len(vars_) <= 3:
            var_label = ", ".join(variable_label(value) for value in vars_)
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
