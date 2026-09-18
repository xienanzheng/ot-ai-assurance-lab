from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from shared.models import FaultInjectionRequest, ModeChange, SimulationCommand
from .opcua_server import WaterOpcUaServer
from .scenarios import INJECTIONS, injection_list, scenario_list
from .simulator import WaterPlantSimulator


simulator = WaterPlantSimulator(speed=int(os.getenv("SIM_SPEED", "10")))
opcua = WaterOpcUaServer(simulator)


async def simulation_loop() -> None:
    while True:
        if simulator.running:
            simulator.advance(1)
        await opcua.sync()
        await asyncio.sleep(60 / simulator.speed if simulator.running else 0.5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await opcua.start()
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()
    await opcua.stop()


app = FastAPI(title="WaterLab Plant Simulator", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "plant-sim"}


@app.get("/state")
def state():
    return simulator.snapshot()


@app.get("/scenarios")
def scenarios():
    return scenario_list()


@app.get("/injections")
def injections():
    return {"definitions": injection_list(), "active": simulator.active_injections()}


@app.post("/injections/{injection_id}")
def activate_injection(injection_id: str, request: FaultInjectionRequest):
    if injection_id not in INJECTIONS:
        raise HTTPException(status_code=404, detail="Unknown lab fault injection")
    active = simulator.inject(injection_id, request.duration_minutes)
    simulator.exercise.event(simulator.minute, "injection", injection_id, duration_minutes=request.duration_minutes)
    simulator.running = True
    simulator.advance(1)
    return {"status": "active", "injection_id": injection_id, "active": active, "plant": simulator.snapshot()}


@app.delete("/injections")
def clear_injections():
    simulator.clear_injections()
    simulator.exercise.event(simulator.minute, "injection", "Cleared field overrides")
    return {"status": "cleared", "active": []}


@app.put("/mode")
def mode(request: ModeChange):
    simulator.controller_mode = request.mode
    return {"mode": request.mode}


@app.post("/command")
async def command(request: SimulationCommand):
    if request.action == "start":
        simulator.running = True
    elif request.action == "pause":
        simulator.running = False
    elif request.action == "reset":
        current = request.config
        simulator.reset(
            seed=current.seed if current else simulator.seed,
            speed=current.speed if current else simulator.speed,
            scenario=current.scenario if current else simulator.scenario,
        )
        if current:
            simulator.controller_mode = current.controller_mode
        await opcua.push_actuators()
        await opcua.sync()
    elif request.action == "step":
        simulator.running = False
        await opcua.sync()
        simulator.advance(request.minutes)
        await opcua.sync()
    elif request.action == "configure" and request.config:
        simulator.configure(
            scenario=request.config.scenario,
            seed=request.config.seed,
            speed=request.config.speed,
            mode=request.config.controller_mode,
        )
        await opcua.push_actuators()
        await opcua.sync()
    else:
        raise HTTPException(status_code=400, detail="Invalid simulation command")
    simulator.exercise.event(simulator.minute, "command", request.action)
    return simulator.snapshot()


from shared.exercise_api import exercise_router

def exercise_simulator(domain):
    if domain != "water":
        raise HTTPException(404, "Unknown simulation domain")
    return simulator

app.include_router(exercise_router(exercise_simulator))


from shared.operations_api import operations_router
app.include_router(operations_router(exercise_simulator))
