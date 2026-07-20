import csv, hashlib, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import finalize_external_review_adjudication as f
import prepare_external_review_adjudication as p

class FinalizeTests(unittest.TestCase):
 def test_merge_and_deterministic_outputs(self):
  before=[hashlib.sha256(x.read_bytes()).hexdigest() for x in (p.PRIMARY,p.SECONDARY,f.ADJUDICATION)]
  with tempfile.TemporaryDirectory() as d:
   d=Path(d); a=f.finalize(d/'a.csv',d/'g.csv',d/'m.csv',d/'r.md'); b=f.finalize(d/'b.csv',d/'h.csv',d/'n.csv',d/'s.md')
   self.assertEqual(a['final_sha256'],b['final_sha256']); self.assertEqual(a['gold_sha256'],b['gold_sha256'])
   rows=f.read_csv(d/'a.csv'); gold=f.read_csv(d/'g.csv')
   self.assertEqual((len(rows),len(gold)),(120,51)); self.assertEqual(len({x['review_id'] for x in gold}),51); self.assertEqual(len({x['external_session_id'] for x in rows}),120)
   from collections import Counter
   self.assertEqual(Counter(x['decision_source'] for x in rows),Counter(primary_only=96,dual_agreement=8,adjudicated=16)); self.assertEqual(Counter(x['final_included'] for x in rows),Counter(yes=51,no=69)); self.assertEqual(Counter(x['sample_group'] for x in rows),Counter(representative=96,risk=24))
   report=(d/'r.md').read_text(encoding='utf-8')
   self.assertFalse(any(x in report.lower() for x in ('sender','external_store_v1_primary_review_120_final.csv','c:\\users')))
   self.assertFalse(any(x['question'] in report or x['answer'] in report for x in p.read_csv(p.PRIMARY)))
   self.assertEqual(before,[hashlib.sha256(x.read_bytes()).hexdigest() for x in (p.PRIMARY,p.SECONDARY,f.ADJUDICATION)])
 def test_frozen_and_adjudication_scope(self):
  self.assertEqual(f.digest(p.PRIMARY),p.PRIMARY_SHA256); self.assertEqual(f.digest(p.SECONDARY),p.SECONDARY_SHA256); self.assertEqual(f.digest(f.ADJUDICATION),f.ADJUDICATION_SHA256)
  rows=f.merge(); pb={x['review_id']:x for x in p.read_csv(p.PRIMARY)}
  self.assertEqual({x['review_id'] for x in rows if x['final_included']!=('yes' if p.eligible(pb[x['review_id']]) else 'no')},f.EXPECTED_CHANGES)
  self.assertTrue(all(('yes' if f.included(x) else 'no')==x['final_included'] for x in rows))
if __name__=='__main__': unittest.main()
