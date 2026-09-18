from __future__ import annotations

import json

try:
    from app import watcher_outbox
except ModuleNotFoundError:
    from services.supervisor.app import watcher_outbox


def test_outbox_exports_only_allowlisted_open_weight_decision_fields(tmp_path):
    path = tmp_path / "decisions.jsonl"
    watcher_outbox.OUTBOX_PATH = str(path)
    exported = watcher_outbox.export_open_weight_decision(
        domain="water",
        simulation_time="2026-01-01T00:05:00Z",
        scenario="normal_operation",
        controller_mode="advisory",
        model_id="qwen3:8b",
        proposal={
            "source": "ollama",
            "decision_id": "decision-1",
            "expected_effect": "Maintain pressure",
            "changes": {"pressure_target_m": 42.0, "non_scalar": {"secret": "blocked"}},
            "confidence": 0.82,
            "explanation": "Small bounded adjustment",
            "raw_prompt": "must never be exported",
            "sensor_dump": {"must": "never be exported"},
        },
        gate={
            "status": "accepted",
            "violated_constraints": [],
            "applied_values": {"pressure_target_m": 42.0},
            "internal_policy": "must never be exported",
        },
    )
    assert exported is True
    record = json.loads(path.read_text())
    assert record["model_id"] == "qwen3:8b"
    assert record["decision"]["proposed_changes"] == {"pressure_target_m": 42.0}
    assert record["local_gate"]["applied_values"] == {"pressure_target_m": 42.0}
    serialized = path.read_text()
    assert "raw_prompt" not in serialized
    assert "sensor_dump" not in serialized
    assert "internal_policy" not in serialized
    assert "must never be exported" not in serialized


def test_outbox_does_not_export_manual_test_or_fallback_decisions(tmp_path):
    path = tmp_path / "decisions.jsonl"
    watcher_outbox.OUTBOX_PATH = str(path)
    for source in ("manual", "test", "deterministic fallback policy", ""):
        exported = watcher_outbox.export_open_weight_decision(
            domain="nuclear",
            simulation_time="2026-01-01T00:00:00Z",
            scenario="normal_operation",
            controller_mode="advisory",
            model_id="qwen3:8b",
            proposal={"source": source, "changes": {}, "confidence": 0.0},
            gate={"status": "rejected"},
        )
        assert exported is False
    assert path.exists() is False
