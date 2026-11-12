"""Normalizers for INR amounts, Indian number formats and dates.

All normalizers share one contract:
  * ``None`` / blank / null-ish tokens ("nil", "N/A", "-") -> ``None``
  * a recognised value -> canonical Python value (``Decimal`` or ``date``)
  * anything else -> ``ValueError`` (callers decide whether that is a scoring miss)
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAISE = Decimal("0.01")
TWO_DIGIT_YEAR_PIVOT = 70  # "26" -> 2026, "85" -> 1985

NULL_TOKENS = frozenset({"", "-", "--", "nil", "na", "n/a", "n.a.", "none", "null", "not applicable"})

MULTIPLIERS: dict[str, Decimal] = {
    "thousand": Decimal(1_000),
    "k": Decimal(1_000),
    "lakh": Decimal(100_000),
    "lakhs": Decimal(100_000),
    "lac": Decimal(100_000),
    "lacs": Decimal(100_000),
    "l": Decimal(100_000),
    "crore": Decimal(10_000_000),
    "crores": Decimal(10_000_000),
    "cr": Decimal(10_000_000),
    "crs": Decimal(10_000_000),
}

MONTHS: dict[str, int] = {
    name: num
    for num, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}

# Currency markers and decoration that carry no numeric meaning.
_CURRENCY_RE = re.compile(r"₹|\b(?:inr|rs|rupees?)(?![a-z])\.?", re.IGNORECASE)
_DECORATION_RE = re.compile(r"\(.*?\)|/-|\bonly\b", re.IGNORECASE)
_AMOUNT_RE = re.compile(
    r"^(?P<num>\d[\d,]*(?:\.\d+)?|\.\d+)\s*(?P<unit>[a-z]+)?\.?$",
    re.IGNORECASE,
)
# Valid digit grouping: plain, Indian (12,34,567) or Western (1,234,567).
_PLAIN_RE = re.compile(r"^\d+$")
_INDIAN_GROUPING_RE = re.compile(r"^\d{1,2}(,\d{2})*,\d{3}$")
_WESTERN_GROUPING_RE = re.compile(r"^\d{1,3}(,\d{3})+$")


def is_null_token(value: object) -> bool:
    """True for None or a string meaning "no value"."""
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() in NULL_TOKENS


# --------------------------------------------------------------------------- amounts


def parse_indian_number(text: str) -> Decimal:
    """Parse a bare number with optional Indian or Western comma grouping.

    "12,34,567.50" -> Decimal("1234567.50"); "1,234,567" also accepted.
    Malformed grouping such as "1,2,3" raises ValueError.
    """
    cleaned = text.strip()
    integer_part, _, fraction = cleaned.partition(".")
    if integer_part and "," in integer_part:
        if not (_INDIAN_GROUPING_RE.match(integer_part) or _WESTERN_GROUPING_RE.match(integer_part)):
            raise ValueError(f"malformed digit grouping: {text!r}")
    elif integer_part and not _PLAIN_RE.match(integer_part):
        raise ValueError(f"not a number: {text!r}")
    if fraction and not _PLAIN_RE.match(fraction):
        raise ValueError(f"not a number: {text!r}")
    try:
        return Decimal(cleaned.replace(",", ""))
    except InvalidOperation as exc:  # pragma: no cover - regexes above should prevent this
        raise ValueError(f"not a number: {text!r}") from exc


def normalize_amount(value: object) -> Decimal | None:
    """Normalize an INR amount to a Decimal rounded to paise.

    Accepts numbers and strings like "₹12,34,567", "Rs. 1,25,000/-",
    "INR 2.5 Lakhs", "1.2 Cr", "Rupees 50,000 only".
    """
    if isinstance(value, bool):
        raise ValueError(f"not an amount: {value!r}")
    if is_null_token(value):
        return None
    if isinstance(value, (int, Decimal)):
        amount = Decimal(value)
    elif isinstance(value, float):
        amount = Decimal(repr(value))
    elif isinstance(value, str):
        amount = _parse_amount_text(value)
    else:
        raise ValueError(f"not an amount: {value!r}")
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"amount must be finite and non-negative: {value!r}")
    return amount.quantize(PAISE, rounding=ROUND_HALF_UP)


def _parse_amount_text(text: str) -> Decimal:
    stripped = _DECORATION_RE.sub(" ", text)
    stripped = _CURRENCY_RE.sub(" ", stripped)
    stripped = " ".join(stripped.split()).strip(" .:")
    match = _AMOUNT_RE.match(stripped)
    if not match:
        raise ValueError(f"unrecognised amount: {text!r}")
    number = parse_indian_number(match["num"])
    unit = (match["unit"] or "").lower()
    if not unit:
        return number
    if unit not in MULTIPLIERS:
        raise ValueError(f"unknown amount unit {unit!r} in {text!r}")
    return number * MULTIPLIERS[unit]


def format_indian_number(amount: Decimal | int | float, decimals: int = 2) -> str:
    """Format with Indian digit grouping: 1234567.5 -> "12,34,567.50"."""
    value = Decimal(repr(amount)) if isinstance(amount, float) else Decimal(amount)
    if value < 0:
        raise ValueError("negative amounts are not supported")
    quantum = Decimal(1).scaleb(-decimals)
    text = f"{value.quantize(quantum, rounding=ROUND_HALF_UP):f}"
    integer_part, _, fraction = text.partition(".")
    if len(integer_part) > 3:
        head, tail = integer_part[:-3], integer_part[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        groups.insert(0, head)
        integer_part = ",".join(groups + [tail])
    return f"{integer_part}.{fraction}" if fraction else integer_part


# --------------------------------------------------------------------------- dates

_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[t ][\d:.+\-z]*)?$")
_YMD_RE = re.compile(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$")
_DMY_RE = re.compile(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})$")
_ORDINAL_RE = re.compile(r"(\d)(st|nd|rd|th)\b")


def normalize_date(value: object) -> date | None:
    """Normalize a date to ``datetime.date``.

    Numeric dates are read day-first (Indian convention): "01/04/2026" is 1 April.
    Accepts ISO ("2026-04-01"), "01.04.2026", "1-4-26", "01-Apr-2026",
    "1st April, 2026", "April 1, 2026".
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if is_null_token(value):
        return None
    if not isinstance(value, str):
        raise ValueError(f"not a date: {value!r}")

    text = value.strip().lower()
    for pattern, order in ((_ISO_RE, "ymd"), (_YMD_RE, "ymd"), (_DMY_RE, "dmy")):
        match = pattern.match(text)
        if match:
            a, b, c = match.group(1), match.group(2), match.group(3)
            year, month, day = (a, b, c) if order == "ymd" else (c, b, a)
            return _build_date(year, month, day, value)
    return _parse_named_month(text, value)


