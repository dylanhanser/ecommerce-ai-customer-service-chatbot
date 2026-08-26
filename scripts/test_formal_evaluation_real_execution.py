"""Focused zero-network verification for Stage B5 guarded real execution."""
from __future__ import annotations

import copy
import builtins
import contextlib
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import formal_evaluation_orchestration as orchestration
import formal_evaluation_real_execution as real
import formal_evaluation_review_projection as projection
import formal_evaluation_store as store
import formal_evaluation_transport as transport
import run_formal_evaluation as runner


def _deny_network(*_args: Any, **_kwargs: Any) -> Any:
    raise AssertionError("NETWORK_FORBIDDEN")


@pytest.fixture(autouse=True)
def offline_synthetic_boundaries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    sensitive_markers = (
        "DEEPSEEK",
        "OPENAI",
        "API_KEY",
        "ACCESS_TOKEN",
        "AUTH_TOKEN",
        "BEARER",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    )
    for name in tuple(os.environ):
        if any(marker in name.upper() for marker in sensitive_markers):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(socket, "socket", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)
    protected_exact = (ROOT / "outputs" / ".env").resolve()
    protected_roots = tuple(
        path.resolve()
        for path in (
            ROOT / "outputs" / "cache",
            ROOT / "evaluation",
            ROOT / "data" / "external_eval",
            ROOT / "data" / "formal_eval" / "private_state",
            ROOT / "data" / "formal_eval" / "reviewer_projection",
            ROOT / "data" / "formal_eval" / "resource_preflight",
        )
    )

    def reject_protected(value: Any) -> None:
        if isinstance(value, int):
            return
        try:
            candidate = Path(os.fspath(value))
        except TypeError:
            return
        resolved = candidate.resolve()
        if resolved == protected_exact or any(
            resolved == protected or resolved.is_relative_to(protected)
            for protected in protected_roots
        ):
            raise AssertionError("PROTECTED_INPUT_ACCESS_FORBIDDEN")

    original_builtin_open = builtins.open
    original_path_open = Path.open

    def guarded_builtin_open(file, *args, **kwargs):
        reject_protected(file)
        return original_builtin_open(file, *args, **kwargs)

    def guarded_path_open(path, *args, **kwargs):
        reject_protected(path)
        return original_path_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_builtin_open)
    monkeypatch.setattr(Path, "open", guarded_path_open)
    short_root = Path(tempfile.mkdtemp(prefix="b5s-"))
    monkeypatch.setattr(store, "_PRIVATE_STATE_ROOT", short_root / "s")
    monkeypatch.setattr(projection, "_REVIEWER_PROJECTION_ROOT", short_root / "p")
    monkeypatch.setattr(real, "EVIDENCE_PATH", short_root / "missing_b4.json")
    try:
        yield
    finally:
        shutil.rmtree(short_root)


def _sha(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _synthetic_plan() -> list[dict[str, Any]]:
    generation = copy.deepcopy(runner.GENERATION)
    plan: list[dict[str, Any]] = []

    def add(rq: str, case: str, turn: int, system: str, user: str, history=None):
        payload = {
            "protocol_version": "1.0",
            "rq": rq,
            "system_config": system,
            "generation": generation,
            "user_input": user,
            "history": [] if history is None else history,
        }
        request_id = hashlib.sha256(
            f"stage-b5-test|{rq}|{case}|{turn}|{system}".encode()
        ).hexdigest()
        unit = {
            "request_id": request_id,
            "rq": rq,
            "case_id": case,
            "turn_index": turn,
            "system_config_id": system,
            "input_sha256": hashlib.sha256(user.encode()).hexdigest(),
            "payload": payload,
            "payload_sha256": _sha(payload),
            "frozen_test_file_sha256": hashlib.sha256(rq.encode()).hexdigest(),
        }
        if rq == "RQ1":
            unit["review_id"] = case
        plan.append(unit)

    for index in range(51):
        case = f"rq1_{index:02d}"
        add("RQ1", case, 1, "qa_only_reconstructed_baseline", f"marker {case} a")
        add("RQ1", case, 1, "v2", f"marker {case} b")
    for index in range(20):
        case = f"rq2_{index:02d}"
        add("RQ2", case, 1, "qa_only_reconstructed_baseline", f"marker {case} a")
        add("RQ2", case, 1, "v2", f"marker {case} b")
    for index in range(12):
        case = f"rq3_{index:02d}"
        first = f"marker {case} turn one"
        second = f"marker {case} turn two"
        add("RQ3", case, 1, "single_turn", first)
        add("RQ3", case, 2, "single_turn", second)
        add("RQ3", case, 1, "context_aware", first)
        add(
            "RQ3",
            case,
            2,
            "context_aware",
            second,
            [{"user_input": first, "assistant_answer": "__PRIOR_RESPONSE_BY_SAME_REQUEST_SEQUENCE__"}],
        )
    for order, unit in enumerate(plan, 1):
        unit["execution_order"] = order
    assert len(plan) == 190
    assert Counter(unit["rq"] for unit in plan) == {
        "RQ1": 102,
        "RQ2": 40,
        "RQ3": 48,
    }
    assert Counter(unit["system_config_id"] for unit in plan) == {
        "qa_only_reconstructed_baseline": 71,
        "v2": 71,
        "single_turn": 24,
        "context_aware": 24,
    }
    return plan


def _production_resource_mapping(config: str) -> dict[str, Any]:
    identity = transport.formal_identity(config)
    family = identity.resource_family
    v2 = family == "v2_mixed"
    version = "production_v2_mixed" if v2 else "production_v1_qa_only"
    corpus_name = "mixed_corpus_v2.pkl" if v2 else "qa_corpus.pkl"
    embeddings_name = "mixed_embeddings_v2.npy" if v2 else "qa_embeddings.npy"
    return {
        "schema_version": 1,
        "resource_type": "production_frozen",
        "logical_resource_id": f"production_frozen_{family}_{version}",
        "system_config_id": config,
        "formal_system_id": identity.formal_system_id,
        "corpus_path": f"outputs/cache/{family}/{corpus_name}",
        "embeddings_path": f"outputs/cache/{family}/{embeddings_name}",
        "corpus_sha256": ("1" if v2 else "2") * 64,
        "embeddings_sha256": ("3" if v2 else "4") * 64,
        "cache_family": family,
        "corpus_version": version,
        "row_count": 15688 if v2 else 15333,
        "qa_count": 15333,
        "snippet_count": 355 if v2 else 0,
        "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "embedding_rows": 15688 if v2 else 15333,
        "embedding_dimensions": 384,
        "synthetic": False,
    }


def _evidence(
    *, preflight_sha: str = "a" * 64, authority_sha: str = "b" * 64
) -> real.ValidatedB4Evidence:
    wrappers: dict[str, dict[str, Any]] = {}
    for config in real._SYSTEM_CONFIG_IDS:
        mapping = _production_resource_mapping(config)
        resource = transport.ProductionResourceIdentity.from_mapping(mapping)
        wrappers[config] = {
            "resource_identity": mapping,
            "resource_identity_sha256": transport.resource_identity_sha256(resource),
        }
    artifact = {
        "authority_files": [
            {"byte_count": 7, "path": "synthetic/authority.py", "sha256": authority_sha}
        ],
        "contract_id": "formal_production_resource_preflight_v1",
        "embedding_model": {
            "revision": "1" * 40,
            "snapshot_file_count": 1,
            "snapshot_sha256": "5" * 64,
            "snapshot_total_bytes": 7,
        },
        "preflight_sha256": preflight_sha,
        "resource_families": [
            {"cache_family": "v1_qa"},
            {"cache_family": "v2_mixed"},
        ],
        "resource_identities": [copy.deepcopy(wrappers[name]) for name in real._SYSTEM_CONFIG_IDS],
        "schema_version": 1,
        "stage_id": "B4",
        "status": "passed",
    }
    raw = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    return real.ValidatedB4Evidence(
        artifact,
        hashlib.sha256(raw).hexdigest(),
        preflight_sha,
        wrappers,
    )


def _base_contract() -> dict[str, Any]:
    systems = {}
    for config in real._SYSTEM_CONFIG_IDS:
        identity = transport.formal_identity(config)
        systems[config] = {
            "formal_system_id": identity.formal_system_id,
            "resolved_runtime_system_id": identity.resolved_runtime_system_id,
            "resource_family": identity.resource_family,
            "top_k": identity.top_k,
            "uses_context": identity.uses_context,
            "uses_checkpoint": identity.uses_checkpoint,
        }
    value = {
        "schema_version": 1,
        "stage_id": "B2",
        "plan_authority": {
            "plan_fingerprint": real.PLAN_FINGERPRINT,
            "base_seed": 20260721,
            "execution_unit_count": 190,
            "unique_request_id_count": 190,
            "execution_order_first": 1,
            "execution_order_last": 190,
            "rq_counts": {"RQ1": 102, "RQ2": 40, "RQ3": 48},
            "system_counts": {
                "context_aware": 24,
                "qa_only_reconstructed_baseline": 71,
                "single_turn": 24,
                "v2": 71,
            },
        },
        "frozen_input_sha256": {"synthetic_authority": "6" * 64},
        "formal_system_authority": systems,
        "provider_generation_authority": {
            "generation": {
                "contract_id": transport.generation_contract_id(),
                "contract_sha256": transport.generation_contract_sha256(),
                "runner_generation_sha256": runner.generation_sha(),
                "snapshot": dict(transport.fixed_generation_snapshot()),
            },
            "transport": {
                "contract_id": transport.transport_contract_id(),
                "contract_sha256": transport.transport_contract_sha256(),
                "snapshot": dict(transport.transport_contract_snapshot()),
            },
            "offline_execution": {
                "authority_bundle_id": "synthetic",
                "clock_id": "synthetic",
                "executor_registry_id": "synthetic",
                "fake_raw_client_id": "synthetic",
                "mode": "offline_fake_only",
                "snapshot_validator_id": "synthetic",
                "test_fault_controller_id": "synthetic",
            },
        },
        "runtime_resource_authority": {
            "transport_implementation_sha256": "7" * 64,
            "runtime_identity_sha256": "8" * 64,
            "resources": {},
        },
        "schema_authority": {
            "attempt_archive_schema_version": 1,
            "b1_checkpoint_evidence_schema_version": 1,
            "formal_result_schema_version": 1,
            "journal_wrapper_schema_version": 1,
            "private_commit_envelope_schema_version": 1,
            "run_contract_schema_version": 1,
            "stage_a_authoritative_success_schema_version": 1,
            "stage_a_inflight_journal_schema_version": 3,
            "stage_a_resource_identity_schema_version": 1,
        },
    }
    value["run_contract_sha256"] = "9" * 64
    return value


def _metadata() -> dict[str, Any]:
    return {
        "base_url": "https://api.deepseek.com",
        "max_retries": 0,
        "model": "deepseek-chat",
        "sdk_distribution": "openai",
        "sdk_version": "synthetic-1.0",
        "timeout_seconds": 60.0,
    }


def _real_contract(plan: list[dict[str, Any]], evidence=None) -> dict[str, Any]:
    return real.build_real_run_contract(
        plan,
        evidence or _evidence(),
        real.RepositoryIdentity("main", "1" * 40),
        _metadata(),
        _base_contract=_base_contract(),
    )


def _patch_synthetic_plan_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "verify_frozen", lambda: {})
    monkeypatch.setattr(runner, "frozen_hashes", lambda: dict(runner.FROZEN))
    monkeypatch.setattr(runner, "validate_plan", lambda _plan: None)
    monkeypatch.setattr(runner, "plan_fingerprint", lambda _plan: real.PLAN_FINGERPRINT)
    monkeypatch.setattr(
        runner, "_plan_fingerprint_bytes", lambda _plan: real.PLAN_FINGERPRINT
    )


