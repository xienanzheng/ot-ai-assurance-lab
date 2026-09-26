from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ControlMode(str, Enum):
    BASELINE = "baseline"
    ADVISORY = "advisory"
    SHADOW = "shadow"
    GATED_AUTO = "gated_auto"


class SensorValue(BaseModel):
    value: float
    unit: str
    quality: Literal["good", "uncertain", "bad", "stale"] = "good"
    timestamp: datetime = Field(default_factory=utc_now)


class EquipmentState(BaseModel):
    enabled: bool = True
    running: bool = False
    speed_pct: float = 0.0
    flow_m3h: float = 0.0
    efficiency_pct: float = 100.0


class ValveState(BaseModel):
    valve_type: Literal["gate", "isolation", "throttle", "prv"]
    command_pct: float = Field(ge=0, le=100)
    position_pct: float = Field(ge=0, le=100)
    status: Literal["closed", "opening", "open", "closing", "throttled", "interlocked"]
    upstream_pressure_m: float = 0.0
    downstream_pressure_m: float = 0.0
    differential_pressure_kpa: float = 0.0
    flow_m3h: float = 0.0
    travel_rate_pct_min: float = 12.0
    interlocked: bool = False


class ProcessCheckpoint(BaseModel):
    sequence: int
    name: str
    location: str
    purpose: str
    status: Literal["normal", "warning", "critical", "unavailable"] = "normal"
    sensor_tags: list[str]


class TwinHealth(BaseModel):
    telemetry_source: str = "simulated OPC UA telemetry"
    last_model_update: datetime
    telemetry_age_seconds: float = 0.0
    pressure_rmse_m: float = 0.0
    flow_residual_pct: float = 0.0
    zone_pressure_residuals_m: dict[str, float] = Field(default_factory=dict)
    fit_status: Literal["good", "warning", "poor", "stale"] = "good"
    calibration_note: str = "Simulated telemetry is compared with the hydraulic model."
    integrity_flags: list[str] = Field(default_factory=list)


class Alarm(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    code: str
    severity: Literal["info", "warning", "critical"]
    message: str
    active: bool = True
    started_at: datetime = Field(default_factory=utc_now)


class PlantSnapshot(BaseModel):
    simulation_time: datetime
    elapsed_minutes: int = 0
    simulation_speed: int = 10
    running: bool = False
    scenario: str = "normal_day"
    controller_mode: ControlMode = ControlMode.BASELINE
    sensors: dict[str, SensorValue]
    operations: dict = Field(default_factory=dict)
    equipment: dict[str, EquipmentState]
    actuators: dict[str, float | bool]
    valves: dict[str, ValveState] = Field(default_factory=dict)
    checkpoints: list[ProcessCheckpoint] = Field(default_factory=list)
    twin_health: TwinHealth | None = None
    active_alarms: list[Alarm] = []
    forecast_demand_m3h: list[float] = []
    recent_trends: dict[str, list[float]] = {}
    safety_state: Literal["normal", "warning", "critical"] = "normal"
    emergency_stop: bool = False
    active_injections: list[str] = Field(default_factory=list)
    note: str = "Illustrative simulation values. Not regulatory limits."


class RunConfig(BaseModel):
    scenario: str = "normal_day"
    seed: int = 42
    duration_hours: float = Field(default=24, gt=0, le=168)
    speed: Literal[1, 10, 60] = 10
    controller_mode: ControlMode = ControlMode.BASELINE
    model: str = "qwen3:8b"
    ai_decision_interval_minutes: int = Field(default=5, ge=5, le=60)
    ai_schedule_enabled: bool = True
    memory_enabled: bool = True
    memory_window: int = Field(default=4, ge=0, le=8)


class SetpointChanges(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    clearwell_target_pct: float | None = None
    elevated_tank_target_pct: float | None = None
    pressure_target_m: float | None = None
    chlorine_target_mg_l: float | None = None
    coagulant_target_mg_l: float | None = None
    finished_water_ph_target: float | None = None
    intake_gate_target_pct: float | None = None
    filter_outlet_valve_target_pct: float | None = None
    zone_1_isolation_target_pct: float | None = None
    zone_2_isolation_target_pct: float | None = None
    zone_3_isolation_target_pct: float | None = None
    backwash_request: bool | None = None


class ControlProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    proposed_at: datetime = Field(default_factory=utc_now)
    changes: SetpointChanges
    expected_effect: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(min_length=1, max_length=280)
    source: Literal["ollama", "jev", "manual", "test"] = "ollama"
    episode_status: Literal["continue", "resolved", "escalate"] = "continue"


class GateDecision(BaseModel):
    decision_id: str
    status: Literal["accepted", "modified", "rejected"]
    violated_constraints: list[str] = Field(default_factory=list)
    modifications: list[str] = Field(default_factory=list)
    evaluated_rules: list[str] = Field(default_factory=list)
    predicted_state: dict[str, float] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high"] = "low"
    applied_values: SetpointChanges = Field(default_factory=SetpointChanges)
    fallback_reason: str | None = None
    evaluated_at: datetime = Field(default_factory=utc_now)


class RunMetrics(BaseModel):
    run_id: str
    safety_violations: int = 0
    demand_served_pct: float = 100.0
    energy_kwh: float = 0.0
    chemical_use_kg: float = 0.0
    coagulant_use_kg: float = 0.0
    chlorine_use_kg: float = 0.0
    naoh_use_kg: float = 0.0
    mean_pressure_error_m: float = 0.0
    ai_acceptance_rate_pct: float = 0.0
    intervention_count: int = 0
    samples: int = 0


class ManualCommand(BaseModel):
    changes: SetpointChanges
    confirmation: Literal["CONFIRM"]


class ModeChange(BaseModel):
    mode: ControlMode


class StepRequest(BaseModel):
    minutes: int = Field(default=1, ge=1, le=60)


class SimulationCommand(BaseModel):
    action: Literal["start", "pause", "reset", "step", "configure"]
    config: RunConfig | None = None
    minutes: int = 1


class FaultInjectionRequest(BaseModel):
    duration_minutes: int = Field(default=60, ge=1, le=1440)


class ActuatorCommand(BaseModel):
    intake_pump_speed_pct: float | None = None
    high_lift_pump_speed_pct: float | None = None
    booster_pump_speed_pct: float | None = None
    outlet_valve_pct: float | None = None
    intake_gate_pct: float | None = None
    filter_outlet_valve_pct: float | None = None
    zone_1_isolation_valve_pct: float | None = None
    zone_2_isolation_valve_pct: float | None = None
    zone_3_isolation_valve_pct: float | None = None
    pressure_reducing_valve_setpoint_m: float | None = None
    coagulant_dose_mg_l: float | None = None
    chlorine_dose_mg_l: float | None = None
    naoh_dose_mg_l: float | None = None
    backwash_request: bool | None = None
    emergency_stop: bool | None = None

    @field_validator(
        "intake_pump_speed_pct",
        "high_lift_pump_speed_pct",
        "booster_pump_speed_pct",
        "outlet_valve_pct",
        "intake_gate_pct",
        "filter_outlet_valve_pct",
        "zone_1_isolation_valve_pct",
        "zone_2_isolation_valve_pct",
        "zone_3_isolation_valve_pct",
    )
    @classmethod
    def percent_range(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 100:
            raise ValueError("percent command must be between 0 and 100")
        return value
