# Stage B4 V2 Document-ID Deduplication Pre-Execution Amendment Plan

Status: **APPROVED AND FROZEN — IMPLEMENTATION UNAUTHORIZED — OPERATIONAL REPAIR UNAUTHORIZED — B4 PREFLIGHT UNAUTHORIZED**

Review token: `STAGE_B4_V2_DOC_ID_AMENDMENT_REVIEW_PASS`

Verdict: **PASS**

Reviewed candidate SHA-256: `11a7dbb50165ee4d464ca31725ff78693ec2d7052689f27593f14325edad4d16`

## 1. Purpose and boundary

This is one small pre-execution remediation for the confirmed V2 snippet `doc_id` defect. It is not a redesign of Stage B4 or B5 and does not expand the evaluation framework. Formal generation has not begun, and this approved and frozen amendment authorizes neither tracked implementation nor production-cache repair.

Repository baseline: `main` at `663696fe4a819a185866be1fe313cc3ee3acfde1`, with local `main` and `origin/main` equal, ahead/behind `0/0`, a clean worktree/index, and no B4 evidence artifact.

## 2. Confirmed defect and protected identities

The V2 corpus has 15,688 rows but only 15,675 distinct document IDs: 13 duplicate groups and 13 excess occurrences. The 15,333-row QA prefix is unique; the snippet partition has 342 unique IDs among 355 rows; and there are no cross-partition collisions. The earliest B4 failure is the V2 `_frame_contract` document-ID uniqueness check in `scripts/formal_evaluation_resource_preflight_worker.py`, classified as `B4_IDENTITY_MISMATCH`.

| Resource | Required pre-repair identity |
| --- | --- |
| `outputs/cache/v2_mixed/mixed_corpus_v2.pkl` | SHA-256 `e2121cc34bd9bd01a168430976f2c83c3310b9fff4390deb8eb74426f17e90da` |
| `outputs/cache/v2_mixed/mixed_embeddings_v2.npy` | SHA-256 `58f4dd3c05d466a277b23437c2edcbcffe576f179f947b345f220cb21fbe2f93` |
| `data/processed/knowledge_snippets_v2_reviewed.csv` | SHA-256 `d88f449a80a308ed8d648fa13a60a77671dcd273748e4e0bddf30e4c9076b685` |
| `data/processed/jd_final_safe_qa_refined_category.csv` | SHA-256 `730670dc6a47d6f1d7c7b146f546dc061802d672d78922fab82718f394100714` |
| `outputs/cache/v1_qa/qa_corpus.pkl` | 2,923,146 bytes; SHA-256 `ccb1c9484ec2e9b835eb9bb986f77194d7ef6689438be82a923cbc805931e8ed` |
| `outputs/cache/v1_qa/qa_embeddings.npy` | 23,551,616 bytes; SHA-256 `d2683cfd5483359c889aa5ecc93bf78166be83742bec67e2eff3bf65c0c76a1a` |

The two V1 resources are valid and must not be regenerated, overwritten, repaired, or deleted.

## 3. Restricted root-cause confirmation

After separate authorization, root-cause confirmation may inspect only source identifier fields and aggregate duplicate facts. It may compute counts, occurrence positions, partition membership, and collision categories in memory, but must not print identifiers or row-level records. Questions, answers, snippet text, retrieval text, embedding values, and any other protected row content must neither be inspected for root-cause analysis nor printed.

If the aggregates differ from Section 2, if a duplicate occurs in the QA prefix, if a cross-partition collision exists, or if the required old hashes do not match, the repair must fail closed as a scope/provenance mismatch.

## 4. Deterministic correction contract

The implementation must expose one deterministic allocation behavior used by both the snippet builder and the separately authorized repair operation:

1. Traverse the complete corpus in existing row order and treat the QA prefix as immutable.
2. Require every original ID to be a nonempty string. Build a reserved set containing every original complete-corpus ID, an initially empty allocated set, and a stable per-base-ID occurrence counter.
3. Preserve the first occurrence of every ID exactly.
4. For each later occurrence, require that it is a snippet row; increment its stable occurrence counter and form the suffix candidate `<original_id>__dup_<occurrence>`, where the second occurrence starts at `2`.
5. While the candidate is empty or appears in either the reserved-original set or the newly allocated set, increment the suffix integer and try again. Allocate the first available candidate.
6. For the current protected corpus, require exactly 13 replacements, all in the 355-row snippet suffix. Any other replacement count or location fails closed.
7. After allocation, require 15,688 nonempty IDs and 15,688 unique IDs across the complete corpus.

The full original-ID reservation makes allocation independent of encounter timing and prevents a generated ID from colliding with an original ID that appears later. Reapplying the behavior to an already unique corpus changes nothing, so it is idempotent. The tracked V2 snippet builder must use this same behavior so rebuilding from the unchanged sources reproduces the repaired IDs, then enforce a final complete-corpus invariant that fails if any document ID is empty or non-unique.

