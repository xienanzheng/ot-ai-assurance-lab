from copy import deepcopy
import json
from services.supervisor.app.inference_profiles import compact_context, column_history, unpack_history, apply_profile
from shared.models import ControlProposal


def test_history_compaction_is_lossless_including_quality_transitions():
    rows=[{'minute':i,'values':{'ph':7-i*.1,'pressure':42},'quality':{'ph':'good' if i<3 else 'stale'},
           'setpoints':{'pressure':44,'chlorine':1.15},'alarms':[] if i<3 else ['quality']} for i in range(6)]
    packed=column_history(rows)
    assert unpack_history(packed)==rows
    assert len(json.dumps(packed))<len(json.dumps(rows))


def test_fast_context_preserves_live_constraints_and_source_input():
    state={'sensor_values':{'ph':[7,'pH','stale']},'operating_limits':{'ph':[6,8]},
        'allowed_target_ranges':{'ph':[6.5,7.5]},'plc_control_state':{'trips':[{'latched':True}]}}
    before=deepcopy(state)
    assert compact_context(state)==state
    assert state==before


def test_fast_schema_keeps_required_actions_but_omits_server_fields():
    payload={'think':True,'options':{'num_predict':2048},'format':ControlProposal.model_json_schema(),
             'messages':[{'role':'system','content':'Respect limits.'},{'role':'user','content':'{}'}]}
    result=apply_profile(payload,'water','fast')
    assert result['think'] is False and payload['think'] is True
    assert result['options']['num_predict']==192
    assert 'decision_id' not in result['format']['properties']
    assert 'actions' in result['format']['required']
    assert result['_inference_profile']['profile']=='fast'


def test_sparse_actions_validate_before_conversion_to_existing_gate_proposal():
    import pytest
    from services.supervisor.app.inference_profiles import normalize_fast_response
    payload={'think':False,'options':{},'format':ControlProposal.model_json_schema(),
             'messages':[{'role':'system','content':'Respect limits.'},{'role':'user','content':'{}'}]}
    wire=apply_profile(payload,'water','fast')
    body={'actions':[],'confidence':.8,'reason':'Hold targets.','episode_status':'continue'}
    assert normalize_fast_response(json.dumps(body),wire,'water')['changes']=={}
    body['actions']=[{'target':'pressure_target_m','value':43}]
    assert normalize_fast_response(json.dumps(body),wire,'water')['changes']=={'pressure_target_m':43}
    for actions in [[{'target':'unknown','value':1}],body['actions']*2,
                    [{'target':'pressure_target_m','value':True}],body['actions']*3]:
        with pytest.raises(ValueError):normalize_fast_response(json.dumps({**body,'actions':actions}),wire,'water')


def test_water_fast_keeps_every_gate_sensor_and_bad_auxiliary_reading():
    from services.plant_sim.app.simulator import WaterPlantSimulator
    from services.plc_control.app.controller import SafetyGate
    from shared.limits import SETPOINT_LIMITS
    snap=WaterPlantSimulator().snapshot()
    state={'sensor_values':{k:[v.value,v.unit,v.quality] for k,v in snap.sensors.items()},
           'allowed_target_ranges':SETPOINT_LIMITS}
    state['sensor_values']['aux_test']=[3,'pct','stale']
    slim=compact_context(state,'water')
    assert SafetyGate._dependencies(set(SETPOINT_LIMITS)) <= slim['sensor_values'].keys()
    assert slim['sensor_values']['aux_test']==[3,'pct','stale']
    for key,row in slim['sensor_values'].items(): assert row==state['sensor_values'][key]


def test_fast_schema_does_not_relax_existing_control_validation():
    import pytest
    from services.supervisor.app.inference_profiles import normalize_fast_response
    payload={'think':False,'options':{},'format':ControlProposal.model_json_schema(),
             'messages':[{'role':'system','content':'Respect limits.'},{'role':'user','content':'{}'}]}
    wire=apply_profile(payload,'water','fast')
    body={'actions':[{'target':'pressure_target_m','value':999}], 'confidence':.9,'reason':'Test limit.', 'episode_status':'continue'}
    normalized=normalize_fast_response(json.dumps(body),wire,'water')
    proposal=ControlProposal.model_validate(normalized)
    from services.plant_sim.app.simulator import WaterPlantSimulator
    from services.plc_control.app.controller import SafetyGate,BaselineController
    assert SafetyGate(BaselineController()).evaluate(proposal,WaterPlantSimulator().snapshot()).status=='rejected'
