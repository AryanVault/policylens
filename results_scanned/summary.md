# PolicyLens extraction eval

Exact match per field after normalization (amounts to paise, dates to ISO, names case/punctuation/suffix-insensitive). Null vs null counts as correct. Rows with fewer than 60 docs were stopped by a deadline and cover the first docs only.

| Config | Docs | Overall field accuracy | All-fields-correct docs | 95% CI (all-correct) | Failures | Cost/doc | Mean latency | p95 latency | Projected cost (60 docs) |
|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | 60 | 98.3% | 83.3% | 72%-91% | 0 | $0.0007 | 3.9s | 6.5s | $0.04 |
| claude-opus-5-5:low | 60 | 99.7% | 96.7% | 89%-99% | 0 | $0.0267 | 4.0s | 6.7s | $1.60 |

**Projected cost of all configs on 60 docs: $1.65** (actually spent in this results folder, including retries: $1.65)

Per-field accuracy:

| Field | claude-haiku-5-5:low | claude-opus-5-5:low |
|---|---|---|
| insured_name | 97% | 100% |
| insurer_name | 100% | 100% |
| policy_or_bond_number | 95% | 98% |
| document_type | 100% | 100% |
| sum_insured | 93% | 100% |
| premium | 100% | 100% |
| gst_amount | 100% | 100% |
| period_start | 100% | 100% |
| period_end | 100% | 100% |
| beneficiary | 98% | 98% |

The 95% interval is a Wilson score interval on all-fields-correct documents. Overlapping intervals mean the data cannot separate those configs.

## Excluding the 3 smoke-test documents

The extraction prompt was corrected after a smoke test on doc_001, doc_002, doc_003, so those documents influenced the prompt they are scored with. Scores on the remaining documents:

| Config | Docs | Field accuracy | All-fields-correct docs | 95% CI |
|---|---|---|---|---|
| claude-haiku-5-5:low | 57 | 98.2% | 82.5% | 71%-90% |
| claude-opus-5-5:low | 57 | 99.6% | 96.5% | 88%-99% |

## Strict vs lenient scoring

Strict is the headline. Lenient additionally accepts a name that differs only by a trailing comma segment (e.g. an obligee printed with its city). It changes nothing else.

| Config | Strict field acc. | Lenient field acc. | Strict all-correct | Lenient all-correct |
|---|---|---|---|---|
| claude-haiku-5-5:low | 98.3% | 98.3% | 83.3% | 83.3% |
| claude-opus-5-5:low | 99.7% | 99.7% | 96.7% | 96.7% |

Misses that lenient scoring forgives: none.

## Human-review flag

A document is routed to a person if any field's confidence is below 0.80, GST is not 18% of the premium (±₹1) or is present without a premium, the end date is not after the start date, or extraction failed. The flag sees only the model's output, never the truth. Catches are counted per document: a flagged document gets every field checked by a person.

| Config | Docs | Flagged | Docs with errors | Errored docs caught | Field errors caught | False alarms (flagged, no error) |
|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | 60 | 6 (10%) | 10 | 3/10 | 3/10 | 3 |
| claude-opus-5-5:low | 60 | 3 (5%) | 2 | 1/2 | 1/2 | 2 |
| **all configs** | 120 | 9 (8%) | 12 | 4/12 | 4/12 | 5 |

### With the amount-grounding rule

Same flag plus one rule added after the first eval (`policylens/grounding.py`): every extracted amount must be printed somewhere in the PDF's text layer, as figures or in words. It reads the document, never the answer key, and has no threshold to tune.

| Config | Docs | Flagged | Docs with errors | Errored docs caught | Field errors caught | False alarms (flagged, no error) |
|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | 60 | 6 (10%) | 10 | 3/10 | 3/10 | 3 |
| claude-opus-5-5:low | 60 | 3 (5%) | 2 | 1/2 | 1/2 | 2 |
| **all configs** | 120 | 9 (8%) | 12 | 4/12 | 4/12 | 5 |

Confidence-threshold sweep (all configs pooled; 0.80 is the default, fixed before looking at results):

| Threshold | Flagged docs | Errored docs caught | Field errors caught | False alarms |
|---|---|---|---|---|
| 0.50 | 0/120 | 0/12 | 0/12 | 0 |
| 0.70 | 6/120 | 2/12 | 2/12 | 4 |
| 0.80 | 9/120 | 4/12 | 4/12 | 5 |
| 0.90 | 62/120 | 11/12 | 11/12 | 51 |
| 0.95 | 107/120 | 12/12 | 12/12 | 95 |
| 0.99 | 120/120 | 12/12 | 12/12 | 108 |

Rules that fired at 0.80 (documents, all configs pooled): low_confidence: 9.

### Stress test: does the grounding rule generalize beyond the two errors it was built after?

Every true amount in the 60 documents was corrupted in each way below and passed to the rule. A miss means the corrupted number happens to be printed elsewhere in the same document (e.g. a sub-limit).

| Corruption | Cases | Caught | Rate |
|---|---|---|---|
| x10 (extra zero) | 152 | 0 | 0.0% |
| /10 (dropped zero) | 152 | 0 | 0.0% |
| x100 (lakh read as crore-scale) | 152 | 0 | 0.0% |
| /100 | 152 | 0 | 0.0% |
| two adjacent digits swapped | 152 | 0 | 0.0% |
| off by one rupee | 152 | 0 | 0.0% |

## Every miss

| Config | Doc | Field | Truth | Predicted | Confidence | Flagged at 0.80 (with grounding)? |
|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | doc_011 | insured_name | Konkan Chemtrade Imports Private Limited | Konkan Chamitrade Imports Private Limited | 0.90 | no |
| claude-haiku-5-5:low | doc_016 | sum_insured | 50000000.0 | 500000000.0 | 0.93 | no |
| claude-haiku-5-5:low | doc_020 | policy_or_bond_number | KAC/SB/PB/2025/004718 | KAC/SB/PR/2025/004718 | 0.80 | no |
| claude-haiku-5-5:low | doc_028 | policy_or_bond_number | KGI/SB/PB/2025/0047821 | KGI/SB/P3/2025/0047821 | 0.70 | low_confidence:policy_or_bond_number |
| claude-haiku-5-5:low | doc_034 | policy_or_bond_number | AGI/32/FIR/BLUS/2025/004817 | ASI/32/FIR/BLUS/2025/004817 | 0.60 | low_confidence:policy_or_bond_number |
| claude-haiku-5-5:low | doc_037 | sum_insured | 200000000.0 | 2000000000.0 | 0.70 | low_confidence:sum_insured |
| claude-haiku-5-5:low | doc_043 | insured_name | Shivranjani Food Processors Pvt. Ltd. | Shivanjani Food Processors Pvt. Ltd. | 0.80 | no |
| claude-haiku-5-5:low | doc_045 | sum_insured | 185000000.0 | 18500000.0 | 0.90 | no |
| claude-haiku-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Awadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.80 | no |
| claude-haiku-5-5:low | doc_056 | sum_insured | 50000000.0 | 500000000.0 | 0.90 | no |
| claude-opus-5-5:low | doc_028 | policy_or_bond_number | KGI/SB/PB/2025/0047821 | KGI/SB/KB/2025/0047821 | 0.60 | low_confidence:policy_or_bond_number |
| claude-opus-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Awadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.85 | no |
