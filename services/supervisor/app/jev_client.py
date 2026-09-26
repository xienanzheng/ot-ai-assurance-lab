"""Typed Jev decisions. Candidate generation is code; selection is model output."""
import math
import os
from pathlib import Path
from time import perf_counter
import httpx
from shared.models import ControlProposal, SetpointChanges
from shared.limits import SETPOINT_LIMITS, MAX_SETPOINT_STEP
from .ollama_client import InfrastructureProposal, OllamaUnavailable
from .agent_audit import create_audit, update_audit

MODEL = 'typesafe/jev-1.13'
INFRA_LIMITS = {
    'nuclear': {'turbine_load_target_mwe':(300,1050,40), 'condenser_cooling_pct':(50,100,5), 'thermal_dispatch_target_mwth':(0,300,25)},
    'grid': {'gas_dispatch_mw':(0,650,40), 'hydro_dispatch_mw':(80,320,30), 'battery_dispatch_mw':(-100,100,30), 'capacitor_support_mvar':(0,120,20), 'transformer_tap_pct':(-7.5,7.5,1.25), 'demand_response_mw':(0,120,25)},
}


def local_key():
    # Read only the named credential; never return it to the browser or audit record.
    key=os.getenv('OPENROUTER_API_KEY')
    path=Path(__file__).resolve().parents[3]/'.env.local'
    if not key and path.exists():
        for line in path.read_text().splitlines():
            name,sep,value=line.partition('=')
            if sep and name=='OPENROUTER_API_KEY': key=value.strip().strip('\"\'')
    return key


async def availability():
    if os.getenv('HOSTED_MODE')=='true':
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r=await client.get(os.getenv('OLLAMA_BASE_URL','http://inference.lab').rstrip('/')+'/api/providers')
                r.raise_for_status()
                return bool(r.json().get('jev'))
        except httpx.HTTPError: return False
    return bool(local_key())


def candidates(domain, context):
    targets=context['plc']['setpoints'] if domain=='water' else context['plant']['controls']
    limits={k:(*v, MAX_SETPOINT_STEP[k]/2) for k,v in SETPOINT_LIMITS.items()} if domain=='water' else INFRA_LIMITS[domain]
    result={'hold':{'changes':{},'description':'Keep current targets and monitor readings.'},
            'review':{'changes':{},'description':'Keep current targets; request operator review of unsafe or uncertain conditions.'}}
    for key,(low,high,step) in limits.items():
        current=targets.get(key)
        if not isinstance(current,(float,int)) or not math.isfinite(current): continue
        for direction,sign in [('decrease',-1),('increase',1)]:
            value=round(max(low,min(high,current+sign*step)),4)
            if value==current or abs(value-current)>step+1e-8: continue
            result[f'{direction}_{key}']={'changes':{key:value}, 'description':f'Set {key} from {current} to {value} for at most 5 simulated minutes; monitor process response.'}
    return result


def to_proposal(domain, action, confidence):
    if not isinstance(confidence,(float,int)) or not math.isfinite(confidence) or not 0<=confidence<=1:
        raise ValueError('Invalid Jev confidence')
    explanation='Adapter description: '+action['description']
    if domain=='water':
        return ControlProposal(source="jev", changes=SetpointChanges(**action['changes']), expected_effect=action['description'][:240], explanation=explanation[:280],confidence=confidence)
    return InfrastructureProposal(changes=action['changes'],objective=action['description'][:180],explanation=explanation,confidence=confidence)


async def propose(domain, context):
    options=candidates(domain,context)
    plant=context['plant']
    state={k:plant[k] for k in ['simulation_time','scenario','controller_mode','safety_state','sensors','equipment','active_alarms','alarms','twin_health','model_health'] if k in plant}
    state['recent_trends']=plant.get('recent_trends') or {k:v[-12:] for k,v in plant.get('history',{}).items() if isinstance(v,list)}
    state['prior_decision']=plant.get('ai_decision')
    state['current_targets']=context.get('plc',{}).get('setpoints',plant.get('controls',{}))
    state['control_state']=context.get('plc',{}).get('control_state',{})
    state['candidate_controls']=options
    payload={'model':MODEL,'state':state,'questions':{'response':{'type':'choice',
        'instructions':'Select one bounded supervisory action for this simulated '+domain+' plant. Safety first. Use measured quality and trends. If measurements are untrusted, plant critical, or an action conflicts with protections, choose review. Choose hold if no adjustment is justified. Descriptions are candidates, not evidence they will work. No direct actuator authority.',
        'criteria':{k:v['description'] for k,v in options.items()}}}}
    identifier=create_audit(domain,payload)
    update_audit(identifier,provider='jev',model_name=MODEL,candidates=options,provenance='OpenRouter hosted Jev',
        interpretation='Jev selects a code-defined candidate. The adapter description is not model reasoning. Choice probabilities are not calibrated safety scores.')
    start=perf_counter()
    try:
        hosted=os.getenv('HOSTED_MODE')=='true'
        endpoint=os.getenv('OLLAMA_BASE_URL','http://inference.lab').rstrip('/')+'/api/decisions' if hosted else 'https://openrouter.ai/api/alpha/decisions'
        headers={} if hosted else {'Authorization':'Bearer '+(local_key() or ''),'X-Title':'OT AI Assurance Lab'}
        if not hosted and not local_key(): raise ValueError('Jev credential is not configured')
        async with httpx.AsyncClient(timeout=45) as client:
            response=await client.post(endpoint,json=payload,headers=headers)
            if response.status_code>=400: raise ValueError(f'Jev unavailable (HTTP {response.status_code})')
            result=response.json()
        update_audit(identifier,response=result,latency_seconds=perf_counter()-start)
        answer=result.get('answers',{}).get('response',{})
        choice=answer.get('choice')
        if choice not in options: raise ValueError('Jev returned an unknown candidate')
        proposal=to_proposal(domain,options[choice],answer.get('confidence'))
        if domain=='water': proposal.decision_id=identifier
        else: proposal._audit_id=identifier
        update_audit(identifier,selected_candidate=choice,status='proposed')
        return proposal,identifier
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else 'Jev connection or response failed'
        update_audit(identifier,status='invalid_or_unavailable',error=message,applied=False,gate={'status':'not_submitted'},latency_seconds=perf_counter()-start)
        raise OllamaUnavailable(message,identifier) from None