def _prefix_state(plan: list[dict[str, Any]], prefix: int, *, action="ready", new=0, block=None):
    rq = {"RQ1": 0, "RQ2": 0, "RQ3": 0}
    systems = {name: 0 for name in real._SYSTEM_CONFIG_IDS}
    for unit in plan[:prefix]:
        rq[unit["rq"]] += 1
        systems[unit["system_config_id"]] += 1
    remaining = 190 - prefix
    progress = store.DurableProgress(
        schema_version=1,
        run_state="complete" if prefix == 190 else "in_progress",
        total_successful_units=prefix,
        successful_by_rq=rq,
        successful_by_system=systems,
        remaining_units=remaining,
        next_eligible_execution_order=None if prefix == 190 else prefix + 1,
        initial_executable_units=remaining,
        same_attempt_continuable_units=0,
        retry_constructible_units=0,
        dependency_blocked_units=0,
        permanently_non_executable_units=0,
    )
    if prefix == 190:
        action = "run_complete"
    return store.DurablePrefixOutcome(1, action, new, block, progress)


class _Clock:
    def __init__(self):
        self.value = datetime(2026, 7, 23, 10, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> str:
        self.value += timedelta(seconds=1)
        return self.value.isoformat(timespec="seconds").replace("+00:00", "Z")


def test_real_clock_is_whole_second_monotonic_and_journal_compatible(monkeypatch):
    fixed = datetime(2026, 8, 25, 12, 34, 56, 987654, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc
            return fixed

    monkeypatch.setattr(real, "datetime", FrozenDatetime)
    clock = real._MonotonicUTCClockV1()
    observed = [clock() for _ in range(3)]
    assert observed == [
        "2026-08-25T12:34:56Z",
        "2026-08-25T12:34:57Z",
        "2026-08-25T12:34:58Z",
    ]
    assert all(len(value) == 20 and "." not in value for value in observed)
    assert observed == sorted(set(observed))

    unit = _synthetic_plan()[0]
    resource = transport.ProductionResourceIdentity.from_mapping(
        _production_resource_mapping(unit["system_config_id"])
    )
    identity = orchestration._build_identity(
        unit=unit,
        resource=resource,
        resolved_payload_sha256=unit["payload_sha256"],
        attempt_number=1,
        checkpoint=None,
    )
    journal = orchestration.create_initial_journal(identity, observed[0])
    assert journal.prepared_at == observed[0]
    assert journal.updated_at == observed[0]


@pytest.mark.skipif(os.name != "nt", reason="Windows extended paths only")
def test_windows_long_atomic_archive_round_trip_and_cleanup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    import winreg

    with winreg.OpenKey(
        winreg.HKEY_LOCAL_MACHINE,
        r"SYSTEM\CurrentControlSet\Control\FileSystem",
    ) as key:
        long_paths_enabled, _kind = winreg.QueryValueEx(key, "LongPathsEnabled")
    assert long_paths_enabled == 0

    root = tmp_path.joinpath(
        *(f"long-path-segment-{index:02d}-" + "x" * 28 for index in range(7)),
        "state",
    )
    execution_unit_id = "a" * 64
    archive_directory = root / "attempts" / execution_unit_id
    target = archive_directory / f"1-1-{'b' * 64}.json"
    failed_target = archive_directory / f"1-2-{'c' * 64}.json"
    assert len(str(target)) > 300
    extended_target = os.fspath(store._os_io_path(target))
    assert extended_target.startswith("\\\\?\\")
    assert store._os_io_path(Path(extended_target)) == extended_target
    unc = Path(r"\\server\share") / ("u" * 125) / ("v" * 125)
    assert store._os_io_path(unc) == "\\\\?\\UNC\\" + str(unc)[2:]

    logical_member = target.relative_to(root).as_posix()
    initial = {"durable_member": logical_member, "generation": 1}
    replacement = {"durable_member": logical_member, "generation": 2}
    failure = {
        "durable_member": failed_target.relative_to(root).as_posix(),
        "generation": 3,
    }
    try:
        monkeypatch.setattr(store, "_PRIVATE_STATE_ROOT", root)
        with store._RunWideLock(root) as lock:
            store._ensure_fixed_directories(root)
            store._path_mkdir(archive_directory)
            assert store._atomic_publish_json(
                target,
                initial,
                replace=False,
                maximum=store._ARCHIVE_LIMIT,
            )
            assert store._read_json(target, store._ARCHIVE_LIMIT) == initial
            assert store._atomic_publish_json(
                target,
                replacement,
                replace=True,
                maximum=store._ARCHIVE_LIMIT,
            )
            assert store._read_json(target, store._ARCHIVE_LIMIT) == replacement
            raw = store._path_read_bytes(target)
            assert b"\\\\?\\" not in raw
            assert "\\\\?\\" not in logical_member
            assert target.name == f"1-1-{'b' * 64}.json"

            with monkeypatch.context() as publication_failure:
                publication_failure.setattr(
                    store,
                    "_move_file_ex",
                    lambda *_args: (_ for _ in ()).throw(
                        store.StoreError("STORE_IO_FAILURE")
                    ),
                )
                with pytest.raises(store.StoreError, match="STORE_IO_FAILURE"):
                    store._atomic_publish_json(
                        failed_target,
                        failure,
                        replace=False,
                        maximum=store._ARCHIVE_LIMIT,
                    )
            owned_temps = [
                path
                for path in store._path_iterdir(archive_directory)
                if path.name.startswith(".")
            ]
            assert len(owned_temps) == 1
            store._clean_owned_temps_locked(root, lock)
            assert not any(
                path.name.startswith(".")
                for path in store._path_iterdir(archive_directory)
            )
            store._path_unlink(target)
            assert not store._path_exists(target)
    finally:
        io_root = store._os_io_path(root)
        if os.path.exists(io_root):
            shutil.rmtree(io_root)


class _LocalAuthority:
    def __init__(
        self,
        evidence: real.ValidatedB4Evidence,
        contract: Mapping[str, Any],
    ):
        mappings = {
            name: dict(evidence.resource_wrappers[name]["resource_identity"])
            for name in real._SYSTEM_CONFIG_IDS
        }
        self.resources = orchestration.ProductionResourceBundle.from_mappings(mappings)
        self.clock = _Clock()
        self.orders: list[int] = []
        self.resumed_turn_two_orders: list[int] = []
        runtime = contract["runtime_resource_authority"]
        self.transport_sha256 = runtime["transport_implementation_sha256"]
        self.runtime_sha256 = runtime["runtime_identity_sha256"]

    def clock_for(self, _unit: Mapping[str, Any], _state: Any) -> _Clock:
        return self.clock

    def dependencies_for(self, unit: Mapping[str, Any], _state: Any) -> dict[str, Any]:
        def execute(context):
            self.orders.append(context.unit["execution_order"])
            if (
                context.unit["rq"] == "RQ3"
                and context.unit["system_config_id"] == "context_aware"
                and context.unit["turn_index"] == 2
            ):
                assert context.checkpoint_snapshot is not None
                restored = real.ProductionRealAuthorityV1._snapshot_validator(
                    context.checkpoint_snapshot
                )
                assert restored.to_dict() == context.checkpoint_snapshot
                self.resumed_turn_two_orders.append(
                    context.unit["execution_order"]
                )
            response = "STAGE_B2_SYNTHETIC_LOCAL " + context.unit["request_id"][:24]
            result = {
                "response_text": response,
                "route": "local_guard",
                "guard_category": "stage_b5_test",
                "requires_backend_api": False,
                "retrieval_used": False,
                "retrieved_document_ids": [],
                "retrieved_scores": [],
            }
            if (
                context.unit["rq"] == "RQ3"
                and context.unit["system_config_id"] == "context_aware"
                and context.unit["turn_index"] == 1
            ):
                result["runtime_snapshot"] = runner._fixed_synthetic_snapshot(
                    context.unit, response
                )
            return result

        return {
            "resources": self.resources,
            "executors": orchestration.ExecutorRegistry(
                {name: execute for name in real._SYSTEM_CONFIG_IDS}
            ),
            "fake_raw_client": object(),
            "clock": self.clock,
            "transport_implementation_sha256": self.transport_sha256,
            "runtime_identity_sha256": self.runtime_sha256,
            "snapshot_validator": real.ProductionRealAuthorityV1._snapshot_validator,
        }


class _ProviderAuthority(_LocalAuthority):
    def __init__(self, evidence, contract, completions):
        super().__init__(evidence, contract)
        self.raw = real._SDKRawCompletionsAdapterV1(completions)

    def dependencies_for(self, unit: Mapping[str, Any], _state: Any) -> dict[str, Any]:
        def execute(context):
            self.orders.append(context.unit["execution_order"])
            normalized = context.invoke_provider(
                [{"role": "user", "content": context.unit["payload"]["user_input"]}]
            )
            return {
                "response_text": normalized.content,
                "route": "provider",
                "guard_category": "stage_b5_test",
                "requires_backend_api": False,
                "retrieval_used": True,
                "retrieved_document_ids": ["synthetic_doc"],
                "retrieved_scores": [0.5],
            }

        return {
            "resources": self.resources,
            "executors": orchestration.ExecutorRegistry(
                {name: execute for name in real._SYSTEM_CONFIG_IDS}
            ),
            "fake_raw_client": self.raw,
            "clock": self.clock,
            "transport_implementation_sha256": self.transport_sha256,
            "runtime_identity_sha256": self.runtime_sha256,
            "snapshot_validator": runner._validate_fixed_synthetic_snapshot_v1,
        }


class _SuccessCompletions:
    def __init__(self, content: str | None = None):
        self.content = content
        self.calls = 0
        self.requests: list[dict[str, Any]] = []

    def create(self, **request):
        self.calls += 1
        self.requests.append(copy.deepcopy(request))
        return SimpleNamespace(
            id=f"synthetic_response_{self.calls}",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=self.content or f"provider answer {self.calls}"
                    )
                )
            ],
        )


