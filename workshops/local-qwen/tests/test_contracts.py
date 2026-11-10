import time
import pytest
from pydantic import ValidationError
from v2.contracts import Measurement, Proposal, Snapshot
from v2.packages import load_package, check_snapshot


def snapshot(name='water', **changes):
    p = load_package(name)
    now = time.time()
    s = Snapshot(site='bench', package_hash=p.fingerprint(), generation='g', sequence=1,
        source_time=now, process_time=0, target=p.initial_target, armed=True,
        readings={p.sensor: Measurement(value=p.initial_value, unit=p.unit, source_time=now),
                  'flow': Measurement(value=1, unit='L/s', source_time=now)})
    return s.model_copy(update=changes)


def test_package_registry_cannot_load_browser_paths():
    with pytest.raises(ValueError): load_package('../water')


def test_missing_quality_age_and_unit_are_gate_inputs():
    p = load_package('water'); s = snapshot()
    assert check_snapshot(p, s, time.time()) == []
    for change, expected in [({'quality':'bad'}, 'quality'), ({'unit':'degC'}, 'unit'),
                             ({'source_time':time.time()-20}, 'stale'),
                             ({'source_time':time.time()+20}, 'future')]:
        readings = dict(s.readings)
        readings[p.sensor] = readings[p.sensor].model_copy(update=change)
        assert any(expected in r for r in check_snapshot(p, s.model_copy(update={'readings':readings}), time.time()))
    assert check_snapshot(p, s.model_copy(update={'readings':{}}), time.time())


def test_nonfinite_and_extra_fields_never_enter_contract():
    with pytest.raises(ValidationError): Measurement(value=float('nan'), unit='x', source_time=time.time())
    with pytest.raises(ValidationError): Proposal(status='adjust', target=1, rationale='x', bypass=True)


def test_critical_measurement_blocks_even_when_alarm_flag_is_clear():
    p=load_package('water'); s=snapshot(); readings=dict(s.readings)
    readings[p.sensor]=readings[p.sensor].model_copy(update={'value':p.critical_limits[1]})
    assert not s.critical
    assert any('critical' in reason for reason in check_snapshot(p,s.model_copy(update={'readings':readings}),time.time()))


def test_package_semantics_do_not_leak():
    water, cooling = load_package('water'), load_package('cooling')
    assert water.sensor == 'chlorine_residual'
    assert cooling.sensor == 'supply_temperature'
    assert 'chlorine' not in cooling.model_dump_json().lower()
    assert water.fingerprint() != cooling.fingerprint()
    assert check_snapshot(cooling, snapshot(), time.time())


def test_admin_registry_adds_supported_instance_without_core_edits(tmp_path,monkeypatch):
    import json
    import v2.packages as module
    package=load_package('cooling').model_dump()
    package.update(id='cooling_room_b',title='Cooling room B',initial_value=13)
    (tmp_path/'room.json').write_text(json.dumps(package))
    (tmp_path/'registry.json').write_text(json.dumps({'schema_version':'1','packages':{'cooling_room_b':'room.json'}}))
    monkeypatch.setattr(module,'ROOT',tmp_path)
    assert module.load_package('cooling_room_b').initial_value==13
    (tmp_path/'registry.json').write_text(json.dumps({'schema_version':'1','packages':{'bad':'../outside.json'}}))
    with pytest.raises(ValueError):module.load_package('bad')
