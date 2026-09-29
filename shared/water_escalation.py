"""Mandatory operator guidance for the simulated water lab; never executable commands."""
import hashlib
import json
from pathlib import Path

SOP_PATH=Path(__file__).resolve().parents[1]/'services/supervisor/app/plant_sops.json'


def intervention_required(state,control_state=None,episode_status=None):
    alarms=state.get('active_alarms',state.get('alarms',[]))
    return bool(episode_status=='escalate' or state.get('safety_state')=='critical' or state.get('emergency_stop') or
      state.get('active_injections') or any(isinstance(a,dict) and a.get('severity')=='critical' for a in alarms) or
      any(t.get('latched') for t in (control_state or {}).get('trips',[])))


def operator_plan(state,control_state=None,episode_status=None):
    if not intervention_required(state,control_state,episode_status):return None
    book=json.loads(SOP_PATH.read_text());codes=[a['code'] for a in state.get('active_alarms',state.get('alarms',[])) if isinstance(a,dict) and a.get('severity')=='critical']
    mapping={'pressure':['ZONE_','VALVE','DEADHEAD'],'storage':['LEVEL','OVERFLOW'],'disinfection':['CHLORINE','CHEMICAL_FEED','HYPOCHLORITE'],
             'coagulation':['TURBIDITY','COAGULATION','ALUM'],'finished_ph':['PH','ALKALINITY','NAOH']}
    selected=[p for p in book['procedures'] if p['domain']=='water' and any(any(word in code for word in mapping[p['id'].split('.')[1]]) for code in codes)]
    if not selected:selected=[p for p in book['procedures'] if p['domain']=='water']
    actions=[{'id':'verify_protection','instruction':'Verify the alarm, emergency-stop, override and latched-trip states against field feedback. Treat inconsistent or missing evidence as unresolved.',
              'requires_operator':True,'prerequisites':['Operator review before recovery; no automatic trip reset or override removal.']}]
    for procedure in selected:
        actions.append({'id':procedure['id'],'instruction':procedure['steps'][0] if procedure['id'] not in {'water.disinfection','water.finished_ph'} else
            ('Verify residual, CT, flow proof, delivered dose and independent readings before considering recovery.' if procedure['id']=='water.disinfection' else 'Verify downstream pH, alkalinity and chemical delivery before considering recovery.'),
            'sop_id':procedure['id'],'requires_operator':True,'prerequisites':procedure['prerequisites']})
    if any('VALVE' in c or 'DEADHEAD' in c for c in codes):
        actions.append({'id':'verify_flow_path','instruction':'Verify commanded versus actual valve position and pump state; identify forced equipment or an active override. Do not compensate by repeatedly increasing pressure.',
                        'requires_operator':True,'prerequisites':['Operator must resolve the fault under the applicable procedure before recovery is considered.']})
    signals=sorted(set(s for p in selected for s in p['signals']))
    windows={'water.disinfection':12,'water.finished_ph':6,'water.coagulation':15,'water.storage':15,'water.pressure':5}
    return {'version':'1.0.0','source':'deterministic_simulator_sop','episode_status':'escalate','actions':[],
      'operator_intervention_required':True,'recommended_actions':actions,'alarm_codes':codes,
      'sop_version':book['version'],'sop_sha256':hashlib.sha256(SOP_PATH.read_bytes()).hexdigest(),
      'monitoring_plan':{'sensor_ids':signals,'review_every_simulated_minutes':1,
        'minimum_observation_after_operator_authorized_recovery_minutes':max(windows[p['id']] for p in selected),
        'instructions':'Monitor immediately. Observation time starts only after operator-authorized recovery. Confirm reliable feedback, cleared critical conditions and stable trends; elapsed time alone never authorizes reset or recovery.'},
      'recovery_authorization':'Operator review required. Recommendations are not commands and cannot be applied through the AI gate.'}


def response_contract(plan):
    """Model selects explicit SOP references; prose is never accepted as actuator authority."""
    value={'operator_intervention_required':True,
           'recommended_actions':[a['id'] for a in plan['recommended_actions']],
           'evidence_alarm_codes':plan['alarm_codes'],
           'uncertainty':'Root cause unconfirmed; operator verification required.',
           'monitoring_plan':'observe_without_automatic_recovery'}
    properties={}
    for key,item in value.items():
        if isinstance(item,list):
            properties[key]={'type':'array','items':{'type':'string','enum':item} if item else {'type':'string'},
                             'minItems':len(item),'maxItems':len(item)}
        else:properties[key]={'type':'boolean' if isinstance(item,bool) else 'string','enum':[item]}
    return value,{'type':'object','additionalProperties':False,'properties':properties,'required':list(value)}


def validate_response(value,plan):
    from copy import deepcopy
    expected,_=response_contract(plan)
    if not isinstance(value,dict) or set(value)!=set(expected):raise ValueError('Required operator response is missing or incomplete')
    for key,item in expected.items():
        actual=value[key]
        if isinstance(item,list):
            if not isinstance(actual,list) or any(not isinstance(v,str) for v in actual) or len(actual)!=len(set(actual)) or set(actual)!=set(item):
                raise ValueError('Unsupported or missing operator response references')
        elif type(actual) is not type(item) or actual!=item:raise ValueError('Invalid operator intervention or monitoring requirement')
    result=deepcopy(plan);result['source']='model_selected_sop';result['model_selection']=deepcopy(value)
    return result
