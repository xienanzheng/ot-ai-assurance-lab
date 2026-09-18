import csv
import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.exercise import ExerciseRecorder
from shared.exercise_api import exercise_router
from services.infrastructure_sim.app.grid import GridSimulator, GRID_SCENARIOS, LINES
from services.infrastructure_sim.app.nuclear import NuclearSimulator, NUCLEAR_SCENARIOS
from services.plc_control.app.controller import BaselineController
from services.plant_sim.app.simulator import WaterPlantSimulator


@pytest.mark.parametrize("factory", [GridSimulator, NuclearSimulator])
def test_configure_preserves_elapsed_state_except_new_scenario(factory):
    sim = factory()
    sim.advance(9)
    original = sim.exercise.run_id
    sim.command("configure", speed=60, mode="shadow")
    assert sim.minute == 9 and sim.speed == 60 and sim.controller_mode == "shadow"
    assert sim.exercise.run_id == original
    sim.command("start")
    sim.command("pause")
    assert sim.minute == 9
    sim.command("reset")
    assert sim.minute == 0 and sim.exercise.run_id != original


@pytest.mark.parametrize("factory,scenarios", [(GridSimulator, GRID_SCENARIOS), (NuclearSimulator, NUCLEAR_SCENARIOS)])
def test_every_infrastructure_scenario_has_finite_repeatable_evidence(factory, scenarios):
    import json
    for scenario in scenarios:
        sim = factory()
        sim.reset(scenario=scenario["id"], mode="baseline")
        sim.advance(120)
        evidence = sim.exercise.report(True)
        json.dumps(evidence, allow_nan=False)
        assert len(evidence["samples"]) == 121
        assert [s["minute"] for s in evidence["samples"]] == list(range(121))
        assert sim.ai_decision is None
        repeat = factory()
        repeat.reset(scenario=scenario["id"], mode="baseline")
        repeat.advance(120)
        assert repeat.exercise.report(True)["samples"] == evidence["samples"]


def test_grid_isolated_load_is_deenergized_with_no_phantom_import():
    sim = GridSimulator()
    result = sim.manual({"L-CM_breaker_closed": False, "L-SM_breaker_closed": False})
    assert result.status == "accepted"
    assert len(sim.islands) == 2
    assert sim.bus_voltages_pu[2] == 0
    assert sim.served_by_bus[2] == 0
    assert sim.unserved_load_mw >= 390
    assert all(abs(i["balance_residual_mw"]) < 1e-7 for i in sim.islands)
    assert any(abs(line["flow_mw"]) > 1 for line in sim.line_results if line["closed"])


def test_grid_all_buses_isolated_conserves_each_island():
    sim = GridSimulator()
    sim.manual({f"{line['id']}_breaker_closed": False for line in LINES})
    assert len(sim.islands) == 5
    assert all(abs(i["balance_residual_mw"]) < 1e-7 for i in sim.islands)
    assert sum(i["import_mw"] for i in sim.islands if "B1" not in i["buses"]) == 0
    assert sim.served_load_mw + sim.unserved_load_mw == pytest.approx(sim.demand_mw)


def test_grid_unknown_breaker_is_rejected_atomically():
    sim = GridSimulator()
    before = sim.controls.copy()
    result = sim.manual({"bad_breaker_closed": False, "battery_dispatch_mw": 20.0})
    assert result.status == "rejected"
    assert sim.controls == before


@pytest.mark.parametrize("soc,target", [(10.001, 100.0), (94.999, -100.0)])
def test_battery_energy_limit_applies_to_actual_output(soc, target):
    sim = GridSimulator()
    sim.battery_soc_pct = soc
    sim.controls["battery_dispatch_mw"] = target
    sim.battery_output_mw = target
    sim.advance(1)
    assert 10.0 - 1e-9 <= sim.battery_soc_pct <= 95.0 + 1e-9
    assert abs(sim.battery_output_mw) < 1.0


def test_nuclear_first_out_remains_latched_and_decay_heat_persists():
    sim = NuclearSimulator()
    sim.reset(scenario="coolant_pump_trip", mode="baseline")
    sim.advance(40)
    first = sim.first_out_trip.copy()
    assert "Low primary-loop flow" in first["causes"]
    heat = sim.decay_heat_mw
    sim.advance(60)
    assert sim.first_out_trip == first
    assert 0 < sim.decay_heat_mw < heat
    assert len([e for e in sim.exercise.events if e["kind"] == "protection"]) == 1


def test_acknowledgement_does_not_clear_condition_and_recurrence_needs_ack():
    sim = GridSimulator()
    sim.true_frequency_hz = 58
    sim.exercise.capture(sim.snapshot(), sim.minute)
    alarm = next(a for a in sim.exercise.active.values() if a["code"] == "FREQUENCY_DEVIATION")
    sim.exercise.acknowledge(alarm["occurrence"], sim.minute)
    assert sim.snapshot().safety_state == "critical"
    assert alarm["acknowledged"]
    sim.true_frequency_hz = 60
    sim.exercise.capture(sim.snapshot(), sim.minute)
    sim.true_frequency_hz = 58
    sim.exercise.capture(sim.snapshot(), sim.minute)
    fresh = sim.exercise.active["FREQUENCY_DEVIATION"]
    assert not fresh["acknowledged"] and fresh["occurrence"] != alarm["occurrence"]
    with pytest.raises(ValueError):
        sim.exercise.acknowledge(alarm["occurrence"], sim.minute)


