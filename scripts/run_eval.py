"""Run extraction configs (model x effort [x repeat run]) over the dataset, score, and summarize.

    python scripts/run_eval.py --out results --n 60 \
        --configs claude-haiku-5-5:low claude-opus-5-5:medium claude-haiku-5-5:low:r2
    python scripts/run_eval.py --out results --n 60 --configs ... --summary-only   # no API calls

A config is model:effort or model:effort:run (a repeat run gets its own file). Raw per-document
results go to <out>/<model>__<effort>[__<run>].jsonl as they arrive (resumable: documents
already present are skipped). --deadline HH:MM (local time) stops starting new requests.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from policylens.extract import extract  # noqa: E402
from policylens.grounding import document_text  # noqa: E402
from policylens.llm import make_client  # noqa: E402
from policylens.review import DEFAULT_CONFIDENCE_THRESHOLD, evaluate_flag, review  # noqa: E402
from policylens.schema import FIELD_NAMES  # noqa: E402
from policylens.scorer import DocScore, aggregate, normalize_field, score_document, wilson_interval  # noqa: E402

from report_extras import (  # noqa: E402
    baseline_section, grounding_stress_section, held_out_section, lenient_section,
)

DOCS_DIR = ROOT / "data" / "docs"
TRUTH_DIR = ROOT / "data" / "truth"
FULL_DATASET_SIZE = 60
SWEEP_THRESHOLDS = (0.50, 0.70, 0.80, 0.90, 0.95, 0.99)
# The extraction prompt was fixed after a smoke test on these documents (README, "Where it failed").
SMOKE_DOCS = frozenset({"doc_001", "doc_002", "doc_003"})
BASELINE_FILE = "rule-baseline__none.jsonl"
BASELINE_DEV_LAST = "doc_030"  # baseline rules were fixed by looking at doc_001..doc_030 only

_lock = threading.Lock()
_progress = {"done": 0, "total": 0, "skipped": 0}


@dataclass(frozen=True)
class Config:
    model: str
    effort: str
    run: str = ""  # "" = first run; "r2", "r3" = repeats

    @property
    def label(self) -> str:
        return f"{self.model}:{self.effort}" + (f":{self.run}" if self.run else "")

    def path(self, out: Path) -> Path:
        return out / (f"{self.model}__{self.effort}" + (f"__{self.run}" if self.run else "") + ".jsonl")


def _load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _latest_rows(out: Path, cfg: Config) -> list[dict]:
    return list({r["doc_id"]: r for r in _load_rows(cfg.path(out))}.values())  # last attempt wins


def _truth(doc_id: str) -> dict:
    return json.loads((TRUTH_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))


def _run_one(client, out: Path, cfg: Config, doc_id: str, deadline: datetime | None) -> None:
    if deadline and datetime.now() >= deadline:
        with _lock:
            _progress["skipped"] += 1
        return
    result = extract(client, DOCS_DIR / f"{doc_id}.pdf", cfg.model, cfg.effort)
    prediction = result.extraction.model_dump(mode="json") if result.extraction else None
    score = score_document(doc_id, _truth(doc_id), prediction)
    row = {
        "doc_id": doc_id, "model": cfg.model, "effort": cfg.effort, "run": cfg.run or "r1",
        "served_model": result.served_model, "stop_reason": result.stop_reason,
        "latency_s": round(result.latency_s, 2), "usage": result.usage, "cost_usd": result.cost_usd,
        "request_id": result.request_id, "error": result.error, "prediction": prediction,
        "field_correct": {r.field: r.correct for r in score.fields},
        "raw_response": result.raw_response,
    }
    with _lock:
        with cfg.path(out).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        _progress["done"] += 1
        done, total = _progress["done"], _progress["total"]
    flag = "" if result.error is None else f"  ERROR: {result.error}"
    print(f"  [{done}/{total}] {cfg.label} {doc_id} {score.n_correct}/{len(FIELD_NAMES)} "
          f"${result.cost_usd:.4f} {result.latency_s:.1f}s{flag}", flush=True)


def _rescore(rows: list[dict]) -> list[DocScore]:
    return [score_document(r["doc_id"], _truth(r["doc_id"]), r["prediction"]) for r in rows]


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def summarize(out: Path, configs: list[Config]) -> str:
    lines = ["# PolicyLens extraction eval", "",
             "Exact match per field after normalization (amounts to paise, dates to ISO, names "
             "case/punctuation/suffix-insensitive). Null vs null counts as correct. Rows with fewer "
             f"than {FULL_DATASET_SIZE} docs were stopped by a deadline and cover the first docs only.", "",
             "| Config | Docs | Overall field accuracy | All-fields-correct docs | 95% CI (all-correct) | "
             "Failures | Cost/doc | Mean latency | p95 latency | Projected cost (60 docs) |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    projected_total = spent_total = 0.0
    per_field_rows = []
    for cfg in configs:
        rows = _latest_rows(out, cfg)
        if not rows:
            continue
        summary = aggregate(_rescore(rows))
        cost_per_doc = sum(r["cost_usd"] for r in rows) / len(rows)
        latencies = [r["latency_s"] for r in rows]
        projected = cost_per_doc * FULL_DATASET_SIZE
        projected_total += projected
        spent_total += sum(r["cost_usd"] for r in _load_rows(cfg.path(out)))
        fallbacks = sum(1 for r in rows if r["served_model"] and r["served_model"] != cfg.model)
        fail_note = f"{summary.n_extraction_failures}" + (f" (+{fallbacks} fallback)" if fallbacks else "")
        low, high = wilson_interval(round(summary.doc_exact_match_rate * len(rows)), len(rows))
        lines.append(f"| {cfg.label} | {len(rows)} | {summary.overall_accuracy:.1%} | "
                     f"{summary.doc_exact_match_rate:.1%} | {low:.0%}-{high:.0%} | {fail_note} | "
                     f"${cost_per_doc:.4f} | {sum(latencies) / len(latencies):.1f}s | {_p95(latencies):.1f}s | "
                     f"${projected:.2f} |")
        per_field_rows.append((cfg.label, summary.per_field_accuracy))
    lines.append(f"\n**Projected cost of all configs on {FULL_DATASET_SIZE} docs: ${projected_total:.2f}** "
                 f"(actually spent in this results folder, including retries: ${spent_total:.2f})")
    if per_field_rows:
        lines += ["", "Per-field accuracy:", "",
                  "| Field | " + " | ".join(name for name, _ in per_field_rows) + " |",
                  "|---|" + "---|" * len(per_field_rows)]
        for field in FIELD_NAMES:
            lines.append(f"| {field} | " + " | ".join(f"{acc[field]:.0%}" for _, acc in per_field_rows) + " |")
    lines.append("\nThe 95% interval is a Wilson score interval on all-fields-correct documents. Overlapping "
                 "intervals mean the data cannot separate those configs.")
    per_config = {cfg.label: rows for cfg in configs if (rows := _latest_rows(out, cfg))}
    sections = (
        held_out_section(per_config, _truth, SMOKE_DOCS)
        + lenient_section(per_config, _truth)
        + _variance_section(out, configs)
        + _review_section(out, configs)
        + grounding_stress_section(sorted(TRUTH_DIR.glob("doc_*.json")), _doc_text)
        + baseline_section(out / BASELINE_FILE, per_config, _truth, BASELINE_DEV_LAST)
        + _misses_section(out, configs)
    )
    return "\n".join(lines + sections)


def _doc_text(doc_id: str) -> str:
    return document_text(DOCS_DIR / f"{doc_id}.pdf")


def _variance_section(out: Path, configs: list[Config]) -> list[str]:
    """Repeat runs of the same model+effort: how much do predictions and scores move?"""
    groups: dict[tuple[str, str], list[Config]] = {}
    for cfg in configs:
        groups.setdefault((cfg.model, cfg.effort), []).append(cfg)
    lines: list[str] = []
    for (model, effort), runs in groups.items():
        if len(runs) < 2:
            continue
        by_run = {cfg.label: {r["doc_id"]: r for r in _latest_rows(out, cfg)} for cfg in runs}
        common = sorted(set.intersection(*(set(rows) for rows in by_run.values())))
        if not common:
            continue
        lines += ["", f"## Run-to-run variance: {model} at {effort} effort ({len(runs)} runs, "
                  f"{len(common)} docs present in every run)", "",
                  "| Run | Field accuracy | All-fields-correct docs | Field errors |", "|---|---|---|---|"]
        for label, rows in by_run.items():
            s = aggregate(_rescore([rows[d] for d in common]))
            errors = sum(not ok for d in common for ok in rows[d]["field_correct"].values())
            lines.append(f"| {label} | {s.overall_accuracy:.1%} | {s.doc_exact_match_rate:.1%} | {errors} |")
        value_changes, correctness_flips, changed = 0, 0, []
        for doc_id in common:
            for field in FIELD_NAMES:
                values = {repr(_safe_norm(field, (rows[doc_id]["prediction"] or {}).get(field)))
                          for rows in by_run.values()}
                verdicts = {rows[doc_id]["field_correct"][field] for rows in by_run.values()}
                value_changes += len(values) > 1
                correctness_flips += len(verdicts) > 1
                if len(values) > 1:
                    changed.append(f"{doc_id}.{field}")
        total = len(common) * len(FIELD_NAMES)
        lines += ["", f"Of {total} doc-fields, {value_changes} got a different (normalized) value in at "
                  f"least one run and {correctness_flips} flipped between right and wrong."
                  + (f" Changed: {', '.join(changed[:20])}." if changed else "")]
    return lines


def _safe_norm(field: str, value: object) -> object:
    try:
        return normalize_field(field, value)
    except ValueError:
        return f"unparseable:{value!r}"


def _flag_row(label: str, s) -> str:
    return (f"| {label} | {s.docs} | {s.flagged_docs} ({s.flagged_docs / s.docs:.0%}) | {s.docs_with_errors} | "
            f"{s.errored_docs_flagged}/{s.docs_with_errors} | {s.field_errors_caught}/{s.field_errors} | "
            f"{s.false_alarms} |")


def _review_section(out: Path, configs: list[Config]) -> list[str]:
    per_config = {cfg.label: rows for cfg in configs if (rows := _latest_rows(out, cfg))}
    pooled = [row for rows in per_config.values() for row in rows]
    if not pooled:
        return []
    t = DEFAULT_CONFIDENCE_THRESHOLD
    lines = ["", "## Human-review flag", "",
             f"A document is routed to a person if any field's confidence is below {t:.2f}, GST is not "
             "18% of the premium (±₹1) or is present without a premium, the end date is not after the "
             "start date, or extraction failed. The flag sees only the model's output, never the truth. "
             "Catches are counted per document: a flagged document gets every field checked by a person.",
             "", "| Config | Docs | Flagged | Docs with errors | Errored docs caught | Field errors caught | "
             "False alarms (flagged, no error) |", "|---|---|---|---|---|---|---|"]
    lines += [_flag_row(name, evaluate_flag(rows, t)) for name, rows in per_config.items()]
    lines.append(_flag_row("**all configs**", evaluate_flag(pooled, t)))
    lines += ["", "### With the amount-grounding rule", "",
              "Same flag plus one rule added after the first eval (`policylens/grounding.py`): every extracted "
              "amount must be printed somewhere in the PDF's text layer, as figures or in words. It reads the "
              "document, never the answer key, and has no threshold to tune.", "",
              "| Config | Docs | Flagged | Docs with errors | Errored docs caught | Field errors caught | "
              "False alarms (flagged, no error) |", "|---|---|---|---|---|---|---|"]
    lines += [_flag_row(name, evaluate_flag(rows, t, _doc_text)) for name, rows in per_config.items()]
    lines.append(_flag_row("**all configs**", evaluate_flag(pooled, t, _doc_text)))
    lines += ["", f"Confidence-threshold sweep (all configs pooled; {t:.2f} is the default, fixed before "
              "looking at results):", "", "| Threshold | Flagged docs | Errored docs caught | "
              "Field errors caught | False alarms |", "|---|---|---|---|---|"]
    for threshold in SWEEP_THRESHOLDS:
        s = evaluate_flag(pooled, threshold)
        lines.append(f"| {threshold:.2f} | {s.flagged_docs}/{s.docs} | {s.errored_docs_flagged}/{s.docs_with_errors} | "
                     f"{s.field_errors_caught}/{s.field_errors} | {s.false_alarms} |")
    reason_counts: dict[str, int] = {}
    for row in pooled:
        for reason in {r.split(":")[0] for r in review(row["prediction"], t).reasons}:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
    fired = ", ".join(f"{k}: {v}" for k, v in sorted(reason_counts.items())) or "none"
    lines += ["", f"Rules that fired at {t:.2f} (documents, all configs pooled): {fired}."]
    return lines


def _misses_section(out: Path, configs: list[Config]) -> list[str]:
    """Every wrong field with truth, prediction, the model's own confidence, and the review flag."""
    lines = ["", "## Every miss", "", "| Config | Doc | Field | Truth | Predicted | Confidence | "
             f"Flagged at {DEFAULT_CONFIDENCE_THRESHOLD:.2f} (with grounding)? |", "|---|---|---|---|---|---|---|"]
    for cfg in configs:
        for row in sorted(_latest_rows(out, cfg), key=lambda r: r["doc_id"]):
            decision = review(row["prediction"], doc_text=_doc_text(row["doc_id"]))
            flagged = ", ".join(decision.reasons) if decision.needs_review else "no"
            truth = _truth(row["doc_id"])
            prediction = row["prediction"] or {}
            confidence = prediction.get("confidence") or {}
            for field, ok in row["field_correct"].items():
                if not ok:
                    conf = confidence.get(field)
                    lines.append(f"| {cfg.label} | {row['doc_id']} | {field} | {truth[field]} | "
                                 f"{prediction.get(field)} | {'' if conf is None else f'{conf:.2f}'} | "
                                 f"{flagged} |")
    return lines if len(lines) > 5 else lines[:2] + ["No misses."]


