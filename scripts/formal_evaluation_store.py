"""Stage B2 durable private state for the offline formal-evaluation harness.

The module is deliberately Windows-only, fixed-root, and fake-only.  It does
not import an SDK, environment loader, production resource loader, or formal
system implementation.
"""
from __future__ import annotations

import copy
import ctypes
import hashlib
import json
import math
import os
import re
import stat
import tempfile
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping, Sequence

from formal_evaluation_inflight import (
    AuthoritativeSuccess,
    ExecutionIdentity,
    InflightJournal,
    JournalError,
    derive_execution_unit_id,
    journal_sha256,
    next_retry_journal,
    reconcile,
    recovery_decision,
    validate_authoritative_success,
    validate_execution_identity,
    validate_journal,
)
from formal_evaluation_orchestration import (
    CheckpointEvidence,
    OrchestrationError,
    OrchestrationOutcome,
    SyntheticResourceBundle,
    validate_checkpoint_evidence,
)
from formal_evaluation_transport import (
    ProductionResourceIdentity,
    TransportError,
    project_formal_result,
    resource_identity_sha256,
    sha256_text,
    validate_resource_identity,
    validate_sha256,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PRODUCTION_PRIVATE_STATE_ROOT = (
    _REPOSITORY_ROOT / "data" / "formal_eval" / "private_state"
)
_PRIVATE_STATE_ROOT = _PRODUCTION_PRIVATE_STATE_ROOT
_PREFIX_LOCK_CONTEXT = threading.local()
_PLAN_FINGERPRINT = (
    "4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ATTEMPT_ID_RE = re.compile(r"^attempt_[0-9a-f]{64}$")
_ARCHIVE_NAME_RE = re.compile(
    r"^(?P<attempt>[1-3])-(?P<sequence>[1-4])-(?P<journal>[0-9a-f]{64})\.json$"
)
_JOURNAL_NAME_RE = re.compile(r"^[0-9a-f]{64}\.json$")
_COMMIT_NAME_RE = re.compile(r"^(?:[1-9]|[1-9][0-9]|1[0-8][0-9]|190)-[0-9a-f]{64}\.json$")
_TEMP_NAME_RE = re.compile(r"^\.(?P<target>.{1,180})\.[0-9a-f]{32}\.tmp$")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_MOVEFILE_REPLACE_EXISTING = 0x1
_MOVEFILE_WRITE_THROUGH = 0x8
_WINDOWS_MAX_PATH = 260
_RUN_CONTRACT_LIMIT = 131_072
_JOURNAL_LIMIT = 524_288
_ARCHIVE_LIMIT = 524_288
_COMMIT_LIMIT = 2_097_152
_JSON_MAX_DEPTH = 16
_JSON_MAX_STRING_BYTES = 262_144
_JSON_MAX_MAPPING_MEMBERS = 128
_JSON_MAX_ARRAY_MEMBERS = 256

_STORE_CATEGORIES = frozenset(
    {
        "STORE_PLATFORM_UNSUPPORTED",
        "STORE_LOCK_FILE_INVALID",
        "STORE_LOCK_BUSY",
        "STORE_PATH_INVALID",
        "STORE_DURABILITY_UNAVAILABLE",
        "STORE_IO_FAILURE",
        "STORE_JSON_LIMIT_EXCEEDED",
        "STORE_JSON_INVALID",
        "STORE_NONCANONICAL_JSON",
        "STORE_SCHEMA_INVALID",
        "STORE_STATE_WITHOUT_CONTRACT",
        "STORE_RUN_CONTRACT_MISMATCH",
        "STORE_FIXED_AUTHORITY_MISMATCH",
        "STORE_HASH_MISMATCH",
        "STORE_ARCHIVE_CHAIN_INVALID",
        "STORE_PREDECESSOR_INVALID",
        "STORE_COMMIT_INVALID",
        "STORE_COMMIT_JOURNAL_CONFLICT",
        "STORE_COMMITTED_WITHOUT_PRIVATE_COMMIT",
        "STORE_CONFLICTING_FIRST_SUCCESS",
        "STORE_DEPENDENCY_INVALID",
        "STORE_TEST_FAULT_INVALID",
    }
)


class StoreError(RuntimeError):
    """A closed, sanitized Stage B2 failure category."""

    def __init__(self, category: str):
        if type(category) is not str or category not in _STORE_CATEGORIES:
            raise ValueError("invalid StoreError category")
        self.category = category
        super().__init__(category)


def _require_exact_int(value: object, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError("invalid integer")
    return value


def _require_sha(value: object) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ValueError("invalid sha256")
    return value


@dataclass(frozen=True, slots=True)
class CanonicalPrivateResultV1:
    """Detached, read-only projection of one validated canonical commit."""

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

    def __post_init__(self) -> None:
        try:
            _require_exact_int(self.schema_version, 1, 1)
            _require_exact_int(self.execution_order, 1, 190)
            _require_exact_int(self.turn_index, 1, 2)
            for name in (
                "plan_fingerprint",
                "run_contract_sha256",
                "plan_member_sha256",
                "execution_unit_id",
                "request_id",
                "envelope_sha256",
                "response_sha256",
            ):
                _require_sha(getattr(self, name))
            for name in (
                "turn_one_commit_sha256",
                "checkpoint_record_sha256",
            ):
                value = getattr(self, name)
                if value is not None:
                    _require_sha(value)
            if self.plan_fingerprint != _PLAN_FINGERPRINT:
                raise ValueError
            if self.rq not in {"RQ1", "RQ2", "RQ3"}:
                raise ValueError
            for value in (
                self.case_id,
                self.system_config_id,
                self.formal_system_id,
            ):
                if (
                    type(value) is not str
                    or not value
                    or len(value.encode("utf-8")) > 262_144
                    or re.search(r"[\x00-\x1f\x7f]", value) is not None
                ):
                    raise ValueError
            if (
                type(self.response_text) is not str
                or not self.response_text
                or not self.response_text.strip()
                or len(self.response_text) > 32_768
                or re.search(r"[\x00-\x1f\x7f]", self.response_text) is not None
                or hashlib.sha256(self.response_text.encode("utf-8")).hexdigest()
                != self.response_sha256
            ):
                raise ValueError
            if self.rq != "RQ3":
                valid_relationship = (
                    self.dialogue_id is None
                    and self.turn_index == 1
                    and self.rq3_relationship_kind == "none"
                    and self.turn_one_commit_sha256 is None
                    and self.checkpoint_record_sha256 is None
                )
            elif (
                type(self.dialogue_id) is not str
                or not self.dialogue_id
                or self.dialogue_id != self.case_id
            ):
                valid_relationship = False
            elif self.rq3_relationship_kind == "single_turn":
                valid_relationship = (
                    self.turn_one_commit_sha256 is None
                    and self.checkpoint_record_sha256 is None
                )
            elif self.rq3_relationship_kind == "context_turn_one":
                valid_relationship = (
                    self.turn_index == 1
                    and self.turn_one_commit_sha256 is None
                    and self.checkpoint_record_sha256 is not None
                )
            elif self.rq3_relationship_kind == "context_turn_two":
                valid_relationship = (
                    self.turn_index == 2
                    and self.turn_one_commit_sha256 is not None
                    and self.checkpoint_record_sha256 is not None
                )
            else:
                valid_relationship = False
            if not valid_relationship:
                raise ValueError
        except (UnicodeError, ValueError) as exc:
            raise ValueError("invalid CanonicalPrivateResultV1") from exc


_RUN_STATES = frozenset(
    {"in_progress", "temporarily_blocked", "permanently_blocked", "complete"}
)


@dataclass(frozen=True)
class DurableProgress:
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

    def __post_init__(self) -> None:
        try:
            _require_exact_int(self.schema_version, 1, 1)
            if type(self.run_state) is not str or self.run_state not in _RUN_STATES:
                raise ValueError
            names = (
                "total_successful_units",
                "remaining_units",
                "initial_executable_units",
                "same_attempt_continuable_units",
                "retry_constructible_units",
                "dependency_blocked_units",
                "permanently_non_executable_units",
            )
            for name in names:
                _require_exact_int(getattr(self, name), 0, 190)
            if self.next_eligible_execution_order is not None:
                _require_exact_int(self.next_eligible_execution_order, 1, 190)
            rq_limits = {"RQ1": 102, "RQ2": 40, "RQ3": 48}
            system_limits = {
                "qa_only_reconstructed_baseline": 71,
                "v2": 71,
                "single_turn": 24,
                "context_aware": 24,
            }
            if (
                not isinstance(self.successful_by_rq, Mapping)
                or set(self.successful_by_rq) != set(rq_limits)
                or not isinstance(self.successful_by_system, Mapping)
                or set(self.successful_by_system) != set(system_limits)
            ):
                raise ValueError
            rq = dict(self.successful_by_rq)
            systems = dict(self.successful_by_system)
            for key, maximum in rq_limits.items():
                _require_exact_int(rq[key], 0, maximum)
            for key, maximum in system_limits.items():
                _require_exact_int(systems[key], 0, maximum)
            object.__setattr__(self, "successful_by_rq", MappingProxyType(rq))
            object.__setattr__(
                self, "successful_by_system", MappingProxyType(systems)
            )

            successful = self.total_successful_units
            remaining = self.remaining_units
            initial = self.initial_executable_units
            continuable = self.same_attempt_continuable_units
            retry = self.retry_constructible_units
            dependency = self.dependency_blocked_units
            permanent = self.permanently_non_executable_units
            eligible = initial + continuable + retry
            if (
                successful + remaining != 190
                or sum(rq.values()) != successful
                or sum(systems.values()) != successful
                or eligible + dependency + permanent != remaining
                or successful
                + initial
                + continuable
                + retry
                + dependency
                + permanent
                != 190
            ):
                raise ValueError
            if self.run_state == "in_progress":
                valid = (
                    successful < 190
                    and remaining > 0
                    and eligible > 0
                    and self.next_eligible_execution_order is not None
                )
            elif self.run_state == "temporarily_blocked":
                valid = (
                    successful < 190
                    and remaining > 0
                    and eligible == 0
                    and permanent == 0
                    and dependency == remaining
                    and self.next_eligible_execution_order is None
                )
            elif self.run_state == "permanently_blocked":
                valid = (
                    successful < 190
                    and remaining > 0
                    and eligible == 0
                    and permanent >= 1
                    and dependency + permanent == remaining
                    and self.next_eligible_execution_order is None
                )
            else:
                valid = (
                    successful == 190
                    and remaining == 0
                    and eligible == 0
                    and dependency == 0
                    and permanent == 0
                    and self.next_eligible_execution_order is None
                )
            if not valid:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid DurableProgress") from exc


_ACTIONS = frozenset(
    {
        "advanced",
        "completed",
        "retry_constructed",
        "dependency_blocked",
        "permanently_non_executable",
        "no_eligible",
        "run_complete",
    }
)
_DIRECT_BLOCKS = frozenset(
    {
        "call_started",
        "provider_returned_without_commit",
        "uncertain",
        "terminal_failed",
        "attempts_exhausted",
    }
)


@dataclass(frozen=True)
class DurableExecutionOutcome:
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

    def __post_init__(self) -> None:
        try:
            _require_exact_int(self.schema_version, 1, 1)
            if type(self.action) is not str or self.action not in _ACTIONS:
                raise ValueError
            if type(self.progress) is not DurableProgress:
                raise ValueError
            _require_exact_int(self.provider_call_count, 0, 1)
            if self.execution_unit_id is not None:
                _require_sha(self.execution_unit_id)
            if self.execution_order is not None:
                _require_exact_int(self.execution_order, 1, 190)
            if self.attempt_number is not None:
                _require_exact_int(self.attempt_number, 1, 3)
            if self.journal_state is not None and self.journal_state not in {
                "prepared",
                "call_started",
                "provider_returned",
                "retryable_failed",
                "terminal_failed",
                "uncertain",
                "committed",
            }:
                raise ValueError
            if self.private_commit_sha256 is not None:
                _require_sha(self.private_commit_sha256)
            if self.orchestration_outcome is not None and type(
                self.orchestration_outcome
            ) is not OrchestrationOutcome:
                raise ValueError
            unit_identity = (
                self.execution_unit_id is not None
                and self.execution_order is not None
            )
            if self.action == "advanced":
                valid = (
                    unit_identity
                    and self.attempt_number in {1, 2}
                    and self.journal_state == "retryable_failed"
                    and self.private_commit_sha256 is None
                    and self.block_category is None
                    and self.orchestration_outcome is not None
                    and self.provider_call_count
                    == self.orchestration_outcome.provider_call_count
                )
            elif self.action == "completed":
                new_local = (
                    self.orchestration_outcome is not None
                    and self.orchestration_outcome.action == "local_success"
                    and self.orchestration_outcome.provider_call_count == 0
                    and self.provider_call_count == 0
                    and self.journal_state == "prepared"
                )
                new_provider = (
                    self.orchestration_outcome is not None
                    and self.orchestration_outcome.action == "success"
                    and self.orchestration_outcome.provider_call_count == 1
                    and self.provider_call_count == 1
                    and self.journal_state == "committed"
                )
                reopened = (
                    self.orchestration_outcome is None
                    and self.provider_call_count == 0
                    and self.journal_state in {"prepared", "committed"}
                )
                valid = (
                    unit_identity
                    and self.attempt_number is not None
                    and self.journal_state in {"prepared", "committed"}
                    and self.private_commit_sha256 is not None
                    and self.block_category is None
                    and (new_local or new_provider or reopened)
                )
            elif self.action == "retry_constructed":
                valid = (
                    unit_identity
                    and self.attempt_number in {2, 3}
                    and self.journal_state == "prepared"
                    and self.private_commit_sha256 is None
                    and self.block_category is None
                    and self.orchestration_outcome is None
                    and self.provider_call_count == 0
                )
            elif self.action == "dependency_blocked":
                valid = (
                    unit_identity
                    and self.attempt_number is None
                    and self.journal_state is None
                    and self.private_commit_sha256 is None
                    and self.block_category == "dependency_missing"
                    and self.orchestration_outcome is None
                    and self.provider_call_count == 0
                )
            elif self.action == "permanently_non_executable":
                dependency_permanent = self.block_category == "dependency_permanent"
                valid = (
                    unit_identity
                    and self.private_commit_sha256 is None
                    and self.orchestration_outcome is None
                    and self.provider_call_count == 0
                    and (
                        (
                            dependency_permanent
                            and self.attempt_number is None
                            and self.journal_state is None
                        )
                        or (
                            self.block_category in _DIRECT_BLOCKS
                            and self.attempt_number is not None
                            and self.journal_state is not None
                        )
                    )
                )
            elif self.action == "no_eligible":
                valid = (
                    self.progress.run_state
                    in {"temporarily_blocked", "permanently_blocked"}
                    and not unit_identity
                    and self.execution_unit_id is None
                    and self.execution_order is None
                    and self.attempt_number is None
                    and self.journal_state is None
                    and self.private_commit_sha256 is None
                    and self.block_category is None
                    and self.orchestration_outcome is None
                    and self.provider_call_count == 0
                )
            else:
                valid = (
                    self.progress.run_state == "complete"
                    and self.execution_unit_id is None
                    and self.execution_order is None
                    and self.attempt_number is None
                    and self.journal_state is None
                    and self.private_commit_sha256 is None
                    and self.block_category is None
                    and self.orchestration_outcome is None
                    and self.provider_call_count == 0
                )
            if not valid:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid DurableExecutionOutcome") from exc


@dataclass(frozen=True)
class DurablePrefixOutcome:
    """Aggregate result of one contiguous-prefix invocation."""

    schema_version: int
    action: str
    new_successes: int
    block_category: str | None
    progress: DurableProgress

    def __post_init__(self) -> None:
        valid_actions = {"ready", "prefix_paused", "blocked", "run_complete"}
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or self.action not in valid_actions
            or type(self.new_successes) is not int
            or not 0 <= self.new_successes <= 190
            or type(self.progress) is not DurableProgress
            or (
                self.block_category is not None
                and (
                    type(self.block_category) is not str
                    or not self.block_category
                    or len(self.block_category) > 64
                )
            )
            or (self.action == "blocked") != (self.block_category is not None)
            or (self.action == "run_complete")
            != (self.progress.run_state == "complete")
            or (
                self.action in {"ready", "prefix_paused"}
                and self.progress.run_state != "in_progress"
            )
            or (self.action == "ready" and self.new_successes != 0)
        ):
            raise ValueError("invalid DurablePrefixOutcome")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StoreError("STORE_JSON_INVALID")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    raise StoreError("STORE_JSON_INVALID")


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc


def _domain_sha(domain: str, member: str, value: object) -> str:
    return hashlib.sha256(
        _canonical_bytes({"domain": domain, member: value})
    ).hexdigest()


def _recursive_limits(value: object, depth: int = 1) -> None:
    if depth > _JSON_MAX_DEPTH:
        raise StoreError("STORE_JSON_LIMIT_EXCEEDED")
    if type(value) is str:
        if len(value.encode("utf-8")) > _JSON_MAX_STRING_BYTES:
            raise StoreError("STORE_JSON_LIMIT_EXCEEDED")
    elif type(value) is dict:
        if len(value) > _JSON_MAX_MAPPING_MEMBERS:
            raise StoreError("STORE_JSON_LIMIT_EXCEEDED")
        for key, item in value.items():
            if type(key) is not str:
                raise StoreError("STORE_JSON_INVALID")
            if len(key.encode("utf-8")) > _JSON_MAX_STRING_BYTES:
                raise StoreError("STORE_JSON_LIMIT_EXCEEDED")
            _recursive_limits(item, depth + 1)
    elif type(value) is list:
        if len(value) > _JSON_MAX_ARRAY_MEMBERS:
            raise StoreError("STORE_JSON_LIMIT_EXCEEDED")
        for item in value:
            _recursive_limits(item, depth + 1)
    elif value is None or type(value) in {bool, int}:
        return
    elif type(value) is float:
        if not math.isfinite(value):
            raise StoreError("STORE_JSON_INVALID")
    else:
        raise StoreError("STORE_JSON_INVALID")


def _load_json_bytes(raw: bytes, maximum: int) -> dict[str, Any]:
    if len(raw) > maximum:
        raise StoreError("STORE_JSON_LIMIT_EXCEEDED")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise StoreError("STORE_JSON_INVALID") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except StoreError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise StoreError("STORE_JSON_INVALID") from exc
    if type(value) is not dict:
        raise StoreError("STORE_JSON_INVALID")
    _recursive_limits(value)
    if raw != _canonical_bytes(value) + b"\n":
        raise StoreError("STORE_NONCANONICAL_JSON")
    return value


def _os_io_path(path: Path) -> Path | str:
    """Return an extended Windows path only for the immediate I/O call."""
    if os.name != "nt":
        return path
    raw = os.fspath(path)
    if raw.startswith("\\\\?\\"):
        return raw
    if not path.is_absolute():
        return path
    absolute = os.path.abspath(raw)
    if len(absolute) < _WINDOWS_MAX_PATH:
        return path
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute


def _path_exists(path: Path) -> bool:
    io_path = _os_io_path(path)
    return path.exists() if io_path is path else os.path.exists(io_path)


def _path_is_dir(path: Path) -> bool:
    io_path = _os_io_path(path)
    return path.is_dir() if io_path is path else os.path.isdir(io_path)


def _path_is_file(path: Path) -> bool:
    io_path = _os_io_path(path)
    return path.is_file() if io_path is path else os.path.isfile(io_path)


def _path_lstat(path: Path) -> os.stat_result:
    io_path = _os_io_path(path)
    return path.lstat() if io_path is path else os.lstat(io_path)


def _path_iterdir(path: Path) -> Iterator[Path]:
    io_path = _os_io_path(path)
    if io_path is path:
        return path.iterdir()

    def entries() -> Iterator[Path]:
        with os.scandir(io_path) as directory:
            for entry in directory:
                yield path / entry.name

    return entries()


def _path_mkdir(
    path: Path, *, parents: bool = False, exist_ok: bool = False
) -> None:
    io_path = _os_io_path(path)
    if io_path is path:
        path.mkdir(parents=parents, exist_ok=exist_ok)
    elif parents:
        os.makedirs(io_path, exist_ok=exist_ok)
    else:
        try:
            os.mkdir(io_path)
        except FileExistsError:
            if not exist_ok:
                raise


def _path_open(path: Path, mode: str, *, buffering: int = -1) -> Any:
    io_path = _os_io_path(path)
    if io_path is path:
        return path.open(mode, buffering=buffering)
    return open(io_path, mode, buffering=buffering)


def _path_read_bytes(path: Path) -> bytes:
    io_path = _os_io_path(path)
    if io_path is path:
        return path.read_bytes()
    with open(io_path, "rb") as handle:
        return handle.read()


def _path_unlink(path: Path) -> None:
    io_path = _os_io_path(path)
    if io_path is path:
        path.unlink()
    else:
        os.unlink(io_path)


def _read_json(path: Path, maximum: int) -> dict[str, Any]:
    try:
        raw = _path_read_bytes(path)
    except OSError as exc:
        raise StoreError("STORE_IO_FAILURE") from exc
    return _load_json_bytes(raw, maximum)


def _is_reparse(path: Path) -> bool:
    try:
        info = _path_lstat(path)
    except OSError as exc:
        raise StoreError("STORE_PATH_INVALID") from exc
    attributes = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attributes & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _validate_root(root: Path) -> Path:
    if not isinstance(root, Path) or not root.is_absolute():
        raise StoreError("STORE_PATH_INVALID")
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current = current / part
        if _path_exists(current) and _is_reparse(current):
            raise StoreError("STORE_PATH_INVALID")
    return root


def _ensure_fixed_directories(root: Path) -> None:
    _validate_root(root)
    for path in (root, root / "journals", root / "attempts", root / "commits"):
        if _path_exists(path):
            if _is_reparse(path) or not _path_is_dir(path):
                raise StoreError("STORE_PATH_INVALID")
            continue
        try:
            _path_mkdir(path)
        except FileExistsError:
            if _is_reparse(path) or not _path_is_dir(path):
                raise StoreError("STORE_PATH_INVALID")
        except OSError as exc:
            raise StoreError("STORE_IO_FAILURE") from exc
        if _is_reparse(path) or not _path_is_dir(path):
            raise StoreError("STORE_PATH_INVALID")


_LEASED_PATHS: set[str] = set()
_LEASED_PATHS_GUARD = threading.Lock()


class _RunWideLock:
    def __init__(self, root: Path, *, create_missing: bool = True):
        if type(create_missing) is not bool:
            raise StoreError("STORE_PATH_INVALID")
        self.root = _validate_root(root)
        self.create_missing = create_missing
        self.path = self.root / "run.lock"
        self.handle: Any = None
        self.locked = False
        self.pid: int | None = None
        self.thread_id: int | None = None
        self._registry_key: str | None = None

    def __enter__(self) -> "_RunWideLock":
        if os.name != "nt":
            raise StoreError("STORE_PLATFORM_UNSUPPORTED")
        try:
            import msvcrt
        except ImportError as exc:
            raise StoreError("STORE_PLATFORM_UNSUPPORTED") from exc
        _validate_root(self.root)
        if not _path_exists(self.root):
            if not self.create_missing:
                raise StoreError("STORE_PATH_INVALID")
            try:
                _path_mkdir(self.root, parents=True)
            except OSError as exc:
                raise StoreError("STORE_IO_FAILURE") from exc
        if _is_reparse(self.root) or not _path_is_dir(self.root):
            raise StoreError("STORE_PATH_INVALID")
        if not _path_exists(self.path):
            if not self.create_missing:
                raise StoreError("STORE_LOCK_FILE_INVALID")
            try:
                descriptor = os.open(
                    _os_io_path(self.path),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY,
                )
                try:
                    if os.write(descriptor, b"\x00") != 1:
                        raise StoreError("STORE_IO_FAILURE")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except FileExistsError:
                pass
            except StoreError:
                raise
            except OSError as exc:
                raise StoreError("STORE_IO_FAILURE") from exc
        if _is_reparse(self.path) or not _path_is_file(self.path):
            raise StoreError("STORE_LOCK_FILE_INVALID")
        try:
            self.handle = _path_open(self.path, "r+b", buffering=0)
        except OSError as exc:
            if self.handle is not None:
                self.handle.close()
            raise StoreError("STORE_LOCK_FILE_INVALID") from exc
        key = str(self.path).casefold()
        with _LEASED_PATHS_GUARD:
            if key in _LEASED_PATHS:
                self.handle.close()
                self.handle = None
                raise StoreError("STORE_LOCK_BUSY")
            _LEASED_PATHS.add(key)
            self._registry_key = key
        deadline = time.monotonic() + 5.0
        try:
            while True:
                try:
                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
                    self.locked = True
                    break
                except OSError as exc:
                    if time.monotonic() >= deadline:
                        raise StoreError("STORE_LOCK_BUSY") from exc
                    time.sleep(0.05)
            self.pid = os.getpid()
            self.thread_id = threading.get_ident()
            self.handle.seek(0)
            if self.handle.read(2) != b"\x00" or _is_reparse(self.path):
                raise StoreError("STORE_LOCK_FILE_INVALID")
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        try:
            if self.handle is not None and self.locked:
                try:
                    import msvcrt

                    self.handle.seek(0)
                    msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
                finally:
                    self.locked = False
            if self.handle is not None:
                self.handle.close()
                self.handle = None
        finally:
            if self._registry_key is not None:
                with _LEASED_PATHS_GUARD:
                    _LEASED_PATHS.discard(self._registry_key)
                self._registry_key = None

    def require_active(self) -> None:
        if (
            type(self) is not _RunWideLock
            or not self.locked
            or self.handle is None
            or self.pid != os.getpid()
            or self.thread_id != threading.get_ident()
            or self.root != _PRIVATE_STATE_ROOT
        ):
            raise StoreError("STORE_LOCK_BUSY")


def _move_file_ex(source: Path, target: Path, replace: bool) -> None:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        function = kernel32.MoveFileExW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        function.restype = ctypes.c_int
    except (AttributeError, OSError) as exc:
        raise StoreError("STORE_DURABILITY_UNAVAILABLE") from exc
    flags = _MOVEFILE_WRITE_THROUGH | (
        _MOVEFILE_REPLACE_EXISTING if replace else 0
    )
    if not function(
        os.fspath(_os_io_path(source)),
        os.fspath(_os_io_path(target)),
        flags,
    ):
        error = ctypes.get_last_error()
        if not replace and error in {80, 183}:
            raise FileExistsError(str(target))
        raise StoreError("STORE_IO_FAILURE")


def _atomic_target_kind(path: Path) -> str:
    root = _PRIVATE_STATE_ROOT
    if path == root / "run_contract.json":
        return "run_contract"
    if path.parent == root / "journals" and _JOURNAL_NAME_RE.fullmatch(
        path.name
    ):
        return "mutable"
    if path.parent == root / "commits" and _COMMIT_NAME_RE.fullmatch(
        path.name
    ):
        return "commit"
    if (
        path.parent.parent == root / "attempts"
        and _SHA256_RE.fullmatch(path.parent.name)
        and _ARCHIVE_NAME_RE.fullmatch(path.name)
    ):
        return "archive"
    raise StoreError("STORE_PATH_INVALID")


def _owned_temp_kind(path: Path) -> str | None:
    match = _TEMP_NAME_RE.fullmatch(path.name)
    if match is None:
        return None
    try:
        return _atomic_target_kind(path.with_name(match.group("target")))
    except StoreError:
        return None


def _active_fault_point() -> str | None:
    controller = _STAGE_B2_TEST_FAULT_CONTROLLER
    if controller is None:
        return None
    with _FAULT_STATE_GUARD:
        active, _state = _require_fault_owner_locked()
        return active.fault_point


def _write_all_once(handle: Any, value: bytes) -> None:
    try:
        written = handle.write(value)
    except OSError as exc:
        raise StoreError("STORE_IO_FAILURE") from exc
    if written != len(value):
        raise StoreError("STORE_IO_FAILURE")


def _open_tracked(path: Path, mode: str, family: str) -> Any:
    try:
        handle = _path_open(path, mode, buffering=0)
    except (FileExistsError, OSError):
        raise
    _fault_handle_opened(family, handle)
    return handle


def _raise_close_secondary() -> None:
    try:
        raise StoreError("STORE_IO_FAILURE")
    except BaseException:
        raise


def _close_tracked(
    handle: Any,
    family: str,
    *,
    normal_temp_close_hook: bool = False,
    secondary_close_fault: bool = False,
) -> None:
    _fault_handle_close_attempt(family, handle)
    close_primary = (
        normal_temp_close_hook
        and _consume_fault("during_atomic_temp_close_error")
    )
    try:
        handle.close()
    except OSError as exc:
        raise StoreError("STORE_IO_FAILURE") from exc
    if close_primary:
        _raise_new_fault_primary()
    if secondary_close_fault:
        _raise_close_secondary()


def _record_primary_if_active(primary: BaseException) -> None:
    if _STAGE_B2_TEST_FAULT_CONTROLLER is None or type(primary) is not StoreError:
        return
    with _FAULT_STATE_GUARD:
        _controller, state = _require_fault_owner_locked()
        if state["trigger_count"] != 1:
            return
    _record_fault_exception("primary", primary)


def _close_during_primary(
    handle: Any,
    family: str,
    primary: BaseException,
    *,
    inject_secondary: bool,
) -> None:
    _record_primary_if_active(primary)
    try:
        _close_tracked(
            handle,
            family,
            secondary_close_fault=inject_secondary,
        )
    except BaseException as secondary:
        if inject_secondary:
            _record_fault_exception("secondary", secondary)
    if _STAGE_B2_TEST_FAULT_CONTROLLER is not None and type(primary) is StoreError:
        with _FAULT_STATE_GUARD:
            _controller, state = _require_fault_owner_locked()
            group = state["exception_groups"].get("primary")
        if group is not None and group[0] == id(primary):
            _refresh_fault_exception_traceback("primary", primary)


def _validate_published_bytes(
    raw: bytes,
    value: Mapping[str, Any],
    maximum: int,
) -> None:
    loaded = _load_json_bytes(raw, maximum)
    if loaded != dict(value) or raw != _canonical_bytes(value) + b"\n":
        raise StoreError("STORE_HASH_MISMATCH")


def _read_and_validate_recovery(
    path: Path,
    value: Mapping[str, Any],
    maximum: int,
    *,
    mode: str,
) -> None:
    _fault_increment("recovery_readback_attempt_count")
    try:
        handle = _open_tracked(path, "rb", "recovery")
    except OSError as exc:
        raise StoreError("STORE_IO_FAILURE") from exc
    close_attempted = False
    try:
        if mode in {"read_error", "read_close_error"}:
            _raise_new_fault_primary()
        try:
            raw = handle.read()
        except OSError as exc:
            raise StoreError("STORE_IO_FAILURE") from exc
        validation_raw = (
            raw[:-1]
            if mode in {"invalid_bytes", "validation_close_error"}
            else raw
        )
        _validate_published_bytes(validation_raw, value, maximum)
        close_attempted = True
        _close_tracked(handle, "recovery")
    except BaseException as primary:
        _record_primary_if_active(primary)
        if not close_attempted:
            close_attempted = True
            _close_during_primary(
                handle,
                "recovery",
                primary,
                inject_secondary=mode
                in {"read_close_error", "validation_close_error"},
            )
        if _STAGE_B2_TEST_FAULT_CONTROLLER is not None and type(primary) is StoreError:
            _refresh_fault_exception_traceback("primary", primary)
        raise


def _post_publication_readback(
    path: Path,
    value: Mapping[str, Any],
    maximum: int,
) -> None:
    _fault_increment("initial_verification_readback_attempt_count")
    point = _active_fault_point()
    if point == "after_atomic_publication_before_readback_error" and _consume_fault(
        point
    ):
        try:
            raise StoreError("STORE_IO_FAILURE")
        except BaseException as initial:
            _record_fault_exception("initial", initial)
        _read_and_validate_recovery(
            path,
            value,
            maximum,
            mode="success",
        )
        return

    try:
        handle = _open_tracked(path, "rb", "initial")
    except OSError as exc:
        raise StoreError("STORE_IO_FAILURE") from exc
    injected = point in {
        "during_atomic_publication_readback_error",
        "during_atomic_publication_recovery_readback_error",
        "during_atomic_publication_recovery_invalid_bytes",
        "during_atomic_publication_readback_then_close_error",
        "during_atomic_publication_recovery_readback_then_close_error",
        "during_atomic_publication_recovery_validation_then_close_error",
    } and _consume_fault(point)
    if injected:
        try:
            raise StoreError("STORE_IO_FAILURE")
        except BaseException as initial:
            if point == "during_atomic_publication_readback_then_close_error":
                _record_fault_exception("primary", initial)
                try:
                    _close_tracked(
                        handle,
                        "initial",
                        secondary_close_fault=True,
                    )
                except BaseException as secondary:
                    _record_fault_exception("secondary", secondary)
                _refresh_fault_exception_traceback("primary", initial)
                raise
            try:
                _close_tracked(handle, "initial")
            except BaseException:
                _record_fault_exception("primary", initial)
                _refresh_fault_exception_traceback("primary", initial)
                raise
            _record_fault_exception("initial", initial)
        recovery_mode = {
            "during_atomic_publication_readback_error": "success",
            "during_atomic_publication_recovery_readback_error": "read_error",
            "during_atomic_publication_recovery_invalid_bytes": "invalid_bytes",
            "during_atomic_publication_recovery_readback_then_close_error": "read_close_error",
            "during_atomic_publication_recovery_validation_then_close_error": "validation_close_error",
        }[point]
        _read_and_validate_recovery(
            path,
            value,
            maximum,
            mode=recovery_mode,
        )
        return

    close_attempted = False
    try:
        try:
            raw = handle.read()
        except OSError as exc:
            raise StoreError("STORE_IO_FAILURE") from exc
        _validate_published_bytes(raw, value, maximum)
        close_attempted = True
        _close_tracked(handle, "initial")
    except BaseException as primary:
        if not close_attempted:
            close_attempted = True
            _close_during_primary(
                handle,
                "initial",
                primary,
                inject_secondary=False,
            )
        raise


def _trigger_target_specific_publication_fault(
    kind: str,
    value: Mapping[str, Any],
) -> None:
    _raise_if_fault("before_atomic_publication_error")
    if kind == "mutable":
        _raise_if_fault("before_mutable_record_publication_error")
    elif kind == "commit":
        _raise_if_fault("before_private_commit_publication_error")
    elif kind == "archive" and (
        value.get("sequence_number") == 3
        and value.get("event")
        in {"provider_returned", "retryable_failed", "terminal_failed", "uncertain"}
    ):
        _raise_if_fault("before_post_call_archive_publication_error")


def _trigger_compound_temp_fault(kind: str, phase: str) -> None:
    if _active_fault_point() != "during_atomic_temp_failure_then_close_error":
        return
    expected_phase = {
        "run_contract": "partial_write",
        "archive": "before_flush",
        "commit": "before_fsync",
        "mutable": "before_close",
    }[kind]
    if phase == expected_phase and _consume_fault(
        "during_atomic_temp_failure_then_close_error"
    ):
        _raise_new_fault_primary()


def _atomic_publish_json(
    path: Path,
    value: Mapping[str, Any],
    *,
    replace: bool,
    maximum: int,
) -> bool:
    raw = _canonical_bytes(value) + b"\n"
    if len(raw) > maximum:
        raise StoreError("STORE_JSON_LIMIT_EXCEEDED")
    if _is_reparse(path.parent) or not _path_is_dir(path.parent):
        raise StoreError("STORE_PATH_INVALID")
    kind = _atomic_target_kind(path)
    name = f".{path.name}.{os.urandom(16).hex()}.tmp"
    if len(name) > 255 or _TEMP_NAME_RE.fullmatch(name) is None:
        raise StoreError("STORE_PATH_INVALID")
    temporary = path.parent / name
    handle: Any = None
    close_attempted = False
    published = False
    try:
        _raise_if_fault("before_atomic_temp_create_error")
        handle = _open_tracked(temporary, "xb", "temporary")
        prefix_length = len(raw) // 2
        _write_all_once(handle, raw[:prefix_length])
        _trigger_compound_temp_fault(kind, "partial_write")
        _raise_if_fault("after_atomic_temp_partial_write_error")
        _write_all_once(handle, raw[prefix_length:])
        _trigger_compound_temp_fault(kind, "before_flush")
        _raise_if_fault("before_atomic_temp_flush_error")
        try:
            handle.flush()
        except OSError as exc:
            raise StoreError("STORE_IO_FAILURE") from exc
        _trigger_compound_temp_fault(kind, "before_fsync")
        _raise_if_fault("before_atomic_temp_fsync_error")
        try:
            os.fsync(handle.fileno())
        except OSError as exc:
            raise StoreError("STORE_IO_FAILURE") from exc
        _trigger_compound_temp_fault(kind, "before_close")
        close_attempted = True
        _close_tracked(
            handle,
            "temporary",
            normal_temp_close_hook=True,
        )
        handle = None
        try:
            _trigger_target_specific_publication_fault(kind, value)
            _fault_increment("publication_attempt_count")
            _move_file_ex(temporary, path, replace)
            published = True
            _fault_increment("successful_publication_count")
        except FileExistsError:
            published = False
        if published:
            _post_publication_readback(path, value, maximum)
        else:
            existing = _read_json(path, maximum)
            if existing != dict(value):
                return False
            try:
                _path_unlink(temporary)
            except OSError as exc:
                raise StoreError("STORE_IO_FAILURE") from exc
        return published
    except BaseException as primary:
        inject_secondary = (
            _active_fault_point()
            == "during_atomic_temp_failure_then_close_error"
            and _STAGE_B2_TEST_FAULT_CONTROLLER is not None
        )
        if handle is not None and not close_attempted:
            close_attempted = True
            _close_during_primary(
                handle,
                "temporary",
                primary,
                inject_secondary=inject_secondary,
            )
        if type(primary) is StoreError:
            raise
        if isinstance(primary, (OSError, UnicodeError, ValueError)):
            raise StoreError("STORE_IO_FAILURE") from primary
        raise
    except OSError as exc:
        raise StoreError("STORE_IO_FAILURE") from exc


def _clean_owned_temps_locked(root: Path, lock: _RunWideLock) -> None:
    lock.require_active()
    for directory in (
        root,
        root / "journals",
        root / "commits",
        root / "attempts",
    ):
        if not _path_exists(directory):
            continue
        for path in sorted(_path_iterdir(directory), key=lambda item: item.name):
            if _path_is_file(path) and path.name.startswith("."):
                if (
                    _TEMP_NAME_RE.fullmatch(path.name) is None
                    or _is_reparse(path)
                    or not _path_is_file(path)
                    or _atomic_target_kind(path.with_name(
                        _TEMP_NAME_RE.fullmatch(path.name).group("target")
                    ))
                    not in {"run_contract", "mutable", "commit"}
                ):
                    raise StoreError("STORE_PATH_INVALID")
                try:
                    _raise_if_fault("before_owned_temp_cleanup_error")
                    _path_unlink(path)
                except OSError as exc:
                    raise StoreError("STORE_IO_FAILURE") from exc
        if directory == root / "attempts":
            for child in sorted(
                _path_iterdir(directory), key=lambda item: item.name
            ):
                if (
                    _SHA256_RE.fullmatch(child.name) is None
                    or _is_reparse(child)
                    or not _path_is_dir(child)
                ):
                    raise StoreError("STORE_PATH_INVALID")
                for path in sorted(
                    _path_iterdir(child), key=lambda item: item.name
                ):
                    if _path_is_file(path) and path.name.startswith("."):
                        match = _TEMP_NAME_RE.fullmatch(path.name)
                        if (
                            match is None
                            or _is_reparse(path)
                            or not _path_is_file(path)
                            or _atomic_target_kind(
                                path.with_name(match.group("target"))
                            )
                            != "archive"
                        ):
                            raise StoreError("STORE_PATH_INVALID")
                        try:
                            _raise_if_fault("before_owned_temp_cleanup_error")
                            _path_unlink(path)
                        except OSError as exc:
                            raise StoreError("STORE_IO_FAILURE") from exc


def _validate_run_contract_shape(value: Mapping[str, Any]) -> None:
    if type(value) is not dict or list(value) != sorted(value):
        # Parsed canonical mappings retain sorted key order.
        raise StoreError("STORE_SCHEMA_INVALID")
    expected = {
        "schema_version",
        "stage_id",
        "plan_authority",
        "frozen_input_sha256",
        "formal_system_authority",
        "provider_generation_authority",
        "runtime_resource_authority",
        "schema_authority",
        "run_contract_sha256",
    }
    if set(value) != expected:
        raise StoreError("STORE_SCHEMA_INVALID")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise StoreError("STORE_SCHEMA_INVALID")
    if value["stage_id"] not in {"B2", "B5"}:
        raise StoreError("STORE_SCHEMA_INVALID")
    if value["stage_id"] == "B5":
        provider = value.get("provider_generation_authority")
        runtime = value.get("runtime_resource_authority")
        if (
            type(provider) is not dict
            or set(provider) != {"generation", "transport", "real_execution"}
            or type(provider.get("real_execution")) is not dict
            or provider["real_execution"].get("mode") != "production_real"
            or type(runtime) is not dict
            or set(runtime)
            != {
                "b4_preflight",
                "implementation_files",
                "repository",
                "resources",
                "runtime_identity_sha256",
                "transport_implementation_sha256",
            }
            or type(runtime.get("resources")) is not dict
            or set(runtime["resources"])
            != {
                "qa_only_reconstructed_baseline",
                "v2",
                "single_turn",
                "context_aware",
            }
        ):
            raise StoreError("STORE_SCHEMA_INVALID")
        try:
            for wrapper in runtime["resources"].values():
                resource = ProductionResourceIdentity.from_mapping(
                    wrapper["resource_identity"]
                )
                validate_resource_identity(resource)
                if (
                    resource.synthetic
                    or resource.resource_type != "production_frozen"
                    or wrapper["resource_identity_sha256"]
                    != resource_identity_sha256(resource)
                ):
                    raise StoreError("STORE_SCHEMA_INVALID")
        except StoreError:
            raise
        except (KeyError, TypeError, TransportError) as exc:
            raise StoreError("STORE_SCHEMA_INVALID") from exc
    try:
        _require_sha(value["run_contract_sha256"])
    except ValueError as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc
    without_hash = dict(value)
    del without_hash["run_contract_sha256"]
    expected_hash = _domain_sha(
        "formal-evaluation-run-contract-v1",
        "contract",
        without_hash,
    )
    if value["run_contract_sha256"] != expected_hash:
        raise StoreError("STORE_HASH_MISMATCH")


def _durable_state_exists_without_contract(root: Path) -> bool:
    allowed_empty_directories = {"journals", "attempts", "commits"}
    for path in _path_iterdir(root):
        if path.name == "run.lock":
            continue
        if path.name in allowed_empty_directories and _path_is_dir(path):
            if any(_path_iterdir(path)):
                return True
            continue
        return True
    return False


def _open_contract_locked(
    expected: Mapping[str, Any], lock: _RunWideLock
) -> dict[str, Any]:
    lock.require_active()
    root = lock.root
    contract_path = root / "run_contract.json"
    if not _path_exists(contract_path):
        _clean_owned_temps_locked(root, lock)
        if _durable_state_exists_without_contract(root):
            raise StoreError("STORE_STATE_WITHOUT_CONTRACT")
        _ensure_fixed_directories(root)
        _atomic_publish_json(
            contract_path,
            expected,
            replace=False,
            maximum=_RUN_CONTRACT_LIMIT,
        )
    loaded = _read_json(contract_path, _RUN_CONTRACT_LIMIT)
    _validate_run_contract_shape(loaded)
    if loaded != dict(expected) or _path_read_bytes(contract_path) != (
        _canonical_bytes(expected) + b"\n"
    ):
        raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
    return loaded


@dataclass(frozen=True)
class _StageB2TestFaultControllerV1:
    schema_version: int
    root: Path
    fault_point: str

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or not isinstance(self.root, Path)
            or type(self.fault_point) is not str
            or self.fault_point not in _FAULT_POINTS
        ):
            raise StoreError("STORE_TEST_FAULT_INVALID")


_FAULT_POINTS = frozenset(
    {
        "after_call_started_published_exit",
        "after_fake_client_returned_mark",
        "after_fake_client_returned_exit",
        "after_private_commit_published_exit",
        "after_committed_archive_published_exit",
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
    }
)
_STAGE_B2_TEST_FAULT_CONTROLLER: _StageB2TestFaultControllerV1 | None = None
_ACTIVE_FAULT_CONTEXT: dict[str, Any] | None = None
_FAULT_STATE_GUARD = threading.RLock()
_FAULT_STATE: dict[str, Any] | None = None


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


_FAULT_COUNT_NAMES = (
    "trigger_count",
    "publication_attempt_count",
    "successful_publication_count",
    "initial_verification_readback_attempt_count",
    "recovery_readback_attempt_count",
    "atomic_temp_close_attempt_count",
    "initial_verification_handle_close_attempt_count",
    "recovery_readback_handle_close_attempt_count",
)
_FAULT_HANDLE_NAMES = (
    "temporary_opened_handle_ids",
    "temporary_close_attempt_handle_ids",
    "initial_verification_opened_handle_ids",
    "initial_verification_close_attempt_handle_ids",
    "recovery_opened_handle_ids",
    "recovery_close_attempt_handle_ids",
)
_FAULT_EXCEPTION_ROLES = ("initial", "primary", "secondary")


def _new_fault_state(
    controller: _StageB2TestFaultControllerV1,
) -> dict[str, Any]:
    state: dict[str, Any] = {
        "controller": controller,
        "controller_root": os.path.normcase(
            str(controller.root.resolve(strict=True))
        ),
        "owner_pid": os.getpid(),
        "owner_thread_id": threading.get_ident(),
        "strong_references": [controller],
        "exception_groups": {name: None for name in _FAULT_EXCEPTION_ROLES},
    }
    state.update({name: 0 for name in _FAULT_COUNT_NAMES})
    state.update({name: [] for name in _FAULT_HANDLE_NAMES})
    return state


def _require_fault_owner_locked() -> tuple[
    _StageB2TestFaultControllerV1, dict[str, Any]
]:
    controller = _STAGE_B2_TEST_FAULT_CONTROLLER
    state = _FAULT_STATE
    if (
        type(controller) is not _StageB2TestFaultControllerV1
        or type(state) is not dict
        or state.get("controller") is not controller
        or state.get("owner_pid") != os.getpid()
        or state.get("owner_thread_id") != threading.get_ident()
        or state.get("controller_root")
        != os.path.normcase(str(controller.root.resolve(strict=True)))
    ):
        raise StoreError("STORE_TEST_FAULT_INVALID")
    return controller, state


def _traceback_ids(error: BaseException) -> tuple[int, ...]:
    result: list[int] = []
    current = error.__traceback__
    while current is not None:
        result.append(id(current))
        current = current.tb_next
    if not result:
        raise StoreError("STORE_TEST_FAULT_INVALID")
    return tuple(result)


def _exception_group(error: BaseException) -> tuple[Any, ...]:
    if type(error) is not StoreError:
        raise StoreError("STORE_TEST_FAULT_INVALID")
    notes = getattr(error, "__notes__", None)
    return (
        id(error),
        "formal_evaluation_store.StoreError",
        error.category,
        tuple(error.args),
        id(error.__cause__) if error.__cause__ is not None else None,
        id(error.__context__) if error.__context__ is not None else None,
        bool(error.__suppress_context__),
        tuple(notes) if notes is not None else (),
        _traceback_ids(error),
        True,
    )


def _record_fault_exception(role: str, error: BaseException) -> None:
    with _FAULT_STATE_GUARD:
        _controller, state = _require_fault_owner_locked()
        if role not in _FAULT_EXCEPTION_ROLES:
            raise StoreError("STORE_TEST_FAULT_INVALID")
        existing = state["exception_groups"].get(role)
        if existing is not None and existing[0] != id(error):
            raise StoreError("STORE_TEST_FAULT_INVALID")
        state["strong_references"].append(error)
        state["exception_groups"][role] = _exception_group(error)


def _refresh_fault_exception_traceback(role: str, error: BaseException) -> None:
    with _FAULT_STATE_GUARD:
        _controller, state = _require_fault_owner_locked()
        existing = state["exception_groups"].get(role)
        if existing is None or existing[0] != id(error):
            raise StoreError("STORE_TEST_FAULT_INVALID")
        refreshed = list(existing)
        refreshed[8] = _traceback_ids(error)
        state["exception_groups"][role] = tuple(refreshed)


def _fault_increment(name: str) -> None:
    controller = _STAGE_B2_TEST_FAULT_CONTROLLER
    if controller is None:
        return
    with _FAULT_STATE_GUARD:
        _controller, state = _require_fault_owner_locked()
        if name not in _FAULT_COUNT_NAMES or name == "trigger_count":
            raise StoreError("STORE_TEST_FAULT_INVALID")
        state[name] += 1


def _fault_handle_opened(family: str, handle: Any) -> None:
    controller = _STAGE_B2_TEST_FAULT_CONTROLLER
    if controller is None:
        return
    field = {
        "temporary": "temporary_opened_handle_ids",
        "initial": "initial_verification_opened_handle_ids",
        "recovery": "recovery_opened_handle_ids",
    }.get(family)
    if field is None:
        raise StoreError("STORE_TEST_FAULT_INVALID")
    with _FAULT_STATE_GUARD:
        _controller, state = _require_fault_owner_locked()
        token = id(handle)
        if type(token) is not int or token <= 0:
            raise StoreError("STORE_TEST_FAULT_INVALID")
        state[field].append(token)
        state["strong_references"].append(handle)


def _fault_handle_close_attempt(family: str, handle: Any) -> None:
    controller = _STAGE_B2_TEST_FAULT_CONTROLLER
    if controller is None:
        return
    fields = {
        "temporary": (
            "temporary_close_attempt_handle_ids",
            "atomic_temp_close_attempt_count",
        ),
        "initial": (
            "initial_verification_close_attempt_handle_ids",
            "initial_verification_handle_close_attempt_count",
        ),
        "recovery": (
            "recovery_close_attempt_handle_ids",
            "recovery_readback_handle_close_attempt_count",
        ),
    }.get(family)
    if fields is None:
        raise StoreError("STORE_TEST_FAULT_INVALID")
    with _FAULT_STATE_GUARD:
        _controller, state = _require_fault_owner_locked()
        token = id(handle)
        state[fields[0]].append(token)
        state[fields[1]] += 1
        state["strong_references"].append(handle)


def _consume_fault(point: str) -> bool:
    controller = _STAGE_B2_TEST_FAULT_CONTROLLER
    if controller is None:
        return False
    if type(point) is not str or point not in _FAULT_POINTS:
        raise StoreError("STORE_TEST_FAULT_INVALID")
    with _FAULT_STATE_GUARD:
        active, state = _require_fault_owner_locked()
        if active.fault_point != point or state["trigger_count"] != 0:
            return False
        state["trigger_count"] = 1
        return True


def _raise_new_fault_primary(
    *, category: str = "STORE_IO_FAILURE", role: str = "primary"
) -> None:
    try:
        raise StoreError(category)
    except BaseException as primary:
        _record_fault_exception(role, primary)
        raise


def _stage_b2_test_fault_observation_for_tests(
    fault_point: str,
) -> _StageB2TestFaultObservationV1:
    with _FAULT_STATE_GUARD:
        controller, state = _require_fault_owner_locked()
        if type(fault_point) is not str or fault_point != controller.fault_point:
            raise StoreError("STORE_TEST_FAULT_INVALID")
        groups: list[Any] = []
        for role in _FAULT_EXCEPTION_ROLES:
            group = state["exception_groups"][role]
            groups.extend((None,) * 10 if group is None else group)
        observation = _StageB2TestFaultObservationV1(
            1,
            fault_point,
            id(controller),
            state["controller_root"],
            state["owner_pid"],
            state["owner_thread_id"],
            *(state[name] for name in _FAULT_COUNT_NAMES),
            *(tuple(state[name]) for name in _FAULT_HANDLE_NAMES),
            *groups,
        )
    _validate_fault_observation(observation)
    return observation


def _validate_fault_observation(
    value: _StageB2TestFaultObservationV1,
) -> None:
    if (
        type(value) is not _StageB2TestFaultObservationV1
        or type(value.schema_version) is not int
        or value.schema_version != 1
        or type(value.fault_point) is not str
        or value.fault_point not in _FAULT_POINTS
        or any(
            type(getattr(value, name)) is not int or getattr(value, name) < 0
            for name in _FAULT_COUNT_NAMES
        )
        or value.trigger_count not in {0, 1}
        or value.successful_publication_count
        > value.publication_attempt_count
        or value.initial_verification_readback_attempt_count
        > value.successful_publication_count
        or value.recovery_readback_attempt_count
        > value.initial_verification_readback_attempt_count
    ):
        raise StoreError("STORE_TEST_FAULT_INVALID")
    for name in _FAULT_HANDLE_NAMES:
        item = getattr(value, name)
        if type(item) is not tuple or any(
            type(token) is not int or token <= 0 for token in item
        ):
            raise StoreError("STORE_TEST_FAULT_INVALID")
    if (
        type(value.controller_identity) is not int
        or value.controller_identity <= 0
        or type(value.controller_root) is not str
        or not value.controller_root
        or type(value.owner_pid) is not int
        or value.owner_pid <= 0
        or type(value.owner_thread_id) is not int
        or value.owner_thread_id == 0
        or value.initial_exception_id is not None
        and value.initial_exception_id == value.primary_exception_id
        or value.initial_exception_id is not None
        and value.initial_exception_id == value.secondary_exception_id
        or value.primary_exception_id is not None
        and value.primary_exception_id == value.secondary_exception_id
        or any(
            exception_id is not None
            and exception_id
            in (
                value.temporary_opened_handle_ids
                + value.initial_verification_opened_handle_ids
                + value.recovery_opened_handle_ids
            )
            for exception_id in (
                value.initial_exception_id,
                value.primary_exception_id,
                value.secondary_exception_id,
            )
        )
        or
        value.atomic_temp_close_attempt_count
        != len(value.temporary_close_attempt_handle_ids)
        or value.initial_verification_handle_close_attempt_count
        != len(value.initial_verification_close_attempt_handle_ids)
        or value.recovery_readback_handle_close_attempt_count
        != len(value.recovery_close_attempt_handle_ids)
    ):
        raise StoreError("STORE_TEST_FAULT_INVALID")
    for prefix in _FAULT_EXCEPTION_ROLES:
        fields = [
            getattr(value, f"{prefix}_exception_{suffix}")
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
        ]
        if fields[0] is None:
            if any(item is not None for item in fields):
                raise StoreError("STORE_TEST_FAULT_INVALID")
        elif (
            type(fields[0]) is not int
            or fields[0] <= 0
            or fields[1] != "formal_evaluation_store.StoreError"
            or fields[2] not in _STORE_CATEGORIES
            or type(fields[3]) is not tuple
            or fields[3] != (fields[2],)
            or any(type(item) is not str for item in fields[3])
            or (
                fields[4] is not None
                and (type(fields[4]) is not int or fields[4] <= 0)
            )
            or (
                fields[5] is not None
                and (type(fields[5]) is not int or fields[5] <= 0)
            )
            or type(fields[6]) is not bool
            or type(fields[7]) is not tuple
            or any(type(item) is not str for item in fields[7])
            or type(fields[8]) is not tuple
            or not fields[8]
            or any(type(token) is not int or token <= 0 for token in fields[8])
            or fields[9] is not True
        ):
            raise StoreError("STORE_TEST_FAULT_INVALID")
    if (
        value.initial_exception_id is not None
        and (
            value.initial_exception_category != "STORE_IO_FAILURE"
            or value.initial_exception_cause_id is not None
            or value.initial_exception_context_id is not None
            or value.initial_exception_suppress_context is not False
            or value.initial_exception_notes != ()
        )
        or value.primary_exception_id is not None
        and (
            value.primary_exception_category
            not in {"STORE_IO_FAILURE", "STORE_NONCANONICAL_JSON"}
            or value.primary_exception_cause_id is not None
            or value.primary_exception_context_id is not None
            or value.primary_exception_suppress_context is not False
            or value.primary_exception_notes != ()
        )
        or value.secondary_exception_id is not None
        and (
            value.secondary_exception_category != "STORE_IO_FAILURE"
            or value.secondary_exception_cause_id is not None
            or value.secondary_exception_suppress_context is not False
            or value.secondary_exception_notes != ()
        )
        or
        value.secondary_exception_id is not None
        and (
            value.primary_exception_id is None
            or value.secondary_exception_id == value.primary_exception_id
            or value.secondary_exception_context_id
            != value.primary_exception_id
        )
    ):
        raise StoreError("STORE_TEST_FAULT_INVALID")


def _raise_if_fault(point: str) -> None:
    """Consume one matching simple persistence point and raise exact I/O."""
    if _consume_fault(point):
        _raise_new_fault_primary()


@contextmanager
def _install_stage_b2_test_fault_controller_for_tests(
    root: Path, fault_point: str
) -> Iterator[_StageB2TestFaultControllerV1]:
    global _ACTIVE_FAULT_CONTEXT
    global _STAGE_B2_TEST_FAULT_CONTROLLER, _FAULT_STATE
    if not isinstance(root, Path) or type(fault_point) is not str:
        raise StoreError("STORE_TEST_FAULT_INVALID")
    with _FAULT_STATE_GUARD:
        if _STAGE_B2_TEST_FAULT_CONTROLLER is not None or _FAULT_STATE is not None:
            raise StoreError("STORE_TEST_FAULT_INVALID")
    try:
        resolved_root = root.resolve(strict=True)
        temp_root = Path(tempfile.gettempdir()).resolve()
        repository_root = _REPOSITORY_ROOT.resolve()
        under_temp = (
            os.path.normcase(
                os.path.commonpath((str(resolved_root), str(temp_root)))
            )
            == os.path.normcase(str(temp_root))
        )
        under_repository = (
            os.path.normcase(
                os.path.commonpath((str(resolved_root), str(repository_root)))
            )
            == os.path.normcase(str(repository_root))
        )
    except (OSError, ValueError) as exc:
        raise StoreError("STORE_TEST_FAULT_INVALID") from exc
    if (
        _PRIVATE_STATE_ROOT != root
        or root == _PRODUCTION_PRIVATE_STATE_ROOT
        or resolved_root == temp_root
        or not under_temp
        or under_repository
        or fault_point not in _FAULT_POINTS
    ):
        raise StoreError("STORE_TEST_FAULT_INVALID")
    try:
        _validate_root(root)
        if _is_reparse(root) or not _path_is_dir(root):
            raise StoreError("STORE_TEST_FAULT_INVALID")
        from run_formal_evaluation import (
            _FixedFakeRawClientV1,
            _FixedOfflineExecutorRegistryV1,
            _FixedSyntheticClockV1,
            _fixed_offline_authority,
            _validate_fixed_offline_authority_for_tests,
            _validate_fixed_synthetic_snapshot_v1,
        )

        if not all(
            (
                type(_FixedFakeRawClientV1) is type,
                type(_FixedOfflineExecutorRegistryV1) is type,
                type(_FixedSyntheticClockV1) is type,
                callable(_validate_fixed_synthetic_snapshot_v1),
            )
        ):
            raise StoreError("STORE_TEST_FAULT_INVALID")
        fixed_authority = _fixed_offline_authority()
        _validate_fixed_offline_authority_for_tests(fixed_authority)
        if (
            fixed_authority.fake_raw_client_type is not _FixedFakeRawClientV1
            or fixed_authority.executor_registry_type
            is not _FixedOfflineExecutorRegistryV1
            or fixed_authority.clock_type is not _FixedSyntheticClockV1
            or fixed_authority.snapshot_validator
            is not _validate_fixed_synthetic_snapshot_v1
            or fixed_authority.test_fault_controller_type
            is not _StageB2TestFaultControllerV1
        ):
            raise StoreError("STORE_TEST_FAULT_INVALID")
    except StoreError as exc:
        if exc.category == "STORE_TEST_FAULT_INVALID":
            raise
        raise StoreError("STORE_TEST_FAULT_INVALID") from exc
    except (ImportError, OSError, TypeError, ValueError) as exc:
        raise StoreError("STORE_TEST_FAULT_INVALID") from exc
    controller = _StageB2TestFaultControllerV1(1, root, fault_point)
    with _FAULT_STATE_GUARD:
        if _STAGE_B2_TEST_FAULT_CONTROLLER is not None or _FAULT_STATE is not None:
            raise StoreError("STORE_TEST_FAULT_INVALID")
        state = _new_fault_state(controller)
        _STAGE_B2_TEST_FAULT_CONTROLLER = controller
        _FAULT_STATE = state
    try:
        yield controller
    finally:
        with _FAULT_STATE_GUARD:
            if (
                _STAGE_B2_TEST_FAULT_CONTROLLER is not controller
                or _FAULT_STATE is not state
            ):
                _STAGE_B2_TEST_FAULT_CONTROLLER = None
                _FAULT_STATE = None
                raise StoreError("STORE_TEST_FAULT_INVALID")
            _STAGE_B2_TEST_FAULT_CONTROLLER = None
            _FAULT_STATE = None
            _ACTIVE_FAULT_CONTEXT = None


def _write_fault_marker(
    fault_point: str,
    *,
    execution_unit_id: str,
    attempt_number: int,
    archive_sha256: str,
    private_commit_sha256: str | None,
    provider_call_count: int,
) -> None:
    controller = _STAGE_B2_TEST_FAULT_CONTROLLER
    if controller is None or controller.fault_point != fault_point:
        return
    if controller.root != _PRIVATE_STATE_ROOT or controller.root == _PRODUCTION_PRIVATE_STATE_ROOT:
        raise StoreError("STORE_TEST_FAULT_INVALID")
    try:
        _require_sha(execution_unit_id)
        _require_exact_int(attempt_number, 1, 3)
        _require_sha(archive_sha256)
        if private_commit_sha256 is not None:
            _require_sha(private_commit_sha256)
        _require_exact_int(provider_call_count, 0, 1)
    except ValueError as exc:
        raise StoreError("STORE_TEST_FAULT_INVALID") from exc
    marker_root = controller.root.parent / ".stage_b2_fault_markers"
    try:
        _path_mkdir(marker_root, exist_ok=True)
        if _is_reparse(marker_root) or not _path_is_dir(marker_root):
            raise StoreError("STORE_TEST_FAULT_INVALID")
    except OSError as exc:
        raise StoreError("STORE_TEST_FAULT_INVALID") from exc
    marker = marker_root / f"marker-{os.getpid()}-{fault_point}.json"
    value = {
        "schema_version": 1,
        "fault_point": fault_point,
        "pid": os.getpid(),
        "execution_unit_id": execution_unit_id,
        "attempt_number": attempt_number,
        "archive_sha256": archive_sha256,
        "private_commit_sha256": private_commit_sha256,
        "provider_call_count": provider_call_count,
    }
    raw = _canonical_bytes(value) + b"\n"
    try:
        handle = _path_open(marker, "xb", buffering=0)
        try:
            written = handle.write(raw)
            if written != len(raw):
                raise StoreError("STORE_TEST_FAULT_INVALID")
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        if _path_read_bytes(marker) != raw:
            raise StoreError("STORE_TEST_FAULT_INVALID")
    except StoreError:
        raise
    except (FileExistsError, OSError) as exc:
        raise StoreError("STORE_TEST_FAULT_INVALID") from exc


def _stage_b2_fake_client_fault_hook(provider_call_count: int) -> None:
    context = _ACTIVE_FAULT_CONTEXT
    if context is None:
        return
    for point, exit_code in (
        ("after_fake_client_returned_mark", None),
        ("after_fake_client_returned_exit", 91),
    ):
        controller = _STAGE_B2_TEST_FAULT_CONTROLLER
        if (
            controller is not None
            and controller.fault_point == point
            and _consume_fault(point)
        ):
            _write_fault_marker(
                point,
                execution_unit_id=context["execution_unit_id"],
                attempt_number=context["attempt_number"],
                archive_sha256=context["archive_sha256"],
                private_commit_sha256=None,
                provider_call_count=provider_call_count,
            )
            if exit_code is not None:
                os._exit(exit_code)


_ARCHIVE_FIELDS = (
    "schema_version",
    "run_contract_sha256",
    "execution_unit_id",
    "attempt_number",
    "attempt_id",
    "sequence_number",
    "event",
    "predecessor_attempt_id",
    "predecessor_terminal_archive_sha256",
    "previous_archive_sha256",
    "journal",
    "journal_sha256",
    "private_commit_sha256",
    "archive_sha256",
)
_MUTABLE_FIELDS = (
    "schema_version",
    "run_contract_sha256",
    "execution_unit_id",
    "attempt_number",
    "attempt_id",
    "predecessor_attempt_id",
    "predecessor_terminal_archive_sha256",
    "latest_archive_sha256",
    "private_commit_sha256",
    "journal",
    "journal_sha256",
    "record_sha256",
)
_ARCHIVE_STATES = frozenset(
    {
        "prepared",
        "call_started",
        "provider_returned",
        "retryable_failed",
        "terminal_failed",
        "uncertain",
        "committed",
    }
)


@dataclass(frozen=True)
class _LoadedArchive:
    value: Mapping[str, Any]
    journal: InflightJournal
    path: Path


@dataclass(frozen=True)
class _UnitState:
    archives: tuple[_LoadedArchive, ...]
    tip: _LoadedArchive | None
    mutable: Mapping[str, Any] | None


def _archive_hash(value: Mapping[str, Any]) -> str:
    content = dict(value)
    content.pop("archive_sha256", None)
    return _domain_sha(
        "formal-evaluation-private-attempt-archive-v1",
        "archive",
        content,
    )


def _record_hash(value: Mapping[str, Any]) -> str:
    content = dict(value)
    content.pop("record_sha256", None)
    return _domain_sha(
        "formal-evaluation-private-journal-record-v1",
        "record",
        content,
    )


def _checked_journal_mapping(value: object) -> InflightJournal:
    if type(value) is not dict:
        raise StoreError("STORE_SCHEMA_INVALID")
    try:
        journal = InflightJournal.from_mapping(value)
        validate_journal(journal)
        return journal
    except (JournalError, TypeError, ValueError) as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc


def _validate_archive(
    value: Mapping[str, Any],
    *,
    contract_sha256: str,
    expected_path: Path,
) -> _LoadedArchive:
    if type(value) is not dict or tuple(value) != tuple(sorted(_ARCHIVE_FIELDS)):
        # Canonical persisted objects are parsed in sorted-key order.
        if type(value) is not dict or set(value) != set(_ARCHIVE_FIELDS):
            raise StoreError("STORE_SCHEMA_INVALID")
    if set(value) != set(_ARCHIVE_FIELDS):
        raise StoreError("STORE_SCHEMA_INVALID")
    journal = _checked_journal_mapping(value["journal"])
    try:
        _require_exact_int(value["schema_version"], 1, 1)
        _require_sha(value["run_contract_sha256"])
        _require_sha(value["execution_unit_id"])
        _require_exact_int(value["attempt_number"], 1, 3)
        if (
            type(value["attempt_id"]) is not str
            or _ATTEMPT_ID_RE.fullmatch(value["attempt_id"]) is None
        ):
            raise ValueError
        _require_exact_int(value["sequence_number"], 1, 4)
        if type(value["event"]) is not str or value["event"] not in _ARCHIVE_STATES:
            raise ValueError
        for key in (
            "predecessor_attempt_id",
            "predecessor_terminal_archive_sha256",
            "previous_archive_sha256",
            "private_commit_sha256",
        ):
            item = value[key]
            if item is not None:
                if key == "predecessor_attempt_id":
                    if type(item) is not str or _ATTEMPT_ID_RE.fullmatch(item) is None:
                        raise ValueError
                else:
                    _require_sha(item)
        _require_sha(value["journal_sha256"])
        _require_sha(value["archive_sha256"])
    except ValueError as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc
    if (
        value["run_contract_sha256"] != contract_sha256
        or value["execution_unit_id"] != journal.identity.execution_unit_id
        or value["attempt_number"] != journal.identity.attempt_number
        or value["attempt_id"] != journal.identity.attempt_id
        or value["event"] != journal.state
    ):
        raise StoreError("STORE_SCHEMA_INVALID")
    try:
        public_journal_hash = journal_sha256(journal)
    except JournalError as exc:
        raise StoreError("STORE_HASH_MISMATCH") from exc
    if (
        value["journal_sha256"] != public_journal_hash
        or value["archive_sha256"] != _archive_hash(value)
    ):
        raise StoreError("STORE_HASH_MISMATCH")
    match = _ARCHIVE_NAME_RE.fullmatch(expected_path.name)
    if (
        match is None
        or int(match.group("attempt")) != value["attempt_number"]
        or int(match.group("sequence")) != value["sequence_number"]
        or match.group("journal") != value["journal_sha256"]
    ):
        raise StoreError("STORE_PATH_INVALID")
    attempt = value["attempt_number"]
    predecessor_null = (
        value["predecessor_attempt_id"] is None
        and value["predecessor_terminal_archive_sha256"] is None
    )
    if (attempt == 1) != predecessor_null:
        raise StoreError("STORE_PREDECESSOR_INVALID")
    sequence = value["sequence_number"]
    if (sequence == 1) != (value["previous_archive_sha256"] is None):
        raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
    state = journal.state
    commit = value["private_commit_sha256"]
    valid_matrix = (
        (sequence == 1 and state == "prepared" and commit is None)
        or (
            sequence == 2
            and (
                (state == "call_started" and commit is None)
                or (
                    state == "retryable_failed"
                    and journal.sanitized_outcome_category == "pre_send_failure"
                    and commit is None
                )
                or (state == "prepared" and commit is not None)
            )
        )
        or (
            sequence == 3
            and state
            in {
                "provider_returned",
                "retryable_failed",
                "terminal_failed",
                "uncertain",
            }
            and commit is None
        )
        or (sequence == 4 and state == "committed" and commit is not None)
    )
    if not valid_matrix:
        raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
    return _LoadedArchive(MappingProxyType(dict(value)), journal, expected_path)


def _mutable_from_archive(archive: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "schema_version": 1,
        "run_contract_sha256": archive["run_contract_sha256"],
        "execution_unit_id": archive["execution_unit_id"],
        "attempt_number": archive["attempt_number"],
        "attempt_id": archive["attempt_id"],
        "predecessor_attempt_id": archive["predecessor_attempt_id"],
        "predecessor_terminal_archive_sha256": archive[
            "predecessor_terminal_archive_sha256"
        ],
        "latest_archive_sha256": archive["archive_sha256"],
        "private_commit_sha256": archive["private_commit_sha256"],
        "journal": copy.deepcopy(archive["journal"]),
        "journal_sha256": archive["journal_sha256"],
    }
    value["record_sha256"] = _record_hash(value)
    return value


def _validate_mutable(
    value: Mapping[str, Any],
    *,
    contract_sha256: str,
    execution_unit_id: str,
) -> tuple[dict[str, Any], InflightJournal]:
    if type(value) is not dict or set(value) != set(_MUTABLE_FIELDS):
        raise StoreError("STORE_SCHEMA_INVALID")
    journal = _checked_journal_mapping(value["journal"])
    try:
        _require_exact_int(value["schema_version"], 1, 1)
        for key in (
            "run_contract_sha256",
            "execution_unit_id",
            "latest_archive_sha256",
            "journal_sha256",
            "record_sha256",
        ):
            _require_sha(value[key])
        _require_exact_int(value["attempt_number"], 1, 3)
        if (
            type(value["attempt_id"]) is not str
            or _ATTEMPT_ID_RE.fullmatch(value["attempt_id"]) is None
        ):
            raise ValueError
        for key in (
            "predecessor_attempt_id",
            "predecessor_terminal_archive_sha256",
            "private_commit_sha256",
        ):
            if value[key] is not None:
                if key == "predecessor_attempt_id":
                    if (
                        type(value[key]) is not str
                        or _ATTEMPT_ID_RE.fullmatch(value[key]) is None
                    ):
                        raise ValueError
                else:
                    _require_sha(value[key])
    except ValueError as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc
    if (
        value["run_contract_sha256"] != contract_sha256
        or value["execution_unit_id"] != execution_unit_id
        or value["execution_unit_id"] != journal.identity.execution_unit_id
        or value["attempt_number"] != journal.identity.attempt_number
        or value["attempt_id"] != journal.identity.attempt_id
        or value["journal_sha256"] != journal_sha256(journal)
        or value["record_sha256"] != _record_hash(value)
    ):
        raise StoreError("STORE_HASH_MISMATCH")
    if (value["attempt_number"] == 1) != (
        value["predecessor_attempt_id"] is None
        and value["predecessor_terminal_archive_sha256"] is None
    ):
        raise StoreError("STORE_PREDECESSOR_INVALID")
    return dict(value), journal


def _validate_transition(previous: InflightJournal, current: InflightJournal) -> None:
    if previous.identity != current.identity:
        raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
    if previous.state == "prepared" and current.state == "prepared":
        if previous != current:
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        return
    try:
        if current.state == "call_started":
            from formal_evaluation_inflight import transition

            rebuilt = transition(
                previous,
                "call_started",
                current.updated_at,
                provider_request_id=current.provider_request_id,
            )
        elif current.state == "provider_returned":
            from formal_evaluation_inflight import transition

            rebuilt = transition(
                previous,
                "provider_returned",
                current.updated_at,
                provider_response_id=current.provider_response_id,
                provider_response_sha256=current.provider_response_sha256,
                response_sha256=current.response_sha256,
            )
        elif current.state in {
            "retryable_failed",
            "terminal_failed",
            "uncertain",
        }:
            from formal_evaluation_inflight import transition

            rebuilt = transition(
                previous,
                current.state,
                current.updated_at,
                sanitized_outcome_category=current.sanitized_outcome_category,
            )
        else:
            return
    except JournalError as exc:
        raise StoreError("STORE_ARCHIVE_CHAIN_INVALID") from exc
    if rebuilt != current:
        raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")


def _load_unit_state_locked(
    execution_unit_id: str,
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
    repair_mutable: bool = True,
    allow_owned_temps: bool = False,
) -> _UnitState:
    lock.require_active()
    if type(repair_mutable) is not bool or type(allow_owned_temps) is not bool:
        raise StoreError("STORE_SCHEMA_INVALID")
    try:
        _require_sha(execution_unit_id)
    except ValueError as exc:
        raise StoreError("STORE_PATH_INVALID") from exc
    root = lock.root
    attempt_directory = root / "attempts" / execution_unit_id
    loaded: list[_LoadedArchive] = []
    if _path_exists(attempt_directory):
        if _is_reparse(attempt_directory) or not _path_is_dir(attempt_directory):
            raise StoreError("STORE_PATH_INVALID")
        for path in _path_iterdir(attempt_directory):
            if allow_owned_temps and _owned_temp_kind(path) == "archive":
                if _is_reparse(path) or not _path_is_file(path):
                    raise StoreError("STORE_PATH_INVALID")
                continue
            if _is_reparse(path) or not _path_is_file(path):
                raise StoreError("STORE_PATH_INVALID")
            if _ARCHIVE_NAME_RE.fullmatch(path.name) is None:
                raise StoreError("STORE_PATH_INVALID")
            value = _read_json(path, _ARCHIVE_LIMIT)
            loaded.append(
                _validate_archive(
                    value,
                    contract_sha256=run_contract["run_contract_sha256"],
                    expected_path=path,
                )
            )
    loaded.sort(
        key=lambda item: (
            item.value["attempt_number"],
            item.value["sequence_number"],
        )
    )
    attempts: dict[int, list[_LoadedArchive]] = {}
    hashes: set[str] = set()
    for archive in loaded:
        if archive.value["execution_unit_id"] != execution_unit_id:
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        archive_hash = archive.value["archive_sha256"]
        if archive_hash in hashes:
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        hashes.add(archive_hash)
        attempts.setdefault(archive.value["attempt_number"], []).append(archive)
    if attempts and sorted(attempts) != list(range(1, max(attempts) + 1)):
        raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
    previous_attempt_tip: _LoadedArchive | None = None
    for attempt_number, chain in attempts.items():
        if [item.value["sequence_number"] for item in chain] != list(
            range(1, len(chain) + 1)
        ):
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        for index, archive in enumerate(chain):
            expected_previous = (
                None if index == 0 else chain[index - 1].value["archive_sha256"]
            )
            if archive.value["previous_archive_sha256"] != expected_previous:
                raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
            if index:
                _validate_transition(chain[index - 1].journal, archive.journal)
        first = chain[0]
        if attempt_number == 1:
            if (
                first.value["predecessor_attempt_id"] is not None
                or first.value["predecessor_terminal_archive_sha256"] is not None
            ):
                raise StoreError("STORE_PREDECESSOR_INVALID")
        else:
            if (
                previous_attempt_tip is None
                or previous_attempt_tip.journal.state != "retryable_failed"
                or previous_attempt_tip.journal.identity.attempt_number
                != attempt_number - 1
                or first.value["predecessor_attempt_id"]
                != previous_attempt_tip.journal.identity.attempt_id
                or first.value["predecessor_terminal_archive_sha256"]
                != previous_attempt_tip.value["archive_sha256"]
            ):
                raise StoreError("STORE_PREDECESSOR_INVALID")
            try:
                rebuilt = next_retry_journal(
                    previous_attempt_tip.journal,
                    first.journal.prepared_at,
                )
            except JournalError as exc:
                raise StoreError("STORE_PREDECESSOR_INVALID") from exc
            if rebuilt != first.journal:
                raise StoreError("STORE_PREDECESSOR_INVALID")
        previous_attempt_tip = chain[-1]
    tip = loaded[-1] if loaded else None
    mutable_path = root / "journals" / f"{execution_unit_id}.json"
    mutable: dict[str, Any] | None = None
    if _path_exists(mutable_path):
        if _is_reparse(mutable_path) or not _path_is_file(mutable_path):
            raise StoreError("STORE_PATH_INVALID")
        mutable, _mutable_journal = _validate_mutable(
            _read_json(mutable_path, _JOURNAL_LIMIT),
            contract_sha256=run_contract["run_contract_sha256"],
            execution_unit_id=execution_unit_id,
        )
    if tip is None:
        if mutable is not None:
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        return _UnitState(tuple(), None, None)
    expected_mutable = _mutable_from_archive(tip.value)
    if mutable is None:
        if repair_mutable:
            _atomic_publish_json(
                mutable_path,
                expected_mutable,
                replace=True,
                maximum=_JOURNAL_LIMIT,
            )
            mutable = expected_mutable
        else:
            return _UnitState(tuple(loaded), tip, None)
    elif mutable != expected_mutable:
        pointed_index = next(
            (
                index
                for index, archive in enumerate(loaded)
                if archive.value["archive_sha256"]
                == mutable["latest_archive_sha256"]
            ),
            None,
        )
        if pointed_index is None:
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        pointed = loaded[pointed_index]
        if mutable != _mutable_from_archive(pointed.value):
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        if pointed_index >= len(loaded) - 1:
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        if repair_mutable:
            _atomic_publish_json(
                mutable_path,
                expected_mutable,
                replace=True,
                maximum=_JOURNAL_LIMIT,
            )
            mutable = expected_mutable
    return _UnitState(tuple(loaded), tip, MappingProxyType(mutable))


def _publish_journal_locked(
    journal: InflightJournal,
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
    private_commit_sha256: str | None = None,
) -> Mapping[str, Any]:
    global _ACTIVE_FAULT_CONTEXT
    lock.require_active()
    try:
        validate_journal(journal)
    except JournalError as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc
    execution_unit_id = journal.identity.execution_unit_id
    state = _load_unit_state_locked(
        execution_unit_id, run_contract=run_contract, lock=lock
    )
    attempt = journal.identity.attempt_number
    current_attempt = [
        item for item in state.archives if item.value["attempt_number"] == attempt
    ]
    predecessor_attempt_id: str | None = None
    predecessor_terminal_archive_sha256: str | None = None
    if not current_attempt:
        if attempt == 1:
            if state.archives:
                raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        else:
            previous = [
                item
                for item in state.archives
                if item.value["attempt_number"] == attempt - 1
            ]
            if not previous or previous[-1].journal.state != "retryable_failed":
                raise StoreError("STORE_PREDECESSOR_INVALID")
            predecessor_attempt_id = previous[-1].journal.identity.attempt_id
            predecessor_terminal_archive_sha256 = previous[-1].value[
                "archive_sha256"
            ]
            try:
                if next_retry_journal(
                    previous[-1].journal, journal.prepared_at
                ) != journal:
                    raise StoreError("STORE_PREDECESSOR_INVALID")
            except JournalError as exc:
                raise StoreError("STORE_PREDECESSOR_INVALID") from exc
        sequence = 1
        previous_hash = None
    else:
        last = current_attempt[-1]
        predecessor_attempt_id = last.value["predecessor_attempt_id"]
        predecessor_terminal_archive_sha256 = last.value[
            "predecessor_terminal_archive_sha256"
        ]
        sequence = last.value["sequence_number"] + 1
        previous_hash = last.value["archive_sha256"]
        if sequence > 4:
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
        if journal != last.journal:
            _validate_transition(last.journal, journal)
        elif not (
            journal.state == "prepared"
            and sequence == 2
            and private_commit_sha256 is not None
        ):
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
    value = {
        "schema_version": 1,
        "run_contract_sha256": run_contract["run_contract_sha256"],
        "execution_unit_id": execution_unit_id,
        "attempt_number": attempt,
        "attempt_id": journal.identity.attempt_id,
        "sequence_number": sequence,
        "event": journal.state,
        "predecessor_attempt_id": predecessor_attempt_id,
        "predecessor_terminal_archive_sha256": predecessor_terminal_archive_sha256,
        "previous_archive_sha256": previous_hash,
        "journal": journal.to_dict(),
        "journal_sha256": journal_sha256(journal),
        "private_commit_sha256": private_commit_sha256,
    }
    value["archive_sha256"] = _archive_hash(value)
    attempt_directory = lock.root / "attempts" / execution_unit_id
    if not _path_exists(attempt_directory):
        try:
            _path_mkdir(attempt_directory)
        except OSError as exc:
            raise StoreError("STORE_IO_FAILURE") from exc
    if _is_reparse(attempt_directory) or not _path_is_dir(attempt_directory):
        raise StoreError("STORE_PATH_INVALID")
    path = attempt_directory / (
        f"{attempt}-{sequence}-{value['journal_sha256']}.json"
    )
    published = _atomic_publish_json(
        path,
        value,
        replace=False,
        maximum=_ARCHIVE_LIMIT,
    )
    if not published:
        existing = _read_json(path, _ARCHIVE_LIMIT)
        if existing != value:
            raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
    if (
        _STAGE_B2_TEST_FAULT_CONTROLLER is not None
        and _STAGE_B2_TEST_FAULT_CONTROLLER.fault_point
        == "after_committed_archive_published_exit"
        and journal.state == "committed"
        and _consume_fault("after_committed_archive_published_exit")
    ):
        context = _ACTIVE_FAULT_CONTEXT
        provider_calls = (
            0
            if context is None
            else context.get("provider_call_count", 0)
        )
        _write_fault_marker(
            "after_committed_archive_published_exit",
            execution_unit_id=execution_unit_id,
            attempt_number=attempt,
            archive_sha256=value["archive_sha256"],
            private_commit_sha256=private_commit_sha256,
            provider_call_count=provider_calls,
        )
        os._exit(93)
    mutable = _mutable_from_archive(value)
    _atomic_publish_json(
        lock.root / "journals" / f"{execution_unit_id}.json",
        mutable,
        replace=True,
        maximum=_JOURNAL_LIMIT,
    )
    _ACTIVE_FAULT_CONTEXT = (
        {
            "execution_unit_id": execution_unit_id,
            "attempt_number": attempt,
            "archive_sha256": value["archive_sha256"],
            "provider_call_count": 0,
        }
        if _STAGE_B2_TEST_FAULT_CONTROLLER is not None
        else None
    )
    if (
        journal.state == "call_started"
        and _STAGE_B2_TEST_FAULT_CONTROLLER is not None
        and _STAGE_B2_TEST_FAULT_CONTROLLER.fault_point
        == "after_call_started_published_exit"
        and _consume_fault("after_call_started_published_exit")
    ):
        _write_fault_marker(
            "after_call_started_published_exit",
            execution_unit_id=execution_unit_id,
            attempt_number=attempt,
            archive_sha256=value["archive_sha256"],
            private_commit_sha256=None,
            provider_call_count=0,
        )
        os._exit(90)
    return MappingProxyType(value)


def _validate_store_layout_locked(
    lock: _RunWideLock, *, allow_owned_temps: bool = False
) -> None:
    lock.require_active()
    if type(allow_owned_temps) is not bool:
        raise StoreError("STORE_SCHEMA_INVALID")
    root = lock.root
    allowed_root = {
        "run.lock",
        "run_contract.json",
        "journals",
        "attempts",
        "commits",
    }
    for path in _path_iterdir(root):
        if (
            allow_owned_temps
            and _owned_temp_kind(path) == "run_contract"
            and not _is_reparse(path)
            and _path_is_file(path)
        ):
            continue
        if path.name not in allowed_root or _is_reparse(path):
            raise StoreError("STORE_PATH_INVALID")
    for path in _path_iterdir(root / "journals"):
        if (
            allow_owned_temps
            and _owned_temp_kind(path) == "mutable"
            and not _is_reparse(path)
            and _path_is_file(path)
        ):
            continue
        if (
            _is_reparse(path)
            or not _path_is_file(path)
            or _JOURNAL_NAME_RE.fullmatch(path.name) is None
        ):
            raise StoreError("STORE_PATH_INVALID")
    for path in _path_iterdir(root / "commits"):
        if (
            allow_owned_temps
            and _owned_temp_kind(path) == "commit"
            and not _is_reparse(path)
            and _path_is_file(path)
        ):
            continue
        if (
            _is_reparse(path)
            or not _path_is_file(path)
            or _COMMIT_NAME_RE.fullmatch(path.name) is None
        ):
            raise StoreError("STORE_PATH_INVALID")
    for directory in _path_iterdir(root / "attempts"):
        if (
            _is_reparse(directory)
            or not _path_is_dir(directory)
            or _SHA256_RE.fullmatch(directory.name) is None
        ):
            raise StoreError("STORE_PATH_INVALID")
        for path in _path_iterdir(directory):
            if (
                allow_owned_temps
                and _owned_temp_kind(path) == "archive"
                and not _is_reparse(path)
                and _path_is_file(path)
            ):
                continue
            if (
                _is_reparse(path)
                or not _path_is_file(path)
                or _ARCHIVE_NAME_RE.fullmatch(path.name) is None
            ):
                raise StoreError("STORE_PATH_INVALID")


_PLAN_BINDING_FIELDS = (
    "plan_fingerprint",
    "plan_member_sha256",
    "execution_unit_id",
    "execution_order",
    "request_id",
    "rq",
    "case_id",
    "dialogue_id",
    "turn_index",
    "system_config_id",
    "formal_system_id",
    "input_sha256",
    "payload_sha256",
    "resolved_payload_sha256",
    "frozen_test_file_sha256",
)
_ATTEMPT_LINEAGE_FIELDS = (
    "attempt_number",
    "attempt_id",
    "prepared_archive_sha256",
    "pre_commit_archive_sha256",
    "predecessor_attempt_id",
    "predecessor_terminal_archive_sha256",
)
_RQ3_RELATIONSHIP_FIELDS = (
    "kind",
    "dialogue_id",
    "turn_one_request_id",
    "turn_two_request_id",
    "turn_one_commit_sha256",
    "checkpoint_evidence",
    "checkpoint_record_sha256",
)
_ENVELOPE_FIELDS = (
    "schema_version",
    "formal_result_schema_version",
    "run_contract_sha256",
    "plan_member_binding",
    "execution_identity",
    "success_kind",
    "attempt_lineage",
    "authoritative_success",
    "formal_result",
    "formal_result_sha256",
    "response_sha256",
    "provider_response_sha256",
    "rq3_relationship",
    "envelope_sha256",
)
_FORMAL_RESULT_FIELDS = frozenset(
    {
        "plan_fingerprint",
        "execution_unit_id",
        "execution_order",
        "request_id",
        "research_question",
        "case_id",
        "dialogue_id",
        "turn_index",
        "turn_id",
        "input_checkpoint_id",
        "input_checkpoint_sha256",
        "system_config_id",
        "formal_system_id",
        "resolved_runtime_system_id",
        "payload_sha256",
        "resolved_payload_sha256",
        "transport_contract_id",
        "transport_contract_sha256",
        "generation_contract_id",
        "generation_contract_sha256",
        "transport_implementation_sha256",
        "resource_identity",
        "resource_identity_sha256",
        "attempt_id",
        "response_text",
        "response_sha256",
        "provider",
        "provider_model",
        "attempt_count",
        "route",
        "guard_category",
        "requires_backend_api",
        "retrieval_used",
        "retrieved_document_ids",
        "retrieved_scores",
        "checkpoint_snapshot_sha256",
        "execution_status",
        "status",
        "provider_called",
        "provider_request_id",
        "provider_response_id",
        "provider_response_sha256",
        "call_started_at",
        "provider_returned_at",
        "committed_at",
        "authoritative_success",
    }
)


def _plan_member_sha256(unit: Mapping[str, Any]) -> str:
    return _domain_sha(
        "formal-evaluation-plan-member-v1",
        "plan_member",
        unit,
    )


def _formal_result_sha256(result: Mapping[str, Any]) -> str:
    return _domain_sha(
        "formal-evaluation-private-formal-result-v1",
        "formal_result",
        result,
    )


def _envelope_hash(value: Mapping[str, Any]) -> str:
    content = dict(value)
    content.pop("envelope_sha256", None)
    return _domain_sha(
        "formal-evaluation-private-commit-envelope-v1",
        "envelope",
        content,
    )


def _execution_unit_id(unit: Mapping[str, Any]) -> str:
    try:
        return derive_execution_unit_id(
            plan_fingerprint=_PLAN_FINGERPRINT,
            request_id=unit["request_id"],
            execution_order=unit["execution_order"],
        )
    except (JournalError, KeyError, TypeError) as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc


def _plan_pair(
    plan: Sequence[Mapping[str, Any]], unit: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any]] | None:
    if unit["rq"] != "RQ3":
        return None
    pair = [
        candidate
        for candidate in plan
        if candidate["rq"] == "RQ3"
        and candidate["case_id"] == unit["case_id"]
        and candidate["system_config_id"] == unit["system_config_id"]
    ]
    pair.sort(key=lambda candidate: candidate["turn_index"])
    if (
        len(pair) != 2
        or [candidate["turn_index"] for candidate in pair] != [1, 2]
    ):
        raise StoreError("STORE_SCHEMA_INVALID")
    return pair[0], pair[1]


