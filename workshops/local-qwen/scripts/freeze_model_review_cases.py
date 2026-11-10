import json,time
from pathlib import Path
from v2.packages import load_package
from v2.controller import Controller
from v2.journal import Journal
from v2.supervisor import Supervisor
from v2.contracts import digest
rows=[]
for domain in ['water','cooling']:
 p=load_package(domain)
 for name in ['high','low','inside','waiting','critical','trip','bad_sensor','no_flow','stale','override','critical_reading','high_variant','inside_variant','limit']:
  c=Controller(p,Journal('sqlite://'));c.arm('off')
  expected='adjust';direction=-1
  if name=='low':
   c.state.update(value=.7 if domain=='water' else 9, target=.8 if domain=='water' else 10);direction=1
  elif name=='inside':c.state.update(value=1.02 if domain=='water' else 11,target=1.02 if domain=='water' else 11);expected='hold'
  elif name=='waiting':c.state.update(target=1 if domain=='water' else 11,wait_until=90);expected='hold'
  elif name=='critical':c.state.update(critical=True,trip_latched=True);expected='escalate'
  elif name=='trip':c.state.update(value=1 if domain=='water' else 11,trip_latched=True);expected='escalate'
  elif name=='bad_sensor':c.state.update(quality='bad');expected='escalate'
  elif name=='no_flow':c.state.update(flow=0);expected='escalate'
  elif name=='stale':c.state.update(stale=True);expected='escalate'
  elif name=='override':c.state.update(override=True);expected='escalate'
  elif name=='critical_reading':c.state.update(value=p.critical_limits[1]);expected='escalate'
  elif name=='high_variant':c.state.update(value=1.65 if domain=='water' else 16,target=1.3 if domain=='water' else 13)
  elif name=='inside_variant':c.state.update(value=1.06 if domain=='water' else 10.8,target=1.06 if domain=='water' else 10.8);expected='hold'
  elif name=='limit':c.state.update(target=p.initial_target-p.max_excursion);expected='escalate'
  s=Supervisor(p,c.journal,None,{},None);snap=c.snapshot();context=s.context(snap)
  rows.append({'id':domain+'.'+name,'split':'development' if name in ['high','low','inside','waiting','critical','trip','bad_sensor','no_flow'] else 'confirmation','context':context,'expected':expected,'direction':direction if expected=='adjust' else None})
manifest={'version':'model-review-v1','cases':rows,'cases_hash':digest(rows),'created_at':time.time(),'interpretation':'Small local regression set, not a safety qualification or independent research benchmark.'}
p=Path('artifacts/model-review-v1/cases.json')
if p.exists():raise SystemExit('Frozen cases already exist')
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(manifest,indent=2));print(manifest['cases_hash'],len(rows))
