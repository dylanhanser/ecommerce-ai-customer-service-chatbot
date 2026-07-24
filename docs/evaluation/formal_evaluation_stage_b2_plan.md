# Stage B2 — Durable Private State and Process-Safe Recovery

Status: **Frozen plan  not implemented; independent review pending.**

## Frozen Stage B2 implementation contract

## 1. Verdict

INDEPENDENT_REVIEW_PENDING

Repository baseline: PASS. The six-file candidate allowlist is sufficient; no implementation scope expansion is
needed. This plan remains documentation-only and is not approved until a new independent review accepts it.

## 2. Full HEAD and origin/main

* Branch: main
* HEAD: cef9955b83c513d1b2ec3922ad4e78a3bcbd2ec9
* Local origin/main: cef9955b83c513d1b2ec3922ad4e78a3bcbd2ec9
* Ahead/behind: 0/0
* No fetch was performed.

## 3. Complete Git and index state

The documentation-revision initial and final states are:

* git status --short --untracked-files=all:
  ?? docs/evaluation/formal_evaluation_stage_b2_plan.md
* Index: empty
* git diff --check: exit 0, no output
* git diff --cached --check: exit 0, no output
* Repository .venv: Python 3.11.9
* No tracked file was modified. The proposed plan is the sole untracked file and was revised in place.
* Nothing was staged, committed, pushed, fetched, pulled, reset, restored, checked out, cleaned, or stashed.

## 4. Verified Stage A and Stage B1 hashes

At this planning baseline, committed blobs and worktree bytes matched each other. The Stage A transport row is the
Section 9 LF-canonical semantic source hash; because the current transport source is LF-only, its canonical bytes are
also its current worktree bytes. The remaining rows record the verified current-file SHA-256 values.

Stage    File                                               SHA-256
━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B1       scripts/run_formal_evaluation.py                   6aebfa9d1f4d23a6d86599cc6d2c3df8ce86077320e266a74016391450f924d9
───────  ─────────────────────────────────────────────────  ──────────────────────────────────────────────────────────
B1       scripts/test_run_formal_evaluation.py              a0ad048b93a4b3b8f455480fa4bbfc67188d6f24569e4ac4b2e0f2353d2c7141
───────  ─────────────────────────────────────────────────  ──────────────────────────────────────────────────────────
B1       scripts/formal_evaluation_orchestration.py         755944cf2d5623daef849c67c70432c957199d6f1eaab69b5da87926b2c7f889
───────  ─────────────────────────────────────────────────  ──────────────────────────────────────────────────────────
B1       scripts/test_formal_evaluation_orchestration.py    0c20e0ecc8c97144a565ea34169c2bd7e7e1a0ccbf38ae94d439fed08fdd2878
───────  ─────────────────────────────────────────────────  ──────────────────────────────────────────────────────────
A        scripts/formal_evaluation_transport.py             464890905866d517bb036569458e6dd69578a2dbacd0eab272c4f0f6ec6fb927
───────  ─────────────────────────────────────────────────  ──────────────────────────────────────────────────────────
A        scripts/test_formal_evaluation_transport.py        565e1a3c923dde0db1fb05faccadeb9c46a3b6db21f8329d72422e9714c0e0ca
───────  ─────────────────────────────────────────────────  ──────────────────────────────────────────────────────────
A        scripts/formal_evaluation_inflight.py              2126f9ecc1d5f0fe71807482b34c31237eb0baecdaf405150ec75b187fa19251
───────  ─────────────────────────────────────────────────  ──────────────────────────────────────────────────────────
A        scripts/test_formal_evaluation_inflight.py         1c082f76c4d133397f4519b4cd29c8c5b138abb5eb62a3d269d0d02efd370a02

## 5. Current B1 call graph and durable-state gap

Current public call graph:

formal_evaluation_orchestration.orchestrate_validated_unit()
-> run_formal_evaluation.orchestrate_offline_unit()
-> verify_frozen()
-> validate_plan()
-> exact selected-unit membership
-> exact RQ3 pair resolution
-> formal_evaluation_orchestration._orchestrate_plan_member()
-> Stage A recovery_decision()
-> create_initial_journal() / next_retry_journal()
-> injected executor
-> FixedGenerationProxy.invoke()
-> _RawClientBoundary.create()
-> injected fake client
-> Stage A success/failure evidence
-> project_formal_result()
-> optional CheckpointEvidence
-> OrchestrationOutcome

Relevant current locations:

* Runner authority and first public B1 interface: scripts/run_formal_evaluation.py:214
* Second public interface: scripts/formal_evaluation_orchestration.py:858
* Private B1 core: scripts/formal_evaluation_orchestration.py:870
* Immediate in-memory call_started transition and fake call: scripts/formal_evaluation_orchestration.py:394
* Stage A recovery decision: scripts/formal_evaluation_inflight.py:973
* Stage A reconciliation: scripts/formal_evaluation_inflight.py:938
* Closed projection: scripts/formal_evaluation_transport.py:1028
* B1 checkpoint construction/validation: scripts/formal_evaluation_orchestration.py:470 and :552

OrchestrationOutcome families are:

* success
* local_success
* retry_available
* fail_closed
* authoritative_success
* reconcile_committed
* confirmed

Pre-call validation failures raise sanitized exceptions instead of returning an outcome.

The durable gap is exact:

* B1 journals, results, success evidence, and checkpoints exist only in memory.

* _RawClientBoundary currently transitions to call_started and immediately calls the fake client.

* A persisted retry attempt in prepared state cannot restart at attempt 2 or 3 because B1 requires its predecessor but
  has no predecessor input for that path (scripts/formal_evaluation_orchestration.py:1046).

* Provider success returns a provider_returned journal plus AuthoritativeSuccess; it does not publish a private result
  or durable committed journal.

* Local success has no Stage A AuthoritativeSuccess, correctly leaving Provider evidence null.

Legacy runner persistence at scripts/run_formal_evaluation.py:237-458 writes JSONL responses, checkpoints, manifests,
events, and reviewer templates. It must not become Stage B2 authority.

## 6. Exact Stage B2 title and objective

Stage B2 — durable private state and process-safe recovery

Objective:

> Make execution state, canonical private projected results, authoritative-success evidence, attempt history, and RQ3
> checkpoints crash-safe, restart-safe, and process-safe.

The canonical private projected result and any required context-aware RQ3 Turn 1 checkpoint must be published in the
same immutable private commit. Stage B3 will project blinded reviewer artifacts from those commits; it will not
redefine success.

## 7. Exact implementation allowlist

Confirmed without expansion:

* New scripts/formal_evaluation_store.py
* New scripts/test_formal_evaluation_store.py
* Modify scripts/run_formal_evaluation.py
* Modify scripts/test_run_formal_evaluation.py
* Modify scripts/formal_evaluation_orchestration.py
* Modify scripts/test_formal_evaluation_orchestration.py

Within existing test files, retain all existing tests and add tests; do not delete or weaken existing assertions.

## 8. Files and behavior that must remain unchanged

Byte-unchanged:

