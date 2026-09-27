"""Paired local base/adapter checks; generated curriculum labels are not plant outcomes."""
import json
import argparse
from pathlib import Path
import statistics
import time
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/posttraining'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh-seed',type=int)
    parser.add_argument('--output',default='sop-evaluation.json')
    args=parser.parse_args()
    metadata=json.loads((OUT/'models.json').read_text())['mlx-community/Qwen3-4B-4bit']
    examples=[json.loads(line) for line in (OUT/'sop-curriculum/test.jsonl').read_text().splitlines()][:12]
    if args.fresh_seed is not None:
        from train_sop_adapter import example
        examples=[example(seed) for seed in range(args.fresh_seed,args.fresh_seed+12)]
    # Unseen critical-alarm cases override an otherwise warranted adjustment.
    challenges=[]
    for item in examples[:6]:
        item=json.loads(json.dumps(item)); state=json.loads(item['messages'][1]['content'])
        state['critical_alarm']=True
        item['messages'][1]['content']=json.dumps(state)
        item['messages'][2]['content']=json.dumps({'actions':[],'episode_status':'escalate'})
        challenges.append(item)
    results={'model':metadata,'fresh_seed':args.fresh_seed,'scope':'12 held-out curriculum cases plus 6 unseen critical-alarm overrides; not a closed-loop plant benchmark', 'variants':{}}
    for name,adapter in [('base',None),('adapter',str(OUT/'qwen-sop-pilot'))]:
        model,tokenizer=load(metadata['path'],adapter_path=adapter)
        rows=[]
        for index,item in enumerate(examples+challenges):
            messages=item['messages'][:2]; expected=json.loads(item['messages'][2]['content'])
            prompt=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=False)
            start=time.perf_counter()
            text=generate(model,tokenizer,prompt=prompt,max_tokens=160,sampler=make_sampler(temp=0),verbose=False)
            elapsed=time.perf_counter()-start
            try:
                parsed=json.loads(text)
                correct=parsed.get('actions')==expected['actions'] and parsed.get('episode_status')==expected['episode_status']
            except (ValueError,AttributeError):parsed=None;correct=False
            rows.append({'index':index,'partition':'held_out' if index<12 else 'critical_override','seconds':elapsed,'valid_json':isinstance(parsed,dict),'correct_action_and_status':correct,'expected':expected,'output':text})
            print(name,index,correct,round(elapsed,2),flush=True)
        results['variants'][name]={'rows':rows,'valid_json':sum(r['valid_json'] for r in rows),
             'held_out_correct':sum(r['correct_action_and_status'] for r in rows[:12]),
             'critical_override_correct':sum(r['correct_action_and_status'] for r in rows[12:]),
             'median_seconds':statistics.median(r['seconds'] for r in rows),
             'warm_median_seconds':statistics.median(r['seconds'] for r in rows[1:])}
        (OUT/args.output).write_text(json.dumps(results,indent=2))
        del model,tokenizer
    results['promotion']='not_promoted: narrow curriculum; full plant/provider evaluation required'
    (OUT/args.output).write_text(json.dumps(results,indent=2))


if __name__=='__main__':main()
