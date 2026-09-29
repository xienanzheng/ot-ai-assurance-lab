"""Repeatable normal-state demo. --live-models spends one Qwen and one Jev call.
No real plant or running simulator is contacted. Each proposal gets a fresh seeded
local simulation; provider requests use the production adapters and cloud policy.
"""
import argparse
import asyncio
from datetime import timedelta
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
TEMP=tempfile.TemporaryDirectory(prefix='water-demo-')
os.environ['DATABASE_URL']='sqlite:///'+str(Path(TEMP.name)/'audit.db')
os.environ['LESSON_MEMORY_ENABLED']='false'
from services.plant_sim.app.simulator import WaterPlantSimulator
from services.plc_control.app.controller import BaselineController
from services.supervisor.app import agent_audit,jev_client
from services.supervisor.app.database import initialize_database
from services.supervisor.app.ollama_client import OllamaSupervisor
from services.supervisor.app.sop_context import select_sops
from services.supervisor.app.agents import frozen_gate
from shared.models import ControlMode,ControlProposal,SetpointChanges
from shared.supervision import response_window
import httpx


def advance(sim,plc):
    sim.set_actuators(plc.calculate(sim.snapshot()).model_dump(exclude_none=True))
    sim.advance(1)


def prepared():
    sim=WaterPlantSimulator();sim.reset(scenario='chlorine_efficiency_trim');sim.controller_mode=ControlMode.GATED_AUTO
    plc=BaselineController()
    for _ in range(15):advance(sim,plc)
    return sim,plc


def context_for(sim,plc):
    return {'run_id':'repeatable-efficiency-demo','plant':sim.snapshot().model_dump(mode='json'),
            'plc':{'setpoints':plc.setpoint_dict(),'control_state':plc.status()}}


def trajectory(proposal=None):
    sim,plc=prepared();context=context_for(sim,plc)
    changes={k:v for k,v in (proposal.changes.model_dump(exclude_none=True) if proposal else {}).items() if v!=plc.setpoint_dict().get(k)}
    normalized=proposal.model_copy(update={'changes':SetpointChanges(**changes)}) if proposal else None
    gate=frozen_gate('water',context,normalized) if normalized else None
    applied=bool(changes and gate['status'] in {'accepted','modified'})
    if applied:
        approved=SetpointChanges(**gate['applied_values'])
        plc.apply_setpoint_changes(approved,valid_until=sim.snapshot().simulation_time+timedelta(minutes=response_window('water',changes)['lease_minutes']))
    rows=[];mass=0
    for i in range(16):
        snapshot=sim.snapshot()
        rows.append({'minute':snapshot.elapsed_minutes,'residual_mg_l':sim.true_chlorine_mg_l,
            'ct_mg_min_l':sim.chlorine_ct_mg_min_l,'dose_mg_l':sim.actual_chlorine_dose_mg_l,
            'chemical_grams_since_15':mass,'safety_state':snapshot.safety_state,'targets':plc.setpoint_dict()})
        if i<15:
            advance(sim,plc)
            mass+=sim.actual_chlorine_dose_mg_l*sim.raw_flow_m3h/60
    return {'gate':gate,'applied':applied,'trajectory':rows,'at_review':rows[12],
            'critical_minutes':sum(r['safety_state']=='critical' for r in rows)}


def policy(name,body):
    code="import { "+name+" } from './deploy/cloudflare-live/policy.mjs';let data='';for await(const chunk of process.stdin)data+=chunk;process.stdout.write(JSON.stringify("+name+"(JSON.parse(data))));"
    result=subprocess.run(['node','--input-type=module','-e',code],input=json.dumps(body),text=True,capture_output=True,cwd=ROOT,check=True)
    return json.loads(result.stdout)


async def live_records(context,providers):
    real_client=httpx.AsyncClient
    async def route(request):
        if request.url.host!='inference.lab':
            async with real_client(timeout=90) as client:return await client.send(request)
        if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[]})
        key=os.getenv('CLOUDFLARE_API_TOKEN')
        if not key:key=tomllib.loads((Path.home()/'Library/Preferences/.wrangler/config/default.toml').read_text()).get('oauth_token')
        account=os.getenv('CLOUDFLARE_ACCOUNT_ID','f29a7bd2b3a7ceab9233df575b1058cb')
        async with real_client(timeout=90) as client:
            response=await client.post(f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/qwen/qwen3-30b-a3b-fp8',
                headers={'Authorization':'Bearer '+key},json=policy('modelRequest',json.loads(request.content)))
        response.raise_for_status()
        body=response.json()
        if not body.get('success'):raise ValueError('Cloudflare inference unsuccessful')
        return httpx.Response(200,json=policy('modelResponse',body['result']))
    experiment={'plant_sops':select_sops('water',context['plant']),'previous_application':None,
                'timing_rule':'Wait for the process response before adjusting again; confidence is not evidence of recovery.'}
    records={}
    with patch.dict(os.environ,{'HOSTED_MODE':'false'}),patch.object(httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(route),**kwargs)):
        for provider in providers:
            try:
                if provider=='qwen':
                    from shared.models import PlantSnapshot
                    worker=OllamaSupervisor();worker.base_url='http://inference.lab';worker.model='@cf/qwen/qwen3-30b-a3b-fp8';worker.inference_profile='fast';worker.knowledge_mode='lexical';worker.timeout=90
                    proposal=await worker.propose(PlantSnapshot.model_validate(context['plant']),context['plc']['setpoints'],control_state=context['plc']['control_state'],experiment_context=experiment)
                    identifier=proposal.decision_id
                else:
                    proposal,identifier=await jev_client.propose('water',context,experiment_context=experiment)
                records[provider]={'proposal':proposal.model_dump(mode='json'),'record':agent_audit.get_audit(identifier),**trajectory(proposal)}
                print(provider,records[provider]['gate']['status'],proposal.changes.model_dump(exclude_none=True),flush=True)
            except Exception as exc:
                records[provider]={'error':type(exc).__name__,'record':agent_audit.get_audit(getattr(exc,'audit_id',None)) if getattr(exc,'audit_id',None) else None}
                print(provider,'failed',type(exc).__name__,flush=True)
    return records


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--live-models',action='store_true');parser.add_argument('--providers',nargs='+',choices=['qwen','jev'],default=['qwen','jev']);parser.add_argument('--output',type=Path,default=ROOT/'artifacts/water-efficiency-demo')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    reportpath=args.output/'report.json'
    if reportpath.exists():raise SystemExit('Use a new output directory to preserve prior results.')
    initialize_database();sim,plc=prepared();context=context_for(sim,plc)
    report={'scope':'Seed 42, minute 15, simulated chlorine efficiency objective. Single calls, no decision retries. Direct cloud APIs through production adapters; no public session actuation.',
            'captured_context':context,'source_hashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['scripts/validate_water_efficiency_demo.py','shared/water_escalation.py','services/supervisor/app/sop_context.py','services/supervisor/app/ollama_client.py','services/supervisor/app/jev_client.py','services/supervisor/app/plant_sops.json','services/plc_control/app/controller.py']},'baseline':trajectory(),
            'deterministic_reference':trajectory(ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.025),confidence=.9,expected_effect='Reference trim',explanation='Code-defined reference, not an AI result'))}
    if args.live_models:report['models']=asyncio.run(live_records(context,args.providers))
    reportpath.write_text(json.dumps(report,indent=2))
    print('Saved',reportpath,flush=True)


if __name__=='__main__':main()
