"""Offline-only Stage B1 orchestration over the frozen Stage A public contracts.

This module has no durable store, environment access, production-resource loader,
SDK client, or real-system import.  Every executable dependency is injected.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from formal_evaluation_inflight import (
    AuthoritativeSuccess,
    ExecutionIdentity,
    InflightJournal,
    JournalError,
    TERMINAL_OUTCOMES,
    create_initial_journal,
    derive_attempt_id,
    derive_checkpoint_id,
    derive_execution_unit_id,
    derive_provider_request_id,
    derive_turn_id,
    next_retry_journal,
    reconcile,
    recovery_decision,
    transition,
    validate_authoritative_success,
    validate_execution_identity,
    validate_journal,
)
from formal_evaluation_transport import (
    FixedGenerationProxy,
    NormalizedProviderResponse,
    ProductionResourceIdentity,
    ProviderCallTracker,
    TransportError,
    formal_identity,
    generation_contract_id,
    generation_contract_sha256,
    may_retry,
    project_formal_result,
    resource_identity_sha256,
    retry_classification,
    sha256_text,
    transport_contract_id,
    transport_contract_sha256,
    validate_core_result,
    validate_registry,
    validate_resource_identity,
    validate_sha256,
)


PLAN_FINGERPRINT = "4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"
SYSTEM_CONFIG_IDS = (
    "qa_only_reconstructed_baseline",
    "v2",
    "single_turn",
    "context_aware",
)
_COMMON_UNIT_FIELDS = frozenset(
    {
        "request_id",
        "rq",
        "case_id",
        "turn_index",
        "system_config_id",
        "input_sha256",
        "payload",
        "payload_sha256",
        "frozen_test_file_sha256",
        "execution_order",
    }
)
_PAYLOAD_FIELDS = frozenset(
    {"protocol_version", "rq", "system_config", "generation", "user_input", "history"}
)
_CORE_FIELDS = frozenset(
    {
        "response_text",
        "route",
        "guard_category",
        "requires_backend_api",
        "retrieval_used",
        "retrieved_document_ids",
        "retrieved_scores",
    }
)
_LOCAL_ROUTES = frozenset(
    {"local_guard", "backend_boundary", "conservative_response"}
)


class OrchestrationError(RuntimeError):
    """A sanitized, stable Stage B1 failure category."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(category)


def _canonical_sha256(value: object) -> str:
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise OrchestrationError("ORCHESTRATION_INPUT_INVALID") from exc
    return hashlib.sha256(encoded).hexdigest()


def _checked_unit(value: Mapping[str, Any]) -> dict[str, Any]:
    if type(value) is not dict:
        raise OrchestrationError("PLAN_UNIT_INVALID")
    expected_fields = _COMMON_UNIT_FIELDS | ({"review_id"} if value.get("rq") == "RQ1" else set())
    if set(value) != expected_fields:
        raise OrchestrationError("PLAN_UNIT_INVALID")
    payload = value.get("payload")
    if type(payload) is not dict or set(payload) != _PAYLOAD_FIELDS:
        raise OrchestrationError("PLAN_UNIT_INVALID")
    if (
        not all(
            type(value.get(name)) is str
            for name in (
                "request_id",
                "case_id",
                "system_config_id",
                "input_sha256",
                "payload_sha256",
                "frozen_test_file_sha256",
            )
        )
        or value.get("rq") not in {"RQ1", "RQ2", "RQ3"}
        or type(value.get("turn_index")) is not int
        or value["turn_index"] not in {1, 2}
        or type(value.get("execution_order")) is not int
        or not 1 <= value["execution_order"] <= 190
        or not value["case_id"]
        or value["system_config_id"] not in SYSTEM_CONFIG_IDS
    ):
        raise OrchestrationError("PLAN_UNIT_INVALID")
    try:
        for name in (
            "request_id",
            "input_sha256",
            "payload_sha256",
            "frozen_test_file_sha256",
        ):
            validate_sha256(value[name], "PLAN_UNIT_INVALID")
    except TransportError as exc:
        raise OrchestrationError(exc.category) from exc
    if (
        payload["protocol_version"] != "1.0"
        or payload["rq"] != value["rq"]
        or payload["system_config"] != value["system_config_id"]
        or type(payload["user_input"]) is not str
        or not payload["user_input"]
        or type(payload["history"]) is not list
        or value["input_sha256"] != sha256_text(payload["user_input"])
        or value["payload_sha256"] != _canonical_sha256(payload)
    ):
        raise OrchestrationError("PLAN_UNIT_PAYLOAD_INTEGRITY_INVALID")
    matrix = (
        value["rq"] in {"RQ1", "RQ2"}
        and value["system_config_id"] in {"qa_only_reconstructed_baseline", "v2"}
        and value["turn_index"] == 1
        and payload["history"] == []
    ) or (
        value["rq"] == "RQ3"
        and value["system_config_id"] in {"single_turn", "context_aware"}
        and value["turn_index"] in {1, 2}
        and (
            payload["history"] == []
            if value["system_config_id"] == "single_turn" or value["turn_index"] == 1
            else payload["history"]
            == [
                {
                    "user_input": payload["history"][0].get("user_input")
                    if len(payload["history"]) == 1
                    and type(payload["history"][0]) is dict
                    else None,
                    "assistant_answer": "__PRIOR_RESPONSE_BY_SAME_REQUEST_SEQUENCE__",
                }
            ]
        )
    )
    if not matrix:
        raise OrchestrationError("RQ_SYSTEM_TURN_INVALID")
    if value["rq"] == "RQ1" and value["review_id"] != value["case_id"]:
        raise OrchestrationError("PLAN_UNIT_INVALID")
    return copy.deepcopy(value)


