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


class ChatRequest(BaseModel):
    question: str


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

    def chat(self, question: str) -> dict[str, Any]:
        skip_retrieval, guarded_type, guarded_answer = rag.intent_guard(question)
        if skip_retrieval:
            backend_required = guarded_type == "backend_required"
            invalid_input = guarded_type == "unclear"
            return {
                "question": question,
                "final_answer": guarded_answer,
                "requires_backend_api": backend_required,
                "invalid_input": invalid_input,
                "skip_retrieval": True,
                "skip_llm": True,
                "query_type": guarded_type,
                "policy_category": None,
                "retrieved_results": [],
                "reranked_results": [],
            }

        invalid_input, invalid_answer = rag.invalid_input_guard(question)
        if invalid_input:
            return {
                "question": question,
                "final_answer": invalid_answer or rag.INVALID_INPUT_ANSWER,
                "requires_backend_api": False,
                "invalid_input": True,
                "skip_retrieval": True,
                "skip_llm": True,
                "query_type": "unclear",
                "policy_category": None,
                "retrieved_results": [],
                "reranked_results": [],
            }

        self.load()
        top_k = int(os.getenv("RAG_TOP_K", "10"))
        threshold = float(
            os.getenv("RAG_LOW_CONFIDENCE_THRESHOLD", str(rag.LOW_CONFIDENCE_THRESHOLD))
        )

        original_results = rag.retrieve(
            question,
            self.corpus,
            self.embeddings,
            self.embedding_model,
            top_k,
            self.cosine_similarity,
        )
        reranked_results, policy_category = rag.rerank_retrieved_results(
            question, original_results
        )
        backend_required = rag.resolve_backend_required(question, reranked_results)
        query_type = rag.detect_query_type(question, backend_required, policy_category)
        final_answer, _prompt = rag.generate_final_answer(
            question,
            original_results,
            reranked_results,
            threshold,
            self.llm_config,
            backend_required,
            query_type=query_type,
        )

        return {
            "question": question,
            "final_answer": final_answer,
            "requires_backend_api": backend_required,
            "invalid_input": False,
            "skip_retrieval": False,
            "skip_llm": backend_required,
            "query_type": query_type,
            "policy_category": policy_category,
            "retrieved_results": serialize_results(original_results),
            "reranked_results": serialize_results(reranked_results),
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
    try:
        return engine.chat(question)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
