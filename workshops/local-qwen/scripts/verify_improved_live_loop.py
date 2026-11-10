"""Real model-selected correction and monitoring, via local V2 public API.

No fixture target or direct simulator commands. Resets only the local bench.
"""
import argparse,json,time
from pathlib import Path
import httpx
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True)
parser.add_argument('--policy',choices=['off','observe','required'],default='off')
args=parser.parse_args();path=Path(args.output)
if path.exists():raise SystemExit('Preserve existing evidence')
c=httpx.Client(base_url='http://127.0.0.1:18790',timeout=15)
def get(p):r=c.get('/api/'+p);r.raise_for_status();return r.json()
def post(p,b):r=c.post('/api/'+p,json=b);r.raise_for_status();return r.json()
def wait(predicate,seconds=120):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  s=get('status')
  if s['snapshot'] and not s['capture_error'] and predicate(s):return s
  time.sleep(.5)
 raise TimeoutError('Expected state not observed')
initial=get('status')
if initial['busy'] or initial['feedback']['active'] or initial['snapshot']['armed']:raise SystemExit('Existing supervision active')
report={'started_at':time.time(),'package':initial['package'],'policy':args.policy,'status':'running','samples':[]}
def save():path.write_text(json.dumps(report,indent=2))
try:
 post('scenario',{'name':'reset'});wait(lambda s:True)
 post('arm',{'policy':args.policy});wait(lambda s:s['snapshot']['armed'])
 report['before']=get('status')['snapshot'];old={r['id'] for r in get('records')}
 post('analysis',{'provider':'qwen','apply':True});wait(lambda s:not s['busy'])
 record=next(r for r in get('records') if r['id'] not in old);report['initial_record']=record;save()
 print(json.dumps({'initial_status':record['status'],'proposal':record['proposal'],'audit':record.get('audit'),'command':record.get('command')}),flush=True)
 if not (record.get('command') or {}).get('actually_applied'):
  report.update(status='completed',passed=False,failure='Qwen did not produce an applied correction');save()
 else:
  baseline={r['id'] for r in get('records')};post('feedback',{'provider':'qwen','apply':True,'limit':2})
  deadline=time.monotonic()+330;last_print=0
  while time.monotonic()<deadline:
   s=get('status');report['samples'].append(s['snapshot']);save()
   if time.monotonic()-last_print>30:
    print(json.dumps({'process_time':s['snapshot']['process_time'],'measurement':s['snapshot']['readings'][s['package']['sensor']]['value'],'feedback':s['feedback']}),flush=True);last_print=time.monotonic()
   if not s['busy'] and not s['feedback']['active']:break
   time.sleep(2)
  else:raise TimeoutError('Feedback failed to finish')
  # Reaching the call budget does not stop outcome observation. Allow the
  # measured response to finish its sustain interval without another AI call.
  deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   latest=next(r for r in get('records') if r['id']==record['id'])
   if (latest.get('outcome') or {}).get('status')!='observing':break
   report['samples'].append(get('status')['snapshot']);save();time.sleep(2)
  if args.policy=='observe':
   deadline=time.monotonic()+60
   while time.monotonic()<deadline:
    reviewed=[r for r in get('records') if r['id']==record['id'] or r['id'] not in baseline]
    if all(r.get('audit') is not None for r in reviewed):break
    time.sleep(.5)
   else:raise TimeoutError('Background audits did not complete')
  report['followups']=[r for r in get('records') if r['id'] not in baseline]
  report['final_record']=next(r for r in get('records') if r['id']==record['id'])
  report['after']=get('status');p=report['package'];value=report['after']['snapshot']['readings'][p['sensor']]['value']
  report['checks']={'qwen_target_applied':record['command']['actually_applied'],
   'initial_measurement_did_not_jump':abs(record['readback']['readings'][p['sensor']]['value']-record['proposal']['target'])>1e-3,
   'two_followups':len(report['followups'])==2,
   'followups_after_command_wait':all(r['input']['snapshot']['process_time']>=record['command']['process_time']+p['observe_seconds'] for r in report['followups']),
   'budget_finished':not report['after']['feedback']['active'],
   'sustained_recovery':(report['final_record'].get('outcome') or {}).get('status')=='completed',
   'measurement_inside':p['objective'][0]<=value<=p['objective'][1]}
  if args.policy=='observe':report['checks']['background_reviews_finished']=all(r.get('audit') is not None for r in reviewed)
  report.update(status='completed',passed=all(report['checks'].values()));save()
except BaseException as error:
 report.update(status='failed',passed=False,error=type(error).__name__+': '+str(error))
 raise
finally:
 try:
  post('stop',{});wait(lambda s:not s['busy']);post('scenario',{'name':'reset'});wait(lambda s:True)
  post('arm',{'policy':initial['policy']});wait(lambda s:s['snapshot']['armed']);post('stop',{});report['final_state']=wait(lambda s:not s['snapshot']['armed'])['snapshot']
 except Exception as error:report.update(cleanup_error=str(error),passed=False)
 report['finished_at']=time.time();save()
print(json.dumps({k:report.get(k) for k in ['status','passed','checks','failure','cleanup_error']}),flush=True)
