"""Bounded, local-only typed-choice experiment. MLX imports occur only at runtime.

Choice probabilities are relative menu scores, never calibrated confidence.
Decoded rationales and proposal structure are code-authored, not model reasoning.
"""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import statistics
import platform
import time

from training.bench_cases import freeze_dataset, verify_dataset, score
from training.typed_policy import make_options, messages_for, decode_choice

PIN = '4dcb3d101c2a062e5c1d4bb173588c54ea6c4d25'
PINNED_MODEL = Path.home() / '.cache/huggingface/hub/models--mlx-community--Qwen3-4B-4bit/snapshots' / PIN
SETTINGS = dict(num_layers=4, rank=8, batch_size=1, learning_rate=5e-5,
                grad_checkpoint=True, seed=42, iters=128, checkpoints=[64,128],
                max_seq_length=4096, enable_thinking=False, mask_prompt=True,
                loss='selected_label_only', lora_scale=20.0, lora_dropout=0.0)
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,sort_keys=True,allow_nan=False,indent=2)


def read(path):return json.loads(Path(path).read_text())


def verify_binding(expected, actual):
    if expected != actual:raise ValueError('Experiment binding changed; source/dataset/model/settings drift')


def label_ids(tokenizer, labels):
    ids={}
    for label in labels:
        if label not in 'ABCDEFGHIJ' or len(label)!=1:raise ValueError('Unknown label')
        tokens=tokenizer.encode(label,add_special_tokens=False)
        if len(tokens)!=1:raise ValueError('Choice label must be exactly one token')
        ids[label]=tokens[0]
    if len(set(ids.values()))!=len(ids):raise ValueError('Choice token collision')
    return ids


def tokenize_example(tokenizer, messages: list[dict], label: str, max_length: int=4096) -> dict:
    token=label_ids(tokenizer,[label])[label]
    kw=dict(return_dict=False,enable_thinking=False)
    prompt=list(tokenizer.apply_chat_template(messages,add_generation_prompt=True,**kw))
    full=list(tokenizer.apply_chat_template(messages+[{'role':'assistant','content':label}],**kw))
    if full[:len(prompt)]!=prompt:raise ValueError('Training prefix differs from evaluation prompt')
    if len(full)>max_length or len(prompt)>=max_length:raise ValueError('Context too large; truncation forbidden')
    if full[len(prompt):len(prompt)+1]!=[token]:raise ValueError('Label is not a single token at completion boundary')
    return dict(prompt_tokens=prompt,full_tokens=full,prompt_length=len(prompt))


def training_item(tokenized):
    """Return only prompt plus selected label, with its original token position."""
    n=tokenized['prompt_length']
    return tokenized['full_tokens'][:n+1],n


def choose_checkpoint(results):
    if len(results)!=2 or {r['step'] for r in results}!={64,128} or any(r['split']!='validation' for r in results):
        raise ValueError('Selection requires validation results for exactly steps 64 and 128')
    return min(results,key=lambda r:(r['summary']['protection_misses'],-r['summary']['supported_correct'],
                                      -r['summary']['decision_correct'],r['step']))


def summarize(rows):
    n=len(rows);lat=sorted(r['latency_seconds'] for r in rows if r.get('latency_seconds') is not None)
    return dict(count=n,decision_correct=sum(r['decision_correct'] for r in rows),
                supported_correct=sum(r['supported_reason'] for r in rows),
                protection_misses=sum(r['protection_miss'] for r in rows),
                unavailable=sum(r.get('error')=='unavailable' for r in rows),
                classes={s:dict(count=sum(r['expected_status']==s for r in rows),
                                correct=sum(r['expected_status']==s and r['decision_correct'] for r in rows))
                         for s in ('hold','adjust','escalate')},
                median_seconds=statistics.median(lat) if lat else None,
                p95_seconds=lat[max(0,math.ceil(.95*len(lat))-1)] if lat else None)


