"""Explicit fast supervisory profile; lossless tables and smaller output contract."""
from copy import deepcopy
import json
from .plant_knowledge import digest


def table(rows):
    if not rows or not all(isinstance(row,dict) for row in rows):
        return rows
    columns=list(dict.fromkeys(key for row in rows for key in row))
    if any(set(row)!=set(columns) for row in rows):
        return rows
    constants={key:deepcopy(rows[0][key]) for key in columns if all(row[key]==rows[0][key] for row in rows)}
    varying=[key for key in columns if key not in constants]
    values=[[deepcopy(row[key]) for key in varying] for row in rows]
    encoded={'encoding':'rows-v1','count':len(rows),'constants':constants,'columns':varying,'rows':values}
    return encoded if len(json.dumps(encoded))<len(json.dumps(rows)) else rows


def column_history(rows):
    if not rows or not all(isinstance(row,dict) for row in rows):
        return rows
    def column(values):
        if all(v==values[0] for v in values):
            return {'constant':deepcopy(values[0])}
        if all(isinstance(v,dict) and set(v)==set(values[0]) for v in values):
            return {'fields':{k:column([v[k] for v in values]) for k in values[0]}}
        return {'values':deepcopy(values)}
    packed={'encoding':'columns-v1','count':len(rows),'data':column(rows)}
    return packed if len(json.dumps(packed))<len(json.dumps(rows)) else rows


def unpack_history(packed):
    if isinstance(packed,list): return packed
    def decode(node,i):
        if 'constant' in node:return deepcopy(node['constant'])
        if 'values' in node:return deepcopy(node['values'][i])
        return {k:decode(v,i) for k,v in node['fields'].items()}
    return [decode(packed['data'],i) for i in range(packed['count'])]


def compact_context(state, domain=None):
    state=deepcopy(state)
    if domain == 'water' and 'sensor_values' in state:
        try:
            from plc_app.controller import SafetyGate
        except ModuleNotFoundError:
            from services.plc_control.app.controller import SafetyGate
        from shared.limits import LIMITS
        required = SafetyGate._dependencies(set(state.get('allowed_target_ranges', {}))) | set(LIMITS)
        required |= {'coagulant_dose_actual_mg_l','chlorine_contact_time_min','chemical_feed_flow_proof',
                     'leak_flow_m3h','water_temperature_c','hocl_fraction_pct'}
        readings=state['sensor_values']
        selected={key:row for key,row in readings.items() if key in required or row[2] != 'good'}
        state['sensor_values']=selected
        state['context_selection']={'rule':'all gate dependencies, bounded process readings, and every non-good sensor',
                                    'omitted_normal_auxiliary_sensor_count':len(readings)-len(selected)}
        plc=state.get('plc_control_state',{})
        # PID internals are baseline-controller implementation details, not AI actions.
        plc.pop('control_loops',None)
        aux=state.get('auxiliary_equipment',{})
        devices=aux.get('devices') if isinstance(aux,dict) else None
        if isinstance(devices,list):
            abnormal=[d for d in devices if d.get('status') != 'running'
                      or abs(d.get('feedback_pct',0)-d.get('setpoint_pct',0))>1]
            aux['devices']=abnormal
            aux['normal_running_device_count']=len(devices)-len(abnormal)
    timeline=state.get('research_context',{}).get('timeline')
    if isinstance(timeline,dict):
        for key in ['recent_samples','samples','previous_decisions']:
            if isinstance(timeline.get(key),list):timeline[key]=column_history(timeline[key])
    aux=state.get('auxiliary_equipment',{})
    if isinstance(aux,dict) and isinstance(aux.get('devices'),list):aux['devices']=table(aux['devices'])
    return state


def apply_profile(payload, domain, profile):
    if profile not in {'standard','fast'}:raise ValueError('Unknown inference profile')
    payload=deepcopy(payload)
    state=json.loads(payload['messages'][-1]['content'])
    original=json.dumps(state,separators=(',',':'))
    metadata={'profile':profile,'original_context_bytes':len(original.encode()),'context_sha256':digest(state)}
    if profile=='fast':
        compact=compact_context(state, domain)
        payload['messages'][-1]['content']=json.dumps(compact,separators=(',',':'))
        payload['messages'][0]['content'] += (
            ' Fast supervisory exchange: propose at most two changes; use one short sentence per text field. '
            'Do not output identifiers, timestamps or source fields. '
            'History encoding columns-v1 stores repeated values under constant, varying values under values, '
            'and nested objects under fields; array position is the observation order. '
            'Equipment rows-v1 uses columns and rows plus constants shared by all rows. '
            'Tables preserve the supplied observations. Full state is retained in the audit; normal auxiliary telemetry and PID internals may be omitted from this prompt. Current limits and protection still govern.')
        payload['think']=False
        payload['options']['num_predict']=192
        if domain == 'water':
            targets = list(payload['format']['$defs']['SetpointChanges']['properties'])
        else:
            targets = list(state['allowed_changes'])
        payload['format'] = {
            'type':'object','additionalProperties':False,
            'properties':{
                'actions':{'type':'array','maxItems':2,'items':{
                    'type':'object','additionalProperties':False,
                    'properties':{'target':{'type':'string','enum':targets},
                                  'value':{'anyOf':[{'type':'number'},{'type':'boolean'}]}},
                    'required':['target','value']}},
                'confidence':{'type':'number','minimum':0,'maximum':1},
                'reason':{'type':'string','minLength':1,'maxLength':96},
                'episode_status':{'type':'string','enum':['continue','resolved','escalate']}},
            'required':['actions','confidence','reason','episode_status']}
        payload['messages'][0]['content'] += (
            ' Output actions [{target,value}], confidence, reason, episode_status only. '
            'Use actions [] to hold or escalate; never echo unchanged setpoints. '
            'The reason must describe the chosen actions in at most ten words; do not repeat readings. '
            'If no adjustment is justified, hold baseline targets rather than invent a change. '
            'A resolved claim needs the supplied sustained-recovery evidence.')
        metadata['uncompressed_context']=state
    metadata['sent_context_bytes']=len(payload['messages'][-1]['content'].encode())
    payload['_inference_profile']=metadata
    return payload


def normalize_fast_response(content, payload, domain):
    import math
    from pydantic import BaseModel, ConfigDict, Field
    from typing import Any, Literal
    class Action(BaseModel):
        model_config = ConfigDict(extra='forbid')
        target: str
        value: Any
    class Response(BaseModel):
        model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
        actions: list[Action] = Field(max_length=2)
        confidence: float = Field(ge=0,le=1)
        reason: str = Field(min_length=1,max_length=96)
        episode_status: Literal['continue','resolved','escalate']
    response = Response.model_validate_json(content)
    allowed = payload['format']['properties']['actions']['items']['properties']['target']['enum']
    changes = {}
    for action in response.actions:
        if action.target not in allowed or action.target in changes:
            raise ValueError('Unknown or duplicate fast action')
        if action.target == 'backwash_request':
            if type(action.value) is not bool: raise ValueError('Backwash requires a boolean')
        elif type(action.value) not in (int,float) or not math.isfinite(action.value):
            raise ValueError('Setpoints require finite numeric values')
        changes[action.target] = action.value
    normalized = {'changes':changes,'confidence':response.confidence,'explanation':response.reason}
    if domain == 'water':
        normalized.update(expected_effect=response.reason,episode_status=response.episode_status)
    else:
        normalized['objective'] = 'Bounded simulator supervision'
    return normalized
