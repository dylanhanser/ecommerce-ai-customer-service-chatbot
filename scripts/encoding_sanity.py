#!/usr/bin/env python3
"""Reusable UTF-8 and readable-Chinese checks for V2.1b fixtures."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


MOJIBAKE_MARKERS = (
    "鎴戜殑",
    "閭ｄ綘",
    "杩欓瀷",
)


def assert_readable_chinese(text: str) -> None:
    """Fail early when a string contains a known corrupted-Chinese marker."""
    hits = [marker for marker in MOJIBAKE_MARKERS if marker in str(text or "")]
    assert not hits, f"Mojibake detected: {hits}"


def assert_readable_chinese_values(value: object) -> None:
    """Recursively validate strings in test cases, keyword lists, and fixtures."""
    if isinstance(value, str):
        assert_readable_chinese(value)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            assert_readable_chinese_values(key)
            assert_readable_chinese_values(item)
        return
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        for item in value:
            assert_readable_chinese_values(item)
