import json
from decimal import Decimal
from pathlib import Path

import pytest

from policylens.grounding import amounts_in_text, document_text, parse_amount_words, ungrounded_amounts
from policylens.normalize import normalize_amount
from policylens.review import evaluate_flag, review
from policylens.schema import AMOUNT_FIELDS, FIELD_NAMES

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("words, expected", [
    ("One", 1),
    ("Twenty", 20),
    ("Ninety Nine", 99),
    ("One Hundred", 100),
    ("Thirty Four Thousand Nine Hundred Twenty", 34_920),
    ("One Lakh Ninety Four Thousand", 194_000),
    ("Forty Eight Crore Fifty Lakh", 485_000_000),
    ("One Crore Eighty Seven Lakh Fifty Thousand", 18_750_000),
    ("Twenty Crore", 200_000_000),
    ("One Hundred Twenty Five Crore", 1_250_000_000),
    ("Two Lacs Fifty Thousand", 250_000),
    ("Forty-Two Thousand Three Hundred and Eighty-Six", 42_386),
    ("Rupees Fifty Thousand Only", 50_000),
])
def test_parse_amount_words(words, expected):
    assert parse_amount_words(words) == Decimal(expected)


def test_parse_amount_words_with_paise():
    assert parse_amount_words("Seven Thousand Six Hundred Twenty Nine and Forty Eight Paise") == Decimal("7629.48")
    assert parse_amount_words("Fifty Paise") == Decimal("0.50")


@pytest.mark.parametrize("bad", ["", "Fourty", "One Million"])
def test_parse_amount_words_rejects_non_numbers(bad):
    with pytest.raises(ValueError):
        parse_amount_words(bad)


def test_amounts_in_text_finds_figures_units_and_words():
    text = (
        "Total Sum Insured Rs. 48,50,00,000/- (Rupees Forty Eight Crore Fifty\nLakh Only)\n"
        "Net Premium INR 1,845,000.00  Limit 2.5 Lakhs  Stamp Duty Rs.100/-  GSTIN 27AAKCS4417M1Z6"
    )
    found = amounts_in_text(text)
    for value in ("485000000", "1845000", "250000", "100"):
        assert Decimal(value) in found
    assert Decimal("4850000000") not in found  # the misreading the check exists to catch


PRINTED = "Sum Insured: Rs. 20,00,00,000/-  Net Premium: Rs. 1,40,000/-  GST @ 18%: Rs. 25,200/-"
GOOD = {"sum_insured": 200_000_000.0, "premium": 140_000.0, "gst_amount": 25_200.0}


def test_grounded_extraction_has_no_reasons():
    assert ungrounded_amounts(GOOD, PRINTED) == []


@pytest.mark.parametrize("field, wrong", [
    ("sum_insured", 2_000_000_000.0),   # one zero too many (the real Sonnet error)
    ("premium", 14_000.0),              # one zero too few
    ("gst_amount", 25_002.0),           # transposed digits
])
def test_misread_amount_is_flagged(field, wrong):
    assert ungrounded_amounts({**GOOD, field: wrong}, PRINTED) == [f"amount_not_in_document:{field}"]


def test_null_amounts_and_missing_text_layer_are_not_flagged():
    assert ungrounded_amounts({**GOOD, "gst_amount": None}, PRINTED) == []
    assert ungrounded_amounts({**GOOD, "premium": 1.0}, "   ") == []  # scanned PDF: no evidence


def test_review_runs_grounding_only_when_text_is_given():
    prediction = {**GOOD, "sum_insured": 2_000_000_000.0, "premium": 140_000.0, "gst_amount": 25_200.0,
                  "period_start": "2025-05-01", "period_end": "2026-04-30",
                  "confidence": {f: 0.97 for f in FIELD_NAMES}}
    assert not review(prediction).needs_review
    assert review(prediction, doc_text=PRINTED).reasons == ("amount_not_in_document:sum_insured",)


def test_evaluate_flag_uses_document_text():
    prediction = {**GOOD, "sum_insured": 2_000_000_000.0, "confidence": {f: 0.97 for f in FIELD_NAMES}}
    rows = [{"doc_id": "d1", "prediction": prediction,
             "field_correct": {**{f: True for f in FIELD_NAMES}, "sum_insured": False}}]
    assert evaluate_flag(rows).errored_docs_flagged == 0
    assert evaluate_flag(rows, doc_text=lambda _: PRINTED).errored_docs_flagged == 1


def test_every_true_amount_is_printed_in_its_pdf():
    """Guards the parser: a true amount it cannot find would become a false alarm."""
    truth_files = sorted((ROOT / "data" / "truth").glob("doc_*.json"))
    assert truth_files, "dataset missing"
    for path in truth_files:
        truth = json.loads(path.read_text(encoding="utf-8"))
        printed = amounts_in_text(document_text(ROOT / "data" / "docs" / f"{path.stem}.pdf"))
        for field in AMOUNT_FIELDS:
            value = normalize_amount(truth[field])
            assert value is None or value in printed, f"{path.stem}.{field}={value} not found"


@pytest.mark.parametrize("text, expected", [
    ("Sum Insured Rs. 5,00,000, subject to the terms", "500000"),   # trailing comma is not part of it
    ("Declared value INR1,845,000.00 only", "1845000"),             # currency code glued to the number
    ("Amount in Rupees Premium Forty Lakh Only", "4000000"),         # words after a stray label word
])
def test_amounts_in_text_edge_cases(text, expected):
    assert Decimal(expected) in amounts_in_text(text)


def test_glued_currency_code_is_not_read_as_a_smaller_number():
    assert Decimal("845000") not in amounts_in_text("Declared value INR1,845,000.00 only")
