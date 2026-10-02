from datetime import timedelta
from services.plant_sim.app.scenarios import SCENARIOS,scenario_modifiers
from services.plant_sim.app.simulator import WaterPlantSimulator
from services.plc_control.app.controller import BaselineController,SafetyGate
from services.supervisor.app.sop_context import select_sops
from shared.models import ControlMode,ControlProposal,SetpointChanges


def test_efficiency_demo_is_a_normal_physics_objective_not_an_override():
    assert 'chlorine_efficiency_trim' in SCENARIOS
    assert scenario_modifiers(15,'chlorine_efficiency_trim')==scenario_modifiers(15,'normal_day')
    context=select_sops('water',{'scenario':'chlorine_efficiency_trim','sensors':{}})
    assert context['operating_objective']['residual_band_mg_l']==[.9,1.0]
    assert context['procedures'][0]['id']=='water.disinfection'


def test_bounded_trim_passes_gate_has_delayed_benefit_and_expires():
    results=[]
    for apply in (False,True):
        sim=WaterPlantSimulator();sim.reset(scenario='chlorine_efficiency_trim');sim.controller_mode=ControlMode.GATED_AUTO
        plc=BaselineController();rows=[];chemical=0
        for minute in range(31):
            snapshot=sim.snapshot()
            assert snapshot.safety_state!='critical' and not snapshot.active_injections
            if minute==15 and apply:
                proposal=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.025),confidence=.9,expected_effect='Trim residual',explanation='Reduce excess residual while preserving CT')
                gate=SafetyGate(plc).evaluate(proposal,snapshot)
                assert gate.status=='accepted'
                previous=sim.true_chlorine_mg_l
                plc.apply_setpoint_changes(gate.applied_values,valid_until=snapshot.simulation_time+timedelta(minutes=14))
                assert sim.true_chlorine_mg_l==previous  # Target changes are not instant sensor changes.
            if minute==27:rows=[sim.true_chlorine_mg_l,sim.chlorine_ct_mg_min_l,chemical]
            if minute==30:
                assert plc.setpoints.chlorine_target_mg_l==1.15
                break
            sim.set_actuators(plc.calculate(snapshot).model_dump(exclude_none=True));sim.advance(1)
            if 15<=minute<27:chemical+=sim.actual_chlorine_dose_mg_l*sim.raw_flow_m3h/60
        results.append(rows)
    baseline,trim=results
    assert .9<=trim[0]<=1.0
    assert trim[1]>=20
    assert trim[2]<baseline[2]
    assert abs(trim[0]-.95)<abs(baseline[0]-.95)


def test_objective_evidence_is_computed_from_measurements_not_assumed(safe_snapshot):
    snapshot=safe_snapshot.model_dump(mode='json');snapshot['scenario']='chlorine_efficiency_trim'
    objective=select_sops('water',snapshot)['operating_objective']
    assert objective['observed_residual_mg_l']==1.15
    assert objective['position']=='above_objective'
    snapshot['sensors']['chlorine_residual_mg_l']['value']=.95
    assert select_sops('water',snapshot)['operating_objective']['position']=='within_objective'
    snapshot['sensors']['chlorine_residual_mg_l']['quality']='bad'
    assert select_sops('water',snapshot)['operating_objective']['position']=='unreliable_measurement'


def test_jev_objective_choices_are_focused_and_use_actual_loop_timing(safe_snapshot):
    from dataclasses import asdict
    from services.supervisor.app.jev_client import candidates
    state=safe_snapshot.model_dump(mode='json');state['scenario']='chlorine_efficiency_trim'
    context={'plant':state,'plc':{'setpoints':asdict(BaselineController().setpoints)}}
    options=candidates('water',context,adaptive_timing=True)
    assert set(options)=={'hold','review','decrease_chlorine_target_mg_l','increase_chlorine_target_mg_l'}
    trim=options['decrease_chlorine_target_mg_l']
    assert trim['changes']=={'chlorine_target_mg_l':1.025}
    assert trim['observe_minutes']==12 and trim['lease_minutes']==14
    assert '14 simulated minutes' in trim['description']
    manual=candidates('water',context)
    assert manual['decrease_chlorine_target_mg_l']['lease_minutes']==5
    state['scenario']='normal_day'
    assert 'decrease_pressure_target_m' in candidates('water',context)


