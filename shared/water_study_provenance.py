"""Fail-closed identity binding for local water study artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evaluation_identity(dataset, base_revision, adapter=None):
    dataset = Path(dataset)
    sources = ['scripts/run_water_alarm_study.py', 'scripts/water_alarm_benchmark.py',
               'services/supervisor/app/water_alarm.py', 'shared/models.py',
               'shared/water_study_provenance.py','scripts/train_water_alarm_adapter.py',
               'scripts/water_alarm_server.py','services/supervisor/app/plant_sops.json',
               'services/supervisor/app/sop_context.py','services/plc_control/app/controller.py',
               'services/plant_sim/app/simulator.py','shared/limits.py',
               'requirements-water-alarm-training.txt']
    base=json.loads((ROOT/'artifacts/posttraining/models.json').read_text())['mlx-community/Qwen3-4B-4bit']
    if base['revision']!=base_revision:raise ValueError('Base revision changed')
    base_path=Path(base['path'])
    base_files=sorted(base_path.glob('*.safetensors'))+sorted(base_path.glob('*.json'))
    if not any(p.suffix=='.safetensors' for p in base_files):raise ValueError('Missing pinned base weights')
    return {
        'version': 2,
        'base_files':{p.name:sha256(p) for p in base_files},
        'base_revision': base_revision,
        'adapter_sha256': sha256(Path(adapter)/'adapters.safetensors') if adapter else None,
        'adapter_config_sha256': sha256(Path(adapter)/'adapter_config.json') if adapter else None,
        'dataset': {name: sha256(dataset/name) for name in
                    ['manifest.json', 'train.cases.jsonl', 'valid.cases.jsonl', 'test.cases.jsonl']},
        'sources': {name: sha256(ROOT/name) for name in sources},
        'decoding': {'temperature': 0, 'thinking': False, 'max_output': 256,
                     'max_sequence': 4096, 'completion_batch_size': 8, 'prefill_batch_size': 2},
    }


def bind_artifact(path, identity):
    """Bind before measuring. Never attach identity retroactively to old results."""
    path = Path(path)
    sidecar = path.with_name(path.name+'.identity.json')
    if sidecar.exists():
        if json.loads(sidecar.read_text()) != identity:
            raise ValueError(f'Artifact identity changed: {path.name}; use a new run')
    elif path.exists():
        raise ValueError(f'Unbound legacy artifact: {path.name}; preserve it and rerun')
    else:
        sidecar.write_text(json.dumps(identity, indent=2))
