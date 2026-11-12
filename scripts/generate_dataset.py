"""Generate synthetic policy / surety-bond PDFs with ground truth, using claude-opus-5-5.

    python scripts/generate_dataset.py --n 3            # smoke test: doc_001..doc_003
    python scripts/generate_dataset.py --n 60 --workers 6

Existing documents are skipped, so a full run resumes after the smoke test.
Every attempt's usage and cost is logged to results/generation_log.jsonl.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402
import pydantic  # noqa: E402

from policylens.generation.plan import DocPlan, make_plans  # noqa: E402
from policylens.generation.render import render_pdf  # noqa: E402
from policylens.generation.spec import SYSTEM_PROMPT, GeneratedDocument, build_prompt, validate  # noqa: E402
from policylens.llm import FALLBACK_BETA, make_client  # noqa: E402
from policylens.pricing import cost_usd  # noqa: E402
from policylens.schema import GroundTruth  # noqa: E402

MODEL = "claude-opus-5-5"
EFFORT = "high"
MAX_TOKENS = 16000
MAX_ATTEMPTS = 3
FULL_DATASET_SIZE = 60

DOCS_DIR = ROOT / "data" / "docs"
TRUTH_DIR = ROOT / "data" / "truth"
RAW_DIR = ROOT / "data" / "generated"
LOG_PATH = ROOT / "results" / "generation_log.jsonl"

_log_lock = threading.Lock()


@dataclass
class DocOutcome:
    doc_id: str
    ok: bool
    attempts: int = 0
    cost_usd: float = 0.0
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    models: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _call(client: anthropic.Anthropic, plan: DocPlan, problems: list[str]):
    return client.beta.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        betas=[FALLBACK_BETA],
        fallbacks="default",
        output_config={"effort": EFFORT},
        output_format=GeneratedDocument,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(plan, problems)}],
    )


def generate_one(client: anthropic.Anthropic, plan: DocPlan) -> DocOutcome:
    outcome = DocOutcome(plan.doc_id, ok=False)
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        outcome.attempts = attempt
        started = time.perf_counter()
        try:
            response = _call(client, plan, problems)
        except pydantic.ValidationError as exc:
            outcome.latency_s += time.perf_counter() - started
            problems = [f"output did not match the schema: {exc.errors()[:3]}"]
            continue  # usage of a schema-invalid response is not returned by the SDK here
        except anthropic.APIStatusError as exc:
            outcome.problems = [f"API error {exc.status_code}: {exc.message} (request {exc.request_id})"]
            return outcome
        outcome.latency_s += time.perf_counter() - started
        outcome.cost_usd += cost_usd(response.model, response.usage)
        outcome.input_tokens += response.usage.input_tokens
        outcome.output_tokens += response.usage.output_tokens
        outcome.models.append(response.model)

        if response.stop_reason != "end_turn" or response.parsed_output is None:
            problems = [f"response ended with stop_reason={response.stop_reason}"]
            continue
        doc: GeneratedDocument = response.parsed_output
        problems = validate(doc, plan)
        if not problems:
            _save(plan, doc, response._request_id)
            outcome.ok = True
            outcome.problems = []
            return outcome
    outcome.problems = problems
    return outcome


def _save(plan: DocPlan, doc: GeneratedDocument, request_id: str | None) -> None:
    render_pdf(doc, plan.layout, DOCS_DIR / f"{plan.doc_id}.pdf")
    truth = GroundTruth(doc_id=plan.doc_id, template=plan.layout, **doc.truth.model_dump())
    TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    (TRUTH_DIR / f"{plan.doc_id}.json").write_text(truth.model_dump_json(indent=2), encoding="utf-8")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw = {"plan": asdict(plan), "request_id": request_id, "generated": doc.model_dump(mode="json")}
    (RAW_DIR / f"{plan.doc_id}.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")


def _log(outcome: DocOutcome) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"model": MODEL, "effort": EFFORT, **asdict(outcome)}, ensure_ascii=False)
    with _log_lock, LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


_progress = {"done": 0, "total": 0}


def _run_and_log(client: anthropic.Anthropic, plan: DocPlan) -> DocOutcome:
    outcome = generate_one(client, plan)
    _log(outcome)
    status = "ok" if outcome.ok else "FAILED"
    with _log_lock:
        _progress["done"] += 1
        counter = f"[{_progress['done']}/{_progress['total']}]"
    print(f"  {counter} {plan.doc_id} [{plan.document_type}/{plan.layout}] {status} "
          f"attempts={outcome.attempts} ${outcome.cost_usd:.4f} {outcome.latency_s:.0f}s", flush=True)
    for problem in outcome.problems:
        print(f"      - {problem}", flush=True)
    return outcome


def _report(outcomes: list[DocOutcome], workers: int, wall_s: float) -> None:
    if not outcomes:
        print("Nothing to do - all requested documents already exist.")
        return
    total = sum(o.cost_usd for o in outcomes)
    per_doc = total / len(outcomes)
    mean_latency = sum(o.latency_s for o in outcomes) / len(outcomes)
    projected_wall_min = FULL_DATASET_SIZE * mean_latency / max(workers, 1) / 60
    print("\n=== Generation cost ===")
    print(f"documents attempted : {len(outcomes)} ({sum(o.ok for o in outcomes)} ok)")
    print(f"tokens in / out     : {sum(o.input_tokens for o in outcomes):,} / {sum(o.output_tokens for o in outcomes):,}")
    print(f"total cost          : ${total:.4f}")
    print(f"mean cost per doc   : ${per_doc:.4f}  (includes retries)")
    print(f"projected for {FULL_DATASET_SIZE}    : ${per_doc * FULL_DATASET_SIZE:.2f}")
    print(f"mean latency / doc  : {mean_latency:.0f}s; this run took {wall_s:.0f}s wall clock")
    print(f"projected wall time : ~{projected_wall_min:.0f} min for {FULL_DATASET_SIZE} docs at {workers} workers")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, required=True, help="generate doc_001..doc_N")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="print plans and the first prompt; no API call")
    args = parser.parse_args()

    plans = [p for p in make_plans(args.n) if not (TRUTH_DIR / f"{p.doc_id}.json").exists()]
    if args.dry_run:
        for p in plans:
            print(p)
        if plans:
            print("\n--- prompt for", plans[0].doc_id, "---\n" + build_prompt(plans[0]))
        return

    client = make_client()
    _progress["total"] = len(plans)
    print(f"Generating {len(plans)} document(s) with {MODEL} (effort={EFFORT}), {args.workers} workers")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        outcomes = list(pool.map(lambda p: _run_and_log(client, p), plans))
    _report(outcomes, args.workers, time.perf_counter() - started)


if __name__ == "__main__":
    main()
