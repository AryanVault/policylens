"""Run the rule-based (non-LLM) baseline over the dataset and save rows in the eval format.

    python scripts/run_baseline.py            # writes results/rule-baseline__none.jsonl

No API calls. The rules were fixed by looking at misses on doc_001-doc_030 only; doc_031-doc_060
were not inspected, so they are the fair held-out score for the baseline.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from policylens.baseline import extract_rules  # noqa: E402
from policylens.grounding import document_text  # noqa: E402
from policylens.scorer import score_document  # noqa: E402

BASELINE_MODEL = "rule-baseline"
BASELINE_EFFORT = "none"
OUT_PATH = ROOT / "results" / f"{BASELINE_MODEL}__{BASELINE_EFFORT}.jsonl"


def main() -> None:
    rows = []
    for truth_path in sorted((ROOT / "data" / "truth").glob("doc_*.json")):
        doc_id = truth_path.stem
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        started = time.perf_counter()
        prediction = extract_rules(document_text(ROOT / "data" / "docs" / f"{doc_id}.pdf"))
        latency = time.perf_counter() - started
        score = score_document(doc_id, truth, prediction)
        rows.append({
            "doc_id": doc_id, "model": BASELINE_MODEL, "effort": BASELINE_EFFORT, "run": "r1",
            "served_model": None, "stop_reason": None, "latency_s": round(latency, 3), "usage": None,
            "cost_usd": 0.0, "request_id": None, "error": None, "prediction": prediction,
            "field_correct": {r.field: r.correct for r in score.fields}, "raw_response": None,
        })
    OUT_PATH.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    correct = sum(ok for r in rows for ok in r["field_correct"].values())
    total = sum(len(r["field_correct"]) for r in rows)
    print(f"{len(rows)} documents, field accuracy {correct / total:.1%} -> {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
