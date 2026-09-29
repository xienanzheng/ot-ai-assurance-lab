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

@pytest.mark.parametrize("target_name,delta,adaptive,observe",[("pressure_target_m",1,False,5),("chlorine_target_mg_l",.05,True,12)])
def test_water_requested_cycle_applies_live_targets_without_reset(target_name,delta,adaptive,observe,audit_database,monkeypatch,safe_snapshot):
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
    target=getattr(controller.setpoints,target_name)+delta
    async def propose(*args,**kw):
        p=ControlProposal(changes=SetpointChanges(**{target_name:target}),confidence=.95,expected_effect='Adjust simulated pressure',explanation='Bounded pressure correction')
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
    async def run():
        if adaptive:
            await service.enable_application('water')
            return await service.cycle('water',evaluate_only=False,adaptive_timing=True)
        return await service.requested_cycle('water',AgentRequest(evaluate_only=False))
    record=asyncio.run(run())
    assert record['applied'] and main.status()['setpoints'][target_name]==target
    assert controller.supervisory_expiry is not None
    assert controller.supervisory_timing["observe_minutes"]==observe
    assert record["lease_minutes"]==(observe+2 if adaptive else 5)
    assert not manager.active_config.ai_schedule_enabled
    assert manager.active_config.controller_mode is ControlMode.GATED_AUTO
    assert safe_snapshot.elapsed_minutes==0


def test_cancelled_model_result_never_reaches_gate_and_retains_provider(audit_database,monkeypatch):
    from services.supervisor.app import agent_audit
    from services.supervisor.app.ollama_client import InfrastructureProposal
    worker=OllamaSupervisor()
    async def propose(*args,**kwargs):
        p=InfrastructureProposal(objective='Bounded adjustment',changes={'gas_dispatch_mw':480},confidence=.9,explanation='Test')
        p._audit_id=agent_audit.create_audit('grid',{})
        return p
    monkeypatch.setattr(worker,'propose_infrastructure',propose)
    service=AgentService(SimpleNamespace(ollama=worker),'http://unused')
    async def forbidden(*args,**kwargs):raise AssertionError('Stopped loop submitted a proposal')
    monkeypatch.setattr(service,'submit',forbidden)
    record=asyncio.run(service.cycle('grid',context={'run_id':'r','plant':GridSimulator().snapshot().model_dump(mode='json')},evaluate_only=False,application_guard=lambda:False))
    assert record['status']=='cancelled' and not record['applied']
    assert record.get('provider')=='qwen'


@pytest.mark.parametrize('domain,target_name,delta',[('grid','gas_dispatch_mw',30),('nuclear','turbine_load_target_mwe',10)])
@pytest.mark.parametrize('provider',['qwen','jev'])
def test_feedback_runs_real_infrastructure_gate_observes_then_releases(domain,target_name,delta,provider,audit_database,monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from services.infrastructure_sim.app import main
    from services.supervisor.app import agent_audit,jev_client
    from services.supervisor.app.feedback import FeedbackRequest
    from services.supervisor.app.ollama_client import InfrastructureProposal
    sim=getattr(main,domain)
    sim.reset(); client=TestClient(main.app)
    initial=sim.controls[target_name]; target=initial+delta
    contexts=[]
    async def make_proposal(*args,**kwargs):
        contexts.append(kwargs.get('experiment_context'))
        p=InfrastructureProposal(objective='Bounded test correction',changes={target_name:target},confidence=.95,explanation='Simulated test')
        identifier=agent_audit.create_audit(domain,{})
        p._audit_id=identifier
        return (p,identifier) if provider=='jev' else p
    worker=OllamaSupervisor()
    monkeypatch.setattr(worker,'propose_infrastructure',make_proposal)
    monkeypatch.setattr(jev_client,'propose',make_proposal)
    real_client=httpx.AsyncClient
    def handler(request):
        response=client.request(request.method,request.url.path,content=request.content)
        return httpx.Response(response.status_code,json=response.json())
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    service=AgentService(SimpleNamespace(ollama=worker),'http://infra')
    async def run():
        await service.feedback.start(domain,FeedbackRequest(provider=provider,max_calls=1))
        sim.running=True
        await service.feedback.tick()
        await asyncio.gather(*list(service.tasks))
        assert sim.controls[target_name]==target
        assert sim.ai_lease['expires_minute']==7
        assert service.feedback.state['status']=='observing'
        record=agent_audit.get_audit(service.feedback.state['records'][0])
        assert record['applied'] and record['provider']==provider
        assert contexts[0]['plant_sops']['procedures']
        assert contexts[0]['feedback']['loop_id']==service.feedback.state['id']
        proposal=InfrastructureProposal(objective='Repeat early',changes={target_name:target+delta},confidence=.95,explanation='Early repeat')
        decision=sim.apply_ai_proposal(**proposal.model_dump(exclude={'episode_status'}),source='test',lease_minutes=7)
        assert decision.gate.status=='rejected'
        for _ in range(5):
            sim.advance(1)
            await service.feedback.tick()
        assert not service.feedback.active
        assert sim.ai_lease is None
        assert sim.controls[target_name]==initial
        assert service.feedback.state['response']['status']=='observed_trend'
    try:asyncio.run(run())
    finally:sim.reset()


def test_feedback_api_has_resolvable_request_schema():
    from fastapi import FastAPI
    app=FastAPI(); service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()),'http://unused')
    app.include_router(service.router)
    schema=app.openapi()
    assert 'FeedbackRequest' in schema['components']['schemas']


