from collections import Counter
import json
import pytest
from training.bench_cases import generate_cases, freeze_dataset, verify_dataset, state_fingerprint


def test_exact_balance_determinism_and_no_leakage():
    data=generate_cases();assert data==generate_cases()
    episodes=set();fingerprints=set()
    for split,n in [('train',384),('validation',48),('test',96)]:
        cases=data[split];assert len(cases)==n
        assert Counter(c['expected']['status'] for c in cases)=={'hold':n//3,'adjust':n//3,'escalate':n//3}
        assert Counter(c['domain'] for c in cases)=={'water':n//2,'cooling':n//2}
        for c in cases:
            assert c['episode_id'] not in episodes;episodes.add(c['episode_id'])
            fp=state_fingerprint(c['context']);assert fp not in fingerprints;fingerprints.add(fp)
    assert any(c['scenario']=='combined_fault' for c in data['test'])
    assert not any(c['scenario']=='combined_fault' for c in data['train'])


def test_frozen_artifacts_refuse_collision_and_detect_tampering(tmp_path):
    out=tmp_path/'frozen';manifest=freeze_dataset(out)
    assert verify_dataset(out)==manifest
    with pytest.raises(FileExistsError):freeze_dataset(out)
    path=out/'train.jsonl';path.write_text(path.read_text()+'\n')
    with pytest.raises(ValueError):verify_dataset(out)


def test_missing_sensor_and_misleading_prose_are_preserved():
    data=generate_cases()
    assert any(c['scenario']=='missing' for c in data['train'])
    c=next(c for c in data['test'] if c['scenario']=='combined_fault')
    assert c['context']['snapshot']['wait_until']>100
    assert c['expected']['reason_code']=='protection'


def test_generated_captures_retain_production_prerequisite_evidence():
    data=generate_cases()
    for scenario in ('stale','bad','unit','no_flow','missing'):
        c=next(c for c in data['train'] if c['scenario']==scenario)
        assert c['context']['eligibility'], scenario
