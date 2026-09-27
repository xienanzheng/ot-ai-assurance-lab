"""Sequential, resumable local study. Locked test is opened only after selection."""
import argparse
from datetime import datetime,timezone
import hashlib
import fcntl
import json
from pathlib import Path
import statistics
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.water_alarm_benchmark import OUT,VERSION,score
from shared.water_study_provenance import evaluation_identity,bind_artifact,sha256

MODEL_REVISION='4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25'
MAX_SEQUENCE=4096
MAX_OUTPUT=256


def write(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(value,indent=2));temporary.replace(path)


def model_path():
    manifest=json.loads((ROOT/'artifacts/posttraining/models.json').read_text())['mlx-community/Qwen3-4B-4bit']
    if manifest['revision']!=MODEL_REVISION:raise ValueError('Unmatched base revision')
    return manifest['path']


def prompt_tokens(tokenizer,row):
    tokens=tokenizer.apply_chat_template(row['payload']['messages'],add_generation_prompt=True,enable_thinking=False,tokenize=True,return_dict=False)
    if len(tokens)+MAX_OUTPUT>MAX_SEQUENCE:raise ValueError(f"Oversized case {row['id']}: {len(tokens)} tokens; no truncation allowed")
    return tokens


def aggregate(rows):
    critical=[r for r in rows if r['kind']=='critical'];other=[r for r in rows if r['kind']!='critical']
    return {'count':len(rows),'critical_count':len(critical),'critical_correct':sum(r['score']['critical_ok'] for r in critical),
      'valid':sum(r['score']['valid'] for r in rows),'supported_assessments':sum(r['score']['assessment_supported'] for r in rows),
      'other_count':len(other),'other_correct':sum(r['score']['correct'] for r in other),
      'reference_errors':sum(r['score']['reference_errors'] for r in rows),
      'correct':sum(r['score']['correct'] for r in rows)}


def evaluate(variant,split,adapter=None):
    import mlx.core as mx
    from mlx_lm import load
    from mlx_lm.generate import batch_generate
    from mlx_lm.sample_utils import make_sampler
    result_path=OUT/f'{variant}-{split}.jsonl'
    identity=evaluation_identity(OUT,MODEL_REVISION,adapter)
    bind_artifact(result_path,identity)
    bind_artifact(OUT/f'{variant}-{split}-summary.json',identity)
    finished=[] if not result_path.exists() else [json.loads(x) for x in result_path.read_text().splitlines()]
    seen={x['id'] for x in finished}
    if len(seen)!=len(finished):raise ValueError('Duplicate cached case IDs')
    rows=[json.loads(x) for x in (OUT/f'{split}.cases.jsonl').read_text().splitlines()]
    by_id={r['id']:r for r in rows}
    if not seen<=by_id.keys():raise ValueError('Unknown cached case IDs')
    for record in finished:
        if record['score']!=score(record['output'],by_id[record['id']]):raise ValueError('Cached score mismatch')
    pending=[x for x in rows if x['id'] not in seen]
    if not pending:
        summary={**aggregate(finished),'identity':identity,'results_sha256':sha256(result_path)}
        write(OUT/f'{variant}-{split}-summary.json',summary)
        return summary
    model,tokenizer=load(model_path(),adapter_path=adapter)
    for start in range(0,len(pending),8):
        chunk=pending[start:start+8];prompts=[prompt_tokens(tokenizer,row) for row in chunk]
        result=batch_generate(model,tokenizer,prompts,max_tokens=MAX_OUTPUT,completion_batch_size=8,prefill_batch_size=2,sampler=make_sampler(temp=0))
        for row,output in zip(chunk,result.texts):
            record={'id':row['id'],'kind':row['kind'],'output':output,'score':score(output,row)}
            with result_path.open('a') as handle:handle.write(json.dumps(record)+'\n')
            finished.append(record)
        print(variant,split,len(finished),aggregate(finished),flush=True)
        mx.clear_cache()
    if identity!=evaluation_identity(OUT,MODEL_REVISION,adapter):raise ValueError('Identity changed during evaluation')
    summary={**aggregate(finished),'identity':identity,'results_sha256':sha256(result_path)};write(OUT/f'{variant}-{split}-summary.json',summary)
    del model,tokenizer;mx.clear_cache()
    return summary


