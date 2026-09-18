from __future__ import annotations

from shared.exercise import ExerciseRecorder
from shared.operations import OperationsModel

from collections import deque
from datetime import datetime, timedelta, timezone
from math import exp, sqrt
from threading import RLock

import numpy as np

from shared.chemistry import (
    ALUM_PRODUCT_G_L,
    HYPOCHLORITE_AVAILABLE_CHLORINE_G_L,
    NAOH_SOLUTION_G_L,
    alum_alkalinity_demand,
    free_chlorine_hocl_fraction,
    inorganic_carbon_mol_l,
    naoh_alkalinity_addition,
    ph_from_alkalinity,
    solution_flow_lph,
)
from shared.limits import LIMITS, VALVE_TRAVEL_RATE_PCT_MIN
from shared.models import (
    Alarm,
    ControlMode,
    EquipmentState,
    PlantSnapshot,
    ProcessCheckpoint,
    SensorValue,
    TwinHealth,
    ValveState,
)
from .scenarios import INJECTIONS, SCENARIOS, demand_multiplier, scenario_modifiers

try:
    import wntr
except ImportError:  # pragma: no cover
    wntr = None


VALVE_COMMANDS = {
    "intake_gate": "intake_gate_pct",
    "filter_outlet": "filter_outlet_valve_pct",
    "zone_1_isolation": "zone_1_isolation_valve_pct",
    "zone_2_isolation": "zone_2_isolation_valve_pct",
    "zone_3_isolation": "zone_3_isolation_valve_pct",
}


