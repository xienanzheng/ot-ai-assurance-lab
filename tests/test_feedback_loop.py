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


def test_low_confidence_water_hold_continues_read_only_without_rearming():
    async def run():
        s=Service();f=FeedbackController(s);evaluations=[]
        async def hold(*args,**kwargs):
            evaluations.append(kwargs['evaluate_only'])
            return {'id':str(len(evaluations)), 'status':'complete','applied':False,
                'gate':{'status':'rejected','violated_constraints':['Confidence is below the 0.55 gate threshold']},
                'proposal':{'changes':{},'episode_status':'continue','confidence':0},'response_window':{'observe_minutes':5}}
        s.cycle=hold
        await f.start('water',FeedbackRequest(max_calls=2));await f.tick();await s.calls[0]()
        assert f.active and f.state['observation_only']
        assert s.current['plant']['controller_mode']=='baseline'
        s.current['plant']['elapsed_minutes']=5
        await f.tick();await s.calls[1]()
        assert evaluations==[False,True]
        s.current['plant']['elapsed_minutes']=10
        await f.tick();assert not f.active
    asyncio.run(run())


def test_rejected_action_or_additional_protection_failure_still_stops():
    async def run():
        for changes,reasons in [({'chlorine_target_mg_l':1.0},['Confidence is below the 0.55 gate threshold']),
                               ({},['Confidence is below the 0.55 gate threshold','Sensor data is stale'])]:
            s=Service();f=FeedbackController(s)
            async def blocked(*args,**kwargs):
                return {'id':'blocked','status':'complete','applied':False,'gate':{'status':'rejected','violated_constraints':reasons},'proposal':{'changes':changes,'episode_status':'continue'}}
            s.cycle=blocked
            await f.start('water',FeedbackRequest());await f.tick();await s.calls[0]()
            assert not f.active
    asyncio.run(run())


def test_read_only_loop_still_stops_for_critical_condition():
    async def run():
        s=Service();f=FeedbackController(s)
        await f.start('water',FeedbackRequest())
        f.state['observation_only']=True;s.current['plant']['controller_mode']='baseline'
        s.current['plant']['safety_state']='critical'
        await f.tick()
        assert not f.active and not s.calls and 'Critical' in f.state['reason']
    asyncio.run(run())


def test_guided_setup_reserves_owner_and_starts_only_after_warmup():
    async def run():
        s=Service();f=FeedbackController(s);events=[]
        def create(config):
            assert f.active and f.state is None
            assert config.scenario=='chlorine_efficiency_trim' and not config.ai_schedule_enabled
            events.append('create');return 'guided'
        async def reset(identifier):events.append('reset')
        async def step(identifier,minutes):assert minutes==15;events.append('warmup')
        async def start(identifier):assert f.state['domain']=='water';events.append('start')
        s.manager=SimpleNamespace(ollama=SimpleNamespace(model='test'),create_run=create,reset=reset,step=step,start=start)
        await f.start_guided_water(FeedbackRequest())
        assert events==['create','reset','warmup','start'] and f.active
        with pytest.raises(Exception):await f.start_guided_water(FeedbackRequest())
    asyncio.run(run())


def test_guided_failure_pauses_and_releases_supervision():
    async def run():
        s=Service();f=FeedbackController(s);events=[]
        async def reset(identifier):raise RuntimeError('offline')
        async def pause(identifier):events.append('pause')
        s.manager=SimpleNamespace(ollama=SimpleNamespace(model='test'),create_run=lambda c:'guided',reset=reset,pause=pause)
        with pytest.raises(RuntimeError):await f.start_guided_water(FeedbackRequest())
        assert not f.active and events==['pause'] and s.current['plant']['controller_mode']=='baseline'
    asyncio.run(run())


def test_disarming_can_be_observed_and_operator_stop_is_never_undone():
    async def run():
        s=Service();f=FeedbackController(s)
        async def hold(*args,**kwargs):
            return {'id':'hold','status':'complete','gate':{'status':'rejected','violated_constraints':['Confidence is below the 0.55 gate threshold']},'proposal':{'changes':{},'episode_status':'continue'}}
        async def baseline(domain):
            await f.tick()  # Concurrent monitor sees old mode while release is in flight.
            assert f.active and len(s.calls)==1
            s.current['plant']['controller_mode']='baseline'
            await f.tick()  # Publication may arrive before the HTTP call completes.
            assert f.active and len(s.calls)==1
            await f.stop('Operator stopped feedback',release=False)
        s.cycle=hold;s.baseline=baseline
        await f.start('water',FeedbackRequest());await f.tick();await s.calls[0]()
        assert not f.active and f.state['status']=='stopped'
    asyncio.run(run())


