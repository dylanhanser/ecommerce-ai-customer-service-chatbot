import copy, csv, hashlib, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import prepare_external_review_adjudication as prep
import validate_external_review_adjudication as validator

class AdjudicationTests(unittest.TestCase):
 def write(self, path, rows): prep.write_csv(path, rows)
 def completed(self, rows):
  for row in rows:
   for field in prep.FIELDS:
    if field in row['disputed_fields'].split(','): row[f'{field}_final']=row[f'{field}_primary']
   row['adjudicator_id']='H1'; row['adjudication_date']='2026-07-20'; row['adjudication_notes']='human review'
  return rows
 def test_deterministic_template_scope_and_encoding(self):
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'a.csv'; b=Path(d)/'b.csv'; prep.build(a); prep.build(b)
   self.assertEqual(hashlib.sha256(a.read_bytes()).hexdigest(), hashlib.sha256(b.read_bytes()).hexdigest())
   self.assertTrue(a.read_bytes().startswith(b'\xef\xbb\xbf'))
   with a.open(encoding='utf-8-sig',newline='') as fh: rows=list(csv.DictReader(fh))
   self.assertEqual(len(rows),16); self.assertEqual(len({r['review_id'] for r in rows}),16)
   self.assertEqual(sum(r['eligibility_disagreement']=='yes' for r in rows),7)
   self.assertEqual(sum(not r[f'{x}_final'] for r in rows for x in r['disputed_fields'].split(',')),47)
 def test_blank_template_is_expected_incomplete(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.csv'; prep.build(p); errors, missing=validator.validate(p)
   self.assertEqual(errors,[]); self.assertEqual(missing,47)
 def test_rejects_immutable_and_text_changes_without_leakage(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.csv'; rows=prep.build_rows(); rows[0]['question']='SECRET_QA'; self.write(p,rows)
   errors,_=validator.validate(p); self.assertTrue(any(':question:modified' in x for x in errors)); self.assertFalse(any('SECRET_QA' in x for x in errors))
   rows=prep.build_rows(); rows[0]['pair_valid_primary']='bad'; self.write(p,rows); errors,_=validator.validate(p); self.assertTrue(any(':pair_valid_primary:modified' in x for x in errors))
   rows=prep.build_rows(); rows[0]['role_pairing_correct_final']='no'; self.write(p,rows); errors,_=validator.validate(p); self.assertTrue(any(':role_pairing_correct_final:agreed_value_modified' in x for x in errors))
 def test_rejects_invalid_labels_dates_ids_and_pii(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.csv'; rows=self.completed(prep.build_rows()); rows[0]['pair_valid_final']='bad'; rows[0]['adjudication_date']='2026-99-99'; rows[0]['adjudication_notes']='call 1234567890'; rows[1]['review_id']=rows[0]['review_id']; self.write(p,rows)
   errors,_=validator.validate(p); text='\n'.join(errors)
   self.assertIn('invalid_label',text); self.assertIn('invalid_or_required',text); self.assertIn('possible_pii',text); self.assertIn('duplicate',text); self.assertTrue(all('SECRET' not in x for x in errors))
 def test_missing_and_unknown_ids_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.csv'; rows=prep.build_rows(); rows.pop(); self.write(p,rows); errors,_=validator.validate(p); self.assertTrue(any('row_count' in x for x in errors))
   rows=prep.build_rows(); rows[0]['review_id']='R999'; self.write(p,rows); errors,_=validator.validate(p); self.assertTrue(any('unknown_or_order_invalid' in x for x in errors))
 def test_legal_blank_exclude_reason_and_illegal_blank_are_distinguished(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.csv'
   with prep.OUTPUT.open(encoding='utf-8-sig',newline='') as fh: rows=list(csv.DictReader(fh))
   self.write(p,rows); errors,missing=validator.validate(p); self.assertEqual((errors,missing),([],0))
   row=next(r for r in rows if r['review_id']=='R054'); row['answer_relevance_final']='no'; self.write(p,rows); errors,_=validator.validate(p); self.assertTrue(any('inconsistent_with_eligibility' in x for x in errors))
 def test_no_blinding_fields_in_template_or_report(self):
  forbidden=['candidate_id','risk','role inference','anomaly','decision margin']
  self.assertFalse(any(x in ' '.join(prep.ADJUDICATION_FIELDS).lower() for x in forbidden))
  report=(prep.ROOT/'outputs/reports/external_store_v1_adjudication_setup_report.md').read_text(encoding='utf-8')
  self.assertFalse(any(x in report.lower() for x in forbidden))
if __name__=='__main__': unittest.main()
