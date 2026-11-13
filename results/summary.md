# PolicyLens extraction eval

Exact match per field after normalization (amounts to paise, dates to ISO, names case/punctuation/suffix-insensitive). Null vs null counts as correct. Rows with fewer than 60 docs were stopped by a deadline and cover the first docs only.

| Config | Docs | Overall field accuracy | All-fields-correct docs | 95% CI (all-correct) | Failures | Cost/doc | Mean latency | p95 latency | Projected cost (60 docs) |
|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | 60 | 99.7% | 96.7% | 89%-99% | 0 | $0.0009 | 3.3s | 7.1s | $0.05 |
| claude-haiku-5-5:low:r2 | 60 | 99.7% | 96.7% | 89%-99% | 0 | $0.0008 | 2.3s | 3.5s | $0.05 |
| claude-haiku-5-5:low:r3 | 60 | 99.7% | 96.7% | 89%-99% | 0 | $0.0009 | 2.7s | 4.6s | $0.05 |
| claude-sonnet-5-5:low | 60 | 99.5% | 95.0% | 86%-98% | 0 | $0.0164 | 3.0s | 3.5s | $0.98 |
| claude-opus-5-5:low | 60 | 99.8% | 98.3% | 91%-100% | 0 | $0.0328 | 3.4s | 3.9s | $1.97 |
| claude-opus-5-5:medium | 60 | 99.8% | 98.3% | 91%-100% | 0 | $0.0329 | 3.6s | 4.8s | $1.98 |
| claude-fable-5-2:low | 60 | 99.8% | 98.3% | 91%-100% | 0 | $0.0657 | 5.6s | 11.2s | $3.94 |

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

The 95% interval is a Wilson score interval on all-fields-correct documents. Overlapping intervals mean the data cannot separate those configs.

## Excluding the 3 smoke-test documents

The extraction prompt was corrected after a smoke test on doc_001, doc_002, doc_003, so those documents influenced the prompt they are scored with. Scores on the remaining documents:

| Config | Docs | Field accuracy | All-fields-correct docs | 95% CI |
|---|---|---|---|---|
| claude-haiku-5-5:low | 57 | 99.6% | 96.5% | 88%-99% |
| claude-haiku-5-5:low:r2 | 57 | 99.6% | 96.5% | 88%-99% |
| claude-haiku-5-5:low:r3 | 57 | 99.6% | 96.5% | 88%-99% |
| claude-sonnet-5-5:low | 57 | 99.5% | 94.7% | 86%-98% |
| claude-opus-5-5:low | 57 | 99.8% | 98.2% | 91%-100% |
| claude-opus-5-5:medium | 57 | 99.8% | 98.2% | 91%-100% |
| claude-fable-5-2:low | 57 | 99.8% | 98.2% | 91%-100% |

## Strict vs lenient scoring

Strict is the headline. Lenient additionally accepts a name that differs only by a trailing comma segment (e.g. an obligee printed with its city). It changes nothing else.

| Config | Strict field acc. | Lenient field acc. | Strict all-correct | Lenient all-correct |
|---|---|---|---|---|
| claude-haiku-5-5:low | 99.7% | 99.8% | 96.7% | 98.3% |
| claude-haiku-5-5:low:r2 | 99.7% | 99.8% | 96.7% | 98.3% |
| claude-haiku-5-5:low:r3 | 99.7% | 99.8% | 96.7% | 98.3% |
| claude-sonnet-5-5:low | 99.5% | 99.7% | 95.0% | 96.7% |
| claude-opus-5-5:low | 99.8% | 100.0% | 98.3% | 100.0% |
| claude-opus-5-5:medium | 99.8% | 100.0% | 98.3% | 100.0% |
| claude-fable-5-2:low | 99.8% | 100.0% | 98.3% | 100.0% |

Misses that lenient scoring forgives: doc_052.beneficiary.

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

### With the amount-grounding rule

Same flag plus one rule added after the first eval (`policylens/grounding.py`): every extracted amount must be printed somewhere in the PDF's text layer, as figures or in words. It reads the document, never the answer key, and has no threshold to tune.

