"""Package only the recorded dashboard and its synthetic evidence for hosting."""
from pathlib import Path
import json
import shutil
import argparse


def build(live=False):
    root=Path(__file__).resolve().parents[1]
    source=root/('services/web/dist-hosted' if live else 'services/web/dist')
    target=root/('deploy/cloudflare-live/public' if live else 'deploy/cloudflare/public')
    if not (source/'research.html').is_file(): raise SystemExit('Run npm ci and npm run build in services/web first')
    # This is a generated, fixed output directory; never accept an arbitrary delete path.
    if target.is_symlink(): raise SystemExit('Refusing symlink output')
    if target.exists(): shutil.rmtree(target)
    target.mkdir(parents=True)
    shutil.copy2(source/'research.html',target/'research.html')
    if live: shutil.copy2(source/'index.html',target/'index.html')
    for name in ['assets','fonts','research']:
        shutil.copytree(source/name,target/name,ignore=shutil.ignore_patterns('*.npz','*.map'))
    # Raw activations exceed the static per-file limit; the repository retains them.
    for path in (target/'research/mechanistic').glob('*/results.json'):
        data=json.loads(path.read_text())
        data.pop('activations_url',None)
        data['distribution_note']='Raw NPZ activations are included in the GitHub repository, not in this hosted demo.'
        path.write_text(json.dumps(data,indent=2)+'\n')
    print(f'Recorded demo: {target}')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true',help='Package the separate VITE_HOSTED build')
    build(parser.parse_args().live)
