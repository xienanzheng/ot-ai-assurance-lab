"""Paired hosted Qwen comparison on the frozen 400-case validation split."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import tomllib
import urllib.request
import urllib.error
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.water_alarm_benchmark import OUT as DATASET,score
from scripts.run_water_alarm_study import aggregate,model_path
MODEL='@cf/qwen/qwen3-30b-a3b-fp8'
OUT=ROOT/'artifacts/posttraining/cloudflare-water-compare-v1'


def credential():
    key=os.getenv('CLOUDFLARE_API_TOKEN')
    if not key:
        path=Path.home()/'Library/Preferences/.wrangler/config/default.toml'
        key=tomllib.loads(path.read_text()).get('oauth_token')
    if not key:raise ValueError('Cloudflare credential unavailable')
    return key


def request_for(row,tokenizer):
    if row['split']!='valid':raise ValueError('Comparison restricted to validation')
    prompt=tokenizer.apply_chat_template(row['payload']['messages'],tokenize=False,
                                       add_generation_prompt=True,enable_thinking=False)
    return {'prompt':prompt,'raw':True,'stream':False,'max_tokens':256,'temperature':0,'seed':42}


def extract(body):
    if body.get('success') is False:raise ValueError('Cloudflare returned an unsuccessful result')
    result=body.get('result',body)
    choices=result.get('choices') or []
    content=choices[0].get('message',{}).get('content',choices[0].get('text')) if choices else result.get('response')
    if not isinstance(content,str):raise ValueError('No text response')
    return content


def collect(limit=400):
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(model_path(),local_files_only=True)
    account=os.environ.get('CLOUDFLARE_ACCOUNT_ID','f29a7bd2b3a7ceab9233df575b1058cb')
    source=DATASET/'valid.cases.jsonl'
    all_rows=[json.loads(x) for x in source.read_text().splitlines()]
    OUT.mkdir(parents=True,exist_ok=True)
    identity={'model':MODEL,'split':'valid','case_ids':[r['id'] for r in all_rows],
      'data_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
      'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'scorer_sha256':hashlib.sha256((ROOT/'scripts/water_alarm_benchmark.py').read_bytes()).hexdigest(),
      'protocol':'Identical rendered Qwen3 prompt; raw mode; temperature zero; 256 output tokens. Four concurrent cloud requests. No actuation.'}
    manifest=OUT/'manifest.json'
    if manifest.exists() and json.loads(manifest.read_text())!=identity:raise ValueError('Comparison identity changed')
    manifest.write_text(json.dumps(identity,indent=2))
    path=OUT/'responses.jsonl'
    records=[] if not path.exists() else [json.loads(x) for x in path.read_text().splitlines()]
    seen={r['id'] for r in records}
    jobs=[(row,request_for(row,tokenizer)) for row in all_rows[:limit] if row['id'] not in seen]
    def call(row,payload):
        start=time.perf_counter()
        record={'id':row['id'],'kind':row['kind'],'request':payload,'model':MODEL}
        for attempt in range(3):
            try:
                req=urllib.request.Request(f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}',
                    data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+credential(),'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=90) as response:body=json.load(response)
                record['response']=body
                output=extract(body)
                record.update(response=body,output=output,score=score(output,row),latency_seconds=time.perf_counter()-start,attempts=attempt+1)
                return record
            except urllib.error.HTTPError as exc:
                if exc.code in {429,502,503,504} and attempt<2:time.sleep(2**(attempt+1));continue
                record['error']=f'HTTP {exc.code}';break
            except Exception as exc:record['error']=type(exc).__name__;break
        record.update(output='',score=score('',row),latency_seconds=time.perf_counter()-start)
        return record
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(call,*job) for job in jobs]):
            record=future.result()
            with path.open('a') as handle:handle.write(json.dumps(record)+'\n')
            records.append(record)
            print(len(records),'completed',sum('error' in r for r in records),'transport errors',flush=True)
    chosen={r['id'] for r in records}
    report={'count':len(records),'hosted':aggregate(records),'transport_errors':sum('error' in r for r in records),'local':{}}
    for variant in ['base','lr5e5','lr1e4']:
        local=[json.loads(x) for x in (DATASET/f'{variant}-valid.jsonl').read_text().splitlines()]
        report['local'][variant]=aggregate([r for r in local if r['id'] in chosen])
    (OUT/'summary.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int,default=400)
    args=parser.parse_args()
    if not 1<=args.limit<=400:parser.error('Limit must be 1..400')
    collect(args.limit)
