"""Sequential local model replay. Never submits a command to the simulator."""
import argparse,asyncio,importlib.util,json,time,statistics
from pathlib import Path
import httpx
from v2.contracts import Proposal,digest
from v2.providers import OllamaProvider


def score(case,proposal):
    p=case['context']['package'];s=case['context']['snapshot']
    valid_refs=all(x in s['readings'] for x in proposal.evidence) and all(x in p['checks'] for x in proposal.operator_checks)
    correct=proposal.status==case['expected']
    if proposal.status=='adjust':
        target=proposal.target
        correct=correct and p['minimum']<=target<=p['maximum'] and abs(target-s['target'])<=p['max_delta']+1e-9 and abs(target-p['initial_target'])<=p['max_excursion']+1e-9
        if case['direction']:correct=correct and (target-s['target'])*case['direction']>1e-9
    supported=valid_refs and bool(proposal.operator_checks if proposal.status=='escalate' else proposal.evidence)
    return {'decision_correct':bool(correct),'valid_references':valid_refs,'evidence_present':supported}


async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=['baseline','focused'],required=True)
    parser.add_argument('--split',choices=['development','confirmation'],default='development')
    parser.add_argument('--model',choices=['qwen3:4b','qwen3:8b'],default='qwen3:4b')
    args=parser.parse_args();root=Path('artifacts/model-review-v1')
    manifest=json.loads((root/'cases.json').read_text())
    if digest(manifest['cases'])!=manifest['cases_hash']:raise ValueError('Frozen case hash mismatch')
    cls=OllamaProvider
    if args.profile=='baseline':
        spec=importlib.util.spec_from_file_location('v2.review_baseline',root/'providers-baseline.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);cls=module.OllamaProvider
    model=cls('http://127.0.0.1:11434',args.model)
    suffix='' if args.model=='qwen3:4b' else '-'+args.model.replace(':','-')
    path=root/f'{args.profile}{suffix}-{args.split}.json'
    if path.exists():raise SystemExit('Result exists; preserve it rather than rerunning selected cases')
    report={'profile':args.profile,'model':args.model,'split':args.split,'cases_hash':manifest['cases_hash'],'started_at':time.time(),'rows':[],
            'provider_source_hash':digest(Path('v2/providers.py').read_text() if args.profile=='focused' else (root/'providers-baseline.py').read_text()),
            'context_source_hash':digest(Path('v2/decision_context.py').read_text()),
            'runtime':httpx.get('http://127.0.0.1:11434/api/version').json(),
            'models':[{k:m[k] for k in ('name','digest')} for m in httpx.get('http://127.0.0.1:11434/api/tags').json()['models'] if m['name']==args.model]}
    for case in [r for r in manifest['cases'] if r['split']==args.split]:
        request=model.decision_request(case['context']);started=time.monotonic()
        row={'id':case['id'],'request':request}
        try:
            proposal=await model.decide(case['context']);row.update(proposal=proposal.model_dump(),**score(case,proposal))
        except Exception as error:row.update(error=str(error),decision_correct=False,valid_references=False,evidence_present=False)
        row.update(seconds=time.monotonic()-started,raw_response=getattr(model,'last_response',None))
        report['rows'].append(row);path.write_text(json.dumps(report,indent=2))
        print(json.dumps({k:row.get(k) for k in ['id','decision_correct','proposal','seconds','error']}),flush=True)
    report['summary']={key:sum(bool(r.get(key)) for r in report['rows']) for key in ['decision_correct','valid_references','evidence_present']}
    report['summary'].update(total=len(report['rows']),structured=sum('proposal' in r for r in report['rows']),median_seconds=statistics.median(r['seconds'] for r in report['rows']))
    path.write_text(json.dumps(report,indent=2));print(json.dumps(report['summary']),flush=True)

if __name__=='__main__':asyncio.run(main())
