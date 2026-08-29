"""Offline regressions for the isolated synthetic demo-product catalog.

The fixtures are fictional.  These tests must not load embeddings, create a
Provider client, read ``.env``, fetch URLs, or write runtime/evaluation assets.
"""

from __future__ import annotations

import builtins
from contextlib import ExitStack
from datetime import datetime
import json
import pickle
import re
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock
import urllib.request
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app as web_app  # noqa: E402
import demo_catalog as catalog_module  # noqa: E402
from demo_catalog import (  # noqa: E402
    CATALOG_PATH,
    EXPECTED_PRODUCT_IDS,
    PUBLIC_PRODUCT_FIELDS,
    CatalogValidationError,
    answer_product_question,
    extract_demo_product_link,
    load_catalog,
    validate_catalog_payload,
)


SHANGHAI_BEFORE_CUTOFF = datetime(
    2026,
    8,
    30,
    16,
    59,
    59,
    tzinfo=ZoneInfo("Asia/Shanghai"),
)

EXPECTED_PRIMARY_IMAGE_URLS = {
    product_id: f"/static/demo-products/{product_id}/cover.webp"
    for product_id in EXPECTED_PRODUCT_IDS
}
ACCEPTED_IMAGE_CONTENT_TYPES = {
    "image/avif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


class CatalogValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG_PATH)

    def test_catalog_has_exactly_six_expected_synthetic_products(self) -> None:
        self.assertEqual(tuple(self.catalog.product_ids), EXPECTED_PRODUCT_IDS)
        self.assertEqual(len(self.catalog.products), 6)
        self.assertEqual(len(set(self.catalog.product_ids)), 6)
        for product in self.catalog.products:
            self.assertEqual(product["data_classification"], "synthetic_demo_data")

    def test_public_display_names_are_neutral_and_natural(self) -> None:
        expected_names = {
            "DEMO-CASUAL-001": "基础款日常休闲鞋",
            "DEMO-RUN-002": "复古拼色运动休闲鞋",
            "DEMO-WIDE-003": "宽楦魔术贴运动鞋",
            "DEMO-WORK-004": "防滑闭口工作鞋",
            "DEMO-RAIN-005": "轻便防泼水休闲鞋",
            "DEMO-PREORDER-006": "加绒保暖冬季鞋（预售款）",
        }
        actual_names = {
            product["product_id"]: product["identity"]["name"]
            for product in self.catalog.products
        }
        self.assertEqual(actual_names, expected_names)

    def test_required_fields_and_monotonic_charts_are_validated(self) -> None:
        required = {
            "product_id",
            "data_classification",
            "identity",
            "pricing",
            "construction",
            "style",
            "functions",
            "sizing",
            "sale",
            "variants",
            "media",
        }
        for product in self.catalog.products:
            self.assertTrue(required.issubset(product))
            chart = product["sizing"]["size_chart"]
            lengths = [row["foot_length_cm"] for row in chart]
            sizes = [row["recommended_size"] for row in chart]
            self.assertEqual(lengths, sorted(lengths))
            self.assertEqual(sizes, sorted(sizes))
            if product["sale"]["sale_type"] == "preorder":
                self.assertTrue(product["sale"]["preorder_note"])

    def test_standard_and_smaller_fit_products_use_explicit_distinct_charts(self) -> None:
        standard = self.catalog.lookup("DEMO-CASUAL-001")
        running = self.catalog.lookup("DEMO-RUN-002")
        standard_chart = {
            row["foot_length_cm"]: row["recommended_size"]
            for row in standard["sizing"]["size_chart"]
        }
        running_chart = {
            row["foot_length_cm"]: row["recommended_size"]
            for row in running["sizing"]["size_chart"]
        }
        self.assertEqual(standard_chart[26.0], 42)
        self.assertEqual(running_chart[26.0], 43)
        self.assertNotEqual(running_chart[26.0], standard_chart[26.0])

    def test_validation_rejects_duplicates_missing_fields_and_non_monotonic_charts(self) -> None:
        source = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

        duplicate = json.loads(json.dumps(source))
        duplicate["products"][1]["product_id"] = duplicate["products"][0]["product_id"]
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(duplicate)

        missing = json.loads(json.dumps(source))
        del missing["products"][0]["construction"]["upper_material"]
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(missing)

        non_monotonic = json.loads(json.dumps(source))
        non_monotonic["products"][0]["sizing"]["size_chart"][2]["recommended_size"] = 39
        with self.assertRaises(CatalogValidationError):
            validate_catalog_payload(non_monotonic)

    def test_catalog_contains_no_customer_order_price_or_real_brand_fields(self) -> None:
        raw = CATALOG_PATH.read_text(encoding="utf-8").casefold()
        for forbidden in (
            "customer_id",
            "order_id",
            "phone",
            "address",
            "nike",
            "adidas",
            "warrior",
            "回力",
            "中国人保",
            "picc",
        ):
            self.assertNotIn(forbidden, raw)
        self.assertEqual(raw.count('"classification": "synthetic_demo_price"'), 6)


class CatalogLookupAndLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG_PATH)

    def test_lookup_accepts_only_validated_exact_product_ids(self) -> None:
        self.assertEqual(
            self.catalog.lookup("DEMO-WORK-004")["product_id"],
            "DEMO-WORK-004",
        )
        for invalid in (
            "demo-work-004",
            "DEMO-UNKNOWN-999",
            "../../.env",
            "https://example.invalid/products/DEMO-WORK-004",
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(self.catalog.lookup(invalid))

    def test_public_projection_is_allowlisted_and_uses_relative_product_path(self) -> None:
        public = self.catalog.public_product("DEMO-RAIN-005")
        self.assertEqual(set(public), PUBLIC_PRODUCT_FIELDS)
        self.assertEqual(public["product_path"], "/products/DEMO-RAIN-005")
        self.assertNotIn("session", json.dumps(public).casefold())

    def test_pasted_link_parser_accepts_path_format_without_fetching(self) -> None:
        known = extract_demo_product_link(
            "https://chat.example/products/DEMO-RUN-002 这款26厘米穿多大？",
            self.catalog,
        )
        self.assertTrue(known.matched)
        self.assertEqual(known.product_id, "DEMO-RUN-002")
        self.assertTrue(known.is_known)

        unknown = extract_demo_product_link(
            "https://chat.example/products/DEMO-UNKNOWN-999 这款怎么样？",
            self.catalog,
        )
        self.assertTrue(unknown.matched)
        self.assertFalse(unknown.is_known)

        external = extract_demo_product_link(
            "https://169.254.169.254/latest/meta-data 这款怎么样？",
            self.catalog,
        )
        self.assertFalse(external.matched)

    def test_catalog_service_contains_no_network_or_arbitrary_url_fetcher(self) -> None:
        source = (ROOT / "demo_catalog.py").read_text(encoding="utf-8").casefold()
        for forbidden in (
            "requests.",
            "httpx.",
            "urllib.request",
            "urlopen",
            "socket.",
        ):
            self.assertNotIn(forbidden, source)


class ProductAnswerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG_PATH)

    def answer(self, product_id: str, question: str) -> str | None:
        return answer_product_question(
            question,
            self.catalog.lookup(product_id),
            business_now=SHANGHAI_BEFORE_CUTOFF,
        )

    def test_standard_and_smaller_fit_size_answers_use_product_charts(self) -> None:
        standard = self.answer("DEMO-CASUAL-001", "我的脚长26厘米，这款穿多少码？")
        running = self.answer("DEMO-RUN-002", "我的脚长26厘米，这款穿多少码？")
        self.assertIn("42码", standard)
        self.assertIn("商品详情", standard)
        self.assertIn("43码", running)
        self.assertIn("偏小", running)
        self.assertNotEqual(standard, running)

    def test_implicit_foot_lengths_require_marker_and_size_intent(self) -> None:
        positive_cases = (
            "我脚26,这款鞋应该选多大码",
            "我脚26这款穿几码",
            "脚26应该选多大",
            "脚长26.5这款穿多大",
            "脚长260这款选几码",
            "足长260，应该买多大码",
            "我脚是26的，这双怎么选",
            "26厘米这款穿多大",
        )
        for question in positive_cases:
            with self.subTest(question=question):
                answer = self.answer("DEMO-CASUAL-001", question)
                expected_size = "43码" if "26.5" in question else "42码"
                self.assertIn(expected_size, answer)
                self.assertIn("商品详情页", answer)

        smaller_fit = self.answer("DEMO-RUN-002", "我脚26这款穿几码")
        self.assertIn("43码", smaller_fit)
        self.assertIn("偏小", smaller_fit)

    def test_unrelated_numbers_are_not_inferred_as_foot_length(self) -> None:
        counterexamples = (
            "我平时穿42码",
            "这款有42码吗",
            "26号下单",
            "订单号是260123",
            "预算260",
            "我买2双",
            "身高170体重60",
            "这款26号有货吗",
        )
        for question in counterexamples:
            with self.subTest(question=question):
                answer = self.answer("DEMO-CASUAL-001", question)
                if answer is not None:
                    self.assertNotIn("脚长", answer)
                    self.assertNotRegex(answer, r"建议选\d+码")

        ambiguous = self.answer("DEMO-CASUAL-001", "我26，这款穿多大")
        self.assertIn("26", ambiguous)
        self.assertIn("脚长26厘米", ambiguous)
        self.assertIn("？", ambiguous)

    def test_selected_product_size_tone_uses_one_grounded_fit_and_detail_note(self) -> None:
        cases = (
            ("DEMO-CASUAL-001", "基础款日常休闲鞋", "42码", "标准版型"),
            ("DEMO-RUN-002", "复古拼色运动休闲鞋", "43码", "版型偏小"),
            ("DEMO-WIDE-003", "宽楦魔术贴运动鞋", "42码", "宽楦友好版型"),
        )
        mechanical_phrases = (
            "对应42码",
            "本商品尺码表",
            "根据检测结果",
            "按这款演示商品自己的尺码表",
            "具体请再核对演示商品详情",
        )
        for product_id, name, size, fit in cases:
            with self.subTest(product_id=product_id):
                answer = self.answer(product_id, "我脚26,这款鞋应该选多大码")
                self.assertIn(size, answer)
                self.assertIn(name, answer)
                self.assertIn("亲，", answer)
                self.assertIn(fit, answer)
                self.assertEqual(answer.count("商品详情页"), 1)
                self.assertLessEqual(answer.count("。"), 2)
                for phrase in mechanical_phrases:
                    self.assertNotIn(phrase, answer)

    def test_attributes_are_answered_only_from_selected_product(self) -> None:
        cases = (
            ("DEMO-WORK-004", "这款防滑吗？", "防滑"),
            ("DEMO-RAIN-005", "这款防水吗？", "小雨"),
            ("DEMO-CASUAL-001", "鞋面什么材质？", "PU"),
            ("DEMO-CASUAL-001", "鞋底什么材质？", "橡胶"),
            ("DEMO-WIDE-003", "有什么颜色？", "雾灰"),
            ("DEMO-WIDE-003", "有哪些尺码？", "40"),
            ("DEMO-RUN-002", "这款偏大偏小？", "偏小"),
        )
        for product_id, question, expected in cases:
            with self.subTest(product_id=product_id, question=question):
                self.assertIn(expected, self.answer(product_id, question))

    def test_preorder_product_excludes_normal_same_day_cutoff(self) -> None:
        answer = self.answer("DEMO-PREORDER-006", "现在下单今天能发吗？")
        preorder_note = self.catalog.lookup("DEMO-PREORDER-006")["sale"]["preorder_note"]
        self.assertIn(preorder_note, answer)
        self.assertNotIn("今天可以安排发出", answer)
        self.assertNotIn("17点前", answer)

    def test_existing_order_shipping_is_not_consumed_by_product_clock_or_preorder_note(self) -> None:
        for product_id in ("DEMO-CASUAL-001", "DEMO-PREORDER-006"):
            with self.subTest(product_id=product_id):
                self.assertIsNone(
                    self.answer(product_id, "我已经下单了，今天能发吗？")
                )

    def test_in_stock_product_can_use_safe_general_shipping_window(self) -> None:
        answer = self.answer("DEMO-CASUAL-001", "现在下单今天能发吗？")
        self.assertIn("一般今天可以安排发出", answer)
        self.assertIn("订单页", answer)

    def test_unhandled_or_missing_attribute_does_not_invent_a_claim(self) -> None:
        product = dict(self.catalog.lookup("DEMO-WORK-004"))
        product["functions"]["water_resistance"]["description"] = ""
        answer = answer_product_question("这款防水吗？", product)
        self.assertIn("没有标注", answer)
        self.assertIn("雨天穿着能力", answer)
        self.assertNotIn("防水", answer.replace("防水信息", ""))


