#!/usr/bin/env python3
"""Remove incremental intermediate questions from JD contextual QA pairs."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path


REMOVED_FIELDS = (
    "session_id",
    "removed_question",
    "kept_question",
    "removed_answer",
    "kept_answer",
    "remove_reason",
)
SUMMARY_FIELDS = (
    "input_rows",
    "output_rows",
    "removed_incremental_rows",
    "affected_sessions",
    "category_distribution_after_dedup",
)

BUSINESS_KEYWORDS = (
    "尺码", "码数", "偏大", "偏小", "发货", "快递", "物流", "退货", "退款", "换货", "运费",
    "质量", "开胶", "发错", "补偿", "赔偿", "材质", "防滑", "正品", "颜色", "无货", "拒收",
    "派送", "京东余额", "地址", "拦截",
)
TOPIC_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("size", ("尺码", "码数", "偏大", "偏小")),
    ("shipping", ("发货", "快递", "物流", "拒收", "派送", "地址", "拦截")),
    ("refund", ("退货", "退款")),
    ("exchange", ("换货",)),
    ("freight", ("运费",)),
    ("quality", ("质量", "开胶", "发错")),
    ("compensation", ("补偿", "赔偿", "京东余额")),
    ("product", ("材质", "防滑", "正品", "颜色")),
    ("stock", ("无货",)),
)

PUNCT_RE = re.compile(r"[\s\u3000，,。.!！?？~～、；;：:…·\-]+")
SENTENCE_SPLIT_RE = re.compile(r"[；;。！？!?\n]+")
GENERIC_PHRASES = {
    "怎么办", "怎么办呀", "怎么处理", "咋处理", "这咋办", "可以吗", "行吗", "退吗", "换吗",
    "然后呢", "什么意思", "为什么", "那呢", "这个呢", "还没发", "无货了", "不行", "不可以",
    "好的", "好吧", "谢谢", "嗯嗯", "是吗", "对吗",
}


def normalize(text: str) -> str:
    return PUNCT_RE.sub("", text or "").casefold()


NORMALIZED_GENERIC = {normalize(value) for value in GENERIC_PHRASES}


def similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def keyword_set(text: str) -> set[str]:
    return {keyword for keyword in BUSINESS_KEYWORDS if keyword in (text or "")}


def topic_set(text: str) -> set[str]:
    return {
        topic
        for topic, keywords in TOPIC_GROUPS
        if any(keyword in (text or "") for keyword in keywords)
    }


def key_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    for raw in SENTENCE_SPLIT_RE.split(text or ""):
        phrase = normalize(raw)
        if len(phrase) >= 2 and phrase not in NORMALIZED_GENERIC:
            phrases.append(phrase)
    return list(dict.fromkeys(phrases))


def all_key_phrases_contained(earlier: str, later: str) -> bool:
    phrases = key_phrases(earlier)
    later_normalized = normalize(later)
    return bool(phrases) and all(phrase in later_normalized for phrase in phrases)


def answer_clearly_different(earlier: dict, later: dict) -> bool:
    earlier_answer = normalize(earlier.get("answer", ""))
    later_answer = normalize(later.get("answer", ""))
    if similarity(earlier_answer, later_answer) >= 0.80:
        return False
    # Both answers must contain enough substance for "clearly different" to be
    # meaningful; tiny acknowledgements should not block incremental cleanup.
    return len(earlier_answer) >= 8 and len(later_answer) >= 8


def protected_as_different_topic(earlier: dict, later: dict) -> bool:
    earlier_category = (earlier.get("category") or "其他").strip()
    later_category = (later.get("category") or "其他").strip()
    if (
        earlier_category != later_category
        and earlier_category != "其他"
        and later_category != "其他"
    ):
        return True

    earlier_topics = topic_set(earlier.get("merged_question", ""))
    later_topics = topic_set(later.get("merged_question", ""))
    # Protect both disjoint topics and a later question that adds a genuinely
    # new topic (e.g. 运费 -> 运费 + 鞋底材质). Merely adding more detail within
    # the same topic remains eligible for incremental deduplication.
    if earlier_topics and later_topics and (
        earlier_topics.isdisjoint(later_topics) or bool(later_topics - earlier_topics)
    ):
        return True
    return False


def incremental_reason(earlier: dict, later: dict) -> str | None:
    earlier_question = earlier.get("merged_question", "")
    later_question = later.get("merged_question", "")
    earlier_normalized = normalize(earlier_question)
    later_normalized = normalize(later_question)
    if not earlier_normalized or not later_normalized:
        return None
    if protected_as_different_topic(earlier, later):
        return None

    # A cumulative-looking question can still receive a genuinely different
    # answer in a later turn. Preserve both rows when both answers are
    # substantive and their normalized similarity is below 0.80.
    if answer_clearly_different(earlier, later):
        return None

    later_is_longer = len(later_normalized) > len(earlier_normalized)
    # Equal questions are repeated questions, not incremental versions.
    if not later_is_longer:
        return None
    if later_normalized.startswith(earlier_normalized):
        return "earlier_question_is_prefix"
    if earlier_normalized in later_normalized:
        return "earlier_question_contained_in_later"

    score = similarity(earlier_normalized, later_normalized)
    if score >= 0.90:
        return f"question_similarity_{score:.3f}"
    if all_key_phrases_contained(earlier_question, later_question):
        return "all_key_phrases_contained_in_later"
    return None


def integer_value(row: dict, field: str) -> int:
    try:
        return int(float(row.get(field, 0) or 0))
    except (TypeError, ValueError):
        return 0


def answer_specificity(answer: str) -> tuple[int, int, int]:
    normalized = normalize(answer)
    keyword_count = len(keyword_set(answer))
    number_count = sum(character.isdigit() for character in normalized)
    return keyword_count, number_count, len(normalized)


def quality_key(index: int, row: dict) -> tuple[int, int, tuple[int, int, int], int]:
    return (
        len(normalize(row.get("merged_question", ""))),
        integer_value(row, "context_message_count"),
        answer_specificity(row.get("answer", "")),
        index,  # Prefer the later record when all quality signals tie.
    )


class UnionFind:
    def __init__(self, size: int):
        self.parent = list(range(size))

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[left_root] = right_root


def deduplicate_session(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    if len(rows) < 2:
        return rows, []

    union_find = UnionFind(len(rows))
    edge_reasons: dict[tuple[int, int], str] = {}
    for earlier_index in range(len(rows) - 1):
        for later_index in range(earlier_index + 1, len(rows)):
            reason = incremental_reason(rows[earlier_index], rows[later_index])
            if reason:
                union_find.union(earlier_index, later_index)
                edge_reasons[(earlier_index, later_index)] = reason

    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        components[union_find.find(index)].append(index)

    keep_indices: set[int] = set()
    removed_rows: list[dict] = []
    for indices in components.values():
        kept_index = max(indices, key=lambda index: quality_key(index, rows[index]))
        keep_indices.add(kept_index)
        for removed_index in indices:
            if removed_index == kept_index:
                continue
            direct_reason = edge_reasons.get((removed_index, kept_index))
            if direct_reason is None:
                direct_reason = "incremental_chain_to_more_complete_question"
            removed_rows.append(
                {
                    "session_id": rows[removed_index].get("session_id", ""),
                    "removed_question": rows[removed_index].get("merged_question", ""),
                    "kept_question": rows[kept_index].get("merged_question", ""),
                    "removed_answer": rows[removed_index].get("answer", ""),
                    "kept_answer": rows[kept_index].get("answer", ""),
                    "remove_reason": direct_reason,
                }
            )
    kept_rows = [row for index, row in enumerate(rows) if index in keep_indices]
    return kept_rows, removed_rows


def load_rows(path: Path) -> tuple[list[str], dict[str, list[dict]], int]:
    sessions: dict[str, list[dict]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required = {"session_id", "question_time_start", "merged_question", "answer", "category"}
        missing = required.difference(fieldnames)
        if missing:
            raise ValueError("输入 CSV 缺少字段：" + ", ".join(sorted(missing)))
        input_rows = 0
        for input_rows, row in enumerate(reader, start=1):
            sessions[(row.get("session_id") or "").strip()].append(row)
    for rows in sessions.values():
        rows.sort(key=lambda row: (row.get("question_time_start") or "", row.get("question_time_end") or ""))
    return fieldnames, sessions, input_rows


def run(input_path: Path, output_dir: Path) -> tuple[int, int, int, int]:
    fieldnames, sessions, input_rows = load_rows(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "jd_context_qa_pairs_v3.csv"
    removed_path = output_dir / "jd_incremental_removed.csv"
    summary_path = output_dir / "jd_incremental_dedup_summary.csv"

    output_rows = 0
    removed_count = 0
    affected_sessions = 0
    category_counts: Counter[str] = Counter()

    with (
        output_path.open("w", encoding="utf-8-sig", newline="") as output_handle,
        removed_path.open("w", encoding="utf-8-sig", newline="") as removed_handle,
    ):
        output_writer = csv.DictWriter(output_handle, fieldnames=fieldnames)
        removed_writer = csv.DictWriter(removed_handle, fieldnames=REMOVED_FIELDS)
        output_writer.writeheader()
        removed_writer.writeheader()

        for session_id in sorted(sessions):
            kept, removed = deduplicate_session(sessions[session_id])
            output_writer.writerows(kept)
            removed_writer.writerows(removed)
            output_rows += len(kept)
            removed_count += len(removed)
            if removed:
                affected_sessions += 1
            category_counts.update((row.get("category") or "其他") for row in kept)

    summary = {
        "input_rows": input_rows,
        "output_rows": output_rows,
        "removed_incremental_rows": removed_count,
        "affected_sessions": affected_sessions,
        "category_distribution_after_dedup": json.dumps(
            dict(sorted(category_counts.items())), ensure_ascii=False
        ),
    }
    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerow(summary)
    return input_rows, output_rows, removed_count, affected_sessions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="删除京东 QA 中同一会话内逐步累加的问题中间版本。"
    )
    parser.add_argument("input", help="jd_context_qa_pairs_v2.csv 路径")
    parser.add_argument("-o", "--output-dir", default=".", help="v3 CSV 输出目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not input_path.is_file():
        print(f"Error: 找不到输入文件：{input_path}", file=sys.stderr)
        return 2
    try:
        input_rows, output_rows, removed_rows, affected_sessions = run(input_path, output_dir)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(
        f"完成：输入 {input_rows} 行，输出 {output_rows} 行，"
        f"删除 {removed_rows} 行，影响 {affected_sessions} 个会话"
    )
    print(f"输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
