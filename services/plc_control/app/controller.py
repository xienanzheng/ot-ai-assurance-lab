from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import copysign, isfinite, sqrt

from shared.chemistry import required_naoh_dose
from shared.limits import LIMITS, MAX_SETPOINT_STEP, SETPOINT_LIMITS
from shared.models import ActuatorCommand, ControlProposal, GateDecision, PlantSnapshot, SetpointChanges

from .control_blocks import BackwashPhase, BackwashSequencer, EquipmentRuntime, OnDelayTimer, PIController, clamp


@dataclass
class ControllerSetpoints:
    clearwell_target_pct: float = 65.0
    elevated_tank_target_pct: float = 68.0
    pressure_target_m: float = 44.0
    chlorine_target_mg_l: float = 1.15
    coagulant_target_mg_l: float = 22.0
    finished_water_ph_target: float = 7.35
    intake_gate_target_pct: float = 95.0
    filter_outlet_valve_target_pct: float = 95.0
    zone_1_isolation_target_pct: float = 100.0
    zone_2_isolation_target_pct: float = 100.0
    zone_3_isolation_target_pct: float = 100.0


class BaselineController:
    """Stateful PLC-style controller for the simulated treatment and distribution train."""

    TRIP_REASONS = {
        "INTAKE_DEADHEAD": "Intake pump discharge pressure or closed-path feedback indicates deadhead risk",
        "HIGH_LIFT_LOW_SUCTION": "Clearwell level is below the high-lift pump suction protection point",
        "CHLORINE_FEED_DEVIATION": "Delivered chlorine dose does not agree with the PLC command",
    }

    def __init__(self) -> None:
        self.setpoints = ControllerSetpoints()
        self.last_command = ActuatorCommand(
            intake_pump_speed_pct=72.0,
            high_lift_pump_speed_pct=70.0,
            booster_pump_speed_pct=54.0,
            outlet_valve_pct=82.0,
            intake_gate_pct=95.0,
            filter_outlet_valve_pct=95.0,
            zone_1_isolation_valve_pct=100.0,
            zone_2_isolation_valve_pct=100.0,
            zone_3_isolation_valve_pct=100.0,
            pressure_reducing_valve_setpoint_m=52.0,
            coagulant_dose_mg_l=22.0,
            chlorine_dose_mg_l=1.45,
            naoh_dose_mg_l=8.0,
            backwash_request=False,
            emergency_stop=False,
        )
        self.supervisory_expiry: datetime | None = None
        self.supervisory_previous: dict[str, float] = {}
        self.last_cycle_time: datetime | None = None
        self.control_source = "baseline"
        self.loops = {
            "clearwell_level": PIController("Clearwell level", 1.35, 0.055, 25.0, 98.0, 10.0, last_output=72.0),
            "distribution_pressure": PIController("Distribution pressure", 1.15, 0.09, 30.0, 100.0, 10.0, last_output=70.0),
            "elevated_tank": PIController("Elevated tank", 0.72, 0.035, 35.0, 90.0, 8.0, last_output=54.0),
            "chlorine_residual": PIController("Chlorine residual", 0.78, 0.025, 0.0, 5.0, 0.35, last_output=1.45),
            "finished_water_ph": PIController("Finished-water pH", 2.5, 0.08, 0.0, 25.0, 2.0, last_output=8.0),
        }
        self.runtimes = {
            "intake_pump": EquipmentRuntime(running=True),
            "high_lift_pump": EquipmentRuntime(running=True),
            "booster_pump": EquipmentRuntime(running=True),
        }
        self.booster_start_delay = OnDelayTimer(2.0)
        self.booster_stop_delay = OnDelayTimer(8.0)
        self.backwash = BackwashSequencer()
        self.trip_latches = {code: False for code in self.TRIP_REASONS}
        self.trip_first_out: dict[str, str] = {}
        self.permissives: dict[str, dict[str, object]] = {}
        self.loop_status: dict[str, dict[str, object]] = {}
        self.sensor_selection: dict[str, object] = {}

    @staticmethod
    def _bounded(value: float, low: float, high: float) -> float:
        return clamp(value, low, high)

    def _slew(self, field: str, target: float, maximum_step: float = 12.0) -> float:
        previous = getattr(self.last_command, field, None)
        if previous is None:
            return target
        return self._bounded(target, float(previous) - maximum_step, float(previous) + maximum_step)

    @staticmethod
    def _sensor(snapshot: PlantSnapshot, name: str, default: float = 0.0) -> float:
        sensor = snapshot.sensors.get(name)
        return sensor.value if sensor is not None else default

    @staticmethod
    def _quality_ok(snapshot: PlantSnapshot, names: list[str]) -> bool:
        return all(name in snapshot.sensors and snapshot.sensors[name].quality == "good" for name in names)

    def _cycle_minutes(self, now: datetime) -> float:
        if self.last_cycle_time is None:
            self.last_cycle_time = now
            return 1.0
        if now < self.last_cycle_time:
            self.reset_dynamic_state()
            self.last_cycle_time = now
            return 1.0
        if now == self.last_cycle_time:
            return 0.1
        elapsed = (now - self.last_cycle_time).total_seconds() / 60.0
        self.last_cycle_time = now
        return clamp(elapsed, 0.1, 10.0)

    def reset_dynamic_state(self) -> None:
        outputs = {
            "clearwell_level": 72.0,
            "distribution_pressure": 70.0,
            "elevated_tank": 54.0,
            "chlorine_residual": 1.45,
            "finished_water_ph": 8.0,
        }
        for name, loop in self.loops.items():
            loop.reset(outputs[name])
        self.runtimes = {
            "intake_pump": EquipmentRuntime(running=True),
            "high_lift_pump": EquipmentRuntime(running=True),
            "booster_pump": EquipmentRuntime(running=True),
        }
        self.booster_start_delay.reset()
        self.booster_stop_delay.reset()
        self.backwash.reset()
        self.trip_latches = {code: False for code in self.TRIP_REASONS}
        self.trip_first_out = {}
        self.permissives = {}
        self.loop_status = {}
        self.sensor_selection = {}

    def _latch_trip(self, code: str, now: datetime) -> None:
        if not self.trip_latches[code]:
            self.trip_first_out[code] = now.isoformat()
        self.trip_latches[code] = True

    def _update_trips(self, snapshot: PlantSnapshot) -> None:
        deadhead = self._sensor(snapshot, "pump_deadhead_pressure_kpa") >= 160.0
        closed_running_path = (
            self._sensor(snapshot, "filter_outlet_valve_position_pct", 100.0) < 5.0
            and self._sensor(snapshot, "raw_flow_m3h") < 25.0
            and float(self.last_command.intake_pump_speed_pct or 0.0) > 20.0
        )
        if deadhead or closed_running_path:
            self._latch_trip("INTAKE_DEADHEAD", snapshot.simulation_time)

        conservative_clearwell = min(
            self._sensor(snapshot, "clearwell_level_pct", 100.0),
            self._sensor(snapshot, "clearwell_level_model_pct", 100.0),
        )
        if conservative_clearwell < 15.0:
            self._latch_trip("HIGH_LIFT_LOW_SUCTION", snapshot.simulation_time)

        actual_chlorine = self._sensor(snapshot, "chlorine_dose_actual_mg_l")
        commanded_chlorine = float(snapshot.actuators.get("chlorine_dose_mg_l", 0.0))
        if actual_chlorine > 4.0 or actual_chlorine - commanded_chlorine > 1.0:
            self._latch_trip("CHLORINE_FEED_DEVIATION", snapshot.simulation_time)

    def reset_trips(self, snapshot: PlantSnapshot) -> dict[str, list[str]]:
        reset_codes: list[str] = []
        blocked_codes: list[str] = []
        reset_ready = {
            "INTAKE_DEADHEAD": (
                self._sensor(snapshot, "pump_deadhead_pressure_kpa") < 25.0
                and self._sensor(snapshot, "filter_outlet_valve_position_pct", 0.0) > 30.0
            ),
            "HIGH_LIFT_LOW_SUCTION": min(
                self._sensor(snapshot, "clearwell_level_pct"),
                self._sensor(snapshot, "clearwell_level_model_pct"),
            ) > 30.0,
            "CHLORINE_FEED_DEVIATION": (
                self._sensor(snapshot, "chlorine_dose_actual_mg_l") <= 4.0
                and abs(
                    self._sensor(snapshot, "chlorine_dose_actual_mg_l")
                    - float(snapshot.actuators.get("chlorine_dose_mg_l", 0.0))
                ) <= 0.5
            ),
        }
        for code, latched in self.trip_latches.items():
            if not latched:
                continue
            if reset_ready[code]:
                self.trip_latches[code] = False
                self.trip_first_out.pop(code, None)
                reset_codes.append(code)
            else:
                blocked_codes.append(code)
        return {"reset": reset_codes, "blocked": blocked_codes}

    def _build_permissives(self, snapshot: PlantSnapshot) -> dict[str, bool]:
        clearwell_reported = self._sensor(snapshot, "clearwell_level_pct")
        clearwell_model = self._sensor(snapshot, "clearwell_level_model_pct", clearwell_reported)
        fill_protection_level = max(clearwell_reported, clearwell_model)
        draw_protection_level = min(clearwell_reported, clearwell_model)
        intake_gate_open = self._sensor(snapshot, "intake_gate_position_pct", 100.0) >= 20.0
        filter_path_open = self._sensor(snapshot, "filter_outlet_valve_position_pct", 100.0) >= 20.0
        one_zone_open = any(self._sensor(snapshot, f"zone_{index}_isolation_valve_position_pct", 100.0) >= 35.0 for index in range(1, 4))
        process_quality_ok = self._quality_ok(
            snapshot,
            [
                "clearwell_level_pct",
                "clearwell_level_model_pct",
                "filter_outlet_valve_position_pct",
                "zone_1_pressure_m",
                "zone_2_pressure_m",
                "zone_3_pressure_m",
            ],
        )
        raw_flow_ok = self._sensor(snapshot, "raw_flow_m3h") >= 25.0
        chemical_levels_ok = all(self._sensor(snapshot, f"{name}_day_tank_level_pct", 100.0) >= 10.0 for name in ("alum", "naoh", "hypochlorite"))

        values = {
            "intake_path": intake_gate_open and filter_path_open,
            "clearwell_not_high_high": fill_protection_level < 95.0,
            "high_lift_suction": draw_protection_level > 22.0,
            "distribution_path": one_zone_open,
            "control_sensor_quality": process_quality_ok,
            "chemical_flow_proof": raw_flow_ok,
            "chemical_inventory": chemical_levels_ok,
            "no_emergency_stop": not snapshot.emergency_stop,
            "intake_trip_clear": not self.trip_latches["INTAKE_DEADHEAD"],
            "high_lift_trip_clear": not self.trip_latches["HIGH_LIFT_LOW_SUCTION"],
            "chlorine_trip_clear": not self.trip_latches["CHLORINE_FEED_DEVIATION"],
        }
        self.permissives = {
            name: {"ok": ok, "state": "satisfied" if ok else "blocked"}
            for name, ok in values.items()
        }
        self.sensor_selection = {
            "clearwell_reported_pct": round(clearwell_reported, 3),
            "clearwell_model_pct": round(clearwell_model, 3),
            "fill_protection_level_pct": round(fill_protection_level, 3),
            "draw_protection_level_pct": round(draw_protection_level, 3),
            "strategy": "High selector protects overflow and low selector protects pump suction",
        }
        return values

    def calculate(self, snapshot: PlantSnapshot) -> ActuatorCommand:
        dt_minutes = self._cycle_minutes(snapshot.simulation_time)
        if self.supervisory_expiry and (snapshot.simulation_time >= self.supervisory_expiry or snapshot.controller_mode.value != "gated_auto"):
            self.release_supervision()
        self.control_source = "supervisory lease" if self.supervisory_expiry else "baseline"
        self._update_trips(snapshot)
        permissives = self._build_permissives(snapshot)
        s = snapshot.sensors

        if snapshot.emergency_stop:
            command = ActuatorCommand(
                intake_pump_speed_pct=58.0,
                high_lift_pump_speed_pct=62.0,
                booster_pump_speed_pct=45.0,
                outlet_valve_pct=75.0,
                intake_gate_pct=95.0,
                filter_outlet_valve_pct=95.0,
                zone_1_isolation_valve_pct=100.0,
                zone_2_isolation_valve_pct=100.0,
                zone_3_isolation_valve_pct=100.0,
                pressure_reducing_valve_setpoint_m=52.0,
                coagulant_dose_mg_l=22.0,
                chlorine_dose_mg_l=1.45,
                naoh_dose_mg_l=8.0,
                backwash_request=False,
                emergency_stop=False,
            )
            self.control_source = "emergency recovery to baseline"
            self.last_command = command
            return command

        clearwell_reported = s["clearwell_level_pct"].value
        clearwell_model = self._sensor(snapshot, "clearwell_level_model_pct", clearwell_reported)
        clearwell_for_fill = max(clearwell_reported, clearwell_model)
        clearwell_for_draw = min(clearwell_reported, clearwell_model)
        tank = s["elevated_tank_level_pct"].value
        pressure = min(s[f"zone_{index}_pressure_m"].value for index in range(1, 4))
        chlorine = s["chlorine_residual_mg_l"].value
        raw_turbidity = s["raw_turbidity_ntu"].value
        filter_dp = s["filter_dp_kpa"].value
        finished_ph = s["finished_water_ph"].value
        chlorine_ct = s["chlorine_ct_mg_min_l"].value

        intake = self.loops["clearwell_level"].update(
            setpoint=self.setpoints.clearwell_target_pct,
            process_value=clearwell_for_fill,
            dt_minutes=dt_minutes,
            feedforward=70.0,
            hold_integral=not permissives["control_sensor_quality"],
        )
        high_lift = self.loops["distribution_pressure"].update(
            setpoint=self.setpoints.pressure_target_m,
            process_value=pressure,
            dt_minutes=dt_minutes,
            feedforward=67.0,
            hold_integral=not permissives["control_sensor_quality"],
        )
        booster_output = self.loops["elevated_tank"].update(
            setpoint=self.setpoints.elevated_tank_target_pct,
            process_value=tank,
            dt_minutes=dt_minutes,
            feedforward=48.0 + max(0.0, self.setpoints.pressure_target_m - pressure) * 0.22,
            hold_integral=not permissives["control_sensor_quality"],
        )

        booster_start = pressure < self.setpoints.pressure_target_m - 2.0 or tank < self.setpoints.elevated_tank_target_pct - 5.0
        booster_stop = pressure > self.setpoints.pressure_target_m + 1.0 and tank > self.setpoints.elevated_tank_target_pct + 2.0
        if self.booster_start_delay.update(booster_start, dt_minutes):
            self.runtimes["booster_pump"].running = True
        if self.booster_stop_delay.update(booster_stop, dt_minutes):
            self.runtimes["booster_pump"].running = False
        booster_running = self.runtimes["booster_pump"].update(
            self.runtimes["booster_pump"].running and permissives["high_lift_suction"] and permissives["distribution_path"],
            dt_minutes,
            minimum_off_minutes=3.0,
        )
        booster = booster_output if booster_running else 0.0

        chlorine_feedforward = self.setpoints.chlorine_target_mg_l + 0.20 + raw_turbidity * 0.0025
        chlorine_dose = self.loops["chlorine_residual"].update(
            setpoint=self.setpoints.chlorine_target_mg_l,
            process_value=chlorine,
            dt_minutes=dt_minutes,
            feedforward=chlorine_feedforward,
            hold_integral=not self._quality_ok(snapshot, ["chlorine_residual_mg_l", "chlorine_model_estimate_mg_l"]),
        )
        coag_feedforward = 10.0 + 0.55 * raw_turbidity
        clarified_trim = 1.5 * max(-3.0, min(8.0, self._sensor(snapshot, "clarified_turbidity_ntu", 1.0) - 1.0))
        coagulant_target = 0.45 * self.setpoints.coagulant_target_mg_l + 0.55 * coag_feedforward + clarified_trim
        coagulant = self._bounded(
            self._slew("coagulant_dose_mg_l", coagulant_target, maximum_step=4.0),
            LIMITS["coagulant_dose_mg_l"][0],
            LIMITS["coagulant_dose_mg_l"][1],
        )
        naoh_feedforward = required_naoh_dose(
            s["raw_ph"].value,
            s["raw_alkalinity_mg_l_caco3"].value,
            coagulant,
            self.setpoints.finished_water_ph_target,
        )
        naoh_dose = self.loops["finished_water_ph"].update(
            setpoint=self.setpoints.finished_water_ph_target,
            process_value=finished_ph,
            dt_minutes=dt_minutes,
            feedforward=naoh_feedforward,
            hold_integral=not self._quality_ok(snapshot, ["raw_ph", "raw_alkalinity_mg_l_caco3", "finished_water_ph"]),
        )

        intake_gate = self.setpoints.intake_gate_target_pct
        filter_outlet = self.setpoints.filter_outlet_valve_target_pct
        zone_valves = [
            self.setpoints.zone_1_isolation_target_pct,
            self.setpoints.zone_2_isolation_target_pct,
            self.setpoints.zone_3_isolation_target_pct,
        ]

        backwash_control = self.backwash.update(
            now=snapshot.simulation_time,
            filter_dp_kpa=filter_dp,
            clearwell_level_pct=clearwell_for_draw,
            outlet_position_pct=self._sensor(snapshot, "filter_outlet_valve_position_pct", 100.0),
            sensor_quality_ok=self._quality_ok(snapshot, ["filter_dp_kpa", "clearwell_level_pct", "clearwell_level_model_pct", "filter_outlet_valve_position_pct"]),
        )
        if self.backwash.phase not in {BackwashPhase.IDLE, BackwashPhase.BLOCKED}:
            intake = float(backwash_control.get("intake_pump_speed_pct", intake))
            filter_outlet = float(backwash_control.get("filter_outlet_valve_pct", filter_outlet))
            coagulant = 0.0
            chlorine_dose = 0.0
            naoh_dose = 0.0

        if clearwell_for_draw < 25.0:
            intake, intake_gate, high_lift = 100.0, 100.0, min(high_lift, 45.0)
        if tank < 25.0 or pressure < 25.0:
            high_lift, booster = 100.0, 90.0
            zone_valves = [100.0, 100.0, 100.0]
        if chlorine < 0.2:
            chlorine_dose = min(3.5, chlorine_dose + 1.0)
        if chlorine_ct < LIMITS["chlorine_ct_mg_min_l"][0]:
            chlorine_dose = min(4.0, chlorine_dose + 0.8)
        if finished_ph < LIMITS["finished_water_ph"][0]:
            naoh_dose = min(LIMITS["naoh_dose_mg_l"][1], naoh_dose + 2.0)
        if s["filtered_turbidity_ntu"].value > 1.0:
            high_lift = min(high_lift, 45.0)
        if clearwell_for_fill > 95.0:
            intake, intake_gate, high_lift = 0.0, 0.0, 100.0

        if not (permissives["intake_path"] and permissives["clearwell_not_high_high"] and permissives["intake_trip_clear"]):
            intake = 0.0
        if not (permissives["high_lift_suction"] and permissives["distribution_path"] and permissives["high_lift_trip_clear"]):
            high_lift, booster = 0.0, 0.0
        if not (permissives["chemical_flow_proof"] and permissives["chemical_inventory"]):
            coagulant, chlorine_dose, naoh_dose = 0.0, 0.0, 0.0
        if not permissives["chlorine_trip_clear"]:
            chlorine_dose = 0.0

        intake_running = self.runtimes["intake_pump"].update(intake > 0.5, dt_minutes, minimum_off_minutes=2.0)
        high_lift_running = self.runtimes["high_lift_pump"].update(high_lift > 0.5, dt_minutes, minimum_off_minutes=3.0)
        if not intake_running:
            intake = 0.0
        if not high_lift_running:
            high_lift, booster = 0.0, 0.0

        command = ActuatorCommand(
            intake_pump_speed_pct=round(intake, 2),
            high_lift_pump_speed_pct=round(high_lift, 2),
            booster_pump_speed_pct=round(booster, 2),
            outlet_valve_pct=82.0,
            intake_gate_pct=round(self._slew("intake_gate_pct", intake_gate), 2),
            filter_outlet_valve_pct=round(self._slew("filter_outlet_valve_pct", filter_outlet), 2),
            zone_1_isolation_valve_pct=round(self._slew("zone_1_isolation_valve_pct", zone_valves[0]), 2),
            zone_2_isolation_valve_pct=round(self._slew("zone_2_isolation_valve_pct", zone_valves[1]), 2),
            zone_3_isolation_valve_pct=round(self._slew("zone_3_isolation_valve_pct", zone_valves[2]), 2),
            pressure_reducing_valve_setpoint_m=round(self._bounded(self.setpoints.pressure_target_m + 8.0, 43.0, 60.0), 2),
            coagulant_dose_mg_l=round(coagulant, 2),
            chlorine_dose_mg_l=round(chlorine_dose, 3),
            naoh_dose_mg_l=round(naoh_dose, 3),
            backwash_request=bool(backwash_control["backwash_request"]),
            emergency_stop=False,
        )
        self.loop_status = {
            "clearwell_level": self.loops["clearwell_level"].status(self.setpoints.clearwell_target_pct, clearwell_for_fill),
            "distribution_pressure": self.loops["distribution_pressure"].status(self.setpoints.pressure_target_m, pressure),
            "elevated_tank": self.loops["elevated_tank"].status(self.setpoints.elevated_tank_target_pct, tank),
            "chlorine_residual": self.loops["chlorine_residual"].status(self.setpoints.chlorine_target_mg_l, chlorine),
            "finished_water_ph": self.loops["finished_water_ph"].status(self.setpoints.finished_water_ph_target, finished_ph),
        }
        self.last_command = command
        return command

    def release_supervision(self) -> None:
        for name, value in self.supervisory_previous.items():
            setattr(self.setpoints, name, value)
        self.supervisory_previous = {}
        self.supervisory_expiry = None

    def apply_setpoint_changes(self, changes: SetpointChanges, valid_until: datetime | None = None, source: str = "supervisory") -> None:
        self.release_supervision()
        for name, value in changes.model_dump(exclude_none=True).items():
            if name == "backwash_request":
                if value:
                    self.backwash.request(source)
                continue
            if valid_until is not None:
                self.supervisory_previous[name] = getattr(self.setpoints, name)
            setattr(self.setpoints, name, value)
        self.supervisory_expiry = valid_until

    def setpoint_dict(self) -> dict[str, float]:
        return asdict(self.setpoints)

    def status(self) -> dict[str, object]:
        return {
            "control_source": self.control_source,
            "setpoint_lease_expires": self.supervisory_expiry.isoformat() if self.supervisory_expiry else None,
            "backwash_sequence": self.backwash.status(self.last_cycle_time),
            "permissives": self.permissives,
            "trips": [
                {
                    "code": code,
                    "latched": latched,
                    "reason": self.TRIP_REASONS[code],
                    "first_out": self.trip_first_out.get(code),
                }
                for code, latched in self.trip_latches.items()
            ],
            "control_loops": self.loop_status,
            "equipment_runtime": {name: runtime.status() for name, runtime in self.runtimes.items()},
            "sensor_selection": self.sensor_selection,
        }


