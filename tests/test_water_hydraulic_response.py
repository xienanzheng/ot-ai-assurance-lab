"""Physical relationships, using plant instances without a controller or AI."""
import pytest

from services.plant_sim.app.simulator import WaterPlantSimulator


def plant():
    sim = WaterPlantSimulator(seed=42)
    sim.network = None  # Exercise the shipped analytical fallback explicitly.
    sim.advance(10)
    return sim


def test_manual_filter_closure_reduces_raw_flow_and_raises_upstream_pressure():
    sim = plant()
    initial_flow, initial_pressure = sim.raw_flow_m3h, sim.filter_inlet_pressure_kpa
    sim.set_actuators({'filter_outlet_valve_pct': 0})
    flows, pressures = [], []
    for _ in range(10):
        sim.advance(1)
        flows.append(sim.raw_flow_m3h)
        pressures.append(sim.filter_inlet_pressure_kpa)
    assert flows[-1] == 0
    assert all(b <= a for a, b in zip(flows, flows[1:]))
    assert all(b >= a for a, b in zip(pressures, pressures[1:]))
    assert pressures[-1] > initial_pressure * 1.5
    assert flows[0] < initial_flow
    assert any(a.code == 'PUMP_DEADHEAD' for a in sim.snapshot().active_alarms)
    sim.advance(10)
    assert sim.filter_inlet_pressure_kpa == pytest.approx(pressures[-1])


def test_equivalent_manual_and_injected_equipment_have_same_hydraulics():
    manual, injected = plant(), plant()
    for sim in (manual, injected):
        sim.set_actuators({'intake_pump_speed_pct': 75, 'filter_outlet_valve_pct': 0})
        sim.valve_positions['filter_outlet'] = 0
    injected.inject('pump_valve_conflict', 60)
    for _ in range(10):
        manual.advance(1)
        injected.advance(1)
        for name in ('raw_flow_m3h', 'filter_inlet_pressure_kpa', 'filter_outlet_pressure_kpa',
                     'distribution_flow_m3h', 'clearwell_level_pct'):
            assert getattr(manual, name) == pytest.approx(getattr(injected, name))


def test_closed_treatment_valve_does_not_disconnect_clearwell_from_high_lift():
    sim = plant()
    sim.set_actuators({'filter_outlet_valve_pct': 0})
    sim.advance(10)
    level = sim.clearwell_level_pct
    assert sim.raw_flow_m3h == 0
    assert sim.distribution_flow_m3h > 100
    sim.advance(10)
    assert sim.clearwell_level_pct < level
    assert abs(sim.water_balance_error_m3) < 1e-8


def test_stopping_deadheaded_pump_removes_added_head_and_alarm():
    sim = plant()
    sim.set_actuators({'filter_outlet_valve_pct': 0})
    sim.advance(10)
    sim.set_actuators({'intake_pump_speed_pct': 0})
    sim.advance(1)
    assert sim.raw_flow_m3h == 0
    assert sim.pump_deadhead_pressure_kpa == 0
    assert sim.filter_inlet_pressure_kpa < 10
    assert not any(a.code == 'PUMP_DEADHEAD' for a in sim.snapshot().active_alarms)


def test_zone_closure_is_visible_before_five_minute_refresh():
    sim = plant()
    before = sim.zone_pressures[1]
    sim.set_actuators({'zone_2_isolation_valve_pct': 0})
    sim.advance(1)
    assert sim.zone_pressures[1] < before


def test_reopening_restores_flow_gradually_without_reset():
    sim = plant()
    sim.set_actuators({'filter_outlet_valve_pct': 0})
    sim.advance(10)
    assert sim.raw_flow_m3h == 0
    sim.set_actuators({'filter_outlet_valve_pct': 95})
    sim.advance(1)
    first = sim.raw_flow_m3h
    sim.advance(9)
    assert 0 < first < sim.raw_flow_m3h
    assert sim.filter_inlet_pressure_kpa < 200
    assert not any(a.code == 'PUMP_DEADHEAD' for a in sim.snapshot().active_alarms)


def test_closed_valve_retains_pressure_difference_at_zero_flow():
    sim = plant()
    sim.set_actuators({'zone_2_isolation_valve_pct': 0})
    sim.advance(10)
    assert sim.zone_served[1] == 0
    assert sim.zone_valve_dp_kpa[1] > 100


def test_filter_valve_display_excludes_filter_media_loss():
    sim = plant()
    sim.set_actuators({'filter_outlet_valve_pct': 100})
    sim.advance(1)
    valve = sim.snapshot().valves['filter_outlet']
    assert sim.filter_dp_kpa > 5  # Filter media still creates a pressure drop.
    assert valve.differential_pressure_kpa == pytest.approx(0, abs=0.02)


def test_chlorine_change_has_delayed_response_and_flow_interlock():
    sim = plant()
    sim.set_actuators({'chlorine_dose_mg_l': 2.5})
    before = sim.true_chlorine_mg_l
    sim.advance(1)
    first = sim.true_chlorine_mg_l
    sim.advance(5)
    assert before < first < sim.true_chlorine_mg_l < 2.5
    sim.set_actuators({'filter_outlet_valve_pct': 0})
    sim.advance(10)
    assert not sim.chemical_feed_flow_proof
    assert sim.actual_chlorine_dose_mg_l == 0
    before = sim.true_chlorine_mg_l
    sim.advance(1)
    assert 0 < sim.true_chlorine_mg_l < before


@pytest.mark.parametrize('command', ['intake_pump_speed_pct', 'intake_gate_pct'])
def test_stopped_intake_cannot_supply_water_or_generate_deadhead(command):
    sim = plant()
    sim.set_actuators({command: 0})
    sim.advance(10)
    assert sim.raw_flow_m3h == 0
    assert sim.pump_deadhead_pressure_kpa == 0
    assert not sim.chemical_feed_flow_proof


def test_wntr_can_recalculate_each_step_and_after_reset():
    pytest.importorskip('wntr')
    sim = WaterPlantSimulator()
    assert sim.network is not None
    for _ in range(3):
        sim.advance(1)
        assert sim.hydraulic_error is None
        assert sim.hydraulic_engine.startswith('WNTR PDD')
    sim.reset()
    sim.advance(1)
    assert sim.hydraulic_error is None
    assert sim.hydraulic_engine.startswith('WNTR PDD')


def test_wntr_closed_zone_is_isolated_instead_of_just_high_resistance():
    pytest.importorskip('wntr')
    sim = WaterPlantSimulator()
    sim.set_actuators({'zone_2_isolation_valve_pct': 0})
    sim.advance(10)
    assert sim.hydraulic_error is None
    assert sim.zone_pressures[1] == 0
    assert sim.zone_served[1] == 0


def test_wntr_stopped_pump_cannot_remain_an_open_supply_path():
    pytest.importorskip('wntr')
    sim = WaterPlantSimulator()
    sim.set_actuators({'high_lift_pump_speed_pct': 0})
    sim.advance(1)
    assert sim.hydraulic_error is None
    assert sim.network.get_link('HighLift').flow == 0
    assert sim.distribution_flow_m3h <= 25
