from __future__ import annotations

import ast
import copy
import importlib
import inspect
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import formal_evaluation_inflight as f
import formal_evaluation_orchestration as o
import formal_evaluation_transport as t
import run_formal_evaluation as runner


TRANSPORT_SHA = "d" * 64
RUNTIME_SHA = "e" * 64
STAGE_A_MODULES = {
    "formal_evaluation_transport",
    "formal_evaluation_inflight",
}
TRACKER_PRIVATE_MEMBERS = {"_receipt", "_begin", "_fail", "_succeed"}


def stage_a_private_accesses(source: str) -> list[str]:
    """Return statically visible B1 accesses to prohibited Stage A internals."""

    tree = ast.parse(source)
    violations: list[str] = []
    module_aliases: set[str] = set()
    builtins_aliases: set[str] = set()
    tracker_types = {"ProviderCallTracker"}
    tracker_names = {"tracker"}
    string_aliases: dict[str, str] = {}
    ambiguous_strings: set[str] = set()
    callable_aliases: dict[str, tuple[str, str | None]] = {
        "getattr": ("getattr", None),
        "vars": ("vars", None),
    }
    ambiguous_callables: set[str] = set()
    dict_aliases: dict[str, str] = {}
    ambiguous_dicts: set[str] = set()
    assignments: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in STAGE_A_MODULES:
            for alias in node.names:
                local_name = alias.asname or alias.name
                if alias.name.startswith("_"):
                    violations.append(f"private_import:{alias.name}")
                if alias.name == "ProviderCallTracker":
                    tracker_types.add(local_name)
        elif isinstance(node, ast.ImportFrom) and node.module == "builtins":
            for alias in node.names:
                if alias.name in {"getattr", "vars"}:
                    callable_aliases[alias.asname or alias.name] = (
                        alias.name,
                        None,
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in STAGE_A_MODULES:
                    module_aliases.add(alias.asname or alias.name)
                elif alias.name == "builtins":
                    builtins_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, node.value))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                assignments.append((node.target.id, node.value))

    def string_arg(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return string_aliases.get(node.id)
        return None

    def is_module(node: ast.AST) -> bool:
        return isinstance(node, ast.Name) and node.id in module_aliases

    def is_tracker_type(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Name)
            and node.id in tracker_types
        ) or (
            isinstance(node, ast.Attribute)
            and is_module(node.value)
            and node.attr == "ProviderCallTracker"
        ) or (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in tracker_types
        )

    def is_tracker(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Name)
            and node.id in tracker_names
        ) or (
            isinstance(node, ast.Call)
            and is_tracker_type(node.func)
        )

    def callable_kind(node: ast.AST) -> tuple[str, str | None] | None:
        if isinstance(node, ast.Name):
            return callable_aliases.get(node.id)
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in builtins_aliases
            and node.attr in {"getattr", "vars"}
        ):
            return (node.attr, None)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "__getattribute__"
        ):
            if is_tracker(node.value):
                return ("bound_tracker_getattribute", None)
            if isinstance(node.value, ast.Name) and node.value.id == "object":
                return ("object_getattribute", None)
        if isinstance(node, ast.Attribute) and node.attr == "get":
            mapping_kind = dict_kind(node.value)
            if mapping_kind is not None:
                return ("dict_get", mapping_kind)
        return None

    def dict_kind(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return dict_aliases.get(node.id)
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "__dict__"
        ):
            if is_module(node.value):
                return "module"
            if is_tracker(node.value):
                return "tracker"
        if isinstance(node, ast.Call):
            kind = callable_kind(node.func)
            if kind == ("vars", None) and len(node.args) == 1:
                if is_module(node.args[0]):
                    return "module"
                if is_tracker(node.args[0]):
                    return "tracker"
        return None

    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            arguments = (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            )
            if node.args.vararg is not None:
                arguments.append(node.args.vararg)
            if node.args.kwarg is not None:
                arguments.append(node.args.kwarg)
            for argument in arguments:
                if (
                    argument.annotation is not None
                    and is_tracker_type(argument.annotation)
                    and argument.arg not in tracker_names
                ):
                    tracker_names.add(argument.arg)
                    changed = True
        for name, value in assignments:
            text = string_arg(value)
            if text is not None and name not in ambiguous_strings:
                existing_text = string_aliases.get(name)
                if existing_text is None:
                    string_aliases[name] = text
                    changed = True
                elif existing_text != text:
                    del string_aliases[name]
                    ambiguous_strings.add(name)
                    changed = True
            if isinstance(value, ast.Name):
                if value.id in module_aliases and name not in module_aliases:
                    module_aliases.add(name)
                    changed = True
                if value.id in tracker_names and name not in tracker_names:
                    tracker_names.add(name)
                    changed = True
            if is_tracker_type(value) and name not in tracker_types:
                tracker_types.add(name)
                changed = True
            kind = callable_kind(value)
            if kind is not None and name not in ambiguous_callables:
                existing_kind = callable_aliases.get(name)
                if existing_kind is None:
                    callable_aliases[name] = kind
                    changed = True
                elif existing_kind != kind:
                    del callable_aliases[name]
                    ambiguous_callables.add(name)
                    changed = True
            mapping_kind = dict_kind(value)
            if mapping_kind is not None and name not in ambiguous_dicts:
                existing_mapping = dict_aliases.get(name)
                if existing_mapping is None:
                    dict_aliases[name] = mapping_kind
                    changed = True
                elif existing_mapping != mapping_kind:
                    del dict_aliases[name]
                    ambiguous_dicts.add(name)
                    changed = True
            if isinstance(value, ast.Call):
                if is_tracker(value) and name not in tracker_names:
                    tracker_names.add(name)
                    changed = True

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                is_module(node.value)
                and node.attr.startswith("_")
            ):
                violations.append(f"stage_a_attribute:{node.attr}")
            if is_tracker(node.value) and node.attr in TRACKER_PRIVATE_MEMBERS:
                violations.append(f"tracker_attribute:{node.attr}")
        if isinstance(node, ast.Subscript):
            member = string_arg(node.slice)
            target_kind = dict_kind(node.value)
            if member is not None and (
                (target_kind == "module" and member.startswith("_"))
                or (
                    target_kind == "tracker"
                    and member in TRACKER_PRIVATE_MEMBERS
                )
            ):
                violations.append(f"private_dict_access:{member}")
        if not isinstance(node, ast.Call):
            continue
        kind = callable_kind(node.func)
        if kind == ("getattr", None) and len(node.args) >= 2:
            target, member = node.args[0], string_arg(node.args[1])
            if (
                member is not None
                and (
                    (is_module(target) and member.startswith("_"))
                    or (
                        is_tracker(target)
                        and member in TRACKER_PRIVATE_MEMBERS
                    )
                )
            ):
                violations.append(f"indirect_getattr:{member}")
        elif kind == ("bound_tracker_getattribute", None) and node.args:
            member = string_arg(node.args[0])
            if member in TRACKER_PRIVATE_MEMBERS:
                violations.append(f"indirect_getattribute:{member}")
        elif kind == ("object_getattribute", None) and len(node.args) >= 2:
            member = string_arg(node.args[1])
            if is_tracker(node.args[0]) and member in TRACKER_PRIVATE_MEMBERS:
                violations.append(f"indirect_object_getattribute:{member}")
        elif (
            kind is not None
            and kind[0] == "dict_get"
            and node.args
        ):
            member = string_arg(node.args[0])
            target_kind = kind[1]
            if member is not None and (
                (target_kind == "module" and member.startswith("_"))
                or (
                    target_kind == "tracker"
                    and member in TRACKER_PRIVATE_MEMBERS
                )
            ):
                violations.append(f"private_dict_get:{member}")
    return violations


