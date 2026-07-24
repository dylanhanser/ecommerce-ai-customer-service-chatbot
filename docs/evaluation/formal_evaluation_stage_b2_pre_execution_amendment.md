# Stage B2 Pre-Execution Fault-Injection Amendment

Status: **DRAFT_PRE_EXECUTION_AMENDMENT — NOT_IMPLEMENTED — INDEPENDENT_REVIEW_REQUIRED**

This document is a draft normative amendment. It is not approved, has not been implemented, and authorizes no
implementation while it is being drafted or reviewed.

## 1. Identity, scope, and authority

| Item | Frozen value |
| --- | --- |
| Amended plan | `docs/evaluation/formal_evaluation_stage_b2_plan.md` |
| Frozen plan SHA-256 | `7bfb39de93701854a1a883d96de94015236ca88a2304d9ccb6faac14072e8435` |
| Repository baseline commit | `5d829a99d1975feddec32dfb5b6fa89a0e0b4d3a` |
| Normatively affected plan sections | Sections 12, 13, 14, 15, 23, 24, 26, 27, and 29 |
| Finding only; not amended | Section 28 frozen-resource and regression boundary |

This amendment supplements the frozen Stage B2 plan and overrides only the conflicting clauses identified in
Sections 2 and 3 below. Every Stage B2 requirement not expressly changed here remains unchanged and retains the
frozen plan as its authority.

This amendment does not retrospectively approve, validate, adopt, or review the preserved blocked implementation.
Its requirements derive only from the frozen plan and the tracked Stage A/B1 authorities at the repository baseline.

The nine affected sections have this exact scope:

- Section 12 retains the complete one-byte lock bootstrap, process-lock lifetime, normal-release, and unsupported-
  platform rules. It gains only the universal close-exception precedence and exception-preservation rule in Section 7
  of this amendment; no `run.lock` fault point is added.
- Section 13 retains the temporary-root and fixed-dependency restrictions but recognizes the extended controller as
  the only permitted persistence-fault mechanism.
- Section 14 retains its complete atomic-write protocol and gains only the deterministic hooks in Section 5 and the
  read-only test observation in Section 6 of this amendment.
- Section 15 retains every ordering rule and gains only the transition-specific hooks named in Section 5.
- Section 23 retains both B1 integration signatures, callback timing, callback return validation, and retry-predecessor
  behavior. It gains only the exact exception-preservation requirements in Section 7 and their controller-backed tests
  in Section 8.
- Section 24 retains the fixed private offline authority and `StoreError` vocabulary; references that restricted the
  controller to subprocess use are replaced by the direct-test and subprocess contract here.
- Section 26 retains every test obligation and is made executable only through the closed controller vocabulary here.
- Section 27 retains the controller type, installer, five marker/exit points, marker schema, exit codes, and subprocess
  cases, while its controller vocabulary and activation semantics are replaced by Sections 4–6 here.
- Section 29 retains every acceptance criterion; its “only subprocess fault mechanism” criterion is replaced by the
  requirement that this same private controller is the sole Stage B2 direct-test and subprocess fault mechanism.

No other plan section is amended.

## 2. Exact contradiction

Section 26, under “Atomic persistence”, requires injected failure at all of these locations:

1. before temporary-file creation;
2. during a partial write;
3. before or at flush;
4. at file `fsync`;
5. at close;
6. before Win32 publication;
7. after publication but before return;
8. during publication readback verification;
9. during mutable-pointer update; and
10. during temporary-file cleanup.

The same section requires verification that the old mutable state remains valid, immutable targets are not
overwritten, post-publication recovery is idempotent, and no best-effort fallback occurs. Sections 11, 14, 15, 16,
17, 23, and 26 additionally require observable failure behavior for archive-first publication, mutable replacement,
private-commit publication, post-call persistence, archive-tip repair, and cleanup.

At the same time:

- Section 13 permits tests to patch only the private root, use the fixed fake dependencies, and install the one
  Section 27 controller. It expressly forbids every other persistence patch.
- Section 27 freezes `_StageB2TestFaultControllerV1` as the sole private test-fault mechanism.
- Section 27 gives that controller only five literals:
  `after_call_started_published_exit`, `after_fake_client_returned_mark`,
  `after_fake_client_returned_exit`, `after_private_commit_published_exit`, and
  `after_committed_archive_published_exit`.
- Section 27 states that the controller can only mark or terminate.
- Sections 13 and 27 prohibit arbitrary persistence-primitive monkeypatching.

None of the five frozen literals can raise a deterministic failure before temp creation, after a partial write, at
flush, at file `fsync`, at close, before publication, during readback, during mutable replacement, or during cleanup.
Consequently, the Section 26 tests cannot be implemented while the Section 13/27 exclusivity rule is obeyed. The
requirements cannot be satisfied together without a normative amendment.

## 3. Chosen resolution

The sole resolution is:

> Extend `_StageB2TestFaultControllerV1` with the minimum closed set of persistence fault points required by the
> existing Stage B2 test obligations.

`_StageB2TestFaultControllerV1` remains the sole authorized Stage B2 fault-injection mechanism. Arbitrary
monkeypatching of `open`, file objects, `os.write`, `flush`, `os.fsync`, `close`, `MoveFileExW`, readback, `unlink`,
`Path` methods, Win32 APIs, or any persistence helper remains prohibited.

The controller remains a frozen dataclass with exactly the existing three fields, in the existing order:

```text
schema_version: int
root: Path
fault_point: str
```

The installer remains exactly
`_install_stage_b2_test_fault_controller_for_tests(root: Path, fault_point: str)`. No occurrence, operation, exception,
path, callback, response, or dependency parameter is added.

All five pre-existing frozen literals remain unchanged. No pre-existing literal is renamed, aliased, removed, or given
a different hook, marker, exit code, or continuation behavior. One amendment-added literal from the prior unapproved
draft is superseded below before approval and therefore has no retained alias.

## 4. Complete closed fault-point vocabulary

The complete effective controller vocabulary after this correction is exactly 23 string literals.

The five pre-existing frozen Section 27 literals are exactly:

```text
after_call_started_published_exit
after_fake_client_returned_mark
after_fake_client_returned_exit
after_private_commit_published_exit
after_committed_archive_published_exit
```

The 18 amendment-added literals are exactly:

```text
before_atomic_temp_create_error
after_atomic_temp_partial_write_error
before_atomic_temp_flush_error
before_atomic_temp_fsync_error
during_atomic_temp_close_error
before_atomic_publication_error
after_atomic_publication_before_readback_error
during_atomic_publication_readback_error
before_mutable_record_publication_error
before_post_call_archive_publication_error
before_private_commit_publication_error
before_owned_temp_cleanup_error
during_atomic_publication_recovery_readback_error
during_atomic_publication_recovery_invalid_bytes
during_atomic_temp_failure_then_close_error
during_atomic_publication_readback_then_close_error
during_atomic_publication_recovery_readback_then_close_error
during_atomic_publication_recovery_validation_then_close_error
```

The five pre-existing literals retain the exact frozen Section 27 semantics. Every other string and every non-string
value is invalid. No literal has an alias, alternate spelling, prefix match, suffix match, normalization, or
case-insensitive form.

`before_atomic_temp_close_error` is obsolete and invalid. It is not an alias. Its former pre-close-primary semantics
are removed. `during_atomic_temp_close_error` is the sole normative spelling for the normal temporary-file close
operation itself being the first failing operation.

The five pre-existing marker/exit literals remain the only points that write a fault marker. The 18 amendment-added
literals never create, modify, or read a fault marker. In the frozen marker schema, `fault_point` therefore remains
restricted to the five pre-existing marker/exit literals. The marker schema is not widened.

## 5. Normative persistence fault-point table

The following definitions are normative for the table:

- “Atomic JSON write” means exactly a Section 14 write of `run_contract.json`, an immutable attempt archive, a private
  commit, or a mutable current-journal record. It excludes the one-byte `run.lock` bootstrap and excludes Section 27
  marker files.
- A candidate has exact byte length `N` after canonical UTF-8 JSON plus the final LF has been constructed. Every
  candidate has `N >= 3`.
- “Raise IO” means raise exactly `StoreError("STORE_IO_FAILURE")`. The exception contains no added detail, path, raw
  exception text, or candidate content.
- “Stop” means the current store/orchestration call performs no later callback, journal transition, archive or mutable
  publication, private-commit publication, fake-client/Provider action, retry, reconciliation, progress derivation,
  public outcome construction, or formal-unit advancement.
- “Later reopen” means a separate later public durable invocation under a newly acquired run lock. It is not an
  automatic retry in the failing call and never enters the Provider retry loop.
- “Owned temp remains” means exactly the temp created for the candidate remains as one recognized sibling
  `.<target-name>.<cryptographic-random-hex>.tmp`; it is non-authoritative. The failing call does not delete it. A
  later reopen must remove it under the lock before durable-state loading continues.
- “First matching operation” means the first operation after controller installation whose exact hook matches the
  selected literal. Prerequisite state for a specific archive, commit, mutable update, or repair test must be created
  before installing the controller.

