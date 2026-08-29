#!/usr/bin/env python3
"""Command-line RAG answer demo for the final JD QA corpus."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, time
from enum import Enum
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data" / "processed"
DEFAULT_QA_CSV_PATH = DEFAULT_DATA_DIR / "jd_final_safe_qa_refined_category.csv"
DEFAULT_SNIPPETS_CSV_PATH = DEFAULT_DATA_DIR / "knowledge_snippets_v2_reviewed.csv"
FALLBACK_QA_CSV_PATH = MODULE_DIR / "jd_final_safe_qa_refined_category.csv"
DEFAULT_CACHE_ROOT = MODULE_DIR / "cache"
V1_CACHE_SUBDIR = "v1_qa"
V2_CACHE_SUBDIR = "v2_mixed"
QA_CORPUS_SOURCE_FILE = "jd_final_safe_qa_refined_category.csv"
SNIPPETS_CORPUS_SOURCE_FILE = "knowledge_snippets_v2_reviewed.csv"
BACKEND_SOURCE_TYPES = frozenset({"backend_rule"})
QUARANTINED_KNOWLEDGE_DOC_IDS = {
    "snippet_yf_1": (
        "conflicting absolute freight-insurance statement; use conditional current-policy guidance"
    ),
    "snippet_zp_1": (
        "unverified PICC/authenticity-insurance endorsement; canonical support is absent"
    ),
}
SNIPPET_EMBED_CONTENT_LIMIT = 240
EMBEDDING_FILENAME = "qa_embeddings.npy"
CORPUS_FILENAME = "qa_corpus.pkl"
MIXED_EMBEDDING_FILENAME = "mixed_embeddings_v2.npy"
MIXED_CORPUS_FILENAME = "mixed_corpus_v2.pkl"
CORPUS_VERSION_V1 = "v1_qa_only"
CORPUS_VERSION_V2_MIXED = "v2_mixed"
DEFAULT_QA_PRIORITY = 50
LOW_CONFIDENCE_THRESHOLD = 0.55

LOW_CONFIDENCE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8fd9\u4e2a\u95ee\u9898\u6211\u6682\u65f6\u65e0\u6cd5"
    "\u786e\u8ba4\uff0c\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u4e3a\u60a8"
    "\u6838\u5b9e\u3002"
)
INVALID_INPUT_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u6211\u6ca1\u6709\u592a\u7406\u89e3\u60a8\u7684\u610f\u601d\uff0c"
    "\u53ef\u4ee5\u9ebb\u70e6\u60a8\u518d\u5177\u4f53\u63cf\u8ff0\u4e00\u4e0b\u5546\u54c1\u3001"
    "\u5c3a\u7801\u3001\u8ba2\u5355\u6216\u552e\u540e\u95ee\u9898\u5417\uff1f"
)
UNCLEAR_ANSWER = INVALID_INPUT_ANSWER
IDENTITY_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u6211\u662f\u672c\u5e97\u7684 AI \u5ba2\u670d\u52a9\u624b\uff0c"
    "\u53ef\u4ee5\u5e2e\u60a8\u89e3\u7b54\u5546\u54c1\u3001\u5c3a\u7801\u3001"
    "\u9000\u6362\u8d27\u3001\u8fd0\u8d39\u3001\u7269\u6d41\u89c4\u5219\u7b49"
    "\u5e38\u89c1\u95ee\u9898\u3002\u5982\u679c\u6d89\u53ca\u5177\u4f53\u8ba2\u5355"
    "\u72b6\u6001\u3001\u7269\u6d41\u8fdb\u5ea6\u6216\u552e\u540e\u8fdb\u5ea6\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u4e3a\u60a8\u6838\u5b9e\u54e6\u3002"
)
HUMAN_HANDOVER_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u597d\u7684\uff0c\u8fd9\u4e2a\u95ee\u9898\u5efa\u8bae\u8f6c"
    "\u4eba\u5de5\u5ba2\u670d\u4e3a\u60a8\u8fdb\u4e00\u6b65\u5904\u7406\u3002"
    "\u5f53\u524d demo \u6682\u672a\u63a5\u5165\u771f\u5b9e\u4eba\u5de5\u5ba2\u670d"
    "\u7cfb\u7edf\uff0c\u6b63\u5f0f\u7cfb\u7edf\u4e2d\u4f1a\u5728\u8fd9\u91cc"
    "\u8fdb\u884c\u4eba\u5de5\u8f6c\u63a5\u3002"
)
ABUSIVE_OR_IRRELEVANT_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u6211\u4f1a\u5c3d\u91cf\u5e2e\u60a8\u89e3\u51b3\u95ee\u9898\uff0c"
    "\u9ebb\u70e6\u60a8\u5177\u4f53\u63cf\u8ff0\u4e00\u4e0b\u5546\u54c1\u3001"
    "\u5c3a\u7801\u3001\u8ba2\u5355\u6216\u552e\u540e\u95ee\u9898\u54e6\u3002"
)
BACKEND_REQUIRED_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8fd9\u4e2a\u9700\u8981\u67e5\u8be2\u60a8\u7684"
    "\u8ba2\u5355/\u7269\u6d41\u5b9e\u65f6\u4fe1\u606f\u3002\u76ee\u524d"
    "\u7cfb\u7edf\u6682\u65f6\u65e0\u6cd5\u76f4\u63a5\u8bfb\u53d6\u540e"
    "\u53f0\u72b6\u6001\uff0c\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d"
    "\u4e3a\u60a8\u6838\u5b9e\u5e76\u5904\u7406\u54e6\u3002"
)
SOFT_HARD_SOLE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8fd9\u6b3e\u978b\u5e95\u6574\u4f53\u662f\u8f6f\u786c\u9002\u4e2d\u7684\uff0c"
    "\u811a\u611f\u6bd4\u8f83\u8f7b\u4fbf\u8212\u9002\uff0c\u65e5\u5e38\u8d70\u8def\u4e0d\u5bb9\u6613\u7d2f\u811a\u54e6\u3002"
)

CATEGORY_RETURN = "\u9000\u8d27\u9000\u6b3e"
CATEGORY_EXCHANGE = "\u6362\u8d27"
CATEGORY_FREIGHT = "\u8fd0\u8d39"
CATEGORY_LOGISTICS = "\u7269\u6d41\u53d1\u8d27"
CATEGORY_SIZE = "\u5c3a\u7801\u95ee\u9898"
CATEGORY_OTHER = "\u5176\u4ed6"

POLICY_CATEGORY_KEYWORDS = {
    CATEGORY_RETURN: [
        "\u53ef\u4ee5\u9000\u8d27",
        "\u80fd\u9000\u8d27",
        "\u53ef\u4ee5\u9000\u5417",
        "\u80fd\u9000\u5417",
        "\u4e03\u5929\u65e0\u7406\u7531",
        "7\u5929\u65e0\u7406\u7531",
        "\u9000\u6b3e",
    ],
    CATEGORY_EXCHANGE: [
        "\u53ef\u4ee5\u6362",
        "\u80fd\u6362",
        "\u6362\u8d27",
        "\u6362\u7801",
    ],
    CATEGORY_FREIGHT: ["\u8fd0\u8d39", "\u8fd0\u8d39\u9669", "\u90ae\u8d39"],
    CATEGORY_LOGISTICS: [
        "\u53d1\u4ec0\u4e48\u5feb\u9012",
        "\u4ec0\u4e48\u65f6\u5019\u53d1\u8d27",
        "多久发货",
        "\u591a\u4e45\u5230",
        "\u4ec0\u4e48\u65f6\u5019\u80fd\u5230",
    ],
    CATEGORY_SIZE: [
        "\u5927\u4e00\u7801",
        "\u5c0f\u4e00\u7801",
        "\u504f\u5927",
        "\u504f\u5c0f",
        "\u5c3a\u7801",
        "\u7801\u6570",
    ],
}
POLICY_CATEGORY_PRIORITY = [
    CATEGORY_RETURN,
    CATEGORY_EXCHANGE,
    CATEGORY_FREIGHT,
    CATEGORY_LOGISTICS,
    CATEGORY_SIZE,
]

CONTEXT_DEPENDENT_ANSWER_TERMS = [
    "\u4fee\u978b",
    "\u80f6\u6c34",
    "\u8ba2\u5355\u8fc7\u671f",
    "\u8d28\u4fdd\u671f",
    "\u65e0\u6cd5\u5904\u7406",
    "\u5904\u7406\u4e0d\u4e86",
    "\u4e0d\u80fd\u5904\u7406",
    "\u4e09\u4e2a\u6708",
    "\u4e00\u4e2a\u6708",
    "\u8865\u507f\u91d1\u989d",
    "\u5c0f\u989d\u6253\u6b3e",
]
STANDARD_POLICY_ANSWER_TERMS = [
    "\u652f\u6301\u4e03\u5929\u65e0\u7406\u7531\u9000\u6362",
    "\u4e03\u5929\u65e0\u7406\u7531\u9000\u6362",
    "\u4e03\u5929\u65e0\u7406\u7531",
    "\u4e0d\u5f71\u54cd\u4e8c\u6b21\u9500\u552e",
    "\u53ef\u4ee5\u7533\u8bf7\u552e\u540e",
    "\u7533\u8bf7\u552e\u540e",
    "\u6b63\u5e38\u62cd\u5e73\u65f6\u5c3a\u7801",
    "\u5e73\u65f6\u5c3a\u7801",
    "\u811a\u5bbd\u811a\u80d6\u5efa\u8bae\u5927\u4e00\u7801",
    "\u811a\u5bbd",
    "\u811a\u80d6",
    "\u5efa\u8bae\u5927\u4e00\u7801",
    "\u53d1\u51fa\u540e\u4ee5\u7269\u6d41\u4fe1\u606f\u4e3a\u51c6",
    "\u4ee5\u7269\u6d41\u4fe1\u606f\u4e3a\u51c6",
]
BACKEND_API_REQUIRED_KEYWORDS = [
    "\u67e5\u7269\u6d41",
    "\u7269\u6d41\u4fe1\u606f",
    "\u8ba2\u5355\u7269\u6d41",
    "\u7269\u6d41\u5230\u54ea\u4e86",
    "\u5230\u54ea\u4e86",
    "\u5feb\u9012\u50ac\u50ac",
    "\u50ac\u5feb\u9012",
    "\u50ac\u4e00\u4e0b",
    "\u5e2e\u6211\u50ac",
    "\u50ac\u53d1\u8d27",
    "\u53d1\u8d27\u4e86\u5417",
    "\u53d1\u4e86\u6ca1",
    "\u8ba2\u5355\u53d1\u4e86\u5417",
    "\u4ec0\u4e48\u65f6\u5019\u53d1\u8d27",
    "\u4ec0\u4e48\u65f6\u5019\u5230",
    "\u591a\u4e45\u5230",
    "\u4eca\u5929\u80fd\u5230\u5417",
    "\u8ba2\u5355\u72b6\u6001",
    "订单现在什么状态",
    "\u552e\u540e\u8fdb\u5ea6",
    "\u9000\u6b3e\u8fdb\u5ea6",
    "\u8865\u507f\u5230\u8d26",
    "\u8fd4\u6b3e\u5230\u8d26",
]
LIVE_LOGISTICS_STATUS_PATTERNS = [
    r"(?:我的|我买的|我下单的).{0,10}(?:还没送到|还没收到|还没到|还没发货|什么时候到)",
    r"(?:怎么|为什么|为何)?还没(?:送到|收到|到)",
    r"(?:物流|快递).{0,6}(?:一直不动|不动了|没更新|没有更新)",
    r"(?:物流)?显示(?:已)?签收.{0,10}(?:没收到|未收到)",
    r"(?:已)?签收.{0,8}(?:但是|但)?(?:我)?(?:没收到|未收到)",
]
UNSAFE_LIVE_LOGISTICS_ANSWER_MARKERS = [
    "[TRACKING_ID]",
    "显示已签收",
    "正在运输",
    "当前位于",
    "物流信息如下",
    "快递单号",
    "距离下一站",
]
PRODUCT_ATTRIBUTE_KEYWORDS = [
    "\u978b\u5e95",
    "\u8f6f\u5e95",
    "\u786c\u5e95",
    "\u8f6f\u786c",
    "\u900f\u6c14",
    "\u95f7\u811a",
    "\u9632\u6ed1",
    "\u6253\u6ed1",
    "\u6750\u8d28",
    "\u9762\u6599",
    "\u52a0\u7ed2",
    "\u4fdd\u6696",
    "\u81ed\u811a",
    "\u91cd\u4e0d\u91cd",
    "\u8f7b\u4fbf",
    "\u8212\u670d\u5417",
    "\u7d2f\u811a\u5417",
]
BUSINESS_QUERY_KEYWORDS = [
    "\u5c3a\u7801",
    "\u7801\u6570",
    "\u978b\u7801",
    "\u504f\u5927",
    "\u504f\u5c0f",
    "\u5927\u4e00\u7801",
    "\u5c0f\u4e00\u7801",
    "\u6b63\u7801",
    "\u6807\u51c6\u7801",
    "\u811a\u5bbd",
    "\u811a\u80d6",
    "\u811a\u80cc\u9ad8",
    "\u9000",
    "\u9000\u8d27",
    "\u9000\u6b3e",
    "\u6362",
    "\u6362\u8d27",
    "\u6362\u7801",
    "\u4e0d\u5408\u9002",
    "\u53ef\u4ee5\u6362",
    "\u80fd\u6362",
    "\u53ef\u4ee5\u9000",
    "\u80fd\u9000",
    "\u978b\u5e95",
    "\u8f6f\u5e95",
    "\u786c\u5e95",
    "\u9632\u6ed1",
    "\u6253\u6ed1",
    "\u900f\u6c14",
    "\u95f7\u811a",
    "\u6750\u8d28",
    "\u9762\u6599",
    "\u52a0\u7ed2",
    "\u4fdd\u6696",
    "\u8d28\u91cf",
    "\u5f00\u80f6",
    "\u7834\u635f",
    "\u53d1\u9519",
    "\u6b3e\u5f0f",
    "\u989c\u8272",
    "\u53d1\u8d27",
    "\u5feb\u9012",
    "\u591a\u4e45\u5230",
    "\u4ec0\u4e48\u65f6\u5019\u5230",
    "\u4ec0\u4e48\u5feb\u9012",
    "\u8fd0\u8d39",
    "\u8fd0\u8d39\u9669",
]
IRRELEVANT_ATTRIBUTE_ANSWER_TERMS = [
    "\u5efa\u8bae\u73b0\u5728\u62cd\u4e0b",
    "\u5c3d\u5feb\u4e0b\u5355",
    "\u770b\u597d\u4e86\u5c3d\u5feb\u62cd",
    "\u8fd0\u8d39\u9669",
    "\u9000\u6362",
    "\u9000\u8d27",
    "\u6362\u8d27",
    "\u552e\u540e",
    "\u7269\u6d41",
    "\u53d1\u8d27",
    "\u8865\u507f",
    "\u8ba2\u5355",
]
IDENTITY_QUERY_KEYWORDS = [
    "\u4f60\u662f\u8c01",
    "\u4f60\u662fai\u5417",
    "\u4f60\u662fAI\u5417",
    "\u4f60\u662f\u0061\u0069\u5417",
    "\u4f60\u662f\u0041\u0049\u5417",
    "\u4f60\u662f\u673a\u5668\u4eba\u5417",
    "\u4f60\u662f\u4eba\u5de5\u5417",
    "\u4f60\u662f\u771f\u4eba\u5417",
    "\u4f60\u662f\u4ec0\u4e48",
    "\u4f60\u80fd\u5e72\u561b",
    "\u4f60\u4f1a\u4ec0\u4e48",
    "\u4f60\u662f\u4e0d\u662f\u5ba2\u670d",
    "\u4f60\u662f\u771f\u5ba2\u670d\u5417",
]
HUMAN_HANDOVER_KEYWORDS = [
    "\u4eba\u5de5",
    "\u8f6c\u4eba\u5de5",
    "\u627e\u5ba2\u670d",
    "\u4eba\u5de5\u5ba2\u670d",
    "\u627e\u4eba\u5de5",
    "\u771f\u4eba",
    "\u771f\u4eba\u5ba2\u670d",
    "\u6211\u8981\u4eba\u5de5",
    "\u63a5\u4eba\u5de5",
    "\u6709\u4eba\u5417",
    "\u6d3b\u4eba",
    "\u4eba\u5462",
    "\u5ba2\u670d\u5728\u5417",
]
ABUSIVE_OR_IRRELEVANT_KEYWORDS = [
    "\u4f60\u5988",
    "\u50bb\u903c",
    "\u50bb\u5c4c",
    "\u7b28",
    "\u7b28\u554a",
    "\u8822",
    "\u50bb",
    "\u7b28\u86cb",
    "\u667a\u969c",
    "\u8111\u6b8b",
    "\u5783\u573e\u5ba2\u670d",
    "\u5e9f\u7269",
    "\u65e0\u8bed",
    "\u6c14\u6b7b",
    "\u592a\u5dee\u4e86",
    "\u8111\u6b8b",
    "\u6eda",
    "\u5783\u573e",
    "\u65e0\u8bed",
    "\u670d\u4e86",
    "\u4ec0\u4e48\u9b3c",
    "\u4ec0\u4e48\u73a9\u610f",
    "\u5565\u73a9\u610f",
    "\u6709\u75c5",
    "\u70c2",
    "sb",
    "shit",
    "fuck",
]
SLIP_QUERY_KEYWORDS = [
    "\u4e0b\u96e8",
    "\u96e8\u5929",
    "\u6709\u6c34",
    "\u6e7f\u6ed1",
    "\u6253\u6ed1",
    "\u6ed1\u4e0d\u6ed1",
    "\u9632\u6ed1",
    "\u978b\u5e95\u6ed1",
]
SLIP_CONTENT_KEYWORDS = [
    "\u9632\u6ed1",
    "\u6253\u6ed1",
    "\u6e7f\u6ed1",
    "\u978b\u5e95\u7eb9\u8def",
    "\u6709\u6c34",
    "\u6709\u6cb9",
    "\u6469\u64e6\u529b",
    "\u7eb9\u8def",
]
RAIN_SHOE_SIZE_KEYWORDS = ["\u96e8\u978b", "\u504f\u5c0f", "\u504f\u5927", "\u7801\u6570"]
SLIP_QUERY_EXPANSION = " \u9632\u6ed1 \u6253\u6ed1 \u6e7f\u6ed1 \u978b\u5e95\u7eb9\u8def \u6709\u6c34 \u6709\u6cb9"
POST_SHIP_QUERY_KEYWORDS = [
    "\u5df2\u53d1\u51fa",
    "\u53d1\u8d27\u4e86",
    "\u5df2\u7ecf\u53d1\u8d27",
    "\u5546\u54c1\u53d1\u51fa",
    "\u5feb\u9012\u53d1\u4e86",
    "\u8fd8\u80fd\u9000\u6b3e",
    "\u62e6\u622a",
    "\u62d2\u6536",
]
POST_SHIP_CONTENT_KEYWORDS = [
    "\u62e6\u622a",
    "\u62d2\u6536",
    "\u9000\u56de",
    "\u9000\u56de\u540e\u9000\u6b3e",
    "\u7269\u6d41\u9000\u56de",
    "\u5546\u54c1\u5df2\u53d1\u51fa",
    "\u5546\u54c1\u53d1\u51fa\u540e",
]
FREIGHT_ONLY_KEYWORDS = [
    "\u8fd0\u8d39\u9669",
    "\u9000\u8d27\u8fd0\u8d39",
    "\u8fd0\u8d39\u9700\u8981\u81ea\u7406",
    "\u90ae\u8d39",
    "\u6536\u8fd0\u8d39",
]
FOOT_DISCOMFORT_QUERY_KEYWORDS = [
    "\u811a\u4e0d\u8212\u670d",
    "\u811a\u75db",
    "\u78e8\u811a",
    "\u8131\u76ae",
    "\u811a\u6c14",
    "\u771f\u83cc",
    "\u76ae\u80a4",
    "\u4e0d\u9002",
]
FOOT_SAFE_SNIPPET_KEYWORDS = [
    "\u5c31\u533b",
    "\u533b\u751f",
    "\u76ae\u80a4\u79d1",
    "\u65e0\u6cd5\u5224\u65ad",
    "\u65e0\u6cd5\u51c6\u786e\u5224\u65ad",
    "\u4eba\u5de5\u6838\u5b9e",
    "\u552e\u540e\u89c4\u5219",
    "\u811a\u90e8\u4e0d\u9002",
]
FOOT_TRANSITION_QA_KEYWORDS = ["\u62cd\u7167", "\u53d1\u6211", "\u6838\u5b9e", "\u4f18\u5148\u5904\u7406"]
GREETING_STRIP_PHRASES = [
    "\u4eb2\u4eb2\uff0c\u4eb2\u7231\u7684\u5728\u7684\u5462",
    "\u4eb2\u7231\u7684\u5728\u7684\u5462",
    "\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u52a9\u60a8\u7684\u5417",
    "\u4eb2\u7231\u7684\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u60a8",
    "\u5728\u7684\u5462",
    "\u60a8\u597d\uff0c\u5728\u7684",
    "\u4eb2\uff0c\u60a8\u597d",
    "\u4eb2\u4eb2\uff0c\u60a8\u597d",
    "\u60a8\u597d\u4eb2",
    "\u6b22\u8fce\u5149\u4e34",
    "\u5ba2\u670d\u6b63\u5728\u4e3a\u60a8\u670d\u52a1",
    "\u8bf7\u95ee\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u60a8",
    "\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u60a8",
    "\u4eb2\u7231\u7684\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u60a8\u7684\u5417",
]
GREETING_ONLY_PHRASES = [
    "\u4eb2\u7231\u7684\u5728\u7684\u5462",
    "\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u52a9\u60a8\u7684\u5417",
    "\u4eb2\u7231\u7684\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u60a8",
    "\u5728\u7684\u5462",
    "\u60a8\u597d\uff0c\u5728\u7684",
    "\u4eb2\uff0c\u60a8\u597d",
    "\u4eb2\u4eb2\uff0c\u60a8\u597d",
    "\u60a8\u597d\u4eb2",
    "\u6b22\u8fce\u5149\u4e34",
    "\u5ba2\u670d\u6b63\u5728\u4e3a\u60a8\u670d\u52a1",
    "\u8bf7\u95ee\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u60a8",
    "\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u60a8",
    "\u4eb2\u7231\u7684\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u60a8\u7684\u5417",
    "\u4eb2\u4eb2\u4eb2\u7231\u7684\u5728\u7684\u5462\u6709\u4ec0\u4e48\u53ef\u4ee5\u5e2e\u52a9\u60a8\u7684\u5417",
]
GENERIC_RETURN_KEYWORDS = [
    "\u4e03\u5929\u65e0\u7406\u7531",
    "\u652f\u6301\u9000\u6362",
    "\u9000\u6362\u8d27",
    "\u53ef\u4ee5\u9000\u8d27",
    "\u80fd\u9000\u8d27",
    "\u4e0d\u5f71\u54cd\u4e8c\u6b21\u9500\u552e",
]
WRONG_ITEM_QUERY_KEYWORDS = ["\u53d1\u9519\u6b3e\u5f0f", "\u9519\u53d1", "\u53d1\u9519\u8d27"]
GLUE_QUALITY_QUERY_KEYWORDS = ["\u5f00\u80f6", "\u65ad\u5e95", "\u5f00\u7ebf"]
RISKY_ANSWER_PATTERNS = [
    re.compile(r"\u8865\u507f\s*\d+\s*\u5143"),
    re.compile(r"\d+\s*\u5143\s*\u8865\u507f"),
    re.compile(r"\u8fd4\u73b0"),
    re.compile(r"\u6253\u6b3e"),
    re.compile(r"\u5df2\u7ecf\u6253\u6b3e"),
    re.compile(r"\u5df2\u7ecf\u9000\u6b3e"),
    re.compile(r"\u5df2\u7ecf\u8fd4\u6b3e"),
    re.compile(r"\u5df2\u7ecf\u50ac\u4fc3"),
    re.compile(r"\u5df2\u7ecf\u62e6\u622a"),
    re.compile(r"\u5df2\u53cd\u9988\u62e6\u622a"),
    re.compile(r"\u4e94\u661f\u597d\u8bc4"),
    re.compile(r"\u597d\u8bc4\u622a\u56fe"),
    re.compile(r"\u8bc4\u4ef7\u8fd4\u73b0"),
    re.compile(r"\u4fee\u6539\u9000\u8d27\u539f\u56e0"),
    re.compile(r"\u7533\u8bf7\u8865\u507f\s*\d+"),
    re.compile(r"\u7ed9\u60a8\u8865\u507f\s*\d+"),
    re.compile(r"\u8865\u507f\s*\d+"),
    re.compile(r"\u5df2\u7ecf\u5907\u6ce8"),
    re.compile(r"\u6211\u4eec\u5907\u6ce8\u4e86"),
    re.compile(r"\u5df2\u5907\u6ce8"),
    re.compile(r"\u5e2e\u60a8\u5907\u6ce8"),
    re.compile(r"\u5df2\u7ecf\u5b89\u6392"),
    re.compile(r"\u5df2\u5b89\u6392"),
    re.compile(r"\u5b89\u6392\u8865\u53d1"),
    re.compile(r"\u5df2\u7ecf\u8865\u53d1"),
    re.compile(r"\u5df2\u8865\u53d1"),
    re.compile(r"\u7ed9\u60a8\u8865\u53d1"),
    re.compile(r"\u7ed9\u60a8\u91cd\u53d1"),
    re.compile(r"\u5df2\u7ecf\u91cd\u53d1"),
    re.compile(r"\u653e\u65b0"),
    re.compile(r"\u53d1\u65b0\u7684"),
    re.compile(r"\u6362\u65b0"),
    re.compile(r"\u5df2\u6362\u65b0"),
    re.compile(r"\u5df2\u5904\u7406"),
    re.compile(r"\u5df2\u7ecf\u5904\u7406"),
]
SAFE_HUMAN_VERIFICATION_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8fd9\u4e2a\u95ee\u9898\u9700\u8981\u4eba\u5de5\u5ba2\u670d\u7ed3\u5408\u8ba2\u5355\u3001"
    "\u5546\u54c1\u60c5\u51b5\u548c\u5e73\u53f0\u552e\u540e\u89c4\u5219\u8fdb\u4e00\u6b65\u6838\u5b9e\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u4e3a\u60a8\u5904\u7406\u54e6\u3002"
)
WRONG_ITEM_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u53d1\u9519\u6b3e\u5f0f\u5efa\u8bae\u8054\u7cfb\u4eba\u5de5\u5ba2\u670d\uff0c"
    "\u63d0\u4f9b\u8ba2\u5355\u4fe1\u606f\u548c\u5546\u54c1\u7167\u7247\uff0c"
    "\u7531\u5ba2\u670d\u6839\u636e\u8ba2\u5355\u548c\u5e73\u53f0\u552e\u540e\u89c4\u5219\u6838\u5b9e\u5904\u7406\uff1b"
    "\u5f53\u524d demo \u4e0d\u80fd\u627f\u8bfa\u5177\u4f53\u8865\u507f\u91d1\u989d\u3002"
)
GLUE_QUALITY_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u5f00\u80f6\u662f\u5426\u5c5e\u4e8e\u8d28\u91cf\u95ee\u9898\u9700\u8981\u7ed3\u5408\u7167\u7247\u3001"
    "\u4f7f\u7528\u60c5\u51b5\u548c\u5e73\u53f0\u552e\u540e\u89c4\u5219\u5224\u65ad\uff1b"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u6838\u5b9e\uff0c"
    "\u5f53\u524d demo \u4e0d\u627f\u8bfa\u5177\u4f53\u8865\u507f\u91d1\u989d\u3002"
)
FOOT_DISCOMFORT_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u975e\u5e38\u62b1\u6b49\u7ed9\u60a8\u5e26\u6765\u4e0d\u597d\u7684\u7a7f\u7740\u4f53\u9a8c\u3002"
    "\u811a\u90e8\u4e0d\u9002\u53ef\u80fd\u7531\u591a\u79cd\u539f\u56e0\u5f15\u8d77\uff0c\u4ec5\u51ed\u63cf\u8ff0\u65e0\u6cd5\u51c6\u786e\u5224\u65ad\u539f\u56e0\u3002"
    "\u4e3a\u4e86\u60a8\u7684\u5065\u5eb7\uff0c\u5efa\u8bae\u60a8\u4f18\u5148\u54a8\u8be2\u6b63\u89c4\u533b\u9662\u76ae\u80a4\u79d1\u6216\u4e13\u4e1a\u533b\u751f\u3002"
    "\u5982\u60a8\u6000\u7591\u4e0e\u5546\u54c1\u8d28\u91cf\u6709\u5173\uff0c\u53ef\u4ee5\u8054\u7cfb\u4eba\u5de5\u5ba2\u670d\uff0c"
    "\u7ed3\u5408\u8ba2\u5355\u4fe1\u606f\u3001\u5546\u54c1\u60c5\u51b5\u548c\u5e73\u53f0\u552e\u540e\u89c4\u5219\u8fdb\u4e00\u6b65\u6838\u5b9e\u5904\u7406\u3002"
)
POST_SHIP_REFUND_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u5546\u54c1\u53d1\u51fa\u540e\u901a\u5e38\u65e0\u6cd5\u76f4\u63a5\u53d6\u6d88\u53d1\u8d27\u6216\u7acb\u5373\u9000\u6b3e\uff0c"
    "\u53ef\u5148\u6839\u636e\u7269\u6d41\u72b6\u6001\u5c1d\u8bd5\u62e6\u622a\uff1b"
    "\u82e5\u62e6\u622a\u6210\u529f\uff0c\u5305\u88f9\u9000\u56de\u540e\u53ef\u6309\u5e73\u53f0\u89c4\u5219\u5904\u7406\u9000\u6b3e\uff1b"
    "\u82e5\u62e6\u622a\u5931\u8d25\uff0c\u5305\u88f9\u53ef\u80fd\u4f1a\u7ee7\u7eed\u6d3e\u9001\uff0c"
    "\u60a8\u53ef\u5728\u6536\u5230\u6d3e\u9001\u65f6\u9009\u62e9\u62d2\u6536\uff0c"
    "\u5f85\u7269\u6d41\u9000\u56de\u540e\u518d\u7533\u8bf7\u6216\u5904\u7406\u9000\u6b3e\u3002"
    "\u5177\u4f53\u62e6\u622a\u7ed3\u679c\u3001\u9000\u6b3e\u8fdb\u5ea6\u548c\u8ba2\u5355\u72b6\u6001\u9700\u8981\u4eba\u5de5\u5ba2\u670d\u7ed3\u5408\u540e\u53f0\u4fe1\u606f\u6838\u5b9e\u54e6\u3002"
)
DEMO_CANNOT_OPERATE_BACKEND_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u5f53\u524d demo \u65e0\u6cd5\u76f4\u63a5\u64cd\u4f5c\u8ba2\u5355\u6216\u7269\u6d41\u540e\u53f0\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u7ed3\u5408\u540e\u53f0\u4fe1\u606f\u4e3a\u60a8\u5904\u7406\u54e6\u3002"
)
COMPENSATION_REQUEST_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8865\u507f\u91d1\u989d\u9700\u8981\u4eba\u5de5\u5ba2\u670d\u7ed3\u5408\u8ba2\u5355\u60c5\u51b5\u3001"
    "\u5546\u54c1\u95ee\u9898\u548c\u5e73\u53f0\u552e\u540e\u89c4\u5219\u6838\u5b9e\u5904\u7406\uff0c"
    "\u5f53\u524d demo \u4e0d\u80fd\u76f4\u63a5\u627f\u8bfa\u5177\u4f53\u8865\u507f\u91d1\u989d\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u8fdb\u4e00\u6b65\u786e\u8ba4\u54e6\u3002"
)
COMPENSATION_REQUEST_KEYWORDS = [
    "\u8865\u507f",
    "\u8d54\u507f",
    "\u8d54\u6211",
    "\u8865\u6211",
    "\u8865\u507f\u51e0\u5757",
    "\u8865\u507f\u4e24\u5757",
    "\u80fd\u7ed9\u6211\u8865\u507f",
    "\u80fd\u8d54\u5417",
    "\u80fd\u8865\u5417",
    "\u80fd\u7ed9\u6211\u8865\u507f\u5417",
]
COMPENSATION_REQUEST_PATTERNS = [
    re.compile(r"\u8865\u507f\s*\d+\s*\u5143"),
    re.compile(r"\u8d54\s*\d+\s*\u5143"),
    re.compile(r"\u9000\u6211\s*\d+\s*\u5143"),
    re.compile(r"(\u8865\u507f|\u8d54\u507f|\u8d54|\u8865).{0,8}([一二两三四五六七八九十百千万\d]+)\s*\u5757"),
    re.compile(r"\u80fd\u7ed9\u6211\u8865\u507f"),
    re.compile(r"\u90a3\u80fd\u7ed9\u6211\u8865\u507f"),
]
COMPENSATION_REQUEST_SIGNAL_TERMS = [
    "\u51e0\u5757",
    "\u4e24\u5757",
    "\u5757",
    "\u5143",
    "\u591a\u5c11",
    "\u7ed9\u6211",
    "\u8d54\u6211",
    "\u8865\u6211",
    "\u80fd\u8d54",
    "\u80fd\u8865",
    "\u80fd\u8865\u507f",
    "\u80fd\u8d54\u507f",
    "\u5417",
]
REVIEW_INCENTIVE_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u5f53\u524d demo \u4e0d\u80fd\u627f\u8bfa\u4efb\u4f55\u8bc4\u4ef7\u8fd4\u73b0\u3001"
    "\u597d\u8bc4\u5956\u52b1\u6216\u622a\u56fe\u8fd4\u73b0\u3002"
    "\u5982\u60a8\u6709\u552e\u540e\u3001\u9000\u6b3e\u6216\u8865\u507f\u95ee\u9898\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u6839\u636e\u8ba2\u5355\u60c5\u51b5\u548c\u5e73\u53f0\u89c4\u5219\u6838\u5b9e\u5904\u7406\u54e6\u3002"
)
PRICE_DIFFERENCE_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u4ef7\u5dee\u6216\u4ef7\u4fdd\u76f8\u5173\u95ee\u9898\u9700\u8981\u7ed3\u5408\u60a8\u7684\u8ba2\u5355\u65f6\u95f4\u3001"
    "\u5546\u54c1\u6d3b\u52a8\u548c\u5e73\u53f0\u89c4\u5219\u7531\u4eba\u5de5\u5ba2\u670d\u6838\u5b9e\u5904\u7406\u3002"
    "\u5f53\u524d demo \u4e0d\u80fd\u76f4\u63a5\u627f\u8bfa\u9000\u4ef7\u5dee\u6216\u8865\u4ef7\u5dee\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u8fdb\u4e00\u6b65\u786e\u8ba4\u54e6\u3002"
)
SHIPPING_FEE_REIMBURSEMENT_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8fd0\u8d39\u627f\u62c5\u6216\u62a5\u9500\u9700\u8981\u7ed3\u5408\u8ba2\u5355\u662f\u5426\u6709\u8fd0\u8d39\u9669\u3001"
    "\u9000\u6362\u8d27\u539f\u56e0\u3001\u5546\u54c1\u72b6\u6001\u548c\u5e73\u53f0\u89c4\u5219\u6838\u5b9e\u3002"
    "\u5f53\u524d demo \u4e0d\u80fd\u76f4\u63a5\u627f\u8bfa\u62a5\u9500\u8fd0\u8d39\u6216\u8865\u8d34\u8fd0\u8d39\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u8fdb\u4e00\u6b65\u786e\u8ba4\u54e6\u3002"
)
REFUND_STATUS_OR_AMOUNT_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8fd9\u4e2a\u9700\u8981\u67e5\u8be2\u60a8\u7684\u8ba2\u5355\u3001\u9000\u6b3e\u6216\u652f\u4ed8\u540e\u53f0\u72b6\u6001\u3002"
    "\u76ee\u524d\u7cfb\u7edf\u6682\u65f6\u65e0\u6cd5\u76f4\u63a5\u8bfb\u53d6\u540e\u53f0\u4fe1\u606f\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u4e3a\u60a8\u6838\u5b9e\u9000\u6b3e\u91d1\u989d\u3001\u8fdb\u5ea6\u6216\u5230\u8d26\u60c5\u51b5\u54e6\u3002"
)
PAYMENT_TRANSFER_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u6253\u6b3e\u3001\u8fd4\u6b3e\u6216\u8f6c\u8d26\u76f8\u5173\u95ee\u9898\u9700\u8981\u4eba\u5de5\u5ba2\u670d\u7ed3\u5408\u8ba2\u5355\u548c\u540e\u53f0\u8bb0\u5f55\u6838\u5b9e\u3002"
    "\u5f53\u524d demo \u4e0d\u80fd\u786e\u8ba4\u6216\u627f\u8bfa\u4efb\u4f55\u6253\u6b3e\u3001\u8fd4\u6b3e\u3001\u5230\u8d26\u6216\u7ebf\u4e0b\u8f6c\u8d26\u5904\u7406\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u8fdb\u4e00\u6b65\u786e\u8ba4\u54e6\u3002"
)
DISCOUNT_OR_PRICE_CHANGE_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u5546\u54c1\u4ef7\u683c\u548c\u4f18\u60e0\u6d3b\u52a8\u4ee5\u9875\u9762\u663e\u793a\u53ca\u5e73\u53f0\u6d3b\u52a8\u89c4\u5219\u4e3a\u51c6\u3002"
    "\u5f53\u524d demo \u4e0d\u80fd\u4fee\u6539\u8ba2\u5355\u4ef7\u683c\u6216\u627f\u8bfa\u989d\u5916\u4f18\u60e0\uff0c"
    "\u5982\u9700\u786e\u8ba4\u6d3b\u52a8\u6216\u4f18\u60e0\u5238\u89c4\u5219\uff0c\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u6838\u5b9e\u54e6\u3002"
)
INVOICE_REQUEST_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u5e97\u94fa\u652f\u6301\u7535\u5b50\u53d1\u7968\u76f8\u5173\u54a8\u8be2\u3002"
    "\u5f00\u7968\u4fe1\u606f\u3001\u53d1\u7968\u91d1\u989d\u548c\u5f00\u7968\u8fdb\u5ea6\u9700\u8981\u7ed3\u5408\u8ba2\u5355\u53ca\u5e73\u53f0\u5f00\u7968\u6d41\u7a0b\u7531\u4eba\u5de5\u5ba2\u670d\u6838\u5b9e\u5904\u7406\uff0c"
    "\u5f53\u524d demo \u4e0d\u80fd\u76f4\u63a5\u767b\u8bb0\u6216\u786e\u8ba4\u5f00\u7968\u72b6\u6001\u54e6\u3002"
)
LEGAL_COMPENSATION_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8d54\u4ed8\u6216\u6295\u8bc9\u76f8\u5173\u95ee\u9898\u9700\u8981\u7ed3\u5408\u8ba2\u5355\u3001"
    "\u5546\u54c1\u60c5\u51b5\u548c\u5e73\u53f0\u89c4\u5219\u7531\u4eba\u5de5\u5ba2\u670d\u6838\u5b9e\u5904\u7406\u3002"
    "\u5f53\u524d demo \u4e0d\u80fd\u76f4\u63a5\u627f\u8bfa\u5177\u4f53\u8d54\u4ed8\u6807\u51c6\u6216\u91d1\u989d\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u8fdb\u4e00\u6b65\u786e\u8ba4\u54e6\u3002"
)
REVIEW_INCENTIVE_KEYWORDS = [
    "\u597d\u8bc4\u8fd4\u73b0",
    "\u4e94\u661f\u597d\u8bc4",
    "\u4e94\u661f\u8bc4\u4ef7",
    "\u8bc4\u4ef7\u8fd4\u73b0",
    "\u6652\u56fe\u8fd4\u73b0",
    "\u622a\u56fe\u8fd4\u73b0",
    "\u597d\u8bc4\u622a\u56fe",
    "\u8bc4\u4ef7\u622a\u56fe",
    "\u597d\u8bc4\u5956\u52b1",
    "\u8bc4\u4ef7\u5956\u52b1",
    "\u7ed9\u597d\u8bc4\u8fd4\u94b1\u5417",
    "\u8fd4\u73b0\u5417",
    "\u597d\u8bc4\u80fd\u4e0d\u80fd\u8fd4\u73b0",
    "\u4e94\u661f\u597d\u8bc4\u622a\u56fe\u53d1\u4f60\u80fd\u8fd4\u73b0\u5417",
    "\u597d\u8bc4\u80fd\u8fd4\u73b0",
    "\u80fd\u8fd4\u73b0\u5417",
]
PRICE_DIFFERENCE_KEYWORDS = [
    "\u9000\u4ef7\u5dee",
    "\u8865\u4ef7\u5dee",
    "\u4ef7\u4fdd",
    "\u4ef7\u683c\u4fdd\u62a4",
    "\u964d\u4ef7\u4e86",
    "\u4e70\u8d35\u4e86",
    "\u9000\u6211\u4ef7\u5dee",
    "\u80fd\u4e0d\u80fd\u9000\u4ef7\u5dee",
    "\u80fd\u4e0d\u80fd\u8865\u5dee",
    "\u4fdd\u4ef7",
]
SHIPPING_FEE_REIMBURSEMENT_KEYWORDS = [
    "\u62a5\u9500\u8fd0\u8d39",
    "\u8fd0\u8d39\u62a5\u9500",
    "\u90ae\u8d39\u62a5\u9500",
    "\u90ae\u8d39\u8c01\u51fa",
    "\u8fd0\u8d39\u8c01\u627f\u62c5",
    "\u8865\u8fd0\u8d39",
    "\u9000\u8fd0\u8d39",
    "\u8fd0\u8d39\u8865\u8d34",
    "\u6765\u56de\u8fd0\u8d39",
    "\u5bc4\u56de\u8fd0\u8d39",
    "\u90ae\u8d39\u8865\u8d34",
    "\u7ed9\u6211\u62a5\u9500",
    "\u80fd\u7ed9\u6211\u62a5\u9500",
]
REFUND_STATUS_OR_AMOUNT_KEYWORDS = [
    "\u9000\u591a\u5c11\u94b1",
    "\u9000\u6b3e\u591a\u5c11",
    "\u9000\u6b3e\u91d1\u989d",
    "\u4ec0\u4e48\u65f6\u5019\u5230\u8d26",
    "\u591a\u4e45\u5230\u8d26",
    "\u51e0\u5929\u5230\u8d26",
    "\u9000\u5230\u54ea\u91cc",
    "\u9000\u6211\u94b1",
    "\u94b1\u4ec0\u4e48\u65f6\u5019\u9000",
    "\u5230\u8d26\u4e86\u5417",
    "\u5df2\u9000\u6b3e\u4e86\u5417",
]
PAYMENT_TRANSFER_KEYWORDS = [
    "\u6253\u6b3e",
    "\u8fd4\u6b3e",
    "\u8f6c\u8d26",
    "\u8fd4\u94b1",
    "\u8fd4\u6211\u94b1",
    "\u6253\u5230\u54ea\u91cc",
    "\u8fd4\u5230\u54ea\u91cc",
    "\u5fae\u4fe1\u6536\u6b3e",
    "\u652f\u4ed8\u5b9d",
    "\u94f6\u884c\u5361",
    "\u6536\u6b3e\u7801",
    "\u5df2\u6253\u6b3e",
    "\u5df2\u8fd4\u6b3e",
    "\u7ebf\u4e0b\u8f6c\u8d26",
]
DISCOUNT_OR_PRICE_CHANGE_KEYWORDS = [
    "\u4fbf\u5b9c\u70b9",
    "\u80fd\u4f18\u60e0\u5417",
    "\u4f18\u60e0\u591a\u5c11",
    "\u6539\u4ef7",
    "\u6539\u4e2a\u4ef7",
    "\u5c11\u70b9\u94b1",
    "\u6253\u6298",
    "\u6298\u6263",
    "\u4f18\u60e0\u5238",
    "\u80fd\u4e0d\u80fd\u4fbf\u5b9c",
    "\u518d\u4fbf\u5b9c\u70b9",
    "\u80fd\u4fbf\u5b9c\u70b9",
]
INVOICE_REQUEST_KEYWORDS = [
    "\u53d1\u7968",
    "\u5f00\u7968",
    "\u7535\u5b50\u53d1\u7968",
    "\u53d1\u7968\u91d1\u989d",
    "\u62ac\u5934",
    "\u7a0e\u53f7",
]
LEGAL_COMPENSATION_KEYWORDS = [
    "\u7cbe\u795e\u635f\u5931\u8d39",
    "\u6295\u8bc9\u8d54\u507f",
    "\u5e73\u53f0\u8d54\u4ed8",
    "\u5546\u5bb6\u8d54\u4ed8",
    "\u5047\u4e00\u8d54\u5341",
    "\u4e09\u500d\u8d54\u507f",
    "\u5341\u500d\u8d54\u507f",
    "\u8d54\u94b1",
]
FINANCIAL_RISK_QUERY_TYPES = frozenset(
    {
        "review_incentive_request",
        "price_difference_request",
        "shipping_fee_reimbursement_request",
        "refund_status_or_amount_request",
        "payment_transfer_request",
        "discount_or_price_change_request",
        "invoice_request",
        "legal_compensation_request",
        "compensation_request",
    }
)
FOLLOWUP_QUERY_PHRASES = [
    "\u771f\u7684\u5417",
    "\u771f\u7684\u554a",
    "\u786e\u5b9a\u5417",
    "\u662f\u5417",
    "\u53ef\u4ee5\u5417",
    "\u884c\u5417",
    "\u80fd\u5417",
    "\u4e3a\u4ec0\u4e48",
    "\u4e3a\u5565",
    "\u90a3\u600e\u4e48\u529e",
    "\u600e\u4e48\u529e",
    "\u600e\u4e48\u5904\u7406",
    "\u7136\u540e\u5462",
    "\u90a3\u5462",
    "\u4e0b\u96e8\u5462",
    "\u6cb9\u5730\u5462",
    "\u6709\u6c34\u5462",
    "\u6e7f\u5730\u5462",
    "\u90a3\u80fd\u9000\u5417",
    "\u90a3\u80fd\u6362\u5417",
    "\u90a3\u80fd\u8d54\u5417",
    "\u90a3\u591a\u4e45\u5230\u8d26",
    "\u90a3\u591a\u4e45\u9000",
    "\u4f60\u80fd\u5904\u7406\u5417",
    "\u4f60\u5e2e\u6211\u5904\u7406",
    "\u90a3\u600e\u4e48\u5f04",
    "\u90a3\u4e25\u91cd\u5417",
    "\u4e25\u91cd\u5417",
    "\u90a3\u80fd\u8d54\u5417",
    "\u80fd\u8d54\u5417",
    "\u80fd\u8865\u507f\u5417",
    "\u90a3\u80fd\u8865\u507f\u5417",
    "\u90a3\u600e\u4e48\u9000",
    "\u90a3\u6211\u600e\u4e48\u529e",
    "\u90a3\u4f60\u5e2e\u6211\u5904\u7406",
    "\u90a3\u4f60\u5e2e\u6211\u5904\u7406\u5427",
    "\u771f\u4e0d\u53ef\u4ee5\u5417",
    "\u771f\u7684\u4e0d\u53ef\u4ee5\u5417",
    "\u771f\u7684\u4e0d\u884c\u5417",
    "\u4e0d\u53ef\u4ee5\u5417",
    "\u4e0d\u80fd\u5417",
    "\u4e0d\u884c\u5417",
    "\u771f\u4e0d\u884c\u5417",
    "\u4e3a\u4ec0\u4e48\u4e0d\u53ef\u4ee5",
    "\u4e3a\u5565\u4e0d\u884c",
    "\u90a3\u4e3a\u4ec0\u4e48",
    "\u786e\u5b9a\u4e0d\u80fd\u67e5\u5417",
    "\u6211\u8fd9\u4e2a\u9000\u56de\u53bb",
    "\u90a3\u6211\u9000\u56de\u53bb",
    "\u6211\u5bc4\u56de\u53bb",
    "\u90a3\u5bc4\u56de\u53bb",
    "\u9000\u56de\u53bb\u5462",
    "\u90a3\u600e\u4e48\u5f04",
    "\u4f60\u5e2e\u6211\u5907\u6ce8",
    "\u5e2e\u6211\u5907\u6ce8\u4e00\u4e0b",
    "\u4f60\u7ed9\u6211\u5b89\u6392\u5427",
    "\u90a3\u7ed9\u6211\u636239",
    "\u90a3\u8865\u53d139",
    "\u90a3\u53d1\u65b0\u7684",
]
FINANCIAL_SAFE_ANSWER_BY_TYPE = {
    "review_incentive_request": REVIEW_INCENTIVE_SAFE_ANSWER,
    "payment_transfer_request": PAYMENT_TRANSFER_SAFE_ANSWER,
    "refund_status_or_amount_request": REFUND_STATUS_OR_AMOUNT_SAFE_ANSWER,
    "legal_compensation_request": LEGAL_COMPENSATION_SAFE_ANSWER,
    "compensation_request": COMPENSATION_REQUEST_SAFE_ANSWER,
    "price_difference_request": PRICE_DIFFERENCE_SAFE_ANSWER,
    "shipping_fee_reimbursement_request": SHIPPING_FEE_REIMBURSEMENT_SAFE_ANSWER,
    "discount_or_price_change_request": DISCOUNT_OR_PRICE_CHANGE_SAFE_ANSWER,
    "invoice_request": INVOICE_REQUEST_SAFE_ANSWER,
}
FINANCIAL_ASSISTANT_ANSWER_SIGNALS: list[tuple[str, list[str]]] = [
    ("review_incentive_request", ["\u4e0d\u80fd\u627f\u8bfa\u4efb\u4f55\u8bc4\u4ef7\u8fd4\u73b0", "\u597d\u8bc4\u5956\u52b1", "\u622a\u56fe\u8fd4\u73b0"]),
    ("payment_transfer_request", ["\u6253\u6b3e\u3001\u8fd4\u6b3e\u6216\u8f6c\u8d26", "\u4e0d\u80fd\u786e\u8ba4\u6216\u627f\u8bfa\u4efb\u4f55\u6253\u6b3e"]),
    ("refund_status_or_amount_request", ["\u6838\u5b9e\u9000\u6b3e\u91d1\u989d\u3001\u8fdb\u5ea6\u6216\u5230\u8d26\u60c5\u51b5", "\u67e5\u8be2\u60a8\u7684\u8ba2\u5355\u3001\u9000\u6b3e\u6216\u652f\u4ed8\u540e\u53f0\u72b6\u6001"]),
    ("legal_compensation_request", ["\u8d54\u4ed8\u6216\u6295\u8bc9\u76f8\u5173\u95ee\u9898", "\u4e0d\u80fd\u76f4\u63a5\u627f\u8bfa\u5177\u4f53\u8d54\u4ed8\u6807\u51c6"]),
    ("compensation_request", ["\u8865\u507f\u91d1\u989d\u9700\u8981\u4eba\u5de5\u5ba2\u670d", "\u4e0d\u80fd\u76f4\u63a5\u627f\u8bfa\u5177\u4f53\u8865\u507f\u91d1\u989d"]),
    ("price_difference_request", ["\u4ef7\u5dee\u6216\u4ef7\u4fdd", "\u4e0d\u80fd\u76f4\u63a5\u627f\u8bfa\u9000\u4ef7\u5dee\u6216\u8865\u4ef7\u5dee"]),
    ("shipping_fee_reimbursement_request", ["\u8fd0\u8d39\u627f\u62c5\u6216\u62a5\u9500", "\u4e0d\u80fd\u76f4\u63a5\u627f\u8bfa\u62a5\u9500\u8fd0\u8d39\u6216\u8865\u8d34\u8fd0\u8d39"]),
    ("discount_or_price_change_request", ["\u4e0d\u80fd\u4fee\u6539\u8ba2\u5355\u4ef7\u683c\u6216\u627f\u8bfa\u989d\u5916\u4f18\u60e0", "\u5546\u54c1\u4ef7\u683c\u548c\u4f18\u60e0\u6d3b\u52a8"]),
    ("invoice_request", ["\u5f00\u7968\u4fe1\u606f\u3001\u53d1\u7968\u91d1\u989d\u548c\u5f00\u7968\u8fdb\u5ea6", "\u4e0d\u80fd\u76f4\u63a5\u767b\u8bb0\u6216\u786e\u8ba4\u5f00\u7968\u72b6\u6001"]),
]
AFTERSALES_OPERATION_QUERY_TYPE = "aftersales_operation_request"
AFTERSALES_OPERATION_SAFE_ANSWER = (
    "\u4eb2\u4eb2\uff0c\u8865\u53d1\u3001\u91cd\u53d1\u3001\u6362\u7801\u6216\u6362\u8d27\u9700\u8981\u4eba\u5de5\u5ba2\u670d\u7ed3\u5408\u60a8\u7684\u8ba2\u5355\u3001"
    "\u9000\u56de\u7269\u6d41\u3001\u5546\u54c1\u72b6\u6001\u3001\u5e93\u5b58\u60c5\u51b5\u548c\u5e73\u53f0\u552e\u540e\u89c4\u5219\u6838\u5b9e\u5904\u7406\u3002"
    "\u5f53\u524d demo \u4e0d\u80fd\u76f4\u63a5\u786e\u8ba4\u53ef\u4ee5\u8865\u53d1\u3001\u5907\u6ce8\u6362\u7801\u6216\u5b89\u6392\u6362\u65b0\uff0c"
    "\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u8fdb\u4e00\u6b65\u5904\u7406\u54e6\u3002"
)
AFTERSALES_RESHIP_KEYWORDS = [
    "\u8865\u53d1",
    "\u91cd\u53d1",
    "\u91cd\u65b0\u53d1",
    "\u518d\u53d1\u4e00\u53cc",
    "\u53d1\u65b0\u7684",
    "\u6362\u65b0\u7684",
    "\u6362\u65b0",
    "\u653e\u65b0",
    "\u8865\u4e00\u53cc",
    "\u91cd\u65b0\u5bc4",
    "\u518d\u5bc4\u4e00\u53cc",
]
AFTERSALES_SIZE_EXCHANGE_KEYWORDS = [
    "\u6362\u7801",
    "\u6362\u5c3a\u7801",
    "\u6362\u4e2a\u7801",
    "\u6362\u4e00\u53cc",
    "\u6362\u8d27\u6362\u7801",
    "\u6362\u5927\u4e00\u7801",
    "\u6362\u5c0f\u4e00\u7801",
]
AFTERSALES_RETURN_RESHIP_KEYWORDS = [
    "\u9000\u56de\u53bb",
    "\u6211\u9000\u56de\u53bb",
    "\u9000\u56de\u540e",
    "\u5bc4\u56de\u53bb",
    "\u5bc4\u56de\u540e",
    "\u9000\u56de\u53bb\u518d\u53d1",
    "\u9000\u56de\u53bb\u6362",
    "\u6536\u5230\u540e\u8865\u53d1",
    "\u6536\u5230\u540e\u6362",
    "\u9000\u56de\u53bb\u4e86\u80fd\u6362\u5417",
]
AFTERSALES_BACKEND_ACTION_KEYWORDS = [
    "\u5e2e\u6211\u5907\u6ce8",
    "\u5907\u6ce8\u4e00\u4e0b",
    "\u5907\u6ce8\u6362\u7801",
    "\u5907\u6ce8\u8865\u53d1",
    "\u5e2e\u6211\u5b89\u6392",
    "\u5b89\u6392\u8865\u53d1",
    "\u5b89\u6392\u6362\u8d27",
    "\u7ed9\u6211\u5904\u7406",
    "\u4f60\u5e2e\u6211\u5f04",
]
AFTERSALES_OPERATION_CONTEXT_KEYWORDS = (
    AFTERSALES_RESHIP_KEYWORDS
    + AFTERSALES_RETURN_RESHIP_KEYWORDS
    + AFTERSALES_BACKEND_ACTION_KEYWORDS
    + AFTERSALES_SIZE_EXCHANGE_KEYWORDS
    + ["\u6362\u8d27", "\u9000\u56de", "\u5bc4\u56de", "\u53d1\u65b0", "\u6362\u65b0"]
)
AFTERSALES_SIZE_CONSULTATION_KEYWORDS = [
    "\u5c3a\u7801\u6807\u51c6",
    "\u7801\u6807\u51c6",
    "\u978b\u7801",
    "\u9009\u7801",
    "\u9002\u5408\u591a\u957f",
    "\u811a\u957f",
    "\u811a\u5bbd",
    "\u811a\u80d6",
    "\u504f\u5927",
    "\u504f\u5c0f",
    "\u5efa\u8bae\u5927",
    "\u5efa\u8bae\u5c0f",
    "\u600e\u4e48\u9009\u7801",
    "\u62cd\u5927",
    "\u62cd\u5c0f",
]
AFTERSALES_ASSISTANT_ANSWER_SIGNALS = [
    "\u8865\u53d1\u3001\u91cd\u53d1\u3001\u6362\u7801\u6216\u6362\u8d27",
    "\u4e0d\u80fd\u76f4\u63a5\u786e\u8ba4\u53ef\u4ee5\u8865\u53d1",
    "\u5907\u6ce8\u6362\u7801\u6216\u5b89\u6392\u6362\u65b0",
    "\u9000\u56de\u7269\u6d41\u3001\u5546\u54c1\u72b6\u6001\u3001\u5e93\u5b58\u60c5\u51b5",
]
AFTERSALES_FOLLOWUP_PHRASES = [
    "\u6211\u8fd9\u4e2a\u9000\u56de\u53bb",
    "\u90a3\u6211\u9000\u56de\u53bb",
    "\u6211\u5bc4\u56de\u53bb",
    "\u90a3\u5bc4\u56de\u53bb",
    "\u9000\u56de\u53bb\u5462",
    "\u90a3\u600e\u4e48\u5f04",
    "\u4f60\u5e2e\u6211\u5907\u6ce8",
    "\u5e2e\u6211\u5907\u6ce8\u4e00\u4e0b",
    "\u4f60\u7ed9\u6211\u5b89\u6392\u5427",
    "\u90a3\u7ed9\u6211\u636239",
    "\u90a3\u8865\u53d139",
    "\u90a3\u53d1\u65b0\u7684",
]
BACKEND_ACTION_FOLLOWUP_KEYWORDS = [
    "\u4f60\u80fd\u5904\u7406\u5417",
    "\u4f60\u5e2e\u6211\u5904\u7406",
    "\u5e2e\u6211\u5904\u7406",
    "\u90a3\u4f60\u5e2e\u6211",
    "\u90a3\u4f60\u5e2e\u6211\u5904\u7406",
]
BACKEND_STATE_FOLLOWUP_PHRASES = [
    "那你帮我查一下",
    "你能看一下吗",
    "帮我查一下",
    "能查一下吗",
    "那你查一下",
    "帮我看一下",
]
COMPENSATION_FOLLOWUP_KEYWORDS = [
    "\u90a3\u80fd\u8d54\u5417",
    "\u80fd\u8d54\u5417",
    "\u80fd\u8865\u507f\u5417",
    "\u90a3\u80fd\u8865\u507f\u5417",
    "\u8d54\u5417",
    "\u8865\u507f\u5417",
]
SLIP_TOPIC_CONTEXT_KEYWORDS = SLIP_CONTENT_KEYWORDS + [
    "\u6ed1\u4e0d\u6ed1",
    "\u4e0b\u96e8",
    "\u96e8\u5929",
    "\u6709\u6c34",
    "\u6e7f\u6ed1",
    "\u6709\u6cb9",
]
SLIP_FOLLOWUP_TRIGGERS = [
    "\u771f\u7684\u5417",
    "\u771f\u7684\u554a",
    "\u786e\u5b9a\u5417",
    "\u662f\u5417",
    "\u4e0b\u96e8\u5462",
    "\u6cb9\u5730\u5462",
    "\u6709\u6c34\u5462",
    "\u6e7f\u5730\u5462",
]
POST_SHIP_TOPIC_CONTEXT_KEYWORDS = POST_SHIP_QUERY_KEYWORDS + POST_SHIP_CONTENT_KEYWORDS + [
    "\u53d1\u51fa\u540e",
    "\u9000\u6b3e",
]
POST_SHIP_FOLLOWUP_TRIGGERS = [
    "\u90a3\u600e\u4e48\u529e",
    "\u600e\u4e48\u5904\u7406",
    "\u90a3\u600e\u4e48\u9000",
    "\u90a3\u591a\u4e45\u5230\u8d26",
    "\u4f60\u80fd\u5904\u7406\u5417",
    "\u4f60\u5e2e\u6211\u5904\u7406",
    "\u90a3\u4f60\u5e2e\u6211\u5904\u7406",
    "\u90a3\u4f60\u5e2e\u6211\u5904\u7406\u5427",
]
QUALITY_TOPIC_CONTEXT_KEYWORDS = [
    "\u5f00\u80f6",
    "\u8d28\u91cf\u95ee\u9898",
    "\u53d1\u9519\u6b3e\u5f0f",
    "\u9519\u53d1",
    "\u8865\u507f",
    "\u8d54\u507f",
    "\u552e\u540e",
]
QUALITY_FOLLOWUP_TRIGGERS = [
    "\u90a3\u80fd\u8d54\u5417",
    "\u80fd\u8d54\u5417",
    "\u80fd\u8865\u507f\u5417",
    "\u90a3\u80fd\u8865\u507f\u5417",
    "\u600e\u4e48\u5904\u7406",
    "\u90a3\u600e\u4e48\u529e",
    "\u90a3\u80fd\u7ed9\u6211\u8865\u507f",
    "\u80fd\u7ed9\u6211\u8865\u507f",
]
FOOT_TOPIC_CONTEXT_KEYWORDS = FOOT_DISCOMFORT_QUERY_KEYWORDS + [
    "\u811a\u4e0d\u8212\u670d",
    "\u811a\u90e8\u4e0d\u9002",
    "\u76ae\u80a4\u79d1",
    "\u533b\u751f",
    "\u5c31\u533b",
]
FOOT_FOLLOWUP_TRIGGERS = [
    "\u90a3\u600e\u4e48\u529e",
    "\u4e25\u91cd\u5417",
    "\u90a3\u4e25\u91cd\u5417",
    "\u771f\u7684\u5417",
    "\u600e\u4e48\u5904\u7406",
]
SLIP_FOLLOWUP_CONTEXTUAL_QUERY = (
    "\u7528\u6237\u5728\u8ffd\u95ee\u4e0a\u4e00\u8f6e\u5173\u4e8e\u978b\u5e95\u9632\u6ed1\u7684\u95ee\u9898\uff1a"
    "\u8fd9\u6b3e\u978b\u662f\u5426\u771f\u7684\u9632\u6ed1\uff1f"
    "\u5728\u4e0b\u96e8\u3001\u6709\u6c34\u3001\u6709\u6cb9\u6216\u6e7f\u6ed1\u5730\u9762\u662f\u5426\u5bb9\u6613\u6253\u6ed1\uff1f"
)
POST_SHIP_FOLLOWUP_CONTEXTUAL_QUERY = (
    "\u7528\u6237\u5728\u8ffd\u95ee\u5546\u54c1\u5df2\u53d1\u51fa\u540e\u7684\u9000\u6b3e\u5904\u7406\uff1a"
    "\u662f\u5426\u9700\u8981\u7269\u6d41\u62e6\u622a\u3001\u62d2\u6536\u3001\u9000\u56de\u540e\u9000\u6b3e\uff0c"
    "\u4ee5\u53ca\u662f\u5426\u9700\u8981\u4eba\u5de5\u5ba2\u670d\u540e\u53f0\u6838\u5b9e\u3002"
)
QUALITY_FOLLOWUP_CONTEXTUAL_QUERY = (
    "\u7528\u6237\u5728\u8ffd\u95ee\u552e\u540e\u8d28\u91cf\u95ee\u9898\u662f\u5426\u53ef\u4ee5\u8865\u507f\u6216\u5904\u7406\uff0c"
    "\u9700\u8981\u7ed3\u5408\u8ba2\u5355\u3001\u7167\u7247\u548c\u5e73\u53f0\u552e\u540e\u89c4\u5219\u4eba\u5de5\u6838\u5b9e\uff0c"
    "\u4e0d\u80fd\u627f\u8bfa\u5177\u4f53\u8865\u507f\u91d1\u989d\u3002"
)
FOOT_FOLLOWUP_CONTEXTUAL_QUERY = (
    "\u7528\u6237\u5728\u8ffd\u95ee\u7a7f\u7740\u540e\u811a\u90e8\u4e0d\u9002\u95ee\u9898\uff0c"
    "\u9700\u8981\u907f\u514d\u533b\u5b66\u8bca\u65ad\uff0c\u5efa\u8bae\u5c31\u533b\uff0c"
    "\u5e76\u7531\u4eba\u5de5\u5ba2\u670d\u7ed3\u5408\u8ba2\u5355\u548c\u552e\u540e\u89c4\u5219\u6838\u5b9e\u3002"
)
UNCLEAR_SHORT_KEYWORDS = [
    "\u4f55\u610f\u5473",
    "\u5565\u610f\u601d",
    "\u4ec0\u4e48\u610f\u601d",
    "\u4ec0\u9ebc\u610f\u601d",
    "\uff1f",
    "\uff1f\uff1f\uff1f",
    "?",
    "???",
    "\u989d",
    "\u554a",
    "\u55ef",
    "\u54e6",
]
STANDALONE_VAGUE_CLARIFICATION = (
    "请问您具体想咨询哪方面呢？是尺码、发货、退换货，还是订单/物流状态？"
)
STANDALONE_VAGUE_ACTION_FORMS = frozenset(
    {
        "怎么办",
        "咋办",
        "咋整",
        "怎么弄",
        "怎么整",
        "怎么处理",
        "如何处理",
    }
)
STANDALONE_VAGUE_PREFIXES = frozenset(
    {
        "",
        "那",
        "这",
        "该",
        "我该",
        "现在",
        "那该",
        "这该",
    }
)
STANDALONE_VAGUE_EXACT_FORMS = frozenset(
    {
        "怎么了",
        "有问题",
        "帮帮我",
    }
)
AMBIGUOUS_DELIVERY_LOCATION_CLARIFICATION = (
    "请问您是下单时收货地址填错了，还是物流显示包裹送错了地点？"
)
STANDALONE_AMBIGUOUS_DELIVERY_LOCATION_FORMS = frozenset(
    {
        "发错位置了",
        "发错地方了",
        "寄错位置了",
        "寄错地方了",
        "送错位置了",
        "送错地方了",
    }
)
FOOT_LENGTH_MIN_CM = 10.0
FOOT_LENGTH_MAX_CM = 35.0
FOOT_LENGTH_CLARIFICATION = (
    "请提供脚长（厘米或毫米，例如24厘米）；如方便，也可补充平时鞋码、"
    "脚宽或高脚背情况。"
)
SIZE_FIT_UNKNOWN_ANSWER = (
    "目前没有当前商品可靠的尺码表或版型证据，无法确认这款是标准码、"
    "偏大还是偏小。请查看商品详情页的尺码表和版型说明；如需进一步参考，"
    "也可以补充商品名称或编号及脚长。"
)
# The reviewed knowledge snippets contain sizing cautions and fit scripts, but
# no approved foot-length-to-size table. Keep this empty until merchant-owned
# ranges are supplied; never derive an exact size from model knowledge.
MERCHANT_APPROVED_GENERIC_SIZE_CHART: tuple[tuple[float, float, str], ...] = ()
TRUSTED_SIZE_DATA_SOURCES = frozenset(
    {"merchant_product_data", "merchant_size_chart", "canonical_product_record"}
)
BUSINESS_TIMEZONE_NAME = "Asia/Shanghai"
BUSINESS_TIMEZONE = ZoneInfo(BUSINESS_TIMEZONE_NAME)
PROSPECTIVE_DISPATCH_CUTOFF = time(17, 0, 0)
PROSPECTIVE_SHIPPING_BEFORE_CUTOFF_ANSWER = (
    "亲，现在下单一般今天可以安排发出哦，具体以订单页显示的预计发货时间为准；"
    "预售款按商品详情页标注的时间发货。"
)
PROSPECTIVE_SHIPPING_AFTER_CUTOFF_ANSWER = (
    "亲，现在下单今天可能来不及发出了，一般会安排到下一批次哦。"
    "具体以订单页显示的预计发货时间为准；预售款按商品详情页标注的时间发货。"
)
PROSPECTIVE_SHIPPING_CUTOFF_ANSWER = (
    "亲，正常情况下17点前下单当天可以安排发出，17点后会安排到下一批次哦。"
    "具体以订单页显示为准；预售款按商品详情页标注的时间发货。"
)
PROSPECTIVE_PREORDER_ANSWER = (
    "预售商品不适用普通当日发货时段，请以商品详情页标注的预计发货时间"
    "和预售说明为准。"
)


@dataclass
class FollowupResolution:
    is_followup_query: bool
    original_query: str
    contextual_query: str
    previous_user_query: str
    previous_assistant_answer: str
    retrieval_query: str


class AnswerRoute(str, Enum):
    """Minimal product routing states for shipping, refund, and exchange."""

    DIRECT_ANSWER = "DIRECT_ANSWER"
    CLARIFY_THEN_ANSWER = "CLARIFY_THEN_ANSWER"
    POLICY_PLUS_HANDOFF = "POLICY_PLUS_HANDOFF"
    FULL_HANDOFF = "FULL_HANDOFF"


@dataclass(frozen=True)
class AnswerRouteDecision:
    route: AnswerRoute
    domain: str | None
    has_policy_facet: bool = False
    needs_realtime_status: bool = False
    needs_backend_action: bool = False
    policy_query: str | None = None
    clarification_question: str | None = None
    reason: str = "outside_p0_s1_scope"


class CustomerPrimaryGoal(str, Enum):
    PRODUCT_INFORMATION = "product_information"
    PURCHASE_SUITABILITY = "purchase_suitability"
    SIZE_RECOMMENDATION = "size_recommendation"
    GENERAL_POLICY_INFORMATION = "general_policy_information"
    RETURN_ELIGIBILITY = "return_eligibility"
    EXCHANGE_ELIGIBILITY = "exchange_eligibility"
    REFUND_REQUEST = "refund_request"
    CANCELLATION_REQUEST = "cancellation_request"
    AFTERSALES_PROBLEM_RESOLUTION = "aftersales_problem_resolution"
    ORDER_OR_REFUND_STATUS = "order_or_refund_status"
    BACKEND_OPERATION_REQUEST = "backend_operation_request"
    COMPLAINT_OR_DESCRIPTION_MISMATCH = "complaint_or_description_mismatch"
    AMBIGUOUS_HELP_REQUEST = "ambiguous_help_request"


class CustomerRequestedResolution(str, Enum):
    ANSWER_PRODUCT_QUESTION = "answer_product_question"
    RETURN = "return"
    EXCHANGE = "exchange"
    REFUND = "refund"
    CANCEL_ORDER = "cancel_order"
    REPLACE_OR_RESEND = "replace_or_resend"
    REPAIR_OR_AFTERSALES = "repair_or_aftersales"
    CORRECT_WRONG_ITEM = "correct_wrong_item"
    CHECK_STATUS = "check_status"
    ESCALATE_TO_HUMAN = "escalate_to_human_service"


class CustomerIssueType(str, Enum):
    SUBJECTIVE_DISSATISFACTION = "subjective_dissatisfaction"
    POOR_BREATHABILITY = "poor_breathability"
    INSUFFICIENT_WARMTH = "insufficient_warmth"
    SLIPPERY_EXPERIENCE = "slippery_experience"
    UNCOMFORTABLE_HARD_OR_HEAVY = "uncomfortable_hard_or_heavy"
    RUBBING_OR_PRESSURE = "rubbing_or_pressure"
    WRONG_SIZE_OR_FIT = "wrong_size_or_fit"
    WRONG_COLOR_STYLE_OR_ITEM = "wrong_color_style_or_item"
    MISSING_ITEM = "missing_item"
    DAMAGE = "damage"
    SOLE_SEPARATION = "sole_separation"
    DESCRIPTION_MISMATCH = "description_mismatch"
    SUSPECTED_QUALITY_PROBLEM = "suspected_quality_problem"
    SHIPPING_DELAY = "shipping_delay"
    LOGISTICS_DELIVERY_ERROR = "logistics_delivery_error"
    PREORDER_TIMING = "preorder_timing"
    CHANGE_OF_MIND = "change_of_mind"
    UNKNOWN_REASON = "unknown_reason"


class CustomerLifecycleStage(str, Enum):
    PRE_PURCHASE_HYPOTHETICAL = "pre_purchase_hypothetical"
    ORDERED_NOT_SHIPPED = "ordered_not_shipped"
    SHIPPED_IN_TRANSIT = "shipped_in_transit"
    RECEIVED = "received"
    RECEIVED_NOT_TRIED = "received_not_tried"
    INDOOR_TRY_ON_ONLY = "indoor_try_on_only"
    WORN_OUTDOORS = "worn_outdoors"
    USED_FOR_A_PERIOD = "used_for_a_period"
    RETURN_ALREADY_SUBMITTED = "return_already_submitted"
    REFUND_PROCESSING = "refund_processing"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class CustomerUsageState(str, Enum):
    UNKNOWN = "unknown"
    UNUSED = "unused"
    INDOOR_TRY_ON = "indoor_try_on"
    WORN_OUTDOORS = "worn_outdoors"
    USED_FOR_MULTIPLE_DAYS = "used_for_multiple_days"
    ALTERED = "altered"
    DAMAGED = "damaged"
    VISIBLY_DAMAGED_OR_ALTERED = "visibly_damaged_or_altered"
    UNCLEAR = "unclear"


class EvidenceStatus(str, Enum):
    UNKNOWN = "unknown"
    USER_REPORTED_POSITIVE = "user_reported_positive"
    USER_REPORTED_NEGATIVE = "user_reported_negative"
    TRUSTED_VERIFIED = "trusted_verified"


class EvidenceProvenance(str, Enum):
    UNKNOWN = "unknown"
    EXPLICIT_USER_STATEMENT = "explicit_user_statement"
    STRUCTURED_PRODUCT_DATA = "structured_product_data"
    CANONICAL_POLICY = "canonical_policy"
    TRUSTED_BACKEND_RECEIPT = "trusted_backend_receipt"
    DERIVED_INFERENCE = "derived_inference"


class EligibilityDecisionState(str, Enum):
    UNKNOWN = "unknown"
    GENERAL_POLICY_ONLY = "general_policy_only"
    MAY_SUBMIT_REQUEST = "may_submit_request"
    REQUIRES_POLICY_CHECK = "requires_policy_check"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    REQUIRES_BACKEND_STATUS = "requires_backend_status"
    APPROVED_WITH_RECEIPT = "approved_with_receipt"
    REJECTED_WITH_RECEIPT = "rejected_with_receipt"


class CommercialCostType(str, Enum):
    NONE = "none"
    RETURN_SHIPPING_FEE = "return_shipping_fee"
    EXCHANGE_SHIPPING_FEE = "exchange_shipping_fee"
    ORIGINAL_DELIVERY_FEE = "original_delivery_fee"
    REFUND_PROCESSING_FEE = "refund_processing_fee"
    REFUND_AMOUNT_DEDUCTION = "refund_amount_deduction"
    INSURANCE_REIMBURSEMENT = "insurance_reimbursement"
    COMPENSATION = "compensation"
    UNKNOWN_COST_TYPE = "unknown_cost_type"


@dataclass(frozen=True)
class ExplicitStateFact:
    value: str = "unknown"
    status: EvidenceStatus = EvidenceStatus.UNKNOWN
    provenance: EvidenceProvenance = EvidenceProvenance.UNKNOWN


@dataclass(frozen=True)
class ProductConditionEvidence:
    cleanliness: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    visible_wear: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    outsole_wear: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    upper_condition: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    packaging_complete: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    shoe_box_complete: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    tags_complete: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    accessories_complete: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    alteration_status: ExplicitStateFact = field(default_factory=ExplicitStateFact)


@dataclass(frozen=True)
class CustomerUsageEvidence:
    has_been_worn: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    has_been_tried_on: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    indoor_use: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    outdoor_use: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    usage_duration: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    usage_occurrence: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    usage_extent: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    statement_confidence: ExplicitStateFact = field(default_factory=ExplicitStateFact)
    evidence_provenance: EvidenceProvenance = EvidenceProvenance.UNKNOWN


class CustomerRequestRoute(str, Enum):
    PRODUCT_ONLY = "PRODUCT_ONLY"
    POLICY_ONLY = "POLICY_ONLY"
    PRODUCT_PLUS_POLICY = "PRODUCT_PLUS_POLICY"
    POLICY_PLUS_CLARIFICATION = "POLICY_PLUS_CLARIFICATION"
    POLICY_PLUS_HANDOFF = "POLICY_PLUS_HANDOFF"
    BACKEND_STATUS = "BACKEND_STATUS"
    BACKEND_OPERATION = "BACKEND_OPERATION"
    FULL_HANDOFF = "FULL_HANDOFF"


@dataclass(frozen=True)
class CustomerRequestFrame:
    original_text: str
    normalized_text: str
    primary_goal: CustomerPrimaryGoal
    requested_resolution: tuple[CustomerRequestedResolution, ...]
    product_facets: tuple[str, ...]
    issue_type: CustomerIssueType
    lifecycle_stage: CustomerLifecycleStage
    usage_state: CustomerUsageState
    lifecycle_provenance: EvidenceProvenance
    usage_provenance: EvidenceProvenance
    product_condition: ProductConditionEvidence
    eligibility_state: EligibilityDecisionState
    cost_type: CommercialCostType
    policy_questions: tuple[str, ...]
    backend_requirements: tuple[str, ...]
    clarification_slots: tuple[str, ...]
    supporting_product_context: tuple[str, ...]
    route: CustomerRequestRoute
    usage_evidence: CustomerUsageEvidence = field(default_factory=CustomerUsageEvidence)
    inherited_service_context: bool = False


@dataclass(frozen=True)
class CustomerResolutionRule:
    resolution: CustomerRequestedResolution
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class CustomerIssueRule:
    issue_type: CustomerIssueType
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen=True)
class FootLengthParse:
    status: str
    normalized_cm: float | None = None
    values_cm: tuple[float, ...] = ()
    unit_inferred: bool = False
    uncertain: bool = False
    is_range: bool = False
    correction_hint: str | None = None


@dataclass(frozen=True)
class SizeConsultationDecision:
    matched: bool
    query_type: str = "normal"
    answer: str | None = None
    foot_length: FootLengthParse | None = None
    usual_shoe_size: float | None = None
    foot_width: str | None = None
    high_instep: bool | None = None
    awaiting_foot_length: bool = False
    secondary_policy_query: str | None = None


@dataclass(frozen=True)
class ClaimValidationResult:
    answer: str
    blocked_claims: tuple[str, ...] = ()
    rewritten: bool = False


@dataclass
class FinancialRiskInheritance:
    query_type: str
    safe_answer: str
    inherited_from_previous_query: str


@dataclass
class AftersalesOperationInheritance:
    safe_answer: str
    inherited_from_previous_query: str


@dataclass
class BackendRequiredInheritance:
    query_type: str
    safe_answer: str
    current_topic: str


@dataclass
class ConversationState:
    current_topic: str = "none"
    query_type: str = "normal"
    risk_type: str = "none"
    requires_backend_api: bool = False
    last_safe_answer_type: str = "none"
    last_user_query: str = ""
    last_assistant_answer: str = ""
    last_retrieval_query: str = ""
    last_contextual_query: str = ""
    last_successful_contextual_query: str = ""
    state_confidence: float = 0.0
    state_turn_count: int = 0
    updated_at_turn: int = 0
    should_reset: bool = False
    size_foot_length_cm: float | None = None
    size_foot_length_values_cm: tuple[float, ...] = ()
    size_measurement_uncertain: bool = False
    size_usual_shoe_size: float | None = None
    size_foot_width: str = "unknown"
    size_high_instep: bool | None = None
    size_product_context: str = ""
    size_product_fit: str = ""
    size_product_fit_source: str = ""
    size_product_size_chart: tuple[tuple[float, float, str], ...] = ()
    size_product_size_chart_source: str = ""
    size_awaiting_foot_length: bool = False
    service_primary_goal: str = "none"
    service_requested_resolutions: tuple[str, ...] = ()
    service_issue_type: str = CustomerIssueType.UNKNOWN_REASON.value
    service_lifecycle_stage: str = CustomerLifecycleStage.UNKNOWN.value
    service_usage_state: str = CustomerUsageState.UNKNOWN.value
    service_lifecycle_provenance: str = EvidenceProvenance.UNKNOWN.value
    service_usage_provenance: str = EvidenceProvenance.UNKNOWN.value
    service_usage_evidence: dict[str, object] = field(default_factory=dict)
    service_product_condition: dict[str, dict[str, str]] = field(default_factory=dict)
    service_eligibility_state: str = EligibilityDecisionState.UNKNOWN.value
    service_cost_type: str = CommercialCostType.NONE.value
    service_clarification_count: int = 0
    service_pending_clarification: tuple[str, ...] = ()
    service_supporting_context: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class GenerationConfig:
    """Optional request parameters for an individual answer-generation call.

    Callers that omit this object retain the legacy DeepSeek request payload.
    Evaluation code can pass an explicit, immutable configuration without
    mutating process-wide environment state.
    """

    temperature: float = 0.2
    top_p: float | None = None
    max_tokens: int | None = None
    stream: bool = False


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    client: object | None

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def mode(self) -> str:
        return "DeepSeek API" if self.has_api_key and self.client is not None else "mock"


def _request_patterns(*expressions: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(expression, re.IGNORECASE) for expression in expressions)


CUSTOMER_RESOLUTION_RULES = (
    CustomerResolutionRule(
        CustomerRequestedResolution.RETURN,
        _request_patterns(
            r"退货",
            r"(?:能不能|能否|能|可以|可不可以|是否|还能|想|要|申请|怎么|如何|只能).{0,5}退(?:吗|呢|掉|回去|了|$)",
            r"(?:想|要)退(?:了|$)",
        ),
    ),
    CustomerResolutionRule(
        CustomerRequestedResolution.EXCHANGE,
        _request_patterns(
            r"换货|换尺码|换码",
            r"(?:能不能|能否|能|可以|可不可以|是否|还能|想|要|申请|怎么|如何).{0,6}换(?:吗|呢|货|大|小|成|到|别的|颜色|款|\d{2}|$)",
            r"(?:换|改成)\d{2}码|换大(?:一)?码|换小(?:一)?码|想换\d{2}|改码",
        ),
    ),
    CustomerResolutionRule(
        CustomerRequestedResolution.REFUND,
        _request_patterns(r"退款|退钱|返款"),
    ),
    CustomerResolutionRule(
        CustomerRequestedResolution.CANCEL_ORDER,
        _request_patterns(r"取消(?:订单|这单|下单)?|撤销订单"),
    ),
    CustomerResolutionRule(
        CustomerRequestedResolution.REPLACE_OR_RESEND,
        _request_patterns(r"补发|重发|重新发|换新|再发一双"),
    ),
    CustomerResolutionRule(
        CustomerRequestedResolution.ESCALATE_TO_HUMAN,
        _request_patterns(r"转人工|人工客服|找客服"),
    ),
)


CUSTOMER_ISSUE_RULES = (
    CustomerIssueRule(
        CustomerIssueType.DESCRIPTION_MISMATCH,
        _request_patterns(
            r"(?:页面|商品|详情|介绍|写|说|标注).{0,10}(?:实际|但是|但|怎么).{0,12}",
            r"图片.{0,8}(?:收到|实物).{0,6}(?:不一样|不一致|有差别)",
        ),
    ),
    CustomerIssueRule(
        CustomerIssueType.WRONG_COLOR_STYLE_OR_ITEM,
        _request_patterns(
            r"(?:发错|寄错|送错)(?:颜色|尺码|码|款式|款|货|商品)",
            r"收到的?不是我(?:买|拍|下单)的?(?:款|商品|货)?",
            r"左右脚.{0,5}(?:尺码|码数).{0,3}(?:不一样|不同)",
        ),
    ),
    CustomerIssueRule(CustomerIssueType.MISSING_ITEM, _request_patterns(r"少发|漏发|缺(?:了|少).{0,4}(?:一双|一件|商品)")),
    CustomerIssueRule(CustomerIssueType.SOLE_SEPARATION, _request_patterns(r"开胶|脱胶|鞋底分离")),
    CustomerIssueRule(CustomerIssueType.DAMAGE, _request_patterns(r"鞋底断|刚收到就破|破损|破了|断裂|裂开")),
    CustomerIssueRule(CustomerIssueType.POOR_BREATHABILITY, _request_patterns(r"不透气|很闷|太闷|闷脚|捂脚")),
    CustomerIssueRule(CustomerIssueType.INSUFFICIENT_WARMTH, _request_patterns(r"不够保暖|不保暖|太冷|冻脚")),
    CustomerIssueRule(CustomerIssueType.SLIPPERY_EXPERIENCE, _request_patterns(r"走路打滑|穿着会滑|实际.{0,3}滑|容易滑")),
    CustomerIssueRule(CustomerIssueType.RUBBING_OR_PRESSURE, _request_patterns(r"磨脚|压得难受|压脚|挤脚|顶脚|勒脚")),
    CustomerIssueRule(CustomerIssueType.WRONG_SIZE_OR_FIT, _request_patterns(r"鞋.{0,2}(?:小了|大了)|大了一码|小了一码|\d{2}码不合适|尺码不合适|穿着挤|宽脚.{0,4}挤")),
    CustomerIssueRule(CustomerIssueType.UNCOMFORTABLE_HARD_OR_HEAVY, _request_patterns(r"鞋底太硬|穿着太重|太重了|不舒服|不舒适|太硬了")),
    CustomerIssueRule(CustomerIssueType.SHIPPING_DELAY, _request_patterns(r"迟迟不发货|一直没发货|发货太慢|物流太慢|快递太慢")),
    CustomerIssueRule(CustomerIssueType.LOGISTICS_DELIVERY_ERROR, _request_patterns(r"物流显示.{0,6}(?:送错|投错).{0,4}(?:地方|位置|地点)|包裹.{0,4}(?:送错|投错)")),
    CustomerIssueRule(CustomerIssueType.PREORDER_TIMING, _request_patterns(r"预售.{0,8}(?:什么时候|多久|发货|到货)")),
    CustomerIssueRule(CustomerIssueType.CHANGE_OF_MIND, _request_patterns(r"不想要了|后悔了|改变主意")),
    CustomerIssueRule(CustomerIssueType.SUBJECTIVE_DISSATISFACTION, _request_patterns(r"颜色不好看|不喜欢|不满意|不好看")),
    CustomerIssueRule(CustomerIssueType.SUSPECTED_QUALITY_PROBLEM, _request_patterns(r"穿.{0,3}(?:天|次).{0,3}就坏|很大异味|质量问题|刚收到就坏|坏了")),
)


_STATUS_REQUEST_PATTERN = re.compile(
    r"(?:退款|退货|换货|售后|订单).{0,10}(?:什么时候|多久|进度|处理到哪|到账|完成|状态)|"
    r"(?:什么时候|多久|进度|处理到哪).{0,8}(?:退款|退货|换货|售后)"
)
_EXPLICIT_BACKEND_OPERATION_PATTERN = re.compile(
    r"(?:帮我|给我|替我|直接|马上).{0,10}(?:退货|换货|退款|取消|改码|改成|补发|重发|换新)|"
    r"(?:订单|这单).{0,6}(?:能不能|能|可以)?(?:帮我)?(?:改码|改成|取消)|"
    r"还没发货.{0,10}(?:改码|取消)"
)
_SHIPPING_FEE_POLICY_PATTERN = re.compile(
    r"(?:退货|换货|售后)?.{0,8}(?:运费|邮费).{0,10}(?:谁出|谁付|承担|怎么算|自己付|报销|退不退)|"
    r"(?:退款).{0,6}(?:手续费|费用|扣费|少了|少退|全额)|"
    r"(?:免费退货|运费险|保险赔付|补偿|赔偿)"
)
_SERVICE_FOLLOWUP_PATTERN = re.compile(
    r"没脏|干净|弄脏|包装|鞋盒|吊牌|配件|鞋底.{0,4}磨损|"
    r"鞋面.{0,4}(?:完好|破损)|没有明显破损|改动|已经提交申请|还没发货|已经发货|运输中|"
    r"订单页.{0,6}(?:售后入口|申请售后)"
)

_PRODUCT_CONDITION_FIELDS = (
    "cleanliness",
    "visible_wear",
    "outsole_wear",
    "upper_condition",
    "packaging_complete",
    "shoe_box_complete",
    "tags_complete",
    "accessories_complete",
    "alteration_status",
)

_USAGE_EVIDENCE_FIELDS = (
    "has_been_worn",
    "has_been_tried_on",
    "indoor_use",
    "outdoor_use",
    "usage_duration",
    "usage_occurrence",
    "usage_extent",
    "statement_confidence",
)

_USAGE_ACTION_WORN_PATTERNS = _request_patterns(
    r"穿出去|穿出门|穿着|穿过|穿了|穿去|(?:每天都|一直)在穿|"
    r"在(?:家里|家|室内|屋里|房间里)穿|上班穿|走过路|用过"
)
_USAGE_ACTION_TRY_PATTERNS = _request_patterns(r"试穿|试了|试过|试一下|试了试|套了|上脚")
_USAGE_INDOOR_PATTERNS = _request_patterns(r"家里|在家|室内|屋里|房间里")
_USAGE_OUTDOOR_PATTERNS = _request_patterns(
    r"穿出去|穿出门|出门(?:后|时)?穿|外面.{0,5}(?:穿|走|试)|"
    r"室外.{0,5}(?:穿|走|试)|户外.{0,5}(?:穿|走|试)|"
    r"穿着?下楼|下楼(?:了|过)|下楼.{0,5}穿|上班.{0,5}穿|穿着?上了?.{0,4}班|"
    r"通勤|上街|逛街|穿去(?:过)?外面|走过路"
)
_USAGE_OUTDOOR_NEGATIVE_PATTERNS = _request_patterns(
    r"没穿出去|没有穿出去|未穿出去|没出门|没出过门|没有出过门|"
    r"没到外面(?:穿|走)|没有到外面(?:穿|走)|没在外面(?:穿|走)"
)
_USAGE_INDOOR_NEGATIVE_PATTERNS = _request_patterns(r"没在家穿|没有在家穿|不是只在家穿|不只在家穿")
_USAGE_INDOOR_LIMIT_PATTERNS = _request_patterns(
    r"(?:只|就|就是|仅仅)(?:在)?(?:家里|家|室内|屋里|房间里)"
)
_USAGE_UNUSED_PATTERNS = _request_patterns(
    r"(?:还)?没穿(?:过)?$|完全没穿|完全没试过|从来没穿|没上过脚|收到后一直没穿|"
    r"一直没穿|未穿过|全新未用"
)
_USAGE_BRIEF_PATTERNS = _request_patterns(
    r"试了?(?:一)?下|试了试|穿了一下|穿了一会儿|穿过一次|穿了一次|套了一下|"
    r"上脚一下|试了一脚|穿了穿"
)
_USAGE_EXTENDED_PATTERNS = _request_patterns(
    r"穿了?(?:半天|一天|[二两三四五六七八九十\d]+天|好几天|几天|一周|"
    r"[二两三四五六七八九十\d]+周|[一二两三四五六七八九十\d]+个月)|"
    r"连续穿|每天都在穿|一直在穿|上班穿了一天|穿着上了几天班|"
    r"穿出去一天|穿出门一天"
)
_USAGE_ONCE_PATTERNS = _request_patterns(r"一次|一脚")
_USAGE_UNCERTAIN_PATTERNS = _request_patterns(r"好像|可能|也许|记不清|记不得|不确定|忘了")


def _reported_fact(value: str, *, positive: bool) -> ExplicitStateFact:
    return ExplicitStateFact(
        value=value,
        status=(
            EvidenceStatus.USER_REPORTED_POSITIVE
            if positive
            else EvidenceStatus.USER_REPORTED_NEGATIVE
        ),
        provenance=EvidenceProvenance.EXPLICIT_USER_STATEMENT,
    )


def _coerce_state_fact(value: object) -> ExplicitStateFact:
    if isinstance(value, ExplicitStateFact):
        return value
    if not isinstance(value, dict):
        return ExplicitStateFact()
    try:
        status = EvidenceStatus(str(value.get("status", EvidenceStatus.UNKNOWN.value)))
    except ValueError:
        status = EvidenceStatus.UNKNOWN
    try:
        provenance = EvidenceProvenance(
            str(value.get("provenance", EvidenceProvenance.UNKNOWN.value))
        )
    except ValueError:
        provenance = EvidenceProvenance.UNKNOWN
    return ExplicitStateFact(
        value=str(value.get("value", "unknown")),
        status=status,
        provenance=provenance,
    )


def _condition_from_state(state: ConversationState) -> ProductConditionEvidence:
    stored = state.service_product_condition or {}
    return ProductConditionEvidence(
        **{
            field_name: _coerce_state_fact(stored.get(field_name))
            for field_name in _PRODUCT_CONDITION_FIELDS
        }
    )


def _explicit_condition_updates(normalized: str) -> dict[str, ExplicitStateFact]:
    updates: dict[str, ExplicitStateFact] = {}
    if re.search(r"没脏|没有弄脏|未弄脏|很干净|是干净的", normalized):
        updates["cleanliness"] = _reported_fact("clean", positive=True)
    elif re.search(r"弄脏|脏了|有污渍", normalized):
        updates["cleanliness"] = _reported_fact("dirty", positive=False)

    if re.search(r"没有(?:明显)?(?:穿着)?痕迹|无(?:明显)?磨损", normalized):
        updates["visible_wear"] = _reported_fact("no_visible_wear", positive=True)
    elif re.search(r"有(?:明显)?(?:穿着)?痕迹|明显磨损", normalized):
        updates["visible_wear"] = _reported_fact("visible_wear", positive=False)

    if re.search(r"鞋底.{0,4}(?:没磨|无磨损|没有磨损)", normalized):
        updates["outsole_wear"] = _reported_fact("no_wear", positive=True)
    elif re.search(r"鞋底.{0,4}(?:有点|有|明显)?磨损", normalized):
        updates["outsole_wear"] = _reported_fact("visible_wear", positive=False)

    if re.search(r"鞋面.{0,4}(?:完好|没破|无破损)", normalized):
        updates["upper_condition"] = _reported_fact("intact", positive=True)
    elif re.search(r"鞋面.{0,4}(?:破损|破了|有损坏)", normalized):
        updates["upper_condition"] = _reported_fact("damaged", positive=False)

    if re.search(r"包装(?:都)?完整|包装齐全", normalized):
        updates["packaging_complete"] = _reported_fact("complete", positive=True)
    elif re.search(r"包装(?:不全|不完整|丢了|没有了)", normalized):
        updates["packaging_complete"] = _reported_fact("incomplete", positive=False)

    if re.search(r"鞋盒(?:还|都)?在|鞋盒(?:和|、)?吊牌都在|有鞋盒|鞋盒完整", normalized):
        updates["shoe_box_complete"] = _reported_fact("present", positive=True)
    elif re.search(r"鞋盒(?:丢了|没了|不在|破了|坏了)", normalized):
        updates["shoe_box_complete"] = _reported_fact("missing_or_damaged", positive=False)

    if re.search(r"吊牌(?:还|都)?在|鞋盒(?:和|、)?吊牌都在|有吊牌|吊牌完整", normalized):
        updates["tags_complete"] = _reported_fact("present", positive=True)
    elif re.search(r"吊牌(?:剪了|拆了|丢了|没了|不在)", normalized):
        updates["tags_complete"] = _reported_fact("removed", positive=False)

    if re.search(r"配件(?:都)?(?:在|齐全|完整)", normalized):
        updates["accessories_complete"] = _reported_fact("complete", positive=True)
    elif re.search(r"配件(?:不全|缺少|丢了)", normalized):
        updates["accessories_complete"] = _reported_fact("incomplete", positive=False)

    if re.search(r"没有改动|未改动|没改过", normalized):
        updates["alteration_status"] = _reported_fact("unaltered", positive=True)
    elif re.search(r"改过|改动过|自行修改", normalized):
        updates["alteration_status"] = _reported_fact("altered", positive=False)
    return updates


def _merge_product_condition(
    base: ProductConditionEvidence,
    updates: dict[str, ExplicitStateFact],
) -> ProductConditionEvidence:
    values = {name: getattr(base, name) for name in _PRODUCT_CONDITION_FIELDS}
    values.update(updates)
    return ProductConditionEvidence(**values)


def _usage_fact(
    value: str,
    *,
    positive: bool = True,
    provenance: EvidenceProvenance = EvidenceProvenance.EXPLICIT_USER_STATEMENT,
) -> ExplicitStateFact:
    return ExplicitStateFact(
        value=value,
        status=(
            EvidenceStatus.USER_REPORTED_POSITIVE
            if positive
            else EvidenceStatus.USER_REPORTED_NEGATIVE
        ),
        provenance=provenance,
    )


def _last_signal_position(
    normalized: str,
    patterns: tuple[re.Pattern[str], ...],
    *,
    reject_negated: bool = False,
) -> int:
    positions: list[int] = []
    for pattern in patterns:
        for match in pattern.finditer(normalized):
            if reject_negated:
                prefix = normalized[max(0, match.start() - 4) : match.start()]
                if (
                    not prefix.endswith("有没有")
                    and re.search(r"(?:没|未|无|不|没有|不是)(?:有|曾|到|在)?$", prefix)
                ):
                    continue
            positions.append(match.end())
    return max(positions, default=-1)


def _usage_evidence_has_signal(evidence: CustomerUsageEvidence) -> bool:
    return any(
        getattr(evidence, field_name).provenance is not EvidenceProvenance.UNKNOWN
        for field_name in _USAGE_EVIDENCE_FIELDS
    )


def _extract_usage_evidence(normalized: str) -> CustomerUsageEvidence:
    """Compose usage facts from independent action, location, extent and certainty signals."""
    values = {name: ExplicitStateFact() for name in _USAGE_EVIDENCE_FIELDS}
    uncertain = _last_signal_position(normalized, _USAGE_UNCERTAIN_PATTERNS) >= 0

    worn_positive = _last_signal_position(
        normalized,
        _USAGE_ACTION_WORN_PATTERNS,
        reject_negated=True,
    )
    unused_position = _last_signal_position(normalized, _USAGE_UNUSED_PATTERNS)
    if uncertain and worn_positive >= 0:
        values["has_been_worn"] = _usage_fact("unknown")
    elif worn_positive > unused_position:
        values["has_been_worn"] = _usage_fact("yes")
    elif unused_position >= 0:
        values["has_been_worn"] = _usage_fact("no", positive=False)

    tried_positive = _last_signal_position(
        normalized,
        _USAGE_ACTION_TRY_PATTERNS,
        reject_negated=True,
    )
    tried_negative = _last_signal_position(
        normalized,
        _request_patterns(r"没试过|没有试过|未试过|没上过脚|没有上过脚"),
    )
    if uncertain and tried_positive >= 0:
        values["has_been_tried_on"] = _usage_fact("unknown")
    elif tried_positive > tried_negative:
        values["has_been_tried_on"] = _usage_fact("yes")
    elif tried_negative >= 0:
        values["has_been_tried_on"] = _usage_fact("no", positive=False)

    indoor_positive = _last_signal_position(
        normalized,
        _USAGE_INDOOR_PATTERNS,
        reject_negated=True,
    )
    indoor_negative = _last_signal_position(normalized, _USAGE_INDOOR_NEGATIVE_PATTERNS)
    if indoor_positive > indoor_negative:
        values["indoor_use"] = _usage_fact("yes")
    elif indoor_negative >= 0:
        values["indoor_use"] = _usage_fact("no", positive=False)
    elif tried_positive >= 0 and not uncertain:
        values["indoor_use"] = _usage_fact(
            "yes",
            provenance=EvidenceProvenance.DERIVED_INFERENCE,
        )

    outdoor_positive = _last_signal_position(
        normalized,
        _USAGE_OUTDOOR_PATTERNS,
        reject_negated=True,
    )
    outdoor_negative = _last_signal_position(normalized, _USAGE_OUTDOOR_NEGATIVE_PATTERNS)
    indoor_limiter = _last_signal_position(normalized, _USAGE_INDOOR_LIMIT_PATTERNS)
    if uncertain and outdoor_positive >= 0:
        values["outdoor_use"] = _usage_fact("unknown")
    elif outdoor_positive > max(outdoor_negative, indoor_limiter):
        values["outdoor_use"] = _usage_fact("yes")
    elif max(outdoor_negative, indoor_limiter) >= 0:
        values["outdoor_use"] = _usage_fact("no", positive=False)

    extended_position = _last_signal_position(normalized, _USAGE_EXTENDED_PATTERNS)
    brief_position = _last_signal_position(normalized, _USAGE_BRIEF_PATTERNS)
    if uncertain and max(extended_position, brief_position) >= 0:
        values["usage_duration"] = _usage_fact("unknown")
        values["usage_extent"] = _usage_fact("unknown")
    elif extended_position >= 0:
        duration = "one_day" if re.search(r"半天|一天", normalized) else "multiple_days"
        values["usage_duration"] = _usage_fact(duration)
        values["usage_extent"] = _usage_fact("extended")
    elif brief_position >= 0:
        values["usage_duration"] = _usage_fact("brief")
        values["usage_extent"] = _usage_fact("brief")

    if _last_signal_position(normalized, _USAGE_ONCE_PATTERNS) >= 0:
        values["usage_occurrence"] = _usage_fact("once")

    has_semantic_signal = any(
        fact.provenance is not EvidenceProvenance.UNKNOWN
        for field_name, fact in values.items()
        if field_name != "statement_confidence"
    )
    if uncertain and has_semantic_signal:
        values["statement_confidence"] = _usage_fact("uncertain")
    elif has_semantic_signal:
        values["statement_confidence"] = _usage_fact("certain")

    provenance = (
        EvidenceProvenance.EXPLICIT_USER_STATEMENT
        if any(
            fact.provenance is EvidenceProvenance.EXPLICIT_USER_STATEMENT
            for fact in values.values()
        )
        else EvidenceProvenance.UNKNOWN
    )
    return CustomerUsageEvidence(**values, evidence_provenance=provenance)


def _usage_evidence_from_state(state: ConversationState) -> CustomerUsageEvidence:
    stored = state.service_usage_evidence or {}
    if stored:
        try:
            provenance = EvidenceProvenance(
                str(stored.get("evidence_provenance", EvidenceProvenance.UNKNOWN.value))
            )
        except ValueError:
            provenance = EvidenceProvenance.UNKNOWN
        return CustomerUsageEvidence(
            **{
                field_name: _coerce_state_fact(stored.get(field_name))
                for field_name in _USAGE_EVIDENCE_FIELDS
            },
            evidence_provenance=provenance,
        )

    try:
        legacy_usage = CustomerUsageState(state.service_usage_state)
    except ValueError:
        legacy_usage = CustomerUsageState.UNKNOWN
    if legacy_usage is CustomerUsageState.INDOOR_TRY_ON:
        return CustomerUsageEvidence(
            has_been_tried_on=_usage_fact("yes"),
            indoor_use=_usage_fact("yes"),
            evidence_provenance=EvidenceProvenance.EXPLICIT_USER_STATEMENT,
        )
    if legacy_usage is CustomerUsageState.WORN_OUTDOORS:
        return CustomerUsageEvidence(
            has_been_worn=_usage_fact("yes"),
            outdoor_use=_usage_fact("yes"),
            evidence_provenance=EvidenceProvenance.EXPLICIT_USER_STATEMENT,
        )
    if legacy_usage is CustomerUsageState.UNUSED:
        return CustomerUsageEvidence(
            has_been_worn=_usage_fact("no", positive=False),
            evidence_provenance=EvidenceProvenance.EXPLICIT_USER_STATEMENT,
        )
    return CustomerUsageEvidence()


def _merge_usage_evidence(
    base: CustomerUsageEvidence,
    updates: CustomerUsageEvidence,
) -> CustomerUsageEvidence:
    values = {name: getattr(base, name) for name in _USAGE_EVIDENCE_FIELDS}
    for field_name in _USAGE_EVIDENCE_FIELDS:
        update = getattr(updates, field_name)
        if update.provenance is not EvidenceProvenance.UNKNOWN:
            values[field_name] = update
    provenance = (
        updates.evidence_provenance
        if updates.evidence_provenance is not EvidenceProvenance.UNKNOWN
        else base.evidence_provenance
    )
    return CustomerUsageEvidence(**values, evidence_provenance=provenance)


def _compose_usage_state(
    evidence: CustomerUsageEvidence,
    normalized: str,
) -> CustomerUsageState:
    if evidence.statement_confidence.value == "uncertain":
        return CustomerUsageState.UNCLEAR
    if evidence.outdoor_use.value == "yes":
        return CustomerUsageState.WORN_OUTDOORS
    if evidence.usage_extent.value == "extended":
        return CustomerUsageState.USED_FOR_MULTIPLE_DAYS
    if evidence.has_been_worn.value == "no":
        return CustomerUsageState.UNUSED
    if evidence.indoor_use.value == "yes" or evidence.has_been_tried_on.value == "yes":
        return CustomerUsageState.INDOOR_TRY_ON
    if re.search(r"剪(?:了)?吊牌|改动|改过|自行修改", normalized):
        return CustomerUsageState.ALTERED
    if re.search(r"人为损坏|明显破损", normalized):
        return CustomerUsageState.DAMAGED
    return CustomerUsageState.UNKNOWN


def _compose_lifecycle_from_usage(
    detected: CustomerLifecycleStage,
    usage: CustomerUsageState,
) -> CustomerLifecycleStage:
    if usage is CustomerUsageState.WORN_OUTDOORS:
        return CustomerLifecycleStage.WORN_OUTDOORS
    if usage is CustomerUsageState.USED_FOR_MULTIPLE_DAYS:
        return CustomerLifecycleStage.USED_FOR_A_PERIOD
    if usage is CustomerUsageState.INDOOR_TRY_ON:
        return CustomerLifecycleStage.INDOOR_TRY_ON_ONLY
    return detected


def _detect_cost_type(normalized: str) -> CommercialCostType:
    if re.search(r"运费险|保险.{0,4}(?:赔|报销|公司)", normalized):
        return CommercialCostType.INSURANCE_REIMBURSEMENT
    if re.search(r"补偿|赔偿", normalized):
        return CommercialCostType.COMPENSATION
    if re.search(r"退款.{0,8}(?:少了|少退|金额不对|差了|扣了)\d*|退款金额.{0,5}(?:少|不对|扣)", normalized):
        return CommercialCostType.REFUND_AMOUNT_DEDUCTION
    if re.search(r"退款.{0,6}(?:手续费|处理费|服务费|扣费)", normalized):
        return CommercialCostType.REFUND_PROCESSING_FEE
    if re.search(r"(?:发货时|原(?:来)?|下单时|购买时).{0,6}(?:运费|邮费).{0,5}(?:退不退|退吗|返还|退回)", normalized):
        return CommercialCostType.ORIGINAL_DELIVERY_FEE
    if re.search(r"换货.{0,8}(?:来回)?(?:运费|邮费)|(?:运费|邮费).{0,5}换货", normalized):
        return CommercialCostType.EXCHANGE_SHIPPING_FEE
    if re.search(r"退货.{0,8}(?:运费|邮费)|(?:发错货|寄错货).{0,8}(?:退回|寄回).{0,4}(?:运费|邮费)|免费退货", normalized):
        return CommercialCostType.RETURN_SHIPPING_FEE
    if re.search(r"退款.{0,4}费用.{0,5}(?:谁出|谁付|承担|怎么算)", normalized):
        return CommercialCostType.UNKNOWN_COST_TYPE
    return CommercialCostType.NONE


def _first_issue(normalized: str) -> CustomerIssueType:
    for rule in CUSTOMER_ISSUE_RULES:
        if any(pattern.search(normalized) for pattern in rule.patterns):
            return rule.issue_type
    return CustomerIssueType.UNKNOWN_REASON


def _detect_lifecycle(normalized: str) -> CustomerLifecycleStage:
    if re.search(r"(?:退货|换货|退款|售后).{0,6}(?:已完成|完成了|已结束|已办结)", normalized):
        return CustomerLifecycleStage.COMPLETED
    if re.search(r"退款.{0,8}(?:到账|进度|处理中|什么时候|多久)", normalized):
        return CustomerLifecycleStage.REFUND_PROCESSING
    if re.search(r"退货.{0,5}(?:已经|已)?(?:申请|提交)", normalized) or "已经提交申请" in normalized:
        return CustomerLifecycleStage.RETURN_ALREADY_SUBMITTED
    if "还没发货" in normalized or "未发货" in normalized:
        return CustomerLifecycleStage.ORDERED_NOT_SHIPPED
    if "已经发货" in normalized or "已发货" in normalized or "运输中" in normalized:
        return CustomerLifecycleStage.SHIPPED_IN_TRANSIT
    if "刚收到" in normalized:
        return CustomerLifecycleStage.RECEIVED_NOT_TRIED
    if re.search(r"已经?收到|已签收|收到货", normalized):
        return CustomerLifecycleStage.RECEIVED
    if re.search(r"(?:如果|要是)?买了.{0,10}(?:能|可以|怎么).{0,5}(?:退|换)", normalized):
        return CustomerLifecycleStage.PRE_PURCHASE_HYPOTHETICAL
    if re.search(r"(?:试穿后|预售款).{0,8}(?:能|可以).{0,4}(?:退|换)", normalized):
        return CustomerLifecycleStage.PRE_PURCHASE_HYPOTHETICAL
    return CustomerLifecycleStage.UNKNOWN


def _detect_usage(normalized: str) -> CustomerUsageState:
    return _compose_usage_state(_extract_usage_evidence(normalized), normalized)


def _resolution_values_from_state(state: ConversationState) -> tuple[CustomerRequestedResolution, ...]:
    values: list[CustomerRequestedResolution] = []
    for value in state.service_requested_resolutions:
        try:
            values.append(CustomerRequestedResolution(value))
        except ValueError:
            continue
    return tuple(values)


def analyze_customer_request(
    question: str,
    *,
    product_facets: Iterable[str] = (),
    conversation_state: ConversationState | dict | None = None,
    has_selected_product: bool = False,
) -> CustomerRequestFrame:
    """Collect the complete request before any product or service fast path returns."""
    original = str(question or "").strip()
    normalized = re.sub(r"[\s，。！？!?、；;：:“”‘’\"'（）()【】\[\]]+", "", original).casefold()
    facets = tuple(dict.fromkeys(str(item) for item in product_facets if str(item)))
    state = coerce_conversation_state(conversation_state)
    has_service_context = state.service_primary_goal not in {"", "none"}
    empty_condition = ProductConditionEvidence()

    if is_standalone_ambiguous_delivery_location_query(original, has_service_context):
        return CustomerRequestFrame(
            original_text=original,
            normalized_text=normalized,
            primary_goal=CustomerPrimaryGoal.AMBIGUOUS_HELP_REQUEST,
            requested_resolution=(),
            product_facets=facets,
            issue_type=CustomerIssueType.LOGISTICS_DELIVERY_ERROR,
            lifecycle_stage=CustomerLifecycleStage.UNKNOWN,
            usage_state=CustomerUsageState.UNKNOWN,
            lifecycle_provenance=EvidenceProvenance.UNKNOWN,
            usage_provenance=EvidenceProvenance.UNKNOWN,
            product_condition=empty_condition,
            eligibility_state=EligibilityDecisionState.UNKNOWN,
            cost_type=CommercialCostType.NONE,
            policy_questions=(),
            backend_requirements=(),
            clarification_slots=("delivery_location_object",),
            supporting_product_context=(),
            route=CustomerRequestRoute.POLICY_PLUS_CLARIFICATION,
        )
    if normalized in {"退", "退款", "换", "换货", "发货"}:
        return CustomerRequestFrame(
            original_text=original,
            normalized_text=normalized,
            primary_goal=CustomerPrimaryGoal.AMBIGUOUS_HELP_REQUEST,
            requested_resolution=(),
            product_facets=facets,
            issue_type=CustomerIssueType.UNKNOWN_REASON,
            lifecycle_stage=CustomerLifecycleStage.UNKNOWN,
            usage_state=CustomerUsageState.UNKNOWN,
            lifecycle_provenance=EvidenceProvenance.UNKNOWN,
            usage_provenance=EvidenceProvenance.UNKNOWN,
            product_condition=empty_condition,
            eligibility_state=EligibilityDecisionState.UNKNOWN,
            cost_type=CommercialCostType.NONE,
            policy_questions=(),
            backend_requirements=(),
            clarification_slots=("short_service_object",),
            supporting_product_context=(),
            route=CustomerRequestRoute.POLICY_PLUS_CLARIFICATION,
        )

    resolutions: list[CustomerRequestedResolution] = []
    for rule in CUSTOMER_RESOLUTION_RULES:
        if any(pattern.search(normalized) for pattern in rule.patterns):
            resolutions.append(rule.resolution)

    issue = _first_issue(normalized)
    raw_lifecycle = _detect_lifecycle(normalized)
    current_usage_evidence = _extract_usage_evidence(normalized)
    current_usage_signal = _usage_evidence_has_signal(current_usage_evidence)
    detected_usage = _compose_usage_state(current_usage_evidence, normalized)
    detected_lifecycle = _compose_lifecycle_from_usage(raw_lifecycle, detected_usage)
    lifecycle = detected_lifecycle
    usage = detected_usage
    usage_evidence = current_usage_evidence
    lifecycle_provenance = (
        EvidenceProvenance.EXPLICIT_USER_STATEMENT
        if lifecycle is not CustomerLifecycleStage.UNKNOWN
        else EvidenceProvenance.UNKNOWN
    )
    usage_provenance = (
        EvidenceProvenance.EXPLICIT_USER_STATEMENT
        if usage is not CustomerUsageState.UNKNOWN
        else EvidenceProvenance.UNKNOWN
    )
    condition_updates = _explicit_condition_updates(normalized)
    cost_type = _detect_cost_type(normalized)
    inherited = False
    if (
        has_service_context
        and not resolutions
        and (_SERVICE_FOLLOWUP_PATTERN.search(normalized) or current_usage_signal)
    ):
        resolutions.extend(_resolution_values_from_state(state))
        inherited = bool(resolutions)
        if issue is CustomerIssueType.UNKNOWN_REASON:
            try:
                issue = CustomerIssueType(state.service_issue_type)
            except ValueError:
                pass
        if lifecycle is CustomerLifecycleStage.UNKNOWN:
            try:
                lifecycle = CustomerLifecycleStage(state.service_lifecycle_stage)
                lifecycle_provenance = EvidenceProvenance(
                    state.service_lifecycle_provenance
                )
            except ValueError:
                pass
        if not current_usage_signal and usage is CustomerUsageState.UNKNOWN:
            try:
                usage = CustomerUsageState(state.service_usage_state)
                usage_provenance = EvidenceProvenance(state.service_usage_provenance)
            except ValueError:
                pass

    if inherited:
        usage_evidence = _merge_usage_evidence(
            _usage_evidence_from_state(state),
            current_usage_evidence,
        )
        composed_usage = _compose_usage_state(usage_evidence, normalized)
        if composed_usage is not CustomerUsageState.UNKNOWN or current_usage_signal:
            usage = composed_usage
            usage_provenance = usage_evidence.evidence_provenance
        if current_usage_signal:
            lifecycle = _compose_lifecycle_from_usage(raw_lifecycle, usage)
            lifecycle_provenance = usage_evidence.evidence_provenance

    product_condition = _merge_product_condition(
        _condition_from_state(state) if inherited else empty_condition,
        condition_updates,
    )

    if _STATUS_REQUEST_PATTERN.search(normalized):
        resolutions.append(CustomerRequestedResolution.CHECK_STATUS)
    if inherited and lifecycle is CustomerLifecycleStage.RETURN_ALREADY_SUBMITTED:
        resolutions.append(CustomerRequestedResolution.CHECK_STATUS)
    if issue in {
        CustomerIssueType.SOLE_SEPARATION,
        CustomerIssueType.DAMAGE,
        CustomerIssueType.SUSPECTED_QUALITY_PROBLEM,
        CustomerIssueType.DESCRIPTION_MISMATCH,
    } and not resolutions:
        resolutions.append(CustomerRequestedResolution.REPAIR_OR_AFTERSALES)
    if issue is CustomerIssueType.WRONG_COLOR_STYLE_OR_ITEM and not resolutions:
        resolutions.append(CustomerRequestedResolution.CORRECT_WRONG_ITEM)
    if issue is CustomerIssueType.MISSING_ITEM and not resolutions:
        resolutions.append(CustomerRequestedResolution.REPAIR_OR_AFTERSALES)
    if facets and not resolutions:
        resolutions.append(CustomerRequestedResolution.ANSWER_PRODUCT_QUESTION)

    unique_resolutions = tuple(dict.fromkeys(resolutions))
    commercial_resolutions = tuple(
        item
        for item in unique_resolutions
        if item is not CustomerRequestedResolution.ANSWER_PRODUCT_QUESTION
    )
    shipping_fee_policy = cost_type is not CommercialCostType.NONE
    backend_operation = bool(_EXPLICIT_BACKEND_OPERATION_PATTERN.search(normalized))
    has_product_context = bool(facets) or issue is not CustomerIssueType.UNKNOWN_REASON
    standalone_usage_statement = bool(
        current_usage_signal
        and not has_service_context
        and not commercial_resolutions
        and issue is CustomerIssueType.UNKNOWN_REASON
        and not facets
    )

    primary_arbitration = (
        (
            CustomerPrimaryGoal.ORDER_OR_REFUND_STATUS,
            CustomerRequestedResolution.CHECK_STATUS in commercial_resolutions
            or cost_type is CommercialCostType.REFUND_AMOUNT_DEDUCTION,
        ),
        (CustomerPrimaryGoal.BACKEND_OPERATION_REQUEST, backend_operation),
        (CustomerPrimaryGoal.GENERAL_POLICY_INFORMATION, shipping_fee_policy),
        (
            CustomerPrimaryGoal.AFTERSALES_PROBLEM_RESOLUTION,
            issue is CustomerIssueType.WRONG_COLOR_STYLE_OR_ITEM
            and len(commercial_resolutions) > 1,
        ),
        (
            CustomerPrimaryGoal.RETURN_ELIGIBILITY,
            CustomerRequestedResolution.RETURN in commercial_resolutions,
        ),
        (
            CustomerPrimaryGoal.EXCHANGE_ELIGIBILITY,
            CustomerRequestedResolution.EXCHANGE in commercial_resolutions,
        ),
        (
            CustomerPrimaryGoal.CANCELLATION_REQUEST,
            CustomerRequestedResolution.CANCEL_ORDER in commercial_resolutions,
        ),
        (
            CustomerPrimaryGoal.REFUND_REQUEST,
            CustomerRequestedResolution.REFUND in commercial_resolutions,
        ),
        (
            CustomerPrimaryGoal.COMPLAINT_OR_DESCRIPTION_MISMATCH,
            issue is CustomerIssueType.DESCRIPTION_MISMATCH,
        ),
        (CustomerPrimaryGoal.AFTERSALES_PROBLEM_RESOLUTION, bool(commercial_resolutions)),
        (CustomerPrimaryGoal.SIZE_RECOMMENDATION, "size_recommendation" in facets),
        (
            CustomerPrimaryGoal.PRODUCT_INFORMATION,
            bool(facets)
            or bool(
                re.search(
                    r"褪色|掉色|换季|换气|颜色|(?:黑|白|红|蓝|绿|灰|棕|米|卡其|粉)色",
                    normalized,
                )
            ),
        ),
        (CustomerPrimaryGoal.AMBIGUOUS_HELP_REQUEST, True),
    )
    primary = next(goal for goal, matches in primary_arbitration if matches)

    policy_questions: list[str] = []
    if CustomerRequestedResolution.RETURN in unique_resolutions:
        policy_questions.append("return_eligibility")
    if CustomerRequestedResolution.EXCHANGE in unique_resolutions:
        policy_questions.append("exchange_eligibility")
    if CustomerRequestedResolution.REFUND in unique_resolutions:
        policy_questions.append("refund")
    if shipping_fee_policy:
        policy_questions.append(cost_type.value)

    backend_requirements: list[str] = []
    if primary is CustomerPrimaryGoal.ORDER_OR_REFUND_STATUS:
        backend_requirements.append("order_or_refund_status")
    if backend_operation:
        backend_requirements.append("order_operation")
    if issue in {
        CustomerIssueType.WRONG_COLOR_STYLE_OR_ITEM,
        CustomerIssueType.MISSING_ITEM,
        CustomerIssueType.DAMAGE,
        CustomerIssueType.SOLE_SEPARATION,
        CustomerIssueType.SUSPECTED_QUALITY_PROBLEM,
        CustomerIssueType.DESCRIPTION_MISMATCH,
    }:
        backend_requirements.append("order_and_evidence_verification")
    if shipping_fee_policy:
        backend_requirements.append("order_policy_verification")

    clarification_slots: list[str] = []
    if standalone_usage_statement:
        clarification_slots.append("usage_help_object")
    eligibility_goal = primary in {
        CustomerPrimaryGoal.RETURN_ELIGIBILITY,
        CustomerPrimaryGoal.EXCHANGE_ELIGIBILITY,
    }
    if (
        eligibility_goal
        and issue not in {
            CustomerIssueType.WRONG_COLOR_STYLE_OR_ITEM,
            CustomerIssueType.DAMAGE,
            CustomerIssueType.SOLE_SEPARATION,
        }
        and lifecycle is CustomerLifecycleStage.UNKNOWN
        and usage in {CustomerUsageState.UNKNOWN, CustomerUsageState.UNCLEAR}
        and has_product_context
    ):
        clarification_slots.append("usage_state")
    prior_clarification_count = state.service_clarification_count if inherited else 0
    if (
        eligibility_goal
        and usage is not CustomerUsageState.UNKNOWN
        and prior_clarification_count < 2
        and product_condition.shoe_box_complete.value == "unknown"
        and product_condition.tags_complete.value == "unknown"
    ):
        clarification_slots.append("packaging_and_tags")
    if cost_type is CommercialCostType.UNKNOWN_COST_TYPE:
        clarification_slots = ["cost_type"]

    route_arbitration = (
        (
            CustomerRequestRoute.POLICY_PLUS_CLARIFICATION,
            standalone_usage_statement,
        ),
        (
            CustomerRequestRoute.PRODUCT_ONLY,
            not commercial_resolutions and not policy_questions,
        ),
        (
            CustomerRequestRoute.BACKEND_STATUS,
            primary is CustomerPrimaryGoal.ORDER_OR_REFUND_STATUS,
        ),
        (CustomerRequestRoute.BACKEND_OPERATION, backend_operation),
        (CustomerRequestRoute.POLICY_PLUS_HANDOFF, shipping_fee_policy),
        (
            CustomerRequestRoute.POLICY_PLUS_HANDOFF,
            primary
            in {
                CustomerPrimaryGoal.COMPLAINT_OR_DESCRIPTION_MISMATCH,
                CustomerPrimaryGoal.AFTERSALES_PROBLEM_RESOLUTION,
            },
        ),
        (
            CustomerRequestRoute.POLICY_ONLY,
            lifecycle is CustomerLifecycleStage.PRE_PURCHASE_HYPOTHETICAL,
        ),
        (CustomerRequestRoute.POLICY_PLUS_CLARIFICATION, bool(clarification_slots)),
        (CustomerRequestRoute.PRODUCT_PLUS_POLICY, has_product_context),
        (CustomerRequestRoute.POLICY_ONLY, True),
    )
    route = next(candidate for candidate, matches in route_arbitration if matches)

    if primary is CustomerPrimaryGoal.ORDER_OR_REFUND_STATUS:
        eligibility_state = EligibilityDecisionState.REQUIRES_BACKEND_STATUS
    elif eligibility_goal:
        if lifecycle is CustomerLifecycleStage.PRE_PURCHASE_HYPOTHETICAL:
            eligibility_state = EligibilityDecisionState.GENERAL_POLICY_ONLY
        elif re.search(r"订单页.{0,6}(?:还有|存在|显示).{0,4}(?:售后入口|申请售后)", normalized):
            eligibility_state = EligibilityDecisionState.MAY_SUBMIT_REQUEST
        elif usage in {
            CustomerUsageState.WORN_OUTDOORS,
            CustomerUsageState.USED_FOR_MULTIPLE_DAYS,
            CustomerUsageState.ALTERED,
            CustomerUsageState.DAMAGED,
            CustomerUsageState.VISIBLY_DAMAGED_OR_ALTERED,
        }:
            eligibility_state = EligibilityDecisionState.REQUIRES_HUMAN_REVIEW
        else:
            eligibility_state = EligibilityDecisionState.REQUIRES_POLICY_CHECK
    elif shipping_fee_policy:
        eligibility_state = EligibilityDecisionState.GENERAL_POLICY_ONLY
    else:
        eligibility_state = EligibilityDecisionState.UNKNOWN

    supporting = list(facets)
    if issue is not CustomerIssueType.UNKNOWN_REASON:
        supporting.append(issue.value)
    return CustomerRequestFrame(
        original_text=original,
        normalized_text=normalized,
        primary_goal=primary,
        requested_resolution=unique_resolutions,
        product_facets=facets,
        issue_type=issue,
        lifecycle_stage=lifecycle,
        usage_state=usage,
        lifecycle_provenance=lifecycle_provenance,
        usage_provenance=usage_provenance,
        product_condition=product_condition,
        eligibility_state=eligibility_state,
        cost_type=cost_type,
        policy_questions=tuple(dict.fromkeys(policy_questions)),
        backend_requirements=tuple(dict.fromkeys(backend_requirements)),
        clarification_slots=tuple(clarification_slots),
        supporting_product_context=tuple(dict.fromkeys(supporting)),
        route=route,
        usage_evidence=usage_evidence,
        inherited_service_context=inherited,
    )


_CUSTOMER_COMPLAINT_REASON_LABELS = {
    CustomerIssueType.POOR_BREATHABILITY: "不透气",
    CustomerIssueType.INSUFFICIENT_WARMTH: "不够保暖",
    CustomerIssueType.SLIPPERY_EXPERIENCE: "走路打滑",
    CustomerIssueType.UNCOMFORTABLE_HARD_OR_HEAVY: "穿着不舒服",
    CustomerIssueType.RUBBING_OR_PRESSURE: "磨脚或受压",
    CustomerIssueType.WRONG_SIZE_OR_FIT: "尺码或版型不合适",
    CustomerIssueType.SUBJECTIVE_DISSATISFACTION: "颜色不合心意",
}


def _customer_complaint_reason(frame: CustomerRequestFrame) -> str:
    normalized = frame.normalized_text
    if frame.issue_type is CustomerIssueType.UNCOMFORTABLE_HARD_OR_HEAVY:
        if "鞋底太硬" in normalized or "太硬" in normalized:
            return "鞋底太硬"
        if "太重" in normalized:
            return "穿着太重"
        return "穿着不舒服"
    if frame.issue_type is CustomerIssueType.RUBBING_OR_PRESSURE:
        if "磨脚" in normalized:
            return "磨脚"
        return "穿着受压或拥挤"
    return _CUSTOMER_COMPLAINT_REASON_LABELS.get(
        frame.issue_type,
        "您反馈的使用感受",
    )


def plan_customer_service_answer(frame: CustomerRequestFrame) -> str | None:
    """Render a short, policy-bounded answer with the requested action first."""
    if frame.route is CustomerRequestRoute.PRODUCT_ONLY:
        return None
    if "delivery_location_object" in frame.clarification_slots:
        return AMBIGUOUS_DELIVERY_LOCATION_CLARIFICATION
    if "short_service_object" in frame.clarification_slots:
        if "退" in frame.normalized_text:
            return "请问您想咨询退货流程、退款进度，还是其他售后问题？"
        return "请问您想了解一般流程、当前处理状态，还是需要人工执行操作？"
    if "usage_help_object" in frame.clarification_slots:
        return "请问您是想咨询退换货条件，还是想了解商品的穿着体验呢？"

    normalized = frame.normalized_text
    resolutions = set(frame.requested_resolution)
    issue = frame.issue_type
    if frame.cost_type is CommercialCostType.UNKNOWN_COST_TYPE:
        return (
            "亲，请问您想确认的是退货寄回的运费由谁承担，还是退款时是否会扣手续费呢？"
            "这两项规则不同，需要结合订单原因和订单页保障确认哦。"
        )
    if frame.cost_type is CommercialCostType.INSURANCE_REIMBURSEMENT:
        return (
            "亲，是否有相应保险保障、具体承保方和可报销金额，需要以当前商品详情页、订单页和保障说明为准哦。"
            "当前无法直接确认是否可赔或具体金额，页面没有明确标注时请按当前店铺规则或联系人工客服核验。"
        )
    if frame.cost_type is CommercialCostType.REFUND_AMOUNT_DEDUCTION:
        return (
            "亲，我无法查询这笔订单实际退款金额或扣减明细哦。"
            "请先核对订单页的退款记录和费用明细，仍不一致时联系人工客服核验。"
        )
    if frame.cost_type is CommercialCostType.RETURN_SHIPPING_FEE:
        return (
            "亲，退货寄回运费由谁承担，需要结合售后原因、订单页规则和实际核验结果确认哦。"
            "请先查看订单页的售后说明；页面无法确认时再联系人工客服。"
        )
    if frame.cost_type is CommercialCostType.EXCHANGE_SHIPPING_FEE:
        return (
            "亲，换货产生的寄回和再次寄出费用，需要结合换货原因、订单页规则和实际核验结果确认哦。"
            "当前不能直接判定由哪一方承担，请先查看订单页售后说明。"
        )
    if frame.cost_type is CommercialCostType.ORIGINAL_DELIVERY_FEE:
        return (
            "亲，下单时支付的原配送费是否随退款退回，需要结合订单页费用明细、售后原因和当前规则确认哦。"
            "页面没有说明时请联系人工客服核验。"
        )
    if frame.cost_type is CommercialCostType.REFUND_PROCESSING_FEE:
        return (
            "亲，退款是否涉及手续费或金额扣减，需要以订单页退款明细和当前规则为准哦。"
            "当前不能直接确认会收费或全额退回，页面不明确时请联系人工客服核验。"
        )
    if frame.cost_type is CommercialCostType.COMPENSATION:
        return (
            "亲，是否涉及补偿及具体金额，需要结合订单原因、相关凭证和平台核验结果确认哦。"
            "当前不能预先承诺补偿，请通过订单页售后入口提交核验。"
        )
    if frame.primary_goal is CustomerPrimaryGoal.ORDER_OR_REFUND_STATUS:
        if "退款" in normalized or frame.lifecycle_stage is CustomerLifecycleStage.REFUND_PROCESSING:
            return (
                "亲，我无法查询这笔订单当前的退款进度或到账状态。"
                "请先查看订单页的退款记录，如仍不明确请联系人工客服核验。"
            )
        return (
            "亲，我无法查询这笔订单当前的售后处理状态。"
            "请先查看订单页的售后进度，如仍不明确请联系人工客服核验。"
        )
    if frame.route is CustomerRequestRoute.BACKEND_OPERATION:
        requested = "、".join(
            {
                CustomerRequestedResolution.EXCHANGE: "改码或换货",
                CustomerRequestedResolution.CANCEL_ORDER: "取消订单",
                CustomerRequestedResolution.REFUND: "退款",
                CustomerRequestedResolution.REPLACE_OR_RESEND: "补发",
                CustomerRequestedResolution.RETURN: "退货",
            }.get(item, item.value)
            for item in frame.requested_resolution
        ) or "该订单操作"
        return (
            f"亲，{requested}都需要结合订单当前状态在后台处理，我无法直接替您完成哦。"
            "请先在订单页查看可用操作；页面无法办理时请联系人工客服。"
        )
    if len(resolutions) > 1:
        labels = []
        for resolution, label in (
            (CustomerRequestedResolution.EXCHANGE, "换货"),
            (CustomerRequestedResolution.RETURN, "退货"),
            (CustomerRequestedResolution.REPLACE_OR_RESEND, "补发"),
            (CustomerRequestedResolution.REFUND, "退款"),
            (CustomerRequestedResolution.CANCEL_ORDER, "取消订单"),
        ):
            if resolution in resolutions:
                labels.append(label)
        choices = "或".join(labels)
        return (
            f"亲，您提到的{choices}需要结合订单状态、商品情况和订单页售后规则核验，当前不能直接确认哪一种已经获批哦。"
            "建议保留相关商品和订单凭证，先从订单页售后入口提交；无法选择对应方式时请联系人工客服。"
        )
    if frame.primary_goal is CustomerPrimaryGoal.COMPLAINT_OR_DESCRIPTION_MISMATCH:
        return (
            "亲，如果实际商品体验或外观与页面描述不一致，建议先保留商品页截图、实物照片和订单等相关凭证哦。"
            "是否构成描述不一致或责任归属仍需核验，请通过订单页售后入口提交，必要时联系人工客服。"
        )
    if issue in {
        CustomerIssueType.WRONG_COLOR_STYLE_OR_ITEM,
        CustomerIssueType.MISSING_ITEM,
    }:
        return (
            "亲，您反馈的是收到商品与订单不一致或数量异常，需要结合订单和实物凭证核验哦。"
            "请保留商品、包装和订单信息，通过订单页售后入口提交；无法操作时请联系人工客服。"
        )
    if issue in {
        CustomerIssueType.DAMAGE,
        CustomerIssueType.SOLE_SEPARATION,
        CustomerIssueType.SUSPECTED_QUALITY_PROBLEM,
    }:
        return (
            "亲，您反馈的商品异常需要结合订单、商品状态和相关凭证核验，当前不能直接判定为质量问题哦。"
            "建议保留实物照片和订单信息，通过订单页售后入口申请处理；无法操作时请联系人工客服。"
        )
    if frame.primary_goal is CustomerPrimaryGoal.RETURN_ELIGIBILITY:
        if frame.lifecycle_stage is CustomerLifecycleStage.PRE_PURCHASE_HYPOTHETICAL:
            return (
                "亲，购买后是否可以退货要以商品详情页和订单页的售后规则为准哦。"
                "下单前建议先查看页面标注的退货条件，当前不能预先确认具体订单一定符合。"
            )
        if (
            frame.product_condition.cleanliness.value == "clean"
            and frame.product_condition.cleanliness.provenance
            is EvidenceProvenance.EXPLICIT_USER_STATEMENT
        ):
            return (
                "了解，您反馈商品没有弄脏。"
                "不过“没脏”只是其中一项，是否符合退货条件还需要结合鞋盒、吊牌、配件、穿着痕迹和订单页规则确认哦。"
                "建议先查看订单页是否仍可申请售后；页面无法确认时再联系人工客服核验。"
            )
        if (
            frame.usage_state is CustomerUsageState.INDOOR_TRY_ON
            and "packaging_and_tags" in frame.clarification_slots
        ):
            evidence = frame.usage_evidence
            if evidence.indoor_use.value == "yes" and evidence.outdoor_use.value == "no":
                if evidence.has_been_tried_on.value == "yes":
                    acknowledgement = "了解，您反馈是室内试穿，且没有外出使用哦。"
                elif evidence.has_been_worn.value == "yes":
                    acknowledgement = "了解，您反馈只在家里穿过，没有外出使用哦。"
                else:
                    acknowledgement = "了解，您反馈只在室内使用过，没有外出使用哦。"
            elif evidence.indoor_use.value == "yes":
                if evidence.has_been_tried_on.value == "yes":
                    acknowledgement = "了解，您反馈的是室内试穿哦。"
                else:
                    acknowledgement = "了解，您反馈在室内穿过哦。"
            else:
                acknowledgement = "了解，您反馈简单试穿过哦。"
            return (
                acknowledgement
                +
                "是否符合退货条件还要结合商品、鞋盒、吊牌和配件状态以及订单页规则确认；"
                "请问鞋盒和吊牌是否还完整保留呢？"
            )
        if frame.usage_state is CustomerUsageState.INDOOR_TRY_ON:
            return (
                "亲，已了解您反馈的是室内试穿；是否符合退货条件仍需结合订单规则和商品各项状态核验哦。"
                "请先查看订单页售后入口，页面无法确认时再联系人工客服。"
            )
        if frame.usage_state is CustomerUsageState.UNUSED:
            return (
                "亲，已了解商品目前尚未穿着；能否退货仍需结合订单售后规则和商品状态确认哦。"
                "请先查看订单页售后入口，并按页面要求提交。"
            )
        if frame.usage_state is CustomerUsageState.WORN_OUTDOORS:
            return (
                "亲，您反馈已经外出穿着过，能否退货需要结合订单售后规则和商品实际状态核验，当前不能直接确认哦。"
                "请在订单页查看售后入口，必要时联系人工客服。"
            )
        if frame.usage_state is CustomerUsageState.USED_FOR_MULTIPLE_DAYS:
            if frame.usage_evidence.outdoor_use.value == "no":
                acknowledgement = "您反馈没有外出使用，但在室内穿了较长时间"
            else:
                acknowledgement = "您反馈已经穿着或使用了较长时间"
            return (
                f"亲，{acknowledgement}，能否退货需要结合订单售后规则和商品实际状态核验，当前不能直接确认哦。"
                "请在订单页查看售后入口，必要时联系人工客服。"
            )
        if frame.usage_state in {
            CustomerUsageState.ALTERED,
            CustomerUsageState.DAMAGED,
            CustomerUsageState.VISIBLY_DAMAGED_OR_ALTERED,
        }:
            return (
                "亲，您反馈商品存在使用状态变化，能否退货需要结合订单售后规则和商品实际状态核验，当前不能直接确认哦。"
                "请在订单页查看售后入口，必要时联系人工客服。"
            )
        if "usage_state" in frame.clarification_slots:
            complaint_reason = _customer_complaint_reason(frame)
            return (
                "亲，能否退货需要结合订单的售后规则、商品状态和实际穿着情况确认，"
                f"不能只根据“{complaint_reason}”这一点直接判断哦。"
                "您可以先查看订单页是否仍可申请售后；请问这双鞋只是室内试穿，还是已经外出穿过了呢？"
            )
        return (
            "亲，能否退货需要结合订单售后规则、商品状态和当前订单页信息确认哦。"
            "请先查看订单页是否仍可申请售后，页面无法确认时请联系人工客服。"
        )
    if frame.primary_goal is CustomerPrimaryGoal.EXCHANGE_ELIGIBILITY:
        if frame.lifecycle_stage is CustomerLifecycleStage.PRE_PURCHASE_HYPOTHETICAL:
            return (
                "亲，购买后是否可以换货要以商品详情页和订单页的售后规则为准哦。"
                "下单前建议先核对尺码信息和页面标注的换货条件。"
            )
        question = "；请问目前只是室内试穿，还是已经外出穿过了呢？" if "usage_state" in frame.clarification_slots else "。"
        return (
            "亲，能否换货需要结合订单售后规则、商品状态和可选库存确认，当前不能直接确认已经可以换哦。"
            f"请先查看订单页售后入口{question}"
        )
    if frame.primary_goal is CustomerPrimaryGoal.CANCELLATION_REQUEST:
        return (
            "亲，订单能否取消取决于当前订单状态，我无法直接替您取消或确认已经取消哦。"
            "请先在订单页查看是否有取消入口，无法操作时请联系人工客服。"
        )
    if frame.primary_goal is CustomerPrimaryGoal.REFUND_REQUEST:
        return (
            "亲，退款需要通过订单页售后入口按页面提示申请，我无法直接替您发起或确认退款哦。"
            "如果订单页没有对应入口，请联系人工客服核验。"
        )
    return (
        "亲，这个问题需要结合订单状态、商品情况和当前售后规则核验哦。"
        "请先查看订单页的售后入口，仍不明确时联系人工客服。"
    )


def update_customer_request_state(
    previous_state: ConversationState | dict | None,
    frame: CustomerRequestFrame,
    *,
    answer: str,
) -> dict[str, object]:
    """Persist only bounded service slots for short, isolated follow-ups."""
    state = coerce_conversation_state(previous_state)
    state.service_primary_goal = frame.primary_goal.value
    state.service_requested_resolutions = tuple(item.value for item in frame.requested_resolution)
    state.service_issue_type = frame.issue_type.value
    state.service_lifecycle_stage = frame.lifecycle_stage.value
    state.service_usage_state = frame.usage_state.value
    state.service_lifecycle_provenance = frame.lifecycle_provenance.value
    state.service_usage_provenance = frame.usage_provenance.value
    state.service_usage_evidence = {
        **{
            field_name: {
                "value": getattr(frame.usage_evidence, field_name).value,
                "status": getattr(frame.usage_evidence, field_name).status.value,
                "provenance": getattr(frame.usage_evidence, field_name).provenance.value,
            }
            for field_name in _USAGE_EVIDENCE_FIELDS
        },
        "evidence_provenance": frame.usage_evidence.evidence_provenance.value,
    }
    state.service_product_condition = {
        field_name: {
            "value": getattr(frame.product_condition, field_name).value,
            "status": getattr(frame.product_condition, field_name).status.value,
            "provenance": getattr(frame.product_condition, field_name).provenance.value,
        }
        for field_name in _PRODUCT_CONDITION_FIELDS
    }
    state.service_eligibility_state = frame.eligibility_state.value
    state.service_cost_type = frame.cost_type.value
    asked_question = "？" in answer or "?" in answer
    if frame.inherited_service_context:
        state.service_clarification_count = min(
            2,
            state.service_clarification_count + (1 if asked_question else 0),
        )
    else:
        state.service_clarification_count = 1 if asked_question else 0
    state.service_pending_clarification = frame.clarification_slots
    state.service_supporting_context = frame.supporting_product_context
    state.current_topic = f"service:{frame.primary_goal.value}"
    state.query_type = f"customer_request_{frame.route.value.casefold()}"
    state.requires_backend_api = frame.route in {
        CustomerRequestRoute.BACKEND_STATUS,
        CustomerRequestRoute.BACKEND_OPERATION,
        CustomerRequestRoute.POLICY_PLUS_HANDOFF,
        CustomerRequestRoute.FULL_HANDOFF,
    }
    state.last_user_query = frame.original_text
    state.last_assistant_answer = answer
    state.last_safe_answer_type = "customer_service_boundary"
    state.state_confidence = 0.95
    state.state_turn_count = state.state_turn_count + 1 if frame.inherited_service_context else 1
    state.updated_at_turn += 1
    state.should_reset = False
    return state.to_dict()


def clear_customer_service_context(
    previous_state: ConversationState | dict | None,
) -> dict[str, object] | None:
    """Reset service-only slots when an explicit product topic takes over."""
    if previous_state is None:
        return None
    state = coerce_conversation_state(previous_state)
    state.service_primary_goal = "none"
    state.service_requested_resolutions = ()
    state.service_issue_type = CustomerIssueType.UNKNOWN_REASON.value
    state.service_lifecycle_stage = CustomerLifecycleStage.UNKNOWN.value
    state.service_usage_state = CustomerUsageState.UNKNOWN.value
    state.service_lifecycle_provenance = EvidenceProvenance.UNKNOWN.value
    state.service_usage_provenance = EvidenceProvenance.UNKNOWN.value
    state.service_usage_evidence = {}
    state.service_product_condition = {}
    state.service_eligibility_state = EligibilityDecisionState.UNKNOWN.value
    state.service_cost_type = CommercialCostType.NONE.value
    state.service_clarification_count = 0
    state.service_pending_clarification = ()
    state.service_supporting_context = ()
    if state.current_topic.startswith("service:"):
        state.current_topic = "none"
    return state.to_dict()


def load_dependencies():
    try:
        import numpy as np
        import pandas as pd
        from dotenv import load_dotenv
        from openai import OpenAI
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependencies. Run: python -m pip install -r outputs\\requirements.txt"
        ) from exc
    return np, pd, load_dotenv, OpenAI, SentenceTransformer, cosine_similarity


def load_llm_config(load_dotenv, OpenAI) -> LLMConfig:
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).strip()
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL).strip()
    client = OpenAI(api_key=api_key, base_url=base_url) if api_key else None
    print(f"DEEPSEEK_API_KEY loaded: {bool(api_key)}")
    print(f"LLM mode: {'DeepSeek API' if api_key else 'mock'}")
    print(f"Model: {model}")
    return LLMConfig(api_key=api_key, base_url=base_url, model=model, client=client)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def combined_source_hash(*paths: Path) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(file_sha256(path).encode("utf-8"))
    return digest.hexdigest()


def resolve_qa_csv_path(path: Path | str | None = None) -> Path:
    if path is not None:
        candidate = Path(path).expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"QA CSV not found: {candidate}")
    for candidate in (DEFAULT_QA_CSV_PATH, FALLBACK_QA_CSV_PATH):
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "QA CSV not found. Expected one of: "
        f"{DEFAULT_QA_CSV_PATH}, {FALLBACK_QA_CSV_PATH}"
    )


def resolve_snippets_csv_path(path: Path | str | None = None) -> Path:
    if path is not None:
        candidate = Path(path).expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise FileNotFoundError(f"Knowledge snippets CSV not found: {candidate}")
    if DEFAULT_SNIPPETS_CSV_PATH.is_file():
        return DEFAULT_SNIPPETS_CSV_PATH.resolve()
    raise FileNotFoundError(f"Knowledge snippets CSV not found: {DEFAULT_SNIPPETS_CSV_PATH}")


def resolve_cache_dir(cache_dir: Path | str | None, mixed_mode: bool) -> Path:
    root = Path(cache_dir).expanduser().resolve() if cache_dir is not None else DEFAULT_CACHE_ROOT
    subdir = V2_CACHE_SUBDIR if mixed_mode else V1_CACHE_SUBDIR
    target = root / subdir
    target.mkdir(parents=True, exist_ok=True)
    return target


def normalize_category(category: object) -> str:
    value = str(category or "").strip()
    return value or CATEGORY_OTHER


def snippet_text_for_embedding(category: str, title: str, content: str) -> str:
    parts = [category, title, content[:SNIPPET_EMBED_CONTENT_LIMIT]]
    return " ".join(part.strip() for part in parts if part and part.strip())


def row_needs_backend_api(row) -> bool:
    return parse_bool_flag(row.get("needs_backend_api"), default=False)


def row_is_backend_only(row) -> bool:
    source_type = str(row.get("source_type", "")).strip()
    return row_needs_backend_api(row) or source_type in BACKEND_SOURCE_TYPES


def knowledge_quarantine_reason(row) -> str | None:
    """Return a reason only for an exact, stable structured-knowledge identity."""

    source_file = str(row.get("source_file", "")).strip()
    doc_id = str(row.get("doc_id", "")).strip()
    if source_file != SNIPPETS_CORPUS_SOURCE_FILE:
        return None
    return QUARANTINED_KNOWLEDGE_DOC_IDS.get(doc_id)


def filter_quarantined_knowledge_results(results: list) -> list:
    return [item for item in results if knowledge_quarantine_reason(item[0]) is None]


def filter_results_for_answer_generation(
    results: list,
    backend_required: bool,
    user_question: str = "",
) -> list:
    filtered = filter_quarantined_knowledge_results(results)
    if not backend_required:
        filtered = [item for item in filtered if not row_is_backend_only(item[0])]
        filtered = [
            item
            for item in filtered
            if not contains_any(
                row_answer_text(item[0]), UNSAFE_LIVE_LOGISTICS_ANSWER_MARKERS
            )
        ]
    filtered = [item for item in filtered if not is_risky_chat_qa_row(item[0])]
    if is_foot_discomfort_query(user_question):
        non_transition = [item for item in filtered if not is_foot_transition_qa_row(item[0])]
        if non_transition:
            filtered = non_transition
    if is_post_ship_refund_query(user_question):
        post_ship_rows = [item for item in filtered if not is_generic_return_only_row(item[0])]
        if post_ship_rows:
            filtered = post_ship_rows
    return filtered


def is_generic_return_only_row(row) -> bool:
    if str(row.get("source_type", "chat_qa")).strip() != "chat_qa":
        return False
    combined = row_combined_text(row)
    if not contains_any(combined, GENERIC_RETURN_KEYWORDS + ["\u9000\u6b3e", "\u9000\u8d27"]):
        return False
    return not contains_any(combined, POST_SHIP_CONTENT_KEYWORDS)


def resolve_backend_required(
    user_question: str,
    reranked_results: list,
    allow_top_row_inference: bool = True,
) -> bool:
    if requires_backend_api(user_question):
        return True
    if not allow_top_row_inference or not reranked_results:
        return False
    top_row, top_score = reranked_results[0][0], float(reranked_results[0][1])
    if row_is_backend_only(top_row) and top_score >= 0.62 and not is_business_query(user_question):
        return True
    return False


def parse_bool_flag(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().casefold()
    if normalized in {"true", "1", "yes", "y"}:
        return True
    if normalized in {"false", "0", "no", "n", ""}:
        return default if normalized == "" else False
    return default


def corpus_embedding_texts(corpus) -> list[str]:
    if "text_for_embedding" in corpus.columns:
        return corpus["text_for_embedding"].astype(str).tolist()
    return corpus["question"].astype(str).tolist()


def _resolve_qa_category(frame, pd):
    if "refined_category" in frame.columns:
        categories = frame["refined_category"].astype(str).str.strip()
        if "category" in frame.columns:
            fallback = frame["category"].astype(str).str.strip()
            categories = categories.where(categories != "", fallback)
        return categories
    if "category" in frame.columns:
        return frame["category"].astype(str).str.strip()
    return pd.Series([CATEGORY_OTHER] * len(frame), index=frame.index)


def _allocate_unique_document_ids(
    document_ids: Iterable[object], *, immutable_prefix_count: int = 0
) -> list[str]:
    original_ids = list(document_ids)
    if not 0 <= immutable_prefix_count <= len(original_ids):
        raise ValueError("Immutable document-ID prefix is outside the corpus.")
    if any(not isinstance(doc_id, str) or not doc_id for doc_id in original_ids):
        raise ValueError("Document IDs must be nonempty strings.")

    reserved_ids = set(original_ids)
    allocated_ids: set[str] = set()
    occurrence_by_id: dict[str, int] = {}
    result: list[str] = []

    for index, original_id in enumerate(original_ids):
        occurrence = occurrence_by_id.get(original_id, 0) + 1
        occurrence_by_id[original_id] = occurrence
        if original_id not in allocated_ids:
            allocated_ids.add(original_id)
            result.append(original_id)
            continue
        if index < immutable_prefix_count:
            raise ValueError("Duplicate document ID appears in the immutable prefix.")

        candidate = f"{original_id}__dup_{occurrence}"
        while not candidate or candidate in reserved_ids or candidate in allocated_ids:
            occurrence += 1
            candidate = f"{original_id}__dup_{occurrence}"
        occurrence_by_id[original_id] = occurrence
        allocated_ids.add(candidate)
        result.append(candidate)

    return result


def build_qa_corpus_items(csv_path: Path, pd) -> list[dict]:
    frame = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = {"final_question", "final_answer"}.difference(frame.columns)
    if missing:
        raise ValueError("Input CSV missing fields: " + ", ".join(sorted(missing)))

    questions = frame["final_question"].astype(str).str.strip()
    answers = frame["final_answer"].astype(str).str.strip()
    categories = _resolve_qa_category(frame, pd)
    session_ids = (
        frame["session_id"].astype(str).str.strip()
        if "session_id" in frame.columns
        else pd.Series([""] * len(frame), index=frame.index)
    )

    items: list[dict] = []
    for row_idx, row in frame.iterrows():
        question = str(questions.loc[row_idx]).strip()
        answer = str(answers.loc[row_idx]).strip()
        if not question or not answer:
            continue
        category = normalize_category(categories.loc[row_idx])
        session_id = str(session_ids.loc[row_idx]).strip()
        doc_id = f"qa_{session_id}_{row_idx}" if session_id else f"qa_{row_idx}"
        items.append(
            {
                "doc_id": doc_id,
                "source_type": "chat_qa",
                "category": category,
                "title": question,
                "text_for_embedding": question,
                "answer_or_content": answer,
                "question": question,
                "answer": answer,
                "priority": DEFAULT_QA_PRIORITY,
                "allowed_for_answer": True,
                "needs_backend_api": False,
                "source_file": QA_CORPUS_SOURCE_FILE,
                "session_id": session_id,
            }
        )
    if not items:
        raise ValueError("No searchable QA rows after filtering empty question/answer.")
    return items


def build_snippet_corpus_items(csv_path: Path, pd) -> list[dict]:
    frame = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    required = {"source_type", "category", "title", "content", "priority", "allowed_for_answer"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError("Knowledge snippets CSV missing fields: " + ", ".join(sorted(missing)))

    items: list[dict] = []
    for row_idx, row in frame.iterrows():
        if not parse_bool_flag(row.get("allowed_for_answer"), default=False):
            continue
        content = str(row.get("content", "")).strip()
        if not content:
            continue
        category = normalize_category(row.get("category", ""))
        title = str(row.get("title", "")).strip()
        original_key = str(row.get("original_key", "")).strip()
        doc_id = f"snippet_{original_key}" if original_key else f"snippet_{row_idx}"
        doc_id = doc_id.replace(",", "_").replace(" ", "_")
        text_for_embedding = snippet_text_for_embedding(category, title, content)
        needs_backend = parse_bool_flag(row.get("needs_backend_api"), default=False)
        items.append(
            {
                "doc_id": doc_id,
                "source_type": str(row.get("source_type", "")).strip() or "knowledge_snippet",
                "category": category,
                "title": title,
                "text_for_embedding": text_for_embedding,
                "answer_or_content": content,
                "question": title or category,
                "answer": content,
                "priority": int(str(row.get("priority", "70")).strip() or "70"),
                "allowed_for_answer": True,
                "needs_backend_api": needs_backend,
                "source_file": SNIPPETS_CORPUS_SOURCE_FILE,
                "session_id": "",
            }
        )
    if not items:
        raise ValueError("No searchable knowledge snippets after filtering allowed_for_answer/content.")
    return items


def build_corpus(csv_path: Path, pd):
    return build_mixed_corpus(csv_path, None, pd)


def build_mixed_corpus(qa_csv_path: Path, snippets_csv_path: Path | None, pd):
    items = build_qa_corpus_items(qa_csv_path, pd)
    if snippets_csv_path is not None:
        qa_item_count = len(items)
        snippet_items = build_snippet_corpus_items(snippets_csv_path, pd)
        items.extend(snippet_items)
        allocated_ids = _allocate_unique_document_ids(
            (item.get("doc_id") for item in items),
            immutable_prefix_count=qa_item_count,
        )
        for index in range(qa_item_count, len(items)):
            items[index]["doc_id"] = allocated_ids[index]
        print(
            f"Mixed corpus: {len(items) - len(snippet_items):,} QA + "
            f"{len(snippet_items):,} knowledge snippets"
        )
    corpus = pd.DataFrame(items).reset_index(drop=True)
    if snippets_csv_path is not None:
        document_ids = corpus["doc_id"].tolist()
        if (
            any(not isinstance(doc_id, str) or not doc_id for doc_id in document_ids)
            or len(set(document_ids)) != len(document_ids)
        ):
            raise ValueError(
                "Mixed corpus document IDs must be nonempty and globally unique."
            )
    return corpus


def cache_is_valid(
    corpus,
    embeddings,
    source_hash: str,
    embedding_model_name: str,
    corpus_version: str | None = None,
) -> bool:
    attrs = getattr(corpus, "attrs", {})
    version_ok = corpus_version is None or attrs.get("corpus_version") == corpus_version
    return (
        version_ok
        and attrs.get("source_sha256") == source_hash
        and attrs.get("model_name") == embedding_model_name
        and len(corpus) == embeddings.shape[0]
        and embeddings.ndim == 2
        and embeddings.shape[1] > 0
    )


def load_or_create_cache(
    csv_path: Path,
    cache_dir: Path,
    embedding_model,
    embedding_model_name: str,
    batch_size: int,
    rebuild: bool,
    np,
    pd,
    snippets_csv_path: Path | None = None,
):
    mixed_mode = snippets_csv_path is not None and snippets_csv_path.is_file()
    mode_cache_dir = resolve_cache_dir(cache_dir, mixed_mode)
    if mixed_mode:
        embeddings_path = mode_cache_dir / MIXED_EMBEDDING_FILENAME
        corpus_path = mode_cache_dir / MIXED_CORPUS_FILENAME
        source_hash = combined_source_hash(csv_path, snippets_csv_path)
        corpus_version = CORPUS_VERSION_V2_MIXED
    else:
        embeddings_path = mode_cache_dir / EMBEDDING_FILENAME
        corpus_path = mode_cache_dir / CORPUS_FILENAME
        source_hash = file_sha256(csv_path)
        corpus_version = CORPUS_VERSION_V1

    if not rebuild and embeddings_path.is_file() and corpus_path.is_file():
        try:
            corpus = pd.read_pickle(corpus_path)
            embeddings = np.load(embeddings_path, mmap_mode="r")
            if cache_is_valid(corpus, embeddings, source_hash, embedding_model_name, corpus_version):
                label = "mixed corpus" if mixed_mode else "QA"
                print(f"Loaded cache: {len(corpus):,} {label} rows")
                return corpus, embeddings
            print("Cache does not match current sources/model; rebuilding embeddings.")
        except (OSError, ValueError, EOFError, AttributeError) as exc:
            print(f"Failed to read cache; rebuilding embeddings: {exc}")

    corpus = build_mixed_corpus(csv_path, snippets_csv_path if mixed_mode else None, pd)
    print(f"Building embeddings for {len(corpus):,} documents...")
    embeddings = embedding_model.encode(
        corpus_embedding_texts(corpus),
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32", copy=False)
    corpus.attrs["source_sha256"] = source_hash
    corpus.attrs["model_name"] = embedding_model_name
    corpus.attrs["corpus_version"] = corpus_version
    corpus.to_pickle(corpus_path)
    np.save(embeddings_path, embeddings)
    print(f"Saved: {embeddings_path}")
    print(f"Saved: {corpus_path}")
    return corpus, embeddings


def retrieve(query: str, corpus, embeddings, embedding_model, top_k: int, cosine_similarity):
    search_query = expand_retrieval_query(query)
    query_embedding = embedding_model.encode(
        [search_query], convert_to_numpy=True, normalize_embeddings=True
    )
    scores = cosine_similarity(query_embedding, embeddings)[0]
    top_indices = scores.argsort()[-min(top_k, len(corpus)):][::-1]
    return [(corpus.iloc[int(index)], float(scores[index])) for index in top_indices]


def normalize_query_text(user_question: str) -> str:
    return re.sub(r"\s+", "", user_question.strip())


def row_answer_text(row) -> str:
    return str(row.get("answer_or_content", row.get("answer", ""))).strip()


def row_combined_text(row) -> str:
    return " ".join(
        [
            str(row.get("category", "")),
            str(row.get("title", "")),
            str(row.get("question", "")),
            row_answer_text(row),
        ]
    ).strip()


def has_risky_answer_content(text: str) -> bool:
    return any(pattern.search(str(text or "")) for pattern in RISKY_ANSWER_PATTERNS)


def is_risky_chat_qa_row(row) -> bool:
    if str(row.get("source_type", "chat_qa")).strip() != "chat_qa":
        return False
    return has_risky_answer_content(row_answer_text(row))


def is_foot_transition_qa_row(row) -> bool:
    if str(row.get("source_type", "chat_qa")).strip() != "chat_qa":
        return False
    return contains_any(row_combined_text(row), FOOT_TRANSITION_QA_KEYWORDS)


def is_slip_resistance_query(user_question: str) -> bool:
    return contains_any(normalize_query_text(user_question), SLIP_QUERY_KEYWORDS)


def is_post_ship_refund_query(user_question: str) -> bool:
    return contains_any(normalize_query_text(user_question), POST_SHIP_QUERY_KEYWORDS)


def is_foot_discomfort_query(user_question: str) -> bool:
    normalized = normalize_query_text(user_question)
    if contains_any(normalized, FOOT_DISCOMFORT_QUERY_KEYWORDS):
        return True
    if "\u811a\u90e8\u4e0d\u9002" in normalized:
        return True
    return "\u811a" in normalized and "\u4e0d\u8212\u670d" in normalized


def is_wrong_item_query(user_question: str) -> bool:
    return contains_any(normalize_query_text(user_question), WRONG_ITEM_QUERY_KEYWORDS)


def is_glue_quality_query(user_question: str) -> bool:
    normalized = normalize_query_text(user_question)
    if contains_any(normalized, GLUE_QUALITY_QUERY_KEYWORDS):
        return True
    return "\u5f00\u80f6" in normalized and "\u8d28\u91cf" in normalized


def is_compensation_request(query: str) -> bool:
    stripped = str(query or "").strip()
    if not stripped:
        return False
    if requires_backend_api(stripped):
        return False

    normalized = re.sub(r"\s+", "", stripped)
    for pattern in COMPENSATION_REQUEST_PATTERNS:
        if pattern.search(normalized):
            return True

    if not contains_any(normalized, COMPENSATION_REQUEST_KEYWORDS):
        return False

    if normalized in {
        "\u80fd\u8d54\u5417",
        "\u80fd\u8865\u5417",
        "\u80fd\u8d54\u507f\u5417",
        "\u80fd\u8865\u507f\u5417",
    }:
        return True

    if contains_any(normalized, COMPENSATION_REQUEST_SIGNAL_TERMS):
        return True

    return False


def is_review_incentive_request(query: str) -> bool:
    normalized = re.sub(r"\s+", "", str(query or "").strip())
    if not normalized:
        return False
    if contains_any(normalized, REVIEW_INCENTIVE_KEYWORDS):
        return True
    if "\u8fd4\u73b0" in normalized and contains_any(
        normalized, ["\u597d\u8bc4", "\u4e94\u661f", "\u8bc4\u4ef7", "\u622a\u56fe", "\u6652\u56fe"]
    ):
        return True
    if contains_any(normalized, ["\u597d\u8bc4", "\u4e94\u661f", "\u8bc4\u4ef7"]) and contains_any(
        normalized, ["\u622a\u56fe", "\u6652\u56fe"]
    ):
        return True
    return False


def is_price_difference_request(query: str) -> bool:
    normalized = re.sub(r"\s+", "", str(query or "").strip())
    if not normalized:
        return False
    if contains_any(normalized, PRICE_DIFFERENCE_KEYWORDS):
        return True
    return "\u4ef7\u5dee" in normalized and contains_any(
        normalized, ["\u9000", "\u8865", "\u80fd", "\u5417", "\u4ef7\u4fdd", "\u4fdd\u4ef7"]
    )


def is_shipping_fee_reimbursement_request(query: str) -> bool:
    normalized = re.sub(r"\s+", "", str(query or "").strip())
    if not normalized:
        return False
    if contains_any(normalized, SHIPPING_FEE_REIMBURSEMENT_KEYWORDS):
        return True
    return "\u62a5\u9500" in normalized and contains_any(
        normalized, ["\u8fd0\u8d39", "\u90ae\u8d39", "\u7ed9\u6211", "\u80fd"]
    )


def is_refund_status_or_amount_request(query: str) -> bool:
    stripped = str(query or "").strip()
    if not stripped:
        return False
    normalized = re.sub(r"\s+", "", stripped)
    if contains_any(normalized, REFUND_STATUS_OR_AMOUNT_KEYWORDS):
        return True
    if "\u9000\u6b3e" in normalized and contains_any(
        normalized, ["\u5230\u8d26", "\u591a\u5c11", "\u591a\u5c11\u94b1", "\u8fdb\u5ea6", "\u591a\u4e45", "\u51e0\u5929"]
    ):
        return True
    if "\u9000\u94b1" in normalized or "\u9000\u6211\u94b1" in normalized:
        return True
    return False


def is_payment_transfer_request(query: str) -> bool:
    normalized = re.sub(r"\s+", "", str(query or "").strip())
    if not normalized:
        return False
    return contains_any(normalized, PAYMENT_TRANSFER_KEYWORDS)


def is_discount_or_price_change_request(query: str) -> bool:
    normalized = re.sub(r"\s+", "", str(query or "").strip())
    if not normalized:
        return False
    return contains_any(normalized, DISCOUNT_OR_PRICE_CHANGE_KEYWORDS)


def is_invoice_request(query: str) -> bool:
    normalized = re.sub(r"\s+", "", str(query or "").strip())
    if not normalized:
        return False
    return contains_any(normalized, INVOICE_REQUEST_KEYWORDS)


def is_legal_compensation_request(query: str) -> bool:
    normalized = re.sub(r"\s+", "", str(query or "").strip())
    if not normalized:
        return False
    if contains_any(normalized, LEGAL_COMPENSATION_KEYWORDS):
        return True
    if "\u6295\u8bc9" in normalized and contains_any(
        normalized, ["\u8d54", "\u8d54\u507f", "\u8d54\u4ed8", "\u8d54\u94b1"]
    ):
        return True
    if "\u8d54\u4ed8" in normalized:
        return True
    return False


def detect_financial_risk_query(query: str) -> tuple[str, str] | None:
    stripped = str(query or "").strip()
    if not stripped:
        return None

    checks: list[tuple[str, object, str]] = [
        ("review_incentive_request", is_review_incentive_request, REVIEW_INCENTIVE_SAFE_ANSWER),
        ("payment_transfer_request", is_payment_transfer_request, PAYMENT_TRANSFER_SAFE_ANSWER),
        ("refund_status_or_amount_request", is_refund_status_or_amount_request, REFUND_STATUS_OR_AMOUNT_SAFE_ANSWER),
        ("legal_compensation_request", is_legal_compensation_request, LEGAL_COMPENSATION_SAFE_ANSWER),
        ("compensation_request", is_compensation_request, COMPENSATION_REQUEST_SAFE_ANSWER),
        ("price_difference_request", is_price_difference_request, PRICE_DIFFERENCE_SAFE_ANSWER),
        ("shipping_fee_reimbursement_request", is_shipping_fee_reimbursement_request, SHIPPING_FEE_REIMBURSEMENT_SAFE_ANSWER),
        ("discount_or_price_change_request", is_discount_or_price_change_request, DISCOUNT_OR_PRICE_CHANGE_SAFE_ANSWER),
        ("invoice_request", is_invoice_request, INVOICE_REQUEST_SAFE_ANSWER),
    ]
    for query_type, detector, answer in checks:
        if detector(stripped):
            return query_type, answer
    return None


def is_financial_risk_query(query: str) -> bool:
    return detect_financial_risk_query(query) is not None


def detect_financial_risk_from_assistant_answer(answer: str) -> str | None:
    stripped = str(answer or "").strip()
    if not stripped:
        return None
    for query_type, signals in FINANCIAL_ASSISTANT_ANSWER_SIGNALS:
        if contains_any(stripped, signals):
            return query_type
    return None


def inherit_financial_risk_from_previous(
    current_query: str,
    previous_user_query: str | None = None,
    previous_assistant_answer: str | None = None,
) -> FinancialRiskInheritance | None:
    current = str(current_query or "").strip()
    previous_user = str(previous_user_query or "").strip()
    previous_answer = str(previous_assistant_answer or "").strip()
    if not current or not previous_user:
        return None
    if not is_followup_query(current):
        return None

    inherited_type: str | None = None
    financial_from_previous = detect_financial_risk_query(previous_user)
    if financial_from_previous:
        inherited_type = financial_from_previous[0]
    else:
        inherited_type = detect_financial_risk_from_assistant_answer(previous_answer)

    if not inherited_type or inherited_type not in FINANCIAL_RISK_QUERY_TYPES:
        return None

    safe_answer = FINANCIAL_SAFE_ANSWER_BY_TYPE.get(inherited_type)
    if not safe_answer:
        return None

    return FinancialRiskInheritance(
        query_type=inherited_type,
        safe_answer=safe_answer,
        inherited_from_previous_query=previous_user,
    )


def is_pure_size_consultation_query(normalized: str) -> bool:
    if contains_any(normalized, AFTERSALES_OPERATION_CONTEXT_KEYWORDS):
        return False
    if re.search(r"\u6362\s*\d{2}\s*\u7801|\u6362\u6210\d{2}|\u6362\d{2}\u7801", normalized):
        return False
    if contains_any(normalized, AFTERSALES_SIZE_CONSULTATION_KEYWORDS):
        return True
    if re.search(r"\d{2}\u7801", normalized) and contains_any(
        normalized, ["\u9002\u5408", "\u591a\u957f", "\u600e\u4e48\u9009", "\u6807\u51c6", "\u5bf9\u5e94"]
    ):
        return True
    if ("\u5927\u4e00\u7801" in normalized or "\u5c0f\u4e00\u7801" in normalized) and "\u6362" not in normalized:
        return True
    return False


def is_aftersales_operation_request(query: str) -> bool:
    stripped = str(query or "").strip()
    if not stripped:
        return False
    normalized = re.sub(r"\s+", "", stripped)
    if is_pure_size_consultation_query(normalized):
        return False
    if contains_any(normalized, AFTERSALES_RESHIP_KEYWORDS):
        return True
    if contains_any(normalized, AFTERSALES_RETURN_RESHIP_KEYWORDS):
        return True
    if contains_any(normalized, AFTERSALES_BACKEND_ACTION_KEYWORDS):
        return True
    if contains_any(normalized, AFTERSALES_SIZE_EXCHANGE_KEYWORDS):
        return True
    if re.search(r"\u6362\s*\d{2}\s*\u7801|\u6362\u6210\d{2}|\u6362\d{2}\u7801", normalized):
        return True
    has_size_code = bool(re.search(r"\d{2}\u7801", normalized))
    has_operation_context = contains_any(
        normalized,
        ["\u8865\u53d1", "\u91cd\u53d1", "\u6362\u8d27", "\u9000\u56de", "\u5bc4\u56de", "\u53d1\u65b0", "\u6362\u65b0"],
    )
    if has_operation_context and has_size_code:
        return True
    if contains_any(normalized, ["\u53d1\u65b0", "\u6362\u65b0"]) and contains_any(
        normalized, ["\u5bc4\u56de", "\u9000\u56de", "\u9000"]
    ):
        return True
    return False


def detect_aftersales_operation_from_assistant_answer(answer: str) -> bool:
    stripped = str(answer or "").strip()
    if not stripped:
        return False
    return contains_any(stripped, AFTERSALES_ASSISTANT_ANSWER_SIGNALS)


def is_aftersales_followup_query(query: str) -> bool:
    normalized = re.sub(r"\s+", "", str(query or "").strip())
    if not normalized:
        return False
    return contains_any(normalized, AFTERSALES_FOLLOWUP_PHRASES)


def inherit_aftersales_operation_from_previous(
    current_query: str,
    previous_user_query: str | None = None,
    previous_assistant_answer: str | None = None,
) -> AftersalesOperationInheritance | None:
    current = str(current_query or "").strip()
    previous_user = str(previous_user_query or "").strip()
    previous_answer = str(previous_assistant_answer or "").strip()
    if not current or not previous_user:
        return None

    previous_is_aftersales = is_aftersales_operation_request(previous_user) or detect_aftersales_operation_from_assistant_answer(
        previous_answer
    )
    if not previous_is_aftersales:
        return None

    if not (
        is_followup_query(current)
        or is_aftersales_followup_query(current)
        or is_aftersales_operation_request(current)
    ):
        return None

    return AftersalesOperationInheritance(
        safe_answer=AFTERSALES_OPERATION_SAFE_ANSWER,
        inherited_from_previous_query=previous_user,
    )


def expand_retrieval_query(user_question: str) -> str:
    if is_slip_resistance_query(user_question):
        return f"{user_question.strip()}{SLIP_QUERY_EXPANSION}"
    if is_post_ship_refund_query(user_question):
        return f"{user_question.strip()} 拦截 拒收 退回后退款 商品发出后"
    if is_foot_discomfort_query(user_question):
        return f"{user_question.strip()} 就医 医生 皮肤科 脚部不适 人工核实"
    return user_question.strip()


def count_effective_query_chars(query: str) -> int:
    compact = re.sub(r"\s+", "", str(query or ""))
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", compact))


def is_intent_guard_priority_query(
    query: str,
    has_conversation_context: bool = False,
) -> bool:
    skip_retrieval, _guarded_type, _answer = intent_guard(
        query,
        has_conversation_context=has_conversation_context,
    )
    return skip_retrieval


def is_followup_query(query: str, has_conversation_context: bool = False) -> bool:
    stripped = str(query or "").strip()
    if not stripped:
        return False
    if is_intent_guard_priority_query(
        stripped,
        has_conversation_context=has_conversation_context,
    ):
        return False

    normalized = re.sub(r"\s+", "", stripped)
    if contains_any(normalized, IDENTITY_QUERY_KEYWORDS):
        return False
    if contains_any(normalized, HUMAN_HANDOVER_KEYWORDS):
        return False
    if requires_backend_api(stripped):
        return False
    if contains_any(normalized, ABUSIVE_OR_IRRELEVANT_KEYWORDS):
        return False

    if contains_any(normalized, FOLLOWUP_QUERY_PHRASES + BACKEND_STATE_FOLLOWUP_PHRASES):
        return True

    if len(normalized) <= 8 or count_effective_query_chars(stripped) <= 6:
        if is_business_query(stripped) and not contains_any(normalized, FOLLOWUP_QUERY_PHRASES):
            return False
        return True
    return False


def _combined_topic_text(previous_user_query: str, previous_assistant_answer: str) -> str:
    return f"{previous_user_query or ''}{previous_assistant_answer or ''}"


def build_contextual_query(
    current_query: str,
    previous_user_query: str,
    previous_assistant_answer: str = "",
) -> str:
    current = str(current_query or "").strip()
    previous_user = str(previous_user_query or "").strip()
    if not previous_user:
        return current

    combined_topic = _combined_topic_text(previous_user, previous_assistant_answer)
    normalized_current = re.sub(r"\s+", "", current)

    if contains_any(combined_topic, SLIP_TOPIC_CONTEXT_KEYWORDS) and contains_any(
        normalized_current, SLIP_FOLLOWUP_TRIGGERS
    ):
        return SLIP_FOLLOWUP_CONTEXTUAL_QUERY

    if contains_any(combined_topic, POST_SHIP_TOPIC_CONTEXT_KEYWORDS) and contains_any(
        normalized_current, POST_SHIP_FOLLOWUP_TRIGGERS
    ):
        return POST_SHIP_FOLLOWUP_CONTEXTUAL_QUERY

    if contains_any(combined_topic, QUALITY_TOPIC_CONTEXT_KEYWORDS) and contains_any(
        normalized_current, QUALITY_FOLLOWUP_TRIGGERS
    ):
        return QUALITY_FOLLOWUP_CONTEXTUAL_QUERY

    if contains_any(combined_topic, FOOT_TOPIC_CONTEXT_KEYWORDS) and contains_any(
        normalized_current, FOOT_FOLLOWUP_TRIGGERS
    ):
        return FOOT_FOLLOWUP_CONTEXTUAL_QUERY

    return f"{previous_user} {current}".strip()


def resolve_followup_context(
    current_query: str,
    previous_user_query: str | None = None,
    previous_assistant_answer: str | None = None,
) -> FollowupResolution:
    original = str(current_query or "").strip()
    previous_user = str(previous_user_query or "").strip()
    previous_answer = str(previous_assistant_answer or "").strip()
    has_previous = bool(previous_user)

    if has_previous and (
        is_followup_query(original, has_conversation_context=True)
        or is_financial_risk_query(original)
    ):
        contextual = build_contextual_query(original, previous_user, previous_answer)
        retrieval_query = contextual
        is_followup = True
    else:
        contextual = original
        retrieval_query = original
        is_followup = False

    return FollowupResolution(
        is_followup_query=is_followup,
        original_query=original,
        contextual_query=contextual,
        previous_user_query=previous_user,
        previous_assistant_answer=previous_answer,
        retrieval_query=retrieval_query,
    )


def try_followup_safe_answer(
    current_query: str,
    retrieval_query: str,
    previous_user_query: str | None,
    previous_assistant_answer: str | None,
) -> str | None:
    if not previous_user_query or not is_followup_query(current_query):
        return None

    normalized_current = re.sub(r"\s+", "", current_query)
    combined_prev = _combined_topic_text(previous_user_query or "", previous_assistant_answer or "")

    financial = detect_financial_risk_query(current_query)
    if financial:
        return financial[1]

    if contains_any(normalized_current, BACKEND_ACTION_FOLLOWUP_KEYWORDS):
        if is_post_ship_refund_query(retrieval_query) or contains_any(
            combined_prev, POST_SHIP_TOPIC_CONTEXT_KEYWORDS
        ):
            return DEMO_CANNOT_OPERATE_BACKEND_ANSWER

    if contains_any(normalized_current, COMPENSATION_FOLLOWUP_KEYWORDS):
        if (
            is_glue_quality_query(retrieval_query)
            or is_wrong_item_query(retrieval_query)
            or contains_any(combined_prev, QUALITY_TOPIC_CONTEXT_KEYWORDS)
        ):
            return COMPENSATION_REQUEST_SAFE_ANSWER

    return None


def followup_debug_info(followup: FollowupResolution) -> dict[str, str | bool]:
    return {
        "original_query": followup.original_query,
        "is_followup_query": followup.is_followup_query,
        "contextual_query": followup.contextual_query,
        "previous_user_query": followup.previous_user_query,
        "retrieval_query": followup.retrieval_query,
    }


def apply_domain_rerank_rules(
    user_question: str,
    row,
    similarity: float,
    rerank_score: float,
    reasons: list[str],
) -> float:
    combined = row_combined_text(row)
    category = normalize_category(row.get("category", ""))
    source_type = str(row.get("source_type", "chat_qa")).strip()

    if is_slip_resistance_query(user_question):
        if contains_any(combined, SLIP_CONTENT_KEYWORDS):
            rerank_score += 0.22
            reasons.append("slip_match+0.22")
        if category == CATEGORY_SIZE and contains_any(combined, RAIN_SHOE_SIZE_KEYWORDS + ["\u96e8\u978b"]):
            rerank_score -= 0.28
            reasons.append("rain_shoe_size_penalty-0.28")

    if is_post_ship_refund_query(user_question):
        if contains_any(combined, POST_SHIP_CONTENT_KEYWORDS):
            rerank_score += 0.24
            reasons.append("post_ship_rule+0.24")
        if contains_any(combined, FREIGHT_ONLY_KEYWORDS) and not contains_any(
            combined, ["\u62e6\u622a", "\u62d2\u6536", "\u5546\u54c1\u53d1\u51fa"]
        ):
            rerank_score -= 0.22
            reasons.append("freight_only_penalty-0.22")
        if is_generic_return_only_row(row):
            rerank_score -= 0.30
            reasons.append("generic_return_penalty-0.30")

    if is_foot_discomfort_query(user_question):
        if source_type != "chat_qa" and contains_any(combined, FOOT_SAFE_SNIPPET_KEYWORDS):
            rerank_score += 0.28
            reasons.append("foot_safe_snippet+0.28")
        if is_foot_transition_qa_row(row):
            rerank_score -= 0.24
            reasons.append("foot_transition_qa-0.24")

    return rerank_score


def try_conservative_topic_answer(user_question: str, answer_context: list) -> str | None:
    if is_wrong_item_query(user_question):
        if not answer_context:
            return WRONG_ITEM_SAFE_ANSWER
        top_row = answer_context[0][0]
        if str(top_row.get("source_type", "chat_qa")).strip() == "chat_qa":
            return WRONG_ITEM_SAFE_ANSWER
        if is_risky_chat_qa_row(top_row):
            return WRONG_ITEM_SAFE_ANSWER
    if is_glue_quality_query(user_question):
        if not answer_context:
            return GLUE_QUALITY_SAFE_ANSWER
        top_row = answer_context[0][0]
        if str(top_row.get("source_type", "chat_qa")).strip() == "chat_qa":
            return GLUE_QUALITY_SAFE_ANSWER
        if is_risky_chat_qa_row(top_row):
            return GLUE_QUALITY_SAFE_ANSWER
    if is_foot_discomfort_query(user_question):
        if not answer_context:
            return FOOT_DISCOMFORT_SAFE_ANSWER
        top_row = answer_context[0][0]
        source_type = str(top_row.get("source_type", "chat_qa")).strip()
        answer = row_answer_text(top_row)
        if source_type == "chat_qa" or not contains_any(answer, FOOT_SAFE_SNIPPET_KEYWORDS):
            return FOOT_DISCOMFORT_SAFE_ANSWER
    if is_post_ship_refund_query(user_question):
        return POST_SHIP_REFUND_SAFE_ANSWER
    return None


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def normalize_standalone_vague_query(user_question: str) -> str:
    """Normalize only syntax that cannot add a concrete business object."""

    normalized = str(user_question or "").casefold()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[，。！？!?、,.…~～；;：:\"'“”‘’（）()【】\[\]]+", "", normalized)
    return re.sub(r"[啊呀呢吧嘛呐哦喔啦哈]+$", "", normalized)


def is_standalone_vague_query(
    user_question: str,
    has_conversation_context: bool = False,
) -> bool:
    if has_conversation_context:
        return False
    normalized = normalize_standalone_vague_query(user_question)
    if normalized in STANDALONE_VAGUE_EXACT_FORMS:
        return True
    return any(
        normalized == f"{prefix}{action}"
        for prefix in STANDALONE_VAGUE_PREFIXES
        for action in STANDALONE_VAGUE_ACTION_FORMS
    )


def is_standalone_ambiguous_delivery_location_query(
    user_question: str,
    has_conversation_context: bool = False,
) -> bool:
    if has_conversation_context:
        return False
    normalized = normalize_standalone_vague_query(user_question)
    return normalized in STANDALONE_AMBIGUOUS_DELIVERY_LOCATION_FORMS


def _format_centimeters(value: float) -> str:
    return f"{value:g}"


def _chinese_integer_to_arabic(token: str) -> int | None:
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if token == "十":
        return 10
    if "十" in token:
        tens, ones = token.split("十", 1)
        tens_value = 1 if not tens else digits.get(tens)
        ones_value = 0 if not ones else digits.get(ones)
        if tens_value is None or ones_value is None:
            return None
        return tens_value * 10 + ones_value
    if len(token) == 1:
        return digits.get(token)
    return None


def _normalize_chinese_measurement_numbers(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = _chinese_integer_to_arabic(match.group(1))
        return str(value) if value is not None else match.group(1)

    return re.sub(
        r"([零〇一二两三四五六七八九十]{1,3})(?=厘米|公分|毫米|cm|mm)",
        replace,
        text,
    )


def _convert_foot_length_value(value: float, unit: str) -> float:
    return value / 10.0 if unit in {"mm", "毫米"} else value


def _valid_foot_length_cm(value: float) -> bool:
    # Deliberately broad enough for children's and adult footwear.
    return FOOT_LENGTH_MIN_CM <= value <= FOOT_LENGTH_MAX_CM


def _invalid_measurement_hint(value: float, unit: str) -> str:
    if unit in {"厘米", "cm", "公分"} and 100 <= value <= 350:
        intended = value / 10.0
        return (
            f"请确认“{value:g}{unit}”是否想表达{value:g}毫米"
            f"（{intended:g}厘米）？确认后我再结合当前商品尺码表提供参考。"
        )
    if unit in {"毫米", "mm"} and 10 <= value <= 35:
        return (
            f"请确认“{value:g}{unit}”是否想表达{value:g}厘米"
            f"（{value * 10:g}毫米）？确认后我再结合当前商品尺码表提供参考。"
        )
    return (
        f"脚长“{value:g}{unit}”超出可合理核对的范围，请检查数值和单位后重试，"
        "例如填写24厘米或240毫米。"
    )


def _build_foot_length_parse(
    values_cm: list[float],
    *,
    unit_inferred: bool,
    uncertain: bool,
    is_range: bool,
) -> FootLengthParse:
    if not values_cm:
        return FootLengthParse(status="not_found")
    if not all(_valid_foot_length_cm(value) for value in values_cm):
        return FootLengthParse(
            status="invalid",
            values_cm=tuple(values_cm),
            unit_inferred=unit_inferred,
            uncertain=uncertain,
            is_range=is_range,
            correction_hint=(
                "脚长数值超出可合理核对的范围，请检查数值和单位后重试，"
                "例如填写24厘米或240毫米。"
            ),
        )
    values = tuple(round(value, 3) for value in values_cm)
    return FootLengthParse(
        status="valid",
        normalized_cm=max(values),
        values_cm=values,
        unit_inferred=unit_inferred,
        uncertain=uncertain,
        is_range=is_range,
    )


def parse_foot_length_expression(
    text: str,
    *,
    expecting_foot_length: bool = False,
) -> FootLengthParse:
    """Normalize deterministic foot-length expressions without LLM reasoning."""

    normalized = re.sub(r"\s+", "", str(text or "")).casefold()
    normalized = _normalize_chinese_measurement_numbers(normalized)
    if not normalized:
        return FootLengthParse(status="not_found")
    uncertainty = contains_any(
        normalized,
        ["大概", "差不多", "左右", "约", "不准", "不太准", "之间"],
    )

    range_match = re.search(
        r"(?<![\d.])(\d+(?:\.\d+)?)(?:到|至|[-~～])"
        r"(\d+(?:\.\d+)?)(厘米|公分|毫米|cm|mm)(?![a-z])",
        normalized,
    )
    if range_match:
        first, second = float(range_match.group(1)), float(range_match.group(2))
        unit = range_match.group(3)
        values = [_convert_foot_length_value(first, unit), _convert_foot_length_value(second, unit)]
        if not all(_valid_foot_length_cm(value) for value in values):
            return FootLengthParse(
                status="invalid",
                values_cm=tuple(values),
                uncertain=True,
                is_range=True,
                correction_hint=_invalid_measurement_hint(max(first, second), unit),
            )
        return _build_foot_length_parse(
            values,
            unit_inferred=False,
            uncertain=True,
            is_range=True,
        )

    explicit = re.findall(
        r"(?<![\d.])(\d+(?:\.\d+)?)(厘米|公分|毫米|cm|mm)(?![a-z])",
        normalized,
    )
    if explicit:
        values: list[float] = []
        for raw_value, unit in explicit:
            value = float(raw_value)
            converted = _convert_foot_length_value(value, unit)
            if not _valid_foot_length_cm(converted):
                return FootLengthParse(
                    status="invalid",
                    values_cm=(converted,),
                    uncertain=uncertainty,
                    correction_hint=_invalid_measurement_hint(value, unit),
                )
            values.append(converted)
        return _build_foot_length_parse(
            values,
            unit_inferred=False,
            uncertain=uncertainty or any(value % 0.5 != 0 for value in values),
            is_range=len(values) > 1,
        )

    has_foot_context = contains_any(normalized, ["脚长", "脚是", "左脚", "右脚"])
    if not expecting_foot_length and not has_foot_context:
        return FootLengthParse(status="not_found")

    bare_values: list[float] = []
    is_range = False
    bare_range = re.search(
        r"(\d+(?:\.\d+)?)(?:到|至|[-~～])(\d+(?:\.\d+)?)",
        normalized,
    )
    if bare_range:
        bare_values = [float(bare_range.group(1)), float(bare_range.group(2))]
        is_range = True
    elif "左脚" in normalized and "右脚" in normalized:
        left = re.search(r"左脚(?:长|是|约)?(\d+(?:\.\d+)?)", normalized)
        right = re.search(r"右脚(?:长|是|约)?(\d+(?:\.\d+)?)", normalized)
        if left and right:
            bare_values = [float(left.group(1)), float(right.group(1))]
    elif has_foot_context:
        contextual = re.search(
            r"(?:脚长|脚是)(?:是|为|约|大概|有|[:：])?(\d+(?:\.\d+)?)",
            normalized,
        )
        if contextual:
            bare_values = [float(contextual.group(1))]
    elif expecting_foot_length:
        numbers = re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])", normalized)
        if len(numbers) == 1:
            bare_values = [float(numbers[0])]

    if not bare_values:
        return FootLengthParse(status="not_found")

    inferred_cm: list[float] = []
    for value in bare_values:
        if FOOT_LENGTH_MIN_CM <= value <= FOOT_LENGTH_MAX_CM:
            inferred_cm.append(value)
        elif 100 <= value <= FOOT_LENGTH_MAX_CM * 10:
            inferred_cm.append(value / 10.0)
        else:
            return FootLengthParse(
                status="ambiguous",
                unit_inferred=True,
                uncertain=uncertainty or is_range,
                is_range=is_range,
                correction_hint=FOOT_LENGTH_CLARIFICATION,
            )
    return _build_foot_length_parse(
        inferred_cm,
        unit_inferred=True,
        uncertain=(
            uncertainty
            or is_range
            or any(value % 0.5 != 0 for value in inferred_cm)
        ),
        is_range=is_range or len(inferred_cm) > 1,
    )


def _extract_usual_shoe_size(text: str) -> float | None:
    normalized = re.sub(r"\s+", "", str(text or "")).casefold()
    patterns = (
        r"(?:平时|平常|通常)(?:穿|是)?(\d{2}(?:\.\d+)?)码?",
        r"(?:耐克|运动鞋|皮鞋)(?:平时)?穿(\d{2}(?:\.\d+)?)码?",
        r"(?:另一款|上一双|以前买.{0,8})(\d{2}(?:\.\d+)?)码?",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            value = float(match.group(1))
            if 20 <= value <= 55:
                return value
    return None


def _extract_foot_shape(text: str) -> tuple[str | None, bool | None]:
    normalized = re.sub(r"\s+", "", str(text or "")).casefold()
    if contains_any(normalized, ["脚比较宽", "脚宽", "脚胖", "宽脚"]):
        width = "wide"
    elif contains_any(normalized, ["脚很瘦", "脚瘦", "窄脚"]):
        width = "slim"
    else:
        width = None
    high_instep = True if contains_any(normalized, ["脚背高", "高脚背"]) else None
    return width, high_instep


def _is_size_recommendation_query(text: str) -> bool:
    normalized = re.sub(r"\s+", "", str(text or "")).casefold()
    return contains_any(
        normalized,
        [
            "穿多大",
            "穿几码",
            "多少码",
            "多大码",
            "买几码",
            "什么码",
            "怎么选",
            "选尺码",
            "推荐个尺码",
            "适合穿",
            "这个穿多少",
            "这款也",
        ],
    )


def _is_product_fit_query(text: str) -> bool:
    normalized = re.sub(r"\s+", "", str(text or "")).casefold()
    return contains_any(
        normalized,
        ["偏大", "偏小", "标准码", "大一码", "小一码", "尺码一样", "版型"],
    )


def _trusted_product_fit_answer(state: ConversationState) -> str | None:
    if state.size_product_fit_source not in TRUSTED_SIZE_DATA_SOURCES:
        return None
    fit_labels = {
        "narrow": "偏窄",
        "wide": "偏宽",
        "large": "偏大",
        "small": "偏小",
        "standard": "标准",
    }
    label = fit_labels.get(state.size_product_fit)
    if not label:
        return None
    return (
        f"商家商品资料显示当前商品版型为{label}。这只适用于该商品；"
        "请同时核对商品详情页尺码表，并结合脚长、脚宽和脚背情况选择。"
    )


def _size_from_authoritative_chart(
    foot_length_cm: float,
    state: ConversationState,
) -> tuple[str, str] | None:
    charts: tuple[tuple[tuple[float, float, str], ...], str] = (
        (state.size_product_size_chart, state.size_product_size_chart_source),
        (MERCHANT_APPROVED_GENERIC_SIZE_CHART, "merchant_approved_generic"),
    )
    for chart, source in charts:
        if not chart:
            continue
        if source != "merchant_approved_generic" and source not in TRUSTED_SIZE_DATA_SOURCES:
            continue
        for entry in chart:
            if len(entry) != 3:
                continue
            lower, upper, size_label = entry
            if float(lower) <= foot_length_cm <= float(upper):
                return str(size_label), source
    return None


def _measurement_display(parsed: FootLengthParse) -> str:
    if parsed.is_range and len(parsed.values_cm) > 1:
        return "–".join(_format_centimeters(value) for value in parsed.values_cm)
    return _format_centimeters(parsed.normalized_cm or 0.0)


def _has_meaningful_size_conflict(
    foot_length_cm: float,
    usual_shoe_size: float,
    chart_result: tuple[str, str] | None,
) -> bool:
    if chart_result:
        try:
            return abs(float(chart_result[0]) - usual_shoe_size) >= 3.0
        except ValueError:
            return False
    # The product requirement explicitly identifies <=24 cm with >=41 as a
    # clearly suspicious pair. This is a correction guard, not a size mapping.
    return foot_length_cm <= 24.0 and usual_shoe_size >= 41.0


def _base_size_guidance_answer(
    parsed: FootLengthParse,
    state: ConversationState,
    *,
    usual_shoe_size: float | None,
) -> str:
    display = _measurement_display(parsed)
    chart_result = _size_from_authoritative_chart(parsed.normalized_cm or 0.0, state)
    if chart_result:
        size_label, source = chart_result
        source_label = "当前商品的商家尺码表" if source != "merchant_approved_generic" else "商家批准的通用尺码表"
        answer = (
            f"按{source_label}，脚长{display}厘米可先参考{size_label}码。"
            "这是初步参考，请再核对当前商品详情页的尺码表和版型说明。"
        )
    else:
        answer = (
            f"已记录脚长{display}厘米。当前可用资料中没有可验证的脚长与鞋码对照表，"
            "暂时无法可靠推荐具体码数；请以当前商品详情页尺码表和版型说明为准。"
        )

    if parsed.uncertain or parsed.is_range:
        answer += (
            "该测量值带有范围、误差或临界可能，请不要直接四舍五入；"
            "可复测较长一只脚，并结合脚宽、高脚背、袜子厚度和松紧偏好判断。"
        )
    if usual_shoe_size is not None:
        if _has_meaningful_size_conflict(
            parsed.normalized_cm or 0.0,
            usual_shoe_size,
            chart_result,
        ):
            answer += (
                f"您还提供了常穿{usual_shoe_size:g}码，这与脚长信息存在明显不一致风险；"
                "建议重新测量脚长并以当前商品尺码表核对后再决定。"
            )
        else:
            answer += (
                f"常穿{usual_shoe_size:g}码可作为补充信息，但不同品牌和鞋款不能直接等同。"
            )
    return answer


def decide_size_consultation(
    user_question: str,
    conversation_state: ConversationState | dict | None = None,
    business_now: datetime | None = None,
) -> SizeConsultationDecision:
    state = coerce_conversation_state(conversation_state)
    question = str(user_question or "").strip()
    normalized = re.sub(r"\s+", "", question).casefold()
    parsed = parse_foot_length_expression(
        question,
        expecting_foot_length=state.size_awaiting_foot_length,
    )
    usual_size = _extract_usual_shoe_size(question)
    foot_width, high_instep = _extract_foot_shape(question)
    asks_size = _is_size_recommendation_query(question)
    asks_fit = _is_product_fit_query(question)
    has_shape = foot_width is not None or high_instep is not None
    explicit_size_context = contains_any(normalized, ["脚长", "尺码", "鞋码", "脚是"])
    standalone_numeric_ambiguity = bool(
        re.fullmatch(r"(?:大概|差不多|约)?\d+(?:\.\d+)?(?:左右)?[？?。！!]?", normalized)
    )
    aftersales_size_operation = contains_any(
        normalized,
        ["尺码不合适", "换货", "退货", "换码", "改码", "申请换"],
    )
    matched = (
        parsed.status != "not_found"
        or asks_size
        or asks_fit
        or has_shape
        or (state.size_awaiting_foot_length and bool(question))
        or (state.size_foot_length_cm is not None and (asks_fit or has_shape))
        or explicit_size_context
        or standalone_numeric_ambiguity
    )
    if aftersales_size_operation and parsed.status == "not_found" and not has_shape:
        matched = False
    if not matched:
        return SizeConsultationDecision(matched=False)

    if standalone_numeric_ambiguity and parsed.status == "not_found":
        return SizeConsultationDecision(
            matched=True,
            query_type="size_measurement_clarification",
            answer=(
                f"请问“{question.strip('？?。！! ')}”是指脚长（厘米/毫米）、鞋码，"
                "还是其他信息？"
            ),
            foot_length=parsed,
            awaiting_foot_length=False,
        )

    if parsed.status in {"invalid", "ambiguous"}:
        return SizeConsultationDecision(
            matched=True,
            query_type="size_measurement_clarification",
            answer=parsed.correction_hint or FOOT_LENGTH_CLARIFICATION,
            foot_length=parsed,
            usual_shoe_size=usual_size,
            foot_width=foot_width,
            high_instep=high_instep,
            awaiting_foot_length=True,
        )

    if asks_fit:
        trusted_fit = _trusted_product_fit_answer(state)
        if trusted_fit:
            return SizeConsultationDecision(
                matched=True,
                query_type="size_consultation",
                answer=trusted_fit,
                foot_length=parsed,
                usual_shoe_size=usual_size,
                foot_width=foot_width,
                high_instep=high_instep,
            )
        known_facts: list[str] = []
        if state.size_foot_length_cm is not None:
            known_facts.append(f"脚长{state.size_foot_length_cm:g}厘米")
        if state.size_usual_shoe_size is not None:
            known_facts.append(f"常穿{state.size_usual_shoe_size:g}码")
        answer = SIZE_FIT_UNKNOWN_ANSWER
        if known_facts:
            answer += f"已记录{'、'.join(known_facts)}，但这些信息不能替代当前商品的版型证据。"
        return SizeConsultationDecision(
            matched=True,
            query_type="size_fit_unknown",
            answer=answer,
            foot_length=parsed,
            usual_shoe_size=usual_size,
            foot_width=foot_width,
            high_instep=high_instep,
            awaiting_foot_length=state.size_foot_length_cm is None,
        )

    effective_parsed = parsed
    if parsed.status == "not_found" and state.size_foot_length_cm is not None:
        effective_parsed = FootLengthParse(
            status="valid",
            normalized_cm=state.size_foot_length_cm,
            values_cm=state.size_foot_length_values_cm or (state.size_foot_length_cm,),
            uncertain=state.size_measurement_uncertain,
            is_range=len(state.size_foot_length_values_cm) > 1,
        )

    if has_shape and effective_parsed.status == "valid":
        display = _measurement_display(effective_parsed)
        answer = (
            f"已记录脚长{display}厘米及您的脚型信息。脚宽、脚背高度与脚长是不同维度，"
            "不能据此固定大一码；请结合当前商品详情页尺码表和版型说明判断。"
        )
        if state.size_product_fit_source in TRUSTED_SIZE_DATA_SOURCES:
            fit_answer = _trusted_product_fit_answer(state)
            if fit_answer:
                answer += fit_answer
        decision = SizeConsultationDecision(
            matched=True,
            query_type="size_consultation",
            answer=answer,
            foot_length=effective_parsed,
            usual_shoe_size=usual_size,
            foot_width=foot_width,
            high_instep=high_instep,
        )
    elif effective_parsed.status == "valid":
        answer = _base_size_guidance_answer(
            effective_parsed,
            state,
            usual_shoe_size=usual_size or state.size_usual_shoe_size,
        )
        decision = SizeConsultationDecision(
            matched=True,
            query_type="size_consultation",
            answer=answer,
            foot_length=effective_parsed,
            usual_shoe_size=usual_size,
            foot_width=foot_width,
            high_instep=high_instep,
        )
    else:
        prefix = "仅凭其他品牌或鞋款的常穿码不能推定当前商品尺码。" if usual_size else ""
        if has_shape:
            prefix += "脚宽或高脚背不能机械地换算为大一码。"
        decision = SizeConsultationDecision(
            matched=True,
            query_type="size_clarification",
            answer=f"{prefix}{FOOT_LENGTH_CLARIFICATION}",
            foot_length=parsed,
            usual_shoe_size=usual_size,
            foot_width=foot_width,
            high_instep=high_instep,
            awaiting_foot_length=True,
        )

    if is_prospective_shipping_policy_query(question):
        shipping_answer = answer_for_prospective_shipping_policy(
            question,
            business_now=business_now,
        )
        return SizeConsultationDecision(
            matched=decision.matched,
            query_type="size_and_shipping_policy",
            answer=f"{decision.answer} {shipping_answer or ''}".strip(),
            foot_length=decision.foot_length,
            usual_shoe_size=decision.usual_shoe_size,
            foot_width=decision.foot_width,
            high_instep=decision.high_instep,
            awaiting_foot_length=decision.awaiting_foot_length,
        )
    if is_existing_order_shipping_status_query(question):
        return SizeConsultationDecision(
            matched=decision.matched,
            query_type="size_and_backend_handoff",
            answer=f"{decision.answer} {BACKEND_REQUIRED_ANSWER}",
            foot_length=decision.foot_length,
            usual_shoe_size=decision.usual_shoe_size,
            foot_width=decision.foot_width,
            high_instep=decision.high_instep,
            awaiting_foot_length=decision.awaiting_foot_length,
        )
    explicit_size_backend_action = bool(
        re.search(r"(?:帮我|给我|替我).{0,12}(?:改|换).{0,8}\d{2}码", normalized)
        or re.search(r"(?:这单|当前订单|订单).{0,8}(?:改|换).{0,8}\d{2}码", normalized)
    )
    if explicit_size_backend_action or is_aftersales_operation_request(question):
        return SizeConsultationDecision(
            matched=decision.matched,
            query_type="size_and_backend_handoff",
            answer=f"{decision.answer} {AFTERSALES_OPERATION_SAFE_ANSWER}",
            foot_length=decision.foot_length,
            usual_shoe_size=decision.usual_shoe_size,
            foot_width=decision.foot_width,
            high_instep=decision.high_instep,
            awaiting_foot_length=decision.awaiting_foot_length,
        )
    refund_status = contains_any(normalized, ["退款", "返款"]) and contains_any(
        normalized, ["到账", "进度", "处理到哪", "退了吗"]
    )
    exchange_status = "换货" in normalized and contains_any(
        normalized, ["进度", "处理到哪", "到哪了", "完成了吗"]
    )
    if refund_status or exchange_status:
        boundary = (
            REFUND_STATUS_OR_AMOUNT_SAFE_ANSWER
            if refund_status
            else "当前换货进度需要结合订单售后记录核验；请查看订单页或联系人工客服确认。"
        )
        return SizeConsultationDecision(
            matched=decision.matched,
            query_type="size_and_backend_handoff",
            answer=f"{decision.answer} {boundary}",
            foot_length=decision.foot_length,
            usual_shoe_size=decision.usual_shoe_size,
            foot_width=decision.foot_width,
            high_instep=decision.high_instep,
            awaiting_foot_length=decision.awaiting_foot_length,
        )
    general_policy_markers = ["怎么", "如何", "流程", "申请", "规则", "政策"]
    secondary_policy_query: str | None = None
    if contains_any(normalized, ["退货", "退款"]) and contains_any(
        normalized, general_policy_markers
    ):
        secondary_policy_query = "退款流程是什么"
    elif "换货" in normalized and contains_any(normalized, general_policy_markers):
        secondary_policy_query = "尺码不合适怎么申请换货"
    if secondary_policy_query:
        return SizeConsultationDecision(
            matched=decision.matched,
            query_type="size_and_policy_retrieval",
            answer=decision.answer,
            foot_length=decision.foot_length,
            usual_shoe_size=decision.usual_shoe_size,
            foot_width=decision.foot_width,
            high_instep=decision.high_instep,
            awaiting_foot_length=decision.awaiting_foot_length,
            secondary_policy_query=secondary_policy_query,
        )
    return decision


def answer_for_foot_length_size_query(user_question: str) -> str | None:
    """Compatibility wrapper around the structured size-consultation decision."""

    decision = decide_size_consultation(user_question)
    if (
        not decision.matched
        or decision.foot_length is None
        or decision.foot_length.status == "not_found"
    ):
        return None
    return decision.answer


def is_existing_order_shipping_status_query(user_question: str) -> bool:
    normalized = re.sub(r"\s+", "", str(user_question or "")).casefold()
    patterns = (
        r"(?:我)?(?:已经|已)下单",
        r"我的订单.{0,12}(?:发货|什么时候发|发了吗|发了没)",
        r"订单.{0,8}(?:还没|未).{0,4}发货",
        r"帮我查.{0,10}(?:什么时候发|发货)",
        r"订单.{0,8}(?:已经|已)付款.{0,10}(?:今天|什么时候).{0,6}(?:能)?发(?:货|吗)",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def is_prospective_shipping_policy_query(user_question: str) -> bool:
    normalized = re.sub(r"\s+", "", str(user_question or "")).casefold()
    if is_existing_order_shipping_status_query(normalized):
        return False
    shipping_time_expression = (
        r"(?:大概)?什么时候(?:能|可以)?发(?:货)?|多久(?:能|可以)?发货"
    )
    patterns = (
        rf"(?:我)?现在下单.{{0,12}}(?:{shipping_time_expression})",
        rf"今天下单.{{0,12}}(?:{shipping_time_expression})",
        rf"现在拍.{{0,12}}(?:{shipping_time_expression})",
        r"(?:我)?现在下单.{0,8}(?:今天|当天)(?:能|可以)?发(?:货)?",
        r"现在拍.{0,8}(?:今天|当天)(?:能|可以)?发(?:货)?",
        r"今天下单.{0,8}(?:(?:能|可以)?(?:当天|今天)?发(?:货)?|(?:当天|今天)(?:能|可以)?发(?:货)?)",
        r"(?:\d{1,2}点|几点)前下单.{0,12}(?:当天|今天).{0,6}(?:能|可以)?发(?:货|吗)",
        r"几点前下单.{0,12}(?:可以|能)?当天发货",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def is_explicit_dispatch_cutoff_query(user_question: str) -> bool:
    normalized = re.sub(r"\s+", "", str(user_question or "")).casefold()
    return bool(
        re.search(r"(?:几点|什么时候|\d{1,2}点)前.{0,8}下单", normalized)
        or re.search(r"下单.{0,8}(?:截止|最晚).{0,6}(?:几点|什么时候)", normalized)
    )


def answer_for_prospective_shipping_policy(
    user_question: str,
    *,
    business_now: datetime | None = None,
) -> str | None:
    """Return time-aware policy guidance for a future purchase only.

    The injected clock must be timezone-aware. Runtime calls use an explicit
    Asia/Shanghai clock and never consult the operating-system timezone.
    """

    if not is_prospective_shipping_policy_query(user_question):
        return None
    normalized = re.sub(r"\s+", "", str(user_question or "")).casefold()
    if contains_any(normalized, ["预售", "预定", "预订"]):
        return PROSPECTIVE_PREORDER_ANSWER
    if is_explicit_dispatch_cutoff_query(user_question):
        return PROSPECTIVE_SHIPPING_CUTOFF_ANSWER

    current = business_now or datetime.now(BUSINESS_TIMEZONE)
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("business_now must be timezone-aware")
    shanghai_now = current.astimezone(BUSINESS_TIMEZONE)
    local_time = time(
        shanghai_now.hour,
        shanghai_now.minute,
        shanghai_now.second,
        shanghai_now.microsecond,
    )
    if local_time < PROSPECTIVE_DISPATCH_CUTOFF:
        return PROSPECTIVE_SHIPPING_BEFORE_CUTOFF_ANSWER
    return PROSPECTIVE_SHIPPING_AFTER_CUTOFF_ANSWER


def detect_policy_category(user_question: str) -> str | None:
    normalized = re.sub(r"\s+", "", user_question)
    for category in POLICY_CATEGORY_PRIORITY:
        if contains_any(normalized, POLICY_CATEGORY_KEYWORDS[category]):
            return category
    return None


def decide_p0_s1_answer_route(
    user_question: str,
    has_conversation_context: bool = False,
    conversation_state: ConversationState | dict | None = None,
    size_decision: SizeConsultationDecision | None = None,
    business_now: datetime | None = None,
) -> AnswerRouteDecision:
    """Route only the P0-S1 shipping/refund/exchange slice.

    Questions outside these three domains retain the legacy product path.
    """

    normalized = re.sub(r"\s+", "", str(user_question or "").strip()).casefold()
    if not normalized:
        return AnswerRouteDecision(
            route=AnswerRoute.CLARIFY_THEN_ANSWER,
            domain=None,
            clarification_question="请问您想咨询发货、退款还是换货问题？",
            reason="empty_input",
        )

    size_decision = size_decision or decide_size_consultation(
        user_question,
        conversation_state,
        business_now=business_now,
    )
    if size_decision.matched:
        if size_decision.query_type in {
            "size_clarification",
            "size_measurement_clarification",
        }:
            return AnswerRouteDecision(
                route=AnswerRoute.CLARIFY_THEN_ANSWER,
                domain=None,
                clarification_question=size_decision.answer,
                reason=size_decision.query_type,
            )
        if size_decision.query_type == "size_and_backend_handoff":
            return AnswerRouteDecision(
                route=AnswerRoute.FULL_HANDOFF,
                domain="shipping",
                needs_realtime_status=True,
                reason=size_decision.query_type,
            )
        if size_decision.query_type == "size_and_policy_retrieval":
            policy_domain = (
                "exchange"
                if size_decision.secondary_policy_query and "换货" in size_decision.secondary_policy_query
                else "refund"
            )
            return AnswerRouteDecision(
                route=AnswerRoute.DIRECT_ANSWER,
                domain=policy_domain,
                has_policy_facet=True,
                policy_query=size_decision.secondary_policy_query,
                reason=size_decision.query_type,
            )
        return AnswerRouteDecision(
            route=AnswerRoute.DIRECT_ANSWER,
            domain="shipping" if size_decision.query_type == "size_and_shipping_policy" else None,
            has_policy_facet=size_decision.query_type == "size_and_shipping_policy",
            reason=size_decision.query_type,
        )

    if is_standalone_ambiguous_delivery_location_query(
        user_question,
        has_conversation_context,
    ):
        return AnswerRouteDecision(
            route=AnswerRoute.CLARIFY_THEN_ANSWER,
            domain=None,
            clarification_question=AMBIGUOUS_DELIVERY_LOCATION_CLARIFICATION,
            reason="standalone_ambiguous_delivery_location",
        )

    if is_standalone_vague_query(user_question, has_conversation_context):
        return AnswerRouteDecision(
            route=AnswerRoute.CLARIFY_THEN_ANSWER,
            domain=None,
            clarification_question=STANDALONE_VAGUE_CLARIFICATION,
            reason="standalone_vague_query",
        )

    if normalized in {"退", "退款", "换", "换货", "发货"}:
        clarification = (
            "请问您想咨询退货流程、退款进度，还是其他售后问题？"
            if "退" in normalized
            else "请问您想了解一般流程、当前处理状态，还是需要人工执行操作？"
        )
        return AnswerRouteDecision(
            route=AnswerRoute.CLARIFY_THEN_ANSWER,
            domain=None,
            clarification_question=clarification,
            reason="short_or_object_only_input",
        )

    if (
        "客服" in normalized
        and contains_any(normalized, ["没回", "未回", "不回复"])
        and contains_any(normalized, ["物流", "快递"])
        and contains_any(normalized, ["没更新", "未更新", "不更新"])
    ):
        return AnswerRouteDecision(
            route=AnswerRoute.CLARIFY_THEN_ANSWER,
            domain=None,
            clarification_question="请问您主要想确认人工客服回复进度，还是订单物流是否更新？",
            reason="customer_service_or_logistics_ambiguity",
        )

    prospective_shipping = is_prospective_shipping_policy_query(normalized)
    existing_order_shipping = is_existing_order_shipping_status_query(normalized)
    domains: list[str] = []
    shipping = (
        prospective_shipping
        or existing_order_shipping
        or contains_any(normalized, ["发货", "物流", "快递", "催发"])
    )
    refund = contains_any(normalized, ["退款", "退钱", "返款", "到账"])
    exchange = contains_any(normalized, ["换货", "换码", "改码", "换尺码"]) or bool(
        re.search(r"(?:改成|换成)\d{2}码", normalized)
    )
    if shipping:
        domains.append("shipping")
    if refund:
        domains.append("refund")
    if exchange:
        domains.append("exchange")

    if len(domains) > 1:
        return AnswerRouteDecision(
            route=AnswerRoute.CLARIFY_THEN_ANSWER,
            domain=None,
            clarification_question="请问您这次主要想处理发货、退款还是换货中的哪一项？",
            reason="multiple_p0_s1_domains",
        )
    if not domains:
        return AnswerRouteDecision(route=AnswerRoute.DIRECT_ANSWER, domain=None)
    domain = domains[0]

    backend_action = False
    if domain == "shipping":
        backend_action = bool(
            re.search(r"(?:帮我|请|麻烦).{0,6}(?:催|催促).{0,6}发货", normalized)
            or contains_any(normalized, ["帮我催发货", "催一下发货", "催促发货"])
        )
    elif domain == "refund":
        backend_action = contains_any(normalized, ["帮我退款", "给我退款", "立即退款"])
    elif domain == "exchange":
        backend_action = bool(
            re.search(r"(?:帮我|请|麻烦|把这单).{0,10}(?:改成|换成)\d{2}码", normalized)
            or re.search(r"(?:修改|更改).{0,6}(?:尺码|码数)", normalized)
        )

    general_markers = ["一般", "通常", "流程", "怎么", "如何", "申请", "规则", "政策", "多久"]
    has_policy_facet = (
        prospective_shipping
        or (
            contains_any(normalized, general_markers)
            and not existing_order_shipping
        )
    ) and not backend_action
    specific_order = existing_order_shipping or contains_any(
        normalized, ["我的", "我这", "这单", "当前订单", "订单现在"]
    )

    if domain == "shipping":
        status_signal = contains_any(
            normalized,
            ["什么时候发货", "发货了吗", "还没发货", "发了没", "处理到哪", "状态", "没更新"],
        )
        if prospective_shipping:
            needs_realtime = False
        elif existing_order_shipping:
            needs_realtime = True
        else:
            needs_realtime = status_signal and (specific_order or not has_policy_facet)
        policy_query = "一般多久发货"
    elif domain == "refund":
        status_signal = contains_any(
            normalized,
            ["到账", "进度", "处理到哪", "退款了吗", "退了吗", "退款状态"],
        )
        explicit_general_policy = contains_any(
            normalized, ["一般", "通常", "流程", "怎么", "如何", "申请", "规则", "政策"]
        )
        needs_realtime = status_signal and (specific_order or not explicit_general_policy)
        policy_query = "退款流程是什么"
    else:
        status_signal = contains_any(
            normalized,
            ["处理到哪", "进度", "换好了吗", "完成了吗", "换货状态", "现在处理"],
        )
        needs_realtime = status_signal and (specific_order or not has_policy_facet)
        policy_query = "尺码不合适怎么申请换货"

    if prospective_shipping:
        route = AnswerRoute.DIRECT_ANSWER
        reason = "prospective_shipping_policy"
    elif backend_action:
        route = AnswerRoute.FULL_HANDOFF
        reason = "backend_action_required"
    elif has_policy_facet and needs_realtime:
        route = AnswerRoute.POLICY_PLUS_HANDOFF
        reason = "policy_and_realtime_facets"
    elif needs_realtime:
        route = AnswerRoute.FULL_HANDOFF
        reason = "realtime_status_required"
    else:
        route = AnswerRoute.DIRECT_ANSWER
        reason = "general_policy"

    return AnswerRouteDecision(
        route=route,
        domain=domain,
        has_policy_facet=has_policy_facet,
        needs_realtime_status=needs_realtime,
        needs_backend_action=backend_action,
        policy_query=policy_query if has_policy_facet else None,
        reason=reason,
    )


def answer_for_p0_s1_route(decision: AnswerRouteDecision) -> str:
    if decision.route is AnswerRoute.CLARIFY_THEN_ANSWER:
        return decision.clarification_question or "请问您想咨询哪一项具体问题？"
    if decision.route is not AnswerRoute.FULL_HANDOFF:
        return ""
    if decision.needs_backend_action:
        if decision.domain == "exchange":
            return (
                "当前系统没有后台执行能力，不能直接修改这笔订单的尺码；"
                "请先在订单页查看是否可修改，若无法操作请联系人工客服处理。"
            )
        if decision.domain == "shipping":
            return (
                "当前系统没有后台执行能力，不能直接催促发货；"
                "请先查看订单页的预计发货信息，仍需处理时请联系人工客服。"
            )
        return (
            "当前系统没有后台执行能力，不能直接为订单发起退款；"
            "请在订单页申请售后，或联系人工客服处理。"
        )
    if decision.domain == "refund":
        return (
            "我无法查询当前退款进度或是否到账；请先查看订单页的退款记录，"
            "如仍不明确请联系人工客服核验。"
        )
    if decision.domain == "exchange":
        return (
            "我无法查询当前换货处理状态；请先查看订单页的售后进度，"
            "如仍不明确请联系人工客服核验。"
        )
    return (
        "我无法查询当前订单的实时发货状态；请先查看订单页的预计发货信息，"
        "如仍不明确请联系人工客服核验。"
    )


def p0_s1_status_handoff_boundary(decision: AnswerRouteDecision) -> str:
    if decision.domain == "refund":
        return "这笔订单是否已经退款到账我无法查询，请以订单页记录为准，必要时联系人工客服核验。"
    if decision.domain == "exchange":
        return "这笔订单当前的换货进度我无法查询，请以订单页售后记录为准，必要时联系人工客服核验。"
    return "这笔订单当前是否已经发货我无法查询，请以订单页记录为准，必要时联系人工客服核验。"


def invalid_input_guard(user_question: str) -> tuple[bool, str | None]:
    stripped = user_question.strip()
    if not stripped:
        return True, INVALID_INPUT_ANSWER

    compact = re.sub(r"\s+", "", stripped)
    if compact == "\u4eba\u5de5" or is_business_query(compact):
        return False, None

    effective_chars = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]", compact)
    if len(effective_chars) < 2:
        return True, INVALID_INPUT_ANSWER

    has_chinese = bool(re.search(r"[\u4e00-\u9fff]", compact))
    if not has_chinese:
        return True, INVALID_INPUT_ANSWER

    return False, None


def is_business_query(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text)
    return contains_any(normalized, BUSINESS_QUERY_KEYWORDS)


def intent_guard(
    user_question: str,
    has_conversation_context: bool = False,
    conversation_state: ConversationState | dict | None = None,
    size_decision: SizeConsultationDecision | None = None,
    business_now: datetime | None = None,
) -> tuple[bool, str, str | None]:
    normalized = re.sub(r"\s+", "", user_question.strip()).casefold()
    if not normalized:
        return False, "normal", None

    if contains_any(normalized, IDENTITY_QUERY_KEYWORDS):
        return True, "identity", IDENTITY_ANSWER

    if contains_any(normalized, HUMAN_HANDOVER_KEYWORDS):
        return True, "human_handover", HUMAN_HANDOVER_ANSWER

    route_decision = decide_p0_s1_answer_route(
        user_question,
        has_conversation_context=has_conversation_context,
        conversation_state=conversation_state,
        size_decision=size_decision,
        business_now=business_now,
    )
    if route_decision.reason in {
        "size_consultation",
        "size_clarification",
        "size_measurement_clarification",
        "size_fit_unknown",
        "size_and_shipping_policy",
        "size_and_backend_handoff",
    }:
        size_decision = size_decision or decide_size_consultation(
            user_question,
            conversation_state,
            business_now=business_now,
        )
        return True, route_decision.reason, size_decision.answer
    if route_decision.reason == "prospective_shipping_policy":
        return (
            True,
            "prospective_shipping_policy",
            answer_for_prospective_shipping_policy(
                user_question,
                business_now=business_now,
            ),
        )
    if route_decision.domain is not None or route_decision.route is AnswerRoute.CLARIFY_THEN_ANSWER:
        if route_decision.route is AnswerRoute.CLARIFY_THEN_ANSWER:
            return True, "unclear", answer_for_p0_s1_route(route_decision)
        if route_decision.route is AnswerRoute.FULL_HANDOFF:
            return True, "backend_required", answer_for_p0_s1_route(route_decision)
        if route_decision.has_policy_facet:
            return False, "normal", None

    if requires_backend_api(user_question):
        return True, "backend_required", BACKEND_REQUIRED_ANSWER

    if contains_any(normalized, ABUSIVE_OR_IRRELEVANT_KEYWORDS):
        return True, "abusive_or_emotional", ABUSIVE_OR_IRRELEVANT_ANSWER

    if is_business_query(user_question):
        return False, "normal", None

    if normalized in UNCLEAR_SHORT_KEYWORDS:
        # In this minimal demo there is no multi-turn memory, so short context
        # questions such as "what does this mean?" should ask for clarification.
        return True, "unclear", UNCLEAR_ANSWER

    if len(normalized) <= 4 and re.fullmatch(r"[\u4e00-\u9fff]{2,4}", normalized):
        unclear_chars = ["\u610f\u601d", "\u610f\u5473"]
        if contains_any(normalized, unclear_chars):
            return True, "unclear", UNCLEAR_ANSWER

    return False, "normal", None


def is_product_attribute_query(user_question: str) -> bool:
    normalized = re.sub(r"\s+", "", user_question)
    return contains_any(normalized, PRODUCT_ATTRIBUTE_KEYWORDS)


def is_soft_hard_sole_query(user_question: str) -> bool:
    normalized = re.sub(r"\s+", "", user_question)
    return (
        "\u978b\u5e95" in normalized
        and (
            "\u8f6f\u5e95" in normalized
            or "\u786c\u5e95" in normalized
            or "\u8f6f\u786c" in normalized
            or ("\u8f6f" in normalized and "\u786c" in normalized)
        )
    )


def detect_query_type(
    user_question: str,
    backend_required: bool | None = None,
    policy_category: str | None = None,
    domain_query: str | None = None,
) -> str:
    skip_retrieval, guarded_type, _answer = intent_guard(user_question)
    if skip_retrieval:
        return guarded_type
    effective_query = str(domain_query or user_question)
    if backend_required is None:
        backend_required = requires_backend_api(user_question)
    if backend_required:
        return "backend_required"
    if is_product_attribute_query(effective_query):
        return "product_attribute"
    if policy_category is None:
        policy_category = detect_policy_category(effective_query)
    if policy_category:
        return "general_policy"
    return "normal"


def requires_backend_api(user_question: str) -> bool:
    normalized = re.sub(r"\s+", "", user_question)
    if is_prospective_shipping_policy_query(normalized):
        return False
    if is_existing_order_shipping_status_query(normalized):
        return True
    if any(re.search(pattern, normalized) for pattern in LIVE_LOGISTICS_STATUS_PATTERNS):
        return True
    if contains_any(normalized, BACKEND_API_REQUIRED_KEYWORDS):
        return True
    backend_patterns = [
        r"(?:\u7269\u6d41|\u5feb\u9012).{0,6}(?:\u54ea|\u54ea\u91cc|\u5230\u54ea|\u5230\u4e86\u6ca1|\u5230\u6ca1|\u67e5|\u67e5\u8be2)",
        r"(?:\u8ba2\u5355).{0,6}(?:\u72b6\u6001|\u53d1\u8d27|\u53d1\u4e86|\u7269\u6d41)",
        r"(?:\u552e\u540e|\u9000\u6b3e|\u8865\u507f|\u8fd4\u6b3e).{0,6}(?:\u8fdb\u5ea6|\u5230\u8d26|\u5230\u4e86\u6ca1|\u5230\u6ca1|\u5904\u7406\u5230\u54ea)",
        r"(?:\u50ac).{0,6}(?:\u5feb\u9012|\u7269\u6d41|\u53d1\u8d27|\u6d3e\u9001)",
        r"(?:\u4eca\u5929|\u660e\u5929).{0,4}(?:\u80fd\u5230|\u5230\u5417|\u9001\u5230)",
    ]
    return any(re.search(pattern, normalized) for pattern in backend_patterns)


def has_context_dependent_answer(answer: str) -> bool:
    if contains_any(answer, CONTEXT_DEPENDENT_ANSWER_TERMS):
        return True
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:\u5143|\u5757|\u5757\u94b1)", answer))


def has_standard_policy_answer(answer: str) -> bool:
    return contains_any(answer, STANDARD_POLICY_ANSWER_TERMS)


def rerank_retrieved_results(user_question: str, retrieved_results: list) -> tuple[list, str | None]:
    policy_category = detect_policy_category(user_question)
    backend_query = requires_backend_api(user_question)
    domain_query = any(
        [
            is_slip_resistance_query(user_question),
            is_post_ship_refund_query(user_question),
            is_foot_discomfort_query(user_question),
        ]
    )
    if not policy_category and not domain_query and not backend_query:
        return retrieved_results, None

    reranked = []
    for original_rank, (row, similarity) in enumerate(retrieved_results, start=1):
        category = normalize_category(row["category"])
        question = str(row["question"]).strip()
        answer = row_answer_text(row)
        combined = question + "\uff1b" + answer
        rerank_score = similarity
        reasons = []

        rerank_score = apply_domain_rerank_rules(
            user_question, row, similarity, rerank_score, reasons
        )

        if policy_category:
            if category == policy_category:
                rerank_score += 0.14
                reasons.append("same_category+0.14")
            elif category and category != CATEGORY_OTHER:
                rerank_score -= 0.08
                reasons.append("different_category-0.08")
            if has_standard_policy_answer(answer):
                rerank_score += 0.12
                reasons.append("standard_policy+0.12")
            if has_context_dependent_answer(answer):
                rerank_score -= 0.15
                reasons.append("context_dependent-0.15")
            if contains_any(combined, POLICY_CATEGORY_KEYWORDS[policy_category]):
                rerank_score += 0.04
                reasons.append("keyword_match+0.04")

        priority = int(row.get("priority", DEFAULT_QA_PRIORITY) or DEFAULT_QA_PRIORITY)
        priority_bonus = max(0.0, (priority - DEFAULT_QA_PRIORITY) / 500.0)
        if priority_bonus:
            rerank_score += priority_bonus
            reasons.append(f"priority+{priority_bonus:.3f}")
        source_type = str(row.get("source_type", "")).strip()
        if source_type != "chat_qa":
            rerank_score += 0.03
            reasons.append("knowledge_snippet+0.03")
        if backend_query:
            if row_is_backend_only(row):
                rerank_score += 0.10
                reasons.append("backend_match+0.10")
        elif row_is_backend_only(row):
            rerank_score -= 0.18
            reasons.append("backend_only-0.18")
        if is_risky_chat_qa_row(row):
            rerank_score -= 0.30
            reasons.append("risky_chat_qa-0.30")

        reranked.append(
            {
                "row": row,
                "similarity": similarity,
                "rerank_score": rerank_score,
                "original_rank": original_rank,
                "rerank_reason": ";".join(reasons) if reasons else "embedding_only",
            }
        )

    reranked.sort(key=lambda item: (item["rerank_score"], item["similarity"], -item["original_rank"]), reverse=True)
    return [(item["row"], item["similarity"], item) for item in reranked], policy_category


def build_rag_prompt(
    user_question: str,
    retrieved_results: Iterable[tuple],
    query_type: str = "normal",
    backend_required: bool = False,
    contextual_query: str | None = None,
    is_followup: bool = False,
) -> str:
    context_blocks = []
    for rank, result in enumerate(retrieved_results, start=1):
        row, score = result[0], result[1]
        meta = result[2] if len(result) > 2 else {}
        rerank_score = meta.get("rerank_score", score)
        rerank_reason = meta.get("rerank_reason", "embedding_only")
        answer_text = str(row.get("answer_or_content", row.get("answer", ""))).strip()
        context_blocks.append(
            "\n".join(
                [
                    f"[{rank}] similarity={score:.4f} rerank_score={rerank_score:.4f}",
                    f"rerank_reason: {rerank_reason}",
                    f"source_type: {row.get('source_type', 'chat_qa')}",
                    f"needs_backend_api: {row_needs_backend_api(row)}",
                    f"category: {row['category']}",
                    f"title: {row.get('title', row['question'])}",
                    f"question: {row['question']}",
                    f"answer: {answer_text}",
                ]
            )
        )
    context = "\n\n".join(context_blocks) if context_blocks else "(empty)"
    product_attribute_rule = ""
    if query_type == "product_attribute":
        product_attribute_rule = (
            "\n\u989d\u5916\u91cd\u8981\u89c4\u5219\uff1a\u7528\u6237\u5f53\u524d\u95ee\u7684"
            "\u662f\u5546\u54c1\u5c5e\u6027\u3002Final answer must be concise. "
            "\u53ea\u7528 1-2 \u53e5\u56de\u7b54\u5546\u54c1\u5c5e\u6027\uff0c\u5fc5\u987b"
            "\u5ffd\u7565\u4fc3\u5355\u3001\u8fd0\u8d39\u9669\u3001\u7269\u6d41\u53d1\u8d27\u3001"
            "\u552e\u540e\u9000\u6362\u3001\u8865\u507f\u3001\u8ba2\u5355\u72b6\u6001\u7b49"
            "\u65e0\u5173\u5185\u5bb9\u3002"
        )
    backend_rule = ""
    if backend_required:
        backend_rule = (
            "\n10. \u7528\u6237\u95ee\u9898\u9700\u8981\u67e5\u8be2\u8ba2\u5355/\u7269\u6d41/\u9000\u6b3e\u7b49\u5b9e\u65f6\u4fe1\u606f\u3002"
            "\u53ea\u80fd\u8bf4\u660e\u5f53\u524d\u65e0\u6cd5\u76f4\u63a5\u67e5\u8be2\u540e\u53f0\uff0c\u5efa\u8bae\u8f6c\u4eba\u5de5\u5ba2\u670d\u6838\u5b9e\uff1b"
            "\u7981\u6b62\u7f16\u9020\u8fdb\u5ea6\u3001\u91d1\u989d\u3001\u5230\u8d26\u6216\u5904\u7406\u72b6\u6001\u3002"
        )
    else:
        backend_rule = (
            "\n10. \u6807\u8bb0 needs_backend_api=true \u6216 source_type=backend_rule \u7684 context "
            "\u4e0d\u80fd\u7528\u6765\u627f\u8bfa\u5177\u4f53\u8ba2\u5355\u72b6\u6001\u3001\u8865\u507f\u91d1\u989d\u3001"
            "\u9000\u6b3e/\u5230\u8d26\u8fdb\u5ea6\u6216\u7269\u6d41\u7ed3\u8bba\u3002"
        )
    followup_rule = ""
    if is_followup and contextual_query and contextual_query != user_question:
        followup_rule = (
            f"\n\u8865\u5145\uff1a\u7528\u6237\u5f53\u524d\u662f\u5728\u8ffd\u95ee\u4e0a\u4e00\u8f6e\u8bdd\u9898\u3002"
            f"\u4e0a\u4e0b\u6587\u68c0\u7d22\u4e3b\u9898\uff1a{contextual_query}"
            f"\n\u8bf7\u7ed3\u5408\u8be5\u8bdd\u9898\u56de\u7b54\u7528\u6237\u7684\u7b80\u77ed\u8ffd\u95ee\u300c{user_question}\u300d\u3002"
        )
    return f"""\u4f60\u662f\u4eac\u4e1c\u5e97\u94fa\u5ba2\u670d\u52a9\u624b\u3002\u8bf7\u53ea\u57fa\u4e8e\u4e0b\u9762\u68c0\u7d22\u5230\u7684\u5386\u53f2\u5ba2\u670d QA \u4e0e\u5ba1\u6838\u8fc7\u7684\u8bdd\u672f\u77e5\u8bc6\u5e93\u56de\u7b54\u7528\u6237\u5f53\u524d\u95ee\u9898\u3002

