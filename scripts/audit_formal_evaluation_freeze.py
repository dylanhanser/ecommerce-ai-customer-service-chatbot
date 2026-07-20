"""Read-only formal-freeze audit; never invokes model generation."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
for name in ("evaluation/formal_rq1_scoring_schema.json","evaluation/formal_rq2_boundary_cases.json","evaluation/formal_rq3_multiturn_cases.json","data/external_eval/review/final/external_store_v1_gold_51.csv"):
 print(f"{name}: {hashlib.sha256((ROOT/name).read_bytes()).hexdigest()}")
manifest=json.loads((ROOT/"evaluation/formal_evaluation_manifest.json").read_text(encoding="utf-8"))
print("execution_not_started:",manifest["execution_not_started"])