def _expected_plan_binding(
    unit: Mapping[str, Any],
    identity: ExecutionIdentity,
    run_contract: Mapping[str, Any],
) -> dict[str, Any]:
    system = run_contract["formal_system_authority"][unit["system_config_id"]]
    return {
        "plan_fingerprint": _PLAN_FINGERPRINT,
        "plan_member_sha256": _plan_member_sha256(unit),
        "execution_unit_id": identity.execution_unit_id,
        "execution_order": unit["execution_order"],
        "request_id": unit["request_id"],
        "rq": unit["rq"],
        "case_id": unit["case_id"],
        "dialogue_id": unit["case_id"] if unit["rq"] == "RQ3" else None,
        "turn_index": unit["turn_index"],
        "system_config_id": unit["system_config_id"],
        "formal_system_id": system["formal_system_id"],
        "input_sha256": unit["input_sha256"],
        "payload_sha256": unit["payload_sha256"],
        "resolved_payload_sha256": identity.resolved_payload_sha256,
        "frozen_test_file_sha256": unit["frozen_test_file_sha256"],
    }


def _resource_from_contract(
    run_contract: Mapping[str, Any], system_config_id: str
) -> ProductionResourceIdentity:
    try:
        wrapper = run_contract["runtime_resource_authority"]["resources"][
            system_config_id
        ]
        resource = ProductionResourceIdentity.from_mapping(
            wrapper["resource_identity"]
        )
        validate_resource_identity(resource)
        if wrapper["resource_identity_sha256"] != resource_identity_sha256(resource):
            raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
        return resource
    except StoreError:
        raise
    except (KeyError, TypeError, TransportError) as exc:
        raise StoreError("STORE_RUN_CONTRACT_MISMATCH") from exc


