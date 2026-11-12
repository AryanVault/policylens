| Model | Effort | Docs | Field accuracy | All-fields-correct | Failures | Cost/doc | Mean latency | Projected cost (60 docs) |
|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | low | 3 | 100.0% | 100.0% | 0 | $0.0008 | 7.1s | $0.05 |
| claude-sonnet-5-5 | low | 3 | 100.0% | 100.0% | 0 | $0.0168 | 6.9s | $1.01 |
| claude-opus-5-5 | low | 3 | 100.0% | 100.0% | 0 | $0.0336 | 6.9s | $2.01 |
| claude-opus-5-5 | medium | 3 | 100.0% | 100.0% | 0 | $0.0336 | 6.8s | $2.01 |

**Projected cost of all configs on 60 docs: $5.09**

Per-field accuracy:

| Field | claude-haiku-5-5:low | claude-sonnet-5-5:low | claude-opus-5-5:low | claude-opus-5-5:medium |
|---|---|---|---|---|
| insured_name | 100% | 100% | 100% | 100% |
| insurer_name | 100% | 100% | 100% | 100% |
| policy_or_bond_number | 100% | 100% | 100% | 100% |
| document_type | 100% | 100% | 100% | 100% |
| sum_insured | 100% | 100% | 100% | 100% |
| premium | 100% | 100% | 100% | 100% |
| gst_amount | 100% | 100% | 100% | 100% |
| period_start | 100% | 100% | 100% | 100% |
| period_end | 100% | 100% | 100% | 100% |
| beneficiary | 100% | 100% | 100% | 100% |
