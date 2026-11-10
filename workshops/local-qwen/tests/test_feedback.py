import asyncio
import pytest
from v2.controller import Controller
from v2.journal import Journal
from v2.packages import load_package
from v2.providers import FixtureProvider
from v2.supervisor import Supervisor


class LocalReceiver:
    def __init__(self,c): self.c=c
    async def apply(self,r): return self.c.apply(r)
    async def status(self,id): return self.c.status(id)
    async def snapshot(self): return self.c.snapshot()
    async def stop(self): return self.c.stop()
    async def arm(self,p): return self.c.arm(p)


def setup():
    p=load_package('water'); j=Journal('sqlite://'); c=Controller(p,j)
    s=Supervisor(p,j,LocalReceiver(c),{'fixture':FixtureProvider()},FixtureProvider())
    return c,s


async def test_analysis_applies_and_records_exact_evidence():
    c,s=setup(); await s.arm('off'); await s.observe(c.snapshot())
    r=await s.analyse('fixture',True)
    assert r['command']['actually_applied']
    assert r['audit'] is None
    assert c.snapshot().target==1.0
    assert r['input']['snapshot']['target']==1.2
    assert r['readback']['target']==1.0
    c.step(120); await s.observe(c.snapshot()); c.step(31); await s.observe(c.snapshot())
    assert s.records()[0]['outcome']['status']=='completed'


async def test_slow_proposal_is_disarmed_by_critical_transition():
    c,s=setup(); await s.arm('off'); await s.observe(c.snapshot())
    entered=asyncio.Event(); release=asyncio.Event()
    class Slow(FixtureProvider):
        async def decide(self,context):
            entered.set(); await release.wait(); return await super().decide(context)
    s.providers['slow']=Slow()
    task=asyncio.create_task(s.analyse('slow',True)); await entered.wait()
    c.inject('critical'); await s.observe(c.snapshot()); release.set()
    r=await task
    assert not (r.get('command') or {}).get('actually_applied',False)
    assert c.snapshot().target==1.2
    assert not s.feedback['active']


async def test_required_audit_flag_blocks_application():
    c,s=setup(); await s.arm('required'); await s.observe(c.snapshot())
    class Flag(FixtureProvider):
        async def audit(self,context,proposal):
            result=await super().audit(context,proposal)
            return result.model_copy(update={'status':'flagged','reason':'Missing corroborating evidence'})
    s.auditor=Flag()
    r=await s.analyse('fixture',True)
    assert r['audit']['status']=='flagged'
    assert c.snapshot().target==1.2


async def test_failure_is_not_disguised_as_a_model_decision():
    c,s=setup(); await s.observe(c.snapshot())
    class Broken(FixtureProvider):
        async def decide(self,context): raise RuntimeError('model unavailable')
    s.providers['broken']=Broken()
    r=await s.analyse('broken',False)
    assert r['status']=='inference_failed'
    assert r['proposal'] is None
    assert s.latest is not None


async def test_feedback_budget_is_bounded():
    c,s=setup(); await s.observe(c.snapshot())
    s.start_feedback('fixture',1,False)
    await s.feedback_tick()
    await s.feedback_tick()
    assert s.feedback['calls']==1
    assert not s.feedback['active']
    assert len(s.records())==1


async def test_arm_invalidates_previous_capture_until_new_telemetry_arrives():
    c,s=setup(); await s.observe(c.snapshot())
    await s.arm('off')
    assert s.latest is None
    with pytest.raises(ValueError,match='No captured snapshot'):
        await s.analyse('fixture',True)


async def test_initial_journal_error_releases_analysis_owner():
    c,s=setup(); await s.observe(c.snapshot()); original=s.journal.put_many
    def fail(entries): raise OSError('storage offline')
    s.journal.put_many=fail
    with pytest.raises(OSError): await s.analyse('fixture',False)
    s.journal.put_many=original
    assert not s.busy
    assert (await s.analyse('fixture',False))['status']=='evaluated'


async def test_durable_submitting_blocks_new_work():
    c,s=setup(); await s.arm('off'); await s.observe(c.snapshot())
    original=s.save
    def fail_after_apply(record):
        if record['status']=='applied': raise OSError('commit outcome failed')
        return original(record)
    s.save=fail_after_apply
    with pytest.raises(OSError): await s.analyse('fixture',True)
    s.save=original; c.step(120); await s.observe(c.snapshot())
    assert s.records()[0]['status']=='submitting'
    with pytest.raises(ValueError,match='[Uu]nresolved|[Rr]econcile'): await s.analyse('fixture',True)


