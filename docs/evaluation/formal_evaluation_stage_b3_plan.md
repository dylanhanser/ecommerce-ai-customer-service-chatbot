# Stage B3 — Blinded Reviewer-Output Projection

**Status: Approved and frozen implementation contract — not implemented.**

Approval and freeze metadata:

- Independent review classification: `STAGE_B3_PLAN_REVIEW_PASS`
- Independent review verdict: `PASS`
- Exact reviewed-source SHA-256: `7b2e92aa86ea67991c555c432c2a2c8de9f2065314d8af1ff5dc4825202fbccf`
- Approval/freeze date: `2026-08-11`

This approval applies to the exact independently reviewed substantive contract. Only approval/freeze metadata in this
document and the path-specific checkout-reproducibility rule in `.gitattributes` are changed after review; no
substantive contract text is changed. Stage B3 implementation requires a separate explicitly authorized task. B4, B5,
formal execution, Provider access, scoring, adjudication, and reviewer operation remain unauthorized.

## 1. Decision and scope

### 1.1 Objective

Stage B3 has one objective:

> Deterministically project blinded, reviewer-facing evaluation inputs from validated canonical Stage B2 private
> commits, while preserving the frozen request membership and research identity and without redefining authoritative
> success.

The projection is a local, offline, single-user operation. It is deliberately smaller than a production publication
platform. Its required safeguards are closed schemas, strict input validation, deterministic blinding, private/public
separation, create-only atomic file publication, safe reopen behavior, and tests proving that no Provider-capable path
is reachable.

### 1.2 In scope

Stage B3 includes only:

- a narrow read-only Stage B2 observation boundary that reuses the implemented canonical private-commit validator;
- an explicit source-eligibility gate over the freshly reconstructed authoritative run contract before any Stage B2
  commit observation or B3 output-root access;
- complete-set validation for the frozen 190 request units;
- deterministic reviewer IDs, reviewer ordering, and the existing deterministic RQ1 secondary-review selection;
- four reviewer-facing JSON data artifacts and one reviewer-facing integrity manifest;
- one separate private mapping/provenance manifest needed for later unblinding;
- fixed ignored output paths, create-only atomic publication, idempotent reopen, and bounded local resume;
- synthetic offline verification plus the existing Stage A, B1, and B2 compatibility suites.

### 1.3 Non-goals

Stage B3 does not:

- decide whether execution succeeded or create a success predicate;
- choose among competing outputs, attempts, timestamps, journals, or Provider returns;
- replace, weaken, copy, or independently approximate Stage B2 private-commit validation;
- repair, rewrite, reconcile, or guess missing private execution evidence;
- invoke an executor, core system, model, transport, client, SDK, endpoint, or Provider;
- recall a Provider, regenerate a response, replay RQ3 Turn 1, or reconstruct a checkpoint;
- read `outputs/.env`, credentials, production caches, corpora, embeddings, models, or arbitrary output state;
- make reviewer output authoritative private execution state;
- permit reviewer output or a private mapping to resume model execution;
- alter the request plan, request IDs, execution order, fingerprint, systems, prompts, generation settings, fixtures,
  scoring rules, acceptable-response rules, or statistical-analysis plan;
- conduct human scoring, assign people to reviewer roles, manage reviewer identities, adjudicate, or analyse results;
- define an immutable-after-scoring policy or a scoring-result schema;
- implement Stage B4 production-resource preflight or Stage B5 real authorization and guarded client integration;
- authorize canary, real mode, formal generation, or any network access.

B4, B5, canary, real execution, formal generation, reviewer scoring, adjudication, and statistical analysis remain later
and separately authorized work.

The implemented Stage B2 authority is currently fixed to `offline_fake_only` with synthetic resources. It can support
offline infrastructure verification, but it cannot produce a successful production reviewer projection. Successful
production projection remains unavailable until separately governed later B5-era work establishes a validated
non-synthetic run authority. This statement neither authorizes nor implements B5; B3 may still be implemented and
verified as offline infrastructure before that later authority exists.

## 2. Planning baseline and authority hierarchy

### 2.1 Verified planning baseline

This approved and frozen contract is based on the following verified repository identity:

- branch: `main`;
- `HEAD`, local `main`, and local `origin/main`:
  `26c0ae5628f387c9ee3c5af415acfacd4734784b`;
- subject: `feat(eval): implement Stage B2 durable execution store`;
- local ahead/behind: `0/0`;
- Stage B2 plan SHA-256:
  `7bfb39de93701854a1a883d96de94015236ca88a2304d9ccb6faac14072e8435`;
- Stage B2 fault-injection amendment SHA-256:
  `ab2c7c91b479ec5181d9ce01c7286240ca46a8991f75478096c288f6005fdbb9`;
- current Stage B2 run-authority mode: `offline_fake_only`, with every current
  `runtime_resource_authority.resources[*].resource_identity.synthetic` value equal to `true`;
- formal execution state recorded by the governing authorities:
  `formal_model_responses = 0`, `real_execution_started = false`, and `execution_not_started = true`.

No remote refresh is implied by the local `origin/main` verification.

### 2.2 Precedence

The implementation and review must apply the following precedence:

1. the user's current explicit task and any separately authorized implementation task;
2. repository `AGENTS.md`;
3. `docs/evaluation/formal_evaluation_protocol.md`;
4. `docs/evaluation/formal_evaluation_pre_execution_amendment.md`;
5. `docs/evaluation/formal_evaluation_baseline_identity_correction_amendment.md`;
6. `docs/evaluation/formal_evaluation_execution_guide.md`, as corrected by the amendments;
7. `docs/evaluation/formal_evaluation_stage_b2_pre_execution_amendment.md`, where it expressly supersedes Stage B2
   fault-injection text;
8. `docs/evaluation/formal_evaluation_stage_b2_plan.md` for all non-superseded Stage B2 contract requirements;
9. the implemented Stage B2 production interfaces at commit
   `26c0ae5628f387c9ee3c5af415acfacd4734784b`;
10. this exact independently reviewed, approved, frozen, and separately published Stage B3 contract.

The current task's statement that Stage B2 implementation, correction, independent review, local commit, and push are
complete controls over the older historical status line in the Stage B2 plan. The Stage B2 contract remains the design
authority for the implemented interfaces.

If implementation behavior conflicts with a higher authority, B3 must stop. It must not make the implementation
conform by changing frozen research behavior, accepting an alias, suppressing a validator, or introducing a new
research rule.

### 2.3 Boundaries B3 cannot alter

Stage B3 cannot redefine or infer any of the following:

- authoritative success;
- create-only first success;
- retry eligibility or attempt lineage;
- terminal, uncertain, retryable, or committed state;
- Provider ownership, Provider call count, or Provider success;
- local-success validity;
- RQ3 checkpoint validity or Turn 1/Turn 2 dependency identity;
- `system_config_id`, `formal_system_id`, or `specification_path`;
- plan membership, request identity, or execution order.

An implementation finding that would require one of these changes is not a B3 issue. It is a blocking authority
conflict requiring a separately governed pre-execution correction.

## 3. Stage B2 interfaces consumed

### 3.1 Existing validation authority

The future B3 implementation must reuse these existing authorities through a narrow wrapper:

- runner `verify_frozen()`, `validate_plan()`, `plan_fingerprint()`, `build_plan()`, and
  `build_durable_run_contract()`;
- the Stage B2 fixed private root and run-wide lock;
- Stage B2 strict canonical JSON loading and run-contract equality;
- Stage B2 archive and mutable-record validation;
- `_load_unit_state_locked(..., repair_mutable=False)` for read-only state observation;
- `_load_commit_for_unit_locked()` and `_validate_private_commit()` for the canonical envelope;
- `_validate_known_store_members()` for foreign or duplicated durable members;
- the public Stage A `ExecutionIdentity`, `AuthoritativeSuccess`, and B1 checkpoint validators already called by
  `_validate_private_commit()`;
- public `project_formal_result()`, already re-applied by the Stage B2 commit validator.

The underscore-prefixed functions remain implementation details. B3 must not import them directly. The allowed Stage
B2 and runner modifications in Section 11 wrap them in one read-only observation API; the validator bodies and success
rules are reused, not copied into the B3 module.

The following are not B3 inputs:

- legacy `responses.jsonl`, execution events, legacy checkpoints, run manifests, or `templates()` output;
- a `DurableExecutionOutcome` supplied by a caller;
- reviewer artifacts or an earlier private reviewer mapping;
- an archive event label or mutable journal pointer by itself;
- raw Provider responses, SDK objects, tracker objects, exceptions, prompts, or retrieved documents;
- the Stage B2 test fault controller, installer, or 50-field test observation accessor.

The Stage B2 test controller and observation objects stay module-private, temporary-test-root-only, and inactive in
normal execution. B3 cannot activate, inspect, serialize, expose, or depend on them.

### 3.2 Proposed read-only observation DTO

The future implementation adds one frozen, detached DTO in `formal_evaluation_store.py`:

```python
@dataclass(frozen=True, slots=True)
class CanonicalPrivateResultV1:
    schema_version: int
    plan_fingerprint: str
    run_contract_sha256: str
    plan_member_sha256: str
    execution_unit_id: str
    execution_order: int
    request_id: str
    rq: str
    case_id: str
    dialogue_id: str | None
    turn_index: int
    system_config_id: str
    formal_system_id: str
    envelope_sha256: str
    response_text: str
    response_sha256: str
    rq3_relationship_kind: str
    turn_one_commit_sha256: str | None
    checkpoint_record_sha256: str | None
```

It contains only the fields B3 needs for mapping, display, identity proof, and RQ3 relationship proof. It does not
contain Provider names, Provider IDs, timestamps, attempt metadata, prompts, retrieved data, resource paths, raw
checkpoint content, or exceptions.

Every field is copied only after the complete private envelope has passed the existing Stage B2 validator. The DTO
does not itself validate success and cannot be constructed from an unvalidated result in the production path. Nested
or mutable input is not retained.

The exact future runner interface is:

```python
def observe_validated_canonical_private_results(
    plan: list[dict[str, Any]],
) -> tuple[CanonicalPrivateResultV1, ...]:
    ...
```

It accepts no store root, output path, subset, request ID, attempt, journal, commit, repair flag, client, executor,
transport, resource, clock, callback, Provider, or force option. It:

1. verifies the frozen authorities and exact plan;
2. reconstructs the exact Stage B2 run contract;
3. opens an already-existing private store under the existing run lock in read-only observation mode;
4. creates no root, lock file, contract, directory, archive, journal, commit, or cleanup write;
5. validates every known durable member;
6. loads unit state with `repair_mutable=False`;
7. validates any canonical commit through the existing complete private-commit path;
8. returns the validated results in source `execution_order`.

The focused B3 test contract does not change this signature. It patches the existing module-private Stage B2
`_PRIVATE_STATE_ROOT` to its validated temporary B2 root before invoking this production observation seam, as specified
in Section 8.3.

The private read-only store context must require the fixed root, `run.lock`, `run_contract.json`, and fixed directories
to exist before opening. A private `create_missing=False` lock/open mode may be added with existing callers retaining
their current default behavior. Observation must not call `_open_store()`, because `_open_store()` can create a
contract, clean temporary files, and repair mutable state.

The observation API may return fewer than 190 DTOs only to represent valid absence without inventing a success. Stage
B3 itself rejects that snapshot as incomplete before creating an output directory. Malformed or contradictory state
raises the original sanitized `StoreError`; B3 does not turn it into an absent row.

### 3.3 Source-eligibility gate

After `verify_frozen()`, exact plan validation, and fingerprint/count verification, B3 must freshly call
`build_durable_run_contract(plan)` and validate the returned authoritative contract before it calls
`observe_validated_canonical_private_results(plan)`. The B3 gate reads only these already-validated contract members:

- `provider_generation_authority.offline_execution.mode`; and
- each of the four exact
  `runtime_resource_authority.resources[system_config_id].resource_identity.synthetic` values.

There is exactly one source-ineligibility classification: `B3_SOURCE_INELIGIBLE`. The gate returns that category if
either the run-authority mode is exactly `offline_fake_only` or any exact built-in `bool` `synthetic` value is `true`.
Both predicates still produce the same one category. Missing, wrong-typed, additional, or otherwise malformed contract
structure must already fail the governing run-contract validation; B3 must not guess a mode or synthetic status.

The gate is fail-closed and runs before B3 invokes or accepts the Stage B2 observation result, resolves or probes the
B3 output root, acquires its lock, creates a directory, or inspects any B3 artifact. On `B3_SOURCE_INELIGIBLE`, B3 must
not reinterpret synthetic evidence as formal evidence, read or repair the Stage B2 commit set for projection, recall a
Provider, regenerate a response, create a temporary or final B3 artifact, touch the reviewer-output root, or begin
B4/B5 behavior.

The current fixed Stage B2 contract necessarily fails this gate, even if its temporary or production-shaped private
store contains a complete validated 190-unit synthetic commit set. Successful production projection therefore remains
blocked pending a separately governed, validated non-synthetic run authority from later authorized B5-era work. B3
implementation and offline verification remain useful before then. Fully offline tests may use test-owned,
structurally valid eligible-contract fixtures to exercise the post-gate projection success path, but those fixtures and
their artifacts are synthetic test evidence only and must never be treated, stored, named, or reported as formal
evaluation results.

## 4. Canonical input contract

### 4.1 Eligible private records

A unit may be projected only when all of these conditions hold:

1. it is one complete, exact member of the validated frozen plan;
2. its expected canonical path is
   `data/formal_eval/private_state/commits/<execution_order>-<execution_unit_id>.json`;
3. that file is the unique canonical file for the unit;
4. its canonical bytes, closed schema, run-contract binding, envelope hash, plan-member binding, execution identity,
   attempt lineage, result hash, response hash, and path all validate;
5. its nested formal result revalidates through public `project_formal_result()` and equals the stored canonical
   projection;
6. Provider success, when present, revalidates through public `AuthoritativeSuccess`; local success has null Provider
   evidence and `provider_called = false` exactly as Stage B2 requires;
7. its RQ3 relationship, if any, passes the complete existing B1/Stage B2 checkpoint and pair validation;
8. no foreign, duplicated, forked, off-chain, contradictory, malformed, or unknown private evidence exists anywhere
   in the fixed store.

An archive, journal, result dictionary, response string, reviewer file, or legacy response row cannot satisfy these
conditions by itself.

The validated `system_config_id` remains dispatch/classification identity; `formal_system_id` remains success and
provenance identity; a `specification_path` remains only a frozen-resource lookup. The observation DTO copies the first
two only after Stage B2 agreement validation. B3 accepts no path alias, derives no identity from a path, and exposes
none of the three to a reviewer.

### 4.2 Canonical-success selection

There is no B3 selection heuristic. For each exact plan member, the only possible source is the valid immutable
create-only Stage B2 commit at the expected path. The existing first valid canonical commit remains the first success.

B3 must never select:

- the newest or oldest timestamp;
- the highest attempt number;
- a `committed` event without its commit;
- a Provider return without its commit;
- a second file with the same request ID;
- a response from a mutable record, archive, stdout, log, reviewer artifact, or old JSONL file;
- a value that merely has a matching response hash;
- an alternate valid-looking envelope under another filename.

An identical validated reopen of the one expected commit is the same success, not a second record. A different valid
envelope, malformed occupant, duplicate path, foreign member, or contradictory journal/commit relationship blocks the
entire projection.

### 4.3 Absence, incompleteness, and repairable lag

Stage B3 requires a complete validated snapshot of all 190 canonical private commits. It has no subset, preview,
incremental-review, or `allow_partial` mode.

- Zero or any number fewer than 190 valid canonical commits is `B3_INPUT_INCOMPLETE`.
- Missing context-aware RQ3 Turn 1 or Turn 2 is incomplete, even if the other turn exists.
- A valid canonical commit with a Stage B2-recognized repairable mutable-pointer lag remains a Stage B2 success. The
  observation path may validate and project it without repairing the pointer.
- Recognized abandoned Stage B2 temporary files are non-authoritative. Observation neither deletes them nor derives a
  result from them. If the existing B2 validator cannot establish a unique canonical commit without cleanup, B3 stops.
- Malformed or contradictory private state is not incompleteness and must not be silently omitted. The original
  `StoreError` blocks projection.
- B3 cannot invoke an execution or recovery API to fill a gap. Operator action, if any, is outside B3 and requires its
  own authority and no-recall analysis.
- A gap associated with `call_started`, `provider_returned` without a commit, `uncertain`, terminal failure, exhausted
  attempts, or a permanently failed RQ3 dependency retains its exact Stage B2 non-executable classification. B3 never
  turns that gap into retry eligibility.

No reviewer or private projection directory may be created until the complete input snapshot and all in-memory output
schemas have validated.

### 4.4 RQ-specific representation

RQ1 input consists of 102 validated commits: 51 complete cases, each with the exact
`qa_only_reconstructed_baseline` and `v2` member. The display question is the exact validated plan input. The reference
answer is joined by the unique exact `review_id == case_id` from the frozen Gold-51 file, and the Gold question must
equal the validated plan `payload.user_input` byte-for-byte as a Unicode string. The Gold file must contain exactly 51
unique joined identities. Missing, duplicate, unmatched, extra, or text-mismatched Gold identity is
`B3_REFERENCE_INVALID`.

RQ2 input consists of 40 validated commits: 20 complete cases, each with the exact baseline and V2 member. The display
and reference fields are joined by the exact validated `case_id` from the frozen RQ2 case file. The case file must have
exactly 20 unique cases, and each frozen `user_input` must equal both matching plan members' `payload.user_input`.

RQ3 input consists of 48 validated commits: 12 source dialogues, two systems, and two turns. For each
`(case_id, system_config_id)` there must be exactly Turn 1 and Turn 2:

- `single_turn` Turn 1 and Turn 2 each have `rq3_relationship_kind = "single_turn"` and no checkpoint or Turn 1 commit
  hash;
- context-aware Turn 1 has `rq3_relationship_kind = "context_turn_one"`, a non-null validated
  `checkpoint_record_sha256`, and null `turn_one_commit_sha256`;
- context-aware Turn 2 has `rq3_relationship_kind = "context_turn_two"`, the same validated checkpoint-record hash,
  and a non-null `turn_one_commit_sha256` equal to the exact validated context-aware Turn 1 envelope hash.

The RQ3 case file must have exactly 12 unique dialogue identities and exactly two ordered turns per dialogue. Each
frozen turn `user_input` must equal both matching system plan members' `payload.user_input` for that turn.

The full checkpoint remains private. B3 neither serializes it to reviewer output nor reconstructs it. The two responses
are grouped under one anonymous conversation ID only after this relationship has validated.

### 4.5 Ordering and cardinality

The private snapshot and private mapping preserve exact execution order `1..190`. Reviewer order is deliberately not
execution order and is specified in Section 6.

The source snapshot must prove all of the following before transformation:

- 190 DTOs and 190 unique request IDs;
- 190 unique execution-unit IDs and 190 unique expected commit paths;
- continuous execution order `1..190`;
- RQ counts `RQ1 = 102`, `RQ2 = 40`, `RQ3 = 48`;
- system counts `qa_only_reconstructed_baseline = 71`, `v2 = 71`, `single_turn = 24`,
  `context_aware = 24`;
- complete per-case system/turn matrices;
- plan fingerprint `4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5`.

Any failed equation blocks all output.

## 5. Closed reviewer-output contract

### 5.1 Format and common encoding

Reviewer artifacts are typed JSON, not editable scoring spreadsheets. This keeps the projection schema closed,
preserves JSON types, avoids spreadsheet formula interpretation, and lets later scoring write separate artifacts
without altering the canonical reviewer input.

Every JSON file is encoded as:

```python
json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"
```

For B3-owned domain hashes over JSON values, the exact helper is:

```python
def domain_hash(domain: str, member: str, value: object) -> str:
    preimage = {"domain": domain, member: value}
    raw = json.dumps(
        preimage,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
```

The exact `(domain, member)` pairs are:

- canonical commit set: (`formal-evaluation-b3-canonical-commit-set-v1`, `commits`);
- secondary selection: (`formal-evaluation-b3-secondary-selection-v1`, `case_ids`);
- reviewer manifest self-hash: (`formal-evaluation-b3-reviewer-manifest-v1`, `manifest`), after removing only
  `manifest_sha256`;
- private projection manifest self-hash: (`formal-evaluation-b3-private-manifest-v1`, `manifest`), after removing only
  `projection_manifest_sha256`.

