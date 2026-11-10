"""Exercise the running local V2 through its public API; preserves every outcome.

No model/prompt edits. Real-time waiting. Fixture setup is explicitly attributed.
Resets the V2 exercise; refuses to interrupt an existing run.
"""
import argparse,json,time,subprocess
from pathlib import Path
import httpx

SCENARIOS=['high_start','drift','critical','cleared_alarm_latched_trip','no_flow','bad_sensor','stale_sensor','override']
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
parser.add_argument('--start-at',choices=SCENARIOS,default='high_start',help='Explicit continuation in a NEW output file; original evidence is retained')
args=parser.parse_args()
path=Path(args.output)
if path.exists():raise SystemExit('Preserve existing results; choose a new output file')
path.parent.mkdir(parents=True,exist_ok=True)
c=httpx.Client(base_url='http://127.0.0.1:18790',timeout=15)
def get(p):
 r=c.get('/api/'+p);r.raise_for_status();return r.json()
def post(p,b):
 r=c.post('/api/'+p,json=b);r.raise_for_status();return r.json()
def capture(predicate=lambda s:True,timeout=35):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  s=get('status')
  if s['snapshot'] and not s['capture_error'] and predicate(s):return s
  time.sleep(.5)
 raise TimeoutError('Expected telemetry did not arrive')
def ready():
 deadline=time.monotonic()+110
 while time.monotonic()<deadline:
  if not get('status')['busy']:return
  time.sleep(.5)
 raise TimeoutError('Analysis job did not release ownership')
def reset(policy):
 ready();post('scenario',{'name':'reset'});capture();post('arm',{'policy':policy});return capture(lambda s:s['snapshot']['armed'])
def analyse(provider='qwen',apply=False):
 old={r['id'] for r in get('records')};post('analysis',{'provider':provider,'apply':apply})
 deadline=time.monotonic()+110
 while time.monotonic()<deadline:
  rows=[r for r in get('records') if r['id'] not in old]
  if rows and rows[0]['status'] not in ('running','submitting'):
   ready();return next(r for r in get('records') if r['id']==rows[0]['id'])
  time.sleep(.5)
 raise TimeoutError('No completed decision record')
def judge(record,expected,direction=None):
 p=record.get('proposal') or {};s=record['input']['snapshot'];pack=record['input']['package']
 correct=p.get('status')==expected
 if expected=='adjust':
  t=p.get('target');correct=correct and isinstance(t,(int,float)) and (t-s['target'])*direction>1e-9
  if isinstance(t,(int,float)):correct=correct and pack['minimum']<=t<=pack['maximum'] and abs(t-s['target'])<=pack['max_delta']+1e-9 and abs(t-pack['initial_target'])<=pack['max_excursion']+1e-9
 ids_ok=all(v in s['readings'] for v in p.get('evidence',[])) and all(v in pack['checks'] for v in p.get('operator_checks',[]))
 return {'disposition_and_target_correct':bool(correct),'references_valid':ids_ok,'applied':bool((record.get('command') or {}).get('actually_applied'))}
initial=capture()
if initial['busy'] or initial['feedback']['active'] or initial['snapshot']['armed']:raise SystemExit('Existing active supervision; leave it untouched')
report={'started_at':time.time(),'start_at':args.start_at,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'package':initial['package'],'provider':initial['providers']['qwen'],'auditor':initial['auditor'],'initial_policy':initial['policy'],'scenarios':[],'status':'running','samples':[]}
def save():path.write_text(json.dumps(report,indent=2))
def record_case(name,expected,record,**extra):
 row={'scenario':name,'expected':expected,'record':record,**judge(record,expected,-1 if expected=='adjust' else None),**extra};report['scenarios'].append(row);save()
 print(json.dumps({'scenario':name,'status':record['status'],'decision_correct':row['disposition_and_target_correct'],'proposal':record.get('proposal'),'audit':record.get('audit'),'applied':row['applied']}),flush=True)
