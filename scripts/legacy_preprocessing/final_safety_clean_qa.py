#!/usr/bin/env python3
"""Final PII and validity safety gate for anonymized JD QA data."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


REPORT_COLUMNS = (
    "input_rows",
    "output_rows",
    "rejected_rows",
    "email_replacements",
    "phone_replacements",
    "order_id_replacements",
    "product_id_replacements",
    "tracking_id_replacements",
    "long_number_replacements",
    "name_replacements",
    "address_replacements",
    "empty_question_removed",
    "empty_answer_removed",
    "pii_only_question_removed",
)
EXAMPLE_COLUMNS = (
    "original_question",
    "final_question",
    "original_answer",
    "final_answer",
    "change_types",
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
LANDLINE_RE = re.compile(r"(?<!\d)(?:0\d{2,3}[-—－ ]?)\d{7,8}(?!\d)")
LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{10,}(?!\d)")
SPACED_NUMBER_RE = re.compile(r"(?<!\d)(?:\d{3}[ -]){2,}\d{3,}(?!\d)")
PLATFORM_CODE_RE = re.compile(r"(?:#\s*E\s*[-_][A-Za-z0-9_-]+|/:\d{3,})", re.IGNORECASE)

LABELED_NAME_RE = re.compile(
    r"((?:收件人|收货人|联系人|姓名|名字|客户|配送员)\s*[:：]\s*)"
    r"([\u3400-\u9fff]{2,5})"
)
PHONE_AFTER_NAME_RE = re.compile(
    r"(\[PHONE\])([^，,。；;！？!?\n]{0,6}?)([\u3400-\u9fff]{2,5})"
    r"(?=$|[，,。；;！？!?\s])"
)
NAME_BEFORE_PHONE_RE = re.compile(
    r"(?<![\u3400-\u9fff])([\u3400-\u9fff]{2,5})([^\u3400-\u9fff]{0,6}\[PHONE\])"
)
NON_NAME_WORDS = {
    "亲亲", "客服", "客服小妹", "商家", "快递", "快递员", "仓库", "鞋子", "订单", "商品", "质量",
    "尺码", "发货", "退款", "电话", "手机", "号码", "地址", "平台", "物流", "售后", "客户",
}
NON_NAME_PREFIXES = ("为", "请", "可", "能", "已", "将", "会", "是", "的", "了", "在", "由", "如", "若", "不", "有", "无", "让", "给", "您", "我", "他", "她", "这", "那")
COMMON_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平"
    "黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴宋茅庞熊纪舒屈项祝董"
    "梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林钟徐邱骆高夏蔡田樊胡凌"
    "霍虞万支柯管卢莫房裘缪解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇邢"
    "滑裴陆荣翁荀羊甄曲封芮储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯"
    "宓蓬全班仰秋仲伊宫宁仇栾甘厉戎祖武符刘景詹束龙叶幸司黎乔苍双闻"
)

NUMBER_PRODUCT_CONTEXT = ("商品", "商品id", "商品ID", "商品号", "商品编号")
NUMBER_ORDER_CONTEXT = ("订单", "订单号", "订单编号")
NUMBER_TRACKING_CONTEXT = ("快递", "物流", "运单", "单号", "韵达", "申通", "圆通", "京东快递")

GEO_SUFFIX_RE = re.compile(r"[\u3400-\u9fff]{1,12}?(?:省|市|区|县|镇|乡|村|街道|路)")
NUMBERED_ADDRESS_RE = re.compile(r"\d+(?:号|栋|单元|楼|室)")
ADDRESS_PLACE_RE = re.compile(r"小区|广场|超市|学校|工厂|公司|门店|驿站|代收点|站点|菜鸟|京东站|营业部")
STRONG_LOCATION_RE = re.compile(r"奉贤区|青村镇|中国移动|佳好佳超市")
ADDRESS_LABEL_RE = re.compile(
    r"((?:发到|寄到|收货地址|地址|送到|派送到|给我送到)\s*[:：]?\s*)"
    r"([^，,。；;！？!?\n]{2,100})"
)
PHONE_NEAR_SEGMENT_RE = re.compile(r"(\[PHONE\])([^，,。；;！？!?\n]{2,80})")
SENTENCE_SPLIT_RE = re.compile(r"([。！？!?；;\n]+)")

BUSINESS_WORDS = (
    "尺码", "码数", "偏大", "偏小", "发货", "快递", "物流", "退货", "退款", "换货", "运费",
    "质量", "开胶", "发错", "补偿", "赔偿", "材质", "防滑", "正品", "颜色", "无货", "拒收",
    "派送", "京东余额", "地址", "拦截", "款式", "增高", "保暖", "售后", "取消", "修改",
)
INVALID_QUESTIONS = {"你好", "在吗", "亲", "嗯", "好的", "谢谢", "？", "?"}
INVALID_ANSWERS = {"好的", "可以的", "嗯嗯", "稍等", "在的亲"}
SENSITIVE_PLACEHOLDER_RE = re.compile(
    r"\[(?:NAME|PHONE|ADDRESS|EMAIL|ORDER_ID|PRODUCT_ID|TRACKING_ID|LONG_NUMBER)\]"
)
LINK_ONLY_RE = re.compile(r"^(?:\[(?:IMAGE_LINK|PRODUCT_LINK|URL|EMOJI_CODE)\][\s，,；;]*)+$")
PUNCT_ONLY_RE = re.compile(r"^[\s\u3000，,。.!！?？~～、；;：:…·\-—_（）()【】\[\]{}]*$")
TRIM_PUNCT_RE = re.compile(r"[\s\u3000，,。.!！?？~～、；;：:…·\-—_（）()【】\[\]{}]+")


class SafetyCleaner:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def _sub(
        self,
        pattern: re.Pattern[str],
        replacement,
        text: str,
        counter: str,
        change_type: str,
        changes: set[str],
    ) -> str:
        result, count = pattern.subn(replacement, text)
        if count:
            self.counts[counter] += count
            changes.add(change_type)
        return result

    @staticmethod
    def _number_type(text: str, start: int, end: int) -> tuple[str, str]:
        nearby = text[max(0, start - 12): min(len(text), end + 12)]
        lowered = nearby.casefold()
        if any(keyword.casefold() in lowered for keyword in NUMBER_PRODUCT_CONTEXT):
            return "[PRODUCT_ID]", "PRODUCT_ID"
        if any(keyword.casefold() in lowered for keyword in NUMBER_ORDER_CONTEXT):
            return "[ORDER_ID]", "ORDER_ID"
        if any(keyword.casefold() in lowered for keyword in NUMBER_TRACKING_CONTEXT):
            return "[TRACKING_ID]", "TRACKING_ID"
        return "[LONG_NUMBER]", "LONG_NUMBER"

    def _replace_long_numbers(self, text: str, changes: set[str]) -> str:
        def replace(match: re.Match[str]) -> str:
            placeholder, kind = self._number_type(text, *match.span())
            counter = {
                "PRODUCT_ID": "product_id_replacements",
                "ORDER_ID": "order_id_replacements",
                "TRACKING_ID": "tracking_id_replacements",
                "LONG_NUMBER": "long_number_replacements",
            }[kind]
            self.counts[counter] += 1
            changes.add(kind)
            return placeholder

        text = LONG_NUMBER_RE.sub(replace, text)

        def replace_spaced(match: re.Match[str]) -> str:
            digits = re.sub(r"\D", "", match.group(0))
            if len(digits) < 9:
                return match.group(0)
            placeholder, kind = self._number_type(text, *match.span())
            counter = {
                "PRODUCT_ID": "product_id_replacements",
                "ORDER_ID": "order_id_replacements",
                "TRACKING_ID": "tracking_id_replacements",
                "LONG_NUMBER": "long_number_replacements",
            }[kind]
            self.counts[counter] += 1
            changes.add(kind)
            return placeholder

        return SPACED_NUMBER_RE.sub(replace_spaced, text)

    @staticmethod
    def _valid_name(candidate: str) -> bool:
        return (
            candidate not in NON_NAME_WORDS
            and not candidate.startswith(NON_NAME_PREFIXES)
            and not any(word in candidate for word in NON_NAME_WORDS)
            and (candidate[0] in COMMON_SURNAMES or candidate.endswith(("先生", "女士")))
        )

    def _replace_names(self, text: str, changes: set[str]) -> str:
        text = self._sub(
            LABELED_NAME_RE, lambda match: match.group(1) + "[NAME]", text,
            "name_replacements", "NAME", changes,
        )

        def after_phone(match: re.Match[str]) -> str:
            candidate = match.group(3)
            if not self._valid_name(candidate):
                return match.group(0)
            self.counts["name_replacements"] += 1
            changes.add("NAME")
            return match.group(1) + match.group(2) + "[NAME]"

        text = PHONE_AFTER_NAME_RE.sub(after_phone, text)

        def before_phone(match: re.Match[str]) -> str:
            candidate = match.group(1)
            if not self._valid_name(candidate):
                return match.group(0)
            self.counts["name_replacements"] += 1
            changes.add("NAME")
            return "[NAME]" + match.group(2)

        text = NAME_BEFORE_PHONE_RE.sub(before_phone, text)

        return text

    @staticmethod
    def _address_hit_count(segment: str) -> int:
        hits = 0
        for match in GEO_SUFFIX_RE.finditer(segment):
            token = match.group(0)
            if token.endswith(("地区", "小区", "在路", "上路")):
                continue
            if token.endswith("市") and match.end() < len(segment) and segment[match.end()] == "场":
                continue
            if token.endswith("区") and match.end() < len(segment) and segment[match.end()] == "别":
                continue
            hits += 1
        hits += len(NUMBERED_ADDRESS_RE.findall(segment))
        hits += len(set(ADDRESS_PLACE_RE.findall(segment)))
        return hits

    def _replace_addresses(self, text: str, changes: set[str]) -> str:
        def phone_address(match: re.Match[str]) -> str:
            segment = match.group(2)
            if self._address_hit_count(segment) or STRONG_LOCATION_RE.search(segment):
                self.counts["address_replacements"] += 1
                changes.add("ADDRESS")
                return match.group(1) + "[ADDRESS]"
            return match.group(0)

        text = PHONE_NEAR_SEGMENT_RE.sub(phone_address, text)

        def labeled_address(match: re.Match[str]) -> str:
            prefix, candidate = match.group(1), match.group(2)
            explicit_colon = ":" in prefix or "：" in prefix
            if explicit_colon or self._address_hit_count(candidate) or STRONG_LOCATION_RE.search(candidate):
                self.counts["address_replacements"] += 1
                changes.add("ADDRESS")
                return prefix + "[ADDRESS]"
            return match.group(0)

        text = ADDRESS_LABEL_RE.sub(labeled_address, text)

        parts = SENTENCE_SPLIT_RE.split(text)
        for index in range(0, len(parts), 2):
            segment = parts[index]
            if not segment.strip() or "[ADDRESS" in segment:
                continue
            if self._address_hit_count(segment) >= 2:
                parts[index] = "[ADDRESS_RELATED_MESSAGE]"
                self.counts["address_replacements"] += 1
                changes.add("ADDRESS")
        return "".join(parts)

    def clean(self, value: object) -> tuple[str, set[str]]:
        text = "" if value is None else str(value)
        changes: set[str] = set()

        text = self._sub(
            EMAIL_RE, "[EMAIL]", text, "email_replacements", "EMAIL", changes
        )
        text = self._sub(
            MOBILE_RE, "[PHONE]", text, "phone_replacements", "PHONE", changes
        )
        text = self._sub(
            LANDLINE_RE, "[PHONE]", text, "phone_replacements", "PHONE", changes
        )
        text = self._replace_long_numbers(text, changes)
        text = self._replace_names(text, changes)
        text = self._replace_addresses(text, changes)

        before_codes = text
        text, code_count = PLATFORM_CODE_RE.subn("", text)
        if code_count:
            changes.add("PLATFORM_CODE")
        if text != before_codes:
            text = re.sub(r"(?:；\s*){2,}", "；", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = text.strip(" \t\r\n；;")
        return text, changes


def compact(text: str) -> str:
    return TRIM_PUNCT_RE.sub("", text or "").casefold()


def question_rejection(question: str) -> str | None:
    stripped = (question or "").strip()
    normalized = compact(stripped)
    if (
        not stripped
        or PUNCT_ONLY_RE.fullmatch(stripped)
        or len(normalized) < 2
        or normalized in {compact(value) for value in INVALID_QUESTIONS}
        or LINK_ONLY_RE.fullmatch(stripped)
        or stripped in {"[NAME]", "[PHONE]", "[ADDRESS]", "[EMAIL]", "[ORDER_ID]"}
    ):
        return "empty_or_invalid_question"

    without_pii = SENSITIVE_PLACEHOLDER_RE.sub("", stripped)
    without_pii = TRIM_PUNCT_RE.sub("", without_pii)
    has_business = any(word in stripped for word in BUSINESS_WORDS)
    if not has_business and len(without_pii) <= 1 and SENSITIVE_PLACEHOLDER_RE.search(stripped):
        return "pii_only_question"
    return None


def answer_rejection(answer: str) -> str | None:
    stripped = (answer or "").strip()
    normalized = compact(stripped)
    if not stripped or PUNCT_ONLY_RE.fullmatch(stripped) or normalized in {
        compact(value) for value in INVALID_ANSWERS
    }:
        return "empty_or_invalid_answer"
    return None


def run(input_path: Path, output_dir: Path) -> tuple[int, int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "jd_final_safe_qa.csv"
    rejected_path = output_dir / "jd_final_safety_rejected.csv"
    report_path = output_dir / "jd_final_safety_report.csv"
    examples_path = output_dir / "jd_final_safety_examples.csv"

    frame = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    question_field = "anonymized_question" if "anonymized_question" in frame.columns else "merged_question"
    answer_field = "anonymized_answer" if "anonymized_answer" in frame.columns else "answer"
    required = {question_field, answer_field, "category", "source_file", "session_id"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError("输入 CSV 缺少字段：" + ", ".join(sorted(missing)))

    cleaner = SafetyCleaner()
    accepted: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    examples: list[dict[str, str]] = []

    for record in frame.to_dict(orient="records"):
        original_question = record.get(question_field, "")
        original_answer = record.get(answer_field, "")
        final_question, question_changes = cleaner.clean(original_question)
        final_answer, answer_changes = cleaner.clean(original_answer)
        change_types = question_changes | answer_changes

        output_record = dict(record)
        output_record["final_question"] = final_question
        output_record["final_answer"] = final_answer

        reason = question_rejection(final_question)
        if reason is None:
            reason = answer_rejection(final_answer)
        if reason:
            output_record["reject_reason"] = reason
            rejected.append(output_record)
            if reason == "empty_or_invalid_question":
                cleaner.counts["empty_question_removed"] += 1
            elif reason == "empty_or_invalid_answer":
                cleaner.counts["empty_answer_removed"] += 1
            elif reason == "pii_only_question":
                cleaner.counts["pii_only_question_removed"] += 1
        else:
            accepted.append(output_record)

        if final_question != original_question or final_answer != original_answer:
            examples.append(
                {
                    "original_question": original_question,
                    "final_question": final_question,
                    "original_answer": original_answer,
                    "final_answer": final_answer,
                    "change_types": ";".join(sorted(change_types)),
                }
            )

    base_columns = list(frame.columns) + ["final_question", "final_answer"]
    pd.DataFrame(accepted, columns=base_columns).to_csv(
        output_path, index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(rejected, columns=base_columns + ["reject_reason"]).to_csv(
        rejected_path, index=False, encoding="utf-8-sig"
    )

    report = {
        "input_rows": len(frame),
        "output_rows": len(accepted),
        "rejected_rows": len(rejected),
        **{column: cleaner.counts[column] for column in REPORT_COLUMNS[3:]},
    }
    pd.DataFrame([report], columns=REPORT_COLUMNS).to_csv(
        report_path, index=False, encoding="utf-8-sig"
    )

    example_frame = pd.DataFrame(examples, columns=EXAMPLE_COLUMNS)
    if len(example_frame) > 200:
        example_frame = example_frame.sample(n=200)
    example_frame.to_csv(examples_path, index=False, encoding="utf-8-sig")
    return len(frame), len(accepted), len(rejected)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="对京东 QA 执行最终脱敏与有效性安全清洗。")
    parser.add_argument("input", help="jd_turn_based_qa_anonymized_v2.csv 路径")
    parser.add_argument("-o", "--output-dir", default=".", help="最终安全 CSV 输出目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not input_path.is_file():
        print(f"Error: 找不到输入文件：{input_path}", file=sys.stderr)
        return 2
    try:
        input_rows, output_rows, rejected_rows = run(input_path, output_dir)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"完成：输入 {input_rows} 行，输出 {output_rows} 行，拒绝 {rejected_rows} 行")
    print(f"输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
