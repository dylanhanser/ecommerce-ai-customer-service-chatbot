from __future__ import annotations

import copy
import dataclasses
import hashlib
import inspect
import json
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

import formal_evaluation_review_projection as projection
import formal_evaluation_store as store
import run_formal_evaluation as runner
from formal_evaluation_store import CanonicalPrivateResultV1, StoreError


def _under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


@pytest.fixture(autouse=True)
def isolated_roots_and_offline_guard(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="b3t-") as directory:
        temporary_parent = Path(directory)
        b2_root = temporary_parent / "b2"
        b3_root = temporary_parent / "b3"
        b2_root.mkdir()
        b3_root.mkdir()
        assert b2_root != b3_root
        assert b2_root.parent == temporary_parent == b3_root.parent
        assert not _under(b2_root, b3_root) and not _under(b3_root, b2_root)
        monkeypatch.setattr(store, "_PRIVATE_STATE_ROOT", b2_root)
        monkeypatch.setattr(projection, "_REVIEWER_PROJECTION_ROOT", b3_root)

        production_roots = (
            store._PRODUCTION_PRIVATE_STATE_ROOT,
            projection._PRODUCTION_REVIEWER_PROJECTION_ROOT,
        )

        def guarded(method):
            def wrapper(self, *args, **kwargs):
                candidate = Path(self)
                if any(_under(candidate, root) for root in production_roots):
                    raise AssertionError("actual production root access")
                return method(self, *args, **kwargs)

            return wrapper

        for name in (
            "exists",
            "lstat",
            "is_file",
            "is_dir",
            "iterdir",
            "read_bytes",
            "write_bytes",
            "open",
            "mkdir",
            "unlink",
            "resolve",
        ):
            monkeypatch.setattr(Path, name, guarded(getattr(Path, name)))

        def forbidden_network(*_args, **_kwargs):
            raise AssertionError("network access is forbidden")

        monkeypatch.setattr(socket, "socket", forbidden_network)
        monkeypatch.setattr(socket, "create_connection", forbidden_network)
        monkeypatch.setattr(socket, "getaddrinfo", forbidden_network)
        with pytest.raises(StoreError, match="^STORE_TEST_FAULT_INVALID$"):
            store._stage_b2_test_fault_observation_for_tests(
                "before_atomic_temp_create_error"
            )
        yield {"b2": b2_root, "b3": b3_root, "tmp": temporary_parent}
        with pytest.raises(StoreError, match="^STORE_TEST_FAULT_INVALID$"):
            store._stage_b2_test_fault_observation_for_tests(
                "before_atomic_temp_create_error"
            )


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _synthetic_plan() -> list[dict]:
    units: list[dict] = []

    def add(rq: str, case_id: str, turn: int, system: str, user_input: str):
        request_id = _sha(f"request|{rq}|{case_id}|{turn}|{system}")
        payload = {
            "user_input": user_input,
            "rq": rq,
            "system_config": system,
        }
        unit = {
            "request_id": request_id,
            "rq": rq,
            "case_id": case_id,
            "turn_index": turn,
            "system_config_id": system,
            "payload": payload,
            "input_sha256": _sha(user_input),
            "payload_sha256": _sha(
                json.dumps(payload, sort_keys=True, separators=(",", ":"))
            ),
            "frozen_test_file_sha256": _sha(f"fixture|{rq}"),
        }
        if rq == "RQ1":
            unit["review_id"] = case_id
        units.append(unit)

    for number in range(51):
        case_id = f"rq1_case_{number:02d}"
        for system in ("qa_only_reconstructed_baseline", "v2"):
            add("RQ1", case_id, 1, system, f"Synthetic RQ1 question {number}")
    for number in range(20):
        case_id = f"rq2_case_{number:02d}"
        for system in ("qa_only_reconstructed_baseline", "v2"):
            add("RQ2", case_id, 1, system, f"Synthetic RQ2 input {number}")
    for number in range(12):
        case_id = f"rq3_dialogue_{number:02d}"
        for system in ("single_turn", "context_aware"):
            for turn in (1, 2):
                add(
                    "RQ3",
                    case_id,
                    turn,
                    system,
                    f"Synthetic RQ3 dialogue {number} turn {turn}",
                )
    for order, unit in enumerate(units, 1):
        unit["execution_order"] = order
    assert len(units) == 190
    return units


def _resource_identity(system: str, synthetic: bool) -> dict:
    return {
        "schema_version": 1,
        "system_config_id": system,
        "formal_system_id": f"formal_{system}",
        "resource_type": "test_owned_structural_fixture",
        "logical_resource_id": f"test_{system}",
        "corpus_version": "test-v1",
        "cache_family": "test-only",
        "corpus_path": "test-only/corpus",
        "embeddings_path": "test-only/embeddings",
        "corpus_sha256": _sha(f"corpus|{system}"),
        "embeddings_sha256": _sha(f"embeddings|{system}"),
        "embedding_model": "test-only",
        "embedding_dimensions": 1,
        "embedding_rows": 1,
        "row_count": 1,
        "qa_count": 1,
        "snippet_count": 0,
        "synthetic": synthetic,
    }


