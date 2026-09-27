"""Deterministic timing policy grounded in this simulator, not a physical plant."""
from math import ceil, log


def response_window(domain, changes, tuning=None):
    """Wait roughly one time constant (63% response), not a claim of settling."""
    windows=[]
    tuning=tuning or {}
    for target in changes:
        alpha=None
        if domain=='water':
            alpha={'chlorine_target_mg_l':.08,'finished_water_ph_target':.18}.get(target)
            fallback=15 if 'tank' in target or 'clearwell' in target else 5
        elif domain=='nuclear':
            alpha={'thermal_dispatch_target_mwth':.16*float(tuning.get('thermal_response',1)),
                   'condenser_cooling_pct':.20*float(tuning.get('condenser_response',1)),
                   'turbine_load_target_mwe':.22}.get(target)
            fallback=5
        else:
            # Gas/hydro/battery are slew-limited; frequency has a separate 0.24 pole.
            alpha=.24; fallback=5
        windows.append(ceil(-1/log(1-alpha)) if alpha and 0<alpha<1 else fallback)
    observe=max([5]+windows)
    observe=min(observe,28)
    return {'observe_minutes':observe,'lease_minutes':min(30,observe+2),
            'basis':'simulator_coefficients_not_physical_calibration',
            'interpretation':'Earliest review, not full settling. Storage is integrating; inflow, outflow and remaining capacity govern its response.'}


def temporal_check(minute, changes, prior):
    if not changes or not prior:return []
    elapsed=minute-prior['applied_minute']
    wait=prior['observe_minutes']
    if elapsed<0:return ['Simulation clock changed; supervisory history must be reset']
    if elapsed<wait:return [f'Observe the previous response for {wait-elapsed:g} more simulated minutes before another adjustment']
    if elapsed<2*wait:
        for key,value in changes.items():
            if isinstance(value,bool):continue
            old=prior.get('before_targets',{}).get(key)
            previous=prior.get('applied_targets',{}).get(key)
            if old is not None and previous is not None and (previous-old)*(value-previous)<0:
                return ['Rapid target reversal blocked; observe longer or return to baseline for operator review']
    return []