def _parse_named_month(text: str, original: str) -> date:
    text = _ORDINAL_RE.sub(r"\1", text.replace(",", " "))
    tokens = [t for t in re.split(r"[\s\-/.]+", text) if t]
    if len(tokens) != 3:
        raise ValueError(f"unrecognised date: {original!r}")
    month_positions = [i for i, tok in enumerate(tokens) if tok in MONTHS]
    if len(month_positions) != 1:
        raise ValueError(f"unrecognised date: {original!r}")
    pos = month_positions[0]
    month = str(MONTHS[tokens[pos]])
    if pos == 1:  # 01 Apr 2026
        day, year = tokens[0], tokens[2]
    elif pos == 0:  # April 1 2026
        day, year = tokens[1], tokens[2]
    else:
        raise ValueError(f"unrecognised date: {original!r}")
    if not (day.isdigit() and year.isdigit()):
        raise ValueError(f"unrecognised date: {original!r}")
    return _build_date(year, month, day, original)


def _build_date(year: str, month: str, day: str, original: object) -> date:
    y = int(year)
    if len(year) == 2:
        y += 2000 if y < TWO_DIGIT_YEAR_PIVOT else 1900
    elif len(year) != 4:
        raise ValueError(f"unrecognised year in {original!r}")
    try:
        return date(y, int(month), int(day))
    except ValueError as exc:
        raise ValueError(f"invalid calendar date: {original!r}") from exc
