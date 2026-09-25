#!/usr/bin/env python3
"""Local paired retrieval evaluation. No HTTP control endpoints or real equipment.

Frozen tests measure proposal/gate behavior; water timelines additionally measure
simulated process outcomes. Neither establishes real-plant safety or causality.
"""
import argparse
import asyncio
from datetime import timedelta
import json
import os
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def arguments():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--model', default='qwen3:4b')
    p.add_argument('--url', default='http://127.0.0.1:11434')
    p.add_argument('--domains', nargs='+', choices=['water', 'grid', 'nuclear'], default=['water'])
    p.add_argument('--modes', nargs='+', choices=['off', 'lexical', 'hybrid'], default=['off', 'hybrid'])
    p.add_argument('--seeds', nargs='+', type=int, default=[101, 202])
    p.add_argument('--timeline', action='store_true', help='Water only; isolated closed-loop branches')
    p.add_argument('--minutes', type=int, default=40)
    p.add_argument('--interval', type=int, default=10)
    return p.parse_args()


async def main(args):
    if os.getenv('HOSTED_MODE') == 'true':
        raise SystemExit('This experiment is local-only')
    if args.minutes < 1 or args.interval < 1 or (args.timeline and args.domains != ['water']):
        raise SystemExit('Use positive minutes/interval; timeline supports water only')
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ['DATABASE_URL'] = 'sqlite:///'+str((args.output/'audit.sqlite3').resolve())
    os.environ['OLLAMA_BASE_URL'] = args.url
    os.environ['OLLAMA_MODEL'] = args.model
    os.environ['KNOWLEDGE_EMBED_URL'] = args.url
    os.environ['LESSON_MEMORY_ENABLED'] = 'false'  # isolate static retrieval effect
    from services.supervisor.app.database import Base, engine
    from services.supervisor.app.ollama_client import OllamaSupervisor, OllamaUnavailable
    from services.supervisor.app.agent_audit import get_audit, update_audit
    from services.supervisor.app.agents import frozen_gate
    from services.supervisor.app.plant_knowledge import digest
    from services.plant_sim.app.simulator import WaterPlantSimulator
    from services.infrastructure_sim.app.grid import GridSimulator
    from services.infrastructure_sim.app.nuclear import NuclearSimulator
    from services.plc_control.app.controller import BaselineController, SafetyGate
    from scripts.run_recovery_timeline import recovered, summarize_sample, safe
    from shared.models import ControlMode
    Base.metadata.create_all(engine)
    worker = OllamaSupervisor()
    results = []

    async def decide(domain, state, controller, mode, timeline):
        worker.knowledge_mode = mode
        started = perf_counter()
        context = {'plant': state.model_dump(mode='json'), 'plc': {
            'setpoints': controller.setpoint_dict(), 'control_state': controller.status()}}
        identifier = None
        try:
            if domain == 'water':
                proposal = await worker.propose(state, controller.setpoint_dict(),
                    control_state=controller.status(), experiment_context={'timeline': timeline})
                gate = SafetyGate(controller).evaluate(proposal, state).model_dump(mode='json')
                identifier = proposal.decision_id
            else:
                proposal = await worker.propose_infrastructure(domain, context['plant'])
                identifier = proposal._audit_id
                gate = frozen_gate(domain, context, proposal)
            update_audit(identifier, before=context, gate=gate, applied=False,
                         evaluate_only=not args.timeline, status='complete')
            record = get_audit(identifier)
        except OllamaUnavailable as exc:
            identifier = exc.audit_id
            record = get_audit(identifier)
        except Exception as exc:
            raise RuntimeError(f'{domain} experiment failed') from exc
        model_input = json.loads(record['request']['messages'][-1]['content'])
        model_input.pop('plant_knowledge', None)
        return {'paired_input_sha256': digest(model_input), 'id': identifier, 'mode': mode, 'domain': domain,
                'state_sha256': digest(context['plant']), 'total_seconds': round(perf_counter()-started, 3),
                'record': record}

    for seed_index, seed in enumerate(args.seeds):
        modes = args.modes if seed_index % 2 == 0 else list(reversed(args.modes))
        for domain in args.domains:
            for mode in modes:
                controller = BaselineController()
                sim = {'water': WaterPlantSimulator, 'grid': GridSimulator, 'nuclear': NuclearSimulator}[domain]()
                if domain == 'water':
                    sim.reset(seed=seed, scenario='gradual_turbidity_rise')
                    sim.controller_mode = ControlMode.GATED_AUTO
                if not args.timeline:
                    if domain == 'water':
                        for _ in range(25):
                            sim.set_actuators(controller.calculate(sim.snapshot()).model_dump(exclude_none=True))
                            sim.advance(1)
                    result = await decide(domain, sim.snapshot(), controller, mode, [])
                    result['seed'] = seed
                    results.append(result)
                else:
                    samples, decisions = [], []
                    first_unsafe = recovered_at = None
                    for minute in range(args.minutes+1):
                        snapshot = sim.snapshot()
                        sample = summarize_sample(snapshot.model_dump(mode='json'), {'setpoints': controller.setpoint_dict()})
                        samples.append(sample)
                        if not safe(sample) and first_unsafe is None:
                            first_unsafe = minute
                        if first_unsafe is not None and recovered_at is None and recovered(samples):
                            recovered_at = minute
                        if minute == args.minutes:
                            break
                        if minute >= 10 and minute % args.interval == 0:
                            history = {'recent_samples': samples[-6:], 'previous_decisions': [
                                {'proposal': d['record'].get('proposal'), 'gate': d['record'].get('gate'),
                                 'applied': d['record'].get('applied')} for d in decisions[-3:]]}
                            decision = await decide(domain, snapshot, controller, mode, history)
                            record = decision['record']
                            gate = record.get('gate') or {}
                            if gate.get('status') in {'accepted', 'modified'}:
                                from shared.models import SetpointChanges
                                changes = SetpointChanges.model_validate(gate['applied_values'])
                                applied = bool(changes.model_dump(exclude_none=True))
                                if applied:
                                    controller.apply_setpoint_changes(changes, snapshot.simulation_time+timedelta(minutes=args.interval))
                                update_audit(decision['id'], applied=applied)
                                record['applied'] = applied
                            decisions.append(decision)
                        sim.set_actuators(controller.calculate(sim.snapshot()).model_dump(exclude_none=True))
                        sim.advance(1)
                        if decisions:
                            update_audit(decisions[-1]['id'], outcome={'status':'observed', 'plant':sim.snapshot().model_dump(mode='json')})
                    for decision in decisions:
                        decision['record'] = get_audit(decision['id'])
                    results.append({'domain':domain, 'seed':seed, 'mode':mode, 'samples':samples, 'decisions':decisions,
                        'unsafe_sample_count':sum(not safe(s) for s in samples),
                        'first_unsafe_minute':first_unsafe, 'recovery_confirmed_minute':recovered_at,
                        'recovery_minutes':None if recovered_at is None else recovered_at-first_unsafe,
                        'escalation_accuracy':None, 'unnecessary_interventions':None})
                report = {'experiment':'closed_loop_water' if args.timeline else 'frozen_state',
                    'model':args.model, 'results':results, 'interpretation':
                    'Exploratory simulated evaluation. Gate acceptance is not accuracy. Null recovery means not observed within the horizon. Escalation and unnecessary actions require independent labels. No fine-tuning performed.'}
                (args.output/'report.json').write_text(json.dumps(report, indent=2, default=str, allow_nan=False)+'\n')
                print(f'Completed {domain} seed={seed} mode={mode}', flush=True)


if __name__ == '__main__':
    asyncio.run(main(arguments()))
