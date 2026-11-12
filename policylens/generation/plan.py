"""Deterministic per-document variation plan.

Python (not the model) decides what varies across the dataset, so coverage of document
types, layouts, amount/date formats and missing fields is controlled and reproducible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

DEFAULT_SEED = 20261113

# 3 of every 8 documents are surety bonds (the brokerage's core line).
DOC_TYPE_CYCLE: tuple[str, ...] = (
    "surety_bond",
    "fire",
    "motor",
    "surety_bond",
    "marine",
    "health",
    "surety_bond",
    "liability",
)

LAYOUTS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "surety_bond": ("prose_deed", "schedule_table", "certificate"),
    "default": ("schedule_table", "two_column", "certificate"),
}

AMOUNT_STYLES: dict[str, str] = {
    "rupee_indian": "₹ symbol with Indian digit grouping and paise, e.g. ₹12,34,567.00",
    "rs_slash": "'Rs.' with Indian digit grouping ending in '/-', e.g. Rs. 12,34,567/-",
    "inr_western": "'INR' with Western digit grouping and paise, e.g. INR 1,234,567.00",
    "words_paren": (
        "'Rs.' with Indian digit grouping and '/-', followed by the amount in words in "
        "parentheses, e.g. Rs. 25,00,000/- (Rupees Twenty Five Lakh Only)"
    ),
    "lakh_crore": (
        "amounts of 1 lakh or more in lakh/crore shorthand, e.g. ₹ 25 Lakhs or Rs. 1.5 Crore "
        "(pick amounts that the shorthand states exactly); amounts below 1 lakh with Indian "
        "grouping, e.g. Rs. 48,500"
    ),
}

DATE_STYLES: dict[str, str] = {
    "dmy_slash": "DD/MM/YYYY, e.g. 01/04/2026",
    "dmy_dash": "DD-MM-YYYY, e.g. 01-04-2026",
    "dmy_dot": "DD.MM.YYYY, e.g. 01.04.2026",
    "d_mon_y": "DD-Mon-YYYY, e.g. 01-Apr-2026",
    "ordinal_long": "ordinal day, full month, year, e.g. 1st April 2026",
    "month_first_long": "full month, day, comma, year, e.g. April 1, 2026",
}

# Fictional insurers - deliberately not the names of real Indian insurers.
FICTIONAL_INSURERS: tuple[str, ...] = (
    "Sahyadri General Insurance Company Limited",
    "Ganga Valley General Insurance Co. Ltd.",
    "Deccan Shield Insurance Limited",
    "Konark General Insurance Company Ltd.",
    "Vindhya Assurance Company Limited",
    "Konkan Surety & General Insurance Ltd.",
    "Narmada General Insurance Co. Ltd.",
    "Himgiri Insurance Company Limited",
    "Aravalli General Insurance Limited",
    "Kaveri Assurance Co. Ltd.",
)

PARTY_HINTS: tuple[str, ...] = (
    "road construction contractor in Pune",
    "textile exporter in Tiruppur",
    "pharmaceutical distributor in Ahmedabad",
    "solar EPC contractor in Jaipur",
    "cold-chain logistics firm in Kolkata",
    "auto-components manufacturer in Chennai",
    "IT services company in Bengaluru",
    "food processing unit in Indore",
    "civil works contractor in Lucknow",
    "family-run jewellery business in Surat",
    "hospital trust in Kochi",
    "steel trader in Raipur",
    "individual salaried professional in Hyderabad",
    "water-supply pipeline contractor in Bhubaneswar",
    "chemical importer in Navi Mumbai",
    "dredging and port services company in Visakhapatnam",
)


@dataclass(frozen=True)
class DocPlan:
    doc_id: str
    document_type: str
    layout: str
    amount_style: str
    date_style: str
    insurer: str
    party_hint: str
    omit: tuple[str, ...]  # fields that must be absent from the document (truth = null)

    @property
    def amount_style_text(self) -> str:
        return AMOUNT_STYLES[self.amount_style]

    @property
    def date_style_text(self) -> str:
        return DATE_STYLES[self.date_style]


def _omissions(doc_type: str, layout: str, rng: random.Random) -> tuple[str, ...]:
    omit: list[str] = []
    if doc_type == "surety_bond" and layout == "prose_deed":
        omit += ["premium", "gst_amount"]  # a bond deed does not print the premium
    elif rng.random() < 0.2:
        omit.append("gst_amount")
    if rng.random() < 0.08:
        omit.append("policy_or_bond_number")
    return tuple(omit)


def make_plans(n: int, seed: int = DEFAULT_SEED) -> list[DocPlan]:
    """Plans for doc_001..doc_{n}. The same seed always gives the same plans."""
    rng = random.Random(seed)
    amount_keys, date_keys = list(AMOUNT_STYLES), list(DATE_STYLES)
    plans = []
    for i in range(n):
        doc_type = DOC_TYPE_CYCLE[i % len(DOC_TYPE_CYCLE)]
        layouts = LAYOUTS_BY_TYPE.get(doc_type, LAYOUTS_BY_TYPE["default"])
        layout = layouts[i % len(layouts)]
        plans.append(
            DocPlan(
                doc_id=f"doc_{i + 1:03d}",
                document_type=doc_type,
                layout=layout,
                amount_style=amount_keys[i % len(amount_keys)],
                date_style=date_keys[(i * 5 + 1) % len(date_keys)],
                insurer=rng.choice(FICTIONAL_INSURERS),
                party_hint=rng.choice(PARTY_HINTS),
                omit=_omissions(doc_type, layout, rng),
            )
        )
    return plans
