"""Render the checked-in SOP registry; --check detects stale documentation."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.supervisor.app.sop_context import load_book
from shared.supervision import response_window

OUTPUT = ROOT / 'docs' / 'PLANT_CONTEXT_BOOK.md'


def render():
    book = load_book()
    lines = ['# Plant SOP and context book', '',
             f"Version {book['version']} · Water / Nuclear / Power grid", '',
             'This book describes the simulation lab. Procedures are grounded in simulator code and have not been validated as operating procedures for a physical facility.', '',
             'The JSON registry is the source of truth. Both provider adapters receive selected procedures as context; the independent gate retains control authority. This book does not establish that every recommendation below is already enforced by code.', '',
             '## Shared decision principles', '']
    lines += [f'{i}. {rule}' for i, rule in enumerate(book['principles'], 1)]
    lines += ['', '## The decision exchange', '',
              '| Stage | Information to record |', '| --- | --- |',
              '| Observe | Run identity, simulated minute, mode, sensor values and units, quality, alarms, current targets and overrides. |',
              '| Context | SOP version/hash and selected IDs, prior applied changes, observation window, trend history and unresolved events. |',
              '| Propose | Provider/model, explicit target values, hold or escalation, concise rationale and requested observation period. |',
              '| Gate | Schema, target allowlist, ranges, step limits, prerequisites, freshness, temporal checks and acceptance/rejection reasons. |',
              '| Apply | Targets actually applied, application minute, control lease and expiry. Approval alone does not prove application. |',
              '| Observe again | Actuator feedback, delayed sensor response, trend, other affected measurements and baseline-controller activity. |',
              '| Resolve | Sustained recovery, no response, worsening, escalation or budget stop. Keep the supporting observations. |', '',
              'This is the evidence contract for implementation and review; fields must not be fabricated when unavailable.', '',
              '## Response timing', '',
              'For a first-order update `y += alpha * (target - y)`, one time constant is `-1 / log(1 - alpha)` simulation steps: approximately 63% of a fixed step response. It is not full settling. Roughly three time constants reach 95% only under an unchanged target and an ideal, undisturbed first-order model.', '',
              'Storage follows net inflow minus outflow; its response cannot be inferred from valve position alone. Water valves travel at up to 12 percentage points per simulated minute; hydraulic calculations refresh every five simulated minutes. Coagulation calculations currently lack a calibrated transport-delay model.', '',
              'The timing helper uses conservative review floors and a bounded lease. Manual single analyses and feedback-loop leases can differ; inspect the actual recorded lease. Simulator tuning and disturbances affect response. Regression slopes describe observed trends and do not prove causation.', '',
              '## Procedures', '']
    for p in book['procedures']:
        window = response_window(p['domain'], dict.fromkeys(p['targets'], 0))
        lines += [f"### {p['id']} — {p['title']}", '',
                  f"**Source:** [{p['source']}](../{p['source']})", '',
                  '**Measurements:** ' + ', '.join(f'`{x}`' for x in p['signals']), '',
                  '**Target families:** ' + ', '.join(f'`{x}`' for x in p['targets']), '',
                  '**Prerequisites:** ' + '; '.join(p['prerequisites']) + '.', '',
                  f"**Timing helper, default tuning:** earliest review {window['observe_minutes']} simulated minutes for this combined target set. Per-proposal timing depends on the targets actually changed.", '']
        lines += [f'{i}. {step}' for i, step in enumerate(p['steps'], 1)]
        lines += ['', '**Escalate:** ' + ' '.join(p['escalation']), '']
    lines += ['## Context, memory and post-training', '',
              '- **Contextualization:** retrieve domain-relevant SOPs and combine them with fresh readings, gate constraints and previous actions. This changes model inputs, not weights.',
              '- **Critical-event memory:** preserve applied actions, rejections, overrides, missing signals and delayed outcomes with provenance. Summaries should retain unresolved hazards and point to original records.',
              '- **Retrieval evaluation:** test procedure relevance on held-out scenarios, including conflicting alarms and missing sensors. A BERT-style reranker is an experiment, not an assumed improvement.',
              '- **Qwen adaptation:** offline SFT/LoRA is a separate candidate experiment. Compare base and adapter on explicit actions, valid holds, gate violations, latency and delayed outcomes before promotion.',
              '- **Jev:** use the same SOP and observation context with typed candidate choices. Supplying context does not fine-tune the hosted model.',
              '- **Preference learning/RL:** retain failed and rejected trajectories. Gate acceptance alone is not a reward for successful control; use delayed outcomes and untouched evaluation scenarios. No automatic online weight updates are prescribed.', '',
              'These are evaluation requirements and planned training directions, not claims that a trained adapter or reranker has passed validation.', '',
              '## Maintaining this book', '',
              'Edit `services/supervisor/app/plant_sops.json`, update its semantic version when meaning changes, and regenerate this document with:', '',
              '```sh', '.venv-interpret/bin/python scripts/build_sop_book.py', '.venv-interpret/bin/python scripts/build_sop_book.py --check', '```', '',
              'Review sensor and target names against simulator contracts, source equations, prerequisites and cross-process effects. Keep actual limits in authoritative controller code rather than duplicating potentially stale numbers in prose. New real-world procedures require separate domain-expert validation.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = render()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text() != result:
            raise SystemExit('Context book is stale; run scripts/build_sop_book.py')
        print('Context book matches the validated registry.')
    else:
        OUTPUT.write_text(result)
        print(OUTPUT.relative_to(ROOT))
