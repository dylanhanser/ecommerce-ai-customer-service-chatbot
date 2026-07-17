#!/usr/bin/env python3
"""Anonymize sensitive information in final JD QA CSV data using re and pandas."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


REPORT_COLUMNS = (
    "total_rows",
    "rows_with_pii",
    "phone_replacements",
    "order_id_replacements",
    "product_id_replacements",
    "tracking_id_replacements",
    "address_replacements",
    "name_replacements",
    "link_replacements",
    "emoji_code_removed",
)
EXAMPLE_COLUMNS = (
    "original_question",
    "anonymized_question",
    "original_answer",
    "anonymized_answer",
    "pii_types",
)
TEXT_FIELDS = (
    "merged_question",
    "answer",
    "normalized_question",
    "normalized_answer",
    "alternative_questions",
)

URL_RE = re.compile(r"https?://[^\s，。；;！？!?<>\]\[\"']+", re.IGNORECASE)
ORDER_RE = re.compile(
    r"((?:查询\s*)?(?:订单号|订单编号|订单号码|order\s*id)\s*[:：#]?\s*)"
    r"([A-Za-z0-9_-]{8,})",
    re.IGNORECASE,
)
PRODUCT_RE = re.compile(
    r"((?:商品号|商品编号|商品编码|item\s*id)\s*[:：#]?\s*)"
    r"([A-Za-z0-9_-]{6,})",
    re.IGNORECASE,
)
MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
LANDLINE_RE = re.compile(r"(?<!\d)(?:0\d{2,3}[-—－ ]?)\d{7,8}(?!\d)")
PHONE_CONTEXT_RE = re.compile(
    r"((?:手机号|手机号码|联系电话|投诉电话|服务热线|客服电话|快递员|联系站点|致电)"
    r"[^\n，。；;！？!?\d]{0,8}[:：]?\s*)(\d{5,12})",
    re.IGNORECASE,
)
NAME_RE = re.compile(
    r"((?:收件人|收货人|联系人|姓名|名字)\s*[:：]\s*)([\u3400-\u9fff]{2,4})"
)
USER_ID_RE = re.compile(r"(?<![A-Za-z0-9_])(?:[A-Za-z0-9])\*{3,}[A-Za-z0-9_]{1,8}(?![A-Za-z0-9_])")
EMOJI_CODE_RE = re.compile(
    r"(?:#\s*E\s*[-_]\s*[A-Za-z]\s*\d+|/:\d{3})",
    re.IGNORECASE,
)
TRACKING_AFTER_RE = re.compile(
    r"((?:快递(?:单号)?|物流(?:单号)?|运单(?:号)?|单号|韵达|申通|圆通|京东快递)"
    r"[^\n，。；;！？!?]{0,12}?[:：#]?\s*)"
    r"([A-Za-z0-9-]{10,})",
    re.IGNORECASE,
)
TRACKING_BEFORE_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z0-9-]{10,})"
    r"(\s*(?:快递(?:单号)?|物流(?:单号)?|运单(?:号)?|单号))",
    re.IGNORECASE,
)

ADDRESS_LABEL_RE = re.compile(r"(?:收货地址|代收点地址|驿站地址|地址)\s*[:：]\s*.+")
ADDRESS_MARKER_RE = re.compile(
    r"[\u3400-\u9fff]{1,12}(?:省|市|区|县|镇|街道|村|路)"
    r"|\d+(?:号|栋|单元|楼|室)"
)
SENTENCE_SPLIT_RE = re.compile(r"([。！？!?；;\n]+)")


class Anonymizer:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def _sub(
        self,
        pattern: re.Pattern[str],
        replacement,
        text: str,
        counter_name: str,
        pii_type: str,
        detected: set[str],
    ) -> str:
        result, count = pattern.subn(replacement, text)
        if count:
            self.counts[counter_name] += count
            detected.add(pii_type)
        return result

    def _replace_urls(self, text: str, detected: set[str]) -> str:
        def replace(match: re.Match[str]) -> str:
            url = match.group(0)
            self.counts["link_replacements"] += 1
            lowered = url.casefold()
            if "item.jd.com" in lowered:
                detected.add("PRODUCT_LINK")
                return "[PRODUCT_LINK]"
            if "dd-static.jd.com" in lowered:
                detected.add("IMAGE_LINK")
                return "[IMAGE_LINK]"
            detected.add("URL")
            return "[URL]"

        return URL_RE.sub(replace, text)

    def _replace_addresses(self, text: str, detected: set[str]) -> str:
        parts = SENTENCE_SPLIT_RE.split(text)
        replacements = 0
        for index in range(0, len(parts), 2):
            segment = parts[index]
            if not segment.strip() or "[ADDRESS" in segment:
                continue
            label_match = ADDRESS_LABEL_RE.search(segment)
            markers = [
                match.group(0)
                for match in ADDRESS_MARKER_RE.finditer(segment)
                if not match.group(0).endswith("地区")
            ]
            if label_match:
                # A labelled address with actual content is safest to replace as
                # a whole message fragment, retaining surrounding punctuation.
                parts[index] = ADDRESS_LABEL_RE.sub("[ADDRESS]", segment)
                replacements += 1
            elif len(markers) >= 2:
                parts[index] = "[ADDRESS_RELATED_MESSAGE]"
                replacements += 1
        if replacements:
            self.counts["address_replacements"] += replacements
            detected.add("ADDRESS")
        return "".join(parts)

    def anonymize(self, value: object) -> tuple[str, set[str]]:
        text = "" if value is None else str(value)
        detected: set[str] = set()

        # Remove platform/emoji codes first; they carry no useful QA meaning.
        text = self._sub(
            EMOJI_CODE_RE, "", text, "emoji_code_removed", "EMOJI_CODE", detected
        )
        text = self._replace_urls(text, detected)

        # Labelled identifiers must be handled before generic phone/tracking
        # patterns so a long order number cannot be misclassified.
        text = self._sub(
            ORDER_RE, lambda match: match.group(1) + "[ORDER_ID]", text,
            "order_id_replacements", "ORDER_ID", detected,
        )
        text = self._sub(
            PRODUCT_RE, lambda match: match.group(1) + "[PRODUCT_ID]", text,
            "product_id_replacements", "PRODUCT_ID", detected,
        )
        text = self._sub(
            PHONE_CONTEXT_RE, lambda match: match.group(1) + "[PHONE]", text,
            "phone_replacements", "PHONE", detected,
        )
        text = self._sub(
            MOBILE_RE, "[PHONE]", text, "phone_replacements", "PHONE", detected
        )
        text = self._sub(
            LANDLINE_RE, "[PHONE]", text, "phone_replacements", "PHONE", detected
        )
        text = self._sub(
            TRACKING_AFTER_RE, lambda match: match.group(1) + "[TRACKING_ID]", text,
            "tracking_id_replacements", "TRACKING_ID", detected,
        )
        text = self._sub(
            TRACKING_BEFORE_RE, lambda match: "[TRACKING_ID]" + match.group(2), text,
            "tracking_id_replacements", "TRACKING_ID", detected,
        )
        text = self._sub(
            NAME_RE, lambda match: match.group(1) + "[NAME]", text,
            "name_replacements", "NAME", detected,
        )
        text = self._sub(
            USER_ID_RE, "[USER_ID]", text, "user_id_replacements", "USER_ID", detected
        )
        text = self._replace_addresses(text, detected)

        # Cleanup artifacts left by deleting platform codes without altering
        # meaningful Chinese semicolon-separated content.
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"(?:；\s*){2,}", "；", text)
        text = text.strip(" \t；;")
        return text, detected


def anonymize_file(input_path: Path, output_dir: Path) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "jd_turn_based_qa_anonymized.csv"
    report_path = output_dir / "anonymization_report.csv"
    examples_path = output_dir / "anonymization_examples.csv"

    frame = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = {"merged_question", "answer"}.difference(frame.columns)
    if missing:
        raise ValueError("输入 CSV 缺少字段：" + ", ".join(sorted(missing)))

    anonymizer = Anonymizer()
    example_rows: list[dict[str, str]] = []
    output_records: list[dict[str, str]] = []

    for record in frame.to_dict(orient="records"):
        original_question = record.get("merged_question", "")
        original_answer = record.get("answer", "")
        row_types: set[str] = set()
        processed: dict[str, str] = dict(record)

        for field in TEXT_FIELDS:
            if field not in processed:
                continue
            anonymized, field_types = anonymizer.anonymize(processed[field])
            processed[field] = anonymized
            row_types.update(field_types)

        processed["anonymized_question"] = processed.get("merged_question", "")
        processed["anonymized_answer"] = processed.get("answer", "")
        processed["pii_detected"] = "true" if row_types else "false"
        processed["pii_types"] = ";".join(sorted(row_types))
        output_records.append(processed)

        if row_types:
            example_rows.append(
                {
                    "original_question": original_question,
                    "anonymized_question": processed["anonymized_question"],
                    "original_answer": original_answer,
                    "anonymized_answer": processed["anonymized_answer"],
                    "pii_types": processed["pii_types"],
                }
            )

    output_frame = pd.DataFrame(output_records)
    output_frame.to_csv(output_path, index=False, encoding="utf-8-sig")

    report = {
        "total_rows": len(frame),
        "rows_with_pii": len(example_rows),
        "phone_replacements": anonymizer.counts["phone_replacements"],
        "order_id_replacements": anonymizer.counts["order_id_replacements"],
        "product_id_replacements": anonymizer.counts["product_id_replacements"],
        "tracking_id_replacements": anonymizer.counts["tracking_id_replacements"],
        "address_replacements": anonymizer.counts["address_replacements"],
        "name_replacements": anonymizer.counts["name_replacements"],
        "link_replacements": anonymizer.counts["link_replacements"],
        "emoji_code_removed": anonymizer.counts["emoji_code_removed"],
    }
    pd.DataFrame([report], columns=REPORT_COLUMNS).to_csv(
        report_path, index=False, encoding="utf-8-sig"
    )

    examples_frame = pd.DataFrame(example_rows, columns=EXAMPLE_COLUMNS)
    if len(examples_frame) > 100:
        examples_frame = examples_frame.sample(n=100)
    examples_frame.to_csv(examples_path, index=False, encoding="utf-8-sig")
    return len(frame), len(example_rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="脱敏最终京东 QA CSV 数据。")
    parser.add_argument("input", help="jd_turn_based_qa_filtered.csv 路径")
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
        total_rows, rows_with_pii = anonymize_file(input_path, output_dir)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"完成：处理 {total_rows} 行，其中 {rows_with_pii} 行检测到并处理了敏感信息")
    print(f"输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