class ProductSemanticAnalysisAndPlanningTests(unittest.TestCase):
    """Table-driven coverage for semantic analysis, evidence, and planning."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG_PATH)

    def answer(self, product_id: str, question: str) -> str | None:
        return answer_product_question(
            question,
            self.catalog.lookup(product_id),
            business_now=SHANGHAI_BEFORE_CUTOFF,
        )

    def test_semantic_matrix_collects_facets_and_separates_question_mode(self) -> None:
        F = catalog_module.ProductFacet
        M = catalog_module.ProductQuestionMode
        cases = (
            ("鞋底是什么材质", {F.SOLE_MATERIAL}, M.FACTUAL_LOOKUP),
            ("这双鞋舒适性怎么样", {F.GENERAL_COMFORT}, M.SUBJECTIVE_ASSESSMENT),
            ("上班久站舒服吗", {F.GENERAL_COMFORT, F.LONG_WEAR_COMFORT, F.USE_SCENARIO}, M.COMPARISON_OR_MULTI_FACET),
            ("脚背会不会压", {F.WIDTH_AND_INSTEP, F.RUBBING_OR_PRESSURE}, M.RISK_OR_LIMITATION),
            ("鞋底软吗，缓震怎么样", {F.SOLE_SOFTNESS, F.CUSHIONING}, M.COMPARISON_OR_MULTI_FACET),
            ("夏天穿会不会闷脚", {F.BREATHABILITY, F.USE_SCENARIO}, M.COMPARISON_OR_MULTI_FACET),
            ("冬天暖不暖，里面有绒吗", {F.WARMTH, F.LINING_MATERIAL, F.USE_SCENARIO}, M.COMPARISON_OR_MULTI_FACET),
            ("这鞋重不重", {F.WEIGHT}, M.SUBJECTIVE_ASSESSMENT),
            ("耐不耐穿", {F.DURABILITY_OR_QUALITY}, M.RISK_OR_LIMITATION),
            ("适合通勤吗", {F.USE_SCENARIO}, M.SUITABILITY_ASSESSMENT),
            ("下雨爬山会不会滑", {F.RAIN_USE, F.SLIP_RESISTANCE, F.USE_SCENARIO}, M.COMPARISON_OR_MULTI_FACET),
            ("这个好吗", set(), M.AMBIGUOUS_CLARIFICATION),
        )
        for question, expected_facets, expected_mode in cases:
            with self.subTest(question=question):
                analysis = catalog_module.analyze_product_question(question)
                self.assertTrue(expected_facets.issubset(set(analysis.facets)))
                self.assertEqual(analysis.mode, expected_mode)

    def test_all_six_products_use_grounded_behavior_families(self) -> None:
        cases = (
            ("DEMO-CASUAL-001", "鞋底是什么材质", ("橡胶",), ("缓震",)),
            ("DEMO-RUN-002", "这双鞋舒适性怎么样", ("轻", "透气", "织物", "偏小"), ("保证舒适",)),
            ("DEMO-WIDE-003", "鞋头挤不挤", ("宽楦", "前掌", "尺码表"), ("绝对不挤", "保证不磨脚")),
            ("DEMO-WORK-004", "上班久站舒服吗", ("长期穿着测试", "日常站立"), ("久站不累",)),
            ("DEMO-RAIN-005", "这鞋重不重", ("225", "克"), ("非常轻",)),
            ("DEMO-PREORDER-006", "冬天暖不暖，里面有绒吗", ("保暖织物", "冬季"), ("保证暖和",)),
        )
        for product_id, question, required, prohibited in cases:
            with self.subTest(product_id=product_id, question=question):
                answer = self.answer(product_id, question)
                self.assertIsNotNone(answer)
                for fact in required:
                    self.assertIn(fact, answer)
                for unsafe in prohibited:
                    self.assertNotIn(unsafe, answer)

    def test_missing_experience_evidence_is_explicit_and_never_fabricated(self) -> None:
        cases = (
            ("DEMO-CASUAL-001", "鞋底软吗", ("没有", "软硬"), ("橡胶所以软", "鞋底柔软")),
            ("DEMO-RUN-002", "缓震怎么样", ("没有", "缓震"), ("缓震出色", "减震")),
            ("DEMO-WORK-004", "穿久了累不累", ("长期穿着测试",), ("不会累", "全天不累")),
            ("DEMO-CASUAL-001", "会不会磨脚", ("没有", "磨脚", "尺码表"), ("不会磨脚",)),
            ("DEMO-WORK-004", "会不会开胶", ("长期耐用",), ("不会开胶", "保证耐穿")),
        )
        for product_id, question, required, prohibited in cases:
            with self.subTest(question=question):
                answer = self.answer(product_id, question)
                self.assertIsNotNone(answer)
                for text in required:
                    self.assertIn(text, answer)
                for text in prohibited:
                    self.assertNotIn(text, answer)

    def test_scenario_suitability_uses_declared_scenarios_not_neighboring_features(self) -> None:
        supported = self.answer("DEMO-CASUAL-001", "适合日常通勤和走路吗")
        professional_run = self.answer("DEMO-RUN-002", "能不能专业跑步")
        hiking = self.answer("DEMO-RAIN-005", "下雨爬山会不会滑")
        work = self.answer("DEMO-WORK-004", "上班工作穿合适吗")

        self.assertIn("通勤", supported)
        self.assertIn("日常步行", supported)
        self.assertIn("没有标注专业跑步", professional_run)
        self.assertNotIn("适合专业跑步", professional_run)
        for part in ("小雨", "日常防滑", "没有标注登山"):
            self.assertIn(part, hiking)
        self.assertIn("室内工作", work)

    def test_multifacet_questions_keep_every_concern_without_duplicate_caveats(self) -> None:
        cases = (
            ("DEMO-RUN-002", "这鞋舒服吗，会不会偏小", ("轻", "透气", "偏小")),
            ("DEMO-RUN-002", "轻不轻，夏天闷不闷", ("255", "透气")),
            ("DEMO-RAIN-005", "下雨爬山会不会滑", ("小雨", "防滑", "没有标注登山")),
            ("DEMO-CASUAL-001", "鞋底软吗，走久了会不会累", ("软硬", "长期穿着测试")),
            ("DEMO-PREORDER-006", "冬天暖不暖，雨天能穿吗", ("保暖织物", "轻微泼溅")),
        )
        for product_id, question, expected in cases:
            with self.subTest(question=question):
                answer = self.answer(product_id, question)
                for text in expected:
                    self.assertIn(text, answer)
                self.assertLessEqual(answer.count("尺码表"), 1)
                self.assertLessEqual(answer.count("实际"), 1)

    def test_ambiguity_asks_one_stable_clarification_instead_of_summary_or_fit(self) -> None:
        expected = "亲，您主要想了解尺码、舒适度、透气性，还是适合什么场景呢？"
        for question in ("穿着怎么样", "这个好吗", "适合我吗", "这款怎么样？", "请问这个好吗呀"):
            with self.subTest(question=question):
                answer = self.answer("DEMO-CASUAL-001", question)
                self.assertEqual(answer, expected)
                self.assertNotIn("标准版型", answer)
                self.assertNotIn("基础款日常休闲鞋", answer)

    def test_collision_boundaries_preserve_dedicated_routes(self) -> None:
        F = catalog_module.ProductFacet
        dedicated = (
            ("我脚26，这款穿多大", F.SIZE_RECOMMENDATION),
            ("这款有42码吗", F.STOCK),
            ("这款偏小吗", F.FIT),
            ("鞋面是什么材料", F.UPPER_MATERIAL),
            ("什么时候发货", F.SHIPPING),
        )
        for question, expected in dedicated:
            with self.subTest(question=question):
                analysis = catalog_module.analyze_product_question(question)
                self.assertIn(expected, analysis.facets)

        self.assertNotIn(F.SIZE_RECOMMENDATION, catalog_module.analyze_product_question("26号下单").facets)
        self.assertIsNone(self.answer("DEMO-CASUAL-001", "鞋子开胶了怎么办"))
        self.assertIsNone(self.answer("DEMO-CASUAL-001", "物流慢怎么办"))

    def test_metamorphic_variants_preserve_evidence_and_add_facets_monotonically(self) -> None:
        F = catalog_module.ProductFacet
        equivalent = (
            "这鞋舒服吗",
            "请问，这鞋舒服吗？",
            "这鞋舒服吗呀",
            "这鞋好不好穿",
        )
        analyses = [catalog_module.analyze_product_question(item) for item in equivalent]
        for analysis in analyses:
            self.assertIn(F.GENERAL_COMFORT, analysis.facets)
        evidence_classes = {
            tuple(item.status for item in catalog_module.build_product_answer_plan(
                analysis,
                self.catalog.lookup("DEMO-RUN-002"),
            ).evidence)
            for analysis in analyses
        }
        self.assertEqual(len(evidence_classes), 1)

        first = catalog_module.analyze_product_question("这鞋下雨会不会滑")
        reordered = catalog_module.analyze_product_question("会不会滑，下雨穿呢")
        extended = catalog_module.analyze_product_question("这鞋下雨爬山会不会滑")
        self.assertEqual(set(first.facets), set(reordered.facets))
        self.assertTrue(set(first.facets).issubset(set(extended.facets)))
        self.assertIn(F.USE_SCENARIO, extended.facets)

    def test_answer_plan_marks_supported_conditional_and_unsupported_claims(self) -> None:
        F = catalog_module.ProductFacet
        S = catalog_module.ProductClaimStatus
        analysis = catalog_module.analyze_product_question(
            "这鞋透气吗，鞋底软吗，适合跑步吗"
        )
        plan = catalog_module.build_product_answer_plan(
            analysis,
            self.catalog.lookup("DEMO-RUN-002"),
        )
        statuses = {item.facet: item.status for item in plan.evidence}
        self.assertEqual(statuses[F.BREATHABILITY], S.SUPPORTED)
        self.assertEqual(statuses[F.SOLE_SOFTNESS], S.UNSUPPORTED)
        self.assertEqual(statuses[F.USE_SCENARIO], S.CONDITIONALLY_SUPPORTED)

    def test_personal_medical_constraints_are_explicit_and_never_inferred(self) -> None:
        F = catalog_module.ProductFacet
        M = catalog_module.ProductQuestionMode
        analysis = catalog_module.analyze_product_question("孕妇脚受伤了能穿吗")
        self.assertIn(F.TARGET_GENDER_OR_GROUP, analysis.facets)
        self.assertEqual(analysis.mode, M.SUITABILITY_ASSESSMENT)
        self.assertEqual(set(analysis.constraints), {"孕期", "受伤或康复"})

        answer = self.answer("DEMO-CASUAL-001", "孕妇脚受伤了能穿吗")
        self.assertIn("没有提供", answer)
        self.assertIn("孕期", answer)
        self.assertIn("受伤或康复", answer)
        self.assertNotIn("适合孕妇", answer)
        self.assertNotIn("有助康复", answer)

    def test_temperature_suitability_uses_warmth_evidence_without_inventing_a_range(self) -> None:
        analysis = catalog_module.analyze_product_question("零下30度还能穿吗")
        self.assertIn(catalog_module.ProductFacet.WARMTH, analysis.facets)
        answer = self.answer("DEMO-PREORDER-006", "零下30度还能穿吗")
        for expected in ("加绒冬季款", "保暖织物", "没有标注具体适用温度", "零下30℃", "严寒环境"):
            self.assertIn(expected, answer)
        for unsupported in ("零下5-10", "零下5～10", "适合零下", "可以在零下30"):
            self.assertNotIn(unsupported, answer)
        self.assertIn("不建议只凭商品参数判断", answer)

    def test_numeric_claim_validator_requires_matching_structured_evidence(self) -> None:
        temperature_analysis = catalog_module.analyze_product_question("零下30度还能穿吗")
        temperature_plan = catalog_module.build_product_answer_plan(
            temperature_analysis,
            self.catalog.lookup("DEMO-PREORDER-006"),
        )
        invented_temperature = "亲，这款建议零下5-10℃穿，能保暖8小时哦。"
        validated_temperature = catalog_module.validate_product_answer_claims(
            invented_temperature,
            temperature_plan,
        )
        self.assertNotIn("5-10", validated_temperature)
        self.assertNotIn("8小时", validated_temperature)
        self.assertIn("没有标注具体适用温度", validated_temperature)

        weight_analysis = catalog_module.analyze_product_question("单只鞋多重")
        weight_plan = catalog_module.build_product_answer_plan(
            weight_analysis,
            self.catalog.lookup("DEMO-RUN-002"),
        )
        supported_weight = "亲，这款单只鞋约重255克哦。"
        self.assertEqual(
            catalog_module.validate_product_answer_claims(supported_weight, weight_plan),
            supported_weight,
        )
        self.assertNotIn(
            "280克",
            catalog_module.validate_product_answer_claims(
                "亲，这款单只鞋约重280克哦。",
                weight_plan,
            ),
        )

        height_analysis = catalog_module.analyze_product_question("跟高多少")
        height_plan = catalog_module.build_product_answer_plan(
            height_analysis,
            self.catalog.lookup("DEMO-RUN-002"),
        )
        self.assertEqual(
            catalog_module.validate_product_answer_claims("亲，这款跟高约3厘米哦。", height_plan),
            "亲，这款跟高约3厘米哦。",
        )
        for invented in ("跟高8厘米", "耐磨10级", "可以走20公里"):
            with self.subTest(invented=invented):
                self.assertNotIn(
                    invented,
                    catalog_module.validate_product_answer_claims(
                        f"亲，这款{invented}哦。",
                        height_plan,
                    ),
                )

    def test_final_product_claim_validator_uses_plan_and_preserves_negated_boundaries(self) -> None:
        analysis = catalog_module.analyze_product_question("鞋底软吗，缓震怎么样")
        plan = catalog_module.build_product_answer_plan(
            analysis,
            self.catalog.lookup("DEMO-CASUAL-001"),
        )
        unsafe = "这款鞋底很柔软，缓震出色，而且绝对防滑，不会开胶。"
        validated = catalog_module.validate_product_answer_claims(unsafe, plan)
        for claim in ("鞋底很柔软", "缓震出色", "绝对防滑", "不会开胶"):
            self.assertNotIn(claim, validated)
        self.assertIn("没有鞋底软硬度测量", validated)
        self.assertIn("没有缓震测试数据", validated)

        bounded = "当前资料不能保证不会开胶，也无法确认绝对防滑。"
        self.assertEqual(
            catalog_module.validate_product_answer_claims(bounded, plan),
            bounded,
        )


class ProductSemanticRuntimeIsolationTests(unittest.TestCase):
    def test_every_semantic_behavior_family_bypasses_heavy_dependencies(self) -> None:
        engine = web_app.RAGEngine()
        forbidden = mock.Mock(side_effect=AssertionError("heavy product dependency called"))
        cases = (
            ("DEMO-CASUAL-001", "鞋底是什么材质"),
            ("DEMO-RUN-002", "这双鞋舒适性怎么样"),
            ("DEMO-WORK-004", "上班久站舒服吗"),
            ("DEMO-WIDE-003", "脚背会不会压"),
            ("DEMO-CASUAL-001", "鞋底软吗，缓震怎么样"),
            ("DEMO-RUN-002", "夏天穿会不会闷脚"),
            ("DEMO-PREORDER-006", "冬天暖不暖，里面有绒吗"),
            ("DEMO-PREORDER-006", "零下30度还能穿吗"),
            ("DEMO-RAIN-005", "这鞋重不重"),
            ("DEMO-WORK-004", "耐不耐穿"),
            ("DEMO-RAIN-005", "下雨爬山会不会滑"),
            ("DEMO-CASUAL-001", "孕妇脚受伤了能穿吗"),
            ("DEMO-CASUAL-001", "这个好吗"),
        )
        with (
            mock.patch.object(web_app, "engine", engine),
            mock.patch.object(engine, "load", forbidden),
            mock.patch.object(web_app.rag, "load_dependencies", forbidden),
            mock.patch.object(web_app.rag, "load_llm_config", forbidden),
            mock.patch.object(web_app.rag, "load_or_create_cache", forbidden),
            mock.patch.object(web_app.rag, "retrieve", forbidden),
            mock.patch.object(web_app.rag, "rerank_retrieved_results", forbidden),
            mock.patch.object(web_app.rag, "call_deepseek_api", forbidden),
            mock.patch.object(web_app.rag, "run_rag_query", forbidden),
            mock.patch.object(socket, "create_connection", forbidden),
        ):
            with TestClient(web_app.app) as client:
                for product_id, question in cases:
                    with self.subTest(product_id=product_id, question=question):
                        selected = client.post(
                            "/api/demo-products/select",
                            json={"product_id": product_id},
                        )
                        self.assertEqual(selected.status_code, 200)
                        response = client.post("/chat", json={"question": question})
                        self.assertEqual(response.status_code, 200)
                        self.assertTrue(response.json()["final_answer"])

        forbidden.assert_not_called()


class ProductApiAndSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = web_app.RAGEngine()
        self.engine.load = mock.Mock(side_effect=AssertionError("model load is forbidden"))

    def test_catalog_list_and_select_api_are_public_allowlisted(self) -> None:
        with mock.patch.object(web_app, "engine", self.engine):
            with TestClient(web_app.app) as client:
                listing = client.get("/api/demo-products")
                selected = client.post(
                    "/api/demo-products/select",
                    json={"product_id": "DEMO-WORK-004"},
                )

        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()["products"]), 6)
        self.assertEqual(selected.status_code, 200)
        self.assertEqual(selected.json()["selected_product"]["product_id"], "DEMO-WORK-004")
        self.assertNotIn("session", listing.text.casefold())
        self.assertNotIn("session", selected.text.casefold())

    def test_two_clients_keep_selected_product_and_this_product_answers_isolated(self) -> None:
        with mock.patch.object(web_app, "engine", self.engine):
            with TestClient(web_app.app) as first, TestClient(web_app.app) as second:
                first.post(
                    "/api/demo-products/select",
                    json={"product_id": "DEMO-WORK-004"},
                )
                second.post(
                    "/api/demo-products/select",
                    json={"product_id": "DEMO-RAIN-005"},
                )
                first_answer = first.post("/chat", json={"question": "这款防滑吗？"})
                second_answer = second.post("/chat", json={"question": "这款防水吗？"})

        self.assertIn("防滑", first_answer.json()["final_answer"])
        self.assertIn("小雨", second_answer.json()["final_answer"])
        self.engine.load.assert_not_called()

    def test_missing_selection_requests_product_without_loading_rag(self) -> None:
        with mock.patch.object(web_app, "engine", self.engine):
            with TestClient(web_app.app) as client:
                response = client.post("/chat", json={"question": "这款防滑吗？"})

        self.assertEqual(
            response.json()["final_answer"],
            "请先选择或告诉我您咨询的是哪款演示商品，我再根据对应商品信息为您确认。",
        )
        self.engine.load.assert_not_called()

    def test_authenticity_policy_is_direct_and_bypasses_all_heavy_dependencies(self) -> None:
        questions = ("是正品吧", "这款是不是正品", "会不会是假货", "怎么验真")
        with (
            mock.patch.object(web_app, "engine", self.engine),
            mock.patch.object(web_app.rag, "load_dependencies") as dependency_load,
            mock.patch.object(web_app.rag, "load_llm_config") as provider_client,
            mock.patch.object(web_app.rag, "load_or_create_cache") as cache_load,
            mock.patch.object(web_app.rag, "retrieve") as retrieve_call,
            mock.patch.object(web_app.rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(web_app.rag, "call_deepseek_api") as provider_call,
        ):
            with TestClient(web_app.app) as client:
                answers = [
                    client.post("/chat", json={"question": question}).json()["final_answer"]
                    for question in questions
                ]

        expected = (
            "亲，本店所售商品均为正品，您可以放心选购哦。"
            "具体商品信息和售后保障以商品详情页及订单页展示为准。"
        )
        self.assertEqual(answers, [expected] * len(questions))
        for answer in answers:
            for forbidden in ("PICC", "中国人保", "保险", "授权", "无法确认", "转人工"):
                self.assertNotIn(forbidden, answer)
        dependency_load.assert_not_called()
        provider_client.assert_not_called()
        cache_load.assert_not_called()
        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.engine.load.assert_not_called()

    def test_known_pasted_link_selects_locally_and_external_url_never_loads_or_fetches(self) -> None:
        with mock.patch.object(web_app, "engine", self.engine):
            with TestClient(web_app.app) as first, TestClient(web_app.app) as second:
                known = first.post(
                    "/chat",
                    json={
                        "question": (
                            "https://chat.yunyaoai.top/products/DEMO-RUN-002 "
                            "这款26厘米穿多大？"
                        )
                    },
                )
                external = second.post(
                    "/chat",
                    json={
                        "question": "http://169.254.169.254/latest/meta-data 这款防滑吗？"
                    },
                )

        self.assertIn("43码", known.json()["final_answer"])
        self.assertIn("请先选择", external.json()["final_answer"])
        self.engine.load.assert_not_called()

    def test_unknown_demo_link_is_safely_rejected_without_model_load(self) -> None:
        with mock.patch.object(web_app, "engine", self.engine):
            with TestClient(web_app.app) as client:
                response = client.post(
                    "/chat",
                    json={"question": "/products/DEMO-UNKNOWN-999 这款怎么样？"},
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("未找到", response.json()["final_answer"])
        self.assertNotIn("path", response.text.casefold())
        self.engine.load.assert_not_called()

    def test_product_answers_bypass_retrieval_rerank_and_provider(self) -> None:
        with (
            mock.patch.object(web_app, "engine", self.engine),
            mock.patch.object(web_app.rag, "retrieve") as retrieve_call,
            mock.patch.object(web_app.rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(web_app.rag, "call_deepseek_api") as provider_call,
        ):
            with TestClient(web_app.app) as client:
                client.post(
                    "/api/demo-products/select",
                    json={"product_id": "DEMO-CASUAL-001"},
                )
                response = client.post(
                    "/chat",
                    json={"question": "我的脚长26厘米，这款穿多少码？"},
                )

        self.assertIn("42码", response.json()["final_answer"])
        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.engine.load.assert_not_called()

    def test_multifacet_rain_hiking_slip_query_stays_grounded_and_bypasses_rag(self) -> None:
        with (
            mock.patch.object(web_app, "engine", self.engine),
            mock.patch.object(web_app.rag, "load_dependencies") as dependency_load,
            mock.patch.object(web_app.rag, "load_llm_config") as provider_client,
            mock.patch.object(web_app.rag, "load_or_create_cache") as cache_load,
            mock.patch.object(web_app.rag, "retrieve") as retrieve_call,
            mock.patch.object(web_app.rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(web_app.rag, "call_deepseek_api") as provider_call,
        ):
            with TestClient(web_app.app) as client:
                client.post(
                    "/api/demo-products/select",
                    json={"product_id": "DEMO-RAIN-005"},
                )
                response = client.post(
                    "/chat",
                    json={"question": "这鞋下雨爬山会打滑不"},
                )

        answer = response.json()["final_answer"]
        for expected in ("小雨", "PVC纹理鞋底", "日常防滑", "轻雨通勤", "日常休闲"):
            self.assertIn(expected, answer)
        self.assertIn("没有标注登山", answer)
        self.assertIn("不建议", answer)
        dependency_load.assert_not_called()
        provider_client.assert_not_called()
        cache_load.assert_not_called()
        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.engine.load.assert_not_called()

    def test_reported_implicit_size_query_stays_on_deterministic_product_path(self) -> None:
        with (
            mock.patch.object(web_app, "engine", self.engine),
            mock.patch.object(web_app.rag, "load_dependencies") as dependency_load,
            mock.patch.object(web_app.rag, "load_llm_config") as provider_client,
            mock.patch.object(web_app.rag, "load_or_create_cache") as cache_load,
            mock.patch.object(web_app.rag, "retrieve") as retrieve_call,
            mock.patch.object(web_app.rag, "rerank_retrieved_results") as rerank_call,
            mock.patch.object(web_app.rag, "call_deepseek_api") as provider_call,
        ):
            with TestClient(web_app.app) as client:
                client.post(
                    "/api/demo-products/select",
                    json={"product_id": "DEMO-CASUAL-001"},
                )
                response = client.post(
                    "/chat",
                    json={"question": "我脚26,这款鞋应该选多大码"},
                )

        answer = response.json()["final_answer"]
        self.assertIn("42码", answer)
        self.assertIn("基础款日常休闲鞋", answer)
        self.assertIn("标准版型", answer)
        self.assertEqual(answer.count("商品详情页"), 1)
        self.assertNotEqual(
            answer,
            "基础款日常休闲鞋：标准版型，适合日常通勤的演示休闲鞋。"
            "版型说明：标准版型，请优先按本商品尺码表选择。",
        )
        dependency_load.assert_not_called()
        provider_client.assert_not_called()
        cache_load.assert_not_called()
        retrieve_call.assert_not_called()
        rerank_call.assert_not_called()
        provider_call.assert_not_called()
        self.engine.load.assert_not_called()


class ProductDependencyIsolationAuditTests(unittest.TestCase):
    """Fail immediately if a catalog-only request reaches a heavy dependency."""

    FORBIDDEN_IMPORT_ROOTS = {
        "numpy",
        "openai",
        "pandas",
        "sentence_transformers",
    }

    def setUp(self) -> None:
        self.engine = web_app.RAGEngine()
        self.forbidden_calls: dict[str, mock.Mock] = {}

    def _forbidden(self, name: str) -> mock.Mock:
        spy = mock.Mock(side_effect=AssertionError(f"forbidden operation: {name}"))
        self.forbidden_calls[name] = spy
        return spy

    def _guarded_import(self, original_import):
        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name.split(".", 1)[0] in self.FORBIDDEN_IMPORT_ROOTS:
                raise AssertionError(f"forbidden dependency import: {name}")
            return original_import(name, globals, locals, fromlist, level)

        return guarded_import

    def test_all_catalog_only_routes_bypass_every_heavy_operation(self) -> None:
        original_import = builtins.__import__
        route_calls = []
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(web_app, "engine", self.engine))
            stack.enter_context(
                mock.patch.object(self.engine, "load", self._forbidden("RAGEngine.load"))
            )
            for target, attribute, name in (
                (web_app.rag, "load_dependencies", "load_dependencies"),
                (web_app.rag, "load_llm_config", "Provider-client construction"),
                (web_app.rag, "load_or_create_cache", "embedding/cache/corpus loading"),
                (web_app.rag, "retrieve", "retrieval"),
                (web_app.rag, "rerank_retrieved_results", "rerank"),
                (web_app.rag, "call_deepseek_api", "call_deepseek_api"),
                (web_app.rag, "run_rag_query", "RAG pipeline"),
                (catalog_module, "load_catalog", "catalog reload"),
                (catalog_module, "validate_catalog_payload", "catalog revalidation"),
            ):
                stack.enter_context(
                    mock.patch.object(target, attribute, self._forbidden(name))
                )
            stack.enter_context(
                mock.patch.object(Path, "read_text", self._forbidden("catalog file reread"))
            )
            stack.enter_context(
                mock.patch.object(pickle, "load", self._forbidden("pickle corpus loading"))
            )
            stack.enter_context(
                mock.patch.object(
                    builtins,
                    "__import__",
                    side_effect=self._guarded_import(original_import),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    socket,
                    "create_connection",
                    self._forbidden("external network create_connection"),
                )
            )
            stack.enter_context(
                mock.patch.object(
                    urllib.request,
                    "urlopen",
                    self._forbidden("external network urlopen"),
                )
            )

            with TestClient(web_app.app) as client:
                with mock.patch.object(
                    socket.socket,
                    "connect",
                    self._forbidden("external network socket.connect"),
                ):
                    route_calls.extend(
                        (
                            client.get("/"),
                            client.get("/api/demo-products"),
                            client.get("/api/demo-products"),
                            client.get("/products/DEMO-CASUAL-001"),
                            client.post(
                                "/api/demo-products/select",
                                json={"product_id": "DEMO-CASUAL-001"},
                            ),
                        )
                    )
                    for question in (
                        "这款有什么颜色？",
                        "我的脚长26厘米，这款穿多少码？",
                        "这款防滑吗？",
                    ):
                        route_calls.append(
                            client.post("/chat", json={"question": question})
                        )
                    route_calls.append(
                        client.post(
                            "/chat",
                            json={
                                "question": (
                                    "/products/DEMO-RUN-002 "
                                    "我的脚长26厘米，这款穿多少码？"
                                )
                            },
                        )
                    )

        self.assertTrue(all(response.status_code == 200 for response in route_calls))
        self.assertEqual(len(route_calls[1].json()["products"]), 6)
        self.assertIn("42码", route_calls[6].json()["final_answer"])
        self.assertIn("43码", route_calls[-1].json()["final_answer"])
        for name, spy in self.forbidden_calls.items():
            with self.subTest(forbidden_operation=name):
                spy.assert_not_called()
        self.assertFalse(self.engine.loaded)
        self.assertIsNone(self.engine.embedding_model)
        self.assertIsNone(self.engine.embeddings)
        self.assertIsNone(self.engine.corpus)
        self.assertIsNone(self.engine.llm_config)

    def test_only_a_non_product_query_crosses_the_lazy_rag_boundary(self) -> None:
        load_attempt = mock.Mock(side_effect=RuntimeError("audit stop before real load"))
        self.engine.load = load_attempt

        with self.assertRaisesRegex(RuntimeError, "audit stop before real load"):
            self.engine.chat("请介绍一下你们的客服能力", session_id="audit-session")

        load_attempt.assert_called_once_with()

    def test_catalog_instance_is_reused_without_request_time_reload(self) -> None:
        catalog_identity = id(web_app.demo_catalog)
        with (
            mock.patch.object(web_app, "engine", self.engine),
            mock.patch.object(
                web_app,
                "load_catalog",
                side_effect=AssertionError("catalog must not reload per request"),
            ) as app_loader,
            mock.patch.object(
                catalog_module,
                "validate_catalog_payload",
                side_effect=AssertionError("catalog must not revalidate per request"),
            ) as validator,
        ):
            with TestClient(web_app.app) as client:
                for _ in range(3):
                    self.assertEqual(client.get("/api/demo-products").status_code, 200)
                self.assertEqual(
                    client.get("/products/DEMO-CASUAL-001").status_code,
                    200,
                )

        self.assertEqual(id(web_app.demo_catalog), catalog_identity)
        app_loader.assert_not_called()
        validator.assert_not_called()


class ProductRouteAndFrontendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = web_app.RAGEngine()

    def test_all_product_routes_render_and_bind_selection(self) -> None:
        with mock.patch.object(web_app, "engine", self.engine):
            with TestClient(web_app.app) as client:
                for product_id in EXPECTED_PRODUCT_IDS:
                    with self.subTest(product_id=product_id):
                        response = client.get(f"/products/{product_id}")
                        self.assertEqual(response.status_code, 200)
                        self.assertIn("模拟商品数据，仅用于功能演示", response.text)
                        self.assertIn(product_id, response.text)
                        self.assertEqual(
                            self.engine.get_selected_product_id(
                                client.cookies.get(web_app.SESSION_COOKIE_NAME)
                            ),
                            product_id,
                        )

    def test_invalid_product_route_is_sanitized(self) -> None:
        with TestClient(web_app.app, raise_server_exceptions=False) as client:
            response = client.get("/products/DEMO-UNKNOWN-999")
        self.assertEqual(response.status_code, 404)
        self.assertIn("演示商品不存在", response.text)
        for forbidden in ("traceback", "filesystem", str(ROOT).casefold(), ".env"):
            self.assertNotIn(forbidden, response.text.casefold())

    def test_frontend_is_text_safe_origin_independent_and_keeps_chat_contract(self) -> None:
        script = (ROOT / "static" / "main.js").read_text(encoding="utf-8")
        normalized = script.casefold()
        self.assertNotIn("innerhtml", normalized)
        self.assertIn("textcontent", normalized)
        self.assertIn("createtextnode", normalized)
        self.assertIn('fetch("/api/demo-products")', normalized)
        self.assertIn('fetch("/api/demo-products/select"', normalized)
        self.assertIn("window.location.origin", normalized)
        self.assertNotIn("chat.yunyaoai.top", normalized)
        self.assertIn("json.stringify({ question })", normalized)
        for forbidden in ("session_id", "eai_session", "retrieved_results", "rerank_score"):
            self.assertNotIn(forbidden, normalized)

    def test_frontend_catalog_load_is_single_independent_and_has_no_delay_loop(self) -> None:
        script = (ROOT / "static" / "main.js").read_text(encoding="utf-8")
        normalized = script.casefold()
        self.assertEqual(script.count('fetch("/api/demo-products")'), 1)
        self.assertEqual(script.count("loadDemoProducts();"), 1)
        self.assertNotIn("settimeout", normalized)
        self.assertNotIn("setinterval", normalized)
        self.assertNotIn("innerhtml", normalized)
        select_source = script[
            script.index("async function selectDemoProduct") :
            script.index("function renderDemoProducts")
        ]
        self.assertLess(
            select_source.index("await response.json()"),
            select_source.index("setSelectedProduct(data.selected_product)"),
        )
        consult_source = script[
            script.index('consultButton.addEventListener("click"') :
            script.index('shareButton.addEventListener("click"')
        ]
        self.assertLess(
            consult_source.index("await selectDemoProduct(product)"),
            consult_source.index('card.classList.add("selected")'),
        )

    def test_frontend_has_compact_responsive_selector_without_debug_data(self) -> None:
        template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8").casefold()
        self.assertIn("演示商品", template)
        self.assertIn("模拟商品数据，仅用于功能演示", template)
        self.assertRegex(css, r"\.demo-product-list\s*\{[^}]*overflow-x:\s*auto")
        self.assertIn("min-width: 0", css)
        self.assertNotIn("100vw", css)
        self.assertNotIn("retrieved_results", template.casefold())
        self.assertNotIn("reranked_results", template.casefold())


class RichCatalogSchemaRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG_PATH)

    def test_six_products_have_complete_synthetic_semantic_groups(self) -> None:
        required_groups = {
            "identity",
            "pricing",
            "construction",
            "style",
            "functions",
            "sizing",
            "sale",
            "variants",
            "media",
        }
        seen_skus: set[str] = set()
        seen_variants: set[str] = set()
        for product in self.catalog.products:
            with self.subTest(product_id=product["product_id"]):
                self.assertTrue(required_groups.issubset(product))
                self.assertEqual(product["data_classification"], "synthetic_demo_data")
                self.assertEqual(
                    product["pricing"]["classification"],
                    "synthetic_demo_price",
                )
                self.assertEqual(product["pricing"]["currency"], "CNY")
                self.assertGreater(product["pricing"]["display_price"], 0)
                self.assertRegex(product["identity"]["synthetic_sku"], r"^SYN-[A-Z0-9-]+$")
                self.assertNotIn(product["identity"]["synthetic_sku"], seen_skus)
                seen_skus.add(product["identity"]["synthetic_sku"])
                self.assertTrue(product["construction"]["upper_material"])
                self.assertTrue(product["construction"]["lining_material"])
                self.assertTrue(product["construction"]["sole_material"])
                self.assertTrue(product["variants"])
                for variant in product["variants"]:
                    self.assertNotIn(variant["variant_id"], seen_variants)
                    seen_variants.add(variant["variant_id"])
                    self.assertTrue(variant["color_name"])
                    self.assertTrue(variant["variant_label"])

    def test_catalog_covers_six_distinct_footwear_profiles(self) -> None:
        products = {item["product_id"]: item for item in self.catalog.products}
        self.assertEqual(products["DEMO-CASUAL-001"]["sizing"]["fit"], "standard")
        self.assertEqual(products["DEMO-RUN-002"]["sizing"]["fit"], "runs_small")
        self.assertEqual(products["DEMO-WIDE-003"]["sizing"]["fit"], "wide_friendly")
        self.assertEqual(
            products["DEMO-WORK-004"]["functions"]["slip_resistance"]["level"],
            "high_daily",
        )
        self.assertIn(
            products["DEMO-RAIN-005"]["functions"]["water_resistance"]["level"],
            {"daily_splash", "light_rain"},
        )
        self.assertEqual(products["DEMO-PREORDER-006"]["sale"]["sale_type"], "preorder")
        self.assertEqual(
            products["DEMO-PREORDER-006"]["construction"]["lining_material"],
            "保暖织物",
        )

    def test_validation_rejects_nested_schema_and_media_violations(self) -> None:
        source = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        mutations = []

        missing_group = json.loads(json.dumps(source))
        del missing_group["products"][0]["construction"]
        mutations.append(missing_group)

        real_classification = json.loads(json.dumps(source))
        real_classification["products"][0]["data_classification"] = "merchant_data"
        mutations.append(real_classification)

        malformed_price = json.loads(json.dumps(source))
        malformed_price["products"][0]["pricing"]["display_price"] = "89元"
        mutations.append(malformed_price)

        malformed_sku = json.loads(json.dumps(source))
        malformed_sku["products"][0]["identity"]["synthetic_sku"] = "REAL SKU 001"
        mutations.append(malformed_sku)

        invalid_construction_enum = json.loads(json.dumps(source))
        invalid_construction_enum["products"][0]["construction"]["closure_type"] = (
            "unknown_closure"
        )
        mutations.append(invalid_construction_enum)

        duplicate_variant = json.loads(json.dumps(source))
        duplicate_variant["products"][1]["variants"][0]["variant_id"] = (
            duplicate_variant["products"][0]["variants"][0]["variant_id"]
        )
        mutations.append(duplicate_variant)

        outside_chart = json.loads(json.dumps(source))
        outside_chart["products"][0]["variants"][0]["available_sizes"].append(99)
        mutations.append(outside_chart)

        empty_variant_label = json.loads(json.dumps(source))
        empty_variant_label["products"][0]["variants"][0]["color_name"] = ""
        mutations.append(empty_variant_label)

        unsafe_asset = json.loads(json.dumps(source))
        unsafe_asset["products"][0]["media"]["primary_image"]["asset_ref"] = (
            "https://example.invalid/shoe.webp"
        )
        mutations.append(unsafe_asset)

        preorder_without_note = json.loads(json.dumps(source))
        preorder_without_note["products"][-1]["sale"]["preorder_note"] = None
        mutations.append(preorder_without_note)

        for payload in mutations:
            with self.subTest(payload=mutations.index(payload)):
                with self.assertRaises(CatalogValidationError):
                    validate_catalog_payload(payload)


class RichProductAnswerRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG_PATH)

    def answer(self, product_id: str, question: str) -> str | None:
        return answer_product_question(
            question,
            self.catalog.lookup(product_id),
            business_now=SHANGHAI_BEFORE_CUTOFF,
        )

    def test_major_parameters_are_answered_from_structured_fields(self) -> None:
        cases = (
            ("DEMO-CASUAL-001", "这款是什么材质？", ("鞋面", "内里", "鞋底")),
            ("DEMO-CASUAL-001", "鞋面是什么材质？", ("PU",)),
            ("DEMO-CASUAL-001", "内里是什么材质？", ("织物",)),
            ("DEMO-CASUAL-001", "鞋底是什么材质？", ("橡胶",)),
            ("DEMO-RUN-002", "这款透气吗？", ("透气",)),
            ("DEMO-WORK-004", "这款防滑吗？", ("日常", "防滑")),
            ("DEMO-WORK-004", "这款耐磨吗？", ("耐磨",)),
            ("DEMO-RAIN-005", "能下雨天穿吗？", ("小雨",)),
            ("DEMO-CASUAL-001", "鞋底多厚？", ("厘米",)),
            ("DEMO-CASUAL-001", "跟高多少？", ("厘米",)),
            ("DEMO-RUN-002", "单只鞋多重？", ("克",)),
            ("DEMO-CASUAL-001", "是高帮还是低帮？", ("低帮",)),
            ("DEMO-WIDE-003", "怎么闭合？", ("魔术贴",)),
            ("DEMO-PREORDER-006", "适合什么季节？", ("冬季",)),
            ("DEMO-CASUAL-001", "适合男生还是女生？", ("男女",)),
            ("DEMO-WIDE-003", "有什么颜色？", ("雾灰",)),
            ("DEMO-WIDE-003", "有哪些尺码？", ("码",)),
            ("DEMO-CASUAL-001", "多少钱？", ("¥", "89")),
            ("DEMO-CASUAL-001", "是现货还是预售？", ("现货",)),
        )
        for product_id, question, expected_parts in cases:
            with self.subTest(product_id=product_id, question=question):
                answer = self.answer(product_id, question)
                self.assertIsNotNone(answer)
                for expected in expected_parts:
                    self.assertIn(expected, answer)
                self.assertNotIn("：标准版型，适合", answer)

    def test_slip_resistance_answer_uses_natural_customer_service_tone(self) -> None:
        answer = self.answer("DEMO-RAIN-005", "这个防滑性能怎么样")
        self.assertEqual(
            answer,
            "亲，这款的PVC纹理鞋底可以提供日常防滑表现哦。"
            "遇到湿滑路面时，还是建议您多注意脚下。",
        )
        self.assertNotIn("防滑说明是：", answer)
        self.assertNotIn("绝对防滑", answer)

    def test_structured_product_answers_share_one_customer_service_tone(self) -> None:
        cases = (
            ("DEMO-CASUAL-001", "这款偏大偏小？", "标准版型"),
            ("DEMO-WIDE-003", "有什么颜色？", "雾灰"),
            ("DEMO-WIDE-003", "有哪些尺码？", "40码"),
            ("DEMO-CASUAL-001", "鞋面是什么材质？", "PU"),
            ("DEMO-CASUAL-001", "内里是什么材质？", "织物"),
            ("DEMO-CASUAL-001", "鞋底是什么材质？", "橡胶"),
            ("DEMO-CASUAL-001", "鞋底多厚？", "厘米"),
            ("DEMO-RUN-002", "单只鞋多重？", "克"),
            ("DEMO-CASUAL-001", "是高帮还是低帮？", "低帮"),
            ("DEMO-WIDE-003", "怎么闭合？", "魔术贴"),
            ("DEMO-PREORDER-006", "适合什么季节？", "冬季"),
            ("DEMO-CASUAL-001", "适合男生还是女生？", "男女"),
            ("DEMO-CASUAL-001", "多少钱？", "¥89.00"),
            ("DEMO-RUN-002", "这款透气吗？", "透气"),
            ("DEMO-RAIN-005", "能下雨天穿吗？", "小雨"),
            ("DEMO-WORK-004", "这款防滑吗？", "防滑"),
            ("DEMO-WORK-004", "这款耐磨吗？", "耐磨"),
            ("DEMO-CASUAL-001", "请介绍一下这款", "基础款日常休闲鞋"),
        )
        mechanical_phrases = (
            "说明是：",
            "当前模拟",
            "当前演示商品信息",
            "版型说明：",
            "定位为",
        )
        for product_id, question, expected_fact in cases:
            with self.subTest(product_id=product_id, question=question):
                answer = self.answer(product_id, question)
                self.assertIsNotNone(answer)
                self.assertTrue(answer.startswith("亲，"), answer)
                self.assertIn(expected_fact, answer)
                for phrase in mechanical_phrases:
                    self.assertNotIn(phrase, answer)

    def test_authenticity_policy_does_not_depend_on_product_selection_or_risky_endorsement(self) -> None:
        expected = (
            "亲，本店所售商品均为正品，您可以放心选购哦。"
            "具体商品信息和售后保障以商品详情页及订单页展示为准。"
        )
        questions = ("是正品吧", "这款是不是正品", "会不会是假货", "怎么验真")
        for question in questions:
            with self.subTest(question=question):
                self.assertEqual(answer_product_question(question, None), expected)
                self.assertEqual(self.answer("DEMO-CASUAL-001", question), expected)
        self.assertIsNone(answer_product_question("这款有PICC正品险吗", None))

    def test_multifacet_product_question_combines_facts_and_context(self) -> None:
        for question in (
            "这鞋下雨爬山会打滑不",
            "爬山遇到下雨的话，这款防滑吗",
        ):
            with self.subTest(question=question):
                answer = self.answer("DEMO-RAIN-005", question)
                for expected in (
                    "小雨",
                    "PVC纹理鞋底",
                    "日常防滑",
                    "轻雨通勤",
                    "日常休闲",
                    "没有标注登山",
                ):
                    self.assertIn(expected, answer)
                self.assertNotIn("说明是：", answer)

        water_only = self.answer("DEMO-RAIN-005", "这款下雨天能穿吗")
        slip_only = self.answer("DEMO-RAIN-005", "这款防滑吗")
        self.assertNotIn("PVC纹理鞋底", water_only)
        self.assertNotIn("小雨", slip_only)

    def test_missing_exact_weight_uses_only_existing_qualitative_evidence(self) -> None:
        answer = self.answer("DEMO-WIDE-003", "单只鞋多重？")
        self.assertIn("没有标注具体克重", answer)
        self.assertIn("常规轻便度", answer)
        self.assertNotRegex(answer, r"\d+克")

    def test_recommended_size_is_checked_against_named_variant(self) -> None:
        product = self.catalog.lookup("DEMO-CASUAL-001")
        product["variants"][0]["available_sizes"] = [40, 41, 43]
        answer = answer_product_question("脚长26厘米，米白基础款穿多大？", product)
        self.assertIn("42码", answer)
        self.assertIn("米白基础款", answer)
        self.assertIn("不含42码", answer)
        self.assertNotIn("机械加码", answer)


class ProductMediaContractRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_catalog(CATALOG_PATH)

    def test_all_six_primary_images_are_validated_and_product_owned(self) -> None:
        image_root = (ROOT / "static" / "demo-products").resolve()
        total_webp_bytes = 0
        for product_id, expected_url in EXPECTED_PRIMARY_IMAGE_URLS.items():
            with self.subTest(product_id=product_id):
                product = self.catalog.lookup(product_id)
                asset_ref = product["media"]["primary_image"]["asset_ref"]
                self.assertEqual(asset_ref, f"{product_id}/cover.webp")
                self.assertEqual(
                    catalog_module.resolve_media_asset_ref(product_id, asset_ref),
                    expected_url,
                )
                image_path = (image_root / product_id / "cover.webp").resolve()
                self.assertEqual(image_path.parent, image_root / product_id)
                self.assertTrue(image_path.is_file())
                self.assertFalse(image_path.is_symlink())
                image_bytes = image_path.read_bytes()
                self.assertTrue(image_bytes.startswith(b"RIFF"))
                self.assertEqual(image_bytes[8:12], b"WEBP")
                self.assertFalse((image_root / product_id / "cover.png").exists())
                total_webp_bytes += len(image_bytes)
        self.assertLess(total_webp_bytes, 2_500_000)

    def test_primary_asset_references_have_safe_public_urls(self) -> None:
        public = self.catalog.public_product("DEMO-CASUAL-001")
        self.assertEqual(
            public["thumbnail_url"],
            EXPECTED_PRIMARY_IMAGE_URLS["DEMO-CASUAL-001"],
        )
        self.assertTrue(public["thumbnail_alt"])
        self.assertIsNone(
            catalog_module.resolve_media_asset_ref("DEMO-CASUAL-001", None)
        )
        self.assertEqual(
            catalog_module.resolve_media_asset_ref(
                "DEMO-CASUAL-001",
                "DEMO-CASUAL-001/cover.webp",
            ),
            "/static/demo-products/DEMO-CASUAL-001/cover.webp",
        )

    def test_unsafe_asset_references_are_rejected_without_io_or_network(self) -> None:
        unsafe_refs = (
            "http://example.invalid/a.webp",
            "https://example.invalid/a.webp",
            "data:image/png;base64,abc",
            "file:///tmp/a.webp",
            "\\server\\share\\a.webp",
            "/absolute/a.webp",
            "../cover.webp",
            "DEMO-CASUAL-001/../cover.webp",
            "DEMO-CASUAL-001/cover.svg",
            "DEMO-CASUAL-001/cover.webp?x=1",
            "DEMO-CASUAL-001/cover.webp#x",
        )
        with (
            mock.patch.object(Path, "read_bytes") as image_read,
            mock.patch.object(urllib.request, "urlopen") as network_call,
        ):
            for asset_ref in unsafe_refs:
                with self.subTest(asset_ref=asset_ref):
                    with self.assertRaises(CatalogValidationError):
                        catalog_module.resolve_media_asset_ref(
                            "DEMO-CASUAL-001",
                            asset_ref,
                        )
        image_read.assert_not_called()
        network_call.assert_not_called()

    def test_public_media_and_variant_reservations_are_allowlisted(self) -> None:
        public = self.catalog.public_product("DEMO-CASUAL-001")
        self.assertEqual(
            set(public["media"]),
            {"primary_image", "gallery", "detail_images"},
        )
        self.assertIn("image_url", public["media"]["primary_image"])
        for variant in public["variants"]:
            self.assertIn("image_url", variant)
            self.assertIsNone(variant["image_url"])
            self.assertNotIn("filesystem", json.dumps(variant).casefold())

    def test_list_detail_selection_and_static_responses_keep_safe_product_images(self) -> None:
        engine = web_app.RAGEngine()
        engine.load = mock.Mock(side_effect=AssertionError("model load is forbidden"))
        with mock.patch.object(web_app, "engine", engine):
            with TestClient(web_app.app) as client:
                listing = client.get("/api/demo-products").json()["products"]
                detail_pages = {
                    product_id: client.get(f"/products/{product_id}")
                    for product_id in EXPECTED_PRODUCT_IDS
                }
                selected = {
                    product_id: client.post(
                        "/api/demo-products/select",
                        json={"product_id": product_id},
                    ).json()["selected_product"]
                    for product_id in EXPECTED_PRODUCT_IDS
                }
                static_images = {
                    product_id: client.get(EXPECTED_PRIMARY_IMAGE_URLS[product_id])
                    for product_id in EXPECTED_PRODUCT_IDS
                }

        self.assertEqual(len(listing), 6)
        self.assertEqual(
            {product["thumbnail_url"] for product in listing},
            set(EXPECTED_PRIMARY_IMAGE_URLS.values()),
        )
        for product in listing:
            product_id = product["product_id"]
            expected_url = EXPECTED_PRIMARY_IMAGE_URLS[product_id]
            with self.subTest(product_id=product_id):
                self.assertEqual(product["thumbnail_url"], expected_url)
                self.assertEqual(selected[product_id]["thumbnail_url"], expected_url)
                self.assertEqual(
                    self.catalog.public_product(product_id)["thumbnail_url"], expected_url
                )
                self.assertTrue(product["thumbnail_alt"])
                self.assertEqual(
                    set(product["media"]["primary_image"]),
                    {"image_url", "alt"},
                )
                serialized = json.dumps(product)
                self.assertNotIn("asset_ref", serialized)
                self.assertNotIn(str(ROOT), serialized)
                self.assertNotRegex(expected_url, r"\\|\.\.|\?|#|://")
                self.assertEqual(detail_pages[product_id].status_code, 200)
                self.assertIn(product_id, detail_pages[product_id].text)
                self.assertEqual(static_images[product_id].status_code, 200)
                self.assertIn(
                    static_images[product_id].headers["content-type"].split(";", 1)[0],
                    ACCEPTED_IMAGE_CONTENT_TYPES,
                )
        engine.load.assert_not_called()


class RichProductFrontendRevisionTests(unittest.TestCase):
    def test_cards_and_detail_summary_reserve_safe_image_behavior(self) -> None:
        script = (ROOT / "static" / "main.js").read_text(encoding="utf-8")
        normalized = script.casefold()
        self.assertIn("demo-product-media", normalized)
        self.assertIn("demo-product-placeholder", normalized)
        self.assertIn('image.loading = "lazy"', normalized)
        self.assertIn("image.alt", normalized)
        self.assertIn("image.width", normalized)
        self.assertIn("image.height", normalized)
        self.assertRegex(normalized, r"image\.addeventlistener\(\s*[\"']error[\"']")
        self.assertIn("image.replacewith(placeholder)", normalized)
        self.assertIn("thumbnail_url", normalized)
        self.assertNotIn('image.src = ""', normalized)
        self.assertNotIn("innerhtml", normalized)
        for visible_field in (
            "display_price",
            "key_function",
            "sale_type",
            "materials",
            "available_sizes",
            "available_colors",
        ):
            self.assertIn(visible_field, normalized)

    def test_product_images_show_complete_square_source_without_cropping(self) -> None:
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8").casefold()
        normalized = re.sub(r"\s+", " ", css)
        media = re.search(r"\.demo-product-media\s*\{(?P<body>[^}]*)\}", normalized)
        image = re.search(r"\.demo-product-media\s+img\s*\{(?P<body>[^}]*)\}", normalized)
        self.assertIsNotNone(media)
        self.assertIsNotNone(image)
        media_body = media.group("body") if media else ""
        image_body = image.group("body") if image else ""
        self.assertRegex(media_body, r"aspect-ratio:\s*4\s*/\s*3")
        self.assertIn("place-items: center", media_body)
        self.assertIn("overflow: hidden", media_body)
        self.assertIn("width: 100%", image_body)
        self.assertIn("height: 100%", image_body)
        self.assertIn("object-fit: contain", image_body)
        self.assertIn("object-position: center", image_body)
        self.assertIn("padding: 4px 8px 14px", image_body)
        self.assertIn("transform: translatey(-15px)", image_body)
        self.assertIn("box-sizing: border-box", image_body)
        self.assertNotIn("object-fit: cover", image_body)
        self.assertNotRegex(image_body, r"clip-path|transform:\s*scale")

        script = (ROOT / "static" / "main.js").read_text(encoding="utf-8").casefold()
        self.assertIn('image.loading = "lazy"', script)
        self.assertIn("image.alt", script)
        self.assertIn('image.addeventlistener(\n    "error"', script)
        self.assertIn("demo-product-placeholder", script)
        self.assertNotIn("innerhtml", script)

    def test_preorder_winter_image_has_product_specific_extra_upward_offset(self) -> None:
        script = (ROOT / "static" / "main.js").read_text(encoding="utf-8").casefold()
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8").casefold()
        normalized_css = re.sub(r"\s+", " ", css)
        self.assertIn("card.dataset.productid = product.product_id", script)
        self.assertRegex(
            normalized_css,
            r'\.demo-product-card\[data-product-id="demo-preorder-006"\]\s+'
            r'\.demo-product-media\s+img\s*\{[^}]*transform:\s*translatey\(-25px\)',
        )

    def test_catalog_has_accessible_expand_collapse_control(self) -> None:
        template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8").casefold()
        script = (ROOT / "static" / "main.js").read_text(encoding="utf-8").casefold()
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8").casefold()
        self.assertIn('id="democatalogtoggle"', template)
        self.assertIn('type="button"', template)
        self.assertIn('aria-controls="democatalogbody"', template)
        self.assertIn('aria-expanded="true"', template)
        self.assertIn('id="democatalogbody"', template)
        self.assertIn('document.queryselector("#democatalogtoggle")', script)
        self.assertIn('document.queryselector("#democatalogbody")', script)
        self.assertIn('democatalogtoggle.addeventlistener("click"', script)
        self.assertIn("democatalogbody.hidden", script)
        self.assertIn('setattribute("aria-expanded"', script)
        self.assertIn('"收起商品"', script)
        self.assertIn('"展开商品"', script)
        self.assertRegex(css, r"\.demo-catalog-body\[hidden\]\s*\{[^}]*display:\s*none")
        self.assertNotIn("innerhtml", script)

    def test_richer_catalog_remains_mobile_scroll_safe(self) -> None:
        css = (ROOT / "static" / "style.css").read_text(encoding="utf-8").casefold()
        self.assertRegex(css, r"\.demo-product-media\s*\{[^}]*aspect-ratio:")
        self.assertIn("overflow-x: auto", css)
        self.assertIn("min-width: 0", css)
        self.assertNotIn("100vw", css)


if __name__ == "__main__":
    unittest.main()
