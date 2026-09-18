import csv
import io
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field


class ExerciseAction(BaseModel):
    action: Literal["acknowledge", "note"]
    occurrence: int | None = None
    note: str = Field(default="", max_length=500)


def exercise_router(resolve):
    router = APIRouter()

    @router.get("/{domain}/exercise")
    def report(domain: str):
        sim = resolve(domain)
        with sim.lock:
            sim.exercise.capture(sim.snapshot(), sim.minute)
            return sim.exercise.report()

    @router.post("/{domain}/exercise")
    def action(domain: str, request: ExerciseAction):
        sim = resolve(domain)
        with sim.lock:
            sim.exercise.capture(sim.snapshot(), sim.minute)
            if request.action == "acknowledge":
                try:
                    sim.exercise.acknowledge(request.occurrence, sim.minute)
                except ValueError as exc:
                    raise HTTPException(409, str(exc)) from exc
            else:
                if not request.note.strip():
                    raise HTTPException(422, "Enter an operator observation")
                sim.exercise.event(sim.minute, "note", request.note.strip())
            return sim.exercise.report()

    @router.get("/{domain}/exercise/export")
    def export(domain: str, format: str = Query("json", pattern="^(json|csv)$")):
        sim = resolve(domain)
        with sim.lock:
            sim.exercise.capture(sim.snapshot(), sim.minute)
            data = sim.exercise.report(include_samples=True)
        if format == "json":
            body, media = json.dumps(data, allow_nan=False), "application/json"
        else:
            buffer = io.StringIO()
            tags = sorted({key for sample in data["samples"] for key in sample["values"]})
            writer = csv.writer(buffer)
            writer.writerow(["minute", "simulation_time", *tags])
            for sample in data["samples"]:
                writer.writerow([sample["minute"], sample["simulation_time"], *[sample["values"].get(k, "") for k in tags]])
            body, media = buffer.getvalue(), "text/csv"
        return Response(body, media_type=media, headers={"Content-Disposition": f'attachment; filename="{domain}-{data["run_id"]}.{format}"'})

    return router
