# Formal Evaluation Stage B5 Guarded Real-Execution Plan

**Status:** APPROVED AND FROZEN — planning only.

**Current readiness:** `RQ1_READINESS_STATUS: NOT_READY`. This plan does not change that verdict. Stage B5 implementation, production-resource preflight, Provider access, canary execution, formal generation, reviewer projection, scoring, and statistical analysis remain unauthorized.

## 1. Purpose and boundaries

Stage B5 is the smallest implementation slice that may, after later independent approval and separately authorized commands, connect the existing formal-evaluation runner to DeepSeek while preserving the frozen request plan and the Stage A–B4 safety contracts.

Stage B5 will not create a second runner or evaluation plan. It will add one real-execution authority behind the current runner and reuse the current transport tracker, orchestration, in-flight journal, durable private store, and reviewer-projection lifecycle. Dry-run and the fixed offline fake authority remain byte-for-byte and behaviorally unchanged.

No planning, implementation, compile check, or test may contact DeepSeek or any other network endpoint, read `outputs/.env`, construct a real client, run a production preflight, or access production resources. Real execution remains impossible until every gate in Section 10 has been passed separately.

## 2. Frozen plan remains exact

The only request plan remains the current deterministic 190-unit plan:

| Research question | Execution orders | Unit count |
|---|---:|---:|
| RQ1 | 1–102 | 102 |
| RQ2 | 103–142 | 40 |
| RQ3 | 143–190 | 48 |

The system counts remain `qa_only_reconstructed_baseline = 71`, `v2 = 71`, `single_turn = 24`, and `context_aware = 24`. Request IDs, complete payloads, system identities, execution order, generation parameters, and canonical fingerprint calculation remain unchanged. The required fingerprint is:

`4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5`

Stage B5 must not add `--rq`, filter or reorder cases, alter plan units, attach transport/resource metadata to plan units, or create a second plan. Transport, resource, preflight, and execution-authority metadata belong only in the durable run contract.

## 3. Guarded prefix semantics

Real mode requires a positive `--max-new-successes`; an unbounded real command is invalid. The real prefix executor must hold the existing B2 run-wide lock for the complete invocation, commit each success atomically, and count only newly committed first successes. It must require the durable successes to form the exact contiguous prefix `1..P`; it must never skip a blocked order to spend the success budget on a later unit.

The phase rules are:

1. With `P = 0`, real mode accepts only `--max-new-successes 1`. This is the one-unit canary and may execute only order 1, the first pending unit.
2. With `1 <= P < 102`, the bound must satisfy `P + max_new_successes <= 102`. Immediately after a successful canary, the exact RQ1-completion command therefore uses `--max-new-successes 101` and can commit only orders 2–102.
3. If an RQ1 invocation stops early, a later separately authorized resume uses `--max-new-successes (102 - P)`. It cannot cross order 102.
4. At `P = 102`, the next eligible order must be exactly 103. No completed order may re-enter orchestration or call the Provider. A later authorization may use 40 new successes to stop at 142 and, after another reviewed checkpoint if required, 48 to complete at 190; a single bound up to 88 is permitted only if the later authorization explicitly covers both RQ2 and RQ3.
5. Any gap, uncertain outcome, terminal outcome, exhausted retry, provider-returned-without-commit state, contract mismatch, or persistence failure stops the prefix at that order. Later orders are not attempted.

`--max-new-successes` bounds successful units, not raw attempts. One unit may use up to three attempts only under the existing retry contract. A legitimate local guard or backend-boundary success counts as one success with `provider_called = false`; it does not become Provider success.

The canary and initial RQ1 commands, after their separate authorizations, are:

```powershell
& $VenvPython scripts/run_formal_evaluation.py `
  --mode real `
  --confirm-real-api FORMAL_EVAL_20260721 `
  --expected-b4-preflight-sha256 <reviewed-64-lowercase-hex> `
  --max-new-successes 1

& $VenvPython scripts/run_formal_evaluation.py `
  --mode real `
  --confirm-real-api FORMAL_EVAL_20260721 `
  --expected-b4-preflight-sha256 <same-reviewed-64-lowercase-hex> `
  --max-new-successes 101
```

