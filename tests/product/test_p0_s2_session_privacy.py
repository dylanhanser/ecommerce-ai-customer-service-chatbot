"""Offline regression tests for P0-S2 session isolation and response privacy."""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as web_app  # noqa: E402


SAFE_ANSWER = "这是脱敏的合成回答。"
SENSITIVE_KEY_FRAGMENTS = {
    "retriev",
    "rerank",
    "score",
    "doc_id",
    "source_id",
    "metadata",
    "prompt",
    "system_message",
    "provider",
    "trace",
    "debug",
    "session",
}


class RecordingEngine:
    """Small offline engine double; it never imports or calls a Provider."""

    def __init__(self, result: dict | None = None, failure: Exception | None = None) -> None:
        self.result = result or {"final_answer": SAFE_ANSWER}
        self.failure = failure
        self.session_ids: list[str] = []

    def chat(self, question: str, session_id: str) -> dict:
        self.session_ids.append(session_id)
        if self.failure is not None:
            raise self.failure
        return dict(self.result)


def post_chat(client: TestClient, **payload: str):
    body = {"question": "合成测试问题"}
    body.update(payload)
    return client.post("/chat", json=body)


def assert_no_sensitive_keys(testcase: unittest.TestCase, value: object) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).casefold()
            testcase.assertFalse(
                any(fragment in normalized for fragment in SENSITIVE_KEY_FRAGMENTS),
                f"sensitive response key: {key}",
            )
            assert_no_sensitive_keys(testcase, nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_sensitive_keys(testcase, nested)


class SessionIsolationTests(unittest.TestCase):
    def test_two_cookie_less_clients_receive_distinct_engine_sessions(self) -> None:
        recorder = RecordingEngine()
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app) as first, TestClient(web_app.app) as second:
                self.assertEqual(post_chat(first).status_code, 200)
                self.assertEqual(post_chat(second).status_code, 200)

        self.assertEqual(len(recorder.session_ids), 2)
        self.assertNotEqual(recorder.session_ids[0], recorder.session_ids[1])
        self.assertNotEqual(recorder.session_ids[0], "demo")
        self.assertNotEqual(recorder.session_ids[1], "demo")

    def test_same_client_reuses_server_session(self) -> None:
        recorder = RecordingEngine()
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app) as client:
                post_chat(client)
                post_chat(client)

        self.assertEqual(len(recorder.session_ids), 2)
        self.assertEqual(recorder.session_ids[0], recorder.session_ids[1])

    def test_client_supplied_demo_session_is_not_authoritative(self) -> None:
        recorder = RecordingEngine()
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app) as first, TestClient(web_app.app) as second:
                post_chat(first, session_id="demo")
                post_chat(second, session_id="demo")

        self.assertEqual(len(recorder.session_ids), 2)
        self.assertNotEqual(recorder.session_ids[0], recorder.session_ids[1])
        self.assertNotIn("demo", recorder.session_ids)

    def test_missing_cookie_creates_session_and_sets_cookie(self) -> None:
        recorder = RecordingEngine()
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app) as client:
                response = post_chat(client)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(recorder.session_ids), 1)
        self.assertTrue(recorder.session_ids[0])
        self.assertIn(web_app.SESSION_COOKIE_NAME, response.headers.get("set-cookie", ""))

    def test_invalid_or_overlong_cookie_is_rotated(self) -> None:
        invalid_values = ("bad!", "x" * 256, "contains space")
        for invalid_value in invalid_values:
            with self.subTest(cookie=invalid_value[:20]):
                recorder = RecordingEngine()
                with mock.patch.object(web_app, "engine", recorder):
                    with TestClient(web_app.app) as client:
                        client.cookies.set(web_app.SESSION_COOKIE_NAME, invalid_value)
                        response = post_chat(client)

                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(recorder.session_ids), 1)
                self.assertNotEqual(recorder.session_ids[0], invalid_value)
                self.assertIn(web_app.SESSION_COOKIE_NAME, response.headers.get("set-cookie", ""))

    def test_cookie_has_required_security_attributes_without_domain(self) -> None:
        recorder = RecordingEngine()
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app) as client:
                header = post_chat(client).headers.get("set-cookie", "")

        normalized = header.casefold()
        self.assertIn("httponly", normalized)
        self.assertIn("samesite=lax", normalized)
        self.assertIn("path=/", normalized)
        self.assertNotIn("domain=", normalized)

    def test_secure_cookie_can_be_enabled_for_https(self) -> None:
        recorder = RecordingEngine()
        with mock.patch.dict(os.environ, {web_app.SECURE_COOKIE_ENV: "true"}, clear=False):
            with mock.patch.object(web_app, "engine", recorder):
                with TestClient(web_app.app) as client:
                    header = post_chat(client).headers.get("set-cookie", "")

        self.assertIn("secure", header.casefold())

    def test_session_token_is_absent_from_json_and_page_body(self) -> None:
        recorder = RecordingEngine()
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app) as client:
                chat_response = post_chat(client)
                page_response = client.get("/")

        token = recorder.session_ids[0]
        self.assertNotIn(token, chat_response.text)
        self.assertNotIn(token, page_response.text)
        self.assertNotIn(web_app.SESSION_COOKIE_NAME, chat_response.text)
        self.assertNotIn(web_app.SESSION_COOKIE_NAME, page_response.text)


