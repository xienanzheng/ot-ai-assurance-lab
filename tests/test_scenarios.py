try:
    from plant_scenarios import INJECTIONS, demand_multiplier, injection_list, scenario_modifiers
except ImportError:
    from services.plant_sim.app.scenarios import INJECTIONS, demand_multiplier, injection_list, scenario_modifiers


def test_demand_pattern_is_repeatable():
    first = [demand_multiplier(minute, "normal_day") for minute in range(0, 1440, 15)]
    second = [demand_multiplier(minute, "normal_day") for minute in range(0, 1440, 15)]
    assert first == second


def test_morning_surge_exceeds_normal_demand():
    assert demand_multiplier(450, "morning_surge") > demand_multiplier(450, "normal_day")


def test_pump_failure_degrades_before_trip():
    degraded = scenario_modifiers(700, "pump_failure")
    failed = scenario_modifiers(850, "pump_failure")
    assert degraded["pump_efficiency_pct"] < 92
    assert failed["pump_available"] is False


def test_opc_interruption_marks_data_stale():
    assert scenario_modifiers(370, "opcua_interruption")["sensor_quality"] == "stale"


def test_hazard_injection_pack_has_the_expected_exercises():
    expected = {
        "clearwell_overflow",
        "level_sensor_spoof_low",
        "chlorine_sensor_spoof_high",
        "pump_valve_conflict",
        "zone_2_valve_forced_closed",
        "chlorine_overfeed",
    }
    assert set(INJECTIONS) == expected
    assert {item["id"] for item in injection_list()} == expected