| Effective literal | Exact operation and trigger position | Bytes/filesystem mutation already completed | Injected behavior | Durable state when hook completes | Temporary-artifact state | Required reopen/recovery result | Retry permitted | Applicable operation or transition | Required test category |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `after_call_started_published_exit` | Exact frozen Section 27 point immediately after the `call_started` archive and matching mutable record pass readback, before tracker begin, proxy invocation, or fake-client entry. | Exact `call_started` archive and matching mutable record are durable and verified. | In the child, consume the trigger, create/read back the unchanged exact marker with archive tip, null commit, and call count `0`, then immediately call `os._exit(90)`. The trigger transition is not parent-observable. | `call_started` is authoritative. | No controller-created atomic temp remains. | Ordinary reopen validates `call_started`, makes zero fake calls, and returns the frozen permanent `call_started` result. | No retry or recall. | Existing pre-call subprocess crash boundary. | Unchanged frozen Section 27 exit-code, eight-field-marker, durable-state, and reopen assertions only; no post-exit accessor assertion. |
| `after_fake_client_returned_mark` | Exact frozen point inside `_FixedFakeRawClientV1`, after its call-count increment and closed response construction, before return to the proxy. | Durable tip remains `call_started`; fake call count is `1`. | Change `trigger_count` `0 -> 1`, create/read back the unchanged marker, and continue normally. | Frozen later success/failure persistence proceeds normally after the marker. | No controller-created atomic temp remains. | The same call completes normally; race test proves one valid marker/call/commit. | Only the frozen normal continuation; no controller retry. | Existing mark-only race point. | Unchanged frozen Section 27 exactly-one-call subprocess case. |
| `after_fake_client_returned_exit` | Same frozen post-fake-return point as the mark literal. | Durable tip remains `call_started`; fake call count is `1`; no post-call archive exists. | In the child, consume the trigger, create/read back the unchanged marker, then immediately call `os._exit(91)`. The trigger transition is not parent-observable. | `call_started` remains authoritative. | No controller-created atomic temp remains. | Ordinary reopen makes zero additional calls and returns the frozen permanent `call_started` result. | No retry or recall. | Existing post-call ambiguity subprocess crash boundary. | Unchanged frozen Section 27 exit-code, eight-field-marker, durable-state, and reopen assertions only; no post-exit accessor assertion. |
| `after_private_commit_published_exit` | Exact frozen point immediately after create-only private-commit publication and exact readback, before a local pointer archive or Provider reconciliation. | One valid commit and its frozen prepared/provider-returned pre-commit archive are durable. | In the child, consume the trigger, create/read back the unchanged marker, then immediately call `os._exit(92)`. The trigger transition is not parent-observable. | The exact commit is authoritative; its journal pointer may lag. | No source publication temp exists. | Ordinary reopen performs only the frozen local pointer repair or Provider reconciliation with zero calls. | No Provider retry or recall. | Existing local/Provider post-commit subprocess boundary. | Unchanged frozen Section 27 exit-code, eight-field-marker, durable-state, and reopen assertions only; no post-exit accessor assertion. |
| `after_committed_archive_published_exit` | Exact frozen Provider-only point immediately after sequence-4 committed archive publication/readback and before mutable-record replacement. | Valid Provider commit and committed archive are durable; mutable pointer may lag. | In the child, consume the trigger, create/read back the unchanged marker, then immediately call `os._exit(93)`. The trigger transition is not parent-observable. | The committed archive tip is authoritative. | No source publication temp exists. | Ordinary reopen advances only the mutable pointer, makes zero calls, and returns completed. | No retry or recall. | Existing committed-archive pointer subprocess boundary. | Unchanged frozen Section 27 exit-code, eight-field-marker, durable-state, and reopen assertions only; no post-exit accessor assertion. |
| `before_atomic_temp_create_error` | First matching atomic JSON write, after target/parent containment and candidate-byte construction, immediately before exclusive sibling-temp creation. | No candidate temp exists; target and directory entries are unchanged. | Raise IO and stop. | The previously authoritative target, archive tip, mutable record, and commit set remain unchanged. | No new temp exists. | Reopen derives the same decision from the unchanged durable state. | No retry in the failing call; later reopen is permitted; no Provider retry. | Run contract, any archive, any commit, or any mutable record. | Section 26 before-temp-creation; unchanged-state; no-action-after-failure. |
| `after_atomic_temp_partial_write_error` | First matching atomic JSON write, after exclusive temp creation and one unbuffered write of exactly the first `floor(N/2)` candidate bytes, before any remaining byte, flush, file `fsync`, close step, or publication. | One nonempty proper prefix has been written to the temp; target is unchanged. | Raise IO; the failure path invokes the mandatory temp-handle close exactly once and increments its Section 6 count; the consumed point injects nothing further; stop. | The prior target and every prior authoritative wrapper remain unchanged. | One owned temp remains and contains exactly the first `floor(N/2)` bytes. | Reopen removes that temp, then derives the decision from prior durable evidence. | No retry in the failing call; later cleanup/reopen only; no Provider retry. | Run contract, archive, commit, or mutable-record candidate. | Section 26 partial-write; truncated-temp cleanup; target non-publication. |
| `before_atomic_temp_flush_error` | First matching atomic JSON write, after the complete `N` bytes have been submitted to the temp file, immediately before the required `flush()`. | Temp exists and the complete candidate has been submitted; flush, file `fsync`, close step, and publication have not occurred. | Raise IO; the failure path invokes the mandatory temp-handle close exactly once and increments its Section 6 count; the consumed point injects nothing further; stop. | Prior authoritative state remains unchanged. | One owned temp remains; its bytes are non-authoritative regardless of OS buffering. | Reopen removes the temp and uses only prior durable evidence. | No retry in the failing call; later cleanup/reopen only; no Provider retry. | Every atomic JSON write. | Section 26 before/at-flush; no best-effort publication. |
| `before_atomic_temp_fsync_error` | First matching atomic JSON write, immediately after successful `flush()` and immediately before `os.fsync()` on the temp handle. | Temp exists and flush returned; file `fsync`, close step, and publication have not occurred. | Raise IO; the failure path invokes the mandatory temp-handle close exactly once and increments its Section 6 count; the consumed point injects nothing further; stop. | Prior authoritative state remains unchanged. | One owned temp remains and is non-authoritative. | Reopen removes the temp and uses only prior durable evidence. | No retry in the failing call; later cleanup/reopen only; no Provider retry. | Every atomic JSON write. | Section 26 file-fsync; durability-unproven temp rejection. |
| `during_atomic_temp_close_error` | First matching atomic JSON write when its mandatory normal temporary-file close is invoked, after the complete candidate write, `flush()`, and file `fsync()` have all succeeded. The close-attempt counter increments and the controller is consumed at entry to this one close invocation. | A complete flushed and file-fsynced owned temp exists; the target is unchanged; no earlier primary failure exists. | The one normal close invocation performs its one underlying handle-release operation and, before that same close invocation returns to its caller, creates and raises exact primary `P = StoreError("STORE_IO_FAILURE")`. Thus the close operation itself is the first and authoritative failure. Record exact `P`; do not enter a failure `finally` that closes again; stop. | Prior authoritative target, archive tip, mutable record, and commit set remain unchanged. No publication, verification, recovery readback, callback, Provider action, outcome, or formal-unit advancement occurs. | One fully written and file-fsynced but unpublished owned temp remains non-authoritative. Although the one underlying handle-release operation completed for deterministic injection, the handle is treated as indeterminate and unusable after the close reports failure. | A later ordinary reopen removes the recognized temp under the lock and derives state only from the last authoritative durable bytes. | No second close attempt, close retry, publication retry, Provider retry, or same-call continuation. | Mandatory normal temp close for every atomic JSON write. | Section 14/26 normal close itself as first failure; exact one close attempt; no earlier primary; exact trigger/negative observation; unpublished-temp cleanup. |
| `before_atomic_publication_error` | First matching atomic JSON write, after temp write, flush, file `fsync`, and close have succeeded, immediately before the exact `MoveFileExW` call. | A closed, file-fsynced owned temp exists; no publication/replacement mutation has occurred. | Raise IO and stop. | Immutable target remains absent or unchanged; old mutable target remains authoritative. | One complete owned temp remains. | Reopen removes the temp. For an archive candidate, the old tip remains authority; for a repair archive, the same repair is derived again; for a commit candidate, no commit exists; for a mutable candidate, the already durable unique archive tip is used to reconstruct/advance the pointer; for a contract candidate, no application state is authorized without the contract. | No retry in the failing call; deterministic later reopen/repair only; no Provider retry. | Exact Win32 publication for run contract, normal or repair archive, private commit, or mutable replacement. | Section 26 before-Win32-publication; immutable no-overwrite; archive/repair publication; mutable-old-state. |
| `after_atomic_publication_before_readback_error` | First matching atomic JSON write, immediately after `MoveFileExW` returns success and before opening the target for the first readback. | The immutable directory entry was created or the mutable entry was atomically replaced with write-through; no readback has occurred. | Raise IO internally. Because publication success is known, catch only this injected exception, perform exactly one fresh recovery readback, and return publication success only if exact bytes, canonical form, schema, and hash validate. If that recovery validation fails, raise its existing exact `StoreError` category and stop. | On successful recovery, the published target is authoritative. No second publication occurs. | The source temp no longer exists after successful `MoveFileExW`. | The same call completes the one recovery readback and continues; a later reopen sees the same canonical target and is idempotent. | Exactly one recovery readback is permitted; no publication retry and no Provider retry. | Successful create-only contract/archive/commit publication or mutable replacement. | Section 26 after-publication-before-return; idempotent post-publication recovery. |
| `during_atomic_publication_readback_error` | First matching atomic JSON write, after successful publication and after the target is opened for its first verification, immediately before the first byte read. | Publication succeeded; the first verification handle is open; no verification byte has been consumed. | Raise IO internally, close the first verification handle, perform exactly one new open and complete recovery readback, and return publication success only after exact validation. A failed recovery readback raises its existing exact `StoreError` category and stops. | On successful recovery, the one published target is authoritative; no second publication occurs. | No source temp exists. | Same-call recovery validates the target; later reopen is byte-idempotent. | Exactly one recovery readback is permitted; no publication retry and no Provider retry. | Readback of any successfully published contract, archive, commit, or mutable record. | Section 26 readback failure; exact-hash/canonical verification; no duplicate publication. |
| `before_mutable_record_publication_error` | First mutable-current-record write after installation, after its new referenced archive is durable and read back and after the mutable temp is written, flushed, file-fsynced, and closed, immediately before `MoveFileExW(..., MOVEFILE_REPLACE_EXISTING \| MOVEFILE_WRITE_THROUGH)`. | The unique archive tip is durable; old mutable record is absent or points to the earlier valid chain position; complete mutable temp exists. | Raise IO and stop. | The archive tip is authority. The old mutable record remains absent or unchanged and is never ahead. | One complete owned mutable temp remains. | Reopen removes the temp and reconstructs or advances only the mutable record to exact tip equality. If the tip is `call_started`, reopen makes zero fake calls and classifies it permanently non-executable; if the tip is a post-call state, no call is repeated; if it is a local/committed repair tip, only pointer repair occurs. | No retry in the failing call; later deterministic pointer repair only; no Provider retry. | Every normal or repair mutable-record publication, including prepared, call-started, post-call, local-pointer, committed, and lagging-pointer repair. | Section 26 mutable-pointer update; Section 11 archive-first repair; provider-ordering no-recall. |
| `before_post_call_archive_publication_error` | First attempt-archive candidate after installation whose exact validated event is sequence-3 `provider_returned`, `retryable_failed`, `terminal_failed`, or `uncertain`, after the fake client has returned and after the archive temp is written, flushed, file-fsynced, and closed, immediately before create-only publication. It never matches sequence-2 pre-send `retryable_failed`. | The fake call count is exactly one; durable tip remains `call_started`; no post-call archive, commit, or post-call mutable record exists. | Raise IO and stop. | `call_started` remains authoritative. No Provider result, failure classification, commit, reconciliation, or public outcome is published. | One complete owned archive temp remains. | Reopen removes the temp, validates `call_started`, performs zero additional fake calls, and returns the exact permanent `call_started` result. | No retry in the failing call or on reopen; Provider retry is prohibited. | B1 post-call callback for provider return or post-call retryable/terminal/uncertain transition. | Section 23 callback propagation; Section 26 post-call persistence and no-recall. |
| `before_private_commit_publication_error` | First private-commit candidate after installation, after exact result/success/checkpoint validation and after its temp is written, flushed, file-fsynced, and closed, immediately before create-only publication. | For Provider success the `provider_returned` archive/current state is durable; for local success the prepared archive/current state is durable; no commit exists. | Raise IO and stop. | No private commit is authoritative and no local-pointer or committed archive is created. Provider state remains `provider_returned`; local state remains `prepared`. | One complete owned commit temp remains. | Reopen removes the temp. Provider `provider_returned` without a commit fails closed with zero further calls. Local `prepared` without a commit may re-execute only the fixed deterministic local path and still makes zero fake calls. | No retry in the failing call; no Provider retry; only the frozen later local re-execution rule remains available for local state. | Provider or local first-success private-commit publication, including RQ3 Turn 1 result/checkpoint single-file commit. | Section 26 commit/reconciliation; RQ3 atomic commit; provider no-recall; local crash rule. |
| `before_owned_temp_cleanup_error` | First recognized owned-temp removal after installation, while holding the run lock, after exact owned-name, containment, regular-file, non-reparse, and target-category validation, immediately before the removal call. | No temp has been removed by this cleanup pass and no journal/archive/commit/contract loading, repair, reconciliation, publication, callback, or fake call has followed cleanup. | Raise IO and stop opening. | All durable targets remain unchanged and authoritative; no temp becomes authority. | The selected owned temp and every not-yet-processed owned temp remain. | A separate later reopen may attempt the same validated cleanup again; durable-state access remains blocked until all recognized temps are removed successfully. | No retry in the failing open; later cleanup invocation only; no Provider retry. | Contract/store open cleanup for every recognized Section 14 temp category. | Section 14 cleanup-failure block; Section 26 temp-cleanup injection; confinement. |
| `during_atomic_publication_recovery_readback_error` | First matching atomic JSON write, after successful publication and opening the first verification handle, immediately before its first byte read. This is one compound controller behavior: the single trigger first synthesizes the initial verification failure, then deterministically fails the sole recovery readback. | `MoveFileExW` succeeded; the canonical target is durable; the first verification handle is open; no verification byte has been consumed. | Atomically consume the controller; create and raise initial `P = StoreError("STORE_IO_FAILURE")` with exact null cause/context, false suppression, and no notes; catch and record exact `P`, close the first handle exactly once, then exit the handler for `P`. Recovery begins with no active handled exception. Open the one permitted recovery handle; immediately before its first byte read create and raise `R = StoreError("STORE_IO_FAILURE")` with exact null cause/context, false suppression, and no notes. Catch and record exact `R`, close the recovery handle exactly once, and propagate exact `R` only by the Section 7 bare-reraise structure. `P is not R`; both remain strongly retained through outer exit. | The one published canonical target is the durable authority, but the failing call returns no publication success and performs no later action. No second publication or recovery readback occurs. | No source temp exists after successful `MoveFileExW`. | A later ordinary reopen reads the actual canonical target, validates it, and treats the single publication idempotently. | No publication retry, second recovery readback, Provider retry, or same-call continuation. | Readback of any successfully published contract, archive, commit, or mutable record. | Failed internal recovery-readback I/O; deterministic handler exit; exact recovery identity/metadata/traceback suffix and handle tokens; single-trigger compound behavior. |
| `during_atomic_publication_recovery_invalid_bytes` | First matching atomic JSON write at the same post-publication, first-verification pre-read state. This is one compound controller behavior: the single trigger synthesizes the initial verification I/O failure and then makes the sole recovery validation receive one exact invalid detached byte buffer. | `MoveFileExW` succeeded; the canonical target is durable; the first verification handle is open; no verification byte has been consumed. | Atomically consume the controller; create, raise, catch, and record initial `P = StoreError("STORE_IO_FAILURE")` with exact null cause/context, false suppression, and no notes; close the first handle exactly once; exit the handler for `P`; then begin recovery with no active handled exception. Open the one recovery handle, read the complete actual target, and give only the validator exact detached `published_bytes[:-1]`. The existing validator creates and raises exact `V = StoreError("STORE_NONCANONICAL_JSON")` with null cause/context, false suppression, and no notes. Catch/record `V`, close the recovery handle once, and propagate exact `V` only by bare rereraise. Disk bytes are unchanged; `P is not V`; both are retained through outer exit. | The actual published canonical target remains the durable authority, but the failing call returns no publication success and performs no later action. No malformed byte is written and no second publication or recovery readback occurs. | No source temp exists. | A later ordinary reopen reads the unmodified canonical target, validates it, and treats the single publication idempotently. | No publication retry, second recovery readback, Provider retry, or same-call continuation. | Recovery validation of any successfully published contract, archive, commit, or mutable record. | Failed internal recovery validation; deterministic handler exit; exact validation identity/metadata/traceback suffix and handle tokens. |
| `during_atomic_temp_failure_then_close_error` | First matching atomic JSON write of the target category reached after installation. This one compound literal has an exact closed target-category mapping: `run_contract.json` triggers after writing exactly `floor(N/2)` bytes; an immutable attempt archive triggers after all `N` bytes are submitted and immediately before `flush()`; a private commit triggers immediately after successful `flush()` and before file `fsync`; a mutable record triggers immediately after successful file `fsync` and before its normal close. No other phase or target mapping exists. | Run contract: one nonempty proper prefix temp. Archive: complete submitted temp, not flushed. Commit: complete temp with successful flush, not file-fsynced. Mutable: complete flushed and file-fsynced temp; its referenced unique archive tip is already durable, while the old mutable record is absent or lagging. No mapped target has been published. | At the mapped phase create and raise `P = StoreError("STORE_IO_FAILURE")` with null cause/context, false suppression, and no notes. Catch/record exact `P` and its lower traceback suffix; with `P` active invoke the exact opened temp handle's close once. That close releases the handle then creates/raises `C = StoreError("STORE_IO_FAILURE")`, for which cause is null, context is exact `P`, suppression is false, and notes are empty. Catch/record `C`, leave its handler, then bare-reraise exact unchanged `P` from the outer handler. The recorded opened and close-attempt tuples are the same one token. | Run contract: no application durable state is authorized beyond the lock sentinel. Archive/commit: the prior archive tip, mutable record, and commit set remain authoritative. Mutable: the newly referenced archive tip is authoritative and the old mutable record remains absent or lagging. No later callback, publication, or action occurs. | Exactly one mapped owned temp remains non-authoritative with the bytes/state stated at left. The handle is physically released by the one underlying close but is treated as indeterminate and unusable by the failing call. | A later ordinary reopen removes the owned temp under the lock. Run-contract reopen creates the exact contract only if the frozen missing-contract rule permits; archive/commit reopen uses prior durable evidence and its frozen state decision; mutable reopen reconstructs or advances only the pointer to the unique durable tip. | No close retry, write/flush/`fsync` retry, publication retry, Provider retry, or same-call continuation. | Closed pre-publication secondary-close coverage for run contract, attempt archive, private commit, and mutable record. | Four exact target-category tests for partial-write, flush, file-`fsync`, and pre-close primary phases; exact identities/metadata/traceback suffix/handle token; primary precedence; no chaining; one close; target-specific state/reopen result. |
| `during_atomic_publication_readback_then_close_error` | First matching atomic JSON write, after successful publication and opening the first verification handle, immediately before its first byte read. This is the materially distinct post-publication primary-error-plus-verification-handle-close path. | `MoveFileExW` succeeded; the canonical target is durable; the first verification handle is open; no verification byte has been consumed. | Create/raise/catch authoritative `P = StoreError("STORE_IO_FAILURE")` with null cause/context, false suppression, and no notes. With `P` active close the exact recorded first-verification handle once. The close releases it then creates/raises `C` with null cause, exact context `P`, false suppression, and no notes. Catch/record `C`, leave its handler, refresh `P`'s lower traceback suffix, and bare-reraise exact unchanged `P` from the outer handler. The first-verification opened and close-attempt tuples are the same token. Recovery is forbidden. | The one published canonical target is durable authority, but the failing call returns no publication success and performs no later action. No republication or recovery readback occurs. | No source temp exists. The verification handle is physically released by the one underlying close but is treated as indeterminate and unusable by the failing call. | A later ordinary reopen reads and validates the actual canonical target and treats the single publication idempotently. | No close retry, recovery readback, publication retry, Provider retry, or same-call continuation. | First verification-handle close before post-publication recovery for any atomic target. | Exact identities, metadata, lower traceback suffix, primary precedence, no `C` frame in `P`, recovery suppression, and post-publication state preservation. |
| `during_atomic_publication_recovery_readback_then_close_error` | First matching atomic JSON write at the post-publication first-verification pre-read state. One consumed trigger creates/raises/catches initial verification `P`, records it, closes the first verification handle normally once, exits `P`'s handler, and only then enters recovery with no active handled exception. The recovery handle opens; immediately before its first byte read exact recovery primary `R` is created and raised with null cause/context, false suppression, and no notes. | The initial publication succeeded exactly once; the canonical target is durable; the source temp no longer exists; the first verification failed and its handle closed once; the recovery handle is open; no recovery byte has been read. | Catch/record exact `R`; with `R` active close the exact recorded recovery handle once. The close releases it then creates/raises `C` with null cause, exact context `R`, false suppression, and no notes. Catch/record `C`, leave its handler, refresh `R`'s lower traceback suffix, and bare-reraise unchanged `R`. Opened and close-attempt tuples match for the first-verification and recovery families. | The one canonical published target remains authoritative. No second recovery readback, republication, later persistence, callback, journal transition, archive, private commit, Provider action, outcome, progress derivation, or formal-unit advancement occurs. | No source temp exists. The recovery handle is physically released by its one underlying close but is treated as indeterminate and unusable by the failing call. | A later ordinary reopen reads only the canonical durable target, validates it, and treats the single publication idempotently. | No close retry, second recovery readback, publication retry, Provider retry, or same-call continuation. | Recovery-handle close while exact recovery-read I/O primary `R` is active, for any atomic target. | Exact `P`, `R`, and `C` lifetime/metadata/traceback/handle observation; deterministic handler exit; one recovery and one recovery close. |
| `during_atomic_publication_recovery_validation_then_close_error` | First matching atomic JSON write at the same post-publication first-verification pre-read state. One consumed trigger creates/raises/catches initial `P`, records it, closes the first verification handle normally once, exits `P`'s handler, then opens the sole recovery handle with no active handled exception, reads the canonical target, and gives the validator exact detached `published_bytes[:-1]`. The validator creates/raises exact `V` with null cause/context, false suppression, and no notes; disk bytes are unchanged. | The initial publication succeeded exactly once; the canonical target is durable; the source temp no longer exists; the first verification failed and its handle closed once; one recovery read completed; exact validation primary `V` is active. | Catch/record exact `V`; with `V` active close the exact recorded recovery handle once. The close releases it then creates/raises `C` with null cause, exact context `V`, false suppression, and no notes. Catch/record `C`, leave its handler, refresh `V`'s lower traceback suffix, and bare-reraise unchanged `V`. Opened and close-attempt tuples match for both verification families. | The unmodified canonical published target remains authoritative. No second recovery readback, republication, later persistence, callback, journal transition, archive, private commit, Provider action, outcome, progress derivation, or formal-unit advancement occurs. | No source temp exists. The recovery handle is physically released by its one underlying close but is treated as indeterminate and unusable by the failing call. | A later ordinary reopen reads only the unmodified canonical durable target, validates it, and treats the single publication idempotently. | No close retry, second recovery readback, publication retry, Provider retry, or same-call continuation. | Recovery-handle close while exact recovery canonical-validation primary `V` is active, for any atomic target. | Exact `P`, `V`, and `C` lifetime/metadata/traceback/handle observation; deterministic handler exit; one recovery and one recovery close. |

For the four immediate-exit rows in this table, `trigger_count` and the described pre-exit controller action are
child-local behavior, not parent-observed evidence. Their executable positive test category is limited by Sections 8
and 13.3 to the exact frozen exit code, unchanged eight-field marker, and expressly authorized durable/reopen facts.
No post-exit 50-field accessor observation, `K`/`H` tuple, controller metadata, counter not recorded in the marker,
handle/exception identity, or exception group is required or implied. The mark-only row is unaffected.

The invalid-byte recovery case is separately required by the original frozen plan. Section 14 requires the
post-publication readback to validate exact target bytes and canonical hash and separately requires truncated or
malformed targets to fail closed; Section 26 requires both publication-readback fault injection and proof that no
corrupt, partial, noncanonical, unread, or hash-invalid wrapper becomes authoritative. An I/O-only failed recovery
cannot prove the validation branch. Therefore `during_atomic_publication_recovery_invalid_bytes` is mandatory in
addition to `during_atomic_publication_recovery_readback_error`; neither is an alias or an alternative to the other.

