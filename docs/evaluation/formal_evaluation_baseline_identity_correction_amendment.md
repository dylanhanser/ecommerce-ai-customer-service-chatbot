# Formal Evaluation Pre-Execution Baseline Identity-Correction Amendment

## 1. Status and scope

This amendment records a **pre-execution identity metadata correction**. Formal execution has not started: `formal_model_responses = 0`, `real_execution_started = false`, and `execution_not_started = true`. No DeepSeek formal request has been made. No formal model response has been generated. No formal human scoring has been conducted. No formal statistical analysis has been conducted. Real mode has not been executed. No canary has been executed.

It authorises no implementation in this revision. The sole purpose is to transparently record the frozen formal-system identity conflict and the exact, limited correction contract required before Stage A may resume.

## 2. Discovery of the identity conflict

The manifest SHA-256 recorded before this amendment is `38f29a9714168b8b319023fb64c650e01051c7180727ac623e7c4ae8426b6d7c`. Its field `$.formal_system_ids.qa_only_reconstructed_baseline` incorrectly contains `evaluation/formal_qa_only_baseline_spec.json`.

That value is a specification path, not a formal system identifier. This is an actual frozen metadata conflict, rather than a naming ambiguity: the runner currently resolves the manifest mapping directly for future success-row creation and validation, so the path would become the baseline row's `formal_system_id`.

## 3. Conflicting frozen identity sources

The conflicting manifest value is `evaluation/formal_qa_only_baseline_spec.json`. The authoritative frozen sources instead state:

- `evaluation/formal_qa_only_baseline_spec.json`: `system_id = qa_only_reconstructed_baseline`.
- `scripts/formal_qa_only_baseline/adapter.py`: `SYSTEM_ID = qa_only_reconstructed_baseline`.

The baseline specification does not identify itself by its path, and the adapter returns the correct system ID. The manifest's other three mapping values are semantic system IDs, which further confirms that the baseline path is not an intended alias.

## 4. Authoritative baseline identity

The following concepts are distinct and must not be interchanged:

- `system_config_id = qa_only_reconstructed_baseline`: plan classification and executor dispatch.
- `formal_system_id = qa_only_reconstructed_baseline`: success rows, resume validation, and formal provenance.
- `specification_path = evaluation/formal_qa_only_baseline_spec.json`: lookup of the frozen baseline specification and its SHA/provenance.

A specification path must never be represented as an alias formal ID.

## 5. Impact on the existing runner and checkpoint implementation

The impact on commit `09c1037` (`fix(eval): enforce fail-closed RQ3 checkpoint resume identity`) is **partial**.

Unaffected: RQ3 uses only `single_turn` and `context_aware`, whose formal IDs are correct. Its snapshot, Turn 1/Turn 2 checkpoint, resume, first-success, and plan binding remain valid. The runtime snapshot does not contain baseline identity.

Affected: the commit's global success-row creation and validation would use the erroneous path-like manifest value for a future baseline row. A subsequent implementation must correct the manifest and add fail-closed rejection of path-like formal IDs. This finding does not invalidate `09c1037` as a whole.

## 6. Frozen research design preserved

This correction changes only **the frozen formal-system identity metadata and its fail-closed validation before execution**. It is classified as a **pre-execution identity metadata correction**, not a model improvement, research redesign, post-result correction, ablation, or scoring change.

It does not change RQ1/RQ2/RQ3, the Gold Set, evaluation cases, baseline behaviour, V2/V2.1b behaviour, prompts, generation parameters, scoring dimensions, acceptable threshold, blinded review, statistical analysis plan, request contents or order, or the plan fingerprint.

## 7. Plan and fingerprint impact

The frozen plan remains:

| system configuration | units |
| --- | ---: |
| `qa_only_reconstructed_baseline` | 71 |
| `v2` | 71 |
| `single_turn` | 24 |
| `context_aware` | 24 |
| total | 190 |

Its research-question counts are RQ1 102, RQ2 40, and RQ3 48. The frozen fingerprint remains `4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5`.

Each plan unit stores `system_config_id`; it does not store `formal_system_id` or the baseline specification path. Therefore the approved manifest identity correction does not change plan content, request IDs, execution order, blinded templates, or the fingerprint. No new fingerprint and no re-freeze of the 190-unit plan are required.