Artifact `sha256` values are ordinary SHA-256 over the complete exact file bytes. The blinding-key commitment is
`SHA-256(UTF8("formal-evaluation-b3-blinding-key-commitment-v1\0") || blinding_key)`.

Requirements:

- strict UTF-8;
- no BOM;
- one final LF;
- no CRLF dependence;
- duplicate keys and non-finite numbers rejected on reopen;
- exact canonical-byte equality on reopen;
- maximum 16 MiB per reviewer JSON file and 4 MiB for the private manifest;
- maximum nesting depth 16, mapping members 128, array members 256 except the explicitly bounded top-level record
  arrays, and individual string size 262,144 UTF-8 bytes;
- no missing, renamed, or additional fields at any level.

`model_answer` inherits the validated Stage A maximum of 32,768 Unicode characters and its control-character rules.
Display/reference strings must be exact source strings, nonempty where their frozen source requires nonempty, strict
UTF-8, contain no U+0000, and stay within the 262,144-byte JSON string bound. B3 never truncates, normalizes,
translates, redacts, repairs, or adds display text.

The contract identifier is exactly `formal_reviewer_projection_v1`. Every schema version below has exact built-in
type `int`, never `bool`, and value `1`.

No reviewer schema key is optional. Conditional private-manifest fields are always present and use the exact null rules
in Sections 4.4 and 6.3.

### 5.2 Common reviewer data-file envelope

Each of the four reviewer data files has exactly these eight top-level keys:

1. `schema_version`: `1`;
2. `projection_contract_id`: `"formal_reviewer_projection_v1"`;
3. `reviewer_bundle_id`: `b3b_` followed by 24 lowercase hexadecimal characters;
4. `plan_fingerprint`: the frozen lowercase SHA-256;
5. `artifact_kind`: one exact value specified below;
6. `record_count`: exact non-boolean integer specified below;
7. `source_unit_count`: exact non-boolean integer specified below;
8. `records`: the exact ordered array specified below.

No source commit hash, request ID, system label, timestamp, execution order, Provider value, or private mapping hash is
permitted in this envelope.

### 5.3 RQ1 primary-review artifact

File: `rq1_primary_v1.json`

- `artifact_kind = "rq1_primary"`;
- `record_count = 102`;
- `source_unit_count = 102`;
- `records` contains exactly 102 objects.

Each record has exactly:

```text
response_id: "b3r_" + 24 lowercase hexadecimal characters
display_payload:
  question: nonempty exact Gold/plan string
  reference_answer: nonempty exact frozen Gold string
  model_answer: nonempty exact canonical Stage B2 response text
```

The `display_payload` object has exactly those three keys. All 102 `response_id` values are unique.

### 5.4 RQ1 secondary-review artifact

File: `rq1_secondary_v1.json`

- `artifact_kind = "rq1_secondary"`;
- `record_count = 22`;
- `source_unit_count = 22`;
- `records` has the same closed record schema as RQ1 primary;
- it contains both system results for exactly 11 complete RQ1 cases;
- every `response_id` is the same stable ID used for that source unit in the primary artifact;
- the 22 IDs are unique within this file and are an exact subset of the primary IDs.

The 11-case selection reuses the current deterministic tracked rule without treating legacy response rows as result
authority:

1. group the 51 unique Gold cases by exact `gold_category`;
2. iterate categories in ordinal string order;
3. select the first case in each category by the existing
   `derive("rq1-secondary", review_id)` order using the unchanged runner `BASE_SEED = 20260721`;
4. order all unselected cases by existing `derive("rq1-secondary-fill", review_id)` with the same base seed;
5. append from that order until exactly 11 unique cases are selected;
6. require both canonical system commits for every selected case.

If the rule cannot produce exactly 11 complete cases, projection stops with `B3_REFERENCE_INVALID`. Gold category,
case identity, derivation key, and selection order are private and do not appear in reviewer artifacts.

### 5.5 RQ2 artifact

File: `rq2_v1.json`

- `artifact_kind = "rq2"`;
- `record_count = 40`;
- `source_unit_count = 40`;
- `records` contains exactly 40 objects.

Each record has exactly:

```text
response_id: "b3r_" + 24 lowercase hexadecimal characters
display_payload:
  user_input: nonempty exact frozen plan string
  model_answer: nonempty exact canonical Stage B2 response text
reference_payload:
  expected_action_type: nonempty exact frozen string
  retrieval_expected: exact frozen bool or nonempty string
  required_elements: exact frozen array of 0..256 nonempty strings
  forbidden_elements: exact frozen array of 0..256 nonempty strings
```

The two nested mappings have exactly the listed keys. Source arrays retain exact item text and source order. Category
and case IDs are not reviewer-visible.

### 5.6 RQ3 artifact

File: `rq3_v1.json`

- `artifact_kind = "rq3"`;
- `record_count = 24` anonymous system-dialogue records;
- `source_unit_count = 48` turn-level source commits;
- `records` contains exactly 24 objects.

Each dialogue record has exactly:

```text
anonymous_conversation_id: "b3d_" + 24 lowercase hexadecimal characters
turns: array of exactly two turn objects
reference_payload:
  retrieval_expected: exact frozen bool or nonempty string
  required_elements: exact frozen array of 0..256 nonempty strings
  forbidden_elements: exact frozen array of 0..256 nonempty strings
```

Each turn object has exactly:

```text
response_id: "b3r_" + 24 lowercase hexadecimal characters
turn_index: exact integer 1 or 2
display_payload:
  user_input: nonempty exact frozen plan string
  expected_action_type: nonempty exact frozen string
  critical_turn: exact bool
  model_answer: nonempty exact canonical Stage B2 response text
```

`turns` is always ordered `[1, 2]`. There are 24 unique anonymous conversation IDs and 48 unique response IDs. No
original dialogue ID, condition label, state snapshot, history placeholder, expected internal state, reset flag,
checkpoint, or alternate-condition link is included.

### 5.7 Reviewer bundle manifest

File: `manifest_v1.json`

It has exactly:

```text
schema_version: 1
projection_contract_id: "formal_reviewer_projection_v1"
reviewer_bundle_id: exact bundle ID shared by all four files
plan_fingerprint: frozen SHA-256
encoding: "UTF-8"
artifacts: exact four-element array in this order:
  rq1_primary, rq1_secondary, rq2, rq3
manifest_sha256: lowercase SHA-256
```

Each artifact entry has exactly:

```text
artifact_kind: exact kind
filename: exact basename
schema_version: 1
record_count: exact count
source_unit_count: exact count
sha256: SHA-256 of the complete exact artifact bytes
```

`manifest_sha256` is the domain-separated canonical SHA-256 of the complete manifest mapping excluding only
`manifest_sha256`. It proves reviewer-bundle integrity without exposing private source hashes or mappings.

Its computation is exact and nonrecursive:

1. construct the complete manifest mapping without the `manifest_sha256` member;
2. compute
   `domain_hash("formal-evaluation-b3-reviewer-manifest-v1", "manifest", manifest_without_manifest_sha256)` using
   Section 5.1 canonical serialization, which has no appended file LF inside the domain-hash preimage;
3. insert that lowercase digest as the final mapping member named `manifest_sha256` before canonical key sorting;
4. serialize the now-complete mapping with the Section 5.1 file serializer, including its one final LF; and
5. compute the ordinary SHA-256 of those complete file bytes only for the private manifest's
   `reviewer_artifacts["manifest_v1.json"]` value.

The top-level private-manifest field `reviewer_manifest_sha256` and the projection outcome field of the same name both
contain the internal domain-separated `manifest_sha256` value from step 2. They never contain the ordinary complete-file
hash from step 5. Conversely, the complete-file hash appears only in
`reviewer_artifacts["manifest_v1.json"]`; no second alias is defined for either digest.

### 5.8 Fields prohibited from every reviewer artifact

Reviewer artifacts must not contain structural fields for:

- `system_config_id`, `formal_system_id`, resolved runtime identity, condition, treatment, baseline, V2, single-turn,
  or context-aware labels;
- request ID, execution-unit ID, execution order, case ID, original dialogue ID, review ID, turn ID, attempt ID, or
  checkpoint ID;
- private commit, response, run-contract, archive, journal, checkpoint, resource, payload, input, or Provider hashes;
- Provider name/model/base URL, Provider response ID, Provider request ID, call counts, call state, or success receipt;
- prompts, system messages, complete request payloads, history placeholders, retrieved document IDs, scores, snippets,
  context, resources, corpus rows, or embeddings;
- Gold category, sampling group, risk reason, external candidate ID, external session ID, or private provenance;
- filesystem paths, usernames, machine identity, lock state, temporary filenames, or environment values;
- exceptions, exception messages, tracebacks, timestamps, durations, attempt counts, or execution ordering;
- reviewer identity, scores, notes, adjudication fields, statistical fields, or completed rating data.

The literal occurrence of a Provider or system name inside a legitimate model answer is not a structural metadata
leak and must not be edited. Leakage tests operate on closed keys and synthetic sentinel values, not substring bans on
the answers reviewers must assess.

## 6. Deterministic blinding and private mapping

### 6.1 Source commitment and blinding key

After validation, B3 forms an execution-order list with exactly these four fields per unit:

```text
execution_order
execution_unit_id
request_id
envelope_sha256
```

`canonical_commit_set_sha256` is a domain-separated SHA-256 over that exact 190-element list. It is private and is not
written to reviewer output.

The deterministic private blinding key is:

```text
SHA-256(
  UTF8("formal-evaluation-b3-blinding-key-v1\0") ||
  bytes.fromhex(plan_fingerprint) ||
  bytes.fromhex(canonical_commit_set_sha256)
)
```

This is not an API key, credential, or user secret. It is derived from already-private canonical evidence, is stable
for the same first-success commit set, is never written in raw form, and requires no `.env` or random seed. The private
manifest stores only a domain-separated SHA-256 commitment to the key.

### 6.2 IDs and ordering

All keyed derivations use HMAC-SHA-256 with the private blinding key. For one or more components, the exact message is
`UTF8(domain) || b"\0" || UTF8(component_1) || b"\0" || ... || UTF8(component_n)`, with no trailing NUL. With no
component, the message is exactly `UTF8(domain)`:

- response ID: domain `formal-evaluation-b3-response-id-v1`, component `request_id`, serialized as `b3r_` plus the
  first 24 lowercase hex characters;
