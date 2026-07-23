#!/usr/bin/env python3
"""Deterministic, offline-safe runner for the frozen formal evaluation.

Dry-run deliberately produces marker strings, never customer-service answers.
The real transport is intentionally a guarded stub until separately authorised.
"""
from __future__ import annotations

import argparse, ast, copy, csv, hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

BASE_SEED = 20260721
CONFIRM = "FORMAL_EVAL_20260721"
FROZEN = {
 "data/external_eval/review/final/external_store_v1_gold_51.csv":"773535bf13c1d2a80ebff5410c2f16c96b6f297b2b3f17cd99628165b26fc444",
 "evaluation/formal_evaluation_manifest.json":"1c1c803d50a25a611c0317923cb2d60b668d0d9973b232fa89ab135ce4d3dc18",
 "evaluation/formal_qa_only_baseline_spec.json":"ea776d7cd43e76cad9f42874a0d9da0fb9b0abd4007d752ea7cc1794bd5ed399",
 "evaluation/formal_rq1_scoring_schema.json":"a2854a92a5dff3c59215cfef5cc49416a4d64e5c89b0a915d95a43791f4bba9b",
 "evaluation/formal_rq2_boundary_cases.json":"4a5680a7cd21ba434c958b3c3cdd9407a84b77d7f3741b10476fa86fa9851417",
 "evaluation/formal_rq3_multiturn_cases.json":"c534867d93edbed724efd8064c85555b3fbeab89f4bdc58dbebb45a904018b95",
}
GENERATION = {"provider":"DeepSeek","base_url":"https://api.deepseek.com","model":"deepseek-chat","temperature":0.0,"top_p":1.0,"max_tokens":512,"stream":False,"thinking":"not_applicable"}
PLAN_FINGERPRINT = "4d8b22f755d3906762a9d680700fa87fc91155aeceb33e7bce9bb293067f78a5"
CHECKPOINT_SCHEMA_VERSION = 1
FORMAL_SYSTEM_IDS = {
 "qa_only_reconstructed_baseline":"qa_only_reconstructed_baseline",
 "v2":"current_v2",
 "single_turn":"v2_without_context_management",
 "context_aware":"v21b_context_aware",
}
BASELINE_SPECIFICATION_PATH = "evaluation/formal_qa_only_baseline_spec.json"
BASELINE_ADAPTER_PATH = "scripts/formal_qa_only_baseline/adapter.py"

class Blocked(RuntimeError): pass
def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def canonical(x: Any) -> str: return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",",":"))
def sha(x: Any) -> str: return sha_bytes(canonical(x).encode())
def file_sha(p: Path) -> str: return sha_bytes(p.read_bytes())
def derive(namespace: str, *parts: str) -> str: return sha_bytes((namespace+"|"+str(BASE_SEED)+"|"+"|".join(parts)).encode())
def read_json(name: str) -> Any: return json.loads((ROOT/name).read_text(encoding="utf-8"))
def _path_like_formal_id(value: str) -> bool:
 return (not value or "/" in value or "\\" in value or value.lower().endswith(".json")
         or value.startswith(("./","../","/","\\")) or bool(re.match(r"^[A-Za-z]:",value))
         or bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:",value)))
def resolve_formal_system_ids(mapping: object) -> dict[str,str]:
 if not isinstance(mapping,dict) or set(mapping)!=set(FORMAL_SYSTEM_IDS):
  raise Blocked("BLOCKED FORMAL SYSTEM ID MANIFEST")
 values=[]
 for config_id,expected in FORMAL_SYSTEM_IDS.items():
  value=mapping.get(config_id)
  if not isinstance(value,str) or _path_like_formal_id(value) or value!=expected:
   raise Blocked("BLOCKED FORMAL SYSTEM ID MANIFEST")
  values.append(value)
 if len(values)!=len(set(values)):
  raise Blocked("BLOCKED FORMAL SYSTEM ID MANIFEST")
 return dict(mapping)
def _baseline_adapter_system_id() -> str:
 try: tree=ast.parse((ROOT/BASELINE_ADAPTER_PATH).read_text(encoding="utf-8"))
 except (OSError,SyntaxError) as exc: raise Blocked("BLOCKED BASELINE IDENTITY") from exc
 for node in tree.body:
  if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=="SYSTEM_ID" for target in node.targets):
   if isinstance(node.value,ast.Constant) and isinstance(node.value.value,str): return node.value.value
 raise Blocked("BLOCKED BASELINE IDENTITY")
def validate_baseline_identity(mapping: dict[str,str]) -> None:
 try: spec=read_json(BASELINE_SPECIFICATION_PATH)
 except (OSError,json.JSONDecodeError) as exc: raise Blocked("BLOCKED BASELINE IDENTITY") from exc
 expected=FORMAL_SYSTEM_IDS["qa_only_reconstructed_baseline"]
 if mapping["qa_only_reconstructed_baseline"]!=expected or not isinstance(spec,dict) or spec.get("system_id")!=expected or _baseline_adapter_system_id()!=expected:
  raise Blocked("BLOCKED BASELINE IDENTITY")
def formal_system_ids() -> dict[str,str]:
 manifest=read_json("evaluation/formal_evaluation_manifest.json")
 if not isinstance(manifest,dict): raise Blocked("BLOCKED FORMAL SYSTEM ID MANIFEST")
 mapping=resolve_formal_system_ids(manifest.get("formal_system_ids"))
 validate_baseline_identity(mapping)
 return mapping
def formal_system_id(system_config_id: str) -> str:
 mapping=formal_system_ids()
 if not isinstance(system_config_id,str) or system_config_id not in mapping:
  raise Blocked("BLOCKED FORMAL SYSTEM ID MANIFEST")
 return mapping[system_config_id]