def resource_mapping(config: str) -> dict:
    identity = t.formal_identity(config)
    is_v2 = identity.resource_family == "v2_mixed"
    return {
        "schema_version": 1,
        "resource_type": "synthetic_fixture",
        "logical_resource_id": (
            f"synthetic_fixture_{identity.resource_family}_synthetic_v1"
        ),
        "system_config_id": config,
        "formal_system_id": identity.formal_system_id,
        "corpus_path": f"synthetic/{identity.resource_family}/corpus.json",
        "embeddings_path": f"synthetic/{identity.resource_family}/embeddings.npy",
        "corpus_sha256": "a" * 64,
        "embeddings_sha256": "b" * 64,
        "cache_family": identity.resource_family,
        "corpus_version": "synthetic_v1",
        "row_count": 15688 if is_v2 else 15333,
        "qa_count": 15333,
        "snippet_count": 355 if is_v2 else 0,
        "embedding_model": (
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
        "embedding_rows": 15688 if is_v2 else 15333,
        "embedding_dimensions": 384,
        "synthetic": True,
    }


def resources() -> o.SyntheticResourceBundle:
    return o.SyntheticResourceBundle.from_mappings(
        {config: resource_mapping(config) for config in o.SYSTEM_CONFIG_IDS}
    )


class Clock:
    def __init__(self, start: int = 0, events: list[str] | None = None):
        self.second = start
        self.events = events

    def __call__(self) -> str:
        value = f"2026-07-23T10:00:{self.second:02d}Z"
        if self.events is not None:
            self.events.append(f"clock:{self.second}")
        self.second += 1
        return value


class ProviderFailure(RuntimeError):
    def __init__(self, *, status_code=None, category=None):
        self.status_code = status_code
        self.category = category
        super().__init__("synthetic provider failure")


class FakeRawClient:
    def __init__(
        self,
        *,
        content: str = "synthetic provider output",
        error: BaseException | None = None,
        malformed: dict | None = None,
        events: list[str] | None = None,
        extra_fields: bool = False,
    ):
        self.content = content
        self.error = error
        self.malformed = malformed
        self.events = events
        self.extra_fields = extra_fields
        self.expected_request_id: str | None = None
        self.calls: list[dict] = []

    def create(self, **request):
        if self.events is not None:
            self.events.append("fake_client")
        self.calls.append(copy.deepcopy(request))
        if self.error is not None:
            raise self.error
        if self.malformed is not None:
            return copy.deepcopy(self.malformed)
        response = {
            "request_id": self.expected_request_id,
            "id": "synthetic_response_1",
            "choices": [{"message": {"content": self.content}}],
        }
        if self.extra_fields:
            response["synthetic_ignored_metadata"] = "allowed_by_stage_a"
        return response


def snapshot(unit: dict, text: str) -> dict:
    return {
        "schema_version": 1,
        "completed_turn_index": 1,
        "conversation_state": {
            "current_topic": "none",
            "query_type": "normal",
            "risk_type": "none",
            "last_safe_answer_type": "none",
            "last_user_query": unit["payload"]["user_input"],
            "last_assistant_answer": text,
            "last_retrieval_query": "",
            "last_contextual_query": "",
            "last_successful_contextual_query": "",
            "requires_backend_api": False,
            "should_reset": False,
            "state_confidence": 0.0,
            "state_turn_count": 0,
            "updated_at_turn": 1,
        },
        "previous_user_text": unit["payload"]["user_input"],
        "previous_assistant_text": text,
    }


def validate_synthetic_snapshot(value: dict) -> dict:
    top_fields = {
        "schema_version",
        "completed_turn_index",
        "conversation_state",
        "previous_user_text",
        "previous_assistant_text",
    }
    state_fields = {
        "current_topic",
        "query_type",
        "risk_type",
        "last_safe_answer_type",
        "last_user_query",
        "last_assistant_answer",
        "last_retrieval_query",
        "last_contextual_query",
        "last_successful_contextual_query",
        "requires_backend_api",
        "should_reset",
        "state_confidence",
        "state_turn_count",
        "updated_at_turn",
    }
    if (
        type(value) is not dict
        or set(value) != top_fields
        or value.get("schema_version") != 1
        or value.get("completed_turn_index") != 1
        or type(value.get("conversation_state")) is not dict
        or set(value["conversation_state"]) != state_fields
    ):
        raise ValueError("synthetic snapshot invalid")
    return copy.deepcopy(value)


def core_result(
    text: str,
    *,
    route: str,
    unit: dict | None = None,
    extra: dict | None = None,
) -> dict:
    result = {
        "response_text": text,
        "route": route,
        "guard_category": "synthetic_validation",
        "requires_backend_api": False,
        "retrieval_used": route == "provider",
        "retrieved_document_ids": ["synthetic_doc"] if route == "provider" else [],
        "retrieved_scores": [0.5] if route == "provider" else [],
    }
    if unit is not None:
        result["runtime_snapshot"] = snapshot(unit, text)
    if extra:
        result.update(extra)
    return result


class ExecutorSpy:
    def __init__(
        self,
        *,
        client: FakeRawClient,
        mode: str = "local",
        overrides: dict | None = None,
        fallback: bool = False,
        answer: str | None = None,
    ):
        self.client = client
        self.mode = mode
        self.overrides = overrides or {}
        self.fallback = fallback
        self.answer = answer
        self.calls: list[o.ExecutorContext] = []

    def __call__(self, context: o.ExecutorContext) -> dict:
        self.calls.append(context)
        is_turn_one = (
            context.identity.rq == "RQ3"
            and context.identity.system_config_id == "context_aware"
            and context.identity.turn_index == 1
        )
        if self.mode == "local":
            text = self.answer or "synthetic local output"
            return core_result(
                text,
                route="local_guard",
                unit=dict(context.unit) if is_turn_one else None,
            )
        self.client.expected_request_id = f.derive_provider_request_id(context.identity)
        try:
            normalized = context.invoke_provider(
                [{"role": "user", "content": "synthetic request"}],
                **self.overrides,
            )
        except t.TransportError:
            if not self.fallback:
                raise
            return core_result("synthetic fallback", route="local_guard")
        text = self.answer if self.answer is not None else normalized.content
        return core_result(
            text,
            route="provider",
            unit=dict(context.unit) if is_turn_one else None,
        )


def registry_for(
    selected_config: str,
    selected: ExecutorSpy,
    *,
    other_calls: list[str] | None = None,
) -> o.ExecutorRegistry:
    mapping = {}
    for config in o.SYSTEM_CONFIG_IDS:
        if config == selected_config:
            mapping[config] = selected
        else:
            def other(_context, name=config):
                if other_calls is not None:
                    other_calls.append(name)
                raise AssertionError("foreign executor called")
            mapping[config] = other
    return o.ExecutorRegistry(mapping)


class OrchestrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = runner.build_plan()
        cls.bundle = resources()

    def unit(self, *, config="v2", rq=None, turn=1) -> dict:
        return next(
            unit
            for unit in self.plan
            if unit["system_config_id"] == config
            and unit["turn_index"] == turn
            and (rq is None or unit["rq"] == rq)
        )

    def dependencies(
        self,
        unit: dict,
        executor: ExecutorSpy,
        client: FakeRawClient,
        *,
        clock: Clock | None = None,
    ) -> dict:
        return {
            "resources": self.bundle,
            "executors": registry_for(unit["system_config_id"], executor),
            "fake_raw_client": client,
            "clock": clock or Clock(),
            "transport_implementation_sha256": TRANSPORT_SHA,
            "runtime_identity_sha256": RUNTIME_SHA,
            "snapshot_validator": validate_synthetic_snapshot,
        }

    def execute(
        self,
        unit: dict,
        executor: ExecutorSpy,
        client: FakeRawClient,
        **extra,
    ) -> o.OrchestrationOutcome:
        dependencies = self.dependencies(
            unit, executor, client, clock=extra.pop("clock", None)
        )
        dependencies.update(extra)
        return runner.orchestrate_offline_unit(
            self.plan, unit, **dependencies
        )

    def test_import_is_offline_and_does_not_import_real_systems(self):
        source = (ROOT / "scripts/formal_evaluation_orchestration.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        forbidden = {
            "formal_evaluation_runtime",
            "rag_answer_demo",
            "formal_qa_only_baseline",
            "openai",
            "dotenv",
        }
        self.assertTrue(imported.isdisjoint(forbidden))
        self.assertNotIn("os", imported)
        original_getenv = os.getenv
        original_socket = socket.socket
        try:
            os.getenv = lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("environment access")
            )
            socket.socket = lambda *_a, **_k: (_ for _ in ()).throw(
                AssertionError("network access")
            )
            sys.modules.pop("formal_evaluation_orchestration", None)
            imported_module = importlib.import_module(
                "formal_evaluation_orchestration"
            )
            self.assertEqual(imported_module.PLAN_FINGERPRINT, runner.PLAN_FINGERPRINT)
        finally:
            os.getenv = original_getenv
            socket.socket = original_socket
            sys.modules["formal_evaluation_orchestration"] = o

    def test_fresh_interpreter_public_interfaces_exclude_runtime_and_core(self):
        probe = r"""
import copy
import importlib
import importlib.abc
import pathlib
import sys
from unittest import mock

interface, mode, root_text = sys.argv[1:]
root = pathlib.Path(root_text)
sys.path.insert(0, str(root / "scripts"))
prohibited = (
    "formal_evaluation_runtime",
    "rag_answer_demo",
    "outputs.rag_answer_demo",
    "formal_qa_only_baseline",
    "scripts.formal_qa_only_baseline",
)
attempted = []

class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in prohibited):
            attempted.append(fullname)
            raise ImportError("prohibited real runtime/core import")
        return None

sys.meta_path.insert(0, Guard())
target_module = importlib.import_module(interface)
runner = (
    target_module
    if interface == "run_formal_evaluation"
    else importlib.import_module("run_formal_evaluation")
)
orchestration = (
    target_module
    if interface == "formal_evaluation_orchestration"
    else importlib.import_module("formal_evaluation_orchestration")
)
transport = importlib.import_module("formal_evaluation_transport")

def resource_mapping(config):
    identity = transport.formal_identity(config)
    is_v2 = identity.resource_family == "v2_mixed"
    return {
        "schema_version": 1,
        "resource_type": "synthetic_fixture",
        "logical_resource_id": (
            "synthetic_fixture_" + identity.resource_family + "_synthetic_v1"
        ),
        "system_config_id": config,
        "formal_system_id": identity.formal_system_id,
        "corpus_path": "synthetic/" + identity.resource_family + "/corpus.json",
        "embeddings_path": (
            "synthetic/" + identity.resource_family + "/embeddings.npy"
        ),
        "corpus_sha256": "a" * 64,
        "embeddings_sha256": "b" * 64,
        "cache_family": identity.resource_family,
        "corpus_version": "synthetic_v1",
        "row_count": 15688 if is_v2 else 15333,
        "qa_count": 15333,
        "snippet_count": 355 if is_v2 else 0,
        "embedding_model": (
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        ),
        "embedding_rows": 15688 if is_v2 else 15333,
        "embedding_dimensions": 384,
        "synthetic": True,
    }

plan = runner.build_plan()
unit = next(
    item for item in plan
    if item["rq"] == "RQ2" and item["system_config_id"] == "v2"
)
counts = {"plan": 0, "resource": 0, "executor": 0, "client": 0}
resources = orchestration.SyntheticResourceBundle.from_mappings(
    {
        config: resource_mapping(config)
        for config in orchestration.SYSTEM_CONFIG_IDS
    }
)

def local_executor(context):
    counts["executor"] += 1
    return {
        "response_text": "synthetic local output",
        "route": "local_guard",
        "guard_category": "synthetic_validation",
        "requires_backend_api": False,
        "retrieval_used": False,
        "retrieved_document_ids": [],
        "retrieved_scores": [],
    }

executors = orchestration.ExecutorRegistry(
    {config: local_executor for config in orchestration.SYSTEM_CONFIG_IDS}
)

class Client:
    def create(self, **request):
        counts["client"] += 1
        raise AssertionError("fake client must not be called")

tick = [0]
def clock():
    value = "2026-07-23T10:00:%02dZ" % tick[0]
    tick[0] += 1
    return value

dependencies = {
    "resources": resources,
    "executors": executors,
    "fake_raw_client": Client(),
    "clock": clock,
    "transport_implementation_sha256": "d" * 64,
    "runtime_identity_sha256": "e" * 64,
    "snapshot_validator": lambda value: copy.deepcopy(value),
}
entry = (
    runner.orchestrate_offline_unit
    if interface == "run_formal_evaluation"
    else orchestration.orchestrate_validated_unit
)
original_resource_for = orchestration.SyntheticResourceBundle.resource_for
original_validate_plan = runner.validate_plan
def counted_validate_plan(value):
    counts["plan"] += 1
    return original_validate_plan(value)

def counted_resource_for(self, config):
    counts["resource"] += 1
    return original_resource_for(self, config)

with mock.patch.object(
    runner,
    "validate_plan",
    counted_validate_plan,
), mock.patch.object(
    orchestration.SyntheticResourceBundle,
    "resource_for",
    counted_resource_for,
):
    if mode == "valid":
        outcome = entry(plan, unit, **dependencies)
        assert outcome.action == "local_success"
        assert counts == {
            "plan": 1,
            "resource": 1,
            "executor": 1,
            "client": 0,
        }
    else:
        mismatch_path = "evaluation/formal_rq2_boundary_cases.json"
        def mismatched_file_sha(path):
            relative = path.relative_to(runner.ROOT).as_posix()
            return "0" * 64 if relative == mismatch_path else runner.FROZEN[relative]
        runner.file_sha = mismatched_file_sha
        outcome = None
        try:
            entry(plan, unit, **dependencies)
        except runner.Blocked as exc:
            assert str(exc) == (
                "BLOCKED FROZEN INPUT SHA MISMATCH: " + mismatch_path
            )
        else:
            raise AssertionError("frozen mismatch was accepted")
        assert outcome is None
        assert counts == {
            "plan": 0,
            "resource": 0,
            "executor": 0,
            "client": 0,
        }

assert attempted == []
assert not any(
    any(name == blocked or name.startswith(blocked + ".") for blocked in prohibited)
    for name in sys.modules
)
"""
        for interface in (
            "run_formal_evaluation",
            "formal_evaluation_orchestration",
        ):
            for mode in ("valid", "mismatch"):
                with self.subTest(interface=interface, mode=mode):
                    completed = subprocess.run(
                        [
                            sys.executable,
                            "-I",
                            "-c",
                            probe,
                            interface,
                            mode,
                            str(ROOT),
                        ],
                        cwd=ROOT,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(
                        completed.returncode,
                        0,
                        msg=completed.stderr,
                    )
                    self.assertEqual(completed.stdout, "")

    def test_exact_dispatch_all_four_and_isolation(self):
        selections = (
            ("qa_only_reconstructed_baseline", "RQ1", 1),
            ("v2", "RQ2", 1),
            ("single_turn", "RQ3", 1),
            ("context_aware", "RQ3", 1),
        )
        for config, rq, turn in selections:
            with self.subTest(config=config):
                unit = self.unit(config=config, rq=rq, turn=turn)
                client = FakeRawClient()
                selected = ExecutorSpy(client=client, mode="local")
                others: list[str] = []
                deps = self.dependencies(unit, selected, client)
                deps["executors"] = registry_for(
                    config, selected, other_calls=others
                )
                outcome = runner.orchestrate_offline_unit(
                    self.plan, unit, **deps
                )
                self.assertEqual(outcome.action, "local_success")
                self.assertEqual(
                    outcome.identity.formal_system_id,
                    t.formal_identity(config).formal_system_id,
                )
                self.assertEqual(len(selected.calls), 1)
                self.assertEqual(others, [])
                self.assertEqual(client.calls, [])

    def test_unknown_and_mismatched_dispatch_fail_before_invocation(self):
        client = FakeRawClient()
        executor = ExecutorSpy(client=client)
        calls = []
        mapping = {name: executor for name in o.SYSTEM_CONFIG_IDS}
        mapping["foreign"] = mapping.pop("v2")
        with self.assertRaises(o.OrchestrationError) as caught:
            o.ExecutorRegistry(mapping)
        self.assertEqual(caught.exception.category, "EXECUTOR_REGISTRY_INVALID")
        unit = self.unit()
        foreign_journal_outcome = self.execute(
            self.unit(config="qa_only_reconstructed_baseline"),
            ExecutorSpy(client=client),
            client,
        )
        with self.assertRaises(o.OrchestrationError) as caught:
            self.execute(
                unit,
                executor,
                client,
                journal=foreign_journal_outcome.journal,
                clock=Clock(10),
            )
        self.assertEqual(caught.exception.category, "JOURNAL_IDENTITY_MISMATCH")
        self.assertEqual(executor.calls, [])
        self.assertEqual(client.calls, [])
        self.assertEqual(calls, [])

    def test_frozen_plan_accepts_exact_aggregate_authority(self):
        runner.validate_plan(copy.deepcopy(self.plan))
        self.assertEqual(len(self.plan), 190)
        self.assertEqual(len({unit["request_id"] for unit in self.plan}), 190)
        self.assertEqual(
            [unit["execution_order"] for unit in self.plan], list(range(1, 191))
        )
        self.assertEqual(runner.plan_fingerprint(self.plan), runner.PLAN_FINGERPRINT)

    def test_frozen_byte_mismatch_precedes_all_b1_processing(self):
        unit = self.unit(config="v2", rq="RQ2")
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="provider")
        frozen_path = "evaluation/formal_rq2_boundary_cases.json"
        mismatched_hashes = runner.frozen_hashes()
        mismatched_hashes[frozen_path] = "0" * 64
        expected = f"BLOCKED FROZEN INPUT SHA MISMATCH: {frozen_path}"
        with mock.patch.object(
            runner, "frozen_hashes", return_value=mismatched_hashes
        ) as frozen_hash_boundary, mock.patch.object(
            runner, "validate_plan", autospec=True
        ) as plan_validation, mock.patch.object(
            o.SyntheticResourceBundle, "resource_for", autospec=True
        ) as resource_resolution:
            with self.assertRaises(runner.Blocked) as caught:
                runner.orchestrate_offline_unit(
                    self.plan,
                    unit,
                    **self.dependencies(unit, executor, client),
                )
        self.assertEqual(str(caught.exception), expected)
        frozen_hash_boundary.assert_called_once_with()
        plan_validation.assert_not_called()
        resource_resolution.assert_not_called()
        self.assertEqual(executor.calls, [])
        self.assertEqual(client.calls, [])

    def test_public_direct_interface_rejects_foreign_unit_before_invocation(self):
        foreign = copy.deepcopy(self.unit(config="v2", rq="RQ2"))
        foreign["request_id"] = "f" * 64
        foreign["payload"]["generation"]["temperature"] = 0.25
        foreign["payload_sha256"] = runner.sha(foreign["payload"])
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="provider")
        with mock.patch.object(
            o.SyntheticResourceBundle, "resource_for", autospec=True
        ) as resource_resolution:
            with self.assertRaises(runner.Blocked) as caught:
                o.orchestrate_validated_unit(
                    self.plan,
                    foreign,
                    **self.dependencies(foreign, executor, client),
                )
        self.assertEqual(
            str(caught.exception), "BLOCKED SELECTED PLAN UNIT MISMATCH"
        )
        resource_resolution.assert_not_called()
        self.assertEqual(executor.calls, [])
        self.assertEqual(client.calls, [])

    def _rewrite_request_id(self, unit: dict) -> None:
        frozen = unit["frozen_test_file_sha256"]
        unit["request_id"] = runner.derive(
            "formal-evaluation-request-id-v1",
            "1.0",
            unit["rq"],
            unit["case_id"],
            str(unit["turn_index"]),
            unit["system_config_id"],
            unit["input_sha256"],
            runner.generation_sha(),
            frozen,
        )

    def test_plan_validation_failures_are_exact_and_precede_execution(self):
        cases: list[tuple[str, list[dict], str]] = []

        discontinuous = copy.deepcopy(self.plan)
        discontinuous[0]["execution_order"], discontinuous[1]["execution_order"] = (
            discontinuous[1]["execution_order"],
            discontinuous[0]["execution_order"],
        )
        cases.append(("order", discontinuous, "BLOCKED REQUEST PLAN EXECUTION ORDER"))

        wrong_rq = copy.deepcopy(self.plan)
        target = next(unit for unit in wrong_rq if unit["rq"] == "RQ1")
        target.pop("review_id")
        target["rq"] = "RQ2"
        target["payload"]["rq"] = "RQ2"
        target["frozen_test_file_sha256"] = runner.FROZEN[
            "evaluation/formal_rq2_boundary_cases.json"
        ]
        target["payload_sha256"] = runner.sha(target["payload"])
        self._rewrite_request_id(target)
        cases.append(("rq_count", wrong_rq, "BLOCKED REQUEST PLAN RQ COUNT"))

        wrong_system = copy.deepcopy(self.plan)
        target = next(
            unit
            for unit in wrong_system
            if unit["rq"] == "RQ1"
            and unit["system_config_id"] == "qa_only_reconstructed_baseline"
        )
        target["system_config_id"] = "v2"
        target["payload"]["system_config"] = "v2"
        target["case_id"] = "synthetic_system_count_case"
        target["review_id"] = target["case_id"]
        target["payload_sha256"] = runner.sha(target["payload"])
        self._rewrite_request_id(target)
        cases.append(
            ("system_count", wrong_system, "BLOCKED REQUEST PLAN SYSTEM COUNT")
        )

        duplicate = copy.deepcopy(self.plan)
        duplicate[1]["request_id"] = duplicate[0]["request_id"]
        cases.append(("duplicate", duplicate, "BLOCKED DUPLICATE REQUEST ID"))

        missing = copy.deepcopy(self.plan)
        missing[0].pop("payload_sha256")
        cases.append(("missing", missing, "BLOCKED FORMAL PLAN UNIT SCHEMA"))

        unsupported = copy.deepcopy(self.plan)
        unsupported[0]["system_config_id"] = "single_turn"
        cases.append(("unsupported", unsupported, "BLOCKED UNSUPPORTED PLAN UNIT"))

        altered = copy.deepcopy(self.plan)
        altered[0]["payload"]["user_input"] += " synthetic alteration"
        cases.append(
            ("payload", altered, "BLOCKED FORMAL PLAN PAYLOAD INTEGRITY")
        )

        fingerprint = copy.deepcopy(self.plan)
        old_case = fingerprint[0]["case_id"]
        pair = [
            unit
            for unit in fingerprint
            if unit["rq"] == "RQ1" and unit["case_id"] == old_case
        ]
        for unit in pair:
            unit["case_id"] = "synthetic_fingerprint_case"
            unit["review_id"] = unit["case_id"]
            self._rewrite_request_id(unit)
        cases.append(
            (
                "fingerprint",
                fingerprint,
                "BLOCKED FORMAL PLAN FINGERPRINT MISMATCH",
            )
        )

        for name, changed, category in cases:
            with self.subTest(name=name):
                client = FakeRawClient()
                selected = ExecutorSpy(client=client)
                with self.assertRaises(runner.Blocked) as caught:
                    runner.orchestrate_offline_unit(
                        changed,
                        changed[0],
                        **self.dependencies(changed[0], selected, client),
                    )
                self.assertEqual(str(caught.exception), category)
                self.assertEqual(selected.calls, [])
                self.assertEqual(client.calls, [])

    def test_complete_plan_mutation_matrix_precedes_all_b1_activity(self):
        cases: list[tuple[str, list[dict], str]] = []

        wrong_total = copy.deepcopy(self.plan)
        wrong_total.pop()
        cases.append(
            ("wrong_total", wrong_total, "BLOCKED REQUEST PLAN COUNT")
        )

        extra_unit_field = copy.deepcopy(self.plan)
        extra_unit_field[0]["prohibited_extra"] = "synthetic"
        cases.append(
            (
                "extra_unit_field",
                extra_unit_field,
                "BLOCKED FORMAL PLAN UNIT SCHEMA",
            )
        )

        extra_payload_field = copy.deepcopy(self.plan)
        extra_payload_field[0]["payload"]["prohibited_extra"] = "synthetic"
        cases.append(
            (
                "extra_payload_field",
                extra_payload_field,
                "BLOCKED FORMAL PLAN UNIT SCHEMA",
            )
        )

        wrong_request_id = copy.deepcopy(self.plan)
        wrong_request_id[0]["request_id"] = "f" * 64
        cases.append(
            (
                "wrong_request_id",
                wrong_request_id,
                "BLOCKED FORMAL PLAN REQUEST ID",
            )
        )

        wrong_generation = copy.deepcopy(self.plan)
        generation_target = wrong_generation[0]
        generation_target["payload"]["generation"] = copy.deepcopy(
            generation_target["payload"]["generation"]
        )
        generation_target["payload"]["generation"]["temperature"] = 0.25
        generation_target["payload_sha256"] = runner.sha(
            generation_target["payload"]
        )
        self.assertEqual(
            sum(
                unit["payload"]["generation"] != runner.GENERATION
                for unit in wrong_generation
            ),
            1,
        )
        self.assertEqual(
            generation_target["payload_sha256"],
            runner.sha(generation_target["payload"]),
        )
        cases.append(
            (
                "wrong_generation",
                wrong_generation,
                "BLOCKED FORMAL PLAN PAYLOAD INTEGRITY",
            )
        )

        malformed_history = copy.deepcopy(self.plan)
        history_target = next(
            unit
            for unit in malformed_history
            if unit["rq"] == "RQ3"
            and unit["system_config_id"] == "context_aware"
            and unit["turn_index"] == 2
        )
        history_target["payload"]["history"][0]["assistant_answer"] = (
            "__MALFORMED_HISTORY_MARKER__"
        )
        history_target["payload_sha256"] = runner.sha(history_target["payload"])
        cases.append(
            (
                "malformed_rq3_history",
                malformed_history,
                "BLOCKED FORMAL PLAN PAYLOAD INTEGRITY",
            )
        )

        altered_frozen_identity = copy.deepcopy(self.plan)
        altered_frozen_identity[0]["frozen_test_file_sha256"] = "0" * 64
        cases.append(
            (
                "altered_frozen_identity",
                altered_frozen_identity,
                "BLOCKED FORMAL PLAN PAYLOAD INTEGRITY",
            )
        )

        incomplete_rq3_pair = copy.deepcopy(self.plan)
        pair_target = next(
            unit
            for unit in incomplete_rq3_pair
            if unit["rq"] == "RQ3"
            and unit["system_config_id"] == "context_aware"
            and unit["turn_index"] == 2
        )
        pair_target["case_id"] = "synthetic_incomplete_rq3_pair"
        self._rewrite_request_id(pair_target)
        cases.append(
            (
                "incomplete_rq3_pair",
                incomplete_rq3_pair,
                "BLOCKED INCOMPLETE CASE IDS",
            )
        )

        prohibited_modules = (
            "formal_evaluation_runtime",
            "rag_answer_demo",
            "formal_qa_only_baseline",
        )
        for name, changed, category in cases:
            with self.subTest(name=name):
                self.assertFalse(
                    any(
                        loaded == prohibited
                        or loaded.startswith(prohibited + ".")
                        for loaded in sys.modules
                        for prohibited in prohibited_modules
                    )
                )
                unit = changed[0]
                client = FakeRawClient()
                selected = ExecutorSpy(client=client, mode="provider")
                outcome = None
                with mock.patch.object(
                    o.SyntheticResourceBundle, "resource_for", autospec=True
                ) as resource_resolution, mock.patch.object(
                    o, "_build_checkpoint", autospec=True
                ) as checkpoint_construction:
                    with self.assertRaises(runner.Blocked) as caught:
                        outcome = o.orchestrate_validated_unit(
                            changed,
                            unit,
                            **self.dependencies(unit, selected, client),
                        )
                self.assertEqual(str(caught.exception), category)
                resource_resolution.assert_not_called()
                checkpoint_construction.assert_not_called()
                self.assertIsNone(outcome)
                self.assertEqual(selected.calls, [])
                self.assertEqual(client.calls, [])
                self.assertFalse(
                    any(
                        loaded == prohibited
                        or loaded.startswith(prohibited + ".")
                        for loaded in sys.modules
                        for prohibited in prohibited_modules
                    )
                )

    def test_provider_success_fixed_request_identity_hashes_and_order(self):
        unit = self.unit(config="v2", rq="RQ1")
        events: list[str] = []
        client = FakeRawClient(events=events)
        executor = ExecutorSpy(client=client, mode="provider")
        outcome = self.execute(
            unit, executor, client, clock=Clock(events=events)
        )
        self.assertEqual(outcome.action, "success")
        self.assertEqual(outcome.recovery_action, "begin")
        self.assertEqual(outcome.tracker_state, "validated_success")
        self.assertEqual(outcome.provider_call_count, 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(events[:3], ["clock:0", "clock:1", "fake_client"])
        request = client.calls[0]
        self.assertEqual(
            request,
            {
                "model": "deepseek-chat",
                "temperature": 0.0,
                "top_p": 1.0,
                "max_tokens": 512,
                "stream": False,
                "messages": [
                    {"role": "user", "content": "synthetic request"}
                ],
            },
        )
        identity = outcome.identity
        self.assertEqual(
            identity.execution_unit_id,
            f.derive_execution_unit_id(
                plan_fingerprint=runner.PLAN_FINGERPRINT,
                request_id=unit["request_id"],
                execution_order=unit["execution_order"],
            ),
        )
        self.assertEqual(
            identity.turn_id,
            f.derive_turn_id(
                execution_unit_id=identity.execution_unit_id,
                rq=identity.rq,
                case_id=identity.case_id,
                turn_index=identity.turn_index,
            ),
        )
        self.assertEqual(
            identity.attempt_id,
            f.derive_attempt_id(identity=identity, attempt_number=1),
        )
        self.assertEqual(
            outcome.authoritative_success.provider_request_id,
            f.derive_provider_request_id(identity),
        )
        self.assertEqual(
            outcome.authoritative_success.provider_response_sha256,
            t.sha256_text(client.content),
        )
        self.assertEqual(
            outcome.authoritative_success.response_sha256,
            t.sha256_text(client.content),
        )
        self.assertEqual(
            set(outcome.formal_result), set(t.SAFE_RESULT_FIELDS)
        )
        self.assertEqual(
            outcome.formal_result["response_text"], client.content
        )

    def test_invalid_generation_and_caller_ids_have_zero_client_calls(self):
        unit = self.unit()
        for mode in ("overrides", "claimed_ids"):
            with self.subTest(mode=mode):
                events: list[str] = []
                client = FakeRawClient(events=events)
                executor = ExecutorSpy(
                    client=client,
                    mode="provider",
                    overrides={"temperature": 0.2} if mode == "overrides" else None,
                )
                extra = (
                    {"claimed_ids": {"execution_unit_id": "foreign"}}
                    if mode == "claimed_ids"
                    else {}
                )
                with self.assertRaises(o.OrchestrationError) as caught:
                    self.execute(
                        unit,
                        executor,
                        client,
                        clock=Clock(events=events),
                        **extra,
                    )
                self.assertEqual(
                    caught.exception.category,
                    "FIXED_REQUEST_INVALID"
                    if mode == "overrides"
                    else "CALLER_IDENTITY_MISMATCH",
                )
                self.assertEqual(client.calls, [])
                self.assertNotIn("fake_client", events)

    def test_provider_core_mismatch_returns_non_recallable_recovery_evidence(self):
        unit = self.unit()
        mismatch_client = FakeRawClient()
        mismatch = ExecutorSpy(
            client=mismatch_client,
            mode="provider",
            answer="different core output",
        )
        failed = self.execute(unit, mismatch, mismatch_client)
        self.assertEqual(failed.action, "fail_closed")
        self.assertEqual(
            failed.failure_category, "PROVIDER_CORE_RESPONSE_MISMATCH"
        )
        self.assertEqual(failed.journal.state, "provider_returned")
        self.assertEqual(failed.identity.attempt_number, 1)
        self.assertEqual(len(mismatch.calls), 1)
        self.assertEqual(len(mismatch_client.calls), 1)
        self.assertIsNone(failed.formal_result)
        self.assertIsNone(failed.authoritative_success)

        stopped_client = FakeRawClient()
        stopped_executor = ExecutorSpy(
            client=stopped_client, mode="provider"
        )
        stopped = self.execute(
            unit,
            stopped_executor,
            stopped_client,
            journal=failed.journal,
            clock=Clock(10),
        )
        self.assertEqual(stopped.action, "fail_closed")
        self.assertEqual(stopped.recovery_action, "fail_closed")
        self.assertEqual(stopped.identity.attempt_number, 1)
        self.assertEqual(stopped_executor.calls, [])
        self.assertEqual(stopped_client.calls, [])
        self.assertIsNone(stopped.formal_result)
        self.assertIsNone(stopped.authoritative_success)

    def _assert_swallowed_nonretryable(
        self,
        error: BaseException,
        *,
        state: str,
        category: str,
    ) -> None:
        unit = self.unit()
        client = FakeRawClient(error=error)
        executor = ExecutorSpy(
            client=client, mode="provider", fallback=True
        )
        failed = self.execute(unit, executor, client)
        self.assertEqual(failed.action, "fail_closed")
        self.assertEqual(failed.journal.state, state)
        self.assertEqual(failed.failure_category, category)
        self.assertEqual(failed.identity.attempt_number, 1)
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(len(client.calls), 1)
        self.assertIsNone(failed.formal_result)
        self.assertIsNone(failed.authoritative_success)

        stopped_client = FakeRawClient()
        stopped_executor = ExecutorSpy(
            client=stopped_client, mode="provider"
        )
        stopped = self.execute(
            unit,
            stopped_executor,
            stopped_client,
            journal=failed.journal,
            clock=Clock(10),
        )
        self.assertEqual(stopped.action, "fail_closed")
        self.assertEqual(stopped.recovery_action, "fail_closed")
        self.assertEqual(stopped.identity.attempt_number, 1)
        self.assertEqual(stopped.failure_category, category)
        self.assertEqual(stopped_executor.calls, [])
        self.assertEqual(stopped_client.calls, [])
        self.assertIsNone(stopped.formal_result)
        self.assertIsNone(stopped.authoritative_success)

    def test_executor_swallowed_terminal_failure_is_non_recallable(self):
        self._assert_swallowed_nonretryable(
            ProviderFailure(
                status_code=400, category="invalid_request"
            ),
            state="terminal_failed",
            category="invalid_request",
        )

    def test_executor_swallowed_uncertain_failure_is_non_recallable(self):
        self._assert_swallowed_nonretryable(
            TimeoutError("synthetic timeout"),
            state="uncertain",
            category="timeout",
        )

    def _assert_swallowed_retryable(self, status_code: int, category: str) -> None:
        unit = self.unit()
        first_client = FakeRawClient(
            error=ProviderFailure(status_code=status_code)
        )
        first_executor = ExecutorSpy(
            client=first_client, mode="provider", fallback=True
        )
        first = self.execute(unit, first_executor, first_client)
        self.assertEqual(first.action, "retry_available")
        self.assertEqual(first.journal.state, "retryable_failed")
        self.assertEqual(first.failure_category, category)
        self.assertEqual(first.identity.attempt_number, 1)
        self.assertEqual(len(first_executor.calls), 1)
        self.assertEqual(len(first_client.calls), 1)
        self.assertIsNone(first.formal_result)
        self.assertIsNone(first.authoritative_success)

        retry_client = FakeRawClient()
        retry_executor = ExecutorSpy(client=retry_client, mode="provider")
        retried = self.execute(
            unit,
            retry_executor,
            retry_client,
            journal=first.journal,
            clock=Clock(10),
        )
        self.assertEqual(retried.action, "success")
        self.assertEqual(retried.recovery_action, "retry")
        self.assertEqual(retried.identity.attempt_number, 2)
        self.assertIs(retried.predecessor_journal, first.journal)
        self.assertEqual(len(retry_executor.calls), 1)
        self.assertEqual(len(retry_client.calls), 1)
        self.assertEqual(
            retried.identity.attempt_id,
            f.derive_attempt_id(identity=retried.identity, attempt_number=2),
        )

        stopped_client = FakeRawClient()
        stopped_executor = ExecutorSpy(
            client=stopped_client, mode="provider"
        )
        stopped = self.execute(
            unit,
            stopped_executor,
            stopped_client,
            journal=retried.journal,
            clock=Clock(20),
        )
        self.assertEqual(stopped.action, "fail_closed")
        self.assertEqual(stopped.identity.attempt_number, 2)
        self.assertEqual(stopped_executor.calls, [])
        self.assertEqual(stopped_client.calls, [])

    def test_executor_swallowed_http_429_retries_once_through_stage_a(self):
        self._assert_swallowed_retryable(429, "http_429")

    def test_executor_swallowed_http_5xx_retries_once_through_stage_a(self):
        self._assert_swallowed_retryable(500, "http_5xx")

    def test_malformed_provider_responses_fail_closed(self):
        unit = self.unit()
        malformed_values = (
            {},
            {
                "request_id": "call_foreign",
                "id": "synthetic_response_1",
                "choices": [{"message": {"content": "synthetic"}}],
            },
            {
                "request_id": "call_placeholder",
                "id": "synthetic_response_1",
                "choices": [],
            },
        )
        for raw in malformed_values:
            with self.subTest(keys=tuple(raw)):
                client = FakeRawClient(malformed=raw)
                executor = ExecutorSpy(client=client, mode="provider")
                outcome = self.execute(unit, executor, client)
                self.assertEqual(outcome.action, "fail_closed")
                self.assertEqual(outcome.failure_category, "invalid_response")
                self.assertEqual(outcome.tracker_state, "post_call_terminal_failure")
                self.assertEqual(len(client.calls), 1)

    def test_stage_a_permitted_extra_raw_metadata_does_not_escape_projection(self):
        unit = self.unit()
        client = FakeRawClient(extra_fields=True)
        executor = ExecutorSpy(client=client, mode="provider")
        outcome = self.execute(unit, executor, client)
        self.assertEqual(outcome.action, "success")
        self.assertNotIn("synthetic_ignored_metadata", outcome.formal_result)

    def test_local_success_is_closed_not_called_and_provider_null(self):
        unit = self.unit()
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="local")
        outcome = self.execute(unit, executor, client)
        self.assertEqual(outcome.action, "local_success")
        self.assertEqual(outcome.tracker_state, "not_called")
        self.assertEqual(outcome.provider_call_count, 0)
        self.assertEqual(client.calls, [])
        self.assertFalse(outcome.formal_result["provider_called"])
        for field in (
            "provider_request_id",
            "provider_response_id",
            "provider_response_sha256",
            "call_started_at",
            "provider_returned_at",
            "committed_at",
            "authoritative_success",
        ):
            self.assertIsNone(outcome.formal_result[field])
        self.assertEqual(set(outcome.formal_result), set(t.SAFE_RESULT_FIELDS))

    def test_local_fabricated_evidence_and_invalid_matrix_are_rejected(self):
        unit = self.unit()
        client = FakeRawClient()

        def fabricated(_context):
            return core_result(
                "synthetic local",
                route="local_guard",
                extra={"provider_response_id": "fabricated"},
            )

        registry = {
            name: fabricated if name == unit["system_config_id"] else lambda _c: {}
            for name in o.SYSTEM_CONFIG_IDS
        }
        with self.assertRaises(o.OrchestrationError) as caught:
            runner.orchestrate_offline_unit(
                self.plan,
                unit,
                resources=self.bundle,
                executors=o.ExecutorRegistry(registry),
                fake_raw_client=client,
                clock=Clock(),
                transport_implementation_sha256=TRANSPORT_SHA,
                runtime_identity_sha256=RUNTIME_SHA,
                snapshot_validator=validate_synthetic_snapshot,
            )
        self.assertEqual(caught.exception.category, "CORE_RESULT_SCHEMA_INVALID")
        self.assertEqual(client.calls, [])

        def missing_provenance(_context):
            result = core_result("synthetic local", route="local_guard")
            result.pop("guard_category")
            return result

        missing_mapping = {
            name: missing_provenance
            if name == unit["system_config_id"]
            else lambda _c: {}
            for name in o.SYSTEM_CONFIG_IDS
        }
        with self.assertRaises(o.OrchestrationError) as caught:
            runner.orchestrate_offline_unit(
                self.plan,
                unit,
                resources=self.bundle,
                executors=o.ExecutorRegistry(missing_mapping),
                fake_raw_client=client,
                clock=Clock(),
                transport_implementation_sha256=TRANSPORT_SHA,
                runtime_identity_sha256=RUNTIME_SHA,
                snapshot_validator=validate_synthetic_snapshot,
            )
        self.assertEqual(caught.exception.category, "CORE_RESULT_SCHEMA_INVALID")
        self.assertEqual(client.calls, [])

        provider_client = FakeRawClient()
        provider = ExecutorSpy(client=provider_client, mode="provider")
        original = provider.__call__

        def provider_with_local_route(context):
            result = original(context)
            result["route"] = "local_guard"
            return result

        mapping = {
            name: provider_with_local_route
            if name == unit["system_config_id"]
            else lambda _c: {}
            for name in o.SYSTEM_CONFIG_IDS
        }
        failed = runner.orchestrate_offline_unit(
            self.plan,
            unit,
            resources=self.bundle,
            executors=o.ExecutorRegistry(mapping),
            fake_raw_client=provider_client,
            clock=Clock(),
            transport_implementation_sha256=TRANSPORT_SHA,
            runtime_identity_sha256=RUNTIME_SHA,
            snapshot_validator=validate_synthetic_snapshot,
        )
        self.assertEqual(failed.action, "fail_closed")
        self.assertEqual(
            failed.failure_category, "PROVIDER_PROVENANCE_INVALID"
        )
        self.assertEqual(failed.journal.state, "provider_returned")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(len(provider_client.calls), 1)
        self.assertIsNone(failed.formal_result)
        self.assertIsNone(failed.authoritative_success)

        stopped_client = FakeRawClient()
        stopped_executor = ExecutorSpy(
            client=stopped_client, mode="provider"
        )
        stopped = self.execute(
            unit,
            stopped_executor,
            stopped_client,
            journal=failed.journal,
            clock=Clock(10),
        )
        self.assertEqual(stopped.action, "fail_closed")
        self.assertEqual(stopped.identity.attempt_number, 1)
        self.assertEqual(stopped_executor.calls, [])
        self.assertEqual(stopped_client.calls, [])

    def test_recovery_begin_continue_and_success_decisions_call_correctly(self):
        unit = self.unit()
        local_client = FakeRawClient()
        local = ExecutorSpy(client=local_client)
        initial = self.execute(unit, local, local_client)
        self.assertEqual(initial.recovery_action, "begin")

        provider_client = FakeRawClient()
        provider = ExecutorSpy(client=provider_client, mode="provider")
        continued = self.execute(
            unit,
            provider,
            provider_client,
            journal=initial.journal,
            clock=Clock(10),
        )
        self.assertEqual(continued.recovery_action, "continue_before_provider")
        self.assertEqual(len(provider_client.calls), 1)

        no_call_client = FakeRawClient()
        no_call_executor = ExecutorSpy(client=no_call_client)
        authoritative = self.execute(
            unit,
            no_call_executor,
            no_call_client,
            authoritative_success=continued.authoritative_success,
            clock=Clock(20),
        )
        self.assertEqual(authoritative.action, "authoritative_success")
        self.assertEqual(authoritative.provider_call_count, 0)
        self.assertEqual(no_call_executor.calls, [])

        reconciled = self.execute(
            unit,
            no_call_executor,
            no_call_client,
            journal=continued.journal,
            authoritative_success=continued.authoritative_success,
            clock=Clock(30),
        )
        self.assertEqual(reconciled.action, "reconcile_committed")
        self.assertEqual(reconciled.journal.state, "committed")
        confirmed = self.execute(
            unit,
            no_call_executor,
            no_call_client,
            journal=reconciled.journal,
            authoritative_success=continued.authoritative_success,
            clock=Clock(40),
        )
        self.assertEqual(confirmed.action, "confirmed")
        self.assertEqual(no_call_executor.calls, [])
        self.assertEqual(no_call_client.calls, [])

    def test_retry_only_advances_one_attempt_and_complete_ids(self):
        unit = self.unit()
        first_client = FakeRawClient(error=ProviderFailure(status_code=429))
        first_executor = ExecutorSpy(client=first_client, mode="provider")
        first = self.execute(unit, first_executor, first_client)
        self.assertEqual(first.action, "retry_available")
        self.assertEqual(first.failure_category, "http_429")
        self.assertEqual(first.identity.attempt_number, 1)

        second_client = FakeRawClient()
        second_executor = ExecutorSpy(client=second_client, mode="provider")
        second = self.execute(
            unit,
            second_executor,
            second_client,
            journal=first.journal,
            clock=Clock(10),
        )
        self.assertEqual(second.recovery_action, "retry")
        self.assertEqual(second.identity.attempt_number, 2)
        self.assertIs(second.predecessor_journal, first.journal)
        self.assertEqual(len(second_client.calls), 1)
        self.assertEqual(
            second.identity.attempt_id,
            f.derive_attempt_id(identity=second.identity, attempt_number=2),
        )
        self.assertEqual(
            second.authoritative_success.provider_request_id,
            f.derive_provider_request_id(second.identity),
        )
        self.assertNotEqual(first.identity.attempt_id, second.identity.attempt_id)

    def test_unknown_recovery_action_and_incomplete_retry_evidence_fail_closed(self):
        unit = self.unit()
        client = FakeRawClient()
        executor = ExecutorSpy(client=client)
        original = o.recovery_decision
        try:
            o.recovery_decision = lambda *_a, **_k: "foreign_action"
            with self.assertRaises(o.OrchestrationError) as caught:
                self.execute(unit, executor, client)
            self.assertEqual(caught.exception.category, "UNKNOWN_RECOVERY_ACTION")
        finally:
            o.recovery_decision = original
        self.assertEqual(executor.calls, [])
        self.assertEqual(client.calls, [])

        failed_client = FakeRawClient(error=ProviderFailure(status_code=429))
        failed_executor = ExecutorSpy(client=failed_client, mode="provider")
        failed = self.execute(unit, failed_executor, failed_client)
        prepared_attempt_two = f.next_retry_journal(
            failed.journal, "2026-07-23T10:00:10Z"
        )
        no_call_client = FakeRawClient()
        no_call_executor = ExecutorSpy(client=no_call_client)
        with self.assertRaises(o.OrchestrationError) as caught:
            self.execute(
                unit,
                no_call_executor,
                no_call_client,
                journal=prepared_attempt_two,
                clock=Clock(20),
            )
        self.assertEqual(caught.exception.category, "RECOVERY_PREDECESSOR_REQUIRED")
        self.assertEqual(no_call_executor.calls, [])
        self.assertEqual(no_call_client.calls, [])

    def test_attempt_three_is_terminal_and_attempt_four_impossible(self):
        unit = self.unit()
        outcomes = []
        journal = None
        for index in range(3):
            client = FakeRawClient(error=ProviderFailure(status_code=500))
            executor = ExecutorSpy(client=client, mode="provider")
            outcome = self.execute(
                unit,
                executor,
                client,
                journal=journal,
                clock=Clock(index * 10),
            )
            outcomes.append(outcome)
            journal = outcome.journal
        self.assertEqual(
            [outcome.identity.attempt_number for outcome in outcomes], [1, 2, 3]
        )
        self.assertEqual(
            [outcome.action for outcome in outcomes],
            ["retry_available", "retry_available", "fail_closed"],
        )
        for attempt_number, outcome in enumerate(outcomes, 1):
            self.assertEqual(
                outcome.identity.attempt_id,
                f.derive_attempt_id(
                    identity=outcome.identity, attempt_number=attempt_number
                ),
            )
            self.assertEqual(
                f.derive_provider_request_id(outcome.identity),
                outcome.journal.provider_request_id,
            )
        blocked_client = FakeRawClient()
        blocked_executor = ExecutorSpy(client=blocked_client)
        stopped = self.execute(
            unit,
            blocked_executor,
            blocked_client,
            journal=journal,
            clock=Clock(40),
        )
        self.assertEqual(stopped.action, "fail_closed")
        self.assertEqual(stopped.provider_call_count, 0)
        self.assertEqual(blocked_executor.calls, [])
        self.assertEqual(blocked_client.calls, [])
        with self.assertRaises(f.JournalError) as caught:
            f.derive_attempt_id(identity=outcomes[-1].identity, attempt_number=4)
        self.assertEqual(caught.exception.category, "ATTEMPT_IDENTITY_INVALID")

    def test_uncertain_outcome_does_not_retry(self):
        unit = self.unit()
        client = FakeRawClient(error=TimeoutError("synthetic timeout"))
        executor = ExecutorSpy(client=client, mode="provider")
        failed = self.execute(unit, executor, client)
        self.assertEqual(failed.action, "fail_closed")
        self.assertEqual(failed.journal.state, "uncertain")
        self.assertEqual(failed.failure_category, "timeout")
        again_client = FakeRawClient()
        again_executor = ExecutorSpy(client=again_client)
        stopped = self.execute(
            unit,
            again_executor,
            again_client,
            journal=failed.journal,
            clock=Clock(10),
        )
        self.assertEqual(stopped.action, "fail_closed")
        self.assertEqual(stopped.failure_category, "timeout")
        self.assertEqual(again_executor.calls, [])
        self.assertEqual(again_client.calls, [])

    def _assert_terminal_category(
        self,
        category: str,
        *,
        error: BaseException | None = None,
        malformed: dict | None = None,
    ) -> None:
        unit = self.unit()
        client = FakeRawClient(error=error, malformed=malformed)
        executor = ExecutorSpy(client=client, mode="provider")
        failed = self.execute(unit, executor, client)
        self.assertEqual(failed.action, "fail_closed")
        self.assertEqual(failed.recovery_action, "begin")
        self.assertEqual(failed.journal.state, "terminal_failed")
        self.assertEqual(failed.journal.sanitized_outcome_category, category)
        self.assertEqual(failed.failure_category, category)
        self.assertEqual(failed.identity.attempt_number, 1)
        self.assertEqual(len(executor.calls), 1)
        self.assertEqual(len(client.calls), 1)
        self.assertIsNone(failed.formal_result)
        self.assertIsNone(failed.authoritative_success)

        stopped_client = FakeRawClient()
        stopped_executor = ExecutorSpy(client=stopped_client, mode="provider")
        stopped = self.execute(
            unit,
            stopped_executor,
            stopped_client,
            journal=failed.journal,
            clock=Clock(10),
        )
        self.assertEqual(stopped.action, "fail_closed")
        self.assertEqual(stopped.recovery_action, "fail_closed")
        self.assertEqual(stopped.failure_category, category)
        self.assertEqual(stopped.journal.sanitized_outcome_category, category)
        self.assertEqual(stopped.identity.attempt_number, 1)
        self.assertIsNone(stopped.predecessor_journal)
        self.assertIsNone(stopped.formal_result)
        self.assertIsNone(stopped.authoritative_success)
        self.assertEqual(stopped_executor.calls, [])
        self.assertEqual(stopped_client.calls, [])

    def test_authentication_failure_category_is_preserved_and_terminal(self):
        self._assert_terminal_category(
            "authentication_failure",
            error=ProviderFailure(
                status_code=401, category="authentication_failure"
            ),
        )

    def test_invalid_request_category_is_preserved_and_terminal(self):
        self._assert_terminal_category(
            "invalid_request",
            error=ProviderFailure(status_code=400, category="invalid_request"),
        )

    def test_generic_provider_rejection_category_is_preserved_and_terminal(self):
        self._assert_terminal_category(
            "provider_rejected",
            error=ProviderFailure(status_code=400),
        )

    def test_unknown_string_terminal_category_normalizes_to_provider_rejected(self):
        self._assert_terminal_category(
            "provider_rejected",
            error=ProviderFailure(
                status_code=403, category="permission_denied"
            ),
        )

    def test_non_string_terminal_category_normalizes_to_provider_rejected(self):
        self._assert_terminal_category(
            "provider_rejected",
            error=ProviderFailure(status_code=403, category=7),
        )

    def test_invalid_response_category_is_preserved_and_terminal(self):
        self._assert_terminal_category("invalid_response", malformed={})

    def test_conflict_and_direct_identity_mismatch_have_zero_calls(self):
        unit = self.unit()
        client = FakeRawClient()
        provider = ExecutorSpy(client=client, mode="provider")
        successful = self.execute(unit, provider, client)
        conflicting = successful.authoritative_success.to_dict()
        conflicting["provider_response_id"] = "synthetic_response_foreign"
        no_call_client = FakeRawClient()
        no_call = ExecutorSpy(client=no_call_client)
        with self.assertRaises(o.OrchestrationError) as caught:
            self.execute(
                unit,
                no_call,
                no_call_client,
                journal=successful.journal,
                authoritative_success=conflicting,
                clock=Clock(20),
            )
        self.assertEqual(caught.exception.category, "JOURNAL_EVIDENCE_CONFLICT")
        self.assertEqual(no_call.calls, [])
        self.assertEqual(no_call_client.calls, [])

        foreign_unit = self.unit(config="qa_only_reconstructed_baseline")
        foreign_client = FakeRawClient()
        foreign_executor = ExecutorSpy(client=foreign_client)
        foreign = self.execute(foreign_unit, foreign_executor, foreign_client)
        with self.assertRaises(o.OrchestrationError) as caught:
            self.execute(
                unit,
                no_call,
                no_call_client,
                journal=foreign.journal,
                clock=Clock(30),
            )
        self.assertEqual(caught.exception.category, "JOURNAL_IDENTITY_MISMATCH")
        self.assertEqual(no_call.calls, [])

    def test_wrong_resource_identity_fails_before_executor_and_client(self):
        mappings = {
            config: resource_mapping(config) for config in o.SYSTEM_CONFIG_IDS
        }
        mappings["v2"]["formal_system_id"] = "foreign_system"
        with self.assertRaises(o.OrchestrationError) as caught:
            o.SyntheticResourceBundle.from_mappings(mappings)
        self.assertEqual(caught.exception.category, "RESOURCE_IDENTITY_INVALID")
        with self.assertRaises(o.OrchestrationError) as caught:
            o.SyntheticResourceBundle(
                {"v2": t.ProductionResourceIdentity.from_mapping(resource_mapping("v2"))}
            )
        self.assertEqual(
            caught.exception.category, "SYNTHETIC_RESOURCE_BUNDLE_INVALID"
        )

    def _turn_one_checkpoint(self) -> tuple[dict, o.OrchestrationOutcome]:
        unit = self.unit(config="context_aware", rq="RQ3", turn=1)
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="local")
        outcome = self.execute(unit, executor, client)
        self.assertIsNotNone(outcome.checkpoint_evidence)
        return unit, outcome

    def test_rq3_turn_one_and_turn_two_exact_checkpoint_without_replay(self):
        turn_one, first = self._turn_one_checkpoint()
        turn_two = next(
            unit
            for unit in self.plan
            if unit["rq"] == "RQ3"
            and unit["system_config_id"] == "context_aware"
            and unit["case_id"] == turn_one["case_id"]
            and unit["turn_index"] == 2
        )
        client = FakeRawClient()
        second_executor = ExecutorSpy(client=client, mode="local")
        second = self.execute(
            turn_two,
            second_executor,
            client,
            checkpoint_evidence=first.checkpoint_evidence,
        )
        self.assertEqual(second.action, "local_success")
        self.assertEqual(len(second_executor.calls), 1)
        self.assertEqual(client.calls, [])
        self.assertEqual(
            second.identity.input_checkpoint_id,
            first.checkpoint_evidence.checkpoint_id,
        )
        self.assertEqual(
            second.identity.input_checkpoint_sha256,
            first.checkpoint_evidence.checkpoint_sha256,
        )
        self.assertEqual(
            dict(second_executor.calls[0].checkpoint_snapshot),
            dict(first.checkpoint_evidence.snapshot),
        )
        self.assertEqual(
            first.checkpoint_evidence.turn_one_resource_identity,
            self.bundle.resource_for("context_aware").to_dict(),
        )
        self.assertEqual(
            first.checkpoint_evidence.turn_one_resource_identity_sha256,
            t.resource_identity_sha256(
                self.bundle.resource_for("context_aware")
            ),
        )

    def test_rq3_checkpoint_is_bound_to_exact_resource_identity(self):
        turn_one, first = self._turn_one_checkpoint()
        turn_two = next(
            unit
            for unit in self.plan
            if unit["rq"] == "RQ3"
            and unit["system_config_id"] == "context_aware"
            and unit["case_id"] == turn_one["case_id"]
            and unit["turn_index"] == 2
        )
        mappings = {
            config: resource_mapping(config) for config in o.SYSTEM_CONFIG_IDS
        }
        mappings["context_aware"]["corpus_sha256"] = "c" * 64
        mappings["context_aware"]["embeddings_sha256"] = "d" * 64
        bundle_b = o.SyntheticResourceBundle.from_mappings(mappings)
        self.assertNotEqual(
            t.resource_identity_sha256(
                self.bundle.resource_for("context_aware")
            ),
            t.resource_identity_sha256(bundle_b.resource_for("context_aware")),
        )
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="provider")
        with self.assertRaises(o.OrchestrationError) as caught:
            self.execute(
                turn_two,
                executor,
                client,
                resources=bundle_b,
                checkpoint_evidence=first.checkpoint_evidence,
            )
        self.assertEqual(
            caught.exception.category,
            "CHECKPOINT_RESOURCE_IDENTITY_MISMATCH",
        )
        self.assertEqual(executor.calls, [])
        self.assertEqual(client.calls, [])

    def test_rq3_foreign_turn_two_pair_is_rejected_before_turn_one(self):
        turn_ones = [
            unit
            for unit in self.plan
            if unit["rq"] == "RQ3"
            and unit["system_config_id"] == "context_aware"
            and unit["turn_index"] == 1
        ]
        turn_one = turn_ones[0]
        foreign_turn_two = next(
            unit
            for unit in self.plan
            if unit["rq"] == "RQ3"
            and unit["system_config_id"] == "context_aware"
            and unit["turn_index"] == 2
            and unit["case_id"] != turn_one["case_id"]
        )
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="provider")
        outcome = None
        with self.assertRaises(runner.Blocked) as caught:
            outcome = o.orchestrate_validated_unit(
                self.plan,
                turn_one,
                turn_two_unit=foreign_turn_two,
                **self.dependencies(turn_one, executor, client),
            )
        self.assertEqual(str(caught.exception), "BLOCKED RQ3 PAIR MISMATCH")
        self.assertIsNone(outcome)
        self.assertEqual(executor.calls, [])
        self.assertEqual(client.calls, [])

    def test_rq3_checkpoint_failures_precede_executor_and_client(self):
        turn_one, first = self._turn_one_checkpoint()
        turn_two = next(
            unit
            for unit in self.plan
            if unit["rq"] == "RQ3"
            and unit["system_config_id"] == "context_aware"
            and unit["case_id"] == turn_one["case_id"]
            and unit["turn_index"] == 2
        )
        mutations: list[tuple[str, object, str]] = [
            ("missing", None, "TURN_TWO_CHECKPOINT_REQUIRED")
        ]
        for field, value in (
            ("checkpoint_id", "checkpoint_foreign"),
            ("checkpoint_sha256", "f" * 64),
            ("formal_system_id", "foreign_system"),
        ):
            changed = first.checkpoint_evidence.to_dict()
            changed[field] = value
            mutations.append((field, changed, "CHECKPOINT_EVIDENCE_MISMATCH"))
        malformed = first.checkpoint_evidence.to_dict()
        malformed["snapshot"]["conversation_state"].pop("current_topic")
        mutations.append(
            ("snapshot", malformed, "CHECKPOINT_SNAPSHOT_INVALID")
        )
        missing_resource = first.checkpoint_evidence.to_dict()
        missing_resource.pop("turn_one_resource_identity")
        mutations.append(
            ("missing_resource", missing_resource, "CHECKPOINT_EVIDENCE_INVALID")
        )
        extra_resource = first.checkpoint_evidence.to_dict()
        extra_resource["foreign_resource_evidence"] = {}
        mutations.append(
            ("extra_resource", extra_resource, "CHECKPOINT_EVIDENCE_INVALID")
        )
        malformed_resource = first.checkpoint_evidence.to_dict()
        malformed_resource["turn_one_resource_identity"]["corpus_path"] = (
            "/foreign/corpus.json"
        )
        mutations.append(
            (
                "malformed_resource",
                malformed_resource,
                "CHECKPOINT_RESOURCE_EVIDENCE_INVALID",
            )
        )
        foreign = first.checkpoint_evidence.to_dict()
        foreign["expected_turn_two_request_id"] = self.unit(
            config="context_aware", rq="RQ3", turn=2
        )["request_id"]
        if foreign["expected_turn_two_request_id"] == turn_two["request_id"]:
            foreign["expected_turn_two_request_id"] = "f" * 64
        mutations.append(
            ("foreign", foreign, "CHECKPOINT_EVIDENCE_MISMATCH")
        )

        for name, evidence, category in mutations:
            with self.subTest(name=name):
                client = FakeRawClient()
                executor = ExecutorSpy(client=client, mode="local")
                with self.assertRaises(o.OrchestrationError) as caught:
                    self.execute(
                        turn_two,
                        executor,
                        client,
                        checkpoint_evidence=evidence,
                    )
                self.assertEqual(caught.exception.category, category)
                self.assertEqual(executor.calls, [])
                self.assertEqual(client.calls, [])

    def test_rq3_turn_one_malformed_snapshot_rejected_without_client_call(self):
        unit = self.unit(config="context_aware", rq="RQ3", turn=1)
        client = FakeRawClient()

        def malformed(_context):
            result = core_result(
                "synthetic local output", route="local_guard", unit=unit
            )
            result["runtime_snapshot"]["conversation_state"].pop("current_topic")
            return result

        mapping = {
            name: malformed if name == "context_aware" else lambda _c: {}
            for name in o.SYSTEM_CONFIG_IDS
        }
        with self.assertRaises(o.OrchestrationError) as caught:
            runner.orchestrate_offline_unit(
                self.plan,
                unit,
                resources=self.bundle,
                executors=o.ExecutorRegistry(mapping),
                fake_raw_client=client,
                clock=Clock(),
                transport_implementation_sha256=TRANSPORT_SHA,
                runtime_identity_sha256=RUNTIME_SHA,
                snapshot_validator=validate_synthetic_snapshot,
            )
        self.assertEqual(caught.exception.category, "CHECKPOINT_SNAPSHOT_INVALID")
        self.assertEqual(client.calls, [])

    def test_provider_backed_invalid_turn_one_snapshot_is_non_recallable(self):
        unit = self.unit(config="context_aware", rq="RQ3", turn=1)
        client = FakeRawClient()
        executor_calls: list[o.ExecutorContext] = []

        def malformed_provider(context: o.ExecutorContext) -> dict:
            executor_calls.append(context)
            client.expected_request_id = f.derive_provider_request_id(
                context.identity
            )
            normalized = context.invoke_provider(
                [{"role": "user", "content": "synthetic request"}]
            )
            result = core_result(
                normalized.content,
                route="provider",
                unit=dict(context.unit),
            )
            result["runtime_snapshot"]["conversation_state"].pop(
                "current_topic"
            )
            return result

        mapping = {
            name: (
                malformed_provider
                if name == "context_aware"
                else lambda _context: {}
            )
            for name in o.SYSTEM_CONFIG_IDS
        }
        failed = runner.orchestrate_offline_unit(
            self.plan,
            unit,
            resources=self.bundle,
            executors=o.ExecutorRegistry(mapping),
            fake_raw_client=client,
            clock=Clock(),
            transport_implementation_sha256=TRANSPORT_SHA,
            runtime_identity_sha256=RUNTIME_SHA,
            snapshot_validator=validate_synthetic_snapshot,
        )
        self.assertEqual(failed.action, "fail_closed")
        self.assertEqual(
            failed.failure_category, "CHECKPOINT_SNAPSHOT_INVALID"
        )
        self.assertEqual(failed.journal.state, "provider_returned")
        self.assertEqual(failed.identity.attempt_number, 1)
        self.assertEqual(len(executor_calls), 1)
        self.assertEqual(len(client.calls), 1)
        self.assertIsNone(failed.checkpoint_evidence)
        self.assertIsNone(failed.formal_result)
        self.assertIsNone(failed.authoritative_success)

        stopped_client = FakeRawClient()
        stopped_executor = ExecutorSpy(
            client=stopped_client, mode="provider"
        )
        stopped = self.execute(
            unit,
            stopped_executor,
            stopped_client,
            journal=failed.journal,
            clock=Clock(10),
        )
        self.assertEqual(stopped.action, "fail_closed")
        self.assertEqual(stopped.identity.attempt_number, 1)
        self.assertEqual(stopped_executor.calls, [])
        self.assertEqual(stopped_client.calls, [])
        self.assertIsNone(stopped.checkpoint_evidence)
        self.assertIsNone(stopped.formal_result)
        self.assertIsNone(stopped.authoritative_success)

    def test_stage_a_encapsulation_ast_regression(self):
        paths = (
            ROOT / "scripts/run_formal_evaluation.py",
            ROOT / "scripts/formal_evaluation_orchestration.py",
        )
        for path in paths:
            with self.subTest(path=path.name):
                source = path.read_text(encoding="utf-8")
                self.assertEqual(stage_a_private_accesses(source), [])
        prohibited = {
            "tracker_getattr": (
                'getattr(tracker, "_receipt")',
                "indirect_getattr:_receipt",
            ),
            "constant_tracker_member": (
                'private_name = "_receipt"\n'
                "member_alias = private_name\n"
                "getattr(tracker, member_alias)",
                "indirect_getattr:_receipt",
            ),
            "aliased_getattr": (
                "read_member = getattr\n"
                "read_member_alias = read_member\n"
                'read_member_alias(tracker, "_receipt")',
                "indirect_getattr:_receipt",
            ),
            "qualified_builtins_getattr": (
                "import builtins\n"
                "read_member = builtins.getattr\n"
                "read_member_alias = read_member\n"
                'read_member_alias(tracker, "_receipt")',
                "indirect_getattr:_receipt",
            ),
            "imported_builtins_getattr_alias": (
                "from builtins import getattr as read_member\n"
                "read_member_alias = read_member\n"
                'read_member_alias(tracker, "_receipt")',
                "indirect_getattr:_receipt",
            ),
            "annotated_tracker_parameter": (
                "from formal_evaluation_transport import ProviderCallTracker\n"
                "def inspect(tracker_value: ProviderCallTracker):\n"
                "    return tracker_value._receipt",
                "tracker_attribute:_receipt",
            ),
            "annotated_tracker_parameter_alias": (
                "from formal_evaluation_transport import "
                "ProviderCallTracker as Tracker\n"
                "def inspect(tracker_value: Tracker):\n"
                "    tracker_alias = tracker_value\n"
                '    return getattr(tracker_alias, "_fail")',
                "indirect_getattr:_fail",
            ),
            "tracker_getattribute": (
                'tracker.__getattribute__("_receipt")',
                "indirect_getattribute:_receipt",
            ),
            "bound_getattribute_alias": (
                "read_member = tracker.__getattribute__\n"
                "read_member_alias = read_member\n"
                'read_member_alias("_receipt")',
                "indirect_getattribute:_receipt",
            ),
            "object_getattribute": (
                'object.__getattribute__(tracker, "_begin")',
                "indirect_object_getattribute:_begin",
            ),
            "object_getattribute_alias": (
                "read_member = object.__getattribute__\n"
                "read_member_alias = read_member\n"
                'private_name = "_begin"\n'
                "read_member_alias(tracker, private_name)",
                "indirect_object_getattribute:_begin",
            ),
            "stage_a_getattr": (
                "import formal_evaluation_transport as stage_a_alias\n"
                'getattr(stage_a_alias, "_private_name")',
                "indirect_getattr:_private_name",
            ),
            "chained_stage_a_getattr_aliases": (
                "import formal_evaluation_transport as imported_stage_a\n"
                "stage_a_alias = imported_stage_a\n"
                "stage_a_alias_2 = stage_a_alias\n"
                "read_member = getattr\n"
                "read_member_2 = read_member\n"
                'private_name = "_PROVIDER_CAPABILITY"\n'
                "private_name_2 = private_name\n"
                "read_member_2(stage_a_alias_2, private_name_2)",
                "indirect_getattr:_PROVIDER_CAPABILITY",
            ),
            "provider_capability": (
                "import formal_evaluation_transport as stage_a_alias\n"
                "stage_a_alias._PROVIDER_CAPABILITY",
                "stage_a_attribute:_PROVIDER_CAPABILITY",
            ),
            "stage_a_vars": (
                "import formal_evaluation_transport as stage_a\n"
                'vars(stage_a)["_PROVIDER_CAPABILITY"]',
                "private_dict_access:_PROVIDER_CAPABILITY",
            ),
            "stage_a_vars_get": (
                "import formal_evaluation_transport as stage_a\n"
                'vars(stage_a).get("_PROVIDER_CAPABILITY")',
                "private_dict_get:_PROVIDER_CAPABILITY",
            ),
            "stage_a_vars_get_alias": (
                "import formal_evaluation_transport as imported_stage_a\n"
                "stage_a = imported_stage_a\n"
                "stage_a_dict = vars(stage_a)\n"
                "read_member = stage_a_dict.get\n"
                "read_member_alias = read_member\n"
                'private_name = "_PROVIDER_CAPABILITY"\n'
                "read_member_alias(private_name)",
                "private_dict_get:_PROVIDER_CAPABILITY",
            ),
            "stage_a_vars_alias": (
                "import formal_evaluation_transport as imported_stage_a\n"
                "stage_a = imported_stage_a\n"
                "read_vars = vars\n"
                "stage_a_dict = read_vars(stage_a)\n"
                'private_name = "_PROVIDER_CAPABILITY"\n'
                "stage_a_dict[private_name]",
                "private_dict_access:_PROVIDER_CAPABILITY",
            ),
            "stage_a_dunder_dict": (
                "import formal_evaluation_inflight as stage_a\n"
                "stage_a_dict = stage_a.__dict__\n"
                'stage_a_dict["_CanonicalIdentity"]',
                "private_dict_access:_CanonicalIdentity",
            ),
            "canonical_private": (
                "import formal_evaluation_transport as stage_a_alias\n"
                "stage_a_alias._CanonicalProductionResourceIdentity",
                "stage_a_attribute:_CanonicalProductionResourceIdentity",
            ),
            "private_import": (
                "from formal_evaluation_transport import _PROVIDER_CAPABILITY",
                "private_import:_PROVIDER_CAPABILITY",
            ),
            "direct_receipt": (
                "tracker._receipt",
                "tracker_attribute:_receipt",
            ),
            "direct_begin": (
                "tracker._begin()",
                "tracker_attribute:_begin",
            ),
            "direct_fail": (
                "tracker._fail()",
                "tracker_attribute:_fail",
            ),
            "direct_succeed": (
                "tracker._succeed()",
                "tracker_attribute:_succeed",
            ),
            "tracker_dunder_dict": (
                "tracker_dict = tracker.__dict__\n"
                'private_name = "_receipt"\n'
                "tracker_dict[private_name]",
                "private_dict_access:_receipt",
            ),
            "aliased_tracker": (
                "from formal_evaluation_transport import "
                "ProviderCallTracker as Tracker\n"
                "request_tracker = Tracker()\n"
                'getattr(request_tracker, "_fail")',
                "indirect_getattr:_fail",
            ),
            "assigned_tracker_type_alias": (
                "from formal_evaluation_transport import ProviderCallTracker\n"
                "TrackerAlias = ProviderCallTracker\n"
                "TrackerAlias2 = TrackerAlias\n"
                "request_tracker = TrackerAlias2()\n"
                'getattr(request_tracker, "_receipt")',
                "indirect_getattr:_receipt",
            ),
            "module_tracker_type_alias": (
                "import formal_evaluation_transport as stage_a\n"
                "TrackerAlias = stage_a.ProviderCallTracker\n"
                "request_tracker = TrackerAlias()\n"
                'getattr(request_tracker, "_succeed")',
                "indirect_getattr:_succeed",
            ),
            "private_tracker_call_target": (
                "from formal_evaluation_transport import ProviderCallTracker\n"
                'getattr(ProviderCallTracker(), "_receipt")',
                "indirect_getattr:_receipt",
            ),
        }
        for name, (source, expected) in prohibited.items():
            with self.subTest(synthetic=name):
                self.assertIn(expected, stage_a_private_accesses(source))
        permitted = (
            "class Local:\n"
            "    def _private_helper(self):\n"
            "        return 1\n"
            "    def _receipt(self):\n"
            "        return 2\n"
            "helper = Local()\n"
            "helper._private_helper()\n"
            "helper._receipt()\n"
            "read_member = getattr\n"
            'read_member(helper, "_private_helper")()\n'
            'vars(helper)["_receipt"]\n'
            "read_attribute = helper.__getattribute__\n"
            'read_attribute("_receipt")\n'
        )
        self.assertEqual(stage_a_private_accesses(permitted), [])
        orchestration_source = paths[1].read_text(encoding="utf-8")
        orchestration_tree = ast.parse(orchestration_source)
        assigned_names = {
            target.id
            for node in ast.walk(orchestration_tree)
            if isinstance(node, (ast.Assign, ast.AnnAssign))
            for target in (
                node.targets if isinstance(node, ast.Assign) else [node.target]
            )
            if isinstance(target, ast.Name)
        }
        self.assertTrue(
            assigned_names.isdisjoint(
                {"FIXED_GENERATION", "GENERATION", "MAX_ATTEMPTS"}
            )
        )
        function_names = {
            node.name
            for node in ast.walk(orchestration_tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertNotIn("retryable", function_names)
        wrapper = next(
            node
            for node in ast.walk(ast.parse(paths[0].read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef)
            and node.name == "orchestrate_offline_unit"
        )
        wrapper_names = {
            node.id for node in ast.walk(wrapper) if isinstance(node, ast.Name)
        }
        self.assertNotIn("retryable", wrapper_names)
        self.assertNotIn("run_plan", wrapper_names)

class StageB2PersistenceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = runner.build_plan()
        cls.bundle = resources()

    def unit(self, *, config="v2", rq=None, turn=1):
        return next(
            unit
            for unit in self.plan
            if unit["system_config_id"] == config
            and unit["turn_index"] == turn
            and (rq is None or unit["rq"] == rq)
        )

    def execute(self, unit, executor, client, **extra):
        dependencies = {
            "resources": self.bundle,
            "executors": registry_for(unit["system_config_id"], executor),
            "fake_raw_client": client,
            "clock": extra.pop("clock", Clock()),
            "transport_implementation_sha256": TRANSPORT_SHA,
            "runtime_identity_sha256": RUNTIME_SHA,
            "snapshot_validator": validate_synthetic_snapshot,
        }
        dependencies.update(extra)
        return runner.orchestrate_offline_unit(self.plan, unit, **dependencies)

    def test_exact_public_and_private_signature_order(self):
        public = inspect.signature(o.orchestrate_validated_unit)
        self.assertEqual(
            list(public.parameters),
            [
                "plan",
                "unit",
                "journal_persistence_callback",
                "retry_predecessor",
                "dependencies",
            ],
        )
        self.assertIsNone(
            public.parameters["journal_persistence_callback"].default
        )
        self.assertIsNone(public.parameters["retry_predecessor"].default)
        private = inspect.signature(o._orchestrate_plan_member)
        names = list(private.parameters)
        snapshot = names.index("snapshot_validator")
        self.assertEqual(
            names[snapshot + 1 :],
            [
                "journal_persistence_callback",
                "retry_predecessor",
                "journal",
                "authoritative_success",
                "checkpoint_evidence",
                "turn_one_unit",
                "turn_two_unit",
                "claimed_ids",
            ],
        )

    def test_local_initial_publishes_prepared_once(self):
        unit = self.unit()
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="local")
        published = []
        outcome = self.execute(
            unit,
            executor,
            client,
            journal_persistence_callback=lambda journal: published.append(
                journal
            ),
        )
        self.assertEqual("local_success", outcome.action)
        self.assertEqual(["prepared"], [item.state for item in published])
        self.assertTrue(all(type(item) is f.InflightJournal for item in published))
        self.assertEqual([], client.calls)

    def test_provider_publication_order_is_prepared_started_returned(self):
        events = []
        unit = self.unit()
        client = FakeRawClient(events=events)
        executor = ExecutorSpy(client=client, mode="provider")

        def persist(journal):
            events.append("persist:" + journal.state)

        outcome = self.execute(
            unit,
            executor,
            client,
            journal_persistence_callback=persist,
        )
        self.assertEqual("success", outcome.action)
        self.assertEqual(
            [
                "persist:prepared",
                "persist:call_started",
                "fake_client",
                "persist:provider_returned",
            ],
            events,
        )

    def test_callback_requires_exact_none_return(self):
        unit = self.unit()
        for value in (False, 0, object()):
            with self.subTest(value=repr(value)):
                client = FakeRawClient()
                executor = ExecutorSpy(client=client, mode="local")
                with self.assertRaises(o.OrchestrationError) as caught:
                    self.execute(
                        unit,
                        executor,
                        client,
                        journal_persistence_callback=lambda _journal, result=value: result,
                    )
                self.assertEqual(
                    "JOURNAL_PERSISTENCE_CALLBACK_RETURN_INVALID",
                    caught.exception.category,
                )
                self.assertEqual([], executor.calls)
                self.assertEqual([], client.calls)

    def test_callback_exception_identity_propagates(self):
        unit = self.unit()
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="local")
        failure = RuntimeError("private persistence failure")

        def persist(_journal):
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            self.execute(
                unit,
                executor,
                client,
                journal_persistence_callback=persist,
            )
        self.assertIs(failure, caught.exception)
        self.assertEqual([], executor.calls)
        self.assertEqual([], client.calls)

    def test_call_started_failure_precedes_tracker_and_fake_call(self):
        unit = self.unit()
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="provider")
        failure = RuntimeError("call-start persistence failure")
        states = []

        def persist(journal):
            states.append(journal.state)
            if journal.state == "call_started":
                raise failure

        with self.assertRaises(RuntimeError) as caught:
            self.execute(
                unit,
                executor,
                client,
                journal_persistence_callback=persist,
            )
        self.assertIs(failure, caught.exception)
        self.assertEqual(["prepared", "call_started"], states)
        self.assertEqual([], client.calls)

    def test_provider_returned_failure_is_nonrecallable(self):
        unit = self.unit()
        client = FakeRawClient()
        executor = ExecutorSpy(client=client, mode="provider")
        failure = RuntimeError("provider-returned persistence failure")

        def persist(journal):
            if journal.state == "provider_returned":
                raise failure

        with self.assertRaises(RuntimeError) as caught:
            self.execute(
                unit,
                executor,
                client,
                journal_persistence_callback=persist,
            )
        self.assertIs(failure, caught.exception)
        self.assertEqual(1, len(client.calls))

    def test_same_attempt_prepared_resume_does_not_republish(self):
        unit = self.unit()
        initial_client = FakeRawClient()
        initial_executor = ExecutorSpy(client=initial_client, mode="local")
        first = self.execute(unit, initial_executor, initial_client)
        resumed_client = FakeRawClient()
        resumed_executor = ExecutorSpy(client=resumed_client, mode="local")
        published = []
        resumed = self.execute(
            unit,
            resumed_executor,
            resumed_client,
            journal=first.journal,
            journal_persistence_callback=lambda journal: published.append(
                journal
            ),
        )
        self.assertEqual("local_success", resumed.action)
        self.assertEqual([], published)

    def test_resumed_retry_requires_exact_predecessor_and_does_not_republish(self):
        unit = self.unit()
        first_client = FakeRawClient(error=ProviderFailure(status_code=429))
        first_executor = ExecutorSpy(client=first_client, mode="provider")
        first = self.execute(unit, first_executor, first_client)
        self.assertEqual("retry_available", first.action)
        prepared = f.next_retry_journal(first.journal, "2026-07-23T10:00:09Z")
        resumed_client = FakeRawClient()
        resumed_executor = ExecutorSpy(client=resumed_client, mode="local")
        published = []
        resumed = self.execute(
            unit,
            resumed_executor,
            resumed_client,
            journal=prepared,
            retry_predecessor=first.journal,
            clock=Clock(start=10),
            journal_persistence_callback=lambda journal: published.append(
                journal
            ),
        )
        self.assertEqual("local_success", resumed.action)
        self.assertEqual([], published)
        self.assertEqual(first.journal, resumed.predecessor_journal)
        with self.assertRaises(o.OrchestrationError) as missing:
            self.execute(
                unit,
                resumed_executor,
                resumed_client,
                journal=prepared,
                clock=Clock(start=10),
            )
        self.assertEqual("RECOVERY_PREDECESSOR_REQUIRED", missing.exception.category)
        # The prepared timestamp itself is not authority: the frozen contract
        # reconstructs from ``journal.prepared_at``.  Use an attempt-2
        # prepared journal as purported predecessor instead, which cannot be
        # the exact immediately preceding retryable terminal journal.
        wrong = f.next_retry_journal(first.journal, "2026-07-23T10:00:08Z")
        with self.assertRaises(o.OrchestrationError) as invalid:
            self.execute(
                unit,
                resumed_executor,
                FakeRawClient(),
                journal=prepared,
                retry_predecessor=wrong,
                clock=Clock(start=10),
            )
        self.assertEqual("RECOVERY_PREDECESSOR_INVALID", invalid.exception.category)


if __name__ == "__main__":
    unittest.main()
