import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from shared.models import ControlProposal, SetpointChanges
from shared.operations import OperationsModel, INCIDENTS
from services.infrastructure_sim.app.grid import GridSimulator
from services.infrastructure_sim.app.nuclear import NuclearSimulator
from services.plant_sim.app.simulator import WaterPlantSimulator
from services.supervisor.app.agents import AgentService, frozen_gate
from services.supervisor.app.ollama_client import OllamaSupervisor, InfrastructureProposal, OllamaUnavailable
from services.supervisor.app import agent_audit, ollama_client
from services.supervisor.app.database import Base


@pytest.mark.parametrize("domain", ["water", "nuclear", "grid"])
def test_auxiliary_command_is_atomic_and_rejects_unknown_tags(domain):
    model = OperationsModel(domain)
    before = deepcopy(model.devices)
    tag = next(iter(model.devices))
    with pytest.raises(ValueError):
        model.command({tag:{"mode":"off"},"unknown":{"mode":"run"}})
    assert model.devices == before
    for value in [float("nan"), float("inf"), True, -1, 101]:
        with pytest.raises(ValueError): model.command({tag:{"mode":"run","setpoint_pct":value}})


def test_last_water_filter_path_and_nuclear_cooling_path_cannot_be_removed():
    for domain, tags in [("water",["FT-151A","FT-151B"]),("nuclear",["CW-301A","CW-301B"])]:
        model = OperationsModel(domain)
        with pytest.raises(ValueError): model.command({tag:{"mode":"off"} for tag in tags})


def test_equipment_feedback_runtime_and_reserve_output_are_connected():
    sim=GridSimulator()
    sim.operations.command({"GT-301":{"mode":"run","setpoint_pct":100}})
    assert sim.reserve_output_mw==0
    sim.advance(1)
    assert sim.reserve_output_mw==37.5
    assert sim.operations.devices["GT-301"]["runtime_min"]==1
    sim.advance(3)
    assert sim.reserve_output_mw==150


def test_water_mixer_changes_treatment_and_emergency_stop_dominates_equipment():
    normal, changed=WaterPlantSimulator(),WaterPlantSimulator()
    changed.operations.command({"MX-111":{"mode":"off"}})
    normal.advance(5);changed.advance(5)
    assert changed.clarified_turbidity_ntu>normal.clarified_turbidity_ntu
    changed.actuators["emergency_stop"]=True
    changed.advance(1)
    assert all(d["feedback_pct"]==0 for d in changed.operations.devices.values())
    assert abs(changed.water_balance_error_m3)<1e-8


@pytest.mark.parametrize("factory,domain",[(WaterPlantSimulator,"water"),(NuclearSimulator,"nuclear"),(GridSimulator,"grid")])
def test_predefined_incidents_expire_and_do_not_stack(factory,domain):
    for incident in INCIDENTS[domain]:
        sim=factory()
        sim.operations.start_incident(incident["id"],sim.minute,10)
        with pytest.raises(ValueError):sim.operations.start_incident(incident["id"],sim.minute,10)
        sim.advance(8)
        assert sim.operations.incident
        assert sim.operations.snapshot(sim)["impact"]["equivalent_full_loss_minutes"]>=0
        sim.advance(2)
        assert sim.operations.incident is None
        json.dumps(sim.snapshot().model_dump(mode="json"),allow_nan=False)
        if domain=="nuclear" and incident["id"]=="regional_grid_disturbance":
            assert sim.controls["reactor_trip"]
            assert sim.operations.snapshot(sim)["impact"]["equivalent_accounts_affected"] is None


@pytest.mark.parametrize("factory,key,target",[(GridSimulator,"gas_dispatch_mw",480),(NuclearSimulator,"turbine_load_target_mwe",980)])
def test_ai_lease_expires_and_mode_change_releases_targets(factory,key,target):
    sim=factory();sim.controller_mode="gated_auto"
    original=sim.controls[key]
    sim.apply_ai_proposal({key:target},.9,"Bounded adjustment","Test lease")
    assert sim.controls[key]==target
    sim.advance(5)
    assert sim.controls[key]==original and sim.ai_lease is None
    sim.apply_ai_proposal({key:target},.9,"Bounded adjustment","Test lease")
    sim.command("configure",mode="baseline")
    assert sim.controls[key]==original and sim.ai_lease is None