def latency(variant,adapter=None):
    identity=evaluation_identity(OUT,MODEL_REVISION,adapter)
    bind_artifact(OUT/f'{variant}-latency.json',identity)
    if (OUT/f'{variant}-latency.json').exists():
        saved=json.loads((OUT/f'{variant}-latency.json').read_text())
        if saved.get('identity')!=identity:raise ValueError('Latency identity mismatch')
        return saved
    from mlx_lm import load,generate
    from mlx_lm.sample_utils import make_sampler
    model,tokenizer=load(model_path(),adapter_path=adapter)
    rows=[json.loads(x) for x in (OUT/'test.cases.jsonl').read_text().splitlines()][:32]
    measurements=[]
    for i,row in enumerate(rows):
        prompt=prompt_tokens(tokenizer,row)
        start=time.perf_counter(); output=generate(model,tokenizer,prompt=prompt,max_tokens=MAX_OUTPUT,sampler=make_sampler(temp=0),verbose=False)
        seconds=time.perf_counter()-start
        measurements.append({'id':row['id'],'seconds':seconds,'input_tokens':len(prompt),'output_tokens':len(tokenizer.encode(output))})
        print(variant,'sequential_latency',i,round(seconds,3),flush=True)
    warm=sorted(x['seconds'] for x in measurements[1:])
    if identity!=evaluation_identity(OUT,MODEL_REVISION,adapter):raise ValueError('Identity changed during latency measurement')
    report={'identity':identity,'rows':measurements,'warm_median_seconds':statistics.median(warm),'warm_p95_seconds':warm[int(.95*(len(warm)-1))],
            'method':'sequential identical 32 full-context cases; first excluded; training stopped; temperature zero'}
    write(OUT/f'{variant}-latency.json',report)
    return report


def preflight():
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(model_path(),local_files_only=True)
    result={}
    for split in ['train','valid','test']:
        lengths=[]
        for line in (OUT/f'{split}.cases.jsonl').read_text().splitlines():
            row=json.loads(line);tokens=prompt_tokens(tokenizer,row)
            full=tokenizer.apply_chat_template(row['payload']['messages']+[{'role':'assistant','content':json.dumps(row['teacher'])}],return_dict=False,enable_thinking=False)
            if full[:len(tokens)]!=tokens:raise ValueError('Training prefix differs from inference')
            if len(full)>MAX_SEQUENCE:raise ValueError('Training example would be truncated')
            if not score(row['teacher'],row)['correct']:raise ValueError('Inconsistent teacher label')
            lengths.append(len(tokens))
        result[split]={'min':min(lengths),'max':max(lengths),'count':len(lengths)}
    write(OUT/'token-preflight.json',result)


def run_stage(stage,*extra):
    subprocess.run([sys.executable,__file__,'--stage',stage,*extra],check=True)


