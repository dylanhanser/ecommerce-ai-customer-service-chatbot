"""Stage B4 offline production-resource preflight.

This module is deliberately orchestration-only.  It imports no optional data or
model package, accepts no operational path override, never constructs a client,
and publishes only deterministic, observational evidence after a complete fresh
validation.  Production invocation remains a separately authorized operation.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, fields
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence


sys.dont_write_bytecode = True

_SCHEMA_VERSION = 1
_STAGE_ID = "B4"
_STATUS_PASSED = "passed"
_CONTRACT_ID = "formal_production_resource_preflight_v1"
_MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_MODEL_REPOSITORY_NAME = (
    "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"
)
_MODEL_PROBE_ID = "formal-evaluation-b4-offline-probe-v1"
_MODEL_TREE_DOMAIN = b"formal-evaluation-b4-model-tree-v1\0"
_PREFLIGHT_DOMAIN = b"formal-evaluation-b4-preflight-v1\0"
_FILE_MAXIMUM = 268_435_456
_MODEL_FILE_MAXIMUM = 4_096
_MODEL_BYTES_MAXIMUM = 2_147_483_648
_EVIDENCE_BYTES_MAXIMUM = 131_072
_WORKER_OUTPUT_MAXIMUM = 32_768
_WORKER_TIMEOUT_SECONDS = 300.0
_JSON_DEPTH_MAXIMUM = 16
_JSON_STRING_BYTES_MAXIMUM = 262_144
_JSON_MAPPING_MEMBERS_MAXIMUM = 128
_JSON_ARRAY_MEMBERS_MAXIMUM = 256
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_MOVEFILE_WRITE_THROUGH = 0x00000008
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+!-]{0,127}$")
_PATH_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TEMP_RE = re.compile(
    r"^\.production_resource_preflight_v1\.json\.[0-9a-f]{32}\.tmp$"
)

_FAILURE_CATEGORIES = (
    "B4_PLATFORM_UNSUPPORTED",
    "B4_AUTHORITY_INVALID",
    "B4_DEPENDENCY_UNAVAILABLE",
    "B4_PATH_UNSAFE",
    "B4_RESOURCE_MISSING",
    "B4_RESOURCE_TYPE_INVALID",
    "B4_EVIDENCE_INVALID",
    "B4_RESOURCE_MALFORMED",
    "B4_RESOURCE_INCOMPATIBLE",
    "B4_IDENTITY_MISMATCH",
    "B4_OFFLINE_VIOLATION",
    "B4_RESOURCE_MUTATED",
    "B4_EVIDENCE_STALE",
    "B4_LOCK_BUSY",
    "B4_IO_FAILURE",
    "B4_INTERNAL_FAILURE",
)
_FAILURE_SET = frozenset(_FAILURE_CATEGORIES)
_WORKER_FAILURE_SET = frozenset(
    {
        "B4_DEPENDENCY_UNAVAILABLE",
        "B4_RESOURCE_MALFORMED",
        "B4_RESOURCE_INCOMPATIBLE",
        "B4_IDENTITY_MISMATCH",
        "B4_OFFLINE_VIOLATION",
    }
)
_DEPENDENCY_NAMES = (
    "python",
    "numpy",
    "pandas",
    "scikit-learn",
    "sentence-transformers",
    "transformers",
    "huggingface-hub",
    "torch",
)
_DISTRIBUTION_NAMES = _DEPENDENCY_NAMES[1:]
_SYSTEM_CONFIG_ORDER = (
    "qa_only_reconstructed_baseline",
    "v2",
    "single_turn",
    "context_aware",
)
_AUTHORITY_PATHS = tuple(
    sorted(
        (
            "docs/evaluation/formal_evaluation_baseline_identity_correction_amendment.md",
            "docs/evaluation/formal_evaluation_pre_execution_amendment.md",
            "docs/evaluation/formal_evaluation_protocol.md",
            "docs/evaluation/formal_evaluation_stage_b4_plan.md",
            "evaluation/formal_evaluation_manifest.json",
            "evaluation/formal_qa_only_baseline_spec.json",
            "outputs/rag_answer_demo.py",
            "outputs/requirements.txt",
            "scripts/formal_evaluation_orchestration.py",
            "scripts/formal_evaluation_resource_preflight.py",
            "scripts/formal_evaluation_resource_preflight_worker.py",
            "scripts/formal_evaluation_runtime.py",
            "scripts/formal_evaluation_transport.py",
            "scripts/formal_qa_only_baseline/adapter.py",
            "scripts/formal_qa_only_baseline/vendor/rag_answer_demo_12136b7.py",
            "scripts/run_formal_evaluation.py",
        )
    )
)
_RESOURCE_COLUMNS = (
    "doc_id",
    "source_type",
    "category",
    "title",
    "text_for_embedding",
    "answer_or_content",
    "question",
    "answer",
    "priority",
    "allowed_for_answer",
    "needs_backend_api",
    "source_file",
    "session_id",
)
_QA_SOURCE_PATH = "data/processed/jd_final_safe_qa_refined_category.csv"
_SNIPPET_SOURCE_PATH = "data/processed/knowledge_snippets_v2_reviewed.csv"
_V1_CORPUS_PATH = "outputs/cache/v1_qa/qa_corpus.pkl"
_V1_EMBEDDINGS_PATH = "outputs/cache/v1_qa/qa_embeddings.npy"
_V2_CORPUS_PATH = "outputs/cache/v2_mixed/mixed_corpus_v2.pkl"
_V2_EMBEDDINGS_PATH = "outputs/cache/v2_mixed/mixed_embeddings_v2.npy"
_EVIDENCE_RELATIVE_ROOT = "data/formal_eval/resource_preflight"
_B2_RELATIVE_ROOT = "data/formal_eval/private_state"
_B3_RELATIVE_ROOT = "data/formal_eval/reviewer_projection"
_EVIDENCE_FILENAME = "production_resource_preflight_v1.json"
_LOCK_FILENAME = "run.lock"
_WORKER_INHERITED_ENV_NAMES = (
    "COMSPEC",
    "PATH",
    "PATHEXT",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "WINDIR",
)


class _PreflightError(RuntimeError):
    """A category-only error; underlying diagnostics never cross the boundary."""

    def __init__(self, category: str):
        if type(category) is not str or category not in _FAILURE_SET:
            category = "B4_INTERNAL_FAILURE"
        self.category = category
        super().__init__(category)


class _OfflineAttempt(RuntimeError):
    pass


@dataclass(frozen=True)
class ProductionResourcePreflightResultV1:
    schema_version: int
    action: str
    status: str
    preflight_sha256: str
    resource_identities: tuple["ProductionResourceIdentity", ...]

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or type(self.action) is not str
            or self.action not in {"created", "already_complete"}
            or type(self.status) is not str
            or self.status != _STATUS_PASSED
            or type(self.preflight_sha256) is not str
            or _SHA256_RE.fullmatch(self.preflight_sha256) is None
            or type(self.resource_identities) is not tuple
            or len(self.resource_identities) != 4
        ):
            raise _PreflightError("B4_INTERNAL_FAILURE")
        transport = _transport_authority()
        for identity in self.resource_identities:
            try:
                transport.validate_resource_identity(identity)
            except Exception as exc:
                raise _PreflightError("B4_INTERNAL_FAILURE") from exc


@dataclass(frozen=True)
class _PreflightPathsV1:
    repository_root: Path
    evidence_root: Path
    qa_source: Path
    snippet_source: Path
    v1_corpus: Path
    v1_embeddings: Path
    v2_corpus: Path
    v2_embeddings: Path
    model_cache_root: Path
    model_repository: Path
    authority_files: tuple[tuple[str, Path], ...]
    test_only: bool


@dataclass(frozen=True)
class _FileObservationV1:
    relative_path: str
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class _ModelObservationV1:
    revision: str
    snapshot_path: Path
    file_count: int
    total_bytes: int
    snapshot_sha256: str
    members: tuple[tuple[str, str, int, str], ...]


@dataclass(frozen=True)
class _WorkerProcessResultV1:
    returncode: int
    stdout: bytes
    timed_out: bool = False
    io_failed: bool = False


@dataclass(frozen=True)
class _FreshMaterialV1:
    artifact: Mapping[str, Any]
    artifact_bytes: bytes
    identities: tuple[object, ...]
    preflight_sha256: str


_PARENT_GUARD_LOCK = threading.Lock()
_PARENT_GUARD_DEPTH = 0
_PARENT_GUARD_ORIGINALS: tuple[object, object, object] | None = None
_PARENT_NETWORK_ATTEMPTS = 0


class _ParentOfflineGuard:
    def __enter__(self) -> "_ParentOfflineGuard":
        global _PARENT_GUARD_DEPTH, _PARENT_GUARD_ORIGINALS
        global _PARENT_NETWORK_ATTEMPTS
        with _PARENT_GUARD_LOCK:
            if _PARENT_GUARD_DEPTH == 0:
                _PARENT_NETWORK_ATTEMPTS = 0
                _PARENT_GUARD_ORIGINALS = (
                    socket.socket,
                    socket.create_connection,
                    socket.getaddrinfo,
                )

                def blocked(*_args: object, **_kwargs: object) -> object:
                    global _PARENT_NETWORK_ATTEMPTS
                    _PARENT_NETWORK_ATTEMPTS += 1
                    raise _OfflineAttempt()

                socket.socket = blocked  # type: ignore[assignment]
                socket.create_connection = blocked  # type: ignore[assignment]
                socket.getaddrinfo = blocked  # type: ignore[assignment]
            _PARENT_GUARD_DEPTH += 1
        return self

    def __exit__(self, _type: object, _value: object, _tb: object) -> None:
        global _PARENT_GUARD_DEPTH, _PARENT_GUARD_ORIGINALS
        with _PARENT_GUARD_LOCK:
            _PARENT_GUARD_DEPTH -= 1
            if _PARENT_GUARD_DEPTH == 0 and _PARENT_GUARD_ORIGINALS is not None:
                socket.socket = _PARENT_GUARD_ORIGINALS[0]  # type: ignore[assignment]
                socket.create_connection = _PARENT_GUARD_ORIGINALS[1]  # type: ignore[assignment]
                socket.getaddrinfo = _PARENT_GUARD_ORIGINALS[2]  # type: ignore[assignment]
                _PARENT_GUARD_ORIGINALS = None


def _transport_authority() -> Any:
    try:
        import formal_evaluation_transport as transport
    except Exception as exc:
        raise _PreflightError("B4_AUTHORITY_INVALID") from exc
    return transport


def _canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise _PreflightError("B4_INTERNAL_FAILURE") from exc


def _canonical_file_bytes(value: object) -> bytes:
    return _canonical_json_bytes(value) + b"\n"


def _ordinary_sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _require_sha(value: object, category: str = "B4_EVIDENCE_INVALID") -> str:
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise _PreflightError(category)
    return value


def _require_exact_int(
    value: object, lower: int, upper: int, category: str = "B4_EVIDENCE_INVALID"
) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise _PreflightError(category)
    return value


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result


def _reject_nonfinite(_value: str) -> None:
    raise ValueError("nonfinite")


def _recursive_limits(value: object, depth: int = 1) -> None:
    if depth > _JSON_DEPTH_MAXIMUM:
        raise _PreflightError("B4_EVIDENCE_INVALID")
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        if len(value.encode("utf-8")) > _JSON_STRING_BYTES_MAXIMUM:
            raise _PreflightError("B4_EVIDENCE_INVALID")
        return
    if type(value) is list:
        if len(value) > _JSON_ARRAY_MEMBERS_MAXIMUM:
            raise _PreflightError("B4_EVIDENCE_INVALID")
        for member in value:
            _recursive_limits(member, depth + 1)
        return
    if type(value) is dict:
        if len(value) > _JSON_MAPPING_MEMBERS_MAXIMUM:
            raise _PreflightError("B4_EVIDENCE_INVALID")
        for key, member in value.items():
            if type(key) is not str or len(key.encode("utf-8")) > _JSON_STRING_BYTES_MAXIMUM:
                raise _PreflightError("B4_EVIDENCE_INVALID")
            _recursive_limits(member, depth + 1)
        return
    raise _PreflightError("B4_EVIDENCE_INVALID")


def _load_canonical_json(raw: bytes, maximum: int, category: str) -> dict[str, Any]:
    if type(raw) is not bytes or not 0 < len(raw) <= maximum or not raw.endswith(b"\n"):
        raise _PreflightError(category)
    try:
        value = json.loads(
            raw[:-1].decode("utf-8"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise _PreflightError(category) from exc
    if type(value) is not dict:
        raise _PreflightError(category)
    try:
        _recursive_limits(value)
        canonical = _canonical_file_bytes(value)
    except _PreflightError as exc:
        raise _PreflightError(category) from exc
    if canonical != raw:
        raise _PreflightError(category)
    return value


def _validate_relative_path(value: object) -> str:
    if type(value) is not str or not value or len(value) > 240:
        raise _PreflightError("B4_AUTHORITY_INVALID")
    lowered = value.lower()
    if (
        "\\" in value
        or "%" in value
        or ":" in value
        or "\x00" in value
        or value.startswith(("/", "./", "../"))
        or value.endswith("/")
        or "//" in value
        or lowered.startswith(("file:", "http:", "https:"))
    ):
        raise _PreflightError("B4_PATH_UNSAFE")
    parts = value.split("/")
    if any(
        part in {"", ".", ".."} or _PATH_SEGMENT_RE.fullmatch(part) is None
        for part in parts
    ):
        raise _PreflightError("B4_PATH_UNSAFE")
    if PurePosixPath(value).as_posix() != value:
        raise _PreflightError("B4_PATH_UNSAFE")
    return value


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _paths_overlap(first: Path, second: Path) -> bool:
    return first == second or _is_within(first, second) or _is_within(second, first)


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise _PreflightError("B4_RESOURCE_MISSING") from exc
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _absolute_lexical(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise _PreflightError("B4_PATH_UNSAFE")
    raw = str(path)
    anchor = path.anchor
    if "\x00" in raw:
        raise _PreflightError("B4_PATH_UNSAFE")
    if os.name == "nt":
        reserved = {
            "con",
            "prn",
            "aux",
            "nul",
            "clock$",
            *(f"com{number}" for number in range(1, 10)),
            *(f"lpt{number}" for number in range(1, 10)),
        }
        if (
            anchor.startswith(("\\\\", "//", "\\\\?\\", "\\\\.\\"))
            or not path.drive
            or not anchor.endswith(("\\", "/"))
        ):
            raise _PreflightError("B4_PATH_UNSAFE")
        for part in path.parts[1:]:
            if (
                not part
                or part in {".", ".."}
                or part.endswith((" ", "."))
                or any(ord(character) < 32 for character in part)
                or part.casefold().split(".", 1)[0] in reserved
                or ":" in part
            ):
                raise _PreflightError("B4_PATH_UNSAFE")
    return Path(os.path.abspath(str(path)))


def _resolved(path: Path, *, strict: bool) -> Path:
    try:
        return path.resolve(strict=strict)
    except FileNotFoundError as exc:
        raise _PreflightError("B4_RESOURCE_MISSING") from exc
    except (OSError, RuntimeError) as exc:
        raise _PreflightError("B4_PATH_UNSAFE") from exc


def _validate_components_nonreparse(
    path: Path, floor: Path, *, allow_missing: bool = False
) -> None:
    path = _absolute_lexical(path)
    floor = _absolute_lexical(floor)
    if not _is_within(path, floor):
        raise _PreflightError("B4_PATH_UNSAFE")
    current = floor
    for part in (None, *path.relative_to(floor).parts):
        if part is not None:
            current = current / part
        try:
            current.lstat()
        except FileNotFoundError as exc:
            if allow_missing:
                return
            raise _PreflightError("B4_RESOURCE_MISSING") from exc
        except OSError as exc:
            raise _PreflightError("B4_IO_FAILURE") from exc
        if _is_reparse(current):
            raise _PreflightError("B4_PATH_UNSAFE")


def _filesystem_anchor(path: Path) -> Path:
    path = _absolute_lexical(path)
    anchor = Path(path.anchor)
    if not anchor.is_absolute():
        raise _PreflightError("B4_PATH_UNSAFE")
    return anchor


def _validate_regular_file(path: Path, floor: Path, maximum: int = _FILE_MAXIMUM) -> int:
    _validate_components_nonreparse(path, floor)
    try:
        if not path.is_file():
            raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
        info = path.stat()
    except _PreflightError:
        raise
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0 or info.st_size > maximum:
        raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
    return info.st_size


def _hash_regular_file(path: Path, floor: Path, relative_path: str) -> _FileObservationV1:
    size_before = _validate_regular_file(path, floor)
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as handle:
            while True:
                block = handle.read(1024 * 1024)
                if not block:
                    break
                total += len(block)
                if total > _FILE_MAXIMUM:
                    raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
                digest.update(block)
    except _PreflightError:
        raise
    except FileNotFoundError as exc:
        raise _PreflightError("B4_RESOURCE_MISSING") from exc
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc
    size_after = _validate_regular_file(path, floor)
    if total != size_before or size_after != size_before:
        raise _PreflightError("B4_RESOURCE_MUTATED")
    return _FileObservationV1(relative_path, total, digest.hexdigest())


def _resolve_model_cache_root() -> Path:
    allowed = (
        "SENTENCE_TRANSFORMERS_HOME",
        "HF_HUB_CACHE",
        "HUGGINGFACE_HUB_CACHE",
        "HF_HOME",
        "XDG_CACHE_HOME",
    )
    values = {name: os.environ.get(name, "") for name in allowed}
    if values["SENTENCE_TRANSFORMERS_HOME"]:
        selected = values["SENTENCE_TRANSFORMERS_HOME"]
    elif values["HF_HUB_CACHE"]:
        selected = values["HF_HUB_CACHE"]
    elif values["HUGGINGFACE_HUB_CACHE"]:
        selected = values["HUGGINGFACE_HUB_CACHE"]
    elif values["HF_HOME"]:
        selected = os.path.join(values["HF_HOME"], "hub")
    elif values["XDG_CACHE_HOME"]:
        selected = os.path.join(values["XDG_CACHE_HOME"], "huggingface", "hub")
    else:
        selected = os.path.expanduser("~/.cache/huggingface/hub")
    if not selected or "\x00" in selected or "://" in selected or "%" in selected:
        raise _PreflightError("B4_PATH_UNSAFE")
    candidate = Path(os.path.expanduser(selected))
    if not candidate.is_absolute():
        raise _PreflightError("B4_PATH_UNSAFE")
    return _absolute_lexical(candidate)


def _paths_from_roots(
    repository_root: Path,
    evidence_root: Path,
    model_cache_root: Path,
    *,
    test_only: bool,
) -> _PreflightPathsV1:
    repository_root = _absolute_lexical(repository_root)
    evidence_root = _absolute_lexical(evidence_root)
    model_cache_root = _absolute_lexical(model_cache_root)

    def joined(relative: str) -> Path:
        _validate_relative_path(relative)
        return repository_root.joinpath(*relative.split("/"))

    authority_files = tuple((relative, joined(relative)) for relative in _AUTHORITY_PATHS)
    return _PreflightPathsV1(
        repository_root=repository_root,
        evidence_root=evidence_root,
        qa_source=joined(_QA_SOURCE_PATH),
        snippet_source=joined(_SNIPPET_SOURCE_PATH),
        v1_corpus=joined(_V1_CORPUS_PATH),
        v1_embeddings=joined(_V1_EMBEDDINGS_PATH),
        v2_corpus=joined(_V2_CORPUS_PATH),
        v2_embeddings=joined(_V2_EMBEDDINGS_PATH),
        model_cache_root=model_cache_root,
        model_repository=model_cache_root / _MODEL_REPOSITORY_NAME,
        authority_files=authority_files,
        test_only=test_only,
    )


def _production_paths(repository_root: Path | None = None) -> _PreflightPathsV1:
    if repository_root is None:
        repository_root = Path(__file__).resolve().parents[1]
    return _paths_from_roots(
        repository_root,
        repository_root.joinpath(*_EVIDENCE_RELATIVE_ROOT.split("/")),
        _resolve_model_cache_root(),
        test_only=False,
    )


def _paths_for_tests(
    repository_root: Path, evidence_root: Path, model_cache_root: Path
) -> _PreflightPathsV1:
    return _paths_from_roots(
        repository_root, evidence_root, model_cache_root, test_only=True
    )


def _validate_path_bundle(paths: _PreflightPathsV1) -> None:
    if type(paths) is not _PreflightPathsV1 or type(paths.test_only) is not bool:
        raise _PreflightError("B4_PATH_UNSAFE")
    values = [
        paths.repository_root,
        paths.evidence_root,
        paths.qa_source,
        paths.snippet_source,
        paths.v1_corpus,
        paths.v1_embeddings,
        paths.v2_corpus,
        paths.v2_embeddings,
        paths.model_cache_root,
        paths.model_repository,
        *(path for _relative, path in paths.authority_files),
    ]
    if any(not isinstance(path, Path) or not path.is_absolute() for path in values):
        raise _PreflightError("B4_PATH_UNSAFE")
    if tuple(relative for relative, _path in paths.authority_files) != _AUTHORITY_PATHS:
        raise _PreflightError("B4_AUTHORITY_INVALID")
    expected = _paths_from_roots(
        paths.repository_root,
        paths.evidence_root,
        paths.model_cache_root,
        test_only=paths.test_only,
    )
    if paths != expected:
        raise _PreflightError("B4_PATH_UNSAFE")
    repository_anchor = _filesystem_anchor(paths.repository_root)
    model_anchor = _filesystem_anchor(paths.model_cache_root)
    evidence_anchor = _filesystem_anchor(paths.evidence_root)
    _validate_components_nonreparse(paths.repository_root, repository_anchor)
    _validate_components_nonreparse(paths.model_cache_root, model_anchor)
    _validate_components_nonreparse(
        paths.model_repository, paths.model_cache_root, allow_missing=True
    )
    _validate_components_nonreparse(
        paths.evidence_root, evidence_anchor, allow_missing=True
    )
    for path in (
        paths.qa_source,
        paths.snippet_source,
        paths.v1_corpus,
        paths.v1_embeddings,
        paths.v2_corpus,
        paths.v2_embeddings,
        *(path for _relative, path in paths.authority_files),
    ):
        _validate_components_nonreparse(
            path, paths.repository_root, allow_missing=True
        )
    for protected in (
        paths.repository_root.joinpath(*_B2_RELATIVE_ROOT.split("/")),
        paths.repository_root.joinpath(*_B3_RELATIVE_ROOT.split("/")),
    ):
        _validate_components_nonreparse(
            protected, paths.repository_root, allow_missing=True
        )
    roots = (
        paths.repository_root / "data" / "processed",
        paths.repository_root / "outputs" / "cache" / "v1_qa",
        paths.repository_root / "outputs" / "cache" / "v2_mixed",
        paths.model_cache_root,
        paths.evidence_root,
        paths.repository_root.joinpath(*_B2_RELATIVE_ROOT.split("/")),
        paths.repository_root.joinpath(*_B3_RELATIVE_ROOT.split("/")),
    )
    normalized = tuple(_absolute_lexical(root) for root in roots)
    for index, first in enumerate(normalized):
        for second in normalized[index + 1 :]:
            if _paths_overlap(first, second):
                raise _PreflightError("B4_PATH_UNSAFE")
    resolved_roots = tuple(_resolved(root, strict=False) for root in normalized)
    for index, first in enumerate(resolved_roots):
        for second in resolved_roots[index + 1 :]:
            if _paths_overlap(first, second):
                raise _PreflightError("B4_PATH_UNSAFE")
    expected_containment = (
        (paths.qa_source, paths.repository_root / "data" / "processed"),
        (paths.snippet_source, paths.repository_root / "data" / "processed"),
        (paths.v1_corpus, paths.repository_root / "outputs" / "cache" / "v1_qa"),
        (paths.v1_embeddings, paths.repository_root / "outputs" / "cache" / "v1_qa"),
        (paths.v2_corpus, paths.repository_root / "outputs" / "cache" / "v2_mixed"),
        (paths.v2_embeddings, paths.repository_root / "outputs" / "cache" / "v2_mixed"),
        (paths.model_repository, paths.model_cache_root),
        *( (path, paths.repository_root) for _relative, path in paths.authority_files ),
    )
    for target, expected_root in expected_containment:
        if not _is_within(
            _resolved(target, strict=False), _resolved(expected_root, strict=False)
        ):
            raise _PreflightError("B4_PATH_UNSAFE")
    if paths.test_only:
        temp_root = _resolved(Path(tempfile.gettempdir()), strict=True)
        protected_repo = Path(__file__).resolve().parents[1]
        for root in (paths.repository_root, paths.evidence_root, paths.model_cache_root):
            resolved = _resolved(root, strict=False)
            if resolved == temp_root or not _is_within(resolved, temp_root):
                raise _PreflightError("B4_PATH_UNSAFE")
            if _paths_overlap(resolved, protected_repo):
                raise _PreflightError("B4_PATH_UNSAFE")


def _validate_authority_contract(transport: Any) -> None:
    try:
        transport.validate_registry()
        expected = (
            (
                "qa_only_reconstructed_baseline",
                "qa_only_reconstructed_baseline",
                "v1_qa",
                5,
            ),
            ("v2", "current_v2", "v2_mixed", 10),
            ("single_turn", "v2_without_context_management", "v2_mixed", 10),
            ("context_aware", "v21b_context_aware", "v2_mixed", 10),
        )
        observed = tuple(
            (
                config,
                transport.formal_identity(config).formal_system_id,
                transport.formal_identity(config).resource_family,
                transport.formal_identity(config).top_k,
            )
            for config in _SYSTEM_CONFIG_ORDER
        )
    except Exception as exc:
        raise _PreflightError("B4_AUTHORITY_INVALID") from exc
    if observed != expected:
        raise _PreflightError("B4_AUTHORITY_INVALID")
    for relative in (
        _QA_SOURCE_PATH,
        _SNIPPET_SOURCE_PATH,
        _V1_CORPUS_PATH,
        _V1_EMBEDDINGS_PATH,
        _V2_CORPUS_PATH,
        _V2_EMBEDDINGS_PATH,
        *_AUTHORITY_PATHS,
    ):
        _validate_relative_path(relative)


def _discover_dependency_versions() -> tuple[dict[str, str], ...]:
    versions: list[dict[str, str]] = []
    python_version = platform.python_version()
    if sys.version_info[:2] != (3, 11) or _VERSION_RE.fullmatch(python_version) is None:
        raise _PreflightError("B4_DEPENDENCY_UNAVAILABLE")
    versions.append({"name": "python", "version": python_version})
    for distribution in _DISTRIBUTION_NAMES:
        try:
            version = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError as exc:
            raise _PreflightError("B4_DEPENDENCY_UNAVAILABLE") from exc
        except Exception as exc:
            raise _PreflightError("B4_DEPENDENCY_UNAVAILABLE") from exc
        if type(version) is not str or _VERSION_RE.fullmatch(version) is None:
            raise _PreflightError("B4_DEPENDENCY_UNAVAILABLE")
        versions.append({"name": distribution, "version": version})
    if tuple(item["name"] for item in versions) != _DEPENDENCY_NAMES:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    return tuple(versions)


def _validate_resource_paths(paths: _PreflightPathsV1) -> None:
    source_root = paths.repository_root / "data" / "processed"
    v1_root = paths.repository_root / "outputs" / "cache" / "v1_qa"
    v2_root = paths.repository_root / "outputs" / "cache" / "v2_mixed"
    for path, root in (
        (paths.qa_source, source_root),
        (paths.snippet_source, source_root),
        (paths.v1_corpus, v1_root),
        (paths.v1_embeddings, v1_root),
        (paths.v2_corpus, v2_root),
        (paths.v2_embeddings, v2_root),
    ):
        _validate_regular_file(path, paths.repository_root)
        if not _is_within(_resolved(path, strict=True), _resolved(root, strict=True)):
            raise _PreflightError("B4_PATH_UNSAFE")
    for relative, path in paths.authority_files:
        if path != paths.repository_root.joinpath(*relative.split("/")):
            raise _PreflightError("B4_AUTHORITY_INVALID")
        _validate_regular_file(path, paths.repository_root)
        if not _is_within(
            _resolved(path, strict=True),
            _resolved(paths.repository_root, strict=True),
        ):
            raise _PreflightError("B4_PATH_UNSAFE")
    _validate_components_nonreparse(
        paths.model_cache_root, _filesystem_anchor(paths.model_cache_root)
    )
    _validate_components_nonreparse(paths.model_repository, paths.model_cache_root)
    if not paths.model_repository.is_dir():
        raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
    if not _is_within(
        _resolved(paths.model_repository, strict=True),
        _resolved(paths.model_cache_root, strict=True),
    ):
        raise _PreflightError("B4_PATH_UNSAFE")


def _file_observations(paths: _PreflightPathsV1) -> dict[str, _FileObservationV1]:
    return {
        "qa_source": _hash_regular_file(
            paths.qa_source, paths.repository_root, _QA_SOURCE_PATH
        ),
        "snippet_source": _hash_regular_file(
            paths.snippet_source, paths.repository_root, _SNIPPET_SOURCE_PATH
        ),
        "v1_corpus": _hash_regular_file(
            paths.v1_corpus, paths.repository_root, _V1_CORPUS_PATH
        ),
        "v1_embeddings": _hash_regular_file(
            paths.v1_embeddings, paths.repository_root, _V1_EMBEDDINGS_PATH
        ),
        "v2_corpus": _hash_regular_file(
            paths.v2_corpus, paths.repository_root, _V2_CORPUS_PATH
        ),
        "v2_embeddings": _hash_regular_file(
            paths.v2_embeddings, paths.repository_root, _V2_EMBEDDINGS_PATH
        ),
    }


def _authority_observations(paths: _PreflightPathsV1) -> tuple[_FileObservationV1, ...]:
    return tuple(
        _hash_regular_file(path, paths.repository_root, relative)
        for relative, path in paths.authority_files
    )


def _authority_observations_from_root(
    repository_root: Path,
) -> tuple[_FileObservationV1, ...]:
    repository_root = _absolute_lexical(repository_root)
    return tuple(
        _hash_regular_file(
            repository_root.joinpath(*relative.split("/")),
            repository_root,
            relative,
        )
        for relative in _AUTHORITY_PATHS
    )


def _read_model_revision(paths: _PreflightPathsV1) -> str:
    refs = paths.model_repository / "refs"
    ref = refs / "main"
    _validate_components_nonreparse(ref, paths.model_repository)
    size = _validate_regular_file(ref, paths.model_repository, maximum=41)
    if size not in (40, 41):
        raise _PreflightError("B4_RESOURCE_MALFORMED")
    try:
        raw = ref.read_bytes()
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc
    if len(raw) == 41 and not raw.endswith(b"\n"):
        raise _PreflightError("B4_RESOURCE_MALFORMED")
    content = raw[:-1] if raw.endswith(b"\n") else raw
    try:
        revision = content.decode("ascii")
    except UnicodeError as exc:
        raise _PreflightError("B4_RESOURCE_MALFORMED") from exc
    if _REVISION_RE.fullmatch(revision) is None:
        raise _PreflightError("B4_RESOURCE_MALFORMED")
    return revision


def _hash_model_snapshot(paths: _PreflightPathsV1) -> _ModelObservationV1:
    revision = _read_model_revision(paths)
    snapshots_root = paths.model_repository / "snapshots"
    snapshot = snapshots_root / revision
    _validate_components_nonreparse(snapshot, paths.model_repository)
    if not snapshot.is_dir():
        raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
    repository_resolved = _resolved(paths.model_repository, strict=True)
    members: list[tuple[str, str, int, str]] = []

    def visit(directory: Path, prefix: PurePosixPath) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise _PreflightError("B4_IO_FAILURE") from exc
        for entry in entries:
            logical = prefix / entry.name
            logical_name = logical.as_posix()
            info = _model_entry_lstat(entry)
            reparse = stat.S_ISLNK(info.st_mode) or bool(
                getattr(info, "st_file_attributes", 0)
                & _FILE_ATTRIBUTE_REPARSE_POINT
            )
            if reparse:
                if not stat.S_ISLNK(info.st_mode):
                    raise _PreflightError("B4_PATH_UNSAFE")
                target = _model_link_target(entry)
                if not _is_within(target, repository_resolved):
                    raise _PreflightError("B4_PATH_UNSAFE")
                try:
                    target_info = target.lstat()
                except OSError as exc:
                    raise _PreflightError("B4_PATH_UNSAFE") from exc
                if (
                    not stat.S_ISREG(target_info.st_mode)
                    or stat.S_ISLNK(target_info.st_mode)
                    or bool(
                        getattr(target_info, "st_file_attributes", 0)
                        & _FILE_ATTRIBUTE_REPARSE_POINT
                    )
                ):
                    raise _PreflightError("B4_PATH_UNSAFE")
                physical = target
            elif stat.S_ISDIR(info.st_mode):
                visit(entry, logical)
                continue
            elif stat.S_ISREG(info.st_mode):
                physical = entry
            else:
                raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
            if len(members) >= _MODEL_FILE_MAXIMUM:
                raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
            try:
                size_before = physical.stat().st_size
            except OSError as exc:
                raise _PreflightError("B4_IO_FAILURE") from exc
            if size_before < 0 or size_before > _MODEL_BYTES_MAXIMUM:
                raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
            digest = hashlib.sha256()
            total = 0
            try:
                with physical.open("rb") as handle:
                    while True:
                        block = handle.read(1024 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > _MODEL_BYTES_MAXIMUM:
                            raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
                        digest.update(block)
            except _PreflightError:
                raise
            except OSError as exc:
                raise _PreflightError("B4_IO_FAILURE") from exc
            try:
                size_after = physical.stat().st_size
            except OSError as exc:
                raise _PreflightError("B4_IO_FAILURE") from exc
            if total != size_before or size_after != size_before:
                raise _PreflightError("B4_RESOURCE_MUTATED")
            physical_name = _resolved(physical, strict=True).relative_to(
                repository_resolved
            ).as_posix()
            members.append((logical_name, physical_name, total, digest.hexdigest()))

    visit(snapshot, PurePosixPath())
    members.sort(key=lambda item: item[0])
    total_bytes = sum(member[2] for member in members)
    if not members or len(members) > _MODEL_FILE_MAXIMUM or total_bytes > _MODEL_BYTES_MAXIMUM:
        raise _PreflightError("B4_RESOURCE_TYPE_INVALID")
    digest = hashlib.sha256(_MODEL_TREE_DOMAIN)
    for logical_name, _physical_name, size, file_hash in members:
        encoded = logical_name.encode("utf-8")
        digest.update(struct.pack(">Q", len(encoded)))
        digest.update(encoded)
        digest.update(struct.pack(">Q", size))
        digest.update(bytes.fromhex(file_hash))
    return _ModelObservationV1(
        revision=revision,
        snapshot_path=snapshot,
        file_count=len(members),
        total_bytes=total_bytes,
        snapshot_sha256=digest.hexdigest(),
        members=tuple(members),
    )


def _model_entry_lstat(path: Path) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc


def _model_link_target(path: Path) -> Path:
    return _resolved(path, strict=True)


def _legacy_combined_source_hash(qa_sha: str, snippet_sha: str) -> str:
    digest = hashlib.sha256()
    digest.update(Path(_QA_SOURCE_PATH).name.encode("utf-8"))
    digest.update(qa_sha.encode("ascii"))
    digest.update(Path(_SNIPPET_SOURCE_PATH).name.encode("utf-8"))
    digest.update(snippet_sha.encode("ascii"))
    return digest.hexdigest()


def _worker_environment(worker_root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in _WORKER_INHERITED_ENV_NAMES:
        value = os.environ.get(name)
        if type(value) is str and value:
            result[name] = value
    cache = worker_root / "cache"
    values = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
        "TOKENIZERS_PARALLELISM": "false",
        "TEMP": str(worker_root / "tmp"),
        "TMP": str(worker_root / "tmp"),
        "PYTHONPYCACHEPREFIX": str(worker_root / "pycache"),
        "HF_HOME": str(cache / "hf-home"),
        "HF_HUB_CACHE": str(cache / "hf-hub"),
        "TRANSFORMERS_CACHE": str(cache / "transformers"),
        "SENTENCE_TRANSFORMERS_HOME": str(cache / "sentence-transformers"),
        "TORCH_HOME": str(cache / "torch"),
        "XDG_CACHE_HOME": str(cache / "xdg"),
    }
    result.update(values)
    return result


def _bounded_process(
    command: Sequence[str], environment: Mapping[str, str], cwd: Path
) -> _WorkerProcessResultV1:
    process: subprocess.Popen[bytes] | None = None
    output = bytearray()
    overflow = False
    read_error = False
    try:
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if process.stdout is None:
            return _WorkerProcessResultV1(-1, b"", io_failed=True)

        def reader() -> None:
            nonlocal overflow, read_error
            try:
                while True:
                    block = process.stdout.read(4096)
                    if not block:
                        return
                    remaining = _WORKER_OUTPUT_MAXIMUM + 1 - len(output)
                    if remaining > 0:
                        output.extend(block[:remaining])
                    if len(output) > _WORKER_OUTPUT_MAXIMUM or len(block) > remaining:
                        overflow = True
                        process.stdout.close()
                        return
            except OSError:
                read_error = True

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        try:
            returncode = process.wait(timeout=_WORKER_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            thread.join(timeout=5.0)
            return _WorkerProcessResultV1(process.returncode or -1, bytes(output), timed_out=True)
        thread.join(timeout=5.0)
        if thread.is_alive() or overflow or read_error:
            if process.poll() is None:
                process.kill()
                process.wait()
            return _WorkerProcessResultV1(process.returncode or -1, bytes(output), io_failed=True)
        return _WorkerProcessResultV1(returncode, bytes(output))
    except (OSError, ValueError):
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        return _WorkerProcessResultV1(-1, bytes(output), io_failed=True)


def _default_worker_launcher(
    mode: str,
    paths: _PreflightPathsV1,
    model: _ModelObservationV1,
    observations: Mapping[str, _FileObservationV1],
) -> _WorkerProcessResultV1:
    if mode not in {"resource", "model"}:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    worker_script = Path(__file__).with_name(
        "formal_evaluation_resource_preflight_worker.py"
    ).resolve(strict=True)
    try:
        with tempfile.TemporaryDirectory(prefix="formal-evaluation-b4-worker-") as directory:
            worker_root = Path(directory).resolve(strict=True)
            for child in (
                worker_root / "tmp",
                worker_root / "pycache",
                worker_root / "cache",
            ):
                child.mkdir()
            command = [sys.executable, str(worker_script), mode, str(worker_root)]
            if mode == "resource":
                command.extend(
                    [
                        str(paths.v1_corpus),
                        str(paths.v1_embeddings),
                        str(paths.v2_corpus),
                        str(paths.v2_embeddings),
                        observations["qa_source"].sha256,
                        _legacy_combined_source_hash(
                            observations["qa_source"].sha256,
                            observations["snippet_source"].sha256,
                        ),
                    ]
                )
            else:
                command.append(str(model.snapshot_path))
            if any(len(argument.encode("utf-8")) > 4096 for argument in command):
                raise _PreflightError("B4_PATH_UNSAFE")
            return _bounded_process(command, _worker_environment(worker_root), worker_root)
    except _PreflightError:
        raise
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc


def _decode_worker_result(
    mode: str, process: _WorkerProcessResultV1
) -> Mapping[str, Any]:
    if type(process) is not _WorkerProcessResultV1:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    if (
        type(process.returncode) is not int
        or type(process.timed_out) is not bool
        or type(process.io_failed) is not bool
    ):
        raise _PreflightError("B4_INTERNAL_FAILURE")
    if process.timed_out or process.io_failed:
        raise _PreflightError("B4_IO_FAILURE")
    if not 0 < len(process.stdout) <= _WORKER_OUTPUT_MAXIMUM:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    try:
        value = _load_canonical_json(
            process.stdout, _WORKER_OUTPUT_MAXIMUM, "B4_INTERNAL_FAILURE"
        )
    except _PreflightError as exc:
        raise _PreflightError("B4_INTERNAL_FAILURE") from exc
    if process.returncode == 2:
        if set(value) != {"category", "schema_version", "status"}:
            raise _PreflightError("B4_INTERNAL_FAILURE")
        category = value.get("category")
        if (
            type(value.get("schema_version")) is not int
            or value.get("schema_version") != 1
            or value.get("status") != "failed"
            or type(category) is not str
            or category not in _WORKER_FAILURE_SET
        ):
            raise _PreflightError("B4_INTERNAL_FAILURE")
        raise _PreflightError(category)
    if process.returncode != 0:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    if set(value) != {"probe", "result", "schema_version", "status"}:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["status"] != "passed"
        or value["probe"] != mode
        or type(value["result"]) is not dict
    ):
        raise _PreflightError("B4_INTERNAL_FAILURE")
    return value["result"]


def _validate_resource_worker_result(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if type(value) is not dict or set(value) != {
        "families",
        "network_attempt_count",
        "v1_is_exact_v2_qa_prefix",
    }:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    if type(value["network_attempt_count"]) is not int:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    if value["network_attempt_count"] != 0:
        raise _PreflightError("B4_OFFLINE_VIOLATION")
    if value["v1_is_exact_v2_qa_prefix"] is not True:
        raise _PreflightError("B4_IDENTITY_MISMATCH")
    families = value["families"]
    if type(families) is not list or len(families) != 2:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    expected = (
        ("v1_qa", "v1_qa_only", "production_v1_qa_only", 15333, 15333, 0),
        ("v2_mixed", "v2_mixed", "production_v2_mixed", 15688, 15333, 355),
    )
    metadata_keys = {
        "allowed_for_answer_all_true",
        "cache_corpus_version",
        "columns",
        "doc_ids_unique",
        "index_kind",
        "logical_corpus_version",
        "model_name",
        "needs_backend_api_all_boolean",
        "nonempty_retrieval_text",
        "priority_values_runtime_compatible",
        "qa_count",
        "qa_priority_fixed_50",
        "row_count",
        "snippet_count",
        "source_partition_valid",
        "source_sha256",
    }
    embedding_keys = {
        "all_finite",
        "dimensions",
        "dtype",
        "rows",
        "unit_normalized",
    }
    for family, contract in zip(families, expected):
        cache, cache_version, logical_version, rows, qa, snippets = contract
        if type(family) is not dict or set(family) != {
            "cache_family",
            "corpus_metadata",
            "embeddings",
        }:
            raise _PreflightError("B4_INTERNAL_FAILURE")
        metadata = family["corpus_metadata"]
        embeddings = family["embeddings"]
        if (
            family["cache_family"] != cache
            or type(metadata) is not dict
            or set(metadata) != metadata_keys
            or type(embeddings) is not dict
            or set(embeddings) != embedding_keys
        ):
            raise _PreflightError("B4_INTERNAL_FAILURE")
        for name, exact in (
            ("row_count", rows),
            ("qa_count", qa),
            ("snippet_count", snippets),
        ):
            if type(metadata[name]) is not int or metadata[name] != exact:
                raise _PreflightError("B4_INTERNAL_FAILURE")
        for name, exact in (("dimensions", 384), ("rows", rows)):
            if type(embeddings[name]) is not int or embeddings[name] != exact:
                raise _PreflightError("B4_INTERNAL_FAILURE")
        for name in ("all_finite", "unit_normalized"):
            if embeddings[name] is not True:
                raise _PreflightError("B4_INTERNAL_FAILURE")
        if (
            metadata["cache_corpus_version"] != cache_version
            or metadata["logical_corpus_version"] != logical_version
            or metadata["columns"] != list(_RESOURCE_COLUMNS)
            or metadata["index_kind"] != "range_0_based_contiguous"
            or metadata["model_name"] != _MODEL_ID
            or metadata["row_count"] != rows
            or metadata["qa_count"] != qa
            or metadata["snippet_count"] != snippets
            or _SHA256_RE.fullmatch(str(metadata["source_sha256"])) is None
            or any(
                metadata[name] is not True
                for name in (
                    "allowed_for_answer_all_true",
                    "doc_ids_unique",
                    "needs_backend_api_all_boolean",
                    "nonempty_retrieval_text",
                    "priority_values_runtime_compatible",
                    "qa_priority_fixed_50",
                    "source_partition_valid",
                )
            )
            or embeddings != {
                "all_finite": True,
                "dimensions": 384,
                "dtype": "float32",
                "rows": rows,
                "unit_normalized": True,
            }
        ):
            raise _PreflightError("B4_INTERNAL_FAILURE")
    return value


def _validate_model_worker_result(value: Mapping[str, Any]) -> Mapping[str, Any]:
    expected_keys = {
        "backend",
        "dimensions",
        "local_only",
        "model_id",
        "network_attempt_count",
        "probe_all_finite",
        "probe_dtype",
        "probe_id",
        "probe_shape",
        "probe_unit_normalized",
        "runtime_cosine_probe_valid",
        "trust_remote_code",
    }
    if type(value) is not dict or set(value) != expected_keys:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    if type(value["network_attempt_count"]) is not int:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    if value["network_attempt_count"] != 0:
        raise _PreflightError("B4_OFFLINE_VIOLATION")
    if type(value["dimensions"]) is not int or value["dimensions"] != 384:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    for name in (
        "local_only",
        "probe_all_finite",
        "probe_unit_normalized",
        "runtime_cosine_probe_valid",
    ):
        if value[name] is not True:
            raise _PreflightError("B4_INTERNAL_FAILURE")
    if value["trust_remote_code"] is not False:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    shape = value["probe_shape"]
    if (
        type(shape) is not list
        or len(shape) != 2
        or type(shape[0]) is not int
        or type(shape[1]) is not int
        or shape != [1, 384]
    ):
        raise _PreflightError("B4_INTERNAL_FAILURE")
    expected = {
        "backend": "torch",
        "dimensions": 384,
        "local_only": True,
        "model_id": _MODEL_ID,
        "network_attempt_count": 0,
        "probe_all_finite": True,
        "probe_dtype": "float32",
        "probe_id": _MODEL_PROBE_ID,
        "probe_shape": [1, 384],
        "probe_unit_normalized": True,
        "runtime_cosine_probe_valid": True,
        "trust_remote_code": False,
    }
    if value != expected:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    return value


def _build_identities(
    transport: Any, observations: Mapping[str, _FileObservationV1]
) -> tuple[object, ...]:
    specs = {
        "qa_only_reconstructed_baseline": (
            "v1_qa",
            "production_v1_qa_only",
            _V1_CORPUS_PATH,
            _V1_EMBEDDINGS_PATH,
            observations["v1_corpus"].sha256,
            observations["v1_embeddings"].sha256,
            15333,
            15333,
            0,
        ),
        "v2": (
            "v2_mixed",
            "production_v2_mixed",
            _V2_CORPUS_PATH,
            _V2_EMBEDDINGS_PATH,
            observations["v2_corpus"].sha256,
            observations["v2_embeddings"].sha256,
            15688,
            15333,
            355,
        ),
        "single_turn": (
            "v2_mixed",
            "production_v2_mixed",
            _V2_CORPUS_PATH,
            _V2_EMBEDDINGS_PATH,
            observations["v2_corpus"].sha256,
            observations["v2_embeddings"].sha256,
            15688,
            15333,
            355,
        ),
        "context_aware": (
            "v2_mixed",
            "production_v2_mixed",
            _V2_CORPUS_PATH,
            _V2_EMBEDDINGS_PATH,
            observations["v2_corpus"].sha256,
            observations["v2_embeddings"].sha256,
            15688,
            15333,
            355,
        ),
    }
    result: list[object] = []
    try:
        for config in _SYSTEM_CONFIG_ORDER:
            identity = transport.formal_identity(config)
            (
                family,
                version,
                corpus_path,
                embeddings_path,
                corpus_sha,
                embeddings_sha,
                rows,
                qa,
                snippets,
            ) = specs[config]
            resource = transport.ProductionResourceIdentity(
                schema_version=1,
                resource_type="production_frozen",
                logical_resource_id=f"production_frozen_{family}_{version}",
                system_config_id=config,
                formal_system_id=identity.formal_system_id,
                corpus_path=corpus_path,
                embeddings_path=embeddings_path,
                corpus_sha256=corpus_sha,
                embeddings_sha256=embeddings_sha,
                cache_family=family,
                corpus_version=version,
                row_count=rows,
                qa_count=qa,
                snippet_count=snippets,
                embedding_model=_MODEL_ID,
                embedding_rows=rows,
                embedding_dimensions=384,
                synthetic=False,
            )
            transport.validate_resource_identity(resource)
            transport.resource_identity_sha256(resource)
            result.append(resource)
    except Exception as exc:
        raise _PreflightError("B4_IDENTITY_MISMATCH") from exc
    if len(result) != 4:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    v2_mappings = [item.to_dict() for item in result[1:]]
    physical_fields = (
        "corpus_path",
        "embeddings_path",
        "corpus_sha256",
        "embeddings_sha256",
        "cache_family",
        "corpus_version",
        "row_count",
        "qa_count",
        "snippet_count",
        "embedding_model",
        "embedding_rows",
        "embedding_dimensions",
    )
    if any(
        tuple(mapping[name] for name in physical_fields)
        != tuple(v2_mappings[0][name] for name in physical_fields)
        for mapping in v2_mappings[1:]
    ):
        raise _PreflightError("B4_IDENTITY_MISMATCH")
    return tuple(result)


def _artifact_without_hash(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in value if key != "preflight_sha256"}


def _preflight_sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _PREFLIGHT_DOMAIN + _canonical_json_bytes(_artifact_without_hash(value))
    ).hexdigest()


def _build_material(
    transport: Any,
    dependencies: tuple[dict[str, str], ...],
    authorities: tuple[_FileObservationV1, ...],
    observations: Mapping[str, _FileObservationV1],
    model: _ModelObservationV1,
    resource_result: Mapping[str, Any],
    model_result: Mapping[str, Any],
    identities: tuple[object, ...],
) -> _FreshMaterialV1:
    qa_sha = observations["qa_source"].sha256
    snippet_sha = observations["snippet_source"].sha256
    combined_sha = _legacy_combined_source_hash(qa_sha, snippet_sha)
    worker_families = resource_result["families"]
    if (
        worker_families[0]["corpus_metadata"]["source_sha256"] != qa_sha
        or worker_families[1]["corpus_metadata"]["source_sha256"] != combined_sha
    ):
        raise _PreflightError("B4_IDENTITY_MISMATCH")
    family_files = (
        (
            "v1_qa",
            observations["v1_corpus"],
            observations["v1_embeddings"],
            worker_families[0],
        ),
        (
            "v2_mixed",
            observations["v2_corpus"],
            observations["v2_embeddings"],
            worker_families[1],
        ),
    )
    resource_families: list[dict[str, Any]] = []
    for cache_family, corpus, embeddings, worker in family_files:
        resource_families.append(
            {
                "cache_family": cache_family,
                "corpus": {
                    "byte_count": corpus.byte_count,
                    "format": "pandas_pickle",
                    "path": corpus.relative_path,
                    "sha256": corpus.sha256,
                },
                "corpus_metadata": dict(worker["corpus_metadata"]),
                "embeddings": {
                    "all_finite": True,
                    "byte_count": embeddings.byte_count,
                    "dimensions": worker["embeddings"]["dimensions"],
                    "dtype": worker["embeddings"]["dtype"],
                    "format": "numpy_npy",
                    "path": embeddings.relative_path,
                    "rows": worker["embeddings"]["rows"],
                    "sha256": embeddings.sha256,
                    "unit_normalized": True,
                },
            }
        )
    resource_identities = [
        {
            "resource_identity": identity.to_dict(),
            "resource_identity_sha256": transport.resource_identity_sha256(identity),
        }
        for identity in identities
    ]
    artifact: dict[str, Any] = {
        "authority_files": [
            {
                "byte_count": item.byte_count,
                "path": item.relative_path,
                "sha256": item.sha256,
            }
            for item in authorities
        ],
        "checks": {
            "authority_files_unchanged": True,
            "client_construction_count": 0,
            "corpus_files_unchanged": True,
            "embedding_files_unchanged": True,
            "generation_call_count": 0,
            "model_snapshot_unchanged": True,
            "network_attempt_count": 0,
            "provider_call_count": 0,
            "runtime_cosine_probe_valid": model_result[
                "runtime_cosine_probe_valid"
            ],
            "source_files_unchanged": True,
            "v1_is_exact_v2_qa_prefix": resource_result[
                "v1_is_exact_v2_qa_prefix"
            ],
        },
        "contract_id": _CONTRACT_ID,
        "dependency_versions": [dict(item) for item in dependencies],
        "embedding_model": {
            "backend": model_result["backend"],
            "dimensions": model_result["dimensions"],
            "local_only": model_result["local_only"],
            "model_id": model_result["model_id"],
            "probe_all_finite": model_result["probe_all_finite"],
            "probe_dtype": model_result["probe_dtype"],
            "probe_id": model_result["probe_id"],
            "probe_shape": model_result["probe_shape"],
            "probe_unit_normalized": model_result["probe_unit_normalized"],
            "revision": model.revision,
            "snapshot_file_count": model.file_count,
            "snapshot_sha256": model.snapshot_sha256,
            "snapshot_total_bytes": model.total_bytes,
            "trust_remote_code": model_result["trust_remote_code"],
        },
        "resource_families": resource_families,
        "resource_identities": resource_identities,
        "schema_version": 1,
        "source_files": [
            {
                "byte_count": observations["qa_source"].byte_count,
                "id": "qa_source",
                "path": _QA_SOURCE_PATH,
                "role": "cleaned_qa_source",
                "sha256": qa_sha,
            },
            {
                "byte_count": observations["snippet_source"].byte_count,
                "id": "snippet_source",
                "path": _SNIPPET_SOURCE_PATH,
                "role": "reviewed_snippet_source",
                "sha256": snippet_sha,
            },
        ],
        "stage_id": _STAGE_ID,
        "status": _STATUS_PASSED,
    }
    artifact["preflight_sha256"] = _preflight_sha(artifact)
    _validate_artifact(artifact, transport)
    raw = _canonical_file_bytes(artifact)
    if len(raw) > _EVIDENCE_BYTES_MAXIMUM:
        raise _PreflightError("B4_INTERNAL_FAILURE")
    return _FreshMaterialV1(
        artifact=artifact,
        artifact_bytes=raw,
        identities=identities,
        preflight_sha256=artifact["preflight_sha256"],
    )


def _validate_artifact(value: Mapping[str, Any], transport: Any) -> None:
    top_keys = {
        "authority_files",
        "checks",
        "contract_id",
        "dependency_versions",
        "embedding_model",
        "preflight_sha256",
        "resource_families",
        "resource_identities",
        "schema_version",
        "source_files",
        "stage_id",
        "status",
    }
    if type(value) is not dict or set(value) != top_keys:
        raise _PreflightError("B4_EVIDENCE_INVALID")
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["contract_id"] != _CONTRACT_ID
        or value["stage_id"] != _STAGE_ID
        or value["status"] != _STATUS_PASSED
        or _require_sha(value["preflight_sha256"]) != _preflight_sha(value)
    ):
        raise _PreflightError("B4_EVIDENCE_INVALID")
    authority_files = value["authority_files"]
    if type(authority_files) is not list or len(authority_files) != len(_AUTHORITY_PATHS):
        raise _PreflightError("B4_EVIDENCE_INVALID")
    for entry, expected_path in zip(authority_files, _AUTHORITY_PATHS):
        if (
            type(entry) is not dict
            or set(entry) != {"byte_count", "path", "sha256"}
            or entry["path"] != expected_path
        ):
            raise _PreflightError("B4_EVIDENCE_INVALID")
        _require_exact_int(entry["byte_count"], 1, _FILE_MAXIMUM)
        _require_sha(entry["sha256"])
    dependencies = value["dependency_versions"]
    if type(dependencies) is not list or len(dependencies) != len(_DEPENDENCY_NAMES):
        raise _PreflightError("B4_EVIDENCE_INVALID")
    for entry, name in zip(dependencies, _DEPENDENCY_NAMES):
        if (
            type(entry) is not dict
            or set(entry) != {"name", "version"}
            or entry["name"] != name
            or type(entry["version"]) is not str
            or _VERSION_RE.fullmatch(entry["version"]) is None
        ):
            raise _PreflightError("B4_EVIDENCE_INVALID")
    sources = value["source_files"]
    source_expected = (
        ("qa_source", _QA_SOURCE_PATH, "cleaned_qa_source"),
        ("snippet_source", _SNIPPET_SOURCE_PATH, "reviewed_snippet_source"),
    )
    if type(sources) is not list or len(sources) != 2:
        raise _PreflightError("B4_EVIDENCE_INVALID")
    source_hashes: dict[str, str] = {}
    for entry, expected in zip(sources, source_expected):
        if (
            type(entry) is not dict
            or set(entry) != {"byte_count", "id", "path", "role", "sha256"}
            or (entry["id"], entry["path"], entry["role"]) != expected
        ):
            raise _PreflightError("B4_EVIDENCE_INVALID")
        _require_exact_int(entry["byte_count"], 1, _FILE_MAXIMUM)
        source_hashes[entry["id"]] = _require_sha(entry["sha256"])
    family_specs = (
        (
            "v1_qa",
            _V1_CORPUS_PATH,
            _V1_EMBEDDINGS_PATH,
            "v1_qa_only",
            "production_v1_qa_only",
            15333,
            15333,
            0,
            source_hashes["qa_source"],
        ),
        (
            "v2_mixed",
            _V2_CORPUS_PATH,
            _V2_EMBEDDINGS_PATH,
            "v2_mixed",
            "production_v2_mixed",
            15688,
            15333,
            355,
            _legacy_combined_source_hash(
                source_hashes["qa_source"], source_hashes["snippet_source"]
            ),
        ),
    )
    families = value["resource_families"]
    if type(families) is not list or len(families) != 2:
        raise _PreflightError("B4_EVIDENCE_INVALID")
    family_hashes: dict[str, tuple[str, str]] = {}
    metadata_keys = {
        "allowed_for_answer_all_true",
        "cache_corpus_version",
        "columns",
        "doc_ids_unique",
        "index_kind",
        "logical_corpus_version",
        "model_name",
        "needs_backend_api_all_boolean",
        "nonempty_retrieval_text",
        "priority_values_runtime_compatible",
        "qa_count",
        "qa_priority_fixed_50",
        "row_count",
        "snippet_count",
        "source_partition_valid",
        "source_sha256",
    }
    for family, spec in zip(families, family_specs):
        cache, corpus_path, embeddings_path, core_version, logical_version, rows, qa, snippets, source_sha = spec
        if type(family) is not dict or set(family) != {
            "cache_family",
            "corpus",
            "corpus_metadata",
            "embeddings",
        } or family["cache_family"] != cache:
            raise _PreflightError("B4_EVIDENCE_INVALID")
        corpus = family["corpus"]
        embeddings = family["embeddings"]
        metadata = family["corpus_metadata"]
        if (
            type(corpus) is not dict
            or set(corpus) != {"byte_count", "format", "path", "sha256"}
            or corpus["format"] != "pandas_pickle"
            or corpus["path"] != corpus_path
            or type(embeddings) is not dict
            or set(embeddings)
            != {
                "all_finite",
                "byte_count",
                "dimensions",
                "dtype",
                "format",
                "path",
                "rows",
                "sha256",
                "unit_normalized",
            }
            or embeddings["format"] != "numpy_npy"
            or embeddings["path"] != embeddings_path
            or embeddings["dtype"] != "float32"
            or embeddings["rows"] != rows
            or embeddings["dimensions"] != 384
            or embeddings["all_finite"] is not True
            or embeddings["unit_normalized"] is not True
            or type(metadata) is not dict
            or set(metadata) != metadata_keys
            or metadata["cache_corpus_version"] != core_version
            or metadata["logical_corpus_version"] != logical_version
            or metadata["columns"] != list(_RESOURCE_COLUMNS)
            or metadata["index_kind"] != "range_0_based_contiguous"
            or metadata["model_name"] != _MODEL_ID
            or metadata["row_count"] != rows
            or metadata["qa_count"] != qa
            or metadata["snippet_count"] != snippets
            or metadata["source_sha256"] != source_sha
            or any(
                metadata[name] is not True
                for name in (
                    "allowed_for_answer_all_true",
                    "doc_ids_unique",
                    "needs_backend_api_all_boolean",
                    "nonempty_retrieval_text",
                    "priority_values_runtime_compatible",
                    "qa_priority_fixed_50",
                    "source_partition_valid",
                )
            )
        ):
            raise _PreflightError("B4_EVIDENCE_INVALID")
        for name, exact in (
            ("row_count", rows),
            ("qa_count", qa),
            ("snippet_count", snippets),
        ):
            _require_exact_int(metadata[name], exact, exact)
        _require_exact_int(embeddings["rows"], rows, rows)
        _require_exact_int(embeddings["dimensions"], 384, 384)
        _require_exact_int(corpus["byte_count"], 1, _FILE_MAXIMUM)
        _require_exact_int(embeddings["byte_count"], 1, _FILE_MAXIMUM)
        family_hashes[cache] = (_require_sha(corpus["sha256"]), _require_sha(embeddings["sha256"]))
    model = value["embedding_model"]
    if type(model) is not dict or set(model) != {
        "backend",
        "dimensions",
        "local_only",
        "model_id",
        "probe_all_finite",
        "probe_dtype",
        "probe_id",
        "probe_shape",
        "probe_unit_normalized",
        "revision",
        "snapshot_file_count",
        "snapshot_sha256",
        "snapshot_total_bytes",
        "trust_remote_code",
    }:
        raise _PreflightError("B4_EVIDENCE_INVALID")
    if (
        model["backend"] != "torch"
        or type(model["dimensions"]) is not int
        or model["dimensions"] != 384
        or model["local_only"] is not True
        or model["model_id"] != _MODEL_ID
        or model["probe_all_finite"] is not True
        or model["probe_dtype"] != "float32"
        or model["probe_id"] != _MODEL_PROBE_ID
        or type(model["probe_shape"]) is not list
        or len(model["probe_shape"]) != 2
        or type(model["probe_shape"][0]) is not int
        or type(model["probe_shape"][1]) is not int
        or model["probe_shape"] != [1, 384]
        or model["probe_unit_normalized"] is not True
        or type(model["revision"]) is not str
        or _REVISION_RE.fullmatch(model["revision"]) is None
        or model["trust_remote_code"] is not False
    ):
        raise _PreflightError("B4_EVIDENCE_INVALID")
    _require_exact_int(model["snapshot_file_count"], 1, _MODEL_FILE_MAXIMUM)
    _require_exact_int(model["snapshot_total_bytes"], 1, _MODEL_BYTES_MAXIMUM)
    _require_sha(model["snapshot_sha256"])
    checks = value["checks"]
    check_keys = {
        "authority_files_unchanged",
        "client_construction_count",
        "corpus_files_unchanged",
        "embedding_files_unchanged",
        "generation_call_count",
        "model_snapshot_unchanged",
        "network_attempt_count",
        "provider_call_count",
        "runtime_cosine_probe_valid",
        "source_files_unchanged",
        "v1_is_exact_v2_qa_prefix",
    }
    if type(checks) is not dict or set(checks) != check_keys:
        raise _PreflightError("B4_EVIDENCE_INVALID")
    for name in (
        "authority_files_unchanged",
        "corpus_files_unchanged",
        "embedding_files_unchanged",
        "model_snapshot_unchanged",
        "runtime_cosine_probe_valid",
        "source_files_unchanged",
        "v1_is_exact_v2_qa_prefix",
    ):
        if checks[name] is not True:
            raise _PreflightError("B4_EVIDENCE_INVALID")
    for name in (
        "client_construction_count",
        "generation_call_count",
        "network_attempt_count",
        "provider_call_count",
    ):
        if type(checks[name]) is not int or checks[name] != 0:
            raise _PreflightError("B4_EVIDENCE_INVALID")
    identities = value["resource_identities"]
    if type(identities) is not list or len(identities) != 4:
        raise _PreflightError("B4_EVIDENCE_INVALID")
    for entry, config in zip(identities, _SYSTEM_CONFIG_ORDER):
        if type(entry) is not dict or set(entry) != {
            "resource_identity",
            "resource_identity_sha256",
        }:
            raise _PreflightError("B4_EVIDENCE_INVALID")
        identity_mapping = entry["resource_identity"]
        if type(identity_mapping) is not dict:
            raise _PreflightError("B4_EVIDENCE_INVALID")
        for name, lower, upper in (
            ("schema_version", 1, 1),
            ("row_count", 1, _FILE_MAXIMUM),
            ("qa_count", 0, _FILE_MAXIMUM),
            ("snippet_count", 0, _FILE_MAXIMUM),
            ("embedding_rows", 1, _FILE_MAXIMUM),
            ("embedding_dimensions", 1, _FILE_MAXIMUM),
        ):
            if name not in identity_mapping:
                raise _PreflightError("B4_EVIDENCE_INVALID")
            _require_exact_int(identity_mapping[name], lower, upper)
        try:
            resource = transport.ProductionResourceIdentity.from_mapping(
                identity_mapping
            )
            transport.validate_resource_identity(resource)
            identity_hash = transport.resource_identity_sha256(resource)
        except Exception as exc:
            raise _PreflightError("B4_EVIDENCE_INVALID") from exc
        expected_family = "v1_qa" if config == _SYSTEM_CONFIG_ORDER[0] else "v2_mixed"
        corpus_sha, embeddings_sha = family_hashes[expected_family]
        if (
            resource.system_config_id != config
            or resource.cache_family != expected_family
            or resource.corpus_sha256 != corpus_sha
            or resource.embeddings_sha256 != embeddings_sha
            or entry["resource_identity_sha256"] != identity_hash
        ):
            raise _PreflightError("B4_EVIDENCE_INVALID")


def _read_existing_artifact(path: Path, transport: Any) -> tuple[bytes, dict[str, Any]]:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or bool(
                getattr(info, "st_file_attributes", 0)
                & _FILE_ATTRIBUTE_REPARSE_POINT
            )
            or not stat.S_ISREG(info.st_mode)
        ):
            raise _PreflightError("B4_PATH_UNSAFE")
        if info.st_size <= 0 or info.st_size > _EVIDENCE_BYTES_MAXIMUM:
            raise _PreflightError("B4_EVIDENCE_INVALID")
        with path.open("rb") as handle:
            raw = handle.read(_EVIDENCE_BYTES_MAXIMUM + 1)
    except _PreflightError:
        raise
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc
    if len(raw) > _EVIDENCE_BYTES_MAXIMUM or len(raw) != info.st_size:
        raise _PreflightError("B4_EVIDENCE_INVALID")
    value = _load_canonical_json(raw, _EVIDENCE_BYTES_MAXIMUM, "B4_EVIDENCE_INVALID")
    _validate_artifact(value, transport)
    return raw, value


def _scan_evidence_layout(
    root: Path,
    transport: Any,
    *,
    allow_missing: bool,
    lock: "_EvidenceLock | None" = None,
) -> tuple[bytes, dict[str, Any]] | None:
    _validate_components_nonreparse(
        root, _filesystem_anchor(root), allow_missing=True
    )
    if not root.exists():
        if allow_missing:
            return None
        raise _PreflightError("B4_PATH_UNSAFE")
    if _is_reparse(root) or not root.is_dir():
        raise _PreflightError("B4_PATH_UNSAFE")
    final: Path | None = None
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc
    for entry in entries:
        if _is_reparse(entry):
            raise _PreflightError("B4_PATH_UNSAFE")
        if entry.name == _LOCK_FILENAME:
            try:
                lock_info = entry.lstat()
            except OSError as exc:
                raise _PreflightError("B4_IO_FAILURE") from exc
            if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_size != 1:
                raise _PreflightError("B4_PATH_UNSAFE")
            try:
                if lock is None:
                    with entry.open("rb") as handle:
                        lock_bytes = handle.read(2)
                else:
                    lock.require_active()
                    if entry != lock.path or lock.handle is None:
                        raise _PreflightError("B4_LOCK_BUSY")
                    lock.handle.seek(0)
                    lock_bytes = lock.handle.read(2)
                if lock_bytes != b"\x00":
                    raise _PreflightError("B4_PATH_UNSAFE")
            except _PreflightError:
                raise
            except OSError as exc:
                raise _PreflightError("B4_IO_FAILURE") from exc
        elif entry.name == _EVIDENCE_FILENAME:
            if not entry.is_file():
                raise _PreflightError("B4_PATH_UNSAFE")
            final = entry
        elif _TEMP_RE.fullmatch(entry.name) is not None:
            if not entry.is_file():
                raise _PreflightError("B4_PATH_UNSAFE")
        else:
            raise _PreflightError("B4_PATH_UNSAFE")
    return _read_existing_artifact(final, transport) if final is not None else None


_LEASED_B4_LOCKS: set[str] = set()
_LEASED_B4_LOCKS_GUARD = threading.Lock()


class _EvidenceLock:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / _LOCK_FILENAME
        self.handle: Any = None
        self.locked = False
        self.pid: int | None = None
        self.thread_id: int | None = None
        self.registry_key: str | None = None

    def __enter__(self) -> "_EvidenceLock":
        if os.name != "nt":
            raise _PreflightError("B4_PLATFORM_UNSUPPORTED")
        try:
            import msvcrt
        except ImportError as exc:
            raise _PreflightError("B4_PLATFORM_UNSUPPORTED") from exc
        if not self.root.exists() or _is_reparse(self.root) or not self.root.is_dir():
            raise _PreflightError("B4_PATH_UNSAFE")
        if not self.path.exists():
            try:
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_BINARY,
                )
                try:
                    if os.write(descriptor, b"\x00") != 1:
                        raise _PreflightError("B4_IO_FAILURE")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except FileExistsError:
                pass
            except _PreflightError:
                raise
            except OSError as exc:
                raise _PreflightError("B4_IO_FAILURE") from exc
        if _is_reparse(self.path) or not self.path.is_file():
            raise _PreflightError("B4_PATH_UNSAFE")
        try:
            self.handle = self.path.open("r+b", buffering=0)
        except OSError as exc:
            raise _PreflightError("B4_IO_FAILURE") from exc
        key = str(self.path).casefold()
        with _LEASED_B4_LOCKS_GUARD:
            if key in _LEASED_B4_LOCKS:
                self.handle.close()
                self.handle = None
                raise _PreflightError("B4_LOCK_BUSY")
            _LEASED_B4_LOCKS.add(key)
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
                        raise _PreflightError("B4_LOCK_BUSY") from exc
                    time.sleep(0.05)
            self.pid = os.getpid()
            self.thread_id = threading.get_ident()
            self.handle.seek(0)
            if self.handle.read(2) != b"\x00" or _is_reparse(self.path):
                raise _PreflightError("B4_PATH_UNSAFE")
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
                with _LEASED_B4_LOCKS_GUARD:
                    _LEASED_B4_LOCKS.discard(self.registry_key)
                self.registry_key = None

    def require_active(self) -> None:
        if (
            type(self) is not _EvidenceLock
            or not self.locked
            or self.handle is None
            or self.pid != os.getpid()
            or self.thread_id != threading.get_ident()
        ):
            raise _PreflightError("B4_LOCK_BUSY")


def _ensure_evidence_root(root: Path) -> None:
    root = _absolute_lexical(root)
    anchor = _filesystem_anchor(root)
    _validate_components_nonreparse(root, anchor, allow_missing=True)
    if root.exists():
        if _is_reparse(root) or not root.is_dir():
            raise _PreflightError("B4_PATH_UNSAFE")
        _validate_components_nonreparse(root, anchor)
        return
    missing: list[Path] = []
    current = root
    while not current.exists():
        missing.append(current)
        if current == anchor:
            raise _PreflightError("B4_PATH_UNSAFE")
        current = current.parent
    _validate_components_nonreparse(current, anchor)
    created: list[Path] = []
    try:
        for path in reversed(missing):
            try:
                path.mkdir()
                created.append(path)
            except FileExistsError:
                pass
            if _is_reparse(path) or not path.is_dir():
                raise _PreflightError("B4_PATH_UNSAFE")
            _validate_components_nonreparse(path, anchor)
    except _PreflightError:
        for path in reversed(created):
            try:
                path.rmdir()
            except OSError:
                pass
        raise
    except OSError as exc:
        for path in reversed(created):
            try:
                path.rmdir()
            except OSError:
                pass
        raise _PreflightError("B4_IO_FAILURE") from exc
    _validate_components_nonreparse(root, anchor)


def _move_file_create_only(source: Path, target: Path) -> None:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        function = kernel32.MoveFileExW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
        function.restype = ctypes.c_int
    except (AttributeError, OSError) as exc:
        raise _PreflightError("B4_PLATFORM_UNSUPPORTED") from exc
    if not function(str(source), str(target), _MOVEFILE_WRITE_THROUGH):
        error = ctypes.get_last_error()
        if error in {80, 183}:
            raise FileExistsError()
        raise _PreflightError("B4_IO_FAILURE")


def _clean_owned_temps(root: Path, lock: _EvidenceLock) -> None:
    lock.require_active()
    try:
        entries = list(root.iterdir())
    except OSError as exc:
        raise _PreflightError("B4_IO_FAILURE") from exc
    for path in entries:
        if _TEMP_RE.fullmatch(path.name) is not None:
            if _is_reparse(path) or not path.is_file():
                raise _PreflightError("B4_PATH_UNSAFE")
            try:
                path.unlink()
            except OSError as exc:
                raise _PreflightError("B4_IO_FAILURE") from exc


def _classify_existing(
    root: Path, expected: bytes, transport: Any
) -> str | None:
    final = root / _EVIDENCE_FILENAME
    if not final.exists():
        return None
    raw, _value = _read_existing_artifact(final, transport)
    if raw == expected:
        return "already_complete"
    raise _PreflightError("B4_EVIDENCE_STALE")


def _publish_candidate(
    root: Path,
    expected: bytes,
    transport: Any,
    *,
    fault: Callable[[str], None] | None = None,
) -> str:
    _ensure_evidence_root(root)
    with _EvidenceLock(root) as lock:
        _scan_evidence_layout(root, transport, allow_missing=False, lock=lock)
        _clean_owned_temps(root, lock)
        existing = _classify_existing(root, expected, transport)
        if existing is not None:
            return existing
        temporary = root / f".{_EVIDENCE_FILENAME}.{os.urandom(16).hex()}.tmp"
        if _TEMP_RE.fullmatch(temporary.name) is None:
            raise _PreflightError("B4_INTERNAL_FAILURE")
        handle: Any = None
        try:
            handle = temporary.open("xb", buffering=0)
            if fault is not None:
                fault("after_open")
            written = handle.write(expected)
            if written != len(expected):
                raise _PreflightError("B4_IO_FAILURE")
            if fault is not None:
                fault("after_write")
            handle.flush()
            if fault is not None:
                fault("after_flush")
            os.fsync(handle.fileno())
            if fault is not None:
                fault("after_fsync")
            handle.close()
            handle = None
            if fault is not None:
                fault("after_close")
            if fault is not None:
                fault("before_move")
            try:
                _move_file_create_only(temporary, root / _EVIDENCE_FILENAME)
            except FileExistsError:
                existing = _classify_existing(root, expected, transport)
                if temporary.exists():
                    temporary.unlink()
                if existing is None:
                    raise _PreflightError("B4_IO_FAILURE")
                return existing
            if fault is not None:
                fault("after_move")
        except _PreflightError:
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
            raise
        except OSError as exc:
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
            raise _PreflightError("B4_IO_FAILURE") from exc
        final = root / _EVIDENCE_FILENAME
        if fault is not None:
            fault("before_readback")
        raw, _value = _read_existing_artifact(final, transport)
        if raw != expected:
            raise _PreflightError("B4_IO_FAILURE")
        if fault is not None:
            fault("after_readback")
        return "created"


def _preflight_with_paths(
    paths: _PreflightPathsV1 | None,
    worker_launcher: Callable[
        [str, _PreflightPathsV1, _ModelObservationV1, Mapping[str, _FileObservationV1]],
        _WorkerProcessResultV1,
    ] = _default_worker_launcher,
    *,
    publication_fault: Callable[[str], None] | None = None,
) -> ProductionResourcePreflightResultV1:
    if os.name != "nt":
        raise _PreflightError("B4_PLATFORM_UNSUPPORTED")
    if paths is not None and type(paths) is not _PreflightPathsV1:
        raise _PreflightError("B4_PATH_UNSAFE")
    if not callable(worker_launcher):
        raise _PreflightError("B4_INTERNAL_FAILURE")
    with _ParentOfflineGuard():
        try:
            transport = _transport_authority()
            _validate_authority_contract(transport)
            if paths is None:
                repository_root = _absolute_lexical(Path(__file__).resolve().parents[1])
                paths = _production_paths(repository_root)
            _validate_path_bundle(paths)
            authorities_first = _authority_observations(paths)
            _scan_evidence_layout(paths.evidence_root, transport, allow_missing=True)
            _validate_resource_paths(paths)
            dependencies = _discover_dependency_versions()
            observations_first = _file_observations(paths)
            model_first = _hash_model_snapshot(paths)
            resource_process = worker_launcher(
                "resource", paths, model_first, observations_first
            )
            resource_result = _validate_resource_worker_result(
                _decode_worker_result("resource", resource_process)
            )
            model_process = worker_launcher("model", paths, model_first, observations_first)
            model_result = _validate_model_worker_result(
                _decode_worker_result("model", model_process)
            )
            identities = _build_identities(transport, observations_first)
            _validate_resource_paths(paths)
            authorities_second = _authority_observations(paths)
            observations_second = _file_observations(paths)
            model_second = _hash_model_snapshot(paths)
            if (
                authorities_first != authorities_second
                or observations_first != observations_second
                or model_first != model_second
            ):
                raise _PreflightError("B4_RESOURCE_MUTATED")
            if _PARENT_NETWORK_ATTEMPTS != 0:
                raise _PreflightError("B4_OFFLINE_VIOLATION")
            material = _build_material(
                transport,
                dependencies,
                authorities_first,
                observations_first,
                model_first,
                resource_result,
                model_result,
                identities,
            )
            action = _publish_candidate(
                paths.evidence_root,
                material.artifact_bytes,
                transport,
                fault=publication_fault,
            )
            if _PARENT_NETWORK_ATTEMPTS != 0:
                raise _PreflightError("B4_OFFLINE_VIOLATION")
            return ProductionResourcePreflightResultV1(
                schema_version=1,
                action=action,
                status=_STATUS_PASSED,
                preflight_sha256=material.preflight_sha256,
                resource_identities=tuple(material.identities),
            )
        except _OfflineAttempt as exc:
            raise _PreflightError("B4_OFFLINE_VIOLATION") from exc
        except _PreflightError as exc:
            if _PARENT_NETWORK_ATTEMPTS:
                raise _PreflightError("B4_OFFLINE_VIOLATION") from exc
            raise
        except Exception as exc:
            if _PARENT_NETWORK_ATTEMPTS:
                raise _PreflightError("B4_OFFLINE_VIOLATION") from exc
            raise _PreflightError("B4_INTERNAL_FAILURE") from exc


def preflight_production_resources() -> ProductionResourcePreflightResultV1:
    """Validate and publish the fixed production snapshot observational evidence."""

    return _preflight_with_paths(None)


def _success_line(result: ProductionResourcePreflightResultV1) -> bytes:
    return _canonical_file_bytes(
        {
            "action": result.action,
            "family_count": 2,
            "preflight_sha256": result.preflight_sha256,
            "schema_version": 1,
            "status": "passed",
            "system_count": 4,
        }
    )


class _SilentArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise _PreflightError("B4_AUTHORITY_INVALID")


def _parser() -> argparse.ArgumentParser:
    return _SilentArgumentParser(
        description="Offline Stage B4 production-resource preflight."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        parser.parse_args(list(argv) if argv is not None else None)
    except _PreflightError as exc:
        sys.stderr.write(exc.category + "\n")
        return 2
    except SystemExit as exc:
        return int(exc.code)
    try:
        result = preflight_production_resources()
    except _PreflightError as exc:
        sys.stderr.write(exc.category + "\n")
        return 2
    sys.stdout.buffer.write(_success_line(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