def test_water_exercise_catalog_separates_process_and_efficiency_limits():
    from services.plant_sim.app.scenarios import scenario_list
    from shared.limits import LIMITS
    catalog={x['id']:x for x in scenario_list()}
    chlorine=catalog['chlorine_efficiency_trim']['objective']
    assert chlorine['operating_band']==list(LIMITS['chlorine_residual_mg_l'])
    assert chlorine['operating_band'][0]<1.15<chlorine['operating_band'][1]
    assert chlorine['optimization_band']==select_sops('water',{'scenario':'chlorine_efficiency_trim'})['operating_objective']['residual_band_mg_l']
    turbidity=catalog['gradual_turbidity_rise']['objective']
    assert turbidity['signal']=='filtered_turbidity_ntu' and turbidity['operating_band']==[0,1]
    assert 'optimization_band' not in turbidity


def test_overdose_exercise_uses_existing_fault_and_cannot_be_fixed_by_ai_target():
    sim=WaterPlantSimulator();sim.reset(scenario='chlorine_overdose');sim.controller_mode=ControlMode.GATED_AUTO
    plc=BaselineController()
    for minute in range(11):
        snapshot=sim.snapshot()
        if minute < 10:
            assert 'chlorine_overfeed' not in snapshot.active_injections
        else:
            assert 'chlorine_overfeed' in snapshot.active_injections
            assert snapshot.safety_state == 'critical'
            proposal=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.0),confidence=.99,expected_effect='Lower residual',explanation='Lower target')
            gate=SafetyGate(plc).evaluate(proposal,snapshot)
            assert gate.status == 'rejected'
            assert 'Plant is in a critical state' in gate.violated_constraints
            break
        sim.set_actuators(plc.calculate(snapshot).model_dump(exclude_none=True));sim.advance(1)
    sim.clear_injections();sim.advance(1)
    assert 'chlorine_overfeed' not in sim.active_injections()
    sim.reset(scenario='chlorine_efficiency_trim')
    assert not sim.active_injections()


def test_chlorine_high_alarm_boundaries_and_recovery():
    sim=WaterPlantSimulator();sim.reset(scenario='chlorine_efficiency_trim')
    for value,severity in [(1.499,None),(1.5,'warning'),(1.999,'warning'),(2.0,'critical'),(1.8,'warning'),(1.49,None),(.1,'critical')]:
        sim.true_chlorine_mg_l=value
        snapshot=sim.snapshot()
        alarms=[a for a in snapshot.active_alarms if a.code=='CHLORINE_RESIDUAL']
        assert [a.severity for a in alarms]==([] if severity is None else [severity])
        if severity:assert snapshot.safety_state==severity


def test_chlorine_yellow_allows_bounded_reduction_but_red_blocks_actuation():
    sim=WaterPlantSimulator();sim.reset(scenario='chlorine_efficiency_trim');sim.controller_mode=ControlMode.GATED_AUTO
    plc=BaselineController()
    proposal=ControlProposal(changes=SetpointChanges(chlorine_target_mg_l=1.05),confidence=.9,expected_effect='Lower residual',explanation='Observe a bounded reduction')
    sim.true_chlorine_mg_l=1.5
    assert SafetyGate(plc).evaluate(proposal,sim.snapshot()).status=='accepted'
    sim.true_chlorine_mg_l=2.0
    result=SafetyGate(plc).evaluate(proposal,sim.snapshot())
    assert result.status=='rejected' and 'Plant is in a critical state' in result.violated_constraints


def test_alarm_thresholds_are_shared_by_exercise_display_and_model_context():
    from services.plant_sim.app.scenarios import scenario_list
    catalog={s['id']:s for s in scenario_list()}
    for scenario in ('chlorine_efficiency_trim','chlorine_overdose'):
        thresholds=catalog[scenario]['objective']['alarm_thresholds']
        assert thresholds['warning_high_mg_l']==1.5 and thresholds['critical_high_mg_l']==2.0
        assert select_sops('water',{'scenario':scenario})['alarm_thresholds']==thresholds