- anonymous RQ3 conversation ID: domain `formal-evaluation-b3-dialogue-id-v1`, components `case_id` and
  `system_config_id`, serialized as `b3d_` plus the first 24 lowercase hex characters;
- reviewer bundle ID: domain `formal-evaluation-b3-bundle-id-v1`, no additional component, serialized as `b3b_` plus
  the first 24 lowercase hex characters;
- independent full-width ordering keys use domains `formal-evaluation-b3-rq1-primary-order-v1`,
  `formal-evaluation-b3-rq1-secondary-order-v1`, `formal-evaluation-b3-rq2-order-v1`, and
  `formal-evaluation-b3-rq3-order-v1`.

The RQ1 primary, RQ1 secondary, and RQ2 ordering-key component is the exact `request_id`. The RQ3 dialogue ordering-key
components are the exact private `case_id` and `system_config_id`. Turn order is not hashed.

Every truncated ID set and every full-width ordering-key set within an artifact must be collision-free. A collision is
`B3_BLINDING_INCONSISTENT`; B3 does not lengthen one ID, add a fallback sort, or choose another value ad hoc.

RQ1 primary, RQ1 secondary, and RQ2 records are sorted by their independent full HMAC order key, with `response_id` as
an equality-only assertion, never a fallback that changes the order. RQ3 dialogue groups are sorted by their dialogue
order key; turns remain `1, 2`. No HMAC order key is serialized.

This produces stable reruns, hides source execution order, avoids a public deterministic mapping, and requires no
credential-management architecture.

### 6.3 Private mapping/provenance manifest

The mapping is part of B3 because later paired analysis and unblinding would otherwise be irreproducible. It is not a
reviewer artifact and is never distributed to a reviewer.

File: `data/formal_eval/reviewer_projection/private/projection_manifest_v1.json`

It has exactly these top-level keys:

```text
schema_version
projection_contract_id
reviewer_bundle_id
plan_fingerprint
run_contract_sha256
canonical_commit_set_sha256
blinding_key_commitment_sha256
counts
secondary_selection
reviewer_artifacts
entries
reviewer_manifest_sha256
projection_manifest_sha256
```

`counts` has exactly:

```text
source_units: 190
unique_request_ids: 190
execution_order_first: 1
execution_order_last: 190
by_rq: {RQ1: 102, RQ2: 40, RQ3: 48}
by_system: {
  qa_only_reconstructed_baseline: 71,
  v2: 71,
  single_turn: 24,
  context_aware: 24
}
rq1_primary_records: 102
rq1_secondary_cases: 11
rq1_secondary_records: 22
rq2_records: 40
rq3_dialogues: 24
rq3_units: 48
```

`secondary_selection` has exactly `algorithm_id`, `case_ids`, and `selection_sha256`. `algorithm_id` is
`rq1_secondary_existing_deterministic_v1`; `case_ids` is the exact private 11-string selection in selection order;
`selection_sha256` is a domain-separated hash over that list. Gold category values are not retained.

`reviewer_artifacts` has exactly five basename-to-SHA-256 entries for the four data files and reviewer manifest. Every
value is the ordinary SHA-256 of that complete canonical file's bytes, including its final LF. In particular,
`reviewer_artifacts["manifest_v1.json"]` is the ordinary complete-file hash defined in Section 5.7.

`entries` contains exactly 190 objects in execution order. Each has exactly:

```text
execution_order
request_id
execution_unit_id
plan_member_sha256
rq
case_id
dialogue_id
turn_index
system_config_id
formal_system_id
source_envelope_sha256
response_sha256
response_id
anonymous_conversation_id
reviewer_artifacts
rq3_relationship_kind
turn_one_commit_sha256
checkpoint_record_sha256
```

`anonymous_conversation_id` is non-null only for RQ3. `reviewer_artifacts` is an exact ordered array: every unit occurs
once in its primary RQ artifact, and selected RQ1 units additionally name the secondary artifact. RQ3 nullability must
match Section 4.4.

The exact membership arrays are:

- unselected RQ1: `["rq1_primary_v1.json"]`;
- selected RQ1: `["rq1_primary_v1.json", "rq1_secondary_v1.json"]`;
- RQ2: `["rq2_v1.json"]`;
- RQ3: `["rq3_v1.json"]`.

The top-level private `reviewer_manifest_sha256` is exactly the reviewer manifest's internal domain-separated
`manifest_sha256`, not the ordinary hash of the reviewer manifest file. The private manifest contains no query,
question, reference answer, model answer, prompt, retrieved content, Provider metadata, timestamp, exception,
environment value, or raw blinding key. `projection_manifest_sha256` is computed only after the internal reviewer
manifest digest and all five ordinary `reviewer_artifacts` hashes are inserted; it is a domain-separated canonical hash
excluding only `projection_manifest_sha256` itself.

Ownership and lifecycle:

- the local evaluation operator owns the private manifest;
- it remains under the ignored private B3 directory and is never copied into the reviewer directory;
- it is create-only and preserved with formal private provenance through later scoring and analysis;
- later tools may read it only under their own explicit authorization;
- a reviewer artifact can never update it;
- deletion, rotation, sharing, and archival policy are outside B3; B3 itself never deletes the final manifest.

For recovery, **absent** means that the exact expected private-manifest path does not exist after the fixed parent path
has passed path validation. An empty file, malformed file, wrong-version file, hash-invalid file, non-file occupant,
reparse point, or validly formed but different mapping is present, not absent. An absent mapping may be reconstructed
create-only under the complete Section 7 recovery contract. A present malformed or differing mapping must never be
replaced, merged, guessed, repaired, or treated as absent.

### 6.4 Reviewer access and privacy boundary

Designated reviewers may receive only the applicable reviewer data file, `manifest_v1.json`, and the separately
governed scoring/rubric instructions. Within those files they may see only:

- blind response IDs and, for RQ3, blind conversation IDs;
- RQ1 question, reference answer, and exact model answer;
- RQ2/RQ3 user inputs, minimized frozen reference payloads defined in Section 5, turn index/critical-turn status where
  applicable, and exact model answers;
- safe schema, bundle, plan-fingerprint, count, filename, encoding, and reviewer-file integrity metadata.

The question/user-input fields are customer-derived evaluation material and the model answers are formal evaluation
material reviewers legitimately need to assess. They therefore remain sensitive even after system blinding. B3 relies
on the already frozen cleaned/anonymised evaluation sources; it performs no new PII redaction that could alter a test
unit. A detected source-identity or privacy defect stops projection for operator review rather than guessing a rewrite.

Reviewers must not receive the private mapping, original IDs, condition labels, private hashes, Provider metadata,
execution order/timing, prompts, retrieval context, exceptions, or filesystem provenance. The local operator controls
distribution outside B3. B3 sends no file over a network, creates no share, and exposes no credential.

The schema/contract IDs, reviewer bundle ID, frozen plan fingerprint, aggregate reviewer counts, fixed basenames,
encoding label, and hashes of files the reviewer already receives are the complete safe reviewer provenance allowlist.
No other provenance field may be added without a reviewed B3 schema change.

## 7. Projection behavior

### 7.1 Production entrypoint

The future production entrypoint is:

```python
def project_blinded_reviewer_outputs() -> ReviewerProjectionOutcome:
    ...
```

It accepts no arguments. In particular it accepts no caller-selected root, file, request, subset, seed, key, mapping,
response, client, Provider, overwrite, force, repair, or resume value. A module CLI may invoke this function with no
options; unexpected command-line arguments fail before private-state access.

`ReviewerProjectionOutcome` is a frozen, slotted dataclass with exactly:

```text
schema_version: int = 1
action: "created" | "resumed" | "already_complete"
reviewer_bundle_id: str
source_unit_count: int = 190
reviewer_artifact_count: int = 5
reviewer_manifest_sha256: str
projection_manifest_sha256: str
```

`reviewer_manifest_sha256` is exactly the internal domain-separated reviewer-manifest `manifest_sha256` defined in
Section 5.7. It is not the ordinary hash of the complete manifest file; that ordinary hash exists only in the private
manifest's `reviewer_artifacts["manifest_v1.json"]`. The outcome contains no row content, system mapping, path,
Provider value, timestamp, or exception text.

### 7.2 Validation and transformation order

The exact order is:

1. reject unexpected CLI arguments and validate fixed B3/B2 module authorities without opening Stage B2 durable state
   or resolving, probing, or creating the B3 root;
2. call `verify_frozen()`, build and validate the exact plan, and verify the frozen fingerprint/counts;
3. freshly call `build_durable_run_contract(plan)`, validate the authoritative contract, and apply the complete Section
   3.3 source-eligibility gate;
4. only after eligibility succeeds, call the read-only Stage B2 observation interface under the Stage B2 run lock; the
   observation boundary itself rejects an active Stage B2 test controller before durable-state access without B3
   inspecting controller state;
5. release the Stage B2 lock with a detached immutable snapshot;
6. require the complete 190-unit matrix and require every DTO `run_contract_sha256` to equal the freshly gated contract;
7. load only the exact frozen display/reference fields needed by Section 5 and validate unique joins;
8. construct and validate the canonical commit-set commitment, private blinding key, IDs, sort keys, selection, four
   reviewer objects, reviewer manifest, and private manifest entirely in memory;
9. run a second closed-schema and prohibited-key validation over the in-memory reviewer objects;
10. serialize all final bytes and compute the reviewer manifest's internal hash, all five ordinary reviewer-file hashes,
    and the private-manifest self-hash in the exact Section 5.7/6.3 order;
11. validate the fixed B3 root and acquire the B3 projection lock;
12. inspect every existing B3 path and file using the global Section 7.6 precedence before cleaning an owned temp or
    publishing anything;
13. publish or recover according to Sections 7.4 and 7.5;
14. reread every final, reapply Section 7.6, and validate every exact byte, internal hash, complete-file hash, and
    cross-artifact relationship;
15. return only the sanitized outcome.

No B3 output path is touched before steps 1–10 pass. In particular, `B3_SOURCE_INELIGIBLE` is decided at step 3 before
the Stage B2 commit set is observed or accepted at step 4 and before any output-root existence check at step 11.

### 7.3 Determinism and idempotency

For the same validated plan, commit set, and frozen references, every ID, order, JSON object, byte, filename, and hash is
identical. There is no clock, random nonce in final content, locale-dependent sorting, filesystem enumeration order,
or environment-dependent value.

Temporary filenames alone use a 32-lowercase-hex random nonce. They are not final content or provenance.

