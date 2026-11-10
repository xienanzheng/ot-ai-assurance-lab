"""Browser-independent, real-time local endurance. No automatic rearm or training."""
import argparse,json,time,subprocess
from pathlib import Path
import httpx
p=argparse.ArgumentParser(); p.add_argument('--minutes',type=float,default=60); p.add_argument('--provider',choices=['fixture','qwen'],default='fixture');args=p.parse_args()
if not 1<=args.minutes<=60: raise SystemExit('Duration must be 1–60 minutes')
c=httpx.Client(base_url='http://127.0.0.1:18790',timeout=10)
def post(path,body):
    r=c.post('/api/'+path,json=body);r.raise_for_status();return r.json()
initial=c.get('/api/status').json()
if initial['busy'] or initial['feedback']['active']: raise SystemExit('An existing run owns supervision')
post('scenario',{'name':'reset'});post('arm',{'policy':'off'})
for _ in range(30):
    status=c.get('/api/status').json()
    if status['snapshot'] and status['snapshot']['armed']:break
    time.sleep(.5)
else:raise SystemExit('No armed fresh capture')
start=time.monotonic(); wall=time.time(); before={r['id'] for r in c.get('/api/records').json()}
post('feedback',{'provider':args.provider,'apply':True,'limit':12})
Path('artifacts').mkdir(exist_ok=True)
path=Path('artifacts/endurance-'+str(int(wall))+'.json')
report=dict(status='running',duration_minutes=args.minutes,provider=args.provider,started_at=wall,
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
    package_hash=status['package_hash'],samples=[],errors=[])
try:
    while time.monotonic()-start<args.minutes*60:
        try:
            s=c.get('/api/status').json(); snap=s.get('snapshot')
            report['samples'].append(dict(wall_time=time.time(),process_time=snap['process_time'] if snap else None,
                target=snap['target'] if snap else None,value=snap['readings'][s['package']['sensor']]['value'] if snap else None,
                armed=snap['armed'] if snap else None,quality=snap['readings'][s['package']['sensor']]['quality'] if snap else None,
                capture_error=s['capture_error'],feedback=s['feedback']))
        except Exception as e:report['errors'].append({'time':time.time(),'error':str(e)})
        report['elapsed_seconds']=time.monotonic()-start;path.write_text(json.dumps(report,indent=2))
        print(json.dumps({'elapsed_seconds':round(report['elapsed_seconds']),'samples':len(report['samples']),'errors':len(report['errors'])}),flush=True)
        time.sleep(min(5,max(.1,args.minutes*60-(time.monotonic()-start))))
    records=[r for r in c.get('/api/records').json() if r['id'] not in before]
    samples=report['samples']
    report.update(status='completed',elapsed_seconds=time.monotonic()-start,records=records,
        checks={'call_budget':0<len(records)<=12,'telemetry_samples':len(samples)>=args.minutes*10,
                'no_transport_errors':not report['errors'],
                'no_capture_errors':bool(samples) and all(not s['capture_error'] for s in samples),
                'good_measurements':bool(samples) and all(s['quality']=='good' for s in samples),
                'poll_gaps_bounded':all(b['wall_time']-a['wall_time']<15 for a,b in zip(samples,samples[1:])),
                'target_accepted':any((r.get('command') or {}).get('actually_applied') for r in records),
                'recovery_observed':any((r.get('outcome') or {}).get('status')=='completed' for r in records)})
except BaseException as e:
    report.update(status='interrupted',elapsed_seconds=time.monotonic()-start)
    report['errors'].append({'time':time.time(),'error':type(e).__name__+': '+str(e)})
    raise
finally:
    try:post('stop',{})
    except Exception as e:
        report['errors'].append({'time':time.time(),'error':'stop: '+str(e)})
        report['stop_failed']=True
    report['passed']=report['status']=='completed' and not report['errors'] and all(report.get('checks',{}).values())
    path.write_text(json.dumps(report,indent=2))
print(str(path))
