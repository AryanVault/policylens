from policylens.baseline import extract_rules

# Synthetic documents, fictional parties only.
SCHEDULE = """Konkan Surety & General Insurance Ltd.
 Registered Office: Ratnadurg Towers, Nariman Point, Mumbai - 400021
 Standard Fire and Special Perils Policy - Policy Schedule
PREMIUM AND COVER
Name of the Insured
Shivneri Infracon Pvt. Ltd.
Policy No.
KSG/FIR/2026/004417
Period of Insurance - From
01/04/2026
Period of Insurance - To (Midnight)
31/03/2027
Total Sum Insured (Estimated Annual
Turnover)
Rs. 9,00,00,000/-
Net Premium
Rs. 63,000/-
Total GST @ 18%
Rs. 11,340/-
Total Premium Payable (incl.
GST)
Rs. 74,340/-
"""

DEED = """Deccan Shield Insurance Limited
CONTRACT PERFORMANCE SURETY BOND
KNOW ALL MEN BY THESE PRESENTS that we, Sahyadri Infra Roadways Private Limited, a company
incorporated under the Companies Act, 2013 (hereinafter called the Principal), are held and firmly
bound unto the Pune Road Infrastructure Authority (hereinafter called the Obligee) in the sum of
Rs. 1,87,50,000/- (Rupees One Crore Eighty Seven Lakh Fifty Thousand Only). Bond No. DSIL/SB/2026/0048.
This bond shall be effective from 15-07-2026 and shall remain in force up to and including 14-07-2027.
"""


def test_schedule_layout_with_wrapped_labels():
    fields = extract_rules(SCHEDULE)
    assert fields["insurer_name"] == "Konkan Surety & General Insurance Ltd."
    assert fields["insured_name"] == "Shivneri Infracon Pvt. Ltd."
    assert fields["policy_or_bond_number"] == "KSG/FIR/2026/004417"
    assert fields["document_type"] == "fire"  # not "surety_bond" from the insurer's own name
    assert fields["sum_insured"] == 90_000_000.0
    assert fields["premium"] == 63_000.0      # not the "PREMIUM AND COVER" section header
    assert fields["gst_amount"] == 11_340.0   # not the "(incl. GST)" total on the wrapped line
    assert (fields["period_start"], fields["period_end"]) == ("2026-04-01", "2027-03-31")
    assert fields["beneficiary"] is None


def test_prose_deed_uses_sentence_patterns():
    fields = extract_rules(DEED)
    assert fields["document_type"] == "surety_bond"
    assert fields["insured_name"] == "Sahyadri Infra Roadways Private Limited"
    assert fields["beneficiary"] == "Pune Road Infrastructure Authority"
    assert fields["sum_insured"] == 18_750_000.0
    assert fields["policy_or_bond_number"] == "DSIL/SB/2026/0048"
    assert (fields["period_start"], fields["period_end"]) == ("2026-07-15", "2027-07-14")


def test_empty_text_returns_nothing():
    assert extract_rules("") == {}
