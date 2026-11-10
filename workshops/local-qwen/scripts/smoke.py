"""One local provider run; exports evidence without claiming model accuracy."""
import argparse,json,time
from pathlib import Path
import httpx
p=argparse.ArgumentParser();p.add_argument('--provider',choices=['fixture','qwen'],default='fixture');p.add_argument('--apply',action='store_true');p.add_argument('--audit',choices=['off','observe','required'],default='off');args=p.parse_args()
client=httpx.Client(base_url='http://127.0.0.1:18790',timeout=10)
def post(path,data):
    r=client.post('/api/'+path,json=data);r.raise_for_status();return r.json()
post('scenario',{'name':'reset'})
if args.apply: post('arm',{'policy':args.audit})
for _ in range(20):
    status=client.get('/api/status').json()
    if status['snapshot'] and (not args.apply or status['snapshot']['armed']):break
    time.sleep(.5)
previous={r['id'] for r in client.get('/api/records').json()}
post('analysis',{'provider':args.provider,'apply':args.apply})
for _ in range(110):
    records=client.get('/api/records').json()
    new=[r for r in records if r['id'] not in previous]
    if new and new[0]['status'] not in ('running','submitting'):
        record=new[0];break
    time.sleep(1)
else: raise SystemExit('Timed out waiting for completed record')
Path('artifacts').mkdir(exist_ok=True)
Path(f'artifacts/{args.provider}-{args.audit}-{int(time.time())}-smoke.json').write_text(json.dumps(record,indent=2))
print(json.dumps({'provider':record['provider'],'status':record['status'],'seconds':record.get('inference_seconds'),'proposal':record.get('proposal'),'audit':record.get('audit'),'command':record.get('command'),'error':record.get('error')},indent=2))
