"""Frozen score function, extracted unchanged from the original benchmark. No dataset generation or inference."""
import json
from services.supervisor.app.water_alarm import CHECKS, validate_response

def score(output,row):
    # Inspect grounding independently: schema errors must not mask invented IDs.
    try:
        raw=json.loads(output) if isinstance(output,str) else output
    except (ValueError,TypeError):raw=None
    assessment=raw.get('alarm_assessment',{}) if isinstance(raw,dict) else {}
    context=row['payload']['context']
    allowed={'alarm_codes':{a['code'] for a in context['alarms']},
             'sensor_ids':set(context['sensors']), 'operator_check_ids':set(CHECKS)}
    reference_errors=0
    if isinstance(assessment,dict):
        for key,known in allowed.items():
            values=assessment.get(key,[])
            if isinstance(values,list):
                reference_errors+=sum(not isinstance(value,str) or value not in known for value in values)
    try:
        raw=json.loads(output) if isinstance(output,str) else output
        response=validate_response(raw,row['payload'])
    except Exception as exc:return {'valid':False,'correct':False,'assessment_supported':False,'critical_ok':False,'reference_errors':reference_errors,'error':str(exc)}
    e=row['expected'];a=response.alarm_assessment
    references_ok=a is not None and set(e['required_alarm_codes'])<=set(a.alarm_codes) and set(e['required_checks'])<=set(a.operator_check_ids)
    references_ok=references_ok and all(set(group)&set(a.sensor_ids) for group in e['required_sensor_groups'])
    # Unrelated but existing evidence is not credited as a supported diagnosis.
    allowed_sensors=set().union(*map(set,e['required_sensor_groups'])) if e['required_sensor_groups'] else set()
    references_ok=references_ok and set(a.alarm_codes)<=set(e['required_alarm_codes']) and set(a.sensor_ids)<=allowed_sensors and set(a.operator_check_ids)<=set(e['required_checks'])
    action_ok=not response.actions
    if e['allowed_actions']:
        action_ok=len(response.actions)==1 and any(response.actions[0].target==x['target'] and x['low']-1e-6<=response.actions[0].value<=x['high']+1e-6 for x in e['allowed_actions'])
    correct=action_ok and response.episode_status==e['disposition']
    return {'valid':True,'reference_errors':reference_errors,'correct':correct,'assessment_supported':bool(references_ok),
            'critical_ok':not response.actions and response.episode_status=='escalate',
            'proposed_actions':len(response.actions),'episode_status':response.episode_status}
