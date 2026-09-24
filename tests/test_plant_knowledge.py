import asyncio
import json

import pytest

from services.supervisor.app import plant_knowledge as knowledge


def retrieve(domain='water', state=None, mode='lexical'):
    return asyncio.run(knowledge.retrieve(domain, state or {}, mode=mode))


def test_off_does_not_access_embeddings(monkeypatch):
    async def fail(*args):
        raise AssertionError('Embedding access while disabled')
    monkeypatch.setattr(knowledge, 'embed_documents', fail)
    assert retrieve(mode='off')['records'] == []


def test_domain_filter_budget_and_relevant_water_record():
    result = retrieve(state={'active_alarms': ['coagulation pH low; raw alkalinity falling']})
    assert result['records'][0]['id'] == 'water.coagulation'
    assert all(r['domain'] == 'water' for r in result['records'])
    assert len(result['records']) <= 3
    assert len(json.dumps(result['records']).encode()) <= 5000
    assert result['pack_sha256'] and result['state_sha256']


def test_hosted_never_contacts_local_embedding_service(monkeypatch):
    monkeypatch.setenv('HOSTED_MODE', 'true')
    async def fail(*args):
        raise AssertionError('Hosted must not contact local embedding service')
    monkeypatch.setattr(knowledge, 'embed_documents', fail)
    result = retrieve(mode='hybrid')
    assert result['method'] == 'lexical'
    assert result['fallback'] == 'hosted_embeddings_unavailable'


def test_embedding_failure_is_explicit_and_still_scoped(monkeypatch):
    async def fail(*args):
        raise ValueError('invalid embedding')
    monkeypatch.setattr(knowledge, 'embed_documents', fail)
    result = retrieve('grid', mode='hybrid')
    assert result['method'] == 'lexical'
    assert result['fallback'] == 'embedding_unavailable'
    assert all(r['domain'] == 'grid' for r in result['records'])


def test_invalid_vectors_are_rejected():
    for vectors in ([[0, 0]], [[float('nan'), 1]], [[1, 0], [1]], [[True, 1]]):
        with pytest.raises(ValueError):
            knowledge.validate_vectors(vectors, len(vectors))


def test_hybrid_uses_probably_relevant_document_not_other_domain(monkeypatch):
    async def embeddings(documents, query):
        return ([[1., 0.] if d['id'] == 'water.coagulation' else [0., 1.] for d in documents],
                [1., 0.], {'model': 'test-embed', 'digest': 'test', 'cache_hits': 0})
    monkeypatch.setattr(knowledge, 'embed_documents', embeddings)
    result = retrieve(state={'active_alarms': ['coagulation pH']}, mode='hybrid')
    assert result['method'] == 'hybrid'
    assert result['records'][0]['id'] == 'water.coagulation'
    assert result['embedding']['digest'] == 'test'


def test_bad_pack_fails_to_empty_context(monkeypatch):
    def fail():
        raise ValueError('bad pack')
    monkeypatch.setattr(knowledge, 'load_pack', fail)
    result = retrieve()
    assert result['records'] == []
    assert result['fallback'] == 'invalid_pack'


def test_scope_filters_before_embedding(monkeypatch):
    pack = knowledge.load_pack()
    for record in pack['records']:
        record['scenarios'] = ['different-scenario']
    monkeypatch.setattr(knowledge, 'load_pack', lambda: pack)
    assert retrieve(state={'scenario': 'normal'})['records'] == []


def test_unknown_equipment_does_not_receive_irrelevant_plant_records():
    assert retrieve(state={'sensors': {'unknown': {'value': 1}}, 'equipment': {'unknown': {}}})['records'] == []


def test_water_compact_quality_and_limits_inform_query():
    query = knowledge.query_for('water', {'sensor_values': {
        'coagulation_ph': [0.1, 'pH', 'stale']}})
    assert 'coagulation_ph' in query
    assert json.loads(query)['bad_quality'] == ['coagulation_ph']