def test_escalation_cannot_apply_accompanying_targets(audit_database,monkeypatch):
    from services.supervisor.app import agent_audit
    from services.supervisor.app.ollama_client import InfrastructureProposal
    worker=OllamaSupervisor()
    async def propose(*args,**kwargs):
        p=InfrastructureProposal(objective='Operator review',changes={'gas_dispatch_mw':480},confidence=.95,explanation='Escalate',episode_status='escalate')
        p._audit_id=agent_audit.create_audit('grid',{})
        return p
    monkeypatch.setattr(worker,'propose_infrastructure',propose)
    service=AgentService(SimpleNamespace(ollama=worker),'http://unused')
    async def submit(*args,**kwargs):return {'status':'accepted'},True
    monkeypatch.setattr(service,'submit',submit)
    record=asyncio.run(service.cycle('grid',context={'run_id':'r','plant':GridSimulator().snapshot().model_dump(mode='json')},evaluate_only=False))
    assert not record['applied']
    assert record['gate']['status']=='rejected'


def test_fast_water_application_waits_for_mode_publication(audit_database,monkeypatch,safe_snapshot):
    """The HTTP plant mode and PLC's published snapshot are distinct state copies."""
    import httpx
    from shared.models import ControlMode,ControlProposal,SetpointChanges,RunConfig
    from services.plant_sim.app import main as plant
    from services.plc_control.app import main as plc
    from services.plc_control.app.controller import BaselineController,SafetyGate
    from services.supervisor.app import agent_audit
    current=safe_snapshot.model_copy(deep=True);current.controller_mode=ControlMode.BASELINE
    published=current.model_copy(deep=True)
    sim=SimpleNamespace(controller_mode=ControlMode.BASELINE)
    monkeypatch.setattr(plant,'simulator',sim)
    async def publish():
        await asyncio.sleep(0)
        current.controller_mode=sim.controller_mode
        published.controller_mode=sim.controller_mode
    monkeypatch.setattr(plant.opcua,'sync',publish)
    controller=BaselineController();monkeypatch.setattr(plc,'controller',controller);monkeypatch.setattr(plc,'gate',SafetyGate(controller))
    async def snapshot():return published
    monkeypatch.setattr(plc,'fetch_snapshot',snapshot)
    worker=OllamaSupervisor()
    async def propose(*args,**kwargs):
        p=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.1),confidence=.75,expected_effect='Trim chlorine',explanation='Bounded target change')
        p.decision_id=agent_audit.create_audit('water',{});return p
    monkeypatch.setattr(worker,'propose',propose)
    manager=SimpleNamespace(ollama=worker,active_config=RunConfig(),plant_url='http://plant',plc_url='http://plc')
    service=AgentService(manager,'http://unused')
    async def context(domain):
        current.controller_mode=sim.controller_mode
        return {'plant':current.model_dump(mode='json'),'plc':plc.status(),'run_id':'r'}
    monkeypatch.setattr(service,'context',context)
    real=httpx.AsyncClient
    async def route(request):
        app=plant.app if request.url.host=='plant' else plc.app
        async with real(transport=httpx.ASGITransport(app=app)) as client:return await client.send(request)
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(route),**kwargs))
    record=asyncio.run(service.requested_cycle('water',AgentRequest(evaluate_only=False)))
    assert record['applied'] and record['gate']['status']=='accepted'
    assert controller.setpoints.chlorine_target_mg_l==1.1
    assert published.controller_mode is ControlMode.GATED_AUTO


