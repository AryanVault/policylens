"""A rule-based (non-LLM) extractor over the PDF text layer - the baseline the models must beat.

Label matching ("Net Premium", "Policy No.") plus a few patterns for the prose bond deed. It was
written in one sitting against the four layouts in this dataset, with no tuning to the answer
keys - roughly what a first rules-based attempt in a brokerage would look like. It would need new
rules for every new insurer layout, which is the point of the comparison.
"""

from __future__ import annotations

import re
from typing import Any

from .normalize import normalize_amount, normalize_date

_DATE_RE = re.compile(
    r"\d{1,2}(?:st|nd|rd|th)?[\s\-/.](?:\d{1,2}|[A-Za-z]{3,9})[\s\-/.,]+\d{2,4}"
    r"|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{4}-\d{2}-\d{2}"
)
_AMOUNT_RE = re.compile(r"(?:₹|Rs\.?|INR|Rupees)\s*\d[\d,]*(?:\.\d+)?(?:\s*(?:lakhs?|lacs?|crores?|cr)\b)?", re.I)
_POLICY_NO_RE = re.compile(
    r"(?:Policy|Bond|Certificate|Guarantee)[\w ]{0,30}?(?:No\.?|Number)\s*[:\-]?\s*([A-Z0-9][A-Z0-9/\-.]{5,})"
)
_TYPE_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("surety_bond", r"surety|\bbond\b|guarantee"),
    ("marine", r"marine|cargo|transit|voyage"),
    ("motor", r"motor|vehicle|\bidv\b"),
    ("health", r"health|mediclaim|hospitali[sz]ation"),
    ("liability", r"liability|indemnity"),
    ("fire", r"fire|perils|property|sookshma|laghu|burglary"),
)
_LABELS: dict[str, str] = {
    "insured_name": r"name of (?:the )?(?:insured|principal|proposer|policy ?holder)|insured(?:'s)? name"
                    r"|policy ?holder|principal(?: name)?|proposer",
    "sum_insured": r"(?:total )?sum (?:insured|assured)|bond (?:amount|value)|guarantee amount"
                   r"|.*declared value|limit of (?:indemnity|liability)|.*sum insured",
    "premium": r"net premium|(?:basic |annual )?premium(?:\s+(?:amount|payable))?\s*(?:[(:@]|$)"
               r"(?!.*(?:total|incl|gst))",
    "gst_amount": r"(?:total )?(?:i?gst|goods and services tax)\b(?!in)(?!\))",
    "period_start": r".*\bfrom\b|.*commencement|.*start date|.*effective (?:from|date)|.*inception",
    "period_end": r".*\bto\b|.*expiry|.*end date|.*valid (?:up ?to|till)",
    "beneficiary": r"beneficiary|obligee|in favou?r of",
}


LABEL_WINDOW = 3  # lines after a label to search for its value (long labels wrap in table cells)


def _labelled_values(lines: list[str], label: str, window: int = 1) -> list[str]:
    """Values printed after a label: on the same line after ':' or on the following line(s)."""
    pattern = re.compile(rf"^\s*(?:{label})", re.IGNORECASE)
    values = []
    for i, line in enumerate(lines):
        if not pattern.match(line):
            continue
        _, colon, rest = line.partition(":")
        if colon and rest.strip():
            values.append(rest.strip())
        values += [following.strip() for following in lines[i + 1: i + 1 + window]]
    return [v for v in values if v]


def _clean_party(value: str | None) -> str | None:
    """Cut a party name at the address or description that follows it in running text."""
    if value is None:
        return None
    return re.split(r",\s*(?:having|a |an |at |situated|located)|\s*\(hereinafter", value, maxsplit=1)[0].strip()


def _first_amount(values: list[str]) -> float | None:
    for value in values:
        match = _AMOUNT_RE.search(value)
        if match:
            try:
                amount = normalize_amount(match.group(0))
            except ValueError:
                continue
            if amount is not None:
                return float(amount)
    return None


