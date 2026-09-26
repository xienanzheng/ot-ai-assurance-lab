import asyncio
from copy import deepcopy
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from services.supervisor.app import agents
from services.supervisor.app.agents import AgentRequest, AgentService
from services.supervisor.app.ollama_client import OllamaSupervisor
from services.infrastructure_sim.app.grid import GridSimulator


def test_provider_selection_is_typed_and_does_not_accept_arbitrary_provider():
    assert AgentRequest(provider='jev').provider == 'jev'
    with pytest.raises(ValueError): AgentRequest(provider='external-url')


def test_jev_candidates_are_numeric_bounded_and_hold_is_explicit():
    from services.supervisor.app.jev_client import candidates, to_proposal
    state=GridSimulator().snapshot().model_dump(mode='json')
    options=candidates('grid', {'plant':state})
    assert options['hold']['changes']=={}
    action=next(v for v in options.values() if v['changes'])
    assert len(action['changes'])==1
    proposal=to_proposal('grid', action, .8)
    assert proposal.changes == action['changes']
    with pytest.raises(ValueError): to_proposal('grid', action, float('nan'))
    assert 'Adapter' in proposal.explanation


def test_comparison_captures_once_never_applies_and_preserves_records(monkeypatch):
    service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()), 'http://unused')
    sim=GridSimulator(); original=sim.snapshot().model_dump(mode='json')
    calls=[]; records={}; captures=[]
    async def context(domain): captures.append(domain); return {'plant':deepcopy(original),'run_id':'run'}
    async def cycle(domain, **kwargs):
        calls.append(kwargs)
        return {'id':kwargs['provider'], 'applied':False, 'before':kwargs['context']}
    monkeypatch.setattr(service,'context',context)
    monkeypatch.setattr(service,'cycle',cycle)
    monkeypatch.setattr(agents,'create_audit',lambda *a:'comparison')
    monkeypatch.setattr(agents,'update_audit',lambda id,**kw:records.setdefault(id,{}).update(kw))
    monkeypatch.setattr(agents,'get_audit',lambda id:records[id])
    result=asyncio.run(service.compare('grid', AgentRequest()))
    assert captures==['grid']
    assert [c['provider'] for c in calls]==['qwen','jev']
    assert all(c['evaluate_only'] for c in calls)
    assert calls[0]['context']==calls[1]['context']
    assert result['record_type']=='comparison' and not result['applied']
    assert result['comparison']['record_ids']==['qwen','jev']
    assert sim.snapshot().model_dump(mode='json')==original


def test_apply_rejects_changed_exercise_before_enabling_control(monkeypatch):
    service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()),'http://unused')
    monkeypatch.setattr(agents,'get_audit',lambda id:{'id':id,'domain':'grid','record_type':'decision','status':'complete','evaluate_only':True,'before':{'run_id':'old','plant':{'elapsed_minutes':0}},'proposal':{'changes':{'gas_dispatch_mw':480}},'gate':{'status':'shadow'}})
    async def context(domain): return {'run_id':'new','plant':{'elapsed_minutes':0}}
    monkeypatch.setattr(service,'context',context)
    with pytest.raises(HTTPException) as exc: asyncio.run(service.apply_record('r'))
    assert exc.value.status_code==409