def frozen_hashes() -> dict[str,str]: return {p:file_sha(ROOT/p) for p in FROZEN}
def verify_frozen() -> dict[str,str]:
 h=frozen_hashes()
 bad=[p for p in FROZEN if h[p] != FROZEN[p]]
 if bad: raise Blocked("BLOCKED FROZEN INPUT SHA MISMATCH: " + ", ".join(bad))
 formal_system_ids()
 return h
def clean_worktree() -> bool:
 return subprocess.run(["git","status","--short"], cwd=ROOT, text=True, capture_output=True, check=True).stdout == ""
def generation_sha() -> str:
 return sha(GENERATION)
def _legacy_runtime():
 # The legacy dry-run/checkpoint path alone needs the real runtime.  Keeping
 # this import here leaves plan construction and both injected B1 interfaces
 # independent of the real baseline/V2/V2.1b core.
 from formal_evaluation_runtime import (EVALUATION_GENERATION_CONFIG,
  SNAPSHOT_SCHEMA_VERSION, SnapshotValidationError, restore_runtime_snapshot)
 return (EVALUATION_GENERATION_CONFIG,SNAPSHOT_SCHEMA_VERSION,
  SnapshotValidationError,restore_runtime_snapshot)
def _validate_legacy_generation_config() -> None:
 from dataclasses import asdict
 evaluation_config,_,_,_=_legacy_runtime()
 cfg=asdict(evaluation_config)
 if cfg != {k:GENERATION[k] for k in ("temperature","top_p","max_tokens","stream")}:
  raise Blocked("BLOCKED EVALUATION GENERATION CONFIG MISMATCH")

def _payload(user: str, system: str, rq: str, history: list[dict[str,str]] | None=None) -> dict[str,Any]:
 return {"protocol_version":"1.0","rq":rq,"system_config":system,"generation":GENERATION,"user_input":user,"history":history or []}
def _unit(rq: str, case_id: str, turn: int, system: str, user: str, frozen_file: str, history=None) -> dict[str,Any]:
 payload=_payload(user,system,rq,history)
 input_sha=sha_bytes(user.encode())
 rid=derive("formal-evaluation-request-id-v1", "1.0",rq,case_id,str(turn),system,input_sha,generation_sha(),FROZEN[frozen_file])
 return {"request_id":rid,"rq":rq,"case_id":case_id,"turn_index":turn,"system_config_id":system,"input_sha256":input_sha,"payload":payload,"payload_sha256":sha(payload),"frozen_test_file_sha256":FROZEN[frozen_file]}

def build_plan() -> list[dict[str,Any]]:
 gold=[]
 with (ROOT/"data/external_eval/review/final/external_store_v1_gold_51.csv").open(encoding="utf-8-sig",newline="") as f: gold=list(csv.DictReader(f))
 plan=[]
 for row in gold:
  for system in ("qa_only_reconstructed_baseline","v2"):
   u=_unit("RQ1",row["review_id"],1,system,row["question"],"data/external_eval/review/final/external_store_v1_gold_51.csv")
   u["review_id"]=row["review_id"]; plan.append(u)
 for row in read_json("evaluation/formal_rq2_boundary_cases.json")["cases"]:
  for system in ("qa_only_reconstructed_baseline","v2"):
   plan.append(_unit("RQ2",row["case_id"],1,system,row["user_input"],"evaluation/formal_rq2_boundary_cases.json"))
 for dialog in read_json("evaluation/formal_rq3_multiturn_cases.json")["cases"]:
  for system in ("single_turn","context_aware"):
   for i,turn in enumerate(dialog["turns"],1):
    history=[] if system=="single_turn" or i==1 else [{"user_input":dialog["turns"][0]["user_input"],"assistant_answer":"__PRIOR_RESPONSE_BY_SAME_REQUEST_SEQUENCE__"}]
    plan.append(_unit("RQ3",dialog["dialogue_id"],i,system,turn["user_input"],"evaluation/formal_rq3_multiturn_cases.json",history))
 # Namespace SHA-256 defines the fixed execution order. RQ3 pairs retain their
 # causal Turn-1 -> Turn-2 order inside a SHA-256 ordered dialogue/system group.
 def order_key(x):
  if x["rq"]=="RQ3": return ("RQ3",derive("formal-evaluation-execution-order-v1",x["rq"],x["case_id"],x["system_config_id"]),x["turn_index"])
  return (x["rq"],derive("formal-evaluation-execution-order-v1",x["request_id"]),0)
 plan.sort(key=order_key)
 for n,u in enumerate(plan,1): u["execution_order"]=n
 validate_plan(plan); return plan
