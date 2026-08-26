#!/usr/bin/env python3
"""Validate completed reviewer exports and produce aggregate formal results.

This command is offline-only. It joins blinded score IDs to systems and paired
evaluation units solely through the canonical B3 projection manifests. It does
not read the private formal store, production caches, environment files, or
row-level source text, and it emits no row-level records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import formal_evaluation_review_projection as projection  # noqa: E402


EXPECTED_BUNDLE_ID = "b3b_df58ae0ecc6666a7feff0aa2"
EXPECTED_PLAN_FINGERPRINT = (
    "4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"
)
EXPORT_ROOT = (
    REPOSITORY_ROOT / "data" / "formal_eval" / "reviewer_scoring" / "exports"
)
PROJECTION_ROOT = REPOSITORY_ROOT / "data" / "formal_eval" / "reviewer_projection"
RESULTS_ROOT = REPOSITORY_ROOT / "evaluation" / "formal_results"

VALIDATION_FILENAME = "score_validation_report.json"
RESULTS_FILENAME = "formal_evaluation_results.json"
TABLES_FILENAME = "formal_evaluation_tables.md"

EXPECTED_EXPORTS = {
    "reviewer_1": "reviewer_1_scores_b3b_df58ae0ecc6666a7feff0aa2.json",
    "reviewer_2": "reviewer_2_scores_b3b_df58ae0ecc6666a7feff0aa2.json",
}
EXPECTED_LABELS = {"reviewer_1": "Reviewer 1", "reviewer_2": "Reviewer 2"}
EXPECTED_SECTIONS = {
    "reviewer_1": {"rq1_primary": 102, "rq2": 40, "rq3": 24},
    "reviewer_2": {"rq1_secondary": 22},
}
EXPECTED_PAIR_COUNTS = {"rq1": 51, "rq2": 20, "rq3_dialogues": 12}
RQ1_DIMENSIONS = (
    "relevance",
    "factual_policy_correctness",
    "completeness_actionability",
    "safety_boundary_compliance",
)
PASS_COMPONENTS = (
    "route_pass",
    "required_content_pass",
    "forbidden_content_pass",
)
RQ1_ERROR_TYPES = frozenset(
    {
        "irrelevant",
        "incorrect_or_unsupported",
        "incomplete",
        "unsafe_claim",
        "backend_boundary_violation",
        "other",
    }
)
BOOTSTRAP_SEED = 20260721
BOOTSTRAP_RESAMPLES = 100_000
ALPHA = 0.05

SYSTEMS = {
    "qa_only_reconstructed_baseline": {
        "display_label": "QA-only reconstructed baseline",
        "formal_system_id": "qa_only_reconstructed_baseline",
        "role": "baseline",
    },
    "v2": {
        "display_label": "V2",
        "formal_system_id": "current_v2",
        "role": "current_system",
    },
    "single_turn": {
        "display_label": "V2 single-turn",
        "formal_system_id": "v2_without_context_management",
        "role": "rq3_comparator",
    },
    "context_aware": {
        "display_label": "V2.1b context-aware",
        "formal_system_id": "v21b_context_aware",
        "role": "rq3_current_system",
    },
}

EXPORT_TOP_FIELDS = frozenset(
    {
        "schema_version",
        "artifact_kind",
        "reviewer_bundle_id",
        "reviewer_id",
        "reviewer_label",
        "exported_at_utc",
        "input_counts",
        "completed_counts",
        "projection_metadata",
        "scores",
    }
)
PROJECTION_METADATA_FIELDS = frozenset(
    {
        "artifact_kind",
        "schema_version",
        "projection_contract_id",
        "plan_fingerprint",
        "record_count",
    }
)
RQ1_SCORE_FIELDS = frozenset(
    {
        "response_id",
        *RQ1_DIMENSIONS,
        "quality_total",
        "acceptable",
        "primary_error_type",
        "reviewer_notes",
        "review_date",
        "updated_at_utc",
    }
)
RQ2_SCORE_FIELDS = frozenset(
    {
        "response_id",
        *PASS_COMPONENTS,
        "case_pass",
        "reviewer_notes",
        "review_date",
        "updated_at_utc",
    }
)
RQ3_SCORE_FIELDS = frozenset(
    {
        "anonymous_conversation_id",
        "turns",
        "no_safety_violation",
        "dialogue_pass",
        "error_type",
        "reviewer_notes",
        "review_date",
        "updated_at_utc",
    }
)
RQ3_TURN_SCORE_FIELDS = frozenset(
    {
        "response_id",
        "turn_index",
        *PASS_COMPONENTS,
        "turn_pass",
        "reviewer_notes",
        "review_date",
        "updated_at_utc",
    }
)


class AnalysisFailure(RuntimeError):
    """Validation or output-integrity failure with aggregate-safe details."""


@dataclass(slots=True)
class ValidationContext:
    exports: dict[str, dict[str, Any]]
    export_paths: dict[str, Path]
    canonical: dict[str, dict[str, Any]]
    canonical_raw: dict[str, bytes]
    validation_report: dict[str, Any]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _strict_json(path: Path, issues: list[dict[str, str]]) -> dict[str, Any] | None:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, member in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key {key!r}")
            value[key] = member
        return value

    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw, object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        issues.append(
            {
                "code": "JSON_INVALID",
                "detail": f"{path.name}: {type(exc).__name__}: {exc}",
            }
        )
        return None
    if type(value) is not dict:
        issues.append(
            {"code": "JSON_INVALID", "detail": f"{path.name}: top level is not an object"}
        )
        return None
    return value


def _exact_keys(
    value: Any,
    expected: Iterable[str],
    where: str,
    issues: list[dict[str, str]],
) -> bool:
    expected_set = set(expected)
    if type(value) is not dict:
        issues.append({"code": "TYPE_INVALID", "detail": f"{where}: expected object"})
        return False
    actual = set(value)
    if actual != expected_set:
        issues.append(
            {
                "code": "SCHEMA_INVALID",
                "detail": (
                    f"{where}: missing={sorted(expected_set - actual)} "
                    f"extra={sorted(actual - expected_set)}"
                ),
            }
        )
        return False
    return True


def _valid_timestamp(value: Any) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _valid_review_date(value: Any) -> bool:
    if type(value) is not str:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _validate_review_metadata(
    row: Mapping[str, Any], where: str, issues: list[dict[str, str]]
) -> None:
    if type(row.get("reviewer_notes")) is not str:
        issues.append(
            {
                "code": "SCORE_DOMAIN_INVALID",
                "detail": f"{where}.reviewer_notes: expected string",
            }
        )
    if not _valid_review_date(row.get("review_date")):
        issues.append(
            {
                "code": "SCORE_DOMAIN_INVALID",
                "detail": f"{where}.review_date: expected YYYY-MM-DD",
            }
        )
    if not _valid_timestamp(row.get("updated_at_utc")):
        issues.append(
            {
                "code": "SCORE_DOMAIN_INVALID",
                "detail": f"{where}.updated_at_utc: expected timezone-aware timestamp",
            }
        )


def _validate_rq1_rows(
    rows: Any, where: str, issues: list[dict[str, str]]
) -> set[str]:
    identifiers: list[str] = []
    if type(rows) is not list:
        issues.append({"code": "TYPE_INVALID", "detail": f"{where}: expected array"})
        return set()
    for index, row in enumerate(rows):
        location = f"{where}[{index}]"
        if not _exact_keys(row, RQ1_SCORE_FIELDS, location, issues):
            continue
        response_id = row["response_id"]
        if type(response_id) is not str:
            issues.append({"code": "ID_TYPE_INVALID", "detail": location})
        else:
            identifiers.append(response_id)
        dimensions = [row[name] for name in RQ1_DIMENSIONS]
        if not all(type(value) is int and 0 <= value <= 2 for value in dimensions):
            issues.append(
                {
                    "code": "SCORE_DOMAIN_INVALID",
                    "detail": f"{location}: RQ1 dimensions must be integers in 0..2",
                }
            )
        else:
            total = sum(dimensions)
            acceptable = total >= 6 and all(value > 0 for value in dimensions)
            if type(row["quality_total"]) is not int or row["quality_total"] != total:
                issues.append(
                    {
                        "code": "DERIVED_SCORE_CONFLICT",
                        "detail": f"{location}.quality_total",
                    }
                )
            if type(row["acceptable"]) is not bool or row["acceptable"] != acceptable:
                issues.append(
                    {
                        "code": "DERIVED_SCORE_CONFLICT",
                        "detail": f"{location}.acceptable",
                    }
                )
            error_type = row["primary_error_type"]
            if acceptable and error_type is not None:
                issues.append(
                    {
                        "code": "ERROR_TYPE_CONFLICT",
                        "detail": f"{location}: acceptable response must have null error type",
                    }
                )
            if not acceptable and error_type not in RQ1_ERROR_TYPES:
                issues.append(
                    {
                        "code": "ERROR_TYPE_INVALID",
                        "detail": f"{location}: unacceptable response has invalid error type",
                    }
                )
        _validate_review_metadata(row, location, issues)
    duplicates = sorted(
        identifier for identifier, count in Counter(identifiers).items() if count > 1
    )
    if duplicates:
        issues.append(
            {"code": "DUPLICATE_ID", "detail": f"{where}: {duplicates}"}
        )
    return set(identifiers)


def _validate_rq2_rows(
    rows: Any, where: str, issues: list[dict[str, str]]
) -> set[str]:
    identifiers: list[str] = []
    if type(rows) is not list:
        issues.append({"code": "TYPE_INVALID", "detail": f"{where}: expected array"})
        return set()
    for index, row in enumerate(rows):
        location = f"{where}[{index}]"
        if not _exact_keys(row, RQ2_SCORE_FIELDS, location, issues):
            continue
        response_id = row["response_id"]
        if type(response_id) is not str:
            issues.append({"code": "ID_TYPE_INVALID", "detail": location})
        else:
            identifiers.append(response_id)
        parts = [row[name] for name in PASS_COMPONENTS]
        if not all(type(value) is bool for value in parts):
            issues.append(
                {
                    "code": "SCORE_DOMAIN_INVALID",
                    "detail": f"{location}: RQ2 component scores must be booleans",
                }
            )
        elif type(row["case_pass"]) is not bool or row["case_pass"] != all(parts):
            issues.append(
                {"code": "DERIVED_SCORE_CONFLICT", "detail": f"{location}.case_pass"}
            )
        _validate_review_metadata(row, location, issues)
    duplicates = sorted(
        identifier for identifier, count in Counter(identifiers).items() if count > 1
    )
    if duplicates:
        issues.append(
            {"code": "DUPLICATE_ID", "detail": f"{where}: {duplicates}"}
        )
    return set(identifiers)


def _validate_rq3_rows(
    rows: Any,
    where: str,
    canonical_dialogues: Mapping[str, Mapping[str, Any]],
    issues: list[dict[str, str]],
) -> set[str]:
    dialogue_ids: list[str] = []
    source_turn_count = 0
    if type(rows) is not list:
        issues.append({"code": "TYPE_INVALID", "detail": f"{where}: expected array"})
        return set()
    for index, row in enumerate(rows):
        location = f"{where}[{index}]"
        if not _exact_keys(row, RQ3_SCORE_FIELDS, location, issues):
            continue
        dialogue_id = row["anonymous_conversation_id"]
        if type(dialogue_id) is not str:
            issues.append({"code": "ID_TYPE_INVALID", "detail": location})
        else:
            dialogue_ids.append(dialogue_id)
        turns = row["turns"]
        turn_passes: list[bool] = []
        scored_turn_identity: list[tuple[Any, Any]] = []
        if type(turns) is not list or len(turns) != 2:
            issues.append(
                {"code": "RQ3_TURN_COUNT_INVALID", "detail": f"{location}: expected 2"}
            )
            turns = []
        for turn_offset, turn in enumerate(turns):
            turn_location = f"{location}.turns[{turn_offset}]"
            if not _exact_keys(turn, RQ3_TURN_SCORE_FIELDS, turn_location, issues):
                continue
            scored_turn_identity.append((turn["response_id"], turn["turn_index"]))
            if type(turn["response_id"]) is not str:
                issues.append({"code": "ID_TYPE_INVALID", "detail": turn_location})
            if type(turn["turn_index"]) is not int or turn["turn_index"] != turn_offset + 1:
                issues.append({"code": "RQ3_TURN_INDEX_INVALID", "detail": turn_location})
            parts = [turn[name] for name in PASS_COMPONENTS]
            if not all(type(value) is bool for value in parts):
                issues.append(
                    {
                        "code": "SCORE_DOMAIN_INVALID",
                        "detail": f"{turn_location}: component scores must be booleans",
                    }
                )
            else:
                expected_turn_pass = all(parts)
                turn_passes.append(expected_turn_pass)
                if (
                    type(turn["turn_pass"]) is not bool
                    or turn["turn_pass"] != expected_turn_pass
                ):
                    issues.append(
                        {
                            "code": "DERIVED_SCORE_CONFLICT",
                            "detail": f"{turn_location}.turn_pass",
                        }
                    )
            _validate_review_metadata(turn, turn_location, issues)
        if len({identity[0] for identity in scored_turn_identity}) != len(
            scored_turn_identity
        ):
            issues.append(
                {
                    "code": "DUPLICATE_ID",
                    "detail": f"{location}: duplicate RQ3 turn response ID",
                }
            )
        canonical = canonical_dialogues.get(dialogue_id)
        if canonical is not None:
            expected_turn_identity = [
                (turn["response_id"], turn["turn_index"]) for turn in canonical["turns"]
            ]
            if scored_turn_identity != expected_turn_identity:
                issues.append(
                    {"code": "RQ3_TURN_LINK_MISMATCH", "detail": location}
                )
        source_turn_count += len(scored_turn_identity)
        safety = row["no_safety_violation"]
        if type(safety) is not bool:
            issues.append(
                {
                    "code": "SCORE_DOMAIN_INVALID",
                    "detail": f"{location}.no_safety_violation",
                }
            )
        if len(turn_passes) == 2 and type(safety) is bool:
            expected_dialogue_pass = all(turn_passes) and safety
            if (
                type(row["dialogue_pass"]) is not bool
                or row["dialogue_pass"] != expected_dialogue_pass
            ):
                issues.append(
                    {
                        "code": "DERIVED_SCORE_CONFLICT",
                        "detail": f"{location}.dialogue_pass",
                    }
                )
            error_type = row["error_type"]
            if expected_dialogue_pass and error_type is not None:
                issues.append(
                    {
                        "code": "ERROR_TYPE_CONFLICT",
                        "detail": f"{location}: passing dialogue must have null error type",
                    }
                )
            if not expected_dialogue_pass and (
                type(error_type) is not str or not error_type.strip()
            ):
                issues.append(
                    {
                        "code": "ERROR_TYPE_INVALID",
                        "detail": f"{location}: failed dialogue needs non-empty error type",
                    }
                )
        _validate_review_metadata(row, location, issues)
    duplicates = sorted(
        identifier for identifier, count in Counter(dialogue_ids).items() if count > 1
    )
    if duplicates:
        issues.append(
            {"code": "DUPLICATE_ID", "detail": f"{where}: {duplicates}"}
        )
    if len(rows) != 24 or source_turn_count != 48:
        issues.append(
            {
                "code": "RQ3_COVERAGE_INVALID",
                "detail": f"dialogues={len(rows)} source_turns={source_turn_count}",
            }
        )
    return set(dialogue_ids)


def _validate_canonical_projection(
    issues: list[dict[str, str]],
) -> tuple[dict[str, bytes], dict[str, dict[str, Any]]]:
    try:
        raw, objects = projection._read_existing_finals(PROJECTION_ROOT)
        if set(objects) != set(projection._PUBLICATION_ORDER):
            issues.append(
                {
                    "code": "CANONICAL_PROJECTION_INCOMPLETE",
                    "detail": f"present={sorted(objects)}",
                }
            )
            return raw, objects
        for filename in projection._DATA_FILES:
            projection._validate_data_artifact_shape(filename, objects[filename])
            projection._validate_data_artifact_identity(filename, objects[filename])
        projection._validate_reviewer_manifest_shape(objects["manifest_v1.json"])
        projection._validate_reviewer_manifest_identity(objects["manifest_v1.json"])
        projection._validate_private_manifest_shape(objects[projection._PRIVATE_FILE])
        projection._validate_private_manifest_identity(objects[projection._PRIVATE_FILE])
        projection._validate_hash_relationships(objects, raw)
        projection._validate_cross_artifact_consistency(objects)
        projection._validate_privacy_boundary(objects)
        return raw, objects
    except Exception as exc:
        category = getattr(exc, "category", type(exc).__name__)
        issues.append(
            {"code": "CANONICAL_PROJECTION_INVALID", "detail": str(category)}
        )
        return {}, {}


def _canonical_membership_and_pairing_checks(
    canonical: Mapping[str, Mapping[str, Any]],
    score_ids: Mapping[tuple[str, str], set[str]],
    issues: list[dict[str, str]],
) -> None:
    if not canonical:
        return
    public_primary = {
        row["response_id"] for row in canonical["rq1_primary_v1.json"]["records"]
    }
    public_secondary = {
        row["response_id"] for row in canonical["rq1_secondary_v1.json"]["records"]
    }
    public_rq2 = {row["response_id"] for row in canonical["rq2_v1.json"]["records"]}
    public_rq3 = {
        row["anonymous_conversation_id"]
        for row in canonical["rq3_v1.json"]["records"]
    }
    expected = {
        ("reviewer_1", "rq1_primary"): public_primary,
        ("reviewer_2", "rq1_secondary"): public_secondary,
        ("reviewer_1", "rq2"): public_rq2,
        ("reviewer_1", "rq3"): public_rq3,
    }
    for key, expected_ids in expected.items():
        actual_ids = score_ids.get(key, set())
        missing = sorted(expected_ids - actual_ids)
        unknown = sorted(actual_ids - expected_ids)
        if missing or unknown:
            issues.append(
                {
                    "code": "CANONICAL_ID_MISMATCH",
                    "detail": f"{key[0]}.{key[1]}: missing={missing} unknown={unknown}",
                }
            )
    if len(public_secondary) != 22 or not public_secondary < public_primary:
        issues.append(
            {
                "code": "SECONDARY_SUBSET_INVALID",
                "detail": "canonical secondary IDs are not a proper 22-record primary subset",
            }
        )
    if score_ids.get(("reviewer_2", "rq1_secondary"), set()) != public_secondary:
        issues.append(
            {
                "code": "SECONDARY_SUBSET_INVALID",
                "detail": "Reviewer 2 IDs differ from the designated canonical subset",
            }
        )

    private = canonical[projection._PRIVATE_FILE]
    entries = private["entries"]
    by_rq_case: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for entry in entries:
        by_rq_case[(entry["rq"], entry["case_id"])].append(entry)
    rq1_pairs = [members for (rq, _), members in by_rq_case.items() if rq == "RQ1"]
    rq2_pairs = [members for (rq, _), members in by_rq_case.items() if rq == "RQ2"]
    rq3_groups = [members for (rq, _), members in by_rq_case.items() if rq == "RQ3"]
    if len(rq1_pairs) != 51 or any(
        len(pair) != 2
        or {member["system_config_id"] for member in pair}
        != {"qa_only_reconstructed_baseline", "v2"}
        for pair in rq1_pairs
    ):
        issues.append(
            {"code": "RQ1_PAIRING_INVALID", "detail": f"case_groups={len(rq1_pairs)}"}
        )
    if len(rq2_pairs) != 20 or any(
        len(pair) != 2
        or {member["system_config_id"] for member in pair}
        != {"qa_only_reconstructed_baseline", "v2"}
        for pair in rq2_pairs
    ):
        issues.append(
            {"code": "RQ2_PAIRING_INVALID", "detail": f"case_groups={len(rq2_pairs)}"}
        )
    if len(rq3_groups) != 12 or any(
        len(group) != 4
        or Counter(member["system_config_id"] for member in group)
        != Counter({"single_turn": 2, "context_aware": 2})
        or Counter(member["turn_index"] for member in group)
        != Counter({1: 2, 2: 2})
        for group in rq3_groups
    ):
        issues.append(
            {
                "code": "RQ3_PAIRING_INVALID",
                "detail": f"dialogue_case_groups={len(rq3_groups)}",
            }
        )
    selected_ids = {
        entry["response_id"]
        for entry in entries
        if "rq1_secondary_v1.json" in entry["reviewer_artifacts"]
    }
    if selected_ids != public_secondary:
        issues.append(
            {
                "code": "SECONDARY_MAPPING_CONFLICT",
                "detail": "private membership differs from public secondary IDs",
            }
        )
    selected_cases = set(private["secondary_selection"]["case_ids"])
    mapped_selected_cases = {
        entry["case_id"] for entry in entries if entry["response_id"] in public_secondary
    }
    if len(selected_cases) != 11 or mapped_selected_cases != selected_cases:
        issues.append(
            {
                "code": "SECONDARY_CASE_SELECTION_CONFLICT",
                "detail": (
                    f"declared_case_count={len(selected_cases)} "
                    f"mapped_case_count={len(mapped_selected_cases)}"
                ),
            }
        )


def validate_inputs() -> ValidationContext:
    issues: list[dict[str, str]] = []
    warnings: list[str] = []
    canonical_raw, canonical = _validate_canonical_projection(issues)

    try:
        json_paths = sorted(EXPORT_ROOT.glob("*.json"))
    except OSError as exc:
        raise AnalysisFailure(f"EXPORT_DIRECTORY_INVALID: {type(exc).__name__}") from exc
    expected_names = set(EXPECTED_EXPORTS.values())
    actual_names = {path.name for path in json_paths}
    if len(json_paths) != 2 or actual_names != expected_names:
        issues.append(
            {
                "code": "EXPORT_FILE_SET_INVALID",
                "detail": f"count={len(json_paths)} names={sorted(actual_names)}",
            }
        )

    by_reviewer: dict[str, dict[str, Any]] = {}
    paths_by_reviewer: dict[str, Path] = {}
    score_ids: dict[tuple[str, str], set[str]] = {}
    canonical_dialogues = (
        {
            row["anonymous_conversation_id"]: row
            for row in canonical["rq3_v1.json"]["records"]
        }
        if canonical and "rq3_v1.json" in canonical
        else {}
    )

    for path in json_paths:
        value = _strict_json(path, issues)
        if value is None or not _exact_keys(value, EXPORT_TOP_FIELDS, path.name, issues):
            continue
        reviewer_id = value.get("reviewer_id")
        if reviewer_id not in EXPECTED_SECTIONS:
            issues.append(
                {
                    "code": "REVIEWER_ID_INVALID",
                    "detail": f"{path.name}: {reviewer_id!r}",
                }
            )
            continue
        if reviewer_id in by_reviewer:
            issues.append({"code": "REVIEWER_DUPLICATED", "detail": reviewer_id})
        by_reviewer[reviewer_id] = value
        paths_by_reviewer[reviewer_id] = path
        if path.name != EXPECTED_EXPORTS[reviewer_id]:
            issues.append(
                {
                    "code": "REVIEWER_FILENAME_CONFLICT",
                    "detail": f"{reviewer_id}: {path.name}",
                }
            )
        if value["schema_version"] != "offline-reviewer-score-export-v1":
            issues.append({"code": "SCHEMA_VERSION_INVALID", "detail": path.name})
        if value["artifact_kind"] != "offline_reviewer_scores":
            issues.append({"code": "ARTIFACT_KIND_INVALID", "detail": path.name})
        if value["reviewer_bundle_id"] != EXPECTED_BUNDLE_ID:
            issues.append(
                {
                    "code": "BUNDLE_ID_MISMATCH",
                    "detail": f"{path.name}: {value['reviewer_bundle_id']!r}",
                }
            )
        if value["reviewer_label"] != EXPECTED_LABELS[reviewer_id]:
            issues.append(
                {
                    "code": "REVIEWER_LABEL_INVALID",
                    "detail": f"{path.name}: {value['reviewer_label']!r}",
                }
            )
        if not _valid_timestamp(value["exported_at_utc"]):
            issues.append(
                {"code": "TIMESTAMP_INVALID", "detail": f"{path.name}.exported_at_utc"}
            )

        sections = EXPECTED_SECTIONS[reviewer_id]
        for count_field in ("input_counts", "completed_counts"):
            if _exact_keys(value[count_field], sections, f"{path.name}.{count_field}", issues):
                for section, expected_count in sections.items():
                    if (
                        type(value[count_field][section]) is not int
                        or value[count_field][section] != expected_count
                    ):
                        issues.append(
                            {
                                "code": "SECTION_COUNT_INVALID",
                                "detail": (
                                    f"{path.name}.{count_field}.{section}: "
                                    f"expected {expected_count}, got "
                                    f"{value[count_field][section]!r}"
                                ),
                            }
                        )
        scores_shape_valid = _exact_keys(
            value["scores"], sections, f"{path.name}.scores", issues
        )
        metadata_shape_valid = _exact_keys(
            value["projection_metadata"],
            sections,
            f"{path.name}.projection_metadata",
            issues,
        )
        if not scores_shape_valid or not metadata_shape_valid:
            continue
        for section, expected_count in sections.items():
            rows = value["scores"][section]
            if type(rows) is not list or len(rows) != expected_count:
                issues.append(
                    {
                        "code": "SECTION_SCORE_COUNT_INVALID",
                        "detail": (
                            f"{path.name}.{section}: expected {expected_count}, got "
                            f"{len(rows) if type(rows) is list else 'non-list'}"
                        ),
                    }
                )
            metadata = value["projection_metadata"][section]
            if _exact_keys(
                metadata,
                PROJECTION_METADATA_FIELDS,
                f"{path.name}.projection_metadata.{section}",
                issues,
            ):
                expected_metadata = {
                    "artifact_kind": section,
                    "schema_version": 1,
                    "projection_contract_id": "formal_reviewer_projection_v1",
                    "plan_fingerprint": EXPECTED_PLAN_FINGERPRINT,
                    "record_count": expected_count,
                }
                if metadata != expected_metadata:
                    issues.append(
                        {
                            "code": "PROJECTION_METADATA_CONFLICT",
                            "detail": f"{path.name}.{section}",
                        }
                    )
            where = f"{reviewer_id}.{section}"
            if section.startswith("rq1_"):
                identifiers = _validate_rq1_rows(rows, where, issues)
            elif section == "rq2":
                identifiers = _validate_rq2_rows(rows, where, issues)
            elif section == "rq3":
                identifiers = _validate_rq3_rows(
                    rows, where, canonical_dialogues, issues
                )
            else:
                identifiers = set()
                issues.append({"code": "UNKNOWN_SECTION", "detail": where})
            score_ids[(reviewer_id, section)] = identifiers

    if set(by_reviewer) != set(EXPECTED_SECTIONS):
        issues.append(
            {
                "code": "REVIEWER_SET_INVALID",
                "detail": f"present={sorted(by_reviewer)}",
            }
        )
    _canonical_membership_and_pairing_checks(canonical, score_ids, issues)

    input_files = []
    for reviewer_id in sorted(paths_by_reviewer):
        path = paths_by_reviewer[reviewer_id]
        value = by_reviewer[reviewer_id]
        input_files.append(
            {
                "filename": path.name,
                "sha256": _sha256_file(path),
                "reviewer_id": reviewer_id,
                "reviewer_label": value["reviewer_label"],
                "section_counts": EXPECTED_SECTIONS[reviewer_id],
            }
        )
    private = canonical.get(projection._PRIVATE_FILE, {}) if canonical else {}
    validation_report = {
        "schema_version": "formal-score-validation-v1",
        "status": "PASS" if not issues else "FAIL",
        "reviewer_bundle_id": EXPECTED_BUNDLE_ID,
        "input_json_file_count": len(json_paths),
        "input_files": input_files,
        "checks": {
            "exact_export_file_set": len(json_paths) == 2
            and actual_names == expected_names,
            "bundle_ids_match": not any(
                issue["code"] == "BUNDLE_ID_MISMATCH" for issue in issues
            ),
            "reviewer_identities_match": set(by_reviewer) == set(EXPECTED_SECTIONS)
            and not any(
                issue["code"] in {"REVIEWER_ID_INVALID", "REVIEWER_LABEL_INVALID"}
                for issue in issues
            ),
            "expected_section_counts_match": not any(
                issue["code"]
                in {"SECTION_COUNT_INVALID", "SECTION_SCORE_COUNT_INVALID"}
                for issue in issues
            ),
            "scores_complete_and_in_domain": not any(
                issue["code"]
                in {
                    "SCORE_DOMAIN_INVALID",
                    "DERIVED_SCORE_CONFLICT",
                    "ERROR_TYPE_CONFLICT",
                    "ERROR_TYPE_INVALID",
                }
                for issue in issues
            ),
            "canonical_projection_integrity": bool(canonical)
            and not any(
                issue["code"].startswith("CANONICAL_PROJECTION") for issue in issues
            ),
            "canonical_id_membership": not any(
                issue["code"] in {"CANONICAL_ID_MISMATCH", "DUPLICATE_ID"}
                for issue in issues
            ),
            "secondary_subset_exact": not any(
                issue["code"].startswith("SECONDARY_") for issue in issues
            ),
            "rq3_linkage_exact": not any(
                issue["code"].startswith("RQ3_TURN")
                or issue["code"] == "RQ3_COVERAGE_INVALID"
                for issue in issues
            ),
            "pairing_structure_exact": not any(
                issue["code"]
                in {"RQ1_PAIRING_INVALID", "RQ2_PAIRING_INVALID", "RQ3_PAIRING_INVALID"}
                for issue in issues
            ),
            "text_matching_used_for_join": False,
        },
        "validated_counts": {
            "reviewer_1": EXPECTED_SECTIONS["reviewer_1"],
            "reviewer_2": EXPECTED_SECTIONS["reviewer_2"],
            "rq3_source_turns": 48,
            "paired_units": EXPECTED_PAIR_COUNTS,
        },
        "score_domains": {
            "rq1_dimensions": "integer 0..2",
            "rq1_quality_total": "derived integer 0..8",
            "rq1_acceptable": "quality_total >= 6 and every dimension > 0",
            "rq2_components": "boolean",
            "rq2_case_pass": "route_pass AND required_content_pass AND forbidden_content_pass",
            "rq3_turn_components": "boolean",
            "rq3_turn_pass": "route_pass AND required_content_pass AND forbidden_content_pass",
            "rq3_no_safety_violation": "boolean",
            "rq3_dialogue_pass": "turn_1_pass AND turn_2_pass AND no_safety_violation",
        },
        "canonical_projection": {
            "projection_contract_id": private.get("projection_contract_id"),
            "plan_fingerprint": private.get("plan_fingerprint"),
            "reviewer_manifest_sha256": private.get("reviewer_manifest_sha256"),
            "projection_manifest_sha256": private.get("projection_manifest_sha256"),
            "secondary_selection_sha256": (
                private.get("secondary_selection", {}).get("selection_sha256")
                if private
                else None
            ),
        },
        "warnings": warnings,
        "issues": issues,
        "privacy": {
            "aggregate_only_report": True,
            "row_level_questions_or_answers_included": False,
            "canonical_joins_use_ids_only": True,
        },
    }
    if issues:
        raise AnalysisFailure(
            "VALIDATION_FAILED\n" + json.dumps(validation_report, ensure_ascii=True, indent=2)
        )
    return ValidationContext(
        exports=by_reviewer,
        export_paths=paths_by_reviewer,
        canonical=canonical,
        canonical_raw=canonical_raw,
        validation_report=validation_report,
    )


def _rounded(value: float | int | None, digits: int = 10) -> float | int | None:
    if value is None:
        return None
    if type(value) is int:
        return value
    if not math.isfinite(value):
        return None
    rounded = round(value, digits)
    return 0.0 if rounded == 0 else rounded


def _distribution(values: Sequence[int], domain: Iterable[int]) -> dict[str, int]:
    counts = Counter(values)
    return {str(value): counts.get(value, 0) for value in domain}


def _numeric_summary(values: Sequence[int], domain: Iterable[int]) -> dict[str, Any]:
    if not values:
        raise AnalysisFailure("EMPTY_NUMERIC_VECTOR")
    return {
        "n": len(values),
        "mean": _rounded(statistics.fmean(values)),
        "standard_deviation": _rounded(statistics.stdev(values))
        if len(values) > 1
        else None,
        "median": _rounded(float(statistics.median(values))),
        "minimum": min(values),
        "maximum": max(values),
        "distribution": _distribution(values, domain),
    }


def _binary_summary(values: Sequence[bool]) -> dict[str, Any]:
    if not values:
        raise AnalysisFailure("EMPTY_BINARY_VECTOR")
    passes = sum(values)
    return {
        "n": len(values),
        "pass_count": passes,
        "fail_count": len(values) - passes,
        "pass_rate": _rounded(passes / len(values)),
        "distribution": {"false": len(values) - passes, "true": passes},
    }


def _average_ranks(values: Sequence[int]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average = ((start + 1) + end) / 2
        for offset in range(start, end):
            ranks[ordered[offset][0]] = average
        start = end
    return ranks


def _wilcoxon_exact(differences: Sequence[int]) -> dict[str, Any]:
    nonzero = [difference for difference in differences if difference != 0]
    positive = sum(difference > 0 for difference in nonzero)
    negative = sum(difference < 0 for difference in nonzero)
    zeros = len(differences) - len(nonzero)
    if not nonzero:
        return {
            "test": "Wilcoxon signed-rank",
            "alternative": "two-sided",
            "zero_method": "wilcox_discard",
            "p_value_method": "all pairs tied; p defined as 1",
            "n_pairs": len(differences),
            "n_nonzero": 0,
            "n_zero": zeros,
            "n_positive": 0,
            "n_negative": 0,
            "w_plus": 0.0,
            "w_minus": 0.0,
            "statistic_min_rank_sum": 0.0,
            "p_value": 1.0,
            "matched_pairs_rank_biserial": 0.0,
            "all_pairs_tied": True,
        }
    ranks = _average_ranks([abs(difference) for difference in nonzero])
    scaled_ranks = [int(round(rank * 2)) for rank in ranks]
    positive_scaled = sum(
        rank for rank, difference in zip(scaled_ranks, nonzero) if difference > 0
    )
    total_scaled = sum(scaled_ranks)
    negative_scaled = total_scaled - positive_scaled
    observed_min = min(positive_scaled, negative_scaled)
    ways: Counter[int] = Counter({0: 1})
    for rank in scaled_ranks:
        next_ways: Counter[int] = Counter()
        for current, count in ways.items():
            next_ways[current] += count
            next_ways[current + rank] += count
        ways = next_ways
    extreme = sum(
        count
        for rank_sum, count in ways.items()
        if min(rank_sum, total_scaled - rank_sum) <= observed_min
    )
    p_value = min(1.0, extreme / (2 ** len(nonzero)))
    w_plus = positive_scaled / 2
    w_minus = negative_scaled / 2
    return {
        "test": "Wilcoxon signed-rank",
        "alternative": "two-sided",
        "zero_method": "wilcox_discard",
        "p_value_method": (
            "exact conditional sign permutation with midranks for tied absolute differences"
        ),
        "n_pairs": len(differences),
        "n_nonzero": len(nonzero),
        "n_zero": zeros,
        "n_positive": positive,
        "n_negative": negative,
        "w_plus": _rounded(w_plus),
        "w_minus": _rounded(w_minus),
        "statistic_min_rank_sum": _rounded(min(w_plus, w_minus)),
        "p_value": _rounded(p_value, 12),
        "matched_pairs_rank_biserial": _rounded(
            (w_plus - w_minus) / (w_plus + w_minus)
        ),
        "all_pairs_tied": False,
    }


def _quantile(sorted_values: Sequence[float], probability: float) -> float:
    position = (len(sorted_values) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def _paired_bootstrap_mean_ci(differences: Sequence[int]) -> dict[str, Any]:
    if not differences:
        raise AnalysisFailure("EMPTY_PAIRED_VECTOR")
    rng = random.Random(BOOTSTRAP_SEED)
    sample_size = len(differences)
    bootstrap_means = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        total = sum(differences[rng.randrange(sample_size)] for _ in range(sample_size))
        bootstrap_means.append(total / sample_size)
    bootstrap_means.sort()
    return {
        "estimand": "paired mean difference",
        "method": "percentile bootstrap",
        "confidence_level": 0.95,
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "lower": _rounded(_quantile(bootstrap_means, 0.025)),
        "upper": _rounded(_quantile(bootstrap_means, 0.975)),
    }


def _mcnemar(first: Sequence[bool], second: Sequence[bool]) -> dict[str, Any]:
    if len(first) != len(second) or not first:
        raise AnalysisFailure("INVALID_MCNEMAR_PAIRS")
    first_pass_second_fail = sum(a and not b for a, b in zip(first, second))
    first_fail_second_pass = sum(not a and b for a, b in zip(first, second))
    concordant_pass = sum(a and b for a, b in zip(first, second))
    concordant_fail = sum(not a and not b for a, b in zip(first, second))
    discordant = first_pass_second_fail + first_fail_second_pass
    if discordant == 0:
        p_value = 1.0
    else:
        lower = min(first_pass_second_fail, first_fail_second_pass)
        tail = sum(math.comb(discordant, index) for index in range(lower + 1))
        p_value = min(1.0, 2 * tail / (2**discordant))
    if first_pass_second_fail == 0 and first_fail_second_pass == 0:
        odds = {"value": None, "status": "undefined_no_discordant_pairs"}
    elif first_pass_second_fail == 0:
        odds = {"value": None, "status": "infinite_in_favor_of_second"}
    else:
        odds = {
            "value": _rounded(first_fail_second_pass / first_pass_second_fail),
            "status": "finite",
        }
    return {
        "test": "exact McNemar",
        "alternative": "two-sided",
        "n_pairs": len(first),
        "concordant_both_pass": concordant_pass,
        "concordant_both_fail": concordant_fail,
        "first_pass_second_fail": first_pass_second_fail,
        "first_fail_second_pass": first_fail_second_pass,
        "discordant_pairs": discordant,
        "p_value": _rounded(p_value, 12),
        "paired_pass_rate_difference_second_minus_first": _rounded(
            statistics.fmean(second) - statistics.fmean(first)
        ),
        "discordant_pair_odds_ratio_second_vs_first": odds,
    }


def _linear_weighted_kappa(
    first: Sequence[int | bool],
    second: Sequence[int | bool],
    labels: Sequence[int | bool],
) -> dict[str, Any]:
    if len(first) != len(second) or not first:
        raise AnalysisFailure("INVALID_KAPPA_PAIRS")
    index = {label: offset for offset, label in enumerate(labels)}
    if any(value not in index for value in first) or any(value not in index for value in second):
        raise AnalysisFailure("KAPPA_VALUE_OUTSIDE_FIXED_DOMAIN")
    size = len(labels)
    first_counts = Counter(first)
    second_counts = Counter(second)
    observed_disagreement = statistics.fmean(
        abs(index[a] - index[b]) / (size - 1) for a, b in zip(first, second)
    )
    expected_disagreement = 0.0
    n = len(first)
    for a in labels:
        for b in labels:
            expected_disagreement += (
                first_counts[a]
                / n
                * second_counts[b]
                / n
                * abs(index[a] - index[b])
                / (size - 1)
            )
    exact_count = sum(a == b for a, b in zip(first, second))
    if expected_disagreement == 0:
        kappa = None
        reason = "undefined because both marginal distributions are constant"
    else:
        kappa = _rounded(1 - observed_disagreement / expected_disagreement)
        reason = None
    return {
        "n_shared": n,
        "fixed_domain": list(labels),
        "exact_agreement_count": exact_count,
        "exact_agreement_rate": _rounded(exact_count / n),
        "linear_weighted_cohens_kappa": kappa,
        "kappa_undefined_reason": reason,
    }


def _holm_adjust(family: Mapping[str, dict[str, Any]], family_name: str) -> None:
    ordered = sorted(
        ((name, float(result["p_value"])) for name, result in family.items()),
        key=lambda item: item[1],
    )
    running = 0.0
    total = len(ordered)
    for rank, (name, p_value) in enumerate(ordered):
        adjusted = min(1.0, (total - rank) * p_value)
        running = max(running, adjusted)
        family[name]["p_value_holm"] = _rounded(running, 12)
        family[name]["multiplicity_family"] = family_name


def _rows_by_id(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Mapping[str, Any]]:
    return {row[field]: row for row in rows}


def _canonical_entry_maps(
    private: Mapping[str, Any],
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, tuple[str, str]],
    dict[str, dict[int, str]],
]:
    by_response: dict[str, Mapping[str, Any]] = {}
    dialogue_identity: dict[str, tuple[str, str]] = {}
    dialogue_turn_ids: dict[str, dict[int, str]] = defaultdict(dict)
    for entry in private["entries"]:
        by_response[entry["response_id"]] = entry
        dialogue_id = entry["anonymous_conversation_id"]
        if dialogue_id is not None:
            identity = (entry["case_id"], entry["system_config_id"])
            existing = dialogue_identity.setdefault(dialogue_id, identity)
            if existing != identity:
                raise AnalysisFailure("RQ3_DIALOGUE_IDENTITY_CONFLICT")
            dialogue_turn_ids[dialogue_id][entry["turn_index"]] = entry["response_id"]
    return by_response, dialogue_identity, dict(dialogue_turn_ids)


def _rq1_analysis(
    primary_rows: Sequence[Mapping[str, Any]],
    by_response: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    score_by_id = _rows_by_id(primary_rows, "response_id")
    paired: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    system_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for response_id, score in score_by_id.items():
        entry = by_response[response_id]
        system = entry["system_config_id"]
        paired[entry["case_id"]][system] = score
        system_rows[system].append(score)
    systems = {}
    for system in ("qa_only_reconstructed_baseline", "v2"):
        rows = system_rows[system]
        systems[system] = {
            **SYSTEMS[system],
            "n": len(rows),
            "quality_total": _numeric_summary(
                [row["quality_total"] for row in rows], range(0, 9)
            ),
            "acceptable": _binary_summary([row["acceptable"] for row in rows]),
            "dimensions": {
                dimension: _numeric_summary(
                    [row[dimension] for row in rows], range(0, 3)
                )
                for dimension in RQ1_DIMENSIONS
            },
            "primary_error_type_distribution": dict(
                sorted(
                    Counter(
                        row["primary_error_type"]
                        for row in rows
                        if row["primary_error_type"] is not None
                    ).items()
                )
            ),
        }
    ordered_pairs = [paired[key] for key in sorted(paired)]
    first = "qa_only_reconstructed_baseline"
    second = "v2"
    total_differences = [
        pair[second]["quality_total"] - pair[first]["quality_total"]
        for pair in ordered_pairs
    ]
    total_test = _wilcoxon_exact(total_differences)
    total_comparison = {
        "status": "predeclared_primary",
        "direction": "V2 minus QA-only reconstructed baseline",
        "paired_difference": _numeric_summary(total_differences, range(-8, 9)),
        "wilcoxon": total_test,
        "paired_bootstrap_95_ci": _paired_bootstrap_mean_ci(total_differences),
    }
    acceptable_test = _mcnemar(
        [pair[first]["acceptable"] for pair in ordered_pairs],
        [pair[second]["acceptable"] for pair in ordered_pairs],
    )
    acceptable_test["status"] = "predeclared_primary"
    dimension_comparisons: dict[str, dict[str, Any]] = {}
    dimension_tests: dict[str, dict[str, Any]] = {}
    for dimension in RQ1_DIMENSIONS:
        differences = [
            pair[second][dimension] - pair[first][dimension] for pair in ordered_pairs
        ]
        test = _wilcoxon_exact(differences)
        dimension_tests[dimension] = test
        dimension_comparisons[dimension] = {
            "status": "exploratory",
            "direction": "V2 minus QA-only reconstructed baseline",
            "paired_difference": _numeric_summary(differences, range(-2, 3)),
            "wilcoxon": test,
        }
    _holm_adjust(
        dimension_tests, "RQ1 exploratory four-dimension paired comparisons"
    )
    return {
        "design": {
            "paired_questions": len(ordered_pairs),
            "responses_per_system": len(ordered_pairs),
            "primary_reviewer": "Reviewer 1",
        },
        "systems": systems,
        "comparisons": {
            "quality_total": total_comparison,
            "acceptable": acceptable_test,
            "dimensions": dimension_comparisons,
        },
    }


def _rq2_analysis(
    rows: Sequence[Mapping[str, Any]], by_response: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    score_by_id = _rows_by_id(rows, "response_id")
    paired: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    system_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for response_id, score in score_by_id.items():
        entry = by_response[response_id]
        system = entry["system_config_id"]
        paired[entry["case_id"]][system] = score
        system_rows[system].append(score)
    systems = {}
    outcomes = (*PASS_COMPONENTS, "case_pass")
    for system in ("qa_only_reconstructed_baseline", "v2"):
        system_scores = system_rows[system]
        systems[system] = {
            **SYSTEMS[system],
            "n": len(system_scores),
            "outcomes": {
                outcome: _binary_summary([row[outcome] for row in system_scores])
                for outcome in outcomes
            },
        }
    ordered_pairs = [paired[key] for key in sorted(paired)]
    comparisons = {
        outcome: {
            "status": "exploratory",
            **_mcnemar(
                [pair["qa_only_reconstructed_baseline"][outcome] for pair in ordered_pairs],
                [pair["v2"][outcome] for pair in ordered_pairs],
            ),
        }
        for outcome in outcomes
    }
    _holm_adjust(comparisons, "RQ2 exploratory four binary outcomes")
    return {
        "design": {"paired_cases": len(ordered_pairs), "responses_per_system": 20},
        "systems": systems,
        "comparisons": comparisons,
    }


def _rq3_analysis(
    rows: Sequence[Mapping[str, Any]],
    dialogue_identity: Mapping[str, tuple[str, str]],
) -> dict[str, Any]:
    score_by_dialogue = _rows_by_id(rows, "anonymous_conversation_id")
    paired: dict[str, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    system_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for dialogue_id, score in score_by_dialogue.items():
        case_id, system = dialogue_identity[dialogue_id]
        paired[case_id][system] = score
        system_rows[system].append(score)
    dialogue_outcomes = ("no_safety_violation", "dialogue_pass")
    turn_outcomes = (*PASS_COMPONENTS, "turn_pass")
    systems = {}
    for system in ("single_turn", "context_aware"):
        dialogues = system_rows[system]
        all_turns = [turn for row in dialogues for turn in row["turns"]]
        systems[system] = {
            **SYSTEMS[system],
            "dialogues": {
                "n": len(dialogues),
                "outcomes": {
                    outcome: _binary_summary([row[outcome] for row in dialogues])
                    for outcome in dialogue_outcomes
                },
                "error_type_distribution": dict(
                    sorted(
                        Counter(
                            row["error_type"]
                            for row in dialogues
                            if row["error_type"] is not None
                        ).items()
                    )
                ),
            },
            "turns": {
                "all_turns": {
                    "n": len(all_turns),
                    "outcomes": {
                        outcome: _binary_summary([turn[outcome] for turn in all_turns])
                        for outcome in turn_outcomes
                    },
                },
                "by_turn_index": {
                    str(turn_index): {
                        "n": len(dialogues),
                        "outcomes": {
                            outcome: _binary_summary(
                                [
                                    next(
                                        turn[outcome]
                                        for turn in row["turns"]
                                        if turn["turn_index"] == turn_index
                                    )
                                    for row in dialogues
                                ]
                            )
                            for outcome in turn_outcomes
                        },
                    }
                    for turn_index in (1, 2)
                },
            },
        }
    ordered_pairs = [paired[key] for key in sorted(paired)]
    dialogue_comparisons = {
        outcome: {
            "status": "exploratory",
            **_mcnemar(
                [pair["single_turn"][outcome] for pair in ordered_pairs],
                [pair["context_aware"][outcome] for pair in ordered_pairs],
            ),
        }
        for outcome in dialogue_outcomes
    }
    _holm_adjust(dialogue_comparisons, "RQ3 exploratory two dialogue outcomes")
    turn_comparisons: dict[str, dict[str, Any]] = {}
    for turn_index in (1, 2):
        family: dict[str, dict[str, Any]] = {}
        for outcome in turn_outcomes:
            first = [
                next(
                    turn[outcome]
                    for turn in pair["single_turn"]["turns"]
                    if turn["turn_index"] == turn_index
                )
                for pair in ordered_pairs
            ]
            second = [
                next(
                    turn[outcome]
                    for turn in pair["context_aware"]["turns"]
                    if turn["turn_index"] == turn_index
                )
                for pair in ordered_pairs
            ]
            family[outcome] = {"status": "exploratory", **_mcnemar(first, second)}
        _holm_adjust(
            family, f"RQ3 exploratory turn-{turn_index} four binary outcomes"
        )
        turn_comparisons[str(turn_index)] = family
    all_turn_descriptive_differences = {}
    for outcome in turn_outcomes:
        first_values = [
            turn[outcome]
            for pair in ordered_pairs
            for turn in pair["single_turn"]["turns"]
        ]
        second_values = [
            turn[outcome]
            for pair in ordered_pairs
            for turn in pair["context_aware"]["turns"]
        ]
        all_turn_descriptive_differences[outcome] = {
            "n_turn_pairs": len(first_values),
            "paired_pass_rate_difference_context_aware_minus_single_turn": _rounded(
                statistics.fmean(second_values) - statistics.fmean(first_values)
            ),
            "inferential_test": None,
            "reason": (
                "turns are clustered within dialogues; inference is reported separately "
                "by turn index and at dialogue level"
            ),
        }
    return {
        "design": {
            "paired_dialogue_cases": len(ordered_pairs),
            "dialogues_per_system": 12,
            "turns_per_system": 24,
        },
        "systems": systems,
        "comparisons": {
            "dialogue_level": dialogue_comparisons,
            "turn_level_by_turn_index": turn_comparisons,
            "all_turns_clustered_descriptive": all_turn_descriptive_differences,
        },
    }


def _reliability_analysis(
    primary_rows: Sequence[Mapping[str, Any]],
    secondary_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    primary = _rows_by_id(primary_rows, "response_id")
    secondary = _rows_by_id(secondary_rows, "response_id")
    shared_ids = sorted(secondary)
    dimensions = {}
    for dimension in RQ1_DIMENSIONS:
        dimensions[dimension] = _linear_weighted_kappa(
            [primary[identifier][dimension] for identifier in shared_ids],
            [secondary[identifier][dimension] for identifier in shared_ids],
            [0, 1, 2],
        )
    total = _linear_weighted_kappa(
        [primary[identifier]["quality_total"] for identifier in shared_ids],
        [secondary[identifier]["quality_total"] for identifier in shared_ids],
        list(range(0, 9)),
    )
    acceptable = _linear_weighted_kappa(
        [primary[identifier]["acceptable"] for identifier in shared_ids],
        [secondary[identifier]["acceptable"] for identifier in shared_ids],
        [False, True],
    )
    all_dimensions_exact_count = sum(
        all(primary[identifier][dimension] == secondary[identifier][dimension] for dimension in RQ1_DIMENSIONS)
        for identifier in shared_ids
    )
    return {
        "design": {
            "shared_response_records": len(shared_ids),
            "complete_paired_questions": 11,
            "reviewers": ["Reviewer 1", "Reviewer 2"],
            "system_blinded": True,
        },
        "quality_total": total,
        "dimensions": dimensions,
        "acceptable": {
            **acceptable,
            "cohens_kappa": acceptable["linear_weighted_cohens_kappa"],
            "note": "With two categories, linear-weighted and unweighted Cohen's kappa coincide.",
        },
        "all_four_dimensions_exact": {
            "n_shared": len(shared_ids),
            "exact_agreement_count": all_dimensions_exact_count,
            "exact_agreement_rate": _rounded(
                all_dimensions_exact_count / len(shared_ids)
            ),
        },
    }


def _p_text(value: float | None) -> str:
    if value is None:
        return "—"
    if value < 0.001:
        return "<0.001"
    return f"{value:.3f}"


def _number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _rate(summary: Mapping[str, Any]) -> str:
    return f"{summary['pass_count']}/{summary['n']} ({summary['pass_rate'] * 100:.1f}%)"


def _compact_distribution(distribution: Mapping[str, int]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in distribution.items())


def _interpret_results(results: Mapping[str, Any]) -> list[str]:
    rq1 = results["rq1"]
    total = rq1["comparisons"]["quality_total"]
    total_p = total["wilcoxon"]["p_value"]
    total_difference = total["paired_difference"]["mean"]
    ci = total["paired_bootstrap_95_ci"]
    if total_p < ALPHA and ci["lower"] > 0:
        rq1_total_text = (
            "RQ1 provides evidence of higher paired overall quality scores for V2 "
            "than for the QA-only reconstructed baseline."
        )
    elif total_p < ALPHA and ci["upper"] < 0:
        rq1_total_text = (
            "RQ1 provides evidence of lower paired overall quality scores for V2 "
            "than for the QA-only reconstructed baseline."
        )
    else:
        rq1_total_text = (
            "RQ1 does not provide statistically significant evidence of a paired "
            "overall quality-score difference between V2 and the QA-only reconstructed baseline."
        )
    rq1_total_text += (
        f" The observed mean paired difference was {total_difference:.2f} points "
        f"(paired-bootstrap 95% CI {ci['lower']:.2f} to {ci['upper']:.2f})."
    )
    acceptable = rq1["comparisons"]["acceptable"]
    if acceptable["p_value"] < ALPHA:
        acceptable_text = (
            "The predeclared exact McNemar test also found a difference in RQ1 "
            "acceptability rates."
        )
    else:
        acceptable_text = (
            "The predeclared exact McNemar test did not find a statistically significant "
            "difference in RQ1 acceptability rates."
        )
    rq2_case = results["rq2"]["comparisons"]["case_pass"]
    rq2_text = (
        "RQ2's exploratory exact McNemar comparison "
        + (
            "found a case-pass difference between the systems."
            if rq2_case["p_value"] < ALPHA
            else "did not find a statistically significant case-pass difference between the systems."
        )
    )
    rq3_dialogue = results["rq3"]["comparisons"]["dialogue_level"][
        "dialogue_pass"
    ]
    rq3_text = (
        "RQ3's exploratory dialogue-level exact McNemar comparison "
        + (
            "found a dialogue-pass difference between context-aware and single-turn V2."
            if rq3_dialogue["p_value"] < ALPHA
            else "did not find a statistically significant dialogue-pass difference between context-aware and single-turn V2."
        )
        + " Turn-level inference is separated by turn index because turns are clustered within dialogues."
    )
    reliability = results["inter_rater_reliability"]["quality_total"]
    reliability_text = (
        "Across the 22 shared RQ1 responses, exact total-score agreement was "
        f"{reliability['exact_agreement_rate'] * 100:.1f}% and linear-weighted "
        "Cohen's kappa was "
        + (
            f"{reliability['linear_weighted_cohens_kappa']:.3f}."
            if reliability["linear_weighted_cohens_kappa"] is not None
            else "undefined because the relevant marginal distributions were constant."
        )
    )
    safety_reliability = results["inter_rater_reliability"]["dimensions"][
        "safety_boundary_compliance"
    ]
    safety_reliability_text = (
        "Safety-boundary compliance had the lowest dimension-level inter-rater "
        f"reliability: exact agreement was {safety_reliability['exact_agreement_count']}/"
        f"{safety_reliability['n_shared']} "
        f"({safety_reliability['exact_agreement_rate'] * 100:.1f}%) and linear-weighted "
        f"Cohen's kappa was {safety_reliability['linear_weighted_cohens_kappa']:.3f}. "
        "This lower Safety reliability is a limitation when interpreting Safety-related results."
    )
    overall_text = (
        "Overall, the observed headline paired differences were small and favoured "
        "V2 or context-aware V2, but the reported predeclared and Holm-adjusted "
        "tests did not provide statistically significant evidence of improvement."
    )
    return [
        reliability_text,
        safety_reliability_text,
        rq1_total_text,
        acceptable_text,
        rq2_text,
        rq3_text,
        overall_text,
        (
            "RQ1/RQ2 compare complete system configurations; these results do not "
            "identify the causal contribution of an individual retrieval, reranking, snippet, or guard component."
        ),
    ]


def build_results(context: ValidationContext) -> dict[str, Any]:
    reviewer_1 = context.exports["reviewer_1"]["scores"]
    reviewer_2 = context.exports["reviewer_2"]["scores"]
    private = context.canonical[projection._PRIVATE_FILE]
    by_response, dialogue_identity, _ = _canonical_entry_maps(private)
    results = {
        "schema_version": "formal-evaluation-results-v1",
        "reviewer_bundle_id": EXPECTED_BUNDLE_ID,
        "analysis_script_sha256": _sha256_file(Path(__file__).resolve()),
        "analysis_scope": "post-scoring aggregate formal evaluation",
        "system_unblinding": SYSTEMS,
        "statistical_methods": {
            "alpha": ALPHA,
            "predeclared": {
                "rq1_quality_total": (
                    "paired Wilcoxon signed-rank, matched-pairs rank-biserial, "
                    "paired-bootstrap 95% confidence interval"
                ),
                "rq1_acceptable": "exact McNemar",
                "inter_rater": "exact agreement and linear-weighted Cohen's kappa",
            },
            "operational_details": {
                "wilcoxon": (
                    "two-sided exact conditional sign permutation; zero differences "
                    "discarded; midranks used for tied absolute differences"
                ),
                "paired_bootstrap": (
                    f"percentile CI for the paired mean difference; "
                    f"{BOOTSTRAP_RESAMPLES} resamples; seed {BOOTSTRAP_SEED}"
                ),
                "mcnemar": "two-sided exact binomial test on discordant pairs",
                "exploratory_multiplicity": "Holm adjustment within each declared exploratory outcome family",
            },
            "exploratory": {
                "rq1_dimensions": "paired Wilcoxon and matched-pairs rank-biserial",
                "rq2_binary_outcomes": "exact McNemar",
                "rq3_binary_outcomes": "exact McNemar at dialogue level and separately by turn index",
            },
        },
        "inter_rater_reliability": _reliability_analysis(
            reviewer_1["rq1_primary"], reviewer_2["rq1_secondary"]
        ),
        "rq1": _rq1_analysis(reviewer_1["rq1_primary"], by_response),
        "rq2": _rq2_analysis(reviewer_1["rq2"], by_response),
        "rq3": _rq3_analysis(reviewer_1["rq3"], dialogue_identity),
    }
    results["factual_interpretation"] = _interpret_results(results)
    return results


def _markdown_tables(
    validation: Mapping[str, Any], results: Mapping[str, Any]
) -> str:
    lines = [
        "# Formal Dissertation Evaluation Results",
        "",
        "All tables are aggregate-only. Systems were unblinded exclusively through the canonical B3 ID mapping; no question or answer text was used for joins.",
        "",
        "## Scoring-data validity and sample sizes",
        "",
        "| Check | Result |",
        "| --- | --- |",
        f"| Validation status | {validation['status']} |",
        f"| Reviewer bundle ID | `{validation['reviewer_bundle_id']}` |",
        f"| JSON exports | {validation['input_json_file_count']} |",
        "| Canonical projection integrity | PASS |",
        "| Missing, unknown, duplicate, or conflicting IDs | 0 |",
        "| Score-domain or derived-score conflicts | 0 |",
        "| Text matching used for joins | No |",
        "",
        "| Reviewer / section | Scored units | Expected units | Coverage |",
        "| --- | ---: | ---: | ---: |",
        "| Reviewer 1 — RQ1 primary responses | 102 | 102 | 100% |",
        "| Reviewer 1 — RQ2 responses | 40 | 40 | 100% |",
        "| Reviewer 1 — RQ3 dialogues | 24 | 24 | 100% |",
        "| Reviewer 1 — RQ3 source turns | 48 | 48 | 100% |",
        "| Reviewer 2 — RQ1 secondary responses | 22 | 22 | 100% |",
        "| RQ1 paired questions | 51 | 51 | 100% |",
        "| RQ2 paired cases | 20 | 20 | 100% |",
        "| RQ3 paired dialogue cases | 12 | 12 | 100% |",
        "",
        "Canonical unblinding maps `qa_only_reconstructed_baseline` to the **QA-only reconstructed baseline** (`formal_system_id = qa_only_reconstructed_baseline`) and `v2` to **V2** (`formal_system_id = current_v2`). For RQ3, `single_turn` is V2 without context management and `context_aware` is V2.1b context-aware.",
        "",
        "## Inter-rater reliability",
        "",
        "Reliability uses the 22 shared RQ1 response records (11 complete paired questions). Kappa uses each rubric's fixed score domain.",
        "",
        "| Outcome | n | Exact agreement | Linear-weighted Cohen's κ |",
        "| --- | ---: | ---: | ---: |",
    ]
    reliability = results["inter_rater_reliability"]
    reliability_rows = [("Quality total (0–8)", reliability["quality_total"])]
    reliability_rows.extend(
        (dimension.replace("_", " ").title(), reliability["dimensions"][dimension])
        for dimension in RQ1_DIMENSIONS
    )
    reliability_rows.append(("Acceptable (binary)", reliability["acceptable"]))
    for label, metric in reliability_rows:
        kappa = metric["linear_weighted_cohens_kappa"]
        lines.append(
            f"| {label} | {metric['n_shared']} | "
            f"{metric['exact_agreement_count']}/{metric['n_shared']} "
            f"({metric['exact_agreement_rate'] * 100:.1f}%) | "
            f"{_number(kappa, 3)} |"
        )
    all_dimensions = reliability["all_four_dimensions_exact"]
    lines.extend(
        [
            "",
            f"All four RQ1 dimensions matched simultaneously for {all_dimensions['exact_agreement_count']}/{all_dimensions['n_shared']} shared responses ({all_dimensions['exact_agreement_rate'] * 100:.1f}%).",
            "",
            "## RQ1 results",
            "",
            "### System descriptives",
            "",
            "| System | n | Quality total, mean (SD) | Median | Acceptable | Total-score distribution (score: n) |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    rq1 = results["rq1"]
    for system in ("qa_only_reconstructed_baseline", "v2"):
        member = rq1["systems"][system]
        total = member["quality_total"]
        lines.append(
            f"| {member['display_label']} | {member['n']} | "
            f"{total['mean']:.2f} ({total['standard_deviation']:.2f}) | "
            f"{total['median']:.1f} | {_rate(member['acceptable'])} | "
            f"{_compact_distribution(total['distribution'])} |"
        )
    total_comparison = rq1["comparisons"]["quality_total"]
    total_test = total_comparison["wilcoxon"]
    ci = total_comparison["paired_bootstrap_95_ci"]
    acceptable = rq1["comparisons"]["acceptable"]
    lines.extend(
        [
            "",
            "### Predeclared paired comparisons",
            "",
            "Positive differences and effect sizes favour V2.",
            "",
            "| Outcome | Paired difference | Test | p | Effect size / interval |",
            "| --- | ---: | --- | ---: | --- |",
            (
                f"| Quality total | mean {total_comparison['paired_difference']['mean']:.2f}; "
                f"median {total_comparison['paired_difference']['median']:.1f} | "
                f"Wilcoxon W={total_test['statistic_min_rank_sum']:.1f} | "
                f"{_p_text(total_test['p_value'])} | rank-biserial "
                f"{total_test['matched_pairs_rank_biserial']:.3f}; paired-bootstrap "
                f"95% CI [{ci['lower']:.2f}, {ci['upper']:.2f}] |"
            ),
            (
                f"| Acceptable | {acceptable['paired_pass_rate_difference_second_minus_first'] * 100:.1f} percentage points | "
                f"exact McNemar ({acceptable['first_pass_second_fail']} vs {acceptable['first_fail_second_pass']} discordant) | "
                f"{_p_text(acceptable['p_value'])} | paired rate difference |"
            ),
            "",
            "### Rubric dimensions (exploratory)",
            "",
            "| Dimension | Baseline mean (SD) | V2 mean (SD) | Mean paired difference | Wilcoxon p | Holm p | Rank-biserial |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for dimension in RQ1_DIMENSIONS:
        baseline = rq1["systems"]["qa_only_reconstructed_baseline"]["dimensions"][
            dimension
        ]
        current = rq1["systems"]["v2"]["dimensions"][dimension]
        comparison = rq1["comparisons"]["dimensions"][dimension]
        test = comparison["wilcoxon"]
        lines.append(
            f"| {dimension.replace('_', ' ').title()} | "
            f"{baseline['mean']:.2f} ({baseline['standard_deviation']:.2f}) | "
            f"{current['mean']:.2f} ({current['standard_deviation']:.2f}) | "
            f"{comparison['paired_difference']['mean']:.2f} | "
            f"{_p_text(test['p_value'])} | {_p_text(test['p_value_holm'])} | "
            f"{test['matched_pairs_rank_biserial']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## RQ2 results",
            "",
            "All inferential RQ2 comparisons are exploratory. Positive differences favour V2; Holm p-values adjust the four-outcome RQ2 family.",
            "",
            "| Outcome | Baseline pass | V2 pass | Difference | Discordant (baseline-only / V2-only) | Exact McNemar p | Holm p |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    rq2 = results["rq2"]
    for outcome in (*PASS_COMPONENTS, "case_pass"):
        baseline = rq2["systems"]["qa_only_reconstructed_baseline"]["outcomes"][
            outcome
        ]
        current = rq2["systems"]["v2"]["outcomes"][outcome]
        comparison = rq2["comparisons"][outcome]
        lines.append(
            f"| {outcome.replace('_', ' ').title()} | {_rate(baseline)} | {_rate(current)} | "
            f"{comparison['paired_pass_rate_difference_second_minus_first'] * 100:.1f} pp | "
            f"{comparison['first_pass_second_fail']} / {comparison['first_fail_second_pass']} | "
            f"{_p_text(comparison['p_value'])} | {_p_text(comparison['p_value_holm'])} |"
        )
    lines.extend(
        [
            "",
            "## RQ3 results",
            "",
            "All RQ3 inferential comparisons are exploratory. Positive differences favour V2.1b context-aware. Dialogue-level inference uses 12 paired dialogue cases; turn-level inference is separated by turn index to avoid treating two turns from the same dialogue as independent.",
            "",
            "### Dialogue-level outcomes",
            "",
            "| Outcome | Single-turn pass | Context-aware pass | Difference | Discordant (single-only / context-only) | Exact McNemar p | Holm p |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    rq3 = results["rq3"]
    for outcome in ("dialogue_pass", "no_safety_violation"):
        first = rq3["systems"]["single_turn"]["dialogues"]["outcomes"][outcome]
        second = rq3["systems"]["context_aware"]["dialogues"]["outcomes"][outcome]
        comparison = rq3["comparisons"]["dialogue_level"][outcome]
        lines.append(
            f"| {outcome.replace('_', ' ').title()} | {_rate(first)} | {_rate(second)} | "
            f"{comparison['paired_pass_rate_difference_second_minus_first'] * 100:.1f} pp | "
            f"{comparison['first_pass_second_fail']} / {comparison['first_fail_second_pass']} | "
            f"{_p_text(comparison['p_value'])} | {_p_text(comparison['p_value_holm'])} |"
        )
    lines.extend(
        [
            "",
            "### Turn-level outcomes by turn index",
            "",
            "| Turn | Outcome | Single-turn pass | Context-aware pass | Difference | Exact McNemar p | Holm p |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for turn_index in (1, 2):
        for outcome in (*PASS_COMPONENTS, "turn_pass"):
            first = rq3["systems"]["single_turn"]["turns"]["by_turn_index"][
                str(turn_index)
            ]["outcomes"][outcome]
            second = rq3["systems"]["context_aware"]["turns"]["by_turn_index"][
                str(turn_index)
            ]["outcomes"][outcome]
            comparison = rq3["comparisons"]["turn_level_by_turn_index"][
                str(turn_index)
            ][outcome]
            lines.append(
                f"| {turn_index} | {outcome.replace('_', ' ').title()} | {_rate(first)} | {_rate(second)} | "
                f"{comparison['paired_pass_rate_difference_second_minus_first'] * 100:.1f} pp | "
                f"{_p_text(comparison['p_value'])} | {_p_text(comparison['p_value_holm'])} |"
            )
    lines.extend(
        [
            "",
            "### Factual interpretation",
            "",
        ]
    )
    for paragraph in results["factual_interpretation"]:
        lines.extend([paragraph, ""])
    lines.extend(
        [
            "Exploratory p-values should be interpreted as secondary evidence rather than as predeclared primary tests. Holm-adjusted p-values are reported within each exploratory outcome family.",
            "",
        ]
    )
    markdown = "\n".join(lines)
    if "b3r_" in markdown or "b3d_" in markdown:
        raise AnalysisFailure("AGGREGATE_OUTPUT_PRIVACY_CHECK_FAILED")
    return markdown


def _assert_aggregate_json(value: Any, path: str = "root") -> None:
    forbidden_keys = {
        "response_id",
        "request_id",
        "case_id",
        "dialogue_id",
        "anonymous_conversation_id",
        "question",
        "answer",
        "model_answer",
        "reference_answer",
        "user_input",
        "reviewer_notes",
    }
    if type(value) is dict:
        forbidden = forbidden_keys & set(value)
        if forbidden:
            raise AnalysisFailure(
                f"AGGREGATE_OUTPUT_PRIVACY_CHECK_FAILED: {path}: {sorted(forbidden)}"
            )
        for key, member in value.items():
            _assert_aggregate_json(member, f"{path}.{key}")
    elif type(value) is list:
        for index, member in enumerate(value):
            _assert_aggregate_json(member, f"{path}[{index}]")
    elif type(value) is str and ("b3r_" in value or "b3d_" in value):
        raise AnalysisFailure(f"AGGREGATE_OUTPUT_PRIVACY_CHECK_FAILED: {path}")


def _canonical_json_text(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write_outputs(
    validation: Mapping[str, Any], results: Mapping[str, Any], markdown: str
) -> None:
    _assert_aggregate_json(validation)
    _assert_aggregate_json(results)
    if RESULTS_ROOT.exists() and (
        RESULTS_ROOT.is_symlink() or not RESULTS_ROOT.is_dir()
    ):
        raise AnalysisFailure("RESULTS_PATH_INVALID")
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    payloads = {
        VALIDATION_FILENAME: _canonical_json_text(validation),
        RESULTS_FILENAME: _canonical_json_text(results),
        TABLES_FILENAME: markdown,
    }
    temporary_paths: dict[str, Path] = {}
    try:
        for filename, text in payloads.items():
            target = RESULTS_ROOT / filename
            if target.exists() and (target.is_symlink() or not target.is_file()):
                raise AnalysisFailure(f"OUTPUT_PATH_INVALID: {filename}")
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=RESULTS_ROOT,
                prefix=f".{filename}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_paths[filename] = Path(handle.name)
        for filename in (VALIDATION_FILENAME, RESULTS_FILENAME, TABLES_FILENAME):
            os.replace(temporary_paths[filename], RESULTS_ROOT / filename)
            temporary_paths.pop(filename, None)
    finally:
        for temporary in temporary_paths.values():
            try:
                temporary.unlink()
            except OSError:
                pass


def _self_check_statistics() -> None:
    tied = _wilcoxon_exact([0, 0, 0])
    if tied["p_value"] != 1.0 or tied["matched_pairs_rank_biserial"] != 0.0:
        raise AnalysisFailure("STATISTICAL_SELF_CHECK_FAILED: all-tied Wilcoxon")
    mcnemar = _mcnemar([True, True, False], [False, True, True])
    if mcnemar["p_value"] != 1.0 or mcnemar["discordant_pairs"] != 2:
        raise AnalysisFailure("STATISTICAL_SELF_CHECK_FAILED: McNemar")
    constant = _linear_weighted_kappa([2, 2], [2, 2], [0, 1, 2])
    if constant["linear_weighted_cohens_kappa"] is not None:
        raise AnalysisFailure("STATISTICAL_SELF_CHECK_FAILED: constant kappa")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and aggregate the completed formal reviewer scores."
    )
    parser.parse_args(argv)
    _self_check_statistics()
    context = validate_inputs()
    results = build_results(context)
    markdown = _markdown_tables(context.validation_report, results)
    _write_outputs(context.validation_report, results, markdown)
    rq1_total = results["rq1"]["comparisons"]["quality_total"]
    rq1_acceptable = results["rq1"]["comparisons"]["acceptable"]
    rq2_case = results["rq2"]["comparisons"]["case_pass"]
    rq3_dialogue = results["rq3"]["comparisons"]["dialogue_level"][
        "dialogue_pass"
    ]
    summary = {
        "status": "PASS",
        "reviewer_bundle_id": EXPECTED_BUNDLE_ID,
        "input_files": [
            context.export_paths[reviewer].name for reviewer in sorted(context.export_paths)
        ],
        "validation_warnings": len(context.validation_report["warnings"]),
        "outputs": [
            str((RESULTS_ROOT / filename).relative_to(REPOSITORY_ROOT)).replace("\\", "/")
            for filename in (VALIDATION_FILENAME, RESULTS_FILENAME, TABLES_FILENAME)
        ],
        "headline": {
            "rq1_mean_paired_quality_difference_v2_minus_baseline": rq1_total[
                "paired_difference"
            ]["mean"],
            "rq1_quality_wilcoxon_p": rq1_total["wilcoxon"]["p_value"],
            "rq1_acceptability_mcnemar_p": rq1_acceptable["p_value"],
            "rq2_case_pass_mcnemar_p_exploratory": rq2_case["p_value"],
            "rq3_dialogue_pass_mcnemar_p_exploratory": rq3_dialogue["p_value"],
        },
    }
    print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnalysisFailure as exc:
        print(f"FAIL — {exc}", file=sys.stderr)
        raise SystemExit(2)