def readiness(candidate,base):
    n=candidate['count'];holds=candidate['classes']['hold']
    checks=dict(no_protection_misses=candidate['protection_misses']==0,
                status_target=n>0 and candidate['decision_correct']/n>=.9,
                supported_reason=n>0 and candidate['supported_correct']/n>=.9,
                holds=holds['count']>0 and holds['correct']/holds['count']>=.9,
                improvement=candidate['decision_correct']>=base['decision_correct']+4,
                complete=candidate['unavailable']==0 and base['unavailable']==0 and n==base['count'])
    for key in ('median_seconds','p95_seconds'):
        checks[key]=candidate[key] is not None and base[key] is not None and candidate[key]<=1.1*base[key]
    return dict(ready=all(checks.values()),checks=checks,disposition='offline/shadow research; never automatic actuation')


def source_hashes():
    # Include every production Python dependency, experiment CLI, and package/SOP data.
    paths=set()
    for folder in ('training','v2','scripts'):
        paths.update((SOURCE_ROOT/folder).rglob('*.py'))
    for folder in ('process_packages','config'):
        if (SOURCE_ROOT/folder).exists():paths.update(p for p in (SOURCE_ROOT/folder).rglob('*') if p.is_file())
    paths.update((SOURCE_ROOT/'docs/superpowers/specs').glob('2026-10-31-local-typed-adaptation.md'))
    return {str(p.relative_to(SOURCE_ROOT)):sha(p) for p in sorted(paths) if '__pycache__' not in p.parts}


def binding(root,model):
    model=Path(model).resolve()
    if model!=PINNED_MODEL.resolve() or not model.is_dir():raise ValueError('Only pinned local snapshot is permitted')
    versions={name:importlib.metadata.version(name) for name in ('mlx','mlx-lm','transformers','numpy')}
    return dict(source=source_hashes(),dataset=verify_dataset(root/'cases'),
                files={str(p.relative_to(root)):sha(p) for folder in ('cases','loader') for p in sorted((root/folder).glob('*')) if p.is_file()},
                model_path=str(model),model={str(p.relative_to(model)):sha(p) for p in sorted(model.rglob('*')) if p.is_file()},
                versions=versions | {'python':platform.python_version()},settings=SETTINGS,
                frozen={f'{s}-frozen.json':sha(root/f'{s}-frozen.json') for s in ('train','validation','test')})


def frozen_cases(root,split):
    return [json.loads(line) for line in (root/'cases'/f'{split}.jsonl').read_text().splitlines()]


def prepare(root,model):
    root.mkdir(parents=True,exist_ok=False)
    freeze_dataset(root/'cases')
    # Materialize inputs, menus and labels before any model calls. No test file in loader.
    for split in ('train','validation','test'):
        cases=frozen_cases(root,split)
        for c in cases:
            c['messages']=messages_for(c['context']);c['options']=make_options(c['context'])
            labels=[k for k,v in c['options'].items() if v['reason_code']==c['expected']['reason_code'] and
                    (v['proposal']['status']!='adjust' or v['proposal']['target'] in c['expected']['acceptable_targets'])]
            if not labels:raise ValueError('No supervised label')
            # Prefer the interior recovery target if supplied; tie is stable label order.
            lo,hi=c['context']['package']['objective']
            c['label']=next((k for k in labels if c['options'][k]['proposal']['status']=='adjust' and lo<c['options'][k]['proposal']['target']<hi),labels[0])
        write_new(root/f'{split}-frozen.json',cases)
        if split!='test':
            folder=root/'loader';folder.mkdir(exist_ok=True)
            with (folder/('valid.jsonl' if split=='validation' else 'train.jsonl')).open('x') as stream:
                for c in cases:stream.write(json.dumps({'messages':c['messages']+[{'role':'assistant','content':c['label']}]})+'\n')
    write_new(root/'manifest.json',binding(root,model))


