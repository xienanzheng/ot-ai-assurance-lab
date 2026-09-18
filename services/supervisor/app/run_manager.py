from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
from sqlalchemy import select

from shared.models import ControlProposal, GateDecision, PlantSnapshot, RunConfig, RunMetrics, SetpointChanges
from .database import AlarmRecord, DecisionRecord, MetricRecord, RunRecord, SampleRecord, SessionLocal
from .ollama_client import OllamaSupervisor, OllamaUnavailable
from .watcher_outbox import export_open_weight_decision
from .agent_audit import update_audit


class RunManager:
    def __init__(self, plant_url: str, plc_url: str) -> None:
        self.plant_url = plant_url.rstrip("/")
        self.plc_url = plc_url.rstrip("/")
        self.ollama = OllamaSupervisor()
        self.active_run_id: str | None = None
        self.active_config: RunConfig | None = None
        self.last_sample_time: str | None = None
        self.last_decision_minute: int = -1
        self.latest_decision: dict | None = None
        self.initial_simulation_time: datetime | None = None
        self.last_memory_context: list[dict] = []

    async def plant_state(self) -> PlantSnapshot:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.get(f"{self.plant_url}/state")
            response.raise_for_status()
        return PlantSnapshot.model_validate(response.json())

    async def plc_status(self) -> dict:
        async with httpx.AsyncClient(timeout=4) as client:
            response = await client.get(f"{self.plc_url}/status")
            response.raise_for_status()
        return response.json()

    async def command_plant(self, action: str, config: RunConfig | None = None, minutes: int = 1) -> PlantSnapshot:
        payload = {"action": action, "minutes": minutes, "config": config.model_dump(mode="json") if config else None}
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(f"{self.plant_url}/command", json=payload)
            response.raise_for_status()
        return PlantSnapshot.model_validate(response.json())

    def create_run(self, config: RunConfig) -> str:
        run_id = str(uuid4())
        with SessionLocal() as db:
            db.add(RunRecord(id=run_id, status="created", config=config.model_dump(mode="json")))
            db.add(MetricRecord(run_id=run_id, payload=RunMetrics(run_id=run_id).model_dump()))
            db.commit()
        return run_id

    async def start(self, run_id: str) -> PlantSnapshot:
        config = self._config_for(run_id)
        if self.active_run_id == run_id:
            snapshot = await self.command_plant("start")
            with SessionLocal() as db:
                db.get(RunRecord, run_id).status = "running"
                db.commit()
            return snapshot
        await self.command_plant("configure", config)
        await self.reset_plc()
        snapshot = await self.command_plant("start")
        self.active_run_id = run_id
        self.active_config = config
        self.initial_simulation_time = snapshot.simulation_time - timedelta(minutes=snapshot.elapsed_minutes)
        self.last_sample_time = None
        self.last_decision_minute = -1
        self.last_memory_context = []
        with SessionLocal() as db:
            run = db.get(RunRecord, run_id)
            run.status = "running"
            run.started_at = datetime.now(timezone.utc)
            db.commit()
        return snapshot

    async def pause(self, run_id: str) -> PlantSnapshot:
        self._require_run(run_id)
        if self.active_run_id != run_id:
            raise KeyError("Run is not active")
        snapshot = await self.command_plant("pause")
        with SessionLocal() as db:
            run = db.get(RunRecord, run_id)
            run.status = "paused"
            db.commit()
        return snapshot

    async def reset(self, run_id: str) -> PlantSnapshot:
        config = self._config_for(run_id)
        snapshot = await self.command_plant("reset", config)
        await self.reset_plc()
        self.active_run_id = run_id
        self.active_config = config
        self.initial_simulation_time = snapshot.simulation_time
        self.last_sample_time = None
        self.last_decision_minute = -1
        self.last_memory_context = []
        with SessionLocal() as db:
            db.query(SampleRecord).filter(SampleRecord.run_id == run_id).delete()
            db.query(DecisionRecord).filter(DecisionRecord.run_id == run_id).delete()
            db.query(AlarmRecord).filter(AlarmRecord.run_id == run_id).delete()
            db.get(MetricRecord, run_id).payload = RunMetrics(run_id=run_id).model_dump()
            db.get(RunRecord, run_id).status = "created"
            db.commit()
        return snapshot

    async def step(self, run_id: str, minutes: int) -> PlantSnapshot:
        self._require_run(run_id)
        if self.active_run_id != run_id:
            raise KeyError("Run is not active")
        await self.command_plant("pause")
        async with httpx.AsyncClient(timeout=8) as client:
            for _ in range(minutes):
                response = await client.post(f"{self.plc_url}/scan")
                response.raise_for_status()
                snapshot = await self.command_plant("step", minutes=1)
                await self.sample_and_decide()
        with SessionLocal() as db:
            db.get(RunRecord, run_id).status = "paused"
            db.commit()
        return snapshot

    async def reset_plc(self):
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(f"{self.plc_url}/reset")
            response.raise_for_status()

    def _require_run(self, run_id: str) -> RunRecord:
        with SessionLocal() as db:
            run = db.get(RunRecord, run_id)
            if run is None:
                raise KeyError(run_id)
            db.expunge(run)
            return run

    def _config_for(self, run_id: str) -> RunConfig:
        return RunConfig.model_validate(self._require_run(run_id).config)

    async def sample_and_decide(self) -> None:
        if not self.active_run_id or not self.active_config:
            return
        try:
            snapshot = await self.plant_state()
        except httpx.HTTPError:
            return
        stamp = snapshot.simulation_time.isoformat()
        if stamp == self.last_sample_time:
            return
        self.last_sample_time = stamp
        self._record_sample(snapshot)
        if self.initial_simulation_time is None:
            self.initial_simulation_time = snapshot.simulation_time
        elapsed = int((snapshot.simulation_time - self.initial_simulation_time).total_seconds() / 60)
        interval = self.active_config.ai_decision_interval_minutes
        if self.active_config.ai_schedule_enabled and self.active_config.controller_mode.value != "baseline" and elapsed >= 0 and elapsed % interval == 0 and elapsed != self.last_decision_minute:
            self.last_decision_minute = elapsed
            await self._ai_decision(snapshot)
        if elapsed >= int(self.active_config.duration_hours * 60):
            await self.command_plant("pause")
            with SessionLocal() as db:
                run = db.get(RunRecord, self.active_run_id)
                run.status = "completed"
                run.ended_at = datetime.now(timezone.utc)
                db.commit()

    async def _ai_decision(self, snapshot: PlantSnapshot) -> None:
        plc = await self.plc_status()
        memory_context = self._memory_context(
            snapshot,
            self.active_config.memory_window if self.active_config.memory_enabled else 0,
        )
        self.last_memory_context = memory_context
        inference_id = None
        try:
            if snapshot.scenario == "unsafe_ai":
                proposal = ControlProposal(
                    changes=SetpointChanges(pressure_target_m=92.0, chlorine_target_mg_l=4.6),
                    expected_effect="Increase pressure and disinfectant quickly",
                    confidence=0.98,
                    explanation="Deliberately unsafe test proposal",
                    source="test",
                )
            else:
                proposal = await self.ollama.propose(
                    snapshot,
                    plc["setpoints"],
                    control_state=plc.get("control_state"),
                    memory_context=memory_context,
                    model=self.active_config.model,
                )
            inference_id = proposal.decision_id
            apply = self.active_config.controller_mode.value == "gated_auto"
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post(
                    f"{self.plc_url}/proposal",
                    params={"apply": str(apply).lower(), "lease_minutes": self.active_config.ai_decision_interval_minutes,
                            "expected_controller_generation": plc["controller_generation"], "expected_time":snapshot.simulation_time.isoformat(),
                            "expected_mode":snapshot.controller_mode.value},
                    json=proposal.model_dump(mode="json"),
                )
                response.raise_for_status()
            decision = GateDecision.model_validate(response.json())
        except (OllamaUnavailable, httpx.HTTPError) as exc:
            proposal = ControlProposal(
                changes=SetpointChanges(),
                expected_effect="No change",
                confidence=0.0,
                explanation="AI proposal unavailable",
                source="test",
            )
            decision = GateDecision(
                decision_id=proposal.decision_id,
                status="rejected",
                violated_constraints=["AI timeout, connection, or schema failure"],
                fallback_reason="Baseline controller retained control",
            )
        update_audit(inference_id, status="complete", before={"plant":snapshot.model_dump(mode="json"), "plc":plc, "run_id":self.active_run_id},
                     gate=decision.model_dump(mode="json"), applied=self.active_config.controller_mode.value=="gated_auto" and decision.status in {"accepted", "modified"},
                     outcome={"status":"awaiting later simulation sample"})
        self.latest_decision = {
            "proposal": proposal.model_dump(mode="json"),
            "gate": decision.model_dump(mode="json"),
            "mode": self.active_config.controller_mode.value,
            "memory": {
                "enabled": self.active_config.memory_enabled,
                "episodes_used": len(memory_context),
                "maximum_episodes": self.active_config.memory_window,
            },
        }
        with SessionLocal() as db:
            db.add(DecisionRecord(
                run_id=self.active_run_id,
                decision_id=proposal.decision_id,
                simulation_time=snapshot.simulation_time.isoformat(),
                mode=self.active_config.controller_mode.value,
                proposal=proposal.model_dump(mode="json"),
                gate=decision.model_dump(mode="json"),
            ))
            db.commit()
        export_open_weight_decision(
            domain="water",
            simulation_time=snapshot.simulation_time.isoformat(),
            scenario=snapshot.scenario,
            controller_mode=self.active_config.controller_mode.value,
            model_id=self.active_config.model,
            proposal=proposal.model_dump(mode="json"),
            gate=decision.model_dump(mode="json"),
        )

    def _memory_context(self, snapshot: PlantSnapshot, limit: int) -> list[dict]:
        """Retrieve bounded, auditable decision episodes with similar plant conditions."""
        if limit <= 0:
            return []
        sensor_scales = {
            "raw_turbidity_ntu": 25.0,
            "raw_alkalinity_mg_l_caco3": 60.0,
            "coagulation_ph": 2.0,
            "finished_water_ph": 2.0,
            "filtered_turbidity_ntu": 1.0,
            "clearwell_level_pct": 50.0,
            "elevated_tank_level_pct": 50.0,
            "chlorine_residual_mg_l": 2.0,
            "distribution_header_pressure_m": 40.0,
            "leak_flow_m3h": 60.0,
        }
        candidates: list[tuple[float, dict]] = []
        with SessionLocal() as db:
            decisions = db.scalars(select(DecisionRecord).order_by(DecisionRecord.id.desc()).limit(100)).all()
            for rank, decision in enumerate(decisions):
                if not decision.run_id:
                    continue
                run = db.get(RunRecord, decision.run_id)
                if not run or run.config.get("scenario") != snapshot.scenario:
                    continue
                sample = db.scalars(
                    select(SampleRecord).where(
                        SampleRecord.run_id == decision.run_id,
                        SampleRecord.simulation_time == decision.simulation_time,
                    ).limit(1)
                ).first()
                if not sample:
                    continue
                prior_sensors = sample.payload.get("sensors", {})
                distance = 0.0
                summary = {}
                for name, scale in sensor_scales.items():
                    if name not in prior_sensors or name not in snapshot.sensors:
                        continue
                    prior_value = float(prior_sensors[name]["value"])
                    current_value = snapshot.sensors[name].value
                    distance += ((prior_value - current_value) / scale) ** 2
                    summary[name] = round(prior_value, 3)
                recency_penalty = min(rank, 50) * 0.002
                candidates.append((distance + recency_penalty, {
                    "scenario": snapshot.scenario,
                    "simulation_time": decision.simulation_time,
                    "sensor_summary": summary,
                    "proposed_changes": decision.proposal.get("changes", {}),
                    "expected_effect": decision.proposal.get("expected_effect", ""),
                    "gate_status": decision.gate.get("status", "rejected"),
                    "violated_constraints": decision.gate.get("violated_constraints", [])[:3],
                }))
        candidates.sort(key=lambda item: item[0])
        return [episode for _, episode in candidates[:limit]]

    def memory_status(self) -> dict:
        config = self.active_config
        return {
            "enabled": bool(config and config.memory_enabled),
            "maximum_episodes": config.memory_window if config else 0,
            "episodes_in_last_prompt": len(self.last_memory_context),
            "strategy": "same-scenario numeric similarity from audited PostgreSQL decisions",
            "episodes": self.last_memory_context,
        }

    def _record_sample(self, snapshot: PlantSnapshot) -> None:
        with SessionLocal() as db:
            db.add(SampleRecord(run_id=self.active_run_id, simulation_time=snapshot.simulation_time.isoformat(), payload=snapshot.model_dump(mode="json")))
            from .lesson_memory import archive
            archive(db, {"id":f"sample:{self.active_run_id}:{snapshot.simulation_time.isoformat()}",
                         "domain":"water", "record_type":"sensor_event",
                         "request":{"model":self.active_config.model if self.active_config else None},
                         "before":{"run_id":self.active_run_id,"plant":snapshot.model_dump(mode="json")}})
            for alarm in snapshot.active_alarms:
                db.add(AlarmRecord(run_id=self.active_run_id, simulation_time=snapshot.simulation_time.isoformat(), code=alarm.code, severity=alarm.severity, message=alarm.message))
            db.commit()
        self._update_metrics()

    def _update_metrics(self) -> RunMetrics:
        run_id = self.active_run_id
        if not run_id:
            return RunMetrics(run_id="none")
        with SessionLocal() as db:
            samples = db.scalars(select(SampleRecord).where(SampleRecord.run_id == run_id).order_by(SampleRecord.id)).all()
            decisions = db.scalars(select(DecisionRecord).where(DecisionRecord.run_id == run_id)).all()
            if not samples:
                metrics = RunMetrics(run_id=run_id)
            else:
                demand_total = 0.0
                served_total = 0.0
                energy_kwh = 0.0
                coagulant_kg = 0.0
                chlorine_kg = 0.0
                naoh_kg = 0.0
                pressure_errors = []
                safety_violations = 0
                for record in samples:
                    state = record.payload
                    sensors = state["sensors"]
                    demand = sum(sensors[f"zone_{index}_demand_m3h"]["value"] for index in range(1, 4))
                    served = sum(sensors.get(f"zone_{index}_served_m3h", sensors[f"zone_{index}_demand_m3h"])["value"] for index in range(1, 4))
                    demand_total += demand
                    served_total += served
                    energy_kwh += sensors["energy_kw"]["value"] / 60.0
                    flow_m3h = sensors["raw_flow_m3h"]["value"]
                    coagulant_kg += flow_m3h * state["actuators"]["coagulant_dose_mg_l"] / 60_000
                    chlorine_kg += flow_m3h * state["actuators"]["chlorine_dose_mg_l"] / 60_000
                    naoh_kg += flow_m3h * state["actuators"].get("naoh_dose_mg_l", 0.0) / 60_000
                    pressure_errors.append(abs(44.0 - min(sensors[f"zone_{index}_pressure_m"]["value"] for index in range(1, 4))))
                    safety_violations += 1 if state["safety_state"] == "critical" else 0
                accepted = sum(1 for record in decisions if record.gate.get("status") in {"accepted", "modified"})
                metrics = RunMetrics(
                    run_id=run_id,
                    safety_violations=safety_violations,
                    demand_served_pct=round(100 * served_total / max(demand_total, 1), 2),
                    energy_kwh=round(energy_kwh, 2),
                    chemical_use_kg=round(coagulant_kg + chlorine_kg + naoh_kg, 4),
                    coagulant_use_kg=round(coagulant_kg, 4),
                    chlorine_use_kg=round(chlorine_kg, 4),
                    naoh_use_kg=round(naoh_kg, 4),
                    mean_pressure_error_m=round(sum(pressure_errors) / len(pressure_errors), 2),
                    ai_acceptance_rate_pct=round(100 * accepted / len(decisions), 1) if decisions else 0,
                    intervention_count=accepted,
                    samples=len(samples),
                )
            metric_record = db.get(MetricRecord, run_id)
            metric_record.payload = metrics.model_dump()
            metric_record.updated_at = datetime.now(timezone.utc)
            db.commit()
        return metrics

    def metrics(self, run_id: str) -> RunMetrics:
        self._require_run(run_id)
        if run_id == self.active_run_id:
            return self._update_metrics()
        with SessionLocal() as db:
            return RunMetrics.model_validate(db.get(MetricRecord, run_id).payload)