def _checked_formal_result(value: object) -> dict[str, Any]:
    if type(value) is not dict or set(value) != _FORMAL_RESULT_FIELDS:
        raise StoreError("STORE_SCHEMA_INVALID")
    try:
        projected = project_formal_result(value)
    except TransportError as exc:
        raise StoreError("STORE_COMMIT_INVALID") from exc
    if _canonical_bytes(projected) != _canonical_bytes(value):
        raise StoreError("STORE_COMMIT_INVALID")
    return copy.deepcopy(value)


def _attempt_lineage_for_outcome(
    outcome: OrchestrationOutcome,
    state: _UnitState,
) -> dict[str, Any]:
    attempt = outcome.identity.attempt_number
    attempt_archives = [
        archive
        for archive in state.archives
        if archive.value["attempt_number"] == attempt
    ]
    if not attempt_archives or attempt_archives[0].value["sequence_number"] != 1:
        raise StoreError("STORE_ARCHIVE_CHAIN_INVALID")
    prepared = attempt_archives[0]
    if outcome.action == "success":
        if (
            state.tip is None
            or state.tip.journal.state != "provider_returned"
            or state.tip.value["attempt_number"] != attempt
        ):
            raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
        pre_commit = state.tip
    elif outcome.action == "local_success":
        if (
            state.tip is None
            or state.tip.journal.state != "prepared"
            or state.tip.value["attempt_number"] != attempt
        ):
            raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
        pre_commit = prepared
    else:
        raise StoreError("STORE_COMMIT_INVALID")
    return {
        "attempt_number": attempt,
        "attempt_id": outcome.identity.attempt_id,
        "prepared_archive_sha256": prepared.value["archive_sha256"],
        "pre_commit_archive_sha256": pre_commit.value["archive_sha256"],
        "predecessor_attempt_id": prepared.value["predecessor_attempt_id"],
        "predecessor_terminal_archive_sha256": prepared.value[
            "predecessor_terminal_archive_sha256"
        ],
    }


