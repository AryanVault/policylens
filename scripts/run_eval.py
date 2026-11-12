"""Run extraction configs (model x effort) over the dataset, score, and summarize.

    python scripts/run_eval.py --out results/smoke --docs doc_001 doc_002 doc_003 \
        --configs claude-haiku-5-5:low claude-sonnet-5-5:low claude-opus-5-5:low claude-opus-5-5:medium
    python scripts/run_eval.py --out results/full --n 60 --configs ...

Raw per-document results go to <out>/<model>__<effort>.jsonl (resumable: documents already
present are skipped). The summary table goes to <out>/summary.md and stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from policylens.extract import extract  # noqa: E402
from policylens.llm import make_client  # noqa: E402
from policylens.schema import FIELD_NAMES  # noqa: E402
from policylens.scorer import DocScore, aggregate, score_document  # noqa: E402

DOCS_DIR = ROOT / "data" / "docs"
TRUTH_DIR = ROOT / "data" / "truth"
FULL_DATASET_SIZE = 60

_lock = threading.Lock()
_progress = {"done": 0, "total": 0}


def _raw_path(out: Path, model: str, effort: str) -> Path:
    return out / f"{model}__{effort}.jsonl"


def _load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _truth(doc_id: str) -> dict:
    return json.loads((TRUTH_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))


def _run_one(client, out: Path, model: str, effort: str, doc_id: str) -> None:
    result = extract(client, DOCS_DIR / f"{doc_id}.pdf", model, effort)
    prediction = result.extraction.model_dump(mode="json") if result.extraction else None
    score = score_document(doc_id, _truth(doc_id), prediction)
    row = {
        "doc_id": doc_id, "model": model, "effort": effort, "served_model": result.served_model,
        "stop_reason": result.stop_reason, "latency_s": round(result.latency_s, 2), "usage": result.usage,
        "cost_usd": result.cost_usd, "request_id": result.request_id, "error": result.error,
        "prediction": prediction,
        "field_correct": {r.field: r.correct for r in score.fields},
        "raw_response": result.raw_response,
    }
    with _lock:
        with _raw_path(out, model, effort).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        _progress["done"] += 1
        done, total = _progress["done"], _progress["total"]
    flag = "" if result.error is None else f"  ERROR: {result.error}"
    print(f"  [{done}/{total}] {model}:{effort} {doc_id} {score.n_correct}/{len(FIELD_NAMES)} "
          f"${result.cost_usd:.4f} {result.latency_s:.1f}s{flag}", flush=True)


def _rescore(rows: list[dict]) -> list[DocScore]:
    return [score_document(r["doc_id"], _truth(r["doc_id"]), r["prediction"]) for r in rows]


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def summarize(out: Path, configs: list[tuple[str, str]]) -> str:
    header = ("| Model | Effort | Docs | Overall field accuracy | All-fields-correct docs | Failures | "
              "Cost/doc | Mean latency | p95 latency | Projected cost (60 docs) |")
    lines = ["# PolicyLens extraction eval", "",
             "Exact match per field after normalization (amounts to paise, dates to ISO, names "
             "case/punctuation/suffix-insensitive). Null vs null counts as correct.", "",
             header, "|---|---|---|---|---|---|---|---|---|---|"]
    projected_total = spent_total = 0.0
    per_field_rows = []
    for model, effort in configs:
        latest = {r["doc_id"]: r for r in _load_rows(_raw_path(out, model, effort))}  # last attempt wins
        rows = list(latest.values())
        if not rows:
            continue
        summary = aggregate(_rescore(rows))
        cost_per_doc = sum(r["cost_usd"] for r in rows) / len(rows)
        latency = sum(r["latency_s"] for r in rows) / len(rows)
        p95 = _p95([r["latency_s"] for r in rows])
        projected = cost_per_doc * FULL_DATASET_SIZE
        projected_total += projected
        spent_total += sum(r["cost_usd"] for r in _load_rows(_raw_path(out, model, effort)))
        fallbacks = sum(1 for r in rows if r["served_model"] and r["served_model"] != model)
        fail_note = f"{summary.n_extraction_failures}" + (f" (+{fallbacks} fallback)" if fallbacks else "")
        lines.append(f"| {model} | {effort} | {len(rows)} | {summary.overall_accuracy:.1%} | "
                     f"{summary.doc_exact_match_rate:.1%} | {fail_note} | ${cost_per_doc:.4f} | "
                     f"{latency:.1f}s | {p95:.1f}s | ${projected:.2f} |")
        per_field_rows.append((f"{model}:{effort}", summary.per_field_accuracy))
    lines.append(f"\n**Projected cost of all configs on {FULL_DATASET_SIZE} docs: ${projected_total:.2f}** "
                 f"(actually spent in this results folder, including retries: ${spent_total:.2f})")
    if per_field_rows:
        lines += ["", "Per-field accuracy:", "",
                  "| Field | " + " | ".join(name for name, _ in per_field_rows) + " |",
                  "|---|" + "---|" * len(per_field_rows)]
        for field in FIELD_NAMES:
            lines.append(f"| {field} | " + " | ".join(f"{acc[field]:.0%}" for _, acc in per_field_rows) + " |")
    return "\n".join(lines + _misses_section(out, configs))


def _misses_section(out: Path, configs: list[tuple[str, str]]) -> list[str]:
    """Every wrong field with truth, prediction and the model's own confidence."""
    lines = ["", "## Every miss", "", "| Config | Doc | Field | Truth | Predicted | Confidence |",
             "|---|---|---|---|---|---|"]
    for model, effort in configs:
        rows = {r["doc_id"]: r for r in _load_rows(_raw_path(out, model, effort))}.values()
        for row in sorted(rows, key=lambda r: r["doc_id"]):
            truth = _truth(row["doc_id"])
            prediction = row["prediction"] or {}
            confidence = prediction.get("confidence") or {}
            for field, ok in row["field_correct"].items():
                if not ok:
                    conf = confidence.get(field)
                    lines.append(f"| {model}:{effort} | {row['doc_id']} | {field} | {truth[field]} | "
                                 f"{prediction.get(field)} | {'' if conf is None else f'{conf:.2f}'} |")
    return lines if len(lines) > 5 else lines[:2] + ["No misses."]


def _parse_config(text: str) -> tuple[str, str]:
    model, _, effort = text.partition(":")
    if not effort:
        raise argparse.ArgumentTypeError(f"config must be model:effort, got {text!r}")
    return model, effort


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--configs", type=_parse_config, nargs="+", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--n", type=int, help="first N documents")
    group.add_argument("--docs", nargs="+", help="explicit doc ids")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    doc_ids = args.docs or [f"doc_{i:03d}" for i in range(1, args.n + 1)]
    jobs = []
    for model, effort in args.configs:
        done = {r["doc_id"] for r in _load_rows(_raw_path(out, model, effort)) if r["error"] is None}
        jobs += [(model, effort, d) for d in doc_ids if d not in done]
    _progress["total"] = len(jobs)

    if jobs:
        client = make_client()
        print(f"Running {len(jobs)} extraction(s) with {args.workers} workers")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(lambda job: _run_one(client, out, *job), jobs))
    report = summarize(out, args.configs)
    (out / "summary.md").write_text(report + "\n", encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    main()
