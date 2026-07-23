from __future__ import annotations

import json
import importlib
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import formal_evaluation_inflight as f
import formal_evaluation_transport as t

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
T0 = "2026-07-23T10:00:00Z"
T1 = "2026-07-23T10:00:01Z"
T2 = "2026-07-23T10:00:02Z"
T3 = "2026-07-23T10:00:03Z"
T4 = "2026-07-23T10:00:04Z"


def resource(config: str = "v2") -> t.ProductionResourceIdentity:
    identity = t.formal_identity(config)
    v2 = identity.resource_family == "v2_mixed"
    resource_type = "synthetic_fixture"
    version = "synthetic_v1"
    value = {
        "schema_version": 1,
        "resource_type": resource_type,
        "logical_resource_id": f"{resource_type}_{identity.resource_family}_{version}",
        "system_config_id": config,
        "formal_system_id": identity.formal_system_id,
        "corpus_path": f"synthetic/{identity.resource_family}/corpus.json",
        "embeddings_path": f"synthetic/{identity.resource_family}/embeddings.npy",
        "corpus_sha256": A,
        "embeddings_sha256": B,
        "cache_family": identity.resource_family,
        "corpus_version": version,
        "row_count": 15688 if v2 else 15333,
        "qa_count": 15333,
        "snippet_count": 355 if v2 else 0,
        "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "embedding_rows": 15688 if v2 else 15333,
        "embedding_dimensions": 384,
        "synthetic": True,
    }
    return t.ProductionResourceIdentity.from_mapping(value)


def identity(
    *,
    system: str = "v2",
    rq: str = "RQ1",
    turn: int = 1,
    attempt: int = 1,
    request_id: str = A,
    execution_order: int = 1,
    case_id: str = "case_1",
) -> f.ExecutionIdentity:
    system_identity = t.formal_identity(system)
    execution_unit_id = f.derive_execution_unit_id(
        plan_fingerprint=f.PLAN_FINGERPRINT,
        request_id=request_id,
        execution_order=execution_order,
    )
    dialogue_id = case_id if rq == "RQ3" else None
    checkpoint_sha = C if rq == "RQ3" and system == "context_aware" and turn == 2 else None
    checkpoint_id = (
        f.derive_checkpoint_id(
            plan_fingerprint=f.PLAN_FINGERPRINT,
            execution_unit_id=execution_unit_id,
            dialogue_id=dialogue_id,
            system_config_id=system,
            input_checkpoint_sha256=checkpoint_sha,
        )
        if checkpoint_sha is not None
        else None
    )
    resource_identity = resource(system)
    base_identity = {
        "plan_fingerprint": f.PLAN_FINGERPRINT,
        "execution_unit_id": execution_unit_id,
        "execution_order": execution_order,
        "request_id": request_id,
        "rq": rq,
        "case_id": case_id,
        "dialogue_id": dialogue_id,
        "turn_index": turn,
        "system_config_id": system,
        "formal_system_id": system_identity.formal_system_id,
        "resolved_runtime_system_id": system_identity.resolved_runtime_system_id,
        "payload_sha256": B,
        "resolved_payload_sha256": C,
        "transport_contract_id": t.transport_contract_id(),
        "transport_contract_sha256": t.transport_contract_sha256(),
        "generation_contract_id": t.generation_contract_id(),
        "generation_contract_sha256": t.generation_contract_sha256(),
        "resource_identity": resource_identity,
        "resource_identity_sha256": t.resource_identity_sha256(resource_identity),
        "input_checkpoint_sha256": checkpoint_sha,
        "provider": "DeepSeek",
        "provider_model": "deepseek-chat",
    }
    attempt_id = f.derive_attempt_id(identity=base_identity, attempt_number=attempt)
    return f.ExecutionIdentity(
        plan_fingerprint=f.PLAN_FINGERPRINT,
        execution_unit_id=execution_unit_id,
        execution_order=execution_order,
        request_id=request_id,
        rq=rq,
        case_id=case_id,
        dialogue_id=dialogue_id,
        turn_index=turn,
        turn_id=f.derive_turn_id(
            execution_unit_id=execution_unit_id,
            rq=rq,
            case_id=case_id,
            turn_index=turn,
        ),
        system_config_id=system,
        formal_system_id=system_identity.formal_system_id,
        resolved_runtime_system_id=system_identity.resolved_runtime_system_id,
        payload_sha256=B,
        resolved_payload_sha256=C,
        transport_contract_id=t.transport_contract_id(),
        transport_contract_sha256=t.transport_contract_sha256(),
        generation_contract_id=t.generation_contract_id(),
        generation_contract_sha256=t.generation_contract_sha256(),
        resource_identity=resource_identity,
        resource_identity_sha256=t.resource_identity_sha256(resource_identity),
        input_checkpoint_id=checkpoint_id,
        input_checkpoint_sha256=checkpoint_sha,
        attempt_number=attempt,
        attempt_id=attempt_id,
        provider="DeepSeek",
        provider_model="deepseek-chat",
    )


def prepared(ident: f.ExecutionIdentity | None = None) -> f.InflightJournal:
    return f.create_initial_journal(ident or identity(), T0)