## 5. Preservation contract

The repair must preserve all 15,688 rows and their order. At the pandas DataFrame semantic level, exact before/after comparison must prove:

- the complete 15,333-row QA prefix is byte-for-value unchanged, including `doc_id`;
- every value outside the `doc_id` column is unchanged for all rows;
- columns, index, dtypes, DataFrame attributes, partition boundaries, and row positions are unchanged;
- retrieval text, categories, priorities, allowed flags, backend flags, and all other non-ID values are unchanged; and
- only the 13 later duplicate snippet `doc_id` cells changed, each according to Section 4.

Exact comparisons must use value- and dtype-sensitive DataFrame assertions, not lossy string conversion. Protected values may be compared in memory but must not be emitted in terminal output, exceptions, tests, or reports.

Both source CSVs must remain byte-for-byte at their Section 2 hashes. `mixed_embeddings_v2.npy` must remain byte-for-byte at its Section 2 hash; embeddings must not be regenerated. Its payload, shape, row count, and position-to-corpus alignment must remain unchanged because no corpus row or embedding row moves. Both V1 files must retain their exact sizes and hashes. The exact local embedding-model revision identifier and model-tree hash observed immediately before repair must equal the observations immediately after repair. Any mismatch aborts or invalidates the operation.

## 6. Atomic operational repair

Operational repair is a separate, explicitly authorized step. It may modify exactly `outputs/cache/v2_mixed/mixed_corpus_v2.pkl` and no other production artifact.

The operation must first verify every precondition and protected identity above. It must write the repaired DataFrame to a uniquely named sibling temporary file on the same filesystem, flush and `fsync` it, reopen it, and complete all semantic, aggregate, schema, source, embedding, V1, and model revision/tree validations before publication. Only then may it atomically replace the corpus path. A post-replacement readback and hash must repeat the full validation. Failure before replacement preserves the old corpus; failure after replacement is reported without attempting a rebuild, embedding generation, or unreviewed rollback.

The repair report must record the old V2 corpus SHA-256 `e2121cc34bd9bd01a168430976f2c83c3310b9fff4390deb8eb74426f17e90da` and the newly computed V2 corpus SHA-256. It must record only aggregate results and safe identities, never row-level IDs or content.

## 7. Exact future change budgets

The future tracked implementation candidate is limited to exactly these two files:

- `outputs/rag_answer_demo.py`
- `scripts/test_formal_evaluation_resource_preflight.py`

The operational repair budget is limited to exactly this one ignored/generated artifact:

- `outputs/cache/v2_mixed/mixed_corpus_v2.pkl`

No B4 worker, B4 schema, manifest, protocol, Stage B5 file, source CSV, V1 resource, or embedding file may change. In particular, `outputs/cache/v2_mixed/mixed_embeddings_v2.npy` must not be written.

## 8. Minimal verification scope

The future test addition is exactly three focused offline tests using synthetic DataFrames, synthetic arrays, and temporary directories only:

1. one deterministic duplicate-ID allocation test;
2. one combined collision-avoidance and idempotence test; and
3. one aggregate cache-repair preservation test covering exact partition counts, QA-prefix equality, non-`doc_id` equality, row order, schema/attributes, unchanged embedding bytes, and alignment.

No test may open production resources, rebuild a cache, load a model by network-capable ID, or expand into a general regression matrix. The separately authorized operational validation must establish these aggregates on the real snapshot without printing protected content:

- 15,688 rows and 15,688 unique nonempty IDs;
- 15,333 QA rows and 355 snippet rows;
- unchanged QA prefix, non-`doc_id` values, row order, schema, and attributes;
- exactly 13 repaired later snippet IDs; and
- unchanged embedding payload, shape, row count, hash, and row alignment.

## 9. Unchanged B4/B5 contracts and lifecycle

The existing B4 priority, schema, resource, offline, failure-category, and evidence contracts remain unchanged. The category remains `B4_IDENTITY_MISMATCH`; the preflight worker is not modified to tolerate duplicates. No request plan, fingerprint, system identity, frozen evaluation fixture, generation parameter, scoring rule, retrieval behavior, or B5 authorization contract changes.

B4 production preflight remains unexecuted until all of the following occur in separate tasks: the completed focused read-only review of the exact candidate; user-controlled amendment commit and push; separately authorized two-file implementation; offline execution of exactly the three tests; independent read-only implementation review; separately authorized atomic operational repair; and independent verification of the aggregate preservation report and old/new corpus hashes. Real mode, canary, Provider/API use, formal response generation, and B4 evidence publication remain unauthorized.

The exact next task is an exact one-path local publication commit of this amendment with subject `docs(eval): approve V2 document ID repair amendment`. That publication task must not implement the change, access production resources, run B4 preflight, or authorize later stages.
