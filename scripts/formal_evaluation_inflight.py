"""Fail-closed Stage A in-flight identity, journal, and recovery primitives.

The module is synthetic/offline only.  It does not invoke providers or inspect
referenced resources.  Durable cross-process orchestration remains Stage B.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from formal_evaluation_transport import (
    _CanonicalProductionResourceIdentity as _ProductionResourceIdentity,
    TransportError as _TransportError,
    _formal_identity,
    _generation_contract_id,
    _generation_contract_sha256,
    _resource_identity_sha256,
    _transport_contract_id,
    _transport_contract_sha256,
    _validate_provider_identity,
    _validate_resource_identity,
    _validate_sha256,
)

_FROZEN_PLAN_FINGERPRINT = (
    "4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"
)
PLAN_FINGERPRINT = _FROZEN_PLAN_FINGERPRINT  # compatibility snapshot only
_MAX_ATTEMPTS = 3
MAX_ATTEMPTS = _MAX_ATTEMPTS
_SHA = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_UTC_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_STATES = frozenset(
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
_RETRYABLE_OUTCOMES = frozenset(
    {"pre_send_failure", "http_429", "http_5xx", "temporary_unavailable"}
)
_TERMINAL_OUTCOMES = frozenset(
    {"authentication_failure", "invalid_request", "provider_rejected", "invalid_response"}
)
_UNCERTAIN_OUTCOMES = frozenset(
    {"timeout", "read_timeout", "connection_reset", "broken_pipe", "connection_error", "unknown"}
)
SHA = _SHA
SAFE_ID = _SAFE_ID
UTC_TIMESTAMP = _UTC_TIMESTAMP
STATES = frozenset(_STATES)
RETRYABLE_OUTCOMES = frozenset(_RETRYABLE_OUTCOMES)
TERMINAL_OUTCOMES = frozenset(_TERMINAL_OUTCOMES)
UNCERTAIN_OUTCOMES = frozenset(_UNCERTAIN_OUTCOMES)
_POST_CALL_RETRYABLE = _RETRYABLE_OUTCOMES - {"pre_send_failure"}


class JournalError(RuntimeError):
    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _derive(namespace: str, *parts: object) -> str:
    if type(namespace) is not str:
        raise JournalError("DERIVATION_INPUT_INVALID")
    material = _canonical_json({"domain": namespace, "parts": list(parts)})
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def _safe_id(value: object) -> bool:
    return type(value) is str and _SAFE_ID.fullmatch(value) is not None


def _parse_timestamp(value: object) -> datetime:
    if type(value) is not str or len(value) != 20 or _UTC_TIMESTAMP.fullmatch(value) is None:
        raise JournalError("JOURNAL_TIMESTAMP_INVALID")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise JournalError("JOURNAL_TIMESTAMP_INVALID") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise JournalError("JOURNAL_TIMESTAMP_INVALID")
    return parsed


def _strictly_after(later: str, earlier: str) -> bool:
    return _parse_timestamp(later) > _parse_timestamp(earlier)


def _derive_execution_unit_id(
    *, plan_fingerprint: str, request_id: str, execution_order: int
) -> str:
    if (
        plan_fingerprint != _FROZEN_PLAN_FINGERPRINT
        or not _sha(request_id)
        or type(execution_order) is not int
        or not 1 <= execution_order <= 190
    ):
        raise JournalError("EXECUTION_IDENTITY_INVALID")
    return _derive("formal-execution-unit-v1", plan_fingerprint, request_id, execution_order)


def derive_execution_unit_id(
    *, plan_fingerprint: str, request_id: str, execution_order: int
) -> str:
    return _derive_execution_unit_id(
        plan_fingerprint=plan_fingerprint,
        request_id=request_id,
        execution_order=execution_order,
    )


def _derive_attempt_id(
    identity: "ExecutionIdentity | Mapping[str, Any]", attempt_number: int
) -> str:
    if type(attempt_number) is not int or not 1 <= attempt_number <= _MAX_ATTEMPTS:
        raise JournalError("ATTEMPT_IDENTITY_INVALID")
    return "attempt_" + _derive(
        "formal-provider-attempt-v2",
        _canonical_base_execution_identity(identity),
        attempt_number,
    )


def derive_attempt_id(
    *, identity: "ExecutionIdentity | Mapping[str, Any]", attempt_number: int
) -> str:
    """Derive an attempt ID from the complete non-derived execution authority."""
    return _derive_attempt_id(identity, attempt_number)


def _derive_turn_id(
    *,
    execution_unit_id: str,
    rq: str,
    case_id: str,
    turn_index: int,
) -> str:
    if (
        not _sha(execution_unit_id)
        or rq not in {"RQ1", "RQ2", "RQ3"}
        or not _safe_id(case_id)
        or type(turn_index) is not int
        or turn_index not in {1, 2}
    ):
        raise JournalError("TURN_IDENTITY_INVALID")
    return "turn_" + _derive(
        "formal-execution-turn-v1", execution_unit_id, rq, case_id, turn_index
    )


def derive_turn_id(
    *, execution_unit_id: str, rq: str, case_id: str, turn_index: int
) -> str:
    return _derive_turn_id(
        execution_unit_id=execution_unit_id,
        rq=rq,
        case_id=case_id,
        turn_index=turn_index,
    )


def _derive_provider_request_id(identity: "ExecutionIdentity") -> str:
    _validate_execution_identity(identity)
    return "call_" + _derive(
        "formal-provider-call-v2",
        _canonical_attempt_authority(identity),
    )


def derive_provider_request_id(identity: "ExecutionIdentity") -> str:
    return _derive_provider_request_id(identity)


def derive_provider_call_id(identity: "ExecutionIdentity") -> str:
    """Compatibility alias for the canonical provider request-ID derivation."""
    return _derive_provider_request_id(identity)


def _derive_checkpoint_id(
    *,
    plan_fingerprint: str,
    execution_unit_id: str,
    dialogue_id: str,
    system_config_id: str,
    input_checkpoint_sha256: str,
) -> str:
    if (
        plan_fingerprint != _FROZEN_PLAN_FINGERPRINT
        or not _sha(execution_unit_id)
        or not _safe_id(dialogue_id)
        or system_config_id != "context_aware"
        or not _sha(input_checkpoint_sha256)
    ):
        raise JournalError("CHECKPOINT_IDENTITY_INVALID")
    return "checkpoint_" + _derive(
        "formal-context-checkpoint-v1",
        plan_fingerprint,
        execution_unit_id,
        dialogue_id,
        system_config_id,
        input_checkpoint_sha256,
    )


def derive_checkpoint_id(
    *,
    plan_fingerprint: str,
    execution_unit_id: str,
    dialogue_id: str,
    system_config_id: str,
    input_checkpoint_sha256: str,
) -> str:
    return _derive_checkpoint_id(
        plan_fingerprint=plan_fingerprint,
        execution_unit_id=execution_unit_id,
        dialogue_id=dialogue_id,
        system_config_id=system_config_id,
        input_checkpoint_sha256=input_checkpoint_sha256,
    )


@dataclass(frozen=True)
class ExecutionIdentity:
    plan_fingerprint: str
    execution_unit_id: str
    execution_order: int
    request_id: str
    rq: str
    case_id: str
    dialogue_id: str | None
    turn_index: int
    turn_id: str
    system_config_id: str
    formal_system_id: str
    resolved_runtime_system_id: str
    payload_sha256: str
    resolved_payload_sha256: str
    transport_contract_id: str
    transport_contract_sha256: str
    generation_contract_id: str
    generation_contract_sha256: str
    resource_identity: _ProductionResourceIdentity
    resource_identity_sha256: str
    input_checkpoint_id: str | None
    input_checkpoint_sha256: str | None
    attempt_number: int
    attempt_id: str
    provider: str
    provider_model: str

    def __post_init__(self) -> None:
        _validate_execution_identity(self)

    def to_dict(self) -> dict[str, Any]:
        _validate_execution_identity(self)
        result = {field.name: getattr(self, field.name) for field in fields(self)}
        result["resource_identity"] = self.resource_identity.to_dict()
        return result

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExecutionIdentity":
        if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:
            raise JournalError("EXECUTION_IDENTITY_INVALID")
        resource_value = value.get("resource_identity")
        try:
            resource = _ProductionResourceIdentity.from_mapping(resource_value)
            data = dict(value)
            data["resource_identity"] = resource
            return cls(**data)
        except (TypeError, _TransportError, JournalError) as exc:
            if isinstance(exc, JournalError):
                raise
            raise JournalError("EXECUTION_IDENTITY_INVALID") from exc


_CanonicalExecutionIdentity = ExecutionIdentity


_IDENTITY_FIELDS = frozenset(field.name for field in fields(ExecutionIdentity))
_BASE_EXECUTION_FIELDS = frozenset(
    {
        "plan_fingerprint",
        "execution_unit_id",
        "execution_order",
        "request_id",
        "rq",
        "case_id",
        "dialogue_id",
        "turn_index",
        "system_config_id",
        "formal_system_id",
        "resolved_runtime_system_id",
        "payload_sha256",
        "resolved_payload_sha256",
        "transport_contract_id",
        "transport_contract_sha256",
        "generation_contract_id",
        "generation_contract_sha256",
        "resource_identity",
        "resource_identity_sha256",
        "input_checkpoint_sha256",
        "provider",
        "provider_model",
    }
)


def _canonical_base_execution_identity(
    value: ExecutionIdentity | Mapping[str, Any],
) -> str:
    """Return the domain-separated, complete, non-derived execution authority.

    ``turn_id``, ``input_checkpoint_id``, ``attempt_number``, and ``attempt_id``
    are omitted because they are derived separately.  The execution-unit ID is
    retained deliberately as the already-validated plan-unit binding.
    """
    if type(value) is ExecutionIdentity:
        authority = {name: getattr(value, name) for name in _BASE_EXECUTION_FIELDS}
    elif type(value) is dict and set(value) == _BASE_EXECUTION_FIELDS:
        authority = dict(value)
    else:
        raise JournalError("ATTEMPT_IDENTITY_INVALID")
    resource = authority["resource_identity"]
    if type(resource) is _ProductionResourceIdentity:
        authority["resource_identity"] = resource.to_dict()
    elif type(resource) is dict:
        authority["resource_identity"] = dict(resource)
    else:
        raise JournalError("ATTEMPT_IDENTITY_INVALID")
    try:
        return _canonical_json(
            {
                "domain": "formal-base-execution-identity-v1",
                "authority": authority,
            }
        )
    except (TypeError, ValueError) as exc:
        raise JournalError("ATTEMPT_IDENTITY_INVALID") from exc


def _canonical_attempt_authority(identity: ExecutionIdentity) -> str:
    return _canonical_json(
        {
            "domain": "formal-canonical-attempt-authority-v1",
            "base_execution_identity": json.loads(_canonical_base_execution_identity(identity)),
            "attempt_number": identity.attempt_number,
            "attempt_id": identity.attempt_id,
        }
    )


def _validate_rq_matrix(identity: ExecutionIdentity) -> None:
    if identity.rq in {"RQ1", "RQ2"}:
        valid = (
            identity.system_config_id in {"qa_only_reconstructed_baseline", "v2"}
            and identity.turn_index == 1
            and identity.dialogue_id is None
            and identity.input_checkpoint_id is None
            and identity.input_checkpoint_sha256 is None
        )
    elif identity.rq == "RQ3":
        valid = (
            identity.system_config_id in {"single_turn", "context_aware"}
            and identity.turn_index in {1, 2}
            and _safe_id(identity.dialogue_id)
            and identity.dialogue_id == identity.case_id
        )
        checkpoint_required = (
            identity.system_config_id == "context_aware" and identity.turn_index == 2
        )
        if checkpoint_required:
            valid = (
                valid
                and _sha(identity.input_checkpoint_sha256)
                and type(identity.input_checkpoint_id) is str
                and identity.input_checkpoint_id
                == _derive_checkpoint_id(
                    plan_fingerprint=identity.plan_fingerprint,
                    execution_unit_id=identity.execution_unit_id,
                    dialogue_id=identity.dialogue_id,
                    system_config_id=identity.system_config_id,
                    input_checkpoint_sha256=identity.input_checkpoint_sha256,
                )
            )
        else:
            valid = (
                valid
                and identity.input_checkpoint_id is None
                and identity.input_checkpoint_sha256 is None
            )
    else:
        valid = False
    if not valid:
        raise JournalError("RQ_SYSTEM_TURN_CHECKPOINT_INVALID")


def _validate_execution_identity(identity: ExecutionIdentity) -> None:
    if type(identity) is not ExecutionIdentity:
        raise JournalError("EXECUTION_IDENTITY_INVALID")
    if (
        identity.plan_fingerprint != _FROZEN_PLAN_FINGERPRINT
        or not _sha(identity.request_id)
        or type(identity.execution_order) is not int
        or not 1 <= identity.execution_order <= 190
        or not _safe_id(identity.case_id)
        or type(identity.turn_index) is not int
        or identity.turn_index not in {1, 2}
        or type(identity.attempt_number) is not int
        or not 1 <= identity.attempt_number <= _MAX_ATTEMPTS
        or identity.provider != "DeepSeek"
        or identity.provider_model != "deepseek-chat"
    ):
        raise JournalError("EXECUTION_IDENTITY_INVALID")
    expected_unit_id = _derive_execution_unit_id(
        plan_fingerprint=identity.plan_fingerprint,
        request_id=identity.request_id,
        execution_order=identity.execution_order,
    )
    if identity.execution_unit_id != expected_unit_id:
        raise JournalError("EXECUTION_IDENTITY_INVALID")
    if identity.turn_id != _derive_turn_id(
        execution_unit_id=identity.execution_unit_id,
        rq=identity.rq,
        case_id=identity.case_id,
        turn_index=identity.turn_index,
    ):
        raise JournalError("TURN_IDENTITY_INVALID")
    expected_attempt_id = _derive_attempt_id(identity, identity.attempt_number)
    if identity.attempt_id != expected_attempt_id:
        raise JournalError("ATTEMPT_IDENTITY_INVALID")
    for value in (identity.payload_sha256, identity.resolved_payload_sha256):
        if not _sha(value):
            raise JournalError("EXECUTION_IDENTITY_INVALID")
    if (
        identity.transport_contract_id != _transport_contract_id()
        or identity.generation_contract_id != _generation_contract_id()
        or
        identity.transport_contract_sha256 != _transport_contract_sha256()
        or identity.generation_contract_sha256 != _generation_contract_sha256()
    ):
        raise JournalError("CONTRACT_IDENTITY_INVALID")
    try:
        system = _formal_identity(identity.system_config_id)
        _validate_resource_identity(identity.resource_identity)
    except _TransportError as exc:
        raise JournalError("EXECUTION_IDENTITY_INVALID") from exc
    if (
        identity.formal_system_id != system.formal_system_id
        or identity.resolved_runtime_system_id != system.resolved_runtime_system_id
        or identity.resource_identity.system_config_id != identity.system_config_id
        or identity.resource_identity.formal_system_id != identity.formal_system_id
        or identity.resource_identity.cache_family != system.resource_family
        or identity.resource_identity_sha256
        != _resource_identity_sha256(identity.resource_identity)
    ):
        raise JournalError("EXECUTION_IDENTITY_INVALID")
    _validate_rq_matrix(identity)


def validate_execution_identity(identity: ExecutionIdentity) -> None:
    _validate_execution_identity(identity)


def validate_expected_identity(value: object) -> ExecutionIdentity:
    if type(value) is ExecutionIdentity:
        _validate_execution_identity(value)
        return value
    if type(value) is dict:
        return ExecutionIdentity.from_mapping(value)
    raise JournalError("EXPECTED_IDENTITY_REQUIRED")


@dataclass(frozen=True)
class InflightJournal:
    schema_version: int
    identity: ExecutionIdentity
    state: str
    prepared_at: str
    call_started_at: str | None
    provider_returned_at: str | None
    failed_at: str | None
    committed_at: str | None
    updated_at: str
    sanitized_outcome_category: str | None
    provider_request_id: str | None
    provider_response_id: str | None
    provider_response_sha256: str | None
    response_sha256: str | None

    def __post_init__(self) -> None:
        _validate_journal(self)

    @property
    def provider_called(self) -> bool:
        return self.call_started_at is not None

    def to_dict(self) -> dict[str, Any]:
        _validate_journal(self)
        result = {field.name: getattr(self, field.name) for field in fields(self)}
        result["identity"] = self.identity.to_dict()
        return result

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, Any], expected: ExecutionIdentity | Mapping[str, Any] | None = None
    ) -> "InflightJournal":
        if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:
            raise JournalError("JOURNAL_SCHEMA_INVALID")
        try:
            data = dict(value)
            data["identity"] = ExecutionIdentity.from_mapping(value["identity"])
            journal = cls(**data)
        except (TypeError, JournalError) as exc:
            if isinstance(exc, JournalError):
                raise
            raise JournalError("JOURNAL_SCHEMA_INVALID") from exc
        if expected is not None:
            _validate_journal(journal, expected)
        return journal

    @classmethod
    def from_json(
        cls, raw_json: str, expected: ExecutionIdentity | Mapping[str, Any] | None = None
    ) -> "InflightJournal":
        return cls.from_mapping(_loads_closed_json(raw_json), expected)


def _validate_timestamp_order(journal: InflightJournal) -> None:
    prepared = _parse_timestamp(journal.prepared_at)
    updated = _parse_timestamp(journal.updated_at)
    if updated < prepared:
        raise JournalError("JOURNAL_TIMESTAMP_ORDER_INVALID")
    ordered = [
        journal.prepared_at,
        journal.call_started_at,
        journal.provider_returned_at,
        journal.committed_at,
    ]
    present = [value for value in ordered if value is not None]
    parsed = [_parse_timestamp(value) for value in present]
    if parsed != sorted(parsed) or len(set(parsed)) != len(parsed):
        raise JournalError("JOURNAL_TIMESTAMP_ORDER_INVALID")
    if journal.failed_at is not None:
        failed = _parse_timestamp(journal.failed_at)
        lower = _parse_timestamp(journal.call_started_at or journal.prepared_at)
        if failed <= lower:
            raise JournalError("JOURNAL_TIMESTAMP_ORDER_INVALID")


def _validate_state_matrix(journal: InflightJournal) -> None:
    expected_request_id = _derive_provider_request_id(journal.identity)
    if journal.provider_request_id is not None:
        try:
            _validate_provider_identity(journal.provider_request_id, "JOURNAL_STATE_INVALID")
        except _TransportError as exc:
            raise JournalError("JOURNAL_STATE_INVALID") from exc
        if journal.provider_request_id != expected_request_id:
            raise JournalError("JOURNAL_STATE_INVALID")
    if journal.provider_response_id is not None:
        try:
            _validate_provider_identity(journal.provider_response_id, "JOURNAL_STATE_INVALID")
        except _TransportError as exc:
            raise JournalError("JOURNAL_STATE_INVALID") from exc
        if journal.provider_response_id == journal.provider_request_id:
            raise JournalError("JOURNAL_STATE_INVALID")
    response_evidence = (
        journal.provider_response_id,
        journal.provider_response_sha256,
        journal.response_sha256,
    )
    if journal.state == "prepared":
        valid = (
            journal.updated_at == journal.prepared_at
            and journal.call_started_at is None
            and journal.provider_returned_at is None
            and journal.failed_at is None
            and journal.committed_at is None
            and journal.sanitized_outcome_category is None
            and journal.provider_request_id is None
            and all(item is None for item in response_evidence)
        )
    elif journal.state == "call_started":
        valid = (
            journal.call_started_at is not None
            and journal.updated_at == journal.call_started_at
            and journal.provider_returned_at is None
            and journal.failed_at is None
            and journal.committed_at is None
            and journal.sanitized_outcome_category is None
            and journal.provider_request_id == expected_request_id
            and all(item is None for item in response_evidence)
        )
    elif journal.state == "provider_returned":
        valid = (
            journal.call_started_at is not None
            and journal.provider_returned_at is not None
            and journal.updated_at == journal.provider_returned_at
            and journal.failed_at is None
            and journal.committed_at is None
            and journal.sanitized_outcome_category is None
            and journal.provider_request_id == expected_request_id
            and journal.provider_response_id is not None
            and _sha(journal.provider_response_sha256)
            and _sha(journal.response_sha256)
        )
    elif journal.state == "retryable_failed":
        pre_send = journal.sanitized_outcome_category == "pre_send_failure"
        valid = (
            journal.failed_at is not None
            and journal.updated_at == journal.failed_at
            and journal.provider_returned_at is None
            and journal.committed_at is None
            and journal.sanitized_outcome_category in _RETRYABLE_OUTCOMES
            and all(item is None for item in response_evidence)
        )
        if pre_send:
            valid = (
                valid
                and journal.call_started_at is None
                and journal.provider_request_id is None
            )
        else:
            valid = (
                valid
                and journal.sanitized_outcome_category in _POST_CALL_RETRYABLE
                and journal.call_started_at is not None
                and journal.provider_request_id == expected_request_id
            )
    elif journal.state == "terminal_failed":
        valid = (
            journal.call_started_at is not None
            and journal.failed_at is not None
            and journal.updated_at == journal.failed_at
            and journal.provider_returned_at is None
            and journal.committed_at is None
            and journal.sanitized_outcome_category in _TERMINAL_OUTCOMES
            and journal.provider_request_id == expected_request_id
            and all(item is None for item in response_evidence)
        )
    elif journal.state == "uncertain":
        valid = (
            journal.call_started_at is not None
            and journal.failed_at is not None
            and journal.updated_at == journal.failed_at
            and journal.provider_returned_at is None
            and journal.committed_at is None
            and journal.sanitized_outcome_category in _UNCERTAIN_OUTCOMES
            and journal.provider_request_id == expected_request_id
            and all(item is None for item in response_evidence)
        )
    elif journal.state == "committed":
        valid = (
            journal.call_started_at is not None
            and journal.provider_returned_at is not None
            and journal.failed_at is None
            and journal.committed_at is not None
            and journal.updated_at == journal.committed_at
            and journal.sanitized_outcome_category == "provider_success"
            and journal.provider_request_id == expected_request_id
            and journal.provider_response_id is not None
            and _sha(journal.provider_response_sha256)
            and _sha(journal.response_sha256)
        )
    else:
        valid = False
    if not valid:
        raise JournalError("JOURNAL_STATE_INVALID")


def _validate_journal(
    journal: InflightJournal,
    expected: ExecutionIdentity | Mapping[str, Any] | None = None,
) -> None:
    if (
        type(journal) is not InflightJournal
        or type(journal.schema_version) is not int
        or journal.schema_version != 3
        or journal.state not in _STATES
    ):
        raise JournalError("JOURNAL_SCHEMA_INVALID")
    _validate_execution_identity(journal.identity)
    _validate_timestamp_order(journal)
    _validate_state_matrix(journal)
    if expected is not None and journal.identity != validate_expected_identity(expected):
        raise JournalError("JOURNAL_IDENTITY_MISMATCH")


def validate_journal(
    journal: InflightJournal,
    expected: ExecutionIdentity | Mapping[str, Any] | None = None,
) -> None:
    _validate_journal(journal, expected)


def create_initial_journal(identity: ExecutionIdentity, prepared_at: str) -> InflightJournal:
    _validate_execution_identity(identity)
    if identity.attempt_number != 1:
        raise JournalError("INITIAL_ATTEMPT_REQUIRED")
    _parse_timestamp(prepared_at)
    return InflightJournal(
        schema_version=3,
        identity=identity,
        state="prepared",
        prepared_at=prepared_at,
        call_started_at=None,
        provider_returned_at=None,
        failed_at=None,
        committed_at=None,
        updated_at=prepared_at,
        sanitized_outcome_category=None,
        provider_request_id=None,
        provider_response_id=None,
        provider_response_sha256=None,
        response_sha256=None,
    )


_TRANSITIONS = {
    "prepared": {"call_started", "retryable_failed"},
    "call_started": {
        "provider_returned",
        "retryable_failed",
        "terminal_failed",
        "uncertain",
    },
}


def transition(
    journal: InflightJournal, state: str, updated_at: str, **updates: Any
) -> InflightJournal:
    _validate_journal(journal)
    _parse_timestamp(updated_at)
    if state not in _TRANSITIONS.get(journal.state, set()) or not _strictly_after(
        updated_at, journal.updated_at
    ):
        raise JournalError("JOURNAL_ILLEGAL_TRANSITION")
    allowed = {
        "call_started": {"provider_request_id"},
        "provider_returned": {
            "provider_response_id",
            "provider_response_sha256",
            "response_sha256",
        },
        "retryable_failed": {"sanitized_outcome_category"},
        "terminal_failed": {"sanitized_outcome_category"},
        "uncertain": {"sanitized_outcome_category"},
    }[state]
    if set(updates) != allowed:
        raise JournalError("JOURNAL_ILLEGAL_TRANSITION")
    common: dict[str, Any] = {"state": state, "updated_at": updated_at, **updates}
    if state == "call_started":
        common["call_started_at"] = updated_at
    elif state == "provider_returned":
        common["provider_returned_at"] = updated_at
    else:
        common["failed_at"] = updated_at
    try:
        return replace(journal, **common)
    except JournalError as exc:
        raise JournalError("JOURNAL_ILLEGAL_TRANSITION") from exc


def next_retry_journal(
    predecessor: InflightJournal, prepared_at: str
) -> InflightJournal:
    _validate_journal(predecessor)
    _parse_timestamp(prepared_at)
    if (
        predecessor.state != "retryable_failed"
        or predecessor.identity.attempt_number >= _MAX_ATTEMPTS
        or not _strictly_after(prepared_at, predecessor.updated_at)
    ):
        raise JournalError("RETRY_PREDECESSOR_INVALID")
    next_number = predecessor.identity.attempt_number + 1
    next_identity = replace(
        predecessor.identity,
        attempt_number=next_number,
        attempt_id=_derive_attempt_id(predecessor.identity, next_number),
    )
    return InflightJournal(
        schema_version=3,
        identity=next_identity,
        state="prepared",
        prepared_at=prepared_at,
        call_started_at=None,
        provider_returned_at=None,
        failed_at=None,
        committed_at=None,
        updated_at=prepared_at,
        sanitized_outcome_category=None,
        provider_request_id=None,
        provider_response_id=None,
        provider_response_sha256=None,
        response_sha256=None,
    )


@dataclass(frozen=True)
class AuthoritativeSuccess:
    schema_version: int
    identity: ExecutionIdentity
    provider_request_id: str
    provider_response_id: str
    provider_response_sha256: str
    response_sha256: str
    call_started_at: str
    provider_returned_at: str
    committed_at: str
    execution_status: str

    def __post_init__(self) -> None:
        _validate_success(self)

    def to_dict(self) -> dict[str, Any]:
        _validate_success(self)
        result = {field.name: getattr(self, field.name) for field in fields(self)}
        result["identity"] = self.identity.to_dict()
        return result

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AuthoritativeSuccess":
        if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:
            raise JournalError("JOURNAL_SUCCESS_INVALID")
        try:
            data = dict(value)
            data["identity"] = ExecutionIdentity.from_mapping(value["identity"])
            return cls(**data)
        except (TypeError, JournalError) as exc:
            if isinstance(exc, JournalError):
                raise
            raise JournalError("JOURNAL_SUCCESS_INVALID") from exc

    @classmethod
    def from_json(cls, raw_json: str) -> "AuthoritativeSuccess":
        return cls.from_mapping(_loads_closed_json(raw_json))


_CanonicalAuthoritativeSuccess = AuthoritativeSuccess


_SUCCESS_FIELDS = frozenset(field.name for field in fields(AuthoritativeSuccess))


def _validate_success(success: AuthoritativeSuccess) -> None:
    if (
        type(success) is not AuthoritativeSuccess
        or type(success.schema_version) is not int
        or success.schema_version != 1
        or success.execution_status != "success"
    ):
        raise JournalError("JOURNAL_SUCCESS_INVALID")
    _validate_execution_identity(success.identity)
    try:
        _validate_provider_identity(success.provider_request_id, "JOURNAL_SUCCESS_INVALID")
        _validate_provider_identity(success.provider_response_id, "JOURNAL_SUCCESS_INVALID")
        _validate_sha256(success.provider_response_sha256, "JOURNAL_SUCCESS_INVALID")
        _validate_sha256(success.response_sha256, "JOURNAL_SUCCESS_INVALID")
    except _TransportError as exc:
        raise JournalError("JOURNAL_SUCCESS_INVALID") from exc
    if (
        success.provider_request_id != _derive_provider_request_id(success.identity)
        or success.provider_response_id == success.provider_request_id
    ):
        raise JournalError("JOURNAL_SUCCESS_INVALID")
    started = _parse_timestamp(success.call_started_at)
    returned = _parse_timestamp(success.provider_returned_at)
    committed = _parse_timestamp(success.committed_at)
    if not started < returned < committed:
        raise JournalError("JOURNAL_TIMESTAMP_ORDER_INVALID")


def _checked_authoritative_success(
    success: AuthoritativeSuccess | Mapping[str, Any],
) -> AuthoritativeSuccess:
    if type(success) is AuthoritativeSuccess:
        checked = success
        _validate_success(checked)
    elif type(success) is dict:
        checked = AuthoritativeSuccess.from_mapping(success)
    else:
        raise JournalError("JOURNAL_SUCCESS_INVALID")
    return checked


def validate_authoritative_success(
    success: AuthoritativeSuccess | Mapping[str, Any],
    expected: ExecutionIdentity | Mapping[str, Any] | None = None,
) -> AuthoritativeSuccess:
    expected_identity = validate_expected_identity(expected)
    checked = _checked_authoritative_success(success)
    if checked.identity != expected_identity:
        raise JournalError("JOURNAL_IDENTITY_MISMATCH")
    return checked


def _reject_conflicting_journal_evidence(
    journal: InflightJournal, success: AuthoritativeSuccess
) -> None:
    """Fail closed if a journal has already recorded different call evidence."""
    for field_name in (
        "provider_request_id",
        "provider_response_id",
        "provider_response_sha256",
        "response_sha256",
        "call_started_at",
        "provider_returned_at",
        "committed_at",
    ):
        existing = getattr(journal, field_name)
        if existing is not None and existing != getattr(success, field_name):
            raise JournalError("JOURNAL_EVIDENCE_CONFLICT")


def reconcile(
    journal: InflightJournal,
    success: AuthoritativeSuccess | Mapping[str, Any],
    expected: ExecutionIdentity | Mapping[str, Any] | None = None,
) -> InflightJournal:
    _validate_journal(journal)
    expected_identity = journal.identity if expected is None else validate_expected_identity(expected)
    if journal.identity != expected_identity:
        raise JournalError("JOURNAL_IDENTITY_MISMATCH")
    checked = _checked_authoritative_success(success)
    if checked.identity != expected_identity:
        raise JournalError("JOURNAL_EVIDENCE_CONFLICT")
    _reject_conflicting_journal_evidence(journal, checked)
    if journal.state == "committed":
        return journal
    if _parse_timestamp(checked.call_started_at) <= _parse_timestamp(journal.prepared_at):
        raise JournalError("JOURNAL_TIMESTAMP_ORDER_INVALID")
    return InflightJournal(
        schema_version=3,
        identity=journal.identity,
        state="committed",
        prepared_at=journal.prepared_at,
        call_started_at=checked.call_started_at,
        provider_returned_at=checked.provider_returned_at,
        failed_at=None,
        committed_at=checked.committed_at,
        updated_at=checked.committed_at,
        sanitized_outcome_category="provider_success",
        provider_request_id=checked.provider_request_id,
        provider_response_id=checked.provider_response_id,
        provider_response_sha256=checked.provider_response_sha256,
        response_sha256=checked.response_sha256,
    )


def recovery_decision(
    journal: InflightJournal | None,
    *,
    authoritative_success: AuthoritativeSuccess | Mapping[str, Any] | None = None,
    expected: ExecutionIdentity | Mapping[str, Any] | None = None,
) -> str:
    expected_identity = validate_expected_identity(expected)
    if journal is not None:
        _validate_journal(journal, expected_identity)
    if authoritative_success is not None:
        if journal is None:
            validate_authoritative_success(authoritative_success, expected_identity)
            return "authoritative_success"
        reconcile(journal, authoritative_success, expected_identity)
        return "confirmed" if journal.state == "committed" else "reconcile_committed"
    if journal is None:
        return "begin"
    if journal.state == "prepared":
        return "continue_before_provider"
    if journal.state == "retryable_failed":
        return "retry" if journal.identity.attempt_number < _MAX_ATTEMPTS else "fail_closed"
    return "fail_closed"


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JournalError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _loads_closed_json(raw_json: str) -> dict[str, Any]:
    if type(raw_json) is not str or len(raw_json) > 1_000_000:
        raise JournalError("JOURNAL_READ_INVALID")
    try:
        value = json.loads(raw_json, object_pairs_hook=_reject_duplicate_pairs)
    except JournalError:
        raise
    except json.JSONDecodeError as exc:
        raise JournalError("JOURNAL_READ_INVALID") from exc
    if type(value) is not dict:
        raise JournalError("JOURNAL_READ_INVALID")
    return value


def journal_path(directory: Path, request_id: str) -> Path:
    if not isinstance(directory, Path) or not _sha(request_id):
        raise JournalError("JOURNAL_PATH_INVALID")
    return directory / (request_id + ".json")


def read_journal(
    path: Path, expected: ExecutionIdentity | Mapping[str, Any] | None = None
) -> InflightJournal:
    if not isinstance(path, Path) or path.name.endswith(".tmp") or not path.name.endswith(".json"):
        raise JournalError("JOURNAL_PATH_INVALID")
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise JournalError("JOURNAL_READ_INVALID") from exc
    journal = InflightJournal.from_json(raw, expected)
    if path.name != journal.identity.request_id + ".json":
        raise JournalError("JOURNAL_PATH_INVALID")
    return journal


def atomic_write_journal(path: Path, journal: InflightJournal) -> None:
    _validate_journal(journal)
    if not isinstance(path, Path) or path.name != journal.identity.request_id + ".json":
        raise JournalError("JOURNAL_PATH_INVALID")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=path.name + ".", suffix=".tmp", dir=path.parent, text=True
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            json.dump(journal.to_dict(), output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        raise JournalError("JOURNAL_PERSISTENCE_FAILURE") from exc


def journal_sha256(journal: InflightJournal) -> str:
    _validate_journal(journal)
    return hashlib.sha256(_canonical_json(journal.to_dict()).encode("utf-8")).hexdigest()