def call_started(record: f.InflightJournal | None = None) -> f.InflightJournal:
    record = record or prepared()
    return f.transition(
        record,
        "call_started",
        T1,
        provider_request_id=f.derive_provider_request_id(record.identity),
    )


def returned(record: f.InflightJournal | None = None) -> f.InflightJournal:
    return f.transition(
        call_started(record),
        "provider_returned",
        T2,
        provider_response_id="response_1",
        provider_response_sha256=B,
        response_sha256=C,
    )


def success(ident: f.ExecutionIdentity | None = None) -> f.AuthoritativeSuccess:
    ident = ident or identity()
    return f.AuthoritativeSuccess(
        schema_version=1,
        identity=ident,
        provider_request_id=f.derive_provider_request_id(ident),
        provider_response_id="response_1",
        provider_response_sha256=B,
        response_sha256=C,
        call_started_at=T1,
        provider_returned_at=T2,
        committed_at=T4,
        execution_status="success",
    )


def projection_control(module, ident, *, text: str = "synthetic safe output") -> dict:
    authoritative = module.AuthoritativeSuccess(
        schema_version=1,
        identity=ident,
        provider_request_id=module.derive_provider_request_id(ident),
        provider_response_id="response_1",
        provider_response_sha256=B,
        response_sha256=t.sha256_text(text),
        call_started_at=T1,
        provider_returned_at=T2,
        committed_at=T4,
        execution_status="success",
    )
    return {
        "plan_fingerprint": ident.plan_fingerprint,
        "execution_unit_id": ident.execution_unit_id,
        "execution_order": ident.execution_order,
        "request_id": ident.request_id,
        "research_question": ident.rq,
        "case_id": ident.case_id,
        "dialogue_id": ident.dialogue_id,
        "turn_index": ident.turn_index,
        "turn_id": ident.turn_id,
        "input_checkpoint_id": ident.input_checkpoint_id,
        "input_checkpoint_sha256": ident.input_checkpoint_sha256,
        "system_config_id": ident.system_config_id,
        "formal_system_id": ident.formal_system_id,
        "resolved_runtime_system_id": ident.resolved_runtime_system_id,
        "payload_sha256": ident.payload_sha256,
        "resolved_payload_sha256": ident.resolved_payload_sha256,
        "transport_contract_id": ident.transport_contract_id,
        "transport_contract_sha256": ident.transport_contract_sha256,
        "generation_contract_id": ident.generation_contract_id,
        "generation_contract_sha256": ident.generation_contract_sha256,
        "transport_implementation_sha256": D,
        "resource_identity": ident.resource_identity.to_dict(),
        "resource_identity_sha256": ident.resource_identity_sha256,
        "attempt_id": ident.attempt_id,
        "execution_status": "success",
        "status": "success",
        "response_text": text,
        "response_sha256": authoritative.response_sha256,
        "provider_called": True,
        "provider": ident.provider,
        "provider_model": ident.provider_model,
        "provider_request_id": authoritative.provider_request_id,
        "provider_response_id": authoritative.provider_response_id,
        "provider_response_sha256": authoritative.provider_response_sha256,
        "call_started_at": authoritative.call_started_at,
        "provider_returned_at": authoritative.provider_returned_at,
        "committed_at": authoritative.committed_at,
        "authoritative_success": authoritative.to_dict(),
        "attempt_count": ident.attempt_number,
    }


def state_family() -> list[f.InflightJournal]:
    base = prepared()
    started = call_started(base)
    provider_returned = returned(base)
    pre_send = f.transition(
        base,
        "retryable_failed",
        T1,
        sanitized_outcome_category="pre_send_failure",
    )
    post_retry = f.transition(
        started,
        "retryable_failed",
        T2,
        sanitized_outcome_category="http_429",
    )
    terminal = f.transition(
        started,
        "terminal_failed",
        T2,
        sanitized_outcome_category="invalid_response",
    )
    uncertain = f.transition(
        started,
        "uncertain",
        T2,
        sanitized_outcome_category="timeout",
    )
    committed = f.reconcile(provider_returned, success())
    return [
        base,
        started,
        provider_returned,
        pre_send,
        post_retry,
        terminal,
        uncertain,
        committed,
    ]