def validate_plan(plan: list[dict[str,Any]]) -> None:
 from collections import Counter
 if type(plan) is not list or len(plan)!=190: raise Blocked("BLOCKED REQUEST PLAN COUNT")
 if all(type(unit) is dict for unit in plan) and len({unit.get("request_id") for unit in plan})!=190: raise Blocked("BLOCKED DUPLICATE REQUEST ID")
 common={"request_id","rq","case_id","turn_index","system_config_id","input_sha256","payload","payload_sha256","frozen_test_file_sha256","execution_order"}
 payload_fields={"protocol_version","rq","system_config","generation","user_input","history"}
 rq_counts=Counter()
 system_counts=Counter()
 identities=[]
 for unit in plan:
  if type(unit) is not dict: raise Blocked("BLOCKED FORMAL PLAN UNIT SCHEMA")
  rq=unit.get("rq")
  expected_fields=common|({"review_id"} if rq=="RQ1" else set())
  if set(unit)!=expected_fields: raise Blocked("BLOCKED FORMAL PLAN UNIT SCHEMA")
  payload=unit.get("payload")
  if type(payload) is not dict or set(payload)!=payload_fields: raise Blocked("BLOCKED FORMAL PLAN UNIT SCHEMA")
  if (rq not in {"RQ1","RQ2","RQ3"} or type(unit["request_id"]) is not str
      or type(unit["case_id"]) is not str or not unit["case_id"]
      or type(unit["turn_index"]) is not int or unit["turn_index"] not in {1,2}
      or unit["system_config_id"] not in FORMAL_SYSTEM_IDS
      or type(unit["execution_order"]) is not int):
   raise Blocked("BLOCKED UNSUPPORTED PLAN UNIT")
  matrix=((rq in {"RQ1","RQ2"} and unit["system_config_id"] in {"qa_only_reconstructed_baseline","v2"} and unit["turn_index"]==1)
          or (rq=="RQ3" and unit["system_config_id"] in {"single_turn","context_aware"} and unit["turn_index"] in {1,2}))
  if not matrix: raise Blocked("BLOCKED UNSUPPORTED PLAN UNIT")
  expected_frozen={"RQ1":FROZEN["data/external_eval/review/final/external_store_v1_gold_51.csv"],
                   "RQ2":FROZEN["evaluation/formal_rq2_boundary_cases.json"],
                   "RQ3":FROZEN["evaluation/formal_rq3_multiturn_cases.json"]}[rq]
  user=payload.get("user_input")
  if (payload.get("protocol_version")!="1.0" or payload.get("rq")!=rq
      or payload.get("system_config")!=unit["system_config_id"] or payload.get("generation")!=GENERATION
      or type(user) is not str or not user
      or unit["input_sha256"]!=sha_bytes(user.encode("utf-8"))
      or unit["payload_sha256"]!=sha(payload)
      or unit["frozen_test_file_sha256"]!=expected_frozen):
   raise Blocked("BLOCKED FORMAL PLAN PAYLOAD INTEGRITY")
  history=payload["history"]
  if unit["system_config_id"]=="context_aware" and unit["turn_index"]==2:
   if (type(history) is not list or len(history)!=1 or type(history[0]) is not dict
       or set(history[0])!={"user_input","assistant_answer"}
       or type(history[0]["user_input"]) is not str or not history[0]["user_input"]
       or history[0]["assistant_answer"]!="__PRIOR_RESPONSE_BY_SAME_REQUEST_SEQUENCE__"):
    raise Blocked("BLOCKED FORMAL PLAN PAYLOAD INTEGRITY")
  elif history!=[]: raise Blocked("BLOCKED FORMAL PLAN PAYLOAD INTEGRITY")
  if rq=="RQ1" and unit["review_id"]!=unit["case_id"]: raise Blocked("BLOCKED FORMAL PLAN UNIT SCHEMA")
  expected_request=derive("formal-evaluation-request-id-v1","1.0",rq,unit["case_id"],str(unit["turn_index"]),unit["system_config_id"],unit["input_sha256"],generation_sha(),expected_frozen)
  if unit["request_id"]!=expected_request: raise Blocked("BLOCKED FORMAL PLAN REQUEST ID")
  rq_counts[rq]+=1; system_counts[unit["system_config_id"]]+=1
  identities.append((rq,unit["case_id"],unit["turn_index"],unit["system_config_id"]))
 if rq_counts!={"RQ1":102,"RQ2":40,"RQ3":48}: raise Blocked("BLOCKED REQUEST PLAN RQ COUNT")
 if system_counts!={"qa_only_reconstructed_baseline":71,"v2":71,"single_turn":24,"context_aware":24}: raise Blocked("BLOCKED REQUEST PLAN SYSTEM COUNT")
 if [unit["execution_order"] for unit in plan]!=list(range(1,191)): raise Blocked("BLOCKED REQUEST PLAN EXECUTION ORDER")
 if len({unit["request_id"] for unit in plan})!=190: raise Blocked("BLOCKED DUPLICATE REQUEST ID")
 if len(set(identities))!=190: raise Blocked("BLOCKED INCOMPLETE CASE IDS")
 groups={}
 for rq,case_id,turn,system in identities: groups.setdefault((rq,case_id),set()).add((system,turn))
 for (rq,_case_id),members in groups.items():
  expected=({("qa_only_reconstructed_baseline",1),("v2",1)} if rq in {"RQ1","RQ2"}
            else {("single_turn",1),("single_turn",2),("context_aware",1),("context_aware",2)})
  if members!=expected: raise Blocked("BLOCKED INCOMPLETE CASE IDS")
 if _plan_fingerprint_bytes(plan)!=PLAN_FINGERPRINT: raise Blocked("BLOCKED FORMAL PLAN FINGERPRINT MISMATCH")

def _plan_fingerprint_bytes(plan: list[dict[str,Any]]) -> str:
 plan_bytes="".join(canonical(unit)+"\r\n" for unit in plan).encode("utf-8")
 return sha_bytes(plan_bytes)

def plan_fingerprint(plan: list[dict[str,Any]]) -> str:
 # This is the exact byte representation used when the reconstructed-baseline
 # plan was frozen on Windows: ordered canonical JSONL, including final CRLF.
 return _plan_fingerprint_bytes(plan)

