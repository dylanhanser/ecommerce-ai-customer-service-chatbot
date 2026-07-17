#!/usr/bin/env python3
"""Parse JD customer-service chat TXT files into message/session CSV files.

Inputs may be TXT files, ZIP files containing TXT files, or directories.  ZIP
members are read directly, so large archives do not need to be extracted first.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import zipfile
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator


SESSION_START_TEXT = "以下为一通会话"
SESSION_END_FALLBACK_TEXT = "会话结束"
SERVICE_KEYWORDS = ("阿拉蕾", "盼盼", "回力恒大", "恒大鞋靴")

HEADER_RE = re.compile(
    r"^\s*(?P<sender>.+?)\s+"
    r"(?P<time>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\s*$"
)
END_TIME_RE = re.compile(
    r"会话结束_时间\s*[:：]\s*(?P<time>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})"
)
URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
IMAGE_RE = re.compile(r"\.(?:jpe?g|png|gif|webp|bmp)(?:[?#]\S*)?\b", re.IGNORECASE)

MESSAGE_FIELDS = (
    "session_id",
    "sender",
    "sender_type",
    "message_time",
    "message_content",
    "content_type",
    "source_file",
)
SUMMARY_FIELDS = (
    "session_id",
    "source_file",
    "message_count",
    "customer_message_count",
    "service_message_count",
    "start_time",
    "end_time",
)
ERROR_FIELDS = (
    "source_file",
    "line_number",
    "session_id",
    "error_type",
    "raw_line",
    "detail",
)


@dataclass
class TextSource:
    name: str
    data: bytes


class CsvSink:
    """Small append-compatible CSV writer used for streaming output."""

    def __init__(self, handle, fieldnames: tuple[str, ...]):
        self.writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        self.writer.writeheader()
        self.count = 0

    def append(self, row: dict) -> None:
        self.writer.writerow(row)
        self.count += 1


def decode_text(data: bytes) -> tuple[str, str]:
    """Decode common Chinese text encodings, returning (text, encoding)."""
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            pass
    # Preserve as much data as possible and report the replacement in errors.
    return data.decode("utf-8", errors="replace"), "utf-8-replace"


def iter_input_paths(values: Iterable[str]) -> Iterator[Path]:
    """Expand input files/directories in a stable, duplicate-free order."""
    found: dict[str, Path] = {}
    for value in values:
        path = Path(value).expanduser()
        if path.is_dir():
            candidates = (
                p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".zip"}
            )
        elif path.is_file():
            candidates = iter((path,))
        else:
            print(f"Warning: input does not exist, skipped: {path}", file=sys.stderr)
            continue
        for candidate in candidates:
            key = str(candidate.resolve()).casefold()
            found[key] = candidate.resolve()
    yield from (found[key] for key in sorted(found))


def iter_text_sources(paths: Iterable[Path], errors: CsvSink) -> Iterator[TextSource]:
    for path in paths:
        if path.suffix.lower() == ".txt":
            try:
                yield TextSource(str(path), path.read_bytes())
            except OSError as exc:
                add_error(errors, str(path), 0, "", "file_read_error", "", str(exc))
            continue

        try:
            with zipfile.ZipFile(path) as archive:
                members = sorted(
                    (info for info in archive.infolist() if not info.is_dir() and info.filename.lower().endswith(".txt")),
                    key=lambda info: info.filename.casefold(),
                )
                if not members:
                    add_error(errors, str(path), 0, "", "zip_has_no_txt", "", "ZIP 中没有 TXT 文件")
                for info in members:
                    source_name = f"{path}!{info.filename}"
                    try:
                        yield TextSource(source_name, archive.read(info))
                    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                        add_error(errors, source_name, 0, "", "zip_member_read_error", "", str(exc))
        except (OSError, zipfile.BadZipFile) as exc:
            add_error(errors, str(path), 0, "", "zip_read_error", "", str(exc))


def add_error(
    errors: CsvSink,
    source_file: str,
    line_number: int,
    session_id: str,
    error_type: str,
    raw_line: str,
    detail: str,
) -> None:
    errors.append(
        {
            "source_file": source_file,
            "line_number": line_number,
            "session_id": session_id,
            "error_type": error_type,
            "raw_line": raw_line,
            "detail": detail,
        }
    )


def is_valid_datetime(value: str) -> bool:
    try:
        datetime.strptime(value.replace("T", " "), "%Y-%m-%d %H:%M:%S")
        return True
    except ValueError:
        return False


def classify_content(content: str) -> str:
    return "image_or_link" if URL_RE.search(content) or IMAGE_RE.search(content) else "text"


def parse_source(
    source: TextSource,
    session_counter: int,
    messages: CsvSink,
    summaries: CsvSink,
    errors: CsvSink,
) -> int:
    text, encoding = decode_text(source.data)
    if encoding == "utf-8-replace":
        add_error(errors, source.name, 0, "", "decode_replacement", "", "无法严格解码；已用 UTF-8 替换无效字符")

    in_session = False
    session_id = ""
    session_messages: list[dict] = []
    current_header: tuple[str, str, int, str] | None = None
    current_content: list[str] = []

    def flush_message() -> None:
        nonlocal current_header, current_content
        if current_header is None:
            return
        sender, message_time, header_line, raw_header = current_header
        # Strip separator whitespace but preserve meaningful multiline content.
        while current_content and not current_content[0].strip():
            current_content.pop(0)
        while current_content and not current_content[-1].strip():
            current_content.pop()
        content = "\n".join(line.rstrip("\r\n\t") for line in current_content)
        if not content:
            add_error(
                errors, source.name, header_line, session_id,
                "missing_message_content", raw_header, "消息头后没有正文",
            )
        row = {
            "session_id": session_id,
            "sender": sender.strip(),
            "sender_type": "service" if any(k in sender for k in SERVICE_KEYWORDS) else "customer",
            "message_time": message_time.replace("T", " "),
            "message_content": content,
            "content_type": classify_content(content),
            "source_file": source.name,
        }
        messages.append(row)
        session_messages.append(row)
        current_header = None
        current_content = []

    def close_session(end_time: str, line_number: int, implicit: bool = False) -> None:
        nonlocal in_session, session_id, session_messages, current_header, current_content
        flush_message()
        if implicit:
            add_error(
                errors, source.name, line_number, session_id,
                "missing_session_end", "", "遇到下一会话或文件结束，已自动关闭当前会话",
            )
        times = [row["message_time"] for row in session_messages]
        summaries.append(
            {
                "session_id": session_id,
                "source_file": source.name,
                "message_count": len(session_messages),
                "customer_message_count": sum(r["sender_type"] == "customer" for r in session_messages),
                "service_message_count": sum(r["sender_type"] == "service" for r in session_messages),
                "start_time": min(times) if times else "",
                "end_time": end_time or (max(times) if times else ""),
            }
        )
        if not session_messages:
            add_error(errors, source.name, line_number, session_id, "empty_session", "", "会话中没有解析到消息")
        in_session = False
        session_id = ""
        session_messages = []
        current_header = None
        current_content = []

    for line_number, raw_line in enumerate(io.StringIO(text), start=1):
        line = raw_line.rstrip("\r\n").rstrip("\t")

        if SESSION_START_TEXT in line:
            if in_session:
                close_session("", line_number, implicit=True)
            session_counter += 1
            session_id = f"JD{session_counter:09d}"
            in_session = True
            session_messages = []
            continue

        # Some exports contain a shortened "会话结束" marker without _时间.
        # Treat it as a boundary, but record the missing timestamp as dirty data.
        if SESSION_END_FALLBACK_TEXT in line:
            if not in_session:
                add_error(errors, source.name, line_number, "", "end_without_start", line, "会话结束标记前没有开始标记")
                continue
            match = END_TIME_RE.search(line)
            end_time = match.group("time").replace("T", " ") if match else ""
            if not match or not is_valid_datetime(end_time):
                add_error(errors, source.name, line_number, session_id, "invalid_session_end_time", line, "无法解析会话结束时间")
                end_time = ""
            close_session(end_time, line_number)
            continue

        if not in_session:
            if line.strip():
                add_error(errors, source.name, line_number, "", "line_outside_session", line, "非空行不在会话范围内")
            continue

        header = HEADER_RE.match(line)
        if header:
            message_time = header.group("time")
            if not is_valid_datetime(message_time):
                add_error(errors, source.name, line_number, session_id, "invalid_message_time", line, "消息时间无效")
                if current_header is not None:
                    current_content.append(line)
                continue
            flush_message()
            current_header = (header.group("sender"), message_time, line_number, line)
            continue

        if current_header is None:
            if line.strip():
                add_error(errors, source.name, line_number, session_id, "content_without_header", line, "正文前没有可识别的发送者和时间")
        else:
            current_content.append(line)

    if in_session:
        close_session("", max(1, text.count("\n") + 1), implicit=True)
    return session_counter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="解析京东客服聊天 TXT/ZIP，生成消息、会话汇总和异常 CSV。"
    )
    parser.add_argument(
        "inputs", nargs="+", metavar="INPUT",
        help="一个或多个 TXT、ZIP 或目录（目录会递归查找 TXT/ZIP）",
    )
    parser.add_argument(
        "-o", "--output-dir", default=".",
        help="CSV 输出目录（默认：当前目录）",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = list(iter_input_paths(args.inputs))
    if not paths:
        print("Error: 没有找到可处理的 TXT 或 ZIP 文件。", file=sys.stderr)
        return 2

    counter = 0
    source_count = 0
    with ExitStack() as stack:
        message_handle = stack.enter_context(
            (output_dir / "jd_messages.csv").open("w", encoding="utf-8-sig", newline="")
        )
        summary_handle = stack.enter_context(
            (output_dir / "jd_sessions_summary.csv").open("w", encoding="utf-8-sig", newline="")
        )
        error_handle = stack.enter_context(
            (output_dir / "jd_parse_errors.csv").open("w", encoding="utf-8-sig", newline="")
        )
        messages = CsvSink(message_handle, MESSAGE_FIELDS)
        summaries = CsvSink(summary_handle, SUMMARY_FIELDS)
        errors = CsvSink(error_handle, ERROR_FIELDS)

        for source in iter_text_sources(paths, errors):
            source_count += 1
            counter = parse_source(source, counter, messages, summaries, errors)

        message_count = messages.count
        summary_count = summaries.count
        error_count = errors.count

    print(f"完成：{source_count} 个 TXT，{summary_count} 个会话，{message_count} 条消息，{error_count} 条异常")
    print(f"输出目录：{output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
