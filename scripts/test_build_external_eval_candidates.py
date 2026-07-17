#!/usr/bin/env python3
"""Synthetic regression tests for the external evaluation candidate builder."""

from __future__ import annotations

import csv
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_external_eval_candidates as builder  # noqa: E402
from encoding_sanity import assert_readable_chinese_values  # noqa: E402


def tree_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.as_posix()):
        if not path.exists():
            continue
        files = [path] if path.is_file() else sorted(item for item in path.rglob("*") if item.is_file())
        for file_path in files:
            digest.update(file_path.relative_to(ROOT).as_posix().encode("utf-8"))
            digest.update(hashlib.sha256(file_path.read_bytes()).digest())
    return digest.hexdigest()


def synthetic_chat(month: int, session_count: int = 4) -> str:
    lines: list[str] = []
    for index in range(1, session_count + 1):
        day = index
        lines.extend(
            [
                "以下为一通会话",
                f"虚构顾客{month:02d}{index:02d} 2026-{month:02d}-{day:02d} 10:00:00",
                f"这款鞋底材质适合第{month}月第{index}个测试场景吗？",
                f"虚构客服甲 2026-{month:02d}-{day:02d} 10:01:00",
                "这是完全虚构的合成回复，仅用于验证候选池处理流程。",
                f"会话结束_时间：2026-{month:02d}-{day:02d} 10:02:00",
            ]
        )
    return "\n".join(lines) + "\n"


def create_valid_input(parent: Path, service_sender: str | None = None) -> Path:
    input_dir = parent / builder.DEFAULT_STORE_ID
    input_dir.mkdir(parents=True)
    for month in builder.EXPECTED_MONTHS:
        content = synthetic_chat(month)
        if service_sender:
            content = re.sub(
                rf"^.+(?= 2026-{month:02d}-\d{{2}} 10:01:00$)",
                service_sender,
                content,
                flags=re.MULTILINE,
            )
        (input_dir / f"虚构样本_{month:02d}月.txt").write_text(
            content, encoding="utf-8"
        )
    return input_dir


def candidate_row(question: str, month: int = 1, session: str = "session-a") -> dict[str, object]:
    return {
        "external_store_id": builder.DEFAULT_STORE_ID,
        "external_session_id": session,
        "source_file_id": f"{builder.DEFAULT_STORE_ID}_month_{month:02d}",
        "source_month": month,
        "question_time_start": f"2026-{month:02d}-01 10:00:00",
        "answer_time_end": f"2026-{month:02d}-01 10:01:00",
        "customer_turn_message_count": 1,
        "service_turn_message_count": 1,
        "final_question": question,
        "final_answer": "这是完全虚构且足够长的测试回复。",
        "refined_category": "商品咨询",
        "pii_detected": "false",
        "pii_types": "",
        "candidate_status": "accepted",
        "rejection_reason": "",
    }