class PublicResponsePrivacyTests(unittest.TestCase):
    def test_endpoint_uses_an_explicit_success_whitelist(self) -> None:
        unsafe_result = {
            "final_answer": SAFE_ANSWER,
            "retrieved_results": [{"doc_id": "synthetic-doc", "answer": "private context"}],
            "reranked_results": [{"rerank_score": 0.99}],
            "conversation_state": {"trace": "internal"},
            "prompt": "internal prompt",
            "provider_response": {"body": "private"},
        }
        recorder = RecordingEngine(result=unsafe_result)
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app) as client:
                response = post_chat(client)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"final_answer": SAFE_ANSWER})

    def test_public_json_has_no_recursively_nested_sensitive_keys(self) -> None:
        unsafe_result = {
            "final_answer": SAFE_ANSWER,
            "ui_state": {
                "nested": [
                    {"metadata": {"source_id": "synthetic"}},
                    {"trace": ["private"]},
                ]
            },
        }
        recorder = RecordingEngine(result=unsafe_result)
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app) as client:
                payload = post_chat(client).json()

        assert_no_sensitive_keys(self, payload)
        self.assertEqual(set(payload), {"final_answer"})

    def test_internal_exception_is_replaced_by_generic_error(self) -> None:
        secret_exception = RuntimeError(
            "DeepSeek provider body api_key=synthetic-secret at D:\\private\\runtime.pkl"
        )
        recorder = RecordingEngine(failure=secret_exception)
        with mock.patch.object(web_app, "engine", recorder):
            with TestClient(web_app.app, raise_server_exceptions=False) as client:
                response = post_chat(client)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(set(response.json()), {"final_answer", "error_code"})
        self.assertEqual(response.json()["error_code"], "CHAT_UNAVAILABLE")
        body = response.text.casefold()
        for forbidden in ("deepseek", "api_key", "synthetic-secret", "d:\\private", "runtime.pkl"):
            self.assertNotIn(forbidden.casefold(), body)

    def test_invalid_request_is_sanitized_and_uses_whitelist(self) -> None:
        with TestClient(web_app.app, raise_server_exceptions=False) as client:
            response = client.post("/chat", json={"question": {"unexpected": "object"}})

        self.assertEqual(response.status_code, 422)
        self.assertEqual(set(response.json()), {"final_answer", "error_code"})
        self.assertEqual(response.json()["error_code"], "INVALID_REQUEST")
        self.assertNotIn("detail", response.json())


class FrontendSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (ROOT / "static" / "main.js").read_text(encoding="utf-8")
        cls.normalized = cls.source.casefold()

    def test_frontend_does_not_read_send_or_persist_session_identity(self) -> None:
        self.assertNotIn("session_id", self.normalized)
        self.assertNotIn("eai_session", self.normalized)
        self.assertNotIn("localstorage", self.normalized)
        self.assertNotIn("sessionstorage", self.normalized)
        self.assertIn('json.stringify({ question })', self.normalized)

    def test_frontend_inserts_chat_content_as_text(self) -> None:
        self.assertIn("textcontent", self.normalized)
        self.assertIn("createtextnode", self.normalized)
        self.assertNotIn("innerhtml", self.normalized)
        self.assertNotIn("insertadjacenthtml", self.normalized)

    def test_frontend_does_not_render_internal_debug_data(self) -> None:
        for forbidden in (
            "retrieved_results",
            "reranked_results",
            "rerank_score",
            "doc_id",
            "conversation_state",
            "retrieval_query",
            "followupdebug",
        ):
            self.assertNotIn(forbidden, self.normalized)
        self.assertIn("internaldebugpanel.remove()", self.normalized)


class FrontendChatOnlyLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = (ROOT / "static" / "main.js").read_text(encoding="utf-8")
        cls.css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
        cls.normalized_script = re.sub(r"\s+", " ", cls.script.casefold())
        cls.normalized_css = re.sub(r"\s+", " ", cls.css.casefold())

    def test_debug_removal_sets_explicit_chat_only_state_on_page_layout(self) -> None:
        self.assertIn('document.queryselector(".page")', self.normalized_script)
        self.assertIn('classlist.add("chat-only")', self.normalized_script)
        self.assertLess(
            self.normalized_script.index("internaldebugpanel.remove()"),
            self.normalized_script.index('classlist.add("chat-only")'),
        )

    def test_chat_only_layout_is_single_column_centered_with_bounded_desktop_width(
        self,
    ) -> None:
        self.assertRegex(
            self.normalized_css,
            r"\.page\.chat-only\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*;[^}]*justify-items:\s*center\s*;",
        )
        match = re.search(
            r"\.page\.chat-only\s+\.chat-card\s*\{(?P<body>[^}]*)\}",
            self.normalized_css,
        )
        self.assertIsNotNone(match)
        body = match.group("body") if match else ""
        self.assertIn("width: min(100%,", body)
        max_width = re.search(r"max-width:\s*(\d+)px\s*;", body)
        self.assertIsNotNone(max_width)
        self.assertGreaterEqual(int(max_width.group(1)), 680)
        self.assertLessEqual(int(max_width.group(1)), 800)

    def test_chat_only_narrow_layout_is_full_width_without_horizontal_overflow(
        self,
    ) -> None:
        mobile = self.normalized_css[self.normalized_css.index("@media (max-width: 980px)") :]
        self.assertRegex(
            mobile,
            r"\.page\.chat-only\s+\.chat-card\s*\{[^}]*width:\s*100%\s*;[^}]*max-width:\s*100%\s*;[^}]*min-width:\s*0\s*;",
        )
        self.assertRegex(mobile, r"\.composer\s+input\s*\{[^}]*min-width:\s*0\s*;")
        self.assertNotIn("100vw", mobile)


if __name__ == "__main__":
    unittest.main()
