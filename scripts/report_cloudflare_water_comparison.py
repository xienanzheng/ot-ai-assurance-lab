"""Report paired validation results only after all hosted requests complete."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.compare_cloudflare_water import OUT,DATASET


def report():
    hosted=[json.loads(x) for x in (OUT/'responses.jsonl').read_text().splitlines()]
    cases={r['id']:r for r in (json.loads(x) for x in (DATASET/'valid.cases.jsonl').read_text().splitlines())}
    if len(hosted)!=400 or {r['id'] for r in hosted}!=cases.keys():raise ValueError('Full 400-case comparison not yet complete')
    models={'Untrained local Qwen3 4B':[json.loads(x) for x in (DATASET/'base-valid.jsonl').read_text().splitlines()],
            'Trained local Qwen3 4B':[json.loads(x) for x in (DATASET/'lr5e5-valid.jsonl').read_text().splitlines()],
            'Cloudflare Qwen3 30B-A3B':hosted}
    def rate(rows,key):return f"{sum(bool(r['score'][key]) for r in rows)}/{len(rows)} ({100*sum(bool(r['score'][key]) for r in rows)/len(rows):.1f}%)"
    lines=['# Cloudflare versus local Qwen: paired water comparison','',
      'Completed 400 validation cases through the Cloudflare Workers AI API. No plant commands or deployment changes were made.','',
      '| Metric | Untrained 4B | Trained 4B | Cloudflare 30B-A3B |','| --- | ---: | ---: | ---: |']
    for label,key,kind in [('Valid contract','valid',None),('Critical escalation, no actions','critical_ok','critical'),
                          ('Prerequisite failures','correct','prerequisite'),('Correct holds','correct','hold'),
                          ('Correct adjustments','correct','adjust'),('Correct noncritical decisions','correct','noncritical'),
                          ('Supported evidence/checks','assessment_supported',None),('Correct action/status overall','correct',None)]:
        values=[]
        for rows in models.values():
            filtered=rows if kind is None else [r for r in rows if (r['kind']!='critical' if kind=='noncritical' else r['kind']==kind)]
            values.append(rate(filtered,key))
        lines.append('| '+label+' | '+' | '.join(values)+' |')
    lines+=['','## What this comparison establishes','',
      'All models saw the same saved cases and exact serialized Qwen3 prompts, with temperature zero, a 256-token output budget, and the same unmodified scorer. Cloudflare used raw completion mode; responses were not repaired before scoring.',
      '', 'This compares the hosted model under matched benchmark settings. The live simulator uses a different wrapper: a schema instruction, JSON-constrained output and a 2,048-token allowance. These results do not directly measure that complete production configuration.',
      '', 'The trained adapter was selected using this validation set, so these results are development evidence, not an independent held-out confirmation of its advantage. Its separate locked test remains authoritative for the original acceptance protocol.',
      '', 'Cloudflare made four concurrent network requests; local correctness evaluation used batched MLX generation. Their timings are not a controlled inference-speed comparison. Model size, quantization and runtime also differ.',
      '', 'Critical scores require a valid complete contract as well as escalation without actions. A reference can be real but irrelevant: zero fabricated references does not imply a supported diagnosis.',
      '', '## Cases where results differ','']
    paired={name:{r['id']:r for r in rows} for name,rows in models.items()}
    local=paired['Trained local Qwen3 4B'];cloud=paired['Cloudflare Qwen3 30B-A3B']
    examples=[]
    for direction in ['trained_only','cloud_only']:
        ids=[identifier for identifier in cases if bool(local[identifier]['score']['correct'])!=bool(cloud[identifier]['score']['correct']) and bool(local[identifier]['score']['correct'])==(direction=='trained_only')][:3]
        for identifier in ids:
            case=cases[identifier]
            examples.append({'id':identifier,'kind':case['kind'],'direction':direction,'input':case['payload'],
              'expected':case['expected'],'trained':local[identifier],'cloudflare':cloud[identifier]})
            lines.append(f"- `{identifier}` ({case['kind']}): {'trained adapter' if direction=='trained_only' else 'Cloudflare model'} has the correct action/status; the other does not.")
    errors=sum('error' in r for r in hosted)
    retries=sum(bool(r.get('prior_transport_error')) for r in hosted)
    lines+=['',f'Unresolved API/transport errors: **{errors}**. Such rows are retained in the denominator. Authentication retries: **{retries}**; the original failed attempt is retained separately.',
       '', '## Reproduce','', '```sh', '.venv-posttrain/bin/python scripts/compare_cloudflare_water.py',
       '.venv-interpret/bin/python scripts/report_cloudflare_water_comparison.py','```','',
       'Credentials stay in the existing local Wrangler credential store or environment. Requests, raw responses, scores, manifest and paired examples are saved locally under `artifacts/posttraining/cloudflare-water-compare-v1/`.']
    (OUT/'paired-examples.json').write_text(json.dumps(examples,indent=2))
    destination=ROOT/'docs/CLOUDFLARE_QWEN_COMPARISON.md';destination.write_text('\n'.join(lines)+'\n')
    print(destination)


if __name__=='__main__':report()
