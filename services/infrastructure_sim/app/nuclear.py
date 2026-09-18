from __future__ import annotations

from shared.exercise import ExerciseRecorder
from shared.operations import OperationsModel
from math import isfinite

from collections import deque
from datetime import datetime, timedelta, timezone
from math import exp
from threading import RLock

from .models import AiDecision, GateResult, LabSnapshot


NUCLEAR_SCENARIOS = [
    {"id": "normal_operation", "name": "Normal full-power operation", "description": "Stable PWR operation at rated electrical output."},
    {"id": "load_rejection", "name": "Turbine load rejection", "description": "The grid rejects generator output after minute 30."},
    {"id": "loss_feedwater", "name": "Loss of main feedwater", "description": "Main feedwater flow is lost after minute 20."},
    {"id": "coolant_pump_trip", "name": "Reactor coolant pump trip", "description": "The Loop B reactor coolant pump trips after minute 20."},
    {"id": "condenser_vacuum_loss", "name": "Condenser vacuum loss", "description": "Condenser heat rejection degrades after minute 30."},
    {"id": "pressurizer_sensor_bias", "name": "Pressurizer sensor bias", "description": "Reported primary pressure drifts below the process-model estimate."},
    {"id": "steam_generator_imbalance", "name": "Loop B feedwater restriction", "description": "One steam-generator feedwater path degrades after minute 20."},
    {"id": "thermal_dispatch_ramp", "name": "Industrial heat dispatch ramp", "description": "A bounded heat-transfer loop ramps to 240 MWth after minute 20."},
    {"id": "industrial_heat_rejection", "name": "Industrial heat-load rejection", "description": "A 240 MWth heat customer disconnects after minute 50."},
    {"id": "feedwater_pump_degradation", "name": "Feedwater pump degradation", "description": "Feedwater delivery efficiency declines after minute 20."},
]


