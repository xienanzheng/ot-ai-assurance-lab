import asyncio
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from scripts.run_recovery_timeline import CHECKS, TAGS, recovered
from services.plant_sim.app.scenarios import scenario_modifiers
from services.supervisor.app import agents


def samples():
    values = {k: 1.0 for k in TAGS}
    values.update({k: (low + high) / 2 for k, (low, high) in CHECKS.items()})
    return [{'minute': m, 'values': deepcopy(values), 'quality': {k: 'good' for k in TAGS}, 'alarms': []} for m in range(30, 39)]


def test_resolution_requires_elapsed_contiguous_safe_window():
    history = samples()
    assert recovered(history)
    assert not recovered(history[1:])
    history[4]['minute'] = 99
    assert not recovered(history)


@pytest.mark.parametrize('change', ['effluent', 'ph', 'quality', 'alarm', 'nonfinite'])
def test_a_single_unsafe_or_unknown_observation_prevents_resolution(change):
    history = samples()
    s = history[4]
    if change == 'effluent': s['values']['filtered_turbidity_ntu'] = 1.01
    if change == 'ph': s['values']['finished_water_ph'] = 6.0
    if change == 'quality': s['quality']['coagulation_ph'] = 'uncertain'
    if change == 'alarm': s['alarms'] = ['TEST']
    if change == 'nonfinite': s['values']['filtered_turbidity_ntu'] = float('nan')
    assert not recovered(history)


def test_disturbance_ramps_and_does_not_expire_at_recovery_horizon():
    value = lambda m: scenario_modifiers(m, 'gradual_turbidity_rise')['raw_turbidity_ntu']
    assert value(0) == value(10) == 8
    assert value(10) < value(15) < value(20) < value(25) < value(30)
    assert value(30) == value(60) == value(120) == 72


def test_server_history_excludes_other_runs_resets_and_offline_studies(monkeypatch):
    context = {'run_id':'current', 'plc':{'controller_generation':'g1'},
               'plant':{'simulation_time':'2026-01-01T00:38:00+00:00'}}
    record = {'id':'valid', 'before':deepcopy(context), 'evaluate_only':False,
              'proposal':{'changes':{}}, 'gate':{'status':'accepted'}, 'applied':True}
    other = deepcopy(record); other['id']='other';other['before']['run_id']='old'
    reset = deepcopy(record); reset['id']='reset';reset['before']['plc']['controller_generation']='g0'
    offline = deepcopy(record); offline['id']='offline';offline['evaluate_only']=True
    monkeypatch.setattr(agents, 'list_audits', lambda *args: [other, reset, offline, record])
    real_client = httpx.AsyncClient
    def handler(request):
        assert request.url.path == '/water/exercise'
        return httpx.Response(200, json={'recent_samples':samples()})
    monkeypatch.setattr(agents.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    service = agents.AgentService(SimpleNamespace(plant_url='http://plant'), 'http://unused')
    async def current(domain): return deepcopy(context)
    monkeypatch.setattr(service, 'context', current)
    history = asyncio.run(service.water_history(context))
    assert [r['record_id'] for r in history['previous_exchanges']] == ['valid']
    assert len(history['recent_samples']) == 9
    assert history['recent_samples'][-1]['minute'] == 38
    reconstructed = dict(zip(history['sample_columns'], history['recent_samples'][-1]['values']))
    assert reconstructed == {k:samples()[-1]['values'][k] for k in history['sample_columns']}
    assert history['recent_samples'][-1]['quality_exceptions'] == {}
    captured = deepcopy(context);captured['plc']['controller_generation']='obsolete'
    with pytest.raises(HTTPException):
        asyncio.run(service.water_history(captured))
