from __future__ import annotations

import math
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import MappingProxyType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import formal_evaluation_transport as t
import formal_evaluation_inflight as f

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
T0 = "2026-07-23T10:00:00Z"
T1 = "2026-07-23T10:00:01Z"
T2 = "2026-07-23T10:00:02Z"
T4 = "2026-07-23T10:00:04Z"


def resource(config: str = "v2", *, synthetic: bool = True) -> dict:
    identity = t.formal_identity(config)
    version = "synthetic_v1" if synthetic else "production_v1"
    resource_type = "synthetic_fixture" if synthetic else "production_frozen"
    prefix = (
        f"synthetic/{identity.resource_family}"
        if synthetic
        else f"outputs/cache/{identity.resource_family}"
    )
    is_v2 = identity.resource_family == "v2_mixed"
    return {
        "schema_version": 1,
        "resource_type": resource_type,
        "logical_resource_id": f"{resource_type}_{identity.resource_family}_{version}",
        "system_config_id": config,
        "formal_system_id": identity.formal_system_id,
        "corpus_path": f"{prefix}/corpus.{('json' if synthetic else 'pkl')}",
        "embeddings_path": f"{prefix}/embeddings.npy",
        "corpus_sha256": A,
        "embeddings_sha256": B,
        "cache_family": identity.resource_family,
        "corpus_version": version,
        "row_count": 15688 if is_v2 else 15333,
        "qa_count": 15333,
        "snippet_count": 355 if is_v2 else 0,
        "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "embedding_rows": 15688 if is_v2 else 15333,
        "embedding_dimensions": 384,
        "synthetic": synthetic,
    }


def execution_identity(
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
    resource_identity = t.ProductionResourceIdentity.from_mapping(resource(system))
    authority = {
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
        attempt_id=f.derive_attempt_id(identity=authority, attempt_number=attempt),
        provider="DeepSeek",
        provider_model="deepseek-chat",
    )


def projection_control(
    identity: f.ExecutionIdentity | None = None,
    *,
    local: bool = False,
) -> dict:
    identity = identity or execution_identity()
    text = "safe output"
    if local:
        success = None
        status = "local_success"
        provider_called = False
        provider_request_id = None
        provider_response_id = None
        provider_response_sha256 = None
        call_started_at = None
        provider_returned_at = None
        committed_at = None
    else:
        success = f.AuthoritativeSuccess(
            schema_version=1,
            identity=identity,
            provider_request_id=f.derive_provider_request_id(identity),
            provider_response_id="response_1",
            provider_response_sha256=B,
            response_sha256=t.sha256_text(text),
            call_started_at=T1,
            provider_returned_at=T2,
            committed_at=T4,
            execution_status="success",
        )
        status = "success"
        provider_called = True
        provider_request_id = success.provider_request_id
        provider_response_id = success.provider_response_id
        provider_response_sha256 = success.provider_response_sha256
        call_started_at = success.call_started_at
        provider_returned_at = success.provider_returned_at
        committed_at = success.committed_at
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
        "transport_implementation_sha256": D,
        "resource_identity": identity.resource_identity.to_dict(),
        "resource_identity_sha256": identity.resource_identity_sha256,
        "attempt_id": identity.attempt_id,
        "execution_status": status,
        "status": status,
        "response_text": text,
        "response_sha256": t.sha256_text(text),
        "provider_called": provider_called,
        "provider": identity.provider,
        "provider_model": identity.provider_model,
        "provider_request_id": provider_request_id,
        "provider_response_id": provider_response_id,
        "provider_response_sha256": provider_response_sha256,
        "call_started_at": call_started_at,
        "provider_returned_at": provider_returned_at,
        "committed_at": committed_at,
        "authoritative_success": None if success is None else success.to_dict(),
        "attempt_count": identity.attempt_number,
        "route": "normal",
        "guard_category": "none",
        "requires_backend_api": False,
        "retrieval_used": True,
        "retrieved_document_ids": ["doc_1", "doc_2"],
        "retrieved_scores": [0.0, 0.5],
    }


