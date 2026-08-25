"""Private scrubbed worker for the Stage B4 resource and model probes.

Importing this module is standard-library-only.  Optional data/model imports
occur only after the worker controls are established inside ``_execute``.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import re
import socket
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


sys.dont_write_bytecode = True

_MODEL_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_MODEL_PROBE_ID = "formal-evaluation-b4-offline-probe-v1"
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
_QA_SOURCE_FILE = "jd_final_safe_qa_refined_category.csv"
_SNIPPET_SOURCE_FILE = "knowledge_snippets_v2_reviewed.csv"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_OUTPUT_MAXIMUM = 32_768
_KNOWN_FAILURES = frozenset(
    {
        "B4_DEPENDENCY_UNAVAILABLE",
        "B4_RESOURCE_MALFORMED",
        "B4_RESOURCE_INCOMPATIBLE",
        "B4_IDENTITY_MISMATCH",
        "B4_OFFLINE_VIOLATION",
    }
)
_FORBIDDEN_ENV_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "deepseek",
    "dotenv",
    "openai",
    "password",
    "proxy",
    "secret",
    "token",
)
_ESSENTIAL_ENV_KEYS = frozenset(
    {"comspec", "path", "pathext", "systemdrive", "systemroot", "windir"}
)
_OFFLINE_ENV = {
    "PYTHONDONTWRITEBYTECODE": "1",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
    "TOKENIZERS_PARALLELISM": "false",
}
_CONTROL_ENV_KEYS = frozenset(
    {
        *(_ESSENTIAL_ENV_KEYS),
        *(key.casefold() for key in _OFFLINE_ENV),
        "temp",
        "tmp",
        "pythonpycacheprefix",
        "hf_home",
        "hf_hub_cache",
        "transformers_cache",
        "sentence_transformers_home",
        "torch_home",
        "xdg_cache_home",
    }
)


class _WorkerFailure(RuntimeError):
    def __init__(self, category: str):
        if category not in _KNOWN_FAILURES:
            category = "B4_RESOURCE_MALFORMED"
        self.category = category
        super().__init__(category)


class _OfflineAttempt(RuntimeError):
    pass


class _BoundedDiscard(io.TextIOBase):
    def __init__(self, maximum: int = _OUTPUT_MAXIMUM):
        self.maximum = maximum
        self.count = 0

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        if type(value) is not str:
            value = str(value)
        size = len(value.encode("utf-8", errors="replace"))
        self.count += size
        if self.count > self.maximum:
            raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
        return len(value)

    def flush(self) -> None:
        return None


@dataclass(frozen=True)
class _ResourceRequest:
    worker_root: Path
    v1_corpus: Path
    v1_embeddings: Path
    v2_corpus: Path
    v2_embeddings: Path
    qa_source_sha256: str
    combined_source_sha256: str


@dataclass(frozen=True)
class _ModelRequest:
    worker_root: Path
    snapshot: Path


class _ControlState:
    def __init__(
        self,
        worker_root: Path,
        *,
        source_environment: Mapping[str, str] | None = None,
    ):
        self.worker_root = worker_root
        self.source_environment = (
            dict(os.environ) if source_environment is None else dict(source_environment)
        )
        self.network_attempt_count = 0
        self.original_environment: dict[str, str] | None = None
        self.original_cwd: str | None = None
        self.original_socket: object | None = None
        self.original_create_connection: object | None = None
        self.original_getaddrinfo: object | None = None
        self.stdout_sink = _BoundedDiscard()
        self.stderr_sink = _BoundedDiscard()
        self.stdout_context: Any = None
        self.stderr_context: Any = None

    def __enter__(self) -> "_ControlState":
        if not self.worker_root.is_absolute() or len(str(self.worker_root).encode("utf-8")) > 4096:
            raise _WorkerFailure("B4_RESOURCE_MALFORMED")
        try:
            if not self.worker_root.is_dir() or _is_reparse(self.worker_root):
                raise _WorkerFailure("B4_RESOURCE_MALFORMED")
            resolved_root = self.worker_root.resolve(strict=True)
        except _WorkerFailure:
            raise
        except (OSError, RuntimeError) as exc:
            raise _WorkerFailure("B4_RESOURCE_MALFORMED") from exc
        for key in self.source_environment:
            folded = key.casefold()
            if folded not in _CONTROL_ENV_KEYS and any(
                marker in folded for marker in _FORBIDDEN_ENV_MARKERS
            ):
                raise _WorkerFailure("B4_OFFLINE_VIOLATION")
        safe_environment = {
            key: value
            for key, value in self.source_environment.items()
            if key.casefold() in _ESSENTIAL_ENV_KEYS and type(value) is str
        }
        cache = resolved_root / "cache"
        configured = {
            **_OFFLINE_ENV,
            "TEMP": str(resolved_root / "tmp"),
            "TMP": str(resolved_root / "tmp"),
            "PYTHONPYCACHEPREFIX": str(resolved_root / "pycache"),
            "HF_HOME": str(cache / "hf-home"),
            "HF_HUB_CACHE": str(cache / "hf-hub"),
            "TRANSFORMERS_CACHE": str(cache / "transformers"),
            "SENTENCE_TRANSFORMERS_HOME": str(cache / "sentence-transformers"),
            "TORCH_HOME": str(cache / "torch"),
            "XDG_CACHE_HOME": str(cache / "xdg"),
        }
        try:
            for path in (
                resolved_root / "tmp",
                resolved_root / "pycache",
                cache,
                cache / "hf-home",
                cache / "hf-hub",
                cache / "transformers",
                cache / "sentence-transformers",
                cache / "torch",
                cache / "xdg",
            ):
                path.mkdir(parents=True, exist_ok=True)
                if not path.is_dir() or _is_reparse(path):
                    raise _WorkerFailure("B4_RESOURCE_MALFORMED")
        except _WorkerFailure:
            raise
        except OSError as exc:
            raise _WorkerFailure("B4_RESOURCE_MALFORMED") from exc
        safe_environment.update(configured)
        self.original_environment = dict(os.environ)
        self.original_cwd = os.getcwd()
        original_socket_type = socket.socket
        self.original_socket = original_socket_type
        self.original_create_connection = socket.create_connection
        self.original_getaddrinfo = socket.getaddrinfo

        def blocked(*_args: object, **_kwargs: object) -> object:
            self.network_attempt_count += 1
            raise _OfflineAttempt()

        class guarded_socket(original_socket_type):  # type: ignore[misc, valid-type]
            def __new__(cls, *args: object, **kwargs: object) -> object:
                return blocked(*args, **kwargs)

        os.environ.clear()
        os.environ.update(safe_environment)
        os.chdir(resolved_root)
        socket.socket = guarded_socket
        socket.create_connection = blocked  # type: ignore[assignment]
        socket.getaddrinfo = blocked  # type: ignore[assignment]
        self.stdout_context = contextlib.redirect_stdout(self.stdout_sink)
        self.stderr_context = contextlib.redirect_stderr(self.stderr_sink)
        self.stdout_context.__enter__()
        self.stderr_context.__enter__()
        return self

    def __exit__(self, error_type: object, error: object, traceback: object) -> None:
        if self.stderr_context is not None:
            self.stderr_context.__exit__(error_type, error, traceback)
        if self.stdout_context is not None:
            self.stdout_context.__exit__(error_type, error, traceback)
        if self.original_socket is not None:
            socket.socket = self.original_socket  # type: ignore[assignment]
        if self.original_create_connection is not None:
            socket.create_connection = self.original_create_connection  # type: ignore[assignment]
        if self.original_getaddrinfo is not None:
            socket.getaddrinfo = self.original_getaddrinfo  # type: ignore[assignment]
        if self.original_cwd is not None:
            os.chdir(self.original_cwd)
        if self.original_environment is not None:
            os.environ.clear()
            os.environ.update(self.original_environment)


def _is_reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & _FILE_ATTRIBUTE_REPARSE_POINT
    )


def _canonical_file_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _validated_absolute(value: str, *, directory: bool = False) -> Path:
    if type(value) is not str or not value or len(value.encode("utf-8")) > 4096:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    if "\x00" in value or "://" in value:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    path = Path(value)
    if not path.is_absolute():
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    try:
        if _is_reparse(path):
            raise _WorkerFailure("B4_RESOURCE_MALFORMED")
        valid = path.is_dir() if directory else path.is_file()
    except _WorkerFailure:
        raise
    except OSError as exc:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED") from exc
    if not valid:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    return path


def _parse_request(argv: Sequence[str]) -> tuple[str, _ResourceRequest | _ModelRequest]:
    values = list(argv)
    if not values or values[0] not in {"resource", "model"}:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    mode = values[0]
    expected = 8 if mode == "resource" else 3
    if len(values) != expected:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    root = _validated_absolute(values[1], directory=True)
    if mode == "resource":
        hashes = values[6:8]
        if any(_SHA256_RE.fullmatch(value) is None for value in hashes):
            raise _WorkerFailure("B4_RESOURCE_MALFORMED")
        request: _ResourceRequest | _ModelRequest = _ResourceRequest(
            root,
            _validated_absolute(values[2]),
            _validated_absolute(values[3]),
            _validated_absolute(values[4]),
            _validated_absolute(values[5]),
            hashes[0],
            hashes[1],
        )
    else:
        request = _ModelRequest(root, _validated_absolute(values[2], directory=True))
    return mode, request


def _import_resource_dependencies(
    importer: Callable[[str], Any] | None,
) -> tuple[Any, Any]:
    if importer is None:
        import numpy as np
        import pandas as pd

        dependencies = (np, pd)
    else:
        dependencies = (importer("numpy"), importer("pandas"))
    np, pd = dependencies
    required = (
        np.load,
        np.ndarray,
        np.dtype,
        np.isscalar,
        np.bool_,
        np.integer,
        np.isfinite,
        np.linalg.norm,
        np.allclose,
        pd.read_pickle,
        pd.DataFrame,
        pd.RangeIndex,
    )
    if any(symbol is None for symbol in required):
        raise AttributeError()
    return np, pd


def _import_model_dependencies(
    importer: Callable[[str], Any] | None,
) -> tuple[Any, Any, Any]:
    if importer is None:
        import numpy as np
        import sklearn
        from sklearn.metrics.pairwise import cosine_similarity
        import sentence_transformers
        import transformers
        import huggingface_hub
        import torch

        required_modules = (sklearn, transformers, huggingface_hub, torch)
        if any(module is None for module in required_modules):
            raise ImportError()
        sentence_transformer = sentence_transformers.SentenceTransformer
        dependencies = (np, cosine_similarity, sentence_transformer)
    else:
        np = importer("numpy")
        sklearn = importer("sklearn")
        pairwise = importer("sklearn.metrics.pairwise")
        sentence_transformers = importer("sentence_transformers")
        transformers = importer("transformers")
        huggingface_hub = importer("huggingface_hub")
        torch = importer("torch")
        if any(
            module is None
            for module in (
                np,
                sklearn,
                pairwise,
                sentence_transformers,
                transformers,
                huggingface_hub,
                torch,
            )
        ):
            raise ImportError()
        dependencies = (
            np,
            pairwise.cosine_similarity,
            sentence_transformers.SentenceTransformer,
        )
    np, cosine_similarity, sentence_transformer = dependencies
    required = (
        np.ndarray,
        np.dtype,
        np.isfinite,
        np.linalg.norm,
        np.allclose,
        cosine_similarity,
        sentence_transformer,
    )
    if any(symbol is None for symbol in required):
        raise AttributeError()
    return np, cosine_similarity, sentence_transformer


def _priority_compatible(value: object, np: Any) -> bool:
    if value is None:
        return False
    try:
        if not np.isscalar(value):
            return False
    except Exception:
        return False
    if isinstance(value, (bool, np.bool_)):
        return False
    if not isinstance(value, (int, np.integer)):
        return False
    try:
        converted = int(value)
        bonus = max(0.0, (converted - 50) / 500.0)
        return math.isfinite(bonus)
    except (OverflowError, TypeError, ValueError, ArithmeticError):
        return False


def _frame_contract(
    frame: Any,
    *,
    pd: Any,
    np: Any,
    family: str,
    rows: int,
    qa_count: int,
    snippet_count: int,
    core_version: str,
    logical_version: str,
    expected_source_sha: str,
) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame):
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    if list(frame.columns) != list(_RESOURCE_COLUMNS):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    if not isinstance(frame.index, pd.RangeIndex) or (
        frame.index.start,
        frame.index.stop,
        frame.index.step,
    ) != (0, rows, 1):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    if len(frame) != rows:
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    attrs = getattr(frame, "attrs", None)
    if type(attrs) is not dict or (
        attrs.get("source_sha256") != expected_source_sha
        or attrs.get("model_name") != _MODEL_ID
        or attrs.get("corpus_version") != core_version
    ):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    doc_ids = frame["doc_id"]
    if not doc_ids.is_unique or any(
        type(value) is not str or not value.strip() for value in doc_ids
    ):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    for column in ("text_for_embedding", "answer_or_content"):
        if any(type(value) is not str or not value.strip() for value in frame[column]):
            raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    if any(
        not isinstance(value, (bool, np.bool_)) or not bool(value)
        for value in frame["allowed_for_answer"]
    ):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    if any(
        not isinstance(value, (bool, np.bool_))
        for value in frame["needs_backend_api"]
    ):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    priorities = frame["priority"]
    if any(not _priority_compatible(value, np) for value in priorities):
        raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
    if any(int(value) != 50 for value in priorities.iloc[:qa_count]):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    qa = frame.iloc[:qa_count]
    if any(value != _QA_SOURCE_FILE for value in qa["source_file"]) or any(
        value != "chat_qa" for value in qa["source_type"]
    ):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    snippets = frame.iloc[qa_count:]
    if len(snippets) != snippet_count:
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    if snippet_count and (
        any(value != _SNIPPET_SOURCE_FILE for value in snippets["source_file"])
        or any(type(value) is not str or not value.strip() for value in snippets["source_type"])
    ):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    return {
        "allowed_for_answer_all_true": True,
        "cache_corpus_version": core_version,
        "columns": list(_RESOURCE_COLUMNS),
        "doc_ids_unique": True,
        "index_kind": "range_0_based_contiguous",
        "logical_corpus_version": logical_version,
        "model_name": _MODEL_ID,
        "needs_backend_api_all_boolean": True,
        "nonempty_retrieval_text": True,
        "priority_values_runtime_compatible": True,
        "qa_count": qa_count,
        "qa_priority_fixed_50": True,
        "row_count": rows,
        "snippet_count": snippet_count,
        "source_partition_valid": True,
        "source_sha256": expected_source_sha,
    }


def _embedding_contract(array: Any, *, np: Any, rows: int) -> dict[str, Any]:
    if not isinstance(array, np.ndarray) or array.ndim != 2:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    if array.shape != (rows, 384):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    dtype = array.dtype
    native = dtype.isnative or dtype.byteorder in {"=", "|"}
    if dtype != np.dtype("float32") or not native:
        raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
    for start in range(0, rows, 1_024):
        chunk = array[start : start + 1_024]
        if not bool(np.isfinite(chunk).all()):
            raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
        norms = np.linalg.norm(chunk, axis=1)
        if not bool(np.allclose(norms, 1.0, rtol=0.0, atol=1e-3)):
            raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
    return {
        "all_finite": True,
        "dimensions": 384,
        "dtype": "float32",
        "rows": rows,
        "unit_normalized": True,
    }


def _resource_probe(request: _ResourceRequest, np: Any, pd: Any) -> dict[str, Any]:
    try:
        v1 = pd.read_pickle(request.v1_corpus)
        v2 = pd.read_pickle(request.v2_corpus)
    except Exception as exc:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED") from exc
    v1_metadata = _frame_contract(
        v1,
        pd=pd,
        np=np,
        family="v1_qa",
        rows=15333,
        qa_count=15333,
        snippet_count=0,
        core_version="v1_qa_only",
        logical_version="production_v1_qa_only",
        expected_source_sha=request.qa_source_sha256,
    )
    v2_metadata = _frame_contract(
        v2,
        pd=pd,
        np=np,
        family="v2_mixed",
        rows=15688,
        qa_count=15333,
        snippet_count=355,
        core_version="v2_mixed",
        logical_version="production_v2_mixed",
        expected_source_sha=request.combined_source_sha256,
    )
    if not v1.equals(v2.iloc[:15333].reset_index(drop=True)):
        raise _WorkerFailure("B4_IDENTITY_MISMATCH")
    try:
        v1_embeddings = np.load(
            request.v1_embeddings, allow_pickle=False, mmap_mode="r"
        )
        v2_embeddings = np.load(
            request.v2_embeddings, allow_pickle=False, mmap_mode="r"
        )
    except Exception as exc:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED") from exc
    v1_embedding_metadata = _embedding_contract(v1_embeddings, np=np, rows=15333)
    v2_embedding_metadata = _embedding_contract(v2_embeddings, np=np, rows=15688)
    return {
        "families": [
            {
                "cache_family": "v1_qa",
                "corpus_metadata": v1_metadata,
                "embeddings": v1_embedding_metadata,
            },
            {
                "cache_family": "v2_mixed",
                "corpus_metadata": v2_metadata,
                "embeddings": v2_embedding_metadata,
            },
        ],
        "network_attempt_count": 0,
        "v1_is_exact_v2_qa_prefix": True,
    }


def _model_probe(
    request: _ModelRequest,
    np: Any,
    cosine_similarity: Callable[[Any, Any], Any],
    sentence_transformer: Callable[..., Any],
) -> dict[str, Any]:
    try:
        model = sentence_transformer(
            str(request.snapshot),
            local_files_only=True,
            trust_remote_code=False,
            token=False,
            backend="torch",
        )
        probe = model.encode(
            [_MODEL_PROBE_ID],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
    except _OfflineAttempt:
        raise
    except Exception as exc:
        raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE") from exc
    if not isinstance(probe, np.ndarray) or probe.ndim != 2:
        raise _WorkerFailure("B4_RESOURCE_MALFORMED")
    if probe.dtype != np.dtype("float32") or probe.shape != (1, 384):
        raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
    if not bool(np.isfinite(probe).all()):
        raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
    norm = np.linalg.norm(probe, axis=1)
    if not bool(np.allclose(norm, 1.0, rtol=0.0, atol=1e-3)):
        raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
    try:
        similarity = cosine_similarity(probe, probe)
    except Exception as exc:
        raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE") from exc
    if (
        not isinstance(similarity, np.ndarray)
        or similarity.shape != (1, 1)
        or not bool(np.isfinite(similarity).all())
        or not math.isclose(float(similarity[0, 0]), 1.0, rel_tol=0.0, abs_tol=1e-5)
    ):
        raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE")
    return {
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


def _raise_with_offline_precedence(
    controls: _ControlState, error: BaseException
) -> None:
    if controls.network_attempt_count:
        raise _WorkerFailure("B4_OFFLINE_VIOLATION") from error
    if isinstance(error, _OfflineAttempt):
        raise _WorkerFailure("B4_OFFLINE_VIOLATION") from error
    if isinstance(error, _WorkerFailure):
        raise error
    if isinstance(
        error,
        (ImportError, ModuleNotFoundError, AttributeError, OSError),
    ):
        raise _WorkerFailure("B4_DEPENDENCY_UNAVAILABLE") from error
    raise _WorkerFailure("B4_RESOURCE_INCOMPATIBLE") from error


def _execute(
    mode: str,
    request: _ResourceRequest | _ModelRequest,
    *,
    importer: Callable[[str], Any] | None = None,
    source_environment: Mapping[str, str] | None = None,
    control_observer: Callable[[_ControlState], None] | None = None,
) -> dict[str, Any]:
    controls = _ControlState(request.worker_root, source_environment=source_environment)
    try:
        with controls:
            try:
                if control_observer is not None:
                    control_observer(controls)
                if mode == "resource" and type(request) is _ResourceRequest:
                    np, pd = _import_resource_dependencies(importer)
                    result = _resource_probe(request, np, pd)
                elif mode == "model" and type(request) is _ModelRequest:
                    np, cosine_similarity, sentence_transformer = _import_model_dependencies(
                        importer
                    )
                    result = _model_probe(
                        request, np, cosine_similarity, sentence_transformer
                    )
                else:
                    raise _WorkerFailure("B4_RESOURCE_MALFORMED")
            except BaseException as exc:
                _raise_with_offline_precedence(controls, exc)
            if controls.network_attempt_count:
                raise _WorkerFailure("B4_OFFLINE_VIOLATION")
            result["network_attempt_count"] = 0
            if controls.network_attempt_count:
                raise _WorkerFailure("B4_OFFLINE_VIOLATION")
            return {
                "probe": mode,
                "result": result,
                "schema_version": 1,
                "status": "passed",
            }
    except _WorkerFailure as exc:
        if controls.network_attempt_count and exc.category != "B4_OFFLINE_VIOLATION":
            raise _WorkerFailure("B4_OFFLINE_VIOLATION") from exc
        raise
    except Exception as exc:
        if controls.network_attempt_count:
            raise _WorkerFailure("B4_OFFLINE_VIOLATION") from exc
        raise


def _failure_value(category: str) -> dict[str, Any]:
    return {"category": category, "schema_version": 1, "status": "failed"}


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        mode, request = _parse_request(arguments)
        value = _execute(mode, request)
    except _WorkerFailure as exc:
        try:
            sys.stdout.buffer.write(_canonical_file_bytes(_failure_value(exc.category)))
        except Exception:
            return 3
        return 2
    except BaseException:
        return 3
    try:
        raw = _canonical_file_bytes(value)
        if len(raw) > _OUTPUT_MAXIMUM:
            return 3
        sys.stdout.buffer.write(raw)
    except Exception:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
