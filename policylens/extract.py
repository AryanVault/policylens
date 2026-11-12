"""Extract PolicyFields (+ per-field confidence) from a PDF with one Claude call.

The PDF goes in as a base64 ``document`` content block; the answer comes back through
structured outputs (``messages.parse`` with the ``Extraction`` Pydantic model), so the
response is schema-valid by construction. Model and effort are parameters.
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import pydantic

from .llm import FALLBACK_BETA
from .pricing import cost_usd
from .schema import Extraction

MAX_TOKENS = 16000
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Server-side refusal fallback exists for these; Haiku 5.5 has none. The served model is
# recorded on every result so a fallback can never silently contaminate a model's score.
FALLBACK_MODELS = frozenset({"claude-opus-5-5", "claude-sonnet-5-5"})

SYSTEM_PROMPT = """\
You extract structured fields from Indian insurance policy documents and surety bonds.

Rules:
- Report only what the document states. If a field is not printed in the document, return \
null - never infer or compute a missing value.
- Amounts: plain numbers in rupees (e.g. "Rs. 12.5 Lakhs" -> 1250000, "₹1,87,50,000.00" -> \
18750000). sum_insured is the sum insured / bond amount of the cover itself (for a motor \
policy that is the total IDV, Insured's Declared Value), not an underlying contract value, a \
deductible or a sub-limit. premium is the net premium before GST. gst_amount is the total GST on \
that premium (CGST + SGST, or IGST). Do not return a "total premium payable" as premium.
- Dates: ISO format (YYYY-MM-DD). Numeric Indian dates are day-first: 01/04/2026 is 1 April 2026.
- policy_or_bond_number: exactly as printed, including separators.
- insured_name: the policyholder / insured / principal. insurer_name: the insurer or surety. \
beneficiary: the obligee / beneficiary of a surety bond; null for every other document type.
- document_type: surety_bond, fire, marine, motor, health, liability, or other.
- confidence: for each field, your probability (0 to 1) that the extracted value is exactly \
right, including when the value is null."""

USER_PROMPT = "Extract the fields from this document."


@dataclass(frozen=True)
class ExtractionResult:
    model: str
    effort: str
    served_model: str | None
    stop_reason: str | None
    extraction: Extraction | None
    usage: dict[str, int]
    cost_usd: float
    latency_s: float
    request_id: str | None
    error: str | None = None
    raw_response: dict[str, Any] | None = None  # full API response (content, usage, stop_reason)


def _pdf_block(pdf_path: Path) -> dict[str, Any]:
    data = base64.standard_b64encode(pdf_path.read_bytes()).decode("ascii")
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}


def _usage_dict(usage: Any) -> dict[str, int]:
    names = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    return {n: int(getattr(usage, n, 0) or 0) for n in names}


def extract(client: anthropic.Anthropic, pdf_path: Path, model: str, effort: str) -> ExtractionResult:
    """One extraction call. Never raises for API/parse failures - they come back as ``error``."""
    if effort not in EFFORTS:
        raise ValueError(f"effort must be one of {EFFORTS}, got {effort!r}")
    fallback_kwargs: dict[str, Any] = (
        {"betas": [FALLBACK_BETA], "fallbacks": "default"} if model in FALLBACK_MODELS else {}
    )
    started = time.perf_counter()
    try:
        response = client.beta.messages.parse(
            model=model,
            max_tokens=MAX_TOKENS,
            output_config={"effort": effort},
            output_format=Extraction,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [_pdf_block(pdf_path), {"type": "text", "text": USER_PROMPT}]}],
            **fallback_kwargs,
        )
    except pydantic.ValidationError as exc:
        return _failed(model, effort, started, f"schema validation failed: {exc.errors()[:2]}")
    except anthropic.APIStatusError as exc:
        return _failed(model, effort, started, f"API error {exc.status_code}: {exc.message}", exc.request_id)
    except anthropic.APIConnectionError as exc:
        return _failed(model, effort, started, f"connection error: {exc}")

    latency = time.perf_counter() - started
    usage = _usage_dict(response.usage)
    parsed = response.parsed_output if response.stop_reason == "end_turn" else None
    error = None if parsed is not None else f"no parsed output (stop_reason={response.stop_reason})"
    return ExtractionResult(
        model=model,
        effort=effort,
        served_model=response.model,
        stop_reason=response.stop_reason,
        extraction=parsed,
        usage=usage,
        cost_usd=_cost(response.model, model, usage),
        latency_s=latency,
        request_id=response._request_id,
        error=error,
        raw_response=response.model_dump(mode="json", exclude={"parsed_output"}),
    )


def _cost(served_model: str, requested_model: str, usage: dict[str, int]) -> float:
    """Price by the model that served the request; fall back to the requested model's price
    if a fallback model is not in the price table (the row is flagged by served_model anyway)."""
    try:
        return cost_usd(served_model, usage)
    except KeyError:
        return cost_usd(requested_model, usage)


def _failed(model: str, effort: str, started: float, error: str, request_id: str | None = None) -> ExtractionResult:
    return ExtractionResult(model, effort, None, None, None, {}, 0.0, time.perf_counter() - started, request_id, error)
