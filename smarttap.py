import sys
import json
from pathlib import Path
from datetime import datetime

from llm.interpretation import get_task_specification
from core.data_fetcher import fetch_data
from core.visualizer import png_bytes, vega_spec, payload_to_df, choose_view
from core.validation import validate_payload, validate_and_fix_spec
from llm.followups import generate_followups_with_gemma
from llm.session_update import spec_patch_from_followup, apply_patch


# -------------------------
# Core pipeline (one place)
# -------------------------
def run_pipeline(query: str, spec: dict, base: str, chart_dir: Path, validation_dir: Path):
    """
    Runs: fetch -> validate -> choose_view -> png + vega -> followups
    Returns dict with paths + objects needed for session memory.
    """
    results = {}

    # 1) Fetch
    payload = fetch_data(spec)

    # 2) Validate payload
    report = validate_payload(payload)
    validation_file = validation_dir / f"{base}_validation.json"
    with open(validation_file, "w") as f:
        json.dump(report, f, indent=2)

    if not report["ok"]:
        print(f"Validation failed. See: {validation_file}")
        return None

    if report.get("warnings"):
        print("Validation warnings:")
        for w in report["warnings"]:
            print(" -", w)

    # 3) Decide visualization layout
    spec_, df_, vars_ = payload_to_df(payload)
    view = choose_view(df_, vars_, spec_.get("chart_type"))

    view_file = validation_dir / f"{base}_view.json"
    with open(view_file, "w") as f:
        json.dump(view, f, indent=2)

    meta_file = chart_dir / f"{base}_meta.json"
    with open(meta_file, "w") as f:
        json.dump({"view": view, "spec": spec_}, f, indent=2)

    print("Visualization decision:", view.get("reason"))

    # 4) PNG
    png_data = png_bytes(payload)
    png_file = chart_dir / f"{base}_chart.png"
    with open(png_file, "wb") as f:
        f.write(png_data)

    # 5) Vega-Lite
    vega = vega_spec(payload)
    vega_file = chart_dir / f"{base}_chart_vega.json"
    with open(vega_file, "w") as f:
        json.dump(vega, f, indent=2)

    # 6) Follow-up questions (Gemma)
    followups = generate_followups_with_gemma(
        user_query=query,
        spec=spec_,
        view=view,
        validation_report=report,
        max_q=4,
        model="gemma3",
    )

    followups_file = validation_dir / f"{base}_followups.json"
    with open(followups_file, "w") as f:
        json.dump({"followups": followups}, f, indent=2)

    results.update({
        "png": str(png_file),
        "vega": str(vega_file),
        "meta": str(meta_file),
        "validation": str(validation_file),
        "view": str(view_file),
        "followups_file": str(followups_file),

        # session memory objects
        "followups": followups,
        "final_spec": spec_,
        "report": report,
        "view_obj": view,
    })

    return results


# -------------------------
# Single-shot mode
# -------------------------
def process_query(query: str):
    base_output = Path("outputs")
    chart_dir = base_output / "charts"
    validation_dir = base_output / "validation"
    chart_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"chart_{timestamp}"

    print(f"\n{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")

    print("Parsing query with LLM...")
    spec = validate_and_fix_spec(get_task_specification(query), query)

    if spec.get("task") == "error":
        print(f"\nError: {spec.get('error_message', 'Invalid query')}")
        return None

    print("Parsed specification:")
    print(f"   Dataset: {spec.get('dataset')}")
    print(f"   Location: {spec.get('location')}")
    print(f"   Variables: {spec.get('variables')}")
    print(f"   Date range: {spec.get('start_date')} to {spec.get('end_date')}")
    print(f"   Chart type: {spec.get('chart_type')}")

    print("\nGenerating chart...")
    out = run_pipeline(query, spec, base, chart_dir, validation_dir)
    if out is None:
        return None

    print(f"PNG: {out['png']}")
    print(f"Vega: {out['vega']}")
    print("   View at: https://vega.github.io/editor/")

    fqs = out.get("followups") or []
    if fqs:
        print("\nFollow-up questions:")
        for i, q in enumerate(fqs, start=1):
            print(f"{i}) {q}")

    print(f"\n{'='*60}")
    print("Charts generated.")
    print(f"{'='*60}\n")

    return out


# -------------------------
# Session mode (multi-turn)
# -------------------------
def session():
    base_output = Path("outputs")
    chart_dir = base_output / "charts"
    validation_dir = base_output / "validation"
    chart_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)

    print("Smart-TAP Session. Type 'exit' to quit.")
    print("Tip: type 'new: <question>' to start a fresh query.\n")

    last_spec = None
    last_query = None

    while True:
        prompt = "You: " if last_spec is None else "You (follow-up or new query): "
        user_in = input(prompt).strip()

        if not user_in:
            continue
        if user_in.lower() in ("exit", "quit"):
            break

        # ---------- New query ----------
        if last_spec is None or user_in.lower().startswith("new:"):
            query = user_in[4:].strip() if user_in.lower().startswith("new:") else user_in

            spec = validate_and_fix_spec(get_task_specification(query), query)
            if spec.get("task") == "error":
                print("Smart-TAP:", spec.get("error_message"))
                continue

        # ---------- Follow-up ----------
        else:
            patch_obj = spec_patch_from_followup(
                user_reply=user_in,
                last_user_query=last_query,
                last_spec=last_spec,
                model="gemma3",
            )

            clarify_msg = patch_obj.get("clarify")
            if isinstance(clarify_msg, str) and clarify_msg.strip():
                print("Smart-TAP:", clarify_msg)
                continue

            patch = patch_obj.get("patch", {})
            if not isinstance(patch, dict):
                patch = {}


            if not patch:
                print("Smart-TAP: I didn't detect a change to apply. "
                    "Try saying what you'd like to change (year, variable, chart type).")
                continue

            spec = apply_patch(last_spec, patch)
            query = last_query


        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"chart_{timestamp}"

        print("\nGenerating chart...")
        out = run_pipeline(query, spec, base, chart_dir, validation_dir)
        if out is None:
            # reset context if something went wrong
            last_spec = None
            last_query = None
            continue

        print(f"PNG: {out['png']}")
        print(f"Vega: {out['vega']}")
        print("   View at: https://vega.github.io/editor/")

        fqs = out.get("followups") or []
        if fqs:
            print("\nFollow-up questions:")
            for i, q in enumerate(fqs, start=1):
                print(f"{i}) {q}")

        # update session memory
        last_spec = out["final_spec"]
        last_query = query
        print()


# -------------------------
# Entrypoint
# -------------------------
def main():
    if len(sys.argv) == 2:
        process_query(sys.argv[1])
    else:
        session()


if __name__ == "__main__":
    main()
