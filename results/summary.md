# PolicyLens extraction eval

Exact match per field after normalization (amounts to paise, dates to ISO, names case/punctuation/suffix-insensitive). Null vs null counts as correct. Rows with fewer than 60 docs were stopped by a deadline and cover the first docs only.

| Config | Docs | Overall field accuracy | All-fields-correct docs | Failures | Cost/doc | Mean latency | p95 latency | Projected cost (60 docs) |
|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | 60 | 99.7% | 96.7% | 0 | $0.0009 | 3.3s | 7.1s | $0.05 |
| claude-haiku-5-5:low:r2 | 60 | 99.7% | 96.7% | 0 | $0.0008 | 2.3s | 3.5s | $0.05 |
| claude-haiku-5-5:low:r3 | 60 | 99.7% | 96.7% | 0 | $0.0009 | 2.7s | 4.6s | $0.05 |
| claude-sonnet-5-5:low | 60 | 99.5% | 95.0% | 0 | $0.0164 | 3.0s | 3.5s | $0.98 |
| claude-opus-5-5:low | 60 | 99.8% | 98.3% | 0 | $0.0328 | 3.4s | 3.9s | $1.97 |
| claude-opus-5-5:medium | 60 | 99.8% | 98.3% | 0 | $0.0329 | 3.6s | 4.8s | $1.98 |
| claude-fable-5-2:low | 60 | 99.8% | 98.3% | 0 | $0.0657 | 5.6s | 11.2s | $3.94 |

**Projected cost of all configs on 60 docs: $9.02** (actually spent in this results folder, including retries: $9.02)

Per-field accuracy:

| Field | claude-haiku-5-5:low | claude-haiku-5-5:low:r2 | claude-haiku-5-5:low:r3 | claude-sonnet-5-5:low | claude-opus-5-5:low | claude-opus-5-5:medium | claude-fable-5-2:low |
|---|---|---|---|---|---|---|---|
| insured_name | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| insurer_name | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| policy_or_bond_number | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| document_type | 98% | 98% | 98% | 100% | 100% | 100% | 100% |
| sum_insured | 100% | 100% | 100% | 97% | 100% | 100% | 100% |
| premium | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| gst_amount | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| period_start | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| period_end | 100% | 100% | 100% | 100% | 100% | 100% | 100% |
| beneficiary | 98% | 98% | 98% | 98% | 98% | 98% | 98% |

## Run-to-run variance: claude-haiku-5-5 at low effort (3 runs, 60 docs present in every run)

| Run | Field accuracy | All-fields-correct docs | Field errors |
|---|---|---|---|
| claude-haiku-5-5:low | 99.7% | 96.7% | 2 |
| claude-haiku-5-5:low:r2 | 99.7% | 96.7% | 2 |
| claude-haiku-5-5:low:r3 | 99.7% | 96.7% | 2 |

Of 600 doc-fields, 0 got a different (normalized) value in at least one run and 0 flipped between right and wrong.

## Human-review flag

A document is routed to a person if any field's confidence is below 0.80, GST is not 18% of the premium (±₹1) or is present without a premium, the end date is not after the start date, or extraction failed. The flag sees only the model's output, never the truth. Catches are counted per document: a flagged document gets every field checked by a person.

| Config | Docs | Flagged | Docs with errors | Errored docs caught | Field errors caught | False alarms (flagged, no error) |
|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | 60 | 5 (8%) | 2 | 0/2 | 0/2 | 5 |
| claude-haiku-5-5:low:r2 | 60 | 4 (7%) | 2 | 0/2 | 0/2 | 4 |
| claude-haiku-5-5:low:r3 | 60 | 3 (5%) | 2 | 0/2 | 0/2 | 3 |
| claude-sonnet-5-5:low | 60 | 1 (2%) | 3 | 0/3 | 0/3 | 1 |
| claude-opus-5-5:low | 60 | 0 (0%) | 1 | 0/1 | 0/1 | 0 |
| claude-opus-5-5:medium | 60 | 1 (2%) | 1 | 0/1 | 0/1 | 1 |
| claude-fable-5-2:low | 60 | 0 (0%) | 1 | 0/1 | 0/1 | 0 |
| **all configs** | 420 | 14 (3%) | 12 | 0/12 | 0/12 | 14 |

Confidence-threshold sweep (all configs pooled; 0.80 is the default, fixed before looking at results):

| Threshold | Flagged docs | Errored docs caught | Field errors caught | False alarms |
|---|---|---|---|---|
| 0.50 | 0/420 | 0/12 | 0/12 | 0 |
| 0.70 | 10/420 | 0/12 | 0/12 | 10 |
| 0.80 | 14/420 | 0/12 | 0/12 | 14 |
| 0.90 | 76/420 | 5/12 | 5/12 | 71 |
| 0.95 | 294/420 | 11/12 | 11/12 | 283 |
| 0.99 | 420/420 | 12/12 | 12/12 | 408 |

Rules that fired at 0.80 (documents, all configs pooled): low_confidence: 14.

## Every miss

| Config | Doc | Field | Truth | Predicted | Confidence | Flagged at 0.80? |
|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | doc_008 | document_type | liability | other | 0.90 | no |
| claude-haiku-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.94 | no |
| claude-haiku-5-5:low:r2 | doc_008 | document_type | liability | other | 0.90 | no |
| claude-haiku-5-5:low:r2 | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.95 | no |
| claude-haiku-5-5:low:r3 | doc_008 | document_type | liability | other | 0.90 | no |
| claude-haiku-5-5:low:r3 | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.93 | no |
| claude-sonnet-5-5:low | doc_034 | sum_insured | 485000000.0 | 4850000000.0 | 0.97 | no |
| claude-sonnet-5-5:low | doc_037 | sum_insured | 200000000.0 | 2000000000.0 | 0.90 | no |
| claude-sonnet-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.95 | no |
| claude-opus-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.88 | no |
| claude-opus-5-5:medium | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.88 | no |
| claude-fable-5-2:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.90 | no |