class IdentityAndMatrixTests(unittest.TestCase):
    def test_public_transport_callable_rebinding_cannot_poison_fresh_or_loaded_inflight(self):
        canonical = identity()
        original_inflight = sys.modules["formal_evaluation_inflight"]
        names = (
            "formal_identity",
            "generation_contract_id",
            "generation_contract_sha256",
            "resource_identity_sha256",
            "transport_contract_id",
            "transport_contract_sha256",
            "validate_provider_identity",
            "validate_resource_identity",
            "validate_sha256",
        )
        originals = {name: getattr(t, name) for name in names}
        try:
            for name in names:
                setattr(t, name, lambda *args, **kwargs: "poisoned")
            sys.modules.pop("formal_evaluation_inflight", None)
            fresh = importlib.import_module("formal_evaluation_inflight")
            fresh_identity = fresh.ExecutionIdentity.from_mapping(canonical.to_dict())
            self.assertEqual(canonical.to_dict(), fresh_identity.to_dict())
            fresh.validate_execution_identity(fresh_identity)
            fresh_journal = fresh.create_initial_journal(fresh_identity, T0)
            fresh_success = fresh.AuthoritativeSuccess.from_mapping(success(canonical).to_dict())
            self.assertEqual(
                "reconcile_committed",
                fresh.recovery_decision(
                    fresh_journal,
                    authoritative_success=fresh_success,
                    expected=fresh_identity,
                ),
            )
            # The same poisoned public exports remain irrelevant after import.
            fresh.validate_execution_identity(fresh_identity)
            self.assertEqual(
                fresh.derive_provider_request_id(fresh_identity),
                fresh_success.provider_request_id,
            )
        finally:
            for name, value in originals.items():
                setattr(t, name, value)
            sys.modules["formal_evaluation_inflight"] = original_inflight

    def test_public_resource_rebinding_isolated_before_and_after_inflight_import(self):
        canonical = identity()
        canonical_resource_hash = t.resource_identity_sha256(canonical.resource_identity)
        original_inflight = sys.modules["formal_evaluation_inflight"]
        original_resource = t.ProductionResourceIdentity
        original_formal_identity = t.FormalSystemIdentity

        class ReboundResource:
            def __init__(self):
                for field, value in canonical.resource_identity.to_dict().items():
                    setattr(self, field, value)

            @classmethod
            def from_mapping(cls, value):
                return cls()

            def to_dict(self):
                changed = canonical.resource_identity.to_dict()
                changed["system_config_id"] = "single_turn"
                return changed

        class ReboundFormalIdentity:
            pass

        def exercise(module, restored):
            checked = module.ExecutionIdentity.from_mapping(canonical.to_dict())
            module.validate_execution_identity(checked)
            self.assertEqual(canonical_resource_hash, t.resource_identity_sha256(checked.resource_identity))
            self.assertEqual(
                checked.attempt_id,
                module.derive_attempt_id(
                    identity={key: checked.to_dict()[key] for key in module._BASE_EXECUTION_FIELDS},
                    attempt_number=checked.attempt_number,
                ),
            )
            initial = module.create_initial_journal(checked, T0)
            authoritative = module.AuthoritativeSuccess(
                schema_version=1,
                identity=checked,
                provider_request_id=module.derive_provider_request_id(checked),
                provider_response_id="response_1",
                provider_response_sha256=B,
                response_sha256=C,
                call_started_at=T1,
                provider_returned_at=T2,
                committed_at=T4,
                execution_status="success",
            )
            committed = module.reconcile(initial, authoritative, checked)
            self.assertEqual("confirmed", module.recovery_decision(
                committed, authoritative_success=authoritative, expected=checked
            ))
            self.assertEqual("success", t.project_formal_result(projection_control(module, checked))["status"])
            fake = ReboundResource()
            with self.assertRaises(t.TransportError) as raised:
                t.validate_resource_identity(fake)
            self.assertEqual("RESOURCE_IDENTITY_INVALID", raised.exception.category)
            with self.assertRaises(t.TransportError) as raised:
                t.resource_identity_sha256(fake)
            self.assertEqual("RESOURCE_IDENTITY_INVALID", raised.exception.category)
            self.assertEqual("current_v2", t.formal_identity("v2").formal_system_id)
            self.assertIs(restored, module)

        try:
            t.ProductionResourceIdentity = ReboundResource
            t.FormalSystemIdentity = ReboundFormalIdentity
            sys.modules.pop("formal_evaluation_inflight", None)
            fresh = importlib.import_module("formal_evaluation_inflight")
            exercise(fresh, fresh)
            sys.modules["formal_evaluation_inflight"] = original_inflight
            exercise(original_inflight, original_inflight)
        finally:
            t.ProductionResourceIdentity = original_resource
            t.FormalSystemIdentity = original_formal_identity
            sys.modules["formal_evaluation_inflight"] = original_inflight

    def test_public_contract_snapshots_are_not_live_authority(self):
        valid = identity()
        third_identity = identity(attempt=3)
        valid_journal = prepared(valid)
        original_plan = f.PLAN_FINGERPRINT
        original_attempts = f.MAX_ATTEMPTS
        original_states = f.STATES
        f.PLAN_FINGERPRINT = A
        f.MAX_ATTEMPTS = 99
        f.STATES = frozenset({"forged"})
        try:
            f.validate_execution_identity(valid)
            third_failed = f.InflightJournal(
                schema_version=3,
                identity=third_identity,
                state="retryable_failed",
                prepared_at=T0,
                call_started_at=None,
                provider_returned_at=None,
                failed_at=T1,
                committed_at=None,
                updated_at=T1,
                sanitized_outcome_category="pre_send_failure",
                provider_request_id=None,
                provider_response_id=None,
                provider_response_sha256=None,
                response_sha256=None,
            )
            self.assertEqual(
                "fail_closed",
                f.recovery_decision(third_failed, expected=third_identity),
            )
            with self.assertRaises(f.JournalError):
                replace(valid_journal, state="forged")
        finally:
            f.PLAN_FINGERPRINT = original_plan
            f.MAX_ATTEMPTS = original_attempts
            f.STATES = original_states

    def test_every_permitted_rq_system_turn_family(self):
        permitted = (
            ("RQ1", "qa_only_reconstructed_baseline", 1),
            ("RQ1", "v2", 1),
            ("RQ2", "qa_only_reconstructed_baseline", 1),
            ("RQ2", "v2", 1),
            ("RQ3", "single_turn", 1),
            ("RQ3", "single_turn", 2),
            ("RQ3", "context_aware", 1),
            ("RQ3", "context_aware", 2),
        )
        for rq, system, turn in permitted:
            f.validate_execution_identity(identity(rq=rq, system=system, turn=turn))

    def test_impossible_rq_system_turn_checkpoint_combinations_fail(self):
        base = identity()
        mutations = (
            {"rq": "RQ1", "system_config_id": "context_aware",
             "formal_system_id": "v21b_context_aware",
             "resolved_runtime_system_id": "v21b_context_aware",
             "resource_identity": resource("context_aware"),
             "resource_identity_sha256": t.resource_identity_sha256(resource("context_aware"))},
            {"turn_index": 2},
            {"rq": "RQ3", "dialogue_id": "case_1", "system_config_id": "v2"},
            {"input_checkpoint_sha256": C, "input_checkpoint_id": "checkpoint_" + A},
        )
        for changes in mutations:
            with self.assertRaises(f.JournalError, msg=repr(changes)):
                replace(base, **changes)
        context_two = identity(rq="RQ3", system="context_aware", turn=2)
        for changes in (
            {"input_checkpoint_id": None},
            {"input_checkpoint_sha256": None},
            {"input_checkpoint_id": "checkpoint_" + A},
            {"dialogue_id": "foreign_dialogue"},
        ):
            with self.assertRaises(f.JournalError, msg=repr(changes)):
                replace(context_two, **changes)

    def test_complete_identity_binds_contract_resource_and_runtime(self):
        valid = identity()
        mapping = valid.to_dict()
        restored = f.ExecutionIdentity.from_mapping(mapping)
        self.assertEqual(valid, restored)
        mapping["resource_identity"]["corpus_path"] = "synthetic/v2_mixed/mutated.json"
        self.assertEqual(
            "synthetic/v2_mixed/corpus.json",
            restored.resource_identity.corpus_path,
        )
        f.validate_execution_identity(restored)
        mutations = (
            ("plan_fingerprint", A),
            ("execution_unit_id", B),
            ("execution_order", 2),
            ("request_id", B),
            ("turn_id", "turn_" + A),
            ("formal_system_id", "v2_without_context_management"),
            ("resolved_runtime_system_id", "v2_without_context_management"),
            ("transport_contract_id", "other_transport"),
            ("transport_contract_sha256", A),
            ("generation_contract_id", "other_generation"),
            ("generation_contract_sha256", B),
            ("resource_identity_sha256", A),
            ("provider", "Other"),
            ("provider_model", "other"),
        )
        for key, value in mutations:
            changed = valid.to_dict()
            changed[key] = value
            with self.assertRaises(f.JournalError, msg=key):
                f.ExecutionIdentity.from_mapping(changed)
        changed = valid.to_dict()
        changed["resource_identity"]["corpus_path"] = "synthetic/v2_mixed/other.json"
        with self.assertRaises(f.JournalError):
            f.ExecutionIdentity.from_mapping(changed)

    def test_complete_authority_substitutions_change_attempt_and_provider_ids(self):
        base = identity()

        def amended(source: f.ExecutionIdentity, **changes: object) -> f.ExecutionIdentity:
            raw = source.to_dict()
            raw.update(changes)
            raw["turn_id"] = f.derive_turn_id(
                execution_unit_id=raw["execution_unit_id"],
                rq=raw["rq"],
                case_id=raw["case_id"],
                turn_index=raw["turn_index"],
            )
            base_authority = {key: raw[key] for key in f._BASE_EXECUTION_FIELDS}
            raw["attempt_id"] = f.derive_attempt_id(
                identity=base_authority, attempt_number=raw["attempt_number"]
            )
            return f.ExecutionIdentity.from_mapping(raw)

        payload_changed = amended(base, payload_sha256=D)
        resolved_changed = amended(base, resolved_payload_sha256=D)
        rq_changed = amended(base, rq="RQ2")
        case_changed = amended(base, case_id="case_2")
        request_changed = identity(request_id=B, execution_order=1)
        order_changed = identity(request_id=A, execution_order=2)
        turn_one = identity(rq="RQ3", system="single_turn", turn=1, case_id="case_3")
        turn_two = identity(rq="RQ3", system="single_turn", turn=2, case_id="case_3")
        resource_system_changed = identity(rq="RQ3", system="single_turn")
        resource_context_changed = identity(rq="RQ3", system="context_aware")
        resource_raw = base.to_dict()
        changed_resource = resource_raw["resource_identity"]
        changed_resource["corpus_sha256"] = D
        resource_raw["resource_identity_sha256"] = t.resource_identity_sha256(
            t.ProductionResourceIdentity.from_mapping(changed_resource)
        )
        resource_raw["attempt_id"] = f.derive_attempt_id(
            identity={key: resource_raw[key] for key in f._BASE_EXECUTION_FIELDS},
            attempt_number=base.attempt_number,
        )
        resource_changed = f.ExecutionIdentity.from_mapping(resource_raw)
        checkpoint = identity(rq="RQ3", system="context_aware", turn=2)
        checkpoint_raw = checkpoint.to_dict()
        checkpoint_raw["input_checkpoint_sha256"] = D
        checkpoint_raw["input_checkpoint_id"] = f.derive_checkpoint_id(
            plan_fingerprint=checkpoint.plan_fingerprint,
            execution_unit_id=checkpoint.execution_unit_id,
            dialogue_id=checkpoint.dialogue_id,
            system_config_id=checkpoint.system_config_id,
            input_checkpoint_sha256=D,
        )
        checkpoint_raw["attempt_id"] = f.derive_attempt_id(
            identity={key: checkpoint_raw[key] for key in f._BASE_EXECUTION_FIELDS},
            attempt_number=checkpoint.attempt_number,
        )
        checkpoint_changed = f.ExecutionIdentity.from_mapping(checkpoint_raw)
        pairs = (
            (base, payload_changed, "payload"),
            (base, resolved_changed, "resolved payload"),
            (base, rq_changed, "research question"),
            (base, case_changed, "case/turn"),
            (base, request_changed, "request ID/execution unit"),
            (base, order_changed, "execution order/execution unit"),
            (turn_one, turn_two, "turn identity"),
            (resource_system_changed, resource_context_changed, "formal/runtime/resource family"),
            (base, resource_changed, "complete resource identity"),
            (checkpoint, checkpoint_changed, "checkpoint"),
        )
        for left, right, label in pairs:
            self.assertNotEqual(left.attempt_id, right.attempt_id, label)
            self.assertNotEqual(
                f.derive_provider_request_id(left),
                f.derive_provider_request_id(right),
                label,
            )

    def test_expected_identity_is_closed_complete_and_exact(self):
        valid = identity()
        self.assertEqual(valid, f.validate_expected_identity(valid.to_dict()))
        for malformed in (
            None,
            {},
            {"malformed": True},
            {key: value for key, value in valid.to_dict().items() if key != "request_id"},
            {**valid.to_dict(), "extra": 1},
            [],
            "identity",
        ):
            with self.assertRaises(f.JournalError, msg=repr(malformed)[:80]):
                f.validate_expected_identity(malformed)


