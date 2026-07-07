#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Build structured JD knowledge snippets for RAG V2.

This script parses raw JD customer-service scripts into a safer, structured
knowledge-snippet CSV. Risky originals are separated into a rejected CSV; when a
risky script is still useful, a conservative rewrite can enter the main KB.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RAW_FILE = ROOT / "data" / "raw" / "jd" / "京东话术.txt"
OUTPUT_CSV = ROOT / "data" / "processed" / "knowledge_snippets_v2.csv"
REPORT_MD = ROOT / "outputs" / "reports" / "knowledge_snippets_report.md"
REJECTED_CSV = ROOT / "outputs" / "rejected" / "knowledge_snippets_rejected.csv"

PLATFORM = "JD"
SOURCE_FILE_VALUE = "data/raw/jd/京东话术.txt"
DEFAULT_GROUP = "未分组"

FIELDS = [
    "source_file",
    "platform",
    "source_type",
    "category",
    "title",
    "content",
    "priority",
    "allowed_for_answer",
    "needs_backend_api",
    "risk_note",
    "original_key",
    "original_group",
]

KEY_VALUE_RE = re.compile(r"^\s*([^=\s][^=]{0,80}?)\s*=\s*(.*)$")

CATEGORY_RULES = [
    ("尺码问题", ["尺码", "码数", "鞋码", "偏大", "偏小", "大一码", "小一码", "正码", "脚宽", "脚胖", "脚背高"]),
    ("质量问题", ["质量", "开胶", "断底", "开线", "破损", "瑕疵", "掉色", "磨损", "鞋面开裂", "质保", "三包", "发错", "残次"]),
    ("换货", ["换货", "换码", "换一双", "调换"]),
    ("退货退款", ["退货", "退款", "七天无理由", "不影响二次销售", "拒收", "退换", "申请售后", "售后"]),
    ("物流发货", ["发货", "快递", "到货", "物流", "催促", "仓库", "揽件", "派送", "预计送达", "补发", "掉单"]),
    ("运费", ["运费", "运费险", "邮费", "上门取件", "报销运费"]),
    ("价格补偿", ["补偿", "返款", "返现", "优惠", "差价", "打款", "京东余额", "补贴"]),
    ("正品保障", ["正品", "授权", "验货", "假一罚十", "品牌", "鉴定"]),
    ("商品咨询", ["防滑", "打滑", "鞋底", "透气", "材质", "面料", "加绒", "保暖", "臭脚", "软底", "硬底", "重量", "鞋盒", "颜色", "款式", "清洗", "保养", "磨脚"]),
]

SOURCE_TYPE_RULES = [
    ("backend_rule", ["查订单", "查询订单", "查物流", "物流进度", "退款进度", "补偿到账", "返款到账", "售后进度", "后台", "打款", "到账", "拦截", "催促快递"]),
    ("shipping_rule", ["发货时间", "发货", "快递", "到货", "物流", "仓库", "揽件", "派送", "预计送达", "补发"]),
    ("aftersales_rule", ["开胶", "发错", "破损", "质量问题", "售后申请", "申请售后", "拒收", "残次", "瑕疵", "断底", "开线", "鞋面开裂", "磨损"]),
    ("policy_rule", ["七天无理由", "影响二次销售", "退换货", "退换", "质保", "三包", "正品保障", "假一罚十", "授权"]),
    ("product_info", ["防滑", "透气", "材质", "软底", "硬底", "加绒", "保暖", "正品", "臭脚", "鞋底", "重量", "面料", "鞋盒", "颜色", "款式", "清洗", "保养"]),
]

PRODUCT_INFO_KEYWORDS = set(SOURCE_TYPE_RULES[-1][1])

BACKEND_API_KEYWORDS = [
    "查订单",
    "查询",
    "后台",
    "订单",
    "物流",
    "退款进度",
    "到账",
    "售后进度",
    "补偿到账",
    "打款",
    "拦截",
    "催促",
    "申请售后",
]

MEANINGLESS_PATTERNS = [
    re.compile(r"^(在的呢?|在呢|好的呢?|好呢|嗯嗯|稍等呢?|稍等|您好|你好|亲亲|亲)$"),
    re.compile(r"^有什么可以帮您[的呢哈呀]*[？?]?$"),
    re.compile(r"^按照这上面的操作呢?$"),
]

