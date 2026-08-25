from __future__ import annotations

import ast
import builtins
import copy
import dataclasses
import hashlib
import importlib.util
import inspect
import io
import json
import os
import socket
import stat
import sys
import tempfile
import threading
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import formal_evaluation_resource_preflight as preflight
import formal_evaluation_resource_preflight_worker as worker
import formal_evaluation_transport as transport
from outputs import rag_answer_demo as rag_demo


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _sha(value: bytes | str) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with io.open(path, "rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _inventory(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            result[relative + "/"] = "directory"
        elif path.is_file():
            result[relative] = _file_sha(path)
        else:
            result[relative] = "other"
    return result


class _SyntheticPreservationControl:
    def __init__(self) -> None:
        self._temporary_root = Path(tempfile.gettempdir()).resolve(strict=True)
        self._before: dict[Path, dict[str, str]] = {}

    def _synthetic(self, path: Path) -> Path:
        resolved = path.resolve(strict=True)
        assert resolved != self._temporary_root and _under(
            resolved, self._temporary_root
        ), f"preservation root is not test-owned OS-temporary data: {resolved.name}"
        return resolved

    @staticmethod
    def _path_inventory(path: Path) -> dict[str, str]:
        if not path.exists():
            return {"<root>": "missing"}
        if path.is_file():
            return {"<root>": _file_sha(path)}
        if path.is_dir():
            return _inventory(path)
        return {"<root>": "other"}

    def protect(self, path: Path) -> None:
        resolved = self._synthetic(Path(path))
        self._before.setdefault(resolved, self._path_inventory(resolved))

    def protect_snapshot(self, snapshot) -> None:
        repository = Path(snapshot["repository"])
        self.protect(repository)
        self.protect(Path(snapshot["model_cache"]))
        self.protect(
            repository.joinpath(*preflight._B2_RELATIVE_ROOT.split("/"))
        )
        self.protect(
            repository.joinpath(*preflight._B3_RELATIVE_ROOT.split("/"))
        )

    def protect_paths(self, paths) -> None:
        if type(paths) is not preflight._PreflightPathsV1:
            return
        self.protect(paths.repository_root)
        self.protect(paths.model_cache_root)
        protected_roots = (paths.repository_root, paths.model_cache_root)
        inputs = (
            paths.qa_source,
            paths.snippet_source,
            paths.v1_corpus,
            paths.v1_embeddings,
            paths.v2_corpus,
            paths.v2_embeddings,
            *(path for _relative, path in paths.authority_files),
        )
        for path in inputs:
            candidate = Path(path)
            if candidate.exists() and not any(
                _under(candidate.resolve(strict=True), Path(root).resolve(strict=True))
                for root in protected_roots
            ):
                self.protect(candidate)

    def protect_worker_request(self, request) -> None:
        if type(request) is worker._ResourceRequest:
            for path in (
                request.v1_corpus,
                request.v1_embeddings,
                request.v2_corpus,
                request.v2_embeddings,
            ):
                if Path(path).exists():
                    self.protect(Path(path))
        elif type(request) is worker._ModelRequest:
            if Path(request.snapshot).resolve(strict=True) != Path(
                request.worker_root
            ).resolve(strict=True):
                self.protect(request.snapshot)

    def assert_unchanged(self) -> None:
        for root, before in self._before.items():
            after = self._path_inventory(root)
            assert after == before, (
                "protected synthetic input or B2/B3 sentinel inventory changed: "
                f"{root.name}"
            )


_OPTIONAL_IMPORT_FUNCTIONS = {
    "numpy": frozenset({"_import_resource_dependencies", "_import_model_dependencies"}),
    "pandas": frozenset({"_import_resource_dependencies"}),
    "sklearn": frozenset({"_import_model_dependencies"}),
    "sentence_transformers": frozenset({"_import_model_dependencies"}),
    "transformers": frozenset({"_import_model_dependencies"}),
    "huggingface_hub": frozenset({"_import_model_dependencies"}),
    "torch": frozenset({"_import_model_dependencies"}),
}
_FORBIDDEN_IMPORT_PREFIXES = (
    "outputs.rag_answer_demo",
    "formal_evaluation_inflight",
    "formal_evaluation_review_projection",
    "formal_evaluation_runner",
    "formal_evaluation_runtime",
)
_FORBIDDEN_BOUNDARY_NAMES = frozenset(
    {
        "OpenAI",
        "__import__",
        "find_spec",
        "from_pretrained",
        "import_module",
        "load_dotenv",
        "load_or_create_cache",
        "parse_deepseek_config",
        "project_blinded_reviewer_outputs",
        "run_dialogue_checkpointed",
        "run_rag_query",
        "save",
        "save_pretrained",
    }
)


def _qualified_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner = _qualified_name(node.value, aliases)
        return f"{owner}.{node.attr}" if owner else node.attr
    if (
        isinstance(node, ast.Call)
        and _qualified_name(node.func, aliases) in {"getattr", "builtins.getattr"}
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        owner = _qualified_name(node.args[0], aliases)
        return f"{owner}.{node.args[1].value}" if owner else node.args[1].value
    return None


def _static_import_boundary_violations(
    parent_source: str, worker_source: str
) -> tuple[str, ...]:
    violations = []
    for role, source in (("parent", parent_source), ("worker", worker_source)):
        tree = ast.parse(source)
        parents = {
            child: node
            for node in ast.walk(tree)
            for child in ast.iter_child_nodes(node)
        }

        def enclosing_function(node: ast.AST) -> str | None:
            current = parents.get(node)
            while current is not None:
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return current.name
                current = parents.get(current)
            return None

        aliases: dict[str, str] = {"__import__": "builtins.__import__"}
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name
                    local = alias.asname or imported.split(".")[0]
                    aliases[local] = imported if alias.asname else imported.split(".")[0]
                    imports.append((node, imported, None))
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    imported = f"{node.module}.{alias.name}"
                    aliases[alias.asname or alias.name] = imported
                    imports.append((node, node.module, alias.name))

        assignments = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
        ]
        for _pass in range(len(assignments) + 1):
            changed = False
            for node in assignments:
                target = None
                value = None
                if (
                    isinstance(node, ast.Assign)
                    and len(node.targets) == 1
                    and isinstance(node.targets[0], ast.Name)
                ):
                    target, value = node.targets[0].id, node.value
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    target, value = node.target.id, node.value
                if (
                    target is not None
                    and value is not None
                    and not any(
                        isinstance(member, ast.Name) and member.id == target
                        for member in ast.walk(value)
                    )
                ):
                    resolved = _qualified_name(value, aliases)
                    if resolved is not None and aliases.get(target) != resolved:
                        aliases[target] = resolved
                        changed = True
            if not changed:
                break

        for node, module_name, imported_name in imports:
            root = module_name.split(".")[0]
            full_name = (
                f"{module_name}.{imported_name}" if imported_name else module_name
            )
            segments = full_name.lower().split(".")
            prohibited_identity = (
                root.lower() in {"openai", "dotenv"}
                or any("provider" in segment or "deepseek" in segment for segment in segments)
                or any(
                    segment in {"config", "configuration"}
                    or segment.endswith("_config")
                    for segment in segments
                )
                or any(
                    full_name == prefix or full_name.startswith(prefix + ".")
                    for prefix in _FORBIDDEN_IMPORT_PREFIXES
                )
                or (imported_name in _FORBIDDEN_BOUNDARY_NAMES)
            )
            if role == "worker" and root == "formal_evaluation_transport":
                prohibited_identity = True
            if prohibited_identity:
                violations.append(f"{role}:forbidden-import:{full_name}")
            if root in _OPTIONAL_IMPORT_FUNCTIONS:
                allowed = _OPTIONAL_IMPORT_FUNCTIONS[root]
                function = enclosing_function(node)
                if role == "parent" or function not in allowed:
                    violations.append(
                        f"{role}:optional-import-partition:{root}:{function}"
                    )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = _qualified_name(node.func, aliases)
            if called is None:
                continue
            leaf = called.rsplit(".", 1)[-1]
            if leaf in _FORBIDDEN_BOUNDARY_NAMES:
                violations.append(f"{role}:forbidden-call:{called}")
    return tuple(sorted(set(violations)))


@pytest.fixture(autouse=True)
def isolated_offline_boundary(monkeypatch, request):
    repository = Path(__file__).resolve().parents[1]
    protected = (
        repository / "data" / "processed",
        repository / "outputs" / "cache",
        repository / "data" / "formal_eval" / "private_state",
        repository / "data" / "formal_eval" / "reviewer_projection",
    )
    original_validate = preflight._validate_regular_file
    original_hash = preflight._hash_regular_file
    preservation = _SyntheticPreservationControl()
    if "exact_snapshot" in request.fixturenames:
        preservation.protect_snapshot(request.getfixturevalue("exact_snapshot"))

    def guarded_validate(path, floor, maximum=preflight._FILE_MAXIMUM):
        candidate = Path(path)
        if any(_under(candidate, root) for root in protected):
            raise AssertionError("actual production or B2/B3 access")
        return original_validate(path, floor, maximum)

    def guarded_hash(path, floor, relative_path):
        candidate = Path(path)
        if any(_under(candidate, root) for root in protected):
            raise AssertionError("actual production or B2/B3 access")
        return original_hash(path, floor, relative_path)

    monkeypatch.setattr(preflight, "_validate_regular_file", guarded_validate)
    monkeypatch.setattr(preflight, "_hash_regular_file", guarded_hash)
    original_preflight = preflight._preflight_with_paths
    original_launcher = preflight._default_worker_launcher
    original_execute = worker._execute
    original_resource_probe = worker._resource_probe

    def guarded_preflight(paths, *args, **kwargs):
        preservation.protect_paths(paths)
        return original_preflight(paths, *args, **kwargs)

    def guarded_launcher(mode, paths, model, observations):
        preservation.protect_paths(paths)
        return original_launcher(mode, paths, model, observations)

    def guarded_execute(mode, worker_request, *args, **kwargs):
        preservation.protect_worker_request(worker_request)
        return original_execute(mode, worker_request, *args, **kwargs)

    def guarded_resource_probe(worker_request, *args, **kwargs):
        preservation.protect_worker_request(worker_request)
        return original_resource_probe(worker_request, *args, **kwargs)

    monkeypatch.setattr(preflight, "_preflight_with_paths", guarded_preflight)
    monkeypatch.setattr(preflight, "_default_worker_launcher", guarded_launcher)
    monkeypatch.setattr(worker, "_execute", guarded_execute)
    monkeypatch.setattr(worker, "_resource_probe", guarded_resource_probe)
    network_calls = {"count": 0}

    def forbidden_network(*_args, **_kwargs):
        network_calls["count"] += 1
        raise AssertionError("network access is forbidden")

    original_socket_type = socket.socket

    class ForbiddenSocket(original_socket_type):
        def __new__(cls, *args, **kwargs):
            return forbidden_network(*args, **kwargs)

    monkeypatch.setattr(socket, "socket", ForbiddenSocket)
    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden_network)
    yield network_calls
    assert network_calls["count"] == 0
    preservation.assert_unchanged()


def _qa_frame(count: int) -> pd.DataFrame:
    numbers = np.arange(count)
    frame = pd.DataFrame(
        {
            "doc_id": [f"qa_{number}" for number in numbers],
            "source_type": ["chat_qa"] * count,
            "category": ["category"] * count,
            "title": [f"title_{number}" for number in numbers],
            "text_for_embedding": [f"question_{number}" for number in numbers],
            "answer_or_content": [f"answer_{number}" for number in numbers],
            "question": [f"question_{number}" for number in numbers],
            "answer": [f"answer_{number}" for number in numbers],
            "priority": np.full(count, 50, dtype=np.int64),
            "allowed_for_answer": np.full(count, True, dtype=bool),
            "needs_backend_api": np.full(count, False, dtype=bool),
            "source_file": [preflight.Path(preflight._QA_SOURCE_PATH).name] * count,
            "session_id": [""] * count,
        },
        columns=preflight._RESOURCE_COLUMNS,
    )
    return frame