def test_pack_sources_and_sensor_names_exist():
    from pathlib import Path
    from services.plant_sim.app.simulator import WaterPlantSimulator
    from services.infrastructure_sim.app.grid import GridSimulator
    from services.infrastructure_sim.app.nuclear import NuclearSimulator
    states = {domain: cls().snapshot().model_dump(mode='json') for domain, cls in
              [('water', WaterPlantSimulator), ('grid', GridSimulator), ('nuclear', NuclearSimulator)]}
    for record in knowledge.load_pack()['records']:
        assert set(record['sensors']) <= states[record['domain']]['sensors'].keys()
        assert all(Path(source).is_file() for source in record['sources'])


def test_embedding_cache_reuses_documents_but_refreshes_query_and_model_digest(monkeypatch, tmp_path):
    import httpx
    calls = []
    current = {'digest': 'v1'}
    real_client = httpx.AsyncClient
    def handler(request):
        if request.url.path == '/api/tags':
            return httpx.Response(200, json={'models':[{'name':'embeddinggemma:latest', 'digest':current['digest']}]})
        payload = json.loads(request.content)
        calls.append(payload['input'])
        return httpx.Response(200, json={'model':'embeddinggemma', 'embeddings':[[1., 0.] for _ in payload['input']]})
    monkeypatch.setattr(knowledge.httpx, 'AsyncClient', lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))
    monkeypatch.setenv('KNOWLEDGE_CACHE_PATH', str(tmp_path/'vectors.sqlite3'))
    monkeypatch.setenv('KNOWLEDGE_EMBED_URL', 'http://127.0.0.1:11434')
    docs = [{'id':'test', 'text':'Static simulator record'}]
    async def exercise():
        await knowledge.embed_documents(docs, 'state one')
        _, _, meta = await knowledge.embed_documents(docs, 'state two')
        assert meta['cache_hits'] == 1
        current['digest'] = 'v2'
        await knowledge.embed_documents(docs, 'state three')
    asyncio.run(exercise())
    assert list(map(len, calls)) == [2, 1, 2]
    assert calls[1] == ['task: search result | query: state two']


def test_request_mode_is_explicit_and_validated():
    from services.supervisor.app.agents import AgentRequest
    assert AgentRequest(knowledge_mode='hybrid').knowledge_mode == 'hybrid'
    with pytest.raises(ValueError):
        AgentRequest(knowledge_mode='arbitrary')


@pytest.mark.parametrize('domain', ['water', 'grid', 'nuclear'])
def test_prompt_retains_live_measurements_and_limits_with_retrieval(monkeypatch, domain):
    from services.supervisor.app.ollama_client import OllamaSupervisor, InfrastructureProposal
    from services.plant_sim.app.simulator import WaterPlantSimulator
    from services.infrastructure_sim.app.grid import GridSimulator
    from services.infrastructure_sim.app.nuclear import NuclearSimulator
    from shared.models import ControlProposal, SetpointChanges
    worker = OllamaSupervisor()
    captured = []
    async def chat(domain, payload, schema):
        captured.append(payload)
        if domain == 'water':
            return ControlProposal(changes=SetpointChanges(), expected_effect='Hold', confidence=.7, explanation='Test only'), 'test'
        return InfrastructureProposal(objective='Hold state', changes={}, confidence=.7, explanation='Test only'), 'test'
    monkeypatch.setattr(worker, '_chat', chat)
    state = {'water':WaterPlantSimulator, 'grid':GridSimulator, 'nuclear':NuclearSimulator}[domain]().snapshot()
    async def exercise():
        for mode in ['off', 'lexical']:
            worker.knowledge_mode = mode
            if domain == 'water':
                await worker.propose(state, {})
            else:
                await worker.propose_infrastructure(domain, state.model_dump(mode='json'))
    asyncio.run(exercise())
    before, after = [json.loads(p['messages'][-1]['content']) for p in captured]
    retrieved = after.pop('plant_knowledge')
    assert before == after
    assert isinstance(retrieved['records'], list)
    assert captured[1]['_retrieval']['pack_sha256']
    assert 'retrieval_ms' not in retrieved