A complete identical rerun performs no final-file write and returns `already_complete`. An interrupted identical run
may publish only missing final files and returns `resumed`. A fresh run returns `created`.

`already_complete` is permitted only when the exact private mapping, all four reviewer data files, and the reviewer
manifest already exist and validate without a final-file write. `created` is permitted only when none of those six
finals existed and the complete ordered publication succeeds. Any successful invocation that reconstructs an absent
private mapping or fills one or more missing reviewer finals returns `resumed`, including recovery from an exact
complete reviewer bundle whose private mapping alone was absent.

### 7.4 Publication order and create-only rules

Final files are immutable and create-only. B3 has no final-file replacement or force mode.

All six deterministic final byte strings are regenerated and validated in memory before the B3 root is touched. Under
the fixed projection lock, fresh publication and recovery publish missing files in this order:

1. private `projection_manifest_v1.json`;
2. `rq1_primary_v1.json`;
3. `rq1_secondary_v1.json`;
4. `rq2_v1.json`;
5. `rq3_v1.json`;
6. reviewer `manifest_v1.json` last.

The reviewer manifest is the sole reviewer-bundle completion marker. Reviewers must not receive the directory unless
that manifest and all four listed files validate. Publishing it last prevents a partial set from being represented as
complete.

When the private mapping is absent, B3 may reconstruct it only after all of the following have succeeded in the current
invocation:

1. the full eligible run contract has been freshly reconstructed, validated, and passed the Section 3.3 gate;
2. the complete canonical 190-unit Stage B2 private input has been re-observed and revalidated;
3. all expected reviewer artifacts and the exact private mapping have been regenerated deterministically in memory;
4. every existing reviewer final has been checked against its exact expected deterministic bytes; and
5. the complete B3 tree has no unexpected, malformed, stale, wrong-version, hash-inconsistent, mixed-generation, or
   differing reviewer path or file under the Section 7.6 precedence.

The reconstructed mapping is then published first using the same exclusive-temp, flush, `os.fsync()`, create-only
same-directory atomic rename, reread, and exact-byte rules as its original publication. Existing exact reviewer files
are never rewritten merely because the mapping was missing. Only after the mapping exists and rereads exactly may B3
publish any missing reviewer data final, followed by a missing reviewer manifest last.

If an exact complete reviewer bundle including its reviewer manifest already exists while the private mapping is
absent, B3 first validates all five reviewer finals and their cross-artifact hashes, publishes and rereads only the
mapping, and then returns `resumed`; it does not rewrite the completion manifest. Until that reconstructed mapping is
safely present, the invocation must not treat the bundle as complete or return an outcome. If the reviewer manifest is
absent, B3 never publishes it until the required private mapping and all four reviewer data finals are safely present.
Thus recovery cannot newly mark a bundle complete before its required private mapping and reviewer finals exist.

A present private mapping that differs, is malformed, has the wrong version, or fails any internal or cross-artifact
check is not an absent mapping. B3 stops under Section 7.6 and never replaces, merges, guesses, or repairs it.

For each final file:

1. validate the fixed contained non-reparse path and parent;
2. if the final exists, require it to pass the complete Section 7.6 classification and equal its exact expected bytes;
   identical is idempotent and any defect returns only the category selected by that precedence;
3. if absent, create an exclusive sibling temporary file;
4. write all bytes, flush, `os.fsync()`, and close;
5. atomically rename within the same directory without replacement;
6. reread and require exact expected bytes and hash.

The implementation may use the existing Windows semantics behind a small B3-owned byte publisher, but must not call
the Stage B2 JSON publisher against a B3 root or widen Stage B2 root authority. No directory-durability or distributed
exactly-once claim is made.

### 7.5 Temporary cleanup, interruption, and uncertain publication

Owned temporary names are exactly `.<final-basename>.<32-lowercase-hex>.tmp` in one of the two fixed B3 output
directories. Under the projection lock, B3 may remove only those exact contained regular non-reparse files. Unknown,
malformed, nested, reparse, or out-of-root entries stop with `B3_OUTPUT_PATH_INVALID`. Cleanup failure is
`B3_IO_FAILURE`.

On reopen after a publication exception:

- exact final bytes mean the file is published; remove only an owned leftover temp and continue locally;
- absent final bytes mean the missing file may be republished locally from the already revalidated deterministic
  source;
- different, malformed, noncanonical, wrong-version, or hash-mismatched final bytes stop under the exact Section 7.6
  category and are never overwritten;
- a reviewer manifest with a missing or mismatched dependency stops as `B3_HASH_MISMATCH` under Section 7.6;
- a missing reviewer manifest with any exact subset of reviewer data finals is resumable only after the private mapping
  exists exactly or has passed the complete absent-mapping reconstruction contract;
- an absent private mapping with an exact partial reviewer bundle permits mapping-first reconstruction and publication
  of only missing reviewer finals;
- an absent private mapping with all four exact reviewer data files but no reviewer manifest permits reconstruction of
  the mapping followed by publication of only the reviewer manifest;
- an absent private mapping with an exact complete reviewer bundle and reviewer manifest permits publication of only
  the mapping and returns `resumed` after complete reread;
- an absent mapping with any differing reviewer file stops before mapping creation; and
- a present but differing private mapping stops and is never reconstructed over.

Local retry and resume repeat the complete input validation first. They never call an executor or Provider.

### 7.6 Existing-path and existing-file error precedence

After expected bytes have been generated in memory and the B3 lock has been acquired, B3 applies the following table
globally in order. At each row it evaluates the complete existing B3 tree before considering any lower-precedence row.
If one or more paths match a row, exactly that row's category is returned, evaluation of all lower rows stops, no final
is created, removed, replaced, or rewritten, and no sanitized outcome is returned. Exact owned temporary files are not
finals and may be cleaned only after no table row matches.

| Order | Objective detection predicate | Exact category | Lower-precedence evaluation | Permitted next action | Operator, retry/resume, and Provider rule |
| ---: | --- | --- | --- | --- | --- |
| 1 | Any unexpected path; expected path or owned-temp occupant is a wrong filesystem object type, reparse point, out-of-root target, invalid basename, or prohibited path collision; or the fixed lock occupant is invalid | `B3_OUTPUT_PATH_INVALID` | Stop | Preserve the tree; only a separately authorized operator may resolve the path condition | Operator action required; B3 retry/resume prohibited until resolution; Provider recall forbidden |
| 2 | An expected regular JSON final cannot pass size bounds, strict UTF-8/no-BOM decoding, duplicate-key/non-finite rejection, JSON parsing, canonical-byte form, or its closed structural field/type/bounds schema, with recognized version/contract field values deferred exclusively to row 3 | `B3_ARTIFACT_INVALID` | Stop | Preserve the file; operator diagnoses malformed or unverifiable bytes outside B3 | Operator action required; B3 retry/resume prohibited until resolution; Provider recall forbidden |
| 3 | A row-2-readable artifact has any non-integer/unsupported `schema_version` or wrong `projection_contract_id`/versioned artifact identity | `B3_SCHEMA_VERSION_MISMATCH` | Stop | Preserve the file; use only a separately reviewed migration or contract amendment | Operator action required; B3 retry/resume prohibited until that work; Provider recall forbidden |
| 4 | A supported-version artifact fails its internal self-hash, a declared ordinary complete-file hash, reviewer-manifest dependency hash, private `reviewer_manifest_sha256` link, private `reviewer_artifacts` link, or another defined cross-artifact hash relationship | `B3_HASH_MISMATCH` | Stop | Preserve all files; operator investigates integrity/provenance under separate authority | Operator action required; B3 retry/resume prohibited until resolution; Provider recall forbidden |
| 5 | A reviewer data final or reviewer manifest passes rows 1–4 but its complete canonical bytes differ from the exact deterministic expected bytes regenerated from the current eligible source | `B3_OUTPUT_COLLISION` | Stop | Preserve both source state and existing final; B3 never overwrites or chooses between generations | Operator action required; B3 retry/resume prohibited until resolution; Provider recall forbidden |
| 6 | The private mapping exists and passes rows 1–4, but its counts, source bindings, blind IDs, entries, selection, artifact membership, or other deterministic mapping value differs from the exact expected mapping after every existing reviewer final has passed the higher rows | `B3_BLINDING_INCONSISTENT` | Stop | Preserve the mapping and reviewer files; correction requires separate reviewed operator action | Operator action required; B3 retry/resume prohibited until resolution; Provider recall forbidden |

The rows are mutually exclusive by construction. A missing private mapping is not a row-2 malformed mapping and follows
Sections 6.3–7.5. Malformed or unverifiable bytes use row 2; a well-formed wrong-version artifact uses row 3; an
internally or cross-artifact hash-inconsistent artifact uses row 4; a well-formed, internally consistent reviewer final
with different expected bytes uses row 5; and an internally consistent private mapping that conflicts with the exact
source-to-reviewer relationship uses row 6. If defects exist in multiple files, the first matching row across the whole
tree controls, rather than filesystem enumeration order.

Reopen validates both reviewer-manifest digests without conflating them: recomputation of the internal domain-separated
digest must equal reviewer `manifest_sha256`, private `reviewer_manifest_sha256`, and the returned outcome field, while
the ordinary SHA-256 of the complete canonical reviewer-manifest bytes must equal only private
`reviewer_artifacts["manifest_v1.json"]`. A failure of either check is row 4 `B3_HASH_MISMATCH`.

### 7.7 Exceptions and terminal output

Existing Stage B2 `StoreError` objects propagate unchanged to the Python caller. They are not classified as B3 retry,
Provider retry, absence, or a reviewer result.

`B3_PRIVATE_STATE_INVALID` is reserved for a malformed, duplicated, out-of-order, or internally inconsistent detached
observation DTO returned after the Store boundary has succeeded. It must not replace or obscure a `StoreError` raised
while validating durable Stage B2 evidence.

`ProjectionError` is a sanitized `RuntimeError` containing exactly one category from:

```text
B3_PLATFORM_UNSUPPORTED
B3_LOCK_BUSY
B3_SOURCE_INELIGIBLE
B3_INPUT_INCOMPLETE
B3_PRIVATE_STATE_INVALID
B3_REFERENCE_INVALID
B3_SCHEMA_VERSION_MISMATCH
B3_BLINDING_INCONSISTENT
B3_PRIVACY_BOUNDARY_VIOLATION
B3_OUTPUT_PATH_INVALID
B3_ARTIFACT_INVALID
B3_OUTPUT_COLLISION
B3_HASH_MISMATCH
B3_IO_FAILURE
```