class InputValidationTests(unittest.TestCase):
    def test_recognizes_and_sorts_months(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sources = builder.validate_sources(create_valid_input(Path(temp)), builder.DEFAULT_STORE_ID)
        self.assertEqual([source.month for source in sources], [1, 2, 3, 4, 5, 6])
        self.assertEqual(
            [source.source_file_id for source in sources],
            [f"external_store_v1_month_{month:02d}" for month in range(1, 7)],
        )

    def test_missing_month_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            input_dir = create_valid_input(Path(temp))
            next(path for path in input_dir.iterdir() if "06月" in path.name).unlink()
            with self.assertRaisesRegex(builder.InputValidationError, "missing"):
                builder.validate_sources(input_dir, builder.DEFAULT_STORE_ID)

    def test_duplicate_month_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            input_dir = create_valid_input(Path(temp))
            month_six = next(path for path in input_dir.iterdir() if "06月" in path.name)
            month_six.rename(input_dir / "另一个虚构样本_05月.txt")
            with self.assertRaisesRegex(builder.InputValidationError, "duplicate"):
                builder.validate_sources(input_dir, builder.DEFAULT_STORE_ID)


class IdentifierAndPrivacyTests(unittest.TestCase):
    def test_external_session_id_is_stable_and_file_scoped(self) -> None:
        first = builder.stable_external_session_id(
            builder.DEFAULT_STORE_ID, "虚构一月.txt", "session-001"
        )
        repeat = builder.stable_external_session_id(
            builder.DEFAULT_STORE_ID, "虚构一月.txt", "session-001"
        )
        other_file = builder.stable_external_session_id(
            builder.DEFAULT_STORE_ID, "虚构二月.txt", "session-001"
        )
        self.assertEqual(first, repeat)
        self.assertNotEqual(first, other_file)
        self.assertEqual(len(first), 16)

    def test_pii_can_be_sanitized_and_accepted(self) -> None:
        question, types = builder.sanitize_text(
            "请联系虚构手机号19900000000确认鞋底材质。",
            builder.ANONYMIZER_V1.Anonymizer(),
            builder.ANONYMIZER_V2.V2Anonymizer(),
            builder.SAFETY.SafetyCleaner(),
        )
        self.assertIn("[PHONE]", question)
        self.assertIn("PHONE", types)
        self.assertIsNone(
            builder.candidate_rejection_reason(
                question, "这是完全虚构且足够长的测试回复。", "商品咨询"
            )
        )

    def test_residual_pii_and_missing_category_are_rejected(self) -> None:
        self.assertEqual(
            builder.candidate_rejection_reason(
                "请加微信 test_account_123", "这是虚构测试回复。", "商品咨询"
            ),
            "pii_residual",
        )
        self.assertEqual(
            builder.candidate_rejection_reason(
                "这款鞋底材质怎么样？", "这是完全虚构且足够长的测试回复。", ""
            ),
            "missing_category",
        )
        self.assertTrue(
            {"pii_residual", "missing_category", "exact_duplicate", "normalized_duplicate"}
            .issubset(builder.REJECTION_REASONS)
        )


def lineage_item(
    method: str | None,
    sender: str = "",
    stats: builder.SenderInferenceStats | None = None,
) -> tuple[object, str]:
    attributes: dict[str, object] = {}
    if method is not None:
        attributes["_role_inference_method"] = method
    if sender:
        attributes["_role_inference_sender_key"] = sender
    if stats is not None:
        attributes["_role_inference_stats"] = stats
    return SimpleNamespace(**attributes), "retained answer text"


class TraceabilityTests(unittest.TestCase):
    def test_statistical_rule_metadata_preserves_existing_threshold_logic(self) -> None:
        rows: list[dict[str, object]] = []
        for index in range(1, 6):
            session_id = f"session-{index}"
            rows.extend(
                [
                    {
                        "session_id": session_id,
                        "sender": f"customer-{index}",
                        "sender_type": "customer",
                    },
                    {
                        "session_id": session_id,
                        "sender": "private-statistical-agent",
                        "sender_type": "customer",
                    },
                ]
            )
        inference = builder._infer_service_senders(rows)
        self.assertEqual(inference.threshold_sessions, 3)
        self.assertEqual(
            inference.statistical_senders, frozenset({"private-statistical-agent"})
        )
        stats = inference.sender_stats["private-statistical-agent"]
        self.assertEqual(stats.sender_session_count, 5)
        self.assertEqual(stats.coverage_ratio, 1.0)
        self.assertEqual(stats.first_ratio, 0.0)
        self.assertEqual(stats.last_ratio, 1.0)

    def test_candidate_and_session_role_inference_are_separate(self) -> None:
        inferred_stats = builder.SenderInferenceStats(5, 3, 1.0, 0.0, 1.0)
        inferred = builder.answer_role_lineage(
            [
                lineage_item(
                    "statistical_sender_rule",
                    "private-statistical-agent",
                    inferred_stats,
                )
            ],
            session_has_inferred_role=True,
        )
        self.assertEqual(inferred["role_inference_used"], "true")
        self.assertEqual(inferred["role_inference_method"], "statistical_sender_rule")

        legacy_current_qa = builder.answer_role_lineage(
            [lineage_item("legacy_keyword")],
            session_has_inferred_role=True,
        )
        self.assertEqual(legacy_current_qa["role_inference_used"], "false")
        self.assertEqual(legacy_current_qa["role_inference_method"], "legacy_keyword")
        self.assertEqual(legacy_current_qa["session_has_inferred_role"], "true")
        self.assertEqual(legacy_current_qa["role_inference_coverage_ratio"], "")

    def test_legacy_mixed_and_unresolved_methods(self) -> None:
        stats = builder.SenderInferenceStats(8, 3, 0.8, 0.1, 0.9)
        mixed = builder.answer_role_lineage(
            [
                lineage_item("legacy_keyword"),
                lineage_item("statistical_sender_rule", "private-agent", stats),
            ],
            session_has_inferred_role=True,
        )
        self.assertEqual(mixed["role_inference_method"], "mixed")
        self.assertEqual(mixed["role_inference_used"], "true")

        unresolved = builder.answer_role_lineage(
            [lineage_item(None)], session_has_inferred_role=False
        )
        self.assertEqual(unresolved["role_inference_method"], "unresolved")
        self.assertEqual(unresolved["role_inference_used"], "false")

    def test_single_and_multiple_sender_aggregation_is_conservative(self) -> None:
        first = builder.SenderInferenceStats(10, 3, 0.5, 0.1, 0.9)
        second = builder.SenderInferenceStats(6, 3, 0.3, 0.2, 0.85)
        single = builder.answer_role_lineage(
            [lineage_item("statistical_sender_rule", "private-a", first)],
            session_has_inferred_role=True,
        )
        self.assertEqual(single["inferred_service_sender_count"], 1)
        self.assertEqual(single["role_inference_sender_session_count"], 10)

        multiple = builder.answer_role_lineage(
            [
                lineage_item("statistical_sender_rule", "private-a", first),
                lineage_item("statistical_sender_rule", "private-b", second),
                lineage_item("statistical_sender_rule", "private-a", first),
            ],
            session_has_inferred_role=True,
        )
        self.assertEqual(multiple["inferred_service_sender_count"], 2)
        self.assertEqual(multiple["role_inference_sender_session_count"], 6)
        self.assertEqual(multiple["role_inference_threshold_sessions"], 3)
        self.assertEqual(multiple["role_inference_coverage_ratio"], "0.300000")
        self.assertEqual(multiple["role_inference_first_ratio"], "0.200000")
        self.assertEqual(multiple["role_inference_last_ratio"], "0.850000")
        self.assertNotIn("private-a", repr(multiple))
        self.assertNotIn("private-b", repr(multiple))

    def test_parser_anomaly_fields_are_session_level_sorted_and_deduplicated(self) -> None:
        present = builder.session_parser_anomaly_fields(
            [
                {"error_type": "z_type"},
                {"error_type": "a_type"},
                {"error_type": "z_type"},
            ]
        )
        self.assertEqual(present["session_has_parser_anomaly"], "true")
        self.assertEqual(present["parser_anomaly_count"], 3)
        self.assertEqual(present["parser_anomaly_types"], "a_type|z_type")
        self.assertEqual(
            builder.session_parser_anomaly_fields([]),
            {
                "session_has_parser_anomaly": "false",
                "parser_anomaly_count": 0,
                "parser_anomaly_types": "",
            },
        )

    def test_candidate_ids_are_unique_and_rebuild_stable(self) -> None:
        first = [
            builder.stable_external_candidate_id(
                builder.DEFAULT_STORE_ID,
                "external_store_v1_month_01",
                "anonymous-session",
                ordinal,
            )
            for ordinal in range(1, 6)
        ]
        repeat = [
            builder.stable_external_candidate_id(
                builder.DEFAULT_STORE_ID,
                "external_store_v1_month_01",
                "anonymous-session",
                ordinal,
            )
            for ordinal in range(1, 6)
        ]
        self.assertEqual(first, repeat)
        self.assertEqual(len(first), len(set(first)))


class DeduplicationTests(unittest.TestCase):
    def test_exact_and_normalized_duplicates_are_audited(self) -> None:
        sources = {
            f"external_store_v1_month_{month:02d}": builder.SourceSpec(
                Path(f"虚构_{month:02d}月.txt"), month, f"external_store_v1_month_{month:02d}"
            )
            for month in (1, 2, 3)
        }
        rows = [
            candidate_row("这款鞋底防滑吗？", 1, "session-a"),
            candidate_row("这款鞋底防滑吗？", 2, "session-b"),
            candidate_row(" 这款鞋底防滑吗!! ", 3, "session-c"),
        ]
        kept, rejected, metrics = builder.deduplicate_candidates(rows, sources)
        self.assertEqual(len(kept), 1)
        self.assertEqual(
            [row["rejection_reason"] for row in rejected],
            ["exact_duplicate", "normalized_duplicate"],
        )
        self.assertEqual(metrics["exact_duplicate"], 1)
        self.assertEqual(metrics["normalized_duplicate"], 1)
        self.assertEqual(metrics["cross_month_duplicate"], 2)


class EndToEndSyntheticTests(unittest.TestCase):
    def test_utf8_anonymous_outputs_and_protected_files_unchanged(self) -> None:
        protected = [
            ROOT / "data" / "processed" / "jd_final_safe_qa_refined_category.csv",
            ROOT / "data" / "processed" / "knowledge_snippets_v2.csv",
            ROOT / "data" / "processed" / "knowledge_snippets_v2_reviewed.csv",
            ROOT / "outputs" / "cache_v1",
            ROOT / "outputs" / "cache_v2",
        ]
        before = tree_digest(protected)
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            private_sender = "private-statistical-agent"
            input_dir = create_valid_input(temp_root, private_sender)
            output_dir = temp_root / "processed"
            rejected_path = temp_root / "rejected.csv"
            report_path = temp_root / "report.md"
            result = builder.build_candidates(
                input_dir,
                output_dir=output_dir,
                rejected_path=rejected_path,
                report_path=report_path,
            )
            repeat = builder.build_candidates(input_dir, dry_run=True)
            candidate_path = output_dir / "external_store_v1_candidates.csv"
            self.assertEqual(len(result.candidates), 24)
            self.assertTrue(candidate_path.is_file())
            self.assertTrue(rejected_path.is_file())
            self.assertTrue(report_path.is_file())
            candidate_text = candidate_path.read_text(encoding="utf-8-sig")
            rejected_text = rejected_path.read_text(encoding="utf-8-sig")
            report_text = report_path.read_text(encoding="utf-8")
            assert_readable_chinese_values((candidate_text, rejected_text, report_text))
            self.assertIn("这款鞋底材质", candidate_text)
            self.assertNotIn("虚构样本_01月.txt", candidate_text + rejected_text + report_text)
            self.assertNotIn(private_sender, candidate_text + rejected_text + report_text)
            with candidate_path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(tuple(rows[0].keys()), builder.CANDIDATE_FIELDS)
            self.assertNotIn("session_id", rows[0])
            self.assertTrue(all(row["candidate_status"] == "accepted" for row in rows))
            self.assertTrue(all(row["role_inference_used"] == "true" for row in rows))
            self.assertTrue(
                all(row["role_inference_method"] == "statistical_sender_rule" for row in rows)
            )
            candidate_ids = [row["external_candidate_id"] for row in rows]
            self.assertEqual(len(candidate_ids), len(set(candidate_ids)))
            self.assertEqual(result.candidates, repeat.candidates)
        self.assertEqual(before, tree_digest(protected))


class PackagedDependencyTests(unittest.TestCase):
    def test_builder_runs_without_outputs_legacy_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            clean_root = Path(temp)
            clean_scripts = clean_root / "scripts"
            clean_scripts.mkdir()
            shutil.copy2(
                ROOT / "scripts" / "build_external_eval_candidates.py",
                clean_scripts,
            )
            shutil.copytree(
                ROOT / "scripts" / "legacy_preprocessing",
                clean_scripts / "legacy_preprocessing",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            input_dir = create_valid_input(clean_root)
            self.assertFalse((clean_root / "outputs").exists())

            probe = """
from pathlib import Path
import sys

sys.path.insert(0, sys.argv[1])
import build_external_eval_candidates as builder

module_paths = (
    builder.PARSER.__file__,
    builder.EXTRACTOR.__file__,
    builder.ANONYMIZER_V1.__file__,
    builder.ANONYMIZER_V2.__file__,
    builder.SHORT_FILTER.__file__,
    builder.SAFETY.__file__,
    builder.DEDUP.__file__,
    builder.CATEGORIES.__file__,
)
if any("outputs" in Path(path).parts for path in module_paths):
    raise AssertionError(module_paths)
result = builder.build_candidates(Path(sys.argv[2]), dry_run=True)
counts = (
    sum(result.monthly[month]["sessions"] for month in builder.EXPECTED_MONTHS),
    sum(result.monthly[month]["messages"] for month in builder.EXPECTED_MONTHS),
    sum(result.monthly[month]["extracted_qa"] for month in builder.EXPECTED_MONTHS),
    len(result.candidates),
    len(result.rejected),
)
if counts != (24, 48, 24, 24, 0):
    raise AssertionError(counts)
print("packaged-dependency-fixture-pass")
"""
            completed = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    probe,
                    str(clean_scripts),
                    str(input_dir),
                ],
                cwd=clean_root,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
            )
            self.assertIn("packaged-dependency-fixture-pass", completed.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