def test_exercise_api_exports_real_samples_and_rejects_stale_ack():
    sim = GridSimulator()
    sim.advance(12)
    app = FastAPI()
    app.include_router(exercise_router(lambda _: sim))
    client = TestClient(app)
    report = client.get("/grid/exercise").json()
    assert report["sample_count"] == 13
    response = client.post("/grid/exercise", json={"action": "note", "note": "Observed dispatch"})
    assert response.status_code == 200
    assert client.post("/grid/exercise", json={"action": "acknowledge", "occurrence": -1}).status_code == 409
    export = client.get("/grid/exercise/export?format=json").json()
    assert export["samples"][-1]["minute"] == 12
    assert export["events"][-1]["message"] == "Observed dispatch"
    rows = list(csv.reader(io.StringIO(client.get("/grid/exercise/export?format=csv").text)))
    assert len(rows) == 14 and "frequency_model_hz" in rows[0]


@pytest.mark.parametrize("levels", [(0.0, 20.0), (65.0, 68.0), (100.0, 100.0)])
def test_water_storage_balance_with_plc_and_empty_full_boundaries(levels):
    sim = WaterPlantSimulator()
    controller = BaselineController()
    sim.clearwell_level_pct, sim.elevated_tank_level_pct = levels
    for _ in range(25):
        sim.set_actuators(controller.calculate(sim.snapshot()).model_dump())
        sim.advance(1)
        assert abs(sim.water_balance_error_m3) < 1e-8
        assert 0 <= sim.clearwell_level_pct <= 100
        assert 0 <= sim.elevated_tank_level_pct <= 100
        assert all(0 <= served <= demand for served, demand in zip(sim.zone_served, sim.zone_demands))
    assert sim.exercise.report()["sample_count"] == 26


def test_evidence_rollover_preserves_cumulative_metrics():
    sim = GridSimulator()
    recorder = ExerciseRecorder("grid", "test")
    snapshot = sim.snapshot()
    snapshot.sensors["unserved_load_mw"]["value"] = 60
    for minute in range(1450):
        recorder.capture(snapshot, minute)
    report = recorder.report()
    assert report["dropped_samples"] == 9
    assert report["metrics"]["unserved_energy_mwh"] == 1449


@pytest.mark.parametrize("injection", ["clearwell_overflow", "zone_2_valve_forced_closed", "pump_valve_conflict"])
def test_water_faults_preserve_storage_balance(injection):
    sim = WaterPlantSimulator()
    sim.inject(injection, 20)
    sim.advance(10)
    assert abs(sim.water_balance_error_m3) < 1e-8
    assert sim.exercise.report()["sample_count"] == 11
    if injection == "clearwell_overflow":
        assert sim.exercise.report()["metrics"]["overflow_m3"] > 0
    if injection == "zone_2_valve_forced_closed":
        assert sim.zone_served[1] == 0


def test_water_resume_preserves_sampling_and_ai_bookkeeping(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from services.supervisor.app import run_manager as module
    from shared.models import RunConfig
    manager = module.RunManager("http://plant", "http://plc")
    manager.active_run_id = "test-run"
    manager.last_sample_time = "already-recorded"
    manager.last_decision_minute = 5
    manager._config_for = lambda _: RunConfig()
    calls = []
    async def command(action):
        calls.append(action)
        return SimpleNamespace(elapsed_minutes=5)
    manager.command_plant = command
    record = SimpleNamespace(status="paused")
    class Session:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args): return record
        def commit(self): pass
    monkeypatch.setattr(module, "SessionLocal", Session)
    result = asyncio.run(manager.start("test-run"))
    assert result.elapsed_minutes == 5 and calls == ["start"]
    assert manager.last_sample_time == "already-recorded" and manager.last_decision_minute == 5
    assert record.status == "running"


def test_isolated_battery_cannot_charge_from_a_phantom_supply():
    sim = GridSimulator()
    sim.manual({f"{line['id']}_breaker_closed": False for line in LINES})
    sim.solar_output_mw = 0.0
    sim.battery_output_mw = -100.0
    sim.controls["battery_dispatch_mw"] = -100.0
    initial_soc = sim.battery_soc_pct
    sim.advance(1)
    assert sim.battery_output_mw == 0.0
    assert sim.battery_soc_pct == initial_soc


def test_surplus_curtails_battery_before_drawing_stored_energy():
    sim = GridSimulator()
    sim.loads = [0.0] * 5
    sim.battery_output_mw = 100.0
    sim._run_power_flow()
    assert sim.battery_output_mw == 0.0
    assert all(abs(i["balance_residual_mw"]) < 1e-7 for i in sim.islands)
