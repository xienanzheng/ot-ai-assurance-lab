import asyncio
import json
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from services.supervisor.app import agents
from services.supervisor.app.agents import AgentService
from services.supervisor.app.ollama_client import OllamaSupervisor


def test_shadow_record_is_never_applicable(monkeypatch):
    service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()),'http://unused')
    monkeypatch.setattr(agents,'get_audit',lambda _: {'id':'candidate','shadow_only':True,'status':'complete','evaluate_only':True,'proposal':{'changes':{'pressure_target_m':44}},'gate':{'status':'accepted'}})
    with pytest.raises(HTTPException,match='shadow'):
        asyncio.run(service.apply_record('candidate'))


def test_water_context_retains_alarm_evidence_and_age(safe_snapshot):
    from services.supervisor.app.water_alarm import build_payload
    safe_snapshot.sensors['chlorine_residual_mg_l'].timestamp=safe_snapshot.simulation_time
    payload=build_payload(safe_snapshot,{'pressure_target_m':43},{'trips':[{'code':'HIGH_LIFT_LOW_SUCTION','latched':True}]})
    context=json.loads(payload['messages'][1]['content'])
    assert context['sensors']['chlorine_residual_mg_l']['age_seconds']==0
    assert context['control_state']['trips'][0]['latched']
    assert 'operator_checks' in context


def test_diagnosis_references_must_be_grounded(safe_snapshot):
    from services.supervisor.app.water_alarm import build_payload,validate_response
    payload=build_payload(safe_snapshot,{'pressure_target_m':43},{})
    output={'actions':[],'episode_status':'escalate','confidence':.8,'reason':'Review measurements.',
            'alarm_assessment':{'alarm_codes':['MADE_UP'],'sensor_ids':[],'operator_check_ids':[]}}
    with pytest.raises(ValueError,match='reference'):
        validate_response(output,payload)


def test_benchmark_teachers_and_episode_splits_are_consistent():
    from scripts.water_alarm_benchmark import case,score
    ids=set()
    for split in ['train','valid','test']:
        for index in list(range(25))+([800,801,802,803,804,805] if split=='train' else [200,201,202,203,204,205] if split=='valid' else [500,501,502,503,504,505]):
            row=case(index,split)
            assert row['id'] not in ids;ids.add(row['id'])
            result=score(row['teacher'],row)
            assert result['correct'] and result['assessment_supported']


def test_valid_hold_does_not_pass_critical_escalation():
    from scripts.water_alarm_benchmark import case,score
    row=case(0,'test');output=dict(row['teacher']);output['episode_status']='continue'
    result=score(output,row)
    assert not result['correct'] and not result['critical_ok']


def test_acceptable_action_interval_not_one_exact_target():
    from scripts.water_alarm_benchmark import case,score
    row=case(502,'test');assert row['kind']=='adjust'
    output=dict(row['teacher']);output['actions']=[{'target':'chlorine_target_mg_l','value':row['expected']['allowed_actions'][0]['low']}]
    assert score(output,row)['correct']


def test_unapproved_candidate_is_unavailable(tmp_path,monkeypatch):
    from services.supervisor.app.water_candidate import approval
    path=tmp_path/'approval.json';path.write_text(json.dumps({'approved':True}))
    monkeypatch.setenv('WATER_ALARM_ACCEPTANCE_PATH',str(path))
    with pytest.raises(ValueError):approval()


def test_candidate_route_is_hosted_disabled(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    monkeypatch.setattr(agents,'HOSTED',True)
    service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()),'http://unused')
    app=FastAPI();app.include_router(service.router)
    response=TestClient(app).post('/api/v1/agents/water/compare-candidate',json={})
    assert response.status_code==403


@pytest.fixture
def candidate_audit_db(monkeypatch):
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


