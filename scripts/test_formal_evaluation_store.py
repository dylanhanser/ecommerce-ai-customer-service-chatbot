"""Offline Stage B2 durable-store and closed fault-controller evidence."""
from __future__ import annotations

import dataclasses
import copy
import hashlib
import inspect
import json
import math
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

import formal_evaluation_inflight as inflight
import formal_evaluation_orchestration as orchestration
import formal_evaluation_store as store
import formal_evaluation_transport as transport
import run_formal_evaluation as runner


def _deny_network(*_args, **_kwargs):
    raise AssertionError("NETWORK_FORBIDDEN")


@pytest.fixture(autouse=True)
def offline_socket_guard(monkeypatch):
    monkeypatch.setattr(socket, "socket", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)


INHERITED = (
    "after_call_started_published_exit",
    "after_fake_client_returned_mark",
    "after_fake_client_returned_exit",
    "after_private_commit_published_exit",
    "after_committed_archive_published_exit",
)
ADDED = (
    "before_atomic_temp_create_error",
    "after_atomic_temp_partial_write_error",
    "before_atomic_temp_flush_error",
    "before_atomic_temp_fsync_error",
    "during_atomic_temp_close_error",
    "before_atomic_publication_error",
    "after_atomic_publication_before_readback_error",
    "during_atomic_publication_readback_error",
    "before_mutable_record_publication_error",
    "before_post_call_archive_publication_error",
    "before_private_commit_publication_error",
    "before_owned_temp_cleanup_error",
    "during_atomic_publication_recovery_readback_error",
    "during_atomic_publication_recovery_invalid_bytes",
    "during_atomic_temp_failure_then_close_error",
    "during_atomic_publication_readback_then_close_error",
    "during_atomic_publication_recovery_readback_then_close_error",
    "during_atomic_publication_recovery_validation_then_close_error",
)

TARGETS = (
    "RUN_CONTRACT",
    "PREPARED_ARCHIVE",
    "PROVIDER_COMMIT",
    "PREPARED_MUTABLE",
)
MUTABLE_BRANCHES = (
    "PREPARED_MUTABLE",
    "CALL_STARTED_MUTABLE",
    "PRE_SEND_RETRYABLE_MUTABLE_A1",
    "PRE_SEND_RETRYABLE_MUTABLE_A2",
    "PRE_SEND_RETRYABLE_MUTABLE_A3",
    "PROVIDER_RETURNED_MUTABLE",
    "POST_CALL_RETRYABLE_MUTABLE_A1",
    "POST_CALL_RETRYABLE_MUTABLE_A2",
    "POST_CALL_RETRYABLE_MUTABLE_A3",
    "TERMINAL_MUTABLE",
    "UNCERTAIN_MUTABLE",
    "LOCAL_POINTER_MUTABLE",
    "COMMITTED_POINTER_MUTABLE",
)
POST_CALL_BRANCHES = (
    "POST_PROVIDER_RETURNED",
    "POST_RETRYABLE",
    "POST_TERMINAL",
    "POST_UNCERTAIN",
)
COMMIT_BRANCHES = (
    "COMMIT_PROVIDER",
    "COMMIT_LOCAL",
    "COMMIT_RQ3_T1_PROVIDER",
    "COMMIT_RQ3_T1_LOCAL",
    "COMMIT_RQ3_T2_PROVIDER",
    "COMMIT_RQ3_T2_LOCAL",
)
CLEAN_BRANCHES = (
    "CLEAN_CONTRACT_TEMP",
    "CLEAN_ARCHIVE_TEMP",
    "CLEAN_COMMIT_TEMP",
    "CLEAN_MUTABLE_TEMP",
)


def _rows(point: str, branches: tuple[str, ...], vector: str):
    return tuple((point, branch, vector) for branch in branches)


TRANSITIONS = (
    _rows("before_atomic_temp_create_error", TARGETS, "B")
    + _rows("after_atomic_temp_partial_write_error", TARGETS, "T")
    + _rows("before_atomic_temp_flush_error", TARGETS, "T")
    + _rows("before_atomic_temp_fsync_error", TARGETS, "T")
    + _rows("during_atomic_temp_close_error", TARGETS, "T")
    + _rows(
        "before_atomic_publication_error",
        (
            "RUN_CONTRACT",
            "PREPARED_ARCHIVE",
            "LOCAL_REPAIR_ARCHIVE",
            "PROVIDER_REPAIR_ARCHIVE",
            "PROVIDER_COMMIT",
            "COMMITTED_POINTER_MUTABLE",
        ),
        "T",
    )
    + _rows("after_atomic_publication_before_readback_error", TARGETS, "S0")
    + _rows("during_atomic_publication_readback_error", TARGETS, "S1")
    + _rows("before_mutable_record_publication_error", MUTABLE_BRANCHES, "T")
    + _rows(
        "before_post_call_archive_publication_error",
        POST_CALL_BRANCHES,
        "PC",
    )
    + (
        ("before_private_commit_publication_error", "COMMIT_PROVIDER", "PP"),
        ("before_private_commit_publication_error", "COMMIT_LOCAL", "T"),
        (
            "before_private_commit_publication_error",
            "COMMIT_RQ3_T1_PROVIDER",
            "PP",
        ),
        (
            "before_private_commit_publication_error",
            "COMMIT_RQ3_T1_LOCAL",
            "T",
        ),
        (
            "before_private_commit_publication_error",
            "COMMIT_RQ3_T2_PROVIDER",
            "PP",
        ),
        (
            "before_private_commit_publication_error",
            "COMMIT_RQ3_T2_LOCAL",
            "T",
        ),
    )
    + _rows("before_owned_temp_cleanup_error", CLEAN_BRANCHES, "B")
    + _rows(
        "during_atomic_publication_recovery_readback_error",
        TARGETS,
        "FR",
    )
    + _rows("during_atomic_publication_recovery_invalid_bytes", TARGETS, "FV")
    + (
        (
            "during_atomic_temp_failure_then_close_error",
            "RUN_CONTRACT",
            "TC",
        ),
        (
            "during_atomic_temp_failure_then_close_error",
            "PREPARED_ARCHIVE",
            "TC",
        ),
        (
            "during_atomic_temp_failure_then_close_error",
            "PROVIDER_COMMIT",
            "TC",
        ),
        (
            "during_atomic_temp_failure_then_close_error",
            "PREPARED_MUTABLE",
            "TC",
        ),
    )
    + _rows(
        "during_atomic_publication_readback_then_close_error",
        TARGETS,
        "VC",
    )
    + _rows(
        "during_atomic_publication_recovery_readback_then_close_error",
        TARGETS,
        "RC",
    )
    + _rows(
        "during_atomic_publication_recovery_validation_then_close_error",
        TARGETS,
        "VRC",
    )
)

K = {
    "B": (1, 0, 0, 0, 0, 0, 0, 0),
    "T": (1, 0, 0, 0, 0, 1, 0, 0),
    "S0": (1, 1, 1, 1, 1, 1, 0, 1),
    "S1": (1, 1, 1, 1, 1, 1, 1, 1),
    "FR": (1, 1, 1, 1, 1, 1, 1, 1),
    "FV": (1, 1, 1, 1, 1, 1, 1, 1),
    "TC": (1, 0, 0, 0, 0, 1, 0, 0),
    "VC": (1, 1, 1, 1, 0, 1, 1, 0),
    "RC": (1, 1, 1, 1, 1, 1, 1, 1),
    "VRC": (1, 1, 1, 1, 1, 1, 1, 1),
    "PC": (1, 2, 2, 2, 0, 3, 2, 0),
    "PP": (1, 4, 4, 4, 0, 5, 4, 0),
}
H_LENGTHS = {
    "B": (0, 0, 0),
    "T": (1, 0, 0),
    "S0": (1, 0, 1),
    "S1": (1, 1, 1),
    "FR": (1, 1, 1),
    "FV": (1, 1, 1),
    "TC": (1, 0, 0),
    "VC": (1, 1, 0),
    "RC": (1, 1, 1),
    "VRC": (1, 1, 1),
    "PC": (3, 2, 0),
    "PP": (5, 4, 0),
}
SUCCESS_VECTORS = {"S0", "S1"}
SECONDARY_VECTORS = {"TC", "VC", "RC", "VRC"}
INITIAL_VECTORS = {"S0", "S1", "FR", "FV", "RC", "VRC"}
NONCANONICAL_VECTORS = {"FV", "VRC"}
POST_PUBLICATION_VECTORS = {
    "S0",
    "S1",
    "FR",
    "FV",
    "VC",
    "RC",
    "VRC",
}


@pytest.fixture
def state_root(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="stage-b2-") as name:
        root = Path(name)
        monkeypatch.setattr(store, "_PRIVATE_STATE_ROOT", root)
        store._ensure_fixed_directories(root)
        yield root


def _target(root: Path, branch: str, suffix: int = 0) -> tuple[Path, bool]:
    token = f"{suffix + 1:064x}"
    if branch == "RUN_CONTRACT" or branch == "CLEAN_CONTRACT_TEMP":
        return root / "run_contract.json", False
    if branch in MUTABLE_BRANCHES or branch == "CLEAN_MUTABLE_TEMP":
        return root / "journals" / f"{'b' * 64}.json", True
    if "ARCHIVE" in branch or branch.startswith("POST_") or branch == "CLEAN_ARCHIVE_TEMP":
        directory = root / "attempts" / ("a" * 64)
        directory.mkdir(exist_ok=True)
        sequence = min(suffix + 1, 4)
        return directory / f"1-{sequence}-{token}.json", False
    if "COMMIT" in branch or branch == "CLEAN_COMMIT_TEMP":
        return root / "commits" / f"1-{token}.json", False
    raise AssertionError(f"unknown transition branch: {branch}")


def _publish(path: Path, replace: bool, value: dict[str, object]) -> bool:
    return store._atomic_publish_json(
        path,
        value,
        replace=replace,
        maximum=store._COMMIT_LIMIT,
    )


def _temps(root: Path) -> list[Path]:
    result = list(root.glob(".*.tmp"))
    result.extend((root / "journals").glob(".*.tmp"))
    result.extend((root / "commits").glob(".*.tmp"))
    result.extend((root / "attempts").glob("*/.*.tmp"))
    return sorted(result)


def _count_tuple(observation):
    return tuple(
        getattr(observation, name)
        for name in store._FAULT_COUNT_NAMES
    )


def _assert_absent_group(observation, role: str) -> None:
    assert all(
        getattr(observation, f"{role}_exception_{suffix}") is None
        for suffix in (
            "id",
            "type",
            "category",
            "args",
            "cause_id",
            "context_id",
            "suppress_context",
            "notes",
            "traceback_ids",
            "retained",
        )
    )


def _assert_group(observation, role: str, category: str) -> None:
    assert getattr(observation, f"{role}_exception_id") > 0
    assert (
        getattr(observation, f"{role}_exception_type")
        == "formal_evaluation_store.StoreError"
    )
    assert getattr(observation, f"{role}_exception_category") == category
    assert getattr(observation, f"{role}_exception_args") == (category,)
    assert getattr(observation, f"{role}_exception_cause_id") is None
    assert getattr(observation, f"{role}_exception_suppress_context") is False
    assert getattr(observation, f"{role}_exception_notes") == ()
    assert getattr(observation, f"{role}_exception_traceback_ids")
    assert getattr(observation, f"{role}_exception_retained") is True


def _assert_vector(observation, vector: str, error: BaseException | None) -> None:
    assert _count_tuple(observation) == K[vector]
    opened = (
        observation.temporary_opened_handle_ids,
        observation.initial_verification_opened_handle_ids,
        observation.recovery_opened_handle_ids,
    )
    closed = (
        observation.temporary_close_attempt_handle_ids,
        observation.initial_verification_close_attempt_handle_ids,
        observation.recovery_close_attempt_handle_ids,
    )
    assert tuple(map(len, opened)) == H_LENGTHS[vector]
    assert opened == closed
    live_tokens = tuple(token for family in opened for token in family)
    assert len(live_tokens) == len(set(live_tokens))

    if vector in INITIAL_VECTORS:
        _assert_group(observation, "initial", "STORE_IO_FAILURE")
    else:
        _assert_absent_group(observation, "initial")
    if vector in SUCCESS_VECTORS:
        _assert_absent_group(observation, "primary")
        _assert_absent_group(observation, "secondary")
        assert error is None
        return

    category = (
        "STORE_NONCANONICAL_JSON"
        if vector in NONCANONICAL_VECTORS
        else "STORE_IO_FAILURE"
    )
    _assert_group(observation, "primary", category)
    assert type(error) is store.StoreError
    assert id(error) == observation.primary_exception_id
    assert error.category == category
    final_traceback = []
    current = error.__traceback__
    while current is not None:
        final_traceback.append(id(current))
        current = current.tb_next
    suffix = observation.primary_exception_traceback_ids
    assert tuple(final_traceback[-len(suffix) :]) == suffix
    if vector in SECONDARY_VECTORS:
        _assert_group(observation, "secondary", "STORE_IO_FAILURE")
        assert (
            observation.secondary_exception_context_id
            == observation.primary_exception_id
        )
        assert observation.secondary_exception_id != observation.primary_exception_id
        assert set(observation.secondary_exception_traceback_ids).isdisjoint(
            final_traceback
        )
    else:
        _assert_absent_group(observation, "secondary")


def _archive_candidate(
    root: Path,
    contract,
    journal,
    *,
    sequence: int,
    previous_sha: str | None,
    predecessor_attempt_id: str | None,
    predecessor_terminal_sha: str | None,
    private_commit_sha: str | None = None,
):
    value = {
        "schema_version": 1,
        "run_contract_sha256": contract["run_contract_sha256"],
        "execution_unit_id": journal.identity.execution_unit_id,
        "attempt_number": journal.identity.attempt_number,
        "attempt_id": journal.identity.attempt_id,
        "sequence_number": sequence,
        "event": journal.state,
        "predecessor_attempt_id": predecessor_attempt_id,
        "predecessor_terminal_archive_sha256": predecessor_terminal_sha,
        "previous_archive_sha256": previous_sha,
        "journal": journal.to_dict(),
        "journal_sha256": inflight.journal_sha256(journal),
        "private_commit_sha256": private_commit_sha,
    }
    value["archive_sha256"] = store._archive_hash(value)
    directory = root / "attempts" / journal.identity.execution_unit_id
    directory.mkdir(exist_ok=True)
    path = directory / (
        f"{journal.identity.attempt_number}-{sequence}-"
        f"{value['journal_sha256']}.json"
    )
    loaded = store._validate_archive(
        value,
        contract_sha256=contract["run_contract_sha256"],
        expected_path=path,
    )
    assert loaded.value == value
    assert loaded.journal == journal
    return value, path


def _owned_temp_for(target: Path, value, token: str = "c") -> Path:
    temporary = target.with_name(f".{target.name}.{token * 32}.tmp")
    temporary.write_bytes(store._canonical_bytes(value) + b"\n")
    assert temporary.is_file()
    return temporary


def _temp_target(temporary: Path) -> Path:
    match = store._TEMP_NAME_RE.fullmatch(temporary.name)
    assert match is not None
    return temporary.with_name(match.group("target"))


def _durable_snapshot(root: Path) -> dict[str, bytes]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and store._TEMP_NAME_RE.fullmatch(path.name) is None:
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _load_exact_unit_state(
    contract,
    execution_unit_id: str,
    *,
    repair_mutable: bool,
):
    with store._RunWideLock(store._PRIVATE_STATE_ROOT) as lock:
        return store._load_unit_state_locked(
            execution_unit_id,
            run_contract=contract,
            lock=lock,
            repair_mutable=repair_mutable,
        )


def _construct_unpublished_commit_candidate(plan, contract, unit):
    _publish_fixed_prepared(plan, contract, unit)
    evidence = {
        "callback_attempts": 0,
        "callback_completions": 0,
        "fake_calls": None,
    }
    with store._open_store(contract) as (opened, lock):
        unit_id = store._execution_unit_id(unit)
        state = store._load_unit_state_locked(
            unit_id,
            run_contract=opened,
            lock=lock,
        )
        assert state.tip is not None and state.tip.journal.state == "prepared"
        checkpoint, turn_one_commit_sha = store._selected_dependency_commit(
            plan,
            unit,
            run_contract=opened,
            lock=lock,
        )
        authority = runner._fixed_offline_authority()
        dependencies = authority.dependencies_for(unit, state)

        def persistence_callback(journal):
            evidence["callback_attempts"] += 1
            store._publish_journal_locked(
                journal,
                run_contract=opened,
                lock=lock,
            )
            evidence["callback_completions"] += 1

        outcome = runner.orchestrate_offline_unit(
            plan,
            unit,
            journal_persistence_callback=persistence_callback,
            retry_predecessor=store._retry_predecessor(state),
            journal=state.tip.journal,
            checkpoint_evidence=checkpoint,
            **dependencies,
        )
        evidence["fake_calls"] = dependencies["fake_raw_client"].call_count
        assert evidence["fake_calls"] == outcome.provider_call_count
        state = store._load_unit_state_locked(
            unit_id,
            run_contract=opened,
            lock=lock,
        )
        candidate = store._construct_private_commit(
            plan,
            unit,
            outcome,
            run_contract=opened,
            state=state,
            turn_one_commit_sha256=turn_one_commit_sha,
        )
        turn_one_commit = None
        if turn_one_commit_sha is not None:
            pair = store._plan_pair(plan, unit)
            assert pair is not None
            turn_one_state = store._load_unit_state_locked(
                store._execution_unit_id(pair[0]),
                run_contract=opened,
                lock=lock,
            )
            turn_one_commit = store._load_commit_for_unit_locked(
                plan,
                pair[0],
                run_contract=opened,
                lock=lock,
                state=turn_one_state,
            )
            assert turn_one_commit is not None
            assert turn_one_commit["envelope_sha256"] == turn_one_commit_sha
        path = store._commit_path(store._PRIVATE_STATE_ROOT, unit)
        validated = store._validate_private_commit(
            candidate,
            plan=plan,
            unit=unit,
            run_contract=opened,
            state=state,
            expected_path=path,
            turn_one_commit=turn_one_commit,
        )
        assert validated == candidate
    return candidate, path, evidence


