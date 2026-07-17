#!/usr/bin/env python3
"""Build an anonymized cross-store evaluation candidate pool.

This is deliberately an orchestration layer.  It reuses the project's JD
parser, turn extraction, short-input filter, two anonymizers, final safety
cleaner, dedup normalizer, and category refiner.  External rows are never
added to a retrieval corpus and this module does not create embeddings.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from legacy_preprocessing import anonymize_qa_data as ANONYMIZER_V1
from legacy_preprocessing import anonymize_qa_data_v2 as ANONYMIZER_V2
from legacy_preprocessing import dedup_incremental_jd_questions as DEDUP
from legacy_preprocessing import extract_jd_turn_based_qa as EXTRACTOR
from legacy_preprocessing import filter_short_keyword_questions as SHORT_FILTER
from legacy_preprocessing import final_safety_clean_qa as SAFETY
from legacy_preprocessing import parse_jd_chat_txt as PARSER
from legacy_preprocessing import refine_categories as CATEGORIES


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE_ID = "external_store_v1"
EXPECTED_MONTHS = tuple(range(1, 7))
MONTH_RE = re.compile(r"(?<!\d)(0?[1-6])\s*月(?!\d)")

CANDIDATE_FIELDS = (
    "external_store_id",
    "external_session_id",
    "external_candidate_id",
    "source_file_id",
    "source_month",
    "question_time_start",
    "answer_time_end",
    "customer_turn_message_count",
    "service_turn_message_count",
    "final_question",
    "final_answer",
    "refined_category",
    "pii_detected",
    "pii_types",
    "candidate_status",
    "rejection_reason",
    "role_inference_used",
    "role_inference_method",
    "session_has_inferred_role",
    "inferred_service_sender_count",
    "role_inference_sender_session_count",
    "role_inference_threshold_sessions",
    "role_inference_coverage_ratio",
    "role_inference_first_ratio",
    "role_inference_last_ratio",
    "session_has_parser_anomaly",
    "parser_anomaly_count",
    "parser_anomaly_types",
)
REJECTED_FIELDS = (
    "external_store_id",
    "external_session_id",
    "source_file_id",
    "source_month",
    "refined_category",
    "rejection_reason",
    "safe_preview",
)
REJECTION_REASONS = frozenset(
    {
        "parse_failure",
        "empty_question",
        "empty_answer",
        "invalid_short_input",
        "missing_service_response",
        "pii_residual",
        "exact_duplicate",
        "normalized_duplicate",
        "missing_category",
        "invalid_timestamp",
        "unsupported_format",
        "other",
    }
)

IDENTITY_RE = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")
WECHAT_RE = re.compile(
    r"((?:微信(?:号|ID)?|[Vv]信|[Vv][Xx]|[Ww][Xx])\s*[:：]?\s*)"
    r"([A-Za-z][A-Za-z0-9_-]{4,})"
)
PAYMENT_RE = re.compile(
    r"((?:银行卡号|收款账号|支付宝账号|支付账号)\s*[:：]?\s*)"
    r"([A-Za-z0-9_-]{6,})"
)
RAW_PAYMENT_QR_RE = re.compile(r"(?:收款码|付款码)\s*[:：]\s*\S+")
ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|/(?:home|Users|tmp)/)")
TRAILING_PARTICLE_RE = re.compile(r"([啊呀呢吗吧哦噢哈嘛啦])\1+")


class InputValidationError(ValueError):
    """Raised without including a raw source filename in its message."""


@dataclass(frozen=True)
class SourceSpec:
    path: Path
    month: int
    source_file_id: str


@dataclass
class BuildResult:
    candidates: list[dict[str, object]]
    rejected: list[dict[str, object]]
    report: str
    monthly: dict[int, Counter]
    quality: Counter


@dataclass(frozen=True)
class SenderInferenceStats:
    sender_session_count: int
    threshold_sessions: int
    coverage_ratio: float
    first_ratio: float
    last_ratio: float


@dataclass(frozen=True)
class RoleInferenceResult:
    service_senders: frozenset[str]
    statistical_senders: frozenset[str]
    sender_stats: dict[str, SenderInferenceStats]
    threshold_sessions: int


class MemorySink:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []
        self.count = 0

    def append(self, row: dict[str, object]) -> None:
        self.rows.append(dict(row))
        self.count += 1


def _resolve_from_root(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (ROOT / path).resolve() if not path.is_absolute() else path.resolve()


def validate_sources(input_dir: str | Path, external_store_id: str) -> list[SourceSpec]:
    if external_store_id != DEFAULT_STORE_ID:
        raise InputValidationError("external-store-id must be the approved anonymous ID")
    directory = _resolve_from_root(input_dir)
    if not directory.is_dir():
        raise InputValidationError("input directory does not exist")
    if directory.name != external_store_id:
        raise InputValidationError("input directory must match the anonymous external store ID")

    entries = list(directory.iterdir())
    if any(not entry.is_file() for entry in entries):
        raise InputValidationError("input directory contains an unsupported entry")
    if any(entry.suffix.casefold() != ".txt" for entry in entries):
        raise InputValidationError("input directory must contain TXT files only")
    by_month: dict[int, Path] = {}
    for path in entries:
        matches = {int(value) for value in MONTH_RE.findall(path.name)}
        if len(matches) != 1:
            raise InputValidationError("each TXT filename must identify exactly one month from 1 to 6")
        month = next(iter(matches))
        if month in by_month:
            raise InputValidationError("duplicate month detected")
        if path.stat().st_size <= 0:
            raise InputValidationError("an empty TXT file was detected")
        by_month[month] = path.resolve()

    missing = set(EXPECTED_MONTHS).difference(by_month)
    if missing:
        raise InputValidationError("one or more required months are missing")
    if len(entries) != len(EXPECTED_MONTHS):
        raise InputValidationError("input directory must contain exactly six TXT files")
    return [
        SourceSpec(by_month[month], month, f"{external_store_id}_month_{month:02d}")
        for month in EXPECTED_MONTHS
    ]


def stable_external_session_id(
    external_store_id: str, source_filename: str, original_session_id: str
) -> str:
    payload = "\0".join((external_store_id, source_filename, original_session_id))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stable_external_candidate_id(
    external_store_id: str,
    source_file_id: str,
    external_session_id: str,
    qa_ordinal: int,
) -> str:
    payload = "\0".join(
        (external_store_id, source_file_id, external_session_id, str(qa_ordinal))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def _private_filename_markers(sources: Sequence[SourceSpec]) -> set[str]:
    cleaned: list[str] = []
    for source in sources:
        value = MONTH_RE.sub("", source.path.stem)
        value = re.sub(r"\d{4}[-_.年]?\d{0,2}[-_.月]?\d{0,2}日?", "", value)
        value = re.sub(r"(?i)京东|聊天记录|客服记录|导出|记录", "", value)
        value = re.sub(r"[\s._()（）\[\]【】\-]+", "", value)
        if len(value) >= 3:
            cleaned.append(value)
    markers = set(cleaned)
    if cleaned:
        prefix = os.path.commonprefix(cleaned).strip()
        if len(prefix) >= 3:
            markers.add(prefix)
    return {marker for marker in markers if marker and marker != DEFAULT_STORE_ID}


def _infer_service_senders(
    message_rows: Sequence[dict[str, object]],
) -> RoleInferenceResult:
    sessions: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in message_rows:
        sessions[str(row.get("session_id") or "")].append(row)
    coverage: dict[str, set[str]] = defaultdict(set)
    first: Counter[str] = Counter()
    last: Counter[str] = Counter()
    legacy_service: set[str] = set()
    for session_id, rows in sessions.items():
        if not rows:
            continue
        first[str(rows[0].get("sender") or "")] += 1
        last[str(rows[-1].get("sender") or "")] += 1
        for row in rows:
            sender = str(row.get("sender") or "")
            coverage[sender].add(session_id)
            if row.get("sender_type") == "service":
                legacy_service.add(sender)

    minimum_coverage = max(3, math.ceil(len(sessions) * 0.02))
    inferred = set(legacy_service)
    statistical: set[str] = set()
    sender_stats: dict[str, SenderInferenceStats] = {}
    for sender, session_ids in coverage.items():
        count = len(session_ids)
        if count < minimum_coverage:
            continue
        if last[sender] / count >= 0.80 and first[sender] / count <= 0.20:
            inferred.add(sender)
            if sender not in legacy_service:
                statistical.add(sender)
                sender_stats[sender] = SenderInferenceStats(
                    sender_session_count=count,
                    threshold_sessions=minimum_coverage,
                    coverage_ratio=count / len(sessions),
                    first_ratio=first[sender] / count,
                    last_ratio=last[sender] / count,
                )
    return RoleInferenceResult(
        service_senders=frozenset(inferred),
        statistical_senders=frozenset(statistical),
        sender_stats=sender_stats,
        threshold_sessions=minimum_coverage,
    )


def _session_messages(message_rows: Sequence[dict[str, object]]):
    sessions: dict[str, list[object]] = defaultdict(list)
    for order, row in enumerate(message_rows, start=1):
        time_text = str(row.get("message_time") or "")
        message = EXTRACTOR.Message(
            session_id=str(row.get("session_id") or ""),
            source_file=str(row.get("source_file") or ""),
            sender_type=str(row.get("sender_type") or ""),
            message_time=time_text,
            parsed_time=EXTRACTOR.parse_datetime(time_text),
            content=str(row.get("message_content") or ""),
            input_order=order,
        )
        setattr(
            message,
            "_role_inference_method",
            str(row.get("_role_inference_method") or "unresolved"),
        )
        setattr(message, "_role_inference_sender_key", str(row.get("sender") or ""))
        setattr(message, "_role_inference_stats", row.get("_role_inference_stats"))
        sessions[str(row.get("session_id") or "")].append(message)
    for rows in sessions.values():
        rows.sort(
            key=lambda message: (
                0 if message.parsed_time is not None else 1,
                message.parsed_time or EXTRACTOR.datetime.max,
                message.input_order,
            )
        )
    return sessions


def _format_ratio(value: float) -> str:
    return f"{value:.6f}"


def answer_role_lineage(
    service_items: Sequence[tuple[object, str]],
    *,
    session_has_inferred_role: bool,
) -> dict[str, object]:
    methods = [
        str(getattr(message, "_role_inference_method", "unresolved"))
        for message, _ in service_items
    ]
    method_set = set(methods)
    role_inference_used = "statistical_sender_rule" in method_set
    if not methods or not method_set.issubset(
        {"legacy_keyword", "statistical_sender_rule"}
    ):
        method = "unresolved"
    elif method_set == {"legacy_keyword"}:
        method = "legacy_keyword"
    elif method_set == {"statistical_sender_rule"}:
        method = "statistical_sender_rule"
    else:
        method = "mixed"

    inferred_by_sender: dict[str, SenderInferenceStats] = {}
    for message, _ in service_items:
        if getattr(message, "_role_inference_method", "") != "statistical_sender_rule":
            continue
        sender_key = str(getattr(message, "_role_inference_sender_key", ""))
        stats = getattr(message, "_role_inference_stats", None)
        if sender_key and isinstance(stats, SenderInferenceStats):
            inferred_by_sender[sender_key] = stats

    inferred_stats = list(inferred_by_sender.values())
    result: dict[str, object] = {
        "role_inference_used": "true" if role_inference_used else "false",
        "role_inference_method": method,
        "session_has_inferred_role": (
            "true" if session_has_inferred_role else "false"
        ),
        "inferred_service_sender_count": len(inferred_by_sender),
        "role_inference_sender_session_count": "",
        "role_inference_threshold_sessions": "",
        "role_inference_coverage_ratio": "",
        "role_inference_first_ratio": "",
        "role_inference_last_ratio": "",
    }
    if inferred_stats:
        result.update(
            {
                "role_inference_sender_session_count": min(
                    item.sender_session_count for item in inferred_stats
                ),
                "role_inference_threshold_sessions": max(
                    item.threshold_sessions for item in inferred_stats
                ),
                "role_inference_coverage_ratio": _format_ratio(
                    min(item.coverage_ratio for item in inferred_stats)
                ),
                "role_inference_first_ratio": _format_ratio(
                    max(item.first_ratio for item in inferred_stats)
                ),
                "role_inference_last_ratio": _format_ratio(
                    min(item.last_ratio for item in inferred_stats)
                ),
            }
        )
    return result


def session_parser_anomaly_fields(
    anomaly_rows: Sequence[dict[str, object]],
) -> dict[str, object]:
    anomaly_types = sorted(
        {
            str(row.get("error_type") or "").strip()
            for row in anomaly_rows
            if str(row.get("error_type") or "").strip()
        }
    )
    return {
        "session_has_parser_anomaly": "true" if anomaly_rows else "false",
        "parser_anomaly_count": len(anomaly_rows),
        "parser_anomaly_types": "|".join(anomaly_types),
    }


def _rejected_metadata(
    external_store_id: str,
    external_session_id: str,
    source: SourceSpec,
    reason: str,
    category: str = "",
) -> dict[str, object]:
    if reason not in REJECTION_REASONS:
        raise ValueError(f"Unsupported rejection reason: {reason}")
    return {
        "external_store_id": external_store_id,
        "external_session_id": external_session_id,
        "source_file_id": source.source_file_id,
        "source_month": source.month,
        "refined_category": category,
        "rejection_reason": reason,
        "safe_preview": "",
    }


def _legacy_rejection_reason(question: str, answer: str, reasons: Sequence[str]) -> str:
    if not question.strip():
        return "empty_question"
    if not answer.strip():
        return "empty_answer"
    if "bad_answer" in reasons:
        return "empty_answer"
    return "invalid_short_input"


def _replace_private_markers(
    text: str, private_markers: Iterable[str], service_senders: Iterable[str]
) -> tuple[str, set[str]]:
    result = text
    types: set[str] = set()
    for marker in sorted(set(private_markers), key=len, reverse=True):
        if len(marker) >= 3 and marker in result:
            result = result.replace(marker, "[EXTERNAL_STORE]")
            types.add("STORE_IDENTITY")
    generic_senders = {"客服", "商家", "客户", "用户", "系统"}
    for sender in sorted(set(service_senders), key=len, reverse=True):
        if len(sender) >= 2 and sender not in generic_senders and sender in result:
            result = result.replace(sender, "[SERVICE_AGENT]")
            types.add("SERVICE_AGENT")
    return result, types


def _supplemental_anonymize(text: str) -> tuple[str, set[str]]:
    detected: set[str] = set()

    def identity(_: re.Match[str]) -> str:
        detected.add("IDENTITY_ID")
        return "[IDENTITY_ID]"

    def wechat(match: re.Match[str]) -> str:
        detected.add("WECHAT_ID")
        return match.group(1) + "[WECHAT_ID]"

    def payment(match: re.Match[str]) -> str:
        detected.add("PAYMENT_INFO")
        return match.group(1) + "[PAYMENT_INFO]"

    def payment_qr(_: re.Match[str]) -> str:
        detected.add("PAYMENT_INFO")
        return "[PAYMENT_INFO]"

    text = IDENTITY_RE.sub(identity, text)
    text = WECHAT_RE.sub(wechat, text)
    text = PAYMENT_RE.sub(payment, text)
    text = RAW_PAYMENT_QR_RE.sub(payment_qr, text)
    return text, detected


def sanitize_text(
    text: str,
    anonymizer_v1,
    anonymizer_v2,
    safety_cleaner,
    private_markers: Iterable[str] = (),
    service_senders: Iterable[str] = (),
) -> tuple[str, set[str]]:
    value, detected = _replace_private_markers(text, private_markers, service_senders)
    value, supplemental = _supplemental_anonymize(value)
    detected.update(supplemental)
    value, found_v1 = anonymizer_v1.anonymize(value)
    detected.update(found_v1)
    value, found_v2 = anonymizer_v2.anonymize(value)
    detected.update(found_v2)
    value, found_final = safety_cleaner.clean(value)
    detected.update(found_final)
    return value, detected


def find_residual_pii(text: str, private_markers: Iterable[str] = ()) -> set[str]:
    hits: set[str] = set()
    if SAFETY.EMAIL_RE.search(text):
        hits.add("EMAIL")
    if SAFETY.MOBILE_RE.search(text) or SAFETY.LANDLINE_RE.search(text):
        hits.add("PHONE")
    if SAFETY.LONG_NUMBER_RE.search(text) or SAFETY.SPACED_NUMBER_RE.search(text):
        hits.add("LONG_NUMBER")
    if IDENTITY_RE.search(text):
        hits.add("IDENTITY_ID")
    if WECHAT_RE.search(text):
        hits.add("WECHAT_ID")
    if PAYMENT_RE.search(text) or RAW_PAYMENT_QR_RE.search(text):
        hits.add("PAYMENT_INFO")
    probe = SAFETY.SafetyCleaner()
    probed, changes = probe.clean(text)
    if probed != text:
        hits.update(changes)
    for marker in private_markers:
        if len(marker) >= 3 and marker in text:
            hits.add("STORE_IDENTITY")
    return hits


def candidate_rejection_reason(
    question: str,
    answer: str,
    refined_category: str,
    private_markers: Iterable[str] = (),
) -> str | None:
    if find_residual_pii(question, private_markers) or find_residual_pii(answer, private_markers):
        return "pii_residual"
    question_reason = SAFETY.question_rejection(question)
    if question_reason:
        return "empty_question" if not question.strip() else "invalid_short_input"
    if SAFETY.answer_rejection(answer):
        return "empty_answer"
    if not refined_category.strip():
        return "missing_category"
    return None


def normalize_candidate_question(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "")
    value = re.sub(r"\s+", " ", value).strip()
    value = TRAILING_PARTICLE_RE.sub(r"\1", value)
    return DEDUP.normalize(value)


def deduplicate_candidates(
    candidates: Sequence[dict[str, object]],
    sources_by_id: dict[str, SourceSpec],
) -> tuple[list[dict[str, object]], list[dict[str, object]], Counter]:
    kept: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    metrics: Counter = Counter()
    exact_seen: dict[str, dict[str, object]] = {}
    normalized_seen: dict[str, dict[str, object]] = {}
    pair_seen: set[tuple[str, str]] = set()

    ordered = sorted(
        candidates,
        key=lambda row: (
            int(row["source_month"]),
            str(row["question_time_start"]),
            str(row["external_session_id"]),
        ),
    )
    for row in ordered:
        question = str(row["final_question"])
        answer = str(row["final_answer"])
        normalized = normalize_candidate_question(question)
        prior = exact_seen.get(question)
        reason = "exact_duplicate" if prior is not None else ""
        if not reason:
            prior = normalized_seen.get(normalized)
            if prior is not None:
                reason = "normalized_duplicate"
        pair = (question, answer)
        if pair in pair_seen:
            metrics["question_answer_duplicate"] += 1
        if reason:
            metrics[reason] += 1
            if prior and prior.get("external_session_id") == row.get("external_session_id"):
                metrics["same_session_duplicate"] += 1
            if prior and prior.get("source_month") != row.get("source_month"):
                metrics["cross_month_duplicate"] += 1
            source = sources_by_id[str(row["source_file_id"])]
            rejected.append(
                _rejected_metadata(
                    str(row["external_store_id"]),
                    str(row["external_session_id"]),
                    source,
                    reason,
                    str(row["refined_category"]),
                )
            )
            continue
        kept.append(dict(row))
        exact_seen[question] = row
        normalized_seen[normalized] = row
        pair_seen.add(pair)
    return kept, rejected, metrics


def _parse_and_extract_source(
    source: SourceSpec,
    external_store_id: str,
    private_markers: set[str],
    monthly: Counter,
    quality: Counter,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    set[str],
    set[str],
    set[str],
]:
    messages_sink, summaries_sink, errors_sink = MemorySink(), MemorySink(), MemorySink()
    PARSER.parse_source(
        PARSER.TextSource(source.path.name, source.path.read_bytes()),
        0,
        messages_sink,
        summaries_sink,
        errors_sink,
    )
    monthly["sessions"] += len(summaries_sink.rows)
    monthly["messages"] += len(messages_sink.rows)
    monthly["parse_errors"] += len(errors_sink.rows)
    if errors_sink.rows:
        monthly["format_anomaly_file"] = 1

    anomalies_by_session: dict[str, list[dict[str, object]]] = defaultdict(list)
    for error_row in errors_sink.rows:
        error_session_id = str(error_row.get("session_id") or "")
        if error_session_id:
            anomalies_by_session[error_session_id].append(error_row)
    quality["parser_anomaly_sessions"] += len(anomalies_by_session)

    role_inference = _infer_service_senders(messages_sink.rows)
    service_senders = set(role_inference.service_senders)
    quality["statistical_service_sender_count"] += len(
        role_inference.statistical_senders
    )
    for row in messages_sink.rows:
        sender = str(row.get("sender") or "")
        legacy_service = row.get("sender_type") == "service"
        statistical_service = sender in role_inference.statistical_senders
        row["_role_inference_method"] = (
            "legacy_keyword"
            if legacy_service
            else "statistical_sender_rule"
            if statistical_service
            else "unresolved"
        )
        row["_role_inference_stats"] = role_inference.sender_stats.get(sender)
        row["sender_type"] = "service" if sender in service_senders else "customer"
        monthly[f"{row['sender_type']}_messages"] += 1
    sessions_with_inferred_role = {
        str(row.get("session_id") or "")
        for row in messages_sink.rows
        if row.get("_role_inference_method") == "statistical_sender_rule"
    }

    accepted: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    session_ids: set[str] = set()
    external_ids: set[str] = set()
    anonymizer_v1 = ANONYMIZER_V1.Anonymizer()
    anonymizer_v2 = ANONYMIZER_V2.V2Anonymizer()
    safety_cleaner = SAFETY.SafetyCleaner()

    for original_session_id, messages in sorted(_session_messages(messages_sink.rows).items()):
        session_ids.add(original_session_id)
        external_id = stable_external_session_id(
            external_store_id, source.path.name, original_session_id
        )
        external_ids.add(external_id)
        turns = EXTRACTOR.make_turns(messages)
        index = 0
        qa_ordinal = 0
        while index < len(turns):
            turn = turns[index]
            if turn.sender_type != "customer":
                index += 1
                continue
            qa_ordinal += 1
            monthly["extracted_qa"] += 1
            if index + 1 >= len(turns) or turns[index + 1].sender_type != "service":
                rejected.append(
                    _rejected_metadata(
                        external_store_id, external_id, source, "missing_service_response"
                    )
                )
                index += 1
                continue

            customer_items = EXTRACTOR.clean_turn(turn)
            service_items = EXTRACTOR.clean_turn(turns[index + 1])
            role_lineage = answer_role_lineage(
                service_items,
                session_has_inferred_role=(
                    original_session_id in sessions_with_inferred_role
                ),
            )
            anomaly_lineage = session_parser_anomaly_fields(
                anomalies_by_session.get(original_session_id, [])
            )
            row = EXTRACTOR.make_row(original_session_id, customer_items, service_items)
            question = str(row.get("merged_question") or "")
            answer = str(row.get("answer") or "")
            legacy_reasons = EXTRACTOR.rejection_reasons(question, answer)
            if legacy_reasons:
                rejected.append(
                    _rejected_metadata(
                        external_store_id,
                        external_id,
                        source,
                        _legacy_rejection_reason(question, answer, legacy_reasons),
                        str(row.get("category") or ""),
                    )
                )
                index += 2
                continue
            if SHORT_FILTER.short_keyword_to_remove(question) is not None:
                rejected.append(
                    _rejected_metadata(
                        external_store_id,
                        external_id,
                        source,
                        "invalid_short_input",
                        str(row.get("category") or ""),
                    )
                )
                index += 2
                continue
            if (
                EXTRACTOR.parse_datetime(str(row.get("question_time_start") or "")) is None
                or EXTRACTOR.parse_datetime(str(row.get("answer_time_end") or "")) is None
            ):
                rejected.append(
                    _rejected_metadata(
                        external_store_id,
                        external_id,
                        source,
                        "invalid_timestamp",
                        str(row.get("category") or ""),
                    )
                )
                index += 2
                continue

            final_question, question_pii = sanitize_text(
                question,
                anonymizer_v1,
                anonymizer_v2,
                safety_cleaner,
                private_markers,
                service_senders,
            )
            final_answer, answer_pii = sanitize_text(
                answer,
                anonymizer_v1,
                anonymizer_v2,
                safety_cleaner,
                private_markers,
                service_senders,
            )
            pii_types = question_pii | answer_pii
            refined, matches, _ = CATEGORIES.classify(final_question, final_answer)
            original_category = str(row.get("category") or "")
            if refined == "其他" and not matches and original_category:
                refined = "商品咨询" if original_category == "库存问题" else original_category
            reason = candidate_rejection_reason(
                final_question, final_answer, refined, private_markers
            )
            if reason:
                rejected.append(
                    _rejected_metadata(
                        external_store_id, external_id, source, reason, refined
                    )
                )
                index += 2
                continue

            accepted.append(
                {
                    "external_store_id": external_store_id,
                    "external_session_id": external_id,
                    "external_candidate_id": stable_external_candidate_id(
                        external_store_id,
                        source.source_file_id,
                        external_id,
                        qa_ordinal,
                    ),
                    "source_file_id": source.source_file_id,
                    "source_month": source.month,
                    "question_time_start": row.get("question_time_start") or "",
                    "answer_time_end": row.get("answer_time_end") or "",
                    "customer_turn_message_count": row.get("customer_turn_message_count") or 0,
                    "service_turn_message_count": row.get("service_turn_message_count") or 0,
                    "final_question": final_question,
                    "final_answer": final_answer,
                    "refined_category": refined,
                    "pii_detected": "true" if pii_types else "false",
                    "pii_types": ";".join(sorted(pii_types)),
                    "candidate_status": "accepted",
                    "rejection_reason": "",
                    **role_lineage,
                    **anomaly_lineage,
                    "_original_session_id": original_session_id,
                }
            )
            if pii_types:
                quality["pii_detected"] += 1
            index += 2
    return accepted, rejected, session_ids, external_ids, service_senders


def _percentile(values: Sequence[int], fraction: float) -> int | float:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def _report_text(
    sources: Sequence[SourceSpec],
    candidates: Sequence[dict[str, object]],
    rejected: Sequence[dict[str, object]],
    monthly: dict[int, Counter],
    quality: Counter,
    original_session_collisions: int,
    external_id_collisions: int,
) -> str:
    total_sessions = sum(monthly[m]["sessions"] for m in EXPECTED_MONTHS)
    total_messages = sum(monthly[m]["messages"] for m in EXPECTED_MONTHS)
    total_extracted = sum(monthly[m]["extracted_qa"] for m in EXPECTED_MONTHS)
    accepted_count = len(candidates)
    rejected_count = len(rejected)
    accepted_rate = accepted_count / total_extracted if total_extracted else 0.0
    category_counts = Counter(str(row["refined_category"]) for row in candidates)
    reason_counts = Counter(str(row["rejection_reason"]) for row in rejected)
    role_method_counts = Counter(
        str(row["role_inference_method"]) for row in candidates
    )
    role_inference_used_count = sum(
        str(row["role_inference_used"]).casefold() == "true" for row in candidates
    )
    inferred_role_candidate_count = sum(
        str(row["session_has_inferred_role"]).casefold() == "true"
        for row in candidates
    )
    inferred_role_session_count = len(
        {
            str(row["external_session_id"])
            for row in candidates
            if str(row["session_has_inferred_role"]).casefold() == "true"
        }
    )
    multiple_inferred_sender_count = sum(
        int(row["inferred_service_sender_count"]) > 1 for row in candidates
    )
    anomaly_candidate_count = sum(
        str(row["session_has_parser_anomaly"]).casefold() == "true"
        for row in candidates
    )
    anomaly_type_counts: Counter[str] = Counter()
    for row in candidates:
        for anomaly_type in str(row["parser_anomaly_types"]).split("|"):
            if anomaly_type:
                anomaly_type_counts[anomaly_type] += 1
    rows_by_session = Counter(str(row["external_session_id"]) for row in candidates)
    row_counts = list(rows_by_session.values())
    missing_counts = {}
    for field in CANDIDATE_FIELDS:
        if field == "rejection_reason":
            continue
        if field == "pii_types":
            missing_counts[field] = sum(
                str(row.get("pii_detected", "")).casefold() == "true"
                and not str(row.get(field, "")).strip()
                for row in candidates
            )
        elif field in {
            "role_inference_sender_session_count",
            "role_inference_threshold_sessions",
            "role_inference_coverage_ratio",
            "role_inference_first_ratio",
            "role_inference_last_ratio",
        }:
            missing_counts[field] = sum(
                str(row.get("role_inference_used", "")).casefold() == "true"
                and not str(row.get(field, "")).strip()
                for row in candidates
            )
        elif field == "parser_anomaly_types":
            missing_counts[field] = sum(
                str(row.get("session_has_parser_anomaly", "")).casefold() == "true"
                and not str(row.get(field, "")).strip()
                for row in candidates
            )
        else:
            missing_counts[field] = sum(
                not str(row.get(field, "")).strip() for row in candidates
            )

    lines = [
        "# external_store_v1 external evaluation candidate report",
        "",
        "## Input validation",
        "",
        f"- Recognized TXT files: {len(sources)}",
        "- Recognized months: 1, 2, 3, 4, 5, 6",
        "- Missing months: 0",
        "- Duplicate months: 0",
        "- Empty files: 0",
        f"- Files with parser anomalies: {sum(monthly[m]['format_anomaly_file'] for m in EXPECTED_MONTHS)}",
        f"- Parser anomaly records (aggregate): {sum(monthly[m]['parse_errors'] for m in EXPECTED_MONTHS)}",
        f"- Parser anomaly sessions: {quality['parser_anomaly_sessions']}",
        "",
        "## Monthly parsing summary",
        "",
        "| Month | Sessions | Messages | Customer messages | Service messages | Extracted QA | Accepted | Rejected |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for month in EXPECTED_MONTHS:
        stats = monthly[month]
        lines.append(
            f"| {month} | {stats['sessions']} | {stats['messages']} | "
            f"{stats['customer_messages']} | {stats['service_messages']} | "
            f"{stats['extracted_qa']} | {stats['accepted']} | {stats['rejected']} |"
        )
    lines.extend(
        [
            "",
            "Extracted QA counts customer-turn attempts; every excluded attempt is represented in the rejection totals.",
            "Parser anomaly records are reported separately because they are source-format diagnostics, not extracted QA rows.",
            "",
            "## Overall quality summary",
            "",
            f"- Total sessions: {total_sessions}",
            f"- Total messages: {total_messages}",
            f"- Total extracted QA: {total_extracted}",
            f"- Accepted candidates: {accepted_count}",
            f"- Rejected candidates: {rejected_count}",
            f"- Accepted rate: {accepted_rate:.2%}",
            "- Accepted rows per session: "
            f"min={min(row_counts) if row_counts else 0}, "
            f"median={statistics.median(row_counts) if row_counts else 0}, "
            f"p95={_percentile(row_counts, 0.95)}, max={max(row_counts) if row_counts else 0}",
            f"- Missing field counts: {', '.join(f'{k}={v}' for k, v in missing_counts.items())}",
            "- Refined category distribution: "
            + (", ".join(f"{key}={value}" for key, value in sorted(category_counts.items())) or "none"),
            "- Rejection reason distribution: "
            + (", ".join(f"{key}={value}" for key, value in sorted(reason_counts.items())) or "none"),
            f"- PII detected and safely anonymized before duplicate removal: {quality['pii_detected']}",
            f"- Accepted candidates with PII anonymization metadata: {sum(str(row['pii_detected']).casefold() == 'true' for row in candidates)}",
            f"- PII residual rejected: {reason_counts['pii_residual']}",
            f"- Exact duplicate rejected: {quality['exact_duplicate']}",
            f"- Normalized duplicate rejected: {quality['normalized_duplicate']}",
            f"- Question-and-answer duplicate observations: {quality['question_answer_duplicate']}",
            f"- Same-session duplicate observations: {quality['same_session_duplicate']}",
            f"- Cross-month duplicate observations: {quality['cross_month_duplicate']}",
            f"- Original parser session-ID collisions across files: {original_session_collisions}",
            f"- External session-ID collisions: {external_id_collisions}",
            f"- External candidate-ID collisions: {quality['external_candidate_id_collisions']}",
            "",
            "## Candidate traceability fields",
            "",
            "- `external_candidate_id`: deterministic anonymous ID derived only from approved anonymous IDs and the session-local QA ordinal; it does not use question, answer, sender, or a real store name.",
            "- `role_inference_used`: true only when at least one message retained in this candidate's answer was reclassified by the statistical sender rule.",
            "- `role_inference_method`: `legacy_keyword`, `statistical_sender_rule`, `mixed`, or `unresolved`, describing the retained answer messages.",
            "- `session_has_inferred_role`: whether any message anywhere in the session was reclassified from customer to service by the statistical rule; this is intentionally separate from candidate-level use.",
            "- `inferred_service_sender_count`: number of distinct statistically inferred senders retained in the answer; no sender identifier is emitted.",
            "- `role_inference_sender_session_count`, `role_inference_coverage_ratio`, `role_inference_first_ratio`, `role_inference_last_ratio`: conservative deterministic aggregates over inferred senders used by the answer (minimum, minimum, maximum, minimum respectively).",
            "- `role_inference_threshold_sessions`: unchanged minimum session-coverage threshold used by the existing statistical rule.",
            "- `session_has_parser_anomaly`, `parser_anomaly_count`, `parser_anomaly_types`: session-level association with parser diagnostics. Types are sorted, deduplicated, and pipe-delimited.",
            "",
            "## Role inference lineage summary",
            "",
            f"- Candidates with role_inference_used=true: {role_inference_used_count} ({role_inference_used_count / accepted_count if accepted_count else 0:.2%})",
            "- Method distribution: "
            + (", ".join(f"{key}={value}" for key, value in sorted(role_method_counts.items())) or "none"),
            f"- Candidates with session_has_inferred_role=true: {inferred_role_candidate_count}",
            f"- Distinct accepted sessions with an inferred role: {inferred_role_session_count}",
            f"- Unresolved candidates: {role_method_counts['unresolved']}",
            f"- Candidates using multiple inferred senders: {multiple_inferred_sender_count}",
            "",
            "## Parser anomaly lineage summary",
            "",
            f"- Candidates associated with a session parser anomaly: {anomaly_candidate_count}",
            "- Candidate-associated anomaly type distribution: "
            + (", ".join(f"{key}={value}" for key, value in sorted(anomaly_type_counts.items())) or "none"),
            "- Limitation: these fields record session-level association only; they do not claim that an anomaly caused an error in any candidate QA.",
            "",
            "## Privacy and safety",
            "",
            "- Candidate output contains only the approved anonymized schema: yes",
            f"- Residual PII in accepted candidates: {'yes' if any(find_residual_pii(str(r['final_question'])) or find_residual_pii(str(r['final_answer'])) for r in candidates) else 'no'}",
            "- Rejected CSV contains original text: no",
            "- Complete absolute paths in row-level outputs: no",
            "- Raw source filenames in row-level outputs: no",
            "- Raw session IDs in row-level outputs: no",
            "- Sender names or sender hashes in traceability fields: no",
            "- Real store names in traceability fields: no",
            "- Store and service-sender aliases derived during processing are replaced before output.",
            "- Manual review is still required: anonymization is rule-based, ambiguous category labels remain possible, and service answers are reference material rather than verified ground truth.",
            "",
            "## External evaluation boundary",
            "",
            "external_store_v1 is reserved exclusively for external evaluation.",
            "It was not added to the V1 or V2 retrieval corpus.",
            "No embeddings were generated from this dataset.",
            "",
            "## Review gate",
            "",
            "- Status: READY FOR 120-SAMPLE REVIEW",
            "",
        ]
    )
    return "\n".join(lines)


def _write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _serialized_rows(fields: Sequence[str], rows: Sequence[dict[str, object]]) -> str:
    return "\n".join(
        "|".join(str(row.get(field, "")) for field in fields) for row in rows
    )


def build_candidates(
    input_dir: str | Path,
    external_store_id: str = DEFAULT_STORE_ID,
    output_dir: str | Path = "data/external_eval/processed",
    report_path: str | Path = "outputs/reports/external_store_v1_report.md",
    rejected_path: str | Path = "outputs/rejected/external_store_v1_rejected.csv",
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> BuildResult:
    sources = validate_sources(input_dir, external_store_id)
    private_markers = _private_filename_markers(sources)
    monthly = {month: Counter() for month in EXPECTED_MONTHS}
    quality: Counter = Counter()
    provisional: list[dict[str, object]] = []
    rejected: list[dict[str, object]] = []
    original_id_files: dict[str, set[str]] = defaultdict(set)
    all_external_ids: list[str] = []
    all_service_senders: set[str] = set()

    for source in sources:
        (
            accepted_rows,
            rejected_rows,
            original_ids,
            external_ids,
            service_senders,
        ) = _parse_and_extract_source(
            source, external_store_id, private_markers, monthly[source.month], quality
        )
        provisional.extend(accepted_rows)
        rejected.extend(rejected_rows)
        for session_id in original_ids:
            original_id_files[session_id].add(source.source_file_id)
        all_external_ids.extend(external_ids)
        all_service_senders.update(service_senders)

    sources_by_id = {source.source_file_id: source for source in sources}
    candidates, duplicate_rejected, duplicate_metrics = deduplicate_candidates(
        provisional, sources_by_id
    )
    rejected.extend(duplicate_rejected)
    quality.update(duplicate_metrics)
    candidate_ids = [str(row["external_candidate_id"]) for row in candidates]
    quality["external_candidate_id_collisions"] = len(candidate_ids) - len(
        set(candidate_ids)
    )
    if quality["external_candidate_id_collisions"]:
        raise RuntimeError("external candidate ID uniqueness invariant failed")

    for row in candidates:
        monthly[int(row["source_month"])]["accepted"] += 1
    for row in rejected:
        monthly[int(row["source_month"])]["rejected"] += 1
    for month in EXPECTED_MONTHS:
        if monthly[month]["accepted"] + monthly[month]["rejected"] != monthly[month]["extracted_qa"]:
            raise RuntimeError("candidate accounting invariant failed")

    original_collisions = sum(len(files) > 1 for files in original_id_files.values())
    external_collisions = len(all_external_ids) - len(set(all_external_ids))
    report = _report_text(
        sources,
        candidates,
        rejected,
        monthly,
        quality,
        original_collisions,
        external_collisions,
    )

    candidate_text = _serialized_rows(CANDIDATE_FIELDS, candidates)
    rejected_text = _serialized_rows(REJECTED_FIELDS, rejected)
    forbidden = [source.path.name for source in sources]
    forbidden.extend(private_markers)
    if any(marker and marker in candidate_text + rejected_text + report for marker in forbidden):
        raise RuntimeError("privacy invariant failed: a private source marker reached output")
    if ABSOLUTE_PATH_RE.search(candidate_text + rejected_text + report):
        raise RuntimeError("privacy invariant failed: an absolute path reached output")
    generic_senders = {"客服", "商家", "客户", "用户", "系统"}
    private_service_senders = {
        sender
        for sender in all_service_senders
        if len(sender) >= 2 and sender not in generic_senders
    }
    candidate_narrative = "\n".join(
        f"{row['final_question']}\n{row['final_answer']}" for row in candidates
    )
    if any(sender in candidate_narrative for sender in private_service_senders):
        raise RuntimeError("privacy invariant failed: a sender alias reached candidate text")
    if any(find_residual_pii(str(row["final_question"]), private_markers) or find_residual_pii(str(row["final_answer"]), private_markers) for row in candidates):
        raise RuntimeError("privacy invariant failed: residual PII reached accepted output")

    public_candidates = [
        {field: row.get(field, "") for field in CANDIDATE_FIELDS} for row in candidates
    ]
    public_rejected = [
        {field: row.get(field, "") for field in REJECTED_FIELDS} for row in rejected
    ]
    result = BuildResult(public_candidates, public_rejected, report, monthly, quality)
    if dry_run:
        return result

    candidate_path = _resolve_from_root(output_dir) / f"{external_store_id}_candidates.csv"
    report_output = _resolve_from_root(report_path)
    rejected_output = _resolve_from_root(rejected_path)
    targets = (candidate_path, rejected_output, report_output)
    if not overwrite and any(path.exists() for path in targets):
        raise FileExistsError("one or more output files already exist; use --overwrite explicitly")
    _write_csv(candidate_path, CANDIDATE_FIELDS, public_candidates)
    _write_csv(rejected_output, REJECTED_FIELDS, public_rejected)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(report, encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an anonymized external evaluation candidate pool."
    )
    parser.add_argument(
        "--input-dir",
        default="data/external_eval/raw/external_store_v1",
        help="Directory containing exactly one TXT for each month from 1 to 6",
    )
    parser.add_argument("--external-store-id", default=DEFAULT_STORE_ID)
    parser.add_argument("--output-dir", default="data/external_eval/processed")
    parser.add_argument(
        "--report-path", default="outputs/reports/external_store_v1_report.md"
    )
    parser.add_argument(
        "--rejected-path", default="outputs/rejected/external_store_v1_rejected.csv"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = build_candidates(
            args.input_dir,
            args.external_store_id,
            args.output_dir,
            args.report_path,
            args.rejected_path,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
        )
    except (InputValidationError, FileExistsError, RuntimeError, OSError, ValueError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    total_sessions = sum(result.monthly[m]["sessions"] for m in EXPECTED_MONTHS)
    total_messages = sum(result.monthly[m]["messages"] for m in EXPECTED_MONTHS)
    total_extracted = sum(result.monthly[m]["extracted_qa"] for m in EXPECTED_MONTHS)
    mode = "Dry run complete" if args.dry_run else "Build complete"
    print(
        f"{mode}: files=6 sessions={total_sessions} messages={total_messages} "
        f"extracted={total_extracted} accepted={len(result.candidates)} "
        f"rejected={len(result.rejected)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
