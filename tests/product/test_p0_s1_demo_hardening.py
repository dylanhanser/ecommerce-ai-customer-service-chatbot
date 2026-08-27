"""Offline product regressions for the P0-S1 demo-hardening slice.

All questions and answers in this module are synthetic. Reviewer identifiers
are retained only as trace metadata because the score exports do not identify
which formal system produced the response under review.
"""

from __future__ import annotations

import unittest
from unittest import mock

from outputs import rag_answer_demo as rag


REVIEWER_TRACE_METADATA = (
    {"reviewer_case_id": "b3r_cf2f009f12da1da3ad0c7edb", "source_system": "unknown"},
    {"reviewer_case_id": "b3r_b1ed7689a2c480186be724c3", "source_system": "unknown"},
    {"reviewer_case_id": "b3r_95a1ee965670f6ec0d7ace2c", "source_system": "unknown"},
    {"reviewer_case_id": "b3r_9c5ba71ea90168584c7ba343", "source_system": "unknown"},
)


class P0S1DemoHardeningTests(unittest.TestCase):
    def test_general_policy_routes_to_direct_answer(self) -> None:
        cases = (
            ("一般多久发货", "shipping"),
            ("退款流程是什么", "refund"),
            ("一般退款多久能到账", "refund"),
            ("尺码不合适怎么申请换货", "exchange"),
        )
        for question, domain in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertIs(decision.route, rag.AnswerRoute.DIRECT_ANSWER)
                self.assertEqual(decision.domain, domain)
                self.assertTrue(decision.has_policy_facet)
                self.assertFalse(decision.needs_realtime_status)
                self.assertFalse(decision.needs_backend_action)
                self.assertFalse(rag.intent_guard(question)[0])

    def test_realtime_status_routes_to_full_handoff(self) -> None:
        cases = (
            ("我的订单什么时候发货", "shipping"),
            ("退款什么时候到账", "refund"),
            ("我的换货现在处理到哪了", "exchange"),
        )
        for question, domain in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertIs(decision.route, rag.AnswerRoute.FULL_HANDOFF)
                self.assertEqual(decision.domain, domain)
                self.assertTrue(decision.needs_realtime_status)
                self.assertFalse(decision.needs_backend_action)
                self.assertIn("无法查询", rag.answer_for_p0_s1_route(decision))

    def test_mixed_refund_question_keeps_policy_and_hands_off_status(self) -> None:
        decision = rag.decide_p0_s1_answer_route("一般怎么退款，我这单到账了吗")
        self.assertIs(decision.route, rag.AnswerRoute.POLICY_PLUS_HANDOFF)
        self.assertEqual(decision.domain, "refund")
        self.assertTrue(decision.has_policy_facet)
        self.assertTrue(decision.needs_realtime_status)
        self.assertEqual(decision.policy_query, "退款流程是什么")

    def test_backend_actions_route_to_full_handoff(self) -> None:
        cases = (
            ("帮我把这单改成38码", "exchange"),
            ("帮我催一下发货", "shipping"),
        )
        for question, domain in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                answer = rag.answer_for_p0_s1_route(decision)
                self.assertIs(decision.route, rag.AnswerRoute.FULL_HANDOFF)
                self.assertEqual(decision.domain, domain)
                self.assertTrue(decision.needs_backend_action)
                self.assertIn("没有后台执行能力", answer)
                self.assertNotIn("已改", answer)
                self.assertNotIn("已催", answer)

    def test_ambiguous_input_asks_one_minimal_question(self) -> None:
        for question in ("退", "客服一直没回，是物流没更新吗"):
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                answer = rag.answer_for_p0_s1_route(decision)
                self.assertIs(decision.route, rag.AnswerRoute.CLARIFY_THEN_ANSWER)
                self.assertEqual(answer.count("？") + answer.count("?"), 1)
                self.assertFalse(
                    any(marker in answer for marker in ("已查询", "已退款", "物流就是"))
                )

    def test_runtime_quarantine_uses_stable_metadata_and_preserves_safe_policy(self) -> None:
        risky_freight = {
            "doc_id": "snippet_yf_1",
            "source_file": rag.SNIPPETS_CORPUS_SOURCE_FILE,
            "source_type": "aftersales_rule",
            "answer_or_content": "synthetic freight statement",
        }
        risky_endorsement = {
            "doc_id": "snippet_zp_1",
            "source_file": rag.SNIPPETS_CORPUS_SOURCE_FILE,
            "source_type": "aftersales_rule",
            "answer_or_content": "synthetic insurance statement",
        }
        conditional_freight = {
            "doc_id": "snippet_yf_6",
            "source_file": rag.SNIPPETS_CORPUS_SOURCE_FILE,
            "source_type": "aftersales_rule",
            "answer_or_content": "是否可用以订单页和当前店铺规则为准",
        }
        results = [(risky_freight, 0.91), (risky_endorsement, 0.90), (conditional_freight, 0.89)]

        filtered = rag.filter_results_for_answer_generation(results, backend_required=False)

        self.assertEqual(
            set(rag.QUARANTINED_KNOWLEDGE_DOC_IDS), {"snippet_yf_1", "snippet_zp_1"}
        )
        self.assertEqual([item[0]["doc_id"] for item in filtered], ["snippet_yf_6"])
        self.assertTrue(rag.knowledge_quarantine_reason(risky_freight))
        self.assertTrue(rag.knowledge_quarantine_reason(risky_endorsement))
        self.assertIsNone(rag.knowledge_quarantine_reason(conditional_freight))

    def test_claim_validator_rewrites_unverified_high_risk_claims(self) -> None:
        cases = (
            ("已查询，包裹正在处理中。", "backend_success"),
            ("已经把这单改成38码。", "backend_success"),
            ("已经把地址修改为新地址。", "backend_success"),
            ("这笔款已经退款。", "backend_success"),
            ("已经帮您催促发货。", "backend_success"),
            ("缺货商品已补发。", "backend_success"),
            ("您的换货已经处理完成。", "backend_success"),
            ("这笔退货已经处理完成。", "backend_success"),
            ("商品会从上海仓发出。", "warehouse_location"),
            ("商品由中国人保PICC提供正品险。", "insurance_endorsement"),
        )
        decision = rag.decide_p0_s1_answer_route("我的订单什么时候发货")
        for answer, claim_type in cases:
            with self.subTest(answer=answer):
                result = rag.validate_final_answer_claims(answer, route_decision=decision)
                self.assertTrue(result.rewritten)
                self.assertIn(claim_type, result.blocked_claims)
                self.assertTrue(result.answer)
                self.assertNotEqual(result.answer, answer)

    def test_claim_validator_does_not_kill_boundaries_or_negated_examples(self) -> None:
        safe_answers = (
            "我无法查询当前订单状态。",
            "需要联系人工确认是否已经退款。",
            "以下是一般换货流程。",
            "当前系统没有后台能力，不能声称已催促。",
            "订单尚未退款，请以订单页为准。",
        )
        for answer in safe_answers:
            with self.subTest(answer=answer):
                result = rag.validate_final_answer_claims(answer)
                self.assertFalse(result.rewritten)
                self.assertEqual(result.blocked_claims, ())
                self.assertEqual(result.answer, answer)

    def test_claim_validator_allows_explicit_trusted_support(self) -> None:
        backend = rag.validate_final_answer_claims(
            "已查询到退款完成。", backend_receipt_verified=True
        )
        canonical = rag.validate_final_answer_claims(
            "商品会从上海仓发出，由PICC承保正品险。",
            canonical_support={"warehouse_location", "insurance_endorsement"},
        )
        self.assertFalse(backend.rewritten)
        self.assertEqual(backend.blocked_claims, ())
        self.assertFalse(canonical.rewritten)
        self.assertEqual(canonical.blocked_claims, ())

    def test_mixed_route_returns_policy_plus_status_boundary_with_synthetic_retrieval(
        self,
    ) -> None:
        row = {
            "doc_id": "synthetic_refund_policy",
            "source_type": "policy_rule",
            "category": rag.CATEGORY_RETURN,
            "title": "合成退款流程",
            "question": "退款流程是什么",
            "answer": "可在订单页申请售后，按页面提示提交退款申请。",
            "answer_or_content": "可在订单页申请售后，按页面提示提交退款申请。",
            "priority": 90,
            "needs_backend_api": False,
        }
        llm_config = rag.LLMConfig(api_key="", base_url="", model="offline", client=None)
        with (
            mock.patch.object(rag, "retrieve", return_value=[(row, 0.95)]),
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "一般怎么退款，我这单到账了吗",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=llm_config,
            )
        provider_call.assert_not_called()
        self.assertEqual(
            result["answer_route"], rag.AnswerRoute.POLICY_PLUS_HANDOFF.value
        )
        self.assertTrue(result["requires_backend_api"])
        self.assertIn("申请售后", result["final_answer"])
        self.assertIn("无法查询", result["final_answer"])
        self.assertTrue(result["skip_llm"])

    def test_final_runtime_boundary_validates_synthetic_retrieval_claim(self) -> None:
        row = {
            "doc_id": "synthetic_bad_shipping_claim",
            "source_type": "policy_rule",
            "category": rag.CATEGORY_LOGISTICS,
            "title": "合成发货规则",
            "question": "一般多久发货",
            "answer": "已经帮您催促发货。",
            "answer_or_content": "已经帮您催促发货。",
            "priority": 90,
            "needs_backend_api": False,
        }
        llm_config = rag.LLMConfig(api_key="", base_url="", model="offline", client=None)
        with (
            mock.patch.object(rag, "retrieve", return_value=[(row, 0.95)]),
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "一般多久发货",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=llm_config,
            )
        provider_call.assert_not_called()
        self.assertTrue(result["claim_validation_rewritten"])
        self.assertIn("backend_success", result["blocked_claim_types"])
        self.assertNotIn("已经帮您催促", result["final_answer"])


if __name__ == "__main__":
    unittest.main()
