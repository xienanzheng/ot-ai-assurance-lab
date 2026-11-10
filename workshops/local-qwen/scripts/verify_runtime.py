"""Real-time same-core response and restart check for the active bundled package.

Resets only the V2 bench. Uses fixture policy to isolate integration behavior.
Do not run alongside endurance or an operator demonstration.
"""
import json
import subprocess
import time
from pathlib import Path
import httpx

c=httpx.Client(base_url='http://127.0.0.1:18790',timeout=10)
def get(path):
    r=c.get('/api/'+path);r.raise_for_status();return r.json()
def post(path,body):
    r=c.post('/api/'+path,json=body);r.raise_for_status();return r.json()
def wait_capture(armed=None,old_generation=None):
    for _ in range(60):
        try:
            s=get('status'); snap=s['snapshot']
            if snap and not s['capture_error'] and (armed is None or snap['armed']==armed) and (old_generation is None or snap['generation']!=old_generation):return s
        except httpx.HTTPError:pass
        time.sleep(1)
    raise RuntimeError('No expected fresh capture')

initial=get('status')
if initial['busy'] or initial['feedback']['active']:raise SystemExit('Existing run owns supervision')
post('scenario',{'name':'reset'});post('arm',{'policy':'off'});s=wait_capture(True)
package=s['package']; before={r['id'] for r in get('records')}
start=time.monotonic()
report={'started_at':time.time(),'package':package,'package_hash':s['package_hash'],
        'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'provider':'fixture · deterministic test policy','samples':[],'checks':{},'status':'running'}
Path('artifacts').mkdir(exist_ok=True)
path=Path(f'artifacts/{package["id"]}-runtime-{int(time.time())}.json')
try:
    post('analysis',{'provider':'fixture','apply':True})
    record=None
    while time.monotonic()-start<240:
        status=get('status'); snap=status['snapshot']; rows=[r for r in get('records') if r['id'] not in before]
        if rows:record=rows[0]
        report['samples'].append(snap)
        print(json.dumps({'elapsed_seconds':round(time.monotonic()-start),'value':snap['readings'][package['sensor']]['value'],
            'target':snap['target'],'outcome':(record or {}).get('outcome')}),flush=True)
        path.write_text(json.dumps(report,indent=2))
        if record and (record.get('outcome') or {}).get('status')=='completed':break
        if record and record['status'] not in ('running','submitting','applied'):raise RuntimeError('Unexpected decision status '+record['status'])
        time.sleep(5)
    if not record:raise RuntimeError('No decision record')
    report['record_before_restart']=record
    report['checks'].update(accepted=bool((record.get('command') or {}).get('actually_applied')),
        delayed_response=len(report['samples'])>2,
        sustained_outcome=(record.get('outcome') or {}).get('status')=='completed')
    old=get('status')['snapshot']
    post('feedback',{'provider':'fixture','apply':False,'limit':2})
    report['feedback_before_restart']=get('status')['feedback']
    report['checks']['feedback_was_active']=report['feedback_before_restart']['active']
    subprocess.run(['docker','compose','restart','controller','app'],check=True)
    restarted=wait_capture(False,old['generation'])
    restored=next(r for r in get('records') if r['id']==record['id'])
    report['after_restart']=restarted['snapshot'];report['restored_record']=restored
    report['checks'].update(target_persisted=restarted['snapshot']['target']==old['target'],
        new_generation=restarted['snapshot']['generation']!=old['generation'],
        disarmed=not restarted['snapshot']['armed'],feedback_stopped=not restarted['feedback']['active'],
        record_preserved=restored['command']==record['command'])
    report['status']='completed'
except BaseException as e:
    report.update(status='failed',error=type(e).__name__+': '+str(e));raise
finally:
    report['elapsed_seconds']=time.monotonic()-start
    report['passed']=report['status']=='completed' and all(report['checks'].values())
    path.write_text(json.dumps(report,indent=2))
    try:post('stop',{})
    except httpx.HTTPError:pass
print(str(path),flush=True)
