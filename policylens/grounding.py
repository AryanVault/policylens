"""Amount grounding: is every extracted amount actually printed in the document?

The check reads the PDF's text layer (never the answer key) and collects every amount it can
find, written as figures ("Rs. 48,50,00,000/-", "INR 1,845,000.00", "2.5 Lakhs") or in words
("Rupees Forty Eight Crore Fifty Lakh Only"). An extracted amount that matches none of them was
misread or invented, whatever confidence the model reported.

Limits: it needs a text layer (a scanned document would need OCR first), and it catches misread
numbers, not a correctly read number taken from the wrong line (e.g. total premium including GST
reported as net premium), because that number is printed in the document too.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from .normalize import normalize_amount
from .schema import AMOUNT_FIELDS

_ONES: dict[str, int] = {
    word: value
    for value, word in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_TENS: dict[str, int] = {
    word: 10 * value
    for value, word in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), start=2)
}
_SCALES: dict[str, int] = {
    "thousand": 1_000,
    "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
    "crore": 10_000_000, "crores": 10_000_000,
}
_FILLER = frozenset({"and", "rupees", "rupee", "only", "inr", "rs"})

# "Rupees ... Only" (the near-universal Indian convention for amounts in words).
_WORDS_RE = re.compile(r"\brupees?\s+([a-z][a-z\s\-]*?)\s+only\b", re.IGNORECASE)
# A figure, optionally followed by a lakh/crore unit: "48,50,00,000", "2.5 Lakhs", "1.2 Cr".
_FIGURE_RE = re.compile(
    # Not preceded by a digit/comma (so "INR1,845,000" is read whole), and ending on a digit (so the
    # comma in "Rs. 5,00,000, subject to" is not swallowed into the number).
    r"(?<![\d,])(\d(?:[\d,]*\d)?(?:\.\d+)?)(?:\s*(lakhs?|lacs?|crores?|crs?)\b)?", re.IGNORECASE
)


def parse_amount_words(text: str) -> Decimal:
    """Parse an Indian-English amount in words: "Forty Eight Crore Fifty Lakh" -> 485000000.

    Handles units, tens, hundred, thousand, lakh/lac and crore, "and", hyphens, and a trailing
    paise part ("... and Fifty Paise"). Raises ValueError on anything else.
    """
    tokens = [w for w in re.split(r"[\s\-]+", text.lower()) if w]
    if "paise" in tokens:
        rupee_words, paise_words = _split_paise(tokens[: tokens.index("paise")])
        rupees = _words_to_int(rupee_words) if rupee_words else 0
        return Decimal(rupees) + Decimal(_words_to_int(paise_words)) / 100
    return Decimal(_words_to_int(_content(tokens)))


def _content(tokens: list[str]) -> list[str]:
    return [w for w in tokens if w not in _FILLER]


def _split_paise(tokens: list[str]) -> tuple[list[str], list[str]]:
    """Split "<rupees> [and] <paise>". With "and", the paise are after the last one; without,
    they are the trailing two-digit number ("forty eight", "forty", "nineteen").

    Without "and" this is ambiguous: "One Hundred Fifty Paise" reads as Rs 100 + 50 paise, not
    Rs 1.50. Indian documents almost always write "and ... Paise", so the "and" form is preferred.
    """
    if "and" in tokens:
        cut = len(tokens) - 1 - tokens[::-1].index("and")
        return _content(tokens[:cut]), _content(tokens[cut + 1:])
    words = _content(tokens)
    if len(words) >= 2 and words[-2] in _TENS and words[-1] in _ONES and 0 < _ONES[words[-1]] < 10:
        return words[:-2], words[-2:]
    return words[:-1], words[-1:]


def _words_to_int(words: list[str]) -> int:
    if not words:
        raise ValueError("empty amount in words")
    total = current = 0
    for word in words:
        if word in _ONES:
            current += _ONES[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        elif word in _SCALES:
            total += max(current, 1) * _SCALES[word]
            current = 0
        else:
            raise ValueError(f"not a number word: {word!r}")
    return total + current


def amounts_in_text(text: str) -> frozenset[Decimal]:
    """Every amount printed in ``text``, as figures or in words, normalized to paise."""
    found: set[Decimal] = set()
    for number, unit in _FIGURE_RE.findall(text):
        for candidate in filter(None, (number, f"{number} {unit}" if unit else None)):
            try:
                value = normalize_amount(candidate)
            except ValueError:
                continue  # malformed grouping, dates, phone numbers - not an amount
            if value is not None:
                found.add(value)
    for words in _WORDS_RE.findall(" ".join(text.split())):
        value = _longest_parseable_suffix(words)
        if value is not None:
            found.add(normalize_amount(value))
    return frozenset(found)


def _longest_parseable_suffix(words: str) -> Decimal | None:
    """"Premium Forty Lakh" -> 4000000: skip leading non-number words between "Rupees" and the amount."""
    tokens = words.split()
    for start in range(len(tokens)):
        try:
            return parse_amount_words(" ".join(tokens[start:]))
        except ValueError:
            continue
    return None


@lru_cache(maxsize=256)
def document_text(pdf_path: Path) -> str:
    """The PDF's text layer (empty for a scanned, image-only PDF)."""
    from pypdf import PdfReader  # local import: only grounding needs pypdf

    return "\n".join(page.extract_text() or "" for page in PdfReader(pdf_path).pages)


def ungrounded_amounts(prediction: Mapping[str, Any], text: str) -> list[str]:
    """Review reasons for extracted amounts that are not printed anywhere in ``text``.

    Returns nothing when the document has no text layer: absence of evidence is not evidence.
    """
    if not text.strip():
        return []
    printed = amounts_in_text(text)
    reasons = []
    for field in AMOUNT_FIELDS:
        try:
            value = normalize_amount(prediction.get(field))
        except ValueError:
            continue  # the review module reports unparseable amounts separately
        if value is not None and value not in printed:
            reasons.append(f"amount_not_in_document:{field}")
    return reasons