def orchestrate_offline_unit(plan: list[dict[str,Any]], unit: dict[str,Any], **dependencies: Any) -> Any:
 """Validate the frozen plan, then enter only the Stage A-backed fake B1 path.

 This path is intentionally separate from ``run_plan`` and never consults the
 legacy dry-run ``retryable`` helper or its marker-output persistence.
 """
 verify_frozen()
 validate_plan(plan)
 if _plan_fingerprint_bytes(plan)!=PLAN_FINGERPRINT: raise Blocked("BLOCKED FORMAL PLAN FINGERPRINT MISMATCH")
 matching=[candidate for candidate in plan if candidate["request_id"]==unit.get("request_id")]
 if len(matching)!=1 or matching[0]!=unit: raise Blocked("BLOCKED SELECTED PLAN UNIT MISMATCH")
 turn_one=None; turn_two=None
 if unit["rq"]=="RQ3" and unit["system_config_id"]=="context_aware":
   turn_one=next((candidate for candidate in plan if candidate["rq"]=="RQ3" and candidate["case_id"]==unit["case_id"] and candidate["system_config_id"]=="context_aware" and candidate["turn_index"]==1),None)
   turn_two=next((candidate for candidate in plan if candidate["rq"]=="RQ3" and candidate["case_id"]==unit["case_id"] and candidate["system_config_id"]=="context_aware" and candidate["turn_index"]==2),None)
   if turn_one is None or turn_two is None: raise Blocked("BLOCKED INCOMPLETE RQ3 CHECKPOINT PAIR")
 supplied_turn_one=dependencies.pop("turn_one_unit",turn_one)
 supplied_turn_two=dependencies.pop("turn_two_unit",turn_two)
 if supplied_turn_one!=turn_one or supplied_turn_two!=turn_two:
  raise Blocked("BLOCKED RQ3 PAIR MISMATCH")
 from formal_evaluation_orchestration import _orchestrate_plan_member
 return _orchestrate_plan_member(unit,turn_one_unit=turn_one,turn_two_unit=turn_two,**dependencies)

def write_json(p: Path, obj: Any) -> None: p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def write_jsonl(p: Path, rows: list[dict[str,Any]]) -> None: p.parent.mkdir(parents=True,exist_ok=True); p.write_text("".join(canonical(r)+"\n" for r in rows),encoding="utf-8")
def load_jsonl(p: Path) -> list[dict[str,Any]]:
 return [] if not p.exists() else [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x]
def atomic_append_jsonl(p: Path, row: dict[str,Any]) -> None:
 rows=load_jsonl(p); rows.append(row)
 with tempfile.NamedTemporaryFile("w",encoding="utf-8",delete=False,dir=p.parent,newline="\n") as f: f.write("".join(canonical(x)+"\n" for x in rows)); tmp=Path(f.name)
 os.replace(tmp,p)
def retryable(exc: BaseException) -> bool:
 return isinstance(exc,(TimeoutError,ConnectionError)) or getattr(exc,"status_code",None)==429 or 500<=getattr(exc,"status_code",0)<600
def fake_executor(unit: dict[str,Any], attempt: int) -> dict[str,Any]:
 marker="DRY_RUN_NOT_MODEL_OUTPUT " + sha_bytes((unit["request_id"]+"|"+unit["payload_sha256"]).encode())[:24]
 result={"response_text":marker,"action_type":"dry_run_unclassified","guard_decision":"not_executed","retrieval_performed":False,"retrieved_ids":[],"retrieval_scores":[],"latency_ms":0}
 if unit["rq"]=="RQ3" and unit["system_config_id"]=="context_aware" and unit["turn_index"]==1:
  _,snapshot_schema_version,_,_=_legacy_runtime()
  result["runtime_snapshot"]={"schema_version":snapshot_schema_version,"completed_turn_index":1,"conversation_state":{"current_topic":"none","query_type":"normal","risk_type":"none","requires_backend_api":False,"last_safe_answer_type":"none","last_user_query":unit["payload"]["user_input"],"last_assistant_answer":marker,"last_retrieval_query":"","last_contextual_query":"","last_successful_contextual_query":"","state_confidence":0.0,"state_turn_count":0,"updated_at_turn":1,"should_reset":False},"previous_user_text":unit["payload"]["user_input"],"previous_assistant_text":marker}
 return result
def resolved_execution_unit(unit: dict[str,Any], known: dict[str,dict[str,Any]]) -> dict[str,Any]:
 """Resolve only the permitted, already-locked prior answer at execution time.

 The plan stores a stable reference marker so its hash never depends on model text.
 """
 execution_unit=copy.deepcopy(unit)
 if unit["rq"]!="RQ3" or unit["system_config_id"]!="context_aware" or unit["turn_index"]!=2: return execution_unit
 prior=next((r for r in known.values() if r["rq"]=="RQ3" and r["case_id"]==unit["case_id"] and r["system_config_id"]==unit["system_config_id"] and r["turn_index"]==1 and r["execution_status"]=="success"),None)
 if prior is None: raise Blocked("BLOCKED MISSING LOCKED RQ3 TURN 1")
 execution_unit["payload"]["history"][0]["assistant_answer"]=prior["response_text"]
 return execution_unit
def _is_context_turn_one(unit: dict[str,Any]) -> bool:
 return unit["rq"]=="RQ3" and unit["system_config_id"]=="context_aware" and unit["turn_index"]==1
def _is_context_turn_two(unit: dict[str,Any]) -> bool:
 return unit["rq"]=="RQ3" and unit["system_config_id"]=="context_aware" and unit["turn_index"]==2
def _checkpoint_path(directory: Path, unit: dict[str,Any]) -> Path:
 return directory/"rq3_checkpoints"/(unit["request_id"]+".json")
def _atomic_json(path: Path, value: dict[str,Any]) -> None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile("w",encoding="utf-8",delete=False,dir=path.parent,newline="\n") as f:
  f.write(canonical(value)+"\n"); tmp=Path(f.name)
 os.replace(tmp,path)