class AttemptLifecycleTests(unittest.TestCase):
    def test_attempt_type_range_and_identity_enforced_at_construction(self):
        valid = identity()
        for attempt in (0, 4, 99, True, "1", 1.0):
            raw = valid.to_dict()
            raw["attempt_number"] = attempt
            with self.assertRaises(f.JournalError, msg=repr(attempt)):
                f.ExecutionIdentity.from_mapping(raw)
        raw = valid.to_dict()
        raw["attempt_number"] = 3
        raw["attempt_id"] = valid.attempt_id
        with self.assertRaises(f.JournalError):
            f.ExecutionIdentity.from_mapping(raw)
        valid_three = identity(attempt=3)
        f.validate_execution_identity(valid_three)
        with self.assertRaises(f.JournalError):
            f.create_initial_journal(valid_three, T0)

    def test_invalid_attempts_fail_deserialization_and_never_serialize(self):
        raw = prepared().to_dict()
        for attempt in (0, 4, True, "1", 1.0):
            changed = json.loads(json.dumps(raw))
            changed["identity"]["attempt_number"] = attempt
            with self.assertRaises(f.JournalError, msg=repr(attempt)):
                f.InflightJournal.from_mapping(changed)
        self.assertEqual(1, prepared().to_dict()["identity"]["attempt_number"])

    def test_predecessor_aware_retry_increments_exactly_once(self):
        first = f.transition(
            prepared(),
            "retryable_failed",
            T1,
            sanitized_outcome_category="pre_send_failure",
        )
        second = f.next_retry_journal(first, T2)
        self.assertEqual(2, second.identity.attempt_number)
        self.assertEqual(
            f.derive_attempt_id(identity=first.identity, attempt_number=2),
            second.identity.attempt_id,
        )
        first_base = first.identity.to_dict()
        second_base = second.identity.to_dict()
        for field in set(first_base) - {"attempt_number", "attempt_id"}:
            self.assertEqual(first_base[field], second_base[field], field)
        second_failed = f.transition(
            second,
            "retryable_failed",
            T3,
            sanitized_outcome_category="pre_send_failure",
        )
        third = f.next_retry_journal(second_failed, T4)
        self.assertEqual(3, third.identity.attempt_number)
        self.assertEqual(second, f.next_retry_journal(first, T2))
        third_failed = f.InflightJournal(
            schema_version=3,
            identity=third.identity,
            state="retryable_failed",
            prepared_at=T4,
            call_started_at=None,
            provider_returned_at=None,
            failed_at="2026-07-23T10:00:05Z",
            committed_at=None,
            updated_at="2026-07-23T10:00:05Z",
            sanitized_outcome_category="pre_send_failure",
            provider_request_id=None,
            provider_response_id=None,
            provider_response_sha256=None,
            response_sha256=None,
        )
        with self.assertRaises(f.JournalError) as raised:
            f.next_retry_journal(third_failed, "2026-07-23T10:00:06Z")
        self.assertEqual("RETRY_PREDECESSOR_INVALID", raised.exception.category)
        self.assertEqual(
            "fail_closed",
            f.recovery_decision(third_failed, expected=third.identity),
        )

    def test_retry_refuses_repeat_skip_backward_and_nonretryable_predecessors(self):
        for record in state_family():
            if record.state == "retryable_failed":
                continue
            with self.assertRaises(f.JournalError, msg=record.state):
                f.next_retry_journal(record, "2026-07-23T10:00:10Z")
        retryable = f.transition(
            prepared(),
            "retryable_failed",
            T1,
            sanitized_outcome_category="pre_send_failure",
        )
        with self.assertRaises(f.JournalError):
            f.next_retry_journal(retryable, T0)
        next_record = f.next_retry_journal(retryable, T2)
        self.assertNotEqual(retryable.identity.attempt_id, next_record.identity.attempt_id)
        self.assertEqual(
            retryable.identity.execution_unit_id, next_record.identity.execution_unit_id
        )


