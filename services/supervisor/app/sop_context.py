"""Versioned simulated SOP context shared by Qwen and Jev."""
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from shared.supervision import response_window, temporal_check
from .retrieval_ranking import terms

PATH=Path(__file__).with_name('plant_sops.json')


class Procedure(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1)
    domain: Literal['water', 'nuclear', 'grid']
    title: str = Field(min_length=1)
    signals: list[str] = Field(min_length=1)
    targets: list[str] = Field(min_length=1)
    steps: list[str] = Field(min_length=1)
    prerequisites: list[str] = Field(min_length=1)
    escalation: list[str] = Field(min_length=1)
    source: str = Field(min_length=1)
    scope: Literal['simulated_lab_only']
    review_status: Literal['code_grounded_not_operator_validated']


class ContextBook(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: str = Field(pattern=r'^\d+\.\d+\.\d+$')
    scope: Literal['simulated_lab_only']
    principles: list[str] = Field(min_length=1)
    procedures: list[Procedure] = Field(min_length=1)

    @model_validator(mode='after')
    def unique_identifiers(self):
        ids = [procedure.id for procedure in self.procedures]
        if len(ids) != len(set(ids)):
            raise ValueError('SOP identifiers must be unique')
        if any(not p.id.startswith(p.domain + '.') for p in self.procedures):
            raise ValueError('SOP identifier must match its domain')
        return self


def load_book(path=PATH):
    return ContextBook.model_validate_json(Path(path).read_text()).model_dump()


def select_sops(domain, state):
    pack=load_book()
    sensors=state.get('sensors',{})
    alarms=state.get('active_alarms') or state.get('alarms') or []
    query=' '.join([str(state.get('scenario','')),str(alarms),str(state.get('retrieval_question',''))])
    words=set(terms(query))
    docs=[d for d in pack['procedures'] if d['domain']==domain]
    ranked=sorted(docs,key=lambda d:(-len(words&set(terms(json.dumps(d)))),-len(set(d['signals'])&set(sensors)),d['id']))
    objective=None
    if domain=='water' and state.get('scenario')=='chlorine_efficiency_trim':
        ranked.sort(key=lambda p:p['id']!='water.disinfection')
        sensor=sensors.get('chlorine_residual_mg_l',{})
        residual=sensor.get('value')
        fresh=False
        try:
            age=(datetime.fromisoformat(state['simulation_time'])-datetime.fromisoformat(sensor['timestamp'])).total_seconds()
            fresh=0<=age<=120
        except (ValueError,TypeError,KeyError):pass
        reliable=isinstance(residual,(int,float)) and not isinstance(residual,bool) and math.isfinite(residual) and sensor.get('quality')=='good' and fresh
        position=('above_objective' if residual>1.0 else 'below_objective' if residual<.9 else 'within_objective') if reliable else 'unreliable_measurement'
        objective={'id':'chlorine_efficiency_trim_v1','purpose':'Reduce unnecessary chemical consumption in stable operation',
                   'residual_band_mg_l':[0.9,1.0],'unit':'mg/L',
                   'observed_residual_mg_l':residual if reliable else None,'position':position,
                   'evidence_source':'deterministic comparison of captured sensor against scenario objective; not model diagnosis or gate approval',
                   'rule':'If reliable residual is above the objective band, consider a small bounded residual-target reduction after checking CT, flow proof, model agreement and prior observation windows. Hold if within band or still observing. Do not trade away CT, pH or any protection constraint. This objective is not a fault or mandatory escalation.',
                   'relevant_targets':['chlorine_target_mg_l'],
                   'control_relationship':'The chlorine residual target drives a PLC dosing loop. A small target decrease can reduce residual and chemical use over time; the sensor value does not change immediately. Do not alter pressure or storage to solve this objective.',
                   'decision_requirement':'When above objective, assess a bounded decrease. A hold must identify a specific unmet prerequisite, active observation window or uncertainty; being inside broad safety limits alone does not justify a hold. Never raise confidence just to pass a gate. Predicted improvement is not measured recovery.',
                   'observe_minutes':12,'scope':'simulated_lab_only'}
    selected=ranked[:1] if objective else ranked[:3]
    return {'version':pack['version'],'sha256':hashlib.sha256(PATH.read_bytes()).hexdigest(),
            'scope':'simulated_lab_only','authority':'context_only','procedures':selected,'operating_objective':objective,
            'principles':pack['principles'],
            'retrieval':'deterministic_domain_and_signal','query':query,
            'rule':'Live measurements, temporal interlocks and the independent process gate override procedural suggestions.'}


def response_summary(samples):
    if len(samples)<3:return {'status':'insufficient_observations','causal_claim':False,'signals':{}}
    # Distinct simulation minutes only; polling frequency must not inflate evidence.
    unique={s['minute']:s for s in samples}; rows=[unique[k] for k in sorted(unique)]
    if len(rows)<3:return {'status':'insufficient_observations','causal_claim':False,'signals':{}}
    signals={}
    for name in set().union(*(s['values'] for s in rows)):
        pairs=[(s['minute'],s['values'][name]) for s in rows if isinstance(s['values'].get(name),(int,float)) and math.isfinite(s['values'][name])]
        if len(pairs)<3:continue
        xbar=sum(x for x,y in pairs)/len(pairs); ybar=sum(y for x,y in pairs)/len(pairs)
        denominator=sum((x-xbar)**2 for x,y in pairs)
        if denominator<=0:continue
        slope=sum((x-xbar)*(y-ybar) for x,y in pairs)/denominator
        residual=sum((y-ybar-slope*(x-xbar))**2 for x,y in pairs)
        stderr=math.sqrt(residual/(len(pairs)-2)/denominator)
        signals[name]={'n':len(pairs),'first':pairs[0][1],'last':pairs[-1][1],
                       'slope_per_simulated_minute':round(slope,6),'slope_standard_error':round(stderr,6)}
    return {'status':'observed_trend','causal_claim':False,'signals':signals,
            'window_minutes':rows[-1]['minute']-rows[0]['minute'],
            'interpretation':'Descriptive slope only; serial correlation, disturbances and baseline control prevent a causal interpretation.'}


def compact_sample(context, names=None):
    plant=context['plant']
    sensors=plant.get('sensors',{})
    selected=list(sensors) if names is None else names
    values={}; exceptions={}
    for name in selected:
        sensor=sensors.get(name)
        if not isinstance(sensor,dict):
            exceptions[name]='missing'; continue
        quality=sensor.get('quality','good')
        value=sensor.get('value')
        if quality!='good':
            exceptions[name]=quality; continue
        if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value):
            exceptions[name]='invalid'; continue
        values[name]=value
    return {'minute':plant['elapsed_minutes'],'safety_state':plant.get('safety_state'),
            'values':values,'quality_exceptions':exceptions}
