# Formal Evaluation Pre-Execution Implementation-Correction Amendment

## 1. Status and scope

This is a **pre-execution implementation correction**. When the defect was identified, `formal_model_responses = 0`. No formal model response, real-mode request, canary request, or 190-unit formal generation had been performed.

The correction is limited to the reliability and fail-closed resumability of the pre-execution formal evaluation runtime. It does not report, correct, or imply an evaluation result.

## 2. Discovery of the execution defect

The RQ3 context-aware two-turn runner originally constructed a new `ConversationState` in the formal runtime and had no supported state-restoration input. On a resume at Turn 2, it would lose both the structured state and bounded previous-turn texts. Supplying Turn 1 and Turn 2 again would replay a successfully completed Turn 1. Bypassing the formal runtime or copying the V2 state machine was not permitted. A minimal, versioned, fail-closed restoration contract was therefore required before any formal execution.

## 3. Why replaying Turn 1 was not acceptable

Replaying Turn 1 would issue a further model request and could produce a different answer. That answer could change the context supplied to Turn 2, violate the first-success lock, and compromise formal-evaluation reproducibility and execution consistency in the paired comparison.

## 4. Approved implementation correction

Commit `09c1037` (`fix(eval): enforce fail-closed RQ3 checkpoint resume identity`) implements the following, without enabling real transport:

- a versioned runtime snapshot using a nested frozen dataclass / deeply immutable scalar representation;
- a complete 14-field `ConversationState` snapshot, including bounded previous user and assistant text;
- strict schema validation that fails closed for unknown or missing fields and type mismatches, rejects `bool` as `int`, requires finite confidence values, and requires non-negative counters;
- UTF-8 byte limits, canonical JSON hashing, and a Turn 1 first-success checkpoint;
- Turn 2 restoration without replaying Turn 1, complete checkpoint identity validation, and binding to the fingerprint of the actual plan content;
- fail-closed duplicate request-ID handling, retry-input isolation, `--max-new-successes`, and single-turn isolation.

The final snapshot contract limits each text field to 16,384 UTF-8 bytes and the complete runtime snapshot to 65,536 canonical UTF-8 JSON bytes. These are byte limits rather than Unicode-character limits. Multibyte Chinese coverage includes rejection of `"中" * 5462` (16,386 bytes), acceptance at 16,384 bytes, and rejection at 16,385 bytes.

For RQ3, `system_config_id = context_aware` identifies the execution configuration, whereas `formal_system_id = v21b_context_aware` identifies the frozen formal system. They are intentionally distinct.

## 5. Frozen research design preserved

This correction did not change RQ1, RQ2, or RQ3; the external held-out Gold Set; evaluation cases; scoring dimensions; acceptable threshold; statistical analysis plan; blinded-review design; baseline definition; V2 definition; V2.1b definition; generation parameters; formal request contents; request ordering; plan fingerprint; or system IDs.

It also did not modify the research questions, evaluation cases, Gold Set, baseline specification, baseline adapter, baseline vendor, V2/V2.1b core, scoring rules, blinded-review schemas, formal request plan, manifest, or protocol.

## 6. Verification and tests

The correction was verified offline with the existing `.venv`, Python 3.11.9, and pytest 9.1.1. The recorded final results are:

- `scripts/test_formal_evaluation_runtime.py`: 11 passed, 11 subtests passed.
- `scripts/test_run_formal_evaluation.py`: 19 passed.
- `scripts/test_formal_evaluation_freeze.py`: 7 passed.
- `scripts/test_formal_qa_only_baseline_adapter.py`: 18 passed.

`py_compile` and `git diff --check` passed. The implementation-test verification used no `.env`, API, formal model, cache, corpus, or formal data. A separate strict read-only Sol audit deselected `test_ignore_rule` because that test creates a temporary file under repository `data/`; that audit result is not the implementation-verification result. Terra's full runner suite is the recorded 19 passed result.

The formal runtime snapshot and restore contract was shown to be semantically equivalent under a deterministic synthetic state-transition module covering backend, financial, after-sales, and reset/new-topic scenarios. This is not a claim that production V2.1b has passed end-to-end formal model validation.

## 7. File, commit and SHA provenance

The only files changed by commit `09c1037` are:

- `scripts/formal_evaluation_runtime.py` — `4441c6782acbd3a733bba98970bd8636d010bbd0c0dc98d32596d70c59a445a3`
- `scripts/run_formal_evaluation.py` — `0230ca86a2776745c897ad71e923ee80568756654b8f2cd15a67f4cdffe8e92b`
- `scripts/test_formal_evaluation_runtime.py` — `058224634d3ec98517d7884d137f69bcf3c4ef5f54ee7b3c36b4865f5559349d`
- `scripts/test_run_formal_evaluation.py` — `b0ba8c03a3e6a2918eabacacb6ffe4152297c61db77fe5027139648eddd9e5ab`

The protected-file SHA-256 values verified during the preceding audit are:

