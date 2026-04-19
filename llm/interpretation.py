from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from .config import get_model_name
from core.variable_registry import variables_for_dataset


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _ollama_client():
    try:
        import ollama
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "SmartTap parsing requires the optional 'ollama' package. Install dependencies with "
            "`pip install -r requirements.txt` and ensure Ollama is running."
        ) from exc
    return ollama


def load_prompt_template(template_name: str) -> str | None:
    prompt_path = PROMPTS_DIR / f"{template_name}.txt"
    try:
        return prompt_path.read_text()
    except FileNotFoundError:
        return None


def load_keyword_mappings():
    variable_keywords = {}
    crop_keywords = {}
    try:
        variable_keywords = json.loads((DATA_DIR / "openet_variable_keywords.json").read_text())
    except FileNotFoundError:
        pass
    try:
        crop_keywords = json.loads((DATA_DIR / "crop_name_keywords.json").read_text())
    except FileNotFoundError:
        pass
    return variable_keywords, crop_keywords


def build_agrimet_location_guidance() -> str:
    examples = ", ".join(["corvallis", "pendleton", "hood river", "klamath falls", "ontario"])
    return (
        "For AgriMet queries:\n"
        "- Accept location as station name, city name, or county name.\n"
        "- County mentions should be preserved as the user said them; downstream resolution maps supported counties to local AgriMet stations.\n"
        "- Use the local Oregon station set when the query is weather-focused.\n"
        f"- Common local examples: {examples}"
    )


def get_task_specification(user_query: str):
    today = date.today().strftime("%Y-%m-%d")
    last_year = int(today.split("-")[0]) - 1
    variable_keywords, _ = load_keyword_mappings()
    variable_hints = []
    for dataset in ("openet", "agrimet"):
        variable_hints.append(f"{dataset.upper()} variables:")
        for metadata in variables_for_dataset(dataset):
            fallback_keywords = ", ".join(metadata.aliases[:4])
            configured = variable_keywords.get(metadata.code, {})
            keywords = ", ".join(configured.get("keywords", [])[:5]) or fallback_keywords
            variable_hints.append(f"- {metadata.code} ({metadata.label}): {keywords}")
    variable_section = "\n".join(variable_hints)

    prompt_template = load_prompt_template("interpretation") or "You convert agricultural questions into valid JSON."
    system_prompt = prompt_template.format(
        today=today,
        variable_section=variable_section,
        last_year=last_year,
        agrimet_location_guidance=build_agrimet_location_guidance(),
    )

    response = _ollama_client().chat(
        model=get_model_name(),
        format="json",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
    )

    raw_content = response.message.content
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as exc:
        return {"task": "error", "error_message": f"Parser returned invalid JSON: {exc}"}


if __name__ == "__main__":
    print(json.dumps(get_task_specification("Show temperature in Corvallis for July 2024"), indent=2))
