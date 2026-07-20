"""Evaluation-only invocation adapter; it does not implement RAG behavior."""

from __future__ import annotations

from dataclasses import fields
from enum import Enum
from typing import Any, Callable, Iterable

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
if str(OUTPUTS) not in sys.path:
    sys.path.insert(0, str(OUTPUTS))

import rag_answer_demo as rag  # noqa: E402


class ContextMode(str, Enum):
    SINGLE_TURN = "single_turn"
    CONTEXT_AWARE = "context_aware"


EVALUATION_GENERATION_CONFIG = rag.GenerationConfig(
    temperature=0.0,
    top_p=1.0,
    max_tokens=512,
    stream=False,
)


def _copy_returned_state(state: rag.ConversationState, returned: object) -> None:
    if not isinstance(returned, dict):
        return
    for item in fields(rag.ConversationState):
        if item.name in returned:
            setattr(state, item.name, returned[item.name])


def run_dialogue(
    turns: Iterable[str],
    *,
    mode: ContextMode,
    corpus: Any,
    embeddings: Any,
    embedding_model: Any,
    top_k: int,
    cosine_similarity: Any,
    low_confidence_threshold: float,
    llm_config: rag.LLMConfig,
    run_query: Callable[..., dict] = rag.run_rag_query,
    generation_config: rag.GenerationConfig = EVALUATION_GENERATION_CONFIG,
) -> list[dict]:
    """Invoke the unchanged runtime with either context disabled or enabled."""
    shared_state = rag.ConversationState() if mode is ContextMode.CONTEXT_AWARE else None
    previous_user: str | None = None
    previous_answer: str | None = None
    results: list[dict] = []

    for turn in turns:
        if mode is ContextMode.SINGLE_TURN:
            state = rag.ConversationState()
            prior_user = None
            prior_answer = None
        else:
            state = shared_state
            prior_user = previous_user
            prior_answer = previous_answer
        result = run_query(
            turn,
            corpus,
            embeddings,
            embedding_model,
            top_k,
            cosine_similarity,
            low_confidence_threshold,
            llm_config,
            previous_user_query=prior_user,
            previous_assistant_answer=prior_answer,
            conversation_state=state,
            generation_config=generation_config,
        )
        results.append(result)
        if mode is ContextMode.CONTEXT_AWARE:
            _copy_returned_state(shared_state, result.get("conversation_state"))
            previous_user = turn
            previous_answer = str(result.get("final_answer", ""))
    return results