For a failed first `run_contract.json` publication, its one recognized temp is not application durable state for
`STORE_STATE_WITHOUT_CONTRACT`. On the later reopen, while holding the run lock, that exact temp is removed before the
state-without-contract decision. If no other non-lock durable state exists, the freshly derived exact contract is then
published create-only. If any other non-lock durable state exists, `STORE_STATE_WITHOUT_CONTRACT` remains mandatory.
This is the exact Section 16 “before contract publication” recovery row; it creates no general missing-contract
repair.

There is no parent-directory `fsync` fault point. The frozen Windows atomicity contract requires file `fsync` followed
by `MoveFileExW` with `MOVEFILE_WRITE_THROUGH`; it does not require or authorize a parent-directory handle or
parent-directory `fsync`. This amendment does not add a new durability primitive. Publication durability remains
exactly the frozen Win32 write-through contract, and missing Win32 capability remains
`STORE_DURABILITY_UNAVAILABLE`.

## 6. Controller activation and trigger semantics

### Read-only trigger observation contract

The one and only test observation interface is the module-private accessor
`formal_evaluation_store._stage_b2_test_fault_observation_for_tests`. No second accessor, hidden selector, mutable
record, direct controller-state inspection, or controller-returning API exists. Its signature is exactly:

```python
def _stage_b2_test_fault_observation_for_tests(
    fault_point: str,
) -> _StageB2TestFaultObservationV1
```

It accepts exactly one positional argument. `fault_point` must have exact type `str` and equal the one literal armed by
the active installer context.

The exact immutable return type is the module-private type
`formal_evaluation_store._StageB2TestFaultObservationV1`, with exactly 50 fields in this exact order:

```python
@dataclass(frozen=True, slots=True)
class _StageB2TestFaultObservationV1:
    schema_version: int
    fault_point: str
    controller_identity: int
    controller_root: str
    owner_pid: int
    owner_thread_id: int
    trigger_count: int
    publication_attempt_count: int
    successful_publication_count: int
    initial_verification_readback_attempt_count: int
    recovery_readback_attempt_count: int
    atomic_temp_close_attempt_count: int
    initial_verification_handle_close_attempt_count: int
    recovery_readback_handle_close_attempt_count: int
    temporary_opened_handle_ids: tuple[int, ...]
    temporary_close_attempt_handle_ids: tuple[int, ...]
    initial_verification_opened_handle_ids: tuple[int, ...]
    initial_verification_close_attempt_handle_ids: tuple[int, ...]
    recovery_opened_handle_ids: tuple[int, ...]
    recovery_close_attempt_handle_ids: tuple[int, ...]
    initial_exception_id: int | None
    initial_exception_type: str | None
    initial_exception_category: str | None
    initial_exception_args: tuple[str, ...] | None
    initial_exception_cause_id: int | None
    initial_exception_context_id: int | None
    initial_exception_suppress_context: bool | None
    initial_exception_notes: tuple[str, ...] | None
    initial_exception_traceback_ids: tuple[int, ...] | None
    initial_exception_retained: bool | None
    primary_exception_id: int | None
    primary_exception_type: str | None
    primary_exception_category: str | None
    primary_exception_args: tuple[str, ...] | None
    primary_exception_cause_id: int | None
    primary_exception_context_id: int | None
    primary_exception_suppress_context: bool | None
    primary_exception_notes: tuple[str, ...] | None
    primary_exception_traceback_ids: tuple[int, ...] | None
    primary_exception_retained: bool | None
    secondary_exception_id: int | None
    secondary_exception_type: str | None
    secondary_exception_category: str | None
    secondary_exception_args: tuple[str, ...] | None
    secondary_exception_cause_id: int | None
    secondary_exception_context_id: int | None
    secondary_exception_suppress_context: bool | None
    secondary_exception_notes: tuple[str, ...] | None
    secondary_exception_traceback_ids: tuple[int, ...] | None
    secondary_exception_retained: bool | None
```

`schema_version` has exact built-in type `int`, never `bool`, and value `1`. `fault_point` is the exact armed literal.
`controller_identity` is the positive exact built-in `int` returned by `id()` for the installed
`_StageB2TestFaultControllerV1` object. `controller_root` is the exact built-in `str` produced once at successful
installation by `os.path.normcase(str(root.resolve(strict=True)))`; on Windows it is absolute, uses the platform's
normalized separators and case, and equals the identically normalized active private-root constant. `owner_pid` is
the positive exact built-in `int` from `os.getpid()`. `owner_thread_id` is the nonzero exact built-in `int` from
`threading.get_ident()`. The installed controller object and every recorded handle and exception object remain backed
by separate private strong references until the successfully installed outer context exits.

The accessor reads only the active controller and observation state in its current process. It cannot inspect,
recover, reconstruct, or serialize another process's controller state. In particular, after a child calls immediate
`os._exit`, the parent cannot call the child's process-local accessor or recover its 50-field record. Immediate
`os._exit` runs no later accessor, installer cleanup path, `finally`, `atexit`, or ordinary exception propagation that
could make that record observable to the parent. Only data already written to an authorized cross-process artifact
before exit is parent-observable. For the four immediate-exit literals, that artifact remains solely the unchanged
frozen eight-field marker, together with the frozen child exit status and any durable filesystem evidence that frozen
Section 27 expressly authorizes the parent to inspect. No child-local `K` or `H` tuple, controller field or metadata,
counter absent from that marker, handle or exception identity, exception object, exception group, or other unrecorded
state may be asserted as a parent-observed fact. A value's existence in the child before exit does not make it
observable to the parent.

`trigger_count` is exactly `0` or `1`. Every operation-attempt/count field is a nonnegative exact built-in `int`, never
`bool`, with no upper clamp. A prohibited second publication, readback, recovery, or close attempt therefore becomes
observable as `2` even after trigger consumption.

The exact event for every scalar count is:

1. `trigger_count` changes `0 -> 1` atomically at the first exact matching hook, before that hook's injected behavior.
2. `publication_attempt_count` increments immediately after the before-publication hook returns normally and
   immediately before each actual `MoveFileExW` invocation. A failure at that before-publication hook therefore leaves
   this count unchanged.
3. `successful_publication_count` increments immediately after that actual `MoveFileExW` returns success and before
   the after-publication hook, first-verification phase, or any caller continuation.
4. `initial_verification_readback_attempt_count` increments once on entry to each required first-verification phase,
   after successful publication and before the after-publication-before-readback hook or first-verification handle open.
5. `recovery_readback_attempt_count` increments once on entry to each permitted recovery-readback phase, after the
   initial `P` handler and first-verification close have both completed and immediately before recovery-handle open.
6. `atomic_temp_close_attempt_count`, `initial_verification_handle_close_attempt_count`, and
   `recovery_readback_handle_close_attempt_count` each increment immediately before the corresponding actual close
   invocation and in the same locked state change that appends that actual close argument's identity.

No counter is decremented or cleared while the outer installer context remains active. Trigger consumption does not
disable any operation-count increment.

Every handle-identity field is an exact built-in tuple containing only positive exact built-in integers:

1. Immediately after an actual temporary, initial-verification, or recovery handle open returns successfully, and
   before any byte operation or matching post-open hook, append `id(handle)` to that family's opened tuple.
2. Immediately before every actual close invocation, append `id(the_handle_actually_passed_to_close)` to that family's
   close-attempt tuple, then increment the matching close-attempt counter.
3. A failed open appends nothing. A second successful open appends a second token. A second close attempt appends a
   second token even after trigger consumption. Closing the same handle twice yields `(T,T)`; closing a different
   handle yields a different token such as `U`.
4. The strong-reference table retains every successfully opened handle object and every different handle object
   actually passed to close until outer-context exit, so a token cannot be misleadingly reused during an installation.
5. The exact invariants are:
   `atomic_temp_close_attempt_count == len(temporary_close_attempt_handle_ids)`,
   `initial_verification_handle_close_attempt_count ==
   len(initial_verification_close_attempt_handle_ids)`, and
   `recovery_readback_handle_close_attempt_count == len(recovery_close_attempt_handle_ids)`.
   For every conforming one-open/one-close path, the applicable opened tuple is exactly `(T,)` and its close-attempt
   tuple is exactly the same `(T,)`. No close permitted means the close tuple is exactly `()`.
6. The returned record exposes only detached integer tuples. It never exposes a handle, controller, exception,
   mutable container, counter object, callback, setter, or private strong-reference table.

The exception roles are exact:

- `initial_exception_*` describes only the internally caught first-verification
  `P = StoreError("STORE_IO_FAILURE")` that starts an allowed post-publication recovery branch. It is wholly absent for
  a behavior that does not leave that initial handler and enter recovery.
- `primary_exception_*` describes the authoritative `P`, `R`, or `V` that escapes the atomic-write/store call. It is
  wholly absent from returned records for successful recovery and the accessor-observable mark-only continuation.
  An immediate-exit literal produces no post-trigger returned record, so the parent must not reinterpret its
  unobservable exception group as an observed ten-field absence.
- `secondary_exception_*` describes only the caught and suppressed close exception `C`. It is wholly absent unless an
  exact primary-plus-secondary-close behavior creates `C`.

An absent exception group has `None` in all ten fields. A present group populates all ten fields atomically:

- positive `id()` identity;
- exact type string `"formal_evaluation_store.StoreError"`;
- exact category;
- a newly detached exact built-in `tuple` equal to `args`;
- `id(__cause__)` or `None`;
- `id(__context__)` or `None`;
- exact built-in `bool` `__suppress_context__`;
- exact built-in tuple equal to `tuple(__notes__)`, or exact `()` when `__notes__` is absent;
- an exact built-in tuple of positive `id()` values for the traceback objects, in head-to-tail order, at the frozen
  lower observation boundary; and
- exact built-in `True`, asserting that the private strong-reference table contains that exact exception object at
  the snapshot event.

The exact exception-field events are closed. A caught first-verification `P` is recorded privately immediately on
entry to its handler. For the before-open S0 path, its complete initial group becomes observable immediately after
that recording and before handler exit. For an after-open path, its complete initial group becomes observable
immediately after the one successful first-verification close and before handler exit. If that close instead raises
`C`, the initial group remains wholly absent and the same authoritative `P` populates the ten `primary_exception_*` fields.
Any escaping `P`, `R`, or `V` populates the primary group immediately upon its authoritative catch and before its
mandatory close. A caught suppressed close `C` populates the secondary group immediately on entry to the inner `C`
handler and before that handler exits. For a primary with a secondary close, only its
`primary_exception_traceback_ids` value is refreshed, exactly once after the inner handler exits and immediately before
the outer bare rereraise, to capture the final lower-boundary suffix; every other primary field remains unchanged.
Without a secondary close, the traceback tuple is captured at the authoritative lower catch boundary. No returned
snapshot can expose a partially populated group.

For every controller-created I/O primary and for validator-created `V`, the initial metadata at creation is
deterministic: `__cause__ is None`, `__context__ is None`, `__suppress_context__ is False`, and no notes. Their exact
detached metadata, apart from identity and traceback tuple, is:

```text
IO primary = ("formal_evaluation_store.StoreError",
              "STORE_IO_FAILURE",
              ("STORE_IO_FAILURE",),
              None, None, False, (), True)
NC primary = ("formal_evaluation_store.StoreError",
              "STORE_NONCANONICAL_JSON",
              ("STORE_NONCANONICAL_JSON",),
              None, None, False, (), True)
```

For a controller-created close secondary `C`, `__cause__ is None`, `__context__` is the exact active authoritative
primary object, `__suppress_context__ is False`, and no notes exist. The primary itself retains its exact prior cause,
context, suppression, notes, type, arguments, category, identity, and traceback suffix.

The exact recovery exception-lifetime and handler ordering is:

1. Create and raise initial verification `P` with no active handled exception.
2. Catch exact `P`; record its identity, complete metadata, traceback chain, and strong reference.
3. While `P` is the active handled exception, close the first verification handle exactly once. If that close creates
   `C`, record `C` with `C.__context__ is P`, suppress `C`, promote the same `P` to the authoritative primary group,
   refresh the lower-boundary traceback suffix, and bare-reraise `P`; recovery is forbidden.
4. If the close succeeds, exit the handler for `P` completely. The retained strong reference is not an active handled
   exception.
5. Only after handler exit begin recovery. Recovery starts with no active handled exception.
6. Create and raise recovery I/O `R`, or invoke the exact canonical validator that creates and raises `V`, only in that
   no-active-exception state. Therefore `R` and `V` begin with exact null cause and context, false suppression, and no
   notes.
7. Catch exact `R` or `V`; record it as primary; while it is the active handled exception close the recovery handle
   exactly once. If close creates `C`, `C.__context__` is the exact `R` or `V`, while `C` has null cause, false
   suppression, and no notes. Suppress `C`, refresh the primary's lower-boundary traceback suffix, then bare-reraise
   the unchanged recovery primary.
8. No implementation may create `R` or `V` inside the handler for initial `P`, and no alternative handler nesting is
   permitted. The same creation, raising, catch, recording, handler-exit, close, and bare-reraise ordering governs
   every pre-publication or verification primary-plus-secondary-close path.

For exact expected-record notation, define:

```text
K = (trigger_count,
     publication_attempt_count,
     successful_publication_count,
     initial_verification_readback_attempt_count,
     recovery_readback_attempt_count,
     atomic_temp_close_attempt_count,
     initial_verification_handle_close_attempt_count,
     recovery_readback_handle_close_attempt_count)

H = (temporary_opened_handle_ids,
     temporary_close_attempt_handle_ids,
     initial_verification_opened_handle_ids,
     initial_verification_close_attempt_handle_ids,
     recovery_opened_handle_ids,
     recovery_close_attempt_handle_ids)
```

Define `ABSENT` as ten `None` values. Define
`IO(x,q,ctx)` and `NC(x,q,ctx)` as the complete ten-field group with identity `x`, the exact I/O or noncanonical
metadata above, cause ID `None`, context ID `ctx`, traceback tuple `q`, and retained value `True`. `q` is a nonempty
head-to-tail tuple of traceback-object IDs captured at that group's frozen lower boundary. Differently named object
tokens are pairwise distinct. The complete live-token vocabulary is `t` (temporary handle), `i`
(first-verification handle), `hr` (recovery handle), `p` (initial exception), `er` (recovery I/O exception), `v`
(recovery validation exception), and `c` (secondary close exception). `hr != er`; every concurrently live handle token
is unequal to every concurrently live exception token; and `p`, `er`, `v`, and `c` are pairwise unequal whenever they
are concurrently live. The private strong-reference table retains every such object through installer-context exit.
The exact positive vectors are:

| Vector | Exact `K` | Exact `H` | Initial group | Primary group | Secondary group |
| --- | --- | --- | --- | --- | --- |
| `B` | `(1,0,0,0,0,0,0,0)` | `((),(),(),(),(),())` | `ABSENT` | `IO(p,qp,None)` | `ABSENT` |
| `T` | `(1,0,0,0,0,1,0,0)` | `((t,),(t,),(),(),(),())` | `ABSENT` | `IO(p,qp,None)` | `ABSENT` |
| `S0` | `(1,1,1,1,1,1,0,1)` | `((t,),(t,),(),(),(hr,),(hr,))` | `IO(p,qp,None)` | `ABSENT` | `ABSENT` |
| `S1` | `(1,1,1,1,1,1,1,1)` | `((t,),(t,),(i,),(i,),(hr,),(hr,))` | `IO(p,qp,None)` | `ABSENT` | `ABSENT` |
| `FR` | `(1,1,1,1,1,1,1,1)` | `((t,),(t,),(i,),(i,),(hr,),(hr,))` | `IO(p,qp,None)` | `IO(er,qer,None)` | `ABSENT` |
| `FV` | `(1,1,1,1,1,1,1,1)` | `((t,),(t,),(i,),(i,),(hr,),(hr,))` | `IO(p,qp,None)` | `NC(v,qv,None)` | `ABSENT` |
| `TC` | `(1,0,0,0,0,1,0,0)` | `((t,),(t,),(),(),(),())` | `ABSENT` | `IO(p,qp,None)` | `IO(c,qc,p)` |
| `VC` | `(1,1,1,1,0,1,1,0)` | `((t,),(t,),(i,),(i,),(),())` | `ABSENT` | `IO(p,qp,None)` | `IO(c,qc,p)` |
| `RC` | `(1,1,1,1,1,1,1,1)` | `((t,),(t,),(i,),(i,),(hr,),(hr,))` | `IO(p,qp,None)` | `IO(er,qer,None)` | `IO(c,qc,er)` |
| `VRC` | `(1,1,1,1,1,1,1,1)` | `((t,),(t,),(i,),(i,),(hr,),(hr,))` | `IO(p,qp,None)` | `NC(v,qv,None)` | `IO(c,qc,v)` |
| `PC` | `(1,2,2,2,0,3,2,0)` | `((t1,t2,t3),(t1,t2,t3),(i1,i2),(i1,i2),(),())` | `ABSENT` | `IO(p,qp,None)` | `ABSENT` |
| `PP` | `(1,4,4,4,0,5,4,0)` | `((t1,t2,t3,t4,t5),(t1,t2,t3,t4,t5),(i1,i2,i3,i4),(i1,i2,i3,i4),(),())` | `ABSENT` | `IO(p,qp,None)` | `ABSENT` |

