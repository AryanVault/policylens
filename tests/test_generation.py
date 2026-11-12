from dataclasses import replace

import pytest

from policylens.generation.plan import make_plans
from policylens.generation.render import LAYOUTS, render_pdf
from policylens.generation.spec import GeneratedDocument, validate
from policylens.pricing import cost_usd

# Synthetic fixture - fictional parties only.
BOND = {
    "truth": {
        "insured_name": "Shivneri Infracon Private Limited",
        "insurer_name": "Konkan Surety & General Insurance Ltd.",
        "policy_or_bond_number": "KSG/PB/2026/004417",
        "document_type": "surety_bond",
        "sum_insured": 2500000.0,
        "premium": 18000.0,
        "gst_amount": 3240.0,
        "period_start": "2026-04-01",
        "period_end": "2027-03-31",
        "beneficiary": "Executive Engineer, Public Works Division No. 4, Pune",
    },
    "displayed": {
        "insured_name": {"label": "Principal", "text": "Shivneri Infracon Private Limited"},
        "insurer_name": {"label": "Surety", "text": "Konkan Surety & General Insurance Ltd."},
        "policy_or_bond_number": {"label": "Bond No.", "text": "KSG/PB/2026/004417"},
        "sum_insured": {"label": "Bond Amount", "text": "₹25,00,000.00"},
        "premium": {"label": "Premium", "text": "₹18,000.00"},
        "gst_amount": {"label": "GST @ 18%", "text": "₹3,240.00"},
        "period_start": {"label": "Valid From", "text": "01/04/2026"},
        "period_end": {"label": "Valid To", "text": "31/03/2027"},
        "beneficiary": {"label": "Beneficiary", "text": "Executive Engineer, Public Works Division No. 4, Pune"},
    },
    "title": "Performance Bank Guarantee Replacement - Surety Bond",
    "insurer_address": "7th Floor, Example Towers, Ratnagiri 415612",
    "insured_address": "Plot 12, Example MIDC, Pune 411019",
    "extra_rows": [{"label": "Stamp Duty", "value": "₹500.00"}],
    "sections": [{"heading": "Obligation", "body": "The Surety binds itself..."}],
    "signatory": "For Konkan Surety & General Insurance Ltd. - Authorised Signatory",
}


def _doc(**truth_overrides):
    data = {**BOND, "truth": {**BOND["truth"], **truth_overrides}}
    return GeneratedDocument.model_validate(data)


@pytest.fixture
def plan():
    surety = next(p for p in make_plans(8) if p.document_type == "surety_bond")
    return replace(surety, layout="schedule_table", omit=())


def test_plans_are_deterministic_and_varied():
    plans = make_plans(60)
    assert plans == make_plans(60)
    assert len({p.document_type for p in plans}) == 6
    assert len({p.layout for p in plans}) == 4
    assert len({p.amount_style for p in plans}) == 5
    assert len({p.date_style for p in plans}) == 6
    assert sum(p.document_type == "surety_bond" for p in plans) >= 20


def test_valid_document_has_no_problems(plan):
    assert validate(_doc(), plan) == []


def test_printed_amount_mismatch_is_caught(plan):
    problems = validate(_doc(sum_insured=250000.0), plan)
    assert any("sum_insured" in p for p in problems)


def test_wrong_gst_is_caught(plan):
    doc = GeneratedDocument.model_validate({
        **BOND,
        "truth": {**BOND["truth"], "gst_amount": 3600.0},
        "displayed": {**BOND["displayed"], "gst_amount": {"label": "GST", "text": "₹3,600.00"}},
    })
    assert any("18%" in p for p in validate(doc, plan))


def test_omitted_field_must_be_null(plan):
    problems = validate(_doc(), replace(plan, omit=("gst_amount",)))
    assert any("gst_amount must be absent" in p for p in problems)


def test_prose_layout_requires_values_in_text(plan):
    problems = validate(_doc(), replace(plan, layout="prose_deed"))
    assert any("verbatim" in p for p in problems)


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_every_layout_renders(layout, tmp_path):
    path = tmp_path / f"{layout}.pdf"
    render_pdf(_doc(), layout, path)
    assert path.read_bytes()[:5] == b"%PDF-"


def test_cost_usd_opus():
    usage = {"input_tokens": 1_000_000, "output_tokens": 100_000}
    assert cost_usd("claude-opus-5-5", usage) == pytest.approx(4.0 + 2.0)
