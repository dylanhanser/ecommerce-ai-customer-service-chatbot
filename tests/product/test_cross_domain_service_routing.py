"""Offline regressions for cross-domain product/service request arbitration.

All questions are synthetic.  The suite must not load RAG dependencies,
models, caches, a Provider client, or any external network resource.
"""

from __future__ import annotations

import re
import socket
import sys
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as web_app  # noqa: E402
import demo_catalog as catalog_module  # noqa: E402
from outputs import rag_answer_demo as rag  # noqa: E402


SELECTED_PRODUCT_ID = "DEMO-CASUAL-001"
PUBLIC_CHAT_KEYS = {"final_answer"}


def analyze(question: str, *, state: dict | None = None):
    product = web_app.demo_catalog.lookup(SELECTED_PRODUCT_ID)
    product_analysis = catalog_module.analyze_product_question(question)
    return rag.analyze_customer_request(
        question,
        product_facets=tuple(facet.value for facet in product_analysis.facets),
        conversation_state=state,
        has_selected_product=product is not None,
    )


class CustomerRequestFrameTests(unittest.TestCase):
    def test_cross_domain_matrix_preserves_goal_issue_and_resolution(self) -> None:
        cases = (
            ("不透气能不能退", "return_eligibility", "poor_breathability", {"return"}),
            ("鞋底太硬了可以退吗", "return_eligibility", "uncomfortable_hard_or_heavy", {"return"}),
            ("穿着太重了想退", "return_eligibility", "uncomfortable_hard_or_heavy", {"return"}),
            ("不够保暖能退吗", "return_eligibility", "insufficient_warmth", {"return"}),
            ("走路打滑能不能退", "return_eligibility", "slippery_experience", {"return"}),
            ("磨脚可以退货吗", "return_eligibility", "rubbing_or_pressure", {"return"}),
            ("颜色不好看想退", "return_eligibility", "subjective_dissatisfaction", {"return"}),
            ("穿着不舒服能退吗", "return_eligibility", "uncomfortable_hard_or_heavy", {"return"}),
            ("鞋小了能换吗", "exchange_eligibility", "wrong_size_or_fit", {"exchange"}),
            ("大了一码怎么换", "exchange_eligibility", "wrong_size_or_fit", {"exchange"}),
            ("脚背压得难受可以换大吗", "exchange_eligibility", "rubbing_or_pressure", {"exchange"}),
            ("42码不合适想换43", "exchange_eligibility", "wrong_size_or_fit", {"exchange"}),
            ("鞋子开胶了怎么办", "aftersales_problem_resolution", "sole_separation", {"repair_or_aftersales"}),
            ("鞋底断了能退吗", "return_eligibility", "damage", {"return"}),
            ("穿两天就坏了", "aftersales_problem_resolution", "suspected_quality_problem", {"repair_or_aftersales"}),
            ("发错颜色了怎么办", "aftersales_problem_resolution", "wrong_color_style_or_item", {"correct_wrong_item"}),
            ("寄错尺码了能换吗", "exchange_eligibility", "wrong_color_style_or_item", {"exchange"}),
            ("少发了一双", "aftersales_problem_resolution", "missing_item", {"repair_or_aftersales"}),
            ("页面说透气，实际很闷", "complaint_or_description_mismatch", "description_mismatch", {"repair_or_aftersales"}),
            ("页面说透气，实际很闷，能退吗", "return_eligibility", "description_mismatch", {"return"}),
            ("商品写防滑但我穿着会滑", "complaint_or_description_mismatch", "description_mismatch", {"repair_or_aftersales"}),
            ("退货运费谁出", "general_policy_information", "unknown_reason", set()),
            ("退款什么时候到账", "order_or_refund_status", "unknown_reason", {"check_status"}),
            ("还没发货，能改码或者取消吗", "backend_operation_request", "unknown_reason", {"exchange", "cancel_order"}),
            ("发错颜色了，能补发还是退款", "aftersales_problem_resolution", "wrong_color_style_or_item", {"replace_or_resend", "refund"}),
        )
        for question, goal, issue, resolutions in cases:
            with self.subTest(question=question):
                frame = analyze(question)
                self.assertEqual(frame.primary_goal.value, goal)
                self.assertEqual(frame.issue_type.value, issue)
                self.assertTrue(
                    resolutions.issubset({item.value for item in frame.requested_resolution})
                )
                if resolutions:
                    self.assertNotEqual(frame.route.value, "PRODUCT_ONLY")

    def test_lifecycle_and_usage_are_explicit_and_never_invented(self) -> None:
        cases = (
            ("买了不合适能退吗", "pre_purchase_hypothetical", "unknown"),
            ("还没发货可以取消吗", "ordered_not_shipped", "unknown"),
            ("已经发货了还能退吗", "shipped_in_transit", "unknown"),
            ("刚收到可以退吗", "received_not_tried", "unknown"),
            ("只在家试穿过能退吗", "indoor_try_on_only", "indoor_try_on"),
            ("穿了两天还能退吗", "used_for_a_period", "used_for_multiple_days"),
            ("退货已经申请了什么时候处理", "return_already_submitted", "unknown"),
            ("退款什么时候到账", "refund_processing", "unknown"),
        )
        for question, stage, usage in cases:
            with self.subTest(question=question):
                frame = analyze(question)
                self.assertEqual(frame.lifecycle_stage.value, stage)
                self.assertEqual(frame.usage_state.value, usage)
        unknown = analyze("不透气能不能退")
        self.assertEqual(unknown.lifecycle_stage.value, "unknown")
        self.assertEqual(unknown.usage_state.value, "unknown")

    def test_pure_product_and_policy_routes_remain_distinct(self) -> None:
        product_cases = (
            "这款透气吗",
            "鞋底软不软",
            "冬天暖不暖",
            "舒适性怎么样",
            "这款偏小吗",
            "我脚26穿多大",
            "这款适合爬山吗",
        )
        for question in product_cases:
            with self.subTest(question=question):
                frame = analyze(question)
                self.assertEqual(frame.route.value, "PRODUCT_ONLY")
                self.assertIn(
                    "answer_product_question",
                    {item.value for item in frame.requested_resolution},
                )

        policy_cases = ("可以退货吗", "怎么换货", "退款流程是什么", "退货需要什么条件")
        for question in policy_cases:
            with self.subTest(question=question):
                self.assertEqual(analyze(question).route.value, "POLICY_ONLY")

        prior = analyze("不透气能退吗")
        state = rag.update_customer_request_state(
            None, prior, answer=rag.plan_customer_service_answer(prior)
        )
        changed_topic = analyze("这款还有黑色吗", state=state)
        self.assertEqual(changed_topic.primary_goal.value, "product_information")
        self.assertFalse(changed_topic.inherited_service_context)
        self.assertEqual(changed_topic.route.value, "PRODUCT_ONLY")

    def test_collision_terms_do_not_become_return_or_exchange_actions(self) -> None:
        collisions = (
            "褪色吗",
            "会不会掉色",
            "换季穿合适吗",
            "换气效果怎么样",
            "退烧",
            "后退",
            "退步",
            "换一种颜色看看",
            "这款颜色会褪吗",
        )
        for question in collisions:
            with self.subTest(question=question):
                resolutions = {item.value for item in analyze(question).requested_resolution}
                self.assertNotIn("return", resolutions)
                self.assertNotIn("exchange", resolutions)
        self.assertIn("exchange", {item.value for item in analyze("能换颜色吗").requested_resolution})
        self.assertNotIn("exchange", {item.value for item in analyze("有哪些颜色可选").requested_resolution})
        self.assertIn(
            "return",
            {item.value for item in analyze("换季穿不合适能退吗").requested_resolution},
        )


