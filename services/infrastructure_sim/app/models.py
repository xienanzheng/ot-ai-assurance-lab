from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


class LabCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["start", "pause", "reset", "step", "configure"]
    minutes: int = Field(default=1, ge=1, le=120)
    speed: Literal[1, 10, 60] | None = None
    scenario: str | None = None
    controller_mode: Literal["baseline", "advisory", "shadow", "gated_auto"] | None = None


class ManualControl(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    changes: dict[str, float | bool]
    confirmation: Literal["CONFIRM"]


class ScenarioRequest(BaseModel):
    scenario: str


class AiRequest(BaseModel):
    force: bool = True


class ExternalAiProposal(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    objective: str = Field(min_length=3, max_length=180)
    changes: dict[str, float]
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=3, max_length=500)
    source: str = Field(default="ollama", max_length=80)
    expected_run_id: str | None = None
    expected_minute: int | None = None
    expected_mode: str | None = None
    evaluate_only: bool = False


class NuclearTuningRequest(BaseModel):
    preset: Literal["nominal", "slow_thermal", "high_inertia", "degraded_heat_transfer", "custom"] = "nominal"
    thermal_response: float = Field(default=1.0, ge=0.5, le=1.5)
    pressure_response: float = Field(default=1.0, ge=0.5, le=1.5)
    inventory_response: float = Field(default=1.0, ge=0.5, le=1.5)
    condenser_response: float = Field(default=1.0, ge=0.5, le=1.5)


class GateResult(BaseModel):
    status: Literal["accepted", "rejected", "advisory", "shadow"]
    reasons: list[str] = Field(default_factory=list)
    applied: dict[str, float | bool] = Field(default_factory=dict)


class AiDecision(BaseModel):
    objective: str
    changes: dict[str, float | bool]
    confidence: float
    explanation: str
    gate: GateResult
    source: str = "deterministic demonstration policy"


class LabSnapshot(BaseModel):
    domain: Literal["nuclear", "grid"]
    simulation_time: str
    elapsed_minutes: int
    running: bool
    speed: int
    scenario: str
    controller_mode: str
    safety_state: Literal["normal", "warning", "critical"]
    alarms: list[dict[str, str]]
    sensors: dict[str, dict[str, Any]]
    controls: dict[str, float | bool | str]
    operations: dict[str, Any] = Field(default_factory=dict)
    equipment: dict[str, Any]
    flows: list[dict[str, Any]]
    ai_decision: AiDecision | None = None
    input_channels: list[dict[str, str]] = Field(default_factory=list)
    output_channels: list[dict[str, str]] = Field(default_factory=list)
    history: dict[str, list[float]] = Field(default_factory=dict)
    procedures: list[dict[str, Any]] = Field(default_factory=list)
    model_health: dict[str, Any] = Field(default_factory=dict)
    tuning: dict[str, Any] = Field(default_factory=dict)
    alarm_timeline: list[dict[str, Any]] = Field(default_factory=list)
    note: str
