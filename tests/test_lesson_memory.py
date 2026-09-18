from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.supervisor.app import lesson_memory as memory
from services.supervisor.app import agent_audit
from services.supervisor.app.database import Base, CriticalEventRecord, LessonRecord


@pytest.fixture
def database(monkeypatch):
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(memory, 'SessionLocal', factory)
    monkeypatch.setattr(agent_audit, 'SessionLocal', factory)
    yield factory
    engine.dispose()


def audit():
    return dict(id='audit-1', domain='water', status='complete', request={'model':'qwen3:8b'},
                before={'run_id':'run-1','plant':{'scenario':'storm','safety_state':'warning','active_alarms':['high turbidity']}},
                proposal={'changes':{'coagulant_target_mg_l':17}}, gate={'status':'accepted'},
                applied=True, outcome={'status':'observed','plant':{'filtered_turbidity_ntu':1.2}})


def event():
    with memory.SessionLocal() as db:
        value = memory.archive(db, audit())
        db.commit()
    return value


def candidate():
    return memory.propose([event()], 'Check measured effluent after changing the target.', expires_days=30)


def test_archive_is_idempotent_and_keeps_evidence_after_source_deletion(database):
    identifier = event()
    assert event() == identifier
    with database() as db:
        rows = db.scalars(select(CriticalEventRecord)).all()
        assert len(rows) == 1
        assert rows[0].payload['outcome']['plant']['filtered_turbidity_ntu'] == 1.2


def test_normal_unapplied_record_does_not_become_critical(database):
    record = audit(); record.update(applied=False, outcome=None)
    record['before']['plant'].update(safety_state='normal', active_alarms=[])
    with database() as db:
        assert memory.archive(db, record) is None


def test_audit_updates_capture_failures_and_later_outcomes(database):
    identifier = agent_audit.create_audit('water', {'model':'qwen3:8b'})
    agent_audit.update_audit(identifier, **{k:v for k,v in audit().items() if k not in {'id','domain','request'}})
    with database() as db:
        assert len(db.scalars(select(CriticalEventRecord)).all()) == 1


def test_candidate_cannot_enter_prompt_until_operator_review(database):
    lesson = candidate()
    assert memory.retrieve('water', 'storm', 'qwen3:8b') == []
    reviewed = memory.review(lesson['lesson_id'], 1, 'approved', 'operator', 'Checked source and applicability.')
    assert reviewed['version'] == 2
    found = memory.retrieve('water', 'storm', 'qwen3:8b')
    assert len(found) == 1 and found[0]['version'] == 2
    assert found[0]['authority'] == 'context_only'


@pytest.mark.parametrize('domain,scenario,model', [('grid','storm','qwen3:8b'),('water','normal','qwen3:8b'),('water','storm','other')])
def test_lessons_do_not_cross_scope(database, domain, scenario, model):
    lesson = candidate(); memory.review(lesson['lesson_id'],1,'approved','operator','Evidence checked.')
    assert memory.retrieve(domain, scenario, model) == []


def test_revocation_expiry_and_stale_review(database):
    lesson = candidate(); memory.review(lesson['lesson_id'],1,'approved','operator','Evidence checked.')
    assert memory.retrieve('water','storm','qwen3:8b',now=datetime.now(timezone.utc)+timedelta(days=31)) == []
    with pytest.raises(ValueError, match='version'):
        memory.review(lesson['lesson_id'],1,'revoked','operator','Stale request.')
    memory.review(lesson['lesson_id'],2,'revoked','operator','Contradictory observation.')
    assert memory.retrieve('water','storm','qwen3:8b') == []
    with database() as db:
        assert len(db.scalars(select(LessonRecord)).all()) == 3


def test_unbacked_or_oversized_lessons_are_rejected(database):
    with pytest.raises(ValueError): memory.propose(['missing'], 'Do something')
    with pytest.raises(ValueError): memory.propose([event()], 'x'*601)
    lesson=candidate()
    with pytest.raises(ValueError): memory.review(lesson['lesson_id'],1,'approved','','')


def test_retention_is_independent_of_resettable_run_tables(database):
    from services.supervisor.app.database import SampleRecord, DecisionRecord, AlarmRecord
    lesson=candidate()
    with database() as db:
        for table in (SampleRecord, DecisionRecord, AlarmRecord): db.query(table).delete()
        db.commit()
    memory.review(lesson['lesson_id'],1,'approved','operator','Evidence still preserved.')
    assert memory.retrieve('water','storm','qwen3:8b')


def test_reviewed_lesson_is_supplied_as_untrusted_prompt_data(database, monkeypatch):
    import asyncio, json
    from services.plant_sim.app.simulator import WaterPlantSimulator
    from services.supervisor.app.ollama_client import OllamaSupervisor
    from shared.models import ControlProposal, SetpointChanges
    snapshot=WaterPlantSimulator().snapshot()
    record=audit();record['before']['plant']['scenario']=snapshot.scenario
    with database() as db:
        event_id=memory.archive(db,record);db.commit()
    lesson=memory.propose([event_id],'Inspect measured dose and effluent before repeating an adjustment.')
    memory.review(lesson['lesson_id'],1,'approved','operator','Checked source and scope.')
    monkeypatch.setenv('LESSON_MEMORY_ENABLED','true')
    worker=OllamaSupervisor();captured={}
    async def chat(domain,payload,schema):
        captured.update(payload)
        return ControlProposal(changes=SetpointChanges(),expected_effect='No change',confidence=.5,explanation='Test'), 'test'
    monkeypatch.setattr(worker,'_chat',chat)
    asyncio.run(worker.propose(snapshot,{},model='qwen3:8b'))
    state=json.loads(captured['messages'][1]['content'])
    assert state['reviewed_lessons'][0]['lesson_id']==lesson['lesson_id']
    assert 'untrusted' in captured['messages'][0]['content']
    monkeypatch.setenv('LESSON_MEMORY_ENABLED','false')
    asyncio.run(worker.propose(snapshot,{},model='qwen3:8b'))
    assert json.loads(captured['messages'][1]['content'])['reviewed_lessons']==[]