def _parse_config(text: str) -> Config:
    parts = text.split(":")
    if len(parts) not in (2, 3) or not all(parts):
        raise argparse.ArgumentTypeError(f"config must be model:effort or model:effort:run, got {text!r}")
    return Config(*parts)


def _parse_deadline(text: str) -> datetime:
    hour, minute = (int(x) for x in text.split(":"))
    return datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)


def main() -> None:
    global DOCS_DIR  # noqa: PLW0603 - one script-wide setting, read by _run_one and _doc_text
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--configs", type=_parse_config, nargs="+", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--n", type=int, help="first N documents")
    group.add_argument("--docs", nargs="+", help="explicit doc ids")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--deadline", type=_parse_deadline, help="HH:MM local time; no new requests after it")
    parser.add_argument("--summary-only", action="store_true",
                        help="rebuild summary.md from saved .jsonl files; never calls the API")
    parser.add_argument("--summary-configs", type=_parse_config, nargs="+",
                        help="configs to include in summary.md (default: --configs)")
    parser.add_argument("--docs-dir", type=Path, default=DOCS_DIR,
                        help="PDFs to extract (default data/docs; data/docs_scanned for the scanned set)")
    args = parser.parse_args()
    DOCS_DIR = args.docs_dir if args.docs_dir.is_absolute() else ROOT / args.docs_dir

    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    doc_ids = args.docs or [f"doc_{i:03d}" for i in range(1, args.n + 1)]
    jobs = []
    for cfg in args.configs:
        done = {r["doc_id"] for r in _load_rows(cfg.path(out)) if r["error"] is None}
        jobs += [(cfg, d) for d in doc_ids if d not in done]
    _progress["total"] = len(jobs)

    if jobs and args.summary_only:
        print(f"--summary-only: {len(jobs)} document(s) have no saved result; summarizing what exists")
    elif jobs:
        client = make_client()
        print(f"Running {len(jobs)} extraction(s) with {args.workers} workers", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            list(pool.map(lambda job: _run_one(client, out, *job, args.deadline), jobs))
        if _progress["skipped"]:
            print(f"Deadline reached: {_progress['skipped']} request(s) not started", flush=True)
    report = summarize(out, args.summary_configs or args.configs)
    (out / "summary.md").write_text(report + "\n", encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    main()
