"""What Opus returns for one synthetic document, the prompt that asks for it, and the
validator that proves the printed values agree with the answer key."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..schema import AMOUNT_FIELDS, FIELD_NAMES, PolicyFields
from ..scorer import normalize_field
from .plan import DocPlan

GST_RATE = 0.18
GST_TOLERANCE_INR = 1.0
DISPLAYED_FIELDS: tuple[str, ...] = tuple(f for f in FIELD_NAMES if f != "document_type")
PROSE_LAYOUTS: frozenset[str] = frozenset({"prose_deed"})


class FieldText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(description="Label printed before the value, e.g. 'Sum Insured'")
    text: str = Field(description="The value exactly as printed, without the label")


class DisplayedFields(BaseModel):
    """How each answer-key value is printed. Null exactly when the truth value is null."""

    model_config = ConfigDict(extra="forbid")
    insured_name: FieldText | None
    insurer_name: FieldText | None
    policy_or_bond_number: FieldText | None
    sum_insured: FieldText | None
    premium: FieldText | None
    gst_amount: FieldText | None
    period_start: FieldText | None
    period_end: FieldText | None
    beneficiary: FieldText | None


class Section(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: str
    body: str


class ExtraRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    value: str


class GeneratedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    truth: PolicyFields
    displayed: DisplayedFields
    title: str
    insurer_address: str
    insured_address: str
    extra_rows: list[ExtraRow]
    sections: list[Section]
    signatory: str


SYSTEM_PROMPT = """\
You write synthetic Indian general-insurance policy documents and surety bonds that are used \
to test a document-extraction system. Every person, company, address, GSTIN, CIN and number \
must be fictional: never use a real insurer, real company or real person. Apart from that, \
make each document read like a genuine Indian document (IRDAI-style wording, UIN, GSTIN, \
stamp duty, intermediary codes, Indian addresses).

You return the document content together with its answer key ("truth"). The answer key is \
used to grade extraction, so it must agree exactly with what the document prints. Plain text \
only - no markdown."""


def build_prompt(plan: DocPlan, problems: list[str] | None = None) -> str:
    omitted = ", ".join(plan.omit) if plan.omit else "none"
    layout_rule = (
        "This layout has no table: the document is the bond text itself. The `text` of every "
        "non-null displayed field must appear verbatim inside the section bodies."
        if plan.layout in PROSE_LAYOUTS
        else "The template prints each displayed field as 'label: text' in a table, so the "
        "section bodies must not restate answer-key values."
    )
    beneficiary_rule = (
        "beneficiary is the obligee in whose favour the bond is issued (a fictional government "
        "department, municipal body or public-sector-style undertaking)."
        if plan.document_type == "surety_bond"
        else "beneficiary must be null (this is not a surety bond)."
    )
    prompt = f"""\
Create one document with this specification.

- document_type: {plan.document_type}  (truth.document_type must be exactly this)
- layout: {plan.layout}
- insurer / surety: "{plan.insurer}"  (truth.insurer_name and the printed name use exactly this)
- insured / principal: invent a fictional {plan.party_hint}
- amount format for every printed amount, including extra rows: {plan.amount_style_text}
- date format for the printed period dates: {plan.date_style_text}
- fields that must be ABSENT (truth null, displayed null, not printed anywhere): {omitted}

Rules:
1. displayed.<field>.text is exactly what the document prints for the value; label is the \
printed label (vary labels realistically, e.g. "Sum Insured", "Bond Amount", "Total Sum \
Insured", "Period of Insurance - From").
2. truth amounts are plain rupee numbers equal to the printed values. premium is the net \
premium excluding GST. gst_amount is 18% of premium rounded to 2 decimals (if you show a \
CGST/SGST split in extra rows, gst_amount is the total).
3. Use realistic magnitudes and premium rates for the line of business.
4. Dates fall in 2025-2027. Annual policies end the day before the anniversary; surety bonds \
run 6-36 months. truth dates are ISO.
5. {beneficiary_rule}
6. extra_rows: 4-8 realistic details that are NOT in the answer key (GSTIN, intermediary \
code, UIN, location of risk, vehicle registration, IDV, deductible, stamp duty, receipt \
number, total premium payable including GST, CGST/SGST split). Distractor amounts are \
welcome but must be clearly labelled.
7. sections: 3-6 sections with headings. {layout_rule}
8. title is the document heading as printed.
"""
    if problems:
        prompt += "\nA previous attempt was rejected for these problems - fix all of them:\n"
        prompt += "\n".join(f"- {p}" for p in problems)
    return prompt


def validate(doc: GeneratedDocument, plan: DocPlan) -> list[str]:
    """Problems that would make the answer key wrong. Empty list means the document is usable."""
    problems: list[str] = []
    truth = doc.truth.model_dump()

    if truth["document_type"] != plan.document_type:
        problems.append(f"truth.document_type is {truth['document_type']!r}, expected {plan.document_type!r}")
    for field in plan.omit:
        if truth[field] is not None:
            problems.append(f"{field} must be absent but truth has {truth[field]!r}")
    if plan.document_type != "surety_bond" and truth["beneficiary"] is not None:
        problems.append("beneficiary must be null for a non-surety document")
    if plan.document_type == "surety_bond" and truth["beneficiary"] is None:
        problems.append("a surety bond needs a beneficiary")

    problems += _check_displayed(doc, truth)
    problems += _check_consistency(truth)
    if plan.layout in PROSE_LAYOUTS:
        problems += _check_prose_contains_values(doc)
    return problems


def _check_displayed(doc: GeneratedDocument, truth: dict) -> list[str]:
    problems = []
    for field in DISPLAYED_FIELDS:
        shown = getattr(doc.displayed, field)
        if (shown is None) != (truth[field] is None):
            problems.append(f"{field}: displayed and truth must both be null or both be set")
            continue
        if shown is None:
            continue
        try:
            printed = normalize_field(field, shown.text)
        except ValueError as exc:
            problems.append(f"{field}: printed text {shown.text!r} is not parseable ({exc})")
            continue
        if printed != normalize_field(field, truth[field]):
            problems.append(f"{field}: printed {shown.text!r} does not equal truth {truth[field]!r}")
    return problems


def _check_consistency(truth: dict) -> list[str]:
    problems = []
    start, end = truth["period_start"], truth["period_end"]
    if start and end and end <= start:
        problems.append("period_end must be after period_start")
    premium, gst = truth["premium"], truth["gst_amount"]
    if premium is not None and gst is not None and abs(gst - premium * GST_RATE) > GST_TOLERANCE_INR:
        problems.append(f"gst_amount {gst} is not 18% of premium {premium}")
    for field in AMOUNT_FIELDS:
        if truth[field] is not None and truth[field] <= 0:
            problems.append(f"{field} must be positive")
    return problems


def _check_prose_contains_values(doc: GeneratedDocument) -> list[str]:
    body = "\n".join(s.body for s in doc.sections)
    problems = []
    for field in DISPLAYED_FIELDS:
        shown = getattr(doc.displayed, field)
        if shown is not None and shown.text not in body:
            problems.append(f"{field}: text {shown.text!r} must appear verbatim in the bond text")
    return problems