class CustomerStateEvidenceTests(unittest.TestCase):
    def test_state_transition_matrix_updates_only_explicit_slots(self) -> None:
        cases = (
            ("只在家试穿", "indoor_try_on", None, None),
            ("没脏", None, ("clean", "user_reported_positive"), None),
            ("包装完整", None, None, ("complete", "user_reported_positive")),
            ("吊牌都在", None, None, None),
            ("其实穿出去一天", "worn_outdoors", None, None),
            ("已经穿了两天", "used_for_multiple_days", None, None),
            ("鞋底有点磨损", None, None, None),
        )
        for question, usage, cleanliness, packaging in cases:
            with self.subTest(question=question):
                frame = analyze(question, state={
                    "service_primary_goal": "return_eligibility",
                    "service_requested_resolutions": ("return",),
                })
                if usage:
                    self.assertEqual(frame.usage_state.value, usage)
                    self.assertEqual(frame.usage_provenance.value, "explicit_user_statement")
                if cleanliness:
                    fact = frame.product_condition.cleanliness
                    self.assertEqual((fact.value, fact.status.value), cleanliness)
                    self.assertEqual(fact.provenance.value, "explicit_user_statement")
                if packaging:
                    fact = frame.product_condition.packaging_complete
                    self.assertEqual((fact.value, fact.status.value), packaging)
                if question == "吊牌都在":
                    self.assertEqual(frame.product_condition.tags_complete.value, "present")
                    self.assertEqual(frame.product_condition.shoe_box_complete.value, "unknown")
                if question == "鞋底有点磨损":
                    self.assertEqual(frame.product_condition.outsole_wear.value, "visible_wear")
                    self.assertEqual(frame.product_condition.cleanliness.value, "unknown")

    def test_not_dirty_does_not_infer_other_condition_fields(self) -> None:
        frame = analyze("没脏", state={
            "service_primary_goal": "return_eligibility",
            "service_requested_resolutions": ("return",),
            "service_usage_state": "indoor_try_on",
        })
        condition = frame.product_condition
        self.assertEqual(condition.cleanliness.value, "clean")
        for field_name in (
            "visible_wear",
            "outsole_wear",
            "upper_condition",
            "packaging_complete",
            "shoe_box_complete",
            "tags_complete",
            "accessories_complete",
            "alteration_status",
        ):
            with self.subTest(field=field_name):
                self.assertEqual(getattr(condition, field_name).value, "unknown")
        self.assertNotIn(
            frame.eligibility_state.value,
            {"approved_with_receipt", "rejected_with_receipt"},
        )

    def test_contradictory_followups_replace_only_latest_user_reported_fact(self) -> None:
        state = None
        for question in ("不透气能退吗", "只在家试穿", "其实穿出去一天"):
            frame = analyze(question, state=state)
            answer = rag.plan_customer_service_answer(frame)
            state = rag.update_customer_request_state(state, frame, answer=answer)
        self.assertEqual(frame.usage_state.value, "worn_outdoors")
        self.assertEqual(frame.usage_provenance.value, "explicit_user_statement")
        self.assertNotIn("approved", state["service_eligibility_state"])

        for question in ("没脏", "鞋底有点磨损", "吊牌都在", "吊牌剪了"):
            frame = analyze(question, state=state)
            answer = rag.plan_customer_service_answer(frame)
            state = rag.update_customer_request_state(state, frame, answer=answer)
        self.assertEqual(frame.product_condition.cleanliness.value, "clean")
        self.assertEqual(frame.product_condition.outsole_wear.value, "visible_wear")
        self.assertEqual(frame.product_condition.tags_complete.value, "removed")
        self.assertEqual(frame.product_condition.tags_complete.provenance.value, "explicit_user_statement")

    def test_no_user_fact_or_fact_combination_approves_or_rejects_eligibility(self) -> None:
        facts = (
            "只在家试穿",
            "没脏",
            "鞋盒还在",
            "吊牌都在",
            "没有明显破损",
            "订单页还有售后入口",
        )
        state = {
            "service_primary_goal": "return_eligibility",
            "service_requested_resolutions": ("return",),
        }
        for fact in facts:
            frame = analyze(fact, state=state)
            self.assertNotIn(
                frame.eligibility_state.value,
                {"approved_with_receipt", "rejected_with_receipt"},
            )
            answer = rag.plan_customer_service_answer(frame)
            state = rag.update_customer_request_state(state, frame, answer=answer)
        self.assertNotIn(
            state["service_eligibility_state"],
            {"approved_with_receipt", "rejected_with_receipt"},
        )