`B` applies before temp creation and during owned-temp cleanup. `T` applies after a temp has opened and to every
pre-publication simple primary, including the local private-commit integration branches. `S0` and `S1` are the two
successful-recovery branches. `FR` and `FV` are failed recovery. `TC`, `VC`, `RC`, and `VRC` are the four exact
secondary-close families. `PC` is the full post-call callback integration from an already durable prepared tip:
call-started archive and mutable publication succeed, the fake call occurs once, then the post-call archive temp
closes and its before-publication hook fails. `PP` is the full Provider private-commit integration from an already
durable prepared tip: call-started archive/mutable and provider-returned archive/mutable publication succeed, one fake
call occurs, then the commit temp closes and its before-publication hook fails.

Every positive branch below has a separate missing-trigger negative context. In that negative context the same literal
is armed and the accessor is called immediately, before any store operation or hook. Its exact record retains the
active controller identity/root/PID/thread but has
`K = (0,0,0,0,0,0,0,0)`, `H = ((),(),(),(),(),())`, and all three exception groups `ABSENT`.
The negative context then exits without a store action. Thus every row has its own exact all-zero-count/all-empty-handle
negative and does not depend on another row, second literal, hidden selector, race, malformed production input, or raw
persistence spy.

The complete branch vocabulary used by the transition matrix is:

| Branch | Exact prerequisite before installer entry | Selected operation | Exact durable/temporary state and later reopen |
| --- | --- | --- | --- |
| `RUN_CONTRACT` | Valid lock infrastructure; no contract and no non-lock durable state. | First create-only `run_contract.json` write. | A pre-publication failure leaves no application durable state and leaves either no temp for `B` or one recognized contract temp for every other pre-publication vector; reopen removes the temp if present and creates the exact contract. A post-publication vector leaves the one canonical contract and no source temp; successful recovery continues, while an escaping primary stops and later reopen validates that same contract. |
| `PREPARED_ARCHIVE` | Exact contract; no evidence for the selected unit; exact sequence-1 prepared archive candidate constructed before installation. | Create-only prepared archive write. | Pre-publication failure leaves no unit evidence; reopen may begin the same exact unit. Post-publication vector leaves the unique prepared archive tip and no source temp; reopen creates the matching mutable record and classifies same-attempt continuable. |
| `LOCAL_REPAIR_ARCHIVE` | Exact local commit, exact sequence-1 prepared archive/current record, and no sequence-2 pointer archive. | Create-only sequence-2 repeated-prepared local repair archive. | Pre-publication failure leaves commit plus sequence-1 prepared authority; reopen appends the same repair archive and advances the mutable pointer. Post-publication vector leaves the repair archive authoritative and reopen advances only the pointer. No fake call occurs. |
| `PROVIDER_REPAIR_ARCHIVE` | Exact Provider commit and exact sequence-3 provider-returned archive/current record, with no sequence-4 committed archive. | Create-only sequence-4 committed repair archive. | Pre-publication failure leaves commit plus provider-returned authority; reopen performs the same public reconciliation. Post-publication vector leaves the committed archive authoritative and reopen advances only the mutable pointer. No fake call occurs. |
| `PROVIDER_COMMIT` | Exact non-RQ3 Provider result/success candidate and sequence-3 provider-returned archive/current record, all constructed before installation. | Isolated create-only private-commit write. | Pre-publication failure leaves no commit and provider-returned authority; reopen is permanently non-executable with zero calls. Post-publication vector leaves the exact commit authoritative; later reopen reconciles with zero calls. |
| `PREPARED_MUTABLE` | Exact sequence-1 prepared archive is durable; its mutable record is absent. | Mutable publication to that exact tip. | Pre-publication failure leaves the prepared archive authoritative and one recognized mutable temp except for `B`; reopen creates the exact pointer and remains continuable. Post-publication vector leaves exact archive/mutable equality. |
| `CALL_STARTED_MUTABLE` | Exact sequence-2 call-started archive is durable; mutable record is absent or points to sequence 1. | Mutable publication to call-started. | Failure leaves call-started archive authority; reopen repairs the pointer, makes zero fake calls, and returns the permanent call-started result. |
| `PRE_SEND_RETRYABLE_MUTABLE_A1` | Exact attempt-1 sequence-2 pre-send retryable-failed archive is durable; mutable points to prepared. | Mutable publication to that attempt-1 retryable tip. | Failure leaves the exact archive authoritative; reopen repairs the pointer and the next eligible invocation constructs attempt 2. No fake call occurs. |
| `PRE_SEND_RETRYABLE_MUTABLE_A2` | Exact attempt-2 sequence-2 pre-send retryable-failed archive and predecessor lineage are durable; mutable points to attempt-2 prepared. | Mutable publication to that attempt-2 retryable tip. | Failure leaves the exact archive authoritative; reopen repairs the pointer and the next eligible invocation constructs attempt 3. No fake call occurs. |
| `PRE_SEND_RETRYABLE_MUTABLE_A3` | Exact attempt-3 sequence-2 pre-send retryable-failed archive and predecessor lineage are durable; mutable points to attempt-3 prepared. | Mutable publication to that attempt-3 retryable tip. | Failure leaves the exact archive authoritative; reopen repairs the pointer and returns permanently non-executable with `attempts_exhausted`. No fake call occurs. |
| `PROVIDER_RETURNED_MUTABLE` | Exact sequence-3 provider-returned archive is durable; mutable points to call-started. | Mutable publication to provider-returned. | Failure leaves provider-returned archive authority; reopen repairs the pointer and remains permanently non-executable without a commit and with zero calls. |
| `POST_CALL_RETRYABLE_MUTABLE_A1` | Exact attempt-1 sequence-3 post-call retryable-failed archive is durable; mutable points to call-started. | Mutable publication to that attempt-1 retryable tip. | Failure leaves the exact archive authoritative; reopen repairs the pointer and the next eligible invocation constructs attempt 2; no fake call is repeated. |
| `POST_CALL_RETRYABLE_MUTABLE_A2` | Exact attempt-2 sequence-3 post-call retryable-failed archive and predecessor lineage are durable; mutable points to call-started. | Mutable publication to that attempt-2 retryable tip. | Failure leaves the exact archive authoritative; reopen repairs the pointer and the next eligible invocation constructs attempt 3; no fake call is repeated. |
| `POST_CALL_RETRYABLE_MUTABLE_A3` | Exact attempt-3 sequence-3 post-call retryable-failed archive and predecessor lineage are durable; mutable points to call-started. | Mutable publication to that attempt-3 retryable tip. | Failure leaves the exact archive authoritative; reopen repairs the pointer and returns permanently non-executable with `attempts_exhausted`; no fake call is repeated. |
| `TERMINAL_MUTABLE` | Exact sequence-3 terminal-failed archive is durable; mutable points to call-started. | Mutable publication to terminal-failed. | Failure leaves terminal archive authority; reopen repairs the pointer and returns the permanent terminal result with zero calls. |
| `UNCERTAIN_MUTABLE` | Exact sequence-3 uncertain archive is durable; mutable points to call-started. | Mutable publication to uncertain. | Failure leaves uncertain archive authority; reopen repairs the pointer and returns the permanent uncertain result with zero calls. |
| `LOCAL_POINTER_MUTABLE` | Exact local commit and exact sequence-2 repeated-prepared archive are durable; mutable points to sequence 1. | Mutable publication to the local pointer archive. | Failure leaves commit plus repair archive authority; reopen advances only the pointer and returns completed with zero calls. |
| `COMMITTED_POINTER_MUTABLE` | Exact Provider commit and exact sequence-4 committed archive are durable; mutable points to sequence 3. | Mutable publication to the committed archive. | Failure leaves commit plus committed archive authority; reopen advances only the pointer and returns completed with zero calls. |
| `POST_PROVIDER_RETURNED` | Exact prepared tip before installation; selected fixed Provider branch. | Full B1 call-started callback, one fake call, then failing sequence-3 provider-returned callback publication. | Exact `PC`; durable authority after failure is call-started, one post-call archive temp remains, callback attempts/completions are `2/1`, fake-client action count is `1`; reopen cleans the temp and returns permanent call-started with zero additional calls. |
| `POST_RETRYABLE` | Exact Section 13.1 prepared/call-started prerequisite and deterministic `transition()` candidate authority. | Full fixed-fake call then failing sequence-3 retryable-failed callback publication. | Exact `PC`; the unpublished candidate event is retryable-failed; durable authority after failure is call-started; one complete post-call archive temp remains; callback attempts/completions are exactly `2/1`; fake-client action count is `1`; no later action or retry occurs; reopen cleans the temp and returns permanent call-started with zero additional calls. |
| `POST_TERMINAL` | Exact Section 13.1 prepared/call-started prerequisite and deterministic `transition()` candidate authority. | Full fixed-fake call then failing sequence-3 terminal-failed callback publication. | Exact `PC`; the unpublished candidate event is terminal-failed; durable authority after failure is call-started; one complete post-call archive temp remains; callback attempts/completions are exactly `2/1`; fake-client action count is `1`; no later action or retry occurs; reopen cleans the temp and returns permanent call-started with zero additional calls. |
| `POST_UNCERTAIN` | Exact Section 13.1 prepared/call-started prerequisite and deterministic `transition()` candidate authority. | Full fixed-fake call then failing sequence-3 uncertain callback publication. | Exact `PC`; the unpublished candidate event is uncertain; durable authority after failure is call-started; one complete post-call archive temp remains; callback attempts/completions are exactly `2/1`; fake-client action count is `1`; no later action or retry occurs; reopen cleans the temp and returns permanent call-started with zero additional calls. |
| `COMMIT_PROVIDER` | Exact prepared tip before installation; non-RQ3 fixed Provider success selected. | Full B1 Provider path through commit publication. | Exact `PP`; callback attempts/completions are `2/2`, fake count `1`; failure leaves provider-returned authority, no commit, and one commit temp; reopen cleans the temp and is permanently non-executable with zero calls. |
| `COMMIT_LOCAL` | Exact prepared tip before installation; non-RQ3 fixed local success selected. | Full B1 local path through commit publication. | Exact `T`; callback attempts/completions are `0/0`, fake count `0`; failure leaves prepared authority, no commit, and one commit temp; reopen cleans it and may re-execute only the fixed local path. |
| `COMMIT_RQ3_T1_PROVIDER` | Exact context-aware Turn 1 prepared tip before installation; fixed Provider success selected; exact checkpoint candidate constructed in B1. | Full Provider Turn 1 single-file result/checkpoint commit publication. | Exact `PP`; callbacks `2/2`, fake count `1`; failure leaves provider-returned authority with no result or checkpoint commit; reopen cleans and is permanently non-executable with no Turn 1 replay. |
| `COMMIT_RQ3_T1_LOCAL` | Exact context-aware Turn 1 prepared tip before installation; fixed local success and exact checkpoint candidate selected. | Full local Turn 1 single-file result/checkpoint commit publication. | Exact `T`; callbacks `0/0`, fake count `0`; failure leaves prepared authority with no commit; reopen cleans and may re-execute only the fixed local Turn 1 path. |
| `COMMIT_RQ3_T2_PROVIDER` | Exact validated Turn 1 commit/checkpoint and exact Turn 2 prepared tip before installation; fixed Provider Turn 2 selected. | Full Provider Turn 2 commit bound to Turn 1. | Exact `PP`; callbacks `2/2`, fake count `1`; failure leaves Turn 2 provider-returned authority and no Turn 2 commit; reopen cleans and makes zero further calls. |
| `COMMIT_RQ3_T2_LOCAL` | Exact validated Turn 1 commit/checkpoint and exact Turn 2 prepared tip before installation; fixed local Turn 2 selected. | Full local Turn 2 commit bound to Turn 1. | Exact `T`; callbacks `0/0`, fake count `0`; failure leaves Turn 2 prepared authority and no Turn 2 commit; reopen cleans and may re-execute only fixed local Turn 2. |
| `CLEAN_CONTRACT_TEMP` | Exact recognized unpublished contract temp and otherwise no non-lock durable state. | Cleanup before any store load. | Selected temp remains, no handle is opened or closed by the injected point, and no durable access/action follows; a later reopen removes it then creates the exact contract. |
| `CLEAN_ARCHIVE_TEMP` | Exact recognized post-call archive temp plus call-started authority. | Cleanup before any store load. | Selected temp remains; no durable access/action follows; later reopen removes it and returns permanent call-started with zero calls. |
| `CLEAN_COMMIT_TEMP` | Exact recognized Provider commit temp plus provider-returned authority. | Cleanup before any store load. | Selected temp remains; no durable access/action follows; later reopen removes it and remains permanently provider-returned without a commit or recall. |
| `CLEAN_MUTABLE_TEMP` | Exact recognized committed-pointer mutable temp plus exact Provider commit and committed archive. | Cleanup before any store load. | Selected temp remains; no durable access/action follows; later reopen removes it, advances only the mutable pointer, and returns completed with zero calls. |

Except for the four `POST_*` and six `COMMIT_*` integration branches, every prerequisite object and durable state above
is created and validated before installer entry and the selected exact store helper is the only operation performed
inside the positive context. Therefore its callback and fake-client counts are exactly `0/0` and `0`. All failing rows
stop at their named hook, perform no same-call retry or republication, never enter the Provider retry loop, and perform
no later callback, Provider action, reconciliation, progress derivation, public outcome construction, or formal-unit
advancement. A successful `S0` or `S1` row is the only exception: it completes the single recovery readback, verifies
the target, returns publication success, and continues the already authorized caller without a second publication.

The complete exact positive and missing-trigger transition table for all 18 amendment-added literals is below. Each
branch token expands to the exact prerequisite, operation, durable/temp state, handle state, stop ordering,
callback/fake counts, retry prohibition, and reopen result in the branch table; each vector expands to every exact
observation field above. Each listed row has its own independently installed all-zero-count/all-empty-handle negative
record as already frozen.

