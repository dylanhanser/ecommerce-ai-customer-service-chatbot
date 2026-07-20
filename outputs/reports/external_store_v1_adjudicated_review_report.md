# external_store_v1 adjudicated review report

## Frozen inputs and validation

- Primary SHA-256: `cf1c1e9ca76dd76acca50576adfb860ac69a7279ff045eb540e1626c580c2767`
- Secondary SHA-256: `874fcfa587aa9619f72ff2fba5595791fef1ddefa26a59b5954d597b731c360a`
- Adjudication SHA-256: `05db65b63bc4dd8f5835662347f18e173db5a3b1c7b1f867498c6cff8971d38a`
- Adjudication validation: VALID; 16 rows, 35 columns, fixed 16-ID scope, 47 disputed fields resolved. R3 dated 2026-07-20.

## Merge and final outcome

- Merge: primary frozen question/answer; 96 primary-only, 8 dual agreements, 16 adjudicated.
- Decision sources: primary_only included/excluded=42/54; dual_agreement=6/2; adjudicated=3/13.
- Overall: reviewed=120; included=51; excluded=69; inclusion_rate=42.50%; categories={商品咨询: 13, 退货退款: 12, 物流发货: 11, 尺码问题: 6, 其他: 3, 换货: 3, 运费: 2, 价格补偿: 1, 质量问题: 0}; exclude_reasons={'context_dependent': 27, 'missing_or_irrelevant_answer': 14, 'other': 22, 'residual_pii': 6}
- Status changes: R011, R054, R061, R064, R095.
- Gold-51 SHA-256: `773535bf13c1d2a80ebff5410c2f16c96b6f297b2b3f17cd99628165b26fc444`

## Authoritative sample strata

- representative: reviewed=96; included=40; excluded=56; inclusion_rate=41.67%; categories={商品咨询: 10, 退货退款: 9, 物流发货: 7, 尺码问题: 5, 其他: 3, 换货: 3, 运费: 2, 价格补偿: 1, 质量问题: 0}; exclude_reasons={'context_dependent': 21, 'missing_or_irrelevant_answer': 12, 'other': 19, 'residual_pii': 4}
- risk: reviewed=24; included=11; excluded=13; inclusion_rate=45.83%; categories={商品咨询: 3, 退货退款: 3, 物流发货: 4, 尺码问题: 1, 其他: 0, 换货: 0, 运费: 0, 价格补偿: 0, 质量问题: 0}; exclude_reasons={'context_dependent': 6, 'missing_or_irrelevant_answer': 2, 'other': 3, 'residual_pii': 2}
- Overall 42.50% is the frozen 120-sample approval rate, not a natural-quality estimate for the 21,132-candidate pool: risk was purposively oversampled. The representative subset better describes ordinary candidates; risk tests role inference, parsing anomalies, and threshold boundaries.

## Pre-adjudication agreement (retain for paper)

- pair_valid 0.8750, κ 0.5135; question_self_contained 0.6250, κ 0.1429; answer_relevance 0.5417, κ 0.3333 (weighted κ 0.4783); role_pairing_correct 1.0000, κ N/A; answer_usable_as_reference 0.6667, κ 0.3962; residual_pii_found 0.9583, κ 0.0000; gold_category 1.0000, κ 1.0000; exclude_reason 0.3750, κ 0.1910; final inclusion 0.7083, κ 0.4167.
- PII κ=0 reflects class imbalance, not zero agreement. Lower self-contained/relevance agreement indicates subjective difficulty and motivates adjudication. Final labels establish gold labels and do not replace reviewer agreement.

## Reproduction and limits

- Run `PYTHONDONTWRITEBYTECODE=1 python scripts/finalize_external_review_adjudication.py` and the three review test modules.
- This is a held-out real external Gold Set component; boundary items are not yet combined. No model-answer evaluation has been run.
