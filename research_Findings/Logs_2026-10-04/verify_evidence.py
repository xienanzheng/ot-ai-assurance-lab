"""Verify published research records offline. Never calls a model or the simulator."""
from pathlib import Path
import csv
import hashlib
import json
import math
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parent
CHART = ROOT.parent / 'OT_Lab_Results_2026-10-04/data'
DATA = ROOT / 'shared-case-comparison/data'
ART = ROOT / 'water-ot-ai-lab/artifacts'
V2 = ART / 'posttraining/water-alarms-v2'
PILOT = ART / 'posttraining/water-context-v3-pilot'
sys.path.insert(0, str(ROOT / 'shared-case-comparison/source_snapshot'))
from scripts.water_alarm_benchmark import score


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def table(path):
    with path.open(newline='') as stream:
        return list(csv.DictReader(stream))


def unique(rows):
    mapped = {row['id']: row for row in rows}
    assert len(mapped) == len(rows), 'Duplicate case IDs'
    return mapped


def main():
    report = {}
    cases = unique(records(DATA / 'valid.cases.jsonl'))
    assert len(cases) == 400
    saved = {(r['model'], r['id']): r for r in table(CHART / 'shared-case-scores.csv')}
    report['shared_comparison'] = {}
    for name, filename in [('Cloud Qwen30B', 'cloud-responses.jsonl'),
                           ('Fine-tuned Qwen4B', 'lr5e5-valid.jsonl'),
                           ('Jev typed choices', 'jev-responses.jsonl')]:
        rows = unique(records(DATA / filename))
        assert set(rows) == set(cases)
        for case_id, row in rows.items():
            rescored = score(row.get('output'), cases[case_id])
            assert rescored == row['score'], (name, case_id, 'saved score mismatch')
            plotted = saved[(name, case_id)]
            for field in ['valid', 'correct', 'critical_ok', 'assessment_supported']:
                assert str(rescored[field]) == plotted[field]
            assert int(plotted['reference_errors']) == rescored['reference_errors']
        report['shared_comparison'][name] = {
            'count': len(rows), 'correct': sum(r['score']['correct'] for r in rows.values()),
            'valid': sum(r['score']['valid'] for r in rows.values())}

    cases = unique(records(V2 / 'test.cases.jsonl'))
    rows = unique(records(V2 / 'lr5e5-test.jsonl'))
    assert len(cases) == 1000 and set(cases) == set(rows)
    for case_id, row in rows.items():
        assert score(row['output'], cases[case_id]) == row['score'], case_id
    critical = [r for r in rows.values() if r['kind'] == 'critical']
    other = [r for r in rows.values() if r['kind'] != 'critical']
    result = {'count': len(rows), 'critical_count': len(critical),
              'critical_correct': sum(r['score']['critical_ok'] for r in critical),
              'valid': sum(r['score']['valid'] for r in rows.values()),
              'supported_assessments': sum(r['score']['assessment_supported'] for r in rows.values()),
              'other_count': len(other), 'other_correct': sum(r['score']['correct'] for r in other),
              'reference_errors': sum(r['score']['reference_errors'] for r in rows.values())}
    original = json.loads((V2 / 'lr5e5-test-summary.json').read_text())
    for field, value in result.items():
        assert original[field] == value, field
    expected = [(result['critical_correct'], 500), (result['valid'], 1000),
                (result['supported_assessments'], 1000), (result['other_correct'], 500)]
    for plotted, (num, den) in zip(table(CHART / 'locked-test-acceptance.csv'), expected):
        assert (int(plotted['numerator']), int(plotted['denominator'])) == (num, den)
    report['locked_test'] = result

    report['latency'] = []
    sources = [(V2 / 'base-latency.json', 'v2'), (V2 / 'lr5e5-latency.json', 'v2'),
               (PILOT / 'local-assisted-base.jsonl', 'pilot'),
               (PILOT / 'local-assisted-adapter.jsonl', 'pilot'),
               (PILOT / 'local-typed-base.jsonl', 'pilot'),
               (PILOT / 'local-typed-adapter.jsonl', 'pilot')]
    for plotted, (path, kind) in zip(table(CHART / 'latency-summary.csv'), sources):
        if kind == 'v2':
            summary = json.loads(path.read_text())
            raw = summary['rows']
            values = [r['seconds'] for r in raw[1:] if not r.get('error')]
        else:
            raw = records(path)
            summary = json.loads(path.with_name(path.stem + '-summary.json').read_text())
            values = [r['latency_seconds'] for r in raw[1:] if not r.get('error')]
        median = statistics.median(values)
        ordered = sorted(values)
        index = int(.95 * (len(values) - 1)) if kind == 'v2' else min(len(values) - 1, int(.95 * len(values)))
        p95 = ordered[index]
        assert len(values) == 31 == int(plotted['warm_n'])
        assert math.isclose(median, summary['warm_median_seconds'], abs_tol=1e-8)
        assert math.isclose(p95, summary['warm_p95_seconds'], abs_tol=1e-8)
        assert math.isclose(median, float(plotted['median_seconds']), abs_tol=1e-8)
        assert math.isclose(p95, float(plotted['p95_seconds']), abs_tol=1e-8)
        report['latency'].append({'source': str(path.relative_to(ROOT)), 'warm_count': len(values),
                                  'median_seconds': median, 'p95_seconds': p95})

    pilot_cases = unique(records(PILOT / 'valid.cases.jsonl'))
    variants = [('Assisted base', 'local-assisted-base'),
                ('Previous adapter + assistance', 'local-assisted-previous'),
                ('New assisted adapter', 'local-assisted-adapter'),
                ('Compact base', 'local-typed-base'), ('New compact adapter', 'local-typed-adapter')]
    plotted_pilot = {(r['variant'], r['category']): r for r in table(CHART / 'pilot-category-results.csv')}
    pilot_ids = None
    for name, stem in variants:
        responses = unique(records(PILOT / (stem + '.jsonl')))
        assert len(responses) == 32 and set(responses) <= set(pilot_cases)
        if pilot_ids is None:
            pilot_ids = set(responses)
        assert set(responses) == pilot_ids, 'Pilot comparison IDs differ'
        for case_id, row in responses.items():
            assert score(row['decoded'], pilot_cases[case_id]) == row['score']
        for category in ['critical', 'prerequisite', 'hold', 'adjust']:
            group = [r for r in responses.values() if r['kind'] == category]
            plotted = plotted_pilot[(name, category)]
            assert len(group) == 8 == int(plotted['denominator'])
            assert sum(r['score']['correct'] for r in group) == int(plotted['correct'])
    report['pilot_scored_responses'] = 160

    loss_rows = []
    for label, path in [('Original adapter / 160 updates', V2 / 'lr5e5/training.log'),
                        ('Assisted / 80 updates', PILOT / 'local-run.log'),
                        ('Compact / 80 updates', PILOT / 'typed-run.log')]:
        for iteration, split, value in re.findall(r'Iter (\d+): (Train|Val) loss ([0-9.]+)', path.read_text()):
            loss_rows.append({'experiment': label, 'iteration': iteration, 'split': split, 'loss': str(float(value))})
    plotted_loss = table(CHART / 'training-loss.csv')
    assert loss_rows == plotted_loss
    report['training_loss_checkpoints'] = len(loss_rows)

    retrieval = json.loads((ART / 'retrieval-v2/evaluation.json').read_text())
    methods = [('legacy_keyword', 'Legacy keyword'), ('bm25', 'BM25'),
               ('local_dense', 'Local dense'), ('local_rrf', 'Local hybrid'),
               ('openai_dense', 'OpenAI dense'), ('openai_rrf', 'OpenAI hybrid')]
    for plotted, (key, label) in zip(table(CHART / 'retrieval-results.csv'), methods):
        queries = retrieval['cases'][key]
        hits = sum(q['ranking'][0] == q['expected'] for q in queries)
        assert plotted['method'] == label
        assert hits == int(plotted['correct_top1'])
        assert len(queries) == 18 == int(plotted['queries'])
    report['retrieval_queries_per_method'] = 18

    manifest = json.loads((ROOT / 'publication_manifest.json').read_text())
    for entry in manifest['files']:
        path = ROOT.parent / entry['file']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['published_sha256'], str(path)
    report['publication_source_hashes_checked'] = len(manifest['files'])

    parsed = 0
    for path in ROOT.rglob('*'):
        if path.suffix == '.json':
            json.loads(path.read_text()); parsed += 1
        elif path.suffix == '.jsonl':
            records(path); parsed += 1
    report['parsed_json_files'] = parsed
    report['status'] = 'passed'
    return report


if __name__ == '__main__':
    print(json.dumps(main(), indent=2))
