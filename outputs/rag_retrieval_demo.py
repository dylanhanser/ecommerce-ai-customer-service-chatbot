#!/usr/bin/env python3
"""Minimal command-line semantic retrieval demo for the final JD QA corpus."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_FILENAME = "qa_embeddings.npy"
CORPUS_FILENAME = "qa_corpus.pkl"


def load_dependencies():
    try:
        import numpy as np
        import pandas as pd
        from sentence_transformers import SentenceTransformer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError as exc:
        raise RuntimeError(
            "缺少依赖。请先运行：python -m pip install -r requirements.txt"
        ) from exc
    return np, pd, SentenceTransformer, cosine_similarity


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_corpus(csv_path: Path, pd):
    frame = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    required = {"final_question", "final_answer"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError("输入 CSV 缺少字段：" + ", ".join(sorted(missing)))

    questions = frame["final_question"].astype(str).str.strip()
    answers = frame["final_answer"].astype(str).str.strip()
    if "refined_category" in frame.columns:
        categories = frame["refined_category"].astype(str).str.strip()
        if "category" in frame.columns:
            fallback = frame["category"].astype(str).str.strip()
            categories = categories.where(categories != "", fallback)
    elif "category" in frame.columns:
        categories = frame["category"].astype(str).str.strip()
    else:
        categories = pd.Series(["其他"] * len(frame), index=frame.index)

    valid = (questions != "") & (answers != "")
    corpus = pd.DataFrame(
        {
            "question": questions.loc[valid],
            "answer": answers.loc[valid],
            "category": categories.loc[valid].replace("", "其他"),
            "session_id": (
                frame.loc[valid, "session_id"] if "session_id" in frame.columns else ""
            ),
            "source_file": (
                frame.loc[valid, "source_file"] if "source_file" in frame.columns else ""
            ),
        }
    ).reset_index(drop=True)
    if corpus.empty:
        raise ValueError("过滤空问题/空回答后没有可检索数据")
    return corpus


def cache_is_valid(corpus, embeddings, csv_hash: str, model_name: str) -> bool:
    attrs = getattr(corpus, "attrs", {})
    return (
        attrs.get("source_sha256") == csv_hash
        and attrs.get("model_name") == model_name
        and len(corpus) == embeddings.shape[0]
        and embeddings.ndim == 2
        and embeddings.shape[1] > 0
    )


def load_or_create_cache(
    csv_path: Path,
    cache_dir: Path,
    model,
    model_name: str,
    batch_size: int,
    rebuild: bool,
    np,
    pd,
):
    cache_dir.mkdir(parents=True, exist_ok=True)
    embeddings_path = cache_dir / EMBEDDING_FILENAME
    corpus_path = cache_dir / CORPUS_FILENAME
    csv_hash = file_sha256(csv_path)

    if not rebuild and embeddings_path.is_file() and corpus_path.is_file():
        try:
            corpus = pd.read_pickle(corpus_path)
            embeddings = np.load(embeddings_path, mmap_mode="r")
            if cache_is_valid(corpus, embeddings, csv_hash, model_name):
                print(f"已加载缓存：{len(corpus):,} 条 QA")
                return corpus, embeddings
            print("缓存与当前 CSV 或模型不一致，将重新生成 embeddings。")
        except (OSError, ValueError, EOFError, AttributeError) as exc:
            print(f"缓存读取失败，将重新生成：{exc}")

    corpus = build_corpus(csv_path, pd)
    print(f"正在为 {len(corpus):,} 条问题生成 embeddings……")
    embeddings = model.encode(
        corpus["question"].tolist(),
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ).astype("float32", copy=False)
    corpus.attrs["source_sha256"] = csv_hash
    corpus.attrs["model_name"] = model_name
    corpus.to_pickle(corpus_path)
    np.save(embeddings_path, embeddings)
    print(f"已保存：{embeddings_path}")
    print(f"已保存：{corpus_path}")
    return corpus, embeddings


def retrieve(query: str, corpus, embeddings, model, top_k: int, cosine_similarity):
    query_embedding = model.encode(
        [query], convert_to_numpy=True, normalize_embeddings=True
    )
    scores = cosine_similarity(query_embedding, embeddings)[0]
    result_count = min(top_k, len(corpus))
    # argsort is simple and stable enough for this small prototype corpus.
    top_indices = scores.argsort()[-result_count:][::-1]
    return [(corpus.iloc[int(index)], float(scores[index])) for index in top_indices]


def print_results(query: str, results) -> None:
    print("\n" + "=" * 88)
    print(f"用户问题：{query}")
    print("=" * 88)
    for rank, (row, score) in enumerate(results, start=1):
        print(f"\n[{rank}] similarity={score:.4f} | category={row['category']}")
        print(f"Retrieved question: {row['question']}")
        print(f"Answer: {row['answer']}")
    print()


def interactive_loop(corpus, embeddings, model, top_k: int, cosine_similarity) -> None:
    print("\nJD QA 语义检索已就绪。输入问题开始检索，输入 exit 退出。")
    while True:
        try:
            query = input("\n问题> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            break
        if query.casefold() == "exit":
            print("已退出。")
            break
        if not query:
            print("请输入非空问题，或输入 exit 退出。")
            continue
        results = retrieve(query, corpus, embeddings, model, top_k, cosine_similarity)
        print_results(query, results)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="最小 JD 客服 QA 语义检索原型。")
    parser.add_argument("csv_path", help="jd_final_safe_qa_refined_category.csv 路径")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="sentence-transformers 模型名或本地路径")
    parser.add_argument("--top-k", type=int, default=5, help="返回结果数量（默认：5）")
    parser.add_argument("--batch-size", type=int, default=64, help="embedding 批大小（默认：64）")
    parser.add_argument(
        "--cache-dir", default=".", help="qa_embeddings.npy 和 qa_corpus.pkl 保存目录"
    )
    parser.add_argument("--rebuild", action="store_true", help="忽略已有缓存并重新生成 embeddings")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    csv_path = Path(args.csv_path).expanduser().resolve()
    if not csv_path.is_file():
        print(f"Error: 找不到输入文件：{csv_path}", file=sys.stderr)
        return 2
    if args.top_k < 1 or args.batch_size < 1:
        print("Error: --top-k 和 --batch-size 必须大于 0", file=sys.stderr)
        return 2

    try:
        np, pd, SentenceTransformer, cosine_similarity = load_dependencies()
        print(f"正在加载 embedding 模型：{args.model}")
        model = SentenceTransformer(args.model)
        corpus, embeddings = load_or_create_cache(
            csv_path=csv_path,
            cache_dir=Path(args.cache_dir).expanduser().resolve(),
            model=model,
            model_name=args.model,
            batch_size=args.batch_size,
            rebuild=args.rebuild,
            np=np,
            pd=pd,
        )
        interactive_loop(corpus, embeddings, model, args.top_k, cosine_similarity)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
