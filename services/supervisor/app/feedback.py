"""Opt-in feedback orchestration; simulation time governs observations, not polling."""
import os
import asyncio
import time
from copy import deepcopy
from uuid import uuid4
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field
from .sop_context import compact_sample,response_summary,select_sops
from shared.water_exercises import WATER_EXERCISES


class FeedbackRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider:Literal['qwen','jev']='qwen'
    max_calls:int=Field(default=3,ge=1,le=6)
    max_minutes:int=Field(default=90,ge=5,le=120)
    knowledge_mode:Literal['off','lexical','hybrid']='lexical'
    inference_profile:Literal['standard','fast']='fast'
    start_clock:bool=False


class FeedbackController:
    def __init__(self,service):
        self.service=service;self.state=None;self.active=False
        self.lifecycle_lock=asyncio.Lock()
        self.started_wall=0;self.last_call_wall=0;self.samples=[]

    def permitted(self,identifier):
        return self.active and self.state is not None and self.state['id']==identifier

    async def start(self,domain,request):
        async with self.lifecycle_lock:
            if self.active or self.service.tasks:raise HTTPException(409,'Stop the existing loop or wait for its decision first')
            previous=self.state
            self.active=True;self.state=None
            try:
                await self._start(domain,request)
                if request.start_clock:
                    await self.service.resume_simulation(domain)
                    self.state['reason']='Clock running; waiting for the next analysis'
                return deepcopy(self.state)
            except BaseException:
                if self.state:
                    await self._stop('Monitoring could not start; baseline retained control',True)
                self.active=False;self.state=previous
                raise

    async def start_guided_water(self,request):
        """Reserve supervision before resetting a fresh, explicit demo exercise."""
        from shared.models import RunConfig
        async with self.lifecycle_lock:
            if self.active or self.service.tasks:
                raise HTTPException(409,'Stop the existing loop or wait for its decision first')
            self.active=True;self.state=None
            manager=self.service.manager
            run_id=None
            try:
                config=RunConfig(scenario='chlorine_efficiency_trim',seed=42,speed=10,
                    ai_schedule_enabled=False,model=manager.ollama.model)
                run_id=manager.create_run(config)
                await manager.reset(run_id)
                await manager.step(run_id,15)
                await self._start('water',request)
                await manager.start(run_id)
                return deepcopy(self.state)
            except BaseException:
                self.active=False
                if self.state:self.state.update(status='stopped',reason='Guided setup failed; restart the exercise')
                if run_id:
                    try:await manager.pause(run_id)
                    except Exception:pass
                try:await self.service.baseline('water')
                except Exception:pass
                raise

    async def _start(self,domain,request):
        context=await self.service.context(domain)
        if context['plant'].get('safety_state')=='critical':raise HTTPException(409,'Critical plant condition requires operator review')
        await self.service.enable_application(domain)
        context=await self.service.context(domain)
        self.active=True;self.started_wall=time.monotonic();self.last_call_wall=0;self.samples=[]
        self.service.manual_domains.add(domain)
        self.state={'id':str(uuid4()),'domain':domain,'provider':request.provider,'status':'waiting',
            'calls_used':0,'max_calls':request.max_calls,'max_minutes':request.max_minutes,
            'started_minute':context['plant']['elapsed_minutes'],'next_review_minute':context['plant']['elapsed_minutes'],
            'run_id':context['run_id'],'controller_generation':context.get('plc',{}).get('controller_generation'),
            'objective_history':[],'process_history':[],'observation_only':False,'records':[],'reason':'Waiting for the simulation clock to run','job_id':None,'settings':request.model_dump(),
            'response':{'status':'insufficient_observations'}}
        return deepcopy(self.state)

    async def stop(self,reason='Operator stopped feedback',release=True):
        async with self.lifecycle_lock:
            return await self._stop(reason,release)

    async def _stop(self,reason,release):
        if not self.state:return {'status':'idle'}
        self.active=False
        self.state.update(status='stopped',reason=reason)
        if reason!='Call budget complete; observation window recorded' and hasattr(self.service,'close_feedback_outcomes'):
            try:self.service.close_feedback_outcomes(self.state['records'],reason)
            except Exception:self.state['outcome_warning']='Could not finalize observation records; recovery is not established'
        if release:
            try:await self.service.baseline(self.state['domain'])
            except Exception:self.state['release_warning']='Could not confirm baseline return; existing bounded lease still expires'
        return deepcopy(self.state)

    async def tick(self):
        if not self.active or self.state is None:return
        state=self.state
        context=await self.service.context(state['domain'])
        if not self.permitted(state['id']):return
        plant=context['plant'];minute=plant['elapsed_minutes']
        changed=context['run_id']!=state['run_id'] or context.get('plc',{}).get('controller_generation')!=state['controller_generation']
        if changed or minute<state['started_minute']:
            await self.stop('Exercise reset; feedback ended',release=False);return
        expected_mode='baseline' if state.get('observation_only') else 'gated_auto'
        allowed_modes={'baseline','gated_auto'} if state['status']=='disarming' else {expected_mode}
        if plant.get('controller_mode') not in allowed_modes:
            await self.stop('Operator changed control mode',release=False);return
        if plant.get('safety_state')=='critical' or plant.get('emergency_stop'):
            await self.stop('Critical condition; operator review required');return
        if minute-state['started_minute']>=state['max_minutes'] or time.monotonic()-self.started_wall>900:
            await self.stop('Feedback time limit reached');return
        objective=select_sops(state['domain'],plant).get('operating_objective')
        exercise=WATER_EXERCISES.get(plant.get('scenario')) if state['domain']=='water' else None
        if exercise:
            sensor=plant.get('sensors',{}).get(exercise['signal'],{})
            history=state['process_history']
            if not history or history[-1]['minute']!=minute:
                history.append({'minute':minute,'value':sensor.get('value'),'quality':sensor.get('quality'),
                    'timestamp':sensor.get('timestamp'),'simulation_time':plant.get('simulation_time'),
                    'target':context.get('plc',{}).get('setpoints',{}).get(exercise['target'])})
                del history[:-120]
        if objective:
            state['objective']=objective
            history=state['objective_history']
            if not history or history[-1]['minute']!=minute:
                history.append({'minute':minute,'residual':objective['observed_residual_mg_l'],
                    'position':objective['position'],'safety_state':plant.get('safety_state'),
                    'target':context.get('plc',{}).get('setpoints',{}).get('chlorine_target_mg_l')})
                del history[:-90]
        if not self.samples or self.samples[-1]['minute']!=minute:
            procedures=select_sops(state['domain'],plant)['procedures']
            names=list(dict.fromkeys(name for p in procedures for name in p['signals']))[:24]
            sample=compact_sample(context,names)
            self.samples=(self.samples+[sample])[-30:]
            state['response']=response_summary(self.samples)
        if state['status'] in {'inferencing','disarming'}:return
        if not plant.get('running'):
            state.update(status='paused',reason='Simulation paused; no AI calls');return
        if minute<state['next_review_minute']:
            state.update(status='observing',reason=f"Observe until simulated minute {state['next_review_minute']}");return
        if state['calls_used']>=state['max_calls']:
            await self.stop('Call budget complete; observation window recorded');return
        if self.service.tasks:return
        if os.getenv('HOSTED_MODE')=='true' and time.monotonic()-self.last_call_wall<11:return
        state.update(status='inferencing',reason='Selected model is reviewing current observations')
        state['calls_used']+=1;self.last_call_wall=time.monotonic()
        loop_id=state['id'];frozen=deepcopy(context)
        feedback_context={'loop_id':loop_id,'previous_record_ids':state['records'][-4:],
            'observations':deepcopy(self.samples[-8:]),'response':deepcopy(state['response']),
            'policy':'Hold during delayed response. Review observed trends before any new target. Hold when no adjustment is justified and observations remain trustworthy. Escalate for protection triggers, unresolved unsafe conditions or unreliable required evidence.'}
        async def decide():
            try:
                record=await self.service.cycle(state['domain'],provider=state['provider'],evaluate_only=state.get('observation_only',False),context=frozen,
                    knowledge_mode=state['settings']['knowledge_mode'],inference_profile=state['settings']['inference_profile'],
                    experiment={'feedback':feedback_context},application_guard=lambda:self.permitted(loop_id),adaptive_timing=True)
                state['records'].append(record['id'])
                if not self.permitted(loop_id):
                    if hasattr(self.service,'close_feedback_outcomes'):
                        self.service.close_feedback_outcomes([record['id']],state.get('reason','Feedback ended'))
                    return record
                changes=any(v is not None for v in record.get('proposal',{}).get('changes',{}).values())
                if record.get('status')=='complete' and not changes and (record.get('proposal',{}).get('episode_status')=='escalate' or record.get('selected_candidate')=='review'):
                    await self.stop('Model requested operator review');return record
                rejected=record.get('gate',{}).get('status')=='rejected'
                reasons=record.get('gate',{}).get('violated_constraints',[])
                confidence_only=(state['domain']=='water' and not changes and record.get('status')=='complete'
                    and reasons==['Confidence is below the 0.55 gate threshold'] and rejected)
                if confidence_only and not state.get('observation_only'):
                    # This loop can never rearm after losing actuation permission.
                    state.update(observation_only=True,status='disarming')
                    await self.service.baseline(state['domain'])
                    if not self.permitted(loop_id):return record
                if record.get('status')!='complete' or (rejected and not confidence_only):
                    await self.stop('Proposal blocked or invalid; inspect the decision record');return record
                latest=await self.service.context(state['domain'])
                if not self.permitted(loop_id):return record
                state['next_review_minute']=latest['plant']['elapsed_minutes']+record.get('response_window',{}).get('observe_minutes',5)
                self.service.schedule_feedback_outcome(record['id'],latest['plant']['elapsed_minutes'],state['next_review_minute'])
                self.samples=[]  # Next window describes this exchange, not prior interventions.
                state.update(status='observing',reason='Read-only monitoring; targets cannot be applied' if state.get('observation_only') else 'Waiting for measured process response')
                return record
            except Exception as exc:
                if self.permitted(loop_id):
                    if getattr(exc,'audit_id',None) and exc.audit_id not in state['records']:state['records'].append(exc.audit_id)
                    await self.stop('Inference or response validation failed; inspect the recorded exchange. No automatic retry')
                raise
        try:job=self.service.enqueue(state['domain'],decide);state['job_id']=job['id']
        except HTTPException:
            state['calls_used']-=1;state['status']='waiting'
