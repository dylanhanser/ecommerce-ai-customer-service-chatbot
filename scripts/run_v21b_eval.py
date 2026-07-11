#!/usr/bin/env python3
"""Run V2.1b against the fixed V2.1a baseline with state-specific assertions."""

from __future__ import annotations

import os

os.environ["RAG_EVAL_SYSTEM_VERSION"] = "V2.1b"

import run_v21a_baseline_eval as baseline  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(baseline.main())
