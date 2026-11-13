"""Command-line demo. Demo mode (the default) replays saved results and needs no API key.

    python -m policylens                      # overview of every saved eval run
    python -m policylens --doc doc_034        # one document: answer key vs every model's saved answer
    python -m policylens --live --doc doc_034 --model claude-haiku-5-5 --effort low
    python -m policylens --live --pdf some.pdf --model claude-opus-5-5 --effort low

Live mode calls the API and runs only when ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .grounding import document_text
from .review import review
from .schema import FIELD_NAMES
from .scorer import score_field

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
TRUTH_DIR = ROOT / "data" / "truth"
DOCS_DIR = ROOT / "data" / "docs"
LIVE_KEY_ENV_VAR = "ANTHROPIC_API_KEY"
NOT_LOGGED = {"generation_log.jsonl"}


def _load_rows(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return list({r["doc_id"]: r for r in rows}.values())  # last attempt per document wins


def _runs(results_dir: Path) -> dict[str, list[dict]]:
    runs = {}
    for path in sorted(results_dir.glob("*.jsonl")):
        if path.name in NOT_LOGGED:
            continue
        rows = _load_rows(path)
        if rows:
            first = rows[0]
            run = first.get("run", "r1")
            label = f"{first['model']}:{first['effort']}" + ("" if run == "r1" else f":{run}")
            runs[label] = rows
    return runs


def _truth(doc_id: str) -> dict | None:
    path = TRUTH_DIR / f"{doc_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def show_overview(results_dir: Path = RESULTS_DIR) -> int:
    runs = _runs(results_dir)
    if not runs:
        print(f"No saved results in {results_dir}.")
        return 1
    print("Saved eval runs (demo mode - no API calls)\n")
    print(f"{'config':32} {'docs':>4} {'field acc':>9} {'all-correct':>11} {'$/doc':>8} {'latency':>8}")
    for label, rows in runs.items():
        fields = [ok for r in rows for ok in r["field_correct"].values()]
        all_ok = sum(all(r["field_correct"].values()) for r in rows)
        cost = sum(r["cost_usd"] for r in rows) / len(rows)
        latency = sum(r["latency_s"] for r in rows) / len(rows)
        print(f"{label:32} {len(rows):>4} {sum(fields) / len(fields):>9.1%} {all_ok / len(rows):>11.1%} "
              f"{cost:>8.4f} {latency:>7.1f}s")
    print("\nFull report: results/summary.md. One document: python -m policylens --doc doc_034")
    return 0


def _pdf_text(path: Path) -> str | None:
    return document_text(path) if path.exists() else None


def _print_comparison(truth: dict | None, label: str, prediction: dict | None, doc_text: str | None = None) -> None:
    decision = review(prediction, doc_text=doc_text)
    flag = ", ".join(decision.reasons) if decision.needs_review else "not flagged"
    print(f"\n[{label}]  review flag: {flag}")
    if prediction is None:
        print("  extraction failed")
        return
    confidence = prediction.get("confidence") or {}
    for field in FIELD_NAMES:
        value = prediction.get(field)
        mark = ""
        if truth is not None:
            mark = "ok  " if score_field(field, truth.get(field), value).correct else "MISS"
        print(f"  {mark} {field:22} {str(value):55.55} conf {confidence.get(field, float('nan')):.2f}")


def show_doc(doc_id: str, results_dir: Path = RESULTS_DIR) -> int:
    truth = _truth(doc_id)
    if truth is None:
        print(f"No answer key for {doc_id!r} in {TRUTH_DIR}.")
        return 1
    print(f"{doc_id} ({truth['document_type']}, layout {truth['template']}) - PDF: {DOCS_DIR / (doc_id + '.pdf')}")
    print("\n[answer key]")
    for field in FIELD_NAMES:
        print(f"       {field:22} {truth[field]}")
    text = _pdf_text(DOCS_DIR / f"{doc_id}.pdf")
    for label, rows in _runs(results_dir).items():
        row = next((r for r in rows if r["doc_id"] == doc_id), None)
        if row is not None:
            _print_comparison(truth, label, row["prediction"], text)
    return 0


def run_live(model: str, effort: str, doc_id: str | None, pdf: Path | None) -> int:
    if not os.environ.get(LIVE_KEY_ENV_VAR):
        print(f"Live mode needs {LIVE_KEY_ENV_VAR}. Without it, run demo mode: python -m policylens",
              file=sys.stderr)
        return 2
    from .extract import extract  # imported here so demo mode never touches the SDK client
    from .llm import make_client

    path = pdf if pdf else DOCS_DIR / f"{doc_id}.pdf"
    if not path.exists():
        print(f"No such PDF: {path}", file=sys.stderr)
        return 1
    result = extract(make_client(), path, model, effort)
    print(f"{path.name}: {model} at {effort} effort, ${result.cost_usd:.4f}, {result.latency_s:.1f}s"
          + (f", served by {result.served_model}" if result.served_model != model else ""))
    if result.error:
        print(f"error: {result.error}")
    prediction = result.extraction.model_dump(mode="json") if result.extraction else None
    _print_comparison(_truth(doc_id) if doc_id else None, f"live {model}:{effort}", prediction, _pdf_text(path))
    return 0 if result.error is None else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="python -m policylens", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--doc", help="document id, e.g. doc_034")
    parser.add_argument("--live", action="store_true", help=f"call the API (needs {LIVE_KEY_ENV_VAR})")
    parser.add_argument("--pdf", type=Path, help="live mode: any PDF instead of a dataset document")
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--effort", default="low")
    args = parser.parse_args(argv)

    if args.live:
        if not (args.doc or args.pdf):
            parser.error("--live needs --doc or --pdf")
        return run_live(args.model, args.effort, args.doc, args.pdf)
    if args.pdf:
        parser.error("--pdf is a live-mode option; add --live")
    return show_doc(args.doc) if args.doc else show_overview()