def test_stale_or_reset_infrastructure_proposal_never_reaches_controls():
    from services.infrastructure_sim.app import main
    sim=main.grid
    sim.reset(mode="gated_auto")
    identifier=sim.exercise.run_id
    payload=dict(objective="Small change",changes={"gas_dispatch_mw":480},confidence=.9,explanation="Test stale gate",expected_run_id=identifier,expected_minute=0)
    sim.advance(6)
    before=sim.controls.copy()
    client=TestClient(main.app)
    assert client.post("/grid/proposal",json=payload).status_code==409
    assert sim.controls==before
    sim.reset(mode="gated_auto")
    assert client.post("/grid/proposal",json=payload).status_code==409


def test_water_ai_unknown_actuator_keys_are_not_silently_ignored():
    with pytest.raises(ValidationError):
        ControlProposal(changes={"raw_actuator":100},confidence=.9,expected_effect="Test",explanation="Test")


@pytest.fixture
def audit_database(monkeypatch):
    engine=create_engine("sqlite://",poolclass=StaticPool,connect_args={"check_same_thread":False})
    Base.metadata.create_all(engine)
    monkeypatch.setattr(agent_audit,"SessionLocal",sessionmaker(bind=engine))
    yield
    engine.dispose()


def fake_ollama(monkeypatch, content):
    real_client=httpx.AsyncClient
    def handler(request):
        if request.url.path=="/api/tags":return httpx.Response(200,json={"models":[{"name":"qwen3:8b","digest":"test-digest"}]})
        return httpx.Response(200,json={"model":"qwen3:8b","message":{"content":content,"thinking":"Model emitted test reasoning"},"done":True,"eval_count":12})
    monkeypatch.setattr(ollama_client.httpx,"AsyncClient",lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))


def test_reasoning_inputs_gate_and_no_actuation_are_persisted(audit_database,monkeypatch):
    content=json.dumps(dict(objective="Conserve reserve",changes={"gas_dispatch_mw":480},confidence=.9,explanation="Bounded change"))
    fake_ollama(monkeypatch,content)
    sim=GridSimulator()
    original=sim.controls.copy()
    service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()),"http://unused")
    context={"plant":sim.snapshot().model_dump(mode="json"),"run_id":sim.exercise.run_id}
    record=asyncio.run(service.cycle("grid",True,True,context))
    assert record["status"]=="complete" and not record["applied"]
    assert record["response"]["message"]["thinking"]
    assert record["request"]["think"] is True
    assert record["model_manifest"]["digest"]=="test-digest"
    assert record["gate"]["status"]=="shadow"
    assert sim.controls==original


def test_malformed_ai_output_is_recorded_with_no_gate_submission(audit_database,monkeypatch):
    fake_ollama(monkeypatch,'{"changes":{"breaker":0}}')
    with pytest.raises(OllamaUnavailable):
        asyncio.run(OllamaSupervisor().propose_infrastructure("grid",GridSimulator().snapshot().model_dump(mode="json")))
    record=agent_audit.list_audits()[0]
    assert record["status"]=="invalid_or_unavailable"
    assert record["response"]["message"]["content"]=='{"changes":{"breaker":0}}'
    assert record["gate"]["status"]=="not_submitted"


def test_frozen_gate_blocks_protection_actions_and_critical_state():
    sim=NuclearSimulator()
    context={"plant":sim.snapshot().model_dump(mode="json")}
    proposal=InfrastructureProposal(objective="Test",changes={"reactor_trip":1},confidence=.99,explanation="Boundary probe")
    assert frozen_gate("nuclear",context,proposal)["status"]=="rejected"
    assert sim.controls["reactor_trip"] is False


def test_water_lease_release_restores_manual_baseline_and_manual_preempts(safe_snapshot):
    from datetime import timedelta
    from services.plc_control.app.controller import BaselineController
    from shared.models import ControlMode
    controller=BaselineController()
    controller.apply_setpoint_changes(SetpointChanges(pressure_target_m=45),source="manual")
    controller.apply_setpoint_changes(SetpointChanges(pressure_target_m=46),safe_snapshot.simulation_time+timedelta(minutes=5))
    safe_snapshot.controller_mode=ControlMode.GATED_AUTO
    controller.calculate(safe_snapshot)
    assert controller.setpoints.pressure_target_m==46
    safe_snapshot.controller_mode=ControlMode.BASELINE
    controller.calculate(safe_snapshot)
    assert controller.setpoints.pressure_target_m==45 and controller.supervisory_expiry is None
    controller.apply_setpoint_changes(SetpointChanges(pressure_target_m=46),safe_snapshot.simulation_time+timedelta(minutes=5))
    controller.apply_setpoint_changes(SetpointChanges(chlorine_target_mg_l=1.3),source="manual")
    assert controller.setpoints.pressure_target_m==45 and controller.setpoints.chlorine_target_mg_l==1.3
    assert controller.supervisory_expiry is None


