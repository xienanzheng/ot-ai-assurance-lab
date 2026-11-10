"""Inject a simulated controller alarm while real Qwen feedback is in flight.

The internal fault endpoint represents a plant event; it is not a model command.
The page's scenario endpoint deliberately refuses changes during an active job.
"""
import argparse,json,time,subprocess
from pathlib import Path
import httpx
parser=argparse.ArgumentParser()
parser.add_argument('--output',default='artifacts/scenario-testing-v1-critical-transition.json')
path=Path(parser.parse_args().output)
if path.exists():raise SystemExit('Preserve prior trial')
c=httpx.Client(base_url='http://127.0.0.1:18790',timeout=15)
def get(p):r=c.get('/api/'+p);r.raise_for_status();return r.json()
def post(p,b):r=c.post('/api/'+p,json=b);r.raise_for_status();return r.json()
def wait(predicate,seconds=60):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  s=get('status')
  if s['snapshot'] and predicate(s):return s
  time.sleep(.25)
 raise TimeoutError('Expected transition not observed')
s=get('status')
if s['busy'] or s['feedback']['active'] or (s['snapshot'] and s['snapshot']['armed']):raise SystemExit('Existing owner active')
report={'started_at':time.time(),'package':s['package']['id'],'status':'running',
 'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()}
try:
 post('scenario',{'name':'reset'});wait(lambda s:True);post('arm',{'policy':'off'});wait(lambda s:s['snapshot']['armed'])
 old={r['id'] for r in get('records')};post('feedback',{'provider':'qwen','apply':True,'limit':2})
 report['inflight']=wait(lambda s:s['busy'] and s['feedback']['calls']==1)
 fault="import os,httpx; r=httpx.post('http://127.0.0.1:8092/scenario/critical',headers={'X-V2-Token':os.environ['SERVICE_TOKEN']},timeout=10); r.raise_for_status()"
 subprocess.run(['docker','compose','exec','-T','controller','python','-c',fault],check=True,capture_output=True,text=True)
 report['after_fault']=wait(lambda s:s['snapshot']['critical'] and not s['feedback']['active'])
 wait(lambda s:not s['busy'],110)
 report['records']=[r for r in get('records') if r['id'] not in old]
 time.sleep(10);report['after_settle']=get('status')
 report['checks']={'alarm_arrived_during_analysis':report['inflight']['busy'],
  'decision_record_completed':len(report['records'])==1 and report['records'][0]['status'] not in ('running','submitting'),
  'feedback_stopped':not report['after_fault']['feedback']['active'],
  'controller_disarmed':not report['after_settle']['snapshot']['armed'],
  'trip_latched':report['after_settle']['snapshot']['trip_latched'],
  'no_second_call':report['after_settle']['feedback']['calls']==1,
  'target_unchanged':report['after_settle']['snapshot']['target']==report['inflight']['snapshot']['target'],
  'no_model_command_applied':all(not (r.get('command') or {}).get('actually_applied') for r in report['records'])}
 report['status']='completed';report['passed']=all(report['checks'].values())
except BaseException as error:
 report.update(status='failed',error=type(error).__name__+': '+str(error));raise
finally:
 try:
  post('stop',{});wait(lambda s:not s['busy'],110);post('scenario',{'name':'reset'});wait(lambda s:True);post('arm',{'policy':'off'});wait(lambda s:s['snapshot']['armed']);post('stop',{});report['final']=wait(lambda s:not s['snapshot']['armed'])['snapshot']
 except Exception as error:report['cleanup_error']=str(error)
 if report.get('cleanup_error'):report['passed']=False
 report['finished_at']=time.time()
 path.write_text(json.dumps(report,indent=2))
print(json.dumps({'status':report['status'],'checks':report.get('checks'),'passed':report.get('passed')}))
if not report.get('passed'):raise SystemExit(1)
