"""Build the blank, human-only external_store_v1 adjudication template."""
from __future__ import annotations
import argparse, csv, hashlib
from pathlib import Path

from validate_external_review_annotations import ALLOWED
from evaluate_external_review_agreement import FIELDS

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "data/external_eval/review/final/external_store_v1_primary_review_120_final.csv"
SECONDARY = ROOT / "data/external_eval/review/final/external_store_v1_secondary_review_24_final.csv"
OUTPUT = ROOT / "data/external_eval/review/adjudication/external_store_v1_adjudication_16.csv"
PRIMARY_SHA256 = "cf1c1e9ca76dd76acca50576adfb860ac69a7279ff045eb540e1626c580c2767"
SECONDARY_SHA256 = "874fcfa587aa9619f72ff2fba5595791fef1ddefa26a59b5954d597b731c360a"
REVIEW_FIELDS = ["review_id", "question", "answer", "reviewer_id", "review_date", *FIELDS, "reviewer_notes"]
EXPECTED_IDS = ["R010", "R011", "R013", "R016", "R025", "R030", "R051", "R054", "R061", "R064", "R081", "R095", "R100", "R104", "R105", "R115"]
EXPECTED_FIELD_IDS = {
 "pair_valid": ["R010", "R100", "R105"],
 "question_self_contained": ["R025", "R030", "R051", "R061", "R064", "R095", "R100", "R104", "R115"],
 "answer_relevance": ["R010", "R013", "R030", "R051", "R054", "R061", "R064", "R081", "R095", "R104", "R115"],
 "role_pairing_correct": [],
 "answer_usable_as_reference": ["R011", "R016", "R061", "R064", "R081", "R095", "R104", "R115"],
 "residual_pii_found": ["R025"], "gold_category": [],
 "exclude_reason": ["R010", "R011", "R013", "R025", "R030", "R051", "R054", "R061", "R064", "R081", "R095", "R100", "R104", "R105", "R115"],
}
ADJUDICATION_FIELDS = ["adjudication_id", "review_id", "question", "answer", "disputed_fields", "eligibility_primary", "eligibility_secondary", "eligibility_disagreement", *[item for f in FIELDS for item in (f"{f}_primary", f"{f}_secondary", f"{f}_final")], "adjudicator_id", "adjudication_date", "adjudication_notes"]

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != REVIEW_FIELDS: raise ValueError("input_columns_invalid")
        return list(reader)
def eligible(row):
    return all((row["pair_valid"] == "yes", row["question_self_contained"] == "yes", row["answer_relevance"] == "yes", row["role_pairing_correct"] == "yes", row["answer_usable_as_reference"] == "yes", row["residual_pii_found"] == "no", row["gold_category"] != "invalid", row["exclude_reason"] == ""))
def validate_frozen_inputs(primary=PRIMARY, secondary=SECONDARY):
    if digest(primary) != PRIMARY_SHA256: raise ValueError("primary_sha256_mismatch")
    if digest(secondary) != SECONDARY_SHA256: raise ValueError("secondary_sha256_mismatch")
    p, s = read_csv(primary), read_csv(secondary)
    if len(p) != 120 or len(s) != 24: raise ValueError("input_row_count_invalid")
    pb, sb = {r["review_id"]: r for r in p}, {r["review_id"]: r for r in s}
    if len(pb) != len(p) or len(sb) != len(s) or not set(sb) <= set(pb): raise ValueError("input_ids_invalid")
    if any(sb[i][f] != pb[i][f] for i in sb for f in ("question", "answer")): raise ValueError("input_qa_mismatch")
    return pb, sb
def build_rows(primary=PRIMARY, secondary=SECONDARY):
    pb, sb = validate_frozen_inputs(primary, secondary)
    actual = {f: [i for i in EXPECTED_IDS if pb[i][f] != sb[i][f]] for f in FIELDS}
    ids = [i for i in sorted(sb) if any(pb[i][f] != sb[i][f] for f in FIELDS)]
    if ids != EXPECTED_IDS or actual != EXPECTED_FIELD_IDS or sum(map(len, actual.values())) != 47: raise ValueError("disagreement_scope_mismatch")
    rows = []
    for number, rid in enumerate(ids, 1):
        p, s = pb[rid], sb[rid]; disputed = [f for f in FIELDS if p[f] != s[f]]
        row = {"adjudication_id": f"A{number:03d}", "review_id": rid, "question": p["question"], "answer": p["answer"], "disputed_fields": ",".join(disputed), "eligibility_primary": "yes" if eligible(p) else "no", "eligibility_secondary": "yes" if eligible(s) else "no", "eligibility_disagreement": "yes" if eligible(p) != eligible(s) else "no", "adjudicator_id": "", "adjudication_date": "", "adjudication_notes": ""}
        for f in FIELDS:
            row[f"{f}_primary"], row[f"{f}_secondary"] = p[f], s[f]
            row[f"{f}_final"] = "" if f in disputed else p[f]
        rows.append(row)
    if sum(r["eligibility_disagreement"] == "yes" for r in rows) != 7: raise ValueError("eligibility_scope_mismatch")
    return rows
def write_csv(path, rows):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ADJUDICATION_FIELDS, lineterminator="\r\n")
        writer.writeheader(); writer.writerows(rows)
def build(output=OUTPUT, primary=PRIMARY, secondary=SECONDARY):
    rows = build_rows(primary, secondary); write_csv(output, rows)
    with Path(output).open(encoding="utf-8-sig", newline="") as fh:
        if list(csv.DictReader(fh)) != rows: raise ValueError("output_roundtrip_invalid")
    return {"path": str(output), "sha256": digest(output), "rows": len(rows), "disputed_final_cells": 47}
if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=OUTPUT); args = parser.parse_args()
    result = build(args.output); print(f"TEMPLATE_READY rows={result['rows']} disputed_final_cells={result['disputed_final_cells']} sha256={result['sha256']}")