class WaterPlantSimulator:
    """Treatment and pressure-dependent distribution model for a local OT lab."""

    def __init__(self, seed: int = 42, speed: int = 10) -> None:
        self.lock = RLock()
        self._build_distribution_model()
        self.reset(seed=seed, speed=speed)

    def reset(self, seed: int = 42, speed: int = 10, scenario: str = "normal_day") -> None:
        with self.lock:
            self.seed = seed
            self.rng = np.random.default_rng(seed)
            self.operations = OperationsModel("water")
            self.minute = 0
            self.simulation_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
            self.speed = speed
            self.running = False
            self.scenario = scenario if scenario in SCENARIOS else "normal_day"
            self.injection_expiry: dict[str, int] = {}
            self.controller_mode = ControlMode.BASELINE
            self.clearwell_level_pct = 65.0
            self.elevated_tank_level_pct = 68.0
            self.filter_dp_kpa = 18.0
            self.filtered_turbidity_ntu = 0.18
            self.clarified_turbidity_ntu = 1.4
            self.true_chlorine_mg_l = 1.15
            self.raw_turbidity_ntu = 8.0
            self.raw_ph = 7.35
            self.raw_alkalinity_mg_l_caco3 = 55.0
            self.settled_alkalinity_mg_l_caco3 = 44.0
            self.finished_alkalinity_mg_l_caco3 = 54.0
            self.coagulation_ph = 6.78
            self.finished_water_ph = 7.30
            self.water_temperature_c = 15.0
            self.chlorine_contact_time_min = 65.0
            self.chlorine_ct_mg_min_l = 74.8
            self.hocl_fraction_pct = 61.3
            self.alum_feed_runtime_min = 0.0
            self.chlorine_feed_runtime_min = 0.0
            self.naoh_feed_runtime_min = 0.0
            self.actual_coagulant_dose_mg_l = 22.0
            self.actual_naoh_dose_mg_l = 8.0
            self.actual_chlorine_dose_mg_l = 1.45
            self.chemical_feed_flow_proof = True
            self.actual_intake_speed_pct = 72.0
            self.actual_high_lift_speed_pct = 70.0
            self.water_balance_error_m3 = 0.0
            self.elevated_exchange_m3h = 0.0
            self.clearwell_overflow_m3h = 0.0
            self.pump_deadhead_pressure_kpa = 0.0
            self.alum_solution_flow_lph = solution_flow_lph(280.0, 22.0, ALUM_PRODUCT_G_L)
            self.naoh_solution_flow_lph = solution_flow_lph(280.0, 8.0, NAOH_SOLUTION_G_L)
            self.hypochlorite_solution_flow_lph = solution_flow_lph(280.0, 1.45, HYPOCHLORITE_AVAILABLE_CHLORINE_G_L)
            self.chemical_tanks = {
                "alum": {"bulk_capacity_l": 15_000.0, "bulk_volume_l": 12_300.0, "day_capacity_l": 1_000.0, "day_volume_l": 680.0, "transfer_lpm": 8.0, "refilling": False},
                "naoh": {"bulk_capacity_l": 8_000.0, "bulk_volume_l": 6_240.0, "day_capacity_l": 750.0, "day_volume_l": 465.0, "transfer_lpm": 5.0, "refilling": False},
                "hypochlorite": {"bulk_capacity_l": 10_000.0, "bulk_volume_l": 7_500.0, "day_capacity_l": 1_000.0, "day_volume_l": 610.0, "transfer_lpm": 6.0, "refilling": False},
            }
            self.raw_flow_m3h = 280.0
            self.distribution_flow_m3h = 228.0
            self.telemetry_distribution_flow_m3h = 228.0
            self.zone_pressures = [46.0, 43.0, 40.0]
            self.telemetry_zone_pressures = self.zone_pressures.copy()
            self.zone_demands = [86.0, 78.0, 64.0]
            self.zone_served = self.zone_demands.copy()
            self.zone_valve_dp_kpa = [0.0, 0.0, 0.0]
            self.pump_discharge_pressure_m = 56.0
            self.distribution_header_pressure_m = 52.0
            self.filter_inlet_pressure_kpa = 112.0
            self.filter_outlet_pressure_kpa = 94.0
            self.intake_upstream_pressure_m = 6.0
            self.intake_downstream_pressure_m = 5.9
            self.leak_flow_m3h = 0.0
            self.energy_kw = 48.0
            self.hydraulic_engine = "WNTR" if wntr is not None else "analytical fallback"
            self.hydraulic_error: str | None = None
            self.actuators: dict[str, float | bool] = {
                "intake_pump_speed_pct": 72.0,
                "high_lift_pump_speed_pct": 70.0,
                "booster_pump_speed_pct": 54.0,
                "outlet_valve_pct": 82.0,
                "intake_gate_pct": 95.0,
                "filter_outlet_valve_pct": 95.0,
                "zone_1_isolation_valve_pct": 100.0,
                "zone_2_isolation_valve_pct": 100.0,
                "zone_3_isolation_valve_pct": 100.0,
                "pressure_reducing_valve_setpoint_m": 52.0,
                "coagulant_dose_mg_l": 22.0,
                "chlorine_dose_mg_l": 1.45,
                "naoh_dose_mg_l": 8.0,
                "backwash_request": False,
                "emergency_stop": False,
            }
            self.valve_positions = {
                name: float(self.actuators[command]) for name, command in VALVE_COMMANDS.items()
            }
            self.previous_valve_positions = self.valve_positions.copy()
            self.histories = {
                key: deque(maxlen=120)
                for key in [
                    "clearwell_level_pct",
                    "elevated_tank_level_pct",
                    "zone_2_pressure_m",
                    "chlorine_residual_mg_l",
                    "finished_water_ph",
                    "chlorine_ct_mg_min_l",
                    "filtered_turbidity_ntu",
                    "energy_kw",
                    "distribution_header_pressure_m",
                ]
            }
            self._last_modifiers = scenario_modifiers(0, self.scenario)
            self._record_history()
            self.exercise = ExerciseRecorder("water", self.scenario, self.seed)
            self.exercise.capture(self.snapshot(), self.minute)

    def _build_distribution_model(self) -> None:
        self.network = None
        if wntr is None:
            return
        try:
            network = wntr.network.WaterNetworkModel()
            network.options.time.duration = 300
            network.options.time.hydraulic_timestep = 300
            network.options.hydraulic.demand_model = "PDD"
            network.options.hydraulic.minimum_pressure = 10.0
            network.options.hydraulic.required_pressure = 30.0
            network.options.hydraulic.pressure_exponent = 0.5
            network.add_reservoir("Clearwell", base_head=70.0)
            network.add_junction("PumpDischarge", base_demand=0, demand_pattern=None, elevation=20.0)
            network.add_junction("Header", base_demand=0, demand_pattern=None, elevation=20.0)
            for index, elevation in enumerate([20.0, 23.0, 27.0], start=1):
                network.add_junction(f"Zone{index}Up", base_demand=0, demand_pattern=None, elevation=elevation)
                network.add_junction(f"Zone{index}", base_demand=0.02, demand_pattern=None, elevation=elevation)
            network.add_tank("Elevated", elevation=50.0, init_level=13.6, min_level=2.0, max_level=20.0, diameter=18.0)
            network.add_curve("HighLiftCurve", "HEAD", [(0.0, 70.0), (0.15, 55.0), (0.30, 20.0)])
            network.add_pump("HighLift", "Clearwell", "PumpDischarge", pump_type="HEAD", pump_parameter="HighLiftCurve")
            network.add_valve("HeaderPRV", "PumpDischarge", "Header", diameter=0.45, valve_type="PRV", initial_setting=52.0)
            lengths = [900.0, 1800.0, 2500.0]
            diameters = [0.35, 0.32, 0.30]
            for index in range(1, 4):
                network.add_pipe(f"P{index}", "Header", f"Zone{index}Up", length=lengths[index - 1], diameter=diameters[index - 1], roughness=125, minor_loss=0)
                network.add_valve(f"VZ{index}", f"Zone{index}Up", f"Zone{index}", diameter=diameters[index - 1], valve_type="TCV", initial_setting=0.2)
            network.add_pipe("PTank", "Header", "Elevated", length=950, diameter=0.32, roughness=125, minor_loss=0)
            self.network = network
        except Exception:
            self.network = None

    def configure(self, *, scenario: str, seed: int, speed: int, mode: ControlMode) -> None:
        self.reset(seed=seed, speed=speed, scenario=scenario)
        self.controller_mode = mode

    def set_actuators(self, changes: dict[str, float | bool]) -> None:
        with self.lock:
            for name, value in changes.items():
                if name in self.actuators and value is not None:
                    self.actuators[name] = value

    def active_injections(self) -> list[str]:
        expired = [name for name, expiry in self.injection_expiry.items() if self.minute >= expiry]
        for name in expired:
            del self.injection_expiry[name]
        return sorted(self.injection_expiry)

    def inject(self, injection_id: str, duration_minutes: int) -> list[str]:
        with self.lock:
            if injection_id not in INJECTIONS:
                raise KeyError(injection_id)
            self.injection_expiry[injection_id] = self.minute + duration_minutes
            if injection_id == "clearwell_overflow":
                self.clearwell_level_pct = max(self.clearwell_level_pct, 99.8)
            return self.active_injections()

    def clear_injections(self) -> None:
        with self.lock:
            self.injection_expiry.clear()
            self.clearwell_overflow_m3h = 0.0
            self.pump_deadhead_pressure_kpa = 0.0

    def advance(self, minutes: int = 1) -> None:
        with self.lock:
            for _ in range(minutes):
                self._step_minute()
                self.operations.observe(self)
                self.exercise.capture(self.snapshot(), self.minute)

    @staticmethod
    def _flow_factor(position_pct: float) -> float:
        return sqrt(max(0.0, min(1.0, position_pct / 100.0)))

    @staticmethod
    def _valve_headloss_m(flow_m3h: float, position_pct: float) -> float:
        position = max(position_pct, 2.0)
        return max(0.0, 0.35 * (flow_m3h / 100.0) ** 2 * ((100.0 / position) ** 2 - 1.0))

    def _move_valves(self) -> None:
        self.previous_valve_positions = self.valve_positions.copy()
        for name, command_name in VALVE_COMMANDS.items():
            current = self.valve_positions[name]
            target = float(self.actuators[command_name])
            movement = float(np.clip(target - current, -VALVE_TRAVEL_RATE_PCT_MIN, VALVE_TRAVEL_RATE_PCT_MIN))
            self.valve_positions[name] = float(np.clip(current + movement, 0.0, 100.0))

    def _step_minute(self) -> None:
        self.minute += 1
        self.simulation_time += timedelta(minutes=1)
        self.operations.tick(self.minute, self.exercise, backwash=bool(self.actuators["backwash_request"]), emergency=bool(self.actuators["emergency_stop"]))
        mods = scenario_modifiers(self.minute, self.scenario)
        if self.operations.active("storm_water_quality"):
            mods["raw_turbidity_ntu"] = 65.0
        self._last_modifiers = mods
        self._move_valves()
        injections = set(self.active_injections())
        if "clearwell_overflow" in injections:
            self.valve_positions["intake_gate"] = 100.0
        if "pump_valve_conflict" in injections:
            self.valve_positions["filter_outlet"] = 0.0
        if "zone_2_valve_forced_closed" in injections:
            self.valve_positions["zone_2_isolation"] = 0.0
        emergency = bool(self.actuators["emergency_stop"])
        intake_speed = 0.0 if emergency else float(self.actuators["intake_pump_speed_pct"])
        high_lift_speed = 0.0 if emergency or not mods["pump_available"] else float(self.actuators["high_lift_pump_speed_pct"])
        if not emergency and "clearwell_overflow" in injections:
            intake_speed, high_lift_speed = 100.0, 10.0
        if not emergency and "pump_valve_conflict" in injections:
            intake_speed = max(75.0, intake_speed)
        supply = .2 + .65*self.operations.fraction("DG-901") if self.operations.active("storm_supply") else 1.0
        intake_speed *= supply * (.6+.4*self.operations.fraction("SC-101"))
        high_lift_speed *= supply
        self.actual_intake_speed_pct = intake_speed
        self.actual_high_lift_speed_pct = high_lift_speed

        intake_factor = self._flow_factor(self.valve_positions["intake_gate"])
        self.raw_flow_m3h = 4.1 * intake_speed * intake_factor
        if "pump_valve_conflict" in injections:
            self.raw_flow_m3h *= 0.04
        self.raw_turbidity_ntu = max(0.01, float(mods["raw_turbidity_ntu"]) + float(self.rng.normal(0, 0.18)))
        self.raw_ph = float(np.clip(float(mods["raw_ph"]) + float(self.rng.normal(0, 0.006)), 5.5, 9.5))
        self.raw_alkalinity_mg_l_caco3 = max(
            1.0,
            float(mods["raw_alkalinity_mg_l_caco3"]) + float(self.rng.normal(0, 0.25)),
        )
        self.water_temperature_c = float(mods["water_temperature_c"])
        intake_loss = self._valve_headloss_m(self.raw_flow_m3h, self.valve_positions["intake_gate"])
        self.intake_downstream_pressure_m = max(0.0, self.intake_upstream_pressure_m - intake_loss)

        self.chemical_feed_flow_proof = self.raw_flow_m3h >= 25.0 and not emergency
        alum_inventory_ok = self.chemical_tanks["alum"]["day_volume_l"] > 0.5
        naoh_inventory_ok = self.chemical_tanks["naoh"]["day_volume_l"] > 0.5
        hypochlorite_inventory_ok = self.chemical_tanks["hypochlorite"]["day_volume_l"] > 0.5
        coagulant_command = float(self.actuators["coagulant_dose_mg_l"])
        coagulant = coagulant_command if self.chemical_feed_flow_proof and alum_inventory_ok else 0.0
        self.actual_coagulant_dose_mg_l = coagulant
        self.alum_solution_flow_lph = solution_flow_lph(self.raw_flow_m3h, coagulant, ALUM_PRODUCT_G_L)
        inorganic_carbon = inorganic_carbon_mol_l(self.raw_ph, self.raw_alkalinity_mg_l_caco3)
        self.settled_alkalinity_mg_l_caco3 = max(
            0.1,
            self.raw_alkalinity_mg_l_caco3 - alum_alkalinity_demand(coagulant),
        )
        self.coagulation_ph = ph_from_alkalinity(self.settled_alkalinity_mg_l_caco3, inorganic_carbon)
        ideal_dose = 10.0 + 0.55 * self.raw_turbidity_ntu
        dose_error = abs(coagulant - ideal_dose) / max(ideal_dose, 1.0)
        ph_efficiency = exp(-((self.coagulation_ph - 6.8) / 0.85) ** 2)
        removal = np.clip(0.66 + 0.28 * ph_efficiency - dose_error * 0.24, 0.35, 0.94)
        mixing = .4+.6*min(self.operations.fraction("MX-111"), self.operations.fraction("MX-121"))
        removal *= mixing
        self.operations.sludge_inventory_pct = max(0.0, min(100.0, self.operations.sludge_inventory_pct + self.raw_turbidity_ntu*.02 - self.operations.fraction("P-161")*.6))
        removal *= 1-max(0.0, self.operations.sludge_inventory_pct-70)*.005
        self.clarified_turbidity_ntu = max(0.05, self.raw_turbidity_ntu * (1 - removal))

        backwashing = bool(self.actuators["backwash_request"])
        if backwashing:
            self.filter_dp_kpa = max(12.0, self.filter_dp_kpa - 8.0*min(self.operations.fraction("P-171"),self.operations.fraction("BL-172")))
            filtration_factor = 0.24
        else:
            self.filter_dp_kpa = min(80.0, self.filter_dp_kpa + self.raw_flow_m3h * (0.0003 + self.raw_turbidity_ntu * 0.000008))
            filtration_factor = 0.11 + max(0.0, self.filter_dp_kpa - 45.0) * 0.006
        self.filtered_turbidity_ntu = max(0.02, self.clarified_turbidity_ntu * filtration_factor)
        self.pump_deadhead_pressure_kpa = 0.0
        self.filter_inlet_pressure_kpa = 112.0 + self.raw_flow_m3h * 0.015
        if "pump_valve_conflict" in injections and intake_speed > 20.0:
            self.pump_deadhead_pressure_kpa = 175.0 + intake_speed * 1.15
            self.filter_inlet_pressure_kpa = self.pump_deadhead_pressure_kpa
        outlet_valve_loss_kpa = 9.80665 * self._valve_headloss_m(self.raw_flow_m3h, self.valve_positions["filter_outlet"])
        self.filter_outlet_pressure_kpa = max(0.0, self.filter_inlet_pressure_kpa - self.filter_dp_kpa - outlet_valve_loss_kpa)
        if "pump_valve_conflict" in injections:
            self.filter_outlet_pressure_kpa = 0.0

        naoh_command = float(self.actuators["naoh_dose_mg_l"])
        self.actual_naoh_dose_mg_l = naoh_command if bool(mods["naoh_available"]) and self.chemical_feed_flow_proof and naoh_inventory_ok else 0.0
        self.naoh_solution_flow_lph = solution_flow_lph(self.raw_flow_m3h, self.actual_naoh_dose_mg_l, NAOH_SOLUTION_G_L)
        equilibrium_alkalinity = self.settled_alkalinity_mg_l_caco3 + naoh_alkalinity_addition(self.actual_naoh_dose_mg_l)
        equilibrium_ph = ph_from_alkalinity(equilibrium_alkalinity, inorganic_carbon)
        self.finished_alkalinity_mg_l_caco3 += (equilibrium_alkalinity - self.finished_alkalinity_mg_l_caco3) * 0.18
        self.finished_water_ph += (equilibrium_ph - self.finished_water_ph) * 0.18

        demand_factor = demand_multiplier(self.minute, self.scenario)
        base_demands = np.array([86.0, 78.0, 64.0])
        noise = self.rng.normal(1.0, 0.012, 3)
        self.zone_demands = list(base_demands * demand_factor * noise)
        self.leak_flow_m3h = float(mods["leak_flow_m3h"])
        requested_flow = sum(self.zone_demands) + self.leak_flow_m3h
        pump_efficiency = float(mods["pump_efficiency_pct"]) / 100.0
        pump_capacity = 4.5 * high_lift_speed * pump_efficiency
        filter_factor = self._flow_factor(self.valve_positions["filter_outlet"])
        zone_capacity_factor = sum(self._flow_factor(self.valve_positions[f"zone_{index}_isolation"]) for index in range(1, 4)) / 3.0
        available_flow = pump_capacity * filter_factor * zone_capacity_factor
        self.distribution_flow_m3h = min(requested_flow * 1.08, available_flow)

        filter_factor *= (self.operations.fraction("FT-151A")+self.operations.fraction("FT-151B"))/2
        treatment_outflow = min(self.raw_flow_m3h * 0.97 * filter_factor * (0.15 if backwashing else 1.0), 330.0)
        initial_storage = self.clearwell_level_pct * 22.0 + self.elevated_tank_level_pct * 9.5
        pump_flow = min(self.distribution_flow_m3h, self.clearwell_level_pct * 22 * 60 + treatment_outflow)
        # Elevated storage can supply up to 25 m3/h through its modeled gravity path.
        gravity_flow = min(25.0, max(0.0, self.elevated_tank_level_pct - 20.0) * 9.5 * 60)
        self.distribution_flow_m3h = pump_flow + gravity_flow

        dose = float(self.actuators["chlorine_dose_mg_l"]) if self.chemical_feed_flow_proof and hypochlorite_inventory_ok else 0.0
        if not emergency and "chlorine_overfeed" in injections:
            dose = 5.0
        self.actual_chlorine_dose_mg_l = dose
        self.hypochlorite_solution_flow_lph = solution_flow_lph(self.raw_flow_m3h, self.actual_chlorine_dose_mg_l, HYPOCHLORITE_AVAILABLE_CHLORINE_G_L)
        usable_clearwell_m3 = max(0.0, (self.clearwell_level_pct - 25.0) / 100.0 * 2200.0)
        theoretical_detention_min = usable_clearwell_m3 / max(self.distribution_flow_m3h / 60.0, 0.1)
        self.chlorine_contact_time_min = float(np.clip(theoretical_detention_min * 0.30, 0.0, 360.0))
        self.hocl_fraction_pct = 100.0 * free_chlorine_hocl_fraction(self.finished_water_ph)
        temperature_rate = 0.14 * 1.035 ** (self.water_temperature_c - 15.0)
        chlorine_demand = 0.10 + self.raw_turbidity_ntu * 0.0025
        target_true = max(0.0, dose - chlorine_demand) * exp(-temperature_rate * self.chlorine_contact_time_min / 60.0)
        self.true_chlorine_mg_l += (target_true - self.true_chlorine_mg_l) * 0.08
        self.chlorine_ct_mg_min_l = max(0.0, self.true_chlorine_mg_l * self.chlorine_contact_time_min)
        if dose > 0.05:
            self.chlorine_feed_runtime_min += 1.0
        if self.actual_coagulant_dose_mg_l > 0.05:
            self.alum_feed_runtime_min += 1.0
        if self.actual_naoh_dose_mg_l > 0.05:
            self.naoh_feed_runtime_min += 1.0

        self._update_chemical_storage()

        if self.minute % 5 == 0:
            self._run_hydraulics(requested_flow, high_lift_speed)
        self._update_served_demand()
        delivered = self.distribution_flow_m3h
        tank_draw = max(0.0, delivered - pump_flow)
        tank_fill = min(20.0, max(0.0, pump_flow - delivered), (100-self.elevated_tank_level_pct)*9.5*60)
        clearwell_outflow = min(pump_flow, delivered) + tank_fill
        self.elevated_exchange_m3h = tank_fill - tank_draw
        self.elevated_tank_level_pct += self.elevated_exchange_m3h / 60 / 9.5
        candidate_volume = self.clearwell_level_pct * 22 + (treatment_outflow-clearwell_outflow)/60
        self.clearwell_overflow_m3h = max(0.0, candidate_volume - 2200) * 60
        self.clearwell_level_pct = min(2200.0, max(0.0, candidate_volume))/22
        final_storage = self.clearwell_level_pct * 22 + self.elevated_tank_level_pct * 9.5
        self.water_balance_error_m3 = final_storage - initial_storage - (treatment_outflow-delivered-self.clearwell_overflow_m3h)/60
        self.telemetry_zone_pressures = [
            max(0.0, pressure + float(self.rng.normal(0.0, 0.18)))
            for pressure in self.zone_pressures
        ]
        self.telemetry_distribution_flow_m3h = max(
            0.0,
            self.distribution_flow_m3h * (1.0 + float(self.rng.normal(0.0, 0.004))),
        )
        self.energy_kw = (
            0.0048 * self.raw_flow_m3h * intake_speed
            + 0.0065 * self.distribution_flow_m3h * high_lift_speed / max(pump_efficiency, 0.3)
            + 0.8 * float(self.actuators["booster_pump_speed_pct"])
        )
        self._record_history()

    def _update_chemical_storage(self) -> None:
        feed_rates = {
            "alum": self.alum_solution_flow_lph,
            "naoh": self.naoh_solution_flow_lph,
            "hypochlorite": self.hypochlorite_solution_flow_lph,
        }
        for name, tank in self.chemical_tanks.items():
            day_pct = 100.0 * tank["day_volume_l"] / tank["day_capacity_l"]
            if day_pct < 35.0 and tank["bulk_volume_l"] > 0.0:
                tank["refilling"] = True
            elif day_pct > 80.0 or tank["bulk_volume_l"] <= 0.0:
                tank["refilling"] = False
            transfer = min(tank["transfer_lpm"], tank["bulk_volume_l"]) if tank["refilling"] else 0.0
            consumption = feed_rates[name] / 60.0
            tank["bulk_volume_l"] = max(0.0, tank["bulk_volume_l"] - transfer)
            tank["day_volume_l"] = float(np.clip(tank["day_volume_l"] + transfer - consumption, 0.0, tank["day_capacity_l"]))

    def _chemical_sensor_data(self) -> dict[str, tuple[float, str]]:
        sensor_data: dict[str, tuple[float, str]] = {}
        feed_rates = {
            "alum": self.alum_solution_flow_lph,
            "naoh": self.naoh_solution_flow_lph,
            "hypochlorite": self.hypochlorite_solution_flow_lph,
        }
        for name, tank in self.chemical_tanks.items():
            sensor_data[f"{name}_bulk_tank_level_pct"] = (100.0 * tank["bulk_volume_l"] / tank["bulk_capacity_l"], "%")
            sensor_data[f"{name}_day_tank_level_pct"] = (100.0 * tank["day_volume_l"] / tank["day_capacity_l"], "%")
            sensor_data[f"{name}_transfer_valve_position_pct"] = (100.0 if tank["refilling"] else 0.0, "%")
            sensor_data[f"{name}_injection_valve_position_pct"] = (100.0 if feed_rates[name] > 0.05 else 0.0, "%")
        return sensor_data

    def _run_hydraulics(self, requested_flow: float, pump_speed: float) -> None:
        self.pump_discharge_pressure_m = 18.0 + pump_speed * 0.58 + self.elevated_tank_level_pct * 0.05
        prv_setpoint = float(self.actuators["pressure_reducing_valve_setpoint_m"])
        self.distribution_header_pressure_m = min(self.pump_discharge_pressure_m, prv_setpoint)
        shortage = max(0.0, requested_flow - self.distribution_flow_m3h)
        leak_penalty = self.leak_flow_m3h * 0.12
        analytical = []
        for index, base_pipe_loss in enumerate([2.0, 4.0, 7.0], start=1):
            position = self.valve_positions[f"zone_{index}_isolation"]
            allocation = self.zone_demands[index - 1] * min(1.0, self.distribution_flow_m3h / max(requested_flow, 1.0))
            valve_loss = self._valve_headloss_m(allocation, position)
            analytical.append(max(0.0, self.distribution_header_pressure_m - base_pipe_loss - valve_loss - shortage * 0.06 - leak_penalty))
        if self.network is None:
            self.zone_pressures = analytical
            self._update_valve_differentials()
            return
        try:
            for index, name in enumerate(["Zone1", "Zone2", "Zone3"]):
                node = self.network.get_node(name)
                node.demand_timeseries_list[0].base_value = self.zone_demands[index] / 3600.0
                valve = self.network.get_link(f"VZ{index + 1}")
                position = self.valve_positions[f"zone_{index + 1}_isolation"]
                valve.initial_setting = min(1_000_000.0, 0.2 + 80.0 * ((100.0 - position) / max(position, 2.0)) ** 2)
            self.network.get_link("HeaderPRV").initial_setting = prv_setpoint
            self.network.get_node("Elevated").init_level = 20.0 * self.elevated_tank_level_pct / 100.0
            speed_ratio = float(np.clip(pump_speed / 70.0, 0.20, 1.35))
            base_curve = [(0.0, 70.0), (0.15, 55.0), (0.30, 20.0)]
            self.network.get_curve("HighLiftCurve").points = [(flow * speed_ratio, head * speed_ratio**2) for flow, head in base_curve]
            self.network.get_link("HighLift").base_speed = 1.0
            result = wntr.sim.WNTRSimulator(self.network).run_sim()
            last_pressure = result.node["pressure"].iloc[-1]
            calculated = [float(last_pressure[name]) for name in ["Zone1", "Zone2", "Zone3"]]
            if all(np.isfinite(calculated)):
                self.zone_pressures = [max(0.0, value - leak_penalty) for value in calculated]
                self.pump_discharge_pressure_m = max(0.0, float(last_pressure["PumpDischarge"]))
                self.distribution_header_pressure_m = max(0.0, float(last_pressure["Header"]))
                self.hydraulic_engine = "WNTR PDD with PRV and TCV valves"
                self._update_valve_differentials()
                return
        except Exception as exc:
            self.hydraulic_error = f"{type(exc).__name__}: {exc}"
            self.hydraulic_engine = "analytical valve fallback"
        self.zone_pressures = analytical
        self._update_valve_differentials()

    def _update_served_demand(self) -> None:
        total_capacity_ratio = min(1.0, self.distribution_flow_m3h / max(sum(self.zone_demands), 1.0))
        served = []
        for index, demand in enumerate(self.zone_demands, start=1):
            pressure = self.zone_pressures[index - 1]
            if pressure <= 10.0:
                pressure_factor = 0.0
            elif pressure < 30.0:
                pressure_factor = sqrt((pressure - 10.0) / 20.0)
            else:
                pressure_factor = 1.0
            valve_factor = self._flow_factor(self.valve_positions[f"zone_{index}_isolation"])
            served.append(float(demand * min(total_capacity_ratio, pressure_factor, valve_factor)))
        self.zone_served = served
        self.distribution_flow_m3h = sum(served) + min(self.leak_flow_m3h, max(0.0, self.distribution_flow_m3h - sum(served)))
        self._update_valve_differentials()

    def _update_valve_differentials(self) -> None:
        self.zone_valve_dp_kpa = []
        for index in range(1, 4):
            loss_m = self._valve_headloss_m(
                self.zone_served[index - 1],
                self.valve_positions[f"zone_{index}_isolation"],
            )
            self.zone_valve_dp_kpa.append(loss_m * 9.80665)

    def _record_history(self) -> None:
        injections = set(self.active_injections())
        observed_chlorine = self.true_chlorine_mg_l + float(self._last_modifiers.get("chlorine_sensor_bias", 0.0))
        observed_clearwell_level = self.clearwell_level_pct
        if "chlorine_sensor_spoof_high" in injections:
            observed_chlorine = 2.6
        if "level_sensor_spoof_low" in injections:
            observed_clearwell_level = 32.0
        values = {
            "clearwell_level_pct": observed_clearwell_level,
            "elevated_tank_level_pct": self.elevated_tank_level_pct,
            "zone_2_pressure_m": self.telemetry_zone_pressures[1],
            "chlorine_residual_mg_l": observed_chlorine,
            "finished_water_ph": self.finished_water_ph,
            "chlorine_ct_mg_min_l": self.chlorine_ct_mg_min_l,
            "filtered_turbidity_ntu": self.filtered_turbidity_ntu,
            "energy_kw": self.energy_kw,
            "distribution_header_pressure_m": self.distribution_header_pressure_m,
        }
        for key, value in values.items():
            self.histories[key].append(round(float(value), 4))

    def _valve_status(self, name: str, interlocked: bool = False) -> str:
        if interlocked:
            return "interlocked"
        current = self.valve_positions[name]
        previous = self.previous_valve_positions[name]
        if current <= 2.0:
            return "closed"
        if current >= 98.0:
            return "open"
        if current > previous + 0.1:
            return "opening"
        if current < previous - 0.1:
            return "closing"
        return "throttled"

    def _valve_states(self) -> dict[str, ValveState]:
        states: dict[str, ValveState] = {}
        valve_data = {
            "intake_gate": ("gate", self.intake_upstream_pressure_m, self.intake_downstream_pressure_m, self.raw_flow_m3h, False),
            "filter_outlet": ("isolation", self.filter_inlet_pressure_kpa / 9.80665, self.filter_outlet_pressure_kpa / 9.80665, self.raw_flow_m3h, bool(self.actuators["backwash_request"])),
        }
        for index in range(1, 4):
            valve_data[f"zone_{index}_isolation"] = (
                "isolation",
                self.zone_pressures[index - 1] + self.zone_valve_dp_kpa[index - 1] / 9.80665,
                self.zone_pressures[index - 1],
                self.zone_served[index - 1],
                False,
            )
        for name, (valve_type, upstream, downstream, flow, interlocked) in valve_data.items():
            command_name = VALVE_COMMANDS[name]
            states[name] = ValveState(
                valve_type=valve_type,
                command_pct=float(self.actuators[command_name]),
                position_pct=round(self.valve_positions[name], 2),
                status=self._valve_status(name, interlocked),
                upstream_pressure_m=round(float(upstream), 3),
                downstream_pressure_m=round(float(downstream), 3),
                differential_pressure_kpa=round(max(0.0, float(upstream - downstream)) * 9.80665, 3),
                flow_m3h=round(float(flow), 3),
                travel_rate_pct_min=VALVE_TRAVEL_RATE_PCT_MIN,
                interlocked=interlocked,
            )
        prv_position = 100.0 if self.pump_discharge_pressure_m <= self.distribution_header_pressure_m + 0.5 else max(10.0, 100.0 - (self.pump_discharge_pressure_m - self.distribution_header_pressure_m) * 5.0)
        states["distribution_prv"] = ValveState(
            valve_type="prv",
            command_pct=100.0,
            position_pct=round(prv_position, 2),
            status="open" if prv_position >= 98 else "throttled",
            upstream_pressure_m=round(self.pump_discharge_pressure_m, 3),
            downstream_pressure_m=round(self.distribution_header_pressure_m, 3),
            differential_pressure_kpa=round(max(0.0, self.pump_discharge_pressure_m - self.distribution_header_pressure_m) * 9.80665, 3),
            flow_m3h=round(self.distribution_flow_m3h, 3),
            travel_rate_pct_min=VALVE_TRAVEL_RATE_PCT_MIN,
        )
        return states

    def _checkpoints(self, sensors: dict[str, SensorValue], alarms: list[Alarm]) -> list[ProcessCheckpoint]:
        alarm_codes = {alarm.code for alarm in alarms}
        specifications = [
            (1, "CP-01 Intake", "Raw-water intake", "Confirm flow, turbidity, pH, and source-water buffering", ["raw_flow_m3h", "raw_turbidity_ntu", "raw_ph", "raw_alkalinity_mg_l_caco3", "intake_gate_position_pct"]),
            (2, "CP-02 Clarifier outlet", "Settled-water channel", "Check alum dose, coagulation pH, alkalinity use, and clarification", ["clarified_turbidity_ntu", "coagulation_ph", "settled_alkalinity_mg_l_caco3"]),
            (3, "CP-03 Filter outlet", "Combined filter effluent", "Check filter loading, effluent clarity, and outlet isolation", ["filtered_turbidity_ntu", "filter_dp_kpa", "filter_outlet_valve_position_pct"]),
            (4, "CP-04 Chemical conditioning", "Post-filter chemical gallery", "Verify NaOH pH correction occurs after alum treatment and before distribution", ["finished_water_ph", "finished_alkalinity_mg_l_caco3"]),
            (5, "CP-05 Clearwell", "Post-disinfection storage", "Track free chlorine residual, baffled contact time, and calculated CT", ["clearwell_level_pct", "chlorine_residual_mg_l", "chlorine_contact_time_min", "chlorine_ct_mg_min_l"]),
            (6, "CP-06 Pump discharge", "High-lift discharge header", "Compare pump discharge with PRV-regulated header pressure", ["pump_discharge_pressure_m", "distribution_header_pressure_m", "distribution_flow_m3h"]),
            (7, "CP-07 Zone delivery", "Demand-zone boundaries", "Track pressure, isolation position, and delivered demand", ["zone_1_pressure_m", "zone_2_pressure_m", "zone_3_pressure_m", "zone_1_served_m3h", "zone_2_served_m3h", "zone_3_served_m3h"]),
        ]
        checkpoints = []
        for sequence, name, location, purpose, tags in specifications:
            if any(sensors[tag].quality != "good" for tag in tags):
                status = "unavailable"
            elif sequence == 2 and ({"COAGULATION_PH"} & alarm_codes):
                status = "critical" if any(alarm.severity == "critical" and alarm.code == "COAGULATION_PH" for alarm in alarms) else "warning"
            elif sequence == 3 and ({"FILTERED_TURBIDITY", "FILTER_DP_HIGH", "PUMP_DEADHEAD", "VALVE_COMMAND_MISMATCH"} & alarm_codes):
                status = "critical" if "PUMP_DEADHEAD" in alarm_codes else "warning"
            elif sequence == 4 and ({"FINISHED_WATER_PH", "FINISHED_ALKALINITY", "NAOH_FEED_FAILURE"} & alarm_codes):
                status = "critical" if any(alarm.severity == "critical" and alarm.code in {"FINISHED_WATER_PH", "NAOH_FEED_FAILURE"} for alarm in alarms) else "warning"
            elif sequence == 5 and ({"CLEARWELL_LEVEL", "CLEARWELL_OVERFLOW", "CHLORINE_RESIDUAL", "CHLORINE_CT", "MODEL_SENSOR_MISMATCH", "CHEMICAL_FEED_MISMATCH"} & alarm_codes):
                status = "critical" if any(alarm.severity == "critical" and alarm.code in {"CLEARWELL_LEVEL", "CLEARWELL_OVERFLOW", "CHLORINE_RESIDUAL", "CHLORINE_CT", "MODEL_SENSOR_MISMATCH", "CHEMICAL_FEED_MISMATCH"} for alarm in alarms) else "warning"
            elif sequence == 7 and (any(code.endswith("LOW_PRESSURE") for code in alarm_codes) or "VALVE_COMMAND_MISMATCH" in alarm_codes):
                status = "critical" if any(alarm.severity == "critical" and (alarm.code.endswith("LOW_PRESSURE") or alarm.code == "VALVE_COMMAND_MISMATCH") for alarm in alarms) else "warning"
            else:
                status = "normal"
            checkpoints.append(ProcessCheckpoint(sequence=sequence, name=name, location=location, purpose=purpose, status=status, sensor_tags=tags))
        return checkpoints

    def _twin_health(self, quality: str) -> TwinHealth:
        injections = set(self.active_injections())
        residuals = {
            f"zone_{index}": round(self.telemetry_zone_pressures[index - 1] - self.zone_pressures[index - 1], 3)
            for index in range(1, 4)
        }
        pressure_rmse = sqrt(sum(residual**2 for residual in residuals.values()) / len(residuals))
        flow_residual = 100.0 * abs(
            self.telemetry_distribution_flow_m3h - self.distribution_flow_m3h
        ) / max(self.distribution_flow_m3h, 1.0)
        integrity_flags: list[str] = []
        if "level_sensor_spoof_low" in injections:
            integrity_flags.append(
                f"Clearwell level differs from the process model by {abs(self.clearwell_level_pct - 32.0):.1f} percentage points"
            )
        if "chlorine_sensor_spoof_high" in injections:
            integrity_flags.append(
                f"Reported chlorine differs from the process model by {abs(2.6 - self.true_chlorine_mg_l):.2f} mg/L"
            )
        if "pump_valve_conflict" in injections:
            integrity_flags.append("Filter outlet position conflicts with its open command while the intake pump is running")
        if "zone_2_valve_forced_closed" in injections:
            integrity_flags.append("Zone 2 field position conflicts with its commanded position")
        if "chlorine_overfeed" in injections:
            integrity_flags.append("Delivered chlorine dose conflicts with the PLC dose command")
        if quality == "stale":
            fit_status = "stale"
            age_seconds = 1800.0
        elif integrity_flags:
            fit_status = "poor"
            age_seconds = 0.0
        elif pressure_rmse > 2.0 or flow_residual > 5.0:
            fit_status = "poor"
            age_seconds = 0.0
        elif pressure_rmse > 1.0 or flow_residual > 2.0:
            fit_status = "warning"
            age_seconds = 0.0
        else:
            fit_status = "good"
            age_seconds = 0.0
        return TwinHealth(
            last_model_update=self.simulation_time,
            telemetry_age_seconds=age_seconds,
            pressure_rmse_m=round(pressure_rmse, 3),
            flow_residual_pct=round(flow_residual, 3),
            zone_pressure_residuals_m=residuals,
            fit_status=fit_status,
            integrity_flags=integrity_flags,
        )

    def snapshot(self) -> PlantSnapshot:
        with self.lock:
            mods = self._last_modifiers
            injections = set(self.active_injections())
            quality = str(mods.get("sensor_quality", "good"))
            observed_chlorine = self.true_chlorine_mg_l + float(mods.get("chlorine_sensor_bias", 0.0))
            observed_clearwell_level = self.clearwell_level_pct
            if "chlorine_sensor_spoof_high" in injections:
                observed_chlorine = 2.6
            if "level_sensor_spoof_low" in injections:
                observed_clearwell_level = 32.0
            sensor_data = {
                "water_balance_error_m3": (self.water_balance_error_m3, "m3"),
                "elevated_exchange_m3h": (self.elevated_exchange_m3h, "m3/h"),
                "unserved_water_m3h": (max(0.0, sum(self.zone_demands)-sum(self.zone_served)), "m3/h"),
                "raw_flow_m3h": (self.raw_flow_m3h, "m3/h"),
                "raw_turbidity_ntu": (self.raw_turbidity_ntu, "NTU"),
                "raw_ph": (self.raw_ph, "pH"),
                "raw_alkalinity_mg_l_caco3": (self.raw_alkalinity_mg_l_caco3, "mg/L as CaCO3"),
                "coagulation_ph": (self.coagulation_ph, "pH"),
                "settled_alkalinity_mg_l_caco3": (self.settled_alkalinity_mg_l_caco3, "mg/L as CaCO3"),
                "finished_water_ph": (self.finished_water_ph, "pH"),
                "finished_alkalinity_mg_l_caco3": (self.finished_alkalinity_mg_l_caco3, "mg/L as CaCO3"),
                "water_temperature_c": (self.water_temperature_c, "degC"),
                "clarified_turbidity_ntu": (self.clarified_turbidity_ntu, "NTU"),
                "filtered_turbidity_ntu": (self.filtered_turbidity_ntu, "NTU"),
                "filter_dp_kpa": (self.filter_dp_kpa, "kPa"),
                "clearwell_level_pct": (observed_clearwell_level, "%"),
                "clearwell_level_model_pct": (self.clearwell_level_pct, "%"),
                "clearwell_overflow_m3h": (self.clearwell_overflow_m3h, "m3/h"),
                "chlorine_residual_mg_l": (observed_chlorine, "mg/L"),
                "chlorine_model_estimate_mg_l": (self.true_chlorine_mg_l, "mg/L"),
                "chlorine_dose_actual_mg_l": (self.actual_chlorine_dose_mg_l, "mg/L"),
                "coagulant_dose_actual_mg_l": (self.actual_coagulant_dose_mg_l, "mg/L"),
                "chemical_feed_flow_proof": (1.0 if self.chemical_feed_flow_proof else 0.0, "bool"),
                "chlorine_contact_time_min": (self.chlorine_contact_time_min, "min"),
                "chlorine_ct_mg_min_l": (self.chlorine_ct_mg_min_l, "mg-min/L"),
                "hocl_fraction_pct": (self.hocl_fraction_pct, "%"),
                "chlorine_feed_runtime_min": (self.chlorine_feed_runtime_min, "min"),
                "alum_feed_runtime_min": (self.alum_feed_runtime_min, "min"),
                "naoh_feed_runtime_min": (self.naoh_feed_runtime_min, "min"),
                "naoh_dose_actual_mg_l": (self.actual_naoh_dose_mg_l, "mg/L"),
                "alum_solution_flow_lph": (self.alum_solution_flow_lph, "L/h"),
                "naoh_solution_flow_lph": (self.naoh_solution_flow_lph, "L/h"),
                "hypochlorite_solution_flow_lph": (self.hypochlorite_solution_flow_lph, "L/h"),
                "distribution_flow_m3h": (self.telemetry_distribution_flow_m3h, "m3/h"),
                "elevated_tank_level_pct": (self.elevated_tank_level_pct, "%"),
                "zone_1_demand_m3h": (self.zone_demands[0], "m3/h"),
                "zone_2_demand_m3h": (self.zone_demands[1], "m3/h"),
                "zone_3_demand_m3h": (self.zone_demands[2], "m3/h"),
                "zone_1_pressure_m": (self.telemetry_zone_pressures[0], "m"),
                "zone_2_pressure_m": (self.telemetry_zone_pressures[1], "m"),
                "zone_3_pressure_m": (self.telemetry_zone_pressures[2], "m"),
                "leak_flow_m3h": (self.leak_flow_m3h, "m3/h"),
                "energy_kw": (self.energy_kw, "kW"),
                "intake_upstream_pressure_m": (self.intake_upstream_pressure_m, "m"),
                "intake_downstream_pressure_m": (self.intake_downstream_pressure_m, "m"),
                "filter_inlet_pressure_kpa": (self.filter_inlet_pressure_kpa, "kPa"),
                "filter_outlet_pressure_kpa": (self.filter_outlet_pressure_kpa, "kPa"),
                "pump_discharge_pressure_m": (self.pump_discharge_pressure_m, "m"),
                "pump_deadhead_pressure_kpa": (self.pump_deadhead_pressure_kpa, "kPa"),
                "distribution_header_pressure_m": (self.distribution_header_pressure_m, "m"),
                "intake_gate_position_pct": (self.valve_positions["intake_gate"], "%"),
                "filter_outlet_valve_position_pct": (self.valve_positions["filter_outlet"], "%"),
                "zone_1_isolation_valve_position_pct": (self.valve_positions["zone_1_isolation"], "%"),
                "zone_2_isolation_valve_position_pct": (self.valve_positions["zone_2_isolation"], "%"),
                "zone_3_isolation_valve_position_pct": (self.valve_positions["zone_3_isolation"], "%"),
                "zone_1_valve_dp_kpa": (self.zone_valve_dp_kpa[0], "kPa"),
                "zone_2_valve_dp_kpa": (self.zone_valve_dp_kpa[1], "kPa"),
                "zone_3_valve_dp_kpa": (self.zone_valve_dp_kpa[2], "kPa"),
                "zone_1_served_m3h": (self.zone_served[0], "m3/h"),
                "zone_2_served_m3h": (self.zone_served[1], "m3/h"),
                "zone_3_served_m3h": (self.zone_served[2], "m3/h"),
            }
            sensor_data.update(self._chemical_sensor_data())
            sensor_data.update({"aux_"+tag.lower().replace("-", "_")+"_feedback_pct": (d["feedback_pct"], "%") for tag,d in self.operations.devices.items()})
            sensors = {
                key: SensorValue(value=round(float(reading), 3), unit=unit, quality=quality, timestamp=self.simulation_time)
                for key, (reading, unit) in sensor_data.items()
            }
            equipment = {
                "intake_pump": EquipmentState(running=self.actual_intake_speed_pct > 0, speed_pct=self.actual_intake_speed_pct, flow_m3h=self.raw_flow_m3h),
                "high_lift_pump": EquipmentState(enabled=bool(mods["pump_available"]), running=self.actual_high_lift_speed_pct > 0 and bool(mods["pump_available"]), speed_pct=self.actual_high_lift_speed_pct, flow_m3h=self.distribution_flow_m3h, efficiency_pct=float(mods["pump_efficiency_pct"])),
                "booster_pump": EquipmentState(running=float(self.actuators["booster_pump_speed_pct"]) > 0, speed_pct=float(self.actuators["booster_pump_speed_pct"])),
                "filter": EquipmentState(running=not bool(self.actuators["backwash_request"]), efficiency_pct=max(0, 100 - self.filtered_turbidity_ntu * 25)),
                "alum_feed_pump": EquipmentState(running=self.actual_coagulant_dose_mg_l > 0),
                "chlorine_feed_pump": EquipmentState(running=self.actual_chlorine_dose_mg_l > 0),
                "naoh_feed_pump": EquipmentState(enabled=bool(mods["naoh_available"]), running=self.actual_naoh_dose_mg_l > 0),
            }
            for chemical, tank in self.chemical_tanks.items():
                equipment[f"{chemical}_transfer_pump"] = EquipmentState(
                    running=bool(tank["refilling"]),
                    flow_m3h=float(tank["transfer_lpm"]) * 0.06 if tank["refilling"] else 0.0,
                )
            alarms = self._alarms(sensors)
            safety_state = "critical" if any(alarm.severity == "critical" for alarm in alarms) else "warning" if alarms else "normal"
            forecast = [round(228.0 * demand_multiplier(self.minute + offset, self.scenario), 1) for offset in range(0, 65, 5)]
            return PlantSnapshot(
                simulation_time=self.simulation_time,
                elapsed_minutes=self.minute,
                simulation_speed=self.speed,
                running=self.running,
                scenario=self.scenario,
                controller_mode=self.controller_mode,
                sensors=sensors,
                equipment=equipment,
                operations=self.operations.snapshot(self),
                actuators=self.actuators.copy(),
                valves=self._valve_states(),
                checkpoints=self._checkpoints(sensors, alarms),
                twin_health=self._twin_health(quality),
                active_alarms=alarms,
                forecast_demand_m3h=forecast,
                recent_trends={key: list(values) for key, values in self.histories.items()},
                safety_state=safety_state,
                emergency_stop=bool(self.actuators["emergency_stop"]),
                active_injections=sorted(injections),
                note=f"Illustrative simulation values. Not regulatory limits. Hydraulics: {self.hydraulic_engine}.",
            )

    def _alarms(self, sensors: dict[str, SensorValue]) -> list[Alarm]:
        alarms: list[Alarm] = [Alarm(**a, started_at=self.simulation_time) for a in self.operations.alarms()]
        injections = set(self.active_injections())
        checks = [
            ("clearwell_level_pct", "CLEARWELL_LEVEL", "Clearwell level outside the illustrative operating band"),
            ("elevated_tank_level_pct", "ELEVATED_TANK_LEVEL", "Elevated tank level outside the illustrative operating band"),
            ("chlorine_residual_mg_l", "CHLORINE_RESIDUAL", "Chlorine residual outside the illustrative operating band"),
            ("filtered_turbidity_ntu", "FILTERED_TURBIDITY", "Filtered turbidity above the illustrative operating band"),
            ("coagulation_ph", "COAGULATION_PH", "Coagulation pH outside the illustrative process band"),
            ("finished_water_ph", "FINISHED_WATER_PH", "Finished-water pH outside the illustrative operating band"),
            ("finished_alkalinity_mg_l_caco3", "FINISHED_ALKALINITY", "Finished-water alkalinity outside the illustrative operating band"),
            ("chlorine_ct_mg_min_l", "CHLORINE_CT", "Calculated chlorine CT below the illustrative study benchmark"),
        ]
        for sensor, code, message in checks:
            low, high = LIMITS[sensor]
            reading = sensors[sensor].value
            if reading < low or reading > high:
                severity = "critical" if reading < low * 0.7 or reading > high * 1.35 else "warning"
                alarms.append(Alarm(code=code, severity=severity, message=message, started_at=self.simulation_time))
        for index in range(1, 4):
            pressure = sensors[f"zone_{index}_pressure_m"].value
            if pressure < LIMITS["zone_pressure_m"][0]:
                alarms.append(Alarm(code=f"ZONE_{index}_LOW_PRESSURE", severity="critical" if pressure < 15 else "warning", message=f"Zone {index} pressure is low", started_at=self.simulation_time))
            if self.valve_positions[f"zone_{index}_isolation"] < 30:
                alarms.append(Alarm(code=f"ZONE_{index}_VALVE_RESTRICTED", severity="warning", message=f"Zone {index} isolation valve is nearly closed", started_at=self.simulation_time))
        if sensors["filter_dp_kpa"].value > 55:
            alarms.append(Alarm(code="FILTER_DP_HIGH", severity="warning", message="Filter differential pressure is high", started_at=self.simulation_time))
        if any(sensor.quality != "good" for sensor in sensors.values()):
            alarms.append(Alarm(code="SENSOR_QUALITY", severity="warning", message=f"Sensor data quality is {next(iter(sensors.values())).quality}", started_at=self.simulation_time))
        if bool(self.actuators["emergency_stop"]):
            alarms.append(Alarm(code="EMERGENCY_STOP", severity="critical", message="Emergency stop is active", started_at=self.simulation_time))
        if not bool(self._last_modifiers.get("naoh_available", True)):
            alarms.append(Alarm(code="NAOH_FEED_FAILURE", severity="critical", message="NaOH feed command has no confirmed chemical delivery", started_at=self.simulation_time))
        if injections:
            alarms.append(Alarm(code="CONTROL_OVERRIDE_ACTIVE", severity="critical", message="An isolated lab fault injection is overriding simulated process behavior", started_at=self.simulation_time))
        if self.clearwell_level_pct >= 98.0 or self.clearwell_overflow_m3h > 0.0:
            alarms.append(Alarm(code="CLEARWELL_OVERFLOW", severity="critical", message="Physical clearwell level is at the overflow point", started_at=self.simulation_time))
        if "level_sensor_spoof_low" in injections or "chlorine_sensor_spoof_high" in injections:
            alarms.append(Alarm(code="MODEL_SENSOR_MISMATCH", severity="critical", message="A reported sensor value conflicts with the independent process-model estimate", started_at=self.simulation_time))
        if "pump_valve_conflict" in injections:
            alarms.append(Alarm(code="PUMP_DEADHEAD", severity="critical", message="Intake pump is running against a forced-closed filter outlet valve", started_at=self.simulation_time))
            alarms.append(Alarm(code="VALVE_COMMAND_MISMATCH", severity="critical", message="Filter outlet field position does not follow its PLC command", started_at=self.simulation_time))
        if "zone_2_valve_forced_closed" in injections:
            alarms.append(Alarm(code="VALVE_COMMAND_MISMATCH", severity="critical", message="Zone 2 valve field position does not follow its PLC command", started_at=self.simulation_time))
        if "chlorine_overfeed" in injections:
            alarms.append(Alarm(code="CHEMICAL_FEED_MISMATCH", severity="critical", message="Delivered chlorine dose is higher than the PLC command", started_at=self.simulation_time))
        commanded_chemical = any(float(self.actuators[name]) > 0.05 for name in ("coagulant_dose_mg_l", "chlorine_dose_mg_l", "naoh_dose_mg_l"))
        if commanded_chemical and not self.chemical_feed_flow_proof:
            alarms.append(Alarm(code="CHEMICAL_FLOW_INTERLOCK", severity="warning", message="Chemical feed is inhibited because treatment flow proof is absent", started_at=self.simulation_time))
        for chemical in ("alum", "naoh", "hypochlorite"):
            bulk_level = sensors[f"{chemical}_bulk_tank_level_pct"].value
            day_level = sensors[f"{chemical}_day_tank_level_pct"].value
            if bulk_level < 10.0:
                alarms.append(Alarm(code=f"{chemical.upper()}_BULK_LOW", severity="warning", message=f"{chemical.title()} bulk storage is low", started_at=self.simulation_time))
            if day_level < 20.0:
                alarms.append(Alarm(code=f"{chemical.upper()}_DAY_TANK_LOW", severity="critical", message=f"{chemical.title()} day tank is low", started_at=self.simulation_time))
        return alarms