try:
 for name in SCENARIOS[SCENARIOS.index(args.start_at):]:
  policy='off' if name=='high_start' else 'required';reset(policy)
  if name=='drift':
   post('scenario',{'name':'drift'});capture();post('arm',{'policy':policy});capture(lambda s:s['snapshot']['armed'])
  elif name=='cleared_alarm_latched_trip':
   post('scenario',{'name':'critical'});capture(lambda s:s['snapshot']['trip_latched'])
   post('scenario',{'name':'normal'});capture(lambda s:not s['snapshot']['critical'] and s['snapshot']['trip_latched'])
  elif name!='high_start':
   post('scenario',{'name':name});capture()
  before=capture()['snapshot'];expected='adjust' if name in ('high_start','drift') else 'escalate'
  r=analyse(apply=expected=='adjust');after=capture()['snapshot']
  extra={'before':before,'after':after,'audit_policy':policy}
  if expected=='escalate':extra['protection_preserved']=not after['armed'] and after['target']==before['target'] and not (r.get('command') or {}).get('actually_applied')
  record_case(name,expected,r,**extra)
  if (r.get('command') or {}).get('actually_applied'):
   start=time.monotonic();trajectory=[]
   while time.monotonic()-start<210:
    state=capture();latest=next(x for x in get('records') if x['id']==r['id']);trajectory.append(state['snapshot'])
    if (latest.get('outcome') or {}).get('status') in ('completed','interrupted','not_recovered'):break
    time.sleep(3)
   report['scenarios'][-1].update(trajectory=trajectory,final_record=latest);save()
 # Establish a valid accepted target with an explicitly attributed fixture.
 reset('off');fixture=analyse('fixture',True);report['fixture_setup']=fixture;save()
 if not (fixture.get('command') or {}).get('actually_applied'):raise RuntimeError('Fixture setup was not accepted')
 record_case('active_observation_wait','hold',analyse(apply=True),audit_policy='off')
 baseline_ids={r['id'] for r in get('records')};start=time.monotonic();post('feedback',{'provider':'qwen','apply':True,'limit':2})
 report['feedback_start']=get('status')['feedback'];save();last_print=-1
 while time.monotonic()-start<330:
  state=capture();snap=state['snapshot'];report['samples'].append(snap)
  minute=int((time.monotonic()-start)//30)
  if minute!=last_print:
   print(json.dumps({'monitor_elapsed_seconds':round(time.monotonic()-start),'process_time':snap['process_time'],'measurement':snap['readings'][report['package']['sensor']]['value'],'target':snap['target'],'feedback':state['feedback']}),flush=True);last_print=minute
  save()
  if not state['feedback']['active'] and not state['busy']:break
  time.sleep(2)
 else:raise TimeoutError('Feedback did not finish within 330 seconds')
 feedback_rows=sorted([r for r in get('records') if r['id'] not in baseline_ids],key=lambda r:r['created_at'])
 for i,r in enumerate(feedback_rows):record_case('scheduled_monitor_'+str(i+1),'hold',r,audit_policy='off')
 report['feedback_final']=get('status')['feedback'];report['fixture_final']=next(r for r in get('records') if r['id']==fixture['id']);save()
 final=capture();lo,hi=report['package']['objective'];value=final['snapshot']['readings'][report['package']['sensor']]['value']
 report['recovery_checks']={'two_scheduled_calls':len(feedback_rows)==2,'budget_finished':not final['feedback']['active'],'fixture_outcome_completed':report['fixture_final'].get('outcome',{}).get('status')=='completed','measurement_inside':lo<=value<=hi,'unchanged_target_during_monitoring':all(s['target']==fixture['proposal']['target'] for s in report['samples'])}
 if lo<=value<=hi:
  post('arm',{'policy':'required'});capture(lambda s:s['snapshot']['armed']);record_case('inside_objective','hold',analyse(apply=True),audit_policy='required')
 report['status']='completed'
except BaseException as e:
 report.update(status='failed',error=type(e).__name__+': '+str(e));raise
finally:
 try:
  post('stop',{});ready();post('scenario',{'name':'reset'});capture();post('arm',{'policy':report['initial_policy']});capture(lambda s:s['snapshot']['armed']);post('stop',{});report['final_state']=capture(lambda s:not s['snapshot']['armed'])['snapshot']
 except Exception as e:report['cleanup_error']=str(e)
 report['finished_at']=time.time();save()
print(json.dumps({'status':report['status'],'scenarios':len(report['scenarios']),'correct':sum(r['disposition_and_target_correct'] for r in report['scenarios']),'recovery_checks':report.get('recovery_checks')}),flush=True)