def _contract(*, mode: str = "test_owned_eligible", synthetic: bool = False) -> dict:
    systems = {
        system: {
            "formal_system_id": f"formal_{system}",
            "resolved_runtime_system_id": f"runtime_{system}",
            "resource_family": "test-only",
            "top_k": 1,
            "uses_context": system == "context_aware",
            "uses_checkpoint": system == "context_aware",
        }
        for system in projection._SYSTEM_COUNTS
    }
    resources = {}
    for system in projection._SYSTEM_COUNTS:
        identity = _resource_identity(system, synthetic)
        resources[system] = {
            "resource_identity": identity,
            "resource_identity_sha256": hashlib.sha256(
                projection._canonical_json_bytes(identity)
            ).hexdigest(),
        }
    without_hash = {
        "schema_version": 1,
        "stage_id": "B2",
        "plan_authority": {
            "plan_fingerprint": projection._PLAN_FINGERPRINT,
            "base_seed": 20260721,
            "execution_unit_count": 190,
            "unique_request_id_count": 190,
            "execution_order_first": 1,
            "execution_order_last": 190,
            "rq_counts": dict(projection._RQ_COUNTS),
            "system_counts": {
                "context_aware": 24,
                "qa_only_reconstructed_baseline": 71,
                "single_turn": 24,
                "v2": 71,
            },
        },
        "frozen_input_sha256": {"test-only": _sha("frozen-test-only")},
        "formal_system_authority": systems,
        "provider_generation_authority": {
            "generation": {
                "contract_id": "test_owned_generation_v1",
                "contract_sha256": _sha("test-generation-contract"),
                "runner_generation_sha256": _sha("test-runner-generation"),
                "snapshot": {
                    "model": "test-owned-model",
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "max_tokens": 32,
                    "stream": False,
                },
            },
            "transport": {
                "contract_id": "test_owned_transport_v1",
                "contract_sha256": _sha("test-transport-contract"),
                "snapshot": {
                    "schema_version": 1,
                    "contract_id": "test_owned_transport_v1",
                    "provider": "test-owned-provider",
                    "base_url": "test-owned-no-network",
                    "provider_api": "test_owned_fake_api",
                    "maximum_attempts": 1,
                    "success_receipt_schema": 1,
                },
            },
            "offline_execution": {
                "authority_bundle_id": "test-only",
                "clock_id": "test-only",
                "executor_registry_id": "test-only",
                "fake_raw_client_id": "test-only",
                "mode": mode,
                "snapshot_validator_id": "test-only",
                "test_fault_controller_id": "test-only",
            },
        },
        "runtime_resource_authority": {
            "transport_implementation_sha256": _sha("test-transport"),
            "runtime_identity_sha256": _sha("test-runtime"),
            "resources": resources,
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
    contract = copy.deepcopy(without_hash)
    contract["run_contract_sha256"] = projection.domain_hash(
        "formal-evaluation-run-contract-v1", "contract", without_hash
    )
    return contract


def _rehash_contract(contract: dict) -> None:
    without_hash = dict(contract)
    without_hash.pop("run_contract_sha256", None)
    contract["run_contract_sha256"] = projection.domain_hash(
        "formal-evaluation-run-contract-v1", "contract", without_hash
    )


def _synthetic_results(plan: list[dict], contract: dict) -> tuple[CanonicalPrivateResultV1, ...]:
    envelopes = {
        unit["request_id"]: _sha(f"envelope|{unit['request_id']}") for unit in plan
    }
    turn_one_envelopes = {
        (unit["case_id"], unit["system_config_id"]): envelopes[unit["request_id"]]
        for unit in plan
        if unit["rq"] == "RQ3" and unit["turn_index"] == 1
    }
    results = []
    for unit in plan:
        rq = unit["rq"]
        system = unit["system_config_id"]
        turn = unit["turn_index"]
        if rq != "RQ3":
            kind = "none"
            turn_one_sha = None
            checkpoint_sha = None
        elif system == "single_turn":
            kind = "single_turn"
            turn_one_sha = None
            checkpoint_sha = None
        elif turn == 1:
            kind = "context_turn_one"
            turn_one_sha = None
            checkpoint_sha = _sha(f"checkpoint|{unit['case_id']}")
        else:
            kind = "context_turn_two"
            turn_one_sha = turn_one_envelopes[(unit["case_id"], system)]
            checkpoint_sha = _sha(f"checkpoint|{unit['case_id']}")
        answer = f"Synthetic model answer 中 {unit['execution_order']}"
        execution_unit_id = runner.derive_execution_unit_id(
            plan_fingerprint=projection._PLAN_FINGERPRINT,
            request_id=unit["request_id"],
            execution_order=unit["execution_order"],
        ) if hasattr(runner, "derive_execution_unit_id") else projection.derive_execution_unit_id(
            plan_fingerprint=projection._PLAN_FINGERPRINT,
            request_id=unit["request_id"],
            execution_order=unit["execution_order"],
        )
        results.append(
            CanonicalPrivateResultV1(
                schema_version=1,
                plan_fingerprint=projection._PLAN_FINGERPRINT,
                run_contract_sha256=contract["run_contract_sha256"],
                plan_member_sha256=projection._plan_member_sha256(unit),
                execution_unit_id=execution_unit_id,
                execution_order=unit["execution_order"],
                request_id=unit["request_id"],
                rq=rq,
                case_id=unit["case_id"],
                dialogue_id=unit["case_id"] if rq == "RQ3" else None,
                turn_index=turn,
                system_config_id=system,
                formal_system_id=contract["formal_system_authority"][system][
                    "formal_system_id"
                ],
                envelope_sha256=envelopes[unit["request_id"]],
                response_text=answer,
                response_sha256=_sha(answer),
                rq3_relationship_kind=kind,
                turn_one_commit_sha256=turn_one_sha,
                checkpoint_record_sha256=checkpoint_sha,
            )
        )
    return tuple(results)


def _reference_values(plan: list[dict]) -> tuple[list[dict], dict, dict]:
    rq1_questions = {
        unit["case_id"]: unit["payload"]["user_input"]
        for unit in plan
        if unit["rq"] == "RQ1"
    }
    gold = [
        {
            "review_id": case_id,
            "external_candidate_id": "test-only",
            "external_session_id": "test-only",
            "question": question,
            "reference_answer": f"Synthetic reference {number}",
            "gold_category": f"category_{number % 5}",
            "sample_group": "test-only",
            "risk_reason": "test-only",
        }
        for number, (case_id, question) in enumerate(rq1_questions.items())
    ]
    rq2_inputs = {
        unit["case_id"]: unit["payload"]["user_input"]
        for unit in plan
        if unit["rq"] == "RQ2"
    }
    rq2 = {
        "schema_version": "1.0",
        "pass_rule": "test-only",
        "cases": [
            {
                "case_id": case_id,
                "category": "test-only",
                "user_input": user_input,
                "expected_action_type": "test-action",
                "retrieval_expected": number % 2 == 0,
                "required_elements": ["required"],
                "forbidden_elements": ["forbidden"],
            }
            for number, (case_id, user_input) in enumerate(rq2_inputs.items())
        ],
    }
    rq3_dialogues: dict[str, list[str]] = {}
    for unit in plan:
        if unit["rq"] == "RQ3" and unit["system_config_id"] == "single_turn":
            rq3_dialogues.setdefault(unit["case_id"], ["", ""])[
                unit["turn_index"] - 1
            ] = unit["payload"]["user_input"]
    rq3 = {
        "schema_version": "1.0",
        "pass_rule": "test-only",
        "error_types": ["test-only"],
        "cases": [
            {
                "dialogue_id": case_id,
                "scenario_type": "test-only",
                "turns": [
                    {
                        "user_input": texts[0],
                        "expected_action_type": "turn-one-action",
                        "critical_turn": False,
                    },
                    {
                        "user_input": texts[1],
                        "expected_action_type": "turn-two-action",
                        "critical_turn": True,
                    },
                ],
                "retrieval_expected": True,
                "expected_state_before": "test-before",
                "expected_state_after": "test-after",
                "reset_expected": False,
                "required_elements": ["required"],
                "forbidden_elements": ["forbidden"],
            }
            for case_id, texts in rq3_dialogues.items()
        ],
    }
    return gold, rq2, rq3


def _synthetic_inputs():
    plan = _synthetic_plan()
    contract = _contract()
    results = _synthetic_results(plan, contract)
    raw_references = _reference_values(plan)
    references = projection._build_reference_bundle(plan, *raw_references)
    return plan, contract, results, references, raw_references


@pytest.fixture
def synthetic_material():
    plan, contract, results, references, raw = _synthetic_inputs()
    material = projection._build_projection_material(
        plan, contract, results, references
    )
    return plan, contract, results, references, raw, material


def _final(root: Path, filename: str) -> Path:
    return (
        root / "private" / filename
        if filename == projection._PRIVATE_FILE
        else root / "reviewer" / filename
    )


def _tree_bytes(root: Path) -> dict[str, bytes]:
    values = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            values[str(path.relative_to(root))] = path.read_bytes()
    return values


def _rewrite_json(path: Path, value: dict) -> None:
    path.write_bytes(projection._canonical_file_bytes(value))


def _populate_complete_current_stage_b2_store(plan: list[dict]) -> None:
    """Use the fixed B1 path and B2 publishers without repeated progress scans."""

    contract = dict(runner.build_durable_run_contract(plan))
    authority = runner._fixed_offline_authority()
    with store._open_store(contract) as (opened, lock):
        for unit in plan:
            unit_id = store._execution_unit_id(unit)
            state = store._load_unit_state_locked(
                unit_id, run_contract=opened, lock=lock
            )
            checkpoint, turn_one_commit_sha = store._selected_dependency_commit(
                plan, unit, run_contract=opened, lock=lock
            )
            dependencies = authority.dependencies_for(unit, state)

            def persist(journal):
                store._publish_journal_locked(
                    journal, run_contract=opened, lock=lock
                )
                return None

            orchestration = runner.orchestrate_offline_unit(
                plan,
                unit,
                journal_persistence_callback=persist,
                checkpoint_evidence=checkpoint,
                **dependencies,
            )
            assert orchestration.action in {"success", "local_success"}
            state = store._load_unit_state_locked(
                unit_id, run_contract=opened, lock=lock
            )
            candidate = store._construct_private_commit(
                plan,
                unit,
                orchestration,
                run_contract=opened,
                state=state,
                turn_one_commit_sha256=turn_one_commit_sha,
            )
            commit, _published = store._publish_private_commit_locked(
                candidate, unit=unit, lock=lock
            )
            store._reconcile_commit_locked(
                commit, state, run_contract=opened, lock=lock
            )


def test_canonical_private_result_exact_fields_immutable_and_validated(synthetic_material):
    result = synthetic_material[2][0]
    assert [field.name for field in dataclasses.fields(result)] == [
        "schema_version", "plan_fingerprint", "run_contract_sha256",
        "plan_member_sha256", "execution_unit_id", "execution_order",
        "request_id", "rq", "case_id", "dialogue_id", "turn_index",
        "system_config_id", "formal_system_id", "envelope_sha256",
        "response_text", "response_sha256", "rq3_relationship_kind",
        "turn_one_commit_sha256", "checkpoint_record_sha256",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.response_text = "changed"
    with pytest.raises(ValueError, match="invalid CanonicalPrivateResultV1"):
        dataclasses.replace(result, schema_version=True)
    with pytest.raises(ValueError, match="invalid CanonicalPrivateResultV1"):
        dataclasses.replace(result, response_sha256="0" * 64)


def test_projection_error_and_outcome_are_closed_and_sanitized(synthetic_material):
    with pytest.raises(ValueError, match="invalid ProjectionError category"):
        projection.ProjectionError("UNKNOWN")
    error = projection.ProjectionError("B3_SOURCE_INELIGIBLE")
    assert error.args == ("B3_SOURCE_INELIGIBLE",)
    assert vars(error) == {"category": "B3_SOURCE_INELIGIBLE"}
    material = synthetic_material[-1]
    outcome = projection.ReviewerProjectionOutcome(
        1,
        "created",
        material.reviewer_bundle_id,
        190,
        5,
        material.reviewer_manifest_sha256,
        material.projection_manifest_sha256,
    )
    assert [field.name for field in dataclasses.fields(outcome)] == [
        "schema_version", "action", "reviewer_bundle_id", "source_unit_count",
        "reviewer_artifact_count", "reviewer_manifest_sha256",
        "projection_manifest_sha256",
    ]


@pytest.mark.parametrize(
    "mode,synthetic,eligible",
    [
        ("offline_fake_only", False, False),
        ("test_owned_eligible", True, False),
        ("offline_fake_only", True, False),
        ("test_owned_eligible", False, True),
    ],
)
def test_source_gate_exact_predicates_and_single_category(mode, synthetic, eligible):
    contract = projection._validate_authoritative_contract(
        _contract(mode=mode, synthetic=synthetic)
    )
    if eligible:
        projection._apply_source_eligibility_gate(contract)
    else:
        with pytest.raises(projection.ProjectionError, match="^B3_SOURCE_INELIGIBLE$"):
            projection._apply_source_eligibility_gate(contract)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_offline",
        "wrong_mode_type",
        "extra_resource",
        "wrong_synthetic_type",
        "resource_hash",
        "excess_depth",
        "hash",
    ],
)
def test_source_gate_malformed_authority_fails_closed(mutation):
    contract = _contract()
    if mutation == "missing_offline":
        del contract["provider_generation_authority"]["offline_execution"]
    elif mutation == "wrong_mode_type":
        contract["provider_generation_authority"]["offline_execution"]["mode"] = 1
    elif mutation == "extra_resource":
        contract["runtime_resource_authority"]["resources"]["extra"] = {}
    elif mutation == "wrong_synthetic_type":
        first = next(iter(projection._SYSTEM_COUNTS))
        contract["runtime_resource_authority"]["resources"][first][
            "resource_identity"
        ]["synthetic"] = 0
    elif mutation == "resource_hash":
        first = next(iter(projection._SYSTEM_COUNTS))
        contract["runtime_resource_authority"]["resources"][first][
            "resource_identity_sha256"
        ] = "0" * 64
    elif mutation == "excess_depth":
        nested = None
        for _ in range(projection._JSON_MAX_DEPTH + 1):
            nested = [nested]
        contract["provider_generation_authority"]["generation"] = nested
    else:
        contract["run_contract_sha256"] = "0" * 64
    if mutation != "hash":
        _rehash_contract(contract)
    with pytest.raises(projection.ProjectionError, match="^B3_PRIVATE_STATE_INVALID$"):
        projection._validate_authoritative_contract(contract)


def test_complete_current_stage_b2_store_observation_is_read_only_and_b3_ineligible(
    isolated_roots_and_offline_guard,
    monkeypatch,
):
    plan = runner.build_plan()
    _populate_complete_current_stage_b2_store(plan)
    before = _tree_bytes(isolated_roots_and_offline_guard["b2"])
    observed = runner.observe_validated_canonical_private_results(plan)
    after_observation = _tree_bytes(isolated_roots_and_offline_guard["b2"])
    assert len(observed) == 190
    assert [item.execution_order for item in observed] == list(range(1, 191))
    assert before == after_observation

    commits = isolated_roots_and_offline_guard["b2"] / "commits"
    canonical_commit = sorted(commits.iterdir(), key=lambda path: path.name)[0]
    canonical_bytes = canonical_commit.read_bytes()
    canonical_commit.write_bytes(b"\xff")
    malformed_before = _tree_bytes(isolated_roots_and_offline_guard["b2"])
    with pytest.raises(StoreError):
        runner.observe_validated_canonical_private_results(plan)
    assert _tree_bytes(isolated_roots_and_offline_guard["b2"]) == malformed_before
    canonical_commit.write_bytes(canonical_bytes)

    foreign = commits / "foreign.json"
    foreign.write_bytes(canonical_bytes)
    foreign_before = _tree_bytes(isolated_roots_and_offline_guard["b2"])
    with pytest.raises(StoreError, match="^STORE_PATH_INVALID$"):
        runner.observe_validated_canonical_private_results(plan)
    assert _tree_bytes(isolated_roots_and_offline_guard["b2"]) == foreign_before
    foreign.unlink()

    first = plan[0]
    execution_unit_id = projection.derive_execution_unit_id(
        plan_fingerprint=projection._PLAN_FINGERPRINT,
        request_id=first["request_id"],
        execution_order=first["execution_order"],
    )
    mutable = isolated_roots_and_offline_guard["b2"] / "journals" / f"{execution_unit_id}.json"
    mutable.unlink()
    expected_commit = next(
        (isolated_roots_and_offline_guard["b2"] / "commits").iterdir()
    )
    abandoned = expected_commit.with_name(
        f".{expected_commit.name}.{'a' * 32}.tmp"
    )
    abandoned.write_bytes(b"test-owned-abandoned-temp")
    before_lag = _tree_bytes(isolated_roots_and_offline_guard["b2"])
    observed_lag = runner.observe_validated_canonical_private_results(plan)
    assert len(observed_lag) == 190
    assert _tree_bytes(isolated_roots_and_offline_guard["b2"]) == before_lag
    assert not mutable.exists()
    assert abandoned.exists()

    b3_before = _tree_bytes(isolated_roots_and_offline_guard["b3"])
    monkeypatch.setattr(
        projection,
        "observe_validated_canonical_private_results",
        lambda _plan: (_ for _ in ()).throw(AssertionError("observation invoked")),
    )
    monkeypatch.setattr(
        projection,
        "_load_reference_sources",
        lambda _plan: (_ for _ in ()).throw(AssertionError("references loaded")),
    )
    monkeypatch.setattr(
        projection,
        "_publish_material",
        lambda _material: (_ for _ in ()).throw(AssertionError("publication invoked")),
    )
    with pytest.raises(projection.ProjectionError, match="^B3_SOURCE_INELIGIBLE$"):
        projection.project_blinded_reviewer_outputs()
    assert _tree_bytes(isolated_roots_and_offline_guard["b2"]) == before_lag
    assert _tree_bytes(isolated_roots_and_offline_guard["b3"]) == b3_before == {}


def test_observation_rejects_active_stage_b2_fault_controller_before_access(
    isolated_roots_and_offline_guard,
):
    plan = runner.build_plan()
    root = isolated_roots_and_offline_guard["b2"]
    before = _tree_bytes(root)
    with store._install_stage_b2_test_fault_controller_for_tests(
        root, "before_atomic_temp_create_error"
    ):
        with pytest.raises(StoreError, match="^STORE_TEST_FAULT_INVALID$"):
            runner.observe_validated_canonical_private_results(plan)
    assert _tree_bytes(root) == before


def test_observation_requires_existing_store_without_creating_or_cleaning(
    isolated_roots_and_offline_guard,
):
    plan = runner.build_plan()
    root = isolated_roots_and_offline_guard["b2"]
    before = _tree_bytes(root)
    with pytest.raises(StoreError, match="^STORE_LOCK_FILE_INVALID$"):
        runner.observe_validated_canonical_private_results(plan)
    assert _tree_bytes(root) == before == {}


def test_ineligible_source_precedes_observation_references_and_b3_root_access(
    synthetic_material, monkeypatch, isolated_roots_and_offline_guard
):
    plan, _eligible, results, references, _raw, _material = synthetic_material
    contract = _contract(mode="offline_fake_only", synthetic=True)
    calls = {"observe": 0, "references": 0, "publish": 0}
    monkeypatch.setattr(projection, "verify_frozen", lambda: {})
    monkeypatch.setattr(projection, "build_plan", lambda: plan)
    monkeypatch.setattr(projection, "validate_plan", lambda value: None)
    monkeypatch.setattr(projection, "plan_fingerprint", lambda value: projection._PLAN_FINGERPRINT)
    monkeypatch.setattr(projection, "build_durable_run_contract", lambda value: contract)

    def observe(_plan):
        calls["observe"] += 1
        return results

    def load(_plan):
        calls["references"] += 1
        return references

    def publish(_material):
        calls["publish"] += 1
        raise AssertionError

    monkeypatch.setattr(projection, "observe_validated_canonical_private_results", observe)
    monkeypatch.setattr(projection, "_load_reference_sources", load)
    monkeypatch.setattr(projection, "_publish_material", publish)
    with pytest.raises(projection.ProjectionError, match="^B3_SOURCE_INELIGIBLE$"):
        projection.project_blinded_reviewer_outputs()
    assert calls == {"observe": 0, "references": 0, "publish": 0}
    assert _tree_bytes(isolated_roots_and_offline_guard["b3"]) == {}


def test_test_owned_eligible_fixture_exercises_production_entrypoint(
    synthetic_material, monkeypatch, isolated_roots_and_offline_guard
):
    plan, contract, results, references, _raw, material = synthetic_material
    observations = 0

    def observe(value):
        nonlocal observations
        assert value == plan
        observations += 1
        return results

    monkeypatch.setattr(projection, "verify_frozen", lambda: {})
    monkeypatch.setattr(projection, "build_plan", lambda: plan)
    monkeypatch.setattr(projection, "validate_plan", lambda value: None)
    monkeypatch.setattr(projection, "plan_fingerprint", lambda value: projection._PLAN_FINGERPRINT)
    monkeypatch.setattr(projection, "build_durable_run_contract", lambda value: contract)
    monkeypatch.setattr(
        projection,
        "observe_validated_canonical_private_results",
        observe,
    )
    monkeypatch.setattr(projection, "_load_reference_sources", lambda value: references)
    outcome = projection.project_blinded_reviewer_outputs()
    assert outcome.action == "created"
    assert outcome.reviewer_bundle_id == material.reviewer_bundle_id
    reopened = projection.project_blinded_reviewer_outputs()
    assert reopened.action == "already_complete"
    mapping = _final(
        isolated_roots_and_offline_guard["b3"], projection._PRIVATE_FILE
    )
    mapping.unlink()
    reconstructed = projection.project_blinded_reviewer_outputs()
    assert reconstructed.action == "resumed"
    assert observations == 3


@pytest.mark.parametrize(
    "mutation,category",
    [
        ("zero", "B3_INPUT_INCOMPLETE"),
        ("partial", "B3_INPUT_INCOMPLETE"),
        ("duplicate", "B3_PRIVATE_STATE_INVALID"),
        ("off_chain", "B3_PRIVATE_STATE_INVALID"),
        ("contract", "B3_PRIVATE_STATE_INVALID"),
        ("order", "B3_PRIVATE_STATE_INVALID"),
        ("malformed", "B3_PRIVATE_STATE_INVALID"),
        ("contradictory", "B3_PRIVATE_STATE_INVALID"),
        ("foreign", "B3_PRIVATE_STATE_INVALID"),
    ],
)
def test_snapshot_complete_set_and_canonical_binding_negatives(synthetic_material, mutation, category):
    plan, contract, results = synthetic_material[:3]
    candidate = results
    if mutation == "zero":
        candidate = tuple()
    elif mutation == "partial":
        candidate = results[:-1]
    elif mutation == "duplicate":
        candidate = results[:-1] + (results[0],)
    elif mutation == "off_chain":
        candidate = (dataclasses.replace(results[0], plan_member_sha256="0" * 64),) + results[1:]
    elif mutation == "contract":
        candidate = (dataclasses.replace(results[0], run_contract_sha256="0" * 64),) + results[1:]
    elif mutation == "order":
        candidate = (results[1], results[0]) + results[2:]
    elif mutation == "malformed":
        candidate = (object(),) + results[1:]
    elif mutation == "contradictory":
        candidate = (dataclasses.replace(results[0], case_id="contradiction"),) + results[1:]
    else:
        candidate = results + (results[-1],)
    with pytest.raises(projection.ProjectionError, match=f"^{category}$"):
        projection._validate_snapshot(plan, contract, candidate)


def test_snapshot_preserves_frozen_identity_and_rq3_relationships(synthetic_material):
    plan, contract, results = synthetic_material[:3]
    validated = projection._validate_snapshot(plan, contract, results)
    assert len(validated) == 190
    assert {rq: sum(item.rq == rq for item in validated) for rq in projection._RQ_COUNTS} == projection._RQ_COUNTS
    assert {
        system: sum(item.system_config_id == system for item in validated)
        for system in projection._SYSTEM_COUNTS
    } == projection._SYSTEM_COUNTS
    context = [
        item for item in validated if item.rq == "RQ3" and item.system_config_id == "context_aware"
    ]
    assert len(context) == 24
    for first, second in zip(context[::2], context[1::2]):
        assert first.turn_index == 1 and second.turn_index == 2
        assert second.turn_one_commit_sha256 == first.envelope_sha256
        assert second.checkpoint_record_sha256 == first.checkpoint_record_sha256


@pytest.mark.parametrize("mutation", ["gold_duplicate", "gold_text", "rq2_extra", "rq3_turn"])
def test_reference_join_and_closed_schema_fail_closed(synthetic_material, mutation):
    plan = synthetic_material[0]
    gold, rq2, rq3 = copy.deepcopy(synthetic_material[4])
    if mutation == "gold_duplicate":
        gold[1]["review_id"] = gold[0]["review_id"]
    elif mutation == "gold_text":
        gold[0]["question"] += " changed"
    elif mutation == "rq2_extra":
        rq2["cases"][0]["extra"] = "no"
    else:
        rq3["cases"][0]["turns"] = rq3["cases"][0]["turns"][:1]
    with pytest.raises(projection.ProjectionError, match="^B3_REFERENCE_INVALID$"):
        projection._build_reference_bundle(plan, gold, rq2, rq3)


def test_secondary_selection_rejects_more_than_eleven_required_categories(
    synthetic_material,
):
    references = synthetic_material[3]
    gold = copy.deepcopy(references.gold)
    for number, row in enumerate(gold.values()):
        if number == 12:
            break
        row["gold_category"] = f"required_category_{number:02d}"
    changed = dataclasses.replace(references, gold=gold)
    with pytest.raises(projection.ProjectionError, match="^B3_REFERENCE_INVALID$"):
        projection._secondary_selection(changed)


def test_reviewer_schemas_counts_secondary_subset_and_exact_answers(synthetic_material):
    results = synthetic_material[2]
    material = synthetic_material[-1]
    objects = material.objects
    assert objects["rq1_primary_v1.json"]["record_count"] == 102
    assert objects["rq1_secondary_v1.json"]["record_count"] == 22
    assert objects["rq2_v1.json"]["record_count"] == 40
    assert objects["rq3_v1.json"]["record_count"] == 24
    assert objects["rq3_v1.json"]["source_unit_count"] == 48
    primary = {row["response_id"] for row in objects["rq1_primary_v1.json"]["records"]}
    secondary = {row["response_id"] for row in objects["rq1_secondary_v1.json"]["records"]}
    assert secondary < primary and len(secondary) == 22
    all_answers = [
        row["display_payload"]["model_answer"]
        for row in objects["rq1_primary_v1.json"]["records"]
    ] + [
        row["display_payload"]["model_answer"]
        for row in objects["rq2_v1.json"]["records"]
    ] + [
        turn["display_payload"]["model_answer"]
        for row in objects["rq3_v1.json"]["records"]
        for turn in row["turns"]
    ]
    assert sorted(all_answers) == sorted(item.response_text for item in results)


def test_rq3_grouping_turn_order_and_mapping_nullability(synthetic_material):
    material = synthetic_material[-1]
    rq3 = material.objects["rq3_v1.json"]
    assert len({row["anonymous_conversation_id"] for row in rq3["records"]}) == 24
    assert all([turn["turn_index"] for turn in row["turns"]] == [1, 2] for row in rq3["records"])
    entries = material.objects[projection._PRIVATE_FILE]["entries"]
    for entry in entries:
        if entry["rq"] == "RQ3":
            assert entry["anonymous_conversation_id"] is not None
            assert entry["dialogue_id"] == entry["case_id"]
        else:
            assert entry["anonymous_conversation_id"] is None
            assert entry["dialogue_id"] is None


def test_deterministic_ids_independent_ordering_and_repeat_bytes(synthetic_material):
    plan, contract, results, references = synthetic_material[:4]
    first = synthetic_material[-1]
    second = projection._build_projection_material(plan, contract, results, references)
    assert first.file_bytes == second.file_bytes
    assert first.reviewer_bundle_id == second.reviewer_bundle_id
    private = first.objects[projection._PRIVATE_FILE]
    assert [entry["execution_order"] for entry in private["entries"]] == list(range(1, 191))
    primary_ids = [row["response_id"] for row in first.objects["rq1_primary_v1.json"]["records"]]
    execution_primary_ids = [
        entry["response_id"] for entry in private["entries"] if entry["rq"] == "RQ1"
    ]
    assert primary_ids != execution_primary_ids


def test_private_mapping_membership_source_commitment_and_key_commitment(
    synthetic_material,
):
    results = synthetic_material[2]
    private = synthetic_material[-1].objects[projection._PRIVATE_FILE]
    commits = [
        {
            "execution_order": item.execution_order,
            "execution_unit_id": item.execution_unit_id,
            "request_id": item.request_id,
            "envelope_sha256": item.envelope_sha256,
        }
        for item in results
    ]
    commit_sha = projection.domain_hash(
        "formal-evaluation-b3-canonical-commit-set-v1", "commits", commits
    )
    key = hashlib.sha256(
        b"formal-evaluation-b3-blinding-key-v1\0"
        + bytes.fromhex(projection._PLAN_FINGERPRINT)
        + bytes.fromhex(commit_sha)
    ).digest()
    commitment = hashlib.sha256(
        b"formal-evaluation-b3-blinding-key-commitment-v1\0" + key
    ).hexdigest()
    assert private["canonical_commit_set_sha256"] == commit_sha
    assert private["blinding_key_commitment_sha256"] == commitment
    assert len(private["entries"]) == 190
    assert len({entry["response_id"] for entry in private["entries"]}) == 190
    for entry in private["entries"]:
        expected = {
            "RQ1": "rq1_primary_v1.json",
            "RQ2": "rq2_v1.json",
            "RQ3": "rq3_v1.json",
        }[entry["rq"]]
        assert expected in entry["reviewer_artifacts"]


def test_synthetic_private_sentinels_do_not_leak_to_reviewer_artifacts(
    synthetic_material,
):
    plan, contract, results, references = synthetic_material[:4]
    changed_contract = copy.deepcopy(contract)
    sentinels = {
        "provider": "__B3_PRIVATE_PROVIDER_SENTINEL__",
        "prompt": "__B3_PRIVATE_PROMPT_SENTINEL__",
        "snippet": "__B3_PRIVATE_SNIPPET_SENTINEL__",
        "timestamp": "__B3_PRIVATE_TIMESTAMP_SENTINEL__",
        "exception": "__B3_PRIVATE_EXCEPTION_SENTINEL__",
        "path": "C:\\__B3_PRIVATE_PATH_SENTINEL__",
        "system": "__B3_PRIVATE_SYSTEM_SENTINEL__",
    }
    changed_contract["provider_generation_authority"]["generation"] = {
        key: sentinels[key]
        for key in (
            "provider",
            "prompt",
            "snippet",
            "timestamp",
            "exception",
            "path",
        )
    }
    for system in changed_contract["formal_system_authority"].values():
        system["formal_system_id"] = sentinels["system"]
    _rehash_contract(changed_contract)
    changed_results = tuple(
        dataclasses.replace(
            result,
            run_contract_sha256=changed_contract["run_contract_sha256"],
            formal_system_id=sentinels["system"],
        )
        for result in results
    )
    material = projection._build_projection_material(
        plan, changed_contract, changed_results, references
    )
    reviewer_bytes = b"".join(
        material.file_bytes[name] for name in projection._REVIEWER_FILES
    )
    private_values = [
        *sentinels.values(),
        results[0].request_id,
        results[0].execution_unit_id,
        results[0].envelope_sha256,
        material.objects[projection._PRIVATE_FILE]["canonical_commit_set_sha256"],
    ]
    for value in private_values:
        assert value.encode("utf-8") not in reviewer_bytes


def test_hmac_collision_rejected_without_fallback(synthetic_material, monkeypatch):
    plan, contract, results, references = synthetic_material[:4]
    monkeypatch.setattr(projection, "_hmac_digest", lambda *_args, **_kwargs: b"\x00" * 32)
    with pytest.raises(projection.ProjectionError, match="^B3_BLINDING_INCONSISTENT$"):
        projection._build_projection_material(plan, contract, results, references)


def test_reviewer_private_separation_and_prohibited_structural_keys(synthetic_material):
    material = synthetic_material[-1]
    projection._validate_privacy_boundary(material.objects)
    for filename in projection._REVIEWER_FILES:
        serialized = material.file_bytes[filename]
        for key in projection._PROHIBITED_REVIEWER_KEYS:
            assert f'"{key}":'.encode() not in serialized
    assert b'"entries":' not in material.file_bytes["manifest_v1.json"]
    assert b'"entries":' in material.file_bytes[projection._PRIVATE_FILE]
    leaked = copy.deepcopy(material.objects)
    leaked["rq1_primary_v1.json"]["records"][0]["display_payload"][
        "provider"
    ] = "synthetic-private-provider"
    with pytest.raises(
        projection.ProjectionError,
        match="^B3_PRIVACY_BOUNDARY_VIOLATION$",
    ):
        projection._validate_privacy_boundary(leaked)


def test_legitimate_answer_system_or_provider_name_is_not_redacted(synthetic_material):
    plan, contract, results, references = synthetic_material[:4]
    answer = "Legitimate model text mentions DeepSeek and context_aware"
    changed = (dataclasses.replace(results[0], response_text=answer, response_sha256=_sha(answer)),) + results[1:]
    material = projection._build_projection_material(plan, contract, changed, references)
    assert answer in material.file_bytes["rq1_primary_v1.json"].decode("utf-8")


def test_manifest_internal_and_complete_file_hash_have_exact_distinct_meanings(synthetic_material):
    material = synthetic_material[-1]
    manifest = material.objects["manifest_v1.json"]
    private = material.objects[projection._PRIVATE_FILE]
    without = dict(manifest)
    del without["manifest_sha256"]
    internal = projection.domain_hash(
        "formal-evaluation-b3-reviewer-manifest-v1", "manifest", without
    )
    complete = hashlib.sha256(material.file_bytes["manifest_v1.json"]).hexdigest()
    assert internal == manifest["manifest_sha256"]
    assert internal == private["reviewer_manifest_sha256"]
    assert complete == private["reviewer_artifacts"]["manifest_v1.json"]
    assert internal != complete


def test_fresh_create_publication_order_idempotent_reopen_and_no_rewrite(
    synthetic_material, monkeypatch, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    moves = []
    original = projection._move_file_create_only

    def record(source, target):
        moves.append(target.name)
        return original(source, target)

    monkeypatch.setattr(projection, "_move_file_create_only", record)
    created = projection._publish_material(material)
    assert created.action == "created"
    assert moves == list(projection._PUBLICATION_ORDER)
    root = isolated_roots_and_offline_guard["b3"]
    before = {
        name: (_final(root, name).read_bytes(), _final(root, name).stat().st_mtime_ns)
        for name in projection._PUBLICATION_ORDER
    }
    moves.clear()
    reopened = projection._publish_material(material)
    assert reopened.action == "already_complete"
    assert moves == []
    after = {
        name: (_final(root, name).read_bytes(), _final(root, name).stat().st_mtime_ns)
        for name in projection._PUBLICATION_ORDER
    }
    assert before == after
    assert reopened.reviewer_manifest_sha256 == material.reviewer_manifest_sha256


@pytest.mark.parametrize("boundary", projection._PUBLICATION_ORDER)
def test_interruption_after_each_publication_boundary_resumes_exactly(
    synthetic_material, monkeypatch, boundary
):
    material = synthetic_material[-1]
    original = projection._publish_final
    triggered = False

    def interrupt(root, filename, expected, lock):
        nonlocal triggered
        published = original(root, filename, expected, lock)
        if filename == boundary and not triggered:
            triggered = True
            raise projection.ProjectionError("B3_IO_FAILURE")
        return published

    monkeypatch.setattr(projection, "_publish_final", interrupt)
    with pytest.raises(projection.ProjectionError, match="^B3_IO_FAILURE$"):
        projection._publish_material(material)
    monkeypatch.setattr(projection, "_publish_final", original)
    outcome = projection._publish_material(material)
    assert outcome.action == (
        "already_complete" if boundary == "manifest_v1.json" else "resumed"
    )


def test_failure_before_rename_leaves_owned_temp_then_resumes(
    synthetic_material, monkeypatch, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    original = projection._move_file_create_only
    monkeypatch.setattr(
        projection,
        "_move_file_create_only",
        lambda *_args: (_ for _ in ()).throw(projection.ProjectionError("B3_IO_FAILURE")),
    )
    with pytest.raises(projection.ProjectionError, match="^B3_IO_FAILURE$"):
        projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    assert any(path.name.endswith(".tmp") for path in (root / "private").iterdir())
    monkeypatch.setattr(projection, "_move_file_create_only", original)
    outcome = projection._publish_material(material)
    assert outcome.action == "resumed"
    assert not any(path.name.endswith(".tmp") for path in root.rglob("*"))


def test_uncertain_failure_after_rename_recovers_exact_final_without_duplicate(
    synthetic_material, monkeypatch
):
    material = synthetic_material[-1]
    original = projection._move_file_create_only
    calls = []

    def uncertain(source, target):
        original(source, target)
        calls.append(target.name)
        raise projection.ProjectionError("B3_IO_FAILURE")

    monkeypatch.setattr(projection, "_move_file_create_only", uncertain)
    outcome = projection._publish_material(material)
    assert outcome.action == "created"
    assert calls == list(projection._PUBLICATION_ORDER)


def test_absent_mapping_partial_bundle_reconstructs_mapping_first_and_preserves_existing(
    synthetic_material, monkeypatch, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    original = projection._publish_final
    stopped = False

    def stop_after_primary(root, filename, expected, lock):
        nonlocal stopped
        published = original(root, filename, expected, lock)
        if filename == "rq1_primary_v1.json" and not stopped:
            stopped = True
            raise projection.ProjectionError("B3_IO_FAILURE")
        return published

    monkeypatch.setattr(projection, "_publish_final", stop_after_primary)
    with pytest.raises(projection.ProjectionError):
        projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    mapping = _final(root, projection._PRIVATE_FILE)
    primary = _final(root, "rq1_primary_v1.json")
    primary_before = primary.read_bytes()
    mapping.unlink()
    monkeypatch.setattr(projection, "_publish_final", original)
    moves = []
    move = projection._move_file_create_only

    def record(source, target):
        moves.append(target.name)
        return move(source, target)

    monkeypatch.setattr(projection, "_move_file_create_only", record)
    outcome = projection._publish_material(material)
    assert outcome.action == "resumed"
    assert moves[0] == projection._PRIVATE_FILE
    assert primary.read_bytes() == primary_before


def test_absent_mapping_all_data_without_manifest_publishes_mapping_then_manifest(
    synthetic_material, monkeypatch, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    original = projection._publish_final

    def stop_before_manifest(root, filename, expected, lock):
        if filename == "manifest_v1.json":
            raise projection.ProjectionError("B3_IO_FAILURE")
        return original(root, filename, expected, lock)

    monkeypatch.setattr(projection, "_publish_final", stop_before_manifest)
    with pytest.raises(projection.ProjectionError):
        projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    _final(root, projection._PRIVATE_FILE).unlink()
    monkeypatch.setattr(projection, "_publish_final", original)
    moves = []
    move = projection._move_file_create_only

    def record(source, target):
        moves.append(target.name)
        return move(source, target)

    monkeypatch.setattr(projection, "_move_file_create_only", record)
    outcome = projection._publish_material(material)
    assert outcome.action == "resumed"
    assert moves == [projection._PRIVATE_FILE, "manifest_v1.json"]


def test_complete_reviewer_bundle_without_mapping_publishes_only_mapping(
    synthetic_material, monkeypatch, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    reviewer_before = {
        name: _final(root, name).read_bytes() for name in projection._REVIEWER_FILES
    }
    _final(root, projection._PRIVATE_FILE).unlink()
    moves = []
    original = projection._move_file_create_only

    def record(source, target):
        moves.append(target.name)
        return original(source, target)

    monkeypatch.setattr(projection, "_move_file_create_only", record)
    outcome = projection._publish_material(material)
    assert outcome.action == "resumed"
    assert moves == [projection._PRIVATE_FILE]
    assert reviewer_before == {
        name: _final(root, name).read_bytes() for name in projection._REVIEWER_FILES
    }


@pytest.mark.parametrize("phase", ["before_mapping_rename", "after_mapping_rename"])
def test_mapping_reconstruction_interruption_reopens_without_reviewer_rewrite(
    synthetic_material,
    monkeypatch,
    isolated_roots_and_offline_guard,
    phase,
):
    material = synthetic_material[-1]
    projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    mapping = _final(root, projection._PRIVATE_FILE)
    mapping.unlink()
    reviewer_before = {
        name: (_final(root, name).read_bytes(), _final(root, name).stat().st_mtime_ns)
        for name in projection._REVIEWER_FILES
    }
    original_move = projection._move_file_create_only
    original_publish = projection._publish_final
    if phase == "before_mapping_rename":
        def interrupt_before(source, target):
            if target.name == projection._PRIVATE_FILE:
                raise projection.ProjectionError("B3_IO_FAILURE")
            return original_move(source, target)

        monkeypatch.setattr(projection, "_move_file_create_only", interrupt_before)
    else:
        def interrupt_after(root_arg, filename, expected, lock):
            published = original_publish(root_arg, filename, expected, lock)
            if filename == projection._PRIVATE_FILE:
                raise projection.ProjectionError("B3_IO_FAILURE")
            return published

        monkeypatch.setattr(projection, "_publish_final", interrupt_after)
    with pytest.raises(projection.ProjectionError, match="^B3_IO_FAILURE$"):
        projection._publish_material(material)
    if phase == "before_mapping_rename":
        assert not mapping.exists()
    else:
        assert mapping.read_bytes() == material.file_bytes[projection._PRIVATE_FILE]
    monkeypatch.setattr(projection, "_move_file_create_only", original_move)
    monkeypatch.setattr(projection, "_publish_final", original_publish)
    outcome = projection._publish_material(material)
    assert outcome.action == (
        "resumed" if phase == "before_mapping_rename" else "already_complete"
    )
    assert reviewer_before == {
        name: (_final(root, name).read_bytes(), _final(root, name).stat().st_mtime_ns)
        for name in projection._REVIEWER_FILES
    }


@pytest.mark.parametrize(
    "defect,expected",
    [
        ("unexpected_path", "B3_OUTPUT_PATH_INVALID"),
        ("wrong_object", "B3_OUTPUT_PATH_INVALID"),
        ("prohibited_collision", "B3_OUTPUT_PATH_INVALID"),
        ("artifact", "B3_ARTIFACT_INVALID"),
        ("version", "B3_SCHEMA_VERSION_MISMATCH"),
        ("hash", "B3_HASH_MISMATCH"),
        ("collision", "B3_OUTPUT_COLLISION"),
        ("mapping", "B3_BLINDING_INCONSISTENT"),
    ],
)
def test_existing_final_global_precedence_and_preservation(
    synthetic_material, isolated_roots_and_offline_guard, defect, expected
):
    material = synthetic_material[-1]
    projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    if defect == "unexpected_path":
        (root / "unexpected.txt").write_bytes(b"unexpected")
    elif defect == "wrong_object":
        target = _final(root, "rq1_primary_v1.json")
        target.unlink()
        target.mkdir()
    elif defect == "prohibited_collision":
        (root / "private" / "rq1_primary_v1.json").write_bytes(b"collision")
    elif defect == "artifact":
        _final(root, "rq1_primary_v1.json").write_bytes(b"\xff")
    elif defect == "version":
        value = copy.deepcopy(material.objects["rq1_primary_v1.json"])
        value["schema_version"] = 2
        _rewrite_json(_final(root, "rq1_primary_v1.json"), value)
    elif defect == "hash":
        value = copy.deepcopy(material.objects["manifest_v1.json"])
        value["manifest_sha256"] = "0" * 64
        _rewrite_json(_final(root, "manifest_v1.json"), value)
    elif defect == "collision":
        _final(root, projection._PRIVATE_FILE).unlink()
        _final(root, "manifest_v1.json").unlink()
        value = copy.deepcopy(material.objects["rq1_primary_v1.json"])
        value["records"][0]["display_payload"]["model_answer"] += " different"
        _rewrite_json(_final(root, "rq1_primary_v1.json"), value)
    else:
        value = copy.deepcopy(material.objects[projection._PRIVATE_FILE])
        value["counts"]["source_units"] = 189
        without = dict(value)
        without.pop("projection_manifest_sha256")
        value["projection_manifest_sha256"] = projection.domain_hash(
            "formal-evaluation-b3-private-manifest-v1", "manifest", without
        )
        _rewrite_json(_final(root, projection._PRIVATE_FILE), value)
    before = _tree_bytes(root)
    with pytest.raises(projection.ProjectionError, match=f"^{expected}$"):
        projection._publish_material(material)
    assert _tree_bytes(root) == before
    if defect == "wrong_object":
        assert _final(root, "rq1_primary_v1.json").is_dir()


def test_multi_defect_global_precedence_stops_at_first_category(
    synthetic_material, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    (root / "unexpected.txt").write_bytes(b"unexpected")
    _final(root, "rq1_primary_v1.json").write_bytes(b"{")
    value = copy.deepcopy(material.objects["rq2_v1.json"])
    value["schema_version"] = 2
    _rewrite_json(_final(root, "rq2_v1.json"), value)
    before = _tree_bytes(root)
    with pytest.raises(projection.ProjectionError, match="^B3_OUTPUT_PATH_INVALID$"):
        projection._publish_material(material)
    assert _tree_bytes(root) == before


def test_manifest_present_with_missing_dependency_is_hash_mismatch(
    synthetic_material, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    _final(root, "rq2_v1.json").unlink()
    with pytest.raises(projection.ProjectionError, match="^B3_HASH_MISMATCH$"):
        projection._publish_material(material)


def test_present_malformed_mapping_is_not_treated_as_absent(
    synthetic_material, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    mapping = _final(root, projection._PRIVATE_FILE)
    mapping.write_bytes(b"not-json")
    before = _tree_bytes(root)
    with pytest.raises(projection.ProjectionError, match="^B3_ARTIFACT_INVALID$"):
        projection._publish_material(material)
    assert _tree_bytes(root) == before


@pytest.mark.parametrize(
    "invalid_case_id",
    [
        pytest.param({"nested": "object"}, id="object"),
        pytest.param(["nested-array"], id="array"),
    ],
)
def test_present_canonical_mapping_with_nested_case_id_is_sanitized_artifact_invalid(
    synthetic_material,
    isolated_roots_and_offline_guard,
    monkeypatch,
    capsys,
    invalid_case_id,
):
    material = synthetic_material[-1]
    projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    mapping = _final(root, projection._PRIVATE_FILE)
    value = copy.deepcopy(material.objects[projection._PRIVATE_FILE])
    value["secondary_selection"]["case_ids"][0] = invalid_case_id
    malformed_bytes = projection._canonical_file_bytes(value)
    mapping.write_bytes(malformed_bytes)
    b2_before = _tree_bytes(isolated_roots_and_offline_guard["b2"])
    b3_before = _tree_bytes(root)
    calls = {"publication": 0, "provider_or_execution": 0}

    def forbid_publication(*_args, **_kwargs):
        calls["publication"] += 1
        raise AssertionError("publication or reconstruction invoked")

    def forbid_provider_or_execution(*_args, **_kwargs):
        calls["provider_or_execution"] += 1
        raise AssertionError("Provider, generation, or execution seam invoked")

    monkeypatch.setattr(projection, "_publish_final", forbid_publication)
    monkeypatch.setattr(projection, "_move_file_create_only", forbid_publication)
    for name in (
        "verify_frozen",
        "build_plan",
        "validate_plan",
        "build_durable_run_contract",
        "observe_validated_canonical_private_results",
        "_load_reference_sources",
        "_build_projection_material",
    ):
        monkeypatch.setattr(projection, name, forbid_provider_or_execution)
    monkeypatch.setattr(
        projection,
        "project_blinded_reviewer_outputs",
        lambda: projection._publish_material(material),
    )

    assert projection.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "B3_ARTIFACT_INVALID\n"
    assert calls == {"publication": 0, "provider_or_execution": 0}
    assert mapping.read_bytes() == malformed_bytes
    assert _tree_bytes(root) == b3_before
    assert _tree_bytes(isolated_roots_and_offline_guard["b2"]) == b2_before == {}


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("wrong_version", "B3_SCHEMA_VERSION_MISMATCH"),
        ("hash_invalid", "B3_HASH_MISMATCH"),
    ],
)
def test_present_wrong_version_or_hash_invalid_mapping_is_never_reconstructed(
    synthetic_material,
    isolated_roots_and_offline_guard,
    mutation,
    expected,
):
    material = synthetic_material[-1]
    projection._publish_material(material)
    root = isolated_roots_and_offline_guard["b3"]
    mapping = _final(root, projection._PRIVATE_FILE)
    value = copy.deepcopy(material.objects[projection._PRIVATE_FILE])
    if mutation == "wrong_version":
        value["schema_version"] = 2
    else:
        value["projection_manifest_sha256"] = "0" * 64
    _rewrite_json(mapping, value)
    before = _tree_bytes(root)
    with pytest.raises(projection.ProjectionError, match=f"^{expected}$"):
        projection._publish_material(material)
    assert _tree_bytes(root) == before


def test_public_projection_and_observation_apis_have_no_root_or_repair_arguments():
    assert list(inspect.signature(projection.project_blinded_reviewer_outputs).parameters) == []
    assert list(inspect.signature(runner.observe_validated_canonical_private_results).parameters) == [
        "plan"
    ]


@pytest.mark.parametrize(
    "path",
    [
        Path(r"\\server\share\reviewer_projection"),
        Path(r"\\?\C:\temp\reviewer_projection"),
        Path(r"C:\temp\..\reviewer_projection"),
        Path(r"C:\temp\CON\reviewer_projection"),
        Path("C:\\temp\\trailing.\\reviewer_projection"),
        Path("C:\\temp\\control\x01\\reviewer_projection"),
    ],
)
def test_fixed_path_grammar_rejects_prohibited_windows_forms(path):
    with pytest.raises(projection.ProjectionError, match="^B3_OUTPUT_PATH_INVALID$"):
        projection._validate_path_components(path)


@pytest.mark.parametrize("lock_bytes", [b"", b"x", b"\x00\x00"])
def test_malformed_existing_lock_stops_before_directory_creation(
    isolated_roots_and_offline_guard,
    lock_bytes,
):
    root = isolated_roots_and_offline_guard["b3"]
    lock = root / "projection.lock"
    lock.write_bytes(lock_bytes)
    before = _tree_bytes(root)
    with pytest.raises(projection.ProjectionError, match="^B3_OUTPUT_PATH_INVALID$"):
        projection._ensure_projection_directories(root)
    assert _tree_bytes(root) == before
    assert not (root / "private").exists()
    assert not (root / "reviewer").exists()


def test_projection_lock_is_one_byte_and_same_process_contention_fails(
    synthetic_material, isolated_roots_and_offline_guard
):
    material = synthetic_material[-1]
    root = projection._validate_projection_root_for_access()
    projection._ensure_projection_directories(root)
    with projection._ProjectionLock(root):
        with pytest.raises(projection.ProjectionError, match="^B3_LOCK_BUSY$"):
            with projection._ProjectionLock(root):
                pass
    assert (root / "projection.lock").read_bytes() == b"\x00"
    assert _tree_bytes(isolated_roots_and_offline_guard["b3"]) == {
        "projection.lock": b"\x00"
    }


def test_cli_prints_only_sanitized_category(monkeypatch, capsys):
    monkeypatch.setattr(
        projection,
        "project_blinded_reviewer_outputs",
        lambda: (_ for _ in ()).throw(
            projection.ProjectionError("B3_SOURCE_INELIGIBLE")
        ),
    )
    assert projection.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "B3_SOURCE_INELIGIBLE\n"


def test_generated_paths_are_ignored_and_untracked():
    root = projection._REPOSITORY_ROOT
    for path in (
        "data/formal_eval/reviewer_projection/private/projection_manifest_v1.json",
        "data/formal_eval/reviewer_projection/reviewer/manifest_v1.json",
    ):
        completed = subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=root, check=False
        )
        assert completed.returncode == 0
    tracked = subprocess.run(
        ["git", "ls-files", "--", "data/formal_eval/reviewer_projection"],
        cwd=root,
        check=True,
        text=True,
        capture_output=True,
    )
    assert tracked.stdout == ""
