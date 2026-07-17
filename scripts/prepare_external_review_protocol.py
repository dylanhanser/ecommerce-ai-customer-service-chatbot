"""Freeze the R1/R2 review files for external_store_v1 without reading labels."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

SEED = "20260717"
REP_QUOTAS = {"其他": 4, "物流发货": 4, "尺码问题": 3, "商品咨询": 2, "退货退款": 2,
              "质量问题": 1, "运费": 1, "换货": 1, "价格补偿": 1}
REVIEW_FIELDS = ["review_id", "question", "answer", "reviewer_id", "review_date", "pair_valid",
                 "question_self_contained", "answer_relevance", "role_pairing_correct",
                 "answer_usable_as_reference", "residual_pii_found", "gold_category", "exclude_reason", "reviewer_notes"]
SECONDARY_MANIFEST_FIELDS = ["review_id", "external_candidate_id", "external_session_id", "secondary_group",
                             "secondary_reason", "source_month", "refined_category", "role_inference_method",
                             "parser_anomaly_types", "decision_margin"]


def hash_rank(candidate_id: str) -> str:
    return hashlib.sha256(f"{SEED}|secondary|{candidate_id}".encode()).hexdigest()


def largest_remainder(total, counts, keys):
    denominator = sum(counts[k] for k in keys)
    if not denominator: raise ValueError("empty quota pool")
    raw = {k: total * counts[k] / denominator for k in keys}
    result = {k: int(raw[k]) for k in keys}
    for k in sorted(keys, key=lambda k: (-(raw[k] - result[k]), k))[:total-sum(result.values())]: result[k] += 1
    return result


def choose_diverse(rows, count, used, purpose):
    """Prefer previously unseen months; all ties use the mandated hash."""
    selected, months = [], set()
    for _ in range(count):
        pool = [r for r in rows if r["external_candidate_id"] not in used]
        if not pool: raise ValueError(f"cannot fill {purpose}")
        pool.sort(key=lambda r: (-(r["source_month"] not in months), hash_rank(r["external_candidate_id"])))
        row = pool[0]; selected.append(row); used.add(row["external_candidate_id"]); months.add(row["source_month"])
    return selected


def select_secondary(manifest_rows):
    rows = sorted(manifest_rows, key=lambda r: r["external_candidate_id"])
    if len(rows) != 120 or len({r["review_id"] for r in rows}) != 120: raise ValueError("frozen manifest must have 120 unique review IDs")
    used, fallback, selected = set(), [], []
    reps = [r for r in rows if r["sample_group"] == "representative"]
    for category, quota in REP_QUOTAS.items():
        category_rows = [r for r in reps if r["refined_category"] == category]
        methods = sorted({r["role_inference_method"] for r in category_rows})
        allocation = largest_remainder(quota, Counter(r["role_inference_method"] for r in category_rows), methods)
        for method in methods:
            pool = [r for r in category_rows if r["role_inference_method"] == method]
            picked = choose_diverse(pool, allocation[method], used, f"representative:{category}:{method}")
            if len(picked) != allocation[method]: fallback.append(f"{category}/{method}")
            for r in picked: r = dict(r); r.update(secondary_group="representative", secondary_reason=""); selected.append(r)
    special = [r for r in rows if r["sample_group"] == "role_special"]
    r = choose_diverse(special, 1, used, "role_special")[0]; r = dict(r); r.update(secondary_group="risk", secondary_reason="role_special"); selected.append(r)
    for anomaly in ("invalid_session_end_time", "missing_message_content"):
        pool = [r for r in rows if r["sample_group"] == "parser_anomaly" and r["risk_reason"] == anomaly]
        r = choose_diverse(pool, 1, used, f"parser:{anomaly}")[0]; r = dict(r); r.update(secondary_group="risk", secondary_reason=anomaly); selected.append(r)
    near = [r for r in rows if r["sample_group"] == "near_threshold" and r["external_candidate_id"] not in used]
    near.sort(key=lambda r: (float(r["decision_margin"]), hash_rank(r["external_candidate_id"])))
    first = near[0]; used.add(first["external_candidate_id"])
    different_month = [r for r in near[1:] if r["source_month"] != first["source_month"] and r["external_candidate_id"] not in used]
    second_pool = different_month or [r for r in near[1:] if r["external_candidate_id"] not in used]
    if not second_pool: raise ValueError("cannot select two near-threshold samples")
    second = second_pool[0]; used.add(second["external_candidate_id"])
    for r in (first, second): r = dict(r); r.update(secondary_group="risk", secondary_reason="closest_to_threshold"); selected.append(r)
    if len(selected) != 24 or len({r["review_id"] for r in selected}) != 24 or len({r["external_session_id"] for r in selected}) != 24:
        raise ValueError("secondary selection is not 24 unique review/candidate/session rows")
    if Counter(r["secondary_group"] for r in selected) != Counter(representative=19, risk=5): raise ValueError("secondary group quota failure")
    return selected, fallback


def blank_row(row):
    return {field: row.get(field, "") if field in {"review_id", "question", "answer"} else "" for field in REVIEW_FIELDS}


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def file_hash(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def build(sample_path, manifest_path, out_dir):
    sample_rows = read_csv(sample_path)
    manifest_rows = read_csv(manifest_path)
    by_id = {r["review_id"]: r for r in sample_rows}
    if len(by_id) != 120: raise ValueError("frozen sample must have 120 unique review IDs")
    selected, fallback = select_secondary(manifest_rows)
    primary_path = out_dir / "external_store_v1_primary_review_120.csv"
    secondary_path = out_dir / "external_store_v1_secondary_review_24.csv"
    secondary_manifest_path = out_dir / "external_store_v1_secondary_review_manifest.csv"
    write_csv(primary_path, [blank_row(r) for r in sample_rows], REVIEW_FIELDS)
    write_csv(secondary_path, [blank_row(by_id[r["review_id"]]) for r in selected], REVIEW_FIELDS)
    write_csv(secondary_manifest_path, [{k: r.get(k, "") for k in SECONDARY_MANIFEST_FIELDS} for r in selected], SECONDARY_MANIFEST_FIELDS)
    return {"primary": str(primary_path), "secondary": str(secondary_path), "secondary_manifest": str(secondary_manifest_path),
            "fallbacks": fallback, "hashes": {"sample": file_hash(sample_path), "manifest": file_hash(manifest_path),
            "primary": file_hash(primary_path), "secondary": file_hash(secondary_path), "secondary_manifest": file_hash(secondary_manifest_path)},
            "secondary_groups": Counter(r["secondary_group"] for r in selected),
            "secondary_reasons": Counter(r["secondary_reason"] for r in selected)}


if __name__ == "__main__":
    result = build("data/external_eval/review/external_store_v1_review_sample_120.csv", "data/external_eval/review/external_store_v1_review_manifest.csv", Path("data/external_eval/review"))
    print(json.dumps(result, ensure_ascii=False, default=dict))