def _publish_unreconciled_commit(plan, contract, unit):
    candidate, path, evidence = _construct_unpublished_commit_candidate(
        plan, contract, unit
    )
    with store._open_store(contract) as (opened, lock):
        published, created = store._publish_private_commit_locked(
            candidate,
            unit=unit,
            lock=lock,
        )
        assert created is True
        assert published == candidate
        state = store._load_unit_state_locked(
            store._execution_unit_id(unit),
            run_contract=opened,
            lock=lock,
        )
        loaded = store._load_commit_for_unit_locked(
            plan,
            unit,
            run_contract=opened,
            lock=lock,
            state=state,
        )
        assert loaded == candidate
    assert path.read_bytes() == store._canonical_bytes(candidate) + b"\n"
    return candidate, evidence


def _assert_transition_temp(
    root: Path,
    *,
    point: str,
    branch: str,
    target: Path,
    value,
    should_exist: bool,
) -> None:
    temps = _temps(root)
    if not should_exist:
        assert temps == []
        return
    assert len(temps) == 1
    temporary = temps[0]
    assert _temp_target(temporary) == target
    raw = store._canonical_bytes(value) + b"\n"
    partial = point == "after_atomic_temp_partial_write_error" or (
        point == "during_atomic_temp_failure_then_close_error"
        and branch == "RUN_CONTRACT"
    )
    assert temporary.read_bytes() == (raw[: len(raw) // 2] if partial else raw)


def _prepare_direct_atomic_transition(root, plan, contract, point, branch, vector):
    unit = _selected_unit(plan, provider=True)
    preparation = {"fake_calls": 0, "callback_attempts": 0, "callback_completions": 0}
    if branch == "RUN_CONTRACT":
        with store._RunWideLock(root):
            pass
        value = json.loads(store._canonical_bytes(contract))
        store._validate_run_contract_shape(value)
        target = root / "run_contract.json"
        replace = False
        maximum = store._RUN_CONTRACT_LIMIT
    else:
        progress = runner.durable_progress(plan)
        assert progress.total_successful_units == 0
        if branch == "PREPARED_ARCHIVE":
            journal = _capture_initial_prepared(plan, unit)
            value, target = _archive_candidate(
                root,
                contract,
                journal,
                sequence=1,
                previous_sha=None,
                predecessor_attempt_id=None,
                predecessor_terminal_sha=None,
            )
            replace = False
            maximum = store._ARCHIVE_LIMIT
        elif branch == "PREPARED_MUTABLE":
            journal, archive = _build_archive_only_tip(
                plan, contract, root, unit, "PREPARED_MUTABLE"
            )
            value = store._mutable_from_archive(archive)
            target = root / "journals" / f"{journal.identity.execution_unit_id}.json"
            validated, validated_journal = store._validate_mutable(
                value,
                contract_sha256=contract["run_contract_sha256"],
                execution_unit_id=journal.identity.execution_unit_id,
            )
            assert validated == value and validated_journal == journal
            replace = True
            maximum = store._JOURNAL_LIMIT
        elif branch == "PROVIDER_COMMIT":
            value, target, preparation = _construct_unpublished_commit_candidate(
                plan, contract, unit
            )
            assert preparation == {
                "callback_attempts": 2,
                "callback_completions": 2,
                "fake_calls": 1,
            }
            replace = False
            maximum = store._COMMIT_LIMIT
        else:
            raise AssertionError(f"unsupported direct target branch: {branch}")

    assert not target.exists()
    result = {"value": None}

    def operation():
        with store._RunWideLock(root) as lock:
            lock.require_active()
            result["value"] = store._atomic_publish_json(
                target,
                value,
                replace=replace,
                maximum=maximum,
            )
        return result["value"]

    def verify(_error):
        published = vector in POST_PUBLICATION_VECTORS
        assert target.exists() is published
        if published:
            assert target.read_bytes() == store._canonical_bytes(value) + b"\n"
        _assert_transition_temp(
            root,
            point=point,
            branch=branch,
            target=target,
            value=value,
            should_exist=not published and vector != "B",
        )
        if branch == "RUN_CONTRACT":
            reopened = runner.durable_progress(plan)
            assert reopened.total_successful_units == 0
            assert reopened.next_eligible_execution_order == 1
            assert target.read_bytes() == store._canonical_bytes(contract) + b"\n"
        elif branch in {"PREPARED_ARCHIVE", "PREPARED_MUTABLE"}:
            with store._open_store(contract) as (opened, lock):
                state = store._load_unit_state_locked(
                    store._execution_unit_id(unit),
                    run_contract=opened,
                    lock=lock,
                )
                category, _state, commit = store._direct_unit_category_locked(
                    plan,
                    unit,
                    run_contract=opened,
                    lock=lock,
                )
            if branch == "PREPARED_ARCHIVE" and not published:
                assert state.tip is None and state.mutable is None
                assert category == "initial-executable"
            else:
                assert state.tip is not None
                expected_archive_sha = (
                    value["archive_sha256"]
                    if branch == "PREPARED_ARCHIVE"
                    else value["latest_archive_sha256"]
                )
                assert state.tip.value["archive_sha256"] == expected_archive_sha
                assert state.mutable == store._mutable_from_archive(state.tip.value)
                assert category == "same-attempt-continuable"
            assert commit is None
        else:
            reopened = _safe_durable_call(plan, unit)
            assert reopened.provider_call_count == 0
            if published:
                assert reopened.action == "completed"
                assert reopened.private_commit_sha256 == value["envelope_sha256"]
            else:
                assert reopened.action == "permanently_non_executable"
                assert reopened.block_category == "provider_returned_without_commit"
        assert _temps(root) == []
        assert preparation["fake_calls"] == (1 if branch == "PROVIDER_COMMIT" else 0)

    return operation, verify


def _prepare_unreconciled_pointer_tip(root, plan, contract, branch):
    provider = branch == "COMMITTED_POINTER_MUTABLE"
    unit = _selected_unit(plan, provider=provider)
    commit, preparation = _publish_unreconciled_commit(plan, contract, unit)
    unit_id = store._execution_unit_id(unit)
    state = _load_exact_unit_state(
        contract,
        unit_id,
        repair_mutable=False,
    )
    assert state.tip is not None and state.mutable is not None
    previous_tip = state.tip
    if provider:
        success = inflight.AuthoritativeSuccess.from_mapping(
            commit["authoritative_success"]
        )
        journal = inflight.reconcile(
            previous_tip.journal,
            success,
            previous_tip.journal.identity,
        )
        sequence = 4
    else:
        journal = previous_tip.journal
        sequence = 2
    tip_value = _publish_archive_only(
        root,
        contract,
        journal,
        sequence=sequence,
        previous_sha=previous_tip.value["archive_sha256"],
        predecessor_attempt_id=previous_tip.value["predecessor_attempt_id"],
        predecessor_terminal_sha=previous_tip.value[
            "predecessor_terminal_archive_sha256"
        ],
        private_commit_sha=commit["envelope_sha256"],
    )
    lagging = store._read_json(
        root / "journals" / f"{unit_id}.json",
        store._JOURNAL_LIMIT,
    )
    assert lagging == store._mutable_from_archive(previous_tip.value)
    state = _load_exact_unit_state(contract, unit_id, repair_mutable=False)
    assert state.tip is not None
    assert state.tip.value["archive_sha256"] == tip_value["archive_sha256"]
    assert state.mutable == lagging
    return unit, commit, tip_value, lagging, preparation


def _prepare_mutable_transition(root, plan, contract, point, branch):
    runner.durable_progress(plan)
    if branch in {"LOCAL_POINTER_MUTABLE", "COMMITTED_POINTER_MUTABLE"}:
        unit, commit, tip_value, old_mutable, preparation = (
            _prepare_unreconciled_pointer_tip(root, plan, contract, branch)
        )
        unit_id = store._execution_unit_id(unit)
    else:
        unit = _selected_unit(plan, provider=True)
        tip_journal, tip_value = _build_archive_only_tip(
            plan,
            contract,
            root,
            unit,
            branch,
        )
        unit_id = tip_journal.identity.execution_unit_id
        state = _load_exact_unit_state(contract, unit_id, repair_mutable=False)
        assert state.tip is not None and state.mutable is None
        commit = None
        preparation = {
            "callback_attempts": 0,
            "callback_completions": 0,
            "fake_calls": 0,
        }
        mutable_path = root / "journals" / f"{unit_id}.json"
        if branch == "PREPARED_MUTABLE":
            old_mutable = None
        else:
            assert len(state.archives) >= 2
            old_mutable = store._mutable_from_archive(state.archives[-2].value)
            assert store._atomic_publish_json(
                mutable_path,
                old_mutable,
                replace=True,
                maximum=store._JOURNAL_LIMIT,
            )
            checked, _journal = store._validate_mutable(
                store._read_json(mutable_path, store._JOURNAL_LIMIT),
                contract_sha256=contract["run_contract_sha256"],
                execution_unit_id=unit_id,
            )
            assert checked == old_mutable

    mutable_path = root / "journals" / f"{unit_id}.json"
    old_bytes = mutable_path.read_bytes() if mutable_path.exists() else None
    expected_mutable = store._mutable_from_archive(tip_value)
    result = {"state": None}

    def operation():
        with store._open_store(contract) as (opened, lock):
            result["state"] = store._load_unit_state_locked(
                unit_id,
                run_contract=opened,
                lock=lock,
            )
        return result["state"]

    def verify(_error):
        assert mutable_path.exists() is (old_bytes is not None)
        if old_bytes is not None:
            assert mutable_path.read_bytes() == old_bytes
        _assert_transition_temp(
            root,
            point=point,
            branch=branch,
            target=mutable_path,
            value=expected_mutable,
            should_exist=True,
        )
        with store._open_store(contract) as (opened, lock):
            repaired = store._load_unit_state_locked(
                unit_id,
                run_contract=opened,
                lock=lock,
            )
            category, _state, loaded_commit = store._direct_unit_category_locked(
                plan,
                unit,
                run_contract=opened,
                lock=lock,
            )
        assert repaired.tip is not None
        assert repaired.tip.value["archive_sha256"] == tip_value["archive_sha256"]
        assert repaired.mutable == expected_mutable
        assert mutable_path.read_bytes() == store._canonical_bytes(expected_mutable) + b"\n"
        assert _temps(root) == []

        expected = {
            "PREPARED_MUTABLE": ("same-attempt-continuable", None, None),
            "CALL_STARTED_MUTABLE": (
                "permanently-non-executable",
                "permanently_non_executable",
                "call_started",
            ),
            "PRE_SEND_RETRYABLE_MUTABLE_A1": (
                "retry-constructible",
                "retry_constructed",
                None,
            ),
            "PRE_SEND_RETRYABLE_MUTABLE_A2": (
                "retry-constructible",
                "retry_constructed",
                None,
            ),
            "PRE_SEND_RETRYABLE_MUTABLE_A3": (
                "permanently-non-executable",
                "permanently_non_executable",
                "attempts_exhausted",
            ),
            "PROVIDER_RETURNED_MUTABLE": (
                "permanently-non-executable",
                "permanently_non_executable",
                "provider_returned_without_commit",
            ),
            "POST_CALL_RETRYABLE_MUTABLE_A1": (
                "retry-constructible",
                "retry_constructed",
                None,
            ),
            "POST_CALL_RETRYABLE_MUTABLE_A2": (
                "retry-constructible",
                "retry_constructed",
                None,
            ),
            "POST_CALL_RETRYABLE_MUTABLE_A3": (
                "permanently-non-executable",
                "permanently_non_executable",
                "attempts_exhausted",
            ),
            "TERMINAL_MUTABLE": (
                "permanently-non-executable",
                "permanently_non_executable",
                "terminal_failed",
            ),
            "UNCERTAIN_MUTABLE": (
                "permanently-non-executable",
                "permanently_non_executable",
                "uncertain",
            ),
            "LOCAL_POINTER_MUTABLE": ("successful", "completed", None),
            "COMMITTED_POINTER_MUTABLE": ("successful", "completed", None),
        }[branch]
        assert category == expected[0]
        if branch.endswith("POINTER_MUTABLE"):
            assert loaded_commit == commit
        else:
            assert loaded_commit is None
        if expected[1] is not None:
            outcome = _safe_durable_call(plan, unit)
            assert outcome.action == expected[1]
            assert outcome.block_category == expected[2]
            assert outcome.provider_call_count == 0
        assert preparation["fake_calls"] == (
            1 if branch == "COMMITTED_POINTER_MUTABLE" else 0
        )

    return operation, verify


def _prepare_repair_archive_transition(root, plan, contract, branch):
    provider = branch == "PROVIDER_REPAIR_ARCHIVE"
    runner.durable_progress(plan)
    unit = _selected_unit(plan, provider=provider)
    commit, preparation = _publish_unreconciled_commit(plan, contract, unit)
    unit_id = store._execution_unit_id(unit)
    before = _load_exact_unit_state(contract, unit_id, repair_mutable=False)
    assert before.tip is not None and before.mutable is not None
    before_mutable = copy.deepcopy(dict(before.mutable))
    before_archives = len(before.archives)

    def operation():
        return runner.orchestrate_durable_offline_unit(plan, unit)

    def verify(_error):
        archive_directory = root / "attempts" / unit_id
        durable_archives = [
            path
            for path in archive_directory.iterdir()
            if store._ARCHIVE_NAME_RE.fullmatch(path.name) is not None
        ]
        assert len(durable_archives) == before_archives
        mutable_path = root / "journals" / f"{unit_id}.json"
        assert store._read_json(mutable_path, store._JOURNAL_LIMIT) == before_mutable
        temps = _temps(root)
        assert len(temps) == 1
        target = _temp_target(temps[0])
        candidate = store._load_json_bytes(temps[0].read_bytes(), store._ARCHIVE_LIMIT)
        validated = store._validate_archive(
            candidate,
            contract_sha256=contract["run_contract_sha256"],
            expected_path=target,
        )
        assert validated.value == candidate
        assert candidate["sequence_number"] == (4 if provider else 2)
        assert candidate["event"] == ("committed" if provider else "prepared")
        assert candidate["private_commit_sha256"] == commit["envelope_sha256"]
        reopened = _safe_durable_call(plan, unit)
        assert reopened.action == "completed"
        assert reopened.provider_call_count == 0
        assert reopened.private_commit_sha256 == commit["envelope_sha256"]
        final = _load_exact_unit_state(contract, unit_id, repair_mutable=False)
        assert len(final.archives) == before_archives + 1
        assert final.tip is not None
        assert final.tip.value["sequence_number"] == (4 if provider else 2)
        assert final.mutable == store._mutable_from_archive(final.tip.value)
        assert _temps(root) == []
        assert preparation["fake_calls"] == (1 if provider else 0)

    return operation, verify


def _prepare_post_call_transition(root, plan, contract, branch):
    runner.durable_progress(plan)
    unit = _selected_unit(plan, provider=True)
    prepared = _publish_fixed_prepared(plan, contract, unit)
    assert prepared.state == "prepared"
    evidence = {
        "callback_attempts": 0,
        "callback_completions": 0,
        "fake_calls": None,
        "candidate": None,
        "tracker_state": None,
    }

    def operation():
        with store._open_store(contract) as (opened, lock):
            unit_id = store._execution_unit_id(unit)
            durable = store._load_unit_state_locked(
                unit_id,
                run_contract=opened,
                lock=lock,
            )
            assert durable.tip is not None
            authority = runner._fixed_offline_authority()
            dependencies = authority.dependencies_for(unit, durable)

            def persistence_callback(journal):
                evidence["callback_attempts"] += 1
                evidence["candidate"] = journal
                store._publish_journal_locked(
                    journal,
                    run_contract=opened,
                    lock=lock,
                )
                evidence["callback_completions"] += 1

            if branch == "POST_PROVIDER_RETURNED":
                try:
                    return runner.orchestrate_offline_unit(
                        plan,
                        unit,
                        journal_persistence_callback=persistence_callback,
                        retry_predecessor=store._retry_predecessor(durable),
                        journal=durable.tip.journal,
                        **dependencies,
                    )
                finally:
                    evidence["fake_calls"] = dependencies[
                        "fake_raw_client"
                    ].call_count

            clock = dependencies["clock"]
            provider_request_id = inflight.derive_provider_request_id(
                durable.tip.journal.identity
            )
            call_started = inflight.transition(
                durable.tip.journal,
                "call_started",
                clock(),
                provider_request_id=provider_request_id,
            )
            persistence_callback(call_started)
            fake = dependencies["fake_raw_client"]
            fake._provider_request_id = provider_request_id
            boundary = orchestration._RawClientBoundary(
                fake,
                call_started,
                clock,
                provider_request_id,
            )
            tracker = orchestration.ProviderCallTracker()
            normalized = orchestration.FixedGenerationProxy().invoke(
                boundary,
                tracker,
                [{"role": "user", "content": "stage-b2-synthetic-message"}],
                provider_request_id=provider_request_id,
            )
            evidence["fake_calls"] = fake.call_count
            evidence["tracker_state"] = tracker.state
            assert normalized.provider_request_id == provider_request_id
            state, category = {
                "POST_RETRYABLE": ("retryable_failed", "http_429"),
                "POST_TERMINAL": ("terminal_failed", "provider_rejected"),
                "POST_UNCERTAIN": ("uncertain", "timeout"),
            }[branch]
            candidate = inflight.transition(
                call_started,
                state,
                clock(),
                sanitized_outcome_category=category,
            )
            evidence["candidate"] = candidate
            return persistence_callback(candidate)

    def verify(_error):
        assert evidence["callback_attempts"] == 2
        assert evidence["callback_completions"] == 1
        assert evidence["fake_calls"] == 1
        if branch != "POST_PROVIDER_RETURNED":
            assert evidence["tracker_state"] == "validated_success"
        candidate = evidence["candidate"]
        assert type(candidate) is inflight.InflightJournal
        expected_state = {
            "POST_PROVIDER_RETURNED": "provider_returned",
            "POST_RETRYABLE": "retryable_failed",
            "POST_TERMINAL": "terminal_failed",
            "POST_UNCERTAIN": "uncertain",
        }[branch]
        assert candidate.state == expected_state
        temps = _temps(root)
        assert len(temps) == 1
        target = _temp_target(temps[0])
        unpublished = store._load_json_bytes(
            temps[0].read_bytes(), store._ARCHIVE_LIMIT
        )
        checked = store._validate_archive(
            unpublished,
            contract_sha256=contract["run_contract_sha256"],
            expected_path=target,
        )
        assert checked.journal == candidate
        assert unpublished["sequence_number"] == 3
        assert unpublished["event"] == expected_state
        unit_id = store._execution_unit_id(unit)
        archive_directory = root / "attempts" / unit_id
        archive_paths = sorted(
            (
                path
                for path in archive_directory.iterdir()
                if store._ARCHIVE_NAME_RE.fullmatch(path.name) is not None
            ),
            key=lambda path: int(store._ARCHIVE_NAME_RE.fullmatch(path.name).group("sequence")),
        )
        assert len(archive_paths) == 2
        call_started = store._validate_archive(
            store._read_json(archive_paths[-1], store._ARCHIVE_LIMIT),
            contract_sha256=contract["run_contract_sha256"],
            expected_path=archive_paths[-1],
        )
        assert call_started.journal.state == "call_started"
        mutable_path = root / "journals" / f"{unit_id}.json"
        assert store._read_json(mutable_path, store._JOURNAL_LIMIT) == (
            store._mutable_from_archive(call_started.value)
        )
        assert list((root / "commits").iterdir()) == []
        reopened = _safe_durable_call(plan, unit)
        assert reopened.action == "permanently_non_executable"
        assert reopened.block_category == "call_started"
        assert reopened.provider_call_count == 0
        assert _temps(root) == []
        durable = _load_exact_unit_state(contract, unit_id, repair_mutable=False)
        assert durable.tip is not None and durable.tip.journal.state == "call_started"
        assert durable.mutable == store._mutable_from_archive(durable.tip.value)

    return operation, verify


def _commit_branch_selection(plan, branch):
    values = {
        "COMMIT_PROVIDER": (True, "v2", None, 1),
        "COMMIT_LOCAL": (False, "v2", None, 1),
        "COMMIT_RQ3_T1_PROVIDER": (True, "context_aware", "RQ3", 1),
        "COMMIT_RQ3_T1_LOCAL": (False, "context_aware", "RQ3", 1),
        "COMMIT_RQ3_T2_PROVIDER": (True, "context_aware", "RQ3", 2),
        "COMMIT_RQ3_T2_LOCAL": (False, "context_aware", "RQ3", 2),
    }
    provider, config, rq, turn = values[branch]
    unit = _selected_unit(
        plan,
        provider=provider,
        config=config,
        rq=rq,
        turn=turn,
    )
    return unit, provider, turn


def _prepare_commit_transition(root, plan, contract, branch):
    runner.durable_progress(plan)
    unit, provider, turn = _commit_branch_selection(plan, branch)
    if turn == 2:
        _complete_turn_one_for(plan, unit)
    _publish_fixed_prepared(plan, contract, unit)
    evidence = {
        "callback_attempts": 0,
        "callback_completions": 0,
        "fake_calls": None,
        "candidate": None,
        "turn_one_commit": None,
    }

    def operation():
        with store._open_store(contract) as (opened, lock):
            unit_id = store._execution_unit_id(unit)
            state = store._load_unit_state_locked(
                unit_id,
                run_contract=opened,
                lock=lock,
            )
            assert state.tip is not None and state.tip.journal.state == "prepared"
            checkpoint, turn_one_commit_sha = store._selected_dependency_commit(
                plan,
                unit,
                run_contract=opened,
                lock=lock,
            )
            authority = runner._fixed_offline_authority()
            dependencies = authority.dependencies_for(unit, state)

            def persistence_callback(journal):
                evidence["callback_attempts"] += 1
                store._publish_journal_locked(
                    journal,
                    run_contract=opened,
                    lock=lock,
                )
                evidence["callback_completions"] += 1

            outcome = runner.orchestrate_offline_unit(
                plan,
                unit,
                journal_persistence_callback=persistence_callback,
                retry_predecessor=store._retry_predecessor(state),
                journal=state.tip.journal,
                checkpoint_evidence=checkpoint,
                **dependencies,
            )
            evidence["fake_calls"] = dependencies["fake_raw_client"].call_count
            assert evidence["fake_calls"] == outcome.provider_call_count
            state = store._load_unit_state_locked(
                unit_id,
                run_contract=opened,
                lock=lock,
            )
            candidate = store._construct_private_commit(
                plan,
                unit,
                outcome,
                run_contract=opened,
                state=state,
                turn_one_commit_sha256=turn_one_commit_sha,
            )
            evidence["candidate"] = candidate
            if turn_one_commit_sha is not None:
                pair = store._plan_pair(plan, unit)
                assert pair is not None
                turn_one_state = store._load_unit_state_locked(
                    store._execution_unit_id(pair[0]),
                    run_contract=opened,
                    lock=lock,
                )
                evidence["turn_one_commit"] = store._load_commit_for_unit_locked(
                    plan,
                    pair[0],
                    run_contract=opened,
                    lock=lock,
                    state=turn_one_state,
                )
                assert evidence["turn_one_commit"]["envelope_sha256"] == (
                    turn_one_commit_sha
                )
            path = store._commit_path(root, unit)
            validated = store._validate_private_commit(
                candidate,
                plan=plan,
                unit=unit,
                run_contract=opened,
                state=state,
                expected_path=path,
                turn_one_commit=evidence["turn_one_commit"],
            )
            assert validated == candidate
            return store._publish_private_commit_locked(
                candidate,
                unit=unit,
                lock=lock,
            )

    def verify(_error):
        assert evidence["callback_attempts"] == (2 if provider else 0)
        assert evidence["callback_completions"] == (2 if provider else 0)
        assert evidence["fake_calls"] == (1 if provider else 0)
        candidate = evidence["candidate"]
        assert candidate is not None
        path = store._commit_path(root, unit)
        assert not path.exists()
        temps = _temps(root)
        assert len(temps) == 1 and _temp_target(temps[0]) == path
        assert temps[0].read_bytes() == store._canonical_bytes(candidate) + b"\n"
        unit_id = store._execution_unit_id(unit)
        durable = _load_exact_unit_state(contract, unit_id, repair_mutable=False)
        assert durable.tip is not None
        assert durable.tip.journal.state == (
            "provider_returned" if provider else "prepared"
        )
        assert durable.tip.value["private_commit_sha256"] is None
        assert durable.mutable == store._mutable_from_archive(durable.tip.value)
        reopened = _safe_durable_call(plan, unit)
        assert reopened.provider_call_count == 0
        if provider:
            assert reopened.action == "permanently_non_executable"
            assert reopened.block_category == "provider_returned_without_commit"
            assert not path.exists()
        else:
            assert reopened.action == "completed"
            assert reopened.private_commit_sha256 is not None
            assert path.is_file()
        assert _temps(root) == []
        if branch == "COMMIT_RQ3_T1_PROVIDER":
            pair = store._plan_pair(plan, unit)
            assert pair is not None
            blocked = _safe_durable_call(plan, pair[1])
            assert blocked.action == "permanently_non_executable"
            assert blocked.block_category == "dependency_permanent"
            assert blocked.provider_call_count == 0

    return operation, verify


def _prepare_cleanup_transition(root, plan, contract, branch):
    unit = _selected_unit(plan, provider=True)
    preparation_fake_calls = 0
    if branch == "CLEAN_CONTRACT_TEMP":
        with store._RunWideLock(root):
            pass
        target = root / "run_contract.json"
        value = json.loads(store._canonical_bytes(contract))
        store._validate_run_contract_shape(value)
        temporary = _owned_temp_for(target, value)
        expected_action = "contract"
    elif branch == "CLEAN_ARCHIVE_TEMP":
        runner.durable_progress(plan)
        call_started, call_value = _build_archive_only_tip(
            plan,
            contract,
            root,
            unit,
            "CALL_STARTED_MUTABLE",
        )
        mutable = store._mutable_from_archive(call_value)
        mutable_path = root / "journals" / (
            f"{call_started.identity.execution_unit_id}.json"
        )
        assert store._atomic_publish_json(
            mutable_path,
            mutable,
            replace=True,
            maximum=store._JOURNAL_LIMIT,
        )
        clock = runner._FixedSyntheticClockV1(call_started.updated_at)
        candidate = inflight.transition(
            call_started,
            "provider_returned",
            clock(),
            provider_response_id="synthetic_response_id",
            provider_response_sha256="d" * 64,
            response_sha256=transport.sha256_text("synthetic-response"),
        )
        value, target = _archive_candidate(
            root,
            contract,
            candidate,
            sequence=3,
            previous_sha=call_value["archive_sha256"],
            predecessor_attempt_id=call_value["predecessor_attempt_id"],
            predecessor_terminal_sha=call_value[
                "predecessor_terminal_archive_sha256"
            ],
        )
        temporary = _owned_temp_for(target, value)
        expected_action = "call_started"
    elif branch == "CLEAN_COMMIT_TEMP":
        runner.durable_progress(plan)
        value, target, preparation = _construct_unpublished_commit_candidate(
            plan, contract, unit
        )
        assert preparation == {
            "callback_attempts": 2,
            "callback_completions": 2,
            "fake_calls": 1,
        }
        preparation_fake_calls = 1
        temporary = _owned_temp_for(target, value)
        expected_action = "provider_returned"
    elif branch == "CLEAN_MUTABLE_TEMP":
        runner.durable_progress(plan)
        unit, commit, tip_value, _old_mutable, preparation = (
            _prepare_unreconciled_pointer_tip(
                root,
                plan,
                contract,
                "COMMITTED_POINTER_MUTABLE",
            )
        )
        assert preparation["fake_calls"] == 1
        preparation_fake_calls = 1
        value = store._mutable_from_archive(tip_value)
        target = root / "journals" / f"{store._execution_unit_id(unit)}.json"
        temporary = _owned_temp_for(target, value)
        expected_action = "committed"
        assert commit["envelope_sha256"] == value["private_commit_sha256"]
    else:
        raise AssertionError(f"unsupported cleanup branch: {branch}")

    before = _durable_snapshot(root)

    def operation():
        if branch == "CLEAN_CONTRACT_TEMP":
            return runner.durable_progress(plan)
        return runner.orchestrate_durable_offline_unit(plan, unit)

    def verify(_error):
        assert temporary.is_file()
        assert temporary.read_bytes() == store._canonical_bytes(value) + b"\n"
        assert _durable_snapshot(root) == before
        if expected_action == "contract":
            progress = runner.durable_progress(plan)
            assert progress.total_successful_units == 0
            assert target.is_file()
            assert target.read_bytes() == store._canonical_bytes(contract) + b"\n"
        else:
            reopened = _safe_durable_call(plan, unit)
            assert reopened.provider_call_count == 0
            if expected_action == "call_started":
                assert reopened.action == "permanently_non_executable"
                assert reopened.block_category == "call_started"
            elif expected_action == "provider_returned":
                assert reopened.action == "permanently_non_executable"
                assert reopened.block_category == "provider_returned_without_commit"
            else:
                assert reopened.action == "completed"
                state = _load_exact_unit_state(
                    contract,
                    store._execution_unit_id(unit),
                    repair_mutable=False,
                )
                assert state.tip is not None
                assert state.mutable == store._mutable_from_archive(state.tip.value)
        assert not temporary.exists()
        assert _temps(root) == []
        assert preparation_fake_calls == (
            1
            if branch in {"CLEAN_COMMIT_TEMP", "CLEAN_MUTABLE_TEMP"}
            else 0
        )

    return operation, verify


def _prepare_authorized_transition(root, plan, contract, point, branch, vector):
    if point == "before_private_commit_publication_error":
        return _prepare_commit_transition(root, plan, contract, branch)
    if point == "before_post_call_archive_publication_error":
        return _prepare_post_call_transition(root, plan, contract, branch)
    if point == "before_owned_temp_cleanup_error":
        return _prepare_cleanup_transition(root, plan, contract, branch)
    if branch in {"LOCAL_REPAIR_ARCHIVE", "PROVIDER_REPAIR_ARCHIVE"}:
        assert point == "before_atomic_publication_error"
        return _prepare_repair_archive_transition(root, plan, contract, branch)
    if point == "before_mutable_record_publication_error":
        assert branch in MUTABLE_BRANCHES
        return _prepare_mutable_transition(root, plan, contract, point, branch)
    if point == "before_atomic_publication_error" and branch == (
        "COMMITTED_POINTER_MUTABLE"
    ):
        return _prepare_mutable_transition(root, plan, contract, point, branch)
    assert branch in TARGETS
    return _prepare_direct_atomic_transition(
        root,
        plan,
        contract,
        point,
        branch,
        vector,
    )


@pytest.mark.parametrize(
    "point,branch,vector",
    TRANSITIONS,
    ids=lambda value: str(value),
)
def test_each_authorized_transition_positive(
    state_root,
    frozen_plan_and_contract,
    point,
    branch,
    vector,
):
    root = state_root
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    operation, verify = _prepare_authorized_transition(
        root,
        plan,
        contract,
        point,
        branch,
        vector,
    )
    error = None
    with store._install_stage_b2_test_fault_controller_for_tests(root, point):
        if vector in SUCCESS_VECTORS:
            assert operation() is True
        else:
            with pytest.raises(store.StoreError) as caught:
                operation()
            error = caught.value
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, vector, error)
    verify(error)


@pytest.mark.parametrize(
    "point,branch,vector",
    TRANSITIONS,
    ids=lambda value: str(value),
)
def test_each_authorized_transition_has_independent_missing_trigger_negative(
    state_root,
    point,
    branch,
    vector,
):
    del branch, vector
    root = state_root
    with store._install_stage_b2_test_fault_controller_for_tests(root, point):
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        assert _count_tuple(observation) == (0,) * 8
        assert all(
            getattr(observation, name) == () for name in store._FAULT_HANDLE_NAMES
        )
        for role in store._FAULT_EXCEPTION_ROLES:
            _assert_absent_group(observation, role)


def test_closed_vocabulary_and_exact_observation_shape():
    assert store._FAULT_POINTS == frozenset(INHERITED + ADDED)
    assert len(store._FAULT_POINTS) == 23
    assert len(TRANSITIONS) == 85
    assert len(set(TRANSITIONS)) == 85
    assert [field.name for field in dataclasses.fields(
        store._StageB2TestFaultObservationV1
    )] == [
        "schema_version",
        "fault_point",
        "controller_identity",
        "controller_root",
        "owner_pid",
        "owner_thread_id",
        "trigger_count",
        "publication_attempt_count",
        "successful_publication_count",
        "initial_verification_readback_attempt_count",
        "recovery_readback_attempt_count",
        "atomic_temp_close_attempt_count",
        "initial_verification_handle_close_attempt_count",
        "recovery_readback_handle_close_attempt_count",
        "temporary_opened_handle_ids",
        "temporary_close_attempt_handle_ids",
        "initial_verification_opened_handle_ids",
        "initial_verification_close_attempt_handle_ids",
        "recovery_opened_handle_ids",
        "recovery_close_attempt_handle_ids",
        "initial_exception_id",
        "initial_exception_type",
        "initial_exception_category",
        "initial_exception_args",
        "initial_exception_cause_id",
        "initial_exception_context_id",
        "initial_exception_suppress_context",
        "initial_exception_notes",
        "initial_exception_traceback_ids",
        "initial_exception_retained",
        "primary_exception_id",
        "primary_exception_type",
        "primary_exception_category",
        "primary_exception_args",
        "primary_exception_cause_id",
        "primary_exception_context_id",
        "primary_exception_suppress_context",
        "primary_exception_notes",
        "primary_exception_traceback_ids",
        "primary_exception_retained",
        "secondary_exception_id",
        "secondary_exception_type",
        "secondary_exception_category",
        "secondary_exception_args",
        "secondary_exception_cause_id",
        "secondary_exception_context_id",
        "secondary_exception_suppress_context",
        "secondary_exception_notes",
        "secondary_exception_traceback_ids",
        "secondary_exception_retained",
    ]


def test_controller_installation_nested_restoration_and_fresh_state(
    state_root,
):
    root = state_root
    point = "before_atomic_temp_create_error"
    with pytest.raises(store.StoreError) as inactive:
        store._stage_b2_test_fault_observation_for_tests(point)
    assert inactive.value.category == "STORE_TEST_FAULT_INVALID"
    with store._install_stage_b2_test_fault_controller_for_tests(root, point):
        before = store._stage_b2_test_fault_observation_for_tests(point)
        with pytest.raises(store.StoreError) as nested:
            with store._install_stage_b2_test_fault_controller_for_tests(
                root, "before_atomic_temp_flush_error"
            ):
                pass
        assert nested.value.category == "STORE_TEST_FAULT_INVALID"
        after = store._stage_b2_test_fault_observation_for_tests(point)
        assert after == before
        with pytest.raises(store.StoreError):
            _publish(
                root / "run_contract.json",
                False,
                {"schema_version": 1},
            )
        assert store._stage_b2_test_fault_observation_for_tests(point).trigger_count == 1
    with pytest.raises(store.StoreError):
        store._stage_b2_test_fault_observation_for_tests(point)
    with store._install_stage_b2_test_fault_controller_for_tests(root, point):
        fresh = store._stage_b2_test_fault_observation_for_tests(point)
        assert _count_tuple(fresh) == (0,) * 8


def test_observation_is_frozen_detached_and_owner_thread_only(state_root):
    root = state_root
    point = "before_atomic_temp_create_error"
    with store._install_stage_b2_test_fault_controller_for_tests(root, point):
        first = store._stage_b2_test_fault_observation_for_tests(point)
        with pytest.raises(dataclasses.FrozenInstanceError):
            first.trigger_count = 7
        failures = []

        def wrong_thread():
            try:
                store._stage_b2_test_fault_observation_for_tests(point)
            except store.StoreError as exc:
                failures.append(exc.category)

        thread = threading.Thread(target=wrong_thread)
        thread.start()
        thread.join()
        assert failures == ["STORE_TEST_FAULT_INVALID"]
        assert store._stage_b2_test_fault_observation_for_tests(point) == first


def test_exceptional_outer_exit_clears_state_and_later_install_is_fresh(
    state_root,
):
    point = "before_atomic_temp_create_error"
    failure = RuntimeError("synthetic outer failure")
    with pytest.raises(RuntimeError) as caught:
        with store._install_stage_b2_test_fault_controller_for_tests(
            state_root, point
        ):
            initial = store._stage_b2_test_fault_observation_for_tests(point)
            assert _count_tuple(initial) == (0,) * 8
            raise failure
    assert caught.value is failure
    with pytest.raises(store.StoreError) as inactive:
        store._stage_b2_test_fault_observation_for_tests(point)
    assert inactive.value.category == "STORE_TEST_FAULT_INVALID"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        fresh = store._stage_b2_test_fault_observation_for_tests(point)
        assert _count_tuple(fresh) == (0,) * 8
        with pytest.raises(store.StoreError) as wrong_point:
            store._stage_b2_test_fault_observation_for_tests(
                "before_atomic_temp_flush_error"
            )
        assert wrong_point.value.category == "STORE_TEST_FAULT_INVALID"


@pytest.mark.parametrize(
    "invalid",
    (
        "before_atomic_temp_close_error",
        "BEFORE_ATOMIC_TEMP_CREATE_ERROR",
        "before_atomic_temp_create_error ",
        "",
        None,
        1,
        True,
    ),
)
def test_invalid_fault_points_fail_before_durable_access(
    state_root, invalid
):
    root = state_root
    before = sorted(path.name for path in root.iterdir())
    with pytest.raises(store.StoreError) as caught:
        with store._install_stage_b2_test_fault_controller_for_tests(root, invalid):
            pass
    assert caught.value.category == "STORE_TEST_FAULT_INVALID"
    assert sorted(path.name for path in root.iterdir()) == before


def test_disabled_fault_injection_is_behavior_neutral(state_root):
    root = state_root
    assert store._STAGE_B2_TEST_FAULT_CONTROLLER is None
    path, replace = _target(root, "RUN_CONTRACT")
    value = {"schema_version": 1, "probe": "disabled-controller"}
    assert _publish(path, replace, value) is True
    assert path.read_bytes() == store._canonical_bytes(value) + b"\n"
    assert _temps(root) == []


def test_controller_metadata_uses_exact_process_thread_and_normalized_root(
    state_root,
):
    root = state_root
    point = "before_atomic_temp_create_error"
    with store._install_stage_b2_test_fault_controller_for_tests(root, point) as controller:
        value = store._stage_b2_test_fault_observation_for_tests(point)
        assert value.schema_version == 1
        assert value.controller_identity == id(controller)
        assert value.controller_root == os.path.normcase(str(root.resolve(strict=True)))
        assert value.owner_pid == os.getpid()
        assert value.owner_thread_id == threading.get_ident()


@pytest.fixture(scope="session")
def frozen_plan_and_contract():
    plan = runner.build_plan()
    runner.validate_plan(plan)
    assert len(plan) == 190
    assert runner.plan_fingerprint(plan) == store._PLAN_FINGERPRINT
    contract = dict(runner.build_durable_run_contract(plan))
    return _FrozenPlanAuthority(plan, contract)


@dataclasses.dataclass(frozen=True, repr=False)
class _FrozenPlanAuthority:
    plan: list[dict]
    contract: dict

    def __repr__(self) -> str:
        return "<frozen-plan-authority>"


def _selected_unit(
    plan,
    *,
    provider: bool,
    config: str = "v2",
    rq: str | None = None,
    turn: int = 1,
):
    return next(
        unit
        for unit in plan
        if unit["system_config_id"] == config
        and unit["turn_index"] == turn
        and (rq is None or unit["rq"] == rq)
        and (int(unit["request_id"][0], 16) >= 8) is provider
    )


class _PreparedCaptured(RuntimeError):
    pass


def _publish_fixed_prepared(plan, contract, unit):
    authority = runner._fixed_offline_authority()
    captured = []
    with store._open_store(contract) as (opened, lock):
        state = store._load_unit_state_locked(
            store._execution_unit_id(unit),
            run_contract=opened,
            lock=lock,
        )
        checkpoint, _turn_one_commit = store._selected_dependency_commit(
            plan,
            unit,
            run_contract=opened,
            lock=lock,
        )
        dependencies = authority.dependencies_for(unit, state)

        def capture(journal):
            captured.append(journal)
            raise _PreparedCaptured

        with pytest.raises(_PreparedCaptured):
            runner.orchestrate_offline_unit(
                plan,
                unit,
                journal_persistence_callback=capture,
                checkpoint_evidence=checkpoint,
                **dependencies,
            )
        assert len(captured) == 1
        assert type(captured[0]) is inflight.InflightJournal
        assert captured[0].state == "prepared"
        store._publish_journal_locked(
            captured[0],
            run_contract=opened,
            lock=lock,
        )
    return captured[0]


def _complete_turn_one_for(plan, turn_two):
    turn_one = next(
        unit
        for unit in plan
        if unit["rq"] == "RQ3"
        and unit["system_config_id"] == "context_aware"
        and unit["case_id"] == turn_two["case_id"]
        and unit["turn_index"] == 1
    )
    outcome = runner.orchestrate_durable_offline_unit(plan, turn_one)
    assert outcome.action == "completed"
    assert outcome.private_commit_sha256 is not None
    return turn_one


@pytest.mark.parametrize(
    "provider,config,rq,turn,vector,reopen_action,reopen_block",
    (
        (True, "v2", None, 1, "PP", "permanently_non_executable", "provider_returned_without_commit"),
        (False, "v2", None, 1, "T", "completed", None),
        (True, "context_aware", "RQ3", 1, "PP", "permanently_non_executable", "provider_returned_without_commit"),
        (False, "context_aware", "RQ3", 1, "T", "completed", None),
        (True, "context_aware", "RQ3", 2, "PP", "permanently_non_executable", "provider_returned_without_commit"),
        (False, "context_aware", "RQ3", 2, "T", "completed", None),
    ),
)
def test_private_commit_fault_full_provider_local_and_rq3_contract(
    state_root,
    frozen_plan_and_contract,
    provider,
    config,
    rq,
    turn,
    vector,
    reopen_action,
    reopen_block,
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(
        plan,
        provider=provider,
        config=config,
        rq=rq,
        turn=turn,
    )
    if turn == 2:
        _complete_turn_one_for(plan, unit)
    _publish_fixed_prepared(plan, contract, unit)
    point = "before_private_commit_publication_error"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with pytest.raises(store.StoreError) as caught:
            runner.orchestrate_durable_offline_unit(plan, unit)
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, vector, caught.value)
    assert len(_temps(state_root)) == 1
    reopened = runner.orchestrate_durable_offline_unit(plan, unit)
    assert reopened.action == reopen_action
    assert reopened.block_category == reopen_block
    assert reopened.provider_call_count == 0
    assert _temps(state_root) == []
    if turn == 1 and config == "context_aware" and provider:
        paired_turn_two = next(
            candidate
            for candidate in plan
            if candidate["case_id"] == unit["case_id"]
            and candidate["system_config_id"] == "context_aware"
            and candidate["turn_index"] == 2
        )
        blocked = runner.orchestrate_durable_offline_unit(plan, paired_turn_two)
        assert blocked.action == "permanently_non_executable"
        assert blocked.block_category == "dependency_permanent"
        assert blocked.provider_call_count == 0


def test_post_provider_returned_callback_fault_is_nonrecallable(
    state_root, frozen_plan_and_contract
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    _publish_fixed_prepared(plan, contract, unit)
    point = "before_post_call_archive_publication_error"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with pytest.raises(store.StoreError) as caught:
            runner.orchestrate_durable_offline_unit(plan, unit)
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, "PC", caught.value)
    assert len(_temps(state_root)) == 1
    reopened = runner.orchestrate_durable_offline_unit(plan, unit)
    assert reopened.action == "permanently_non_executable"
    assert reopened.block_category == "call_started"
    assert reopened.provider_call_count == 0
    assert _temps(state_root) == []


@pytest.mark.parametrize(
    "branch,state,category",
    (
        ("POST_RETRYABLE", "retryable_failed", "http_429"),
        ("POST_TERMINAL", "terminal_failed", "provider_rejected"),
        ("POST_UNCERTAIN", "uncertain", "timeout"),
    ),
)
def test_closed_post_call_candidate_authority_and_callback_propagation(
    state_root,
    frozen_plan_and_contract,
    branch,
    state,
    category,
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    _publish_fixed_prepared(plan, contract, unit)
    point = "before_post_call_archive_publication_error"
    callback_attempts = 0
    callback_completions = 0
    fake_count = 0
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with store._open_store(contract) as (opened, lock):
            durable = store._load_unit_state_locked(
                store._execution_unit_id(unit),
                run_contract=opened,
                lock=lock,
            )
            assert durable.tip is not None
            prepared = durable.tip.journal
            assert prepared.state == "prepared"
            authority = runner._fixed_offline_authority()
            clock = authority.clock_for(unit, durable)
            provider_request_id = inflight.derive_provider_request_id(
                prepared.identity
            )

            def persistence_callback(journal):
                nonlocal callback_attempts, callback_completions
                callback_attempts += 1
                store._publish_journal_locked(
                    journal,
                    run_contract=opened,
                    lock=lock,
                )
                callback_completions += 1

            call_started = inflight.transition(
                prepared,
                "call_started",
                clock(),
                provider_request_id=provider_request_id,
            )
            persistence_callback(call_started)
            fake = authority.fake_raw_client_type(unit)
            boundary = orchestration._RawClientBoundary(
                fake,
                call_started,
                clock,
                provider_request_id,
            )
            tracker = orchestration.ProviderCallTracker()
            fake._provider_request_id = provider_request_id
            normalized = orchestration.FixedGenerationProxy().invoke(
                boundary,
                tracker,
                [{"role": "user", "content": "stage-b2-synthetic-message"}],
                provider_request_id=provider_request_id,
            )
            fake_count = fake.call_count
            if state == "retryable_failed":
                candidate = inflight.transition(
                    call_started,
                    state,
                    clock(),
                    sanitized_outcome_category=category,
                )
            elif state == "terminal_failed":
                candidate = inflight.transition(
                    call_started,
                    state,
                    clock(),
                    sanitized_outcome_category=category,
                )
            else:
                candidate = inflight.transition(
                    call_started,
                    state,
                    clock(),
                    sanitized_outcome_category=category,
                )
            with pytest.raises(store.StoreError) as caught:
                try:
                    persistence_callback(candidate)
                except BaseException:
                    raise
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, "PC", caught.value)
        assert tracker.state == "validated_success"
        assert normalized.provider_request_id == provider_request_id
        assert boundary.call_count == 1
    assert callback_attempts == 2
    assert callback_completions == 1
    assert fake_count == 1
    reopened = runner.orchestrate_durable_offline_unit(plan, unit)
    assert reopened.action == "permanently_non_executable"
    assert reopened.block_category == "call_started"
    assert reopened.provider_call_count == 0


@pytest.mark.parametrize(
    "config",
    (
        "qa_only_reconstructed_baseline",
        "v2",
        "single_turn",
        "context_aware",
    ),
)
@pytest.mark.parametrize("provider", (False, True))
def test_first_success_idempotence_and_all_system_coverage(
    state_root, frozen_plan_and_contract, config, provider
):
    plan = frozen_plan_and_contract.plan
    rq = "RQ3" if config in {"single_turn", "context_aware"} else None
    unit = _selected_unit(plan, provider=provider, config=config, rq=rq, turn=1)
    first = runner.orchestrate_durable_offline_unit(plan, unit)
    assert first.action == "completed"
    assert first.provider_call_count == (1 if provider else 0)
    assert first.private_commit_sha256 is not None
    second = runner.orchestrate_durable_offline_unit(plan, unit)
    assert second.action == "completed"
    assert second.provider_call_count == 0
    assert second.private_commit_sha256 == first.private_commit_sha256
    progress = runner.durable_progress(plan)
    assert progress.total_successful_units == 1
    assert progress.remaining_units == 189
    assert sum(progress.successful_by_rq.values()) == 1
    assert sum(progress.successful_by_system.values()) == 1
    assert progress.successful_by_system[config] == 1


_WINDOWS_WORKER = r"""
import os
import socket
import sys
import time
from pathlib import Path

def forbidden(*args, **kwargs):
    raise RuntimeError("NETWORK_FORBIDDEN")

socket.socket = forbidden
socket.create_connection = forbidden
sys.path.insert(0, str(Path.cwd() / "scripts"))
import formal_evaluation_store as store
import run_formal_evaluation as runner

root = Path(sys.argv[1])
mode = sys.argv[2]
store._PRIVATE_STATE_ROOT = root

if mode == "lock_hold":
    with store._RunWideLock(root):
        sys.stdout.write("READY\n")
        sys.stdout.flush()
        time.sleep(30)
    raise SystemExit(0)

if mode == "lock_attempt":
    try:
        with store._RunWideLock(root):
            pass
    except store.StoreError as exc:
        codes = {
            "STORE_LOCK_BUSY": 40,
            "STORE_LOCK_FILE_INVALID": 41,
        }
        raise SystemExit(codes.get(exc.category, 42))
    raise SystemExit(0)

plan = runner.build_plan()
if mode == "contract":
    runner.durable_progress(plan)
    raise SystemExit(0)

runner.durable_progress(plan)
point = sys.argv[3]
provider = sys.argv[4] == "provider"
unit = next(
    candidate
    for candidate in plan
    if candidate["system_config_id"] == "v2"
    and candidate["turn_index"] == 1
    and ((int(candidate["request_id"][0], 16) >= 8) is provider)
)
with store._install_stage_b2_test_fault_controller_for_tests(root, point):
    runner.orchestrate_durable_offline_unit(plan, unit)
raise SystemExit(0)
"""


def _worker_command(root: Path, mode: str, *arguments: str):
    return [
        sys.executable,
        "-c",
        _WINDOWS_WORKER,
        str(root),
        mode,
        *arguments,
    ]


def _worker_environment():
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONPYCACHEPREFIX"] = str(
        Path(tempfile.gettempdir()) / "stage-b2-child-pycache"
    )
    return environment


