#!/usr/bin/env python3
"""Export a read-only local research catalogue from real experiment artifacts."""
import argparse
import hashlib
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path


def finite(value):
    return isinstance(value,(float,int)) and not isinstance(value,bool) and math.isfinite(value)


def values_only(value):
    return {k:v for k,v in (value or {}).items() if v is not None}


def summarize_control(session):
    baseline=session.get('baseline',{}).get('samples',[])
    agent=session.get('agent',{}).get('samples',[])
    end=min(baseline[-1]['minute'],agent[-1]['minute']) if baseline and agent else None
    def arm_metrics(samples):
        retained=[s for s in samples if end is not None and s['minute']<=end]
        observed=[s for s in retained if s['minute']>0]
        good=[s for s in observed if finite(s.get('values',{}).get('filtered_turbidity_ntu')) and s.get('quality',{}).get('filtered_turbidity_ntu')=='good']
        last=retained[-1].get('values',{}).get('filtered_turbidity_ntu') if retained and retained[-1].get('quality',{}).get('filtered_turbidity_ntu')=='good' else None
        minute_cadence=bool(retained) and retained[0]['minute']==0 and all(y['minute']-x['minute']==1 for x,y in zip(retained,retained[1:]))
        return {'excursion':sum(s['values']['filtered_turbidity_ntu']>1.0 for s in good) if observed else None,
                'unknown':len(observed)-len(good) if observed else None,'observed':len(good) if observed else None,
                'minute_cadence':minute_cadence,'final':last if finite(last) else None}
    b,a=arm_metrics(baseline),arm_metrics(agent)
    exchanges=[]
    for t in session.get('agent',{}).get('exchanges',[]):
        r=t.get('record') or {}; p=r.get('proposal') or {};g=r.get('gate') or {};response=r.get('response') or {}
        request=r.get('request') or {};timeline={}
        try:timeline=json.loads(request['messages'][1]['content']).get('research_context',{}).get('timeline',{})
        except (KeyError,IndexError,ValueError,TypeError):pass
        exchanges.append({'minute':t['minute'],'record_id':r.get('id'),'status':t.get('job',{}).get('status',r.get('status','unknown')),
            'latency_seconds':r.get('latency_seconds'),'thinking':response.get('message',{}).get('thinking',''),
            'explanation':p.get('explanation') or r.get('error') or t.get('job',{}).get('error','No valid proposal'),
            'proposed':values_only(p.get('changes')),'applied':values_only(g.get('applied_values')) if r.get('applied') else {},
            'was_applied':bool(r.get('applied')),'gate':g,'episode_status':p.get('episode_status'),
            'done_reason':response.get('done_reason'),'context':{'sample_count':len(timeline.get('recent_samples',[])),
            'prior_count':len(timeline.get('previous_exchanges',[])),'prompt_tokens':response.get('prompt_eval_count'),
            'configured_tokens':request.get('options',{}).get('num_ctx')},'record_url':None})
    latencies=[t['latency_seconds'] for t in exchanges if finite(t['latency_seconds'])]
    return {'id':session['id'],'title':'Gradual water-quality deterioration','status':session.get('status','unknown'),
        'model':session.get('protocol',{}).get('model','Qwen3 8B / Ollama'), 'protocol':session.get('protocol',{}),
        'samples':{'baseline':baseline,'agent':agent},'exchanges':exchanges,
        'metrics':{'elapsed':agent[-1]['minute'] if agent else None,'matched_end':end,'total':len(exchanges),
            'failures':sum(t['status']=='failed' for t in exchanges),'applied':sum(t['was_applied'] for t in exchanges),
            'sample_count_method':'Post-minute-zero good-quality observations in the matched horizon; counts, not elapsed exposure. Legacy minute fields are populated only for one-minute cadence.',
            'baseline_excursion_samples':b['excursion'],'agent_excursion_samples':a['excursion'],
            'baseline_observed_samples':b['observed'],'agent_observed_samples':a['observed'],
            'baseline_unknown_samples':b['unknown'],'agent_unknown_samples':a['unknown'],
            'baseline_excursion_minutes':b['excursion'] if b['minute_cadence'] else None,'agent_excursion_minutes':a['excursion'] if a['minute_cadence'] else None,
            'baseline_unknown_minutes':b['unknown'] if b['minute_cadence'] else None,'agent_unknown_minutes':a['unknown'] if a['minute_cadence'] else None,
            'baseline_final':b['final'],'agent_final':a['final'],
            'latency_min':min(latencies) if latencies else None,'latency_max':max(latencies) if latencies else None},
        'interpretation':'One constructed simulation, not a calibrated plant. Gate acceptance is not proof of effective control. No accident probabilities or alignment scores are inferred. The clock was paused during inference.'}


def write_json(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False))


def export_catalogue(root,output):
    catalogue={'generated_at':datetime.now(timezone.utc).isoformat(),'control_studies':[],'mechanistic_studies':[]}
    for path in sorted((root/'artifacts/recovery-timelines').glob('*/session.json'),reverse=True):
        raw=path.read_bytes();session=json.loads(raw);summary=summarize_control(session)
        identifier=path.parent.name; summary['source_sha256']=hashlib.sha256(raw).hexdigest()
        # Local artifact IDs, never model-produced filenames.
        folder=output/'control'/identifier
        for index,t in enumerate(session.get('agent',{}).get('exchanges',[])):
            if t.get('record'):
                filename=f'exchange-{index+1}.json';write_json(folder/filename,t['record'])
                summary['exchanges'][index]['record_url']=f'/research/control/{identifier}/{filename}'
        write_json(folder/'summary.json',summary)
        catalogue['control_studies'].append({'id':identifier,'title':f"{identifier[:8]} · {summary['status'].replace('_',' ')}",'url':f'/research/control/{identifier}/summary.json'})
    for path in sorted((root/'artifacts/mechanistic').glob('*/results.json'),reverse=True):
        data=json.loads(path.read_text());identifier=path.parent.name; folder=output/'mechanistic'/identifier
        data['source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        for filename in ['activations.npz','activation-effects.png','activation-effects.svg']:
            if (path.parent/filename).exists():
                folder.mkdir(parents=True,exist_ok=True);shutil.copy2(path.parent/filename,folder/filename)
        data['activations_url']=f'/research/mechanistic/{identifier}/activations.npz' if (folder/'activations.npz').exists() else None
        write_json(folder/'results.json',data)
        catalogue['mechanistic_studies'].append({'id':identifier,'title':f"{data.get('model',{}).get('id','Local model')} · {data.get('status')}",'url':f'/research/mechanistic/{identifier}/results.json'})
    write_json(output/'index.json',catalogue)
    return catalogue


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    args=parser.parse_args(); result=export_catalogue(args.root,args.root/'services/web/public/research')
    print(json.dumps({k:len(v) for k,v in result.items() if isinstance(v,list)}))
