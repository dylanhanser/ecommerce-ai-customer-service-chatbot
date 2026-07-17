#!/usr/bin/env python3
"""Second-pass anonymization for sensitive data missed by anonymize_qa_data.py."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


TEXT_FIELDS = (
    "merged_question",
    "answer",
    "anonymized_question",
    "anonymized_answer",
    "normalized_question",
    "normalized_answer",
    "alternative_questions",
)
REPORT_COLUMNS = (
    "total_rows",
    "rows_with_new_pii_found",
    "product_id_replacements",
    "order_id_replacements",
    "tracking_id_replacements",
    "long_number_replacements",
    "phone_near_name_replacements",
    "phone_near_address_replacements",
    "address_replacements",
    "link_replacements",
)
EXAMPLE_COLUMNS = (
    "before_question",
    "after_question",
    "before_answer",
    "after_answer",
    "pii_types",
)

URL_RE = re.compile(r"https?://[^\s，。；;！？!?<>\]\[\"']+", re.IGNORECASE)
PRODUCT_ID_RE = re.compile(
    r"商品[^\d\n]{0,5}?(?:id|编号|号)\s*[:：#]?\s*\d{6,}",
    re.IGNORECASE,
)
ORDER_ID_RE = re.compile(
    r"(?:(?:订单)[^\d\n]{0,5}?(?:id|编号|号)|order\s*id)\s*[:：#]?\s*\d{6,}",
    re.IGNORECASE,
)
TRACKING_LABEL_RE = re.compile(
    r"((?:快递(?:单号)?|物流(?:单号)?|运单(?:号)?|单号|韵达|申通|圆通|京东快递)"
    r"[^\n，。；;！？!?\d]{0,10}?[:：#]?\s*)(\d{10,})",
    re.IGNORECASE,
)
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{10,}(?!\d)")

PHONE_AFTER_SEGMENT_RE = re.compile(r"(\[PHONE\])([^，,。；;！？!?\n]{2,80})")
PHONE_AFTER_NAME_RE = re.compile(
    r"(\[PHONE\])([\u3400-\u9fff]{2,4})(?=$|[，,。；;！？!?\s])"
)
NAME_BEFORE_PHONE_RE = re.compile(
    r"(?<![\u3400-\u9fff])([\u3400-\u9fff]{2,4})(\s*[，,|]?\s*\[PHONE\])"
)
BUSINESS_WORDS = ("发货", "退款", "尺码", "质量", "快递", "鞋子", "电话", "手机", "号码", "联系")
NON_NAME_PREFIXES = ("为", "请", "可", "能", "已", "将", "会", "是", "的", "了", "在", "由", "如", "若", "不", "有", "无", "让", "给", "您", "我", "他", "她", "这", "那")

ADDRESS_KEYWORDS = (
    "省", "市", "区", "县", "镇", "乡", "村", "街道", "路", "号", "栋", "单元", "楼", "室",
    "广场", "小区", "驿站", "代收点", "工厂", "公司", "门店", "上海", "北京", "广州", "深圳",
    "杭州", "苏州", "南京", "青村镇", "奉贤区",
)
STRONG_ADDRESS_LABEL_RE = re.compile(
    r"(?:(?:京东)?(?:代收点|驿站|收货)?地址)\s*[:：]\s*.+"
)
REGIONAL_ADDRESS_RE = re.compile(
    r"(?:上海奉贤区青村镇|河南省|广西(?:壮族自治区)?|广东省)[^，,。；;！？!?\n]{2,}"
)
SENTENCE_SPLIT_RE = re.compile(r"([。！？!?；;\n]+)")
GEO_SUFFIX_RE = re.compile(r"[\u3400-\u9fff]{1,12}?(?:省|市|区|县|镇|乡|村|街道|路)")
NUMBERED_ADDRESS_UNIT_RE = re.compile(r"\d+(?:号|栋|单元|楼|室)")
ADDRESS_PLACE_RE = re.compile(r"广场|小区|驿站|代收点|工厂|公司|门店")
ADDRESS_CITY_RE = re.compile(r"上海|北京|广州|深圳|杭州|苏州|南京|青村镇|奉贤区")

PRODUCT_CONTEXT = ("商品", "商品id", "商品ID", "商品编号", "商品号")
ORDER_CONTEXT = ("订单", "订单号", "订单编号")
TRACKING_CONTEXT = ("快递", "物流", "运单", "单号", "韵达", "申通", "圆通", "京东快递")


class V2Anonymizer:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

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

    def _sub_count(
        self,
        pattern: re.Pattern[str],
        replacement,
        text: str,
        counter: str,
        pii_type: str,
        detected: set[str],
    ) -> str:
        result, count = pattern.subn(replacement, text)
        if count:
            self.counts[counter] += count
            detected.add(pii_type)
        return result

    def _replace_phone_neighbors(self, text: str, detected: set[str]) -> str:
        # Address after [PHONE] takes priority over the shorter name rule.
        def replace_phone_segment(match: re.Match[str]) -> str:
            segment = match.group(2)
            keyword_count = self._address_hit_count(segment)
            if keyword_count >= 1 and len(segment) >= 5:
                self.counts["phone_near_address_replacements"] += 1
                detected.add("ADDRESS")
                return match.group(1) + "[ADDRESS]"
            return match.group(0)

        text = PHONE_AFTER_SEGMENT_RE.sub(replace_phone_segment, text)

        def replace_after_name(match: re.Match[str]) -> str:
            candidate = match.group(2)
            if any(word in candidate for word in BUSINESS_WORDS) or candidate.startswith(NON_NAME_PREFIXES):
                return match.group(0)
            self.counts["phone_near_name_replacements"] += 1
            detected.add("NAME")
            return match.group(1) + "[NAME]"

        text = PHONE_AFTER_NAME_RE.sub(replace_after_name, text)

        def replace_before_name(match: re.Match[str]) -> str:
            candidate = match.group(1)
            if any(word in candidate for word in BUSINESS_WORDS) or candidate.startswith(NON_NAME_PREFIXES):
                return match.group(0)
            self.counts["phone_near_name_replacements"] += 1
            detected.add("NAME")
            return "[NAME]" + match.group(2)

        return NAME_BEFORE_PHONE_RE.sub(replace_before_name, text)

    @staticmethod
    def _address_hit_count(segment: str) -> int:
        """Count address-shaped markers without treating IDs/templates as addresses."""
        hits = 0
        for match in GEO_SUFFIX_RE.finditer(segment):
            token = match.group(0)
            # “其他地区/偏远地区” are logistics ranges, not addresses. Also
            # avoid reading the 市 in 市场 as a city suffix.
            if token.endswith("地区"):
                continue
            if token.endswith("小区"):
                continue
            if token.endswith("市") and match.end() < len(segment) and segment[match.end()] == "场":
                continue
            if token.endswith("区") and match.end() < len(segment) and segment[match.end()] == "别":
                continue
            if token.endswith("在路") or token.endswith("上路"):
                continue
            hits += 1
        hits += len(NUMBERED_ADDRESS_UNIT_RE.findall(segment))
        # Repeated occurrences of the same facility word do not represent two
        # independent address elements (e.g. “联系驿站，已经不在驿站”).
        hits += len(set(ADDRESS_PLACE_RE.findall(segment)))
        # Standalone city names are not detailed addresses by themselves. A
        # special-region rule separately handles explicit high-risk forms such
        # as 上海奉贤区青村镇.
        return hits

    def _replace_addresses(self, text: str, detected: set[str]) -> str:
        parts = SENTENCE_SPLIT_RE.split(text)
        replacements = 0
        for index in range(0, len(parts), 2):
            segment = parts[index]
            if not segment.strip() or "[ADDRESS" in segment:
                continue
            keyword_hits = self._address_hit_count(segment)
            has_label = bool(STRONG_ADDRESS_LABEL_RE.search(segment))
            has_special_region = bool(REGIONAL_ADDRESS_RE.search(segment))
            if has_label:
                parts[index] = STRONG_ADDRESS_LABEL_RE.sub("[ADDRESS]", segment)
                replacements += 1
            elif keyword_hits >= 2 or has_special_region:
                parts[index] = "[ADDRESS_RELATED_MESSAGE]"
                replacements += 1
        if replacements:
            self.counts["address_replacements"] += replacements
            detected.add("ADDRESS")
        return "".join(parts)

    def _replace_long_numbers(self, text: str, detected: set[str]) -> str:
        def replace(match: re.Match[str]) -> str:
            start, end = match.span()
            nearby = text[max(0, start - 10): min(len(text), end + 10)]
            lowered = nearby.casefold()
            if any(keyword.casefold() in lowered for keyword in PRODUCT_CONTEXT):
                self.counts["product_id_replacements"] += 1
                detected.add("PRODUCT_ID")
                return "[PRODUCT_ID]"
            if any(keyword.casefold() in lowered for keyword in ORDER_CONTEXT):
                self.counts["order_id_replacements"] += 1
                detected.add("ORDER_ID")
                return "[ORDER_ID]"
            if any(keyword.casefold() in lowered for keyword in TRACKING_CONTEXT):
                self.counts["tracking_id_replacements"] += 1
                detected.add("TRACKING_ID")
                return "[TRACKING_ID]"
            self.counts["long_number_replacements"] += 1
            detected.add("LONG_NUMBER")
            return "[LONG_NUMBER]"

        return LONG_NUMBER_RE.sub(replace, text)

    def anonymize(self, value: object) -> tuple[str, set[str]]:
        text = "" if value is None else str(value)
        detected: set[str] = set()

        text = self._replace_urls(text, detected)
        text = self._sub_count(
            PRODUCT_ID_RE, "商品ID：[PRODUCT_ID]", text,
            "product_id_replacements", "PRODUCT_ID", detected,
        )
        text = self._sub_count(
            ORDER_ID_RE, "订单ID：[ORDER_ID]", text,
            "order_id_replacements", "ORDER_ID", detected,
        )
        text = self._sub_count(
            TRACKING_LABEL_RE, lambda match: match.group(1) + "[TRACKING_ID]", text,
            "tracking_id_replacements", "TRACKING_ID", detected,
        )
        text = self._replace_phone_neighbors(text, detected)
        text = self._replace_addresses(text, detected)
        text = self._replace_long_numbers(text, detected)

        text = re.sub(r"[ \t]+", " ", text).strip()
        return text, detected


def parse_existing_types(value: object) -> set[str]:
    return {item.strip() for item in str(value or "").split(";") if item.strip()}


def anonymize_file(input_path: Path, output_dir: Path) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "jd_turn_based_qa_anonymized_v2.csv"
    report_path = output_dir / "anonymization_v2_report.csv"
    examples_path = output_dir / "anonymization_v2_examples.csv"

    frame = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    if "merged_question" not in frame.columns or "answer" not in frame.columns:
        raise ValueError("输入 CSV 缺少 merged_question 或 answer 字段")

    anonymizer = V2Anonymizer()
    output_records: list[dict[str, str]] = []
    changed_examples: list[dict[str, str]] = []

    for record in frame.to_dict(orient="records"):
        processed: dict[str, str] = dict(record)
        before_question = processed.get("anonymized_question") or processed.get("merged_question", "")
        before_answer = processed.get("anonymized_answer") or processed.get("answer", "")
        new_types: set[str] = set()
        row_changed = False

        for field in TEXT_FIELDS:
            if field not in processed:
                continue
            before = processed[field]
            after, field_types = anonymizer.anonymize(before)
            processed[field] = after
            if after != before:
                row_changed = True
                new_types.update(field_types)

        # Keep the explicit anonymized fields synchronized with their own v1
        # values when present, otherwise derive them from processed base fields.
        if "anonymized_question" not in processed:
            processed["anonymized_question"] = processed.get("merged_question", "")
        if "anonymized_answer" not in processed:
            processed["anonymized_answer"] = processed.get("answer", "")

        existing_types = parse_existing_types(processed.get("pii_types", ""))
        all_types = existing_types | new_types
        existing_detected = str(processed.get("pii_detected", "")).casefold() == "true"
        processed["pii_detected"] = "true" if existing_detected or all_types else "false"
        processed["pii_types"] = ";".join(sorted(all_types))
        output_records.append(processed)

        if row_changed:
            changed_examples.append(
                {
                    "before_question": before_question,
                    "after_question": processed.get("anonymized_question", ""),
                    "before_answer": before_answer,
                    "after_answer": processed.get("anonymized_answer", ""),
                    "pii_types": ";".join(sorted(new_types)),
                }
            )

    pd.DataFrame(output_records).to_csv(output_path, index=False, encoding="utf-8-sig")

    report = {
        "total_rows": len(frame),
        "rows_with_new_pii_found": len(changed_examples),
        "product_id_replacements": anonymizer.counts["product_id_replacements"],
        "order_id_replacements": anonymizer.counts["order_id_replacements"],
        "tracking_id_replacements": anonymizer.counts["tracking_id_replacements"],
        "long_number_replacements": anonymizer.counts["long_number_replacements"],
        "phone_near_name_replacements": anonymizer.counts["phone_near_name_replacements"],
        "phone_near_address_replacements": anonymizer.counts["phone_near_address_replacements"],
        "address_replacements": anonymizer.counts["address_replacements"],
        "link_replacements": anonymizer.counts["link_replacements"],
    }
    pd.DataFrame([report], columns=REPORT_COLUMNS).to_csv(
        report_path, index=False, encoding="utf-8-sig"
    )

    examples = pd.DataFrame(changed_examples, columns=EXAMPLE_COLUMNS)
    if len(examples) > 200:
        examples = examples.sample(n=200)
    examples.to_csv(examples_path, index=False, encoding="utf-8-sig")
    return len(frame), len(changed_examples)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="对第一版京东 QA 脱敏结果执行第二轮补充脱敏。")
    parser.add_argument("input", help="jd_turn_based_qa_anonymized.csv 路径")
    parser.add_argument("-o", "--output-dir", default=".", help="v2 输出 CSV 目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not input_path.is_file():
        print(f"Error: 找不到输入文件：{input_path}", file=sys.stderr)
        return 2
    try:
        total_rows, changed_rows = anonymize_file(input_path, output_dir)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"完成：处理 {total_rows} 行，本轮在 {changed_rows} 行发现并处理了新敏感信息")
    print(f"输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