def _rq3_relationship_for_outcome(
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    outcome: OrchestrationOutcome,
    *,
    turn_one_commit_sha256: str | None,
) -> dict[str, Any]:
    pair = _plan_pair(plan, unit)
    if pair is None:
        return {
            "kind": "none",
            "dialogue_id": None,
            "turn_one_request_id": None,
            "turn_two_request_id": None,
            "turn_one_commit_sha256": None,
            "checkpoint_evidence": None,
            "checkpoint_record_sha256": None,
        }
    turn_one, turn_two = pair
    base = {
        "dialogue_id": unit["case_id"],
        "turn_one_request_id": turn_one["request_id"],
        "turn_two_request_id": turn_two["request_id"],
    }
    if unit["system_config_id"] == "single_turn":
        return {
            "kind": "single_turn",
            **base,
            "turn_one_commit_sha256": None,
            "checkpoint_evidence": None,
            "checkpoint_record_sha256": None,
        }
    checkpoint = outcome.checkpoint_evidence
    if type(checkpoint) is not CheckpointEvidence:
        raise StoreError("STORE_COMMIT_INVALID")
    if unit["turn_index"] == 1:
        return {
            "kind": "context_turn_one",
            **base,
            "turn_one_commit_sha256": None,
            "checkpoint_evidence": checkpoint.to_dict(),
            "checkpoint_record_sha256": checkpoint.checkpoint_sha256,
        }
    if turn_one_commit_sha256 is None:
        raise StoreError("STORE_DEPENDENCY_INVALID")
    return {
        "kind": "context_turn_two",
        **base,
        "turn_one_commit_sha256": turn_one_commit_sha256,
        "checkpoint_evidence": checkpoint.to_dict(),
        "checkpoint_record_sha256": checkpoint.checkpoint_sha256,
    }


