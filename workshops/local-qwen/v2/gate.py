from .packages import check_snapshot,recovery_interval


def gate(package,snapshot,proposal,now):
    reasons=check_snapshot(package,snapshot,now)
    if snapshot.critical or snapshot.trip_latched or snapshot.override:
        reasons.append('Protection requires operator intervention')
    if proposal.status!='adjust': reasons.append('No control action requested')
    elif package.sensor not in proposal.evidence: reasons.append('Required sensor reference missing')
    if snapshot.process_time < snapshot.wait_until: reasons.append('Observation window active')
    if any(x not in snapshot.readings for x in proposal.evidence): reasons.append('Unknown sensor reference')
    if any(x not in package.checks for x in proposal.operator_checks): reasons.append('Unknown operator check')
    if proposal.target is not None:
        low,high=recovery_interval(package.model_dump(),snapshot.model_dump())
        if not low-1e-9<=proposal.target<=high+1e-9:reasons.append('Target outside bench recovery interval')
        if not package.minimum <= proposal.target <= package.maximum: reasons.append('Target outside package bounds')
        if abs(proposal.target-snapshot.target)>package.max_delta+1e-9: reasons.append('Maximum step exceeded')
        if abs(proposal.target-package.initial_target)>package.max_excursion+1e-9: reasons.append('Cumulative excursion exceeded')
        # Installed benches expose a direct measurement target, not raw valve position.
        reading=snapshot.readings.get(package.sensor)
        if reading and reading.quality=='good' and reading.unit==package.unit:
            delta=proposal.target-snapshot.target
            if ((reading.value>package.objective[1] and delta>=-1e-9)
                or (reading.value<package.objective[0] and delta<=1e-9)):
                reasons.append('Target direction does not correct the measured deviation')
    return reasons
