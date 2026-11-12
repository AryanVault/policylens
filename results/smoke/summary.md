| Model | Effort | Docs | Field accuracy | All-fields-correct | Failures | Cost/doc | Mean latency | Projected cost (60 docs) |
|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | low | 3 | 96.7% | 66.7% | 0 | $0.0009 | 5.3s | $0.05 |
| claude-sonnet-5-5 | low | 3 | 100.0% | 100.0% | 0 | $0.0167 | 7.2s | $1.00 |
| claude-opus-5-5 | low | 3 | 100.0% | 100.0% | 0 | $0.0334 | 5.4s | $2.01 |
| claude-opus-5-5 | medium | 3 | 96.7% | 66.7% | 0 | $0.0346 | 5.8s | $2.08 |

**Projected cost of all configs on 60 docs: $5.14**

Per-field accuracy:

| Field | claude-haiku-5-5:low | claude-sonnet-5-5:low | claude-opus-5-5:low | claude-opus-5-5:medium |
|---|---|---|---|---|
| insured_name | 100% | 100% | 100% | 100% |
| insurer_name | 100% | 100% | 100% | 100% |
| policy_or_bond_number | 100% | 100% | 100% | 100% |
| document_type | 100% | 100% | 100% | 100% |
| sum_insured | 67% | 100% | 100% | 67% |
| premium | 100% | 100% | 100% | 100% |
| gst_amount | 100% | 100% | 100% | 100% |
| period_start | 100% | 100% | 100% | 100% |
| period_end | 100% | 100% | 100% | 100% |
| beneficiary | 100% | 100% | 100% | 100% |