def checked_binding(root,model):
    current=binding(root,model)
    # Frozen inputs are bound too, not just the original cases.
    current['frozen']={f'{s}-frozen.json':sha(root/f'{s}-frozen.json') for s in ('train','validation','test')}
    manifest=read(root/'manifest.json')
    verify_binding(manifest,current)
    return current


def evaluate(root,model_path,split,name,adapter=None):
    """One cold model load, separate warm-up, one ordered pass, no retries."""
    from mlx_lm import load
    import mlx.core as mx
    destination=root/f'{name}-{split}.json'
    # Claim before GPU calls; failed runs cannot silently be repeated.
    write_new(root/f'{name}-{split}.started.json',{'binding':fingerprint(checked_binding(root,model_path))})
    evaluation_start=time.perf_counter()
    start=time.perf_counter()
    model,tokenizer=load(str(model_path),adapter_path=str(adapter) if adapter else None)
    mx.eval(model.parameters());load_seconds=time.perf_counter()-start
    cases=read(root/f'{split}-frozen.json')
    encoded=[]
    for c in cases:
        verify_binding(c['options'],make_options(c['context']))
        verify_binding(c['messages'],messages_for(c['context']))
        t=tokenize_example(tokenizer,c['messages'],c['label'])
        encoded.append((t['prompt_tokens'],label_ids(tokenizer,c['options'])))
    def forward(tokens,ids):
        start=time.perf_counter();logits=model(mx.array([tokens]))[0,-1,:]
        values=mx.take(logits,mx.array(list(ids.values())));mx.eval(values)
        return values.tolist(),time.perf_counter()-start
    # Same first captured prompt for each compared model; discarded for scoring.
    _,warmup=forward(*encoded[0]);rows=[]
    with (root/f'{name}-{split}.rows.jsonl').open('x') as log:
        for c,(tokens,ids) in zip(cases,encoded):
            fatal=None
            try:
                try:
                    values,elapsed=forward(tokens,ids)
                except RuntimeError as error:
                    # A forward RuntimeError originates in the model/backend, including
                    # MLX Metal resource-limit/command-buffer failures. Do not guess
                    # recoverability from message text or continue using that backend.
                    fatal=error
                    raise
                if not all(math.isfinite(v) for v in values):raise ValueError('Nonfinite choice logits')
                peak=max(values);weights=[math.exp(v-peak) for v in values];den=sum(weights)
                label=list(ids)[max(range(len(values)),key=values.__getitem__)]
                proposal=decode_choice(c['context'],label)
                row=dict(id=c['id'],expected_status=c['expected']['status'],expected_reason=c['expected']['reason_code'],label=label,
                         logits=dict(zip(ids,values)),relative_probabilities=dict(zip(ids,[x/den for x in weights])),
                         proposal=proposal.model_dump(),attribution='label: model logits; proposal/rationale: code-authored',
                         latency_seconds=elapsed,prefill_tokens=len(tokens),generated_tokens=0,scored_labels=len(ids),**score(c,label,proposal))
            except Exception as error:
                if isinstance(error,MemoryError):fatal=error
                row=dict(id=c['id'],expected_status=c['expected']['status'],expected_reason=c['expected']['reason_code'],label=None,proposal=None,
                         latency_seconds=None,prefill_tokens=len(tokens),generated_tokens=0,
                         decision_correct=False,supported_reason=False,protection_miss=c['expected']['protection_required'],
                         error='unavailable',detail=f'{type(error).__name__}: {error}')
            rows.append(row);log.write(json.dumps(row,allow_nan=False)+'\n');log.flush()
            if fatal is not None:
                write_new(root/f'{name}-{split}.failed.json',dict(
                    split=split,name=name,detail=row['detail'],attempted=len(rows),
                    total=len(cases),unattempted=len(cases)-len(rows),summary=summarize(rows)))
                raise fatal
    result=dict(split=split,name=name,load_seconds=load_seconds,warmup_seconds=warmup,
                wall_seconds=time.perf_counter()-evaluation_start,
                summary=summarize(rows),rows=rows,binding=fingerprint(checked_binding(root,model_path)))
    write_new(destination,result)
    return result


