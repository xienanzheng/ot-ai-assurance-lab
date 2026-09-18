from __future__ import annotations

try:
    from infra_app.grid import GridSimulator
    from infra_app.nuclear import NuclearSimulator
except ModuleNotFoundError:
    from services.infrastructure_sim.app.grid import GridSimulator
    from services.infrastructure_sim.app.nuclear import NuclearSimulator


def test_nuclear_normal_operation_is_stable_and_repeatable():
    first = NuclearSimulator()
    second = NuclearSimulator()
    first.advance(60)
    second.advance(60)
    assert first.snapshot().safety_state == "normal"
    assert first.snapshot().model_dump() == second.snapshot().model_dump()
    assert 99.0 <= first.reactor_power_pct <= 101.0
    assert 50.0 <= first.steam_generator_level_pct <= 60.0


def test_nuclear_loss_of_feedwater_uses_independent_trip_and_auxiliary_feedwater():
    simulator = NuclearSimulator()
    simulator.reset(scenario="loss_feedwater")
    simulator.advance(80)
    codes = {alarm["code"] for alarm in simulator.snapshot().alarms}
    assert "REACTOR_TRIP" in codes
    assert simulator.controls["reactor_trip"] is True
    assert simulator.controls["auxiliary_feedwater"] is True
    assert simulator.controls["control_rod_withdrawal_pct"] == 0.0


def test_nuclear_ai_cannot_cross_the_safety_boundary():
    simulator = NuclearSimulator()
    simulator.controller_mode = "gated_auto"
    decision = simulator.apply_ai_proposal(
        {"control_rod_withdrawal_pct": 78.0, "turbine_load_target_mwe": 980.0},
        confidence=0.95,
        objective="Increase output",
        explanation="Test proposal",
    )
    assert decision.gate.status == "rejected"
    assert decision.gate.applied == {}
    assert simulator.controls["control_rod_withdrawal_pct"] == 72.0


def test_nuclear_low_confidence_proposal_is_rejected():
    simulator = NuclearSimulator()
    simulator.controller_mode = "gated_auto"
    decision = simulator.apply_ai_proposal(
        {"turbine_load_target_mwe": 980.0},
        confidence=0.2,
        objective="Small load change",
        explanation="Low confidence test",
    )
    assert decision.gate.status == "rejected"
    assert simulator.controls["turbine_load_target_mwe"] == 1000.0


def test_nuclear_snapshot_exposes_three_public_capability_loops_and_guidance():
    simulator = NuclearSimulator()
    simulator.advance(5)
    snapshot = simulator.snapshot()
    assert snapshot.equipment["reactor_coolant_pumps"]["total"] == 3
    assert set(snapshot.equipment["primary_loops"]) == {"A", "B", "C"}
    assert len(snapshot.procedures) == 4
    assert snapshot.model_health["fidelity"] == "reduced-order software-in-the-loop"
    assert len(snapshot.history["reactor_power_pct"]) == 6


def test_nuclear_loop_imbalance_is_visible_in_individual_steam_generators():
    simulator = NuclearSimulator()
    simulator.reset(scenario="steam_generator_imbalance")
    simulator.advance(70)
    levels = [loop["sg_level_pct"] for loop in simulator.loops.values()]
    assert max(levels) - min(levels) > 15.0
    assert simulator.snapshot().model_health["steam_generator_level_spread_pct"] > 15.0


def test_nuclear_thermal_dispatch_reduces_electric_output_inside_gate():
    simulator = NuclearSimulator()
    simulator.reset(scenario="thermal_dispatch_ramp")
    simulator.advance(60)
    snapshot = simulator.snapshot()
    assert snapshot.sensors["thermal_dispatch_mwth"]["value"] > 200.0
    assert snapshot.sensors["electric_output_mwe"]["value"] < 950.0
    assert snapshot.equipment["thermal_dispatch_skid"]["connected"] is True


def test_nuclear_tuning_preset_changes_reduced_order_response_gains():
    simulator = NuclearSimulator()
    simulator.set_tuning({"preset": "high_inertia"})
    assert simulator.snapshot().tuning == {
        "preset": "high_inertia",
        "thermal_response": 0.55,
        "pressure_response": 0.7,
        "inventory_response": 0.75,
        "condenser_response": 0.8,
    }


def test_nuclear_ai_can_request_bounded_heat_dispatch_but_not_safety_actions():
    simulator = NuclearSimulator()
    simulator.controller_mode = "gated_auto"
    accepted = simulator.apply_ai_proposal(
        {"thermal_dispatch_target_mwth": 40.0},
        confidence=0.9,
        objective="Start bounded industrial heat dispatch",
        explanation="Test bounded proposal",
    )
    assert accepted.gate.status == "accepted"
    assert simulator.controls["thermal_dispatch_target_mwth"] == 40.0
    rejected = simulator.apply_ai_proposal(
        {"reactor_trip": 1.0},
        confidence=0.99,
        objective="Attempt safety action",
        explanation="Test prohibited proposal",
    )
    assert rejected.gate.status == "rejected"
    assert simulator.controls["reactor_trip"] is False


def test_grid_power_flow_and_normal_operation_are_stable():
    simulator = GridSimulator()
    simulator.advance(60)
    snapshot = simulator.snapshot()
    assert snapshot.safety_state == "normal"
    assert len(simulator.line_results) == 6
    assert all(float(line["loading_pct"]) >= 0 for line in simulator.line_results)
    assert 59.5 < simulator.true_frequency_hz < 60.5


def test_grid_generator_trip_creates_supply_consequence():
    simulator = GridSimulator()
    simulator.reset(scenario="generator_trip")
    simulator.advance(80)
    codes = {alarm["code"] for alarm in simulator.snapshot().alarms}
    assert simulator.gas_output_mw < 1.0
    assert simulator.unserved_load_mw > 0
    assert "UNSERVED_LOAD" in codes


def test_grid_line_trip_opens_only_the_selected_breaker():
    simulator = GridSimulator()
    simulator.reset(scenario="line_trip")
    simulator.advance(40)
    lines = {line["id"]: line for line in simulator.line_results}
    assert lines["L-CI"]["closed"] is False
    assert all(line["closed"] is True for name, line in lines.items() if name != "L-CI")


def test_grid_frequency_spoof_is_detected_by_model_comparison():
    simulator = GridSimulator()
    simulator.reset(scenario="frequency_sensor_spoof")
    simulator.advance(80)
    codes = {alarm["code"] for alarm in simulator.snapshot().alarms}
    assert abs(simulator.frequency_hz - simulator.true_frequency_hz) > 0.15
    assert "FREQUENCY_MODEL_MISMATCH" in codes


def test_grid_ai_cannot_operate_breakers():
    simulator = GridSimulator()
    simulator.controller_mode = "gated_auto"
    decision = simulator.apply_ai_proposal(
        {"L-CI_breaker_closed": 0.0, "battery_dispatch_mw": 20.0},
        confidence=0.95,
        objective="Change network topology",
        explanation="Test proposal",
    )
    assert decision.gate.status == "rejected"
    assert simulator.controls["L-CI_breaker_closed"] is True
