"""Offline tests for the immutable QA-only baseline adapter."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.formal_qa_only_baseline import adapter


class _Indices(list):
    pass


class _Scores(list):
    def argsort(self):
        return _Indices(sorted(range(len(self)), key=self.__getitem__))


class _Corpus:
    def __init__(self, rows):
        self._rows = rows
        self.iloc = self

    def __len__(self):
        return len(self._rows)

    def __getitem__(self, index):
        return self._rows[index]


class _Encoder:
    def __init__(self):
        self.calls = 0

    def encode(self, values, **_kwargs):
        self.calls += 1
        return values


class _Completions:
    def __init__(self):
        self.payloads = []

    def create(self, **kwargs):
        self.payloads.append(kwargs)
        message = type("Message", (), {"content": "synthetic response"})()
        return type("Response", (), {"choices": [type("Choice", (), {"message": message})()]})()


class _Client:
    def __init__(self):
        self.completions = _Completions()
        self.chat = type("Chat", (), {"completions": self.completions})()


def _cosine(_query, _embeddings):
    return [_Scores([0.95, 0.80, 0.70, 0.60, 0.56])]


def _resources(*, synthetic=True, metadata=None):
    rows = [
        {"category": "other", "question": "商品问题", "answer": "普通说明", "source_type": "chat_qa", "priority": 50}
        for _ in range(5)
    ]
    supplied = {
        "corpus_type": "qa_only",
        "cache_family": "v1_qa",
        "embedding_model": adapter.EMBEDDING_MODEL_NAME,
        "contains_structured_snippets": False,
        "synthetic": synthetic,
        "row_count": len(rows) if synthetic else 15333,
    }
    if metadata:
        supplied.update(metadata)
    return adapter.BaselineResources(_Corpus(rows), object(), _Encoder(), _cosine, _Client(), supplied, synthetic)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        sys.modules.pop(adapter.VENDOR_MODULE_NAME, None)

    def test_import_has_no_vendor_or_v2_side_effect(self):
        code = "import sys; import scripts.formal_qa_only_baseline.adapter; print('_formal_qa_only_vendor_snapshot' in sys.modules); print('outputs.rag_answer_demo' in sys.modules)"
        result = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
        self.assertEqual(result.stdout.splitlines(), ["False", "False"])

    def test_import_does_not_read_env_or_create_client_or_load_model(self):
        source = Path(adapter.__file__).read_text(encoding="utf-8")
        self.assertNotIn("load_dotenv", source)
        self.assertNotIn("SentenceTransformer(", source)
        self.assertNotIn("OpenAI(", source)

    def test_vendor_provenance_is_frozen(self):
        path = adapter._verify_vendor()
        self.assertEqual(path.stat().st_size, adapter.VENDOR_SIZE)

    def test_tampered_vendor_fails_closed(self):
        original = adapter._vendor_path
        with tempfile.TemporaryDirectory() as directory:
            changed = Path(directory) / "vendor.py"
            changed.write_bytes(b"tampered")
            adapter._vendor_path = lambda: changed
            with self.assertRaises(adapter.VendorIntegrityError):
                adapter._verify_vendor()
        adapter._vendor_path = original

    def test_no_git_dependency(self):
        self.assertEqual(adapter._verify_vendor().name, "rag_answer_demo_12136b7.py")

    def test_system_id_top_k_and_cache_family_are_fixed(self):
        result = adapter.run_qa_only_baseline_query("商品问题", _resources())
        self.assertEqual((result["system_id"], result["top_k"], result["cache_family"]),
                         ("qa_only_reconstructed_baseline", 5, "v1_qa"))

    def test_callers_cannot_override_top_k_or_state(self):
        with self.assertRaises(TypeError):
            adapter.run_qa_only_baseline_query("商品问题", _resources(), top_k=1)
        with self.assertRaises(TypeError):
            adapter.run_qa_only_baseline_query("商品问题", _resources(), conversation_state={})

    def test_mixed_or_snippets_resources_are_rejected(self):
        for metadata in ({"corpus_type": "mixed"}, {"contains_structured_snippets": True}, {"cache_family": "v2_mixed"}):
            with self.assertRaises(adapter.BaselineAdapterError):
                adapter.run_qa_only_baseline_query("商品问题", _resources(metadata=metadata))

    def test_missing_or_mismatched_formal_metadata_fails_closed(self):
        formal = _resources(synthetic=False, metadata={"synthetic": False, "row_count": 1})
        with self.assertRaises(adapter.BaselineAdapterError):
            adapter.run_qa_only_baseline_query("商品问题", formal)
        bad_model = _resources(metadata={"embedding_model": "wrong"})
        with self.assertRaises(adapter.BaselineAdapterError):
            adapter.run_qa_only_baseline_query("商品问题", bad_model)

    def test_synthetic_requires_explicit_marker(self):
        with self.assertRaises(adapter.BaselineAdapterError):
            adapter.run_qa_only_baseline_query("商品问题", _resources(metadata={"synthetic": False}))

    def test_query_uses_vendor_retrieve_rerank_and_generate_not_cli(self):
        vendor = adapter._load_vendor()
        calls = []
        originals = {name: getattr(vendor, name) for name in ("retrieve", "rerank_retrieved_results", "generate_final_answer")}
        try:
            for name in originals:
                setattr(vendor, name, self._wrapped(name, originals[name], calls))
            vendor.main = lambda: (_ for _ in ()).throw(AssertionError("main called"))
            vendor.interactive_loop = lambda *_: (_ for _ in ()).throw(AssertionError("interactive called"))
            adapter.run_qa_only_baseline_query("商品问题", _resources())
        finally:
            for name, value in originals.items():
                setattr(vendor, name, value)
        self.assertEqual(calls, ["retrieve", "rerank_retrieved_results", "generate_final_answer"])

    @staticmethod
    def _wrapped(name, fn, calls):
        def wrapped(*args, **kwargs):
            calls.append(name)
            return fn(*args, **kwargs)
        return wrapped

    def test_generation_payload_is_forced_and_has_no_thinking(self):
        resources = _resources()
        adapter.run_qa_only_baseline_query("商品问题", resources)
        payload = resources.llm_client.completions.payloads[-1]
        self.assertEqual({key: payload[key] for key in adapter.GENERATION_CONFIG}, adapter.GENERATION_CONFIG)
        self.assertNotIn("thinking", payload)

    def test_generation_config_cannot_be_overridden(self):
        with self.assertRaises(TypeError):
            adapter.run_qa_only_baseline_query("商品问题", _resources(), model="other")

    def test_queries_are_state_isolated_and_deterministic(self):
        first = adapter.run_qa_only_baseline_query("商品问题", _resources())
        second = adapter.run_qa_only_baseline_query("商品问题", _resources())
        self.assertEqual(first, second)

    def test_output_does_not_expose_prompt_or_documents(self):
        result = adapter.run_qa_only_baseline_query("商品问题", _resources())
        self.assertEqual(set(result), {"answer", "system_id", "top_k", "cache_family", "provenance_sha256", "generation_config", "retrieved_count"})

    def test_no_automatic_cache_rebuild_or_data_access(self):
        resources = _resources()
        adapter.run_qa_only_baseline_query("商品问题", resources)
        self.assertEqual(resources.embedding_model.calls, 1)

    def test_client_exception_is_not_emitted_or_leaked(self):
        resources = _resources()
        def fail(**_kwargs):
            raise RuntimeError("secret question and local path")
        resources.llm_client.completions.create = fail
        result = adapter.run_qa_only_baseline_query("商品问题", resources)
        self.assertIn("answer", result)

    def test_formal_runner_transport_is_not_imported(self):
        adapter.run_qa_only_baseline_query("商品问题", _resources())
        self.assertNotIn("scripts.formal_evaluation_runtime", sys.modules)


if __name__ == "__main__":
    unittest.main()