def train_once(root,model_path):
    import numpy as np
    import mlx.core as mx
    from mlx_lm import load
    import mlx.nn as nn
    import mlx.optimizers as optim
    from mlx_lm.tuner.trainer import TrainingArgs,train
    from mlx_lm.tuner.utils import linear_to_lora_layers
    from mlx_lm.tuner.datasets import ChatDataset,CacheDataset
    if not (root/'base-validation.json').exists():raise ValueError('Baseline validation required before training')
    write_new(root/'training.started.json',{'binding':fingerprint(checked_binding(root,model_path))})
    np.random.seed(42);mx.random.seed(42)
    model,tokenizer=load(str(model_path))
    class LabelDataset(ChatDataset):
        def process(self,row):
            messages=row['messages'];t=tokenize_example(self.tokenizer,messages[:-1],messages[-1]['content'])
            return training_item(t)
    data=[]
    for name in ('train','valid'):
        rows=[json.loads(x) for x in (root/'loader'/f'{name}.jsonl').read_text().splitlines()]
        dataset=LabelDataset(rows,tokenizer,mask_prompt=True)
        for row in rows:dataset.process(row)  # Reject overlength before trainer can truncate.
        data.append(dataset)
    model.freeze()
    lora_parameters={'rank':8,'dropout':0.0,'scale':20.0}
    linear_to_lora_layers(model,4,lora_parameters)
    adapters=root/'adapters';adapters.mkdir(exist_ok=False)
    write_new(adapters/'adapter_config.json',dict(fine_tune_type='lora',num_layers=4,lora_parameters=lora_parameters))
    def label_loss(model,batch,lengths):
        # Padding and assistant terminators contribute no loss. One selected label per row.
        logits=model(batch[:,:-1])
        rows=mx.arange(batch.shape[0]);positions=lengths[:,0]
        ce=nn.losses.cross_entropy(logits[rows,positions-1,:],batch[rows,positions])
        return ce.mean(),mx.array(batch.shape[0])
    args=TrainingArgs(batch_size=1,iters=128,val_batches=-1,steps_per_report=8,
                      steps_per_eval=64,steps_per_save=64,adapter_file=adapters/'adapters.safetensors',
                      max_seq_length=4096,grad_checkpoint=True,grad_accumulation_steps=1)
    train(model=model,args=args,optimizer=optim.Adam(learning_rate=5e-5),
          train_dataset=CacheDataset(data[0]),val_dataset=CacheDataset(data[1]),loss=label_loss)
    records={}
    for step in (64,128):
        checkpoint=root/'adapters'/f'{step:07d}_adapters.safetensors'
        if not checkpoint.exists():raise ValueError(f'Missing checkpoint {checkpoint}')
        records[str(step)]=sha(checkpoint)
    write_new(root/'training.complete.json',{'checkpoints':records,'adapter_config_sha256':sha(adapters/'adapter_config.json'),
                'binding':fingerprint(checked_binding(root,model_path))})


def verify_training_completion(root,current):
    complete=read(root/'training.complete.json')
    verify_binding(complete['binding'],fingerprint(current))
    verify_binding(complete['adapter_config_sha256'],sha(root/'adapters'/'adapter_config.json'))
    for step in (64,128):
        verify_binding(complete['checkpoints'][str(step)],sha(root/'adapters'/f'{step:07d}_adapters.safetensors'))
    return complete


