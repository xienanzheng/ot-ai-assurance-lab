from copy import deepcopy
import pytest
from scripts.water_context_study import fresh_case, assist, typed_request, decode_choice
from scripts.water_alarm_benchmark import score


def test_fresh_balanced_episodes_and_teachers():
    rows = [fresh_case(i, 'valid', 48) for i in range(48)]
    assert len({r['seed'] for r in rows}) == 48
    assert all(r['seed'] >= 1000000 for r in rows)
    assert {k: sum(r['kind'] == k for r in rows) for k in ['critical','prerequisite','hold','adjust']} == dict.fromkeys(['critical','prerequisite','hold','adjust'], 12)
    for row in rows:
        result = score(row['teacher'], row)
        assert result['correct'] and result['assessment_supported'] and not result['reference_errors']


def test_inference_has_no_access_to_expected_answers():
    row = fresh_case(47, 'valid', 48)
    changed = deepcopy(row)
    changed['expected'] = {'secret': 'FORBIDDEN_LABEL'}
    changed['teacher'] = {'secret': 'FORBIDDEN_LABEL'}
    assert assist(row['payload']) == assist(changed['payload'])
    assert typed_request(row['payload']) == typed_request(changed['payload'])
    assert 'FORBIDDEN_LABEL' not in str(assist(changed['payload']))


def test_choices_match_each_scenario_without_being_preselected():
    for i in range(96):
        row = fresh_case(i, 'valid', 96)
        payload = assist(row['payload'])
        assert set(payload['context']['decision_support']['choices']) == {'escalate','hold','increase','decrease'}
        correct = []
        for choice in ['escalate','hold','increase','decrease']:
            proposal = decode_choice({'decision':choice,'confidence':.8}, row['payload'])
            s = score(proposal,row)
            if s['correct'] and s['assessment_supported']: correct.append(choice)
        assert len(correct) == 1, (row['id'], correct)
    with pytest.raises(ValueError):
        decode_choice({'decision':'ignore_trip','confidence':.8}, row['payload'])
    with pytest.raises(ValueError):
        decode_choice({'decision':'hold','confidence':True}, row['payload'])


def test_assistance_preserves_all_original_evidence():
    row = fresh_case(0, 'valid', 48)
    before = deepcopy(row['payload'])
    enriched = assist(row['payload'])
    assert row['payload'] == before
    for name,value in before['context'].items():
        assert enriched['context'][name] == value


def test_frozen_identity_rejects_changed_runs(tmp_path):
    from scripts.run_water_context_study import freeze, pilot_rows
    path=tmp_path/'identity.json'
    freeze(path, {'data':'first'})
    freeze(path, {'data':'first'})
    with pytest.raises(ValueError): freeze(path, {'data':'changed'})
    rows=[fresh_case(i,'valid',96) for i in range(96)]
    selected=pilot_rows(rows)
    assert len(selected)==32
    assert all(sum(r['kind']==k for r in selected)==8 for k in ['critical','prerequisite','hold','adjust'])


def test_final_audit_rejects_missing_duplicate_or_altered_evidence():
    from scripts.audit_water_context_study import audit_records
    row=fresh_case(0,'valid',48)
    record={'id':row['id'],'kind':row['kind'],'decoded':row['teacher'],
            'input':assist(row['payload']),'score':score(row['teacher'],row)}
    audit_records([record],[row],'assisted')
    with pytest.raises(ValueError):audit_records([],[row],'assisted')
    with pytest.raises(ValueError):audit_records([record,record],[row],'assisted')
    wrong=deepcopy(record);wrong['score']['correct']=False
    with pytest.raises(ValueError):audit_records([wrong],[row],'assisted')
    wrong=deepcopy(record);wrong['input']['context']['minute']+=1
    with pytest.raises(ValueError):audit_records([wrong],[row],'assisted')


def test_compact_training_target_preserves_the_reviewed_decision():
    from scripts.run_typed_water_adapter import training_target
    for i in range(96):
        row=fresh_case(i,'train',96)
        target=training_target(row)
        proposal=decode_choice(target,row['payload'])
        assessment=score(proposal,row)
        assert assessment['correct'] and assessment['assessment_supported']
        assert set(target)=={'decision','confidence'}
