#!/usr/bin/env python3
"""Deterministic, offline-safe runner for the frozen formal evaluation.

Dry-run deliberately produces marker strings, never customer-service answers.
The real transport is intentionally a guarded stub until separately authorised.
"""
from __future__ import annotations

import argparse, csv, hashlib, json, os, subprocess, sys, tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from formal_evaluation_runtime import EVALUATION_GENERATION_CONFIG  # explicit existing config

BASE_SEED = 20260721
CONFIRM = "FORMAL_EVAL_20260721"
FROZEN = {
 "data/external_eval/review/final/external_store_v1_gold_51.csv":"773535bf13c1d2a80ebff5410c2f16c96b6f297b2b3f17cd99628165b26fc444",
 "evaluation/formal_qa_only_baseline_spec.json":"ea776d7cd43e76cad9f42874a0d9da0fb9b0abd4007d752ea7cc1794bd5ed399",
 "evaluation/formal_rq1_scoring_schema.json":"a2854a92a5dff3c59215cfef5cc49416a4d64e5c89b0a915d95a43791f4bba9b",
 "evaluation/formal_rq2_boundary_cases.json":"4a5680a7cd21ba434c958b3c3cdd9407a84b77d7f3741b10476fa86fa9851417",
 "evaluation/formal_rq3_multiturn_cases.json":"c534867d93edbed724efd8064c85555b3fbeab89f4bdc58dbebb45a904018b95",
}
GENERATION = {"provider":"DeepSeek","base_url":"https://api.deepseek.com","model":"deepseek-chat","temperature":0.0,"top_p":1.0,"max_tokens":512,"stream":False,"thinking":"not_applicable"}

class Blocked(RuntimeError): pass
def sha_bytes(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def canonical(x: Any) -> str: return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(",",":"))
def sha(x: Any) -> str: return sha_bytes(canonical(x).encode())
def file_sha(p: Path) -> str: return sha_bytes(p.read_bytes())
def derive(namespace: str, *parts: str) -> str: return sha_bytes((namespace+"|"+str(BASE_SEED)+"|"+"|".join(parts)).encode())
def read_json(name: str) -> Any: return json.loads((ROOT/name).read_text(encoding="utf-8"))
def frozen_hashes() -> dict[str,str]: return {p:file_sha(ROOT/p) for p in FROZEN}
def verify_frozen() -> dict[str,str]:
 h=frozen_hashes()
 bad=[p for p in FROZEN if h[p] != FROZEN[p]]
 if bad: raise Blocked("BLOCKED FROZEN INPUT SHA MISMATCH: " + ", ".join(bad))
 return h
def clean_worktree() -> bool:
 return subprocess.run(["git","status","--short"], cwd=ROOT, text=True, capture_output=True, check=True).stdout == ""
def generation_sha() -> str:
 # Enforce that the runner uses the existing explicit evaluation config.
 cfg=asdict(EVALUATION_GENERATION_CONFIG)
 if cfg != {k:GENERATION[k] for k in ("temperature","top_p","max_tokens","stream")}:
  raise Blocked("BLOCKED EVALUATION GENERATION CONFIG MISMATCH")
 return sha(GENERATION)

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
 c=Counter(x["rq"] for x in plan)
 if len(plan)!=190 or c!={"RQ1":102,"RQ2":40,"RQ3":48}: raise Blocked("BLOCKED REQUEST PLAN COUNT")
 if len({x["request_id"] for x in plan}) != len(plan): raise Blocked("BLOCKED DUPLICATE REQUEST ID")
 if len({(x["rq"],x["case_id"],x["turn_index"],x["system_config_id"]) for x in plan}) != 190: raise Blocked("BLOCKED INCOMPLETE CASE IDS")

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
 return {"response_text":marker,"action_type":"dry_run_unclassified","guard_decision":"not_executed","retrieval_performed":False,"retrieved_ids":[],"retrieval_scores":[],"latency_ms":0}
def resolved_execution_unit(unit: dict[str,Any], known: dict[str,dict[str,Any]]) -> dict[str,Any]:
 """Resolve only the permitted, already-locked prior answer at execution time.

 The plan stores a stable reference marker so its hash never depends on model text.
 """
 if unit["rq"]!="RQ3" or unit["system_config_id"]!="context_aware" or unit["turn_index"]!=2: return unit
 prior=next((r for r in known.values() if r["rq"]=="RQ3" and r["case_id"]==unit["case_id"] and r["system_config_id"]==unit["system_config_id"] and r["turn_index"]==1 and r["execution_status"]=="success"),None)
 if prior is None: raise Blocked("BLOCKED MISSING LOCKED RQ3 TURN 1")
 copy=json.loads(json.dumps(unit,ensure_ascii=False)); copy["payload"]["history"][0]["assistant_answer"]=prior["response_text"]
 return copy