@pytest.mark.parametrize('reason',['PLC reset while the model was reasoning','Control mode changed during inference','Proposal snapshot is stale or clock was reset'])
def test_plc_conflict_exposes_reason_without_internal_url(reason,monkeypatch,safe_snapshot):
    import httpx
    from shared.models import ControlProposal,SetpointChanges
    service=AgentService(SimpleNamespace(plc_url='http://127.0.0.1:8082'),'http://unused')
    context={'plant':safe_snapshot.model_dump(mode='json'),'plc':{'controller_generation':'test-generation'}}
    proposal=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.1),confidence=.75,expected_effect='Trim',explanation='Test')
    real=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(lambda req:httpx.Response(409,json={'detail':reason})),**kw))
    with pytest.raises(Exception) as failure:asyncio.run(service.submit('water',context,proposal,'qwen'))
    assert reason in str(failure.value)
    assert '127.0.0.1' not in str(failure.value)


@pytest.mark.parametrize('conflict',['reset','mode','stale'])
def test_real_state_conflicts_still_prevent_water_actuation(conflict,monkeypatch,safe_snapshot):
    from datetime import timedelta
    from services.plc_control.app import main
    from services.plc_control.app.controller import BaselineController,SafetyGate
    from shared.models import ControlMode,ControlProposal,SetpointChanges
    safe_snapshot.controller_mode=ControlMode.GATED_AUTO
    controller=BaselineController();monkeypatch.setattr(main,'controller',controller);monkeypatch.setattr(main,'gate',SafetyGate(controller))
    async def snapshot():return safe_snapshot
    monkeypatch.setattr(main,'fetch_snapshot',snapshot)
    args={'expected_controller_generation':main.controller_generation,'expected_mode':'gated_auto','expected_time':safe_snapshot.simulation_time.isoformat()}
    if conflict=='reset':args['expected_controller_generation']='previous-generation'
    if conflict=='mode':args['expected_mode']='baseline'
    if conflict=='stale':args['expected_time']=(safe_snapshot.simulation_time-timedelta(minutes=6)).isoformat()
    proposal=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.1),confidence=.75,expected_effect='Trim',explanation='Test')
    with pytest.raises(HTTPException) as failure:asyncio.run(main.evaluate_proposal(proposal,apply=True,**args))
    assert failure.value.status_code==409
    assert controller.setpoints.chlorine_target_mg_l==1.15


def test_opc_publications_cannot_overwrite_new_mode_with_older_snapshot(safe_snapshot):
    from services.plant_sim.app.opcua_server import WaterOpcUaServer
    from shared.models import ControlMode
    async def run():
        entered=asyncio.Event();release=asyncio.Event();new_started=asyncio.Event()
        values={};snapshot=safe_snapshot.model_copy(deep=True);snapshot.controller_mode=ControlMode.BASELINE
        class Node:
            def __init__(self,name):self.name=name
            async def write_value(self,value):
                if self.name=='controller_mode' and value=='baseline':entered.set();await release.wait()
                values[self.name]=value
        server=WaterOpcUaServer(SimpleNamespace(snapshot=lambda:snapshot.model_copy(deep=True),set_actuators=lambda changes:None))
        server.system_nodes={name:Node(name) for name in ['simulation_time','elapsed_minutes','simulation_speed','controller_mode','active_scenario','alarm_state','emergency_stop']}
        old=asyncio.create_task(server.sync());await entered.wait()
        snapshot.controller_mode=ControlMode.GATED_AUTO
        async def publish_new():new_started.set();await server.sync()
        new=asyncio.create_task(publish_new());await new_started.wait();await asyncio.sleep(0)
        assert not new.done()  # Waits for older publication instead of racing it.
        release.set();await asyncio.gather(old,new)
        assert values['controller_mode']=='gated_auto'
    asyncio.run(run())
