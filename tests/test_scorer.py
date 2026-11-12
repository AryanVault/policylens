from datetime import date
from decimal import Decimal

import pytest

from policylens.schema import FIELD_NAMES, Extraction, GroundTruth
from policylens.scorer import (
    aggregate,
    normalize_identifier,
    normalize_name,
    score_document,
    score_field,
)

# Synthetic example only - no real client data.
TRUTH = {
    "doc_id": "doc_001",
    "template": "classic",
    "insured_name": "Acme Infra Pvt Ltd",
    "insurer_name": "Example General Insurance Co. Ltd.",
    "policy_or_bond_number": "SB/2026/000123",
    "document_type": "surety_bond",
    "sum_insured": 2500000.0,
    "premium": 18000.0,
    "gst_amount": 3240.0,
    "period_start": "2026-04-01",
    "period_end": "2027-03-31",
    "beneficiary": "National Highways Example Authority",
}


def _perfect_prediction():
    return {k: v for k, v in TRUTH.items() if k in FIELD_NAMES}


# ----------------------------------------------------------------- field normalizers


@pytest.mark.parametrize(
    "a, b",
    [
        ("Acme Infra Pvt Ltd", "ACME INFRA PRIVATE LIMITED"),
        ("M/s. Acme Infra Pvt. Ltd.", "Acme Infra Private Limited"),
        ("The New Example Assurance Co. Ltd.", "New Example Assurance Company Limited"),
        ("Shah & Sons", "Shah and Sons"),
        ("  Acme   Infra  ", "acme infra"),
    ],
)
def test_name_variants_match(a, b):
    assert normalize_name(a) == normalize_name(b)


@pytest.mark.parametrize(
    "a, b",
    [("Acme Infra Pvt Ltd", "Acme Infratech Pvt Ltd"), ("Shah & Sons", "Shah Sons Traders")],
)
def test_different_names_do_not_match(a, b):
    assert normalize_name(a) != normalize_name(b)


def test_identifier_ignores_case_and_spaces_but_keeps_separators():
    assert normalize_identifier("sb/2026/ 000123") == normalize_identifier("SB/2026/000123")
    assert normalize_identifier("SB-2026-000123") != normalize_identifier("SB/2026/000123")


# ----------------------------------------------------------------- score_field


def test_amount_field_matches_across_formats():
    assert score_field("sum_insured", 2500000.0, "₹25,00,000").correct
    assert score_field("sum_insured", 2500000.0, "Rs. 25 Lakhs").correct
    assert not score_field("sum_insured", 2500000.0, 250000).correct


def test_date_field_matches_across_formats():
    assert score_field("period_start", "2026-04-01", "01/04/2026").correct
    assert not score_field("period_start", "2026-04-01", "04/01/2026").correct  # US order = wrong


def test_document_type_normalization():
    assert score_field("document_type", "surety_bond", "Surety Bond").correct
    assert score_field("document_type", "surety_bond", "surety-bond").correct
    assert not score_field("document_type", "surety_bond", "fire").correct


def test_null_handling():
    assert score_field("beneficiary", None, None).correct
    assert score_field("beneficiary", None, "N/A").correct
    assert not score_field("beneficiary", None, "Some Authority").correct  # hallucination
    assert not score_field("gst_amount", 3240.0, None).correct  # omission


def test_unparseable_prediction_is_a_miss_not_a_crash():
    result = score_field("premium", 18000.0, "eighteen thousand")
    assert not result.correct
    assert result.error and "unrecognised amount" in result.error


def test_bad_truth_raises():
    with pytest.raises(ValueError):
        score_field("premium", "garbage", 18000.0)


def test_unknown_field_raises():
    with pytest.raises(KeyError):
        score_field("colour", "red", "red")


# ----------------------------------------------------------------- score_document


def test_perfect_document():
    score = score_document("doc_001", TRUTH, _perfect_prediction())
    assert score.all_correct
    assert score.n_correct == len(FIELD_NAMES)
    assert score.accuracy == 1.0


def test_document_with_two_errors():
    pred = {**_perfect_prediction(), "premium": 1800.0, "period_end": "2027-03-30"}
    score = score_document("doc_001", TRUTH, pred)
    assert score.n_correct == len(FIELD_NAMES) - 2
    assert not score.result("premium").correct
    assert not score.result("period_end").correct
    assert score.result("period_end").truth == date(2027, 3, 31)
    assert score.result("premium").predicted == Decimal("1800.00")


def test_missing_keys_in_prediction_count_as_null():
    pred = {k: v for k, v in _perfect_prediction().items() if k != "beneficiary"}
    assert not score_document("doc_001", TRUTH, pred).result("beneficiary").correct


def test_failed_extraction_scores_zero():
    score = score_document("doc_001", TRUTH, None)
    assert score.extraction_failed
    assert score.n_correct == 0


def test_scoring_does_not_mutate_inputs():
    truth, pred = dict(TRUTH), _perfect_prediction()
    score_document("doc_001", truth, pred)
    assert truth == TRUTH and pred == _perfect_prediction()


def test_scores_a_validated_extraction_model_dump():
    confidence = {f: 0.9 for f in FIELD_NAMES}
    extraction = Extraction(**_perfect_prediction(), confidence=confidence)
    truth = GroundTruth(**TRUTH)
    score = score_document(truth.doc_id, truth.model_dump(), extraction.model_dump())
    assert score.all_correct


# ----------------------------------------------------------------- aggregate


def test_aggregate():
    perfect = score_document("a", TRUTH, _perfect_prediction())
    one_wrong = score_document("b", TRUTH, {**_perfect_prediction(), "insured_name": "Wrong Co"})
    failed = score_document("c", TRUTH, None)
    summary = aggregate([perfect, one_wrong, failed])

    assert summary.n_docs == 3
    assert summary.n_extraction_failures == 1
    assert summary.doc_exact_match_rate == pytest.approx(1 / 3)
    assert summary.overall_accuracy == pytest.approx((10 + 9 + 0) / 30)
    assert summary.per_field_accuracy["insured_name"] == pytest.approx(1 / 3)
    assert summary.per_field_accuracy["premium"] == pytest.approx(2 / 3)


def test_aggregate_empty():
    summary = aggregate([])
    assert summary.n_docs == 0 and summary.overall_accuracy == 0.0
