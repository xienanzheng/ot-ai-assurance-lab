"""Launch only evaluated, passing weights on loopback port 18784."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.supervisor.app.water_candidate import approval,REVISION

if __name__=='__main__':
    report=approval()
    model=json.loads((ROOT/'artifacts/posttraining/models.json').read_text())['mlx-community/Qwen3-4B-4bit']
    if model['revision']!=REVISION:raise SystemExit('Base revision does not match evaluated model')
    config={'model':model['path'],'adapter':report['adapter_path'],
            'dataset':report['dataset_path'],'identity':report['evaluation_identity']}
    with tempfile.NamedTemporaryFile(mode='w',suffix='.json') as handle:
        json.dump(config,handle);handle.flush()
        subprocess.run([str(ROOT/'.venv-posttrain/bin/python'),str(ROOT/'scripts/water_alarm_server.py'),
                        '--config',handle.name],check=True)