class JournalStateAndTimestampTests(unittest.TestCase):
    def test_state_lifecycle_and_provider_called_semantics(self):
        base = prepared()
        self.assertFalse(base.provider_called)
        pre_send = f.transition(
            base,
            "retryable_failed",
            T1,
            sanitized_outcome_category="pre_send_failure",
        )
        self.assertFalse(pre_send.provider_called)
        self.assertIsNone(pre_send.provider_request_id)
        started = call_started(base)
        self.assertTrue(started.provider_called)
        terminal = f.transition(
            started,
            "terminal_failed",
            T2,
            sanitized_outcome_category="invalid_response",
        )
        self.assertTrue(terminal.provider_called)
        with self.assertRaises(f.JournalError):
            f.transition(started, "prepared", T2)
        with self.assertRaises(f.JournalError):
            f.transition(started, "provider_returned", T2, provider_response_id="response_1")
        with self.assertRaises(FrozenInstanceError):
            base.state = "committed"

    def test_failure_metadata_is_state_exact(self):
        started = call_started()
        call_id = f.derive_provider_request_id(started.identity)
        bad_records = (
            {**prepared().to_dict(), "state": "retryable_failed",
             "failed_at": T1, "updated_at": T1,
             "sanitized_outcome_category": "pre_send_failure",
             "provider_request_id": call_id},
            {**started.to_dict(), "state": "retryable_failed",
             "failed_at": T2, "updated_at": T2,
             "sanitized_outcome_category": "http_429",
             "provider_request_id": None},
            {**started.to_dict(), "state": "terminal_failed",
             "failed_at": T2, "updated_at": T2,
             "sanitized_outcome_category": "authentication_failure",
             "provider_response_id": "response_1"},
            {**returned().to_dict(), "state": "committed",
             "committed_at": T4, "updated_at": T4,
             "sanitized_outcome_category": "provider_success",
             "failed_at": T3},
        )
        for raw in bad_records:
            with self.assertRaises(f.JournalError):
                f.InflightJournal.from_mapping(raw)

    def test_impossible_timezone_and_nonmonotonic_timestamps_fail(self):
        raw = prepared().to_dict()
        invalid = (
            "2026-02-30T10:00:00Z",
            "2026-13-01T10:00:00Z",
            "2026-07-23T25:00:00Z",
            "2026-07-23T10:00:00",
            "2026-07-23T11:00:00+01:00",
            "2026-07-23t10:00:00z",
            "2026-07-23T10:00:00Z\n",
        )
        for timestamp in invalid:
            changed = json.loads(json.dumps(raw))
            changed["prepared_at"] = timestamp
            changed["updated_at"] = timestamp
            with self.assertRaises(f.JournalError, msg=timestamp):
                f.InflightJournal.from_mapping(changed)
        with self.assertRaises(f.JournalError):
            f.transition(prepared(), "call_started", T0,
                         provider_request_id=f.derive_provider_request_id(identity()))
        nonmonotonic = returned().to_dict()
        nonmonotonic["provider_returned_at"] = T0
        nonmonotonic["updated_at"] = T0
        with self.assertRaises(f.JournalError):
            f.InflightJournal.from_mapping(nonmonotonic)

    def test_closed_dict_and_duplicate_json_boundaries(self):
        raw = prepared().to_dict()
        for changed in (
            {**raw, "extra": 1},
            {key: value for key, value in raw.items() if key != "state"},
            {**raw, "state": 1},
        ):
            with self.assertRaises(f.JournalError):
                f.InflightJournal.from_mapping(changed)
        serialized = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        self.assertEqual(prepared(), f.InflightJournal.from_json(serialized))
        duplicate_top = serialized.replace(
            '"schema_version":3', '"schema_version":3,"schema_version":3', 1
        )
        with self.assertRaisesRegex(f.JournalError, "DUPLICATE_JSON_KEY"):
            f.InflightJournal.from_json(duplicate_top)
        duplicate_nested = serialized.replace(
            '"attempt_number":1', '"attempt_number":1,"attempt_number":1', 1
        )
        with self.assertRaisesRegex(f.JournalError, "DUPLICATE_JSON_KEY"):
            f.InflightJournal.from_json(duplicate_nested)


