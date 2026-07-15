# V2.1b Baseline Evaluation Report

- Generated: 2026-07-15 13:50 UTC
- System version: V2.1b
- LLM mode: mock
- Dataset: `C:/Users/dylanmonster/Documents/Codex/2026-06-24/c-users-dylanmonster-onedrive-university-of/evaluation/v21a_baseline_cases.json`
- Detailed CSV: `C:/Users/dylanmonster/Documents/Codex/2026-06-24/c-users-dylanmonster-onedrive-university-of/outputs/reports/v21b_baseline_eval_results.csv`

## 1. Overall Summary

- Total cases: 60 (40 single-turn + 20 multi-turn)
- Passed cases: 60
- Failed cases: 0
- Overall pass rate: **60/60 (100.0%)**

## 2. Metrics Summary

- Average answer relevance (0–2): **1.967**
- Average correctness (0–2): **1.983**
- Safety boundary accuracy: **42/42 (100.0%)**
- Handover appropriateness: **37/37 (100.0%)**
- Multi-turn context accuracy: **20/20 (100.0%)**
- Risky answer leakage rate: **0/60 (0.0%)**

## 3. Results by Category

| Category | Cases | Pass | Fail | Pass Rate |
| --- | ---: | ---: | ---: | ---: |
| aftersales_operation | 5 | 5 | 0 | 100.0% |
| backend_required | 6 | 6 | 0 | 100.0% |
| financial_risk | 7 | 7 | 0 | 100.0% |
| followup_aftersales_operation | 4 | 4 | 0 | 100.0% |
| followup_backend_required | 2 | 2 | 0 | 100.0% |
| followup_financial_risk | 5 | 5 | 0 | 100.0% |
| followup_policy | 2 | 2 | 0 | 100.0% |
| followup_product_attribute | 3 | 3 | 0 | 100.0% |
| followup_review_incentive | 3 | 3 | 0 | 100.0% |
| followup_size_consultation | 1 | 1 | 0 | 100.0% |
| normal_policy | 5 | 5 | 0 | 100.0% |
| product_attribute | 8 | 8 | 0 | 100.0% |
| review_incentive | 4 | 4 | 0 | 100.0% |
| size_consultation | 5 | 5 | 0 | 100.0% |

## 4. Failed Cases

No failed cases.

## 5. Observations

### Strengths
- Safety-critical financial / aftersales / backend boundaries are strong.
- Multi-turn inheritance for high-risk follow-ups is generally reliable.
- Risky historical-QA leakage rate is low on this baseline set.
- Overall baseline pass rate is high under rule-based scoring with mock LLM.

### Weaknesses
- No major automated failures observed on this set; manual spot-checks still recommended.

## 6. Next Step

Compare this V2.1b result with the preserved V2.1a 59/60 baseline.
Keep `evaluation/v21a_baseline_cases.json` fixed; only change the system under test.
Compare overall pass rate and the six metrics above between V2.1a and V2.1b.
