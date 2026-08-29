#!/usr/bin/env python3
"""Minimal FastAPI web demo for the JD QA RAG assistant."""

from __future__ import annotations

import mimetypes
import os
import re
import secrets
import sys
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.requests import Request
from starlette.responses import Response

from demo_catalog import (
    MISSING_PRODUCT_SELECTION_ANSWER,
    UNKNOWN_PRODUCT_LINK_ANSWER,
    answer_product_question,
    extract_demo_product_link,
    is_product_specific_query,
    load_catalog,
)


BASE_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = BASE_DIR / "outputs"

if str(OUTPUTS_DIR) not in sys.path:
    sys.path.insert(0, str(OUTPUTS_DIR))

import rag_answer_demo as rag  # noqa: E402

DEFAULT_CACHE_DIR = rag.DEFAULT_CACHE_ROOT
MAX_SESSION_HISTORY_TURNS = 3
SESSION_COOKIE_NAME = "eai_session"
SECURE_COOKIE_ENV = "EAI_SESSION_COOKIE_SECURE"
SESSION_TOKEN_BYTES = 32
SESSION_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43}$")
GENERIC_CHAT_ERROR = "暂时无法处理，请稍后重试。"
GENERIC_CHAT_ERROR_CODE = "CHAT_UNAVAILABLE"
INVALID_REQUEST_ERROR = "请输入有效的问题。"
INVALID_REQUEST_ERROR_CODE = "INVALID_REQUEST"
INVALID_PRODUCT_ERROR = "演示商品不存在。"


class ChatRequest(BaseModel):
    question: str
    # Accepted only for backward-compatible request parsing. The server cookie is authoritative.
    session_id: str | None = None


class DemoProductSelectionRequest(BaseModel):
    product_id: str


class RAGEngine:
    def __init__(self) -> None:
        self.lock = Lock()
        self.session_lock = Lock()
        self.loaded = False
        self.np = None
        self.pd = None
        self.cosine_similarity = None
        self.embedding_model = None
        self.corpus = None
        self.embeddings = None
        self.llm_config = None
        self.session_history: dict[str, list[dict[str, str]]] = {}
        self.session_states: dict[str, dict[str, Any]] = {}
        self.session_products: dict[str, str] = {}

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
        with self.session_lock:
            history = self.session_history.get(session_id, [])
            if not history:
                return "", ""
            last_turn = history[-1]
            return last_turn.get("user", ""), last_turn.get("assistant", "")

    def _get_conversation_state(self, session_id: str) -> dict[str, Any] | None:
        with self.session_lock:
            state = self.session_states.get(session_id)
            return dict(state) if state else None

    def _append_turn(self, session_id: str, user_query: str, assistant_answer: str) -> None:
        with self.session_lock:
            history = self.session_history.setdefault(session_id, [])
            history.append({"user": user_query, "assistant": assistant_answer})
            if len(history) > MAX_SESSION_HISTORY_TURNS:
                self.session_history[session_id] = history[-MAX_SESSION_HISTORY_TURNS:]

    def _store_conversation_state(self, session_id: str, state: dict[str, Any]) -> None:
        with self.session_lock:
            self.session_states[session_id] = dict(state)

    def select_product(self, session_id: str, product_id: str) -> bool:
        if demo_catalog.lookup(product_id) is None:
            return False
        with self.session_lock:
            self.session_products[session_id] = product_id
        return True

    def get_selected_product_id(self, session_id: str) -> str | None:
        with self.session_lock:
            return self.session_products.get(session_id)

    def _deterministic_product_result(
        self,
        question: str,
        answer: str,
        *,
        session_id: str,
        query_type: str,
    ) -> dict[str, Any]:
        self._append_turn(session_id, question, answer)
        return {
            "question": question,
            "final_answer": answer,
            "requires_backend_api": False,
            "invalid_input": False,
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": query_type,
            "policy_category": None,
            "original_query": question,
            "is_followup_query": False,
            "contextual_query": question,
            "previous_user_query": "",
            "retrieval_query": question,
            "inherited_financial_risk": False,
            "inherited_from_previous_query": "",
            "inherited_aftersales_operation": False,
            "inherited_backend_required": False,
            "conversation_state": {},
            "state_update_reason": "",
            "retrieved_results": [],
            "reranked_results": [],
        }

    def chat(self, question: str, *, session_id: str) -> dict[str, Any]:
        link_reference = extract_demo_product_link(question, demo_catalog)
        if link_reference.matched:
            if not link_reference.is_known or not link_reference.product_id:
                return self._deterministic_product_result(
                    question,
                    UNKNOWN_PRODUCT_LINK_ANSWER,
                    session_id=session_id,
                    query_type="demo_product_not_found",
                )
            self.select_product(session_id, link_reference.product_id)

        selected_product_id = self.get_selected_product_id(session_id)
        selected_product = demo_catalog.lookup(selected_product_id)
        product_answer = answer_product_question(question, selected_product)
        if product_answer:
            return self._deterministic_product_result(
                question,
                product_answer,
                session_id=session_id,
                query_type="demo_product_answer",
            )
        if selected_product is None and is_product_specific_query(question):
            return self._deterministic_product_result(
                question,
                MISSING_PRODUCT_SELECTION_ANSWER,
                session_id=session_id,
                query_type="demo_product_clarification",
            )

        self.load()
        top_k = int(os.getenv("RAG_TOP_K", "10"))
        threshold = float(
            os.getenv("RAG_LOW_CONFIDENCE_THRESHOLD", str(rag.LOW_CONFIDENCE_THRESHOLD))
        )
        previous_user_query, previous_assistant_answer = self._get_previous_turn(session_id)
        conversation_state = self._get_conversation_state(session_id)

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
            conversation_state=conversation_state,
        )

        final_answer = result.get("final_answer", "")
        if final_answer:
            self._append_turn(session_id, question, final_answer)
        returned_state = result.get("conversation_state") or {}
        if returned_state:
            self._store_conversation_state(session_id, returned_state)

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
            "inherited_backend_required": result.get("inherited_backend_required", False),
            "conversation_state": returned_state,
            "state_update_reason": result.get("state_update_reason", ""),
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