class _RetryableFailure(RuntimeError):
    status_code = 500


class _TerminalFailure(RuntimeError):
    status_code = 400
    category = "invalid_request"


class _RetryCompletions:
    def __init__(self, failure: BaseException):
        self.failure = failure
        self.calls = 0

    def create(self, **_request):
        self.calls += 1
        raise self.failure


class _InvalidResponseCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **_request):
        self.calls += 1
        return SimpleNamespace(id="synthetic_invalid_response", choices=[])


def _tracked_multiline_rag_messages() -> list[dict[str, str]]:
    import formal_evaluation_runtime as runtime

    row = {
        "source_type": "chat_qa",
        "category": "synthetic",
        "title": "Synthetic source title",
        "question": "Synthetic source question",
        "answer_or_content": "Synthetic context answer",
        "needs_backend_api": False,
        "allowed_for_answer": True,
    }
    prompt = runtime.rag.build_rag_prompt(
        "Synthetic provider-eligible question",
        [
            (
                row,
                0.9,
                {
                    "rerank_score": 0.95,
                    "rerank_reason": "synthetic_test",
                },
            )
        ],
    )
    assert "\n\n" in prompt
    return [
        {"role": "system", "content": "Synthetic formal RAG system"},
        {"role": "user", "content": prompt},
    ]


