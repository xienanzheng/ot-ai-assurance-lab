from datetime import datetime, timedelta, timezone

try:
    from plc_app.control_blocks import BackwashPhase, BackwashSequencer, EquipmentRuntime, OnDelayTimer, PIController
except ImportError:
    from services.plc_control.app.control_blocks import BackwashPhase, BackwashSequencer, EquipmentRuntime, OnDelayTimer, PIController


def test_pi_controller_limits_slew_and_avoids_unbounded_windup():
    loop = PIController("pressure", 5.0, 2.0, 0.0, 100.0, 4.0, last_output=50.0)
    outputs = [
        loop.update(setpoint=80.0, process_value=20.0, dt_minutes=1.0)
        for _ in range(20)
    ]
    assert outputs[0] == 54.0
    assert outputs[-1] <= 100.0
    assert abs(loop.integral) <= 75.0


def test_on_delay_requires_a_continuous_condition():
    timer = OnDelayTimer(2.0)
    assert timer.update(True, 1.0) is False
    assert timer.update(False, 1.0) is False
    assert timer.update(True, 1.0) is False
    assert timer.update(True, 1.0) is True


def test_equipment_runtime_enforces_minimum_off_time():
    runtime = EquipmentRuntime(running=True)
    assert runtime.update(False, 1.0) is False
    assert runtime.update(True, 1.0, minimum_off_minutes=3.0) is False
    assert runtime.update(True, 2.0, minimum_off_minutes=3.0) is True
    assert runtime.starts == 1


def test_backwash_sequence_is_timed_and_requires_feedback():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sequence = BackwashSequencer()
    sequence.request("operator")
    first = sequence.update(
        now=now,
        filter_dp_kpa=45.0,
        clearwell_level_pct=70.0,
        outlet_position_pct=95.0,
        sensor_quality_ok=True,
    )
    assert sequence.phase == BackwashPhase.ISOLATING
    assert first["filter_outlet_valve_pct"] == 15.0

    second = sequence.update(
        now=now + timedelta(minutes=1),
        filter_dp_kpa=45.0,
        clearwell_level_pct=70.0,
        outlet_position_pct=15.0,
        sensor_quality_ok=True,
    )
    assert sequence.phase == BackwashPhase.BACKWASH
    assert second["backwash_request"] is True

    sequence.update(
        now=now + timedelta(minutes=6),
        filter_dp_kpa=20.0,
        clearwell_level_pct=65.0,
        outlet_position_pct=15.0,
        sensor_quality_ok=True,
    )
    assert sequence.phase == BackwashPhase.RINSE
    sequence.update(
        now=now + timedelta(minutes=8),
        filter_dp_kpa=20.0,
        clearwell_level_pct=65.0,
        outlet_position_pct=20.0,
        sensor_quality_ok=True,
    )
    assert sequence.phase == BackwashPhase.RETURNING
    sequence.update(
        now=now + timedelta(minutes=9),
        filter_dp_kpa=20.0,
        clearwell_level_pct=65.0,
        outlet_position_pct=90.0,
        sensor_quality_ok=True,
    )
    assert sequence.phase == BackwashPhase.IDLE
    assert sequence.completed_cycles == 1


def test_backwash_blocks_and_aborts_on_storage_limits():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sequence = BackwashSequencer()
    sequence.request("operator")
    result = sequence.update(
        now=now,
        filter_dp_kpa=45.0,
        clearwell_level_pct=42.0,
        outlet_position_pct=95.0,
        sensor_quality_ok=True,
    )
    assert sequence.phase == BackwashPhase.BLOCKED
    assert "below 50" in result["blocked_reason"]

    sequence.update(
        now=now + timedelta(minutes=1),
        filter_dp_kpa=45.0,
        clearwell_level_pct=60.0,
        outlet_position_pct=95.0,
        sensor_quality_ok=True,
    )
    assert sequence.phase == BackwashPhase.ISOLATING
    aborted = sequence.update(
        now=now + timedelta(minutes=2),
        filter_dp_kpa=45.0,
        clearwell_level_pct=30.0,
        outlet_position_pct=15.0,
        sensor_quality_ok=True,
    )
    assert sequence.phase == BackwashPhase.RETURNING
    assert "aborted" in sequence.event_log[-1].lower()
    assert aborted["filter_outlet_valve_pct"] == 95.0