def _runtime_sha() -> str: return file_sha(ROOT/"scripts/formal_evaluation_runtime.py")
def _core_sha() -> str: return file_sha(ROOT/"outputs/rag_answer_demo.py")
_SUCCESS_IDENTITY_FIELDS={"request_id","rq","case_id","turn_index","system_config_id","formal_system_id","original_user_input","input_sha256","payload_sha256","resolved_payload_sha256","plan_fingerprint","execution_status","response_text","response_sha256"}
def _validate_success_row(row: object, unit: dict[str,Any], plan_sha: str, resolved_payload_sha256: str) -> dict[str,Any]:
 if not isinstance(row,dict) or not _SUCCESS_IDENTITY_FIELDS.issubset(row):
  raise Blocked("BLOCKED FORMAL SUCCESS ROW SCHEMA")
 user=unit.get("payload",{}).get("user_input") if isinstance(unit.get("payload"),dict) else None
 if not isinstance(user,str) or unit.get("input_sha256")!=sha_bytes(user.encode("utf-8")) or unit.get("payload_sha256")!=sha(unit.get("payload")):
  raise Blocked("BLOCKED FORMAL PLAN PAYLOAD INTEGRITY")
 expected={
  "request_id":unit["request_id"],"rq":unit["rq"],"case_id":unit["case_id"],
  "system_config_id":unit["system_config_id"],"formal_system_id":formal_system_id(unit["system_config_id"]),
  "original_user_input":user,"input_sha256":unit["input_sha256"],"payload_sha256":unit["payload_sha256"],
  "resolved_payload_sha256":resolved_payload_sha256,"plan_fingerprint":plan_sha,"execution_status":"success",
 }
 if type(row.get("turn_index")) is not int or type(unit.get("turn_index")) is not int or row["turn_index"]!=unit["turn_index"]:
  raise Blocked("BLOCKED FORMAL SUCCESS ROW IDENTITY")
 if any(row.get(key)!=value for key,value in expected.items()):
  raise Blocked("BLOCKED FORMAL SUCCESS ROW IDENTITY")
 response=row.get("response_text")
 if not isinstance(response,str) or row.get("response_sha256")!=sha_bytes(response.encode("utf-8")):
  raise Blocked("BLOCKED FORMAL SUCCESS ROW RESPONSE INTEGRITY")
 return row

def _checkpoint_envelope(turn_one: dict[str,Any], turn_two: dict[str,Any], row: dict[str,Any], snapshot: dict[str,Any], plan: list[dict[str,Any]]) -> dict[str,Any]:
 return {"checkpoint_schema_version":CHECKPOINT_SCHEMA_VERSION,"rq":"RQ3","system_config_id":"context_aware","formal_system_id":formal_system_id("context_aware"),"dialogue_id":turn_one["case_id"],"completed_through_turn":1,"turn_one_request_id":turn_one["request_id"],"turn_one_payload_sha256":turn_one["payload_sha256"],"turn_one_response_sha256":row["response_sha256"],"expected_turn_two_request_id":turn_two["request_id"],"resolved_turn_two_payload_sha256":sha(resolved_execution_unit(turn_two,{turn_one["request_id"]:row})["payload"]),"plan_fingerprint":plan_fingerprint(plan),"runtime_implementation_sha256":_runtime_sha(),"v21b_core_sha256":_core_sha(),"runtime_snapshot":snapshot,"runtime_snapshot_sha256":sha(snapshot),"previous_user_text":snapshot["previous_user_text"],"previous_assistant_text":snapshot["previous_assistant_text"],"turn_one_success":row}
def _load_checkpoint(path: Path, turn_one: dict[str,Any], turn_two: dict[str,Any], plan: list[dict[str,Any]]) -> dict[str,Any]:
 _,_,snapshot_validation_error,restore_runtime_snapshot=_legacy_runtime()
 try: envelope=json.loads(path.read_text(encoding="utf-8"))
 except (OSError,json.JSONDecodeError) as exc: raise Blocked("BLOCKED CORRUPT RQ3 CHECKPOINT") from exc
 required={"checkpoint_schema_version","rq","system_config_id","formal_system_id","dialogue_id","completed_through_turn","turn_one_request_id","turn_one_payload_sha256","turn_one_response_sha256","expected_turn_two_request_id","resolved_turn_two_payload_sha256","plan_fingerprint","runtime_implementation_sha256","v21b_core_sha256","runtime_snapshot","runtime_snapshot_sha256","previous_user_text","previous_assistant_text","turn_one_success"}
 if not isinstance(envelope,dict) or set(envelope)!=required: raise Blocked("BLOCKED RQ3 CHECKPOINT IDENTITY MISMATCH")
 if type(envelope["checkpoint_schema_version"]) is not int or envelope["checkpoint_schema_version"]!=CHECKPOINT_SCHEMA_VERSION:
  raise Blocked("BLOCKED RQ3 CHECKPOINT SCHEMA VERSION")
 if type(envelope["completed_through_turn"]) is not int or envelope["completed_through_turn"]!=1:
  raise Blocked("BLOCKED RQ3 CHECKPOINT COMPLETED TURN")
 plan_sha=plan_fingerprint(plan)
 if plan_sha!=PLAN_FINGERPRINT: raise Blocked("BLOCKED FORMAL PLAN FINGERPRINT MISMATCH")
 expected={"rq":"RQ3","system_config_id":"context_aware","formal_system_id":formal_system_id("context_aware"),"dialogue_id":turn_one["case_id"],"turn_one_request_id":turn_one["request_id"],"turn_one_payload_sha256":turn_one["payload_sha256"],"expected_turn_two_request_id":turn_two["request_id"],"plan_fingerprint":plan_sha,"runtime_implementation_sha256":_runtime_sha(),"v21b_core_sha256":_core_sha()}
 if any(envelope[k]!=v for k,v in expected.items()): raise Blocked("BLOCKED RQ3 CHECKPOINT IDENTITY MISMATCH")
 row=envelope["turn_one_success"]
 _validate_success_row(row,turn_one,plan_sha,turn_one["payload_sha256"])
 if row["response_sha256"]!=envelope["turn_one_response_sha256"]: raise Blocked("BLOCKED RQ3 CHECKPOINT RESPONSE MISMATCH")
 try: snapshot=restore_runtime_snapshot(envelope["runtime_snapshot"])
 except snapshot_validation_error as exc: raise Blocked("BLOCKED INVALID RQ3 RUNTIME SNAPSHOT") from exc
 if snapshot.completed_turn_index!=1: raise Blocked("BLOCKED RQ3 CHECKPOINT COMPLETED TURN")
 if sha(snapshot.to_dict())!=envelope["runtime_snapshot_sha256"] or envelope["previous_user_text"]!=turn_one["payload"]["user_input"] or envelope["previous_user_text"]!=snapshot.previous_user_text or envelope["previous_assistant_text"]!=row["response_text"] or envelope["previous_assistant_text"]!=snapshot.previous_assistant_text: raise Blocked("BLOCKED RQ3 CHECKPOINT SNAPSHOT MISMATCH")
 resolved=resolved_execution_unit(turn_two,{turn_one["request_id"]:row})
 if envelope["resolved_turn_two_payload_sha256"]!=sha(resolved["payload"]): raise Blocked("BLOCKED RQ3 CHECKPOINT TURN 2 PAYLOAD MISMATCH")
 return envelope