def _synthetic_loaded_resources() -> real.LoadedProductionResources:
    import numpy as np
    import pandas as pd

    corpus = pd.DataFrame(
        [
            {
                "doc_id": "synthetic_doc",
                "source_type": "chat_qa",
                "category": "synthetic",
                "title": "Synthetic product information",
                "text_for_embedding": "Synthetic product color information",
                "answer_or_content": "Synthetic context answer",
                "question": "Synthetic source question",
                "answer": "Synthetic context answer",
                "priority": 100,
                "allowed_for_answer": True,
                "needs_backend_api": False,
                "source_file": "synthetic",
                "session_id": "",
            }
        ]
    )
    embeddings = np.asarray([[1.0]], dtype=np.float32)

    class EmbeddingModel:
        @staticmethod
        def encode(*_args, **_kwargs):
            return np.asarray([[1.0]], dtype=np.float32)

    def cosine_similarity(_query, _embeddings):
        return np.asarray([[0.99]], dtype=np.float32)

    return real.LoadedProductionResources(
        {"v1_qa": (corpus, embeddings), "v2_mixed": (corpus, embeddings)},
        EmbeddingModel(),
        cosine_similarity,
    )


class _CoreGatewayAuthority(_LocalAuthority):
    def __init__(
        self,
        evidence: real.ValidatedB4Evidence,
        contract: Mapping[str, Any],
        completions: Any,
        messages: list[dict[str, str]],
        *,
        behavior: str = "provider",
        fallback_query_type: str = "normal",
    ):
        super().__init__(evidence, contract)
        self.raw = real._SDKRawCompletionsAdapterV1(completions)
        self.messages = copy.deepcopy(messages)
        self.behavior = behavior
        self.fallback_query_type = fallback_query_type

    def dependencies_for(self, unit: Mapping[str, Any], _state: Any) -> dict[str, Any]:
        def execute(context):
            self.orders.append(context.unit["execution_order"])
            gateway = real._CoreCompletionsGatewayV1(context)
            if self.behavior == "local_guard":
                answer = "synthetic deterministic local guard"
                requires_backend = False
                skip_llm = True
            elif self.behavior == "backend_boundary":
                answer = "synthetic deterministic backend boundary"
                requires_backend = True
                skip_llm = False
            else:
                answer = "synthetic mock fallback"
                requires_backend = False
                skip_llm = False
                try:
                    response = gateway.create(
                        messages=copy.deepcopy(self.messages),
                        **dict(transport.fixed_generation_snapshot()),
                    )
                    answer = response.choices[0].message.content
                except Exception:
                    # Mirrors the tracked RAG cores' catch-and-fallback behavior.
                    if self.fallback_query_type == "product_attribute":
                        answer = "synthetic product-attribute fallback"
            return real._project_v2_core_result(
                {
                    "final_answer": answer,
                    "reranked_results": [],
                    "requires_backend_api": requires_backend,
                    "skip_llm": skip_llm,
                    "skip_retrieval": self.behavior == "local_guard",
                    "query_type": self.fallback_query_type,
                },
                gateway,
                runtime_snapshot=None,
            )

        return {
            "resources": self.resources,
            "executors": orchestration.ExecutorRegistry(
                {name: execute for name in real._SYSTEM_CONFIG_IDS}
            ),
            "fake_raw_client": self.raw,
            "clock": self.clock,
            "transport_implementation_sha256": self.transport_sha256,
            "runtime_identity_sha256": self.runtime_sha256,
            "snapshot_validator": runner._validate_fixed_synthetic_snapshot_v1,
        }