It stores no path, raw exception message, row content, answer, prompt, ID mapping, or arbitrary detail. Internal causes
may be chained for in-process debugging, but the CLI catches known errors and prints only the category. It never prints
the cause, traceback, source row, or artifact content.

`B3_SOURCE_INELIGIBLE` is the sole classification for the two Section 3.3 predicates. The six Section 7.6 categories
are exact for existing-path/file defects and are not interchangeable. No `ReviewerProjectionOutcome` is constructed on
any error category.

A local serialization or persistence failure cannot enter any Stage A/B1 retry loop and cannot produce a Provider
recall.

## 8. Artifact layout and repository hygiene

### 8.1 Fixed future layout

The future implementation generates only this ignored layout:

```text
data/formal_eval/reviewer_projection/
├── projection.lock
├── private/
│   └── projection_manifest_v1.json
└── reviewer/
    ├── rq1_primary_v1.json
    ├── rq1_secondary_v1.json
    ├── rq2_v1.json
    ├── rq3_v1.json
    └── manifest_v1.json
```

Sibling owned temporary files may exist only during publication and use the exact Section 7.5 pattern.

After all in-memory validation succeeds, create only the fixed root, `private`, and `reviewer` directories one
component at a time, validating containment and reparse status after each operation. `projection.lock` is exactly the
one byte `b"\x00"`; an existing zero-byte, multi-byte, wrong-byte, non-file, or reparse occupant fails
`B3_OUTPUT_PATH_INVALID` without repair. The lock is publication infrastructure, not a reviewer artifact or completion
record.

The private Stage B2 state remains separately under `data/formal_eval/private_state/`. B3 must not create a directory
inside that store, whose fixed layout rejects unknown members.

### 8.2 Ignore and tracking contract

`.gitignore` currently ignores all of `data/`, and `git check-ignore` confirms the proposed B3 paths are ignored. The
future implementation must not modify `.gitignore` merely for B3.

Required hygiene verification:

- `git check-ignore -q` succeeds for every fixed generated final and representative temporary path;
- `git ls-files -- data/formal_eval/reviewer_projection` returns no path;
- a focused test creates generated files only under its two patched OS-temporary roots and proves by guarded path
  access that neither actual production root is read, inspected, created, repaired, or written;
- the implementation report verifies that no generated file is staged or tracked;
- unknown output-root entries fail closed rather than being swept into a manifest.

Tracked source and tests may encode the schemas as constants/dataclasses. No new frozen evaluation schema file is
needed for this smallest design. The only tracked documentation authority is this plan after its separate approval and
freeze; implementation does not modify it.

### 8.3 Windows and path requirements

- Production roots derive from the repository root; callers cannot supply them.
- Every existing component is checked for symlink, junction, or Windows reparse-point status.
- Fixed basenames contain only lower-case ASCII, digits, and underscore, with `.json` or `.lock` suffixes.
- Reject UNC, extended path, traversal, drive-relative, URI-like, reserved-device, trailing-dot/space, control, and
  mixed-separator paths.
- The projection lock uses the same one-process-at-a-time Windows byte-lock principle as Stage B2, but controls only B3
  publication. It cannot authorize private-state mutation or execution.
- Production code has no public root argument. The focused B3 test file may patch exactly two root-selection constants:
  B3's module-private `_REVIEWER_PROJECTION_ROOT` and B2's existing module-private `_PRIVATE_STATE_ROOT`. It must not
  patch either immutable production-root sentinel or add a public production root argument merely for testing.
- The two patched values must be distinct, disjoint, validated directories created beneath `tmp_path` or another
  OS-managed temporary directory. Before any test access, each must resolve within that test-owned temporary parent,
  differ from its actual production root, contain no reparse component, and be neither equal to nor nested within the
  other.
- The patching fixture must install both temporary roots before importing or invoking projection behavior that could
  resolve a root. Tests must not read from, write to, repair, enumerate, existence-check, or otherwise inspect the
  actual Stage B2 private root or actual B3 reviewer-projection root.
- The B2 `_STAGE_B2_TEST_FAULT_CONTROLLER` remains inactive. It may be installed only by a specifically named B3
  interruption or fault-injection test whose asserted behavior requires that existing controller; all other B3 tests,
  including ordinary observation, source eligibility, success, reopen, and mapping recovery, must prove the controller
  was not installed.
- Root patching does not permit a duplicate validator: observation tests must still enter the production Stage B2
  read-only observation seam and its existing complete private-commit validator.

## 9. Frozen evaluation identity preservation

The frozen identity remains exactly:

| invariant | required value |
| --- | ---: |
| total request units | 190 |
| unique request IDs | 190 |
| execution order | `1..190` |
| RQ1 | 102 |
| RQ2 | 40 |
| RQ3 | 48 |
| `qa_only_reconstructed_baseline` | 71 |
| `v2` | 71 |
| `single_turn` | 24 |
| `context_aware` | 24 |

Plan fingerprint:

`4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5`

B3 proves preservation in four layers:

1. the runner revalidates the exact plan and fingerprint;
2. the Stage B2 validator binds each commit to one exact plan member and execution identity;
3. the private mapping contains one execution-ordered entry for every unit and independently rechecks all totals and
   matrices;
4. reviewer artifacts account for all 190 primary units exactly once across RQ1 primary, RQ2, and RQ3, while the 22
   secondary rows are a declared duplicate review subset, not new units.

The reviewer artifacts blind condition membership by omitting system identity and replacing private IDs. The private
mapping preserves the exact condition-to-blind-ID relationship for later authorized unblinding. Reviewer reordering
does not change source execution order, membership, or the plan fingerprint.

B3 never recomputes a different request ID or fingerprint from reviewer data and never adds transport, journal,
mapping, reviewer, or projection metadata to plan units.

## 10. Failure and recovery matrix

No row below authorizes a Provider call, model call, execution retry, or response regeneration.

| Classification | Detection | B3 action | Permitted next action |
| --- | --- | --- | --- |
| Source ineligible | Fresh authoritative contract has mode `offline_fake_only` or any `resource_identity.synthetic` value is `true` | Stop exactly `B3_SOURCE_INELIGIBLE` before Stage B2 observation and before any B3-root access | Separately governed later work may establish a validated non-synthetic authority; this row does not authorize B5, execution, or Provider access |
| No canonical private success | Zero validated canonical commits | Stop `B3_INPUT_INCOMPLETE`; create no B3 path | Operator determines execution status under separate authority; B3 cannot fill it |
| Incomplete evaluation set | Any count below 190, missing pair/turn/system, or missing expected commit | Stop `B3_INPUT_INCOMPLETE`; publish nothing | Reinvoke B3 only after a separately authorized process has produced a complete validated set; this row does not make uncertain or terminal state executable |
| Invalid or contradictory private state | Any Stage B2 schema, hash, path, archive, lineage, commit, journal, dependency, or authority error | Propagate exact `StoreError`; no omission or repair | Operator investigates Stage B2 evidence; no B3 retry until corrected by authorized process |
| Repairable private pointer lag with valid canonical commit | Existing B2 validator proves the commit and recognizes non-authoritative lag without repair | Accept the commit as Stage B2 success; write no private state | Continue projection; any private cleanup/reconciliation is separate |
| Already complete canonical reviewer artifact | Private manifest, four reviewer files, and reviewer manifest all equal recomputed bytes/hashes | Return `already_complete`; write nothing | Safe local reread/rerun |
| Private mapping absent; exact partial reviewer bundle | Mapping path is absent and every existing reviewer final is exact, with at least one expected reviewer final missing and no completion-manifest contradiction | Revalidate eligible source and all expected bytes; publish mapping first, then only missing data finals, then missing reviewer manifest last | Local create-only recovery; return `resumed` after complete reread |
| Private mapping absent; exact complete reviewer data without completion manifest | Mapping path and reviewer manifest are absent; all four reviewer data finals are exact | Publish and reread mapping, then publish reviewer manifest last | Local create-only recovery; return `resumed` |
| Private mapping absent; exact complete reviewer bundle with completion manifest | Only mapping is absent; all five reviewer finals and both manifest-hash meanings validate exactly | Publish and reread only the mapping; do not rewrite reviewer files | Local create-only recovery; return `resumed`; bundle is not accepted complete before mapping exists |
| Private mapping absent with a defective reviewer final | Mapping is absent, but any existing reviewer path/file matches Section 7.6 | Stop with the first exact Section 7.6 category before mapping creation | Required operator action from the precedence row; no automatic repair or resume |
| Private mapping present but defective or different | Mapping is present and matches Section 7.6 row 1–4, or passes those rows but differs from the deterministic expected mapping | Stop with the first exact Section 7.6 category; an internally valid deterministic mapping difference is exactly `B3_BLINDING_INCONSISTENT` | Operator action; never treat it as absent or reconstruct over it |
| Existing B3 path/file defect | Any existing path or file satisfies a Section 7.6 predicate | Apply the global ordered table and return exactly its first matching category | Preserve evidence; retry/resume remains prohibited until the table's required operator action completes |
| Atomic replacement failure | Replacement of an existing final is prohibited; a low-level rename/publication error occurs | Stop `B3_IO_FAILURE`; preserve old final and any owned temp | Reopen classification decides exact-final, absent-final, or collision; local retry only |
| Reopen after uncertain publication | Prior call failed after rename may have completed | Exact final = published; absent final = locally retryable; different/malformed final = stop | Resume only after complete input revalidation; never Provider recall |
| Privacy-boundary violation | Closed reviewer object contains a prohibited key/value sentinel or mapping/public separation fails | Stop `B3_PRIVACY_BOUNDARY_VIOLATION` before reviewer manifest | Preserve existing finals; operator review required |
| Reference join mismatch | Missing, duplicate, unmatched, extra, or wrong-type Gold/RQ2/RQ3 structural source | Stop `B3_REFERENCE_INVALID` | Resolve as a frozen-authority issue; no silent fallback |
| Projection lock busy | Another B3 publisher holds the fixed lock | Stop `B3_LOCK_BUSY`; no writes | Local retry after the other process exits |
| Temporary cleanup failure | Exact owned temp cannot be safely removed | Stop `B3_IO_FAILURE` | Operator resolves local filesystem issue, then full revalidation and retry |

