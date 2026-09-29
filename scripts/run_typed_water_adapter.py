"""Second development strategy: focus supervised loss on a compact decision choice."""
import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.water_context_study import OUT,typed_request,decode_choice
from scripts.water_alarm_benchmark import score
from scripts.run_water_context_study import verify,lines,pilot_rows,token_prompt,sha,freeze,write,append,summarize,model_path,evaluate
STUDY=OUT/'typed-study'


def training_target(row):
    """Uses labels only while building supervised targets; never in inference."""
    good=[]
    for choice in ['escalate','hold','increase','decrease']:
        target={'decision':choice,'confidence':.8}
        result=score(decode_choice(target,row['payload']),row)
        if result['correct'] and result['assessment_supported']:good.append(target)
    if len(good)!=1:raise ValueError('Ambiguous compact training target')
    return good[0]


def prepare():
    verify()
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(model_path(),local_files_only=True)
    STUDY.mkdir(exist_ok=True)
    identity={'source_manifest_sha256':sha(OUT/'manifest.json'),'script_sha256':sha(__file__),
        'scope':'Same fresh development splits, compact typed supervision; no locked test',
        'updates':80,'rank':8,'layers':4,'learning_rate':5e-5,'splits':{}}
    for split in ['train','valid']:
        chats=[];lengths=[]
        for row in lines(OUT/f'{split}.cases.jsonl'):
            payload=typed_request(row['payload']);prefix=token_prompt(tokenizer,payload)
            messages=payload['messages']+[{'role':'assistant','content':json.dumps(training_target(row),separators=(',',':'))}]
            full=tokenizer.apply_chat_template(messages,return_dict=False,enable_thinking=False)
            if full[:len(prefix)]!=prefix or len(full)>4096:raise ValueError('Training prefix or context overflow')
            lengths.append(len(full));chats.append({'messages':messages})
        raw=''.join(json.dumps(r,separators=(',',':'))+'\n' for r in chats);path=STUDY/f'{split}.jsonl'
        if path.exists() and path.read_text()!=raw:raise ValueError('Compact dataset changed')
        if not path.exists():path.write_text(raw)
        identity['splits'][split]={'count':len(chats),'sha256':sha(path),'max_tokens':max(lengths)}
    freeze(STUDY/'manifest.json',identity)
    print('Compact target dataset prepared',identity['splits'],flush=True)


def verify_typed():
    verify();identity=json.loads((STUDY/'manifest.json').read_text())
    if identity['script_sha256']!=sha(__file__) or identity['source_manifest_sha256']!=sha(OUT/'manifest.json'):
        raise ValueError('Compact experiment identity changed')
    for split,info in identity['splits'].items():
        if sha(STUDY/f'{split}.jsonl')!=info['sha256']:raise ValueError('Compact dataset changed')


def train():
    verify_typed();adapter=STUDY/'adapter'
    if (adapter/'training-complete.json').exists():
        done=json.loads((adapter/'training-complete.json').read_text())
        if done['adapter_sha256']!=sha(adapter/'adapters.safetensors') or done['config_sha256']!=sha(adapter/'adapter_config.json'):
            raise ValueError('Compact adapter changed')
        return
    if adapter.exists():raise ValueError('Partial compact training exists; do not overwrite')
    command=[sys.executable,str(ROOT/'scripts/train_water_alarm_adapter.py'),'--model',model_path(),'--train','--data',str(STUDY),
        '--adapter-path',str(adapter),'--iters','80','--batch-size','1','--num-layers','4','--mask-prompt','--grad-checkpoint',
        '--max-seq-length','4096','--learning-rate','0.00005','--val-batches','4','--steps-per-report','10','--steps-per-eval','40','--save-every','40','--seed','42']
    freeze(STUDY/'training-command.json',{'argv':command,'manifest_sha256':sha(STUDY/'manifest.json')})
    subprocess.run(command,cwd=ROOT,check=True);verify_typed()
    write(adapter/'training-complete.json',{'adapter_sha256':sha(adapter/'adapters.safetensors'),'config_sha256':sha(adapter/'adapter_config.json'),'approved':False})


def evaluate_adapter():
    verify_typed();adapter=STUDY/'adapter'
    done=json.loads((adapter/'training-complete.json').read_text())
    if done['adapter_sha256']!=sha(adapter/'adapters.safetensors') or done['config_sha256']!=sha(adapter/'adapter_config.json'):
        raise ValueError('Compact adapter changed')
    path=OUT/'local-typed-adapter.jsonl';identity=OUT/'local-typed-adapter.identity.json'
    if path.exists() and not identity.exists():raise ValueError('Unbound evaluation')
    freeze(identity,{'typed_manifest_sha256':sha(STUDY/'manifest.json'),'pilot_sha256':sha(OUT/'pilot.json'),
        'weights':done,'temperature':0,'max_output':256,'thinking':False})
    rows=pilot_rows(lines(OUT/'valid.cases.jsonl'));by_id={r['id']:r for r in rows}
    records=lines(path) if path.exists() else [];seen={r['id'] for r in records}
    if len(seen)!=len(records) or not seen<=by_id.keys():raise ValueError('Invalid cache IDs')
    for r in records:
        if r['score']!=score(r['decoded'],by_id[r['id']]):raise ValueError('Cached score differs')
    pending=[r for r in rows if r['id'] not in seen]
    if pending:
        from mlx_lm import load,generate
        from mlx_lm.sample_utils import make_sampler
        model,tokenizer=load(model_path(),adapter_path=str(adapter))
    for row in pending:
        payload=typed_request(row['payload']);prompt=token_prompt(tokenizer,payload);start=time.perf_counter()
        output=generate(model,tokenizer,prompt=prompt,max_tokens=256,sampler=make_sampler(temp=0),verbose=False)
        record={'id':row['id'],'kind':row['kind'],'input':payload,'output':output,'decoded':'',
            'latency_seconds':time.perf_counter()-start,'input_tokens':len(prompt),'output_tokens':len(tokenizer.encode(output))}
        try:record['decoded']=decode_choice(output,row['payload'])
        except (ValueError,TypeError):record['decode_error']='Invalid typed choice'
        record['score']=score(record['decoded'],row);append(path,record);records.append(record)
        print('compact-adapter',len(records),row['kind'],record['score']['correct'],flush=True)
    verify_typed();write(OUT/'local-typed-adapter-summary.json',summarize(records))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['prepare','train','eval','study']);args=parser.parse_args()
    with (OUT/'local.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if args.stage=='prepare':prepare()
        elif args.stage=='train':train()
        elif args.stage=='eval':evaluate_adapter()
        else:
            prepare()
            # Process boundaries release Metal buffers and ensure sequential training/evaluation.
            for code in ["from scripts.run_water_context_study import evaluate; evaluate('local','typed')",
                         'from scripts.run_typed_water_adapter import train; train()',
                         'from scripts.run_typed_water_adapter import evaluate_adapter; evaluate_adapter()']:
                subprocess.run([sys.executable,'-c',code],cwd=ROOT,check=True)

if __name__=='__main__':main()
