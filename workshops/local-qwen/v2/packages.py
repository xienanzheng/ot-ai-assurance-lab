from pathlib import Path
import json
import re
from .contracts import Package, Snapshot

ROOT = Path(__file__).resolve().parent.parent / 'process_packages'


def recovery_interval(package, snapshot):
    """Bench SOP range, with 10% interior margin when reachable this step.

    Only for direct measurement-target capabilities in the installed benches.
    It supplies constraints, never a selected command or a model verdict.
    """
    p=package;s=snapshot;target=s['target']
    low=max(p['minimum'],target-p['max_delta'],p['initial_target']-p['max_excursion'])
    high=min(p['maximum'],target+p['max_delta'],p['initial_target']+p['max_excursion'])
    reading=s['readings'].get(p['sensor']);band_low,band_high=p['objective']
    if reading and reading['quality']=='good' and reading['unit']==p['unit']:
        value=reading['value'];margin=.1*(band_high-band_low)
        inner_low=max(low,band_low+margin);inner_high=min(high,band_high-margin)
        if value>band_high:inner_high=min(inner_high,target-1e-6)
        elif value<band_low:inner_low=max(inner_low,target+1e-6)
        else:return low,high
        # An already interior target may need compensation for an unmodelled
        # disturbance. Do not forbid the existing bounded correction authority.
        if not band_low+1e-9<target<band_high-1e-9 and inner_low<=inner_high:return inner_low,inner_high
        if value>band_high:high=min(high,target-1e-6)
        elif value<band_low:low=max(low,target+1e-6)
    # No reachable interior: preserve bounded intermediate steps and protection handling.
    return low,high


def candidate_targets(package,snapshot):
    low,high=recovery_interval(package,snapshot)
    if low>high:return []
    goal=max(low,min(high,sum(package['objective'])/2))
    return sorted({round(x,6) for x in [low,goal,(low+high)/2,high]
                   if low-1e-9<=round(x,6)<=high+1e-9})



def load_package(name: str) -> Package:
    registry=json.loads((ROOT/'registry.json').read_text())
    if registry.get('schema_version')!='1' or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}',name) or name not in registry['packages']:
        raise ValueError('Unknown process package or registry version')
    path=(ROOT/registry['packages'][name]).resolve()
    if path.parent!=ROOT.resolve() or path.suffix!='.json':
        raise ValueError('Package must be installed inside the registry directory')
    package=Package.model_validate_json(path.read_text())
    if package.id!=name: raise ValueError('Package identity mismatch')
    return package


def check_snapshot(package: Package, snapshot: Snapshot, now: float) -> list[str]:
    reasons = []
    if snapshot.package_hash != package.fingerprint(): reasons.append('package mismatch')
    times = []
    for tag, unit in [(package.sensor, package.unit), ('flow', 'L/s')]:
        reading = snapshot.readings.get(tag)
        if reading is None:
            reasons.append(f'{tag}: missing'); continue
        times.append(reading.source_time)
        if reading.unit != unit: reasons.append(f'{tag}: unit mismatch')
        if reading.quality != 'good': reasons.append(f'{tag}: bad quality')
        if now - reading.source_time > 5: reasons.append(f'{tag}: stale')
        if reading.source_time - now > 1: reasons.append(f'{tag}: future timestamp')
    if times and max(times)-min(times) > 2: reasons.append('incoherent snapshot')
    if now - snapshot.source_time > 5: reasons.append('snapshot stale')
    if snapshot.source_time > now + 1: reasons.append('snapshot future')
    if snapshot.readings.get('flow') and snapshot.readings['flow'].value <= 0:
        reasons.append('flow proof missing')
    value=snapshot.readings.get(package.sensor)
    if value and value.unit==package.unit and not package.critical_limits[0]<value.value<package.critical_limits[1]:
        reasons.append(f'{package.sensor}: critical measurement requires operator intervention')
    return reasons
