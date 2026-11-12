"""Pydantic schema for extracted policy / surety-bond fields.

The same field set is used for ground truth (written by the dataset generator)
and for model extractions (which additionally carry per-field confidence).
Amounts are plain INR numbers (rupees, not paise); dates are ISO dates.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DocumentType = Literal[
    "surety_bond",
    "fire",
    "marine",
    "motor",
    "health",
    "liability",
    "other",
]

AMOUNT_FIELDS: tuple[str, ...] = ("sum_insured", "premium", "gst_amount")
DATE_FIELDS: tuple[str, ...] = ("period_start", "period_end")
NAME_FIELDS: tuple[str, ...] = ("insured_name", "insurer_name", "beneficiary")
ID_FIELDS: tuple[str, ...] = ("policy_or_bond_number",)
ENUM_FIELDS: tuple[str, ...] = ("document_type",)

FIELD_NAMES: tuple[str, ...] = (
    "insured_name",
    "insurer_name",
    "policy_or_bond_number",
    "document_type",
    "sum_insured",
    "premium",
    "gst_amount",
    "period_start",
    "period_end",
    "beneficiary",
)


class PolicyFields(BaseModel):
    """The ten extracted fields. Null means "not present in the document"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    insured_name: str | None = Field(description="Policyholder / principal / insured party")
    insurer_name: str | None = Field(description="Insurance company or surety issuing the document")
    policy_or_bond_number: str | None = Field(description="Policy or bond number exactly as printed")
    document_type: DocumentType | None = Field(description="Line of business of the document")
    sum_insured: float | None = Field(description="Sum insured / bond amount in INR (rupees)")
    premium: float | None = Field(description="Net premium in INR, excluding GST")
    gst_amount: float | None = Field(description="GST charged on the premium in INR")
    period_start: date | None = Field(description="Cover / bond start date")
    period_end: date | None = Field(description="Cover / bond end date")
    beneficiary: str | None = Field(
        description="Obligee / beneficiary of a surety bond; null for other document types"
    )


class FieldConfidence(BaseModel):
    """Model's self-reported confidence (0-1) for each field."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    insured_name: float
    insurer_name: float
    policy_or_bond_number: float
    document_type: float
    sum_insured: float
    premium: float
    gst_amount: float
    period_start: float
    period_end: float
    beneficiary: float


class Extraction(PolicyFields):
    """What a model returns: the fields plus per-field confidence."""

    confidence: FieldConfidence


class GroundTruth(PolicyFields):
    """Ground truth for one synthetic document, stored in data/truth/<doc_id>.json."""

    doc_id: str
    template: str | None = None
