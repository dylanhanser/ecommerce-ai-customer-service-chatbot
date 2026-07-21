"""Offline-only, single-turn adapter for the frozen QA-only baseline.

The vendor module is verified and loaded only when a query is run.  This module
does not read environment files, construct clients, load models, or assemble
corpora.  Callers must provide already-loaded resources.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import contextlib
import io
import importlib.util
from pathlib import Path
import sys
from typing import Any, Callable


SYSTEM_ID = "qa_only_reconstructed_baseline"
TOP_K = 5
CACHE_FAMILY = "v1_qa"
FORMAL_ROW_COUNT = 15333
EMBEDDING_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
VENDOR_SHA256 = "2a1585575162de62de30df3fca809048f5a81878b491050e57565e548936fcdc"
VENDOR_SIZE = 65949
VENDOR_MODULE_NAME = "_formal_qa_only_vendor_snapshot"
GENERATION_CONFIG = {
    "model": "deepseek-chat",
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 512,
    "stream": False,
}


class BaselineAdapterError(RuntimeError):
    """A deliberately non-sensitive adapter failure."""


class VendorIntegrityError(BaselineAdapterError):
    """The immutable vendor source did not match its frozen provenance."""


@dataclass(frozen=True)
class BaselineResources:
    """Explicit, already-loaded QA-only resources.

    ``synthetic`` is solely for offline fixtures.  Production resources must
    declare the formal row count, QA-only corpus type, v1 cache family, and
    frozen embedding-model name.  No paths are accepted or resolved here.
    """

    documents: Any
    embeddings: Any
    embedding_model: Any
    cosine_similarity: Callable[[Any, Any], Any]
    llm_client: Any
    metadata: dict[str, Any]
    synthetic: bool = False


def _vendor_path() -> Path:
    return Path(__file__).with_name("vendor") / "rag_answer_demo_12136b7.py"


def _verify_vendor() -> Path:
    path = _vendor_path()
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise VendorIntegrityError("Vendor snapshot integrity verification failed.") from exc
    if len(payload) != VENDOR_SIZE or sha256(payload).hexdigest() != VENDOR_SHA256:
        raise VendorIntegrityError("Vendor snapshot integrity verification failed.")
    return path


def _load_vendor() -> Any:
    path = _verify_vendor()
    module = sys.modules.get(VENDOR_MODULE_NAME)
    if module is not None:
        return module
    spec = importlib.util.spec_from_file_location(VENDOR_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise BaselineAdapterError("Baseline vendor could not be loaded.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[VENDOR_MODULE_NAME] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(VENDOR_MODULE_NAME, None)
        raise BaselineAdapterError("Baseline vendor could not be loaded.") from exc
    return module


def _validate_resources(resources: BaselineResources) -> None:
    metadata = resources.metadata
    required = {
        "corpus_type": "qa_only",
        "cache_family": CACHE_FAMILY,
        "embedding_model": EMBEDDING_MODEL_NAME,
    }
    if any(metadata.get(key) != value for key, value in required.items()):
        raise BaselineAdapterError("Baseline resources do not satisfy the QA-only contract.")
    if metadata.get("contains_structured_snippets") is not False:
        raise BaselineAdapterError("Baseline resources do not satisfy the QA-only contract.")
    if resources.synthetic:
        if metadata.get("synthetic") is not True:
            raise BaselineAdapterError("Synthetic resources require explicit synthetic metadata.")
    elif metadata.get("synthetic") is True or metadata.get("row_count") != FORMAL_ROW_COUNT:
        raise BaselineAdapterError("Baseline resources do not satisfy the QA-only contract.")
    if not all((resources.documents is not None, resources.embeddings is not None,
                resources.embedding_model is not None, callable(resources.cosine_similarity),
                resources.llm_client is not None)):
        raise BaselineAdapterError("Required baseline resources are unavailable.")


class _ForcedCompletions:
    def __init__(self, completions: Any) -> None:
        self._completions = completions

    def create(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.pop("thinking", None)
        kwargs.update(GENERATION_CONFIG)
        return self._completions.create(*args, **kwargs)


class _ForcedClient:
    """Preserves vendor prompt construction while forcing non-secret settings."""

    def __init__(self, client: Any) -> None:
        self.chat = type("Chat", (), {"completions": _ForcedCompletions(client.chat.completions)})()


def run_qa_only_baseline_query(question: str, resources: BaselineResources) -> dict[str, Any]:
    """Answer one isolated question using injected QA-only resources.

    Conversation state, prior messages, path resolution, cache rebuilding, and
    model/client construction are intentionally unsupported.
    """
    if not isinstance(question, str):
        raise BaselineAdapterError("Question must be a string.")
    _validate_resources(resources)
    vendor = _load_vendor()
    try:
        # The historical CLI prints diagnostics; the adapter contract is a safe
        # structured result, so preserve logic while suppressing those side effects.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            skip, query_type, guarded_answer = vendor.intent_guard(question)
            if skip:
                answer = guarded_answer or vendor.UNCLEAR_ANSWER
                retrieved_count = 0
            else:
                invalid, invalid_answer = vendor.invalid_input_guard(question)
                if invalid:
                    answer = invalid_answer or vendor.INVALID_INPUT_ANSWER
                    retrieved_count = 0
                else:
                    original = vendor.retrieve(question, resources.documents, resources.embeddings,
                                               resources.embedding_model, TOP_K, resources.cosine_similarity)
                    reranked, policy_category = vendor.rerank_retrieved_results(question, original)
                    backend_required = vendor.resolve_backend_required(question, reranked)
                    query_type = vendor.detect_query_type(question, backend_required, policy_category)
                    config = vendor.LLMConfig(
                        api_key="injected-client",
                        base_url="injected",
                        model=GENERATION_CONFIG["model"],
                        client=_ForcedClient(resources.llm_client),
                    )
                    answer, _ = vendor.generate_final_answer(
                        question, original, reranked, vendor.LOW_CONFIDENCE_THRESHOLD,
                        config, backend_required, query_type=query_type,
                    )
                    retrieved_count = len(original)
    except BaselineAdapterError:
        raise
    except Exception as exc:
        raise BaselineAdapterError("Baseline query could not be completed.") from exc
    return {
        "answer": answer,
        "system_id": SYSTEM_ID,
        "top_k": TOP_K,
        "cache_family": CACHE_FAMILY,
        "provenance_sha256": VENDOR_SHA256,
        "generation_config": dict(GENERATION_CONFIG),
        "retrieved_count": retrieved_count,
    }