- Gold-51 — `773535bf13c1d2a80ebff5410c2f16c96b6f297b2b3f17cd99628165b26fc444`
- baseline spec — `ea776d7cd43e76cad9f42874a0d9da0fb9b0abd4007d752ea7cc1794bd5ed399`
- RQ1 schema — `a2854a92a5dff3c59215cfef5cc49416a4d64e5c89b0a915d95a43791f4bba9b`
- RQ2 cases — `4a5680a7cd21ba434c958b3c3cdd9407a84b77d7f3741b10476fa86fa9851417`
- RQ3 cases — `c534867d93edbed724efd8064c85555b3fbeab89f4bdc58dbebb45a904018b95`
- formal protocol — `361ff39e405846757d454c4d9f49838049b5a7996d929a580310d092316f3f1f`
- formal manifest — `38f29a9714168b8b319023fb64c650e01051c7180727ac623e7c4ae8426b6d7c`
- V2/V2.1b core — `b5d288be643228505b2b76c07ee595b0b80e3526f32f37303edd06fa2f3ba110`
- baseline adapter — `1c08e7891d0f0eaebbef2beaa0416aafa0f2c053efc2291ed30f75dbd8a92c48`
- baseline vendor — `2a1585575162de62de30df3fca809048f5a81878b491050e57565e548936fcdc`

This revision did not repeat any cache, corpus, embedding, or broad `outputs/`-directory hash scan.

## 8. Plan fingerprint provenance

The frozen plan contains 190 units: `qa_only_reconstructed_baseline` 71, `v2` 71, `single_turn` 24, and `context_aware` 24; by research question, RQ1 102, RQ2 40, and RQ3 48. Its fingerprint is `4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5`.

The current calculation preserves complete plan order, serializes every complete request unit as canonical JSON with `ensure_ascii=False`, `sort_keys=True`, and `separators=(",", ":")`, writes one unit per line with CRLF line endings including a final CRLF, then applies SHA-256 to the complete UTF-8 JSONL bytes.

Its historical provenance is **plausible but incompletely documented**: the method agrees with the contemporaneous freeze report, historical `write_jsonl()` behaviour, and Windows newline behaviour, but no original committed `request_plan.jsonl` bytes or historical hash command is available. It must not be represented as fully verified historical provenance.

## 9. Procedural note on the provenance audit

During preparation of this amendment, an overly broad SHA-verification command read the raw bytes of two existing cache artefacts: `outputs/cache/v2_mixed/mixed_corpus_v2.pkl` and `outputs/cache/v2_mixed/mixed_embeddings_v2.npy`. The files were not deserialised, executed, modified, or used for model inference, retrieval, corpus inspection, or formal response generation. No environment file, API key, model endpoint, or formal evaluation output was accessed. This was a procedural boundary violation in the documentation audit, not contamination of the research design or formal results.

Classification:

- research-design contamination: no;
- formal-output contamination: no;
- repository modification outside the two documentation files: no;
- cache modification: no;
- cache deserialisation or execution: no;
- procedural boundary violation during documentation audit: yes.

No cache artefact was deserialised, executed, modified, or used in the formal evaluation pipeline. The two cache files were inadvertently byte-read during the overly broad SHA scan while preparing this amendment. `formal_model_responses = 0` remains unchanged.

The incident did not alter RQ1, RQ2, or RQ3; the Gold Set; evaluation cases; scoring rules; system definitions; generation parameters; formal request plan; plan ordering; plan fingerprint; model outputs; or the statistical analysis plan.

## 10. Remaining provider in-flight risk

The provider may have successfully generated a response, but the process could crash before the local checkpoint is atomically committed with `os.replace`.

The local first-success record would then be absent, and a restart could resend Turn 1. The implementation therefore cannot claim provider-level exactly-once execution. Classification: blocks checkpoint commit: no; blocks real transport: yes; blocks canary: yes; documentation requirement: yes. This risk is not resolved by this amendment.

## 11. Conditions before real execution

Real transport remains disabled and canary remains disabled. A new, independent authorization and a fresh preflight are required before any formal execution. That preflight must review this amendment, verify its implementation SHA-256 values against the checked-out commit, verify protected hashes and a clean worktree, and explicitly govern or address the provider in-flight boundary. No manifest change is authorized or made by this amendment.

## 12. Dissertation reporting language

Before any formal model response was generated, a limitation was identified in the checkpoint and resume implementation for context-aware two-turn evaluation cases. The original runtime could not restore the structured conversation state and bounded previous-turn context required for Turn 2 without replaying Turn 1. A narrowly scoped implementation correction was therefore introduced to support versioned, fail-closed restoration of the frozen Turn 1 state. The correction did not alter the research questions, evaluation samples, scoring rules, system definitions, generation parameters, or deterministic request plan.

The implementation does not provide provider-level exactly-once execution. A process failure after a provider response but before local checkpoint commitment may leave the request outcome uncertain. Consequently, real transport and canary execution remained disabled until this in-flight failure boundary could be addressed or explicitly governed.

## 13. Sign-off checklist

- [x] Amendment records a pre-execution correction only.
- [x] Commit scope and implementation SHA-256 values are recorded.
- [x] Frozen research-design inputs and protected SHA-256 values are recorded as unchanged.
- [x] No manifest modification is made.
- [x] Real transport and canary remain disabled.
- [ ] Independent authorization and preflight for real execution.
