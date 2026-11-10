import time
from uuid import uuid4
import pytest
from v2.contracts import CommandRequest, Proposal, AuditResult, digest
from v2.packages import load_package
from v2.controller import Controller
from v2.journal import Journal


def setup(name='water', journal=None):
    c=Controller(load_package(name),journal or Journal('sqlite://'))
    c.arm('off')
    return c


def request(c, target=1.0, **kw):
    now=time.time()
    return CommandRequest(id=str(uuid4()),snapshot=c.snapshot(),proposal=Proposal(status='adjust',target=target,rationale='Reduce elevated reading',evidence=[c.package.sensor]),issued_at=now,expires_at=now+30,**kw)


def test_target_acceptance_does_not_instantly_change_sensor():
    c=setup(); r=request(c)
    assert c.apply(r)['status']=='applied'
    assert c.snapshot().target==1.0
    assert c.snapshot().readings['chlorine_residual'].value==1.4
    c.step(60)
    assert 1.0<c.snapshot().readings['chlorine_residual'].value<1.4
    assert c.apply(request(c,.9))['status']=='rejected'


def test_duplicate_and_modified_id_cannot_apply_twice():
    c=setup(); r=request(c); first=c.apply(r)
    assert c.apply(r)==first
    bad=r.model_copy(update={'proposal':r.proposal.model_copy(update={'target':.9})})
    assert c.apply(bad)['reason']=='command ID payload mismatch'


@pytest.mark.parametrize('fault',['critical','no_flow','bad_sensor','stale_sensor','override'])
def test_protection_blocks_adjustment(fault):
    c=setup(); r=request(c); c.inject(fault)
    assert c.apply(r)['status']=='rejected'
    assert c.snapshot().target==1.2


def test_acknowledge_does_not_clear_trip():
    c=setup(); c.inject('critical'); c.inject('normal')
    assert not c.snapshot().critical
    assert c.snapshot().trip_latched
    assert c.apply(request(c))['status']=='rejected'


def test_takeover_and_restart_invalidate_late_request(tmp_path):
    journal=Journal('sqlite:///'+str(tmp_path/'journal.db'))
    c=setup(journal=journal); r=request(c); c.stop()
    assert c.apply(r)['status']=='rejected'
    c.arm('off'); r=request(c)
    new=Controller(c.package,journal)
    assert not new.snapshot().armed
    new.arm('off')
    assert new.apply(r)['status']=='rejected'


def test_limits_and_expiry():
    c=setup()
    assert c.apply(request(c,.6))['status']=='rejected'
    r=request(c); assert c.apply(r.model_copy(update={'expires_at':time.time()-1}))['status']=='rejected'
    c.apply(request(c,1.0)); c.step(120)
    assert c.apply(request(c,.8))['status']=='applied'
    c.step(120)
    assert c.apply(request(c,.6))['status']=='rejected'


def test_required_audit_binds_to_captured_input_and_policy():
    c=setup(); c.arm('required')
    assert c.apply(request(c))['status']=='rejected'
    r=request(c,policy='required')
    assert c.apply(r)['status']=='rejected'
    r=request(c,policy='required')
    audit=AuditResult(status='passed',reason='Supported',proposal_hash=digest({'snapshot':r.snapshot.model_dump(),'proposal':r.proposal.model_dump()}))
    assert c.apply(r.model_copy(update={'audit':audit}))['status']=='applied'


def test_journal_failure_does_not_change_target():
    c=setup(); r=request(c)
    def fail(*args): raise OSError('disk unavailable')
    c.journal.put_many=fail
    with pytest.raises(OSError): c.apply(r)
    assert c.snapshot().target==1.2


def test_cooling_uses_same_controller():
    c=setup('cooling')
    assert c.apply(request(c,11))['status']=='applied'
    c.step(60)
    assert 11<c.snapshot().readings['supply_temperature'].value<14


def test_lease_expiry_holds_target_and_disarms():
    c=setup(); c.apply(request(c)); c.step(301)
    assert not c.snapshot().armed
    assert c.snapshot().target==1.0


def test_rearm_clears_expired_lease():
    c=setup(); c.apply(request(c)); c.step(301); c.arm(); c.step(1)
    assert c.snapshot().armed


def test_snapshot_age_does_not_refresh_without_process_scan():
    c=setup(); first=c.snapshot(); time.sleep(.02); second=c.snapshot()
    assert second.source_time==first.source_time


def test_bounded_slow_proposal_revalidates_current_fresh_evidence():
    c=setup(); r=request(c); now=time.time()
    old=r.snapshot.model_copy(update={'source_time':now-10,'readings':{k:v.model_copy(update={'source_time':now-10}) for k,v in r.snapshot.readings.items()}})
    r=r.model_copy(update={'snapshot':old})
    assert c.apply(r)['status']=='applied'
    c=setup(); r=request(c)
    old=r.snapshot.model_copy(update={'source_time':now-40})
    assert c.apply(r.model_copy(update={'snapshot':old}))['status']=='rejected'
