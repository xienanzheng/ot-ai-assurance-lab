"""Recompute development results from complete saved records; no model calls."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_water_context_study import verify, lines, pilot_rows, payload_for, summarize, sha, write, model_path
from scripts.water_context_study import OUT
from scripts.water_alarm_benchmark import score


def normalized(value):return json.loads(json.dumps(value))


def audit_records(records,rows,mode):
    ids=[r['id'] for r in records]
    if len(ids)!=len(set(ids)) or set(ids)!={r['id'] for r in rows}:
        raise ValueError('Missing, duplicate or unexpected result IDs')
    by_id={r['id']:r for r in rows}
    for record in records:
        row=by_id[record['id']]
        if record['score']!=score(record['decoded'],row):raise ValueError('Cached score differs')
        if record['kind']!=row['kind']:raise ValueError('Scenario category differs')
        if normalized(record['input'])!=normalized(payload_for(row,mode)):raise ValueError('Captured input differs')


def main():
    verify();rows=pilot_rows(lines(OUT/'valid.cases.jsonl'))
    labels=['local-assisted-base','local-assisted-adapter','cloud-baseline-base','cloud-assisted-base','cloud-typed-base']
    if (OUT/'local-assisted-previous.jsonl').exists():labels.append('local-assisted-previous')
    if (OUT/'local-typed-base.jsonl').exists():labels.extend(['local-typed-base','local-typed-adapter'])
    report={'scope':'32-case development pilot; no approval or locked test','variants':{},'paired_local':{}}
    all_records={}
    for label in labels:
        records=lines(OUT/f'{label}.jsonl');mode=label.split('-')[1]
        binding=json.loads((OUT/f'{label}.identity.json').read_text())
        if binding.get('pilot_sha256')!=sha(OUT/'pilot.json'):raise ValueError('Pilot binding differs')
        if 'typed_manifest_sha256' in binding:
            if binding['typed_manifest_sha256']!=sha(OUT/'typed-study/manifest.json'):raise ValueError('Compact source binding differs')
        elif binding.get('manifest_sha256')!=sha(OUT/'manifest.json'):raise ValueError('Source binding differs')
        audit_records(records,rows,mode)
        saved=json.loads((OUT/f'{label}-summary.json').read_text())
        recalculated=summarize(records)
        if saved!=recalculated:raise ValueError(f'Summary differs: {label}')
        report['variants'][label]={**recalculated,'records_sha256':sha(OUT/f'{label}.jsonl'),'binding':binding}
        all_records[label]={r['id']:r for r in records}
    base=all_records['local-assisted-base'];adapter=all_records['local-assisted-adapter']
    report['paired_local']={
        'adapter_only_correct':[i for i in base if adapter[i]['score']['correct'] and not base[i]['score']['correct']],
        'base_only_correct':[i for i in base if base[i]['score']['correct'] and not adapter[i]['score']['correct']]}
    if 'local-typed-adapter' in all_records:
        from scripts.run_typed_water_adapter import verify_typed,STUDY
        verify_typed()
        typed_base=all_records['local-typed-base'];typed=all_records['local-typed-adapter']
        report['paired_typed']={
            'adapter_only_correct':[i for i in typed if typed[i]['score']['correct'] and not typed_base[i]['score']['correct']],
            'base_only_correct':[i for i in typed if typed_base[i]['score']['correct'] and not typed[i]['score']['correct']]}
        done=json.loads((STUDY/'adapter/training-complete.json').read_text())
        if done['adapter_sha256']!=sha(STUDY/'adapter/adapters.safetensors') or done['config_sha256']!=sha(STUDY/'adapter/adapter_config.json'):
            raise ValueError('Compact adapter changed after evaluation')
        typed_config=json.loads((STUDY/'adapter/adapter_config.json').read_text())
        if any(typed_config[k]!=v for k,v in {'iters':80,'num_layers':4,'batch_size':1,'mask_prompt':True,'grad_checkpoint':True,'learning_rate':5e-5}.items()) or typed_config['lora_parameters']['rank']!=8:
            raise ValueError('Unexpected compact training settings')
    config=json.loads((OUT/'adapter/adapter_config.json').read_text())
    for field,expected in {'iters':80,'num_layers':4,'batch_size':1,'mask_prompt':True,'grad_checkpoint':True,'learning_rate':5e-5}.items():
        if config[field]!=expected:raise ValueError(f'Unexpected training setting: {field}')
    if config['lora_parameters']['rank']!=8:raise ValueError('Unexpected adapter rank')
    complete=json.loads((OUT/'adapter/training-complete.json').read_text())
    if complete['adapter_sha256']!=sha(OUT/'adapter/adapters.safetensors') or complete['config_sha256']!=sha(OUT/'adapter/adapter_config.json'):
        raise ValueError('Trained artifacts changed')
    # Additional final integrity check against hashes recorded by the earlier pinned study.
    # This is an after-run verification, not a claim that new hashes were bound before inference.
    expected=json.loads((ROOT/'artifacts/posttraining/water-alarms-v2/acceptance.json').read_text())['test']['identity']['base_files']
    actual={name:sha(Path(model_path())/name) for name in expected}
    if actual!=expected:raise ValueError('Pinned base files differ from prior recorded hashes')
    report['base_files_final_integrity_check']=actual
    report['training_updates_per_new_candidate']=80
    report['total_new_training_updates']=160 if 'local-typed-adapter' in all_records else 80
    report['training_examples_available']=1200
    report['approval']=False
    write(OUT/'audited-report.json',report)
    print(json.dumps({label:{k:row[k] for k in ['count','correct','valid','critical_correct','supported_assessments']} for label,row in report['variants'].items()},indent=2))


if __name__=='__main__':main()
