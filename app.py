#!/usr/bin/env python3
"""Minimal FastAPI web demo for the JD QA RAG assistant."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request


BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"

if str(OUTPUTS_DIR) not in sys.path:
    sys.path.insert(0, str(OUTPUTS_DIR))

import rag_answer_demo as rag  # noqa: E402

DEFAULT_CACHE_DIR = rag.DEFAULT_CACHE_ROOT
DEFAULT_SESSION_ID = "demo"
MAX_SESSION_HISTORY_TURNS = 3


class ChatRequest(BaseModel):
    question: str
    session_id: str = DEFAULT_SESSION_ID


class RAGEngine:
    def __init__(self) -> None:
        self.lock = Lock()
        self.loaded = False
        self.np = None
        self.pd = None
        self.cosine_similarity = None
        self.embedding_model = None
        self.corpus = None
        self.embeddings = None
        self.llm_config = None
        self.session_history: dict[str, list[dict[str, str]]] = {}

    def load(self) -> None:
        with self.lock:
            if self.loaded:
                return

            try:
                csv_path = rag.resolve_qa_csv_path(os.getenv("JD_QA_CSV"))
            except FileNotFoundError as exc:
                raise RuntimeError(str(exc)) from exc
            use_mixed = os.getenv("RAG_USE_MIXED_CORPUS", "true").strip().casefold() in {
                "1",
                "true",
                "yes",
                "on",
            }
            snippets_path = None
            if use_mixed:
                try:
                    snippets_path = rag.resolve_snippets_csv_path(os.getenv("JD_KNOWLEDGE_SNIPPETS_CSV"))
                except FileNotFoundError as exc:
                    raise RuntimeError(str(exc)) from exc
            cache_dir = Path(os.getenv("JD_RAG_CACHE_DIR", str(DEFAULT_CACHE_DIR))).expanduser().resolve()
            embedding_model_name = os.getenv("RAG_EMBEDDING_MODEL", rag.DEFAULT_EMBEDDING_MODEL)
            batch_size = int(os.getenv("RAG_BATCH_SIZE", "64"))

            (
                self.np,
                self.pd,
                load_dotenv,
                OpenAI,
                SentenceTransformer,
                self.cosine_similarity,
            ) = rag.load_dependencies()

            self.llm_config = rag.load_llm_config(load_dotenv, OpenAI)
            self.embedding_model = SentenceTransformer(embedding_model_name)
            self.corpus, self.embeddings = rag.load_or_create_cache(
                csv_path=csv_path,
                cache_dir=cache_dir,
                embedding_model=self.embedding_model,
                embedding_model_name=embedding_model_name,
                batch_size=batch_size,
                rebuild=False,
                np=self.np,
                pd=self.pd,
                snippets_csv_path=snippets_path,
            )
            self.loaded = True

    def _get_previous_turn(self, session_id: str) -> tuple[str, str]:
        history = self.session_history.get(session_id, [])
        if not history:
            return "", ""
        last_turn = history[-1]
        return last_turn.get("user", ""), last_turn.get("assistant", "")

    def _append_turn(self, session_id: str, user_query: str, assistant_answer: str) -> None:
        history = self.session_history.setdefault(session_id, [])
        history.append({"user": user_query, "assistant": assistant_answer})
        if len(history) > MAX_SESSION_HISTORY_TURNS:
            self.session_history[session_id] = history[-MAX_SESSION_HISTORY_TURNS:]

    def chat(self, question: str, session_id: str = DEFAULT_SESSION_ID) -> dict[str, Any]:
        self.load()
        top_k = int(os.getenv("RAG_TOP_K", "10"))
        threshold = float(
            os.getenv("RAG_LOW_CONFIDENCE_THRESHOLD", str(rag.LOW_CONFIDENCE_THRESHOLD))
        )
        previous_user_query, previous_assistant_answer = self._get_previous_turn(session_id)

        result = rag.run_rag_query(
            question,
            self.corpus,
            self.embeddings,
            self.embedding_model,
            top_k,
            self.cosine_similarity,
            threshold,
            self.llm_config,
            previous_user_query=previous_user_query or None,
            previous_assistant_answer=previous_assistant_answer or None,
        )

        final_answer = result.get("final_answer", "")
        if final_answer:
            self._append_turn(session_id, question, final_answer)

        return {
            "question": result["question"],
            "final_answer": final_answer,
            "requires_backend_api": result["requires_backend_api"],
            "invalid_input": result["invalid_input"],
            "skip_retrieval": result["skip_retrieval"],
            "skip_llm": result.get("skip_llm", result["requires_backend_api"]),
            "query_type": result["query_type"],
            "policy_category": result.get("policy_category"),
            "original_query": result.get("original_query", question),
            "is_followup_query": result.get("is_followup_query", False),
            "contextual_query": result.get("contextual_query", question),
            "previous_user_query": result.get("previous_user_query", ""),
            "retrieval_query": result.get("retrieval_query", question),
            "inherited_financial_risk": result.get("inherited_financial_risk", False),
            "inherited_from_previous_query": result.get("inherited_from_previous_query", ""),
            "inherited_aftersales_operation": result.get("inherited_aftersales_operation", False),
            "retrieved_results": serialize_results(result.get("original_results", [])),
            "reranked_results": serialize_results(result.get("reranked_results", [])),
        }


def serialize_results(results: list) -> list[dict[str, Any]]:
    serialized = []
    for rank, result in enumerate(results, start=1):
        row, similarity = result[0], result[1]
        meta = result[2] if len(result) > 2 else {}
        serialized.append(
            {
                "rank": rank,
                "original_rank": int(meta.get("original_rank", rank)),
                "similarity": round(float(similarity), 4),
                "rerank_score": round(float(meta.get("rerank_score", similarity)), 4),
                "rerank_reason": str(meta.get("rerank_reason", "embedding_only")),
                "doc_id": str(row.get("doc_id", "")),
                "source_type": str(row.get("source_type", "chat_qa")),
                "title": str(row.get("title", row.get("question", ""))),
                "question": str(row.get("question", "")),
                "answer": str(row.get("answer_or_content", row.get("answer", ""))),
                "category": str(row.get("category", "")),
                "priority": int(row.get("priority", rag.DEFAULT_QA_PRIORITY) or rag.DEFAULT_QA_PRIORITY),
                "needs_backend_api": rag.row_needs_backend_api(row),
                "session_id": str(row.get("session_id", "")),
                "source_file": str(row.get("source_file", "")),
            }
        )
    return serialized


app = FastAPI(title="JD QA + Knowledge Base RAG Web Demo")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
engine = RAGEngine()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
    request=request,
    name="index.html",
    context={}
)

@app.post("/chat")
def chat(request: ChatRequest):
    question = request.question.strip()
    session_id = (request.session_id or DEFAULT_SESSION_ID).strip() or DEFAULT_SESSION_ID
    try:
        return engine.chat(question, session_id=session_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
