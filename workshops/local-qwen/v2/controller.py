import math
import threading
import time
from uuid import uuid4
from .contracts import Snapshot, Measurement, digest
from .gate import gate


class Controller:
    def __init__(self,package,journal):
        self.package=package; self.journal=journal; self.lock=threading.RLock()
        self.key='controller:'+package.id; self.scan_error=''
        previous=journal.get(self.key)
        self.state=previous if previous and previous['package_hash']==package.fingerprint() else self.initial()
        self.state.setdefault('sample_time', time.time())
        self.state.update(generation=str(uuid4()),armed=False,policy='off')
        # Accepted setpoints are retained. Restart never replays a command or re-arms.
        journal.put_many({self.key:self.state})

    def initial(self):
        p=self.package
        return dict(package_hash=p.fingerprint(),generation=str(uuid4()),armed=False,policy='off',
            target=p.initial_target,value=p.initial_value,process_time=0.,sequence=0,wait_until=0.,
            critical=False,trip_latched=False,override=False,flow=1.,quality='good',stale=False,
            disturbance=0.,lease_until=0.,sample_time=time.time())

    def snapshot(self):
        with self.lock:
            s=self.state; now=s['sample_time']; timestamp=now-30 if s['stale'] else now
            return Snapshot(site='bench',package_hash=s['package_hash'],generation=s['generation'],
                sequence=s['sequence'],source_time=now,process_time=s['process_time'],target=s['target'],armed=s['armed'],
                critical=s['critical'],trip_latched=s['trip_latched'],override=s['override'],wait_until=s['wait_until'],
                readings={self.package.sensor:Measurement(value=s['value'],unit=self.package.unit,source_time=timestamp,quality='bad' if self.scan_error else s['quality']),
                          'flow':Measurement(value=s['flow'],unit='L/s',source_time=now)})

    def save(self, **changes):
        next_state={**self.state,**changes}
        writes={self.key:next_state}
        if 'sequence' not in changes:
            writes['event:'+str(uuid4())]={'time':time.time(),'package_hash':self.package.fingerprint(),'type':'controller_transition','changes':changes}
        self.journal.put_many(writes)
        self.state=next_state

    def arm(self,policy='off'):
        if policy not in ('off','observe','required'): raise ValueError('Unknown audit policy')
        with self.lock:
            if self.state['trip_latched'] or self.state['critical']: raise ValueError('Protection remains active')
            # New ownership epoch invalidates all earlier captured proposals.
            self.save(armed=True,policy=policy,generation=str(uuid4()),lease_until=0.)
        return self.snapshot()

    def stop(self):
        with self.lock: self.save(armed=False,generation=str(uuid4()))
        return self.snapshot()

    def reset(self):
        with self.lock:
            state=self.initial(); self.journal.put_many({self.key:state}); self.state=state
        return self.snapshot()

    def inject(self,name):
        with self.lock:
            if name=='normal': self.save(critical=False,override=False,flow=1.,quality='good',stale=False,disturbance=0.,value=self.package.initial_value)
            elif name=='critical': self.save(critical=True,trip_latched=True,armed=False,value=self.package.critical_limits[1]+1)
            elif name=='no_flow': self.save(flow=0.)
            elif name=='bad_sensor': self.save(quality='bad')
            elif name=='stale_sensor': self.save(stale=True)
            elif name=='override': self.save(override=True)
            elif name=='drift': self.save(disturbance=self.package.disturbance)
            else: raise ValueError('Unknown scenario')
        return self.snapshot()

    def step(self,seconds):
        if not 0<seconds<=600: raise ValueError('Invalid process step')
        with self.lock:
            s=self.state; p=self.package
            value=s['value']
            if s['flow']>0 and not s['override'] and not s['critical']:
                value+=(s['target']+s['disturbance']-value)*(1-math.exp(-seconds/p.response_seconds))
            critical=not p.critical_limits[0]<value<p.critical_limits[1]
            self.save(sample_time=time.time(),value=value,process_time=s['process_time']+seconds,sequence=s['sequence']+1,
                critical=critical,trip_latched=s['trip_latched'] or critical,armed=s['armed'] and not critical and not (s['lease_until'] and s['process_time']+seconds>=s['lease_until']))
            self.scan_error=''
        return self.snapshot()

    def status(self,command_id): return self.journal.get('command:'+command_id)

    def apply(self,request):
        with self.lock:
            key='command:'+request.id; fingerprint=digest(request)
            existing=self.journal.get(key)
            if existing:
                if existing['request_hash']==fingerprint: return existing
                return dict(status='rejected',reason='command ID payload mismatch',id=request.id)
            now=time.time(); current=self.snapshot(); captured=request.snapshot
            reasons=gate(self.package,current,request.proposal,now)+gate(self.package,captured,request.proposal,captured.source_time)
            if now-captured.source_time>self.package.max_decision_age or captured.source_time>now+1:
                reasons.append('Captured decision context expired')
            if not current.armed or not captured.armed: reasons.append('Controller is not armed')
            if captured.site!=current.site or captured.generation!=current.generation: reasons.append('Ownership or site changed')
            if captured.target!=current.target: reasons.append('Target changed since capture')
            if request.issued_at>now+1 or request.expires_at<now or request.expires_at-request.issued_at>60:
                reasons.append('Invalid command lifetime')
            if request.policy!=self.state['policy']: reasons.append('Audit policy changed')
            if self.state['policy']=='required':
                h=digest({'snapshot':captured.model_dump(),'proposal':request.proposal.model_dump()})
                if not request.audit or request.audit.status!='passed' or request.audit.proposal_hash!=h:
                    reasons.append('Matching audit pass required')
            result=dict(id=request.id,request_hash=fingerprint,generation=current.generation,
                status='rejected' if reasons else 'applied',reason='; '.join(dict.fromkeys(reasons)) or 'Target accepted',
                accepted_target=current.target if reasons else request.proposal.target,process_time=current.process_time,
                actually_applied=not reasons)
            writes={key:result}
            if not reasons:
                state={**self.state,'target':request.proposal.target,'wait_until':current.process_time+self.package.observe_seconds,
                       'lease_until':current.process_time+300}
                writes[self.key]=state
            self.journal.put_many(writes)
            if not reasons: self.state=state
            return result
