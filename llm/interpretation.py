from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from .config import OLLAMA_HOST, get_model_name
from core.paths import CROP_NAME_KEYWORDS_JSON, OPENET_VARIABLE_KEYWORDS_JSON
from core.variable_registry import variables_for_dataset


PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class _HttpOllamaClient:
    def __init__(self, *, host: str):
        self._host = host.rstrip("/")

    def chat(self, **kwargs: Any) -> dict[str, Any]:
        payload = json.dumps({**kwargs, "stream": False}).encode("utf-8")
        request = urllib_request.Request(
            f"{self._host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(request, timeout=90) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib_error.URLError as exc:
            raise RuntimeError(
                "SmartTap parsing could not reach the local Ollama server. Ensure Ollama is running "
                f"and accessible at {self._host}."
            ) from exc


def _ollama_client():
    try:
        import ollama
    except ModuleNotFoundError:
        return _HttpOllamaClient(host=OLLAMA_HOST)
    return ollama


def load_prompt_template(template_name: str) -> str | None:
    prompt_path = PROMPTS_DIR / f"{template_name}.txt"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def load_prompt_template_path(prompt_path: str | Path) -> str:
    return Path(prompt_path).read_text(encoding="utf-8")


def load_keyword_mappings():
    variable_keywords = {}
    crop_keywords = {}
    try:
        variable_keywords = json.loads(OPENET_VARIABLE_KEYWORDS_JSON.read_text())
    except FileNotFoundError:
        pass
    try:
        crop_keywords = json.loads(CROP_NAME_KEYWORDS_JSON.read_text())
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


def build_system_prompt(
    *,
    template_name: str = "interpretation",
    prompt_text: str | None = None,
    prompt_path: str | Path | None = None,
    today_value: str | None = None,
) -> str:
    today = today_value or date.today().strftime("%Y-%m-%d")
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

    if prompt_text is not None:
        prompt_template = prompt_text
    elif prompt_path is not None:
        prompt_template = load_prompt_template_path(prompt_path)
    else:
        prompt_template = load_prompt_template(template_name) or "You convert agricultural questions into valid JSON."

    return prompt_template.format(
        today=today,
        variable_section=variable_section,
        last_year=last_year,
        agrimet_location_guidance=build_agrimet_location_guidance(),
    )


def _parser_error(message: str) -> dict[str, Any]:
    return {"task": "error", "error_message": message}


def get_task_specification(
    user_query: str,
    *,
    model_name: str | None = None,
    template_name: str = "interpretation",
    prompt_text: str | None = None,
    prompt_path: str | Path | None = None,
    chat_client: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    system_prompt = build_system_prompt(
        template_name=template_name,
        prompt_text=prompt_text,
        prompt_path=prompt_path,
    )

    chat = chat_client
    if chat is None:
        chat = _ollama_client().chat

    response = chat(
        model=model_name or get_model_name(),
        format="json",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query},
        ],
    )

    raw_content = getattr(getattr(response, "message", None), "content", None)
    if raw_content is None and isinstance(response, dict):
        raw_content = (
            response.get("message", {}) if isinstance(response.get("message"), dict) else {}
        ).get("content")
    if raw_content is None:
        return _parser_error("Parser returned no content.")

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError as exc:
        return _parser_error(f"Parser returned invalid JSON: {exc}")


if __name__ == "__main__":
    print(json.dumps(get_task_specification("Show temperature in Corvallis for July 2024"), indent=2))