The second command is valid only when the durable readback proves exactly one committed success at order 1 and next order 2. Placeholder text is never executable authorization.

## 4. Stage B4 evidence binding

The required evidence path is fixed:

`data/formal_eval/resource_preflight/production_resource_preflight_v1.json`

A real invocation must consume, but must not invoke, the Stage B4 preflight. Before credential access or client construction it must:

- require the operator-supplied `--expected-b4-preflight-sha256` and exact equality to the artifact self-hash;
- reuse the existing B4 strict bounded reader and complete schema/self-hash/canonical-byte validation rather than inventing a permissive parser;
- require `stage_id = B4`, `status = passed`, and the exact B4 contract ID;
- require exactly four Stage A-valid `production_frozen` identities in canonical system order, all with `synthetic = false` and exact family/system/count relationships;
- compare every B4 authority-file byte count and SHA-256 to the current checkout, so evidence produced before the Stage B5 runner/orchestration changes is stale;
- bind both the B4 self-hash and the ordinary SHA-256 of the canonical artifact bytes into the real run contract;
- bind each complete resource identity and its identity hash into the same contract;
- bind the Stage B5 execution-module, runner, orchestration, store, runtime, transport, baseline-adapter, and reviewer-projection implementation identities in the real contract, without altering plan units;
- when production loading is later authorized, observe each corpus, embedding matrix, and exact local model snapshot before and after load and require equality with the B4 hashes, sizes, types, and local-only identity.

The evidence is fresh only when a separately authorized B4 invocation on the exact reviewed Stage B5 implementation checkout returns the same explicitly reviewed self-hash and the real command supplies that hash. Artifact existence alone is never authorization. Missing, malformed, noncanonical, stale, mismatched, synthetic, unknown-member, unsafe-path, or resource-drift evidence fails before `.env`, SDK import, client construction, DNS, socket, or durable execution.

The production preflight remains its own offline, Provider-free command and must not be called automatically by real mode.

## 5. Real configuration, resources, and client boundary

All non-secret gates run first, in this order:

1. CLI mode, confirmation token, required bound, phase cap, fixed output policy, branch/commit, clean worktree, and no concurrent executor;
2. frozen SHA, identity, 190-unit plan, counts, continuous order, and fingerprint validation;
3. strict B4 evidence validation and current authority-file matching;
4. construction and create-only/reopen validation of the exact non-synthetic durable run contract;
5. contiguous durable-progress validation and phase-bound validation;
6. read-only production resource/model loading with before/after identity matching and no rebuild, repair, save, or remote fallback.

Only if all six pass may the implementation call:

`parse_deepseek_config("outputs/.env")`

