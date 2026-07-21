"""Offline tests for formal-evaluation generation and context adapters."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "outputs"))
sys.path.insert(0, str(ROOT / "scripts"))
import rag_answer_demo as rag  # noqa: E402
from formal_evaluation_runtime import (ContextMode, EVALUATION_GENERATION_CONFIG,
    MAX_SNAPSHOT_BYTES, MAX_SNAPSHOT_TEXT_BYTES, SnapshotValidationError, restore_runtime_snapshot,
    run_dialogue, run_dialogue_checkpointed)  # noqa: E402


class _Completions:
    def __init__(self): self.payloads = []
    def create(self, **kwargs):
        self.payloads.append(kwargs)
        return type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "ok"})()})()]})()


class _Client:
    def __init__(self): self.chat = type("Chat", (), {"completions": _Completions()})()


class GenerationConfigTests(unittest.TestCase):
    def setUp(self):
        self.client = _Client()
        self.config = rag.LLMConfig(api_key="redacted", base_url="https://api.deepseek.com", model="deepseek-chat", client=self.client)

    def test_default_payload_is_legacy_compatible(self):
        rag.call_deepseek_api("prompt", self.config)
        payload = self.client.chat.completions.payloads[-1]
        self.assertEqual(0.2, payload["temperature"])
        self.assertNotIn("top_p", payload); self.assertNotIn("max_tokens", payload); self.assertNotIn("stream", payload)
        self.assertNotIn("thinking", payload); self.assertEqual("deepseek-chat", payload["model"])

    def test_evaluation_payload_is_explicit_and_prompt_unchanged(self):
        rag.call_deepseek_api("same prompt", self.config, EVALUATION_GENERATION_CONFIG)
        payload = self.client.chat.completions.payloads[-1]
        self.assertEqual(0.0, payload["temperature"]); self.assertEqual(1.0, payload["top_p"])
        self.assertEqual(512, payload["max_tokens"]); self.assertFalse(payload["stream"])
        self.assertEqual("deepseek-chat", payload["model"]); self.assertNotIn("thinking", payload)
        self.assertEqual("same prompt", payload["messages"][1]["content"])
        self.assertNotIn("redacted", repr(payload))


class ContextIsolationTests(unittest.TestCase):
    def _fake(self, calls):
        def fake(question, *args, **kwargs):
            calls.append((question, kwargs))
            return {"final_answer": "answer:" + question, "conversation_state": {"last_user_query": question, "state_turn_count": 1}}
        return fake

    def _run(self, mode, calls):
        return run_dialogue(["first", "second"], mode=mode, corpus=object(), embeddings=object(), embedding_model=object(), top_k=10, cosine_similarity=object(), low_confidence_threshold=.55, llm_config=rag.LLMConfig("", "", "deepseek-chat", None), run_query=self._fake(calls))

    def test_single_turn_clears_all_context(self):
        calls=[]; self._run(ContextMode.SINGLE_TURN, calls)
        self.assertIsNot(calls[0][1]["conversation_state"], calls[1][1]["conversation_state"])
        for _, kwargs in calls:
            self.assertIsNone(kwargs["previous_user_query"]); self.assertIsNone(kwargs["previous_assistant_answer"])
            self.assertIs(kwargs["generation_config"], EVALUATION_GENERATION_CONFIG)

    def test_context_aware_reuses_context_and_dialogues_are_isolated(self):
        calls=[]; self._run(ContextMode.CONTEXT_AWARE, calls); self._run(ContextMode.CONTEXT_AWARE, calls)
        self.assertIsNot(calls[0][1]["conversation_state"], calls[1][1]["conversation_state"])
        self.assertEqual("first", calls[1][1]["previous_user_query"]); self.assertEqual("answer:first", calls[1][1]["previous_assistant_answer"])
        self.assertIsNot(calls[1][1]["conversation_state"], calls[2][1]["conversation_state"])
        self.assertIsNone(calls[2][1]["previous_user_query"]); self.assertIsNone(calls[2][1]["previous_assistant_answer"])
        self.assertIs(calls[0][1]["generation_config"], calls[1][1]["generation_config"])

    def test_snapshot_restores_all_state_and_previous_texts(self):
        calls=[]; incoming=[]
        def fake(question, *args, **kwargs):
            incoming.append(kwargs["conversation_state"].to_dict())
            calls.append((question, kwargs))
            return {"final_answer": "answer:" + question,
                    "conversation_state": {"last_user_query": question, "state_turn_count": 1}}
        first=run_dialogue_checkpointed(["backend"], mode=ContextMode.CONTEXT_AWARE,
            corpus=object(), embeddings=object(), embedding_model=object(), top_k=10,
            cosine_similarity=object(), low_confidence_threshold=.55,
            llm_config=rag.LLMConfig("", "", "deepseek-chat", None), run_query=fake)
        resumed=run_dialogue_checkpointed(["follow-up"], mode=ContextMode.CONTEXT_AWARE,
            initial_state_snapshot=first.final_snapshot.to_dict(), corpus=object(), embeddings=object(),
            embedding_model=object(), top_k=10, cosine_similarity=object(), low_confidence_threshold=.55,
            llm_config=rag.LLMConfig("", "", "deepseek-chat", None), run_query=fake)
        self.assertEqual("backend", calls[-1][1]["previous_user_query"])
        self.assertEqual("answer:backend", calls[-1][1]["previous_assistant_answer"])
        self.assertEqual(first.final_snapshot.conversation_state.to_dict(), incoming[-1])
        self.assertEqual(2, resumed.final_snapshot.completed_turn_index)

    def test_snapshot_validation_fails_closed(self):
        state=rag.ConversationState().to_dict()
        good={"schema_version":1,"completed_turn_index":1,"conversation_state":state,
              "previous_user_text":"","previous_assistant_text":""}
        for mutate in (
            lambda x: x.update(schema_version=2),
            lambda x: x.update(schema_version=True),
            lambda x: x.update(schema_version=False),
            lambda x: x.update(extra=True),
            lambda x: x.pop("previous_user_text"),
            lambda x: x["conversation_state"].update(state_turn_count=True),
            lambda x: x["conversation_state"].update(state_confidence=float("nan")),
            lambda x: x["conversation_state"].update(last_user_query="x" * (MAX_SNAPSHOT_TEXT_BYTES + 1)),
            lambda x: x["conversation_state"].update(unknown="x"),
        ):
            import copy
            value=copy.deepcopy(good); mutate(value)
            with self.assertRaises(SnapshotValidationError): restore_runtime_snapshot(value)
        self.assertEqual(1,restore_runtime_snapshot(good).schema_version)

    def test_snapshot_is_deeply_immutable_and_to_dict_is_detached(self):
        good={"schema_version":1,"completed_turn_index":1,"conversation_state":rag.ConversationState().to_dict(),
              "previous_user_text":"","previous_assistant_text":""}
        snapshot=restore_runtime_snapshot(good)
        with self.assertRaises(FrozenInstanceError): snapshot.conversation_state.current_topic="changed"
        detached=snapshot.to_dict(); detached["conversation_state"]["current_topic"]="changed"
        self.assertNotEqual("changed",snapshot.conversation_state.current_topic)

    def test_snapshot_total_size_boundary_and_utf8_bytes(self):
        def value(fill):
            state=rag.ConversationState().to_dict()
            for name,text in fill.items(): state[name]=text
            return {"schema_version":1,"completed_turn_index":1,"conversation_state":state,
                    "previous_user_text":"","previous_assistant_text":""}
        within=value({name:"x" * 7000 for name in (
            "current_topic","query_type","risk_type","last_safe_answer_type",
            "last_retrieval_query","last_contextual_query","last_successful_contextual_query")})
        self.assertLessEqual(len(json.dumps(within,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")),MAX_SNAPSHOT_BYTES)
        self.assertEqual(1,restore_runtime_snapshot(within).completed_turn_index)
        combined=value({name:"x" * 9000 for name in (
            "current_topic","query_type","risk_type","last_safe_answer_type",
            "last_retrieval_query","last_contextual_query","last_successful_contextual_query","last_assistant_answer")})
        combined["previous_assistant_text"]=combined["conversation_state"]["last_assistant_answer"]
        self.assertTrue(all(len(text.encode("utf-8"))<=MAX_SNAPSHOT_TEXT_BYTES for text in combined["conversation_state"].values() if isinstance(text,str)))
        with self.assertRaises(SnapshotValidationError): restore_runtime_snapshot(combined)
        multibyte=value({"current_topic":"中" * 16000,"query_type":"文" * 6000})
        self.assertLess(len(json.dumps(multibyte,ensure_ascii=False,sort_keys=True,separators=(",",":"))),MAX_SNAPSHOT_BYTES)
        encoded=json.dumps(multibyte,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
        self.assertGreater(len(encoded),MAX_SNAPSHOT_BYTES)
        self.assertEqual(hashlib.sha256(encoded).hexdigest(),hashlib.sha256(bytes(encoded)).hexdigest())
        with self.assertRaises(SnapshotValidationError): restore_runtime_snapshot(multibyte)

    def test_snapshot_single_text_limit_is_utf8_byte_bounded(self):
        def snapshot(field, text):
            state = rag.ConversationState().to_dict()
            if field in state:
                state[field] = text
            value = {"schema_version": 1, "completed_turn_index": 1,
                     "conversation_state": state, "previous_user_text": "",
                     "previous_assistant_text": ""}
            if field in ("previous_user_text", "previous_assistant_text"):
                value[field] = text
            return value

        over_multibyte = "中" * 5462
        self.assertLess(len(over_multibyte), MAX_SNAPSHOT_TEXT_BYTES)
        self.assertEqual(16_386, len(over_multibyte.encode("utf-8")))
        candidate = snapshot("previous_user_text", over_multibyte)
        total = len(json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode("utf-8"))
        self.assertLess(total, MAX_SNAPSHOT_BYTES)
        with self.assertRaisesRegex(SnapshotValidationError, "UTF-8 bytes"):
            restore_runtime_snapshot(candidate)

        for byte_count, accepted in ((16_384, True), (16_385, False)):
            candidate = snapshot("current_topic", "a" * byte_count)
            self.assertLess(len(json.dumps(candidate, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8")), MAX_SNAPSHOT_BYTES)
            if accepted:
                self.assertEqual(1, restore_runtime_snapshot(candidate).schema_version)
            else:
                with self.assertRaisesRegex(SnapshotValidationError, "UTF-8 bytes"):
                    restore_runtime_snapshot(candidate)

        for text, accepted in (("中" * 5461, True), ("中" * 5461 + "a", True),
                               ("中" * 5461 + "aa", False)):
            self.assertIn(len(text.encode("utf-8")), (16_383, 16_384, 16_385))
            candidate = snapshot("query_type", text)
            if accepted:
                self.assertEqual(1, restore_runtime_snapshot(candidate).schema_version)
            else:
                with self.assertRaisesRegex(SnapshotValidationError, "UTF-8 bytes"):
                    restore_runtime_snapshot(candidate)

        text_fields = ("previous_user_text", "previous_assistant_text", "current_topic",
                       "query_type", "risk_type", "last_safe_answer_type", "last_user_query",
                       "last_assistant_answer", "last_retrieval_query", "last_contextual_query",
                       "last_successful_contextual_query")
        for field in text_fields:
            with self.subTest(field=field), self.assertRaisesRegex(SnapshotValidationError, "UTF-8 bytes"):
                restore_runtime_snapshot(snapshot(field, over_multibyte))

    def test_single_turn_rejects_snapshot_and_isolates_turns(self):
        snapshot={"schema_version":1,"completed_turn_index":0,"conversation_state":rag.ConversationState().to_dict(),
                  "previous_user_text":"","previous_assistant_text":""}
        with self.assertRaises(SnapshotValidationError):
            run_dialogue_checkpointed([], mode=ContextMode.SINGLE_TURN, initial_state_snapshot=snapshot,
                corpus=object(), embeddings=object(), embedding_model=object(), top_k=10,
                cosine_similarity=object(), low_confidence_threshold=.55,
                llm_config=rag.LLMConfig("", "", "deepseek-chat", None))

    def test_backend_financial_aftersales_and_reset_continuous_equals_resume(self):
        class Machine:
            def __init__(self,scenario): self.scenario=scenario; self.calls=[]
            def __call__(self,question,*args,**kwargs):
                state=kwargs["conversation_state"]
                self.calls.append({"question":question,"state":state.to_dict(),"previous_user":kwargs["previous_user_query"],"previous_answer":kwargs["previous_assistant_answer"]})
                if question=="turn-one":
                    topic,risk,query_type,backend={
                        "backend":("logistics","backend_operation","tracking",True),
                        "financial":("refund","financial","refund_commitment",False),
                        "aftersales":("aftersales","aftersales_operation","return_request",False),
                        "reset":("logistics","backend_operation","tracking",True),
                    }[self.scenario]
                    state.current_topic=topic; state.risk_type=risk; state.query_type=query_type
                    state.requires_backend_api=backend; state.should_reset=False; state.last_safe_answer_type="bounded"
                    state.last_retrieval_query="retrieve:"+topic; state.last_contextual_query="context:"+topic
                    state.last_successful_contextual_query="success:"+topic; state.state_confidence=.91
                    decision="initial_"+self.scenario
                else:
                    history_ok=kwargs["previous_user_query"]=="turn-one" and kwargs["previous_assistant_answer"]=="answer:initial_"+self.scenario
                    if self.scenario=="backend": decision="inherit_backend" if state.requires_backend_api and history_ok else "lost_backend"
                    elif self.scenario=="financial": decision="inherit_financial" if state.risk_type=="financial" and history_ok else "lost_financial"
                    elif self.scenario=="aftersales": decision="inherit_aftersales" if state.risk_type=="aftersales_operation" and history_ok else "lost_aftersales"
                    else:
                        decision="reset_new_topic" if state.current_topic=="logistics" and history_ok else "lost_reset"
                        state.current_topic="product"; state.query_type="normal"; state.risk_type="none"
                        state.requires_backend_api=False; state.should_reset=True; state.last_safe_answer_type="none"
                        state.last_successful_contextual_query=""
                    state.last_contextual_query="context:turn-two"; state.last_retrieval_query="retrieve:turn-two"
                    state.state_confidence=.97
                state.state_turn_count+=1; state.updated_at_turn+=1
                state.last_user_query=question; answer="answer:"+decision; state.last_assistant_answer=answer
                return {"final_answer":answer,"conversation_state":state.to_dict(),"route_decision":decision,
                        "contextual_query":state.last_contextual_query,"retrieval_query":state.last_retrieval_query}
        common={"mode":ContextMode.CONTEXT_AWARE,"corpus":object(),"embeddings":object(),"embedding_model":object(),
                "top_k":10,"cosine_similarity":object(),"low_confidence_threshold":.55,
                "llm_config":rag.LLMConfig("","","deepseek-chat",None)}
        for scenario in ("backend","financial","aftersales","reset"):
            continuous_machine=Machine(scenario)
            continuous=run_dialogue_checkpointed(["turn-one","turn-two"],run_query=continuous_machine,**common)
            resumed_machine=Machine(scenario)
            first=run_dialogue_checkpointed(["turn-one"],run_query=resumed_machine,**common)
            serialized=json.loads(json.dumps(first.final_snapshot.to_dict(),ensure_ascii=False,sort_keys=True,separators=(",",":")))
            resumed=run_dialogue_checkpointed(["turn-two"],initial_state_snapshot=serialized,run_query=resumed_machine,**common)
            self.assertEqual(continuous_machine.calls[1],resumed_machine.calls[1])
            self.assertEqual(continuous.results[1],resumed.results[0])
            self.assertEqual(continuous.final_snapshot.to_dict(),resumed.final_snapshot.to_dict())
            self.assertEqual(set(rag.ConversationState().to_dict()),set(resumed.final_snapshot.conversation_state.to_dict()))
            self.assertEqual(2,resumed.final_snapshot.completed_turn_index)
            self.assertEqual(hashlib.sha256(json.dumps(continuous.results[1],sort_keys=True,separators=(",",":")).encode()).hexdigest(),
                             hashlib.sha256(json.dumps(resumed.results[0],sort_keys=True,separators=(",",":")).encode()).hexdigest())
            self.assertEqual(2,len(continuous_machine.calls)); self.assertEqual(2,len(resumed_machine.calls))
            self.assertEqual(1,sum(call["question"]=="turn-one" for call in continuous_machine.calls))
            self.assertEqual(1,sum(call["question"]=="turn-one" for call in resumed_machine.calls))


if __name__ == "__main__":
    unittest.main()