@dataclass(frozen=True)
class SyntheticResourceBundle:
    """Closed, validated synthetic identities for all four formal systems."""

    resources: Mapping[str, ProductionResourceIdentity]

    def __post_init__(self) -> None:
        validate_registry()
        if not isinstance(self.resources, Mapping) or set(self.resources) != set(
            SYSTEM_CONFIG_IDS
        ):
            raise OrchestrationError("SYNTHETIC_RESOURCE_BUNDLE_INVALID")
        checked: dict[str, ProductionResourceIdentity] = {}
        for config_id in SYSTEM_CONFIG_IDS:
            resource = self.resources.get(config_id)
            try:
                validate_resource_identity(resource)
            except TransportError as exc:
                raise OrchestrationError(exc.category) from exc
            if (
                type(resource) is not ProductionResourceIdentity
                or not resource.synthetic
                or resource.resource_type != "synthetic_fixture"
                or resource.system_config_id != config_id
                or resource.formal_system_id
                != formal_identity(config_id).formal_system_id
            ):
                raise OrchestrationError("SYNTHETIC_RESOURCE_BUNDLE_INVALID")
            checked[config_id] = resource
        object.__setattr__(self, "resources", MappingProxyType(checked))

    @classmethod
    def from_mappings(
        cls, value: Mapping[str, Mapping[str, Any]]
    ) -> "SyntheticResourceBundle":
        validate_registry()
        if type(value) is not dict or set(value) != set(SYSTEM_CONFIG_IDS):
            raise OrchestrationError("SYNTHETIC_RESOURCE_BUNDLE_INVALID")
        checked: dict[str, ProductionResourceIdentity] = {}
        for config_id in SYSTEM_CONFIG_IDS:
            try:
                resource = ProductionResourceIdentity.from_mapping(value[config_id])
                validate_resource_identity(resource)
            except (TransportError, TypeError) as exc:
                category = getattr(exc, "category", "SYNTHETIC_RESOURCE_BUNDLE_INVALID")
                raise OrchestrationError(category) from exc
            if (
                not resource.synthetic
                or resource.resource_type != "synthetic_fixture"
                or resource.system_config_id != config_id
                or resource.formal_system_id
                != formal_identity(config_id).formal_system_id
            ):
                raise OrchestrationError("SYNTHETIC_RESOURCE_BUNDLE_INVALID")
            checked[config_id] = resource
        return cls(MappingProxyType(checked))

    def resource_for(self, system_config_id: str) -> ProductionResourceIdentity:
        if system_config_id not in SYSTEM_CONFIG_IDS:
            raise OrchestrationError("UNKNOWN_FORMAL_SYSTEM")
        resource = self.resources.get(system_config_id)
        if type(resource) is not ProductionResourceIdentity:
            raise OrchestrationError("SYNTHETIC_RESOURCE_BUNDLE_INVALID")
        validate_resource_identity(resource)
        if not resource.synthetic or resource.system_config_id != system_config_id:
            raise OrchestrationError("SYNTHETIC_RESOURCE_BUNDLE_INVALID")
        return resource


@dataclass(frozen=True)
class ExecutorContext:
    """Closed input supplied to one injected offline executor."""

    unit: Mapping[str, Any]
    identity: ExecutionIdentity
    checkpoint_snapshot: Mapping[str, Any] | None
    invoke_provider: Callable[..., NormalizedProviderResponse]


class ExecutorRegistry:
    """Exact dispatch table; it never imports a real formal system."""

    def __init__(self, executors: Mapping[str, Callable[[ExecutorContext], Mapping[str, Any]]]):
        validate_registry()
        if type(executors) is not dict or set(executors) != set(SYSTEM_CONFIG_IDS):
            raise OrchestrationError("EXECUTOR_REGISTRY_INVALID")
        if any(not callable(executors[name]) for name in SYSTEM_CONFIG_IDS):
            raise OrchestrationError("EXECUTOR_REGISTRY_INVALID")
        self.__executors = MappingProxyType(dict(executors))

    def dispatch(self, context: ExecutorContext) -> Mapping[str, Any]:
        validate_execution_identity(context.identity)
        identity = formal_identity(context.identity.system_config_id)
        if (
            context.identity.formal_system_id != identity.formal_system_id
            or context.identity.resolved_runtime_system_id
            != identity.resolved_runtime_system_id
        ):
            raise OrchestrationError("FORMAL_SYSTEM_IDENTITY_MISMATCH")
        executor = self.__executors.get(context.identity.system_config_id)
        if executor is None:
            raise OrchestrationError("UNKNOWN_FORMAL_SYSTEM")
        return executor(context)


@dataclass(frozen=True)
class CheckpointEvidence:
    schema_version: int
    plan_fingerprint: str
    checkpoint_id: str
    checkpoint_sha256: str
    system_config_id: str
    formal_system_id: str
    resolved_runtime_system_id: str
    dialogue_id: str
    turn_one_request_id: str
    turn_one_execution_unit_id: str
    turn_one_payload_sha256: str
    turn_one_response_text: str
    turn_one_response_sha256: str
    turn_one_resource_identity: Mapping[str, Any]
    turn_one_resource_identity_sha256: str
    expected_turn_two_request_id: str
    resolved_turn_two_payload_sha256: str
    runtime_identity_sha256: str
    snapshot: Mapping[str, Any]
    snapshot_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_fingerprint": self.plan_fingerprint,
            "checkpoint_id": self.checkpoint_id,
            "checkpoint_sha256": self.checkpoint_sha256,
            "system_config_id": self.system_config_id,
            "formal_system_id": self.formal_system_id,
            "resolved_runtime_system_id": self.resolved_runtime_system_id,
            "dialogue_id": self.dialogue_id,
            "turn_one_request_id": self.turn_one_request_id,
            "turn_one_execution_unit_id": self.turn_one_execution_unit_id,
            "turn_one_payload_sha256": self.turn_one_payload_sha256,
            "turn_one_response_text": self.turn_one_response_text,
            "turn_one_response_sha256": self.turn_one_response_sha256,
            "turn_one_resource_identity": copy.deepcopy(
                dict(self.turn_one_resource_identity)
            ),
            "turn_one_resource_identity_sha256": self.turn_one_resource_identity_sha256,
            "expected_turn_two_request_id": self.expected_turn_two_request_id,
            "resolved_turn_two_payload_sha256": self.resolved_turn_two_payload_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "snapshot": copy.deepcopy(dict(self.snapshot)),
            "snapshot_sha256": self.snapshot_sha256,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CheckpointEvidence":
        if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
            raise OrchestrationError("CHECKPOINT_EVIDENCE_INVALID")
        try:
            return cls(**copy.deepcopy(value))
        except TypeError as exc:
            raise OrchestrationError("CHECKPOINT_EVIDENCE_INVALID") from exc


@dataclass(frozen=True)
class OrchestrationOutcome:
    action: str
    recovery_action: str
    identity: ExecutionIdentity
    journal: InflightJournal | None
    predecessor_journal: InflightJournal | None
    tracker_state: str
    provider_call_count: int
    formal_result: Mapping[str, Any] | None
    authoritative_success: AuthoritativeSuccess | None
    checkpoint_evidence: CheckpointEvidence | None
    failure_category: str | None