\u786c\u6027\u8981\u6c42\uff1a
1. final answer \u5fc5\u987b\u57fa\u4e8e\u68c0\u7d22 context\uff0c\u4e0d\u5141\u8bb8\u7f16\u9020\u672a\u51fa\u73b0\u5728 context \u91cc\u7684\u552e\u540e\u653f\u7b56\u3001\u4ef7\u683c\u3001\u65f6\u6548\u3001\u627f\u8bfa\u3001\u8865\u507f\u91d1\u989d\u6216\u7269\u6d41\u7ed3\u8bba\u3002
2. \u53ea\u56de\u7b54\u7528\u6237\u5f53\u524d\u95ee\u7684\u70b9\uff0c\u4e0d\u8981\u628a\u591a\u4e2a retrieved answers \u751f\u786c\u62fc\u63a5\uff0c\u4e0d\u8981\u987a\u5e26\u6269\u5c55\u672a\u88ab\u95ee\u5230\u7684\u5185\u5bb9\u3002
3. \u5982\u679c retrieved answer \u4e2d\u5305\u542b\u4e0e\u5f53\u524d\u95ee\u9898\u65e0\u5173\u7684\u5185\u5bb9\uff0c\u5fc5\u987b\u5ffd\u7565\uff1a\u4fc3\u5355\u8bdd\u672f\uff08\u5efa\u8bae\u73b0\u5728\u62cd\u4e0b\u3001\u5c3d\u5feb\u4e0b\u5355\uff09\u3001\u8fd0\u8d39\u9669\u3001\u7269\u6d41\u53d1\u8d27\u3001\u552e\u540e\u9000\u6362\u3001\u8865\u507f\u91d1\u989d\u3001\u8ba2\u5355\u72b6\u6001\u7b49\u3002
4. \u5982\u679c\u7528\u6237\u95ee\u7684\u662f\u5546\u54c1\u5c5e\u6027\uff0c\u4f8b\u5982\u900f\u6c14\u3001\u9632\u6ed1\u3001\u8f6f\u5e95\u3001\u786c\u5e95\u3001\u6750\u8d28\u3001\u52a0\u7ed2\uff0c\u53ea\u56de\u7b54\u5546\u54c1\u5c5e\u6027\uff1b\u4e0d\u4e3b\u52a8\u6269\u5c55\u5230\u9000\u6362\u8d27\u3001\u8fd0\u8d39\u9669\u3001\u53d1\u8d27\u3001\u4fc3\u5355\u3002
5. final answer \u63a7\u5236\u5728 1-3 \u53e5\u8bdd\uff0c\u8bed\u6c14\u81ea\u7136\u3001\u7b80\u6d01\u3001\u9002\u5408\u5ba2\u670d\u573a\u666f\uff0c\u4f46\u4e0d\u8981\u8fc7\u5ea6\u8425\u9500\u3002
6. \u5982\u679c context \u53ea\u80fd\u652f\u6301\u90e8\u5206\u56de\u7b54\uff0c\u5c31\u53ea\u56de\u7b54\u80fd\u786e\u8ba4\u7684\u90e8\u5206\u3002\u5982\u679c context \u4e0d\u80fd\u652f\u6301\u660e\u786e\u56de\u7b54\uff0c\u8bf7\u56de\u590d\uff1a{LOW_CONFIDENCE_ANSWER}
7. \u4e0d\u8981\u53ea\u76f2\u76ee\u590d\u5236 Top 1\uff1b\u5bf9\u901a\u7528\u95ee\u9898\u4f18\u5148\u603b\u7ed3 context \u4e2d\u66f4\u901a\u7528\u3001\u66f4\u6807\u51c6\u653f\u7b56\u578b\u7684\u7b54\u6848\u3002\u5982\u679c retrieved answers \u76f8\u4e92\u51b2\u7a81\uff0c\u4f18\u5148\u4f7f\u7528\u66f4\u901a\u7528\u3001\u66f4\u4fdd\u5b88\u7684\u8bf4\u6cd5\u3002
8. \u5f53\u524d\u7cfb\u7edf\u6ca1\u6709\u63a5\u5165\u5e97\u94fa\u540e\u53f0 API\uff0c\u4e0d\u80fd\u67e5\u8be2\u5b9e\u65f6\u8ba2\u5355\u3001\u7269\u6d41\u3001\u9000\u6b3e\u6216\u552e\u540e\u72b6\u6001\uff1b\u4e0d\u8981\u58f0\u79f0\u5df2\u7ecf\u5e2e\u7528\u6237\u50ac\u4fc3\u6216\u5904\u7406\u3002
9. Final answer must be concise. Do not copy long retrieved answers directly. Ignore irrelevant sales, shipping, refund, compensation, logistics, and after-sales content unless the user explicitly asks about them. Do not include unrelated policies.
{backend_rule}
{product_attribute_rule}
{followup_rule}

