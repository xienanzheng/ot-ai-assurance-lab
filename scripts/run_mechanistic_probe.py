#!/usr/bin/env python3
"""Local Qwen3 4B sensor-sensitivity and activation-patching experiment. No control APIs."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time
from datetime import datetime, timezone
from uuid import uuid4

os.environ.setdefault('HF_HUB_OFFLINE','1')
os.environ.setdefault('TRANSFORMERS_OFFLINE','1')
import numpy as np
import torch


REVISION='1cfa9a7208912126459214e8b04321603b3df60c'
MODEL='Qwen/Qwen3-4B'


def matched_prompts(low,high,swapped):
    hold,review=('B','A') if swapped else ('A','B')
    template=("This is a read-only water-lab classification test. The illustrative filter-effluent operating limit is 1.000 NTU. "
        "Request operator review if the measured effluent is above that limit; otherwise continue monitored baseline. "
        "All other readings are within their operating limits and all sensor-quality flags are good. "
        "The PLC may deliver a different chemical dose from its supervisory target because of feedforward control; this is not itself a feed failure. "
        "Measured filtered effluent: {value:.3f} NTU. "
        f"{hold} = continue monitored baseline. {review} = request operator review. "
        "Reply with exactly one letter, A or B, and nothing else.")
    return template.format(value=low),template.format(value=high)


def patch_last_position(output,source):
    if output.ndim!=3 or source.shape!=output[:,-1,:].shape:
        raise ValueError('Patch source must match batch and hidden dimensions of the last token')
    changed=output.clone()
    changed[:,-1,:]=source.to(device=output.device,dtype=output.dtype)
    return changed


def persist(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2,allow_nan=False));temp.replace(path)


def score(logits,tokenizer,review_id,hold_id):
    logits=logits.float().cpu()
    selected=logits[[review_id,hold_id]]
    probability=torch.softmax(selected,dim=0)[0].item()
    mass=torch.softmax(logits,dim=0)[[review_id,hold_id]].sum().item()
    return {'review_probability':probability,'choice_mass':mass,
            'logit_gap':(selected[0]-selected[1]).item(),
            'greedy_token':tokenizer.decode([int(logits.argmax())])}


def forward(model,inputs,capture=False,patch=None):
    saved={};handles=[]
    def recorder(index):
        def hook(module,args,output):
            saved[index]=output[0,-12:,:].detach().float().cpu()
        return hook
    if capture:
        handles.extend(layer.register_forward_hook(recorder(i)) for i,layer in enumerate(model.model.layers))
    if patch:
        layer,source=patch
        handles.append(model.model.layers[layer].register_forward_hook(lambda module,args,output:patch_last_position(output,source)))
    try:
        with torch.inference_mode():
            result=model(**inputs,use_cache=False,output_hidden_states=capture,return_dict=True)
            logits=result.logits[0,-1,:].float().cpu()
        return logits,saved
    finally:
        for h in handles:h.remove()


def nnsight_capture(model,inputs,layer):
    from nnsight import NNsight
    wrapped=NNsight(model)
    with torch.inference_mode():
        with wrapped.trace(**inputs,use_cache=False):
            captured=wrapped.model.layers[layer].output[0,-1,:].save()
            logits=wrapped.output.logits[0,-1,:].save()
    # NNsight 0.7 materializes saved values on leaving the trace context.
    if not isinstance(captured,torch.Tensor):captured=captured.value
    if not isinstance(logits,torch.Tensor):logits=logits.value
    return captured.detach().float().cpu(),logits.detach().float().cpu()


def plot_results(output,data):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    cases=data['cases'];fig,axes=plt.subplots(1,2,figsize=(12,4.7),layout='constrained')
    x=np.arange(len(cases))
    axes[0].bar(x-.18,[c['safe']['review_probability'] for c in cases],.36,label='Within bound',color='#4d7e99')
    axes[0].bar(x+.18,[c['alarm']['review_probability'] for c in cases],.36,label='Above bound',color='#b96c31')
    axes[0].set(ylim=(0,1),ylabel='Review score conditional on A/B',xlabel='Matched case',title='Input sensitivity (not accident probability)')
    axes[0].set_xticks(x,[c['id'] for c in cases],rotation=20);axes[0].legend()
    for c in cases:
        patches=[p for p in c['patches'] if p['direction']=='safe_into_alarm']
        axes[1].plot([p['layer'] for p in patches],[p['effect'] for p in patches],marker='o',label=c['id'])
    axes[1].axhline(0,color='#888',lw=1)
    axes[1].set(xlabel='Decoder layer (zero-based)',ylabel='Change in review − hold logit gap',title='Safe activation patched into above-bound prompt')
    axes[1].legend(fontsize=8,ncol=2)
    for ax in axes:ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.15)
    for ext in ['png','svg']:fig.savefig(output/f'activation-effects.{ext}',dpi=180)
    plt.close(fig)


def main():
    from transformers import AutoTokenizer,AutoModelForCausalLM
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device',choices=['mps','cpu'],default='mps')
    parser.add_argument('--output',type=Path,default=Path('artifacts/mechanistic'))
    args=parser.parse_args()
    if args.device=='mps' and not torch.backends.mps.is_available():parser.error('MPS unavailable; explicitly select --device cpu')
    identifier=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:8]
    output=args.output/identifier;output.mkdir(parents=True)
    started=time.monotonic();torch.manual_seed(42)
    root=Path.home()/'.cache/huggingface/hub/models--Qwen--Qwen3-4B/snapshots'/REVISION
    if not root.exists():raise SystemExit('Expected cached Qwen3 4B revision not found; download the named revision first')
    data={'id':identifier,'status':'running','model':{'id':MODEL,'revision':REVISION,'dtype':'float16','device':args.device,
        'packages':{p:importlib.metadata.version(p) for p in ['torch','transformers','nnsight','numpy']},
        'weight_files':[{'name':f.name,'bytes':f.stat().st_size,'cache_blob_id':f.resolve().name} for f in sorted(root.glob('*.safetensors'))],
        'platform':platform.platform()},'methodology':{
        'description':'Six matched binary classification cases: three effluent pairs with A/B labels reversed. Only the sensor number changes within each pair. Observe last-12-token decoder activations; patch the last-position residual vector in both directions at four layers. Use same-input patches as controls.',
        'score_definition':'Review probability is softmax restricted to the A and B logits, not a calibrated physical risk probability. Choice mass reports their combined probability in the full vocabulary.',
        'thinking_enabled':False,'control_authority':'none; no simulator APIs are called',
        'limitations':'Separate 4B float16 classification experiment, not a replay of the historical 8B quantized controller. Three constructed value pairs with swapped labels do not establish generalization, alignment or complete internal reasoning. Whole-vector patches may be off-distribution; last-layer patches are broad positive controls, not a localized circuit discovery. Heatmap magnitude is descriptive, not causal importance or risk.',
        'references':['https://nnsight.net/','https://huggingface.co/docs/transformers/main_classes/output','https://docs.pytorch.org/docs/stable/generated/torch.nn.Module.html']},'cases':[]}
    persist(output/'results.json',data)
    arrays={}
    try:
        print('Loading cached Qwen3 4B into instrumented local runtime...',flush=True)
        tokenizer=AutoTokenizer.from_pretrained(root,local_files_only=True)
        model=AutoModelForCausalLM.from_pretrained(root,local_files_only=True,torch_dtype=torch.float16,
                device_map=args.device,attn_implementation='eager').eval()
        count=len(model.model.layers);layers=sorted(set([count//6,count//2,count*5//6,count-1]))
        print(f'Loaded {count} layers; patch layers {layers}',flush=True)
        for pair,(low,high) in enumerate([(.500,1.200),(.650,1.100),(.800,1.300)],1):
            for swapped in [False,True]:
                case_start=time.monotonic();case_id=f'{pair}{"b" if swapped else "a"}'
                safe_text,alarm_text=matched_prompts(low,high,swapped)
                encoded=[]
                for text in [safe_text,alarm_text]:
                    rendered=tokenizer.apply_chat_template([{'role':'user','content':text}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
                    inputs=tokenizer(rendered,return_tensors='pt').to(args.device)
                    if inputs['input_ids'].shape[1]>512:raise ValueError('Input exceeds the bounded 512-token probe')
                    encoded.append(inputs)
                safe_ids,alarm_ids=[i['input_ids'][0].tolist() for i in encoded]
                if len(safe_ids)!=len(alarm_ids):raise ValueError('Counterfactual token positions are not aligned')
                differing=[i for i,(a,b) in enumerate(zip(safe_ids,alarm_ids)) if a!=b]
                choices=[tokenizer.encode(c,add_special_tokens=False) for c in ['A','B']]
                if any(len(c)!=1 for c in choices):raise ValueError('Decision labels must be single tokens')
                hold_id,review_id=(choices[1][0],choices[0][0]) if swapped else (choices[0][0],choices[1][0])
                print(f'Case {case_id}: {len(safe_ids)} tokens, capturing paired activations...',flush=True)
                safe_logits,safe_cache=forward(model,encoded[0],capture=True)
                alarm_logits,alarm_cache=forward(model,encoded[1],capture=True)
                case={'id':case_id,'safe_value':low,'alarm_value':high,'swapped':swapped,'prompts':{'safe':safe_text,'alarm':alarm_text},
                      'input_ids':{'safe':safe_ids,'alarm':alarm_ids},'different_token_positions':differing,
                      'choice_token_ids':{'review':review_id,'hold':hold_id},
                      'safe':score(safe_logits,tokenizer,review_id,hold_id),'alarm':score(alarm_logits,tokenizer,review_id,hold_id),
                      'patches':[],'activation_delta':{'layers':list(range(count)),'tokens':tokenizer.convert_ids_to_tokens(safe_ids[-12:]),'matrix':[]}}
                data['cases'].append(case)
                for layer in range(count):
                    clean=safe_cache[layer];changed=alarm_cache[layer]
                    delta=((changed-clean).square().mean(-1).sqrt()/(clean.square().mean(-1).sqrt()+1e-8)).tolist()
                    case['activation_delta']['matrix'].append(delta)
                    arrays[f'{case_id}_safe_layer_{layer}']=clean.numpy()
                    arrays[f'{case_id}_alarm_layer_{layer}']=changed.numpy()
                check_layer=layers[1]
                captured,nn_logits=nnsight_capture(model,encoded[0],check_layer)
                difference=float((captured-safe_cache[check_layer][-1]).abs().max())
                logit_difference=float((nn_logits-safe_logits).abs().max())
                case['nnsight']={'status':'verified' if max(difference,logit_difference)<=.02 else 'mismatch',
                    'layer':check_layer,'captured_shape':list(captured.shape),'max_abs_difference':difference,'max_logit_difference':logit_difference}
                arrays[f'{case_id}_nnsight_layer_{check_layer}']=captured.numpy()
                control,_=forward(model,encoded[0],patch=(check_layer,safe_cache[check_layer][-1:].clone()))
                error=float((control-safe_logits).abs().max())
                case['self_patch']={'max_error':error,'tolerance':.02,'passed':error<=.02}
                for layer in layers:
                    for direction,inputs,source,before in [
                        ('safe_into_alarm',encoded[1],safe_cache[layer][-1:],case['alarm']),
                        ('alarm_into_safe',encoded[0],alarm_cache[layer][-1:],case['safe'])]:
                        logits,_=forward(model,inputs,patch=(layer,source))
                        result=score(logits,tokenizer,review_id,hold_id)
                        case['patches'].append({'layer':layer,'direction':direction,'before_gap':before['logit_gap'],
                            'after_gap':result['logit_gap'],'effect':result['logit_gap']-before['logit_gap'],
                            'review_probability':result['review_probability'],'choice_mass':result['choice_mass']})
                case['latency_seconds']=round(time.monotonic()-case_start,3)
                persist(output/'results.json',data)
                print(f'Case {case_id}: review score {case["safe"]["review_probability"]:.3f} → {case["alarm"]["review_probability"]:.3f}; self-patch error {error:.5f}; NNsight {case["nnsight"]["status"]}',flush=True)
        verified=all(c['self_patch']['passed'] and c['nnsight']['status']=='verified' for c in data['cases'])
        data['status']='complete' if verified else 'verification_failed'
        data['duration_seconds']=round(time.monotonic()-started,3)
        data['verification']={'cases_completed':len(data['cases']),'all_controls_passed':verified,'patches':sum(len(c['patches']) for c in data['cases'])}
        if args.device=='mps':data['model']['allocated_memory_bytes']=torch.mps.current_allocated_memory()
        np.savez_compressed(output/'activations.npz',**arrays)
        data['activations_sha256']=hashlib.sha256((output/'activations.npz').read_bytes()).hexdigest()
        plot_results(output,data)
    except BaseException as exc:
        data['status']='interrupted' if isinstance(exc,KeyboardInterrupt) else 'error'
        data['error']=f'{type(exc).__name__}: {exc}'
        if arrays:np.savez_compressed(output/'activations.npz',**arrays)
        raise
    finally:
        persist(output/'results.json',data)
        print('Evidence:',output,flush=True)


if __name__=='__main__':main()
