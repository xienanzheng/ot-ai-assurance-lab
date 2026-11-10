import asyncio
import time
from uuid import uuid4
from .contracts import CommandRequest, AuditResult, digest
from .packages import check_snapshot
from .gate import gate


class Supervisor:
    def __init__(self,package,journal,receiver,providers,auditor):
        self.package=package; self.journal=journal; self.receiver=receiver
        self.providers=providers; self.auditor=auditor
        self.latest=None; self.history=[]; self.capture_error='Connecting'; self.busy=False
        self.policy='off'; self.epoch=0; self.jobs=set(); self.arming=False
        self.feedback=dict(active=False,calls=0,limit=0,provider='',apply=False,next_at=0,started=0,reason='Not started')
    def records(self):
        return sorted(self.journal.list('record:'),key=lambda r:r['created_at'],reverse=True)
    def save(self,r): self.journal.put_many({'record:'+r['id']:r})
    async def recover(self):
        await self.receiver.stop()
        for r in self.records():
            if r['status']=='running':
                r.update(status='interrupted',error='Supervisor restarted before submission')
                self.save(r)
            if r['status'] in ('submitting','unknown'):
                try: status=await self.receiver.status(r['id'])
                except Exception: status=None
                if status is not None:
                    try: self.validate_ack(CommandRequest.model_validate(r['command_request']),status)
                    except Exception: status=None
                r['command']=status
                r['status']='reconciled' if status is not None else 'unknown'
                self.save(r)
    async def arm(self,policy):
        if self.busy or self.arming or self.feedback['active']: raise ValueError('Stop active analysis/feedback before arming')
        if any(r['status'] in ('unknown','submitting') for r in self.records()): raise ValueError('Unresolved command outcome')
        self.epoch+=1; epoch=self.epoch; self.arming=True; self.latest=None
        try:
            await self.receiver.arm(policy)
            if self.epoch!=epoch:
                await self.receiver.stop()
                raise ValueError('Arming cancelled by stop')
            self.policy=policy
        finally:
            self.arming=False
    async def stop(self):
        self.epoch+=1; self.feedback['active']=False; self.feedback['reason']='Stopped'
        await self.receiver.stop()
    async def observe(self,snapshot):
        self.latest=snapshot; self.capture_error=''
        self.history.append(snapshot.model_dump()); self.history=self.history[-600:]
        if snapshot.critical or snapshot.trip_latched or snapshot.override or check_snapshot(self.package,snapshot,time.time()):
            if self.feedback['active'] or snapshot.armed: await self.stop()
        for r in self.records():
            outcome=r.get('outcome')
            if not outcome or outcome['status']!='observing': continue
            if snapshot.generation!=r['input']['snapshot']['generation'] or snapshot.critical or snapshot.trip_latched:
                outcome['status']='interrupted'; outcome['reason']='Protection or ownership changed'
            elif not check_snapshot(self.package,snapshot,time.time()):
                value=snapshot.readings[self.package.sensor].value
                inside=self.package.objective[0]<=value<=self.package.objective[1]
                if not inside: outcome['inside_since']=None
                elif outcome.get('inside_since') is None: outcome['inside_since']=snapshot.process_time
                if snapshot.process_time>=outcome['review_after'] and inside and snapshot.process_time-outcome['inside_since']>=self.package.sustain_seconds:
                    outcome['status']='completed'
                elif snapshot.process_time-outcome['started_at']>=self.package.max_episode_seconds:
                    outcome['status']='not_recovered'
                outcome['last_value']=value; outcome['last_process_time']=snapshot.process_time
            else:
                outcome['inside_since']=None
            self.save(r)
    def context(self,snapshot):
        reading=snapshot.readings.get(self.package.sensor)
        value=reading.value if reading else None
        low,high=self.package.objective
        remaining=max(0,snapshot.wait_until-snapshot.process_time)
        return dict(package=self.package.model_dump(),snapshot=snapshot.model_dump(),
            current_facts={'source':'deterministic calculation from captured snapshot',
                'measurement_relative_to_objective':'unknown' if value is None else 'below' if value<low else 'above' if value>high else 'inside',
                'observation_active':remaining>0,'observation_remaining_seconds':remaining},
            observed_protection={'critical':snapshot.critical,'latched_trip':snapshot.trip_latched,'override':snapshot.override},
            eligibility=check_snapshot(self.package,snapshot,time.time()),
            recent_observations=[s for s in self.history if s['package_hash']==snapshot.package_hash and s['generation']==snapshot.generation][-5:],
            recent_decisions=[dict(proposal=r.get('proposal'),command=r.get('command'),outcome=r.get('outcome')) for r in [r for r in self.records() if r['package_hash']==self.package.fingerprint() and r['input']['snapshot']['generation']==snapshot.generation][:3]])
    async def analyse(self,provider,apply=False):
        if self.busy or self.arming: raise ValueError('An analysis already owns supervision')
        if self.latest is None: raise ValueError('No captured snapshot')
        if provider not in self.providers: raise ValueError('Unknown provider')
        if any(r['status'] in ('unknown','submitting') for r in self.records()): raise ValueError('Reconcile unknown outcome before another analysis')
        self.busy=True
        try:
            epoch=self.epoch; captured=self.latest; context=self.context(captured)
            model=self.providers[provider]; started=time.monotonic()
            r=dict(id=str(uuid4()),created_at=time.time(),provider=model.name,package_hash=self.package.fingerprint(),
                audit_policy=self.policy,audit_provider=self.auditor.name if self.policy!='off' else None,
                input=context,request=model.decision_request(context) if hasattr(model,'decision_request') else {'fixture':True},
                proposal=None,audit=None,gate=None,command=None,readback=None,outcome=None,status='running')
            self.save(r)
            try:
                proposal=await asyncio.wait_for(model.decide(context),50)
                r['raw_response']=getattr(model,'last_response',None)
                r['decision_evidence']=getattr(model,'last_decision_trace',None)
                r['proposal']=proposal.model_dump(); r['inference_seconds']=time.monotonic()-started
            except Exception as error:
                r.update(status='inference_failed',error=str(error)[:500],raw_response=getattr(model,'last_response',None),decision_evidence=getattr(model,'last_decision_trace',None)); self.save(r); return r
            if self.policy=='required':
                r['audit']=await self.review(context,proposal,r)
            current=self.latest
            reasons=gate(self.package,current,proposal,time.time())
            if epoch!=self.epoch or current.generation!=captured.generation: reasons.append('Analysis disarmed by control transition')
            if self.policy=='required' and r['audit']['status']!='passed': reasons.append('Audit did not pass')
            if proposal.status!='adjust':
                r.update(status='escalated' if proposal.status=='escalate' else 'held',gate={'status':'not_requested','reasons':reasons})
            elif reasons:
                r.update(status='blocked',gate={'status':'rejected','reasons':reasons})
            elif not apply:
                r.update(status='evaluated',gate={'status':'accepted','reasons':[]})
            else:
                now=time.time()
                request=CommandRequest(id=r['id'],snapshot=captured,proposal=proposal,issued_at=now,expires_at=now+30,
                    policy=self.policy,audit=AuditResult.model_validate(r['audit']) if r['audit'] else None)
                r.update(status='submitting',gate={'status':'accepted','reasons':[]},command_request=request.model_dump())
                self.save(r)  # Durable intent before any transport side effect.
                try:
                    result=await self.receiver.apply(request)
                    self.validate_ack(request,result)
                    r['command']=result; r['status']=result['status']
                    if result.get('actually_applied'):
                        for old in self.records():
                            if old['id']!=r['id'] and (old.get('outcome') or {}).get('status')=='observing':
                                old['outcome'].update(status='superseded',reason='A later target was accepted',superseded_by=r['id'])
                                self.save(old)
                        r['readback']=(await self.receiver.snapshot()).model_dump()
                        if r['readback']['generation']!=captured.generation or r['readback']['target']!=proposal.target:
                            raise ValueError('Target readback mismatch')
                        r['outcome']=dict(status='observing',started_at=result['process_time'],
                            review_after=result['process_time']+self.package.observe_seconds,inside_since=None)
                except Exception as error:
                    r.update(status='unknown',error=str(error)[:500])
                    self.feedback['active']=False
            self.save(r)
            if self.policy=='observe':
                async def background():
                    r['audit']=await self.review(context,proposal,r)
                    # Reload so a later monitoring outcome is not overwritten.
                    saved=self.journal.get('record:'+r['id']); saved['audit']=r['audit']; saved['audit_evidence']=r.get('audit_evidence'); self.save(saved)
                task=asyncio.create_task(background()); self.jobs.add(task); task.add_done_callback(self.jobs.discard)
            return r
        finally:
            self.busy=False
    def validate_ack(self,request,result):
        if not result or result.get('id')!=request.id or result.get('request_hash')!=digest(request) or result.get('generation')!=request.snapshot.generation:
            raise ValueError('Acknowledgement identity mismatch')
        if result.get('actually_applied') and (result.get('status')!='applied' or result.get('accepted_target')!=request.proposal.target):
            raise ValueError('Acknowledged target mismatch')
    async def review(self,context,proposal,record=None):
        h=digest({'snapshot':context['snapshot'],'proposal':proposal.model_dump()})
        trace={'provider':self.auditor.name,'proposal_hash':h}
        try:
            if hasattr(self.auditor,'audit_request'):trace['request']=self.auditor.audit_request(context,proposal)
            if hasattr(self.auditor,'audit_with_evidence'):
                result,trace=await asyncio.wait_for(self.auditor.audit_with_evidence(context,proposal),50)
            else:result=await asyncio.wait_for(self.auditor.audit(context,proposal),50)
            if result.proposal_hash!=h: raise ValueError('Audit hash mismatch')
            return result.model_dump()
        except Exception as error:
            trace['error']=str(error)[:300] or 'Audit unavailable'
            return AuditResult(status='unavailable',reason=str(error)[:300] or 'Audit unavailable',proposal_hash=h).model_dump()
        finally:
            if record is not None:record['audit_evidence']=trace
    def command_wait_until(self,snapshot):
        # An accepted command is known before the next OPC UA sample arrives.
        # Keep that observation deadline without inventing a newer sensor value.
        deadlines=[snapshot.wait_until]
        for record in self.records():
            command=record.get('command') or {}
            if (record['package_hash']==snapshot.package_hash
                and command.get('actually_applied')
                and command.get('generation')==snapshot.generation):
                deadlines.append(command['process_time']+self.package.observe_seconds)
        return max(deadlines)
    def start_feedback(self,provider,limit,apply):
        if self.busy or self.feedback['active']: raise ValueError('Supervision is already owned')
        if provider not in self.providers or not 1<=limit<=12: raise ValueError('Invalid provider or budget')
        self.feedback=dict(active=True,calls=0,limit=limit,provider=provider,apply=apply,
            next_at=self.command_wait_until(self.latest) if self.latest else 0,started=time.monotonic(),reason='Monitoring')
    async def feedback_tick(self):
        f=self.feedback
        if not f['active'] or self.busy or self.latest is None: return
        if f['calls']>=f['limit'] or time.monotonic()-f['started']>=3600:
            f.update(active=False,reason='Budget complete · observation continues'); return
        if check_snapshot(self.package,self.latest,time.time()):
            await self.stop(); f['reason']='Required measurements unavailable'; return
        if self.latest.process_time<max(f['next_at'],self.command_wait_until(self.latest)): return
        f['calls']+=1
        await self.analyse(f['provider'],f['apply'])
        f['next_at']=self.latest.process_time+self.package.observe_seconds
        if f['calls']>=f['limit']: f.update(active=False,reason='Budget complete · observation continues')
