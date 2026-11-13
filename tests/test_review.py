import pytest

from policylens.review import evaluate_flag, review
from policylens.schema import FIELD_NAMES

# Synthetic prediction - fictional parties only.
GOOD = {
    "insured_name": "Shivneri Infracon Private Limited",
    "insurer_name": "Konkan Surety & General Insurance Ltd.",
    "policy_or_bond_number": "KSG/PB/2026/004417",
    "document_type": "fire",
    "sum_insured": 2500000.0,
    "premium": 18000.0,
    "gst_amount": 3240.0,
    "period_start": "2026-04-01",
    "period_end": "2027-03-31",
    "beneficiary": None,
    "confidence": {f: 0.97 for f in FIELD_NAMES},
}


def _with(**changes):
    return {**GOOD, **changes}


def test_clean_extraction_is_not_flagged():
    assert not review(GOOD).needs_review


def test_failed_extraction_is_flagged():
    assert review(None).reasons == ("extraction_failed",)


def test_low_confidence_is_flagged_per_field():
    pred = _with(confidence={**GOOD["confidence"], "premium": 0.6})
    assert review(pred, threshold=0.8).reasons == ("low_confidence:premium",)
    assert not review(pred, threshold=0.5).needs_review


def test_missing_confidence_counts_as_low():
    pred = _with(confidence={f: 0.97 for f in FIELD_NAMES if f != "insured_name"})
    assert "low_confidence:insured_name" in review(pred).reasons


@pytest.mark.parametrize("gst, flagged", [(3240.0, False), (3240.9, False), (3242.0, True), (324.0, True)])
def test_gst_must_be_18pct_of_premium(gst, flagged):
    assert review(_with(gst_amount=gst)).needs_review is flagged


def test_premium_without_gst_is_fine_but_gst_without_premium_is_not():
    assert not review(_with(gst_amount=None)).needs_review
    assert review(_with(premium=None)).reasons == ("gst_without_premium",)


@pytest.mark.parametrize("end, flagged", [("2027-03-31", False), ("2026-04-01", True), ("2025-03-31", True)])
def test_end_date_must_be_after_start(end, flagged):
    assert review(_with(period_end=end)).needs_review is flagged


def test_evaluate_flag_counts_catches_and_false_alarms():
    ok = {f: True for f in FIELD_NAMES}
    rows = [
        {"prediction": GOOD, "field_correct": ok},                                   # clean, not flagged
        {"prediction": _with(gst_amount=1.0), "field_correct": {**ok, "gst_amount": False}},  # caught
        {"prediction": GOOD, "field_correct": {**ok, "sum_insured": False}},          # missed
        {"prediction": _with(period_end="2020-01-01"), "field_correct": ok},          # false alarm
    ]
    stats = evaluate_flag(rows)
    assert (stats.docs, stats.flagged_docs, stats.docs_with_errors) == (4, 2, 2)
    assert (stats.errored_docs_flagged, stats.field_errors, stats.field_errors_caught) == (1, 2, 1)
    assert stats.false_alarms == 1