def test_multiline_rag_provider_unit_commits_as_provider_backed(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    eligible_question = "这个商品是什么颜色"
    plan[0]["payload"]["user_input"] = eligible_question
    plan[0]["input_sha256"] = hashlib.sha256(eligible_question.encode()).hexdigest()
    plan[0]["payload_sha256"] = _sha(plan[0]["payload"])
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    completions = _SuccessCompletions("这是合成的提供方回答。")
    authority = real.ProductionRealAuthorityV1(
        evidence,
        _synthetic_loaded_resources(),
        real._SDKRawCompletionsAdapterV1(completions),
        contract,
    )
    outcome = store._orchestrate_durable_offline_unit(
        plan,
        plan[0],
        expected_contract=contract,
        authority=authority,
    )

    assert outcome.action == "completed"
    assert outcome.private_commit_sha256 is not None
    assert outcome.provider_call_count == 1
    assert outcome.progress.total_successful_units == 1
    assert completions.calls == 1
    messages = completions.requests[0]["messages"]
    assert "\n\n" in messages[1]["content"]
    assert [dict(message) for message in transport.validate_messages(messages)] == messages
    executed = outcome.orchestration_outcome
    assert executed is not None
    assert executed.action == "success"
    assert executed.tracker_state == "validated_success"
    assert executed.authoritative_success is not None
    assert executed.formal_result is not None
    assert executed.formal_result["status"] == "success"
    assert executed.formal_result["provider_called"] is True
    assert executed.formal_result["route"] == "provider"
    assert executed.formal_result["response_text"] == "这是合成的提供方回答。"
    observed = store._observe_validated_canonical_private_results(plan, contract)
    assert len(observed) == 1
    assert observed[0].response_text == "这是合成的提供方回答。"


@pytest.mark.parametrize("fallback_query_type", ["normal", "product_attribute"])
def test_pre_provider_request_failure_cannot_commit_caught_fallback(
    monkeypatch: pytest.MonkeyPatch,
    fallback_query_type: str,
):
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    messages = _tracked_multiline_rag_messages()
    messages[1]["content"] += "\x00"
    completions = _SuccessCompletions()
    authority = _CoreGatewayAuthority(
        evidence,
        contract,
        completions,
        messages,
        fallback_query_type=fallback_query_type,
    )

    with pytest.raises(orchestration.OrchestrationError) as raised:
        store._orchestrate_durable_offline_unit(
            plan,
            plan[0],
            expected_contract=contract,
            authority=authority,
        )
    assert raised.value.category == "FIXED_REQUEST_INVALID"
    assert completions.calls == 0
    assert store._real_prefix_progress(plan, contract).progress.total_successful_units == 0
    assert store._observe_validated_canonical_private_results(plan, contract) == ()


def test_guarded_real_execution_exposes_stable_pre_provider_failure_category():
    plan = _synthetic_plan()
    evidence = _evidence()
    state = _prefix_state(plan, 0)

    def reject_fixed_request(*_args, **_kwargs):
        raise orchestration.OrchestrationError("FIXED_REQUEST_INVALID")

    with pytest.raises(real.RealExecutionError) as raised:
        real.execute_guarded_real_prefix(
            plan,
            confirmation=real.CONFIRMATION_TOKEN,
            expected_b4_preflight_sha256=evidence.preflight_sha256,
            max_new_successes=1,
            output_path=real.DRY_RUN_OUTPUT_PATH,
            repository_gate=lambda: real.RepositoryIdentity("main", "1" * 40),
            plan_validator=lambda _plan: None,
            evidence_consumer=lambda _sha: evidence,
            metadata_loader=_metadata,
            contract_builder=lambda *_args: {},
            progress_reader=lambda *_args: state,
            resource_loader=lambda _evidence: object(),
            config_parser=lambda _path: object(),
            client_factory=lambda _config: object(),
            authority_factory=lambda *_args: object(),
            prefix_executor=reject_fixed_request,
        )
    assert raised.value.category == "B5_PRE_PROVIDER_REQUEST_INVALID"


@pytest.mark.parametrize("provider_outcome", ["exception", "invalid_response"])
def test_provider_failure_cannot_commit_caught_mock_as_local_success(
    monkeypatch: pytest.MonkeyPatch,
    provider_outcome: str,
):
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    completions = (
        _RetryCompletions(_TerminalFailure())
        if provider_outcome == "exception"
        else _InvalidResponseCompletions()
    )
    authority = _CoreGatewayAuthority(
        evidence,
        contract,
        completions,
        _tracked_multiline_rag_messages(),
    )

    outcome = store._orchestrate_durable_offline_unit(
        plan,
        plan[0],
        expected_contract=contract,
        authority=authority,
    )
    assert outcome.action == "permanently_non_executable"
    assert outcome.block_category == "terminal_failed"
    assert outcome.private_commit_sha256 is None
    assert outcome.progress.total_successful_units == 0
    assert completions.calls == 1
    assert store._observe_validated_canonical_private_results(plan, contract) == ()


@pytest.mark.parametrize(
    ("behavior", "expected_route"),
    [("local_guard", "local_guard"), ("backend_boundary", "backend_boundary")],
)
def test_genuine_local_guard_and_backend_boundary_commit_without_provider(
    monkeypatch: pytest.MonkeyPatch,
    behavior: str,
    expected_route: str,
):
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    completions = _SuccessCompletions()
    authority = _CoreGatewayAuthority(
        evidence,
        contract,
        completions,
        _tracked_multiline_rag_messages(),
        behavior=behavior,
    )

    outcome = store._orchestrate_durable_offline_unit(
        plan,
        plan[0],
        expected_contract=contract,
        authority=authority,
    )
    assert outcome.action == "completed"
    assert outcome.private_commit_sha256 is not None
    assert outcome.provider_call_count == 0
    assert completions.calls == 0
    executed = outcome.orchestration_outcome
    assert executed is not None
    assert executed.action == "local_success"
    assert executed.formal_result is not None
    assert executed.formal_result["status"] == "local_success"
    assert executed.formal_result["provider_called"] is False
    assert executed.formal_result["route"] == expected_route
    assert len(store._observe_validated_canonical_private_results(plan, contract)) == 1


def test_import_help_and_dry_run_compatibility_are_offline(monkeypatch, capsys, tmp_path):
    assert real.CONFIG_PATH == "outputs/.env"
    with pytest.raises(SystemExit) as help_exit:
        runner.main(["--help"])
    assert help_exit.value.code == 0
    assert "--expected-b4-preflight-sha256" in capsys.readouterr().out
    manifest = {
        "invocation_new_successes": 1,
        "total_locked_successes": 1,
        "remaining_units": 189,
    }
    monkeypatch.setattr(runner, "prepare", lambda *_args, **_kwargs: manifest)
    assert runner.main(["--mode", "dry-run", "--output", str(tmp_path)]) == 0
    output = capsys.readouterr()
    assert "no API or model execution" in output.out
    assert output.err == ""
    mappings = {
        name: runner._fixed_resource_mapping(name) for name in real._SYSTEM_CONFIG_IDS
    }
    bundle = orchestration.SyntheticResourceBundle.from_mappings(mappings)
    assert all(bundle.resource_for(name).synthetic for name in real._SYSTEM_CONFIG_IDS)


def test_offline_fake_contract_bytes_and_authority_remain_stable(monkeypatch):
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    before = runner.build_durable_run_contract(plan)
    before_bytes = json.dumps(
        before, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    evidence = _evidence()
    real.build_real_run_contract(
        plan,
        evidence,
        real.RepositoryIdentity("main", "1" * 40),
        _metadata(),
        _base_contract=before,
    )
    after = runner.build_durable_run_contract(plan)
    after_bytes = json.dumps(
        after, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    assert before_bytes == after_bytes
    assert after["stage_id"] == "B2"
    assert (
        after["provider_generation_authority"]["offline_execution"]["mode"]
        == "offline_fake_only"
    )
    authority = runner._fixed_offline_authority()
    dependencies = authority.dependencies_for(
        plan[0], SimpleNamespace(archives=())
    )
    outcome = runner.orchestrate_offline_unit(plan, plan[0], **dependencies)
    assert outcome.action in {"success", "local_success"}
    assert outcome.identity.request_id == plan[0]["request_id"]


def test_production_bundle_accepts_only_complete_non_synthetic_authority():
    mappings = {
        name: _production_resource_mapping(name) for name in real._SYSTEM_CONFIG_IDS
    }
    bundle = orchestration.ProductionResourceBundle.from_mappings(mappings)
    assert all(not bundle.resource_for(name).synthetic for name in real._SYSTEM_CONFIG_IDS)
    bad = copy.deepcopy(mappings)
    bad["v2"] = runner._fixed_resource_mapping("v2")
    with pytest.raises(orchestration.OrchestrationError):
        orchestration.ProductionResourceBundle.from_mappings(bad)
    missing = dict(mappings)
    del missing["context_aware"]
    with pytest.raises(orchestration.OrchestrationError):
        orchestration.ProductionResourceBundle.from_mappings(missing)


class _PreflightDouble:
    def __init__(self, artifact, raw, authorities):
        self.artifact = artifact
        self.raw = raw
        self.authorities = authorities
        self.read_count = 0

    @staticmethod
    def _transport_authority():
        return transport

    def _read_existing_artifact(self, _path, _transport):
        self.read_count += 1
        return self.raw, copy.deepcopy(self.artifact)

    def _authority_observations_from_root(self, _root):
        return tuple(self.authorities)


def test_b4_evidence_hash_freshness_and_non_synthetic_validation(tmp_path):
    evidence = _evidence()
    artifact = copy.deepcopy(dict(evidence.artifact))
    raw = json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    observations = [
        SimpleNamespace(relative_path=item["path"], byte_count=item["byte_count"], sha256=item["sha256"])
        for item in artifact["authority_files"]
    ]
    double = _PreflightDouble(artifact, raw, observations)
    validated = real.consume_b4_evidence(
        evidence.preflight_sha256,
        repository_root=tmp_path,
        _evidence_path=tmp_path / "evidence.json",
        _preflight_module=double,
    )
    assert double.read_count == 1
    assert validated.artifact_sha256 == hashlib.sha256(raw).hexdigest()
    with pytest.raises(real.RealExecutionError, match="B5_PREFLIGHT_INVALID"):
        real.consume_b4_evidence(
            "f" * 64,
            repository_root=tmp_path,
            _evidence_path=tmp_path / "evidence.json",
            _preflight_module=double,
        )
    stale = _PreflightDouble(
        artifact,
        raw,
        [SimpleNamespace(relative_path="synthetic/authority.py", byte_count=8, sha256="b" * 64)],
    )
    with pytest.raises(real.RealExecutionError, match="B5_PREFLIGHT_INVALID"):
        real.consume_b4_evidence(
            evidence.preflight_sha256,
            repository_root=tmp_path,
            _evidence_path=tmp_path / "evidence.json",
            _preflight_module=stale,
        )
    malformed = _PreflightDouble({}, b"{}\n", [])
    with pytest.raises(real.RealExecutionError, match="B5_PREFLIGHT_INVALID"):
        real.consume_b4_evidence(
            evidence.preflight_sha256,
            repository_root=tmp_path,
            _evidence_path=tmp_path / "evidence.json",
            _preflight_module=malformed,
        )
    missing = _PreflightDouble(artifact, raw, observations)
    missing._read_existing_artifact = lambda *_args: (_ for _ in ()).throw(
        FileNotFoundError("synthetic missing evidence")
    )
    with pytest.raises(real.RealExecutionError, match="B5_PREFLIGHT_INVALID"):
        real.consume_b4_evidence(
            evidence.preflight_sha256,
            repository_root=tmp_path,
            _evidence_path=tmp_path / "evidence.json",
            _preflight_module=missing,
        )
    for mutation in ("synthetic", "resource_hash"):
        changed = copy.deepcopy(artifact)
        if mutation == "synthetic":
            changed["resource_identities"][0]["resource_identity"]["synthetic"] = True
        else:
            changed["resource_identities"][0]["resource_identity_sha256"] = "f" * 64
        changed_raw = (
            json.dumps(changed, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
        )
        changed_double = _PreflightDouble(changed, changed_raw, observations)
        with pytest.raises(real.RealExecutionError, match="B5_PREFLIGHT_INVALID"):
            real.consume_b4_evidence(
                evidence.preflight_sha256,
                repository_root=tmp_path,
                _evidence_path=tmp_path / "evidence.json",
                _preflight_module=changed_double,
            )


def test_synthetic_resource_loader_rechecks_identity_and_never_mutates_inputs(
    tmp_path: Path,
):
    base = _evidence()
    artifact = copy.deepcopy(dict(base.artifact))
    observations: dict[str, SimpleNamespace] = {}
    families = []
    for index, family in enumerate(("v1_qa", "v2_mixed"), 1):
        rows = 2 + index
        corpus_path = f"synthetic/{family}/corpus.pkl"
        embeddings_path = f"synthetic/{family}/embeddings.npy"
        corpus_sha = str(index) * 64
        embeddings_sha = str(index + 2) * 64
        observations[corpus_path] = SimpleNamespace(
            byte_count=10 + index, sha256=corpus_sha
        )
        observations[embeddings_path] = SimpleNamespace(
            byte_count=20 + index, sha256=embeddings_sha
        )
        families.append(
            {
                "cache_family": family,
                "corpus": {
                    "byte_count": 10 + index,
                    "path": corpus_path,
                    "sha256": corpus_sha,
                },
                "corpus_metadata": {
                    "columns": ["synthetic_marker"],
                    "row_count": rows,
                },
                "embeddings": {
                    "byte_count": 20 + index,
                    "path": embeddings_path,
                    "rows": rows,
                    "sha256": embeddings_sha,
                },
            }
        )
    artifact["resource_families"] = families
    evidence = real.ValidatedB4Evidence(
        artifact,
        base.artifact_sha256,
        base.preflight_sha256,
        base.resource_wrappers,
    )
    before_artifact = _sha(dict(evidence.artifact))
    before_wrappers = _sha(
        {name: dict(value) for name, value in evidence.resource_wrappers.items()}
    )
    paths = SimpleNamespace(
        v1_corpus=tmp_path / "v1.pkl",
        v1_embeddings=tmp_path / "v1.npy",
        v2_corpus=tmp_path / "v2.pkl",
        v2_embeddings=tmp_path / "v2.npy",
    )
    model_observation = SimpleNamespace(
        revision="1" * 40,
        file_count=1,
        total_bytes=7,
        snapshot_sha256="5" * 64,
        snapshot_path=tmp_path / "synthetic-model",
    )

    class FakePreflight:
        @staticmethod
        def _hash_regular_file(_path, _root, expected_path):
            return copy.deepcopy(observations[expected_path])

        @staticmethod
        def _hash_model_snapshot(_paths):
            return copy.deepcopy(model_observation)

    class FakeFrame:
        def __init__(self, rows):
            self.rows = rows
            self.columns = ["synthetic_marker"]

        def __len__(self):
            return self.rows

    frames = [FakeFrame(3), FakeFrame(4)]

    class FakePandas:
        DataFrame = FakeFrame

        @staticmethod
        def read_pickle(_path):
            return frames.pop(0)

    class FakeArray:
        def __init__(self, rows):
            self.shape = (rows, 384)
            self.dtype = "float32"
            self.writeable = True

        def setflags(self, *, write):
            self.writeable = write

    arrays = [FakeArray(3), FakeArray(4)]

    class FakeFinite:
        @staticmethod
        def all():
            return True

    class FakeNumpy:
        ndarray = FakeArray

        @staticmethod
        def load(_path, *, allow_pickle):
            assert allow_pickle is False
            return arrays.pop(0)

        @staticmethod
        def isfinite(_value):
            return FakeFinite()

    model_calls = []

    class FakeSentenceTransformer:
        def __init__(self, path, *, local_files_only, trust_remote_code):
            model_calls.append((path, local_files_only, trust_remote_code))

        @staticmethod
        def get_sentence_embedding_dimension():
            return 384

    loaded_arrays = [FakeArray(3), FakeArray(4)]
    arrays[:] = loaded_arrays
    loaded = real.load_production_resources(
        evidence,
        repository_root=tmp_path,
        _preflight_module=FakePreflight,
        _paths=paths,
        _dependency_loader=lambda: (
            FakeNumpy,
            FakePandas,
            FakeSentenceTransformer,
            lambda *_args: None,
        ),
    )
    assert set(loaded.families) == {"v1_qa", "v2_mixed"}
    assert all(not array.writeable for array in loaded_arrays)
    assert model_calls == [(str(model_observation.snapshot_path), True, False)]
    assert _sha(dict(evidence.artifact)) == before_artifact
    assert (
        _sha({name: dict(value) for name, value in evidence.resource_wrappers.items()})
        == before_wrappers
    )
    assert not any(tmp_path.iterdir())


def test_guard_order_delays_resources_config_and_client_until_non_secret_gates():
    plan = _synthetic_plan()
    evidence = _evidence()
    events: list[str] = []
    repository = real.RepositoryIdentity("main", "1" * 40)
    ready = _prefix_state(plan, 0)
    paused = _prefix_state(plan, 1, action="prefix_paused", new=1)
    loaded = real.LoadedProductionResources(
        {"v1_qa": (object(), object()), "v2_mixed": (object(), object())},
        object(),
        lambda *_args: None,
    )

    def event(name, value):
        def called(*_args, **_kwargs):
            events.append(name)
            return value

        return called

    outcome = real.execute_guarded_real_prefix(
        plan,
        confirmation=real.CONFIRMATION_TOKEN,
        expected_b4_preflight_sha256=evidence.preflight_sha256,
        max_new_successes=1,
        output_path=real.DRY_RUN_OUTPUT_PATH,
        repository_gate=event("repository", repository),
        plan_validator=event("plan", None),
        evidence_consumer=event("evidence", evidence),
        metadata_loader=event("metadata", _metadata()),
        contract_builder=event("contract", _real_contract(plan, evidence)),
        progress_reader=event("progress", ready),
        resource_loader=event("resources", loaded),
        config_parser=event("config", SimpleNamespace(api_key="synthetic", base_url="https://api.deepseek.com", model="deepseek-chat")),
        client_factory=event("client", object()),
        authority_factory=event("authority", object()),
        prefix_executor=event("prefix", paused),
    )
    assert outcome is paused
    assert events == [
        "repository",
        "plan",
        "evidence",
        "metadata",
        "contract",
        "progress",
        "resources",
        "config",
        "client",
        "authority",
        "prefix",
    ]


def test_default_real_path_holds_one_lock_across_pending_secret_and_prefix_gates(
    monkeypatch: pytest.MonkeyPatch,
):
    plan = _synthetic_plan()
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    repository = real.RepositoryIdentity("main", "1" * 40)
    ready = _prefix_state(plan, 0)
    paused = _prefix_state(plan, 1, action="prefix_paused", new=1)
    loaded = real.LoadedProductionResources(
        {"v1_qa": (object(), object()), "v2_mixed": (object(), object())},
        object(),
        lambda *_args: None,
    )
    active = False
    events: list[str] = []

    @contextlib.contextmanager
    def locked_invocation(_plan, _contract):
        nonlocal active
        assert active is False
        active = True
        events.append("lock_enter")
        try:
            yield ready
        finally:
            events.append("lock_exit")
            active = False

    def inside(name, value):
        def called(*_args, **_kwargs):
            assert active is True
            events.append(name)
            return value

        return called

    monkeypatch.setattr(store, "_real_prefix_invocation", locked_invocation)
    monkeypatch.setattr(
        store,
        "_orchestrate_durable_prefix",
        inside("prefix", paused),
    )
    outcome = real.execute_guarded_real_prefix(
        plan,
        confirmation=real.CONFIRMATION_TOKEN,
        expected_b4_preflight_sha256=evidence.preflight_sha256,
        max_new_successes=1,
        output_path=real.DRY_RUN_OUTPUT_PATH,
        repository_gate=lambda: repository,
        plan_validator=lambda _plan: None,
        evidence_consumer=lambda _sha: evidence,
        metadata_loader=_metadata,
        contract_builder=lambda *_args: contract,
        resource_loader=inside("resources", loaded),
        config_parser=inside(
            "config",
            SimpleNamespace(
                api_key="synthetic",
                base_url="https://api.deepseek.com",
                model="deepseek-chat",
            ),
        ),
        client_factory=inside("client", object()),
        authority_factory=inside("authority", object()),
    )
    assert outcome is paused
    assert active is False
    assert events == [
        "lock_enter",
        "resources",
        "config",
        "client",
        "authority",
        "prefix",
        "lock_exit",
    ]


@pytest.mark.parametrize(
    ("confirmation", "maximum", "preflight"),
    [
        (None, 1, "a" * 64),
        ("wrong", 1, "a" * 64),
        (real.CONFIRMATION_TOKEN, None, "a" * 64),
        (real.CONFIRMATION_TOKEN, 1, None),
    ],
)
def test_explicit_real_authorization_fails_before_any_gate(
    confirmation, maximum, preflight
):
    called = []
    with pytest.raises(real.RealExecutionError, match="B5_AUTHORIZATION_BLOCKED"):
        real.execute_guarded_real_prefix(
            _synthetic_plan(),
            confirmation=confirmation,
            expected_b4_preflight_sha256=preflight,
            max_new_successes=maximum,
            output_path=real.DRY_RUN_OUTPUT_PATH,
            repository_gate=lambda: called.append("repository"),
        )
    assert called == []


def test_pre_secret_failure_and_complete_run_never_load_config_or_client():
    plan = _synthetic_plan()
    evidence = _evidence()
    forbidden = lambda *_args, **_kwargs: pytest.fail("secret/client boundary reached")
    with pytest.raises(real.RealExecutionError, match="B5_PREFLIGHT_INVALID"):
        real.execute_guarded_real_prefix(
            plan,
            confirmation=real.CONFIRMATION_TOKEN,
            expected_b4_preflight_sha256=evidence.preflight_sha256,
            max_new_successes=1,
            output_path=real.DRY_RUN_OUTPUT_PATH,
            repository_gate=lambda: real.RepositoryIdentity("main", "1" * 40),
            plan_validator=lambda _plan: None,
            evidence_consumer=lambda _sha: (_ for _ in ()).throw(
                real.RealExecutionError("B5_PREFLIGHT_INVALID")
            ),
            resource_loader=forbidden,
            config_parser=forbidden,
            client_factory=forbidden,
        )
    complete = _prefix_state(plan, 190)
    outcome = real.execute_guarded_real_prefix(
        plan,
        confirmation=real.CONFIRMATION_TOKEN,
        expected_b4_preflight_sha256=evidence.preflight_sha256,
        max_new_successes=1,
        output_path=real.DRY_RUN_OUTPUT_PATH,
        repository_gate=lambda: real.RepositoryIdentity("main", "1" * 40),
        plan_validator=lambda _plan: None,
        evidence_consumer=lambda _sha: evidence,
        metadata_loader=_metadata,
        contract_builder=lambda *_args: _real_contract(plan, evidence),
        progress_reader=lambda *_args: complete,
        resource_loader=forbidden,
        config_parser=forbidden,
        client_factory=forbidden,
    )
    assert outcome.action == "run_complete"


def test_phase_boundaries_canary_interrupted_rq1_and_resume_order_103():
    plan = _synthetic_plan()
    real.validate_phase_boundary(plan, _prefix_state(plan, 0), 1)
    with pytest.raises(real.RealExecutionError, match="B5_PREFIX_BOUNDARY_INVALID"):
        real.validate_phase_boundary(plan, _prefix_state(plan, 0), 2)
    real.validate_phase_boundary(plan, _prefix_state(plan, 1), 101)
    real.validate_phase_boundary(plan, _prefix_state(plan, 37), 65)
    with pytest.raises(real.RealExecutionError, match="B5_PREFIX_BOUNDARY_INVALID"):
        real.validate_phase_boundary(plan, _prefix_state(plan, 37), 66)
    state = _prefix_state(plan, 102)
    assert state.progress.next_eligible_execution_order == 103
    real.validate_phase_boundary(plan, state, 40)


def test_store_prefix_canary_rq1_completion_resume_and_real_projection(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    authority = _LocalAuthority(evidence, contract)
    plan_before = _sha(plan)
    evidence_before = _sha(dict(evidence.artifact))
    canary = store._orchestrate_durable_prefix(
        plan,
        expected_contract=contract,
        authority=authority,
        max_new_successes=1,
    )
    assert (canary.action, canary.new_successes) == ("prefix_paused", 1)
    assert canary.progress.total_successful_units == 1
    assert authority.orders == [1]
    rq1 = store._orchestrate_durable_prefix(
        plan,
        expected_contract=contract,
        authority=authority,
        max_new_successes=101,
    )
    assert rq1.progress.total_successful_units == 102
    assert rq1.progress.next_eligible_execution_order == 103
    assert authority.orders == list(range(1, 103))
    rq2 = store._orchestrate_durable_prefix(
        plan,
        expected_contract=contract,
        authority=authority,
        max_new_successes=40,
    )
    assert rq2.progress.total_successful_units == 142
    assert authority.orders[102] == 103
    complete = store._orchestrate_durable_prefix(
        plan,
        expected_contract=contract,
        authority=authority,
        max_new_successes=48,
    )
    assert complete.action == "run_complete"
    assert complete.progress.total_successful_units == 190
    assert authority.orders == list(range(1, 191))
    assert len(authority.resumed_turn_two_orders) == 12
    reopened = store._real_prefix_progress(plan, contract)
    assert reopened.action == "run_complete"
    assert authority.orders == list(range(1, 191))
    observed = store._observe_validated_canonical_private_results(plan, contract)
    checked_contract = projection._validate_authoritative_contract(dict(contract))
    projection._apply_source_eligibility_gate(checked_contract)
    snapshot = projection._validate_snapshot(plan, checked_contract, observed)
    assert len(snapshot) == 190
    assert _sha(plan) == plan_before
    assert _sha(dict(evidence.artifact)) == evidence_before


def test_provider_retry_ceiling_and_uncertain_outcome_are_non_recallable(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    retry_client = _RetryCompletions(_RetryableFailure())
    retry_authority = _ProviderAuthority(evidence, contract, retry_client)
    exhausted = store._orchestrate_durable_prefix(
        plan,
        expected_contract=contract,
        authority=retry_authority,
        max_new_successes=1,
    )
    assert exhausted.action == "blocked"
    assert exhausted.block_category == "attempts_exhausted"
    assert retry_client.calls == 3
    assert store._real_prefix_progress(plan, contract).block_category == "attempts_exhausted"
    assert retry_client.calls == 3

    monkeypatch.setattr(
        store,
        "_PRIVATE_STATE_ROOT",
        store._PRIVATE_STATE_ROOT.parent / "uncertain_state",
    )
    contract2 = _real_contract(plan, evidence)
    uncertain_client = _RetryCompletions(TimeoutError())
    uncertain_authority = _ProviderAuthority(evidence, contract2, uncertain_client)
    uncertain = store._orchestrate_durable_prefix(
        plan,
        expected_contract=contract2,
        authority=uncertain_authority,
        max_new_successes=1,
    )
    assert uncertain.action == "blocked"
    assert uncertain.block_category == "uncertain"
    assert uncertain_client.calls == 1
    assert store._real_prefix_progress(plan, contract2).block_category == "uncertain"
    assert uncertain_client.calls == 1

    monkeypatch.setattr(
        store,
        "_PRIVATE_STATE_ROOT",
        store._PRIVATE_STATE_ROOT.parent / "terminal_state",
    )
    contract3 = _real_contract(plan, evidence)
    terminal_client = _RetryCompletions(_TerminalFailure())
    terminal_authority = _ProviderAuthority(evidence, contract3, terminal_client)
    terminal = store._orchestrate_durable_prefix(
        plan,
        expected_contract=contract3,
        authority=terminal_authority,
        max_new_successes=1,
    )
    assert terminal.action == "blocked"
    assert terminal.block_category == "terminal_failed"
    assert terminal_client.calls == 1
    assert store._real_prefix_progress(plan, contract3).block_category == "terminal_failed"
    assert terminal_client.calls == 1


def test_proven_pre_send_failure_is_the_only_no_call_retry_class():
    tracker = transport.ProviderCallTracker()
    tracker.record_pre_send_failure()
    assert tracker.state == "pre_send_failure"
    assert tracker.provider_called is False
    assert transport.retry_classification(pre_send=True) == "retryable"
    assert transport.may_retry(1, "retryable") is True
    assert transport.may_retry(3, "retryable") is False


def test_provider_returned_persistence_failure_blocks_without_recall(
    monkeypatch: pytest.MonkeyPatch,
):
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    client = _SuccessCompletions()
    authority = _ProviderAuthority(evidence, contract, client)
    original = store._publish_private_commit_locked

    def fail_commit(*_args, **_kwargs):
        raise store.StoreError("STORE_IO_FAILURE")

    monkeypatch.setattr(store, "_publish_private_commit_locked", fail_commit)
    with pytest.raises(store.StoreError, match="STORE_IO_FAILURE"):
        store._orchestrate_durable_prefix(
            plan,
            expected_contract=contract,
            authority=authority,
            max_new_successes=1,
        )
    assert client.calls == 1
    monkeypatch.setattr(store, "_publish_private_commit_locked", original)
    state = store._real_prefix_progress(plan, contract)
    assert state.action == "blocked"
    assert state.block_category == "provider_returned_without_commit"
    assert client.calls == 1


def test_credentials_are_synthetic_redacted_and_client_retries_are_disabled(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
):
    sentinel = "SYNTHETIC_STAGE_B5_SENTINEL_DO_NOT_LOG"
    path = tmp_path / "synthetic.env"
    path.write_text(
        "DEEPSEEK_API_KEY="
        + sentinel
        + "\nDEEPSEEK_BASE_URL=https://api.deepseek.com\nDEEPSEEK_MODEL=deepseek-chat\n",
        encoding="utf-8",
    )
    config = transport.parse_deepseek_config(str(path))
    assert sentinel not in repr(config)
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.chat = SimpleNamespace(completions=_SuccessCompletions())

    adapter = real.construct_real_client(config, _client_type=FakeClient)
    assert isinstance(adapter, real._SDKRawCompletionsAdapterV1)
    assert captured["max_retries"] == 0
    assert captured["timeout"] == 60.0
    assert sentinel not in repr(adapter)
    output = capsys.readouterr()
    assert sentinel not in output.out
    assert sentinel not in output.err
    contract = _real_contract(_synthetic_plan())
    assert sentinel.encode() not in json.dumps(dict(contract), default=dict).encode()
    _patch_synthetic_plan_authority(monkeypatch)
    plan = _synthetic_plan()
    evidence = _evidence()
    contract = _real_contract(plan, evidence)
    authority = _ProviderAuthority(evidence, contract, _SuccessCompletions())
    authority.raw = adapter
    outcome = store._orchestrate_durable_prefix(
        plan,
        expected_contract=contract,
        authority=authority,
        max_new_successes=1,
    )
    assert outcome.new_successes == 1
    for artifact in store._PRIVATE_STATE_ROOT.rglob("*"):
        if artifact.is_file():
            assert sentinel.encode() not in artifact.read_bytes()
    assert not projection._REVIEWER_PROJECTION_ROOT.exists()

    class RejectingClient:
        def __init__(self, **_kwargs):
            raise RuntimeError(sentinel)

    with pytest.raises(real.RealExecutionError) as rejected:
        real.construct_real_client(config, _client_type=RejectingClient)
    assert sentinel not in str(rejected.value)
    assert sentinel not in repr(rejected.value)


def test_real_contract_projection_acceptance_and_fake_synthetic_rejection():
    plan = _synthetic_plan()
    contract = projection._validate_authoritative_contract(dict(_real_contract(plan)))
    projection._apply_source_eligibility_gate(contract)
    with pytest.raises(projection.ProjectionError, match="B3_INPUT_INCOMPLETE"):
        projection._validate_snapshot(plan, contract, ())
    fake = _base_contract()
    fake["runtime_resource_authority"]["resources"] = {
        name: {
            "resource_identity": runner._fixed_resource_mapping(name),
            "resource_identity_sha256": transport.resource_identity_sha256(
                transport.ProductionResourceIdentity.from_mapping(
                    runner._fixed_resource_mapping(name)
                )
            ),
        }
        for name in real._SYSTEM_CONFIG_IDS
    }
    with pytest.raises(projection.ProjectionError, match="B3_SOURCE_INELIGIBLE"):
        projection._apply_source_eligibility_gate(fake)
    synthetic_real = copy.deepcopy(contract)
    for name in real._SYSTEM_CONFIG_IDS:
        mapping = runner._fixed_resource_mapping(name)
        synthetic_real["runtime_resource_authority"]["resources"][name] = {
            "resource_identity": mapping,
            "resource_identity_sha256": transport.resource_identity_sha256(
                transport.ProductionResourceIdentity.from_mapping(mapping)
            ),
        }
    with pytest.raises(projection.ProjectionError, match="B3_SOURCE_INELIGIBLE"):
        projection._apply_source_eligibility_gate(synthetic_real)


def test_sdk_adapter_binds_request_identity_and_never_uses_network():
    completions = _SuccessCompletions()
    adapter = real._SDKRawCompletionsAdapterV1(completions)
    request_id = "call_" + "a" * 64
    adapter.bind_provider_request_id(request_id)
    raw = adapter.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "synthetic"}],
        temperature=0.0,
        top_p=1.0,
        max_tokens=512,
        stream=False,
    )
    assert raw["request_id"] == request_id
    assert raw["id"] == "synthetic_response_1"
    with pytest.raises(real.RealExecutionError, match="B5_CLIENT_INVALID"):
        adapter.create()
