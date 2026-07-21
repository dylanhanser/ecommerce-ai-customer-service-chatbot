"""Offline safety and structural tests for the formal runner."""
from __future__ import annotations
import csv, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"scripts"))
import run_formal_evaluation as runner

class E(Exception):
 def __init__(self, status_code): self.status_code=status_code
class RunnerTests(unittest.TestCase):
 def setUp(self): self.plan=runner.build_plan()
 def test_frozen_and_plan(self):
  self.assertEqual(runner.FROZEN,runner.verify_frozen()); self.assertEqual(190,len(self.plan))
  self.assertEqual({"RQ1":102,"RQ2":40,"RQ3":48},{x:sum(u["rq"]==x for u in self.plan) for x in ("RQ1","RQ2","RQ3")})
  self.assertEqual(190,len({u["request_id"] for u in self.plan})); self.assertEqual(190,len({u["case_id"]+str(u["turn_index"])+u["system_config_id"] for u in self.plan}))
  self.assertEqual(71,sum(u["system_config_id"]=="qa_only_reconstructed_baseline" for u in self.plan)); self.assertEqual(71,sum(u["system_config_id"]=="v2" for u in self.plan)); self.assertEqual(24,sum(u["system_config_id"]=="single_turn" for u in self.plan)); self.assertEqual(24,sum(u["system_config_id"]=="context_aware" for u in self.plan))
 def test_fixed_generation_and_no_scoring_leak(self):
  self.assertEqual(0.0,runner.GENERATION["temperature"]); self.assertEqual(1.0,runner.GENERATION["top_p"]); self.assertEqual(512,runner.GENERATION["max_tokens"])
  forbidden={"reference_answer","gold_category","expected_action_type","required_elements","forbidden_elements","pass_rule","critical_turn","expected_state_before"}
  def fields(x):
   if isinstance(x,dict):
    for k,v in x.items(): yield k; yield from fields(v)
   elif isinstance(x,list):
    for v in x: yield from fields(v)
  for u in self.plan: self.assertFalse(forbidden & set(fields(u["payload"])))
 def test_rq3_context_and_single_turn(self):
  units=[u for u in self.plan if u["rq"]=="RQ3"]
  for u in units:
   if u["system_config_id"]=="single_turn": self.assertEqual([],u["payload"]["history"])
  second=[u for u in units if u["system_config_id"]=="context_aware" and u["turn_index"]==2]
  self.assertEqual(12,len(second)); self.assertTrue(all(len(x["payload"]["history"])==1 for x in second))
  # Execution resolves the permitted Turn-1 response, while the plan hash stays stable.
  dialog=sorted((u for u in units if u["case_id"]=="M001" and u["system_config_id"]=="context_aware"),key=lambda x:x["turn_index"])
  with tempfile.TemporaryDirectory() as t:
   seen=[]
   runner.run_plan(dialog,Path(t),lambda u,a: (seen.append(u),runner.fake_executor(u,a))[1])
   self.assertTrue(seen[1]["payload"]["history"][0]["assistant_answer"].startswith("DRY_RUN_NOT_MODEL_OUTPUT"))
 def test_dry_run_has_no_dotenv_network_or_model(self):
  with tempfile.TemporaryDirectory() as t, patch("run_formal_evaluation.load_dotenv",side_effect=AssertionError("dotenv"),create=True), patch("run_formal_evaluation.create_client",side_effect=AssertionError("network"),create=True), patch("run_formal_evaluation.load_model",side_effect=AssertionError("model"),create=True):
   runner.prepare(Path(t)); self.assertFalse((Path(t)/"responses.jsonl").read_text().find("DRY_RUN_NOT_MODEL_OUTPUT")<0)
 def test_real_gate(self):
  class A: mode="real"; confirm_real_api=None; output=Path("nope")
  with self.assertRaises(runner.Blocked): runner.real_gate(A())
  A.confirm_real_api=runner.CONFIRM
  with patch("run_formal_evaluation.clean_worktree",return_value=False):
   with self.assertRaises(runner.Blocked): runner.real_gate(A())
 def test_lock_resume_retry_and_mismatch(self):
  unit=self.plan[:1]
  with tempfile.TemporaryDirectory() as t:
   calls=[]
   def okay(u,a): calls.append(a); return runner.fake_executor(u,a)
   runner.run_plan(unit,Path(t),okay); runner.run_plan(unit,Path(t),okay); self.assertEqual([1],calls)
   rows=runner.load_jsonl(Path(t)/"responses.jsonl"); rows[0]["payload_sha256"]="bad"; runner.write_jsonl(Path(t)/"responses.jsonl",rows)
   with self.assertRaises(runner.Blocked): runner.run_plan(unit,Path(t),okay)
  with tempfile.TemporaryDirectory() as t:
   legacy={"request_id":"legacy-v1","system_config_id":"v1_qa_top5","payload_sha256":"x","execution_status":"success"}
   runner.write_jsonl(Path(t)/"responses.jsonl",[legacy])
   with self.assertRaises(runner.Blocked): runner.run_plan(unit,Path(t),okay)
  with tempfile.TemporaryDirectory() as t:
   calls=[]
   def flaky(u,a):
    calls.append(a)
    if a<3: raise TimeoutError()
    return runner.fake_executor(u,a)
   runner.run_plan(unit,Path(t),flaky); self.assertEqual([1,2,3],calls)
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(runner.Blocked): runner.run_plan(unit,Path(t),lambda u,a: (_ for _ in ()).throw(E(503)))
 def test_templates_blind_and_deterministic(self):
  with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
   runner.prepare(Path(a)); runner.prepare(Path(b))
   rel=["request_plan.jsonl","responses.jsonl","run_manifest.json","scoring/rq1_primary_review.csv","scoring/rq1_secondary_review.csv","scoring/rq1_blind_manifest.json","scoring/rq2_review.csv","scoring/rq2_blind_manifest.json","scoring/rq3_review.csv","scoring/rq3_blind_manifest.json"]
   self.assertTrue(all((Path(a)/x).read_bytes()==(Path(b)/x).read_bytes() for x in rel))
   with (Path(a)/"scoring/rq1_primary_review.csv").open(encoding="utf-8") as f: p=list(csv.DictReader(f))
   with (Path(a)/"scoring/rq1_secondary_review.csv").open(encoding="utf-8") as f: s=list(csv.DictReader(f))
   self.assertEqual(102,len(p)); self.assertEqual(22,len(s)); self.assertEqual(11,len({x["question"] for x in s}))
   self.assertTrue(all(not x["reviewer_id"] and not x["quality_total"] for x in p))
   for name in ("rq1_primary_review.csv","rq2_review.csv","rq3_review.csv"):
    self.assertNotIn("system_config",(Path(a)/"scoring"/name).read_text(encoding="utf-8"))
 def test_ignore_rule(self):
  import subprocess
  with tempfile.TemporaryDirectory(dir=ROOT/"data") as t:
   p=Path(t)/"row.jsonl"; p.write_text("x")
   r=subprocess.run(["git","check-ignore","-v","--no-index","--",str(p)],cwd=ROOT,capture_output=True,text=True)
   self.assertEqual(0,r.returncode)
if __name__=="__main__": unittest.main()
