"""Offline safety and structural tests for the formal runner."""
from __future__ import annotations
import copy, csv, hashlib, inspect, io, json, os, sys, tempfile, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"scripts"))
import run_formal_evaluation as runner

class E(Exception):
 def __init__(self, status_code): self.status_code=status_code
class RunnerTests(unittest.TestCase):
 def setUp(self): self.plan=runner.build_plan()
 def _first_context_pair(self):
  first=next(x for x in self.plan if x["rq"]=="RQ3" and x["system_config_id"]=="context_aware" and x["turn_index"]==1)
  second=next(x for x in self.plan if x["rq"]=="RQ3" and x["system_config_id"]=="context_aware" and x["case_id"]==first["case_id"] and x["turn_index"]==2)
  return first,second,self.plan.index(first)+1
 def _checkpointed_first(self, directory):
  first,second,limit=self._first_context_pair(); calls=[]
  def context(unit, attempt, snapshot):
   calls.append((unit["request_id"],attempt,snapshot))
   return runner.fake_executor(unit,attempt)
  runner.run_plan(self.plan,directory,context_executor=context,max_new_successes=limit)
  return first,second,calls
 def test_frozen_and_plan(self):
  self.assertEqual(runner.FROZEN,runner.verify_frozen()); self.assertEqual(190,len(self.plan))
  self.assertEqual({"RQ1":102,"RQ2":40,"RQ3":48},{x:sum(u["rq"]==x for u in self.plan) for x in ("RQ1","RQ2","RQ3")})
  self.assertEqual(190,len({u["request_id"] for u in self.plan})); self.assertEqual(190,len({u["case_id"]+str(u["turn_index"])+u["system_config_id"] for u in self.plan}))
  self.assertEqual(71,sum(u["system_config_id"]=="qa_only_reconstructed_baseline" for u in self.plan)); self.assertEqual(71,sum(u["system_config_id"]=="v2" for u in self.plan)); self.assertEqual(24,sum(u["system_config_id"]=="single_turn" for u in self.plan)); self.assertEqual(24,sum(u["system_config_id"]=="context_aware" for u in self.plan))
  self.assertEqual("4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5",runner.plan_fingerprint(self.plan))
  expected_bytes="".join(runner.canonical(unit)+"\r\n" for unit in self.plan).encode("utf-8")
  self.assertEqual(runner.PLAN_FINGERPRINT,hashlib.sha256(expected_bytes).hexdigest())
  self.assertEqual("v21b_context_aware",runner.formal_system_id("context_aware"))
 def test_formal_system_identity_resolver_rejects_paths_and_mismatches(self):
  expected={"qa_only_reconstructed_baseline":"qa_only_reconstructed_baseline","v2":"current_v2","single_turn":"v2_without_context_management","context_aware":"v21b_context_aware"}
  self.assertEqual(expected,runner.resolve_formal_system_ids(expected))
  for value in ("semantic_id-2","v2_without_context_management","qa_only_reconstructed_baseline"):
   self.assertFalse(runner._path_like_formal_id(value))
  for value in ("evaluation/formal_qa_only_baseline_spec.json","a/b","a\\b","item.json","/absolute","./relative","../relative","C:\\path","file:///path","https://example.invalid/id"):
   self.assertTrue(runner._path_like_formal_id(value))
  mutations=[]
  missing=copy.deepcopy(expected); del missing["v2"]; mutations.append(missing)
  extra=copy.deepcopy(expected); extra["unknown"]="unknown_id"; mutations.append(extra)
  duplicate=copy.deepcopy(expected); duplicate["v2"]=expected["single_turn"]; mutations.append(duplicate)
  unknown=copy.deepcopy(expected); unknown["v2"]="unknown_formal_id"; mutations.append(unknown)
  swapped=copy.deepcopy(expected); swapped["single_turn"]="context_aware"; mutations.append(swapped)
  path=copy.deepcopy(expected); path["qa_only_reconstructed_baseline"]="evaluation/formal_qa_only_baseline_spec.json"; mutations.append(path)
  for mapping in mutations:
   with self.assertRaises(runner.Blocked): runner.resolve_formal_system_ids(mapping)
 def test_baseline_success_row_uses_identity_not_spec_path_and_resume_rejects_legacy_path(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); baseline=next(unit for unit in self.plan if unit["system_config_id"]=="qa_only_reconstructed_baseline")
   runner.run_plan(self.plan,path,max_new_successes=self.plan.index(baseline)+1)
   rows=runner.load_jsonl(path/"responses.jsonl"); row=next(row for row in rows if row["request_id"]==baseline["request_id"])
   self.assertEqual("qa_only_reconstructed_baseline",row["system_config_id"]); self.assertEqual("qa_only_reconstructed_baseline",row["formal_system_id"]); self.assertNotEqual("evaluation/formal_qa_only_baseline_spec.json",row["formal_system_id"])
   row["formal_system_id"]="evaluation/formal_qa_only_baseline_spec.json"; runner.write_jsonl(path/"responses.jsonl",rows)
   with self.assertRaises(runner.Blocked): runner.run_plan(self.plan,path,max_new_successes=1)
 def test_corrected_manifest_sha_is_a_frozen_gate(self):
  self.assertEqual("1c1c803d50a25a611c0317923cb2d60b668d0d9973b232fa89ab135ce4d3dc18",runner.FROZEN["evaluation/formal_evaluation_manifest.json"])
  actual=runner.file_sha
  for replacement in ("38f29a9714168b8b319023fb64c650e01051c7180727ac623e7c4ae8426b6d7c","0"*64):
   def tampered(path, value=replacement): return value if path==runner.ROOT/"evaluation/formal_evaluation_manifest.json" else actual(path)
   with patch("run_formal_evaluation.file_sha",side_effect=tampered):
    with self.assertRaises(runner.Blocked): runner.verify_frozen()
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
  # Execution resolves the permitted Turn-1 response, while the full frozen
  # plan fingerprint remains stable.
  with tempfile.TemporaryDirectory() as t:
   seen=[]
   runner.run_plan(self.plan,Path(t),lambda u,a: (seen.append(u),runner.fake_executor(u,a))[1])
   second=next(x for x in seen if x["rq"]=="RQ3" and x["case_id"]=="M001" and x["system_config_id"]=="context_aware" and x["turn_index"]==2)
   self.assertTrue(second["payload"]["history"][0]["assistant_answer"].startswith("DRY_RUN_NOT_MODEL_OUTPUT"))
 def test_dry_run_has_no_dotenv_network_or_model(self):
  with tempfile.TemporaryDirectory() as t, patch("run_formal_evaluation.load_dotenv",side_effect=AssertionError("dotenv"),create=True), patch("run_formal_evaluation.create_client",side_effect=AssertionError("network"),create=True), patch("run_formal_evaluation.load_model",side_effect=AssertionError("model"),create=True):
   runner.prepare(Path(t)); self.assertFalse((Path(t)/"responses.jsonl").read_text(encoding="utf-8").find("DRY_RUN_NOT_MODEL_OUTPUT")<0)
 def test_real_gate(self):
  class A: mode="real"; confirm_real_api=None; output=Path("nope")
  with self.assertRaises(runner.Blocked): runner.real_gate(A())
  A.confirm_real_api=runner.CONFIRM
  with patch("run_formal_evaluation.clean_worktree",return_value=False):
   with self.assertRaises(runner.Blocked): runner.real_gate(A())
 def test_lock_resume_retry_and_mismatch(self):
  with tempfile.TemporaryDirectory() as t:
   calls=[]
   def okay(u,a): calls.append(a); return runner.fake_executor(u,a)
   runner.run_plan(self.plan,Path(t),okay,max_new_successes=1); runner.run_plan(self.plan,Path(t),okay,max_new_successes=1); self.assertEqual([1,1],calls)
   rows=runner.load_jsonl(Path(t)/"responses.jsonl"); rows[0]["payload_sha256"]="bad"; runner.write_jsonl(Path(t)/"responses.jsonl",rows)
   with self.assertRaises(runner.Blocked): runner.run_plan(self.plan,Path(t),okay)
  with tempfile.TemporaryDirectory() as t:
   legacy={"request_id":"legacy-v1","system_config_id":"v1_qa_top5","payload_sha256":"x","execution_status":"success"}
   runner.write_jsonl(Path(t)/"responses.jsonl",[legacy])
   with self.assertRaises(runner.Blocked): runner.run_plan(self.plan,Path(t),okay)
  with tempfile.TemporaryDirectory() as t:
   calls=[]
   def flaky(u,a):
    calls.append(a)
    if a<3: raise TimeoutError()
    return runner.fake_executor(u,a)
   runner.run_plan(self.plan,Path(t),flaky,max_new_successes=1); self.assertEqual([1,2,3],calls)
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(runner.Blocked): runner.run_plan(self.plan,Path(t),lambda u,a: (_ for _ in ()).throw(E(503)),max_new_successes=1)
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
 def test_checkpoint_resume_only_executes_turn_two_and_preserves_provenance(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,calls=self._checkpointed_first(path)
   self.assertEqual([(first["request_id"],1,None)],calls)
   checkpoint=runner._checkpoint_path(path,first); self.assertTrue(checkpoint.exists())
   resumed=[]
   def context(unit, attempt, snapshot):
    resumed.append((unit["request_id"],attempt,snapshot))
    return runner.fake_executor(unit,attempt)
   runner.run_plan(self.plan,path,context_executor=context,max_new_successes=1)
   self.assertEqual([second["request_id"]],[x[0] for x in resumed])
   row=runner.load_jsonl(path/"responses.jsonl")[-1]
   self.assertEqual(runner.sha(runner._load_checkpoint(checkpoint,first,second,self.plan)["runtime_snapshot"]),row["checkpoint_snapshot_sha256"])
 def test_checkpoint_identity_and_hash_tampering_fail_closed(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path); checkpoint=runner._checkpoint_path(path,first)
   original=json.loads(checkpoint.read_text(encoding="utf-8"))
   mutations=(
    ("system_config_id","wrong"), ("dialogue_id","wrong"),
    ("turn_one_payload_sha256","0" * 64), ("turn_one_response_sha256","0" * 64),
    ("plan_fingerprint","0" * 64), ("runtime_snapshot_sha256","0" * 64),
   )
   for key,value in mutations:
    changed=json.loads(json.dumps(original)); changed[key]=value; checkpoint.write_text(json.dumps(changed),encoding="utf-8")
    with self.assertRaises(runner.Blocked): runner._load_checkpoint(checkpoint,first,second,self.plan)
   checkpoint.write_text(json.dumps(original),encoding="utf-8")
   changed=json.loads(json.dumps(original)); changed["runtime_snapshot"]["schema_version"]=99; checkpoint.write_text(json.dumps(changed),encoding="utf-8")
   with self.assertRaises(runner.Blocked): runner._load_checkpoint(checkpoint,first,second,self.plan)
 def test_turn_two_retry_restarts_from_same_snapshot_and_persistence_failure_does_not_recall(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path); snapshots=[]
   def flaky(unit, attempt, snapshot):
    if unit["request_id"]!=second["request_id"]: return runner.fake_executor(unit,attempt)
    snapshots.append(json.loads(json.dumps(snapshot)))
    if attempt==1:
     snapshot["conversation_state"]["current_topic"]="mutated"; raise TimeoutError()
    return runner.fake_executor(unit,attempt)
   runner.run_plan(self.plan,path,context_executor=flaky,max_new_successes=1)
   self.assertEqual(2,len(snapshots)); self.assertEqual(snapshots[0],snapshots[1])
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path); calls=[]
   original=runner.atomic_append_jsonl
   def fail_append(p,row):
    if row["request_id"]==second["request_id"]: raise OSError("synthetic persistence failure")
    return original(p,row)
   with patch("run_formal_evaluation.atomic_append_jsonl",side_effect=fail_append):
    with self.assertRaises(runner.Blocked):
     runner.run_plan(self.plan,path,context_executor=lambda u,a,s: (calls.append(u["request_id"]),runner.fake_executor(u,a))[1],max_new_successes=1)
   self.assertEqual([second["request_id"]],calls)
 def test_completed_turn_two_checkpoint_conflict_fails_closed(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path)
   runner.run_plan(self.plan,path,max_new_successes=1)
   rows=runner.load_jsonl(path/"responses.jsonl")
   target=next(x for x in rows if x["request_id"]==second["request_id"]); target["checkpoint_snapshot_sha256"]="bad"
   runner.write_jsonl(path/"responses.jsonl",rows)
   with self.assertRaises(runner.Blocked): runner.run_plan(self.plan,path,max_new_successes=1)

 def test_plan_fingerprint_binds_full_ordered_plan_and_checkpoint(self):
  original=runner.plan_fingerprint(self.plan)
  mutations=[]
  payload=json.loads(json.dumps(self.plan)); payload[0]["payload"]["generation"]["model"]="mutated"; mutations.append(payload)
  user=json.loads(json.dumps(self.plan)); user[0]["payload"]["user_input"]+=" mutation"; mutations.append(user)
  system=json.loads(json.dumps(self.plan)); system[0]["system_config_id"]="mutated"; mutations.append(system)
  turn=json.loads(json.dumps(self.plan)); turn[0]["turn_index"]=2; mutations.append(turn)
  order=json.loads(json.dumps(self.plan)); order[0],order[1]=order[1],order[0]; mutations.append(order)
  self.assertEqual(original,runner.plan_fingerprint(copy.deepcopy(self.plan)))
  self.assertTrue(all(runner.plan_fingerprint(changed)!=original for changed in mutations))
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path)
   unrelated=copy.deepcopy(self.plan); unrelated[0]["payload"]["history"].append({"unexpected":"mutation"})
   checkpoint=runner._checkpoint_path(path,first)
   with self.assertRaises(runner.Blocked):
    runner._load_checkpoint(checkpoint,first,second,unrelated)
   resigned=json.loads(checkpoint.read_text(encoding="utf-8")); changed_sha=runner.plan_fingerprint(unrelated)
   resigned["plan_fingerprint"]=changed_sha; resigned["turn_one_success"]["plan_fingerprint"]=changed_sha
   runner.write_json(checkpoint,resigned)
   with self.assertRaises(runner.Blocked): runner._load_checkpoint(checkpoint,first,second,unrelated)

 def test_checkpoint_rejects_boolean_versions_and_wrong_completed_snapshot(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path); checkpoint=runner._checkpoint_path(path,first)
   original=json.loads(checkpoint.read_text(encoding="utf-8"))
   for value in (True,False):
    changed=copy.deepcopy(original); changed["checkpoint_schema_version"]=value; runner.write_json(checkpoint,changed)
    with self.assertRaises(runner.Blocked): runner._load_checkpoint(checkpoint,first,second,self.plan)
   self.assertEqual(1,runner._load_checkpoint((runner.write_json(checkpoint,original) or checkpoint),first,second,self.plan)["checkpoint_schema_version"])
   for value in (0,2,True,-1):
    changed=copy.deepcopy(original); changed["runtime_snapshot"]["completed_turn_index"]=value
    changed["runtime_snapshot_sha256"]=runner.sha(changed["runtime_snapshot"]); runner.write_json(checkpoint,changed)
    with self.assertRaises(runner.Blocked): runner._load_checkpoint(checkpoint,first,second,self.plan)

 def test_checkpoint_formal_and_configuration_ids_are_distinct_and_bound(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path); checkpoint=runner._checkpoint_path(path,first)
   original=json.loads(checkpoint.read_text(encoding="utf-8"))
   self.assertEqual("context_aware",original["system_config_id"])
   self.assertEqual("v21b_context_aware",original["formal_system_id"])
   runner._load_checkpoint(checkpoint,first,second,self.plan)
   for key,value in (("system_config_id","single_turn"),("formal_system_id","context_aware"),
                     ("formal_system_id",runner.formal_system_id("single_turn"))):
    changed=copy.deepcopy(original); changed[key]=value; runner.write_json(checkpoint,changed)
    with self.assertRaises(runner.Blocked): runner._load_checkpoint(checkpoint,first,second,self.plan)

 def test_embedded_turn_one_full_identity_and_hash_tampering_fails_closed(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path); checkpoint=runner._checkpoint_path(path,first)
   original=json.loads(checkpoint.read_text(encoding="utf-8"))
   mutations=(
    ("request_id","wrong"),("rq","RQ2"),("case_id","wrong"),("turn_index",2),
    ("system_config_id","single_turn"),("formal_system_id","context_aware"),
    ("original_user_input","tampered"),("input_sha256","0"*64),("payload_sha256","0"*64),
    ("resolved_payload_sha256","0"*64),("response_text","tampered"),("response_sha256","0"*64),
    ("plan_fingerprint","0"*64),
   )
   for key,value in mutations:
    changed=copy.deepcopy(original); changed["turn_one_success"][key]=value; runner.write_json(checkpoint,changed)
    with self.assertRaises(runner.Blocked): runner._load_checkpoint(checkpoint,first,second,self.plan)
   changed=copy.deepcopy(original); changed["turn_one_success"]["response_sha256"]="1"*64
   changed["turn_one_response_sha256"]="1"*64; runner.write_json(checkpoint,changed)
   with self.assertRaises(runner.Blocked): runner._load_checkpoint(checkpoint,first,second,self.plan)
   runner.write_json(checkpoint,original)
   rows=runner.load_jsonl(path/"responses.jsonl"); rows.append(copy.deepcopy(rows[0])); runner.write_jsonl(path/"responses.jsonl",rows)
   with self.assertRaisesRegex(runner.Blocked,"DUPLICATE"): runner.run_plan(self.plan,path,max_new_successes=1)

 def test_completed_turn_two_full_identity_response_and_provenance_fail_closed(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,second,_=self._checkpointed_first(path); runner.run_plan(self.plan,path,max_new_successes=1)
   original=runner.load_jsonl(path/"responses.jsonl")
   index=next(i for i,row in enumerate(original) if row["request_id"]==second["request_id"])
   mutations=(
    ("response_text","tampered"),("response_sha256","0"*64),("checkpoint_snapshot_sha256","0"*64),
    ("turn_one_response_sha256","0"*64),("resolved_payload_sha256","0"*64),("input_checkpoint_sha256","0"*64),
    ("rq","RQ2"),("case_id","wrong"),("turn_index",1),("system_config_id","single_turn"),
    ("formal_system_id","context_aware"),("original_user_input","tampered"),("input_sha256","0"*64),
    ("payload_sha256","0"*64),("plan_fingerprint","0"*64),("request_id","wrong"),
   )
   for key,value in mutations:
    changed=copy.deepcopy(original); changed[index][key]=value; runner.write_jsonl(path/"responses.jsonl",changed)
    with self.assertRaises(runner.Blocked): runner.run_plan(self.plan,path,max_new_successes=1)

 def test_turn_one_retry_input_isolation_preserves_plan_and_single_state_advance(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t); first,_,limit=self._first_context_pair(); before=copy.deepcopy(self.plan); before_sha=runner.plan_fingerprint(self.plan); seen=[]
   def context(unit,attempt,snapshot):
    if unit["request_id"]==first["request_id"]:
     seen.append(copy.deepcopy(unit["payload"]))
     if attempt==1:
      unit["payload"]["generation"]["model"]="mutated-by-executor"; unit["payload"]["history"].append({"mutated":True})
      raise TimeoutError()
    return runner.fake_executor(unit,attempt)
   runner.run_plan(self.plan,path,context_executor=context,max_new_successes=limit)
   self.assertEqual(2,len(seen)); self.assertEqual(seen[0],seen[1])
   self.assertEqual(before,self.plan); self.assertEqual(before_sha,runner.plan_fingerprint(self.plan))
   rows=runner.load_jsonl(path/"responses.jsonl"); locked=[row for row in rows if row["request_id"]==first["request_id"]]
   self.assertEqual(1,len(locked)); self.assertEqual(2,locked[0]["attempt_count"])
   checkpoint=runner._load_checkpoint(runner._checkpoint_path(path,first),first,next(x for x in self.plan if x["case_id"]==first["case_id"] and runner._is_context_turn_two(x)),self.plan)
   self.assertEqual(1,checkpoint["runtime_snapshot"]["completed_turn_index"])
   self.assertEqual(0,checkpoint["runtime_snapshot"]["conversation_state"]["state_turn_count"])
   self.assertEqual(1,checkpoint["runtime_snapshot"]["conversation_state"]["updated_at_turn"])

 def test_invalid_max_new_successes_api_and_cli_and_partial_wording(self):
  for value in (True,False,0,-1,1.5,"1"):
   with tempfile.TemporaryDirectory() as t:
    with self.assertRaises(ValueError): runner.run_plan(self.plan,Path(t),max_new_successes=value)
  with tempfile.TemporaryDirectory() as t:
   runner.run_plan(self.plan,Path(t),max_new_successes=1)
   self.assertEqual(1,len(runner.load_jsonl(Path(t)/"responses.jsonl")))
  for args in (("--max-new-successes","0"),("--max-new-successes","-1"),("--max-new-successes","abc"),("--max-new-successes",)):
   with self.assertRaises(SystemExit): runner.main(list(args))
  with tempfile.TemporaryDirectory() as t:
   output=io.StringIO()
   with redirect_stdout(output): self.assertEqual(0,runner.main(["--output",t,"--max-new-successes","1"]))
   text=output.getvalue(); self.assertIn("frozen plan contains 190 units",text); self.assertIn("added 1 new successes",text)
   self.assertIn("total locked successes is 1",text); self.assertIn("remaining units is 189",text)
   self.assertNotIn("COMPLETE: 190 response units",text)
class StageB2RunnerSignatureTests(unittest.TestCase):
 def test_offline_wrapper_exact_persistence_signature(self):
  signature=inspect.signature(runner.orchestrate_offline_unit)
  self.assertEqual(
   ["plan","unit","journal_persistence_callback","retry_predecessor","dependencies"],
   list(signature.parameters),
  )
  self.assertIsNone(signature.parameters["journal_persistence_callback"].default)
  self.assertIsNone(signature.parameters["retry_predecessor"].default)

 def test_durable_public_signatures_reject_dependency_injection(self):
  self.assertEqual(["plan"],list(inspect.signature(runner.build_durable_run_contract).parameters))
  self.assertEqual(["plan"],list(inspect.signature(runner.durable_progress).parameters))
  self.assertEqual(
   ["plan","unit"],
   list(inspect.signature(runner.orchestrate_durable_offline_unit).parameters),
  )

if __name__=="__main__": unittest.main()