class CompositionalUsageStateTests(unittest.TestCase):
    SERVICE_STATE = {
        "service_primary_goal": "return_eligibility",
        "service_requested_resolutions": ("return",),
        "service_issue_type": "poor_breathability",
        "service_pending_clarification": ("usage_state",),
        "service_clarification_count": 1,
    }

    def assert_fact(self, frame, field_name: str, value: str) -> None:
        fact = getattr(frame.usage_evidence, field_name)
        self.assertEqual(fact.value, value)
        if value != "unknown":
            self.assertIn(
                fact.provenance.value,
                {"explicit_user_statement", "derived_inference"},
            )

    def test_indoor_usage_is_composed_from_action_location_and_extent(self) -> None:
        cases = (
            ("就在家里穿过", "indoor_try_on", "yes", "yes", "no", "unknown"),
            ("只在家穿了一下", "indoor_try_on", "yes", "yes", "no", "brief"),
            ("室内试了试", "indoor_try_on", "unknown", "yes", "unknown", "brief"),
            ("在屋里上脚过", "indoor_try_on", "unknown", "yes", "unknown", "unknown"),
            ("房间里套了一下", "indoor_try_on", "unknown", "yes", "unknown", "brief"),
            ("就试了一脚", "indoor_try_on", "unknown", "yes", "unknown", "brief"),
            ("只试了一下", "indoor_try_on", "unknown", "yes", "unknown", "brief"),
            ("没出门，只在家试了下", "indoor_try_on", "unknown", "yes", "no", "brief"),
        )
        for text, coarse, worn, indoor, outdoor, extent in cases:
            with self.subTest(text=text):
                frame = analyze(text, state=self.SERVICE_STATE)
                self.assertEqual(frame.usage_state.value, coarse)
                self.assert_fact(frame, "has_been_worn", worn)
                self.assert_fact(frame, "indoor_use", indoor)
                self.assert_fact(frame, "outdoor_use", outdoor)
                self.assert_fact(frame, "usage_extent", extent)

    def test_outdoor_unused_and_extended_signals_remain_independent(self) -> None:
        outdoor_cases = (
            "穿出去过",
            "穿出门一次",
            "出门穿了一次",
            "在外面走过",
            "穿着下楼了",
            "上班穿了一天",
            "已经穿去逛街了",
        )
        for text in outdoor_cases:
            with self.subTest(text=text):
                frame = analyze(text, state=self.SERVICE_STATE)
                self.assertEqual(frame.usage_state.value, "worn_outdoors")
                self.assert_fact(frame, "outdoor_use", "yes")

        unused_cases = ("没穿", "还没穿", "完全没试过", "没上过脚", "收到后一直没穿")
        for text in unused_cases:
            with self.subTest(text=text):
                frame = analyze(text, state=self.SERVICE_STATE)
                self.assertEqual(frame.usage_state.value, "unused")
                self.assert_fact(frame, "has_been_worn", "no")

        extended_cases = (
            "在家穿了好几天",
            "在家穿了一周",
            "穿了两天",
            "连续穿了一周",
            "每天都在穿",
            "穿着上了几天班",
        )
        for text in extended_cases:
            with self.subTest(text=text):
                frame = analyze(text, state=self.SERVICE_STATE)
                self.assertIn(frame.usage_state.value, {"used_for_multiple_days", "worn_outdoors"})
                self.assert_fact(frame, "usage_extent", "extended")

    def test_negative_outdoor_information_does_not_invent_other_facts(self) -> None:
        cases = (
            ("没穿出去", "unknown", "no"),
            ("没出过门", "unknown", "no"),
            ("只在室内穿", "indoor_try_on", "no"),
            ("没有到外面走过", "unknown", "no"),
        )
        for text, coarse, outdoor in cases:
            with self.subTest(text=text):
                frame = analyze(text, state=self.SERVICE_STATE)
                self.assertEqual(frame.usage_state.value, coarse)
                self.assert_fact(frame, "outdoor_use", outdoor)
                self.assertEqual(frame.product_condition.cleanliness.value, "unknown")
                self.assertEqual(frame.product_condition.packaging_complete.value, "unknown")
                self.assertNotIn(
                    frame.eligibility_state.value,
                    {"approved_with_receipt", "rejected_with_receipt"},
                )

    def test_uncertain_and_contradictory_language_keeps_safe_precedence(self) -> None:
        for text in ("好像穿出去过", "记不清有没有出门穿", "可能下楼穿过一次"):
            with self.subTest(text=text):
                frame = analyze(text, state=self.SERVICE_STATE)
                self.assertIn(frame.usage_state.value, {"unknown", "unclear"})
                self.assert_fact(frame, "statement_confidence", "uncertain")
                self.assertNotEqual(frame.usage_evidence.outdoor_use.value, "no")

        cases = (
            ("只在家穿，后来又穿出门一天", "worn_outdoors", "yes", "extended"),
            ("一开始没穿，昨天穿出去了", "worn_outdoors", "yes", "unknown"),
            ("没出门，不过上班穿了一次", "worn_outdoors", "yes", "brief"),
            ("就在屋里试穿，不对，其实下楼了", "worn_outdoors", "yes", "unknown"),
            ("不是只在家穿，后来穿出去一天", "worn_outdoors", "yes", "extended"),
            ("没在家穿，是在外面试的", "worn_outdoors", "yes", "unknown"),
            ("没穿出去，但在家穿了好几天", "used_for_multiple_days", "no", "extended"),
        )
        for text, coarse, outdoor, extent in cases:
            with self.subTest(text=text):
                frame = analyze(text, state=self.SERVICE_STATE)
                self.assertEqual(frame.usage_state.value, coarse)
                self.assert_fact(frame, "outdoor_use", outdoor)
                self.assert_fact(frame, "usage_extent", extent)

    def test_normalization_keeps_negation_and_colloquial_particles(self) -> None:
        cases = (
            "亲，就在家里穿过。",
            "只、在家试了一下",
            "我就是在屋里穿了穿呀",
            "没出门，在家上脚过",
            "在家试过，但是没穿出去",
        )
        for text in cases:
            with self.subTest(text=text):
                frame = analyze(text, state=self.SERVICE_STATE)
                self.assertEqual(frame.usage_state.value, "indoor_try_on")
                self.assert_fact(frame, "indoor_use", "yes")
                if "没出门" in text or "没穿出去" in text or "就是" in text or "只" in text:
                    self.assert_fact(frame, "outdoor_use", "no")

    def test_state_update_serializes_independent_usage_evidence(self) -> None:
        frame = analyze("没穿出去，但在家穿了好几天", state=self.SERVICE_STATE)
        answer = rag.plan_customer_service_answer(frame)
        state = rag.update_customer_request_state(self.SERVICE_STATE, frame, answer=answer)
        evidence = state["service_usage_evidence"]
        self.assertEqual(evidence["indoor_use"]["value"], "yes")
        self.assertEqual(evidence["outdoor_use"]["value"], "no")
        self.assertEqual(evidence["usage_extent"]["value"], "extended")
        self.assertEqual(evidence["evidence_provenance"], "explicit_user_statement")

    def test_colloquial_indoor_followup_advances_to_packaging_question(self) -> None:
        first = analyze("不透气能退吗")
        state = rag.update_customer_request_state(
            None, first, answer=rag.plan_customer_service_answer(first)
        )
        second = analyze("就在家里穿过", state=state)
        answer = rag.plan_customer_service_answer(second)
        self.assertEqual(second.usage_state.value, "indoor_try_on")
        self.assertIn("packaging_and_tags", second.clarification_slots)
        self.assertIn("只在家里穿过", answer)
        self.assertIn("没有外出使用", answer)
        self.assertIn("鞋盒和吊牌", answer)
        self.assertNotIn("只是室内试穿，还是已经外出", answer)
        self.assertEqual(answer.count("？"), 1)

    def test_standalone_usage_statement_does_not_create_return_context(self) -> None:
        frame = analyze("就在家里穿过")
        self.assertNotEqual(frame.primary_goal.value, "return_eligibility")
        self.assertNotIn("return", {item.value for item in frame.requested_resolution})
        self.assertFalse(frame.inherited_service_context)


