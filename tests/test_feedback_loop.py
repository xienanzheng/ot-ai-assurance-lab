import asyncio
from copy import deepcopy
from types import SimpleNamespace
import pytest
from services.supervisor.app.feedback import FeedbackController, FeedbackRequest


class Service:
    def __init__(self):
        self.current={'run_id':'r','plant':{'elapsed_minutes':0,'running':True,'controller_mode':'gated_auto','safety_state':'normal','sensors':{}}}
        self.tasks=set();self.jobs={};self.calls=[];self.manual_domains=set()
    async def context(self,domain):return deepcopy(self.current)
    def schedule_feedback_outcome(self,identifier,start,review):pass
    async def enable_application(self,domain):pass
    async def baseline(self,domain):self.current['plant']['controller_mode']='baseline'
    def enqueue(self,domain,action):
        self.calls.append(action);identifier=str(len(self.calls));self.jobs[identifier]={'id':identifier,'status':'running'};return self.jobs[identifier]
    async def cycle(self,*args,**kwargs):return {'id':'decision','applied':False,'status':'complete','gate':{'status':'accepted'},'proposal':{'changes':{}},'response_window':{'observe_minutes':5}}


def test_loop_waits_for_simulated_time_and_never_calls_while_paused():
    async def run():
        s=Service();f=FeedbackController(s)
        state=await f.start('grid',FeedbackRequest(max_calls=2))
        s.current['plant']['running']=False
        await f.tick();assert not s.calls
        s.current['plant']['running']=True
        await f.tick();assert len(s.calls)==1
        await s.calls[0]();await f.tick();assert len(s.calls)==1
        s.current['plant']['elapsed_minutes']=4
        await f.tick();assert len(s.calls)==1
        s.current['plant']['elapsed_minutes']=5
        await f.tick();assert len(s.calls)==2
    asyncio.run(run())


def test_stop_disarms_inflight_guard_and_reset_ends_loop():
    async def run():
        s=Service();f=FeedbackController(s)
        state=await f.start('grid',FeedbackRequest())
        assert f.permitted(state['id'])
        await f.stop('operator stop')
        assert not f.permitted(state['id'])
        await f.start('grid',FeedbackRequest())
        s.current['run_id']='reset'
        await f.tick()
        assert f.state['status']=='stopped' and not s.calls
    asyncio.run(run())


def test_only_one_loop_and_budget_is_bounded():
    with pytest.raises(ValueError):FeedbackRequest(max_calls=100)
    async def run():
        f=FeedbackController(Service());await f.start('grid',FeedbackRequest())
        with pytest.raises(Exception):await f.start('water',FeedbackRequest())
    asyncio.run(run())


def test_simultaneous_starts_have_one_owner():
    async def run():
        class SlowService(Service):
            async def context(self, domain):
                await asyncio.sleep(0)
                return await super().context(domain)
        f = FeedbackController(SlowService())
        results = await asyncio.gather(f.start('grid', FeedbackRequest()), f.start('water', FeedbackRequest()), return_exceptions=True)
        assert sum(isinstance(result, dict) for result in results) == 1
    asyncio.run(run())


def test_feedback_context_is_bounded_and_keeps_bad_quality_visible():
    async def run():
        s = Service()
        s.current['plant']['sensors'] = {f'aux_{i}': {'value': i, 'quality': 'good'} for i in range(300)}
        s.current['plant']['sensors']['frequency_hz'] = {'value': 50, 'quality': 'bad'}
        f = FeedbackController(s)
        await f.start('grid', FeedbackRequest())
        await f.tick()
        assert len(f.samples[0]['values']) <= 24
        assert f.samples[0]['quality_exceptions']['frequency_hz'] == 'bad'
    asyncio.run(run())


def test_stop_during_observation_fetch_spends_no_new_call():
    async def run():
        s=Service(); f=FeedbackController(s)
        await f.start('grid',FeedbackRequest())
        async def context(domain):
            await f.stop(release=False)
            return deepcopy(s.current)
        s.context=context
        await f.tick()
        assert not s.calls
    asyncio.run(run())


def test_feedback_defers_outcome_until_response_window_is_scheduled():
    async def run():
        s=Service(); f=FeedbackController(s)
        s.scheduled=[]
        def schedule(identifier,start,review):s.scheduled.append((identifier,start,review))
        s.schedule_feedback_outcome=schedule
        await f.start('grid',FeedbackRequest())
        await f.tick(); await s.calls[0]()
        assert s.scheduled==[('decision',0,5)]
    asyncio.run(run())


def test_start_reserves_supervision_before_waiting_for_context():
    async def run():
        s=Service(); f=FeedbackController(s)
        async def context(domain):
            assert f.active, 'Manual analyses must be blocked while start is in progress'
            return deepcopy(s.current)
        s.context=context
        await f.start('grid',FeedbackRequest())
    asyncio.run(run())


def test_operator_review_is_not_reported_as_invalid_decision():
    async def run():
        s=Service();f=FeedbackController(s)
        async def review(*args,**kwargs):
            assert 'Hold when no adjustment is justified' in kwargs['experiment']['feedback']['policy']
            return {'id':'review','status':'complete','gate':{'status':'rejected'},'proposal':{'episode_status':'escalate','changes':{}}}
        s.cycle=review
        await f.start('water',FeedbackRequest());await f.tick();await s.calls[0]()
        assert f.state['reason']=='Model requested operator review'
    asyncio.run(run())


def test_failed_inference_record_remains_accessible_from_loop():
    from services.supervisor.app.ollama_client import OllamaUnavailable
    async def run():
        s=Service();f=FeedbackController(s)
        async def fail(*args,**kwargs):raise OllamaUnavailable('bad JSON',audit_id='failed-record')
        s.cycle=fail
        await f.start('water',FeedbackRequest());await f.tick()
        with pytest.raises(OllamaUnavailable):await s.calls[0]()
        assert f.state['records']==['failed-record']
        assert not f.active
    asyncio.run(run())