async def test_stop_fences_pending_arm():
    c,s=setup(); entered=asyncio.Event(); release=asyncio.Event()
    original=s.receiver.arm
    async def delayed(policy):
        entered.set(); await release.wait(); return await original(policy)
    s.receiver.arm=delayed
    task=asyncio.create_task(s.arm('off')); await entered.wait(); await s.stop(); release.set()
    with pytest.raises(ValueError): await task
    assert not c.snapshot().armed


async def test_later_adjustment_cannot_claim_recovery_for_earlier_one():
    c,s=setup(); c.inject('drift'); await s.arm('off'); await s.observe(c.snapshot())
    first=await s.analyse('fixture',True)
    c.step(91); await s.observe(c.snapshot()); await s.analyse('fixture',True)
    c.step(120); await s.observe(c.snapshot()); c.step(31); await s.observe(c.snapshot())
    old=s.journal.get('record:'+first['id'])
    assert old['outcome']['status']=='superseded'
    assert s.records()[0]['outcome']['status']=='completed'


async def test_mismatched_acknowledgement_becomes_unknown():
    c,s=setup(); await s.arm('off'); await s.observe(c.snapshot())
    original=s.receiver.apply
    async def bad(request):
        r=await original(request); r['id']='different'; return r
    s.receiver.apply=bad
    r=await s.analyse('fixture',True)
    assert r['status']=='unknown'
    assert r['outcome'] is None


async def test_cooling_context_excludes_water_decisions():
    c,s=setup(); await s.observe(c.snapshot()); await s.analyse('fixture',False)
    cool=Supervisor(load_package('cooling'),s.journal,s.receiver,s.providers,s.auditor)
    cc=Controller(cool.package,s.journal)
    assert cool.context(cc.snapshot())['recent_decisions']==[]


async def test_cooling_uses_same_core_for_gradual_recovery():
    p=load_package('cooling'); j=Journal('sqlite://'); c=Controller(p,j)
    s=Supervisor(p,j,LocalReceiver(c),{'fixture':FixtureProvider()},FixtureProvider())
    await s.arm('off'); await s.observe(c.snapshot())
    r=await s.analyse('fixture',True)
    assert r['command']['accepted_target']==11
    assert c.snapshot().readings[p.sensor].value==14
    c.step(120); await s.observe(c.snapshot())
    c.step(31); await s.observe(c.snapshot())
    assert s.records()[0]['outcome']['status']=='completed'


async def test_reset_generation_excludes_old_decisions_from_context():
    c,s=setup(); await s.observe(c.snapshot()); await s.analyse('fixture',False)
    c.reset()
    assert s.context(c.snapshot())['recent_decisions']==[]


async def test_context_excludes_observations_from_an_old_generation():
    c,s=setup(); c.inject('critical'); await s.observe(c.snapshot())
    c.reset(); await s.observe(c.snapshot())
    history=s.context(c.snapshot())['recent_observations']
    assert len(history)==1
    assert not history[0]['critical']


async def test_context_distinguishes_observation_duration_from_active_wait():
    c,s=setup(); await s.arm('off'); await s.observe(c.snapshot())
    facts=s.context(c.snapshot())['current_facts']
    assert facts['measurement_relative_to_objective']=='above'
    assert facts['observation_remaining_seconds']==0
    assert facts['observation_active'] is False
    await s.analyse('fixture',True)
    facts=s.context(c.snapshot())['current_facts']
    assert facts['observation_active'] is True
    assert facts['observation_remaining_seconds']==90


async def test_observe_audit_flag_does_not_reverse_accepted_target():
    c,s=setup(); await s.arm('observe'); await s.observe(c.snapshot())
    class Flag(FixtureProvider):
        async def audit(self,context,proposal):
            r=await super().audit(context,proposal)
            return r.model_copy(update={'status':'flagged','reason':'Review this adjustment'})
    s.auditor=Flag(); r=await s.analyse('fixture',True)
    await asyncio.gather(*list(s.jobs))
    assert c.snapshot().target==1.0
    assert s.journal.get('record:'+r['id'])['audit']['status']=='flagged'