class NuclearSimulator:
    """Reduced-order PWR operator-training model with independent protection logic."""

    def __init__(self) -> None:
        self.lock = RLock()
        self.reset()

    def reset(self, scenario: str = "normal_operation", speed: int = 10, mode: str = "advisory") -> None:
        with self.lock:
            self.operations = OperationsModel("nuclear")
            self.minute = 0
            self.simulation_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
            self.running = False
            self.speed = speed
            self.scenario = scenario if scenario in {item["id"] for item in NUCLEAR_SCENARIOS} else "normal_operation"
            self.controller_mode = mode
            self.loop_count = 3
            self.reactor_power_pct = 100.0
            self.thermal_power_mw = 3000.0
            self.primary_temperature_c = 315.0
            self.primary_pressure_mpa = 15.5
            self.pressurizer_level_pct = 52.0
            self.steam_generator_level_pct = 55.0
            self.steam_generator_pressure_mpa = 6.5
            self.steam_flow_kg_s = 1600.0
            self.feedwater_flow_kg_s = 1600.0
            self.condenser_pressure_kpa_abs = 8.0
            self.turbine_speed_rpm = 1800.0
            self.electric_output_mwe = 1000.0
            self.primary_coolant_flow_pct = 100.0
            self.containment_pressure_kpa_abs = 101.3
            self.radiation_monitor_usv_h = 0.12
            self.rcp_count = 3
            self.turbine_connected = True
            self.trip_minute: int | None = None
            self.first_out_trip = None
            self.decay_heat_mw = 0.0
            self.thermal_dispatch_mwth = 0.0
            self.heat_transfer_flow_kg_s = 0.0
            self.heat_transfer_supply_c = 285.0
            self.heat_transfer_return_c = 180.0
            self.condenser_hotwell_level_pct = 52.0
            self.deaerator_level_pct = 55.0
            self.feedwater_temperature_c = 225.0
            self.circulating_water_inlet_c = 20.0
            self.circulating_water_outlet_c = 30.0
            self.condenser_fouling_pct = 4.0
            self.feedwater_pump_efficiency_pct = 92.0
            self.rcp_bearing_health_pct = 96.0
            self.tuning = {
                "preset": "nominal",
                "thermal_response": 1.0,
                "pressure_response": 1.0,
                "inventory_response": 1.0,
                "condenser_response": 1.0,
            }
            self.loops = {
                name: {
                    "flow_pct": 100.0,
                    "hot_leg_c": 326.0 + bias,
                    "cold_leg_c": 290.0 + bias * 0.3,
                    "sg_level_pct": 55.0 + bias * 0.2,
                    "steam_flow_kg_s": 1600.0 / 3.0,
                    "feedwater_flow_kg_s": 1600.0 / 3.0,
                    "rcp_running": True,
                }
                for name, bias in (("A", -0.4), ("B", 0.0), ("C", 0.4))
            }
            self.controls: dict[str, float | bool | str] = {
                "control_rod_withdrawal_pct": 72.0,
                "boron_concentration_ppm": 850.0,
                "pressurizer_heater_pct": 30.0,
                "pressurizer_spray_valve_pct": 10.0,
                "main_feedwater_valve_pct": 55.0,
                "auxiliary_feedwater": False,
                "main_steam_valve_pct": 92.0,
                "turbine_load_target_mwe": 1000.0,
                "condenser_cooling_pct": 80.0,
                "thermal_dispatch_target_mwth": 0.0,
                "reactor_trip": False,
            }
            self.ai_lease = None
            self.ai_decision: AiDecision | None = None
            self.history = {
                "reactor_power_pct": deque([100.0], maxlen=120),
                "primary_pressure_mpa": deque([15.5], maxlen=120),
                "minimum_sg_level_pct": deque([55.0], maxlen=120),
                "electric_output_mwe": deque([1000.0], maxlen=120),
                "thermal_dispatch_mwth": deque([0.0], maxlen=120),
                "condenser_pressure_kpa_abs": deque([8.0], maxlen=120),
            }
            self.alarm_timeline: deque[dict] = deque(maxlen=80)
            self._active_alarm_codes: set[str] = set()

            self.exercise = ExerciseRecorder("nuclear", self.scenario)
            self.exercise.capture(self.snapshot(), self.minute)

    def set_tuning(self, request: dict[str, float | str]) -> None:
        with self.lock:
            preset = str(request.get("preset", "nominal"))
            profiles = {
                "nominal": (1.0, 1.0, 1.0, 1.0),
                "slow_thermal": (0.65, 0.9, 1.0, 0.9),
                "high_inertia": (0.55, 0.7, 0.75, 0.8),
                "degraded_heat_transfer": (1.15, 1.15, 0.9, 0.6),
            }
            if preset in profiles:
                thermal, pressure, inventory, condenser = profiles[preset]
            else:
                thermal = float(request.get("thermal_response", 1.0))
                pressure = float(request.get("pressure_response", 1.0))
                inventory = float(request.get("inventory_response", 1.0))
                condenser = float(request.get("condenser_response", 1.0))
                preset = "custom"
            self.tuning = {
                "preset": preset,
                "thermal_response": max(0.5, min(1.5, thermal)),
                "pressure_response": max(0.5, min(1.5, pressure)),
                "inventory_response": max(0.5, min(1.5, inventory)),
                "condenser_response": max(0.5, min(1.5, condenser)),
            }

    def command(self, action: str, minutes: int = 1, speed: int | None = None, scenario: str | None = None, mode: str | None = None) -> LabSnapshot:
        with self.lock:
            if action == "start":
                self.running = True
            elif action == "pause":
                self.running = False
            elif action == "reset":
                self.reset(scenario or self.scenario, speed or self.speed, mode or self.controller_mode)
            elif action == "step":
                self.running = False
                self.advance(minutes)
            elif action == "configure":
                if scenario is not None and scenario != self.scenario:
                    self.reset(scenario, speed or self.speed, mode or self.controller_mode)
                else:
                    if speed is not None:
                        self.speed = speed
                    if mode is not None:
                        if mode != self.controller_mode:
                            self._release_ai_lease()
                        self.controller_mode = mode
            self.exercise.event(self.minute, "command", action, speed=self.speed, mode=self.controller_mode)
            return self.snapshot()

    def advance(self, minutes: int = 1) -> None:
        with self.lock:
            for _ in range(minutes):
                self._step()
                self.operations.observe(self)
                self.exercise.capture(self.snapshot(), self.minute)

    def _scenario_state(self) -> dict[str, float | bool]:
        state: dict[str, float | bool] = {
            "main_feedwater_available": True,
            "rcp_count": 3,
            "condenser_effectiveness": 1.0,
            "turbine_connected": True,
            "pressure_sensor_bias": 0.0,
            "loop_b_flow_target_pct": 100.0,
            "loop_b_feedwater_factor": 1.0,
            "feedwater_pump_efficiency_target_pct": 92.0,
            "forced_thermal_dispatch_mwth": -1.0,
        }
        if self.scenario == "load_rejection" and self.minute >= 30:
            state["turbine_connected"] = False
        if self.scenario == "loss_feedwater" and self.minute >= 20:
            state["main_feedwater_available"] = False
        if self.scenario == "coolant_pump_trip" and self.minute >= 20:
            state["rcp_count"] = 2
            state["loop_b_flow_target_pct"] = 0.0
        if self.scenario == "condenser_vacuum_loss" and self.minute >= 30:
            state["condenser_effectiveness"] = 0.22
        if self.scenario == "pressurizer_sensor_bias" and self.minute >= 20:
            state["pressure_sensor_bias"] = max(-1.8, -(self.minute - 20) * 0.06)
        if self.scenario == "steam_generator_imbalance" and self.minute >= 20:
            state["loop_b_feedwater_factor"] = max(0.32, 1.0 - (self.minute - 20) * 0.025)
        if self.scenario == "thermal_dispatch_ramp" and self.minute >= 20:
            state["forced_thermal_dispatch_mwth"] = min(240.0, (self.minute - 20) * 12.0)
        if self.scenario == "industrial_heat_rejection":
            state["forced_thermal_dispatch_mwth"] = 240.0 if self.minute < 50 else 0.0
        if self.scenario == "feedwater_pump_degradation" and self.minute >= 20:
            state["feedwater_pump_efficiency_target_pct"] = max(48.0, 92.0 - (self.minute - 20) * 1.1)
        state["condenser_effectiveness"] *= max(.1, (self.operations.fraction("CW-301A")+self.operations.fraction("CW-301B"))/2) * (.7+.3*self.operations.fraction("CT-310"))
        if self.operations.active("hot_weather"):
            state["condenser_effectiveness"] *= .3
        if self.operations.active("regional_grid_disturbance") or self.operations.fraction("LP-401") < .25:
            state["turbine_connected"] = False
        return state

    def _protection_trip_required(self) -> bool:
        minimum_sg_level = min(loop["sg_level_pct"] for loop in self.loops.values())
        minimum_loop_flow = min(loop["flow_pct"] for loop in self.loops.values())
        return (
            self.primary_pressure_mpa > 16.2
            or self.primary_pressure_mpa < 13.2
            or self.primary_temperature_c > 327.0
            or minimum_sg_level < 18.0
            or minimum_loop_flow < 55.0
            or self.condenser_pressure_kpa_abs > 18.0
        )

    def _baseline_control(self, state: dict[str, float | bool]) -> None:
        minimum_sg_level = min(loop["sg_level_pct"] for loop in self.loops.values())
        if (self._protection_trip_required() or self.operations.active("regional_grid_disturbance")) and not bool(self.controls["reactor_trip"]):
            conditions = [
                (self.operations.active("regional_grid_disturbance"), "External grid disturbance: protective shutdown"),
                (self.primary_pressure_mpa > 16.2, "RCS high pressure"),
                (self.primary_pressure_mpa < 13.2, "RCS low pressure"),
                (self.primary_temperature_c > 327.0, "High primary temperature"),
                (minimum_sg_level < 18.0, "Low steam-generator inventory"),
                (min(loop["flow_pct"] for loop in self.loops.values()) < 55.0, "Low primary-loop flow"),
                (self.condenser_pressure_kpa_abs > 18.0, "Loss of condenser vacuum"),
            ]
            self.first_out_trip = {"minute": self.minute, "causes": [name for active, name in conditions if active]}
            self.exercise.event(self.minute, "protection", "Independent reactor trip", causes=self.first_out_trip["causes"])
            self.controls["reactor_trip"] = True
            self.trip_minute = self.minute
        if bool(self.controls["reactor_trip"]):
            self.controls["control_rod_withdrawal_pct"] = 0.0
            self.controls["main_steam_valve_pct"] = 20.0
            self.controls["main_feedwater_valve_pct"] = 0.0
            self.controls["auxiliary_feedwater"] = minimum_sg_level < 52.0
            return
        power_error = 100.0 - self.reactor_power_pct
        self.controls["control_rod_withdrawal_pct"] = max(25.0, min(78.0, float(self.controls["control_rod_withdrawal_pct"]) + power_error * 0.025))
        pressure_error = 15.5 - self.primary_pressure_mpa
        self.controls["pressurizer_heater_pct"] = max(0.0, min(100.0, 30.0 + pressure_error * 70.0))
        self.controls["pressurizer_spray_valve_pct"] = max(0.0, min(100.0, 10.0 - pressure_error * 65.0))
        level_error = 55.0 - minimum_sg_level
        self.controls["main_feedwater_valve_pct"] = max(15.0, min(100.0, 55.0 + level_error * 1.8))
        self.controls["auxiliary_feedwater"] = minimum_sg_level < 35.0
        if not bool(state["turbine_connected"]):
            self.controls["main_steam_valve_pct"] = max(8.0, float(self.controls["main_steam_valve_pct"]) - 28.0)
        forced_dispatch = float(state["forced_thermal_dispatch_mwth"])
        if forced_dispatch >= 0.0:
            self.controls["thermal_dispatch_target_mwth"] = forced_dispatch

    def _step(self) -> None:
        self.minute += 1
        if self.ai_lease and self.minute >= self.ai_lease["expires_minute"]:
            self._release_ai_lease()
        self.simulation_time += timedelta(minutes=1)
        self.operations.tick(self.minute, self.exercise)
        state = self._scenario_state()
        self.rcp_count = int(state["rcp_count"])
        self.turbine_connected = bool(state["turbine_connected"])
        self._baseline_control(state)

        tripped = bool(self.controls["reactor_trip"])
        rod_position = float(self.controls["control_rod_withdrawal_pct"])
        boron_penalty = max(-8.0, min(8.0, (850.0 - float(self.controls["boron_concentration_ppm"])) / 50.0))
        rod_target = max(0.0, min(105.0, (rod_position - 20.0) / 52.0 * 100.0 + boron_penalty))
        if tripped:
            elapsed_trip = max(0, self.minute - (self.trip_minute or self.minute))
            decay_floor = 1.2 + 5.3 * exp(-elapsed_trip / 90.0)
            self.decay_heat_mw = 30.0 * decay_floor
            self.reactor_power_pct = max(decay_floor, self.reactor_power_pct * 0.42)
        else:
            self.reactor_power_pct += (rod_target - self.reactor_power_pct) * 0.09
        self.thermal_power_mw = 30.0 * self.reactor_power_pct

        thermal_response = float(self.tuning["thermal_response"])
        pressure_response = float(self.tuning["pressure_response"])
        inventory_response = float(self.tuning["inventory_response"])
        condenser_response = float(self.tuning["condenser_response"])

        for name, loop in self.loops.items():
            flow_target = float(state["loop_b_flow_target_pct"]) if name == "B" else 100.0
            loop["flow_pct"] += (flow_target - loop["flow_pct"]) * 0.35
            loop["rcp_running"] = flow_target > 50.0
        self.primary_coolant_flow_pct = sum(loop["flow_pct"] for loop in self.loops.values()) / self.loop_count

        steam_valve = float(self.controls["main_steam_valve_pct"])
        available_steam = 1600.0 * self.reactor_power_pct / 100.0
        steam_header_target = available_steam * steam_valve / 92.0
        feedwater_available = 1.0 if bool(state["main_feedwater_available"]) else 0.0
        self.feedwater_pump_efficiency_pct += (float(state["feedwater_pump_efficiency_target_pct"]) - self.feedwater_pump_efficiency_pct) * 0.20
        main_feedwater = 1600.0 * float(self.controls["main_feedwater_valve_pct"]) / 55.0 * feedwater_available * self.feedwater_pump_efficiency_pct / 92.0
        main_feedwater *= min(1.0, self.operations.fraction("CP-201A")+self.operations.fraction("CP-201B"))
        auxiliary = 420.0 if bool(self.controls["auxiliary_feedwater"]) else 0.0
        for name, loop in self.loops.items():
            feed_factor = float(state["loop_b_feedwater_factor"]) if name == "B" else 1.0
            feed_target = main_feedwater / self.loop_count * feed_factor + auxiliary / self.loop_count
            loop["feedwater_flow_kg_s"] += (feed_target - loop["feedwater_flow_kg_s"]) * 0.28
            steam_target = steam_header_target / self.loop_count * max(0.22, loop["flow_pct"] / 100.0)
            loop["steam_flow_kg_s"] += (steam_target - loop["steam_flow_kg_s"]) * 0.18
            inventory_delta = (loop["feedwater_flow_kg_s"] - loop["steam_flow_kg_s"]) / 317.0 * inventory_response
            loop["sg_level_pct"] = max(0.0, min(100.0, loop["sg_level_pct"] + inventory_delta))
        self.feedwater_flow_kg_s = sum(loop["feedwater_flow_kg_s"] for loop in self.loops.values())
        self.steam_flow_kg_s = sum(loop["steam_flow_kg_s"] for loop in self.loops.values())
        self.steam_generator_level_pct = sum(loop["sg_level_pct"] for loop in self.loops.values()) / self.loop_count

        heat_removal_pct = max(0.0, min(115.0, self.steam_flow_kg_s / 16.0))
        minimum_loop_flow = min(loop["flow_pct"] for loop in self.loops.values())
        flow_penalty = max(0.0, 100.0 - minimum_loop_flow) * 0.018
        self.primary_temperature_c += ((self.reactor_power_pct - heat_removal_pct) * 0.018 + flow_penalty + (315.0 - self.primary_temperature_c) * 0.015) * thermal_response
        for index, loop in enumerate(self.loops.values()):
            bias = (index - 1) * 0.45
            loop["hot_leg_c"] += ((self.primary_temperature_c + 11.0 + bias) - loop["hot_leg_c"]) * 0.22 * thermal_response
            cold_target = self.primary_temperature_c - 25.0 + max(0.0, 100.0 - loop["flow_pct"]) * 0.08 + bias * 0.3
            loop["cold_leg_c"] += (cold_target - loop["cold_leg_c"]) * 0.20 * thermal_response
        pressure_target = 15.5 + (self.primary_temperature_c - 315.0) * 0.035
        pressure_target += float(self.controls["pressurizer_heater_pct"]) * 0.0015
        pressure_target -= float(self.controls["pressurizer_spray_valve_pct"]) * 0.0022
        self.primary_pressure_mpa += (pressure_target - self.primary_pressure_mpa) * 0.22 * pressure_response
        self.pressurizer_level_pct += ((52.0 + (self.primary_temperature_c - 315.0) * 0.8) - self.pressurizer_level_pct) * 0.14 * inventory_response
        self.steam_generator_pressure_mpa += ((6.5 * self.reactor_power_pct / 100.0 + 0.3) - self.steam_generator_pressure_mpa) * 0.12

        dispatch_target = 0.0 if tripped else max(0.0, min(300.0, float(self.controls["thermal_dispatch_target_mwth"])))
        dispatch_target *= self.operations.fraction("HX-501")
        self.thermal_dispatch_mwth += (dispatch_target - self.thermal_dispatch_mwth) * 0.16 * thermal_response
        self.heat_transfer_flow_kg_s = self.thermal_dispatch_mwth / 0.42
        self.heat_transfer_supply_c = 180.0 + self.thermal_dispatch_mwth / max(self.heat_transfer_flow_kg_s, 1.0) / 0.0042
        self.heat_transfer_return_c += (180.0 - self.heat_transfer_return_c) * 0.12
        extracted_steam_kg_s = self.thermal_dispatch_mwth / 2.05
        turbine_steam_kg_s = max(0.0, self.steam_flow_kg_s - extracted_steam_kg_s)
        cooling = float(self.controls["condenser_cooling_pct"]) / 80.0 * float(state["condenser_effectiveness"])
        condenser_target = 5.5 + turbine_steam_kg_s / 650.0 / max(cooling, 0.15) + self.condenser_fouling_pct * 0.025
        condenser_target += 4.0*(1-self.operations.fraction("VP-321"))
        self.condenser_pressure_kpa_abs += (condenser_target - self.condenser_pressure_kpa_abs) * 0.20 * condenser_response
        available_electric = turbine_steam_kg_s / 1.6
        target_electric = float(self.controls["turbine_load_target_mwe"])
        if self.turbine_connected and not tripped:
            self.electric_output_mwe += (min(available_electric, target_electric) - self.electric_output_mwe) * 0.22
            self.turbine_speed_rpm += (1800.0 - self.turbine_speed_rpm) * 0.4
        else:
            self.electric_output_mwe *= 0.35
            self.turbine_speed_rpm += (0.0 - self.turbine_speed_rpm) * 0.18

        self.condenser_hotwell_level_pct = max(10.0, min(90.0, self.condenser_hotwell_level_pct + (self.steam_flow_kg_s - self.feedwater_flow_kg_s) / 1500.0))
        self.deaerator_level_pct += (self.condenser_hotwell_level_pct + 3.0 - self.deaerator_level_pct) * 0.10 * inventory_response
        self.feedwater_temperature_c += ((210.0 + self.reactor_power_pct * 0.15) - self.feedwater_temperature_c) * 0.08 * thermal_response
        self.circulating_water_outlet_c = self.circulating_water_inlet_c + 10.0 * max(0.1, self.reactor_power_pct / 100.0) / max(cooling, 0.25)
        fouling_rate = 0.0008 + (0.018 if self.scenario == "condenser_vacuum_loss" and self.minute >= 30 else 0.0)
        self.condenser_fouling_pct = min(45.0, self.condenser_fouling_pct + fouling_rate)
        self.rcp_bearing_health_pct = max(0.0, self.rcp_bearing_health_pct - 0.0005 * self.primary_coolant_flow_pct)

        self.history["reactor_power_pct"].append(round(self.reactor_power_pct, 3))
        self.history["primary_pressure_mpa"].append(round(self.primary_pressure_mpa, 4))
        self.history["minimum_sg_level_pct"].append(round(min(loop["sg_level_pct"] for loop in self.loops.values()), 3))
        self.history["electric_output_mwe"].append(round(self.electric_output_mwe, 3))
        self.history["thermal_dispatch_mwth"].append(round(self.thermal_dispatch_mwth, 3))
        self.history["condenser_pressure_kpa_abs"].append(round(self.condenser_pressure_kpa_abs, 3))
        self._record_alarm_changes()



    def _record_alarm_changes(self) -> None:
        current = {alarm["code"] for alarm in self._alarms()}
        for code in sorted(current - self._active_alarm_codes):
            alarm = next(item for item in self._alarms() if item["code"] == code)
            self.alarm_timeline.appendleft({"simulation_time": self.simulation_time.isoformat(), "event": "entered", **alarm})
        for code in sorted(self._active_alarm_codes - current):
            self.alarm_timeline.appendleft({"simulation_time": self.simulation_time.isoformat(), "event": "cleared", "code": code, "severity": "normal", "message": "Condition returned inside the illustrative band", "system": "plant"})
        self._active_alarm_codes = current

    def _alarms(self) -> list[dict[str, str]]:
        alarms: list[dict[str, str]] = self.operations.alarms()
        minimum_sg_level = min(loop["sg_level_pct"] for loop in self.loops.values())
        maximum_sg_level = max(loop["sg_level_pct"] for loop in self.loops.values())
        minimum_loop_flow = min(loop["flow_pct"] for loop in self.loops.values())
        checks = [
            (self.primary_pressure_mpa > 16.0 or self.primary_pressure_mpa < 13.5, "RCS_PRESSURE", "Primary coolant pressure is outside its illustrative operating band", "critical", "primary"),
            (self.primary_temperature_c > 325.0, "RCS_TEMPERATURE", "Primary coolant temperature is high", "critical", "primary"),
            (minimum_sg_level < 30.0, "SG_LEVEL_LOW", "At least one steam-generator water level is low", "critical", "secondary"),
            (maximum_sg_level > 80.0, "SG_LEVEL_HIGH", "At least one steam-generator water level is high", "warning", "secondary"),
            (minimum_loop_flow < 85.0, "RCP_FLOW_LOW", "At least one primary-loop coolant flow is reduced", "warning", "primary"),
            (self.condenser_pressure_kpa_abs > 14.0, "CONDENSER_VACUUM", "Condenser backpressure is high", "critical", "secondary"),
            (self.feedwater_pump_efficiency_pct < 70.0, "FEEDWATER_PUMP_DEGRADED", "Main feedwater pump delivery efficiency is degraded", "warning", "secondary"),
            (not self.turbine_connected, "GENERATOR_DISCONNECTED", "Generator is disconnected from the grid", "warning", "electrical"),
            (bool(self.controls["reactor_trip"]), "REACTOR_TRIP", "Independent reactor protection has tripped the reactor", "critical", "protection"),
        ]
        for active, code, message, severity, system in checks:
            if active:
                alarms.append({"code": code, "message": message, "severity": severity, "system": system})
        if self.scenario == "pressurizer_sensor_bias" and self.minute >= 20:
            alarms.append({"code": "PRESSURE_MODEL_MISMATCH", "message": "Reported pressurizer pressure conflicts with the process-model estimate", "severity": "critical", "system": "instrumentation"})
        return alarms

    def _procedures(self) -> list[dict]:
        active_codes = {alarm["code"] for alarm in self._alarms()}
        protection_active = bool(self.controls["reactor_trip"])
        return [
            {
                "id": "CP-01",
                "title": "Independent protection status",
                "status": "active" if protection_active else "verified",
                "reason": "Reactor protection has priority over every supervisory request.",
                "steps": [
                    "Confirm the simulated protection state and trip indication.",
                    "Keep the AI layer outside rods, protection and engineered safety functions.",
                    "Record the initiating alarm and the simulated response.",
                ],
            },
            {
                "id": "CP-02",
                "title": "Secondary heat-sink check",
                "status": "active" if active_codes & {"SG_LEVEL_LOW", "FEEDWATER_PUMP_DEGRADED", "CONDENSER_VACUUM"} else "monitor",
                "reason": "Steam-generator inventory and condenser performance provide the simulated heat sink.",
                "steps": [
                    "Compare all three steam-generator levels and feedwater flows.",
                    "Confirm auxiliary feedwater state after a low-level condition.",
                    "Hold thermal dispatch if any steam-generator level is below the gate threshold.",
                ],
            },
            {
                "id": "CP-03",
                "title": "Instrument confidence check",
                "status": "active" if "PRESSURE_MODEL_MISMATCH" in active_codes else "monitor",
                "reason": "Model comparison can flag a biased measurement before supervisory use.",
                "steps": [
                    "Compare reported pressure with the independent model estimate.",
                    "Treat a mismatched channel as unavailable to the AI supervisor.",
                    "Continue with deterministic control and log the discrepancy.",
                ],
            },
            {
                "id": "CP-04",
                "title": "Coupled heat dispatch check",
                "status": "active" if self.thermal_dispatch_mwth > 10 else "available",
                "reason": "Industrial heat extraction changes turbine steam and electrical output.",
                "steps": [
                    "Confirm the heat-transfer target is inside the demonstration envelope.",
                    "Check steam-generator level, condenser pressure and generator response.",
                    "Return dispatch to zero if the safety gate rejects the next interval.",
                ],
            },
        ]

    def _model_health(self) -> dict:
        minimum_level = min(loop["sg_level_pct"] for loop in self.loops.values())
        maximum_level = max(loop["sg_level_pct"] for loop in self.loops.values())
        expected_steam = max(1.0, 1600.0 * self.reactor_power_pct / 100.0)
        steam_closure = abs(self.steam_flow_kg_s - expected_steam) / expected_steam * 100.0
        inventory_closure = abs(self.feedwater_flow_kg_s - self.steam_flow_kg_s) / max(self.steam_flow_kg_s, 1.0) * 100.0
        pressure_margin = min(self.primary_pressure_mpa - 13.2, 16.2 - self.primary_pressure_mpa)
        return {
            "status": "attention" if steam_closure > 12.0 or inventory_closure > 15.0 else "healthy",
            "steam_balance_error_pct": round(steam_closure, 2),
            "secondary_mass_imbalance_pct": round(inventory_closure, 2),
            "steam_generator_level_spread_pct": round(maximum_level - minimum_level, 2),
            "primary_pressure_trip_margin_mpa": round(max(0.0, pressure_margin), 3),
            "condenser_fouling_pct": round(self.condenser_fouling_pct, 2),
            "feedwater_pump_efficiency_pct": round(self.feedwater_pump_efficiency_pct, 2),
            "rcp_bearing_health_pct": round(self.rcp_bearing_health_pct, 2),
            "fidelity": "reduced-order software-in-the-loop",
        }

    def _gate(self, changes: dict[str, float | bool]) -> GateResult:
        reasons: list[str] = []
        alarms = self._alarms()
        if any(alarm["severity"] == "critical" for alarm in alarms):
            reasons.append("Plant is in a critical state")
        allowed = {
            "turbine_load_target_mwe": (300.0, 1050.0, 80.0),
            "condenser_cooling_pct": (50.0, 100.0, 10.0),
            "thermal_dispatch_target_mwth": (0.0, 300.0, 50.0),
        }
        for name, value in changes.items():
            if name not in allowed:
                reasons.append(f"AI is not authorized to change {name}")
                continue
            low, high, maximum_step = allowed[name]
            if not low <= float(value) <= high:
                reasons.append(f"{name} is outside the permitted demonstration range")
            if abs(float(value) - float(self.controls[name])) > maximum_step:
                reasons.append(f"{name} exceeds the permitted decision step")
        if bool(self.controls["reactor_trip"]):
            reasons.append("Reactor protection is active")
        proposed_dispatch = float(changes.get("thermal_dispatch_target_mwth", self.controls["thermal_dispatch_target_mwth"]))
        if proposed_dispatch > 0 and min(loop["sg_level_pct"] for loop in self.loops.values()) < 45.0:
            reasons.append("Thermal dispatch is blocked while a steam-generator level is below 45 percent")
        return GateResult(status="rejected" if reasons else "accepted", reasons=reasons)

    def run_ai_cycle(self) -> AiDecision:
        proposed_cooling = min(100.0, max(55.0, float(self.controls["condenser_cooling_pct"]) + (self.condenser_pressure_kpa_abs - 8.0) * 2.5))
        proposed_load = min(1000.0, max(300.0, self.electric_output_mwe + (1000.0 - self.electric_output_mwe) * 0.25))
        proposed_dispatch = min(300.0, max(0.0, float(self.controls["thermal_dispatch_target_mwth"])))
        changes = {"turbine_load_target_mwe": round(proposed_load, 1), "condenser_cooling_pct": round(proposed_cooling, 1), "thermal_dispatch_target_mwth": round(proposed_dispatch, 1)}
        return self.apply_ai_proposal(
            changes,
            confidence=0.84 if not self._alarms() else 0.48,
            objective="Coordinate electric output, industrial heat dispatch and condenser performance",
            explanation="The fallback policy coordinates non-safety energy delivery. Reactor protection remains independent.",
            source="deterministic fallback policy",
        )

    def apply_ai_proposal(
        self,
        changes: dict[str, float],
        confidence: float,
        objective: str,
        explanation: str,
        source: str = "ollama",
    ) -> AiDecision:
        with self.lock:
            gate = self._gate(changes)
            if gate.status == "accepted" and (not isfinite(confidence) or not 0.55 <= confidence <= 1.0):
                gate.status = "rejected"
                gate.reasons.append("AI confidence is below the 0.55 acceptance threshold")
            if gate.status == "accepted" and self.controller_mode in {"baseline", "advisory"}:
                gate.status = "advisory"
            elif gate.status == "accepted" and self.controller_mode == "shadow":
                gate.status = "shadow"
            elif gate.status == "accepted" and self.controller_mode == "gated_auto":
                self._release_ai_lease()
                self.ai_lease = {"expires_minute": self.minute+5, "previous": {name:self.controls[name] for name in changes}, "applied": changes.copy()}
                for name, value in changes.items():
                    self.controls[name] = value
                gate.applied = changes.copy()
            decision = AiDecision(
                objective=objective,
                changes=changes,
                confidence=confidence,
                explanation=explanation,
                gate=gate,
                source=source,
            )
            self.ai_decision = decision
            self.exercise.event(self.minute, "ai_decision", gate.status, source=source, changes=changes, reasons=gate.reasons)
            return decision

    def _release_ai_lease(self):
        if not self.ai_lease:
            return
        for name, previous in self.ai_lease["previous"].items():
            if self.controls[name] == self.ai_lease["applied"].get(name):
                self.controls[name] = previous
        self.exercise.event(self.minute, "ai_lease_ended", "Supervisory lease released; baseline targets restored where unchanged")
        self.ai_lease = None

    def manual(self, changes: dict[str, float | bool]) -> GateResult:
        with self.lock:
            gate = self._gate(changes)
            if gate.status == "accepted":
                for name, value in changes.items():
                    self.controls[name] = value
                gate.applied = changes.copy()
            if gate.status == "accepted" and self.ai_lease:
                for name in changes:
                    self.ai_lease["previous"].pop(name, None)
            self.exercise.event(self.minute, "manual", gate.status, changes=changes, reasons=gate.reasons)
            return gate

    def snapshot(self) -> LabSnapshot:
        with self.lock:
            state = self._scenario_state()
            reported_pressure = self.primary_pressure_mpa + float(state["pressure_sensor_bias"])
            alarms = self._alarms()
            safety = "critical" if any(item["severity"] == "critical" for item in alarms) else "warning" if alarms else "normal"

            def sensor(value: float, unit: str, quality: str = "good") -> dict[str, float | str]:
                return {"value": round(value, 3), "unit": unit, "quality": quality}

            sensors = {
                "decay_heat_mw": sensor(self.decay_heat_mw, "MWth"),
                "reactor_power_pct": sensor(self.reactor_power_pct, "%"),
                "thermal_power_mw": sensor(self.thermal_power_mw, "MWth"),
                "primary_temperature_c": sensor(self.primary_temperature_c, "degC"),
                "primary_pressure_mpa": sensor(reported_pressure, "MPa"),
                "primary_pressure_model_mpa": sensor(self.primary_pressure_mpa, "MPa"),
                "pressurizer_level_pct": sensor(self.pressurizer_level_pct, "%"),
                "primary_coolant_flow_pct": sensor(self.primary_coolant_flow_pct, "%"),
                "steam_generator_level_pct": sensor(self.steam_generator_level_pct, "%"),
                "steam_generator_pressure_mpa": sensor(self.steam_generator_pressure_mpa, "MPa"),
                "steam_flow_kg_s": sensor(self.steam_flow_kg_s, "kg/s"),
                "feedwater_flow_kg_s": sensor(self.feedwater_flow_kg_s, "kg/s"),
                "condenser_pressure_kpa_abs": sensor(self.condenser_pressure_kpa_abs, "kPa abs"),
                "turbine_speed_rpm": sensor(self.turbine_speed_rpm, "rpm"),
                "electric_output_mwe": sensor(self.electric_output_mwe, "MWe"),
                "thermal_dispatch_mwth": sensor(self.thermal_dispatch_mwth, "MWth"),
                "heat_transfer_flow_kg_s": sensor(self.heat_transfer_flow_kg_s, "kg/s"),
                "heat_transfer_supply_c": sensor(self.heat_transfer_supply_c, "degC"),
                "heat_transfer_return_c": sensor(self.heat_transfer_return_c, "degC"),
                "condenser_hotwell_level_pct": sensor(self.condenser_hotwell_level_pct, "%"),
                "deaerator_level_pct": sensor(self.deaerator_level_pct, "%"),
                "feedwater_temperature_c": sensor(self.feedwater_temperature_c, "degC"),
                "circulating_water_inlet_c": sensor(self.circulating_water_inlet_c, "degC"),
                "circulating_water_outlet_c": sensor(self.circulating_water_outlet_c, "degC"),
                "containment_pressure_kpa_abs": sensor(self.containment_pressure_kpa_abs, "kPa abs"),
                "radiation_monitor_usv_h": sensor(self.radiation_monitor_usv_h, "uSv/h"),
            }
            for name, loop in self.loops.items():
                prefix = f"loop_{name.lower()}"
                sensors[f"{prefix}_flow_pct"] = sensor(loop["flow_pct"], "%")
                sensors[f"{prefix}_hot_leg_c"] = sensor(loop["hot_leg_c"], "degC")
                sensors[f"{prefix}_cold_leg_c"] = sensor(loop["cold_leg_c"], "degC")
                sensors[f"{prefix}_sg_level_pct"] = sensor(loop["sg_level_pct"], "%")
                sensors[f"{prefix}_steam_flow_kg_s"] = sensor(loop["steam_flow_kg_s"], "kg/s")
                sensors[f"{prefix}_feedwater_flow_kg_s"] = sensor(loop["feedwater_flow_kg_s"], "kg/s")
            sensors.update({"aux_"+tag.lower().replace("-", "_")+"_feedback_pct": sensor(d["feedback_pct"], "%") for tag,d in self.operations.devices.items()})
            equipment = {
                "reactor_coolant_pumps": {"running": self.rcp_count, "total": 3},
                "primary_loops": {
                    name: {
                        "rcp_running": bool(loop["rcp_running"]),
                        "flow_pct": round(loop["flow_pct"], 2),
                        "steam_generator_level_pct": round(loop["sg_level_pct"], 2),
                        "hot_leg_c": round(loop["hot_leg_c"], 2),
                        "cold_leg_c": round(loop["cold_leg_c"], 2),
                    }
                    for name, loop in self.loops.items()
                },
                "turbine_generator": {"connected": self.turbine_connected, "speed_rpm": round(self.turbine_speed_rpm, 1)},
                "reactor_protection": {"trip": bool(self.controls["reactor_trip"]), "independent_of_ai": True, "first_out": self.first_out_trip},
                "auxiliary_feedwater": {"running": bool(self.controls["auxiliary_feedwater"])},
                "thermal_dispatch_skid": {"connected": self.thermal_dispatch_mwth > 1.0, "duty_mwth": round(self.thermal_dispatch_mwth, 2), "bounded_capacity_mwth": 300.0},
                "condition_monitoring": {
                    "condenser_fouling_pct": round(self.condenser_fouling_pct, 2),
                    "feedwater_pump_efficiency_pct": round(self.feedwater_pump_efficiency_pct, 2),
                    "rcp_bearing_health_pct": round(self.rcp_bearing_health_pct, 2),
                },
            }
            flows = [
                {"source": "Reactor vessel", "target": f"Steam generator {name}", "medium": f"Primary coolant loop {name}", "value": round(loop["flow_pct"], 1), "unit": "% flow", "status": "warning" if loop["flow_pct"] < 85 else "normal"}
                for name, loop in self.loops.items()
            ] + [
                {"source": "Steam generator", "target": "Turbine", "medium": "Secondary steam", "value": round(self.steam_flow_kg_s, 1), "unit": "kg/s", "status": "normal" if self.steam_flow_kg_s > 800 else "warning"},
                {"source": "Steam header", "target": "Industrial heat exchanger", "medium": "Dispatched thermal energy", "value": round(self.thermal_dispatch_mwth, 1), "unit": "MWth", "status": "normal"},
                {"source": "Turbine", "target": "Condenser", "medium": "Exhaust steam", "value": round(self.steam_flow_kg_s, 1), "unit": "kg/s", "status": "critical" if self.condenser_pressure_kpa_abs > 14 else "normal"},
                {"source": "Condenser", "target": "Steam generator", "medium": "Feedwater", "value": round(self.feedwater_flow_kg_s, 1), "unit": "kg/s", "status": "critical" if self.feedwater_flow_kg_s < 600 else "normal"},
            ]
            return LabSnapshot(
                domain="nuclear",
                simulation_time=self.simulation_time.isoformat(),
                elapsed_minutes=self.minute,
                running=self.running,
                speed=self.speed,
                scenario=self.scenario,
                controller_mode=self.controller_mode,
                safety_state=safety,
                alarms=alarms,
                sensors=sensors,
                controls=self.controls.copy(),
                equipment=equipment,
                operations=self.operations.snapshot(self),
                flows=flows,
                ai_decision=self.ai_decision,
                input_channels=[
                    {"name": "Control rod position", "type": "reactivity control", "authority": "automatic reactor control and protection"},
                    {"name": "Boron concentration", "type": "slow reactivity control", "authority": "operator procedure"},
                    {"name": "Pressurizer heaters and spray", "type": "primary pressure control", "authority": "deterministic controller"},
                    {"name": "Feedwater and steam valves", "type": "secondary heat removal", "authority": "deterministic controller"},
                    {"name": "Turbine load, condenser cooling and heat dispatch", "type": "balance-of-plant optimization", "authority": "AI eligible inside gate"},
                    {"name": "Reactor trip and auxiliary feedwater", "type": "safety protection", "authority": "independent protection only"},
                ],
                output_channels=[
                    {"name": "Neutron and thermal power", "type": "reactor state", "authority": "monitored"},
                    {"name": "Primary temperature, pressure and flow", "type": "cooling margin", "authority": "monitored"},
                    {"name": "Steam-generator level and pressure", "type": "heat sink", "authority": "monitored"},
                    {"name": "Steam flow and condenser pressure", "type": "secondary cycle", "authority": "monitored"},
                    {"name": "Loop A, B and C temperatures, flows and levels", "type": "loop balance", "authority": "monitored"},
                    {"name": "Thermal dispatch flow and temperatures", "type": "coupled industrial heat", "authority": "monitored"},
                    {"name": "Turbine speed and electrical output", "type": "generation", "authority": "monitored"},
                    {"name": "Containment pressure and radiation", "type": "defence in depth", "authority": "monitored"},
                ],
                history={name: list(values) for name, values in self.history.items()},
                procedures=self._procedures(),
                model_health=self._model_health(),
                tuning=self.tuning.copy(),
                alarm_timeline=list(self.alarm_timeline),
                note="Public-capability-inspired, generic three-loop PWR software-in-the-loop model. It includes balance-of-plant and coupled heat-dispatch behavior for research demonstrations. It is not RELAP5-3D, a licensed engineering model, or an operator certification simulator.",
            )