from `scripts/formal_evaluation_transport.py`. The accepted names remain exactly `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, and `DEEPSEEK_MODEL`; base URL and model must match the frozen DeepSeek contract. Credential values must never be printed, logged, included in exceptions, returned, persisted, hashed, compared in public evidence, placed in tests, or included in `repr`.

After configuration validation, and only in an explicitly authorized real invocation with pending work, a lazy factory may import the installed OpenAI-compatible SDK and construct one DeepSeek client. SDK automatic retries must be disabled so only the existing formal retry controller owns attempts. Client transport settings and the installed SDK version are non-secret and are bound into the real run contract. Client construction must be network-free; the first possible network action is the tracked completion call after its `call_started` journal has been durably published.

The production loader is fixed-path and evidence-driven. It loads only the two B4-approved corpus/embedding families and the exact local embedding-model snapshot. It must never call `load_or_create_cache`, a corpus builder, an embedding save path, model-ID remote resolution, or any repair/rebuild routine.

## 6. Non-synthetic execution authority

Stage B5 adds one import-safe real-execution authority module. Its import, evidence-only, and contract-building surfaces use no SDK, optional data/model package, environment file, client, or network. Its protected constructor, reached only after Section 5 gates, supplies the existing store/orchestration dependency seam with:

- a closed `ProductionResourceBundle` containing the four validated B4 identities and rejecting every synthetic identity;
- already-loaded read-only V1 and V2 resources and the exact local embedding model;
- a monotonic UTC clock compatible with the existing journal contract;
- the current runtime snapshot validator for RQ3;
- the frozen baseline adapter for `qa_only_reconstructed_baseline`;
- `run_dialogue_checkpointed()` for V2 single-turn and context-aware execution;
- one SDK completions adapter routed exclusively through `ExecutorContext.invoke_provider()`;
- an exact executor registry for the four existing `system_config_id` values.

The adapter validates the core's requested messages and fixed generation settings, then routes the call through `FixedGenerationProxy` and the request-scoped `ProviderCallTracker`. It exposes only the normalized answer back to the core while retaining the authoritative receipt in orchestration. It must not permit a direct SDK call by a baseline or V2 executor.

The runner continues to distinguish `system_config_id`, `formal_system_id`, and specification path. No path is accepted as an ID and no ID is used to open a file.

## 7. Retry, no-recall, and persistence rules

The existing Stage A/B1 contracts remain authoritative:

- retry only a proven pre-send failure, explicit HTTP 429, explicit HTTP 5xx, or explicit temporary-unavailable outcome, with at most three total attempts;
- classify timeout, read timeout, connection reset, broken pipe, dropped connection, generic connection error, and unknown post-call SDK failure as uncertain;
- never retry an uncertain or terminal outcome;
- persist `call_started` before entering the raw client and persist `provider_returned` before first-success commit;
- reject any core fallback/mock text after a Provider call unless the tracker contains a matching validated Provider receipt;
- keep legitimate local guard/backend-boundary results as `provider_called = false`;
- never place a local persistence failure inside the Provider retry loop;
- retain the first successful response and reject conflicting success evidence.

If the process loses control after entering the Provider but before a durable first-success commit, the unit fails closed. A `call_started`, uncertain, or provider-returned-without-commit state is non-recallable and blocks that execution order. Stage B5 does not claim Provider-level exactly-once execution and supplies no automatic reconciliation from hashes alone.

On ordinary resume, the store validates the exact real run contract, all archives/journals/commits, the contiguous prefix, and RQ3 checkpoint dependency. Orders already committed are observed only; they receive zero executor and Provider calls. At 102 committed units, the next call is therefore order 103.

## 8. Durable and reviewer-output lifecycle

The sole authoritative real row-level state is the existing fixed ignored B2 tree:

`data/formal_eval/private_state`

Its run contract must identify `production_real`, the reviewed B4 hashes, four non-synthetic resource identities, fixed generation/transport contracts, runtime and implementation identities, and exact client transport metadata. It contains no credential value. Creation remains atomic/create-only; reopen requires exact equality. An existing fake, legacy, stale, or different real contract blocks with no migration, overwrite, deletion, or guessed identity.

The legacy `data/formal_eval/dry_run` tree remains marker-only plumbing evidence and is never counted, copied, migrated, or projected as model output.

The existing B3 projection remains the only reviewer-output path:

`data/formal_eval/reviewer_projection`

B3 must accept the exact real-contract schema, continue to reject `offline_fake_only` and every synthetic resource, and require all 190 validated canonical commits before projection. It must not run automatically at the canary, order 102, or any partial prefix. After full completion and a separate authorization, it may create the existing system-anonymised reviewer artifacts and private mapping using its current create-only lifecycle. No formal system identity may enter reviewer-visible material.

Stage B5 stores answers in the current explicit formal-result allowlist so they are suitable for later B3 human-review projection. It does not implement human scoring, adjudication, statistical analysis, or dissertation conclusions.

Terminal output is aggregate and sanitized only: action, new-success count, total-success count, remaining count, and next execution order. It never prints a query, answer, request ID, Provider response object, retrieved row, prompt, path to protected resources, traceback, or credential.

## 9. CLI preconditions and exits

Real mode retains both existing boundaries: `--mode real` and `--confirm-real-api FORMAL_EVAL_20260721`. The only new public argument is the narrowly required `--expected-b4-preflight-sha256`; `--max-new-successes` becomes mandatory in real mode. `--output` remains dry-run-only and any real-mode custom output is rejected. There is no `--rq`, resource override, model override, credential override, repair, force, migration, or skip-validation option.

Controlled exits are:

| Exit | Public result |
|---:|---|
| 0 | One canonical aggregate line with `B5_PREFIX_PAUSED` or `B5_RUN_COMPLETE`. |
| 2 | Empty stdout and one closed category on stderr: `B5_AUTHORIZATION_BLOCKED`, `B5_FROZEN_PLAN_INVALID`, `B5_PREFIX_BOUNDARY_INVALID`, `B5_PREFLIGHT_INVALID`, `B5_DURABLE_STATE_INVALID`, `B5_CONFIGURATION_INVALID`, `B5_RESOURCE_INVALID`, `B5_CLIENT_INVALID`, `B5_PROVIDER_RETRY_EXHAUSTED`, `B5_PROVIDER_UNCERTAIN`, `B5_PROVIDER_TERMINAL`, `B5_PERSISTENCE_INVALID`, or `B5_INTERNAL_FAILURE`. |
| 2 | Standard argument-parser failure before application code for malformed CLI syntax. |
| 130 | Operator interrupt; durable state controls restart and any post-call interruption remains non-recallable. |

Internal `TransportError`, `OrchestrationError`, `JournalError`, `StoreError`, B4, SDK, loader, and core exceptions are mapped by a closed precedence table to these categories without including raw exception text. Unexpected process termination has no fabricated success exit.

## 10. Separate authorization gates

Each gate is independent; passing one does not authorize the next.

1. **Plan review and implementation authority.** The focused independent review approved the candidate: `STAGE_B5_PLAN_REVIEW_PASS`; Verdict: `PASS`; Reviewed candidate SHA-256: `4ee7c7f3383e7b76af5f9a84113dfc2aefbab726580d2f1771ee3ebe73c4fd2a`. Any later implementation is a separate atomic task, followed by offline verification, independent code audit, and user commit/push. None of those later activities is currently authorized.
2. **Production resource preflight.** After the reviewed implementation is published, separately authorize the offline B4 production command. It may access the exact production resources and create/reopen only B4 evidence. It may not read `.env`, construct a client, or contact the Provider.
3. **Pre-canary audit.** Separately authorize a strictly read-only audit of the exact published commit, clean refs/worktree, frozen plan, implementation hashes, B4 evidence/hash, empty-or-exact real store, phase rules, and zero-response state. It must not read `.env`, load production row content, construct a client, or contact the Provider. It must replace the current `NOT_READY` verdict with an evidence-backed ready verdict before any canary authority can exist.
4. **One-unit canary.** Separately authorize the exact real command with the reviewed B4 hash and `--max-new-successes 1`. This is the first authorization that may read `outputs/.env`, construct the client, access the network, and generate the first pending unit.
5. **RQ1 prefix completion.** After read-only review of a successful canary and exact durable progress, separately authorize only the remaining successes through order 102 (initially 101). This authority does not extend to order 103.
6. **RQ2/RQ3 continuation.** After the order-102 checkpoint is reviewed, separately authorize later bounded command(s) beginning at order 103. RQ2 may be bounded at 40 new successes and RQ3 at 48; no continuation is implied by RQ1 authority.
7. **Reviewer projection and downstream research.** Full B3 projection after 190 commits, human scoring, adjudication, and statistical analysis remain later separate authorities. They are not Stage B5 execution authority.

## 11. Minimal implementation path budget

The complete Stage B5 implementation budget is exactly six tracked paths:

| Path | Change |
|---|---|
| `scripts/formal_evaluation_real_execution.py` | New import-safe B4 evidence consumer, non-synthetic resource/client authority, executor adapters, and protected lazy constructor. |
| `scripts/run_formal_evaluation.py` | Preserve fake APIs; add real contract builder, guarded CLI branch, fixed phase caps, and aggregate reporting. |
| `scripts/formal_evaluation_orchestration.py` | Add a closed production resource bundle and allow it through the existing orchestration core; retain the synthetic bundle unchanged. |
| `scripts/formal_evaluation_store.py` | Generalize the existing locked durable unit core to the exact real authority, select the fixed real snapshot validator, and add invocation-wide contiguous-prefix execution using the existing lock. |
| `scripts/formal_evaluation_review_projection.py` | Validate/build the exact real contract and retain complete-run, non-synthetic B3 eligibility. |
| `scripts/test_formal_evaluation_real_execution.py` | New focused Stage B5 zero-network suite; all new Stage B5 tests live here. |

No change is budgeted for transport, in-flight identity, runtime, B4 preflight/worker, baseline adapter/vendor/specification, frozen manifest/fixtures/protocol, generation settings, dependencies, ignore rules, or existing B1–B4 tests. If implementation proves another path is required, stop for explicit scope expansion; do not consume a seventh path.

## 12. Offline verification plan

All Stage B5 tests use injected fake SDK clients, fake completions, synthetic 190-unit marker plans, synthetic non-production resources, and OS-temporary roots. An autouse guard blocks the actual B2/B3/B4/production resource/model/credential roots and monkeypatches `socket.socket`, `socket.create_connection`, and `socket.getaddrinfo` to fail and count. Tests hash/inventory every synthetic input before and after.

The focused suite must cover:

- real-gate ordering, including proof that every non-secret failure precedes config parsing, SDK import, client construction, resource loading where applicable, and network;
- strict credential parsing through `parse_deepseek_config()` using only a temporary synthetic config, redacted `repr`, and sentinel-secret absence from stdout, stderr, exceptions, contracts, journals, commits, and reviewer material;
- missing, malformed, stale, wrong-hash, synthetic, authority-mismatched, resource-mismatched, and valid fresh B4 evidence;
- exact production-real contract identity and unchanged offline-fake contract bytes/behavior;
- one-unit canary pause at order 1 with no call at order 2;
- exact cap at order 102, including interrupted prefix calculation, no order 103 call, and fixed RQ/system counts;
- resume with 102 committed units, zero recall for orders 1–102, and first new call at order 103;
- explicit retryable outcomes through the three-attempt ceiling, pre-send retry, uncertain/terminal no-retry, response-returned persistence failure, first-success ownership, and no recall after any post-call ambiguous state;
- RQ3 Turn 1 checkpoint/Turn 2 resume without replay under the real snapshot validator;
- partial real state rejected by B3, complete non-synthetic real state accepted, and dry-run/fake state rejected;
- byte-for-byte non-mutation of synthetic resources and absence of repository temp, evidence, private-state, reviewer, pycache, or pytest residue;
- help, import, dry-run, and every implementation test performing zero config reads, client construction, Provider calls, DNS, and sockets.

Implementation verification may compile only the six budgeted Python paths and run the new focused suite plus the directly affected existing runner/orchestration/store/reviewer compatibility suites. It must not expand unrelated B1–B4 matrices. Any compatibility suite that reads frozen fixtures requires explicit fixture-read authority and may report only aggregate counts. No implementation-acceptance command may run B4 production preflight, `--mode real`, a canary, or any production path.

## 13. Acceptance and current disposition

A later implementation may pass only if all six-path scope, zero-network tests, phase caps, B4 binding, secret boundary, non-synthetic authority, durable no-recall behavior, B3 eligibility, compile checks, `git diff --check`, and final path inventory pass exactly. Development test passes are offline implementation verification, not formal evaluation results.

This document is APPROVED AND FROZEN as a plan only. It authorizes no implementation or execution. The current repository state still has real transport deliberately blocked by `real_gate()`, durable authority `offline_fake_only`, no production B4 probe for Stage B5, no client, no canary, and zero Stage B5 formal generation.

**NEXT_ATOMIC_TASK:** Publish this approved and frozen plan in an exact one-path local commit containing only `docs/evaluation/formal_evaluation_stage_b5_plan.md`; do not modify other files, begin implementation, run tests or compilation, access protected data, read `.env`, construct a client, access the network, or push.
