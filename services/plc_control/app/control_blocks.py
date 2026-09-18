from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class PIController:
    """Small discrete PI block with anti-windup and output slew limiting."""

    name: str
    kp: float
    ki_per_minute: float
    output_min: float
    output_max: float
    slew_per_minute: float
    integral: float = 0.0
    last_output: float | None = None
    saturated: bool = False

    def reset(self, output: float | None = None) -> None:
        self.integral = 0.0
        self.last_output = output
        self.saturated = False

    def update(
        self,
        *,
        setpoint: float,
        process_value: float,
        dt_minutes: float,
        feedforward: float = 0.0,
        hold_integral: bool = False,
    ) -> float:
        dt = clamp(dt_minutes, 0.0, 10.0)
        error = setpoint - process_value
        proportional = self.kp * error
        raw_before_integral = feedforward + proportional + self.integral

        if not hold_integral and dt > 0:
            candidate = self.integral + self.ki_per_minute * error * dt
            candidate = clamp(candidate, -0.75 * (self.output_max - self.output_min), 0.75 * (self.output_max - self.output_min))
            candidate_raw = feedforward + proportional + candidate
            drives_back_from_high = raw_before_integral > self.output_max and error < 0
            drives_back_from_low = raw_before_integral < self.output_min and error > 0
            if self.output_min <= raw_before_integral <= self.output_max or drives_back_from_high or drives_back_from_low:
                self.integral = candidate
                raw_before_integral = candidate_raw

        bounded = clamp(raw_before_integral, self.output_min, self.output_max)
        self.saturated = bounded != raw_before_integral
        if self.last_output is not None and dt > 0:
            maximum_change = self.slew_per_minute * dt
            bounded = clamp(bounded, self.last_output - maximum_change, self.last_output + maximum_change)
        self.last_output = bounded
        return bounded

    def status(self, setpoint: float, process_value: float) -> dict[str, float | bool | str]:
        return {
            "name": self.name,
            "setpoint": round(setpoint, 3),
            "process_value": round(process_value, 3),
            "error": round(setpoint - process_value, 3),
            "integral": round(self.integral, 3),
            "output": round(self.last_output or 0.0, 3),
            "saturated": self.saturated,
        }


@dataclass
class OnDelayTimer:
    delay_minutes: float
    accumulated_minutes: float = 0.0

    def update(self, condition: bool, dt_minutes: float) -> bool:
        if condition:
            self.accumulated_minutes += max(0.0, dt_minutes)
        else:
            self.accumulated_minutes = 0.0
        return self.accumulated_minutes >= self.delay_minutes

    def reset(self) -> None:
        self.accumulated_minutes = 0.0


@dataclass
class EquipmentRuntime:
    running: bool = False
    runtime_minutes: float = 0.0
    stopped_minutes: float = 999.0
    starts: int = 0

    def update(self, requested_running: bool, dt_minutes: float, minimum_off_minutes: float = 0.0) -> bool:
        dt = max(0.0, dt_minutes)
        if self.running:
            if requested_running:
                self.runtime_minutes += dt
                self.stopped_minutes = 0.0
            else:
                self.running = False
                self.stopped_minutes = dt
            return self.running

        self.stopped_minutes += dt
        if requested_running and self.stopped_minutes >= minimum_off_minutes:
            self.running = True
            self.starts += 1
            self.runtime_minutes = 0.0
            self.stopped_minutes = 0.0
        return self.running

    def status(self) -> dict[str, float | int | bool]:
        return {
            "running": self.running,
            "runtime_minutes": round(self.runtime_minutes, 1),
            "stopped_minutes": round(self.stopped_minutes, 1),
            "starts": self.starts,
        }


class BackwashPhase(str, Enum):
    IDLE = "idle"
    BLOCKED = "blocked"
    ISOLATING = "isolating"
    BACKWASH = "backwash"
    RINSE = "rinse"
    RETURNING = "returning"


