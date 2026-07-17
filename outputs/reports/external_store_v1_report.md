# external_store_v1 external evaluation candidate report

## Input validation

- Recognized TXT files: 6
- Recognized months: 1, 2, 3, 4, 5, 6
- Missing months: 0
- Duplicate months: 0
- Empty files: 0
- Files with parser anomalies: 6
- Parser anomaly records (aggregate): 1921
- Parser anomaly sessions: 1863

## Monthly parsing summary

| Month | Sessions | Messages | Customer messages | Service messages | Extracted QA | Accepted | Rejected |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 2891 | 32193 | 13253 | 18940 | 11628 | 3722 | 7906 |
| 2 | 2288 | 21588 | 8942 | 12646 | 7629 | 2703 | 4926 |
| 3 | 3548 | 33473 | 13378 | 20095 | 11699 | 4062 | 7637 |
| 4 | 3387 | 31464 | 12748 | 18716 | 10993 | 3833 | 7160 |
| 5 | 3719 | 36352 | 15093 | 21259 | 12870 | 4505 | 8365 |
| 6 | 2064 | 19927 | 8692 | 11235 | 7433 | 2307 | 5126 |

Extracted QA counts customer-turn attempts; every excluded attempt is represented in the rejection totals.
Parser anomaly records are reported separately because they are source-format diagnostics, not extracted QA rows.

## Overall quality summary

- Total sessions: 17897
- Total messages: 174997
- Total extracted QA: 62252
- Accepted candidates: 21132
- Rejected candidates: 41120
- Accepted rate: 33.95%
- Accepted rows per session: min=1, median=1, p95=5, max=28
- Missing field counts: external_store_id=0, external_session_id=0, external_candidate_id=0, source_file_id=0, source_month=0, question_time_start=0, answer_time_end=0, customer_turn_message_count=0, service_turn_message_count=0, final_question=0, final_answer=0, refined_category=0, pii_detected=0, pii_types=0, candidate_status=0, role_inference_used=0, role_inference_method=0, session_has_inferred_role=0, inferred_service_sender_count=0, role_inference_sender_session_count=0, role_inference_threshold_sessions=0, role_inference_coverage_ratio=0, role_inference_first_ratio=0, role_inference_last_ratio=0, session_has_parser_anomaly=0, parser_anomaly_count=0, parser_anomaly_types=0
- Refined category distribution: 价格补偿=655, 其他=5149, 商品咨询=2521, 尺码问题=3138, 换货=895, 物流发货=4773, 质量问题=930, 运费=902, 退货退款=2169
- Rejection reason distribution: empty_answer=16601, empty_question=12834, exact_duplicate=3596, invalid_short_input=6502, missing_service_response=137, normalized_duplicate=1450
- PII detected and safely anonymized before duplicate removal: 2971
- Accepted candidates with PII anonymization metadata: 1629
- PII residual rejected: 0
- Exact duplicate rejected: 3596
- Normalized duplicate rejected: 1450
- Question-and-answer duplicate observations: 381
- Same-session duplicate observations: 94
- Cross-month duplicate observations: 4072
- Original parser session-ID collisions across files: 3548
- External session-ID collisions: 0
- External candidate-ID collisions: 0

## Candidate traceability fields

- `external_candidate_id`: deterministic anonymous ID derived only from approved anonymous IDs and the session-local QA ordinal; it does not use question, answer, sender, or a real store name.
- `role_inference_used`: true only when at least one message retained in this candidate's answer was reclassified by the statistical sender rule.
- `role_inference_method`: `legacy_keyword`, `statistical_sender_rule`, `mixed`, or `unresolved`, describing the retained answer messages.
- `session_has_inferred_role`: whether any message anywhere in the session was reclassified from customer to service by the statistical rule; this is intentionally separate from candidate-level use.
- `inferred_service_sender_count`: number of distinct statistically inferred senders retained in the answer; no sender identifier is emitted.
- `role_inference_sender_session_count`, `role_inference_coverage_ratio`, `role_inference_first_ratio`, `role_inference_last_ratio`: conservative deterministic aggregates over inferred senders used by the answer (minimum, minimum, maximum, minimum respectively).
- `role_inference_threshold_sessions`: unchanged minimum session-coverage threshold used by the existing statistical rule.
- `session_has_parser_anomaly`, `parser_anomaly_count`, `parser_anomaly_types`: session-level association with parser diagnostics. Types are sorted, deduplicated, and pipe-delimited.

## Role inference lineage summary

- Candidates with role_inference_used=true: 12176 (57.62%)
- Method distribution: legacy_keyword=8956, mixed=2, statistical_sender_rule=12174
- Candidates with session_has_inferred_role=true: 12184
- Distinct accepted sessions with an inferred role: 6768
- Unresolved candidates: 0
- Candidates using multiple inferred senders: 2

## Parser anomaly lineage summary

- Candidates associated with a session parser anomaly: 1333
- Candidate-associated anomaly type distribution: invalid_session_end_time=934, missing_message_content=410
- Limitation: these fields record session-level association only; they do not claim that an anomaly caused an error in any candidate QA.

## Privacy and safety

- Candidate output contains only the approved anonymized schema: yes
- Residual PII in accepted candidates: no
- Rejected CSV contains original text: no
- Complete absolute paths in row-level outputs: no
- Raw source filenames in row-level outputs: no
- Raw session IDs in row-level outputs: no
- Sender names or sender hashes in traceability fields: no
- Real store names in traceability fields: no
- Store and service-sender aliases derived during processing are replaced before output.
- Manual review is still required: anonymization is rule-based, ambiguous category labels remain possible, and service answers are reference material rather than verified ground truth.

## External evaluation boundary

external_store_v1 is reserved exclusively for external evaluation.
It was not added to the V1 or V2 retrieval corpus.
No embeddings were generated from this dataset.

## Review gate

- Status: READY FOR 120-SAMPLE REVIEW