def _snippet_frame(count: int) -> pd.DataFrame:
    numbers = np.arange(count)
    priorities = np.array([60, 70, 80, 90] * ((count + 3) // 4), dtype=np.int64)[:count]
    return pd.DataFrame(
        {
            "doc_id": [f"snippet_{number}" for number in numbers],
            "source_type": ["knowledge_snippet"] * count,
            "category": ["category"] * count,
            "title": [f"snippet_title_{number}" for number in numbers],
            "text_for_embedding": [f"snippet_text_{number}" for number in numbers],
            "answer_or_content": [f"snippet_content_{number}" for number in numbers],
            "question": [f"snippet_title_{number}" for number in numbers],
            "answer": [f"snippet_content_{number}" for number in numbers],
            "priority": priorities,
            "allowed_for_answer": np.full(count, True, dtype=bool),
            "needs_backend_api": np.full(count, False, dtype=bool),
            "source_file": [preflight.Path(preflight._SNIPPET_SOURCE_PATH).name] * count,
            "session_id": [""] * count,
        },
        columns=preflight._RESOURCE_COLUMNS,
    )


@pytest.fixture(scope="session")
def exact_snapshot():
    with tempfile.TemporaryDirectory(prefix="formal-evaluation-b4-tests-") as directory:
        base = Path(directory).resolve(strict=True)
        repository = base / "repository"
        model_cache = base / "model-cache"
        repository.mkdir()
        model_repository = model_cache / preflight._MODEL_REPOSITORY_NAME
        revision = "1" * 40
        snapshot = model_repository / "snapshots" / revision
        (model_repository / "refs").mkdir(parents=True)
        snapshot.mkdir(parents=True)
        (model_repository / "refs" / "main").write_bytes((revision + "\n").encode("ascii"))
        (snapshot / "config.json").write_bytes(b"{\"synthetic\":true}\n")

        for relative in preflight._AUTHORITY_PATHS:
            path = repository.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("synthetic authority " + relative + "\n").encode("utf-8"))

        qa_source = repository.joinpath(*preflight._QA_SOURCE_PATH.split("/"))
        snippet_source = repository.joinpath(*preflight._SNIPPET_SOURCE_PATH.split("/"))
        qa_source.parent.mkdir(parents=True, exist_ok=True)
        qa_source.write_bytes(b"synthetic qa source\n")
        snippet_source.write_bytes(b"synthetic snippet source\n")
        qa_sha = _sha(qa_source.read_bytes())
        snippet_sha = _sha(snippet_source.read_bytes())
        combined_sha = preflight._legacy_combined_source_hash(qa_sha, snippet_sha)

        qa = _qa_frame(15333)
        v1 = qa.copy(deep=True)
        v1.attrs = {
            "source_sha256": qa_sha,
            "model_name": preflight._MODEL_ID,
            "corpus_version": "v1_qa_only",
        }
        v2 = pd.concat([qa, _snippet_frame(355)], ignore_index=True)
        v2.attrs = {
            "source_sha256": combined_sha,
            "model_name": preflight._MODEL_ID,
            "corpus_version": "v2_mixed",
        }
        v1_corpus = repository.joinpath(*preflight._V1_CORPUS_PATH.split("/"))
        v2_corpus = repository.joinpath(*preflight._V2_CORPUS_PATH.split("/"))
        v1_corpus.parent.mkdir(parents=True, exist_ok=True)
        v2_corpus.parent.mkdir(parents=True, exist_ok=True)
        v1.to_pickle(v1_corpus)
        v2.to_pickle(v2_corpus)
        v1_embeddings = np.zeros((15333, 384), dtype=np.float32)
        v2_embeddings = np.zeros((15688, 384), dtype=np.float32)
        v1_embeddings[:, 0] = 1.0
        v2_embeddings[:, 0] = 1.0
        np.save(repository.joinpath(*preflight._V1_EMBEDDINGS_PATH.split("/")), v1_embeddings)
        np.save(repository.joinpath(*preflight._V2_EMBEDDINGS_PATH.split("/")), v2_embeddings)

        b2 = repository.joinpath(*preflight._B2_RELATIVE_ROOT.split("/"))
        b3 = repository.joinpath(*preflight._B3_RELATIVE_ROOT.split("/"))
        b2.mkdir(parents=True)
        b3.mkdir(parents=True)
        (b2 / "sentinel.bin").write_bytes(b"synthetic-b2-sentinel")
        (b3 / "sentinel.bin").write_bytes(b"synthetic-b3-sentinel")
        yield {
            "base": base,
            "repository": repository,
            "model_cache": model_cache,
            "model_repository": model_repository,
            "snapshot": snapshot,
            "qa_sha": qa_sha,
            "combined_sha": combined_sha,
            "v1": v1,
            "v2": v2,
        }


def _paths(snapshot, evidence: Path) -> preflight._PreflightPathsV1:
    return preflight._paths_for_tests(
        snapshot["repository"], evidence, snapshot["model_cache"]
    )


def _safe_dependencies() -> tuple[dict[str, str], ...]:
    return tuple(
        {"name": name, "version": "1.0"} for name in preflight._DEPENDENCY_NAMES
    )


def _resource_result(qa_sha: str, combined_sha: str) -> dict:
    families = []
    for cache, core, logical, rows, qa, snippets, source_sha in (
        ("v1_qa", "v1_qa_only", "production_v1_qa_only", 15333, 15333, 0, qa_sha),
        ("v2_mixed", "v2_mixed", "production_v2_mixed", 15688, 15333, 355, combined_sha),
    ):
        families.append(
            {
                "cache_family": cache,
                "corpus_metadata": {
                    "allowed_for_answer_all_true": True,
                    "cache_corpus_version": core,
                    "columns": list(preflight._RESOURCE_COLUMNS),
                    "doc_ids_unique": True,
                    "index_kind": "range_0_based_contiguous",
                    "logical_corpus_version": logical,
                    "model_name": preflight._MODEL_ID,
                    "needs_backend_api_all_boolean": True,
                    "nonempty_retrieval_text": True,
                    "priority_values_runtime_compatible": True,
                    "qa_count": qa,
                    "qa_priority_fixed_50": True,
                    "row_count": rows,
                    "snippet_count": snippets,
                    "source_partition_valid": True,
                    "source_sha256": source_sha,
                },
                "embeddings": {
                    "all_finite": True,
                    "dimensions": 384,
                    "dtype": "float32",
                    "rows": rows,
                    "unit_normalized": True,
                },
            }
        )
    return {
        "families": families,
        "network_attempt_count": 0,
        "v1_is_exact_v2_qa_prefix": True,
    }


def _model_result() -> dict:
    return {
        "backend": "torch",
        "dimensions": 384,
        "local_only": True,
        "model_id": preflight._MODEL_ID,
        "network_attempt_count": 0,
        "probe_all_finite": True,
        "probe_dtype": "float32",
        "probe_id": preflight._MODEL_PROBE_ID,
        "probe_shape": [1, 384],
        "probe_unit_normalized": True,
        "runtime_cosine_probe_valid": True,
        "trust_remote_code": False,
    }


def _process(mode: str, result: dict) -> preflight._WorkerProcessResultV1:
    payload = {
        "probe": mode,
        "result": result,
        "schema_version": 1,
        "status": "passed",
    }
    return preflight._WorkerProcessResultV1(0, preflight._canonical_file_bytes(payload))


def _fake_launcher(mode, _paths, _model, observations):
    if mode == "resource":
        qa = observations["qa_source"].sha256
        snippets = observations["snippet_source"].sha256
        return _process(mode, _resource_result(qa, preflight._legacy_combined_source_hash(qa, snippets)))
    return _process(mode, _model_result())


def _observations() -> dict[str, preflight._FileObservationV1]:
    return {
        "qa_source": preflight._FileObservationV1(preflight._QA_SOURCE_PATH, 1, "a" * 64),
        "snippet_source": preflight._FileObservationV1(preflight._SNIPPET_SOURCE_PATH, 1, "b" * 64),
        "v1_corpus": preflight._FileObservationV1(preflight._V1_CORPUS_PATH, 1, "c" * 64),
        "v1_embeddings": preflight._FileObservationV1(preflight._V1_EMBEDDINGS_PATH, 1, "d" * 64),
        "v2_corpus": preflight._FileObservationV1(preflight._V2_CORPUS_PATH, 1, "e" * 64),
        "v2_embeddings": preflight._FileObservationV1(preflight._V2_EMBEDDINGS_PATH, 1, "f" * 64),
    }


def _material() -> preflight._FreshMaterialV1:
    observations = _observations()
    authorities = tuple(
        preflight._FileObservationV1(path, 1, _sha(path))
        for path in preflight._AUTHORITY_PATHS
    )
    model = preflight._ModelObservationV1(
        "1" * 40,
        Path.cwd(),
        1,
        1,
        "9" * 64,
        (("config.json", "blobs/config", 1, "8" * 64),),
    )
    identities = preflight._build_identities(transport, observations)
    return preflight._build_material(
        transport,
        _safe_dependencies(),
        authorities,
        observations,
        model,
        _resource_result(
            observations["qa_source"].sha256,
            preflight._legacy_combined_source_hash(
                observations["qa_source"].sha256,
                observations["snippet_source"].sha256,
            ),
        ),
        _model_result(),
        identities,
    )


def _small_frame(priorities, *, snippets: int = 0) -> pd.DataFrame:
    qa_count = len(priorities) - snippets
    qa = _qa_frame(qa_count)
    if snippets:
        frame = pd.concat([qa, _snippet_frame(snippets)], ignore_index=True)
    else:
        frame = qa
    frame["priority"] = pd.Series(list(priorities), dtype=object)
    frame.attrs = {
        "source_sha256": "a" * 64,
        "model_name": preflight._MODEL_ID,
        "corpus_version": "v2_mixed" if snippets else "v1_qa_only",
    }
    return frame


def _frame_check(frame: pd.DataFrame, *, snippets: int = 0):
    rows = len(frame)
    qa_count = rows - snippets
    return worker._frame_contract(
        frame,
        pd=pd,
        np=np,
        family="v2_mixed" if snippets else "v1_qa",
        rows=rows,
        qa_count=qa_count,
        snippet_count=snippets,
        core_version="v2_mixed" if snippets else "v1_qa_only",
        logical_version="production_v2_mixed" if snippets else "production_v1_qa_only",
        expected_source_sha="a" * 64,
    )


def _set_nested(value, path, replacement):
    target = value
    for member in path[:-1]:
        target = target[member]
    target[path[-1]] = replacement


def _integer_paths(value, prefix=()):
    paths = []
    if type(value) is int:
        paths.append(prefix)
    elif type(value) is dict:
        for key, member in value.items():
            paths.extend(_integer_paths(member, prefix + (key,)))
    elif type(value) is list:
        for index, member in enumerate(value):
            paths.extend(_integer_paths(member, prefix + (index,)))
    return paths


def _model_importer(model_type, cosine):
    def importer(name):
        if name == "numpy":
            return np
        if name == "sklearn.metrics.pairwise":
            return types.SimpleNamespace(cosine_similarity=cosine)
        if name == "sentence_transformers":
            return types.SimpleNamespace(SentenceTransformer=model_type)
        return types.SimpleNamespace()

    return importer


class _PandasProbeProxy:
    DataFrame = pd.DataFrame
    RangeIndex = pd.RangeIndex

    def __init__(self, frames, hook=None):
        self.frames = iter(frames)
        self.hook = hook

    def read_pickle(self, _path):
        if self.hook is not None:
            self.hook()
        return next(self.frames)


class _NumpyProbeProxy:
    def __init__(self, arrays, hook=None):
        self.arrays = iter(arrays)
        self.hook = hook
        self.load_calls = []

    def __getattr__(self, name):
        return getattr(np, name)

    def load(self, path, **kwargs):
        self.load_calls.append((Path(path), dict(kwargs)))
        if self.hook is not None:
            self.hook()
        return next(self.arrays)


class TestV2DocumentIdDeduplication:
    def test_deterministic_allocation_preserves_first_occurrence_and_values(self):
        original = _snippet_frame(4)
        original["doc_id"] = [
            "snippet_returns",
            "snippet_size",
            "snippet_returns",
            "snippet_returns",
        ]
        repaired = original.copy(deep=True)

        repaired["doc_id"] = rag_demo._allocate_unique_document_ids(
            repaired["doc_id"].tolist()
        )

        assert repaired["doc_id"].tolist() == [
            "snippet_returns",
            "snippet_size",
            "snippet_returns__dup_2",
            "snippet_returns__dup_3",
        ]
        pd.testing.assert_frame_equal(
            repaired.drop(columns="doc_id"),
            original.drop(columns="doc_id"),
            check_exact=True,
        )
        assert repaired.index.equals(original.index)

    def test_collision_avoidance_and_idempotence(self):
        original_ids = [
            "snippet_policy",
            "snippet_policy",
            "snippet_policy__dup_2",
            "snippet_policy",
        ]

        repaired_ids = rag_demo._allocate_unique_document_ids(original_ids)

        assert repaired_ids == [
            "snippet_policy",
            "snippet_policy__dup_3",
            "snippet_policy__dup_2",
            "snippet_policy__dup_4",
        ]
        assert len(repaired_ids) == len(set(repaired_ids))
        assert rag_demo._allocate_unique_document_ids(repaired_ids) == repaired_ids

    def test_mixed_builder_preserves_rows_qa_values_and_embedding_alignment(
        self, monkeypatch
    ):
        qa = _qa_frame(3)
        snippets = _snippet_frame(4)
        snippets["doc_id"] = [
            "snippet_delivery",
            "snippet_returns",
            "snippet_returns",
            "snippet_returns",
        ]
        original = pd.concat([qa, snippets], ignore_index=True)
        original_columns = original.columns.tolist()
        original_attrs = copy.deepcopy(original.attrs)
        embeddings = np.arange(len(original) * 3, dtype=np.float32).reshape(
            len(original), 3
        )
        original_embeddings = embeddings.copy()
        original_embedding_bytes = embeddings.tobytes()
        qa_items = qa.to_dict(orient="records")
        snippet_items = snippets.to_dict(orient="records")
        monkeypatch.setattr(
            rag_demo,
            "build_qa_corpus_items",
            lambda _path, _pd: copy.deepcopy(qa_items),
        )
        monkeypatch.setattr(
            rag_demo,
            "build_snippet_corpus_items",
            lambda _path, _pd: copy.deepcopy(snippet_items),
        )

        repaired = rag_demo.build_mixed_corpus(
            Path("synthetic-qa.csv"), Path("synthetic-snippets.csv"), pd
        )

        assert len(repaired) == len(original) == embeddings.shape[0]
        assert repaired.columns.tolist() == original_columns
        assert repaired.attrs == original_attrs
        pd.testing.assert_frame_equal(
            repaired.iloc[: len(qa)].reset_index(drop=True),
            qa,
            check_exact=True,
        )
        pd.testing.assert_frame_equal(
            repaired.drop(columns="doc_id"),
            original.drop(columns="doc_id"),
            check_exact=True,
        )
        changed_positions = np.flatnonzero(
            repaired["doc_id"].to_numpy() != original["doc_id"].to_numpy()
        ).tolist()
        assert changed_positions == [len(qa) + 2, len(qa) + 3]
        assert repaired["doc_id"].tolist() == [
            "qa_0",
            "qa_1",
            "qa_2",
            "snippet_delivery",
            "snippet_returns",
            "snippet_returns__dup_2",
            "snippet_returns__dup_3",
        ]
        assert repaired["doc_id"].map(
            lambda doc_id: isinstance(doc_id, str) and bool(doc_id)
        ).all()
        assert repaired["doc_id"].is_unique
        np.testing.assert_array_equal(embeddings, original_embeddings)
        assert embeddings.tobytes() == original_embedding_bytes


class TestB4ContractAndDiscovery:
    def test_fixed_resource_contract_matches_tracked_authorities(self):
        assert preflight._QA_SOURCE_PATH.endswith("jd_final_safe_qa_refined_category.csv")
        assert preflight._SNIPPET_SOURCE_PATH.endswith("knowledge_snippets_v2_reviewed.csv")
        assert preflight._RESOURCE_COLUMNS[8] == "priority"
        assert preflight._MODEL_ID == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    def test_stage_a_registry_yields_exact_four_family_bindings(self):
        observations = _observations()
        identities = preflight._build_identities(transport, observations)
        assert tuple(item.system_config_id for item in identities) == preflight._SYSTEM_CONFIG_ORDER
        assert tuple(item.cache_family for item in identities) == (
            "v1_qa", "v2_mixed", "v2_mixed", "v2_mixed"
        )
        assert len({(item.corpus_sha256, item.embeddings_sha256) for item in identities[1:]}) == 1

    def test_public_api_accepts_no_root_model_or_real_override(self):
        assert list(inspect.signature(preflight.preflight_production_resources).parameters) == []
        assert list(inspect.signature(preflight.ProductionResourcePreflightResultV1).parameters) == [
            "schema_version", "action", "status", "preflight_sha256", "resource_identities"
        ]

    def test_dependency_inventory_is_exact_and_bounded(self, monkeypatch):
        calls = []
        monkeypatch.setattr(preflight.platform, "python_version", lambda: "3.11.9")
        monkeypatch.setattr(preflight.sys, "version_info", (3, 11, 9))
        monkeypatch.setattr(
            preflight.importlib.metadata,
            "version",
            lambda name: calls.append(name) or "1.2.3",
        )
        result = preflight._discover_dependency_versions()
        assert tuple(item["name"] for item in result) == preflight._DEPENDENCY_NAMES
        assert tuple(calls) == preflight._DISTRIBUTION_NAMES
        monkeypatch.setattr(preflight.importlib.metadata, "version", lambda _name: "unsafe value")
        with pytest.raises(preflight._PreflightError, match="^B4_DEPENDENCY_UNAVAILABLE$"):
            preflight._discover_dependency_versions()

    def test_authority_inventory_is_exact_sorted_and_unchanged(self):
        assert preflight._AUTHORITY_PATHS == tuple(sorted(preflight._AUTHORITY_PATHS))
        assert len(preflight._AUTHORITY_PATHS) == 16
        assert set(preflight._AUTHORITY_PATHS).intersection(
            {preflight._B2_RELATIVE_ROOT, preflight._B3_RELATIVE_ROOT}
        ) == set()


class TestB4DependencyBoundary:
    def test_parent_worker_environment_uses_only_fixed_get_lookups(self, tmp_path, monkeypatch):
        class EnvironmentSpy:
            def __init__(self, values):
                self.data = values
                self.lookups = []

            def get(self, name, default=None):
                self.lookups.append(name)
                return self.data.get(name, default)

            def __iter__(self):
                raise AssertionError("environment iteration")

            def items(self):
                raise AssertionError("environment items")

            def keys(self):
                raise AssertionError("environment keys")

            def values(self):
                raise AssertionError("environment values")

            def copy(self):
                raise AssertionError("environment copy")

        forbidden = {
            "DEEPSEEK_API_KEY": "SYNTHETIC_CREDENTIAL",
            "OPENAI_TOKEN": "SYNTHETIC_TOKEN",
            "HTTPS_PROXY": "http://synthetic.invalid",
            "PROVIDER_CONFIG": "SYNTHETIC_PROVIDER",
        }
        spy = EnvironmentSpy({"PATH": "synthetic-path", **forbidden})
        monkeypatch.setattr(preflight, "os", types.SimpleNamespace(environ=spy))
        environment = preflight._worker_environment(tmp_path)
        assert spy.lookups == list(preflight._WORKER_INHERITED_ENV_NAMES)
        assert environment["PATH"] == "synthetic-path"
        assert set(environment).isdisjoint(forbidden)
        assert all(value not in environment.values() for value in forbidden.values())

    def test_parent_worker_environment_omits_absent_optional_allowlist(self, tmp_path, monkeypatch):
        class CleanEnvironment:
            def __init__(self):
                self.lookups = []

            def get(self, name, default=None):
                self.lookups.append(name)
                return default

            def __iter__(self):
                raise AssertionError("environment iteration")

            items = keys = values = copy = __iter__

        clean = CleanEnvironment()
        monkeypatch.setattr(preflight, "os", types.SimpleNamespace(environ=clean))
        environment = preflight._worker_environment(tmp_path)
        assert clean.lookups == list(preflight._WORKER_INHERITED_ENV_NAMES)
        assert set(environment).isdisjoint(preflight._WORKER_INHERITED_ENV_NAMES)
        assert environment["HF_HUB_OFFLINE"] == "1"

    def test_parent_never_imports_optional_data_or_model_packages(self, monkeypatch):
        tree = ast.parse(Path(preflight.__file__).read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        assert imported.isdisjoint(
            {"numpy", "pandas", "sklearn", "sentence_transformers", "transformers", "huggingface_hub", "torch"}
        )
        optional = {
            "numpy", "pandas", "sklearn", "sentence_transformers",
            "transformers", "huggingface_hub", "torch",
        }
        original_import = builtins.__import__
        attempts = []

        def trapped(name, *args, **kwargs):
            if name.split(".")[0] in optional:
                attempts.append(name)
                raise AssertionError("parent optional import")
            return original_import(name, *args, **kwargs)

        module_name = "_b4_parent_import_boundary_test"
        specification = importlib.util.spec_from_file_location(module_name, preflight.__file__)
        assert specification is not None and specification.loader is not None
        module = importlib.util.module_from_spec(specification)
        monkeypatch.setitem(sys.modules, module_name, module)
        monkeypatch.setattr(builtins, "__import__", trapped)
        specification.loader.exec_module(module)
        assert attempts == []

    def test_parent_dependency_discovery_uses_only_stdlib_metadata(self):
        source = inspect.getsource(preflight._discover_dependency_versions)
        assert "platform.python_version()" in source
        assert "importlib.metadata.version" in source
        assert "find_spec" not in source and "import_module" not in source

    def test_worker_optional_imports_begin_only_after_all_controls(self, tmp_path):
        root = tmp_path / "worker"
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()
        request = worker._ModelRequest(root, snapshot)
        observed = []

        class FakeModel:
            def __init__(self, *_args, **_kwargs):
                pass

            def encode(self, *_args, **_kwargs):
                value = np.zeros((1, 384), dtype=np.float32)
                value[0, 0] = 1.0
                return value

        def importer(name):
            assert Path.cwd() == root.resolve()
            assert os.environ["HF_HUB_OFFLINE"] == "1"
            assert _under(Path(os.environ["HF_HOME"]), root.resolve())
            assert isinstance(socket.socket, type)

            class ImportCompatibleSocket(socket.socket):
                pass

            assert issubclass(ImportCompatibleSocket, socket.socket)
            observed.append(name)
            if name == "numpy":
                return np
            if name == "sklearn.metrics.pairwise":
                return types.SimpleNamespace(cosine_similarity=lambda a, b: np.array([[1.0]]))
            if name == "sentence_transformers":
                return types.SimpleNamespace(SentenceTransformer=FakeModel)
            return types.SimpleNamespace()

        value = worker._execute(
            "model",
            request,
            importer=importer,
            source_environment={"PATH": os.environ.get("PATH", "")},
        )
        assert value["status"] == "passed"
        assert observed[0] == "numpy"

    def test_worker_socket_controls_are_type_compatible_block_and_restore(
        self, tmp_path
    ):
        root = tmp_path / "worker"
        root.mkdir()
        originals = (
            socket.socket,
            socket.create_connection,
            socket.getaddrinfo,
        )
        controls = worker._ControlState(
            root,
            source_environment={"PATH": os.environ.get("PATH", "")},
        )

        with pytest.raises(RuntimeError, match="^synthetic control exit$"):
            with controls:
                assert isinstance(socket.socket, type)

                class ImportCompatibleSocket(socket.socket):
                    pass

                assert issubclass(ImportCompatibleSocket, socket.socket)
                for operation in (
                    socket.socket,
                    ImportCompatibleSocket,
                    lambda: socket.create_connection(("synthetic.invalid", 443)),
                    lambda: socket.getaddrinfo("synthetic.invalid", 443),
                ):
                    with pytest.raises(worker._OfflineAttempt):
                        operation()
                assert controls.network_attempt_count == 4
                raise RuntimeError("synthetic control exit")

        assert controls.network_attempt_count == 4
        assert socket.socket is originals[0]
        assert socket.create_connection is originals[1]
        assert socket.getaddrinfo is originals[2]

    def test_worker_model_dependencies_import_with_type_compatible_guard(
        self, tmp_path
    ):
        root = tmp_path / "worker"
        root.mkdir()
        source_environment = {
            name: value
            for name in preflight._WORKER_INHERITED_ENV_NAMES
            if (value := os.environ.get(name))
        }
        controls = worker._ControlState(
            root,
            source_environment=source_environment,
        )

        with controls:
            imported_numpy, cosine_similarity, sentence_transformer = (
                worker._import_model_dependencies(None)
            )
            assert imported_numpy is np
            assert callable(cosine_similarity)
            assert callable(sentence_transformer)
            assert controls.network_attempt_count == 0

        assert controls.network_attempt_count == 0

    def test_worker_dependency_import_failure_maps_only_to_b4_dependency_unavailable(self, tmp_path):
        root = tmp_path / "worker"
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()
        request = worker._ModelRequest(root, snapshot)
        with pytest.raises(worker._WorkerFailure, match="^B4_DEPENDENCY_UNAVAILABLE$"):
            worker._execute(
                "model",
                request,
                importer=lambda _name: (_ for _ in ()).throw(ImportError("SECRET C:\\private")),
                source_environment={"PATH": os.environ.get("PATH", "")},
            )

    def test_dependency_failure_with_attempted_remote_resolution_is_offline_violation(
        self, tmp_path
    ):
        root = tmp_path / "worker"
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()

        def importer(_name):
            try:
                socket.getaddrinfo("synthetic.invalid", 443)
            except BaseException as exc:
                raise ImportError("SYNTHETIC_TOKEN https://synthetic.invalid") from exc

        with pytest.raises(worker._WorkerFailure, match="^B4_OFFLINE_VIOLATION$") as caught:
            worker._execute(
                "model",
                worker._ModelRequest(root, snapshot),
                importer=importer,
                source_environment={"PATH": "synthetic"},
            )
        assert str(caught.value) == "B4_OFFLINE_VIOLATION"

    def test_dependency_failure_is_sanitized_nonpublishing_and_preserving(self, exact_snapshot, tmp_path, monkeypatch):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        before = _inventory(exact_snapshot["repository"])
        monkeypatch.setattr(
            preflight.importlib.metadata,
            "version",
            lambda _name: (_ for _ in ()).throw(preflight.importlib.metadata.PackageNotFoundError()),
        )
        with pytest.raises(preflight._PreflightError, match="^B4_DEPENDENCY_UNAVAILABLE$") as caught:
            preflight._preflight_with_paths(paths, _fake_launcher)
        assert str(caught.value) == "B4_DEPENDENCY_UNAVAILABLE"
        assert not paths.evidence_root.exists()
        assert _inventory(exact_snapshot["repository"]) == before

    def test_worker_scrubs_and_replaces_environment_before_optional_import(self, tmp_path):
        root = tmp_path / "worker"
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()
        observed = {}

        class Model:
            def __init__(self, *_args, **_kwargs):
                pass

            def encode(self, *_args, **_kwargs):
                result = np.zeros((1, 384), dtype=np.float32)
                result[0, 0] = 1.0
                return result

        def importer(name):
            if not observed:
                observed.update(dict(os.environ))
            return _model_importer(Model, lambda a, b: np.array([[1.0]]))(name)

        value = worker._execute(
            "model",
            worker._ModelRequest(root, snapshot),
            importer=importer,
            source_environment={"PATH": "synthetic-path", "UNRELATED": "not-forwarded"},
        )
        assert value["status"] == "passed"
        assert observed["PATH"] == "synthetic-path"
        assert "UNRELATED" not in observed
        assert observed["HF_HUB_OFFLINE"] == "1"
        for name in (
            "TEMP",
            "TMP",
            "PYTHONPYCACHEPREFIX",
            "HF_HOME",
            "HF_HUB_CACHE",
            "TRANSFORMERS_CACHE",
            "SENTENCE_TRANSFORMERS_HOME",
            "TORCH_HOME",
            "XDG_CACHE_HOME",
        ):
            assert _under(Path(observed[name]), root.resolve())


class TestB4PathBoundary:
    @pytest.mark.parametrize(
        "value",
        ["../escape", "C:/drive", "//server/share", "https://remote", "a\\b", "a/%TEMP%", "a/../b"],
    )
    def test_rejects_relative_escape_drive_unc_uri_and_alternate_separator(self, value):
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._validate_relative_path(value)

    def test_rejects_source_or_cache_symlink_junction_and_reparse_component(self, exact_snapshot, tmp_path, monkeypatch):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        original = preflight._is_reparse
        monkeypatch.setattr(
            preflight,
            "_is_reparse",
            lambda path: True if Path(path) == paths.qa_source else original(path),
        )
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._validate_resource_paths(paths)

    def test_allows_only_model_file_links_resolving_within_model_repository(self, exact_snapshot, tmp_path, monkeypatch):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        config = exact_snapshot["snapshot"] / "config.json"
        original = preflight._model_entry_lstat
        fake_link = types.SimpleNamespace(
            st_mode=stat.S_IFLNK,
            st_file_attributes=preflight._FILE_ATTRIBUTE_REPARSE_POINT,
        )
        monkeypatch.setattr(
            preflight,
            "_model_entry_lstat",
            lambda path: fake_link if Path(path) == config else original(path),
        )
        monkeypatch.setattr(
            preflight,
            "_model_link_target",
            lambda path: config if Path(path) == config else Path(path).resolve(strict=True),
        )
        observed = preflight._hash_model_snapshot(paths)
        assert observed.file_count == 1
        assert observed.members[0][0] == "config.json"

    def test_rejects_model_link_escape_dangling_link_and_directory_reparse(self, exact_snapshot, tmp_path, monkeypatch):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        snapshot = exact_snapshot["snapshot"]
        config = snapshot / "config.json"
        outside = tmp_path / "outside.bin"
        outside.write_bytes(b"outside")
        original_lstat = preflight._model_entry_lstat
        fake_link = types.SimpleNamespace(
            st_mode=stat.S_IFLNK,
            st_file_attributes=preflight._FILE_ATTRIBUTE_REPARSE_POINT,
        )
        monkeypatch.setattr(
            preflight,
            "_model_entry_lstat",
            lambda path: fake_link if Path(path) == config else original_lstat(path),
        )
        monkeypatch.setattr(preflight, "_model_link_target", lambda _path: outside)
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._hash_model_snapshot(paths)

    def test_rejects_wrong_type_size_file_count_and_overlapping_roots(self, exact_snapshot, tmp_path, monkeypatch):
        wrong = tmp_path / "wrong"
        wrong.mkdir()
        with pytest.raises(preflight._PreflightError, match="^B4_RESOURCE_TYPE_INVALID$"):
            preflight._validate_regular_file(wrong, tmp_path)
        sized = tmp_path / "sized.bin"
        sized.write_bytes(b"12")
        with pytest.raises(preflight._PreflightError, match="^B4_RESOURCE_TYPE_INVALID$"):
            preflight._validate_regular_file(sized, tmp_path, maximum=1)
        paths_for_model = _paths(exact_snapshot, tmp_path / "model-evidence")
        monkeypatch.setattr(preflight, "_MODEL_FILE_MAXIMUM", 0)
        with pytest.raises(preflight._PreflightError, match="^B4_RESOURCE_TYPE_INVALID$"):
            preflight._hash_model_snapshot(paths_for_model)
        paths = preflight._paths_for_tests(
            exact_snapshot["repository"],
            exact_snapshot["repository"] / "outputs" / "cache",
            exact_snapshot["model_cache"],
        )
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._validate_path_bundle(paths)

    def test_production_root_guard_fails_before_any_production_access(self, exact_snapshot, tmp_path):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        unsafe = dataclasses.replace(paths, repository_root=Path(preflight.__file__).resolve().parents[1])
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._validate_path_bundle(unsafe)

    @pytest.mark.parametrize(
        "seam",
        ["data", "outputs", "cache_family", "model_cache", "evidence"],
    )
    def test_reparse_seams_cover_every_required_ancestor(
        self, exact_snapshot, tmp_path, monkeypatch, seam
    ):
        evidence_parent = tmp_path / "evidence-parent"
        evidence_parent.mkdir()
        paths = preflight._paths_for_tests(
            exact_snapshot["repository"],
            evidence_parent / "evidence",
            exact_snapshot["model_cache"],
        )
        targets = {
            "data": paths.repository_root / "data",
            "outputs": paths.repository_root / "outputs",
            "cache_family": paths.repository_root / "outputs" / "cache" / "v1_qa",
            "model_cache": paths.model_cache_root,
            "evidence": evidence_parent,
        }
        target = targets[seam]
        original = preflight._is_reparse
        monkeypatch.setattr(
            preflight,
            "_is_reparse",
            lambda path: True if Path(path) == target else original(path),
        )
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._validate_path_bundle(paths)
        assert not paths.evidence_root.exists()

    def test_resolved_evidence_alias_into_resource_or_b2_b3_is_rejected(
        self, exact_snapshot, tmp_path, monkeypatch
    ):
        for protected in (
            exact_snapshot["repository"] / "outputs" / "cache" / "v1_qa",
            exact_snapshot["repository"].joinpath(*preflight._B2_RELATIVE_ROOT.split("/")),
            exact_snapshot["repository"].joinpath(*preflight._B3_RELATIVE_ROOT.split("/")),
        ):
            evidence = tmp_path / protected.name / "evidence"
            paths = _paths(exact_snapshot, evidence)
            original = preflight._resolved

            def resolved(path, *, strict, evidence=evidence, protected=protected):
                if Path(path) == evidence:
                    return protected
                return original(path, strict=strict)

            with monkeypatch.context() as context:
                context.setattr(preflight, "_resolved", resolved)
                with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
                    preflight._validate_path_bundle(paths)
            assert not evidence.exists()

    def test_resolved_resource_alias_escape_is_rejected_before_content_read(
        self, exact_snapshot, tmp_path, monkeypatch
    ):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        outside = tmp_path / "outside.bin"
        outside.write_bytes(b"outside")
        original = preflight._resolved

        def resolved(path, *, strict):
            if Path(path) == paths.qa_source:
                return outside
            return original(path, strict=strict)

        monkeypatch.setattr(preflight, "_resolved", resolved)
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._validate_resource_paths(paths)

    def test_model_cache_root_overlap_with_resource_family_is_rejected(
        self, exact_snapshot, tmp_path
    ):
        overlapping_cache = exact_snapshot["repository"] / "outputs" / "cache"
        paths = preflight._paths_for_tests(
            exact_snapshot["repository"],
            tmp_path / "evidence",
            overlapping_cache,
        )
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._validate_path_bundle(paths)

    def test_percent_model_cache_setting_is_rejected_without_expansion(self, monkeypatch):
        monkeypatch.setenv("SENTENCE_TRANSFORMERS_HOME", "%TEMP%\\synthetic-cache")
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._resolve_model_cache_root()

    def test_unsafe_path_rejects_before_read_worker_or_evidence_parent_creation(
        self, exact_snapshot, tmp_path, monkeypatch
    ):
        evidence_parent = tmp_path / "must-not-exist"
        paths = _paths(exact_snapshot, evidence_parent / "evidence")
        unsafe = paths.repository_root / "outputs"
        original = preflight._is_reparse
        counters = {"authority": 0, "worker": 0}

        def reparse(path):
            return True if Path(path) == unsafe else original(path)

        def authority(_paths):
            counters["authority"] += 1
            raise AssertionError("content read")

        def launcher(*_args):
            counters["worker"] += 1
            raise AssertionError("worker launch")

        monkeypatch.setattr(preflight, "_is_reparse", reparse)
        monkeypatch.setattr(preflight, "_authority_observations", authority)
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._preflight_with_paths(paths, launcher)
        assert counters == {"authority": 0, "worker": 0}
        assert not evidence_parent.exists()


class TestB4ResourceStructure:
    def test_accepts_exact_count_synthetic_v1_and_v2_snapshot(self, exact_snapshot, tmp_path):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        request = worker._ResourceRequest(
            tmp_path,
            paths.v1_corpus,
            paths.v1_embeddings,
            paths.v2_corpus,
            paths.v2_embeddings,
            exact_snapshot["qa_sha"],
            exact_snapshot["combined_sha"],
        )
        result = worker._resource_probe(request, np, pd)
        assert result["v1_is_exact_v2_qa_prefix"] is True
        assert [item["corpus_metadata"]["row_count"] for item in result["families"]] == [15333, 15688]
        observations = preflight._file_observations(paths)
        model = preflight._hash_model_snapshot(paths)
        process = preflight._default_worker_launcher(
            "resource", paths, model, observations
        )
        decoded = preflight._decode_worker_result("resource", process)
        assert preflight._validate_resource_worker_result(decoded)[
            "v1_is_exact_v2_qa_prefix"
        ] is True

    def test_rejects_missing_family_member_without_rebuild(self, exact_snapshot, tmp_path):
        with pytest.raises(preflight._PreflightError, match="^B4_RESOURCE_MISSING$"):
            preflight._validate_regular_file(tmp_path / "missing.pkl", tmp_path)

    def test_rejects_truncated_wrong_object_and_wrong_attr_pickles(self):
        frame = _small_frame([50])
        frame.attrs["model_name"] = "wrong"
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            _frame_check(frame)
        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_MALFORMED$"):
            worker._frame_contract(
                {}, pd=pd, np=np, family="v1_qa", rows=1, qa_count=1, snippet_count=0,
                core_version="v1_qa_only", logical_version="production_v1_qa_only",
                expected_source_sha="a" * 64,
            )

    @pytest.mark.parametrize(
        "array,category",
        [
            (np.ones((1, 384), dtype=np.float64), "B4_RESOURCE_INCOMPATIBLE"),
            (np.ones((1, 383), dtype=np.float32), "B4_IDENTITY_MISMATCH"),
            (np.full((1, 384), np.nan, dtype=np.float32), "B4_RESOURCE_INCOMPATIBLE"),
            (np.zeros((1, 384), dtype=np.float32), "B4_RESOURCE_INCOMPATIBLE"),
        ],
    )
    def test_rejects_npy_object_dtype_wrong_dtype_shape_nan_inf_and_bad_norm(self, array, category):
        with pytest.raises(worker._WorkerFailure, match=f"^{category}$"):
            worker._embedding_contract(array, np=np, rows=1)

    def test_rejects_wrong_columns_index_counts_partition_and_empty_fields(self):
        frame = _small_frame([50])
        frame.loc[0, "text_for_embedding"] = ""
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            _frame_check(frame)
        frame = _small_frame([50]).drop(columns=["priority"])
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            _frame_check(frame)

    def test_rejects_duplicate_doc_ids_and_nonboolean_flags(self):
        frame = _small_frame([50, 50])
        frame.loc[1, "doc_id"] = frame.loc[0, "doc_id"]
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            _frame_check(frame)
        frame = _small_frame([50])
        frame["needs_backend_api"] = [1]
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            _frame_check(frame)

    def test_accepts_builder_compatible_qa_and_snippet_priorities(self):
        metadata = _frame_check(_small_frame([50, -1000000], snippets=1), snippets=1)
        assert metadata["priority_values_runtime_compatible"] is True
        assert metadata["qa_priority_fixed_50"] is True

    @pytest.mark.parametrize(
        "value",
        [
            "50",
            50.0,
            [50],
            object(),
            pytest.param(10**10000, id="runtime_overflow_integer"),
        ],
    )
    def test_rejects_non_integer_compatible_priority(self, value):
        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_INCOMPATIBLE$"):
            _frame_check(_small_frame([value]))

    @pytest.mark.parametrize("value", [None, pd.NA, np.nan])
    def test_rejects_null_priority(self, value):
        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_INCOMPATIBLE$"):
            _frame_check(_small_frame([value]))

    @pytest.mark.parametrize("value", [True, np.bool_(False)])
    def test_rejects_boolean_priority(self, value):
        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_INCOMPATIBLE$"):
            _frame_check(_small_frame([value]))

    def test_rejects_qa_priority_other_than_fixed_50(self):
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            _frame_check(_small_frame([51]))

    def test_rejects_source_hash_and_legacy_combined_hash_mismatch(self):
        frame = _small_frame([50])
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            worker._frame_contract(
                frame, pd=pd, np=np, family="v1_qa", rows=1, qa_count=1,
                snippet_count=0, core_version="v1_qa_only",
                logical_version="production_v1_qa_only", expected_source_sha="b" * 64,
            )
        assert preflight._legacy_combined_source_hash("a" * 64, "b" * 64) != preflight._legacy_combined_source_hash("b" * 64, "a" * 64)

    def test_rejects_v1_v2_qa_prefix_mismatch_without_emitting_difference(self, exact_snapshot):
        changed = exact_snapshot["v2"].copy(deep=True)
        changed.loc[0, "answer"] = "SYNTHETIC_ROW_SECRET"
        assert not exact_snapshot["v1"].equals(changed.iloc[:15333].reset_index(drop=True))
        error = worker._WorkerFailure("B4_IDENTITY_MISMATCH")
        assert "SYNTHETIC_ROW_SECRET" not in str(error)

    def test_worker_output_is_aggregate_canonical_and_bounded(self):
        value = {"probe": "resource", "result": _resource_result("a" * 64, "b" * 64), "schema_version": 1, "status": "passed"}
        raw = worker._canonical_file_bytes(value)
        assert len(raw) < worker._OUTPUT_MAXIMUM
        assert raw == preflight._canonical_file_bytes(value)
        assert b"priority_values_runtime_compatible" in raw
        assert b"priority_min" not in raw and b"row_id" not in raw

    @pytest.mark.parametrize("kind", ["truncated", "wrong_top_level"])
    def test_resource_probe_actually_loads_and_rejects_bad_pickles(self, tmp_path, kind):
        payload = tmp_path / f"{kind}.pkl"
        if kind == "truncated":
            payload.write_bytes(b"\x80\x04")
        else:
            pd.to_pickle({"unexpected": "mapping"}, payload)
        request = worker._ResourceRequest(
            tmp_path,
            payload,
            tmp_path / "unused-v1.npy",
            payload,
            tmp_path / "unused-v2.npy",
            "a" * 64,
            "b" * 64,
        )
        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_MALFORMED$"):
            worker._resource_probe(request, np, pd)

    @pytest.mark.parametrize(
        "mutation",
        ["missing_attrs", "wrong_model", "malformed_hash", "inconsistent_v2_hash"],
    )
    def test_resource_worker_subprocess_rejects_real_pickles_with_bad_attrs(
        self, exact_snapshot, tmp_path, mutation
    ):
        v1 = exact_snapshot["v1"].copy(deep=False)
        v2 = exact_snapshot["v2"].copy(deep=False)
        v1.attrs = dict(exact_snapshot["v1"].attrs)
        v2.attrs = dict(exact_snapshot["v2"].attrs)
        if mutation == "missing_attrs":
            v1.attrs = {}
        elif mutation == "wrong_model":
            v1.attrs["model_name"] = "SYNTHETIC_WRONG_MODEL_SECRET"
        elif mutation == "malformed_hash":
            v1.attrs["source_sha256"] = 7
        else:
            v2.attrs["source_sha256"] = "0" * 64

        input_root = tmp_path / "inputs"
        input_root.mkdir()
        v1_corpus = input_root / "v1.pkl"
        v2_corpus = input_root / "v2.pkl"
        v1.to_pickle(v1_corpus)
        v2.to_pickle(v2_corpus)
        evidence_root = tmp_path / "evidence"
        valid_paths = _paths(exact_snapshot, evidence_root)
        observations = preflight._file_observations(valid_paths)
        model = preflight._hash_model_snapshot(valid_paths)
        paths = dataclasses.replace(
            valid_paths,
            v1_corpus=v1_corpus,
            v2_corpus=v2_corpus,
        )
        process = preflight._default_worker_launcher(
            "resource", paths, model, observations
        )
        expected = preflight._canonical_file_bytes(
            {
                "category": "B4_IDENTITY_MISMATCH",
                "schema_version": 1,
                "status": "failed",
            }
        )
        assert process.returncode == 2
        assert process.stdout == expected
        with pytest.raises(
            preflight._PreflightError, match="^B4_IDENTITY_MISMATCH$"
        ) as caught:
            preflight._validate_resource_worker_result(
                preflight._decode_worker_result("resource", process)
            )
        assert str(caught.value) == "B4_IDENTITY_MISMATCH"
        assert b"SYNTHETIC_WRONG_MODEL_SECRET" not in process.stdout
        assert str(input_root).encode("utf-8") not in process.stdout
        assert not evidence_root.exists()

    @pytest.mark.parametrize(
        "mutation",
        [
            "column_order",
            "index",
            "row_count",
            "qa_partition",
            "snippet_partition",
            "empty_answer",
            "missing_priority",
            "allowed_false",
        ],
    )
    def test_corpus_contract_matrix_uses_actual_frame_validation(self, mutation):
        frame = _small_frame([50, 60], snippets=1)
        rows = 2
        if mutation == "column_order":
            columns = list(frame.columns)
            columns[0], columns[1] = columns[1], columns[0]
            frame = frame[columns]
        elif mutation == "index":
            frame.index = pd.RangeIndex(1, 3)
        elif mutation == "row_count":
            rows = 3
        elif mutation == "qa_partition":
            frame.loc[0, "source_type"] = "wrong"
        elif mutation == "snippet_partition":
            frame.loc[1, "source_file"] = "wrong.csv"
        elif mutation == "empty_answer":
            frame.loc[0, "answer_or_content"] = "   "
        elif mutation == "missing_priority":
            frame = frame.drop(columns=["priority"])
        else:
            frame.loc[0, "allowed_for_answer"] = False
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            worker._frame_contract(
                frame,
                pd=pd,
                np=np,
                family="v2_mixed",
                rows=rows,
                qa_count=1,
                snippet_count=1,
                core_version="v2_mixed",
                logical_version="production_v2_mixed",
                expected_source_sha="a" * 64,
            )

    @pytest.mark.parametrize(
        "array,category",
        [
            (np.ones((384,), dtype=np.float32), "B4_RESOURCE_MALFORMED"),
            (np.ones((1, 384), dtype=object), "B4_RESOURCE_INCOMPATIBLE"),
            (np.full((1, 384), np.inf, dtype=np.float32), "B4_RESOURCE_INCOMPATIBLE"),
            (np.ones((2, 384), dtype=np.float32), "B4_IDENTITY_MISMATCH"),
        ],
    )
    def test_embedding_rank_object_infinity_and_row_boundaries(self, array, category):
        with pytest.raises(worker._WorkerFailure, match=f"^{category}$"):
            worker._embedding_contract(array, np=np, rows=1)

    def test_numpy_load_is_nonpickle_readonly_mmap_and_checks_are_chunked(
        self, exact_snapshot, tmp_path
    ):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        v1_array = np.load(paths.v1_embeddings, allow_pickle=False, mmap_mode="r")
        v2_array = np.load(paths.v2_embeddings, allow_pickle=False, mmap_mode="r")
        numpy_proxy = _NumpyProbeProxy((v1_array, v2_array))
        pandas_proxy = _PandasProbeProxy((exact_snapshot["v1"], exact_snapshot["v2"]))
        request = worker._ResourceRequest(
            tmp_path,
            paths.v1_corpus,
            paths.v1_embeddings,
            paths.v2_corpus,
            paths.v2_embeddings,
            exact_snapshot["qa_sha"],
            exact_snapshot["combined_sha"],
        )
        result = worker._resource_probe(request, numpy_proxy, pandas_proxy)
        assert result["v1_is_exact_v2_qa_prefix"] is True
        assert [kwargs for _path, kwargs in numpy_proxy.load_calls] == [
            {"allow_pickle": False, "mmap_mode": "r"},
            {"allow_pickle": False, "mmap_mode": "r"},
        ]
        assert v1_array.flags.writeable is False
        assert v2_array.flags.writeable is False

        class TrackingNumpy:
            ndarray = np.ndarray

            def __init__(self):
                self.finite_chunks = []
                self.norm_chunks = []
                self.linalg = types.SimpleNamespace(norm=self.norm)

            def __getattr__(self, name):
                return getattr(np, name)

            def isfinite(self, chunk):
                self.finite_chunks.append(chunk.shape[0])
                return np.isfinite(chunk)

            def norm(self, chunk, axis):
                self.norm_chunks.append(chunk.shape[0])
                return np.linalg.norm(chunk, axis=axis)

        tracking = TrackingNumpy()
        chunked = np.zeros((2050, 384), dtype=np.float32)
        chunked[:, 0] = 1.0
        worker._embedding_contract(chunked, np=tracking, rows=2050)
        assert tracking.finite_chunks == [1024, 1024, 2]
        assert tracking.norm_chunks == [1024, 1024, 2]

    def test_embedding_norm_tolerance_boundary_is_exact(self):
        accepted = np.zeros((1, 384), dtype=np.float32)
        accepted[0, 0] = np.float32(1.0009)
        assert worker._embedding_contract(accepted, np=np, rows=1)[
            "unit_normalized"
        ] is True
        rejected = np.zeros((1, 384), dtype=np.float32)
        rejected[0, 0] = np.float32(1.0011)
        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_INCOMPATIBLE$"):
            worker._embedding_contract(rejected, np=np, rows=1)

    def test_object_npy_is_rejected_with_allow_pickle_false_in_resource_probe(
        self, exact_snapshot, tmp_path
    ):
        object_array = tmp_path / "object.npy"
        np.save(object_array, np.array([[object()]], dtype=object), allow_pickle=True)
        pandas_proxy = _PandasProbeProxy((exact_snapshot["v1"], exact_snapshot["v2"]))
        request = worker._ResourceRequest(
            tmp_path,
            tmp_path / "v1.pkl",
            object_array,
            tmp_path / "v2.pkl",
            object_array,
            exact_snapshot["qa_sha"],
            exact_snapshot["combined_sha"],
        )
        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_MALFORMED$"):
            worker._resource_probe(request, np, pandas_proxy)

    @pytest.mark.parametrize(
        "mutation",
        ["value", "dtype", "index", "order", "length", "boundary"],
    )
    def test_resource_probe_enforces_qa_prefix_invariant(
        self, exact_snapshot, tmp_path, mutation
    ):
        v1 = exact_snapshot["v1"].copy(deep=False)
        v1.attrs = dict(exact_snapshot["v1"].attrs)
        v2 = exact_snapshot["v2"].copy(deep=True)
        v2.attrs = dict(exact_snapshot["v2"].attrs)
        if mutation == "value":
            v2.loc[0, "answer"] = "SYNTHETIC_CHANGED_VALUE"
        elif mutation == "dtype":
            v2["category"] = v2["category"].astype("string")
        elif mutation == "index":
            v2.index = pd.RangeIndex(1, len(v2) + 1)
        elif mutation == "order":
            order = list(range(len(v2)))
            order[0], order[1] = order[1], order[0]
            v2 = v2.iloc[order].reset_index(drop=True)
            v2.attrs = dict(exact_snapshot["v2"].attrs)
        elif mutation == "length":
            v2 = v2.iloc[:-1].copy()
            v2.attrs = dict(exact_snapshot["v2"].attrs)
        else:
            order = list(range(len(v2)))
            order[15332], order[15333] = order[15333], order[15332]
            v2 = v2.iloc[order].reset_index(drop=True)
            v2.attrs = dict(exact_snapshot["v2"].attrs)
        pandas_proxy = _PandasProbeProxy((v1, v2))
        arrays = (
            np.load(
                exact_snapshot["repository"].joinpath(*preflight._V1_EMBEDDINGS_PATH.split("/")),
                allow_pickle=False,
                mmap_mode="r",
            ),
            np.load(
                exact_snapshot["repository"].joinpath(*preflight._V2_EMBEDDINGS_PATH.split("/")),
                allow_pickle=False,
                mmap_mode="r",
            ),
        )
        request = worker._ResourceRequest(
            tmp_path,
            tmp_path / "v1.pkl",
            tmp_path / "v1.npy",
            tmp_path / "v2.pkl",
            tmp_path / "v2.npy",
            exact_snapshot["qa_sha"],
            exact_snapshot["combined_sha"],
        )
        with pytest.raises(worker._WorkerFailure, match="^B4_IDENTITY_MISMATCH$"):
            worker._resource_probe(request, _NumpyProbeProxy(arrays), pandas_proxy)


class TestB4OfflineModelProbe:
    @pytest.mark.parametrize("operation", ["socket", "dns"])
    def test_direct_guarded_network_attempts_have_offline_precedence(self, tmp_path, operation):
        root = tmp_path / "worker"
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()

        def attempt():
            if operation == "socket":
                socket.socket()
            else:
                socket.getaddrinfo("synthetic.invalid", 443)

        class Model:
            def __init__(self, *_args, **_kwargs):
                attempt()

        with pytest.raises(worker._WorkerFailure, match="^B4_OFFLINE_VIOLATION$"):
            worker._execute(
                "model",
                worker._ModelRequest(root, snapshot),
                importer=_model_importer(Model, lambda a, b: np.array([[1.0]])),
                source_environment={"PATH": "synthetic"},
            )

    @pytest.mark.parametrize("stage", ["construction", "encoding", "cosine"])
    @pytest.mark.parametrize("handling", ["replace", "swallow"])
    def test_model_stage_offline_attempt_overrides_replacement_or_success(
        self, tmp_path, stage, handling
    ):
        root = tmp_path / f"worker-{stage}-{handling}"
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()

        def attempt():
            try:
                socket.getaddrinfo("synthetic.invalid", 443)
            except BaseException as exc:
                if handling == "replace":
                    raise ValueError("SYNTHETIC_SECRET URL https://synthetic.invalid") from exc

        class Model:
            def __init__(self, *_args, **_kwargs):
                if stage == "construction":
                    attempt()

            def encode(self, *_args, **_kwargs):
                if stage == "encoding":
                    attempt()
                result = np.zeros((1, 384), dtype=np.float32)
                result[0, 0] = 1.0
                return result

        def cosine(left, right):
            if stage == "cosine":
                attempt()
            return np.array([[1.0]])

        with pytest.raises(worker._WorkerFailure, match="^B4_OFFLINE_VIOLATION$") as caught:
            worker._execute(
                "model",
                worker._ModelRequest(root, snapshot),
                importer=_model_importer(Model, cosine),
                source_environment={"PATH": "synthetic"},
            )
        assert "SYNTHETIC_SECRET" not in str(caught.value)
        assert "synthetic.invalid" not in str(caught.value)

    @pytest.mark.parametrize("handling", ["replace", "swallow"])
    def test_resource_pickle_offline_attempt_has_final_precedence(
        self, exact_snapshot, tmp_path, handling
    ):
        root = tmp_path / f"resource-worker-{handling}"
        root.mkdir()
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        arrays = (
            np.load(paths.v1_embeddings, allow_pickle=False, mmap_mode="r"),
            np.load(paths.v2_embeddings, allow_pickle=False, mmap_mode="r"),
        )
        calls = {"count": 0}

        def hook():
            calls["count"] += 1
            if calls["count"] == 1:
                try:
                    socket.socket()
                except BaseException as exc:
                    if handling == "replace":
                        raise ValueError("SYNTHETIC_PICKLE_SECRET C:\\synthetic") from exc

        pandas_proxy = _PandasProbeProxy(
            (exact_snapshot["v1"], exact_snapshot["v2"]), hook=hook
        )
        numpy_proxy = _NumpyProbeProxy(arrays)

        def importer(name):
            return numpy_proxy if name == "numpy" else pandas_proxy

        request = worker._ResourceRequest(
            root,
            paths.v1_corpus,
            paths.v1_embeddings,
            paths.v2_corpus,
            paths.v2_embeddings,
            exact_snapshot["qa_sha"],
            exact_snapshot["combined_sha"],
        )
        with pytest.raises(worker._WorkerFailure, match="^B4_OFFLINE_VIOLATION$") as caught:
            worker._execute(
                "resource",
                request,
                importer=importer,
                source_environment={"PATH": "synthetic"},
            )
        assert str(caught.value) == "B4_OFFLINE_VIOLATION"

    def test_local_snapshot_probe_uses_exact_path_and_offline_arguments(self, tmp_path):
        calls = {}

        class FakeModel:
            def __init__(self, path, **kwargs):
                calls["path"] = path
                calls["constructor"] = kwargs

            def encode(self, values, **kwargs):
                calls["values"] = values
                calls["encode"] = kwargs
                result = np.zeros((1, 384), dtype=np.float32)
                result[0, 0] = 1.0
                return result

        request = worker._ModelRequest(tmp_path, tmp_path)
        result = worker._model_probe(request, np, lambda a, b: np.array([[1.0]]), FakeModel)
        assert calls["path"] == str(tmp_path)
        assert calls["constructor"] == {"local_files_only": True, "trust_remote_code": False, "token": False, "backend": "torch"}
        assert calls["values"] == [preflight._MODEL_PROBE_ID]
        assert result["runtime_cosine_probe_valid"] is True

    def test_rejects_missing_ref_revision_snapshot_or_model_files(self, exact_snapshot, tmp_path):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        bad = dataclasses.replace(paths, model_repository=tmp_path / "missing-model")
        with pytest.raises(preflight._PreflightError, match="^B4_RESOURCE_MISSING$"):
            preflight._read_model_revision(bad)

    def test_rejects_remote_code_remote_fallback_and_any_socket_attempt(self, tmp_path):
        class NetworkModel:
            def __init__(self, *_args, **_kwargs):
                socket.socket()

        request = worker._ModelRequest(tmp_path, tmp_path)

        def importer(name):
            if name == "numpy":
                return np
            if name == "sklearn.metrics.pairwise":
                return types.SimpleNamespace(cosine_similarity=lambda a, b: np.array([[1.0]]))
            if name == "sentence_transformers":
                return types.SimpleNamespace(SentenceTransformer=NetworkModel)
            return types.SimpleNamespace()

        with pytest.raises(worker._WorkerFailure, match="^B4_OFFLINE_VIOLATION$"):
            worker._execute(
                "model",
                request,
                importer=importer,
                source_environment={"PATH": os.environ.get("PATH", "")},
            )

    @pytest.mark.parametrize("kind", ["shape", "nonfinite", "nonunit"])
    def test_rejects_wrong_probe_shape_nonfinite_or_nonunit_output(self, tmp_path, kind):
        class BadModel:
            def __init__(self, *_args, **_kwargs):
                pass

            def encode(self, *_args, **_kwargs):
                if kind == "shape":
                    return np.ones((1, 3), dtype=np.float32)
                value = np.zeros((1, 384), dtype=np.float32)
                value[0, 0] = np.nan if kind == "nonfinite" else 2.0
                return value

        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_INCOMPATIBLE$"):
            worker._model_probe(worker._ModelRequest(tmp_path, tmp_path), np, lambda a, b: np.array([[1.0]]), BadModel)

    def test_rejects_unusable_or_invalid_runtime_cosine_similarity(self, tmp_path):
        class Model:
            def __init__(self, *_args, **_kwargs):
                pass

            def encode(self, *_args, **_kwargs):
                value = np.zeros((1, 384), dtype=np.float32)
                value[0, 0] = 1.0
                return value

        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_INCOMPATIBLE$"):
            worker._model_probe(worker._ModelRequest(tmp_path, tmp_path), np, lambda a, b: np.array([[0.5]]), Model)

    def test_runtime_cosine_tolerance_boundary_is_exact(self, tmp_path):
        class Model:
            def __init__(self, *_args, **_kwargs):
                pass

            def encode(self, *_args, **_kwargs):
                value = np.zeros((1, 384), dtype=np.float32)
                value[0, 0] = 1.0
                return value

        accepted = worker._model_probe(
            worker._ModelRequest(tmp_path, tmp_path),
            np,
            lambda a, b: np.array([[0.999991]]),
            Model,
        )
        assert accepted["runtime_cosine_probe_valid"] is True
        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_INCOMPATIBLE$"):
            worker._model_probe(
                worker._ModelRequest(tmp_path, tmp_path),
                np,
                lambda a, b: np.array([[0.99998]]),
                Model,
            )

    def test_model_tree_hash_is_deterministic_and_path_sensitive(self, exact_snapshot, tmp_path):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        first = preflight._hash_model_snapshot(paths)
        second = preflight._hash_model_snapshot(paths)
        assert first == second
        assert first.snapshot_sha256 != _sha((exact_snapshot["snapshot"] / "config.json").read_bytes())

    def test_worker_environment_omits_credentials_proxies_and_tokens(self, tmp_path):
        root = tmp_path / "worker"
        root.mkdir()
        controls = worker._ControlState(
            root,
            source_environment={"PATH": os.environ.get("PATH", ""), "DEEPSEEK_API_KEY": "FAKE_SECRET"},
        )
        with pytest.raises(worker._WorkerFailure, match="^B4_OFFLINE_VIOLATION$"):
            with controls:
                pass

    def test_worker_timeout_crash_extra_output_and_schema_error_fail_closed(self):
        cases = (
            preflight._WorkerProcessResultV1(-1, b"", timed_out=True),
            preflight._WorkerProcessResultV1(3, b"{}\n"),
            preflight._WorkerProcessResultV1(0, b"{}\nextra\n"),
            preflight._WorkerProcessResultV1(0, b"{}\n"),
        )
        expected = ("B4_IO_FAILURE", "B4_INTERNAL_FAILURE", "B4_INTERNAL_FAILURE", "B4_INTERNAL_FAILURE")
        for process, category in zip(cases, expected):
            with pytest.raises(preflight._PreflightError, match=f"^{category}$"):
                preflight._decode_worker_result("model", process)

    @pytest.mark.parametrize(
        "kind",
        ["missing_repository", "malformed_ref", "wrong_revision", "missing_snapshot"],
    )
    def test_model_repository_reference_and_snapshot_failure_matrix(
        self, exact_snapshot, tmp_path, kind
    ):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        if kind == "missing_repository":
            paths = dataclasses.replace(paths, model_repository=tmp_path / "missing")
            operation = lambda: preflight._read_model_revision(paths)
            category = "B4_RESOURCE_MISSING"
        else:
            model_cache = tmp_path / "c"
            repository = model_cache / preflight._MODEL_REPOSITORY_NAME
            refs = repository / "refs"
            refs.mkdir(parents=True)
            revision = "2" * 40
            if kind == "malformed_ref":
                (refs / "main").write_bytes(b"UPPERCASE-OR-SHORT\n")
                operation = lambda: preflight._read_model_revision(
                    dataclasses.replace(
                        paths,
                        model_cache_root=model_cache,
                        model_repository=repository,
                    )
                )
                category = "B4_RESOURCE_MALFORMED"
            else:
                (refs / "main").write_bytes((revision + "\n").encode("ascii"))
                if kind == "wrong_revision":
                    other = repository / "snapshots" / ("3" * 40)
                    other.mkdir(parents=True)
                    (other / "config.json").write_bytes(b"{}\n")
                operation = lambda: preflight._hash_model_snapshot(
                    dataclasses.replace(
                        paths,
                        model_cache_root=model_cache,
                        model_repository=repository,
                    )
                )
                category = "B4_RESOURCE_MISSING"
        with pytest.raises(preflight._PreflightError, match=f"^{category}$"):
            operation()

    def test_incomplete_model_members_constructor_failure_is_incompatible_and_sanitized(
        self, tmp_path
    ):
        root = tmp_path / "worker"
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()

        class IncompleteModel:
            def __init__(self, *_args, **_kwargs):
                raise FileNotFoundError(
                    "SYNTHETIC_TOKEN C:\\cache\\missing-module URL https://invalid"
                )

        with pytest.raises(worker._WorkerFailure, match="^B4_RESOURCE_INCOMPATIBLE$") as caught:
            worker._execute(
                "model",
                worker._ModelRequest(root, snapshot),
                importer=_model_importer(
                    IncompleteModel, lambda a, b: np.array([[1.0]])
                ),
                source_environment={"PATH": "synthetic"},
            )
        assert str(caught.value) == "B4_RESOURCE_INCOMPATIBLE"

    def test_invalid_model_logical_tree_is_rejected_without_worker_launch(
        self, exact_snapshot, tmp_path, monkeypatch
    ):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        monkeypatch.setattr(preflight, "_MODEL_FILE_MAXIMUM", 0)
        with pytest.raises(preflight._PreflightError, match="^B4_RESOURCE_TYPE_INVALID$"):
            preflight._hash_model_snapshot(paths)


class TestB4ArtifactLifecycle:
    def test_first_success_publishes_exact_canonical_artifact_and_result(self, tmp_path):
        material = _material()
        root = tmp_path / "evidence"
        assert preflight._publish_candidate(root, material.artifact_bytes, transport) == "created"
        assert (root / preflight._EVIDENCE_FILENAME).read_bytes() == material.artifact_bytes
        parsed = preflight._load_canonical_json(material.artifact_bytes, preflight._EVIDENCE_BYTES_MAXIMUM, "B4_EVIDENCE_INVALID")
        preflight._validate_artifact(parsed, transport)

    def test_exact_reopen_revalidates_resources_and_returns_already_complete(self, exact_snapshot, tmp_path, monkeypatch):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        monkeypatch.setattr(preflight, "_discover_dependency_versions", _safe_dependencies)
        first = preflight._preflight_with_paths(paths, _fake_launcher)
        second = preflight._preflight_with_paths(paths, _fake_launcher)
        assert first.action == "created"
        assert second.action == "already_complete"
        assert first.preflight_sha256 == second.preflight_sha256

    def test_valid_different_existing_artifact_is_stale_and_not_overwritten(self, tmp_path):
        material = _material()
        root = tmp_path / "evidence"
        root.mkdir()
        changed = json.loads(material.artifact_bytes)
        changed["dependency_versions"][0]["version"] = "3.11.8"
        changed["preflight_sha256"] = preflight._preflight_sha(changed)
        existing = preflight._canonical_file_bytes(changed)
        (root / preflight._EVIDENCE_FILENAME).write_bytes(existing)
        with pytest.raises(preflight._PreflightError, match="^B4_EVIDENCE_STALE$"):
            preflight._publish_candidate(root, material.artifact_bytes, transport)
        assert (root / preflight._EVIDENCE_FILENAME).read_bytes() == existing

    @pytest.mark.parametrize("kind", ["malformed", "noncanonical", "oversized", "hash_bad"])
    def test_malformed_noncanonical_oversized_and_hash_bad_artifact_is_preserved(self, tmp_path, kind):
        material = _material()
        root = tmp_path / kind
        root.mkdir()
        if kind == "malformed":
            raw = b"{\n"
        elif kind == "noncanonical":
            raw = b'{"status": "passed"}\n'
        elif kind == "oversized":
            raw = b"x" * (preflight._EVIDENCE_BYTES_MAXIMUM + 1)
        else:
            value = json.loads(material.artifact_bytes)
            value["preflight_sha256"] = "0" * 64
            raw = preflight._canonical_file_bytes(value)
        final = root / preflight._EVIDENCE_FILENAME
        final.write_bytes(raw)
        with pytest.raises(preflight._PreflightError, match="^B4_EVIDENCE_INVALID$"):
            preflight._publish_candidate(root, material.artifact_bytes, transport)
        assert final.read_bytes() == raw

    def test_interruption_before_and_after_create_only_move_recovers_closed(self, tmp_path):
        material = _material()
        root = tmp_path / "before"

        def before(point):
            if point == "before_move":
                raise preflight._PreflightError("B4_IO_FAILURE")

        with pytest.raises(preflight._PreflightError, match="^B4_IO_FAILURE$"):
            preflight._publish_candidate(root, material.artifact_bytes, transport, fault=before)
        assert not (root / preflight._EVIDENCE_FILENAME).exists()
        assert preflight._publish_candidate(root, material.artifact_bytes, transport) == "created"
        root_after = tmp_path / "after"

        def after(point):
            if point == "after_move":
                raise preflight._PreflightError("B4_IO_FAILURE")

        with pytest.raises(preflight._PreflightError, match="^B4_IO_FAILURE$"):
            preflight._publish_candidate(root_after, material.artifact_bytes, transport, fault=after)
        assert preflight._publish_candidate(root_after, material.artifact_bytes, transport) == "already_complete"

    def test_only_owned_temp_is_removed_while_lock_is_held(self, tmp_path):
        material = _material()
        root = tmp_path / "evidence"
        root.mkdir()
        owned = root / f".{preflight._EVIDENCE_FILENAME}.{'1' * 32}.tmp"
        owned.write_bytes(b"partial")
        preflight._publish_candidate(root, material.artifact_bytes, transport)
        assert not owned.exists()

    def test_unknown_member_and_ambiguous_lock_fail_closed(self, tmp_path):
        root = tmp_path / "unknown"
        root.mkdir()
        (root / "unknown.tmp").write_bytes(b"x")
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._scan_evidence_layout(root, transport, allow_missing=False)
        other = tmp_path / "lock"
        other.mkdir()
        (other / preflight._LOCK_FILENAME).write_bytes(b"ambiguous")
        with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
            preflight._scan_evidence_layout(other, transport, allow_missing=False)

    def test_two_publishers_create_or_reopen_without_overwrite(self, tmp_path):
        material = _material()
        root = tmp_path / "evidence"
        outcomes = []
        errors = []

        def publish():
            try:
                outcomes.append(preflight._publish_candidate(root, material.artifact_bytes, transport))
            except preflight._PreflightError as exc:
                errors.append(exc.category)

        threads = [threading.Thread(target=publish) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert "created" in outcomes
        assert set(outcomes + errors).issubset({"created", "already_complete", "B4_LOCK_BUSY"})
        assert (root / preflight._EVIDENCE_FILENAME).read_bytes() == material.artifact_bytes

    def test_existing_evidence_read_is_bounded_and_never_uses_read_bytes(
        self, tmp_path, monkeypatch
    ):
        material = _material()
        final = tmp_path / preflight._EVIDENCE_FILENAME
        final.write_bytes(material.artifact_bytes)
        original_open = Path.open
        read_sizes = []

        class BoundedHandle:
            def __init__(self, handle):
                self.handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.handle.__exit__(*args)

            def read(self, size=-1):
                if size < 0:
                    raise AssertionError("unbounded evidence read")
                read_sizes.append(size)
                return self.handle.read(size)

        def bounded_open(path, *args, **kwargs):
            handle = original_open(path, *args, **kwargs)
            if Path(path) == final and args and args[0] == "rb":
                return BoundedHandle(handle)
            return handle

        monkeypatch.setattr(Path, "read_bytes", lambda _path: (_ for _ in ()).throw(AssertionError("read_bytes")))
        monkeypatch.setattr(Path, "open", bounded_open)
        raw, _value = preflight._read_existing_artifact(final, transport)
        assert raw == material.artifact_bytes
        assert read_sizes == [preflight._EVIDENCE_BYTES_MAXIMUM + 1]

    def test_sparse_oversized_evidence_is_rejected_before_open_and_preserved(
        self, tmp_path, monkeypatch
    ):
        final = tmp_path / preflight._EVIDENCE_FILENAME
        with final.open("wb") as handle:
            handle.seek(preflight._EVIDENCE_BYTES_MAXIMUM)
            handle.write(b"x")
        with final.open("rb") as handle:
            before = (final.stat().st_size, handle.read(1))
        original_open = Path.open

        def guarded_open(path, *args, **kwargs):
            if Path(path) == final and args and args[0] == "rb":
                raise AssertionError("oversized evidence content read")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", guarded_open)
        with pytest.raises(preflight._PreflightError, match="^B4_EVIDENCE_INVALID$"):
            preflight._read_existing_artifact(final, transport)
        assert final.stat().st_size == before[0]
        with original_open(final, "rb") as handle:
            assert handle.read(1) == before[1]

    @pytest.mark.parametrize("extra", [0, 1])
    def test_evidence_exact_limit_and_limit_plus_one_are_bounded_and_preserved(
        self, tmp_path, extra
    ):
        final = tmp_path / f"limit-{extra}.json"
        raw = b"x" * (preflight._EVIDENCE_BYTES_MAXIMUM + extra)
        final.write_bytes(raw)
        with pytest.raises(preflight._PreflightError, match="^B4_EVIDENCE_INVALID$"):
            preflight._read_existing_artifact(final, transport)
        assert final.stat().st_size == len(raw)

    @pytest.mark.parametrize(
        "raw,accepted",
        [(b"", False), (b"\x00", True), (b"\x00\x00", False), (b"large", False)],
    )
    def test_lock_one_byte_contract_reads_at_most_two_and_preserves(
        self, tmp_path, monkeypatch, raw, accepted
    ):
        root = tmp_path / f"lock-{len(raw)}-{raw.hex()}"
        root.mkdir()
        lock = root / preflight._LOCK_FILENAME
        lock.write_bytes(raw)
        monkeypatch.setattr(Path, "read_bytes", lambda _path: (_ for _ in ()).throw(AssertionError("whole lock read")))
        if accepted:
            assert preflight._scan_evidence_layout(
                root, transport, allow_missing=False
            ) is None
        else:
            with pytest.raises(preflight._PreflightError, match="^B4_PATH_UNSAFE$"):
                preflight._scan_evidence_layout(root, transport, allow_missing=False)
        assert lock.stat().st_size == len(raw)

    def test_bounded_evidence_read_failure_maps_to_io_and_preserves_file(
        self, tmp_path, monkeypatch
    ):
        material = _material()
        final = tmp_path / preflight._EVIDENCE_FILENAME
        final.write_bytes(material.artifact_bytes)
        original_open = Path.open

        def failed_open(path, *args, **kwargs):
            if Path(path) == final and args and args[0] == "rb":
                raise OSError("SYNTHETIC_PATH C:\\private")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", failed_open)
        with pytest.raises(preflight._PreflightError, match="^B4_IO_FAILURE$") as caught:
            preflight._read_existing_artifact(final, transport)
        assert str(caught.value) == "B4_IO_FAILURE"
        with original_open(final, "rb") as handle:
            assert handle.read() == material.artifact_bytes

    @pytest.mark.parametrize(
        "point",
        [
            "after_open",
            "after_write",
            "after_flush",
            "after_fsync",
            "after_close",
            "before_move",
            "after_move",
            "before_readback",
            "after_readback",
        ],
    )
    def test_publication_interruption_matrix_recovers_without_overwrite(
        self, tmp_path, point
    ):
        material = _material()
        root = tmp_path / point

        def fault(observed):
            if observed == point:
                raise preflight._PreflightError("B4_IO_FAILURE")

        with pytest.raises(preflight._PreflightError, match="^B4_IO_FAILURE$"):
            preflight._publish_candidate(
                root, material.artifact_bytes, transport, fault=fault
            )
        outcome = preflight._publish_candidate(root, material.artifact_bytes, transport)
        assert outcome in {"created", "already_complete"}
        assert (root / preflight._EVIDENCE_FILENAME).read_bytes() == material.artifact_bytes

    def test_actual_fsync_and_create_only_move_failures_are_io_and_retryable(
        self, tmp_path, monkeypatch
    ):
        material = _material()
        root = tmp_path / "fsync"
        with monkeypatch.context() as context:
            context.setattr(
                preflight.os,
                "fsync",
                lambda _fd: (_ for _ in ()).throw(OSError("synthetic fsync")),
            )
            with pytest.raises(preflight._PreflightError, match="^B4_IO_FAILURE$"):
                preflight._publish_candidate(root, material.artifact_bytes, transport)
        assert preflight._publish_candidate(root, material.artifact_bytes, transport) == "created"

        move_root = tmp_path / "move"
        with monkeypatch.context() as context:
            context.setattr(
                preflight,
                "_move_file_create_only",
                lambda _source, _target: (_ for _ in ()).throw(
                    preflight._PreflightError("B4_IO_FAILURE")
                ),
            )
            with pytest.raises(preflight._PreflightError, match="^B4_IO_FAILURE$"):
                preflight._publish_candidate(
                    move_root, material.artifact_bytes, transport
                )
        assert preflight._publish_candidate(
            move_root, material.artifact_bytes, transport
        ) == "created"

    @pytest.mark.parametrize("operation", ["open", "write", "flush", "close"])
    def test_actual_publication_file_operation_failures_are_io_and_recoverable(
        self, tmp_path, monkeypatch, operation
    ):
        material = _material()
        root = tmp_path / operation
        original_open = Path.open

        class FaultyHandle:
            def __init__(self, handle):
                self.handle = handle

            def __getattr__(self, name):
                return getattr(self.handle, name)

            def write(self, value):
                if operation == "write":
                    raise OSError("synthetic write")
                return self.handle.write(value)

            def flush(self):
                if operation == "flush":
                    raise OSError("synthetic flush")
                return self.handle.flush()

            def close(self):
                self.handle.close()
                if operation == "close":
                    raise OSError("synthetic close")

        def faulty_open(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if mode == "xb" and Path(path).name != preflight._LOCK_FILENAME:
                if operation == "open":
                    raise OSError("synthetic open")
                return FaultyHandle(original_open(path, *args, **kwargs))
            return original_open(path, *args, **kwargs)

        with monkeypatch.context() as context:
            context.setattr(Path, "open", faulty_open)
            with pytest.raises(preflight._PreflightError, match="^B4_IO_FAILURE$"):
                preflight._publish_candidate(root, material.artifact_bytes, transport)
        assert preflight._publish_candidate(
            root, material.artifact_bytes, transport
        ) == "created"


class TestB4FailureBoundaryAndPreservation:
    def test_failure_taxonomy_is_closed_and_precedence_is_stable(self):
        assert preflight._FAILURE_CATEGORIES[0] == "B4_PLATFORM_UNSUPPORTED"
        assert preflight._FAILURE_CATEGORIES[-1] == "B4_INTERNAL_FAILURE"
        assert preflight._FAILURE_CATEGORIES.index("B4_DEPENDENCY_UNAVAILABLE") < preflight._FAILURE_CATEGORIES.index("B4_RESOURCE_INCOMPATIBLE")
        assert preflight._FAILURE_CATEGORIES.index("B4_RESOURCE_INCOMPATIBLE") < preflight._FAILURE_CATEGORIES.index("B4_IDENTITY_MISMATCH")
        assert len(preflight._FAILURE_CATEGORIES) == len(set(preflight._FAILURE_CATEGORIES)) == 16

    def test_cli_success_and_failure_bytes_and_exit_codes_are_exact(self, monkeypatch, capfd):
        material = _material()
        result = preflight.ProductionResourcePreflightResultV1(
            1, "created", "passed", material.preflight_sha256, tuple(material.identities)
        )
        monkeypatch.setattr(preflight, "preflight_production_resources", lambda: result)
        assert preflight.main([]) == 0
        captured = capfd.readouterr()
        assert captured.out.encode() == preflight._success_line(result)
        assert captured.err == ""

        def fail():
            raise preflight._PreflightError("B4_RESOURCE_MISSING")

        monkeypatch.setattr(preflight, "preflight_production_resources", fail)
        assert preflight.main([]) == 2
        captured = capfd.readouterr()
        assert captured.out == ""
        assert captured.err == "B4_RESOURCE_MISSING\n"
        assert preflight.main(["--root", "C:\\unsafe"]) == 2
        captured = capfd.readouterr()
        assert captured.out == ""
        assert captured.err == "B4_AUTHORITY_INVALID\n"

    def test_public_boundary_removes_path_secret_row_vector_and_traceback_markers(self):
        markers = ("FAKE_SECRET", "C:\\private", "ROW_TEXT", "[0.1, 0.2]", "Traceback")
        for category in preflight._FAILURE_CATEGORIES:
            public = str(preflight._PreflightError(category))
            assert all(marker not in public for marker in markers)

    def test_before_after_mutation_is_detected_without_publication(self, exact_snapshot, tmp_path, monkeypatch):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        monkeypatch.setattr(preflight, "_discover_dependency_versions", _safe_dependencies)
        calls = {"count": 0}

        def launcher(mode, bundle, model, observations):
            calls["count"] += 1
            result = _fake_launcher(mode, bundle, model, observations)
            if calls["count"] == 2:
                bundle.qa_source.write_bytes(bundle.qa_source.read_bytes() + b"mutation")
            return result

        original = paths.qa_source.read_bytes()
        try:
            with pytest.raises(preflight._PreflightError, match="^B4_RESOURCE_MUTATED$"):
                preflight._preflight_with_paths(paths, launcher)
            assert not paths.evidence_root.exists()
        finally:
            paths.qa_source.write_bytes(original)

    def test_every_failure_preserves_inputs_and_existing_b2_b3_sentinels_byte_for_byte(self, exact_snapshot, tmp_path, monkeypatch):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        before_b2 = (exact_snapshot["repository"].joinpath(*preflight._B2_RELATIVE_ROOT.split("/")) / "sentinel.bin").read_bytes()
        before_b3 = (exact_snapshot["repository"].joinpath(*preflight._B3_RELATIVE_ROOT.split("/")) / "sentinel.bin").read_bytes()
        monkeypatch.setattr(preflight, "_discover_dependency_versions", lambda: (_ for _ in ()).throw(preflight._PreflightError("B4_DEPENDENCY_UNAVAILABLE")))
        with pytest.raises(preflight._PreflightError):
            preflight._preflight_with_paths(paths, _fake_launcher)
        assert (exact_snapshot["repository"].joinpath(*preflight._B2_RELATIVE_ROOT.split("/")) / "sentinel.bin").read_bytes() == before_b2
        assert (exact_snapshot["repository"].joinpath(*preflight._B3_RELATIVE_ROOT.split("/")) / "sentinel.bin").read_bytes() == before_b3

    def test_ast_has_no_provider_client_env_loader_generation_or_mutating_loader_path(self):
        parent_source = Path(preflight.__file__).read_text(encoding="utf-8")
        worker_source = Path(worker.__file__).read_text(encoding="utf-8")
        assert _static_import_boundary_violations(parent_source, worker_source) == ()

    def test_help_and_import_have_zero_resource_network_or_write_effects(self, capfd):
        before = set(Path(__file__).resolve().parents[1].glob("scripts/formal_evaluation_resource_preflight*"))
        assert preflight.main(["--help"]) == 0
        captured = capfd.readouterr()
        assert "usage:" in captured.out.lower()
        after = set(Path(__file__).resolve().parents[1].glob("scripts/formal_evaluation_resource_preflight*"))
        assert before == after

    def test_worker_protocol_rejects_booleans_for_every_integer_field(self):
        envelopes = {
            "resource": {
                "probe": "resource",
                "result": _resource_result("a" * 64, "b" * 64),
                "schema_version": 1,
                "status": "passed",
            },
            "model": {
                "probe": "model",
                "result": _model_result(),
                "schema_version": 1,
                "status": "passed",
            },
        }
        for mode, envelope in envelopes.items():
            paths = _integer_paths(envelope)
            assert paths
            for path in paths:
                for replacement in (True, False):
                    changed = copy.deepcopy(envelope)
                    _set_nested(changed, path, replacement)
                    process = preflight._WorkerProcessResultV1(
                        0, preflight._canonical_file_bytes(changed)
                    )
                    with pytest.raises(
                        preflight._PreflightError, match="^B4_INTERNAL_FAILURE$"
                    ):
                        decoded = preflight._decode_worker_result(mode, process)
                        if mode == "resource":
                            preflight._validate_resource_worker_result(decoded)
                        else:
                            preflight._validate_model_worker_result(decoded)

        failure = {
            "category": "B4_RESOURCE_MALFORMED",
            "schema_version": 1,
            "status": "failed",
        }
        for replacement in (True, False):
            changed = dict(failure, schema_version=replacement)
            with pytest.raises(preflight._PreflightError, match="^B4_INTERNAL_FAILURE$"):
                preflight._decode_worker_result(
                    "resource",
                    preflight._WorkerProcessResultV1(
                        2, preflight._canonical_file_bytes(changed)
                    ),
                )
        for replacement in (True, False):
            with pytest.raises(preflight._PreflightError, match="^B4_INTERNAL_FAILURE$"):
                preflight._decode_worker_result(
                    "resource",
                    preflight._WorkerProcessResultV1(
                        replacement,
                        preflight._canonical_file_bytes(envelopes["resource"]),
                    ),
                )

    def test_canonical_and_reopened_evidence_reject_boolean_for_every_integer_field(
        self, tmp_path
    ):
        material = _material()
        integer_paths = _integer_paths(material.artifact)
        assert len(integer_paths) >= 30
        final = tmp_path / preflight._EVIDENCE_FILENAME
        for path in integer_paths:
            for replacement in (True, False):
                changed = copy.deepcopy(material.artifact)
                _set_nested(changed, path, replacement)
                changed["preflight_sha256"] = preflight._preflight_sha(changed)
                with pytest.raises(
                    preflight._PreflightError, match="^B4_EVIDENCE_INVALID$"
                ):
                    preflight._validate_artifact(changed, transport)
                raw = preflight._canonical_file_bytes(changed)
                final.write_bytes(raw)
                with pytest.raises(
                    preflight._PreflightError, match="^B4_EVIDENCE_INVALID$"
                ):
                    preflight._read_existing_artifact(final, transport)
                assert final.read_bytes() == raw

    def test_reachable_taxonomy_precedence_not_tuple_order(
        self, exact_snapshot, tmp_path
    ):
        root = tmp_path / "worker"
        root.mkdir()
        snapshot = root / "snapshot"
        snapshot.mkdir()

        class NetworkThenIncompatible:
            def __init__(self, *_args, **_kwargs):
                try:
                    socket.socket()
                except BaseException as exc:
                    raise ValueError("SYNTHETIC_INCOMPATIBLE_SECRET") from exc

        with pytest.raises(worker._WorkerFailure, match="^B4_OFFLINE_VIOLATION$"):
            worker._execute(
                "model",
                worker._ModelRequest(root, snapshot),
                importer=_model_importer(
                    NetworkThenIncompatible, lambda a, b: np.array([[0.0]])
                ),
                source_environment={"PATH": "synthetic"},
            )

        paths = _paths(exact_snapshot, tmp_path / "evidence")
        stale = _material().artifact_bytes
        paths.evidence_root.mkdir()
        (paths.evidence_root / preflight._EVIDENCE_FILENAME).write_bytes(stale)
        before = (paths.evidence_root / preflight._EVIDENCE_FILENAME).read_bytes()
        with pytest.raises(preflight._PreflightError, match="^B4_EVIDENCE_STALE$"):
            preflight._publish_candidate(
                paths.evidence_root,
                preflight._canonical_file_bytes(
                    dict(_material().artifact, preflight_sha256="0" * 64)
                ),
                transport,
            )
        assert (paths.evidence_root / preflight._EVIDENCE_FILENAME).read_bytes() == before

    def test_parent_offline_attempt_overrides_existing_parent_failure(
        self, exact_snapshot, tmp_path, monkeypatch
    ):
        paths = _paths(exact_snapshot, tmp_path / "evidence")

        def attempted_then_replaced(_transport):
            try:
                socket.socket()
            except BaseException as exc:
                raise preflight._PreflightError("B4_AUTHORITY_INVALID") from exc

        monkeypatch.setattr(
            preflight, "_validate_authority_contract", attempted_then_replaced
        )
        with pytest.raises(preflight._PreflightError, match="^B4_OFFLINE_VIOLATION$"):
            preflight._preflight_with_paths(paths, _fake_launcher)
        assert not paths.evidence_root.exists()

    def test_synthetic_third_party_markers_never_reach_public_streams_or_evidence(
        self, tmp_path, monkeypatch, capfd
    ):
        markers = (
            "SYNTHETIC_CREDENTIAL",
            "SYNTHETIC_TOKEN",
            "SYNTHETIC_ENV_VALUE",
            "C:\\private\\absolute",
            "C:\\model-cache",
            "synthetic.invalid",
            "https://synthetic.invalid/path",
            "ValueError",
            "Traceback (most recent call last)",
            "SYNTHETIC_ROW_LEVEL_CONTENT",
            "[0.125,0.25]",
        )

        def failure():
            try:
                raise ValueError(" ".join(markers))
            except ValueError as exc:
                raise preflight._PreflightError("B4_INTERNAL_FAILURE") from exc

        monkeypatch.setattr(preflight, "preflight_production_resources", failure)
        assert preflight.main([]) == 2
        captured = capfd.readouterr()
        public = captured.out + captured.err
        assert captured.out == ""
        assert captured.err == "B4_INTERNAL_FAILURE\n"
        assert all(marker not in public for marker in markers)
        assert not (tmp_path / preflight._EVIDENCE_FILENAME).exists()

    @pytest.mark.parametrize(
        "role,mutant",
        [
            ("parent", "import openai\n"),
            ("parent", "from openai import OpenAI as Provider\n"),
            ("parent", "import formal_evaluation_provider as provider\n"),
            (
                "parent",
                "from formal_evaluation_transport import parse_deepseek_config as config\n",
            ),
            ("parent", "import formal_evaluation_config as configuration\n"),
            ("parent", "import numpy as optional_data\n"),
            (
                "worker",
                "def _import_resource_dependencies():\n    import torch as wrong_partition\n",
            ),
            (
                "worker",
                "def _import_model_dependencies():\n    import pandas as wrong_partition\n",
            ),
            (
                "parent",
                "import importlib\nimportlib.import_module('openai')\n",
            ),
            (
                "parent",
                "import importlib as imports\ndynamic = getattr(imports, 'import_module')\ndynamic('openai')\n",
            ),
            (
                "parent",
                "import importlib as imports\ndynamic = imports.import_module\ndynamic('openai')\n",
            ),
            ("parent", "__import__('openai')\n"),
            (
                "parent",
                "from outputs.rag_answer_demo import load_or_create_cache as load\nload()\n",
            ),
            (
                "parent",
                "import outputs.rag_answer_demo as demo\ndemo.load_or_create_cache()\n",
            ),
        ],
    )
    def test_static_ast_audit_rejects_boundary_mutants(self, role, mutant):
        parent_source = mutant if role == "parent" else "import os\n"
        worker_source = mutant if role == "worker" else "import os\n"
        assert _static_import_boundary_violations(parent_source, worker_source)

    def test_static_ast_audit_accepts_valid_parent_and_worker_candidates(self):
        parent_source = Path(preflight.__file__).read_text(encoding="utf-8")
        worker_source = Path(worker.__file__).read_text(encoding="utf-8")
        assert _static_import_boundary_violations(parent_source, worker_source) == ()
        assert _static_import_boundary_violations(
            '"import openai; load_or_create_cache()"\n',
            "# import torch\n",
        ) == ()
        execute_source = Path(worker.__file__).read_text(encoding="utf-8")
        execute_tree = ast.parse(execute_source)
        execute = next(
            node
            for node in ast.walk(execute_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_execute"
        )
        with_controls = next(
            node.lineno
            for node in ast.walk(execute)
            if isinstance(node, ast.With)
            and any(
                isinstance(item.context_expr, ast.Name)
                and item.context_expr.id == "controls"
                for item in node.items
            )
        )
        optional_calls = [
            node.lineno
            for node in ast.walk(execute)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id
            in {"_import_resource_dependencies", "_import_model_dependencies"}
        ]
        assert optional_calls and all(with_controls < line for line in optional_calls)

    @pytest.mark.parametrize(
        "phase",
        ["authority", "dependency", "resource_worker", "model_worker", "evidence"],
    )
    def test_failure_phase_preservation_matrix(
        self, exact_snapshot, tmp_path, monkeypatch, phase
    ):
        paths = _paths(exact_snapshot, tmp_path / phase / "evidence")
        before = _inventory(exact_snapshot["repository"])
        monkeypatch.setattr(preflight, "_discover_dependency_versions", _safe_dependencies)

        if phase == "authority":
            monkeypatch.setattr(
                preflight,
                "_validate_authority_contract",
                lambda _transport: (_ for _ in ()).throw(
                    preflight._PreflightError("B4_AUTHORITY_INVALID")
                ),
            )
            category = "B4_AUTHORITY_INVALID"
            launcher = _fake_launcher
        elif phase == "dependency":
            monkeypatch.setattr(
                preflight,
                "_discover_dependency_versions",
                lambda: (_ for _ in ()).throw(
                    preflight._PreflightError("B4_DEPENDENCY_UNAVAILABLE")
                ),
            )
            category = "B4_DEPENDENCY_UNAVAILABLE"
            launcher = _fake_launcher
        elif phase in {"resource_worker", "model_worker"}:
            category = (
                "B4_RESOURCE_MALFORMED"
                if phase == "resource_worker"
                else "B4_RESOURCE_INCOMPATIBLE"
            )

            def launcher(mode, bundle, model, observations):
                if (phase == "resource_worker" and mode == "resource") or (
                    phase == "model_worker" and mode == "model"
                ):
                    failure = {
                        "category": category,
                        "schema_version": 1,
                        "status": "failed",
                    }
                    return preflight._WorkerProcessResultV1(
                        2, preflight._canonical_file_bytes(failure)
                    )
                return _fake_launcher(mode, bundle, model, observations)
        else:
            paths.evidence_root.mkdir(parents=True)
            invalid = paths.evidence_root / preflight._EVIDENCE_FILENAME
            invalid.write_bytes(b"{\n")
            category = "B4_EVIDENCE_INVALID"
            launcher = _fake_launcher
        with pytest.raises(preflight._PreflightError, match=f"^{category}$") as caught:
            preflight._preflight_with_paths(paths, launcher)
        assert str(caught.value) == category
        assert _inventory(exact_snapshot["repository"]) == before

    def test_success_preserves_all_resource_and_b2_b3_sentinel_inputs(
        self, exact_snapshot, tmp_path, monkeypatch
    ):
        paths = _paths(exact_snapshot, tmp_path / "evidence")
        before = _inventory(exact_snapshot["repository"])
        monkeypatch.setattr(preflight, "_discover_dependency_versions", _safe_dependencies)
        result = preflight._preflight_with_paths(paths, _fake_launcher)
        assert result.status == "passed"
        assert _inventory(exact_snapshot["repository"]) == before
        assert set(path.name for path in paths.evidence_root.iterdir()) == {
            preflight._LOCK_FILENAME,
            preflight._EVIDENCE_FILENAME,
        }
