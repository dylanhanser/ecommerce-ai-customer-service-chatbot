"""Stage B5 guarded real-execution authority.

Importing this module performs no environment-file access, optional dependency
import, client construction, production-resource access, or network operation.
Those boundaries are entered only by ``execute_guarded_real_prefix`` after the
ordered non-secret gates have succeeded.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.metadata
import io
import json
import math
import os
import re
import stat
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    ROOT
    / "data"
    / "formal_eval"
    / "resource_preflight"
    / "production_resource_preflight_v1.json"
)
PRIVATE_STATE_PATH = ROOT / "data" / "formal_eval" / "private_state"
DRY_RUN_OUTPUT_PATH = ROOT / "data" / "formal_eval" / "dry_run"
CONFIG_PATH = "outputs/.env"
CONFIRMATION_TOKEN = "FORMAL_EVAL_20260721"
PLAN_FINGERPRINT = "4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SYSTEM_CONFIG_IDS = (
    "qa_only_reconstructed_baseline",
    "v2",
    "single_turn",
    "context_aware",
)
_IMPLEMENTATION_PATHS = (
    "scripts/formal_evaluation_real_execution.py",
    "scripts/run_formal_evaluation.py",
    "scripts/formal_evaluation_orchestration.py",
    "scripts/formal_evaluation_store.py",
    "scripts/formal_evaluation_runtime.py",
    "scripts/formal_evaluation_transport.py",
    "scripts/formal_qa_only_baseline/adapter.py",
    "scripts/formal_evaluation_review_projection.py",
)
_ERROR_CATEGORIES = frozenset(
    {
        "B5_AUTHORIZATION_BLOCKED",
        "B5_FROZEN_PLAN_INVALID",
        "B5_PREFIX_BOUNDARY_INVALID",
        "B5_PREFLIGHT_INVALID",
        "B5_DURABLE_STATE_INVALID",
        "B5_CONFIGURATION_INVALID",
        "B5_RESOURCE_INVALID",
        "B5_CLIENT_INVALID",
        "B5_PRE_PROVIDER_REQUEST_INVALID",
        "B5_PROVIDER_RETRY_EXHAUSTED",
        "B5_PROVIDER_UNCERTAIN",
        "B5_PROVIDER_TERMINAL",
        "B5_PERSISTENCE_INVALID",
        "B5_INTERNAL_FAILURE",
    }
)


class RealExecutionError(RuntimeError):
    """A closed public Stage B5 failure category."""

    def __init__(self, category: str):
        if category not in _ERROR_CATEGORIES:
            category = "B5_INTERNAL_FAILURE"
        self.category = category
        super().__init__(category)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _ordinary_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise ValueError("invalid sha256")
    return value


@dataclass(frozen=True)
class RepositoryIdentity:
    branch: str
    commit: str

    def __post_init__(self) -> None:
        if self.branch != "main" or _GIT_OBJECT_RE.fullmatch(self.commit) is None:
            raise ValueError("invalid repository identity")

    def to_dict(self) -> dict[str, str]:
        return {"branch": self.branch, "commit": self.commit}


@dataclass(frozen=True)
class ValidatedB4Evidence:
    artifact: Mapping[str, Any]
    artifact_sha256: str
    preflight_sha256: str
    resource_wrappers: Mapping[str, Mapping[str, Any]]

    def __post_init__(self) -> None:
        _require_sha256(self.artifact_sha256)
        _require_sha256(self.preflight_sha256)
        if (
            not isinstance(self.artifact, Mapping)
            or not isinstance(self.resource_wrappers, Mapping)
            or set(self.resource_wrappers) != set(_SYSTEM_CONFIG_IDS)
        ):
            raise ValueError("invalid B4 evidence")
        object.__setattr__(
            self, "artifact", MappingProxyType(copy.deepcopy(dict(self.artifact)))
        )
        object.__setattr__(
            self,
            "resource_wrappers",
            MappingProxyType(
                {
                    name: MappingProxyType(copy.deepcopy(dict(wrapper)))
                    for name, wrapper in self.resource_wrappers.items()
                }
            ),
        )


@dataclass(frozen=True)
class LoadedProductionResources:
    families: Mapping[str, tuple[Any, Any]]
    embedding_model: Any
    cosine_similarity: Callable[[Any, Any], Any]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.families, Mapping)
            or set(self.families) != {"v1_qa", "v2_mixed"}
            or any(
                type(value) is not tuple
                or len(value) != 2
                or value[0] is None
                or value[1] is None
                for value in self.families.values()
            )
            or self.embedding_model is None
            or not callable(self.cosine_similarity)
        ):
            raise ValueError("invalid loaded production resources")
        object.__setattr__(self, "families", MappingProxyType(dict(self.families)))


def _git(repository_root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RealExecutionError("B5_AUTHORIZATION_BLOCKED") from exc
    return result.stdout.strip()


def validate_repository_gate(repository_root: Path = ROOT) -> RepositoryIdentity:
    """Require the published clean main checkout without contacting a remote."""

    branch = _git(repository_root, "branch", "--show-current")
    head = _git(repository_root, "rev-parse", "HEAD")
    local_main = _git(repository_root, "rev-parse", "main")
    origin_main = _git(repository_root, "rev-parse", "refs/remotes/origin/main")
    divergence = _git(
        repository_root,
        "rev-list",
        "--left-right",
        "--count",
        "main...refs/remotes/origin/main",
    )
    status = _git(repository_root, "status", "--short", "--untracked-files=all")
    if (
        branch != "main"
        or head != local_main
        or head != origin_main
        or divergence.split() != ["0", "0"]
        or status
    ):
        raise RealExecutionError("B5_AUTHORIZATION_BLOCKED")
    try:
        return RepositoryIdentity(branch, head)
    except ValueError as exc:
        raise RealExecutionError("B5_AUTHORIZATION_BLOCKED") from exc


def validate_plan_authority(plan: list[dict[str, Any]]) -> None:
    """Re-enter the one frozen runner authority without changing plan identity."""

    try:
        from collections import Counter
        import run_formal_evaluation as runner

        runner.verify_frozen()
        runner.validate_plan(plan)
        if (
            runner.PLAN_FINGERPRINT != PLAN_FINGERPRINT
            or runner.plan_fingerprint(plan) != PLAN_FINGERPRINT
            or len(plan) != 190
            or len({unit["request_id"] for unit in plan}) != 190
            or [unit["execution_order"] for unit in plan] != list(range(1, 191))
            or Counter(unit["rq"] for unit in plan)
            != {"RQ1": 102, "RQ2": 40, "RQ3": 48}
            or Counter(unit["system_config_id"] for unit in plan)
            != {
                "qa_only_reconstructed_baseline": 71,
                "v2": 71,
                "single_turn": 24,
                "context_aware": 24,
            }
        ):
            raise ValueError
    except RealExecutionError:
        raise
    except Exception as exc:
        raise RealExecutionError("B5_FROZEN_PLAN_INVALID") from exc


def consume_b4_evidence(
    expected_preflight_sha256: str,
    *,
    repository_root: Path = ROOT,
    _evidence_path: Path | None = None,
    _preflight_module: Any | None = None,
) -> ValidatedB4Evidence:
    """Consume the strict canonical B4 artifact and prove checkout freshness."""

    try:
        expected = _require_sha256(expected_preflight_sha256)
        if _preflight_module is None:
            import formal_evaluation_resource_preflight as preflight
        else:
            preflight = _preflight_module
        evidence_path = EVIDENCE_PATH if _evidence_path is None else _evidence_path
        if _evidence_path is None and evidence_path != EVIDENCE_PATH:
            raise ValueError
        transport = preflight._transport_authority()
        raw, artifact = preflight._read_existing_artifact(evidence_path, transport)
        if (
            artifact.get("schema_version") != 1
            or artifact.get("stage_id") != "B4"
            or artifact.get("status") != "passed"
            or artifact.get("contract_id")
            != "formal_production_resource_preflight_v1"
            or artifact.get("preflight_sha256") != expected
        ):
            raise ValueError
        observed = preflight._authority_observations_from_root(repository_root)
        current_authorities = [
            {
                "byte_count": item.byte_count,
                "path": item.relative_path,
                "sha256": item.sha256,
            }
            for item in observed
        ]
        if artifact.get("authority_files") != current_authorities:
            raise ValueError
        identity_entries = artifact.get("resource_identities")
        if type(identity_entries) is not list or len(identity_entries) != 4:
            raise ValueError
        mappings: dict[str, Mapping[str, Any]] = {}
        wrappers: dict[str, Mapping[str, Any]] = {}
        for config_id, entry in zip(_SYSTEM_CONFIG_IDS, identity_entries):
            if type(entry) is not dict or set(entry) != {
                "resource_identity",
                "resource_identity_sha256",
            }:
                raise ValueError
            resource = transport.ProductionResourceIdentity.from_mapping(
                entry["resource_identity"]
            )
            transport.validate_resource_identity(resource)
            if (
                resource.system_config_id != config_id
                or resource.synthetic
                or resource.resource_type != "production_frozen"
                or entry["resource_identity_sha256"]
                != transport.resource_identity_sha256(resource)
            ):
                raise ValueError
            mappings[config_id] = resource.to_dict()
            wrappers[config_id] = copy.deepcopy(entry)
        from formal_evaluation_orchestration import ProductionResourceBundle

        ProductionResourceBundle.from_mappings(mappings)
        return ValidatedB4Evidence(
            artifact=artifact,
            artifact_sha256=_ordinary_sha256(raw),
            preflight_sha256=expected,
            resource_wrappers=wrappers,
        )
    except RealExecutionError:
        raise
    except Exception as exc:
        raise RealExecutionError("B5_PREFLIGHT_INVALID") from exc


def _regular_file_observation(repository_root: Path, relative_path: str) -> dict[str, Any]:
    path = repository_root.joinpath(*relative_path.split("/"))
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise ValueError
        raw = path.read_bytes()
    except (OSError, ValueError) as exc:
        raise RealExecutionError("B5_FROZEN_PLAN_INVALID") from exc
    if len(raw) != info.st_size or not raw:
        raise RealExecutionError("B5_FROZEN_PLAN_INVALID")
    return {
        "path": relative_path,
        "byte_count": len(raw),
        "sha256": _ordinary_sha256(raw),
    }


def implementation_observations(repository_root: Path = ROOT) -> tuple[dict[str, Any], ...]:
    return tuple(
        _regular_file_observation(repository_root, relative)
        for relative in _IMPLEMENTATION_PATHS
    )


def discover_client_transport_metadata() -> dict[str, Any]:
    """Observe SDK identity without importing it or constructing a client."""

    try:
        version = importlib.metadata.version("openai")
    except importlib.metadata.PackageNotFoundError as exc:
        raise RealExecutionError("B5_CLIENT_INVALID") from exc
    if type(version) is not str or not version or len(version) > 128:
        raise RealExecutionError("B5_CLIENT_INVALID")
    return {
        "base_url": "https://api.deepseek.com",
        "max_retries": 0,
        "model": "deepseek-chat",
        "sdk_distribution": "openai",
        "sdk_version": version,
        "timeout_seconds": 60.0,
    }


def build_real_run_contract(
    plan: list[dict[str, Any]],
    evidence: ValidatedB4Evidence,
    repository: RepositoryIdentity,
    client_transport: Mapping[str, Any],
    *,
    repository_root: Path = ROOT,
    _base_contract: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Build the exact non-secret production-real durable contract."""

    try:
        import run_formal_evaluation as runner

        base = copy.deepcopy(
            dict(
                runner.build_durable_run_contract(plan)
                if _base_contract is None
                else _base_contract
            )
        )
        if (
            base.get("schema_version") != 1
            or base.get("stage_id") != "B2"
            or base.get("provider_generation_authority", {})
            .get("offline_execution", {})
            .get("mode")
            != "offline_fake_only"
            or type(evidence) is not ValidatedB4Evidence
            or type(repository) is not RepositoryIdentity
            or type(client_transport) is not dict
            or set(client_transport)
            != {
                "base_url",
                "max_retries",
                "model",
                "sdk_distribution",
                "sdk_version",
                "timeout_seconds",
            }
            or client_transport["base_url"] != "https://api.deepseek.com"
            or client_transport["model"] != "deepseek-chat"
            or client_transport["max_retries"] != 0
            or client_transport["timeout_seconds"] != 60.0
            or client_transport["sdk_distribution"] != "openai"
            or type(client_transport["sdk_version"]) is not str
            or not client_transport["sdk_version"]
            or len(client_transport["sdk_version"]) > 128
        ):
            raise ValueError
        observations = implementation_observations(repository_root)
        by_path = {item["path"]: item for item in observations}
        artifact = dict(evidence.artifact)
        without_hash = {
            "schema_version": 1,
            "stage_id": "B5",
            "plan_authority": copy.deepcopy(base["plan_authority"]),
            "frozen_input_sha256": copy.deepcopy(base["frozen_input_sha256"]),
            "formal_system_authority": copy.deepcopy(
                base["formal_system_authority"]
            ),
            "provider_generation_authority": {
                "generation": copy.deepcopy(
                    base["provider_generation_authority"]["generation"]
                ),
                "transport": copy.deepcopy(
                    base["provider_generation_authority"]["transport"]
                ),
                "real_execution": {
                    "authority_bundle_id": "formal_evaluation_real_execution.ProductionRealAuthorityV1",
                    "client_adapter_id": "formal_evaluation_real_execution._SDKRawCompletionsAdapterV1",
                    "client_transport": copy.deepcopy(dict(client_transport)),
                    "clock_id": "formal_evaluation_real_execution._MonotonicUTCClockV1",
                    "executor_registry_id": "formal_evaluation_real_execution._build_executor_registry_v1",
                    "mode": "production_real",
                    "snapshot_validator_id": "formal_evaluation_runtime.restore_runtime_snapshot",
                },
            },
            "runtime_resource_authority": {
                "b4_preflight": {
                    "artifact_path": "data/formal_eval/resource_preflight/production_resource_preflight_v1.json",
                    "artifact_sha256": evidence.artifact_sha256,
                    "authority_files": copy.deepcopy(artifact["authority_files"]),
                    "contract_id": artifact["contract_id"],
                    "embedding_model": copy.deepcopy(artifact["embedding_model"]),
                    "preflight_sha256": evidence.preflight_sha256,
                    "resource_families": copy.deepcopy(
                        artifact["resource_families"]
                    ),
                    "stage_id": artifact["stage_id"],
                    "status": artifact["status"],
                },
                "implementation_files": [copy.deepcopy(item) for item in observations],
                "repository": repository.to_dict(),
                "resources": {
                    name: copy.deepcopy(dict(evidence.resource_wrappers[name]))
                    for name in _SYSTEM_CONFIG_IDS
                },
                "runtime_identity_sha256": by_path[
                    "scripts/formal_evaluation_runtime.py"
                ]["sha256"],
                "transport_implementation_sha256": by_path[
                    "scripts/formal_evaluation_transport.py"
                ]["sha256"],
            },
            "schema_authority": copy.deepcopy(base["schema_authority"]),
        }
        contract = dict(without_hash)
        contract["run_contract_sha256"] = _canonical_sha256(
            {
                "domain": "formal-evaluation-run-contract-v1",
                "contract": without_hash,
            }
        )
        return contract
    except RealExecutionError:
        raise
    except Exception as exc:
        raise RealExecutionError("B5_DURABLE_STATE_INVALID") from exc


