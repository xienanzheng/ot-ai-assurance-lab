import asyncio,json,time
from pathlib import Path
from v2.providers import OllamaProvider
from v2.contracts import Proposal
async def main():
 root=Path('artifacts/model-review-v1');path=root/'field-order-ablation.json'
 if path.exists():raise SystemExit('Preserve existing results')
 cases=json.loads((root/'cases.json').read_text())['cases'];rows=[]
 model=OllamaProvider('http://127.0.0.1:11434','qwen3:4b')
 for case in cases:
  if case['id'] not in ['water.high','water.low','water.critical','water.trip','cooling.high']:continue
  request=model.decision_request(case['context']);old=request['format'];new=dict(old)
  new['properties']={k:old['properties'][k] for k in ('rationale','evidence','operator_checks','status','target')}
  new['required']=['rationale','status']
  request['format']=new;request['messages'][0]['content']=request['messages'][0]['content'].replace(json.dumps(old),json.dumps(new))
  row={'id':case['id'],'request':request};start=time.monotonic()
  try:
   proposal,raw=await model.invoke_with_response(request,Proposal);row.update(proposal=proposal.model_dump(),raw_response=raw)
  except Exception as e:row['error']=str(e)
  row['seconds']=time.monotonic()-start;rows.append(row);path.write_text(json.dumps(rows,indent=2));print(json.dumps(row.get('proposal',row.get('error'))),flush=True)
asyncio.run(main())