def study(steps):
    preflight()
    # Existing results must be bound before any resume or selection.
    for variant,adapter in [('base',None),('lr5e5',OUT/'lr5e5'),('lr1e4',OUT/'lr1e4')]:
        existing=list(OUT.glob(f'{variant}-*.json'))+list(OUT.glob(f'{variant}-*.jsonl'))
        for artifact in existing:
            if artifact.name.endswith('.identity.json'):continue
            bind_artifact(artifact,evaluation_identity(OUT,MODEL_REVISION,adapter))
    # No base or adapter outputs from the test split exist before selection.
    run_stage('eval','--variant','base','--split','valid')
    for name,lr in [('lr5e5','0.00005'),('lr1e4','0.0001')]:
        adapter=OUT/name
        done=adapter/'training-complete.json'
        training_identity={'steps':steps,'learning_rate':lr,'base_revision':MODEL_REVISION,
          'thinking':False,'layers':4,'rank':8,'batch_size':1,'seed':42,'max_sequence':MAX_SEQUENCE,
          'trainer_sha256':sha256(ROOT/'scripts/train_water_alarm_adapter.py'),
          'train_sha256':sha256(OUT/'train.jsonl'),'valid_sha256':sha256(OUT/'valid.jsonl')}
        if done.exists():
            saved=json.loads(done.read_text())
            if saved.get('training_identity')!=training_identity or saved.get('weights')!=sha256(adapter/'adapters.safetensors') or saved.get('config')!=sha256(adapter/'adapter_config.json'):
                raise ValueError('Training identity or saved adapter changed')
        if not done.exists():
            if (adapter/'adapters.safetensors').exists():raise ValueError('Incomplete training exists; do not overwrite or silently retrain')
            training_data=OUT/'training-data';training_data.mkdir(exist_ok=True)
            for split in ['train','valid']:shutil.copyfile(OUT/f'{split}.jsonl',training_data/f'{split}.jsonl')
            adapter.mkdir(exist_ok=True)
            with (adapter/'training.log').open('w') as log:
                subprocess.run([sys.executable,str(ROOT/'scripts/train_water_alarm_adapter.py'),'--model',model_path(),'--train','--data',str(training_data),
                 '--adapter-path',str(adapter),'--iters',str(steps),'--batch-size','1','--num-layers','4','--mask-prompt',
                 '--grad-checkpoint','--max-seq-length',str(MAX_SEQUENCE),'--learning-rate',lr,'--val-batches','4',
                 '--steps-per-report','10','--steps-per-eval','80','--save-every','80','--seed','42'],stdout=log,stderr=subprocess.STDOUT,check=True)
            write(done,{'training_identity':training_identity,'weights':sha256(adapter/'adapters.safetensors'),'config':sha256(adapter/'adapter_config.json')})
        run_stage('eval','--variant',name,'--split','valid','--adapter',str(adapter))
    selection_path=OUT/'selection.json'
    bind_artifact(selection_path,{name:evaluation_identity(OUT,MODEL_REVISION,OUT/name) for name in ['lr5e5','lr1e4']})
    if selection_path.exists():selection=json.loads(selection_path.read_text())
    else:
        summaries={name:json.loads((OUT/f'{name}-valid-summary.json').read_text()) for name in ['lr5e5','lr1e4']}
        best=max(summaries,key=lambda name:(summaries[name]['critical_correct'],summaries[name]['supported_assessments'],summaries[name]['correct'],summaries[name]['valid']))
        selection={'variant':best,'validation':summaries,'selected_before_test_at':datetime.now(timezone.utc).isoformat(),
             'dataset_manifest_sha256':hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest()}
        write(selection_path,selection)
    best=selection['variant']; adapter=str(OUT/best)
    for name,path in [('base',None),(best,adapter)]:
        extra=[] if path is None else ['--adapter',path]
        run_stage('eval','--variant',name,'--split','test',*extra)
        run_stage('latency','--variant',name,*extra)
    s=json.loads((OUT/f'{best}-test-summary.json').read_text()); b=json.loads((OUT/'base-latency.json').read_text()); l=json.loads((OUT/f'{best}-latency.json').read_text())
    checks={'critical':s['critical_count']==500 and s['critical_correct']==500,'structured':s['valid']>=990,
       'references':s['reference_errors']==0,'assessments':s['supported_assessments']>=950,'noncritical':s['other_correct']/s['other_count']>=.95,
       'median_latency':l['warm_median_seconds']<=b['warm_median_seconds'],'p95_latency':l['warm_p95_seconds']<=b['warm_p95_seconds']}
    report={'version':VERSION,'candidate':best,'acceptance':checks,'approved':all(checks.values()),'test':s,
       'base_latency':b,'candidate_latency':l,'base_revision':MODEL_REVISION,'adapter_path':adapter,
       'evaluation_identity':evaluation_identity(OUT,MODEL_REVISION,adapter),
       'adapter_config_sha256':sha256(Path(adapter)/'adapter_config.json'),
       'adapter_sha256':hashlib.sha256((Path(adapter)/'adapters.safetensors').read_bytes()).hexdigest(),
       'dataset_manifest_sha256':selection['dataset_manifest_sha256'],'shadow_only':True}
    write(OUT/'acceptance.json',report)
    print('FINAL',json.dumps({'approved':report['approved'],'checks':checks}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=['study','eval','latency','preflight'],default='study')
    parser.add_argument('--steps',type=int,default=160)
    parser.add_argument('--variant',default='base')
    parser.add_argument('--split',choices=['valid','test'],default='valid')
    parser.add_argument('--adapter')
    args=parser.parse_args()
    if not 1<=args.steps<=400:parser.error('Training steps must be 1..400')
    if args.stage in {'eval','latency'} and (args.split=='test' or args.stage=='latency') and not (OUT/'selection.json').exists():
        parser.error('Locked test requires completed validation selection')
    if args.stage=='study':
        with (OUT/'study.lock').open('w') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            study(args.steps)
    elif args.stage=='preflight':preflight()
    elif args.stage=='eval':evaluate(args.variant,args.split,args.adapter)
    else:latency(args.variant,args.adapter)
