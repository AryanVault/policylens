from datetime import date, datetime
from decimal import Decimal

import pytest

from policylens.normalize import (
    format_indian_number,
    normalize_amount,
    normalize_date,
    parse_indian_number,
)


# ----------------------------------------------------------------- Indian numbers


@pytest.mark.parametrize(
    "text, expected",
    [
        ("12,34,567", Decimal("1234567")),
        ("1,00,00,000", Decimal("10000000")),
        ("1,234,567", Decimal("1234567")),  # Western grouping also accepted
        ("999", Decimal("999")),
        ("1,000", Decimal("1000")),
        ("12,34,567.50", Decimal("1234567.50")),
        ("1234567", Decimal("1234567")),
    ],
)
def test_parse_indian_number_accepts_valid_grouping(text, expected):
    assert parse_indian_number(text) == expected


@pytest.mark.parametrize("text", ["1,2,3", "12,3456", "1,23,4567", "12,34,56", "1.2.3", "abc"])
def test_parse_indian_number_rejects_malformed(text):
    with pytest.raises(ValueError):
        parse_indian_number(text)


@pytest.mark.parametrize(
    "amount, expected",
    [
        (Decimal("1234567.5"), "12,34,567.50"),
        (10000000, "1,00,00,000.00"),
        (999, "999.00"),
        (1000, "1,000.00"),
        (100000, "1,00,000.00"),
        (0, "0.00"),
        (3240.0, "3,240.00"),
    ],
)
def test_format_indian_number(amount, expected):
    assert format_indian_number(amount) == expected


def test_format_indian_number_without_decimals():
    assert format_indian_number(2500000, decimals=0) == "25,00,000"


def test_format_then_parse_round_trips():
    for value in (Decimal("0.01"), Decimal("12345678901.25"), Decimal("100000")):
        assert parse_indian_number(format_indian_number(value)) == value


# ----------------------------------------------------------------- amounts


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("₹12,34,567", "1234567.00"),
        ("₹ 12,34,567.00", "1234567.00"),
        ("Rs. 1,25,000/-", "125000.00"),
        ("Rs.1,25,000", "125000.00"),
        ("Rs 50000", "50000.00"),
        ("INR 2,50,000", "250000.00"),
        ("INR2,50,000", "250000.00"),
        ("Rupees 50,000 only", "50000.00"),
        ("Rs. 12,34,567/- (Rupees Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven Only)", "1234567.00"),
        ("2.5 Lakhs", "250000.00"),
        ("Rs. 12.5 lakh", "1250000.00"),
        ("5 lacs", "500000.00"),
        ("12.5L", "1250000.00"),
        ("1.2 Cr", "12000000.00"),
        ("₹ 3 crore", "30000000.00"),
        ("2 Crores", "20000000.00"),
        ("50k", "50000.00"),
        ("18,000.505", "18000.51"),  # half-up to paise
    ],
)
def test_normalize_amount_strings(raw, expected):
    assert normalize_amount(raw) == Decimal(expected)


@pytest.mark.parametrize(
    "raw, expected",
    [
        (1234567, "1234567.00"),
        (1234567.0, "1234567.00"),
        (0.1 + 0.2, "0.30"),
        (Decimal("3240"), "3240.00"),
    ],
)
def test_normalize_amount_numbers(raw, expected):
    assert normalize_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", [None, "", "  ", "nil", "N/A", "-", "NA", "null"])
def test_normalize_amount_null_tokens(raw):
    assert normalize_amount(raw) is None


@pytest.mark.parametrize(
    "raw",
    ["abc", "Rs. twelve lakh", "1,2,3", "5 million", "-500", True, [100], float("nan"), "12 34"],
)
def test_normalize_amount_rejects_garbage(raw):
    with pytest.raises(ValueError):
        normalize_amount(raw)


def test_equivalent_amount_spellings_normalize_identically():
    spellings = ["₹12,50,000", "Rs. 12.5 Lakhs", "INR 1,250,000", "1250000", 1250000.0, "12.5L"]
    assert len({normalize_amount(s) for s in spellings}) == 1


# ----------------------------------------------------------------- dates


@pytest.mark.parametrize(
    "raw",
    [
        "2026-04-01",
        "2026-4-1",
        "2026-04-01T00:00:00+05:30",
        "2026/04/01",
        "01/04/2026",  # day-first (Indian)
        "1/4/2026",
        "01-04-2026",
        "01.04.2026",
        "01/04/26",
        "01-Apr-2026",
        "1-apr-26",
        "01 Apr 2026",
        "1st April 2026",
        "1st April, 2026",
        "April 1, 2026",
        "Apr 1st 2026",
        "01 APRIL 2026",
    ],
)
def test_normalize_date_formats(raw):
    assert normalize_date(raw) == date(2026, 4, 1)


def test_normalize_date_is_day_first_for_numeric_dates():
    assert normalize_date("05/11/2026") == date(2026, 11, 5)
    assert normalize_date("31/03/2027") == date(2027, 3, 31)


def test_normalize_date_passthrough_objects():
    assert normalize_date(date(2026, 4, 1)) == date(2026, 4, 1)
    assert normalize_date(datetime(2026, 4, 1, 23, 59)) == date(2026, 4, 1)


def test_two_digit_year_pivot():
    assert normalize_date("01/04/69") == date(2069, 4, 1)
    assert normalize_date("01/04/70") == date(1970, 4, 1)


@pytest.mark.parametrize("raw", [None, "", "N/A", "nil", "-"])
def test_normalize_date_null_tokens(raw):
    assert normalize_date(raw) is None


@pytest.mark.parametrize(
    "raw",
    ["31/02/2026", "2026-13-01", "13/13/2026", "yesterday", "April 2026", "1 Foo 2026", 20260401, "2026 April 01"],
)
def test_normalize_date_rejects_invalid(raw):
    with pytest.raises(ValueError):
        normalize_date(raw)