If a state could be described by more than one prose row, Section 7.6 is controlling for every existing-path/file
defect. No failure or recovery row may recall a Provider, call an executor, regenerate a response, repair Stage B2, or
begin B4/B5 behavior.

## 11. Proposed future implementation allowlist

This allowlist is proposed authority only. It does not authorize changes in the current documentation task.

| Path | Status | Exact purpose |
| --- | --- | --- |
| `scripts/formal_evaluation_store.py` | modified | Add the detached observation DTO and a no-create, no-cleanup, no-repair read-only wrapper over the existing private-commit validator. Do not change validation or execution behavior. |
| `scripts/run_formal_evaluation.py` | modified | Add only `observe_validated_canonical_private_results(plan)` as the fixed-authority runner wrapper. Do not change legacy templates, dry-run, real gate, CLI execution, generation, or Provider behavior. |
| `scripts/formal_evaluation_review_projection.py` | added | Implement the source-eligibility gate, closed B3 transformer, blinding, schemas, fixed paths, exact existing-file precedence, mapping recovery, publication, sanitized outcome/error, and no-option projection entrypoint. |
| `scripts/test_formal_evaluation_review_projection.py` | added, test-only | Cover the new observation boundary and all B3 eligibility, two-root isolation, schema, privacy, hash-semantics, determinism, atomicity, mapping recovery, precedence, RQ3, no-recall, identity, and hygiene requirements with synthetic data and temporary roots. |
| `data/formal_eval/reviewer_projection/projection.lock` | generated, ignored | Fixed local B3 publication lock. |
| `data/formal_eval/reviewer_projection/private/projection_manifest_v1.json` | generated, ignored | Private mapping and provenance; never reviewer-facing. |
| `data/formal_eval/reviewer_projection/reviewer/rq1_primary_v1.json` | generated, ignored | RQ1 primary reviewer data. |
| `data/formal_eval/reviewer_projection/reviewer/rq1_secondary_v1.json` | generated, ignored | RQ1 secondary reviewer data. |
| `data/formal_eval/reviewer_projection/reviewer/rq2_v1.json` | generated, ignored | RQ2 reviewer data. |
| `data/formal_eval/reviewer_projection/reviewer/rq3_v1.json` | generated, ignored | RQ3 reviewer data. |
| `data/formal_eval/reviewer_projection/reviewer/manifest_v1.json` | generated, ignored | Reviewer-visible completion and integrity manifest. |

The proposed tracked implementation allowlist is exactly the first four paths. The generated ignored rows describe
runtime layout only and are not additional tracked allowlist members.

No other tracked path may change. In particular, do not modify:

- Stage A or B1 source/tests;
- existing Stage B2 plan or amendment;
- formal protocol, execution guide, amendments, manifest, plan, fingerprint logic, fixtures, or scoring schemas;
- baseline adapter/vendor/specification or V2/V2.1b core;
- `.gitignore`, `AGENTS.md`, production resources, caches, outputs, or environment files.

If implementation proves that a fifth tracked file is required, stop and seek explicit scope expansion before editing.
Unrelated refactoring is excluded.

## 12. Future offline verification contract

### 12.1 Environment and safety

Use the repository `.venv` and set:

```powershell
$VenvPython = (Resolve-Path ".venv\Scripts\python.exe").Path
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
$env:PYTHONPYCACHEPREFIX = Join-Path $env:TEMP "formal-evaluation-b3-pycache"
```

All focused B3 tests use synthetic DTOs, synthetic display/reference records, Stage B2's existing synthetic commit
construction path where commit validation is exercised, the two distinct Section 8.3 OS-temporary roots, and an
autouse network/socket denial. They patch exactly B3 `_REVIEWER_PROJECTION_ROOT` and B2 `_PRIVATE_STATE_ROOT` for root
selection, never inspect either actual production root, and never bypass or replace the production private-commit
validator to obtain an accepted observation. The B2 fault controller remains inactive except inside a specifically
named interruption/fault-injection test that requires it.

Positive projection tests may use a test-owned, structurally valid contract fixture whose mode is eligible and whose
four `resource_identity.synthetic` values are exactly `false`. That fixture is only synthetic test scaffolding for the
post-gate success path; neither it nor any generated temporary artifact may be described, named, stored, distributed,
or reported as a formal evaluation result. Observation-boundary tests separately exercise the production Stage B2
read-only seam and complete validator against the patched B2 root. All tests remain fully offline.

Tests read no `.env`, credential, production cache, corpus, embedding, model, or formal output and print no query,
reference answer, model answer, prompt, mapping entry, or synthetic response text.

The frozen-identity and compatibility suites retain only their existing authorized fixture reads for deterministic
plan/fingerprint and aggregate regression. They must not print row-level content. No B3 test creates a real client or
imports a Provider SDK.

### 12.2 Non-writing syntax check

After implementation, run a non-writing AST parse of the four allowed tracked files:

```powershell
& $VenvPython -c "import ast,pathlib; files=('scripts/formal_evaluation_store.py','scripts/run_formal_evaluation.py','scripts/formal_evaluation_review_projection.py','scripts/test_formal_evaluation_review_projection.py'); [ast.parse(pathlib.Path(p).read_text(encoding='utf-8'),filename=p) for p in files]"
```

Expected result: exit code 0, no repository file created or modified.

### 12.3 Focused B3 test matrix

The focused test file must include independently identifiable coverage for:

1. exact DTO fields, types, bounds, detachment, and immutability;
2. patching exactly B3 `_REVIEWER_PROJECTION_ROOT` and B2 `_PRIVATE_STATE_ROOT` to distinct, disjoint, validated
   OS-temporary directories before access, with guarded proof that neither actual production root is inspected or
   mutated;
3. observation in execution order through the production B2 read-only seam and existing complete validator, including
   no-create/no-cleanup/no-repair behavior, ordinary fault-controller inactivity, and rejection of an active controller;
4. the source gate's exact two predicates, the one `B3_SOURCE_INELIGIBLE` category when either or both match, fail-closed
   malformed-authority handling, and acceptance of a test-owned structurally valid eligible fixture;
5. a complete 190-unit temporary B2 store associated with the current synthetic/`offline_fake_only` authority that
   returns exactly `B3_SOURCE_INELIGIBLE`, proves the observation interface was never invoked or accepted for
   projection, leaves the patched B3 output root unaccessed and exactly unchanged, creates no reviewer or private mapping
   artifact, calls no executor/core/client/Provider, and generates no formal response;
6. zero, partial, duplicate, off-chain, malformed, contradictory, and foreign private evidence under a source-eligible
   test fixture where reaching input validation is intended;
7. complete 190/190 identity, RQ/system counts, order, contract binding, and fingerprint;
8. RQ1 102 primary rows and deterministic 11-case/22-row complete secondary selection;
9. RQ2 40-row exact reference/display schema;
10. RQ3 24-dialogue/48-turn schema, stable grouping, Turn 1/Turn 2 ordering, context checkpoint hashes, and single-turn
   nullability;
11. exact model-answer preservation without normalization or truncation;
12. deterministic IDs, independent deterministic ordering, collision rejection, and repeat-run byte equality;
13. reviewer/private schema closure and every prohibited structural field;
14. synthetic sentinel leakage negatives for system IDs, internal IDs, Provider metadata, prompts, snippets, hashes,
    paths, timestamps, and exceptions;
15. private mapping completeness, reviewer membership, secondary duplication, and source commitment;
16. exact reviewer-manifest hashing: internal self-hash exclusion/insertion, ordinary complete-file hash after insertion,
    the private/outcome `reviewer_manifest_sha256` equality to only the internal value, the manifest entry in
    `reviewer_artifacts` equality to only the complete-file hash, and reopen/cross-artifact validation of both;
17. fresh create, complete idempotent reopen, fixed mapping-first/data/manifest-last publication order, and exact
    `created`, `resumed`, and `already_complete` outcome semantics;
18. private mapping absent with an exact partial reviewer bundle, proving create-only mapping-first reconstruction,
    preservation of existing exact reviewer bytes, and publication of only missing finals;
19. private mapping absent with all four exact reviewer data files but no completion manifest, proving mapping then
    completion-manifest publication;
20. private mapping absent with an exact complete reviewer bundle and completion manifest, proving only the mapping is
    published and the bundle is not accepted complete before mapping readback;
21. private mapping absent with one well-formed, internally consistent but deterministically differing reviewer file,
    and private mapping present but internally valid and deterministically different, proving respectively exactly
    `B3_OUTPUT_COLLISION` before mapping creation and exactly `B3_BLINDING_INCONSISTENT` without replacement;
22. interruption before and after the create-only atomic rename during mapping reconstruction, followed by exact reopen
    classification and successful reopen after exact reconstruction, with no reviewer rewrite or Provider recall;
23. interruption after every other publication boundary and exact missing-file resume;
24. failure before rename, uncertain failure after rename, owned-temp cleanup, and exact-final recovery;
25. a focused parameterized existing-file precedence matrix covering unexpected path/wrong object/prohibited collision,
    malformed UTF-8 or canonical JSON/schema, supported structure with wrong version, internal or cross-artifact hash
    mismatch, well-formed internally consistent reviewer bytes differing from expected, and an internally consistent
    private-mapping conflict. The expected categories are respectively `B3_OUTPUT_PATH_INVALID`,
    `B3_ARTIFACT_INVALID`, `B3_SCHEMA_VERSION_MISMATCH`, `B3_HASH_MISMATCH`, `B3_OUTPUT_COLLISION`, and
    `B3_BLINDING_INCONSISTENT`; every representative and deliberate multi-defect case must produce exactly one category
    in the global Section 7.6 order and preserve every existing final;
26. reviewer manifest as the last and only reviewer completion marker, including missing-dependency hash failure;
27. sanitized exception/outcome shape and absence of row content in captured stdout/stderr;
28. no executor, core, transport, client, tracker, Provider, network, `.env`, formal-generation, B4, or B5 call on any
    create, reopen, rejection, or recovery path;
29. generated-path ignore checks and proof that tests write only to the two temporary roots; and
30. Windows lock and atomic same-directory rename behavior where it is materially platform-specific.

Run:

```powershell
& $VenvPython -m pytest scripts/test_formal_evaluation_review_projection.py -q -p no:cacheprovider
```

The implementation task must first record the exact `--collect-only` count for this final test matrix. The focused run
passes only if the pytest pass count equals that recorded collection count, with zero failures, errors, skips, xfails,
or deselections. This contract does not fabricate a future parametrized pass total.

