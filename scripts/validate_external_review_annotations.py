"""Validate frozen external review sheets without printing QA text."""
from __future__ import annotations
import argparse, csv, hashlib
from pathlib import Path

FIELDS = ["reviewer_id", "review_date", "pair_valid", "question_self_contained", "answer_relevance", "role_pairing_correct", "answer_usable_as_reference", "residual_pii_found", "gold_category", "exclude_reason", "reviewer_notes"]
ALLOWED = {"pair_valid":{"yes","no","uncertain"}, "question_self_contained":{"yes","no","uncertain"},
 "answer_relevance":{"yes","partial","no","uncertain"}, "role_pairing_correct":{"yes","no","uncertain"},
 "answer_usable_as_reference":{"yes","no","uncertain"}, "residual_pii_found":{"yes","no"},
 "gold_category":{"其他","物流发货","尺码问题","商品咨询","退货退款","质量问题","运费","换货","价格补偿","invalid"},
 "exclude_reason":{"","empty_or_fragmented_question","missing_or_irrelevant_answer","wrong_role_pairing","context_dependent","residual_pii","duplicate","other"}}

def sha(value): return hashlib.sha256(value.encode("utf-8")).hexdigest()
def load(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
def error(errors, review_id, field): errors.append(f"{review_id}:{field}")

def validate(review_path, frozen_path, expected_count, completed=False):
    rows, frozen, errors = load(review_path), load(frozen_path), []
    frozen_by_id = {r["review_id"]: r for r in frozen}
    if len(rows) != expected_count: errors.append(f"FILE:row_count_expected_{expected_count}")
    seen=set()
    for r in rows:
        rid=r.get("review_id","")
        if rid in seen: error(errors,rid,"duplicate_review_id")
        seen.add(rid)
        base=frozen_by_id.get(rid)
        if not base: error(errors,rid,"unknown_review_id"); continue
        for field in ("review_id","question","answer"):
            if sha(r.get(field,"")) != sha(base.get(field,"")): error(errors,rid,field+"_modified")
        for field, allowed in ALLOWED.items():
            if r.get(field,"") not in allowed: error(errors,rid,field+"_invalid")
        if r.get("review_date") and not __import__('re').fullmatch(r"\d{4}-\d{2}-\d{2}",r["review_date"]): error(errors,rid,"review_date_invalid")
        if completed:
            for field in ["reviewer_id","review_date",*ALLOWED.keys()]:
                if not r.get(field,"") and field != "exclude_reason": error(errors,rid,field+"_required")
        reason=r.get("exclude_reason","")
        if r.get("residual_pii_found")=="yes" and reason != "residual_pii": error(errors,rid,"exclude_reason_residual_pii")
        links={"empty_or_fragmented_question":("question_self_contained","no"), "missing_or_irrelevant_answer":("answer_relevance","no"), "wrong_role_pairing":("role_pairing_correct","no"), "residual_pii":("residual_pii_found","yes")}
        if reason in links and r.get(links[reason][0]) != links[reason][1]: error(errors,rid,"exclude_reason_inconsistent")
        eligible = all([r.get("pair_valid")=="yes",r.get("question_self_contained")=="yes",r.get("answer_relevance")=="yes",r.get("role_pairing_correct")=="yes",r.get("answer_usable_as_reference")=="yes",r.get("residual_pii_found")=="no",r.get("gold_category")!="invalid"])
        if eligible and reason: error(errors,rid,"exclude_reason_on_eligible")
    for rid in sorted(set(frozen_by_id) - seen):
        error(errors,rid,"missing_expected_review_id")
    return errors

if __name__ == "__main__":
    p=argparse.ArgumentParser(); p.add_argument("review"); p.add_argument("--frozen",required=True); p.add_argument("--count",type=int,required=True); p.add_argument("--completed",action="store_true"); a=p.parse_args()
    errors=validate(a.review,a.frozen,a.count,a.completed)
    for item in errors: print(item)
    raise SystemExit(bool(errors))
