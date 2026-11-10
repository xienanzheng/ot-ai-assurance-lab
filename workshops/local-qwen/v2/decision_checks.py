"""Explicit SOP consistency checks, separately attributed from model judgement.

These checks can flag a proposal; they never manufacture a replacement command.
The directional rule applies to the two installed direct-target bench packages.
"""
from .decision_context import decision_view


def proposal_comparisons(context, proposal):
    view=decision_view(context);target=proposal.target
    lo,hi=view['objective']['band'];allowed=view['command_limits']['allowed_target_interval']
    delta=None if target is None else target-view['current_target']
    position=view['objective']['measurement_position']
    return {'source':'server arithmetic from captured state and proposed target; not a model verdict',
        'target_position':'not proposed' if target is None else 'below' if target<lo else 'above' if target>hi else 'inside',
        'target_in_allowed_interval':None if target is None else allowed[0]-1e-9<=target<=allowed[1]+1e-9,
        'target_change':None if delta is None else round(delta,6),
        'corrective_direction':None if delta is None else (position=='above' and delta<-1e-9) or (position=='below' and delta>1e-9),
        'unknown_sensor_ids':[v for v in proposal.evidence if v not in view['allowed_sensor_ids']],
        'unknown_check_ids':[v for v in proposal.operator_checks if v not in view['operator_checks']]}


def proposal_findings(context, proposal):
    view=decision_view(context);findings=[]
    def add(issue,reason):findings.append({'issue':issue,'reason':reason})
    active=[k for k,v in view['protection'].items() if v]
    failures=view['prerequisite_failures']
    blocked=bool(active or failures)
    if blocked and proposal.status!='escalate':
        add('protection_active','Escalation required: '+', '.join(active+failures))
    invalid=[v for v in proposal.evidence if v not in view['allowed_sensor_ids']]
    invalid += [v for v in proposal.operator_checks if v not in view['operator_checks']]
    if invalid:add('invalid_reference','Unknown reference: '+', '.join(invalid))
    if proposal.status=='escalate' and not proposal.operator_checks:
        add('missing_evidence','Escalation needs an approved operator-check ID.')
    if proposal.status in ('hold','adjust') and view['sensor_id'] not in proposal.evidence:
        add('missing_evidence','Cite the measured sensor: '+view['sensor_id'])
    if proposal.status=='adjust':
        lo,hi=view['command_limits']['allowed_target_interval'];t=proposal.target
        if t<lo-1e-9 or t>hi+1e-9:add('out_of_bounds',f'Target {t:g} outside permitted [{lo:g}, {hi:g}].')
        recovery_low,recovery_high=view['command_limits']['recovery_target_interval']
        if not recovery_low-1e-9<=t<=recovery_high+1e-9:
            add('recovery_interval',f'Target {t:g} outside reachable bench recovery interval [{recovery_low:g}, {recovery_high:g}].')
        if view['observation']['active']:add('waiting',f"Wait {view['observation']['remaining_seconds']:g}s before another change.")
        position=view['objective']['measurement_position'];delta=t-view['current_target']
        if (position=='above' and delta>=-1e-9) or (position=='below' and delta<=1e-9):
            add('wrong_direction',f"Measurement {position} objective; target {view['current_target']:g} → {t:g} does not correct it.")
        band_low,band_high=view['objective']['band']
        if ((position=='above' and abs(t-band_high)<=1e-9 and lo<band_high-1e-9)
            or (position=='below' and abs(t-band_low)<=1e-9 and hi>band_low+1e-9)):
            add('boundary_target','The approached band edge is only reached asymptotically; an interior target is reachable within this step. Aim inside the band.')
    if not blocked and not view['observation']['active']:
        pos=view['objective']['measurement_position'];limits=view['command_limits']
        settling=view['objective']['target_has_margin'] and view['trend']['approaching_objective']
        if proposal.status=='hold' and pos in ('above','below') and not settling:
            add('unsupported_hold',f"Measurement {pos} objective; no active wait or demonstrated settling to an in-band target.")
        if proposal.status=='escalate':
            headroom=limits['lower_headroom'] if pos=='above' else limits['upper_headroom']
            if pos=='inside' or (pos in ('above','below') and headroom>1e-9):
                add('unsupported_escalation','No captured protection/prerequisite failure or exhausted correction headroom supports escalation.')
    return findings
