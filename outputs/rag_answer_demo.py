#!/usr/bin/env python3
"""Command-line RAG answer demo for the final JD QA corpus."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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
    "\u552e\u540e\u8fdb\u5ea6",
    "\u9000\u6b3e\u8fdb\u5ea6",
    "\u8865\u507f\u5230\u8d26",
    "\u8fd4\u6b3e\u5230\u8d26",
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
]
BACKEND_ACTION_FOLLOWUP_KEYWORDS = [
    "\u4f60\u80fd\u5904\u7406\u5417",
    "\u4f60\u5e2e\u6211\u5904\u7406",
    "\u5e2e\u6211\u5904\u7406",
    "\u90a3\u4f60\u5e2e\u6211",
    "\u90a3\u4f60\u5e2e\u6211\u5904\u7406",
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


@dataclass
class FollowupResolution:
    is_followup_query: bool
    original_query: str
    contextual_query: str
    previous_user_query: str
    previous_assistant_answer: str
    retrieval_query: str


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


def filter_results_for_answer_generation(
    results: list,
    backend_required: bool,
    user_question: str = "",
) -> list:
    filtered = results
    if not backend_required:
        filtered = [item for item in filtered if not row_is_backend_only(item[0])]
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
        snippet_items = build_snippet_corpus_items(snippets_csv_path, pd)
        items.extend(snippet_items)
        print(
            f"Mixed corpus: {len(items) - len(snippet_items):,} QA + "
            f"{len(snippet_items):,} knowledge snippets"
        )
    corpus = pd.DataFrame(items).reset_index(drop=True)
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


def is_intent_guard_priority_query(query: str) -> bool:
    skip_retrieval, _guarded_type, _answer = intent_guard(query)
    return skip_retrieval


def is_followup_query(query: str) -> bool:
    stripped = str(query or "").strip()
    if not stripped:
        return False
    if is_intent_guard_priority_query(stripped):
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

    if contains_any(normalized, FOLLOWUP_QUERY_PHRASES):
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

    if has_previous and (is_followup_query(original) or is_financial_risk_query(original)):
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


def detect_policy_category(user_question: str) -> str | None:
    normalized = re.sub(r"\s+", "", user_question)
    for category in POLICY_CATEGORY_PRIORITY:
        if contains_any(normalized, POLICY_CATEGORY_KEYWORDS[category]):
            return category
    return None


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


def intent_guard(user_question: str) -> tuple[bool, str, str | None]:
    normalized = re.sub(r"\s+", "", user_question.strip()).casefold()
    if not normalized:
        return False, "normal", None

    if contains_any(normalized, IDENTITY_QUERY_KEYWORDS):
        return True, "identity", IDENTITY_ANSWER

    if contains_any(normalized, HUMAN_HANDOVER_KEYWORDS):
        return True, "human_handover", HUMAN_HANDOVER_ANSWER

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


def call_deepseek_api(prompt: str, llm_config: LLMConfig) -> str:
    if llm_config.client is None:
        raise RuntimeError("DeepSeek client is not initialized.")
    response = llm_config.client.chat.completions.create(
        model=llm_config.model,
        messages=[
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
        temperature=0.2,
    )
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
            final_answer = call_deepseek_api(prompt, llm_config)
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
) -> dict:
    question = str(user_question or "").strip()
    followup = resolve_followup_context(
        question,
        previous_user_query=previous_user_query,
        previous_assistant_answer=previous_assistant_answer,
    )
    debug = followup_debug_info(followup)

    skip_retrieval, guarded_type, guarded_answer = intent_guard(question)
    if skip_retrieval:
        backend_required = guarded_type == "backend_required"
        return {
            "question": question,
            "final_answer": finalize_answer(guarded_answer or ""),
            "requires_backend_api": backend_required,
            "invalid_input": guarded_type == "unclear",
            "skip_retrieval": True,
            "skip_llm": True,
            "query_type": guarded_type,
            "policy_category": None,
            "original_results": [],
            "reranked_results": [],
            **debug,
        }

    invalid_input, invalid_answer = invalid_input_guard(question)
    if invalid_input:
        return {
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
            **debug,
        }

    financial_risk = detect_financial_risk_query(question)
    if financial_risk:
        financial_query_type, financial_answer = financial_risk
        return {
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
            **debug,
        }

    retrieval_query = followup.retrieval_query
    original_results = retrieve(
        retrieval_query,
        corpus,
        embeddings,
        embedding_model,
        top_k,
        cosine_similarity,
    )
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
    final_answer, _prompt = generate_final_answer(
        question,
        original_results,
        reranked_results,
        low_confidence_threshold,
        llm_config,
        backend_required,
        query_type=query_type,
        retrieval_query=retrieval_query,
        previous_user_query=followup.previous_user_query,
        previous_assistant_answer=followup.previous_assistant_answer,
        is_followup=followup.is_followup_query,
        contextual_query=followup.contextual_query,
    )
    return {
        "question": question,
        "final_answer": final_answer,
        "requires_backend_api": backend_required,
        "invalid_input": False,
        "skip_retrieval": False,
        "skip_llm": backend_required,
        "query_type": query_type,
        "policy_category": policy_category,
        "original_results": original_results,
        "reranked_results": reranked_results,
        **debug,
    }


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
