from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import timedelta, datetime
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException

from shared.models import ControlMode, ControlProposal, GateDecision, ManualCommand, PlantSnapshot
from .controller import BaselineController, SafetyGate
from .opc_client import OpcActuatorClient


OPCUA_URL = os.getenv("OPCUA_URL", "opc.tcp://plant-sim:4840/waterlab/server/")
PLANT_API_URL = os.getenv("PLANT_API_URL", "http://plant-sim:8081")
controller = BaselineController()
gate = SafetyGate(controller)
opc = OpcActuatorClient(OPCUA_URL)
last_cycle_time = None
connected = False
scan_lock = asyncio.Lock()
controller_generation = str(uuid4())


async def fetch_snapshot() -> PlantSnapshot:
    return await opc.read_snapshot()


async def baseline_loop() -> None:
    global last_cycle_time, connected
    while True:
        try:
            await scan_once()
            connected = True
        except Exception:
            connected = False
        await asyncio.sleep(0.35)


async def scan_once():
    global last_cycle_time
    async with scan_lock:
        snapshot = await fetch_snapshot()
        release_needed = controller.supervisory_expiry is not None and snapshot.controller_mode.value != "gated_auto"
        if snapshot.simulation_time != last_cycle_time or release_needed:
            await opc.write(controller.calculate(snapshot))
            last_cycle_time = snapshot.simulation_time
        return {"simulation_time": snapshot.simulation_time.isoformat()}


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(baseline_loop())
    yield
    task.cancel()


app = FastAPI(title="WaterLab PLC Controller", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "plc-control", "opcua_connected": connected}


@app.get("/status")
def status():
    return {
        "controller_generation": controller_generation,
        "setpoints": controller.setpoint_dict(),
        "last_command": controller.last_command.model_dump(),
        "control_state": controller.status(),
        "opcua_connected": connected,
    }


@app.post("/proposal", response_model=GateDecision)
async def evaluate_proposal(proposal: ControlProposal, apply: bool = False, lease_minutes: int = 5, expected_controller_generation: str | None = None, expected_time: str | None = None, expected_mode: str | None = None):
    try:
        async with scan_lock:
            snapshot = await fetch_snapshot()
            if expected_controller_generation is not None and expected_controller_generation != controller_generation:
                raise HTTPException(409, "PLC reset while the model was reasoning")
            if expected_mode is not None and expected_mode != snapshot.controller_mode.value:
                raise HTTPException(409, "Control mode changed during inference")
            if expected_time is not None and not 0 <= (snapshot.simulation_time-datetime.fromisoformat(expected_time)).total_seconds() <= 300:
                raise HTTPException(409, "Proposal snapshot is stale or clock was reset")
            if apply and snapshot.controller_mode.value != "gated_auto":
                raise HTTPException(409, "AI actuation requires gated_auto mode")
            decision = gate.evaluate(proposal, snapshot)
            if decision.status in {"accepted", "modified"} and apply:
                controller.apply_setpoint_changes(
                    decision.applied_values,
                    valid_until=snapshot.simulation_time + timedelta(minutes=max(1, min(60, lease_minutes))),
                    source=proposal.source,
                )
            return decision
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="OPC UA plant state is unavailable") from exc


@app.post("/manual", response_model=GateDecision)
async def manual(command: ManualCommand):
    proposal = ControlProposal(
        changes=command.changes,
        expected_effect="Operator-requested setpoint adjustment",
        confidence=1.0,
        explanation="Confirmed manual command",
        source="manual",
    )
    decision = gate.evaluate(proposal, await fetch_snapshot())
    if decision.status in {"accepted", "modified"}:
        controller.apply_setpoint_changes(decision.applied_values, source="manual")
    return decision


@app.post("/interlocks/reset")
async def reset_interlocks():
    snapshot = await fetch_snapshot()
    result = controller.reset_trips(snapshot)
    return {**result, "control_state": controller.status()}


@app.post("/emergency-stop")
async def emergency_stop():
    snapshot = await fetch_snapshot()
    command = controller.calculate(snapshot).model_copy(update={
        "intake_pump_speed_pct": 0.0,
        "high_lift_pump_speed_pct": 0.0,
        "booster_pump_speed_pct": 0.0,
        "coagulant_dose_mg_l": 0.0,
        "chlorine_dose_mg_l": 0.0,
        "naoh_dose_mg_l": 0.0,
        "backwash_request": False,
        "emergency_stop": True,
    })
    await opc.write(command)
    return {"status": "stopped", "controller_mode": ControlMode.BASELINE.value}


@app.post("/scan")
async def scan():
    return await scan_once()

@app.post("/reset")
async def reset_controller():
    global controller, gate, last_cycle_time, controller_generation
    async with scan_lock:
        controller_generation = str(uuid4())
        controller = BaselineController()
        gate = SafetyGate(controller)
        last_cycle_time = None
    return await scan_once()
