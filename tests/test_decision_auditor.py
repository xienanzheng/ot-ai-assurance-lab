import asyncio
from copy import deepcopy
import pytest
from services.supervisor.app.decision_auditor import DecisionAuditor, build_evidence, validate_review


def record():
    from services.plc_control.app.controller import SafetyGate
    r= {'id':'record-1','domain':'water','provider':'qwen','proposal':{'changes':{'chlorine_target_mg_l':1.1},'episode_status':'continue','explanation':'Reduce residual'},'before':{'plant':{'simulation_time':'2026-01-01T00:15:00Z','elapsed_minutes':15,'safety_state':'normal','sensors':{'chlorine_residual_mg_l':{'value':1.15,'quality':'good','timestamp':'2026-01-01T00:15:00Z'}},'active_alarms':[]},'plc':{'setpoints':{'chlorine_target_mg_l':1.15}}},'sop_context':{'version':'1.1.1','procedures':[]},'gate':{'status':'accepted'},'applied':True}

    for sensor in SafetyGate._dependencies({'chlorine_target_mg_l'}):
        r['before']['plant']['sensors'].setdefault(sensor,{'value':1.0,'quality':'good','timestamp':'2026-01-01T00:15:00Z'})
    return r

def test_reviewer_blinded_to_gate_and_identity_and_uses_original_proposal():
    r=record();r['model_proposal']={**r['proposal'],'explanation':'Original claim'}
    e=build_evidence(r)
    assert 'accepted' not in str(e) and 'qwen' not in str(e)
    assert 'Original claim' in e['proposal'] and '1.15' in e['plant']
    assert 'timestamp' in e['plant'] and 'sop' in e


def test_invented_or_duplicate_citations_are_rejected():
    e=build_evidence(record())
    for ids in [['invented'],['plant','plant'],[]]:
        with pytest.raises(ValueError):validate_review({'verdict':'flagged','reason':'Check','evidence_ids':ids},e)
    assert validate_review({'verdict':'passed','reason':'No issue found','evidence_ids':['proposal','sop']},e)['verdict']=='passed'


def test_background_review_does_not_wait_or_change_proposal_gate_or_application():
    async def run():
        r=record();original=deepcopy(r);event=asyncio.Event();sent=[]
        def read(i):return deepcopy(r)
        def write(i,**fields):r.update(fields)
        async def send(payload):
            sent.append(payload);await event.wait()
            return {'content':'{"verdict":"passed","reason":"Bounded decrease","evidence_ids":["proposal"]}','model':'test-gemma'}
        audit=DecisionAuditor(read=read,write=write,send=send,enabled=True,model='test-gemma')
        audit.schedule(r);assert r['decision_audit']['status']=='pending'
        audit.schedule(r);await asyncio.sleep(0);assert len(sent)==1
        assert all(r[k]==v for k,v in original.items())
        event.set();await audit.drain()
        assert r['decision_audit']['status']=='passed' and all(r[k]==v for k,v in original.items())
        assert r['decision_audit']['input_sha256'] and r['decision_audit']['request']
    asyncio.run(run())


def test_timeouts_and_cancelled_reviews_are_unavailable_not_passed():
    async def run(cancel):
        r=record()
        async def send(payload):await asyncio.Event().wait()
        audit=DecisionAuditor(read=lambda _:deepcopy(r),write=lambda _,**fields:r.update(fields),send=send,enabled=True,timeout=.01)
        audit.schedule(r)
        if cancel:await asyncio.sleep(0);await audit.close()
        else:await audit.drain()
        assert r['decision_audit']['status']=='unavailable' and r['applied'] is True
    asyncio.run(run(False));asyncio.run(run(True))


def test_missing_or_oversized_context_cannot_receive_pass():
    async def run():
        for before in [{},{'plant':{'sensors':{'x':{'value':'x'*60000}}}}]:
            r=record();r['before']=before
            async def send(payload):raise AssertionError('Must not call model')
            audit=DecisionAuditor(read=lambda _:deepcopy(r),write=lambda _,**fields:r.update(fields),send=send,enabled=True)
            audit.schedule(r);await audit.drain();assert r['decision_audit']['status']=='unavailable'
    asyncio.run(run())


def test_pass_cannot_contradict_captured_protection_or_required_sensor_facts():
    claimed_pass={'verdict':'passed','reason':'Looks fine','evidence_ids':['proposal']}
    for fault in ['critical','stale','old','future','trip','waiting']:
        r=record();plant=r['before']['plant']
        if fault=='critical':plant['safety_state']='critical'
        if fault=='stale':plant['sensors']['chlorine_residual_mg_l']['quality']='stale'
        if fault=='old':plant['sensors']['chlorine_residual_mg_l']['timestamp']='2026-01-01T00:10:00Z'
        if fault=='future':plant['sensors']['chlorine_residual_mg_l']['timestamp']='2026-01-01T00:16:00Z'
        if fault=='trip':r['before']['plc']['control_state']={'trips':[{'code':'X','latched':True}]}
        if fault=='waiting':r['experiment']={'previous_application':{'applied_minute':14,'observe_minutes':12}}
        sources=build_evidence(r)
        with pytest.raises(ValueError,match='contradicts'):validate_review(claimed_pass,sources)
        r['proposal']['changes']={};r['proposal']['episode_status']='escalate' if fault in ['critical','trip'] else 'hold'
        assert validate_review(claimed_pass,build_evidence(r))['verdict']=='passed'


def test_false_pass_is_unavailable_and_raw_model_response_is_preserved():
    async def run():
        r=record();r['before']['plant']['safety_state']='critical'
        async def send(payload):return {'content':'{"verdict":"passed","reason":"Incorrect assertion","evidence_ids":["proposal"]}'}
        audit=DecisionAuditor(write=lambda _,**fields:r.update(fields),send=send,enabled=True)
        audit.schedule(r);await audit.drain()
        result=r['decision_audit']
        assert result['status']=='unavailable' and 'contradicted' in result['reason']
        assert 'Incorrect assertion' in result['response']['content']
        assert r['applied'] is True and r['gate']=={'status':'accepted'}
    asyncio.run(run())


def test_restart_marks_pending_only_without_changing_decisions(tmp_path,monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from services.supervisor.app import database
    engine=create_engine('sqlite:///'+str(tmp_path/'audit.db'))
    database.Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    monkeypatch.setattr(database,'SessionLocal',sessions)
    with sessions() as db:
        for i,status in enumerate(['pending','passed']):
            r=record();r['decision_audit']={'status':status}
            db.add(database.AgentAuditRecord(id=str(i),domain='water',payload=r))
        db.commit()
    DecisionAuditor(enabled=True).recover()
    with sessions() as db:
        assert db.get(database.AgentAuditRecord,'0').payload['decision_audit']['status']=='unavailable'
        assert db.get(database.AgentAuditRecord,'1').payload['decision_audit']['status']=='passed'
        assert db.get(database.AgentAuditRecord,'0').payload['applied'] is True
    engine.dispose()