class CommercialCostTaxonomyTests(unittest.TestCase):
    def test_cost_type_matrix_is_independent_from_action_issue_and_status(self) -> None:
        cases = (
            ("退货运费谁出", "return_shipping_fee", "general_policy_information"),
            ("换货来回运费谁承担", "exchange_shipping_fee", "general_policy_information"),
            ("发货时的运费退不退", "original_delivery_fee", "general_policy_information"),
            ("退款会扣手续费吗", "refund_processing_fee", "general_policy_information"),
            ("退款怎么少了20块", "refund_amount_deduction", "order_or_refund_status"),
            ("运费险能赔多少", "insurance_reimbursement", "general_policy_information"),
            ("能赔偿多少", "compensation", "general_policy_information"),
            ("退款费用谁承担", "unknown_cost_type", "general_policy_information"),
            ("质量问题退货运费谁出", "return_shipping_fee", "general_policy_information"),
            ("发错货退回去邮费谁承担", "return_shipping_fee", "general_policy_information"),
        )
        for question, cost_type, goal in cases:
            with self.subTest(question=question):
                frame = analyze(question)
                self.assertEqual(frame.cost_type.value, cost_type)
                self.assertEqual(frame.primary_goal.value, goal)

    def test_ambiguous_refund_cost_asks_one_fee_question(self) -> None:
        frame = analyze("退款费用谁承担")
        answer = rag.plan_customer_service_answer(frame)
        self.assertEqual(frame.cost_type.value, "unknown_cost_type")
        self.assertIn("退货寄回的运费", answer)
        self.assertIn("退款时是否会扣手续费", answer)
        self.assertEqual(answer.count("？"), 1)
        self.assertNotRegex(answer, r"无法.*退款|退款进度|卖家承担|买家承担")

    def test_cost_collisions_do_not_invent_shipping_responsibility(self) -> None:
        cases = (
            ("这鞋多少钱", "none"),
            ("有优惠吗", "none"),
            ("免费退货吗", "return_shipping_fee"),
            ("谁出这个价格", "none"),
            ("运费险哪个公司", "insurance_reimbursement"),
        )
        for question, expected in cases:
            with self.subTest(question=question):
                frame = analyze(question)
                self.assertEqual(frame.cost_type.value, expected)

    def test_related_fee_context_may_continue_but_new_cost_type_supersedes(self) -> None:
        first = analyze("不透气能退吗")
        state = rag.update_customer_request_state(
            None, first, answer=rag.plan_customer_service_answer(first)
        )
        fee = analyze("退货运费谁出", state=state)
        self.assertEqual(fee.cost_type.value, "return_shipping_fee")
        state = rag.update_customer_request_state(
            state, fee, answer=rag.plan_customer_service_answer(fee)
        )
        processing = analyze("退款会扣手续费吗", state=state)
        self.assertEqual(processing.cost_type.value, "refund_processing_fee")
        self.assertNotEqual(processing.cost_type, fee.cost_type)