def test_water_critical_transition_disarms_inflight_proposal(candidate_audit_db,monkeypatch,safe_snapshot):
    from shared.models import ControlMode,ControlProposal,SetpointChanges,Alarm
    from services.plc_control.app.controller import BaselineController
    from services.supervisor.app.feedback import FeedbackRequest
    from services.supervisor.app import agent_audit
    controller=BaselineController();initial=controller.setpoint_dict()
    safe_snapshot.running=True;safe_snapshot.controller_mode=ControlMode.GATED_AUTO
    worker=OllamaSupervisor();service=AgentService(SimpleNamespace(ollama=worker),'http://unused')
    async def context(domain):return {'run_id':'water-run','plant':safe_snapshot.model_dump(mode='json'),'plc':{'controller_generation':'g','setpoints':controller.setpoint_dict(),'control_state':controller.status()}}
    async def enable(domain):pass
    async def baseline(domain):
        safe_snapshot.controller_mode=ControlMode.BASELINE
        controller.release_supervision()
    async def forbidden(*args,**kwargs):raise AssertionError('Late critical response reached actuation')
    monkeypatch.setattr(service,'context',context);monkeypatch.setattr(service,'enable_application',enable)
    monkeypatch.setattr(service,'baseline',baseline);monkeypatch.setattr(service,'submit',forbidden)
    async def run():
        entered=asyncio.Event();release=asyncio.Event()
        async def delayed(*args,**kwargs):
            entered.set();await release.wait()
            p=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.2),confidence=.9,expected_effect='Small increase',explanation='Captured before alarm')
            p.decision_id=agent_audit.create_audit('water',{})
            return p
        monkeypatch.setattr(worker,'propose',delayed)
        await service.feedback.start('water',FeedbackRequest())
        await service.feedback.tick();await asyncio.wait_for(entered.wait(),2)
        safe_snapshot.safety_state='critical'
        safe_snapshot.active_alarms=[Alarm(code='CHLORINE_CT',severity='critical',message='Critical CT')]
        await service.feedback.tick()
        assert not service.feedback.active
        release.set();await asyncio.gather(*list(service.tasks))
        assert controller.setpoint_dict()==initial
        record=agent_audit.list_audits()[0]
        assert record['status']=='cancelled' and not record['applied']
    asyncio.run(run())


def test_water_alarm_acknowledgement_does_not_clear_trip(safe_snapshot):
    from shared.models import Alarm
    from shared.exercise import ExerciseRecorder
    from services.plc_control.app.controller import BaselineController
    controller=BaselineController();recorder=ExerciseRecorder('water','critical-trip-test')
    safe_snapshot.sensors['pump_deadhead_pressure_kpa'].value=190
    safe_snapshot.active_alarms=[Alarm(code='PUMP_DEADHEAD',severity='critical',message='Deadhead')]
    controller.calculate(safe_snapshot)
    recorder.capture(safe_snapshot,0)
    recorder.acknowledge(recorder.active['PUMP_DEADHEAD']['occurrence'],0)
    assert controller.trip_latches['INTAKE_DEADHEAD']
    safe_snapshot.sensors['pump_deadhead_pressure_kpa'].value=0
    safe_snapshot.active_alarms=[]
    command=controller.calculate(safe_snapshot)
    assert controller.trip_latches['INTAKE_DEADHEAD'] and command.intake_pump_speed_pct==0


def test_water_waiting_and_stale_sensor_gate_remain_enforced(safe_snapshot):
    from datetime import timedelta
    from shared.models import ControlProposal,SetpointChanges
    from services.plc_control.app.controller import BaselineController,SafetyGate
    controller=BaselineController();gate=SafetyGate(controller)
    proposal=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.2),confidence=.9,expected_effect='Small increase',explanation='Test')
    for sensor in safe_snapshot.sensors.values():sensor.timestamp=safe_snapshot.simulation_time
    controller.supervisory_timing={'applied_minute':0,'observe_minutes':12,'before_targets':{},'applied_targets':{}}
    decision=gate.evaluate(proposal,safe_snapshot)
    assert decision.status=='rejected' and any('Observe' in v for v in decision.violated_constraints)
    controller.supervisory_timing=None
    safe_snapshot.sensors['chlorine_residual_mg_l'].timestamp-=timedelta(seconds=121)
    decision=gate.evaluate(proposal,safe_snapshot)
    assert decision.status=='rejected' and any('120-second' in v for v in decision.violated_constraints)


def test_candidate_comparison_preserves_state_and_both_children_are_shadow(candidate_audit_db,monkeypatch,safe_snapshot):
    from copy import deepcopy
    from shared.models import ControlProposal,SetpointChanges
    from services.plc_control.app.controller import BaselineController
    from services.supervisor.app import water_candidate,agent_audit
    controller=BaselineController()
    state={'run_id':'water','plant':safe_snapshot.model_dump(mode='json'),'plc':{'setpoints':controller.setpoint_dict(),'control_state':controller.status(),'controller_generation':'g'}}
    original=deepcopy(state);captures=[]
    async def context(domain):captures.append(domain);return deepcopy(state)
    async def propose(*args,**kwargs):
        p=ControlProposal(changes=SetpointChanges(),confidence=.9,expected_effect='Hold',explanation='Hold')
        p.decision_id=agent_audit.create_audit('water',{})
        return p
    async def candidate(frozen):
        assert frozen==original
        p=await propose();agent_audit.update_audit(p.decision_id,shadow_only=True,proposal=p.model_dump(mode='json'))
        return p,p.decision_id
    worker=OllamaSupervisor();monkeypatch.setattr(worker,'propose',propose)
    service=AgentService(SimpleNamespace(ollama=worker),'http://unused')
    monkeypatch.setattr(service,'context',context);monkeypatch.setattr(water_candidate,'approval',lambda:{})
    monkeypatch.setattr(water_candidate,'propose',candidate)
    result=asyncio.run(service.compare_candidate())
    assert state==original and captures==['water']
    assert len(result['comparison']['record_ids'])==2 and not result['comparison']['failures']
    for identifier in result['comparison']['record_ids']:
        record=agent_audit.get_audit(identifier)
        assert record['shadow_only'] and not record['applied']
        with pytest.raises(HTTPException,match='shadow'):asyncio.run(service.apply_record(identifier))