| Config | Docs | Flagged | Docs with errors | Errored docs caught | Field errors caught | False alarms (flagged, no error) |
|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | 60 | 5 (8%) | 2 | 0/2 | 0/2 | 5 |
| claude-haiku-5-5:low:r2 | 60 | 4 (7%) | 2 | 0/2 | 0/2 | 4 |
| claude-haiku-5-5:low:r3 | 60 | 3 (5%) | 2 | 0/2 | 0/2 | 3 |
| claude-sonnet-5-5:low | 60 | 3 (5%) | 3 | 2/3 | 2/3 | 1 |
| claude-opus-5-5:low | 60 | 0 (0%) | 1 | 0/1 | 0/1 | 0 |
| claude-opus-5-5:medium | 60 | 1 (2%) | 1 | 0/1 | 0/1 | 1 |
| claude-fable-5-2:low | 60 | 0 (0%) | 1 | 0/1 | 0/1 | 0 |
| **all configs** | 420 | 16 (4%) | 12 | 2/12 | 2/12 | 14 |

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

### Stress test: does the grounding rule generalize beyond the two errors it was built after?

Every true amount in the 60 documents was corrupted in each way below and passed to the rule. A miss means the corrupted number happens to be printed elsewhere in the same document (e.g. a sub-limit).

| Corruption | Cases | Caught | Rate |
|---|---|---|---|
| x10 (extra zero) | 152 | 148 | 97.4% |
| /10 (dropped zero) | 152 | 152 | 100.0% |
| x100 (lakh read as crore-scale) | 152 | 152 | 100.0% |
| /100 | 152 | 150 | 98.7% |
| two adjacent digits swapped | 152 | 152 | 100.0% |
| off by one rupee | 152 | 152 | 100.0% |

## Non-LLM baseline

`policylens/baseline.py`: label matching plus sentence patterns for bond deeds, over the PDF text layer. Its rules were fixed by looking at misses on documents up to doc_030 only, so documents after it are its held-out score. The models are shown on the same split.

| Extractor | Dev field acc. | Dev all-correct | Held-out field acc. | Held-out all-correct | Held-out 95% CI | Cost/doc |
|---|---|---|---|---|---|---|
| rule-baseline (no LLM) | 98.3% | 90.0% | 95.7% | 76.7% | 59%-88% | $0.0000 |
| claude-haiku-5-5:low | 99.7% | 96.7% | 99.7% | 96.7% | 83%-99% | $0.0009 |
| claude-haiku-5-5:low:r2 | 99.7% | 96.7% | 99.7% | 96.7% | 83%-99% | $0.0008 |
| claude-haiku-5-5:low:r3 | 99.7% | 96.7% | 99.7% | 96.7% | 83%-99% | $0.0009 |
| claude-sonnet-5-5:low | 100.0% | 100.0% | 99.0% | 90.0% | 74%-97% | $0.0164 |
| claude-opus-5-5:low | 100.0% | 100.0% | 99.7% | 96.7% | 83%-99% | $0.0328 |
| claude-opus-5-5:medium | 100.0% | 100.0% | 99.7% | 96.7% | 83%-99% | $0.0329 |
| claude-fable-5-2:low | 100.0% | 100.0% | 99.7% | 96.7% | 83%-99% | $0.0657 |

Baseline's weakest fields on held-out documents: insured_name 87%, document_type 90%, sum_insured 90%, beneficiary 90%.

## Every miss

| Config | Doc | Field | Truth | Predicted | Confidence | Flagged at 0.80 (with grounding)? |
|---|---|---|---|---|---|---|
| claude-haiku-5-5:low | doc_008 | document_type | liability | other | 0.90 | no |
| claude-haiku-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.94 | no |
| claude-haiku-5-5:low:r2 | doc_008 | document_type | liability | other | 0.90 | no |
| claude-haiku-5-5:low:r2 | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.95 | no |
| claude-haiku-5-5:low:r3 | doc_008 | document_type | liability | other | 0.90 | no |
| claude-haiku-5-5:low:r3 | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.93 | no |
| claude-sonnet-5-5:low | doc_034 | sum_insured | 485000000.0 | 4850000000.0 | 0.97 | amount_not_in_document:sum_insured |
| claude-sonnet-5-5:low | doc_037 | sum_insured | 200000000.0 | 2000000000.0 | 0.90 | amount_not_in_document:sum_insured |
| claude-sonnet-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.95 | no |
| claude-opus-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.88 | no |
| claude-opus-5-5:medium | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.88 | no |
| claude-fable-5-2:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.90 | no |
