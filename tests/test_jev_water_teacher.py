import pytest
from scripts.water_alarm_benchmark import case
from scripts.collect_jev_water_teacher import request_for,normalize


def test_teacher_collection_never_accepts_locked_test_or_validation():
    for split in ['valid','test']:
        with pytest.raises(ValueError,match='training'):request_for(case(0,split))


def test_teacher_request_does_not_leak_expected_labels():
    row=case(0,'train');payload,controls=request_for(row)
    assert payload['state']==row['payload']['context']
    assert 'expected' not in payload['state'] and 'teacher' not in payload['state']
    assert controls['hold']==[]


def test_teacher_normalization_preserves_contradictory_controls_for_scoring():
    payload,controls=request_for(case(0,'train'))
    choices={'disposition':'escalate','control':'increase','alarm':'none','sensor':'none','check':'review_protection'}
    response={'answers':{k:{'type':'choice','choice':v,'confidence':.9} for k,v in choices.items()}}
    proposal,_=normalize(response,payload,controls)
    assert proposal['episode_status']=='escalate' and proposal['actions']


def test_joint_jev_bundle_is_code_grounded_and_training_only():
    from scripts.collect_jev_water_bundles import request_for
    payload,options=request_for(case(3,'train'))
    assert options['escalate']['actions']==[]
    assert options['escalate']['alarm_assessment']['operator_check_ids']==['verify_treatment']
    assert set(payload['questions'])=={'decision'}
    with pytest.raises(ValueError):request_for(case(3,'test'))