def rebuild_real_run_contract_from_stored(
    plan: list[dict[str, Any]], stored_contract: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Rebuild a stored real contract for later B3 read-only projection."""

    try:
        if (
            type(stored_contract) is not dict
            or stored_contract.get("stage_id") != "B5"
            or stored_contract.get("provider_generation_authority", {})
            .get("real_execution", {})
            .get("mode")
            != "production_real"
        ):
            raise ValueError
        expected = stored_contract["runtime_resource_authority"]["b4_preflight"][
            "preflight_sha256"
        ]
        repository = validate_repository_gate()
        validate_plan_authority(plan)
        evidence = consume_b4_evidence(expected)
        metadata = discover_client_transport_metadata()
        rebuilt = build_real_run_contract(plan, evidence, repository, metadata)
        if dict(rebuilt) != dict(stored_contract):
            raise ValueError
        return rebuilt
    except RealExecutionError:
        raise
    except Exception as exc:
        raise RealExecutionError("B5_DURABLE_STATE_INVALID") from exc


def _family_artifact(evidence: ValidatedB4Evidence, family: str) -> Mapping[str, Any]:
    matches = [
        item
        for item in evidence.artifact["resource_families"]
        if item.get("cache_family") == family
    ]
    if len(matches) != 1:
        raise RealExecutionError("B5_RESOURCE_INVALID")
    return matches[0]


def load_production_resources(
    evidence: ValidatedB4Evidence,
    *,
    repository_root: Path = ROOT,
    _preflight_module: Any | None = None,
    _paths: Any | None = None,
    _dependency_loader: Callable[[], tuple[Any, Any, Any, Any]] | None = None,
) -> LoadedProductionResources:
    """Load only B4-identified resources and prove before/after file identity."""

    try:
        if _preflight_module is None:
            import formal_evaluation_resource_preflight as preflight
        else:
            preflight = _preflight_module
        paths = preflight._production_paths(repository_root) if _paths is None else _paths
        family_paths = {
            "v1_qa": (paths.v1_corpus, paths.v1_embeddings),
            "v2_mixed": (paths.v2_corpus, paths.v2_embeddings),
        }

        def observe_files() -> dict[str, tuple[object, object]]:
            observed: dict[str, tuple[object, object]] = {}
            for family, (corpus_path, embeddings_path) in family_paths.items():
                expected = _family_artifact(evidence, family)
                corpus = preflight._hash_regular_file(
                    corpus_path, repository_root, expected["corpus"]["path"]
                )
                embeddings = preflight._hash_regular_file(
                    embeddings_path,
                    repository_root,
                    expected["embeddings"]["path"],
                )
                if (
                    corpus.byte_count != expected["corpus"]["byte_count"]
                    or corpus.sha256 != expected["corpus"]["sha256"]
                    or embeddings.byte_count
                    != expected["embeddings"]["byte_count"]
                    or embeddings.sha256 != expected["embeddings"]["sha256"]
                ):
                    raise ValueError
                observed[family] = (corpus, embeddings)
            return observed

        before = observe_files()
        model_before = preflight._hash_model_snapshot(paths)
        expected_model = evidence.artifact["embedding_model"]
        if (
            model_before.revision != expected_model["revision"]
            or model_before.file_count != expected_model["snapshot_file_count"]
            or model_before.total_bytes != expected_model["snapshot_total_bytes"]
            or model_before.snapshot_sha256 != expected_model["snapshot_sha256"]
        ):
            raise ValueError
        if _dependency_loader is None:
            import numpy as np
            import pandas as pd
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity

            dependencies = (np, pd, SentenceTransformer, cosine_similarity)
        else:
            dependencies = _dependency_loader()
        if type(dependencies) is not tuple or len(dependencies) != 4:
            raise ValueError
        np, pd, sentence_transformer, cosine_similarity = dependencies
        loaded: dict[str, tuple[Any, Any]] = {}
        for family, (corpus_path, embeddings_path) in family_paths.items():
            expected = _family_artifact(evidence, family)
            corpus = pd.read_pickle(corpus_path)
            embeddings = np.load(embeddings_path, allow_pickle=False)
            metadata = expected["corpus_metadata"]
            if (
                not isinstance(corpus, pd.DataFrame)
                or len(corpus) != metadata["row_count"]
                or list(corpus.columns) != metadata["columns"]
                or not isinstance(embeddings, np.ndarray)
                or tuple(embeddings.shape)
                != (expected["embeddings"]["rows"], 384)
                or str(embeddings.dtype) != "float32"
                or not bool(np.isfinite(embeddings).all())
            ):
                raise ValueError
            embeddings.setflags(write=False)
            loaded[family] = (corpus, embeddings)
        model = sentence_transformer(
            str(model_before.snapshot_path),
            local_files_only=True,
            trust_remote_code=False,
        )
        dimension = model.get_sentence_embedding_dimension()
        if type(dimension) is not int or dimension != 384:
            raise ValueError
        after = observe_files()
        model_after = preflight._hash_model_snapshot(paths)
        if after != before or model_after != model_before:
            raise ValueError
        return LoadedProductionResources(loaded, model, cosine_similarity)
    except RealExecutionError:
        raise
    except Exception as exc:
        raise RealExecutionError("B5_RESOURCE_INVALID") from exc


class _MonotonicUTCClockV1:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last: datetime | None = None

    def __call__(self) -> str:
        with self._lock:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            if self._last is not None and now <= self._last:
                now = self._last + timedelta(seconds=1)
            self._last = now
            return now.strftime("%Y-%m-%dT%H:%M:%SZ")


class _SDKRawCompletionsAdapterV1:
    """Attach the local request identity while retaining only safe SDK fields."""

    def __init__(self, completions: Any):
        if not callable(getattr(completions, "create", None)):
            raise RealExecutionError("B5_CLIENT_INVALID")
        self._completions = completions
        self._provider_request_id: str | None = None

    def bind_provider_request_id(self, provider_request_id: str) -> None:
        from formal_evaluation_transport import validate_provider_identity

        validate_provider_identity(provider_request_id, "PROVIDER_REQUEST_ID_INVALID")
        if self._provider_request_id is not None:
            raise RealExecutionError("B5_CLIENT_INVALID")
        self._provider_request_id = provider_request_id

    @staticmethod
    def _field(value: Any, name: str) -> Any:
        return value.get(name) if type(value) is dict else getattr(value, name, None)

    def create(self, **request: Any) -> dict[str, Any]:
        provider_request_id = self._provider_request_id
        self._provider_request_id = None
        if provider_request_id is None:
            raise RealExecutionError("B5_CLIENT_INVALID")
        raw = self._completions.create(**request)
        choices = self._field(raw, "choices")
        response_id = self._field(raw, "id")
        if type(choices) not in (list, tuple) or len(choices) != 1:
            return {"request_id": provider_request_id, "id": response_id, "choices": choices}
        message = self._field(choices[0], "message")
        content = self._field(message, "content")
        return {
            "request_id": provider_request_id,
            "id": response_id,
            "choices": [{"message": {"content": content}}],
        }


class _CoreCompletionsGatewayV1:
    """Validate a core request and route it only through ExecutorContext."""

    def __init__(self, context: Any):
        self._context = context
        self.generation_attempted = False
        self.provider_called = False
        self.pre_provider_failure_category: str | None = None

    def create(self, *args: Any, **request: Any) -> Any:
        from formal_evaluation_transport import TransportError, validate_messages

        self.generation_attempted = True
        if args:
            self.pre_provider_failure_category = "FIXED_REQUEST_INVALID"
            raise TransportError(self.pre_provider_failure_category)
        expected = {
            "model": "deepseek-chat",
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 512,
            "stream": False,
        }
        messages = request.pop("messages", None)
        if request != expected:
            self.pre_provider_failure_category = "FIXED_REQUEST_INVALID"
            raise TransportError(self.pre_provider_failure_category)

        try:
            normalized = validate_messages(messages)
        except TransportError as exc:
            self.pre_provider_failure_category = exc.category
            raise
        self.provider_called = True
        response = self._context.invoke_provider(
            [dict(message) for message in normalized]
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=response.content))]
        )


class _CoreClientFacadeV1:
    def __init__(self, gateway: _CoreCompletionsGatewayV1):
        self.chat = SimpleNamespace(completions=gateway)


def _reject_pre_provider_core_fallback(gateway: _CoreCompletionsGatewayV1) -> None:
    if gateway.generation_attempted and not gateway.provider_called:
        from formal_evaluation_transport import TransportError

        raise TransportError(
            gateway.pre_provider_failure_category or "FIXED_REQUEST_INVALID"
        )


def _safe_retrieval_projection(result: Mapping[str, Any]) -> tuple[list[str], list[float]]:
    rows = result.get("reranked_results", result.get("original_results", []))
    if type(rows) is not list:
        return [], []
    identifiers: list[str] = []
    scores: list[float] = []
    for item in rows[:100]:
        if type(item) not in (tuple, list) or len(item) != 2:
            continue
        row, score = item
        getter = getattr(row, "get", None)
        document_id = getter("doc_id") if callable(getter) else None
        if (
            type(document_id) is str
            and _SAFE_ID_RE.fullmatch(document_id) is not None
            and type(score) in (int, float)
            and not isinstance(score, bool)
            and math.isfinite(score)
        ):
            identifiers.append(document_id)
            scores.append(float(score))
    return identifiers, scores


def _project_v2_core_result(
    result: Mapping[str, Any],
    gateway: _CoreCompletionsGatewayV1,
    *,
    runtime_snapshot: Mapping[str, Any] | None,
) -> dict[str, Any]:
    _reject_pre_provider_core_fallback(gateway)
    answer = result.get("final_answer")
    if type(answer) is not str or not answer:
        raise RealExecutionError("B5_INTERNAL_FAILURE")
    identifiers, scores = _safe_retrieval_projection(result)
    requires_backend = bool(result.get("requires_backend_api", False))
    if gateway.provider_called:
        route = "provider"
    elif requires_backend:
        route = "backend_boundary"
    elif result.get("skip_llm") is True:
        route = "local_guard"
    else:
        route = "conservative_response"
    category = result.get("query_type")
    if type(category) is not str or _SAFE_ID_RE.fullmatch(category) is None:
        category = "formal_core"
    projected = {
        "response_text": answer,
        "route": route,
        "guard_category": category,
        "requires_backend_api": requires_backend,
        "retrieval_used": result.get("skip_retrieval") is not True,
        "retrieved_document_ids": identifiers,
        "retrieved_scores": scores,
    }
    if runtime_snapshot is not None:
        projected["runtime_snapshot"] = copy.deepcopy(dict(runtime_snapshot))
    return projected


class ProductionRealAuthorityV1:
    """Closed real authority supplied to the existing durable dependency seam."""

    mode = "production_real"

    def __init__(
        self,
        evidence: ValidatedB4Evidence,
        loaded: LoadedProductionResources,
        raw_completions: _SDKRawCompletionsAdapterV1,
        contract: Mapping[str, Any],
    ):
        from formal_evaluation_orchestration import ProductionResourceBundle

        if (
            type(evidence) is not ValidatedB4Evidence
            or type(loaded) is not LoadedProductionResources
            or type(raw_completions) is not _SDKRawCompletionsAdapterV1
            or type(contract) is not dict
            or contract.get("stage_id") != "B5"
            or contract.get("provider_generation_authority", {})
            .get("real_execution", {})
            .get("mode")
            != "production_real"
            or contract.get("runtime_resource_authority", {}).get("resources")
            != {
                name: dict(evidence.resource_wrappers[name])
                for name in _SYSTEM_CONFIG_IDS
            }
        ):
            raise RealExecutionError("B5_DURABLE_STATE_INVALID")
        mappings = {
            name: dict(evidence.resource_wrappers[name]["resource_identity"])
            for name in _SYSTEM_CONFIG_IDS
        }
        self.resources = ProductionResourceBundle.from_mappings(mappings)
        self._loaded = loaded
        self._raw_completions = raw_completions
        runtime = contract["runtime_resource_authority"]
        self.transport_implementation_sha256 = runtime[
            "transport_implementation_sha256"
        ]
        self.runtime_identity_sha256 = runtime["runtime_identity_sha256"]
        self.snapshot_validator = self._snapshot_validator
        self._clock = _MonotonicUTCClockV1()

    @staticmethod
    def _snapshot_validator(value: Mapping[str, Any]) -> Any:
        from formal_evaluation_runtime import restore_runtime_snapshot

        return restore_runtime_snapshot(value)

    def clock_for(self, _unit: Mapping[str, Any], _state: Any) -> _MonotonicUTCClockV1:
        return self._clock

    def _baseline_executor(self, context: Any) -> Mapping[str, Any]:
        from formal_qa_only_baseline.adapter import (
            BaselineResources,
            run_qa_only_baseline_query,
        )

        corpus, embeddings = self._loaded.families["v1_qa"]
        gateway = _CoreCompletionsGatewayV1(context)
        resources = BaselineResources(
            documents=corpus,
            embeddings=embeddings,
            embedding_model=self._loaded.embedding_model,
            cosine_similarity=self._loaded.cosine_similarity,
            llm_client=_CoreClientFacadeV1(gateway),
            metadata={
                "cache_family": "v1_qa",
                "contains_structured_snippets": False,
                "corpus_type": "qa_only",
                "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "row_count": 15333,
                "synthetic": False,
            },
            synthetic=False,
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            result = run_qa_only_baseline_query(
                context.unit["payload"]["user_input"], resources
            )
        _reject_pre_provider_core_fallback(gateway)
        answer = result.get("answer")
        if type(answer) is not str or not answer:
            raise RealExecutionError("B5_INTERNAL_FAILURE")
        return {
            "response_text": answer,
            "route": "provider" if gateway.provider_called else "local_guard",
            "guard_category": "qa_only_baseline",
            "requires_backend_api": False,
            "retrieval_used": bool(result.get("retrieved_count", 0)),
            "retrieved_document_ids": [],
            "retrieved_scores": [],
        }

    def _v2_executor(self, context: Any) -> Mapping[str, Any]:
        from formal_evaluation_runtime import (
            ContextMode,
            EVALUATION_GENERATION_CONFIG,
            run_dialogue_checkpointed,
        )
        import rag_answer_demo as rag

        corpus, embeddings = self._loaded.families["v2_mixed"]
        gateway = _CoreCompletionsGatewayV1(context)
        client = _CoreClientFacadeV1(gateway)
        llm_config = rag.LLMConfig(
            api_key="provider-authorized",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            client=client,
        )
        context_aware = context.unit["system_config_id"] == "context_aware"
        mode = ContextMode.CONTEXT_AWARE if context_aware else ContextMode.SINGLE_TURN
        initial = context.checkpoint_snapshot if context_aware else None
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            run = run_dialogue_checkpointed(
                [context.unit["payload"]["user_input"]],
                mode=mode,
                initial_state_snapshot=initial,
                corpus=corpus,
                embeddings=embeddings,
                embedding_model=self._loaded.embedding_model,
                top_k=10,
                cosine_similarity=self._loaded.cosine_similarity,
                low_confidence_threshold=rag.LOW_CONFIDENCE_THRESHOLD,
                llm_config=llm_config,
                generation_config=EVALUATION_GENERATION_CONFIG,
            )
        if len(run.results) != 1:
            raise RealExecutionError("B5_INTERNAL_FAILURE")
        snapshot = (
            run.final_snapshot.to_dict()
            if context_aware and context.unit["turn_index"] == 1
            else None
        )
        return _project_v2_core_result(
            run.results[0], gateway, runtime_snapshot=snapshot
        )

    def dependencies_for(self, unit: Mapping[str, Any], _state: Any) -> dict[str, Any]:
        from formal_evaluation_orchestration import ExecutorRegistry

        executors = {
            "qa_only_reconstructed_baseline": self._baseline_executor,
            "v2": self._v2_executor,
            "single_turn": self._v2_executor,
            "context_aware": self._v2_executor,
        }
        return {
            "resources": self.resources,
            "executors": ExecutorRegistry(executors),
            "fake_raw_client": self._raw_completions,
            "clock": self.clock_for(unit, _state),
            "transport_implementation_sha256": self.transport_implementation_sha256,
            "runtime_identity_sha256": self.runtime_identity_sha256,
            "snapshot_validator": self.snapshot_validator,
        }


def construct_real_client(
    config: Any,
    *,
    _client_type: Callable[..., Any] | None = None,
) -> _SDKRawCompletionsAdapterV1:
    """Construct one zero-retry client only after validated configuration."""

    try:
        if _client_type is None:
            from openai import OpenAI

            client_type = OpenAI
        else:
            client_type = _client_type
        client = client_type(
            api_key=config.api_key,
            base_url=config.base_url,
            max_retries=0,
            timeout=60.0,
        )
        completions = client.chat.completions
        return _SDKRawCompletionsAdapterV1(completions)
    except Exception as exc:
        raise RealExecutionError("B5_CLIENT_INVALID") from exc


def _phase_expected_counts(
    plan: Sequence[Mapping[str, Any]], prefix: int
) -> tuple[dict[str, int], dict[str, int]]:
    rq = {"RQ1": 0, "RQ2": 0, "RQ3": 0}
    systems = {name: 0 for name in _SYSTEM_CONFIG_IDS}
    for unit in plan[:prefix]:
        rq[unit["rq"]] += 1
        systems[unit["system_config_id"]] += 1
    return rq, systems


def _raise_for_block(block_category: str | None) -> None:
    if block_category == "attempts_exhausted":
        raise RealExecutionError("B5_PROVIDER_RETRY_EXHAUSTED")
    if block_category in {
        "call_started",
        "provider_returned_without_commit",
        "uncertain",
    }:
        raise RealExecutionError("B5_PROVIDER_UNCERTAIN")
    if block_category == "terminal_failed":
        raise RealExecutionError("B5_PROVIDER_TERMINAL")
    raise RealExecutionError("B5_DURABLE_STATE_INVALID")


def validate_phase_boundary(
    plan: list[dict[str, Any]], state: Any, max_new_successes: int
) -> None:
    progress = state.progress
    prefix = progress.total_successful_units
    expected_rq, expected_systems = _phase_expected_counts(plan, prefix)
    if (
        dict(progress.successful_by_rq) != expected_rq
        or dict(progress.successful_by_system) != expected_systems
        or progress.remaining_units != 190 - prefix
    ):
        raise RealExecutionError("B5_PREFIX_BOUNDARY_INVALID")
    if state.action == "blocked":
        _raise_for_block(state.block_category)
    if state.action == "run_complete":
        return
    if (
        state.action not in {"ready", "prefix_paused"}
        or progress.next_eligible_execution_order != prefix + 1
    ):
        raise RealExecutionError("B5_PREFIX_BOUNDARY_INVALID")
    valid = False
    if prefix == 0:
        valid = max_new_successes == 1
    elif 1 <= prefix < 102:
        valid = prefix + max_new_successes <= 102
    elif prefix == 102:
        valid = 1 <= max_new_successes <= 88
    elif 103 <= prefix < 190:
        valid = prefix + max_new_successes <= 190
    if not valid:
        raise RealExecutionError("B5_PREFIX_BOUNDARY_INVALID")


def execute_guarded_real_prefix(
    plan: list[dict[str, Any]],
    *,
    confirmation: str | None,
    expected_b4_preflight_sha256: str | None,
    max_new_successes: int | None,
    output_path: Path,
    repository_gate: Callable[[], RepositoryIdentity] | None = None,
    plan_validator: Callable[[list[dict[str, Any]]], None] | None = None,
    evidence_consumer: Callable[[str], ValidatedB4Evidence] | None = None,
    metadata_loader: Callable[[], Mapping[str, Any]] | None = None,
    contract_builder: Callable[..., Mapping[str, Any]] | None = None,
    progress_reader: Callable[..., Any] | None = None,
    resource_loader: Callable[[ValidatedB4Evidence], LoadedProductionResources]
    | None = None,
    config_parser: Callable[[str], Any] | None = None,
    client_factory: Callable[[Any], Any] | None = None,
    authority_factory: Callable[..., Any] | None = None,
    prefix_executor: Callable[..., Any] | None = None,
) -> Any:
    """Run all ordered gates, then execute one bounded contiguous prefix."""

    if (
        confirmation != CONFIRMATION_TOKEN
        or type(max_new_successes) is not int
        or max_new_successes <= 0
        or type(expected_b4_preflight_sha256) is not str
        or _SHA256_RE.fullmatch(expected_b4_preflight_sha256) is None
        or output_path != DRY_RUN_OUTPUT_PATH
    ):
        raise RealExecutionError("B5_AUTHORIZATION_BLOCKED")
    repository = (repository_gate or validate_repository_gate)()
    (plan_validator or validate_plan_authority)(plan)
    evidence = (evidence_consumer or consume_b4_evidence)(
        expected_b4_preflight_sha256
    )
    metadata = dict((metadata_loader or discover_client_transport_metadata)())
    builder = contract_builder or build_real_run_contract
    contract = builder(plan, evidence, repository, metadata)
    use_default_locked_invocation = progress_reader is None and prefix_executor is None

    def execute_from_state(state: Any, selected_prefix_executor: Callable[..., Any]) -> Any:
        validate_phase_boundary(plan, state, max_new_successes)
        if state.action == "run_complete":
            return state
        loaded = (resource_loader or load_production_resources)(evidence)
        selected_config_parser = config_parser
        if selected_config_parser is None:
            from formal_evaluation_transport import parse_deepseek_config

            selected_config_parser = parse_deepseek_config
        try:
            config = selected_config_parser(CONFIG_PATH)
        except Exception as exc:
            raise RealExecutionError("B5_CONFIGURATION_INVALID") from exc
        try:
            raw_completions = (client_factory or construct_real_client)(config)
        except RealExecutionError:
            raise
        except Exception as exc:
            raise RealExecutionError("B5_CLIENT_INVALID") from exc
        factory = authority_factory or ProductionRealAuthorityV1
        try:
            authority = factory(evidence, loaded, raw_completions, contract)
        except RealExecutionError:
            raise
        except Exception as exc:
            raise RealExecutionError("B5_CLIENT_INVALID") from exc
        try:
            outcome = selected_prefix_executor(
                plan,
                expected_contract=contract,
                authority=authority,
                max_new_successes=max_new_successes,
            )
        except RealExecutionError:
            raise
        except Exception as exc:
            if getattr(exc, "category", None) == "FIXED_REQUEST_INVALID":
                raise RealExecutionError(
                    "B5_PRE_PROVIDER_REQUEST_INVALID"
                ) from exc
            raise RealExecutionError("B5_PERSISTENCE_INVALID") from exc
        if outcome.action == "blocked":
            _raise_for_block(outcome.block_category)
        if (
            outcome.action not in {"prefix_paused", "run_complete"}
            or not 0 <= outcome.new_successes <= max_new_successes
        ):
            raise RealExecutionError("B5_INTERNAL_FAILURE")
        return outcome

    if use_default_locked_invocation:
        from formal_evaluation_store import (
            _orchestrate_durable_prefix,
            _real_prefix_invocation,
        )

        try:
            with _real_prefix_invocation(plan, contract) as state:
                return execute_from_state(state, _orchestrate_durable_prefix)
        except RealExecutionError:
            raise
        except Exception as exc:
            raise RealExecutionError("B5_DURABLE_STATE_INVALID") from exc

    if progress_reader is None:
        from formal_evaluation_store import _real_prefix_progress

        progress_reader = _real_prefix_progress
    if prefix_executor is None:
        from formal_evaluation_store import _orchestrate_durable_prefix

        prefix_executor = _orchestrate_durable_prefix
    try:
        state = progress_reader(plan, contract)
    except RealExecutionError:
        raise
    except Exception as exc:
        raise RealExecutionError("B5_DURABLE_STATE_INVALID") from exc
    return execute_from_state(state, prefix_executor)


def aggregate_success_line(outcome: Any) -> str:
    progress = outcome.progress
    action = "B5_RUN_COMPLETE" if outcome.action == "run_complete" else "B5_PREFIX_PAUSED"
    next_order = (
        "none"
        if progress.next_eligible_execution_order is None
        else str(progress.next_eligible_execution_order)
    )
    return (
        f"{action} new_successes={outcome.new_successes} "
        f"total_successes={progress.total_successful_units} "
        f"remaining={progress.remaining_units} next_execution_order={next_order}"
    )