* scripts/formal_evaluation_transport.py
* scripts/test_formal_evaluation_transport.py
* scripts/formal_evaluation_inflight.py
* scripts/test_formal_evaluation_inflight.py
* scripts/formal_evaluation_runtime.py
* scripts/test_formal_evaluation_runtime.py
* All evaluation/ frozen files
* Gold, RQ1, RQ2, and RQ3 fixtures
* scripts/formal_qa_only_baseline/**
* outputs/rag_answer_demo.py
* Production caches, embeddings, corpora, and models
* Formal protocol, manifest, scoring schemas, reviewer templates, and statistical plan

Inside the authorized runner file, preserve the legacy dry-run, template-generation, real gate, and CLI behavior.
Stage B2 adds a separate fake-only durable API; it does not make --mode real reachable.

PART_2_COMPLETE

## 9. Durable run-contract schema

RunContractV1 is a recursively closed JSON object. Its top-level key set has exactly nine members:

schema_version
stage_id
plan_authority
frozen_input_sha256
formal_system_authority
provider_generation_authority
runtime_resource_authority
schema_authority
run_contract_sha256

The construction order above is normative for the Python builder. JSON mapping order is not semantic authority;
durable bytes use the sorted-key canonical serialization defined below. No top-level or nested field is nullable.
Unknown, missing, renamed, duplicated, or additional keys fail closed.

schema_version is an integer, not a boolean, and is exactly 1.

stage_id is a string and is exactly "B2". This literal is new Stage B2-owned authority; no Stage A or B1 API defines a
Stage B2 stage identifier.

plan_authority is an object with exactly eight keys:

plan_fingerprint: lowercase SHA-256 string, exactly
"4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"
base_seed: integer, not boolean, exactly 20260721
execution_unit_count: integer, not boolean, exactly 190
unique_request_id_count: integer, not boolean, exactly 190
execution_order_first: integer, not boolean, exactly 1
execution_order_last: integer, not boolean, exactly 190
rq_counts: object
system_counts: object

rq_counts has exactly three keys and this exact value:

{"RQ1":102,"RQ2":40,"RQ3":48}

system_counts has exactly four keys and this exact value:

{
  "context_aware":24,
  "qa_only_reconstructed_baseline":71,
  "single_turn":24,
  "v2":71
}

Every count is an integer, not a boolean. The builder calls validate_plan(), requires plan_fingerprint(plan) to equal
the literal above, independently recomputes all counts, request-ID uniqueness, and the continuous 1..190 execution
order, and rejects any mismatch.

frozen_input_sha256 is an unordered JSON object, not an array. It has exactly these six case-sensitive repository-
relative keys and values:

{
  "data/external_eval/review/final/external_store_v1_gold_51.csv":"773535bf13c1d2a80ebff5410c2f16c96b6f297b2b3f17cd99628165b26fc444",
  "evaluation/formal_evaluation_manifest.json":"1c1c803d50a25a611c0317923cb2d60b668d0d9973b232fa89ab135ce4d3dc18",
  "evaluation/formal_qa_only_baseline_spec.json":"ea776d7cd43e76cad9f42874a0d9da0fb9b0abd4007d752ea7cc1794bd5ed399",
  "evaluation/formal_rq1_scoring_schema.json":"a2854a92a5dff3c59215cfef5cc49416a4d64e5c89b0a915d95a43791f4bba9b",
  "evaluation/formal_rq2_boundary_cases.json":"4a5680a7cd21ba434c958b3c3cdd9407a84b77d7f3741b10476fa86fa9851417",
  "evaluation/formal_rq3_multiturn_cases.json":"c534867d93edbed724efd8064c85555b3fbeab89f4bdc58dbebb45a904018b95"
}

The contract builder calls the existing runner verify_frozen(), freshly hashes all six current files, requires exact
equality with the six runner FROZEN values above, and stores the freshly calculated mapping. It never trusts contract
bytes, a caller mapping, or caller-supplied hashes.

Every frozen-input key must:

- be a nonempty string of at most 240 UTF-8 bytes;
- use / exclusively;
- be relative to the repository root;
- contain no \, :, %, URI scheme, leading or trailing /, doubled /, empty component, . component, or .. component;
- contain only components matching [A-Za-z0-9][A-Za-z0-9._-]{0,127};
- reconstruct exactly by joining its components with /;
- equal one of the six case-sensitive runner FROZEN keys.

Absolute paths, root-relative paths, drive-absolute paths, drive-relative paths, UNC/device paths, URI-like paths,
traversal, mixed separators, alternate casing, percent encoding, and otherwise noncanonical spellings fail closed.

formal_system_authority is an unordered JSON object with exactly four keys. Every value is an object with exactly six
keys:

formal_system_id: nonempty Stage A safe-ID string
resolved_runtime_system_id: nonempty Stage A safe-ID string
resource_family: nonempty Stage A safe-ID string
top_k: integer, not boolean
uses_context: boolean
uses_checkpoint: boolean

Its exact value is:

{
  "context_aware":{
    "formal_system_id":"v21b_context_aware",
    "resolved_runtime_system_id":"v21b_context_aware",
    "resource_family":"v2_mixed",
    "top_k":10,
    "uses_context":true,
    "uses_checkpoint":true
  },
  "qa_only_reconstructed_baseline":{
    "formal_system_id":"qa_only_reconstructed_baseline",
    "resolved_runtime_system_id":"qa_only_reconstructed_baseline",
    "resource_family":"v1_qa",
    "top_k":5,
    "uses_context":false,
    "uses_checkpoint":false
  },
  "single_turn":{
    "formal_system_id":"v2_without_context_management",
    "resolved_runtime_system_id":"v2_without_context_management",
    "resource_family":"v2_mixed",
    "top_k":10,
    "uses_context":false,
    "uses_checkpoint":false
  },
  "v2":{
    "formal_system_id":"current_v2",
    "resolved_runtime_system_id":"current_v2",
    "resource_family":"v2_mixed",
    "top_k":10,
    "uses_context":false,
    "uses_checkpoint":false
  }
}

The builder freshly calls public Stage A validate_registry() and formal_identity() for each fixed configuration and
requires exact equality with this value. Stored values, compatibility-registry rebinding, runner-manifest aliases, and
caller-supplied identities are not authority.

provider_generation_authority is an object with exactly three keys:

generation
transport
offline_execution

generation is an object with exactly four keys and this exact value:

{
  "contract_id":"deepseek_fixed_generation_v1",
  "contract_sha256":"864a2c75b13be02f1a4a017bb61f29df7a65eb7f9dfcada51e9e52af5ec3e9e2",
  "runner_generation_sha256":"71158e109dd4997dfd18b94ad73d25cc1b7142398225ad2405b690a24bf53406",
  "snapshot":{
    "max_tokens":512,
    "model":"deepseek-chat",
    "stream":false,
    "temperature":0.0,
    "top_p":1.0
  }
}

snapshot has exactly five keys. max_tokens is an integer, not a boolean, and is exactly 512. temperature and top_p are
finite JSON numbers, not booleans, and compare exactly to 0.0 and 1.0. model is exactly "deepseek-chat"; stream is
exactly false. contract_id(), contract_sha256(), and fixed_generation_snapshot() are obtained only from the existing
public Stage A generation_contract_id(), generation_contract_sha256(), and fixed_generation_snapshot() functions.
runner_generation_sha256 is obtained only from existing runner generation_sha(). Each returned value must equal the
literal above.

transport is an object with exactly three keys and this exact value:

{
  "contract_id":"formal_transport_v1",
  "contract_sha256":"5fdcbab6a6058f7747a9b059876e3b0b413500b226123fcbcb3067343c8c1057",
  "snapshot":{
    "base_url":"https://api.deepseek.com",
    "contract_id":"formal_transport_v1",
    "maximum_attempts":3,
    "provider":"DeepSeek",
    "provider_api":"openai_compatible_chat_completions",
    "schema_version":1,
    "success_receipt_schema":1
  }
}

snapshot has exactly seven keys. maximum_attempts, schema_version, and success_receipt_schema are integers, not
booleans, with exact values 3, 1, and 1. All other values are nonempty strings with the exact literals shown.
contract_id, contract_sha256, and snapshot are obtained only from the existing public Stage A
transport_contract_id(), transport_contract_sha256(), and transport_contract_snapshot() functions and must equal the
literals above.

offline_execution is an object with exactly seven non-null string keys and this exact value:

{
  "authority_bundle_id":"run_formal_evaluation._FixedOfflineAuthorityV1",
  "clock_id":"run_formal_evaluation._FixedSyntheticClockV1",
  "executor_registry_id":"run_formal_evaluation._FixedOfflineExecutorRegistryV1",
  "fake_raw_client_id":"run_formal_evaluation._FixedFakeRawClientV1",
  "mode":"offline_fake_only",
  "snapshot_validator_id":"run_formal_evaluation._validate_fixed_synthetic_snapshot_v1",
  "test_fault_controller_id":"formal_evaluation_store._StageB2TestFaultControllerV1"
}

These seven literals are new Stage B2-owned identifiers because Stage A and B1 intentionally accept injected fake
dependencies and define no fixed runner-owned offline dependency identities. They identify exact module-private
runner/store objects required by Section 24; they are not public dependency-injection parameters. The public builder
requires exact Python object identity for the six bundle/callable/type/controller objects and exact mode equality. A caller
cannot supply any of these values.

### Synthetic snapshot schema version 1

This subsection is the exclusive complete definition of synthetic snapshot schema version 1. It does not alter the
production `ConversationState` or `RuntimeConversationSnapshotV1` schemas. It reuses the tracked field authority in
`outputs/rag_answer_demo.py::ConversationState` and the tracked scalar type, UTF-8 size, finite-number, and outer
snapshot rules in `scripts/formal_evaluation_runtime.py`, then deliberately narrows them to one fixed Stage B2-owned
synthetic projection. No caller may select any snapshot field.

The outer value is an exact built-in `dict` with exactly five keys in this Python construction order:

1. `schema_version`
2. `completed_turn_index`
3. `conversation_state`
4. `previous_user_text`
5. `previous_assistant_text`

Its fields are:

- `schema_version`: exact built-in `int`, never `bool`, non-null, fixed literal `1`.
- `completed_turn_index`: exact built-in `int`, never `bool`, non-null, fixed literal `1`.
- `conversation_state`: exact built-in `dict`, non-null, with exactly the 14 keys below.
- `previous_user_text`: exact built-in `str`, non-null, 1..16,384 UTF-8 bytes, exactly the validated Turn 1
  `unit["payload"]["user_input"]`.
- `previous_assistant_text`: exact built-in `str`, non-null, 1..16,384 UTF-8 bytes, exactly the fixed synthetic response
  produced for that Turn 1: either `"STAGE_B2_SYNTHETIC_LOCAL "` or `"STAGE_B2_SYNTHETIC_PROVIDER "` followed by the
  first 24 characters of the exact Turn 1 `request_id`, as selected only by the fixed executor rule in Section 24.

`conversation_state` has exactly these 14 keys in the tracked `ConversationState` dataclass field order:

1. `current_topic`
2. `query_type`
3. `risk_type`
4. `requires_backend_api`
5. `last_safe_answer_type`
6. `last_user_query`
7. `last_assistant_answer`
8. `last_retrieval_query`
9. `last_contextual_query`
10. `last_successful_contextual_query`
11. `state_confidence`
12. `state_turn_count`
13. `updated_at_turn`
14. `should_reset`

The nested fields are exactly:

- `current_topic`: exact `str`, non-null, fixed literal `"none"`.
- `query_type`: exact `str`, non-null, fixed literal `"normal"`.
- `risk_type`: exact `str`, non-null, fixed literal `"none"`.
- `requires_backend_api`: exact `bool`, non-null, fixed literal `false`; integers `0` and `1` are rejected.
- `last_safe_answer_type`: exact `str`, non-null, fixed literal `"none"`.
- `last_user_query`: exact `str`, non-null, 1..16,384 UTF-8 bytes, exactly the validated Turn 1
  `unit["payload"]["user_input"]`; it equals outer `previous_user_text`.
- `last_assistant_answer`: exact `str`, non-null, 1..16,384 UTF-8 bytes, exactly the fixed synthetic Turn 1 response
  defined above; it equals outer `previous_assistant_text`.
- `last_retrieval_query`: exact `str`, non-null, fixed empty literal `""`.
- `last_contextual_query`: exact `str`, non-null, fixed empty literal `""`.
- `last_successful_contextual_query`: exact `str`, non-null, fixed empty literal `""`.
- `state_confidence`: exact built-in `float`, never `bool` or `int`, finite, in the tracked inclusive range `0.0..1.0`,
  fixed exactly to positive `0.0`, and required to satisfy `math.copysign(1.0, value) == 1.0`; negative zero is
  rejected and the one canonical JSON number token is `0.0`.
- `state_turn_count`: exact built-in `int`, never `bool`, non-null, tracked lower bound 0, fixed exactly to `0`.
- `updated_at_turn`: exact built-in `int`, never `bool`, non-null, tracked lower bound 0, fixed exactly to `1`.
- `should_reset`: exact `bool`, non-null, fixed literal `false`; integers `0` and `1` are rejected.

Every fixed string is within the tracked 16,384-byte per-text bound. The complete canonical snapshot must be at most
65,536 UTF-8 bytes, matching the tracked snapshot authority. The two derived strings must already satisfy their bounds;
the builder does not truncate, normalize, replace, or otherwise rewrite them. Missing, renamed, duplicated, or
additional keys are rejected at both mapping levels. Nested mapping subclasses, `MappingProxyType`, dataclass
instances, lists, or any mapping substitution in place of either exact built-in `dict` are rejected. Every field is
non-null. Booleans are accepted only when `type(value) is bool`; every integer field is accepted only when
`type(value) is int`, which excludes booleans.

`_validate_fixed_synthetic_snapshot_v1(value)` accepts exactly one positional `value`, requires the exact mapping and
values above, reconstructs a fresh exact built-in `dict` in the stated construction order, and returns a deep-detached
copy equal to that reconstruction. It performs no coercion and accepts no alternate literal, normalization, default,
migration, or caller-selected response. Any failure raises sanitized B1 `OrchestrationError` with the exact category
`CHECKPOINT_SNAPSHOT_INVALID`. The existing B1 `_validate_snapshot()` retains the same category when it invokes this
validator. When malformed loaded evidence is classified by Stage B2, an invalid snapshot inside its own Turn 1 commit
is `STORE_COMMIT_INVALID`; when encountered as the required Turn 2 dependency it is
`STORE_DEPENDENCY_INVALID`. No raw nested exception text is copied.

Canonical snapshot bytes are:

`json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")`

with recursive Unicode key ordering, no BOM, no whitespace, and no trailing LF. Construction order is normative for
the builder and validator but is not hash authority because canonical serialization sorts all mapping keys.
`snapshot_sha256` is SHA-256 of exactly those bytes. The existing B1 `checkpoint_sha256` remains SHA-256 of its existing
canonical `_checkpoint_content(CheckpointEvidence)` mapping, which includes this exact snapshot and
`snapshot_sha256`, excludes only `checkpoint_id` and `checkpoint_sha256`, uses the same canonical JSON settings, and
has no LF. Durable `PrivateCommitEnvelopeV1` bytes remain the Section 9 canonical envelope JSON plus one final LF; its
existing domain-separated envelope hash therefore binds the complete checkpoint and snapshot without defining a
second snapshot representation.

On Turn 2 resume, the loaded Turn 1 envelope, exact `CheckpointEvidence`, `checkpoint_id`, `checkpoint_sha256`,
`snapshot_sha256`, plan pair, dialogue ID, Turn 1 and Turn 2 request IDs, execution-unit IDs, payload hashes, response
text/hash, resource identity/hash, runtime identity, and all snapshot fields must equal the values freshly rebuilt from
the frozen plan, validated Turn 1 commit, and fixed authority. The validator callable must be the exact Python object
`run_formal_evaluation._validate_fixed_synthetic_snapshot_v1`. The snapshot passed to the Turn 2 executor is a
deep-detached read-only mapping with value equality to the validated nested snapshot; transient Python object identity
with the loaded mapping is neither required nor accepted as evidence. Any Turn 1/Turn 2 identity mismatch fails
`STORE_DEPENDENCY_INVALID` before B1, tracker/proxy construction, executor dispatch, or fake-client invocation.

runtime_resource_authority is an object with exactly three keys:

transport_implementation_sha256
runtime_identity_sha256
resources

transport_implementation_sha256 is exactly
"464890905866d517bb036569458e6dd69578a2dbacd0eab272c4f0f6ec6fb927". This is a new Stage B2-owned LF-canonical
semantic source authority because Stage A validates this field but exposes no public function that derives its value.
The file remains implementation-byte-unchanged in Stage B2; `.gitattributes` is not added or modified.

The complete derivation algorithm is:

1. Read repository-relative `scripts/formal_evaluation_transport.py` as bytes.
2. If the first three bytes are UTF-8 BOM `EF BB BF`, reject; the frozen source authority contains no BOM.
3. Reject every `0D` carriage-return byte not immediately followed by `0A`.
4. Count newline encodings without decoding: an LF newline is a `0A` not preceded by `0D`; a CRLF newline is the pair
   `0D 0A`.
5. If both counts are positive, reject mixed LF/CRLF source.
6. If LF count is positive and CRLF count is zero, classify the file as `LF-only`.
7. If CRLF count is positive and LF count is zero, classify the file as `CRLF-only`.
8. If both counts are zero and no lone CR exists, classify the file as `no-newline`. This classification is
   unambiguous, is accepted, and performs no EOL replacement.
9. For `CRLF-only`, replace every exact `0D 0A` pair with the one byte `0A`. For `LF-only` and `no-newline`, leave the
   byte sequence unchanged.
10. Leave every other byte unchanged; do not decode, Unicode-normalize, trim, alter a final newline, rewrite
    whitespace, or normalize any non-EOL byte.
11. Hash the resulting canonical bytes with SHA-256.
12. Require the frozen literal above and pass only that literal to B1.

The current source is BOM-free LF-only and its canonical bytes produce the frozen literal. A semantically identical
all-CRLF checkout produces the same literal. BOM, lone CR, mixed line endings, or a canonical hash mismatch, including
any non-EOL mutation, fails `STORE_FIXED_AUTHORITY_MISMATCH` before lock acquisition or durable-state access. On
reopen, the builder reruns this algorithm before lock acquisition; after locking, the stored contract must still equal
the freshly constructed contract, with an otherwise valid stored mismatch classified
`STORE_RUN_CONTRACT_MISMATCH`. No statement or loader may treat raw checkout bytes as this identity.

runtime_identity_sha256 is exactly
"0d96cec3538ab20a1ded87990dd1a79ea2d7a5e4a3166136f435839cffa89f12". This is a new Stage B2-owned synthetic-runtime
contract hash because B1 validates only the hash format and exposes no public fixed runtime-identity value. Its exact
canonical preimage is:

{
  "checkpoint_evidence_schema_version":1,
  "domain":"formal-evaluation-synthetic-runtime-identity-v1",
  "snapshot_validator_id":"run_formal_evaluation._validate_fixed_synthetic_snapshot_v1",
  "synthetic_snapshot_schema_version":1
}

The hash is SHA256 of the Section 9 canonical UTF-8 JSON for that exact four-key object, with no LF. The builder
reconstructs this object from literals, hashes it, requires the literal above, and passes that value to B1. It does not
import formal_evaluation_runtime, a formal core, a baseline, a model, or a production loader.

resources is an unordered JSON object with exactly four keys:

qa_only_reconstructed_baseline
v2
single_turn
context_aware

Each key maps to an object with exactly two keys:

resource_identity: exact 18-key object
resource_identity_sha256: exact lowercase SHA-256 string

Every resource_identity has exactly these 18 required, non-null fields and types:

schema_version: integer, not boolean, exactly 1
resource_type: string, exactly "synthetic_fixture"
logical_resource_id: nonempty Stage A safe-ID string
system_config_id: one of the four exact resource-map keys
formal_system_id: exact public Stage A formal-system ID
corpus_path: canonical repository-relative string
embeddings_path: canonical repository-relative string
corpus_sha256: lowercase SHA-256 string
embeddings_sha256: lowercase SHA-256 string
cache_family: exact public Stage A resource family
corpus_version: string, exactly "synthetic_v1"
row_count: nonnegative integer, not boolean
qa_count: nonnegative integer, not boolean
snippet_count: nonnegative integer, not boolean
embedding_model: string, exactly "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
embedding_rows: nonnegative integer, not boolean
embedding_dimensions: integer, not boolean, exactly 384
synthetic: boolean, exactly true

The exact four resource wrappers are:

{
  "qa_only_reconstructed_baseline":{
    "resource_identity":{
      "cache_family":"v1_qa",
      "corpus_path":"synthetic/v1_qa/corpus.json",
      "corpus_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "corpus_version":"synthetic_v1",
      "embedding_dimensions":384,
      "embedding_model":"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
      "embedding_rows":15333,
      "embeddings_path":"synthetic/v1_qa/embeddings.npy",
      "embeddings_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "formal_system_id":"qa_only_reconstructed_baseline",
      "logical_resource_id":"synthetic_fixture_v1_qa_synthetic_v1",
      "qa_count":15333,
      "resource_type":"synthetic_fixture",
      "row_count":15333,
      "schema_version":1,
      "snippet_count":0,
      "synthetic":true,
      "system_config_id":"qa_only_reconstructed_baseline"
    },
    "resource_identity_sha256":"c5fd900704eb81cabe18d88fdd17a8ecbfcca21b4e177e50d71cf770989accbb"
  },
  "v2":{
    "resource_identity":{
      "cache_family":"v2_mixed",
      "corpus_path":"synthetic/v2_mixed/corpus.json",
      "corpus_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "corpus_version":"synthetic_v1",
      "embedding_dimensions":384,
      "embedding_model":"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
      "embedding_rows":15688,
      "embeddings_path":"synthetic/v2_mixed/embeddings.npy",
      "embeddings_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "formal_system_id":"current_v2",
      "logical_resource_id":"synthetic_fixture_v2_mixed_synthetic_v1",
      "qa_count":15333,
      "resource_type":"synthetic_fixture",
      "row_count":15688,
      "schema_version":1,
      "snippet_count":355,
      "synthetic":true,
      "system_config_id":"v2"
    },
    "resource_identity_sha256":"66eada900971b203d1c016dace29506c10bf2b3847b75e2c315ddcbe90d60bc5"
  },
  "single_turn":{
    "resource_identity":{
      "cache_family":"v2_mixed",
      "corpus_path":"synthetic/v2_mixed/corpus.json",
      "corpus_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "corpus_version":"synthetic_v1",
      "embedding_dimensions":384,
      "embedding_model":"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
      "embedding_rows":15688,
      "embeddings_path":"synthetic/v2_mixed/embeddings.npy",
      "embeddings_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "formal_system_id":"v2_without_context_management",
      "logical_resource_id":"synthetic_fixture_v2_mixed_synthetic_v1",
      "qa_count":15333,
      "resource_type":"synthetic_fixture",
      "row_count":15688,
      "schema_version":1,
      "snippet_count":355,
      "synthetic":true,
      "system_config_id":"single_turn"
    },
    "resource_identity_sha256":"a26b9d8eb847524836824616ffd9be6e8922884cd18c33bc5aae2938ca8c9567"
  },
  "context_aware":{
    "resource_identity":{
      "cache_family":"v2_mixed",
      "corpus_path":"synthetic/v2_mixed/corpus.json",
      "corpus_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "corpus_version":"synthetic_v1",
      "embedding_dimensions":384,
      "embedding_model":"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
      "embedding_rows":15688,
      "embeddings_path":"synthetic/v2_mixed/embeddings.npy",
      "embeddings_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "formal_system_id":"v21b_context_aware",
      "logical_resource_id":"synthetic_fixture_v2_mixed_synthetic_v1",
      "qa_count":15333,
      "resource_type":"synthetic_fixture",
      "row_count":15688,
      "schema_version":1,
      "snippet_count":355,
      "synthetic":true,
      "system_config_id":"context_aware"
    },
    "resource_identity_sha256":"cb83d074063606eb612ebbe63409327203534821ec44aa7ebd0f0623e9cc007c"
  }
}

The repeated a...a corpus digest and b...b embeddings digest are exact new Stage B2-owned synthetic-fixture identity
literals. They preserve the already validated B1 synthetic test convention but do not claim to hash a file and never
authorize reading either synthetic path. They are not production hashes and cannot be replaced by caller values.

For each entry the builder constructs the exact ProductionResourceIdentity through the fixed runner-owned mapping,
obtains it through SyntheticResourceBundle.resource_for(key), calls public Stage A validate_resource_identity(),
requires agreement with public formal_identity(key), and calls public Stage A resource_identity_sha256(). Both the
returned 18-key mapping and returned public hash must equal the exact wrapper above. Stage B2 does not redefine the
Stage A resource hash.

Resource paths obey the existing public Stage A 240-character and 128-character-component constraints. No
resource-identity field is optional or nullable. Stage B2 accepts only synthetic = true and resource_type =
"synthetic_fixture".

schema_authority is an object with exactly nine keys. Every value is an integer, not a boolean, and no field is
nullable:

{
  "attempt_archive_schema_version":1,
  "b1_checkpoint_evidence_schema_version":1,
  "formal_result_schema_version":1,
  "journal_wrapper_schema_version":1,
  "private_commit_envelope_schema_version":1,
  "run_contract_schema_version":1,
  "stage_a_authoritative_success_schema_version":1,
  "stage_a_inflight_journal_schema_version":3,
  "stage_a_resource_identity_schema_version":1
}

run-contract, archive, wrapper, envelope, and formal-result version literals are new Stage B2-owned schema authority.
The Stage A journal, authoritative-success, and resource versions and the B1 checkpoint-evidence version are freshly
verified through their existing public constructors/validators and must equal 3, 1, 1, and 1 respectively. Stage B2
does not add aliases, migrations, or version fallbacks.

All JSON objects are semantically unordered maps. Arrays are used only where an inherited public Stage A/B1 schema
requires an array. Canonical serialization sorts every mapping key recursively; source insertion order has no identity
significance. Durable contract bytes nevertheless must be the one canonical sorted-key representation.

### Stage B2 loader limits

Limits apply before semantic validation. Encoded-file limits include the final LF.

 Category                                                                                       Maximum encoded bytes
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 run_contract.json                                                                                            131,072
────────────────────────────────────────────────────────────────────────────  ────────────────────────────────────────
 One mutable current-journal record                                                                           524,288
────────────────────────────────────────────────────────────────────────────  ────────────────────────────────────────
 One immutable attempt archive                                                                                524,288
────────────────────────────────────────────────────────────────────────────  ────────────────────────────────────────
 One private commit envelope, including formal result and checkpoint                                        2,097,152
 evidence
────────────────────────────────────────────────────────────────────────────  ────────────────────────────────────────
 Temporary publication candidate                                               Same limit as its destination category
────────────────────────────────────────────────────────────────────────────  ────────────────────────────────────────
 Run-wide lock file binary sentinel                                                                          Exactly 1

Every recursively loaded Stage B2 JSON value also obeys:

 Limit                                                                  Exact value
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Nesting depth                                     16, counting the root as depth 1
────────────────────────────────────────────────  ──────────────────────────────────
 UTF-8 bytes in any mapping key or string value                             262,144
────────────────────────────────────────────────  ──────────────────────────────────
 Members in any mapping                                                         128
────────────────────────────────────────────────  ──────────────────────────────────
 Members in any array                                                           256
────────────────────────────────────────────────  ──────────────────────────────────
 Durable filename component                                    180 ASCII characters
────────────────────────────────────────────────  ──────────────────────────────────
 Dynamic identifier before .json                               128 ASCII characters
────────────────────────────────────────────────  ──────────────────────────────────
 Dynamic .json filename                                        133 ASCII characters
────────────────────────────────────────────────  ──────────────────────────────────
 Repository-relative resource/frozen path                           240 UTF-8 bytes
────────────────────────────────────────────────  ──────────────────────────────────
 Repository-relative path component                            128 ASCII characters

Fixed cardinalities are: six frozen-input entries, four formal-system entries, four resource entries, three RQ-count
entries, four system-count entries, 190 plan members, 190 unique request IDs, execution orders 1–190, and at most
three Stage A attempts per execution unit. At most one current journal and one first-success commit may exist per
unit. Each attempt may contribute at most four archive records, so one unit may have at most 12 attempt archives.

The encoded-byte check occurs before UTF-8 decoding or JSON parsing. Duplicate-key detection occurs during parsing.
Depth, string, mapping, and array limits are then enforced recursively before schema-specific interpretation. Equality
at a limit is accepted; one unit above it fails closed.

### Exact Stage B2 hash domains

The one lock-file byte is exactly 0x00. It is a binary sentinel, not JSON, and is not passed to the JSON loader.

Canonical hash input is UTF-8 encoded, ensure_ascii=False, sorted keys, compact separators, allow_nan=False, and no
NaN/Infinity. Hash input has no trailing LF; the final LF belongs only to durable JSON file representation.

- run_contract_sha256:

  SHA256(canonical_json({
    "domain":"formal-evaluation-run-contract-v1",
    "contract": contract_without_run_contract_sha256
  }))

  Excluded self-field: run_contract_sha256.

- plan_member_sha256:

  SHA256(canonical_json({
    "domain":"formal-evaluation-plan-member-v1",
    "plan_member": complete_exact_validated_plan_member
  }))

  Excluded self-field: plan_member_sha256; it is never inserted into the source plan member. Row-level text
  participates in memory but is not persisted in plan_member_binding.

- formal_result_sha256:

  SHA256(canonical_json({
    "domain":"formal-evaluation-private-formal-result-v1",
    "formal_result": exact_project_formal_result_output
  }))

  Excluded self-field: formal_result_sha256.

- envelope_sha256:

  SHA256(canonical_json({
    "domain":"formal-evaluation-private-commit-envelope-v1",
    "envelope": envelope_without_envelope_sha256
  }))

  Excluded self-field: envelope_sha256.

- Mutable journal record_sha256:

  SHA256(canonical_json({
    "domain":"formal-evaluation-private-journal-record-v1",
    "record": record_without_record_sha256
  }))

  Excluded self-field: record_sha256.

- Immutable attempt archive_sha256:

  SHA256(canonical_json({
    "domain":"formal-evaluation-private-attempt-archive-v1",
    "archive": archive_without_archive_sha256
  }))

  Excluded self-field: archive_sha256.

journal_sha256, provider_response_sha256, and resource_identity_sha256 remain owned by their existing public Stage A
definitions. checkpoint_record_sha256 is exactly the checkpoint_sha256 field validated by the existing public B1
validate_checkpoint_evidence(); Stage B2 adds no checkpoint wrapper and no second checkpoint hash. Stage A exposes no
public execution-identity or authoritative-success hash, so PrivateCommitEnvelopeV1 contains neither redundant field.
The enclosing Stage B2 envelope_sha256 binds the exact public ExecutionIdentity.to_dict() and, when present, the exact
public AuthoritativeSuccess.to_dict().
private_commit_sha256 is exactly the referenced commit’s envelope_sha256; archive-pointer hashes are exactly the
referenced records’ archive_sha256.

### Exact run-contract construction and reopen comparison

Before lock acquisition, the public runner path:

1. calls verify_frozen(), validate_plan(), plan_fingerprint(), validate_registry(), and formal_identity();
2. reconstructs the exact public provider/generation snapshots and hashes;
3. derives the fixed transport implementation with the LF-canonical semantic source algorithm above and reconstructs
   the Stage B2 runtime-identity preimage;
4. constructs and publicly validates the exact four synthetic resource identities and their Stage A hashes;
5. verifies exact Python identity for every fixed offline dependency and constructs schema_authority from the literals
   above;
6. constructs the eight non-self top-level members solely from these authorities; and
7. calculates run_contract_sha256 using the domain above.

No public parameter or stored field supplies any contract member except the exact validated frozen plan itself.

After acquiring the run lock, create-or-open is one decision:

- If no contract and no other durable state exists, serialize the freshly constructed expected object as canonical
  UTF-8 JSON plus one LF and publish it create-only.
- If any durable state other than the valid one-byte lock sentinel exists without a contract, fail
  STORE_STATE_WITHOUT_CONTRACT.
- If a contract exists, enforce the encoded limit before decoding, strict UTF-8, duplicate-key rejection, recursive
  limits, exact nine-key schema, exact canonical bytes plus LF, every literal and public-authority comparison, and the
  exact self-hash.
- Freshly reconstruct the complete expected object again from current fixed authority and require ordinary mapping
  equality and byte-for-byte equality with canonical(expected) plus LF.
- A semantically equal but differently ordered, whitespace-varied, escaped, or otherwise noncanonical file fails
  STORE_NONCANONICAL_JSON; it is not rewritten.
- A mismatch in any authority group fails STORE_RUN_CONTRACT_MISMATCH. No migration or caller-selected replacement is
  permitted.

### Lock and contract ordering

The private-state root and all directory names are fixed constants. The only pre-lock filesystem creation is the
Section 12 lock-infrastructure bootstrap: safe creation of missing fixed root components and the exact one-byte
run.lock sentinel after fixed-root containment validation. Those components are not application durable evidence. No
caller-selected path is accepted.

Non-durable frozen-plan and fixed-dependency validation may occur before lock acquisition. The run-wide Windows msvcrt
lock is then acquired before:

- inspecting whether any durable state exists;
- creating, opening, or semantically comparing the run contract;
- deciding that durable state exists without a contract;
- cleaning temporary files;
- loading, validating, repairing, reconciling, or publishing any journal, archive, commit, or pointer.

The lock remains held through the complete authoritative decision/write/fake-call lifecycle. Contract create-or-open
is one locked decision: if no contract and no other durable state exists, publish the one freshly derived expected
contract create-only; if durable state exists without a contract, fail closed; otherwise validate exact canonical and
semantic equality. Two processes therefore cannot independently authorize different initial contracts.

## 10. Private commit-envelope schema

Use one immutable PrivateCommitEnvelopeV1 with exactly 14 top-level keys in the construction order shown:

schema_version: 1
formal_result_schema_version: 1
run_contract_sha256

plan_member_binding:
  plan_fingerprint
  plan_member_sha256
  execution_unit_id
  execution_order
  request_id
  rq
  case_id
  dialogue_id
  turn_index
  system_config_id
  formal_system_id
  input_sha256
  payload_sha256
  resolved_payload_sha256
  frozen_test_file_sha256

execution_identity:
  exact ExecutionIdentity.to_dict()

success_kind: "provider" | "local"

attempt_lineage:
  attempt_number
  attempt_id
  prepared_archive_sha256
  pre_commit_archive_sha256
  predecessor_attempt_id
  predecessor_terminal_archive_sha256

authoritative_success:
  exact AuthoritativeSuccess.to_dict() or null

formal_result:
  exact canonical project_formal_result() output
formal_result_sha256

response_sha256
provider_response_sha256: SHA-256 or null

rq3_relationship:
  kind:
    "none" | "single_turn" |
    "context_turn_one" | "context_turn_two"
  dialogue_id
  turn_one_request_id
  turn_two_request_id
  turn_one_commit_sha256
  checkpoint_evidence
  checkpoint_record_sha256

envelope_sha256

schema_version and formal_result_schema_version are integers, not booleans, exactly 1. run_contract_sha256,
formal_result_sha256, response_sha256, and envelope_sha256 are non-null lowercase SHA-256 strings.
provider_response_sha256 is null only for local success and otherwise is a lowercase SHA-256. success_kind is exactly
"provider" or "local". plan_member_binding has exactly 15 keys, execution_identity is the exact closed 26-key public
ExecutionIdentity.to_dict(), attempt_lineage has exactly six keys, authoritative_success is null or the exact closed
10-key public AuthoritativeSuccess.to_dict(), and rq3_relationship has exactly seven keys. No top-level or nested field
is optional.

formal_result has exactly these 46 keys; the fixed B1 path supplies all of them for both local and Provider results:

plan_fingerprint
execution_unit_id
execution_order
request_id
research_question
case_id
dialogue_id
turn_index
turn_id
input_checkpoint_id
input_checkpoint_sha256
system_config_id
formal_system_id
resolved_runtime_system_id
payload_sha256
resolved_payload_sha256
transport_contract_id
transport_contract_sha256
generation_contract_id
generation_contract_sha256
transport_implementation_sha256
resource_identity
resource_identity_sha256
attempt_id
response_text
response_sha256
provider
provider_model
attempt_count
route
guard_category
requires_backend_api
retrieval_used
retrieved_document_ids
retrieved_scores
checkpoint_snapshot_sha256
execution_status
status
provider_called
provider_request_id
provider_response_id
provider_response_sha256
call_started_at
provider_returned_at
committed_at
authoritative_success

Every field is validated by public project_formal_result(), and the reprojected canonical JSON must equal the stored
canonical mapping. retrieved_document_ids and retrieved_scores are JSON arrays of equal length. The exact fixed
executor produces either both empty arrays or respectively ["synthetic_doc"] and [0.5]. All inherited Stage A
identity, SHA, integer, boolean, safe-ID, response-length, status, RQ/system/turn, resource, and Provider/local
nullability constraints remain mandatory. Missing or additional formal-result fields fail STORE_SCHEMA_INVALID even
if project_formal_result() would otherwise accept an optional safe field.

plan_member_sha256 hashes the complete exact validated plan member without persisting its row-level user text
separately. The commit therefore binds the complete member while minimizing unnecessary private duplication.

Validation:

- Reconstruct and validate ExecutionIdentity through public Stage A APIs.
- Re-run public project_formal_result() and require canonical equality.
- Provider success requires exact public AuthoritativeSuccess validation and matching result fields.
- Local success requires authoritative_success = null, provider_called = false, and every Provider evidence field
  null.

- Result, authoritative-success, checkpoint, and response hashes must agree independently.
- Context-aware Turn 1 requires the full exact B1 CheckpointEvidence nested in the envelope.
- Context-aware Turn 2 requires the exact Turn 1 commit hash and input checkpoint hashes.
- Envelope hashing uses a domain-separated canonical hash excluding envelope_sha256.

Publication is create-only first-success:

- Existing identical canonical envelope: idempotent success, no second record.
- Existing different valid envelope for the same execution unit: STORE_CONFLICTING_FIRST_SUCCESS; preserve the first
  file
  unchanged.

- Existing malformed envelope: fail closed; never overwrite it.
- A physically duplicated file under another name is store tampering, not a second count.

### Discriminator and nullability rules

PrivateCommitEnvelopeV1, plan_member_binding, attempt_lineage, and rq3_relationship use fixed key sets. Conditional
fields remain present and use the null rules below; no unlisted optional fields exist.

plan_member_binding has exactly:

plan_fingerprint: lowercase SHA-256 string
plan_member_sha256: lowercase SHA-256 string
execution_unit_id: nonempty Stage A identifier
execution_order: integer 1..190
request_id: nonempty Stage A request identifier
rq: "RQ1" | "RQ2" | "RQ3"
case_id: nonempty string
dialogue_id: nonempty string for RQ3; null for RQ1/RQ2
turn_index: integer 1 or 2
system_config_id: one of the four fixed configuration identifiers
formal_system_id: exact canonical formal-system ID
input_sha256: lowercase SHA-256 string
payload_sha256: lowercase SHA-256 string
resolved_payload_sha256: lowercase SHA-256 string
frozen_test_file_sha256: lowercase SHA-256 string

attempt_lineage has exactly:

attempt_number
attempt_id
prepared_archive_sha256
pre_commit_archive_sha256
predecessor_attempt_id
predecessor_terminal_archive_sha256

For attempt 1, attempt_number = 1; attempt_id, prepared_archive_sha256, and pre_commit_archive_sha256 are non-null;
both predecessor fields are null.

For attempts 2 and 3, attempt_number is respectively 2 or 3; all six fields are non-null. The predecessor fields
identify exactly the immediately preceding Stage A attempt and its terminal retryable archive. No attempt 4 is
representable.

For provider success, pre_commit_archive_sha256 references the validated provider_returned archive immediately
preceding private publication. For local success, it equals prepared_archive_sha256, because the authoritative Stage A
journal remains prepared and no Provider transition occurs.

For success_kind = "provider":

- authoritative_success is non-null and is exactly the closed public Stage A AuthoritativeSuccess.to_dict() result;
- provider_response_sha256 is non-null and equals the validated Stage A Provider response evidence;
- formal_result.provider_called is exactly true;
- response_sha256 equals the hash of the projected response text and agrees with provider_response_sha256;
- all result identity, Provider request, attempt, and success fields agree with the reconstructed Stage A execution
  identity and authoritative success.

For success_kind = "local":

- authoritative_success is null;
- provider_response_sha256 is null;
- formal_result.provider_called is exactly false;
- every Provider request, response, receipt, or success-evidence field inside the inherited formal-result schema is
  null according to that schema;

- response_sha256 remains non-null and hashes the validated local response text.

rq3_relationship has exactly:

kind
dialogue_id
turn_one_request_id
turn_two_request_id
turn_one_commit_sha256
checkpoint_evidence
checkpoint_record_sha256

The discriminator rules are:

- kind = "none" exactly for RQ1/RQ2. All six other fields are null.
- kind = "single_turn" exactly for either RQ3 single_turn member. dialogue_id, turn_one_request_id, and
  turn_two_request_id are non-null and equal the exact validated RQ3 pair. turn_one_commit_sha256,
  checkpoint_evidence, and checkpoint_record_sha256 are null.

- kind = "context_turn_one" exactly for RQ3 context_aware Turn 1. dialogue_id, both request IDs, checkpoint_evidence,
  and checkpoint_record_sha256 are non-null. turn_one_commit_sha256 is null to avoid self-reference. Checkpoint
  evidence is the exact closed B1 object generated for this Turn 1 and intended Turn 2.

- kind = "context_turn_two" exactly for RQ3 context_aware Turn 2. All six other fields are non-null.
  turn_one_commit_sha256 identifies the exact validated immutable Turn 1 envelope; checkpoint_evidence is the exact B1
  checkpoint consumed as input; and checkpoint_record_sha256 equals its existing B1 hash.

The dialogue and pair IDs are derived from the exact validated plan, never supplied separately. Any wrong kind,
missing field, extra field, wrong null, unexpected non-null value, mismatched Turn 1 reference, or checkpoint mismatch
fails closed.

## 11. Durable journal and attempt-archive schemas

### Mutable journal record

MutableJournalRecordV1 is a JSON object with exactly these 12 keys in Python construction order:

schema_version
run_contract_sha256
execution_unit_id
attempt_number
attempt_id
predecessor_attempt_id
predecessor_terminal_archive_sha256
latest_archive_sha256
private_commit_sha256
journal
journal_sha256
record_sha256

Its exact types and bounds are:

- schema_version: integer, not boolean, exactly 1.
- run_contract_sha256: non-null lowercase SHA-256, exactly the open RunContractV1 hash.
- execution_unit_id: non-null lowercase SHA-256, exactly journal.identity.execution_unit_id.
- attempt_number: integer, not boolean, in 1..3, exactly journal.identity.attempt_number.
- attempt_id: non-null string matching attempt_[0-9a-f]{64}, at most 72 ASCII characters, exactly
  journal.identity.attempt_id.
- predecessor_attempt_id: null for attempt 1; otherwise a non-null attempt_[0-9a-f]{64} string.
- predecessor_terminal_archive_sha256: null for attempt 1; otherwise a non-null lowercase SHA-256.
- latest_archive_sha256: always a non-null lowercase SHA-256 identifying the unique validated archive-chain tip.
  A mutable record is never published before its first archive, so null is always invalid.
- private_commit_sha256: null or a lowercase SHA-256 under the exact state matrix below.
- journal: the exact closed public Stage A InflightJournal.to_dict() mapping, schema version 3.
- journal_sha256: non-null lowercase SHA-256, exactly public Stage A journal_sha256(reconstructed_journal).
- record_sha256: non-null lowercase SHA-256 under the Section 9 mutable-record domain.

For attempts 2 and 3, predecessor_attempt_id equals the immediately preceding attempt’s Stage A attempt_id and
predecessor_terminal_archive_sha256 resolves to that attempt’s unique retryable_failed chain tip. The predecessor
journal must be accepted by public next_retry_journal(); the resulting prepared journal must equal the nested current
journal exactly. Both predecessor fields are either null together for attempt 1 or non-null together for attempts 2
and 3. No other combination is valid.

The journal remains Stage A schema version 3. Stage B2 does not add a new Stage A state.

### Immutable attempt archive

AttemptArchiveV1 is a JSON object with exactly these 14 keys in Python construction order:

schema_version
run_contract_sha256
execution_unit_id
attempt_number
attempt_id
sequence_number
event
predecessor_attempt_id
predecessor_terminal_archive_sha256
previous_archive_sha256
journal
journal_sha256
private_commit_sha256
archive_sha256

Its exact types and bounds are:

- schema_version: integer, not boolean, exactly 1.
- run_contract_sha256, execution_unit_id, journal_sha256, and archive_sha256: non-null lowercase SHA-256 strings.
- attempt_number: integer, not boolean, in 1..3.
- attempt_id: non-null attempt_[0-9a-f]{64} string, at most 72 ASCII characters.
- sequence_number: integer, not boolean, in 1..4.
- event: exactly one of "prepared", "call_started", "provider_returned", "retryable_failed", "terminal_failed",
  "uncertain", or "committed".
- predecessor_attempt_id and predecessor_terminal_archive_sha256: the same attempt-dependent nullability and exact
  values required by MutableJournalRecordV1.
- previous_archive_sha256: null exactly when sequence_number = 1; otherwise a non-null lowercase SHA-256 equal to the
  immediately preceding archive’s archive_sha256.
- journal: exact closed public Stage A InflightJournal.to_dict(), schema version 3.
- private_commit_sha256: null or a lowercase SHA-256 under the exact matrix below.

execution_unit_id, attempt_number, and attempt_id equal the same nested journal.identity fields. journal_sha256 equals
public journal_sha256(reconstructed_journal). archive_sha256 uses the Section 9 archive domain and excludes only
archive_sha256. No archive field is optional.

For a given attempt, sequence_number starts at exactly 1 and each subsequent archive increments it by exactly one.
The first archive has previous_archive_sha256 = null. Every later archive points to the immediately preceding archive.
The chain has at most four records. A repeated number, skipped number, number above 4, wrong previous hash, second
sequence-1 record, fork, cycle, or cross-attempt link fails STORE_ARCHIVE_CHAIN_INVALID.

For each journal publication:

1. Create and durably verify the immutable archive.
2. Construct MutableJournalRecordV1 with latest_archive_sha256 equal to that archive’s archive_sha256 and all other
   identity, predecessor, journal, journal-hash, and commit-pointer fields equal to the archive.
3. Atomically replace the mutable record.
4. Only then allow the next action.

If a crash occurs after archive publication but before mutable replacement, the unique valid archive-chain tip is
authoritative and the mutable record is reconstructed or advanced to exact tip equality under the lock. A missing or
lagging mutable pointer is the only repairable mutable condition. A mutable record ahead of the tip, off-chain,
identity-conflicting, hash-conflicting, or pointing to a competing tip fails closed and is never overwritten.

### Authoritative wrapper state and nullability matrix

The table below is exhaustive. "A1" means attempt 1, whose two predecessor fields are null. "A2/A3" means attempt 2 or
3, whose two predecessor fields are non-null and identify the immediately preceding terminal retryable attempt.
"Commit" is private_commit_sha256. Every row applies independently to A1 and A2/A3 except where the row says otherwise.

 Attempt      Sequence  Nested Stage A state  event               Previous archive       Commit       Exact consequence
━━━━━━━━━━━━  ━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 A1 or A2/A3         1  prepared              prepared            null                   null          Required first record; same attempt may execute
 A1 or A2/A3         2  call_started          call_started        sequence 1 hash        null          Fake call may begin only after mutable tip update
 A1 or A2/A3         2  retryable_failed      retryable_failed    sequence 1 hash        null          Valid only for Stage A pre_send_failure
 A1 or A2/A3         2  prepared              prepared            sequence 1 hash        commit hash   Local private commit publication; journal bytes unchanged
 A1 or A2/A3         3  provider_returned     provider_returned   sequence 2 hash        null          Provider result may be committed; no further call
 A1 or A2/A3         3  retryable_failed      retryable_failed    sequence 2 hash        null          Explicit post-call retryable failure
 A1 or A2/A3         3  terminal_failed       terminal_failed     sequence 2 hash        null          Permanently non-executable
 A1 or A2/A3         3  uncertain             uncertain           sequence 2 hash        null          Permanently non-executable
 A1 or A2/A3         4  committed             committed           sequence 3 hash        commit hash   Exact public Stage A reconciliation; confirmed

The sequence-2 repeated prepared row is the only permitted same-State-A-journal repetition. Its journal and
journal_sha256 equal sequence 1 exactly; only previous_archive_sha256, private_commit_sha256, sequence_number, and
archive_sha256 change. It is valid only when the referenced immutable local PrivateCommitEnvelopeV1 validates for the
same run, execution unit, attempt, result, and prepared archive.

The committed row is valid only after a matching Provider PrivateCommitEnvelopeV1 exists. Its nested journal must equal
public Stage A reconcile(sequence-3 provider_returned journal, envelope authoritative_success, expected identity)
exactly. No local commit can produce a committed row.

The complete pointer matrix is:

- Initial prepared, call_started, provider_returned, retryable_failed, terminal_failed, and uncertain archives and
  mutable records: private_commit_sha256 is null.
- Local completion: only the sequence-2 repeated prepared archive and its matching mutable record have a non-null
  private_commit_sha256.
- Provider completion before reconciliation: the sequence-3 provider_returned archive and mutable record remain null
  even though the independently validated commit file now exists.
- Provider completion after reconciliation: only the sequence-4 committed archive and its matching mutable record have
  a non-null private_commit_sha256.
- In every valid mutable record latest_archive_sha256 is non-null and equals the exact archive tip. There is no
  represented null-latest state.

The only permitted within-attempt transitions are:

prepared(1) -> call_started(2)
prepared(1) -> retryable_failed(2) for pre_send_failure only
prepared(1) -> prepared-with-local-commit(2)
call_started(2) -> provider_returned(3)
call_started(2) -> retryable_failed(3) for an explicit post-call retryable category
call_started(2) -> terminal_failed(3)
call_started(2) -> uncertain(3)
provider_returned(3) -> committed(4), only through public reconcile() after private commit publication

All other transitions are forbidden, including prepared directly to provider_returned; call_started to prepared;
failure to any state in the same attempt; provider_returned to a failure; local prepared-with-commit to call_started;
committed to any state; any transition after sequence 4; any second local pointer archive; and any retry construction
from call_started, provider_returned, uncertain, terminal_failed, committed, or attempt-3 retryable_failed.

Attempts are derived only by public Stage A next_retry_journal(). Attempt 2 begins at its own sequence 1 after attempt
1’s exact retryable_failed tip; attempt 3 begins likewise after attempt 2. The terminal predecessor archive remains
immutable and is not linked through previous_archive_sha256, which is attempt-local; it is linked only through the two
predecessor fields.

### Exact archive-tip repair consequences

- No mutable record and one valid chain: recreate the mutable record exactly from the unique tip.
- Mutable record points to an earlier archive on the same unique chain: replace it with the exact tip projection.
- Mutable record equals the unique tip: no write.
- Valid local commit plus sequence-1 prepared tip: append the one sequence-2 prepared-with-commit archive, then advance
  the mutable record. If that archive already exists and is valid, only advance the mutable record.
- Valid Provider commit plus sequence-3 provider_returned tip: call public recovery_decision() and reconcile(), append
  the exact sequence-4 committed archive, then advance the mutable record. If the committed archive already exists and
  is valid, only advance the mutable record.
- Valid commit plus any tip other than the exact local prepared or Provider provider_returned/committed state required
  by its discriminator: fail STORE_COMMIT_JOURNAL_CONFLICT without repair.
- No commit plus prepared tip: retain the same attempt as executable.
- No commit plus retryable_failed attempt-1/2 tip: only public next_retry_journal() may create the next attempt’s
  sequence-1 prepared archive.
- No commit plus call_started, provider_returned, uncertain, terminal_failed, attempt-3 retryable_failed, or committed
  tip: permanently non-executable; committed-without-commit additionally fails STORE_COMMITTED_WITHOUT_PRIVATE_COMMIT.
- Competing tips, fork, gap, malformed archive, missing referenced predecessor, missing referenced commit, foreign
  identity, or mutable-ahead condition: fail closed; do not repair.

“Confirmed” remains a recovery decision derived from a valid private commit plus committed journal; it is not a new
persisted state. Local success retains its exact prepared Stage A journal. Unknown or malformed wrapper, lineage, state,
or hash fails before execution, and local persistence failure never enters the Provider retry loop.

### Archive event authority

Retain event, but it is only a redundant derived label. After validating the nested Stage A journal, require this
exact mapping:

journal.state == "prepared"          -> event == "prepared"
journal.state == "call_started"      -> event == "call_started"
journal.state == "provider_returned" -> event == "provider_returned"
journal.state == "retryable_failed"  -> event == "retryable_failed"
journal.state == "terminal_failed"   -> event == "terminal_failed"
journal.state == "uncertain"         -> event == "uncertain"
journal.state == "committed"         -> event == "committed"

No other event or Stage A state is valid. event never authorizes a transition, retry, Provider call, recovery
decision, or progress result.

event = "committed" is valid only when the nested journal is the exact result of the public Stage A committed
transition and private_commit_sha256 is non-null and resolves to the matching validated commit. Private commit
publication alone does not create a committed event.

A local success retains journal.state = "prepared" and therefore event = "prepared" even when its archive or mutable
wrapper contains a non-null private-commit pointer. Local completion is derived from the validated immutable commit,
not from event.

Mutable and archive wrapper hashes use the Section 9 domains. Nested journal_sha256 remains the exact existing Stage A
journal hash. Any event/state mismatch fails closed before repair, reconciliation, retry construction, or execution.

## 12. Process-lock contract and lifetime

- Path: data/formal_eval/private_state/run.lock
- Authority: successful OS byte-range lock, never file existence.
- Platform: Windows only; import/use msvcrt lazily.
- Binary byte contract: the file is exactly one byte and that byte is exactly 0x00. It is lock infrastructure, not a
  JSON document or application payload.
- Bootstrap: after fixed-root containment validation, create run.lock exclusively if absent; write exactly b"\x00",
  flush, call os.fsync(), and close. If exclusive creation loses a race, open the winner. Open the resulting file in
  binary read/write mode, seek to byte 0, and require exact bytes b"\x00" before locking.
- Existing-file validation: size zero, size greater than one, byte other than 0x00, read failure, non-regular file, or
  reparse point fails STORE_LOCK_FILE_INVALID. The file is never padded, truncated, repaired, or replaced.
- Lock: byte 0, length 1, msvcrt.LK_NBLCK.
- Contention: retry for at most 5 seconds using time.monotonic(), then fail STORE_LOCK_BUSY.
- Same-process protection: a module-level registry guarded by threading.Lock rejects a second lease for the same
  canonical path immediately.

- Ownership evidence: the live _RunWideLock object, its open handle, locked flag, PID, thread ID, and successful
  msvcrt.locking call. No stale owner text is authoritative.

- Normal exit: unlock with LK_UNLCK, close handle, clear registry in finally.
- Forced termination: Windows releases the byte lock when the process handle closes.
- After acquisition, seek to byte 0 and revalidate the same open handle’s exact one-byte content and the contained path
  identity. Any mismatch fails STORE_LOCK_FILE_INVALID while retaining the lock through cleanup.
- A persistent valid one-byte lock file with no OS lock is immediately reusable.
- Unsupported platforms fail STORE_PLATFORM_UNSUPPORTED; there is no lockless fallback.

The lock covers the entire operation:

contract open/validation
-> temp cleanup
-> journal/archive/commit validation
-> reconciliation
-> Stage A decision
-> all pre-call persistence
-> entire executor and fake-client lifecycle
-> post-call persistence
-> commit publication
-> final reconciliation
-> progress derivation
-> return

This run-wide scope prevents two processes from authorizing the same fake Provider call.

## 13. Filesystem layout and containment

Fixed production layout:

data/formal_eval/private_state/
├── run.lock
├── run_contract.json
├── journals/
│   └── <execution_unit_id>.json
├── attempts/
│   └── <execution_unit_id>/
│       └── <attempt>-<sequence>-<journal_sha256>.json
└── commits/
    └── <execution_order>-<execution_unit_id>.json

Temporary files are sibling files in the target directory:

.<target-name>.<cryptographic-random-hex>.tmp

Containment rules:

- Public durable APIs accept no output-root or filename parameter.
- Production root is derived from the runner module’s repository root.
- Execution filenames use validated Stage A hashes and bounded integers only.
- Reject absolute, drive-relative, UNC, extended UNC, URI-like, mixed-separator, traversal, empty-segment, control-
  character, trailing-space/dot, reserved Windows-device, or caller-selected paths.

- Walk every existing component with lstat; reject symlinks, junctions, or any FILE_ATTRIBUTE_REPARSE_POINT.
- Recheck containment after controlled directory creation and before every publish.
- Create only the fixed root and fixed subdirectories, one component at a time.
- Unknown files or directories inside the store fail closed, except recognized abandoned temporary files.
- Tests may patch only the private module root constant to a validated OS-temporary path, use the already frozen fixed
  fake dependencies, and install the one named Section 27 controller through its private context manager. No production
  API exposes that override, and no other dependency, store-path, persistence, clock, validator, or Provider patch is
  authorized.

.gitignore:42 ignores all of data/, and git check-ignore confirmed the proposed path is ignored. No tracked file
currently exists under data/formal_eval/.

## 14. Atomic and durable write protocol

Use Python standard library plus Win32 calls through ctypes; add no dependency.

For every durable JSON write below. The one-byte run.lock bootstrap is the sole exception and follows Section 12
exactly:

1. Validate fixed contained target and non-reparse parent.
2. Serialize canonical UTF-8 JSON plus final LF.
3. Create an exclusive sibling temporary file.
4. Write in binary mode.
5. Flush and call os.fsync().
6. Close every handle.
7. Publish using MoveFileExW with MOVEFILE_WRITE_THROUGH.
    - Mutable records: add MOVEFILE_REPLACE_EXISTING.
    - Immutable contract/archive/commit: omit replacement flag, so an existing target cannot be overwritten.

8. Reopen and verify exact bytes and canonical hash.
9. Treat any missing Win32 durability capability as STORE_DURABILITY_UNAVAILABLE; do not fall back to best effort.

Recovery rules:

- Failure before publication: old mutable target remains authoritative; temp is cleaned on reopen.
- Failure after successful publication but before return: reopen validates the target and treats it as published.
- Immutable collision: validate existing target; identical is idempotent, different is conflict.
- Mutable replacement never occurs until the new archive record is durable.
- Truncated or malformed target fails closed.
- Abandoned temp cleanup happens only while holding the run lock, only for exact owned-name patterns, and cleanup
  failure blocks opening.

- No directory or file is silently repaired by overwriting malformed durable evidence.

## 15. Exact persistence and fake Provider-call ordering

1. verify_frozen().
2. validate_plan(), exact fingerprint, exact selected membership, exact RQ3 relationship.
3. Construct and validate the fixed fake-only authority and derive the exact expected run contract.
4. Resolve fixed private path, acquire run-wide OS lock.
5. Create or exactly reopen immutable run contract.
6. Clean recognized temps; validate archives, journals, commits, and checkpoint evidence.
7. If a valid commit exists, reconcile it and return without executor/client invocation.
8. Load the current exact journal and retry predecessor.
9. Ask public Stage A recovery_decision().
    - begin or continue_before_provider: enter public B1 with the exact current evidence.
    - retry: call public next_retry_journal(), publish the new attempt’s sequence-1 prepared archive and mutable record,
      derive progress, and return retry_constructed with zero executor/client calls.
    - fail_closed: return the exact direct permanently_non_executable outcome with zero executor/client calls.
    - if the selected context-aware Turn 2 has no commit because its required Turn 1 is directly permanently
      non-executable: return the Section 21 dependency-permanent row with zero attempt construction, callback,
      executor/client call, or B1 invocation.
10. B1 independently repeats recovery_decision() and exact identity validation.
11. For begin, B1 invokes the exact Section 23 synchronous callback once with the new prepared journal; that callback
    persists the exact sequence-1 prepared archive and mutable record. For same-attempt continuation, including resumed
    attempt 2/3, B1 validates and reuses the existing prepared tip and exact retry predecessor without invoking the
    callback or appending a duplicate. Prepared evidence is durable before tracker/proxy construction and executor
    dispatch.
12. If the executor invokes Provider:
    - derive exact Stage A call_started transition;
    - invoke the Section 23 callback to durably archive and publish it;
    - only then invoke the proxy, begin the tracker, and call the fake client.
    - invoke the named Section 27 test controller only at its exact permitted point when test mode is valid.

13. Invoke the Section 23 callback exactly once for the newly validated B1 post-call journal/archive before
    AuthoritativeSuccess, result/checkpoint construction, public B1 outcome construction, or any result commit.
14. Revalidate B1 AuthoritativeSuccess, project_formal_result(), plan binding, and checkpoint.
15. Publish the create-only private commit. Context Turn 1 result and checkpoint are one file.
    Invoke the Section 27 post-commit test point only after readback verification.
16. Provider success only: call public Stage A recovery_decision() and reconcile(), then persist the exact committed
   journal/archive. Invoke the committed-archive test point only after archive readback and before mutable replacement.

17. Local success: append the sequence-2 repeated prepared archive with the commit pointer, then replace the mutable
   wrapper without inventing a Provider journal transition.

18. Derive progress only from all validated immutable private commits.
19. Release the lock.

The required invariant is preserved:

private result before journal commit

## 16. Crash-boundary table

Crash boundary      Durable evidence            Restart decision     Another fake call?    Reconciliation
━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Before contract     No formal state,    Clean temp; create exact                    Yes    None
 publication         or temp only                        contract
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After contract,     Exact contract                 Stage A begin                    Yes    Create attempt 1
 before journal      only
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After prepared      Prepared            continue_before_provider                    Yes    Same attempt
                     archive/current
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After retry         Prepared plus       continue_before_provider                    Yes    Validate via
 attempt 2/3         exact                                                                  next_retry_journal
 prepared            predecessor
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After               Call-started                     fail_closed                     No    Preserve conservative
 call_started,       archive                                                                ambiguity
 before fake call
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After fake call,    Call-started                     fail_closed                     No    Manual/future governed
 before post-call    archive                                                                resolution only
 persistence
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After retryable     Call-started                     fail_closed                     No    Lost retry evidence is
 response, before    archive                                                                not guessed
 failure
 persistence
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After retryable     Retryable            Construct next prepared;                  No     Return retry_constructed;
 journal             archive              return; attempts <3                              later invocation may call
 persistence
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After uncertain/    Exact terminal                   fail_closed                     No    Preserve
 terminal            archive
 persistence
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After provider-     Provider-                        fail_closed                     No    Result is unavailable
 returned            returned archive
 evidence, before
 commit
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 During private-     Provider-                        fail_closed                     No    Clean temp
 commit temp         returned
 write               archive, no
                     commit
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After commit        Valid commit             reconcile_committed                     No    Stage A reconcile()
 publication,        plus pre-commit
 before journal      archive
 commit
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 During              Valid commit;         reconcile_committed or                     No    Repair lagging pointer
 committed-          committed                          confirmed
 journal             archive may lead
 publication         mutable pointer
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 After journal       Valid commit and                   confirmed                     No    Return existing result
 commit, before      committed
 return              journal
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 Local result        Prepared journal       Re-execute fixed local                   No     No authoritative success
 before commit       only                   path                                            existed
                                                                              authorizes
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 Local commit        Valid local                      Commit wins                     No    Repair commit pointer
 before wrapper      commit, prepared
 update              journal
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 Context Turn 1      Result and                 Already committed                     No    Turn 2 may resume
 commit before       checkpoint in
 return              one commit
──────────────────  ──────────────────  ──────────────────────────  ─────────────────────  ───────────────────────────
 Turn 2 start        Exact Turn 1             Validate checkpoint        Only for Turn 2    Never replay Turn 1
 after Turn 1        commit/                            before B1
 commit              checkpoint

Persisting call_started before the actual call may conservatively block a call that never commenced. That false-
positive fail-closed outcome is intentional; the design never guesses that a call was absent.

## 17. Durable-state reconciliation matrix

Commit evidence                         Journal/archive evidence                Decision
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 None                                    None                                    Stage A begin
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Prepared attempt 1                      Continue same attempt
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Prepared attempt 2/3 plus exact         Continue same attempt
                                         predecessor
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Prepared retry without predecessor      Fail closed
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Call started                            Fail closed; no recall
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Provider returned                       Fail closed; authoritative result
                                                                                 missing
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Retryable failed, attempt 1/2           Construct Stage A retry; return
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Retryable failed, attempt 3             Fail closed
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Uncertain or terminal                   Fail closed
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 None                                    Committed journal                       Protocol conflict: committed journal
                                                                                 without private result
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Valid Provider commit                   Exact provider-returned                 Public Stage A reconcile to
                                         same-attempt journal                    committed
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Valid Provider commit                   Exact committed journal                 Confirmed
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Valid Provider commit                   Mutable journal missing, referenced     Reconstruct wrapper from archive;
                                         archive valid                           reconcile
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Valid local commit                      Exact prepared journal                  Complete locally; no Provider
                                                                                 recovery
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Valid commit                            Lagging mutable pointer, unique         Advance pointer
                                         later archive tip
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Valid commit                            Missing referenced archive              Commit invalid; fail closed
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Valid commit                            Conflicting journal fields or           Fail closed; preserve both
                                         identity
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Identical publication replay            Existing canonical commit               Idempotent; count once
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Conflicting second success              Existing different valid commit         Fail closed; preserve first
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Malformed/truncated commit              Any                                     Fail closed
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Foreign execution/attempt/run           Any                                     Fail before executor/client
 identity
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Provider success object without         Any                                     Fail closed
 result
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Provider result without                 Any                                     Fail closed
 authoritative success
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Exact local result with null success    Prepared journal                        Valid
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Turn 2 with missing/foreign/            Any                                     Fail before Turn 2 executor
 malformed checkpoint
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Duplicate physical commit/archive       Any                                     Fail closed; never double-count
 path
──────────────────────────────────────  ──────────────────────────────────────  ──────────────────────────────────────
 Unknown file, archive fork, lineage     Any                                     Fail closed
 gap

A valid private commit is never discarded merely because final journal publication was interrupted.

## 18. Conflicting-success behavior

- The canonical path is unique per execution unit.
- The first valid create-only commit remains authoritative.
- Identical replay returns the existing commit.
- A different response, success receipt, attempt, resource, checkpoint, or result produces
  STORE_CONFLICTING_FIRST_SUCCESS.
- The existing file is not renamed, replaced, deleted, or “corrected.”
- The conflicting candidate is not persisted as a second success.
- Progress continues to count the single valid first commit, but the current operation fails closed and reports the
  conflict category without row content.

## 19. Attempts 1–3 and retry-predecessor behavior

- Maximum attempts remain Stage A’s exact value: 3.
- Attempt IDs and Provider request IDs remain exclusively Stage A-derived.
- Retry is permitted only from a public Stage A retryable_failed journal.
- Attempt 2 links to attempt 1’s immutable terminal archive.
- Attempt 3 links to attempt 2’s immutable terminal archive.
- A restarted prepared attempt 2/3 must supply the exact Section 23 `retry_predecessor` to B1.
- B1 validates it only by recreating
  `next_retry_journal(retry_predecessor, journal.prepared_at)` and requiring exact dataclass equality; it invokes no
  persistence callback for either already durable object.
- No attempt skipping, repetition, backward movement, or caller-selected attempt number is accepted.
- Attempt 4 remains impossible through public Stage A validation.
- An uncertain, terminal, provider-returned-without-commit, or call-started journal is never retried.
- A post-call persistence failure leaves at least call_started; it is therefore non-recallable.

## 20. Exact RQ3 durable lifecycle

Context-aware Turn 1:

1. Validate exact frozen Turn 1/Turn 2 pair.
2. Execute Turn 1 once under the run lock.
3. Validate B1 formal result, complete CheckpointEvidence, and the exact Section 9 synthetic snapshot schema version 1.
4. Publish both as one private commit.
5. Count Turn 1 only after that commit is durable.

Turn 2:

1. Locate exact Turn 1 commit by validated plan identity.
2. Validate its complete envelope.
3. Validate nested checkpoint through public validate_checkpoint_evidence().
4. Require exact resource identity, runtime identity, dialogue, system, request IDs, payload hashes, response hash,
   snapshot hash, every exact outer/nested snapshot field, state/history, and expected Turn 2.

5. Pass that exact checkpoint to B1.
6. Bind the Turn 2 commit to the Turn 1 commit hash and checkpoint hashes.

Rules:

- A committed Turn 1 can never lack its checkpoint.
- Turn 1 is never replayed to reconstruct a checkpoint.
- Missing, extra, foreign, malformed, mutated, cross-run, or cross-resource checkpoint evidence fails before Turn 2
  execution.

- Pair mismatch and checkpoint mismatch are tested independently.
- An interrupted process can resume Turn 2 from the Turn 1 commit.
- Single-turn RQ3 commits bind both dialogue request IDs but contain no checkpoint.

## 21. Restart-safe progress derivation

Progress scans and validates canonical commit files under the lock.

### DurableProgress

DurableProgress is a frozen public dataclass with exactly these 12 fields in this order:

schema_version: int
run_state: str
total_successful_units: int
successful_by_rq: Mapping[str, int]
successful_by_system: Mapping[str, int]
remaining_units: int
next_eligible_execution_order: int | None
initial_executable_units: int
same_attempt_continuable_units: int
retry_constructible_units: int
dependency_blocked_units: int
permanently_non_executable_units: int

Validation authority is deliberately split.

`DurableProgress.__post_init__` validates only facts expressible from these 12 stored fields. It:

- requires `schema_version` to have exact type `int`, never `bool`, and value `1`;
- requires `run_state` to have exact type `str` and be exactly `"in_progress"`, `"temporarily_blocked"`,
  `"permanently_blocked"`, or `"complete"`;
- requires `total_successful_units`, `remaining_units`, `initial_executable_units`,
  `same_attempt_continuable_units`, `retry_constructible_units`, `dependency_blocked_units`, and
  `permanently_non_executable_units` each to have exact type `int`, never `bool`, and be in `0..190`;
- requires `next_eligible_execution_order` to be null or exact type `int`, never `bool`, in `1..190`;
- requires `successful_by_rq` to be a mapping with exactly `RQ1`, `RQ2`, and `RQ3`; makes a fresh detached `dict`;
  requires exact non-boolean integer values respectively in `0..102`, `0..40`, and `0..48`; and stores an exact
  `types.MappingProxyType` over that fresh copy;
- requires `successful_by_system` to be a mapping with exactly `qa_only_reconstructed_baseline`, `v2`, `single_turn`,
  and `context_aware`; makes a fresh detached `dict`; requires exact non-boolean integer values respectively in
  `0..71`, `0..71`, `0..24`, and `0..24`; and stores an exact `types.MappingProxyType` over that fresh copy.

Let:

- `S = total_successful_units`;
- `R = remaining_units`;
- `I = initial_executable_units`;
- `C = same_attempt_continuable_units`;
- `Y = retry_constructible_units`;
- `D = dependency_blocked_units`;
- `P = permanently_non_executable_units`; and
- `E = I + C + Y`.

`__post_init__` enforces every aggregate equation explicitly:

1. `S + R = 190`.
2. `successful_by_rq["RQ1"] + successful_by_rq["RQ2"] + successful_by_rq["RQ3"] = S`.
3. `successful_by_system["qa_only_reconstructed_baseline"] + successful_by_system["v2"] +
   successful_by_system["single_turn"] + successful_by_system["context_aware"] = S`.
4. `I + C + Y + D + P = R`.
5. Therefore `S + I + C + Y + D + P = 190`; this is checked directly as well so no aggregate count can leave an
   unclassified unit.

The aggregate run-state implications enforced by `__post_init__` are exactly:

- `"in_progress"`: `0 <= S < 190`, `R > 0`, `E > 0`, and `next_eligible_execution_order` is non-null. `D` and `P` may
  also be nonzero, but the presence of at least one executable, continuable, or retry-constructible unit makes the run
  active.
- `"temporarily_blocked"`: `0 <= S < 190`, `R > 0`, `I = 0`, `C = 0`, `Y = 0`, `P = 0`, `D = R > 0`, and
  `next_eligible_execution_order` is null.
- `"permanently_blocked"`: `0 <= S < 190`, `R > 0`, `I = 0`, `C = 0`, `Y = 0`, `P >= 1`, `D + P = R`, and
  `next_eligible_execution_order` is null. Thus initial-executable, same-attempt-continuable, and retry-constructible
  counts are all exactly zero; at least one permanently blocked unit exists; completed count is less than 190; and the
  partition equation leaves no unclassified unit.
- `"complete"`: `S = 190`, `R = 0`, `I = 0`, `C = 0`, `Y = 0`, `D = 0`, `P = 0`, and
  `next_eligible_execution_order` is null.

Direct public construction can establish only those aggregate invariants. A non-null proposed next order may be
range-valid and aggregate-consistent without being the execution order of an eligible unit, and
`DurableProgress.__post_init__` does not claim otherwise.

Only the locked progress factory establishes unit-order facts. Its private signature is exactly:

```python
def _derive_durable_progress_locked(
    plan: Sequence[Mapping[str, Any]],
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
) -> DurableProgress
```

It has no defaults and accepts no proposed counts, category assignment, run state, or next order. It first requires
exact runtime type `_RunWideLock`, the live lock for the fixed private root, and the exact already validated open
RunContractV1 mapping; wrong or inactive lock evidence fails `STORE_LOCK_BUSY`, and contract mismatch fails
`STORE_RUN_CONTRACT_MISMATCH`. While holding that same run-wide lock, it iterates the exact validated 190-member plan
once and derives for every formal unit exactly one of six categories: successful,
initial-executable, same-attempt-continuable, retry-constructible, dependency-blocked, or
permanently-non-executable. It rejects an overlapping assignment, a missing assignment, an unknown execution-unit ID,
or any assignment not justified by validated commit/journal/archive/dependency evidence. It independently proves that
the 190 unique assignments reproduce all RQ, system, success, and remaining counts above. After the more specific
archive, commit, dependency, and path categories have been ruled out, an overlap, omission, unknown assignment,
aggregate mismatch, or internally proposed non-lowest next order fails exactly `STORE_SCHEMA_INVALID`.

The factory forms the eligible set only from initial-executable, same-attempt-continuable, and retry-constructible
units. If nonempty, it proves `next_eligible_execution_order = min(unit.execution_order for unit in eligible_set)` and
constructs `"in_progress"`. If empty and `S = 190`, it constructs `"complete"`; if empty, `S < 190`, and `P >= 1`, it
constructs `"permanently_blocked"`; otherwise it requires `D = R > 0` and constructs `"temporarily_blocked"`. The
factory, not the dataclass, is the exclusive authority for the lowest-order fact.

Count unique validated execution-unit IDs only. Per-RQ and per-system values come from the validated plan binding, not
stored caller labels. Malformed, foreign, conflicting, duplicated, unknown, forked, or noncanonical evidence raises
StoreError and produces no DurableProgress.

Category assignment is exact and mutually exclusive:

- Initial executable: exact plan member, no commit, no journal/archive evidence, and all dependencies validated.
- Same-attempt continuable: valid prepared tip with null commit pointer and no later evidence.
- Retry constructible: exact retryable_failed attempt-1/2 tip, no commit, and exact predecessor lineage.
- Dependency blocked: context-aware RQ3 Turn 2 with an otherwise valid absent Turn 1 commit, where Turn 1 remains
  initially executable, same-attempt continuable, or retry constructible; no Turn 2 durable evidence.
- Permanently non-executable: call_started; provider_returned without its matching commit; uncertain; terminal_failed;
  attempt-3 retryable_failed; or a context-aware Turn 2 whose exact required Turn 1 is permanently non-executable.
- Successful: a unique validated immutable private commit, regardless of a repairable lagging mutable record.

Malformed or contradictory evidence is not counted as permanently non-executable; it raises the exact StoreError
category and blocks the whole scan.

Retry construction is deliberately one durable operation: public next_retry_journal() constructs the new prepared
journal, Stage B2 publishes its sequence-1 archive and mutable record, and the invocation returns before invoking the
executor. A later invocation continues that same prepared attempt with its exact predecessor. This makes
retry_constructed a stable public return condition and never recalls the predecessor attempt.

No mutable success counter is authoritative. Future --max-new-successes accounting must be:

validated commit count at end - validated commit count at invocation start

Stage B2 does not add that CLI option to real execution or treat it as authorization.

### DurableExecutionOutcome

DurableExecutionOutcome is a frozen public dataclass with exactly these 11 fields in this order:

schema_version: int
action: str
execution_unit_id: str | None
execution_order: int | None
attempt_number: int | None
journal_state: str | None
private_commit_sha256: str | None
block_category: str | None
provider_call_count: int
orchestration_outcome: OrchestrationOutcome | None
progress: DurableProgress

schema_version is integer 1, not boolean. action is exactly "advanced", "completed", "retry_constructed",
"dependency_blocked", "permanently_non_executable", "no_eligible", or "run_complete". provider_call_count is integer
0 or 1, not boolean. Non-null execution_unit_id is a lowercase SHA-256; non-null execution_order is an integer in
1..190; non-null attempt_number is an integer in 1..3; non-null journal_state is one exact public Stage A journal state;
non-null private_commit_sha256 is a lowercase SHA-256.

block_category is null except:

- dependency_blocked -> exactly "dependency_missing";
- permanently_non_executable -> exactly "call_started", "provider_returned_without_commit", "uncertain",
  "terminal_failed", "attempts_exhausted", or the one dependency-permanent literal `"dependency_permanent"`.

The action matrix is exact:

- advanced: selected unit ended in retryable_failed attempt 1 or 2 and is durably retry-constructible;
  identity/order/attempt/journal_state are non-null; commit and block are null; orchestration_outcome is the exact
  existing closed B1 OrchestrationOutcome; provider_call_count equals its 0-or-1 count.
- completed: a new or pre-existing local/Provider commit validates and final repair/reconciliation is complete;
  identity/order/attempt/journal_state/commit are non-null; block is null. orchestration_outcome is the exact B1 object
  for a new completion and null for an idempotently reopened completion. provider_call_count is 0 for reopen or local
  completion and 1 only for a new Provider completion.
- retry_constructed: a new Stage A-derived attempt-2/3 prepared archive and mutable record were durably published;
  identity/order/attempt are non-null, journal_state = "prepared", commit/block/orchestration_outcome are null, and
  provider_call_count = 0.
- dependency_blocked: selected context Turn 2 has no Turn 1 commit; identity/order are non-null; attempt, journal,
  commit, and orchestration_outcome are null; block = "dependency_missing"; provider_call_count = 0.
- permanently_non_executable for a direct journal-state blocker: selected unit has one valid direct permanent state;
  identity/order/attempt/journal are non-null; commit and orchestration_outcome are null; block is exactly
  `"call_started"`, `"provider_returned_without_commit"`, `"uncertain"`, `"terminal_failed"`, or
  `"attempts_exhausted"` as derived from the validated Stage A journal; provider_call_count = 0.
- permanently_non_executable for a dependency-permanent Turn 2: selected unit is context-aware RQ3 Turn 2, its exact
  required Turn 1 has no valid commit and is in one of the direct permanently non-executable journal states, and no
  Turn 2 journal/archive/commit exists. `execution_unit_id` and `execution_order` are non-null and equal the selected
  dependent Turn 2 plan member; `attempt_number`, `journal_state`, `private_commit_sha256`, and
  `orchestration_outcome` are null; `block_category = "dependency_permanent"`; `provider_call_count = 0`. The Turn 1
  dependency execution-unit ID and execution order are not exposed because the existing 11 public fields have no
  dependency-identity member; they are derived internally from the exact validated RQ3 pair. No public field is added.
  In embedded progress this Turn 2 contributes exactly one to `permanently_non_executable_units` and zero to
  `dependency_blocked_units`; the global `run_state` is then derived only by the exact aggregate matrix, so it remains
  `"in_progress"` if any unit is eligible and otherwise becomes `"permanently_blocked"`.
- no_eligible: no unit argument was supplied, progress.run_state is temporarily_blocked or permanently_blocked, and
  progress.next_eligible_execution_order is null. All unit, attempt, journal, commit, block, and B1 fields are null;
  provider_call_count = 0.
- run_complete: no unit argument was supplied and progress.run_state = "complete". All unit, attempt, journal, commit,
  block, and B1 fields are null; provider_call_count = 0.

For every non-global action, execution_unit_id and execution_order equal the exact validated plan member and progress is
derived after the operation under the same lock. For no_eligible and run_complete, no B1 call, executor call, fake-
client call, journal creation, or commit publication occurs.

For the dependency-permanent row, the validated Turn 1 journal/archive evidence is classification authority but is not
copied into the public outcome. There is no Turn 2 Stage A journal, B1 predecessor, B1 checkpoint evidence,
ProviderCallTracker, FixedGenerationProxy, executor context, fake-client call, or persistence callback. Explicitly
selecting that Turn 2 returns exactly this row even when another unit is eligible; it never constructs an attempt. When
the scheduler encounters it during locked derivation, it classifies and skips it, selects the lowest other eligible
unit if one exists, and otherwise returns global `no_eligible` with `"permanently_blocked"` progress. Reopening derives
the same classification and explicit-selection row from the same immutable evidence with zero publication. A Turn 1
that is only initially executable, same-attempt continuable, or retry constructible makes Turn 2
`dependency_blocked` with `"dependency_missing"`, never `"dependency_permanent"`.

DurableExecutionOutcome embeds the existing B1 OrchestrationOutcome only in the two rows stated above; it does not
duplicate, reserialize, or redefine that B1 type. `DurableExecutionOutcome.__post_init__` validates the exact row
matrix, including the dependency-permanent nullability above. `DurableProgress.__post_init__` validates only its
aggregate authority as specified; the locked factory proves unit categories and lowest order. Both dataclasses detach
nested mappings and reject direct construction with extra fields through their exact generated signatures.

## 22. Stage A public APIs to consume

From formal_evaluation_transport.py:

- validate_registry
- formal_identity
- fixed_generation_snapshot
- transport_contract_snapshot
- generation_contract_id
- generation_contract_sha256
- transport_contract_id
- transport_contract_sha256
- validate_resource_identity
- resource_identity_sha256
- validate_sha256
- project_formal_result

From formal_evaluation_inflight.py:

- ExecutionIdentity.from_mapping
- validate_execution_identity
- InflightJournal.from_mapping
- validate_journal
- journal_sha256
- AuthoritativeSuccess.from_mapping
- validate_authoritative_success
- recovery_decision
- reconcile
- create_initial_journal
- transition
- next_retry_journal
- public ID derivation functions only for validation/tests

Do not use Stage A underscore-prefixed objects, tracker internals, capability objects, or reconstructed state
machines.

## 23. B1 APIs and files to integrate

Consume:

- run_formal_evaluation.verify_frozen
- validate_plan
- plan_fingerprint
- formal_system_ids
- generation_sha
- orchestrate_offline_unit
- formal_evaluation_orchestration.orchestrate_validated_unit
- SyntheticResourceBundle.resource_for
- validate_checkpoint_evidence
- returned OrchestrationOutcome

Narrow B1 changes:

- Add only the two exact keyword-only integration parameters below. They are internal B1 integration authority passed
  by the fixed Stage B2 runner; neither is added to any Section 24 public durable API.
- Persist newly created B1 journal transitions synchronously.
- Move the call_started transition out of `_RawClientBoundary.create()` to the `invoke_provider()` boundary immediately
  before `FixedGenerationProxy.invoke()`, persist it, then permit tracker begin and the fake call.
- Validate exact predecessor evidence for resuming prepared retries.
- Keep both parameters optional so every existing B1 call and behavior remains unchanged when no durable store is
  used.
- Do not change retry classification, projection, checkpoint meaning, system identity, or success validation.

The existing public B1 forwarding signatures become exactly:

```python
def orchestrate_validated_unit(
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    *,
    journal_persistence_callback: Callable[[InflightJournal], None] | None = None,
    retry_predecessor: InflightJournal | None = None,
    **dependencies: Any,
) -> OrchestrationOutcome
```

and:

```python
def orchestrate_offline_unit(
    plan: list[dict[str, Any]],
    unit: dict[str, Any],
    *,
    journal_persistence_callback: Callable[[InflightJournal], None] | None = None,
    retry_predecessor: InflightJournal | None = None,
    **dependencies: Any,
) -> OrchestrationOutcome
```

Their existing `plan`, `unit`, and `**dependencies` behavior remains. Each wrapper forwards the two named values
unchanged and by exact keyword; neither wrapper invokes the callback. The runner still performs frozen-plan,
membership, and RQ3-pair validation first. Existing injected resources/executors/fake client/clock/identity hashes and
existing recovery inputs remain in `**dependencies`; Stage B2 does not add a general dependency bundle or any new
caller-selected durable authority. Because the runner already uses postponed annotations and a function-local
orchestration import, `InflightJournal` and `OrchestrationOutcome` are imported only under `TYPE_CHECKING` for these
annotations; runtime dispatch retains the existing function-local import and avoids a circular import.

The private B1 core retains its existing parameter list and order through `snapshot_validator`, followed by these
recovery parameters in this exact order and with these exact defaults:

```python
journal_persistence_callback: Callable[[InflightJournal], None] | None = None,
retry_predecessor: InflightJournal | None = None,
journal: InflightJournal | None = None,
authoritative_success: AuthoritativeSuccess | Mapping[str, Any] | None = None,
checkpoint_evidence: CheckpointEvidence | Mapping[str, Any] | None = None,
turn_one_unit: Mapping[str, Any] | None = None,
turn_two_unit: Mapping[str, Any] | None = None,
claimed_ids: Mapping[str, Any] | None = None,
```

The exact callback contract is
`journal_persistence_callback(journal: InflightJournal) -> None`. The argument has exact runtime type
`InflightJournal`, has passed public `validate_journal()`, and is the newly created full Stage A journal value that must
become durable. Invocation and completion are synchronous on the orchestration thread. Exact successful return is
`None`; any other return, including `False`, `0`, an `InflightJournal`, or an awaitable, raises B1
`OrchestrationError("JOURNAL_PERSISTENCE_CALLBACK_RETURN_INVALID")`. Any exception raised by the callback, including a
Stage B2 `StoreError`, propagates as the identical exception object with its traceback; B1 does not wrap, classify,
retry, or convert it into executor, Provider, transport, journal, or orchestration failure. No B1 outcome is built
after such a failure.

The exact predecessor contract is `retry_predecessor: InflightJournal | None`. It is not a mapping and is never
reconstructed from caller labels. It must be null for attempt 1 and for every current journal other than a resumed
attempt-2/3 `prepared` journal. For a resumed attempt-2/3 prepared journal it is mandatory, has exact runtime type
`InflightJournal`, validates as the immediately preceding attempt’s `retryable_failed` journal, and has attempt number
exactly one less. B1 reconstructs:

```python
expected_prepared = next_retry_journal(
    retry_predecessor,
    journal.prepared_at,
)
```

and requires exact dataclass equality `expected_prepared == journal`, including complete execution identity,
attempt/provider IDs, all timestamps, state, and null fields. Missing required evidence retains
`RECOVERY_PREDECESSOR_REQUIRED`; wrong type, unexpected non-null evidence, invalid predecessor state/attempt, public
`next_retry_journal()` failure, or inequality fails `RECOVERY_PREDECESSOR_INVALID`. Stage B2 maps malformed loaded
predecessor evidence to `STORE_PREDECESSOR_INVALID` before execution. The validated predecessor is returned only as the
existing `OrchestrationOutcome.predecessor_journal`; the returned B1 type remains exactly `OrchestrationOutcome`.

The complete callback invocation matrix is:

 B1/Stage B2 path                              Callback invocations and exact publication rule
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Initial attempt preparation                   Once with the new attempt-1 `prepared` journal, after
                                                `create_initial_journal()`, recovery authorization, identity and journal
                                                validation; before ProviderCallTracker creation, FixedGenerationProxy
                                                construction, executor dispatch, or public outcome construction.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Same-attempt continuation, attempt 1          Zero. The already durable `prepared` journal is validated and consumed;
                                                it is not republished.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Resumed `prepared` attempt 2/3                Zero. Validate both the durable prepared journal and exact
                                                `retry_predecessor` by the reconstruction above before tracker/proxy
                                                creation; republish neither.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 B1 retry construction from retryable journal  Once with the newly returned `next_retry_journal()` prepared journal,
                                                after reconstruction/validation and before tracker/proxy creation.
                                                Existing non-durable B1 behavior may then continue. The Stage B2 durable
                                                scheduler instead constructs and persists this transition itself and
                                                returns `retry_constructed` without entering B1.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Resumed retry evidence                        Zero for both the already durable prepared journal and its already durable
                                                predecessor. Validation is read-only; reopening never republishes either.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Provider call start                           Once with the new `call_started` journal, after executor selection but
                                                before `FixedGenerationProxy.invoke()`, tracker `_begin`, raw-client
                                                entry, fake call-count increment, or any fake-client call.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Pre-send retryable transition                 Once with the new `retryable_failed` journal derived directly from
                                                prepared for exact `pre_send_failure`, before failure outcome
                                                construction; tracker remains not-called and fake-client call count is
                                                zero.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Provider-side success                         Once with the new `provider_returned` journal immediately after its Stage
                                                A transition and validation; before AuthoritativeSuccess construction,
                                                formal projection, checkpoint construction, B1 public outcome
                                                construction, private commit publication, or reconciliation.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Post-call retryable/terminal/uncertain state  Once with the newly transitioned failure journal, before failure outcome
                                                construction. The completed fake call is never repeated if persistence
                                                raises.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Private local commit publication              Zero. B1 has no local Stage A transition: the already durable prepared
                                                journal remains unchanged. Stage B2 publishes the private commit, then
                                                its Stage B2-owned repeated-prepared pointer archive, outside the B1
                                                callback.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Committed reconciliation                      Zero in the Stage B2 integration. After the Provider private commit,
                                                Stage B2 calls public Stage A `recovery_decision()` and `reconcile()` and
                                                durably publishes the resulting committed wrapper itself; it does not
                                                re-enter B1 or republish prior B1 evidence.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Dependency-blocked path                       Zero. No B1 invocation, attempt, journal, tracker/proxy, executor, or fake
                                                call exists.
─────────────────────────────────────────────  ───────────────────────────────────────────────────────────────────────
 Direct/dependency permanent path              Zero. Existing evidence is validated read-only; no dependent attempt or
                                                B1 object is constructed.

For initial and retry preparation, callback failure propagates before tracker creation, proxy construction, executor
dispatch, or fake-client access. For call start it propagates after inert tracker/proxy object construction but before
any tracker transition or proxy invocation. For all callback failures there is no later B1 transition, no public B1
outcome, and no additional Provider/fake-client call. Already durable prepared or retry-predecessor evidence is never
republished on same-attempt continuation, reopen, or resume.

## 24. New proposed public Stage B2 APIs

build_durable_run_contract(
    plan,
) -> Mapping[str, Any]

orchestrate_durable_offline_unit(
    plan,
    unit=None,
) -> DurableExecutionOutcome

durable_progress(
    plan,
) -> DurableProgress

No public Stage B2 API accepts:

- a store root or path;
- resources or a resource identity;
- transport_implementation_sha256;
- runtime_identity_sha256;
- snapshot_validator;
- an executor registry, client, or clock;
- a journal, archive, commit, success counter, claimed execution identity, attempt number, or checkpoint.

unit is the only nullable public argument. When non-null it must be one complete exact validated plan member. When null,
the API derives DurableProgress under the lock, selects the member at next_eligible_execution_order, or returns the
exact no_eligible/run_complete outcome from Section 21. No caller-selected label, identity, attempt, or dependency is
accepted.

An explicitly selected context-aware Turn 2 is classified before B1 entry. If its exact Turn 1 is directly permanently
non-executable and therefore can never publish valid checkpoint evidence, the API returns the exact Section 21
`"dependency_permanent"` outcome even if another plan unit is eligible. With `unit=None`, the locked factory never
selects that Turn 2 as eligible; it skips it and either selects the lowest eligible unit or returns the exact global
`no_eligible` row. Reopen performs the same derivation without creating a Turn 2 journal or attempt.

### StoreError

StoreError is a public RuntimeError subclass with exactly one Stage B2-owned field, category: str. Its constructor
accepts exactly one positional category, rejects values outside the vocabulary below, sets args == (category,), and
stores no path, exception text, row content, prompt, result, or arbitrary detail. The exact closed category vocabulary
is:

STORE_PLATFORM_UNSUPPORTED
STORE_LOCK_FILE_INVALID
STORE_LOCK_BUSY
STORE_PATH_INVALID
STORE_DURABILITY_UNAVAILABLE
STORE_IO_FAILURE
STORE_JSON_LIMIT_EXCEEDED
STORE_JSON_INVALID
STORE_NONCANONICAL_JSON
STORE_SCHEMA_INVALID
STORE_STATE_WITHOUT_CONTRACT
STORE_RUN_CONTRACT_MISMATCH
STORE_FIXED_AUTHORITY_MISMATCH
STORE_HASH_MISMATCH
STORE_ARCHIVE_CHAIN_INVALID
STORE_PREDECESSOR_INVALID
STORE_COMMIT_INVALID
STORE_COMMIT_JOURNAL_CONFLICT
STORE_COMMITTED_WITHOUT_PRIVATE_COMMIT
STORE_CONFLICTING_FIRST_SUCCESS
STORE_DEPENDENCY_INVALID
STORE_TEST_FAULT_INVALID

The mapping is exact:

- STORE_PLATFORM_UNSUPPORTED: msvcrt/required Windows locking is unavailable.
- STORE_LOCK_FILE_INVALID: run.lock is not a contained regular non-reparse file with exact byte b"\x00".
- STORE_LOCK_BUSY: valid OS byte lock was not acquired within five seconds, including same-process registry rejection.
- STORE_PATH_INVALID: containment, component, filename, reparse, unknown-entry, root, or recognized-temp-name validation
  fails.
- STORE_DURABILITY_UNAVAILABLE: required fsync or Win32 write-through/create-only capability is unavailable.
- STORE_IO_FAILURE: a validated ordinary read, write, flush, fsync, close, move, readback, or owned-temp cleanup
  operation fails.
- STORE_JSON_LIMIT_EXCEEDED: an encoded-byte or recursive depth/string/member/array limit is exceeded before semantic
  interpretation.
- STORE_JSON_INVALID: strict UTF-8 decoding, duplicate-key detection, JSON parsing, finite-number validation, or
  root-object validation fails.
- STORE_NONCANONICAL_JSON: decoded content is valid JSON but durable bytes are not exact canonical JSON plus LF.
- STORE_SCHEMA_INVALID: a Stage B2 object has a missing, extra, renamed, wrong-type, wrong-nullability, wrong-version,
  wrong-vocabulary, or out-of-bound field.
- STORE_STATE_WITHOUT_CONTRACT: non-lock durable state exists while run_contract.json is absent.
- STORE_RUN_CONTRACT_MISMATCH: a valid contract differs from the freshly reconstructed exact contract.
- STORE_FIXED_AUTHORITY_MISMATCH: current fixed public/Stage B2 authority differs before durable-state access,
  including a BOM, lone CR, mixed LF/CRLF source, or wrong LF-canonical semantic transport source hash.
- STORE_HASH_MISMATCH: a Stage B2 self-hash, public Stage A/B1 hash, file readback hash, or referenced hash differs.
- STORE_ARCHIVE_CHAIN_INVALID: archive sequence, previous link, event/state pair, fork, gap, tip, or mutable-tip
  projection is invalid.
- STORE_PREDECESSOR_INVALID: attempt-2/3 predecessor fields or public next_retry_journal reconstruction differ.
- STORE_COMMIT_INVALID: an envelope, plan binding, result, success, checkpoint, attempt lineage, or commit path is
  malformed or foreign without a separately classified journal conflict.
- STORE_COMMIT_JOURNAL_CONFLICT: a valid commit and valid journal/archive evidence disagree.
- STORE_COMMITTED_WITHOUT_PRIVATE_COMMIT: a Stage A committed journal/archive exists without its matching envelope.
- STORE_CONFLICTING_FIRST_SUCCESS: a different valid create-only envelope already occupies the canonical unit path.
- STORE_DEPENDENCY_INVALID: context Turn 2 dependency evidence exists but is malformed, foreign, conflicting, or
  mismatched. Simple absence returns dependency_blocked and is not an exception.
- STORE_TEST_FAULT_INVALID: the private test controller is malformed, enabled for the production root, uses a
  non-permitted fault point, or is combined with non-fixed fake types.

Existing public runner Blocked, Stage A TransportError/JournalError, and B1 OrchestrationError remain their existing
types only during pre-store validation of caller plan/unit input. Loaded durable evidence and store operations map to
the one exact StoreError category above; raw nested exception messages are never copied.

### Fixed private offline authority

The public path constructs one `_FixedOfflineAuthorityV1` inside runner authority. It is private and performs exactly
these authority steps:

- constructs the four fixed synthetic identities;
- validates them through SyntheticResourceBundle, validate_registry(), formal_identity(), and
  validate_resource_identity();
- obtains their hashes only through Stage A resource_identity_sha256();
- derives the exact Section 9 Stage B2-owned LF-canonical transport-implementation and runtime-identity values;
- binds `_validate_fixed_synthetic_snapshot_v1` by exact callable identity;
- supplies exact `_FixedOfflineExecutorRegistryV1`, `_FixedFakeRawClientV1`, and `_FixedSyntheticClockV1` types.

These values are derived before lock acquisition and compared against the fixed authority used to build the expected
contract. They are not taken from stored state or a public caller.

The fixed executor mode is deterministic and restart-independent: interpret the first hexadecimal digit of the exact
request_id; 0..7 selects local, and 8..f selects fake Provider. build_durable_run_contract verifies that the exact
validated 190-member plan contains at least one member of each mode for each of the four system configurations or fails
STORE_FIXED_AUTHORITY_MISMATCH. Local response text is exactly "STAGE_B2_SYNTHETIC_LOCAL " plus the first 24 request-ID
characters. Fake Provider response text is exactly "STAGE_B2_SYNTHETIC_PROVIDER " plus the same 24 characters. These
are synthetic offline markers, not formal model responses.

The fixed executor emits only the closed B1 core-result fields. Local mode uses route "local_guard", guard category
"synthetic_validation", requires_backend_api false, retrieval_used false, and empty retrieval lists. Provider mode
uses route "provider", the same guard category, requires_backend_api false, retrieval_used true, document ID
"synthetic_doc", and score 0.5. Context Turn 1 additionally emits exactly synthetic snapshot schema version 1 as
recursively closed in Section 9 and validated by the exact `_validate_fixed_synthetic_snapshot_v1` callable; no
runtime/core import is used and no production `ConversationState` behavior is redefined.

`_FixedFakeRawClientV1` accepts only the exact Stage A fixed request, records one in-memory call, and returns the exact
request ID, response ID "synthetic_response_" plus the first 24 hexadecimal characters after the call_ prefix, and the
fixed synthetic Provider text. `_FixedSyntheticClockV1` starts a new unit at "2026-07-23T10:00:00Z"; on restart it
initializes from the greatest validated timestamp in that unit’s lineage and returns timestamps exactly one second
later on each call. It never uses wall-clock time.

Direct authority-mutation tests may call one private comparison helper,
`_validate_fixed_offline_authority_for_tests(candidate)`, but may not pass candidate into a public durable API. Before
lock acquisition and before any durable-state inspection, the helper compares candidate with a freshly constructed
fixed expected bundle:

- exact four resource keys;
- exact 18-field identity equality for every resource;
- exact Stage A resource hash equality;
- exact LF-canonical transport-implementation and runtime-identity hash equality;
- exact `_FixedOfflineAuthorityV1` and `_StageB2TestFaultControllerV1` class identities;
- exact fixed snapshot-validator callable;
- exact clock, fake-client, and executor-registry class identities.

Mismatch fails before lock acquisition and cannot create, open, or reconcile a contract or any other durable state.
Supplying mutually consistent foreign resources, validators, and claimed hashes therefore cannot create a foreign run
contract.

The sole private subprocess exception is `_StageB2TestFaultControllerV1`, defined in formal_evaluation_store.py and
specified in Section 27. It is installed only through `_install_stage_b2_test_fault_controller_for_tests()` after the
private state root is patched to a validated OS-temporary path outside the repository. It is not a dependency bundle,
public argument, response modifier, or authority source.

Private helpers required include:

- Closed JSON serialization/loading/hashing
- Fixed-root and reparse containment
- _RunWideLock
- Win32 write-through publish
- Temp cleanup
- Run-contract construction/validation
- Journal/archive publication and chain loading
- Commit construction/validation/publication
- Existing-commit reconciliation
- RQ3 relationship derivation
- Exact `_derive_durable_progress_locked` factory from Section 21
- Runner exact-plan-member context helper
- B1 retry-predecessor validator and journal-persistence hook
- `_validate_fixed_offline_authority_for_tests`
- `_StageB2TestFaultControllerV1` and `_install_stage_b2_test_fault_controller_for_tests`

## 25. Complete implementation order

1. Add B1 tests for the exact Section 23 signatures, complete callback matrix, synchronous return/exception contract,
   no-republication rules, callback ordering, and prepared retry restart.
2. Implement only the optional B1 callback and retry-predecessor parameters, exact reconstruction, and invocation
   points without changing default behavior.
3. Add the exact StoreError, DurableProgress, DurableExecutionOutcome, closed JSON, hashing, and malformed-input tests.
4. Implement fixed path containment and the exact one-byte Win32 run-wide lock contract.
5. Implement immutable/mutable write protocols and failure tests.
6. Implement the complete fixed-authority run-contract creation/reopen validation, including the LF-canonical
   transport semantic-source hash and recursively closed synthetic snapshot schema version 1.
7. Implement the exact Section 11 journal-wrapper matrix and immutable attempt chain.
8. Implement private commit validation and create-only publication.
9. Implement commit-first reconciliation.
10. Implement exact RQ3 Turn 1 nested checkpoint, Turn 2 consumption, and the dependency-permanent outcome.
11. Implement aggregate-only `DurableProgress.__post_init__`, locked unit-category/lowest-order derivation, and every
    exact public outcome row.
12. Add the fixed runner authority builder and durable fake-only entry points.
13. Add all-four-system and local/Provider integration tests.
14. Add the one private test-fault controller and genuine Windows subprocess lock/crash tests.
15. Run direct Stage B2 tests.
16. Run unchanged Stage A and existing B1 regressions.
17. Run freeze/runtime/baseline regressions.
18. Run non-writing compile checks, git diff --check, and final scope inspection.
19. Obtain independent read-only review before user commit.

## 26. Complete direct-test inventory

### Contract and schema

- Create exact contract; reopen without rewrite.
- Mismatch every authority group independently.
- Field-by-field equality for provider_generation_authority generation, transport, offline_execution, and the complete
  nine-key schema_authority.
- Exact Stage B2 stage ID, synthetic resource digests, resource wrapper hashes, LF-canonical transport implementation
  hash, runtime identity preimage/hash, and every fixed private component ID.
- Transport semantic-source hash: current LF bytes produce
  `464890905866d517bb036569458e6dd69578a2dbacd0eab272c4f0f6ec6fb927`; a semantically identical all-CRLF byte
  sequence produces the same literal; a file with no newline is classified unambiguously and hashes its unchanged
  bytes; mixed LF/CRLF, every lone CR, and BOM insertion fail `STORE_FIXED_AUTHORITY_MISMATCH`; a non-EOL byte mutation
  changes the canonical hash and is rejected; and CRLF conversion changes no byte other than each exact CRLF pair.
- Tamper without rehash and self-consistent foreign rehash.
- Missing/extra top-level and nested fields.
- Duplicate JSON keys, invalid versions, booleans as integers, wrong literal values, and wrong cardinalities.
- Truncated, oversized, non-object, noncanonical, NaN/Infinity inputs.
- Semantically equal reordered JSON is rejected as noncanonical; source map insertion order reconstructs identical
  canonical bytes.
- State present without contract.
- Canonical Unicode serialization and domain-separated hashes.
- Reject either removed redundant hash key as an additional envelope key.
- Synthetic snapshot schema version 1 outer and nested construction order, exact 5/14 cardinalities, exact built-in
  types, strict non-nullability, boolean-versus-integer rejection, fixed literals, exact Turn 1 user/response
  derivations, tracked UTF-8/total-byte bounds, canonical bytes, snapshot hash, B1 checkpoint hash binding, and
  validator callable identity.
- Field-by-field snapshot mutation covers every outer field and every nested `conversation_state` field: missing key,
  additional key, wrong type, wrong nullability, wrong literal, wrong derived value, out-of-bounds text/number,
  integer-as-boolean, boolean-as-integer, negative-zero confidence, reordered durable canonical input, nested mapping
  substitution, snapshot schema-version mutation, and Turn 1/Turn 2 plan/checkpoint/commit identity mismatch.
  Reordered in-memory construction must produce the same canonical bytes; reordered durable envelope bytes remain
  noncanonical.

These fail implementations that trust caller mappings, ignore extra fields, validate only hashes, or silently migrate
versions.

### Containment

- Reject absolute, drive-relative, UNC, extended UNC, URI, traversal, mixed separators, reserved devices, controls,
  and overlong names.

- Reject public root override.
- Reject reparse components and post-creation escape.
- Reject unknown files and noncanonical filenames.

These fail implementations that use resolve() alone, trust caller roots, or derive filenames from untrusted text.

### Atomic persistence

Inject failure:

- Before temp creation
- During partial write
- Before/at flush
- At fsync
- At close
- Before Win32 publication
- After publication but before return
- During readback verification
- During mutable pointer update
- During temp cleanup

Verify old mutable state remains valid, immutable targets are not overwritten, post-publication recovery is
idempotent, and no best-effort fallback occurs.

Lock bootstrap/corruption tests additionally require exact b"\x00" creation and readback, accept an existing valid
one-byte file, and reject zero-byte, multi-byte, wrong-byte, reparse, and replacement-race cases as
STORE_LOCK_FILE_INVALID without repair.

### Commit and reconciliation

- First-success publication.
- Identical replay.
- Conflicting second success.
- Malformed/truncated/foreign commit.
- Journal without commit for every Stage A state.
- Commit without final journal commit.
- Exact committed agreement.
- Conflicting journal/commit fields.
- Missing result with success.
- Provider result missing success.
- Exact local result with null success.
- Lagging mutable pointer repaired from archive.
- Archive fork/gap/conflict rejected.
- Result-before-journal-commit crash recovery.
- Every MutableJournalRecordV1 and AttemptArchiveV1 field is mutated independently for missing, extra, renamed,
  wrong-type, wrong-nullability, wrong-bound, wrong nested-identity equality, wrong public journal hash, and wrong
  Stage B2 self-hash behavior.

### Provider ordering and attempts

- Prepared archive precedes call-started archive.
- Call-started archive and mutable record precede fake call.
- Persistence failure before fake call makes zero calls.
- Exact B1 signatures and keyword order for `journal_persistence_callback` and `retry_predecessor`; exact callback
  argument runtime type and exact `None` return; wrong callback returns raise
  `JOURNAL_PERSISTENCE_CALLBACK_RETURN_INVALID`.
- Callback exception identity and traceback propagate unchanged; callback failures are not converted into executor,
  Provider, transport, journal, retry, or orchestration outcomes.
- Parameterize every Section 23 callback-matrix row and assert exact invocation count, journal argument, synchronous
  completion, and ordering relative to recovery validation, tracker creation, proxy construction/invocation, fake
  call, Provider return, result/checkpoint construction, local/private commit publication, committed reconciliation,
  and public outcome construction.
- Initial/new-retry prepared transitions publish once. Same-attempt continuation, resumed prepared evidence, resumed
  retry evidence, already durable predecessor evidence, local private commit, committed reconciliation,
  dependency-blocked, and direct/dependency permanent paths do not invoke the B1 callback.
- Reconstruct a resumed prepared attempt 2 and 3 only from exact
  `next_retry_journal(retry_predecessor, journal.prepared_at)` equality; test missing, wrong-type, wrong-state,
  wrong-attempt, wrong-timestamp, wrong-identity, and unequal reconstructed predecessors.
- Prove every prepared or call_started persistence failure occurs before Provider tracker begin, proxy invocation, and
  fake-client entry; initial/prepared failure additionally occurs before tracker/proxy construction. No persistence
  failure permits another Provider call.
- Crash after fake call leaves no recall.
- Retryable attempts 1→2→3 with exact archive lineage.
- Retry construction durably publishes prepared and returns retry_constructed with zero calls; the following invocation
  continues the same prepared attempt and exact predecessor.
- Attempt 4 impossible.
- Uncertain and terminal never recall.
- Post-call validation/persistence failures remain non-recallable.
- Local persistence errors never invoke retry classification.

### RQ3

- Turn 1 result/checkpoint single-file atomic publication.
- Restart-safe Turn 2 exact consumption.
- No Turn 1 replay after commit.
- Pair mismatch before store access.
- Checkpoint mismatch with pair otherwise exact.
- Missing/extra/foreign/malformed/resource/runtime/snapshot mutations.
- Turn 2 result binds exact Turn 1 commit.
- Turn 1 not counted before complete commit.
- Exact synthetic snapshot schema version 1 mutation suite from the contract/schema inventory, including all five
  outer fields, all 14 nested fields, fixed/derived equality, deep-detached Turn 2 copy, and rejection before Turn 2
  tracker/proxy/executor/fake-client action.
- Explicitly selected dependent Turn 2 whose Turn 1 is directly permanently non-executable returns action
  `permanently_non_executable`, block_category `"dependency_permanent"`, selected Turn 2 identity/order, null
  attempt/journal/commit/B1 outcome, and zero callbacks/Provider calls.
- Scheduler derivation classifies that Turn 2 as permanent, skips it, selects any lower-order-authoritative eligible
  unit, or returns global no_eligible when none exists. Reopen preserves the same category without constructing an
  attempt or journal.
- Mutate the dependency-permanent row to every direct blocker category and mutate each required-null attempt,
  journal, commit, or orchestration field to non-null; direct dataclass construction rejects each mutation.
- A Turn 1 that is initially executable, same-attempt continuable, or retry constructible keeps Turn 2
  `dependency_blocked`/`"dependency_missing"` and never yields `"dependency_permanent"`.

### Progress and system coverage

- Total/per-RQ/per-system/remaining values.
- Next eligible order with blocked and retryable states.
- Exact 12-field DurableProgress signature, exact types.MappingProxyType detached count maps, integer bounds, partition
  equations, all four run_state rows, nullability, and wrong/extra-field construction cases.
- Independently mutate every Section 21 aggregate equation: `S + R = 190`, each successful-map sum equals `S`,
  `I + C + Y + D + P = R`, and `S + I + C + Y + D + P = 190`. Reject negative and over-190 counts and every per-RQ or
  per-system bound violation.
- For each status reject inconsistent eligible counts and wrong null/non-null next order. Reject permanently_blocked
  with any nonzero initial/continuable/retry count, `P = 0`, `S = 190`, or an unclassified remainder. Reject complete
  with `S != 190` or any nonzero non-complete category.
- Locked-factory tests supply durable evidence whose derived unit assignments would overlap, omit a category, contain
  an unknown unit, or disagree with aggregate counts, and require failure. A separate evidence input has multiple
  eligible units and makes a non-lowest order eligible; the factory must still return the exact lowest order, and a
  result proposing the other eligible order is rejected by the factory-level assertion even though direct
  `DurableProgress` construction can validate only aggregate consistency.
- Exact lowest-order selection is tested across simultaneous initial-executable, same-attempt-continuable, and
  retry-constructible units. Factory status precedence is complete, then in_progress when any eligible unit exists,
  then permanently_blocked when `P >= 1`, otherwise temporarily_blocked with `D = R`.
- Exact 11-field DurableExecutionOutcome signature and every action row, block vocabulary, B1 embedding condition,
  provider-call count, nullability, cross-field invariant, and wrong/extra-field construction case.
- unit=None returns only no_eligible or run_complete when its exact progress invariant holds.
- StoreError accepts every one of its 22 exact categories, rejects every other string/type, stores only category, and
  maps every enumerated failure condition to the exact category without raw details.
- No mutable counter authority.
- Identical replay counted once.
- Physical duplicate blocks rather than double-counting.
- Representatives of all four formal systems.
- Provider-backed and local success for each system; context Turn 2 uses exact Turn 1.
- Every local success makes zero fake-client calls.
- Early rejection imports no runtime, core, baseline, SDK, dotenv, or client module.
- Network socket guard remains unused.

### Required correction coverage

- Parameterized missing, extra, renamed, wrong-type, boolean-as-integer, and null mutations for every newly enumerated
  nested key set: nine-key run contract, eight-key plan authority, both count maps, six frozen-input keys, four formal-
  system entries, three-key provider-generation authority, generation/transport/offline-execution subobjects,
  three-key runtime-resource authority, four resource wrappers, all 18 resource-identity fields, and nine-key schema
  authority.

- Exact key-set and cardinality mutations for 6 frozen inputs, 4 formal systems, 4 resources, 3 RQ counts, 4 system
  counts, 190 plan members, every fixed snapshot, and every fixed identifier. For each mapping persisted to disk,
  reordered bytes fail noncanonical validation; reordering the in-memory source map yields the same canonical bytes.

- Independently mutate each fixed corpus hash, embeddings hash, public resource-identity hash, generation/transport
  ID/hash/snapshot field, runner generation hash, offline component ID, LF-canonical transport implementation hash, runtime
  preimage member/hash, schema version, and stage ID. Self-consistent foreign recomputation still fails exact authority
  comparison before durable-state access.

- Path mutations covering drive-absolute, drive-relative, UNC, device, root-relative, URI-like, traversal, backslash,
  mixed separator, doubled separator, percent-encoded, alternate-case, over-240-byte path, over-128-character
  component, and otherwise noncanonical frozen/resource paths.

- For each durable file category, accept exactly the encoded-byte limit and reject one byte over before JSON parsing.
- Accept depth 16 and reject 17; accept a 262,144-byte UTF-8 string and reject 262,145; accept 128 mapping members and
  reject 129; accept 256 array members and reject 257; accept the permitted filename/component maxima and reject one
  over.

- Parameterized discriminator tests for every provider/local authoritative-success and Provider-evidence null
  mutation; every attempt-1 and attempt-2/3 predecessor mutation; and every none, single_turn, context_turn_one, and
  context_turn_two relationship null/non-null mutation.

- For every Stage B2 hash, mutate its domain, payload member name, payload value, or excluded self-field treatment and
  require rejection after recomputation. Confirm Stage A/B1-owned hashes are validated by their existing public
  functions and are not accepted under a Stage B2 replacement domain. Confirm no execution-identity or authoritative-
  success hash field is accepted or calculated.

- Parameterize every row in the Section 11 wrapper matrix for attempts 1, 2, and 3. Cover sequence start/increment/max,
  previous-link first/subsequent rules, predecessor nullability, exact nested-ID equality, latest-tip equality,
  Provider/local commit-pointer nullability, repeated prepared local publication, committed reconciliation, every
  permitted transition, and every explicitly forbidden transition. For every repair row, assert the exact archive and
  mutable write count and resulting tip.

- Archive event tests cover every valid event/state pair plus every mismatch; event = "committed" requires the exact
  public reconciled journal and matching commit. Local completion remains event = "prepared".

- Progress tests for initial execution, same-prepared-attempt continuation, retry creation after attempts 1 and 2,
  dependency-blocked Turn 2, validated success, each permanently non-executable state, and lowest-order selection
  across mixed categories.

- Public-signature tests rejecting resources, both claimed hashes, snapshot_validator, executor/client/clock
  injection, and store-root overrides.

- Private authority-comparison tests show that a foreign resource, foreign matching resource hash, foreign
  transport/runtime hash, foreign fixed ID/type/callable, or mutually self-consistent combination fails before lock
  acquisition and durable-state access. No public durable call accepts the candidate.

- Test-controller unit tests cover every exact fault point, invalid point, production-root rejection, non-temporary
  root, second installation, non-fixed fake type, exact marker schema/bytes, create-only collision, restoration to None,
  and the prohibition on response/identity mutation. Genuine crash behavior remains in Section 27 subprocess tests.

## 27. Genuine Windows subprocess-test inventory

### Sole private test-fault mechanism

The only subprocess fault mechanism is module-private
formal_evaluation_store._StageB2TestFaultControllerV1. It is a frozen dataclass with exactly these fields in order:

schema_version: int
root: Path
fault_point: str

schema_version is integer 1, not boolean. root must equal the currently patched private store root. fault_point is
exactly one of:

after_call_started_published_exit
after_fake_client_returned_mark
after_fake_client_returned_exit
after_private_commit_published_exit
after_committed_archive_published_exit

The module global `_STAGE_B2_TEST_FAULT_CONTROLLER` is exactly None on import and in all normal execution. Tests install
one exact controller only through
`_install_stage_b2_test_fault_controller_for_tests(root: Path, fault_point: str)`. That private context manager:

1. requires exact argument types and vocabulary;
2. requires the active private-root constant to equal root;
3. requires root to differ from immutable `_PRODUCTION_PRIVATE_STATE_ROOT`;
4. requires root to be contained under pathlib.Path(tempfile.gettempdir()).resolve(), outside the repository root,
   with no existing reparse component;
5. requires the exact fixed runner fake-client, executor-registry, clock, and snapshot-validator identities;
6. rejects a second installed controller;
7. installs the controller for the context and restores the global to None in finally.

Any failure raises STORE_TEST_FAULT_INVALID before durable-state access. A non-null controller with the production root
also raises STORE_TEST_FAULT_INVALID before lock acquisition. No public function accepts a controller or fault point.
Tests may patch only the private root and install this named controller; arbitrary fake dependency, clock, validator,
store path, persistence primitive, or Provider monkeypatching remains forbidden.

Markers are written outside the store at the fixed sibling directory:

root.parent / ".stage_b2_fault_markers"

The filename is exactly "marker-" plus the current positive decimal PID, "-" plus fault_point, and ".json". The marker
is create-only canonical UTF-8 JSON plus LF, is flushed and fsynced, and has exactly these eight keys:

schema_version: integer 1
fault_point: one exact value above
pid: positive integer, not boolean
execution_unit_id: lowercase SHA-256
attempt_number: integer 1..3, not boolean
archive_sha256: lowercase SHA-256
private_commit_sha256: lowercase SHA-256 or null
provider_call_count: integer 0 or 1, not boolean

The marker contains no query, response, prompt, resource content, exception, credential, or path. A pre-existing marker,
invalid marker directory, write/readback failure, or schema mismatch raises STORE_TEST_FAULT_INVALID rather than
continuing. The marker directory is not under private_state and therefore is not store authority.

The exact hook behavior is:

- after_call_started_published_exit: immediately after the call_started archive and matching mutable record pass
  readback, before tracker begin, proxy invocation, or fake-client entry. Marker archive_sha256 is that call_started
  tip, private_commit_sha256 is null, provider_call_count is 0; after marker readback call os._exit(90).
- after_fake_client_returned_mark: inside `_FixedFakeRawClientV1`, immediately after incrementing its call count and
  constructing the closed raw response, before returning it to FixedGenerationProxy. The durable tip is still
  call_started, commit is null, call count is 1; write/verify the marker and continue normally.
- after_fake_client_returned_exit: the same exact point and fields, then os._exit(91). No provider_returned archive can
  be written.
- after_private_commit_published_exit: immediately after create-only commit publication and exact readback, before a
  local pointer archive or Provider reconciliation. Marker references the current prepared/provider_returned archive,
  the non-null envelope hash, and invocation call count 0 or 1; then os._exit(92).
- after_committed_archive_published_exit: Provider only, immediately after sequence-4 committed archive publication and
  readback, before mutable-record replacement. Marker references that archive and commit, with invocation call count 0
  or 1; then os._exit(93).

No other subprocess fault point is required or permitted. The controller can only mark or terminate; it cannot replace
responses, alter clocks, change identities, suppress validation, construct a client, or request another call.

The parent polls the one expected marker path every 50 milliseconds for at most 10 seconds, validates exact bytes,
schema, PID, selected execution unit, attempt, hashes, and expected call count, then waits for the exact exit code.
Mark-only races wait for both workers to finish and require exactly one valid marker across their two PIDs. Cleanup
occurs only after all worker handles close and removes only the OS-temporary parent created by the test fixture; no
repository or production path is removed.

### Exact subprocess cases

1. Competing lock: worker A holds the valid one-byte OS lock; worker B gets bounded STORE_LOCK_BUSY.
2. Exactly one call: two workers patch the same temporary root, install after_fake_client_returned_mark, and race the
   same public durable unit. Exactly one marker, one fake call, one valid commit, and two completed/idempotent outcomes
   result.
3. Normal release: first worker exits its lock context; second immediately acquires.
4. Forced termination: parent terminates a lock holder; second acquires while the exact b"\x00" lock file remains.
5. Stale valid file: pre-create exact b"\x00" run.lock with no held byte lock; acquisition succeeds.
6. Corrupt lock files: zero-byte, two-byte, and one-byte nonzero files each fail STORE_LOCK_FILE_INVALID without
   replacement.
7. Pre-call conservative crash: worker exits 90 after durable call_started. Reopen validates call_started, performs
   zero fake calls, returns permanently_non_executable with block_category "call_started", and preserves the chain.
8. Post-call ambiguity: worker exits 91 after one fake-call marker but before post-call persistence. Reopen sees only
   call_started, performs zero additional calls, returns permanently_non_executable, and preserves exactly one marker.
9. Post-commit crash: worker exits 92 after Provider commit publication. Reopen validates the provider_returned tip and
   commit, appends/reuses committed reconciliation with zero calls, and returns completed.
10. Local post-commit crash: worker exits 92 after local commit publication. Reopen validates prepared plus commit,
    appends/reuses the repeated prepared pointer archive with zero calls, and returns completed.
11. Committed-archive pointer crash: worker exits 93 after the committed archive but before mutable replacement. Reopen
    advances only the mutable pointer, makes zero calls, and returns completed.
12. First-contract race: two workers use fixed authority; only one create-only publication occurs; the other reopens
    the identical contract or receives STORE_LOCK_BUSY. Exactly one canonical contract remains and no non-lock durable
    state exists without it.

Every worker uses only fixed synthetic identities and fixed fake types. No network, SDK, real client, Provider,
production resource, repository output path, row-level terminal output, canary, or formal response is reachable.

## 28. Required regression suites

Future implementation commands should use the repository .venv, disabled plugin autoload, no bytecode in the
repository, and no pytest cache:

.\.venv\Scripts\python.exe -m pytest scripts/test_formal_evaluation_store.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest scripts/test_formal_evaluation_orchestration.py scripts/test_run_formal_evaluation.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest scripts/test_formal_evaluation_transport.py scripts/test_formal_evaluation_inflight.py -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest scripts/test_formal_evaluation_freeze.py scripts/test_formal_evaluation_runtime.py scripts/test_formal_qa_only_baseline_adapter.py -q -p no:cacheprovider

Existing tests must not be deleted, weakened, or reclassified. Stage A implementation and tests remain byte-unchanged.

Current planning review:

- Test commands run: none
- Test pass count: not applicable
- py_compile: not run because implementation was forbidden
- Python, imports, compilation, and non-writing AST parsing: not run during this documentation-only revision.

## 29. Stage B2 acceptance criteria

Stage B2 passes only if:

- Changes are confined to the six-file allowlist.
- Every schema is recursively closed and version-exact.
- Run contract is immutable and exact on reopen.
- A run-wide Windows lock covers the entire decision/write/fake-call lifecycle.
- call_started is durable before every fake call.
- Exactly one fake call occurs across competing processes.
- Provider post-call ambiguity never recalls.
- Private commit precedes Provider journal commit.
- Valid commit without final journal commit reconciles without a call.
- First success is create-only and conflicting success preserves the first.
- Attempts and Provider IDs remain exclusively Stage A-derived.
- Turn 1 result/checkpoint is atomic and Turn 2 never reconstructs Turn 1.
- Synthetic snapshot schema version 1 is recursively closed by the exact Section 9 five-key outer and 14-key
  `conversation_state` definitions, fixed/derived values, strict types/nullability/bounds, canonical bytes, validator
  category, and Turn 2 equality rules.
- Transport implementation identity is derived only by the Section 9 LF-canonical semantic source algorithm; LF and
  consistently CRLF checkouts agree, while BOM, lone CR, mixed EOL, and non-EOL mutation fail the frozen category.
- A Turn 2 whose required Turn 1 is permanently non-executable is represented only by action
  `permanently_non_executable` and block_category `"dependency_permanent"` with the exact Section 21 nullability and
  zero-attempt/call/callback behavior; it is not a direct journal-state blocker.
- B1 uses only the exact Section 23 callback and retry-predecessor signatures, invokes callbacks synchronously at the
  exact transition points, propagates persistence exceptions unchanged, and never republishes resumed prepared or
  predecessor evidence.
- Progress success counts derive only from validated commits; eligibility/blocking derives only from the exact validated
  wrapper matrix.
- `DurableProgress.__post_init__` proves only the complete aggregate equations/status implications, while the locked
  factory proves exactly-one unit categories and the lowest eligible execution order.
- No public arbitrary-root, mutable-counter, journal, or attempt authority exists.
- No runtime/core import occurs on rejected early paths.
- All specified regressions and subprocess tests pass.
- Real gate remains unconditionally blocked.
- No reviewer artifact, production loader, .env access, real-client construction, network access, canary, or formal
  response is introduced.

Additional frozen acceptance criteria:

- every Stage B2 durable JSON category enforces its exact byte limit and the common recursive depth, string, mapping,
  array, filename, and fixed-cardinality limits;

- the run contract has exactly nine top-level keys and exact stage/schema literals; its provider-generation,
  schema-authority, six-key frozen-input, four-key formal-system, and four-key synthetic-resource maps are recursively
  closed and freshly reconstructed from their named public or Stage B2-owned authority;

- every fixed corpus/embeddings/resource hash, generation/transport snapshot and ID/hash, offline component ID,
  LF-canonical transport implementation hash, runtime preimage/hash, and schema version equals its Section 9 literal;

- every Stage B2-owned hash uses its specified domain and excluded self-field, while Stage A/B1-owned hashes are
  reused without redefinition; no nonexistent public Stage A hash is claimed;

- every private-envelope discriminator and nullability rule is exact and recursively closed;
- every wrapper row, sequence, predecessor, previous link, commit pointer, permitted transition, forbidden transition,
  and archive-tip repair follows the one Section 11 matrix;
- archive event is only the exact derived copy of validated Stage A journal state and never becomes transition or
  recovery authority;

- progress distinguishes initial execution, same-attempt continuation, Stage A-derived retry creation, dependency
  blocking, validated success, direct permanent fail-closed state, and dependency-permanent Turn 2 state;

- DurableProgress, DurableExecutionOutcome, and StoreError have their exact closed Section 21/24 fields, vocabularies,
  nullability, bounds, and cross-field invariants;

- no public API accepts resource, validator, implementation/runtime hash, dependency-bundle, or store-path authority;
- all fixed dependency validation occurs before lock acquisition and before durable-state access;
- apart from the exact Section 12 fixed lock-infrastructure bootstrap, the acquired run-wide lock precedes every
  application contract/durable-state inspection, creation, cleanup, validation, repair, reconciliation, and
  publication;

- simultaneous first-contract creation cannot produce competing contracts or allow durable state without the one fixed
  contract;

- run.lock is exactly b"\x00"; zero-byte, multi-byte, and wrong-byte files fail STORE_LOCK_FILE_INVALID without repair;

- the only subprocess fault mechanism is the exact Section 27 private controller, is disabled for production, is
  restricted to a patched OS-temporary root and fixed fake types, and satisfies every marker/crash/reopen case.

## 30. Explicit B3, B4, and B5 exclusions

Not Stage B2:

- Public rating/scoring files
- Blinded reviewer outputs
- Reviewer identity mapping
- Human-scoring workflows
- Immutable-after-scoring policy
- Production resource loading or preflight
- Cache, corpus, embedding, model, .pkl, or .npy access
- Production resource manifest creation
- .env access
- DeepSeek/OpenAI-compatible client construction
- Network access
- Real-execution authorization
- Real mode or canary
- Formal model generation
- Frozen research, plan, mapping, or generation changes

Later classification:

- Stage B3: blinded reviewer-output projection from canonical private commits.
- Stage B4: offline production-resource preflight.
- Stage B5: restart-safe real authorization protocol and eventual guarded real-client integration.

## 31. Planning-document path and freeze status

Canonical path:

docs/evaluation/formal_evaluation_stage_b2_plan.md

Status: **Frozen plan  not implemented; independent review pending.**

This documentation-only freeze is not part of the six-file Stage B2 implementation batch.

## 32. Recommended future implementation commit message

feat(eval): add durable formal state and process-safe recovery

The user remains responsible for staging, committing, and pushing.

## 33. Recommended implementation model

GPT-5.6 Sol — High reasoning

Use one narrow implementation batch with the exact allowlist and no real-mode authorization.

## 34. Recommended independent-review model

GPT-5.6 Sol — xhigh reasoning, in a fresh strictly read-only review session.

The review should independently verify lock timing, archive-tip recovery, create-only publication, local-success
handling, prepared retry restart, RQ3 checkpoint binding, and absence of Stage A private access.

## 35. Final safety and repository confirmation

The following records the documentation-only plan revision completed before renewed independent review.

Final confirmation:

- Repository files created: none
- Repository files modified: docs/evaluation/formal_evaluation_stage_b2_plan.md only
- Tracked repository file changed: no
- Staged, committed, or pushed: no
- Network or Provider API used: no
- .env, credentials, secrets, or tokens read: no
- Production cache/resource/model/embedding/corpus accessed: no
- Frozen row-level Gold/RQ2/RQ3 questions, answers, payloads, reviewer data, or results accessed: no
- Permitted tracked Stage A/B1 source and synthetic tests inspected: yes
- Row-level content printed: no
- Real client created: no
- Real mode run: no
- Canary run: no
- Formal response generated: no
- Formal execution started: no
- data/formal_eval/ written: no
- git diff --check: passed
- git diff --cached --check: passed
- Final git status --short --untracked-files=all:
  ?? docs/evaluation/formal_evaluation_stage_b2_plan.md
- Remaining blocked stages: B3, B4, B5, real execution, canary, and formal generation remain outside scope and
  unauthorized.
