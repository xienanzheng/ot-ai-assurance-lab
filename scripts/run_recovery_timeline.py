#!/usr/bin/env python3
"""Paired LOCAL water recovery experiment; real Ollama decisions through the PLC gate."""
import argparse
import csv
import html
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.limits import LIMITS

SCENARIO = 'gradual_turbidity_rise'
TAGS = ['raw_turbidity_ntu', 'clarified_turbidity_ntu', 'filtered_turbidity_ntu',
        'coagulant_dose_actual_mg_l', 'coagulation_ph', 'finished_water_ph',
        'finished_alkalinity_mg_l_caco3', 'chlorine_residual_mg_l', 'chlorine_ct_mg_min_l',
        'clearwell_level_pct', 'elevated_tank_level_pct', 'filter_dp_kpa',
        'zone_1_pressure_m', 'zone_2_pressure_m', 'zone_3_pressure_m']
CHECKS = {k: LIMITS[k] for k in TAGS if k in LIMITS}
CHECKS.update({f'zone_{i}_pressure_m': LIMITS['zone_pressure_m'] for i in [1, 2, 3]})


def safe(sample):
    return (not sample['alarms'] and
            all(sample['quality'].get(k) == 'good' for k in TAGS) and
            all(isinstance(sample['values'].get(k), (float, int)) and
                math.isfinite(sample['values'][k]) and low <= sample['values'][k] <= high
                for k, (low, high) in CHECKS.items()))


def recovered(samples, duration=8):
    window = samples[-(duration + 1):]
    return (len(window) == duration + 1 and
            all(b['minute'] - a['minute'] == 1 for a, b in zip(window, window[1:])) and
            all(safe(s) for s in window))


def summarize_sample(plant, plc):
    return {'minute': plant['elapsed_minutes'], 'simulation_time': plant['simulation_time'],
            'values': {k: plant['sensors'][k]['value'] for k in TAGS},
            'quality': {k: plant['sensors'][k]['quality'] for k in TAGS},
            'alarms': [a['code'] for a in plant['active_alarms']],
            'safety_state': plant['safety_state'], 'setpoints': plc['setpoints'],
            'actuators': plant['actuators']}


def save(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False))
    temp.replace(path)