RISK_RULES = [
    ("手机号", re.compile(r"(?<!\d)(?:1[3-9]\d{9}|0\d{2,3}[- ]?\d{7,8})(?!\d)")),
    ("邮箱", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("地址/电话", re.compile(r"(收货地址|详细地址|寄回地址|退货地址|地址|电话|联系方式|联系人|收件人)")),
    ("收款码/线下交易", re.compile(r"(收款码|微信收款|微信支付|线下交易|加微信|转账|提供收款|收款信息|收款账号)")),
    ("订单号", re.compile(r"(订单号|订单编号|单号|(?<!\d)\d{12,}(?!\d))")),
    ("五星好评截图", re.compile(r"((五星|5星|五颗星|点亮五星|追加好评|好评|评价).{0,12}(截图|服务评价|订单|晒图)?|(服务评价|订单).{0,12}(五星|5星|点亮五星|截图))")),
    ("评价返现", re.compile(r"(评价返现|返现话术|好评返|晒图返|评价.{0,12}返|返运费.{0,12}(五星|好评|截图))")),
    ("具体补偿金额", re.compile(r"((补偿|返款|返现|优惠|差价|打款|报销|赔付|申请).{0,16}?[1-9]\d{0,3}(?:\.\d+)?\s*元|[1-9]\d{0,3}(?:\.\d+)?\s*元.{0,16}?(补偿|返款|返现|优惠|差价|打款|报销|赔付))")),
    ("后台操作已完成", re.compile(r"(已经帮您催促|我帮您.{0,8}催促|已经打款|登记打款|已经拦截|已经申请售后|已经退款|已经返款|已经处理|已处理|后台.{0,8}已|帮您.{0,8}申请(补发|补偿|退款|售后))")),
    ("要求修改退货原因", re.compile(r"(修改.{0,8}退货原因|退货原因.{0,8}修改|改一下.{0,8}原因)")),
]

NON_REWRITABLE_RISKS = {
    "手机号",
    "邮箱",
    "地址/电话",
    "收款码/线下交易",
    "订单号",
    "五星好评截图",
    "评价返现",
    "要求修改退货原因",
}


@dataclass
class ParsedSnippet:
    original_key: str
    original_group: str
    content: str
    line_no: int


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"Unable to decode {path}")