class CustomerRequestAnswerPlanningTests(unittest.TestCase):
    def test_screenshot_case_leads_with_return_boundary_and_one_clarification(self) -> None:
        frame = analyze("不透气能不能退")
        answer = rag.plan_customer_service_answer(frame)
        self.assertTrue(answer.startswith("亲，能否退货"))
        self.assertIn("订单", answer)
        self.assertIn("商品状态", answer)
        self.assertIn("室内试穿", answer)
        self.assertIn("外出穿过", answer)
        self.assertEqual(answer.count("？"), 1)
        self.assertNotRegex(answer[:20], r"PU|鞋面|内里|透气表现")
        self.assertNotRegex(answer, r"一定可以退|一定不能退|已批准|已退款")

    def test_return_template_retains_each_complaint_without_point_fix_leakage(self) -> None:
        cases = (
            ("不透气能不能退", "不透气"),
            ("鞋底太硬了可以退吗", "鞋底太硬"),
            ("穿着太重了想退", "穿着太重"),
            ("不够保暖能退吗", "不够保暖"),
            ("走路打滑能不能退", "走路打滑"),
            ("磨脚可以退货吗", "磨脚"),
            ("颜色不好看想退", "颜色不合心意"),
            ("穿着不舒服能退吗", "穿着不舒服"),
        )
        for question, reason in cases:
            with self.subTest(question=question):
                answer = rag.plan_customer_service_answer(analyze(question))
                self.assertIn(f"“{reason}”", answer)
                if reason != "不透气":
                    self.assertNotIn("“不透气”", answer)
                self.assertNotIn(f"这款鞋确实{reason}", answer)

    def test_service_answers_follow_action_boundary_next_step_then_context(self) -> None:
        cases = (
            ("鞋小了能换吗", ("换货", "订单页"), ("已经换", "已批准")),
            ("鞋子开胶了怎么办", ("售后", "订单页", "核验"), ("确实是质量问题",)),
            ("收到的不是我买的款", ("售后", "订单页", "核验"), ("卖家发错",)),
            ("页面说透气，实际很闷", ("页面", "凭证", "售后"), ("虚假宣传",)),
            ("退款什么时候到账", ("无法查询", "订单页"), ("已到账",)),
            ("质量问题退货运费怎么算", ("运费", "订单页", "核验"), ("卖家承担", "一定免费")),
            ("有运费险吗", ("订单页", "当前店铺规则"), ("中国人保", "PICC")),
            ("发错颜色了，能补发还是退款", ("补发", "退款", "订单页"), ("已经补发", "已退款")),
        )
        for question, required, prohibited in cases:
            with self.subTest(question=question):
                answer = rag.plan_customer_service_answer(analyze(question))
                for marker in required:
                    self.assertIn(marker, answer)
                for marker in prohibited:
                    self.assertNotIn(marker, answer)
                self.assertLessEqual(answer.count("？"), 1)

    def test_final_claim_validator_blocks_commercial_and_fault_conclusions(self) -> None:
        unsafe = (
            "这双鞋一定可以退货。",
            "这双鞋不能退货。",
            "室内试穿没脏，不影响二次销售。",
            "鞋底有磨损，已经影响二次销售。",
            "您的换货已经批准。",
            "您的退货申请已被拒绝。",
            "退款已经完成。",
            "订单已经取消。",
            "已经为您安排补发。",
            "本次退货运费由卖家承担。",
            "退款不会收手续费。",
            "款项会全额退回。",
            "退款会扣20元。",
            "这单有运费险。",
            "运费险会赔12元。",
            "这就是质量问题。",
            "这是商家发错货，责任在商家。",
            "商家存在虚假宣传。",
        )
        for answer in unsafe:
            with self.subTest(answer=answer):
                result = rag.validate_final_answer_claims(answer)
                self.assertTrue(result.rewritten)
                self.assertNotEqual(result.answer, answer)
        safe = "是否符合退货条件需要结合订单规则和商品状态确认。"
        self.assertFalse(rag.validate_final_answer_claims(safe).rewritten)
        safe_boundaries = (
            "需要核验是否符合条件。",
            "不能只根据没脏判断。",
            "订单页无法确认时联系人工客服。",
            "当前无法确认运费责任。",
            "请问您指退货运费还是退款手续费？",
        )
        for answer in safe_boundaries:
            with self.subTest(answer=answer):
                self.assertFalse(rag.validate_final_answer_claims(answer).rewritten)


class CustomerRequestRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = web_app.RAGEngine()
        self.assertTrue(self.engine.select_product("service-session", SELECTED_PRODUCT_ID))

    def forbidden_runtime(self):
        return (
            mock.patch.object(self.engine, "load", side_effect=AssertionError("RAGEngine.load called")),
            mock.patch.object(rag, "retrieve", side_effect=AssertionError("retrieval called")),
            mock.patch.object(rag, "rerank_retrieved_results", side_effect=AssertionError("rerank called")),
            mock.patch.object(rag, "call_deepseek_api", side_effect=AssertionError("Provider called")),
            mock.patch.object(rag, "load_dependencies", side_effect=AssertionError("dependencies loaded")),
            mock.patch.object(rag, "load_or_create_cache", side_effect=AssertionError("cache loaded")),
            mock.patch.object(rag, "load_llm_config", side_effect=AssertionError("Provider client constructed")),
            mock.patch.object(socket, "create_connection", side_effect=AssertionError("network called")),
        )

    def test_selected_product_mixed_requests_preempt_product_answer_and_all_heavy_calls(self) -> None:
        questions = (
            "不透气能不能退",
            "鞋小了能换吗",
            "鞋子开胶了怎么办",
            "发错颜色了怎么办",
            "页面说透气，实际很闷",
            "退款什么时候到账",
            "退货运费谁出",
            "发错颜色了，能补发还是退款",
        )
        for index, question in enumerate(questions):
            with self.subTest(question=question), ExitStack() as stack:
                for patcher in self.forbidden_runtime():
                    stack.enter_context(patcher)
                result = self.engine.chat(question, session_id=f"mixed-{index}")
            self.assertTrue(result["skip_retrieval"])
            self.assertTrue(result["skip_llm"])
            self.assertNotEqual(result["query_type"], "demo_product_answer")
            self.assertNotRegex(result["final_answer"][:20], r"PU|鞋面|内里|透气表现")

    def test_pure_product_still_uses_deterministic_product_path(self) -> None:
        with (
            mock.patch.object(self.engine, "load", side_effect=AssertionError("RAGEngine.load called")),
            mock.patch.object(rag, "retrieve", side_effect=AssertionError("retrieval called")),
            mock.patch.object(rag, "call_deepseek_api", side_effect=AssertionError("Provider called")),
        ):
            result = self.engine.chat("这款透气吗", session_id="service-session")
        self.assertEqual(result["query_type"], "demo_product_answer")
        self.assertIn("透气", result["final_answer"])

    def test_short_followup_uses_bounded_return_state_and_sessions_remain_isolated(self) -> None:
        with mock.patch.object(self.engine, "load", side_effect=AssertionError("RAGEngine.load called")):
            first = self.engine.chat("不透气能不能退", session_id="service-session")
            second = self.engine.chat("只在家试穿过", session_id="service-session")
        self.assertIn("室内试穿", second["final_answer"])
        self.assertIn("订单页", second["final_answer"])
        self.assertNotIn("一定可以退", second["final_answer"])
        self.assertEqual(
            first["conversation_state"]["service_primary_goal"],
            "return_eligibility",
        )
        self.assertIsNone(self.engine._get_conversation_state("independent-session"))

    def test_colloquial_indoor_followup_advances_without_heavy_dependencies(self) -> None:
        with ExitStack() as stack:
            for patcher in self.forbidden_runtime():
                stack.enter_context(patcher)
            first = self.engine.chat("不透气能退吗", session_id="colloquial-indoor")
            second = self.engine.chat("就在家里穿过", session_id="colloquial-indoor")
        self.assertIn("室内试穿", first["final_answer"])
        self.assertIn("只在家里穿过", second["final_answer"])
        self.assertIn("没有外出使用", second["final_answer"])
        self.assertIn("鞋盒和吊牌", second["final_answer"])
        self.assertNotIn("只是室内试穿，还是已经外出", second["final_answer"])
        self.assertEqual(second["final_answer"].count("？"), 1)
        self.assertTrue(second["skip_retrieval"])
        self.assertTrue(second["skip_llm"])

    def test_standalone_usage_statement_is_isolated_and_deterministic(self) -> None:
        with ExitStack() as stack:
            for patcher in self.forbidden_runtime():
                stack.enter_context(patcher)
            result = self.engine.chat("就在家里穿过", session_id="standalone-usage")
        self.assertNotIn("能否退货", result["final_answer"])
        self.assertNotIn("符合退货", result["final_answer"])
        self.assertIn("想咨询", result["final_answer"])
        self.assertTrue(result["skip_retrieval"])
        self.assertTrue(result["skip_llm"])
        self.assertIsNone(self.engine._get_conversation_state("unrelated-session"))

    def test_observed_three_turn_conversation_never_promotes_cleanliness_to_eligibility(self) -> None:
        with ExitStack() as stack:
            for patcher in self.forbidden_runtime():
                stack.enter_context(patcher)
            first = self.engine.chat("不透气能退吗", session_id="service-session")
            second = self.engine.chat("室内试穿", session_id="service-session")
            third = self.engine.chat("没脏", session_id="service-session")
        self.assertIn("室内试穿", second["final_answer"])
        self.assertIn("鞋盒", second["final_answer"])
        self.assertIn("吊牌", second["final_answer"])
        self.assertIn("没有弄脏", third["final_answer"])
        self.assertIn("订单页", third["final_answer"])
        self.assertNotIn("不影响二次销售", third["final_answer"])
        self.assertNotRegex(third["final_answer"], r"是可以申请|可以退|所以符合退货条件")
        state = third["conversation_state"]
        self.assertEqual(
            state["service_product_condition"]["cleanliness"]["value"],
            "clean",
        )
        self.assertEqual(
            state["service_product_condition"]["packaging_complete"]["value"],
            "unknown",
        )
        self.assertNotIn(
            state["service_eligibility_state"],
            {"approved_with_receipt", "rejected_with_receipt"},
        )

    def test_ambiguous_refund_cost_preempts_rag_and_provider(self) -> None:
        with ExitStack() as stack:
            for patcher in self.forbidden_runtime():
                stack.enter_context(patcher)
            result = self.engine.chat("退款费用谁承担", session_id="fee-session")
        self.assertTrue(result["skip_retrieval"])
        self.assertTrue(result["skip_llm"])
        self.assertIn("退货寄回的运费", result["final_answer"])
        self.assertIn("退款时是否会扣手续费", result["final_answer"])
        self.assertEqual(result["final_answer"].count("？"), 1)
        self.assertNotIn("无法直接替您发起", result["final_answer"])

    def test_contradictions_and_topic_transitions_are_bounded(self) -> None:
        with ExitStack() as stack:
            for patcher in self.forbidden_runtime():
                stack.enter_context(patcher)
            self.engine.chat("不透气能退吗", session_id="contradiction")
            self.engine.chat("只在家试穿", session_id="contradiction")
            changed = self.engine.chat("其实穿出去一天", session_id="contradiction")
        self.assertIn("外出", changed["final_answer"])
        self.assertNotRegex(changed["final_answer"], r"可以退|一定不能退|不符合")
        self.assertEqual(
            changed["conversation_state"]["service_usage_state"],
            "worn_outdoors",
        )

        session_id = "topic-reset"
        self.assertTrue(self.engine.select_product(session_id, SELECTED_PRODUCT_ID))
        with ExitStack() as stack:
            for patcher in self.forbidden_runtime():
                stack.enter_context(patcher)
            self.engine.chat("不透气能退吗", session_id=session_id)
            product = self.engine.chat("这款有什么颜色", session_id=session_id)
        self.assertEqual(product["query_type"], "demo_product_answer")
        reset_state = self.engine._get_conversation_state(session_id)
        self.assertTrue(
            reset_state is None or reset_state.get("service_primary_goal") in {"", "none"}
        )

    def test_explicit_color_topic_change_uses_product_fast_path_without_service_inheritance(self) -> None:
        session_id = "explicit-color-reset"
        self.assertTrue(self.engine.select_product(session_id, SELECTED_PRODUCT_ID))
        with ExitStack() as stack:
            for patcher in self.forbidden_runtime():
                stack.enter_context(patcher)
            self.engine.chat("不透气能退吗", session_id=session_id)
            result = self.engine.chat("这款还有黑色吗", session_id=session_id)
        self.assertEqual(result["query_type"], "demo_product_answer")
        self.assertIn("米白", result["final_answer"])
        self.assertIn("深灰", result["final_answer"])
        self.assertNotIn("退货", result["final_answer"])
        state = self.engine._get_conversation_state(session_id)
        self.assertTrue(state is None or state.get("service_primary_goal") in {"", "none"})

    def test_cost_type_changes_across_turns_and_sessions_stay_isolated(self) -> None:
        with ExitStack() as stack:
            for patcher in self.forbidden_runtime():
                stack.enter_context(patcher)
            first = self.engine.chat("退货运费谁出", session_id="cost-transition")
            second = self.engine.chat("退款会扣手续费吗", session_id="cost-transition")
        self.assertEqual(
            first["conversation_state"]["service_cost_type"],
            "return_shipping_fee",
        )
        self.assertEqual(
            second["conversation_state"]["service_cost_type"],
            "refund_processing_fee",
        )
        self.assertIsNone(self.engine._get_conversation_state("other-cost-session"))

    def test_service_followup_variants_remain_bounded_and_contextual(self) -> None:
        followups = (
            ("只在家试穿过", "室内试穿"),
            ("已经穿了两天", "穿着或使用了较长时间"),
            ("还没穿", "尚未穿着"),
            ("鞋盒吊牌都在", "订单页"),
            ("已经提交申请了", "售后处理状态"),
        )
        for index, (followup, marker) in enumerate(followups):
            session_id = f"followup-{index}"
            self.assertTrue(self.engine.select_product(session_id, SELECTED_PRODUCT_ID))
            with mock.patch.object(self.engine, "load", side_effect=AssertionError("RAGEngine.load called")):
                self.engine.chat("不透气能不能退", session_id=session_id)
                result = self.engine.chat(followup, session_id=session_id)
            self.assertIn(marker, result["final_answer"])
            self.assertNotRegex(result["final_answer"], r"一定可以退|已经批准|已退款")

    def test_short_service_objects_keep_existing_clarification(self) -> None:
        expected_fragments = {
            "退款": "退货流程、退款进度",
            "换货": "一般流程、当前处理状态",
        }
        for index, (question, marker) in enumerate(expected_fragments.items()):
            with self.subTest(question=question), mock.patch.object(
                self.engine,
                "load",
                side_effect=AssertionError("RAGEngine.load called"),
            ):
                result = self.engine.chat(question, session_id=f"short-service-{index}")
            self.assertIn(marker, result["final_answer"])
            self.assertEqual(result["final_answer"].count("？"), 1)

    def test_public_chat_response_keeps_existing_whitelist(self) -> None:
        engine = web_app.RAGEngine()
        with (
            mock.patch.object(web_app, "engine", engine),
            mock.patch.object(engine, "load", side_effect=AssertionError("RAGEngine.load called")),
            TestClient(web_app.app) as client,
        ):
            selected = client.post(
                "/api/demo-products/select",
                json={"product_id": SELECTED_PRODUCT_ID},
            )
            response = client.post("/chat", json={"question": "不透气能不能退"})
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), PUBLIC_CHAT_KEYS)
        self.assertTrue(response.json()["final_answer"].startswith("亲，能否退货"))


if __name__ == "__main__":
    unittest.main()
