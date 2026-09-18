from __future__ import annotations

from shared.exercise import ExerciseRecorder
from shared.operations import OperationsModel
from math import isfinite

from datetime import datetime, timedelta, timezone
from math import exp, pi, sin
from threading import RLock

from .models import AiDecision, GateResult, LabSnapshot


GRID_SCENARIOS = [
    {"id": "normal_dispatch", "name": "Normal dispatch", "description": "Daily demand and renewable production vary gradually."},
    {"id": "evening_peak", "name": "Evening demand peak", "description": "System demand increases sharply after minute 30."},
    {"id": "generator_trip", "name": "Gas generator trip", "description": "The largest dispatchable generator trips after minute 30."},
    {"id": "line_trip", "name": "Central to industrial line trip", "description": "A transmission breaker opens after minute 30."},
    {"id": "solar_ramp_loss", "name": "Rapid solar loss", "description": "Cloud cover removes most solar output after minute 30."},
    {"id": "frequency_sensor_spoof", "name": "Frequency sensor spoof", "description": "The control-room signal remains near 60 Hz while model frequency falls."},
    {"id": "industrial_overload", "name": "Industrial transformer overload", "description": "Industrial demand rises beyond normal transformer loading."},
]


LINES = [
    {"id": "L-NC", "source": 0, "target": 1, "name": "North to Central", "x": 0.10, "capacity": 650.0},
    {"id": "L-CM", "source": 1, "target": 2, "name": "Central to Metro", "x": 0.08, "capacity": 500.0},
    {"id": "L-CI", "source": 1, "target": 3, "name": "Central to Industrial", "x": 0.09, "capacity": 460.0},
    {"id": "L-CS", "source": 1, "target": 4, "name": "Central to South", "x": 0.12, "capacity": 360.0},
    {"id": "L-SM", "source": 4, "target": 2, "name": "South to Metro", "x": 0.10, "capacity": 300.0},
    {"id": "L-NI", "source": 0, "target": 3, "name": "North to Industrial", "x": 0.14, "capacity": 300.0},
]


