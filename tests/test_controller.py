try:
    from plc_app.controller import BaselineController, SafetyGate
except ImportError:
    from services.plc_control.app.controller import BaselineController, SafetyGate

from shared.models import ControlProposal, SetpointChanges


def proposal(changes, confidence=0.9):
    return ControlProposal(
        changes=SetpointChanges(**changes),
        expected_effect="Improve balanced operation",
        confidence=confidence,
        explanation="Small supervisory adjustment",
        source="test",
    )


def test_gate_accepts_small_safe_change(safe_snapshot):
    decision = SafetyGate(BaselineController()).evaluate(proposal({"pressure_target_m": 46}), safe_snapshot)
    assert decision.status == "accepted"
    assert decision.applied_values.pressure_target_m == 46


def test_gate_rejects_out_of_range_change(safe_snapshot):
    decision = SafetyGate(BaselineController()).evaluate(proposal({"pressure_target_m": 92}), safe_snapshot)
    assert decision.status == "rejected"
    assert any("outside" in item for item in decision.violated_constraints)


def test_gate_rejects_stale_sensor_data(safe_snapshot):
    safe_snapshot.sensors["zone_1_pressure_m"].quality = "stale"
    decision = SafetyGate(BaselineController()).evaluate(proposal({"pressure_target_m": 45}), safe_snapshot)
    assert decision.status == "rejected"
    assert any("quality" in item for item in decision.violated_constraints)


def test_gate_rejects_low_confidence(safe_snapshot):
    decision = SafetyGate(BaselineController()).evaluate(proposal({}, confidence=0.2), safe_snapshot)
    assert decision.status == "rejected"


def test_emergency_stop_returns_recovery_command(safe_snapshot):
    safe_snapshot.emergency_stop = True
    command = BaselineController().calculate(safe_snapshot)
    assert command.emergency_stop is False
    assert command.high_lift_pump_speed_pct == 62.0


def test_supervisory_setpoints_expire(safe_snapshot):
    controller = BaselineController()
    controller.apply_setpoint_changes(
        SetpointChanges(pressure_target_m=46),
        valid_until=safe_snapshot.simulation_time,
    )
    controller.calculate(safe_snapshot)
    assert controller.setpoints.pressure_target_m == 44.0


def test_gate_rejects_two_zone_valves_closing_together(safe_snapshot):
    decision = SafetyGate(BaselineController()).evaluate(
        proposal({"zone_1_isolation_target_pct": 90, "zone_2_isolation_target_pct": 90}),
        safe_snapshot,
    )
    assert decision.status == "rejected"
    assert any("Only one" in item for item in decision.violated_constraints)


def test_gate_rejects_zone_restriction_at_low_pressure(safe_snapshot):
    safe_snapshot.sensors["zone_1_pressure_m"].value = 31.0
    decision = SafetyGate(BaselineController()).evaluate(
        proposal({"zone_1_isolation_target_pct": 90}),
        safe_snapshot,
    )
    assert decision.status == "rejected"
    assert any("pressure is low" in item for item in decision.violated_constraints)


def test_baseline_uses_bounded_valve_commands(safe_snapshot):
    controller = BaselineController()
    command = controller.calculate(safe_snapshot)
    assert 0 <= command.intake_gate_pct <= 100
    assert command.pressure_reducing_valve_setpoint_m == 52.0
    assert 0 <= command.naoh_dose_mg_l <= 25


def test_gate_accepts_small_finished_ph_change(safe_snapshot):
    decision = SafetyGate(BaselineController()).evaluate(
        proposal({"finished_water_ph_target": 7.45}),
        safe_snapshot,
    )
    assert decision.status == "accepted"


def test_gate_rejects_higher_ph_when_chlorine_ct_is_low(safe_snapshot):
    safe_snapshot.sensors["chlorine_ct_mg_min_l"].value = 12.0
    decision = SafetyGate(BaselineController()).evaluate(
        proposal({"finished_water_ph_target": 7.45}),
        safe_snapshot,
    )
    assert decision.status == "rejected"
    assert any("chlorine CT" in item for item in decision.violated_constraints)