def _run_worker(root: Path, mode: str, *arguments: str, timeout: float = 20):
    completed = subprocess.run(
        _worker_command(root, mode, *arguments),
        cwd=Path(__file__).resolve().parents[1],
        env=_worker_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, len(completed.stdout), len(completed.stderr)


def _require_worker(
    result: tuple[int, int, int],
    expected_code: int,
    *,
    allow_stdout: bool = False,
) -> None:
    code, stdout_bytes, stderr_bytes = result
    if (
        code != expected_code
        or stderr_bytes != 0
        or (stdout_bytes != 0 and not allow_stdout)
    ):
        pytest.fail(
            "sanitized child failure: "
            f"code={code}, stdout_bytes={stdout_bytes}, "
            f"stderr_bytes={stderr_bytes}",
            pytrace=False,
        )


def _safe_durable_call(plan, unit):
    try:
        return runner.orchestrate_durable_offline_unit(plan, unit)
    except BaseException as exc:
        category = getattr(exc, "category", type(exc).__name__)
        pytest.fail(
            f"sanitized durable-call failure: {category}",
            pytrace=False,
        )


def _marker_path(root: Path, pid: int, point: str) -> Path:
    return root.parent / ".stage_b2_fault_markers" / f"marker-{pid}-{point}.json"


def _marker_names(root: Path, point: str) -> set[str]:
    marker_root = root.parent / ".stage_b2_fault_markers"
    if not marker_root.is_dir():
        return set()
    return {item.name for item in marker_root.glob(f"marker-*-{point}.json")}


def _wait_for_marker(
    root: Path,
    point: str,
    known_names: set[str],
    process: subprocess.Popen,
) -> Path:
    marker_root = root.parent / ".stage_b2_fault_markers"
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        new_names = _marker_names(root, point) - known_names
        if len(new_names) == 1:
            return marker_root / next(iter(new_names))
        if process.poll() is not None:
            break
        time.sleep(0.05)
    new_names = _marker_names(root, point) - known_names
    if len(new_names) == 1:
        return marker_root / next(iter(new_names))
    pytest.fail(
        "expected marker was not observed; "
        f"child_code={process.poll()}, new_marker_count={len(new_names)}",
        pytrace=False,
    )


def _read_marker(path: Path, point: str, pid: int, provider_calls: int):
    raw = path.read_bytes()
    value = json.loads(raw)
    assert raw == store._canonical_bytes(value) + b"\n"
    assert set(value) == {
        "schema_version",
        "fault_point",
        "pid",
        "execution_unit_id",
        "attempt_number",
        "archive_sha256",
        "private_commit_sha256",
        "provider_call_count",
    }
    assert value["schema_version"] == 1
    assert value["fault_point"] == point
    assert value["pid"] == pid
    assert value["provider_call_count"] == provider_calls
    assert store._SHA256_RE.fullmatch(value["execution_unit_id"])
    assert store._SHA256_RE.fullmatch(value["archive_sha256"])
    assert type(value["attempt_number"]) is int
    assert 1 <= value["attempt_number"] <= 3
    return value


def _remove_own_marker(path: Path) -> None:
    resolved = path.resolve(strict=True)
    expected_parent = path.parent.resolve(strict=True)
    assert resolved.parent == expected_parent
    assert resolved.name == path.name
    resolved.unlink()
    try:
        expected_parent.rmdir()
    except OSError:
        pass


def _run_crash_child(
    root: Path,
    point: str,
    *,
    provider: bool,
    exit_code: int,
    provider_calls: int,
):
    known_markers = _marker_names(root, point)
    process = subprocess.Popen(
        _worker_command(
            root,
            "fault",
            point,
            "provider" if provider else "local",
        ),
        cwd=Path(__file__).resolve().parents[1],
        env=_worker_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    marker = _wait_for_marker(root, point, known_markers, process)
    stdout, stderr = process.communicate(timeout=10)
    if process.returncode != exit_code or stdout or stderr:
        pytest.fail(
            "sanitized crash-child failure: "
            f"code={process.returncode}, stdout_bytes={len(stdout)}, "
            f"stderr_bytes={len(stderr)}",
            pytrace=False,
        )
    marker_pid = int(marker.name.split("-")[1])
    value = _read_marker(marker, point, marker_pid, provider_calls)
    return marker, value


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows lock contract")
def test_windows_subprocess_competing_lock_and_normal_release(state_root):
    holder = subprocess.Popen(
        _worker_command(state_root, "lock_hold"),
        cwd=Path(__file__).resolve().parents[1],
        env=_worker_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert holder.stdout is not None
        ready = holder.stdout.readline()
        if ready not in {b"READY\n", b"READY\r\n"}:
            pytest.fail(
                "lock holder failed before readiness: "
                f"code={holder.poll()}",
                pytrace=False,
            )
        _require_worker(_run_worker(state_root, "lock_attempt", timeout=10), 40)
    finally:
        if holder.poll() is None:
            holder.terminate()
        _remaining, error = holder.communicate(timeout=10)
    if error:
        pytest.fail(
            f"lock holder emitted stderr_bytes={len(error)}", pytrace=False
        )
    _require_worker(_run_worker(state_root, "lock_attempt"), 0)


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows lock contract")
def test_windows_subprocess_forced_termination_preserves_valid_lock_file(
    state_root,
):
    holder = subprocess.Popen(
        _worker_command(state_root, "lock_hold"),
        cwd=Path(__file__).resolve().parents[1],
        env=_worker_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert holder.stdout is not None
    if holder.stdout.readline() not in {b"READY\n", b"READY\r\n"}:
        holder.terminate()
        _out, error = holder.communicate(timeout=10)
        pytest.fail(
            "lock holder failed before forced termination: "
            f"stderr_bytes={len(error)}",
            pytrace=False,
        )
    holder.terminate()
    _out, error = holder.communicate(timeout=10)
    if error:
        pytest.fail(
            f"terminated holder emitted stderr_bytes={len(error)}", pytrace=False
        )
    assert (state_root / "run.lock").read_bytes() == b"\x00"
    _require_worker(_run_worker(state_root, "lock_attempt"), 0)


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows lock contract")
def test_windows_subprocess_stale_valid_lock_file(state_root):
    lock_path = state_root / "run.lock"
    lock_path.write_bytes(b"\x00")
    _require_worker(_run_worker(state_root, "lock_attempt"), 0)
    assert lock_path.read_bytes() == b"\x00"


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows lock contract")
@pytest.mark.parametrize("raw", (b"", b"\x00\x00", b"\x01"))
def test_windows_subprocess_corrupt_lock_files_fail_without_repair(
    state_root, raw
):
    lock_path = state_root / "run.lock"
    lock_path.write_bytes(raw)
    _require_worker(_run_worker(state_root, "lock_attempt"), 41)
    assert lock_path.read_bytes() == raw


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows durability contract")
@pytest.mark.parametrize(
    "point,provider,exit_code,provider_calls,reopen_action,reopen_block,commit_required",
    (
        (
            "after_call_started_published_exit",
            True,
            90,
            0,
            "permanently_non_executable",
            "call_started",
            False,
        ),
        (
            "after_fake_client_returned_exit",
            True,
            91,
            1,
            "permanently_non_executable",
            "call_started",
            False,
        ),
        (
            "after_private_commit_published_exit",
            True,
            92,
            1,
            "completed",
            None,
            True,
        ),
        (
            "after_private_commit_published_exit",
            False,
            92,
            0,
            "completed",
            None,
            True,
        ),
        (
            "after_committed_archive_published_exit",
            True,
            93,
            1,
            "completed",
            None,
            True,
        ),
    ),
)
def test_windows_subprocess_crash_boundaries_and_reopen(
    state_root,
    frozen_plan_and_contract,
    point,
    provider,
    exit_code,
    provider_calls,
    reopen_action,
    reopen_block,
    commit_required,
):
    marker, value = _run_crash_child(
        state_root,
        point,
        provider=provider,
        exit_code=exit_code,
        provider_calls=provider_calls,
    )
    if commit_required:
        assert store._SHA256_RE.fullmatch(value["private_commit_sha256"])
    else:
        assert value["private_commit_sha256"] is None
    plan = frozen_plan_and_contract.plan
    unit = _selected_unit(plan, provider=provider)
    reopened = _safe_durable_call(plan, unit)
    assert reopened.action == reopen_action
    assert reopened.block_category == reopen_block
    assert reopened.provider_call_count == 0
    _remove_own_marker(marker)


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows durability contract")
def test_windows_subprocess_exactly_one_marked_fake_call_across_race(
    state_root, frozen_plan_and_contract
):
    point = "after_fake_client_returned_mark"
    known_markers = _marker_names(state_root, point)
    processes = [
        subprocess.Popen(
            _worker_command(state_root, "fault", point, "provider"),
            cwd=Path(__file__).resolve().parents[1],
            env=_worker_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        results.append((process.returncode, len(stdout), len(stderr)))
    for result in results:
        _require_worker(result, 0)
    marker_root = state_root.parent / ".stage_b2_fault_markers"
    markers = [
        marker_root / name
        for name in (_marker_names(state_root, point) - known_markers)
    ]
    assert len(markers) == 1
    marker = markers[0]
    marker_pid = int(marker.name.split("-")[1])
    value = _read_marker(marker, point, marker_pid, 1)
    assert value["private_commit_sha256"] is None
    plan = frozen_plan_and_contract.plan
    unit = _selected_unit(plan, provider=True)
    reopened = _safe_durable_call(plan, unit)
    assert reopened.action == "completed"
    assert reopened.provider_call_count == 0
    _remove_own_marker(marker)


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows durability contract")
def test_windows_subprocess_first_contract_race_is_create_only(
    state_root, frozen_plan_and_contract
):
    processes = [
        subprocess.Popen(
            _worker_command(state_root, "contract"),
            cwd=Path(__file__).resolve().parents[1],
            env=_worker_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(2)
    ]
    results = []
    for process in processes:
        stdout, stderr = process.communicate(timeout=20)
        results.append((process.returncode, len(stdout), len(stderr)))
    for result in results:
        _require_worker(result, 0)
    contract_path = state_root / "run_contract.json"
    expected = frozen_plan_and_contract.contract
    assert contract_path.read_bytes() == store._canonical_bytes(expected) + b"\n"
    assert list((state_root / "attempts").iterdir()) == []
    assert list((state_root / "journals").iterdir()) == []
    assert list((state_root / "commits").iterdir()) == []


def test_store_error_closed_categories_and_sanitized_shape():
    assert len(store._STORE_CATEGORIES) == 22
    for category in store._STORE_CATEGORIES:
        error = store.StoreError(category)
        assert error.category == category
        assert error.args == (category,)
        assert vars(error) == {"category": category}
    for invalid in ("UNKNOWN", "", None, 1, True):
        with pytest.raises(ValueError):
            store.StoreError(invalid)


def _progress(
    run_state="in_progress",
    successful=0,
    remaining=190,
    next_order=1,
    initial=190,
    continuable=0,
    retry=0,
    dependency=0,
    permanent=0,
    rq=None,
    systems=None,
):
    return store.DurableProgress(
        1,
        run_state,
        successful,
        {"RQ1": 0, "RQ2": 0, "RQ3": 0} if rq is None else rq,
        {
            "qa_only_reconstructed_baseline": 0,
            "v2": 0,
            "single_turn": 0,
            "context_aware": 0,
        }
        if systems is None
        else systems,
        remaining,
        next_order,
        initial,
        continuable,
        retry,
        dependency,
        permanent,
    )


def test_durable_progress_exact_signature_detachment_and_all_run_states():
    assert list(inspect.signature(store.DurableProgress).parameters) == [
        "schema_version",
        "run_state",
        "total_successful_units",
        "successful_by_rq",
        "successful_by_system",
        "remaining_units",
        "next_eligible_execution_order",
        "initial_executable_units",
        "same_attempt_continuable_units",
        "retry_constructible_units",
        "dependency_blocked_units",
        "permanently_non_executable_units",
    ]
    source_rq = {"RQ1": 0, "RQ2": 0, "RQ3": 0}
    source_systems = {
        "qa_only_reconstructed_baseline": 0,
        "v2": 0,
        "single_turn": 0,
        "context_aware": 0,
    }
    active = _progress(rq=source_rq, systems=source_systems)
    source_rq["RQ1"] = 1
    source_systems["v2"] = 1
    assert dict(active.successful_by_rq) == {"RQ1": 0, "RQ2": 0, "RQ3": 0}
    assert dict(active.successful_by_system) == {
        "qa_only_reconstructed_baseline": 0,
        "v2": 0,
        "single_turn": 0,
        "context_aware": 0,
    }
    with pytest.raises(TypeError):
        active.successful_by_rq["RQ1"] = 2
    temporarily_blocked = _progress(
        run_state="temporarily_blocked",
        next_order=None,
        initial=0,
        dependency=190,
    )
    permanently_blocked = _progress(
        run_state="permanently_blocked",
        next_order=None,
        initial=0,
        permanent=190,
    )
    complete = _progress(
        run_state="complete",
        successful=190,
        remaining=0,
        next_order=None,
        initial=0,
        rq={"RQ1": 102, "RQ2": 40, "RQ3": 48},
        systems={
            "qa_only_reconstructed_baseline": 71,
            "v2": 71,
            "single_turn": 24,
            "context_aware": 24,
        },
    )
    assert active.run_state == "in_progress"
    assert temporarily_blocked.run_state == "temporarily_blocked"
    assert permanently_blocked.run_state == "permanently_blocked"
    assert complete.run_state == "complete"


@pytest.mark.parametrize(
    "changes",
    (
        {"schema_version": True},
        {"schema_version": 2},
        {"run_state": "unknown"},
        {"successful": -1},
        {"successful": 191},
        {"remaining": 189},
        {"next_order": None},
        {"next_order": True},
        {"initial": 189},
        {"continuable": 1},
        {"retry": 1},
        {"dependency": 1},
        {"permanent": 1},
        {"rq": {"RQ1": 0, "RQ2": 0}},
        {"rq": {"RQ1": 103, "RQ2": 0, "RQ3": 0}},
        {
            "systems": {
                "qa_only_reconstructed_baseline": 72,
                "v2": 0,
                "single_turn": 0,
                "context_aware": 0,
            }
        },
    ),
)
def test_durable_progress_rejects_type_bound_and_partition_mutations(changes):
    arguments = {
        "run_state": "in_progress",
        "successful": 0,
        "remaining": 190,
        "next_order": 1,
        "initial": 190,
        "continuable": 0,
        "retry": 0,
        "dependency": 0,
        "permanent": 0,
        "rq": None,
        "systems": None,
    }
    schema_version = changes.pop("schema_version", 1)
    arguments.update(changes)
    with pytest.raises(ValueError):
        store.DurableProgress(
            schema_version,
            arguments["run_state"],
            arguments["successful"],
            {"RQ1": 0, "RQ2": 0, "RQ3": 0}
            if arguments["rq"] is None
            else arguments["rq"],
            {
                "qa_only_reconstructed_baseline": 0,
                "v2": 0,
                "single_turn": 0,
                "context_aware": 0,
            }
            if arguments["systems"] is None
            else arguments["systems"],
            arguments["remaining"],
            arguments["next_order"],
            arguments["initial"],
            arguments["continuable"],
            arguments["retry"],
            arguments["dependency"],
            arguments["permanent"],
        )


def test_durable_execution_outcome_exact_signature_and_mutation_rejection(
    state_root, frozen_plan_and_contract
):
    assert list(inspect.signature(store.DurableExecutionOutcome).parameters) == [
        "schema_version",
        "action",
        "execution_unit_id",
        "execution_order",
        "attempt_number",
        "journal_state",
        "private_commit_sha256",
        "block_category",
        "provider_call_count",
        "orchestration_outcome",
        "progress",
    ]
    plan = frozen_plan_and_contract.plan
    unit = _selected_unit(plan, provider=False)
    valid = _safe_durable_call(plan, unit)
    assert type(valid) is store.DurableExecutionOutcome
    for changes in (
        {"schema_version": True},
        {"action": "unknown"},
        {"execution_unit_id": "0"},
        {"execution_order": True},
        {"attempt_number": 4},
        {"journal_state": "unknown"},
        {"private_commit_sha256": None},
        {"block_category": "call_started"},
        {"provider_call_count": 1},
        {"orchestration_outcome": object()},
    ):
        with pytest.raises(ValueError):
            dataclasses.replace(valid, **changes)


def test_closed_json_canonical_unicode_duplicate_and_nonfinite_contract():
    value = {"unicode": "安全", "integer": 1, "flag": False}
    raw = store._canonical_bytes(value) + b"\n"
    assert store._load_json_bytes(raw, len(raw)) == value
    assert b"\\u" not in raw
    malformed = (
        b'{"a":1,"a":1}\n',
        b'{"a":NaN}\n',
        b'{"a":Infinity}\n',
        b'[]\n',
    )
    for candidate in malformed:
        with pytest.raises(store.StoreError) as caught:
            store._load_json_bytes(candidate, len(candidate))
        assert caught.value.category == "STORE_JSON_INVALID"
    for candidate in (
        b'{ "a":1}\n',
        b'{"b":2,"a":1}\n',
        b'{"a":1}',
    ):
        with pytest.raises(store.StoreError) as caught:
            store._load_json_bytes(candidate, len(candidate))
        assert caught.value.category == "STORE_NONCANONICAL_JSON"


@pytest.mark.parametrize(
    "maximum",
    (
        store._RUN_CONTRACT_LIMIT,
        store._JOURNAL_LIMIT,
        store._ARCHIVE_LIMIT,
        store._COMMIT_LIMIT,
    ),
)
def test_closed_json_exact_encoded_byte_limit(maximum):
    overhead = len(b'{"x":""}\n')
    raw = b'{"x":"' + b"a" * (maximum - overhead) + b'"}\n'
    assert len(raw) == maximum
    if maximum - overhead <= store._JSON_MAX_STRING_BYTES:
        assert store._load_json_bytes(raw, maximum)["x"].startswith("a")
    else:
        with pytest.raises(store.StoreError) as string_limit:
            store._load_json_bytes(raw, maximum)
        assert string_limit.value.category == "STORE_JSON_LIMIT_EXCEEDED"
    with pytest.raises(store.StoreError) as one_over:
        store._load_json_bytes(raw, maximum - 1)
    assert one_over.value.category == "STORE_JSON_LIMIT_EXCEEDED"


def test_closed_json_recursive_cardinality_and_string_bounds():
    accepted_mapping = {f"k{index:03d}": index for index in range(128)}
    accepted_array = {"items": list(range(256))}
    accepted_string = {"text": "a" * 262_144}
    for value in (accepted_mapping, accepted_array, accepted_string):
        raw = store._canonical_bytes(value) + b"\n"
        assert store._load_json_bytes(raw, len(raw)) == value
    rejected = (
        {f"k{index:03d}": index for index in range(129)},
        {"items": list(range(257))},
        {"text": "a" * 262_145},
    )
    for value in rejected:
        raw = store._canonical_bytes(value) + b"\n"
        with pytest.raises(store.StoreError) as caught:
            store._load_json_bytes(raw, len(raw))
        assert caught.value.category == "STORE_JSON_LIMIT_EXCEEDED"


def test_domain_separated_hashes_and_self_field_exclusion():
    value = {"schema_version": 1, "member": "synthetic"}
    first = store._domain_sha("domain-a", "record", value)
    second = store._domain_sha("domain-b", "record", value)
    third = store._domain_sha("domain-a", "archive", value)
    assert len({first, second, third}) == 3
    archive = dict(value, archive_sha256="0" * 64)
    expected = store._archive_hash(archive)
    archive["archive_sha256"] = "1" * 64
    assert store._archive_hash(archive) == expected
    record = dict(value, record_sha256="0" * 64)
    expected_record = store._record_hash(record)
    record["record_sha256"] = "1" * 64
    assert store._record_hash(record) == expected_record


def test_run_contract_create_reopen_without_rewrite_and_exact_authority(
    state_root, frozen_plan_and_contract
):
    plan = frozen_plan_and_contract.plan
    expected = frozen_plan_and_contract.contract
    first = runner.durable_progress(plan)
    path = state_root / "run_contract.json"
    before = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns
    second = runner.durable_progress(plan)
    assert path.read_bytes() == before == store._canonical_bytes(expected) + b"\n"
    assert path.stat().st_mtime_ns == before_mtime
    assert first == second
    assert expected["schema_version"] == 1
    assert expected["stage_id"] == "B2"
    assert expected["plan_authority"]["execution_unit_count"] == 190
    assert expected["plan_authority"]["rq_counts"] == {
        "RQ1": 102,
        "RQ2": 40,
        "RQ3": 48,
    }
    assert expected["plan_authority"]["system_counts"] == {
        "context_aware": 24,
        "qa_only_reconstructed_baseline": 71,
        "single_turn": 24,
        "v2": 71,
    }
    assert len(expected["frozen_input_sha256"]) == 6
    assert len(expected["formal_system_authority"]) == 4
    assert len(expected["runtime_resource_authority"]["resources"]) == 4
    assert len(expected["schema_authority"]) == 9


@pytest.mark.parametrize(
    "mutation",
    (
        "stage",
        "plan",
        "frozen",
        "system",
        "generation",
        "runtime",
        "schema",
        "extra_top",
        "missing_top",
    ),
)
def test_self_consistent_foreign_run_contract_fails_closed(
    state_root, frozen_plan_and_contract, mutation
):
    plan = frozen_plan_and_contract.plan
    runner.durable_progress(plan)
    value = copy.deepcopy(frozen_plan_and_contract.contract)
    value.pop("run_contract_sha256")
    if mutation == "stage":
        value["stage_id"] = "B3"
    elif mutation == "plan":
        value["plan_authority"]["base_seed"] += 1
    elif mutation == "frozen":
        key = next(iter(value["frozen_input_sha256"]))
        value["frozen_input_sha256"][key] = "0" * 64
    elif mutation == "system":
        key = next(iter(value["formal_system_authority"]))
        value["formal_system_authority"][key]["top_k"] += 1
    elif mutation == "generation":
        value["provider_generation_authority"]["generation"]["contract_id"] = "foreign"
    elif mutation == "runtime":
        value["runtime_resource_authority"]["runtime_identity_sha256"] = "0" * 64
    elif mutation == "schema":
        value["schema_authority"]["run_contract_schema_version"] = 2
    elif mutation == "extra_top":
        value["unexpected"] = None
    else:
        value.pop("schema_authority")
    value["run_contract_sha256"] = store._domain_sha(
        "formal-evaluation-run-contract-v1",
        "contract",
        value,
    )
    path = state_root / "run_contract.json"
    path.write_bytes(store._canonical_bytes(value) + b"\n")
    with pytest.raises(store.StoreError) as caught:
        runner.durable_progress(plan)
    assert caught.value.category in {
        "STORE_SCHEMA_INVALID",
        "STORE_RUN_CONTRACT_MISMATCH",
    }


@pytest.mark.parametrize(
    "raw_kind,category",
    (
        ("truncated", "STORE_JSON_INVALID"),
        ("noncanonical", "STORE_NONCANONICAL_JSON"),
        ("duplicate", "STORE_JSON_INVALID"),
        ("nonobject", "STORE_JSON_INVALID"),
    ),
)
def test_malformed_run_contract_bytes_fail_closed(
    state_root, frozen_plan_and_contract, raw_kind, category
):
    plan = frozen_plan_and_contract.plan
    runner.durable_progress(plan)
    canonical = store._canonical_bytes(frozen_plan_and_contract.contract) + b"\n"
    if raw_kind == "truncated":
        raw = canonical[: len(canonical) // 2]
    elif raw_kind == "noncanonical":
        raw = b" " + canonical
    elif raw_kind == "duplicate":
        raw = b'{"schema_version":1,"schema_version":1}\n'
    else:
        raw = b"[]\n"
    (state_root / "run_contract.json").write_bytes(raw)
    with pytest.raises(store.StoreError) as caught:
        runner.durable_progress(plan)
    assert caught.value.category == category


def test_nonlock_state_without_contract_fails_before_state_loading(
    state_root, frozen_plan_and_contract
):
    (state_root / "commits" / "synthetic-nonlock-state").write_bytes(b"x")
    with pytest.raises(store.StoreError) as caught:
        runner.durable_progress(frozen_plan_and_contract.plan)
    assert caught.value.category == "STORE_STATE_WITHOUT_CONTRACT"
    assert not (state_root / "run_contract.json").exists()


@pytest.mark.parametrize(
    "location,name",
    (
        ("root", "unknown"),
        ("journals", "not-a-journal.json"),
        ("commits", "0-not-a-commit.json"),
        ("attempts", "not-an-execution-unit"),
    ),
)
def test_unknown_store_members_and_noncanonical_names_fail_closed(
    state_root, frozen_plan_and_contract, location, name
):
    plan = frozen_plan_and_contract.plan
    runner.durable_progress(plan)
    base = state_root if location == "root" else state_root / location
    path = base / name
    if location == "attempts":
        path.mkdir()
    else:
        path.write_bytes(b"synthetic")
    with pytest.raises(store.StoreError) as caught:
        runner.durable_progress(plan)
    assert caught.value.category == "STORE_PATH_INVALID"


def test_non_temporary_and_wrong_root_controller_installation_rejected(
    monkeypatch, state_root
):
    point = "before_atomic_temp_create_error"
    with pytest.raises(store.StoreError) as wrong:
        with store._install_stage_b2_test_fault_controller_for_tests(
            state_root.parent, point
        ):
            pass
    assert wrong.value.category == "STORE_TEST_FAULT_INVALID"
    monkeypatch.setattr(store, "_PRIVATE_STATE_ROOT", Path.cwd())
    with pytest.raises(store.StoreError) as repository:
        with store._install_stage_b2_test_fault_controller_for_tests(
            Path.cwd(), point
        ):
            pass
    assert repository.value.category == "STORE_TEST_FAULT_INVALID"


def test_fixed_offline_authority_rejects_foreign_components_before_store_access():
    authority = runner._fixed_offline_authority()
    runner._validate_fixed_offline_authority_for_tests(authority)
    mutations = (
        {"mode": "foreign"},
        {"transport_implementation_sha256": "0" * 64},
        {"runtime_identity_sha256": "0" * 64},
        {"fake_raw_client_type": object},
        {"executor_registry_type": object},
        {"clock_type": object},
        {"snapshot_validator": lambda _value: {}},
        {"test_fault_controller_type": object},
    )
    for changes in mutations:
        foreign = dataclasses.replace(authority, **changes)
        with pytest.raises(store.StoreError) as caught:
            runner._validate_fixed_offline_authority_for_tests(foreign)
        assert caught.value.category == "STORE_FIXED_AUTHORITY_MISMATCH"


def test_transport_semantic_source_hash_and_eol_rejections():
    raw = (Path(__file__).parent / "formal_evaluation_transport.py").read_bytes()
    canonical = runner._lf_canonical_source_bytes_for_tests(raw)
    assert hashlib.sha256(canonical).hexdigest() == (
        "464890905866d517bb036569458e6dd69578a2dbacd0eab272c4f0f6ec6fb927"
    )
    crlf = canonical.replace(b"\n", b"\r\n")
    assert runner._lf_canonical_source_bytes_for_tests(crlf) == canonical
    assert runner._lf_canonical_source_bytes_for_tests(b"no-newline") == b"no-newline"
    invalid = (
        b"\xef\xbb\xbf" + canonical,
        b"a\rb",
        b"a\r",
        b"a\r\nb\n",
        b"a\nb\r\n",
    )
    for candidate in invalid:
        with pytest.raises(store.StoreError) as caught:
            runner._lf_canonical_source_bytes_for_tests(candidate)
        assert caught.value.category == "STORE_FIXED_AUTHORITY_MISMATCH"
    changed = bytearray(canonical)
    changed[0] ^= 1
    assert hashlib.sha256(bytes(changed)).hexdigest() != hashlib.sha256(
        canonical
    ).hexdigest()


def _synthetic_snapshot():
    response = "STAGE_B2_SYNTHETIC_LOCAL " + "a" * 24
    return {
        "schema_version": 1,
        "completed_turn_index": 1,
        "conversation_state": {
            "current_topic": "none",
            "query_type": "normal",
            "risk_type": "none",
            "requires_backend_api": False,
            "last_safe_answer_type": "none",
            "last_user_query": "synthetic-user",
            "last_assistant_answer": response,
            "last_retrieval_query": "",
            "last_contextual_query": "",
            "last_successful_contextual_query": "",
            "state_confidence": 0.0,
            "state_turn_count": 0,
            "updated_at_turn": 1,
            "should_reset": False,
        },
        "previous_user_text": "synthetic-user",
        "previous_assistant_text": response,
    }


def test_synthetic_snapshot_exact_closed_shape_and_field_mutations():
    original = _synthetic_snapshot()
    validated = runner._validate_fixed_synthetic_snapshot_v1(original)
    assert validated == original
    assert validated is not original
    assert validated["conversation_state"] is not original["conversation_state"]
    assert len(original) == 5
    assert len(original["conversation_state"]) == 14
    mutations = []
    for key in original:
        missing = copy.deepcopy(original)
        missing.pop(key)
        mutations.append(missing)
    for key in original["conversation_state"]:
        missing = copy.deepcopy(original)
        missing["conversation_state"].pop(key)
        mutations.append(missing)
    extra_outer = copy.deepcopy(original)
    extra_outer["extra"] = None
    mutations.append(extra_outer)
    extra_nested = copy.deepcopy(original)
    extra_nested["conversation_state"]["extra"] = None
    mutations.append(extra_nested)
    for key, invalid in (
        ("schema_version", True),
        ("completed_turn_index", False),
        ("previous_user_text", ""),
        ("previous_assistant_text", "foreign"),
        ("conversation_state", []),
    ):
        changed = copy.deepcopy(original)
        changed[key] = invalid
        mutations.append(changed)
    nested_invalid = {
        "requires_backend_api": 0,
        "should_reset": 0,
        "state_confidence": -0.0,
        "state_turn_count": False,
        "updated_at_turn": True,
        "last_user_query": "foreign",
        "last_assistant_answer": "foreign",
        "current_topic": "foreign",
    }
    for key, invalid in nested_invalid.items():
        changed = copy.deepcopy(original)
        changed["conversation_state"][key] = invalid
        mutations.append(changed)
    for value in mutations:
        with pytest.raises(orchestration.OrchestrationError) as caught:
            runner._validate_fixed_synthetic_snapshot_v1(value)
        assert caught.value.category == "CHECKPOINT_SNAPSHOT_INVALID"
    negative_zero = copy.deepcopy(original)
    negative_zero["conversation_state"]["state_confidence"] = -0.0
    assert math.copysign(
        1.0, negative_zero["conversation_state"]["state_confidence"]
    ) == -1.0


def _capture_initial_prepared(plan, unit):
    authority = runner._fixed_offline_authority()
    empty_state = store._UnitState(tuple(), None, None)
    dependencies = authority.dependencies_for(unit, empty_state)
    captured = []

    def capture(journal):
        captured.append(journal)
        raise _PreparedCaptured

    with pytest.raises(_PreparedCaptured):
        runner.orchestrate_offline_unit(
            plan,
            unit,
            journal_persistence_callback=capture,
            **dependencies,
        )
    assert len(captured) == 1
    assert captured[0].state == "prepared"
    return captured[0]


def _publish_archive_only(
    root: Path,
    contract,
    journal,
    *,
    sequence: int,
    previous_sha: str | None,
    predecessor_attempt_id: str | None,
    predecessor_terminal_sha: str | None,
    private_commit_sha: str | None = None,
):
    value, path = _archive_candidate(
        root,
        contract,
        journal,
        sequence=sequence,
        previous_sha=previous_sha,
        predecessor_attempt_id=predecessor_attempt_id,
        predecessor_terminal_sha=predecessor_terminal_sha,
        private_commit_sha=private_commit_sha,
    )
    assert store._atomic_publish_json(
        path,
        value,
        replace=False,
        maximum=store._ARCHIVE_LIMIT,
    )
    loaded = store._validate_archive(
        store._read_json(path, store._ARCHIVE_LIMIT),
        contract_sha256=contract["run_contract_sha256"],
        expected_path=path,
    )
    assert loaded.journal == journal
    return value


def _build_archive_only_tip(plan, contract, root, unit, branch):
    prepared = _capture_initial_prepared(plan, unit)
    clock = runner._FixedSyntheticClockV1(prepared.updated_at)
    attempt = {
        "PREPARED_MUTABLE": 1,
        "CALL_STARTED_MUTABLE": 1,
        "PRE_SEND_RETRYABLE_MUTABLE_A1": 1,
        "PRE_SEND_RETRYABLE_MUTABLE_A2": 2,
        "PRE_SEND_RETRYABLE_MUTABLE_A3": 3,
        "PROVIDER_RETURNED_MUTABLE": 1,
        "POST_CALL_RETRYABLE_MUTABLE_A1": 1,
        "POST_CALL_RETRYABLE_MUTABLE_A2": 2,
        "POST_CALL_RETRYABLE_MUTABLE_A3": 3,
        "TERMINAL_MUTABLE": 1,
        "UNCERTAIN_MUTABLE": 1,
    }[branch]
    predecessor_attempt_id = None
    predecessor_terminal_sha = None
    previous_attempt_tip = None
    tip_value = None
    tip_journal = None
    for number in range(1, attempt + 1):
        if number > 1:
            assert previous_attempt_tip is not None
            prepared = inflight.next_retry_journal(
                previous_attempt_tip,
                clock(),
            )
            predecessor_attempt_id = previous_attempt_tip.identity.attempt_id
        value = _publish_archive_only(
            root,
            contract,
            prepared,
            sequence=1,
            previous_sha=None,
            predecessor_attempt_id=predecessor_attempt_id,
            predecessor_terminal_sha=predecessor_terminal_sha,
        )
        if number < attempt:
            failed = inflight.transition(
                prepared,
                "retryable_failed",
                clock(),
                sanitized_outcome_category="pre_send_failure",
            )
            value = _publish_archive_only(
                root,
                contract,
                failed,
                sequence=2,
                previous_sha=value["archive_sha256"],
                predecessor_attempt_id=predecessor_attempt_id,
                predecessor_terminal_sha=predecessor_terminal_sha,
            )
            previous_attempt_tip = failed
            predecessor_terminal_sha = value["archive_sha256"]
            continue
        if branch == "PREPARED_MUTABLE":
            tip_journal = prepared
            tip_value = value
            continue
        if branch.startswith("PRE_SEND_RETRYABLE"):
            tip_journal = inflight.transition(
                prepared,
                "retryable_failed",
                clock(),
                sanitized_outcome_category="pre_send_failure",
            )
            tip_value = _publish_archive_only(
                root,
                contract,
                tip_journal,
                sequence=2,
                previous_sha=value["archive_sha256"],
                predecessor_attempt_id=predecessor_attempt_id,
                predecessor_terminal_sha=predecessor_terminal_sha,
            )
            continue
        call_started = inflight.transition(
            prepared,
            "call_started",
            clock(),
            provider_request_id=inflight.derive_provider_request_id(
                prepared.identity
            ),
        )
        call_value = _publish_archive_only(
            root,
            contract,
            call_started,
            sequence=2,
            previous_sha=value["archive_sha256"],
            predecessor_attempt_id=predecessor_attempt_id,
            predecessor_terminal_sha=predecessor_terminal_sha,
        )
        if branch == "CALL_STARTED_MUTABLE":
            tip_journal = call_started
            tip_value = call_value
        elif branch == "PROVIDER_RETURNED_MUTABLE":
            tip_journal = inflight.transition(
                call_started,
                "provider_returned",
                clock(),
                provider_response_id="synthetic_response_id",
                provider_response_sha256="d" * 64,
                response_sha256=transport.sha256_text("synthetic-response"),
            )
            tip_value = _publish_archive_only(
                root,
                contract,
                tip_journal,
                sequence=3,
                previous_sha=call_value["archive_sha256"],
                predecessor_attempt_id=predecessor_attempt_id,
                predecessor_terminal_sha=predecessor_terminal_sha,
            )
        else:
            state, category = (
                ("retryable_failed", "http_429")
                if branch.startswith("POST_CALL_RETRYABLE")
                else ("terminal_failed", "provider_rejected")
                if branch == "TERMINAL_MUTABLE"
                else ("uncertain", "timeout")
            )
            tip_journal = inflight.transition(
                call_started,
                state,
                clock(),
                sanitized_outcome_category=category,
            )
            tip_value = _publish_archive_only(
                root,
                contract,
                tip_journal,
                sequence=3,
                previous_sha=call_value["archive_sha256"],
                predecessor_attempt_id=predecessor_attempt_id,
                predecessor_terminal_sha=predecessor_terminal_sha,
            )
    assert tip_journal is not None and tip_value is not None
    return tip_journal, tip_value


@pytest.mark.parametrize(
    "branch,expected_category,expected_action,expected_block",
    (
        ("PREPARED_MUTABLE", "same-attempt-continuable", None, None),
        ("CALL_STARTED_MUTABLE", "permanently-non-executable", "permanently_non_executable", "call_started"),
        ("PRE_SEND_RETRYABLE_MUTABLE_A1", "retry-constructible", "retry_constructed", None),
        ("PRE_SEND_RETRYABLE_MUTABLE_A2", "retry-constructible", "retry_constructed", None),
        ("PRE_SEND_RETRYABLE_MUTABLE_A3", "permanently-non-executable", "permanently_non_executable", "attempts_exhausted"),
        ("PROVIDER_RETURNED_MUTABLE", "permanently-non-executable", "permanently_non_executable", "provider_returned_without_commit"),
        ("POST_CALL_RETRYABLE_MUTABLE_A1", "retry-constructible", "retry_constructed", None),
        ("POST_CALL_RETRYABLE_MUTABLE_A2", "retry-constructible", "retry_constructed", None),
        ("POST_CALL_RETRYABLE_MUTABLE_A3", "permanently-non-executable", "permanently_non_executable", "attempts_exhausted"),
        ("TERMINAL_MUTABLE", "permanently-non-executable", "permanently_non_executable", "terminal_failed"),
        ("UNCERTAIN_MUTABLE", "permanently-non-executable", "permanently_non_executable", "uncertain"),
    ),
)
def test_exact_archive_tip_precedes_mutable_fault_and_reopen_repairs_only_pointer(
    state_root,
    frozen_plan_and_contract,
    branch,
    expected_category,
    expected_action,
    expected_block,
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    runner.durable_progress(plan)
    tip_journal, tip_value = _build_archive_only_tip(
        plan, contract, state_root, unit, branch
    )
    mutable_path = state_root / "journals" / (
        f"{tip_journal.identity.execution_unit_id}.json"
    )
    assert not mutable_path.exists()
    point = "before_mutable_record_publication_error"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with store._RunWideLock(state_root) as lock:
            with pytest.raises(store.StoreError) as caught:
                store._load_unit_state_locked(
                    tip_journal.identity.execution_unit_id,
                    run_contract=contract,
                    lock=lock,
                )
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, "T", caught.value)
    assert not mutable_path.exists()
    assert len(_temps(state_root)) == 1
    with store._open_store(contract) as (opened, lock):
        repaired = store._load_unit_state_locked(
            tip_journal.identity.execution_unit_id,
            run_contract=opened,
            lock=lock,
        )
        category, _state, _commit = store._direct_unit_category_locked(
            plan,
            unit,
            run_contract=opened,
            lock=lock,
        )
    assert repaired.tip is not None
    assert repaired.tip.value["archive_sha256"] == tip_value["archive_sha256"]
    assert repaired.mutable == store._mutable_from_archive(tip_value)
    assert category == expected_category
    assert _temps(state_root) == []
    if expected_action is not None:
        outcome = _safe_durable_call(plan, unit)
        assert outcome.action == expected_action
        assert outcome.block_category == expected_block
        assert outcome.provider_call_count == 0


@pytest.mark.parametrize(
    "terminal_branch,new_attempt",
    (
        ("PRE_SEND_RETRYABLE_MUTABLE_A1", 2),
        ("PRE_SEND_RETRYABLE_MUTABLE_A2", 3),
    ),
)
def test_mutable_reconciliation_repairs_canonical_cross_attempt_lag(
    state_root,
    frozen_plan_and_contract,
    terminal_branch,
    new_attempt,
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    runner.durable_progress(plan)
    terminal_journal, terminal_archive = _build_archive_only_tip(
        plan,
        contract,
        state_root,
        unit,
        terminal_branch,
    )
    unit_id = terminal_journal.identity.execution_unit_id
    mutable_path = state_root / "journals" / f"{unit_id}.json"
    earlier_pointer = store._mutable_from_archive(terminal_archive)
    assert store._atomic_publish_json(
        mutable_path,
        earlier_pointer,
        replace=True,
        maximum=store._JOURNAL_LIMIT,
    )
    earlier_bytes = mutable_path.read_bytes()
    before_archive_count = len(
        [
            path
            for path in (state_root / "attempts" / unit_id).iterdir()
            if store._ARCHIVE_NAME_RE.fullmatch(path.name) is not None
        ]
    )

    point = "before_mutable_record_publication_error"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with pytest.raises(store.StoreError) as caught:
            runner.orchestrate_durable_offline_unit(plan, unit)
        assert caught.value.category == "STORE_IO_FAILURE"
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        assert _count_tuple(observation) == (1, 1, 1, 1, 0, 2, 1, 0)
        assert tuple(
            map(
                len,
                (
                    observation.temporary_opened_handle_ids,
                    observation.temporary_close_attempt_handle_ids,
                    observation.initial_verification_opened_handle_ids,
                    observation.initial_verification_close_attempt_handle_ids,
                    observation.recovery_opened_handle_ids,
                    observation.recovery_close_attempt_handle_ids,
                ),
            )
        ) == (2, 2, 1, 1, 0, 0)
        _assert_group(observation, "primary", "STORE_IO_FAILURE")
        assert observation.primary_exception_id == id(caught.value)
        _assert_absent_group(observation, "initial")
        _assert_absent_group(observation, "secondary")

    assert mutable_path.read_bytes() == earlier_bytes
    assert store._read_json(mutable_path, store._JOURNAL_LIMIT) == earlier_pointer
    assert len(_temps(state_root)) == 1
    archive_paths = [
        path
        for path in (state_root / "attempts" / unit_id).iterdir()
        if store._ARCHIVE_NAME_RE.fullmatch(path.name) is not None
    ]
    assert len(archive_paths) == before_archive_count + 1
    new_path = next(
        path
        for path in archive_paths
        if int(store._ARCHIVE_NAME_RE.fullmatch(path.name).group("attempt"))
        == new_attempt
    )
    new_tip = store._validate_archive(
        store._read_json(new_path, store._ARCHIVE_LIMIT),
        contract_sha256=contract["run_contract_sha256"],
        expected_path=new_path,
    )
    assert new_tip.value["attempt_number"] == new_attempt
    assert new_tip.value["sequence_number"] == 1
    assert new_tip.journal.state == "prepared"
    assert new_tip.value["predecessor_attempt_id"] == terminal_journal.identity.attempt_id
    assert new_tip.value["predecessor_terminal_archive_sha256"] == (
        terminal_archive["archive_sha256"]
    )
    assert list((state_root / "commits").iterdir()) == []

    with store._open_store(contract) as (opened, lock):
        repaired = store._load_unit_state_locked(
            unit_id,
            run_contract=opened,
            lock=lock,
        )
        category, _state, commit = store._direct_unit_category_locked(
            plan,
            unit,
            run_contract=opened,
            lock=lock,
        )
    assert repaired.tip is not None
    assert repaired.tip.value["archive_sha256"] == new_tip.value["archive_sha256"]
    assert repaired.mutable == store._mutable_from_archive(new_tip.value)
    assert store._read_json(mutable_path, store._JOURNAL_LIMIT) == (
        store._mutable_from_archive(new_tip.value)
    )
    assert category == "same-attempt-continuable"
    assert commit is None
    assert _temps(state_root) == []


def test_mutable_reconciliation_rejects_rehashed_cross_archive_wrapper(
    state_root,
    frozen_plan_and_contract,
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    runner.durable_progress(plan)
    journal, _tip = _build_archive_only_tip(
        plan,
        contract,
        state_root,
        unit,
        "CALL_STARTED_MUTABLE",
    )
    state = _load_exact_unit_state(
        contract,
        journal.identity.execution_unit_id,
        repair_mutable=False,
    )
    assert len(state.archives) == 2
    first, second = state.archives
    contradictory = store._mutable_from_archive(first.value)
    contradictory["journal"] = copy.deepcopy(second.value["journal"])
    contradictory["journal_sha256"] = second.value["journal_sha256"]
    contradictory["record_sha256"] = store._record_hash(contradictory)
    validated, embedded = store._validate_mutable(
        contradictory,
        contract_sha256=contract["run_contract_sha256"],
        execution_unit_id=journal.identity.execution_unit_id,
    )
    assert validated == contradictory
    assert embedded == second.journal
    assert contradictory["latest_archive_sha256"] == first.value["archive_sha256"]
    assert contradictory != store._mutable_from_archive(first.value)
    mutable_path = state_root / "journals" / (
        f"{journal.identity.execution_unit_id}.json"
    )
    assert store._atomic_publish_json(
        mutable_path,
        contradictory,
        replace=True,
        maximum=store._JOURNAL_LIMIT,
    )
    before = mutable_path.read_bytes()
    with pytest.raises(store.StoreError) as caught:
        with store._open_store(contract) as (opened, lock):
            store._load_unit_state_locked(
                journal.identity.execution_unit_id,
                run_contract=opened,
                lock=lock,
            )
    assert caught.value.category == "STORE_ARCHIVE_CHAIN_INVALID"
    assert mutable_path.read_bytes() == before
    assert _temps(state_root) == []
    assert list((state_root / "commits").iterdir()) == []


def test_mutable_reconciliation_accepts_exact_tip_without_republication(
    state_root,
    frozen_plan_and_contract,
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    runner.durable_progress(plan)
    journal, tip = _build_archive_only_tip(
        plan,
        contract,
        state_root,
        unit,
        "CALL_STARTED_MUTABLE",
    )
    mutable_path = state_root / "journals" / (
        f"{journal.identity.execution_unit_id}.json"
    )
    canonical = store._mutable_from_archive(tip)
    assert store._atomic_publish_json(
        mutable_path,
        canonical,
        replace=True,
        maximum=store._JOURNAL_LIMIT,
    )
    before = mutable_path.read_bytes()
    point = "before_mutable_record_publication_error"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with store._open_store(contract) as (opened, lock):
            loaded = store._load_unit_state_locked(
                journal.identity.execution_unit_id,
                run_contract=opened,
                lock=lock,
            )
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        assert _count_tuple(observation) == (0,) * 8
        assert all(
            getattr(observation, name) == () for name in store._FAULT_HANDLE_NAMES
        )
        for role in store._FAULT_EXCEPTION_ROLES:
            _assert_absent_group(observation, role)
    assert loaded.mutable == canonical
    assert mutable_path.read_bytes() == before
    assert _temps(state_root) == []


def test_mutable_reconciliation_repairs_canonical_same_attempt_lag(
    state_root,
    frozen_plan_and_contract,
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    runner.durable_progress(plan)
    journal, _tip = _build_archive_only_tip(
        plan,
        contract,
        state_root,
        unit,
        "CALL_STARTED_MUTABLE",
    )
    state = _load_exact_unit_state(
        contract,
        journal.identity.execution_unit_id,
        repair_mutable=False,
    )
    assert len(state.archives) == 2
    earlier = store._mutable_from_archive(state.archives[0].value)
    mutable_path = state_root / "journals" / (
        f"{journal.identity.execution_unit_id}.json"
    )
    assert store._atomic_publish_json(
        mutable_path,
        earlier,
        replace=True,
        maximum=store._JOURNAL_LIMIT,
    )
    with store._open_store(contract) as (opened, lock):
        repaired = store._load_unit_state_locked(
            journal.identity.execution_unit_id,
            run_contract=opened,
            lock=lock,
        )
    assert repaired.tip is not None
    assert repaired.tip.value["archive_sha256"] == state.archives[-1].value[
        "archive_sha256"
    ]
    assert repaired.mutable == store._mutable_from_archive(repaired.tip.value)
    assert store._read_json(mutable_path, store._JOURNAL_LIMIT) == repaired.mutable


@pytest.mark.parametrize(
    "case,expected_category",
    (
        ("absent", "STORE_ARCHIVE_CHAIN_INVALID"),
        ("ahead", "STORE_ARCHIVE_CHAIN_INVALID"),
        ("off_chain", "STORE_ARCHIVE_CHAIN_INVALID"),
        ("hash_conflicting", "STORE_HASH_MISMATCH"),
        ("identity_conflicting", "STORE_HASH_MISMATCH"),
    ),
)
def test_mutable_reconciliation_rejects_nonrepairable_pointer_evidence(
    state_root,
    frozen_plan_and_contract,
    case,
    expected_category,
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    runner.durable_progress(plan)
    journal, _tip = _build_archive_only_tip(
        plan,
        contract,
        state_root,
        unit,
        "CALL_STARTED_MUTABLE",
    )
    unit_id = journal.identity.execution_unit_id
    state = _load_exact_unit_state(contract, unit_id, repair_mutable=False)
    first, second = state.archives
    wrapper = store._mutable_from_archive(second.value)

    if case == "absent":
        wrapper = store._mutable_from_archive(first.value)
        wrapper["latest_archive_sha256"] = "e" * 64
        wrapper["record_sha256"] = store._record_hash(wrapper)
    elif case == "ahead":
        clock = runner._FixedSyntheticClockV1(second.journal.updated_at)
        future = inflight.transition(
            second.journal,
            "provider_returned",
            clock(),
            provider_response_id="synthetic_response_id",
            provider_response_sha256="d" * 64,
            response_sha256=transport.sha256_text("synthetic-response"),
        )
        future_archive, _future_path = _archive_candidate(
            state_root,
            contract,
            future,
            sequence=3,
            previous_sha=second.value["archive_sha256"],
            predecessor_attempt_id=None,
            predecessor_terminal_sha=None,
        )
        wrapper = store._mutable_from_archive(future_archive)
    elif case == "off_chain":
        path = second.path
        off_chain = copy.deepcopy(dict(second.value))
        off_chain["previous_archive_sha256"] = "f" * 64
        off_chain["archive_sha256"] = store._archive_hash(off_chain)
        path.write_bytes(store._canonical_bytes(off_chain) + b"\n")
        wrapper = store._mutable_from_archive(off_chain)
    elif case == "hash_conflicting":
        wrapper["journal_sha256"] = "0" * 64
        wrapper["record_sha256"] = store._record_hash(wrapper)
    else:
        foreign_unit = next(
            candidate
            for candidate in plan
            if candidate["request_id"] != unit["request_id"]
            and candidate["system_config_id"] == unit["system_config_id"]
            and candidate["turn_index"] == 1
        )
        foreign = _capture_initial_prepared(plan, foreign_unit)
        wrapper["execution_unit_id"] = foreign.identity.execution_unit_id
        wrapper["attempt_number"] = foreign.identity.attempt_number
        wrapper["attempt_id"] = foreign.identity.attempt_id
        wrapper["journal"] = foreign.to_dict()
        wrapper["journal_sha256"] = inflight.journal_sha256(foreign)
        wrapper["record_sha256"] = store._record_hash(wrapper)

    mutable_path = state_root / "journals" / f"{unit_id}.json"
    assert store._atomic_publish_json(
        mutable_path,
        wrapper,
        replace=True,
        maximum=store._JOURNAL_LIMIT,
    )
    before = mutable_path.read_bytes()
    with pytest.raises(store.StoreError) as caught:
        with store._open_store(contract) as (opened, lock):
            store._load_unit_state_locked(
                unit_id,
                run_contract=opened,
                lock=lock,
            )
    assert caught.value.category == expected_category
    assert mutable_path.read_bytes() == before
    assert _temps(state_root) == []
    assert list((state_root / "commits").iterdir()) == []


def test_retry_attempts_one_to_three_lineage_and_attempt_four_impossible(
    state_root, frozen_plan_and_contract
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=True)
    runner.durable_progress(plan)
    journal, _value = _build_archive_only_tip(
        plan,
        contract,
        state_root,
        unit,
        "PRE_SEND_RETRYABLE_MUTABLE_A1",
    )
    first_retry = _safe_durable_call(plan, unit)
    assert first_retry.action == "retry_constructed"
    assert first_retry.attempt_number == 2
    assert first_retry.provider_call_count == 0
    with store._open_store(contract) as (opened, lock):
        state = store._load_unit_state_locked(
            journal.identity.execution_unit_id,
            run_contract=opened,
            lock=lock,
        )
        assert state.tip is not None
        attempt_two = state.tip.journal
        assert attempt_two.state == "prepared"
        clock = runner._FixedSyntheticClockV1(attempt_two.updated_at)
        failed_two = inflight.transition(
            attempt_two,
            "retryable_failed",
            clock(),
            sanitized_outcome_category="pre_send_failure",
        )
        store._publish_journal_locked(
            failed_two,
            run_contract=opened,
            lock=lock,
        )
    second_retry = _safe_durable_call(plan, unit)
    assert second_retry.action == "retry_constructed"
    assert second_retry.attempt_number == 3
    assert second_retry.provider_call_count == 0
    with store._open_store(contract) as (opened, lock):
        state = store._load_unit_state_locked(
            journal.identity.execution_unit_id,
            run_contract=opened,
            lock=lock,
        )
        assert state.tip is not None
        attempt_three = state.tip.journal
        clock = runner._FixedSyntheticClockV1(attempt_three.updated_at)
        failed_three = inflight.transition(
            attempt_three,
            "retryable_failed",
            clock(),
            sanitized_outcome_category="pre_send_failure",
        )
        store._publish_journal_locked(
            failed_three,
            run_contract=opened,
            lock=lock,
        )
        with pytest.raises(inflight.JournalError):
            inflight.next_retry_journal(failed_three, clock())
    exhausted = _safe_durable_call(plan, unit)
    assert exhausted.action == "permanently_non_executable"
    assert exhausted.block_category == "attempts_exhausted"
    assert exhausted.attempt_number == 3
    assert exhausted.provider_call_count == 0


def test_private_commit_identical_replay_conflict_and_first_success_preserved(
    state_root, frozen_plan_and_contract
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=False)
    completed = _safe_durable_call(plan, unit)
    assert completed.action == "completed"
    path = store._commit_path(state_root, unit)
    original_bytes = path.read_bytes()
    original = store._read_json(path, store._COMMIT_LIMIT)
    with store._open_store(contract) as (_opened, lock):
        replay, published = store._publish_private_commit_locked(
            original,
            unit=unit,
            lock=lock,
        )
        assert published is False
        assert replay == original
        conflicting = copy.deepcopy(original)
        conflicting["envelope_sha256"] = "0" * 64
        with pytest.raises(store.StoreError) as caught:
            store._publish_private_commit_locked(
                conflicting,
                unit=unit,
                lock=lock,
            )
        assert caught.value.category == "STORE_CONFLICTING_FIRST_SUCCESS"
    assert path.read_bytes() == original_bytes
    reopened = _safe_durable_call(plan, unit)
    assert reopened.action == "completed"
    assert reopened.private_commit_sha256 == completed.private_commit_sha256
    assert reopened.provider_call_count == 0


@pytest.mark.parametrize(
    "mutation",
    (
        "truncated",
        "extra",
        "missing",
        "hash",
        "result",
        "identity",
        "lineage",
        "relationship",
    ),
)
def test_private_commit_malformed_and_field_mutations_fail_closed(
    state_root, frozen_plan_and_contract, mutation
):
    plan = frozen_plan_and_contract.plan
    unit = _selected_unit(plan, provider=False)
    _safe_durable_call(plan, unit)
    path = store._commit_path(state_root, unit)
    original = store._read_json(path, store._COMMIT_LIMIT)
    if mutation == "truncated":
        raw = path.read_bytes()[: len(path.read_bytes()) // 2]
    else:
        changed = copy.deepcopy(original)
        if mutation == "extra":
            changed["extra"] = None
        elif mutation == "missing":
            changed.pop("schema_version")
        elif mutation == "hash":
            changed["envelope_sha256"] = "0" * 64
        elif mutation == "result":
            changed["formal_result"]["response_sha256"] = "0" * 64
        elif mutation == "identity":
            changed["execution_identity"]["request_id"] = "0" * 64
        elif mutation == "lineage":
            changed["attempt_lineage"]["attempt_number"] = 2
        else:
            changed["rq3_relationship"]["kind"] = "context_turn_one"
        raw = store._canonical_bytes(changed) + b"\n"
    path.write_bytes(raw)
    with pytest.raises(store.StoreError) as caught:
        runner.durable_progress(plan)
    assert caught.value.category in {
        "STORE_JSON_INVALID",
        "STORE_SCHEMA_INVALID",
        "STORE_HASH_MISMATCH",
        "STORE_COMMIT_INVALID",
        "STORE_COMMIT_JOURNAL_CONFLICT",
    }


@pytest.mark.parametrize("point", INHERITED)
def test_each_inherited_literal_has_live_process_missing_trigger_negative(
    state_root, point
):
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        assert _count_tuple(observation) == (0,) * 8
        assert all(
            getattr(observation, name) == () for name in store._FAULT_HANDLE_NAMES
        )
        for role in store._FAULT_EXCEPTION_ROLES:
            _assert_absent_group(observation, role)


def test_mark_only_inherited_literal_exact_live_observation_and_continuation(
    state_root, frozen_plan_and_contract
):
    point = "after_fake_client_returned_mark"
    plan = frozen_plan_and_contract.plan
    unit = _selected_unit(plan, provider=True)
    runner.durable_progress(plan)
    known = _marker_names(state_root, point)
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        outcome = _safe_durable_call(plan, unit)
        assert outcome.action == "completed"
        assert outcome.provider_call_count == 1
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        assert _count_tuple(observation) == (1, 9, 9, 9, 0, 9, 9, 0)
        assert len(observation.temporary_opened_handle_ids) == 9
        assert (
            observation.temporary_opened_handle_ids
            == observation.temporary_close_attempt_handle_ids
        )
        assert len(observation.initial_verification_opened_handle_ids) == 9
        assert (
            observation.initial_verification_opened_handle_ids
            == observation.initial_verification_close_attempt_handle_ids
        )
        assert observation.recovery_opened_handle_ids == ()
        assert observation.recovery_close_attempt_handle_ids == ()
        for role in store._FAULT_EXCEPTION_ROLES:
            _assert_absent_group(observation, role)
    new_markers = _marker_names(state_root, point) - known
    assert len(new_markers) == 1
    marker = state_root.parent / ".stage_b2_fault_markers" / next(iter(new_markers))
    marker_pid = int(marker.name.split("-")[1])
    value = _read_marker(marker, point, marker_pid, 1)
    assert value["private_commit_sha256"] is None
    reopened = _safe_durable_call(plan, unit)
    assert reopened.action == "completed"
    assert reopened.provider_call_count == 0
    _remove_own_marker(marker)


def test_repeated_open_close_and_wrong_handle_are_observable_without_spy(
    state_root
):
    point = "before_atomic_temp_create_error"
    first_path = state_root / "first.synthetic"
    second_path = state_root / "second.synthetic"
    third_path = state_root / "third.synthetic"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        first = store._open_tracked(first_path, "xb", "temporary")
        second = store._open_tracked(second_path, "xb", "temporary")
        third = third_path.open("xb", buffering=0)
        store._close_tracked(first, "temporary")
        store._close_tracked(first, "temporary")
        store._close_tracked(third, "temporary")
        store._close_tracked(second, "temporary")
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        t1, t2 = observation.temporary_opened_handle_ids
        close_tokens = observation.temporary_close_attempt_handle_ids
        assert t1 != t2
        assert close_tokens[:2] == (t1, t1)
        assert close_tokens[2] not in {t1, t2}
        assert close_tokens[3] == t2
        assert observation.atomic_temp_close_attempt_count == 4
        assert observation.trigger_count == 0


@pytest.mark.parametrize("provider", (False, True))
def test_rq3_turn_one_checkpoint_and_turn_two_exact_commit_binding(
    state_root, frozen_plan_and_contract, provider
):
    plan = frozen_plan_and_contract.plan
    turn_two = _selected_unit(
        plan,
        provider=provider,
        config="context_aware",
        rq="RQ3",
        turn=2,
    )
    turn_one = _complete_turn_one_for(plan, turn_two)
    first_commit = store._read_json(
        store._commit_path(state_root, turn_one), store._COMMIT_LIMIT
    )
    relationship = first_commit["rq3_relationship"]
    assert relationship["kind"] == "context_turn_one"
    assert relationship["turn_one_commit_sha256"] is None
    assert type(relationship["checkpoint_evidence"]) is dict
    turn_two_outcome = _safe_durable_call(plan, turn_two)
    assert turn_two_outcome.action == "completed"
    assert turn_two_outcome.provider_call_count == (1 if provider else 0)
    second_commit = store._read_json(
        store._commit_path(state_root, turn_two), store._COMMIT_LIMIT
    )
    second_relationship = second_commit["rq3_relationship"]
    assert second_relationship["kind"] == "context_turn_two"
    assert (
        second_relationship["turn_one_commit_sha256"]
        == first_commit["envelope_sha256"]
    )
    assert type(second_relationship["checkpoint_evidence"]) is dict
    assert (
        second_relationship["checkpoint_record_sha256"]
        == relationship["checkpoint_record_sha256"]
    )
    reopened = _safe_durable_call(plan, turn_two)
    assert reopened.action == "completed"
    assert reopened.provider_call_count == 0
    assert reopened.private_commit_sha256 == turn_two_outcome.private_commit_sha256
    progress = runner.durable_progress(plan)
    assert progress.total_successful_units == 2
    assert progress.successful_by_rq["RQ3"] == 2
    assert progress.successful_by_system["context_aware"] == 2


def test_rq3_dependency_missing_and_permanent_rows_never_construct_turn_two(
    state_root, frozen_plan_and_contract
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    turn_two = _selected_unit(
        plan,
        provider=True,
        config="context_aware",
        rq="RQ3",
        turn=2,
    )
    turn_one = next(
        candidate
        for candidate in plan
        if candidate["case_id"] == turn_two["case_id"]
        and candidate["system_config_id"] == "context_aware"
        and candidate["turn_index"] == 1
    )
    missing = _safe_durable_call(plan, turn_two)
    assert missing.action == "dependency_blocked"
    assert missing.block_category == "dependency_missing"
    assert missing.attempt_number is None
    assert missing.journal_state is None
    assert missing.provider_call_count == 0
    turn_two_id = store._execution_unit_id(turn_two)
    assert not (state_root / "attempts" / turn_two_id).exists()

    runner.durable_progress(plan)
    tip, _value = _build_archive_only_tip(
        plan,
        contract,
        state_root,
        turn_one,
        "CALL_STARTED_MUTABLE",
    )
    with store._open_store(contract) as (opened, lock):
        store._load_unit_state_locked(
            tip.identity.execution_unit_id,
            run_contract=opened,
            lock=lock,
        )
    permanent = _safe_durable_call(plan, turn_two)
    assert permanent.action == "permanently_non_executable"
    assert permanent.block_category == "dependency_permanent"
    assert permanent.execution_unit_id == turn_two_id
    assert permanent.execution_order == turn_two["execution_order"]
    assert permanent.attempt_number is None
    assert permanent.journal_state is None
    assert permanent.private_commit_sha256 is None
    assert permanent.orchestration_outcome is None
    assert permanent.provider_call_count == 0
    assert not (state_root / "attempts" / turn_two_id).exists()


def test_progress_fresh_lowest_order_partition_and_idempotent_counting(
    state_root, frozen_plan_and_contract
):
    plan = frozen_plan_and_contract.plan
    fresh = runner.durable_progress(plan)
    assert fresh.run_state == "in_progress"
    assert fresh.total_successful_units == 0
    assert fresh.remaining_units == 190
    assert fresh.next_eligible_execution_order == 1
    assert (
        fresh.initial_executable_units
        + fresh.same_attempt_continuable_units
        + fresh.retry_constructible_units
        + fresh.dependency_blocked_units
        + fresh.permanently_non_executable_units
        == 190
    )
    assert fresh.dependency_blocked_units == 12
    unit = _selected_unit(plan, provider=False)
    first = _safe_durable_call(plan, unit)
    second = _safe_durable_call(plan, unit)
    assert first.private_commit_sha256 == second.private_commit_sha256
    after = runner.durable_progress(plan)
    assert after.total_successful_units == 1
    assert after.remaining_units == 189


@pytest.mark.parametrize("kind", ("archive", "mutable"))
@pytest.mark.parametrize(
    "mutation",
    ("missing", "extra", "version", "hash", "nested", "truncated"),
)
def test_archive_and_mutable_corruption_fail_closed(
    state_root, frozen_plan_and_contract, kind, mutation
):
    plan = frozen_plan_and_contract.plan
    unit = _selected_unit(plan, provider=False)
    _safe_durable_call(plan, unit)
    unit_id = store._execution_unit_id(unit)
    if kind == "archive":
        path = next((state_root / "attempts" / unit_id).iterdir())
        maximum = store._ARCHIVE_LIMIT
    else:
        path = state_root / "journals" / f"{unit_id}.json"
        maximum = store._JOURNAL_LIMIT
    if mutation == "truncated":
        original = path.read_bytes()
        raw = original[: len(original) // 2]
    else:
        value = store._read_json(path, maximum)
        changed = copy.deepcopy(value)
        if mutation == "missing":
            changed.pop("schema_version")
        elif mutation == "extra":
            changed["extra"] = None
        elif mutation == "version":
            changed["schema_version"] = True
        elif mutation == "hash":
            changed[
                "archive_sha256" if kind == "archive" else "record_sha256"
            ] = "0" * 64
        else:
            changed["journal"]["state"] = "uncertain"
        raw = store._canonical_bytes(changed) + b"\n"
    path.write_bytes(raw)
    with pytest.raises(store.StoreError) as caught:
        runner.durable_progress(plan)
    assert caught.value.category in {
        "STORE_JSON_INVALID",
        "STORE_SCHEMA_INVALID",
        "STORE_HASH_MISMATCH",
        "STORE_ARCHIVE_CHAIN_INVALID",
        "STORE_COMMIT_INVALID",
        "STORE_COMMIT_JOURNAL_CONFLICT",
    }


def test_immutable_create_only_and_mutable_replacement_semantics(state_root):
    immutable, _ = _target(state_root, "PREPARED_ARCHIVE")
    first = {"schema_version": 1, "value": "first"}
    second = {"schema_version": 1, "value": "second"}
    assert _publish(immutable, False, first) is True
    original = immutable.read_bytes()
    assert _publish(immutable, False, first) is False
    assert immutable.read_bytes() == original
    assert _publish(immutable, False, second) is False
    assert immutable.read_bytes() == original
    mutable, replace = _target(state_root, "PREPARED_MUTABLE")
    assert replace is True
    assert _publish(mutable, True, first) is True
    assert _publish(mutable, True, second) is True
    assert mutable.read_bytes() == store._canonical_bytes(second) + b"\n"


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows durability contract")
@pytest.mark.parametrize("provider", (False, True))
def test_actual_local_and_provider_repair_archive_publication_faults(
    state_root, frozen_plan_and_contract, provider
):
    plan = frozen_plan_and_contract.plan
    unit = _selected_unit(plan, provider=provider)
    marker, _value = _run_crash_child(
        state_root,
        "after_private_commit_published_exit",
        provider=provider,
        exit_code=92,
        provider_calls=1 if provider else 0,
    )
    _remove_own_marker(marker)
    point = "before_atomic_publication_error"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with pytest.raises(store.StoreError) as caught:
            runner.orchestrate_durable_offline_unit(plan, unit)
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, "T", caught.value)
    assert len(_temps(state_root)) == 1
    reopened = _safe_durable_call(plan, unit)
    assert reopened.action == "completed"
    assert reopened.provider_call_count == 0
    assert _temps(state_root) == []


@pytest.mark.skipif(os.name != "nt", reason="frozen Windows durability contract")
@pytest.mark.parametrize(
    "provider,point",
    (
        (False, "before_mutable_record_publication_error"),
        (True, "before_mutable_record_publication_error"),
        (True, "before_atomic_publication_error"),
    ),
)
def test_actual_local_and_committed_pointer_repair_publication_faults(
    state_root, frozen_plan_and_contract, provider, point
):
    plan = frozen_plan_and_contract.plan
    contract = frozen_plan_and_contract.contract
    unit = _selected_unit(plan, provider=provider)
    crash_point = (
        "after_committed_archive_published_exit"
        if provider
        else "after_private_commit_published_exit"
    )
    marker, _value = _run_crash_child(
        state_root,
        crash_point,
        provider=provider,
        exit_code=93 if provider else 92,
        provider_calls=1 if provider else 0,
    )
    _remove_own_marker(marker)
    if not provider:
        with store._install_stage_b2_test_fault_controller_for_tests(
            state_root, "before_mutable_record_publication_error"
        ):
            with pytest.raises(store.StoreError):
                runner.orchestrate_durable_offline_unit(plan, unit)
        assert len(_temps(state_root)) == 1
        with store._open_store(contract):
            pass
        assert _temps(state_root) == []
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with pytest.raises(store.StoreError) as caught:
            runner.orchestrate_durable_offline_unit(plan, unit)
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, "T", caught.value)
    assert len(_temps(state_root)) == 1
    reopened = _safe_durable_call(plan, unit)
    assert reopened.action == "completed"
    assert reopened.provider_call_count == 0
    assert _temps(state_root) == []


def test_public_first_contract_publication_fault_cleanup_precedes_state_decision(
    state_root, frozen_plan_and_contract
):
    plan = frozen_plan_and_contract.plan
    point = "before_atomic_publication_error"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with pytest.raises(store.StoreError) as caught:
            runner.durable_progress(plan)
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, "T", caught.value)
    assert not (state_root / "run_contract.json").exists()
    assert len(_temps(state_root)) == 1
    progress = runner.durable_progress(plan)
    assert progress.total_successful_units == 0
    assert (state_root / "run_contract.json").is_file()
    assert _temps(state_root) == []


def test_public_contract_temp_cleanup_fault_blocks_before_contract_loading(
    state_root, frozen_plan_and_contract
):
    plan = frozen_plan_and_contract.plan
    target = state_root / "run_contract.json"
    temporary = target.with_name(f".{target.name}.{'f' * 32}.tmp")
    temporary.write_bytes(b"synthetic contract temp")
    point = "before_owned_temp_cleanup_error"
    with store._install_stage_b2_test_fault_controller_for_tests(
        state_root, point
    ):
        with pytest.raises(store.StoreError) as caught:
            runner.durable_progress(plan)
        observation = store._stage_b2_test_fault_observation_for_tests(point)
        _assert_vector(observation, "B", caught.value)
    assert temporary.is_file()
    assert not target.exists()
    progress = runner.durable_progress(plan)
    assert progress.total_successful_units == 0
    assert target.is_file()
    assert not temporary.exists()