def normalize_space(value: str) -> str:
    value = value.replace("\u0001", "").replace("\ufeff", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def clean_group(value: str) -> str:
    return normalize_space(value).rstrip("：:").strip() or DEFAULT_GROUP


def next_nonempty_line(lines: list[str], index: int) -> str:
    for next_index in range(index + 1, len(lines)):
        candidate = lines[next_index].strip()
        if candidate:
            return candidate
    return ""


def is_key_value_line(line: str) -> bool:
    match = KEY_VALUE_RE.match(line)
    if not match:
        return False
    key = match.group(1).strip()
    return bool(re.match(r"^[A-Za-z0-9_\-]+,\d+[A-Za-z0-9_\-]*$", key))


def is_group_heading(line: str, lines: list[str], index: int, previous_blank: bool) -> bool:
    stripped = line.strip()
    if not stripped or "=" in stripped or len(stripped) > 36:
        return False
    if re.match(r"^[\d一二三四五六七八九十]+[\.、:：]", stripped):
        return False

    next_line = next_nonempty_line(lines, index)
    if not is_key_value_line(next_line):
        return False

    if previous_blank:
        return True
    if stripped.endswith(("：", ":")):
        return True
    if "话术" in stripped:
        return True
    return False


def parse_raw_file(path: Path) -> list[ParsedSnippet]:
    text = read_text(path)
    lines = text.splitlines()
    snippets: list[ParsedSnippet] = []
    current_group = DEFAULT_GROUP
    current_key: str | None = None
    current_line_no = 0
    current_content_lines: list[str] = []
    previous_blank = True

    def flush_current() -> None:
        nonlocal current_key, current_line_no, current_content_lines
        if current_key is None:
            return
        content = normalize_space("\n".join(current_content_lines))
        snippets.append(
            ParsedSnippet(
                original_key=current_key,
                original_group=current_group,
                content=content,
                line_no=current_line_no,
            )
        )
        current_key = None
        current_line_no = 0
        current_content_lines = []

    for index, raw_line in enumerate(lines):
        line_no = index + 1
        stripped = raw_line.strip()

        key_match = KEY_VALUE_RE.match(raw_line)
        if key_match and is_key_value_line(raw_line):
            flush_current()
            current_key = key_match.group(1).strip()
            current_line_no = line_no
            current_content_lines = [key_match.group(2).strip()]
            previous_blank = False
            continue

        if not stripped:
            if current_key is not None and current_content_lines and current_content_lines[-1] != "":
                current_content_lines.append("")
            previous_blank = True
            continue

        if is_group_heading(raw_line, lines, index, previous_blank):
            flush_current()
            current_group = clean_group(stripped)
            previous_blank = False
            continue

        if current_key is not None:
            current_content_lines.append(stripped)

        previous_blank = False

    flush_current()
    return snippets


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def infer_category(group: str, content: str) -> str:
    text = f"{group} {content}"
    for category, keywords in CATEGORY_RULES:
        if contains_any(text, keywords):
            return category
    return "其他"


def detect_risks(content: str) -> list[str]:
    risks = []
    for risk_name, pattern in RISK_RULES:
        if pattern.search(content):
            risks.append(risk_name)
    return risks


def infer_source_type(group: str, content: str, risks: list[str]) -> str:
    if risks:
        return "risky_script"
    text = f"{group} {content}"
    for source_type, keywords in SOURCE_TYPE_RULES:
        if contains_any(text, keywords):
            return source_type
    return "script_template"


def needs_backend_api(content: str, risks: list[str]) -> bool:
    if "后台操作已完成" in risks:
        return True
    return contains_any(content, BACKEND_API_KEYWORDS)


def is_meaningless(content: str) -> bool:
    compact = normalize_space(content).replace(" ", "")
    if not compact:
        return True
    if len(compact) <= 3:
        return True
    return any(pattern.match(compact) for pattern in MEANINGLESS_PATTERNS)


def conservative_rewrite(content: str, risks: list[str]) -> str | None:
    if not risks:
        return content
    if any(risk in NON_REWRITABLE_RISKS for risk in risks):
        return None

    rewrite_parts: list[str] = []
    if "具体补偿金额" in risks:
        rewrite_parts.append(
            "涉及补偿、返款、报销运费或差价处理时，需要人工客服结合订单、商品状态和平台规则核实协商，不承诺具体金额。"
        )

    if "后台操作已完成" in risks:
        if "催促" in content or "快递" in content:
            rewrite_parts.append("具体物流催促需要人工客服查询后台后处理，并以平台物流状态为准。")
        elif any(keyword in content for keyword in ["打款", "返款", "到账"]):
            rewrite_parts.append("返款或打款到账情况需要人工客服查询后台后核实，不应直接承诺已完成。")
        elif "拦截" in content:
            rewrite_parts.append("订单拦截结果需要人工客服查询后台后确认，并以平台处理结果为准。")
        elif "售后" in content:
            rewrite_parts.append("售后申请进度需要人工客服查询后台后处理，并按平台规则执行。")
        elif "退款" in content:
            rewrite_parts.append("退款进度需要人工客服查询后台后核实，并以平台到账状态为准。")
        else:
            rewrite_parts.append("具体后台处理结果需要人工客服查询后确认，不应直接承诺已完成。")

    deduped_parts = list(dict.fromkeys(rewrite_parts))
    rewritten = normalize_space(" ".join(deduped_parts))
    if not rewritten:
        return None
    if detect_risks(rewritten):
        return None
    if is_meaningless(rewritten):
        return None
    return rewritten


def priority_for(source_type: str, category: str, rewritten: bool = False) -> int:
    if rewritten:
        return 60
    if source_type in {"policy_rule", "shipping_rule", "aftersales_rule", "backend_rule"}:
        return 90
    if category in {"尺码问题", "商品咨询", "正品保障"}:
        return 80
    return 70


def make_row(
    snippet: ParsedSnippet,
    content: str,
    source_type: str,
    category: str,
    allowed: bool,
    backend_needed: bool,
    risk_note: str,
    priority: int,
) -> dict[str, str]:
    return {
        "source_file": SOURCE_FILE_VALUE,
        "platform": PLATFORM,
        "source_type": source_type,
        "category": category,
        "title": f"{snippet.original_group} {snippet.original_key}",
        "content": content,
        "priority": str(priority),
        "allowed_for_answer": "true" if allowed else "false",
        "needs_backend_api": "true" if backend_needed else "false",
        "risk_note": risk_note,
        "original_key": snippet.original_key,
        "original_group": snippet.original_group,
    }


def build_rows(snippets: list[ParsedSnippet]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    accepted_rows: list[dict[str, str]] = []
    rejected_rows: list[dict[str, str]] = []

    for snippet in snippets:
        content = normalize_space(snippet.content)
        category = infer_category(snippet.original_group, content)
        risks = detect_risks(content)

        if is_meaningless(content):
            rejected_rows.append(
                make_row(
                    snippet,
                    content,
                    "script_template",
                    category,
                    False,
                    False,
                    "meaningless_or_greeting",
                    0,
                )
            )
            continue

        if risks:
            rejected_rows.append(
                make_row(
                    snippet,
                    content,
                    "risky_script",
                    category,
                    False,
                    needs_backend_api(content, risks),
                    "risk:" + ";".join(risks),
                    0,
                )
            )
            rewritten = conservative_rewrite(content, risks)
            if rewritten:
                rewritten_risks: list[str] = []
                rewritten_source_type = infer_source_type(snippet.original_group, rewritten, rewritten_risks)
                if "具体补偿金额" in risks or "后台操作已完成" in risks:
                    rewritten_source_type = "backend_rule"
                elif rewritten_source_type == "script_template" and needs_backend_api(content, risks):
                    rewritten_source_type = "backend_rule"
                accepted_rows.append(
                    make_row(
                        snippet,
                        rewritten,
                        rewritten_source_type,
                        category,
                        True,
                        needs_backend_api(rewritten, rewritten_risks) or needs_backend_api(content, risks),
                        "conservative_rewrite_from_risky_original:" + ";".join(risks),
                        priority_for(rewritten_source_type, category, rewritten=True),
                    )
                )
            continue

        source_type = infer_source_type(snippet.original_group, content, risks)
        accepted_rows.append(
            make_row(
                snippet,
                content,
                source_type,
                category,
                True,
                needs_backend_api(content, risks),
                "",
                priority_for(source_type, category),
            )
        )

    return accepted_rows, rejected_rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def truncate(value: str, limit: int = 90) -> str:
    value = normalize_space(value).replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 1] + "..."


def rows_to_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "_无_"
    lines = [
        "| original_key | category | source_type | allowed | content |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows[:10]:
        lines.append(
            "| {original_key} | {category} | {source_type} | {allowed_for_answer} | {content} |".format(
                original_key=md_escape(row["original_key"]),
                category=md_escape(row["category"]),
                source_type=md_escape(row["source_type"]),
                allowed_for_answer=row["allowed_for_answer"],
                content=md_escape(truncate(row["content"])),
            )
        )
    return "\n".join(lines)


def counter_section(title: str, counter: Counter[str]) -> str:
    lines = [f"## {title}", "", "| 名称 | 数量 |", "| --- | ---: |"]
    if not counter:
        lines.append("| 无 | 0 |")
    else:
        for name, count in counter.most_common():
            lines.append(f"| {md_escape(name)} | {count} |")
    return "\n".join(lines)


def risk_counter(rejected_rows: list[dict[str, str]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rejected_rows:
        note = row["risk_note"]
        if note == "meaningless_or_greeting":
            counter["meaningless_or_greeting"] += 1
            continue
        if note.startswith("risk:"):
            for risk in note.removeprefix("risk:").split(";"):
                if risk:
                    counter[risk] += 1
    return counter


def write_report(
    path: Path,
    parsed_count: int,
    accepted_rows: list[dict[str, str]],
    rejected_rows: list[dict[str, str]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    all_rows = accepted_rows + rejected_rows
    allowed_counter = Counter(row["allowed_for_answer"] for row in all_rows)
    category_counts = Counter(row["category"] for row in accepted_rows)
    source_type_counts = Counter(row["source_type"] for row in accepted_rows)
    risks = risk_counter(rejected_rows)
    rewrite_count = sum(
        1 for row in accepted_rows if row["risk_note"].startswith("conservative_rewrite_from_risky_original:")
    )

    report = [
        "# JD Knowledge Snippets V2 Report",
        "",
        "## Summary",
        "",
        f"- 原始解析条数: {parsed_count}",
        f"- accepted 条数: {len(accepted_rows)}",
        f"- rejected 条数: {len(rejected_rows)}",
        f"- allowed_for_answer=true 数量: {allowed_counter.get('true', 0)}",
        f"- allowed_for_answer=false 数量: {allowed_counter.get('false', 0)}",
        f"- 保守改写进入 accepted 数量: {rewrite_count}",
        "",
        counter_section("各 category 数量", category_counts),
        "",
        counter_section("各 source_type 数量", source_type_counts),
        "",
        counter_section("风险类型统计", risks),
        "",
        "## 示例 accepted 10 条",
        "",
        rows_to_table(accepted_rows),
        "",
        "## 示例 rejected 10 条",
        "",
        rows_to_table(rejected_rows),
        "",
    ]
    path.write_text("\n".join(report), encoding="utf-8")


def main() -> None:
    print("Building JD knowledge snippets for RAG V2...")
    print(f"Reading raw file: {RAW_FILE}")

    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Raw file not found: {RAW_FILE}")

    snippets = parse_raw_file(RAW_FILE)
    accepted_rows, rejected_rows = build_rows(snippets)

    write_csv(OUTPUT_CSV, accepted_rows)
    write_csv(REJECTED_CSV, rejected_rows)
    write_report(REPORT_MD, len(snippets), accepted_rows, rejected_rows)

    print(f"Parsed raw snippets: {len(snippets)}")
    print(f"Accepted rows: {len(accepted_rows)}")
    print(f"Rejected rows: {len(rejected_rows)}")
    print("Generated files:")
    print(f"- {OUTPUT_CSV}")
    print(f"- {REPORT_MD}")
    print(f"- {REJECTED_CSV}")


if __name__ == "__main__":
    main()