def _secure_cookie_enabled() -> bool:
    return os.getenv(SECURE_COOKIE_ENV, "false").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _valid_session_token(value: str | None) -> bool:
    return bool(value and SESSION_TOKEN_PATTERN.fullmatch(value))


def _server_session(request: Request) -> tuple[str, bool]:
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME)
    if _valid_session_token(cookie_value):
        return cookie_value, False
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES), True


def _set_session_cookie(response: Response, session_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        secure=_secure_cookie_enabled(),
        samesite="lax",
        path="/",
    )


def _public_success_payload(result: dict[str, Any]) -> dict[str, str]:
    """Whitelist the sole field currently required by the public chat UI."""
    return {"final_answer": str(result.get("final_answer", ""))}


app = FastAPI(title="JD QA + Knowledge Base RAG Web Demo")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
mimetypes.add_type("image/webp", ".webp")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
demo_catalog = load_catalog()
engine = RAGEngine()


@app.exception_handler(RequestValidationError)
async def request_validation_error(request: Request, _exc: RequestValidationError):
    session_token, rotate_cookie = _server_session(request)
    response = JSONResponse(
        {
            "final_answer": INVALID_REQUEST_ERROR,
            "error_code": INVALID_REQUEST_ERROR_CODE,
        },
        status_code=422,
    )
    if rotate_cookie:
        _set_session_cookie(response, session_token)
    return response


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    session_token, rotate_cookie = _server_session(request)
    selected_product_lookup = getattr(engine, "get_selected_product_id", None)
    selected_product_id = (
        selected_product_lookup(session_token) if selected_product_lookup else None
    )
    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"selected_product": demo_catalog.public_product(selected_product_id)},
    )
    if rotate_cookie:
        _set_session_cookie(response, session_token)
    return response


@app.get("/products/{product_id}", response_class=HTMLResponse)
def product_page(product_id: str, request: Request):
    product = demo_catalog.public_product(product_id)
    if product is None:
        return HTMLResponse(
            "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<title>演示商品不存在</title></head><body><main>演示商品不存在。"
            "请返回首页重新选择。</main></body></html>",
            status_code=404,
        )
    session_token, rotate_cookie = _server_session(request)
    engine.select_product(session_token, product_id)
    response = templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"selected_product": product},
    )
    if rotate_cookie:
        _set_session_cookie(response, session_token)
    return response


@app.get("/api/demo-products")
def list_demo_products(request: Request):
    session_token, rotate_cookie = _server_session(request)
    response = JSONResponse(
        {
            "products": demo_catalog.public_products(),
            "selected_product_id": engine.get_selected_product_id(session_token),
        }
    )
    if rotate_cookie:
        _set_session_cookie(response, session_token)
    return response


@app.post("/api/demo-products/select")
def select_demo_product(selection: DemoProductSelectionRequest, request: Request):
    session_token, rotate_cookie = _server_session(request)
    product = demo_catalog.public_product(selection.product_id)
    if product is None:
        response = JSONResponse({"error": INVALID_PRODUCT_ERROR}, status_code=404)
    else:
        engine.select_product(session_token, selection.product_id)
        response = JSONResponse({"selected_product": product})
    if rotate_cookie:
        _set_session_cookie(response, session_token)
    return response

@app.post("/chat")
def chat(chat_request: ChatRequest, request: Request):
    question = chat_request.question.strip()
    session_token, rotate_cookie = _server_session(request)
    try:
        internal_result = engine.chat(question, session_id=session_token)
        response = JSONResponse(_public_success_payload(internal_result))
    except Exception:
        response = JSONResponse(
            {
                "final_answer": GENERIC_CHAT_ERROR,
                "error_code": GENERIC_CHAT_ERROR_CODE,
            },
            status_code=500,
        )
    if rotate_cookie:
        _set_session_cookie(response, session_token)
    return response
