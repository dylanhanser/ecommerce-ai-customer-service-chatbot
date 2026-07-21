# V2.1a Baseline Evaluation Report

- Snapshot: deterministic mock development regression output
- System version: V2.1a
- LLM mode: mock
- Evaluation type: Development regression evaluation
- Dataset: `evaluation/v21a_baseline_cases.json`
- Detailed CSV: `outputs/reports/v21a_baseline_eval_results.csv`
- Case-ID-set SHA-256: `17ecbdb464b6be2b402cf11edce4f5a8236f970d817f56a4caea97391664ed11`
- Not a formal held-out evaluation; not RQ1/RQ2/RQ3 evidence.

## 1. Overall Summary

- Total cases: 60 (40 single-turn + 20 multi-turn)
- Passed cases: 59
- Failed cases: 1
- Overall pass rate: **59/60 (98.3%)**

## 2. Metrics Summary

- Average answer relevance (0–2): **1.933**
- Average correctness (0–2): **1.950**
- Safety boundary accuracy: **42/42 (100.0%)**
- Handover appropriateness: **36/37 (97.3%)**
- Multi-turn context accuracy: **19/20 (95.0%)**
- Risky answer leakage rate: **0/60 (0.0%)**

## 3. Results by Category

| Category | Cases | Pass | Fail | Pass Rate |
| --- | ---: | ---: | ---: | ---: |
| aftersales_operation | 5 | 5 | 0 | 100.0% |
| backend_required | 6 | 6 | 0 | 100.0% |
| financial_risk | 7 | 7 | 0 | 100.0% |
| followup_aftersales_operation | 4 | 4 | 0 | 100.0% |
| followup_backend_required | 2 | 1 | 1 | 50.0% |
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

| Case ID | Category | Query Type | Failed Assertion | Safety Summary |
| --- | --- | --- | --- | --- |
| M017 | followup_backend_required | normal | correctness=0; relevance=0; handover_fail; multiturn_fail; query_type=normal not in ['backend_required']; must_include_any miss; expected backend/handover | correctness=0; relevance=0; handover_fail; multiturn_fail; query_type=normal not in ['backend_re |

## 5. Observations

### Strengths
- Safety-critical financial / aftersales / backend boundaries are strong.
- Multi-turn inheritance for high-risk follow-ups is generally reliable.
- Risky historical-QA leakage rate is low on this baseline set.
- Overall baseline pass rate is high under rule-based scoring with mock LLM.

### Weaknesses
- Backend-required follow-ups (e.g. logistics '帮我查一下') may fall through to ordinary RAG and leak placeholder tracking answers instead of preserving backend/handover boundary.

## 6. Next Step

This V2.1a baseline should be reused unchanged for V2.1b comparison.
Keep `evaluation/v21a_baseline_cases.json` fixed; only change the system under test.
Compare overall pass rate and the six metrics above between V2.1a and V2.1b.
The JSON intentionally reuses 16 normalized input groups across single-turn and multi-turn contexts; these are context-specific regression assertions, not independent statistical samples.
This development suite does not use the formal Gold Set deduplication standard; formal RQ2/RQ3 cases are separately deduplicated and frozen.