class SuccessRecoveryAndPersistenceTests(unittest.TestCase):
    def test_authoritative_success_is_closed_complete_and_individually_bound(self):
        valid = success()
        self.assertEqual(valid, f.validate_authoritative_success(valid.to_dict(), identity()))
        raw = valid.to_dict()
        serialized = json.dumps(raw, sort_keys=True, separators=(",", ":"))
        self.assertEqual(valid, f.AuthoritativeSuccess.from_json(serialized))
        duplicate = serialized.replace(
            '"provider_response_id":"response_1"',
            '"provider_response_id":"response_1","provider_response_id":"response_1"',
            1,
        )
        with self.assertRaisesRegex(f.JournalError, "DUPLICATE_JSON_KEY"):
            f.AuthoritativeSuccess.from_json(duplicate)
        with self.assertRaises(f.JournalError):
            f.validate_authoritative_success(valid)
        malformed = [
            {key: value for key, value in raw.items() if key != "response_sha256"},
            {**raw, "extra": 1},
            {**raw, "execution_status": "other"},
            {**raw, "provider_request_id": "foreign_call"},
            {**raw, "provider_response_id": raw["provider_request_id"]},
            {**raw, "provider_response_sha256": "BAD"},
            {**raw, "response_sha256": "BAD"},
            {**raw, "call_started_at": T3},
        ]
        identity_substitutions = (
            ("request_id", B),
            ("execution_order", 2),
            ("execution_unit_id", B),
            ("formal_system_id", "v2_without_context_management"),
            ("resolved_runtime_system_id", "v2_without_context_management"),
            ("payload_sha256", A),
            ("resolved_payload_sha256", A),
            ("transport_contract_id", "other_transport"),
            ("transport_contract_sha256", A),
            ("generation_contract_id", "other_generation"),
            ("generation_contract_sha256", A),
            ("resource_identity_sha256", A),
            ("attempt_id", "attempt_" + A),
            ("attempt_number", True),
        )
        for key, value in identity_substitutions:
            changed = json.loads(json.dumps(raw))
            changed["identity"][key] = value
            malformed.append(changed)
        for changed in malformed:
            with self.assertRaises(f.JournalError):
                f.validate_authoritative_success(changed, identity())

    def test_complete_expected_is_mandatory_before_every_recovery_decision(self):
        for expected in (
            None,
            {},
            {"malformed": True},
            {**identity().to_dict(), "extra": True},
            {key: value for key, value in identity().to_dict().items()
             if key != "request_id"},
        ):
            with self.assertRaises(f.JournalError, msg=repr(expected)[:80]):
                f.recovery_decision(None, expected=expected)
        self.assertEqual("begin", f.recovery_decision(None, expected=identity()))

    def test_matching_success_precedes_every_state_and_is_idempotent(self):
        valid_success = success()
        for record in [None, *state_family()]:
            first = f.recovery_decision(
                record,
                authoritative_success=valid_success,
                expected=identity(),
            )
            second = f.recovery_decision(
                record,
                authoritative_success=valid_success,
                expected=identity(),
            )
            self.assertEqual(first, second)
            if record is None:
                self.assertEqual("authoritative_success", first)
            elif record.state == "committed":
                self.assertEqual("confirmed", first)
            else:
                self.assertEqual("reconcile_committed", first)

    def test_coherent_identity_conflicts_normalize_only_during_reconciliation(self):
        expected_identity = identity()
        foreign_request_identity = identity(request_id=B, execution_order=2)
        foreign_attempt_identity = identity(attempt=2)
        candidates = (
            ("request", foreign_request_identity, success(foreign_request_identity)),
            ("attempt", foreign_attempt_identity, success(foreign_attempt_identity)),
        )
        for name, foreign_identity, candidate in candidates:
            self.assertEqual(
                candidate,
                f.validate_authoritative_success(candidate, foreign_identity),
                name,
            )
            with self.assertRaises(f.JournalError) as raised:
                f.validate_authoritative_success(candidate, expected_identity)
            self.assertEqual("JOURNAL_IDENTITY_MISMATCH", raised.exception.category, name)

            record = returned()
            retained = record.to_dict()
            with self.assertRaises(f.JournalError) as raised:
                f.reconcile(record, candidate, expected_identity)
            self.assertEqual("JOURNAL_EVIDENCE_CONFLICT", raised.exception.category, name)
            self.assertEqual(retained, record.to_dict(), name)

            provider_calls = []
            recovery_record = returned()
            retained = recovery_record.to_dict()
            try:
                decision = f.recovery_decision(
                    recovery_record,
                    authoritative_success=candidate,
                    expected=expected_identity,
                )
            except f.JournalError as exc:
                self.assertEqual("JOURNAL_EVIDENCE_CONFLICT", exc.category, name)
            else:
                if decision in {"begin", "continue_before_provider", "retry"}:
                    provider_calls.append("provider")
                self.fail(f"coherent {name} conflict unexpectedly returned {decision!r}")
            self.assertEqual([], provider_calls, name)
            self.assertEqual(retained, recovery_record.to_dict(), name)

    def test_malformed_and_internally_inconsistent_success_preserve_validation_categories(self):
        malformed = success().to_dict()
        malformed["provider_response_id"] = 0
        with self.assertRaises(f.JournalError) as raised:
            f.reconcile(returned(), malformed, identity())
        self.assertEqual("JOURNAL_SUCCESS_INVALID", raised.exception.category)

        inconsistent = success(identity(attempt=2)).to_dict()
        inconsistent["identity"] = identity().to_dict()
        with self.assertRaises(f.JournalError) as raised:
            f.reconcile(returned(), inconsistent, identity())
        self.assertEqual("JOURNAL_SUCCESS_INVALID", raised.exception.category)

        with self.assertRaises(f.JournalError):
            f.recovery_decision(
                None, authoritative_success=success(), expected={"malformed": True}
            )

    def test_matching_success_prevents_provider_invocation(self):
        calls = []

        def guarded_recovery(record, authoritative, expected):
            decision = f.recovery_decision(
                record,
                authoritative_success=authoritative,
                expected=expected,
            )
            if decision in {"begin", "continue_before_provider", "retry"}:
                calls.append("provider")
            return decision

        for record in [None, *state_family()]:
            guarded_recovery(record, success(), identity())
        self.assertEqual([], calls)

    def test_exact_committed_reconciliation_and_foreign_evidence_rejection(self):
        provider_returned = returned()
        committed = f.reconcile(provider_returned, success(), identity())
        self.assertEqual("committed", committed.state)
        self.assertEqual(committed, f.reconcile(committed, success(), identity()))
        for key, value in (
            ("provider_response_id", "response_foreign"),
            ("provider_response_sha256", A),
            ("response_sha256", A),
            ("committed_at", "2026-07-23T10:00:05Z"),
        ):
            changed = success().to_dict()
            changed[key] = value
            if key == "committed_at":
                altered = f.AuthoritativeSuccess.from_mapping(changed)
                with self.assertRaises(f.JournalError):
                    f.reconcile(committed, altered, identity())
            else:
                with self.assertRaises(f.JournalError):
                    f.reconcile(committed, changed, identity())

    def test_reconciliation_preserves_or_rejects_evidence_for_every_journal_state(self):
        for record in state_family():
            committed = f.reconcile(record, success(), identity())
            self.assertEqual("committed", committed.state)
            for field in (
                "provider_request_id",
                "provider_response_id",
                "provider_response_sha256",
                "response_sha256",
                "call_started_at",
                "provider_returned_at",
                "committed_at",
            ):
                existing = getattr(record, field)
                if existing is not None:
                    self.assertEqual(existing, getattr(committed, field), field)

        timestamp_conflict = success().to_dict()
        timestamp_conflict.update(
            call_started_at=T2,
            provider_returned_at=T3,
            committed_at="2026-07-23T10:00:05Z",
        )
        conflicting_call_success = f.AuthoritativeSuccess.from_mapping(timestamp_conflict)
        response_conflict = success().to_dict()
        response_conflict["provider_response_sha256"] = D
        conflicting_response_success = f.AuthoritativeSuccess.from_mapping(response_conflict)
        call_bearing = [
            record
            for record in state_family()
            if record.state
            in {
                "call_started",
                "retryable_failed",
                "terminal_failed",
                "uncertain",
            }
            and record.call_started_at is not None
        ]
        for record in call_bearing:
            with self.assertRaises(f.JournalError) as raised:
                f.recovery_decision(
                    record,
                    authoritative_success=conflicting_call_success,
                    expected=identity(),
                )
            self.assertEqual("JOURNAL_EVIDENCE_CONFLICT", raised.exception.category)
        for record in [returned(), f.reconcile(returned(), success(), identity())]:
            with self.assertRaises(f.JournalError) as raised:
                f.recovery_decision(
                    record,
                    authoritative_success=conflicting_response_success,
                    expected=identity(),
                )
            self.assertEqual("JOURNAL_EVIDENCE_CONFLICT", raised.exception.category)

    def test_persistence_roundtrip_filename_binding_and_no_response_body(self):
        with tempfile.TemporaryDirectory() as directory:
            record = prepared()
            path = f.journal_path(Path(directory), record.identity.request_id)
            f.atomic_write_journal(path, record)
            self.assertEqual(record, f.read_journal(path, identity()))
            self.assertFalse(list(Path(directory).glob("*.tmp")))
            with self.assertRaises(f.JournalError):
                f.journal_path(Path(directory), "../escape")
            with self.assertRaises(f.JournalError):
                f.atomic_write_journal(Path(directory) / "wrong.json", record)
        serialized = prepared().to_dict()
        self.assertNotIn("response_text", serialized)
        self.assertNotIn("prompt", json.dumps(serialized))


if __name__ == "__main__":
    unittest.main()