def test_invalid_schema_cannot_hide_fabricated_references():
    from scripts.water_alarm_benchmark import case,score
    row=case(0,'test');output=json.loads(json.dumps(row['teacher']))
    output['confidence']=2
    output['alarm_assessment']['alarm_codes']=['INVENTED_ALARM']
    result=score(output,row)
    assert not result['valid']
    assert result['reference_errors'] == 1


def test_evaluation_cache_rejects_changed_identity(tmp_path):
    from scripts.run_water_alarm_study import bind_artifact
    path=tmp_path/'results.jsonl'
    bind_artifact(path,{'adapter':'first'})
    path.write_text('{}\n')
    bind_artifact(path,{'adapter':'first'})
    with pytest.raises(ValueError,match='identity'):
        bind_artifact(path,{'adapter':'second'})


def test_legacy_metrics_are_not_retroactively_certified(tmp_path):
    from scripts.run_water_alarm_study import bind_artifact
    path=tmp_path/'results.jsonl';path.write_text('{}\n')
    with pytest.raises(ValueError,match='Unbound'):
        bind_artifact(path,{'adapter':'first'})


def test_candidate_rejects_unrelated_local_server():
    from services.supervisor.app.water_candidate import verify_server_identity
    report={'evaluation_identity':{'adapter_sha256':'approved'}}
    with pytest.raises(ValueError,match='identity'):
        verify_server_identity({'identity':{'adapter_sha256':'old'}},report)
    verify_server_identity({'identity':report['evaluation_identity']},report)


def test_candidate_server_rejects_browser_model_paths():
    from scripts.water_alarm_server import validate_request
    with pytest.raises(ValueError,match='model'):
        validate_request({'model':'/tmp/other-model','messages':[]},'bound-model')


def test_candidate_server_rejects_oversize_without_truncation():
    from scripts.water_alarm_server import encode_request
    class Tokenizer:
        def apply_chat_template(self,*args,**kwargs):return list(range(4096))
    with pytest.raises(ValueError,match='context'):
        encode_request(Tokenizer(),{'model':'bound-model','messages':[{'role':'user','content':'x'}]},'bound-model')


def test_benchmark_has_independent_protection_and_future_timestamp_cases():
    from scripts.water_alarm_benchmark import case
    rows=[case(i,'valid') for i in range(400)]
    contexts=[r['payload']['context'] for r in rows]
    assert any(c['emergency_stop'] and not c['alarms'] and c['safety_state']=='normal' for c in contexts)
    assert any(c['active_overrides'] and not c['alarms'] and c['safety_state']=='normal' for c in contexts)
    assert any(c['safety_state']=='critical' and not c['alarms'] and not c['emergency_stop'] and not c['active_overrides'] for c in contexts)
    assert any(c['sensors']['chlorine_residual_mg_l'] and c['sensors']['chlorine_residual_mg_l']['age_seconds']<0 for c in contexts)


def test_future_sensor_timestamp_cannot_authorize_water_control(safe_snapshot):
    from datetime import timedelta
    from shared.models import ControlProposal,SetpointChanges
    from services.plc_control.app.controller import BaselineController,SafetyGate
    for sensor in safe_snapshot.sensors.values():sensor.timestamp=safe_snapshot.simulation_time
    safe_snapshot.sensors['chlorine_residual_mg_l'].timestamp+=timedelta(seconds=1)
    proposal=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.2),confidence=.9,expected_effect='Small increase',explanation='Test')
    result=SafetyGate(BaselineController()).evaluate(proposal,safe_snapshot)
    assert result.status=='rejected' and any('future' in v for v in result.violated_constraints)


def test_training_uses_inference_template_and_masks_exact_prefix():
    from scripts.train_water_alarm_adapter import process_chat
    calls=[]
    class Tokenizer:
        def apply_chat_template(self,messages,**kwargs):
            calls.append(kwargs)
            return [1,2] if len(messages)==1 else [1,2,3]
    dataset=SimpleNamespace(tokenizer=Tokenizer(),chat_key='messages',mask_prompt=True)
    tokens,offset=process_chat(dataset,{'messages':[{'role':'user','content':'state'},{'role':'assistant','content':'{}'}]})
    assert tokens==[1,2,3] and offset==2
    assert all(c['enable_thinking'] is False and c['return_dict'] is False for c in calls)
    assert calls[-1]['add_generation_prompt'] is True