def run_plan(plan: list[dict[str,Any]], directory: Path, executor: Callable[[dict[str,Any],int],dict[str,Any]]=fake_executor) -> list[dict[str,Any]]:
 directory.mkdir(parents=True,exist_ok=True); rp=directory/"responses.jsonl"; existing={x["request_id"]:x for x in load_jsonl(rp)}; out=[]
 expected={x["request_id"]:x for x in plan}
 for rid,row in existing.items():
  if rid not in expected or row.get("system_config_id") != expected[rid]["system_config_id"]:
   raise Blocked("BLOCKED LEGACY OR MIXED FORMAL PLAN RESULTS")
 for unit in plan:
  old=existing.get(unit["request_id"])
  if old:
   if old["payload_sha256"]!=unit["payload_sha256"]: raise Blocked("BLOCKED PAYLOAD MISMATCH")
   if old["execution_status"]=="success": out.append(old); continue
  last=None
  for attempt in range(1,4):
   try:
    result=executor(resolved_execution_unit(unit,existing),attempt); text=result["response_text"]
    row={k:unit[k] for k in ("request_id","rq","case_id","turn_index","system_config_id","input_sha256","payload_sha256")}
    row.update(result); row.update({"response_sha256":sha_bytes(text.encode()),"attempt_count":attempt,"timestamp_utc":"DRY_RUN_DETERMINISTIC","execution_status":"success","transport":"fake"})
    atomic_append_jsonl(rp,row); existing[unit["request_id"]]=row; out.append(row); break
   except Exception as exc:
    last=exc
    if not retryable(exc) or attempt==3: raise Blocked("BLOCKED TRANSPORT FAILURE") from exc
  else: raise Blocked("BLOCKED TRANSPORT FAILURE") from last
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

def prepare(directory: Path) -> dict[str,Any]:
 hashes=verify_frozen(); plan=build_plan(); write_jsonl(directory/"request_plan.jsonl",plan); responses=run_plan(plan,directory); counts=templates(plan,responses,directory)
 manifest={"protocol_version":"1.1","base_seed":BASE_SEED,"frozen_input_sha256":hashes,"generation":GENERATION,"transport":"fake","responses_are_not_model_outputs":True,"request_count":190,"system_configurations":{"qa_only_reconstructed_baseline":{"corpus":"qa_only","qa_count":15333,"top_k":5},"v2":{"corpus":"mixed","qa_count":15333,"snippet_count":355,"top_k":10},"single_turn":{"context":"disabled","top_k":10},"context_aware":{"context":"enabled","top_k":10}},"template_rows":counts}
 write_json(directory/"run_manifest.json",manifest); write_jsonl(directory/"execution_events.jsonl",[{"request_id":r["request_id"],"execution_status":r["execution_status"],"transport":"fake"} for r in responses]); return manifest
def real_gate(args: argparse.Namespace) -> None:
 if args.mode!="real": return
 if args.confirm_real_api!=CONFIRM or not clean_worktree(): raise Blocked("BLOCKED REAL MODE GATE")
 verify_frozen()
 if (args.output/"responses.jsonl").exists(): raise Blocked("BLOCKED REAL RESULTS ALREADY EXIST")
 # load_dotenv may only be reached beyond all gates; real transport remains intentionally not implemented.
 raise Blocked("BLOCKED REAL TRANSPORT NOT ENABLED IN THIS DRY-RUN BUILD")
def main(argv=None) -> int:
 p=argparse.ArgumentParser(); p.add_argument("--mode",choices=("dry-run","real"),default="dry-run"); p.add_argument("--confirm-real-api"); p.add_argument("--output",type=Path,default=ROOT/"data/formal_eval/dry_run"); a=p.parse_args(argv)
 try:
  real_gate(a); prepare(a.output); print("DRY-RUN COMPLETE: 190 response units; no API or model execution")
 except Blocked as e: print(str(e),file=sys.stderr); return 2
 return 0
if __name__=="__main__": raise SystemExit(main())
