"""Per-field exact-match scoring after normalization.

Rules (applied identically to truth and prediction):
  * amounts      -> Decimal rounded to paise, exact match
  * dates        -> datetime.date, exact match (numeric strings read day-first)
  * names        -> NFKC, casefold, punctuation stripped, "M/s"/"The" prefixes dropped,
                    common suffixes canonicalised (Ltd -> limited, Pvt -> private, Co -> company)
  * policy no.   -> NFKC, uppercase, whitespace removed (separators are significant)
  * document type-> lowercase snake_case
  * null vs null is a match; null vs value is a miss (catches hallucination and omission).
A prediction that cannot be normalized is a miss (recorded with the error), never a crash.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .normalize import is_null_token, normalize_amount, normalize_date
from .schema import AMOUNT_FIELDS, DATE_FIELDS, ENUM_FIELDS, FIELD_NAMES, ID_FIELDS, NAME_FIELDS

_NAME_SUFFIXES: dict[str, str] = {
    "ltd": "limited",
    "pvt": "private",
    "co": "company",
    "corp": "corporation",
    "corpn": "corporation",
    "&": "and",
}
_NAME_PREFIXES: tuple[str, ...] = ("m/s", "the")
_NAME_PUNCT_RE = re.compile(r"[.,'\"()\[\]:;]")


def normalize_name(value: object) -> str | None:
    if is_null_token(value):
        return None
    if not isinstance(value, str):
        raise ValueError(f"not a name: {value!r}")
    text = unicodedata.normalize("NFKC", value).casefold().replace("&", " & ")
    tokens = _NAME_PUNCT_RE.sub(" ", text).split()
    while tokens and tokens[0] in _NAME_PREFIXES:
        tokens = tokens[1:]
    canonical = [_NAME_SUFFIXES.get(tok, tok) for tok in tokens]
    return " ".join(canonical) or None


def normalize_identifier(value: object) -> str | None:
    if is_null_token(value):
        return None
    if not isinstance(value, (str, int)):
        raise ValueError(f"not an identifier: {value!r}")
    text = unicodedata.normalize("NFKC", str(value)).upper()
    return "".join(text.split()) or None


def normalize_enum(value: object) -> str | None:
    if is_null_token(value):
        return None
    if not isinstance(value, str):
        raise ValueError(f"not an enum value: {value!r}")
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def normalize_field(field: str, value: object) -> Any:
    """Normalize ``value`` according to the rules for ``field``."""
    if field in AMOUNT_FIELDS:
        return normalize_amount(value)
    if field in DATE_FIELDS:
        return normalize_date(value)
    if field in NAME_FIELDS:
        return normalize_name(value)
    if field in ID_FIELDS:
        return normalize_identifier(value)
    if field in ENUM_FIELDS:
        return normalize_enum(value)
    raise KeyError(f"unknown field: {field!r}")


@dataclass(frozen=True)
class FieldResult:
    field: str
    truth: Any
    predicted: Any
    correct: bool
    error: str | None = None


@dataclass(frozen=True)
class DocScore:
    doc_id: str
    fields: tuple[FieldResult, ...]
    extraction_failed: bool = False

    @property
    def n_correct(self) -> int:
        return sum(result.correct for result in self.fields)

    @property
    def accuracy(self) -> float:
        return self.n_correct / len(self.fields) if self.fields else 0.0

    @property
    def all_correct(self) -> bool:
        return all(result.correct for result in self.fields)

    def result(self, field: str) -> FieldResult:
        return next(r for r in self.fields if r.field == field)


def _drop_trailing_segment(value: object) -> object:
    """"Board, Lucknow" -> "Board". Used only by lenient scoring."""
    return value.rsplit(",", 1)[0] if isinstance(value, str) and "," in value else value


def _lenient_name_match(truth_value: object, predicted_value: object) -> bool:
    """Names also match when one side only adds a trailing ", <place or qualifier>"."""
    truth_norm = normalize_name(truth_value)
    return normalize_name(_drop_trailing_segment(predicted_value)) == truth_norm or (
        normalize_name(_drop_trailing_segment(truth_value)) == normalize_name(predicted_value)
    )


def score_field(field: str, truth_value: object, predicted_value: object, lenient: bool = False) -> FieldResult:
    """Score one field. Truth must normalize cleanly; prediction failures are misses.

    ``lenient`` (reported separately, never the headline) also accepts a name that differs only by
    a trailing comma segment, e.g. an obligee printed with its city.
    """
    truth_norm = normalize_field(field, truth_value)
    try:
        pred_norm = normalize_field(field, predicted_value)
    except ValueError as exc:
        return FieldResult(field, truth_norm, predicted_value, False, error=str(exc))
    correct = truth_norm == pred_norm
    if not correct and lenient and field in NAME_FIELDS and truth_norm and pred_norm:
        correct = _lenient_name_match(truth_value, predicted_value)
    return FieldResult(field, truth_norm, pred_norm, correct)


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion - sane at 0/n and n/n, unlike the normal one."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def score_document(
    doc_id: str,
    truth: Mapping[str, Any],
    predicted: Mapping[str, Any] | None,
    fields: Iterable[str] = FIELD_NAMES,
    lenient: bool = False,
) -> DocScore:
    """Score a whole extraction. ``predicted=None`` means the extraction call failed."""
    field_list = tuple(fields)
    if predicted is None:
        results = tuple(
            FieldResult(f, normalize_field(f, truth.get(f)), None, False, error="extraction failed")
            for f in field_list
        )
        return DocScore(doc_id, results, extraction_failed=True)
    results = tuple(score_field(f, truth.get(f), predicted.get(f), lenient) for f in field_list)
    return DocScore(doc_id, results)


@dataclass(frozen=True)
class Summary:
    n_docs: int
    overall_accuracy: float
    doc_exact_match_rate: float
    per_field_accuracy: dict[str, float]
    n_extraction_failures: int


def aggregate(scores: Iterable[DocScore], fields: Iterable[str] = FIELD_NAMES) -> Summary:
    """Micro-averaged field accuracy, all-fields-correct rate, and per-field accuracy."""
    score_list = tuple(scores)
    field_list = tuple(fields)
    if not score_list:
        return Summary(0, 0.0, 0.0, {f: 0.0 for f in field_list}, 0)
    n = len(score_list)
    per_field = {
        f: sum(s.result(f).correct for s in score_list) / n for f in field_list
    }
    total_correct = sum(s.n_correct for s in score_list)
    total_fields = sum(len(s.fields) for s in score_list)
    return Summary(
        n_docs=n,
        overall_accuracy=total_correct / total_fields if total_fields else 0.0,
        doc_exact_match_rate=sum(s.all_correct for s in score_list) / n,
        per_field_accuracy=per_field,
        n_extraction_failures=sum(s.extraction_failed for s in score_list),
    )
