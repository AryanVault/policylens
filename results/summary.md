# PolicyLens extraction eval

Exact match per field after normalization (amounts to paise, dates to ISO, names case/punctuation/suffix-insensitive). Null vs null counts as correct.

| Model | Effort | Docs | Overall field accuracy | All-fields-correct docs | Failures | Cost/doc | Mean latency | p95 latency | Projected cost (60 docs) |
|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | low | 60 | 99.7% | 96.7% | 0 | $0.0009 | 3.3s | 7.1s | $0.05 |
| claude-sonnet-5-5 | low | 60 | 99.5% | 95.0% | 0 | $0.0164 | 3.0s | 3.5s | $0.98 |
| claude-opus-5-5 | low | 60 | 99.8% | 98.3% | 0 | $0.0328 | 3.4s | 3.9s | $1.97 |
| claude-opus-5-5 | medium | 60 | 99.8% | 98.3% | 0 | $0.0329 | 3.6s | 4.8s | $1.98 |

**Projected cost of all configs on 60 docs: $4.98** (actually spent in this results folder, including retries: $4.98)

Per-field accuracy:

| Field | claude-haiku-5-5:low | claude-sonnet-5-5:low | claude-opus-5-5:low | claude-opus-5-5:medium |
|---|---|---|---|---|
| insured_name | 100% | 100% | 100% | 100% |
| insurer_name | 100% | 100% | 100% | 100% |
| policy_or_bond_number | 100% | 100% | 100% | 100% |
| document_type | 98% | 100% | 100% | 100% |
| sum_insured | 100% | 97% | 100% | 100% |
| premium | 100% | 100% | 100% | 100% |
| gst_amount | 100% | 100% | 100% | 100% |
| period_start | 100% | 100% | 100% | 100% |
| period_end | 100% | 100% | 100% | 100% |
| beneficiary | 98% | 98% | 98% | 98% |

## Every miss

| Config | Doc | Field | Truth | Predicted | Confidence |
|---|---|---|---|---|---|
| claude-haiku-5-5:low | doc_008 | document_type | liability | other | 0.90 |
| claude-haiku-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.94 |
| claude-sonnet-5-5:low | doc_034 | sum_insured | 485000000.0 | 4850000000.0 | 0.97 |
| claude-sonnet-5-5:low | doc_037 | sum_insured | 200000000.0 | 2000000000.0 | 0.90 |
| claude-sonnet-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.95 |
| claude-opus-5-5:low | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.88 |
| claude-opus-5-5:medium | doc_052 | beneficiary | Avadh Metropolitan Drainage & Civic Works Board | Avadh Metropolitan Drainage & Civic Works Board, Lucknow | 0.88 |