def test_water_proposal_endpoint_requires_mode_and_fresh_controller(monkeypatch,safe_snapshot):
    from services.plc_control.app import main
    async def snapshot():return safe_snapshot
    monkeypatch.setattr(main,"fetch_snapshot",snapshot)
    client=TestClient(main.app)
    proposal=ControlProposal(changes=SetpointChanges(),confidence=.9,expected_effect="Maintain",explanation="Maintain baseline").model_dump(mode="json")
    assert client.post("/proposal?apply=true",json=proposal).status_code==409
    assert client.post("/proposal?expected_controller_generation=obsolete",json=proposal).status_code==409


def test_condensate_standby_starts_when_duty_requested_below_permissive():
    sim=NuclearSimulator()
    sim.operations.command({"CP-201A":{"mode":"run","setpoint_pct":0}})
    sim.advance(4)
    assert sim.operations.fraction("CP-201B")==1


@pytest.mark.parametrize("kind",["label_invariance","safety_priority"])
def test_paired_study_holds_physical_inputs_fixed_and_never_actuates(kind,audit_database,monkeypatch):
    content=json.dumps(dict(objective="Maintain reserve",changes={"gas_dispatch_mw":480},confidence=.9,explanation="Bounded request"))
    fake_ollama(monkeypatch,content)
    sim=GridSimulator();before=sim.snapshot().model_dump(mode="json")
    service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()),"http://unused")
    async def context(domain):return {"plant":deepcopy(before),"run_id":sim.exercise.run_id}
    monkeypatch.setattr(service,"context",context)
    result=asyncio.run(service.study("grid",kind,False))
    assert result["study"]["sample_size"]==2 and result["study"]["actuation_count"]==0
    records=[agent_audit.get_audit(identifier) for identifier in result["study"]["variant_record_ids"]]
    inputs=[json.loads(r["request"]["messages"][1]["content"]) for r in records]
    assert inputs[0].pop("research_context")!=inputs[1].pop("research_context")
    assert inputs[0]==inputs[1]
    assert sim.snapshot().model_dump(mode="json")==before
    if kind=="safety_priority":assert result["study"]["rejected_count"]==2


def test_instructor_incident_can_be_injected_without_starting_clock():
    from services.infrastructure_sim.app import main
    main.grid.reset()
    client=TestClient(main.app)
    response=client.post('/grid/operations',json={'action':'incident','incident_id':'regional_supply_shortfall','start_running':False})
    assert response.status_code==200
    assert main.grid.minute==0 and main.grid.running is False
    assert main.grid.operations.incident
    main.grid.advance(10)
    assert main.grid.minute==10
    main.grid.reset()


def test_worker_profile_overrides_do_not_mutate_scheduled_worker(audit_database,monkeypatch):
    from services.supervisor.app.agents import AgentRequest
    with pytest.raises(ValidationError):AgentRequest(num_ctx=1000000)
    content=json.dumps(dict(objective='Observe',changes={},confidence=.9,explanation='No change'))
    fake_ollama(monkeypatch,content)
    original=OllamaSupervisor();service=AgentService(SimpleNamespace(ollama=original),'http://unused')
    sim=GridSimulator();context={'plant':sim.snapshot().model_dump(mode='json'),'run_id':sim.exercise.run_id}
    record=asyncio.run(service.cycle('grid',True,True,context,model='waterlab-grid:latest',num_ctx=16384))
    assert record['request']['model']=='waterlab-grid:latest'
    assert record['request']['options']['num_ctx']==16384
    assert original.model=='qwen3:8b' and original.num_ctx==8192
    assert record['applied'] is False


def test_failed_live_exchange_keeps_context_for_next_decision(audit_database,monkeypatch):
    fake_ollama(monkeypatch,'not valid JSON')
    sim=GridSimulator()
    context={'plant':sim.snapshot().model_dump(mode='json'),'run_id':sim.exercise.run_id}
    service=AgentService(SimpleNamespace(ollama=OllamaSupervisor()),'http://unused')
    with pytest.raises(OllamaUnavailable):
        asyncio.run(service.cycle('grid',True,False,context))
    record=agent_audit.list_audits()[0]
    assert record['before']==context
    assert record['evaluate_only'] is False and record['applied'] is False
    assert record['gate']['status']=='not_submitted'
