"""Offline hydraulic trajectories. No services, AI calls or live plant commands.

Run from the repository root with the application's Python environment.
"""
import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.plant_sim.app.simulator import WaterPlantSimulator, WATER_HYDRAULIC_VERSION


def collect(engine):
    rows = []
    cases = ('baseline', 'manual_filter_close_reopen', 'manual_matched_fault',
             'injected_matched_fault', 'zone2_close', 'pump_stop', 'chlorine_step')
    for case in cases:
        sim = WaterPlantSimulator(seed=42)
        if engine == 'fallback':
            sim.network = None
        sim.advance(10)
        for minute in range(31):
            if minute == 1:
                if case == 'manual_filter_close_reopen':
                    sim.set_actuators({'filter_outlet_valve_pct': 0})
                elif case in ('manual_matched_fault', 'injected_matched_fault'):
                    sim.set_actuators({'intake_pump_speed_pct': 75, 'filter_outlet_valve_pct': 0})
                    # Match actual equipment state, independent of travel/override.
                    sim.valve_positions['filter_outlet'] = 0
                    if case == 'injected_matched_fault':
                        sim.inject('pump_valve_conflict', 60)
                elif case == 'zone2_close':
                    sim.set_actuators({'zone_2_isolation_valve_pct': 0})
                elif case == 'pump_stop':
                    sim.set_actuators({'intake_pump_speed_pct': 0})
                elif case == 'chlorine_step':
                    sim.set_actuators({'chlorine_dose_mg_l': 2.5})
            if minute == 16 and case == 'manual_filter_close_reopen':
                sim.set_actuators({'filter_outlet_valve_pct': 95})
            if minute:
                sim.advance(1)
            row = dict(case=case, minutes_after=minute, engine=sim.hydraulic_engine,
                       hydraulic_error=sim.hydraulic_error,
                       filter_position_pct=sim.valve_positions['filter_outlet'],
                       zone2_position_pct=sim.valve_positions['zone_2_isolation'])
            for field in ('raw_flow_m3h', 'distribution_flow_m3h', 'filter_inlet_pressure_kpa',
                          'filter_outlet_pressure_kpa', 'filter_dp_kpa', 'pump_deadhead_pressure_kpa',
                          'clearwell_level_pct', 'elevated_tank_level_pct', 'true_chlorine_mg_l',
                          'water_balance_error_m3'):
                row[field] = getattr(sim, field)
            row['zone2_pressure_m'] = sim.zone_pressures[1]
            rows.append(row)
    manual = [r for r in rows if r['case'] == 'manual_matched_fault']
    injected = [r for r in rows if r['case'] == 'injected_matched_fault']
    fields = ('raw_flow_m3h', 'filter_inlet_pressure_kpa', 'distribution_flow_m3h', 'clearwell_level_pct')
    max_difference = max(abs(a[k]-b[k]) for a, b in zip(manual, injected) for k in fields)
    max_balance = max(abs(r['water_balance_error_m3']) for r in rows)
    assert max_difference < 1e-8, 'Equivalent equipment diverged'
    assert max_balance < 1e-8, 'Storage balance failed'
    return rows, {'matched_equipment_max_difference': max_difference,
                  'maximum_storage_balance_error_m3': max_balance,
                  'hydraulic_errors': sorted({r['hydraulic_error'] for r in rows if r['hydraulic_error']})}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', choices=('fallback', 'available'), default='fallback')
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts/water-hydraulics-v2')
    parser.add_argument('--plot', action='store_true', help='Also save a closure/reopening chart (requires matplotlib)')
    args = parser.parse_args()
    rows, checks = collect(args.engine)
    args.output.mkdir(parents=True, exist_ok=True)
    source = ROOT/'services/plant_sim/app/simulator.py'
    report = dict(seed=42, model_version=WATER_HYDRAULIC_VERSION, requested_engine=args.engine, controller='fixed commands; no PLC or AI',
                  simulator_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                  checks=checks, rows=rows)
    (args.output/f'{args.engine}.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    with (args.output/f'{args.engine}.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    if args.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        series = [r for r in rows if r['case'] == 'manual_filter_close_reopen']
        minutes = [r['minutes_after'] for r in series]
        fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True, layout='constrained')
        panels = [('filter_inlet_pressure_kpa', 'Upstream pressure (kPa)', '#0072B2'),
                  ('raw_flow_m3h', 'Treatment flow (m³/h)', '#009E73'),
                  ('clearwell_level_pct', 'Clearwell level (%)', '#D55E00')]
        for ax, (field, label, color) in zip(axes, panels):
            ax.plot(minutes, [r[field] for r in series], color=color, linewidth=2.5)
            ax.set_ylabel(label)
            ax.axvspan(0, 1, color='grey', alpha=.06)
            for at in (1, 16):
                ax.axvline(at, color='#666666', linestyle=':', linewidth=1)
            ax.spines[['top', 'right']].set_visible(False)
            ax.grid(axis='y', alpha=.15)
        axes[0].set_title('Manual valve closure and reopening\nFixed pump commands · simulated water plant', loc='left')
        axes[0].text(1.4, .90, 'Close command', transform=axes[0].get_xaxis_transform())
        axes[0].text(16.4, .90, 'Reopen command', transform=axes[0].get_xaxis_transform())
        axes[-1].set_xlabel('Simulated minutes after warm-up')
        for suffix in ('png', 'svg', 'pdf'):
            fig.savefig(args.output/f'{args.engine}-closure.{suffix}', dpi=220)
        plt.close(fig)
    print(json.dumps({'output': str(args.output), 'samples': len(rows), **checks}))


if __name__ == '__main__':
    main()
