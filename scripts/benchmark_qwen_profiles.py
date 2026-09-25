#!/usr/bin/env python3
"""Replay recorded simulated states through local Qwen; evaluate only, never actuate."""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

async def main(args):
    args.output.mkdir(parents=True,exist_ok=True)
    os.environ['DATABASE_URL']='sqlite:///'+str((args.output/'audits.sqlite3').resolve())
    os.environ['OLLAMA_BASE_URL']='http://127.0.0.1:11434'
    from services.supervisor.app.ollama_client import OllamaSupervisor, InfrastructureProposal, OllamaUnavailable
    from services.supervisor.app.database import Base, engine
    from services.supervisor.app.agent_audit import get_audit, update_audit
    from services.supervisor.app.agents import frozen_gate
    from shared.models import ControlProposal
    Base.metadata.create_all(engine)
    frozen=json.loads(args.frozen.read_text())['results']
    timeline=json.loads(args.timeline.read_text())['results']
    cases=[next(r['record'] for r in frozen if r['domain']=='water' and r['mode']=='off'),
           next(r['record'] for r in frozen if r['domain']=='grid' and r['mode']=='off'),
           next(b for b in timeline if b['mode']=='off')['decisions'][0]['record']]
    output=[]
    worker=OllamaSupervisor();worker.model='qwen3:4b'
    for index,source in enumerate(cases):
        nonce=uuid4().hex[:12]
        for profile in (['standard','fast'] if index%2==0 else ['fast','standard']):
            worker.inference_profile=profile
            payload=deepcopy(source['request']);payload['model']=worker.model
            if args.fresh:
                state=json.loads(payload['messages'][-1]['content'])
                payload['messages'][-1]['content']=json.dumps({'benchmark_nonce':nonce,**state},separators=(',',':'))
            start=perf_counter()
            try:
                proposal,identifier=await worker._chat(source['domain'],payload,ControlProposal if source['domain']=='water' else InfrastructureProposal)
                gate=frozen_gate(source['domain'],source['before'],proposal)
                update_audit(identifier,before=source['before'],gate=gate,applied=False,evaluate_only=True,status='complete')
            except OllamaUnavailable as exc:
                identifier=exc.audit_id
            record=get_audit(identifier);response=record.get('response',{})
            row={'case':index,'domain':source['domain'],'profile':profile,'seconds':round(perf_counter()-start,3),
                 'status':record['status'],'gate':record.get('gate',{}).get('status'),
                 'prompt_tokens':response.get('prompt_eval_count'),'output_tokens':response.get('eval_count'),
                 'prompt_seconds':response.get('prompt_eval_duration',0)/1e9,'generation_seconds':response.get('eval_duration',0)/1e9,
                 'record':record}
            output.append(row)
            (args.output/'report.json').write_text(json.dumps({'model':worker.model,'results':output,
              'limitation':'Small paired frozen replay, not proof of accuracy, recovery or real-plant safety.'},indent=2))
            print(json.dumps({k:v for k,v in row.items() if k!='record'}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frozen',type=Path,default=Path('artifacts/retrieval-2026-09-23/frozen.json'))
    p.add_argument('--timeline',type=Path,default=Path('artifacts/retrieval-2026-09-23/timeline.json'))
    p.add_argument('--fresh',action='store_true',help='Prepend a shared pair nonce to avoid exact-input cache bias')
    p.add_argument('--output',type=Path,required=True)
    asyncio.run(main(p.parse_args()))
