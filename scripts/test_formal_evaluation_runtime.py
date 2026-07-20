"""Offline tests for formal-evaluation generation and context adapters."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "outputs"))
sys.path.insert(0, str(ROOT / "scripts"))
import rag_answer_demo as rag  # noqa: E402
from formal_evaluation_runtime import ContextMode, EVALUATION_GENERATION_CONFIG, run_dialogue  # noqa: E402


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
        self.assertIs(calls[0][1]["conversation_state"], calls[1][1]["conversation_state"])
        self.assertEqual("first", calls[1][1]["previous_user_query"]); self.assertEqual("answer:first", calls[1][1]["previous_assistant_answer"])
        self.assertIsNot(calls[1][1]["conversation_state"], calls[2][1]["conversation_state"])
        self.assertIsNone(calls[2][1]["previous_user_query"]); self.assertIsNone(calls[2][1]["previous_assistant_answer"])
        self.assertIs(calls[0][1]["generation_config"], calls[1][1]["generation_config"])


if __name__ == "__main__":
    unittest.main()
