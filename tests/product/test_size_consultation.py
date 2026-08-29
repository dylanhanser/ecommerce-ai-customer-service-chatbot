"""Offline regressions for structured shoe-size consultation.

All inputs are synthetic.  The tests must not load embeddings, create a real
provider client, read ``.env``, or write runtime/evaluation artifacts.
"""

from __future__ import annotations

from datetime import datetime
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from outputs import rag_answer_demo as rag


class SizeConsultationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.llm_config = rag.LLMConfig(
            api_key="synthetic-key",
            base_url="",
            model="offline",
            client=mock.Mock(),
        )

    def run_offline(
        self,
        question: str,
        *,
        state: dict | None = None,
        business_now: datetime | None = None,
    ) -> dict:
        with (
            mock.patch.object(rag, "retrieve") as retrieve_call,
            mock.patch.object(rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                question,
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=self.llm_config,
                conversation_state=state,
                business_now=business_now,
            )

        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        return result

    def test_explicit_foot_length_formats_normalize_consistently(self) -> None:
        cases = {
            "脚长24厘米穿多大": 24.0,
            "我的脚是24cm": 24.0,
            "24 CM": 24.0,
            "24 cm": 24.0,
            "24公分": 24.0,
            "脚长240毫米": 24.0,
            "240mm": 24.0,
            "24.0厘米": 24.0,
            "大概24厘米": 24.0,
            "差不多24厘米": 24.0,
            "脚长二十四厘米": 24.0,
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                parsed = rag.parse_foot_length_expression(text)
                self.assertEqual(parsed.status, "valid")
                self.assertEqual(parsed.normalized_cm, expected)

    def test_bare_measurements_require_active_foot_length_context(self) -> None:
        for text, expected in (("24", 24.0), ("24.5", 24.5), ("240", 24.0), ("24左右", 24.0)):
            with self.subTest(text=text):
                parsed = rag.parse_foot_length_expression(
                    text,
                    expecting_foot_length=True,
                )
                self.assertEqual(parsed.status, "valid")
                self.assertEqual(parsed.normalized_cm, expected)
                self.assertTrue(parsed.unit_inferred)

        for text in ("24", "24.5", "240", "24左右", "38"):
            with self.subTest(outside_context=text):
                self.assertEqual(
                    rag.parse_foot_length_expression(text).status,
                    "not_found",
                )

        for text in ("24", "24左右", "38"):
            with self.subTest(runtime_ambiguity=text):
                result = self.run_offline(text)
                self.assertEqual(result["query_type"], "size_measurement_clarification")
                self.assertRegex(result["final_answer"], r"脚长.*鞋码")
                self.assertIsNone(result["conversation_state"]["size_foot_length_cm"])

    def test_ranges_and_two_feet_are_preserved_conservatively(self) -> None:
        between = rag.parse_foot_length_expression("脚长24到24.5厘米")
        self.assertEqual(between.status, "valid")
        self.assertEqual(between.values_cm, (24.0, 24.5))
        self.assertTrue(between.is_range)
        self.assertTrue(between.uncertain)

        two_feet = rag.parse_foot_length_expression("左脚24右脚24.5")
        self.assertEqual(two_feet.status, "valid")
        self.assertEqual(two_feet.values_cm, (24.0, 24.5))
        self.assertEqual(two_feet.normalized_cm, 24.5)
        self.assertTrue(two_feet.unit_inferred)

    def test_invalid_measurements_request_correction_not_a_size(self) -> None:
        for text in ("脚长240厘米穿多大", "脚长24毫米穿多大", "脚长2400mm穿多大"):
            with self.subTest(text=text):
                result = self.run_offline(text)
                self.assertEqual(result["query_type"], "size_measurement_clarification")
                self.assertTrue(result["skip_retrieval"])
                self.assertTrue(result["skip_llm"])
                self.assertRegex(result["final_answer"], r"确认|单位|毫米|厘米")
                self.assertNotRegex(result["final_answer"], r"建议\s*\d{2}\s*码")

    def test_missing_authoritative_chart_degrades_without_exact_size(self) -> None:
        for text in ("脚长24厘米穿多大", "24.5厘米穿什么码", "脚长240毫米"):
            with self.subTest(text=text):
                result = self.run_offline(text)
                self.assertEqual(result["query_type"], "size_consultation")
                self.assertIn("脚长", result["final_answer"])
                self.assertIn("商品详情页", result["final_answer"])
                self.assertRegex(result["final_answer"], r"参考|无法可靠")
                self.assertNotRegex(result["final_answer"], r"建议\s*\d{2}\s*码")
                self.assertNotIn("标准码", result["final_answer"])

    def test_insufficient_and_usual_size_only_queries_ask_for_foot_length(self) -> None:
        cases = (
            "我穿多大",
            "这双买几码",
            "给我推荐个尺码",
            "我平时穿38，这个穿多少",
            "耐克穿39，这个穿多少",
            "以前买你们家另一款39，这款也39吗",
        )
        for text in cases:
            with self.subTest(text=text):
                result = self.run_offline(text)
                self.assertEqual(result["query_type"], "size_clarification")
                self.assertIn("脚长", result["final_answer"])
                self.assertNotRegex(result["final_answer"], r"建议\s*\d{2}\s*码")
                self.assertTrue(result["conversation_state"]["size_awaiting_foot_length"])

    def test_bare_reply_after_foot_length_question_uses_context(self) -> None:
        first = self.run_offline("我想知道穿多大")
        self.assertTrue(first["conversation_state"]["size_awaiting_foot_length"])

        for reply, expected in (("24", 24.0), ("24.5", 24.5), ("240mm", 24.0)):
            with self.subTest(reply=reply):
                second = self.run_offline(reply, state=first["conversation_state"])
                self.assertEqual(second["query_type"], "size_consultation")
                self.assertEqual(
                    second["conversation_state"]["size_foot_length_cm"],
                    expected,
                )
                self.assertFalse(second["conversation_state"]["size_awaiting_foot_length"])
                self.assertNotIn("请确认脚长数值及单位", second["final_answer"])

    def test_width_and_high_instep_followups_retain_length_without_plus_one_rule(self) -> None:
        first = self.run_offline("我脚长24厘米")
        for followup in ("我脚比较宽呢", "脚背高呢", "脚很瘦"):
            with self.subTest(followup=followup):
                second = self.run_offline(followup, state=first["conversation_state"])
                self.assertEqual(second["conversation_state"]["size_foot_length_cm"], 24.0)
                self.assertIn("不同维度", second["final_answer"])
                self.assertNotRegex(second["final_answer"], r"建议(?:您)?大一(?:个)?码|直接大一(?:个)?码|\+1")
                self.assertIn("版型", second["final_answer"])

    def test_usual_size_and_measurement_are_stored_and_discrepancy_is_flagged(self) -> None:
        result = self.run_offline("脚长24但是平时穿41")
        state = result["conversation_state"]
        self.assertEqual(state["size_foot_length_cm"], 24.0)
        self.assertEqual(state["size_usual_shoe_size"], 41.0)
        self.assertRegex(result["final_answer"], r"不一致|差异|重新测量|复测")
        self.assertIn("商品详情页", result["final_answer"])
        self.assertNotRegex(result["final_answer"], r"建议\s*\d{2}\s*码")

        plausible = self.run_offline("脚长24厘米，平时穿38")
        self.assertIn("补充信息", plausible["final_answer"])
        self.assertNotIn("明显不一致", plausible["final_answer"])

    def test_uncertain_and_boundary_like_measurements_are_not_blindly_rounded(self) -> None:
        first = self.run_offline("我穿多大")
        for text in ("23.8", "24.2", "24到24.5之间", "量得不是很准，大概24"):
            with self.subTest(text=text):
                result = self.run_offline(text, state=first["conversation_state"])
                self.assertRegex(result["final_answer"], r"临界|范围|大概|误差|不确定")
                self.assertIn("尺码表", result["final_answer"])
                self.assertNotRegex(result["final_answer"], r"建议\s*\d{2}\s*码")

    def test_unknown_product_fit_never_claims_standard_large_or_small(self) -> None:
        for text in ("这款偏大吗", "这款标准码吗", "这个款要不要大一码", "雨鞋和运动鞋尺码一样吗"):
            with self.subTest(text=text):
                result = self.run_offline(text)
                self.assertEqual(result["query_type"], "size_fit_unknown")
                self.assertIn("没有", result["final_answer"])
                self.assertIn("可靠", result["final_answer"])
                self.assertIn("详情页", result["final_answer"])
                self.assertIn("无法确认", result["final_answer"])
                self.assertNotIn("这款就是", result["final_answer"])

    def test_product_fit_is_used_only_with_trusted_state_source(self) -> None:
        trusted = rag.ConversationState(
            size_product_context="synthetic-product",
            size_product_fit="narrow",
            size_product_fit_source="merchant_product_data",
        ).to_dict()
        result = self.run_offline("这款偏大吗", state=trusted)
        self.assertEqual(result["query_type"], "size_consultation")
        self.assertIn("商家商品资料", result["final_answer"])
        self.assertIn("偏窄", result["final_answer"])

        untrusted = dict(trusted)
        untrusted["size_product_fit_source"] = ""
        result = self.run_offline("这款偏大吗", state=untrusted)
        self.assertEqual(result["query_type"], "size_fit_unknown")

    def test_product_chart_precedes_approved_generic_reference(self) -> None:
        state = rag.ConversationState(
            size_product_context="synthetic-product",
            size_product_size_chart=((23.5, 24.0, "38"),),
            size_product_size_chart_source="merchant_size_chart",
        ).to_dict()
        with mock.patch.object(
            rag,
            "MERCHANT_APPROVED_GENERIC_SIZE_CHART",
            ((23.5, 24.0, "39"),),
        ):
            result = self.run_offline("脚长24厘米穿多大", state=state)
        self.assertIn("当前商品的商家尺码表", result["final_answer"])
        self.assertIn("参考38码", result["final_answer"])
        self.assertNotIn("参考39码", result["final_answer"])
        self.assertIn("初步参考", result["final_answer"])

    def test_fit_followup_retains_measurement_and_usual_size(self) -> None:
        first = self.run_offline("我脚长24厘米，平时38")
        second = self.run_offline("这款偏大吗", state=first["conversation_state"])
        self.assertEqual(second["conversation_state"]["size_foot_length_cm"], 24.0)
        self.assertEqual(second["conversation_state"]["size_usual_shoe_size"], 38.0)
        self.assertIn("脚长24厘米", second["final_answer"])
        self.assertIn("常穿38码", second["final_answer"])
        self.assertIn("无法确认", second["final_answer"])

    def test_size_and_shipping_multi_intent_preserves_both_answers(self) -> None:
        result = self.run_offline(
            "我脚长24厘米穿多大，今天下单什么时候发？",
            business_now=datetime(
                2026,
                8,
                30,
                16,
                59,
                59,
                tzinfo=ZoneInfo("Asia/Shanghai"),
            ),
        )
        self.assertEqual(result["query_type"], "size_and_shipping_policy")
        self.assertIn("脚长24厘米", result["final_answer"])
        self.assertIn("商品详情页", result["final_answer"])
        self.assertIn("亲，现在下单一般今天可以安排发出哦", result["final_answer"])
        self.assertNotIn("当前时间未到17点", result["final_answer"])
        self.assertNotRegex(result["final_answer"], r"建议\s*\d{2}\s*码")

    def test_size_and_return_policy_preserves_rag_policy_facet(self) -> None:
        with (
            mock.patch.object(rag, "retrieve", return_value=[]) as retrieve_call,
            mock.patch.object(
                rag,
                "rerank_retrieved_results",
                return_value=([], rag.CATEGORY_RETURN),
            ) as rerank_call,
            mock.patch.object(
                rag,
                "generate_final_answer",
                return_value=("一般退货流程请以订单页售后入口和当前规则为准。", "synthetic"),
            ),
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "我脚长24厘米穿多大，怎么退货？",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=self.llm_config,
            )

        retrieve_call.assert_called_once()
        rerank_call.assert_called_once()
        provider_call.assert_not_called()
        self.assertEqual(retrieve_call.call_args.args[0], "退款流程是什么")
        self.assertEqual(result["query_type"], "size_and_policy_retrieval")
        self.assertIn("脚长24厘米", result["final_answer"])
        self.assertIn("一般退货流程", result["final_answer"])

    def test_size_with_backend_action_keeps_execution_boundary(self) -> None:
        result = self.run_offline("脚长24厘米穿多大，帮我把这单改成38码")
        self.assertEqual(result["query_type"], "size_and_backend_handoff")
        self.assertTrue(result["requires_backend_api"])
        self.assertIn("脚长24厘米", result["final_answer"])
        self.assertIn("无法", result["final_answer"])
        self.assertNotIn("已改", result["final_answer"])

    def test_size_state_instances_remain_isolated(self) -> None:
        first = self.run_offline("我脚长24厘米")
        second = self.run_offline("我脚长25厘米")
        self.assertEqual(first["conversation_state"]["size_foot_length_cm"], 24.0)
        self.assertEqual(second["conversation_state"]["size_foot_length_cm"], 25.0)
        self.assertNotEqual(first["conversation_state"], second["conversation_state"])


if __name__ == "__main__":
    unittest.main()
