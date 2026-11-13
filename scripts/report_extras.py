"""Extra summary.md sections: held-out view, strict vs lenient scoring, a stress test of the
amount-grounding rule, and the non-LLM baseline. No API calls; everything is recomputed from
saved results, the answer keys and the PDFs.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from decimal import Decimal
from pathlib import Path

from policylens.grounding import ungrounded_amounts
from policylens.schema import AMOUNT_FIELDS, FIELD_NAMES
from policylens.scorer import score_document, wilson_interval

Rows = list[dict]
TruthFn = Callable[[str], dict]


def _rates(rows: Rows) -> tuple[float, int, int]:
    """(field accuracy, all-correct docs, docs) from saved strict verdicts."""
    verdicts = [ok for r in rows for ok in r["field_correct"].values()]
    all_ok = sum(all(r["field_correct"].values()) for r in rows)
    return (sum(verdicts) / len(verdicts) if verdicts else 0.0), all_ok, len(rows)


def _ci(successes: int, n: int) -> str:
    low, high = wilson_interval(successes, n)
    return f"{low:.0%}-{high:.0%}"


def held_out_section(per_config: Mapping[str, Rows], truth: TruthFn, smoke_docs: frozenset[str]) -> list[str]:
    lines = ["", f"## Excluding the {len(smoke_docs)} smoke-test documents", "",
             f"The extraction prompt was corrected after a smoke test on {', '.join(sorted(smoke_docs))}, so "
             "those documents influenced the prompt they are scored with. Scores on the remaining documents:", "",
             "| Config | Docs | Field accuracy | All-fields-correct docs | 95% CI |", "|---|---|---|---|---|"]
    for label, rows in per_config.items():
        kept = [r for r in rows if r["doc_id"] not in smoke_docs]
        accuracy, all_ok, n = _rates(kept)
        lines.append(f"| {label} | {n} | {accuracy:.1%} | {all_ok / n:.1%} | {_ci(all_ok, n)} |")
    return lines


def lenient_section(per_config: Mapping[str, Rows], truth: TruthFn) -> list[str]:
    lines = ["", "## Strict vs lenient scoring", "",
             "Strict is the headline. Lenient additionally accepts a name that differs only by a trailing comma "
             "segment (e.g. an obligee printed with its city). It changes nothing else.", "",
             "| Config | Strict field acc. | Lenient field acc. | Strict all-correct | Lenient all-correct |",
             "|---|---|---|---|---|"]
    forgiven: set[str] = set()
    for label, rows in per_config.items():
        strict = [score_document(r["doc_id"], truth(r["doc_id"]), r["prediction"]) for r in rows]
        lenient = [score_document(r["doc_id"], truth(r["doc_id"]), r["prediction"], lenient=True) for r in rows]
        for s, l in zip(strict, lenient):
            forgiven |= {f"{s.doc_id}.{a.field}" for a, b in zip(s.fields, l.fields) if b.correct and not a.correct}
        n_fields = sum(len(s.fields) for s in strict)
        lines.append(
            f"| {label} | {sum(s.n_correct for s in strict) / n_fields:.1%} | "
            f"{sum(s.n_correct for s in lenient) / n_fields:.1%} | "
            f"{sum(s.all_correct for s in strict) / len(rows):.1%} | {sum(s.all_correct for s in lenient) / len(rows):.1%} |")
    lines += ["", f"Misses that lenient scoring forgives: {', '.join(sorted(forgiven)) or 'none'}."]
    return lines


def _swap_first_adjacent_digits(value: Decimal) -> Decimal | None:
    digits = str(int(value))
    for i in range(len(digits) - 1):
        if digits[i] != digits[i + 1]:
            return Decimal(digits[:i] + digits[i + 1] + digits[i] + digits[i + 2:]) + (value - int(value))
    return None


PERTURBATIONS: dict[str, Callable[[Decimal], Decimal | None]] = {
    "x10 (extra zero)": lambda v: v * 10,
    "/10 (dropped zero)": lambda v: v / 10,
    "x100 (lakh read as crore-scale)": lambda v: v * 100,
    "/100": lambda v: v / 100,
    "two adjacent digits swapped": _swap_first_adjacent_digits,
    "off by one rupee": lambda v: v + 1,
}


def grounding_stress_section(truth_paths: list[Path], doc_text: Callable[[str], str]) -> list[str]:
    """Corrupt every true amount in known ways and count how often the rule notices."""
    caught = {name: 0 for name in PERTURBATIONS}
    cases = {name: 0 for name in PERTURBATIONS}
    for path in truth_paths:
        truth = json.loads(path.read_text(encoding="utf-8"))
        text = doc_text(path.stem)
        for field in AMOUNT_FIELDS:
            if truth[field] is None:
                continue
            for name, perturb in PERTURBATIONS.items():
                wrong = perturb(Decimal(str(truth[field])))
                if wrong is None or wrong == Decimal(str(truth[field])):
                    continue
                cases[name] += 1
                prediction = {**truth, field: float(wrong)}
                caught[name] += f"amount_not_in_document:{field}" in ungrounded_amounts(prediction, text)
    lines = ["", "### Stress test: does the grounding rule generalize beyond the two errors it was built after?", "",
             f"Every true amount in the {len(truth_paths)} documents was corrupted in each way below and passed to "
             "the rule. A miss "
             "means the corrupted number happens to be printed elsewhere in the same document (e.g. a sub-limit).",
             "", "| Corruption | Cases | Caught | Rate |", "|---|---|---|---|"]
    lines += [f"| {name} | {cases[name]} | {caught[name]} | {caught[name] / cases[name]:.1%} |"
              for name in PERTURBATIONS if cases[name]]
    return lines


def baseline_section(path: Path, per_config: Mapping[str, Rows], truth: TruthFn, dev_last: str) -> list[str]:
    if not path.exists():
        return []
    baseline = list({r["doc_id"]: r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}.values())
    lines = ["", "## Non-LLM baseline", "",
             f"`policylens/baseline.py`: label matching plus sentence patterns for bond deeds, over the PDF text layer. "
             f"Its rules were fixed by looking at misses on documents up to {dev_last} only, so documents after it "
             "are its held-out score. The models are shown on the same split.", "",
             "| Extractor | Dev field acc. | Dev all-correct | Held-out field acc. | Held-out all-correct | "
             "Held-out 95% CI | Cost/doc |", "|---|---|---|---|---|---|---|"]
    for label, rows in {"rule-baseline (no LLM)": baseline, **per_config}.items():
        dev = [r for r in rows if r["doc_id"] <= dev_last]
        held = [r for r in rows if r["doc_id"] > dev_last]
        if not dev or not held:
            continue
        dev_acc, dev_ok, dev_n = _rates(dev)
        held_acc, held_ok, held_n = _rates(held)
        cost = sum(r["cost_usd"] for r in rows) / len(rows)
        lines.append(f"| {label} | {dev_acc:.1%} | {dev_ok / dev_n:.1%} | {held_acc:.1%} | {held_ok / held_n:.1%} | "
                     f"{_ci(held_ok, held_n)} | ${cost:.4f} |")
    held_base = [r for r in baseline if r["doc_id"] > dev_last]
    per_field = {f: sum(r["field_correct"][f] for r in held_base) / len(held_base) for f in FIELD_NAMES}
    weakest = ", ".join(f"{f} {acc:.0%}" for f, acc in sorted(per_field.items(), key=lambda kv: kv[1])[:4])
    lines += ["", f"Baseline's weakest fields on held-out documents: {weakest}."]
    return lines