### 12.4 Compatibility suites

Run the touched B2/runner suites:

```powershell
& $VenvPython -m pytest scripts/test_formal_evaluation_store.py scripts/test_run_formal_evaluation.py -q -p no:cacheprovider
```

Run B1 compatibility:

```powershell
& $VenvPython -m pytest scripts/test_formal_evaluation_orchestration.py -q -p no:cacheprovider
```

Run Stage A compatibility:

```powershell
& $VenvPython -m pytest scripts/test_formal_evaluation_transport.py scripts/test_formal_evaluation_inflight.py -q -p no:cacheprovider
```

Run frozen identity, RQ3 runtime, and baseline compatibility:

```powershell
& $VenvPython -m pytest scripts/test_formal_evaluation_freeze.py scripts/test_formal_evaluation_runtime.py scripts/test_formal_qa_only_baseline_adapter.py -q -p no:cacheprovider
```

Before implementation edits, record each existing suite's exact pass count at the authorized baseline. After
implementation, each suite must have exit code 0 and its retained existing tests must equal or exceed that baseline
count only by expressly added tests; no existing test may be deleted, skipped, deselected, weakened, or reclassified.

Let `P_B3`, `P_store_runner`, `P_B1`, `P_A`, and `P_frozen` be the exact pytest pass counts reported by the five commands.
The implementation report must record each value and
`P_total = P_B3 + P_store_runner + P_B1 + P_A + P_frozen`. No PASS decision may use an estimated total.

### 12.5 Repository and ignore verification

Run:

```powershell
git diff --check
git diff --cached --check
git status --short --untracked-files=all
git check-ignore -q data/formal_eval/reviewer_projection/private/projection_manifest_v1.json
git check-ignore -q data/formal_eval/reviewer_projection/reviewer/manifest_v1.json
git ls-files -- data/formal_eval/reviewer_projection
```

Expected:

- both diff checks pass;
- only the four authorized tracked implementation paths differ from the implementation baseline;
- the two generated-path checks return ignored;
- `git ls-files` prints nothing for the generated root;
- no generated reviewer/private artifact exists in the repository after tests;
- no staging, commit, or push occurs during implementation or review unless separately assigned to the user-controlled
  lifecycle.

## 13. Acceptance criteria

### 13.1 PASS

Stage B3 implementation receives `PASS` only when all of the following are true:

- changes are confined to the four tracked-path allowlist;
- the freshly reconstructed run contract passes the Section 3.3 source gate before Stage B2 observation or any B3-root
  access, and either `offline_fake_only` or any synthetic resource produces exactly `B3_SOURCE_INELIGIBLE`;
- the current Stage B2 offline-fake/synthetic authority cannot produce a successful production reviewer projection,
  while test-owned eligible fixtures remain explicitly synthetic offline test evidence;
- the observation path reuses the complete Stage B2 validator, opens existing state read-only, and performs no private
  repair or execution;
- focused tests patch exactly the private B2 and B3 root-selection constants to distinct validated OS-temporary roots,
  never inspect the actual production roots, add no public root argument, and keep the B2 fault controller inactive
  except in a specifically named required interruption/fault test;
- projection requires the complete 190-unit canonical set and preserves all frozen counts, matrices, order in the
  private mapping, and fingerprint;
- no reviewer artifact can become private success, recovery, resume, or execution authority;
- all reviewer and private schemas, types, bounds, nullability, filenames, ordering, hashes, and field allowlists are
  exact;
- system identity, internal IDs, Provider metadata, prompts, retrieved/private context, paths, timestamps, exceptions,
  and mapping material do not leak to reviewer structure;
- legitimate display inputs, approved reviewer reference data, and exact canonical model answers are preserved;
- blinding and secondary selection are deterministic, collision-checked, reproducible, and privately reversible;
- the private mapping is complete, separate, ignored, create-only, and absent from the reviewer bundle; mapping absence
  permits only the exact reconstruction contract, while a malformed or differing present mapping always stops;
- the reviewer manifest's `manifest_sha256` and the private-manifest/outcome `reviewer_manifest_sha256` contain the same
  internal domain-separated self-hash, while only `reviewer_artifacts["manifest_v1.json"]` stores the ordinary
  complete-manifest-file hash;
- publication is create-only and atomic per file, reviewer manifest is last, interrupted projection resumes only from
  exact deterministic files, and conflicts are preserved rather than overwritten;
- every existing-path/file defect maps to exactly one category under the global Section 7.6 precedence, every error and
  reopen classification follows Section 10, and none can call or recall a Provider;
- all Section 12 checks pass with exact recorded counts and no unauthorized skip/deselection;
- real gate remains blocked and no network, Provider, canary, real mode, or formal generation is introduced.

### 13.2 CHANGES_REQUIRED

Independent review returns `CHANGES_REQUIRED` only for a concrete defect that could:

- expose condition identity, private mapping, protected content, or unnecessary customer-derived data;
- project a noncanonical, missing, contradictory, or alternate private result;
- change membership, request identity, system identity, turn relationships, execution order, or fingerprint;
- corrupt, overwrite, lose, ambiguously publish, or non-reproducibly regenerate reviewer artifacts;
- make required blinding or ordering nondeterministic;
- allow a reviewer artifact to influence private state or execution;
- permit a Provider call, recall, response regeneration, or unsafe retry;
- violate a frozen protocol/research rule or the exact B3 path/schema contract;
- fail a required offline verification.

Production-platform hardening preferences, optional refactoring, alternate naming preferences, additional telemetry,
database proposals, distributed locks, cloud storage, encryption-at-rest systems, dashboards, style preferences, and
speculative concerns are non-blocking unless tied to one of the concrete defects above.

## 14. Lifecycle and sequencing

The required lifecycle is atomic and must not be combined. Steps 1–3 are complete as recorded by this approval/freeze
publication; steps 4–8 remain future and separately authorized work:

1. independent, strictly read-only review of the exact reviewed-source candidate — complete with `PASS`;
2. bounded documentation-only correction if the review identifies a concrete contract defect — not required;
3. plan approval/freeze and a separate documentation publication commit — complete with this publication;
4. separately authorized B3 implementation limited to Section 11;
5. focused and compatibility verification under Section 12;
6. independent, strictly read-only implementation review;
7. separate implementation commit after accepted review;
8. user-controlled push.

Only after those steps may a later, separately authorized execution sequence consider B4, B5, canary, real execution,
formal generation, reviewer distribution, scoring, adjudication, or analysis.

## 15. Resolved design questions and conflict handling

### 15.1 Resolved choices

The following choices are closed for this approved and frozen contract:

- **Full set, not subset.** Reviewer publication requires all 190 canonical private commits. This avoids biased or
  accidentally selective review material.
- **Stage B2 commit authority.** A valid create-only private commit remains success even with B2-recognized repairable
  mutable lag. B3 observes without repairing and never requires a different success state.
- **Eligible authority only.** Canonical Stage B2 commit validity is necessary but not sufficient for projection. The
  freshly reconstructed run contract must also be non-`offline_fake_only` with every resource explicitly
  non-synthetic before B3 observes the commit set or touches its output root.
- **Typed JSON, not legacy CSV.** Closed typed JSON avoids spreadsheet interpretation and keeps scoring output separate.
  The legacy template function supplies useful naming/selection precedent but is not result authority.
- **Four data artifacts.** RQ1 primary, RQ1 secondary, RQ2, and RQ3 are separated because their reviewer roles and
  schemas differ. A fifth safe manifest closes integrity and completion.
- **Private mapping is B3.** It is necessary for reproducible later unblinding and paired analysis; deferring it would
  make the blind IDs irreversible. It remains private and contains no row text.
- **Mapping absence is recoverable; mismatch is not.** An absent mapping may be reconstructed create-only only from a
  fully revalidated eligible source when every existing reviewer final is exact. Any present malformed or differing
  mapping stops and is never reconstructed over.
- **Two manifest hashes, two locations.** `reviewer_manifest_sha256` is only the internal domain-separated self-hash;
  the ordinary hash of complete `manifest_v1.json` bytes exists only in its `reviewer_artifacts` entry.
- **One existing-file classification.** The global Section 7.6 precedence resolves overlapping path, parsing, version,
  hash, deterministic-byte, and private-mapping defects to one exact category before recovery is considered.
- **Derived private key, no credential.** Stable HMAC blinding is keyed by the validated private commit set, not a
  public seed, `.env`, random secret, or service.
- **No timestamps.** They are unnecessary, harm byte determinism, and may reveal execution/order information.
- **Reference minimization.** RQ1 exposes only question/reference answer; RQ2/RQ3 expose only fields needed to assess
  expected action, retrieval expectation, required content, and forbidden content. Gold categories, internal state
  expectations, reset flags, and source identifiers stay private.
- **No score fields.** Stage B3 produces immutable reviewer inputs. Later scoring must create separate artifacts keyed
  by blind IDs under separate authority.
- **No tracked schema artifact.** Exact code constants/dataclasses plus this frozen contract are sufficient for the
  narrow implementation; adding a frozen evaluation file would unnecessarily widen research-artifact scope.
- **No arbitrary paths or force mode.** Fixed ignored roots and create-only finals are adequate for the local tool.
  Focused tests patch only the two private B2/B3 root-selection constants to disjoint OS-temporary roots and add no
  public root parameter.

### 15.2 Open questions

None. No unresolved question remains that would materially change behavior, privacy, schema, output paths, frozen
identity, verification, or acceptance.

### 15.3 Future conflict handling

If independent review or implementation discovers that an exact requirement cannot be met without changing the frozen
protocol, reviewer design, scoring schema, formal manifest, request plan, plan fingerprint, generation settings,
Stage B2 success rules, or formal system identity:

1. stop B3 work;
2. preserve the worktree and evidence;
3. report the exact verifiable conflict;
4. obtain explicit authority for a pre-execution amendment;
5. complete independent amendment review and separate publication before any correction;
6. do not silently invent, migrate, alias, normalize, or relax the conflicting research requirement.

## 16. Approval/freeze safety statement

Approval and freeze change no substantive contract requirement. This document implements nothing and authorizes no
generated artifact. Formal execution has not started. Provider access, network access, real mode, canary, formal
response generation, reviewer operation, scoring, adjudication, B4, and B5 remain outside scope and unauthorized.
