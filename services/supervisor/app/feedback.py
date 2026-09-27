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


class FeedbackRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    provider:Literal['qwen','jev']='qwen'
    max_calls:int=Field(default=3,ge=1,le=6)
    max_minutes:int=Field(default=90,ge=5,le=120)
    knowledge_mode:Literal['off','lexical','hybrid']='lexical'
    inference_profile:Literal['standard','fast']='fast'


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
                return await self._start(domain,request)
            except BaseException:
                self.active=False;self.state=previous
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
            'records':[],'reason':'Waiting for the simulation clock to run','job_id':None,'settings':request.model_dump(),
            'response':{'status':'insufficient_observations'}}
        return deepcopy(self.state)

    async def stop(self,reason='Operator stopped feedback',release=True):
        async with self.lifecycle_lock:
            return await self._stop(reason,release)

    async def _stop(self,reason,release):
        if not self.state:return {'status':'idle'}
        self.active=False
        self.state.update(status='stopped',reason=reason)
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
        if plant.get('controller_mode')!='gated_auto':
            await self.stop('Operator changed control mode',release=False);return
        if plant.get('safety_state')=='critical' or plant.get('emergency_stop'):
            await self.stop('Critical condition; operator review required');return
        if minute-state['started_minute']>=state['max_minutes'] or time.monotonic()-self.started_wall>900:
            await self.stop('Feedback time limit reached');return
        if not self.samples or self.samples[-1]['minute']!=minute:
            procedures=select_sops(state['domain'],plant)['procedures']
            names=list(dict.fromkeys(name for p in procedures for name in p['signals']))[:24]
            sample=compact_sample(context,names)
            self.samples=(self.samples+[sample])[-30:]
            state['response']=response_summary(self.samples)
        if state['status']=='inferencing':return
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
            'policy':'Hold during delayed response. Review observed trends before any new target. Request escalation if no safe correction is justified.'}
        async def decide():
            try:
                record=await self.service.cycle(state['domain'],provider=state['provider'],evaluate_only=False,context=frozen,
                    knowledge_mode=state['settings']['knowledge_mode'],inference_profile=state['settings']['inference_profile'],
                    experiment={'feedback':feedback_context},application_guard=lambda:self.permitted(loop_id),adaptive_timing=True)
                if not self.permitted(loop_id):return record
                state['records'].append(record['id'])
                if record.get('status')!='complete' or record.get('gate',{}).get('status')=='rejected':
                    await self.stop('Decision rejected or invalid; operator review required');return record
                if record.get('proposal',{}).get('episode_status')=='escalate' or record.get('selected_candidate')=='review':
                    await self.stop('Model requested operator review');return record
                latest=await self.service.context(state['domain'])
                state['next_review_minute']=latest['plant']['elapsed_minutes']+record.get('response_window',{}).get('observe_minutes',5)
                self.service.schedule_feedback_outcome(record['id'],latest['plant']['elapsed_minutes'],state['next_review_minute'])
                self.samples=[]  # Next window describes this exchange, not prior interventions.
                state.update(status='observing',reason='Waiting for measured process response')
                return record
            except Exception:
                if self.permitted(loop_id):await self.stop('Inference failed; no automatic retry')
                raise
        try:job=self.service.enqueue(state['domain'],decide);state['job_id']=job['id']
        except HTTPException:
            state['calls_used']-=1;state['status']='waiting'