async def test_required_unavailable_audit_blocks_command():
    c,s=setup(); await s.arm('required'); await s.observe(c.snapshot())
    class Broken(FixtureProvider):
        async def audit(self,*args): raise TimeoutError('Review unavailable')
    s.auditor=Broken(); r=await s.analyse('fixture',True)
    assert r['audit']['status']=='unavailable'
    assert r['status']=='blocked'
    assert c.snapshot().target==1.2


async def test_restart_reconciles_lost_ack_without_replaying():
    c,s=setup(); await s.arm('off'); await s.observe(c.snapshot())
    async def lost_ack(request):
        c.apply(request)
        raise TimeoutError('Acknowledgement lost')
    s.receiver.apply=lost_ack
    r=await s.analyse('fixture',True)
    assert r['status']=='unknown' and c.snapshot().target==1.0
    await s.recover()
    recovered=s.journal.get('record:'+r['id'])
    assert recovered['status']=='reconciled'
    assert recovered['command']['actually_applied']
    assert not c.snapshot().armed
    assert len(c.journal.list('command:'))==1


async def test_restart_marks_interrupted_inference_without_a_command():
    c,s=setup(); await s.observe(c.snapshot()); entered=asyncio.Event()
    class Pending(FixtureProvider):
        async def decide(self,context):
            entered.set(); await asyncio.Future()
    s.providers['pending']=Pending()
    task=asyncio.create_task(s.analyse('pending',False));await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    await s.recover()
    r=s.records()[0]
    assert r['status']=='interrupted'
    assert r['command'] is None
    assert not c.snapshot().armed


async def test_required_review_export_preserves_auditor_evidence():
    c,s=setup();await s.arm('required');await s.observe(c.snapshot())
    class Traced(FixtureProvider):
        async def audit_with_evidence(self,context,proposal):
            return await self.audit(context,proposal),{'provider':self.name,'request':{'reviewed_target':proposal.target},'raw_response':{'verdict':'passed'},'seconds':.01}
    s.auditor=Traced();r=await s.analyse('fixture',True)
    assert r['audit_evidence']['request']['reviewed_target']==r['proposal']['target']
    assert r['audit_evidence']['raw_response']['verdict']=='passed'


def test_missing_primary_sensor_still_produces_escalation_context():
    c,s=setup();snapshot=c.snapshot()
    snapshot=snapshot.model_copy(update={'readings':{'flow':snapshot.readings['flow']}})
    context=s.context(snapshot)
    assert context['current_facts']['measurement_relative_to_objective']=='unknown'
    assert any('missing' in r for r in context['eligibility'])


async def test_audit_request_failure_is_recorded_and_blocks_application():
    c,s=setup();await s.arm('required');await s.observe(c.snapshot())
    class BrokenRequest(FixtureProvider):
        def audit_request(self,*args):raise ValueError('Cannot construct audit context')
    s.auditor=BrokenRequest();r=await s.analyse('fixture',True)
    assert r['status']=='blocked'
    assert r['audit']['status']=='unavailable'
    assert 'Cannot construct' in r['audit_evidence']['error']
    assert c.snapshot().target==1.2


async def test_feedback_respects_accepted_command_wait_before_telemetry_catches_up():
    c,s=setup();await s.arm('off');await s.observe(c.snapshot())
    original=s.latest
    r=await s.analyse('fixture',True)
    assert r['command']['actually_applied']
    assert s.latest is original and s.latest.wait_until==0
    s.start_feedback('fixture',2,True)
    await s.feedback_tick()
    assert s.feedback['calls']==0
    assert len(s.records())==1
    c.step(89);await s.observe(c.snapshot());await s.feedback_tick()
    assert s.feedback['calls']==0
    c.step(2);await s.observe(c.snapshot());await s.feedback_tick()
    assert s.feedback['calls']==1


async def test_prior_generation_command_wait_does_not_delay_new_episode():
    c,s=setup();await s.arm('off');await s.observe(c.snapshot())
    await s.analyse('fixture',True)
    c.reset();await s.observe(c.snapshot())
    s.start_feedback('fixture',1,False)
    await s.feedback_tick()
    assert s.feedback['calls']==1