def test_baseline_uses_model_level_to_protect_against_spoofing(safe_snapshot):
    safe_snapshot.sensors["clearwell_level_pct"].value = 32.0
    safe_snapshot.sensors["clearwell_level_model_pct"].value = 97.0
    command = BaselineController().calculate(safe_snapshot)
    assert command.intake_pump_speed_pct == 0.0
    assert command.high_lift_pump_speed_pct == 100.0


def test_baseline_stops_intake_for_closed_filter_outlet(safe_snapshot):
    safe_snapshot.sensors["filter_outlet_valve_position_pct"].value = 0.0
    command = BaselineController().calculate(safe_snapshot)
    assert command.intake_pump_speed_pct == 0.0


def test_baseline_commands_chlorine_off_on_confirmed_overfeed(safe_snapshot):
    safe_snapshot.sensors["chlorine_dose_actual_mg_l"].value = 5.0
    command = BaselineController().calculate(safe_snapshot)
    assert command.chlorine_dose_mg_l == 0.0


def test_gate_rate_limits_a_large_but_valid_change(safe_snapshot):
    decision = SafetyGate(BaselineController()).evaluate(
        proposal({"pressure_target_m": 52.0}),
        safe_snapshot,
    )
    assert decision.status == "modified"
    assert decision.applied_values.pressure_target_m == 48.0
    assert any("rate-limited" in item for item in decision.modifications)


def test_gate_rejects_chlorine_change_during_sensor_model_disagreement(safe_snapshot):
    safe_snapshot.sensors["chlorine_residual_mg_l"].value = 2.0
    safe_snapshot.sensors["chlorine_model_estimate_mg_l"].value = 1.0
    decision = SafetyGate(BaselineController()).evaluate(
        proposal({"chlorine_target_mg_l": 1.3}),
        safe_snapshot,
    )
    assert decision.status == "rejected"
    assert any("disagree" in item for item in decision.violated_constraints)


def test_unrelated_stale_sensor_does_not_block_pressure_change(safe_snapshot):
    safe_snapshot.sensors["raw_turbidity_ntu"].quality = "stale"
    decision = SafetyGate(BaselineController()).evaluate(
        proposal({"pressure_target_m": 46.0}),
        safe_snapshot,
    )
    assert decision.status == "accepted"


def test_deadhead_trip_latches_until_a_safe_reset(safe_snapshot):
    controller = BaselineController()
    safe_snapshot.sensors["pump_deadhead_pressure_kpa"].value = 190.0
    command = controller.calculate(safe_snapshot)
    assert command.intake_pump_speed_pct == 0.0
    assert controller.trip_latches["INTAKE_DEADHEAD"] is True

    safe_snapshot.sensors["pump_deadhead_pressure_kpa"].value = 0.0
    command = controller.calculate(safe_snapshot)
    assert command.intake_pump_speed_pct == 0.0
    result = controller.reset_trips(safe_snapshot)
    assert result["reset"] == ["INTAKE_DEADHEAD"]


def test_backwash_request_enters_sequence_when_permissives_are_met(safe_snapshot):
    controller = BaselineController()
    safe_snapshot.sensors["filter_dp_kpa"].value = 45.0
    decision = SafetyGate(controller).evaluate(
        proposal({"backwash_request": True}),
        safe_snapshot,
    )
    assert decision.status == "accepted"
    controller.apply_setpoint_changes(decision.applied_values, source="test")
    command = controller.calculate(safe_snapshot)
    assert command.filter_outlet_valve_pct < 95.0
    assert controller.status()["backwash_sequence"]["phase"] == "isolating"


def test_control_status_exposes_permissives_loops_and_runtime(safe_snapshot):
    controller = BaselineController()
    controller.calculate(safe_snapshot)
    status = controller.status()
    assert status["permissives"]["intake_path"]["ok"] is True
    assert status["control_loops"]["distribution_pressure"]["setpoint"] == 44.0
    assert "starts" in status["equipment_runtime"]["high_lift_pump"]


def test_chemical_feeds_stop_without_flow_proof(safe_snapshot):
    safe_snapshot.sensors["raw_flow_m3h"].value = 0.0
    safe_snapshot.sensors["chemical_feed_flow_proof"].value = 0.0
    command = BaselineController().calculate(safe_snapshot)
    assert command.coagulant_dose_mg_l == 0.0
    assert command.chlorine_dose_mg_l == 0.0
    assert command.naoh_dose_mg_l == 0.0