class _RawClientBoundary:
    """Enter the injected raw client after the caller persisted call start."""

    def __init__(
        self,
        fake_raw_client: Any,
        journal: InflightJournal,
        clock: Callable[[], str],
        provider_request_id: str,
    ):
        self.fake_raw_client = fake_raw_client
        self.journal = journal
        self.clock = clock
        self.provider_request_id = provider_request_id
        self.call_count = 0
        self.exception: BaseException | None = None

    def create(self, **request: Any) -> Any:
        if self.call_count != 0:
            raise OrchestrationError("MULTIPLE_PROVIDER_CALLS_FORBIDDEN")
        if self.journal.state != "call_started":
            raise OrchestrationError("JOURNAL_CALL_START_NOT_PERSISTED")
        self.call_count = 1
        try:
            create = getattr(self.fake_raw_client, "create", None)
            return (
                create(**request)
                if callable(create)
                else self.fake_raw_client(**request)
            )
        except Exception as exc:
            self.exception = exc
            raise


def _resolved_turn_two_payload(
    turn_two: Mapping[str, Any], response_text: str
) -> dict[str, Any]:
    resolved = copy.deepcopy(turn_two["payload"])
    history = resolved.get("history")
    if (
        type(history) is not list
        or len(history) != 1
        or type(history[0]) is not dict
        or set(history[0]) != {"user_input", "assistant_answer"}
        or history[0]["assistant_answer"]
        != "__PRIOR_RESPONSE_BY_SAME_REQUEST_SEQUENCE__"
    ):
        raise OrchestrationError("CHECKPOINT_PAYLOAD_DEPENDENCY_INVALID")
    history[0]["assistant_answer"] = response_text
    return resolved


def _checkpoint_content(evidence: CheckpointEvidence) -> dict[str, Any]:
    content = evidence.to_dict()
    del content["checkpoint_id"]
    del content["checkpoint_sha256"]
    return content


def _validate_snapshot(
    snapshot: object, snapshot_validator: Callable[[Mapping[str, Any]], Any]
) -> dict[str, Any]:
    if type(snapshot) is not dict or not callable(snapshot_validator):
        raise OrchestrationError("CHECKPOINT_SNAPSHOT_INVALID")
    try:
        restored = snapshot_validator(copy.deepcopy(snapshot))
        normalized = restored.to_dict() if callable(getattr(restored, "to_dict", None)) else restored
    except Exception as exc:
        raise OrchestrationError("CHECKPOINT_SNAPSHOT_INVALID") from exc
    if type(normalized) is not dict or normalized != snapshot:
        raise OrchestrationError("CHECKPOINT_SNAPSHOT_INVALID")
    if (
        normalized.get("schema_version") != 1
        or normalized.get("completed_turn_index") != 1
        or type(normalized.get("conversation_state")) is not dict
        or set(normalized)
        != {
            "schema_version",
            "completed_turn_index",
            "conversation_state",
            "previous_user_text",
            "previous_assistant_text",
        }
    ):
        raise OrchestrationError("CHECKPOINT_SNAPSHOT_INVALID")
    return copy.deepcopy(normalized)


def _build_checkpoint(
    *,
    turn_one: Mapping[str, Any],
    turn_two: Mapping[str, Any],
    response_text: str,
    snapshot: Mapping[str, Any],
    resource: ProductionResourceIdentity,
    runtime_identity_sha256: str,
    snapshot_validator: Callable[[Mapping[str, Any]], Any],
) -> CheckpointEvidence:
    snapshot = _validate_snapshot(snapshot, snapshot_validator)
    try:
        validate_resource_identity(resource)
        resource_mapping = resource.to_dict()
        resource_sha = resource_identity_sha256(resource)
    except TransportError as exc:
        raise OrchestrationError("CHECKPOINT_RESOURCE_EVIDENCE_INVALID") from exc
    if (
        type(resource) is not ProductionResourceIdentity
        or resource.system_config_id != "context_aware"
        or resource.formal_system_id
        != formal_identity("context_aware").formal_system_id
    ):
        raise OrchestrationError("CHECKPOINT_RESOURCE_EVIDENCE_INVALID")
    if (
        snapshot["previous_user_text"] != turn_one["payload"]["user_input"]
        or snapshot["previous_assistant_text"] != response_text
    ):
        raise OrchestrationError("CHECKPOINT_SNAPSHOT_MISMATCH")
    turn_one_unit_id = derive_execution_unit_id(
        plan_fingerprint=PLAN_FINGERPRINT,
        request_id=turn_one["request_id"],
        execution_order=turn_one["execution_order"],
    )
    turn_two_unit_id = derive_execution_unit_id(
        plan_fingerprint=PLAN_FINGERPRINT,
        request_id=turn_two["request_id"],
        execution_order=turn_two["execution_order"],
    )
    resolved_payload_sha = _canonical_sha256(
        _resolved_turn_two_payload(turn_two, response_text)
    )
    identity = formal_identity("context_aware")
    provisional = CheckpointEvidence(
        schema_version=1,
        plan_fingerprint=PLAN_FINGERPRINT,
        checkpoint_id="checkpoint_pending",
        checkpoint_sha256="0" * 64,
        system_config_id="context_aware",
        formal_system_id=identity.formal_system_id,
        resolved_runtime_system_id=identity.resolved_runtime_system_id,
        dialogue_id=turn_one["case_id"],
        turn_one_request_id=turn_one["request_id"],
        turn_one_execution_unit_id=turn_one_unit_id,
        turn_one_payload_sha256=turn_one["payload_sha256"],
        turn_one_response_text=response_text,
        turn_one_response_sha256=sha256_text(response_text),
        turn_one_resource_identity=MappingProxyType(resource_mapping),
        turn_one_resource_identity_sha256=resource_sha,
        expected_turn_two_request_id=turn_two["request_id"],
        resolved_turn_two_payload_sha256=resolved_payload_sha,
        runtime_identity_sha256=runtime_identity_sha256,
        snapshot=snapshot,
        snapshot_sha256=_canonical_sha256(snapshot),
    )
    checkpoint_sha = _canonical_sha256(_checkpoint_content(provisional))
    checkpoint_id = derive_checkpoint_id(
        plan_fingerprint=PLAN_FINGERPRINT,
        execution_unit_id=turn_two_unit_id,
        dialogue_id=turn_one["case_id"],
        system_config_id="context_aware",
        input_checkpoint_sha256=checkpoint_sha,
    )
    return CheckpointEvidence(
        **{
            **provisional.to_dict(),
            "checkpoint_id": checkpoint_id,
            "checkpoint_sha256": checkpoint_sha,
        }
    )