def test_record_completing_after_stop_is_retained_and_finalized():
    async def run():
        s=Service();f=FeedbackController(s);closed=[]
        s.close_feedback_outcomes=lambda ids,reason:closed.extend(ids)
        async def late(*args,**kwargs):
            await f.stop('Operator stopped feedback')
            return {'id':'late','status':'complete','applied':True,'outcome':{'status':'awaiting feedback window'}}
        s.cycle=late
        await f.start('water',FeedbackRequest());await f.tick();await s.calls[0]()
        assert f.state['records']==['late'] and 'late' in closed
        assert f.state['status']=='stopped' and not f.active
    asyncio.run(run())


def test_audit_failure_does_not_prevent_baseline_return():
    async def run():
        s=Service();f=FeedbackController(s)
        def broken(*args):raise RuntimeError('audit unavailable')
        s.close_feedback_outcomes=broken
        await f.start('water',FeedbackRequest())
        state=await f.stop()
        assert not f.active and s.current['plant']['controller_mode']=='baseline'
        assert state['outcome_warning']
    asyncio.run(run())


def test_start_can_resume_existing_clock_without_resetting_the_exercise():
    async def run():
        s=Service();s.current['plant'].update(running=False,elapsed_minutes=55)
        f=FeedbackController(s);events=[]
        async def resume(domain):
            assert f.active and f.state['run_id']=='r'
            events.append(domain);s.current['plant']['running']=True
        s.resume_simulation=resume
        await f.start('water',FeedbackRequest(max_calls=2,start_clock=True))
        assert events==['water'] and s.current['plant']['elapsed_minutes']==55
        await f.tick();await s.calls[0]()
        s.current['plant']['elapsed_minutes']=59;await f.tick();assert len(s.calls)==1
        s.current['plant']['elapsed_minutes']=60;await f.tick();assert len(s.calls)==2
    asyncio.run(run())


def test_failed_clock_start_releases_control_and_leaves_no_active_loop():
    async def run():
        s=Service();f=FeedbackController(s)
        async def fail(domain):raise RuntimeError('clock unavailable')
        s.resume_simulation=fail
        with pytest.raises(RuntimeError):await f.start('water',FeedbackRequest(start_clock=True))
        assert not f.active and s.current['plant']['controller_mode']=='baseline'
    asyncio.run(run())


def test_chlorine_feedback_uses_twelve_minutes_before_next_call():
    async def run():
        s=Service();f=FeedbackController(s)
        async def cycle(*args,**kwargs):
            return {'id':'adjust','status':'complete','gate':{'status':'accepted'},'proposal':{'changes':{'chlorine_target_mg_l':1.1}},'response_window':{'observe_minutes':12}}
        s.cycle=cycle
        await f.start('water',FeedbackRequest(max_calls=2));await f.tick();await s.calls[0]()
        s.current['plant']['elapsed_minutes']=5;await f.tick();assert len(s.calls)==1
        s.current['plant']['elapsed_minutes']=11;await f.tick();assert len(s.calls)==1
        s.current['plant']['elapsed_minutes']=12;await f.tick();assert len(s.calls)==2
    asyncio.run(run())


def test_demo_clock_preserves_the_exercise_and_forwards_requested_speed():
    async def run():
        s=Service();s.current['plant'].update(running=False,elapsed_minutes=37)
        seen=[]
        async def resume(domain,speed=None):
            seen.append((domain,speed));s.current['plant']['running']=True
        s.resume_simulation=resume
        f=FeedbackController(s)
        await f.start('water',FeedbackRequest(start_clock=True,simulation_speed=30,max_calls=2))
        assert seen==[('water',30)]
        assert f.state['started_minute']==37 and s.current['plant']['elapsed_minutes']==37
    asyncio.run(run())


def test_water_budget_returns_baseline_and_keeps_read_only_trends_until_stop():
    async def run():
        s=Service()
        s.current['plant'].update(scenario='chlorine_efficiency_trim',sensors={'chlorine_residual_mg_l':{'value':1.1,'quality':'good','timestamp':'2026-01-01T00:00:00Z'}},simulation_time='2026-01-01T00:00:00Z')
        f=FeedbackController(s)
        await f.start('water',FeedbackRequest(max_calls=1,monitor_after_budget=True))
        await f.tick();await s.calls[0]()
        s.current['plant']['elapsed_minutes']=5
        s.current['plant']['sensors']['chlorine_residual_mg_l']['value']=1.02
        await f.tick()
        assert f.active and f.state['budget_complete'] and f.state['status']=='monitoring'
        assert s.current['plant']['controller_mode']=='baseline'
        s.current['plant']['elapsed_minutes']=6
        s.current['plant']['sensors']['chlorine_residual_mg_l']['value']=.99
        await f.tick()
        assert len(s.calls)==1 and f.state['process_history'][-1]['value']==.99
        s.current['plant']['safety_state']='critical'
        await f.tick()
        assert not f.active and f.state['status']=='stopped'
    asyncio.run(run())
