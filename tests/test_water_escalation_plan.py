import asyncio
import pytest
from shared.water_escalation import operator_plan


@pytest.mark.parametrize('hosted',['true','false'])
@pytest.mark.parametrize('trigger',['alarm','state','stop','override','trip','model'])
def test_operator_plan_always_present_for_escalation(hosted,trigger,monkeypatch,safe_snapshot):
    monkeypatch.setenv('HOSTED_MODE',hosted)
    state=safe_snapshot.model_dump(mode='json');controls={};status=None
    if trigger=='alarm':state['active_alarms']=[{'code':'VALVE_COMMAND_MISMATCH','severity':'critical'}]
    if trigger=='state':state['safety_state']='critical'
    if trigger=='stop':state['emergency_stop']=True
    if trigger=='override':state['active_injections']=['zone_2_valve_forced_closed']
    if trigger=='trip':controls={'trips':[{'latched':True}]}
    if trigger=='model':status='escalate'
    plan=operator_plan(state,controls,status)
    assert plan['operator_intervention_required'] and plan['actions']==[]
    assert plan['recommended_actions'] and plan['monitoring_plan']['sensor_ids']
    assert all(a['requires_operator'] for a in plan['recommended_actions'])


def test_noncritical_normal_state_has_no_forced_plan(safe_snapshot):
    assert operator_plan(safe_snapshot.model_dump(mode='json')) is None


@pytest.mark.parametrize('hosted',['true','false'])
def test_live_plc_blocks_critical_alarm_even_with_normal_state(hosted,monkeypatch,safe_snapshot):
    from services.plc_control.app import main
    from shared.models import Alarm,ControlProposal,SetpointChanges,ControlMode
    monkeypatch.setenv('HOSTED_MODE',hosted)
    from services.plc_control.app.controller import BaselineController,SafetyGate
    controller=BaselineController()
    monkeypatch.setattr(main,'controller',controller)
    monkeypatch.setattr(main,'gate',SafetyGate(controller))
    safe_snapshot.controller_mode=ControlMode.GATED_AUTO
    safe_snapshot.active_alarms=[Alarm(code='VALVE_COMMAND_MISMATCH',severity='critical',message='Mismatch')]
    async def snapshot():return safe_snapshot
    monkeypatch.setattr(main,'fetch_snapshot',snapshot)
    before=main.controller.setpoint_dict()
    p=ControlProposal(changes=SetpointChanges(pressure_target_m=45),confidence=.9,expected_effect='test',explanation='test')
    result=asyncio.run(main.evaluate_proposal(p,apply=True))
    assert result.status=='rejected' and main.controller.setpoint_dict()==before

@pytest.mark.parametrize('bad', [None, {}, {'operator_intervention_required':False}, {'recommended_actions':['invented']}])
def test_incomplete_model_plan_rejected(bad,safe_snapshot):
    from shared.water_escalation import validate_response
    plan=operator_plan(safe_snapshot.model_dump(mode='json'),episode_status='escalate')
    with pytest.raises(ValueError):validate_response(bad,plan)


def test_valid_model_plan_references_only_supplied_guidance(safe_snapshot):
    from shared.water_escalation import response_contract,validate_response
    plan=operator_plan(safe_snapshot.model_dump(mode='json'),episode_status='escalate')
    value,schema=response_contract(plan)
    assert validate_response(value,plan)['source']=='model_selected_sop'
    assert set(schema['required'])==set(value)

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


@pytest.mark.parametrize('hosted',['true','false'])
@pytest.mark.parametrize('provider',['qwen','jev'])
@pytest.mark.parametrize('valid',[True,False])
def test_provider_requires_explicit_plan(hosted,provider,valid,monkeypatch,safe_snapshot,audit_database):
    import json,httpx
    from shared.water_escalation import response_contract
    from services.supervisor.app import ollama_client,jev_client,agent_audit
    from services.plc_control.app.controller import BaselineController
    safe_snapshot.safety_state='critical'
    state=safe_snapshot.model_dump(mode='json')
    plan=operator_plan(state,episode_status='escalate')
    value,_=response_contract(plan)
    monkeypatch.setenv('HOSTED_MODE',hosted)
    monkeypatch.setattr(jev_client,'local_key',lambda:'test-only')
    real_client=httpx.AsyncClient
    def handler(request):
        if request.url.path=='/api/tags':return httpx.Response(200,json={'models':[]})
        payload=json.loads(request.content)
        if provider=='jev':
            assert 'operator_response' in payload['questions']
            answers={'response':{'choice':'review','confidence':.9}}
            if valid:answers['operator_response']={'choice':'required_plan','confidence':.9}
            return httpx.Response(200,json={'answers':answers})
        assert 'operator_response' in payload['format']['required']
        answer={'actions':[],'confidence':.9,'episode_status':'escalate','reason':'Critical condition requires operator review.'}
        if valid:answer['operator_response']=value
        return httpx.Response(200,json={'message':{'content':json.dumps(answer)}})
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    targets=BaselineController().setpoint_dict()
    async def run():
        if provider=='jev':return await jev_client.propose('water',{'plant':state,'plc':{'setpoints':targets}})
        worker=ollama_client.OllamaSupervisor();worker.inference_profile='fast';worker.knowledge_mode='off'
        return await worker.propose(safe_snapshot,targets)
    if not valid:
        with pytest.raises(ollama_client.OllamaUnavailable):asyncio.run(run())
    else:
        result=asyncio.run(run());proposal=result[0] if provider=='jev' else result
        record=agent_audit.get_audit(proposal.decision_id)
        assert proposal.episode_status=='escalate'
        assert not proposal.changes.model_dump(exclude_none=True)
        assert record['operator_response']['source']=='model_selected_sop'
        assert record['response']


def test_hosted_status_does_not_import_local_training_modules(monkeypatch):
    import builtins
    from types import SimpleNamespace
    from services.supervisor.app import agents,jev_client
    from services.supervisor.app.ollama_client import OllamaSupervisor
    service=agents.AgentService(SimpleNamespace(ollama=OllamaSupervisor()),'http://unused')
    monkeypatch.setattr(agents,'HOSTED',True)
    async def available():return True
    async def model_status():return {}
    monkeypatch.setattr(jev_client,'availability',available)
    monkeypatch.setattr(service.manager.ollama,'status',model_status)
    original=builtins.__import__
    def restricted(name,*args,**kwargs):
        if name=='water_candidate' or name.startswith('scripts'):raise ModuleNotFoundError('Training files excluded from hosted image')
        return original(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',restricted)
    route=next(r for r in service.router.routes if r.path.endswith('/state'))
    assert asyncio.run(route.endpoint())['water_candidate']=={'available':False}


def test_jev_key_lookup_handles_container_layout(monkeypatch):
    from services.supervisor.app import jev_client
    monkeypatch.delenv('OPENROUTER_API_KEY',raising=False)
    monkeypatch.setattr(jev_client,'__file__','/app/app/jev_client.py')
    assert jev_client.local_key() is None
