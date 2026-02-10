# llm_session_update.py
from __future__ import annotations
from typing import Dict, Any
import json
import ollama

def spec_patch_from_followup(
    *,
    user_reply: str,
    last_user_query: str,
    last_spec: Dict[str, Any],
    model: str = "gemma3",
) -> Dict[str, Any]:
    """
    Use Gemma to convert a user follow-up reply into a JSON patch for the spec.
    Returns: {"patch": {...}} or {"patch": {}, "clarify": "..."}.
    """

    context = {
        "last_user_query": last_user_query,
        "last_spec": {
            "task": last_spec.get("task"),
            "dataset": last_spec.get("dataset"),
            "location": last_spec.get("location"),
            "variables": last_spec.get("variables"),
            "start_date": last_spec.get("start_date"),
            "end_date": last_spec.get("end_date"),
            "interval": last_spec.get("interval"),
            "chart_type": last_spec.get("chart_type"),
        },
        "user_reply": user_reply,
        "allowed": {
            "locations": ["corvallis","pendleton","hood river","klamath falls","ontario"],
            "variables": ["MX","MN","OBM","PC","SR","WS","TU","ET"],
            "chart_type": ["line","bar","scatter","area","histogram","box"],
            "interval": ["daily","monthly","hourly","auto"],
            "dataset": ["agrimet","openet"],
        },
    }

    system_prompt = """
You update a Smart-TAP chart specification based on a user's follow-up reply.

RULES:
- Output STRICT JSON only.
- Return a JSON object with keys:
  - "patch": { ... }    # only include fields that should change
  - optional "clarify": "..." if the reply is ambiguous
- DO NOT erase existing fields unless user asked explicitly.
- If user requests adding/removing variables:
  - Use variables list in "allowed.variables"
  - Keep existing variables unless user says "remove".
- If user requests "monthly", set interval="monthly".
- If user requests "scatter", set chart_type="scatter".
- If user mentions ET or evapotranspiration, set dataset="openet" and include "ET" in variables.
- If user asks to compare with temperature, include OBM (or MX/MN if explicitly asked).
- Keep location and date range unchanged unless user asks to change them.
"""

    resp = ollama.chat(
        model=model,
        format="json",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": json.dumps(context)},
        ],
    )

    raw = resp["message"]["content"]
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return {"patch": {}}
        patch = obj.get("patch", {})
        if not isinstance(patch, dict):
            patch = {}
        out = {"patch": patch}
        if "clarify" in obj and isinstance(obj["clarify"], str):
            out["clarify"] = obj["clarify"]
        return out
    except Exception:
        return {"patch": {}}


def apply_patch(last_spec: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    """Apply patch onto last_spec (shallow merge) with small helpers for variables."""
    new_spec = dict(last_spec)

    # variables: allow add/remove behavior if patch includes 'variables'
    if "variables" in patch and isinstance(patch["variables"], list):
        new_spec["variables"] = patch["variables"]

    # simple scalar fields
    for k in ["dataset","location","start_date","end_date","interval","chart_type","task","title"]:
        if k in patch:
            new_spec[k] = patch[k]

    return new_spec
    