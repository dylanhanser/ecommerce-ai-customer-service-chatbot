import copy, csv, random, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import prepare_external_review_protocol as protocol
import validate_external_review_annotations as validator
import evaluate_external_review_agreement as agreement

ROOT=Path(__file__).resolve().parents[1]
SAMPLE=ROOT/'data/external_eval/review/external_store_v1_review_sample_120.csv'
MANIFEST=ROOT/'data/external_eval/review/external_store_v1_review_manifest.csv'

class ProtocolTests(unittest.TestCase):
 def write_fixture(self, directory, rows):
  path=Path(directory)/'review.csv'; protocol.write_csv(path,rows,protocol.REVIEW_FIELDS); return path

 def test_selection_quotas_unique_and_order_independent(self):
  rows=protocol.read_csv(MANIFEST); selected,_=protocol.select_secondary(rows)
  shuffled=copy.deepcopy(rows); random.Random(9).shuffle(shuffled); again,_=protocol.select_secondary(shuffled)
  self.assertEqual([x['external_candidate_id'] for x in selected],[x['external_candidate_id'] for x in again])
  self.assertEqual(sum(x['secondary_group']=='representative' for x in selected),19); self.assertEqual(sum(x['secondary_group']=='risk' for x in selected),5)
  self.assertEqual(len({x['review_id'] for x in selected}),24); self.assertEqual(len({x['external_session_id'] for x in selected}),24)

 def test_blinded_empty_and_immutable(self):
  with tempfile.TemporaryDirectory() as tmp:
   result=protocol.build(SAMPLE,MANIFEST,Path(tmp)); primary=protocol.read_csv(result['primary']); secondary=protocol.read_csv(result['secondary'])
   frozen={r['review_id']:r for r in protocol.read_csv(SAMPLE)}
   fields=['reviewer_id','review_date','pair_valid','question_self_contained','answer_relevance','role_pairing_correct','answer_usable_as_reference','residual_pii_found','gold_category','exclude_reason','reviewer_notes']
   self.assertTrue(all(not r[f] for r in primary+secondary for f in fields)); self.assertFalse({'sample_group','external_candidate_id','source_month'} & set(secondary[0]))
   self.assertTrue(all((r['question'],r['answer'])==(frozen[r['review_id']]['question'],frozen[r['review_id']]['answer']) for r in secondary))

 def test_validation_rejects_labels_and_modified_text_without_leakage(self):
  rows=protocol.read_csv(SAMPLE); rows[0]['pair_valid']='bad'; rows[1]['question']='SECRET QA TEXT'
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'x.csv'; protocol.write_csv(path,rows,protocol.REVIEW_FIELDS); errors=validator.validate(path,SAMPLE,120)
  self.assertTrue(any('pair_valid_invalid' in x for x in errors)); self.assertTrue(any('question_modified' in x for x in errors)); self.assertFalse(any('SECRET' in x for x in errors))

 def test_validator_rejects_primary_and_secondary_row_counts(self):
  rows=protocol.read_csv(SAMPLE)
  with tempfile.TemporaryDirectory() as tmp:
   self.assertIn('FILE:row_count_expected_120',validator.validate(self.write_fixture(tmp,rows[:-1]),SAMPLE,120))
   self.assertIn('FILE:row_count_expected_24',validator.validate(self.write_fixture(tmp,rows[:23]),SAMPLE,24))

 def test_validator_rejects_duplicate_unknown_and_missing_frozen_ids(self):
  rows=protocol.read_csv(SAMPLE)
  duplicate=copy.deepcopy(rows); duplicate[1]['review_id']=duplicate[0]['review_id']
  unknown=copy.deepcopy(rows); unknown[0]['review_id']='R999'
  with tempfile.TemporaryDirectory() as tmp:
   errors=validator.validate(self.write_fixture(tmp,duplicate),SAMPLE,120)
   self.assertIn('R001:duplicate_review_id',errors); self.assertIn('R002:missing_expected_review_id',errors)
   errors=validator.validate(self.write_fixture(tmp,unknown),SAMPLE,120)
   self.assertIn('R999:unknown_review_id',errors); self.assertIn('R001:missing_expected_review_id',errors)

 def test_validator_errors_contain_only_ids_and_error_types(self):
  rows=protocol.read_csv(SAMPLE); rows[0]['question']='DO_NOT_LEAK_QUESTION'; rows[1]['answer']='DO_NOT_LEAK_ANSWER'
  with tempfile.TemporaryDirectory() as tmp: errors=validator.validate(self.write_fixture(tmp,rows),SAMPLE,120)
  self.assertTrue(errors); self.assertTrue(all('DO_NOT_LEAK' not in e for e in errors)); self.assertTrue(all(e.startswith('R') or e.startswith('FILE:') for e in errors))

 def test_synthetic_kappa(self):
  a={str(i):{'pair_valid':'yes','answer_relevance':'yes','question_self_contained':'yes','role_pairing_correct':'yes','answer_usable_as_reference':'yes','residual_pii_found':'no','gold_category':'其他','exclude_reason':''} for i in range(4)}
  b=copy.deepcopy(a); b['3']['pair_valid']='no'; b['2']['answer_relevance']='partial'
  result=agreement.agreement(a,b); self.assertEqual(result['n'],4); self.assertEqual(result['fields']['pair_valid']['simple_agreement'],.75); self.assertEqual(result['fields']['answer_relevance']['n_excluding_uncertain'],4)

 def test_nominal_kappa_and_uncertain_are_independent_category(self):
  a={str(i):{'pair_valid':x,'question_self_contained':'yes','answer_relevance':'uncertain','role_pairing_correct':'yes','answer_usable_as_reference':'yes','residual_pii_found':'no','gold_category':'其他','exclude_reason':''} for i,x in enumerate(['yes','yes','no','no'])}
  b=copy.deepcopy(a)
  for i,x in enumerate(['yes','no','no','no']): b[str(i)]['pair_valid']=x
  b['1']['answer_relevance']='yes'
  result=agreement.agreement(a,b)
  self.assertAlmostEqual(result['fields']['pair_valid']['cohens_kappa'],.5)
  self.assertEqual(result['fields']['answer_relevance']['simple_agreement'],.75)

 def test_weighted_kappa_excludes_uncertain_and_uses_fixed_order(self):
  values_a=['uncertain','yes','no','partial']; values_b=['uncertain','partial','no','yes']
  a={str(i):{'pair_valid':'yes','question_self_contained':'yes','answer_relevance':x,'role_pairing_correct':'yes','answer_usable_as_reference':'yes','residual_pii_found':'no','gold_category':'其他','exclude_reason':''} for i,x in enumerate(values_a)}
  b=copy.deepcopy(a)
  for i,x in enumerate(values_b): b[str(i)]['answer_relevance']=x
  metric=agreement.agreement(a,b)['fields']['answer_relevance']
  self.assertEqual(metric['n_excluding_uncertain'],3); self.assertAlmostEqual(metric['weighted_kappa_excluding_uncertain'],.25)

 def test_disagreement_output_is_ids_only_and_has_no_qa_text(self):
  a={"R001":{'pair_valid':'yes','question_self_contained':'yes','answer_relevance':'yes','role_pairing_correct':'yes','answer_usable_as_reference':'yes','residual_pii_found':'no','gold_category':'其他','exclude_reason':''}}
  b=copy.deepcopy(a); b['R001']['pair_valid']='no'
  result=agreement.agreement(a,b); output='\n'.join(result['disagreement_review_ids'])
  self.assertEqual(output,'R001'); self.assertNotIn('question',output); self.assertNotIn('answer',output)

if __name__=='__main__': unittest.main()
