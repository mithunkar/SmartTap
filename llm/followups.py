# llm_followups.py
from __future__ import annotations
from typing import Dict, Any, List
import json
import ollama

def generate_followups_with_gemma(
    *,
    user_query: str,
    spec: Dict[str, Any],
    view: Dict[str, Any],
    validation_report: Dict[str, Any],
    max_q: int = 4,
    model: str = "gemma3",
) -> List[str]:
    """
    Use Gemma to propose natural follow-up questions AFTER a chart is generated.
    Returns a list of questions (strings). Forces JSON output.
    """

    # Keep the LLM grounded: only pass small, relevant context
    context = {
        "user_query": user_query,
        "spec": {
            "dataset": spec.get("dataset"),
            "location": spec.get("location"),
            "variables": spec.get("variables"),
            "start_date": spec.get("start_date"),
            "end_date": spec.get("end_date"),
            "interval": spec.get("interval"),
            "chart_type": spec.get("chart_type"),
        },
        "viz_decision": {
            "mode": view.get("mode"),
            "reason": view.get("reason"),
            "left": view.get("left"),
            "right": view.get("right"),
            "vars": view.get("vars"),
        },
        "validation": {
            "ok": validation_report.get("ok"),
            "warnings": validation_report.get("warnings", [])[:6],
            "row_count": (validation_report.get("summary") or {}).get("row_count"),
        },
        "max_questions": max_q,
    }

    system_prompt = f"""
You are Smart-TAP's follow-up question generator for agricultural/time-series charts.

GOAL:
After a chart is produced, ask helpful follow-up questions that improve the user's analysis.

RULES:
- Output STRICT JSON only. No markdown, no extra text.
- Generate 2 to {max_q} follow-up questions.
- Questions must be short (<= 18 words) and actionable.
- Do NOT ask for information already known in the spec (location, date range, variables).
- Prefer questions that:
  1) add a relevant variable (e.g., ET vs rainfall, temp vs rain)
  2) change aggregation (daily -> weekly/monthly)
  3) compare periods (same range last year)
  4) address validation warnings (missing/outliers) if present
- If the visualization mode is dual_axis, include ONE question about alternate view choice.

OUTPUT FORMAT:
{{
  "questions": ["...", "...", ...]
}}
"""

    response = ollama.chat(
        model=model,
        format="json",
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": json.dumps(context)},
        ],
    )

    raw = response["message"]["content"]
    try:
        obj = json.loads(raw)
        questions = obj.get("questions", [])
        if not isinstance(questions, list):
            return []
        # light cleanup: keep strings, strip, dedupe, cap
        cleaned: List[str] = []
        seen = set()
        for q in questions:
            if not isinstance(q, str):
                continue
            q = q.strip()
            if not q or q in seen:
                continue
            seen.add(q)
            cleaned.append(q)
        return cleaned[:max_q]
    except Exception:
        # If Gemma returns invalid JSON, fail gracefully (no follow-ups)
        return []
