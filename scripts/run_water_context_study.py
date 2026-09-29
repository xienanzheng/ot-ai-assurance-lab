"""Bounded development experiment; no locked-test access or model promotion."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import urllib.request
import urllib.error
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.water_context_study import OUT, VERSION, fresh_case, assist, typed_request, decode_choice
from scripts.water_alarm_benchmark import score
from scripts.run_water_alarm_study import aggregate, model_path, MODEL_REVISION
from scripts.compare_cloudflare_water import credential, MODEL, extract


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,indent=2));temporary.replace(path)
def freeze(path,value):
    if path.exists() and json.loads(path.read_text())!=value: raise ValueError(f'Frozen identity changed: {path.name}')
    write(path,value)
def lines(path): return [json.loads(x) for x in path.read_text().splitlines()]
def append(path,value):
    with path.open('a') as stream:
        stream.write(json.dumps(value)+'\n');stream.flush();os.fsync(stream.fileno())
def pilot_rows(rows):
    groups={k:[r for r in rows if r['kind']==k][:8] for k in ['critical','prerequisite','hold','adjust']}
    if any(len(v)!=8 for v in groups.values()): raise ValueError('Incomplete pilot strata')
    return [groups[k][i] for i in range(8) for k in groups]
def payload_for(row,mode):
    return row['payload'] if mode=='baseline' else (assist(row['payload']) if mode=='assisted' else typed_request(row['payload']))
def token_prompt(tokenizer,payload):
    tokens=tokenizer.apply_chat_template(payload['messages'],add_generation_prompt=True,enable_thinking=False,return_dict=False)
    if len(tokens)+256>4096: raise ValueError('Oversized context; no truncation')
    return tokens


def prepare():
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(model_path(),local_files_only=True)
    OUT.mkdir(parents=True,exist_ok=True)
    source_files=['scripts/water_context_study.py','scripts/run_water_context_study.py','scripts/water_alarm_benchmark.py',
        'scripts/train_water_alarm_adapter.py','services/supervisor/app/water_alarm.py','services/supervisor/app/plant_sops.json',
        'services/plant_sim/app/simulator.py','services/plc_control/app/controller.py','shared/models.py','shared/limits.py']
    manifest={'version':VERSION,'base_revision':MODEL_REVISION,'sources':{f:sha(ROOT/f) for f in source_files},
        'scope':'Fresh development episodes; same scenario families. No locked test or visitor data.', 'splits':{}}
    for split,count in [('train',1200),('valid',160)]:
        rows=[fresh_case(i,split,count) for i in range(count)]
        random.Random(42 if split=='train' else 43).shuffle(rows)
        lengths=[];training=[]
        for row in rows:
            s=score(row['teacher'],row)
            if not (s['valid'] and s['correct'] and s['assessment_supported'] and not s['reference_errors']):
                raise ValueError('Invalid training label')
            payload=assist(row['payload']);prefix=token_prompt(tokenizer,payload)
            messages=payload['messages']+[{'role':'assistant','content':json.dumps(row['teacher'],separators=(',',':'))}]
            full=tokenizer.apply_chat_template(messages,enable_thinking=False,return_dict=False)
            if full[:len(prefix)]!=prefix or len(full)>4096: raise ValueError('Training prefix/length mismatch')
            lengths.append(len(full));training.append({'messages':messages})
        for name,values in [(f'{split}.cases.jsonl',rows),(f'{split}.jsonl',training)]:
            raw=''.join(json.dumps(r,separators=(',',':'))+'\n' for r in values)
            path=OUT/name
            if path.exists() and path.read_text()!=raw:raise ValueError('Dataset already frozen with different content')
            if not path.exists():path.write_text(raw)
        manifest['splits'][split]={'count':count,'cases_sha256':sha(OUT/f'{split}.cases.jsonl'),
            'training_sha256':sha(OUT/f'{split}.jsonl'),'max_training_tokens':max(lengths)}
    freeze(OUT/'manifest.json',manifest)
    selected=pilot_rows(lines(OUT/'valid.cases.jsonl'))
    freeze(OUT/'pilot.json',{'ids':[r['id'] for r in selected],'count':32,'per_kind':8})
    print(json.dumps(manifest['splits']),flush=True)


def verify():
    manifest=json.loads((OUT/'manifest.json').read_text())
    for name,digest in manifest['sources'].items():
        if sha(ROOT/name)!=digest:raise ValueError(f'Source changed after freeze: {name}')
    for split,info in manifest['splits'].items():
        if sha(OUT/f'{split}.cases.jsonl')!=info['cases_sha256'] or sha(OUT/f'{split}.jsonl')!=info['training_sha256']:
            raise ValueError('Dataset changed')
    return manifest


def summarize(records):
    warm=[r['latency_seconds'] for r in records[1:] if not r.get('error')]
    return {**aggregate(records),'by_kind':{k:aggregate([r for r in records if r['kind']==k]) for k in ['critical','prerequisite','hold','adjust']},
        'transport_errors':sum(bool(r.get('error')) for r in records),'denominator':32,
        'warm_median_seconds':statistics.median(warm) if warm else None,
        'warm_p95_seconds':sorted(warm)[min(len(warm)-1,int(.95*len(warm)))] if warm else None,
        'timing_note':'Sequential, first excluded. Local matched prompts; hosted timing is a separate system measurement.',
        'reported_usage':[r.get('response',{}).get('result',{}).get('usage') for r in records if 'response' in r],
        'approved':False,'locked_test_used':False}


def evaluate(runtime,mode,adapter=False):
    verify()
    if runtime=='cloud' and adapter:raise ValueError('Local adapter cannot be uploaded to this Workers AI model')
    selected=pilot_rows(lines(OUT/'valid.cases.jsonl'))
    label=f'{runtime}-{mode}'+('-adapter' if adapter else '-base')
    path=OUT/f'{label}.jsonl'
    identity={'manifest_sha256':sha(OUT/'manifest.json'),'pilot_sha256':sha(OUT/'pilot.json'),
        'runtime':runtime,'mode':mode,'model':MODEL if runtime=='cloud' else MODEL_REVISION,
        'adapter_sha256':sha(OUT/'adapter/adapters.safetensors') if adapter else None,
        'temperature':0,'output_tokens':2048 if runtime=='cloud' else 256,'sequential':True}
    if adapter:
        done=json.loads((OUT/'adapter/training-complete.json').read_text())
        if done['adapter_sha256']!=identity['adapter_sha256']:raise ValueError('Adapter changed')
    freeze(OUT/f'{label}.identity.json',identity)
    records=lines(path) if path.exists() else []
    by_id={r['id']:r for r in selected};seen={r['id'] for r in records}
    if len(seen)!=len(records) or not seen<=by_id.keys():raise ValueError('Invalid resume IDs')
    for record in records:
        if record['score']!=score(record['decoded'],by_id[record['id']]):raise ValueError('Cached score mismatch')
    pending=[r for r in selected if r['id'] not in seen]
    if pending and runtime=='local':
        from mlx_lm import load,generate
        from mlx_lm.sample_utils import make_sampler
        model,tokenizer=load(model_path(),adapter_path=str(OUT/'adapter') if adapter else None)
    key=credential() if pending and runtime=='cloud' else None
    for row in pending:
        payload=payload_for(row,mode);start=time.perf_counter()
        record={'id':row['id'],'kind':row['kind'],'input':payload,'decoded':'','output':''}
        if runtime=='local':
            prompt=token_prompt(tokenizer,payload)
            output=generate(model,tokenizer,prompt=prompt,max_tokens=256,sampler=make_sampler(temp=0),verbose=False)
            record.update(output=output,input_tokens=len(prompt),output_tokens=len(tokenizer.encode(output)))
        else:
            # Mirrors production Workers AI modelRequest transport; all variants share settings.
            request={'messages':payload['messages']+[{'role':'system','content':'Return only a JSON object matching this schema. /no_think\n'+json.dumps(payload['schema'])}],
                'stream':False,'max_tokens':2048,'temperature':0,'seed':42,
                'response_format':{'type':'json_schema','json_schema':payload['schema']}}
            record['request']=request
            account=os.environ.get('CLOUDFLARE_ACCOUNT_ID','f29a7bd2b3a7ceab9233df575b1058cb')
            req=urllib.request.Request(f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{MODEL}',data=json.dumps(request).encode(),
                headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
            record['attempts']=[]
            for attempt in range(2):
                try:
                    with urllib.request.urlopen(req,timeout=90) as response: body=json.load(response)
                    record['response']=body;record['output']=extract(body)
                    record['attempts'].append({'status':200});break
                except urllib.error.HTTPError as exc:
                    record['attempts'].append({'status':exc.code})
                    if exc.code in {429,502,503,504} and attempt==0:time.sleep(2);continue
                    record['error']=f'HTTP {exc.code}';break
                except (TimeoutError,urllib.error.URLError) as exc:
                    record['attempts'].append({'error':type(exc).__name__})
                    if attempt==0:continue
                    record['error']=type(exc).__name__;break
                except ValueError as exc:
                    record['error']=type(exc).__name__;break
        record['latency_seconds']=time.perf_counter()-start
        try: record['decoded']=decode_choice(record['output'],row['payload']) if mode=='typed' else record['output']
        except (ValueError,TypeError):record['decode_error']='Invalid typed choice'
        record['score']=score(record['decoded'],row)
        append(path,record);records.append(record)
        print(label,len(records),row['kind'],record['score']['correct'],round(record['latency_seconds'],2),flush=True)
        if record.get('error') in {'HTTP 401','HTTP 403'}:raise RuntimeError('Cloudflare authentication failed; stopped without further calls')
    verify();write(OUT/f'{label}-summary.json',summarize(records))


def train():
    verify();target=OUT/'adapter'
    if (target/'training-complete.json').exists():
        done=json.loads((target/'training-complete.json').read_text())
        if done['adapter_sha256']!=sha(target/'adapters.safetensors'):raise ValueError('Adapter changed')
        return
    if target.exists():raise ValueError('Partial adapter exists; do not overwrite')
    command=[sys.executable,str(ROOT/'scripts/train_water_alarm_adapter.py'),'--model',model_path(),'--train','--data',str(OUT),
        '--adapter-path',str(target),'--iters','80','--batch-size','1','--num-layers','4','--mask-prompt','--grad-checkpoint',
        '--max-seq-length','4096','--learning-rate','0.00005','--val-batches','4','--steps-per-report','10','--steps-per-eval','40','--save-every','40','--seed','42']
    freeze(OUT/'training-command.json',{'argv':command,'manifest_sha256':sha(OUT/'manifest.json'),'rank':8,'steps':80})
    subprocess.run(command,cwd=ROOT,check=True)
    verify();write(target/'training-complete.json',{'adapter_sha256':sha(target/'adapters.safetensors'),
        'config_sha256':sha(target/'adapter_config.json'),'command_sha256':sha(OUT/'training-command.json'),'approved':False})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','local-study','cloud-study','train','eval'])
    parser.add_argument('--runtime',choices=['local','cloud'],default='local');parser.add_argument('--mode',choices=['baseline','assisted','typed'],default='assisted');parser.add_argument('--adapter',action='store_true')
    args=parser.parse_args();OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/f'{"cloud" if args.stage=="cloud-study" or args.runtime=="cloud" else "local"}.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.stage=='prepare':prepare()
        elif args.stage=='train':train()
        elif args.stage=='eval':evaluate(args.runtime,args.mode,args.adapter)
        elif args.stage=='cloud-study':
            for mode in ['baseline','assisted','typed']:evaluate('cloud',mode)
        else:
            # Separate processes release all Metal buffers before training and matched evaluation.
            for extra in [('eval','--mode','assisted'),('train',),('eval','--mode','assisted','--adapter')]:
                subprocess.run([sys.executable,__file__,*extra],check=True,env={**os.environ,'WATER_CONTEXT_CHILD':'1'})

if __name__=='__main__':
    # Child processes still acquire the same lock after the parent launches each stage directly.
    if os.environ.get('WATER_CONTEXT_CHILD')=='1':
        if sys.argv[1]=='train':train()
        else:evaluate('local','assisted','--adapter' in sys.argv)
    else:main()
