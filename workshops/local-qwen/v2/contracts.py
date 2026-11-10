from __future__ import annotations
import hashlib
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


def digest(value):
    data = value.model_dump(mode='json') if isinstance(value, BaseModel) else value
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class Measurement(Contract):
    value: float
    unit: str
    source_time: float
    quality: Literal['good', 'bad', 'uncertain'] = 'good'


class Snapshot(Contract):
    schema_version: Literal['1'] = '1'
    site: str
    package_hash: str
    generation: str
    sequence: int = Field(ge=0)
    source_time: float
    process_time: float = Field(ge=0)
    target: float
    armed: bool
    readings: dict[str, Measurement]
    critical: bool = False
    trip_latched: bool = False
    override: bool = False
    wait_until: float = 0
    connection_epoch: str = ''
    received_at: float = 0


class Proposal(Contract):
    status: Literal['hold', 'adjust', 'escalate']
    target: float | None = None
    rationale: str = Field(min_length=1, max_length=1200)
    evidence: list[str] = Field(default_factory=list, max_length=20)
    operator_checks: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode='after')
    def consistent(self):
        if (self.status == 'adjust') != (self.target is not None):
            raise ValueError('Only adjust requires a target')
        return self


class AuditResult(Contract):
    status: Literal['passed', 'flagged', 'unavailable']
    reason: str = Field(min_length=1, max_length=300)
    proposal_hash: str


class CommandRequest(Contract):
    id: str = Field(min_length=1, max_length=100)
    snapshot: Snapshot
    proposal: Proposal
    issued_at: float
    expires_at: float
    policy: Literal['off', 'observe', 'required'] = 'off'
    audit: AuditResult | None = None


class Package(Contract):
    schema_version: Literal['1'] = '1'
    id: str
    version: str
    title: str
    sensor: str
    unit: str
    capability: str
    initial_value: float
    initial_target: float
    minimum: float
    maximum: float
    max_delta: float = Field(gt=0)
    max_excursion: float = Field(gt=0)
    objective: tuple[float, float]
    critical_limits: tuple[float, float]
    response_seconds: float = Field(gt=0)
    observe_seconds: float = Field(gt=0)
    sustain_seconds: float = Field(gt=0)
    max_episode_seconds: float = Field(gt=0)
    disturbance: float
    max_decision_age: float = Field(default=30,gt=0,le=60)
    sop: list[str]
    checks: dict[str, str]
    relationships: list[str]

    @model_validator(mode='after')
    def ordered(self):
        if not self.minimum < self.initial_target < self.maximum:
            raise ValueError('Target outside bounds')
        if not self.objective[0] < self.objective[1]:
            raise ValueError('Invalid objective')
        return self

    def fingerprint(self):
        return digest(self)