def _construct_private_commit(
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    outcome: OrchestrationOutcome,
    *,
    run_contract: Mapping[str, Any],
    state: _UnitState,
    turn_one_commit_sha256: str | None,
) -> dict[str, Any]:
    if outcome.formal_result is None:
        raise StoreError("STORE_COMMIT_INVALID")
    try:
        validate_execution_identity(outcome.identity)
    except JournalError as exc:
        raise StoreError("STORE_COMMIT_INVALID") from exc
    formal_result = json.loads(_canonical_bytes(dict(outcome.formal_result)))
    formal_result = _checked_formal_result(formal_result)
    success_kind = "provider" if outcome.action == "success" else "local"
    if success_kind == "provider":
        if type(outcome.authoritative_success) is not AuthoritativeSuccess:
            raise StoreError("STORE_COMMIT_INVALID")
        authoritative_success = outcome.authoritative_success.to_dict()
        provider_response_sha = outcome.authoritative_success.provider_response_sha256
    else:
        if outcome.authoritative_success is not None:
            raise StoreError("STORE_COMMIT_INVALID")
        authoritative_success = None
        provider_response_sha = None
    value = {
        "schema_version": 1,
        "formal_result_schema_version": 1,
        "run_contract_sha256": run_contract["run_contract_sha256"],
        "plan_member_binding": _expected_plan_binding(
            unit, outcome.identity, run_contract
        ),
        "execution_identity": outcome.identity.to_dict(),
        "success_kind": success_kind,
        "attempt_lineage": _attempt_lineage_for_outcome(outcome, state),
        "authoritative_success": authoritative_success,
        "formal_result": formal_result,
        "formal_result_sha256": _formal_result_sha256(formal_result),
        "response_sha256": formal_result["response_sha256"],
        "provider_response_sha256": provider_response_sha,
        "rq3_relationship": _rq3_relationship_for_outcome(
            plan,
            unit,
            outcome,
            turn_one_commit_sha256=turn_one_commit_sha256,
        ),
    }
    value["envelope_sha256"] = _envelope_hash(value)
    return value


