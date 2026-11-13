"""Human-review flag: route an extraction to a person when it looks unreliable.

Rules (any one triggers review):
  * extraction failed (no parsed output)
  * any field's self-reported confidence is below the threshold
  * GST is not 18% of the premium (within a rupee), or GST is present without a premium
  * the period end date is not after the start date
  * (when the document text is supplied) an extracted amount is not printed anywhere in the
    document - see grounding.py. This rule was added after the first eval, see the README.
The flag only sees the model's output and the document - never the ground truth.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .grounding import ungrounded_amounts
from .normalize import normalize_amount, normalize_date
from .schema import FIELD_NAMES

DEFAULT_CONFIDENCE_THRESHOLD = 0.80
GST_RATE = 0.18
GST_TOLERANCE_INR = 1.0


@dataclass(frozen=True)
class ReviewDecision:
    reasons: tuple[str, ...]

    @property
    def needs_review(self) -> bool:
        return bool(self.reasons)


def review(prediction: Mapping[str, Any] | None,
           threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
           doc_text: str | None = None) -> ReviewDecision:
    """Decide whether a person should check this extraction.

    ``doc_text`` is the document's text layer; when given, the amount-grounding rule runs too.
    """
    if prediction is None:
        return ReviewDecision(("extraction_failed",))
    reasons = _low_confidence(prediction, threshold) + _gst_check(prediction) + _period_check(prediction)
    if doc_text is not None:
        reasons += ungrounded_amounts(prediction, doc_text)
    return ReviewDecision(tuple(reasons))


def _low_confidence(prediction: Mapping[str, Any], threshold: float) -> list[str]:
    confidence = prediction.get("confidence") or {}
    return [f"low_confidence:{f}" for f in FIELD_NAMES
            if confidence.get(f) is None or confidence[f] < threshold]


def _gst_check(prediction: Mapping[str, Any]) -> list[str]:
    try:
        premium = normalize_amount(prediction.get("premium"))
        gst = normalize_amount(prediction.get("gst_amount"))
    except ValueError:
        return ["unparseable_amount"]
    if gst is None:
        return []  # many policies print the premium without a GST line
    if premium is None:
        return ["gst_without_premium"]
    if abs(float(gst) - float(premium) * GST_RATE) > GST_TOLERANCE_INR:
        return ["gst_not_18pct_of_premium"]
    return []


def _period_check(prediction: Mapping[str, Any]) -> list[str]:
    try:
        start = normalize_date(prediction.get("period_start"))
        end = normalize_date(prediction.get("period_end"))
    except ValueError:
        return ["unparseable_date"]
    if start and end and end <= start:
        return ["period_end_not_after_start"]
    return []


@dataclass(frozen=True)
class FlagStats:
    docs: int
    flagged_docs: int
    docs_with_errors: int
    errored_docs_flagged: int
    field_errors: int
    field_errors_caught: int  # wrong fields that sit in a flagged document

    @property
    def false_alarms(self) -> int:
        return self.flagged_docs - self.errored_docs_flagged


def evaluate_flag(rows: Iterable[Mapping[str, Any]],
                  threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
                  doc_text: Callable[[str], str] | None = None) -> FlagStats:
    """Score the flag against saved eval rows (each has ``doc_id``, ``prediction`` and
    ``field_correct``). ``doc_text(doc_id)`` supplies document text to enable grounding."""
    docs = flagged = errored = errored_flagged = errors = caught = 0
    for row in rows:
        n_wrong = sum(not ok for ok in row["field_correct"].values())
        text = doc_text(row["doc_id"]) if doc_text else None
        is_flagged = review(row["prediction"], threshold, text).needs_review
        docs += 1
        flagged += is_flagged
        errors += n_wrong
        if n_wrong:
            errored += 1
            errored_flagged += is_flagged
            caught += n_wrong if is_flagged else 0
    return FlagStats(docs, flagged, errored, errored_flagged, errors, caught)