def _validate_turn_two_provenance(row: dict[str,Any], envelope: dict[str,Any]) -> None:
 expected={
  "turn_one_response_sha256":envelope["turn_one_response_sha256"],
  "checkpoint_snapshot_sha256":envelope["runtime_snapshot_sha256"],
  "input_checkpoint_sha256":sha(envelope),
 }
 if any(row.get(key)!=value for key,value in expected.items()):
  raise Blocked("BLOCKED COMPLETED TURN 2 CHECKPOINT CONFLICT")

def run_plan(plan: list[dict[str,Any]], directory: Path, executor: Callable[[dict[str,Any],int],dict[str,Any]]=fake_executor, *, context_executor: Callable[[dict[str,Any],int,dict[str,Any] | None],dict[str,Any]] | None=None, max_new_successes: int | None=None, _stats: dict[str,int] | None=None) -> list[dict[str,Any]]:
 _,_,snapshot_validation_error,restore_runtime_snapshot=_legacy_runtime()
 if max_new_successes is not None and (type(max_new_successes) is not int or max_new_successes<=0): raise ValueError("max_new_successes must be a positive integer")
 plan_sha=plan_fingerprint(plan)
 if plan_sha!=PLAN_FINGERPRINT: raise Blocked("BLOCKED FORMAL PLAN FINGERPRINT MISMATCH")
 directory.mkdir(parents=True,exist_ok=True); rp=directory/"responses.jsonl"; loaded=load_jsonl(rp); out=[]
 if any(not isinstance(row,dict) or not isinstance(row.get("request_id"),str) for row in loaded): raise Blocked("BLOCKED FORMAL SUCCESS ROW SCHEMA")
 request_ids=[row["request_id"] for row in loaded]
 if len(request_ids)!=len(set(request_ids)): raise Blocked("BLOCKED DUPLICATE FIRST-SUCCESS ROW")
 existing={row["request_id"]:row for row in loaded}
 expected={x["request_id"]:x for x in plan}
 for rid,row in existing.items():
  if rid not in expected or row.get("system_config_id") != expected[rid]["system_config_id"]:
   raise Blocked("BLOCKED LEGACY OR MIXED FORMAL PLAN RESULTS")
 # Checkpoints are the authoritative first-success record, including a crash after
 # the envelope write but before responses.jsonl can be rebuilt.
 pairs={(u["case_id"],u["system_config_id"]):u for u in plan if _is_context_turn_two(u)}
 for first in (u for u in plan if _is_context_turn_one(u)):
  cp=_checkpoint_path(directory,first)
  if cp.exists():
   envelope=_load_checkpoint(cp,first,pairs[(first["case_id"],first["system_config_id"])],plan); locked=envelope["turn_one_success"]
   if first["request_id"] in existing and existing[first["request_id"]]!=locked: raise Blocked("BLOCKED TURN 1 FIRST-SUCCESS CONFLICT")
   if first["request_id"] not in existing: atomic_append_jsonl(rp,locked); existing[first["request_id"]]=locked
  elif first["request_id"] in existing: raise Blocked("BLOCKED RQ3 TURN 1 HAS NO CHECKPOINT")
 for rid,row in existing.items():
  unit=expected[rid]
  if row.get("execution_status")!="success": raise Blocked("BLOCKED NON-SUCCESS FORMAL RESULT ROW")
  resolved=resolved_execution_unit(unit,existing)
  _validate_success_row(row,unit,plan_sha,sha(resolved["payload"]))
  if _is_context_turn_two(unit):
   first=next(x for x in plan if _is_context_turn_one(x) and x["case_id"]==unit["case_id"])
   envelope=_load_checkpoint(_checkpoint_path(directory,first),first,unit,plan)
   _validate_turn_two_provenance(row,envelope)
 new_successes=0
 for unit in plan:
  if max_new_successes is not None and new_successes>=max_new_successes: break
  old=existing.get(unit["request_id"])
  envelope=None
  if _is_context_turn_two(unit):
   first=next(x for x in plan if _is_context_turn_one(x) and x["case_id"]==unit["case_id"]); envelope=_load_checkpoint(_checkpoint_path(directory,first),first,unit,plan)
  if old:
   if old["execution_status"]=="success": out.append(old); continue
  last=None
  for attempt in range(1,4):
   try:
    resolved=resolved_execution_unit(unit,existing)
    # Revalidate and recreate the boundary on every attempt.  An executor may
    # mutate the object it receives before failing, but that must never affect
    # the next retry or the persisted checkpoint.
    snapshot=None
    if _is_context_turn_two(unit): snapshot=restore_runtime_snapshot(envelope["runtime_snapshot"]).to_dict()
    result=(context_executor(resolved,attempt,snapshot) if context_executor and unit["rq"]=="RQ3" and unit["system_config_id"]=="context_aware" else executor(resolved,attempt)); text=result["response_text"]
    row={k:unit[k] for k in ("request_id","rq","case_id","turn_index","system_config_id","input_sha256","payload_sha256")}
    row.update({"formal_system_id":formal_system_id(unit["system_config_id"]),"original_user_input":unit["payload"]["user_input"],"resolved_payload_sha256":sha(resolved["payload"]),"plan_fingerprint":plan_sha})
    result=dict(result); snapshot_result=result.pop("runtime_snapshot",None); row.update(result); row.update({"response_sha256":sha_bytes(text.encode("utf-8")),"attempt_count":attempt,"timestamp_utc":"DRY_RUN_DETERMINISTIC","execution_status":"success","transport":"fake"})
    if _is_context_turn_one(unit):
     second=pairs[(unit["case_id"],unit["system_config_id"])]
     try: valid_snapshot_object=restore_runtime_snapshot(snapshot_result)
     except snapshot_validation_error as exc: raise Blocked("BLOCKED RQ3 TURN 1 DID NOT PRODUCE VALID SNAPSHOT") from exc
     if valid_snapshot_object.completed_turn_index!=1: raise Blocked("BLOCKED RQ3 TURN 1 SNAPSHOT COMPLETED TURN")
     valid_snapshot=valid_snapshot_object.to_dict()
     _validate_success_row(row,unit,plan_sha,unit["payload_sha256"])
     envelope=_checkpoint_envelope(unit,second,row,valid_snapshot,plan); _atomic_json(_checkpoint_path(directory,unit),envelope)
    if _is_context_turn_two(unit):
     row.update({"turn_one_response_sha256":envelope["turn_one_response_sha256"],"checkpoint_snapshot_sha256":envelope["runtime_snapshot_sha256"],"input_checkpoint_sha256":sha(envelope)})
     _validate_turn_two_provenance(row,envelope)
    _validate_success_row(row,unit,plan_sha,sha(resolved["payload"]))
    atomic_append_jsonl(rp,row); existing[unit["request_id"]]=row; out.append(row); break
   except Exception as exc:
    last=exc
    if not retryable(exc) or attempt==3: raise Blocked("BLOCKED TRANSPORT FAILURE") from exc
  else: raise Blocked("BLOCKED TRANSPORT FAILURE") from last
  new_successes+=1
 if _stats is not None:
  _stats.clear(); _stats.update({"new_successes":new_successes,"total_locked_successes":len(existing),"remaining_units":len(plan)-len(existing)})
 return out

