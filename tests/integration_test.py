"""Opt-in checks for a running Compose stack.

Run with: WATERLAB_INTEGRATION=1 pytest tests/integration_test.py -q
"""

import json
import os
import urllib.request

import pytest


pytestmark = pytest.mark.skipif(os.getenv("WATERLAB_INTEGRATION") != "1", reason="Compose stack is not enabled")
BASE_URL = os.getenv("WATERLAB_BASE_URL", "http://127.0.0.1:18780").rstrip("/")


def test_dashboard_and_api_are_reachable():
    with urllib.request.urlopen(f"{BASE_URL}/", timeout=4) as response:
        assert response.status == 200
    with urllib.request.urlopen(f"{BASE_URL}/api/v1/state", timeout=4) as response:
        assert response.status == 200


def request_json(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=6) as response:
        return json.load(response)


def test_all_lab_fault_injections_create_visible_consequences():
    definitions = request_json("/api/v1/injections")["definitions"]
    assert len(definitions) == 6
    results = {}
    try:
        for definition in definitions:
            request_json("/api/v1/injections", method="DELETE")
            result = request_json(
                f"/api/v1/injections/{definition['id']}",
                method="POST",
                payload={"duration_minutes": 60},
            )
            plant = result["plant"]
            assert definition["id"] in plant["active_injections"]
            assert any(alarm["code"] == "CONTROL_OVERRIDE_ACTIVE" for alarm in plant["active_alarms"])
            results[definition["id"]] = plant
    finally:
        request_json("/api/v1/injections", method="DELETE")

    assert results["clearwell_overflow"]["sensors"]["clearwell_level_model_pct"]["value"] == 100
    assert results["clearwell_overflow"]["sensors"]["clearwell_overflow_m3h"]["value"] > 0
    assert results["level_sensor_spoof_low"]["sensors"]["clearwell_level_pct"]["value"] == 32
    assert results["level_sensor_spoof_low"]["twin_health"]["integrity_flags"]
    assert results["chlorine_sensor_spoof_high"]["sensors"]["chlorine_residual_mg_l"]["value"] == 2.6
    assert results["pump_valve_conflict"]["valves"]["filter_outlet"]["position_pct"] == 0
    assert results["pump_valve_conflict"]["sensors"]["pump_deadhead_pressure_kpa"]["value"] > 200
    assert results["zone_2_valve_forced_closed"]["valves"]["zone_2_isolation"]["position_pct"] == 0
    assert results["chlorine_overfeed"]["sensors"]["chlorine_dose_actual_mg_l"]["value"] == 5


def test_infrastructure_rooms_expose_live_models_and_ai_gates():
    state = request_json("/api/v1/infrastructure/state")
    scenarios = request_json("/api/v1/infrastructure/scenarios")
    assert state["nuclear"]["domain"] == "nuclear"
    assert state["grid"]["domain"] == "grid"
    assert len(scenarios["nuclear"]) >= 10
    assert len(scenarios["grid"]) >= 7

    nuclear_step = request_json(
        "/api/v1/infrastructure/nuclear/command",
        method="POST",
        payload={"action": "step", "minutes": 1},
    )
    grid_step = request_json(
        "/api/v1/infrastructure/grid/command",
        method="POST",
        payload={"action": "step", "minutes": 1},
    )
    assert nuclear_step["elapsed_minutes"] >= 1
    assert grid_step["elapsed_minutes"] >= 1

    nuclear_ai = request_json("/api/v1/infrastructure/nuclear/ai", method="POST")
    grid_ai = request_json("/api/v1/infrastructure/grid/ai", method="POST")
    assert set(nuclear_ai["decision"]["changes"]) <= {"turbine_load_target_mwe", "condenser_cooling_pct", "thermal_dispatch_target_mwth"}
    assert "gate" in grid_ai["decision"]

    tuned = request_json(
        "/api/v1/infrastructure/nuclear/tuning",
        method="PUT",
        payload={"preset": "high_inertia"},
    )
    assert tuned["tuning"]["preset"] == "high_inertia"
    assert set(tuned["equipment"]["primary_loops"]) == {"A", "B", "C"}
    assert len(tuned["procedures"]) == 4

    request_json("/api/v1/infrastructure/nuclear/command", method="POST", payload={"action": "reset"})
    request_json("/api/v1/infrastructure/grid/command", method="POST", payload={"action": "reset"})