## 8. Approved correction contract

Subsequent implementation is limited to the following contract:

1. Change only the manifest baseline formal ID from the path to `qa_only_reconstructed_baseline`.
2. Leave the baseline specification and the plan/fingerprint unchanged.
3. Make the runner resolver fail closed for path-like formal IDs, including `/`, `\\`, `.json`, and absolute or relative path patterns.
4. Verify four-way agreement among the manifest formal ID, baseline spec `system_id`, adapter `SYSTEM_ID`, and the subsequent Stage A registry.
5. Put the corrected manifest SHA-256 into freeze/preflight enforcement.
6. Permit a baseline success row to contain only the correct formal ID, and reject a path-like baseline formal ID on resume.
7. Fail closed for unknown, duplicate, missing, or conflicting IDs.

The corrected manifest SHA-256 must be computed only after the approved manifest change and recorded in a subsequent implementation provenance update. This amendment records only the existing old manifest SHA; it neither computes nor invents a future SHA.

## 9. Required implementation and regression tests

The subsequent implementation must test all of the following:

- manifest baseline ID equals `qa_only_reconstructed_baseline`;
- manifest ID equals spec `system_id`;
- manifest/spec/adapter/registry four-way agreement;
- rejection of path-like formal IDs;
- separate storage and verification of the specification path;
- formal IDs are never used to open files;
- baseline success rows contain no specification path;
- resume rejects a forged path-like baseline row;
- all four configuration-to-formal-ID mappings are correct;
- plan units gain neither formal IDs nor specification paths;
- the 190 counts remain unchanged;
- the fingerprint remains the frozen value;
- RQ3 checkpoint identity does not regress;
- corrected manifest SHA enters real preflight; and
- unknown, duplicate, missing, and conflicting IDs fail closed.

## 10. Required governance and implementation sequence before Stage A may resume

This amendment must be independently reviewed, committed, and pushed before any manifest or runner identity correction is implemented.

### Phase 1: Amendment governance

Before implementation, the project must complete:

1. amendment final review;
2. amendment commit;
3. amendment push; and
4. amendment commit hash recorded.

### Phase 2: Identity correction implementation

Only after Phase 1 is complete, the project may complete:

1. modify the manifest baseline formal ID;
2. modify runner fail-closed identity validation;
3. update freeze/preflight enforcement;
4. add identity regression tests;
5. compute the corrected manifest SHA;
6. Sol High implementation review;
7. implementation commit; and
8. implementation push.

Stage A remains blocked until every Phase 1 and Phase 2 requirement is complete. Stage A may resume only after the manifest correction, runner fail-closed identity validation, freeze/preflight enforcement, identity regression tests, corrected manifest SHA, Sol High implementation review, and the separate implementation commit and push are complete.

Until every condition is met, real mode and canary remain disabled and `formal_model_responses` remains 0.

## 11. Dissertation reporting language

Before any formal model response was generated, an inconsistency was identified in the frozen system-identity metadata for the reconstructed QA-only baseline. The formal evaluation manifest placed the baseline specification path in a field intended for formal system identifiers, whereas both the baseline specification and its adapter defined the system identifier as qa_only_reconstructed_baseline. A pre-execution metadata correction is therefore required to separate the system configuration identifier, formal system identifier, and specification path. This planned correction does not alter the evaluation cases, system behaviour, request plan, scoring protocol, or deterministic plan fingerprint.

The correction must be implemented and independently verified before real execution. Once implemented, the correction will be recorded as a pre-execution identity-metadata correction completed before any formal model response generation. The original manifest value, corrected value, old and new manifest hashes, implementation changes, and regression results must then be retained in the project provenance record.

## 12. Sign-off checklist

- [x] The old manifest SHA, field, and erroneous path value are recorded.
- [x] The authoritative spec and adapter IDs are recorded.
- [x] The scope is limited to pre-execution identity metadata and future fail-closed validation.
- [x] The plan counts and frozen fingerprint are recorded as unchanged.
- [x] Real mode and canary remain disabled; no formal model response has been generated.
- [ ] Complete amendment final review, amendment commit, amendment push, and record the amendment commit hash before implementation.
- [ ] Complete the separate identity correction implementation, Sol High implementation review, implementation commit, and implementation push before Stage A resumes.
