#!/usr/bin/env python3
"""Refine JD QA categories from final question intent without changing QA text."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd


EXAMPLE_FIELDS = (
    "source_file",
    "session_id",
    "final_question",
    "final_answer",
    "category",
    "refined_category",
    "matched_keywords",
)
REPORT_FIELDS = (
    "input_rows",
    "changed_rows",
    "unchanged_rows",
    "original_category_distribution",
    "refined_category_distribution",
    "original_other_rows",
    "refined_other_rows",
)

SIZE_KEYWORDS = (
    "尺码", "码数", "鞋码", "大一码", "买大一码", "拍大一码", "建议买大一码", "建议拍大一码",
    "要不要买大一码", "要不要拍大一码", "需要买大一码吗", "需要拍大一码吗", "买大一号",
    "拍大一号", "大一号", "小一码", "买小一码", "拍小一码", "正码", "标准码", "码准",
    "码数准", "尺码准", "偏大", "偏小", "脚宽", "脚胖", "脚背高", "平时穿", "穿多大",
    "多大码", "41码", "42码", "43码", "44码", "45码",
)
SIZE_REGEXES = (
    re.compile(r"(?<![号编数])码(?:吗|呢|准|偏|大|小|怎么|如何|选|合适|标准)"),
    re.compile(r"\d{2}\s*码"),
    re.compile(r"(?:穿|买|拍|选)\s*\d{2}"),
)

LOGISTICS_KEYWORDS = (
    "发货", "发了吗", "发了没有", "发没发", "订单发了没", "我的订单发了没有", "什么时候发",
    "什么时候发货", "什么时候能发", "今天发吗", "今天能发吗", "明天发吗", "加急发货", "现货",
    "快递", "什么快递", "发什么快递", "哪种快递", "物流", "派送", "配送", "送到", "送达",
    "到货", "到了吗", "到哪里了", "多久到", "几天到", "什么时候到", "什么时候能到",
    "什么时候能送到", "能到吗", "今天能到", "明天能到", "多长时间能到", "几天能到",
    "到广东", "到东莞", "到西安", "到北京", "到上海", "到广州", "到深圳", "代收点", "驿站",
    "取件", "拒收", "补发", "拦截",
)
PRODUCT_KEYWORDS = (
    "材质", "面料", "鞋底", "防滑", "透气", "透气性", "闷脚", "热不热", "夏天穿热吗",
    "保暖", "增高", "内增高", "加绒", "有没有绒", "里面有绒", "不加绒", "加没加绒",
    "升级版", "款式", "颜色", "黑色", "白色", "英文款", "正品", "是正品吗", "男鞋女鞋",
    "有货", "没货", "无货", "补货", "什么时候有货", "什么时候补货", "还有货吗", "库存",
    "下架", "上架", "还卖吗", "还能买吗", "链接失效", "商品不存在", "这款有不", "有这个吗",
    "有里面的图片吗",
)
REFUND_KEYWORDS = (
    "退货", "退款", "退掉", "可以退吗", "能退吗", "可不可以退", "能不能退", "没穿可以退",
    "没有穿可以退", "没去拿", "没取件", "没拆", "申请退", "申请退款", "申请售后", "退回去",
    "寄回去", "七天无理由", "7天无理由", "仅退款", "退钱", "退一下", "不想要了", "不要了",
)
EXCHANGE_KEYWORDS = (
    "换货", "换码", "换颜色", "换一双", "可以换吗", "能换吗", "换大一码", "换小一码",
    "换个码", "换尺码", "重新换", "调换",
)
FREIGHT_KEYWORDS = (
    "运费", "运费险", "邮费", "包邮", "退货运费", "换货运费", "谁承担", "运费谁出",
    "返运费", "退运费", "评价返运费",
)
QUALITY_KEYWORDS = (
    "质量", "开胶", "破损", "坏了", "瑕疵", "色差", "发错", "发错货", "发错款式", "磨损",
    "划痕", "刮蹭", "剐蹭", "污渍", "脏", "擦不掉", "掉色", "断底", "脱线", "少发", "漏发",
)
PRICE_KEYWORDS = (
    "补偿", "赔偿", "优惠", "便宜", "差价", "买贵了", "退差价", "返多少钱", "补多少钱",
    "8元", "10元", "八元", "十元", "京东余额", "小额打款", "打款", "返现", "价格", "能便宜吗",
)

STOCK_SPECIAL = (
    "什么时候有货", "有没有货", "有货吗", "还有货吗", "什么时候补货", "下架了吗", "下架了",
    "商品不存在", "链接失效", "还能买吗", "还卖吗",
)
LOGISTICS_SPECIAL = (
    "什么时候发货", "什么时候能发", "什么时候能到", "发什么快递", "什么快递", "哪种快递",
    "多久到", "几天到", "什么时候到", "什么时候能送到",
)
SIZE_SPECIAL = (
    "大一码", "大一号", "小一码", "正码", "标准码", "码准", "偏大", "偏小",
)
REFUND_SPECIAL = ("可不可以退掉", "没穿可以退吗", "没有穿可以退吗", "不想要了", "不要了")
PRODUCT_SPECIAL = ("加绒", "透气", "防滑", "材质", "正品", "增高")
FREIGHT_INTENT = (
    "运费谁", "运费谁出", "谁承担运费", "运费谁承担", "退货运费", "换货运费", "返运费",
    "退运费", "有运费险", "运费险吗", "包邮吗", "邮费谁",
)
STOCK_SIZE_REGEXES = (
    re.compile(r"(?:什么时候|啥时候|何时)?有\s*\d{2}\s*码"),
    re.compile(r"\d{2}\s*码[^，。；!?？]{0,6}(?:有吗|有货|没货|无货|补货|上架)"),
)

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("尺码问题", SIZE_KEYWORDS),
    ("退货退款", REFUND_KEYWORDS),
    ("换货", EXCHANGE_KEYWORDS),
    ("运费", FREIGHT_KEYWORDS),
    ("物流发货", LOGISTICS_KEYWORDS),
    ("质量问题", QUALITY_KEYWORDS),
    ("价格补偿", PRICE_KEYWORDS),
    ("商品咨询", PRODUCT_KEYWORDS),
)


def keyword_matches(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


def size_matches(text: str) -> list[str]:
    matches = keyword_matches(text, SIZE_KEYWORDS)
    for pattern in SIZE_REGEXES:
        for found in pattern.finditer(text):
            matches.append(found.group(0))
    # A question that is literally “码” is a size question; arbitrary 码 inside
    # 号码/单号/编码 is intentionally not treated as a size signal.
    if re.sub(r"[\s，,。.!！?？；;：:]", "", text) == "码":
        matches.append("码")
    return list(dict.fromkeys(matches))


def classify_question(text: str) -> tuple[str, list[str]]:
    question = text or ""

    # Strong intent exceptions resolve common priority ambiguities.
    logistics_special = keyword_matches(question, LOGISTICS_SPECIAL)
    if logistics_special:
        return "物流发货", logistics_special
    stock_size_matches = [
        match.group(0)
        for pattern in STOCK_SIZE_REGEXES
        for match in pattern.finditer(question)
    ]
    if stock_size_matches:
        return "商品咨询", list(dict.fromkeys(stock_size_matches))
    stock_special = keyword_matches(question, STOCK_SPECIAL)
    if stock_special:
        return "商品咨询", stock_special
    freight_intent = keyword_matches(question, FREIGHT_INTENT)
    if freight_intent:
        return "运费", freight_intent
    size_special = keyword_matches(question, SIZE_SPECIAL)
    if size_special:
        return "尺码问题", size_special
    refund_special = keyword_matches(question, REFUND_SPECIAL)
    if refund_special:
        return "退货退款", refund_special
    product_special = keyword_matches(question, PRODUCT_SPECIAL)
    # Explicit product properties stay product questions unless the question
    # also contains a stronger size/refund/freight intent below.

    size = size_matches(question)
    if size:
        return "尺码问题", size
    for category, keywords in CATEGORY_RULES[1:]:
        matches = keyword_matches(question, keywords)
        if matches:
            return category, matches
    if product_special:
        return "商品咨询", product_special
    return "其他", []


def classify(question: str, answer: str) -> tuple[str, list[str], str]:
    category, matches = classify_question(question)
    if category != "其他":
        return category, matches, "question"
    # Keep ambiguous questions as 其他 rather than inheriting a category from a
    # potentially generic/canned service answer. The answer remains available
    # for future audited rules, but never overrides absent customer intent.
    return "其他", [], "none"


def distribution(series: pd.Series) -> str:
    counts = Counter(str(value or "其他") for value in series)
    return json.dumps(dict(sorted(counts.items())), ensure_ascii=False)


def refine_file(input_path: Path, output_dir: Path) -> tuple[int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "jd_final_safe_qa_refined_category.csv"
    report_path = output_dir / "category_refinement_report.csv"
    examples_path = output_dir / "category_changed_examples.csv"

    frame = pd.read_csv(input_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    question_field = "final_question" if "final_question" in frame.columns else "merged_question"
    answer_field = "final_answer" if "final_answer" in frame.columns else "answer"
    required = {question_field, answer_field, "category", "source_file", "session_id"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError("输入 CSV 缺少字段：" + ", ".join(sorted(missing)))

    refined_categories: list[str] = []
    matched_values: list[str] = []
    changed_examples: list[dict[str, str]] = []

    for record in frame.to_dict(orient="records"):
        question = record.get(question_field, "")
        answer = record.get(answer_field, "")
        refined, matches, source = classify(question, answer)
        original = record.get("category", "") or "其他"
        if refined == "其他" and not matches:
            # No new customer-intent evidence: preserve the existing label
            # instead of degrading an elliptical question to 其他.
            refined = "商品咨询" if original == "库存问题" else original
        matched = ";".join(dict.fromkeys(matches))
        if source == "answer_fallback" and matched:
            matched = "answer:" + matched
        refined_categories.append(refined)
        matched_values.append(matched)

        if original != refined:
            changed_examples.append(
                {
                    "source_file": record.get("source_file", ""),
                    "session_id": record.get("session_id", ""),
                    "final_question": question,
                    "final_answer": answer,
                    "category": original,
                    "refined_category": refined,
                    "matched_keywords": matched,
                }
            )

    frame["refined_category"] = refined_categories
    frame.to_csv(output_path, index=False, encoding="utf-8-sig")
    pd.DataFrame(changed_examples, columns=EXAMPLE_FIELDS).to_csv(
        examples_path, index=False, encoding="utf-8-sig"
    )

    original_series = frame["category"].replace("", "其他")
    refined_series = frame["refined_category"]
    report = {
        "input_rows": len(frame),
        "changed_rows": len(changed_examples),
        "unchanged_rows": len(frame) - len(changed_examples),
        "original_category_distribution": distribution(original_series),
        "refined_category_distribution": distribution(refined_series),
        "original_other_rows": int((original_series == "其他").sum()),
        "refined_other_rows": int((refined_series == "其他").sum()),
    }
    pd.DataFrame([report], columns=REPORT_FIELDS).to_csv(
        report_path, index=False, encoding="utf-8-sig"
    )
    return len(frame), len(changed_examples)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="根据最终问答意图重新优化京东 QA category。")
    parser.add_argument("input", help="jd_final_safe_qa.csv 路径")
    parser.add_argument("-o", "--output-dir", default=".", help="分类优化输出目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    if not input_path.is_file():
        print(f"Error: 找不到输入文件：{input_path}", file=sys.stderr)
        return 2
    try:
        input_rows, changed_rows = refine_file(input_path, output_dir)
    except (OSError, ValueError, pd.errors.ParserError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"完成：处理 {input_rows} 行，其中 {changed_rows} 行 category 发生变化")
    print(f"输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
