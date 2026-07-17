"""Deterministically freeze the external_store_v1 human-review sample.

This program deliberately consumes accepted candidates only.  It never writes to
the candidate pool and emits no generated answers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SEED = "20260717"
REPRESENTATIVE_QUOTAS = {
    "其他": 22, "物流发货": 21, "尺码问题": 14, "商品咨询": 11,
    "退货退款": 10, "质量问题": 5, "运费": 5, "换货": 4, "价格补偿": 4,
}
METHODS = ("legacy_keyword", "statistical_sender_rule")
ANOMALY_QUOTAS = {"invalid_session_end_time": 5, "missing_message_content": 5,
                  "invalid_session_end_time|missing_message_content": 2}
REVIEW_FIELDS = [
    "review_id", "question", "answer", "reviewer_id", "review_date", "pair_valid",
    "question_self_contained", "answer_relevance", "role_pairing_correct",
    "answer_usable_as_reference", "residual_pii_found", "gold_category",
    "exclude_reason", "reviewer_notes",
]
MANIFEST_FIELDS = [
    "review_id", "external_candidate_id", "external_session_id", "sample_group",
    "risk_reason", "source_month", "refined_category", "role_inference_method",
    "inferred_service_sender_count", "parser_anomaly_types", "decision_margin",
]


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def rank(purpose: str, candidate_id: str) -> str:
    return digest(f"{SEED}|{purpose}|{candidate_id}")


def stable_rows(rows):
    return sorted(rows, key=lambda r: r["external_candidate_id"])


def largest_remainder(total: int, counts: dict[str, int], keys=None) -> dict[str, int]:
    """Allocate ``total`` proportionally, with deterministic tie breaking."""
    keys = list(keys if keys is not None else sorted(counts))
    denominator = sum(counts[k] for k in keys)
    if not denominator:
        raise ValueError("cannot allocate from an empty pool")
    raw = {k: total * counts[k] / denominator for k in keys}
    result = {k: int(raw[k]) for k in keys}
    left = total - sum(result.values())
    for k in sorted(keys, key=lambda k: (-(raw[k] - result[k]), str(k)))[:left]:
        result[k] += 1
    return result


def take(rows, count, purpose, used_candidates, used_sessions):
    pool = [r for r in stable_rows(rows) if r["external_candidate_id"] not in used_candidates
            and r["external_session_id"] not in used_sessions]
    pool.sort(key=lambda r: rank(purpose, r["external_candidate_id"]))
    chosen = pool[:count]
    if len(chosen) != count:
        raise ValueError(f"insufficient eligible candidates for {purpose}: need {count}, got {len(chosen)}")
    for row in chosen:
        used_candidates.add(row["external_candidate_id"])
        used_sessions.add(row["external_session_id"])
    return chosen


def anomaly_key(row):
    values = set(filter(None, row["parser_anomaly_types"].split("|")))
    wanted = {"invalid_session_end_time", "missing_message_content"}
    if values == {"invalid_session_end_time"}:
        return "invalid_session_end_time"
    if values == {"missing_message_content"}:
        return "missing_message_content"
    if wanted <= values:
        return "invalid_session_end_time|missing_message_content"
    return None


def decision_margin(row):
    threshold = float(row["role_inference_threshold_sessions"])
    values = (
        (float(row["role_inference_sender_session_count"]) - threshold) / threshold,
        float(row["role_inference_last_ratio"]) - .80,
        .20 - float(row["role_inference_first_ratio"]),
    )
    return min(values)


def select_representative(rows, used_candidates, used_sessions, fallbacks):
    selected = []
    for category, quota in REPRESENTATIVE_QUOTAS.items():
        category_rows = [r for r in rows if r["refined_category"] == category
                         and r["role_inference_method"] in METHODS]
        role_counts = Counter(r["role_inference_method"] for r in category_rows)
        role_quota = largest_remainder(quota, role_counts, METHODS)
        for method in METHODS:
            role_rows = [r for r in category_rows if r["role_inference_method"] == method]
            months = sorted({r["source_month"] for r in role_rows}, key=int)
            month_quota = largest_remainder(role_quota[method], Counter(r["source_month"] for r in role_rows), months)
            for month in months:
                needed = month_quota[month]
                primary = [r for r in role_rows if r["source_month"] == month]
                picked = take_partial(primary, needed, f"representative|{category}|{method}|{month}", used_candidates, used_sessions)
                selected.extend(picked)
                remaining = needed - len(picked)
                if remaining:
                    other_months = [r for r in role_rows if r["source_month"] != month]
                    picked = take_partial(other_months, remaining, f"fallback-same-role|{category}|{method}|{month}", used_candidates, used_sessions)
                    selected.extend(picked); remaining -= len(picked)
                    if picked:
                        fallbacks.append({"category": category, "target_role": method, "target_month": month,
                                          "fallback": "same_category_same_role_other_month", "count": len(picked)})
                if remaining:
                    alternate = [r for r in category_rows if r["role_inference_method"] != method and r["source_month"] != month]
                    picked = take_partial(alternate, remaining, f"fallback-other-role|{category}|{method}|{month}", used_candidates, used_sessions)
                    selected.extend(picked); remaining -= len(picked)
                    if picked:
                        fallbacks.append({"category": category, "target_role": method, "target_month": month,
                                          "fallback": "same_category_other_role_other_month", "count": len(picked)})
                if remaining:
                    raise ValueError(f"representative cell cannot be filled: {category}/{method}/month-{month}")
    if len(selected) != 96:
        raise AssertionError(f"representative total is {len(selected)}, not 96")
    return selected


def take_partial(rows, count, purpose, used_candidates, used_sessions):
    pool = [r for r in stable_rows(rows) if r["external_candidate_id"] not in used_candidates
            and r["external_session_id"] not in used_sessions]
    pool.sort(key=lambda r: rank(purpose, r["external_candidate_id"]))
    chosen = pool[:count]
    for row in chosen:
        used_candidates.add(row["external_candidate_id"]); used_sessions.add(row["external_session_id"])
    return chosen


def take_diverse(rows, count, purpose, used_candidates, used_sessions):
    """Take deterministically while preferring new month/category coverage."""
    chosen, seen_months, seen_categories = [], set(), set()
    for index in range(count):
        pool = [r for r in stable_rows(rows) if r["external_candidate_id"] not in used_candidates
                and r["external_session_id"] not in used_sessions]
        if not pool:
            raise ValueError(f"insufficient eligible candidates for {purpose}: need {count}, got {index}")
        pool.sort(key=lambda r: (-(int(r["source_month"] not in seen_months) + int(r["refined_category"] not in seen_categories)),
                                 rank(f"{purpose}|{index}", r["external_candidate_id"])))
        item = pool[0]
        chosen.append(item); used_candidates.add(item["external_candidate_id"]); used_sessions.add(item["external_session_id"])
        seen_months.add(item["source_month"]); seen_categories.add(item["refined_category"])
    return chosen


def sanitize(text: str) -> str:
    text = text or ""
    text = re.sub(r"\[?(?:ADDRESS|PHONE|ID_CARD|NAME|EMAIL|ORDER)[^\]]*\]?", "[REDACTED]", text, flags=re.I)
    text = re.sub(r"(?:https?://|www\.)\S+", "[REDACTED_URL]", text, flags=re.I)
    text = re.sub(r"(?<!\d)1[3-9]\d{9}(?!\d)", "[REDACTED_PHONE]", text)
    text = re.sub(r"(?<!\d)\d{15,18}[0-9Xx](?!\d)", "[REDACTED_ID]", text)
    text = re.sub(r"[A-Za-z]:\\[^\s]+|/(?:Users|home|tmp)/[^\s]+", "[REDACTED_PATH]", text)
    return text


def has_residual_pii(text: str) -> bool:
    return bool(re.search(r"(?:https?://|www\.)\S+|(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{15,18}[0-9Xx](?!\d)|[A-Za-z]:\\|/(?:Users|home|tmp)/", text, re.I))


def sample(rows):
    rows = stable_rows([r for r in rows if r["candidate_status"] == "accepted"])
    if len({r["external_candidate_id"] for r in rows}) != len(rows):
        raise ValueError("accepted candidate IDs are not unique")
    used_candidates, used_sessions, fallbacks = set(), set(), []
    special_pool = [r for r in rows if r["role_inference_method"] == "mixed" or int(r["inferred_service_sender_count"]) > 1]
    mixed = [r for r in special_pool if r["role_inference_method"] == "mixed"]
    multi = [r for r in special_pool if r["role_inference_method"] == "statistical_sender_rule" and int(r["inferred_service_sender_count"]) > 1]
    if not (len(mixed) == 2 and len(multi) == 2 and len(special_pool) == 4 and len({r['external_session_id'] for r in special_pool}) == 4):
        raise ValueError("role-special expectation failed: expected mixed=2, statistical multi-sender=2, union/sessions=4")
    special = take(special_pool, 4, "role-special", used_candidates, used_sessions)
    representative = select_representative(rows, used_candidates, used_sessions, fallbacks)
    anomalies = []
    for kind, quota in ANOMALY_QUOTAS.items():
        candidates = [r for r in rows if anomaly_key(r) == kind]
        anomalies += take_diverse(candidates, quota, f"parser-anomaly|{kind}", used_candidates, used_sessions)
    near_pool = [r for r in rows if r["role_inference_method"] == "statistical_sender_rule" and decision_margin(r) >= 0
                 and r["external_candidate_id"] not in used_candidates and r["external_session_id"] not in used_sessions]
    months = sorted({r["source_month"] for r in near_pool}, key=int)
    if len(months) < 6:
        raise ValueError("near-threshold pool cannot cover six months")
    near = []
    for month in months:
        candidates = [r for r in near_pool if r["source_month"] == month]
        candidates.sort(key=lambda r: (decision_margin(r), rank("near-threshold|month", r["external_candidate_id"])))
        near += take(candidates, 1, f"near-threshold|month-{month}", used_candidates, used_sessions)
    remaining = [r for r in near_pool if r["external_candidate_id"] not in used_candidates and r["external_session_id"] not in used_sessions]
    remaining.sort(key=lambda r: (decision_margin(r), rank("near-threshold|remaining", r["external_candidate_id"])))
    near += take(remaining, 2, "near-threshold|remaining", used_candidates, used_sessions)
    groups = [("representative", "", representative), ("role_special", "mixed_or_multi_sender", special),
              ("parser_anomaly", "", anomalies), ("near_threshold", "near_threshold", near)]
    records = []
    for group, default_reason, members in groups:
        for row in members:
            copy = dict(row); copy["sample_group"] = group
            copy["risk_reason"] = anomaly_key(row) if group == "parser_anomaly" else default_reason
            copy["decision_margin"] = f"{decision_margin(row):.12f}" if group == "near_threshold" else ""
            records.append(copy)
    if len(records) != 120 or len({r['external_candidate_id'] for r in records}) != 120 or len({r['external_session_id'] for r in records}) != 120:
        raise AssertionError("sample is not globally unique at 120 candidates and sessions")
    return records, fallbacks


def write_outputs(records, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    blinded = sorted(records, key=lambda r: rank("review-blind", r["external_candidate_id"]))
    for i, row in enumerate(blinded, 1): row["review_id"] = f"R{i:03d}"
    review_path = output_dir / "external_store_v1_review_sample_120.csv"
    manifest_path = output_dir / "external_store_v1_review_manifest.csv"
    with review_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_FIELDS); writer.writeheader()
        for r in blinded:
            writer.writerow({"review_id": r["review_id"], "question": sanitize(r["final_question"]), "answer": sanitize(r["final_answer"]),
                             "reviewer_id": "", "review_date": "", "pair_valid": "", "question_self_contained": "", "answer_relevance": "",
                             "role_pairing_correct": "", "answer_usable_as_reference": "", "residual_pii_found": "", "gold_category": "",
                             "exclude_reason": "", "reviewer_notes": ""})
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS); writer.writeheader()
        for r in blinded: writer.writerow({k: r.get(k, "") for k in MANIFEST_FIELDS})
    review_text = review_path.read_text(encoding="utf-8-sig")
    if any(has_residual_pii(r["question"]) or has_residual_pii(r["answer"]) for r in csv.DictReader(review_text.splitlines())):
        raise ValueError("residual PII pattern found in review output")
    return review_path, manifest_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/external_eval/processed/external_store_v1_candidates.csv")
    parser.add_argument("--output-dir", default="data/external_eval/review")
    parser.add_argument("--summary-json")
    args = parser.parse_args()
    rows = list(csv.DictReader(Path(args.input).open(encoding="utf-8-sig")))
    records, fallbacks = sample(rows)
    review, manifest = write_outputs(records, Path(args.output_dir))
    summary = {"seed": SEED, "total": len(records), "groups": Counter(r["sample_group"] for r in records),
               "categories": Counter(r["refined_category"] for r in records if r["sample_group"] == "representative"),
               "fallbacks": fallbacks, "review_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
               "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}
    if args.summary_json: Path(args.summary_json).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, default=dict))


if __name__ == "__main__":
    main()
