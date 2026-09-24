"""Bounded simulator knowledge retrieval. Context only; never control authority."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from time import perf_counter
from typing import Literal
from urllib.parse import urlparse

from .retrieval_ranking import document_text, search_text, bm25, ranked, fuse_rankings, select_records

import httpx
from pydantic import BaseModel, ConfigDict, Field

PACK_PATH = Path(__file__).with_name('plant_knowledge.json')


class KnowledgeRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    domain: Literal['water', 'grid', 'nuclear']
    title: str
    equipment: list[str]
    sensors: list[str]
    scenarios: list[str] = Field(min_length=1)
    modes: list[str] = Field(min_length=1)
    relationships: list[str]
    text: str = Field(min_length=10, max_length=1200)
    sources: list[str] = Field(min_length=1)


class KnowledgePack(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str
    scope: Literal['synthetic_simulator_only']
    records: list[KnowledgeRecord] = Field(min_length=1, max_length=100)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_pack():
    pack = KnowledgePack.model_validate_json(PACK_PATH.read_text()).model_dump()
    ids = [r['id'] for r in pack['records']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate knowledge IDs')
    return pack


def tokens(text):
    return set(re.findall(r'[a-z][a-z0-9]+', text.lower().replace('_', ' ')))


def query_for(domain, state):
    # Measurements remain in the original prompt. Retrieval uses alarm semantics,
    # quality, operating mode and recent context, not vector arithmetic on readings.
    value = {'scenario': state.get('scenario'), 'controller_mode': state.get('controller_mode'),
             'active_alarms': (state.get('active_alarms') or state.get('alarms') or [])[:8],
             'question': str(state.get('retrieval_question', ''))[:600]}
    sensors = state.get('sensors', {}) or {name: {'value': row[0], 'unit': row[1], 'quality': row[2]}
                for name, row in state.get('sensor_values', {}).items()}
    from shared.limits import LIMITS
    value['out_of_range'] = [name for name, sensor in sensors.items()
        if name in LIMITS and isinstance(sensor, dict) and type(sensor.get('value')) in (int, float)
        and not LIMITS[name][0] <= sensor['value'] <= LIMITS[name][1]]
    value['bad_quality'] = [name for name, sensor in sensors.items()
                            if isinstance(sensor, dict) and sensor.get('quality', 'good') != 'good']
    value['domain'] = domain
    # Never truncate serialized JSON mid-field or embed the full PLC/history dump.
    value['active_alarms'] = [str(a.get('message', a.get('code', '')))[:180] if isinstance(a, dict) else str(a)[:180] for a in value['active_alarms']]
    return canonical(value)


def validate_vectors(vectors, count):
    if not isinstance(vectors, list) or len(vectors) != count or not vectors:
        raise ValueError('Embedding count mismatch')
    dimension = len(vectors[0])
    if not 1 <= dimension <= 8192:
        raise ValueError('Invalid embedding dimension')
    for vector in vectors:
        if (len(vector) != dimension or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)
                or sum(x*x for x in vector) <= 0):
            raise ValueError('Invalid embedding vector')
    return vectors


def cosine(a, b):
    return sum(x*y for x, y in zip(a, b)) / math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))


async def embed_documents(documents, query):
    base = os.getenv('KNOWLEDGE_EMBED_URL', os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')).rstrip('/')
    if urlparse(base).hostname not in {'127.0.0.1', 'localhost', '::1', 'host.docker.internal'}:
        raise ValueError('Embedding endpoint must be local')
    model = os.getenv('KNOWLEDGE_EMBED_MODEL', 'embeddinggemma')
    cache_path = os.getenv('KNOWLEDGE_CACHE_PATH', '/tmp/ot-ai-knowledge.sqlite3')
    async with httpx.AsyncClient(timeout=float(os.getenv("KNOWLEDGE_EMBED_TIMEOUT", "30")), trust_env=False, follow_redirects=False) as client:
        response = await client.get(base+'/api/tags')
        response.raise_for_status()
        manifest = next(m for m in response.json()['models'] if m['name'] in {model, model+':latest'})
        model_digest = manifest['digest']
        texts = [document_text(d) if 'domain' in d else canonical(d) for d in documents]
        formatted_query = search_text(query) if query.startswith('{') else query
        if model.split(':')[0] == 'embeddinggemma':
            texts = ['title: '+d.get('title', 'none')+' | text: '+t for d,t in zip(documents,texts)]
            formatted_query = 'task: search result | query: '+formatted_query
        keys = [digest([model_digest, model, t]) for t in texts]
        # Cache only static documents. Live state/query embeddings never persist here.
        with sqlite3.connect(cache_path, timeout=2) as cache:
            cache.execute('CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector TEXT NOT NULL)')
            cached = [cache.execute('SELECT vector FROM embeddings WHERE key=?', (k,)).fetchone() for k in keys]
            vectors = [json.loads(row[0]) if row else None for row in cached]
            missing = [i for i, v in enumerate(vectors) if v is None]
            response = await client.post(base+'/api/embed', json={
                'model': model, 'input': [texts[i] for i in missing]+[formatted_query],
                'truncate': False, 'keep_alive': '30m'})
            response.raise_for_status()
            body = response.json()
            if body.get('model') not in {model, model+':latest'}:
                raise ValueError('Embedding model mismatch')
            new = validate_vectors(body['embeddings'], len(missing)+1)
            for index, vector in zip(missing, new[:-1]):
                vectors[index] = vector
                cache.execute('INSERT OR REPLACE INTO embeddings VALUES (?, ?)', (keys[index], canonical(vector)))
            validate_vectors(vectors+[new[-1]], len(vectors)+1)
            return vectors, new[-1], {'model': model, 'digest': model_digest,
                                    'cache_hits': len(documents)-len(missing)}


async def retrieve(domain, state, mode=None):
    started = perf_counter()
    mode = mode or os.getenv('PLANT_KNOWLEDGE_MODE', 'off')
    if mode not in {'off', 'lexical', 'hybrid'}:
        raise ValueError('Unknown plant knowledge mode')
    result = {'requested_mode': mode, 'method': mode, 'records': [], 'fallback': None,
              'authority': 'context_only', 'scope': 'synthetic_simulator_only',
              'state_sha256': digest(state)}
    if mode == 'off':
        return result
    try:
        pack = load_pack()
    except (OSError, ValueError):
        return {**result, 'fallback': 'invalid_pack'}
    result.update(pack_version=pack['version'], pack_sha256=digest(pack))
    scenario = state.get('scenario')
    operating_mode = state.get('controller_mode')
    equipment = set(state.get('equipment', {}))
    sensor_names = set(state.get('sensors', state.get('sensor_values', {})))
    docs = [d for d in pack['records'] if d['domain'] == domain
            and ('*' in d['scenarios'] or scenario in d['scenarios'])
            and ('*' in d['modes'] or operating_mode in d['modes'])
            and (not equipment and not sensor_names or bool(set(d['sensors']) & sensor_names)
                 or bool(set(d['equipment']) & equipment))]
    query = query_for(domain, state)
    result['query'] = query
    lexical = bm25(docs, search_text(query))
    scores = list(lexical)
    result['ranking_version'] = 'bm25-rrf-v2'
    result['method'] = 'lexical'
    if mode == 'hybrid' and docs:
        if os.getenv('HOSTED_MODE') == 'true':
            result['fallback'] = 'hosted_embeddings_unavailable'
        else:
            try:
                vectors, qvector, provenance = await embed_documents(docs, query)
                validate_vectors(vectors+[qvector], len(docs)+1)
                dense = [cosine(v, qvector) for v in vectors]
                scores = fuse_rankings(ranked(lexical), ranked(dense), size=len(docs))
                result['rankings'] = {'bm25':[docs[i]['id'] for i in ranked(lexical)],
                                      'dense':[docs[i]['id'] for i in ranked(dense)]}
                result.update(method='hybrid', embedding=provenance)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, StopIteration, RuntimeError, sqlite3.Error, OSError) as exc:
                result["embedding_error_type"] = type(exc).__name__
                if isinstance(exc, httpx.HTTPStatusError):
                    result["embedding_http_status"] = exc.response.status_code
                result['fallback'] = 'embedding_unavailable'
    selected = select_records(docs, scores, query)
    result.update(records=selected, retrieval_ms=round((perf_counter()-started)*1000, 2),
                  records_utf8_bytes=len(canonical(selected).encode()))
    return result


if __name__ == '__main__':
    import argparse
    import asyncio
    parser = argparse.ArgumentParser(description='Prepare static simulator embeddings locally before decisions.')
    parser.add_argument('--prepare', action='store_true', required=True)
    parser.parse_args()
    os.environ.setdefault('KNOWLEDGE_EMBED_TIMEOUT', '60')
    async def prepare():
        for domain in ['water', 'grid', 'nuclear']:
            result = await retrieve(domain, {}, mode='hybrid')
            print(canonical({k:v for k,v in result.items() if k not in {'query', 'records'}}), flush=True)
            if result['method'] != 'hybrid':
                raise SystemExit('Embedding preparation failed; inspect fallback above')
    asyncio.run(prepare())
