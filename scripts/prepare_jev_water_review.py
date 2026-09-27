"""Package rule-matched Jev selections for review, without starting training."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.water_alarm_benchmark import OUT as DATASET,score
from scripts.collect_jev_water_bundles import OUT


def prepare():
    source=OUT/'responses.jsonl'
    rows={r['id']:r for r in (json.loads(l) for l in (DATASET/'train.cases.jsonl').read_text().splitlines())}
    candidates=[];failures=[]
    for line in source.read_text().splitlines():
        record=json.loads(line);row=rows[record['id']]
        proposal=record.get('proposal')
        assessment=score(proposal,row) if proposal else {}
        if not (record['eligible_for_review'] and assessment.get('correct') and assessment.get('assessment_supported')):
            failures.append(record);continue
        target={**proposal,'reason':row['teacher']['reason']}
        candidates.append({'id':record['id'],'messages':row['payload']['messages']+[{'role':'assistant','content':json.dumps(target)}],
          'review_required':True,'sources':{'decision':record['response']['model'],'controls_and_evidence':'code-defined SOP bundle',
          'rationale':'existing rule-labelled scenario teacher, not Jev prose'},
          'response_sha256':hashlib.sha256(json.dumps(record['response'],sort_keys=True).encode()).hexdigest()})
    (OUT/'qwen-review-examples.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in candidates))
    (OUT/'failure-cases.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in failures))
    print(json.dumps({'review_examples':len(candidates),'failures':len(failures),'training_started':False}))


if __name__=='__main__':prepare()
