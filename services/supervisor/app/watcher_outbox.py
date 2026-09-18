from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


OUTBOX_PATH = os.getenv("WATCHER_OUTBOX_PATH", "").strip()
_write_lock = Lock()


def _text(value: Any, limit: int) -> str:
    return str(value or "")[:limit]


def _scalar_changes(changes: Any) -> dict[str, float | bool]:
    if not isinstance(changes, dict):
        return {}
    clean: dict[str, float | bool] = {}
    for name, value in list(changes.items())[:24]:
        if isinstance(value, bool):
            clean[_text(name, 80)] = value
        elif isinstance(value, (int, float)):
            clean[_text(name, 80)] = round(float(value), 6)
    return clean


def export_open_weight_decision(
    *,
    domain: str,
    simulation_time: str,
    scenario: str,
    controller_mode: str,
    model_id: str,
    proposal: dict[str, Any],
    gate: dict[str, Any],
) -> bool:
    """Append an allowlisted Ollama decision record to the one-way outbox."""
    source = _text(proposal.get("source"), 80).lower()
    if not OUTBOX_PATH or not source.startswith("ollama"):
        return False

    raw_changes = proposal.get("changes", {})
    if hasattr(raw_changes, "model_dump"):
        raw_changes = raw_changes.model_dump(exclude_none=True)
    record = {
        "schema_version": "waterlab.open_weight_decision.v1",
        "event_id": str(uuid4()),
        "decision_id": _text(proposal.get("decision_id"), 80),
        "domain": _text(domain, 24),
        "simulation_time": _text(simulation_time, 64),
        "scenario": _text(scenario, 80),
        "controller_mode": _text(controller_mode, 24),
        "model_id": _text(model_id, 100),
        "decision": {
            "objective": _text(proposal.get("objective") or proposal.get("expected_effect"), 240),
            "proposed_changes": _scalar_changes(raw_changes),
            "confidence": round(float(proposal.get("confidence", 0.0)), 4),
            "explanation": _text(proposal.get("explanation"), 280),
        },
        "local_gate": {
            "status": _text(gate.get("status"), 24),
            "violated_constraints": [_text(item, 180) for item in gate.get("violated_constraints", gate.get("reasons", []))[:12]],
            "applied_values": _scalar_changes(gate.get("applied_values", gate.get("applied", {}))),
            "fallback_reason": _text(gate.get("fallback_reason"), 180),
        },
    }

    path = Path(OUTBOX_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock, path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n")
    return True