def csv_write(path: Path, fields: list[str], rows: list[dict[str,Any]]) -> None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open("w",encoding="utf-8",newline="") as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore",lineterminator="\n"); w.writeheader(); w.writerows(rows)
def anon(namespace: str, request_id: str) -> str: return derive(namespace,request_id)[:24]
def templates(plan: list[dict[str,Any]], responses: list[dict[str,Any]], d: Path) -> dict[str,int]:
 byid={r["request_id"]:r for r in responses}; scoring=d/"scoring"; gold={}
 with (ROOT/"data/external_eval/review/final/external_store_v1_gold_51.csv").open(encoding="utf-8-sig") as f: gold={x["review_id"]:x for x in csv.DictReader(f)}
 p1=[]; map1=[]
 for u in plan:
  if u["rq"]=="RQ1":
   g=gold[u["case_id"]]; r=byid[u["request_id"]]; aid=anon("rq1-response",u["request_id"])
   p1.append({"response_id":aid,"question":g["question"],"reference_answer":g["reference_answer"],"model_response":r["response_text"],"relevance":"","factual_policy_correctness":"","completeness_actionability":"","safety_boundary_compliance":"","quality_total":"","acceptable":"","primary_error_type":"","reviewer_id":"","review_date":"","reviewer_notes":""})
   map1.append({"response_id":aid,"request_id":u["request_id"],"system_config_id":u["system_config_id"],"review_id":u["case_id"]})
 fields=list(p1[0]); csv_write(scoring/"rq1_primary_review.csv",fields,p1)
 # deterministic category-stratified 11: hash order round-robin categories, then fill.
 cats={};
 for x in gold.values(): cats.setdefault(x["gold_category"],[]).append(x)
 selected=[]
 for cat in sorted(cats): selected.append(sorted(cats[cat],key=lambda x:derive("rq1-secondary",x["review_id"]))[0]["review_id"])
 remain=sorted((x for x in gold if x not in selected),key=lambda x:derive("rq1-secondary-fill",x))
 selected=(selected+remain)[:11]
 p2=[x for x in p1 if next(m for m in map1 if m["response_id"]==x["response_id"])["review_id"] in selected]
 csv_write(scoring/"rq1_secondary_review.csv",fields,p2); write_json(scoring/"rq1_blind_manifest.json",{"mapping":map1,"secondary_review_ids":selected})
 def simple(rq, name, cols):
  rows=[]; mapping=[]
  for u in plan:
   if u["rq"]==rq:
    r=byid[u["request_id"]]; aid=anon(name,u["request_id"]); row={"response_id":aid,"case_id":u["case_id"],"user_input":u["payload"]["user_input"],"model_response":r["response_text"]}
    row.update({c:"" for c in cols}); rows.append(row); mapping.append({"response_id":aid,"request_id":u["request_id"],"system_config_id":u["system_config_id"]})
  csv_write(scoring/("rq2_review.csv" if rq=="RQ2" else "rq3_review.csv"),list(rows[0]),rows); write_json(scoring/("rq2_blind_manifest.json" if rq=="RQ2" else "rq3_blind_manifest.json"),{"mapping":mapping})
  return len(rows)
 n2=simple("RQ2","rq2-response",["route_pass","required_content_pass","forbidden_content_pass","case_pass","reviewer_id","review_date","reviewer_notes"])
 # RQ3 keeps paired turns visible through anonymous_conversation_id; dialogue_id does not reveal treatment.
 rows=[]; mapping=[]
 for u in plan:
  if u["rq"]=="RQ3":
   r=byid[u["request_id"]]; cid=derive("rq3-conversation",u["case_id"],u["system_config_id"])[:24]; aid=anon("rq3-response",u["request_id"])
   rows.append({"anonymous_conversation_id":cid,"dialogue_id":u["case_id"],"turn_index":u["turn_index"],"user_input":u["payload"]["user_input"],"model_response":r["response_text"],"route_pass":"","required_content_pass":"","forbidden_content_pass":"","turn_pass":"","dialogue_pass":"","error_type":"","reviewer_id":"","review_date":"","reviewer_notes":""}); mapping.append({"anonymous_conversation_id":cid,"response_id":aid,"request_id":u["request_id"],"system_config_id":u["system_config_id"]})
 rows.sort(key=lambda x:(x["anonymous_conversation_id"],x["turn_index"])); csv_write(scoring/"rq3_review.csv",list(rows[0]),rows); write_json(scoring/"rq3_blind_manifest.json",{"mapping":mapping})
 return {"rq1_primary":len(p1),"rq1_secondary":len(p2),"rq2":n2,"rq3":len(rows)}