\u7528\u6237\u95ee\u9898\uff1a
{user_question}

\u68c0\u7d22 context\uff1a
{context}

\u8bf7\u8f93\u51fa\u6700\u7ec8\u5ba2\u670d\u56de\u7b54\uff1a"""


def _normalize_greeting_text(text: str) -> str:
    return re.sub(r"[\s~～。；;，,！!？?…:·•\-~]+", "", str(text or ""))


def is_greeting_only_sentence(sentence: str) -> bool:
    compact = _normalize_greeting_text(sentence)
    if not compact:
        return True
    for phrase in GREETING_ONLY_PHRASES:
        if compact == _normalize_greeting_text(phrase):
            return True
    remainder = compact
    for phrase in sorted(GREETING_STRIP_PHRASES, key=len, reverse=True):
        remainder = remainder.replace(_normalize_greeting_text(phrase), "")
    return len(remainder) < 4


def strip_leading_greetings(sentence: str) -> str:
    text = str(sentence or "").strip()
    changed = True
    while changed and text:
        changed = False
        for phrase in sorted(GREETING_STRIP_PHRASES, key=len, reverse=True):
            pattern = re.compile(
                r"^" + re.escape(phrase) + r"[\s~～，,：:！!？?…]*",
                flags=re.IGNORECASE,
            )
            updated = pattern.sub("", text, count=1).strip()
            if updated != text:
                text = updated
                changed = True
                break
    return text.strip(" ，,。；;~～")


def cleanup_final_answer(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return text

    parts = re.split(r"[；;。\n\r]+", text)
    kept: list[str] = []
    for part in parts:
        sentence = part.strip(" ，,。；;~～")
        if not sentence:
            continue
        if is_greeting_only_sentence(sentence):
            continue
        cleaned = strip_leading_greetings(sentence)
        cleaned = cleaned.strip(" ，,。；;~～")
        if not cleaned or is_greeting_only_sentence(cleaned):
            continue
        kept.append(cleaned)

    if not kept:
        return text

    result = "\u3002".join(kept)
    result = re.sub(r"^(\u4eb2\u4eb2[\uff0c,]){2,}", "\u4eb2\u4eb2\uff0c", result)
    result = re.sub(r"^\u4eb2\u4eb2\uff0c\u4eb2\u4eb2", "\u4eb2\u4eb2", result)
    if not result.endswith(("\u3002", "\uff01", "\uff1f", "!", "?")):
        result += "\u3002"
    return result


def finalize_answer(answer: str) -> str:
    return cleanup_final_answer(answer)


BACKEND_SUCCESS_CLAIM_PATTERNS = (
    re.compile(r"(?:已经|已)(?:为您|帮您|替您)?.{0,3}(?:查询到|查询|查到)"),
    re.compile(r"(?:已经|已).{0,10}(?:修改|改成|换成).{0,10}(?:地址|尺码|码)"),
    re.compile(r"(?:已经|已)(?:为您|帮您|替您)?.{0,4}(?:退款|退回款项)"),
    re.compile(r"(?:退款|款项).{0,6}(?:已经|已)(?:到账|退回|完成)"),
    re.compile(r"(?:已经|已)(?:为您|帮您|替您)?.{0,4}(?:催促|催发货|催快递)"),
    re.compile(r"(?:已经|已)(?:为您|帮您|替您)?.{0,4}(?:补发|重发)"),
    re.compile(r"(?:换货|退货|退换货).{0,8}(?:已经|已).{0,4}(?:处理完成|完成|办结)"),
    re.compile(r"(?:已经|已).{0,6}(?:完成换货|办结换货)"),
)
WAREHOUSE_LOCATION_CLAIM_PATTERNS = (
    re.compile(
        r"(?:从|由)?(?:北京|上海|广州|深圳|杭州|成都|武汉|南京|天津|苏州|东莞)"
        r".{0,4}仓(?:库)?(?:发出|发货|直发)?"
    ),
    re.compile(r"仓库(?:位于|在)(?:北京|上海|广州|深圳|杭州|成都|武汉|南京|天津|苏州|东莞)"),
    re.compile(r"全国.{0,6}(?:个|处)仓(?:库)?"),
)
INSURANCE_ENDORSEMENT_CLAIM_PATTERNS = (
    re.compile(r"中国人保", flags=re.IGNORECASE),
    re.compile(r"\bPICC\b", flags=re.IGNORECASE),
    re.compile(r"正品险|正品保险|保险公司承保"),
)
COMMERCIAL_ELIGIBILITY_CLAIM_PATTERNS = (
    re.compile(r"(?:一定|肯定|确认|符合条件|审核通过)?.{0,4}(?:可以|能够|可直接)(?:办理|申请)?(?:退货|换货)"),
    re.compile(r"(?:退货|换货).{0,5}(?:一定|肯定)?(?:能办|可以办|没问题)"),
    re.compile(r"(?:不能|不可以|不予|无法)(?:办理|申请)?(?:退货|换货)"),
    re.compile(r"(?:不符合|符合)(?:退货|换货|售后)(?:条件|要求)"),
)
SECONDARY_SALE_CLAIM_PATTERNS = (
    re.compile(r"(?:不影响|没有影响|已影响|已经影响|影响了|会影响)(?:商品)?二次销售"),
    re.compile(r"(?:符合|不符合|满足|不满足)二次销售(?:条件|要求)?"),
)
ORDER_OPERATION_OUTCOME_CLAIM_PATTERNS = (
    re.compile(r"(?:退货|换货|退款|售后).{0,6}(?:已经|已)(?:批准|通过|受理)"),
    re.compile(r"(?:退货|换货|退款|售后).{0,8}(?:已被|已经|已)(?:拒绝|驳回|拒收)"),
    re.compile(r"(?:订单|这单).{0,5}(?:已经|已)(?:取消|关闭)"),
)
FEE_RESPONSIBILITY_CLAIM_PATTERNS = (
    re.compile(r"(?:退货|换货|售后)?.{0,6}(?:运费|邮费).{0,6}(?:由)?(?:卖家|商家|平台|买家|用户|您)(?:承担|支付|负责)"),
    re.compile(r"(?:卖家|商家|平台|买家|用户|您).{0,5}(?:承担|支付|负责).{0,4}(?:运费|邮费)"),
)
INSURANCE_COVERAGE_CLAIM_PATTERNS = (
    re.compile(r"(?:这单|订单|商品|本店).{0,5}(?:有|含有|包含|赠送|已投保)(?:运费险|正品险|保险)"),
    re.compile(r"(?:运费险|正品险).{0,4}(?:已经生效|可赔|会赔|负责赔付)"),
    re.compile(r"(?:运费险|保险).{0,6}(?:赔|报销|返还)\s*\d+(?:\.\d+)?\s*元"),
)
REFUND_FINANCIAL_OUTCOME_CLAIM_PATTERNS = (
    re.compile(r"退款.{0,5}(?:不会收|不收|免|没有)(?:取)?(?:手续费|处理费|服务费)"),
    re.compile(r"(?:款项|退款).{0,5}(?:会|将|可以)?全额(?:退回|退款|返还)"),
    re.compile(r"退款.{0,5}(?:会|将|要)?扣(?:除)?\s*\d+(?:\.\d+)?\s*元"),
)
QUALITY_OR_FAULT_CLAIM_PATTERNS = (
    re.compile(r"(?:这|该|就是|属于|确认是).{0,4}(?:质量问题|商品缺陷)"),
    re.compile(r"(?:卖家|商家|店铺).{0,4}(?:存在|属于|应负|负有).{0,4}(?:责任|过错)"),
    re.compile(r"(?:这是|属于|确认是)?(?:卖家|商家).{0,3}(?:发错|寄错|漏发).{0,8}(?:责任|负责|过错)"),
    re.compile(r"(?:发错|寄错|漏发).{0,8}(?:责任在|由).{0,3}(?:卖家|商家|店铺)"),
    re.compile(r"(?:这是|属于|确认是)?(?:卖家|商家|店铺).{0,3}(?:发错货|寄错货|漏发)"),
)
FALSE_ADVERTISING_CLAIM_PATTERNS = (
    re.compile(r"(?:卖家|商家|店铺).{0,5}(?:存在|属于|构成).{0,4}(?:虚假宣传|欺诈)"),
    re.compile(r"(?:这|该).{0,3}(?:就是|属于|构成)(?:虚假宣传|欺诈)"),
)
SAFE_CLAIM_CONTEXT_MARKERS = (
    "无法",
    "不能",
    "不可",
    "未能",
    "未",
    "尚未",
    "不会",
    "不应",
    "禁止",
    "不要",
    "是否",
    "确认是否",
    "需要确认",
    "需确认",
    "如已",
    "若已",
    "如果已经",
    "声称",
)


def _has_unqualified_claim(text: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    for pattern in patterns:
        for match in pattern.finditer(text):
            prefix_window = text[max(0, match.start() - 16):match.start()]
            if not contains_any(prefix_window, SAFE_CLAIM_CONTEXT_MARKERS):
                return True
    return False


def _claim_validation_boundary(
    blocked_claims: Iterable[str],
    route_decision: AnswerRouteDecision | None,
) -> list[str]:
    blocked = set(blocked_claims)
    boundaries: list[str] = []
    if "backend_success" in blocked:
        route_answer = answer_for_p0_s1_route(route_decision) if route_decision else ""
        boundaries.append(
            route_answer
            or (
                "当前系统没有后台查询或执行能力，无法确认动作已经完成；"
                "请通过订单页查看当前状态，必要时联系人工客服处理。"
            )
        )
    if "warehouse_location" in blocked:
        boundaries.append("具体发货仓库需以订单页实际信息为准，当前无法确认。")
    if "insurance_endorsement" in blocked:
        boundaries.append(
            "运费险或正品保障以当前商品详情页、订单页和店铺规则为准，"
            "当前无法确认具体承保机构。"
        )
    if blocked & {
        "commercial_eligibility",
        "secondary_sale_condition",
        "order_operation_outcome",
    }:
        boundaries.append(
            "是否符合退换货条件或相关申请是否获批，需要结合订单页规则、商品状态和后台记录核验。"
        )
    if "fee_responsibility" in blocked:
        boundaries.append(
            "退换货运费承担方式需要以订单页售后规则和实际保障情况为准，当前无法直接确认。"
        )
    if "insurance_coverage" in blocked:
        boundaries.append(
            "是否有运费险或其他保险保障，需要以当前商品详情页和订单页显示为准。"
        )
    if "refund_financial_outcome" in blocked:
        boundaries.append(
            "退款是否收取费用、是否全额退回或是否存在扣减，需要以订单页退款明细和当前规则核验。"
        )
    if blocked & {"quality_or_seller_fault", "false_advertising"}:
        boundaries.append(
            "是否属于质量问题、责任归属或描述不一致，需要结合商品、页面信息和相关凭证核验。"
        )
    return boundaries


def validate_final_answer_claims(
    answer: str,
    route_decision: AnswerRouteDecision | None = None,
    backend_receipt_verified: bool = False,
    canonical_support: Iterable[str] | None = None,
) -> ClaimValidationResult:
    """Block unsupported success, warehouse, and insurance claims.

    Trusted support is explicit and claim-scoped. Negative statements,
    capability boundaries, and questions about whether an action happened are
    not treated as success claims.
    """

    text = str(answer or "")
    supported = frozenset(canonical_support or ())
    chunks = [part for part in re.split(r"(?<=[。！？!?；;，,\n])", text) if part]
    kept: list[str] = []
    blocked: list[str] = []

    for chunk in chunks or [text]:
        chunk_claims: list[str] = []
        if not backend_receipt_verified and _has_unqualified_claim(
            chunk, BACKEND_SUCCESS_CLAIM_PATTERNS
        ):
            chunk_claims.append("backend_success")
        if "warehouse_location" not in supported and _has_unqualified_claim(
            chunk, WAREHOUSE_LOCATION_CLAIM_PATTERNS
        ):
            chunk_claims.append("warehouse_location")
        if "insurance_endorsement" not in supported and _has_unqualified_claim(
            chunk, INSURANCE_ENDORSEMENT_CLAIM_PATTERNS
        ):
            chunk_claims.append("insurance_endorsement")
        if "commercial_eligibility" not in supported and _has_unqualified_claim(
            chunk, COMMERCIAL_ELIGIBILITY_CLAIM_PATTERNS
        ):
            chunk_claims.append("commercial_eligibility")
        if "secondary_sale_condition" not in supported and _has_unqualified_claim(
            chunk, SECONDARY_SALE_CLAIM_PATTERNS
        ):
            chunk_claims.append("secondary_sale_condition")
        if not backend_receipt_verified and _has_unqualified_claim(
            chunk, ORDER_OPERATION_OUTCOME_CLAIM_PATTERNS
        ):
            chunk_claims.append("order_operation_outcome")
        if "fee_responsibility" not in supported and _has_unqualified_claim(
            chunk, FEE_RESPONSIBILITY_CLAIM_PATTERNS
        ):
            chunk_claims.append("fee_responsibility")
        if "insurance_coverage" not in supported and _has_unqualified_claim(
            chunk, INSURANCE_COVERAGE_CLAIM_PATTERNS
        ):
            chunk_claims.append("insurance_coverage")
        if "refund_financial_outcome" not in supported and _has_unqualified_claim(
            chunk, REFUND_FINANCIAL_OUTCOME_CLAIM_PATTERNS
        ):
            chunk_claims.append("refund_financial_outcome")
        if "quality_or_seller_fault" not in supported and _has_unqualified_claim(
            chunk, QUALITY_OR_FAULT_CLAIM_PATTERNS
        ):
            chunk_claims.append("quality_or_seller_fault")
        if "false_advertising" not in supported and _has_unqualified_claim(
            chunk, FALSE_ADVERTISING_CLAIM_PATTERNS
        ):
            chunk_claims.append("false_advertising")
        if chunk_claims:
            for claim_type in chunk_claims:
                if claim_type not in blocked:
                    blocked.append(claim_type)
        else:
            kept.append(chunk)

    if not blocked:
        return ClaimValidationResult(answer=text)

    safe_parts = [part.strip() for part in kept if part.strip()]
    safe_parts.extend(_claim_validation_boundary(blocked, route_decision))
    rewritten = finalize_answer("".join(safe_parts))
    return ClaimValidationResult(
        answer=rewritten or finalize_answer(SAFE_HUMAN_VERIFICATION_ANSWER),
        blocked_claims=tuple(blocked),
        rewritten=True,
    )


def filter_unverified_live_logistics_answer(
    answer: str,
    backend_access_verified: bool = False,
) -> tuple[str, bool]:
    """Replace unverified live tracking claims with the backend-safe boundary."""
    text = str(answer or "")
    if backend_access_verified:
        return text, False
    if contains_any(text, UNSAFE_LIVE_LOGISTICS_ANSWER_MARKERS):
        return finalize_answer(BACKEND_REQUIRED_ANSWER), True
    return text, False


def mock_llm_answer(
    user_question: str,
    retrieved_results: list,
    prompt: str,
    domain_query: str | None = None,
) -> str:
    del prompt
    effective_query = domain_query or user_question
    if not retrieved_results:
        return SAFE_HUMAN_VERIFICATION_ANSWER
    conservative = try_conservative_topic_answer(effective_query, retrieved_results)
    if conservative:
        return conservative
    top_row = retrieved_results[0][0]
    if is_risky_chat_qa_row(top_row):
        return SAFE_HUMAN_VERIFICATION_ANSWER
    answer = row_answer_text(top_row)
    return answer or SAFE_HUMAN_VERIFICATION_ANSWER


def clean_product_attribute_answer(answer: str) -> str:
    text = str(answer or "").strip()
    if not text:
        return LOW_CONFIDENCE_ANSWER
    parts = re.split(r"[；;。\n\r]+", text)
    kept = []
    for part in parts:
        sentence = part.strip(" ，,。；;")
        if not sentence:
            continue
        if is_greeting_only_sentence(sentence):
            continue
        sentence = strip_leading_greetings(sentence)
        if not sentence:
            continue
        if contains_any(sentence, IRRELEVANT_ATTRIBUTE_ANSWER_TERMS):
            continue
        kept.append(sentence)
        if len(kept) >= 2:
            break
    if not kept:
        return LOW_CONFIDENCE_ANSWER
    result = "\u4eb2\u4eb2\uff0c" + "\u3002".join(kept)
    if not result.endswith(("\u3002", "\uff01", "\uff1f", "!", "?")):
        result += "\u3002"
    return result


def product_attribute_fallback_answer(user_question: str, reranked_results: list) -> str:
    if is_soft_hard_sole_query(user_question):
        return SOFT_HARD_SOLE_ANSWER
    if reranked_results:
        row = reranked_results[0][0]
        return clean_product_attribute_answer(str(row.get("answer_or_content", row.get("answer", ""))))
    return LOW_CONFIDENCE_ANSWER


def call_deepseek_api(
    prompt: str,
    llm_config: LLMConfig,
    generation_config: GenerationConfig | None = None,
) -> str:
    if llm_config.client is None:
        raise RuntimeError("DeepSeek client is not initialized.")
    request = {
        "model": llm_config.model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "\u4f60\u662f\u4e25\u8c28\u7684\u4eac\u4e1c\u5ba2\u670d RAG \u52a9\u624b\u3002"
                    "\u5fc5\u987b\u53ea\u4f9d\u636e\u68c0\u7d22 context \u56de\u7b54\uff0c"
                    "\u4e0d\u5f97\u7f16\u9020\u653f\u7b56\u3001\u4ef7\u683c\u3001\u65f6\u6548\u3001"
                    "\u627f\u8bfa\u6216\u8865\u507f\u65b9\u6848\u3002"
                    "\u53ea\u56de\u7b54\u7528\u6237\u5f53\u524d\u95ee\u9898\uff0c"
                    "\u5ffd\u7565\u65e0\u5173\u7684\u4fc3\u5355\u3001\u8fd0\u8d39\u9669\u3001"
                    "\u7269\u6d41\u3001\u552e\u540e\u6216\u8865\u507f\u5185\u5bb9\uff0c"
                    "\u6700\u7ec8\u56de\u7b54\u63a7\u5236\u5728 1-3 \u53e5\u3002"
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    if generation_config is not None:
        request["temperature"] = generation_config.temperature
        if generation_config.top_p is not None:
            request["top_p"] = generation_config.top_p
        if generation_config.max_tokens is not None:
            request["max_tokens"] = generation_config.max_tokens
        request["stream"] = generation_config.stream
    response = llm_config.client.chat.completions.create(**request)
    return (response.choices[0].message.content or "").strip()


def generate_final_answer(
    user_question: str,
    original_results: list,
    reranked_results: list,
    low_confidence_threshold: float,
    llm_config: LLMConfig,
    backend_required: bool,
    query_type: str = "normal",
    retrieval_query: str | None = None,
    previous_user_query: str | None = None,
    previous_assistant_answer: str | None = None,
    is_followup: bool = False,
    contextual_query: str | None = None,
    generation_config: GenerationConfig | None = None,
) -> tuple[str, str]:
    domain_query = retrieval_query or user_question
    if not original_results:
        return finalize_answer(LOW_CONFIDENCE_ANSWER), ""
    answer_context = filter_results_for_answer_generation(
        reranked_results, backend_required, user_question=domain_query
    )
    prompt = build_rag_prompt(
        user_question,
        answer_context,
        query_type=query_type,
        backend_required=backend_required,
        contextual_query=contextual_query or domain_query,
        is_followup=is_followup,
    )
    followup_safe = try_followup_safe_answer(
        user_question,
        domain_query,
        previous_user_query,
        previous_assistant_answer,
    )
    if followup_safe:
        return finalize_answer(followup_safe), prompt
    financial_risk = detect_financial_risk_query(user_question)
    if financial_risk:
        return finalize_answer(financial_risk[1]), prompt
    if backend_required:
        return finalize_answer(BACKEND_REQUIRED_ANSWER), prompt
    conservative = try_conservative_topic_answer(domain_query, answer_context)
    if conservative:
        return finalize_answer(conservative), prompt
    if not answer_context:
        return finalize_answer(SAFE_HUMAN_VERIFICATION_ANSWER), prompt
    if query_type == "product_attribute" and is_soft_hard_sole_query(domain_query):
        return finalize_answer(SOFT_HARD_SOLE_ANSWER), prompt
    if original_results[0][1] < low_confidence_threshold:
        return finalize_answer(LOW_CONFIDENCE_ANSWER), prompt
    if llm_config.has_api_key and llm_config.client is not None:
        try:
            final_answer = call_deepseek_api(prompt, llm_config, generation_config)
            if final_answer:
                return finalize_answer(final_answer), prompt
            print("DeepSeek API returned empty content; fallback to mock.")
        except Exception as exc:  # noqa: BLE001
            print(f"DeepSeek API failed; fallback to mock. Error: {exc}")
    if query_type == "product_attribute":
        return finalize_answer(
            product_attribute_fallback_answer(domain_query, answer_context)
        ), prompt
    return finalize_answer(
        mock_llm_answer(user_question, answer_context, prompt, domain_query=domain_query)
    ), prompt


def coerce_conversation_state(
    value: ConversationState | dict | None,
    previous_user_query: str | None = None,
    previous_assistant_answer: str | None = None,
) -> ConversationState:
    """Return an isolated, validated state while preserving V2.1a compatibility."""
    if isinstance(value, ConversationState):
        state = ConversationState(**value.to_dict())
    elif isinstance(value, dict):
        defaults = ConversationState().to_dict()
        state = ConversationState(
            **{key: value.get(key, default) for key, default in defaults.items()}
        )
    else:
        state = ConversationState()

    if state.should_reset:
        state = ConversationState()
    if not state.last_user_query:
        state.last_user_query = str(previous_user_query or "").strip()
    if not state.last_assistant_answer:
        state.last_assistant_answer = str(previous_assistant_answer or "").strip()
    state.state_confidence = max(0.0, min(1.0, float(state.state_confidence or 0.0)))
    state.state_turn_count = max(0, int(state.state_turn_count or 0))
    state.updated_at_turn = max(0, int(state.updated_at_turn or 0))
    if state.size_foot_length_cm is not None:
        try:
            state.size_foot_length_cm = float(state.size_foot_length_cm)
        except (TypeError, ValueError):
            state.size_foot_length_cm = None
    try:
        state.size_foot_length_values_cm = tuple(
            float(item) for item in (state.size_foot_length_values_cm or ())
        )
    except (TypeError, ValueError):
        state.size_foot_length_values_cm = ()
    if state.size_usual_shoe_size is not None:
        try:
            state.size_usual_shoe_size = float(state.size_usual_shoe_size)
        except (TypeError, ValueError):
            state.size_usual_shoe_size = None
    normalized_chart: list[tuple[float, float, str]] = []
    for entry in state.size_product_size_chart or ():
        if not isinstance(entry, (list, tuple)) or len(entry) != 3:
            continue
        try:
            lower, upper = float(entry[0]), float(entry[1])
        except (TypeError, ValueError):
            continue
        label = str(entry[2]).strip()
        if lower <= upper and label:
            normalized_chart.append((lower, upper, label))
    state.size_product_size_chart = tuple(normalized_chart)
    state.service_requested_resolutions = tuple(
        str(item) for item in (state.service_requested_resolutions or ()) if str(item)
    )
    state.service_pending_clarification = tuple(
        str(item) for item in (state.service_pending_clarification or ()) if str(item)
    )
    state.service_supporting_context = tuple(
        str(item) for item in (state.service_supporting_context or ()) if str(item)
    )
    return state


def detect_conversation_topic(
    query: str,
    query_type: str,
    previous_topic: str = "none",
) -> str:
    normalized = re.sub(r"\s+", "", str(query or ""))
    if query_type in {"backend_required", "refund_status_or_amount_request"}:
        if "退款" in normalized or "返款" in normalized:
            return "refund_progress"
        if "订单" in normalized:
            return "order_status"
        if contains_any(
            normalized,
            ["物流", "快递", "到哪", "发货", "送到", "收到", "签收", "什么时候到", "一直不动", "还没到"],
        ):
            return "logistics_status"
        if previous_topic not in {"", "none"}:
            return previous_topic
        return "backend_operation"
    if query_type in FINANCIAL_RISK_QUERY_TYPES:
        return query_type.removesuffix("_request")
    if query_type == AFTERSALES_OPERATION_QUERY_TYPE:
        if contains_any(normalized, ["补发", "重发", "发新的"]):
            return "reshipment"
        if contains_any(normalized, ["换码", "换货", "换新"]):
            return "exchange_operation"
        if "备注" in normalized:
            return "backend_note"
        return previous_topic if previous_topic not in {"", "none"} else "aftersales_operation"
    if is_slip_resistance_query(normalized) or contains_any(normalized, ["防滑", "打滑", "下雨"]):
        return "anti_slip"
    if is_product_attribute_query(normalized):
        return "product_attribute"
    policy_category = detect_policy_category(normalized)
    if policy_category:
        return f"policy:{policy_category}"
    return previous_topic if previous_topic not in {"", "none"} else "general"


def safe_answer_type_for_query_type(query_type: str) -> str:
    if query_type == "backend_required":
        return "backend_required_answer"
    if query_type == AFTERSALES_OPERATION_QUERY_TYPE:
        return "aftersales_operation_safe_answer"
    if query_type in FINANCIAL_RISK_QUERY_TYPES:
        return f"{query_type}_safe_answer"
    if query_type in {"identity", "human_handover", "abusive_or_emotional", "unclear"}:
        return f"{query_type}_answer"
    return "none"


def inherit_backend_required_from_state(
    current_query: str,
    state: ConversationState,
) -> BackendRequiredInheritance | None:
    """Carry a recent live-data boundary across a short operational follow-up."""
    current = str(current_query or "").strip()
    normalized = re.sub(r"\s+", "", current)
    if not current or state.should_reset or not state.requires_backend_api:
        return None
    if state.query_type not in {
        "backend_required",
        "refund_status_or_amount_request",
        "size_and_backend_handoff",
    }:
        return None
    if state.state_confidence < 0.6 or state.state_turn_count > 3:
        return None
    if not (
        is_followup_query(current)
        or contains_any(normalized, BACKEND_STATE_FOLLOWUP_PHRASES)
    ):
        return None

    query_type = (
        "refund_status_or_amount_request"
        if state.query_type == "refund_status_or_amount_request"
        or state.current_topic == "refund_progress"
        else "backend_required"
    )
    safe_answer = (
        REFUND_STATUS_OR_AMOUNT_SAFE_ANSWER
        if query_type == "refund_status_or_amount_request"
        else BACKEND_REQUIRED_ANSWER
    )
    return BackendRequiredInheritance(
        query_type=query_type,
        safe_answer=safe_answer,
        current_topic=state.current_topic,
    )


def inherit_financial_risk_from_state(
    current_query: str,
    state: ConversationState,
) -> FinancialRiskInheritance | None:
    if (
        state.should_reset
        or state.risk_type != "financial"
        or state.query_type not in FINANCIAL_RISK_QUERY_TYPES
        or state.state_confidence < 0.6
        or state.state_turn_count > 3
        or not is_followup_query(current_query)
    ):
        return None
    safe_answer = FINANCIAL_SAFE_ANSWER_BY_TYPE.get(state.query_type)
    if not safe_answer:
        return None
    return FinancialRiskInheritance(
        query_type=state.query_type,
        safe_answer=safe_answer,
        inherited_from_previous_query=state.last_user_query,
    )


def inherit_aftersales_operation_from_state(
    current_query: str,
    state: ConversationState,
) -> AftersalesOperationInheritance | None:
    if (
        state.should_reset
        or state.risk_type != "aftersales_operation"
        or state.query_type != AFTERSALES_OPERATION_QUERY_TYPE
        or state.state_confidence < 0.6
        or state.state_turn_count > 3
    ):
        return None
    if not (
        is_followup_query(current_query)
        or is_aftersales_followup_query(current_query)
        or is_aftersales_operation_request(current_query)
    ):
        return None
    return AftersalesOperationInheritance(
        safe_answer=AFTERSALES_OPERATION_SAFE_ANSWER,
        inherited_from_previous_query=state.last_user_query,
    )


def _size_state_kwargs(state: ConversationState) -> dict[str, object]:
    return {
        "size_foot_length_cm": state.size_foot_length_cm,
        "size_foot_length_values_cm": state.size_foot_length_values_cm,
        "size_measurement_uncertain": state.size_measurement_uncertain,
        "size_usual_shoe_size": state.size_usual_shoe_size,
        "size_foot_width": state.size_foot_width,
        "size_high_instep": state.size_high_instep,
        "size_product_context": state.size_product_context,
        "size_product_fit": state.size_product_fit,
        "size_product_fit_source": state.size_product_fit_source,
        "size_product_size_chart": state.size_product_size_chart,
        "size_product_size_chart_source": state.size_product_size_chart_source,
        "size_awaiting_foot_length": state.size_awaiting_foot_length,
    }


def _update_size_consultation_state(
    previous_state: ConversationState,
    decision: SizeConsultationDecision,
    *,
    question: str,
    answer: str,
    query_type: str,
    contextual_query: str,
    next_turn: int,
    requires_backend: bool,
) -> ConversationState:
    state = ConversationState(**previous_state.to_dict())
    parsed = decision.foot_length
    if parsed and parsed.status == "valid" and parsed.normalized_cm is not None:
        state.size_foot_length_cm = parsed.normalized_cm
        state.size_foot_length_values_cm = parsed.values_cm or (parsed.normalized_cm,)
        state.size_measurement_uncertain = parsed.uncertain or parsed.is_range
    if decision.usual_shoe_size is not None:
        state.size_usual_shoe_size = decision.usual_shoe_size
    if decision.foot_width is not None:
        state.size_foot_width = decision.foot_width
    if decision.high_instep is not None:
        state.size_high_instep = decision.high_instep
    state.size_awaiting_foot_length = decision.awaiting_foot_length
    state.current_topic = "size_consultation"
    state.query_type = query_type
    state.risk_type = "backend_operation" if requires_backend else "none"
    state.requires_backend_api = requires_backend
    state.last_safe_answer_type = "none"
    state.last_user_query = question
    state.last_assistant_answer = answer
    state.last_contextual_query = contextual_query
    state.state_confidence = 0.9
    state.state_turn_count = (
        previous_state.state_turn_count + 1
        if previous_state.current_topic == "size_consultation"
        else 1
    )
    state.updated_at_turn = next_turn
    state.should_reset = False
    return state


def update_conversation_state(
    previous_state: ConversationState,
    result: dict,
    followup: FollowupResolution,
) -> ConversationState:
    """Update structured state from the authoritative result of the current turn."""
    query_type = str(result.get("query_type", "normal"))
    question = str(result.get("question", "")).strip()
    answer = str(result.get("final_answer", "")).strip()
    next_turn = previous_state.updated_at_turn + 1

    if query_type.startswith("size_"):
        size_decision = decide_size_consultation(question, previous_state)
        return _update_size_consultation_state(
            previous_state,
            size_decision,
            question=question,
            answer=answer,
            query_type=query_type,
            contextual_query=followup.contextual_query,
            next_turn=next_turn,
            requires_backend=bool(result.get("requires_backend_api")),
        )

    if query_type == "human_handover":
        return ConversationState(
            last_user_query=question,
            last_assistant_answer=answer,
            last_contextual_query=followup.contextual_query,
            updated_at_turn=next_turn,
            should_reset=True,
        )

    if query_type in {"identity", "abusive_or_emotional", "unclear"}:
        state = ConversationState(**previous_state.to_dict())
        state.last_user_query = question
        state.last_assistant_answer = answer
        state.last_contextual_query = followup.contextual_query
        state.state_confidence = max(0.0, state.state_confidence - 0.2)
        state.updated_at_turn = next_turn
        state.should_reset = False
        return state

    inherited = any(
        bool(result.get(flag))
        for flag in (
            "inherited_backend_required",
            "inherited_financial_risk",
            "inherited_aftersales_operation",
        )
    )
    topic = detect_conversation_topic(
        followup.retrieval_query or question,
        query_type,
        previous_state.current_topic if inherited else "none",
    )
    if query_type == AFTERSALES_OPERATION_QUERY_TYPE:
        risk_type = "aftersales_operation"
    elif query_type in FINANCIAL_RISK_QUERY_TYPES:
        risk_type = "financial"
    elif query_type == "backend_required":
        risk_type = "backend_operation"
    else:
        risk_type = "none"

    same_state = inherited or (
        topic == previous_state.current_topic
        and query_type == previous_state.query_type
        and topic not in {"", "none", "general"}
    )
    return ConversationState(
        current_topic=topic,
        query_type=query_type,
        risk_type=risk_type,
        requires_backend_api=bool(result.get("requires_backend_api")),
        last_safe_answer_type=safe_answer_type_for_query_type(query_type),
        last_user_query=question,
        last_assistant_answer=answer,
        last_retrieval_query=(
            previous_state.last_retrieval_query
            if result.get("skip_retrieval")
            else followup.retrieval_query
        ),
        last_contextual_query=followup.contextual_query,
        last_successful_contextual_query=(
            followup.contextual_query
            if not result.get("skip_retrieval") and answer
            else previous_state.last_successful_contextual_query
        ),
        state_confidence=(
            min(1.0, max(previous_state.state_confidence, 0.85) + 0.05)
            if inherited
            else (0.95 if risk_type != "none" or result.get("requires_backend_api") else 0.8)
        ),
        state_turn_count=previous_state.state_turn_count + 1 if same_state else 1,
        updated_at_turn=next_turn,
        should_reset=False,
        **_size_state_kwargs(previous_state),
    )


def run_rag_query(
    user_question: str,
    corpus,
    embeddings,
    embedding_model,
    top_k: int,
    cosine_similarity,
    low_confidence_threshold: float,
    llm_config: LLMConfig,
    previous_user_query: str | None = None,
    previous_assistant_answer: str | None = None,
    conversation_state: ConversationState | dict | None = None,
    generation_config: GenerationConfig | None = None,
    business_now: datetime | None = None,
) -> dict:
    question = str(user_question or "").strip()
    prior_state = coerce_conversation_state(
        conversation_state,
        previous_user_query=previous_user_query,
        previous_assistant_answer=previous_assistant_answer,
    )
    previous_user_query = previous_user_query or prior_state.last_user_query or None
    previous_assistant_answer = (
        previous_assistant_answer or prior_state.last_assistant_answer or None
    )
    has_conversation_context = bool(str(previous_user_query or "").strip())
    size_decision = decide_size_consultation(
        question,
        prior_state,
        business_now=business_now,
    )
    route_decision = decide_p0_s1_answer_route(
        question,
        has_conversation_context=has_conversation_context,
        conversation_state=prior_state,
        size_decision=size_decision,
        business_now=business_now,
    )
    followup = resolve_followup_context(
        question,
        previous_user_query=previous_user_query,
        previous_assistant_answer=previous_assistant_answer,
    )
    debug = followup_debug_info(followup)

    def finish(result: dict, state_update_reason: str) -> dict:
        result.setdefault("inherited_backend_required", False)
        result.setdefault("inherited_financial_risk", False)
        result.setdefault("inherited_aftersales_operation", False)
        result.setdefault("answer_route", route_decision.route.value)
        result.setdefault("answer_route_domain", route_decision.domain)
        result.setdefault("answer_route_reason", route_decision.reason)
        filtered_answer, blocked_live_logistics = filter_unverified_live_logistics_answer(
            result.get("final_answer", ""),
            backend_access_verified=bool(result.get("backend_access_verified", False)),
        )
        if blocked_live_logistics:
            result.update(
                {
                    "final_answer": filtered_answer,
                    "requires_backend_api": True,
                    "skip_retrieval": True,
                    "skip_llm": True,
                    "query_type": "backend_required",
                    "policy_category": None,
                    "original_results": [],
                    "reranked_results": [],
                    "unsafe_live_logistics_answer_filtered": True,
                }
            )
            state_update_reason = "unsafe_live_logistics_answer_filter"
        else:
            result.setdefault("unsafe_live_logistics_answer_filtered", False)
        claim_validation = validate_final_answer_claims(
            result.get("final_answer", ""),
            route_decision=route_decision,
            backend_receipt_verified=bool(result.get("backend_access_verified", False)),
            canonical_support=result.get("canonical_claim_support", ()),
        )
        result["final_answer"] = claim_validation.answer
        result["claim_validation_rewritten"] = claim_validation.rewritten
        result["blocked_claim_types"] = list(claim_validation.blocked_claims)
        if claim_validation.rewritten:
            state_update_reason = "final_claim_validation"
        result["conversation_state"] = update_conversation_state(
            prior_state, result, followup
        ).to_dict()
        result["state_update_reason"] = state_update_reason
        return result

    skip_retrieval, guarded_type, guarded_answer = intent_guard(
        question,
        has_conversation_context=has_conversation_context,
        conversation_state=prior_state,
        size_decision=size_decision,
        business_now=business_now,
    )
    if skip_retrieval:
        backend_required = guarded_type in {"backend_required", "size_and_backend_handoff"}
        preserve_policy_template = guarded_type in {
            "prospective_shipping_policy",
            "size_and_shipping_policy",
        }
        final_guarded_answer = (
            str(guarded_answer or "").strip()
            if preserve_policy_template
            else finalize_answer(guarded_answer or "")
        )
        return finish({
            "question": question,
            "final_answer": final_guarded_answer,
            "requires_backend_api": backend_required,
            "invalid_input": guarded_type == "unclear",
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": guarded_type,
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            "inherited_financial_risk": False,
            "inherited_from_previous_query": "",
            **debug,
        }, f"intent_guard:{guarded_type}")

    invalid_input, invalid_answer = invalid_input_guard(question)
    if invalid_input:
        return finish({
            "question": question,
            "final_answer": finalize_answer(invalid_answer or INVALID_INPUT_ANSWER),
            "requires_backend_api": False,
            "invalid_input": True,
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": "unclear",
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            "inherited_financial_risk": False,
            "inherited_from_previous_query": "",
            **debug,
        }, "invalid_input")

    financial_risk = detect_financial_risk_query(question)
    if financial_risk and route_decision.route is not AnswerRoute.POLICY_PLUS_HANDOFF:
        financial_query_type, financial_answer = financial_risk
        return finish({
            "question": question,
            "final_answer": finalize_answer(financial_answer),
            "requires_backend_api": financial_query_type == "refund_status_or_amount_request",
            "invalid_input": False,
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": financial_query_type,
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            "inherited_financial_risk": False,
            "inherited_from_previous_query": "",
            **debug,
        }, f"financial_guard:{financial_query_type}")

    if is_aftersales_operation_request(question) and not is_aftersales_followup_query(question):
        return finish({
            "question": question,
            "final_answer": finalize_answer(AFTERSALES_OPERATION_SAFE_ANSWER),
            "requires_backend_api": True,
            "invalid_input": False,
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": AFTERSALES_OPERATION_QUERY_TYPE,
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            "inherited_financial_risk": False,
            "inherited_from_previous_query": "",
            "inherited_aftersales_operation": False,
            **debug,
        }, "aftersales_operation_guard")

    inherited_backend = inherit_backend_required_from_state(question, prior_state)
    if inherited_backend:
        return finish({
            "question": question,
            "final_answer": finalize_answer(inherited_backend.safe_answer),
            "requires_backend_api": True,
            "invalid_input": False,
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": inherited_backend.query_type,
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            "inherited_backend_required": True,
            "inherited_financial_risk": (
                inherited_backend.query_type == "refund_status_or_amount_request"
            ),
            "inherited_from_previous_query": prior_state.last_user_query,
            "inherited_aftersales_operation": False,
            **debug,
        }, "inherited_backend_required")

    inherited_financial = inherit_financial_risk_from_state(question, prior_state)
    if not inherited_financial:
        inherited_financial = inherit_financial_risk_from_previous(
            question,
            previous_user_query=previous_user_query,
            previous_assistant_answer=previous_assistant_answer,
        )
    if inherited_financial:
        return finish({
            "question": question,
            "final_answer": finalize_answer(inherited_financial.safe_answer),
            "requires_backend_api": inherited_financial.query_type == "refund_status_or_amount_request",
            "invalid_input": False,
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": inherited_financial.query_type,
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            "inherited_financial_risk": True,
            "inherited_from_previous_query": inherited_financial.inherited_from_previous_query,
            "inherited_aftersales_operation": False,
            **debug,
        }, "inherited_financial_risk")

    inherited_aftersales = inherit_aftersales_operation_from_state(question, prior_state)
    if not inherited_aftersales:
        inherited_aftersales = inherit_aftersales_operation_from_previous(
            question,
            previous_user_query=previous_user_query,
            previous_assistant_answer=previous_assistant_answer,
        )
    if inherited_aftersales:
        return finish({
            "question": question,
            "final_answer": finalize_answer(inherited_aftersales.safe_answer),
            "requires_backend_api": True,
            "invalid_input": False,
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": AFTERSALES_OPERATION_QUERY_TYPE,
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            "inherited_financial_risk": False,
            "inherited_from_previous_query": inherited_aftersales.inherited_from_previous_query,
            "inherited_aftersales_operation": True,
            **debug,
        }, "inherited_aftersales_operation")

    if is_aftersales_operation_request(question):
        return finish({
            "question": question,
            "final_answer": finalize_answer(AFTERSALES_OPERATION_SAFE_ANSWER),
            "requires_backend_api": True,
            "invalid_input": False,
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": AFTERSALES_OPERATION_QUERY_TYPE,
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            "inherited_financial_risk": False,
            "inherited_from_previous_query": "",
            "inherited_aftersales_operation": False,
            **debug,
        }, "aftersales_operation_guard")

    mixed_policy_handoff = route_decision.route is AnswerRoute.POLICY_PLUS_HANDOFF
    size_policy_retrieval = size_decision.query_type == "size_and_policy_retrieval"
    retrieval_query = (
        route_decision.policy_query
        if mixed_policy_handoff and route_decision.policy_query
        else (
            size_decision.secondary_policy_query
            if size_policy_retrieval and size_decision.secondary_policy_query
            else followup.retrieval_query
        )
    )
    original_results = filter_quarantined_knowledge_results(retrieve(
        retrieval_query,
        corpus,
        embeddings,
        embedding_model,
        top_k,
        cosine_similarity,
    ))
    reranked_results, policy_category = rerank_retrieved_results(
        retrieval_query, original_results
    )
    backend_required = resolve_backend_required(
        question,
        reranked_results,
        allow_top_row_inference=not followup.is_followup_query,
    )
    query_type = detect_query_type(
        question,
        backend_required,
        policy_category,
        domain_query=retrieval_query,
    )
    generation_question = retrieval_query if (mixed_policy_handoff or size_policy_retrieval) else question
    final_answer, _prompt = generate_final_answer(
        generation_question,
        original_results,
        reranked_results,
        low_confidence_threshold,
        llm_config,
        False if mixed_policy_handoff else backend_required,
        query_type=query_type,
        retrieval_query=retrieval_query,
        previous_user_query=followup.previous_user_query,
        previous_assistant_answer=followup.previous_assistant_answer,
        is_followup=followup.is_followup_query,
        contextual_query=followup.contextual_query,
        generation_config=generation_config,
    )
    if mixed_policy_handoff:
        final_answer = finalize_answer(
            f"{final_answer} {p0_s1_status_handoff_boundary(route_decision)}"
        )
    if size_policy_retrieval:
        final_answer = finalize_answer(f"{size_decision.answer} {final_answer}")
    effective_backend_required = backend_required or mixed_policy_handoff
    provider_was_available = llm_config.has_api_key and llm_config.client is not None
    return finish({
        "question": question,
        "final_answer": final_answer,
        "requires_backend_api": effective_backend_required,
        "invalid_input": False,
        "skip_retrieval": False,
        "skip_llm": backend_required or (mixed_policy_handoff and not provider_was_available),
        "query_type": (
            "policy_plus_handoff"
            if mixed_policy_handoff
            else ("size_and_policy_retrieval" if size_policy_retrieval else query_type)
        ),
        "policy_category": policy_category,
        "original_results": original_results,
        "reranked_results": reranked_results,
        "inherited_financial_risk": False,
        "inherited_from_previous_query": "",
        "inherited_aftersales_operation": False,
        **debug,
    }, "retrieval_answer")


def print_answer_results(
    query: str,
    original_results: list,
    reranked_results: list,
    policy_category: str | None,
    backend_required: bool,
    final_answer: str,
    invalid_input: bool = False,
    query_type: str = "normal",
    skip_retrieval: bool = False,
) -> None:
    print("\n" + "=" * 88)
    print(f"User question: {query}")
    print("=" * 88)
    print(f"Invalid input: {invalid_input}")
    print(f"Query type: {query_type}")
    print(f"Skip retrieval: {skip_retrieval}")
    print("\nOriginal Top 5 retrieved QA:")
    for rank, (row, score) in enumerate(original_results, start=1):
        print(f"\n[{rank}] similarity={score:.4f} | category={row['category']}")
        print(f"Retrieved question: {row['question']}")
        print(f"Answer: {row['answer']}")
    print(f"\nDetected general policy category: {policy_category or 'None'}")
    print(f"Requires backend API: {backend_required}")
    print("\nReranked context order:")
    for rank, result in enumerate(reranked_results, start=1):
        row, score = result[0], result[1]
        meta = result[2] if len(result) > 2 else {}
        print(
            f"\n[{rank}] original_rank={meta.get('original_rank', rank)} "
            f"similarity={score:.4f} rerank_score={meta.get('rerank_score', score):.4f} "
            f"| category={row['category']} | reason={meta.get('rerank_reason', 'embedding_only')}"
        )
        print(f"Context question: {row['question']}")
        print(f"Context answer: {row['answer']}")
    print("\nFinal answer:")
    print(final_answer)


def interactive_loop(corpus, embeddings, embedding_model, top_k: int, cosine_similarity, low_confidence_threshold: float, llm_config: LLMConfig) -> None:
    print("\nJD QA RAG answer demo is ready. Type a question, or exit to quit.")
    previous_user_query: str | None = None
    previous_assistant_answer: str | None = None
    conversation_state: dict | None = None
    while True:
        try:
            query = input("\nQuestion> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExited.")
            break
        if query.casefold() == "exit":
            print("Exited.")
            break
        if not query:
            print(INVALID_INPUT_ANSWER)
            continue

        result = run_rag_query(
            query,
            corpus,
            embeddings,
            embedding_model,
            top_k,
            cosine_similarity,
            low_confidence_threshold,
            llm_config,
            previous_user_query=previous_user_query,
            previous_assistant_answer=previous_assistant_answer,
            conversation_state=conversation_state,
        )
        print_answer_results(
            result["question"],
            result.get("original_results", []),
            result.get("reranked_results", []),
            result.get("policy_category"),
            result.get("requires_backend_api", False),
            result.get("final_answer", ""),
            invalid_input=result.get("invalid_input", False),
            query_type=result.get("query_type", "normal"),
            skip_retrieval=result.get("skip_retrieval", False),
        )
        if result.get("is_followup_query"):
            print(
                f"\nFollow-up debug: contextual_query={result.get('contextual_query', '')} "
                f"| retrieval_query={result.get('retrieval_query', '')}"
            )

        final_answer = result.get("final_answer", "")
        if final_answer:
            previous_user_query = query
            previous_assistant_answer = final_answer
            conversation_state = result.get("conversation_state")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JD customer-service QA RAG answer CLI demo.")
    parser.add_argument("csv_path", help="Path to jd_final_safe_qa_refined_category.csv")
    parser.add_argument(
        "--snippets-csv",
        default="",
        help="Optional path to knowledge_snippets_v2_reviewed.csv for mixed V2 corpus",
    )
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL, help="sentence-transformers embedding model")
    parser.add_argument("--top-k", type=int, default=5, help="Number of retrieved QA pairs")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    parser.add_argument("--cache-dir", default=str(DEFAULT_CACHE_ROOT), help="Cache root; v1/v2 subdirs are created automatically")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild embeddings cache")
    parser.add_argument("--low-confidence-threshold", type=float, default=LOW_CONFIDENCE_THRESHOLD)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        csv_path = resolve_qa_csv_path(args.csv_path if args.csv_path else None)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    snippets_csv_path = None
    if args.snippets_csv.strip():
        try:
            snippets_csv_path = resolve_snippets_csv_path(args.snippets_csv)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    if args.top_k < 1 or args.batch_size < 1:
        print("Error: --top-k and --batch-size must be greater than 0", file=sys.stderr)
        return 2
    try:
        np, pd, load_dotenv, OpenAI, SentenceTransformer, cosine_similarity = load_dependencies()
        llm_config = load_llm_config(load_dotenv, OpenAI)
        print(f"Loading embedding model: {args.model}")
        embedding_model = SentenceTransformer(args.model)
        corpus, embeddings = load_or_create_cache(
            csv_path=csv_path,
            cache_dir=Path(args.cache_dir).expanduser().resolve(),
            embedding_model=embedding_model,
            embedding_model_name=args.model,
            batch_size=args.batch_size,
            rebuild=args.rebuild,
            np=np,
            pd=pd,
            snippets_csv_path=snippets_csv_path,
        )
        interactive_loop(corpus, embeddings, embedding_model, args.top_k, cosine_similarity, args.low_confidence_threshold, llm_config)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
