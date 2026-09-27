"""Local-only Qwen SOP curriculum pilot. Never promotes an adapter to a controller."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/posttraining'
SYSTEM = 'You supervise a simulated plant. Return JSON only: actions (list of target/value), confidence (number), reason (short text), episode_status (continue or escalate). Respect supplied SOP prerequisites and waiting periods. No thinking trace. /no_think'


def example(seed):
    rng = random.Random(seed)
    kind = seed % 6
    current = round(rng.uniform(.9, 1.4), 2)
    state = {'domain': 'water', 'minute': rng.randint(20, 120),
             'current_targets': {'chlorine_target_mg_l': current},
             'sensor_quality': 'good', 'flow_proof': True, 'critical_alarm': False,
             'residual_mg_l': round(rng.uniform(.2, .5), 2),
             'remaining_observation_minutes': 0,
             'sop': 'With good sensors, flow proof and no alarm, residual below 0.6 permits one target increase of 0.05. Residual above 1.8 permits a decrease of 0.05. Otherwise hold. Wait while remaining_observation_minutes > 0. Missing flow or bad quality or critical alarm requires escalation. Gate bounds are 0.8 to 1.8. This is a simulated curriculum rule, not an operating SOP.'}
    actions = []; episode = 'continue'; reason = 'Observe current conditions.'
    if kind == 0:
        actions = [{'target': 'chlorine_target_mg_l', 'value': round(current + .05, 2)}]; reason = 'Small increase for low residual.'
    elif kind == 1:
        state['residual_mg_l'] = round(rng.uniform(1.9, 2.3), 2)
        actions = [{'target': 'chlorine_target_mg_l', 'value': round(current - .05, 2)}]; reason = 'Small decrease for high residual.'
    elif kind == 2:
        state['remaining_observation_minutes'] = rng.randint(1, 12); reason = 'Wait for the previous change.'
    elif kind == 3:
        state['sensor_quality'] = 'bad'; episode = 'escalate'; reason = 'Required sensor is unreliable.'
    elif kind == 4:
        state['flow_proof'] = False; episode = 'escalate'; reason = 'Flow proof is unavailable.'
    else:
        state['residual_mg_l'] = round(rng.uniform(.8, 1.5), 2)
    expected = {'actions': actions, 'confidence': .8, 'reason': reason, 'episode_status': episode}
    return {'messages': [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': json.dumps(state)}, {'role': 'assistant', 'content': json.dumps(expected)}]}


def prepare():
    data = OUT / 'sop-curriculum'; data.mkdir(parents=True, exist_ok=True)
    manifest = {'teacher': 'explicit simulated curriculum rules; not expert-labelled plant outcomes',
                'scope': 'water disinfection prerequisite and response-wait instruction-following only',
                'promotion': 'never automatic', 'splits': {}}
    for name, start, count in [('train', 0, 120), ('valid', 10002, 24), ('test', 20004, 24)]:
        content = ''.join(json.dumps(example(seed)) + '\n' for seed in range(start, start + count))
        (data / f'{name}.jsonl').write_text(content)
        manifest['splits'][name] = {'seed_start': start, 'count': count, 'sha256': hashlib.sha256(content.encode()).hexdigest()}
    (data / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return data


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train', action='store_true')
    parser.add_argument('--iters', type=int, default=24)
    args = parser.parse_args()
    data = prepare()
    print(data, flush=True)
    if args.train:
        model = json.loads((OUT / 'models.json').read_text())['mlx-community/Qwen3-4B-4bit']['path']
        subprocess.run([sys.executable, '-m', 'mlx_lm.lora', '--model', model, '--train', '--data', str(data),
                        '--adapter-path', str(OUT / 'qwen-sop-pilot'), '--iters', str(args.iters), '--batch-size', '1',
                        '--num-layers', '4', '--max-seq-length', '1024', '--mask-prompt', '--learning-rate', '0.00005',
                        '--val-batches', '2', '--steps-per-eval', str(args.iters), '--steps-per-report', '4',
                        '--save-every', str(args.iters), '--seed', '42'], check=True)
