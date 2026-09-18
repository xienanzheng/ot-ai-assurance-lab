from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field


class OperationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["equipment", "incident", "end_incident"]
    changes: dict[str, dict] = Field(default_factory=dict)
    incident_id: str | None = None
    start_running: bool = True
    duration_minutes: int = Field(default=45, ge=5, le=180)


def operations_router(resolve):
    router = APIRouter()

    @router.get("/{domain}/operations")
    def state(domain: str):
        sim = resolve(domain)
        with sim.lock:
            return sim.operations.snapshot(sim)

    @router.post("/{domain}/operations")
    def command(domain: str, request: OperationsRequest):
        sim = resolve(domain)
        with sim.lock:
            try:
                if request.action == "equipment":
                    sim.operations.command(request.changes)
                elif request.action == "incident":
                    sim.operations.start_incident(request.incident_id, sim.minute, request.duration_minutes)
                    if request.start_running:
                        sim.running = True
                else:
                    sim.operations.incident = None
            except ValueError as exc:
                sim.exercise.event(sim.minute, "operations_rejected", str(exc), action=request.action)
                raise HTTPException(409, str(exc)) from exc
            sim.exercise.event(sim.minute, "operations_"+request.action, request.incident_id or request.action,
                               changes=request.changes, duration_minutes=request.duration_minutes)
            return sim.operations.snapshot(sim)

    return router