def validate_checkpoint_evidence(
    value: CheckpointEvidence | Mapping[str, Any],
    *,
    turn_one_unit: Mapping[str, Any],
    turn_two_unit: Mapping[str, Any],
    resource: ProductionResourceIdentity,
    runtime_identity_sha256: str,
    snapshot_validator: Callable[[Mapping[str, Any]], Any],
) -> CheckpointEvidence:
    turn_one = _checked_unit(turn_one_unit)
    turn_two = _checked_unit(turn_two_unit)
    evidence = (
        value
        if type(value) is CheckpointEvidence
        else CheckpointEvidence.from_mapping(value)
    )
    try:
        evidence_resource = ProductionResourceIdentity.from_mapping(
            dict(evidence.turn_one_resource_identity)
            if isinstance(evidence.turn_one_resource_identity, Mapping)
            else evidence.turn_one_resource_identity
        )
        validate_resource_identity(evidence_resource)
        validate_resource_identity(resource)
    except (TransportError, TypeError, ValueError) as exc:
        raise OrchestrationError("CHECKPOINT_RESOURCE_EVIDENCE_INVALID") from exc
    if (
        evidence.turn_one_resource_identity_sha256
        != resource_identity_sha256(evidence_resource)
    ):
        raise OrchestrationError("CHECKPOINT_RESOURCE_EVIDENCE_INVALID")
    if (
        evidence_resource != resource
        or evidence.turn_one_resource_identity_sha256
        != resource_identity_sha256(resource)
    ):
        raise OrchestrationError("CHECKPOINT_RESOURCE_IDENTITY_MISMATCH")
    try:
        validate_sha256(runtime_identity_sha256, "CHECKPOINT_EVIDENCE_INVALID")
    except TransportError as exc:
        raise OrchestrationError(exc.category) from exc
    rebuilt = _build_checkpoint(
        turn_one=turn_one,
        turn_two=turn_two,
        response_text=evidence.turn_one_response_text,
        snapshot=dict(evidence.snapshot),
        resource=resource,
        runtime_identity_sha256=runtime_identity_sha256,
        snapshot_validator=snapshot_validator,
    )
    if (
        evidence != rebuilt
        or turn_one["rq"] != "RQ3"
        or turn_two["rq"] != "RQ3"
        or turn_one["case_id"] != turn_two["case_id"]
        or turn_one["system_config_id"] != "context_aware"
        or turn_two["system_config_id"] != "context_aware"
        or turn_one["turn_index"] != 1
        or turn_two["turn_index"] != 2
    ):
        raise OrchestrationError("CHECKPOINT_EVIDENCE_MISMATCH")
    return evidence


