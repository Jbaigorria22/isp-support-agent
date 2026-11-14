"""Run the intent-classification evaluation against the model.

    python -m evals.run_intent_eval              # real model (Bedrock), ~30 calls
    python -m evals.run_intent_eval --offline    # RuleBrain, free: checks the runner itself
    python -m evals.run_intent_eval --limit 5    # only the first 5 cases

Hard cases (the ones marked DISCUTIBLE / ENGANOSO in the dataset) are scored
separately: we were not fully sure of the label ourselves, so mixing them into
the headline number would hide how the agent does on the clear ones.
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from evals.intent_dataset import CASES

RESULTS_DIR = Path(__file__).parent / "results"
HARD_MARKERS = ("DISCUTIBLE", "ENGAÑOSO", "ENGANOSO")


def is_hard(case: dict) -> bool:
    return any(marker in case.get("note", "") for marker in HARD_MARKERS)


def run_case(brain, case: dict) -> dict:
    """Classify one message and compare with the expected intent."""
    try:
        got = brain.classify_intent(case["message"])
        error = None
    except Exception as exc:  # one bad call must not kill the whole run
        got, error = None, f"{type(exc).__name__}: {exc}"

    return {
        "id": case["id"],
        "message": case["message"],
        "expected": case["expected"],
        "got": got,
        "passed": got == case["expected"],
        "hard": is_hard(case),
        "error": error,
    }


def summarize(results: list[dict]) -> dict:
    """Headline accuracy (clear cases), hard-case accuracy, and per-intent detail."""
    clear = [r for r in results if not r["hard"]]
    hard = [r for r in results if r["hard"]]

    per_intent: dict[str, dict] = {}
    for r in results:
        stats = per_intent.setdefault(r["expected"], {"total": 0, "passed": 0})
        stats["total"] += 1
        stats["passed"] += r["passed"]

    def accuracy(rows: list[dict]) -> float | None:
        return round(100 * sum(r["passed"] for r in rows) / len(rows), 1) if rows else None

    return {
        "cases": len(results),
        "accuracy_clear": accuracy(clear),
        "accuracy_hard": accuracy(hard),
        "clear_total": len(clear),
        "hard_total": len(hard),
        "per_intent": dict(sorted(per_intent.items())),
        "errors": sum(1 for r in results if r["error"]),
    }


def report(results: list[dict], summary: dict, model: str) -> None:
    print(f"\nModelo: {model}\n")

    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"Fallaron {len(failures)} de {summary['cases']}:\n")
        for r in failures:
            flag = "  [dificil]" if r["hard"] else ""
            print(f"  {r['id']}{flag}")
            print(f"    mensaje:  {r['message']}")
            print(f"    esperaba: {r['expected']}")
            print(f"    dijo:     {r['error'] or r['got']}\n")

    print(f"Casos claros:    {summary['accuracy_clear']}%  ({summary['clear_total']} casos)")
    print(f"Casos dificiles: {summary['accuracy_hard']}%  ({summary['hard_total']} casos)")
    if summary["errors"]:
        print(f"Llamadas con error: {summary['errors']}")

    print("\nPor intent:")
    for intent, stats in summary["per_intent"].items():
        print(f"  {stats['passed']:>2}/{stats['total']:<2}  {intent}")


def save(results: list[dict], summary: dict, model: str) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    path = RESULTS_DIR / f"intent-{stamp}.json"
    path.write_text(json.dumps(
        {"timestamp": stamp, "model": model, "summary": summary, "results": results},
        indent=2, ensure_ascii=False,
    ), encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Intent classification evaluation")
    parser.add_argument("--offline", action="store_true", help="use RuleBrain (free)")
    parser.add_argument("--limit", type=int, help="run only the first N cases")
    args = parser.parse_args()

    load_dotenv()
    from fiberlab.agent.brain import BedrockBrain, RuleBrain

    if args.offline:
        brain, model = RuleBrain(), "RuleBrain (offline)"
    else:
        brain = BedrockBrain()
        model = os.environ.get("BEDROCK_MODEL_ID", "default")

    cases = CASES[: args.limit] if args.limit else CASES
    print(f"Evaluando {len(cases)} casos ...")

    results = []
    for i, case in enumerate(cases, 1):
        result = run_case(brain, case)
        results.append(result)
        print(f"  [{i:>2}/{len(cases)}] {'OK  ' if result['passed'] else 'FALLO'} {result['id']}")

    summary = summarize(results)
    report(results, summary, model)
    print(f"\nGuardado en {save(results, summary, model).relative_to(Path.cwd())}")


if __name__ == "__main__":
    main()
