"""Frozen local replay; optional one-pass correction, no actuation or weight training.

Never overwrite results or retry a scored outcome until it happens to pass.
"""
import argparse,asyncio,json,time,statistics,math
from pathlib import Path
import httpx
from v2.contracts import Proposal,digest
from v2.providers import OllamaProvider
from scripts.evaluate_decisions import score

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--kind',choices=['decision','audit'],required=True)
    parser.add_argument('--split',choices=['development','confirmation'],default='development')
    parser.add_argument('--variant',choices=['single','bounded','audit-facts','audit-binary'],default='single')
    parser.add_argument('--root',default='artifacts/model-review-v2')
    parser.add_argument('--case-file')
    parser.add_argument('--role',choices=['development','confirmation','regression'])
    args=parser.parse_args();root=Path(args.root);root.mkdir(parents=True,exist_ok=True)
    if args.kind=='decision' and args.variant.startswith('audit-'):raise SystemExit('Audit-only profile')
    suffix='' if args.variant=='single' else '-'+args.variant
    output=root/f'{args.kind}-{args.split}{suffix}.json'
    if output.exists():raise SystemExit('Existing scored results preserved')
    source=Path('artifacts/model-review-v1')
    if args.kind=='decision':
        manifest=json.loads((Path(args.case_file) if args.case_file else source/'cases.json').read_text());assert digest(manifest['cases'])==manifest['cases_hash']
        cases=[c for c in manifest['cases'] if c['split']==args.split];model_name='qwen3:4b'
    else:
        path=source/'audit-cases.json' if args.split=='development' else root/'audit-confirmation-cases.json'
        manifest=json.loads(path.read_text());assert digest(manifest['rows'])==manifest['hash']
        cases=manifest['rows'];model_name='gemma3:4b'
    model=OllamaProvider('http://127.0.0.1:11434',model_name,max_corrections=1 if args.variant=='bounded' else 0)
    source_files={f:Path(f).read_text() for f in ['v2/providers.py','v2/decision_context.py','v2/decision_checks.py','v2/packages.py','v2/gate.py','v2/contracts.py','scripts/evaluate_decisions.py','scripts/evaluate_model_improvements.py']}
    report={'model':model_name,'kind':args.kind,'split':args.split,'evaluation_role':args.role or args.split,'variant':args.variant,'cases_hash':digest(cases),'cases':cases,'rows':[],
        'started_at':time.time(),'source_files':source_files,'source_hashes':{f:digest(content) for f,content in source_files.items()},
        'runtime':httpx.get(model.url+'/api/version').json(),
        'model_identity':[m for m in httpx.get(model.url+'/api/tags').json()['models'] if m['name']==model_name]}
    frozen=root/f'{args.kind}-{args.split}{suffix}-manifest.json'
    if frozen.exists():raise SystemExit('Existing frozen manifest preserved')
    frozen.write_text(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
    for case in cases:
        row={'id':case['id'],'expected':case['expected']};start=time.monotonic()
        try:
            if args.kind=='decision':
                row['request']=model.decision_request(case['context'])
                proposal=await model.decide(case['context'])
                row.update(proposal=proposal.model_dump(),decision_evidence=getattr(model,'last_decision_trace',None),**score(case,proposal))
                if case['expected']=='adjust':
                    p=case['context']['package'];snapshot=case['context']['snapshot'];lo,hi=p['objective']
                    target=proposal.target
                    horizon=p['max_episode_seconds']-p['sustain_seconds']
                    projected=None if target is None else target+(snapshot['readings'][p['sensor']]['value']-target)*math.exp(-horizon/p['response_seconds'])
                    row['nominal_target_recovers']=target is not None and lo<=target<=hi and lo<=projected<=hi
                    row['nominal_projection']={'value_at_review_deadline':projected,'seconds':horizon,'assumption':'First-order bench, constant target, no added disturbance; not observed recovery.'}
            else:
                result,trace=await model.audit_with_evidence(case['context'],Proposal.model_validate(case['proposal']))
                raw_issue=(trace.get('model_verdict') or {}).get('issue')
                model_status=(trace.get('model_verdict') or {}).get('status') or (('passed' if raw_issue=='supported' else 'flagged') if raw_issue else 'unavailable')
                row.update(result=result.model_dump(),trace=trace,correct=result.status==case['expected'],model_status=model_status,model_correct=model_status==case['expected'])
        except Exception as error:row.update(error=str(error),decision_correct=False,valid_references=False,evidence_present=False,correct=False)
        row.update(seconds=time.monotonic()-start,raw_response=getattr(model,'last_response',None))
        report['rows'].append(row);output.write_text(json.dumps(report,indent=2))
        print(json.dumps({k:row.get(k) for k in ['id','decision_correct','proposal','result','model_correct','seconds','error']}),flush=True)
    rows=report['rows']
    report['summary']={'total':len(rows),'median_seconds':statistics.median(r['seconds'] for r in rows)}
    if args.kind=='decision':
        report['summary'].update({k:sum(bool(r.get(k)) for r in rows) for k in ['decision_correct','valid_references','evidence_present']})
        report['summary']['structured']=sum('proposal' in r for r in rows)
        report['summary']['expected_adjustments']=sum(r['expected']=='adjust' for r in rows)
        report['summary']['nominal_recovery_targets']=sum(r.get('nominal_target_recovers',False) for r in rows)
        report['summary']['correct_nominal_recovery_targets']=sum(r.get('decision_correct',False) and r.get('nominal_target_recovers',False) for r in rows)
    else:
        report['summary'].update(correct=sum(r.get('correct',False) for r in rows),model_correct=sum(r.get('model_correct',False) for r in rows),
            false_passes=sum(r['expected']=='flagged' and r.get('result',{}).get('status')=='passed' for r in rows),
            model_false_passes=sum(r['expected']=='flagged' and r.get('model_status')=='passed' for r in rows),
            unavailable=sum(r.get('result',{}).get('status')=='unavailable' or 'error' in r for r in rows))
    report['finished_at']=time.time();output.write_text(json.dumps(report,indent=2));print(json.dumps(report['summary']),flush=True)
if __name__=='__main__':asyncio.run(main())