@pytest.fixture
def audit_database(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from services.supervisor.app import agent_audit
    from services.supervisor.app.database import Base
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(agent_audit,'SessionLocal',sessionmaker(bind=engine))
    yield
    engine.dispose()


def test_comparison_selection_rechecks_real_gate_changes_hmi_and_expires(audit_database,monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from services.infrastructure_sim.app import main
    from services.supervisor.app import agent_audit
    from services.supervisor.app.ollama_client import InfrastructureProposal
    main.grid.reset(); client=TestClient(main.app)
    before=main.grid.snapshot().model_dump(mode='json')
    initial=before['controls']['gas_dispatch_mw']
    target=initial+30
    context={'plant':before,'run_id':main.grid.exercise.run_id}
    parent=agent_audit.create_audit('grid',{'comparison':'test'})
    proposal=InfrastructureProposal(objective='Test bounded target',changes={'gas_dispatch_mw':target},confidence=.9,explanation='Test target')
    identifier=agent_audit.create_audit('grid',{})
    agent_audit.update_audit(identifier,status='complete',comparison_id=parent,before=context,proposal=proposal.model_dump(),evaluate_only=True,gate={'status':'shadow'},provider='jev')
    real_client=httpx.AsyncClient
    def handler(request):
        response=client.request(request.method,request.url.path,content=request.content)
        return httpx.Response(response.status_code,json=response.json())
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()),'http://infra')
    result=asyncio.run(service.apply_record(identifier))
    assert result['applied'] is True
    assert main.grid.snapshot().controls['gas_dispatch_mw']==target
    assert main.grid.minute==0 and main.grid.running is False
    assert main.grid.ai_lease['expires_minute']==5
    assert main.grid.snapshot().ai_decision.source.startswith('jev:')
    with pytest.raises(HTTPException): asyncio.run(service.apply_record(identifier))
    second=agent_audit.create_audit('grid',{})
    agent_audit.update_audit(second,**{k:v for k,v in agent_audit.get_audit(identifier).items() if k not in {'id','application_id'}})
    with pytest.raises(HTTPException): asyncio.run(service.apply_record(second))
    main.grid.advance(5)
    assert main.grid.controls['gas_dispatch_mw']==initial
    assert main.grid.ai_lease is None
    main.grid.reset()


def test_jev_unknown_choice_fails_closed_with_audit(audit_database,monkeypatch):
    import httpx
    from services.supervisor.app import jev_client,agent_audit
    from services.supervisor.app.ollama_client import OllamaUnavailable
    monkeypatch.setattr(jev_client,'local_key',lambda:'test-credential')
    real_client=httpx.AsyncClient
    def handler(request): return httpx.Response(200,json={'answers':{'response':{'choice':'disable_protection','confidence':1}}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    with pytest.raises(OllamaUnavailable): asyncio.run(jev_client.propose('grid',{'plant':GridSimulator().snapshot().model_dump(mode='json')}))
    record=agent_audit.list_audits()[0]
    assert record['applied'] is False and record['gate']['status']=='not_submitted'
    assert 'test-credential' not in str(record)

def test_water_requested_cycle_applies_live_targets_without_reset(audit_database,monkeypatch,safe_snapshot):
    import httpx
    from fastapi.testclient import TestClient
    from shared.models import ControlMode, ControlProposal, SetpointChanges, RunConfig
    from services.plc_control.app import main
    from services.plc_control.app.controller import BaselineController,SafetyGate
    from services.supervisor.app import agent_audit
    controller=BaselineController()
    monkeypatch.setattr(main,'controller',controller)
    monkeypatch.setattr(main,'gate',SafetyGate(controller))
    async def snapshot():return safe_snapshot
    monkeypatch.setattr(main,'fetch_snapshot',snapshot)
    client=TestClient(main.app)
    target=controller.setpoints.pressure_target_m+1
    async def propose(*args,**kw):
        p=ControlProposal(changes=SetpointChanges(pressure_target_m=target),confidence=.95,expected_effect='Adjust simulated pressure',explanation='Bounded pressure correction')
        p.decision_id=agent_audit.create_audit('water',{})
        return p
    worker=OllamaSupervisor();monkeypatch.setattr(worker,'propose',propose)
    manager=SimpleNamespace(ollama=worker,active_config=RunConfig(),plant_url='http://plant',plc_url='http://plc')
    service=AgentService(manager,'http://infra')
    async def context(domain):return {'plant':safe_snapshot.model_dump(mode='json'),'plc':main.status(),'run_id':'water-run'}
    monkeypatch.setattr(service,'context',context)
    real_client=httpx.AsyncClient
    def handler(request):
        if request.url.path=='/mode':
            safe_snapshot.controller_mode=ControlMode.GATED_AUTO
            return httpx.Response(200,json={'mode':'gated_auto'})
        response=client.request(request.method,str(request.url),content=request.content)
        return httpx.Response(response.status_code,json=response.json())
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    record=asyncio.run(service.requested_cycle('water',AgentRequest(evaluate_only=False)))
    assert record['applied'] and main.status()['setpoints']['pressure_target_m']==target
    assert controller.supervisory_expiry is not None
    assert not manager.active_config.ai_schedule_enabled
    assert manager.active_config.controller_mode is ControlMode.GATED_AUTO
    assert safe_snapshot.elapsed_minutes==0
