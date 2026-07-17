"""Pre-adjudication agreement metrics; aggregate output never includes QA text."""
from __future__ import annotations
import argparse, csv, json
from collections import Counter
from pathlib import Path

FIELDS=["pair_valid","question_self_contained","answer_relevance","role_pairing_correct","answer_usable_as_reference","residual_pii_found","gold_category","exclude_reason"]
def load(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f: return {r['review_id']:r for r in csv.DictReader(f)}
def kappa(a,b,labels,weights=None):
    n=len(a)
    if not n: return None
    observed=sum((weights(a[i],b[i]) if weights else int(a[i]==b[i])) for i in range(n))/n
    ca,cb=Counter(a),Counter(b)
    expected=sum((ca[x]/n)*(cb[y]/n)*(weights(x,y) if weights else int(x==y)) for x in labels for y in labels)
    return None if expected==1 else (observed-expected)/(1-expected)
def agreement(r1,r2):
    ids=sorted(set(r1)&set(r2)); result={"n":len(ids),"note":"24 条样本量较小；结果仅作为质量控制证据，且在裁决前计算。","fields":{}}
    for field in FIELDS:
        a=[r1[i][field] for i in ids]; b=[r2[i][field] for i in ids]; labels=sorted(set(a)|set(b))
        item={"simple_agreement":sum(x==y for x,y in zip(a,b))/len(ids),"cohens_kappa":kappa(a,b,labels)}
        if field=='answer_relevance':
            pairs=[(x,y) for x,y in zip(a,b) if x!='uncertain' and y!='uncertain']; order=['no','partial','yes']
            weight=lambda x,y:1-abs(order.index(x)-order.index(y))/2
            item['weighted_kappa_excluding_uncertain']=kappa([x for x,y in pairs],[y for x,y in pairs],order,weight); item['n_excluding_uncertain']=len(pairs)
        non_uncertain=[(x,y) for x,y in zip(a,b) if x!='uncertain' and y!='uncertain']
        item['sensitivity_simple_agreement_excluding_uncertain']=None if not non_uncertain else sum(x==y for x,y in non_uncertain)/len(non_uncertain)
        result['fields'][field]=item
    result['disagreement_review_ids']=[i for i in ids if any(r1[i][f]!=r2[i][f] for f in FIELDS)]
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('r1');p.add_argument('r2');p.add_argument('--disagreements',required=True);p.add_argument('--report',required=True);a=p.parse_args()
    result=agreement(load(a.r1),load(a.r2)); Path(a.disagreements).write_text('\n'.join(result.pop('disagreement_review_ids'))+'\n',encoding='utf-8')
    Path(a.report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