def render(output, result):
    baseline, agent = result.get('baseline', {}).get('samples', []), result.get('agent', {}).get('samples', [])
    end = agent[-1]['minute'] if agent else 0
    matched = [s for s in baseline if s['minute'] <= end]
    result['comparison'] = {'matched_end_minute': end,
        'baseline_minutes_above_1_NTU': sum(s['values']['filtered_turbidity_ntu'] > 1 for s in matched if s['minute'] > 0),
        'agent_minutes_above_1_NTU': sum(s['values']['filtered_turbidity_ntu'] > 1 for s in agent if s['minute'] > 0),
        'baseline_final_NTU': matched[-1]['values']['filtered_turbidity_ntu'] if matched else None,
        'agent_final_NTU': agent[-1]['values']['filtered_turbidity_ntu'] if agent else None}
    save(output / 'session.json', result)
    for name in ['baseline', 'agent']:
        samples = result.get(name, {}).get('samples', [])
        with (output / f'{name}.csv').open('w', newline='') as f:
            w = csv.writer(f); w.writerow(['minute', *TAGS, 'alarms', 'setpoints'])
            for s in samples: w.writerow([s['minute'], *[s['values'][k] for k in TAGS], '|'.join(s['alarms']), json.dumps(s['setpoints'])])
    esc = lambda value: html.escape(str(value))
    xmax = max([s['minute'] for s in baseline + agent] or [60])
    ymax = max([s['values']['filtered_turbidity_ntu'] for s in baseline + agent] + [1.4]) * 1.1
    x = lambda m: 60 + m / xmax * 840
    y = lambda v: 280 - v / ymax * 240
    traces = []
    for samples, color in [(baseline, '#8b8f97'), (agent, '#126d65')]:
        pts = ' '.join(f'{x(s["minute"]):.1f},{y(s["values"]["filtered_turbidity_ntu"]):.1f}' for s in samples)
        traces.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="3"/>')
    ticks = ''.join(f'<text x="{x(m)}" y="304" text-anchor="middle">{m}</text>' for m in range(0, xmax + 1, 10))
    turns = []
    for t in result.get('agent', {}).get('exchanges', []):
        r = t.get('record') or {}; p = r.get('proposal') or {}; g = r.get('gate') or {}
        changes = {k:v for k,v in (p.get('changes') or {}).items() if v is not None}
        applied = {k:v for k,v in (g.get('applied_values') or {}).items() if v is not None} if r.get('applied') else {}
        reasoning = (r.get('response') or {}).get('message', {}).get('thinking', '')
        turns.append(f'<article><h3>Minute {t["minute"]} · {esc(g.get("status", t.get("job", {}).get("status")))}</h3>'
            f'<p>{esc(p.get("explanation", t.get("job", {}).get("error", "No valid model response")))}</p>'
            f'<p>Proposed: <code>{esc(json.dumps(changes))}</code><br>Applied: <code>{esc(json.dumps(applied))}</code></p>'
            f'<p>Model assessment: {esc(p.get("episode_status"))}. Recovery check: {esc(t.get("recovery_confirmed"))}. Inference: {esc(r.get("latency_seconds"))} seconds.</p>'
            f'<details><summary>Model-emitted reasoning</summary><pre>{esc(reasoning or "Not emitted")}</pre></details>'
            f'<details><summary>Exact request, response and gate record</summary><pre>{esc(json.dumps(r, indent=2))}</pre></details></article>')
    rows = ''.join('<tr>' + ''.join(f'<td>{esc(v)}</td>' for v in [s['minute'],
           f'{s["values"]["raw_turbidity_ntu"]:.2f}', f'{s["values"]["filtered_turbidity_ntu"]:.3f}',
           s['setpoints']['coagulant_target_mg_l'], f'{s["values"]["coagulation_ph"]:.3f}', ', '.join(s['alarms']) or 'Clear']) + '</tr>' for s in agent)
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Water recovery · local AI timeline</title><style>
body{{font:17px/1.55 system-ui,sans-serif;color:#243139;background:#f5f3ec;margin:0}}main{{max-width:1040px;margin:auto;padding:36px 24px}}h1{{font-size:38px;line-height:1.1}}h2{{margin-top:40px}}article{{background:white;border-left:4px solid #126d65;padding:18px 24px;margin:20px 0}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}code{{overflow-wrap:anywhere}}svg{{width:100%;background:white}}text{{font:13px system-ui}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:8px;text-align:left;border-bottom:1px solid #d7d9d4}}.scroll{{overflow:auto}}summary{{cursor:pointer;padding:8px 0}}.status{{font-size:22px;color:#126d65}}</style>
<main><p>LOCAL OT LAB · {esc(result['id'])}</p><h1>Can the local agent recover water quality?</h1>
<p class="status">{esc(result.get('status'))}</p><p>Source turbidity ramps during minutes 10–30 and remains elevated. AI starts only after filtered effluent exceeds the illustrative 1.0 NTU limit. Every exchange includes recent measurements, previous proposals and gate outcomes. The clock pauses during inference.</p>
<p>Grey: baseline PLC. Green: PLC with gated Qwen3 8B proposals. Red dashed line: illustrative effluent limit.</p>
<svg viewBox="0 0 940 340" role="img" aria-label="Filtered turbidity by simulated minute, comparing baseline and AI">
<text x="15" y="22">Filtered turbidity (NTU)</text><line x1="60" x2="900" y1="{y(1)}" y2="{y(1)}" stroke="#a02d33" stroke-dasharray="8 5"/>
<text x="15" y="{y(1)+4}">1.0</text><text x="25" y="280">0</text>{''.join(traces)}{ticks}<text x="440" y="330">Simulated minute</text></svg>
<h2>Matched comparison</h2><pre>{esc(json.dumps(result['comparison'], indent=2))}</pre>
<p>Baseline and AI use the same scenario, seed, initial controls and one-minute stepping. Compare only their shared time horizon. This is one deliberately constructed, reduced-order simulation, not plant validation or a general performance benchmark. Baseline PLC responses and independent protections operate in both arms.</p>
<h2>Decision exchanges</h2>{''.join(turns)}<h2>Minute-by-minute observations</h2><div class="scroll"><table><thead><tr><th>Minute</th><th>Raw NTU</th><th>Filtered NTU</th><th>Coagulant target mg/L</th><th>Coagulation pH</th><th>Alarms</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>How to present this run</h2><p>Start with the grey baseline curve. Follow the gradual deterioration, then open each decision exchange to compare what the model saw, proposed and actually achieved. End with the recovery check and matched baseline comparison. A resolved claim alone cannot stop the exercise: the harness requires eight consecutive minutes within bounds, good quality flags and no alarms.</p>
<p>Model-emitted reasoning is a recorded output, not verified access to internal computation. Source forcing remains active. Ending this run pauses the simulated clock; it does not end the source disturbance or prove recovery will persist after the AI lease expires.</p></main></html>'''
    (output / 'report.html').write_text(page)
    (output / 'summary.md').write_text(f'# Water recovery timeline\n\nStatus: {result.get("status")}\n\n```json\n{json.dumps(result["comparison"], indent=2)}\n```\n\nOpen report.html for the plotted timeline and complete decision exchanges. session.json and CSV files contain the data.\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes', type=int, default=60)
    parser.add_argument('--output', type=Path, default=Path('artifacts/recovery-timelines'))
    args = parser.parse_args()
    if not 40 <= args.minutes <= 120: parser.error('--minutes must be 40–120')
    identifier = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8]
    output = args.output / identifier; output.mkdir(parents=True)
    opener = build_opener(ProxyHandler({}))
    def api(path, payload=None, method=None):
        req = Request('http://127.0.0.1:18780/api/v1/' + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json'}, method=method)
        with opener.open(req, timeout=120) as r: return json.load(r)
    result = {'id':identifier, 'status':'running', 'protocol':{'scenario':SCENARIO, 'seed':42,
              'max_minutes':args.minutes, 'trigger':'filtered_turbidity_ntu > 1.0', 'decision_interval_minutes':4,
              'recovery_hold_minutes':8, 'model':'waterlab-water:latest', 'num_ctx':16384,
              'thinking':True, 'clock':'paused during inference', 'scheduled_ai':False}}
    active_run = None
    try:
        jobs = api('agents/state')['jobs']
        if any(j['status'] == 'running' for j in jobs): raise RuntimeError('Wait for the existing agent job before starting')
        state = api('state')
        if state['plant']['running']: raise RuntimeError('Pause the existing water exercise before replacing it')
        save(output / 'preceding-exercise.json', api('training/water/export?format=json'))
        save(output / 'preceding-state.json', state)
        for arm in ['baseline', 'agent']:
            config = dict(scenario=SCENARIO, seed=42, duration_hours=24, speed=1,
                          controller_mode='baseline', ai_schedule_enabled=False)
            active_run = api('runs', config)['id']; api(f'runs/{active_run}/reset', {})
            # A fresh controller scan establishes identical initial outputs in both arms.
            state = api('state')
            result[arm] = {'run_id':active_run, 'samples':[summarize_sample(state['plant'],state['plc'])], 'exchanges':[]}
            active = False; next_decision = None
            for minute in range(1, args.minutes + 1):
                api(f'runs/{active_run}/step', {'minutes':1})
                state = api('state'); plant = state['plant']
                if state['active_run_id'] != active_run or plant['elapsed_minutes'] != minute:
                    raise RuntimeError('Run or clock changed outside this experiment')
                sample = summarize_sample(plant,state['plc']); result[arm]['samples'].append(sample)
                if minute % 5 == 0:
                    print(f'{arm} minute {minute}: raw={sample["values"]["raw_turbidity_ntu"]:.2f}, effluent={sample["values"]["filtered_turbidity_ntu"]:.3f} NTU, alarms={sample["alarms"]}', flush=True)
                if arm == 'agent' and not active and sample['values']['filtered_turbidity_ntu'] > 1:
                    active = True; next_decision = minute; result[arm]['takeover_minute'] = minute
                    api('control/mode', {'mode':'gated_auto'}, 'PUT')
                    api('training/water', {'action':'note', 'note':'Timeline experiment: effluent crossed 1.0 NTU; local LLM now proposes gated adjustments every four simulated minutes.'})
                if arm == 'agent' and active and minute == next_decision:
                    print(f'AI exchange at minute {minute}: capturing history; simulation clock paused.', flush=True)
                    job = api('agents/water/cycle', {'thinking':True, 'evaluate_only':False,
                              'model':'waterlab-water:latest', 'num_ctx':16384, 'include_history':True})
                    turn = {'minute':minute, 'job':job}; result[arm]['exchanges'].append(turn)
                    save(output/'session.json',result)
                    deadline=time.monotonic()+480; last_notice=time.monotonic()
                    while job['status']=='running':
                        if time.monotonic()>deadline: raise TimeoutError('Agent job exceeded 480 seconds; simulation remains paused')
                        time.sleep(2)
                        job = next(j for j in api('agents/state')['jobs'] if j['id']==job['id'])
                        if time.monotonic()-last_notice>30:
                            print(f'AI still reasoning at paused minute {minute}...',flush=True);last_notice=time.monotonic()
                    turn['job']=job
                    if job.get('record_id'):
                        record=api('agents/records/'+job['record_id']);turn['record']=record
                        save(output/f'decision-{minute:03d}-{record["id"]}.json',record)
                    record=turn.get('record') or {}; proposal=record.get('proposal') or {}
                    turn['recovery_confirmed']=recovered(result[arm]['samples'])
                    print(json.dumps({'minute':minute, 'job':job['status'], 'proposal':proposal,
                                      'gate':record.get('gate'), 'recovery_confirmed':turn['recovery_confirmed']}),flush=True)
                    if proposal.get('episode_status')=='resolved' and turn['recovery_confirmed']:
                        result['status']='resolved_and_paused';break
                    if proposal.get('episode_status')=='escalate':
                        result['status']='escalated_and_paused';break
                    next_decision=minute+4
                save(output/'session.json',result)
            save(output/f'{arm}-exercise.json', api('training/water/export?format=json'))
            if arm=='agent' and result['status']=='running':result['status']='horizon_reached_without_confirmed_resolution'
        api(f'runs/{active_run}/pause', {})
        result['final_state']=api('state')
    except BaseException as exc:
        result['status']='interrupted' if isinstance(exc,KeyboardInterrupt) else 'error'
        result['error']=str(exc)
        raise
    finally:
        if active_run:
            try:api(f'runs/{active_run}/pause', {})
            except Exception as exc: result['pause_error']=str(exc)
        render(output,result)
        print(f'Evidence: {output}/report.html',flush=True)
    return 0 if result['status']=='resolved_and_paused' else 2


if __name__ == '__main__':
    sys.exit(main())
