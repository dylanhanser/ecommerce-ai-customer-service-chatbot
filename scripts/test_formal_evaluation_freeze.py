"""Offline structural checks for the formal evaluation freeze."""
from __future__ import annotations
import hashlib, json, sys, unittest
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name): return json.loads((ROOT/name).read_text(encoding="utf-8"))
def sha(name): return hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
class FormalFreezeTests(unittest.TestCase):
 def test_rq1_schema(self):
  x=load("evaluation/formal_rq1_scoring_schema.json"); self.assertEqual(4,len(x["dimensions"])); self.assertEqual([0,8],[x["quality_total"]["minimum"],x["quality_total"]["maximum"]]); self.assertEqual(6,x["acceptable"]["quality_total_at_least"]); self.assertTrue(x["acceptable"]["all_dimensions_nonzero"])
 def test_rq2_structure(self):
  x=load("evaluation/formal_rq2_boundary_cases.json")["cases"]; self.assertEqual(20,len(x)); self.assertEqual(Counter(c["category"] for c in x),Counter({"backend_required":4,"financial_commitment":4,"identity_handover":4,"ambiguous_emotional":4,"normal_control":4})); self.assertEqual(16,sum(c["category"]!="normal_control" for c in x)); self.assertEqual(20,len({c["case_id"] for c in x}))
 def test_rq3_structure(self):
  x=load("evaluation/formal_rq3_multiturn_cases.json")["cases"]; self.assertEqual(12,len(x)); self.assertEqual(Counter(c["scenario_type"] for c in x),Counter({"backend_inheritance":3,"financial_inheritance":3,"aftersales_inheritance":3,"state_reset":3})); self.assertEqual(12,sum(len(c["turns"])==2 and c["turns"][1]["critical_turn"] for c in x)); self.assertEqual(3,sum(c["reset_expected"] for c in x)); self.assertEqual(12,len({c["dialogue_id"] for c in x}))
 def test_gold_and_manifest(self):
  m=load("evaluation/formal_evaluation_manifest.json"); self.assertEqual("773535bf13c1d2a80ebff5410c2f16c96b6f297b2b3f17cd99628165b26fc444",sha("data/external_eval/review/final/external_store_v1_gold_51.csv")); self.assertTrue(m["execution_not_started"]); self.assertEqual(20260721,m["base_seed"]); self.assertEqual("deepseek-chat",m["generator"]["model"]); self.assertEqual(0.0,m["generator"]["evaluation_temperature"])
 def test_json_is_canonical_and_no_secrets(self):
  for p in (ROOT/"evaluation").glob("formal_*.json"):
   text=p.read_text(encoding="utf-8"); self.assertTrue(text.endswith("\n")); self.assertEqual(text,json.dumps(json.loads(text),ensure_ascii=False,indent=2)+"\n"); self.assertNotRegex(text.lower(),r"api[_-]?key|secret|sender|c:\\\\")
if __name__=="__main__": unittest.main()