def prepare(directory: Path, *, max_new_successes: int | None=None) -> dict[str,Any]:
 hashes=verify_frozen(); _validate_legacy_generation_config(); plan=build_plan(); write_jsonl(directory/"request_plan.jsonl",plan); stats={}; run_plan(plan,directory,max_new_successes=max_new_successes,_stats=stats); responses=load_jsonl(directory/"responses.jsonl"); counts=templates(plan,responses,directory) if len(responses)==len(plan) else {}
 manifest={"protocol_version":"1.1","base_seed":BASE_SEED,"frozen_input_sha256":hashes,"generation":GENERATION,"transport":"fake","responses_are_not_model_outputs":True,"request_count":190,"plan_fingerprint":plan_fingerprint(plan),"invocation_new_successes":stats["new_successes"],"total_locked_successes":stats["total_locked_successes"],"remaining_units":stats["remaining_units"],"system_configurations":{"qa_only_reconstructed_baseline":{"corpus":"qa_only","qa_count":15333,"top_k":5},"v2":{"corpus":"mixed","qa_count":15333,"snippet_count":355,"top_k":10},"single_turn":{"context":"disabled","top_k":10},"context_aware":{"context":"enabled","top_k":10}},"template_rows":counts}
 write_json(directory/"run_manifest.json",manifest); write_jsonl(directory/"execution_events.jsonl",[{"request_id":r["request_id"],"execution_status":r["execution_status"],"transport":"fake"} for r in responses]); return manifest
def real_gate(args: argparse.Namespace) -> None:
 if args.mode!="real": return
 if args.confirm_real_api!=CONFIRM or not clean_worktree(): raise Blocked("BLOCKED REAL MODE GATE")
 verify_frozen()
 if (args.output/"responses.jsonl").exists(): raise Blocked("BLOCKED REAL RESULTS ALREADY EXIST")
 # load_dotenv may only be reached beyond all gates; real transport remains intentionally not implemented.
 raise Blocked("BLOCKED REAL TRANSPORT NOT ENABLED IN THIS DRY-RUN BUILD")
def positive_int(value: str) -> int:
 try: parsed=int(value)
 except ValueError as exc: raise argparse.ArgumentTypeError("must be a positive integer") from exc
 if parsed<=0: raise argparse.ArgumentTypeError("must be a positive integer")
 return parsed
def main(argv=None) -> int:
 p=argparse.ArgumentParser(); p.add_argument("--mode",choices=("dry-run","real"),default="dry-run"); p.add_argument("--confirm-real-api"); p.add_argument("--output",type=Path,default=ROOT/"data/formal_eval/dry_run"); p.add_argument("--max-new-successes",type=positive_int); a=p.parse_args(argv)
 try:
  real_gate(a); manifest=prepare(a.output,max_new_successes=a.max_new_successes); print(f"DRY-RUN: frozen plan contains 190 units; this invocation added {manifest['invocation_new_successes']} new successes; total locked successes is {manifest['total_locked_successes']}; remaining units is {manifest['remaining_units']}; no API or model execution")
 except Blocked as e: print(str(e),file=sys.stderr); return 2
 return 0
if __name__=="__main__": raise SystemExit(main())
