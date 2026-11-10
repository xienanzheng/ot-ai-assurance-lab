"""Recompute published historical counts and latencies, with no model calls."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from training.mlx_experiment import summarize, readiness


def review(folder: Path) -> dict:
    provenance = json.loads((folder / 'PROVENANCE.json').read_text())
    rows = {}
    for name in ('base', 'selected'):
        filename = f'{name}-test.rows.jsonl'
        data = (folder / filename).read_bytes()
        if hashlib.sha256(data).hexdigest() != provenance['files'][filename]:
            raise ValueError(f'Historical evidence hash mismatch: {filename}')
        rows[name] = [json.loads(line) for line in data.splitlines()]
    ids = [row['id'] for row in rows['base']]
    if len(ids) != 96 or len(set(ids)) != 96 or ids != [row['id'] for row in rows['selected']]:
        raise ValueError('Expected the same 96 unique test IDs in both files')
    base, selected = (summarize(rows[name]) for name in ('base', 'selected'))
    return {'base': base, 'selected': selected, 'readiness': readiness(selected, base),
            'source': provenance['evaluated_source_revision'],
            'note': 'Historical simulation results; code supplies proposal and rationale templates.'}


if __name__ == '__main__':
    print(json.dumps(review(ROOT / 'evidence/typed-qwen-2026-10-31'), indent=2))
