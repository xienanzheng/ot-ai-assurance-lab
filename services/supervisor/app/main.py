from __future__ import annotations

import asyncio
import csv
import io
import json
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select

from shared.models import ControlMode, FaultInjectionRequest, ManualCommand, ModeChange, RunConfig, StepRequest
from .database import AlarmRecord, DecisionRecord, RunRecord, SampleRecord, SessionLocal, initialize_database
from .run_manager import RunManager
from .ollama_client import OllamaUnavailable
from .watcher_outbox import export_open_weight_decision
from .agents import AgentService


manager = RunManager(
    os.getenv("PLANT_API_URL", "http://plant-sim:8081"),
    os.getenv("PLC_API_URL", "http://plc-control:8082"),
)
INFRASTRUCTURE_API_URL = os.getenv("INFRASTRUCTURE_API_URL", "http://infrastructure-sim:8083").rstrip("/")
agents = AgentService(manager, INFRASTRUCTURE_API_URL)


async def background_sampler() -> None:
    while True:
        await manager.sample_and_decide()
        await asyncio.sleep(0.3)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    task = asyncio.create_task(background_sampler())
    agent_task = asyncio.create_task(agents.monitor())
    yield
    task.cancel()
    agent_task.cancel()
    for pending in agents.tasks:
        pending.cancel()


app = FastAPI(title="WaterLab Supervisor API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    try:
        await manager.plant_state()
        plant = "connected"
    except Exception:
        plant = "unavailable"
    return {"status": "ok", "service": "supervisor-api", "plant": plant}


@app.get("/api/v1/state")
async def state():
    try:
        snapshot = await manager.plant_state()
        plc = await manager.plc_status()
        return {"plant": snapshot, "plc": plc, "latest_decision": manager.latest_decision, "active_run_id": manager.active_run_id, "ollama": await manager.ollama.status(), "memory": manager.memory_status()}
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="OT simulation is unavailable") from exc


@app.get("/api/v1/scenarios")
async def scenarios():
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{manager.plant_url}/scenarios")
        response.raise_for_status()
    return response.json()


@app.get("/api/v1/injections")
async def injections():
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{manager.plant_url}/injections")
        response.raise_for_status()
    return response.json()


