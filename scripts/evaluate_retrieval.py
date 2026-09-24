#!/usr/bin/env python3
"""Compare retrievers on explicit synthetic cases; no Qwen calls or actuation."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from time import perf_counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from services.supervisor.app.plant_knowledge import load_pack, digest, canonical, cosine, validate_vectors
from services.supervisor.app.retrieval_ranking import document_text, bm25, ranked, fuse_rankings, select_records


async def run(args):
    pack=load_pack(); docs=pack['records']
    remote=json.loads(args.openai.read_text())
    if remote['pack_sha256']!=digest(pack):
        raise SystemExit('Pack changed; OpenAI index is stale')
    cases=remote['queries']
    local_path=args.output/'embeddinggemma.json'
    args.output.mkdir(parents=True,exist_ok=True)
    if local_path.exists():
        local=json.loads(local_path.read_text())
        if local['pack_sha256']!=digest(pack):
            raise SystemExit('Local index is stale')
    else:
        inputs=['title: '+d['title']+' | text: '+document_text(d) for d in docs]+[
            'task: search result | query: '+c['query'] for c in cases]
        async with httpx.AsyncClient(timeout=120,trust_env=False) as client:
            response=await client.get('http://127.0.0.1:11434/api/tags');response.raise_for_status()
            manifest=next(m for m in response.json()['models'] if m['name']=='embeddinggemma:latest')
            started=perf_counter()
            response=await client.post('http://127.0.0.1:11434/api/embed',json={'model':'embeddinggemma','input':inputs,'truncate':False,'keep_alive':'30m'})
            response.raise_for_status()
        vectors=validate_vectors(response.json()['embeddings'],len(inputs))
        local={'pack_sha256':digest(pack),'model_digest':manifest['digest'],'vectors':vectors,'batch_seconds':round(perf_counter()-started,3)}
        local_path.write_text(json.dumps(local))
    methods={name:[] for name in ['legacy_keyword','bm25','local_dense','local_rrf','openai_dense','openai_rrf']}
    for ci, case in enumerate(cases):
        ids=[i for i,d in enumerate(docs) if d['domain']==case['domain']]
        eligible=[docs[i] for i in ids]
        def oldtokens(text):
            import re
            return set(re.findall(r'[a-z][a-z0-9]+',text.lower().replace('_',' ')))
        oldquery=oldtokens(canonical({'domain':case['domain'],'active_alarms':[case['query']]}))
        legacy=[len(oldquery & oldtokens(canonical(d)))/max(1,len(oldquery)) for d in eligible]
        lexical=bm25(eligible,case['query'])
        ld=[cosine(local['vectors'][i],local['vectors'][len(docs)+ci]) for i in ids]
        od=[cosine(remote['documents'][i]['embedding'],case['embedding']) for i in ids]
        variants={'legacy_keyword':legacy,'bm25':lexical,'local_dense':ld,'openai_dense':od,
            'local_rrf':fuse_rankings(ranked(lexical),ranked(ld),size=len(ids)),
            'openai_rrf':fuse_rankings(ranked(lexical),ranked(od),size=len(ids))}
        for method,scores in variants.items():
            ranking=[eligible[i]['id'] for i in ranked(scores)]
            position=ranking.index(case['expected_id'])+1 if case['expected_id'] in ranking else None
            methods[method].append({'query':case['query'],'expected':case['expected_id'],'ranking':ranking,
                'top1':position==1,'recall_at_2':position is not None and position<=2,'reciprocal_rank':1/position if position else 0})
    summary={name:{'top1':sum(x['top1'] for x in rows)/len(rows),
                   'recall_at_2':sum(x['recall_at_2'] for x in rows)/len(rows),
                   'mrr':sum(x['reciprocal_rank'] for x in rows)/len(rows)} for name,rows in methods.items()}
    report={'case_count':len(cases),'pack_sha256':digest(pack),'summary':summary,'cases':methods,
            'limitation':'Small developer-authored synthetic retrieval set. Not held-out operator validation or a test of control/recovery accuracy.'}
    (args.output/'evaluation.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--openai',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    asyncio.run(run(p.parse_args()))
