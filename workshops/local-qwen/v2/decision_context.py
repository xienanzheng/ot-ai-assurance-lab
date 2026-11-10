"""Compact, attributed calculations. No expected answer or generated command."""
import math
from .packages import recovery_interval,candidate_targets


def observed_trend(context):
    """Only compare coherent observations from this target and controller generation."""
    current=context['snapshot'];p=context['package'];tag=p['sensor']
    previous=context.get('recent_observations',[])[-5:]
    points=[x for x in previous if x['process_time']!=current['process_time']]+[current]
    unknown={'reliable':False,'approaching_objective':False,'span_seconds':0,'value_change':None}
    if len(points)<2:return unknown
    for x in points:
        r=x['readings'].get(tag)
        if (x['generation']!=current['generation'] or x['package_hash']!=current['package_hash']
            or x['target']!=current['target'] or any(x[k] for k in ('critical','trip_latched','override'))
            or r is None or r['quality']!='good' or r['unit']!=p['unit']
            or not -1<=x['source_time']-r['source_time']<=5):return unknown
    times=[x['process_time'] for x in points]
    if any(b<=a for a,b in zip(times,times[1:])) or times[-1]-times[0]<2:return unknown
    lo,hi=p['objective']
    values=[x['readings'][tag]['value'] for x in points]
    distances=[max(lo-v,0,v-hi) for v in values]
    approaching=distances[-1]<distances[0]-1e-6 and all(b<=a+1e-6 for a,b in zip(distances,distances[1:]))
    return {'reliable':True,'approaching_objective':approaching,
        'span_seconds':round(times[-1]-times[0],3),'value_change':round(values[-1]-values[0],6)}


def decision_view(context):
    p=context['package'];s=context['snapshot'];tag=p['sensor']
    reading=s['readings'].get(tag);lo,hi=p['objective'];target=s['target']
    def position(value):
        return 'unknown' if value is None else 'below' if value<lo else 'above' if value>hi else 'inside'
    allowed_low=max(p['minimum'],target-p['max_delta'],p['initial_target']-p['max_excursion'])
    allowed_high=min(p['maximum'],target+p['max_delta'],p['initial_target']+p['max_excursion'])
    remaining=max(0,s['wait_until']-s['process_time'])
    midpoint=(lo+hi)/2
    recovery_low,recovery_high=recovery_interval(p,s)
    goal=None if recovery_low>recovery_high else max(recovery_low,min(recovery_high,midpoint))
    entry=None
    usable=goal is not None and reading is not None and reading['quality']=='good' and not context['eligibility'] and not any(s[k] for k in ('critical','trip_latched','override'))
    if usable:
        value=reading['value']
        if lo<=value<=hi:entry=0.
        elif value>hi and goal<hi:entry=p['response_seconds']*math.log((value-goal)/(hi-goal))
        elif value<lo and goal>lo:entry=p['response_seconds']*math.log((goal-value)/(goal-lo))
    def measurement(r):
        if r is None:return None
        return {k:r[k] for k in ('value','unit','quality')} | {'age_at_capture_seconds':round(s['source_time']-r['source_time'],3)}
    return {
        'context_version':'typed-recovery-v4','calculation_source':'server calculations from captured state; not model reasoning',
        'process':p['id'],'sensor_id':tag,'measurement':measurement(reading),'flow':measurement(s['readings'].get('flow')),
        'current_target':target,'objective':{'band':[lo,hi],'measurement_position':position(reading['value'] if reading else None),'target_position':position(target),'target_has_margin':lo+1e-9<target<hi-1e-9},
        'response_planning':{'objective_midpoint':round(midpoint,6),'reachable_goal_this_step':None if goal is None else round(goal,6),
            'nominal_seconds_to_band':None if entry is None else round(entry,3),
            'assumption':'Nominal first-order bench response, constant target, good flow, no added disturbance. Not a measured outcome or real-plant calibration.',
            'boundary_note':'A target exactly on the approached band edge is reached only asymptotically. Prefer an interior target when reachable.'},
        'observation':{'active':remaining>0,'remaining_seconds':round(remaining,3),'duration_after_next_accepted_change':p['observe_seconds']},
        'command_limits':{'allowed_target_interval':[round(allowed_low,6),round(allowed_high,6)],
            'recovery_target_interval':[round(recovery_low,6),round(recovery_high,6)],
            'candidate_targets':candidate_targets(p,s),'candidate_source':'Server-calculated bench SOP choices with interior margin; model selects, no automatic fallback.',
            'lower_headroom':round(max(0,target-allowed_low),6),'upper_headroom':round(max(0,allowed_high-target),6),
            'absolute_bounds':[p['minimum'],p['maximum']],'critical_measurement_limits':p['critical_limits']},
        'protection':{k:s[k] for k in ('critical','trip_latched','override')},
        'prerequisite_failures':context['eligibility'],
        'trend':observed_trend(context),
        'recent_measurements':[{'process_time':r['process_time'],'value':r['readings'][tag]['value'],'quality':r['readings'][tag]['quality']} for r in context.get('recent_observations',[])[-5:] if tag in r['readings']],
        'recent_decisions':context.get('recent_decisions',[])[:2],
        'relationships':p['relationships'],'sop_context':p['sop'],
        'allowed_sensor_ids':list(s['readings']),'operator_checks':p['checks']}