def _archive_by_hash(
    state: _UnitState, archive_sha256: str
) -> _LoadedArchive:
    matches = [
        item
        for item in state.archives
        if item.value["archive_sha256"] == archive_sha256
    ]
    if len(matches) != 1:
        raise StoreError("STORE_COMMIT_INVALID")
    return matches[0]


def _validate_attempt_lineage(
    value: object,
    *,
    identity: ExecutionIdentity,
    success_kind: str,
    state: _UnitState,
) -> None:
    if type(value) is not dict or set(value) != set(_ATTEMPT_LINEAGE_FIELDS):
        raise StoreError("STORE_SCHEMA_INVALID")
    try:
        _require_exact_int(value["attempt_number"], 1, 3)
        if (
            type(value["attempt_id"]) is not str
            or _ATTEMPT_ID_RE.fullmatch(value["attempt_id"]) is None
        ):
            raise ValueError
        _require_sha(value["prepared_archive_sha256"])
        _require_sha(value["pre_commit_archive_sha256"])
    except ValueError as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc
    if (
        value["attempt_number"] != identity.attempt_number
        or value["attempt_id"] != identity.attempt_id
    ):
        raise StoreError("STORE_COMMIT_INVALID")
    prepared = _archive_by_hash(state, value["prepared_archive_sha256"])
    pre_commit = _archive_by_hash(state, value["pre_commit_archive_sha256"])
    if (
        prepared.value["attempt_number"] != identity.attempt_number
        or prepared.value["sequence_number"] != 1
        or prepared.journal.state != "prepared"
        or pre_commit.value["attempt_number"] != identity.attempt_number
        or value["predecessor_attempt_id"]
        != prepared.value["predecessor_attempt_id"]
        or value["predecessor_terminal_archive_sha256"]
        != prepared.value["predecessor_terminal_archive_sha256"]
    ):
        raise StoreError("STORE_COMMIT_INVALID")
    if success_kind == "provider":
        if pre_commit.journal.state != "provider_returned":
            raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
    elif pre_commit != prepared:
        raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")


def _validate_rq3_relationship(
    value: object,
    *,
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    identity: ExecutionIdentity,
    formal_result: Mapping[str, Any],
    run_contract: Mapping[str, Any],
    turn_one_commit: Mapping[str, Any] | None,
) -> CheckpointEvidence | None:
    if type(value) is not dict or set(value) != set(_RQ3_RELATIONSHIP_FIELDS):
        raise StoreError("STORE_SCHEMA_INVALID")
    pair = _plan_pair(plan, unit)
    if pair is None:
        expected = {
            "kind": "none",
            "dialogue_id": None,
            "turn_one_request_id": None,
            "turn_two_request_id": None,
            "turn_one_commit_sha256": None,
            "checkpoint_evidence": None,
            "checkpoint_record_sha256": None,
        }
        if value != expected:
            raise StoreError("STORE_COMMIT_INVALID")
        return None
    turn_one, turn_two = pair
    common = (
        value["dialogue_id"] == unit["case_id"]
        and value["turn_one_request_id"] == turn_one["request_id"]
        and value["turn_two_request_id"] == turn_two["request_id"]
    )
    if not common:
        raise StoreError("STORE_COMMIT_INVALID")
    if unit["system_config_id"] == "single_turn":
        if (
            value["kind"] != "single_turn"
            or value["turn_one_commit_sha256"] is not None
            or value["checkpoint_evidence"] is not None
            or value["checkpoint_record_sha256"] is not None
        ):
            raise StoreError("STORE_COMMIT_INVALID")
        return None
    if type(value["checkpoint_evidence"]) is not dict:
        raise StoreError("STORE_COMMIT_INVALID")
    try:
        if run_contract["stage_id"] == "B2":
            from run_formal_evaluation import _validate_fixed_synthetic_snapshot_v1

            snapshot_validator = _validate_fixed_synthetic_snapshot_v1
        elif (
            run_contract["stage_id"] == "B5"
            and run_contract["provider_generation_authority"]["real_execution"][
                "mode"
            ]
            == "production_real"
        ):
            from formal_evaluation_runtime import restore_runtime_snapshot

            snapshot_validator = restore_runtime_snapshot
        else:
            raise KeyError("unknown execution authority")

        checkpoint = validate_checkpoint_evidence(
            value["checkpoint_evidence"],
            turn_one_unit=turn_one,
            turn_two_unit=turn_two,
            resource=_resource_from_contract(run_contract, "context_aware"),
            runtime_identity_sha256=run_contract["runtime_resource_authority"][
                "runtime_identity_sha256"
            ],
            snapshot_validator=snapshot_validator,
        )
    except (OrchestrationError, KeyError, TypeError) as exc:
        category = (
            "STORE_DEPENDENCY_INVALID"
            if unit["turn_index"] == 2
            else "STORE_COMMIT_INVALID"
        )
        raise StoreError(category) from exc
    if value["checkpoint_record_sha256"] != checkpoint.checkpoint_sha256:
        raise StoreError(
            "STORE_DEPENDENCY_INVALID"
            if unit["turn_index"] == 2
            else "STORE_COMMIT_INVALID"
        )
    if unit["turn_index"] == 1:
        if (
            value["kind"] != "context_turn_one"
            or value["turn_one_commit_sha256"] is not None
            or formal_result["checkpoint_snapshot_sha256"] is not None
        ):
            raise StoreError("STORE_COMMIT_INVALID")
    else:
        if (
            value["kind"] != "context_turn_two"
            or turn_one_commit is None
            or value["turn_one_commit_sha256"]
            != turn_one_commit["envelope_sha256"]
            or identity.input_checkpoint_id != checkpoint.checkpoint_id
            or identity.input_checkpoint_sha256 != checkpoint.checkpoint_sha256
            or formal_result["checkpoint_snapshot_sha256"]
            != checkpoint.snapshot_sha256
        ):
            raise StoreError("STORE_DEPENDENCY_INVALID")
    return checkpoint