def _validate_rq3_pair(
    selected: Mapping[str, Any],
    turn_one_unit: Mapping[str, Any] | None,
    turn_two_unit: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    is_context = (
        selected["rq"] == "RQ3"
        and selected["system_config_id"] == "context_aware"
    )
    if not is_context:
        if turn_one_unit is not None or turn_two_unit is not None:
            raise OrchestrationError("RQ3_PAIR_MISMATCH")
        return None, None
    if turn_one_unit is None or turn_two_unit is None:
        raise OrchestrationError("RQ3_PAIR_MISMATCH")
    turn_one = _checked_unit(turn_one_unit)
    turn_two = _checked_unit(turn_two_unit)
    history = turn_two["payload"]["history"]
    if (
        turn_one["rq"] != "RQ3"
        or turn_two["rq"] != "RQ3"
        or turn_one["system_config_id"] != "context_aware"
        or turn_two["system_config_id"] != "context_aware"
        or turn_one["case_id"] != turn_two["case_id"]
        or turn_one["turn_index"] != 1
        or turn_two["turn_index"] != 2
        or turn_one["execution_order"] + 1 != turn_two["execution_order"]
        or selected not in (turn_one, turn_two)
        or type(history) is not list
        or len(history) != 1
        or history[0].get("user_input") != turn_one["payload"]["user_input"]
        or history[0].get("assistant_answer")
        != "__PRIOR_RESPONSE_BY_SAME_REQUEST_SEQUENCE__"
    ):
        raise OrchestrationError("RQ3_PAIR_MISMATCH")
    return turn_one, turn_two


def _build_identity(
    *,
    unit: Mapping[str, Any],
    resource: ProductionResourceIdentity,
    resolved_payload_sha256: str,
    attempt_number: int,
    checkpoint: CheckpointEvidence | None,
) -> ExecutionIdentity:
    system = formal_identity(unit["system_config_id"])
    execution_unit_id = derive_execution_unit_id(
        plan_fingerprint=PLAN_FINGERPRINT,
        request_id=unit["request_id"],
        execution_order=unit["execution_order"],
    )
    turn_id = derive_turn_id(
        execution_unit_id=execution_unit_id,
        rq=unit["rq"],
        case_id=unit["case_id"],
        turn_index=unit["turn_index"],
    )
    checkpoint_id = checkpoint.checkpoint_id if checkpoint is not None else None
    checkpoint_sha = checkpoint.checkpoint_sha256 if checkpoint is not None else None
    authority = {
        "plan_fingerprint": PLAN_FINGERPRINT,
        "execution_unit_id": execution_unit_id,
        "execution_order": unit["execution_order"],
        "request_id": unit["request_id"],
        "rq": unit["rq"],
        "case_id": unit["case_id"],
        "dialogue_id": unit["case_id"] if unit["rq"] == "RQ3" else None,
        "turn_index": unit["turn_index"],
        "system_config_id": unit["system_config_id"],
        "formal_system_id": system.formal_system_id,
        "resolved_runtime_system_id": system.resolved_runtime_system_id,
        "payload_sha256": unit["payload_sha256"],
        "resolved_payload_sha256": resolved_payload_sha256,
        "transport_contract_id": transport_contract_id(),
        "transport_contract_sha256": transport_contract_sha256(),
        "generation_contract_id": generation_contract_id(),
        "generation_contract_sha256": generation_contract_sha256(),
        "resource_identity": resource,
        "resource_identity_sha256": resource_identity_sha256(resource),
        "input_checkpoint_sha256": checkpoint_sha,
        "provider": "DeepSeek",
        "provider_model": "deepseek-chat",
    }
    attempt_id = derive_attempt_id(identity=authority, attempt_number=attempt_number)
    identity = ExecutionIdentity(
        **authority,
        turn_id=turn_id,
        input_checkpoint_id=checkpoint_id,
        attempt_number=attempt_number,
        attempt_id=attempt_id,
    )
    validate_execution_identity(identity)
    return identity


def _validate_claimed_ids(
    claimed_ids: Mapping[str, Any] | None,
    identity: ExecutionIdentity,
    provider_request_id: str,
) -> None:
    if claimed_ids is None:
        return
    expected = {
        "execution_unit_id": identity.execution_unit_id,
        "turn_id": identity.turn_id,
        "attempt_id": identity.attempt_id,
        "provider_request_id": provider_request_id,
    }
    if type(claimed_ids) is not dict or claimed_ids != expected:
        raise OrchestrationError("CALLER_IDENTITY_MISMATCH")


def _may_retry_journal(journal: InflightJournal) -> bool:
    category = journal.sanitized_outcome_category
    if category == "pre_send_failure":
        classification = retry_classification(pre_send=True)
    elif category == "http_429":
        classification = retry_classification(status_code=429)
    elif category == "http_5xx":
        classification = retry_classification(status_code=500)
    elif category == "temporary_unavailable":
        classification = retry_classification(category="temporary_unavailable")
    else:
        classification = retry_classification(category=category)
    return may_retry(journal.identity.attempt_number, classification)


def _retry_supported(journal: InflightJournal) -> None:
    if not _may_retry_journal(journal):
        raise OrchestrationError("RETRY_NOT_AUTHORIZED")


def _failure_state(
    tracker: ProviderCallTracker, boundary: _RawClientBoundary
) -> tuple[str, str]:
    if tracker.state == "explicit_retryable_failure":
        exc = boundary.exception
        status = getattr(exc, "status_code", None)
        category = getattr(exc, "category", None)
        classification = retry_classification(status_code=status, category=category)
        if classification != "retryable":
            raise OrchestrationError("PROVIDER_FAILURE_CLASSIFICATION_MISMATCH")
        if status == 429:
            return "retryable_failed", "http_429"
        if type(status) is int and 500 <= status <= 599:
            return "retryable_failed", "http_5xx"
        return "retryable_failed", "temporary_unavailable"
    if tracker.state == "uncertain_post_call_failure":
        exc = boundary.exception
        if isinstance(exc, TimeoutError):
            return "uncertain", "timeout"
        if isinstance(exc, ConnectionError):
            return "uncertain", "connection_error"
        category = getattr(exc, "category", None)
        allowed = {
            "timeout",
            "read_timeout",
            "connection_reset",
            "broken_pipe",
            "connection_error",
        }
        return "uncertain", category if category in allowed else "unknown"
    if tracker.state == "post_call_terminal_failure":
        if tracker.failure_category == "invalid_response":
            return "terminal_failed", "invalid_response"
        category = getattr(boundary.exception, "category", None)
        return (
            "terminal_failed",
            category
            if type(category) is str and category in TERMINAL_OUTCOMES
            else "provider_rejected",
        )
    raise OrchestrationError("PROVIDER_TRACKER_STATE_INVALID")


def _checked_core_result(value: Mapping[str, Any], *, turn_one: bool) -> dict[str, Any]:
    expected = _CORE_FIELDS | ({"runtime_snapshot"} if turn_one else set())
    if type(value) is not dict or set(value) != expected:
        raise OrchestrationError("CORE_RESULT_SCHEMA_INVALID")
    if (
        type(value["response_text"]) is not str
        or not value["response_text"]
        or type(value["route"]) is not str
        or not value["route"]
        or type(value["guard_category"]) is not str
        or not value["guard_category"]
        or type(value["requires_backend_api"]) is not bool
        or type(value["retrieval_used"]) is not bool
        or type(value["retrieved_document_ids"]) is not list
        or type(value["retrieved_scores"]) is not list
    ):
        raise OrchestrationError("CORE_RESULT_SCHEMA_INVALID")
    return copy.deepcopy(value)


def _projection_base(
    *,
    identity: ExecutionIdentity,
    response_text: str,
    transport_implementation_sha256: str,
    core_result: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "plan_fingerprint": identity.plan_fingerprint,
        "execution_unit_id": identity.execution_unit_id,
        "execution_order": identity.execution_order,
        "request_id": identity.request_id,
        "research_question": identity.rq,
        "case_id": identity.case_id,
        "dialogue_id": identity.dialogue_id,
        "turn_index": identity.turn_index,
        "turn_id": identity.turn_id,
        "input_checkpoint_id": identity.input_checkpoint_id,
        "input_checkpoint_sha256": identity.input_checkpoint_sha256,
        "system_config_id": identity.system_config_id,
        "formal_system_id": identity.formal_system_id,
        "resolved_runtime_system_id": identity.resolved_runtime_system_id,
        "payload_sha256": identity.payload_sha256,
        "resolved_payload_sha256": identity.resolved_payload_sha256,
        "transport_contract_id": identity.transport_contract_id,
        "transport_contract_sha256": identity.transport_contract_sha256,
        "generation_contract_id": identity.generation_contract_id,
        "generation_contract_sha256": identity.generation_contract_sha256,
        "transport_implementation_sha256": transport_implementation_sha256,
        "resource_identity": identity.resource_identity.to_dict(),
        "resource_identity_sha256": identity.resource_identity_sha256,
        "attempt_id": identity.attempt_id,
        "response_text": response_text,
        "response_sha256": sha256_text(response_text),
        "provider": identity.provider,
        "provider_model": identity.provider_model,
        "attempt_count": identity.attempt_number,
        "route": core_result["route"],
        "guard_category": core_result["guard_category"],
        "requires_backend_api": core_result["requires_backend_api"],
        "retrieval_used": core_result["retrieval_used"],
        "retrieved_document_ids": core_result["retrieved_document_ids"],
        "retrieved_scores": core_result["retrieved_scores"],
    }


def orchestrate_validated_unit(
    plan: Sequence[Mapping[str, Any]],
    unit: Mapping[str, Any],
    *,
    journal_persistence_callback: Callable[[InflightJournal], None] | None = None,
    retry_predecessor: InflightJournal | None = None,
    **dependencies: Any,
) -> OrchestrationOutcome:
    """Public B1 entry routed through the runner's complete frozen-plan authority."""

    from run_formal_evaluation import orchestrate_offline_unit

    return orchestrate_offline_unit(
        list(plan),
        dict(unit),
        journal_persistence_callback=journal_persistence_callback,
        retry_predecessor=retry_predecessor,
        **dependencies,
    )


def _orchestrate_plan_member(
    unit: Mapping[str, Any],
    *,
    resources: SyntheticResourceBundle,
    executors: ExecutorRegistry,
    fake_raw_client: Any,
    clock: Callable[[], str],
    transport_implementation_sha256: str,
    runtime_identity_sha256: str,
    snapshot_validator: Callable[[Mapping[str, Any]], Any],
    journal_persistence_callback: Callable[[InflightJournal], None] | None = None,
    retry_predecessor: InflightJournal | None = None,
    journal: InflightJournal | None = None,
    authoritative_success: AuthoritativeSuccess | Mapping[str, Any] | None = None,
    checkpoint_evidence: CheckpointEvidence | Mapping[str, Any] | None = None,
    turn_one_unit: Mapping[str, Any] | None = None,
    turn_two_unit: Mapping[str, Any] | None = None,
    claimed_ids: Mapping[str, Any] | None = None,
) -> OrchestrationOutcome:
    """Internal post-authority core; callers must enter through a public wrapper."""

    checked = _checked_unit(unit)
    checked_turn_one, checked_turn_two = _validate_rq3_pair(
        checked, turn_one_unit, turn_two_unit
    )
    if not callable(clock) or not callable(snapshot_validator):
        raise OrchestrationError("ORCHESTRATION_DEPENDENCY_INVALID")
    try:
        validate_sha256(
            transport_implementation_sha256, "TRANSPORT_IMPLEMENTATION_IDENTITY_INVALID"
        )
        validate_sha256(runtime_identity_sha256, "RUNTIME_IDENTITY_INVALID")
    except TransportError as exc:
        raise OrchestrationError(exc.category) from exc
    if type(resources) is not SyntheticResourceBundle or type(executors) is not ExecutorRegistry:
        raise OrchestrationError("ORCHESTRATION_DEPENDENCY_INVALID")
    if journal_persistence_callback is not None and not callable(
        journal_persistence_callback
    ):
        raise OrchestrationError("ORCHESTRATION_DEPENDENCY_INVALID")

    def persist_new_journal(value: InflightJournal) -> None:
        validate_journal(value)
        if journal_persistence_callback is None:
            return
        try:
            result = journal_persistence_callback(value)
        except BaseException:
            raise
        if result is not None:
            raise OrchestrationError(
                "JOURNAL_PERSISTENCE_CALLBACK_RETURN_INVALID"
            )

    checkpoint: CheckpointEvidence | None = None
    resolved_payload = copy.deepcopy(checked["payload"])
    requires_checkpoint = (
        checked["rq"] == "RQ3"
        and checked["system_config_id"] == "context_aware"
        and checked["turn_index"] == 2
    )
    checkpoint_candidate: CheckpointEvidence | None = None
    if requires_checkpoint:
        if (
            checked_turn_one is None
            or checked_turn_two is None
            or checkpoint_evidence is None
        ):
            raise OrchestrationError("TURN_TWO_CHECKPOINT_REQUIRED")
        checkpoint_candidate = (
            checkpoint_evidence
            if type(checkpoint_evidence) is CheckpointEvidence
            else CheckpointEvidence.from_mapping(checkpoint_evidence)
        )
        resolved_payload = _resolved_turn_two_payload(
            checked, checkpoint_candidate.turn_one_response_text
        )
    elif checkpoint_evidence is not None:
        raise OrchestrationError("UNEXPECTED_CHECKPOINT_EVIDENCE")

    formal_identity(checked["system_config_id"])
    resource = resources.resource_for(checked["system_config_id"])
    if requires_checkpoint:
        checkpoint = validate_checkpoint_evidence(
            checkpoint_candidate,
            turn_one_unit=checked_turn_one,
            turn_two_unit=checked_turn_two,
            resource=resource,
            runtime_identity_sha256=runtime_identity_sha256,
            snapshot_validator=snapshot_validator,
        )
        if checked != checked_turn_two:
            raise OrchestrationError("CHECKPOINT_EVIDENCE_MISMATCH")
        if _canonical_sha256(resolved_payload) != checkpoint.resolved_turn_two_payload_sha256:
            raise OrchestrationError("CHECKPOINT_PAYLOAD_DEPENDENCY_INVALID")

    attempt_number = 1
    if journal is not None:
        if type(journal) is not InflightJournal:
            raise OrchestrationError("RECOVERY_EVIDENCE_INVALID")
        attempt_number = journal.identity.attempt_number
    if authoritative_success is not None:
        success_attempt = (
            authoritative_success.identity.attempt_number
            if type(authoritative_success) is AuthoritativeSuccess
            else authoritative_success.get("identity", {}).get("attempt_number")
            if type(authoritative_success) is dict
            and type(authoritative_success.get("identity")) is dict
            else None
        )
        if type(success_attempt) is not int:
            raise OrchestrationError("RECOVERY_EVIDENCE_INVALID")
        if journal is not None and success_attempt != attempt_number:
            raise OrchestrationError("RECOVERY_EVIDENCE_CONFLICT")
        attempt_number = success_attempt

    identity = _build_identity(
        unit=checked,
        resource=resource,
        resolved_payload_sha256=_canonical_sha256(resolved_payload),
        attempt_number=attempt_number,
        checkpoint=checkpoint,
    )
    provider_request_id = derive_provider_request_id(identity)
    _validate_claimed_ids(claimed_ids, identity, provider_request_id)
    try:
        decision = recovery_decision(
            journal,
            authoritative_success=authoritative_success,
            expected=identity,
        )
    except JournalError as exc:
        raise OrchestrationError(exc.category) from exc

    initial_decision = decision
    predecessor: InflightJournal | None = None
    resumed_retry_predecessor: InflightJournal | None = None
    if journal is None:
        if retry_predecessor is not None:
            raise OrchestrationError("RECOVERY_PREDECESSOR_INVALID")
    elif (
        journal.state == "prepared"
        and journal.identity.attempt_number in {2, 3}
    ):
        if retry_predecessor is None:
            raise OrchestrationError("RECOVERY_PREDECESSOR_REQUIRED")
        if type(retry_predecessor) is not InflightJournal:
            raise OrchestrationError("RECOVERY_PREDECESSOR_INVALID")
        try:
            validate_journal(retry_predecessor)
            expected_prepared = next_retry_journal(
                retry_predecessor,
                journal.prepared_at,
            )
        except JournalError as exc:
            raise OrchestrationError("RECOVERY_PREDECESSOR_INVALID") from exc
        if (
            retry_predecessor.state != "retryable_failed"
            or retry_predecessor.identity.attempt_number
            != journal.identity.attempt_number - 1
            or expected_prepared != journal
        ):
            raise OrchestrationError("RECOVERY_PREDECESSOR_INVALID")
        resumed_retry_predecessor = retry_predecessor
    elif retry_predecessor is not None:
        raise OrchestrationError("RECOVERY_PREDECESSOR_INVALID")

    if decision == "begin":
        journal = create_initial_journal(identity, clock())
        decision = recovery_decision(journal, expected=identity)
        validate_journal(journal, identity)
        persist_new_journal(journal)
    elif decision == "retry":
        if journal is None:
            raise OrchestrationError("RECOVERY_EVIDENCE_INVALID")
        _retry_supported(journal)
        predecessor = journal
        journal = next_retry_journal(journal, clock())
        identity = _build_identity(
            unit=checked,
            resource=resource,
            resolved_payload_sha256=_canonical_sha256(resolved_payload),
            attempt_number=journal.identity.attempt_number,
            checkpoint=checkpoint,
        )
        if journal.identity != identity:
            raise OrchestrationError("RETRY_IDENTITY_MISMATCH")
        provider_request_id = derive_provider_request_id(identity)
        _validate_claimed_ids(claimed_ids, identity, provider_request_id)
        decision = recovery_decision(journal, expected=identity)
        validate_journal(journal, identity)
        persist_new_journal(journal)
    elif decision == "continue_before_provider":
        predecessor = resumed_retry_predecessor
    elif decision in {
        "authoritative_success",
        "reconcile_committed",
        "confirmed",
        "fail_closed",
    }:
        reconciled = journal
        validated_success = None
        if authoritative_success is not None:
            validated_success = validate_authoritative_success(
                authoritative_success, identity
            )
            if journal is not None and decision == "reconcile_committed":
                reconciled = reconcile(journal, validated_success, identity)
        return OrchestrationOutcome(
            action=decision,
            recovery_action=initial_decision,
            identity=identity,
            journal=reconciled,
            predecessor_journal=None,
            tracker_state="not_called",
            provider_call_count=0,
            formal_result=None,
            authoritative_success=validated_success,
            checkpoint_evidence=checkpoint,
            failure_category=(
                journal.sanitized_outcome_category
                if decision == "fail_closed" and journal is not None
                else None
            ),
        )
    else:
        raise OrchestrationError("UNKNOWN_RECOVERY_ACTION")

    if decision != "continue_before_provider" or journal is None:
        raise OrchestrationError("RECOVERY_NOT_AUTHORIZED")
    if journal.identity.attempt_number > 1 and predecessor is None:
        raise OrchestrationError("RECOVERY_PREDECESSOR_REQUIRED")
    validate_journal(journal, identity)

    tracker = ProviderCallTracker()
    boundary = _RawClientBoundary(fake_raw_client, journal, clock, provider_request_id)
    proxy = FixedGenerationProxy()
    provider_invocation_attempted = False

    def post_call_failure(failure_category: str) -> OrchestrationOutcome:
        failed = boundary.journal
        authoritative_category = failure_category
        try:
            if failed.state == "call_started":
                if tracker.state in {
                    "explicit_retryable_failure",
                    "uncertain_post_call_failure",
                    "post_call_terminal_failure",
                }:
                    state, authoritative_category = _failure_state(tracker, boundary)
                    failed = transition(
                        failed,
                        state,
                        clock(),
                        sanitized_outcome_category=authoritative_category,
                    )
                elif tracker.state == "validated_success":
                    provider_result = getattr(boundary, "normalized_response", None)
                    if type(provider_result) is NormalizedProviderResponse:
                        failed = transition(
                            failed,
                            "provider_returned",
                            clock(),
                            provider_response_id=provider_result.provider_response_id,
                            provider_response_sha256=provider_result.response_sha256,
                            response_sha256=sha256_text(provider_result.content),
                        )
                    else:
                        authoritative_category = "invalid_response"
                        failed = transition(
                            failed,
                            "terminal_failed",
                            clock(),
                            sanitized_outcome_category=authoritative_category,
                        )
                else:
                    authoritative_category = "unknown"
                    failed = transition(
                        failed,
                        "uncertain",
                        clock(),
                        sanitized_outcome_category=authoritative_category,
                    )
        except (JournalError, OrchestrationError):
            failed = boundary.journal
        if failed != boundary.journal:
            persist_new_journal(failed)
        boundary.journal = failed
        retry_available = (
            failed.state == "retryable_failed" and _may_retry_journal(failed)
        )
        return OrchestrationOutcome(
            action="retry_available" if retry_available else "fail_closed",
            recovery_action=initial_decision,
            identity=identity,
            journal=failed,
            predecessor_journal=predecessor,
            tracker_state=tracker.state,
            provider_call_count=boundary.call_count,
            formal_result=None,
            authoritative_success=None,
            checkpoint_evidence=checkpoint,
            failure_category=authoritative_category,
        )

    def invoke_provider(
        messages: Sequence[Mapping[str, str]], **overrides: Any
    ) -> NormalizedProviderResponse:
        nonlocal provider_invocation_attempted
        provider_invocation_attempted = True
        call_started = transition(
            boundary.journal,
            "call_started",
            clock(),
            provider_request_id=provider_request_id,
        )
        persist_new_journal(call_started)
        boundary.journal = call_started
        response = proxy.invoke(
            boundary,
            tracker,
            messages,
            provider_request_id=provider_request_id,
            **overrides,
        )
        boundary.normalized_response = response
        return response

    snapshot = dict(checkpoint.snapshot) if checkpoint is not None else None
    context = ExecutorContext(
        MappingProxyType(copy.deepcopy(checked)),
        identity,
        MappingProxyType(copy.deepcopy(snapshot)) if snapshot is not None else None,
        invoke_provider,
    )
    try:
        raw_core_result = executors.dispatch(context)
    except TransportError as exc:
        if boundary.call_count == 0:
            if (
                exc.category == "pre_send_failure"
                and boundary.journal.state == "prepared"
            ):
                failed = transition(
                    boundary.journal,
                    "retryable_failed",
                    clock(),
                    sanitized_outcome_category="pre_send_failure",
                )
                persist_new_journal(failed)
                boundary.journal = failed
                return OrchestrationOutcome(
                    action="retry_available",
                    recovery_action=initial_decision,
                    identity=identity,
                    journal=failed,
                    predecessor_journal=predecessor,
                    tracker_state=tracker.state,
                    provider_call_count=0,
                    formal_result=None,
                    authoritative_success=None,
                    checkpoint_evidence=checkpoint,
                    failure_category="pre_send_failure",
                )
            raise OrchestrationError(exc.category) from exc
        return post_call_failure(exc.category)
    except (JournalError, OrchestrationError) as exc:
        if boundary.call_count == 0:
            raise
        return post_call_failure(exc.category)
    except Exception as exc:
        if boundary.call_count == 0:
            # A durable call-start publication failure occurs inside the
            # executor callback, before the fake client is entered.  It
            # is the primary persistence failure and must retain its
            # original identity rather than being recategorised as an
            # executor failure.
            if provider_invocation_attempted:
                raise
            raise OrchestrationError("EXECUTOR_FAILURE") from exc
        return post_call_failure("EXECUTOR_FAILURE")

    turn_one = (
        checked["rq"] == "RQ3"
        and checked["system_config_id"] == "context_aware"
        and checked["turn_index"] == 1
    )
    try:
        core_result = _checked_core_result(raw_core_result, turn_one=turn_one)
    except OrchestrationError as exc:
        if boundary.call_count != 0:
            return post_call_failure(exc.category)
        raise
    response_text = core_result["response_text"]
    try:
        projection = _projection_base(
            identity=identity,
            response_text=response_text,
            transport_implementation_sha256=transport_implementation_sha256,
            core_result=core_result,
        )
    except OrchestrationError as exc:
        if boundary.call_count != 0:
            return post_call_failure(exc.category)
        raise
    projection["checkpoint_snapshot_sha256"] = (
        checkpoint.snapshot_sha256 if checkpoint is not None else None
    )

    success: AuthoritativeSuccess | None = None
    if tracker.state == "not_called":
        if provider_invocation_attempted or boundary.call_count != 0:
            raise OrchestrationError("LOCAL_SUCCESS_AFTER_PROVIDER_CALL")
        if core_result["route"] not in _LOCAL_ROUTES:
            raise OrchestrationError("LOCAL_PROVENANCE_INVALID")
        try:
            validate_core_result(
                tracker, response_text, success_receipt=None, local_result=True
            )
        except TransportError as exc:
            raise OrchestrationError(exc.category) from exc
        projection.update(
            {
                "execution_status": "local_success",
                "status": "local_success",
                "provider_called": False,
                "provider_request_id": None,
                "provider_response_id": None,
                "provider_response_sha256": None,
                "call_started_at": None,
                "provider_returned_at": None,
                "committed_at": None,
                "authoritative_success": None,
            }
        )
    elif tracker.state == "validated_success":
        if boundary.call_count != 1:
            return post_call_failure("PROVIDER_CALL_COUNT_INVALID")
        if core_result["route"] in _LOCAL_ROUTES:
            return post_call_failure("PROVIDER_PROVENANCE_INVALID")
        provider_result = getattr(boundary, "normalized_response", None)
        if type(provider_result) is not NormalizedProviderResponse:
            return post_call_failure("PROVIDER_RESPONSE_EVIDENCE_MISSING")
        if provider_result.content != response_text:
            return post_call_failure("PROVIDER_CORE_RESPONSE_MISMATCH")
        try:
            validate_core_result(
                tracker,
                response_text,
                success_receipt=provider_result.success_receipt,
                local_result=False,
            )
        except TransportError as exc:
            return post_call_failure(exc.category)
        try:
            returned_journal = transition(
                boundary.journal,
                "provider_returned",
                clock(),
                provider_response_id=provider_result.provider_response_id,
                provider_response_sha256=provider_result.response_sha256,
                response_sha256=sha256_text(response_text),
            )
            persist_new_journal(returned_journal)
            boundary.journal = returned_journal
            committed_at = clock()
            success = AuthoritativeSuccess(
                schema_version=1,
                identity=identity,
                provider_request_id=provider_result.provider_request_id,
                provider_response_id=provider_result.provider_response_id,
                provider_response_sha256=provider_result.response_sha256,
                response_sha256=sha256_text(response_text),
                call_started_at=returned_journal.call_started_at,
                provider_returned_at=returned_journal.provider_returned_at,
                committed_at=committed_at,
                execution_status="success",
            )
            success = validate_authoritative_success(success, identity)
        except JournalError as exc:
            return post_call_failure(exc.category)
        journal = returned_journal
        projection.update(
            {
                "execution_status": "success",
                "status": "success",
                "provider_called": True,
                "provider_request_id": success.provider_request_id,
                "provider_response_id": success.provider_response_id,
                "provider_response_sha256": success.provider_response_sha256,
                "call_started_at": success.call_started_at,
                "provider_returned_at": success.provider_returned_at,
                "committed_at": success.committed_at,
                "authoritative_success": success.to_dict(),
            }
        )
    else:
        if boundary.call_count != 0:
            return post_call_failure("UNSAFE_CORE_FALLBACK")
        raise OrchestrationError("UNSAFE_CORE_FALLBACK")

    try:
        formal_result = project_formal_result(projection)
    except TransportError as exc:
        if boundary.call_count != 0:
            return post_call_failure(exc.category)
        raise OrchestrationError(exc.category) from exc

    produced_checkpoint: CheckpointEvidence | None = checkpoint
    if turn_one:
        if checked_turn_two is None:
            raise OrchestrationError("TURN_ONE_PAIR_REQUIRED")
        try:
            produced_checkpoint = _build_checkpoint(
                turn_one=checked,
                turn_two=checked_turn_two,
                response_text=response_text,
                snapshot=core_result["runtime_snapshot"],
                resource=resource,
                runtime_identity_sha256=runtime_identity_sha256,
                snapshot_validator=snapshot_validator,
            )
        except OrchestrationError as exc:
            if boundary.call_count != 0:
                return post_call_failure(exc.category)
            raise

    return OrchestrationOutcome(
        action="success" if success is not None else "local_success",
        recovery_action=initial_decision,
        identity=identity,
        journal=journal,
        predecessor_journal=predecessor,
        tracker_state=tracker.state,
        provider_call_count=boundary.call_count,
        formal_result=MappingProxyType(formal_result),
        authoritative_success=success,
        checkpoint_evidence=produced_checkpoint,
        failure_category=None,
    )
