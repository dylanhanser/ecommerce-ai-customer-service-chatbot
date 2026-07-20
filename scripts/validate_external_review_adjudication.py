"""Validate human adjudication without exposing QA text in diagnostics."""
from __future__ import annotations
import argparse, csv, re
from datetime import date
from pathlib import Path
import prepare_external_review_adjudication as prep
from validate_external_review_annotations import ALLOWED
from evaluate_external_review_agreement import FIELDS

PII = re.compile(r"(?:[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\+?\d[\d\s().-]{6,}\d|\d{7,})")
def err(aid, rid, field, kind): return f"{aid or 'A000'}:{rid or 'NONE'}:{field}:{kind}"
def final_missing(row, field, disputed):
    """A blank exclude reason is valid only after a human identifies the adjudication."""
    return field in disputed and not row.get(f"{field}_final", "") and (field != "exclude_reason" or not row.get("adjudicator_id", ""))
def read_template(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames != prep.ADJUDICATION_FIELDS: return None, [err("", "", "columns", "invalid")]
        return list(reader), []
def validate(path=prep.OUTPUT):
    rows, errors = read_template(path)
    if rows is None: return errors, 0
    expected = prep.build_rows(); by_id = {r["review_id"]: r for r in expected}; ids = [r.get("review_id", "") for r in rows]
    template_incomplete = any(final_missing(r, field, set(by_id.get(r.get("review_id", ""), {}).get("disputed_fields", "").split(","))) for r in rows for field in FIELDS)
    if len(rows) != 16: errors.append(err("", "", "row_count", "invalid"))
    if len(set(ids)) != len(ids): errors.append(err("", "", "review_id", "duplicate"))
    incomplete = 0
    for index, row in enumerate(rows):
        aid, rid = row.get("adjudication_id", ""), row.get("review_id", "")
        expected_aid = f"A{index + 1:03d}"
        if aid != expected_aid: errors.append(err(aid, rid, "adjudication_id", "invalid_order_or_value"))
        base = by_id.get(rid)
        if not base: errors.append(err(aid, rid, "review_id", "unknown_or_order_invalid")); continue
        for field in ("question", "answer", "disputed_fields", "eligibility_primary", "eligibility_secondary", "eligibility_disagreement", *[f"{f}_{side}" for f in FIELDS for side in ("primary", "secondary")]):
            if row[field] != base[field]: errors.append(err(aid, rid, field, "modified"))
        disputed = set(base["disputed_fields"].split(","))
        for field in FIELDS:
            value, fixed = row[f"{field}_final"], base[f"{field}_final"]
            if field not in disputed and value != fixed: errors.append(err(aid, rid, f"{field}_final", "agreed_value_modified"))
            elif field in disputed:
                if final_missing(row, field, disputed): incomplete += 1
                elif value not in ALLOWED[field]: errors.append(err(aid, rid, f"{field}_final", "invalid_label"))
        if not template_incomplete:
            if not row["adjudicator_id"]: errors.append(err(aid, rid, "adjudicator_id", "required"))
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["adjudication_date"]): raise ValueError
                date.fromisoformat(row["adjudication_date"])
            except ValueError: errors.append(err(aid, rid, "adjudication_date", "invalid_or_required"))
        if PII.search(row["adjudication_notes"]): errors.append(err(aid, rid, "adjudication_notes", "possible_pii"))
        if not any(final_missing(row, f, disputed) for f in disputed):
            gate = all((row["pair_valid_final"] == "yes", row["question_self_contained_final"] == "yes", row["answer_relevance_final"] == "yes", row["role_pairing_correct_final"] == "yes", row["answer_usable_as_reference_final"] == "yes", row["residual_pii_found_final"] == "no", row["gold_category_final"] != "invalid"))
            reason = row["exclude_reason_final"]
            if (gate and reason) or (not gate and not reason): errors.append(err(aid, rid, "exclude_reason_final", "inconsistent_with_eligibility"))
    if ids != prep.EXPECTED_IDS: errors.append(err("", "", "review_id", "missing_or_order_invalid"))
    return errors, incomplete
if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("template", nargs="?", default=prep.OUTPUT); args = parser.parse_args(); errors, incomplete = validate(args.template)
    if errors:
        print("INVALID"); print("\n".join(errors)); raise SystemExit(1)
    if incomplete:
        print(f"INCOMPLETE  {incomplete} DISPUTED FINAL CELLS REQUIRE HUMAN ADJUDICATION"); raise SystemExit(2)
    print("VALID"); raise SystemExit(0)
