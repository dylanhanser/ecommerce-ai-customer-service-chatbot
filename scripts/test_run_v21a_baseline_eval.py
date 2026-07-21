"""Offline safety and schema tests for the V2.1 development runner."""
from __future__ import annotations
import csv, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import run_v21a_baseline_eval as runner  # noqa: E402

class RunnerModeTests(unittest.TestCase):
 def test_mock_config_never_calls_dotenv_or_client(self):
  def forbidden(*a,**k): raise AssertionError('dotenv/network client called')
  cfg=runner.build_llm_config('mock',forbidden,forbidden)
  self.assertFalse(cfg.has_api_key); self.assertIsNone(cfg.client)
 def test_version_priority_and_cli(self):
  with patch.dict(os.environ,{'RAG_EVAL_SYSTEM_VERSION':'V2.1b'}):
   self.assertEqual('V2.1a',runner.resolve_system_version('V2.1a')); self.assertEqual('V2.1b',runner.resolve_system_version(None))
  self.assertEqual('mock',runner.build_parser().parse_args(['--llm-mode','mock']).llm_mode)
  self.assertEqual('real',runner.build_parser().parse_args(['--llm-mode','real']).llm_mode)
 def test_csv_schema_has_state_fields(self):
  with tempfile.TemporaryDirectory() as d:
   old=runner.CSV_PATH
   try:
    runner.CSV_PATH=Path(d)/'x.csv'; runner.write_csv([{'case_id':'X','inherited_backend_required':True,'conversation_state':'{}'}])
    with runner.CSV_PATH.open(encoding='utf-8-sig',newline='') as f: fields=next(csv.reader(f))
    self.assertIn('inherited_backend_required',fields); self.assertIn('conversation_state',fields)
   finally: runner.CSV_PATH=old
 def test_failure_summary_never_uses_answer_and_is_bounded(self):
  self.assertEqual(96,len(runner.safe_failure_summary('x'*200)))
if __name__=='__main__': unittest.main()