@app.post("/api/v1/injections/{injection_id}")
async def activate_injection(injection_id: str, request: FaultInjectionRequest):
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(
            f"{manager.plant_url}/injections/{injection_id}",
            json=request.model_dump(mode="json"),
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Unknown lab fault injection")
        response.raise_for_status()
    return response.json()


@app.delete("/api/v1/injections")
async def clear_injections():
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.delete(f"{manager.plant_url}/injections")
        response.raise_for_status()
    return response.json()


@app.get("/api/v1/infrastructure/state")
async def infrastructure_state():
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{INFRASTRUCTURE_API_URL}/state")
        response.raise_for_status()
    return response.json()


@app.get("/api/v1/infrastructure/scenarios")
async def infrastructure_scenarios():
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(f"{INFRASTRUCTURE_API_URL}/scenarios")
        response.raise_for_status()
    return response.json()


@app.post("/api/v1/infrastructure/{domain}/command")
async def infrastructure_command(domain: str, payload: dict):
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.post(f"{INFRASTRUCTURE_API_URL}/{domain}/command", json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.json().get("detail", "Simulation request failed"))
        response.raise_for_status()
    return response.json()


@app.post("/api/v1/infrastructure/{domain}/manual")
async def infrastructure_manual(domain: str, payload: dict):
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.post(f"{INFRASTRUCTURE_API_URL}/{domain}/manual", json=payload)
        if response.status_code >= 400:
            raise HTTPException(status_code=response.status_code, detail=response.json().get("detail", "Simulation request failed"))
        response.raise_for_status()
    return response.json()


@app.put("/api/v1/infrastructure/nuclear/tuning")
async def infrastructure_nuclear_tuning(payload: dict):
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.put(f"{INFRASTRUCTURE_API_URL}/nuclear/tuning", json=payload)
        response.raise_for_status()
    return response.json()


@app.post("/api/v1/infrastructure/{domain}/ai")
async def infrastructure_ai(domain: str):
    if domain not in {"nuclear", "grid"}:
        raise HTTPException(404, "Unknown simulation domain")
    try:
        record = await agents.cycle(domain, evaluate_only=False)
    except OllamaUnavailable as exc:
        raise HTTPException(503, "Local AI unavailable; baseline retained control. Inspect the agent audit.") from exc
    context = await agents.context(domain)
    proposal = record["proposal"]
    return {"decision":{**proposal,"gate":record["gate"],"source":f"ollama:{manager.ollama.model}"},"plant":context["plant"],"audit_id":record["id"]}


@app.get("/api/v1/runs")
def list_runs():
    with SessionLocal() as db:
        runs = db.scalars(select(RunRecord).order_by(RunRecord.started_at.desc())).all()
        return [{"id": run.id, "status": run.status, "config": run.config, "started_at": run.started_at, "ended_at": run.ended_at} for run in runs]


@app.post("/api/v1/runs", status_code=201)
def create_run(config: RunConfig):
    run_id = manager.create_run(config)
    return {"id": run_id, "status": "created", "config": config}


def unknown_run(exc: KeyError):
    raise HTTPException(status_code=404, detail="Run not found") from exc


@app.post("/api/v1/runs/{run_id}/start")
async def start_run(run_id: str):
    try:
        return await manager.start(run_id)
    except KeyError as exc:
        unknown_run(exc)


@app.post("/api/v1/runs/{run_id}/pause")
async def pause_run(run_id: str):
    try:
        return await manager.pause(run_id)
    except KeyError as exc:
        unknown_run(exc)


@app.post("/api/v1/runs/{run_id}/reset")
async def reset_run(run_id: str):
    try:
        return await manager.reset(run_id)
    except KeyError as exc:
        unknown_run(exc)


@app.post("/api/v1/runs/{run_id}/step")
async def step_run(run_id: str, request: StepRequest):
    try:
        return await manager.step(run_id, request.minutes)
    except KeyError as exc:
        unknown_run(exc)


@app.put("/api/v1/control/mode")
async def control_mode(request: ModeChange):
    if manager.active_run_id:
        with SessionLocal() as db:
            run = db.get(RunRecord, manager.active_run_id)
            run.config = {**run.config, "controller_mode": request.mode.value}
            manager.active_config = RunConfig.model_validate(run.config)
            db.commit()
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.put(f"{manager.plant_url}/mode", json=request.model_dump(mode="json"))
        response.raise_for_status()
    return {"mode": request.mode, "active_run_id": manager.active_run_id}


@app.post("/api/v1/control/manual")
async def manual_control(command: ManualCommand):
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.post(f"{manager.plc_url}/manual", json=command.model_dump(mode="json"))
        response.raise_for_status()
    return response.json()


@app.post("/api/v1/control/interlocks/reset")
async def reset_control_interlocks():
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.post(f"{manager.plc_url}/interlocks/reset")
        response.raise_for_status()
    return response.json()


@app.post("/api/v1/emergency-stop")
async def emergency_stop():
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.post(f"{manager.plc_url}/emergency-stop")
        response.raise_for_status()
    if manager.active_config:
        manager.active_config.controller_mode = ControlMode.BASELINE
        with SessionLocal() as db:
            run = db.get(RunRecord, manager.active_run_id)
            if run:
                run.config = {**run.config, "controller_mode": ControlMode.BASELINE.value}
                db.commit()
    async with httpx.AsyncClient(timeout=5) as client:
        await client.put(f"{manager.plant_url}/mode", json={"mode": ControlMode.BASELINE.value})
    return response.json()


@app.get("/api/v1/decisions")
def decisions(limit: int = Query(default=50, ge=1, le=500)):
    with SessionLocal() as db:
        rows = db.scalars(select(DecisionRecord).order_by(DecisionRecord.id.desc()).limit(limit)).all()
        return [{"decision_id": row.decision_id, "run_id": row.run_id, "simulation_time": row.simulation_time, "mode": row.mode, "proposal": row.proposal, "gate": row.gate} for row in rows]


@app.get("/api/v1/memory")
def memory():
    return manager.memory_status()


@app.get("/api/v1/alarms")
def alarms(limit: int = Query(default=100, ge=1, le=1000)):
    with SessionLocal() as db:
        rows = db.scalars(select(AlarmRecord).order_by(AlarmRecord.id.desc()).limit(limit)).all()
        return [{"run_id": row.run_id, "simulation_time": row.simulation_time, "code": row.code, "severity": row.severity, "message": row.message} for row in rows]


@app.get("/api/v1/runs/{run_id}/metrics")
def run_metrics(run_id: str):
    try:
        return manager.metrics(run_id)
    except KeyError as exc:
        unknown_run(exc)


@app.get("/api/v1/runs/{run_id}/export")
def export_run(run_id: str, format: str = Query(default="csv", pattern="^(csv|json)$")):
    try:
        manager._require_run(run_id)
    except KeyError as exc:
        unknown_run(exc)
    with SessionLocal() as db:
        samples = db.scalars(select(SampleRecord).where(SampleRecord.run_id == run_id).order_by(SampleRecord.id)).all()
        rows = [{"simulation_time": row.simulation_time, **{name: sensor["value"] for name, sensor in row.payload["sensors"].items()}, "safety_state": row.payload["safety_state"]} for row in samples]
    if format == "json":
        return Response(content=json.dumps(rows, indent=2), media_type="application/json", headers={"Content-Disposition": f'attachment; filename="waterlab-{run_id}.json"'})
    output = io.StringIO()
    fieldnames = list(rows[0].keys()) if rows else ["simulation_time"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="waterlab-{run_id}.csv"'})


@app.websocket("/api/v1/live")
async def live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                snapshot = await manager.plant_state()
                plc = await manager.plc_status()
                payload = {"plant": snapshot.model_dump(mode="json"), "plc": plc, "latest_decision": manager.latest_decision, "active_run_id": manager.active_run_id, "memory": manager.memory_status()}
            except (httpx.HTTPError, ValueError):
                payload = {"error": "OT simulation is unavailable"}
            await websocket.send_json(payload)
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        return


async def forward_exercise(domain, suffix="", payload=None, format="json"):
    if domain not in {"water", "nuclear", "grid"}:
        raise HTTPException(404, "Unknown simulation domain")
    base = manager.plant_url if domain == "water" else INFRASTRUCTURE_API_URL
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.request("POST" if payload is not None else "GET",
            f"{base}/{domain}/exercise{suffix}", json=payload, params={"format": format})
    return Response(response.content, status_code=response.status_code,
        media_type=response.headers.get("content-type", "application/json"),
        headers={k: v for k, v in response.headers.items() if k == "content-disposition"})

@app.get("/api/v1/training/{domain}")
async def training_report(domain: str):
    return await forward_exercise(domain)

@app.post("/api/v1/training/{domain}")
async def training_action(domain: str, payload: dict):
    return await forward_exercise(domain, payload=payload)

@app.get("/api/v1/training/{domain}/export")
async def training_export(domain: str, format: str = Query("json", pattern="^(json|csv)$")):
    return await forward_exercise(domain, suffix="/export", format=format)


async def forward_operations(domain, payload=None):
    if domain not in {"water", "nuclear", "grid"}:
        raise HTTPException(404, "Unknown simulation domain")
    base = manager.plant_url if domain == "water" else INFRASTRUCTURE_API_URL
    async with httpx.AsyncClient(timeout=8) as client:
        response = await client.request("POST" if payload is not None else "GET", f"{base}/{domain}/operations", json=payload)
    return Response(response.content, status_code=response.status_code, media_type="application/json")

@app.get("/api/v1/operations/{domain}")
async def operations_state(domain: str):
    return await forward_operations(domain)

@app.post("/api/v1/operations/{domain}")
async def operations_command(domain: str, payload: dict):
    return await forward_operations(domain, payload)

app.include_router(agents.router)