def _validate_private_commit(
    value: Mapping[str, Any],
    *,
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    run_contract: Mapping[str, Any],
    state: _UnitState,
    expected_path: Path,
    turn_one_commit: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != set(_ENVELOPE_FIELDS):
        raise StoreError("STORE_SCHEMA_INVALID")
    try:
        _require_exact_int(value["schema_version"], 1, 1)
        _require_exact_int(value["formal_result_schema_version"], 1, 1)
        for name in (
            "run_contract_sha256",
            "formal_result_sha256",
            "response_sha256",
            "envelope_sha256",
        ):
            _require_sha(value[name])
        if value["provider_response_sha256"] is not None:
            _require_sha(value["provider_response_sha256"])
    except ValueError as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc
    if (
        value["run_contract_sha256"] != run_contract["run_contract_sha256"]
        or value["envelope_sha256"] != _envelope_hash(value)
    ):
        raise StoreError("STORE_HASH_MISMATCH")
    try:
        identity = ExecutionIdentity.from_mapping(value["execution_identity"])
        validate_execution_identity(identity)
    except (JournalError, TypeError) as exc:
        raise StoreError("STORE_COMMIT_INVALID") from exc
    expected_name = f"{unit['execution_order']}-{identity.execution_unit_id}.json"
    if expected_path.name != expected_name:
        raise StoreError("STORE_PATH_INVALID")
    binding = value["plan_member_binding"]
    if (
        type(binding) is not dict
        or set(binding) != set(_PLAN_BINDING_FIELDS)
        or binding != _expected_plan_binding(unit, identity, run_contract)
    ):
        raise StoreError("STORE_COMMIT_INVALID")
    formal_result = _checked_formal_result(value["formal_result"])
    if (
        value["formal_result_sha256"] != _formal_result_sha256(formal_result)
        or value["response_sha256"] != formal_result["response_sha256"]
        or value["response_sha256"] != sha256_text(formal_result["response_text"])
        or formal_result["execution_unit_id"] != identity.execution_unit_id
        or formal_result["attempt_id"] != identity.attempt_id
        or formal_result["attempt_count"] != identity.attempt_number
        or formal_result["request_id"] != identity.request_id
    ):
        raise StoreError("STORE_COMMIT_INVALID")
    success_kind = value["success_kind"]
    if success_kind == "provider":
        try:
            success = AuthoritativeSuccess.from_mapping(
                value["authoritative_success"]
            )
            success = validate_authoritative_success(success, identity)
        except (JournalError, TypeError) as exc:
            raise StoreError("STORE_COMMIT_INVALID") from exc
        if (
            value["provider_response_sha256"]
            != success.provider_response_sha256
            or formal_result["authoritative_success"] != success.to_dict()
            or not formal_result["provider_called"]
            or formal_result["response_sha256"] != success.response_sha256
        ):
            raise StoreError("STORE_COMMIT_INVALID")
    elif success_kind == "local":
        if (
            value["authoritative_success"] is not None
            or value["provider_response_sha256"] is not None
            or formal_result["authoritative_success"] is not None
            or formal_result["provider_called"]
        ):
            raise StoreError("STORE_COMMIT_INVALID")
    else:
        raise StoreError("STORE_SCHEMA_INVALID")
    _validate_attempt_lineage(
        value["attempt_lineage"],
        identity=identity,
        success_kind=success_kind,
        state=state,
    )
    _validate_rq3_relationship(
        value["rq3_relationship"],
        plan=plan,
        unit=unit,
        identity=identity,
        formal_result=formal_result,
        run_contract=run_contract,
        turn_one_commit=turn_one_commit,
    )
    return copy.deepcopy(value)


def _commit_path(root: Path, unit: Mapping[str, Any]) -> Path:
    return root / "commits" / (
        f"{unit['execution_order']}-{_execution_unit_id(unit)}.json"
    )


def _load_commit_for_unit_locked(
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
    state: _UnitState | None = None,
    repair_mutable: bool = True,
    allow_owned_temps: bool = False,
) -> dict[str, Any] | None:
    lock.require_active()
    if type(repair_mutable) is not bool or type(allow_owned_temps) is not bool:
        raise StoreError("STORE_SCHEMA_INVALID")
    path = _commit_path(lock.root, unit)
    if not _path_exists(path):
        return None
    if _is_reparse(path) or not _path_is_file(path):
        raise StoreError("STORE_PATH_INVALID")
    turn_one_commit: dict[str, Any] | None = None
    if (
        unit["rq"] == "RQ3"
        and unit["system_config_id"] == "context_aware"
        and unit["turn_index"] == 2
    ):
        pair = _plan_pair(plan, unit)
        assert pair is not None
        turn_one_state = _load_unit_state_locked(
            _execution_unit_id(pair[0]),
            run_contract=run_contract,
            lock=lock,
            repair_mutable=repair_mutable,
            allow_owned_temps=allow_owned_temps,
        )
        turn_one_commit = _load_commit_for_unit_locked(
            plan,
            pair[0],
            run_contract=run_contract,
            lock=lock,
            state=turn_one_state,
            repair_mutable=repair_mutable,
            allow_owned_temps=allow_owned_temps,
        )
        if turn_one_commit is None:
            raise StoreError("STORE_DEPENDENCY_INVALID")
    if state is None:
        state = _load_unit_state_locked(
            _execution_unit_id(unit),
            run_contract=run_contract,
            lock=lock,
            repair_mutable=repair_mutable,
            allow_owned_temps=allow_owned_temps,
        )
    try:
        return _validate_private_commit(
            _read_json(path, _COMMIT_LIMIT),
            plan=plan,
            unit=unit,
            run_contract=run_contract,
            state=state,
            expected_path=path,
            turn_one_commit=turn_one_commit,
        )
    except StoreError as exc:
        if exc.category in {
            "STORE_SCHEMA_INVALID",
            "STORE_HASH_MISMATCH",
            "STORE_COMMIT_INVALID",
        }:
            raise StoreError("STORE_COMMIT_INVALID") from exc
        raise


def _publish_private_commit_locked(
    value: Mapping[str, Any],
    *,
    unit: Mapping[str, Any],
    lock: _RunWideLock,
) -> tuple[dict[str, Any], bool]:
    lock.require_active()
    path = _commit_path(lock.root, unit)
    published = _atomic_publish_json(
        path,
        value,
        replace=False,
        maximum=_COMMIT_LIMIT,
    )
    if not published:
        existing = _read_json(path, _COMMIT_LIMIT)
        if existing != dict(value):
            raise StoreError("STORE_CONFLICTING_FIRST_SUCCESS")
        return existing, False
    if (
        _STAGE_B2_TEST_FAULT_CONTROLLER is not None
        and _STAGE_B2_TEST_FAULT_CONTROLLER.fault_point
        == "after_private_commit_published_exit"
        and _consume_fault("after_private_commit_published_exit")
    ):
        context = _ACTIVE_FAULT_CONTEXT
        if context is None:
            raise StoreError("STORE_TEST_FAULT_INVALID")
        provider_calls = 1 if value["success_kind"] == "provider" else 0
        _write_fault_marker(
            "after_private_commit_published_exit",
            execution_unit_id=value["plan_member_binding"]["execution_unit_id"],
            attempt_number=value["attempt_lineage"]["attempt_number"],
            archive_sha256=context["archive_sha256"],
            private_commit_sha256=value["envelope_sha256"],
            provider_call_count=provider_calls,
        )
        os._exit(92)
    return dict(value), True


def _validate_unit_journal_authority(
    state: _UnitState,
    unit: Mapping[str, Any],
    run_contract: Mapping[str, Any],
) -> None:
    expected_unit_id = _execution_unit_id(unit)
    expected_system = run_contract["formal_system_authority"][
        unit["system_config_id"]
    ]
    expected_resource = run_contract["runtime_resource_authority"]["resources"][
        unit["system_config_id"]
    ]
    for archive in state.archives:
        identity = archive.journal.identity
        if (
            identity.plan_fingerprint != _PLAN_FINGERPRINT
            or identity.execution_unit_id != expected_unit_id
            or identity.execution_order != unit["execution_order"]
            or identity.request_id != unit["request_id"]
            or identity.rq != unit["rq"]
            or identity.case_id != unit["case_id"]
            or identity.dialogue_id
            != (unit["case_id"] if unit["rq"] == "RQ3" else None)
            or identity.turn_index != unit["turn_index"]
            or identity.system_config_id != unit["system_config_id"]
            or identity.formal_system_id
            != expected_system["formal_system_id"]
            or identity.resolved_runtime_system_id
            != expected_system["resolved_runtime_system_id"]
            or identity.payload_sha256 != unit["payload_sha256"]
            or identity.transport_contract_id
            != run_contract["provider_generation_authority"]["transport"][
                "contract_id"
            ]
            or identity.transport_contract_sha256
            != run_contract["provider_generation_authority"]["transport"][
                "contract_sha256"
            ]
            or identity.generation_contract_id
            != run_contract["provider_generation_authority"]["generation"][
                "contract_id"
            ]
            or identity.generation_contract_sha256
            != run_contract["provider_generation_authority"]["generation"][
                "contract_sha256"
            ]
            or identity.resource_identity.to_dict()
            != expected_resource["resource_identity"]
            or identity.resource_identity_sha256
            != expected_resource["resource_identity_sha256"]
        ):
            raise StoreError("STORE_SCHEMA_INVALID")


def _reconcile_commit_locked(
    commit: Mapping[str, Any],
    state: _UnitState,
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
    repair: bool = True,
) -> _UnitState:
    if type(repair) is not bool:
        raise StoreError("STORE_SCHEMA_INVALID")
    if state.tip is None:
        raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
    commit_sha = commit["envelope_sha256"]
    identity = ExecutionIdentity.from_mapping(commit["execution_identity"])
    if commit["success_kind"] == "local":
        if state.tip.journal.state == "prepared":
            if state.tip.value["private_commit_sha256"] is None:
                if repair:
                    _publish_journal_locked(
                        state.tip.journal,
                        run_contract=run_contract,
                        lock=lock,
                        private_commit_sha256=commit_sha,
                    )
            elif state.tip.value["private_commit_sha256"] != commit_sha:
                raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
        else:
            raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
    else:
        success = AuthoritativeSuccess.from_mapping(commit["authoritative_success"])
        if state.tip.journal.state == "provider_returned":
            try:
                decision = recovery_decision(
                    state.tip.journal,
                    authoritative_success=success,
                    expected=identity,
                )
                if decision != "reconcile_committed":
                    raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
                committed = reconcile(state.tip.journal, success, identity)
            except JournalError as exc:
                raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT") from exc
            if repair:
                _publish_journal_locked(
                    committed,
                    run_contract=run_contract,
                    lock=lock,
                    private_commit_sha256=commit_sha,
                )
        elif state.tip.journal.state == "committed":
            if state.tip.value["private_commit_sha256"] != commit_sha:
                raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
            try:
                if (
                    recovery_decision(
                        state.tip.journal,
                        authoritative_success=success,
                        expected=identity,
                    )
                    != "confirmed"
                ):
                    raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
            except JournalError as exc:
                raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT") from exc
        else:
            raise StoreError("STORE_COMMIT_JOURNAL_CONFLICT")
    if not repair:
        return state
    return _load_unit_state_locked(
        identity.execution_unit_id,
        run_contract=run_contract,
        lock=lock,
    )


def _direct_unit_category_locked(
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
) -> tuple[str, _UnitState, dict[str, Any] | None]:
    execution_unit_id = _execution_unit_id(unit)
    state = _load_unit_state_locked(
        execution_unit_id,
        run_contract=run_contract,
        lock=lock,
    )
    _validate_unit_journal_authority(state, unit, run_contract)
    commit = _load_commit_for_unit_locked(
        plan,
        unit,
        run_contract=run_contract,
        lock=lock,
        state=state,
    )
    if commit is not None:
        state = _reconcile_commit_locked(
            commit,
            state,
            run_contract=run_contract,
            lock=lock,
        )
        return "successful", state, commit
    if state.tip is None:
        return "initial-executable", state, None
    if state.tip.value["private_commit_sha256"] is not None:
        raise StoreError("STORE_COMMIT_INVALID")
    journal = state.tip.journal
    if journal.state == "prepared":
        return "same-attempt-continuable", state, None
    if journal.state == "retryable_failed":
        return (
            "retry-constructible"
            if journal.identity.attempt_number < 3
            else "permanently-non-executable",
            state,
            None,
        )
    if journal.state == "committed":
        raise StoreError("STORE_COMMITTED_WITHOUT_PRIVATE_COMMIT")
    if journal.state in {
        "call_started",
        "provider_returned",
        "uncertain",
        "terminal_failed",
    }:
        return "permanently-non-executable", state, None
    raise StoreError("STORE_SCHEMA_INVALID")


def _unit_category_locked(
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
) -> tuple[str, _UnitState, dict[str, Any] | None]:
    if not (
        unit["rq"] == "RQ3"
        and unit["system_config_id"] == "context_aware"
        and unit["turn_index"] == 2
    ):
        return _direct_unit_category_locked(
            plan, unit, run_contract=run_contract, lock=lock
        )
    pair = _plan_pair(plan, unit)
    assert pair is not None
    turn_one = pair[0]
    turn_one_category, _turn_one_state, turn_one_commit = (
        _direct_unit_category_locked(
            plan,
            turn_one,
            run_contract=run_contract,
            lock=lock,
        )
    )
    turn_two_id = _execution_unit_id(unit)
    turn_two_state = _load_unit_state_locked(
        turn_two_id,
        run_contract=run_contract,
        lock=lock,
    )
    if turn_one_commit is None:
        if turn_two_state.archives or _path_exists(_commit_path(lock.root, unit)):
            raise StoreError("STORE_DEPENDENCY_INVALID")
        if turn_one_category == "permanently-non-executable":
            return "permanently-non-executable", turn_two_state, None
        if turn_one_category not in {
            "initial-executable",
            "same-attempt-continuable",
            "retry-constructible",
        }:
            raise StoreError("STORE_DEPENDENCY_INVALID")
        return "dependency-blocked", turn_two_state, None
    return _direct_unit_category_locked(
        plan, unit, run_contract=run_contract, lock=lock
    )


def _validate_known_store_members(
    plan: Sequence[Mapping[str, Any]],
    lock: _RunWideLock,
    *,
    allow_owned_temps: bool = False,
) -> None:
    if type(allow_owned_temps) is not bool:
        raise StoreError("STORE_SCHEMA_INVALID")
    known_ids = {_execution_unit_id(unit) for unit in plan}
    for path in _path_iterdir(lock.root / "journals"):
        if allow_owned_temps and _owned_temp_kind(path) == "mutable":
            continue
        if path.stem not in known_ids:
            raise StoreError("STORE_SCHEMA_INVALID")
    for path in _path_iterdir(lock.root / "attempts"):
        if path.name not in known_ids:
            raise StoreError("STORE_SCHEMA_INVALID")
    expected_commits = {
        _commit_path(lock.root, unit).name for unit in plan
    }
    for path in _path_iterdir(lock.root / "commits"):
        if allow_owned_temps and _owned_temp_kind(path) == "commit":
            continue
        if path.name not in expected_commits:
            raise StoreError("STORE_SCHEMA_INVALID")


def _derive_durable_progress_locked(
    plan: Sequence[Mapping[str, Any]],
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
) -> DurableProgress:
    if type(lock) is not _RunWideLock:
        raise StoreError("STORE_LOCK_BUSY")
    lock.require_active()
    if (
        type(run_contract) is not dict
        or run_contract["run_contract_sha256"]
        != _read_json(lock.root / "run_contract.json", _RUN_CONTRACT_LIMIT)[
            "run_contract_sha256"
        ]
    ):
        raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
    try:
        from run_formal_evaluation import (
            PLAN_FINGERPRINT,
            plan_fingerprint,
            validate_plan,
        )

        if type(plan) is not list:
            raise StoreError("STORE_SCHEMA_INVALID")
        validate_plan(plan)
        if (
            plan_fingerprint(plan) != PLAN_FINGERPRINT
            or len(plan) != 190
        ):
            raise StoreError("STORE_SCHEMA_INVALID")
    except StoreError:
        raise
    except Exception as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc
    _validate_store_layout_locked(lock)
    _validate_known_store_members(plan, lock)
    categories: dict[str, str] = {}
    successful_by_rq = {"RQ1": 0, "RQ2": 0, "RQ3": 0}
    successful_by_system = {
        "qa_only_reconstructed_baseline": 0,
        "v2": 0,
        "single_turn": 0,
        "context_aware": 0,
    }
    eligible_orders: list[int] = []
    counts = {
        "successful": 0,
        "initial-executable": 0,
        "same-attempt-continuable": 0,
        "retry-constructible": 0,
        "dependency-blocked": 0,
        "permanently-non-executable": 0,
    }
    for unit in plan:
        unit_id = _execution_unit_id(unit)
        if unit_id in categories:
            raise StoreError("STORE_SCHEMA_INVALID")
        category, _state, _commit = _unit_category_locked(
            plan,
            unit,
            run_contract=run_contract,
            lock=lock,
        )
        if category not in counts:
            raise StoreError("STORE_SCHEMA_INVALID")
        categories[unit_id] = category
        counts[category] += 1
        if category == "successful":
            successful_by_rq[unit["rq"]] += 1
            successful_by_system[unit["system_config_id"]] += 1
        if category in {
            "initial-executable",
            "same-attempt-continuable",
            "retry-constructible",
        }:
            eligible_orders.append(unit["execution_order"])
    if len(categories) != 190 or sum(counts.values()) != 190:
        raise StoreError("STORE_SCHEMA_INVALID")
    successful = counts["successful"]
    remaining = 190 - successful
    next_order = min(eligible_orders) if eligible_orders else None
    if eligible_orders:
        run_state = "in_progress"
    elif successful == 190:
        run_state = "complete"
    elif counts["permanently-non-executable"] >= 1:
        run_state = "permanently_blocked"
    elif counts["dependency-blocked"] == remaining and remaining > 0:
        run_state = "temporarily_blocked"
    else:
        raise StoreError("STORE_SCHEMA_INVALID")
    return DurableProgress(
        schema_version=1,
        run_state=run_state,
        total_successful_units=successful,
        successful_by_rq=successful_by_rq,
        successful_by_system=successful_by_system,
        remaining_units=remaining,
        next_eligible_execution_order=next_order,
        initial_executable_units=counts["initial-executable"],
        same_attempt_continuable_units=counts["same-attempt-continuable"],
        retry_constructible_units=counts["retry-constructible"],
        dependency_blocked_units=counts["dependency-blocked"],
        permanently_non_executable_units=counts[
            "permanently-non-executable"
        ],
    )


def _validate_test_controller_before_lock() -> None:
    controller = _STAGE_B2_TEST_FAULT_CONTROLLER
    if controller is None:
        return
    if (
        type(controller) is not _StageB2TestFaultControllerV1
        or controller.root != _PRIVATE_STATE_ROOT
        or controller.root == _PRODUCTION_PRIVATE_STATE_ROOT
    ):
        raise StoreError("STORE_TEST_FAULT_INVALID")


@contextmanager
def _open_store(
    expected_contract: Mapping[str, Any],
) -> Iterator[tuple[dict[str, Any], _RunWideLock]]:
    _validate_test_controller_before_lock()
    if type(expected_contract) is not dict:
        raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
    _validate_run_contract_shape(
        json.loads(_canonical_bytes(expected_contract))
    )
    active = getattr(_PREFIX_LOCK_CONTEXT, "active", None)
    if active is not None:
        if (
            type(active) is not tuple
            or len(active) != 2
            or type(active[0]) is not dict
            or type(active[1]) is not _RunWideLock
            or active[0] != dict(expected_contract)
        ):
            raise StoreError("STORE_LOCK_BUSY")
        active[1].require_active()
        yield active
        return
    with _RunWideLock(_PRIVATE_STATE_ROOT) as lock:
        contract = _open_contract_locked(expected_contract, lock)
        _ensure_fixed_directories(lock.root)
        _clean_owned_temps_locked(lock.root, lock)
        _validate_store_layout_locked(lock)
        yield contract, lock


@contextmanager
def _open_store_read_only(
    expected_contract: Mapping[str, Any],
) -> Iterator[tuple[dict[str, Any], _RunWideLock]]:
    """Open an existing canonical store without creation, cleanup, or repair."""

    if _STAGE_B2_TEST_FAULT_CONTROLLER is not None:
        raise StoreError("STORE_TEST_FAULT_INVALID")
    if type(expected_contract) is not dict:
        raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
    _validate_run_contract_shape(json.loads(_canonical_bytes(expected_contract)))
    root = _validate_root(_PRIVATE_STATE_ROOT)
    if not _path_exists(root) or _is_reparse(root) or not _path_is_dir(root):
        raise StoreError("STORE_PATH_INVALID")
    required_files = (root / "run.lock", root / "run_contract.json")
    required_directories = (
        root / "journals",
        root / "attempts",
        root / "commits",
    )
    for path in required_files:
        if not _path_exists(path) or _is_reparse(path) or not _path_is_file(path):
            raise StoreError(
                "STORE_LOCK_FILE_INVALID"
                if path.name == "run.lock"
                else "STORE_STATE_WITHOUT_CONTRACT"
            )
    for path in required_directories:
        if not _path_exists(path) or _is_reparse(path) or not _path_is_dir(path):
            raise StoreError("STORE_PATH_INVALID")
    with _RunWideLock(root, create_missing=False) as lock:
        contract_path = root / "run_contract.json"
        contract = _read_json(contract_path, _RUN_CONTRACT_LIMIT)
        _validate_run_contract_shape(contract)
        if (
            contract != dict(expected_contract)
            or _path_read_bytes(contract_path)
            != _canonical_bytes(expected_contract) + b"\n"
        ):
            raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
        _validate_store_layout_locked(lock, allow_owned_temps=True)
        yield contract, lock


def _validate_observation_plan(plan: list[dict[str, Any]]) -> None:
    try:
        from run_formal_evaluation import (
            PLAN_FINGERPRINT,
            plan_fingerprint,
            validate_plan,
        )

        if type(plan) is not list:
            raise StoreError("STORE_SCHEMA_INVALID")
        validate_plan(plan)
        if (
            PLAN_FINGERPRINT != _PLAN_FINGERPRINT
            or plan_fingerprint(plan) != _PLAN_FINGERPRINT
            or len(plan) != 190
            or [unit["execution_order"] for unit in plan] != list(range(1, 191))
        ):
            raise StoreError("STORE_SCHEMA_INVALID")
    except StoreError:
        raise
    except Exception as exc:
        raise StoreError("STORE_SCHEMA_INVALID") from exc


def _canonical_private_result(
    commit: Mapping[str, Any],
) -> CanonicalPrivateResultV1:
    binding = commit["plan_member_binding"]
    result = commit["formal_result"]
    relationship = commit["rq3_relationship"]
    try:
        return CanonicalPrivateResultV1(
            schema_version=1,
            plan_fingerprint=binding["plan_fingerprint"],
            run_contract_sha256=commit["run_contract_sha256"],
            plan_member_sha256=binding["plan_member_sha256"],
            execution_unit_id=binding["execution_unit_id"],
            execution_order=binding["execution_order"],
            request_id=binding["request_id"],
            rq=binding["rq"],
            case_id=binding["case_id"],
            dialogue_id=binding["dialogue_id"],
            turn_index=binding["turn_index"],
            system_config_id=binding["system_config_id"],
            formal_system_id=binding["formal_system_id"],
            envelope_sha256=commit["envelope_sha256"],
            response_text=result["response_text"],
            response_sha256=commit["response_sha256"],
            rq3_relationship_kind=relationship["kind"],
            turn_one_commit_sha256=relationship["turn_one_commit_sha256"],
            checkpoint_record_sha256=relationship[
                "checkpoint_record_sha256"
            ],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise StoreError("STORE_COMMIT_INVALID") from exc


def _observe_validated_canonical_private_results(
    plan: list[dict[str, Any]],
    expected_contract: Mapping[str, Any],
) -> tuple[CanonicalPrivateResultV1, ...]:
    """Return detached canonical commits while preserving all durable bytes."""

    _validate_observation_plan(plan)
    with _open_store_read_only(expected_contract) as (contract, lock):
        _validate_known_store_members(
            plan, lock, allow_owned_temps=True
        )
        observed: list[CanonicalPrivateResultV1] = []
        for unit in plan:
            execution_unit_id = _execution_unit_id(unit)
            state = _load_unit_state_locked(
                execution_unit_id,
                run_contract=contract,
                lock=lock,
                repair_mutable=False,
                allow_owned_temps=True,
            )
            _validate_unit_journal_authority(state, unit, contract)
            commit = _load_commit_for_unit_locked(
                plan,
                unit,
                run_contract=contract,
                lock=lock,
                state=state,
                repair_mutable=False,
                allow_owned_temps=True,
            )
            if commit is None:
                if (
                    state.tip is not None
                    and state.tip.value["private_commit_sha256"] is not None
                ):
                    raise StoreError("STORE_COMMIT_INVALID")
                continue
            _reconcile_commit_locked(
                commit,
                state,
                run_contract=contract,
                lock=lock,
                repair=False,
            )
            observed.append(_canonical_private_result(commit))
        return tuple(observed)


def _durable_progress(
    plan: list[dict[str, Any]],
    expected_contract: Mapping[str, Any],
) -> DurableProgress:
    with _open_store(expected_contract) as (contract, lock):
        return _derive_durable_progress_locked(
            plan,
            run_contract=contract,
            lock=lock,
        )


def _block_category(journal: InflightJournal) -> str:
    if journal.state == "call_started":
        return "call_started"
    if journal.state == "provider_returned":
        return "provider_returned_without_commit"
    if journal.state == "uncertain":
        return "uncertain"
    if journal.state == "terminal_failed":
        return "terminal_failed"
    if journal.state == "retryable_failed" and journal.identity.attempt_number == 3:
        return "attempts_exhausted"
    raise StoreError("STORE_SCHEMA_INVALID")


def _contiguous_prefix_outcome_locked(
    plan: list[dict[str, Any]],
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
    new_successes: int = 0,
) -> DurablePrefixOutcome:
    """Validate the exact successful prefix without making later units eligible."""

    progress = _derive_durable_progress_locked(
        plan, run_contract=run_contract, lock=lock
    )
    prefix = 0
    first_non_success: tuple[
        str, _UnitState, dict[str, Any] | None, Mapping[str, Any]
    ] | None = None
    gap_seen = False
    for unit in plan:
        category, state, commit = _unit_category_locked(
            plan, unit, run_contract=run_contract, lock=lock
        )
        if category == "successful":
            if gap_seen:
                raise StoreError("STORE_COMMIT_INVALID")
            prefix += 1
            continue
        gap_seen = True
        if first_non_success is None:
            first_non_success = (category, state, commit, unit)
    if prefix != progress.total_successful_units:
        raise StoreError("STORE_COMMIT_INVALID")
    if prefix == 190:
        if first_non_success is not None or progress.run_state != "complete":
            raise StoreError("STORE_SCHEMA_INVALID")
        return DurablePrefixOutcome(1, "run_complete", new_successes, None, progress)
    if first_non_success is None:
        raise StoreError("STORE_SCHEMA_INVALID")
    category, state, _commit, unit = first_non_success
    if unit["execution_order"] != prefix + 1:
        raise StoreError("STORE_SCHEMA_INVALID")
    if category in {
        "initial-executable",
        "same-attempt-continuable",
        "retry-constructible",
    }:
        return DurablePrefixOutcome(
            1,
            "ready" if new_successes == 0 else "prefix_paused",
            new_successes,
            None,
            progress,
        )
    if category == "dependency-blocked":
        block = "dependency_missing"
    elif category == "permanently-non-executable":
        dependency_permanent = (
            unit["rq"] == "RQ3"
            and unit["system_config_id"] == "context_aware"
            and unit["turn_index"] == 2
            and state.tip is None
        )
        block = (
            "dependency_permanent"
            if dependency_permanent
            else _block_category(state.tip.journal)
            if state.tip is not None
            else None
        )
        if block is None:
            raise StoreError("STORE_SCHEMA_INVALID")
    else:
        raise StoreError("STORE_SCHEMA_INVALID")
    return DurablePrefixOutcome(1, "blocked", new_successes, block, progress)


def _retry_predecessor(state: _UnitState) -> InflightJournal | None:
    if state.tip is None or state.tip.journal.identity.attempt_number == 1:
        return None
    attempt = state.tip.journal.identity.attempt_number
    candidates = [
        archive
        for archive in state.archives
        if archive.value["attempt_number"] == attempt - 1
    ]
    if not candidates or candidates[-1].journal.state != "retryable_failed":
        raise StoreError("STORE_PREDECESSOR_INVALID")
    return candidates[-1].journal


def _selected_dependency_commit(
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    *,
    run_contract: Mapping[str, Any],
    lock: _RunWideLock,
) -> tuple[CheckpointEvidence | None, str | None]:
    if not (
        unit["rq"] == "RQ3"
        and unit["system_config_id"] == "context_aware"
        and unit["turn_index"] == 2
    ):
        return None, None
    pair = _plan_pair(plan, unit)
    assert pair is not None
    turn_one_state = _load_unit_state_locked(
        _execution_unit_id(pair[0]),
        run_contract=run_contract,
        lock=lock,
    )
    turn_one_commit = _load_commit_for_unit_locked(
        plan,
        pair[0],
        run_contract=run_contract,
        lock=lock,
        state=turn_one_state,
    )
    if turn_one_commit is None:
        return None, None
    relationship = turn_one_commit["rq3_relationship"]
    try:
        checkpoint = CheckpointEvidence.from_mapping(
            relationship["checkpoint_evidence"]
        )
    except (OrchestrationError, TypeError) as exc:
        raise StoreError("STORE_DEPENDENCY_INVALID") from exc
    return checkpoint, turn_one_commit["envelope_sha256"]


def _orchestrate_durable_offline_unit(
    plan: list[dict[str, Any]],
    unit: dict[str, Any] | None,
    *,
    expected_contract: Mapping[str, Any],
    authority: Any,
) -> DurableExecutionOutcome:
    global _ACTIVE_FAULT_CONTEXT
    with _open_store(expected_contract) as (contract, lock):
        progress_before = _derive_durable_progress_locked(
            plan, run_contract=contract, lock=lock
        )
        if unit is None:
            if progress_before.run_state == "complete":
                return DurableExecutionOutcome(
                    1,
                    "run_complete",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    0,
                    None,
                    progress_before,
                )
            if progress_before.next_eligible_execution_order is None:
                return DurableExecutionOutcome(
                    1,
                    "no_eligible",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    0,
                    None,
                    progress_before,
                )
            selected = next(
                candidate
                for candidate in plan
                if candidate["execution_order"]
                == progress_before.next_eligible_execution_order
            )
        else:
            selected = unit
        unit_id = _execution_unit_id(selected)
        category, state, commit = _unit_category_locked(
            plan,
            selected,
            run_contract=contract,
            lock=lock,
        )
        if category == "successful":
            assert commit is not None and state.tip is not None
            progress = _derive_durable_progress_locked(
                plan, run_contract=contract, lock=lock
            )
            return DurableExecutionOutcome(
                1,
                "completed",
                unit_id,
                selected["execution_order"],
                state.tip.journal.identity.attempt_number,
                state.tip.journal.state,
                commit["envelope_sha256"],
                None,
                0,
                None,
                progress,
            )
        if category == "dependency-blocked":
            progress = _derive_durable_progress_locked(
                plan, run_contract=contract, lock=lock
            )
            return DurableExecutionOutcome(
                1,
                "dependency_blocked",
                unit_id,
                selected["execution_order"],
                None,
                None,
                None,
                "dependency_missing",
                0,
                None,
                progress,
            )
        if category == "permanently-non-executable":
            dependency_permanent = (
                selected["rq"] == "RQ3"
                and selected["system_config_id"] == "context_aware"
                and selected["turn_index"] == 2
                and state.tip is None
            )
            block = (
                "dependency_permanent"
                if dependency_permanent
                else _block_category(state.tip.journal)
                if state.tip is not None
                else None
            )
            if block is None:
                raise StoreError("STORE_SCHEMA_INVALID")
            progress = _derive_durable_progress_locked(
                plan, run_contract=contract, lock=lock
            )
            return DurableExecutionOutcome(
                1,
                "permanently_non_executable",
                unit_id,
                selected["execution_order"],
                None
                if dependency_permanent
                else state.tip.journal.identity.attempt_number,
                None if dependency_permanent else state.tip.journal.state,
                None,
                block,
                0,
                None,
                progress,
            )
        if category == "retry-constructible":
            assert state.tip is not None
            clock = authority.clock_for(selected, state)
            try:
                new_journal = next_retry_journal(
                    state.tip.journal,
                    clock(),
                )
            except JournalError as exc:
                raise StoreError("STORE_PREDECESSOR_INVALID") from exc
            archive = _publish_journal_locked(
                new_journal,
                run_contract=contract,
                lock=lock,
            )
            progress = _derive_durable_progress_locked(
                plan, run_contract=contract, lock=lock
            )
            return DurableExecutionOutcome(
                1,
                "retry_constructed",
                unit_id,
                selected["execution_order"],
                new_journal.identity.attempt_number,
                "prepared",
                None,
                None,
                0,
                None,
                progress,
            )
        if category not in {
            "initial-executable",
            "same-attempt-continuable",
        }:
            raise StoreError("STORE_SCHEMA_INVALID")
        checkpoint, turn_one_commit_sha = _selected_dependency_commit(
            plan,
            selected,
            run_contract=contract,
            lock=lock,
        )
        predecessor = _retry_predecessor(state)
        dependencies = authority.dependencies_for(selected, state)

        def persistence_callback(journal: InflightJournal) -> None:
            _publish_journal_locked(
                journal,
                run_contract=contract,
                lock=lock,
            )
            return None

        try:
            from run_formal_evaluation import orchestrate_offline_unit

            orchestration = orchestrate_offline_unit(
                plan,
                selected,
                journal_persistence_callback=persistence_callback,
                retry_predecessor=predecessor,
                journal=state.tip.journal if state.tip is not None else None,
                checkpoint_evidence=checkpoint,
                **dependencies,
            )
        except StoreError:
            raise
        finally:
            if _STAGE_B2_TEST_FAULT_CONTROLLER is None:
                _ACTIVE_FAULT_CONTEXT = None
        state = _load_unit_state_locked(
            unit_id,
            run_contract=contract,
            lock=lock,
        )
        if orchestration.action == "retry_available":
            progress = _derive_durable_progress_locked(
                plan, run_contract=contract, lock=lock
            )
            assert state.tip is not None
            return DurableExecutionOutcome(
                1,
                "advanced",
                unit_id,
                selected["execution_order"],
                state.tip.journal.identity.attempt_number,
                state.tip.journal.state,
                None,
                None,
                orchestration.provider_call_count,
                orchestration,
                progress,
            )
        if orchestration.action == "fail_closed":
            if state.tip is None:
                raise StoreError("STORE_SCHEMA_INVALID")
            progress = _derive_durable_progress_locked(
                plan, run_contract=contract, lock=lock
            )
            return DurableExecutionOutcome(
                1,
                "permanently_non_executable",
                unit_id,
                selected["execution_order"],
                state.tip.journal.identity.attempt_number,
                state.tip.journal.state,
                None,
                _block_category(state.tip.journal),
                0,
                None,
                progress,
            )
        if orchestration.action not in {"success", "local_success"}:
            raise StoreError("STORE_SCHEMA_INVALID")
        commit_candidate = _construct_private_commit(
            plan,
            selected,
            orchestration,
            run_contract=contract,
            state=state,
            turn_one_commit_sha256=turn_one_commit_sha,
        )
        if _ACTIVE_FAULT_CONTEXT is not None:
            _ACTIVE_FAULT_CONTEXT["provider_call_count"] = (
                orchestration.provider_call_count
            )
        commit, _published = _publish_private_commit_locked(
            commit_candidate,
            unit=selected,
            lock=lock,
        )
        state = _reconcile_commit_locked(
            commit,
            state,
            run_contract=contract,
            lock=lock,
        )
        progress = _derive_durable_progress_locked(
            plan, run_contract=contract, lock=lock
        )
        assert state.tip is not None
        return DurableExecutionOutcome(
            1,
            "completed",
            unit_id,
            selected["execution_order"],
            state.tip.journal.identity.attempt_number,
            state.tip.journal.state,
            commit["envelope_sha256"],
            None,
            orchestration.provider_call_count,
            orchestration,
            progress,
        )


def _real_prefix_progress(
    plan: list[dict[str, Any]],
    expected_contract: Mapping[str, Any],
) -> DurablePrefixOutcome:
    """Create/reopen the store and validate the real contiguous-prefix boundary."""

    if (
        type(expected_contract) is not dict
        or expected_contract.get("stage_id") != "B5"
        or expected_contract.get("provider_generation_authority", {})
        .get("real_execution", {})
        .get("mode")
        != "production_real"
    ):
        raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
    with _open_store(expected_contract) as (contract, lock):
        return _contiguous_prefix_outcome_locked(
            plan, run_contract=contract, lock=lock
        )


@contextmanager
def _real_prefix_invocation(
    plan: list[dict[str, Any]],
    expected_contract: Mapping[str, Any],
) -> Iterator[DurablePrefixOutcome]:
    """Hold the run-wide lock from progress authorization through execution."""

    if (
        type(expected_contract) is not dict
        or expected_contract.get("stage_id") != "B5"
        or expected_contract.get("provider_generation_authority", {})
        .get("real_execution", {})
        .get("mode")
        != "production_real"
    ):
        raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
    if getattr(_PREFIX_LOCK_CONTEXT, "active", None) is not None:
        raise StoreError("STORE_LOCK_BUSY")
    with _open_store(expected_contract) as (contract, lock):
        _PREFIX_LOCK_CONTEXT.active = (contract, lock)
        try:
            yield _contiguous_prefix_outcome_locked(
                plan, run_contract=contract, lock=lock
            )
        finally:
            del _PREFIX_LOCK_CONTEXT.active


def _orchestrate_durable_prefix_locked(
    plan: list[dict[str, Any]],
    *,
    contract: dict[str, Any],
    lock: _RunWideLock,
    authority: Any,
    max_new_successes: int,
) -> DurablePrefixOutcome:
    state = _contiguous_prefix_outcome_locked(
        plan, run_contract=contract, lock=lock
    )
    if state.action in {"blocked", "run_complete"}:
        return state
    new_successes = 0
    while new_successes < max_new_successes:
        selected_order = state.progress.total_successful_units + 1
        selected = next(
            (
                unit
                for unit in plan
                if unit["execution_order"] == selected_order
            ),
            None,
        )
        if selected is None:
            raise StoreError("STORE_SCHEMA_INVALID")
        outcome = _orchestrate_durable_offline_unit(
            plan,
            selected,
            expected_contract=contract,
            authority=authority,
        )
        if outcome.action == "completed":
            new_successes += 1
        elif outcome.action not in {"advanced", "retry_constructed"}:
            state = _contiguous_prefix_outcome_locked(
                plan,
                run_contract=contract,
                lock=lock,
                new_successes=new_successes,
            )
            if state.action != "blocked":
                raise StoreError("STORE_SCHEMA_INVALID")
            return state
        state = _contiguous_prefix_outcome_locked(
            plan,
            run_contract=contract,
            lock=lock,
            new_successes=new_successes,
        )
        if state.action in {"blocked", "run_complete"}:
            return state
    if state.action != "prefix_paused":
        raise StoreError("STORE_SCHEMA_INVALID")
    return state


def _orchestrate_durable_prefix(
    plan: list[dict[str, Any]],
    *,
    expected_contract: Mapping[str, Any],
    authority: Any,
    max_new_successes: int,
) -> DurablePrefixOutcome:
    """Execute only the next contiguous units while holding one run-wide lock."""

    if type(max_new_successes) is not int or not 1 <= max_new_successes <= 190:
        raise StoreError("STORE_SCHEMA_INVALID")
    if (
        type(expected_contract) is not dict
        or expected_contract.get("stage_id") != "B5"
        or expected_contract.get("provider_generation_authority", {})
        .get("real_execution", {})
        .get("mode")
        != "production_real"
    ):
        raise StoreError("STORE_RUN_CONTRACT_MISMATCH")
    active = getattr(_PREFIX_LOCK_CONTEXT, "active", None)
    if active is not None:
        if (
            type(active) is not tuple
            or len(active) != 2
            or type(active[0]) is not dict
            or type(active[1]) is not _RunWideLock
            or active[0] != dict(expected_contract)
        ):
            raise StoreError("STORE_LOCK_BUSY")
        active[1].require_active()
        return _orchestrate_durable_prefix_locked(
            plan,
            contract=active[0],
            lock=active[1],
            authority=authority,
            max_new_successes=max_new_successes,
        )
    with _real_prefix_invocation(plan, expected_contract):
        active = getattr(_PREFIX_LOCK_CONTEXT, "active", None)
        if active is None:
            raise StoreError("STORE_LOCK_BUSY")
        return _orchestrate_durable_prefix_locked(
            plan,
            contract=active[0],
            lock=active[1],
            authority=authority,
            max_new_successes=max_new_successes,
        )
