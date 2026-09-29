"""Previous unapproved adapter on the fresh pilot, with identical assisted prompts."""
import fcntl
import json
import time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_water_context_study import verify, lines, pilot_rows, payload_for, token_prompt, sha, freeze, append, write, summarize, model_path
from scripts.water_context_study import OUT
from scripts.water_alarm_benchmark import score


def main():
    with (OUT/'local.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        verify()
        old=ROOT/'artifacts/posttraining/water-alarms-v2'
        acceptance=json.loads((old/'acceptance.json').read_text())
        adapter=old/acceptance['candidate'];identity=acceptance['test']['identity']
        if sha(adapter/'adapters.safetensors')!=identity['adapter_sha256'] or sha(adapter/'adapter_config.json')!=identity['adapter_config_sha256']:
            raise ValueError('Previous adapter changed')
        rows=pilot_rows(lines(OUT/'valid.cases.jsonl'));path=OUT/'local-assisted-previous.jsonl'
        sidecar=OUT/'local-assisted-previous.identity.json'
        if path.exists() and not sidecar.exists():raise ValueError('Unbound result file')
        freeze(sidecar,{'manifest_sha256':sha(OUT/'manifest.json'),'pilot_sha256':sha(OUT/'pilot.json'),
            'adapter_sha256':sha(adapter/'adapters.safetensors'),'adapter_config_sha256':sha(adapter/'adapter_config.json'),
            'script_sha256':sha(__file__),'mode':'assisted','max_tokens':256,'temperature':0,'thinking':False})
        records=lines(path) if path.exists() else [];seen={r['id'] for r in records};by_id={r['id']:r for r in rows}
        if len(seen)!=len(records) or not seen<=by_id.keys():raise ValueError('Invalid cached IDs')
        for r in records:
            if r['score']!=score(r['decoded'],by_id[r['id']]):raise ValueError('Changed cached score')
        pending=[r for r in rows if r['id'] not in seen]
        if pending:
            from mlx_lm import load,generate
            from mlx_lm.sample_utils import make_sampler
            model,tokenizer=load(model_path(),adapter_path=str(adapter))
        for row in pending:
            payload=payload_for(row,'assisted');prompt=token_prompt(tokenizer,payload);start=time.perf_counter()
            output=generate(model,tokenizer,prompt=prompt,max_tokens=256,sampler=make_sampler(temp=0),verbose=False)
            record={'id':row['id'],'kind':row['kind'],'input':payload,'output':output,'decoded':output,
                'score':score(output,row),'latency_seconds':time.perf_counter()-start,'input_tokens':len(prompt),'output_tokens':len(tokenizer.encode(output))}
            append(path,record);records.append(record)
            print('previous-adapter',len(records),record['score']['correct'],flush=True)
        verify();write(OUT/'local-assisted-previous-summary.json',summarize(records))


if __name__=='__main__':main()