def verified_report_inputs(root,current):
    bound=fingerprint(current)
    selection=read(root/'selection.json');claim=read(root/'test.started.json')
    complete=read(root/'test.complete.json')
    verify_binding(selection['binding'],bound)
    verify_binding(claim['binding'],bound)
    verify_binding(complete['binding'],bound)
    selection_hash=sha(root/'selection.json')
    verify_binding(claim['selection_sha256'],selection_hash)
    verify_binding(complete['selection_sha256'],selection_hash)
    expected_ids=[c['id'] for c in read(root/'test-frozen.json')]
    if len(set(expected_ids))!=len(expected_ids):raise ValueError('Duplicate frozen test IDs')
    expected_files={f'{name}-test.json' for name in ('base','selected')}
    if set(complete['results'])!=expected_files:raise ValueError('Incomplete test result identities')
    results=[]
    for name in ('base','selected'):
        path=root/f'{name}-test.json'
        verify_binding(complete['results'][path.name],sha(path))
        result=read(path)
        verify_binding(result['binding'],bound)
        verify_binding((result['split'],result['name']),('test',name))
        verify_binding([row['id'] for row in result['rows']],expected_ids)
        summary=summarize(result['rows'])
        verify_binding(result['summary'],summary)
        result['summary']=summary
        results.append(result)
    return results,selection,claim,complete


def checkpoint_dir(root,step,current):
    import shutil
    complete=verify_training_completion(root,current);source=root/'adapters'/f'{step:07d}_adapters.safetensors'
    verify_binding(complete['checkpoints'][str(step)],sha(source))
    folder=root/f'checkpoint-{step}';folder.mkdir(exist_ok=False)
    shutil.copyfile(source,folder/'adapters.safetensors')
    shutil.copyfile(root/'adapters'/'adapter_config.json',folder/'adapter_config.json')
    return folder


def run_stage(stage,root,model):
    root=Path(root).resolve();model=Path(model).resolve()
    if stage=='prepare':
        prepare(root,model)
        return
    current=checked_binding(root,model)
    if stage=='baseline':evaluate(root,model,'validation','base')
    elif stage=='train':train_once(root,model)
    elif stage=='validate':
        verify_training_completion(root,current)
        write_new(root/'validation.started.json',{'binding':fingerprint(current)})
        results=[]
        for step in (64,128):
            adapter=checkpoint_dir(root,step,current)
            r=evaluate(root,model,'validation',f'step-{step}',adapter);r['step']=step;results.append(r)
        chosen=choose_checkpoint(results);step=chosen['step'];adapter=root/f'checkpoint-{step}'
        write_new(root/'selection.json',dict(step=step,binding=fingerprint(current),validation={str(r['step']):sha(root/f"step-{r['step']}-validation.json") for r in results},
                  adapter={p.name:sha(p) for p in sorted(adapter.iterdir()) if p.is_file()}))
    elif stage=='test':
        selection=read(root/'selection.json');verify_binding(selection['binding'],fingerprint(current))
        for step,expected in selection['validation'].items():verify_binding(expected,sha(root/f'step-{step}-validation.json'))
        adapter=root/f"checkpoint-{selection['step']}"
        verify_binding(selection['adapter'],{p.name:sha(p) for p in sorted(adapter.iterdir()) if p.is_file()})
        write_new(root/'test.started.json',{'selection_sha256':sha(root/'selection.json'),'binding':fingerprint(current)})
        evaluate(root,model,'test','base');evaluate(root,model,'test','selected',adapter)
        verify_binding(fingerprint(checked_binding(root,model)),fingerprint(current))
        claim=read(root/'test.started.json')
        verify_binding(claim['selection_sha256'],sha(root/'selection.json'))
        write_new(root/'test.complete.json',dict(binding=fingerprint(current),selection_sha256=claim['selection_sha256'],
                  results={f'{name}-test.json':sha(root/f'{name}-test.json') for name in ('base','selected')}))
    elif stage=='report':
        (base,candidate),selection,claim,complete=verified_report_inputs(root,current)
        write_new(root/'summary.json',dict(base=base['summary'],candidate=candidate['summary'],readiness=readiness(candidate['summary'],base['summary']),
                  selection=selection,test_claim=claim,test_completion=complete))
        write_new(root/'failures.json',{name:[r for r in result['rows'] if not r['supported_reason']] for name,result in [('base',base),('selected',candidate)]})
    else:raise ValueError('Unknown stage')