class SafetyGate:
    RULES = [
        "schema and finite values",
        "confidence and plant state",
        "control-specific data quality",
        "absolute target limits",
        "decision-step limits",
        "latched controller trips",
        "chemical and storage conflicts",
        "valve command and feedback agreement",
        "15-minute conservative prediction",
    ]

    SENSOR_DEPENDENCIES = {
        "pressure_target_m": ["zone_1_pressure_m", "zone_2_pressure_m", "zone_3_pressure_m", "elevated_tank_level_pct", "distribution_header_pressure_m"],
        "elevated_tank_target_pct": ["elevated_tank_level_pct", "distribution_flow_m3h"],
        "clearwell_target_pct": ["clearwell_level_pct", "clearwell_level_model_pct", "raw_flow_m3h", "distribution_flow_m3h"],
        "chlorine_target_mg_l": ["chlorine_residual_mg_l", "chlorine_model_estimate_mg_l", "chlorine_dose_actual_mg_l", "chlorine_ct_mg_min_l", "filtered_turbidity_ntu", "finished_water_ph"],
        "coagulant_target_mg_l": ["raw_turbidity_ntu", "raw_alkalinity_mg_l_caco3", "coagulation_ph", "clarified_turbidity_ntu"],
        "finished_water_ph_target": ["raw_ph", "raw_alkalinity_mg_l_caco3", "finished_water_ph", "chlorine_ct_mg_min_l", "naoh_dose_actual_mg_l"],
        "intake_gate_target_pct": ["intake_gate_position_pct", "filter_outlet_valve_position_pct", "clearwell_level_pct", "clearwell_level_model_pct"],
        "filter_outlet_valve_target_pct": ["filter_outlet_valve_position_pct", "filter_dp_kpa", "raw_flow_m3h"],
        "backwash_request": ["filter_dp_kpa", "filter_outlet_valve_position_pct", "clearwell_level_pct", "clearwell_level_model_pct"],
    }

    def __init__(self, controller: BaselineController) -> None:
        self.controller = controller

    @classmethod
    def _dependencies(cls, change_names: set[str]) -> set[str]:
        dependencies = {"clearwell_level_pct", "clearwell_level_model_pct"}
        for name in change_names:
            dependencies.update(cls.SENSOR_DEPENDENCIES.get(name, []))
            if name.startswith("zone_") and name.endswith("_isolation_target_pct"):
                zone = name.split("_")[1]
                dependencies.update({f"zone_{zone}_pressure_m", f"zone_{zone}_isolation_valve_position_pct", f"zone_{zone}_served_m3h"})
        return dependencies

    def _predict(self, applied: dict[str, float | bool], snapshot: PlantSnapshot, current: dict[str, float]) -> dict[str, float]:
        pressure_target = float(applied.get("pressure_target_m", current["pressure_target_m"]))
        minimum_pressure = min(snapshot.sensors[f"zone_{index}_pressure_m"].value for index in range(1, 4))
        predicted_header = snapshot.sensors["distribution_header_pressure_m"].value + 0.45 * (pressure_target + 8.0 - snapshot.sensors["distribution_header_pressure_m"].value)
        predicted_pressures = []
        for index in range(1, 4):
            target = float(applied.get(f"zone_{index}_isolation_target_pct", current[f"zone_{index}_isolation_target_pct"]))
            position = max(snapshot.sensors[f"zone_{index}_isolation_valve_position_pct"].value, 2.0)
            current_pressure = snapshot.sensors[f"zone_{index}_pressure_m"].value
            pressure_response = current_pressure + 0.45 * (pressure_target - minimum_pressure)
            predicted_pressures.append(pressure_response * sqrt(max(0.0, target / position)))
        clearwell = snapshot.sensors["clearwell_level_model_pct"].value
        clearwell_target = float(applied.get("clearwell_target_pct", current["clearwell_target_pct"]))
        predicted_clearwell = clearwell + clamp((clearwell_target - clearwell) * 0.18, -4.0, 4.0)
        chlorine = snapshot.sensors["chlorine_model_estimate_mg_l"].value
        chlorine_target = float(applied.get("chlorine_target_mg_l", current["chlorine_target_mg_l"]))
        predicted_chlorine = chlorine + 0.35 * (chlorine_target - chlorine)
        finished_ph = snapshot.sensors["finished_water_ph"].value
        ph_target = float(applied.get("finished_water_ph_target", current["finished_water_ph_target"]))
        predicted_ph = finished_ph + 0.35 * (ph_target - finished_ph)
        return {
            "horizon_minutes": 15.0,
            "clearwell_level_pct": round(predicted_clearwell, 3),
            "minimum_zone_pressure_m": round(min(predicted_pressures), 3),
            "distribution_header_pressure_m": round(predicted_header, 3),
            "chlorine_residual_mg_l": round(predicted_chlorine, 3),
            "finished_water_ph": round(predicted_ph, 3),
        }

    def evaluate(self, proposal: ControlProposal, snapshot: PlantSnapshot) -> GateDecision:
        violations: list[str] = []
        modifications: list[str] = []
        raw_changes = proposal.changes.model_dump(exclude_none=True)
        applied = dict(raw_changes)
        current = self.controller.setpoint_dict()

        if proposal.confidence < 0.55:
            violations.append("Confidence is below the 0.55 gate threshold")
        if snapshot.emergency_stop:
            violations.append("Emergency stop is active")
        if snapshot.safety_state == "critical":
            violations.append("Plant is in a critical state")
        if proposal.source in {"ollama", "jev"} and len(raw_changes) > 4:
            violations.append("An AI proposal may change at most four supervisory targets per decision")
        active_trips = [code for code, active in self.controller.trip_latches.items() if active]
        if active_trips and raw_changes:
            violations.append(f"Latched PLC trips require reset before supervisory changes: {', '.join(active_trips)}")

        dependencies = self._dependencies(set(raw_changes))
        poor_quality = [name for name in sorted(dependencies) if name not in snapshot.sensors or snapshot.sensors[name].quality != "good"]
        if poor_quality:
            violations.append(f"Required sensor data is unavailable or not good quality: {', '.join(poor_quality)}")
        for name in sorted(dependencies):
            sensor = snapshot.sensors.get(name)
            if sensor is None:
                continue
            if not isfinite(sensor.value):
                violations.append(f"{name} is not a finite sensor value")
            age_seconds = (snapshot.simulation_time - sensor.timestamp).total_seconds()
            if age_seconds > 120.0:
                violations.append(f"{name} is older than the 120-second simulation freshness limit")

        for name, value in raw_changes.items():
            if name == "backwash_request":
                continue
            if not isfinite(float(value)):
                violations.append(f"{name} is not a finite setpoint")
                continue
            low, high = SETPOINT_LIMITS[name]
            if not low <= float(value) <= high:
                violations.append(f"{name} is outside the illustrative safe range {low} to {high}")
                continue
            difference = float(value) - current[name]
            if abs(difference) > MAX_SETPOINT_STEP[name]:
                limited = current[name] + copysign(MAX_SETPOINT_STEP[name], difference)
                applied[name] = limited
                modifications.append(f"{name} was rate-limited from {float(value):.3g} to {limited:.3g}")

        chlorine_target = float(applied.get("chlorine_target_mg_l", current["chlorine_target_mg_l"]))
        current_chlorine_target = current["chlorine_target_mg_l"]
        reported_chlorine = snapshot.sensors["chlorine_residual_mg_l"].value
        modeled_chlorine = snapshot.sensors["chlorine_model_estimate_mg_l"].value
        if abs(reported_chlorine - modeled_chlorine) > 0.5 and "chlorine_target_mg_l" in applied:
            violations.append("Chlorine target cannot change while reported and modeled residual disagree")
        if snapshot.sensors["filtered_turbidity_ntu"].value > 0.8 and chlorine_target < current_chlorine_target:
            violations.append("Chlorine target cannot be reduced while filtered turbidity is elevated")

        ph_target = float(applied.get("finished_water_ph_target", current["finished_water_ph_target"]))
        if snapshot.sensors["chlorine_ct_mg_min_l"].value < LIMITS["chlorine_ct_mg_min_l"][0] and ph_target > current["finished_water_ph_target"]:
            violations.append("Finished-water pH target cannot be raised while calculated chlorine CT is low")
        if ph_target > 8.3 and chlorine_target < current_chlorine_target:
            violations.append("A higher pH target conflicts with a lower chlorine target")

        coagulant_target = float(applied.get("coagulant_target_mg_l", current["coagulant_target_mg_l"]))
        if snapshot.sensors["raw_alkalinity_mg_l_caco3"].value < 30.0 and coagulant_target > current["coagulant_target_mg_l"] + 2.0 and ph_target <= current["finished_water_ph_target"]:
            violations.append("Higher coagulant target requires an explicit pH response while source alkalinity is low")

        pressure_target = float(applied.get("pressure_target_m", current["pressure_target_m"]))
        if snapshot.sensors["elevated_tank_level_pct"].value < 35.0 and pressure_target > 50.0:
            violations.append("High pressure target conflicts with low elevated tank level")

        clearwell_reported = snapshot.sensors["clearwell_level_pct"].value
        clearwell_model = snapshot.sensors["clearwell_level_model_pct"].value
        if abs(clearwell_reported - clearwell_model) > 8.0 and ({"clearwell_target_pct", "intake_gate_target_pct"} & set(applied)):
            violations.append("Storage or intake target cannot change while reported and modeled clearwell levels disagree")

        intake_target = float(applied.get("intake_gate_target_pct", current["intake_gate_target_pct"]))
        if min(clearwell_reported, clearwell_model) < 45.0 and intake_target < current["intake_gate_target_pct"]:
            violations.append("Intake gate cannot be restricted while clearwell storage is low")
        filter_target = float(applied.get("filter_outlet_valve_target_pct", current["filter_outlet_valve_target_pct"]))
        if (
            applied.get("backwash_request")
            and "filter_outlet_valve_target_pct" in applied
            and filter_target > 30.0
        ):
            violations.append("Backwash conflicts with an open filter outlet target")
        if applied.get("backwash_request"):
            if min(clearwell_reported, clearwell_model) < 50.0:
                violations.append("Backwash requires clearwell level of at least 50 percent")
            if snapshot.sensors["filter_dp_kpa"].value < 38.0:
                violations.append("Backwash requires filter differential pressure of at least 38 kPa")

        filter_command = float(snapshot.actuators.get("filter_outlet_valve_pct", 100.0))
        filter_position = snapshot.sensors["filter_outlet_valve_position_pct"].value
        if abs(filter_command - filter_position) > 20.0 and ({"intake_gate_target_pct", "filter_outlet_valve_target_pct", "pressure_target_m"} & set(applied)):
            violations.append("Pump, intake, and pressure targets are frozen during a filter valve command-feedback mismatch")

        proposed_zone_targets = [float(applied.get(f"zone_{index}_isolation_target_pct", current[f"zone_{index}_isolation_target_pct"])) for index in range(1, 4)]
        closing_valves = sum(target < current[f"zone_{index}_isolation_target_pct"] for index, target in enumerate(proposed_zone_targets, start=1))
        if closing_valves > 1:
            violations.append("Only one demand-zone isolation target may be reduced per decision")
        for index, target in enumerate(proposed_zone_targets, start=1):
            current_pressure = snapshot.sensors[f"zone_{index}_pressure_m"].value
            current_position = max(snapshot.sensors[f"zone_{index}_isolation_valve_position_pct"].value, 1.0)
            commanded_position = float(snapshot.actuators.get(f"zone_{index}_isolation_valve_pct", current_position))
            predicted_pressure = current_pressure * sqrt(max(0.0, target / current_position))
            if abs(commanded_position - current_position) > 20.0 and f"zone_{index}_isolation_target_pct" in applied:
                violations.append(f"Zone {index} valve target is frozen during command-feedback mismatch")
            if target < current[f"zone_{index}_isolation_target_pct"] and current_pressure < 35.0:
                violations.append(f"Zone {index} valve cannot be restricted while its pressure is low")
            if predicted_pressure < LIMITS["zone_pressure_m"][0]:
                violations.append(f"Zone {index} valve target predicts pressure below the illustrative minimum")

        predicted_state = self._predict(applied, snapshot, current)
        if predicted_state["minimum_zone_pressure_m"] < LIMITS["zone_pressure_m"][0]:
            violations.append("The 15-minute conservative prediction crosses the minimum zone-pressure boundary")
        if not LIMITS["chlorine_residual_mg_l"][0] <= predicted_state["chlorine_residual_mg_l"] <= LIMITS["chlorine_residual_mg_l"][1]:
            violations.append("The 15-minute conservative prediction crosses the chlorine-residual boundary")
        if not LIMITS["finished_water_ph"][0] <= predicted_state["finished_water_ph"] <= LIMITS["finished_water_ph"][1]:
            violations.append("The 15-minute conservative prediction crosses the finished-water pH boundary")

        if violations:
            return GateDecision(
                decision_id=proposal.decision_id,
                status="rejected",
                violated_constraints=list(dict.fromkeys(violations)),
                modifications=modifications,
                evaluated_rules=self.RULES,
                predicted_state=predicted_state,
                risk_level="high",
                fallback_reason="Baseline controller retained control",
            )

        applied_values = SetpointChanges(**applied)
        return GateDecision(
            decision_id=proposal.decision_id,
            status="modified" if modifications else "accepted",
            modifications=modifications,
            evaluated_rules=self.RULES,
            predicted_state=predicted_state,
            risk_level="medium" if modifications else "low",
            applied_values=applied_values,
        )