class Fake:
    def __init__(self, response=None, error: BaseException | None = None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def good_raw(call_id: str = "call_test", *, content: str = "safe output") -> dict:
    return {
        "request_id": call_id,
        "id": "response_test",
        "choices": [{"message": {"content": content}}],
    }


def invoke(client: Fake, tracker: t.ProviderCallTracker | None = None, **kwargs):
    tracker = tracker or t.ProviderCallTracker()
    response = t.FixedGenerationProxy().invoke(
        client,
        tracker,
        [{"role": "user", "content": "synthetic"}],
        provider_request_id="call_test",
        **kwargs,
    )
    return tracker, response


class TransportAuthorityTests(unittest.TestCase):
    def test_public_registry_rebinding_and_detached_mutation_are_not_authority(self):
        original = t.FORMAL_SYSTEM_REGISTRY
        canonical_v2 = t.formal_identity("v2")
        initial_hash = t.transport_contract_sha256()
        detached = dict(original)
        detached["v2"] = t.formal_identity("single_turn")
        with self.assertRaises(t.TransportError):
            t.validate_registry(detached)
        t.FORMAL_SYSTEM_REGISTRY = {"v2": "attacker"}
        try:
            self.assertEqual(canonical_v2, t.formal_identity("v2"))
            t.validate_registry()
            self.assertEqual(initial_hash, t.transport_contract_sha256())
        finally:
            t.FORMAL_SYSTEM_REGISTRY = original
        with self.assertRaises(FrozenInstanceError):
            canonical_v2.formal_system_id = "changed"

    def test_public_identity_and_registry_values_are_detached_from_private_authority(self):
        first = t.formal_identity("v2")
        second = t.formal_identity("v2")
        first_registry = t._registry_snapshot()
        second_registry = t._registry_snapshot()
        before_generation_hash = t.generation_contract_sha256()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertEqual(first_registry["v2"], second_registry["v2"])
        self.assertIsNot(first_registry["v2"], second_registry["v2"])
        public_snapshot_value = t.FORMAL_SYSTEM_REGISTRY["v2"]
        try:
            object.__setattr__(first, "formal_system_id", "caller_changed")
            object.__setattr__(first_registry["v2"], "formal_system_id", "caller_changed")
            object.__setattr__(public_snapshot_value, "formal_system_id", "caller_changed")
            self.assertEqual("current_v2", t.formal_identity("v2").formal_system_id)
            self.assertEqual("current_v2", t._registry_snapshot()["v2"].formal_system_id)
            self.assertEqual(before_generation_hash, t.generation_contract_sha256())
            checked_identity = execution_identity()
            f.validate_execution_identity(checked_identity)
            self.assertEqual("current_v2", checked_identity.formal_system_id)
            with self.assertRaises(t.TransportError) as raised:
                t.validate_registry({**dict(t._registry_snapshot()), "v2": first})
            self.assertEqual("FORMAL_SYSTEM_REGISTRY_INVALID", raised.exception.category)
        finally:
            object.__setattr__(public_snapshot_value, "formal_system_id", "current_v2")

    def test_public_generation_and_transport_rebinding_cannot_change_invocation_or_hashes(self):
        old_generation = t.FIXED_GENERATION
        old_transport = t.TRANSPORT_CONTRACT
        old_attempts = t.MAX_ATTEMPTS
        old_safe_fields = t.SAFE_RESULT_FIELDS
        old_generation_id = t.GENERATION_CONTRACT_ID
        old_transport_id = t.TRANSPORT_CONTRACT_ID
        generation_hash = t.generation_contract_sha256()
        transport_hash = t.transport_contract_sha256()
        detached_generation = dict(t.fixed_generation_snapshot())
        detached_transport = dict(t.transport_contract_snapshot())
        detached_generation["max_tokens"] = 1
        detached_transport["maximum_attempts"] = 99
        t.FIXED_GENERATION = {"model": "attacker", "max_tokens": 1}
        t.TRANSPORT_CONTRACT = {"provider": "attacker"}
        t.MAX_ATTEMPTS = 99
        t.SAFE_RESULT_FIELDS = frozenset({"unknown"})
        t.GENERATION_CONTRACT_ID = "attacker"
        t.TRANSPORT_CONTRACT_ID = "attacker"
        try:
            client = Fake(good_raw())
            _, response = invoke(client)
            self.assertEqual("safe output", response.content)
            self.assertEqual(512, client.calls[0]["max_tokens"])
            self.assertEqual("deepseek-chat", client.calls[0]["model"])
            self.assertEqual(generation_hash, t.generation_contract_sha256())
            self.assertEqual(transport_hash, t.transport_contract_sha256())
            self.assertEqual("deepseek_fixed_generation_v1", t.generation_contract_id())
            self.assertEqual("formal_transport_v1", t.transport_contract_id())
            self.assertFalse(t.may_retry(3, "retryable"))
        finally:
            t.FIXED_GENERATION = old_generation
            t.TRANSPORT_CONTRACT = old_transport
            t.MAX_ATTEMPTS = old_attempts
            t.SAFE_RESULT_FIELDS = old_safe_fields
            t.GENERATION_CONTRACT_ID = old_generation_id
            t.TRANSPORT_CONTRACT_ID = old_transport_id

    def test_supplied_registry_is_exact(self):
        valid = dict(t.FORMAL_SYSTEM_REGISTRY)
        t.validate_registry(valid)
        mutations = []
        missing = dict(valid)
        missing.pop("v2")
        mutations.append(missing)
        extra = dict(valid)
        extra["extra"] = valid["v2"]
        mutations.append(extra)
        wrong = dict(valid)
        wrong["v2"] = t.FormalSystemIdentity(
            "v2", "evaluation/formal_qa_only_baseline_spec.json", "current_v2",
            "v2_mixed", 10, False, False
        )
        mutations.append(wrong)
        swapped = dict(valid)
        swapped["v2"], swapped["single_turn"] = swapped["single_turn"], swapped["v2"]
        mutations.append(swapped)
        for candidate in mutations:
            with self.assertRaises(t.TransportError):
                t.validate_registry(candidate)


class ResourceIdentityTests(unittest.TestCase):
    def test_synthetic_and_production_closed_schemas(self):
        synthetic = t.ProductionResourceIdentity.from_mapping(resource())
        production = t.ProductionResourceIdentity.from_mapping(resource(synthetic=False))
        self.assertNotEqual(
            t.resource_identity_sha256(synthetic), t.resource_identity_sha256(production)
        )
        self.assertIsInstance(synthetic.to_dict(), dict)
        extra = resource()
        extra["unknown"] = True
        with self.assertRaises(t.TransportError):
            t.ProductionResourceIdentity.from_mapping(extra)

    def test_path_attacks_controls_and_bounds_fail(self):
        attacks = (
            "",
            "/absolute/corpus.json",
            "../corpus.json",
            "synthetic/v2_mixed/../corpus.json",
            "synthetic/v2_mixed/./corpus.json",
            "synthetic//v2_mixed/corpus.json",
            "C:/corpus.json",
            r"\\server\share\corpus.json",
            r"synthetic\v2_mixed\corpus.json",
            "file:corpus.json",
            "https://host/corpus.json",
            "synthetic/v2_mixed/%2e%2e/corpus.json",
            "synthetic/v2_mixed/%252e%252e/corpus.json",
            "synthetic/v2_mixed/%2fetc/corpus.json",
            "synthetic/v2_mixed/%00corpus.json",
            "synthetic/v2_mixed/\x00corpus.json",
            "synthetic/v2_mixed/\ncorpus.json",
            "synthetic/v2_mixed/" + "x" * 241 + ".json",
        )
        for attack in attacks:
            bad = resource()
            bad["corpus_path"] = attack
            with self.assertRaises(t.TransportError, msg=repr(attack)):
                t.ProductionResourceIdentity.from_mapping(bad)
        for field in ("corpus_version", "logical_resource_id", "cache_family"):
            bad = resource()
            bad[field] = "x" * 129
            with self.assertRaises(t.TransportError, msg=field):
                t.ProductionResourceIdentity.from_mapping(bad)

    def test_synthetic_production_relabelling_and_system_family_swaps_fail(self):
        for field, value in (
            ("synthetic", False),
            ("resource_type", "production_frozen"),
            ("corpus_version", "production_v1"),
            ("cache_family", "v1_qa"),
            ("formal_system_id", "v2_without_context_management"),
            ("logical_resource_id", "synthetic_fixture_v1_qa_synthetic_v1"),
        ):
            bad = resource()
            bad[field] = value
            with self.assertRaises(t.TransportError, msg=field):
                t.ProductionResourceIdentity.from_mapping(bad)
        for field in ("schema_version", "row_count", "embedding_dimensions"):
            bad = resource()
            bad[field] = True
            with self.assertRaises(t.TransportError, msg=field):
                t.ProductionResourceIdentity.from_mapping(bad)


class ProviderBoundaryTests(unittest.TestCase):
    def test_multiline_message_content_is_preserved_and_hashed_canonically(self):
        prompt = (
            "Synthetic RAG instructions\n\n"
            "Rules:\n1. Use context only.\n2. Be concise.\n\n"
            "Retrieved context:\n[1] synthetic evidence"
        )
        messages = [
            {"role": "system", "content": "Synthetic formal RAG system"},
            {"role": "user", "content": prompt},
        ]
        normalized = t.validate_messages(messages)
        self.assertEqual(messages, [dict(message) for message in normalized])

        client = Fake(good_raw(content="provider-backed synthetic answer"))
        tracker = t.ProviderCallTracker()
        response = t.FixedGenerationProxy().invoke(
            client,
            tracker,
            messages,
            provider_request_id="call_test",
        )
        self.assertEqual("validated_success", tracker.state)
        self.assertEqual("provider-backed synthetic answer", response.content)
        self.assertEqual(1, len(client.calls))
        self.assertEqual(messages, client.calls[0]["messages"])

        copy_messages = [dict(message) for message in messages]
        reordered = {
            "messages": copy_messages,
            "stream": False,
            "max_tokens": 512,
            "top_p": 1.0,
            "temperature": 0.0,
            "model": "deepseek-chat",
        }
        self.assertEqual(t._canonical_sha(client.calls[0]), t._canonical_sha(reordered))
        flattened = dict(reordered)
        flattened["messages"] = [dict(copy_messages[0]), dict(copy_messages[1])]
        flattened["messages"][1]["content"] = prompt.replace("\n", " ")
        self.assertNotEqual(t._canonical_sha(reordered), t._canonical_sha(flattened))

    def test_message_content_still_rejects_nul_and_non_lf_controls(self):
        for control in ("\x00", "\x01", "\x08", "\t", "\x0b", "\x0c", "\r", "\x1f", "\x7f"):
            client = Fake(good_raw())
            with self.assertRaises(t.TransportError, msg=repr(control)) as raised:
                t.FixedGenerationProxy().invoke(
                    client,
                    t.ProviderCallTracker(),
                    [{"role": "user", "content": "before" + control + "after"}],
                    provider_request_id="call_test",
                )
            self.assertEqual("FIXED_REQUEST_INVALID", raised.exception.category)
            self.assertEqual(0, len(client.calls))

    def test_success_is_proxy_capability_bound(self):
        tracker = t.ProviderCallTracker()
        self.assertFalse(hasattr(tracker, "transition"))
        with self.assertRaises(t.TransportError):
            tracker._begin(object(), "call_test")
        with self.assertRaises(t.TransportError):
            t.ProviderSuccessReceipt(
                object(),
                provider="DeepSeek",
                model="deepseek-chat",
                provider_request_id="call_test",
                provider_response_id="response_test",
                response_sha256=A,
            )
        client = Fake(good_raw())
        tracker, response = invoke(client, tracker)
        self.assertEqual("validated_success", tracker.state)
        self.assertTrue(tracker.provider_called)
        t.validate_core_result(
            tracker, response.content, success_receipt=response.success_receipt
        )
        with self.assertRaises(t.TransportError):
            t.validate_core_result(tracker, response.content)
        with self.assertRaises(t.TransportError):
            t.validate_core_result(
                tracker, response.content + "x", success_receipt=response.success_receipt
            )
        with self.assertRaises(t.TransportError):
            invoke(client, tracker)
        self.assertEqual(1, len(client.calls))

    def test_forged_tracker_like_and_receipt_like_objects_fail(self):
        class ForgedTracker:
            state = "validated_success"
            provider_called = True

        class ForgedReceipt:
            provider = "DeepSeek"
            model = "deepseek-chat"
            provider_request_id = "call_test"
            provider_response_id = "response_test"
            response_sha256 = t.sha256_text("safe")

        with self.assertRaises(t.TransportError):
            t.validate_core_result(
                ForgedTracker(), "safe", success_receipt=ForgedReceipt()
            )
        local = t.ProviderCallTracker()
        t.validate_core_result(local, "guarded local response", local_result=True)
        self.assertFalse(local.provider_called)
        local.record_pre_send_failure()
        self.assertEqual("pre_send_failure", local.state)
        self.assertFalse(local.provider_called)
        with self.assertRaises(t.TransportError):
            t.validate_core_result(local, "fallback", local_result=True)

    def test_every_pre_call_rejection_has_zero_calls(self):
        cases = [
            ({"provider_request_id": value}, [{"role": "user", "content": "synthetic"}])
            for value in (None, "", " ", False, 0, [], {}, "x\nx", "x" * 129)
        ]
        cases.extend(
            [
                ({"provider_request_id": "call_test"}, []),
                ({"provider_request_id": "call_test"}, [{"role": "bad", "content": "x"}]),
                (
                    {"provider_request_id": "call_test"},
                    [{"role": "user", "content": "x\x00"}],
                ),
            ]
        )
        for kwargs, messages in cases:
            client = Fake(good_raw())
            with self.assertRaises(t.TransportError, msg=repr((kwargs, messages))):
                t.FixedGenerationProxy().invoke(
                    client, t.ProviderCallTracker(), messages, **kwargs
                )
            self.assertEqual(0, len(client.calls))
        client = Fake(good_raw())
        with self.assertRaises(t.TransportError):
            t.FixedGenerationProxy().invoke(
                client,
                t.ProviderCallTracker(),
                [{"role": "user", "content": "synthetic"}],
                provider_request_id="call_test",
                temperature=1,
            )
        self.assertEqual(0, len(client.calls))

    def test_malformed_provider_metadata_never_succeeds(self):
        malformed_ids = (
            None,
            "",
            " ",
            False,
            0,
            [],
            {},
            "bad\nid",
            "x" * 129,
        )
        for field in ("request_id", "id"):
            for bad_id in malformed_ids:
                raw = good_raw()
                raw[field] = bad_id
                client = Fake(raw)
                tracker = t.ProviderCallTracker()
                with self.assertRaises(t.TransportError, msg=f"{field}={bad_id!r}"):
                    invoke(client, tracker)
                self.assertEqual(1, len(client.calls))
                self.assertTrue(tracker.provider_called)
                self.assertEqual("post_call_terminal_failure", tracker.state)
        raw = good_raw()
        raw["request_id"] = "foreign_call"
        with self.assertRaises(t.TransportError):
            invoke(Fake(raw))
        raw = good_raw()
        raw["id"] = "call_test"
        with self.assertRaises(t.TransportError):
            invoke(Fake(raw))

    def test_call_failure_semantics_are_not_terminal_truthiness(self):
        uncertain_client = Fake(error=TimeoutError("synthetic"))
        uncertain = t.ProviderCallTracker()
        with self.assertRaises(t.TransportError):
            invoke(uncertain_client, uncertain)
        self.assertTrue(uncertain.provider_called)
        self.assertEqual("uncertain_post_call_failure", uncertain.state)
        unknown_client = Fake(error=RuntimeError("synthetic unknown"))
        unknown = t.ProviderCallTracker()
        with self.assertRaises(t.TransportError):
            invoke(unknown_client, unknown)
        self.assertTrue(unknown.provider_called)
        self.assertEqual("uncertain_post_call_failure", unknown.state)

        class TooManyRequests(RuntimeError):
            status_code = 429

        retry_client = Fake(error=TooManyRequests("synthetic"))
        retry = t.ProviderCallTracker()
        with self.assertRaises(t.TransportError):
            invoke(retry_client, retry)
        self.assertTrue(retry.provider_called)
        self.assertEqual("explicit_retryable_failure", retry.state)


class ProjectionAndConfigTests(unittest.TestCase):
    def valid_projection(self) -> dict:
        return projection_control()

    def test_projection_is_closed_complete_bounded_and_detached(self):
        source = self.valid_projection()
        projected = t.project_formal_result(source)
        self.assertIsInstance(projected["retrieved_document_ids"], tuple)
        self.assertIsInstance(projected["retrieved_scores"], tuple)
        source["retrieved_document_ids"].append("doc_3")
        source["retrieved_scores"][0] = 99
        self.assertEqual(("doc_1", "doc_2"), projected["retrieved_document_ids"])
        self.assertEqual((0.0, 0.5), projected["retrieved_scores"])
        for bad in (
            {**self.valid_projection(), "unknown": {"unsafe": True}},
            {**self.valid_projection(), "messages": []},
            {},
            {"request_id": "request_1"},
        ):
            with self.assertRaises(t.TransportError):
                t.project_formal_result(bad)
        for attempt in (0, 4, True, "1", 1.0):
            bad = self.valid_projection()
            bad["attempt_count"] = attempt
            with self.assertRaises(t.TransportError, msg=repr(attempt)):
                t.project_formal_result(bad)
        for response in ("bad\ntext", "bad\x00text", "x" * (t.MAX_RESPONSE_TEXT_LENGTH + 1)):
            bad = self.valid_projection()
            bad["response_text"] = response
            bad["response_sha256"] = t.sha256_text(response)
            with self.assertRaises(t.TransportError, msg=repr(response[:20])):
                t.project_formal_result(bad)

    def test_every_complete_success_provenance_field_is_mandatory_and_validated(self):
        for key in t._REQUIRED_RESULT_FIELDS:
            bad = self.valid_projection()
            bad.pop(key)
            with self.assertRaises(t.TransportError, msg=key):
                t.project_formal_result(bad)
        semantic_mutations = (
            ("plan_fingerprint", A),
            ("execution_unit_id", "not-a-hash"),
            ("execution_order", True),
            ("case_id", None),
            ("resolved_runtime_system_id", "foreign_runtime"),
            ("payload_sha256", "not-a-hash"),
            ("resolved_payload_sha256", "not-a-hash"),
            ("transport_contract_id", "foreign_transport"),
            ("transport_contract_sha256", A),
            ("generation_contract_id", "foreign_generation"),
            ("generation_contract_sha256", A),
            ("transport_implementation_sha256", "not-a-hash"),
            ("resource_identity_sha256", A),
            ("attempt_id", "attempt_not-a-hash"),
            ("provider", "Other"),
            ("provider_model", "other-model"),
            ("provider_request_id", "bad\nrequest"),
            ("provider_response_id", "bad\nresponse"),
            ("provider_response_sha256", "not-a-hash"),
        )
        for key, value in semantic_mutations:
            bad = self.valid_projection()
            bad[key] = value
            with self.assertRaises(t.TransportError, msg=key):
                t.project_formal_result(bad)
        bad_resource = self.valid_projection()
        bad_resource["resource_identity"] = {"unsafe": "nested"}
        with self.assertRaises(t.TransportError):
            t.project_formal_result(bad_resource)

    def test_projection_scalar_and_provider_relationships(self):
        mutations = (
            ("retrieved_scores", [math.inf, 0.1]),
            ("retrieved_scores", [math.nan, 0.1]),
            ("retrieved_document_ids", [{"text": "secret"}]),
            ("provider_request_id", 0),
            ("response_sha256", A),
            ("formal_system_id", "v2_without_context_management"),
            ("turn_index", True),
        )
        for key, value in mutations:
            bad = self.valid_projection()
            bad[key] = value
            with self.assertRaises(t.TransportError, msg=key):
                t.project_formal_result(bad)
        missing_call = self.valid_projection()
        missing_call.pop("provider_request_id")
        with self.assertRaises(t.TransportError):
            t.project_formal_result(missing_call)
        local = self.valid_projection()
        local.update(
            status="local_success",
            execution_status="local_success",
            provider_called=False,
            provider_request_id=None,
            provider_response_id=None,
            provider_response_sha256=None,
            call_started_at=None,
            provider_returned_at=None,
            committed_at=None,
            authoritative_success=None,
        )
        self.assertEqual("local_success", t.project_formal_result(local)["status"])

    def test_projection_reconstructs_connected_execution_attempt_and_provider_authority(self):
        source = self.valid_projection()
        self.assertEqual("success", t.project_formal_result(source)["status"])
        for key, value in (
            ("request_id", B),
            ("execution_unit_id", B),
            ("attempt_id", "attempt_" + B),
            ("provider_request_id", "call_alternate"),
            ("attempt_count", 2),
        ):
            changed = self.valid_projection()
            changed[key] = value
            with self.assertRaises(t.TransportError) as raised:
                t.project_formal_result(changed)
            self.assertEqual("FORMAL_RESULT_PROVENANCE_INVALID", raised.exception.category, key)
        alternate_identity = execution_identity(request_id=B, execution_order=2)
        alternate = projection_control(alternate_identity)
        self.assertEqual("success", t.project_formal_result(alternate)["status"])
        self.assertNotEqual(source["attempt_id"], alternate["attempt_id"])
        self.assertNotEqual(source["provider_request_id"], alternate["provider_request_id"])
        self.assertNotEqual(source["authoritative_success"]["identity"], alternate["authoritative_success"]["identity"])

    def test_projection_binds_authoritative_success_lifecycle_and_response_evidence(self):
        for key, value in (
            ("provider_response_id", "response_alternate"),
            ("provider_response_sha256", D),
            ("response_text", "different safe output"),
            ("call_started_at", T0),
            ("provider_returned_at", T4),
            ("committed_at", "2026-07-23T10:00:05Z"),
            ("execution_status", "local_success"),
        ):
            changed = self.valid_projection()
            changed[key] = value
            if key == "response_text":
                changed["response_sha256"] = t.sha256_text(value)
            with self.assertRaises(t.TransportError) as raised:
                t.project_formal_result(changed)
            self.assertEqual("FORMAL_RESULT_PROVENANCE_INVALID", raised.exception.category, key)
        for key, value in (("provider", "Other"), ("provider_model", "other-model")):
            changed = self.valid_projection()
            changed[key] = value
            with self.assertRaises(t.TransportError) as raised:
                t.project_formal_result(changed)
            self.assertEqual("FORMAL_RESULT_PROVENANCE_INVALID", raised.exception.category, key)

    def test_local_projection_requires_full_authority_and_rejects_each_provider_evidence_field(self):
        local = projection_control(local=True)
        self.assertEqual("local_success", t.project_formal_result(local)["status"])
        for key in t._REQUIRED_RESULT_FIELDS:
            changed = projection_control(local=True)
            changed.pop(key)
            with self.assertRaises(t.TransportError, msg=key):
                t.project_formal_result(changed)
        for key, value in (
            ("provider_called", True),
            ("provider_request_id", "call_alternate"),
            ("provider_response_id", "response_alternate"),
            ("provider_response_sha256", D),
            ("call_started_at", T1),
            ("provider_returned_at", T2),
            ("committed_at", T4),
            ("authoritative_success", self.valid_projection()["authoritative_success"]),
        ):
            changed = projection_control(local=True)
            changed[key] = value
            with self.assertRaises(t.TransportError) as raised:
                t.project_formal_result(changed)
            self.assertEqual("LOCAL_PROVIDER_EVIDENCE_INVALID", raised.exception.category, key)

    def test_projection_enforces_rq_checkpoint_matrix_and_closed_nested_success(self):
        for rq, system, turn in (
            ("RQ1", "qa_only_reconstructed_baseline", 1),
            ("RQ2", "v2", 1),
            ("RQ3", "single_turn", 1),
            ("RQ3", "context_aware", 1),
            ("RQ3", "context_aware", 2),
        ):
            control = projection_control(execution_identity(rq=rq, system=system, turn=turn))
            self.assertEqual("success", t.project_formal_result(control)["status"])
        bad_checkpoint = projection_control(execution_identity(rq="RQ3", system="context_aware", turn=2))
        bad_checkpoint["input_checkpoint_id"] = "checkpoint_" + A
        with self.assertRaises(t.TransportError) as raised:
            t.project_formal_result(bad_checkpoint)
        self.assertEqual("FORMAL_RESULT_PROVENANCE_INVALID", raised.exception.category)
        nested = self.valid_projection()
        nested["authoritative_success"]["unknown"] = True
        with self.assertRaises(t.TransportError) as raised:
            t.project_formal_result(nested)
        self.assertEqual("FORMAL_RESULT_PROVENANCE_INVALID", raised.exception.category)

    def test_projection_attempts_remain_exact_and_distinct(self):
        accepted = [projection_control(execution_identity(attempt=number)) for number in (1, 2, 3)]
        for control in accepted:
            self.assertEqual("success", t.project_formal_result(control)["status"])
        self.assertEqual(3, len({control["attempt_id"] for control in accepted}))
        self.assertEqual(3, len({control["provider_request_id"] for control in accepted}))
        for value in (0, 4, True, "1", 1.0, -1, 99):
            changed = self.valid_projection()
            changed["attempt_count"] = value
            with self.assertRaises(t.TransportError) as raised:
                t.project_formal_result(changed)
            self.assertEqual("FORMAL_RESULT_PROVENANCE_INVALID", raised.exception.category, repr(value))

    def test_config_is_strict_and_redacted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic_config"
            secret = "synthetic-secret"
            path.write_text(
                f"DEEPSEEK_API_KEY={secret}\n"
                "DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
                "DEEPSEEK_MODEL=deepseek-chat\n",
                encoding="utf-8",
            )
            config = t.parse_deepseek_config(str(path))
            self.assertNotIn(secret, repr(config))
            path.write_text(
                "DEEPSEEK_API_KEY=x\n"
                "DEEPSEEK_BASE_URL=https://api.deepseek.com\n"
                "DEEPSEEK_MODEL=wrong\n",
                encoding="utf-8",
            )
            with self.assertRaises(t.TransportError):
                t.parse_deepseek_config(str(path))

    def test_retry_taxonomy_and_attempt_ceiling(self):
        self.assertEqual("retryable", t.retry_classification(status_code=429))
        self.assertEqual("retryable", t.retry_classification(status_code=500))
        for category in (
            "timeout",
            "read_timeout",
            "connection_reset",
            "broken_pipe",
            "connection_error",
        ):
            self.assertEqual("uncertain", t.retry_classification(category=category))
        self.assertTrue(t.may_retry(2, "retryable"))
        for attempt in (0, 3, 4, True, "2", 2.0):
            self.assertFalse(t.may_retry(attempt, "retryable"))


if __name__ == "__main__":
    unittest.main()
