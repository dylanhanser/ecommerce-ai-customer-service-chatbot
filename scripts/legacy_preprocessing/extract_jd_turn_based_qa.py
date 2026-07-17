#!/usr/bin/env python3
"""Extract JD QA pairs from non-overlapping customer/service conversation turns."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


OUTPUT_FIELDS = (
    "session_id",
    "source_file",
    "question_time_start",
    "question_time_end",
    "merged_question",
    "answer_time_start",
    "answer_time_end",
    "answer",
    "category",
    "customer_turn_message_count",
    "service_turn_message_count",
)
REJECTED_FIELDS = OUTPUT_FIELDS + ("reject_reason",)
SUMMARY_FIELDS = (
    "input_sessions",
    "input_messages",
    "output_qa_pairs",
    "rejected_qa_pairs",
    "average_customer_turn_message_count",
    "average_service_turn_message_count",
    "category_distribution",
    "average_question_length",
    "average_answer_length",
)

URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
IMAGE_TOKEN_RE = re.compile(
    r"^(?:\[?图片\]?|\[?image\]?|图片链接|查看图片|发送了一张图片)$", re.IGNORECASE
)
SERVICE_CODE_RE = re.compile(r"#\s*E\s*[-_]\s*[A-Z]\s*\d+", re.IGNORECASE)
UNSUPPORTED_TEMPLATE_RE = re.compile(r"聊天记录中暂不支持展示|此消息为.*(?:模板|卡片)")
PUNCT_RE = re.compile(r"[\s\u3000，,。.!！?？~～、；;：:…·\-]+")
VISIBLE_TEXT_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")

CUSTOMER_NOISE = {
    "你好", "您好", "在吗", "亲", "亲亲", "喂", "哈喽", "hello", "hi", "有人吗", "客服在吗",
    "请问在吗", "？", "?", "嗯", "嗯嗯", "好的", "好", "好吧", "谢谢", "谢谢亲", "ok", "哦",
    "知道了", "明白了",
}
SERVICE_NOISE = {
    "在的亲", "在呢亲", "亲亲您好", "亲亲你好", "您好亲", "你好亲",
    "亲亲您好有什么需要我帮助的呢", "亲亲你好有什么需要我帮助的呢",
    "您好有什么需要我帮助的呢", "你好有什么需要我帮助的呢",
    "稍等", "稍等一下", "请稍等", "请稍等一下", "稍等哈", "稍等亲", "稍等一下亲",
    "好的亲", "好的呢亲", "好的", "嗯嗯", "嗯", "收到",
}
BAD_ANSWER_TEMPLATES = {
    "可以的", "可以", "好的亲", "好的", "是的", "是的亲", "没有呢", "没有", "稍等",
    "稍等亲", "稍等一下", "嗯嗯", "嗯", "不可以", "不可以的",
}
SHORT_FOLLOWUPS = {
    "怎么办", "怎么办呀", "怎么处理", "咋处理", "这咋办", "可以吗", "行吗", "退吗", "换吗",
    "然后呢", "什么意思", "为什么", "那呢", "这个呢", "还没发", "无货了", "不行", "不可以",
}
BUSINESS_KEYWORDS = (
    "尺码", "码数", "偏大", "偏小", "发货", "快递", "物流", "退货", "退款", "换货", "运费",
    "质量", "开胶", "发错", "补偿", "赔偿", "材质", "防滑", "正品", "颜色", "无货", "拒收",
    "派送", "京东余额", "地址", "拦截", "款式", "增高", "保暖",
)
CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("尺码问题", ("尺码", "码数", "偏大", "偏小")),
    ("退货退款", ("退货", "退款")),
    ("换货", ("换货",)),
    ("运费", ("运费",)),
    ("物流发货", ("发货", "快递", "物流", "拒收", "派送", "地址", "拦截")),
    ("质量问题", ("质量", "开胶", "发错")),
    ("商品咨询", ("材质", "防滑", "正品", "颜色", "款式", "增高", "保暖")),
    ("价格补偿", ("补偿", "赔偿", "京东余额")),
    ("库存问题", ("无货",)),
)


@dataclass
class Message:
    session_id: str
    source_file: str
    sender_type: str
    message_time: str
    parsed_time: datetime | None
    content: str
    input_order: int


@dataclass
class Turn:
    sender_type: str
    messages: list[Message]


def normalize(text: str) -> str:
    return PUNCT_RE.sub("", text or "").casefold()


NORMALIZED_CUSTOMER_NOISE = {normalize(value) for value in CUSTOMER_NOISE}
NORMALIZED_SERVICE_NOISE = {normalize(value) for value in SERVICE_NOISE}
NORMALIZED_BAD_ANSWERS = {normalize(value) for value in BAD_ANSWER_TEMPLATES}
NORMALIZED_FOLLOWUPS = {normalize(value) for value in SHORT_FOLLOWUPS}


def parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d %H:%M:%S")
    except (ValueError, AttributeError):
        return None


def is_pure_url_or_image(text: str) -> bool:
    value = text.strip()
    if not value:
        return False
    pieces = [piece.strip() for piece in re.split(r"[\s；;]+", value) if piece.strip()]
    return bool(pieces) and all(
        URL_RE.fullmatch(piece) or IMAGE_TOKEN_RE.fullmatch(piece) for piece in pieces
    )


def clean_customer(text: str) -> str:
    value = text.replace("\ufeff", "").strip(" \t\r\n；;")
    if not value or is_pure_url_or_image(value):
        return ""
    token = normalize(value)
    if not token or token in NORMALIZED_CUSTOMER_NOISE or not VISIBLE_TEXT_RE.search(value):
        return ""
    return re.sub(r"\s*\r?\n\s*", "；", value)


def clean_service(text: str) -> str:
    value = text.replace("\ufeff", "").strip(" \t\r\n；;")
    if not value or is_pure_url_or_image(value) or UNSUPPORTED_TEMPLATE_RE.search(value):
        return ""
    value = SERVICE_CODE_RE.sub("", value).strip(" \t，,。；;：:")
    token = normalize(value)
    if not token or token in NORMALIZED_SERVICE_NOISE or not VISIBLE_TEXT_RE.search(value):
        return ""
    return re.sub(r"\s*\r?\n\s*", "；", value)


def load_messages(path: Path) -> tuple[dict[str, list[Message]], int]:
    sessions: dict[str, list[Message]] = defaultdict(list)
    required = {"session_id", "source_file", "sender_type", "message_time", "message_content"}
    input_messages = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError("输入 CSV 缺少字段：" + ", ".join(sorted(missing)))
        for input_messages, row in enumerate(reader, start=1):
            session_id = (row.get("session_id") or "").strip()
            sender_type = (row.get("sender_type") or "").strip().casefold()
            if not session_id or sender_type not in {"customer", "service"}:
                continue
            time_text = (row.get("message_time") or "").strip()
            sessions[session_id].append(
                Message(
                    session_id=session_id,
                    source_file=row.get("source_file") or "",
                    sender_type=sender_type,
                    message_time=time_text,
                    parsed_time=parse_datetime(time_text),
                    content=row.get("message_content") or "",
                    input_order=input_messages,
                )
            )
    for messages in sessions.values():
        messages.sort(
            key=lambda message: (
                0 if message.parsed_time is not None else 1,
                message.parsed_time or datetime.max,
                message.input_order,
            )
        )
    return sessions, input_messages


def make_turns(messages: list[Message]) -> list[Turn]:
    """Create strict, non-overlapping runs of the same sender type."""
    turns: list[Turn] = []
    for message in messages:
        if not turns or turns[-1].sender_type != message.sender_type:
            turns.append(Turn(message.sender_type, [message]))
        else:
            turns[-1].messages.append(message)
    return turns


def clean_turn(turn: Turn) -> list[tuple[Message, str]]:
    cleaner = clean_customer if turn.sender_type == "customer" else clean_service
    cleaned: list[tuple[Message, str]] = []
    seen: set[str] = set()
    for message in turn.messages:
        value = cleaner(message.content)
        if not value:
            continue
        key = normalize(value)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append((message, value))
    return cleaned


def classify(question: str, answer: str) -> str:
    for text in (question, answer):
        for category, keywords in CATEGORIES:
            if any(keyword in text for keyword in keywords):
                return category
    return "其他"


def rejection_reasons(question: str, answer: str) -> list[str]:
    reasons: list[str] = []
    question_token = normalize(question)
    answer_token = normalize(answer)
    has_business_keyword = any(keyword in question for keyword in BUSINESS_KEYWORDS)
    if not question or question_token in NORMALIZED_FOLLOWUPS:
        reasons.append("context_missing")
    if len(question) < 6 and not has_business_keyword:
        reasons.append("too_short_question")
    if len(answer) < 10 or answer_token in NORMALIZED_BAD_ANSWERS:
        reasons.append("bad_answer")
    return list(dict.fromkeys(reasons))


def make_row(
    session_id: str,
    customer_items: list[tuple[Message, str]],
    service_items: list[tuple[Message, str]],
) -> dict[str, str | int]:
    question = "；".join(value for _, value in customer_items)
    answer = "；".join(value for _, value in service_items)
    customer_messages = [message for message, _ in customer_items]
    service_messages = [message for message, _ in service_items]
    source_file = next(
        (message.source_file for message in customer_messages + service_messages if message.source_file), ""
    )
    return {
        "session_id": session_id,
        "source_file": source_file,
        "question_time_start": customer_messages[0].message_time if customer_messages else "",
        "question_time_end": customer_messages[-1].message_time if customer_messages else "",
        "merged_question": question,
        "answer_time_start": service_messages[0].message_time if service_messages else "",
        "answer_time_end": service_messages[-1].message_time if service_messages else "",
        "answer": answer,
        "category": classify(question, answer),
        "customer_turn_message_count": len(customer_items),
        "service_turn_message_count": len(service_items),
    }


def extract(input_path: Path, output_dir: Path) -> tuple[int, int, int, int]:
    sessions, input_messages = load_messages(input_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    qa_path = output_dir / "jd_turn_based_qa.csv"
    rejected_path = output_dir / "jd_turn_based_rejected.csv"
    summary_path = output_dir / "jd_turn_based_summary.csv"

    output_count = 0
    rejected_count = 0
    customer_count_sum = 0
    service_count_sum = 0
    question_length_sum = 0
    answer_length_sum = 0
    category_counts: Counter[str] = Counter()

    with (
        qa_path.open("w", encoding="utf-8-sig", newline="") as qa_handle,
        rejected_path.open("w", encoding="utf-8-sig", newline="") as rejected_handle,
    ):
        qa_writer = csv.DictWriter(qa_handle, fieldnames=OUTPUT_FIELDS)
        rejected_writer = csv.DictWriter(rejected_handle, fieldnames=REJECTED_FIELDS)
        qa_writer.writeheader()
        rejected_writer.writeheader()

        for session_id in sorted(sessions):
            turns = make_turns(sessions[session_id])
            index = 0
            while index < len(turns):
                current = turns[index]
                if current.sender_type != "customer":
                    index += 1
                    continue
                if index + 1 >= len(turns) or turns[index + 1].sender_type != "service":
                    index += 1
                    continue

                # Consume exactly this customer turn and the immediately following
                # service turn. Nothing from either turn can enter a future QA.
                customer_items = clean_turn(current)
                service_items = clean_turn(turns[index + 1])
                row = make_row(session_id, customer_items, service_items)
                reasons = rejection_reasons(str(row["merged_question"]), str(row["answer"]))
                if reasons:
                    rejected_writer.writerow({**row, "reject_reason": ";".join(reasons)})
                    rejected_count += 1
                else:
                    qa_writer.writerow(row)
                    output_count += 1
                    customer_count_sum += int(row["customer_turn_message_count"])
                    service_count_sum += int(row["service_turn_message_count"])
                    question_length_sum += len(str(row["merged_question"]))
                    answer_length_sum += len(str(row["answer"]))
                    category_counts[str(row["category"])] += 1
                index += 2

    category_order = [*(category for category, _ in CATEGORIES), "其他"]
    summary = {
        "input_sessions": len(sessions),
        "input_messages": input_messages,
        "output_qa_pairs": output_count,
        "rejected_qa_pairs": rejected_count,
        "average_customer_turn_message_count": round(customer_count_sum / output_count, 2) if output_count else 0,
        "average_service_turn_message_count": round(service_count_sum / output_count, 2) if output_count else 0,
        "category_distribution": json.dumps(
            {category: category_counts.get(category, 0) for category in category_order},
            ensure_ascii=False,
        ),
        "average_question_length": round(question_length_sum / output_count, 2) if output_count else 0,
        "average_answer_length": round(answer_length_sum / output_count, 2) if output_count else 0,
    }
    with summary_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerow(summary)
    return len(sessions), input_messages, output_count, rejected_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="直接从 jd_messages.csv 提取互不重叠的 turn-based 京东 QA。"
    )
    parser.add_argument("input", help="jd_messages.csv 路径")
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
        sessions, messages, output_count, rejected_count = extract(input_path, output_dir)
    except (OSError, ValueError, csv.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(
        f"完成：输入 {sessions} 个会话、{messages} 条消息；"
        f"输出 {output_count} 组 QA，拒绝 {rejected_count} 组候选"
    )
    print(f"输出目录：{output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
