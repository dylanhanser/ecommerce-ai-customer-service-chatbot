#!/usr/bin/env python3
"""Filter standalone short keyword questions from turn-based JD QA data."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path


SHORT_KEYWORDS = (
    "尺码", "码数", "颜色", "运费", "快递", "物流", "材质", "质量", "发货", "退货", "换货",
    "退款", "防滑", "正品", "增高", "保暖", "鞋底", "补偿", "赔偿", "地址",
)
QUESTION_EXPRESSIONS = (
    "吗", "怎么", "什么", "多少", "有没有", "可以", "能不能", "多久", "哪里", "谁承担",
)
PUNCT_RE = re.compile(r"[\s\u3000，,。.!！?？~～、；;：:…·\-—_（）()【】\[\]{}]+")

SUMMARY_FIELDS = (
    "input_rows",
    "output_rows",
    "removed_short_keyword_rows",
    "removed_by_keyword_count",
)


def normalize_question(text: str) -> str:
    return PUNCT_RE.sub("", text or "").casefold()


def short_keyword_to_remove(question: str) -> str | None:
    normalized = normalize_question(question)
    if len(normalized) > 4:
        return None
    if any(expression in normalized for expression in QUESTION_EXPRESSIONS):
        return None
    return normalized if normalized in SHORT_KEYWORDS else None


def filter_file(input_path: Path, output_dir: Path) -> tuple[int, int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "jd_turn_based_qa_filtered.csv"
    removed_path = output_dir / "jd_short_keyword_removed.csv"
    summary_path = output_dir / "jd_short_keyword_filter_summary.csv"

    input_rows = 0
    output_rows = 0
    removed_rows = 0
    removed_counts: Counter[str] = Counter()

    with (
        input_path.open("r", encoding="utf-8-sig", newline="") as input_handle,
        output_path.open("w", encoding="utf-8-sig", newline="") as output_handle,
        removed_path.open("w", encoding="utf-8-sig", newline="") as removed_handle,
    ):
        reader = csv.DictReader(input_handle)
        fieldnames = reader.fieldnames or []
        if "merged_question" not in fieldnames:
            raise ValueError("输入 CSV 缺少字段：merged_question")

        output_writer = csv.DictWriter(output_handle, fieldnames=fieldnames)
        removed_writer = csv.DictWriter(
            removed_handle, fieldnames=tuple(fieldnames) + ("reject_reason",)
        )
        output_writer.writeheader()
        removed_writer.writeheader()

        for input_rows, row in enumerate(reader, start=1):
            keyword = short_keyword_to_remove(row.get("merged_question") or "")
            if keyword is None:
                output_writer.writerow(row)
                output_rows += 1
                continue
            removed_writer.writerow({**row, "reject_reason": "short_keyword_question"})
            removed_rows += 1
            removed_counts[keyword] += 1

    ordered_counts = {
        keyword: removed_counts[keyword] for keyword in SHORT_KEYWORDS if removed_counts[keyword]
    }
    summary = {
        "input_rows": input_rows,
        "output_rows": output_rows,
        "removed_short_keyword_rows": removed_rows,
        "removed_by_keyword_count": json.dumps(ordered_counts, ensure_ascii=False),
    }
    with summary_path.open("w", encoding="utf-8-sig", newline="") as summary_handle:
        writer = csv.DictWriter(summary_handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerow(summary)
    return input_rows, output_rows, removed_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="过滤 jd_turn_based_qa.csv 中仅由短业务关键词构成的问题。"
    )
    parser.add_argument("input", help="jd_turn_based_qa.csv 路径")
    parser.add_argument("-o", "--output-dir", default=".", help="输出 CSV 目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not input_path.is_file():
        print(f"Error: 找不到输入文件：{input_path}", file=sys.stderr)
        return 2
    try:
        input_rows, output_rows, removed_rows = filter_file(input_path, output_dir)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(
        f"完成：输入 {input_rows} 行，输出 {output_rows} 行，"
        f"删除 {removed_rows} 条短关键词问题"
    )
    print(f"输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
