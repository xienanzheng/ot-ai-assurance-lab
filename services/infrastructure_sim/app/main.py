from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from .grid import GRID_SCENARIOS, GridSimulator
from .models import AiRequest, ExternalAiProposal, LabCommand, ManualControl, NuclearTuningRequest
from .nuclear import NUCLEAR_SCENARIOS, NuclearSimulator


nuclear = NuclearSimulator()
grid = GridSimulator()
SIMULATORS = {"nuclear": nuclear, "grid": grid}


async def simulation_loop(simulator) -> None:
    while True:
        if simulator.running:
            simulator.advance(1)
            await asyncio.sleep(60.0 / simulator.speed)
        else:
            await asyncio.sleep(0.35)


@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = [asyncio.create_task(simulation_loop(simulator)) for simulator in SIMULATORS.values()]
    yield
    for task in tasks:
        task.cancel()


app = FastAPI(title="Critical Infrastructure Training Simulators", version="1.0.0", lifespan=lifespan)


def get_simulator(domain: str):
    simulator = SIMULATORS.get(domain)
    if simulator is None:
        raise HTTPException(status_code=404, detail="Unknown simulation domain")
    return simulator


@app.get("/health")
def health():
    return {"status": "ok", "service": "infrastructure-sim"}


@app.get("/state")
def state():
    return {name: simulator.snapshot() for name, simulator in SIMULATORS.items()}


@app.get("/scenarios")
def scenarios():
    return {"nuclear": NUCLEAR_SCENARIOS, "grid": GRID_SCENARIOS}


@app.get("/{domain}/state")
def domain_state(domain: str):
    return get_simulator(domain).snapshot()


@app.post("/{domain}/command")
def command(domain: str, request: LabCommand):
    simulator = get_simulator(domain)
    allowed = NUCLEAR_SCENARIOS if domain == "nuclear" else GRID_SCENARIOS
    if request.scenario is not None and request.scenario not in {s["id"] for s in allowed}:
        raise HTTPException(422, "Unknown scenario for this domain")
    return simulator.command(
        request.action,
        minutes=request.minutes,
        speed=request.speed,
        scenario=request.scenario,
        mode=request.controller_mode,
    )


@app.post("/{domain}/manual")
def manual(domain: str, request: ManualControl):
    simulator = get_simulator(domain)
    result = simulator.manual(request.changes)
    return {"gate": result, "plant": simulator.snapshot()}


@app.post("/{domain}/ai")
def ai_cycle(domain: str, _: AiRequest):
    simulator = get_simulator(domain)
    decision = simulator.run_ai_cycle()
    return {"decision": decision, "plant": simulator.snapshot()}


@app.post("/{domain}/proposal")
def external_ai_proposal(domain: str, proposal: ExternalAiProposal):
    simulator = get_simulator(domain)
    with simulator.lock:
        if proposal.expected_run_id is not None and proposal.expected_run_id != simulator.exercise.run_id:
            raise HTTPException(409, "Exercise changed while the model was reasoning")
        if proposal.expected_minute is not None and not 0 <= simulator.minute-proposal.expected_minute <= 5:
            raise HTTPException(409, "Proposal snapshot is stale or simulation clock was reset")
        if proposal.expected_mode is not None and proposal.expected_mode != simulator.controller_mode:
            raise HTTPException(409, "Control mode changed during inference")
        mode = simulator.controller_mode
        if proposal.evaluate_only:
            simulator.controller_mode = "shadow"
        try:
            decision = simulator.apply_ai_proposal(changes=proposal.changes, confidence=proposal.confidence,
                objective=proposal.objective, explanation=proposal.explanation, source=proposal.source)
        finally:
            simulator.controller_mode = mode
        return {"decision": decision, "plant": simulator.snapshot()}

@app.get("/{domain}/agent-context")
def agent_context(domain: str):
    simulator = get_simulator(domain)
    with simulator.lock:
        return {"plant": simulator.snapshot(), "run_id": simulator.exercise.run_id}


@app.put("/nuclear/tuning")
def nuclear_tuning(request: NuclearTuningRequest):
    nuclear.set_tuning(request.model_dump())
    return nuclear.snapshot()


from shared.exercise_api import exercise_router
app.include_router(exercise_router(get_simulator))


from shared.operations_api import operations_router
app.include_router(operations_router(get_simulator))
