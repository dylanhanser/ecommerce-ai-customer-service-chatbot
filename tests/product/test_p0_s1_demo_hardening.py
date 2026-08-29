"""Offline product regressions for the P0-S1 demo-hardening slice.

All questions and answers in this module are synthetic. Reviewer identifiers
are retained only as trace metadata because the score exports do not identify
which formal system produced the response under review.
"""

from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

from outputs import rag_answer_demo as rag


REVIEWER_TRACE_METADATA = (
    {"reviewer_case_id": "b3r_cf2f009f12da1da3ad0c7edb", "source_system": "unknown"},
    {"reviewer_case_id": "b3r_b1ed7689a2c480186be724c3", "source_system": "unknown"},
    {"reviewer_case_id": "b3r_95a1ee965670f6ec0d7ace2c", "source_system": "unknown"},
    {"reviewer_case_id": "b3r_9c5ba71ea90168584c7ba343", "source_system": "unknown"},
)


class P0S1DemoHardeningTests(unittest.TestCase):
    def test_standalone_vague_queries_route_to_fixed_clarification(self) -> None:
        expected = "请问您具体想咨询哪方面呢？是尺码、发货、退换货，还是订单/物流状态？"
        cases = (
            "怎么办",
            "怎么办啊",
            "怎么办呢",
            "咋办",
            "咋整",
            "咋整啊",
            "那咋整",
            "这咋整",
            "该咋整",
            "我该咋整",
            "怎么弄",
            "怎么整",
            "怎么处理",
            "如何处理",
            "现在怎么办",
            "那怎么办",
            "我该怎么办",
            "这该怎么弄",
            "怎么了",
            "有问题",
            "帮帮我",
            "  怎么办？！  ",
        )
        for question in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertIs(decision.route, rag.AnswerRoute.CLARIFY_THEN_ANSWER)
                self.assertEqual(decision.reason, "standalone_vague_query")
                self.assertEqual(rag.answer_for_p0_s1_route(decision), expected)

    def test_standalone_vague_guard_skips_retrieval_rerank_and_provider(self) -> None:
        llm_config = rag.LLMConfig(api_key="synthetic-key", base_url="", model="offline", client=mock.Mock())
        with (
            mock.patch.object(rag, "retrieve") as retrieve_call,
            mock.patch.object(rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "怎么办",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=llm_config,
            )

        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.assertEqual(result["answer_route"], rag.AnswerRoute.CLARIFY_THEN_ANSWER.value)
        self.assertEqual(result["answer_route_reason"], "standalone_vague_query")
        self.assertTrue(result["skip_retrieval"])
        self.assertTrue(result["skip_llm"])
        self.assertEqual(
            result["final_answer"],
            "请问您具体想咨询哪方面呢？是尺码、发货、退换货，还是订单/物流状态？",
        )
        self.assertNotIn("39码", result["final_answer"])

    def test_standalone_zazheng_guard_skips_rag_and_guessing(self) -> None:
        expected = "请问您具体想咨询哪方面呢？是尺码、发货、退换货，还是订单/物流状态？"
        llm_config = rag.LLMConfig(
            api_key="synthetic-key",
            base_url="",
            model="offline",
            client=mock.Mock(),
        )
        with (
            mock.patch.object(rag, "retrieve") as retrieve_call,
            mock.patch.object(rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "咋整",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=llm_config,
            )

        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.assertEqual(result["answer_route"], rag.AnswerRoute.CLARIFY_THEN_ANSWER.value)
        self.assertEqual(result["answer_route_reason"], "standalone_vague_query")
        self.assertTrue(result["skip_retrieval"])
        self.assertTrue(result["skip_llm"])
        self.assertEqual(result["final_answer"], expected)
        for guessed_content in ("货号", "快递面单", "39码"):
            self.assertNotIn(guessed_content, result["final_answer"])

    def test_specific_questions_are_not_misclassified_as_standalone_vague(self) -> None:
        cases = (
            "怎么退货",
            "怎么换货",
            "怎么发货",
            "怎么查物流",
            "怎么选尺码",
            "鞋子开胶了怎么办",
            "鞋子开胶了咋整",
            "退货咋整",
            "物流咋查",
            "42码咋选",
            "鞋子偏大怎么办",
        )
        for question in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertNotEqual(decision.reason, "standalone_vague_query")

    def test_vague_short_followup_keeps_explicit_previous_context(self) -> None:
        decision = rag.decide_p0_s1_answer_route(
            "怎么办",
            has_conversation_context=True,
        )
        followup = rag.resolve_followup_context(
            "怎么办",
            previous_user_query="鞋子开胶了",
            previous_assistant_answer="请说明商品情况。",
        )

        self.assertIsNot(decision.route, rag.AnswerRoute.CLARIFY_THEN_ANSWER)
        self.assertTrue(followup.is_followup_query)
        self.assertIn("鞋子开胶了", followup.retrieval_query)
        self.assertIn("怎么办", followup.retrieval_query)

    def test_standalone_ambiguous_delivery_location_asks_targeted_question(self) -> None:
        expected = "请问您是下单时收货地址填错了，还是物流显示包裹送错了地点？"
        cases = (
            "发错位置了",
            "发错地方了",
            "寄错位置了",
            "寄错地方了",
            "送错位置了",
            "送错地方了",
            "送错地方了啊",
            "  发错位置了？！  ",
        )
        for question in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertIs(decision.route, rag.AnswerRoute.CLARIFY_THEN_ANSWER)
                self.assertEqual(
                    decision.reason,
                    "standalone_ambiguous_delivery_location",
                )
                self.assertEqual(rag.answer_for_p0_s1_route(decision), expected)

    def test_standalone_ambiguous_delivery_location_skips_rag(self) -> None:
        expected = "请问您是下单时收货地址填错了，还是物流显示包裹送错了地点？"
        llm_config = rag.LLMConfig(
            api_key="synthetic-key",
            base_url="",
            model="offline",
            client=mock.Mock(),
        )
        with (
            mock.patch.object(rag, "retrieve") as retrieve_call,
            mock.patch.object(rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "发错位置了",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=llm_config,
            )

        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.assertEqual(result["answer_route"], rag.AnswerRoute.CLARIFY_THEN_ANSWER.value)
        self.assertEqual(
            result["answer_route_reason"],
            "standalone_ambiguous_delivery_location",
        )
        self.assertTrue(result["skip_retrieval"])
        self.assertTrue(result["skip_llm"])
        self.assertEqual(result["final_answer"], expected)
        for wrong_content in ("实物", "鞋盒", "白色标签", "拍照"):
            self.assertNotIn(wrong_content, result["final_answer"])

    def test_ambiguous_delivery_location_guard_preserves_specific_objects(self) -> None:
        cases = (
            "发错货了",
            "发错款式了",
            "鞋子发错码了",
            "发错颜色了",
            "收货地址填错了",
            "物流显示送错地方了",
        )
        for question in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertNotEqual(
                    decision.reason,
                    "standalone_ambiguous_delivery_location",
                )
                self.assertNotEqual(
                    rag.answer_for_p0_s1_route(decision),
                    "请问您是下单时收货地址填错了，还是物流显示包裹送错了地点？",
                )

        contextual = rag.decide_p0_s1_answer_route(
            "发错位置了",
            has_conversation_context=True,
        )
        self.assertNotEqual(
            contextual.reason,
            "standalone_ambiguous_delivery_location",
        )

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

    def test_foot_length_size_guidance_supports_explicit_units(self) -> None:
        expected = (
            "已记录脚长26厘米。当前可用资料中没有可验证的脚长与鞋码对照表，"
            "暂时无法可靠推荐具体码数；请以当前商品详情页尺码表和版型说明为准。"
        )
        cases = (
            "我的脚长26厘米，适合穿多少码？",
            "脚长26cm穿几码？",
            "脚长260毫米怎么选？",
            "260mm脚长适合多大码？",
        )
        for question in cases:
            with self.subTest(question=question):
                self.assertEqual(rag.answer_for_foot_length_size_query(question), expected)

    def test_foot_length_size_guidance_rejects_ambiguous_or_implausible_values(
        self,
    ) -> None:
        unrelated_cases = (
            "我平时穿42码",
            "42码适合多长的脚？",
            "这个鞋偏大吗？",
            "脚长多少应该怎么量？",
        )
        for question in unrelated_cases:
            with self.subTest(question=question):
                self.assertIsNone(rag.answer_for_foot_length_size_query(question))

        clarification_cases = (
            "脚长2厘米适合穿多少码？",
            "脚长100厘米适合穿多少码？",
        )
        for question in clarification_cases:
            with self.subTest(question=question):
                answer = rag.answer_for_foot_length_size_query(question)
                self.assertIsNotNone(answer)
                self.assertRegex(answer or "", r"确认|检查|范围")
                self.assertNotRegex(answer or "", r"建议\d{2}码")

        conservative_cases = (
            "脚长26适合穿多少码？",
            "脚长25厘米到26厘米适合穿多少码？",
        )
        for question in conservative_cases:
            with self.subTest(question=question):
                answer = rag.answer_for_foot_length_size_query(question)
                self.assertIsNotNone(answer)
                self.assertIn("尺码表", answer)
                self.assertNotRegex(answer or "", r"建议\d{2}码")

    def test_foot_length_runtime_is_deterministic_and_skips_rag(self) -> None:
        llm_config = rag.LLMConfig(
            api_key="synthetic-key",
            base_url="",
            model="offline",
            client=mock.Mock(),
        )
        with (
            mock.patch.object(rag, "retrieve") as retrieve_call,
            mock.patch.object(rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "我的脚长26厘米，适合穿多少码的鞋？",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=llm_config,
            )

        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.assertEqual(result["answer_route"], rag.AnswerRoute.DIRECT_ANSWER.value)
        self.assertEqual(result["query_type"], "size_consultation")
        self.assertFalse(result["requires_backend_api"])
        self.assertTrue(result["skip_retrieval"])
        self.assertTrue(result["skip_llm"])
        self.assertEqual(
            result["final_answer"],
            "已记录脚长26厘米。当前可用资料中没有可验证的脚长与鞋码对照表，"
            "暂时无法可靠推荐具体码数。请以当前商品详情页尺码表和版型说明为准。",
        )
        self.assertEqual(result["conversation_state"]["size_foot_length_cm"], 26.0)

    def test_prospective_shipping_questions_route_to_policy(self) -> None:
        cases = (
            "我现在下单什么时候发货？",
            "我现在下单什么时候能发货？",
            "我现在下单大概什么时候可以发货？",
            "今天下单什么时候发？",
            "今天下单什么时候能发？",
            "现在拍多久发货？",
            "17点前下单今天能发吗？",
            "几点前下单可以当天发货？",
        )
        for question in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertIs(decision.route, rag.AnswerRoute.DIRECT_ANSWER)
                self.assertEqual(decision.domain, "shipping")
                self.assertTrue(decision.has_policy_facet)
                self.assertFalse(decision.needs_realtime_status)
                self.assertFalse(decision.needs_backend_action)
                self.assertEqual(decision.reason, "prospective_shipping_policy")

    def test_existing_order_shipping_questions_remain_backend_required(self) -> None:
        cases = (
            "我已经下单了，什么时候发货？",
            "我的订单什么时候发？",
            "订单怎么还没发货？",
            "帮我查一下什么时候发货",
            "订单已经付款了，今天能发吗？",
        )
        for question in cases:
            with self.subTest(question=question):
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertIs(decision.route, rag.AnswerRoute.FULL_HANDOFF)
                self.assertEqual(decision.domain, "shipping")
                self.assertTrue(decision.needs_realtime_status)
                self.assertIn("无法查询", rag.answer_for_p0_s1_route(decision))

    def test_prospective_shipping_runtime_uses_canonical_policy_without_rag(self) -> None:
        expected = (
            "亲，现在下单一般今天可以安排发出哦，具体以订单页显示的预计发货时间为准；"
            "预售款按商品详情页标注的时间发货。"
        )
        llm_config = rag.LLMConfig(
            api_key="synthetic-key",
            base_url="",
            model="offline",
            client=mock.Mock(),
        )
        with (
            mock.patch.object(rag, "retrieve") as retrieve_call,
            mock.patch.object(rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "我现在下单什么时候能发货",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=llm_config,
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

        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.assertEqual(result["answer_route"], rag.AnswerRoute.DIRECT_ANSWER.value)
        self.assertEqual(result["answer_route_reason"], "prospective_shipping_policy")
        self.assertEqual(result["query_type"], "prospective_shipping_policy")
        self.assertFalse(result["requires_backend_api"])
        self.assertTrue(result["skip_retrieval"])
        self.assertTrue(result["skip_llm"])
        self.assertEqual(result["final_answer"], expected)
        self.assertNotIn("无法查询当前订单", result["final_answer"])
        self.assertNotRegex(result["final_answer"], r"一定|肯定|保证今天发货")
        self.assertNotIn("当前时间未到17点", result["final_answer"])

    def test_prospective_dispatch_policy_uses_exclusive_shanghai_cutoff(self) -> None:
        shanghai = ZoneInfo("Asia/Shanghai")
        cases = (
            (
                datetime(2026, 8, 30, 16, 59, 59, tzinfo=shanghai),
                "亲，现在下单一般今天可以安排发出哦，具体以订单页显示的预计发货时间为准；"
                "预售款按商品详情页标注的时间发货。",
            ),
            (
                datetime(2026, 8, 30, 17, 0, 0, tzinfo=shanghai),
                "亲，现在下单今天可能来不及发出了，一般会安排到下一批次哦。"
                "具体以订单页显示的预计发货时间为准；预售款按商品详情页标注的时间发货。",
            ),
            (
                datetime(2026, 8, 30, 17, 0, 1, tzinfo=shanghai),
                "亲，现在下单今天可能来不及发出了，一般会安排到下一批次哦。"
                "具体以订单页显示的预计发货时间为准；预售款按商品详情页标注的时间发货。",
            ),
        )
        for now, expected in cases:
            with self.subTest(now=now.isoformat()):
                answer = rag.answer_for_prospective_shipping_policy(
                    "我现在下单什么时候能发货",
                    business_now=now,
                )
                self.assertEqual(answer, expected)
                self.assertNotRegex(answer or "", r"一定|肯定|保证今天发货")
                self.assertNotRegex(answer or "", r"当前时间未到17点|当前时间已过17点|时间检测结果")

    def test_prospective_dispatch_policy_converts_utc_to_shanghai(self) -> None:
        before_cutoff_utc = datetime(2026, 8, 30, 8, 59, 59, tzinfo=timezone.utc)
        at_cutoff_utc = datetime(2026, 8, 30, 9, 0, 0, tzinfo=timezone.utc)

        before = rag.answer_for_prospective_shipping_policy(
            "现在拍今天能发吗",
            business_now=before_cutoff_utc,
        )
        at_cutoff = rag.answer_for_prospective_shipping_policy(
            "今天下单能当天发吗",
            business_now=at_cutoff_utc,
        )

        self.assertEqual(
            before,
            "亲，现在下单一般今天可以安排发出哦，具体以订单页显示的预计发货时间为准；"
            "预售款按商品详情页标注的时间发货。",
        )
        self.assertEqual(
            at_cutoff,
            "亲，现在下单今天可能来不及发出了，一般会安排到下一批次哦。"
            "具体以订单页显示的预计发货时间为准；预售款按商品详情页标注的时间发货。",
        )

    def test_explicit_cutoff_question_uses_fixed_customer_service_template(self) -> None:
        expected = (
            "亲，正常情况下17点前下单当天可以安排发出，17点后会安排到下一批次哦。"
            "具体以订单页显示为准；预售款按商品详情页标注的时间发货。"
        )
        for hour in (16, 18):
            with self.subTest(hour=hour):
                answer = rag.answer_for_prospective_shipping_policy(
                    "几点前下单可以当天发货",
                    business_now=datetime(
                        2026,
                        8,
                        30,
                        hour,
                        0,
                        0,
                        tzinfo=ZoneInfo("Asia/Shanghai"),
                    ),
                )
                self.assertEqual(answer, expected)

    def test_business_clock_excludes_existing_orders_and_preorders(self) -> None:
        shanghai_now = datetime(2026, 8, 30, 16, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        for question in (
            "我已经下单了，今天能发吗？",
            "我的订单什么时候发？",
            "订单怎么还没发货？",
        ):
            with self.subTest(existing_order=question):
                self.assertIsNone(
                    rag.answer_for_prospective_shipping_policy(
                        question,
                        business_now=shanghai_now,
                    )
                )
                decision = rag.decide_p0_s1_answer_route(question)
                self.assertIs(decision.route, rag.AnswerRoute.FULL_HANDOFF)

        preorder = rag.answer_for_prospective_shipping_policy(
            "这个预售款我现在下单什么时候发货？",
            business_now=shanghai_now,
        )
        self.assertIn("预售商品不适用", preorder or "")
        self.assertIn("预售说明", preorder or "")
        self.assertNotIn("今天安排发货", preorder or "")

    def test_business_time_runtime_skips_rag_and_provider(self) -> None:
        llm_config = rag.LLMConfig(
            api_key="synthetic-key",
            base_url="",
            model="offline",
            client=mock.Mock(),
        )
        with (
            mock.patch.object(rag, "retrieve") as retrieve_call,
            mock.patch.object(rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(rag, "call_deepseek_api") as provider_call,
        ):
            result = rag.run_rag_query(
                "现在拍今天能发吗",
                corpus=None,
                embeddings=None,
                embedding_model=None,
                top_k=1,
                cosine_similarity=None,
                low_confidence_threshold=0.55,
                llm_config=llm_config,
                business_now=datetime(
                    2026,
                    8,
                    30,
                    17,
                    0,
                    0,
                    tzinfo=ZoneInfo("Asia/Shanghai"),
                ),
            )

        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.assertEqual(result["query_type"], "prospective_shipping_policy")
        self.assertEqual(
            result["final_answer"],
            "亲，现在下单今天可能来不及发出了，一般会安排到下一批次哦。"
            "具体以订单页显示的预计发货时间为准；预售款按商品详情页标注的时间发货。",
        )

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
