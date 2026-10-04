"""Versioned simulated SOP context shared by Qwen and Jev."""
import hashlib
import json
import math
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
    selected=ranked[:3]
    return {'version':pack['version'],'sha256':hashlib.sha256(PATH.read_bytes()).hexdigest(),
            'scope':'simulated_lab_only','authority':'context_only','procedures':selected,
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
