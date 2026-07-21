"""Evaluation-only invocation adapter; it does not implement RAG behavior."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
import sys
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "outputs"
if str(OUTPUTS) not in sys.path:
    sys.path.insert(0, str(OUTPUTS))

import rag_answer_demo as rag  # noqa: E402


class ContextMode(str, Enum):
    SINGLE_TURN = "single_turn"
    CONTEXT_AWARE = "context_aware"


SNAPSHOT_SCHEMA_VERSION = 1
MAX_SNAPSHOT_TEXT_BYTES = 16_384
MAX_SNAPSHOT_BYTES = 65_536
_STATE_FIELDS = tuple(item.name for item in fields(rag.ConversationState))
_STRING_STATE_FIELDS = {
    "current_topic", "query_type", "risk_type", "last_safe_answer_type",
    "last_user_query", "last_assistant_answer", "last_retrieval_query",
    "last_contextual_query", "last_successful_contextual_query",
}
_BOOL_STATE_FIELDS = {"requires_backend_api", "should_reset"}
_INT_STATE_FIELDS = {"state_turn_count", "updated_at_turn"}


@dataclass(frozen=True)
class ConversationStateSnapshotV1:
    """Scalar-only immutable copy of the V2.1b conversation state."""

    current_topic: str
    query_type: str
    risk_type: str
    last_safe_answer_type: str
    last_user_query: str
    last_assistant_answer: str
    last_retrieval_query: str
    last_contextual_query: str
    last_successful_contextual_query: str
    requires_backend_api: bool
    should_reset: bool
    state_confidence: float
    state_turn_count: int
    updated_at_turn: int

    def to_dict(self) -> dict[str, object]:
        return {
            "current_topic": self.current_topic,
            "query_type": self.query_type,
            "risk_type": self.risk_type,
            "last_safe_answer_type": self.last_safe_answer_type,
            "last_user_query": self.last_user_query,
            "last_assistant_answer": self.last_assistant_answer,
            "last_retrieval_query": self.last_retrieval_query,
            "last_contextual_query": self.last_contextual_query,
            "last_successful_contextual_query": self.last_successful_contextual_query,
            "requires_backend_api": self.requires_backend_api,
            "should_reset": self.should_reset,
            "state_confidence": self.state_confidence,
            "state_turn_count": self.state_turn_count,
            "updated_at_turn": self.updated_at_turn,
        }


@dataclass(frozen=True)
class RuntimeConversationSnapshotV1:
    """The portable, deeply immutable continuation boundary for a turn."""

    schema_version: int
    completed_turn_index: int
    conversation_state: ConversationStateSnapshotV1
    previous_user_text: str | None
    previous_assistant_text: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "completed_turn_index": self.completed_turn_index,
            "conversation_state": self.conversation_state.to_dict(),
            "previous_user_text": self.previous_user_text,
            "previous_assistant_text": self.previous_assistant_text,
        }


@dataclass(frozen=True)
class DialogueRun:
    results: tuple[dict, ...]
    final_snapshot: RuntimeConversationSnapshotV1 | None


class SnapshotValidationError(ValueError):
    pass


EVALUATION_GENERATION_CONFIG = rag.GenerationConfig(
    temperature=0.0, top_p=1.0, max_tokens=512, stream=False,
)


def _utf8_size(value: str) -> int:
    return len(value.encode("utf-8"))


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise SnapshotValidationError("invalid snapshot " + name)
    if _utf8_size(value) > MAX_SNAPSHOT_TEXT_BYTES:
        raise SnapshotValidationError(
            "invalid snapshot " + name + " (UTF-8 bytes exceeds 16384)"
        )
    return value


def _require_optional_text(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, name)


def _validate_state(value: object) -> ConversationStateSnapshotV1:
    if not isinstance(value, Mapping) or set(value) != set(_STATE_FIELDS):
        raise SnapshotValidationError("invalid snapshot conversation_state fields")
    state = dict(value)
    for name in _STRING_STATE_FIELDS:
        _require_text(state[name], "conversation_state." + name)
    for name in _BOOL_STATE_FIELDS:
        if type(state[name]) is not bool:
            raise SnapshotValidationError("invalid snapshot conversation_state." + name)
    for name in _INT_STATE_FIELDS:
        if type(state[name]) is not int or state[name] < 0:
            raise SnapshotValidationError("invalid snapshot conversation_state." + name)
    confidence = state["state_confidence"]
    if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise SnapshotValidationError("invalid snapshot conversation_state.state_confidence")
    return ConversationStateSnapshotV1(
        current_topic=state["current_topic"],
        query_type=state["query_type"],
        risk_type=state["risk_type"],
        last_safe_answer_type=state["last_safe_answer_type"],
        last_user_query=state["last_user_query"],
        last_assistant_answer=state["last_assistant_answer"],
        last_retrieval_query=state["last_retrieval_query"],
        last_contextual_query=state["last_contextual_query"],
        last_successful_contextual_query=state["last_successful_contextual_query"],
        requires_backend_api=state["requires_backend_api"],
        should_reset=state["should_reset"],
        state_confidence=float(confidence),
        state_turn_count=state["state_turn_count"],
        updated_at_turn=state["updated_at_turn"],
    )


def restore_runtime_snapshot(value: Mapping[str, object]) -> RuntimeConversationSnapshotV1:
    """Strictly validate a V1 snapshot; this deliberately has no migration path."""
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "completed_turn_index", "conversation_state",
        "previous_user_text", "previous_assistant_text",
    }:
        raise SnapshotValidationError("invalid snapshot fields")
    if type(value["schema_version"]) is not int or value["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotValidationError("unsupported snapshot schema version")
    completed = value["completed_turn_index"]
    if type(completed) is not int or completed < 0:
        raise SnapshotValidationError("invalid snapshot completed_turn_index")
    state = _validate_state(value["conversation_state"])
    previous_user = _require_optional_text(value["previous_user_text"], "previous_user_text")
    previous_assistant = _require_optional_text(value["previous_assistant_text"], "previous_assistant_text")
    validated = RuntimeConversationSnapshotV1(
        SNAPSHOT_SCHEMA_VERSION, completed, state, previous_user, previous_assistant,
    )
    canonical_bytes = json.dumps(
        validated.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if len(canonical_bytes) > MAX_SNAPSHOT_BYTES:
        raise SnapshotValidationError("snapshot too large")
    # State normally records these values, but reset paths may intentionally clear them.
    if state.last_user_query and state.last_user_query != previous_user:
        raise SnapshotValidationError("snapshot previous_user_text mismatch")
    if state.last_assistant_answer and state.last_assistant_answer != previous_assistant:
        raise SnapshotValidationError("snapshot previous_assistant_text mismatch")
    return validated


def _copy_returned_state(state: rag.ConversationState, returned: object) -> None:
    if not isinstance(returned, dict):
        return
    for item in fields(rag.ConversationState):
        if item.name in returned:
            setattr(state, item.name, returned[item.name])


def _snapshot(state: rag.ConversationState, completed: int, previous_user: str | None, previous_assistant: str | None) -> RuntimeConversationSnapshotV1:
    return restore_runtime_snapshot({
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "completed_turn_index": completed,
        "conversation_state": state.to_dict(),
        "previous_user_text": previous_user,
        "previous_assistant_text": previous_assistant,
    })


def run_dialogue_checkpointed(
    turns: Iterable[str], *, mode: ContextMode, initial_state_snapshot: Mapping[str, object] | None = None,
    corpus: Any, embeddings: Any, embedding_model: Any, top_k: int, cosine_similarity: Any,
    low_confidence_threshold: float, llm_config: rag.LLMConfig,
    run_query: Callable[..., dict] = rag.run_rag_query,
    generation_config: rag.GenerationConfig = EVALUATION_GENERATION_CONFIG,
) -> DialogueRun:
    """Run one sequence through the original runtime, optionally from a validated snapshot."""
    if mode is ContextMode.SINGLE_TURN:
        if initial_state_snapshot is not None:
            raise SnapshotValidationError("single_turn does not accept a snapshot")
        restored = None
    elif mode is ContextMode.CONTEXT_AWARE:
        restored = restore_runtime_snapshot(initial_state_snapshot) if initial_state_snapshot is not None else None
    else:
        raise ValueError("unknown context mode")
    shared_state = rag.ConversationState(**restored.conversation_state.to_dict()) if restored else rag.ConversationState()
    previous_user = restored.previous_user_text if restored else None
    previous_answer = restored.previous_assistant_text if restored else None
    completed = restored.completed_turn_index if restored else 0
    results: list[dict] = []
    for turn in turns:
        if not isinstance(turn, str):
            raise TypeError("dialogue turn must be text")
        if mode is ContextMode.SINGLE_TURN:
            state, prior_user, prior_answer = rag.ConversationState(), None, None
        else:
            # A failed attempt never mutates the saved continuation state.
            state = rag.ConversationState(**shared_state.to_dict())
            prior_user, prior_answer = previous_user, previous_answer
        result = run_query(turn, corpus, embeddings, embedding_model, top_k, cosine_similarity,
                           low_confidence_threshold, llm_config, previous_user_query=prior_user,
                           previous_assistant_answer=prior_answer, conversation_state=state,
                           generation_config=generation_config)
        results.append(result)
        if mode is ContextMode.CONTEXT_AWARE:
            _copy_returned_state(state, result.get("conversation_state"))
            shared_state, previous_user, previous_answer = state, turn, str(result.get("final_answer", ""))
            completed += 1
    final = _snapshot(shared_state, completed, previous_user, previous_answer) if mode is ContextMode.CONTEXT_AWARE else None
    return DialogueRun(tuple(results), final)


def run_dialogue(turns: Iterable[str], **kwargs: Any) -> list[dict]:
    """Legacy list-returning entry point sharing the checkpointed execution path."""
    return list(run_dialogue_checkpointed(turns, **kwargs).results)