def solve_linear(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        if abs(divisor) < 1e-10:
            raise ValueError("Grid admittance matrix is singular")
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [value - factor * pivot_value for value, pivot_value in zip(augmented[row], augmented[column])]
    return [row[-1] for row in augmented]


class GridSimulator:
    """Five-bus DC power-flow and frequency-response training model."""

    def __init__(self) -> None:
        self.lock = RLock()
        self.reset()

    def reset(self, scenario: str = "normal_dispatch", speed: int = 10, mode: str = "advisory") -> None:
        with self.lock:
            self.operations = OperationsModel("grid")
            self.minute = 0
            self.simulation_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
            self.running = False
            self.speed = speed
            self.scenario = scenario if scenario in {item["id"] for item in GRID_SCENARIOS} else "normal_dispatch"
            self.controller_mode = mode
            self.frequency_hz = 60.0
            self.true_frequency_hz = 60.0
            self.loads = [55.0, 105.0, 390.0, 290.0, 160.0]
            self.demand_mw = 1000.0
            self.served_load_mw = 1000.0
            self.unserved_load_mw = 0.0
            self.wind_available_mw = 180.0
            self.solar_available_mw = 120.0
            self.reserve_output_mw = 0.0
            self.operations_demand_response_mw = 0.0
            self.gas_output_mw = 460.0
            self.hydro_output_mw = 240.0
            self.wind_output_mw = 180.0
            self.solar_output_mw = 120.0
            self.battery_output_mw = 0.0
            self.battery_soc_pct = 62.0
            self.reactive_margin_mvar = 180.0
            self.bus_voltages_pu = [1.02, 1.01, 0.99, 0.985, 1.005]
            self.line_results: list[dict[str, float | str | bool]] = []
            self.controls: dict[str, float | bool | str] = {
                "gas_dispatch_mw": 460.0,
                "hydro_dispatch_mw": 240.0,
                "battery_dispatch_mw": 0.0,
                "capacitor_support_mvar": 20.0,
                "transformer_tap_pct": 0.0,
                "demand_response_mw": 0.0,
                "L-NC_breaker_closed": True,
                "L-CM_breaker_closed": True,
                "L-CI_breaker_closed": True,
                "L-CS_breaker_closed": True,
                "L-SM_breaker_closed": True,
                "L-NI_breaker_closed": True,
            }
            self.ai_lease = None
            self.ai_decision: AiDecision | None = None
            self._run_power_flow()
            self.exercise = ExerciseRecorder("grid", self.scenario)
            self.exercise.capture(self.snapshot(), self.minute)

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

    def _conditions(self) -> dict[str, float | bool]:
        day_hour = (self.minute % 1440) / 60.0
        demand_factor = 0.92 + 0.08 * sin((day_hour - 7.0) / 24.0 * 2.0 * pi)
        solar_factor = max(0.0, sin((day_hour - 6.0) / 12.0 * pi))
        wind_factor = 0.75 + 0.18 * sin((day_hour + 2.0) / 8.0 * 2.0 * pi)
        state: dict[str, float | bool] = {
            "demand_factor": demand_factor,
            "solar_factor": solar_factor,
            "wind_factor": wind_factor,
            "gas_available": True,
            "forced_line_trip": False,
            "frequency_sensor_spoof": False,
            "industrial_multiplier": 1.0,
        }
        if self.scenario == "evening_peak" and self.minute >= 30:
            state["demand_factor"] = float(state["demand_factor"]) + 0.32 * (1.0 - exp(-(self.minute - 30) / 12.0))
        if self.scenario == "generator_trip" and self.minute >= 30:
            state["gas_available"] = False
        if self.scenario == "line_trip" and self.minute >= 30:
            state["forced_line_trip"] = True
        if self.scenario == "solar_ramp_loss" and self.minute >= 30:
            state["solar_factor"] = 0.9 * max(0.08, exp(-(self.minute - 30) / 5.0))
        elif self.scenario == "solar_ramp_loss":
            state["solar_factor"] = 0.9
        if self.scenario == "frequency_sensor_spoof" and self.minute >= 30:
            state["frequency_sensor_spoof"] = True
        if self.scenario == "industrial_overload" and self.minute >= 30:
            state["industrial_multiplier"] = 1.75
        if self.operations.active("extreme_demand"):
            state["demand_factor"] *= 1.65
        return state

    def _baseline_control(self, state: dict[str, float | bool]) -> None:
        if bool(state["forced_line_trip"]):
            self.controls["L-CI_breaker_closed"] = False
        if self.true_frequency_hz < 59.75:
            self.controls["battery_dispatch_mw"] = min(100.0, float(self.controls["battery_dispatch_mw"]) + 35.0)
            self.controls["hydro_dispatch_mw"] = min(320.0, float(self.controls["hydro_dispatch_mw"]) + 30.0)
        elif self.true_frequency_hz > 60.15:
            self.controls["battery_dispatch_mw"] = max(-80.0, float(self.controls["battery_dispatch_mw"]) - 25.0)
        if min(self.bus_voltages_pu) < 0.95:
            self.controls["capacitor_support_mvar"] = min(120.0, float(self.controls["capacitor_support_mvar"]) + 20.0)
            self.controls["transformer_tap_pct"] = min(7.5, float(self.controls["transformer_tap_pct"]) + 1.25)

    def _step(self) -> None:
        self.minute += 1
        if self.ai_lease and self.minute >= self.ai_lease["expires_minute"]:
            self._release_ai_lease()
        self.simulation_time += timedelta(minutes=1)
        self.operations.tick(self.minute, self.exercise)
        state = self._conditions()
        self._baseline_control(state)

        base_loads = [55.0, 105.0, 390.0, 290.0 * float(state["industrial_multiplier"]), 160.0]
        factor = float(state["demand_factor"])
        loads = [load * factor for load in base_loads]
        demand_response = min(sum(loads) * 0.12, max(0.0, float(self.controls["demand_response_mw"])))
        loads[2] = max(0.0, loads[2] - demand_response * 0.65)
        loads[3] = max(0.0, loads[3] - demand_response * 0.35)
        reductions = [min(loads[2],60*self.operations.fraction("DR-601")), min(loads[3],50*self.operations.fraction("DR-602"))]
        loads[2] -= reductions[0]
        loads[3] -= reductions[1]
        self.operations_demand_response_mw = sum(reductions)
        self.loads = loads
        self.demand_mw = sum(loads)

        self.wind_available_mw = 220.0 * float(state["wind_factor"])
        self.solar_available_mw = 260.0 * float(state["solar_factor"])
        self.wind_output_mw += (self.wind_available_mw - self.wind_output_mw) * 0.32
        self.solar_output_mw += (self.solar_available_mw - self.solar_output_mw) * 0.38
        gas_target = float(self.controls["gas_dispatch_mw"]) if bool(state["gas_available"]) else 0.0
        hydro_target = float(self.controls["hydro_dispatch_mw"])
        battery_target = float(self.controls["battery_dispatch_mw"])
        self.reserve_output_mw = 150*self.operations.fraction("GT-301") + 50*self.operations.fraction("HY-302")
        if self.operations.active("regional_supply_shortfall"):
            gas_target *= .25
            hydro_target *= .5
        if bool(state["frequency_sensor_spoof"]):
            gas_target = min(gas_target, 250.0)
            hydro_target = min(hydro_target, 150.0)
            battery_target = -100.0
        if self.battery_soc_pct < 10.0:
            battery_target = min(0.0, battery_target)
        if self.battery_soc_pct > 95.0:
            battery_target = max(0.0, battery_target)
        self.gas_output_mw += max(-35.0, min(35.0, gas_target - self.gas_output_mw))
        self.hydro_output_mw += max(-45.0, min(45.0, hydro_target - self.hydro_output_mw))
        self.battery_output_mw += max(-50.0, min(50.0, battery_target - self.battery_output_mw))
        # 400 MWh store, 95% one-way efficiency, hard 10–95% usable energy bounds.
        discharge_limit = max(0.0, (self.battery_soc_pct - 10.0) / 100 * 400 * 60 * 0.95)
        charge_limit = max(0.0, (95.0 - self.battery_soc_pct) / 100 * 400 * 60 / 0.95)
        self.battery_output_mw = max(-charge_limit, min(discharge_limit, self.battery_output_mw))

        generation = self.gas_output_mw + self.hydro_output_mw + self.reserve_output_mw + self.wind_output_mw + self.solar_output_mw + self.battery_output_mw
        imbalance = generation - self.demand_mw
        self.true_frequency_hz += imbalance / 800.0 * 0.22 - (self.true_frequency_hz - 60.0) * 0.24
        self.true_frequency_hz = max(57.0, min(62.0, self.true_frequency_hz))
        self.frequency_hz = 60.01 if bool(state["frequency_sensor_spoof"]) else self.true_frequency_hz
        self._run_power_flow()
        energy_rate = self.battery_output_mw / 0.95 if self.battery_output_mw >= 0 else self.battery_output_mw * 0.95
        self.battery_soc_pct -= energy_rate / 400 * 100 / 60


    def _run_power_flow(self) -> None:
        loads = getattr(self, "loads", [55.0, 105.0, 390.0, 290.0, 160.0])
        generation = [self.gas_output_mw + self.wind_output_mw, self.hydro_output_mw + self.reserve_output_mw,
                      0.0, 0.0, self.solar_output_mw + self.battery_output_mw]
        adjacency = {i: set() for i in range(5)}
        active_lines = [line for line in LINES if self.controls[f"{line['id']}_breaker_closed"]]
        for line in active_lines:
            adjacency[line["source"]].add(line["target"])
            adjacency[line["target"]].add(line["source"])
        remaining, components = set(range(5)), []
        while remaining:
            pending, component = [min(remaining)], []
            while pending:
                bus = pending.pop()
                if bus not in remaining:
                    continue
                remaining.remove(bus)
                component.append(bus)
                pending.extend(sorted(adjacency[bus] & remaining))
            components.append(sorted(component))
        angles, served, injections = [0.0]*5, [0.0]*5, [0.0]*5
        self.islands, self.import_mw, self.curtailed_generation_mw = [], 0.0, 0.0
        base_mva = 100.0
        for component in components:
            demand = sum(loads[i] for i in component)
            supply = sum(generation[i] for i in component)
            import_limit = 30.0 if self.operations.active("regional_supply_shortfall") else 120.0
            interchange = max(-120.0, min(import_limit, demand - supply)) if 0 in component else 0.0
            # Imports exist only at B1. Local charging is curtailed before customer demand.
            positive = sum(max(0.0, generation[i]) for i in component)
            charging = sum(max(0.0, -generation[i]) for i in component)
            available = max(0.0, positive + interchange)
            actual_charging = min(charging, max(0.0, available - demand))
            if 4 in component and charging > actual_charging:
                self.battery_output_mw += charging - actual_charging
            served_total = min(demand, max(0.0, available - actual_charging))
            excess = max(0.0, positive + interchange - actual_charging - served_total)
            if 4 in component and self.battery_output_mw > 0.0:
                reduced_discharge = min(excess, self.battery_output_mw)
                self.battery_output_mw -= reduced_discharge
                generation[4] -= reduced_discharge
                positive -= reduced_discharge
                excess -= reduced_discharge
            for i in component:
                served[i] = loads[i] * served_total / demand if demand else 0.0
                gen = max(0.0, generation[i]) * (1 - excess / positive) if positive else 0.0
                charge = max(0.0, -generation[i]) * actual_charging / charging if charging else 0.0
                injections[i] = gen - charge - served[i] + (interchange if i == 0 else 0.0)
            self.import_mw += interchange
            self.curtailed_generation_mw += excess
            reference, unknowns = component[0], component[1:]
            matrix = [[0.0]*5 for _ in range(5)]
            for line in active_lines:
                x, y, susceptance = line["source"], line["target"], 1.0 / line["x"]
                matrix[x][x] += susceptance
                matrix[y][y] += susceptance
                matrix[x][y] -= susceptance
                matrix[y][x] -= susceptance
            if unknowns:
                solution = solve_linear([[matrix[i][j] for j in unknowns] for i in unknowns],
                                        [injections[i]/base_mva for i in unknowns])
                for i, angle in zip(unknowns, solution):
                    angles[i] = angle
            self.islands.append(dict(buses=[f"B{i+1}" for i in component], reference_bus=f"B{reference+1}",
                demand_mw=round(demand, 3), served_mw=round(served_total, 3), import_mw=round(interchange, 3),
                energized=available > 0.001, balance_residual_mw=round(sum(injections[i] for i in component), 8)))
        self.served_by_bus = served
        self.served_load_mw = sum(served)
        self.unserved_load_mw = max(0.0, sum(loads) - self.served_load_mw)
        results = []
        bus_stress = [0.0] * 5
        for line in LINES:
            closed = bool(self.controls[f"{line['id']}_breaker_closed"])
            flow = (angles[int(line["source"])] - angles[int(line["target"])]) / float(line["x"]) * base_mva if closed else 0.0
            cooling = min(self.operations.fraction("TF-401"), self.operations.fraction("TF-402"))
            rating = float(line["capacity"]) * (.75+.25*cooling) * (.85 if self.operations.active("extreme_demand") else 1.0)
            loading = abs(flow) / rating * 100.0 if closed else 0.0
            results.append({**line, "effective_capacity_mw": round(rating,2), "flow_mw": round(flow, 2), "loading_pct": round(loading, 2), "closed": closed})
            bus_stress[int(line["source"])] = max(bus_stress[int(line["source"])], loading)
            bus_stress[int(line["target"])] = max(bus_stress[int(line["target"])], loading)
        capacitor = float(self.controls["capacitor_support_mvar"]) + 80*self.operations.fraction("SC-501")+40*self.operations.fraction("CB-502")
        tap = float(self.controls["transformer_tap_pct"])
        self.bus_voltages_pu = [
            max(0.82, min(1.12, 1.025 + tap / 100.0 + capacitor / 2400.0 - stress * 0.00042 - max(0.0, load - 260.0) * 0.00008))
            for stress, load in zip(bus_stress, loads)
        ]
        for island in self.islands:
            if not island["energized"]:
                for bus in island["buses"]:
                    self.bus_voltages_pu[int(bus[1:])-1] = 0.0
        self.line_results = results
        self.reactive_margin_mvar = max(0.0, 220.0 + capacitor - sum(max(0.0, 0.98 - voltage) * 800.0 for voltage in self.bus_voltages_pu))

    def _alarms(self) -> list[dict[str, str]]:
        alarms: list[dict[str, str]] = self.operations.alarms()
        reported = self.frequency_hz
        true = self.true_frequency_hz
        checks = [
            (len(self.islands) > 1, "NETWORK_ISLANDED", "Network has electrically disconnected islands; inspect local served demand", "critical"),
            (true < 59.5 or true > 60.5, "FREQUENCY_DEVIATION", "System frequency is outside the illustrative secure band", "critical"),
            (min(self.bus_voltages_pu) < 0.92 or max(self.bus_voltages_pu) > 1.08, "BUS_VOLTAGE", "A bus voltage is outside the illustrative protection band", "critical"),
            (self.unserved_load_mw > 1.0, "UNSERVED_LOAD", "Available generation and import cannot serve all demand", "critical"),
            (self.battery_soc_pct < 15.0, "BATTERY_SOC_LOW", "Battery state of charge is low", "warning"),
        ]
        for active, code, message, severity in checks:
            if active:
                alarms.append({"code": code, "message": message, "severity": severity})
        for line in self.line_results:
            if not bool(line["closed"]):
                alarms.append({"code": f"{line['id']}_OPEN", "message": f"{line['name']} breaker is open", "severity": "warning"})
            elif float(line["loading_pct"]) > 100.0:
                alarms.append({"code": f"{line['id']}_OVERLOAD", "message": f"{line['name']} is overloaded", "severity": "critical" if float(line["loading_pct"]) > 120.0 else "warning"})
        if abs(reported - true) > 0.15:
            alarms.append({"code": "FREQUENCY_MODEL_MISMATCH", "message": "Reported frequency conflicts with the dynamic model estimate", "severity": "critical"})
        return alarms

    def _gate(self, changes: dict[str, float | bool]) -> GateResult:
        reasons: list[str] = []
        if any(alarm["severity"] == "critical" for alarm in self._alarms()):
            reasons.append("Grid is in a critical state")
        allowed = {
            "gas_dispatch_mw": (0.0, 650.0, 80.0),
            "hydro_dispatch_mw": (80.0, 320.0, 60.0),
            "battery_dispatch_mw": (-100.0, 100.0, 60.0),
            "capacitor_support_mvar": (0.0, 120.0, 40.0),
            "transformer_tap_pct": (-7.5, 7.5, 2.5),
            "demand_response_mw": (0.0, 120.0, 50.0),
        }
        for name, value in changes.items():
            if name not in allowed:
                reasons.append(f"AI is not authorized to change {name}")
                continue
            low, high, maximum_step = allowed[name]
            if isinstance(value, bool) or not isfinite(float(value)) or not low <= float(value) <= high:
                reasons.append(f"{name} is outside the permitted demonstration range")
            if abs(float(value) - float(self.controls[name])) > maximum_step:
                reasons.append(f"{name} exceeds the permitted decision step")
        return GateResult(status="rejected" if reasons else "accepted", reasons=reasons)

    def run_ai_cycle(self) -> AiDecision:
        generation_without_battery = self.gas_output_mw + self.hydro_output_mw + self.reserve_output_mw + self.wind_output_mw + self.solar_output_mw
        shortfall = self.demand_mw - generation_without_battery
        battery = max(-80.0, min(100.0, shortfall * 0.45))
        residual = shortfall - battery
        gas = max(0.0, min(650.0, self.gas_output_mw + residual * 0.65))
        capacitor = min(120.0, max(0.0, float(self.controls["capacitor_support_mvar"]) + max(0.0, 0.98 - min(self.bus_voltages_pu)) * 700.0))
        demand_response = 0.0 if self.true_frequency_hz >= 59.7 else min(120.0, (59.7 - self.true_frequency_hz) * 240.0)
        changes = {
            "gas_dispatch_mw": round(gas, 1),
            "battery_dispatch_mw": round(battery, 1),
            "capacitor_support_mvar": round(capacitor, 1),
            "demand_response_mw": round(demand_response, 1),
        }
        return self.apply_ai_proposal(
            changes,
            confidence=0.87 if not self._alarms() else 0.44,
            objective="Balance supply and demand while maintaining frequency and voltage",
            explanation="The fallback policy adjusts dispatch, storage, reactive support and demand response. Protection remains independent.",
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
            breaker_changes = {name: value for name, value in changes.items() if name.endswith("_breaker_closed")}
            dispatch_changes = {name: value for name, value in changes.items() if name not in breaker_changes}
            gate = self._gate(dispatch_changes)
            for name, value in breaker_changes.items():
                if name not in self.controls or not isinstance(value, bool):
                    gate.reasons.append(f"Unknown breaker or non-boolean command: {name}")
                    gate.status = "rejected"
            if breaker_changes and any(alarm["severity"] == "critical" for alarm in self._alarms()):
                gate.reasons.append("Breaker operation is blocked while the grid is critical")
                gate.status = "rejected"
            if gate.status == "accepted":
                for name, value in changes.items():
                    if name in self.controls:
                        self.controls[name] = value
                gate.applied = changes.copy()
                self._run_power_flow()
            if gate.status == "accepted" and self.ai_lease:
                for name in changes:
                    self.ai_lease["previous"].pop(name, None)
            self.exercise.event(self.minute, "manual", gate.status, changes=changes, reasons=gate.reasons)
            return gate

    def snapshot(self) -> LabSnapshot:
        with self.lock:
            alarms = self._alarms()
            safety = "critical" if any(item["severity"] == "critical" for item in alarms) else "warning" if alarms else "normal"

            def sensor(value: float, unit: str, quality: str = "good") -> dict[str, float | str]:
                return {"value": round(value, 3), "unit": unit, "quality": quality}

            generation = self.gas_output_mw + self.hydro_output_mw + self.reserve_output_mw + self.wind_output_mw + self.solar_output_mw + self.battery_output_mw
            sensors = {
                "reserve_generation_mw": sensor(self.reserve_output_mw, "MW"),
                "auxiliary_demand_response_mw": sensor(self.operations_demand_response_mw, "MW"),
                "frequency_hz": sensor(self.frequency_hz, "Hz", "suspect" if abs(self.frequency_hz-self.true_frequency_hz)>0.15 else "good"),
                "frequency_model_hz": sensor(self.true_frequency_hz, "Hz"),
                "system_demand_mw": sensor(self.demand_mw, "MW"),
                "total_generation_mw": sensor(generation, "MW"),
                "served_load_mw": sensor(self.served_load_mw, "MW"),
                "unserved_load_mw": sensor(self.unserved_load_mw, "MW"),
                "gas_generation_mw": sensor(self.gas_output_mw, "MW"),
                "hydro_generation_mw": sensor(self.hydro_output_mw, "MW"),
                "wind_generation_mw": sensor(self.wind_output_mw, "MW"),
                "solar_generation_mw": sensor(self.solar_output_mw, "MW"),
                "battery_power_mw": sensor(self.battery_output_mw, "MW"),
                "battery_soc_pct": sensor(self.battery_soc_pct, "%"),
                "interchange_mw": sensor(self.import_mw, "MW"),
                "curtailed_generation_mw": sensor(self.curtailed_generation_mw, "MW"),
                "island_count": sensor(len(self.islands), "count"),
                "reactive_margin_mvar": sensor(self.reactive_margin_mvar, "MVAr"),
            }
            sensors.update({"aux_"+tag.lower().replace("-", "_")+"_feedback_pct": sensor(d["feedback_pct"], "%") for tag,d in self.operations.devices.items()})
            for index, voltage in enumerate(self.bus_voltages_pu, start=1):
                sensors[f"bus_{index}_voltage_pu"] = sensor(voltage, "pu")
            equipment = {
                "buses": [
                    {"id": "B1", "name": "North generation", "voltage_pu": round(self.bus_voltages_pu[0], 3)},
                    {"id": "B2", "name": "Central 230 kV", "voltage_pu": round(self.bus_voltages_pu[1], 3)},
                    {"id": "B3", "name": "Metro load", "voltage_pu": round(self.bus_voltages_pu[2], 3)},
                    {"id": "B4", "name": "Industrial load", "voltage_pu": round(self.bus_voltages_pu[3], 3)},
                    {"id": "B5", "name": "South DER", "voltage_pu": round(self.bus_voltages_pu[4], 3)},
                ],
                "generators": [
                    {"id": "G1", "name": "Gas turbine", "output_mw": round(self.gas_output_mw, 1), "available": self.gas_output_mw > 0.1},
                    {"id": "G2", "name": "Hydro", "output_mw": round(self.hydro_output_mw, 1), "available": True},
                    {"id": "W1", "name": "Wind", "output_mw": round(self.wind_output_mw, 1), "available": True},
                    {"id": "S1", "name": "Solar", "output_mw": round(self.solar_output_mw, 1), "available": True},
                ],
                "loads": [{"bus": f"B{index + 1}", "mw": round(load, 1)} for index, load in enumerate(getattr(self, "loads", [55.0, 105.0, 390.0, 290.0, 160.0]))],
                "lines": self.line_results,
            }
            flows = [
                {"source": f"B{int(line['source']) + 1}", "target": f"B{int(line['target']) + 1}", "medium": str(line["id"]), "value": float(line["flow_mw"]), "unit": "MW", "status": "open" if not bool(line["closed"]) else "critical" if float(line["loading_pct"]) > 100 else "normal", "loading_pct": float(line["loading_pct"]), "closed": bool(line["closed"])}
                for line in self.line_results
            ]
            return LabSnapshot(
                domain="grid",
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
                    {"name": "Generator MW setpoints", "type": "active-power dispatch", "authority": "AI eligible inside gate"},
                    {"name": "Battery charge or discharge", "type": "fast balancing", "authority": "AI eligible inside gate"},
                    {"name": "Capacitor banks and transformer taps", "type": "voltage support", "authority": "AI eligible inside gate"},
                    {"name": "Demand response", "type": "controllable load", "authority": "AI eligible inside gate"},
                    {"name": "Line breakers", "type": "network topology", "authority": "operator and deterministic protection"},
                    {"name": "Renewable availability and customer load", "type": "external conditions", "authority": "forecast and measurement"},
                ],
                output_channels=[
                    {"name": "System frequency", "type": "supply-demand balance", "authority": "monitored"},
                    {"name": "Bus voltages", "type": "voltage security", "authority": "monitored"},
                    {"name": "Line MW flow and loading", "type": "thermal security", "authority": "monitored"},
                    {"name": "Generation and reserve", "type": "resource adequacy", "authority": "monitored"},
                    {"name": "Served and unserved load", "type": "continuity", "authority": "monitored"},
                    {"name": "Battery state of charge", "type": "flexibility", "authority": "monitored"},
                ],
                model_health={"islands": self.islands, "balance_residual_mw": max(abs(i["balance_residual_mw"]) for i in self.islands),
                              "voltage_model": "Heuristic voltage estimate; DC flow does not solve reactive power",
                              "frequency_model": "Aggregate minute-resolution response; island transient frequency is not resolved"},
                note="Five-bus DC load-flow and reduced-order frequency model. It is not a protection, stability, or market-settlement study.",
            )
