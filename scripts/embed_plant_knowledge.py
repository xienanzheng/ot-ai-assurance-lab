#!/usr/bin/env python3
"""One-off OpenAI embedding job. Reads git-ignored .env.local; never prints secrets.

Embeds only the synthetic knowledge pack and explicit evaluation questions.
The resulting vectors do not enable arbitrary offline query embedding.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.supervisor.app.plant_knowledge import load_pack, canonical, digest, validate_vectors
from services.supervisor.app.retrieval_ranking import document_text
import httpx

CASES = [
 ('water','Cloudy effluent while buffering capacity falls and coagulation pH decreases.','water.coagulation'),
 ('water','Increasing alum has reduced pH; what relationships matter?','water.coagulation'),
 ('water','Disinfectant concentration is acceptable but water spends too little time in the tank.','water.disinfection'),
 ('water','chlorine_ct_mg_min_l below limit; chlorine contact time too short.','water.disinfection'),
 ('water','The high lift pump must serve demand with falling storage and low header pressure.','water.storage'),
 ('water','clearwell_level_pct falling; elevated_tank_level_pct and leak_flow_m3h require inspection.','water.storage'),
 ('water','Pressure drop across the filter rises while a backwash sequence is active.','water.filtration'),
 ('water','filter_dp_kpa high; filter_outlet_valve_position_pct low.','water.filtration'),
 ('grid','Frequency drops while generation falls below demand.','grid.dispatch'),
 ('grid','Battery charge limits constrain active power balancing with gas and hydro.','grid.dispatch'),
 ('grid','Bus voltage is low; should reactive support and transformer taps be evaluated?','grid.voltage'),
 ('grid','bus_1_voltage_pu low, capacitor_support_mvar and transformer tap adjustment.','grid.voltage'),
 ('grid','Equipment availability limits supplied loads; should rich districts get priority?','grid.service'),
 ('grid','How should equal physical need guide service priority when generation is unavailable?','grid.service'),
 ('nuclear','Condenser pressure rises while cooling response and electrical output change.','nuclear.secondary'),
 ('nuclear','What supervisory authority exists over the turbine and cooling versus reactor protection?','nuclear.secondary'),
 ('nuclear','District heat demand changes; assess delivered heat and supply/return temperatures.','nuclear.heat'),
 ('nuclear','thermal_dispatch_mwth differs from its target during a transient.','nuclear.heat'),
]


def validate_response(body, count):
    if body.get('model') != 'text-embedding-3-large':
        raise ValueError('Unexpected embedding model')
    rows=body.get('data',[])
    if sorted(row.get('index',-1) for row in rows)!=list(range(count)):
        raise ValueError('Missing or duplicate embedding indices')
    vectors=validate_vectors([r['embedding'] for r in sorted(rows,key=lambda r:r['index'])],count)
    if len(vectors[0])!=3072:
        raise ValueError('Unexpected embedding dimensions')
    return vectors


async def run(output):
    if output.exists():
        raise SystemExit('Output exists; choose a new path to avoid accidental repeat billing')
    envfile=Path(__file__).resolve().parents[1]/'.env.local'
    local={}
    if envfile.exists():
        local=dict(line.split('=',1) for line in envfile.read_text().splitlines() if '=' in line and not line.lstrip().startswith('#'))
    key=os.environ.get('OPENAI_API_KEY') or local.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit('Set OPENAI_API_KEY in .env.local')
    pack=load_pack()
    documents=pack['records']
    cases=[{'domain':domain,'query':query,'expected_id':expected} for domain,query,expected in CASES]
    texts=[document_text(d) for d in documents]+[c['query'] for c in cases]
    async with httpx.AsyncClient(timeout=60,trust_env=False,follow_redirects=False) as client:
        response=await client.post('https://api.openai.com/v1/embeddings',
            headers={'Authorization':'Bearer '+key},
            json={'model':'text-embedding-3-large','dimensions':3072,'input':texts,'encoding_format':'float'})
        if response.status_code!=200:
            raise SystemExit(f'OpenAI embedding request failed: HTTP {response.status_code}; no automatic retry')
        body=response.json()
    vectors=validate_response(body,len(texts))
    artifact={'model':body['model'],'dimensions':3072,'pack_sha256':digest(pack),'format_version':2,
              'usage':body.get('usage'),'request_id':response.headers.get('x-request-id'),
              'scope':'synthetic_simulator_only','documents':[
                  {'id':d['id'],'text_sha256':digest(texts[i]),'embedding':vectors[i]} for i,d in enumerate(documents)],
              'queries':[{**c,'embedding':vectors[len(documents)+i]} for i,c in enumerate(cases)]}
    output.parent.mkdir(parents=True,exist_ok=True)
    descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as file:
        json.dump(artifact,file)
    print(canonical({'saved':str(output),'documents':len(documents),'evaluation_queries':len(cases),'usage':artifact['usage'],'dimensions':3072}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    asyncio.run(run(args.output))
