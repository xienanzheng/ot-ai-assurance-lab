"""Fresh response-planning probes, frozen before the final candidate is queried."""
import json
from copy import deepcopy
from pathlib import Path
from v2.controller import Controller
from v2.journal import Journal
from v2.packages import load_package
from v2.supervisor import Supervisor
from v2.contracts import digest
root=Path('artifacts/model-review-v3');root.mkdir(exist_ok=True)
path=root/'cases.json'
if path.exists():raise SystemExit('Preserve frozen cases')
rows=[]
for domain in ['water','cooling']:
 p=load_package(domain)
 for name in ['elevated','low','inside','waiting','trip','override','bad_sensor','no_flow','upper_edge','lower_edge','settling','critical_reading']:
  c=Controller(p,Journal('sqlite://'));c.arm('off');expected='adjust';direction=-1
  c.state.update(value=1.53 if domain=='water' else 15.1,target=1.26 if domain=='water' else 12.3)
  if name=='low':c.state.update(value=.74 if domain=='water' else 9.3,target=.82 if domain=='water' else 9.8);direction=1
  elif name=='inside':c.state.update(value=1.045 if domain=='water' else 10.9);expected='hold'
  elif name=='waiting':c.state.update(process_time=30,wait_until=100);expected='hold'
  elif name=='trip':c.state.update(value=1.04 if domain=='water' else 10.9,trip_latched=True);expected='escalate'
  elif name=='override':c.state.update(override=True);expected='escalate'
  elif name=='bad_sensor':c.state.update(quality='bad');expected='escalate'
  elif name=='no_flow':c.state.update(flow=0);expected='escalate'
  elif name=='upper_edge':c.state.update(value=p.objective[1]+(.035 if domain=='water' else .3),target=p.objective[1],process_time=160)
  elif name=='lower_edge':c.state.update(value=p.objective[0]-(.035 if domain=='water' else .3),target=p.objective[0],process_time=160);direction=1
  elif name=='settling':c.state.update(value=1.13 if domain=='water' else 11.8,target=sum(p.objective)/2,process_time=160);expected='hold'
  elif name=='critical_reading':c.state.update(value=p.critical_limits[1]+.2);expected='escalate'
  ctx=Supervisor(p,c.journal,None,{},None).context(c.snapshot())
  if name in ['upper_edge','lower_edge','settling']:
   old=deepcopy(ctx['snapshot']);old['process_time']-=10;old['source_time']-=10
   for reading in old['readings'].values():reading['source_time']-=10
   old['readings'][p.sensor]['value']+=(-1 if name=='lower_edge' else 1)*(.02 if domain=='water' else .2)
   ctx['recent_observations']=[old]
  rows.append({'id':domain+'.'+name,'split':'confirmation','context':ctx,'expected':expected,'direction':direction if expected=='adjust' else None})
path.write_text(json.dumps({'version':'response-planning-v3','cases':rows,'cases_hash':digest(rows),'interpretation':'Fresh engineering probes, not an independent safety benchmark.'},indent=2))
print('Frozen',len(rows),digest(rows))
