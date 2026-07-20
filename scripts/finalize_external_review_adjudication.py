"""Deterministically merge frozen human reviews into the external gold set.

This program never generates text or changes the three human-review inputs.
Diagnostics intentionally use IDs and aggregate counts only.
"""
from __future__ import annotations
import argparse, csv, hashlib
from collections import Counter, defaultdict
from pathlib import Path
import prepare_external_review_adjudication as prep
import validate_external_review_adjudication as adjudication_validator

ROOT = Path(__file__).resolve().parents[1]
ADJUDICATION = ROOT / "data/external_eval/review/adjudication/external_store_v1_adjudication_16.csv"
MANIFEST = ROOT / "data/external_eval/review/external_store_v1_review_manifest.csv"
FINAL = ROOT / "data/external_eval/review/final/external_store_v1_adjudicated_review_120.csv"
GOLD = ROOT / "data/external_eval/review/final/external_store_v1_gold_51.csv"
GOLD_MANIFEST = ROOT / "data/external_eval/review/final/external_store_v1_gold_51_manifest.csv"
REPORT = ROOT / "outputs/reports/external_store_v1_adjudicated_review_report.md"
ADJUDICATION_SHA256 = "05db65b63bc4dd8f5835662347f18e173db5a3b1c7b1f867498c6cff8971d38a"
FINAL_FIELDS = ["review_id", "question", "answer", *prep.FIELDS, "final_included", "decision_source", "sample_group", "risk_reason", "external_candidate_id", "external_session_id"]
GOLD_FIELDS = ["review_id", "question", "reference_answer", "gold_category", "sample_group", "risk_reason", "external_candidate_id", "external_session_id"]
EXPECTED_CHANGES = {"R011", "R054", "R061", "R064", "R095"}

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as f: return list(csv.DictReader(f))
def write_csv(path, fields, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        w=csv.DictWriter(f, fieldnames=fields, lineterminator="\r\n"); w.writeheader(); w.writerows(rows)
def included(row): return prep.eligible(row)

def load_manifest(path=MANIFEST):
    rows=read_csv(path); by={r.get("review_id", ""):r for r in rows}
    required={"review_id","external_candidate_id","external_session_id","sample_group","risk_reason"}
    if len(rows)!=120 or len(by)!=120 or not required <= set(rows[0] if rows else ()): raise ValueError("authoritative_manifest_invalid")
    if len({r["external_session_id"] for r in rows}) != 120: raise ValueError("manifest_session_not_unique")
    normalized=[]
    for r in rows:
        group="representative" if r["sample_group"]=="representative" else "risk"
        normalized.append((r["review_id"], group, r["risk_reason"], r["external_candidate_id"], r["external_session_id"]))
    if Counter(x[1] for x in normalized)!=Counter(representative=96,risk=24): raise ValueError("manifest_group_quota_invalid")
    return dict((x[0], x[1:]) for x in normalized)

def merge(primary=prep.PRIMARY, secondary=prep.SECONDARY, adjudication=ADJUDICATION, manifest=MANIFEST):
    prep.validate_frozen_inputs(primary, secondary)
    if digest(adjudication)!=ADJUDICATION_SHA256: raise ValueError("adjudication_sha256_mismatch")
    errors, incomplete=adjudication_validator.validate(adjudication)
    if errors or incomplete: raise ValueError("adjudication_invalid_or_incomplete")
    p=prep.read_csv(primary); s=prep.read_csv(secondary); a=read_csv(adjudication)
    if any(r["adjudicator_id"] != "R3" or r["adjudication_date"] != "2026-07-20" or not r["adjudication_notes"] for r in a): raise ValueError("adjudicator_metadata_invalid")
    pb={r["review_id"]:r for r in p}; sb={r["review_id"]:r for r in s}; ab={r["review_id"]:r for r in a}; lineage=load_manifest(manifest)
    if set(pb)!=set(lineage) or set(ab)!=set(prep.EXPECTED_IDS): raise ValueError("review_id_scope_invalid")
    result=[]
    for base in p:
        rid=base["review_id"]; row={k:base[k] for k in ["review_id","question","answer",*prep.FIELDS]}
        if rid not in sb: source="primary_only"
        elif rid not in ab:
            source="dual_agreement"
            if any(base[f]!=sb[rid][f] for f in prep.FIELDS): raise ValueError("dual_agreement_disagrees")
        else:
            source="adjudicated"
            for f in prep.FIELDS: row[f]=ab[rid][f"{f}_final"]
        row["final_included"]="yes" if included(row) else "no"; row["decision_source"]=source
        row["sample_group"],row["risk_reason"],row["external_candidate_id"],row["external_session_id"]=lineage[rid]
        result.append(row)
    if Counter(r["decision_source"] for r in result)!=Counter(primary_only=96,dual_agreement=8,adjudicated=16): raise ValueError("decision_source_quota_invalid")
    if len({r["external_session_id"] for r in result})!=120: raise ValueError("final_session_not_unique")
    changes={r["review_id"] for r in result if r["review_id"] in ab and included(pb[r["review_id"]]) != included(r)}
    if changes != EXPECTED_CHANGES: raise ValueError("adjudicated_status_changes_invalid")
    if Counter(r["final_included"] for r in result)!=Counter(yes=51,no=69): raise ValueError("final_inclusion_quota_invalid")
    if Counter(r["exclude_reason"] for r in result if not included(r)) != Counter(context_dependent=27,other=22,missing_or_irrelevant_answer=14,residual_pii=6): raise ValueError("exclude_reason_distribution_invalid")
    if Counter(r["gold_category"] for r in result if included(r)) != Counter({"商品咨询":13,"退货退款":12,"物流发货":11,"尺码问题":6,"其他":3,"换货":3,"运费":2,"价格补偿":1}): raise ValueError("included_category_distribution_invalid")
    return result

def report(rows, gold_sha):
    sources=Counter((r["decision_source"],r["final_included"]) for r in rows)
    def lines(subset):
        total=len(subset); inc=[r for r in subset if r["final_included"]=="yes"]
        cats=Counter(r["gold_category"] for r in inc); reasons=Counter(r["exclude_reason"] for r in subset if r["final_included"]=="no")
        cat_order=["商品咨询","退货退款","物流发货","尺码问题","其他","换货","运费","价格补偿","质量问题"]
        category_text=", ".join(k+": "+str(cats[k]) for k in cat_order)
        return f"reviewed={total}; included={len(inc)}; excluded={total-len(inc)}; inclusion_rate={len(inc)/total:.2%}; categories={{{category_text}}}; exclude_reasons={dict(sorted(reasons.items()))}"
    return "\n".join([
        "# external_store_v1 adjudicated review report", "", "## Frozen inputs and validation", "",
        f"- Primary SHA-256: `{prep.PRIMARY_SHA256}`", f"- Secondary SHA-256: `{prep.SECONDARY_SHA256}`", f"- Adjudication SHA-256: `{ADJUDICATION_SHA256}`", "- Adjudication validation: VALID; 16 rows, 35 columns, fixed 16-ID scope, 47 disputed fields resolved. R3 dated 2026-07-20.", "",
        "## Merge and final outcome", "", "- Merge: primary frozen question/answer; 96 primary-only, 8 dual agreements, 16 adjudicated.", f"- Decision sources: primary_only included/excluded={sources['primary_only','yes']}/{sources['primary_only','no']}; dual_agreement={sources['dual_agreement','yes']}/{sources['dual_agreement','no']}; adjudicated={sources['adjudicated','yes']}/{sources['adjudicated','no']}.", f"- Overall: {lines(rows)}", "- Status changes: R011, R054, R061, R064, R095.", f"- Gold-51 SHA-256: `{gold_sha}`", "",
        "## Authoritative sample strata", "", f"- representative: {lines([r for r in rows if r['sample_group']=='representative'])}", f"- risk: {lines([r for r in rows if r['sample_group']=='risk'])}", "- Overall 42.50% is the frozen 120-sample approval rate, not a natural-quality estimate for the 21,132-candidate pool: risk was purposively oversampled. The representative subset better describes ordinary candidates; risk tests role inference, parsing anomalies, and threshold boundaries.", "",
        "## Pre-adjudication agreement (retain for paper)", "", "- pair_valid 0.8750, κ 0.5135; question_self_contained 0.6250, κ 0.1429; answer_relevance 0.5417, κ 0.3333 (weighted κ 0.4783); role_pairing_correct 1.0000, κ N/A; answer_usable_as_reference 0.6667, κ 0.3962; residual_pii_found 0.9583, κ 0.0000; gold_category 1.0000, κ 1.0000; exclude_reason 0.3750, κ 0.1910; final inclusion 0.7083, κ 0.4167.", "- PII κ=0 reflects class imbalance, not zero agreement. Lower self-contained/relevance agreement indicates subjective difficulty and motivates adjudication. Final labels establish gold labels and do not replace reviewer agreement.", "",
        "## Reproduction and limits", "", "- Run `PYTHONDONTWRITEBYTECODE=1 python scripts/finalize_external_review_adjudication.py` and the three review test modules.", "- This is a held-out real external Gold Set component; boundary items are not yet combined. No model-answer evaluation has been run.", ""])

def finalize(final=FINAL, gold=GOLD, gold_manifest=GOLD_MANIFEST, report_path=REPORT):
    rows=merge(); write_csv(final, FINAL_FIELDS, rows)
    gold_rows=[{"review_id":r["review_id"],"question":r["question"],"reference_answer":r["answer"],"gold_category":r["gold_category"],"sample_group":r["sample_group"],"risk_reason":r["risk_reason"],"external_candidate_id":r["external_candidate_id"],"external_session_id":r["external_session_id"]} for r in rows if r["final_included"]=="yes"]
    if len(gold_rows)!=51 or len({r["review_id"] for r in gold_rows})!=51 or len({r["external_session_id"] for r in gold_rows})!=51 or any(r["gold_category"]=="invalid" for r in gold_rows): raise ValueError("gold_invalid")
    write_csv(gold, GOLD_FIELDS, gold_rows); write_csv(gold_manifest, ["review_id","external_candidate_id","external_session_id","sample_group","risk_reason"], [{k:r[k] for k in ("review_id","external_candidate_id","external_session_id","sample_group","risk_reason")} for r in gold_rows])
    Path(report_path).parent.mkdir(parents=True, exist_ok=True); Path(report_path).write_text(report(rows,digest(gold)),encoding="utf-8",newline="\n")
    return {"final_sha256":digest(final),"gold_sha256":digest(gold),"rows":len(rows)}
if __name__=="__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--final",type=Path,default=FINAL); parser.add_argument("--gold",type=Path,default=GOLD); parser.add_argument("--gold-manifest",type=Path,default=GOLD_MANIFEST); parser.add_argument("--report",type=Path,default=REPORT); args=parser.parse_args(); print(finalize(args.final,args.gold,args.gold_manifest,args.report))