| Amendment-added literal | Exact positive branch | Exact positive vector | Exact independent missing-trigger record |
| --- | --- | --- | --- |
| `before_atomic_temp_create_error` | `RUN_CONTRACT` | `B` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_create_error` | `PREPARED_ARCHIVE` | `B` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_create_error` | `PROVIDER_COMMIT` | `B` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_create_error` | `PREPARED_MUTABLE` | `B` | zero `K`; empty `H`; three `ABSENT` groups |
| `after_atomic_temp_partial_write_error` | `RUN_CONTRACT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `after_atomic_temp_partial_write_error` | `PREPARED_ARCHIVE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `after_atomic_temp_partial_write_error` | `PROVIDER_COMMIT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `after_atomic_temp_partial_write_error` | `PREPARED_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_flush_error` | `RUN_CONTRACT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_flush_error` | `PREPARED_ARCHIVE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_flush_error` | `PROVIDER_COMMIT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_flush_error` | `PREPARED_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_fsync_error` | `RUN_CONTRACT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_fsync_error` | `PREPARED_ARCHIVE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_fsync_error` | `PROVIDER_COMMIT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_temp_fsync_error` | `PREPARED_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_temp_close_error` | `RUN_CONTRACT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_temp_close_error` | `PREPARED_ARCHIVE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_temp_close_error` | `PROVIDER_COMMIT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_temp_close_error` | `PREPARED_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_publication_error` | `RUN_CONTRACT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_publication_error` | `PREPARED_ARCHIVE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_publication_error` | `LOCAL_REPAIR_ARCHIVE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_publication_error` | `PROVIDER_REPAIR_ARCHIVE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_publication_error` | `PROVIDER_COMMIT` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_atomic_publication_error` | `COMMITTED_POINTER_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `after_atomic_publication_before_readback_error` | `RUN_CONTRACT` | `S0` | zero `K`; empty `H`; three `ABSENT` groups |
| `after_atomic_publication_before_readback_error` | `PREPARED_ARCHIVE` | `S0` | zero `K`; empty `H`; three `ABSENT` groups |
| `after_atomic_publication_before_readback_error` | `PROVIDER_COMMIT` | `S0` | zero `K`; empty `H`; three `ABSENT` groups |
| `after_atomic_publication_before_readback_error` | `PREPARED_MUTABLE` | `S0` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_readback_error` | `RUN_CONTRACT` | `S1` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_readback_error` | `PREPARED_ARCHIVE` | `S1` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_readback_error` | `PROVIDER_COMMIT` | `S1` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_readback_error` | `PREPARED_MUTABLE` | `S1` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `PREPARED_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `CALL_STARTED_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `PRE_SEND_RETRYABLE_MUTABLE_A1` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `PRE_SEND_RETRYABLE_MUTABLE_A2` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `PRE_SEND_RETRYABLE_MUTABLE_A3` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `PROVIDER_RETURNED_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `POST_CALL_RETRYABLE_MUTABLE_A1` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `POST_CALL_RETRYABLE_MUTABLE_A2` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `POST_CALL_RETRYABLE_MUTABLE_A3` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `TERMINAL_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `UNCERTAIN_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `LOCAL_POINTER_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_mutable_record_publication_error` | `COMMITTED_POINTER_MUTABLE` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_post_call_archive_publication_error` | `POST_PROVIDER_RETURNED` | `PC` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_post_call_archive_publication_error` | `POST_RETRYABLE` | `PC` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_post_call_archive_publication_error` | `POST_TERMINAL` | `PC` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_post_call_archive_publication_error` | `POST_UNCERTAIN` | `PC` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_private_commit_publication_error` | `COMMIT_PROVIDER` | `PP` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_private_commit_publication_error` | `COMMIT_LOCAL` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_private_commit_publication_error` | `COMMIT_RQ3_T1_PROVIDER` | `PP` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_private_commit_publication_error` | `COMMIT_RQ3_T1_LOCAL` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_private_commit_publication_error` | `COMMIT_RQ3_T2_PROVIDER` | `PP` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_private_commit_publication_error` | `COMMIT_RQ3_T2_LOCAL` | `T` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_owned_temp_cleanup_error` | `CLEAN_CONTRACT_TEMP` | `B` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_owned_temp_cleanup_error` | `CLEAN_ARCHIVE_TEMP` | `B` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_owned_temp_cleanup_error` | `CLEAN_COMMIT_TEMP` | `B` | zero `K`; empty `H`; three `ABSENT` groups |
| `before_owned_temp_cleanup_error` | `CLEAN_MUTABLE_TEMP` | `B` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_readback_error` | `RUN_CONTRACT` | `FR` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_readback_error` | `PREPARED_ARCHIVE` | `FR` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_readback_error` | `PROVIDER_COMMIT` | `FR` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_readback_error` | `PREPARED_MUTABLE` | `FR` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_invalid_bytes` | `RUN_CONTRACT` | `FV` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_invalid_bytes` | `PREPARED_ARCHIVE` | `FV` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_invalid_bytes` | `PROVIDER_COMMIT` | `FV` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_invalid_bytes` | `PREPARED_MUTABLE` | `FV` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_temp_failure_then_close_error` | `RUN_CONTRACT` partial-write mapping | `TC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_temp_failure_then_close_error` | `PREPARED_ARCHIVE` pre-flush mapping | `TC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_temp_failure_then_close_error` | `PROVIDER_COMMIT` pre-`fsync` mapping | `TC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_temp_failure_then_close_error` | `PREPARED_MUTABLE` pre-close mapping | `TC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_readback_then_close_error` | `RUN_CONTRACT` | `VC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_readback_then_close_error` | `PREPARED_ARCHIVE` | `VC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_readback_then_close_error` | `PROVIDER_COMMIT` | `VC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_readback_then_close_error` | `PREPARED_MUTABLE` | `VC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_readback_then_close_error` | `RUN_CONTRACT` | `RC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_readback_then_close_error` | `PREPARED_ARCHIVE` | `RC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_readback_then_close_error` | `PROVIDER_COMMIT` | `RC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_readback_then_close_error` | `PREPARED_MUTABLE` | `RC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_validation_then_close_error` | `RUN_CONTRACT` | `VRC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_validation_then_close_error` | `PREPARED_ARCHIVE` | `VRC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_validation_then_close_error` | `PROVIDER_COMMIT` | `VRC` | zero `K`; empty `H`; three `ABSENT` groups |
| `during_atomic_publication_recovery_validation_then_close_error` | `PREPARED_MUTABLE` | `VRC` | zero `K`; empty `H`; three `ABSENT` groups |

For every `T`, `S0`, `S1`, `FR`, `FV`, `TC`, `VC`, `RC`, `VRC`, `PC`, and `PP` positive, the temporary opened tuple
contains exactly the tokens of the handles that actually opened, and the temporary close-attempt tuple contains those
same tokens in the same order. The initial and recovery families obey the same equality wherever one handle must open
and close once. A deliberately repeated-open, repeated-close, or wrong-handle negative is separate from the
missing-trigger negative: it proves `(T1,T2)`, `(T,T)`, or a close token `U != T` respectively, and the matching close
counter equals the close-tuple length. Trigger consumption never masks the extra token. No raw primitive patch or spy
is used.

The exact initial record for each successful installation has schema `1`; the exact armed literal; the active
controller identity, normalized root, PID, and thread; zero for the trigger and seven operation counters; `()` for all
six handle tuples; and `None` for all 30 exception fields. A later non-nested installation constructs this same shape
from its new active controller/root/PID/thread and never inherits a prior token, counter, metadata field, traceback
tuple, or strong reference. Normal and exceptional outer exit destroy the private record and release every retained
reference; no cleared record is exposed. Immediate `os._exit` is not an outer-context cleanup: it terminates the
process without running that cleanup, and process termination does not expose the abandoned process-local record.

Cross-field invariants are exact: successful publications never exceed publication attempts; initial-verification
attempts never exceed successful publications; recovery attempts never exceed initial-verification attempts; every
close count equals its identity-tuple length; every present exception group has all ten fields present and every absent
group has all ten fields `None`; every present `retained` field is `True`; initial and recovery-primary identities are
distinct; primary and secondary identities are distinct; and a present secondary context ID equals the exact active
primary ID. Any invariant failure raises `STORE_TEST_FAULT_INVALID` rather than returning a partial snapshot.

Each accessor call constructs a fresh frozen slotted record from one locked private snapshot. Normal assignment raises
`dataclasses.FrozenInstanceError`; deliberate mutation of a returned object cannot mutate later snapshots or private
state. The accessor may be called only by Stage B2 tests in
`scripts/test_formal_evaluation_store.py`, `scripts/test_formal_evaluation_orchestration.py`, and
`scripts/test_run_formal_evaluation.py`, only for fault assertions, only from the installing PID and thread, and only
while the matching installer context is active. No controller, after either outer-exit path, wrong PID, wrong thread,
non-string/unknown point, or point different from the armed literal raises exactly
`StoreError("STORE_TEST_FAULT_INVALID")` and exposes no prior state.

The accessor and record remain underscore-prefixed test-only objects in `formal_evaluation_store`. They add no public
export, production input, durable field, run-contract member, plan value, CLI option, environment activation, response
field, or cross-process channel. This remains the sole observation API.

### Installation and hook activation

The complete controller semantics are:

1. A test first patches only the existing private root constant to one validated OS-temporary root, then enters
   `_install_stage_b2_test_fault_controller_for_tests(root, fault_point)`.
2. The installer performs every frozen Section 27 validation before durable-state access. It additionally validates
   `fault_point` against the exact 23-literal vocabulary in Section 4.
3. An unknown string, non-string, wrong root, production root, non-temporary root, reparse root, second installation,
   or non-fixed fake authority raises exactly `StoreError("STORE_TEST_FAULT_INVALID")` before lock acquisition or
   durable mutation.
4. Every validation or rejection before a new installation completes performs no controller or observation-state
   mutation. With no outer controller, a failed installation creates no observation state; the sole accessor raises
   `STORE_TEST_FAULT_INVALID`.
5. A nested installation attempt is rejected with exact `StoreError("STORE_TEST_FAULT_INVALID")`. Immediately before
   the inner attempt, the owner thread captures the complete 50-field outer observation. Immediately after catching
   the exact rejection, it captures the complete outer observation again through the same sole accessor and requires
   dataclass equality. This proves the same `controller_identity`, normalized `controller_root`, `owner_pid`,
   `owner_thread_id`, armed `fault_point`, counters, handle identities, exception metadata, traceback-suffix IDs,
   retained-reference flags, and trigger state. The failed inner entry performs no reset, clear, replacement,
   temporary installation, strong-reference release, or outer `finally` cleanup. No direct inspection of the
   controller, controller global, or private counter container is authorized.
6. One successfully completed installation arms exactly one literal. Multiple points cannot be armed simultaneously.
7. After all validation and nested-installation rejection checks pass, the installer atomically installs the controller
   and exact initial `_StageB2TestFaultObservationV1` private state, records the current PID/thread, and retains the
   controller strongly. These are private test state, not controller-dataclass fields or durable state.
8. A hook that does not exactly match the armed literal does not change `trigger_count` or exception metadata and
   performs no injected behavior. Independently, every real operation named by a Section 6 counter increments that
   counter and appends its exact handle identity at the frozen event even when the armed hook does not match or the
   trigger was already consumed.
9. At the first exact matching hook, `trigger_count` changes atomically from `0` to `1` before the marker, exit,
   injected write, substituted validation buffer, close result, or injected exception behavior occurs. A compound
   behavior's later recovery or close step is continuation of that same consumed trigger and never increments
   `trigger_count` again.
10. Every later matching hook in the same installation performs no second injected behavior. No point can trigger
     twice. Applicable operation counters nevertheless continue to increment, making every prohibited repeat
     observable; opened-handle and close-attempt identity tuples continue to append, making a repeated or wrong handle
     independently observable.
11. A hook or observation access reached from a different PID or thread raises `STORE_TEST_FAULT_INVALID` before its
     filesystem mutation or counter change.
     The controller is therefore process-local and installing-thread-bound. Each Windows subprocess installs its own
     independent controller. A newly spawned Windows process starts a fresh interpreter and has no inherited active
     controller; its accessor rejection proves process-local absence only. It does not prove mutation of an outer
     controller and does not exercise an active-controller PID-mismatch branch. This amendment makes no such
     cross-PID-mismatch test claim.
12. Only exit from the successfully installed outer context clears state. Normal outer exit and exceptional outer exit
     each execute that outer cleanup exactly once: restore `_STAGE_B2_TEST_FAULT_CONTROLLER` to exactly `None`, destroy
     the complete private observation state, clear PID/thread state, and release all retained controller, handle, and
     exception references. A rejected nested entry never executes this cleanup. The required test observes clearing
      only through the sole accessor's exact post-exit `STORE_TEST_FAULT_INVALID`; it does not inspect the global.
      Immediate `os._exit` runs neither this cleanup nor a later accessor call. The OS terminates the process; the
      parent observes only the frozen exit/marker contract and cannot observe whether child-local fields were cleared.
13. A later non-nested installation after either outer-exit path performs full validation and begins from the exact
     Section 6 initial record. It cannot observe or inherit any prior literal, count, handle token, exception metadata,
     traceback tuple, or strong reference. Its `controller_identity` is the current object's `id()`; because old
     references have been released, no cross-installation inequality claim is made about numeric `id()` reuse.
14. After an escaping persistence error, the point remains consumed until outer context exit. The store call has already
     stopped under Section 5. For the two successfully recovered post-publication points, the point is consumed before
     the one recovery readback and cannot interrupt that recovery. Each failed-recovery or secondary-close compound
    literal performs only its own closed continuation after the same single consumption.
15. On module import and during all normal execution,
    `_STAGE_B2_TEST_FAULT_CONTROLLER is None`. Every hook must begin with an exact `None` check and return without
    allocation, counter change, exception, marker, timing change, or filesystem action. An absent controller therefore
    cannot inject a fault.
16. Activation through an environment variable, command-line value, public API value, durable file, marker, plan
    member, fixture value, request payload, global assignment by a test, random choice, clock/timing race, socket,
    network response, Provider response, or callback return is prohibited.
17. Production callers cannot construct, pass, discover, or activate the controller through any public Stage B2,
    Stage B1, runner, CLI, plan, or store input.
18. The controller, installer, observation record type, and accessor remain underscore-prefixed, module-private test
     objects. No public signature,
     return type, schema, durable wrapper, run-contract member, plan member, production dependency, or exported API is
     added or changed. The extension adds no public production API.

The activation mapping for the 18 amendment-added literals is exact and closed:

| Armed literal | Exact matching hook |
| --- | --- |
| `before_atomic_temp_create_error` | Once per candidate immediately before the actual exclusive temporary open. |
| `after_atomic_temp_partial_write_error` | Once after the exact `floor(N/2)` unbuffered prefix write. |
| `before_atomic_temp_flush_error` | Once immediately before the actual temp `flush()`. |
| `before_atomic_temp_fsync_error` | Once immediately before the actual temp-file `os.fsync()`. |
| `during_atomic_temp_close_error` | Once at entry to the mandatory normal temp close invocation. |
| `before_atomic_publication_error` | Once immediately before the actual generic atomic-target `MoveFileExW`. |
| `after_atomic_publication_before_readback_error` | Once after successful publication and before first-verification open. |
| `during_atomic_publication_readback_error` | Once after first-verification open and before its first byte read. |
| `before_mutable_record_publication_error` | Once immediately before the actual mutable-record replacement `MoveFileExW`. |
| `before_post_call_archive_publication_error` | Once before create-only publication of the exact sequence-3 post-call archive candidate. |
| `before_private_commit_publication_error` | Once before create-only publication of the exact validated private-commit candidate. |
| `before_owned_temp_cleanup_error` | Once immediately before removal of the first exact validated recognized owned temp. |
| `during_atomic_publication_recovery_readback_error` | One compound continuation: first-verification pre-read failure, handler exit, then recovery pre-read `R`. |
| `during_atomic_publication_recovery_invalid_bytes` | One compound continuation: first-verification pre-read failure, handler exit, recovery read, then exact detached invalid validation buffer. |
| `during_atomic_temp_failure_then_close_error` | One of the four exact target-category primary positions, followed by that handle's one failure-path close. |
| `during_atomic_publication_readback_then_close_error` | First-verification pre-read primary followed by that first-verification handle's one close. |
| `during_atomic_publication_recovery_readback_then_close_error` | Initial handler exit, recovery pre-read `R`, then that recovery handle's one close. |
| `during_atomic_publication_recovery_validation_then_close_error` | Initial handler exit, recovery validation `V`, then that recovery handle's one close. |

No hook above matches `run.lock`, a marker write, an unknown target, an unowned temp, or a second literal.

## 7. Persistence safety boundaries

### Universal primary/secondary close precedence

The following rule is universal for every mandatory Stage B2 handle close attempted while an injected or validation
exception object `P` is already active:

1. `P` is the exact original controller-created `StoreError` object or the exact existing validator-created
   `StoreError` object that made failure unwinding necessary. Its identity, exact type, `args`, category, cause,
   context, suppression flag, notes, and every other frozen metadata field remain authoritative and unchanged.
2. The affected handle's close operation is attempted exactly once. It is never retried, including by `finally`,
   cleanup, recovery, callback, context exit, or a generic error handler.
3. If close returns normally, the already frozen behavior for `P` continues. If close raises any secondary exception
   object `C`, exact `P` remains authoritative and propagates. `C` never replaces or wraps `P`, is never set as its
   cause or context, is never included in its `args`, category, traceback, note, or detail, and is not exposed at the
   B1 or public store boundary. The implementation must not call `add_note()` or otherwise mutate `P`.
   `P.__cause__`, `P.__context__`, `P.__suppress_context__`, and any existing `P.__notes__` remain exactly as they were
   immediately before close. The required controller-created `C` itself has `__cause__ is None`,
   `C.__context__ is P`, `C.__suppress_context__ is False`, and no notes because it is created and raised while `P` is
   the active handled exception. Those facts do not mutate `P`.
4. If a caught secondary exists, control must leave the inner handler for `C` before propagating `P`. Propagation from
   the still-active outer handler must use the exact bare-reraise structure below; the same structure applies with
   recovery primary `R` or `V`:

   ```python
   try:
       operation_that_raises_primary()
   except BaseException as primary:
       record_primary(primary)
       try:
           close_the_exact_opened_handle_once()
       except BaseException as secondary:
           record_secondary(secondary)
       refresh_primary_lower_traceback_suffix(primary)
       raise
   ```

   No `with_traceback`, `raise P`, `raise R`, `raise V`, `raise P from C`, `raise P from None`, traceback replacement,
   traceback clearing, traceback reconstruction, or bare raise executed inside the inner `C` handler is permitted.
   The analogous named-primary forms are equally prohibited. If no close is required, the controller injection helper
   constructs the new exception object, performs its one initial `raise newly_created_primary`, then catches it exactly
   once as the active primary, records it, and uses bare `raise`. The explicit first raise creates the primary's initial
   traceback; it is not propagation of an already-active primary. The bare rereraise neither reconstructs nor replaces
   the traceback. All outer functions then use ordinary uncaught propagation except for the exact B1 callback form
   below.
5. After `C`, the affected handle is treated as indeterminate and unusable for all control-flow purposes. No read,
   write, flush, `fsync`, second close, publication, removal, validation, or recovery may use it.
6. If the handle was the first post-publication verification handle, a close exception forbids the otherwise
   permitted recovery readback. If it was the recovery handle, no second recovery readback exists. If it was a
   pre-publication temp handle, publication remains forbidden.
7. No later cleanup callback, B1 journal callback, archive or mutable write, commit, reconciliation, progress
   derivation, public outcome construction, fake-client/Provider action, retry transition, formal-unit advancement,
   or return of publication success is permitted in the failing call.
8. Any remaining recognized owned temp is non-authoritative and remains for a later locked cleanup. Foreign and
   unowned files, directories, handles, and artifacts are never closed, changed, removed, renamed, adopted, or made
   authoritative by this rule.
9. Before publication, the last successfully published valid target, archive tip, mutable record, and commit set
   remain authoritative. After successful publication, the one newly published target is the durable directory entry,
   but the failing call cannot claim verified success. No close failure permits republication.
10. A later ordinary reopen uses only authoritative durable bytes. It never infers state from the failed handle or a
   temp. It removes an accessible recognized owned temp under the lock and then derives the frozen decision; if an
   indeterminate OS handle still prevents required access or removal, reopen raises `STORE_IO_FAILURE` without
   mutation until ordinary process/OS handle release. It never retries close or weakens authority.
11. When the close occurs inside a Section 23 persistence callback, exact `P` is the object observed at the lower
    callback boundary. The callback invocation uses exactly:

    ```python
    try:
        callback_result = journal_persistence_callback(journal)
    except BaseException:
        raise
    ```

    B1 constructs no outcome and performs no `raise ... from ...`, `with_traceback`, annotation, wrapping,
    classification, or mutation. The public B1 wrappers do not catch the exception. Exact `P` type, identity, `args`,
    category, cause, context, suppression, notes, and other frozen metadata remain unchanged.
12. Traceback-object preservation is distinct from permitted traceback-head extension. At the lower boundary, the
    observation record captures the complete existing `P.__traceback__` chain as a head-to-tail tuple `Q` of traceback
    object identities. At the final caller boundary, the complete chain must be exactly `O + Q`, where `O` is zero or
    more ordinary outer propagation traceback objects created solely by the callback invocation, private B1 core,
    public B1 wrappers, store caller, and test catch. Every object in suffix `Q` is the same traceback object in the
    same order. No final-head or complete-chain identity equality with the lower-boundary head is required. Every frame
    in `O` must be one of those permitted outer propagation frames; no frame from `C`, a traceback reconstruction
    helper, or an unrelated handler may occur anywhere in `P`'s chain.

This rule covers the mandatory failure-path close after partial temporary write, injected flush failure, injected
file-`fsync` failure, and injected pre-close failure; a normal temporary-file close that is itself the first failure;
the first publication-verification handle; the sole recovery-readback handle; and every other failure-path handle
cleanup required by Sections 12, 14, 15, or 23. If a normal close is itself the first failure, that close failure is
the primary I/O failure, the handle is indeterminate, no second close is attempted, and all state/stop/reopen rules
above apply with no earlier `P`. `during_atomic_temp_close_error` is the sole deterministic injection for that exact
normal-close-as-primary behavior: its one close invocation produces exact `P`, and no failure-path close follows.

The four compound close literals in Section 5 are the sole deterministic secondary-close injection mechanisms:
`during_atomic_temp_failure_then_close_error`,
`during_atomic_publication_readback_then_close_error`,
`during_atomic_publication_recovery_readback_then_close_error`, and
`during_atomic_publication_recovery_validation_then_close_error`. For those test-only behaviors, the one underlying
close is allowed to release the OS handle and that same close invocation then synthesizes `C`; the handle is
nevertheless treated as indeterminate and unusable by the failing call. Consequently, their later-reopen results are
exact: each pre-publication target-category case removes its exact owned temp and applies its closed Section 5
contract/archive/commit/mutable result, while all three post-publication cases validate only the one canonical target
idempotently. This test-only sequencing changes no production close semantics.

Each positive test for each of those four literals, including all four target-category branches of
`during_atomic_temp_failure_then_close_error`, must compare the caught authoritative primary's
complete type, identity, args, category, cause identity/absence, context identity/absence, suppression, notes, retained
flag, and lower traceback suffix with the exact primary observation group. It must compare the final traceback chain
to the recorded suffix using the exact `O + Q` rule above. For these exact primary `StoreError` objects, cause and
context are `None`, suppression is `False`, and notes are `()`. The same assertions apply again at the B1 callback
boundary whenever the failing atomic write occurs inside a Section 23 callback. Exact final traceback-head identity is
never asserted.

This amendment does not:

- weaken any atomic-write, create-only, replacement, write-through, file-`fsync`, close, readback, or lock
  requirement;
- permit an invalid, truncated, partially written, noncanonical, unverified, or hash-mismatched wrapper to be
  authoritative;
- permit silent error recovery;
- change canonical JSON, final-LF rules, hash domains, wrapper schemas, state transitions, lock scope, file `fsync`,
  reopen validation, archive chains, archive-tip repair, commit-first ordering, mutable replacement, cleanup, or
  fail-closed behavior, except to make their already required failure behavior deterministically observable;
- authorize injection against the production root, a repository path, a caller-selected root, or any path outside the
  one validated OS-temporary test root;
- authorize injection into `run.lock`, Section 27 marker creation, frozen fixtures, Provider code, network code,
  production resources, caches, embeddings, corpora, models, real clients, canary, real mode, or formal execution; or
- permit a persistence exception to enter the Provider retry loop.

For every escaping persistence error, the exact authoritative `StoreError` object is visible to the immediate caller;
it is not converted to a B1 outcome, executor failure, Provider result, transport result, retry classification, or
public durable outcome. For the two successfully recovered post-publication points, recovery is not silent: the
read-only immutable observation record proves the injected first failure and exact operation counts, exact target
readback is mandatory, and any
recovery-readback defect is raised under its existing frozen category. The two failed-recovery compound points make
both recovery I/O failure and recovery validation failure independently reachable through the actual internal
post-publication recovery branch with one armed literal each. The two recovery-handle close-compound points separately
make `R + C` and `V + C` reachable with one literal each, without a hidden selector or second armed point.

## 8. Exact test authorization and mapping

For tests exercising the 18 amendment-added fault points, the only configurable fault mechanism is
`_StageB2TestFaultControllerV1`, installed through its existing context manager. The only filesystem override is the
already authorized private root patched to the validated OS-temporary test root. Tests must use the fixed fake client,
executor registry, clock, snapshot validator, and synthetic resources.

Direct monkeypatching, replacement, wrapping, or spying on raw persistence primitives and helpers remains prohibited,
including for operation counts or exception capture. All such proof must use the immutable Section 6 observation
record, escaping exception identity, closed durable-state inspection, and ordinary reopen behavior. No existing frozen
test authority requires raw spying; this amendment creates no exception to that prohibition.

| Existing planned obligation | Sole newly authorized point or points |
| --- | --- |
| Before temp creation | `before_atomic_temp_create_error` |
| Partial temp write | `after_atomic_temp_partial_write_error` |
| Flush failure | `before_atomic_temp_flush_error` |
| File-`fsync` failure | `before_atomic_temp_fsync_error` |
| Mandatory normal temp close itself is the first failing operation | `during_atomic_temp_close_error` |
| Before Win32 create-only publication or replacement | `before_atomic_publication_error` |
| After successful publication and before return | `after_atomic_publication_before_readback_error` |
| Publication readback failure | `during_atomic_publication_readback_error` |
| Recovery readback itself fails after the initial verification failure | `during_atomic_publication_recovery_readback_error` |
| Recovery readback returns bytes that fail canonical validation after the initial verification failure | `during_atomic_publication_recovery_invalid_bytes` |
| Pre-publication primary failure followed by a secondary mandatory-close failure | `during_atomic_temp_failure_then_close_error` |
| Post-publication first-verification failure followed by failure to close that handle before recovery | `during_atomic_publication_readback_then_close_error` |
| Recovery-read I/O primary followed by failure to close the recovery handle | `during_atomic_publication_recovery_readback_then_close_error` |
| Recovery canonical-validation primary followed by failure to close the recovery handle | `during_atomic_publication_recovery_validation_then_close_error` |
| Mutable update after archive durability | `before_mutable_record_publication_error` |
| Normal archive or repair-archive publication | `before_atomic_publication_error`, armed only after the prerequisite durable state is established |
| Post-call archive persistence and no-recall | `before_post_call_archive_publication_error` |
| Provider/local/RQ3 private-commit publication | `before_private_commit_publication_error` |
| Lagging/missing mutable pointer repair | `before_mutable_record_publication_error`, armed for the reopen repair |
| Cleanup/removal failure | `before_owned_temp_cleanup_error` |
| Crash after durable `call_started` and before fake-client entry | `after_call_started_published_exit` |
| Mark after fake-client return and continue | `after_fake_client_returned_mark` |
| Exit after fake-client return and before post-call persistence | `after_fake_client_returned_exit` |
| Exit after private-commit publication/readback and before pointer/reconciliation | `after_private_commit_published_exit` |
| Exit after committed-archive publication/readback and before mutable replacement | `after_committed_archive_published_exit` |

The four immediate-exit positives are subprocess-only exit/marker assertions. After the child terminates, the parent
must assert only the exact frozen exit code, the unchanged eight-field marker and facts represented by its fields, and
the durable/reopen evidence expressly frozen for that literal in Section 27. It must not call the accessor for the
exited child, fabricate a parent-side observation record, or assert child-local `K`, `H`, controller metadata, counters,
handle identities, exception identities, or exception groups. “Not observable through this exit path” is not an
observed zero, `None`, empty tuple, or `ABSENT` group. A same-literal missing-trigger negative may still call the sole
accessor in its own live installing process before any operation; that separate negative does not supply positive
evidence about an exited child. The mark-only literal continues normally and retains its existing in-process accessor
and marker assertions unchanged.

The direct tests must cover each of the four atomic target categories: run contract, attempt archive, private commit,
and mutable record. The complete Section 6 matrix is the sole branch authority. For
`before_atomic_publication_error`, separate tests establish before installation the exact prerequisite for the run
contract, normal prepared archive, local repeated-prepared repair archive, Provider committed repair archive,
create-only Provider commit, and committed mutable-pointer repair rows. The dedicated mutable point separately covers
all 13 materially distinct mutable rows, with attempt 1, attempt 2, and attempt 3 retryable results separated. The dedicated
post-call point covers all four sequence-3 callback events. The dedicated commit point covers non-RQ3 Provider/local,
RQ3 Turn 1 Provider/local, and RQ3 Turn 2 Provider/local branches. Cleanup covers the four recognized temp target
categories. These are exact separate prerequisite installations and add no occurrence selector.

The required tests and negative tests are:

1. reject every unknown fault-point string, every non-string point, and obsolete
   `before_atomic_temp_close_error` before durable-state access;
2. prove default inactivity only by the sole accessor raising `STORE_TEST_FAULT_INVALID`; no direct controller-global
   or controller-object inspection is authorized;
3. prove the exact accessor signature, exact frozen slotted `_StageB2TestFaultObservationV1` return type, all 50 fields
   in their exact frozen order and types, exact active controller identity/root/PID/thread values, the exact initial
   record, one matching `0 -> 1` trigger transition, every Section 6 counter and handle-identity event, all cross-field
   invariants, detached immutable tuples, `dataclasses.FrozenInstanceError` on ordinary record mutation, inability to
   mutate later snapshots or retained private state, wrong-point/unknown/no-controller/wrong-thread rejection, and
   inaccessibility after outer exit;
4. prove no exception, marker, byte write, filesystem mutation, callback, or fake call occurs before the exact hook;
5. prove every escaping persistence failure stops later callback, publication, reconciliation, outcome construction,
   and Provider/fake-client action;
6. for both successfully recovered post-publication points, assert their complete exact Section 6 positive records:
   one publication attempt, one successful publication, one initial-verification attempt, exactly one recovery
   readback, exact target-specific opened/close identity tuples and counts, retained initial `P` with exact
   null-cause/null-context/false-suppression/no-notes metadata, zero escaping primary, zero suppressed secondary, and a
   canonical successful result. The exact counts and tokens prove zero republications, no wrong handle, and no second
   recovery;
7. arm `during_atomic_publication_recovery_readback_error` alone, traverse the actual post-publication recovery branch,
   require its complete exact Section 6 record, catch exact `R` by `primary_exception_id`, prove `R is not` initial
   `P`, prove the handler for `P` exited before `R` was created, require exact null-cause/null-context/false-
   suppression/no-notes `IO` metadata and retained flags for both, and prove one initial verification, one recovery,
   exact open/close token equality for each family, no second readback, republication, callback, Provider action,
   outcome, or advancement;
8. arm `during_atomic_publication_recovery_invalid_bytes` alone, traverse that same recovery branch, require
   its complete exact Section 6 record, catch the exact existing `STORE_NONCANONICAL_JSON` object `V` by
   `primary_exception_id`, prove initial `P`'s handler exited before `V` was created, require exact null-cause/null-
   context/false-suppression/no-notes `NC` metadata and retained flags, prove the validation buffer is exact
   `published_bytes[:-1]`, prove exact open/close token equality, prove durable bytes were not modified, and prove
   ordinary reopen succeeds idempotently;
9. arm `during_atomic_temp_close_error` alone for one isolated atomic write. Require its exact Section 6 record; prove
   all prior write, flush, and file-`fsync` work succeeded; prove the mandatory normal close invocation itself created
   and raised the first exact `P`; prove the temporary opened and close-attempt tuples contain the same single token;
   prove exactly one temp-close attempt, no earlier primary, no failure-path close, publication, initial verification,
   recovery, callback, Provider action, outcome, or advancement; prove the handle is thereafter
   indeterminate/unusable and the temp non-authoritative; and prove later ordinary reopen removes only the temp and
   derives state from the last authoritative durable bytes;
10. arm `during_atomic_temp_failure_then_close_error` alone in four separate prerequisite states and require the exact
     run-contract partial-write, attempt-archive pre-flush, private-commit pre-`fsync`, and mutable-record pre-close
     branches. In every branch require its complete exact Section 6 record, catch exact `P` by
     `primary_exception_id`, prove `P is not C`, require exact primary metadata with null context and exact secondary
     metadata with `C.__context__ is P`, prove both retained flags, exact one-token open/close equality, one close and
     no retry, and the exact target-specific temp, durable, stop, and later-reopen result;
11. arm `during_atomic_publication_readback_then_close_error` alone, require its complete exact Section 6 record, catch
     exact `P` by `primary_exception_id`, require exact primary metadata with null context and exact secondary metadata
     with `C.__context__ is P`, prove one identical initial-verification open/close token, zero recovery readbacks,
     empty recovery handle tuples, no republication or later action, canonical durable-target preservation, and
     idempotent later reopen;
12. arm `during_atomic_publication_recovery_readback_then_close_error` alone. Require its complete exact Section 6
     record; prove initial `P`, authoritative recovery-read primary `R`, and suppressed close `C` have pairwise-distinct
     positive IDs; prove `P` and `R` have null cause/context and `C` has null cause and exact context `R`; catch the
     identical `R`; prove handler exit before `R` creation, retained flags, one publication, one initial verification,
     one recovery, one identical open/close token for each family, no second close/recovery/republication, the complete
     Section 5 stop ordering, canonical durable authority, no source temp, and idempotent ordinary reopen;
13. arm `during_atomic_publication_recovery_validation_then_close_error` alone. Require its complete exact Section 6
     record; prove initial `P` and suppressed `C` have exact `IO` metadata, authoritative validator primary `V` has exact
     `NC` metadata, prove `P` and `V` have null cause/context and `C` has null cause and exact context `V`, prove all
     three IDs are pairwise distinct and retained, and catch identical `V`; prove handler exit before `V` creation, the
     exact detached `published_bytes[:-1]` input, unchanged canonical disk bytes, one exact recovery open/close token,
     no second close/recovery/republication, the complete stop ordering, no source temp, and idempotent reopen;
14. execute every literal/branch row in the complete Section 6 matrix as an independent positive test with its exact
     prerequisite, `K`, `H`, exception groups, durable target, temp state, handle state, callback/fake counts, stop
     ordering, retry prohibition, and reopen result;
15. pair every positive row—including every local, Provider, RQ3, callback, archive, repair, target-category, and
     attempt-dependent mutable branch—with its own independent missing-trigger installation and exact active-controller
     record having zero `K`, empty `H`, and three `ABSENT` groups. No negative uses a second point, hidden selector,
     race, malformed production/frozen resource, raw persistence patch, or spy;
16. parameterize the universal Section 7 rule over failure-path close after partial write, flush, file `fsync`,
     pre-close primary failure, first-verification failure, recovery I/O primary, recovery validation primary, and each
     mandatory controller-covered failure-cleanup handle. In every compound case, assert exact primary identity, type,
     category, args, cause, context, suppression, notes, and all other frozen metadata remain unchanged; assert the
     lower traceback chain is an identity-preserved suffix of the final chain; require exact immutable `C` metadata,
     `C.__context__` equal to the primary, no `C` frame in the primary chain, and exact opened/close token equality;
     prohibit close retry, `with_traceback`, traceback clearing/replacement/reconstruction, `raise P`, `raise P from
     None`, `raise P from C`, inner-handler bare rereraise, annotation, or mutation; and prove the exact state/stop/reopen
     rule;
17. for every primary or compound close point that is reached within an exact Section 23 persistence callback, catch
     the identical authoritative primary at the B1 callback boundary and assert its type, category, args, cause,
     context, suppression, notes, and other metadata are unchanged; prove the recorded lower traceback chain is the
     same-identity suffix of the final chain after only permitted outer propagation frames, without requiring final-head
     identity; assert no `C` frame, B1 outcome, or later callback exists;
18. capture the complete outer observation immediately before a nested attempt; receive exact
     `STORE_TEST_FAULT_INVALID`; capture the complete observation immediately after; require dataclass equality,
     including controller identity/root/PID/thread, literal, counts, handle tokens, exception metadata, traceback
     suffixes, and retained flags; then trigger the outer point to prove the outer context remains operational;
19. prove that, within a surviving process, only normal or exceptional exit from the successfully installed outer
      context makes the sole accessor unavailable; prove a rejected inner entry does not clear it; and prove a later
      non-nested installation begins with the exact initial 50-field record. This lifecycle assertion does not require
      or imply a post-`os._exit` accessor call in a terminated child or its parent;
20. prove a Windows-spawned child has no inherited active controller and its accessor raises
     `STORE_TEST_FAULT_INVALID`; classify that result only as process-local absence, not as proof of mutation or an
     active-controller PID mismatch. Separately, a same-process wrong-thread accessor/hook proves thread binding and
     leaves the owner-thread observation unchanged;
21. prove no corrupt, partial, noncanonical, unread, or hash-invalid wrapper becomes authoritative;
22. prove reopen is deterministic for unchanged old state, unique archive-tip pointer repair, Provider post-call
     no-recall, local prepared re-execution, and successfully recovered publication;
23. prove every temp, marker, and durable mutation remains confined to the validated temporary root or the already
     frozen marker sibling;
24. prove public signatures, CLI input, plan members, request payloads, environment variables, and durable files
     cannot activate the controller;
25. prove a production-root installation fails `STORE_TEST_FAULT_INVALID` before mutation; and
26. prove controller use adds no import, SDK, client, socket, Provider, production-resource, real-mode, canary, or
     formal-generation path.

## 9. Frozen-resource and regression-test boundary finding

The frozen Stage B2 plan contains no contradiction between its required regressions and frozen-fixture access.

The plan requires the existing tracked runner authorities `verify_frozen()`, `build_plan()`, `validate_plan()`, and
`plan_fingerprint()` and requires the Stage A/B1/freeze regression suites. At the repository baseline, tracked
`build_plan()` necessarily parses the three frozen row-bearing evaluation fixtures in-process to reconstruct the exact
190-member plan. The frozen plan does not prohibit that parsing. It prohibits changing the fixtures, printing
row-level content, using production resources, reaching real execution, and changing the frozen plan identity.

The stricter prohibition on parsing frozen fixtures appeared only in the prior implementation execution prompt. It is
not a frozen Stage B2 plan clause and is not amended here.

Accordingly, this amendment does not create new fixture authority. The existing repository instruction remains the
boundary: a later separately authorized offline regression task may allow the tracked plan-building path to parse the
required frozen fixtures in-process only for deterministic Stage A/B1/Stage B2 regression and plan construction.
Fixtures remain read-only; no row-level query, answer, Gold row, payload, or complete plan member may be printed,
copied into this amendment, externally persisted, or transmitted. No Provider, network, production generation,
canary, real mode, or formal execution is authorized.

## 10. Scope and lifecycle

This amendment changes no Stage B2 implementation allowlist. The allowlist remains exactly:

1. new `scripts/formal_evaluation_store.py`;
2. new `scripts/test_formal_evaluation_store.py`;
3. modify `scripts/run_formal_evaluation.py`;
4. modify `scripts/test_run_formal_evaluation.py`;
5. modify `scripts/formal_evaluation_orchestration.py`; and
6. modify `scripts/test_formal_evaluation_orchestration.py`.

This draft authorizes no implementation, code restoration, test modification, project-module execution, dependency
change, Stage B3 work, Stage B4 work, Stage B5 work, canary, real mode, or formal execution.

The exact amendment bytes require a separate independent read-only review. After acceptance by that separate review,
the amendment must be separately committed and pushed by the user before the preserved stash is restored. This
document does not approve the preserved stash, and it does not establish that the stash conforms to this amendment.
Stash restoration, later Stage B2 implementation, offline tests, and implementation code review remain separate
tasks with separate authorization.

## 11. Requirement traceability

| Original requirement | Controlling frozen section | Resolving amendment clause | Enabled production/test obligation | Unchanged safety boundary |
| --- | --- | --- | --- | --- |
| Tests may use only the named controller; arbitrary persistence patches are forbidden. | 13, 24, 27 | Sections 3, 4, 6, and 8 | One controller now expresses every required persistence failure. | Private temporary-root-only controller; no raw primitive patch. |
| Inject failure before temp creation, at partial write, flush, file `fsync`, and close. | 14, 26 | Section 5 atomic-temp rows | Exact pre-publication tests, including `during_atomic_temp_close_error` where the mandatory normal close itself is the first failure. | Old target remains authority; temp is never authority; the one close is never retried. |
| Mandatory normal close must be the first failing operation, not a pre-close error followed by successful cleanup close. | 14, 26 | Sections 4–8 `during_atomic_temp_close_error` | Exact write/flush/file-`fsync` success, one close-attempt, primary identity, stop, temp, durable-state, negative, and reopen assertions. | No earlier primary, failure-path close, publication, recovery, callback, Provider action, or advancement. |
| Inject failure before Win32 publication and prove immutable/mutable safety. | 14, 26 | Section 5 `before_atomic_publication_error` | Create-only, archive, commit, repair, and replacement tests. | No overwrite of immutable evidence; archive precedes mutable. |
| Recover a successful publication when failure occurs before return or during first readback. | 14, 16, 26 | Section 5 two successful-recovery rows | One-shot readback recovery and idempotence tests. | Exact bytes/schema/hash remain mandatory; no republish. |
| Prove exact publication, readback, and exact-handle closure after trigger consumption. | 14, 26 | Section 6 `_StageB2TestFaultObservationV1` | One immutable 50-field record exposes exact counts, successful-open tokens, actual-close-argument tokens, controller identity/root/ownership, exception identities, and detached immutable metadata. | Active installer/thread/PID only; strong-reference backing; no public activation, mutable reference, raw primitive patch, or spy. |
| Exercise failure of the sole recovery readback through the actual post-publication internal-recovery branch. | 14, 26 | Section 5 `during_atomic_publication_recovery_readback_error` and `during_atomic_publication_recovery_invalid_bytes`; Sections 6–8 | Independent one-literal I/O and validation cases freeze catch/record/handler-exit/recovery ordering and exact `P`, `R`, or `V` metadata. | `R`/`V` are created with no active handled `P`; one publication/recovery; no disk corruption, republish, retry, callback, Provider action, or advancement. |
| Preserve one authoritative primary exception when mandatory close also raises. | 12, 14, 15, 23, 26 | Section 5 four close-compound literals; Sections 6–8 | Pre-publication, first-verification, recovery-I/O, recovery-validation, and B1 callback paths prove identity, metadata, exact-handle closure, and traceback suffix preservation. | Exact primary unchanged; `C` has exact primary context but never enters primary traceback; bare rereraise only; no second recovery/publication. |
| Ordinary propagation may extend a traceback head but must preserve the lower chain. | 23, 26 | Sections 6–8 | Tests capture lower traceback-object IDs and prove the final chain is only permitted outer frames followed by the same-identity suffix. | No complete-head identity claim, `with_traceback`, `raise P`, traceback clearing/replacement/reconstruction, or `C` frame. |
| Recovery primaries must have deterministic cause/context independent of handler nesting. | 14, 15, 26 | Sections 5–8 | Initial `P` handler exits before `R`/`V` creation; all primary/secondary cause, context, suppression, notes, identities, and retained lifetimes are exact. | No implementation choice of nested handlers; primary metadata never changes. |
| Every amendment literal and material branch must have an exact transition and negative. | 14, 15, 23, 26 | Section 6 complete branch/vector matrix; Section 8 | All 18 literals cover exact target, archive, repair, mutable, callback, Provider/local, RQ3, cleanup, durable/temp/handle/stop/retry/reopen and all-zero negative transitions. | No open-ended branch, hidden selector, two armed literals, race, malformed production data, or inference across differing rows. |
| Archive must be durable before mutable replacement; missing/lagging pointer is repairable. | 11, 14, 17, 26 | Section 5 `before_mutable_record_publication_error` and Section 8 mapping | Mutable failure and exact tip-repair tests. | Unique archive tip is authority; ahead/off-chain/fork still fails closed. |
| Post-call persistence failure must never permit another fake Provider call. | 15, 16, 23, 26 | Section 5 `before_post_call_archive_publication_error` | Deterministic post-call callback-failure/no-recall test. | Durable `call_started` remains conservative authority. |
| Private commit failure must preserve Provider/local/RQ3 crash semantics. | 14–17, 20, 26 | Section 5 `before_private_commit_publication_error` | Provider fail-closed, local deterministic replay, and RQ3 atomicity tests. | No partial commit; no Provider retry; Turn 1 checkpoint stays single-file. |
| Cleanup failure blocks opening and cannot treat temps as state. | 9, 13–15, 26 | Section 5 `before_owned_temp_cleanup_error` | Deterministic owned-temp cleanup failure test. | Lock, containment, exact owned-name validation, and fail-closed open remain. |
| Rejected nested installation must not clear or mutate the active outer controller. | 26, 27 | Sections 6 and 8 | Complete before/after 50-field record equality proves controller identity/root/PID/thread and all state preservation solely through the accessor; outer operability, outer-only reset, and fresh later installation are tested. | No direct controller inspection; a spawned Windows child proves process-local absence only. |
| Every normatively affected frozen section must be declared accurately. | 12, 13, 14, 15, 23, 24, 26, 27, 29 | Section 1 and this traceability table | Sections 12 and 23 are listed for only universal close/exception preservation; the other seven scopes remain exact. | No unrelated clause in Sections 12 or 23 and no other plan section is amended. |
| Controller was limited to five marker/exit literals and could only mark or terminate. | 27 | Sections 3–6 | Eighteen exact amendment-added points coexist with the five unchanged crash points; total vocabulary is exactly 23. | One private controller, unchanged fields/signature, fixed fake types, temporary root, no production API. |
| Every fault point, invalid point, restoration, and production-root rejection must be tested. | 26, 27, 29 | Sections 5, 6, 8, and 13.3 | Every effective literal has a normative point-table row and exact mapping. Accessor-observable cases use the sole 50-field record; the four immediate-exit positives use only their frozen exit/marker/durable evidence contract. | Unknown/obsolete points and production activation fail before durable access; no parent-side reconstruction of child-local state. |
| Stage A/B1 and freeze regressions must run through tracked plan authority. | 28 | Section 9 finding only | Correct classification for a later separately authorized offline regression task. | Fixtures stay read-only; no row output, network, Provider, or formal execution. |

Literal-level requirement traceability is exact:

| Amendment-added literal | Exact controlling transition/test authority |
| --- | --- |
| `before_atomic_temp_create_error` | Sections 5, 6 `B` across four target categories, and Section 8 positive/all-zero-negative authorization. |
| `after_atomic_temp_partial_write_error` | Sections 5, 6 `T` across four target categories, and Section 8 positive/all-zero-negative authorization. |
| `before_atomic_temp_flush_error` | Sections 5, 6 `T` across four target categories, and Section 8 positive/all-zero-negative authorization. |
| `before_atomic_temp_fsync_error` | Sections 5, 6 `T` across four target categories, and Section 8 positive/all-zero-negative authorization. |
| `during_atomic_temp_close_error` | Sections 4–8 exact normal-close primary, exact-handle token, four target positives, and four negatives. |
| `before_atomic_publication_error` | Sections 5–8 six closed normal/repair/commit/mutable branches and six negatives. |
| `after_atomic_publication_before_readback_error` | Sections 5–8 `S0` across four targets and four negatives. |
| `during_atomic_publication_readback_error` | Sections 5–8 `S1` across four targets and four negatives. |
| `before_mutable_record_publication_error` | Sections 5–8 13 closed mutable rows with exact attempt-1, attempt-2, and attempt-3 retry splits, plus one negative per row. |
| `before_post_call_archive_publication_error` | Sections 5–8 four exact sequence-3 callback branches, `PC`, and one negative per branch. |
| `before_private_commit_publication_error` | Sections 5–8 six exact Provider/local/RQ3 branches, `PP`/`T`, and one negative per branch. |
| `before_owned_temp_cleanup_error` | Sections 5–8 four exact recognized-temp category branches, `B`, and one negative per branch. |
| `during_atomic_publication_recovery_readback_error` | Sections 5–8 `FR`, deterministic initial-handler exit, four targets, and four negatives. |
| `during_atomic_publication_recovery_invalid_bytes` | Sections 5–8 `FV`, deterministic initial-handler exit, four targets, and four negatives. |
| `during_atomic_temp_failure_then_close_error` | Sections 5–8 four fixed target/phase mappings, `TC`, exact primary/secondary/handle/traceback facts, and four negatives. |
| `during_atomic_publication_readback_then_close_error` | Sections 5–8 `VC` across four targets, exact `P + C` facts, and four negatives. |
| `during_atomic_publication_recovery_readback_then_close_error` | Sections 5–8 `RC` across four targets, exact `P`, `R`, and `C` lifetime facts, and four negatives. |
| `during_atomic_publication_recovery_validation_then_close_error` | Sections 5–8 `VRC` across four targets, exact `P`, `V`, and `C` lifetime facts, and four negatives. |

## 12. Governance and internal consistency conclusion

The previously documented controller contradiction and prior accepted corrections remain unchanged. Exactly the five
accepted findings from the second renewed independent review—four HIGH and one MEDIUM—are corrected here:

1. The B1 exception rule now distinguishes permitted traceback-head extension from traceback-object preservation.
   Exact authoritative `P` and all frozen metadata remain unchanged. The lower-boundary traceback chain must be the
   same-object, same-order suffix of the final chain after only permitted outer propagation frames. Exact final-head or
   whole-chain identity is not required. `C` contributes no frame. Catching paths use the exact outer-handler
   bare-reraise structure; B1 uses the exact bare-reraise callback form. `with_traceback`, `raise P`, `raise P from C`,
   `raise P from None`, traceback clearing, replacement, or reconstruction remain prohibited.
2. Initial verification `P` is caught, fully observed, and strongly retained; its handler exits before recovery begins.
   `R` or `V` is then created with no active handled exception and therefore has exact null cause/context, false
   suppression, and no notes. A close `C` created while recovery primary `R` or `V` is active has exact null cause,
   exact context equal to that primary, false suppression, and no notes. The primary remains wholly unchanged. The
   same deterministic creation, catch, recording, handler-exit, close, and bare-reraise order governs every
   pre-publication and verification primary-plus-secondary-close path.
3. The sole immutable observation record now has exactly 50 fields in the one order and with the exact types frozen in
   Section 6. Six detached integer tuples record each successful handle open and each actual close argument for the
   temporary, first-verification, and recovery families. Each token is strong-reference-backed until outer exit; a
   second open, second close, or wrong-handle close remains visible after trigger consumption. Each close counter equals
   its close-tuple length, and required one-handle paths have exact opened/close tuple equality.
4. The complete Section 6 matrix gives a separate closed positive row and separate all-zero-count/all-empty-handle
   missing-trigger negative for every material branch of all 18 amendment-added literals. It freezes exact
   prerequisites, installation/operation branch, publication/readback/close transitions, exception groups, durable
   target, temp and handle states, stop ordering, callback/fake counts, retry/republication prohibitions, and later
   reopen results for target, archive, repair, mutable, post-call, Provider, local, RQ3, and cleanup branches.
5. Nested-installer preservation is observable solely through the same 50-field record. The complete outer record
   captured immediately before and after exact inner rejection must be equal; this exposes controller identity,
   normalized root, PID, thread, literal, counters, handle identities, exception metadata, traceback suffixes, and
   retained-reference flags. The outer remains operational; only outer normal/exceptional exit clears state; later
   installation begins from the exact initial record. A newly spawned Windows child proves only absence of an inherited
   controller, not mutation or active-controller PID mismatch.

Self-review conclusions are exact:

- No requirement remains that an ordinarily propagated exception retain the same final traceback head or that its
  complete traceback chain object be identical across function boundaries.
- `P`, `R`, and `V` have null cause/context, false suppression, and no notes at creation. `C` has null cause, exact
  context equal to the active primary, false suppression, and no notes. Every identity, type, arguments, category,
  metadata field, traceback suffix, and active-context strong-reference claim is immutable and observable as frozen.
- Every required one-handle close passes exactly the handle that opened. Repeated and wrong-handle behavior yields
  distinct tuple evidence and cannot be hidden by a consumed trigger.
- All 18 amendment-added literals occur in the vocabulary, normative point table, activation mapping, complete
  transition matrix, positive authorization, missing-trigger authorization, and literal-level traceability.
- Every materially distinct authorized branch has its own closed row. Every positive row has its own exact
  missing-trigger negative. No row relies on unspecified conditional wording, an open-ended list, a second literal, hidden selector,
  race, concurrent mutation, malformed production data, or inference from a materially different row.
- Nested rejection requires no controller-global or private-controller inspection. The sole accessor proves every
  claimed preservation fact that is reachable on Windows; the spawned-child conclusion is limited to process-local
  absence.
- For the four immediate-exit positives, the sole accessor is not reachable after child termination. Their parent-side
  assertions are limited to the frozen exit code, unchanged eight-field marker, and expressly authorized durable/reopen
  evidence; unavailable child-local fields are not represented as observed empty, zero, `None`, or `ABSENT` values.
- Every occurrence of the observation shape in this document says exactly 50 fields and agrees with the one Section 6
  order and types. No former field-count claim remains.

The complete effective vocabulary remains exactly 23 literals.

The five unchanged frozen marker/exit literals are:

```text
after_call_started_published_exit
after_fake_client_returned_mark
after_fake_client_returned_exit
after_private_commit_published_exit
after_committed_archive_published_exit
```

The 18 amendment-added literals remain:

```text
before_atomic_temp_create_error
after_atomic_temp_partial_write_error
before_atomic_temp_flush_error
before_atomic_temp_fsync_error
during_atomic_temp_close_error
before_atomic_publication_error
after_atomic_publication_before_readback_error
during_atomic_publication_readback_error
before_mutable_record_publication_error
before_post_call_archive_publication_error
before_private_commit_publication_error
before_owned_temp_cleanup_error
during_atomic_publication_recovery_readback_error
during_atomic_publication_recovery_invalid_bytes
during_atomic_temp_failure_then_close_error
during_atomic_publication_readback_then_close_error
during_atomic_publication_recovery_readback_then_close_error
during_atomic_publication_recovery_validation_then_close_error
```

`before_atomic_temp_close_error` remains obsolete and invalid. `during_atomic_temp_close_error` remains the sole normal
temp-close-as-primary point and retains its accepted physical/logical close semantics.

`_StageB2TestFaultControllerV1` remains the sole Stage B2 direct-test and subprocess fault mechanism with exactly the
three frozen fields `schema_version`, `root`, and `fault_point`.
`_install_stage_b2_test_fault_controller_for_tests(root: Path, fault_point: str)` retains its exact signature. The one
50-field record and `_stage_b2_test_fault_observation_for_tests(fault_point: str)` remain the sole process-local
observation surface. The unchanged frozen eight-field marker remains the sole cross-process fault artifact for the five
inherited marker/exit literals; it is not a second accessor and is not widened. No second API, direct controller-state
inspection, raw persistence monkeypatch, spy, or additional evidence or persistence channel is authorized.

The atomic-write protocol, archive-first and repair-publication authority, mutable authority, Provider no-recall rule,
RQ3 checkpoint atomicity, cleanup boundary, fixed dependencies, six-file implementation allowlist, and the exact nine
affected sections—12, 13, 14, 15, 23, 24, 26, 27, and 29—remain unchanged. Windows durability remains file `fsync`
plus `MoveFileExW` with `MOVEFILE_WRITE_THROUGH`; no parent-directory `fsync` is added. The Section 28 frozen-fixture
finding remains unchanged.

Exactly these five accepted findings were corrected. No other finding or unrelated Stage B2 requirement is addressed.
This document does not approve, adopt, inspect, or retrospectively validate the preserved implementation stash and
does not authorize restoring it. It remains draft, unapproved, uncommitted, and unimplemented. Its corrected exact
bytes require another fresh independent read-only review. Only after that review accepts the amendment may the user
separately commit and push it; stash restoration and Stage B2 implementation remain separately unauthorized until
then.

## 13. Fourth-review corrections: controlling closed authorities

This section corrects exactly the four accepted findings from the third renewed independent review. It supersedes
only earlier text that conflicts with an express rule below. All non-conflicting requirements above remain normative.

### 13.1 Closed post-call candidate authority

`_FixedFakeRawClientV1` remains the only fake raw-client type and always returns its one exact successful synthetic
response. It is neither configured nor patched to raise or return another response. The closed nonproduction mechanism
for the three otherwise unreachable `POST_*` rows is the existing tracked Stage A `transition()` authority applied to
the existing validated `InflightJournal` DTO, followed by the exact Section 23
`journal_persistence_callback(journal: InflightJournal) -> None` boundary. It is deterministic candidate construction,
not Provider behavior and not a controller capability.

For each row, the test first uses the ordinary fixed authority to persist `prepared`, invokes the unchanged fixed fake
exactly once, obtains its exact successful response, and retains that response without modifying it. From the durable
`call_started` `InflightJournal`, it then constructs exactly one validated Stage-A post-call candidate using
`transition(call_started, state, clock(), sanitized_outcome_category=category)`, and invokes the existing synchronous
persistence callback once with that exact DTO. The selected armed literal is
`before_post_call_archive_publication_error`; it fires immediately before publication of that candidate's sequence-3
archive. No B1 Provider classification, fake response, tracker state, exception, Provider patch, raw-persistence spy,
or second persistence mechanism is altered.

| Branch | Exact `transition()` configuration | Exact candidate category | Tracker/fake/Provider/callback facts | Archive prerequisite and result |
| --- | --- | --- | --- | --- |
| `POST_RETRYABLE` | `(state="retryable_failed", sanitized_outcome_category="http_429")` | `retryable_failed` / `http_429` | Tracker has recorded one completed fixed fake call; fake and Provider-call counts are exactly `1`; callback attempts/completions are exactly `2/1`. | Valid prepared then durable `call_started`; sequence-3 retryable candidate is validated before callback; publication is not attempted, its temp remains, and no retry or later callback occurs. |
| `POST_TERMINAL` | `(state="terminal_failed", sanitized_outcome_category="provider_rejected")` | `terminal_failed` / `provider_rejected` | The same exact one fixed fake and `2/1` callback facts. | The same prerequisite; terminal sequence-3 candidate is validated, then stopped before publication. |
| `POST_UNCERTAIN` | `(state="uncertain", sanitized_outcome_category="timeout")` | `uncertain` / `timeout` | The same exact one fixed fake and `2/1` callback facts. | The same prerequisite; uncertain sequence-3 candidate is validated, then stopped before publication. |

The candidate helper is invoked only after the fixed fake return and only in these three test rows. It has no production
input or response-changing parameter, and it cannot arm, consume, inspect, or modify the controller. The controller
still has exactly `schema_version`, `root`, and `fault_point`; the installer signature is unchanged; it remains the
sole persistence fault mechanism. Each positive has its own missing-trigger negative: install the same literal,
observe the all-zero record, perform no callback/candidate operation, and exit. The three positive and three negative
rows are part of the existing 85 positive/85 negative amendment-added persistence-transition pairs; that count does
not include inherited-literal authorities below.

Accordingly, every earlier occurrence of “fixed Provider branch configured to return” for these three rows is replaced
by this table. The `POST_PROVIDER_RETURNED` success row remains the ordinary fixed-fake/B1 success path and is unchanged.

### 13.2 Identity and recovery ordering corrections

`hr` is used only in `recovery_opened_handle_ids` and `recovery_close_attempt_handle_ids`. `er` is used only in the
recovery-I/O primary exception group. Thus `FR` is
`H=((t,),(t,),(i,),(i,),(hr,),(hr,))`, primary `IO(er,qer,None)`; `RC` has that same `H`, primary
`IO(er,qer,None)`, and secondary `IO(c,qc,er)`. `Cs` owns token `c`, with `c != hr`, `c != er`, and `c != p`.
`S0`, `S1`, `FV`, and `VRC` use `hr` only for the recovery handle; `v` remains the distinct validation exception.
All handle tokens (`t`, `i`, `hr`, and numbered variants) are unequal to every concurrently live exception token
(`p`, `er`, `v`, `c` and numbered variants); all concurrently live exception tokens are pairwise unequal. Strong
references retain every handle and exception object until outer installer-context exit, so no observed equality can be
created by object-ID reuse. The Section 6 token table, every dependent vector, test, traceability row, and self-review
uses this vocabulary; no recovery handle is denoted by `r` and no recovery exception is denoted by `r`.

Two exact initial-verification ordering models apply.

1. **Before-open S0.** `after_atomic_publication_before_readback_error` fires after successful publication and entry
   to the first-verification phase, but before any first-verification open. The initial `P` is created, caught,
   completely recorded, and strongly retained. At event `E0`, immediately after that complete recording and before
   the `P` handler exits, the complete initial exception group becomes observable. No first-verification handle exists;
   both initial-verification tuples are `()`, its close count is `0`, and no close is attempted. The handler exits
   directly. Only after that exit, with no active handled exception, does recovery open `hr`, read/validate, and close
   `hr` once under the existing deterministic R/V rules. The exact `S0` vector is therefore
   `K=(1,1,1,1,1,1,0,1)` and
   `H=((t,),(t,),(),(),(hr,),(hr,))`.
2. **After-open paths.** For `S1`, `FR`, `FV`, `VC`, `RC`, and `VRC`, immediately after the first-verification open
   succeeds, append `i`; catch and retain `P`; append `i` immediately before the one exact close invocation; and
   close that same handle once. On successful close, event `E1` occurs immediately after that close returns and before
   the `P` handler exits: the complete initial group becomes observable there. The handler then exits before recovery
   `hr` or recovery primary `er`/`v` is created. Recovery begins with no active handled exception. If that first close
   creates `C`, `E1` does not occur, the initial group is absent, and the existing `VC` primary/secondary rule applies.

These `E0` and `E1` rules replace the earlier statement that the initial group first becomes observable only after
handler exit. They preserve all 50 fields and their order. They also govern the matching positive tests, paired
missing-trigger negatives, activation mapping, traceability, and self-review. No S0 clause implies opening, retaining,
passing, or closing a nonexistent first-verification handle.

### 13.3 Closed inherited-literal authorities

The five inherited literals are authorities inherited from frozen Section 27, not amendment-added persistence
transitions. The sole accessor remains process-local and returns its unchanged 50-field Section 6 record only while
the installing process and thread remain alive with the controller state available. The mark-only literal continues
normally and retains its existing accessor-observable positive and negative records. The other four literals call
immediate `os._exit`; no post-trigger accessor runs in the child, and the parent cannot call or recover the exited
child's accessor record. Neither installer cleanup, `finally`, `atexit`, nor ordinary exception propagation runs after
that immediate exit to export the record.

For those four immediate-exit positives, the unchanged eight-field marker is the sole cross-process fault artifact.
The parent may assert only the frozen termination, exact marker bytes/schema and the facts represented by its eight
fields, plus the pre-existing durable filesystem and reopen evidence expressly authorized by frozen Section 27.
Unrecorded child-local `K`/`H` tuples, controller identity/root/PID/thread metadata, counters, handles, exception
objects, and exception groups are not parent-observable. Their absence from the marker is “not observable,” not
observed zero, `None`, empty tuples, or `ABSENT`. No second accessor, private-controller inspection, raw-persistence
spy, non-fixed fake, marker widening, sidecar, pipe, queue, socket, shared memory, manager, temporary evidence file,
callback, serialization, exception pickling, controller persistence, or other evidence channel is authorized.

| Inherited literal | Closed frozen activation and child behavior | Executable positive evidence and paired missing-trigger-negative authority; traceability |
| --- | --- | --- |
| `after_call_started_published_exit` | Immediately after durable/readback-verified `call_started` archive and matching mutable record, before tracker/proxy/fake entry, the child writes and verifies the unchanged marker, then immediately exits `90`. | Parent observes exit `90`; marker schema `1`, exact literal, child PID, selected execution-unit ID, attempt number, `call_started` archive SHA-256, null private-commit SHA-256, and Provider call count `0`; then ordinary reopen validates the durable `call_started` state and makes zero calls. No 50-field positive record is required or implied. Its separate live-process missing-trigger negative may assert the exact initial all-zero/empty/`ABSENT` accessor record before any operation. |
| `after_fake_client_returned_mark` | Inside unchanged fixed fake after its one count increment and exact response construction, before return: at the marker, `K=(1,4,4,4,0,4,4,0)`, `H=((t1,t2,t3,t4),(t1,t2,t3,t4),(i1,i2,i3,i4),(i1,i2,i3,i4),(),())`; the ordinary Provider continuation ends at `K=(1,9,9,9,0,9,9,0)`, `H=((t1,t2,t3,t4,t5,t6,t7,t8,t9),(t1,t2,t3,t4,t5,t6,t7,t8,t9),(i1,i2,i3,i4,i5,i6,i7,i8,i9),(i1,i2,i3,i4,i5,i6,i7,i8,i9),(),())`. Callbacks are `3/3`, fake/Provider/archive/commit `1/1/4/1`, no temp. | Existing frozen mark-race positive and same-literal all-zero no-operation negative. Normal continuation performs the frozen provider-returned, commit, committed-archive, and pointer sequence exactly once; no retry. |
| `after_fake_client_returned_exit` | At the unchanged fixed-fake point after its one count increment and response construction, before return or any sequence-3 archive, the child writes and verifies the unchanged marker, then immediately exits `91`. | Parent observes exit `91`; marker schema `1`, exact literal, child PID, selected execution-unit ID, attempt number, `call_started` archive SHA-256, null private-commit SHA-256, and Provider call count `1`; ordinary reopen sees only durable `call_started`, makes zero additional calls, and returns the frozen permanent result. No 50-field positive record is required or implied. Its separate live-process missing-trigger negative retains the exact initial accessor record. |
| `after_private_commit_published_exit` | Immediately after exact create-only private-commit publication/readback, before local pointer archive or Provider reconciliation, the child writes and verifies the unchanged marker, then immediately exits `92`. Provider and local transition locations remain distinct under their frozen prerequisites. | Parent observes exit `92`; marker schema `1`, exact literal, child PID, selected execution-unit ID, attempt number, the current prepared/provider-returned archive SHA-256, the non-null private-commit SHA-256, and Provider call count `0` or `1` as frozen for the local/Provider case; ordinary reopen validates the durable commit and performs only the frozen zero-call pointer repair or reconciliation. No 50-field positive record is required or implied. Each separate live-process missing-trigger negative retains the exact initial accessor record. |
| `after_committed_archive_published_exit` | At the Provider-only point immediately after sequence-4 committed-archive publication/readback and before mutable-record replacement, the child writes and verifies the unchanged marker, then immediately exits `93`. | Parent observes exit `93`; marker schema `1`, exact literal, child PID, selected execution-unit ID, attempt number, committed-archive SHA-256, non-null private-commit SHA-256, and the frozen Provider call count `0` or `1`; ordinary reopen validates the durable commit/archive and advances only the mutable pointer with zero calls. No 50-field positive record is required or implied. Its separate live-process missing-trigger negative retains the exact initial accessor record. |

The inherited positive/negative tests are the frozen Section 27 tests and are not relabelled into the 85/85
amendment-added count. For the mark-only literal, the unchanged process-local accessor closes the existing controller,
`K`/`H`, exception-group, and continuation assertions. For the four immediate-exit positives, this table plus their
unchanged frozen Section 27 rows close only the parent-observable exit, marker, durable-state, and later-reopen
authority; no unrecorded child-local fact is positively asserted. Their separate missing-trigger negatives remain
accessor-observable only because those live test processes perform no matching operation and do not immediately exit.
This table remains the literal-level traceability for all five.

### 13.4 Fourth-correction self-review

The previously closed Findings 1–3 remain closed: the fixed successful fake/candidate authority is unchanged; `hr`
and `er` remain separated; and the corrected before-open `S0`/`E0` and after-open/`E1` ordering, including all existing
`__suppress_context__` requirements, remains unchanged.

The effective vocabulary remains exactly 23: the five inherited literals named in Section 13.3 and the eighteen
amendment-added literals in Section 4. `before_atomic_temp_close_error` remains obsolete and invalid, while
`during_atomic_temp_close_error` remains the sole normal-close primary. The 50-field observation record remains
unchanged in field order, type, and count. It remains the sole accessor record for observations made while process-local
controller state is available; the four immediate-exit positives require no post-exit accessor call and claim no
parent-observed child-local record. Their evidence is limited to the unchanged exit/eight-field-marker contract and
expressly frozen durable/reopen facts. The mark-only literal remains substantively unchanged. Raw persistence
monkeypatching/spying remains prohibited; the controller and sole accessor remain the only mechanisms, and the
unchanged marker is the only cross-process fault artifact; the six-file allowlist and the nine affected sections (12,
13, 14, 15, 23, 24, 26, 27, and 29) remain unchanged. Windows durability remains file `fsync` plus
`MoveFileExW(...MOVEFILE_WRITE_THROUGH)`, with no parent-directory `fsync`; the Section 28 frozen-fixture conclusion
remains unchanged. This draft remains unapproved, uncommitted, and unimplemented, and another fresh independent
review is required before any user commit/push or separate stash-restoration authorization.