def _first_date(values: list[str]) -> str | None:
    for value in values:
        for candidate in _DATE_RE.findall(value):
            try:
                parsed = normalize_date(candidate.strip(" ,"))
            except ValueError:
                continue
            if parsed:
                return parsed.isoformat()
    return None


def _document_type(text: str, insurer: str) -> str:
    # The insurer's own name ("... Surety & General Insurance") says nothing about this document.
    body = text.replace(insurer, " ").lower() if insurer else text.lower()
    title = " ".join(body.splitlines()[:6])
    for scope in (title, body):
        for doc_type, pattern in _TYPE_KEYWORDS:
            if re.search(pattern, scope):
                return doc_type
    return "other"


def _gst(lines: list[str]) -> float | None:
    gst = _first_amount(_labelled_values(lines, _LABELS["gst_amount"], LABEL_WINDOW))
    if gst is not None:
        return gst
    halves = [_first_amount(_labelled_values(lines, rf"{part}\b", LABEL_WINDOW)) for part in ("cgst", "sgst")]
    return sum(halves) if all(h is not None for h in halves) else None


_DATE = _DATE_RE.pattern


def _prose(text: str) -> dict[str, Any]:
    """Patterns for the bond-deed layout, where facts sit inside sentences."""
    flat = " ".join(text.split())
    found: dict[str, Any] = {}
    if m := re.search(r"\bwe,\s*(?:M/s\.?\s*)?([^,(]+?),", flat, re.I):
        found["insured_name"] = m.group(1).strip()
    if m := re.search(r"unto (?:the )?(.+?)\s*\(hereinafter (?:called|referred to as) the (?:Obligee|Beneficiary)",
                      flat, re.I):
        found["beneficiary"] = _clean_party(m.group(1))
    if m := re.search(r"sum of\s+(.{0,40})", flat, re.I):
        found["sum_insured"] = _first_amount([m.group(1)])
    # "in force from 15-07-2025 (...) up to and including 14-07-2027", "Effective From ... Valid Until ..."
    if m := re.search(rf"\bfrom\s+({_DATE})\b.{{0,80}}?\b(?:to|till|until|up ?to(?: and including)?|ending on)"
                      rf"\s+({_DATE})", flat, re.I):
        found["period_start"], found["period_end"] = _first_date([m.group(1)]), _first_date([m.group(2)])
    return found


def extract_rules(text: str) -> dict[str, Any]:
    """Extract the ten fields from a document's text layer with rules only."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return {}
    insurer = lines[0].strip()
    policy_no = _POLICY_NO_RE.search(text)
    labelled = {
        "insured_name": next(iter(_labelled_values(lines, _LABELS["insured_name"])), None),
        "insurer_name": insurer,
        "policy_or_bond_number": policy_no.group(1).rstrip(".") if policy_no else None,
        "document_type": _document_type(text, insurer),
        "sum_insured": _first_amount(_labelled_values(lines, _LABELS["sum_insured"], LABEL_WINDOW)),
        "premium": _first_amount(_labelled_values(lines, _LABELS["premium"], LABEL_WINDOW)),
        "gst_amount": _gst(lines),
        "period_start": _first_date(_labelled_values(lines, _LABELS["period_start"], LABEL_WINDOW)),
        "period_end": _first_date(_labelled_values(lines, _LABELS["period_end"], LABEL_WINDOW)),
        "beneficiary": _clean_party(next(iter(_labelled_values(lines, _LABELS["beneficiary"])), None)),
    }
    prose = _prose(text)
    if "hereinafter" in text.lower():  # a deed: sentence patterns beat stray label-like lines
        return {field: prose[field] if prose.get(field) is not None else labelled[field] for field in labelled}
    return {field: labelled[field] if labelled[field] is not None else prose.get(field) for field in labelled}