@dataclass
class BackwashSequencer:
    phase: BackwashPhase = BackwashPhase.IDLE
    phase_started_at: datetime | None = None
    request_pending: bool = False
    request_source: str = "automatic"
    blocked_reason: str | None = None
    completed_cycles: int = 0
    event_log: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.phase = BackwashPhase.IDLE
        self.phase_started_at = None
        self.request_pending = False
        self.request_source = "automatic"
        self.blocked_reason = None
        self.completed_cycles = 0
        self.event_log = []

    def request(self, source: str) -> None:
        if self.phase in {BackwashPhase.IDLE, BackwashPhase.BLOCKED}:
            self.request_pending = True
            self.request_source = source

    def _transition(self, phase: BackwashPhase, now: datetime, note: str) -> None:
        self.phase = phase
        self.phase_started_at = now
        self.event_log.append(f"{now.isoformat()} {note}")
        self.event_log = self.event_log[-12:]

    def _elapsed(self, now: datetime) -> float:
        if self.phase_started_at is None:
            return 0.0
        return max(0.0, (now - self.phase_started_at).total_seconds() / 60.0)

    def update(
        self,
        *,
        now: datetime,
        filter_dp_kpa: float,
        clearwell_level_pct: float,
        outlet_position_pct: float,
        sensor_quality_ok: bool,
    ) -> dict[str, float | bool | str | None]:
        automatic_request = filter_dp_kpa >= 55.0
        if automatic_request and self.phase == BackwashPhase.IDLE:
            self.request("automatic high differential pressure")

        storage_ok = clearwell_level_pct >= 50.0
        pressure_ok = filter_dp_kpa >= 38.0
        permissive_ok = storage_ok and pressure_ok and sensor_quality_ok

        if self.phase in {BackwashPhase.ISOLATING, BackwashPhase.BACKWASH, BackwashPhase.RINSE}:
            if clearwell_level_pct < 35.0 or not sensor_quality_ok:
                reason = (
                    "clearwell storage fell below the 35 percent abort point"
                    if clearwell_level_pct < 35.0
                    else "required sensor quality was lost"
                )
                self.blocked_reason = reason
                self._transition(BackwashPhase.RETURNING, now, f"Backwash aborted because {reason}")

        if self.phase in {BackwashPhase.IDLE, BackwashPhase.BLOCKED} and self.request_pending:
            if not permissive_ok:
                reasons = []
                if not storage_ok:
                    reasons.append("clearwell storage below 50 percent")
                if not pressure_ok:
                    reasons.append("filter differential pressure below 38 kPa")
                if not sensor_quality_ok:
                    reasons.append("required sensor quality is not good")
                self.blocked_reason = ", ".join(reasons)
                self.phase = BackwashPhase.BLOCKED
            else:
                self.blocked_reason = None
                self.request_pending = False
                self._transition(BackwashPhase.ISOLATING, now, f"Backwash sequence started by {self.request_source}")

        elapsed = self._elapsed(now)
        if self.phase == BackwashPhase.ISOLATING and outlet_position_pct <= 20.0:
            self._transition(BackwashPhase.BACKWASH, now, "Filter outlet isolated and backwash started")
        elif self.phase == BackwashPhase.BACKWASH and elapsed >= 5.0:
            self._transition(BackwashPhase.RINSE, now, "Backwash finished and rinse started")
        elif self.phase == BackwashPhase.RINSE and elapsed >= 2.0:
            self._transition(BackwashPhase.RETURNING, now, "Rinse finished and outlet reopening")
        elif self.phase == BackwashPhase.RETURNING and outlet_position_pct >= 80.0:
            self.completed_cycles += 1
            self._transition(BackwashPhase.IDLE, now, "Filter returned to service")

        overrides: dict[str, float | bool | str | None] = {
            "phase": self.phase.value,
            "phase_elapsed_minutes": round(self._elapsed(now), 1),
            "blocked_reason": self.blocked_reason,
            "backwash_request": False,
        }
        if self.phase == BackwashPhase.ISOLATING:
            overrides.update(intake_pump_speed_pct=25.0, filter_outlet_valve_pct=15.0)
        elif self.phase == BackwashPhase.BACKWASH:
            overrides.update(intake_pump_speed_pct=0.0, filter_outlet_valve_pct=15.0, backwash_request=True)
        elif self.phase == BackwashPhase.RINSE:
            overrides.update(intake_pump_speed_pct=20.0, filter_outlet_valve_pct=20.0)
        elif self.phase == BackwashPhase.RETURNING:
            overrides.update(intake_pump_speed_pct=45.0, filter_outlet_valve_pct=95.0)
        return overrides

    def status(self, now: datetime | None) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "phase_elapsed_minutes": round(self._elapsed(now), 1) if now else 0.0,
            "request_pending": self.request_pending,
            "request_source": self.request_source,
            "blocked_reason": self.blocked_reason,
            "completed_cycles": self.completed_cycles,
            "recent_events": self.event_log[-5:],
        }
