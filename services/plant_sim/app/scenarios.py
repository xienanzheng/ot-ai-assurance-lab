from __future__ import annotations

from dataclasses import dataclass
from math import exp


@dataclass(frozen=True)
class ScenarioDefinition:
    id: str
    name: str
    description: str
    fault_start_minute: int | None = None


@dataclass(frozen=True)
class InjectionDefinition:
    id: str
    name: str
    description: str
    consequence: str
    default_duration_minutes: int = 60
    severity: str = "critical"


SCENARIOS = {
    "gradual_turbidity_rise": ScenarioDefinition("gradual_turbidity_rise", "Gradual sustained source-quality deterioration", "Raw turbidity ramps from 8 to 72 illustrative NTU over minutes 10–30 and stays elevated; designed for a bounded recovery experiment.", 10),
    "normal_day": ScenarioDefinition("normal_day", "Normal 24-hour cycle", "A repeatable residential demand pattern."),
    "morning_surge": ScenarioDefinition("morning_surge", "Morning demand surge", "Demand rises sharply between 06:30 and 09:00.", 390),
    "turbidity_spike": ScenarioDefinition("turbidity_spike", "Raw-water turbidity spike", "Raw turbidity rises quickly and then recovers.", 420),
    "chlorine_sensor_drift": ScenarioDefinition("chlorine_sensor_drift", "Chlorine sensor drift", "The reported chlorine value drifts away from the simulated true value.", 600),
    "pump_failure": ScenarioDefinition("pump_failure", "High-lift pump degradation", "Pump efficiency declines before the high-lift pump trips.", 540),
    "zone_leak": ScenarioDefinition("zone_leak", "Zone 2 distribution leak", "A leak grows in zone 2 and increases demand while reducing pressure.", 480),
    "opcua_interruption": ScenarioDefinition("opcua_interruption", "OPC UA interruption", "Sensor quality becomes stale during a simulated connection interruption.", 360),
    "unsafe_ai": ScenarioDefinition("unsafe_ai", "Unsafe AI proposal", "The supervisor generates a test proposal that the safety gate must reject.", 60),
    "low_alkalinity": ScenarioDefinition("low_alkalinity", "Low source-water alkalinity", "Source alkalinity falls and reduces buffering through coagulation.", 300),
    "naoh_feed_failure": ScenarioDefinition("naoh_feed_failure", "NaOH feed-pump failure", "The caustic metering pump loses delivery while its command remains visible.", 480),
}


INJECTIONS = {
    "clearwell_overflow": InjectionDefinition(
        "clearwell_overflow",
        "Force clearwell overflow",
        "Forces the intake train high and the high-lift discharge low while the level approaches the overflow point.",
        "Storage rises, overflow begins, and the high-high level alarm activates.",
        180,
    ),
    "level_sensor_spoof_low": InjectionDefinition(
        "level_sensor_spoof_low",
        "Fake low level signal",
        "Reports a plausible low clearwell level while the process model continues to track the physical level.",
        "The controller asks for more inflow and twin residual checks identify the disagreement.",
        90,
        "warning",
    ),
    "chlorine_sensor_spoof_high": InjectionDefinition(
        "chlorine_sensor_spoof_high",
        "Fake high chlorine signal",
        "Reports a false high chlorine residual with good protocol quality.",
        "The controller may reduce dose, while the model estimate and reported value diverge.",
        120,
    ),
    "pump_valve_conflict": InjectionDefinition(
        "pump_valve_conflict",
        "Run pump against closed valve",
        "Forces the filter outlet valve shut and holds the upstream pump on despite the PLC command.",
        "Flow collapses, pressure rises, and the pump deadhead alarm activates.",
        30,
    ),
    "zone_2_valve_forced_closed": InjectionDefinition(
        "zone_2_valve_forced_closed",
        "Force Zone 2 valve closed",
        "Forces the Zone 2 isolation valve shut while its command remains open.",
        "Zone 2 loses pressure and supply, with valve command mismatch alarms.",
        60,
    ),
    "chlorine_overfeed": InjectionDefinition(
        "chlorine_overfeed",
        "Force chlorine overfeed",
        "Forces the simulated hypochlorite metering pump to its maximum dose independently of its command.",
        "Delivered dose and residual rise until the feed mismatch and high residual alarms activate.",
        60,
    ),
}


def demand_multiplier(minute: int, scenario: str) -> float:
    hour = (minute % 1440) / 60
    morning = 0.52 * exp(-((hour - 7.5) / 1.6) ** 2)
    evening = 0.36 * exp(-((hour - 19.0) / 2.1) ** 2)
    overnight = -0.20 * exp(-((hour - 3.0) / 2.2) ** 2)
    multiplier = 0.78 + morning + evening + overnight
    if scenario == "morning_surge" and 6.5 <= hour <= 9:
        multiplier += 0.45
    return max(0.45, multiplier)


def scenario_modifiers(minute: int, scenario: str) -> dict[str, float | bool | str]:
    result: dict[str, float | bool | str] = {
        "raw_turbidity_ntu": 8.0,
        "raw_ph": 7.35,
        "raw_alkalinity_mg_l_caco3": 55.0,
        "water_temperature_c": 15.0,
        "leak_flow_m3h": 0.0,
        "pump_efficiency_pct": 92.0,
        "pump_available": True,
        "chlorine_sensor_bias": 0.0,
        "sensor_quality": "good",
        "naoh_available": True,
    }
    if scenario == "turbidity_spike" and 420 <= minute < 660:
        elapsed = minute - 420
        result["raw_turbidity_ntu"] = 8.0 + 48.0 * exp(-((elapsed - 55) / 70) ** 2)
    if scenario == "gradual_turbidity_rise":
        result["raw_turbidity_ntu"] = 8.0 + 64.0 * max(0.0, min(1.0, (minute - 10) / 20.0))
    if scenario == "zone_leak" and minute >= 480:
        result["leak_flow_m3h"] = min(52.0, (minute - 480) * 0.35)
    if scenario == "pump_failure" and minute >= 540:
        result["pump_efficiency_pct"] = max(38.0, 92.0 - (minute - 540) * 0.18)
        if minute >= 840:
            result["pump_available"] = False
    if scenario == "chlorine_sensor_drift" and minute >= 600:
        result["chlorine_sensor_bias"] = min(0.9, (minute - 600) * 0.003)
        if minute >= 900:
            result["sensor_quality"] = "uncertain"
    if scenario == "opcua_interruption" and 360 <= minute < 390:
        result["sensor_quality"] = "stale"
    if scenario == "low_alkalinity" and 300 <= minute < 720:
        elapsed = minute - 300
        result["raw_alkalinity_mg_l_caco3"] = max(24.0, 55.0 - elapsed * 0.12)
        result["raw_ph"] = max(6.95, 7.35 - elapsed * 0.0015)
    if scenario == "naoh_feed_failure" and minute >= 480:
        result["naoh_available"] = False
    return result


def scenario_list() -> list[dict[str, object]]:
    return [definition.__dict__ for definition in SCENARIOS.values()]


def injection_list() -> list[dict[str, object]]:
    return [definition.__dict__ for definition in INJECTIONS.values()]
