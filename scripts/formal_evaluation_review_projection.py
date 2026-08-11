#!/usr/bin/env python3
"""Stage B3 deterministic blinded reviewer-output projection.

This module is offline-only.  It observes validated Stage B2 private commits,
never executes a unit, and owns only the fixed ignored reviewer-projection
tree.
"""
from __future__ import annotations

import argparse
import csv
import ctypes
import hashlib
import hmac
import json
import math
import os
import re
import stat
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import formal_evaluation_store as _stage_b2_store
from formal_evaluation_inflight import derive_execution_unit_id
from formal_evaluation_store import CanonicalPrivateResultV1, StoreError
from run_formal_evaluation import (
    BASE_SEED,
    Blocked,
    PLAN_FINGERPRINT,
    build_durable_run_contract,
    build_plan,
    derive,
    observe_validated_canonical_private_results,
    plan_fingerprint,
    validate_plan,
    verify_frozen,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_PRODUCTION_REVIEWER_PROJECTION_ROOT = (
    _REPOSITORY_ROOT / "data" / "formal_eval" / "reviewer_projection"
)
_REVIEWER_PROJECTION_ROOT = _PRODUCTION_REVIEWER_PROJECTION_ROOT
_PROJECTION_CONTRACT_ID = "formal_reviewer_projection_v1"
_SCHEMA_VERSION = 1
_PLAN_FINGERPRINT = (
    "4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"
)
_SYSTEM_COUNTS = {
    "qa_only_reconstructed_baseline": 71,
    "v2": 71,
    "single_turn": 24,
    "context_aware": 24,
}
_RQ_COUNTS = {"RQ1": 102, "RQ2": 40, "RQ3": 48}
_DATA_FILES = (
    "rq1_primary_v1.json",
    "rq1_secondary_v1.json",
    "rq2_v1.json",
    "rq3_v1.json",
)
_REVIEWER_FILES = _DATA_FILES + ("manifest_v1.json",)
_PRIVATE_FILE = "projection_manifest_v1.json"
_PUBLICATION_ORDER = (_PRIVATE_FILE,) + _REVIEWER_FILES
_ARTIFACT_KIND_BY_FILE = {
    "rq1_primary_v1.json": "rq1_primary",
    "rq1_secondary_v1.json": "rq1_secondary",
    "rq2_v1.json": "rq2",
    "rq3_v1.json": "rq3",
}
_ARTIFACT_COUNTS = {
    "rq1_primary_v1.json": (102, 102),
    "rq1_secondary_v1.json": (22, 22),
    "rq2_v1.json": (40, 40),
    "rq3_v1.json": (24, 48),
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RESPONSE_ID_RE = re.compile(r"^b3r_[0-9a-f]{24}$")
_DIALOGUE_ID_RE = re.compile(r"^b3d_[0-9a-f]{24}$")
_BUNDLE_ID_RE = re.compile(r"^b3b_[0-9a-f]{24}$")
_TEMP_RE = re.compile(
    r"^\.(?P<target>[a-z0-9_]+\.json)\.(?P<nonce>[0-9a-f]{32})\.tmp$"
)
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_MOVEFILE_WRITE_THROUGH = 0x8
_JSON_MAX_DEPTH = 16
_JSON_MAX_STRING_BYTES = 262_144
_JSON_MAX_MAPPING_MEMBERS = 128
_JSON_MAX_ARRAY_MEMBERS = 256
_REVIEWER_FILE_LIMIT = 16 * 1024 * 1024
_PRIVATE_FILE_LIMIT = 4 * 1024 * 1024
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

_PROJECTION_CATEGORIES = frozenset(
    {
        "B3_PLATFORM_UNSUPPORTED",
        "B3_LOCK_BUSY",
        "B3_SOURCE_INELIGIBLE",
        "B3_INPUT_INCOMPLETE",
        "B3_PRIVATE_STATE_INVALID",
        "B3_REFERENCE_INVALID",
        "B3_SCHEMA_VERSION_MISMATCH",
        "B3_BLINDING_INCONSISTENT",
        "B3_PRIVACY_BOUNDARY_VIOLATION",
        "B3_OUTPUT_PATH_INVALID",
        "B3_ARTIFACT_INVALID",
        "B3_OUTPUT_COLLISION",
        "B3_HASH_MISMATCH",
        "B3_IO_FAILURE",
    }
)


class ProjectionError(RuntimeError):
    """Closed, sanitized Stage B3 failure category."""

    def __init__(self, category: str):
        if type(category) is not str or category not in _PROJECTION_CATEGORIES:
            raise ValueError("invalid ProjectionError category")
        self.category = category
        super().__init__(category)


@dataclass(frozen=True, slots=True)
class ReviewerProjectionOutcome:
    schema_version: int
    action: str
    reviewer_bundle_id: str
    source_unit_count: int
    reviewer_artifact_count: int
    reviewer_manifest_sha256: str
    projection_manifest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or self.action not in {"created", "resumed", "already_complete"}
            or type(self.reviewer_bundle_id) is not str
            or _BUNDLE_ID_RE.fullmatch(self.reviewer_bundle_id) is None
            or type(self.source_unit_count) is not int
            or self.source_unit_count != 190
            or type(self.reviewer_artifact_count) is not int
            or self.reviewer_artifact_count != 5
            or type(self.reviewer_manifest_sha256) is not str
            or _SHA256_RE.fullmatch(self.reviewer_manifest_sha256) is None
            or type(self.projection_manifest_sha256) is not str
            or _SHA256_RE.fullmatch(self.projection_manifest_sha256) is None
        ):
            raise ValueError("invalid ReviewerProjectionOutcome")


@dataclass(frozen=True, slots=True)
class _ReferenceBundle:
    gold: Mapping[str, Mapping[str, Any]]
    rq2: Mapping[str, Mapping[str, Any]]
    rq3: Mapping[str, Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class _ProjectionMaterial:
    reviewer_bundle_id: str
    reviewer_manifest_sha256: str
    projection_manifest_sha256: str
    objects: Mapping[str, Mapping[str, Any]]
    file_bytes: Mapping[str, bytes]


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, UnicodeError, ValueError) as exc:
        raise ProjectionError("B3_ARTIFACT_INVALID") from exc


def _canonical_file_bytes(value: object) -> bytes:
    return _canonical_json_bytes(value) + b"\n"


def domain_hash(domain: str, member: str, value: object) -> str:
    if type(domain) is not str or type(member) is not str:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    return hashlib.sha256(
        _canonical_json_bytes({"domain": domain, member: value})
    ).hexdigest()


def _ordinary_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_sha(value: object, category: str) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ProjectionError(category)
    return value


def _require_int(value: object, lower: int, upper: int, category: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ProjectionError(category)
    return value


def _display_string(value: object, *, nonempty: bool = True) -> str:
    if type(value) is not str or (nonempty and not value):
        raise ProjectionError("B3_REFERENCE_INVALID")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ProjectionError("B3_REFERENCE_INVALID") from exc
    if len(encoded) > _JSON_MAX_STRING_BYTES or "\x00" in value:
        raise ProjectionError("B3_REFERENCE_INVALID")
    return value


def _model_answer(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or not value.strip()
        or len(value) > 32_768
        or _CONTROL_RE.search(value) is not None
    ):
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    return value


def _reference_array(value: object) -> list[str]:
    if type(value) is not list or len(value) > 256:
        raise ProjectionError("B3_REFERENCE_INVALID")
    return [_display_string(item) for item in value]


def _retrieval_expected(value: object) -> bool | str:
    if type(value) is bool:
        return value
    return _display_string(value)


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, member in pairs:
        if key in value:
            raise ProjectionError("B3_ARTIFACT_INVALID")
        value[key] = member
    return value


def _reject_nonfinite(_value: str) -> None:
    raise ProjectionError("B3_ARTIFACT_INVALID")


def _recursive_limits(
    value: object,
    *,
    depth: int = 1,
    top_array_limit: int | None = None,
) -> None:
    if depth > _JSON_MAX_DEPTH:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    if type(value) is str:
        try:
            size = len(value.encode("utf-8"))
        except UnicodeError as exc:
            raise ProjectionError("B3_ARTIFACT_INVALID") from exc
        if size > _JSON_MAX_STRING_BYTES:
            raise ProjectionError("B3_ARTIFACT_INVALID")
    elif type(value) is float:
        if not math.isfinite(value):
            raise ProjectionError("B3_ARTIFACT_INVALID")
    elif type(value) is dict:
        if len(value) > _JSON_MAX_MAPPING_MEMBERS:
            raise ProjectionError("B3_ARTIFACT_INVALID")
        for key, member in value.items():
            if type(key) is not str:
                raise ProjectionError("B3_ARTIFACT_INVALID")
            _recursive_limits(member, depth=depth + 1)
    elif type(value) is list:
        limit = top_array_limit if depth == 2 and top_array_limit is not None else _JSON_MAX_ARRAY_MEMBERS
        if len(value) > limit:
            raise ProjectionError("B3_ARTIFACT_INVALID")
        for member in value:
            _recursive_limits(member, depth=depth + 1)
    elif value is not None and type(value) not in {bool, int}:
        raise ProjectionError("B3_ARTIFACT_INVALID")


def _load_canonical_json_bytes(
    raw: bytes,
    *,
    maximum: int,
    top_array_limit: int | None = None,
) -> dict[str, Any]:
    if len(raw) > maximum or raw.startswith(b"\xef\xbb\xbf"):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except ProjectionError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ProjectionError("B3_ARTIFACT_INVALID") from exc
    if type(value) is not dict:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    _recursive_limits(value, top_array_limit=top_array_limit)
    if raw != _canonical_file_bytes(value):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    return value


def _validate_fixed_module_authorities_lexically() -> None:
    expected_b3 = _REPOSITORY_ROOT / "data" / "formal_eval" / "reviewer_projection"
    expected_b2 = _REPOSITORY_ROOT / "data" / "formal_eval" / "private_state"
    if (
        PLAN_FINGERPRINT != _PLAN_FINGERPRINT
        or BASE_SEED != 20260721
        or _PRODUCTION_REVIEWER_PROJECTION_ROOT != expected_b3
        or _stage_b2_store._PRODUCTION_PRIVATE_STATE_ROOT != expected_b2
        or not isinstance(_REVIEWER_PROJECTION_ROOT, Path)
        or not _REVIEWER_PROJECTION_ROOT.is_absolute()
        or not isinstance(_stage_b2_store._PRIVATE_STATE_ROOT, Path)
        or not _stage_b2_store._PRIVATE_STATE_ROOT.is_absolute()
        or _REVIEWER_PROJECTION_ROOT == _stage_b2_store._PRIVATE_STATE_ROOT
    ):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    _validate_path_components(_REVIEWER_PROJECTION_ROOT)
    _validate_path_components(_stage_b2_store._PRIVATE_STATE_ROOT)
    if (
        _REVIEWER_PROJECTION_ROOT in _stage_b2_store._PRIVATE_STATE_ROOT.parents
        or _stage_b2_store._PRIVATE_STATE_ROOT
        in _REVIEWER_PROJECTION_ROOT.parents
    ):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")


_RUN_CONTRACT_FIELDS = {
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
_RESOURCE_IDENTITY_FIELDS = {
    "schema_version",
    "system_config_id",
    "formal_system_id",
    "resource_type",
    "logical_resource_id",
    "corpus_version",
    "cache_family",
    "corpus_path",
    "embeddings_path",
    "corpus_sha256",
    "embeddings_sha256",
    "embedding_model",
    "embedding_dimensions",
    "embedding_rows",
    "row_count",
    "qa_count",
    "snippet_count",
    "synthetic",
}
_GOLD_FIELDS = {
    "review_id",
    "external_candidate_id",
    "external_session_id",
    "question",
    "reference_answer",
    "gold_category",
    "sample_group",
    "risk_reason",
}
_SCHEMA_AUTHORITY_FIELDS = {
    "attempt_archive_schema_version",
    "b1_checkpoint_evidence_schema_version",
    "formal_result_schema_version",
    "journal_wrapper_schema_version",
    "private_commit_envelope_schema_version",
    "run_contract_schema_version",
    "stage_a_authoritative_success_schema_version",
    "stage_a_inflight_journal_schema_version",
    "stage_a_resource_identity_schema_version",
}


def _contract_string(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > _JSON_MAX_STRING_BYTES
        or _CONTROL_RE.search(value) is not None
    ):
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    return value


def _validate_authoritative_contract(contract: object) -> dict[str, Any]:
    if type(contract) is not dict or set(contract) != _RUN_CONTRACT_FIELDS:
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    try:
        _recursive_limits(contract)
        if (
            type(contract["schema_version"]) is not int
            or contract["schema_version"] != 1
            or contract["stage_id"] != "B2"
        ):
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        run_sha = _require_sha(
            contract["run_contract_sha256"], "B3_PRIVATE_STATE_INVALID"
        )
        without_hash = dict(contract)
        del without_hash["run_contract_sha256"]
        if run_sha != domain_hash(
            "formal-evaluation-run-contract-v1", "contract", without_hash
        ):
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        plan_authority = contract["plan_authority"]
        if type(plan_authority) is not dict or plan_authority != {
            "plan_fingerprint": _PLAN_FINGERPRINT,
            "base_seed": 20260721,
            "execution_unit_count": 190,
            "unique_request_id_count": 190,
            "execution_order_first": 1,
            "execution_order_last": 190,
            "rq_counts": _RQ_COUNTS,
            "system_counts": {
                "context_aware": 24,
                "qa_only_reconstructed_baseline": 71,
                "single_turn": 24,
                "v2": 71,
            },
        }:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        systems = contract["formal_system_authority"]
        if type(systems) is not dict or set(systems) != set(_SYSTEM_COUNTS):
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        formal_ids: set[str] = set()
        for system, value in systems.items():
            if type(value) is not dict or set(value) != {
                "formal_system_id",
                "resolved_runtime_system_id",
                "resource_family",
                "top_k",
                "uses_context",
                "uses_checkpoint",
            }:
                raise ProjectionError("B3_PRIVATE_STATE_INVALID")
            formal_id = _contract_string(value["formal_system_id"])
            _contract_string(value["resolved_runtime_system_id"])
            _contract_string(value["resource_family"])
            if (
                formal_id in formal_ids
                or type(value["top_k"]) is not int
                or not 1 <= value["top_k"] <= 1_000
                or type(value["uses_context"]) is not bool
                or type(value["uses_checkpoint"]) is not bool
                or value["uses_context"] != (system == "context_aware")
                or value["uses_checkpoint"] != (system == "context_aware")
            ):
                raise ProjectionError("B3_PRIVATE_STATE_INVALID")
            formal_ids.add(formal_id)
        provider = contract["provider_generation_authority"]
        if type(provider) is not dict or set(provider) != {
            "generation", "transport", "offline_execution"
        }:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        generation = provider["generation"]
        if type(generation) is not dict or set(generation) != {
            "contract_id", "contract_sha256", "runner_generation_sha256", "snapshot"
        }:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        _contract_string(generation["contract_id"])
        _require_sha(generation["contract_sha256"], "B3_PRIVATE_STATE_INVALID")
        _require_sha(
            generation["runner_generation_sha256"], "B3_PRIVATE_STATE_INVALID"
        )
        generation_snapshot = generation["snapshot"]
        if type(generation_snapshot) is not dict or set(generation_snapshot) != {
            "model", "temperature", "top_p", "max_tokens", "stream"
        }:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        _contract_string(generation_snapshot["model"])
        if (
            type(generation_snapshot["temperature"]) not in {int, float}
            or type(generation_snapshot["top_p"]) not in {int, float}
            or type(generation_snapshot["max_tokens"]) is not int
            or generation_snapshot["max_tokens"] < 1
            or type(generation_snapshot["stream"]) is not bool
        ):
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        transport = provider["transport"]
        if type(transport) is not dict or set(transport) != {
            "contract_id", "contract_sha256", "snapshot"
        }:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        _contract_string(transport["contract_id"])
        _require_sha(transport["contract_sha256"], "B3_PRIVATE_STATE_INVALID")
        transport_snapshot = transport["snapshot"]
        if type(transport_snapshot) is not dict or set(transport_snapshot) != {
            "schema_version",
            "contract_id",
            "provider",
            "base_url",
            "provider_api",
            "maximum_attempts",
            "success_receipt_schema",
        }:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        if (
            type(transport_snapshot["schema_version"]) is not int
            or transport_snapshot["schema_version"] != 1
            or transport_snapshot["contract_id"] != transport["contract_id"]
            or type(transport_snapshot["maximum_attempts"]) is not int
            or transport_snapshot["maximum_attempts"] < 1
            or type(transport_snapshot["success_receipt_schema"]) is not int
            or transport_snapshot["success_receipt_schema"] < 1
        ):
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        for name in ("contract_id", "provider", "base_url", "provider_api"):
            _contract_string(transport_snapshot[name])
        offline = provider["offline_execution"]
        if type(offline) is not dict or set(offline) != {
            "authority_bundle_id",
            "clock_id",
            "executor_registry_id",
            "fake_raw_client_id",
            "mode",
            "snapshot_validator_id",
            "test_fault_controller_id",
        }:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        for value in offline.values():
            _contract_string(value)
        runtime = contract["runtime_resource_authority"]
        if type(runtime) is not dict or set(runtime) != {
            "transport_implementation_sha256",
            "runtime_identity_sha256",
            "resources",
        }:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        _require_sha(runtime["transport_implementation_sha256"], "B3_PRIVATE_STATE_INVALID")
        _require_sha(runtime["runtime_identity_sha256"], "B3_PRIVATE_STATE_INVALID")
        resources = runtime["resources"]
        if type(resources) is not dict or set(resources) != set(_SYSTEM_COUNTS):
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        for system, wrapper in resources.items():
            if type(wrapper) is not dict or set(wrapper) != {
                "resource_identity", "resource_identity_sha256"
            }:
                raise ProjectionError("B3_PRIVATE_STATE_INVALID")
            _require_sha(wrapper["resource_identity_sha256"], "B3_PRIVATE_STATE_INVALID")
            identity = wrapper["resource_identity"]
            if (
                type(identity) is not dict
                or set(identity) != _RESOURCE_IDENTITY_FIELDS
                or identity["system_config_id"] != system
                or identity["formal_system_id"]
                != systems[system]["formal_system_id"]
                or type(identity["synthetic"]) is not bool
                or type(identity["schema_version"]) is not int
                or identity["schema_version"] != 1
            ):
                raise ProjectionError("B3_PRIVATE_STATE_INVALID")
            for name in (
                "system_config_id",
                "formal_system_id",
                "resource_type",
                "logical_resource_id",
                "corpus_version",
                "cache_family",
                "corpus_path",
                "embeddings_path",
                "embedding_model",
            ):
                _contract_string(identity[name])
            for name in ("corpus_sha256", "embeddings_sha256"):
                _require_sha(identity[name], "B3_PRIVATE_STATE_INVALID")
            for name in (
                "embedding_dimensions",
                "embedding_rows",
                "row_count",
                "qa_count",
                "snippet_count",
            ):
                if type(identity[name]) is not int or identity[name] < 0:
                    raise ProjectionError("B3_PRIVATE_STATE_INVALID")
            if (
                identity["embedding_rows"] != identity["row_count"]
                or wrapper["resource_identity_sha256"]
                != _ordinary_sha256(_canonical_json_bytes(identity))
            ):
                raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        if type(contract["frozen_input_sha256"]) is not dict or not contract[
            "frozen_input_sha256"
        ]:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        for value in contract["frozen_input_sha256"].values():
            _require_sha(value, "B3_PRIVATE_STATE_INVALID")
        if (
            type(contract["schema_authority"]) is not dict
            or set(contract["schema_authority"]) != _SCHEMA_AUTHORITY_FIELDS
        ):
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        for value in contract["schema_authority"].values():
            if type(value) is not int or value < 1:
                raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    except ProjectionError as exc:
        if exc.category == "B3_ARTIFACT_INVALID":
            raise ProjectionError("B3_PRIVATE_STATE_INVALID") from exc
        raise
    except (KeyError, TypeError) as exc:
        raise ProjectionError("B3_PRIVATE_STATE_INVALID") from exc
    return contract


def _apply_source_eligibility_gate(contract: Mapping[str, Any]) -> None:
    offline = contract["provider_generation_authority"]["offline_execution"]
    resources = contract["runtime_resource_authority"]["resources"]
    if offline["mode"] == "offline_fake_only" or any(
        resources[system]["resource_identity"]["synthetic"] is True
        for system in sorted(_SYSTEM_COUNTS)
    ):
        raise ProjectionError("B3_SOURCE_INELIGIBLE")


def _plan_member_sha256(unit: Mapping[str, Any]) -> str:
    return domain_hash(
        "formal-evaluation-plan-member-v1", "plan_member", unit
    )


def _validate_snapshot(
    plan: list[dict[str, Any]],
    contract: Mapping[str, Any],
    results: object,
) -> tuple[CanonicalPrivateResultV1, ...]:
    if type(results) is not tuple:
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    if len(results) < 190:
        raise ProjectionError("B3_INPUT_INCOMPLETE")
    if len(results) != 190:
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    by_request = {unit["request_id"]: unit for unit in plan}
    if len(by_request) != 190:
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    seen_request: set[str] = set()
    seen_unit: set[str] = set()
    rq_counts = {key: 0 for key in _RQ_COUNTS}
    system_counts = {key: 0 for key in _SYSTEM_COUNTS}
    run_sha = contract["run_contract_sha256"]
    for expected_order, result in enumerate(results, 1):
        if type(result) is not CanonicalPrivateResultV1:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        unit = by_request.get(result.request_id)
        if unit is None:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        try:
            expected_unit_id = derive_execution_unit_id(
                plan_fingerprint=_PLAN_FINGERPRINT,
                request_id=unit["request_id"],
                execution_order=unit["execution_order"],
            )
        except Exception as exc:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID") from exc
        formal_system = contract["formal_system_authority"][
            unit["system_config_id"]
        ]["formal_system_id"]
        expected = (
            result.plan_fingerprint == _PLAN_FINGERPRINT
            and result.run_contract_sha256 == run_sha
            and result.plan_member_sha256 == _plan_member_sha256(unit)
            and result.execution_unit_id == expected_unit_id
            and result.execution_order == expected_order == unit["execution_order"]
            and result.rq == unit["rq"]
            and result.case_id == unit["case_id"]
            and result.dialogue_id
            == (unit["case_id"] if unit["rq"] == "RQ3" else None)
            and result.turn_index == unit["turn_index"]
            and result.system_config_id == unit["system_config_id"]
            and result.formal_system_id == formal_system
            and _ordinary_sha256(result.response_text.encode("utf-8"))
            == result.response_sha256
        )
        if not expected:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        if result.request_id in seen_request or result.execution_unit_id in seen_unit:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        seen_request.add(result.request_id)
        seen_unit.add(result.execution_unit_id)
        rq_counts[result.rq] += 1
        system_counts[result.system_config_id] += 1
    if rq_counts != _RQ_COUNTS or system_counts != _SYSTEM_COUNTS:
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    grouped: dict[tuple[str, str], list[CanonicalPrivateResultV1]] = {}
    for result in results:
        if result.rq == "RQ3":
            grouped.setdefault(
                (result.case_id, result.system_config_id), []
            ).append(result)
    if len(grouped) != 24:
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    for (_case_id, system), members in grouped.items():
        members.sort(key=lambda item: item.turn_index)
        if len(members) != 2 or [item.turn_index for item in members] != [1, 2]:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
        first, second = members
        if system == "single_turn":
            valid = all(
                item.rq3_relationship_kind == "single_turn"
                and item.turn_one_commit_sha256 is None
                and item.checkpoint_record_sha256 is None
                for item in members
            )
        elif system == "context_aware":
            valid = (
                first.rq3_relationship_kind == "context_turn_one"
                and second.rq3_relationship_kind == "context_turn_two"
                and first.turn_one_commit_sha256 is None
                and second.turn_one_commit_sha256 == first.envelope_sha256
                and first.checkpoint_record_sha256 is not None
                and second.checkpoint_record_sha256
                == first.checkpoint_record_sha256
            )
        else:
            valid = False
        if not valid:
            raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    return results


def _strict_reference_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except ProjectionError as exc:
        raise ProjectionError("B3_REFERENCE_INVALID") from exc
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ProjectionError("B3_REFERENCE_INVALID") from exc
    if type(value) is not dict:
        raise ProjectionError("B3_REFERENCE_INVALID")
    return value


def _build_reference_bundle(
    plan: list[dict[str, Any]],
    gold_rows: object,
    rq2_value: object,
    rq3_value: object,
) -> _ReferenceBundle:
    if type(gold_rows) is not list or len(gold_rows) != 51:
        raise ProjectionError("B3_REFERENCE_INVALID")
    gold: dict[str, dict[str, Any]] = {}
    for row in gold_rows:
        if type(row) is not dict or set(row) != _GOLD_FIELDS:
            raise ProjectionError("B3_REFERENCE_INVALID")
        if not all(type(value) is str for value in row.values()):
            raise ProjectionError("B3_REFERENCE_INVALID")
        review_id = _display_string(row["review_id"])
        _display_string(row["question"])
        _display_string(row["reference_answer"])
        _display_string(row["gold_category"])
        if review_id in gold:
            raise ProjectionError("B3_REFERENCE_INVALID")
        gold[review_id] = dict(row)
    if type(rq2_value) is not dict or set(rq2_value) != {
        "schema_version", "pass_rule", "cases"
    } or rq2_value["schema_version"] != "1.0" or type(rq2_value["pass_rule"]) is not str:
        raise ProjectionError("B3_REFERENCE_INVALID")
    rq2_cases = rq2_value["cases"]
    if type(rq2_cases) is not list or len(rq2_cases) != 20:
        raise ProjectionError("B3_REFERENCE_INVALID")
    rq2: dict[str, dict[str, Any]] = {}
    rq2_fields = {
        "case_id", "category", "user_input", "expected_action_type",
        "retrieval_expected", "required_elements", "forbidden_elements",
    }
    for row in rq2_cases:
        if type(row) is not dict or set(row) != rq2_fields:
            raise ProjectionError("B3_REFERENCE_INVALID")
        case_id = _display_string(row["case_id"])
        _display_string(row["category"])
        _display_string(row["user_input"])
        _display_string(row["expected_action_type"])
        _retrieval_expected(row["retrieval_expected"])
        _reference_array(row["required_elements"])
        _reference_array(row["forbidden_elements"])
        if case_id in rq2:
            raise ProjectionError("B3_REFERENCE_INVALID")
        rq2[case_id] = dict(row)
    if type(rq3_value) is not dict or set(rq3_value) != {
        "schema_version", "pass_rule", "error_types", "cases"
    } or rq3_value["schema_version"] != "1.0" or type(rq3_value["pass_rule"]) is not str:
        raise ProjectionError("B3_REFERENCE_INVALID")
    if type(rq3_value["error_types"]) is not list or not all(
        type(item) is str for item in rq3_value["error_types"]
    ):
        raise ProjectionError("B3_REFERENCE_INVALID")
    rq3_cases = rq3_value["cases"]
    if type(rq3_cases) is not list or len(rq3_cases) != 12:
        raise ProjectionError("B3_REFERENCE_INVALID")
    rq3: dict[str, dict[str, Any]] = {}
    rq3_fields = {
        "dialogue_id", "scenario_type", "turns", "retrieval_expected",
        "expected_state_before", "expected_state_after", "reset_expected",
        "required_elements", "forbidden_elements",
    }
    turn_fields = {"user_input", "expected_action_type", "critical_turn"}
    for row in rq3_cases:
        if type(row) is not dict or set(row) != rq3_fields:
            raise ProjectionError("B3_REFERENCE_INVALID")
        dialogue_id = _display_string(row["dialogue_id"])
        for name in ("scenario_type", "expected_state_before", "expected_state_after"):
            _display_string(row[name])
        if type(row["reset_expected"]) is not bool:
            raise ProjectionError("B3_REFERENCE_INVALID")
        _retrieval_expected(row["retrieval_expected"])
        _reference_array(row["required_elements"])
        _reference_array(row["forbidden_elements"])
        turns = row["turns"]
        if type(turns) is not list or len(turns) != 2:
            raise ProjectionError("B3_REFERENCE_INVALID")
        for turn in turns:
            if type(turn) is not dict or set(turn) != turn_fields:
                raise ProjectionError("B3_REFERENCE_INVALID")
            _display_string(turn["user_input"])
            _display_string(turn["expected_action_type"])
            if type(turn["critical_turn"]) is not bool:
                raise ProjectionError("B3_REFERENCE_INVALID")
        if dialogue_id in rq3:
            raise ProjectionError("B3_REFERENCE_INVALID")
        rq3[dialogue_id] = dict(row)
    rq1_units = [unit for unit in plan if unit["rq"] == "RQ1"]
    rq2_units = [unit for unit in plan if unit["rq"] == "RQ2"]
    rq3_units = [unit for unit in plan if unit["rq"] == "RQ3"]
    if {unit["case_id"] for unit in rq1_units} != set(gold):
        raise ProjectionError("B3_REFERENCE_INVALID")
    if {unit["case_id"] for unit in rq2_units} != set(rq2):
        raise ProjectionError("B3_REFERENCE_INVALID")
    if {unit["case_id"] for unit in rq3_units} != set(rq3):
        raise ProjectionError("B3_REFERENCE_INVALID")
    for unit in rq1_units:
        if gold[unit["case_id"]]["question"] != unit["payload"]["user_input"]:
            raise ProjectionError("B3_REFERENCE_INVALID")
    for unit in rq2_units:
        if rq2[unit["case_id"]]["user_input"] != unit["payload"]["user_input"]:
            raise ProjectionError("B3_REFERENCE_INVALID")
    for unit in rq3_units:
        turns = rq3[unit["case_id"]]["turns"]
        if turns[unit["turn_index"] - 1]["user_input"] != unit["payload"]["user_input"]:
            raise ProjectionError("B3_REFERENCE_INVALID")
    return _ReferenceBundle(gold=gold, rq2=rq2, rq3=rq3)


def _load_reference_sources(plan: list[dict[str, Any]]) -> _ReferenceBundle:
    try:
        with (
            _REPOSITORY_ROOT
            / "data/external_eval/review/final/external_store_v1_gold_51.csv"
        ).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if (
                reader.fieldnames is None
                or len(reader.fieldnames) != len(set(reader.fieldnames))
                or set(reader.fieldnames) != _GOLD_FIELDS
            ):
                raise ProjectionError("B3_REFERENCE_INVALID")
            rows = [dict(row) for row in reader]
    except ProjectionError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ProjectionError("B3_REFERENCE_INVALID") from exc
    return _build_reference_bundle(
        plan,
        rows,
        _strict_reference_json(
            _REPOSITORY_ROOT / "evaluation/formal_rq2_boundary_cases.json"
        ),
        _strict_reference_json(
            _REPOSITORY_ROOT / "evaluation/formal_rq3_multiturn_cases.json"
        ),
    )


def _hmac_digest(key: bytes, domain: str, *components: str) -> bytes:
    if type(key) is not bytes or len(key) != 32 or type(domain) is not str:
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    if not all(type(component) is str for component in components):
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    message = domain.encode("utf-8")
    if components:
        message += b"\0" + b"\0".join(
            component.encode("utf-8") for component in components
        )
    return hmac.new(key, message, hashlib.sha256).digest()


def _blind_id(prefix: str, key: bytes, domain: str, *components: str) -> str:
    return prefix + _hmac_digest(key, domain, *components).hex()[:24]


def _secondary_selection(references: _ReferenceBundle) -> list[str]:
    categories: dict[str, list[Mapping[str, Any]]] = {}
    for row in references.gold.values():
        categories.setdefault(row["gold_category"], []).append(row)
    selected: list[str] = []
    for category in sorted(categories):
        selected.append(
            sorted(
                categories[category],
                key=lambda row: derive("rq1-secondary", row["review_id"]),
            )[0]["review_id"]
        )
    remaining = sorted(
        (case_id for case_id in references.gold if case_id not in selected),
        key=lambda case_id: derive("rq1-secondary-fill", case_id),
    )
    if len(selected) > 11:
        raise ProjectionError("B3_REFERENCE_INVALID")
    for case_id in remaining:
        if len(selected) == 11:
            break
        selected.append(case_id)
    if len(selected) != 11 or len(set(selected)) != 11:
        raise ProjectionError("B3_REFERENCE_INVALID")
    return selected


def _data_envelope(
    bundle_id: str,
    kind: str,
    record_count: int,
    source_unit_count: int,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "projection_contract_id": _PROJECTION_CONTRACT_ID,
        "reviewer_bundle_id": bundle_id,
        "plan_fingerprint": _PLAN_FINGERPRINT,
        "artifact_kind": kind,
        "record_count": record_count,
        "source_unit_count": source_unit_count,
        "records": records,
    }


def _build_projection_material(
    plan: list[dict[str, Any]],
    contract: Mapping[str, Any],
    results: tuple[CanonicalPrivateResultV1, ...],
    references: _ReferenceBundle,
) -> _ProjectionMaterial:
    commit_set = [
        {
            "execution_order": item.execution_order,
            "execution_unit_id": item.execution_unit_id,
            "request_id": item.request_id,
            "envelope_sha256": item.envelope_sha256,
        }
        for item in results
    ]
    commit_set_sha = domain_hash(
        "formal-evaluation-b3-canonical-commit-set-v1",
        "commits",
        commit_set,
    )
    blinding_key = hashlib.sha256(
        b"formal-evaluation-b3-blinding-key-v1\0"
        + bytes.fromhex(_PLAN_FINGERPRINT)
        + bytes.fromhex(commit_set_sha)
    ).digest()
    key_commitment = hashlib.sha256(
        b"formal-evaluation-b3-blinding-key-commitment-v1\0" + blinding_key
    ).hexdigest()
    bundle_id = _blind_id(
        "b3b_", blinding_key, "formal-evaluation-b3-bundle-id-v1"
    )
    response_ids = {
        item.request_id: _blind_id(
            "b3r_",
            blinding_key,
            "formal-evaluation-b3-response-id-v1",
            item.request_id,
        )
        for item in results
    }
    if len(set(response_ids.values())) != 190:
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    result_by_request = {item.request_id: item for item in results}
    plan_by_request = {unit["request_id"]: unit for unit in plan}
    selected_cases = _secondary_selection(references)
    selected_set = set(selected_cases)

    rq1_primary_pairs: list[tuple[bytes, dict[str, Any], str]] = []
    rq1_secondary_pairs: list[tuple[bytes, dict[str, Any], str]] = []
    rq2_pairs: list[tuple[bytes, dict[str, Any], str]] = []
    for item in results:
        unit = plan_by_request[item.request_id]
        response_id = response_ids[item.request_id]
        if item.rq == "RQ1":
            gold = references.gold[item.case_id]
            record = {
                "response_id": response_id,
                "display_payload": {
                    "question": gold["question"],
                    "reference_answer": gold["reference_answer"],
                    "model_answer": item.response_text,
                },
            }
            rq1_primary_pairs.append(
                (
                    _hmac_digest(
                        blinding_key,
                        "formal-evaluation-b3-rq1-primary-order-v1",
                        item.request_id,
                    ),
                    record,
                    response_id,
                )
            )
            if item.case_id in selected_set:
                rq1_secondary_pairs.append(
                    (
                        _hmac_digest(
                            blinding_key,
                            "formal-evaluation-b3-rq1-secondary-order-v1",
                            item.request_id,
                        ),
                        record,
                        response_id,
                    )
                )
        elif item.rq == "RQ2":
            source = references.rq2[item.case_id]
            record = {
                "response_id": response_id,
                "display_payload": {
                    "user_input": source["user_input"],
                    "model_answer": item.response_text,
                },
                "reference_payload": {
                    "expected_action_type": source["expected_action_type"],
                    "retrieval_expected": source["retrieval_expected"],
                    "required_elements": list(source["required_elements"]),
                    "forbidden_elements": list(source["forbidden_elements"]),
                },
            }
            rq2_pairs.append(
                (
                    _hmac_digest(
                        blinding_key,
                        "formal-evaluation-b3-rq2-order-v1",
                        item.request_id,
                    ),
                    record,
                    response_id,
                )
            )
    for pairs in (rq1_primary_pairs, rq1_secondary_pairs, rq2_pairs):
        keys = [item[0] for item in pairs]
        if len(keys) != len(set(keys)):
            raise ProjectionError("B3_BLINDING_INCONSISTENT")
        pairs.sort(key=lambda item: item[0])

    rq3_groups: dict[tuple[str, str], list[CanonicalPrivateResultV1]] = {}
    for item in results:
        if item.rq == "RQ3":
            rq3_groups.setdefault(
                (item.case_id, item.system_config_id), []
            ).append(item)
    conversation_ids: dict[tuple[str, str], str] = {}
    rq3_pairs: list[tuple[bytes, dict[str, Any], str]] = []
    for (case_id, system), members in rq3_groups.items():
        source = references.rq3[case_id]
        members.sort(key=lambda item: item.turn_index)
        conversation_id = _blind_id(
            "b3d_",
            blinding_key,
            "formal-evaluation-b3-dialogue-id-v1",
            case_id,
            system,
        )
        conversation_ids[(case_id, system)] = conversation_id
        turns = []
        for item in members:
            turn_source = source["turns"][item.turn_index - 1]
            turns.append(
                {
                    "response_id": response_ids[item.request_id],
                    "turn_index": item.turn_index,
                    "display_payload": {
                        "user_input": turn_source["user_input"],
                        "expected_action_type": turn_source[
                            "expected_action_type"
                        ],
                        "critical_turn": turn_source["critical_turn"],
                        "model_answer": item.response_text,
                    },
                }
            )
        record = {
            "anonymous_conversation_id": conversation_id,
            "turns": turns,
            "reference_payload": {
                "retrieval_expected": source["retrieval_expected"],
                "required_elements": list(source["required_elements"]),
                "forbidden_elements": list(source["forbidden_elements"]),
            },
        }
        rq3_pairs.append(
            (
                _hmac_digest(
                    blinding_key,
                    "formal-evaluation-b3-rq3-order-v1",
                    case_id,
                    system,
                ),
                record,
                conversation_id,
            )
        )
    if len(set(conversation_ids.values())) != 24:
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    rq3_keys = [item[0] for item in rq3_pairs]
    if len(rq3_keys) != len(set(rq3_keys)):
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    rq3_pairs.sort(key=lambda item: item[0])

    reviewer_objects: dict[str, dict[str, Any]] = {
        "rq1_primary_v1.json": _data_envelope(
            bundle_id,
            "rq1_primary",
            102,
            102,
            [item[1] for item in rq1_primary_pairs],
        ),
        "rq1_secondary_v1.json": _data_envelope(
            bundle_id,
            "rq1_secondary",
            22,
            22,
            [item[1] for item in rq1_secondary_pairs],
        ),
        "rq2_v1.json": _data_envelope(
            bundle_id, "rq2", 40, 40, [item[1] for item in rq2_pairs]
        ),
        "rq3_v1.json": _data_envelope(
            bundle_id, "rq3", 24, 48, [item[1] for item in rq3_pairs]
        ),
    }
    reviewer_bytes = {
        name: _canonical_file_bytes(value)
        for name, value in reviewer_objects.items()
    }
    artifact_entries = []
    for name in _DATA_FILES:
        record_count, source_count = _ARTIFACT_COUNTS[name]
        artifact_entries.append(
            {
                "artifact_kind": _ARTIFACT_KIND_BY_FILE[name],
                "filename": name,
                "schema_version": 1,
                "record_count": record_count,
                "source_unit_count": source_count,
                "sha256": _ordinary_sha256(reviewer_bytes[name]),
            }
        )
    reviewer_manifest_without_hash = {
        "schema_version": 1,
        "projection_contract_id": _PROJECTION_CONTRACT_ID,
        "reviewer_bundle_id": bundle_id,
        "plan_fingerprint": _PLAN_FINGERPRINT,
        "encoding": "UTF-8",
        "artifacts": artifact_entries,
    }
    reviewer_manifest_sha = domain_hash(
        "formal-evaluation-b3-reviewer-manifest-v1",
        "manifest",
        reviewer_manifest_without_hash,
    )
    reviewer_manifest = dict(reviewer_manifest_without_hash)
    reviewer_manifest["manifest_sha256"] = reviewer_manifest_sha
    reviewer_manifest_bytes = _canonical_file_bytes(reviewer_manifest)
    reviewer_objects["manifest_v1.json"] = reviewer_manifest
    reviewer_bytes["manifest_v1.json"] = reviewer_manifest_bytes
    reviewer_hashes = {
        name: _ordinary_sha256(reviewer_bytes[name]) for name in _REVIEWER_FILES
    }

    entries = []
    for item in results:
        memberships: list[str]
        if item.rq == "RQ1":
            memberships = ["rq1_primary_v1.json"]
            if item.case_id in selected_set:
                memberships.append("rq1_secondary_v1.json")
        elif item.rq == "RQ2":
            memberships = ["rq2_v1.json"]
        else:
            memberships = ["rq3_v1.json"]
        entries.append(
            {
                "execution_order": item.execution_order,
                "request_id": item.request_id,
                "execution_unit_id": item.execution_unit_id,
                "plan_member_sha256": item.plan_member_sha256,
                "rq": item.rq,
                "case_id": item.case_id,
                "dialogue_id": item.dialogue_id,
                "turn_index": item.turn_index,
                "system_config_id": item.system_config_id,
                "formal_system_id": item.formal_system_id,
                "source_envelope_sha256": item.envelope_sha256,
                "response_sha256": item.response_sha256,
                "response_id": response_ids[item.request_id],
                "anonymous_conversation_id": (
                    conversation_ids[(item.case_id, item.system_config_id)]
                    if item.rq == "RQ3"
                    else None
                ),
                "reviewer_artifacts": memberships,
                "rq3_relationship_kind": item.rq3_relationship_kind,
                "turn_one_commit_sha256": item.turn_one_commit_sha256,
                "checkpoint_record_sha256": item.checkpoint_record_sha256,
            }
        )
    selection_sha = domain_hash(
        "formal-evaluation-b3-secondary-selection-v1",
        "case_ids",
        selected_cases,
    )
    private_without_hash = {
        "schema_version": 1,
        "projection_contract_id": _PROJECTION_CONTRACT_ID,
        "reviewer_bundle_id": bundle_id,
        "plan_fingerprint": _PLAN_FINGERPRINT,
        "run_contract_sha256": contract["run_contract_sha256"],
        "canonical_commit_set_sha256": commit_set_sha,
        "blinding_key_commitment_sha256": key_commitment,
        "counts": {
            "source_units": 190,
            "unique_request_ids": 190,
            "execution_order_first": 1,
            "execution_order_last": 190,
            "by_rq": dict(_RQ_COUNTS),
            "by_system": dict(_SYSTEM_COUNTS),
            "rq1_primary_records": 102,
            "rq1_secondary_cases": 11,
            "rq1_secondary_records": 22,
            "rq2_records": 40,
            "rq3_dialogues": 24,
            "rq3_units": 48,
        },
        "secondary_selection": {
            "algorithm_id": "rq1_secondary_existing_deterministic_v1",
            "case_ids": selected_cases,
            "selection_sha256": selection_sha,
        },
        "reviewer_artifacts": reviewer_hashes,
        "entries": entries,
        "reviewer_manifest_sha256": reviewer_manifest_sha,
    }
    projection_manifest_sha = domain_hash(
        "formal-evaluation-b3-private-manifest-v1",
        "manifest",
        private_without_hash,
    )
    private_manifest = dict(private_without_hash)
    private_manifest["projection_manifest_sha256"] = projection_manifest_sha
    private_bytes = _canonical_file_bytes(private_manifest)
    objects: dict[str, Mapping[str, Any]] = {
        **reviewer_objects,
        _PRIVATE_FILE: private_manifest,
    }
    file_bytes = {**reviewer_bytes, _PRIVATE_FILE: private_bytes}
    material = _ProjectionMaterial(
        reviewer_bundle_id=bundle_id,
        reviewer_manifest_sha256=reviewer_manifest_sha,
        projection_manifest_sha256=projection_manifest_sha,
        objects=objects,
        file_bytes=file_bytes,
    )
    _validate_material(material)
    return material


def _artifact_text(value: object, *, model_answer: bool = False) -> str:
    if type(value) is not str or not value:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    try:
        encoded = value.encode("utf-8")
    except UnicodeError as exc:
        raise ProjectionError("B3_ARTIFACT_INVALID") from exc
    if len(encoded) > _JSON_MAX_STRING_BYTES or "\x00" in value:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    if model_answer and (
        not value.strip()
        or len(value) > 32_768
        or _CONTROL_RE.search(value) is not None
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    return value


def _artifact_reference_array(value: object) -> None:
    if type(value) is not list or len(value) > 256:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    for item in value:
        _artifact_text(item)


def _artifact_retrieval(value: object) -> None:
    if type(value) is bool:
        return
    _artifact_text(value)


def _validate_data_artifact_shape(
    filename: str, value: Mapping[str, Any]
) -> None:
    if type(value) is not dict or set(value) != {
        "schema_version",
        "projection_contract_id",
        "reviewer_bundle_id",
        "plan_fingerprint",
        "artifact_kind",
        "record_count",
        "source_unit_count",
        "records",
    }:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    if (
        type(value["reviewer_bundle_id"]) is not str
        or _BUNDLE_ID_RE.fullmatch(value["reviewer_bundle_id"]) is None
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    _require_sha(value["plan_fingerprint"], "B3_ARTIFACT_INVALID")
    expected_record_count, expected_source_count = _ARTIFACT_COUNTS[filename]
    if (
        type(value["record_count"]) is not int
        or value["record_count"] != expected_record_count
        or type(value["source_unit_count"]) is not int
        or value["source_unit_count"] != expected_source_count
        or type(value["records"]) is not list
        or len(value["records"]) != expected_record_count
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    response_ids: list[str] = []
    conversation_ids: list[str] = []
    if filename in {"rq1_primary_v1.json", "rq1_secondary_v1.json"}:
        for record in value["records"]:
            if type(record) is not dict or set(record) != {
                "response_id", "display_payload"
            }:
                raise ProjectionError("B3_ARTIFACT_INVALID")
            if (
                type(record["response_id"]) is not str
                or _RESPONSE_ID_RE.fullmatch(record["response_id"]) is None
            ):
                raise ProjectionError("B3_ARTIFACT_INVALID")
            display = record["display_payload"]
            if type(display) is not dict or set(display) != {
                "question", "reference_answer", "model_answer"
            }:
                raise ProjectionError("B3_ARTIFACT_INVALID")
            _artifact_text(display["question"])
            _artifact_text(display["reference_answer"])
            _artifact_text(display["model_answer"], model_answer=True)
            response_ids.append(record["response_id"])
    elif filename == "rq2_v1.json":
        for record in value["records"]:
            if type(record) is not dict or set(record) != {
                "response_id", "display_payload", "reference_payload"
            }:
                raise ProjectionError("B3_ARTIFACT_INVALID")
            if (
                type(record["response_id"]) is not str
                or _RESPONSE_ID_RE.fullmatch(record["response_id"]) is None
            ):
                raise ProjectionError("B3_ARTIFACT_INVALID")
            display = record["display_payload"]
            reference = record["reference_payload"]
            if type(display) is not dict or set(display) != {
                "user_input", "model_answer"
            } or type(reference) is not dict or set(reference) != {
                "expected_action_type",
                "retrieval_expected",
                "required_elements",
                "forbidden_elements",
            }:
                raise ProjectionError("B3_ARTIFACT_INVALID")
            _artifact_text(display["user_input"])
            _artifact_text(display["model_answer"], model_answer=True)
            _artifact_text(reference["expected_action_type"])
            _artifact_retrieval(reference["retrieval_expected"])
            _artifact_reference_array(reference["required_elements"])
            _artifact_reference_array(reference["forbidden_elements"])
            response_ids.append(record["response_id"])
    elif filename == "rq3_v1.json":
        for record in value["records"]:
            if type(record) is not dict or set(record) != {
                "anonymous_conversation_id", "turns", "reference_payload"
            }:
                raise ProjectionError("B3_ARTIFACT_INVALID")
            conversation_id = record["anonymous_conversation_id"]
            if (
                type(conversation_id) is not str
                or _DIALOGUE_ID_RE.fullmatch(conversation_id) is None
            ):
                raise ProjectionError("B3_ARTIFACT_INVALID")
            turns = record["turns"]
            reference = record["reference_payload"]
            if (
                type(turns) is not list
                or len(turns) != 2
                or type(reference) is not dict
                or set(reference)
                != {
                    "retrieval_expected",
                    "required_elements",
                    "forbidden_elements",
                }
            ):
                raise ProjectionError("B3_ARTIFACT_INVALID")
            _artifact_retrieval(reference["retrieval_expected"])
            _artifact_reference_array(reference["required_elements"])
            _artifact_reference_array(reference["forbidden_elements"])
            for expected_turn, turn in enumerate(turns, 1):
                if type(turn) is not dict or set(turn) != {
                    "response_id", "turn_index", "display_payload"
                }:
                    raise ProjectionError("B3_ARTIFACT_INVALID")
                if (
                    type(turn["response_id"]) is not str
                    or _RESPONSE_ID_RE.fullmatch(turn["response_id"]) is None
                    or type(turn["turn_index"]) is not int
                    or turn["turn_index"] != expected_turn
                ):
                    raise ProjectionError("B3_ARTIFACT_INVALID")
                display = turn["display_payload"]
                if type(display) is not dict or set(display) != {
                    "user_input",
                    "expected_action_type",
                    "critical_turn",
                    "model_answer",
                }:
                    raise ProjectionError("B3_ARTIFACT_INVALID")
                _artifact_text(display["user_input"])
                _artifact_text(display["expected_action_type"])
                if type(display["critical_turn"]) is not bool:
                    raise ProjectionError("B3_ARTIFACT_INVALID")
                _artifact_text(display["model_answer"], model_answer=True)
                response_ids.append(turn["response_id"])
            conversation_ids.append(conversation_id)
    else:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    if len(response_ids) != len(set(response_ids)) or len(conversation_ids) != len(
        set(conversation_ids)
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")


def _validate_data_artifact_identity(
    filename: str, value: Mapping[str, Any]
) -> None:
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["projection_contract_id"] != _PROJECTION_CONTRACT_ID
        or value["artifact_kind"] != _ARTIFACT_KIND_BY_FILE[filename]
    ):
        raise ProjectionError("B3_SCHEMA_VERSION_MISMATCH")


def _validate_reviewer_manifest_shape(value: Mapping[str, Any]) -> None:
    if type(value) is not dict or set(value) != {
        "schema_version",
        "projection_contract_id",
        "reviewer_bundle_id",
        "plan_fingerprint",
        "encoding",
        "artifacts",
        "manifest_sha256",
    }:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    if (
        type(value["reviewer_bundle_id"]) is not str
        or _BUNDLE_ID_RE.fullmatch(value["reviewer_bundle_id"]) is None
        or value["encoding"] != "UTF-8"
        or type(value["artifacts"]) is not list
        or len(value["artifacts"]) != 4
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    _require_sha(value["plan_fingerprint"], "B3_ARTIFACT_INVALID")
    _require_sha(value["manifest_sha256"], "B3_ARTIFACT_INVALID")
    for index, entry in enumerate(value["artifacts"]):
        filename = _DATA_FILES[index]
        record_count, source_count = _ARTIFACT_COUNTS[filename]
        if type(entry) is not dict or set(entry) != {
            "artifact_kind",
            "filename",
            "schema_version",
            "record_count",
            "source_unit_count",
            "sha256",
        }:
            raise ProjectionError("B3_ARTIFACT_INVALID")
        if (
            entry["filename"] != filename
            or type(entry["record_count"]) is not int
            or entry["record_count"] != record_count
            or type(entry["source_unit_count"]) is not int
            or entry["source_unit_count"] != source_count
        ):
            raise ProjectionError("B3_ARTIFACT_INVALID")
        _require_sha(entry["sha256"], "B3_ARTIFACT_INVALID")


def _validate_reviewer_manifest_identity(value: Mapping[str, Any]) -> None:
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["projection_contract_id"] != _PROJECTION_CONTRACT_ID
    ):
        raise ProjectionError("B3_SCHEMA_VERSION_MISMATCH")
    for filename, entry in zip(_DATA_FILES, value["artifacts"]):
        if (
            type(entry["schema_version"]) is not int
            or entry["schema_version"] != 1
            or entry["artifact_kind"] != _ARTIFACT_KIND_BY_FILE[filename]
        ):
            raise ProjectionError("B3_SCHEMA_VERSION_MISMATCH")


_PRIVATE_TOP_FIELDS = {
    "schema_version",
    "projection_contract_id",
    "reviewer_bundle_id",
    "plan_fingerprint",
    "run_contract_sha256",
    "canonical_commit_set_sha256",
    "blinding_key_commitment_sha256",
    "counts",
    "secondary_selection",
    "reviewer_artifacts",
    "entries",
    "reviewer_manifest_sha256",
    "projection_manifest_sha256",
}
_PRIVATE_ENTRY_FIELDS = {
    "execution_order",
    "request_id",
    "execution_unit_id",
    "plan_member_sha256",
    "rq",
    "case_id",
    "dialogue_id",
    "turn_index",
    "system_config_id",
    "formal_system_id",
    "source_envelope_sha256",
    "response_sha256",
    "response_id",
    "anonymous_conversation_id",
    "reviewer_artifacts",
    "rq3_relationship_kind",
    "turn_one_commit_sha256",
    "checkpoint_record_sha256",
}


def _validate_private_manifest_shape(value: Mapping[str, Any]) -> None:
    if type(value) is not dict or set(value) != _PRIVATE_TOP_FIELDS:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    if (
        type(value["reviewer_bundle_id"]) is not str
        or _BUNDLE_ID_RE.fullmatch(value["reviewer_bundle_id"]) is None
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    for name in (
        "plan_fingerprint",
        "run_contract_sha256",
        "canonical_commit_set_sha256",
        "blinding_key_commitment_sha256",
        "reviewer_manifest_sha256",
        "projection_manifest_sha256",
    ):
        _require_sha(value[name], "B3_ARTIFACT_INVALID")
    counts = value["counts"]
    if type(counts) is not dict or set(counts) != {
        "source_units",
        "unique_request_ids",
        "execution_order_first",
        "execution_order_last",
        "by_rq",
        "by_system",
        "rq1_primary_records",
        "rq1_secondary_cases",
        "rq1_secondary_records",
        "rq2_records",
        "rq3_dialogues",
        "rq3_units",
    }:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    for name, member in counts.items():
        if name in {"by_rq", "by_system"}:
            continue
        _require_int(member, 0, 190, "B3_ARTIFACT_INVALID")
    if (
        type(counts["by_rq"]) is not dict
        or set(counts["by_rq"]) != set(_RQ_COUNTS)
        or type(counts["by_system"]) is not dict
        or set(counts["by_system"]) != set(_SYSTEM_COUNTS)
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    for member in counts["by_rq"].values():
        _require_int(member, 0, 190, "B3_ARTIFACT_INVALID")
    for member in counts["by_system"].values():
        _require_int(member, 0, 190, "B3_ARTIFACT_INVALID")
    selection = value["secondary_selection"]
    if type(selection) is not dict or set(selection) != {
        "algorithm_id", "case_ids", "selection_sha256"
    }:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    case_ids = selection["case_ids"]
    if (
        type(selection["algorithm_id"]) is not str
        or not selection["algorithm_id"]
        or type(case_ids) is not list
        or len(case_ids) != 11
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    for case_id in case_ids:
        _artifact_text(case_id)
    if len(set(case_ids)) != 11:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    _require_sha(selection["selection_sha256"], "B3_ARTIFACT_INVALID")
    reviewer_hashes = value["reviewer_artifacts"]
    if type(reviewer_hashes) is not dict or set(reviewer_hashes) != set(
        _REVIEWER_FILES
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    for member in reviewer_hashes.values():
        _require_sha(member, "B3_ARTIFACT_INVALID")
    entries = value["entries"]
    if type(entries) is not list or len(entries) != 190:
        raise ProjectionError("B3_ARTIFACT_INVALID")
    response_ids: list[str] = []
    request_ids: list[str] = []
    execution_ids: list[str] = []
    for entry in entries:
        if type(entry) is not dict or set(entry) != _PRIVATE_ENTRY_FIELDS:
            raise ProjectionError("B3_ARTIFACT_INVALID")
        _require_int(entry["execution_order"], 1, 190, "B3_ARTIFACT_INVALID")
        _require_int(entry["turn_index"], 1, 2, "B3_ARTIFACT_INVALID")
        for name in (
            "request_id",
            "execution_unit_id",
            "plan_member_sha256",
            "source_envelope_sha256",
            "response_sha256",
        ):
            _require_sha(entry[name], "B3_ARTIFACT_INVALID")
        for name in ("turn_one_commit_sha256", "checkpoint_record_sha256"):
            if entry[name] is not None:
                _require_sha(entry[name], "B3_ARTIFACT_INVALID")
        for name in ("rq", "case_id", "system_config_id", "formal_system_id", "rq3_relationship_kind"):
            _artifact_text(entry[name])
        if entry["dialogue_id"] is not None:
            _artifact_text(entry["dialogue_id"])
        if (
            type(entry["response_id"]) is not str
            or _RESPONSE_ID_RE.fullmatch(entry["response_id"]) is None
        ):
            raise ProjectionError("B3_ARTIFACT_INVALID")
        if entry["anonymous_conversation_id"] is not None and (
            type(entry["anonymous_conversation_id"]) is not str
            or _DIALOGUE_ID_RE.fullmatch(entry["anonymous_conversation_id"])
            is None
        ):
            raise ProjectionError("B3_ARTIFACT_INVALID")
        memberships = entry["reviewer_artifacts"]
        if type(memberships) is not list or not 1 <= len(memberships) <= 2 or not all(
            type(name) is str and name in _DATA_FILES for name in memberships
        ):
            raise ProjectionError("B3_ARTIFACT_INVALID")
        rq = entry["rq"]
        system = entry["system_config_id"]
        if rq == "RQ1":
            if system not in {"qa_only_reconstructed_baseline", "v2"} or memberships not in (
                ["rq1_primary_v1.json"],
                ["rq1_primary_v1.json", "rq1_secondary_v1.json"],
            ):
                raise ProjectionError("B3_ARTIFACT_INVALID")
        elif rq == "RQ2":
            if (
                system not in {"qa_only_reconstructed_baseline", "v2"}
                or memberships != ["rq2_v1.json"]
            ):
                raise ProjectionError("B3_ARTIFACT_INVALID")
        elif rq == "RQ3":
            if (
                system not in {"single_turn", "context_aware"}
                or memberships != ["rq3_v1.json"]
                or entry["dialogue_id"] is None
                or entry["anonymous_conversation_id"] is None
            ):
                raise ProjectionError("B3_ARTIFACT_INVALID")
        else:
            raise ProjectionError("B3_ARTIFACT_INVALID")
        if rq != "RQ3" and (
            entry["dialogue_id"] is not None
            or entry["anonymous_conversation_id"] is not None
            or entry["rq3_relationship_kind"] != "none"
            or entry["turn_one_commit_sha256"] is not None
            or entry["checkpoint_record_sha256"] is not None
        ):
            raise ProjectionError("B3_ARTIFACT_INVALID")
        if rq == "RQ3" and system == "single_turn" and (
            entry["rq3_relationship_kind"] != "single_turn"
            or entry["turn_one_commit_sha256"] is not None
            or entry["checkpoint_record_sha256"] is not None
        ):
            raise ProjectionError("B3_ARTIFACT_INVALID")
        if rq == "RQ3" and system == "context_aware":
            if entry["turn_index"] == 1:
                relationship_valid = (
                    entry["rq3_relationship_kind"] == "context_turn_one"
                    and entry["turn_one_commit_sha256"] is None
                    and entry["checkpoint_record_sha256"] is not None
                )
            else:
                relationship_valid = (
                    entry["rq3_relationship_kind"] == "context_turn_two"
                    and entry["turn_one_commit_sha256"] is not None
                    and entry["checkpoint_record_sha256"] is not None
                )
            if not relationship_valid:
                raise ProjectionError("B3_ARTIFACT_INVALID")
        response_ids.append(entry["response_id"])
        request_ids.append(entry["request_id"])
        execution_ids.append(entry["execution_unit_id"])
    if (
        len(set(response_ids)) != 190
        or len(set(request_ids)) != 190
        or len(set(execution_ids)) != 190
    ):
        raise ProjectionError("B3_ARTIFACT_INVALID")


def _validate_private_manifest_identity(value: Mapping[str, Any]) -> None:
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["projection_contract_id"] != _PROJECTION_CONTRACT_ID
    ):
        raise ProjectionError("B3_SCHEMA_VERSION_MISMATCH")


def _validate_hash_relationships(
    objects: Mapping[str, Mapping[str, Any]],
    raw_bytes: Mapping[str, bytes],
) -> None:
    manifest = objects.get("manifest_v1.json")
    if manifest is not None:
        without_hash = dict(manifest)
        without_hash.pop("manifest_sha256", None)
        expected_internal = domain_hash(
            "formal-evaluation-b3-reviewer-manifest-v1",
            "manifest",
            without_hash,
        )
        if manifest["manifest_sha256"] != expected_internal:
            raise ProjectionError("B3_HASH_MISMATCH")
        for entry in manifest["artifacts"]:
            filename = entry["filename"]
            if filename not in raw_bytes or entry["sha256"] != _ordinary_sha256(
                raw_bytes[filename]
            ):
                raise ProjectionError("B3_HASH_MISMATCH")
    private = objects.get(_PRIVATE_FILE)
    if private is not None:
        without_hash = dict(private)
        without_hash.pop("projection_manifest_sha256", None)
        expected_private = domain_hash(
            "formal-evaluation-b3-private-manifest-v1",
            "manifest",
            without_hash,
        )
        if private["projection_manifest_sha256"] != expected_private:
            raise ProjectionError("B3_HASH_MISMATCH")
        selection = private["secondary_selection"]
        if selection["selection_sha256"] != domain_hash(
            "formal-evaluation-b3-secondary-selection-v1",
            "case_ids",
            selection["case_ids"],
        ):
            raise ProjectionError("B3_HASH_MISMATCH")
        for filename, declared in private["reviewer_artifacts"].items():
            if filename in raw_bytes and declared != _ordinary_sha256(
                raw_bytes[filename]
            ):
                raise ProjectionError("B3_HASH_MISMATCH")
        if manifest is not None and private["reviewer_manifest_sha256"] != manifest[
            "manifest_sha256"
        ]:
            raise ProjectionError("B3_HASH_MISMATCH")


_PROHIBITED_REVIEWER_KEYS = {
    "system_config_id",
    "formal_system_id",
    "resolved_runtime_system_id",
    "condition",
    "request_id",
    "execution_unit_id",
    "execution_order",
    "case_id",
    "dialogue_id",
    "review_id",
    "attempt_id",
    "checkpoint_id",
    "provider",
    "provider_model",
    "provider_request_id",
    "provider_response_id",
    "prompt",
    "retrieved_document_ids",
    "retrieved_scores",
    "checkpoint_record_sha256",
    "source_envelope_sha256",
    "response_sha256",
    "run_contract_sha256",
    "timestamp",
    "exception",
    "score",
    "reviewer_id",
}


def _validate_privacy_boundary(objects: Mapping[str, Mapping[str, Any]]) -> None:
    def walk(value: object) -> None:
        if type(value) is dict:
            if set(value) & _PROHIBITED_REVIEWER_KEYS:
                raise ProjectionError("B3_PRIVACY_BOUNDARY_VIOLATION")
            for member in value.values():
                walk(member)
        elif type(value) is list:
            for member in value:
                walk(member)

    for filename in _REVIEWER_FILES:
        walk(objects[filename])


def _validate_cross_artifact_consistency(
    objects: Mapping[str, Mapping[str, Any]]
) -> None:
    bundle_ids = {objects[name]["reviewer_bundle_id"] for name in _REVIEWER_FILES}
    fingerprints = {objects[name]["plan_fingerprint"] for name in _REVIEWER_FILES}
    if len(bundle_ids) != 1 or fingerprints != {_PLAN_FINGERPRINT}:
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    primary_ids = {
        record["response_id"]
        for record in objects["rq1_primary_v1.json"]["records"]
    }
    secondary_ids = {
        record["response_id"]
        for record in objects["rq1_secondary_v1.json"]["records"]
    }
    if len(secondary_ids) != 22 or not secondary_ids < primary_ids:
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    private = objects[_PRIVATE_FILE]
    if (
        private["reviewer_bundle_id"] not in bundle_ids
        or private["plan_fingerprint"] != _PLAN_FINGERPRINT
        or private["counts"]
        != {
            "source_units": 190,
            "unique_request_ids": 190,
            "execution_order_first": 1,
            "execution_order_last": 190,
            "by_rq": _RQ_COUNTS,
            "by_system": _SYSTEM_COUNTS,
            "rq1_primary_records": 102,
            "rq1_secondary_cases": 11,
            "rq1_secondary_records": 22,
            "rq2_records": 40,
            "rq3_dialogues": 24,
            "rq3_units": 48,
        }
        or private["secondary_selection"]["algorithm_id"]
        != "rq1_secondary_existing_deterministic_v1"
        or [entry["execution_order"] for entry in private["entries"]]
        != list(range(1, 191))
    ):
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    mapped_ids = {entry["response_id"] for entry in private["entries"]}
    primary_unit_ids = primary_ids
    rq2_ids = {
        record["response_id"] for record in objects["rq2_v1.json"]["records"]
    }
    rq3_ids = {
        turn["response_id"]
        for record in objects["rq3_v1.json"]["records"]
        for turn in record["turns"]
    }
    if mapped_ids != primary_unit_ids | rq2_ids | rq3_ids:
        raise ProjectionError("B3_BLINDING_INCONSISTENT")
    mapped_secondary = {
        entry["response_id"]
        for entry in private["entries"]
        if "rq1_secondary_v1.json" in entry["reviewer_artifacts"]
    }
    if mapped_secondary != secondary_ids:
        raise ProjectionError("B3_BLINDING_INCONSISTENT")


def _validate_material(material: _ProjectionMaterial) -> None:
    if set(material.objects) != set(_PUBLICATION_ORDER) or set(
        material.file_bytes
    ) != set(_PUBLICATION_ORDER):
        raise ProjectionError("B3_ARTIFACT_INVALID")
    for filename in _DATA_FILES:
        _validate_data_artifact_shape(filename, material.objects[filename])
        _validate_data_artifact_identity(filename, material.objects[filename])
    _validate_reviewer_manifest_shape(material.objects["manifest_v1.json"])
    _validate_reviewer_manifest_identity(material.objects["manifest_v1.json"])
    _validate_private_manifest_shape(material.objects[_PRIVATE_FILE])
    _validate_private_manifest_identity(material.objects[_PRIVATE_FILE])
    for filename, value in material.objects.items():
        if material.file_bytes[filename] != _canonical_file_bytes(value):
            raise ProjectionError("B3_ARTIFACT_INVALID")
        limit = _PRIVATE_FILE_LIMIT if filename == _PRIVATE_FILE else _REVIEWER_FILE_LIMIT
        if len(material.file_bytes[filename]) > limit:
            raise ProjectionError("B3_ARTIFACT_INVALID")
    _validate_hash_relationships(material.objects, material.file_bytes)
    _validate_cross_artifact_consistency(material.objects)
    _validate_privacy_boundary(material.objects)
    if (
        material.reviewer_manifest_sha256
        != material.objects["manifest_v1.json"]["manifest_sha256"]
        or material.reviewer_manifest_sha256
        != material.objects[_PRIVATE_FILE]["reviewer_manifest_sha256"]
        or material.projection_manifest_sha256
        != material.objects[_PRIVATE_FILE]["projection_manifest_sha256"]
    ):
        raise ProjectionError("B3_HASH_MISMATCH")


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError as exc:
        raise ProjectionError("B3_OUTPUT_PATH_INVALID") from exc
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0)
        & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or _is_within(first, second) or _is_within(
        second, first
    )


def _validate_path_components(path: Path) -> None:
    reserved = {
        "con", "prn", "aux", "nul", "clock$",
        *(f"com{number}" for number in range(1, 10)),
        *(f"lpt{number}" for number in range(1, 10)),
    }
    anchor = path.anchor
    if (
        anchor.startswith(("\\\\", "//"))
        or anchor.startswith(("\\\\?\\", "\\\\.\\"))
        or not path.drive
        or not anchor.endswith(("\\", "/"))
    ):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    for part in path.parts[1:]:
        if (
            not part
            or part in {".", ".."}
            or part.endswith((" ", "."))
            or any(ord(character) < 32 for character in part)
            or part.casefold().split(".", 1)[0] in reserved
            or "/" in part
            or "\\" in part
            or ":" in part
            or "://" in part
        ):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")


def _validate_projection_root_for_access() -> Path:
    root = _REVIEWER_PROJECTION_ROOT
    b2_root = _stage_b2_store._PRIVATE_STATE_ROOT
    if (
        not isinstance(root, Path)
        or not root.is_absolute()
        or not isinstance(b2_root, Path)
        or not b2_root.is_absolute()
    ):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    _validate_path_components(root)
    _validate_path_components(b2_root)
    try:
        resolved = root.resolve(strict=False)
        resolved_b2 = b2_root.resolve(strict=False)
    except OSError as exc:
        raise ProjectionError("B3_OUTPUT_PATH_INVALID") from exc
    if _paths_overlap(resolved, resolved_b2):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    if root != _PRODUCTION_REVIEWER_PROJECTION_ROOT:
        try:
            temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
        except OSError as exc:
            raise ProjectionError("B3_OUTPUT_PATH_INVALID") from exc
        if (
            resolved == temp_root
            or not _is_within(resolved, temp_root)
            or resolved == _PRODUCTION_REVIEWER_PROJECTION_ROOT
            or resolved_b2
            == _stage_b2_store._PRODUCTION_PRIVATE_STATE_ROOT
        ):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current = current / part
        if current.exists() and _is_reparse(current):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    return root


def _regular_nonreparse(path: Path) -> bool:
    return path.exists() and not _is_reparse(path) and path.is_file()


def _directory_nonreparse(path: Path) -> bool:
    return path.exists() and not _is_reparse(path) and path.is_dir()


def _owned_temp_target(path: Path, directory_kind: str) -> str | None:
    match = _TEMP_RE.fullmatch(path.name)
    if match is None:
        return None
    target = match.group("target")
    allowed = {_PRIVATE_FILE} if directory_kind == "private" else set(
        _REVIEWER_FILES
    )
    return target if target in allowed else None


def _scan_existing_top_before_creation(root: Path) -> None:
    if not root.exists():
        return
    if not _directory_nonreparse(root):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    allowed = {"private", "reviewer", "projection.lock"}
    try:
        paths = list(root.iterdir())
    except OSError as exc:
        raise ProjectionError("B3_OUTPUT_PATH_INVALID") from exc
    for path in paths:
        if path.name not in allowed or _is_reparse(path):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        if path.name in {"private", "reviewer"} and not path.is_dir():
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        if path.name == "projection.lock":
            if not path.is_file():
                raise ProjectionError("B3_OUTPUT_PATH_INVALID")
            try:
                if path.read_bytes() != b"\x00":
                    raise ProjectionError("B3_OUTPUT_PATH_INVALID")
            except ProjectionError:
                raise
            except OSError as exc:
                raise ProjectionError("B3_OUTPUT_PATH_INVALID") from exc


def _ensure_projection_directories(root: Path) -> None:
    _scan_existing_top_before_creation(root)
    if not root.exists():
        parent = root.parent
        if not _directory_nonreparse(parent):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        try:
            root.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            raise ProjectionError("B3_IO_FAILURE") from exc
        if not _directory_nonreparse(root):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    _scan_existing_top_before_creation(root)
    for path in (root / "private", root / "reviewer"):
        if path.exists():
            if not _directory_nonreparse(path):
                raise ProjectionError("B3_OUTPUT_PATH_INVALID")
            continue
        try:
            path.mkdir()
        except FileExistsError:
            if not _directory_nonreparse(path):
                raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        except OSError as exc:
            raise ProjectionError("B3_IO_FAILURE") from exc
        if not _directory_nonreparse(path):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")


_LEASED_PROJECTION_LOCKS: set[str] = set()
_LEASED_PROJECTION_LOCKS_GUARD = threading.Lock()


class _ProjectionLock:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "projection.lock"
        self.handle: Any = None
        self.locked = False
        self.pid: int | None = None
        self.thread_id: int | None = None
        self.registry_key: str | None = None

    def __enter__(self) -> "_ProjectionLock":
        if os.name != "nt":
            raise ProjectionError("B3_PLATFORM_UNSUPPORTED")
        try:
            import msvcrt
        except ImportError as exc:
            raise ProjectionError("B3_PLATFORM_UNSUPPORTED") from exc
        if not _directory_nonreparse(self.root):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        if not self.path.exists():
            try:
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY,
                )
                try:
                    if os.write(descriptor, b"\x00") != 1:
                        raise ProjectionError("B3_IO_FAILURE")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except FileExistsError:
                pass
            except ProjectionError:
                raise
            except OSError as exc:
                raise ProjectionError("B3_IO_FAILURE") from exc
        if not _regular_nonreparse(self.path):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        try:
            self.handle = self.path.open("r+b", buffering=0)
        except OSError as exc:
            raise ProjectionError("B3_OUTPUT_PATH_INVALID") from exc
        key = str(self.path).casefold()
        with _LEASED_PROJECTION_LOCKS_GUARD:
            if key in _LEASED_PROJECTION_LOCKS:
                self.handle.close()
                self.handle = None
                raise ProjectionError("B3_LOCK_BUSY")
            _LEASED_PROJECTION_LOCKS.add(key)
            self.registry_key = key
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
                        raise ProjectionError("B3_LOCK_BUSY") from exc
                    time.sleep(0.05)
            self.pid = os.getpid()
            self.thread_id = threading.get_ident()
            self.handle.seek(0)
            if self.handle.read(2) != b"\x00" or _is_reparse(self.path):
                raise ProjectionError("B3_OUTPUT_PATH_INVALID")
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, _type: object, _value: object, _tb: object) -> None:
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
            if self.registry_key is not None:
                with _LEASED_PROJECTION_LOCKS_GUARD:
                    _LEASED_PROJECTION_LOCKS.discard(self.registry_key)
                self.registry_key = None

    def require_active(self) -> None:
        if (
            type(self) is not _ProjectionLock
            or not self.locked
            or self.handle is None
            or self.pid != os.getpid()
            or self.thread_id != threading.get_ident()
            or self.root != _REVIEWER_PROJECTION_ROOT
        ):
            raise ProjectionError("B3_LOCK_BUSY")


def _final_path(root: Path, filename: str) -> Path:
    if filename == _PRIVATE_FILE:
        return root / "private" / filename
    if filename in _REVIEWER_FILES:
        return root / "reviewer" / filename
    raise ProjectionError("B3_OUTPUT_PATH_INVALID")


def _inspect_tree_paths(
    root: Path, lock: _ProjectionLock | None = None
) -> tuple[Path, ...]:
    if not _directory_nonreparse(root):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    private = root / "private"
    reviewer = root / "reviewer"
    lock_path = root / "projection.lock"
    if (
        not _directory_nonreparse(private)
        or not _directory_nonreparse(reviewer)
        or not _regular_nonreparse(lock_path)
    ):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    try:
        if lock is None:
            lock_bytes = lock_path.read_bytes()
        else:
            lock.require_active()
            lock.handle.seek(0)
            lock_bytes = lock.handle.read(2)
        if lock_bytes != b"\x00":
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        top = list(root.iterdir())
    except OSError as exc:
        raise ProjectionError("B3_OUTPUT_PATH_INVALID") from exc
    if {path.name for path in top} != {"private", "reviewer", "projection.lock"}:
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    owned_temps: list[Path] = []
    for directory, kind, allowed in (
        (private, "private", {_PRIVATE_FILE}),
        (reviewer, "reviewer", set(_REVIEWER_FILES)),
    ):
        try:
            paths = list(directory.iterdir())
        except OSError as exc:
            raise ProjectionError("B3_OUTPUT_PATH_INVALID") from exc
        for path in paths:
            if _is_reparse(path) or not path.is_file():
                raise ProjectionError("B3_OUTPUT_PATH_INVALID")
            if path.name in allowed:
                continue
            if _owned_temp_target(path, kind) is None:
                raise ProjectionError("B3_OUTPUT_PATH_INVALID")
            owned_temps.append(path)
    return tuple(sorted(owned_temps, key=lambda item: str(item)))


def _read_existing_finals(
    root: Path,
) -> tuple[dict[str, bytes], dict[str, dict[str, Any]]]:
    raw: dict[str, bytes] = {}
    objects: dict[str, dict[str, Any]] = {}
    for filename in _PUBLICATION_ORDER:
        path = _final_path(root, filename)
        if not path.exists():
            continue
        if not _regular_nonreparse(path):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        try:
            contents = path.read_bytes()
        except OSError as exc:
            raise ProjectionError("B3_ARTIFACT_INVALID") from exc
        maximum = _PRIVATE_FILE_LIMIT if filename == _PRIVATE_FILE else _REVIEWER_FILE_LIMIT
        top_limit = 190 if filename == _PRIVATE_FILE else 256
        value = _load_canonical_json_bytes(
            contents, maximum=maximum, top_array_limit=top_limit
        )
        raw[filename] = contents
        objects[filename] = value
    return raw, objects


def _classify_existing_tree(
    root: Path,
    material: _ProjectionMaterial,
    lock: _ProjectionLock | None = None,
) -> str | None:
    try:
        _inspect_tree_paths(root, lock)
    except ProjectionError:
        return "B3_OUTPUT_PATH_INVALID"
    try:
        raw, objects = _read_existing_finals(root)
        for filename in _DATA_FILES:
            if filename in objects:
                _validate_data_artifact_shape(filename, objects[filename])
        if "manifest_v1.json" in objects:
            _validate_reviewer_manifest_shape(objects["manifest_v1.json"])
        if _PRIVATE_FILE in objects:
            _validate_private_manifest_shape(objects[_PRIVATE_FILE])
    except ProjectionError as exc:
        if exc.category == "B3_OUTPUT_PATH_INVALID":
            return "B3_OUTPUT_PATH_INVALID"
        return "B3_ARTIFACT_INVALID"
    try:
        for filename in _DATA_FILES:
            if filename in objects:
                _validate_data_artifact_identity(filename, objects[filename])
        if "manifest_v1.json" in objects:
            _validate_reviewer_manifest_identity(objects["manifest_v1.json"])
        if _PRIVATE_FILE in objects:
            _validate_private_manifest_identity(objects[_PRIVATE_FILE])
    except ProjectionError:
        return "B3_SCHEMA_VERSION_MISMATCH"
    try:
        _validate_hash_relationships(objects, raw)
    except ProjectionError:
        return "B3_HASH_MISMATCH"
    if any(
        raw[filename] != material.file_bytes[filename]
        for filename in _REVIEWER_FILES
        if filename in raw
    ):
        return "B3_OUTPUT_COLLISION"
    if (
        _PRIVATE_FILE in raw
        and raw[_PRIVATE_FILE] != material.file_bytes[_PRIVATE_FILE]
    ):
        return "B3_BLINDING_INCONSISTENT"
    return None


def _clean_owned_temps(root: Path, lock: _ProjectionLock) -> bool:
    lock.require_active()
    temps = _inspect_tree_paths(root, lock)
    for path in temps:
        try:
            path.unlink()
        except OSError as exc:
            raise ProjectionError("B3_IO_FAILURE") from exc
    return bool(temps)


def _move_file_create_only(source: Path, target: Path) -> None:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        function = kernel32.MoveFileExW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        function.restype = ctypes.c_int
    except (AttributeError, OSError) as exc:
        raise ProjectionError("B3_PLATFORM_UNSUPPORTED") from exc
    if not function(str(source), str(target), _MOVEFILE_WRITE_THROUGH):
        error = ctypes.get_last_error()
        if error in {80, 183}:
            raise FileExistsError(str(target))
        raise ProjectionError("B3_IO_FAILURE")


def _publish_final(
    root: Path,
    filename: str,
    expected: bytes,
    lock: _ProjectionLock,
) -> bool:
    lock.require_active()
    final = _final_path(root, filename)
    parent = final.parent
    if not _directory_nonreparse(parent):
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    if final.exists():
        if not _regular_nonreparse(final):
            raise ProjectionError("B3_OUTPUT_PATH_INVALID")
        try:
            return False if final.read_bytes() == expected else _raise_collision(filename)
        except OSError as exc:
            raise ProjectionError("B3_IO_FAILURE") from exc
    nonce = os.urandom(16).hex()
    temporary = parent / f".{filename}.{nonce}.tmp"
    if _owned_temp_target(
        temporary, "private" if filename == _PRIVATE_FILE else "reviewer"
    ) != filename:
        raise ProjectionError("B3_OUTPUT_PATH_INVALID")
    handle: Any = None
    try:
        handle = temporary.open("xb", buffering=0)
        written = handle.write(expected)
        if written != len(expected):
            raise ProjectionError("B3_IO_FAILURE")
        handle.flush()
        os.fsync(handle.fileno())
        handle.close()
        handle = None
    except ProjectionError:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        raise
    except (OSError, UnicodeError) as exc:
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        raise ProjectionError("B3_IO_FAILURE") from exc
    try:
        _move_file_create_only(temporary, final)
    except (FileExistsError, ProjectionError, OSError) as exc:
        try:
            if _regular_nonreparse(final) and final.read_bytes() == expected:
                if temporary.exists():
                    temporary.unlink()
                return True
        except (OSError, ProjectionError):
            pass
        if isinstance(exc, ProjectionError):
            raise
        raise ProjectionError("B3_IO_FAILURE") from exc
    try:
        if not _regular_nonreparse(final) or final.read_bytes() != expected:
            raise ProjectionError("B3_IO_FAILURE")
    except OSError as exc:
        raise ProjectionError("B3_IO_FAILURE") from exc
    return True


def _raise_collision(filename: str) -> bool:
    raise ProjectionError(
        "B3_BLINDING_INCONSISTENT"
        if filename == _PRIVATE_FILE
        else "B3_OUTPUT_COLLISION"
    )


def _publish_material(material: _ProjectionMaterial) -> ReviewerProjectionOutcome:
    root = _validate_projection_root_for_access()
    _ensure_projection_directories(root)
    with _ProjectionLock(root) as lock:
        category = _classify_existing_tree(root, material, lock)
        if category is not None:
            raise ProjectionError(category)
        initial_finals = {
            filename
            for filename in _PUBLICATION_ORDER
            if _final_path(root, filename).exists()
        }
        had_temps = bool(_inspect_tree_paths(root, lock))
        _clean_owned_temps(root, lock)
        if len(initial_finals) == 6:
            action = "already_complete"
        else:
            action = (
                "created"
                if not initial_finals and not had_temps
                else "resumed"
            )
            try:
                for filename in _PUBLICATION_ORDER:
                    _publish_final(
                        root, filename, material.file_bytes[filename], lock
                    )
            except ProjectionError:
                category = _classify_existing_tree(root, material, lock)
                if category is not None:
                    raise ProjectionError(category)
                raise
        category = _classify_existing_tree(root, material, lock)
        if category is not None:
            raise ProjectionError(category)
        if any(
            not _final_path(root, filename).exists()
            for filename in _PUBLICATION_ORDER
        ):
            raise ProjectionError("B3_IO_FAILURE")
        raw, objects = _read_existing_finals(root)
        if set(raw) != set(_PUBLICATION_ORDER):
            raise ProjectionError("B3_IO_FAILURE")
        _validate_hash_relationships(objects, raw)
        _validate_cross_artifact_consistency(objects)
        _validate_privacy_boundary(objects)
        return ReviewerProjectionOutcome(
            schema_version=1,
            action=action,
            reviewer_bundle_id=material.reviewer_bundle_id,
            source_unit_count=190,
            reviewer_artifact_count=5,
            reviewer_manifest_sha256=material.reviewer_manifest_sha256,
            projection_manifest_sha256=material.projection_manifest_sha256,
        )


def project_blinded_reviewer_outputs() -> ReviewerProjectionOutcome:
    """Project the complete eligible canonical run to the fixed B3 tree."""

    _validate_fixed_module_authorities_lexically()
    verify_frozen()
    plan = build_plan()
    validate_plan(plan)
    if (
        len(plan) != 190
        or plan_fingerprint(plan) != _PLAN_FINGERPRINT
        or [unit["execution_order"] for unit in plan] != list(range(1, 191))
    ):
        raise ProjectionError("B3_PRIVATE_STATE_INVALID")
    contract = _validate_authoritative_contract(
        dict(build_durable_run_contract(plan))
    )
    _apply_source_eligibility_gate(contract)
    results = observe_validated_canonical_private_results(plan)
    snapshot = _validate_snapshot(plan, contract, results)
    references = _load_reference_sources(plan)
    material = _build_projection_material(plan, contract, snapshot, references)
    return _publish_material(material)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project validated Stage B2 commits to blinded reviewer JSON."
    )
    parser.parse_args(argv)
    try:
        outcome = project_blinded_reviewer_outputs()
    except ProjectionError as exc:
        print(exc.category, file=sys.stderr)
        return 2
    except StoreError as exc:
        print(exc.category, file=sys.stderr)
        return 2
    except Blocked as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "schema_version": outcome.schema_version,
                "action": outcome.action,
                "reviewer_bundle_id": outcome.reviewer_bundle_id,
                "source_unit_count": outcome.source_unit_count,
                "reviewer_artifact_count": outcome.reviewer_artifact_count,
                "reviewer_manifest_sha256": outcome.reviewer_manifest_sha256,
                "projection_manifest_sha256": outcome.projection_manifest_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
